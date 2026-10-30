# -*- coding: utf-8 -*-
"""
Графический интерфейс анализатора кривизны подложки.

Загрузка данных — списками файлов (можно добавлять несколько, можно убирать).
Все геометрические величины (аппроксимация, радиус кривизны, отклонение)
считаются автоматически при любом изменении списка файлов. Линия/поверхность
аппроксимации на графике включается отдельной кнопкой. Напряжение по формуле
Стоуни считается по кнопке (нужны параметры материала). Карта напряжения в
каждой точке — отдельным переключателем.

Окно свободно меняет размер за края (никаких ползунков размера).
"""

import os
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (регистрирует 3D-проекцию)
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import matplotlib.tri as mtri

from data_processor import CurvatureAnalyzer

STYLE_SHEET = """
QMainWindow, QWidget { background-color: #ffffff; color: #1a1a1a; }
QGroupBox {
    border: 1px solid #999999; border-radius: 3px; margin-top: 8px;
    font-weight: bold; padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton {
    background-color: #f2f2f2; border: 1px solid #808080; border-radius: 2px;
    padding: 6px; color: #1a1a1a;
}
QPushButton:hover { background-color: #e0e0e0; }
QPushButton:pressed { background-color: #cccccc; }
QPushButton:checked { background-color: #d0d0d0; border: 1px solid #404040; }
QLabel { color: #1a1a1a; }
QListWidget, QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QTextEdit {
    background-color: #ffffff; border: 1px solid #999999; color: #1a1a1a;
}
QStatusBar { background-color: #f2f2f2; }
QRadioButton { color: #1a1a1a; }
"""

COLOR_BEFORE = "#888888"
COLOR_AFTER = "#000000"
COLOR_FIT = "#c0392b"



class WaferAnalyzerGUI(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.ca = CurvatureAnalyzer()
        self.show_fit = False
        self.show_stress_map = False
        self.color_before = COLOR_BEFORE
        self.color_after = COLOR_AFTER
        self.stress_cmap = "coolwarm"
        self.setStyleSheet(STYLE_SHEET)
        self.init_ui()

    # ------------------------------------------------------------------
    def init_ui(self):
        self.setWindowTitle("Анализатор кривизны подложки")
        self.setGeometry(80, 80,
                          self.config.get("window_width", 1500),
                          self.config.get("window_height", 880))
        self.setMinimumSize(800, 550)  # окно свободно тянется мышью за края

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout()
        central.setLayout(main_layout)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(380)
        left_scroll.setMaximumWidth(460)
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        left_scroll.setWidget(left_panel)

        right_panel = QWidget()
        self.right_panel = right_panel
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)

        # ============= ЛЕВАЯ ПАНЕЛЬ =============

        title = QLabel("АНАЛИЗАТОР КРИВИЗНЫ ПОДЛОЖКИ")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setWordWrap(True)
        left_layout.addWidget(title)

        # --- Группа "до напыления" ---
        before_group = QGroupBox("ПОДЛОЖКА (ДО НАПЫЛЕНИЯ)")
        before_layout = QVBoxLayout()
        self.before_list = QListWidget()
        self.before_list.setMaximumHeight(90)
        before_layout.addWidget(self.before_list)
        btn_row = QHBoxLayout()
        self.before_add_btn = QPushButton("Добавить файл(ы)")
        self.before_add_btn.clicked.connect(self.add_before_files)
        self.before_remove_btn = QPushButton("Убрать")
        self.before_remove_btn.clicked.connect(self.remove_before_file)
        btn_row.addWidget(self.before_add_btn)
        btn_row.addWidget(self.before_remove_btn)
        before_layout.addLayout(btn_row)
        before_group.setLayout(before_layout)
        left_layout.addWidget(before_group)

        # --- Группа "после напыления" ---
        after_group = QGroupBox("ПЛЁНКА (ПОСЛЕ НАПЫЛЕНИЯ)")
        after_layout = QVBoxLayout()
        self.after_list = QListWidget()
        self.after_list.setMaximumHeight(90)
        after_layout.addWidget(self.after_list)
        btn_row2 = QHBoxLayout()
        self.after_add_btn = QPushButton("Добавить файл(ы)")
        self.after_add_btn.clicked.connect(self.add_after_files)
        self.after_remove_btn = QPushButton("Убрать")
        self.after_remove_btn.clicked.connect(self.remove_after_file)
        btn_row2.addWidget(self.after_add_btn)
        btn_row2.addWidget(self.after_remove_btn)
        after_layout.addLayout(btn_row2)
        after_group.setLayout(after_layout)
        left_layout.addWidget(after_group)

        # --- График ---
        plot_group = QGroupBox("ГРАФИК")
        plot_layout = QVBoxLayout()

        view_row = QHBoxLayout()
        self.view_2d_radio = QRadioButton("2D")
        self.view_3d_radio = QRadioButton("3D")
        self.view_2d_radio.setChecked(True)
        self.view_2d_radio.toggled.connect(self.refresh_plot)
        view_row.addWidget(self.view_2d_radio)
        view_row.addWidget(self.view_3d_radio)
        plot_layout.addLayout(view_row)

        self.fit_btn = QPushButton("Аппроксимация")
        self.fit_btn.setCheckable(True)
        self.fit_btn.toggled.connect(self.toggle_fit)
        plot_layout.addWidget(self.fit_btn)

        self.stress_map_btn = QPushButton("Карта напряжения (в каждой точке)")
        self.stress_map_btn.setCheckable(True)
        self.stress_map_btn.toggled.connect(self.toggle_stress_map)
        plot_layout.addWidget(self.stress_map_btn)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("До напыления:"))
        self.color_before_btn = QPushButton()
        self.color_before_btn.setFixedWidth(40)
        self.color_before_btn.setToolTip("Цвет точек «до напыления»")
        self.color_before_btn.clicked.connect(lambda: self.pick_color("before"))
        color_row.addWidget(self.color_before_btn)
        color_row.addSpacing(10)
        color_row.addWidget(QLabel("После напыления:"))
        self.color_after_btn = QPushButton()
        self.color_after_btn.setFixedWidth(40)
        self.color_after_btn.setToolTip("Цвет точек «после напыления»")
        self.color_after_btn.clicked.connect(lambda: self.pick_color("after"))
        color_row.addWidget(self.color_after_btn)
        color_row.addStretch()
        plot_layout.addLayout(color_row)

        cmap_row = QHBoxLayout()
        cmap_row.addWidget(QLabel("Цветовая карта напряжения:"))
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(["coolwarm", "RdBu_r", "seismic", "RdYlBu_r", "Spectral_r", "bwr"])
        self.cmap_combo.currentTextChanged.connect(self.on_cmap_changed)
        cmap_row.addWidget(self.cmap_combo)
        plot_layout.addLayout(cmap_row)

        plot_group.setLayout(plot_layout)
        left_layout.addWidget(plot_group)

        # --- Напряжение по Стоуни ---
        stress_group = QGroupBox("НАПРЯЖЕНИЕ (ФОРМУЛА СТОУНИ)")
        stress_layout = QVBoxLayout()
        form = QFormLayout()

        self.material_combo = QComboBox()
        self.material_combo.addItems(list(CurvatureAnalyzer.PHYSICAL_CONSTANTS.keys()) + ["Свои значения"])
        self.material_combo.currentTextChanged.connect(self.on_material_changed)
        form.addRow("Материал подложки:", self.material_combo)

        self.e_spin = QDoubleSpinBox()
        self.e_spin.setRange(1, 1000)
        self.e_spin.setValue(131.0)
        self.e_spin.setSuffix(" ГПа")
        form.addRow("Модуль Юнга E:", self.e_spin)

        self.nu_spin = QDoubleSpinBox()
        self.nu_spin.setRange(0, 0.5)
        self.nu_spin.setSingleStep(0.01)
        self.nu_spin.setValue(0.28)
        form.addRow("Коэфф. Пуассона ν:", self.nu_spin)

        self.ts_spin = QDoubleSpinBox()
        self.ts_spin.setRange(1, 5000)
        self.ts_spin.setValue(725.0)
        self.ts_spin.setSuffix(" мкм")
        form.addRow("Толщина подложки:", self.ts_spin)

        self.tf_spin = QDoubleSpinBox()
        self.tf_spin.setRange(0.1, 100000)
        self.tf_spin.setValue(300.0)
        self.tf_spin.setSuffix(" нм")
        form.addRow("Толщина плёнки:", self.tf_spin)

        stress_layout.addLayout(form)

        self.stress_btn = QPushButton("Рассчитать напряжение")
        self.stress_btn.clicked.connect(self.run_stress)
        stress_layout.addWidget(self.stress_btn)

        stress_group.setLayout(stress_layout)
        left_layout.addWidget(stress_group)

        # --- Экспорт ---
        export_group = QGroupBox("ЭКСПОРТ")
        export_layout = QVBoxLayout()
        self.export_btn = QPushButton("Экспорт результатов")
        self.export_btn.clicked.connect(self.export_results)
        export_layout.addWidget(self.export_btn)
        export_group.setLayout(export_layout)
        left_layout.addWidget(export_group)

        left_layout.addStretch()

        # --- Результаты (автообновление) ---
        info_group = QGroupBox("РЕЗУЛЬТАТЫ")
        info_layout = QVBoxLayout()
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumHeight(180)
        info_layout.addWidget(self.info_text)
        info_group.setLayout(info_layout)
        left_layout.addWidget(info_group)

        # ============= ПРАВАЯ ПАНЕЛЬ (график) =============
        self.figure = Figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas)

        main_layout.addWidget(left_scroll)
        main_layout.addWidget(right_panel)

        self._update_color_buttons()
        self.plot_empty()
        self.statusBar().showMessage("Готов к работе")

    # ------------------------------------------------------------------
    # Вспомогательные

    def log(self, text):
        self.info_text.append(str(text))

    def _refresh_lists(self):
        self.before_list.clear()
        self.before_list.addItems(self.ca.before_group.file_names())
        self.after_list.clear()
        self.after_list.addItems(self.ca.after_group.file_names())

    def _log_auto_results(self):
        """Автоматический вывод геометрических результатов после пересчёта."""
        if self.ca.mode is None:
            return
        self.log(f"— Режим анализа: {self.ca.mode} —")
        if self.ca.before_fit is not None:
            if self.ca.mode == "2D":
                r_txt = self._fmt_r(self.ca.before_fit["R_m"])
                self.log(f"До напыления: R = {r_txt}, отклонение = {self.ca.before_deviation:.4f}%")
            else:
                rx_txt = self._fmt_r(self.ca.before_fit["Rx_m"])
                ry_txt = self._fmt_r(self.ca.before_fit["Ry_m"])
                iso = " (изотропное допущение — линейный скан)" if self.ca.before_fit.get("isotropic_assumed") else ""
                self.log(f"До напыления: Rx = {rx_txt}, Ry = {ry_txt}{iso}, "
                          f"отклонение = {self.ca.before_deviation:.4f}%")
        if self.ca.after_fit is not None:
            if self.ca.mode == "2D":
                r_txt = self._fmt_r(self.ca.after_fit["R_m"])
                self.log(f"После напыления: R = {r_txt}, отклонение = {self.ca.after_deviation:.4f}%")
            else:
                rx_txt = self._fmt_r(self.ca.after_fit["Rx_m"])
                ry_txt = self._fmt_r(self.ca.after_fit["Ry_m"])
                iso = " (изотропное допущение — линейный скан)" if self.ca.after_fit.get("isotropic_assumed") else ""
                self.log(f"После напыления: Rx = {rx_txt}, Ry = {ry_txt}{iso}, "
                          f"отклонение = {self.ca.after_deviation:.4f}%")

    @staticmethod
    def _fmt_r(R_m):
        return "∞ (плоская)" if np.isinf(R_m) else f"{R_m:.4f} м"

    def _on_data_changed(self):
        self._refresh_lists()
        self.fit_btn.blockSignals(True)
        self.fit_btn.setChecked(False)
        self.fit_btn.blockSignals(False)
        self.stress_map_btn.blockSignals(True)
        self.stress_map_btn.setChecked(False)
        self.stress_map_btn.blockSignals(False)
        self.show_fit = False
        self.show_stress_map = False
        self._log_auto_results()
        self.refresh_plot()

    # ------------------------------------------------------------------
    # Загрузка / удаление файлов

    def add_before_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите CSV файл(ы) подложки (до напыления)", "", "CSV файлы (*.csv);;Все файлы (*.*)"
        )
        if not files:
            return
        for msg in self.ca.add_before_files(files):
            self.log(msg)
        self._on_data_changed()
        self.statusBar().showMessage("Подложка (до) обновлена")

    def add_after_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите CSV файл(ы) плёнки (после напыления)", "", "CSV файлы (*.csv);;Все файлы (*.*)"
        )
        if not files:
            return
        for msg in self.ca.add_after_files(files):
            self.log(msg)
        self._on_data_changed()
        self.statusBar().showMessage("Плёнка (после) обновлена")

    def remove_before_file(self):
        row = self.before_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Информация", "Выберите файл в списке «до напыления»")
            return
        self.ca.remove_before_file(row)
        self.log("Файл убран из группы «до напыления»")
        self._on_data_changed()

    def remove_after_file(self):
        row = self.after_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Информация", "Выберите файл в списке «после напыления»")
            return
        self.ca.remove_after_file(row)
        self.log("Файл убран из группы «после напыления»")
        self._on_data_changed()

    # ------------------------------------------------------------------
    # Кнопки графика

    def toggle_fit(self, checked):
        self.show_fit = checked
        self.refresh_plot()

    def toggle_stress_map(self, checked):
        if checked and self.ca.pointwise is None:
            QMessageBox.information(self, "Информация",
                                     "Сначала рассчитайте напряжение (нужны данные до и после напыления)")
            self.stress_map_btn.blockSignals(True)
            self.stress_map_btn.setChecked(False)
            self.stress_map_btn.blockSignals(False)
            return
        self.show_stress_map = checked
        self.refresh_plot()

    # ------------------------------------------------------------------
    # Цвет точек / цветовая карта / экспорт графика

    def _update_color_buttons(self):
        for btn, hex_color in ((self.color_before_btn, self.color_before),
                                (self.color_after_btn, self.color_after)):
            btn.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #666666; border-radius: 2px;"
            )

    def pick_color(self, which):
        current = self.color_before if which == "before" else self.color_after
        color = QColorDialog.getColor(QColor(current), self, "Выберите цвет точек")
        if not color.isValid():
            return
        hex_color = color.name()
        if which == "before":
            self.color_before = hex_color
        else:
            self.color_after = hex_color
        self._update_color_buttons()
        self.refresh_plot()

    def on_cmap_changed(self, name):
        self.stress_cmap = name
        if self.show_stress_map:
            self.refresh_plot()

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Отрисовка

    def plot_empty(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_xlabel("x, мм")
        ax.set_ylabel("Высота, мм")
        ax.set_title("Добавьте данные подложки (до и/или после напыления)")
        ax.grid(True, alpha=0.3)
        ax.invert_yaxis()
        self.canvas.draw()

    @staticmethod
    def _add_mesh_edges(ax, x, y, z, color="#808080", alpha=0.4, linewidth=0.5):
        """
        Соединяет соседние точки (x, y, z) тонкими линиями по триангуляции
        Делоне (по x,y) — чтобы облако точек одного набора данных визуально
        "склеивалось" в поверхность и не путалось с точками другого набора
        или другого файла.
        """
        x, y, z = np.asarray(x), np.asarray(y), np.asarray(z)
        if len(x) < 3:
            return
        try:
            tri = mtri.Triangulation(x, y)
            edges = set()
            for a, b, c in tri.triangles:
                edges.add(tuple(sorted((int(a), int(b)))))
                edges.add(tuple(sorted((int(b), int(c)))))
                edges.add(tuple(sorted((int(a), int(c)))))
            segments = [[(x[i], y[i], z[i]), (x[j], y[j], z[j])] for i, j in edges]
            lc = Line3DCollection(segments, colors=color, linewidths=linewidth, alpha=alpha)
            ax.add_collection3d(lc)
        except Exception:
            pass

    def _reset_toolbar_mode(self):
        """
        Если на тулбаре включён инструмент "Pan" или "Zoom", matplotlib
        блокирует обработку вращения 3D-графика мышью (виджет-лок достаётся
        тулбару). Поэтому перед каждой перерисовкой отключаем активный
        инструмент — иначе вращение 3D-сцены мышью может "не работать".
        """
        try:
            mode = self.toolbar.mode
            if mode and getattr(mode, "name", "") == "PAN":
                self.toolbar.pan()
            elif mode and getattr(mode, "name", "") == "ZOOM":
                self.toolbar.zoom()
        except Exception:
            pass

    def refresh_plot(self):
        self._reset_toolbar_mode()
        if self.ca.before_data is None and self.ca.after_data is None:
            self.plot_empty()
            return
        if self.show_stress_map and self.ca.pointwise is not None:
            self._plot_stress_map()
        elif self.view_3d_radio.isChecked():
            self._plot_3d()
        else:
            self._plot_2d()

    def _plot_2d(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if self.ca.before_data is not None:
            x, z = self.ca.before_data["x_mm"], self.ca.before_data["z_mm"]
            ax.plot(x, z, "o", color=self.color_before, markersize=3, label="До напыления")
            if self.show_fit and self.ca.before_fit is not None:
                order = np.argsort(x)
                x_f = self.ca.before_fit.get("x_mm", x)
                z_f = self.ca.before_fit.get("z_fit_mm")
                if z_f is not None:
                    ax.plot(np.array(x_f)[order], np.array(z_f)[order], "-",
                            color=self.color_before, linewidth=1.8,
                            label="До напыления — аппроксимация")

        if self.ca.after_data is not None:
            x, z = self.ca.after_data["x_mm"], self.ca.after_data["z_mm"]
            ax.plot(x, z, "o", color=self.color_after, markersize=3, label="После напыления")
            if self.show_fit and self.ca.after_fit is not None:
                order = np.argsort(x)
                x_f = self.ca.after_fit.get("x_mm", x)
                z_f = self.ca.after_fit.get("z_fit_mm")
                if z_f is not None:
                    ax.plot(np.array(x_f)[order], np.array(z_f)[order], "-",
                            color=self.color_after, linewidth=1.8, label="После напыления — аппроксимация")

        ax.set_xlabel("x, мм")
        ax.set_ylabel("Высота, мм")
        ax.set_title("Профиль подложки (проекция по x)")
        ax.grid(True, alpha=0.3)
        ax.invert_yaxis()  # инверсия оси Y — по физическому смыслу изгиба
        ax.legend(loc="best", fontsize=8)
        self.canvas.draw()

    def _plot_3d(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111, projection="3d")

        plotted = False
        for data, fit, color, label in (
            (self.ca.before_data, self.ca.before_fit, self.color_before, "До напыления"),
            (self.ca.after_data, self.ca.after_fit, self.color_after, "После напыления"),
        ):
            if data is None:
                continue
            plotted = True
            x, y, z = data["x_mm"], data["y_mm"], data["z_mm"]
            if data["is_2d"]:
                self._add_mesh_edges(ax, x, y, z, color=color, alpha=0.35, linewidth=0.6)
                ax.scatter(x, y, z, color=color, s=10, label=label)
                if self.show_fit and fit is not None:
                    xf, yf, zf = fit["x_mm"], fit["y_mm"], fit["z_fit_mm"]
                    ax.plot_trisurf(xf, yf, zf, color=color, alpha=0.35, linewidth=0.1)
            else:
                ax.plot(x, y, z, "-o", color=color, markersize=3, linewidth=1.2, label=label)
                if self.show_fit and fit is not None:
                    xf, yf, zf = fit["x_mm"], fit["y_mm"], fit["z_fit_mm"]
                    order = np.argsort(xf)
                    ax.plot(np.array(xf)[order], np.array(yf)[order], np.array(zf)[order],
                            "-", color=color, linewidth=2)

        if not plotted:
            ax.set_title("Нет данных для отображения")
        else:
            ax.set_xlabel("x, мм")
            ax.set_ylabel("y, мм")
            ax.set_zlabel("Высота, мм")
            ax.set_title("Профиль подложки (3D)")
            ax.invert_zaxis()
            ax.legend(loc="best", fontsize=8)

        self.canvas.draw()

    def _plot_stress_map(self):
        """
        Карта напряжения в каждой точке. Цвет точки = величина σ в этой точке
        (синий - сжатие/минимум, красный - растяжение/максимум, симметрично
        относительно нуля). Переключатель 2D/3D слева определяет, показывать
        ли точки как плоскую карту (x,y) или в 3D (x,y,высота), с тем же
        раскрашиванием.
        """
        self.figure.clear()
        pw = self.ca.pointwise
        sigma = np.array(pw["sigma_mpa"], dtype=float)

        finite = sigma[np.isfinite(sigma)]
        vmax = float(np.max(np.abs(finite))) if finite.size else 1.0
        vmax = vmax if vmax > 0 else 1.0
        vmin = -vmax

        use_3d = self.view_3d_radio.isChecked()

        if self.ca.mode == "2D":
            x = np.array(pw["x_mm"], dtype=float)
            order = np.argsort(x)
            if use_3d:
                z = np.array(self.ca.after_data["z_mm"], dtype=float)
                ax = self.figure.add_subplot(111, projection="3d")
                ax.plot(x[order], np.zeros_like(x)[order], z[order], "-",
                        color="#999999", linewidth=1.0, alpha=0.6)
                sc = ax.scatter(x, np.zeros_like(x), z, c=sigma, cmap=self.stress_cmap,
                                 vmin=vmin, vmax=vmax, s=35, edgecolors="k", linewidths=0.3)
                ax.set_xlabel("x, мм")
                ax.set_ylabel("y, мм")
                ax.set_zlabel("Высота, мм")
                ax.set_title("Напряжение в каждой точке (3D)")
                ax.invert_zaxis()
                cbar = self.figure.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
                cbar.set_label("Напряжение σ, МПа")
            else:
                ax = self.figure.add_subplot(111)
                ax.plot(x[order], sigma[order], "-", color="#bbbbbb", linewidth=1.0, zorder=1)
                sc = ax.scatter(x, sigma, c=sigma, cmap=self.stress_cmap, vmin=vmin, vmax=vmax,
                                 s=35, edgecolors="k", linewidths=0.3, zorder=2)
                cbar = self.figure.colorbar(sc, ax=ax)
                cbar.set_label("Напряжение σ, МПа")
                ax.set_xlabel("x, мм")
                ax.set_ylabel("Напряжение σ, МПа")
                ax.set_title("Напряжение в каждой точке")
                ax.grid(True, alpha=0.3)
        else:
            x, y = np.array(pw["x_mm"], dtype=float), np.array(pw["y_mm"], dtype=float)
            if use_3d:
                z = np.array(self.ca.after_data["z_mm"], dtype=float)
                ax = self.figure.add_subplot(111, projection="3d")
                self._add_mesh_edges(ax, x, y, z, color="#555555", alpha=0.3, linewidth=0.5)
                sc = ax.scatter(x, y, z, c=sigma, cmap=self.stress_cmap, vmin=vmin, vmax=vmax,
                                 s=30, edgecolors="k", linewidths=0.3, depthshade=True)
                ax.set_xlabel("x, мм")
                ax.set_ylabel("y, мм")
                ax.set_zlabel("Высота, мм")
                ax.set_title("Карта напряжения по поверхности (3D)")
                ax.invert_zaxis()
                cbar = self.figure.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
                cbar.set_label("Напряжение σ, МПа")
            else:
                ax = self.figure.add_subplot(111)
                sc = ax.scatter(x, y, c=sigma, cmap=self.stress_cmap, vmin=vmin, vmax=vmax, s=45,
                                 edgecolors="k", linewidths=0.3)
                cbar = self.figure.colorbar(sc, ax=ax)
                cbar.set_label("Напряжение σ, МПа")
                ax.set_xlabel("x, мм")
                ax.set_ylabel("y, мм")
                ax.set_title("Карта напряжения по поверхности подложки")
                ax.set_aspect("equal", adjustable="box")
        self.canvas.draw()

    # ------------------------------------------------------------------
    # Напряжение

    def on_material_changed(self, name):
        consts = CurvatureAnalyzer.PHYSICAL_CONSTANTS.get(name)
        if consts:
            self.e_spin.setValue(consts["E"] / 1e9)
            self.nu_spin.setValue(consts["nu"])

    def run_stress(self):
        if self.ca.before_fit is None and self.ca.after_fit is None:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите данные подложки")
            return
        E_s = self.e_spin.value() * 1e9
        nu_s = self.nu_spin.value()
        t_s_m = self.ts_spin.value() * 1e-6
        t_f_m = self.tf_spin.value() * 1e-9
        ok, result = self.ca.calculate_stress(E_s, nu_s, t_s_m, t_f_m)
        if ok:
            if result["mode"] == "3D":
                self.log(f"Напряжение: σx = {result['sigma_x_mpa']:.3f} МПа, "
                          f"σy = {result['sigma_y_mpa']:.3f} МПа, "
                          f"среднее σ = {result['sigma_mpa']:.3f} МПа ({result['sigma_gpa']:.5f} ГПа) "
                          f"— {result['detail']}")
            else:
                self.log(f"Напряжение: σ = {result['sigma_mpa']:.3f} МПа "
                          f"({result['sigma_gpa']:.5f} ГПа) — {result['detail']}")
            if self.ca.pointwise is not None:
                self.log("Карта напряжения в каждой точке рассчитана (кнопка «Карта напряжения»).")
            self.statusBar().showMessage("Напряжение рассчитано")
        else:
            QMessageBox.warning(self, "Ошибка", result)

    # ------------------------------------------------------------------
    # Экспорт

    def export_results(self):
        if self.ca.before_fit is None and self.ca.after_fit is None:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите данные")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить результаты", "results.csv", "CSV файлы (*.csv)")
        if not file_path:
            return
        ok, msg = self.ca.export_results(file_path)
        self.log(msg)
        self.statusBar().showMessage(msg)
