from distutils.core import setup
import py2exe
import scipy.stats

setup(
    console=['H5View.py'],
    options={
        "py2exe":
            { "includes":["h5py.defs", "h5py.utils", "h5py._proxy", "scipy.sparse.csgraph._validation"],
              "dll_excludes":["MSVCP90.dll"]  }
    }
)