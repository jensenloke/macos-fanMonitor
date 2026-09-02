import asyncio
from textual.widgets import TabbedContent
from fanmon.app import FanMonitorApp, ConfirmKill


async def main():
    app = FanMonitorApp(interval=1.0)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(3.5)  # mount + a couple worker cycles

        recs = app.query_one("#recs-table")
        procs = app.query_one("#proc-table")
        wd = app.query_one("#wd-table")
        print("recs rows:", recs.row_count)
        print("proc rows:", procs.row_count)
        print("wd rows:", wd.row_count)

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

        # switch to Processes tab and kill from there
        app.query_one(TabbedContent).active = "tab-procs"
        await pilot.pause(0.5)
        if procs.row_count:
            procs.focus()
            await pilot.pause(0.2)
            await pilot.press("k")
            await pilot.pause(0.6)
            print("kill modal (Processes):", isinstance(app.screen, ConfirmKill))
            await pilot.press("n")
            await pilot.pause(0.4)

        ok = recs.row_count > 0 and procs.row_count > 0
        print("POPULATED:", ok)

    print("SMOKE OK")


asyncio.run(main())
