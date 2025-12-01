"""
CPU Cold Plate Thermal Analysis - 1D Resistance Network Model
==============================================================

Two-zone thermal resistance network calibrated against CFD results.
Demonstrates how thermal engineers use simplified models for rapid 
design optimization after CFD validation.

Author: Mitchell Stolk
Date: November 2025
"""
import numpy as np
from scipy.optimize import fsolve
from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass
class ThermalParams:
    """Parameters for cold plate thermal model"""
    Q_total: float      # Total heat load [W]
    mdot: float         # Mass flow rate [kg/s]
    Tin: float          # Inlet temperature [K]
    cp: float           # Specific heat [J/kg-K]
    R_contact: float    # Contact resistance [K/W]
    t_plate: float      # Plate thickness [m]
    k_plate: float      # Plate thermal conductivity [W/m-K]
    A_porous: float     # Porous zone area [m²]
    A_outlet: float     # Outlet zone area [m²]
    h_porous: float     # Porous zone heat transfer coefficient [W/m²-K]
    h_outlet: float     # Outlet zone heat transfer coefficient [W/m²-K]
    Tcpu_target: float = None  # Target CPU temp for calibration [K]
    Q1_target: float = None    # Target porous heat for calibration [W]

@dataclass
class ThermalResults:
    """Results from thermal model"""
    Tcpu: float         # CPU temperature [K]
    T_plate: float      # Cold plate temperature [K]
    Q: np.ndarray       # Heat split [W] - [Q_porous, Q_outlet]
    Tbulk: np.ndarray   # Bulk fluid temps [K] - [T1, T2]
    Twall: np.ndarray   # Wall temps [K] - [T1, T2]
    Tout: float         # Outlet temperature [K]
    Rpaths: np.ndarray  # Path resistances [K/W]
    R_contact: float    # Contact resistance [K/W]


def residuals_2zone(x: np.ndarray, Qtot: float, mdot: float, cp: float, 
                   Tin: float, Rpaths: np.ndarray, R_contact: float) -> np.ndarray:
    """
    Residual function for 2-zone thermal network solver.
    
    Args:
        x: State vector [Tcpu, Q1]
        Qtot: Total heat [W]
        mdot: Mass flow rate [kg/s]
        cp: Specific heat [J/kg-K]
        Tin: Inlet temperature [K]
        Rpaths: Thermal resistances [K/W]
        R_contact: Contact resistance [K/W]
    
    Returns:
        Residual vector [2]
    """
    Tcpu = x[0]
    Q1 = x[1]
    Q2 = Qtot - Q1
    
    # Temperature at cold plate (after contact resistance)
    T_plate = Tcpu - Qtot * R_contact
    
    # Cumulative bulk fluid temperatures (serial flow)
    Tb1 = Tin + Q1 / (mdot * cp)
    Tb2 = Tb1 + Q2 / (mdot * cp)
    
    # Heat flow predictions through each path
    Q1_pred = (T_plate - Tb1) / Rpaths[0]
    Q2_pred = (T_plate - Tb2) / Rpaths[1]
    
    F = np.zeros(2)
    F[0] = Q1 - Q1_pred
    F[1] = Q2 - Q2_pred
    
    return F


def coldplate_2zone_model(params: ThermalParams) -> ThermalResults:
    """
    Solve 2-zone cold plate thermal resistance network.
    
    Physics:
    - Two parallel thermal paths (porous zone and outlet zone)
    - Single contact resistance from CPU to cold plate
    - Serial fluid heating through zones
    
    Args:
        params: Thermal parameters
    
    Returns:
        Thermal results
    """
    # Extract parameters
    Qtot = params.Q_total
    mdot = params.mdot
    Tin = params.Tin
    cp = params.cp
    R_contact = params.R_contact
    t_plate = params.t_plate
    k_plate = params.k_plate
    A1 = params.A_porous
    A2 = params.A_outlet
    h1 = params.h_porous
    h2 = params.h_outlet
    
    # Thermal resistances
    Rcond1 = t_plate / (k_plate * A1)
    Rcond2 = t_plate / (k_plate * A2)
    Rconv1 = 1 / (h1 * A1)
    Rconv2 = 1 / (h2 * A2)
    Rpath1 = Rcond1 + Rconv1
    Rpath2 = Rcond2 + Rconv2
    Rpaths = np.array([Rpath1, Rpath2])
    
    # Initial guess
    Tout_guess = Tin + Qtot / (mdot * cp)
    Tcpu0 = Tout_guess + Qtot * (R_contact + np.min(Rpaths))
    w = 1.0 / Rpaths
    w = w / np.sum(w)
    Q1_0 = w[0] * Qtot
    x0 = np.array([Tcpu0, Q1_0])
    
    # Solve nonlinear system
    x_sol = fsolve(residuals_2zone, x0, 
                   args=(Qtot, mdot, cp, Tin, Rpaths, R_contact),
                   xtol=1e-9)
    
    Tcpu = x_sol[0]
    Q1 = x_sol[1]
    Q2 = Qtot - Q1
    
    # Cumulative bulk temperatures
    Tb1 = Tin + Q1 / (mdot * cp)
    Tb2 = Tb1 + Q2 / (mdot * cp)
    Tout = Tb2
    
    # Temperature at cold plate surface
    T_plate = Tcpu - Qtot * R_contact
    
    # Wall temperatures per zone
    Tw1 = T_plate - Q1 * Rcond1
    Tw2 = T_plate - Q2 * Rcond2
    
    return ThermalResults(
        Tcpu=Tcpu,
        T_plate=T_plate,
        Q=np.array([Q1, Q2]),
        Tbulk=np.array([Tb1, Tb2]),
        Twall=np.array([Tw1, Tw2]),
        Tout=Tout,
        Rpaths=Rpaths,
        R_contact=R_contact
    )


def calibration_residuals(h: np.ndarray, params: ThermalParams) -> np.ndarray:
    """
    Residuals for calibrating h-values to match CFD.
    
    Args:
        h: Heat transfer coefficients [h_porous, h_outlet]
        params: Thermal parameters with targets
    
    Returns:
        Residual vector [2]
    """
    params.h_porous = h[0]
    params.h_outlet = h[1]
    
    result = coldplate_2zone_model(params)
    
    F = np.zeros(2)
    F[0] = result.Tcpu - params.Tcpu_target
    F[1] = result.Q[0] - params.Q1_target
    
    return F


def main():
    """Main analysis: baseline + parametric studies"""
    
    # === Baseline CFD-Calibrated Model ===
    params_base = ThermalParams(
        Q_total=250.0,       # W
        mdot=0.01,           # kg/s
        cp=4181.72,          # J/kg-K
        Tin=300.0,           # K
        k_plate=398.0,       # W/m-K (copper)
        t_plate=0.000762,    # m
        R_contact=0.1414028, # K/W
        A_porous=1.27e-4,    # m²
        A_outlet=2.91e-4,    # m²
        h_porous=1.18e6,     # W/m²-K - calibrated from CFD
        h_outlet=6.99e3      # W/m²-K - calibrated from CFD
    )
    
    # Run baseline
    result_base = coldplate_2zone_model(params_base)
    
    print("=== BASELINE (CFD-Calibrated) ===")
    print(f"CPU Temp: {result_base.Tcpu:.2f} K ({result_base.Tcpu-273.15:.2f} C)")
    print(f"Outlet Temp: {result_base.Tout:.2f} K ({result_base.Tout-273.15:.2f} C)")
    print(f"Heat Split: Porous={result_base.Q[0]:.1f} W, Outlet={result_base.Q[1]:.1f} W\n")
    
    # === THERMAL RESISTANCE BREAKDOWN ===
    print("=== THERMAL RESISTANCE BREAKDOWN ===")
    R_total = (result_base.Tcpu - params_base.Tin) / params_base.Q_total
    R_porous_path = result_base.Rpaths[0]
    R_outlet_path = result_base.Rpaths[1]
    R_parallel = 1 / (1/R_porous_path + 1/R_outlet_path)
    
    print(f"Total Resistance: {R_total:.4f} K/W")
    print(f"  Contact Resistance: {params_base.R_contact:.4f} K/W ({params_base.R_contact/R_total*100:.1f}% of total)")
    print(f"  Parallel Paths: {R_parallel:.4f} K/W ({R_parallel/R_total*100:.1f}% of total)")
    print(f"    - Porous path: {R_porous_path:.4f} K/W")
    print(f"    - Outlet path: {R_outlet_path:.4f} K/W\n")
    
    # === PARAMETRIC STUDIES ===
    print("=== PARAMETRIC SENSITIVITY ANALYSIS ===\n")
    
    # Study 1: Contact Resistance
    print("--- Effect of Contact Resistance ---")
    R_contact_sweep = [0.01, 0.05, 0.1, 0.1414, 0.2, 0.3]
    for R in R_contact_sweep:
        params = ThermalParams(**vars(params_base))
        params.R_contact = R
        res = coldplate_2zone_model(params)
        print(f"R_contact = {R:.3f} K/W  →  Tcpu = {res.Tcpu:.2f} K  (ΔT = {res.Tcpu - result_base.Tcpu:+.2f} K)")
    
    # Study 2: Mass Flow Rate
    print("\n--- Effect of Mass Flow Rate ---")
    mdot_sweep = [0.005, 0.01, 0.02, 0.03, 0.05]
    for m in mdot_sweep:
        params = ThermalParams(**vars(params_base))
        params.mdot = m
        res = coldplate_2zone_model(params)
        print(f"mdot = {m:.3f} kg/s  →  Tcpu = {res.Tcpu:.2f} K  (ΔT = {res.Tcpu - result_base.Tcpu:+.2f} K),  Tout = {res.Tout:.2f} K")
    
    # Study 3: Porous Zone Area
    print("\n--- Effect of Porous Zone Area (Adding Fins) ---")
    A_multipliers = [0.5, 1.0, 2.0, 5.0, 10.0]
    for mult in A_multipliers:
        params = ThermalParams(**vars(params_base))
        params.A_porous = params_base.A_porous * mult
        res = coldplate_2zone_model(params)
        print(f"A_porous = {params.A_porous:.2e} m^2 ({mult:.1f}x)  →  Tcpu = {res.Tcpu:.2f} K  (ΔT = {res.Tcpu - result_base.Tcpu:+.2f} K)")
    
    # Study 4: Heat Transfer Coefficient
    print("\n--- Effect of Porous h (Improved Fins/Turbulence) ---")
    h_multipliers = [0.5, 1.0, 2.0, 5.0]
    for mult in h_multipliers:
        params = ThermalParams(**vars(params_base))
        params.h_porous = params_base.h_porous * mult
        res = coldplate_2zone_model(params)
        print(f"h_porous = {params.h_porous:.2e} W/m^2-K ({mult:.1f}x)  →  Tcpu = {res.Tcpu:.2f} K  (ΔT = {res.Tcpu - result_base.Tcpu:+.2f} K)")
    
    # Study 5: Plate Thickness
    print("\n--- Effect of Plate Thickness ---")
    t_plate_sweep = [0.0005, 0.000762, 0.001, 0.002]
    for t in t_plate_sweep:
        params = ThermalParams(**vars(params_base))
        params.t_plate = t
        res = coldplate_2zone_model(params)
        print(f"t_plate = {t:.4f} m  →  Tcpu = {res.Tcpu:.2f} K  (ΔT = {res.Tcpu - result_base.Tcpu:+.2f} K)")
    
    # === OPTIMIZATION SCENARIOS ===
    print("\n=== DESIGN OPTIMIZATION SCENARIOS ===\n")
    
    # Scenario 1: Improved TIM
    print("Scenario 1: Improved TIM (R_contact = 0.05 K/W)")
    params = ThermalParams(**vars(params_base))
    params.R_contact = 0.05
    res = coldplate_2zone_model(params)
    print(f"  Tcpu = {res.Tcpu:.2f} K  ({result_base.Tcpu - res.Tcpu:.2f} K reduction)\n")
    
    # Scenario 2: Double mass flow
    print("Scenario 2: Double Mass Flow (mdot = 0.02 kg/s)")
    params = ThermalParams(**vars(params_base))
    params.mdot = 0.02
    res = coldplate_2zone_model(params)
    print(f"  Tcpu = {res.Tcpu:.2f} K  ({result_base.Tcpu - res.Tcpu:.2f} K reduction)\n")
    
    # Scenario 3: 5x fin area
    print(f"Scenario 3: 5x Fin Area (A_porous = {5*params_base.A_porous:.2e} m^2)")
    params = ThermalParams(**vars(params_base))
    params.A_porous = 5 * params_base.A_porous
    res = coldplate_2zone_model(params)
    print(f"  Tcpu = {res.Tcpu:.2f} K  ({result_base.Tcpu - res.Tcpu:.2f} K reduction)\n")
    
    # Scenario 4: Combined
    print("Scenario 4: COMBINED (Better TIM + 2x flow + 3x fins)")
    params = ThermalParams(**vars(params_base))
    params.R_contact = 0.05
    params.mdot = 0.02
    params.A_porous = 3 * params_base.A_porous
    res = coldplate_2zone_model(params)
    print(f"  Tcpu = {res.Tcpu:.2f} K  ({result_base.Tcpu - res.Tcpu:.2f} K reduction!)")
    print(f"  Outlet = {res.Tout:.2f} K\n")

if __name__ == "__main__":

    main()
