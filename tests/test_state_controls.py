"""Native State binding regressions; run with unittest (GUI required)."""
import contextlib
import io
import unittest
from PySide6 import QtCore, QtWidgets
from PUI.dom import recur_delete
from labelate.app import Labelate


class StateControlsTests(unittest.TestCase):
    def test_startup_and_editable_data(self):
        app = Labelate()
        if QtWidgets.QApplication.instance():
            app.ui = QtWidgets.QApplication.instance()
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                app.sync()
                app.add('text')
                app.current()['content'] = 'Hello {name}'
                app.add_data_row()
                app.state('active_tab').value = 'Data'
                app.state('copies').value = '3'
                app.sync()
                def walk(node):
                    yield node
                    for child in node.children:
                        yield from walk(child)
                table = next(n for n in walk(app) if n._id == 'data-table')
                model = table.ui.model()
                self.assertEqual(model.columnCount(QtCore.QModelIndex()), 1)
                self.assertEqual(model.headerData(0, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole), 'name')
                index = model.index(0, 0)
                self.assertTrue(model.flags(index) & QtCore.Qt.ItemIsEditable)
                self.assertTrue(model.setData(index, 'Alice', QtCore.Qt.EditRole))
                self.assertEqual(app.snapshot()['data_rows'][0]['name'], 'Alice')
                app.inputs('label:mode').value = 'Color'
                app.sync()
                self.assertEqual(app.template['canvas']['mode'], 'color')
                self.assertEqual(app.inputs['label:mode'], 'Color')
                self.assertEqual(app.state.copies, '3')
                app.add_data_row()
                first, second = app.template['data_rows']
                app.select_data_row(None, id(first))
                app.remove_data_row()
                self.assertIs(app.template['data_rows'][0], second)
                self.assertIsNone(app.state.selected_data_row)
                app.remove_data_row()
                self.assertEqual(len(app.template['data_rows']), 1)
                app.sync()
                style = next(n for n in walk(app) if n._id == 'font_style')
                self.assertEqual(style.ui.itemText(0), 'Normal')
                style.ui.setCurrentIndex(1)
                self.assertEqual(app.current()['font_style'], 'italic')
            self.assertNotIn('Traceback', output.getvalue())
            self.assertNotIn('<ERROR', output.getvalue())
        finally:
            qtapp = QtWidgets.QApplication.instance()
            recur_delete(app, app, True)
            if qtapp:
                qtapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
