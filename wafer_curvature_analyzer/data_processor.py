import numpy as np
import pandas as pd
from scipy.interpolate import UnivariateSpline, griddata, RectBivariateSpline


# ============================================================================
# Загрузка CSV
# ============================================================================

class WaferDataset:
    """Один загруженный CSV-файл: метаданные + таблица данных."""

    def __init__(self, filename):
        self.filename = filename
        self.metadata = {}
        self.df = None

    def load(self):
        with open(self.filename, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()

        header_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("No,") or "x(mm)" in stripped:
                header_idx = i
                break
        if header_idx is None:
            header_idx = 0

        for line in lines[:header_idx]:
            parts = [p.strip() for p in line.strip().split(",")]
            i = 0
            while i < len(parts) - 1:
                key, val = parts[i], parts[i + 1]
                if key and val:
                    self.metadata[key.rstrip(":")] = val
                    i += 2
                else:
                    i += 1

        df = pd.read_csv(self.filename, skiprows=header_idx, encoding="utf-8-sig")
        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]

        if "x(mm)" not in df.columns:
            raise ValueError("В файле не найдена колонка 'x(mm)' — неизвестный формат CSV")

        df["x(mm)"] = pd.to_numeric(df["x(mm)"], errors="coerce")
        df = df[df["x(mm)"].notna()].reset_index(drop=True)

        for col in df.columns:
            if col != "No":
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.sort_values("x(mm)").reset_index(drop=True)
        self.df = df
        return self

    @property
    def numeric_columns(self):
        exclude = {"No", "x(mm)", "y(mm)"}
        return [c for c in self.df.columns if c not in exclude]

    def default_y_column(self):
        cols = self.numeric_columns
        return "Height(mm)" if "Height(mm)" in cols else cols[0]

    def x(self):
        return self.df["x(mm)"].values.astype(float)

    def y_coord(self):
        return self.df["y(mm)"].values.astype(float) if "y(mm)" in self.df.columns else np.zeros(len(self.df))

    def y(self, column):
        return self.df[column].values.astype(float)

    def has_2d_scan(self):
        yc = self.y_coord()
        return bool(np.nanmax(yc) - np.nanmin(yc) > 1e-6)

    @property
    def short_name(self):
        return self.filename.replace("\\", "/").split("/")[-1]


# ============================================================================
# Группа файлов (например, все измерения "до напыления")
# ============================================================================

def _interp_1d(ref_x, src_x, src_z):
    order = np.argsort(src_x)
    return np.interp(ref_x, src_x[order], src_z[order])


def _interp_2d(ref_x, ref_y, src_x, src_y, src_z):
    z = griddata((src_x, src_y), src_z, (ref_x, ref_y), method="linear")
    nanmask = np.isnan(z)
    if nanmask.any():
        z[nanmask] = griddata((src_x, src_y), src_z, (ref_x[nanmask], ref_y[nanmask]), method="nearest")
    return z


class WaferGroup:
    """Набор из одного или нескольких файлов, относящихся к одному этапу (до/после)."""

    def __init__(self, label):
        self.label = label
        self.datasets = []

    def add(self, dataset):
        self.datasets.append(dataset)

    def remove(self, index):
        if 0 <= index < len(self.datasets):
            del self.datasets[index]

    def clear(self):
        self.datasets = []

    def is_empty(self):
        return len(self.datasets) == 0

    def file_names(self):
        return [d.short_name for d in self.datasets]

    def combined(self):
        """{'x_mm','y_mm','z_mm','is_2d','n_files'}; при нескольких файлах — среднее."""
        if self.is_empty():
            return None
        ref = self.datasets[0]
        col = ref.default_y_column()
        x, y, z = ref.x(), ref.y_coord(), ref.y(col)

        if len(self.datasets) > 1:
            any_2d = any(d.has_2d_scan() for d in self.datasets) or (np.nanmax(y) - np.nanmin(y) > 1e-6)
            zs = [z]
            for d in self.datasets[1:]:
                col_d = d.default_y_column()
                if any_2d:
                    z_i = _interp_2d(x, y, d.x(), d.y_coord(), d.y(col_d))
                else:
                    z_i = _interp_1d(x, d.x(), d.y(col_d))
                zs.append(z_i)
            z = np.mean(zs, axis=0)

        is_2d = bool(np.nanmax(y) - np.nanmin(y) > 1e-6)
        return {"x_mm": x, "y_mm": y, "z_mm": z, "is_2d": is_2d, "n_files": len(self.datasets)}


# ============================================================================
# Аппроксимация (глобальная)
# ============================================================================

def fit_2d(x_mm, z_mm):
    """y = b*x + a*x^2 + c, в СИ (метры). R = 1/(2|a|)."""
    x_m = x_mm * 1e-3
    z_m = z_mm * 1e-3
    a, b, c = np.polyfit(x_m, z_m, 2)
    R_m = np.inf if a == 0 else 1.0 / (2.0 * abs(a))
    z_fit_m = a * x_m ** 2 + b * x_m + c
    return {"mode": "2D", "a": a, "b": b, "c": c, "R_m": R_m,
            "x_mm": x_mm, "z_fit_mm": z_fit_m * 1e3}


def fit_3d(x_mm, y_mm, z_mm):
    """z = z0 + a*x + b*y + c*x^2 + d*y^2, в СИ. Rx=1/(2|c|), Ry=1/(2|d|)."""
    x_m = x_mm * 1e-3
    y_m = y_mm * 1e-3
    z_m = z_mm * 1e-3
    A = np.column_stack([np.ones_like(x_m), x_m, y_m, x_m ** 2, y_m ** 2])
    coeffs, *_ = np.linalg.lstsq(A, z_m, rcond=None)
    z0, a, b, c, d = coeffs
    Rx_m = np.inf if c == 0 else 1.0 / (2.0 * abs(c))
    Ry_m = np.inf if d == 0 else 1.0 / (2.0 * abs(d))
    z_fit_m = A @ coeffs
    return {"mode": "3D", "z0": z0, "a": a, "b": b, "c": c, "d": d,
            "Rx_m": Rx_m, "Ry_m": Ry_m, "x_mm": x_mm, "y_mm": y_mm, "z_fit_mm": z_fit_m * 1e3}


def fit_group(group_data, overall_mode):
    """Аппроксимация одной группы данных с учётом общего режима (2D/3D)."""
    x_mm, y_mm, z_mm, is_2d = (group_data["x_mm"], group_data["y_mm"],
                                group_data["z_mm"], group_data["is_2d"])
    if overall_mode == "2D":
        return fit_2d(x_mm, z_mm)

    # overall_mode == "3D"
    if is_2d:
        return fit_3d(x_mm, y_mm, z_mm)

    # линейный скан внутри 3D-анализа -> допущение изотропности:
    # аппроксимируем по радиусу r=|x| (y=const), считаем Rx=Ry=R
    f2 = fit_2d(x_mm, z_mm)
    return {"mode": "3D", "z0": f2["c"], "a": f2["b"], "b": 0.0,
            "c": f2["a"], "d": f2["a"], "Rx_m": f2["R_m"], "Ry_m": f2["R_m"],
            "x_mm": x_mm, "y_mm": y_mm, "z_fit_mm": f2["z_fit_mm"],
            "isotropic_assumed": True}


def deviation_percent(z_mm):
    """Отклонение (%) = (max - min) * 100, согласно ТЗ."""
    return float((np.max(z_mm) - np.min(z_mm)) * 100.0)


# ============================================================================
# Локальная (поточечная) кривизна — для карты напряжения в каждой точке
# ============================================================================

def _local_curvature_1d(x_mm, z_mm, eval_x_mm):
    x_m = x_mm * 1e-3
    z_m = z_mm * 1e-3
    order = np.argsort(x_m)
    x_sorted, z_sorted = x_m[order], z_m[order]
    k = 3 if len(x_sorted) > 4 else max(1, min(2, len(x_sorted) - 1))
    std = np.std(z_sorted)
    s = len(x_sorted) * (std ** 2) * 0.05 if std > 0 else 0
    try:
        spl = UnivariateSpline(x_sorted, z_sorted, k=k, s=s)
        eval_x_m = eval_x_mm * 1e-3
        a_local = spl.derivative(2)(eval_x_m) / 2.0
        within = (eval_x_m >= x_sorted.min()) & (eval_x_m <= x_sorted.max())
        a_local = np.where(within, a_local, np.nan)
    except Exception:
        a_local = np.full_like(eval_x_mm, np.nan, dtype=float)
    return a_local


def _local_curvature_2d(x_mm, y_mm, z_mm, eval_x_mm, eval_y_mm):
    x_m, y_m, z_m = x_mm * 1e-3, y_mm * 1e-3, z_mm * 1e-3
    try:
        from scipy.interpolate import SmoothBivariateSpline
        std = np.std(z_m)
        s = len(z_m) * (std ** 2) * 0.3 if std > 0 else None
        spline = SmoothBivariateSpline(x_m, y_m, z_m, kx=3, ky=3, s=s)
        eval_x_m = eval_x_mm * 1e-3
        eval_y_m = eval_y_mm * 1e-3
        c_local = np.array([spline(px, py, dx=2, dy=0)[0, 0] for px, py in zip(eval_x_m, eval_y_m)]) / 2.0
        d_local = np.array([spline(px, py, dx=0, dy=2)[0, 0] for px, py in zip(eval_x_m, eval_y_m)]) / 2.0
        r_data_max = np.max(np.sqrt(x_m ** 2 + y_m ** 2))
        r_eval = np.sqrt(eval_x_m ** 2 + eval_y_m ** 2)
        within = r_eval <= r_data_max * 1.0
        c_local = np.where(within, c_local, np.nan)
        d_local = np.where(within, d_local, np.nan)
    except Exception:
        c_local = np.full_like(eval_x_mm, np.nan, dtype=float)
        d_local = np.full_like(eval_x_mm, np.nan, dtype=float)
    return c_local, d_local


def _local_cd_for_group(group_data, eval_x_mm, eval_y_mm):
    """Возвращает (c_local, d_local) в точках (eval_x_mm, eval_y_mm)."""
    if group_data["is_2d"]:
        return _local_curvature_2d(group_data["x_mm"], group_data["y_mm"], group_data["z_mm"],
                                    eval_x_mm, eval_y_mm)
    eval_r_mm = np.sqrt(eval_x_mm ** 2 + eval_y_mm ** 2)
    a_local = _local_curvature_1d(group_data["x_mm"], group_data["z_mm"], eval_r_mm)
    return a_local, a_local.copy()


def pointwise_stress(mode, before_group, after_group, before_fit, after_fit, factor):
    """
    Напряжение в каждой точке сетки "после напыления" (там, где обычно больше
    всего точек и представляет наибольший интерес).

    mode='2D'  -> {'x_mm', 'sigma_mpa'}
    mode='3D'  -> {'x_mm','y_mm','sigma_x_mpa','sigma_y_mpa','sigma_mpa'}
    """
    if before_group is None or after_group is None:
        return None

    ax, ay, az = after_group["x_mm"], after_group["y_mm"], after_group["z_mm"]

    if mode == "2D":
        a_after = _local_curvature_1d(ax, az, ax)
        a_after = np.where(np.isnan(a_after), after_fit["a"], a_after)
        a_before = _local_curvature_1d(before_group["x_mm"], before_group["z_mm"], ax)
        a_before = np.where(np.isnan(a_before), before_fit["a"], a_before)

        R_after = np.where(a_after == 0, np.inf, 1.0 / (2 * np.abs(a_after)))
        R_before = np.where(a_before == 0, np.inf, 1.0 / (2 * np.abs(a_before)))
        inv_after = np.where(np.isinf(R_after), 0.0, 1.0 / R_after)
        inv_before = np.where(np.isinf(R_before), 0.0, 1.0 / R_before)
        sigma_pa = factor * (inv_after - inv_before)
        return {"x_mm": ax, "y_mm": None, "sigma_mpa": sigma_pa / 1e6}

    # mode == "3D"
    c_after, d_after = _local_cd_for_group(after_group, ax, ay)
    c_after = np.where(np.isnan(c_after), after_fit["c"], c_after)
    d_after = np.where(np.isnan(d_after), after_fit["d"], d_after)

    c_before, d_before = _local_cd_for_group(before_group, ax, ay)
    c_before = np.where(np.isnan(c_before), before_fit["c"], c_before)
    d_before = np.where(np.isnan(d_before), before_fit["d"], d_before)

    Rx_after = np.where(c_after == 0, np.inf, 1 / (2 * np.abs(c_after)))
    Ry_after = np.where(d_after == 0, np.inf, 1 / (2 * np.abs(d_after)))
    Rx_before = np.where(c_before == 0, np.inf, 1 / (2 * np.abs(c_before)))
    Ry_before = np.where(d_before == 0, np.inf, 1 / (2 * np.abs(d_before)))

    inv_x_after = np.where(np.isinf(Rx_after), 0.0, 1 / Rx_after)
    inv_y_after = np.where(np.isinf(Ry_after), 0.0, 1 / Ry_after)
    inv_x_before = np.where(np.isinf(Rx_before), 0.0, 1 / Rx_before)
    inv_y_before = np.where(np.isinf(Ry_before), 0.0, 1 / Ry_before)

    sigma_x = factor * (inv_x_after - inv_x_before)
    sigma_y = factor * (inv_y_after - inv_y_before)
    sigma = (sigma_x + sigma_y) / 2.0

    return {"x_mm": ax, "y_mm": ay,
            "sigma_x_mpa": sigma_x / 1e6, "sigma_y_mpa": sigma_y / 1e6, "sigma_mpa": sigma / 1e6}


# ============================================================================
# Основной класс анализа
# ============================================================================

class CurvatureAnalyzer:

    PHYSICAL_CONSTANTS = {
        "Si (100)": {"E": 131e9, "nu": 0.28},
        "Si (111)": {"E": 169e9, "nu": 0.262},
        "Кварц": {"E": 73e9, "nu": 0.17},
    }

    def __init__(self):
        self.before_group = WaferGroup("до напыления")
        self.after_group = WaferGroup("после напыления")

        self.mode = None            # '2D' / '3D' / None
        self.before_data = None     # combined() группы
        self.after_data = None
        self.before_fit = None
        self.after_fit = None
        self.before_deviation = None
        self.after_deviation = None
        self.stress_result = None
        self.pointwise = None

    # ---------------- загрузка / удаление файлов ----------------

    def add_before_files(self, filenames):
        msgs = []
        for fn in filenames:
            try:
                ds = WaferDataset(fn).load()
                self.before_group.add(ds)
                msgs.append(f"«{ds.short_name}» добавлен в «до напыления» ({len(ds.x())} точек)")
            except Exception as e:
                msgs.append(f"Ошибка загрузки «{fn}»: {e}")
        self.recompute()
        return msgs

    def add_after_files(self, filenames):
        msgs = []
        for fn in filenames:
            try:
                ds = WaferDataset(fn).load()
                self.after_group.add(ds)
                msgs.append(f"«{ds.short_name}» добавлен в «после напыления» ({len(ds.x())} точек)")
            except Exception as e:
                msgs.append(f"Ошибка загрузки «{fn}»: {e}")
        self.recompute()
        return msgs

    def remove_before_file(self, index):
        self.before_group.remove(index)
        self.recompute()

    def remove_after_file(self, index):
        self.after_group.remove(index)
        self.recompute()

    # ---------------- автоматический пересчёт ----------------

    def recompute(self):
        """Пересчитывает всё, что не требует параметров E/nu/t_s/t_f (те задаются вручную)."""
        self.before_data = self.before_group.combined()
        self.after_data = self.after_group.combined()
        self.stress_result = None
        self.pointwise = None

        any_2d = (self.before_data is not None and self.before_data["is_2d"]) or \
                 (self.after_data is not None and self.after_data["is_2d"])
        self.mode = "3D" if any_2d else ("2D" if (self.before_data or self.after_data) else None)

        self.before_fit = fit_group(self.before_data, self.mode) if self.before_data else None
        self.after_fit = fit_group(self.after_data, self.mode) if self.after_data else None

        self.before_deviation = deviation_percent(self.before_data["z_mm"]) if self.before_data else None
        self.after_deviation = deviation_percent(self.after_data["z_mm"]) if self.after_data else None

    # ---------------- напряжение ----------------

    def calculate_stress(self, E_s, nu_s, t_s_m, t_f_m):
        if self.before_fit is None and self.after_fit is None:
            return False, "Сначала загрузите данные подложки"

        factor = (E_s * t_s_m ** 2) / (6.0 * (1 - nu_s) * t_f_m)

        if self.before_fit is not None and self.after_fit is not None:
            if self.mode == "2D":
                R_before, R_after = self.before_fit["R_m"], self.after_fit["R_m"]
                inv_b = 0.0 if np.isinf(R_before) else 1.0 / R_before
                inv_a = 0.0 if np.isinf(R_after) else 1.0 / R_after
                sigma = factor * (inv_a - inv_b)
                self.stress_result = {"sigma_pa": sigma, "sigma_mpa": sigma / 1e6, "sigma_gpa": sigma / 1e9,
                                       "mode": "2D", "detail": "разность кривизны до/после"}
            else:
                Rx_b, Ry_b = self.before_fit["Rx_m"], self.before_fit["Ry_m"]
                Rx_a, Ry_a = self.after_fit["Rx_m"], self.after_fit["Ry_m"]
                inv_xb = 0.0 if np.isinf(Rx_b) else 1.0 / Rx_b
                inv_yb = 0.0 if np.isinf(Ry_b) else 1.0 / Ry_b
                inv_xa = 0.0 if np.isinf(Rx_a) else 1.0 / Rx_a
                inv_ya = 0.0 if np.isinf(Ry_a) else 1.0 / Ry_a
                sigma_x = factor * (inv_xa - inv_xb)
                sigma_y = factor * (inv_ya - inv_yb)
                sigma = (sigma_x + sigma_y) / 2.0
                self.stress_result = {
                    "sigma_x_pa": sigma_x, "sigma_y_pa": sigma_y, "sigma_pa": sigma,
                    "sigma_x_mpa": sigma_x / 1e6, "sigma_y_mpa": sigma_y / 1e6, "sigma_mpa": sigma / 1e6,
                    "sigma_gpa": sigma / 1e9, "mode": "3D", "detail": "среднее по осям x и y",
                }
                # точечная карта напряжения (по сетке "после")
                self.pointwise = pointwise_stress(self.mode, self.before_data, self.after_data,
                                                   self.before_fit, self.after_fit, factor)
                return True, self.stress_result

            # точечная карта для 2D
            self.pointwise = pointwise_stress(self.mode, self.before_data, self.after_data,
                                               self.before_fit, self.after_fit, factor)
            return True, self.stress_result
        else:
            fit = self.after_fit or self.before_fit
            if self.mode == "2D":
                R = fit["R_m"]
                inv = 0.0 if np.isinf(R) else 1.0 / R
                sigma = factor * inv
                self.stress_result = {"sigma_pa": sigma, "sigma_mpa": sigma / 1e6, "sigma_gpa": sigma / 1e9,
                                       "mode": "2D", "detail": "классическая формула (один этап)"}
            else:
                Rx, Ry = fit["Rx_m"], fit["Ry_m"]
                inv_x = 0.0 if np.isinf(Rx) else 1.0 / Rx
                inv_y = 0.0 if np.isinf(Ry) else 1.0 / Ry
                sigma_x = factor * inv_x
                sigma_y = factor * inv_y
                sigma = (sigma_x + sigma_y) / 2.0
                self.stress_result = {
                    "sigma_x_pa": sigma_x, "sigma_y_pa": sigma_y, "sigma_pa": sigma,
                    "sigma_x_mpa": sigma_x / 1e6, "sigma_y_mpa": sigma_y / 1e6, "sigma_mpa": sigma / 1e6,
                    "sigma_gpa": sigma / 1e9, "mode": "3D", "detail": "классическая формула (один этап)",
                }
            return True, self.stress_result

    # ---------------- экспорт (несколько таблиц в одном файле) ----------------

    def export_results(self, file_path):
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("# ===== Таблица 1. Сводка результатов =====\n")
                f.write(f"Режим анализа,{self.mode or '-'}\n")
                if self.before_fit is not None:
                    if self.mode == "2D":
                        f.write(f"R (до напыления, м),{self.before_fit['R_m']:.6f}\n")
                    else:
                        f.write(f"Rx (до напыления, м),{self.before_fit['Rx_m']:.6f}\n")
                        f.write(f"Ry (до напыления, м),{self.before_fit['Ry_m']:.6f}\n")
                    f.write(f"Отклонение (до напыления, %),{self.before_deviation:.6f}\n")
                if self.after_fit is not None:
                    if self.mode == "2D":
                        f.write(f"R (после напыления, м),{self.after_fit['R_m']:.6f}\n")
                    else:
                        f.write(f"Rx (после напыления, м),{self.after_fit['Rx_m']:.6f}\n")
                        f.write(f"Ry (после напыления, м),{self.after_fit['Ry_m']:.6f}\n")
                    f.write(f"Отклонение (после напыления, %),{self.after_deviation:.6f}\n")
                if self.stress_result is not None:
                    if self.mode == "3D":
                        f.write(f"Напряжение по X (МПа),{self.stress_result['sigma_x_mpa']:.4f}\n")
                        f.write(f"Напряжение по Y (МПа),{self.stress_result['sigma_y_mpa']:.4f}\n")
                    f.write(f"Напряжение (среднее, МПа),{self.stress_result['sigma_mpa']:.4f}\n")
                    f.write(f"Напряжение (среднее, ГПа),{self.stress_result['sigma_gpa']:.6f}\n")
                f.write("\n")

                if self.before_data is not None:
                    f.write("# ===== Таблица 2. Данные «до напыления» (исходные + аппроксимация) =====\n")
                    df = pd.DataFrame({
                        "x(мм)": self.before_data["x_mm"],
                        "y(мм)": self.before_data["y_mm"],
                        "height_измерено(мм)": self.before_data["z_mm"],
                        "height_аппроксимация(мм)": self.before_fit["z_fit_mm"],
                    })
                    df.to_csv(f, index=False)
                    f.write("\n")

                if self.after_data is not None:
                    f.write("# ===== Таблица 3. Данные «после напыления» (исходные + аппроксимация) =====\n")
                    df = pd.DataFrame({
                        "x(мм)": self.after_data["x_mm"],
                        "y(мм)": self.after_data["y_mm"],
                        "height_измерено(мм)": self.after_data["z_mm"],
                        "height_аппроксимация(мм)": self.after_fit["z_fit_mm"],
                    })
                    df.to_csv(f, index=False)
                    f.write("\n")

                if self.pointwise is not None:
                    f.write("# ===== Таблица 4. Напряжение в каждой точке (сетка «после напыления») =====\n")
                    if self.mode == "2D":
                        df = pd.DataFrame({
                            "x(мм)": self.pointwise["x_mm"],
                            "sigma(МПа)": self.pointwise["sigma_mpa"],
                        })
                    else:
                        df = pd.DataFrame({
                            "x(мм)": self.pointwise["x_mm"],
                            "y(мм)": self.pointwise["y_mm"],
                            "sigma_x(МПа)": self.pointwise["sigma_x_mpa"],
                            "sigma_y(МПа)": self.pointwise["sigma_y_mpa"],
                            "sigma(МПа)": self.pointwise["sigma_mpa"],
                        })
                    df.to_csv(f, index=False)

            return True, f"Результаты сохранены: {file_path}"
        except Exception as e:
            return False, f"Ошибка экспорта: {e}"
