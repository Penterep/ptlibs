import threading
from typing import Generic, TypeVar


class ArrayLock:
    def __init__(self) -> None:
        self.lock = threading.Lock()

    def lock_array_append(self, array: list, item) -> None:
        self.lock.acquire()
        array.append(item)
        self.lock.release()

    def lock_array_remove(self, array: list, item) -> None:
        self.lock.acquire()
        array.remove(item)
        self.lock.release()


T = TypeVar('T')
class ThreadSafeArray(list[T], Generic[T]):
    def __init__(self, value: list[T] = None) -> None:
        self._unsafe_array = super()
        if value is not None:
            self._unsafe_array.__init__(value)
        else:
            self._unsafe_array.__init__()
        self._lock = ArrayLock()

    def append(self, item: T) -> None:
        self._lock.lock_array_append(self._unsafe_array, item)

    def remove(self, item: T) -> None:
        self._lock.lock_array_remove(self._unsafe_array, item)

    def copy(self) -> 'ThreadSafeArray[T]':
        return ThreadSafeArray[T](self)