# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Status reads `none`, "no WSL distribution installed" | `wsl --install -d Ubuntu`, then press **Check install**; no restart needed. |
| `tpx3dump` / `tpx4dump` not found under the Luna folder | Point at the install root or its `bin/`, not at the `.zip`. Check that **Detector** matches the Luna you pointed at. |
| UNC path rejected | Map `\\server\share` to a drive letter first. |
| Qt plugin `xcb` will not load (Linux) | `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1` |
| Launcher installed but not in the applications menu (Linux) | Work through [Linux step 4](installation.md#4-not-showing-up-in-the-applications-menu); start with `desktop-file-validate`. |
| Generic gear instead of the app icon in the dock (Linux) | The window must be matched to its `.desktop` entry. Install the launcher with `./install-linux.sh`: the app reports itself as `luna-gui-wrapper`, and without that file there is nothing to match. |
| Menu entry appears but clicking it does nothing (Linux) | PySide6 or `libxcb-cursor0` missing. Run `./run_gui.sh` in a terminal to see the real error. |
| Inspect tab inert | `pip install h5py numpy pandas matplotlib` |
| "No `/TDCEvents` in this file" | A Timepix4 file (no TDC), a file that predates `tpx3dump`'s TDC support, or a run that recorded no TDC at all. |
| "No TDC1Rising edges in this file" | That reference was never pulsed; the summary line lists which types the file does have. |
| Most rows report no TDC | They precede the first reference edge. Normal at the start of a run; the plot title and the write dialog both state how many. |
| `/ClustersTDC` already exists, refusing to replace | Something other than this GUI wrote that name. Rename or remove it yourself; the GUI will not overwrite what it did not write. |
| Thousands of `[ERROR] ... Packet is ignored` lines (Timepix4) | That is `tpx4dump`'s own output for dropped packets; the file is still written. The log shows the first 20 and counts the rest. |
| Batch is slow on Windows | `/mnt/d` goes through WSL's 9P bridge; copy raw data into the WSL filesystem for big jobs. |
| `index out of bounds: the len is 0`, after `Skipping file ...` | WSL cannot see the drive the data is on, which is normal for USB sticks and other removable disks. Answer **Yes** when the GUI offers to mount it, or see [Can WSL see your data?](installation.md#step-3-check-the-installation). |
| Files report `skipped - output exists` | That is the **Skip files whose output already exists** option. Tick **Overwrite** on the rows you want redone, or use the checkbox in that column's header to tick them all. |
| `H5Fcreate(): unable to create file`, row says *output name too long* | A file name may be at most 255 characters, and `{comment}` can bring a long `comment.txt` into it. Shorten the name template (drop `{comment}`, or use `{stem}`), then press **Rerun failed**. |

## Settings

`~/.luna_gui_wrapper.json` holds the Luna path and batch folders (per
detector), template, flags, TDC reference and theme. On Windows that is
`C:\Users\<you>\.luna_gui_wrapper.json`. Settings saved before the rename, in
`~/.luna_tpx3_gui_qt.json`, are read until the new file exists.
