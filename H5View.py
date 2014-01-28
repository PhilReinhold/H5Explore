from PyQt4 import QtGui, QtCore
from PyQt4.Qt import Qt
import h5py
import sys
from pyqtgraph.dockarea import DockArea
from plot_widgets import CrosshairPlotWidget, CloseableDock, CrossSectionDock

from scipy.stats import futil
from scipy.sparse.csgraph import _validation


class H5File(QtGui.QStandardItemModel):
    def __init__(self, file=None):
        super(H5File, self).__init__()
        if file is not None:
            self.set_file(file)
        #if not isinstance(self, H5FileSearchResult):
        #    self.match_model = H5FileSearchResult()

    def set_file(self, file):
        self.file = file
        self.clear()
        self.setColumnCount(2)
        for k in file.keys():
            item = h5_dispatch(file[k])
            self.invisibleRootItem().appendRow(item)

    def row_index(self, index):
        return self.index(index.row(), 0, index.parent())

    def data(self, index, role):
        item = self.itemFromIndex(self.row_index(index))
        if isinstance(item, H5Item):
            return item.column_data(index.column(), role)
        else:
            return super(H5File, self).data(index, role)

    def flags(self, index):
        f = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() == 0:
            f |= Qt.ItemIsEditable
        return f

    def refresh(self):
        filename = self.file.filename
        self.file.close()
        self.set_file(h5py.File(filename))


class H5Item(QtGui.QStandardItem):
    def __init__(self, group_or_ds):
        super(H5Item, self).__init__()
        self.group_or_ds = group_or_ds
        self.name = group_or_ds.name
        self.text = group_or_ds.name.split('/')[-1]
        self.setColumnCount(2)
        if not self.text:
            self.text = group_or_ds.filename

    def clone_matching(self, term):
        items = self.model().findItems(term, Qt.MatchContains | Qt.MatchRecursive)

        new = type(self)(self.group_or_ds)
        if self.parent() is not None:
            p = self.parent().clone()
            p.setChild()
        new.setChild

    def setData(self, value, role):
        if role == Qt.EditRole:
            if self.parent() is None:
                parent_group = self.group_or_ds.file
            else:
                parent_group = self.parent().group
            v = str(value.toString())
            if not v:
                return
            parent_group[v] = self.group_or_ds
            self.group_or_ds = parent_group[v]
            del parent_group[self.text]
            self.name = self.group_or_ds.name
            self.text = v
            self.emitDataChanged()

    def children(self):
        return [self.child(i) for i in range(self.rowCount())]

def h5_dispatch(item):
    if isinstance(item, h5py.Group):
        item = H5Group(item)
        return item
    else:
        return H5Dataset(item)


class H5Group(H5Item):
    def __init__(self, group):
        super(H5Group, self).__init__(group)
        for k in group.keys():
            child = group[k]
            self.appendRow(h5_dispatch(child))

    def column_data(self, column, role):
        if role == Qt.DisplayRole and column < 1:
            return self.text

    @property
    def group(self):
        return self.group_or_ds

class H5Dataset(H5Item):
    def __init__(self, dataset):
        super(H5Dataset, self).__init__(dataset)
        self.ds_shape = str(self.dataset.shape)
        self.plot = None

    @property
    def dataset(self):
        return self.group_or_ds

    def column_data(self, column, role):
        if role == Qt.BackgroundRole and self.plot is not None:
            return QtGui.QBrush(QtGui.QColor(255, 0, 0, 127))
        elif role == Qt.DisplayRole:
            return [self.text, self.ds_shape][column]


class H5View(QtGui.QTreeView):
    def __init__(self):
        super(H5View, self).__init__()
        self.resizeColumnToContents(0)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        expand_action = QtGui.QAction("Expand", self)
        expand_action.triggered.connect(self.expandAll)
        self.addAction(expand_action)

        collapse_action = QtGui.QAction("Collapse", self)
        collapse_action.triggered.connect(self.collapseAll)
        self.addAction(collapse_action)

        self.contextMenuPolicy()


class RecursiveFilterModel(QtGui.QSortFilterProxyModel):
    def get_matches(self, t):
        items = self.sourceModel().findItems("", Qt.MatchContains | Qt.MatchRecursive)
        return [i for i in items if t in i.group_or_ds.name]
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
        search_box = QtGui.QLineEdit()
        layout.addWidget(self.tree_view)
        layout.addWidget(search_box)
        search_box.textChanged.connect(match_model.set_match_term)

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


    def load_plot(self, index):
        'given an index referring to an H5Dataset, puts a plot corresponding to that dataset in the plot area'
        source_index = self.match_model.mapToSource(index)
        item = self.model.itemFromIndex(self.model.row_index(source_index))
        if isinstance(item, H5Dataset) and item.plot is None:
            dock = self.make_dock(item.name, item.dataset[:])
            self.dock_area.addDock(dock)
            item.plot = dock
            dock.closeClicked.connect(lambda: item.__setattr__('plot', None))

    def make_dock(self, name, array):
        'returns a dockable plot widget'
        if len(array.shape) == 2:
            d = CrossSectionDock(name=name, area=self.dock_area)
            d.setImage(array)

        if len(array.shape) == 1:
            w = CrosshairPlotWidget()
            w.plot(array)
            d = CloseableDock(name=name, widget=w, area=self.dock_area)

        return d

def main(fn):
    f = h5py.File(fn)
    app = QtGui.QApplication([])
    app.lastWindowClosed.connect(f.close)
    win = H5Plotter(f)
    win.setWindowTitle(fn)
    win.show()
    sys.exit(app.exec_())


def test():
    import numpy as np
    test_fn = "test.h5"
    test_f = h5py.File(test_fn, 'w')
    app = QtGui.QApplication([])
    win = H5Plotter(test_f)
    QtGui.QMessageBox.warning(win, "No File Specified", "No file specified, Creating test file instead.")
    A = test_f.create_group('group A')
    B = test_f.create_group('group B')
    C = test_f.create_group('group C')
    B['Simple Data'] = range(25)
    xs, ys = np.mgrid[-25:25, -25:25]
    rs = np.sqrt(xs**2 + ys**2)
    C['Image Data'] = np.sinc(rs)
    C['R Values'] = rs
    main(test_fn)

if __name__ == "__main__":
    import sys
    try:
        main(sys.argv[1])
    except IndexError:
        test()



