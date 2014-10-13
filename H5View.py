import logging
import os
from PyQt4 import QtGui
from PyQt4.Qt import Qt
import h5py
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
        self.marked_junk = False

        for k in group.attrs.keys():
            if k in ('DIMENSION_SCALE', 'DIMENSION_LIST', 'CLASS', 'NAME', 'REFERENCE_LIST'):
                # These are set by h5py for axis handling
                continue
            if k == "__JUNK__":
                self.marked_junk = group.attrs[k]
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

    def is_junk(self):
        p = self.parent()
        if p is None:
            return self.marked_junk
        return self.marked_junk or p.is_junk()


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

    def is_junk(self):
        return self.parent().is_junk()


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
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QtGui.QAbstractItemView.EditKeyPressed)
        expand_action = QtGui.QAction("Expand All", self)
        expand_action.triggered.connect(self.expandAll)
        self.addAction(expand_action)

        collapse_action = QtGui.QAction("Collapse All", self)
        collapse_action.triggered.connect(self.collapseAll)
        self.addAction(collapse_action)

        self.mark_junk_action = QtGui.QAction("Mark Junk", self)
        self.mark_junk_action.triggered.connect(self.mark_node_junk)
        self.addAction(self.mark_junk_action)

        self.attach_axis_scale_action = QtGui.QAction("Attach Axis Scale", self)
        self.attach_axis_scale_action.triggered.connect(self.attach_axis)
        self.addAction(self.attach_axis_scale_action)

    def selectionChanged(self, new_selection, old_selection):
        super(H5View, self).selectionChanged(new_selection, old_selection)
        self.set_valid_context_menu_actions()

    def selected_items(self):
        return [self.model().itemFromIndex(i) for i in self.selectedIndexes() if i.column() == 0]

    def mark_node_junk(self):
        for i in self.selected_items():
            i.group.attrs["__JUNK__"] = True
            i.marked_junk = True
        self.model().invalidateFilter()

    def set_valid_context_menu_actions(self):
        items = self.selected_items()
        print items
        self.mark_junk_action.setEnabled(False)
        self.attach_axis_scale_action.setEnabled(False)
        if not items:
            return
        self.mark_junk_action.setEnabled(True)
        if len(items) == 1 and isinstance(items[0].group, h5py.Dataset):
            self.attach_axis_scale_action.setEnabled(True)

    def attach_axis(self):
        i = self.selected_items()[0]
        # Create widget to select x axis
        m = AxisSelectionModel(self.model().sourceModel(), i)
        w = QtGui.QTreeView()
        w.setModel(m)
        w.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        dialog = QtGui.QDialog()
        button_box = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok |
            QtGui.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout = QtGui.QVBoxLayout(dialog)
        layout.addWidget(QtGui.QLabel("Choose X Axis for Dataset {}".format(i.fullname)))
        layout.addWidget(w)
        layout.addWidget(button_box)
        if dialog.exec_():
            indices = w.selectedIndexes()
            if not indices:
                print 'Nothing selected'
                return

            axis_item = m.itemFromIndex(indices[0])
            if not isinstance(axis_item.group, h5py.Dataset):
                print 'Non-Dataset selected'
                return

            i.group.dims.create_scale(axis_item.group, axis_item.name)
            i.group.dims[0].attach_scale(axis_item.group)
            print 'Successfully attached'

class TreeFilterModel(QtGui.QSortFilterProxyModel):
    def __init__(self, **kwargs):
        super(TreeFilterModel, self).__init__(**kwargs)
        self.matching_items = []

    def itemFromIndex(self, idx):
        return self.sourceModel().itemFromIndex(self.mapToSource(idx))

    def set_matches(self, matches):
        matches = set(matches)
        old_matches = None
        root = self.sourceModel().invisibleRootItem()
        while matches != old_matches:
            old_matches = matches
            matches = matches.union({i.parent() for i in old_matches})
            matches = matches.difference({None, root})
        self.matching_items = matches
        self.invalidateFilter()

    def filterAcceptsRow(self, src_i, src_parent_index):
        this_parent = self.sourceModel().itemFromIndex(src_parent_index)
        if this_parent:
            this_item = this_parent.child(src_i)
        else:
            this_index = self.sourceModel().index(src_i, 0)
            this_item = self.sourceModel().itemFromIndex(this_index)
        return self.filter_accepts_item(this_item)

    def filter_accepts_item(self, item):
        return item in self.matching_items


class RecursiveFilterModel(TreeFilterModel):
    attrs_visible = False
    junk_visible = False
    term_string = ""

    def setSourceModel(self, model):
        super(RecursiveFilterModel, self).setSourceModel(model)
        model.modelReset.connect(self.source_model_changed)

    def get_matches(self, t):
        items = self.sourceModel().findItems("", Qt.MatchContains | Qt.MatchRecursive)
        x = [i for i in items if t in i.fullname]
        return x
        #return [i for i in items if t in i.fullname]
        #return self.sourceModel().findItems(t, Qt.MatchContains | Qt.MatchRecursive)

    def toggle_attrs_visible(self, checked):
        self.attrs_visible = checked
        self.invalidateFilter()

    def toggle_junk_visible(self, checked):
        self.junk_visible = checked
        self.invalidateFilter()

    def source_model_changed(self):
        self.set_match_term(self.term_string)

    def set_match_term(self, term_string):
        # Match all words
        self.term_string = term_string
        matches = [set(self.get_matches(t)) for t in str(term_string).split()]
        m0 = set(self.get_matches(""))
        self.set_matches(m0.intersection(*matches))

    def filter_accepts_item(self, item):
        if not self.attrs_visible and isinstance(item, H5AttrItem):
            return False
        if not self.junk_visible and item.is_junk():
            return False
        return super(RecursiveFilterModel, self).filter_accepts_item(item)

class AxisSelectionModel(TreeFilterModel):
    def __init__(self, source_model, source):
        super(AxisSelectionModel, self).__init__()
        self.setSourceModel(source_model)
        items = self.sourceModel().findItems("", Qt.MatchContains | Qt.MatchRecursive)
        groups = [i for i in items if isinstance(i, H5Item) and i is not source]
        datasets = [i for i in groups if isinstance(i.group, h5py.Dataset)]
        self.set_matches([i for i in datasets if i.group.shape == source.group.shape])



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

        self.setWindowIcon(QtGui.QIcon("icon.ico"))

        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_N), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveDown))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_P), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveUp))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_F), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveRight))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_B), self,
                        lambda: self.move_view_cursor(QtGui.QAbstractItemView.MoveLeft))
        QtGui.QShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_S), self, view_box.search_box.setFocus)

        view_menu = self.menuBar().addMenu("View")

        toggle_attrs_action = QtGui.QAction("Attributes Visible", view_menu)
        toggle_attrs_action.setCheckable(True)
        toggle_attrs_action.triggered.connect(self.match_model.toggle_attrs_visible)
        view_menu.addAction(toggle_attrs_action)

        toggle_junk_action = QtGui.QAction("Junk Visible", view_menu)
        toggle_junk_action.setCheckable(True)
        toggle_junk_action.triggered.connect(self.match_model.toggle_junk_visible)
        view_menu.addAction(toggle_junk_action)

    def move_view_cursor(self, cursor_action):
        self.view.setFocus(Qt.OtherFocusReason)
        self.view.setCurrentIndex(self.view.moveCursor(cursor_action, Qt.NoModifier))


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
                except RuntimeError:
                    print 'Mac bug? Probably no axis available'

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
    if os.name == 'nt':
        try:
            import ctypes
            myappid = 'philreinhold.h5view'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except ImportError:
            logging.warn("ctypes not found, appid not set")


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
    #A['sin(xs)'].dims.create_scale(A['xs'], "The X Axis Label")
    #A['sin(xs)'].dims[0].attach_scale(A['xs'])
    main(test_fn)


if __name__ == "__main__":
    import sys

    try:
        main(sys.argv[1])
    except IndexError:
        test()



