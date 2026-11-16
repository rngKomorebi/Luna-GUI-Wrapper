# License

Luna GUI Wrapper is released under the MIT License. This covers the GUI only;
ASI Luna is licensed separately by its vendor.

## Licence note

This program is a wrapper only. It does not contain, modify, decompile or
redistribute any part of Luna. It runs the unmodified `tpx3dump` / `tpx4dump`
executables as subprocesses through their documented command-line interface,
and you point it at your own Luna installation.

For the same reason there is **no bundled executable** (no PyInstaller `.exe`,
no AppImage, no release downloads) on any platform. A self-contained bundle
makes it too easy to pass the GUI on with the Luna binaries packed inside it,
which would break Luna's licence. The GUI runs from source, through the
launchers and shortcuts described in [Installation](installation.md). **Do not
bundle the Luna binaries with this GUI if you pass it on.**

## MIT License

```{include} ../LICENSE
```
