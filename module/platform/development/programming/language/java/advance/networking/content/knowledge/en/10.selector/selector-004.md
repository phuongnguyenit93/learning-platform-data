# select, selectNow, timed select, and the wakeup mechanism

## Objectives

In Java NIO, `java.nio.channels.Selector` allows **a single thread to coordinate multiple selectable channels** (`SelectableChannel`) without needing one thread blocking on `read()` per socket. The focus of this lesson is **the three ways to perform selection** and the **`wakeup()`** mechanism to wake the event loop at the right time.

After this lesson, you can:

- Distinguish `selector.select()`, `selector.selectNow()`, and `selector.select(timeoutMillis)` in terms of waiting conditions, return timing, and return values.
- Understand precisely the `timeout = 0` case, `timeout < 0`, nonblocking polling choices, and that timeout **does not guarantee real-time precision**.
- Explain `wakeup()` when a thread is currently in `select` or when `wakeup` occurs **before** the next `select`; why multiple wakeups **do not accumulate into a queue**.
- Properly handle `selectedKeys()`, `SelectionKey.interestOps()`, `readyOps()`, and `Iterator.remove()` in an event loop.
- Combine `ConcurrentLinkedQueue` + `wakeup()` so other threads can send registration/interest-change/shutdown commands to the thread owning the selector; avoid common races.
- Run a Java 17+ example verifying the modes with results independent of network timing, then apply the selection loop pattern to a TCP server.

This lesson focuses on **Selector and the wakeup mechanism**, not designing a complete TCP protocol. When examples use sockets, it is only to explain readiness (`OP_ACCEPT`, `OP_READ`, `OP_WRITE`), without equating readiness with a complete application message.

## 1. Selector monitors readiness, it does not read data for you

A channel that wants to register with a selector must be in **nonblocking mode**:

~~~java
server.configureBlocking(false);
SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
~~~

This snippet assumes `server` is an opened/bound `ServerSocketChannel` and `selector` is already open; it is not a standalone program. Registering a blocking channel with a selector will throw `IllegalBlockingModeException`.

Each registration is represented by a `SelectionKey`. The important bits:

| Operation | Typical channel type | Meaning of ready |
|---|---|---|
| `OP_ACCEPT` | `ServerSocketChannel` | Can attempt `accept()` without blocking |
| `OP_CONNECT` | nonblocking `SocketChannel` | Connection progress is available to check `finishConnect()` |
| `OP_READ` | `SocketChannel`, `DatagramChannel` | Can attempt to read/receive; EOF can also make a channel "readable" |
| `OP_WRITE` | `SocketChannel`, `DatagramChannel` | Can attempt to write; does **not** guarantee writing the entire buffer |

**Readiness only means an I/O operation is likely to make progress, not that it will complete.** `SocketChannel.read` can still return `0` and `write` can still write fewer bytes than requested. With TCP, the application needs to maintain per-connection state/buffers and handle message framing itself.

A selector manages three sets of keys:

- `keys()`: registrations still belonging to the selector.
- `selectedKeys()`: keys recorded as ready in a previous selection or just updated in the new selection. This set is **not automatically cleared** after each `select`.
- Cancelled-key set (not directly accessible): keys that have been cancelled and are waiting for the cancellation/deregistration step in the next selection.

One thread typically **owns** the event loop and iterates over selected keys; other threads send commands to it instead of concurrently manipulating `selectedKeys()`.

## 2. Three ways to select: `select()`, `selectNow()`, and `select(timeout)`

| Call | Does it wait? | When does it return? | Suitable use case |
|---|---|---|---|
| `select()` | Yes, can wait indefinitely | Readiness, `wakeup`, interrupt, or another selection termination reason | I/O loop that only needs to wake when there are events/commands |
| `selectNow()` | **Non-blocking** | Returns immediately after polling readiness at that moment | Short polling, integrating with a processing loop that has other work |
| `select(timeoutMillis)` with `timeout > 0` | Yes, waits **at most approximately** the requested duration | Readiness, wakeup, interrupt, or timeout | Event loop with periodic tasks, idle housekeeping/deadlines |
| `select(0)` | **Waits like `select()`, not a poll** | When there is a wakeup cause | Need to wait indefinitely while passing timeout explicitly |
| `select(timeoutMillis)` with `timeout < 0` | Does not perform selection | Throws `IllegalArgumentException` | Invalid input, must validate beforehand |

Be sure to distinguish two easily confused expressions:

~~~java
selector.selectNow(); // Poll immediately; DOES NOT wait.
selector.select(0);   // Can wait indefinitely; NOT a poll.
~~~

**Timeout duration:** the `long timeout` parameter is interpreted in **milliseconds**. `select(250)` may wait around 250 ms if there are no events, but thread/OS scheduling has latency so there is **no real-time guarantee**. It can also return **early** due to wakeup, interrupt, or an I/O event. For accurate business scheduling, re-check the monotonic clock (`System.nanoTime()`) after each iteration.

**Return value:** all three overloads return an `int` — the number of keys whose ready-operation sets were updated by the **just-performed selection operation** (per the Java 17 API specification). This number can be `0`. It **does not necessarily equal `selector.selectedKeys().size()`**, because the selected-key set may still contain keys you did not remove from a previous round.

For example, `selectNow() == 0` does not mean no channel has ever been ready during the entire lifecycle; it only says the latest selection did not record any readiness updates according to the API rules. Do not use the return value as the list of remaining work; process the selected-key set and the application's command queue according to the proper model.

### When should you choose each overload?

- **Pure I/O loop:** `select()` to sleep until readiness arrives; other threads must use `wakeup()` when they need it to process management commands.
- **With heartbeat/cleanup:** `select(positiveMillis)` to avoid sleeping too long if there are no network events. After waking up, check the actual deadline rather than relying solely on counting timeouts.
- **Doing other work and only wanting to poll:** `selectNow()`, but do not call it continuously in a `while` loop without sleeping when there are no events — that will cause a busy spin.

**Note:** the overloads `select(Consumer<SelectionKey>, ...)` and `selectNow(Consumer<SelectionKey>)` also exist in Java 17 (since Java 11); they consume keys via a callback instead of using the selected-key set itself as shown below. This lesson uses the simple `int select...()` overloads to clearly show `selectedKeys()`.

## 3. `wakeup()`: a one-shot wakeup signal, not a datagram or "new event"

According to Java 17, `selector.wakeup()` causes the **first selection operation that has not yet returned** to return early:

1. **If a thread is currently blocked in `select()` or `select(timeout)`:** `wakeup()` wakes that call. It may return `0` if no keys are ready, or return a non-zero number if readiness occurs simultaneously.
2. **If no selection is currently waiting:** the next selection will **return immediately**, unless `selectNow()` is called in between and clears the pending wakeup effect.
3. **Multiple `wakeup()` calls before a selection:** have the same effect as **one** call. The selector does not accumulate "5 wakeup tokens" for 5 `select` calls.
4. **After a selection has consumed the signal:** subsequent `select` calls can block normally if there is no readiness or new signal.
5. **`wakeup()` does not change readiness, does not write to a socket, does not enqueue commands, and does not close the selector.** It only gives the event loop an opportunity to check other work.

Example of a valid sequence:

~~~text
Thread A (event loop)             Thread B (producer)
        |                                  |
     select()  <---------------------  wakeup()
        |                                  |
   select() returns                        |
   check queue/selectedKeys                |
        |                                  |
     select() (may block again)            |
~~~

And the case where wakeup occurs **before** select:

~~~text
Thread B: queue.add(command)
Thread B: selector.wakeup()

Thread A: selector.select()   → returns immediately due to pending wakeup
Thread A: drain queue         → execute command
~~~

This is why the **enqueue first, wakeup after** pattern is safer than a model that only calls wakeup without a source of truth for work. If thread A just checked an empty queue and is about to enter `select`, a wakeup signal arriving before `select` is still preserved for the next selection.

**Pitfall:** between `wakeup()` and `select()`, if code calls `selectNow()`, the pending wakeup effect is **cleared**. If at the same time there are no events or there are unprocessed commands, the subsequent `select()` may block. Do not use wakeup as a mechanism to track the **count** of work items; use a queue with real state.

### `wakeup()` vs. `interrupt()` and `close()`

| Operation | Meaning | Consequence |
|---|---|---|
| `selector.wakeup()` | Requests selection to return early | Selector remains open; can continue to be used |
| `selectionThread.interrupt()` | Requests interrupting the blocked thread | Wakes selection, **sets interrupt status**; requires a handling policy |
| `selector.close()` | Closes the selector | Registration keys are invalidated/deregistered, waiting selection is woken up; subsequent select operations throw `ClosedSelectorException` |

Calling `close()` on a selector **does not mean closing all registered `SocketChannel`s**. The application owning those channels must still manage and close them according to their lifecycle. `interrupt()` is not a complete replacement for a normal stop mechanism if the event loop still needs to drain tasks and close sockets in order.

## 4. Java 17+ demo verifying all three selection modes and wakeup

The following **`SelectorModesDemo.java`** file intentionally **registers no channels**. Because there is no readiness, every completed selection returns `0`; the example isolates and clarifies **the waiting and wakeup mechanics** without depending on the network, ports, or packet arrival timing.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.channels.Selector;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SelectorModesDemo {
    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open()) {
            System.out.println("selectNow: " + selector.selectNow());

            selector.wakeup();
            System.out.println("pre-wakeup select: " + selector.select());

            selector.wakeup();
            System.out.println("selectNow clears wakeup: " + selector.selectNow());

            System.out.println("timed select: " + selector.select(50));

            CountDownLatch aboutToSelect = new CountDownLatch(1);
            AtomicInteger result = new AtomicInteger(-1);
            Thread worker = new Thread(() -> {
                aboutToSelect.countDown();
                try {
                    result.set(selector.select());
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            worker.start();
            aboutToSelect.await();
            selector.wakeup();
            worker.join(2_000);

            if (worker.isAlive()) {
                selector.close();
                worker.join();
                throw new IllegalStateException("Selector did not wake");
            }

            System.out.println("cross-thread wakeup select: "
                + result.get());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SelectorModesDemo.java
java SelectorModesDemo
~~~

Stdout for a normal run (tested with a Java runtime):

~~~text
selectNow: 0
pre-wakeup select: 0
selectNow clears wakeup: 0
timed select: 0
cross-thread wakeup select: 0
~~~

**Step-by-step explanation:**

- The first `selectNow()` does not wait and finds no registered channels: `0`.
- `wakeup()` occurs **before** `select()`, so `select()` returns immediately even without readiness.
- Another `wakeup()` is called, then `selectNow()`: the poll call also **clears the pending wakeup effect**.
- `select(50)` waits at most around 50 ms when no keys are ready. Actual elapsed time may vary; do **not** assert that the wall clock must be exact to 50.000 ms. The return value is still `0`.
- `CountDownLatch` signals that the worker has reached right before the `select()` call, then main calls `wakeup()`. Both schedules are valid: the worker **already blocked** and was woken up; or the signal arrived **before** the worker blocked and was preserved for the subsequent call. `join` bounds the test wait time instead of using `sleep` to "guess" timing.
- There are no network channels, so `0` at the end is **not an error**. It proves wakeup can return without any ready keys.

The example tests **wakeup semantics**, not timing benchmarks. If the system is experiencing a platform bug or the thread is abnormally stuck, the timed join check will throw an exception instead of hanging silently.

## 5. Additional demo: real readiness with `OP_ACCEPT`

A selector is typically used after creating a nonblocking channel, such as `ServerSocketChannel`. The following Java 17 snippet does not replace `main` above, but shows that **selected keys only have meaning once interest is registered**. This is a **standalone method that can be placed in a class** with imports `java.net.*`, `java.nio.channels.*`, and `java.util.Iterator`:

~~~java
static void acceptOnce() throws Exception {
    try (Selector selector = Selector.open();
         ServerSocketChannel listener = ServerSocketChannel.open()) {

        listener.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
        listener.configureBlocking(false);
        listener.register(selector, SelectionKey.OP_ACCEPT);

        try (SocketChannel client = SocketChannel.open()) {
            client.connect(listener.getLocalAddress());
            long deadline = System.nanoTime() + 2_000_000_000L;
            boolean accepted = false;

            while (!accepted && System.nanoTime() < deadline) {
                selector.select(200);
                Iterator<SelectionKey> it =
                    selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();

                    if (key.isValid() && key.isAcceptable()) {
                        try (SocketChannel incoming =
                                 ((ServerSocketChannel)
                                 key.channel()).accept()) {
                            accepted = incoming != null;
                        }
                    }
                }
            }

            System.out.println("accepted: " + accepted);
        }
    }
}
~~~

The method above was tested with a **loopback** TCP connection and produced:

~~~text
accepted: true
~~~

This result depends on the ability to establish a connection on the actual machine, not a constant guaranteed by the API in every environment. `select(200)` may return `0` a few times, but the loop continues running until the deadline. `accept()` itself is called on a nonblocking channel so it can return `null`; the code checks before concluding success.

**Why is `iterator.remove()` necessary?** `selectedKeys()` is the "selected" set retained across iterations; after processing, you must **remove the key from the selected-key set**, not arbitrarily call `key.cancel()`. `cancel()` means wanting to cancel the registration, whereas remove only marks **this batch's readiness as handled** and allows subsequent selections to update cleanly.

## 6. Event loop pattern that properly handles selected keys

Foundational pattern in an I/O thread:

~~~java
while (running) {
    int updated = selector.select(1_000);

    Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Remove from selected set; do not cancel.

        if (!key.isValid()) {
            continue; // May have been cancelled/closed.
        }

        if (key.isAcceptable()) {
            onAccept(key); // Application method you implement.
        }
        if (key.isReadable()) {
            onRead(key);   // Nonblocking read + maintain per-connection state.
        }
        if (key.isWritable()) {
            onWrite(key);  // Nonblocking write of pending bytes.
        }
    }

    performExpiredTimers();
}
~~~

This is an **illustrative pattern**, not a self-running Java class: `running`, `selector`, and the methods `onAccept`/`onRead`/`onWrite`/`performExpiredTimers` must be defined by the application. What matters is not the method names but the **order**:
1. Select readiness or wait until timeout/wakeup.
2. Iterate over the **entire** selected-key set, not just `updated` elements.
3. Remove each key from the selected-key set **before** dispatching, to avoid reprocessing an old key.
4. Check `key.isValid()` because another thread may have closed the channel/cancelled the key.
5. Perform **nonblocking** I/O and do not run heavy CPU work directly inside the event loop.
6. Perform periodic work after waking even if `updated == 0`.

If your `onRead` implementation cannot read all data immediately, it must still manage the input buffer and protocol framing. If `onWrite` writes partially, keep the remaining buffer and wait for the next `OP_WRITE`. One selection is not a complete read/write.

### `keys()`, `selectedKeys()`, and the return value of select

Do not write:

~~~java
int n = selector.select();
if (n > 0) {
    // Wrong if assuming selectedKeys has exactly n elements,
    // or forgetting to process tasks woken up when n == 0.
}
~~~

`n` only reflects the **just-completed selection**; `selector.selectedKeys()` may hold old unremoved keys. And a `wakeup()` can cause `select` to return `0` even though there are application commands to execute. The safe approach is to **iterate over selectedKeys and drain the command queue**, never treating `n == 0` as proof that "there is no work".

`selector.keys()` is the set of all registrations, **not** the currently ready channels. `key.interestOps()` is the set of I/O types the application wants to monitor; `key.readyOps()` is the set of types just detected as ready. `readyOps` can become stale if the selected-key set is not managed properly; do not equate the two bitmasks.

## 7. Other threads sending commands: command queue + wakeup

A subtle bug is when a producer thread adds a task after the event loop has checked the queue, but before the event loop enters `select()`; if `wakeup()` is not called, the task may wait until an unexpected network event or timeout.

Appropriate model:

~~~java
// Illustrative declarations in the event loop management class:
final Selector selector = Selector.open();
final java.util.concurrent.ConcurrentLinkedQueue<Runnable> commands =
    new java.util.concurrent.ConcurrentLinkedQueue<>();

void submitToEventLoop(Runnable command) {
    commands.offer(command);
    selector.wakeup();
}
~~~

This is an **illustrative snippet belonging to a class**; you need to declare/close the selector according to its lifecycle and handle `IOException` from `Selector.open()` in an appropriate constructor. `commands` is where the **actual work** is stored; `wakeup()` is only a signal for the selector thread to drain the queue soon.

Event loop after select:

~~~java
selector.select();

Runnable command;
while ((command = commands.poll()) != null) {
    command.run(); // Short work only; do not block the event loop for long.
}

// Then iterate over selector.selectedKeys() with iterator/remove.
// On shutdown, check the running flag and close channels per policy.
~~~

This is a corresponding snippet, not a standalone `main` program.

**Command to change interest from another thread:** instead of the producer thread modifying the key itself while selection is in progress, it usually submits a command to the I/O thread:

~~~java
submitToEventLoop(() -> {
    if (key.isValid()) {
        key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
    }
});
~~~

Ensure `key` represents a `SocketChannel` that supports these operations. According to the documentation, `interestOps` changes made **while a selection is in progress** are only considered for the next selection; therefore, organizing updates through the owner thread and wakeup helps reduce races.

**Lost signal pitfall:** using the wrong order `selector.wakeup(); commands.offer(command);` can cause the selector to wake up and check the queue before the command appears, then block again. The correct order is **enqueue → wakeup**. Similarly, after `wakeup` has created a pending signal, calling `selectNow()` in between can consume that signal; if the application uses a queue and checks it on every iteration, work still does not depend on "counting wakeups".

**Coalescing pitfall:** five tasks enqueued in quick succession may only need one wakeup. Do not write a system expecting each `wakeup` to correspond to exactly one processing pass; `poll` until the queue is empty. If a task arrives while draining, because the producer calls wakeup after offer, the event loop can be woken once more; accurate task processing comes from the queue, not from the wakeup count.

## 8. `OP_WRITE` and the busy loop problem

For a writable TCP socket, `OP_WRITE` is usually ready most of the time. If you register interest in `OP_WRITE` **at all times** even when there are no bytes to send, `select()` will continuously return and the event loop can consume high CPU while doing nothing useful.

Standard rule:

1. When the outbound queue is **empty**, normally only monitor `OP_READ` (and other truly needed interests); **do not enable `OP_WRITE`**.
2. When there are bytes to send, place the data into a buffer/queue and then **enable `OP_WRITE`** via the owner thread, calling `wakeup()` if operating from another thread.
3. In `onWrite`, call `SocketChannel.write(buffer)`, which may write only partially.
4. If bytes remain, keep `OP_WRITE`; once the queue has **completely drained**, **clear `OP_WRITE`** to avoid a busy-spin.

Bitmask calculation example (illustrative snippet; `key` and queue state belong to the handler):

~~~java
int current = key.interestOps();
key.interestOps(current | SelectionKey.OP_WRITE);  // Need to send.

int afterDrained = key.interestOps();
key.interestOps(afterDrained & ~SelectionKey.OP_WRITE); // Out of data.
~~~

Do not enable `OP_WRITE` when the channel has no pending outbound data just because you "want to write fast". Similarly, calling `selectNow()` continuously in a non-sleeping loop will burn CPU; the selector can do useful work via blocking select or timed select.

## 9. Timed waiting and business deadlines

`selector.select(500)` specifies **a wait of at most roughly 500 ms**, not an exact timer. An I/O event or wakeup makes it return early. If you need periodic tasks or client timeouts:
- Use the monotonic clock `System.nanoTime()` to store deadlines.
- After every select — **even when the return value > 0** — check for expired deadlines.
- Recalculate the wait time from the **next deadline**, rather than always using a fixed 500 ms if an earlier deadline exists.
- When converting nanoseconds to millis, clamp away from `0` if you still want a **positive timeout**: `select(0)` means **wait indefinitely**.

A timeout calculation pattern for a remaining-time target (illustrative Java snippet; `deadlineNanos` is computed beforehand using `System.nanoTime()`):

~~~java
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    runExpiredTimers();
} else {
    long millis = Math.max(
        1L,
        java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(remainingNanos));
    selector.select(millis);
    runExpiredTimers(); // Recheck using System.nanoTime().
}
~~~

This code is **only an illustrative deadline loop**; a real event loop must continue dispatching selected keys and commands. Rounding from nanos to millis plus system latency can cause slight timing drift; it does not replace a real-time scheduler.

If event/read/write/CPU processing inside the event loop takes seconds, `select(100)` also **does not guarantee** the application will run timers every 100 ms. The I/O thread must process quickly, split work appropriately, and offload heavy CPU tasks to another executor.

## 10. Waking up on shutdown and resource lifecycle

A coordinated shutdown across threads can use a `running` flag and a queue:

~~~java
// Thread coordinating shutdown:
running.set(false);
selector.wakeup(); // Wake the I/O thread out of select().

// In the I/O thread after select returns:
if (!running.get()) {
    // Exit loop, close registered channels and selector per lifecycle.
}
~~~

This pattern assumes `running` is an `AtomicBoolean`. Do not just set the flag to false and forget `wakeup()` if the event loop is in an indefinite `select()` — it may not see the new flag until some other I/O arrives. With a finite `select(timeout)`, the loop may eventually wake on timeout, but shutdown is unnecessarily delayed.

Exception cases to anticipate:

- **`ClosedSelectorException`:** the selector is already closed; do not continue calling `select`/`selectedKeys` as usual.
- **`CancelledKeyException`:** the key was cancelled while checking readiness/interest ops; close or skip the channel according to its lifecycle.
- **`IOException`:** system errors during selection/I/O must be logged and recovered from or closed appropriately. Do not use a `while(true)` loop that catches all exceptions and immediately calls `selectNow()`, causing CPU spin.
- **Thread interrupt:** the selector is woken up and the thread's interrupt status is set. A loop that does not handle interrupts may keep spinning rapidly; have a clear exit/recovery policy.
- **Selector close:** cancels registrations and wakes selection, but managing/closing `SocketChannel` and `ServerSocketChannel` remains the program's responsibility.

For applications with many connections, do not close the selector immediately upon receiving a shutdown command if socket cleanup/outbound flushing still needs to happen: clearly decide whether you need **graceful drain** or **immediate close**, with a deadline, without holding connections indefinitely.

## 11. Testing edge cases

| Test | Expected result |
|---|---|
| New selector, no registered keys, call `selectNow()` | Returns `0` immediately |
| `wakeup()` then `select()`, no readiness yet | Returns immediately, may be `0` |
| `wakeup()` multiple times before selection | Acts as a wakeup for **one** next selection, does not stack |
| `wakeup()` then `selectNow()`, followed by `select()` | `selectNow` cleared the pending wakeup effect; subsequent `select` may block |
| `select(50)` on a selector with no ready keys | Returns roughly after timeout or earlier if woken; `0` in the demo |
| `select(0)` on a selector with no readiness | Can wait indefinitely; needs another thread to wakeup/close/interrupt |
| `select(-1)` | Throws `IllegalArgumentException` |
| A key is in `selectedKeys` but not removed | May persist across the next selection round; do not assume `size == return value` |
| Cross-thread enqueue right before `select` | `offer` then `wakeup` ensures the command is processed promptly |
| Enable `OP_WRITE` when output queue is empty | Risk of selector spinning rapidly, high CPU |
| Cancel key in event loop | Skip invalid key; deregistration is handled by selection |
| Close selector while another thread is selecting | Selection is woken up, selector resources are released; manage channels separately |

**Timing test note:** do not assert `elapsedMillis == 50`. Verify that polling `selectNow` does not block long, timed `select` does not wait indefinitely under normal conditions, and wakeup causes selection to end early; concurrency tests should use `CountDownLatch` rather than relying on `Thread.sleep` to guess races. Tests should have their own deadlines to avoid hanging CI.

## 12. Common mistakes

| Mistake | Why is it wrong? |
|---|---|
| Thinking `select(0)` is equivalent to `selectNow()` | `select(0)` **waits indefinitely**, whereas `selectNow` is non-blocking |
| Thinking `wakeup()` always returns exactly 0 | Readiness can appear simultaneously, so the return value can be >0 |
| Thinking one wakeup corresponds to one command | Multiple wakeups coalesce; commands must be stored in a queue |
| Calling `wakeup()` before enqueueing | Creates a race window where the selector goes back to sleep before the task appears |
| Calling `selectNow()` after wakeup and expecting `select()` to still wake | `selectNow` cleared the pending wakeup effect |
| Skipping the command queue if `select() == 0` | `0` can be due to wakeup/timeout, and the queue may still have work |
| Assuming `select()` returns exactly `selectedKeys().size()` | The selected set retains unremoved keys; the return value reflects the current selection |
| Iterating `selectedKeys` without `Iterator.remove()` | Already-processed keys remain in the set and get processed again |
| Using `key.cancel()` instead of `iterator.remove()` | Cancel destroys the registration, rather than marking a readiness event as handled |
| Changing interest set while selection is running and expecting immediate effect | Changes are observed in the next selection; must coordinate wakeup/owner thread |
| Registering `OP_WRITE` at all times | Sockets are usually writable → CPU spin |
| Running long CPU tasks on the selector thread | Stalls socket handling and other deadlines |
| Registering a blocking channel with a selector | `IllegalBlockingModeException`; call `configureBlocking(false)` first |
| Relying on a single `read` for a complete TCP message | Readiness does not preserve message framing; TCP is a stream |
| Calling `close()` on the selector and thinking all sockets are closed too | The application must manage channel lifecycles separately |

## 13. Self-check exercises

1. Why is `select(0)` not a way to check for available events? State the correct API for polling.
2. Thread A is in `select()`, thread B calls `wakeup()`, and no sockets are ready. What can the return value of `select` be?
3. A thread calls `wakeup()` twice **before** the event loop enters `select()`. Does it get "two non-blocking selects"? Why?
4. Why must you call `queue.offer(command)` **before** `selector.wakeup()` when controlling the event loop from another thread?
5. There are 3 keys in `selectedKeys` because the previous round did not remove them, and a new `selectNow()` returns `0`. Can you conclude `selectedKeys` is empty?
6. If `selectNow()` is called right after `wakeup()` and before `select()`, does the wakeup signal still have effect?
7. Why should you only add `OP_WRITE` when the outbound queue has data? What should you do once everything has been written?
8. A periodic task must run after 200 ms. If `select(200)` returns early after 30 ms due to I/O readiness, should you execute the task immediately?
9. Another thread calls `key.interestOps(...)` during selection. Should you expect the ongoing selection to immediately pick up the new interest?
10. To stop an event loop blocked indefinitely in `select()`, is setting `running = false` enough?
11. When `selectedKeys` contains an invalid key, how should you handle it? How does that differ from cancelling every key after each processing pass?

**Suggested answers:** (1) `selectNow()`; (2) it can be `0`; (3) no, wakeups coalesce; (4) to avoid the "wake up before work is visible" race; (5) no; (6) `selectNow` clears a pending wakeup; (7) remove `OP_WRITE` once drained; (8) only run it when checking the actual deadline shows it has arrived; (9) no, it affects the next selection; (10) you need `wakeup()`/a wakeup mechanism; (11) skip/close according to lifecycle, and `Iterator.remove()` for a processed selected key differs from `key.cancel()` which cancels the registration.

## 14. Summary

- **`select()`** waits for readiness/wakeup/interrupt; **`selectNow()`** is non-blocking; **`select(timeout > 0)`** waits for an approximate duration; **`select(0)` is an indefinite wait**, not polling.
- **`wakeup()`** wakes a waiting selection or the next selection; repeated calls **do not accumulate**. `selectNow()` can consume a pending wakeup.
- **It can return `0` and still have work to do**: check the command queue and deadlines; use `Iterator.remove()` when processing selected keys, and do not equate the return value with the number of remaining selected keys.
- **Cross-thread:** keep work in a queue, `offer → wakeup`, and update interest on the owner thread when possible.
- **Avoid busy spin:** do not poll `selectNow` continuously or enable `OP_WRITE` when there is no output; keep I/O handling nonblocking and CPU work short on the selector thread.
- **Lifecycle management:** stop flag + wakeup, handle exceptions/interrupts, and close the selector and channels according to a clear policy.

### References

- [Oracle Java SE 17 — Selector: select, selectNow, select(timeout), wakeup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Oracle Java SE 17 — SelectionKey: interestOps, readyOps, isValid](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Oracle Java SE 17 — SelectableChannel: configureBlocking/register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Oracle Java SE 17 — ServerSocketChannel, nonblocking accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Oracle Java SE 17 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)
