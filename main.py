"""Графический клиент: Телефонный справочник (PySide6)."""
from __future__ import annotations

import sys
import psycopg
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QTableView, QVBoxLayout, QWidget,
    QComboBox, QHeaderView, QGroupBox
)

from db import Database, QueryError

class ConnectDialog(QDialog):
    # ... (Без изменений) ...
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Подключение к PostgreSQL")
        self.host = QLineEdit("localhost")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(5432)
        self.dbname = QLineEdit()
        self.user = QLineEdit("postgres")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout(self)
        form.addRow("Хост:", self.host)
        form.addRow("Порт:", self.port)
        form.addRow("База данных:", self.dbname)
        form.addRow("Пользователь:", self.user)
        form.addRow("Пароль:", self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return dict(host=self.host.text().strip(), port=self.port.value(),
                    dbname=self.dbname.text().strip(), user=self.user.text().strip(),
                    password=self.password.text())


class RecordDialog(QDialog):
    # ... (Без изменений) ...
    def __init__(self, db: Database, record_data: dict = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Редактирование записи" if record_data else "Новая запись")
        self.db = db
        self.setMinimumWidth(300)

        self.fams = db.get_dict("fam", "fid", "f_value")
        self.names = db.get_dict("ns", "nid", "name_value")
        self.otcs = db.get_dict("otcs", "oid", "o_value")
        self.streets = db.get_dict("streets", "sid", "s_value")

        self.fam_cb = self._create_combo(self.fams)
        self.name_cb = self._create_combo(self.names)
        self.otc_cb = self._create_combo(self.otcs)
        self.street_cb = self._create_combo(self.streets)

        self.kor = QSpinBox()
        self.kor.setRange(0, 9999)
        self.dom = QSpinBox()
        self.dom.setRange(0, 9999)
        self.tel = QLineEdit()

        form = QFormLayout(self)
        form.addRow("Фамилия:", self.fam_cb)
        form.addRow("Имя:", self.name_cb)
        form.addRow("Отчество:", self.otc_cb)
        form.addRow("Улица:", self.street_cb)
        form.addRow("Корпус:", self.kor)
        form.addRow("Дом:", self.dom)
        form.addRow("Телефон:", self.tel)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if record_data:
            self._set_combo_value(self.fam_cb, self.fams, record_data['fam'])
            self._set_combo_value(self.name_cb, self.names, record_data['name'])
            self._set_combo_value(self.otc_cb, self.otcs, record_data['otc'])
            self._set_combo_value(self.street_cb, self.streets, record_data['street'])
            self.kor.setValue(record_data['kor'])
            self.dom.setValue(record_data['dom'])
            self.tel.setText(record_data['tel'] or "")

    def _create_combo(self, items: list, add_empty=True) -> QComboBox:
        cb = QComboBox()
        if add_empty:
            cb.addItem("-- Все --", None)
        for id_val, text in items:
            cb.addItem(text, id_val)
        return cb

    def _set_combo_value(self, cb: QComboBox, items: list, text_val: str):
        for idx, (id_val, text) in enumerate(items):
            if text == text_val:
                cb.setCurrentIndex(idx)
                break

    def get_data(self) -> dict:
        return {
            "fam_id": self.fam_cb.currentData(),
            "name_id": self.name_cb.currentData(),
            "otc_id": self.otc_cb.currentData(),
            "street_id": self.street_cb.currentData(),
            "kor": self.kor.value(),
            "dom": self.dom.value(),
            "tel": self.tel.text().strip()
        }


class FilterWidget(QGroupBox):
    """Панель расширенных фильтров."""
    def __init__(self, db: Database, parent: QWidget = None):
        super().__init__("Фильтры", parent)
        self.db = db

        # Комбобоксы для справочников
        self.fam_cb = QComboBox()
        self.name_cb = QComboBox()
        self.otc_cb = QComboBox()
        self.street_cb = QComboBox()
        self.tel_input = QLineEdit()
        self.dom_input = QLineEdit()
        self.dom_input.setPlaceholderText("Номер дома...")

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Фамилия:"), 0, 0)
        layout.addWidget(self.fam_cb, 0, 1)
        layout.addWidget(QLabel("Имя:"), 0, 2)
        layout.addWidget(self.name_cb, 0, 3)
        layout.addWidget(QLabel("Отчество:"), 0, 4)
        layout.addWidget(self.otc_cb, 0, 5)

        layout.addWidget(QLabel("Улица:"), 1, 0)
        layout.addWidget(self.street_cb, 1, 1)
        layout.addWidget(QLabel("Дом:"), 1, 2)
        layout.addWidget(self.dom_input, 1, 3)
        layout.addWidget(QLabel("Телефон:"), 1, 4)
        layout.addWidget(self.tel_input, 1, 5)

    def load_dicts(self):
        """Загружает справочники в комбобоксы."""
        self.fam_cb.clear()
        self.fam_cb.addItem("-- Все --", None)
        for id_val, text in self.db.get_dict("fam", "fid", "f_value"):
            self.fam_cb.addItem(text, id_val)

        self.name_cb.clear()
        self.name_cb.addItem("-- Все --", None)
        for id_val, text in self.db.get_dict("ns", "nid", "name_value"):
            self.name_cb.addItem(text, id_val)

        self.otc_cb.clear()
        self.otc_cb.addItem("-- Все --", None)
        for id_val, text in self.db.get_dict("otcs", "oid", "o_value"):
            self.otc_cb.addItem(text, id_val)

        self.street_cb.clear()
        self.street_cb.addItem("-- Все --", None)
        for id_val, text in self.db.get_dict("streets", "sid", "s_value"):
            self.street_cb.addItem(text, id_val)

    def get_filters(self) -> dict:
        """Собирает текущие значения фильтров."""
        filters = {}
        if self.fam_cb.currentData(): filters["fam_id"] = self.fam_cb.currentData()
        if self.name_cb.currentData(): filters["name_id"] = self.name_cb.currentData()
        if self.otc_cb.currentData(): filters["otc_id"] = self.otc_cb.currentData()
        if self.street_cb.currentData(): filters["street_id"] = self.street_cb.currentData()
        if self.tel_input.text().strip(): filters["tel"] = self.tel_input.text().strip()
        if self.dom_input.text().strip(): filters["dom"] = self.dom_input.text().strip()
        return filters

    def clear_filters(self):
        """Сбрасывает все фильтры."""
        self.fam_cb.setCurrentIndex(0)
        self.name_cb.setCurrentIndex(0)
        self.otc_cb.setCurrentIndex(0)
        self.street_cb.setCurrentIndex(0)
        self.tel_input.clear()
        self.dom_input.clear()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Телефонный справочник")
        self.resize(1100, 700)
        self.db = Database()

        # --- Верхняя панель (Кнопки и базовый поиск) ---
        btn_toggle_filters = QPushButton("Фильтры")
        btn_toggle_filters.setCheckable(True)
        btn_toggle_filters.clicked.connect(self.toggle_filters)

        self.btn_add = QPushButton("Добавить")
        self.btn_add.clicked.connect(self.add_record)
        self.btn_edit = QPushButton("Изменить")
        self.btn_edit.clicked.connect(self.edit_record)
        self.btn_del = QPushButton("Удалить")
        self.btn_del.clicked.connect(self.delete_record)

        top_panel = QHBoxLayout()
        top_panel.addWidget(btn_toggle_filters)
        top_panel.addStretch()
        top_panel.addWidget(self.btn_add)
        top_panel.addWidget(self.btn_edit)
        top_panel.addWidget(self.btn_del)

        # --- Панель фильтров ---
        self.filter_widget = FilterWidget(self.db)
        self.filter_widget.setVisible(False) # Скрыта по умолчанию

        # Кнопки Применить / Сбросить
        btn_apply_filters = QPushButton("Применить фильтры")
        btn_apply_filters.clicked.connect(self.refresh_data)
        btn_clear_filters = QPushButton("Сбросить фильтры")
        btn_clear_filters.clicked.connect(self.clear_filters_and_refresh)

        filter_btn_layout = QHBoxLayout()
        filter_btn_layout.addStretch()
        filter_btn_layout.addWidget(btn_clear_filters)
        filter_btn_layout.addWidget(btn_apply_filters)
        self.filter_widget.layout().addLayout(filter_btn_layout, 2, 0, 1, 6) # Добавляем кнопки внизу фильтров

        # --- Таблица ---
        self.model = QStandardItemModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.view.doubleClicked.connect(self.edit_record)
        self.view.setSortingEnabled(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_panel)
        main_layout.addWidget(self.filter_widget)
        main_layout.addWidget(self.view, 1)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.statusBar().showMessage("Нет подключения")
        self._set_crud_enabled(False)

    def toggle_filters(self):
        self.filter_widget.setVisible(not self.filter_widget.isVisible())

    def _set_crud_enabled(self, state: bool):
        self.btn_add.setEnabled(state)
        self.btn_edit.setEnabled(state)
        self.btn_del.setEnabled(state)

    def connect_db(self) -> None:
        dlg = ConnectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                self.db.connect(**dlg.values())
                self.statusBar().showMessage("Подключено успешно")
                self._set_crud_enabled(True)

                # Загружаем справочники в фильтры
                self.filter_widget.load_dicts()

                self.refresh_data()
            except psycopg.Error as e:
                QMessageBox.critical(self, "Ошибка подключения", str(e).strip())

    def clear_filters_and_refresh(self):
        self.filter_widget.clear_filters()
        self.refresh_data()

    def refresh_data(self) -> None:
        if self.db.conn is None:
            return

        filters = self.filter_widget.get_filters()
        try:
            headers, rows = self.db.get_records(filters=filters)

            sort_col = self.view.horizontalHeader().sortIndicatorSection()
            sort_order = self.view.horizontalHeader().sortIndicatorOrder()

            self.model.clear()
            display_headers = ["UID", "Фамилия", "Имя", "Отчество", "Улица", "Корпус", "Дом", "Телефон"]
            self.model.setHorizontalHeaderLabels(display_headers)

            for row in rows:
                items = []
                for i, val in enumerate(row):
                    if i in (5, 6) and val is not None:
                        item = QStandardItem()
                        item.setData(int(val), Qt.ItemDataRole.DisplayRole)
                    else:
                        text = "NULL" if val is None else str(val)
                        item = QStandardItem(text)
                    item.setEditable(False)
                    items.append(item)
                self.model.appendRow(items)

            self.view.resizeColumnsToContents()
            self.view.setColumnHidden(0, True)

            if sort_col != -1:
                self.view.sortByColumn(sort_col, sort_order)
            else:
                self.view.sortByColumn(1, Qt.SortOrder.AscendingOrder)

            self.statusBar().showMessage(f"Найдено записей: {len(rows)}")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные:\n{e}")

    def _get_selected_uid(self) -> int | None:
        selected = self.view.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "Внимание", "Сначала выберите строку в таблице.")
            return None
        row_idx = selected[0].row()
        uid_item = self.model.item(row_idx, 0)
        return int(uid_item.text())

    def _get_row_data(self, row_idx: int) -> dict:
        return {
            "fam": self.model.item(row_idx, 1).text(),
            "name": self.model.item(row_idx, 2).text(),
            "otc": self.model.item(row_idx, 3).text(),
            "street": self.model.item(row_idx, 4).text(),
            "kor": int(self.model.item(row_idx, 5).text()) if self.model.item(row_idx, 5).text() not in ("NULL", "") else 0,
            "dom": int(self.model.item(row_idx, 6).text()) if self.model.item(row_idx, 6).text() not in ("NULL", "") else 0,
            "tel": self.model.item(row_idx, 7).text() if self.model.item(row_idx, 7).text() != "NULL" else "",
        }

    def add_record(self) -> None:
        dlg = RecordDialog(self.db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.db.add_record(**data)
                self.refresh_data()
            except psycopg.Error as e:
                QMessageBox.critical(self, "Ошибка БД", str(e).strip())

    def edit_record(self) -> None:
        uid = self._get_selected_uid()
        if not uid: return

        row_idx = self.view.selectionModel().selectedRows()[0].row()
        row_data = self._get_row_data(row_idx)

        dlg = RecordDialog(self.db, record_data=row_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.db.update_record(uid, **data)
                self.refresh_data()
            except psycopg.Error as e:
                QMessageBox.critical(self, "Ошибка БД", str(e).strip())

    def delete_record(self) -> None:
        uid = self._get_selected_uid()
        if not uid: return

        reply = QMessageBox.question(self, "Подтверждение", "Вы уверены, что хотите удалить эту запись?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_record(uid)
                self.refresh_data()
            except psycopg.Error as e:
                QMessageBox.critical(self, "Ошибка БД", str(e).strip())

    def closeEvent(self, event) -> None:
        self.db.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    win.connect_db()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()