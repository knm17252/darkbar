#!/usr/bin/env python3
"""DarkBar - blank the Touch Bar on demand (or after you go idle), with a fade.

Menu bar app (PyObjC). Left-click the icon toggles the bar, right-click shows the menu.
Uses PRIVATE NSTouchBar APIs (same trick as Pock / MTMR), so not App Store material.

Run: pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz && python3 darkbar_1g4a.py
"""
import ctypes
import ctypes.util
import os
import plistlib
import re
import sys

import objc
import Quartz
from AppKit import (
    NSAnimationContext, NSApp, NSApplication, NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSAttributedString, NSBackingStoreBuffered, NSButton, NSColor, NSCustomTouchBarItem,
    NSEvent, NSEventMaskKeyDown, NSFont, NSFontAttributeName, NSForegroundColorAttributeName,
    NSImage, NSImageView, NSLinkAttributeName, NSMenu, NSMutableAttributedString,
    NSTextAlignmentCenter, NSMenuItem, NSMutableParagraphStyle, NSObject, NSParagraphStyleAttributeName,
    NSPopUpButton, NSRightTabStopType, NSStatusBar, NSTextField, NSTextTab, NSTouchBar,
    NSVariableStatusItemLength, NSView, NSWindow, NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSTimer, NSURL, NSUserDefaults
from PyObjCTools import AppHelper
from Quartz import CGEventCreateKeyboardEvent, CGEventPost, CGEventSourceSecondsSinceLastEventType, kCGHIDEventTap

VERSION, BUILD = "1.0", "1G4A"
# ---- About window text (edit these)
ABOUT_DESC = "A small utility to customize the behaviour of your Mac Touch Bar."
ABOUT_CREDIT = "Icon SVG template made by [(credit)](https://example.com)"   # [text](link) works
ABOUT_FOOTER = "Made in 2026 by A.B.Diamantopoulos"

BUNDLE_ID = "ua.mk.darkbar"
ITEM_ID = BUNDLE_ID + ".blackout"
BAR_W, BAR_H = 1085, 30
FADE = 0.35
AGENT = os.path.expanduser(f"~/Library/LaunchAgents/{BUNDLE_ID}.plist")

# auto-dim choices: label -> seconds of inactivity (0 = off)
TIMEOUTS = [("Off", 0), ("10 seconds", 10), ("30 seconds", 30), ("1 minute", 60),
            ("2 minutes", 120), ("5 minutes", 300), ("10 minutes", 600)]
IDLE_STATE = getattr(Quartz, "kCGEventSourceStateCombinedSessionState", 0)
IDLE_ANY = getattr(Quartz, "kCGAnyInputEventType", 0xFFFFFFFF)

# NSEvent modifier masks / Carbon modifier masks
CMD, SHIFT, OPT, CTRL = 1 << 20, 1 << 17, 1 << 19, 1 << 18
C_CMD, C_SHIFT, C_OPT, C_CTRL = 256, 512, 2048, 4096


# ---------------------------------------------------------------- private API
def _call(names, *args):
    for n in names:
        try:
            return getattr(NSTouchBar, n)(*args)
        except AttributeError:
            continue
    print("DarkBar: private Touch Bar API not found on this macOS", file=sys.stderr)


def present(tb):
    _call(["presentSystemModalTouchBar_placement_systemTrayItemIdentifier_",
           "presentSystemModalFunctionBar_placement_systemTrayItemIdentifier_"],
          tb, 1, ITEM_ID)


def dismiss(tb):
    _call(["dismissSystemModalTouchBar_", "dismissSystemModalFunctionBar_"], tb)


# ------------------------------------------------- global hotkey (Carbon, no permissions needed)
def fourcc(s):
    return int.from_bytes(s.encode("ascii"), "big")


carbon = ctypes.CDLL(ctypes.util.find_library("Carbon")
                     or "/System/Library/Frameworks/Carbon.framework/Carbon")


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
carbon.InstallEventHandler.argtypes = [ctypes.c_void_p, HANDLER, ctypes.c_uint32,
                                       ctypes.POINTER(EventTypeSpec), ctypes.c_void_p, ctypes.c_void_p]
carbon.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID,
                                       ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
carbon.GetEventParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]


class HotKeys:
    def __init__(self):
        self.refs, self.cbs = [], {}
        self._handler = HANDLER(self._on)  # keep a reference alive
        spec = EventTypeSpec(fourcc("keyb"), 5)  # kEventClassKeyboard, kEventHotKeyPressed
        carbon.InstallEventHandler(carbon.GetApplicationEventTarget(), self._handler,
                                   1, ctypes.byref(spec), None, None)

    def _on(self, call, event, userdata):
        hid = EventHotKeyID()
        carbon.GetEventParameter(event, fourcc("----"), fourcc("hkid"), None,
                                 ctypes.sizeof(hid), None, ctypes.byref(hid))
        cb = self.cbs.get(hid.id)
        if cb:
            cb()
        return 0

    def clear(self):
        for r in self.refs:
            carbon.UnregisterEventHotKey(r)
        self.refs, self.cbs = [], {}

    def add(self, hid, code, mods, cb):
        ref = ctypes.c_void_p()
        carbon.RegisterEventHotKey(code, mods, EventHotKeyID(fourcc("DBAR"), hid),
                                   carbon.GetApplicationEventTarget(), 0, ctypes.byref(ref))
        self.refs.append(ref)
        self.cbs[hid] = cb


def to_carbon(f):
    return ((C_CMD if f & CMD else 0) | (C_SHIFT if f & SHIFT else 0)
            | (C_OPT if f & OPT else 0) | (C_CTRL if f & CTRL else 0))


def label_for(flags, code, chars):
    parts = [n for m, n in ((CTRL, "Ctrl"), (OPT, "Opt"), (SHIFT, "Shift"), (CMD, "Cmd")) if flags & m]
    parts.append("Space" if code == 49 else (chars or "?").upper())
    return " + ".join(parts)


def press_esc():
    for down in (True, False):
        CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, 53, down))


def idle_seconds():
    return CGEventSourceSecondsSinceLastEventType(IDLE_STATE, IDLE_ANY)


def md_attr(text, font):
    """Turn 'plain [link text](https://url) plain' into an attributed string with clickable links."""
    out = NSMutableAttributedString.alloc().init()
    base = {NSFontAttributeName: font, NSForegroundColorAttributeName: NSColor.labelColor()}

    def add(s, attrs):
        out.appendAttributedString_(NSAttributedString.alloc().initWithString_attributes_(s, attrs))
    pos = 0
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        add(text[pos:m.start()], base)
        add(m.group(1), {**base, NSLinkAttributeName: NSURL.URLWithString_(m.group(2)),
                         NSForegroundColorAttributeName: NSColor.linkColor()})
        pos = m.end()
    add(text[pos:], base)
    return out


def resource_path(name):
    """Find a bundled file whether running as a plain script or from a PyInstaller/py2app .app."""
    bases = [getattr(sys, "_MEIPASS", None), os.environ.get("RESOURCEPATH"),
             os.path.dirname(os.path.abspath(__file__))]
    for base in bases:
        if base and os.path.exists(os.path.join(base, name)):
            return os.path.join(base, name)
    return None


# ------------------------------------------------------------------ login item
def set_login(on):
    if on:
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        os.makedirs(os.path.dirname(AGENT), exist_ok=True)
        with open(AGENT, "wb") as f:
            plistlib.dump({"Label": BUNDLE_ID, "ProgramArguments": args, "RunAtLoad": True}, f)
    elif os.path.exists(AGENT):
        os.remove(AGENT)


# ------------------------------------------------------------------------- app
class App(NSObject):
    def applicationDidFinishLaunching_(self, note):
        self.d = NSUserDefaults.standardUserDefaults()
        self.d.registerDefaults_({
            "launch": True, "esc": False, "timeout": 0, "dock": False,
            "hk_code": 17, "hk_mods": CMD | OPT, "hk_label": "Cmd + Opt + T",
        })
        self.tb = self.view = self.prefs = self.monitor = None
        self.active = False
        self.auto = False          # True while the bar is dark because of the idle timeout
        self.hotkeys = HotKeys()
        self.build_status()
        self.apply_hotkeys()
        set_login(self.d.boolForKey_("launch"))
        self.apply_dock()
        self.idle_timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0, True, lambda t: self.idle_tick())

    @objc.python_method
    def apply_dock(self):
        """Show or hide the Dock icon (Regular = Dock icon, Accessory = menu bar only)."""
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular if self.d.boolForKey_("dock")
                                   else NSApplicationActivationPolicyAccessory)

    @objc.python_method
    def cleanup(self):
        if self.active and self.tb is not None:
            dismiss(self.tb)
            self.active = False

    def applicationWillTerminate_(self, note):
        self.cleanup()

    # ---- status item + menu
    @objc.python_method
    def build_status(self):
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        btn = self.item.button()
        path = resource_path("icon.png")
        img = NSImage.alloc().initWithContentsOfFile_(path) if path else None
        if img:
            img.setSize_((18, 18))       # points; a 54px PNG is 3x
            img.setTemplate_(True)       # adapts to light/dark menu bar
            btn.setImage_(img)
        else:
            btn.setTitle_("\u25AC")      # fallback if icon.png is missing
        btn.setTarget_(self)
        btn.setAction_("statusClicked:")
        btn.sendActionOn_((1 << 2) | (1 << 4))  # left mouse up + right mouse up

        m = NSMenu.alloc().init()
        head = m.addItemWithTitle_action_keyEquivalent_("", None, "")
        head.setEnabled_(False)
        head.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(
            f"DarkBar {VERSION}",
            {NSFontAttributeName: NSFont.menuFontOfSize_(0),
             NSForegroundColorAttributeName: NSColor.labelColor()}))
        m.addItem_(NSMenuItem.separatorItem())
        m.addItemWithTitle_action_keyEquivalent_("About DarkBar...", "showAbout:", "").setTarget_(self)
        m.addItemWithTitle_action_keyEquivalent_("Preferences...", "showPrefs:", ",").setTarget_(self)
        m.addItem_(NSMenuItem.separatorItem())
        m.addItemWithTitle_action_keyEquivalent_("Quit DarkBar", "quit:", "q").setTarget_(self)
        self.menu = m

    def statusClicked_(self, sender):
        ev = NSApp.currentEvent()
        if ev.type() == 4 or (ev.modifierFlags() & CTRL):  # right mouse up / ctrl-click
            self.item.setMenu_(self.menu)
            self.item.button().performClick_(None)
            self.item.setMenu_(None)
        else:
            self.toggle_(None)

    def showAbout_(self, sender):
        if getattr(self, "about", None) is None:
            self.build_about()
        NSApp.activateIgnoringOtherApps_(True)
        self.about.makeKeyAndOrderFront_(None)

    @objc.python_method
    def build_about(self):
        W, H = 520, 270
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        w.setTitle_("About DarkBar")
        w.setReleasedWhenClosed_(False)
        w.center()
        c = w.contentView()

        # picture, no border: the app's .icns (macOS picks the 256/512 @1x/@2x rep that fits),
        # else about.png, else icon.png
        path = resource_path("DarkBar.icns") or resource_path("about.png") or resource_path("icon.png")
        img = NSImage.alloc().initWithContentsOfFile_(path) if path else None
        if img:
            img.setSize_((170, 170))              # so a 512px rep is drawn at 2x, crisp on Retina
        iv = NSImageView.alloc().initWithFrame_(NSMakeRect(24, 62, 170, 170))
        iv.setImageFrameStyle_(0)                 # NSImageFrameNone
        iv.setImageScaling_(3)                    # proportionally up or down
        if img:
            iv.setImage_(img)
        c.addSubview_(iv)

        def label(text, frame, font, color=None, wrap=False, center=False, md=False):
            t = NSTextField.wrappingLabelWithString_(text) if wrap else NSTextField.labelWithString_(text)
            t.setFrame_(frame)
            t.setFont_(font)
            if md:                                # [text](link) -> clickable link
                t.setAllowsEditingTextAttributes_(True)
                t.setSelectable_(True)
                t.setAttributedStringValue_(md_attr(text, font))
            if color is not None:
                t.setTextColor_(color)
            if center:
                t.setAlignment_(NSTextAlignmentCenter)
            if wrap:                                  # top-anchored: grow/shrink to fit the text
                h = t.cell().cellSizeForBounds_(NSMakeRect(0, 0, frame.size.width, 10000)).height
                top = frame.origin.y + frame.size.height
                t.setFrame_(NSMakeRect(frame.origin.x, top - h, frame.size.width, h))
            c.addSubview_(t)
            return t

        x, tw = 216, 280
        label("DarkBar", NSMakeRect(x, 188, tw, 40), NSFont.systemFontOfSize_(32))
        label(f"v.{VERSION}, build {BUILD}", NSMakeRect(x, 168, tw, 16),
              NSFont.systemFontOfSize_(11), NSColor.secondaryLabelColor())
        desc = label(ABOUT_DESC, NSMakeRect(x, 114, tw, 46), NSFont.systemFontOfSize_(13), wrap=True)
        cy = desc.frame().origin.y - 12            # credit starts just under the description
        label(ABOUT_CREDIT, NSMakeRect(x, 40, tw, cy - 40), NSFont.systemFontOfSize_(13), wrap=True, md=True)

        foot = NSFont.systemFontOfSize_(13)
        label(ABOUT_FOOTER, NSMakeRect(0, 22, W, 18), foot, center=True)
        self.about = w

    def quit_(self, sender):
        NSApp.terminate_(None)

    # ---- touch bar
    def toggle_(self, sender):
        """Manual toggle (menu icon / hotkey). Manual always wins over the idle timer."""
        self.auto = False
        self.hide() if self.active else self.show()

    @objc.python_method
    def show(self):
        self.view = self.make_view()
        self.view.setAlphaValue_(0.0)
        tb = NSTouchBar.alloc().init()
        tb.setDelegate_(self)
        tb.setDefaultItemIdentifiers_([ITEM_ID])
        self.tb = tb
        present(tb)
        self.active = True
        self.fade(1.0, None)

    @objc.python_method
    def hide(self):
        self.active = False
        tb = self.tb
        self.fade(0.0, lambda: dismiss(tb))

    @objc.python_method
    def fade(self, to, done):
        view = self.view

        def run(ctx):
            ctx.setDuration_(FADE)
            view.animator().setAlphaValue_(to)
        NSAnimationContext.runAnimationGroup_completionHandler_(run, done)

    @objc.python_method
    def make_view(self):
        v = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, BAR_W, BAR_H))
        v.setWantsLayer_(True)
        v.layer().setBackgroundColor_(NSColor.blackColor().CGColor())
        v.setTranslatesAutoresizingMaskIntoConstraints_(False)
        v.widthAnchor().constraintEqualToConstant_(BAR_W).setActive_(True)
        v.heightAnchor().constraintEqualToConstant_(BAR_H).setActive_(True)
        # invisible full-width button: tapping a timeout-dimmed bar wakes it
        tap = NSButton.buttonWithTitle_target_action_("", self, "tapBar:")
        tap.setBordered_(False)
        tap.setFrame_(NSMakeRect(0, 0, BAR_W, BAR_H))
        v.addSubview_(tap)
        if self.d.boolForKey_("esc"):
            b = NSButton.buttonWithTitle_target_action_("esc", self, "sendEsc:")
            b.setFrame_(NSMakeRect(4, 0, 64, BAR_H))
            v.addSubview_(b)
        return v

    def touchBar_makeItemForIdentifier_(self, tb, ident):
        item = NSCustomTouchBarItem.alloc().initWithIdentifier_(ident)
        item.setView_(self.view)
        return item

    def sendEsc_(self, sender):
        press_esc()

    def tapBar_(self, sender):
        if self.active and self.auto:
            self.auto = False
            self.hide()

    # ---- idle timeout
    @objc.python_method
    def idle_tick(self):
        limit = self.d.integerForKey_("timeout")
        if limit <= 0:
            return
        idle = idle_seconds()
        if not self.active and idle >= limit:
            self.auto = True
            self.show()
        elif self.active and self.auto and idle < 1.0:   # keyboard / mouse / trackpad activity
            self.auto = False
            self.hide()

    # ---- hotkey
    @objc.python_method
    def apply_hotkeys(self):
        self.hotkeys.clear()
        d = self.d
        if d.integerForKey_("hk_code") >= 0:
            self.hotkeys.add(1, d.integerForKey_("hk_code"), to_carbon(d.integerForKey_("hk_mods")),
                             lambda: self.toggle_(None))

    # ---- preferences window
    def showPrefs_(self, sender):
        if self.prefs is None:
            self.build_prefs()
        NSApp.activateIgnoringOtherApps_(True)
        self.prefs.makeKeyAndOrderFront_(None)

    @objc.python_method
    def build_prefs(self):
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 470, 250), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        w.setTitle_("Settings")
        w.setReleasedWhenClosed_(False)
        w.center()
        c = w.contentView()

        def row(y, text):
            lab = NSTextField.labelWithString_(text)
            lab.setFrame_(NSMakeRect(20, y, 230, 20))
            c.addSubview_(lab)

        def check(y, key, action):
            b = NSButton.checkboxWithTitle_target_action_("", self, action)
            b.setFrame_(NSMakeRect(260, y, 24, 20))
            b.setState_(1 if self.d.boolForKey_(key) else 0)
            c.addSubview_(b)

        row(200, "Open on launch:");                        check(200, "launch", "toggleLaunch:")
        row(160, "Show in Dock:");                          check(160, "dock", "toggleDock:")
        row(120, "Shortcut:")
        title = self.d.stringForKey_("hk_label") or "Click to record"
        b = NSButton.buttonWithTitle_target_action_(title, self, "record:")
        b.setFrame_(NSMakeRect(260, 116, 190, 28))
        c.addSubview_(b)
        row(80, "Enable esc (for pre-2020 MacBooks):");     check(80, "esc", "toggleEsc:")
        row(40, "Dim Touch Bar after inactivity:")
        pop = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(260, 36, 190, 26), False)
        pop.addItemsWithTitles_([t for t, _ in TIMEOUTS])
        cur = self.d.integerForKey_("timeout")
        pop.selectItemAtIndex_(next((i for i, (_, s) in enumerate(TIMEOUTS) if s == cur), 0))
        pop.setTarget_(self)
        pop.setAction_("timeoutChanged:")
        c.addSubview_(pop)
        self.prefs = w

    def toggleLaunch_(self, s):
        self.d.setBool_forKey_(s.state() == 1, "launch")
        set_login(s.state() == 1)

    def toggleDock_(self, s):
        self.d.setBool_forKey_(s.state() == 1, "dock")
        self.apply_dock()
        NSApp.activateIgnoringOtherApps_(True)       # policy change can drop focus; keep Settings up front
        self.prefs.makeKeyAndOrderFront_(None)

    def toggleEsc_(self, s):
        self.d.setBool_forKey_(s.state() == 1, "esc")

    def timeoutChanged_(self, s):
        secs = TIMEOUTS[s.indexOfSelectedItem()][1]
        self.d.setInteger_forKey_(secs, "timeout")
        if secs == 0 and self.active and self.auto:      # turned off while auto-dimmed: wake up
            self.auto = False
            self.hide()

    def record_(self, sender):
        if self.monitor:
            NSEvent.removeMonitor_(self.monitor)
        old = sender.title()
        sender.setTitle_("Press shortcut...")

        def handler(ev):
            code, flags = ev.keyCode(), ev.modifierFlags() & 0xFFFF0000
            if code == 53:                      # Esc cancels
                sender.setTitle_(old)
            elif flags & (CMD | OPT | CTRL):    # need at least one real modifier
                lab = label_for(flags, code, ev.charactersIgnoringModifiers())
                self.d.setInteger_forKey_(code, "hk_code")
                self.d.setInteger_forKey_(flags, "hk_mods")
                self.d.setObject_forKey_(lab, "hk_label")
                sender.setTitle_(lab)
                self.apply_hotkeys()
            else:
                return None                     # ignore, keep listening
            NSEvent.removeMonitor_(self.monitor)
            self.monitor = None
            return None

        self.monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, handler)


if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon
    delegate = App.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.installMachInterrupt()         # Ctrl-C in the terminal quits the app
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        delegate.cleanup()
