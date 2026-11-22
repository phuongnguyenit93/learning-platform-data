# Waking Up Does Not Guarantee the Condition Is Already True

In `Object`'s monitor mechanism, a thread calls `wait()` because **shared state does not yet satisfy a condition**. When `wait()` completes normally, the thread only knows it has received an opportunity to recheck the state. It **must not infer that the condition is already true** merely because it just woke up.

Core rule: **always check the condition in a `while` loop, under the same monitor that protects that data**.

## 1. What do `wait()` and `notifyAll()` actually do?

Suppose two threads coordinate through a `monitor` object and a `ready` flag:

1. The waiting thread holds the monitor lock via `synchronized (monitor)` and checks `ready`. If `false`, it calls `monitor.wait()` and **releases the monitor lock** while waiting.
2. Another thread acquires that lock, may update the state, and then calls `monitor.notify()` or `monitor.notifyAll()` while holding the lock.
3. The notified thread can resume from `wait()` only **after reacquiring the monitor lock**. In the interval between being notified and reacquiring the lock, the shared state may have changed.
4. The waiting thread must read `ready` again once it holds the lock; if it is still `false`, it continues waiting.

`notify()` selects one thread waiting on the monitor, while `notifyAll()` notifies all threads waiting on the monitor; **neither sets the value of `ready`, confirms the condition, or hands over the lock immediately**. The woken threads continue contending to acquire the monitor.

### Reasons why the condition may still be false after waking up

- **A signal does not mean the condition is true:** the signaling thread may call `notifyAll()` to indicate that *a change occurred*, yet that change is not enough for the waiting thread's condition.
- **Another thread got there first:** after notification, a different thread may acquire the monitor, consume the last item in the queue or modify the state, and release the lock before the waking thread acquires the lock.
- **Spurious wakeup:** Java allows `wait()` to return normally even without a corresponding notification. A correct program must handle this case.
- **Wait timeout:** with `wait(timeout)`, the call can return due to expiration; the condition still needs to be checked.

If interrupted while waiting, `wait()` throws `InterruptedException` after reacquiring the monitor. This is a separate interruption-handling branch, not proof that the condition has been satisfied.

## 2. Wrong with `if`, right with `while`

The examples below are **illustrative code snippets** placed inside a method of a class that has `monitor` and `ready`:

```java
// WRONG: checks the condition only once.
synchronized (monitor) {
    if (!ready) {
        monitor.wait();
    }
    useResource(); // May run while ready is still false.
}
```

Even if `ready` is `false` when waiting begins, `wait()` can return with `ready` still `false`. The resource-using call can therefore run incorrectly.

```java
// RIGHT: the condition is rechecked every time wait() returns.
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    useResource(); // At this point holding this monitor, ready == true.
}
```

What matters lies in the **condition-checking loop**, not in how many `notify` calls were received. Every time `wait()` returns, `while` reads the fresh state under the lock; if the condition is still false, the thread waits again. The thread updating `ready` must also use **this exact monitor**, preserving consistency and the memory-visibility relationship of `synchronized`.

## 3. Runnable Java 17+ example

The following program intentionally calls `notifyAll()` once **while `ready` is still `false`**, and only afterward updates `ready = true` and notifies again. The two `CountDownLatch` instances only help coordinate timing in the demonstration; the `ready` data is still protected by the `Object`'s monitor.

Save into **`WaitPredicateDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class WaitPredicateDemo {
    private static final Object monitor = new Object();
    private static boolean ready = false;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstWait = new CountDownLatch(1);
        CountDownLatch secondWait = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (monitor) {
                int attempt = 0;
                while (!ready) {
                    attempt++;
                    System.out.println("worker: ready=false, wait #" + attempt);

                    if (attempt == 1) {
                        firstWait.countDown();
                    } else if (attempt == 2) {
                        secondWait.countDown();
                    }

                    try {
                        monitor.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        System.out.println("worker: interrupted, exiting");
                        return;
                    }
                }

                System.out.println("worker: ready=true, continuing");
            }
        });

        worker.start();
        firstWait.await();

        synchronized (monitor) {
            System.out.println("main: notifyAll while ready is still false");
            monitor.notifyAll();
        }

        secondWait.await();
        synchronized (monitor) {
            ready = true;
            System.out.println("main: ready=true then notifyAll");
            monitor.notifyAll();
        }

        worker.join();
    }
}
```

Compile and run:

```bash
javac WaitPredicateDemo.java
java WaitPredicateDemo
```

Illustrative output in a normal run (without extra spurious wakeups):

```text
worker: ready=false, wait #1
main: notifyAll while ready is still false
worker: ready=false, wait #2
main: ready=true then notifyAll
worker: ready=true, continuing
```

**Interpretation:** after the first `notifyAll()`, the `worker` thread reacquires the monitor, sees `ready` is still `false`, and enters `wait()` a second time. Only when the `main` thread changes `ready` to `true` under the monitor does `worker` get past the `while` condition. Spurious wakeups may produce additional wait iterations, but will not let `worker` pass the loop while `ready` remains false.

## 4. Distinguishing the wakeup cause from the state allowing execution

Suppose multiple waiters are waiting for `ready == true`. Every wakeup cause only brings the thread back to the **predicate check point**; no cause replaces that check step.

| Reason `wait()` returns normally | Is `ready` guaranteed `true`? | How `while` handles it |
| --- | --- | --- |
| `notifyAll()` while `ready` is still `false` | No | Reacquires monitor and waits again. |
| `notifyAll()` after `ready` became `true` | Not guaranteed by the time the waiter reacquires the lock; another thread may change state | Re-reads `ready`, proceeds only if true. |
| Spurious wakeup | No | Rechecks and waits again if condition is still false. |
| `wait(timeout)` expires | No | Checks state and remaining wait budget per the caller's timeout contract. |

A notable case is **multiple waiter groups waiting on different conditions under the same monitor**: producers wait for the buffer not to be full, consumers wait for the buffer not to be empty. `notifyAll()` wakes both groups, yet each thread may only proceed when its own group's predicate is true. A complete Java example for producer–consumer and a detailed explanation of the `while` loop are in the lesson **"Use a `while` loop to check the condition before and after waiting"**.

If `wait()` throws `InterruptedException`, the thread enters the **interruption-handling branch** after reacquiring the monitor; that is not a normal return where the condition can be assumed satisfied.

## 5. Checklist when writing code with monitors

- **Tie waiting to a concrete condition:** define a predicate, such as `queue.isEmpty()` or `!ready`, and recheck the predicate with `while`.
- **One lock for checking, waiting, and modifying state:** call `wait()`, `notify()`, or `notifyAll()` only while owning the corresponding monitor; otherwise Java throws `IllegalMonitorStateException`.
- **Modify state before notifying:** under the same monitor, update shared data and then call `notifyAll()` when the change may allow other threads to proceed. Notifying without updating the predicate can make everyone go back to waiting.
- **Do not place condition-dependent work right after `wait()` without rechecking.** If `wait()` has a timeout, you still must evaluate the predicate and expiration policy; a timeout does not mean success.
- **Handle interruption deliberately:** if execution cannot continue when `InterruptedException` occurs, restore the interrupt flag with `Thread.currentThread().interrupt()` and exit; do not silently swallow the interruption.
- **Prefer higher-level synchronization constructs when appropriate:** `BlockingQueue`, `CountDownLatch`, `Semaphore`, or `Condition` can express intent more clearly; when using `Condition.await()`, normal condition waiting also needs a predicate-checking loop.

**Key takeaway:** a wakeup signal only creates *an opportunity to recheck*. **Only the condition on shared state, read inside `while` while holding the right lock, allows the thread to proceed.**
