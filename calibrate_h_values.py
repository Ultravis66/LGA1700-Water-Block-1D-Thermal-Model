"""
Heat Transfer Coefficient Calibration Script
=============================================

Calibrates effective h-values (h_porous, h_outlet) by matching 1D model 
predictions to CFD results for CPU temperature and heat split.

This script demonstrates the inverse problem: given CFD results, 
what heat transfer coefficients make the simplified model match?

Author: Mitchell Stolk
Date: November 2025
"""

import numpy as np
from scipy.optimize import fsolve
from coldplate_thermal_analysis import ThermalParams, coldplate_2zone_model

# === CFD Inputs (Baseline Case) ===
Qtot = 250.0          # [W] Total heat load
mdot = 0.01           # [kg/s] Mass flow rate
cp = 4181.72          # [J/kg-K] Specific heat (water)
Tin = 300.0           # [K] Inlet temperature
k_plate = 398.0       # [W/m-K] Copper thermal conductivity
t_plate = 0.000762    # [m] Plate thickness
R_contact = 0.1414028 # [K/W] Contact resistance (LGA1700 IHS)

# === CFD Target Values (to match) ===
Tcpu_CFD = 346.3      # [K] CPU temperature from CFD
Tout_CFD = 306.04     # [K] Outlet temperature from CFD
Q1_CFD = 240.0        # [W] Heat through porous zone
Q2_CFD = 10.2         # [W] Heat through outlet zone

# === Areas from CFD Surface Integrals ===
# Porous zone walls
A_PM_B = 0.0          # [m²] Bottom wall (negligible)
A_PM_S1 = 6.36e-5     # [m²] Side wall 1
A_PM_S2 = 6.36e-5     # [m²] Side wall 2
A_porous_total = A_PM_B + A_PM_S1 + A_PM_S2

# Outlet zone walls (all FV_Out interfaces)
A_outlet_total = (1.92e-4 + 4.19e-5 + 4.19e-5 + 
                  7.83e-6 + 7.83e-6 + 1.22e-14 + 1.22e-14)

print(f"Porous zone area: {A_porous_total:.2e} m²")
print(f"Outlet zone area: {A_outlet_total:.2e} m²")

# === Build parameter structure ===
params = ThermalParams(
    Q_total=Qtot,
    mdot=mdot,
    Tin=Tin,
    cp=cp,
    R_contact=R_contact,
    t_plate=t_plate,
    k_plate=k_plate,
    A_porous=A_porous_total,
    A_outlet=A_outlet_total,
    h_porous=1e5,  # placeholder, will be calibrated
    h_outlet=1e3,  # placeholder, will be calibrated
    Tcpu_target=Tcpu_CFD,
    Q1_target=Q1_CFD
)


def calibration_residuals(h, params):
    """
    Residual function for h-value calibration.
    
    Args:
        h: Array [h_porous, h_outlet] to optimize
        params: ThermalParams with target values
    
    Returns:
        Residuals [Tcpu_error, Q1_error]
    """
    # Update h-values
    params.h_porous = h[0]
    params.h_outlet = h[1]
    
    # Run model
    result = coldplate_2zone_model(params)
    
    # Compute residuals
    F = np.zeros(2)
    F[0] = result.Tcpu - params.Tcpu_target      # Match CPU temp
    F[1] = result.Q[0] - params.Q1_target        # Match heat split
    
    return F


# === Calibration ===
print("\n=== Starting Calibration ===")
print("Target: Tcpu = {:.1f} K, Q_porous = {:.1f} W\n".format(Tcpu_CFD, Q1_CFD))

# Initial guess
h0 = np.array([2.75e4, 1500.0])  # [h_porous, h_outlet]

# Solve for h-values
h_calibrated = fsolve(calibration_residuals, h0, args=(params,), 
                     full_output=False, xtol=1e-8)

print("Calibration complete!")
print(f"  h_porous = {h_calibrated[0]:.2e} W/m²-K")
print(f"  h_outlet = {h_calibrated[1]:.2e} W/m²-K")

# === Verify calibrated model ===
params.h_porous = h_calibrated[0]
params.h_outlet = h_calibrated[1]
result = coldplate_2zone_model(params)

print("\n=== CFD vs 1D Model Comparison ===")
print(f"CPU Temp:  CFD = {Tcpu_CFD:.1f} K  |  1D = {result.Tcpu:.1f} K  |  Error = {result.Tcpu - Tcpu_CFD:+.1f} K")
print(f"Outlet:    CFD = {Tout_CFD:.1f} K  |  1D = {result.Tout:.1f} K  |  Error = {result.Tout - Tout_CFD:+.1f} K")
print(f"\nHeat Split:")
print(f"  Porous = {result.Q[0]:.1f} W (CFD: {Q1_CFD:.1f} W)")
print(f"  Outlet = {result.Q[1]:.1f} W (CFD: {Q2_CFD:.1f} W)")

print("\n=== Calibrated Parameters ===")
print(f"h_porous = {h_calibrated[0]:.2e} W/m²-K")
print(f"h_outlet = {h_calibrated[1]:.2e} W/m²-K")
print("\nThese values can be used in coldplate_thermal_analysis.py")
print("for parametric design studies.")
