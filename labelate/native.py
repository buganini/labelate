"""Small Qt adapters for operations without a QPUIQ 1.8 public API.

All editor layout, controls, drawing and pointer events live in PUI. Only the
window-close veto and native color dialog need Qt here.
"""
from PySide6 import QtCore, QtGui, QtWidgets


class CloseGuard(QtCore.QObject):
    def __init__(self, editor):
        super().__init__(editor.ui)
        self.editor = editor

    def eventFilter(self, watched, event):
        if (event.type() == QtCore.QEvent.Type.Close and
                isinstance(watched, QtWidgets.QMainWindow)):
            if not self.editor.confirm_discard():
                event.ignore()
                return True
        return super().eventFilter(watched, event)


def choose_color(current):
    color = QtWidgets.QColorDialog.getColor(QtGui.QColor(current))
    return color.name() if color.isValid() else None
