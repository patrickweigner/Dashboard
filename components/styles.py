from __future__ import annotations

from nicegui import ui
from nicegui.elements.button import Button


def register_global_head_html(
    *,
    browser_html_zoom: float,
    disconnect_reload_seconds: float,
    native_html_zoom: float,
    open_item_gap_px: float,
    open_item_font_size_px: int,
    open_item_font_weight: int,
    open_item_line_height: float,
) -> None:
    Button.default_props("no-caps")

    ui.add_head_html(
        """
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
        <script>
          (function () {
            if (window.__fristenDialogEnterHandlerInstalled) return;
            window.__fristenDialogEnterHandlerInstalled = true;
            document.addEventListener('keydown', function (event) {
              if (event.key !== 'Enter' || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
              const target = event.target;
              if (!target || !(target instanceof Element)) return;
              const tag = String(target.tagName || '').toLowerCase();
              if (tag === 'textarea' || target.isContentEditable) return;
              const dialog = target.closest('.q-dialog');
              if (!dialog) return;
              const buttons = Array.from(dialog.querySelectorAll('button.q-btn:not([disabled])'));
              const isDanger = (button) => {
                const text = String(button.innerText || button.textContent || '').trim().toLowerCase();
                return button.classList.contains('cfg-btn-danger')
                  || /^(loeschen|löschen|entfernen|abbrechen|schliessen|schließen)$/.test(text);
              };
              const isPrimaryAction = (button) => {
                if (isDanger(button)) return false;
                const text = String(button.innerText || button.textContent || '').trim().toLowerCase();
                return /^(speichern|login|ok|anwenden|hinzufuegen|hinzufügen|bestaetigen|bestätigen|uebernehmen|übernehmen)$/.test(text);
              };
              const button = buttons.find(isPrimaryAction);
              if (!button) return;
              event.preventDefault();
              event.stopPropagation();
              button.click();
            }, true);
          })();
        </script>
        """,
        shared=True,
    )

    ui.add_head_html(
        """
        <style>
          :root {
            --btn-bg: linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%);
            --btn-bg-hover: linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%);
            --btn-fg: #f3f4f6;
            --btn-border: rgba(148,163,184,.22);
            --btn-border-hover: rgba(96,165,250,.50);
            --btn-shadow: 0 18px 40px rgba(0,0,0,.22);
            --btn-shadow-hover: 0 24px 50px rgba(0,0,0,.28);
            --q-primary: #111827;
          }
          html {
            zoom: 0.8;
          }
          html, body, #q-app {
            background: #0e1117;
            --q-primary: #111827 !important;
          }
          html body #q-app .bg-primary {
            background: var(--btn-bg, linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%)) !important;
            background-color: #111827 !important;
            color: var(--btn-fg, #f3f4f6) !important;
          }
          html body #q-app .q-btn,
          html body #q-app .q-btn.q-btn--standard,
          html body #q-app .q-btn.q-btn--unelevated,
          html body #q-app .q-btn.q-btn--outline {
            background: var(--btn-bg, linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%)) !important;
            background-color: #111827 !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border: 1px solid var(--btn-border, rgba(255,255,255,.18)) !important;
            border-radius: 18px !important;
            box-shadow: var(--btn-shadow, 0 18px 40px rgba(0,0,0,.22)) !important;
            text-transform: none !important;
            transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease, background .15s ease !important;
          }
          html body #q-app .q-btn .q-btn__content {
            text-transform: none !important;
          }
          html body #q-app .q-btn:hover {
            background: var(--btn-bg-hover, linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%)) !important;
            background-color: #111827 !important;
            border-color: var(--btn-border-hover, rgba(96,165,250,.50)) !important;
            box-shadow: var(--btn-shadow-hover, 0 24px 50px rgba(0,0,0,.28)) !important;
            transform: translateY(-2px);
          }
          html body #q-app .q-btn .q-focus-helper {
            background: rgba(255,255,255,.10) !important;
          }
          .nicegui-content {
            max-width: 100% !important;
          }
          .nav-row {
            position: sticky;
            top: 0;
            z-index: 1000;
            background: #0e1117;
            border-bottom: 1px solid rgba(255,255,255,.10);
            padding: 6px 0;
            margin-bottom: 8px;
          }
          .nav-btn {
            font-weight: 800 !important;
            font-size: 25px !important;
            background: var(--btn-bg, #111827) !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border: 1px solid var(--btn-border, rgba(255,255,255,.18)) !important;
          }
          .q-btn.nav-btn .q-icon,
          .q-btn.nav-btn .material-icons,
          .q-btn.nav-btn .material-symbols-outlined,
          .q-btn.nav-btn .material-symbols-rounded,
          .q-btn.nav-btn .material-symbols-sharp {
            font-family: 'Material Icons' !important;
            font-weight: normal !important;
            font-style: normal !important;
            font-variation-settings: normal !important;
          }
          html body #q-app .q-btn.bg-primary,
          html body #q-app .q-btn--standard.bg-primary,
          html body #q-app .q-btn--unelevated.bg-primary,
          html body #q-app .q-btn--outline.bg-primary {
            background: var(--btn-bg, linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%)) !important;
            background-color: #111827 !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border: 1px solid var(--btn-border, rgba(255,255,255,.18)) !important;
            border-radius: 18px !important;
            box-shadow: var(--btn-shadow, 0 18px 40px rgba(0,0,0,.22)) !important;
          }
          html body #q-app .q-btn.bg-primary:hover,
          html body #q-app .q-btn--standard.bg-primary:hover,
          html body #q-app .q-btn--unelevated.bg-primary:hover,
          html body #q-app .q-btn--outline.bg-primary:hover {
            background: var(--btn-bg-hover, linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%)) !important;
            background-color: #111827 !important;
            border-color: var(--btn-border-hover, rgba(96,165,250,.50)) !important;
            box-shadow: var(--btn-shadow-hover, 0 24px 50px rgba(0,0,0,.28)) !important;
          }
          .q-btn.nav-btn,
          .q-btn.btn-big {
            background: var(--btn-bg, linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%)) !important;
            background-color: #111827 !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border: 1px solid var(--btn-border, rgba(255,255,255,.18)) !important;
            border-radius: 18px !important;
            box-shadow: var(--btn-shadow, 0 18px 40px rgba(0,0,0,.22)) !important;
          }
          .q-btn.nav-btn:hover,
          .q-btn.btn-big:hover {
            background: var(--btn-bg-hover, linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%)) !important;
            background-color: #111827 !important;
            border-color: var(--btn-border-hover, rgba(96,165,250,.50)) !important;
            box-shadow: var(--btn-shadow-hover, 0 24px 50px rgba(0,0,0,.28)) !important;
          }
          .q-btn.nav-btn .q-focus-helper,
          .q-btn.btn-big .q-focus-helper {
            background: rgba(255,255,255,.10) !important;
          }
          .home-btn {
            width: 100%;
            justify-content: flex-start;
            min-height: 86px;
            background: var(--btn-bg, #111827) !important;
            color: var(--btn-fg, #f3f4f6) !important;
          }
          .home-btn .q-btn__content {
            font-size: 2.2rem !important;
            font-weight: 900 !important;
          }
          .page-title {
            font-size: 2.6rem;
            font-weight: 900;
            color: #f2f5f8;
            margin: 4px 0 10px 0;
          }
          .section-title {
            font-size: 4.0rem;
            line-height: 1.1;
            font-weight: 900;
            color: #0d6efd;
            margin: 10px 0 8px 0;
          }
          .kpi-card {
            min-width: 160px;
            background: rgba(255,255,255,.06);
            color: #f2f5f8;
          }
          .task-shell {
            width: 100%;
            border-radius: 10px;
            background: #262730;
            color: #ffffff;
            border: 0.5px solid rgba(0,0,0,.04);
            box-shadow: 0 1px 3px rgba(0,0,0,.06);
            padding: 6px 8px;
          }
          .no-wrap {
            flex-wrap: nowrap !important;
          }
          .task-col {
            min-width: 0;
            flex: 1 1 0;
          }
          .task-col-fzg {
            min-width: 0;
          }
          .task-col-ratio-22 { flex: 2.2 1 0; }
          .task-col-ratio-16 { flex: 1.6 1 0; }
          .task-col-ratio-13 { flex: 1.3 1 0; }
          .task-col-ratio-12 { flex: 1.2 1 0; }
          .task-col-ratio-09 { flex: 0.9 1 0; }
          .task-col-ratio-09 .q-btn {
            width: 100%;
          }
          .task-actions {
            min-width: 0;
            margin-left: auto;
            gap: 8px;
          }
          .badge-stack {
            display: flex;
            flex-direction: column;
            gap: 4px;
          }
          .badge-label {
            color: #ffffff;
            text-decoration: underline;
            font-weight: 900;
            line-height: 1.1;
            text-shadow: 0 1px 2px rgba(0,0,0,.4);
          }
          .badge-label-big {
            font-size: 20px;
          }
          .badge-label-small {
            font-size: 16px;
          }
          .badge-pill {
            display: inline-block;
            border-radius: 10px;
            padding: 6px 12px;
            font-weight: 900;
            line-height: 1.0;
            white-space: nowrap;
          }
          .badge-pill-big {
            font-size: 30px;
          }
          .badge-pill-small {
            font-size: 22px;
          }
          .task-status {
            margin-top: 14px;
            font-size: 18px;
            font-weight: 800;
            min-width: 330px;
            text-align: center;
            display: inline-flex;
            justify-content: center;
          }
          .btn-big .q-btn__content {
            font-size: 25px !important;
            line-height: 1.15 !important;
            font-weight: 900 !important;
          }
          .btn-done {
            background: var(--btn-bg) !important;
            color: var(--btn-fg) !important;
            border: 1px solid rgba(82,196,26,.55) !important;
          }
          .btn-warn {
            background: var(--btn-bg) !important;
            color: var(--btn-fg) !important;
            border: 1px solid rgba(255,235,59,.70) !important;
          }
          .q-btn.btn-done,
          .q-btn.btn-warn {
            background-color: var(--btn-bg) !important;
            color: var(--btn-fg) !important;
          }
          .btn-done:hover,
          .btn-warn:hover { background: var(--btn-bg-hover) !important; }
          .zus-line {
            font-size: 18px;
            font-weight: 700;
            line-height: 1.1;
            margin: 2px 0;
          }
          .problem-box,
          .problemline {
            margin-top: 4px;
            background: #fff3cd;
            border: 1px solid #ffe08a;
            color: #704c00;
            padding: 6px 8px;
            border-radius: 8px;
            font-size: 14px;
          }
          .legend-row {
            gap: 18px;
            margin: 4px 0 10px 0;
          }
          .legend-item {
            color: #ffffff;
            font-size: 18px;
            font-weight: 700;
          }
          .legend-pill {
            display: inline-block;
            width: 56px;
            height: 26px;
            border-radius: 999px;
          }
          .legend-green { background: #52c41a; }
          .legend-yellow { background: #faad14; }
          .legend-yellow-problem { background: #ffeb3b; }
          .legend-red { background: #ff4d4f; }
          .legend-text {
            font-size: 18px;
            font-weight: 700;
          }
          .hall-card {
            min-width: 220px;
            flex: 1;
            background: #262730;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
          }
          .hall-row {
            padding: 2px 0;
            font-size: 16px;
            font-weight: 700;
          }
          .task-card {
            width: 100%;
            color: #0f1a25;
            border-radius: 14px;
          }
          .open-tasks-page {
            gap: 12px;
            padding: 0 4px 22px 4px;
            color: #f2f5f8;
          }
          .open-command-row {
            padding: 6px 2px 10px 2px;
            border-bottom: 1px solid rgba(148,163,184,.20);
          }
          .open-page-title {
            margin: 0;
            line-height: 1.05;
            letter-spacing: 0;
          }
          .open-new-order-btn {
            min-height: 56px;
          }
          .open-legend-wrap {
            padding: 10px 12px;
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 12px;
            background: rgba(17,24,39,.70);
          }
          .open-legend-wrap .legend-row {
            margin: 0;
            gap: 14px;
          }
          .open-legend-wrap .legend-pill {
            width: 44px;
            height: 20px;
          }
          .open-legend-wrap .legend-text {
            font-size: 1rem;
            line-height: 1.15;
          }
          .open-task-list {
            gap: 12px;
          }
          .open-summary-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(150px, 1fr));
            gap: 10px;
            width: 100%;
          }
          .open-stat {
            min-height: 74px;
            padding: 12px 14px;
            border-radius: 12px;
            border: 1px solid rgba(148,163,184,.20);
            background: #171d25;
            box-shadow: 0 14px 34px rgba(0,0,0,.18);
          }
          .open-stat-total { border-left: 5px solid #60a5fa; }
          .open-stat-due { border-left: 5px solid #faad14; }
          .open-stat-late { border-left: 5px solid #ff4d4f; }
          .open-stat-problem { border-left: 5px solid #ffeb3b; }
          .open-stat-value {
            color: #ffffff;
            font-size: 2rem;
            font-weight: 950;
            line-height: 1;
            letter-spacing: 0;
          }
          .open-stat-label {
            color: #cbd5e1;
            font-size: .95rem;
            font-weight: 800;
            line-height: 1.15;
            margin-top: 7px;
            letter-spacing: 0;
          }
          .open-section-head {
            margin: 4px 0 0 0;
          }
          .open-section-title {
            margin: 0;
            font-size: 2.35rem;
            color: #60a5fa;
            text-decoration: none;
          }
          .open-section-count {
            color: #cbd5e1;
            font-size: 1rem;
            font-weight: 900;
            padding: 7px 10px;
            border: 1px solid rgba(148,163,184,.20);
            border-radius: 999px;
            background: rgba(17,24,39,.72);
          }
          .open-section-separator {
            margin: 6px 0 2px 0;
            opacity: .35;
          }
          .open-task-card {
            background: linear-gradient(180deg, #252b34 0%, #1d232b 100%);
            border: 1px solid rgba(148,163,184,.22);
            border-radius: 12px;
            box-shadow: 0 18px 42px rgba(0,0,0,.24);
            padding: 14px 16px !important;
            overflow: hidden;
          }
          .open-task-card .open-task-grid {
            display: grid !important;
            grid-template-columns: minmax(260px, 2.2fr) minmax(220px, 1.25fr) minmax(150px, .9fr) minmax(220px, 1.2fr) minmax(150px, .9fr) minmax(170px, .8fr);
            gap: 14px;
            align-items: start;
          }
          .open-task-card .badge-label {
            text-decoration: none;
            color: #cbd5e1;
            font-size: .9rem;
            line-height: 1;
            text-shadow: none;
          }
          .open-task-card .badge-pill-big {
            font-size: clamp(1.35rem, 1.5vw, 1.85rem);
            line-height: 1.05;
            max-width: 100%;
            overflow-wrap: anywhere;
            white-space: normal;
          }
          .open-task-card .task-check-list {
            padding-top: 4px;
          }
          .open-task-card .task-check-list .task-check-row {
            margin-bottom: 7px;
          }
          .open-task-card .task-check-text {
            font-size: .98rem;
            line-height: 1.13;
          }
          .open-task-card .task-frist-head {
            font-size: .68rem;
          }
          .open-task-card .task-status {
            min-width: 0;
            max-width: 100%;
            margin-top: 9px;
            font-size: .95rem;
            white-space: normal;
          }
          .open-task-card .task-actions {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            width: 100%;
            margin-left: 0;
            gap: 10px;
          }
          .open-task-card .task-actions .q-btn {
            min-height: 56px;
            width: 100%;
          }
          .open-empty-state {
            min-height: 180px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px dashed rgba(148,163,184,.30);
            border-radius: 12px;
            background: rgba(17,24,39,.45);
          }
          .status-neutral {
            background: #e5e7eb;
          }
          .hall-green { color: #9be37c; }
          .hall-yellow, .hall-yellow_problem { color: #ffd777; }
          .hall-red { color: #ff9a9a; }
          .hall-neutral { color: #d1d5db; }
          .hall-grid {
            align-items: stretch;
          }
          .hall-slot {
            width: 100%;
            min-height: 270px;
            background: transparent;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
          }
          .hall-slot-active {
            background: #262730;
            box-shadow: 0 1px 3px rgba(0,0,0,.06);
          }
          .hall-slot-passive {
            background: transparent;
          }
          .hall-slot-title {
            font-size: 3rem;
            line-height: 1;
            font-weight: 900;
            text-decoration: underline;
            color: #f5f7fa;
            margin: 0;
          }
          .btn-remove {
            background: var(--btn-bg) !important;
            color: var(--btn-fg) !important;
            border: 1px solid var(--btn-border) !important;
          }
          .btn-area-assign {
            background: var(--btn-bg) !important;
            color: var(--btn-fg) !important;
            border: 1px solid var(--btn-border) !important;
          }
          .hall-fzg {
            font-size: 3rem;
            font-weight: 900;
            line-height: 1;
            margin: 4px 0 2px 0;
            color: #f5f7fa;
          }
          .hall-meta {
            font-size: 1.5rem;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 6px;
            color: #f5f7fa;
          }
          .slot-pill {
            display: inline-block;
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 1.15rem;
            font-weight: 900;
            line-height: 1;
            white-space: nowrap;
          }
          .hall-actions .q-btn {
            min-width: 170px;
          }
          .due-card {
            width: 100%;
            min-height: 270px;
            background: #262730;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
          }
          .due-title {
            font-size: 3rem;
            line-height: 1;
            font-weight: 900;
            text-decoration: underline;
            color: #f5f7fa;
            margin: 0 0 8px 0;
          }
          .due-row-card {
            width: 100%;
            background: #111827;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 12px;
            color: #f2f5f8;
          }
          .due-fzg {
            font-size: 2rem;
            font-weight: 900;
            line-height: 1.05;
          }
          .due-meta {
            font-size: 1.15rem;
            font-weight: 700;
          }
          .werkstatthalle-page {
            gap: 12px;
            padding: 0 4px 22px 4px;
            color: #f2f5f8;
          }
          .workshop-command-row {
            padding: 6px 2px 12px 2px;
            border-bottom: 1px solid rgba(148,163,184,.20);
          }
          .workshop-page-title {
            margin: 0;
            line-height: 1.05;
            letter-spacing: 0;
          }
          .workshop-command-tools {
            margin-left: 0;
          }
          .workshop-external-btn {
            min-height: 56px;
          }
          .workshop-legend {
            min-height: 54px;
            padding: 9px 12px;
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 14px;
            background: rgba(17,24,39,.72);
          }
          .workshop-legend .legend-pill {
            width: 42px;
            height: 22px;
            box-shadow: 0 0 0 1px rgba(255,255,255,.22) inset;
          }
          .workshop-content {
            gap: 12px;
          }
          .workshop-summary-row {
            display: grid !important;
            grid-template-columns: repeat(4, minmax(150px, 1fr));
            gap: 10px;
          }
          .workshop-stat {
            min-height: 74px;
            padding: 12px 14px;
            border-radius: 14px;
            border: 1px solid rgba(148,163,184,.20);
            background: #171d25;
            box-shadow: 0 14px 34px rgba(0,0,0,.18);
          }
          .workshop-stat-occupied { border-left: 5px solid #60a5fa; }
          .workshop-stat-free { border-left: 5px solid #52c41a; }
          .workshop-stat-unassigned { border-left: 5px solid #31ccec; }
          .workshop-stat-due { border-left: 5px solid #faad14; }
          .workshop-stat-value {
            color: #ffffff;
            font-size: 2rem;
            font-weight: 950;
            line-height: 1;
            letter-spacing: 0;
          }
          .workshop-stat-label {
            color: #cbd5e1;
            font-size: .95rem;
            font-weight: 800;
            line-height: 1.15;
            margin-top: 7px;
            letter-spacing: 0;
          }
          .hall-bottom-grid {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(360px, 1fr)) !important;
            gap: 12px !important;
          }
          .hall-slot,
          .due-card {
            min-height: 300px;
            padding: 18px !important;
            background: #20252d;
            border: 1px solid rgba(148,163,184,.22);
            border-radius: 14px;
            box-shadow: 0 18px 42px rgba(0,0,0,.24);
            overflow: hidden;
          }
          .hall-slot-active {
            background: linear-gradient(180deg, #252b34 0%, #1d232b 100%);
          }
          .hall-slot-passive {
            background: #151a21;
            border-style: dashed;
            color: #cbd5e1;
          }
          .hall-slot-empty {
            min-height: 190px;
          }
          .hall-slot-title,
          .due-title {
            text-decoration: none;
            color: #ffffff;
            letter-spacing: 0;
            overflow-wrap: anywhere;
          }
          .hall-fzg {
            margin-top: 14px;
            letter-spacing: 0;
            overflow-wrap: anywhere;
          }
          .hall-meta,
          .due-meta {
            color: #d7dee9;
            overflow-wrap: anywhere;
          }
          .slot-pill {
            border: 1px solid rgba(255,255,255,.18);
            box-shadow: 0 1px 0 rgba(255,255,255,.18) inset;
          }
          .hall-actions {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            align-items: stretch;
          }
          .hall-actions .q-btn {
            width: 100%;
            min-width: 0;
            min-height: 58px;
          }
          .due-row-card {
            padding: 12px !important;
            background: #131922;
            border-color: rgba(250,173,20,.30);
          }
          .problem-box,
          .problemline {
            border-radius: 10px;
          }
          .gleisplan-page {
            color: #f3f4f6;
          }
          .gleisplan-clock {
            color: #cbd5e1;
            font-size: 1.25rem;
            font-weight: 800;
          }
          .gleisplan-layout {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(300px, 370px);
            gap: 14px;
            align-items: start;
            width: 100%;
          }
          .gleisplan-main {
            min-width: 0;
          }
          .gleisplan-map {
            width: 100%;
            min-height: 680px;
            padding: 16px;
            background:
              linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px),
              #141922;
            background-size: 36px 36px;
            border: 1px solid rgba(148,163,184,.26);
            border-radius: 16px;
            box-shadow: 0 20px 46px rgba(0,0,0,.24);
            overflow: hidden;
          }
          .gleisplan-map-middle {
            display: grid;
            grid-template-columns: minmax(220px, .8fr) minmax(420px, 1.35fr) minmax(220px, .8fr);
            gap: 14px;
            align-items: center;
            margin: 18px 0;
          }
          .gleisplan-track-section {
            width: 100%;
            padding: 12px;
            background: rgba(15,23,42,.72);
            border: 1px solid rgba(148,163,184,.20);
            border-radius: 12px;
          }
          .gleisplan-track-section-title {
            color: #dbeafe;
            font-size: 1.05rem;
            font-weight: 900;
            margin-bottom: 10px;
          }
          .gleisplan-track-row {
            display: grid;
            grid-template-columns: 74px minmax(120px, 1fr);
            align-items: center;
            gap: 10px;
            min-height: 34px;
          }
          .gleisplan-track-label {
            color: #cbd5e1;
            font-size: .9rem;
            font-weight: 900;
            text-align: right;
            white-space: nowrap;
          }
          .gleisplan-track-line {
            height: 4px;
            border-radius: 999px;
            background: #111827;
            box-shadow: 0 0 0 1px rgba(255,255,255,.32);
            position: relative;
          }
          .gleisplan-track-line::after {
            content: "";
            position: absolute;
            right: 8px;
            top: -5px;
            width: 14px;
            height: 14px;
            border: 2px solid #60a5fa;
            border-radius: 2px;
            transform: rotate(45deg);
            background: #141922;
          }
          .gleisplan-track-line.red {
            background: #dc2626;
            box-shadow: 0 0 0 1px rgba(248,113,113,.55);
          }
          .gleisplan-track-north {
            max-width: 86%;
            margin-left: 4%;
          }
          .gleisplan-track-west,
          .gleisplan-track-service,
          .gleisplan-track-east {
            min-height: 150px;
          }
          .gleisplan-west-stack,
          .gleisplan-east-stack {
            display: flex;
            flex-direction: column;
            gap: 14px;
            min-width: 0;
          }
          .gleisplan-junction {
            min-height: 90px;
            padding: 10px;
            background: rgba(30,41,59,.60);
            border: 1px dashed rgba(148,163,184,.32);
            border-radius: 12px;
          }
          .gleisplan-junction-label {
            color: #f8fafc;
            font-size: 1rem;
            font-weight: 900;
            margin-bottom: 12px;
          }
          .gleisplan-switch-lines {
            height: 46px;
            border-top: 4px solid #dc2626;
            border-bottom: 4px solid #111827;
            transform: skewX(-18deg);
            opacity: .95;
          }
          .gleisplan-hall-wrap {
            min-width: 0;
          }
          .gleishalle-panel {
            background: #2b3038;
            border: 2px solid rgba(191,219,254,.42);
            border-radius: 14px;
            padding: 12px;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.05), 0 16px 36px rgba(0,0,0,.28);
          }
          .gleishalle-title {
            color: #f8fafc;
            font-size: 1.3rem;
            font-weight: 900;
          }
          .gleishalle-source {
            color: #93c5fd;
            font-size: .9rem;
            font-weight: 800;
          }
          .gleishalle-grid-2x2 {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 12px;
            border: 1px solid rgba(226,232,240,.36);
            border-radius: 10px;
            overflow: hidden;
          }
          .gleishalle-cell {
            min-height: 190px;
            padding: 10px;
            background: rgba(15,23,42,.72);
          }
          .gleishalle-cell:nth-child(odd) {
            border-right: 1px solid rgba(226,232,240,.32);
          }
          .gleishalle-cell:nth-child(-n+2) {
            border-bottom: 1px solid rgba(226,232,240,.32);
          }
          .gleishalle-area {
            color: #f8fafc;
            font-size: 1.65rem;
            line-height: 1;
            font-weight: 900;
          }
          .gleishalle-position {
            color: #94a3b8;
            font-size: .85rem;
            font-weight: 800;
            white-space: nowrap;
          }
          .gleisplan-vehicle-card {
            margin-top: 10px;
            padding: 10px;
            background: #0f172a;
            border: 1px solid rgba(148,163,184,.24);
            border-left: 6px solid var(--vehicle-status-bg, #64748b);
            border-radius: 10px;
            min-width: 0;
          }
          .gleisplan-vehicle-title {
            color: #f8fafc;
            font-size: 1.55rem;
            line-height: 1.08;
            font-weight: 900;
            overflow-wrap: anywhere;
          }
          .gleisplan-vehicle-meta {
            color: #cbd5e1;
            font-size: .96rem;
            line-height: 1.25;
            font-weight: 800;
            margin-top: 5px;
          }
          .gleisplan-status-pill,
          .gleisplan-mini-pill {
            display: inline-flex;
            align-items: center;
            min-height: 24px;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: .78rem;
            font-weight: 900;
            line-height: 1;
            white-space: nowrap;
          }
          .gleisplan-status-pill {
            max-width: 140px;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .gleisplan-mini-pill {
            background: rgba(148,163,184,.16);
            color: #e2e8f0;
            border: 1px solid rgba(148,163,184,.18);
          }
          .gleisplan-empty-vehicle {
            margin-top: 10px;
            min-height: 92px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px dashed rgba(148,163,184,.34);
            border-radius: 10px;
            background: rgba(15,23,42,.45);
          }
          .gleisplan-empty-label {
            color: #94a3b8;
            font-size: 1.05rem;
            font-weight: 900;
            text-transform: uppercase;
          }
          .gleisplan-extra-label {
            color: #fbbf24;
            font-size: .85rem;
            font-weight: 900;
            margin-top: 8px;
          }
          .gleisplan-side-panel {
            width: 100%;
            padding: 14px;
            background: #1f2937;
            color: #f8fafc;
            border: 1px solid rgba(148,163,184,.24);
            border-radius: 14px;
            box-shadow: 0 16px 34px rgba(0,0,0,.22);
            display: flex;
            flex-direction: column;
            gap: 12px;
          }
          .gleisplan-panel-title {
            font-size: 1.35rem;
            line-height: 1.1;
            font-weight: 900;
          }
          .gleisplan-muted {
            color: #cbd5e1;
            font-size: 1rem;
            font-weight: 700;
          }
          .gleisplan-select .q-field__native,
          .gleisplan-select .q-field__input,
          .gleisplan-select .q-field__label,
          .gleisplan-select .q-field__marginal,
          .gleisplan-select .q-field__prepend,
          .gleisplan-select .q-field__append {
            color: #ffffff !important;
          }
          .gleisplan-select .q-field__control {
            background: #111827 !important;
          }
          .gleisplan-select .q-field__control:before,
          .gleisplan-select .q-field__control:after {
            border-color: rgba(255,255,255,.82) !important;
          }
          .cfg-gleisplan-editor-panel {
            flex: 2 1 720px;
            min-width: 0;
          }
          .gleisplan-editor-board {
            position: relative;
            width: 100%;
            max-width: 100%;
            height: auto;
            aspect-ratio: 1501 / 1058;
            min-height: 420px;
            max-height: calc(100vh - 195px);
            margin: 10px auto 0;
            background:
              linear-gradient(rgba(15,23,42,.06) 1px, transparent 1px),
              linear-gradient(90deg, rgba(15,23,42,.06) 1px, transparent 1px),
              #f8fafc;
            background-size: 36px 36px;
            border: 1px solid rgba(148,163,184,.55);
            border-radius: 12px;
            overflow: hidden;
            touch-action: none;
          }
          .gleisplan-editor-board.draw-street-active {
            cursor: crosshair;
          }
          .gleisplan-editor-board.hide-editor-grid {
            background: #f8fafc;
          }
          .gleisplan-pdf-trace {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            display: none;
            background-image: url('/assets/gleisplan/eberswalde_lageplan_2026_05_20.png');
            background-size: 100% 100%;
            background-position: center;
            background-repeat: no-repeat;
            opacity: var(--pdf-trace-opacity, .45);
            transform-origin: center center;
            transform:
              translate(var(--pdf-trace-x, 0%), var(--pdf-trace-y, 0%))
              rotate(var(--pdf-trace-rotation, 0deg))
              scale(var(--pdf-trace-scale-x, 1), var(--pdf-trace-scale-y, 1));
            pointer-events: none;
          }
          .gleisplan-editor-board.show-pdf-trace .gleisplan-pdf-trace {
            display: block;
          }
          .gleisplan-editor-item {
            position: absolute;
            z-index: 4;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            padding: 6px;
            border: 1px solid rgba(15,23,42,.32);
            border-radius: 8px;
            background: rgba(255,255,255,.92);
            color: #0f172a;
            box-shadow: 0 8px 18px rgba(15,23,42,.16);
            cursor: move;
            user-select: none;
            touch-action: none;
            will-change: left, top;
          }
          .gleisplan-editor-item.is-dragging {
            z-index: 20 !important;
            box-shadow: 0 16px 34px rgba(15,23,42,.28);
          }
          .gleisplan-editor-item.is-resizing {
            z-index: 21 !important;
          }
          .gleisplan-editor-item.is-selected {
            outline: 3px solid #f59e0b;
            outline-offset: 2px;
          }
          .gleisplan-editor-item.is-connection-source {
            outline: 3px solid #f59e0b;
            outline-offset: 3px;
            box-shadow: 0 0 0 4px rgba(245,158,11,.18), 0 12px 26px rgba(15,23,42,.22);
          }
          .gleisplan-editor-item.item-track {
            z-index: 8;
            border-top: 5px solid var(--layout-color, #dc2626);
          }
          .gleisplan-editor-item.item-track::before {
            content: "";
            position: absolute;
            left: -1px;
            right: -1px;
            top: 50%;
            height: 5px;
            transform: translateY(-50%);
            background: #dc2626;
            box-shadow: 0 0 0 1px rgba(127,29,29,.20);
            pointer-events: none;
          }
          .gleisplan-editor-item.item-anchor {
            z-index: 9;
            width: 1.4% !important;
            height: 1.4% !important;
            min-width: 14px;
            min-height: 14px;
            padding: 0;
            border-radius: 50%;
            background: #f8fafc;
            border: 2px solid #1d4ed8;
            box-shadow: 0 5px 12px rgba(15,23,42,.24);
          }
          .gleisplan-editor-item.item-switch {
            z-index: 9;
            padding: 0;
            background: transparent;
            border: 0;
            box-shadow: none;
          }
          .gleisplan-editor-item.item-buffer_stop {
            z-index: 9;
            padding: 0;
            background: transparent;
            border: 0;
            box-shadow: none;
          }
          .gleisplan-editor-item.item-hall {
            z-index: 4;
            background: rgba(209,213,219,.94);
            padding: 8px;
            overflow: hidden;
          }
          .gleisplan-editor-item.item-building {
            z-index: 2;
            background: var(--layout-color, rgba(254,202,202,.62));
          }
          .gleisplan-editor-item.item-street {
            z-index: 1;
            padding: 0 8px;
            overflow: visible;
            background: transparent;
            border: 0;
            border-radius: 0;
            box-shadow: none;
            transform-origin: left center;
          }
          .gleisplan-editor-item.item-street::before {
            content: "";
            position: absolute;
            inset: 0;
            background: var(--layout-color, #d1d5db);
            border: 0;
            border-left: 0;
            border-right: 0;
            border-radius: var(--curve-radius, 0);
            pointer-events: none;
          }
          .gleisplan-editor-street-preview {
            position: absolute;
            z-index: 1;
            height: 3%;
            background: #d1d5db;
            border: 0;
            border-radius: 0;
            pointer-events: none;
            transform-origin: left center;
          }
          .gleisplan-street-resize-handle {
            position: absolute;
            right: -7px;
            top: 50%;
            z-index: 4;
            display: none;
            width: 14px;
            height: 28px;
            transform: translateY(-50%);
            border: 2px solid #1d4ed8;
            border-radius: 4px;
            background: #f8fafc;
            box-shadow: 0 4px 10px rgba(15,23,42,.22);
            cursor: ew-resize;
            pointer-events: auto;
          }
          .gleisplan-editor-item.item-street.is-selected .gleisplan-street-resize-handle {
            display: block;
          }
          .gleisplan-editor-item.item-street.is-selected .gleisplan-street-width-handle,
          .gleisplan-editor-item.item-street.is-selected .gleisplan-rotate-handle,
          .gleisplan-editor-item.item-street.is-selected .gleisplan-curve-handle,
          .gleisplan-editor-item.item-switch.is-selected .gleisplan-rotate-handle,
          .gleisplan-editor-item.item-buffer_stop.is-selected .gleisplan-rotate-handle {
            display: block;
          }
          .gleisplan-street-resize-handle::before {
            content: "";
            position: absolute;
            left: 4px;
            top: 4px;
            bottom: 4px;
            width: 2px;
            background: #1d4ed8;
            box-shadow: 4px 0 0 #1d4ed8;
          }
          .gleisplan-street-width-handle,
          .gleisplan-rotate-handle,
          .gleisplan-curve-handle {
            position: absolute;
            z-index: 5;
            display: none;
            background: #f8fafc;
            border: 2px solid #1d4ed8;
            box-shadow: 0 4px 10px rgba(15,23,42,.22);
            pointer-events: auto;
          }
          .gleisplan-street-width-handle {
            left: 50%;
            bottom: -7px;
            width: 30px;
            height: 14px;
            transform: translateX(-50%);
            border-radius: 4px;
            cursor: ns-resize;
          }
          .gleisplan-rotate-handle {
            left: 50%;
            top: -34px;
            width: 24px;
            height: 24px;
            transform: translateX(-50%);
            border-radius: 50%;
            cursor: grab;
          }
          .gleisplan-rotate-handle::before {
            content: "↻";
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #1d4ed8;
            font-size: 15px;
            font-weight: 900;
          }
          .gleisplan-curve-handle {
            left: -9px;
            bottom: -9px;
            width: 18px;
            height: 18px;
            transform: rotate(45deg);
            border-radius: 3px;
            cursor: nwse-resize;
          }
          .gleisplan-editor-item-label {
            position: relative;
            z-index: 1;
            font-size: .9rem;
            line-height: 1.05;
            font-weight: 900;
            text-align: center;
            overflow-wrap: anywhere;
          }
          .gleisplan-editor-anchor-label {
            position: absolute;
            left: 50%;
            top: -1.15rem;
            transform: translateX(-50%);
            color: #0f172a;
            font-size: .68rem;
            line-height: 1;
            font-weight: 900;
            white-space: nowrap;
            pointer-events: none;
          }
          .gleisplan-editor-item-type {
            position: relative;
            z-index: 1;
            font-size: .68rem;
            line-height: 1;
            font-weight: 800;
            opacity: .68;
            text-transform: uppercase;
          }
          .gleisplan-editor-hall-title {
            position: relative;
            z-index: 1;
            color: #111827;
            font-size: .78rem;
            line-height: 1.05;
            font-weight: 900;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            pointer-events: none;
          }
          .gleisplan-editor-hall-grid {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 4px;
            width: 100%;
            height: calc(100% - 18px);
            margin-top: 5px;
            pointer-events: none;
          }
          .gleisplan-editor-hall-cell {
            min-width: 0;
            min-height: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 2px;
            padding: 3px 4px;
            border: 1px solid rgba(15,23,42,.24);
            background: rgba(248,250,252,.72);
          }
          .gleisplan-editor-hall-track {
            color: #111827;
            font-size: .70rem;
            line-height: 1;
            font-weight: 900;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .gleisplan-editor-hall-position {
            color: #475569;
            font-size: .58rem;
            line-height: 1;
            font-weight: 800;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .gleisplan-editor-connection {
            position: absolute;
            z-index: 6;
            height: 5px;
            background: #dc2626;
            border-radius: 0;
            transform-origin: left center;
            pointer-events: none;
          }
          .gleisplan-editor-connection.cfg-street {
            z-index: 1;
            height: 14px;
            background: rgba(156,163,175,.44);
          }
          .gleisplan-editor-connection-svg {
            position: absolute;
            inset: 0;
            z-index: 6;
            width: 100%;
            height: 100%;
            pointer-events: none;
            overflow: visible;
          }
          .gleisplan-editor-connection-svg.cfg-street {
            z-index: 1;
          }
          .gleisplan-editor-connection-path {
            fill: none;
            stroke: #dc2626;
            stroke-width: 4px;
            stroke-linecap: round;
            stroke-linejoin: round;
            vector-effect: non-scaling-stroke;
            filter: drop-shadow(0 0 1px rgba(127,29,29,.24));
            pointer-events: none;
          }
          .gleisplan-editor-connection-svg.is-connected-selected .gleisplan-editor-connection-path,
          .gleisplan-editor-connection-svg.is-connection-selected .gleisplan-editor-connection-path,
          .gleisplan-editor-connection-path.is-connection-selected,
          .gleisplan-editor-connection-path.is-connected-selected {
            stroke: #b91c1c;
            stroke-width: 6px;
            filter: drop-shadow(0 0 3px rgba(127,29,29,.36));
          }
          .gleisplan-editor-connection-hit-path {
            fill: none;
            stroke: rgba(0,0,0,0);
            stroke-width: 44px;
            stroke-linecap: round;
            stroke-linejoin: round;
            vector-effect: non-scaling-stroke;
            pointer-events: stroke;
            cursor: grab;
          }
          .gleisplan-editor-connection-hit-path.is-connected-selected,
          .gleisplan-editor-connection-hit-path.is-connection-selected {
            stroke-width: 52px;
          }
          .gleisplan-editor-connection-hit-path:active {
            cursor: grabbing;
          }
          .gleisplan-editor-connection-svg.cfg-street .gleisplan-editor-connection-path {
            stroke: rgba(156,163,175,.72);
            stroke-width: 14px;
            filter: none;
          }
          .gleisplan-editor-connection-label {
            position: absolute;
            z-index: 11;
            transform: translate(-50%, -50%);
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(248,250,252,.9);
            color: #0f172a;
            border: 1px solid rgba(15,23,42,.22);
            font-size: .72rem;
            line-height: 1;
            font-weight: 900;
            white-space: nowrap;
            pointer-events: none;
          }
          .gleisplan-editor-connection-label.is-connected-selected,
          .gleisplan-editor-connection-label.is-connection-selected {
            border-color: rgba(185,28,28,.55);
            color: #991b1b;
            box-shadow: 0 0 0 2px rgba(248,113,113,.16);
          }
          .gleisplan-editor-board.trace-fade-foreground .gleisplan-editor-connection-svg:not(.is-connected-selected):not(.is-connection-selected) .gleisplan-editor-connection-path {
            opacity: .28;
            stroke-width: 3px;
          }
          .gleisplan-editor-board.trace-fade-foreground .gleisplan-editor-connection-svg.is-connected-selected .gleisplan-editor-connection-path,
          .gleisplan-editor-board.trace-fade-foreground .gleisplan-editor-connection-svg.is-connection-selected .gleisplan-editor-connection-path,
          .gleisplan-editor-board.trace-fade-foreground .gleisplan-editor-connection-path.is-connected-selected,
          .gleisplan-editor-board.trace-fade-foreground .gleisplan-editor-connection-path.is-connection-selected {
            opacity: 1;
            stroke-width: 7px;
          }
          .gleisplan-editor-board.trace-fade-foreground .gleisplan-editor-connection-label:not(.is-connected-selected):not(.is-connection-selected) {
            opacity: .58;
          }
          .gleisplan-editor-board.hide-editor-labels .gleisplan-editor-connection-label,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-editor-item-label,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-editor-anchor-label,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-editor-hall-title,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-editor-hall-track,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-editor-hall-position,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-switch-node-label,
          .gleisplan-editor-board.hide-editor-labels .gleisplan-buffer-stop-label {
            display: none;
          }
          .gleisplan-connection-curve-handle {
            position: absolute;
            z-index: 14;
            width: 18px;
            height: 18px;
            transform: translate(-50%, -50%) rotate(45deg);
            border: 2px solid #1d4ed8;
            border-radius: 4px;
            background: #f8fafc;
            box-shadow: 0 5px 12px rgba(15,23,42,.24);
            cursor: grab;
            pointer-events: auto;
            touch-action: none;
          }
          .gleisplan-connection-path-point-handle {
            position: absolute;
            z-index: 18;
            display: none;
            width: 22px;
            height: 22px;
            transform: translate(-50%, -50%);
            border: 3px solid #1d4ed8;
            border-radius: 999px;
            background: #f8fafc;
            box-shadow: 0 0 0 3px rgba(248,250,252,.85), 0 7px 16px rgba(15,23,42,.30);
            cursor: grab;
            pointer-events: auto;
            touch-action: none;
          }
          .gleisplan-connection-path-point-handle.is-connection-selected,
          .gleisplan-connection-path-point-handle.is-dragging {
            display: block;
          }
          .gleisplan-connection-curve-handle::before {
            content: "";
            position: absolute;
            inset: 4px;
            border-radius: 2px;
            background: #1d4ed8;
          }
          .gleisplan-connection-curve-handle.is-dragging {
            cursor: grabbing;
            z-index: 30;
            box-shadow: 0 10px 22px rgba(15,23,42,.34);
          }
          .gleisplan-connection-path-point-handle.is-dragging {
            cursor: grabbing;
            z-index: 31;
            box-shadow: 0 10px 22px rgba(15,23,42,.34);
          }
          @media (max-width: 1200px) {
            .gleisplan-layout {
              grid-template-columns: 1fr;
            }
            .gleisplan-map-middle {
              grid-template-columns: 1fr;
            }
            .gleisplan-track-north {
              max-width: 100%;
              margin-left: 0;
            }
          }
          @media (max-width: 760px) {
            .gleisplan-map {
              min-height: 0;
              padding: 10px;
            }
            .gleishalle-grid-2x2 {
              grid-template-columns: 1fr;
            }
            .gleishalle-cell:nth-child(odd),
            .gleishalle-cell:nth-child(-n+2) {
              border-right: 0;
              border-bottom: 1px solid rgba(226,232,240,.32);
            }
            .gleishalle-cell:last-child {
              border-bottom: 0;
            }
          }
          .gleisplan-map-pdf {
            position: relative;
            aspect-ratio: 1501 / 1058;
            min-height: 720px;
            background:
              linear-gradient(rgba(255,255,255,.028) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,.028) 1px, transparent 1px),
              #f8fafc;
            background-size: 42px 42px;
            color: #0f172a;
            border-color: rgba(15,23,42,.35);
          }
          .gleisplan-map-pdf::before {
            content: "";
            position: absolute;
            inset: 2.4% 1.8%;
            border: 2px solid rgba(15,23,42,.52);
            pointer-events: none;
          }
          .gleisplan-map-building {
            position: absolute;
            background: rgba(254,202,202,.62);
            border: 1px solid rgba(248,113,113,.24);
            z-index: 1;
          }
          .building-north {
            left: 17%;
            top: 4%;
            width: 26%;
            height: 22%;
            clip-path: polygon(0 0, 50% 0, 50% 70%, 100% 70%, 100% 100%, 0 100%);
          }
          .building-yard {
            left: 33%;
            top: 29%;
            width: 30%;
            height: 50%;
            clip-path: polygon(0 0, 100% 0, 100% 70%, 80% 70%, 80% 100%, 30% 100%, 30% 84%, 0 84%);
          }
          .building-kaltlager {
            left: 4%;
            bottom: 16%;
            width: 8%;
            height: 13%;
            background: #d1d5db;
            border-color: rgba(15,23,42,.42);
            transform: rotate(-45deg);
          }
          .gleisplan-building-label,
          .gleisplan-switch-label {
            position: absolute;
            z-index: 4;
            color: #0f172a;
            font-weight: 900;
            pointer-events: none;
          }
          .label-kaltlager {
            left: 5.2%;
            bottom: 20%;
            font-size: .95rem;
          }
          .label-tank {
            left: 61.5%;
            top: 43.5%;
            padding: 4px 8px;
            background: #15803d;
            color: #fef3c7;
            border-radius: 2px;
            font-size: .9rem;
          }
          .switch-a8 {
            left: 46%;
            top: 43.4%;
          }
          .switch-a5 {
            right: 9.5%;
            top: 60.5%;
          }
          .gleisplan-curve {
            position: absolute;
            border: 4px solid transparent;
            z-index: 2;
            pointer-events: none;
          }
          .curve-north {
            left: 6%;
            top: 7%;
            width: 82%;
            height: 28%;
            border-top-color: #111827;
            border-radius: 50% 50% 0 0;
            transform: rotate(8deg);
          }
          .curve-east {
            right: 5.5%;
            top: 20%;
            width: 18%;
            height: 53%;
            border-right-color: #dc2626;
            border-bottom-color: #dc2626;
            border-radius: 0 0 70% 0;
          }
          .curve-west {
            left: 5%;
            top: 47%;
            width: 38%;
            height: 17%;
            border-bottom-color: #dc2626;
            border-radius: 0 0 55% 55%;
          }
          .gleisplan-track-node {
            position: absolute;
            z-index: 8;
            min-width: 150px;
            max-width: 245px;
            padding: 8px;
            background: rgba(255,255,255,.92);
            border: 1px solid rgba(15,23,42,.28);
            border-radius: 8px;
            box-shadow: 0 10px 24px rgba(15,23,42,.16);
            overflow: visible;
          }
          .gleisplan-track-node > * {
            position: relative;
            z-index: 1;
          }
          .gleisplan-layout-object {
            position: absolute;
            transform-origin: center center;
          }
          .gleisplan-map-building,
          .gleisplan-map-street {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px;
            background: var(--layout-color, rgba(254,202,202,.62));
            border: 1px solid rgba(15,23,42,.28);
            border-radius: 4px;
          }
          .gleisplan-map-building {
            z-index: 1;
          }
          .gleisplan-map-street {
            z-index: 0;
            padding: 0 8px;
            overflow: visible;
            background: transparent;
            border: 0;
            border-radius: 0;
            opacity: 1;
            transform-origin: left center;
          }
          .gleisplan-map-street::before {
            content: "";
            position: absolute;
            inset: 0;
            background: var(--layout-color, #d1d5db);
            border: 0;
            border-radius: var(--curve-radius, 0);
            pointer-events: none;
          }
          .gleisplan-layout-label {
            position: relative;
            z-index: 1;
            color: #0f172a;
            font-size: .9rem;
            line-height: 1.05;
            font-weight: 900;
            text-align: center;
            overflow-wrap: anywhere;
          }
          .gleisplan-map-switch {
            z-index: 10;
            background: transparent;
            border: 0;
            box-shadow: none;
          }
          .gleisplan-map-buffer-stop {
            z-index: 10;
            background: transparent;
            border: 0;
            box-shadow: none;
          }
          .gleisplan-switch-node-label {
            position: absolute;
            left: 50%;
            top: -1.45rem;
            transform: translateX(-50%);
            color: #0f172a;
            font-size: .82rem;
            font-weight: 900;
            text-align: center;
            white-space: nowrap;
            pointer-events: none;
          }
          .gleisplan-switch-symbol {
            position: relative;
            width: 100%;
            height: 100%;
            overflow: visible;
          }
          .gleisplan-switch-symbol-editor {
            width: 100%;
            height: 100%;
          }
          .gleisplan-switch-svg {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: visible;
            pointer-events: none;
          }
          .gleisplan-switch-svg-rail {
            stroke: #dc2626;
            stroke-width: 5;
            stroke-linecap: square;
            stroke-linejoin: round;
            vector-effect: non-scaling-stroke;
            filter: drop-shadow(0 0 1px rgba(127,29,29,.22));
          }
          .gleisplan-switch-main-rail,
          .gleisplan-switch-branch-rail {
            position: absolute;
            left: 0;
            top: 50%;
            height: 5px;
            border-radius: 999px;
            background: #dc2626;
            box-shadow: 0 0 0 1px rgba(127,29,29,.22);
            transform-origin: left center;
          }
          .gleisplan-switch-main-rail {
            width: 100%;
            top: 28%;
            transform: translateY(-50%);
          }
          .gleisplan-switch-branch-rail {
            left: 0;
            top: 28%;
            width: 80%;
            transform-origin: right center;
            transform: translateY(-50%) rotate(-22deg);
          }
          .gleisplan-switch-hatch {
            position: absolute;
            left: 38%;
            top: 20%;
            width: 28%;
            height: 60%;
            transform: skewX(-18deg);
            background:
              repeating-linear-gradient(
                90deg,
                rgba(15,23,42,.64) 0,
                rgba(15,23,42,.64) 2px,
                transparent 2px,
                transparent 7px
              );
            opacity: .72;
          }
          .gleisplan-switch-heel {
            position: absolute;
            right: 20%;
            top: calc(28% - 5px);
            width: 10px;
            height: 10px;
            background: #f8fafc;
            border: 2px solid #1d4ed8;
            transform: rotate(45deg);
          }
          .gleisplan-switch-port-label {
            position: absolute;
            z-index: 2;
            width: 12px;
            height: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: rgba(248,250,252,.94);
            border: 1px solid rgba(127,29,29,.35);
            color: #991b1b;
            font-size: .58rem;
            line-height: 1;
            font-weight: 900;
            pointer-events: none;
          }
          .gleisplan-map-pdf .gleisplan-switch-port-label {
            display: none;
          }
          .gleisplan-map-pdf .gleisplan-switch-heel {
            display: none;
          }
          .gleisplan-switch-angle-handle {
            pointer-events: auto;
            cursor: grab;
            box-shadow: 0 0 0 2px rgba(37,99,235,.24);
          }
          .gleisplan-switch-angle-handle.is-dragging {
            cursor: grabbing;
            background: #dbeafe;
            border-color: #2563eb;
          }
          .gleisplan-switch-port-label.port-1 {
            right: -6px;
            top: calc(28% - 6px);
          }
          .gleisplan-switch-port-label.port-2 {
            left: -6px;
            top: calc(28% - 6px);
          }
          .gleisplan-switch-port-label.port-3 {
            left: calc(6% - 6px);
            top: calc(135% - 6px);
          }
          .gleisplan-switch-anchor-debug {
            position: absolute;
            z-index: 4;
            width: 10px;
            height: 10px;
            border-radius: 999px;
            display: none;
            align-items: center;
            justify-content: center;
            border: 1px solid rgba(15,23,42,.65);
            color: #0f172a;
            font-size: .46rem;
            font-weight: 900;
            line-height: 1;
            pointer-events: none;
            box-shadow: 0 0 0 2px rgba(255,255,255,.78);
          }
          .gleisplan-switch-anchor-debug::after {
            content: attr(data-anchor);
            position: absolute;
            left: 12px;
            top: -3px;
            padding: 1px 4px;
            border-radius: 4px;
            background: rgba(255,255,255,.9);
            white-space: nowrap;
          }
          .gleisplan-switch-anchor-debug.anchor-stem { background: #60a5fa; }
          .gleisplan-switch-anchor-debug.anchor-straight { background: #22c55e; }
          .gleisplan-switch-anchor-debug.anchor-branch { background: #fb923c; }
          .show-switch-anchors .gleisplan-switch-anchor-debug {
            display: flex;
          }
          .gleisplan-buffer-stop-symbol {
            position: relative;
            width: 100%;
            height: 100%;
            overflow: visible;
          }
          .gleisplan-buffer-stop-symbol-editor {
            width: 100%;
            height: 100%;
          }
          .gleisplan-buffer-stop-rail {
            position: absolute;
            left: calc(50% - 2px);
            top: 18%;
            width: 4px;
            height: 92%;
            border-radius: 999px;
            background: #dc2626;
            box-shadow: 0 0 0 1px rgba(127,29,29,.16);
          }
          .gleisplan-buffer-stop-beam {
            position: absolute;
            left: 8%;
            right: 8%;
            top: 8%;
            height: 5px;
            border-radius: 2px;
            background: #dc2626;
            box-shadow: 0 0 0 1px rgba(127,29,29,.16);
          }
          .gleisplan-buffer-stop-post {
            display: none;
          }
          .gleisplan-buffer-stop-label {
            position: absolute;
            left: 50%;
            top: -1.45rem;
            transform: translateX(-50%);
            color: #0f172a;
            font-size: .82rem;
            font-weight: 900;
            text-align: center;
            white-space: nowrap;
            pointer-events: none;
          }
          .gleisplan-connection {
            position: absolute;
            z-index: 6;
            height: 5px;
            background: #dc2626;
            border-radius: 0;
            transform-origin: left center;
            box-shadow: 0 0 0 1px rgba(127,29,29,.24);
            pointer-events: none;
          }
          .gleisplan-connection-street {
            z-index: 1;
            height: 14px;
            background: rgba(156,163,175,.44);
            box-shadow: none;
          }
          .gleisplan-connection-svg {
            position: absolute;
            inset: 0;
            z-index: 6;
            width: 100%;
            height: 100%;
            pointer-events: none;
            overflow: visible;
          }
          .gleisplan-connection-svg.connection-street {
            z-index: 1;
          }
          .gleisplan-connection-path {
            fill: none;
            stroke: #dc2626;
            stroke-width: 4px;
            stroke-linecap: round;
            stroke-linejoin: round;
            vector-effect: non-scaling-stroke;
            filter: drop-shadow(0 0 1px rgba(127,29,29,.24));
          }
          .gleisplan-connection-svg.connection-street .gleisplan-connection-path {
            stroke: rgba(156,163,175,.72);
            stroke-width: 14px;
            filter: none;
          }
          .gleisplan-connection-label {
            position: absolute;
            z-index: 11;
            transform: translate(-50%, -50%);
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(248,250,252,.88);
            color: #0f172a;
            border: 1px solid rgba(15,23,42,.20);
            font-size: .72rem;
            line-height: 1;
            font-weight: 900;
            white-space: nowrap;
            pointer-events: none;
          }
          .gleisplan-connection-info {
            position: absolute;
            z-index: 12;
            min-width: 118px;
            max-width: 170px;
            transform: translate(-50%, -50%);
            pointer-events: none;
          }
          .gleisplan-connection-info-label {
            display: inline-block;
            margin: 0 0 4px 0;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(248,250,252,.88);
            color: #0f172a;
            border: 1px solid rgba(15,23,42,.20);
            font-size: .72rem;
            line-height: 1;
            font-weight: 900;
            white-space: nowrap;
          }
          .gleisplan-connection-info .gleisplan-vehicle-card {
            margin-top: 0;
          }
          .cfg-gleisplan-list-row {
            cursor: pointer;
            transition: background .12s ease, border-color .12s ease, box-shadow .12s ease;
          }
          .cfg-gleisplan-list-row.is-selected {
            background: rgba(245,158,11,.18);
            border-color: rgba(245,158,11,.8);
            box-shadow: inset 4px 0 0 #f59e0b;
          }
          .cfg-gleisplan-list-row.is-connection-source {
            background: rgba(245,158,11,.18);
            border-color: rgba(245,158,11,.8);
            box-shadow: inset 4px 0 0 #f59e0b;
          }
          .cfg-selected-editor {
            width: 100%;
            margin-top: 14px;
            padding: 12px;
            background: rgba(15,23,42,.06);
            border: 1px solid rgba(37,99,235,.34);
            border-radius: 10px;
          }
          .gleisplan-track-node-label {
            color: #1d4ed8;
            font-size: 1.05rem;
            line-height: 1;
            font-weight: 900;
          }
          .gleisplan-track-node-title {
            color: #475569;
            font-size: .72rem;
            line-height: 1;
            font-weight: 800;
            text-align: right;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .gleisplan-track-node-line {
            position: absolute;
            left: -1px;
            right: -1px;
            top: 50%;
            height: 4px;
            margin: 0;
            border-radius: 999px;
            background: #dc2626;
            box-shadow: 0 0 0 1px rgba(127,29,29,.26);
            transform: translateY(-50%);
            z-index: 0;
          }
          .track-gl12-nord { left: 7%; top: 6.5%; transform: rotate(8deg); }
          .track-urd { left: 41%; top: 13%; transform: rotate(7deg); }
          .track-gl10 { left: 27.5%; top: 27%; }
          .track-gl1a { left: 12.5%; top: 33.5%; }
          .track-gl1b { left: 10.4%; top: 39.5%; }
          .track-gl1 { left: 35.5%; top: 39%; }
          .track-gl2 { left: 41.5%; top: 44%; }
          .track-ara { left: 48%; top: 47.5%; }
          .track-gl3 { left: 56%; top: 51.5%; }
          .track-gl4-ost { right: 23%; top: 57%; }
          .track-gl5-ost { right: 23%; top: 64%; }
          .track-gl12-ost { right: 12%; top: 23%; transform: rotate(10deg); }
          .gleishalle-panel-map {
            position: absolute;
            left: 23%;
            top: 58%;
            width: 36%;
            min-width: 0;
            z-index: 5;
            background: rgba(209,213,219,.94);
            color: #0f172a;
            border-color: rgba(15,23,42,.44);
          }
          .gleishalle-panel-map .gleishalle-title,
          .gleishalle-panel-map .gleishalle-area {
            color: #0f172a;
          }
          .gleishalle-panel-map .gleishalle-source,
          .gleishalle-panel-map .gleishalle-position {
            color: #334155;
          }
          .gleishalle-panel-map .gleishalle-cell {
            min-height: 135px;
            background: rgba(248,250,252,.78);
          }
          .gleisplan-vehicle-card-compact {
            margin-top: 7px;
            padding: 7px;
            border-radius: 8px;
          }
          .gleisplan-vehicle-card-compact .gleisplan-vehicle-title {
            font-size: 1.08rem;
          }
          .gleisplan-vehicle-card-compact .gleisplan-vehicle-meta {
            font-size: .78rem;
          }
          .gleisplan-track-node .gleisplan-empty-vehicle {
            min-height: 42px;
            margin-top: 5px;
            background: rgba(226,232,240,.65);
          }
          .gleisplan-track-node .gleisplan-empty-label {
            font-size: .76rem;
            color: #64748b;
          }
          @media (max-width: 1200px) {
            .gleisplan-map-pdf {
              min-height: 620px;
              overflow-x: auto;
            }
            .gleisplan-track-node {
              min-width: 138px;
              max-width: 210px;
            }
            .gleishalle-panel-map {
              width: 42%;
              left: 20%;
            }
          }
          @media (max-width: 760px) {
            .gleisplan-map-pdf {
              aspect-ratio: auto;
              min-height: 1120px;
            }
            .gleisplan-map-building,
            .gleisplan-curve,
            .gleisplan-building-label,
            .gleisplan-switch-label {
              display: none;
            }
            .gleisplan-track-node,
            .gleishalle-panel-map {
              position: static;
              transform: none !important;
              width: auto;
              max-width: none;
              margin-bottom: 10px;
            }
            .gleishalle-panel-map .gleishalle-grid-2x2 {
              grid-template-columns: 1fr;
            }
          }
          .dialog-card {
            min-width: min(92vw, 760px);
            max-width: min(92vw, 760px);
            background: #1f2937;
            color: #f3f4f6;
            border: 1px solid rgba(255,255,255,.12);
          }
          .dialog-card,
          .dialog-card * {
            color: #f3f4f6 !important;
          }
          .dialog-card .q-field__native,
          .dialog-card .q-field__input,
          .dialog-card .q-field__label,
          .dialog-card .q-field__marginal,
          .dialog-card .q-field__prepend,
          .dialog-card .q-field__append,
          .dialog-card textarea,
          .dialog-card input {
            color: #ffffff !important;
          }
          .dialog-card .q-field__control {
            background: #1f2937 !important;
          }
          .dialog-card .q-field__control:before,
          .dialog-card .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .dialog-card .q-checkbox__label {
            color: #ffffff !important;
          }
          .dialog-title {
            font-size: 1.35rem;
            font-weight: 900;
          }
          .admin-login-input .q-field__native,
          .admin-login-input .q-field__input,
          .admin-login-input input,
          .admin-login-input textarea {
            color: #ffffff !important;
          }
          .admin-login-input .q-field__label,
          .admin-login-input .q-field__marginal,
          .admin-login-input .q-field__prepend,
          .admin-login-input .q-field__append {
            color: rgba(255,255,255,.95) !important;
          }
          .admin-login-input .q-field__control:before,
          .admin-login-input .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .admin-login-cancel .q-btn__content {
            color: #ffffff !important;
            font-weight: 800 !important;
          }
          .upload-panel {
            background: #262730;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
          }
          .upload-actions-card {
            min-width: 260px;
          }
          .import-diff-card {
            gap: 10px;
          }
          .missing-open-card {
            gap: 12px;
            border-color: rgba(251,146,60,.55) !important;
            box-shadow: 0 0 0 1px rgba(251,146,60,.12);
          }
          .missing-open-title {
            font-size: 1.5rem;
            line-height: 1.2;
            font-weight: 900;
            color: #ef4444 !important;
          }
          .missing-open-vehicle {
            font-size: 2rem;
            line-height: 1.1;
            font-weight: 900;
          }
          .missing-open-item {
            background: rgba(255,255,255,.04);
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 12px;
          }
          .upload-page,
          .upload-page * {
            color: #f3f4f6;
          }
          .upload-page .q-field__native,
          .upload-page .q-field__input,
          .upload-page .q-field__label,
          .upload-page .q-field__marginal,
          .upload-page .q-field__prepend,
          .upload-page .q-field__append {
            color: #ffffff !important;
          }
          .upload-page .q-checkbox__label {
            color: #ffffff !important;
          }
          .upload-field .q-field__control:before,
          .upload-field .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .upload-page .q-uploader {
            background: #1f2937 !important;
            border: 1px solid rgba(255,255,255,.16) !important;
            border-radius: 12px !important;
            color: #ffffff !important;
          }
          .upload-page .q-uploader__header,
          .upload-page .q-uploader__list {
            color: #ffffff !important;
          }
          .upload-page .q-table__container,
          .upload-page .q-table__bottom,
          .upload-page .q-table__middle,
          .upload-page .q-table,
          .upload-page .q-table thead tr,
          .upload-page .q-table tbody tr,
          .upload-page .q-table th,
          .upload-page .q-table td {
            background: #262730 !important;
            color: #ffffff !important;
          }
          .upload-page .q-table th,
          .upload-page .q-table td {
            border-color: rgba(255,255,255,.12) !important;
          }
          .upload-preview-table .q-table td {
            white-space: pre-line !important;
          }
          .archive-page,
          .archive14-page {
            color: #f3f4f6;
          }
          .archive-page .q-field__native,
          .archive-page .q-field__input,
          .archive-page .q-field__label,
          .archive-page .q-field__marginal,
          .archive-page .q-field__prepend,
          .archive-page .q-field__append,
          .archive14-page .q-field__native,
          .archive14-page .q-field__input,
          .archive14-page .q-field__label,
          .archive14-page .q-field__marginal,
          .archive14-page .q-field__prepend,
          .archive14-page .q-field__append {
            color: #ffffff !important;
          }
          .archive-field .q-field__control {
            background: #262730 !important;
          }
          .archive-field .q-field__control:before,
          .archive-field .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .archive-page .q-table__container,
          .archive-page .q-table__bottom,
          .archive-page .q-table__middle,
          .archive-page .q-table,
          .archive-page .q-table thead tr,
          .archive-page .q-table tbody tr,
          .archive-page .q-table th,
          .archive-page .q-table td,
          .archive14-page .q-table__container,
          .archive14-page .q-table__bottom,
          .archive14-page .q-table__middle,
          .archive14-page .q-table,
          .archive14-page .q-table thead tr,
          .archive14-page .q-table tbody tr,
          .archive14-page .q-table th,
          .archive14-page .q-table td {
            background: #262730 !important;
            color: #ffffff !important;
          }
          .archive-page .q-table th,
          .archive-page .q-table td,
          .archive14-page .q-table th,
          .archive14-page .q-table td {
            border-color: rgba(255,255,255,.12) !important;
          }
          .area-select .q-field__native,
          .area-select .q-field__input,
          .area-select .q-field__label,
          .area-select .q-field__marginal,
          .area-select .q-field__prepend,
          .area-select .q-field__append {
            color: #ffffff !important;
          }
          .area-select .q-field__control {
            background: #262730 !important;
          }
          .area-select .q-field__control:before,
          .area-select .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .area-select-popup,
          .area-select-popup .q-virtual-scroll__content,
          .area-select-popup .q-list {
            background: #262730 !important;
            color: #ffffff !important;
          }
          .q-menu.area-select-popup {
            z-index: 10000 !important;
            max-height: min(50vh, 420px) !important;
            overflow-y: auto !important;
            transform: none !important;
          }
          .area-select-popup .q-item,
          .area-select-popup .q-item__label {
            color: #ffffff !important;
          }
          .area-select-popup .q-item:hover,
          .area-select-popup .q-item.q-manual-focusable--focused,
          .area-select-popup .q-item.q-item--active {
            background: rgba(255,255,255,.14) !important;
          }
          .prio-day-input .q-field__native,
          .prio-day-input .q-field__input,
          .prio-day-input .q-field__label,
          .prio-day-input .q-field__marginal,
          .prio-day-input .q-field__prepend,
          .prio-day-input .q-field__append {
            color: #ffffff !important;
          }
          .prio-day-input .q-field__control {
            background: #262730 !important;
          }
          .prio-day-input .q-field__control:before,
          .prio-day-input .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .prio-day-input .q-icon,
          .prio-day-input .q-field__append .q-icon {
            color: #ffffff !important;
            fill: #ffffff !important;
            opacity: 1 !important;
          }
          .prio-day-input .q-field__append svg,
          .prio-day-input .q-field__append path {
            fill: #ffffff !important;
          }
          .prio-day-input input[type="date"] {
            color: #ffffff !important;
            background: #262730 !important;
            color-scheme: dark;
          }
          .prio-day-input input[type="date"]::-webkit-calendar-picker-indicator {
            filter: invert(1) brightness(2) saturate(0) !important;
            opacity: 1 !important;
          }
          .dialog-progress {
            font-size: 1.05rem;
            font-weight: 700;
          }
          .dialog-check {
            font-size: 1.02rem;
            font-weight: 700;
          }
          .dialog-check-row {
            margin: 8px 0;
          }
          .dialog-frist-header,
          .dialog-frist-check-row {
            display: grid !important;
            grid-template-columns: 112px minmax(220px, 1fr) 72px;
            align-items: start;
            column-gap: 12px;
          }
          .dialog-frist-header {
            margin-top: 8px;
            margin-bottom: 2px;
          }
          .dialog-frist-head {
            font-size: .82rem;
            font-weight: 900;
            text-transform: uppercase;
            color: rgba(229,237,246,.82);
            line-height: 1.05;
          }
          .dialog-frist-done-head {
            text-align: center;
          }
          .dialog-check-box {
            min-height: 0 !important;
            padding-top: 0 !important;
          }
          .dialog-check-title {
            font-size: 1.04rem;
            font-weight: 900;
            line-height: 1.15;
            color: #ffffff;
          }
          .dialog-check-meta {
            margin-top: 2px;
            font-size: .94rem;
            font-weight: 700;
            line-height: 1.12;
            color: rgba(229, 237, 246, .78);
          }
          .dialog-check-done,
          .dialog-card .dialog-check-done,
          .dialog-check-done .q-checkbox__label {
            color: #22c55e !important;
          }
          .dialog-check-working,
          .dialog-card .dialog-check-working {
            color: #60a5fa !important;
          }
          .dialog-work-check {
            min-width: 0;
          }
          .dialog-card .dialog-work-check .q-checkbox__bg,
          .task-frist-check-row .task-work-box .q-checkbox__bg {
            position: relative;
          }
          .dialog-card .dialog-work-check .q-checkbox__inner--truthy .q-checkbox__bg,
          .task-frist-check-row .task-work-box .q-checkbox__inner--truthy .q-checkbox__bg {
            background: #2563eb !important;
            border-color: #60a5fa !important;
          }
          .dialog-card .dialog-work-check .q-checkbox__inner--truthy .q-checkbox__check,
          .task-frist-check-row .task-work-box .q-checkbox__inner--truthy .q-checkbox__check {
            display: none !important;
          }
          .dialog-card .dialog-work-check .q-checkbox__inner--truthy .q-checkbox__bg::after,
          .task-frist-check-row .task-work-box .q-checkbox__inner--truthy .q-checkbox__bg::after {
            content: "";
            position: absolute;
            left: 5px;
            right: 5px;
            top: 50%;
            height: 3px;
            border-radius: 999px;
            background: #ffffff;
            transform: translateY(-50%);
          }
          .ausseneinsatz-radio {
            margin-top: 10px;
            gap: 18px;
          }
          .ausseneinsatz-radio .q-radio {
            padding: 10px 0;
          }
          .ausseneinsatz-radio .q-radio__label {
            font-size: 1.38rem;
            font-weight: 800;
            line-height: 1.28;
            padding-left: 10px;
          }
          .ausseneinsatz-radio .q-radio__inner {
            font-size: 3rem;
          }
          .task-check {
            font-size: 1.05rem;
            font-weight: 700;
            line-height: 1.15;
          }
          .task-check-list {
            gap: 0;
          }
          .task-check-list .task-check-row {
            margin-bottom: 10px;
          }
          .task-check-list .task-check-row:last-child {
            margin-bottom: 0;
          }
          .task-frist-header,
          .task-frist-check-row {
            display: grid !important;
            grid-template-columns: 72px minmax(0, 1fr) 58px;
            align-items: start;
            column-gap: 7px;
          }
          .task-frist-header {
            margin-bottom: 5px;
          }
          .task-frist-head {
            font-size: 11px;
            font-weight: 900;
            text-transform: uppercase;
            color: rgba(229,237,246,.82);
            line-height: 1.05;
          }
          .task-frist-done-head {
            text-align: center;
          }
          .task-check-text {
            white-space: pre-wrap;
            font-size: 18px;
            font-weight: 700;
            line-height: 1.08;
            opacity: .95;
            margin: 0;
          }
          .task-check-title {
            font-weight: 900;
            opacity: 1;
          }
          .task-check-meta {
            margin: 2px 0 0;
            font-size: 14px;
            font-weight: 700;
            line-height: 1.1;
            color: rgba(229, 237, 246, .78);
          }
          .task-check-done,
          .task-check-meta.task-check-done {
            color: #22c55e !important;
          }
          .task-check-working,
          .task-check-meta.task-check-working {
            color: #60a5fa !important;
          }
          .task-work-heading {
            font-size: 13px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0;
            color: rgba(229,237,246,.82);
          }
          .task-work-list .task-check-row {
            margin-bottom: 7px;
          }
          .task-work-text {
            font-size: 13px;
            font-weight: 800;
            line-height: 1.12;
            color: rgba(243,246,250,.90);
          }
          .task-check-box {
            margin-left: auto;
            min-height: 0 !important;
            padding: 0 !important;
          }
          .task-frist-check-row .task-check-box {
            margin-left: 0;
          }
          .task-work-box,
          .task-done-box {
            justify-self: center;
          }
          .task-check-box .q-checkbox__label {
            display: none;
          }
          .task-check-box .q-checkbox__inner {
            transform: scale(0.80);
            transform-origin: left center;
          }
          .q-checkbox .q-checkbox__bg {
            border: 2px solid #ffffff !important;
          }
          .q-checkbox.disabled .q-checkbox__bg,
          .q-checkbox--disabled .q-checkbox__bg {
            border-color: rgba(255,255,255,.72) !important;
          }
          .q-checkbox .q-checkbox__inner--truthy .q-checkbox__bg {
            background: #16a34a !important;
            border-color: #16a34a !important;
          }
          .q-checkbox .q-checkbox__inner--truthy .q-checkbox__check {
            color: #ffffff !important;
          }
          .task-status-sm {
            margin-top: 8px;
            font-size: 1rem;
            font-weight: 800;
            display: none !important;
          }
          .prio-card {
            min-height: 260px;
            background: #262730;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
          }
          .prio-title {
            font-size: 2rem;
            font-weight: 900;
            line-height: 1;
            text-decoration: underline;
          }
          .prio-item {
            border-bottom: 1px solid rgba(255,255,255,.08);
            padding: 8px 0;
          }
          .prio-main {
            font-size: 1.25rem;
            font-weight: 900;
            line-height: 1.1;
          }
          .prio-sub {
            font-size: 1rem;
            font-weight: 700;
            opacity: .9;
          }
          .shop-card {
            background: #262730;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
          }
          .shop-title {
            font-size: 2rem;
            font-weight: 900;
            color: #f3f4f6;
          }
          .shop-task {
            font-size: 1.2rem;
            font-weight: 700;
            color: #f3f4f6;
          }
          .shop-week-label {
            color: #f3f4f6;
            font-size: 1.15rem;
            font-weight: 800;
          }
          .week-plan-page {
            color: #f3f4f6;
          }
          .weekplan-week-label {
            color: #f3f4f6;
            font-size: 1.15rem;
            font-weight: 800;
          }
          .weekplan-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            width: 100%;
          }
          .weekplan-card {
            background: #262730;
            color: #f2f5f8;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            padding: 12px;
          }
          .weekplan-card-head {
            margin-bottom: 6px;
          }
          .weekplan-area {
            font-size: 1.7rem;
            font-weight: 900;
            line-height: 1;
          }
          .weekplan-days {
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 6px;
            width: 100%;
          }
          .weekplan-day {
            display: flex;
            flex-direction: column;
            gap: 8px;
            background: rgba(255,255,255,.03);
            border: 1px solid rgba(255,255,255,.07);
            border-radius: 12px;
            padding: 8px;
            min-width: 0;
          }
          .weekplan-day-today {
            border-color: rgba(255,217,102,.9);
            box-shadow: inset 0 0 0 1px rgba(255,217,102,.32);
          }
          .weekplan-day-name {
            font-size: .88rem;
            font-weight: 900;
            line-height: 1.1;
            color: #f3f4f6;
          }
          .weekplan-day-date {
            font-size: .78rem;
            font-weight: 700;
            color: rgba(243,244,246,.88);
          }
          .weekplan-slot {
            display: flex;
            flex-direction: column;
            gap: 2px;
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
            border-radius: 10px;
            padding: 8px 7px;
            border: 1px solid rgba(0,0,0,.08);
          }
          .weekplan-slot-busy {
            background: #4b5563;
            color: #ffffff;
          }
          .weekplan-slot-free {
            background: #93c47d;
            color: #000000;
          }
          .weekplan-slot-time {
            font-size: .68rem;
            font-weight: 900;
            opacity: .78;
            line-height: 1.1;
          }
          .weekplan-slot-main {
            font-size: .82rem;
            font-weight: 900;
            line-height: 1.15;
            word-break: break-word;
            overflow-wrap: anywhere;
          }
          .weekplan-slot-sub {
            min-height: .92rem;
            font-size: .7rem;
            font-weight: 700;
            line-height: 1.1;
            opacity: .9;
            overflow-wrap: anywhere;
          }
          .shop-shift-row {
            align-items: center;
          }
          .shop-shift-label {
            min-width: 220px;
            font-size: 2rem;
            font-weight: 900;
            line-height: 1.1;
          }
          .shop-shift-input .q-field__native,
          .shop-shift-input .q-field__input,
          .shop-shift-input .q-field__label,
          .shop-shift-input .q-field__marginal,
          .shop-shift-input .q-field__prepend,
          .shop-shift-input .q-field__append {
            color: #ffffff !important;
          }
          .shop-shift-input .q-field__native,
          .shop-shift-input .q-field__input {
            font-size: 1.75rem !important;
            font-weight: 900 !important;
          }
          .shop-shift-input .q-field__control:before,
          .shop-shift-input .q-field__control:after {
            border-color: rgba(255,255,255,.92) !important;
          }
          .tl-grid-4 {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            width: 100%;
          }
          .tl-grid-3 {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            width: 100%;
          }
          .tl-grid-1 {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 14px;
            width: 100%;
          }
          .tl-card {
            background: #262730;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            padding: 14px 16px;
            color: #f2f5f8;
          }
          .tl-card-title {
            margin: 0 0 10px 0;
            font-size: 2.5rem;
            line-height: 1.05;
            text-align: center;
            font-weight: 900;
          }
          .tl-card-head {
            margin-bottom: 10px;
          }
          .tl-card-title-inline {
            margin: 0;
          }
          .tl-card-next {
            color: #52c41a;
            font-size: 1rem;
            font-weight: 800;
            line-height: 1.2;
          }
          .tl-item {
            position: relative;
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
            padding: 6px 8px;
            margin: 0 0 6px 0;
            background: #313743;
            color: #ffffff;
            border: 1px solid rgba(0,0,0,.08);
            border-radius: 10px;
          }
          .tl-card .tl-item:last-child {
            margin-bottom: 0;
          }
          .tl-item-main {
            height: 92px;
            overflow: hidden;
          }
          .tl-item-main.now,
          .tl-item-main.shiftmate {
            height: 110px;
          }
          .tl-item.now,
          .tl-item.shiftmate {
            border-color: rgba(250,173,20,.55);
            box-shadow: 0 0 0 1px rgba(250,173,20,.20);
          }
          .tl-item.next {
            opacity: .92;
          }
          .tl-time {
            min-width: 150px;
            text-align: center;
            font-weight: 900;
            border-radius: 999px;
            padding: 6px 10px;
            line-height: 1;
            white-space: nowrap;
            border: 1px solid rgba(255,255,255,.10);
          }
          .tl-item.now .tl-time,
          .tl-item.shiftmate .tl-time {
            padding: 10px 14px;
            font-size: 1.25rem;
            min-width: 170px;
          }
          .tl-veh {
            font-weight: 900;
            font-size: 1.35rem;
            line-height: 1.15;
            margin: 0;
          }
          .tl-item.now .tl-veh,
          .tl-item.shiftmate .tl-veh {
            font-size: 2.25rem;
          }
          .tl-hint {
            opacity: .9;
            font-weight: 700;
            line-height: 1.05;
            margin: 0;
          }
          .tl-item-main .tl-veh,
          .tl-item-main .tl-hint {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .tl-veh-placeholder,
          .tl-hint-placeholder {
            visibility: hidden;
          }
          .tl-side-time {
            white-space: normal;
            line-height: 1.12;
            min-width: 240px;
            text-align: center;
          }
          .tl-side-veh {
            font-size: 1.8rem;
            line-height: 1.05;
          }
          .tl-side-content {
            min-width: 0;
          }
          .tl-side-hint {
            white-space: normal;
            overflow-wrap: anywhere;
            line-height: 1.15;
            margin-top: 2px;
          }
          .tl-side-check {
            margin-left: auto;
            align-self: flex-start;
          }
          .empty {
            opacity: .35;
            font-weight: 800;
          }
          .prio-note-row {
            margin-top: 10px;
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: start;
            gap: 12px;
          }
          .prio-note-wrap {
            margin-top: 0;
            padding: 14px 16px;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            background: #262730;
          }
          .prio-note-title {
            font-weight: 800;
            font-size: .95rem;
            margin: 0 0 6px 0;
            opacity: .9;
            color: #f3f4f6;
          }
          .prio-side-legend {
            justify-self: end;
            align-self: center;
            margin: 0;
          }
          .prio-note-item {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 8px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(255,255,255,.04);
          }
          .prio-note-time {
            font-weight: 900;
            color: #ffd966;
          }
          .prio-note-text {
            font-weight: 700;
            opacity: .92;
            color: #f3f4f6;
          }
          .prio-note-empty {
            font-weight: 700;
            color: #f3f4f6;
            opacity: .92;
          }
          .prio-page {
            gap: 12px;
            padding: 0 4px 22px 4px;
            color: #f2f5f8;
          }
          .prio-command-row {
            padding: 6px 2px 12px 2px;
            border-bottom: 1px solid rgba(148,163,184,.20);
          }
          .prio-page-title {
            margin: 0;
            line-height: 1.05;
            letter-spacing: 0;
          }
          .prio-command-tools {
            margin-left: 0;
          }
          .prio-control-label {
            color: #cbd5e1;
            font-size: .9rem;
            font-weight: 900;
            line-height: 1;
          }
          .prio-date-control {
            min-width: 210px;
          }
          .prio-external-btn {
            min-height: 56px;
          }
          .prio-deadline-legend {
            min-height: 54px;
            padding: 9px 12px;
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 12px;
            background: rgba(17,24,39,.72);
          }
          .prio-deadline-legend .legend-pill {
            width: 42px;
            height: 22px;
          }
          .prio-content {
            gap: 12px;
          }
          .prio-summary-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(150px, 1fr));
            gap: 10px;
            width: 100%;
          }
          .prio-stat {
            min-height: 74px;
            padding: 12px 14px;
            border-radius: 12px;
            border: 1px solid rgba(148,163,184,.20);
            background: #171d25;
            box-shadow: 0 14px 34px rgba(0,0,0,.18);
          }
          .prio-stat-slot { border-left: 5px solid #faad14; }
          .prio-stat-main { border-left: 5px solid #60a5fa; }
          .prio-stat-vehicles { border-left: 5px solid #31ccec; }
          .prio-stat-side { border-left: 5px solid #52c41a; }
          .prio-stat-value {
            color: #ffffff;
            font-size: 1.8rem;
            font-weight: 950;
            line-height: 1;
            letter-spacing: 0;
            overflow-wrap: anywhere;
          }
          .prio-stat-label {
            color: #cbd5e1;
            font-size: .95rem;
            font-weight: 800;
            line-height: 1.15;
            margin-top: 7px;
            letter-spacing: 0;
          }
          .prio-page .tl-grid-4,
          .prio-page .tl-grid-3,
          .prio-page .tl-grid-1 {
            gap: 12px;
          }
          .prio-page .tl-card {
            background: linear-gradient(180deg, #252b34 0%, #1d232b 100%);
            border: 1px solid rgba(148,163,184,.22);
            border-radius: 12px;
            padding: 14px !important;
            box-shadow: 0 18px 42px rgba(0,0,0,.24);
            overflow: hidden;
          }
          .prio-page .tl-card-title {
            font-size: 2rem;
            margin-bottom: 8px;
            text-decoration: none;
          }
          .prio-page .tl-item {
            min-height: 58px;
            padding: 7px 8px;
            margin-bottom: 7px;
            border-radius: 10px;
            border: 1px solid rgba(148,163,184,.18);
            background: #19212c;
          }
          .prio-page .tl-item-main {
            height: 78px;
          }
          .prio-page .tl-item-main.now,
          .prio-page .tl-item-main.shiftmate {
            height: 92px;
          }
          .prio-page .tl-item.now,
          .prio-page .tl-item.shiftmate {
            border-color: rgba(250,173,20,.70);
            box-shadow: 0 0 0 1px rgba(250,173,20,.24), 0 10px 30px rgba(0,0,0,.20);
          }
          .prio-page .tl-time {
            min-width: 118px;
            padding: 6px 9px;
            font-size: .92rem;
          }
          .prio-page .tl-item.now .tl-time,
          .prio-page .tl-item.shiftmate .tl-time {
            min-width: 130px;
            padding: 8px 10px;
            font-size: 1.02rem;
          }
          .prio-page .tl-veh {
            font-size: 1.25rem;
            overflow-wrap: anywhere;
          }
          .prio-page .tl-item.now .tl-veh,
          .prio-page .tl-item.shiftmate .tl-veh {
            font-size: 1.75rem;
          }
          .prio-page .tl-hint {
            color: #d7dee9;
            font-size: .92rem;
          }
          .prio-page .tl-side-time {
            min-width: 190px;
          }
          .prio-page .tl-side-veh {
            font-size: 1.45rem;
          }
          .config-page {
            --cfg-bg: #101820;
            --cfg-panel: #17212b;
            --cfg-panel-soft: #1d2a36;
            --cfg-border: rgba(148, 163, 184, .24);
            --cfg-text: #eef4f8;
            --cfg-muted: #a8b4c0;
            --cfg-primary: #2f80ed;
            --cfg-primary-hover: #2569c7;
            --cfg-danger: #b42318;
            --cfg-danger-hover: #8f1d15;
            --cfg-warning: #f59e0b;
            color: var(--cfg-text);
          }
          .config-page .page-title {
            margin-bottom: 14px;
          }
          .cfg-breadcrumb {
            width: 100%;
            gap: 10px;
            align-items: center;
            margin: 4px 0 14px 0;
            flex-wrap: wrap;
          }
          .cfg-breadcrumb-current,
          .cfg-breadcrumb-link,
          .cfg-breadcrumb-separator {
            color: #ffffff;
            font-size: 2.2rem;
            line-height: 1.12;
            font-weight: 900;
            letter-spacing: 0;
          }
          .cfg-breadcrumb-link {
            cursor: pointer;
          }
          .cfg-breadcrumb-link:hover {
            color: #d7e8ff;
            text-decoration: underline;
            text-underline-offset: 5px;
          }
          .cfg-breadcrumb-separator {
            color: #ffffff;
          }
          .cfg-action-row {
            width: 100%;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
            margin: 0 0 14px 0;
          }
          .cfg-trace-panel {
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin: -4px 0 14px 0;
            padding: 10px 12px;
            border: 1px solid rgba(158,197,254,.22);
            border-radius: 8px;
            background: rgba(23,33,43,.72);
            color: var(--cfg-text);
          }
          .cfg-trace-row {
            width: 100%;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
          }
          .cfg-trace-number {
            min-width: 118px;
            max-width: 142px;
          }
          .cfg-trace-check {
            color: var(--cfg-text);
            font-weight: 800;
          }
          .cfg-page-head {
            width: 100%;
            margin: 6px 0 14px 0;
            padding: 18px 22px;
            border: 1px solid var(--cfg-border);
            border-radius: 8px;
            background: linear-gradient(135deg, rgba(47,128,237,.16), rgba(23,33,43,.96));
            color: var(--cfg-text);
          }
          .cfg-eyebrow {
            color: #9ec5fe;
            font-size: .9rem;
            font-weight: 800;
            letter-spacing: 0;
            text-transform: uppercase;
          }
          .cfg-heading {
            color: var(--cfg-text);
            font-size: 2rem;
            line-height: 1.12;
            font-weight: 900;
            margin: 2px 0 0 0;
          }
          .cfg-subtle {
            color: var(--cfg-muted);
            font-size: .98rem;
            font-weight: 650;
          }
          .cfg-mini-label {
            color: rgba(210, 222, 235, .72);
            font-size: .76rem;
            line-height: 1.05;
            font-weight: 800;
          }
          .cfg-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            width: 100%;
          }
          .cfg-panel,
          .cfg-tile,
          .cfg-table-panel {
            width: 100%;
            background: var(--cfg-panel);
            border: 1px solid var(--cfg-border);
            border-radius: 8px;
            color: var(--cfg-text);
            box-shadow: 0 14px 34px rgba(0,0,0,.16);
          }
          .cfg-panel {
            padding: 18px;
          }
          .cfg-tile {
            padding: 18px;
            min-height: 138px;
          }
          .cfg-table-panel {
            padding: 0;
            overflow: hidden;
          }
          .cfg-section-title {
            color: var(--cfg-text);
            font-size: 1.35rem;
            line-height: 1.18;
            font-weight: 900;
            margin: 0;
          }
          .cfg-tile-title {
            color: var(--cfg-text);
            font-size: 1.35rem;
            line-height: 1.18;
            font-weight: 900;
          }
          .cfg-kpi {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.06);
            border: 1px solid rgba(255,255,255,.10);
            color: var(--cfg-muted);
            font-size: .9rem;
            font-weight: 800;
            white-space: nowrap;
          }
          .cfg-filter-row {
            flex-wrap: nowrap;
          }
          .cfg-filter-row .q-field {
            min-width: 190px;
          }
          .cfg-pill {
            display: inline-flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(47,128,237,.12);
            border: 1px solid rgba(47,128,237,.34);
            color: #d7e8ff;
            font-weight: 800;
          }
          .cfg-empty {
            padding: 18px;
            border: 1px dashed rgba(148, 163, 184, .38);
            border-radius: 8px;
            color: var(--cfg-muted);
            background: rgba(255,255,255,.03);
            font-weight: 700;
          }
          .cfg-toolbar {
            width: 100%;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
          }
          .cfg-frist-list {
            width: 100%;
            gap: 10px;
          }
          .cfg-frist-list .cfg-frist-item {
            width: 100%;
          }
          .cfg-frist-item {
            position: relative;
            padding: 6px 8px;
            border: 1px solid rgba(148, 163, 184, .22);
            border-radius: 8px;
            background: rgba(255,255,255,.035);
            cursor: grab;
            user-select: none;
          }
          .cfg-frist-item:hover {
            border-color: rgba(255,255,255,.62);
            background: rgba(255,255,255,.07);
          }
          .cfg-frist-item-selected {
            border-color: rgba(255,255,255,.88);
            background: rgba(47,128,237,.18);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.18);
          }
          .cfg-frist-item:active {
            cursor: grabbing;
          }
          .cfg-frist-item.cfg-drop-before::before,
          .cfg-frist-item.cfg-drop-after::after {
            content: "";
            position: absolute;
            left: 8px;
            right: 8px;
            height: 3px;
            border-radius: 999px;
            background: #ffffff;
            box-shadow: 0 0 0 1px rgba(15,23,42,.75), 0 0 12px rgba(255,255,255,.72);
            pointer-events: none;
            z-index: 6;
          }
          .cfg-frist-item.cfg-drop-before::before {
            top: -6px;
          }
          .cfg-frist-item.cfg-drop-after::after {
            bottom: -6px;
          }
          .cfg-drag-hint {
            color: var(--cfg-muted);
            font-size: .82rem;
            font-weight: 800;
          }
          .cfg-side-by-side {
            width: 100%;
            gap: 14px;
            align-items: flex-start;
            flex-wrap: nowrap;
          }
          .cfg-side-panel {
            flex: 1 1 0;
            min-width: 0;
          }
          html body #q-app .q-btn.cfg-btn-primary,
          html body #q-app .q-btn.cfg-btn-open {
            background: var(--cfg-primary) !important;
            background-color: var(--cfg-primary) !important;
            color: #ffffff !important;
            border: 1px solid rgba(255,255,255,.10) !important;
          }
          html body #q-app .q-btn.cfg-btn-primary:hover,
          html body #q-app .q-btn.cfg-btn-open:hover {
            background: var(--cfg-primary-hover) !important;
            background-color: var(--cfg-primary-hover) !important;
          }
          html body #q-app .q-btn.cfg-btn-secondary {
            background: var(--cfg-panel-soft) !important;
            background-color: var(--cfg-panel-soft) !important;
            color: var(--cfg-text) !important;
            border: 1px solid var(--cfg-border) !important;
          }
          html body #q-app .q-btn.cfg-btn-danger {
            background: var(--cfg-danger) !important;
            background-color: var(--cfg-danger) !important;
            color: #ffffff !important;
            border: 1px solid rgba(255,255,255,.12) !important;
          }
          html body #q-app .q-btn.cfg-btn-danger:hover {
            background: var(--cfg-danger-hover) !important;
            background-color: var(--cfg-danger-hover) !important;
          }
          .cfg-btn-primary .q-btn__content,
          .cfg-btn-open .q-btn__content,
          .cfg-btn-secondary .q-btn__content,
          .cfg-btn-danger .q-btn__content {
            font-size: .95rem !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
          }
          html body #q-app .q-btn.cfg-entry-button {
            min-height: 82px;
            border: 2px solid rgba(255,255,255,.92) !important;
            box-shadow: 0 12px 28px rgba(0,0,0,.22) !important;
          }
          .cfg-entry-button .q-btn__content {
            font-size: 1.55rem !important;
            font-weight: 950 !important;
            line-height: 1.12 !important;
          }
          .config-page .q-field__native,
          .config-page .q-field__input,
          .config-page .q-field__label,
          .config-page .q-field__marginal,
          .config-page .q-field__prepend,
          .config-page .q-field__append,
          .config-page input,
          .config-page textarea {
            color: #ffffff !important;
          }
          .config-page .q-field__control {
            background: #111b24 !important;
          }
          .config-page .q-field__control:before,
          .config-page .q-field__control:after {
            border-color: rgba(198, 212, 226, .82) !important;
          }
          .config-page .q-radio,
          .config-page .q-radio__label,
          .cfg-dialog-card .q-radio,
          .cfg-dialog-card .q-radio__label {
            color: #ffffff !important;
            font-weight: 750;
          }
          .config-page .q-radio__inner,
          .cfg-dialog-card .q-radio__inner {
            color: #ffffff !important;
            opacity: 1 !important;
          }
          .config-page .q-radio__bg,
          .config-page .q-radio__bg *,
          .cfg-dialog-card .q-radio__bg,
          .cfg-dialog-card .q-radio__bg * {
            color: #ffffff !important;
            stroke: #ffffff !important;
            fill: #ffffff !important;
            opacity: 1 !important;
          }
          .cfg-table .q-table__container,
          .cfg-table .q-table__bottom,
          .cfg-table .q-table__middle,
          .cfg-table .q-table,
          .cfg-table .q-table thead tr,
          .cfg-table .q-table tbody tr,
          .cfg-table .q-table th,
          .cfg-table .q-table td {
            background: var(--cfg-panel) !important;
            color: var(--cfg-text) !important;
          }
          .cfg-table .q-table th {
            background: #111b24 !important;
            color: #d7e8ff !important;
            font-weight: 900 !important;
          }
          .cfg-table .q-table th,
          .cfg-table .q-table td {
            border-color: rgba(148, 163, 184, .20) !important;
          }
          .cfg-row-card {
            width: 100%;
            padding: 12px 14px;
            border-radius: 8px;
            border: 1px solid rgba(148, 163, 184, .18);
            background: rgba(255,255,255,.035);
          }
          .cfg-workshop-layout-preview {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid rgba(148, 163, 184, .22);
            background: rgba(15, 23, 42, .38);
          }
          .cfg-workshop-tile {
            position: relative;
            min-height: 148px;
            padding: 14px;
            border-radius: 8px;
            border: 1px solid rgba(226, 232, 240, .32);
            background: #262730;
            color: #f2f5f8;
            cursor: grab;
            user-select: none;
          }
          .cfg-workshop-tile:active {
            cursor: grabbing;
          }
          .cfg-workshop-tile-muted {
            background: rgba(255,255,255,.035);
            border-style: dashed;
          }
          .cfg-workshop-tile-title {
            color: #f5f7fa;
            font-size: 2rem;
            line-height: 1;
            font-weight: 900;
            text-decoration: underline;
            overflow-wrap: anywhere;
          }
          .cfg-workshop-tile-meta {
            color: rgba(226, 232, 240, .86);
            font-size: .98rem;
            font-weight: 800;
            line-height: 1.2;
          }
          .cfg-workshop-drag-icon {
            color: rgba(226, 232, 240, .74);
            font-size: 1.4rem;
          }
          .cfg-workshop-tile.cfg-workshop-drop-before::before,
          .cfg-workshop-tile.cfg-workshop-drop-after::after {
            content: "";
            position: absolute;
            left: 10px;
            right: 10px;
            height: 4px;
            border-radius: 999px;
            background: #ffffff;
            box-shadow: 0 0 0 1px rgba(15,23,42,.85), 0 0 14px rgba(255,255,255,.72);
            pointer-events: none;
            z-index: 8;
          }
          .cfg-workshop-tile.cfg-workshop-drop-before::before {
            top: -7px;
          }
          .cfg-workshop-tile.cfg-workshop-drop-after::after {
            bottom: -7px;
          }
          .cfg-package-detail {
            color: rgba(210, 222, 235, .84);
            font-size: .86rem;
            font-weight: 700;
            line-height: 1.25;
          }
          .cfg-dialog-card {
            min-width: min(92vw, 600px);
            max-width: min(92vw, 680px);
            max-height: 88vh;
            overflow-y: auto;
            background: #17212b;
            border: 1px solid var(--cfg-border, rgba(148,163,184,.24));
            color: #eef4f8;
          }
          .cfg-dialog-card .q-field__native,
          .cfg-dialog-card .q-field__input,
          .cfg-dialog-card .q-field__label,
          .cfg-dialog-card .q-field__marginal,
          .cfg-dialog-card .q-field__prepend,
          .cfg-dialog-card .q-field__append,
          .cfg-dialog-card input,
          .cfg-dialog-card textarea {
            color: #ffffff !important;
          }
          .cfg-dialog-card .q-field__control {
            background: #111b24 !important;
          }
          .cfg-dialog-card .q-field__control:before,
          .cfg-dialog-card .q-field__control:after {
            border-color: rgba(198, 212, 226, .82) !important;
          }
          @media (max-width: 1300px) {
            .cfg-grid { grid-template-columns: minmax(0, 1fr); }
            .cfg-workshop-layout-preview { grid-template-columns: minmax(0, 1fr); }
            .cfg-side-by-side { flex-wrap: wrap; }
            .cfg-side-panel { flex-basis: 100%; }
            .cfg-filter-row { flex-wrap: wrap; }
            .task-col-ratio-22 { min-width: 220px; }
            .task-col-ratio-16 { min-width: 190px; }
            .task-col-ratio-13 { min-width: 170px; }
            .task-col-ratio-12 { min-width: 160px; }
            .task-col-ratio-09 { min-width: 180px; }
            .open-task-card .open-task-grid {
              grid-template-columns: minmax(240px, 1.7fr) minmax(210px, 1.25fr) minmax(150px, .9fr) minmax(210px, 1.1fr) minmax(150px, .9fr);
            }
            .open-task-card .task-actions {
              grid-column: 1 / -1;
              grid-template-columns: repeat(2, minmax(180px, 1fr));
            }
            .hall-slot-title, .due-title { font-size: 2.35rem; }
            .hall-fzg { font-size: 2.35rem; }
            .hall-meta { font-size: 1.2rem; }
            .slot-pill { font-size: 1rem; }
            .tl-item-main { height: 80px; }
            .tl-item-main.now,
            .tl-item-main.shiftmate { height: 96px; }
            .shop-shift-row { flex-wrap: wrap; }
            .shop-shift-label {
              min-width: 100%;
              font-size: 1.55rem;
            }
            .shop-shift-input .q-field__native,
            .shop-shift-input .q-field__input {
              font-size: 1.3rem !important;
            }
            .weekplan-grid { grid-template-columns: minmax(0, 1fr); }
            .weekplan-days { grid-template-columns: repeat(7, minmax(0, 1fr)); }
            .prio-note-row { grid-template-columns: minmax(0, 1fr); }
            .prio-side-legend {
              justify-self: start;
              align-self: start;
            }
            .tl-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .tl-grid-3 { grid-template-columns: minmax(0, 1fr); }
          }
          @media (min-width: 981px) {
            .prio-page .tl-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
            .prio-page .tl-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
          }
          @media (max-width: 980px) {
            .workshop-summary-row { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
            .hall-bottom-grid { grid-template-columns: minmax(0, 1fr) !important; }
            .open-summary-row { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
            .open-task-card .open-task-grid { grid-template-columns: minmax(0, 1fr); }
            .open-task-card .task-actions { grid-template-columns: minmax(0, 1fr); }
            .prio-summary-row { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
            .prio-page .tl-grid-4,
            .prio-page .tl-grid-3 { grid-template-columns: minmax(0, 1fr); }
          }
          @media (max-width: 760px) {
            .open-tasks-page { padding-bottom: 14px; }
            .open-command-row { align-items: stretch; gap: 10px; }
            .open-page-title { width: 100%; }
            .open-new-order-btn { width: 100%; }
            .open-legend-wrap .legend-row { gap: 9px; }
            .open-legend-wrap .legend-item { width: 100%; }
            .open-legend-wrap .legend-text { white-space: normal; }
            .open-summary-row { grid-template-columns: minmax(0, 1fr); }
            .open-section-title { font-size: 2rem; }
            .open-task-card { padding: 12px !important; }
            .open-task-card .badge-pill-big { font-size: 1.55rem; }
            .werkstatthalle-page { padding-bottom: 14px; }
            .workshop-command-row { align-items: stretch; gap: 10px; }
            .workshop-page-title { width: 100%; }
            .workshop-command-tools {
              display: grid !important;
              grid-template-columns: minmax(0, 1fr);
              width: 100%;
              justify-content: stretch;
              align-items: stretch;
            }
            .workshop-command-tools > * { min-width: 0; }
            .workshop-external-btn { width: 100%; }
            .workshop-legend { width: 100%; justify-content: flex-start; }
            .workshop-legend .legend-text { white-space: normal; }
            .workshop-summary-row { grid-template-columns: minmax(0, 1fr); }
            .workshop-stat { min-height: 66px; }
            .hall-slot,
            .due-card {
              min-height: 250px;
              padding: 14px !important;
            }
            .hall-actions { grid-template-columns: minmax(0, 1fr); }
            .hall-actions .q-btn { min-height: 54px; }
            .prio-page { padding-bottom: 14px; }
            .prio-command-row { align-items: stretch; gap: 10px; }
            .prio-page-title { width: 100%; }
            .prio-command-tools {
              display: grid !important;
              grid-template-columns: minmax(0, 1fr);
              width: 100%;
              justify-content: stretch;
              align-items: stretch;
            }
            .prio-command-tools > * { min-width: 0; }
            .prio-date-control,
            .prio-external-btn,
            .prio-deadline-legend { width: 100%; }
            .prio-summary-row { grid-template-columns: minmax(0, 1fr); }
            .prio-page .tl-card { padding: 12px !important; }
            .prio-page .tl-time { min-width: 110px; }
            .prio-page .tl-side-time { min-width: 140px; }
          }
          html body #q-app .q-btn,
          html body #q-app .q-btn.bg-primary,
          html body #q-app .q-btn.bg-negative,
          html body #q-app .q-btn.bg-warning,
          html body #q-app .q-btn.bg-positive,
          html body #q-app .q-btn.nav-btn,
          html body #q-app .q-btn.home-btn,
          html body #q-app .q-btn.btn-big,
          html body #q-app .q-btn.btn-remove,
          html body #q-app .q-btn.btn-done,
          html body #q-app .q-btn.btn-warn,
          html body #q-app .q-btn.btn-area-assign,
          html body #q-app .q-btn.cfg-btn-primary,
          html body #q-app .q-btn.cfg-btn-open,
          html body #q-app .q-btn.cfg-btn-secondary,
          html body #q-app .q-btn.cfg-btn-danger,
          html body #q-app .q-btn.cfg-entry-button {
            background: #111827 !important;
            background-color: #111827 !important;
            background-image: linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%) !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border-color: var(--btn-border, rgba(255,255,255,.18)) !important;
            border-radius: 18px !important;
            box-shadow: var(--btn-shadow, 0 18px 40px rgba(0,0,0,.22)) !important;
            transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease, background .15s ease !important;
          }
          html body #q-app .q-btn:hover,
          html body #q-app .q-btn.bg-primary:hover,
          html body #q-app .q-btn.bg-negative:hover,
          html body #q-app .q-btn.bg-warning:hover,
          html body #q-app .q-btn.bg-positive:hover,
          html body #q-app .q-btn.nav-btn:hover,
          html body #q-app .q-btn.home-btn:hover,
          html body #q-app .q-btn.btn-big:hover,
          html body #q-app .q-btn.btn-remove:hover,
          html body #q-app .q-btn.btn-done:hover,
          html body #q-app .q-btn.btn-warn:hover,
          html body #q-app .q-btn.btn-area-assign:hover,
          html body #q-app .q-btn.cfg-btn-primary:hover,
          html body #q-app .q-btn.cfg-btn-open:hover,
          html body #q-app .q-btn.cfg-btn-secondary:hover,
          html body #q-app .q-btn.cfg-btn-danger:hover,
          html body #q-app .q-btn.cfg-entry-button:hover {
            background: #111827 !important;
            background-color: #111827 !important;
            background-image: linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%) !important;
            border-color: var(--btn-border-hover, rgba(96,165,250,.50)) !important;
            box-shadow: var(--btn-shadow-hover, 0 24px 50px rgba(0,0,0,.28)) !important;
            transform: translateY(-2px);
          }
          html body #q-app .q-btn .q-focus-helper {
            background: rgba(255,255,255,.10) !important;
          }
          html body #q-app .q-btn .q-btn__content,
          html body #q-app .q-btn .q-btn__content * {
            color: var(--btn-fg, #f3f4f6) !important;
          }
          html body .q-btn,
          html body .q-btn.bg-primary,
          html body .q-btn.bg-negative,
          html body .q-btn.bg-warning,
          html body .q-btn.bg-positive,
          html body .q-btn.nav-btn,
          html body .q-btn.home-btn,
          html body .q-btn.btn-big,
          html body .q-btn.btn-remove,
          html body .q-btn.btn-done,
          html body .q-btn.btn-warn,
          html body .q-btn.btn-area-assign,
          html body .q-btn.cfg-btn-primary,
          html body .q-btn.cfg-btn-open,
          html body .q-btn.cfg-btn-secondary,
          html body .q-btn.cfg-btn-danger,
          html body .q-btn.cfg-entry-button {
            background: #111827 !important;
            background-color: #111827 !important;
            background-image: linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%) !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border-color: var(--btn-border, rgba(148,163,184,.22)) !important;
            border-radius: 18px !important;
            box-shadow: var(--btn-shadow, 0 18px 40px rgba(0,0,0,.22)) !important;
            transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease, background .15s ease !important;
          }
          html body .q-btn:hover,
          html body .q-btn.bg-primary:hover,
          html body .q-btn.bg-negative:hover,
          html body .q-btn.bg-warning:hover,
          html body .q-btn.bg-positive:hover,
          html body .q-btn.nav-btn:hover,
          html body .q-btn.home-btn:hover,
          html body .q-btn.btn-big:hover,
          html body .q-btn.btn-remove:hover,
          html body .q-btn.btn-done:hover,
          html body .q-btn.btn-warn:hover,
          html body .q-btn.btn-area-assign:hover,
          html body .q-btn.cfg-btn-primary:hover,
          html body .q-btn.cfg-btn-open:hover,
          html body .q-btn.cfg-btn-secondary:hover,
          html body .q-btn.cfg-btn-danger:hover,
          html body .q-btn.cfg-entry-button:hover {
            background: #111827 !important;
            background-color: #111827 !important;
            background-image: linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%) !important;
            border-color: var(--btn-border-hover, rgba(96,165,250,.50)) !important;
            box-shadow: var(--btn-shadow-hover, 0 24px 50px rgba(0,0,0,.28)) !important;
            transform: translateY(-2px);
          }
          html body .q-btn .q-focus-helper {
            background: rgba(255,255,255,.10) !important;
          }
          html body .q-btn .q-btn__content,
          html body .q-btn .q-btn__content * {
            color: var(--btn-fg, #f3f4f6) !important;
          }
          html body #app .q-btn,
          html body #app .q-btn.bg-primary,
          html body #app .q-btn.bg-negative,
          html body #app .q-btn.bg-warning,
          html body #app .q-btn.bg-positive,
          html body #app .q-btn.nav-btn,
          html body #app .q-btn.home-btn,
          html body #app .q-btn.btn-big,
          html body #app .q-btn.btn-remove,
          html body #app .q-btn.btn-done,
          html body #app .q-btn.btn-warn,
          html body #app .q-btn.btn-area-assign,
          html body #app .q-btn.cfg-btn-primary,
          html body #app .q-btn.cfg-btn-open,
          html body #app .q-btn.cfg-btn-secondary,
          html body #app .q-btn.cfg-btn-danger,
          html body #app .q-btn.cfg-entry-button {
            background: #111827 !important;
            background-color: #111827 !important;
            background-image: linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%) !important;
            color: var(--btn-fg, #f3f4f6) !important;
            border-color: var(--btn-border, rgba(148,163,184,.22)) !important;
            border-radius: 18px !important;
            box-shadow: var(--btn-shadow, 0 18px 40px rgba(0,0,0,.22)) !important;
            transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease, background .15s ease !important;
          }
          html body #app .q-btn:hover,
          html body #app .q-btn.bg-primary:hover,
          html body #app .q-btn.bg-negative:hover,
          html body #app .q-btn.bg-warning:hover,
          html body #app .q-btn.bg-positive:hover,
          html body #app .q-btn.nav-btn:hover,
          html body #app .q-btn.home-btn:hover,
          html body #app .q-btn.btn-big:hover,
          html body #app .q-btn.btn-remove:hover,
          html body #app .q-btn.btn-done:hover,
          html body #app .q-btn.btn-warn:hover,
          html body #app .q-btn.btn-area-assign:hover,
          html body #app .q-btn.cfg-btn-primary:hover,
          html body #app .q-btn.cfg-btn-open:hover,
          html body #app .q-btn.cfg-btn-secondary:hover,
          html body #app .q-btn.cfg-btn-danger:hover,
          html body #app .q-btn.cfg-entry-button:hover {
            background: #111827 !important;
            background-color: #111827 !important;
            background-image: linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%) !important;
            border-color: var(--btn-border-hover, rgba(96,165,250,.50)) !important;
            box-shadow: var(--btn-shadow-hover, 0 24px 50px rgba(0,0,0,.28)) !important;
            transform: translateY(-2px);
          }
          html body #app .q-btn .q-focus-helper {
            background: rgba(255,255,255,.10) !important;
          }
          html body #app .q-btn .q-btn__content,
          html body #app .q-btn .q-btn__content * {
            color: var(--btn-fg, #f3f4f6) !important;
          }
        </style>
        """,
        shared=True,
    )


    ui.add_head_html(
        """
        <script>
          (function () {
            var browserZoom = "__browser_html_zoom__";
            var nativeZoom = "__native_html_zoom__";

            function hasPywebview() {
              try {
                return !!(window.pywebview && window.pywebview.platform);
              } catch (e) {
                return false;
              }
            }

            function applyClientZoom(forceNative) {
              try {
                document.documentElement.style.zoom = (forceNative || hasPywebview()) ? nativeZoom : browserZoom;
                if (window.__scheduleNiceguiSelectMenuPosition) window.__scheduleNiceguiSelectMenuPosition();
              } catch (e) {}
            }

            applyClientZoom(false);
            window.addEventListener("pywebviewready", function () {
              applyClientZoom(true);
            }, { once: true });

            var tries = 0;
            var timer = setInterval(function () {
              applyClientZoom(false);
              tries += 1;
              if (hasPywebview() || tries > 40) clearInterval(timer);
            }, 250);
          })();
        </script>
        """
        .replace("__browser_html_zoom__", str(browser_html_zoom))
        .replace("__native_html_zoom__", str(native_html_zoom)),
        shared=True,
    )

    ui.add_head_html(
        """
        <script>
          (function () {
            var activeSelect = null;
            var pending = false;

            function currentZoom() {
              try {
                var raw = document.documentElement.style.zoom || getComputedStyle(document.documentElement).zoom || "1";
                var zoom = parseFloat(raw);
                return Number.isFinite(zoom) && zoom > 0 ? zoom : 1;
              } catch (e) {
                return 1;
              }
            }

            function rememberSelect(event) {
              try {
                var target = event && event.target;
                var select = target && target.closest ? target.closest(".q-select") : null;
                if (select) activeSelect = select;
              } catch (e) {}
            }

            function selectMenus() {
              var result = [];
              var seen = new Set();
              try {
                document.querySelectorAll(".area-select-popup").forEach(function (node) {
                  var menu = node.classList && node.classList.contains("q-menu") ? node : node.closest(".q-menu");
                  if (!menu) menu = node;
                  if (!seen.has(menu)) {
                    seen.add(menu);
                    result.push(menu);
                  }
                });
              } catch (e) {}
              return result;
            }

            function isVisibleMenu(menu) {
              if (!menu) return false;
              try {
                var style = window.getComputedStyle(menu);
                if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
                var rect = menu.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
              } catch (e) {
                return false;
              }
            }

            function setImportantStyle(el, key, value) {
              try {
                if (el.style.getPropertyValue(key) !== value) {
                  el.style.setProperty(key, value, "important");
                }
              } catch (e) {}
            }

            function positionMenus() {
              pending = false;
              var visibleCount = 0;
              try {
                if (!activeSelect || !document.body.contains(activeSelect)) {
                  var focused = document.activeElement && document.activeElement.closest
                    ? document.activeElement.closest(".q-select")
                    : null;
                  activeSelect = focused;
                }
                if (!activeSelect || !document.body.contains(activeSelect)) return 0;
                var rect = activeSelect.getBoundingClientRect();
                var zoom = currentZoom();
                selectMenus().forEach(function (menu) {
                  if (!isVisibleMenu(menu)) return;
                  visibleCount += 1;
                  setImportantStyle(menu, "position", "fixed");
                  setImportantStyle(menu, "left", (rect.left / zoom) + "px");
                  setImportantStyle(menu, "top", (rect.bottom / zoom) + "px");
                  setImportantStyle(menu, "min-width", (rect.width / zoom) + "px");
                  setImportantStyle(menu, "max-width", "min(680px, calc(100vw - 24px))");
                  setImportantStyle(menu, "transform", "none");
                  setImportantStyle(menu, "transform-origin", "top left");
                });
              } catch (e) {}
              return visibleCount;
            }

            var correctionLoopActive = false;
            var correctionUntil = 0;

            function startCorrectionLoop() {
              correctionUntil = Math.max(correctionUntil, Date.now() + 1600);
              if (correctionLoopActive) return;
              correctionLoopActive = true;

              function tick() {
                var visibleCount = positionMenus();
                if (visibleCount && Date.now() < correctionUntil) {
                  window.requestAnimationFrame(tick);
                } else if (visibleCount) {
                  window.setTimeout(function () {
                    window.requestAnimationFrame(tick);
                  }, 80);
                } else {
                  correctionLoopActive = false;
                }
              }

              window.requestAnimationFrame(tick);
            }

            function schedulePosition() {
              if (pending) return;
              pending = true;
              window.requestAnimationFrame(function () {
                positionMenus();
                window.setTimeout(positionMenus, 40);
                window.setTimeout(positionMenus, 120);
                window.setTimeout(positionMenus, 300);
                startCorrectionLoop();
              });
            }

            window.__positionNiceguiSelectMenus = positionMenus;
            window.__scheduleNiceguiSelectMenuPosition = schedulePosition;

            document.addEventListener("mousedown", function (event) {
              rememberSelect(event);
              schedulePosition();
            }, true);
            document.addEventListener("focusin", function (event) {
              rememberSelect(event);
              schedulePosition();
            }, true);
            document.addEventListener("click", schedulePosition, true);
            window.addEventListener("resize", schedulePosition, true);
            window.addEventListener("scroll", schedulePosition, true);

            if (document.readyState === "loading") {
              document.addEventListener("DOMContentLoaded", function () {
                new MutationObserver(schedulePosition).observe(document.body, {
                  childList: true,
                  subtree: true,
                });
              }, { once: true });
            } else {
              new MutationObserver(schedulePosition).observe(document.body, {
                childList: true,
                subtree: true,
              });
            }
          })();
        </script>
        """,
        shared=True,
    )


    ui.add_head_html(
        f"""
        <style>
          .task-check-list .task-check-row {{
            margin-bottom: {open_item_gap_px}px !important;
          }}
          .task-check-list .task-check-row:last-child {{
            margin-bottom: 0 !important;
          }}
          .task-check-text {{
            font-family: "Source Sans Pro", "Segoe UI", Tahoma, sans-serif !important;
            font-size: {open_item_font_size_px}px !important;
            font-weight: {open_item_font_weight} !important;
            line-height: {open_item_line_height} !important;
          }}
          .task-check-box,
          .task-check-box * {{
            font-family: "Source Sans Pro", "Segoe UI", Tahoma, sans-serif !important;
          }}
        </style>
        """,
        shared=True,
    )


    ui.add_head_html(
        """
        <script>
          (function () {
            function applyBrandPrimary() {
              try {
                var root = document.documentElement;
                [root, document.body, document.getElementById('q-app')].forEach(function (el) {
                  if (!el) return;
                  el.style.setProperty('--q-primary', '#111827');
                });
              } catch (e) {}
            }
            if (document.readyState === 'loading') {
              document.addEventListener('DOMContentLoaded', applyBrandPrimary, { once: true });
            } else {
              applyBrandPrimary();
            }
            var tries = 0;
            var timer = setInterval(function () {
              applyBrandPrimary();
              tries += 1;
              if (tries > 40) clearInterval(timer);
            }, 250);
          })();
        </script>
        """,
        shared=True,
    )


    ui.add_head_html(
        """
        <style id="button-text-case-override">
          html body #q-app .q-btn,
          html body #q-app .q-btn *,
          html body #q-app .q-btn.text-uppercase,
          html body #q-app .q-btn .text-uppercase,
          html body #q-app .q-btn__content,
          html body #q-app .q-btn__content * {
            text-transform: none !important;
          }
        </style>
        <script>
          (function () {
            function applyButtonTextCase() {
              try {
                document.querySelectorAll('.q-btn, .q-btn *, .q-btn.text-uppercase, .q-btn .text-uppercase, .q-btn__content, .q-btn__content *')
                  .forEach(function (el) {
                    el.style.setProperty('text-transform', 'none', 'important');
                  });
              } catch (e) {}
            }

            if (document.readyState === 'loading') {
              document.addEventListener('DOMContentLoaded', applyButtonTextCase, { once: true });
            } else {
              applyButtonTextCase();
            }

            var tries = 0;
            var timer = setInterval(function () {
              applyButtonTextCase();
              tries += 1;
              if (tries > 30) clearInterval(timer);
            }, 300);

            try {
              new MutationObserver(applyButtonTextCase).observe(document.documentElement, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['class', 'style']
              });
            } catch (e) {}
          })();
        </script>
        """,
        shared=True,
    )

    ui.add_head_html(
        """
        <script>
          (function () {
            var NORMAL_BG = 'linear-gradient(180deg, rgba(30,41,59,.95) 0%, rgba(15,23,42,.98) 100%)';
            var HOVER_BG = 'linear-gradient(180deg, rgba(35,49,73,.98) 0%, rgba(18,28,46,1) 100%)';
            var NORMAL_BORDER = 'rgba(148,163,184,.22)';
            var HOVER_BORDER = 'rgba(96,165,250,.50)';
            var NORMAL_SHADOW = '0 18px 40px rgba(0,0,0,.22)';
            var HOVER_SHADOW = '0 24px 50px rgba(0,0,0,.28)';

            function setButtonLook(el, hover) {
              if (!el || el.classList.contains('planning-page-title-btn')) return;
              el.style.setProperty('background', (hover ? HOVER_BG : NORMAL_BG) + ' #111827', 'important');
              el.style.setProperty('background-color', '#111827', 'important');
              el.style.setProperty('background-image', hover ? HOVER_BG : NORMAL_BG, 'important');
              el.style.setProperty('color', '#f3f4f6', 'important');
              el.style.setProperty('border-color', hover ? HOVER_BORDER : NORMAL_BORDER, 'important');
              el.style.setProperty('border-radius', '18px', 'important');
              el.style.setProperty('box-shadow', hover ? HOVER_SHADOW : NORMAL_SHADOW, 'important');
              el.style.setProperty('transition', 'transform .15s ease, border-color .15s ease, box-shadow .15s ease, background .15s ease', 'important');
              el.style.setProperty('transform', hover ? 'translateY(-2px)' : 'none', 'important');
              el.querySelectorAll('.q-btn__content, .q-btn__content *').forEach(function (child) {
                child.style.setProperty('color', '#f3f4f6', 'important');
              });
              el.querySelectorAll('.q-focus-helper').forEach(function (child) {
                child.style.setProperty('background', 'rgba(255,255,255,.10)', 'important');
              });
            }

            function bindButtonLook(el) {
              if (!el || el.dataset.buttonLookBound === '1') return;
              el.dataset.buttonLookBound = '1';
              el.addEventListener('mouseenter', function () { setButtonLook(el, true); });
              el.addEventListener('mouseleave', function () { setButtonLook(el, false); });
              el.addEventListener('focus', function () { setButtonLook(el, true); });
              el.addEventListener('blur', function () { setButtonLook(el, false); });
            }

            function applyButtonLook() {
              try {
                document.querySelectorAll('.q-btn').forEach(function (el) {
                  setButtonLook(el, el.matches(':hover') || el.matches(':focus'));
                  bindButtonLook(el);
                });
              } catch (e) {}
            }

            if (document.readyState === 'loading') {
              document.addEventListener('DOMContentLoaded', applyButtonLook, { once: true });
            } else {
              applyButtonLook();
            }

            var tries = 0;
            var timer = setInterval(function () {
              applyButtonLook();
              tries += 1;
              if (tries > 40) clearInterval(timer);
            }, 250);

            try {
              new MutationObserver(applyButtonLook).observe(document.documentElement, {
                childList: true,
                subtree: true
              });
            } catch (e) {}
          })();
        </script>
        """,
        shared=True,
    )

    ui.add_head_html(
        """
        <script>
          (function () {
            var ROOT = window.parent || window;
            var delayMs = Math.max(1000, Math.round(__disconnect_reload_seconds__ * 1000));
            var minReloadGapMs = Math.max(60000, delayMs * 3);
            var reloadTimer = null;
            var lastReloadKey = "fristen_disconnect_reload_at";

            function popupVisible() {
              try {
                var popup = document.getElementById("popup");
                return !!popup && popup.getAttribute("aria-hidden") !== "true";
              } catch (e) {
                return false;
              }
            }

            function reloadDisabledForPage() {
              try {
                var path = String(ROOT.location && ROOT.location.pathname || "").toLowerCase();
                if (path.indexOf("konfiguration") !== -1) return true;
                var doc = ROOT.document;
                return !!(doc && doc.querySelector(".config-page"));
              } catch (e) {
                return false;
              }
            }

            function cancelReload() {
              if (!reloadTimer) return;
              try { ROOT.clearTimeout(reloadTimer); } catch (e) {}
              reloadTimer = null;
            }

            function scheduleReload() {
              if (reloadDisabledForPage()) return;
              if (reloadTimer || delayMs <= 0) return;
              reloadTimer = ROOT.setTimeout(function () {
                reloadTimer = null;
                if (reloadDisabledForPage()) return;
                if (!popupVisible()) return;
                try {
                  var now = Date.now();
                  var last = parseInt(ROOT.sessionStorage.getItem(lastReloadKey) || "0", 10) || 0;
                  if (now - last < minReloadGapMs) return;
                  ROOT.sessionStorage.setItem(lastReloadKey, String(now));
                } catch (e) {}
                try {
                  ROOT.location.reload();
                } catch (e) {}
              }, delayMs);
            }

            function watchConnectionPopup() {
              if (reloadDisabledForPage()) {
                cancelReload();
                return;
              }
              if (popupVisible()) {
                scheduleReload();
              } else {
                cancelReload();
              }
            }

            if (document.readyState === "loading") {
              document.addEventListener("DOMContentLoaded", function () {
                watchConnectionPopup();
                ROOT.setInterval(watchConnectionPopup, 1000);
              }, { once: true });
            } else {
              watchConnectionPopup();
              ROOT.setInterval(watchConnectionPopup, 1000);
            }
          })();
        </script>
        """.replace("__disconnect_reload_seconds__", str(disconnect_reload_seconds)),
        shared=True,
    )


    ui.add_head_html(
        """
        <script>
          (function () {
            var ROOT = window.parent || window;
            ROOT._dueWatcherMap = ROOT._dueWatcherMap || {};

            ROOT._fmtHMS = function (ms) {
              if (!isFinite(ms)) ms = 0;
              var neg = ms < 0;
              if (neg) ms = -ms;
              var total = Math.floor(ms / 1000);
              var h = Math.floor(total / 3600);
              var m = Math.floor((total % 3600) / 60);
              var s = Math.floor(total % 60);
              return h + " Std " + m + " Min " + s + " Sek";
            };

            function setBadge(el, bg, fg) {
              if (!el) return;
              if (bg) {
                el.style.setProperty('background', bg, 'important');
                el.style.setProperty('background-color', bg, 'important');
              }
              if (fg) {
                el.style.setProperty('color', fg, 'important');
                el.style.setProperty('-webkit-text-fill-color', fg, 'important');
              }
              el.style.setProperty('border-radius', '999px');
              el.style.setProperty('font-weight', '800');
              if (!el.style.padding) el.style.setProperty('padding', '6px 12px');
            }

            function renderOne(opts) {
              try {
                var doc = ROOT.document;
                var vehEl = opts.vehId ? doc.getElementById(opts.vehId) : null;
                var fristEl = opts.fristId ? doc.getElementById(opts.fristId) : null;
                var startEl = opts.startId ? doc.getElementById(opts.startId) : null;
                var endEl = opts.endId ? doc.getElementById(opts.endId) : null;
                var areaEl = opts.areaId ? doc.getElementById(opts.areaId) : null;
                var statusEl = opts.statusId ? doc.getElementById(opts.statusId) : null;
                var cdEl = opts.cdId ? doc.getElementById(opts.cdId) : null;
                var diff = opts.endMs - Date.now();
                if (!isFinite(diff)) return;

                var G = opts.green || "#52c41a";
                var GF = opts.greenFg || "#ffffff";
                var Y = opts.yellow || "#faad14";
                var YF = opts.yellowFg || "#000000";
                var B = opts.bright || "#ffeb3b";
                var BF = opts.brightFg || "#000000";
                var R = opts.red || "#ff4d4f";
                var RF = opts.redFg || "#ffffff";
                var hasProblem = !!opts.hasProblem;

                if (diff > 24 * 3600 * 1000) {
                  var bg = hasProblem ? B : G;
                  var fg = hasProblem ? BF : GF;
                  if (vehEl) setBadge(vehEl, bg, fg);
                  if (fristEl) setBadge(fristEl, bg, fg);
                  if (startEl) setBadge(startEl, bg, fg);
                  if (endEl) setBadge(endEl, bg, fg);
                  if (areaEl) setBadge(areaEl, bg, fg);
                  if (cdEl) cdEl.style.display = "none";
                  if (statusEl) {
                    setBadge(statusEl, bg, fg);
                    statusEl.textContent = hasProblem ? "Problem gemeldet" : "Im Plan";
                  }
                  return;
                }

                if (diff > 0) {
                  var bg2 = hasProblem ? B : Y;
                  var fg2 = hasProblem ? BF : YF;
                  var labelIn = "Fristfertigstellung in " + ROOT._fmtHMS(diff);
                  if (vehEl) setBadge(vehEl, bg2, fg2);
                  if (fristEl) setBadge(fristEl, bg2, fg2);
                  if (startEl) setBadge(startEl, bg2, fg2);
                  if (endEl) setBadge(endEl, bg2, fg2);
                  if (areaEl) setBadge(areaEl, bg2, fg2);
                  if (cdEl) {
                    cdEl.style.display = "inline-block";
                    setBadge(cdEl, bg2, fg2);
                    cdEl.textContent = labelIn;
                  }
                  if (statusEl) {
                    setBadge(statusEl, bg2, fg2);
                    statusEl.textContent = labelIn;
                  }
                  return;
                }

                var labelSince = "Fristfertigstellung seit " + ROOT._fmtHMS(diff);
                if (vehEl) setBadge(vehEl, R, RF);
                if (fristEl) setBadge(fristEl, R, RF);
                if (startEl) setBadge(startEl, R, RF);
                if (endEl) setBadge(endEl, R, RF);
                if (areaEl) setBadge(areaEl, R, RF);
                if (cdEl) {
                  cdEl.style.display = "inline-block";
                  setBadge(cdEl, R, RF);
                  cdEl.textContent = labelSince;
                }
                if (statusEl) {
                  setBadge(statusEl, R, RF);
                  statusEl.textContent = labelSince;
                }
              } catch (e) {}
            }

            function ensureTicker(forceRestart) {
              if (forceRestart && ROOT._dueTickerId) {
                try { ROOT.clearInterval(ROOT._dueTickerId); } catch (e) {}
                ROOT._dueTickerId = null;
              }
              if (ROOT._dueTickerId) return;
              ROOT._dueTickerId = ROOT.setInterval(function () {
                var map = ROOT._dueWatcherMap || {};
                for (var k in map) {
                  if (!map[k]) continue;
                  renderOne(map[k]);
                }
              }, 1000);
            }

            ensureTicker(true);

            ROOT._watch_due_and_overdue = function (opts) {
              if (!opts || !opts.endMs) return;
              var targetKey = [opts.vehId || "", opts.fristId || "", opts.startId || "", opts.endId || "", opts.areaId || "", opts.cdId || "", opts.statusId || ""].join("|");
              var map = ROOT._dueWatcherMap || {};
              for (var k in map) {
                if (!map[k]) continue;
                var old = map[k];
                var oldTarget = [old.vehId || "", old.fristId || "", old.startId || "", old.endId || "", old.areaId || "", old.cdId || "", old.statusId || ""].join("|");
                if (oldTarget === targetKey) delete map[k];
              }
              var key = targetKey + "|" + (opts.hasProblem ? "P1" : "P0");
              ROOT._dueWatcherMap[key] = opts;
              renderOne(opts);
              ensureTicker(false);
            };
          })();
        </script>
        """,
        shared=True,
    )
