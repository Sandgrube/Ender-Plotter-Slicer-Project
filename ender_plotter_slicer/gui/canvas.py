from __future__ import annotations

from math import ceil, floor

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView, QRubberBand

from ..document import DocumentObject, PlotterDocument
from ..geometry import Polyline


def _polyline_to_qpath(polyline: Polyline) -> QPainterPath:
    path = QPainterPath()
    if not polyline.points:
        return path
    first = polyline.points[0]
    path.moveTo(first.x, first.y)
    for point in polyline.points[1:]:
        path.lineTo(point.x, point.y)
    return path


def object_to_qpath(obj: DocumentObject) -> QPainterPath:
    path = QPainterPath()
    for polyline in obj.local_polylines:
        path.addPath(_polyline_to_qpath(polyline))
    return path


class CanvasObjectItem(QGraphicsPathItem):
    def __init__(self, obj: DocumentObject, canvas: "CanvasView") -> None:
        super().__init__()
        self.object_id = obj.id
        self.canvas = canvas
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(obj.z_order)
        self.refresh_from_object(obj)

    def refresh_from_object(self, obj: DocumentObject) -> None:
        pen = QPen(QColor("#253858"), 0)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setPath(object_to_qpath(obj))
        self.setPos(obj.x_mm, obj.y_mm)
        transform = QTransform()
        transform.rotate(obj.rotation_deg)
        transform.scale(obj.scale_x, obj.scale_y)
        self.setTransform(transform)
        self.setVisible(obj.visible)
        self.setEnabled(not obj.locked)
        self.setZValue(obj.z_order)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.canvas.document.page.snap_enabled:
            point = value
            grid = max(0.1, self.canvas.document.page.grid_mm)
            snapped = QPointF(round(point.x() / grid) * grid, round(point.y() / grid) * grid)
            return snapped
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.canvas.emit_selection_changed_later()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.canvas.commit_item_position(self)

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.save()
            painter.setPen(QPen(QColor("#2a7fff"), 0, Qt.PenStyle.DashLine))
            painter.drawRect(self.boundingRect())
            painter.restore()


class CanvasScene(QGraphicsScene):
    pass


class CanvasView(QGraphicsView):
    coordinateChanged = Signal(float, float)
    selectionChangedDetailed = Signal(list)
    itemMoved = Signal(str, float, float)
    zoomChanged = Signal(float)

    def __init__(self, document: PlotterDocument, parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self._scene = CanvasScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._panning = False
        self._last_mouse_pos = QPoint()
        self._pending_selection_emit = False
        self.object_items: dict[str, CanvasObjectItem] = {}
        self._zoom_factor = 1.0
        self.rebuild_from_document()

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    def scene_page_rect(self) -> QRectF:
        margin = 50.0
        return QRectF(
            -margin,
            -margin,
            self.document.page.width_mm + 2 * margin,
            self.document.page.height_mm + 2 * margin,
        )

    def emit_selection_changed_later(self) -> None:
        if self._pending_selection_emit:
            return
        self._pending_selection_emit = True
        self.viewport().update()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._emit_selection_changed)

    def _emit_selection_changed(self) -> None:
        self._pending_selection_emit = False
        selected_ids = [item.object_id for item in self._scene.selectedItems() if isinstance(item, CanvasObjectItem)]
        self.selectionChangedDetailed.emit(selected_ids)

    def rebuild_from_document(self) -> None:
        self._scene.clear()
        self.object_items.clear()
        self._scene.setSceneRect(self.scene_page_rect())
        for obj in sorted(self.document.objects, key=lambda item: item.z_order):
            item = CanvasObjectItem(obj, self)
            self._scene.addItem(item)
            self.object_items[obj.id] = item
        self.apply_selection(self.document.selected_ids)
        self.viewport().update()

    def refresh_object(self, object_id: str) -> None:
        obj = self.document.object_by_id(object_id)
        item = self.object_items.get(object_id)
        if obj is None and item is not None:
            self._scene.removeItem(item)
            self.object_items.pop(object_id, None)
            return
        if obj is None:
            return
        if item is None:
            item = CanvasObjectItem(obj, self)
            self._scene.addItem(item)
            self.object_items[object_id] = item
            return
        item.refresh_from_object(obj)

    def commit_item_position(self, item: CanvasObjectItem) -> None:
        self.itemMoved.emit(item.object_id, item.pos().x(), item.pos().y())

    def apply_selection(self, object_ids: list[str]) -> None:
        lookup = set(object_ids)
        self._scene.blockSignals(True)
        try:
            for object_id, item in self.object_items.items():
                item.setSelected(object_id in lookup)
        finally:
            self._scene.blockSignals(False)

    def fit_page(self) -> None:
        self.fitInView(QRectF(0, 0, self.document.page.width_mm, self.document.page.height_mm), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_factor = 1.0
        self.zoomChanged.emit(self._zoom_factor)

    def set_zoom_absolute(self, factor: float) -> None:
        factor = max(0.05, min(50.0, factor))
        current_transform = self.transform()
        current_scale = current_transform.m11() or 1.0
        scale_factor = factor / current_scale
        self.scale(scale_factor, scale_factor)
        self._zoom_factor = factor
        self.zoomChanged.emit(self._zoom_factor)

    def delete_selected_items(self) -> list[str]:
        return [item.object_id for item in self._scene.selectedItems() if isinstance(item, CanvasObjectItem)]

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        page_rect = QRectF(0, 0, self.document.page.width_mm, self.document.page.height_mm)

        painter.save()
        painter.fillRect(rect, QColor("#eef2f7"))
        painter.fillRect(page_rect, QColor("white"))
        painter.setPen(QPen(QColor("#d1d9e6"), 0))
        painter.drawRect(page_rect)

        if self.document.page.show_grid:
            grid = max(0.5, self.document.page.grid_mm)
            left = floor(rect.left() / grid) * grid
            right = ceil(rect.right() / grid) * grid
            top = floor(rect.top() / grid) * grid
            bottom = ceil(rect.bottom() / grid) * grid

            minor_pen = QPen(QColor("#edf1f6"), 0)
            major_pen = QPen(QColor("#dbe3ec"), 0)

            x = left
            while x <= right:
                painter.setPen(major_pen if round(x / grid) % 5 == 0 else minor_pen)
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                x += grid

            y = top
            while y <= bottom:
                painter.setPen(major_pen if round(y / grid) % 5 == 0 else minor_pen)
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                y += grid
        painter.restore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.pos())
        self.coordinateChanged.emit(scene_pos.x(), scene_pos.y())
        if self._panning:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._emit_selection_changed()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            self._zoom_factor = self.transform().m11()
            self.zoomChanged.emit(self._zoom_factor)
            event.accept()
            return
        super().wheelEvent(event)
