from PyQt4 import QtGui, QtCore
from PyQt4.Qt import Qt
import h5py
import sys
from pyqtgraph import ImageView
from pyqtgraph.dockarea import DockArea
from plot_widgets import CrosshairPlotWidget, CloseableDock, CrossSectionDock, MoviePlotDock

from scipy.stats import futil
from scipy.sparse.csgraph import _validation


class H5File(QtGui.QStandardItemModel):
    def __init__(self, file=None):
        super(H5File, self).__init__()
        if file is not None:
            self.set_file(file)

    def set_file(self, file):
        self.file = file
        self.clear()
        self.setColumnCount(2)
        for k in file.keys():
            item = h5_dispatch(file[k])
            self.invisibleRootItem().appendRow(item)

    def refresh(self):
        filename = self.file.filename
        self.file.close()
        self.set_file(h5py.File(filename))

def h5_dispatch(item):
    if isinstance(item, h5py.Group):
        return H5ItemName(item)
    else:
        return H5DatasetRow(item).columns

class H5Item(QtGui.QStandardItem):
    def __init__(self, group, row=None, text=""):
        super(H5Item, self).__init__(str(text))
        self.group = group
        self.row = row
        self.fullname = group.name
        self.name = group.name.split('/')[-1]

        for k in group.attrs.keys():
            self.appendRow(H5AttrRow(k, group).columns)

        if isinstance(group, h5py.Group):
            for k in group.keys():
                items = h5_dispatch(group[k])
                try:
                    print [(i.name, i.text()) for i in items]
                except:
                    print i.name, i.text()
                self.appendRow(items)

    def data(self, role):
        if role == Qt.BackgroundRole and self.row and self.row.plot is not None:
            return QtGui.QBrush(QtGui.QColor(255, 0, 0, 127))
        else:
            return super(H5Item, self).data(role)


class H5ItemName(H5Item):
    def __init__(self, group, row=None):
        #name = group.name.split('/')[-1]
        super(H5ItemName, self).__init__(group, row)
        self.setText(str(self.name))

    def setData(self, value, role):
        if role != Qt.EditRole:
            return super(H5ItemName, self).setData(value, role)
        v = value.toString()
        if v:
            self.set_name(v)

    def set_name(self, name):
        name = str(name)
        if name == self.name:
            return
        if self.parent() is None:
            parent_group = self.group.file
        else:
            parent_group = self.parent().group
        parent_group[name] = self.group
        self.group = parent_group[name]
        del parent_group[self.name]
        self.name = name
        self.setText(name)
        self.emitDataChanged()

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

class H5DatasetRow(object):
    def __init__(self, dataset):
        self.name = H5ItemName(dataset, self)
        self.shape = H5Item(dataset, self, text=str(dataset.shape))
        self.shape.setEditable(False)
        self.plot = None
        self.columns = [self.name, self.shape]

class H5AttrItem(QtGui.QStandardItem):
    def __init__(self, key, group, row, text=""):
        super(H5AttrItem, self).__init__(text)
        self.key = key
        self.row = row
        self.value = str(group.attrs[key])
        self.fullname = group.name + '/' + key
        self.name = key

    def data(self, role):
        if role == Qt.BackgroundRole:
            return QtGui.QBrush(QtGui.QColor(0xed, 0xe6, 0xa4, 127))
        else:
            return super(H5AttrItem, self).data(role)

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

class H5AttrKey(H5AttrItem):
    def __init__(self, key, group, row):
        super(H5AttrKey, self).__init__(key, group, row, text=str(key))

    def setData(self, value, role):
        if role != Qt.EditRole:
            return super(H5AttrKey, self).setData(value, role)
        attr_val = self.group.attrs[self.key]
        del self.group.attrs[self.key]
        self.key = str(value.toString())
        self.group.attrs[self.key] = attr_val

class H5AttrValue(H5AttrItem):
    def __init__(self, key, group, row):
        #value = str(group.attrs[key])
        super(H5AttrValue, self).__init__(key, group, row)
        self.setText(self.value)

    def setData(self, value, role):
        if role != Qt.EditRole:
            return super(H5AttrValue, self).setData(value, role)
        if value.canConvert(int):
            v = value.toInt()
        elif value.canConvert(float):
            v = value.toFloat()
        else:
            v = str(value.toString())
        self.group.attrs[self.key] = v

class H5AttrRow(object):
    def __init__(self, key, dataset):
        self.name = H5AttrKey(key, dataset, self)
        self.value = H5AttrValue(key, dataset, self)
        self.columns = [self.name, self.value]

class H5View(QtGui.QTreeView):
    def __init__(self):
        super(H5View, self).__init__()
        self.resizeColumnToContents(0)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        expand_action = QtGui.QAction("Expand", self)
        expand_action.triggered.connect(self.expandAll)
        expand_action.triggered.connect(lambda: self.resizeColumnToContents(0))
        self.addAction(expand_action)

        collapse_action = QtGui.QAction("Collapse", self)
        collapse_action.triggered.connect(self.collapseAll)
        collapse_action.triggered.connect(lambda: self.resizeColumnToContents(0))
        self.addAction(collapse_action)

        self.contextMenuPolicy()


class RecursiveFilterModel(QtGui.QSortFilterProxyModel):
    def get_matches(self, t):
        items = self.sourceModel().findItems("", Qt.MatchContains | Qt.MatchRecursive)
        return [i for i in items if t in i.fullname]
        #return self.sourceModel().findItems(t, Qt.MatchContains | Qt.MatchRecursive)

    def set_match_term(self, term_string):
        # Match all words
        matches = [ set(self.get_matches(t)) for t in str(term_string).split() ]
        m0 = set(self.get_matches(""))
        self.matching_items = m0.intersection(*matches)

        # Get Children of matched groups
        #old_matches = None
        #while self.matching_items != old_matches:
        #    old_matches = self.matching_items
        #    self.matching_items = self.matching_items.union(*[set(i.children()) for i in self.matching_items])

        # Get Parents
        old_matches = None
        root = self.sourceModel().invisibleRootItem()
        while self.matching_items != old_matches:
            old_matches = self.matching_items
            self.matching_items = self.matching_items.union({i.parent() for i in self.matching_items})
            self.matching_items = self.matching_items.difference({None, root})
        self.invalidateFilter()

    def filterAcceptsRow(self, src_i, src_parent_index):
        this_parent = self.sourceModel().itemFromIndex(src_parent_index)
        if this_parent:
            this_item = this_parent.child(src_i)
        else:
            this_index = self.sourceModel().index(src_i, 0)
            this_item = self.sourceModel().itemFromIndex(this_index)
        return this_item in self.matching_items

class SearchableH5View(QtGui.QWidget):
    def __init__(self, model):
        super(SearchableH5View, self).__init__()
        layout = QtGui.QVBoxLayout(self)
        match_model = RecursiveFilterModel()
        match_model.setSourceModel(model)
        match_model.set_match_term("")
        self.tree_view = H5View()
        self.tree_view.setModel(match_model)
        layout.addWidget(self.tree_view)
        self.search_box = QtGui.QLineEdit()
        layout.addWidget(self.search_box)
        self.search_box.textChanged.connect(match_model.set_match_term)

class H5Plotter(QtGui.QMainWindow):
    def __init__(self, file):
        super(H5Plotter, self).__init__()
        view_box = SearchableH5View(H5File(file))
        self.view = view_box.tree_view
        self.match_model = self.view.model()
        self.model = self.match_model.sourceModel()
        self.dock_area = DockArea()

        self.layout = QtGui.QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.layout)
        self.view.activated.connect(self.load_plot)
        self.layout.addWidget(view_box)
        self.layout.addWidget(self.dock_area)
        self.layout.setStretchFactor(0, 0)
        self.layout.setStretchFactor(1, 1)

        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_N), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveDown))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_P), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveUp))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_F), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveRight))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_B), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveLeft))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_S), self, view_box.search_box.setFocus)

    def move_view_cursor(self, cursor_action):
        self.view.setFocus(Qt.OtherFocusReason)
        self.view.setCurrentIndex(self.view.moveCursor(cursor_action, Qt.NoModifier))


    def load_plot(self, index):
        'given an index referring to an H5Dataset, puts a plot corresponding to that dataset in the plot area'
        source_index = self.match_model.mapToSource(index)
        item = self.model.itemFromIndex(source_index)
        if isinstance(item.row, H5DatasetRow) and item.row.plot is None:
            dock = self.make_dock(item.name, item.group[:])
            self.dock_area.addDock(dock)
            item.plot = dock
            dock.closeClicked.connect(lambda: item.__setattr__('plot', None))

    def make_dock(self, name, array):
        'returns a dockable plot widget'
        if len(array.shape) == 3:
            d = MoviePlotDock(array, name=name, area=self.dock_area)

        if len(array.shape) == 2:
            d = CrossSectionDock(name=name, area=self.dock_area)
            d.setImage(array)

        if len(array.shape) == 1:
            w = CrosshairPlotWidget()
            w.plot(array)
            d = CloseableDock(name=name, widget=w, area=self.dock_area)


        return d

def main(fn):
    with h5py.File(fn) as f:
        app = QtGui.QApplication([])
        win = H5Plotter(f)
        win.setWindowTitle(fn)
        win.show()
        win.view.expandAll()
        app.exec_()
    sys.exit()

def test():
    import numpy as np
    test_fn = "test.h5"
    test_f = h5py.File(test_fn, 'w')
#    app = QtGui.QApplication([])
#    win = H5Plotter(test_f)
#    QtGui.QMessageBox.warning(win, "No File Specified", "No file specified, Creating test file instead.")
    A = test_f.create_group('group A')
    B = test_f.create_group('group B')
    C = test_f.create_group('group C')
    B['Simple Data'] = range(25)
    xs, ys = np.mgrid[-25:25, -25:25]
    rs = np.sqrt(xs**2 + ys**2)
    C['Image Data'] = np.sinc(rs)
    C['R Values'] = rs
    A.attrs['words'] = 'bonobo bonanza'
    A.attrs['number'] = 42
    C['Image Data'].attrs['dataset attr'] = 15.5
    ts, xs, ys = np.mgrid[0:100, -50:50, -50:50]
    rs = np.sqrt(xs**2 + ys**2)
    C['Movie Data'] = np.sinc(rs-ts) * np.exp(-ts/100)

    main(test_fn)

if __name__ == "__main__":
    import sys
    try:
        main(sys.argv[1])
    except IndexError:
        test()



