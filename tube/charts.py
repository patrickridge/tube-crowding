"""Plotly charts for both pages."""

from __future__ import annotations

import math

import plotly.graph_objects as go

from tube.models import SLOT_MINUTES, slot_label

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREY = "#b4b2a9"
INK = "#0b0b0b"
MUTED = "#6b6a65"
GRID = "#e1e0d9"
RED = "#d03b3b"

Y_TITLE = "% of busiest time"
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


def _time_axis(fig: go.Figure, start: int = 0, step: int = 6) -> None:
    ticks = list(range(start, 25, step))  # sparse enough to stay horizontal on a phone
    fig.update_xaxes(
        title="Time of day",
        range=[start, 24],
        tickvals=ticks,
        ticktext=[f"{h:02d}:00" for h in ticks],
        gridcolor=GRID,
        title_font=dict(color=MUTED),
        tickfont=dict(color=MUTED),
        tickangle=0,
        fixedrange=True,  # stop accidental zooming when scrolling on a phone
    )


def day_profile(values: list[float], live: tuple[int, float] | None = None) -> go.Figure:
    """Typical crowding through one day (smoothed); optionally the live reading as a dot."""
    fig = go.Figure()
    fig.add_scatter(
        x=[_hours(s) for s in range(len(values))],
        y=_pct(values),
        name="Typical",
        mode="lines",
        line=dict(color=BLUE, width=2.5),
        customdata=[slot_label(s) for s in range(len(values))],
        hovertemplate="%{customdata}: %{y:.0f}%<extra></extra>",
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
    _base_layout(fig, height=280)
    fig.update_layout(showlegend=live is not None)
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


def train_day(people: list[float], seats: int, capacity: int, slot: int) -> go.Figure:
    """People on each train leaving your station through the day, against seats and full."""
    x = [_hours(s) for s in range(len(people))]
    fig = go.Figure()
    fig.add_scatter(
        x=x,
        y=people,
        mode="lines",
        line=dict(color=BLUE, width=2.5),
        customdata=[slot_label(s) for s in range(len(people))],
        hovertemplate="%{customdata}: about %{y:.0f} people<extra></extra>",
        showlegend=False,
    )
    fig.add_scatter(
        x=[_hours(slot)],
        y=[people[slot]],
        mode="markers",
        marker=dict(color=INK, size=11, line=dict(color="white", width=2)),
        hoverinfo="skip",
        showlegend=False,
    )
    for value, label, colour in ((seats, "Seats", GREY), (capacity, "Full", RED)):
        fig.add_hline(
            y=value,
            line=dict(color=colour, width=1.5, dash="dash"),
            annotation=dict(text=label, font=dict(color=colour), xanchor="left"),
            annotation_position="top left",
        )
    _base_layout(fig, height=260)
    _time_axis(fig, start=5, step=4)
    top = max([capacity, *[p for p in people if not math.isnan(p)]]) * 1.1
    fig.update_yaxes(
        title="People on the train",
        range=[0, top],
        gridcolor=GRID,
        fixedrange=True,
        title_font=dict(color=MUTED),
        tickfont=dict(color=MUTED),
    )
    return fig
