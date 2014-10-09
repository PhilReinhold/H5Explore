from collections import defaultdict
from PyQt4 import QtGui, QtCore
from PyQt4.Qt import Qt
from PyQt4.QtGui import QCheckBox
import h5py
import sys
from pyqtgraph import ImageView
from pyqtgraph.dockarea import DockArea
from plot_widgets import CrosshairPlotWidget, CloseableDock, CrossSectionDock, MoviePlotDock, PropertyPlot
import numpy as np

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
        self.modelReset.emit()


def h5_dispatch(item):
    if isinstance(item, h5py.Group):
        return H5ItemName(item)
    else:
        return H5DatasetRow(item).columns


class H5Item(QtGui.QStandardItem):
    props_dict = defaultdict(lambda: [])
    def __init__(self, group, row=None, text=""):
        super(H5Item, self).__init__(str(text))
        self.group = group
        self.row = row
        self.fullname = group.name
        self.name = group.name.split('/')[-1]

        for k in group.attrs.keys():
            if k in ('DIMENSION_SCALE', 'DIMENSION_LIST', 'CLASS', 'NAME', 'REFERENCE_LIST'):
                # These are set by h5py for axis handling
                continue
            v = group.attrs[k]
            if isinstance(group, h5py.Dataset) and isinstance(v, (int, float)):
                self.props_dict[k].append(self)
            self.appendRow(H5AttrRow(k, group).columns)

        if isinstance(group, h5py.Group):
            for k in group.keys():
                items = h5_dispatch(group[k])
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
        self.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        expand_action = QtGui.QAction("Expand", self)
        expand_action.triggered.connect(self.expandAll)
        self.addAction(expand_action)

        collapse_action = QtGui.QAction("Collapse", self)
        collapse_action.triggered.connect(self.collapseAll)
        self.addAction(collapse_action)

    def selected_path(self):
        return self.model().itemFromIndex(self.selectedIndexes()[0]).fullname


class RecursiveFilterModel(QtGui.QSortFilterProxyModel):
    attrs_visible = True
    term_string = ""

    def setSourceModel(self, model):
        super(RecursiveFilterModel, self).setSourceModel(model)
        model.modelReset.connect(self.source_model_changed)

    def get_matches(self, t):
        items = self.sourceModel().findItems("", Qt.MatchContains | Qt.MatchRecursive)
        return [i for i in items if t in i.fullname]
        #return self.sourceModel().findItems(t, Qt.MatchContains | Qt.MatchRecursive)

    def toggle_attrs_visible(self):
        self.attrs_visible = not self.attrs_visible
        self.invalidateFilter()

    def source_model_changed(self):
        self.set_match_term(self.term_string)

    def set_match_term(self, term_string):
        # Match all words
        self.term_string = term_string
        matches = [set(self.get_matches(t)) for t in str(term_string).split()]
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
            if not self.attrs_visible and isinstance(this_item, H5AttrItem):
                return False
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
        self.attrs_visible_check = QCheckBox("Attributes Visible")
        self.attrs_visible_check.setChecked(True)
        self.tree_view = H5View()
        self.attrs_visible_check.toggled.connect(match_model.toggle_attrs_visible)
        self.tree_view.setModel(match_model)
        layout.addWidget(self.attrs_visible_check)
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

        file_notifier = QtCore.QFileSystemWatcher([file.filename])
        file_notifier.fileChanged.connect(lambda n: self.model.refresh)

        self.layout = QtGui.QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.layout)
        self.view.activated.connect(self.load_plot)
        self.layout.addWidget(view_box)
        self.layout.addWidget(self.dock_area)
        self.layout.setStretchFactor(0, 0)
        self.layout.setStretchFactor(1, 1)

        plot_menu = self.menuBar().addMenu('Plot')
        property_plot_action = QtGui.QAction('Plot Property', self.view)
        property_plot_action.triggered.connect(self.make_property_plot)
        #self.view.addAction(property_plot_action)
        plot_menu.addAction(property_plot_action)

        file_menu = self.menuBar().addMenu('File')
        refresh_action = QtGui.QAction('Refresh File Contents', self.view)
        refresh_action.triggered.connect(self.model.refresh)
        file_menu.addAction(refresh_action)


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

    def make_property_plot(self):
        self.property_error_msg = QtGui.QErrorMessage()
        try:
            indexes = filter(lambda i: i.column() == 0, self.view.selectedIndexes())
            selected1, selected2 = [self.model.itemFromIndex(self.match_model.mapToSource(i)) for i in indexes]
            assert isinstance(selected1, H5AttrKey)
            assert isinstance(selected2, H5AttrKey)
            name1 = str(selected1.text())
            name2 = str(selected2.text())
        except:
            raise
        #    self.property_error_msg.showMessage("Must select two distinct properties to plot")
        groups = set(H5Item.props_dict[name1] + H5Item.props_dict[name2])
        if not groups:
            self.property_error_msg.showMessage("No groups share properties '%s' and '%s'" % (name1, name2))
            return

        try:
            points = sorted([(float(g.group.attrs[name1]), float(g.group.attrs[name2])) for g in groups], key=lambda x: x[0])
        except ValueError:
            self.property_error_msg.showMessage("Cannot convert property to float") # todo: better message
        xpts, ypts = np.transpose(points)
        xsets = [g.group.dims[0][0][:] if g.group.dims[0] else None for g in groups]
        ysets = [g.group[:] for g in groups]
        items = {(x, y): (xset, yset) for x, y, xset, yset in zip(xpts, ypts, xsets, ysets)}
        self.dock_area.addDock(PropertyPlot(items, {'bottom':name1, 'left':name2}, self.dock_area))


    def load_plot(self, index):
        'given an index referring to an H5Dataset, puts a plot corresponding to that dataset in the plot area'
        source_index = self.match_model.mapToSource(index)
        item = self.model.itemFromIndex(source_index)
        if isinstance(item.row, H5DatasetRow) and item.row.plot is None:
            labels = []
            axes = []
            for d in item.group.dims:
                try:
                    label, ds = d.items()[0]
                    labels.append(label)
                    axes.append(ds[:])
                except IndexError:
                    print 'Could not find axis in item', item
                    labels.append('')
                    axes.append(None)

            dock = self.make_dock(item.name, item.group[:], labels, axes)
            self.dock_area.addDock(dock)
            item.plot = dock
            dock.closeClicked.connect(lambda: item.__setattr__('plot', None))

    def make_dock(self, name, array, labels=None, axes=None):
        'returns a dockable plot widget'
        labels = {pos: l for l, pos in zip(labels, ('bottom', 'left'))}
        if len(array.shape) == 3:
            d = MoviePlotDock(array, name=name, area=self.dock_area)

        if len(array.shape) == 2:
            d = CrossSectionDock(name=name, area=self.dock_area)
            d.setImage(array)

        if len(array.shape) == 1:
            w = CrosshairPlotWidget(labels=labels)
            if axes and axes[0] is not None:
                w.plot(axes[0], array)
            else:
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
    A = test_f.create_group('group A')
    B = test_f.create_group('group B')
    C = test_f.create_group('group C')
    D = test_f.create_group('Prop Group')
    B['Simple Data'] = range(25)
    xs, ys = np.mgrid[-25:25, -25:25]
    rs = np.sqrt(xs ** 2 + ys ** 2)
    C['Image Data'] = np.sinc(rs)
    C['R Values'] = rs
    A.attrs['words'] = 'bonobo bonanza'
    A.attrs['number'] = 42
    C['Image Data'].attrs['dataset attr'] = 15.5
    ts, xs, ys = np.mgrid[0:100, -50:50, -50:50]
    rs = np.sqrt(xs ** 2 + ys ** 2)
    C['Movie Data'] = np.sinc(rs - ts) * np.exp(-ts / 100)

    xs = A['xs'] = np.linspace(0, 10, 300)
    A['sin(xs)'] = np.sin(xs)
    A['sin(xs)'].dims.create_scale(A['xs'], "The X Axis Label")
    A['sin(xs)'].dims[0].attach_scale(A['xs'])
    A['sin(xs)'].attrs['prop x'] = 3
    A['sin(xs)'].attrs['prop y'] = 7

    B['Simple Data'].attrs['prop x'] = 2
    B['Simple Data'].attrs['prop y'] = 4
    for i, x in enumerate(range(15)):
        data = np.random.normal(0, 1, 25)
        D['dset %s' % i] = data
        D['dset %s' % i].attrs['id'] = i
        D['dset %s' % i].attrs['avg'] = np.mean(data)

    main(test_fn)


if __name__ == "__main__":
    #main(r'C:\_Data\test.h5')
    import sys

    try:
        main(sys.argv[1])
    except IndexError:
        test()



