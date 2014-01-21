from PyQt4 import QtGui, QtCore
from PyQt4.Qt import Qt
import h5py
import sys
from pyqtgraph import ImageView, PlotWidget, PlotItem
from pyqtgraph.dockarea import DockArea, Dock


class H5Model(QtGui.QStandardItemModel):
    def __init__(self, file=None):
        super(H5Model, self).__init__()
        self.root = self.invisibleRootItem()
        self.setColumnCount(2)
        if file is not None:
            self.add_file(file)

    def add_file(self, file):
        self.root.appendRow(H5Group(file))

    def data(self, index, role):
        row_index = self.index(index.row(), 0, index.parent())
        item = self.itemFromIndex(row_index)
        if isinstance(item, H5Item):
            return item.column_data(index.column(), role)
        else:
            return super(H5Model, self).data(index, role)


    def flags(self, index):
        f = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() == 0:
            f |= Qt.ItemIsEditable
        return f

class H5Item(QtGui.QStandardItem):
    def __init__(self, group_or_ds):
        super(H5Item, self).__init__()
        self.group_or_ds = group_or_ds
        self.name = group_or_ds.name
        self.text = group_or_ds.name.split('/')[-1]
        self.setColumnCount(2)
        if not self.text:
            self.text = group_or_ds.filename

    def setData(self, value, role):
        if role == Qt.EditRole:
            parent_group = self.parent().group
            v = str(value.toString())
            if not v:
                return False
            parent_group[v] = self.group_or_ds
            self.group_or_ds = parent_group[v]
            del parent_group[self.text]
            self.name = self.group_or_ds.name
            self.text = v
            self.emitDataChanged()
            return True
        return False

class H5Group(H5Item):
    def __init__(self, group):
        super(H5Group, self).__init__(group)
        for k in group.keys():
            child = group[k]
            if isinstance(child, h5py.Group):
                self.appendRow(H5Group(child))
            else:
                self.appendRow(H5Dataset(child))

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
    def __init__(self, model):
        super(H5View, self).__init__()
        self.setModel(model)

    def add_file(self, file):
        self.model().add_file(file)
        self.expandAll()
        self.resizeColumnToContents(0)

class H5Plotter(QtGui.QWidget):
    def __init__(self):
        super(H5Plotter, self).__init__()
        layout = QtGui.QHBoxLayout(self)
        self.model = H5Model()
        self.view = H5View(self.model)
        self.view.setModel(self.model)
        self.dock_area = DockArea()

        self.view.clicked.connect(self.load_plot)
        layout.addWidget(self.view)
        layout.addWidget(self.dock_area)

    def load_plot(self, index):
        'given an index referring to an H5Dataset, puts a plot corresponding to that dataset in the plot area'
        item = self.model.itemFromIndex(index)
        if isinstance(item, H5Dataset):
            plot = self.add_plot(item.name, item.dataset[:])
            item.plot = plot
            plot.closeClicked.connect(lambda: item.__setattr__('plot', None))

    def add_plot(self, name, array):
        'given an array, puts a plot with that array in the plot area, and returns the dock'
        w = self.make_plot(array)
        d = CloseableDock(name=name, widget=w, area=self.dock_area)
        self.dock_area.addDock(d)
        return d

    def make_plot(self, array):
        'returns a plot widget'
        if len(array.shape) == 2:
            w = ImageView()
            w.setImage(array)
            return w

        if len(array.shape) == 1:
            w = PlotWidget()
            w.plot(array)
            return w

class CloseableDock(Dock):
    def __init__(self, *args, **kwargs):
        super(CloseableDock, self).__init__(*args, **kwargs)
        style = QtGui.QStyleFactory().create("windows")
        icon = style.standardIcon(QtGui.QStyle.SP_TitleBarCloseButton)
        button = QtGui.QPushButton(icon, "", self)
        button.clicked.connect(self.close)
        button.setGeometry(0, 0, 20, 20)
        button.raise_()
        self.closeClicked = button.clicked
        self.closed = False

    def close(self):
        self.setParent(None)
        self.label.setParent(None)
        self.closed = True

test_fn = "test.h5"
test_f = h5py.File(test_fn, 'w')
A = test_f.create_group('group A')
B = test_f.create_group('group B')
C = test_f.create_group('group C')
B['Simple Data'] = range(25)

app = QtGui.QApplication([])
win = H5Plotter()
win.view.add_file(test_f)
win.show()
sys.exit(app.exec_())





