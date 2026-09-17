# Local route metadata

`index.csv` records the current training/validation/test assignment. The
actual route directories remain in `/home/caleb/openpilot/route-data` and are
not stored in this repository. The original symbolic-link tree is
`/home/caleb/openpilot/route-data-splits`.

`drive_metadata.csv` records per-drive labels and observations. The latest
drive is labeled `best guess v1` and assigned to training; its raw route data
is still kept outside this Git repository.
