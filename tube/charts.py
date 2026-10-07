"""Plotly charts. Values come in as a fraction of the station's busiest time."""

from __future__ import annotations

import math

import plotly.graph_objects as go

from tube.models import DAYS, SLOT_MINUTES, slot_label

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREY = "#b4b2a9"
INK = "#0b0b0b"
MUTED = "#6b6a65"
GRID = "#e1e0d9"
# Single-hue sequential ramp (light = quiet, dark = busy) for the heatmap.
BLUE_RAMP = ["#eef4fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

Y_TITLE = "% of busiest time"
DAY_NAMES = dict(zip(DAYS, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], strict=True))
CONFIG = {"displayModeBar": False, "responsive": True}


def _hours(slot: int) -> float:
    return slot * SLOT_MINUTES / 60


def _pct(values: list[float]) -> list[float]:
    return [v * 100 for v in values]


def _base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13, color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color=MUTED)),
    )
    return fig


def _time_axis(fig: go.Figure, title: str = "Time of day") -> None:
    ticks = list(range(0, 25, 6))  # sparse enough to stay horizontal on a phone
    fig.update_xaxes(
        title=title,
        range=[0, 24],
        tickvals=ticks,
        ticktext=[f"{h:02d}:00" for h in ticks],
        gridcolor=GRID,
        title_font=dict(color=MUTED),
        tickfont=dict(color=MUTED),
        tickangle=0,
        fixedrange=True,  # stop accidental zooming when scrolling on a phone
    )


def day_profile(raw: list[float], smoothed: list[float], live: tuple[int, float] | None = None) -> go.Figure:
    """Typical crowding through one day; optionally the live reading as a marker."""
    slots = list(range(len(raw)))
    x = [_hours(s) for s in slots]
    labels = [slot_label(s) for s in slots]
    fig = go.Figure()
    fig.add_scatter(
        x=x,
        y=_pct(raw),
        name="Raw 15-min",
        mode="lines",
        line=dict(color=GREY, width=1, shape="hv"),
        customdata=labels,
        hovertemplate="%{customdata}: %{y:.0f}%<extra>raw</extra>",
    )
    fig.add_scatter(
        x=x,
        y=_pct(smoothed),
        name="Typical",
        mode="lines",
        line=dict(color=BLUE, width=2.5),
        customdata=labels,
        hovertemplate="%{customdata}: %{y:.0f}%<extra>typical</extra>",
    )
    if live is not None:
        slot, value = live
        fig.add_scatter(
            x=[_hours(slot)],
            y=[value * 100],
            name="Live now",
            mode="markers",
            marker=dict(color=ORANGE, size=12, line=dict(color="white", width=2)),
            hovertemplate="Live: %{y:.0f}%<extra></extra>",
        )
    _base_layout(fig, height=320)
    fig.update_layout(hovermode="x unified")
    _time_axis(fig)
    fig.update_yaxes(
        title=Y_TITLE,
        ticksuffix="%",
        rangemode="tozero",
        gridcolor=GRID,
        fixedrange=True,
        title_font=dict(color=MUTED),
        tickfont=dict(color=MUTED),
    )
    return fig


def week_heatmap(grid: dict[str, list[float]]) -> go.Figure:
    """Day-of-week by time-of-day heatmap, Monday at the top."""
    days = list(grid)
    n = len(next(iter(grid.values())))
    fig = go.Figure(
        go.Heatmap(
            z=[_pct(grid[d]) for d in days],
            x=[_hours(s) + SLOT_MINUTES / 120 for s in range(n)],  # centre each cell in its band
            y=[DAY_NAMES[d] for d in days],
            customdata=[[slot_label(s) for s in range(n)] for _ in days],
            colorscale=[[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)],
            zmin=0,
            xgap=0,
            ygap=2,
            colorbar=dict(
                ticksuffix="%",
                thickness=10,
                len=0.9,
                outlinewidth=0,
            ),
            hovertemplate="%{y} %{customdata}: %{z:.0f}%<extra></extra>",
        )
    )
    _base_layout(fig, height=300)
    _time_axis(fig)
    fig.update_yaxes(autorange="reversed", fixedrange=True, tickfont=dict(color=MUTED))
    return fig


def window_bars(slots: list[int], values: list[float], best_slot: int, latest_slot: int) -> go.Figure:
    """Each departure slot in the window; the recommended one in blue, the latest in orange."""
    colours = [BLUE if s == best_slot else ORANGE if s == latest_slot else GREY for s in slots]
    labels = [slot_label(s) for s in slots]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=_pct(values),
            marker=dict(color=colours, cornerradius=4),
            # Only label the recommended and latest bars.
            text=[
                f"{v * 100:.0f}%" if s in (best_slot, latest_slot) else ""
                for s, v in zip(slots, values, strict=True)
            ],
            textposition="outside",
            textfont=dict(color=INK, size=13),
            cliponaxis=False,
            hovertemplate="Leave %{x}: %{y:.0f}%<extra></extra>",
        )
    )
    _base_layout(fig, height=260)
    fig.update_layout(bargap=0.25, showlegend=False)
    step = math.ceil(len(labels) / 6)  # at most ~6 labels so they stay horizontal on a phone
    fig.update_xaxes(
        title="Departure time",
        type="category",
        tickvals=labels[::step],
        tickangle=0,
        fixedrange=True,
        title_font=dict(color=MUTED),
        tickfont=dict(color=MUTED),
    )
    fig.update_yaxes(
        title=Y_TITLE,
        ticksuffix="%",
        rangemode="tozero",
        gridcolor=GRID,
        fixedrange=True,
        title_font=dict(color=MUTED),
        tickfont=dict(color=MUTED),
    )
    return fig
