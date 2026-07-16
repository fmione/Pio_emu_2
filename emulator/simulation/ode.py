import numpy as np
from scipy.integrate import solve_ivp


def function_simulation(ts0, Xo0, u0, THs, D0=None):
    if D0 is None:
        D0 = {"time_feed": [], "Feed_profile": []}

    TH1 = np.array(THs[str(int(u0[1]))])

    ts_start = ts0[0]
    ts_end = ts0[-1]

    time_feed_all = np.array(D0["time_feed"])
    Feed_profile_all = np.array(D0["Feed_profile"])

    if len(time_feed_all) == 0:
        t_u_pulse = np.array([])
        uu_pulse = np.array([])
    else:
        mask = (time_feed_all >= ts_start) & (time_feed_all <= ts_end)
        t_u_pulse = np.round(time_feed_all[mask], decimals=6)
        uu_pulse = Feed_profile_all[mask]

    t_u = np.unique(t_u_pulse)

    if len(t_u) == 0:
        t_u = np.array([ts_start, ts_end])
        uu = np.array([0, 0])
    else:
        if ts_start < t_u[0]:
            t_u = np.append(ts_start, t_u)
        if ts_end > t_u[-1]:
            t_u = np.append(t_u, ts_end)

    Xo1 = Xo0.copy()
    if ts0[0] < 1e-6:
        Xo1[0] = Xo1[0] * (0.5 + TH1[-2])
        Xo1[1] = Xo1[1] * (0.5 + TH1[-1])

    tt = np.array(ts_start)
    yy = np.array([Xo1])
    yy = yy.transpose()

    ni = 0

    for i in t_u[:-1]:
        ts1 = np.linspace(t_u[ni], t_u[ni + 1], 40 + 1)
        V_old = Xo1[3]

        if i in t_u_pulse:
            index_u_pulse = int(np.where(t_u_pulse == t_u[ni])[0][0])
            Xo1[0] = Xo1[0] / (1 + uu_pulse[index_u_pulse] * 1e-3 / Xo1[3])
            Xo1[1] = Xo1[1] + uu_pulse[index_u_pulse] * 1e-3 * u0[0] / Xo1[3]
            Xo1[2] = Xo1[2] / (1 + uu_pulse[index_u_pulse] * 1e-3 / Xo1[3])

        V_new = Xo1[3]

        Xo1 = Xo1 * V_old / V_new
        Xo1[3] = V_new

        t, y = intM(ts1, Xo1, u0, TH1)
        Xo1 = y[:, -1].copy()

        tt = np.append(tt, t[1:])
        yy = np.append(yy, y[:, 1:], axis=1)
        ni = ni + 1

    return tt, yy.transpose()


def odeFB(t, Xo, THo, u):
    X = np.maximum(np.array(Xo, dtype=float), 1e-9)
    TH = np.array(THo, dtype=float)

    Xv, S, E, V, e = X[0], X[1], X[2], X[3], X[4]

    mu_max_f = TH[0]
    mu_max_r = TH[0] * 1 / TH[1]
    mu_max_e = TH[2]

    Ys_f = TH[3]
    Ys_r = TH[4]
    Ye_c = TH[5]
    Ye_p = TH[6]

    S_r = TH[7]
    S_e = TH[8]

    Ks_f = TH[9]
    Ks_r = TH[10]
    Ke = TH[11]

    t_lag = TH[12]

    act = (1 + np.tanh((e - 0.9) / 0.1)) / 2
    f_r = (1 + np.tanh((S - S_r) / 0.05)) / 2
    f_e = (1 + np.tanh((S - S_e) / 0.05)) / 2

    mu_f = act * mu_max_f * S / (S + Ks_f) * f_r
    mu_r = act * mu_max_r * S / (S + Ks_r) * (1 - f_r)
    mu_e = act * mu_max_e * E / (E + Ke) * (1 - f_e)

    D = 0

    dXv = (mu_f + mu_r + mu_e) * Xv - D * Xv
    dS = -(mu_f / Ys_f + mu_r / Ys_r) * Xv - D * S
    dE = (mu_f / Ys_f * Ye_p - mu_e / Ye_c) * Xv - D * E
    dV = D * V
    de = 1 / (t_lag + 1e-6) * (1 - e)

    return np.array([dXv, dS, dE, dV, de])


def intM(ts0, Xo0, u0, TH0):
    tspan = np.array([ts0[0], ts0[-1]])
    Xo1 = list(Xo0)

    sol = solve_ivp(
        lambda t, y: odeFB(t, y, TH0, u0),
        tspan,
        Xo1,
        method="BDF",
        rtol=1e-4,
        atol=1e-3,
        t_eval=ts0,
    )
    y_interm = sol.y
    y_interm[y_interm < 0] = 0
    return sol.t, y_interm.copy()
