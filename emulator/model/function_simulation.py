import numpy as np
from scipy.integrate import solve_ivp


def function_simulation(ts0, Xo0, u0, THs, D0={}):
    """
    Simulate the fed-batch bioreactor ODE model over a time interval.

    The simulation handles discrete feed pulses at specified times,
    applying dilution effects and integrating the ODE system between pulses.

    Parameters
    ----------
    ts0 : array_like
        [start_time, end_time] in hours.
    Xo0 : array_like
        Initial state vector [Xv, S, E, V, e].
    u0 : array_like
        [glucose_feed_concentration, reactor_index, number_of_reactors].
    THs : dict
        Dictionary of parameter sets keyed by reactor index string.
    D0 : dict
        Design dict with 'time_feed', 'Feed_profile', and 'time_sample' keys.

    Returns
    -------
    tt : ndarray
        Time points of the simulation.
    yy : ndarray
        State trajectories (each row is a time point, columns are species).
    """
    TH1 = np.array(THs[str(int(u0[1]))])

    ts_start = ts0[0]
    ts_end = ts0[-1]

    time_feed_all = np.array(D0['time_feed'])
    t_u_pulse = np.round(time_feed_all[(time_feed_all >= ts_start) & (time_feed_all <= ts_end)], decimals=6)
    Feed_profile_all = np.array(D0['Feed_profile'])
    uu_pulse = Feed_profile_all[(time_feed_all >= ts_start) & (time_feed_all <= ts_end)]

    # time_sample_all = np.array(D0['time_sample'])
    # t_u_sample = np.round(time_sample_all[(time_sample_all >= ts_start) & (time_sample_all <= ts_end)], decimals=6)

    time_u_concat = t_u_pulse

    t_u = np.unique(time_u_concat)

    if len(t_u) == 0:
        t_u = np.array([ts_start, ts_end])
        # uu = np.array([0, 0])

    else:
        if ts_start < t_u[0]:
            t_u = np.append(ts_start, t_u)
        if ts_end > t_u[-1]:
            t_u = np.append(t_u, ts_end)

    Xo1 = Xo0.copy()
    # Apply initial condition correction using calibration parameters
    if ts0[0] < 1e-6:
        Xo1[0] = Xo1[0] * (0.5 + TH1[-2])
        Xo1[1] = Xo1[1] * (0.5 + TH1[-1])

    tt = np.array(ts_start)
    yy = np.array([Xo1])
    yy = yy.transpose()

    ni = 0

    # Step through each feed interval, apply pulse then integrate
    for i in t_u[:-1]:
        ts1 = np.linspace(t_u[ni], t_u[ni + 1], 40 + 1)
        # V_old = Xo1[3]
        if i in t_u_pulse:
            index_u_pulse = int(np.where(t_u_pulse == t_u[ni])[0][0])
            # Pulse addition: concentrate feed, dilute biomass & ethanol, add glucose
            Xo1[0] = Xo1[0] / (1 + uu_pulse[index_u_pulse] * 1e-3 / Xo1[3])
            Xo1[1] = Xo1[1] + uu_pulse[index_u_pulse] * 1e-3 * u0[0] / Xo1[3]
            Xo1[2] = Xo1[2] / (1 + uu_pulse[index_u_pulse] * 1e-3 / Xo1[3])

        # V_new = Xo1[3]

        # Volume correction: dilute all species
        # Xo1 = Xo1 * V_old / V_new
        # Xo1[3] = V_new

        t, y = intM(ts1, Xo1, u0, TH1)
        Xo1 = y[:, -1].copy()

        tt = np.append(tt, t[1:])
        yy = np.append(yy, y[:, 1:], axis=1)
        ni = ni + 1

    return tt, yy.transpose()


def odeFB(t, Xo, THo, u):
    """
    Fed-batch ODE right-hand side with 5 states and 3 metabolic pathways.

    States:  Xv (biomass), S (glucose), E (ethanol), V (volume), e (induction)
    Pathways: fermentation (fast growth), respiration (slow growth), ethanol consumption.

    Switching functions (tanh-based) control pathway selection based on
    substrate and ethanol thresholds.
    """
    X = Xo.copy()
    TH = THo.copy()
    X = np.maximum(X, 1e-9)

    Xv = X[0]
    S = X[1]
    E = X[2]
    V = X[3]
    e = X[4]
    Si= X[5]

    # Kinetic parameters from TH vector
    qs_max = TH[0]
    mu_max_f = TH[1]
    mu_max_r = TH[1] * 1 / TH[2]
    mu_max_e = TH[3]

    Ys_f = TH[4]
    Ys_r = TH[5]
    Ye_c = TH[6]
    Ye_p = TH[7]

    S_r = TH[8]
    S_e = TH[9]

    Ks = TH[10]
    Ke = TH[11]

    t_lag = TH[12]

    # Switching functions (sigmoidal) for pathway selection
    act = (1 + np.tanh((e - 0.9) / 0.1)) / 2
    f_r = (1 + np.tanh((Si - S_r) / 0.001)) / 2
    f_e = (1 + np.tanh((Si - S_e) / 0.001)) / 2

    # Specific growth rates for each pathway
    q_s = qs_max * S / (S + Ks)
    
    q_f = (act) * mu_max_f * Si/(Si+0.01) * f_r   #IMPROVE K
    q_r = (act) * mu_max_r * Si/(Si+0.01) * (1 - f_r)
    q_e = (act) * mu_max_e * E / (E + Ke) * (1 - f_e)
    
    mu = q_r * Ys_r + q_f * Ys_f + q_e * Ye_c

    D = 0

    # Material balances
    dXv = mu *  Xv - D * Xv
    dS = -q_s * Xv - D * S
    dE = (q_f*Ye_p - q_e )  * Xv - D * E
    
    dSi = q_s - q_r - q_f - mu * Si

    dV = D * V

    de = 1 / (t_lag + 1e-6) * (1 - e)
    dX = np.array([dXv, dS, dE, dV, de, dSi])
    return dX


def intM(ts0, Xo0, u0, TH0):
    """
    Integrate the ODE system over a time interval using the BDF solver.

    Returns time points and state matrix with negative values clamped to zero.
    """
    tspan = np.array([ts0[0], ts0[-1]])
    Xo1 = Xo0.tolist().copy()

    sol = solve_ivp(lambda t, y: odeFB(t, y, TH0, u0), tspan, Xo1,
                    method="BDF", rtol=1e-4, atol=1e-3, t_eval=ts0)
    y_interm = sol.y
    y_interm[y_interm < 0] = 0
    y_return = y_interm.copy()

    return sol.t, y_return