from distutils.core import setup
import py2exe
import scipy.stats

setup(
    windows=[{"script": "H5View.py", "icon_resources": [(1, "icon.ico")]}],
    data_files=[
        ('imageformats', [
            r'C:\Python27\Lib\site-packages\PyQt4\plugins\imageformats\qico4.dll'
        ]),
        ('', ['icon.ico'])],
    options={
        "py2exe":
            { "includes":["h5py.defs", "h5py.utils", "h5py._proxy", "h5py.h5ac", "scipy.sparse.csgraph._validation"],
              "dll_excludes":["MSVCP90.dll", "libzmq.pyd"]  }
    }
)