# Interruption, Closing from Another Thread, and I/O-Type-Dependent Behavior in Java

A Java thread may be blocked inside `read()`, `write()`, `accept()`, or `select()` when another thread requests the program to stop. At that moment, several mechanisms are easily confused:

- **`Thread.interrupt()`** sets the thread's interrupt flag and can wake up certain blocking operations per the API contract.
- **`close()` from another thread** closes the resource, which can cause a waiting I/O operation to finish or throw an exception.
- **Timeout** limits waiting time for operations that support it, usually without closing the resource.
- **EOF or half-close** describes ending a data stream, unlike interrupting a thread.
- **Cancellation** on `Future`/`ExecutorService` is a request to stop a task; its effect depends on the task type and I/O API.

**There is no universal rule that calling `interrupt()` immediately cancels every `InputStream.read()`.** Java NIO defines explicit contracts for `InterruptibleChannel`, whereas various `java.io` streams, sockets, consoles, files, and selector operations behave differently. This lesson focuses on Java 17+, particularly traditional platform threads; implementation variants and virtual threads in newer JDKs require checking the exact version's documentation.

## 1. Three Questions to Clarify Before Canceling I/O

Before writing cancellation logic, determine:

1. **Which specific API is the thread blocking in?** For instance, `Socket.getInputStream().read()`, `SocketChannel.read()`, `Files.newInputStream(path).read()`, `ServerSocket.accept()`, or `Selector.select()`.
2. **Who can safely close the resource?** Does the worker thread own the resource, or is it shared? Closing a shared resource can break other tasks.
3. **What is a valid outcome?** Stopping via exception, returning EOF `-1`, returning bytes read, returning `0`, or waking up and continuing the loop all carry different meanings.

A reliable cancellation design should specify the **cancellation signal**, **how blocking calls are unblocked**, **how resources are cleaned up**, and **how the termination reason is reported**.

## 2. What Does Thread.interrupt() Actually Do?

`Thread.interrupt()` does not force a thread to die and does not arbitrarily "inject exceptions" into running code. It sets the **interrupted status**; for waiting operations whose contracts support interruption, the wait stops. For example, `Thread.sleep(...)`, `Object.wait(...)`, and `Thread.join(...)` can throw `InterruptedException`, **clearing the interrupted status** when throwing that exception.

~~~java
// Illustrative snippet: worker is a created, running Thread.
worker.interrupt();
~~~

After calling it, whether the other thread stops depends on what it is currently doing. For CPU-bound loops, the application typically must **check the interrupt flag itself**:

~~~java
// Illustrative snippet: loop condition and work are defined elsewhere.
while (!Thread.currentThread().isInterrupted()) {
    // Perform a bounded unit of work.
}
~~~

`Thread.currentThread().isInterrupted()` only **checks** the flag without clearing it. By contrast, `Thread.interrupted()` is a static method that checks **and clears** the current thread's interrupt flag. Therefore, avoid calling `Thread.interrupted()` casually where you do not want to consume the cancellation signal.

If you must catch `InterruptedException` without propagating it per the method's contract, the standard idiom is restoring the flag and ending work:

~~~java
try {
    worker.join();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Cancel or return control to the appropriate calling layer.
}
~~~

This is an **illustrative snippet**. Never swallow `InterruptedException` and keep waiting indefinitely without actively handling cancellation.

**Core distinction:** `interrupt()` may cancel a blocking operation on a **channel** under NIO contracts, yet that **does not prove** every `InputStream` implementation behaves the same way.

## 3. java.nio.channels.InterruptibleChannel: Explicit Contract

`InterruptibleChannel` in Java NIO represents a channel that can both **be closed from another thread** and **be interrupted during blocking I/O operations**. Classes such as `SocketChannel`, `ServerSocketChannel`, `FileChannel`, `Pipe.SourceChannel`, and `Pipe.SinkChannel` implement this interface.

The specification distinguishes two scenarios clearly:

| Event Affecting a Blocking I/O Operation on InterruptibleChannel | Contract Behavior |
|---|---|
| **Another thread calls `channel.close()`** while blocking | The blocked thread receives `AsynchronousCloseException` |
| **Another thread calls `blockedThread.interrupt()`** while blocking | The channel is closed; the thread receives `ClosedByInterruptException`; the interrupted flag is set |
| Thread already has its interrupted flag set before starting blocking I/O on the channel | The channel is closed, immediately throwing `ClosedByInterruptException`; the flag remains set |

`ClosedByInterruptException` **extends** `AsynchronousCloseException`, which extends `ClosedChannelException`, and all three belong to the `IOException` family. When distinguishing causes, catch the **more specific exception first**:

~~~java
try {
    // A blocking read call on an open InterruptibleChannel.
} catch (ClosedByInterruptException ex) {
    // Interrupted: channel closed, interrupt flag set.
} catch (AsynchronousCloseException ex) {
    // Closed from another thread while blocked.
} catch (IOException ex) {
    // Remaining I/O errors.
}
~~~

This is an **illustrative snippet**, not a standalone program. Catching `AsynchronousCloseException` before `ClosedByInterruptException` makes the interrupt branch unreachable.

Notes:

- `ClosedByInterruptException` from a channel is not `InterruptedException`. Never guess interrupt-flag state mechanically from the exception name; under `InterruptibleChannel`'s contract, the interrupt flag **remains set**.
- If the channel was already closed **before** the thread called `read()`, you typically receive `ClosedChannelException` instead of `AsynchronousCloseException`. This is not a program logic bug; two threads are racing in execution timing.
- Interrupting a blocking channel **closes the entire channel**, rather than just aborting one `read` call so it can be reused immediately.
- For channels in **non-blocking** mode, `read()`/`write()` can return `0` when not ready, so waiting/canceling must inspect loop logic or `Selector`; do not blindly expect blocking exceptions.

## 4. Java 17+ Example: Interrupting a Pipe.SourceChannel Blocked on Read

Use NIO's `Pipe` to create a readable source with no data yet. We keep the sink open without writing any bytes; thus `read` will not hit EOF from closing the write side. The main thread interrupts the worker, causing the read channel to close per the `InterruptibleChannel` contract.

Create **`InterruptChannelDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.Pipe;
import java.util.concurrent.CountDownLatch;

public class InterruptChannelDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            CountDownLatch ready = new CountDownLatch(1);

            Thread worker = new Thread(() -> {
                ready.countDown();

                try {
                    source.read(ByteBuffer.allocate(1));
                    System.out.println("read completed");
                } catch (ClosedByInterruptException ex) {
                    System.out.println("ClosedByInterruptException");
                    System.out.println("interrupted="
                            + Thread.currentThread().isInterrupted());
                } catch (IOException ex) {
                    System.out.println("Unexpected I/O: "
                            + ex.getClass().getSimpleName());
                }
            });

            worker.start();
            ready.await();
            worker.interrupt();
            worker.join();

            System.out.println("channelOpen=" + source.isOpen());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 InterruptChannelDemo.java
java InterruptChannelDemo
~~~

Stdout per NIO contract:

~~~text
ClosedByInterruptException
interrupted=true
channelOpen=false
~~~

**Why is the result deterministic?** `CountDownLatch` ensures the worker has started its task before main requests interruption. Even if main calls `interrupt()` right before the worker enters `source.read()`, the interrupted flag is already set, so starting the blocking read closes the channel and throws the same `ClosedByInterruptException`. If the worker is already blocking, interrupting terminates the operation with the same exception.

- `source.read(ByteBuffer.allocate(1))` must wait because the pipe has no bytes yet and `sink` stays open.
- `interrupt()` does not merely throw an exception; it also makes `source.isOpen()` become `false`.
- `worker.join()` lets main wait for the worker to finish before inspecting channel state.
- `try-with-resources` releases both ends of the pipe. Do not use `Thread.sleep(...)` to guess when the worker entered read; a latch avoids scheduler-timing dependencies in the demo logic.

In real programs, protect `await()` and `join()` against interruption of the waiting thread itself: if `InterruptedException` is caught, usually restore the interrupt status and perform cleanup per application policy.

## 5. Closing a Channel from Another Thread and Race Conditions

When thread A calls `source.close()` while thread B is waiting on `source.read()`, `InterruptibleChannel` specifies that B receives `AsynchronousCloseException`. However, if A closes **before** B starts `read()`, B can receive `ClosedChannelException`. Therefore, real code should not insist on one exact exception class name across every thread interleaving.

Standalone example **`CloseChannelDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.Pipe;
import java.util.concurrent.CountDownLatch;

public class CloseChannelDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            CountDownLatch ready = new CountDownLatch(1);

            Thread worker = new Thread(() -> {
                ready.countDown();

                try {
                    source.read(ByteBuffer.allocate(1));
                    System.out.println("Read completed");
                } catch (ClosedChannelException ex) {
                    System.out.println("Stopped by channel close");
                } catch (IOException ex) {
                    System.out.println("Unexpected I/O");
                }
            });

            worker.start();
            ready.await();
            source.close();
            worker.join();

            System.out.println("channelOpen=" + source.isOpen());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CloseChannelDemo.java
java CloseChannelDemo
~~~

Stdout under both valid orderings of close/read:

~~~text
Stopped by channel close
channelOpen=false
~~~

`ClosedChannelException` is the superclass of `AsynchronousCloseException`; hence the demo catches both **closing before read and closing during blocking read** together, avoiding scheduler sensitivity. `sink` stays open until the end of the `try` block so it does not trigger an unintended EOF.

Calling `close()` multiple times on a `Channel` normally has no additional effect once already closed. Even so, resource-closing authority must be clearly assigned: when multiple tasks share a channel, one task canceling via `close` affects all of them.

## 6. java.net.Socket: close, Read Timeout, and Interrupt Are Not the Same

`java.net.Socket` has its own contract; do not extrapolate from `FileInputStream` or an arbitrary `InputStream` subclass.

### 6.1. Closing a Socket from Another Thread

In Java 17, `Socket.close()` is specified to cause any thread currently blocked in an I/O operation on that socket to throw `SocketException`. Closing the socket also closes its associated input and output streams, and the socket cannot be reconnected.

~~~java
// Illustrative snippet: socket is a java.net.Socket used by another thread.
socket.close(); // Can wake up a blocked read on the socket.
~~~

This is a useful cancellation strategy when the task **owns the socket**. If the socket belongs to a shared connection, closing decisions belong to the connection manager; never let one task arbitrarily abort another task's work.

### 6.2. SO_TIMEOUT Only Limits Each Read Wait

With `Socket.setSoTimeout(milliseconds)` set to a positive value, a single `read()` on the socket's input stream waits at most that duration per socket rules. When time expires, the call throws `SocketTimeoutException`, yet **the socket remains valid** and can continue being used.

~~~java
// Illustrative snippet: socket is a valid connected Socket.
socket.setSoTimeout(2_000);

try {
    int value = socket.getInputStream().read();
    // value is in 0..255 or -1 at EOF.
} catch (java.net.SocketTimeoutException ex) {
    // Read wait timed out; the socket is not automatically closed.
}
~~~

Set the timeout before the blocking operation. An `SO_TIMEOUT` value of `0` means **infinite read timeout** under this option. `SocketTimeoutException` is a subclass of `InterruptedIOException`, yet **you must not equate a timeout with the thread being `interrupt()`ed**.

A single read timeout does not establish a **deadline for the entire request**, because the application may perform multiple reads, each getting a fresh wait window. To cap total elapsed time, track an overall deadline or use a deadline-aware abstraction at the proper layer.

### 6.3. Sockets Backed by SocketChannel Follow NIO Rules

A `Socket` obtained from a `SocketChannel` (such as via `SocketChannel.socket()`) has an associated channel. When its streams delegate to the channel, blocking interruption also follows channel behavior: interrupting the reading thread can close the underlying channel and throw `ClosedByInterruptException`.

Conversely, never claim **every traditional socket stream across every Java version cancels immediately on `Thread.interrupt()`**. On Java 17 with platform threads and non-channel sockets, rely on documented mechanisms such as `Socket.close()`, `SO_TIMEOUT`, connection management, and testing on your target environment. JDKs with virtual threads starting in Java 21 add different interruption behaviors depending on socket/implementation type; consult that JDK's documentation.

### 6.4. Half-Close and EOF

`Socket.shutdownInput()` puts the input side at end-of-stream so subsequent reads return `-1` per contract. `Socket.shutdownOutput()` closes the output side, signaling end-of-transmission at the TCP protocol level while receiving can still continue. These are **half-close** operations, distinct from closing the whole socket via `close()`.

A `read()` returning `-1` means **end of input data**, not necessarily that the thread was interrupted. A network peer cleanly closing its send side also causes the receiver to see EOF. Separate normal protocol termination from errors and cancellation.

## 7. ServerSocket.accept() and Shutting Down a Server

`ServerSocket.accept()` blocks waiting for an incoming connection. On Java 17 `ServerSocket`, another thread calling `serverSocket.close()` causes the thread blocked in `accept()` to throw `SocketException`. This is the standard way to exit an accept loop during shutdown.

~~~java
// Illustrative snippet, not a standalone program.
try {
    while (!stopping) {
        Socket client = serverSocket.accept();
        // Hand client to a processing component, with clear ownership.
    }
} catch (java.net.SocketException ex) {
    if (!stopping) {
        throw ex; // Unexpected error; do not hide.
    }
}
~~~

`stopping` is a properly shared stop state, typically using `volatile` or an appropriate synchronization primitive. On shutdown: update the stopping state, then close `serverSocket`. However, a plain boolean flag **does not wake up** a blocked `accept()`; `close()`, a timeout, or another supported mechanism performs the wakeup.

`ServerSocket.setSoTimeout(...)` can cap how long `accept()` waits, causing `SocketTimeoutException` while keeping the server socket valid. For a long-lived server, continuous polling is unnecessary when you already have a clean shutdown path via close.

## 8. Selector and Non-Blocking I/O Use Another Mechanism

`Selector.select()` is not a blocking `SocketChannel.read()`. A thread waiting for ready channels on a selector can be woken up by:

- `selector.wakeup()`: wakes the select operation **without closing** the selector.
- `selector.close()`: closes the selector and wakes any waiting select operation.
- `selectingThread.interrupt()`: sets the interrupt flag and wakes select via the wakeup mechanism.

**Do not confuse them**: interrupting a thread inside `Selector.select()` does not close all channels registered with the selector, unlike directly interrupting blocking I/O on an `InterruptibleChannel`.

Example of an event loop with a shutdown mechanism:

~~~java
// Illustrative snippet: selector is open, running is a safely shared flag.
while (running) {
    selector.select();
    if (!running) {
        break;
    }
    // Process ready keys, then remove/clear selected keys.
}

// A management thread requests stop:
running = false;
selector.wakeup();
~~~

If multiple threads manipulate keys/channels concurrently, follow `Selector` and `SelectionKey` synchronization rules, while handling closed states and invalidated keys.

### Non-Blocking SocketChannel

In non-blocking mode, `SocketChannel.read(ByteBuffer)` can return `0` when no data is available. Never write an infinite CPU-spinning loop `while (read(...) == 0) { }` to "wait" for data. Use a `Selector` or an appropriate wait mechanism, separating cancellation signals from the "not ready yet" state.

## 9. File I/O, Memory, Pipes, and Console: Do Not Treat Them Alike

| Source/Destination Type | What Is Guaranteed or Needs Checking on Cancellation |
|---|---|
| `FileChannel` (NIO) | Implements `InterruptibleChannel`; when performing blocking I/O under this contract, interrupt can close the channel and throw `ClosedByInterruptException` |
| Blocking `SocketChannel` / `ServerSocketChannel` | NIO interruptible; distinguish close from another thread vs. thread interrupt |
| `java.net.Socket` streams on Java 17 | `Socket.close()` terminates blocking socket I/O with `SocketException`; `SO_TIMEOUT` bounds reads |
| `java.net.ServerSocket.accept()` | `close()` from another thread wakes it with `SocketException` |
| `ByteArrayInputStream`/`ByteArrayOutputStream` | Purely in-memory, representing no external waiting I/O; `interrupt()` does not abort an instant buffer read |
| Traditional `FileInputStream`/`FileOutputStream` | No universal contract that `Thread.interrupt()` always aborts blocking I/O; behavior depends on the call and OS/implementation |
| `PipedInputStream`/`PipedOutputStream` | Waiting and `close` have their own mechanisms; may involve `InterruptedIOException` and synchronization, distinct from NIO `Pipe` |
| `System.in` or console | May depend on terminal/OS and wrappers; interrupting or closing from another thread is not guaranteed to unblock every read |

Do not use file I/O to demonstrate an infinitely blocking read and infer all files wait like sockets: reading a file usually blocks only briefly, and the specific operation may finish before cancellation arrives. Likewise, `close()` on an arbitrary I/O stream does not automatically **wake up** every blocked operation immediately; check the documentation for the actual resource type in use.

When using wrappers like `BufferedInputStream`, `BufferedReader`, or `InputStreamReader`, consider the **wrapper**, the **underlying source**, and **internal synchronization**. Closing or interrupting at one layer does not always propagate along the path you expect. Some APIs synchronize `close` with read operations, making cross-thread `close` not as fast an abort path as on `InterruptibleChannel`.

## 10. InterruptedIOException and Handling Partially Transferred Data

`java.io.InterruptedIOException` reports that an I/O operation was interrupted per API contract; its `bytesTransferred` field may indicate how many bytes transferred before interruption. `SocketTimeoutException` also extends this class.

Keep in mind:

- Not every interrupt produces `InterruptedIOException`; NIO channels throw `ClosedByInterruptException`.
- Not every `InterruptedIOException` means the thread has its interrupted flag set; `SocketTimeoutException` can come from a normal timeout.
- If a write is interrupted **after partial data was written**, resending the **entire** payload without tracking progress can duplicate data. Without knowing exactly what the peer received, the application needs sequence numbers, idempotency, or explicit acknowledgments in the protocol.
- If a read ends early, never assume the buffer holds all requested bytes. Rely on return values and each API's contract.

Interpret exceptions using context and resource state, rather than checking `ex instanceof IOException` and retrying endlessly.

## 11. Future.cancel(true) Is Not a Universal Stop Button for All I/O

With `ExecutorService`, a call like:

~~~java
// Illustrative snippet: future represents a submitted task.
future.cancel(true);
~~~

requests task cancellation and **may interrupt the executing thread** if the task is running. It does not guarantee an arbitrary `InputStream.read()` call will stop immediately. For blocking I/O that ignores interrupts, the task may still hold resources even after `Future` transitions to cancelled.

Design steps usually combine:

1. Set a **cancellation state** observable by the processing loop.
2. Call `cancel(true)` or `interrupt()` for operations that support it.
3. **Close task-owned resources** if the resource type has a contract to wake up blocked calls on close.
4. Configure **timeouts/deadlines** to bound waits where supported by the API.
5. Wait for the task to finish and release resources with a reasonable timeout, rather than waiting forever on a shutdown thread.

Never use `Thread.stop()` to resolve a blocked read: it is unsafe and removed from modern practice.

### Responsible Resource Management Pattern

A common pattern is letting the task close the source itself via `try-with-resources` on completion or error; the manager may only call `close()` from another thread when **granted ownership** to cancel a specific task.

~~~java
// Illustrative snippet: socket is created specifically for this task;
// executor and Future<?> are managed at the calling layer.
Socket socket = new Socket();

try {
    // Establish connection via socket.connect(endpoint, connectTimeout).
    // Pass socket to the reading task and set a read timeout if appropriate.
    // On cancellation, the management layer can close this task-owned socket.
} finally {
    socket.close();
}
~~~

`Thread.interrupt()` alone is often insufficient to guarantee resources close, especially for I/O types not implementing `InterruptibleChannel`. At the same time, avoid races where one thread closes a stream/channel while another thread is still using it if not designed for that.

## 12. Classifying Outcomes When a Read Stops

| Observation | Meaning to Consider | How to Handle |
|---|---|---|
| `read()` returns `-1` | End of data (EOF); peer may have half-closed | Handle normal completion per protocol |
| `read()` returns positive byte count | Valid data received | Process exact number of bytes read |
| `read()` returns `0` | Can occur on non-blocking channels or 0-length calls | Do not treat `0` as EOF; avoid busy-spinning |
| `ClosedByInterruptException` | Blocking I/O on interruptible channel was interrupted; channel closed | Stop using channel; preserve cancellation intent |
| `AsynchronousCloseException` | Channel closed while operation was blocking | Check whether intentional shutdown or unexpected error |
| `ClosedChannelException` | Channel is no longer open for the operation | Check lifecycle and races |
| `SocketException` when closing socket | May be intentional shutdown or network failure | Distinguish using application shutdown state |
| `SocketTimeoutException` | Configured read/accept timeout expired | Apply business retry/deadline logic; socket usually remains usable |
| `InterruptedException` | An interruptible wait operation was woken up | Propagate or restore flag and exit cleanly |

Avoid catching all `IOException` and printing "Cancelled", because that hides disconnects, permission errors, hardware failures, and data errors. Conversely, an exception after intentional shutdown is not necessarily an error worth alerting on: know the resource-closing context.

## 13. Testing the Mechanism Properly and Avoiding Flaky Tests

Testing concurrent scenarios requires **explicit synchronization**, never `Thread.sleep(100)` hoping the other thread already blocked.

- With `Pipe.SourceChannel`, keep the sink open and write no bytes so `read` has a reason to block.
- Use `CountDownLatch` to confirm the worker thread reached the point just before reading; NIO contracts also handle the case where interrupt is set right before `read`.
- Wait on `join()`/`Future.get()` with appropriate timeouts in tests; if it does not finish, clean up resources and fail deterministically instead of hanging the test suite.
- When testing `close` from another thread, allow both `AsynchronousCloseException` and `ClosedChannelException` depending on whether close arrives before or during blocking.
- For sockets, create a controlled loopback connection and test timeout, close, EOF, and half-close separately; never rely on external network latency as proof of thread ordering.
- Assert **state** (`isOpen()`, `isClosed()`, interrupted flag, received data) alongside exception types.

If the program runs across multiple JDKs or operating systems, test **the exact stream type used in production**; a test using NIO `SocketChannel` does not represent every `java.io` wrapper or other networking APIs.

## 14. Quick Decision Table

| Practical Need | Typically Appropriate Mechanism | Note |
|---|---|---|
| Cancel a task's own blocking NIO channel | `interrupt()` or `close()` per resource policy | Interrupt also **closes** the blocking `InterruptibleChannel` |
| Stop a task blocked in `Socket.read()` (owned socket) | `Socket.close()`; combine with `setSoTimeout` | `close` typically causes `SocketException`; timeout does not auto-close |
| Stop `ServerSocket.accept()` on shutdown | Set stop flag and call `ServerSocket.close()` | Do not expect a `volatile` flag alone to wake `accept` |
| Wake an event loop in `Selector.select()` | `selector.wakeup()` | No need to close selector/channels just to check new tasks |
| Cancel an executor task | `Future.cancel(true)` + cleanup/timeout | Cancellation does not guarantee aborting all I/O |
| Process large files | Read/write chunks with cancellation checkpoints | Do not assume file streams respond to interrupts like NIO |
| Receive EOF from peer | Handle protocol termination | EOF does not mean interrupted |
| Application needs a total request deadline | Track deadline across reads/writes | Single read timeout does not bound the entire task |

## 15. Core Takeaways

1. **`interrupt` is a cooperative cancellation signal**, not a mechanism forcing every Java thread or I/O call to stop immediately.
2. **`InterruptibleChannel`** has a strong contract: interrupting a blocking thread -> channel closes, `ClosedByInterruptException`, interrupted flag set; closing from another thread while blocking -> `AsynchronousCloseException`.
3. **`Socket.close()`** and **`ServerSocket.close()`** on Java 17 have specific rules for waking blocking I/O; `SO_TIMEOUT` throws a timeout exception while normally keeping the socket valid.
4. **`Selector.select()`** can be woken via `wakeup()` or interrupt without automatically closing all registered channels.
5. **`EOF (-1)`, timeout, interrupt, asynchronous close, and I/O errors** have distinct meanings; never lump them all together as "cancelled".
6. **Task cancellation and resource closing must respect ownership**: avoid closing a shared resource just because one worker no longer needs it.
7. Verify the exact contract of the API/JDK in use and test with deterministic synchronization rather than arbitrary `sleep` calls.

### Official References

- [Java 17 — InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html)
- [Java 17 — ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html)
- [Java 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Java 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java 17 — InterruptedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InterruptedIOException.html)
