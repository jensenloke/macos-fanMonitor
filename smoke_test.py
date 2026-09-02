import asyncio
import os
import sys
import time

from textual.widgets import TabbedContent
from fanmon.app import BrandBoot, ConfirmKill, FanMonitorApp


def _plain(widget) -> str:
    r = widget.render()
    return getattr(r, "plain", str(r)).strip()


async def run_once(fanless: bool) -> bool:
    if fanless:
        os.environ["FANMON_FANLESS"] = "1"
        os.environ["FANMON_THROTTLE"] = "72"
        os.environ["FANMON_NO_ANIM"] = "1"
    else:
        os.environ.pop("FANMON_FANLESS", None)
        os.environ.pop("FANMON_THROTTLE", None)
        os.environ.pop("FANMON_NO_ANIM", None)
    print(f"=== mode: {'fanless (Air)' if fanless else 'fan'} ===")

    app = FanMonitorApp(interval=1.0)
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause(0.3)
        assert app.theme == "abc", app.theme
        assert app.title == "Fan Monitor - Agentic Builders Collective"
        if fanless:
            assert not app.animate_brand
            assert not isinstance(app.screen, BrandBoot)
        else:
            assert app.animate_brand
            assert isinstance(app.screen, BrandBoot)
            assert _plain(app.screen.query_one("#boot-product")) == "FAN MONITOR"
            print("boot visible at 0.3s:", True)

        recs = app.query_one("#recs-table")
        procs = app.query_one("#proc-table")
        cpu_t = app.query_one("#cpu-table")
        mem_t = app.query_one("#mem-table")
        wd = app.query_one("#wd-table")
        for _ in range(80):
            if not isinstance(app.screen, BrandBoot) and recs.row_count:
                break
            await pilot.pause(0.25)
        assert not isinstance(app.screen, BrandBoot)
        if not fanless:
            visible_s = time.monotonic() - app._boot_started
            assert visible_s >= 2.95, visible_s
            print(f"boot duration: {visible_s:.1f}s")
        print("recs rows:", recs.row_count)
        print("proc rows:", procs.row_count)
        print("cpu rows:", cpu_t.row_count, "| mem rows:", mem_t.row_count)
        print("wd rows:", wd.row_count)
        print("cpu spark points:", len(app.query_one("#cpu-spark").data))
        fan_title = _plain(app.query_one("#fan-title"))
        print("fan tile title:", fan_title)
        assert fan_title == ("COOLING" if fanless else "FAN"), fan_title

        # ] / [ cycle the tabs
        tabs = app.query_one(TabbedContent)
        await pilot.press("right_square_bracket")
        await pilot.pause(0.3)
        print("tab after ']':", tabs.active)
        assert tabs.active == "tab-cpu"
        await pilot.press("right_square_bracket")
        await pilot.pause(0.3)
        assert tabs.active == "tab-mem"
        await pilot.press("left_square_bracket")
        await pilot.press("left_square_bracket")
        await pilot.pause(0.3)
        assert tabs.active == "tab-close"

        # sort keys change the process sort instantly
        await pilot.press("2")
        await pilot.pause(0.3)
        print("proc_sort after '2':", app._proc_sort)
        await pilot.press("3")
        await pilot.pause(0.3)
        print("proc_sort after '3':", app._proc_sort)
        await pilot.press("1")
        await pilot.pause(0.3)
        print("proc_sort after '1':", app._proc_sort)

        # kill from the Close table
        if recs.row_count:
            recs.focus()
            await pilot.pause(0.2)
            await pilot.press("k")
            await pilot.pause(0.6)
            print("kill modal (Close):", isinstance(app.screen, ConfirmKill))
            await pilot.press("n")
            await pilot.pause(0.4)
            print("  declined ->", not isinstance(app.screen, ConfirmKill))

        # kill from the CPU / Memory / Processes tables
        for tab, table in (("tab-cpu", cpu_t), ("tab-mem", mem_t),
                           ("tab-procs", procs)):
            tabs.active = tab
            await pilot.pause(0.4)
            if table.row_count:
                table.focus()
                await pilot.pause(0.2)
                await pilot.press("k")
                await pilot.pause(0.6)
                print(f"kill modal ({tab}):", isinstance(app.screen, ConfirmKill))
                assert isinstance(app.screen, ConfirmKill)
                await pilot.press("n")
                await pilot.pause(0.4)

        # narrow terminals keep all four gauges; branding remains in the header.
        await pilot.resize_terminal(90, 40)
        await pilot.pause(0.4)
        assert len(app.query(".stat")) == 4
        assert app.title == "Fan Monitor - Agentic Builders Collective"
        print("four gauges at 90 cols:", True)

        ok = (recs.row_count > 0 and procs.row_count > 0
              and cpu_t.row_count > 0 and mem_t.row_count > 0)
        print("POPULATED:", ok)
        return ok


async def main():
    ok_fan = await run_once(fanless=False)
    ok_air = await run_once(fanless=True)
    if not (ok_fan and ok_air):
        print("SMOKE FAILED")
        sys.exit(1)
    print("SMOKE OK")


asyncio.run(main())
