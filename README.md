H5Explore
=========

An HDF5 dataset plotting tool, with fewer dependencies

![](https://raw.github.com/PhilReinhold/H5Explore/master/screenshot.png)

On Windows, compile to executable with `python setup.py py2exe`, use resulting `dist\H5View.exe` to open `*.h5` files

To use, either associate the executable with the filetype, or somehow run `python H5View.py <filename>`

Once you've opened a file

- Double click on dataset to open as a plot
- Type into the bar below the tree navigator to filter the tree structure
- Double click on plots to activate crosshairs
- Right click tree to toggle tree expand state
