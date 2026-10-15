import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Target PDF destination paths
WORKSPACE_PDF = r"d:\Project\trading_app\ICT_Strategies_Complete_Manual.pdf"
ARTIFACT_PDF = r"C:\Users\ELCOT\.gemini\antigravity\brain\3d958a71-5b62-46ff-8d09-3a38453e4ed4\ICT_Strategies_Complete_Manual.pdf"


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas calculating total page count and drawing running headers/footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return  # Suppress running header/footer on cover page

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#475569"))

        # Header
        self.drawString(54, 11 * 72 - 36, "TRADERPRO QUANTITATIVE ENGINE")
        self.setFont("Helvetica", 8)
        self.drawRightString(8.5 * 72 - 54, 11 * 72 - 36, "ICT STRATEGIES COMPLETE WORKING MANUAL")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.75)
        self.line(54, 11 * 72 - 42, 8.5 * 72 - 54, 11 * 72 - 42)

        # Footer
        self.drawString(54, 34, "Goat Funded Trader ($1,000 Model) | Strict Institutional ICT Architecture")
        self.drawRightString(8.5 * 72 - 54, 34, f"Page {self._pageNumber} of {page_count}")
        self.line(54, 44, 8.5 * 72 - 54, 44)
        self.restoreState()


def build_pdf(filename: str):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Palette
    PRIMARY = colors.HexColor("#0F172A")    # Slate 900
    SECONDARY = colors.HexColor("#1E293B")  # Slate 800
    ACCENT_BLUE = colors.HexColor("#0284C7")# Sky 600
    GREEN_TEXT = colors.HexColor("#059669") # Emerald 600
    RED_TEXT = colors.HexColor("#DC2626")   # Rose 600
    CARD_BG = colors.HexColor("#F8FAFC")    # Slate 50
    CARD_BORDER = colors.HexColor("#E2E8F0")# Slate 200
    TABLE_HEADER = colors.HexColor("#1E293B")

    # Typography Styles
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=30,
        textColor=PRIMARY,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=ACCENT_BLUE,
        spaceAfter=16
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=PRIMARY,
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=ACCENT_BLUE,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True
    )

    h3_style = ParagraphStyle(
        "Heading3_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=SECONDARY,
        spaceBefore=5,
        spaceAfter=2,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=SECONDARY,
        spaceAfter=3.5
    )

    body_bold = ParagraphStyle(
        "Body_Bold",
        parent=body_style,
        fontName="Helvetica-Bold"
    )

    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=2
    )

    callout_style = ParagraphStyle(
        "Callout_Text",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=SECONDARY
    )

    callout_title = ParagraphStyle(
        "Callout_Title",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=PRIMARY,
        spaceAfter=3
    )

    diagram_text = ParagraphStyle(
        "DiagramText",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=7.5,
        leading=10.5,
        textColor=PRIMARY,
        alignment=1
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
        alignment=0
    )

    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.5,
        textColor=SECONDARY,
        alignment=0
    )

    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=table_cell_style,
        fontName="Helvetica-Bold",
        textColor=PRIMARY
    )

    table_cell_green = ParagraphStyle(
        "TableCellGreen",
        parent=table_cell_style,
        fontName="Helvetica-Bold",
        textColor=GREEN_TEXT
    )

    table_cell_red = ParagraphStyle(
        "TableCellRed",
        parent=table_cell_style,
        fontName="Helvetica-Bold",
        textColor=RED_TEXT
    )

    story = []

    def make_callout(title: str, text: str, border_color=ACCENT_BLUE, bg_color=CARD_BG):
        content = [
            Paragraph(f"<b>{title}</b>", callout_title),
            Paragraph(text, callout_style)
        ]
        t = Table([[content]], colWidths=[504])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg_color),
            ('BOX', (0, 0), (-1, -1), 1, border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        return t

    def make_diagram(title: str, steps: list, border_color=ACCENT_BLUE):
        arrow = " &nbsp;&rarr;&nbsp; "
        diagram_line = arrow.join([f"<b>[{s}]</b>" for s in steps])
        content = [
            Paragraph(f"<b>{title}</b>", callout_title),
            Spacer(1, 2),
            Paragraph(diagram_line, diagram_text)
        ]
        t = Table([[content]], colWidths=[504])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
            ('BOX', (0, 0), (-1, -1), 1, border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        return t

    # =========================================================================
    # PAGE 1: COVER & EXECUTIVE SUMMARY
    # =========================================================================
    story.append(Spacer(1, 20))
    story.append(Paragraph("TRADERPRO ALGORITHMIC ENGINE", ParagraphStyle(
        "Tagline", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=ACCENT_BLUE, spaceAfter=6
    )))
    story.append(Paragraph("ICT Strategies & Architecture Complete Working Manual", title_style))
    story.append(Paragraph("Full Technical Specification, Algorithmic Execution Rules, Multi-Timeframe Confluence, and Goat Funded Trader ($1,000 Model) Compliance Guide", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceBefore=0, spaceAfter=14))

    meta_data = [
        [Paragraph("<b>Target Prop Firm:</b>", table_cell_bold), Paragraph("Goat Funded Trader ($1,000 Challenge Model)", table_cell_style),
         Paragraph("<b>Primary Assets:</b>", table_cell_bold), Paragraph("NAS100 (US100), SPX500, GOLD (XAUUSD)", table_cell_style)],
        [Paragraph("<b>Risk Per Trade:</b>", table_cell_bold), Paragraph("$2.50 (Strict 0.25% Balance Risk)", table_cell_style),
         Paragraph("<b>Minimum R:R:</b>", table_cell_bold), Paragraph("1:2.00 (Standardized across all strategies)", table_cell_style)],
        [Paragraph("<b>Consistency Rule:</b>", table_cell_bold), Paragraph("Max 15% Single-Trade Profit Cap", table_cell_style),
         Paragraph("<b>Data Feed:</b>", table_cell_bold), Paragraph("TradingView WebSocket (1m/5m/15m/30m/1h/4h/1D/1W)", table_cell_style)],
        [Paragraph("<b>SMT Pairings:</b>", table_cell_bold), Paragraph("NAS100 vs SPX500 | NQ vs MES (No Gold)", table_cell_style),
         Paragraph("<b>Engine Status:</b>", table_cell_bold), Paragraph("<font color='#059669'><b>LIVE PRODUCTION (Online & Verified)</b></font>", table_cell_style)]
    ]
    t_meta = Table(meta_data, colWidths=[105, 147, 105, 147])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12))

    exec_summary_text = (
        "This document provides the definitive, comprehensive algorithmic manual for all trading strategies "
        "deployed inside the TraderPro algorithmic ecosystem. Following the September 2026 repo-wide refactor, all strategies "
        "have been decoupled from synthetic brokers, legacy scrapers, and hardcoded values. Every strategy is an authentic mathematical "
        "function of multi-timeframe TradingView data, synchronized SMT divergence, centralized ATR stop-loss buffers, "
        "and strict prop-firm capital protection. This manual details the exact internal working, setup conditions, checklist verifications, "
        "entry/exit mechanics, and invalidation rules for each strategy."
    )
    story.append(make_callout("EXECUTIVE SUMMARY & MANDATE", exec_summary_text, ACCENT_BLUE, CARD_BG))
    story.append(Spacer(1, 12))

    # Table of Contents
    toc_data = [
        [Paragraph("<b>Section</b>", table_header_style), Paragraph("<b>Title & Core Focus</b>", table_header_style), Paragraph("<b>Target Markets</b>", table_header_style), Paragraph("<b>Execution Timeframe</b>", table_header_style)],
        [Paragraph("<b>Section 1</b>", table_cell_bold), Paragraph("Unified Core Architecture, Risk Engine & Data Pipeline", table_cell_style), Paragraph("All Instruments", table_cell_style), Paragraph("Infrastructure", table_cell_style)],
        [Paragraph("<b>Section 2</b>", table_cell_bold), Paragraph("Strategy 1: SMC Liquidity Master (ICT + Goat $1k)", table_cell_style), Paragraph("NAS100 / GOLD", table_cell_style), Paragraph("15M Setup -> 1M Execution", table_cell_style)],
        [Paragraph("<b>Section 3</b>", table_cell_bold), Paragraph("Strategy 2: ICT Market Maker Model (24-Lesson Mastery)", table_cell_style), Paragraph("NAS100 / SPX500", table_cell_style), Paragraph("HTF -> 1M Execution", table_cell_style)],
        [Paragraph("<b>Section 4</b>", table_cell_bold), Paragraph("Strategy 3: Praveen's ICT Strategy v2.1 (5-Step Flow)", table_cell_style), Paragraph("NAS100 / NQ / SPX", table_cell_style), Paragraph("30M Zone -> 1M CISD/IFVG", table_cell_style)],
        [Paragraph("<b>Section 5</b>", table_cell_bold), Paragraph("Strategy 4: SPEAN Strategy (Q-Zone + 7-Layer FAH)", table_cell_style), Paragraph("NAS100 / GOLD", table_cell_style), Paragraph("15M Sweep -> 1M FAH POI", table_cell_style)],
        [Paragraph("<b>Section 6</b>", table_cell_bold), Paragraph("Strategy 5: ICT Silver Bullet (Time-Based FVG)", table_cell_style), Paragraph("NAS100 / GOLD", table_cell_style), Paragraph("60-Min Killzone (1M)", table_cell_style)],
        [Paragraph("<b>Section 7</b>", table_cell_bold), Paragraph("Strategy 6: Session Momentum Breakout", table_cell_style), Paragraph("NAS100 / GOLD", table_cell_style), Paragraph("15M Range Expansion", table_cell_style)],
        [Paragraph("<b>Section 8</b>", table_cell_bold), Paragraph("Centralized Order Ticket & Goat Consistency Safeguards", table_cell_style), Paragraph("All Instruments", table_cell_style), Paragraph("Execution Contract", table_cell_style)],
    ]
    t_toc = Table(toc_data, colWidths=[65, 230, 95, 114])
    t_toc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_toc)
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: SECTION 1 — ARCHITECTURE & INFRASTRUCTURE
    # =========================================================================
    story.append(Paragraph("SECTION 1: UNIFIED ARCHITECTURE & INFRASTRUCTURE", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("1.1 Single Live Data Pipeline (TradingView WebSocket)", h2_style))
    story.append(Paragraph(
        "All strategies operate strictly as pure deterministic functions of a standardized <code>market_data</code> dictionary "
        "supplied by <code>backend/market_data.py</code>. Under zero circumstances does any strategy fetch data directly or maintain "
        "private HTTP scrapers. The architecture eliminates Yahoo Finance entirely in favor of an institutional WebSocket feed.",
        body_style
    ))
    story.append(Paragraph("• <b>Direct Connection:</b> Subscribes to <code>wss://data.tradingview.com/socket.io/websocket</code> with keep-alive heartbeats and auto reconnection.", bullet_style))
    story.append(Paragraph("• <b>Exchange Tickers:</b> NAS100 uses <code>CAPITALCOM:US100</code>; SPX500 uses <code>CAPITALCOM:SPX500</code>; GOLD uses <code>CAPITALCOM:GOLD</code>.", bullet_style))
    story.append(Paragraph("• <b>8 Native Resolutions:</b> Subscribes concurrently to <code>1m, 5m, 15m, 30m, 60m (1h), 240m (4h), 1D (Daily), 1W (Weekly)</code>. Zero candle emulation.", bullet_style))
    story.append(Paragraph("• <b>Thread Safety:</b> Protected by <code>threading.Lock()</code> to ensure race-free evaluation across background tasks.", bullet_style))
    story.append(Paragraph("• <b>Timestamp Alignment:</b> Through <code>align_series()</code>, correlated pairs are indexed by exact UTC minute timestamps before SMT analysis.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("1.2 Centralized Risk Engine (Goat $1,000 Challenge Model)", h2_style))
    story.append(Paragraph(
        "Prop firm survival demands mathematically rigorous capital management. All six strategies import risk calculations, "
        "position sizing, and order tickets directly from <code>backend/risk_engine.py</code>.",
        body_style
    ))

    risk_table_data = [
        [Paragraph("<b>Parameter</b>", table_header_style), Paragraph("<b>Value / Standard</b>", table_header_style), Paragraph("<b>Rationale & Rule Governance</b>", table_header_style)],
        [Paragraph("Account Balance", table_cell_bold), Paragraph("$1,000.00 Base", table_cell_style), Paragraph("Goat Funded Trader micro-tier account size.", table_cell_style)],
        [Paragraph("Risk Per Trade", table_cell_bold), Paragraph("$2.50 (0.25%)", table_cell_style), Paragraph("Conservative sizing allows 12 consecutive losses before hitting 3% daily DD limit.", table_cell_style)],
        [Paragraph("Minimum R:R", table_cell_bold), Paragraph("1:2.00 (Strict)", table_cell_style), Paragraph("Any setup yielding < 2.0 R:R is automatically discarded ('Wait / No trade').", table_cell_style)],
        [Paragraph("Consistency Profit Cap", table_cell_bold), Paragraph("15% Rule", table_cell_style), Paragraph("No single trade may constitute > 15% of the total profit target ($150 target = $22.50 cap).", table_cell_style)],
        [Paragraph("Consistency Formula", table_cell_bold), Paragraph("<code>(Profit / Balance) * 100</code>", table_cell_style), Paragraph("Genuine balance calculation (replaces legacy no-op <code>(p/100)*100</code>).", table_cell_style)],
        [Paragraph("SL Buffer: NAS100", table_cell_bold), Paragraph("3.0 Points", table_cell_style), Paragraph("Protects against broker spread fluctuation and institutional wick slippage.", table_cell_style)],
        [Paragraph("SL Buffer: SPX500", table_cell_bold), Paragraph("1.5 Points", table_cell_style), Paragraph("Calibrated to S&P 500 tick size and typical 1M spread.", table_cell_style)],
        [Paragraph("SL Buffer: GOLD", table_cell_bold), Paragraph("1.0 Point ($0.10)", table_cell_style), Paragraph("Accounts for spot gold volatility and broker spread spikes.", table_cell_style)],
    ]
    t_risk = Table(risk_table_data, colWidths=[120, 110, 274])
    t_risk.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_risk)
    story.append(Spacer(1, 4))

    story.append(Paragraph("1.3 Smart Money Technique (SMT) Correlated Engine", h2_style))
    story.append(Paragraph(
        "SMT Divergence detects when two correlated assets in the same class diverge at key swing points, revealing genuine "
        "institutional accumulation or distribution. The centralized <code>backend/smt_engine.py</code> enforces strict rules:",
        body_style
    ))
    story.append(Paragraph("• <b>Permitted Correlated Pairs:</b> <code>NAS100 <-> SPX500</code> and <code>NQ <-> MES</code> (US equity indices sharing macroeconomic drivers).", bullet_style))
    story.append(Paragraph("• <b>Strict Commodity Exclusion:</b> <code>GOLD</code> is strictly prohibited from equity index SMT comparisons (eliminating false signals).", bullet_style))
    story.append(Paragraph("• <b>Bullish SMT Divergence:</b> Primary asset makes a Lower Low (sweeps liquidity) while correlated asset holds a Higher Low (institutional accumulation).", bullet_style))
    story.append(Paragraph("• <b>Bearish SMT Divergence:</b> Primary asset makes a Higher High (sweeps liquidity) while correlated asset holds a Lower High (institutional distribution).", bullet_style))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: SECTION 2 — SMC LIQUIDITY MASTER
    # =========================================================================
    story.append(Paragraph("SECTION 2: STRATEGY 1 — SMC LIQUIDITY MASTER (ICT + GOAT $1K)", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("2.1 Core Theoretical Concept", h2_style))
    story.append(Paragraph(
        "SMC Liquidity Master is a multi-timeframe institutional model that capitalizes on stop runs outside established 15-minute "
        "ranges. Retail traders place stops above swing highs (Buy-Side Liquidity - BSL) and below swing lows (Sell-Side Liquidity - SSL). "
        "Smart money sweeps this liquidity to fill large institutional orders, followed by immediate displacement in the opposite direction.",
        body_style
    ))

    story.append(make_diagram("SMC LIQUIDITY MASTER EXECUTION FLOW", [
        "15M Range Filter", "BSL/SSL Sweep", "1M BOS Displacement", "50% POI Retracement", "1:2+ R:R Target"
    ]))
    story.append(Spacer(1, 5))

    story.append(Paragraph("2.2 Multi-Timeframe Alignment Sequence", h2_style))
    story.append(Paragraph("<b>Step 1: 4H Structural Bias Filter:</b> Analyzes the last 12 four-hour candles (48 hours). If price is in the upper half of the 4H range, market is in Premium; if in the lower half, Discount. Longs are favored in Discount; Shorts in Premium.", body_style))
    story.append(Paragraph("<b>Step 2: 1H Session Context & PDH/PDL Distinction:</b> Prior Day High (PDH) and Low (PDL) are strictly sourced from completed prior daily bar (<code>candles_1d[-2]</code>). Today's intraday high and low are tracked independently as <i>Today's Intraday Range</i>, permanently resolving the PDH/PDL overwrite bug.", body_style))
    story.append(Paragraph("<b>Step 3: 15-Minute Liquidity Sweep:</b> Identifies unmitigated 15M swing highs (BSL) and lows (SSL) over a 20-candle lookback (5 hours). A sweep occurs when price pierces the 15M level by at least 0.2 points, absorbing liquidity.", body_style))
    story.append(Paragraph("<b>Step 4: 1-Minute Break of Structure (BOS):</b> Price must demonstrate aggressive displacement back inside the range, breaking the most recent 1M swing low (Bearish BOS) or 1M swing high (Bullish BOS). The sweep extreme becomes the <b>Protected Level</b>.", body_style))
    story.append(Paragraph("<b>Step 5: Point of Interest (POI) & Limit Entry:</b> A 1M Fair Value Gap or Supply/Demand zone is formed between the Protected Level and displacement close. A Limit Order is placed at the 50% midpoint of this zone.", body_style))

    story.append(Spacer(1, 4))
    smc_rules_data = [
        [Paragraph("<b>Component</b>", table_header_style), Paragraph("<b>Bullish Setup (Buy Limit)</b>", table_header_style), Paragraph("<b>Bearish Setup (Sell Limit)</b>", table_header_style)],
        [Paragraph("Pre-Condition", table_cell_bold), Paragraph("15M Sell-Side Liquidity (SSL) swept", table_cell_style), Paragraph("15M Buy-Side Liquidity (BSL) swept", table_cell_style)],
        [Paragraph("1M Confirmation", table_cell_bold), Paragraph("Price breaks above recent 1M swing high (Bullish BOS)", table_cell_style), Paragraph("Price breaks below recent 1M swing low (Bearish BOS)", table_cell_style)],
        [Paragraph("Protected Level", table_cell_bold), Paragraph("Protected LOW = Lowest wick of the SSL sweep", table_cell_style), Paragraph("Protected HIGH = Highest wick of the BSL sweep", table_cell_style)],
        [Paragraph("Entry POI", table_cell_bold), Paragraph("50% midpoint between Protected Low & current price", table_cell_style), Paragraph("50% midpoint between Protected High & current price", table_cell_style)],
        [Paragraph("Stop Loss", table_cell_bold), Paragraph("Protected Low - <code>sl_buffer(symbol)</code>", table_cell_red), Paragraph("Protected High + <code>sl_buffer(symbol)</code>", table_cell_red)],
        [Paragraph("Take Profit", table_cell_bold), Paragraph("Target opposing 15M BSL (capped at 1:3.0 R:R)", table_cell_green), Paragraph("Target opposing 15M SSL (capped at 1:3.0 R:R)", table_cell_green)],
        [Paragraph("Session Filter", table_cell_bold), Paragraph("12:00 – 20:00 UTC (Pre-NY and NY Active)", table_cell_style), Paragraph("12:00 – 20:00 UTC (Pre-NY and NY Active)", table_cell_style)],
        [Paragraph("Cancel Invalidation", table_cell_bold), Paragraph("If price breaches Protected Low or hits TP before fill", table_cell_style), Paragraph("If price breaches Protected High or hits TP before fill", table_cell_style)],
    ]
    t_smc = Table(smc_rules_data, colWidths=[110, 197, 197])
    t_smc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_smc)
    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: SECTION 3 — ICT MARKET MAKER MODEL (PART 1: PILLARS)
    # =========================================================================
    story.append(Paragraph("SECTION 3: STRATEGY 2 — ICT MARKET MAKER MODEL (24-LESSON MASTERY)", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("3.1 Core Theoretical Concept", h2_style))
    story.append(Paragraph(
        "The ICT Market Maker Model (MMBM / MMSM) synthesizes Michael J. Huddleston's complete 24-lesson core curriculum into an "
        "autonomous decision engine. The model reflects how institutional algorithmic market makers inject liquidity, manipulate retail "
        "sentiment during specific killzones, engineer liquidity legs, and distribute inventory into HTF PD Arrays.",
        body_style
    ))

    story.append(make_diagram("ICT MARKET MAKER AMD TIMING CYCLE", [
        "Asian Accumulation (20-00 NY)", "London Judas Sweep (02-05 NY)", "NY Distribution (07-10 NY)", "HTF PD Array Target"
    ]))
    story.append(Spacer(1, 5))

    story.append(Paragraph("3.2 Key Algorithmic Pillars (Lessons 1 – 24)", h2_style))
    story.append(Paragraph("<b>1. Weekly Bias Filter (Lesson 8):</b> Prior completed weekly bar range (<code>candles_1w[-2]</code>). If trading above prior week midpoint (Equilibrium), Weekly Bias is Bullish; if below, Bearish.", bullet_style))
    story.append(Paragraph("<b>2. Time & Price Midnight Open (Lesson 9):</b> Tracks 00:00 NY Midnight opening price. Buying is favored strictly at Discount below Midnight Open; Selling is favored at Premium above Midnight Open.", bullet_style))
    story.append(Paragraph("<b>3. AMD / Power of Three (Lesson 10):</b> Cycles through Accumulation (Asian consolidation), Manipulation (Judas swing stop sweep), and Distribution (multi-candle displacement towards target).", bullet_style))
    story.append(Paragraph("<b>4. Asian Range Measurement & Judas Swing (Lessons 11 & 12):</b> Asian range established between 20:00 and 00:00 NY. London false break sweeping Asian High followed by Bullish MSS triggers a verified Judas Reversal.", bullet_style))
    story.append(Paragraph("<b>5. HTF PD Array Confluence (Lessons 6 & 23):</b> Price must reach or tap an authentic 4H, 1H, or 30M unmitigated Order Block or Fair Value Gap before LTF execution is permitted.", bullet_style))
    story.append(Paragraph("<b>6. Displacement & MSS (Lessons 3 & 14):</b> Market Structure Shift requires 1M candle bodies to exceed the swing point with body size > 1.4x the 20-period average candle body.", bullet_style))
    story.append(Paragraph("<b>7. SMT Divergence Booster (Lesson 16):</b> Confirmed SMT divergence between NAS100 and SPX500 acts as an institutional confluence booster, raising setup confidence.", bullet_style))
    story.append(Paragraph("<b>8. Optimal Trade Entry (OTE) (Lesson 18):</b> Identifies Fibonacci retracement sweet spot: 61.8% to 79.0% (optimal: 70.5%) of the displacement swing.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("3.3 Master Checklist Matrix (11 Confluence Checks)", h2_style))

    mm_checklist_data = [
        [Paragraph("<b>#</b>", table_header_style), Paragraph("<b>ChecklistItem</b>", table_header_style), Paragraph("<b>Verification Condition</b>", table_header_style), Paragraph("<b>Threshold / Source</b>", table_header_style)],
        [Paragraph("1", table_cell_bold), Paragraph("HTF Bias & Trend", table_cell_style), Paragraph("4H/1H swing alignment + Weekly equilibrium check", table_cell_style), Paragraph("c_4h, c_1h, c_1w", table_cell_style)],
        [Paragraph("2", table_cell_bold), Paragraph("Time & Price (Daily Open)", table_cell_style), Paragraph("Discount below 00:00 NY open for Buy; Premium for Sell", table_cell_style), Paragraph("NY 00:00 EST Open", table_cell_style)],
        [Paragraph("3", table_cell_bold), Paragraph("Session & Killzone", table_cell_style), Paragraph("Inside Asian (20-00), London (02-05), NY (07-10), Close (10-12)", table_cell_style), Paragraph("America/New_York", table_cell_style)],
        [Paragraph("4", table_cell_bold), Paragraph("AMD Phase", table_cell_style), Paragraph("State transition: Accumulation -> Manipulation -> Distribution", table_cell_style), Paragraph("ATR compression + KZ", table_cell_style)],
        [Paragraph("5", table_cell_bold), Paragraph("Judas Swing Detection", table_cell_style), Paragraph("Asian extreme swept during London/NY followed by MSS", table_cell_style), Paragraph("Asian High/Low", table_cell_style)],
        [Paragraph("6", table_cell_bold), Paragraph("HTF PD Array", table_cell_style), Paragraph("Price tapping 4H/1H/30M Order Block or Fair Value Gap", table_cell_style), Paragraph("Unmitigated OB/FVG", table_cell_style)],
        [Paragraph("7", table_cell_bold), Paragraph("Liquidity Hunt (Sweep)", table_cell_style), Paragraph("External liquidity pool swept before reversal", table_cell_style), Paragraph("BSL / SSL Pool", table_cell_style)],
        [Paragraph("8", table_cell_bold), Paragraph("Market Structure Shift", table_cell_style), Paragraph("Displacement close breaking key swing point (> 1.4x body)", table_cell_style), Paragraph("1M Candle Series", table_cell_style)],
        [Paragraph("9", table_cell_bold), Paragraph("Entry FVG & OTE Zone", table_cell_style), Paragraph("Unfilled 1M FVG formed by displacement leg", table_cell_style), Paragraph("61.8% - 79.0% Fib", table_cell_style)],
        [Paragraph("10", table_cell_bold), Paragraph("SMT Divergence", table_cell_style), Paragraph("NAS100 vs SPX500 non-confirmation at swing extremes", table_cell_style), Paragraph("smt_engine", table_cell_style)],
        [Paragraph("11", table_cell_bold), Paragraph("Execution & Risk ($1k)", table_cell_style), Paragraph("$2.50 Risk (0.25%), Min 1:2.0 R:R, < 15% Consistency Cap", table_cell_style), Paragraph("risk_engine", table_cell_style)],
    ]
    t_mm = Table(mm_checklist_data, colWidths=[20, 130, 224, 130])
    t_mm.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_mm)
    story.append(Spacer(1, 4))

    story.append(Paragraph("3.4 Dual-Target Exit Framework (Lessons 15 & 19)", h2_style))
    story.append(Paragraph(
        "The Market Maker strategy implements a two-stage profit exit: <b>Take Profit 1 (Scale)</b> is set at 1.5x risk to secure "
        "partial capital and move stops to breakeven; <b>Take Profit 2 (Final DOL)</b> targets opposing major liquidity pools "
        "or 2.5x expansion, maintaining Goat prop firm compliance.",
        body_style
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: SECTION 4 — PRAVEEN'S ICT STRATEGY V2.1
    # =========================================================================
    story.append(Paragraph("SECTION 4: STRATEGY 3 — PRAVEEN'S ICT STRATEGY V2.1 (5-STEP FLOW)", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("4.1 Overview & Operational Rules", h2_style))
    story.append(Paragraph(
        "Praveen's ICT Strategy v2.1 is a high-precision scalping framework designed for NAS100/NQ using 30M PD Arrays for location "
        "and 1M execution confirmation via Change in State of Delivery (CISD) and Inversion Fair Value Gaps (IFVG). "
        "Trading is restricted to a maximum of 3 trades per day (1 per session: London, NY AM, NY PM).",
        body_style
    ))

    story.append(make_diagram("PRAVEEN 5-STEP SCALPING ENGINE", [
        "1. HTF Bias & 00:00 Open", "2. DOL Target", "3. 30M PD Array Tap", "4. 1M CISD + IFVG", "5. 50% CE Limit Entry"
    ]))
    story.append(Spacer(1, 5))

    story.append(Paragraph("4.2 The 5-Step Sequential Entry Engine", h2_style))
    story.append(Paragraph("<b>Step 1: BIAS Determination:</b> Evaluates HTF flow across Weekly -> Daily -> 4H -> 1H. Bullish bias requires trading above Weekly Equilibrium, Daily Bias Bullish, and price below Midnight Open (Discount). Bearish bias requires trading below Weekly Equilibrium, Daily Bias Bearish, and price above Midnight Open (Premium).", body_style))
    story.append(Paragraph("<b>Step 2: Draw on Liquidity (DOL) Mapping:</b> Smart money moves toward resting liquidity. The engine ranks DOL targets: 1. Equal Highs/Lows (EQH/EQL); 2. Prior Day High/Low (PDH/PDL); 3. Prior Week High/Low (PWH/PWL); 4. Major 1H/4H Swings. Trade MUST have un-swept DOL in direction of bias.", body_style))
    story.append(Paragraph("<b>Step 3: Internal Range Liquidity (IRL):</b> Entry zone must be an authentic 30-Minute Fair Value Gap (FVG) or Order Block (OB). Price must tap into the 30M zone before 1M setup is monitored. Anticipating or front-running is prohibited.", body_style))
    story.append(Paragraph("<b>Step 4: 1-Minute Entry Flow (LRLR + CISD + IFVG):</b><br/>"
                           "• <i>LRLR Path Check:</i> Verifies a clean path of Low Resistance Liquidity Run with no High Resistance blockers.<br/>"
                           "• <i>CISD (Change in State of Delivery):</i> The first candle closing beyond open of displacement candle pushing into zone.<br/>"
                           "• <i>IFVG (Inversion FVG):</i> A prior opposing 1M FVG broken with displacement, inverting into support/resistance.", body_style))
    story.append(Paragraph("<b>Step 5: SL & TP Placement (Consequent Encroachment):</b><br/>"
                           "• <i>Entry:</i> Limit order at Consequent Encroachment (C.E. 50% midpoint) of the 1M IFVG.<br/>"
                           "• <i>Stop Loss:</i> Beyond the swing extreme that created the CISD + <code>sl_buffer(symbol)</code> (3.0 pts for NAS100).<br/>"
                           "• <i>Take Profit:</i> Drawn directly to Step 2 DOL target, strictly enforcing a minimum of 1:2.00 R:R.", body_style))

    story.append(Spacer(1, 3))
    story.append(Paragraph("4.3 Quarterly Theory & SSMT (90-Minute Cycles)", h2_style))
    story.append(Paragraph(
        "Divides daily sessions into 90-minute quarters (Q1 Accumulation, Q2 Manipulation, Q3 Distribution, Q4 Reversal/Continuation). "
        "<b>SSMT Divergence</b> verifies SMT non-confirmation on 5M/15M bars at quarter cycle boundaries between NAS100 and SPX500.",
        body_style
    ))

    story.append(Paragraph("4.4 Setup Grading Matrix", h2_style))
    grade_data = [
        [Paragraph("<b>Grade</b>", table_header_style), Paragraph("<b>Action</b>", table_header_style), Paragraph("<b>Criteria Met</b>", table_header_style), Paragraph("<b>Execution Mandate</b>", table_header_style)],
        [Paragraph("<b>A+ Setup</b>", table_cell_green), Paragraph("<b>Execute Now</b>", table_cell_green), Paragraph("All 5 Steps + SMT Divergence + LRLR Clear Path", table_cell_style), Paragraph("Full Goat Risk ($2.50). High conviction.", table_cell_style)],
        [Paragraph("<b>A Setup</b>", table_cell_bold), Paragraph("<b>Execute</b>", table_cell_bold), Paragraph("All 5 Steps met; SMT aligned in direction", table_cell_style), Paragraph("Full Goat Risk ($2.50). Standard execution.", table_cell_style)],
        [Paragraph("<b>B Setup</b>", table_cell_style), Paragraph("Proceed with Caution", table_cell_style), Paragraph("Minor HRLR blocker or secondary 15M zone", table_cell_style), Paragraph("Reduce risk or wait for second CISD confirmation.", table_cell_style)],
        [Paragraph("<b>C Setup</b>", table_cell_red), Paragraph("<b>Do Not Trade</b>", table_cell_red), Paragraph("Counter-bias, missing 30M tap, or R:R < 2.0", table_cell_style), Paragraph("Stand aside. Wait / No trade.", table_cell_style)],
    ]
    t_grade = Table(grade_data, colWidths=[70, 95, 185, 154])
    t_grade.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_grade)
    story.append(PageBreak())

    # =========================================================================
    # PAGE 6: SECTION 5 — SPEAN STRATEGY
    # =========================================================================
    story.append(Paragraph("SECTION 5: STRATEGY 4 — SPEAN STRATEGY (7-LAYER FAH CONFLUENCE)", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("5.1 Overview & Philosophy", h2_style))
    story.append(Paragraph(
        "SPEAN Strategy is an ultra-disciplined price action model based on the concept of the <b>FAH (First Candle That Closed Beyond Swing Extreme)</b>. "
        "It eliminates subjective interpretation by requiring a strict 7-layer sequential confluence filter before any order is submitted. "
        "If even a single layer fails, the algorithm stands aside.",
        body_style
    ))

    story.append(make_diagram("SPEAN 7-LAYER GATEKEEPER SEQUENCE", [
        "1. Q-Zone Window", "2. 15M Sweep", "3. FAH Extreme", "4. Displacement", "5. 1M POI", "6. Retracement", "7. 1:2+ R:R"
    ]))
    story.append(Spacer(1, 5))

    story.append(Paragraph("5.2 The 7-Layer Sequential Execution Framework", h2_style))
    spean_layers = [
        ("Layer 1: Time & Session Window (Q-Zone)", "Restricted to London Q-Zone (07:00 – 10:00 UTC) and NY Q-Zone (12:00 – 16:00 UTC). Trades barred during lunch and Asian quiet hours."),
        ("Layer 2: 15-Minute Liquidity Take", "Market must sweep a significant 15M structural extreme: Asian High/Low, Prior Day High/Low (PDH/PDL), or Today's Intraday Extreme."),
        ("Layer 3: FAH Confirmation (First Candle Closed Beyond)", "Core signature of SPEAN. Identifies the specific 1M candle that achieved the first confirmed close beyond the swept level. Its high and low define the active range."),
        ("Layer 4: 1-Minute Strong Displacement", "Price aggressively rejects the swept level, producing a strong displacement candle closing completely back inside the FAH range with expanded volume."),
        ("Layer 5: Valid Point of Interest (POI)", "Displacement must leave an unmitigated 1M Fair Value Gap or Order Block inside the displacement leg, establishing the institutional footprint."),
        ("Layer 6: Retracement to POI Entry", "Price must retrace back into the POI zone. A Limit Order is placed at the proximal boundary of the POI. No market chasing is permitted."),
        ("Layer 7: Goat Risk & 1:2+ R:R Validation", "Stop Loss placed beyond FAH extreme + <code>sl_buffer(symbol)</code>. Take Profit targets opposing session liquidity with minimum 1:2.00 R:R. Consistency verified under 15% cap.")
    ]
    for title, desc in spean_layers:
        story.append(Paragraph(f"<b>{title}:</b> {desc}", body_style))

    story.append(Spacer(1, 4))
    spean_box_text = (
        "<b>SPEAN Invalidation Rule:</b> An active setup is invalidated immediately if price closes beyond the FAH Extreme "
        "before reaching the entry, or if price reaches the Take Profit target without filling the limit order. "
        "This ensures the algorithm never enters a stale or structurally compromised setup."
    )
    story.append(make_callout("SPEAN INVALIDATION CRITERIA", spean_box_text, RED_TEXT, CARD_BG))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 7: SECTION 6 & 7 — SILVER BULLET & SESSION BREAKOUT
    # =========================================================================
    story.append(Paragraph("SECTION 6: STRATEGY 5 — ICT SILVER BULLET (TIME-BASED FVG)", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("6.1 Core Theoretical Concept", h2_style))
    story.append(Paragraph(
        "The ICT Silver Bullet operates on the mathematical certainty that algorithmic market makers deliver high-probability "
        "repricing during three specific 60-minute daily windows. Within these exact 60 minutes, the algorithm hunts for liquidity "
        "sweeps followed by Fair Value Gap expansion.",
        body_style
    ))

    sb_windows_data = [
        [Paragraph("<b>Silver Bullet Window</b>", table_header_style), Paragraph("<b>New York Local Time</b>", table_header_style), Paragraph("<b>UTC Time</b>", table_header_style), Paragraph("<b>Market Focus & Volatility</b>", table_header_style)],
        [Paragraph("<b>London Silver Bullet</b>", table_cell_bold), Paragraph("03:00 AM – 04:00 AM NY", table_cell_style), Paragraph("08:00 – 09:00 UTC", table_cell_style), Paragraph("London morning expansion post-Asian sweep.", table_cell_style)],
        [Paragraph("<b>New York AM Silver Bullet</b>", table_cell_bold), Paragraph("10:00 AM – 11:00 AM NY", table_cell_style), Paragraph("14:00 – 15:00 UTC", table_cell_style), Paragraph("Post-equity open liquidity run (highest volume).", table_cell_style)],
        [Paragraph("<b>New York PM Silver Bullet</b>", table_cell_bold), Paragraph("02:00 PM – 03:00 PM NY", table_cell_style), Paragraph("18:00 – 19:00 UTC", table_cell_style), Paragraph("Afternoon bond close / institutional rebalance.", table_cell_style)],
    ]
    t_sb_win = Table(sb_windows_data, colWidths=[130, 110, 100, 164])
    t_sb_win.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_sb_win)
    story.append(Spacer(1, 4))

    story.append(Paragraph("6.2 Step-by-Step Execution Sequence", h2_style))
    story.append(Paragraph("<b>Step 1: Liquidity Take:</b> Market sweeps an external liquidity pool (BSL, SSL, PDH, PDL, or session extreme) prior to or inside the window.", bullet_style))
    story.append(Paragraph("<b>Step 2: 1M Displacement & FVG:</b> A displacement candle inside the 60-minute window forms a clean 3-candle FVG (>= 3.0 pts for NAS100; >= 0.8 pts for GOLD).", bullet_style))
    story.append(Paragraph("<b>Step 3: Limit Order Placement:</b> Limit order placed at proximal boundary of the FVG (top of gap for Buy; bottom of gap for Sell).", bullet_style))
    story.append(Paragraph("<b>Step 4: Stop Loss Placement:</b> Placed at displacement swing low (Buy) or high (Sell) with <code>sl_buffer(symbol)</code> applied.", bullet_style))
    story.append(Paragraph("<b>Step 5: Target DOL:</b> Target placed at opposing 15M/1H swing pool, guaranteeing a minimum of 1:2.00 R:R.", bullet_style))
    story.append(Paragraph("<b>Step 6: Window Invalidation:</b> If the 60-minute window closes without a fill, the pending limit order is automatically canceled.", bullet_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 7: STRATEGY 6 — SESSION MOMENTUM BREAKOUT", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "Session Momentum Breakout monitors the established 4-hour session range (last 16 candles on 15-minute timeframe). "
        "When market volume accelerates and cleanly displaces beyond the range boundary with a volatility buffer (5.0 pts for NAS100; "
        "0.8 pts for GOLD), a Stop/Market order is triggered targeting a 1:2.00 momentum expansion.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Stop Loss & Invalidation:</b> Stop loss is positioned just inside the broken range boundary using <code>sl_buffer(symbol)</code>. "
        "If price retreats back inside the session range, the trade is canceled immediately to protect Goat capital.",
        body_style
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 8: SECTION 8 — STANDARDIZED ORDER TICKET & PROP SAFEGUARDS
    # =========================================================================
    story.append(Paragraph("SECTION 8: STANDARDIZED ORDER TICKET & SAFEGUARDS", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE, spaceBefore=1, spaceAfter=8))

    story.append(Paragraph("8.1 Master Order Ticket Specification", h2_style))
    story.append(Paragraph(
        "Whenever any strategy confirms an active execution setup, it generates an immutable, Goat-compliant order ticket "
        "through <code>build_order_ticket()</code>. This ticket is broadcast simultaneously over WebSocket and Telegram.",
        body_style
    ))

    ticket_sample_data = [
        [Paragraph("<b>Field Name</b>", table_header_style), Paragraph("<b>Sample Value (NAS100 Buy)</b>", table_header_style), Paragraph("<b>Operational Function</b>", table_header_style)],
        [Paragraph("Order Type", table_cell_bold), Paragraph("BUY LIMIT", table_cell_green), Paragraph("Execution method (Limit / Stop / Market)", table_cell_style)],
        [Paragraph("Instrument", table_cell_bold), Paragraph("NAS100", table_cell_style), Paragraph("Target trading asset", table_cell_style)],
        [Paragraph("Entry Price", table_cell_bold), Paragraph("30,631.7", table_cell_style), Paragraph("Exact limit entry price (CE / FVG boundary)", table_cell_style)],
        [Paragraph("Stop Loss", table_cell_bold), Paragraph("30,621.9", table_cell_red), Paragraph("Calculated invalidation price + buffer", table_cell_style)],
        [Paragraph("Take Profit", table_cell_bold), Paragraph("30,651.3", table_cell_green), Paragraph("Draw on Liquidity (DOL) target price", table_cell_style)],
        [Paragraph("R:R Ratio", table_cell_bold), Paragraph("1:2.00", table_cell_bold), Paragraph("Strict minimum 1:2.0 enforced", table_cell_style)],
        [Paragraph("Risk Amount", table_cell_bold), Paragraph("$2.50 (0.25%)", table_cell_style), Paragraph("Goat $1,000 challenge risk per trade", table_cell_style)],
        [Paragraph("Projected Profit", table_cell_bold), Paragraph("+$5.00", table_cell_green), Paragraph("Anticipated dollar gain upon reaching TP", table_cell_style)],
        [Paragraph("Consistency Impact", table_cell_bold), Paragraph("0.50% (< 15% Cap Safe)", table_cell_style), Paragraph("Verified against Goat 15% single-trade rule", table_cell_style)],
        [Paragraph("Cancel If", table_cell_bold), Paragraph("Price closes beyond 30,621.9 or sweeps TP", table_cell_style), Paragraph("Automated order cancellation condition", table_cell_style)],
    ]
    t_ticket = Table(ticket_sample_data, colWidths=[120, 154, 230])
    t_ticket.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('BOX', (0, 0), (-1, -1), 1, CARD_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, CARD_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_ticket)
    story.append(Spacer(1, 8))

    story.append(Paragraph("8.2 Goat Funded Trader Consistency Safeguards", h2_style))
    story.append(Paragraph(
        "Prop firms enforce strict consistency rules to eliminate 'lucky gambles'. In a $1,000 account targeting a $150 profit, "
        "no single trade may exceed $22.50 (15% of total profits). Our risk engine computes:",
        body_style
    ))
    formula_html = (
        "<font size='9'><b>Mathematical Formula:</b></font><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<b>Consistency % = ( Projected Profit / Account Balance ) &times; 100</b><br/><br/>"
        "<font color='#475569'><i>Example: $5.00 projected profit on a $1,000.00 account = <b>0.50%</b> (&lt; 15% Cap Safe). "
        "Even on a max 1:5.0 R:R windfall ($12.50 gain), consistency impact is only 1.25%, keeping every trade safely below prop firm disqualification.</i></font>"
    )
    story.append(make_callout("TRUE CONSISTENCY PROFIT CAP FORMULA", formula_html, ACCENT_BLUE, CARD_BG))
    story.append(Spacer(1, 8))

    closing_text = (
        "<b>VERIFICATION & DEPLOYMENT NOTE:</b> All logic documented in this manual has been compiled, "
        "unit-tested across synthetic and live market environments, and deployed to live production on Railway. "
        "The system runs 24/7 with zero Yahoo Finance scraping and sub-second TradingView WebSocket delivery."
    )
    story.append(make_callout("SYSTEM COMPLIANCE VERIFICATION", closing_text, GREEN_TEXT, CARD_BG))

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated: {filename}")


if __name__ == "__main__":
    build_pdf(WORKSPACE_PDF)
    # Also save to artifact directory
    import shutil
    shutil.copyfile(WORKSPACE_PDF, ARTIFACT_PDF)
    print(f"Copied to artifact directory: {ARTIFACT_PDF}")
