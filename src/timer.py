import asyncio
import logging
from typing import Callable, Coroutine, Optional


logger = logging.getLogger("timer")


class Timer:
    """A simple async timer"""

    #: Refresh frequency in seconds, until DISPLAY_SECONDS is hit
    REFRESH = 30
    #: timer embed will callback every second (more or less) starting from this point
    DISPLAY_SECONDS = 5 * 60
    #: pause will timeout after that many seconds
    PAUSE_TIMEOUT = 1800

    def __init__(
        self,
        time: float,
        update_callback: Callable[[float], Coroutine[None, None, None]],
    ):
        """After run(), The update_callback is called regularily until time is up."""
        self.left: float = float(time)
        self.callback = update_callback
        # internals
        self._stopped: bool = False
        self._offset: float = 0
        self._future_display: Optional[asyncio.Task] = None
        self._future_resume: Optional[asyncio.Task] = None

    def _refresh_offset(self) -> None:
        """Internal: used to compute the new time left"""
        new_offset = asyncio.get_event_loop().time()
        self.left -= min(self.left, max(0, new_offset - self._offset))
        self._offset = new_offset

    def _resume(self) -> None:
        """Internal. Sets the offset to current (resume) time"""
        self._future_resume = None
        self._offset = asyncio.get_event_loop().time()

    async def run(self) -> None:
        """Main loop."""
        self._offset = asyncio.get_event_loop().time()
        while self.left > 0:
            await self.callback(self.left)
            # precise last callback
            if self.left < 2:
                self._future_display = asyncio.create_task(asyncio.sleep(self.left))
            # below DISPLAY_SECONDS, a second-by-second display
            elif self.left < self.DISPLAY_SECONDS + self.REFRESH:
                # 0.5 would be ideal but Discord rate limitations makes it clunky
                # so we try to adjust to stay close to round seconds on time left
                self._future_display = asyncio.create_task(asyncio.sleep(1.01))
            # standard minute-by-minute display
            else:
                self._future_display = asyncio.create_task(asyncio.sleep(self.REFRESH))
            try:
                logger.debug("Countdown to callback")
                await self._future_display
                self._refresh_offset()
            except asyncio.CancelledError:
                logger.debug("Countdown canceled")
                if self._stopped:
                    break
            # when pausing, _future_resume is set, then _future_display is cancelled
            # so the offset and time left are refreshed just befaure starting to wait
            if self.paused:
                try:
                    logger.debug("Wait for resume")
                    await self._future_resume
                except asyncio.CancelledError:
                    logger.debug("Pause cancelled")
                    if self._stopped:
                        break
                logger.debug("Resume")
                self._resume()
        # only callback if we have not been forcefully stopped
        else:
            await self.callback(0)

    def adjust_time(self, time: float) -> None:
        """Forcefully change time left (add or subtract, time can be negative)."""
        self.left = max(0, self.left + time)
        # if not paused, this forces the display callback
        self._future_display.cancel()

    def pause(self) -> float:
        """Pause the timer. No effect if already paused. Return time left"""
        if self._future_resume is None:
            self._refresh_offset()
            self._future_resume = asyncio.create_task(asyncio.sleep(self.PAUSE_TIMEOUT))
            self._future_display.cancel()
        return self.left

    def resume(self) -> None:
        """Resume the timer. No effect if the timer is not paused."""
        if self._future_resume is None:
            return
        self._future_resume.cancel()
        self._future_resume = None

    def stop(self) -> float:
        """Stops the timer"""
        if self._future_resume is not None:
            self._future_resume.cancel()
            self._future_resume = None
        else:
            self._refresh_offset()
        self._stopped = True
        self._future_display.cancel()
        return self.left

    @property
    def paused(self):
        """True if the timer is paused"""
        return self._future_resume is not None
