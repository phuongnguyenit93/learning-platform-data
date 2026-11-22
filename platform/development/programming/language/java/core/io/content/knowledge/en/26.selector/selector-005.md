# Java NIO Selector: `select()`, `selectNow()`, and `select(timeout)`

## 1. What Problem Does Selector Solve?

When a server needs to monitor hundreds of sockets, dedicating a thread blocked on reads for each connection can consume significant resources. Java NIO provides **`java.nio.channels.Selector`** so a single thread can check which **`SelectableChannel`** instances are currently *ready* to perform an interested I/O operation, and then handle the corresponding channels.

Selector does not transfer data directly. It only lets the application detect readiness conditions such as:

- `SelectionKey.OP_ACCEPT`: server socket is capable of accepting a connection.
- `SelectionKey.OP_CONNECT`: connecting socket can complete its connection.
- `SelectionKey.OP_READ`: channel can perform a read operation without blocking for data under the system's readiness semantics.
- `SelectionKey.OP_WRITE`: channel can perform a write operation under readiness conditions.

**Readiness does not equate to completing the work.** A read-ready socket can still return `0`, `-1`, or fewer bytes than expected; a write-ready socket can still perform a partial write. Selector does not replace checking `read/write` return values and managing `ByteBuffer`.

Three key selection methods are central:

1. `selector.select()`: **waits** until a readiness event occurs or it is woken up/interrupted.
2. `selector.selectNow()`: **checks immediately**, without waiting.
3. `selector.select(timeoutMillis)`: **waits up to a time limit** when `timeoutMillis > 0`; note that **`timeoutMillis == 0` waits indefinitely**.

A non-blocking program typically uses `select()` or `select(timeout)` in an **event loop**. `selectNow()` is appropriate when the program has other work to do and just wants to poll I/O right now.

## 2. Preparing Selector, Channel, and SelectionKey

Basic syntax:

~~~java
// Illustrative snippet, not a complete program.
try (Selector selector = Selector.open();
     ServerSocketChannel server = ServerSocketChannel.open()) {
    server.configureBlocking(false);
    server.bind(new InetSocketAddress("127.0.0.1", 8080));

    SelectionKey key = server.register(
            selector, SelectionKey.OP_ACCEPT);
    // Run selection loop and handle events...
}
~~~

Appropriate imports from `java.net` and `java.nio.channels` are required. Only channels that support selection and are placed in **non-blocking mode** can be registered:

~~~java
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

Attempting to register a channel still in blocking mode can throw `IllegalBlockingModeException`. If the interest operation is not in `channel.validOps()`, `register` can throw `IllegalArgumentException`. An ordinary `FileChannel` is **not** a `SelectableChannel`; you cannot register a `FileChannel` with a `Selector` like a socket.

### The Trio of Key Sets

Each selector maintains related key sets:

- **Key set — `selector.keys()`:** `SelectionKey` instances currently registered with the selector and not yet fully canceled/removed.
- **Selected-key set — `selector.selectedKeys()`:** keys selected and not yet removed from the selected set by the application.
- **Cancelled-key set:** a set managed internally by the selector; `key.cancel()` schedules cancellation, and the key is removed during the next selection or cancellation processing.

A `SelectionKey` links **one channel + one selector**, with properties:

| Member | Meaning |
|---|---|
| `channel()` | The registered channel |
| `selector()` | The selector owning the key |
| `interestOps()` | Operations the application **wants to be notified about**, e.g., `OP_READ \| OP_WRITE` |
| `readyOps()` | Operations recorded as **ready** after selection |
| `isReadable()/isWritable()/isAcceptable()/isConnectable()` | Check bits in `readyOps` |
| `attachment()/attach(obj)` | Attaches connection state or an application handler object |
| `isValid()/cancel()` | Checks/cancels registration |

Do not confuse `interestOps` (what you want to watch) with `readyOps` (what has been observed ready). In many situations the application only needs to care about `OP_READ` and should not keep `OP_WRITE` enabled all the time.

## 3. `select()`: Waiting for Events

Signature:

~~~java
int readyCount = selector.select();
~~~

`select()` performs a **blocking** selection pass. Per the specification, the call can return when:

- At least one channel is selected because an operation in its interest set is ready.
- Another thread calls `selector.wakeup()`.
- The selecting thread is interrupted via `interrupt()`.
- The selector is closed while waiting (an error/lifecycle case to handle).

It has **no timeout parameter**. If nothing becomes ready and no wakeup occurs, the thread can wait indefinitely. Unlike `Thread.sleep()`, a selector waits for I/O conditions and manages key registrations.

A typical TCP listener processing loop looks like:

~~~java
// Illustrative event loop snippet: selector and server are open/registered.
while (running) {
    int updated = selector.select();
    if (updated == 0) {
        continue; // May be due to wakeup/interrupt; do not assume I/O occurred.
    }

    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Remove from selected-key set so it can be selected again next time.
        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            // server.accept(), configure non-blocking socket and register.
        } else if (key.isReadable()) {
            // channel.read(buffer), handle 0 / -1 / partial read.
        }
    }
}
~~~

The snippet above **cannot run standalone** because `running`, the channels, and handler branches are undeclared. Section 7 provides a complete Java 17+ example.

**Do not rely mechanically on the return count to decide processing.** `select()` returns the number of keys whose **ready-operation set was updated** during that selection; it does not necessarily equal the number of keys currently present in `selectedKeys()`. When processing selected keys, iterate the selected-key set according to its lifecycle.

## 4. `selectNow()`: Immediate Check Without Waiting

Signature:

~~~java
int updated = selector.selectNow();
~~~

- Performs **non-blocking** selection: does not wait for a channel to become ready.
- May return `0` if no new ready operations were recorded.
- May return a positive number if keys' ready-operation sets were updated.
- Still updates the selected-key set per standard selection rules.
- **Clears the effect of any prior pending `wakeup()` calls**.

Example:

~~~java
// Illustrative: selector already has at least one registered key.
doOtherWork();
int updated = selector.selectNow();
if (updated > 0) {
    processSelectedKeys(selector);
}
~~~

`doOtherWork()` and `processSelectedKeys(...)` are application-defined methods. If a thread calls `selectNow()` continuously in a non-waiting loop with no other work, it turns into **busy polling**, burning CPU.

### Practical Scenarios Where It Fits

- Integrating I/O checks into an existing scheduler loop, game loop, or compute loop.
- Checking whether any event is ready *right now* without pausing main work.
- Performing a non-blocking selection to synchronize key state after a specific change — keeping in mind it **consumes any pending wakeup effect**.

`selectNow()` **does not mean fetching bytes immediately** and **does not automatically make channels non-blocking**. Reading/writing must still be performed by the application with proper result checking.

## 5. `select(timeout)`: Bounded Wait, With the `timeout=0` Trap

Signature:

~~~java
int readyCount = selector.select(500); // positive timeout: wait up to roughly 500 ms.
~~~

The parameter of this overload is a **`long` in milliseconds**, not seconds or nanoseconds.

| Call | Wait Mode | Remarks |
|---|---|---|
| `selector.select()` | Default indefinite wait | Returns on readiness, wakeup, interrupt, or corresponding error/lifecycle |
| `selector.selectNow()` | Non-blocking | Returns after current poll pass |
| `selector.select(1)` | Wait up to roughly 1 ms as requested | Does not guarantee 1 ms precision |
| `selector.select(500)` | Wait up to roughly 500 ms | May return before timeout |
| `selector.select(0)` | **Indefinite wait** | **Not equivalent to `selectNow()`** |
| `selector.select(-1)` | Invalid | Throws `IllegalArgumentException` |

More precisely, Java **does not promise hard real-time deadlines**: scheduling, OS, and timer resolution can make actual return time earlier or later than wall-clock expectation. `timeout > 0` is an API-level wait bound, not a strict timing SLA.

### Example Using Timeout for Periodic Tasks

An application needs to process I/O while running a timer check at least roughly once per interval:

~~~java
// Illustrative: selector is configured; not a standalone program.
while (running) {
    selector.select(250);
    handleSelectedKeys(selector);
    runScheduledTasksIfDue();
}
~~~

This timeout prevents **indefinite I/O waiting** from starving timer checks. However:

- It does not guarantee `runScheduledTasksIfDue()` runs *exactly* every 250 ms.
- If `handleSelectedKeys(...)` takes a long time, the timer can still be delayed.
- If a tighter deadline is needed, compute **the remaining time until the nearest deadline** instead of always passing a fixed timeout.
- If another thread pushes an urgent task into a queue, call `selector.wakeup()` so it does not wait out the timeout.

### Never Poll by Passing 0

A dangerous mistake:

~~~java
// Wrong if expecting an immediate check:
selector.select(0); // 0 = wait indefinitely, NOT poll.
~~~

Use `selectNow()` to **poll without waiting**. When a real deadline is needed, use a positive timeout and track deadlines with `System.nanoTime()` (appropriate for measuring intervals without depending on wall-clock adjustments).

## 6. Comparing the Three Methods in the Same Scenario

Suppose a `Pipe.SourceChannel` or `SocketChannel` is registered for `OP_READ`, but currently has zero bytes available to read:

~~~text
No data available:
  select()       -> waits until an event, wakeup, or interrupt occurs
  selectNow()    -> polls and returns immediately, usually returning 0
  select(100)    -> waits until an event occurs or roughly 100 ms elapses
  select(0)      -> waits indefinitely

When new data arrives:
  all three methods can record OP_READ
  selectedKeys() contains the corresponding key for the application to handle
  the application still must call read(...) and inspect the result
~~~

| Criterion | `select()` | `selectNow()` | `select(timeout > 0)` |
|---|---|---|---|
| Can block | Yes | No | Yes, until event/wakeup/interrupt/timeout |
| Time parameter | No | No | Yes: milliseconds |
| Can return `0` | Yes | Yes | Yes |
| Updates `selectedKeys()` | Yes | Yes | Yes |
| Woken by `wakeup()` | Yes | Doesn't wait; also clears pending wakeup | Yes |
| Best suited for | Event loop mainly waiting on I/O | Polling interleaved with other work | Event loop with deadlines or timers |
| Risk if misused | Periodic tasks starve without wakeup | CPU-burning spin/busy polling | Confusing `0` with non-blocking; expecting exact timer precision |

Common rule: **the return value is not a byte count** and not "how many sockets finished reading." It relates to how many keys had their ready set updated in that selection pass.

## 7. Complete Java 17+ Program: Testing All Three Forms

The example uses `java.nio.channels.Pipe`, so **no network port is needed** and it does not depend on Internet connectivity. `Pipe.SourceChannel` is a `SelectableChannel` supporting `OP_READ`; `Pipe.SinkChannel` writes data into the other end.

The program proceeds in order:

1. Register the non-blocking source to monitor `OP_READ`.
2. Call `selectNow()` while the pipe has no data.
3. Call `select(40)` while still empty — finishes via timeout.
4. Write two ASCII bytes `OK` into the sink; then call `select()` and receive the key with `OP_READ`.
5. Iterate `selectedKeys()`, remove the selected key, and read the data.
6. Call `wakeup()` before another `select()` to demonstrate waking up without waiting for data.

Save with exact filename **`SelectorSelectModesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class SelectorSelectModesDemo {

    private static void writeAll(Pipe.SinkChannel sink, ByteBuffer src)
            throws IOException {
        while (src.hasRemaining()) {
            sink.write(src); // Sink defaults to blocking mode.
        }
    }

    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Selector selector = Selector.open();
             Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            System.out.println("selectNow(empty)="
                    + selector.selectNow());

            System.out.println("select(40,empty)="
                    + selector.select(40));

            writeAll(sink, ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.US_ASCII)));

            System.out.println("select(ready)="
                    + selector.select());

            Iterator<SelectionKey> iterator =
                    selector.selectedKeys().iterator();

            while (iterator.hasNext()) {
                SelectionKey key = iterator.next();
                iterator.remove(); // Very important.

                if (!key.isValid() || !key.isReadable()) {
                    continue;
                }

                Pipe.SourceChannel readable =
                        (Pipe.SourceChannel) key.channel();
                ByteBuffer data = ByteBuffer.allocate(16);
                int count = readable.read(data);

                data.flip();
                byte[] bytes = new byte[data.remaining()];
                data.get(bytes);

                System.out.println("read(" + count + ")="
                        + new String(bytes, StandardCharsets.US_ASCII));
            }

            selector.wakeup();
            System.out.println("select(wakeup)=" + selector.select());
        }
    }
}
~~~

Compile/run:

~~~bash
javac SelectorSelectModesDemo.java
java SelectorSelectModesDemo
~~~

**Stdout under normal conditions, with no thread interrupts or external I/O interference:**

~~~text
selectNow(empty)=0
select(40,empty)=0
select(ready)=1
read(2)=OK
select(wakeup)=0
~~~

Line-by-line explanation:

- `selectNow(empty)=0` because there are no bytes yet and the call does not wait.
- `select(40,empty)=0` because no readiness occurs before the ~40 ms timeout (no exact millisecond measurement is asserted).
- After `writeAll`, the pipe holds two bytes; the source is considered read-ready so `select()` records one key.
- `selectedKeys()` is iterated and `iterator.remove()` deletes the key from the selected set. `read(...)` retrieves two bytes and the program displays `OK`.
- After all bytes are read, `selector.wakeup()` makes the next `select()` return immediately, and in this example no new keys are ready, so it returns 0.

The example **does not use `Thread.sleep()` to fake I/O**; the timeout is demonstrated by a selection pass with no data, and readiness is triggered by writing to the pipe. In an environment with I/O faults, premature channel closure, or external thread interruption, output may differ from the sample stdout — real applications must handle those cases.

### Why Must Source Be Non-Blocking?

Channels passed to `register(selector, ...)` must allow selection. `source.configureBlocking(false)` is mandatory. The `sink.write(...)` call in the example is not registered with the selector and can operate in blocking mode. Those are two separate channel objects, so there is no conflict.

## 8. `selectedKeys()` Does Not Clear Automatically After Each Select

A common bug source is that **the selected set persists across selection calls**.

How `select()` / `selectNow()` / `select(timeout)` work:

1. Check pending cancellations and remove keys that are no longer valid as needed.
2. Query the system for channel operations that are ready.
3. If a key is not yet in the selected-key set, add it and set its ready-operation set.
4. If a key **is already** in the selected-key set, new readiness bits may be **combined** (ORed) into its existing ready-operation set.
5. The selected-key set is not automatically cleared on every select. **The application is responsible for removing handled keys from the set**.

Standard pattern:

~~~java
// Illustrative snippet inside an event loop.
int updated = selector.select();
Iterator<SelectionKey> iter = selector.selectedKeys().iterator();

while (iter.hasNext()) {
    SelectionKey key = iter.next();
    iter.remove(); // Do not leave old keys sitting in selectedKeys().

    if (!key.isValid()) {
        continue;
    }
    if (key.isReadable()) {
        // Read according to non-blocking I/O and protocol rules.
    }
}
~~~

You can call `selector.selectedKeys().clear()` after copying keys out, though `iterator.remove()` during iteration is generally clearer and less error-prone. **Never call `selector.keys().clear()`** intending merely to clear recently selected keys; `keys()` is the registered set, not the selected-key set to consume.

### Why Can `selectedKeys().size()` Differ from the Return Value?

A key left in the selected-key set from a previous round might have no readiness updates in the current round, yet remain in the set because the application did not remove it. Thus:

- `select()` can return `0` while `selectedKeys()` is **not empty**.
- Do not treat `selectedKeys().size()` as "the number of new events in this round."
- Do not rely on the return value independently of managing the key set and channel state.

If old keys linger in the selected set too long, `isReadable()` can trigger logic on already-drained data or stale readiness that no longer matches expectations. This easily causes busy loops and hard-to-debug bugs when multiple operations are ORed into `readyOps()`.

## 9. `wakeup()`, Interrupt, and Close

### `selector.wakeup()`

When a thread is waiting inside `select()` or `select(timeout)`, another thread can tell it to return:

~~~java
// Thread managing task/interest updates:
taskQueue.add(task);
selector.wakeup();
~~~

Upon waking up, the event loop must inspect the task queue, safely update registrations/interests, and continue running.

**Often-overlooked rules:**

- If a selection is currently blocked, `wakeup()` causes it to return promptly.
- If no selection is currently waiting, the wakeup effect is retained for **the next selection operation**; that call can return immediately.
- **`selectNow()` consumes/clears a pending wakeup**.
- Calling `wakeup()` multiple times before a new selection **does not accumulate multiple wakeup tokens**.
- A woken select **can still return a positive number** if a key is ready, so waking up does not mean the return value is guaranteed to be 0.

Diagram:

~~~text
Thread A (event loop)                     Thread B (worker)
----------------------                    -----------------
selector.select()  [waiting]
                                          queue.add(task)
                                          selector.wakeup()
select() returns
drain task queue
process selected keys
continue event loop
~~~

### `Thread.interrupt()`

Interrupting the thread blocked in selection also causes the selection call to return; interrupting the thread sets its interrupt status and still requires proper shutdown rules.

**Never handle `select() == 0` by spinning infinitely.** Check the `running` flag, interrupt status, work queue, and whether the selector is closing.

### `close()` and Key Cancellation

`selector.close()` releases selector resources; subsequent operations on a closed selector can throw `ClosedSelectorException`. `SelectionKey.cancel()` marks a registration for cancellation; removal from the selector completes during the next selection pass. When closing a socket, cancel/release resources and clean up per-connection state.

Do not iterate or mutate `selectedKeys()` concurrently from multiple threads without synchronization. The selected-key set is **not thread-safe**; an event loop should have a clear owning thread, with other threads submitting requests via a queue and calling `wakeup()`.

## 10. Common Mistakes with `OP_WRITE` and Busy Loops

A `SocketChannel` is normally writable immediately under normal conditions because the OS socket send buffer has available space. If you always register:

~~~java
// Illustrative case you normally should NOT do:
socket.register(selector, SelectionKey.OP_WRITE);
~~~

the selector may return very frequently even when the application **has zero outbound data**. The event loop then keeps waking up with nothing to do, causing high CPU usage.

**Common policy for real applications:**

1. When the outbound queue is empty, **do not** keep `OP_WRITE` in the interest set.
2. When data needs to be sent, attempt an immediate write (if the design permits).
3. If the write transfers only partially, preserve `ByteBuffer.position()` and enable `OP_WRITE` to wait until the socket is writable again.
4. Once the queue is completely written, turn off `OP_WRITE` to prevent continuous readiness notifications.

Example:

~~~java
// Illustrative code, key is a valid SelectionKey.
int ops = key.interestOps();
if (hasPendingOutput) {
    key.interestOps(ops | SelectionKey.OP_WRITE);
} else {
    key.interestOps(ops & ~SelectionKey.OP_WRITE);
}
~~~

`hasPendingOutput` is an application-defined variable. Do not update `interestOps()` after a key has been canceled; `CancelledKeyException` can occur. If another thread updates interest while the selector is waiting, coordinate with the event loop and call `wakeup()` so the change takes effect promptly.

## 11. Non-Blocking Read/Write: Ready Does Not Mean Enough Data

With a non-blocking `SocketChannel`:

~~~java
// Illustrative code: socket is registered for OP_READ and buffer is prepared.
int n = socket.read(buffer);
if (n > 0) {
    // Got n new bytes. The frame might still be incomplete.
} else if (n == 0) {
    // No bytes received this round; do not spin continuously.
} else { // n == -1
    // End-of-stream: remote peer closed the send side of the byte stream.
    key.cancel();
    socket.close();
}
~~~

With `OP_ACCEPT`, `server.accept()` on a non-blocking `ServerSocketChannel` **can return `null`**; handle this and never operate on a `null` channel.

With `OP_CONNECT`, when the key is connectable you must call `socket.finishConnect()` per contract, then update interest to `OP_READ` or `OP_WRITE`. Never assume a socket finished connecting solely because `key.isConnectable()` returned true.

In applications transmitting length-prefixed frames, the parser must accumulate complete header/body bytes across **multiple selection rounds**. `select()` only reports readiness; it never says "one complete frame has arrived."

## 12. Selector Timeout vs. Business Timeout

`select(500)` is the wait timeout for **one selection pass**. It does not automatically provide the following timeouts:

- **Connect timeout:** time limit to complete the TCP connect.
- **Frame read timeout:** time limit to receive both header and payload.
- **Idle timeout:** close the connection if no activity occurs within an interval.
- **Request deadline:** expire an entire request including parse/compute/write.
- **Shutdown deadline:** finish the event loop cleanly.

Each requires storing a **deadline** and checking against a monotonic clock like `System.nanoTime()`, while setting the selector wait interval to the time remaining until the nearest deadline.

Calculation example *within a context that already has a deadline*:

~~~java
long now = System.nanoTime();
long remainingNanos = deadlineNanos - now;

if (remainingNanos <= 0) {
    expireRequests();
} else {
    long timeoutMs =
            Math.max(1, java.util.concurrent.TimeUnit.NANOSECONDS
                    .toMillis(remainingNanos));
    selector.select(timeoutMs);
}
~~~

This is illustrative code; `deadlineNanos` and `expireRequests()` are supplied by the application.

**Why `Math.max(1, ...)`?** If positive but under 1 millisecond, converting to milliseconds truncates to `0`, and `select(0)` **will wait indefinitely** instead of waiting very briefly. Clamping to at least 1 ms avoids that trap, though it may slightly overshoot the deadline. If very high precision is required, design an appropriate scheduler/clock rather than treating `select(timeout)` as a hard real-time timer.

### Avoiding Missed Tasks on Early Wakeup

When another thread adds a task to the queue and calls `wakeup()`, the event loop must **process the queue after select**. Never infer `select() == 0` was only due to a timer; the cause could be a wakeup or interrupt.

## 13. Errors, Exceptions, and Edge Cases

| Scenario | Expected Error / Behavior |
|---|---|
| `select(-5)` | `IllegalArgumentException` |
| `select(0)` | Waits indefinitely, **not** polling |
| `selectNow()` | Non-blocking, may return `0`; consumes pending wakeup |
| `select()` after `wakeup()` | Returns immediately; result can be 0 or positive |
| `selector.close()` then select | `ClosedSelectorException` |
| I/O error during selection | `IOException` |
| `key.interestOps()` on an invalid key | `CancelledKeyException` |
| Registering a channel in blocking mode | `IllegalBlockingModeException` |
| Registering invalid operations for the channel | `IllegalArgumentException` |
| Iterating and directly adding to `selectedKeys()` | Direct key insertion is disallowed; may throw `UnsupportedOperationException` |
| Modifying/iterating `selectedKeys` from multiple threads without sync | Races and corrupt results; selected-key set is not thread-safe |
| Not removing processed keys | Ready bits/selected set retain stale state across selects |
| Non-blocking `read()` returns 0 | No progress this round; wait for appropriate readiness |
| Non-blocking `read()` returns -1 | End-of-stream, handle close or half-close per protocol |

**Never solve errors by calling `selectNow()` in an infinite loop.** A solid event loop properly handles lifecycle, backpressure, task queues, and partial I/O.

## 14. A Relatively Safe Event-Loop Pattern

The code below is an **illustrative skeleton**, not a complete server. `processTasks()`, `acceptConnections()`, `readFromConnection()`, and `flushPendingOutput()` must be defined by the application, along with error/socket-close/key-registration handling.

~~~java
while (running) {
    // Pick a positive timeout based on the nearest deadline, or use select().
    selector.select(250);

    processTasks(); // Handle requests submitted to the queue from other threads.

    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }

        try {
            if (key.isAcceptable()) {
                acceptConnections(key);
            }
            if (key.isConnectable()) {
                finishConnecting(key);
            }
            if (key.isReadable()) {
                readFromConnection(key);
            }
            if (key.isWritable()) {
                flushPendingOutput(key);
            }
        } catch (IOException e) {
            closeConnection(key);
        }
    }

    expireDeadlines();
}
~~~

Characteristics of this skeleton:

- Iterates selected keys and removes each key once.
- Checks validity before using operations.
- Does not assume only one readiness bit: the same key can have both READ and WRITE.
- Does not use `else if` everywhere when multiple readiness states need handling in the same pass; however, if one branch cancels the key, subsequent branches may need another validity check.
- Uses `selector.wakeup()` when external tasks need prompt handling by the event loop.
- Establishes clear channel closing, cancellation, timeout, and backpressure mechanisms.

For small single-threaded applications with no timers, `select()` can be the simplest choice. For servers with business timeouts, `select(timeout)` is usually a better fit. `selectNow()` should only be used when non-blocking polling is truly required.

## 15. Misconceptions Table and Fixes

| Misconception | Correct Understanding |
|---|---|
| "`select(0)` is like `selectNow()`" | `select(0)` **waits indefinitely**; `selectNow()` does not wait. |
| "`select(100)` always waits exactly 100 ms" | Can return early on readiness/wakeup/interrupt; not a hard real-time timer. |
| "The return value is the number of bytes read" | It is the number of keys whose ready-operation set was updated, not bytes. |
| "`select() == 0` definitely means no work" | Could be wakeup/interrupt, queued tasks, or unconsumed old keys. |
| "`selectedKeys()` auto-clears on the next `select()` call" | No; the application must remove handled selected keys. |
| "`isReadable()` means an entire message is ready" | Only readiness; you must read/parse actual bytes and handle partials. |
| "`FileChannel` can register with `Selector`" | `FileChannel` is not a `SelectableChannel`. |
| "Just call `register`, no need for non-blocking" | Channel must call `configureBlocking(false)` before registering. |
| "`selectNow()` always saves CPU because it doesn't wait" | Tight polling creates busy-spin. |
| "Always enable `OP_WRITE` on all sockets" | Often makes the selector wake continuously; enable only with pending writes. |
| "`wakeup()` always makes select return 0" | If readiness exists, select can still return a positive number. |
| "`wakeup()` is an accumulating token queue" | Multiple wakeups before one selection usually equal just one. |
| "The selector timeout is the request timeout" | Separate deadlines are needed for requests/protocols, not just I/O waits. |

## 16. Self-Check

1. `OP_READ` is registered but no bytes exist yet; which API returns immediately? **`selectNow()`**.
2. Calling `select(0)` waits up to how long? **Indefinitely with respect to timeout**, until readiness, wakeup, interrupt, or another lifecycle condition occurs.
3. Calling `select(200)` and data arrives after 30 ms. Must it wait the full 200 ms? **No.** It can return as soon as readiness occurs.
4. `select(200)` returns 0. Is it certain the reader has no data left to process? **Never infer that**; check selected keys, task queues, and current state.
5. Why must `iterator.remove()` be called in the selected-key processing loop? **To avoid keeping old keys in the selected set for subsequent selection rounds**.
6. A socket is always marked writable even with zero bytes to send; what should change? **Disable `OP_WRITE` interest when the outbound queue is empty**.
7. Need to wake a thread blocked in `select()` when a worker thread adds a task. What do you call? **`selector.wakeup()`**.
8. What effect does `selectNow()` have on a prior `wakeup()`? **It clears the pending wakeup effect**.
9. After `select()` and `key.isReadable()==true`, is `read()` guaranteed to return a whole frame? **No**.
10. Is `select(-1)` valid? **No, `IllegalArgumentException`**.
11. Can `FileChannel` be used with `Selector`? **No**, it is not a `SelectableChannel`.
12. A deadline has 500 microseconds remaining; is passing `select(TimeUnit.NANOSECONDS.toMillis(500_000))` correct? **No**, that becomes `select(0)` and waits indefinitely. Sub-millisecond remaining times must be handled carefully.

## 17. Official References

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select()`, `selectNow()`, `select(long)`, `selectedKeys()`, `wakeup()`, ready-operation set update rules, and timeout caveats.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, `isReadable`, `isWritable`, key cancellation.
- [Java SE 17 — SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking(false)`, `register`, `validOps`.
- [Java SE 17 — Pipe](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Pipe.html): source/sink channels used in runnable examples without a network server.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): partial read/write, non-blocking mode, `finishConnect()`.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): registering `OP_ACCEPT`, `accept()` on a non-blocking server.
