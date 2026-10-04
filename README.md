# DarkBar: A small utility to customize the behaviour of your Mac Touch Bar.

<table>
  <tr>
    <td width="220" valign="top">
      <img src="assets/DarkBar_512.png" width="200" alt="DarkBar icon">
    </td>
    <td valign="top">
      <h2>DarkBar</h2>
      <p>A small menu bar utility that fades your MacBook's Touch Bar to black, on demand
      or automatically when you go idle.</p>
      <p><b>Download:</b> grab the latest <code>.dmg</code> from the
      <a href="../../releases/latest">Releases page</a>.</p>
    </td>
  </tr>
</table>

## Features

- Disable the touch bar on-demand by using a shortcut (Opt+Cmd+T by default), or by clicking the menu bar item
- Auto-disabling after some time (from 10 seconds, to 10 minutes)
- Optional on-screen **esc** button, for 2016-2019 13" MacBook Pros, and all 15" MBP's that feature the Butterfly keyboard (off by default, since my machine is a 2020 model)
- Auto-open on login
- Show the app icon in dock

## Notes

- The app is unsigned, so you'll need to right (or ctrl+) click the app and select "Open"
- It uses private AppKit APIs, so a future macOS update could break it
- The optional esc button needs Accessibility permission
- I have not tested it on older macOS versions (Sierra - Monterey), as well as newer ones (Sonoma - Tahoe). Also, I have not tested it on any arm64e Macs, since my machine has an Intel CPU

## Building from source

```bash
python3 -m pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz pyinstaller
python3 -m PyInstaller --noconfirm --clean DarkBar.spec
```

## Credits

The Eye of Providence (part of the) icon made by [game-icons.net](https://game-icons.net/?ref=svgrepo.com) in CC Attribution License via [SVG Repo](https://www.svgrepo.com/)

## *AI USAGE NOTE:*
*The code for project was made with the use of AI, Claude to be specific. The icon, title, and almost all text/graphics/design in the app, as well as the text in this readme, were created by me.*
