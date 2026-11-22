# Closing Resources When Mid-Operation Errors Occur and Restoring the Interrupt Flag Appropriately

## Lesson Objectives

In Java network programming, an operation can fail **after opening sockets, streams, channels, or launching several tasks** but before finishing data processing. If resources are only closed on the success path, the application will leak file descriptors, sockets, threads, buffers, or connections. If `InterruptedException` is handled by ignoring it, stop requests from other threads can be lost and the shutdown process becomes unpredictable.

This lesson places two **reliability** rules side by side:

1. **Resource ownership + cleanup:** any resource that was successfully created must be released on every exit path: success, I/O error, parse error, failure when creating a subsequent resource, timeout, or cancellation.
2. **Interrupt preservation:** when a blocking operation throws `InterruptedException`, the code should **propagate the exception** if the method contract allows it; if it truly must be caught and cannot be propagated, **restore the interrupt flag with `Thread.currentThread().interrupt()`** and then stop/return control according to policy. Do not swallow the signal and continue the loop as if nothing happened.

After this lesson, you will:

- Understand `try-with-resources`, `AutoCloseable`/`Closeable`, and how Java **closes in reverse order** and cleans up automatically when the `try` block throws.
- Know the case where **creating a second resource fails** and the already-opened first resource is still cleaned up; avoid allocation patterns outside try/finally.
- Understand **primary exception** and **suppressed exceptions** when both the body and `close()` throw; inspect `Throwable.getSuppressed()` instead of overwriting the root cause.
- Close real sockets/streams over TCP loopback when a parser detects a malformed frame mid-stream, and verify `isClosed()`.
- Distinguish `Thread.currentThread().isInterrupted()` (does not clear the flag) from `Thread.interrupted()` (checks **and clears** the flag).
- Understand that blocking methods such as `CountDownLatch.await`, `Thread.sleep`, and `Object.wait` typically **clear the flag when throwing `InterruptedException`**.
- Write Java 17+ code to test **cleaning up a `ServerSocket` before restoring the interrupt flag**.
- Distinguish the effect of interrupts on `InterruptibleChannel`, `Selector`, classic sockets, `CompletableFuture`, and `ExecutorService`.
- Perform graceful shutdown with `shutdown`/`awaitTermination` and `shutdownNow` fallback, with deadlines and proper interrupt flag preservation.
- Apply an error/cancellation checklist to avoid data loss, orphan tasks, or blindly retrying network operations that cause side effects.

This lesson includes **four standalone compiled/run Java 17+ programs**, using mock data and loopback, with no Internet dependency. This is content for the **Reliability** section; do not treat a thread stop request as a promise that the remote server has not received the request.

## 1. Why Are "Mid-Operation Errors" More Dangerous Than Errors Before Starting?

Consider a TCP handler:

~~~text
Accept connection ─► open InputStream ─► read message ─► parse ─► write result
        │                  │                  │            │
        └───────── many resources created / borrowed ──────┘
                                              └─ may fail
~~~

If the parser throws `IOException` at the fourth step, the resources **created in earlier steps** still exist unless the application actively cleans them up. In a long-running server, each forgotten socket can consume a file descriptor, OS buffers, and connection state; thousands of small errors will lead to **resource exhaustion**.

Exit paths to account for:

| Exit Path | Example | Risk If Cleanup Is Forgotten |
|---|---|---|
| Success | Read full frame and return response | Socket/stream remains held even though the request is done |
| I/O error | Peer reset, write error, timeout | Socket remains open or task keeps waiting |
| Protocol error | Invalid length prefix, invalid JSON | Abandoned frame, stream desynchronization |
| Allocation failure | File opens successfully but the next socket fails to open | The first file descriptor is leaked |
| Callback error | Exception from task, listener, publisher | Future completes exceptionally while resource stays open |
| Interrupt | Worker in `await`/`sleep` is requested to stop | Interrupt swallowed, worker continues indefinitely |
| Close error | `close()` throws an exception when a primary error already occurred | Original error lost if handled improperly |
| Shutdown race | Another thread closes the channel/socket in use | Task receives an asynchronous close error, needs classification |

**Ownership principle:** *Whoever creates a resource is usually responsible for closing it, unless the contract explicitly transfers ownership*. If a method only **borrows** a `Socket` from a connection pool, it must not close it thinking "close it just to be clean." If a method receives ownership of an accepted socket to serve **a single client**, it can use `try-with-resources` to close it.

## 2. `AutoCloseable`, `Closeable`, and try-with-resources

### 2.1. Which resources are suitable?

- `java.lang.AutoCloseable`: interface with `close() throws Exception`, supported by the `try (resource)` syntax. Not every implementation guarantees idempotency; read the specific contract.
- `java.io.Closeable`: interface extending `AutoCloseable`, `close() throws IOException`. Examples: `InputStream`, `OutputStream`, `Reader`.
- `Socket`, `ServerSocket`, `Channel` implementations, `FileChannel`, and many streams are closeable; use `try-with-resources` instead of manual cleanup on every error branch.
- `ExecutorService` in **Java 17** is not an `AutoCloseable` that you can arbitrarily place in `try (pool)` as in some newer JDKs; it must be **shut down** via the executor API and awaited if needed.

**Not every "resource" is closed with `close()`:** an `ExecutorService`, scheduled task, subscription, or future has its own lifecycle policy. A `CompletableFuture.cancel(true)` does not automatically replace closing external sockets/streams.

### 2.2. How is TWR conceptually compiled?

~~~java
try (InputStream in = Files.newInputStream(path)) {
    process(in);
}
~~~

This is a **snippet**, requiring imports from `java.io.*`, `java.nio.file.*`, and an application-defined `process` method. It is **conceptually** equivalent to:

~~~java
InputStream in = Files.newInputStream(path);
try {
    process(in);
} finally {
    in.close();
}
~~~

However, the second `finally` snippet **does not fully reproduce** the important semantics of try-with-resources when **both `process` and `close` throw exceptions**. TWR preserves the primary error and attaches the close error via `getSuppressed()`, rather than risking the close exception masking the body exception.

TWR also handles **partial initialization** and **multiple resources** strictly according to the Java Language Specification rules.

### 2.3. Open and close order

~~~java
try (AutoCloseable a = openA();
     AutoCloseable b = openB();
     AutoCloseable c = openC()) {
    use(a, b, c);
}
~~~

This is **illustrative** code: `openA/openB/openC/use` are hypothetical functions, not a standalone program. If all three are created successfully:
- Opened in the order **A → B → C**.
- Closed in the order **C → B → A** whether the body succeeds or throws an error.

If **B fails to initialize**:
- `C` is not initialized.
- `A` **is already open** so it must be closed.
- The exception from initializing B is the primary error; any error when closing A (if one occurs) is **suppressed** according to TWR semantics.

Therefore, start `try (...)` **immediately upon acquiring ownership**, instead of creating multiple sockets/streams outside and then reaching a `finally` block that is easy to miss.

## 3. Primary Exception and Suppressed Exception

### When both body and close fail

For example, the body throws `IOException("body failure")`; while unwinding, the second and first resources also throw errors from `close()`. Java prioritizes:

1. **Primary exception:** the body error `body failure`.
2. **Suppressed #1:** close of the **second** resource (closed first).
3. **Suppressed #2:** close of the **first** resource (closed second).

~~~text
body failure  ← primary
├── suppressed: close failure: second
└── suppressed: close failure: first
~~~

This is a **diagnostic information** rule; it does not mean every close succeeded. `getSuppressed()` is very useful for tracing the sequence of failures when connections or auxiliary resources also fail.

### When the body succeeds but close fails

If there is no error in the body, the `close()` exception can become **primary**. With multiple resources, the first close error becomes primary and subsequent close errors are suppressed. Therefore, "all requests finished running" does not mean cleanup completely succeeded.

### Do not overwrite the body error with a throwing finally

A trap:

~~~java
Socket socket = createSocket();
try {
    doNetworkWork(socket);
} finally {
    socket.close(); // May throw IOException and mask an error that already occurred.
}
~~~

This is an **illustrative snippet**; `createSocket`/`doNetworkWork` are functions the application must define. A safer way when you **own** the socket:

~~~java
try (Socket socket = createSocket()) {
    doNetworkWork(socket);
}
~~~

TWR handles suppressed exceptions better automatically. When TWR cannot be used due to complex ownership/lifecycle, write `finally` carefully, do not swallow or replace the primary error, and record cleanup errors separately or via `addSuppressed` when appropriate.

## 4. Example A: Error in Body, Error on Close, and Error Mid-Acquisition

The following **complete Java 17+ program** simulates resources that can throw `IOException` on close. It tests three cases:
- The body throws an error and **both resources** also throw on close.
- Initializing the second resource fails; the first resource **is still closed**.
- The body succeeds; cleanup still runs.

Save as **`ResourceFailureDemo.java`**:

~~~java
import java.io.IOException;

public class ResourceFailureDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean closeFails;

        private Tracked(String name, boolean closeFails) {
            this.name = name;
            this.closeFails = closeFails;
            System.out.println("open " + name);
        }

        static Tracked open(String name, boolean closeFails) {
            return new Tracked(name, closeFails);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (closeFails) {
                throw new IOException("close failure: " + name);
            }
        }
    }

    static Tracked failAcquire() throws IOException {
        System.out.println("acquire second: fail");
        throw new IOException("acquire failed");
    }

    public static void main(String[] args) {
        try (Tracked first = Tracked.open("first", true);
             Tracked second = Tracked.open("second", true)) {
            System.out.println("body: fail");
            throw new IOException("body failure");
        } catch (IOException e) {
            System.out.println("primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }

        try (Tracked acquired = Tracked.open("acquired", true);
             Tracked missing = failAcquire()) {
            System.out.println("unreachable");
        } catch (IOException e) {
            System.out.println("acquire-primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("acquire-suppressed: "
                    + suppressed.getMessage());
            }
        }

        try (Tracked success = Tracked.open("success", false)) {
            System.out.println("body: success");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

### Compile and run

~~~bash
javac --release 17 -encoding UTF-8 ResourceFailureDemo.java
java ResourceFailureDemo
~~~

Exact **tested** stdout:

~~~text
open first
open second
body: fail
close second
close first
primary: body failure
suppressed: close failure: second
suppressed: close failure: first
open acquired
acquire second: fail
close acquired
acquire-primary: acquire failed
acquire-suppressed: close failure: acquired
open success
body: success
close success
~~~

### What should you take away?

- **`close second` happens before `close first`:** resources are closed in reverse order of opening.
- The body error is **primary** even though both `close()` calls throw; they appear in `getSuppressed()` without being lost.
- When `failAcquire()` throws, the `acquired` resource is closed automatically even though the body never ran.
- If `close()` does not throw, we still get the normal cleanup path after the body.
- This code only simulates resources for deterministic output; next we will use **real TCP sockets** over loopback.

**An important rule:** do not treat `getSuppressed()` as a sign of "unimportant secondary errors." Socket/file close errors in production may need metrics/alerts, but **must not overwrite the primary error information**.

## 5. Example B: TCP Socket Encounters an Error Mid-Parse

The program below opens a **ServerSocket** on loopback, creates a TCP client, accepts a real connection, receives a line `BAD`, and checks whether it is `OK`. Because the frame is invalid, the parser throws `IOException` before processing completes. The sockets and streams **must still be closed**.

No Internet, certificates, or separate processes are required; everything runs in **one JVM**, with an OS-assigned ephemeral port.

Save as **`SocketFailureDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SocketFailureDemo {
    public static void main(String[] args) throws Exception {
        ServerSocket listener = null;
        Socket sender = null;
        Socket receiver = null;

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener = server;
            try (Socket client = new Socket(
                    InetAddress.getByName("127.0.0.1"),
                    server.getLocalPort())) {
                sender = client;
                try (Socket accepted = server.accept();
                     BufferedReader input = new BufferedReader(
                         new InputStreamReader(
                             accepted.getInputStream(),
                             StandardCharsets.UTF_8))) {
                    receiver = accepted;
                    client.getOutputStream().write(
                        "BAD\n".getBytes(StandardCharsets.UTF_8));
                    client.getOutputStream().flush();
                    String frame = input.readLine();
                    if (!"OK".equals(frame)) {
                        throw new IOException("invalid frame: " + frame);
                    }
                }
            }
        } catch (IOException error) {
            System.out.println("request failed: " + error.getMessage());
        }

        System.out.println("sender closed: " + sender.isClosed());
        System.out.println("receiver closed: " + receiver.isClosed());
        System.out.println("listener closed: " + listener.isClosed());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 SocketFailureDemo.java
java SocketFailureDemo
~~~

Observed stdout:

~~~text
request failed: invalid frame: BAD
sender closed: true
receiver closed: true
listener closed: true
~~~

### Ownership analysis of the example

- `ServerSocket server` belongs to the main method. Upon exiting the outer `try`, the listener is closed.
- `Socket client` is the active connecting side, opened **after** the listener and placed in its own TWR.
- `Socket accepted` is the result of `server.accept()`, i.e., an **accepted connection** rather than the listener; it is closed by the inner TWR.
- `BufferedReader input` wraps `accepted.getInputStream()` and is closed by TWR. For streams obtained from a `Socket`, closing the stream can close the underlying socket; an explicit TWR for `accepted` still clarifies ownership and protects against mid-stream processing errors.
- When the frame is `BAD`, `IOException` exits the inner block; resources are closed before the outermost catch prints the error.
- The three variables `listener/sender/receiver` outside TWR in the demo are only there to **check `isClosed()` after cleanup**; normal production code does not need to retain references to closed sockets.

**Limitations:** the example uses traditional `Socket` with connect/accept calls on loopback and has no socket read timeout because `BAD\n` is sent immediately within the same program. A real server needs `setSoTimeout`, input size/line length limits, framing/encoding validation, connection deadlines, and client count limits.

**A mid-operation error is not a signal to retry blindly.** The parser failed because of an invalid frame: return a protocol error/close the connection according to policy. Creating a new socket and resending the same `BAD` payload indefinitely only wastes resources.

## 6. Interrupt Is a Cooperative Signal, Not a Way to "Kill" a Thread

Java interrupt is a **mechanism to signal a stop/cancellation request** to a thread, not a forced operation that terminates all running work. Calling:

~~~java
worker.interrupt();
~~~

is a request to `worker`; it **does not** guarantee the task will end immediately. CPU-bound code must actively check the interrupt status; code blocked on an interruptible method may be woken up according to that method's contract.

### Two flag-checking APIs have different effects

| Call | Target Checked | Clears the Flag? |
|---|---|---|
| `Thread.currentThread().isInterrupted()` | Current thread | **No** |
| `worker.isInterrupted()` | Thread `worker` | **No** |
| `Thread.interrupted()` | **Only the calling thread** | **Yes**, it checks and then clears the flag |
| `Thread.currentThread().interrupt()` | Current thread | **Sets the flag back to true** |

**Do not use `Thread.interrupted()` just to "log whether it was interrupted"** if you do not intend to clear the signal. A single call to `Thread.interrupted()` can cause the next loop iteration to miss the shutdown request, unless a new interrupt arrives or you restore the flag.

Example:

~~~java
boolean stillRequested = Thread.currentThread().isInterrupted();
~~~

This is a non-destructive read. If you intentionally use `Thread.interrupted()`, you must understand that it **consumes/clears** the flag as documented.

## 7. `InterruptedException`: Why Must the Flag Be Restored?

Many blocking calls, when interrupted, will:
1. Notice that the thread has been requested to interrupt.
2. **Clear the interrupted status**.
3. Throw **`InterruptedException`** so the caller can decide what to do.

For example, `Thread.sleep`, `CountDownLatch.await`, `Object.wait`, `Thread.join`, and `Future.get` have interruptible waiting semantics. Therefore, in catch:

~~~java
try {
    latch.await();
} catch (InterruptedException interrupted) {
    System.out.println(Thread.currentThread().isInterrupted());
    // With an interrupted CountDownLatch.await, typically prints false
}
~~~

This is a **snippet** requiring `latch` of type `CountDownLatch`. Printing `false` does not mean the stop request has "disappeared from a business perspective"; the exception **is itself the signal** that must be respected.

### Two correct strategies (do not apply both mechanically at once)

**Strategy A — propagate:** if the method is allowed to `throws InterruptedException`, prefer:

~~~java
void waitForSignal(CountDownLatch latch)
        throws InterruptedException {
    latch.await();
}
~~~

Do not catch so the caller can handle it. Normally **there is no need to restore the flag yourself before rethrowing** because the exception is propagated upward as an explicit interrupt signal. Let the upper layer decide whether to cancel work, restore the flag, or propagate further.

**Strategy B — cannot propagate the checked exception:** when the method interface does not allow `throws InterruptedException`:

~~~java
try {
    latch.await();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt(); // Preserve the stop request.
    return; // Or throw an unchecked exception with cause.
}
~~~

This is a snippet inside a `void`-returning method with a `latch` variable. Important: **do not restore the flag and then continue the normal processing loop** if the code has no policy for continuing after an interrupt; that can cause a loop that repeatedly throws interrupts.

### What if you need to wrap into a `RuntimeException`?

~~~java
try {
    latch.await();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", interrupted);
}
~~~

This is a snippet requiring `latch`. The exception preserves `cause` to aid debugging; at the same time, the interrupt flag remains true so schedulers/other callers know about the stop request.

**If the block owns resources in try-with-resources**, place the catch outside `try (...)` so cleanup runs **before** deciding to restore the flag/return/throw. Some close methods may react to the interrupted status; manage the order of resource cleanup and flag restoration according to the specific resource.

## 8. Example C: Cleanup `ServerSocket` Before Restoring the Interrupt Flag

The following program opens a **real `ServerSocket` on loopback** in a worker, signals readiness via `CountDownLatch`, and then **waits indefinitely** on another latch. The main thread waits for the worker to report ready, calls `worker.interrupt()`, and then joins with a timeout. The worker receives `InterruptedException` from `await()`, **TWR closes the `ServerSocket` before entering the catch**, records that the flag was cleared, restores the flag, and exits.

`AtomicBoolean`/`AtomicReference` are used to print deterministic results **after the worker has stopped**, independent of stdout ordering between the two threads.

Save as **`InterruptCleanupDemo.java`**:

~~~java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptCleanupDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch waitForever = new CountDownLatch(1);
        AtomicBoolean flagBeforeRestore = new AtomicBoolean(true);
        AtomicBoolean flagAfterRestore = new AtomicBoolean(false);
        AtomicReference<ServerSocket> owned = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try (ServerSocket listener = new ServerSocket(
                    0, 1, InetAddress.getByName("127.0.0.1"))) {
                owned.set(listener);
                ready.countDown();
                waitForever.await();
            } catch (InterruptedException interrupted) {
                // try-with-resources closed the ServerSocket before this catch.
                flagBeforeRestore.set(Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                flagAfterRestore.set(Thread.currentThread().isInterrupted());
            } catch (Exception unexpected) {
                failure.set(unexpected);
                ready.countDown();
            }
        }, "interrupt-demo-worker");

        worker.start();
        if (!ready.await(3, TimeUnit.SECONDS)) {
            worker.interrupt();
            throw new IllegalStateException("Worker did not become ready");
        }
        worker.interrupt();
        worker.join(3_000);
        if (worker.isAlive()) {
            waitForever.countDown();
            worker.interrupt();
            throw new IllegalStateException("Worker did not stop");
        }
        if (failure.get() != null) {
            throw new IllegalStateException(failure.get());
        }
        if (owned.get() == null) {
            throw new IllegalStateException("No ServerSocket created");
        }

        System.out.println("flag in catch before restore: "
            + flagBeforeRestore.get());
        System.out.println("flag after restore: "
            + flagAfterRestore.get());
        System.out.println("server socket closed: "
            + owned.get().isClosed());
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 InterruptCleanupDemo.java
java InterruptCleanupDemo
~~~

Actual stdout:

~~~text
flag in catch before restore: false
flag after restore: true
server socket closed: true
~~~

### Why doesn't this example use `Thread.sleep` to guess timing?

`ready.countDown()` lets main know the worker **has already opened the `ServerSocket`** before sending the interrupt. When the worker receives the interrupt right before or during `waitForever.await()`, the wait still recognizes the signal and throws `InterruptedException`. `worker.join(3_000)` bounds how long main waits for the worker in the test; failure cases are handled instead of hanging the process indefinitely.

**Cleanup order:** the worker exits `try (ServerSocket ...)` due to the exception, the socket is closed, and **then** the `InterruptedException` catch restores the flag. This is an important technique for cleanup when canceling network work.

**Distinguish a stop request from the result of stopping:** `server socket closed: true` is verified inside the JVM; it does not prove that every previous request of a service has committed data or that real-world clients received a Close response. In production, you must also manage in-flight accepted sockets separately, not just the listener.

### When tasks are not allowed to create their own Threads

In real applications, threads are usually managed by an `ExecutorService`. The rule remains the same: when a task is interrupted, clean up resources, stop making new requests, and propagate or restore the flag according to the task API. Do not shut down the entire worker pool just because **one** request had a syntax error; distinguish per-connection errors from a full-service shutdown.

## 9. Different Types of I/O React Differently to Interrupts

**There is no single rule saying "every Java socket throws `InterruptedException` when interrupted."** Each API's specific contract matters:

| API/Operation | What You Need to Know |
|---|---|
| `CountDownLatch.await()`, `Thread.sleep`, `Object.wait` | Interrupt typically leads to `InterruptedException` and **the flag is cleared** |
| `Future.get()` / `ExecutorService.awaitTermination` | Can throw `InterruptedException` while waiting; must propagate/restore |
| `SocketChannel` / `FileChannel` implementing `InterruptibleChannel` | Interrupt while blocking can **close the channel**, throw `ClosedByInterruptException`, and **keep the flag true** |
| Another thread calls `channel.close()` during blocking I/O | May receive `AsynchronousCloseException`, which does not mean the thread was just interrupted |
| `Selector.select()` | Interrupt can cause select to return early with the interrupted status **set**, similar to wakeup |
| Traditional `Socket` / `ServerSocket`, JDK 17 | Do not assume by default that `Thread.interrupt()` always interrupts `read/accept` immediately; use socket read timeout, close from owner/controller, or appropriate NIO APIs |
| `SocketTimeoutException` | Can be a timeout from `setSoTimeout`; it is a subclass of `InterruptedIOException` but **does not** prove the thread was interrupted |
| `InterruptedIOException` | I/O interrupted per its own contract, with `bytesTransferred` when applicable; not the same as `InterruptedException` by default |
| `CompletableFuture.cancel(true)` by default | Does not directly manage/interrupt the background computation thread; the `mayInterruptIfRunning` parameter **has no effect** in base `CompletableFuture` |
| `HttpClient.sendAsync` (JDK implementation) | The returned future may support exchange cancellation requests; **do not** treat cancellation as proof that the remote server did not process the request |

### `ClosedByInterruptException` is an important case

An NIO channel supporting `InterruptibleChannel` can be **closed** when a thread blocked on it is interrupted. The Java Javadoc for `ClosedByInterruptException` explicitly states that the thread's status remains **set** at that point.

Illustrative handling pattern:

~~~java
try {
    channel.read(buffer);
} catch (ClosedByInterruptException interruptedIo) {
    // NIO closed the channel and the interrupt flag is typically true.
    // Do not continue reading on the old channel.
    throw interruptedIo;
}
~~~

This is a snippet requiring `channel` of an appropriate `SocketChannel`/`FileChannel` type, `buffer` of type `ByteBuffer`, and importing `java.nio.channels.ClosedByInterruptException`. Do not call `Thread.interrupted()` to "clear the flag cleanly" before handling it, as doing so can lose the stop signal.

### `AsynchronousCloseException` differs from `ClosedByInterruptException`

Thread A is reading a channel; thread B decides to close the channel to stop the operation. A may receive `AsynchronousCloseException` due to **closing from another thread**, not due to interrupt status. In error analysis, you must know whether the controller is shutting down to avoid logging an "unexpected I/O error" as an incident when it was an intentional stop path.

### `InterruptedIOException` is not always a thread stop request

`SocketTimeoutException` extends `InterruptedIOException`. A `Socket.setSoTimeout(2000)` causing a read to expire can throw `SocketTimeoutException` without **anyone calling `Thread.interrupt()`**. Therefore, the pattern:

~~~java
catch (InterruptedIOException e) {
    Thread.currentThread().interrupt();
}
~~~

**is not correct for all situations**. You must distinguish a read timeout from an actual interrupt/cancellation according to the API/operation contract before deciding to restore the interrupt. **Only restore explicitly when you are catching `InterruptedException` that cleared the flag, or when exception wrapping/contract requires preserving the signal.**

## 10. Interrupted ≠ Total Data Loss; a Separate Retry Strategy Is Needed

Consider a client sending a TCP frame:

~~~text
client write request ──► server receive ──► server commit
        │                        │
        └─ timeout / cancellation occurs at client
~~~

The client not receiving an ACK due to timeout/interrupt **does not mean** the server did not process the request. Especially for order-creation POSTs, financial workflows, or message queues, unconditional retries can cause **duplicate side effects**.

A reliable design:
- Attach a **request/message ID** or idempotency key per the server contract.
- Manage I/O-level timeouts and end-to-end deadlines separately.
- Classify retryable (transient) errors from permanent errors (invalid payload/auth).
- If remote state is unknown, **query status** or perform an idempotent retry according to policy.
- When a task is interrupted due to shutdown, **do not** catch the exception and start retrying connections as normal.
- Resource cleanup ensures local sockets/streams close; it **does not replace** distributed acknowledgment/transaction guarantees.

**Interrupt is a cooperative signal** meant to reduce stopping time, not a transaction rollback or a command forcing the OS to cancel all network operations instantaneously.

## 11. `ExecutorService`: `shutdown`/`awaitTermination` and the Interrupt Flag

A real server usually has a worker pool for multiple connections. For an orderly shutdown, we need to:
1. **Stop accepting/submitting new work**.
2. Call `executor.shutdown()` to reject new tasks while letting already-submitted tasks finish.
3. Wait with `awaitTermination(timeout, TimeUnit)`.
4. If the timeout expires, call `shutdownNow()` to **attempt to interrupt running tasks and return waiting tasks**.
5. Wait once more with a timeout if needed; if still not stopped, report the status clearly.
6. When the waiting thread itself receives `InterruptedException`, call `shutdownNow()` appropriately and **restore the flag** before exiting.

**Unlike `AutoCloseable` resources:** `shutdownNow()` is **best effort**; uncooperative tasks may keep running. Only `isTerminated()` tells you the executor has terminated; `shutdown()` alone does not wait.

### Example D: `ExecutorShutdownDemo.java`

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {
    static void stop(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                    System.out.println("pool: still running");
                }
            }
        } catch (InterruptedException interrupted) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> result = pool.submit(() -> "completed");
            System.out.println("task: " + result.get(3, TimeUnit.SECONDS));
        } finally {
            stop(pool);
        }
        System.out.println("pool terminated: " + pool.isTerminated());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Tested output:

~~~text
task: completed
pool terminated: true
~~~

### Limitations of the output

In the demo, the task is fast and cooperative, so `awaitTermination` returns true early and does not print `pool: still running`. Do not conclude that a pool will always stop within 3 seconds: if a task does not check interrupted status or is blocked on an API that does not support interrupts, `shutdownNow` may not finish by the deadline.

**Depending on policy**, if shutdown is still pending after the grace period, you can:
- Record metrics/live thread count and raise an alert.
- Close sockets/channels **owned** by the application to unblock I/O.
- Ensure application shutdown accepts no new tasks and enforce a global timeout.
- Do not call `System.exit()` as the default solution in a library method.

If `stop` is interrupted, the code resets the interrupt flag. The caller can observe that state and decide not to perform further blocking work.

## 12. Choosing the Right Cancellation Mechanism for Each Resource Type

| Target | Safe Stop Approach by Policy | What **Must Not Be Promised** |
|---|---|---|
| A created and owned `Socket` | Close the socket when no longer used, set read timeout, handle exceptions | `Thread.interrupt` always unblocks every old-style socket read immediately |
| A `ServerSocket` listener | `close()` terminates a blocking accept per contract | Closing only the listener closes all accepted sockets |
| `SocketChannel` / `FileChannel` | TWR, close on cancel, manage `ClosedByInterruptException` | The channel can still be used after an interrupt closes it |
| `Selector` | `wakeup()`/`close()`, manage keys and thread state | Interrupt has a single semantics identical to `await` |
| `InputStream`/`BufferedReader` | TWR and clear ownership, data limits/timeouts | Calling close always releases an external service cleanly at the business level |
| `CompletableFuture` | `cancel`/`orTimeout` per contract + separate resource cleanup | Base CF's `cancel(true)` reliably interrupts the worker thread |
| `Future` from `ExecutorService.submit` | `cancel(true)` can request an interrupt if the task is running; task must cooperate | The task rolled back side effects or closed all sockets |
| `ExecutorService` | `shutdown` → `awaitTermination` → `shutdownNow` if needed | `shutdownNow` guarantees immediate termination |
| `HttpClient.sendAsync` | Use future cancellation per implementation + request timeouts, read/close streaming body | The remote server has not received the request |
| A borrowed connection from a pool | Return/mark unusable per pool contract | Calling `close` directly at any time is safe for the entire pool |

**Ownership cannot be ignored:** A library method receiving a `Socket` managed by the caller must not decide to call `socket.close()` on error unless the API specifies **ownership transfer**. Conversely, a method that directly creates a socket and then throws an exception before returning it must close it itself.

## 13. Errors on Close and How to Report/Log Them

For production debugging:
- Keep the **original error** (e.g., `IOException: bad frame`).
- Inspect `getSuppressed()` when TWR has closing errors; do not only print `e.getMessage()` when RCA is needed.
- Use stack traces with non-sensitive trace/request IDs. Do not log access tokens, cookies, private keys, or secret raw payloads.
- Classify expected network/timeout/shutdown errors to avoid false alarms when a client closes intentionally.
- If close fails while the request succeeded, decide whether to treat the operation result as an error or warning **depending on the nature of the resource** (especially flush/write durability).
- Closing an `OutputStream` can trigger provider-specific flush/close; do not assume a close exception on a writer is "just secondary, safe to ignore" if data durability must be guaranteed.
- With TCP, closing the socket does not confirm the peer saved bytes to a database; the application needs a protocol ACK.

### Why not catch `Exception` and return success?

Anti-pattern example:

~~~java
try (Socket socket = connect()) {
    sendRequest(socket);
} catch (Exception ignored) {
    return true; // Wrong: masks all errors, including connection loss.
}
~~~

This is an **intentionally wrong snippet**; `connect/sendRequest` are hypothetical functions. It makes the caller believe the request succeeded even when TCP or parsing failed. When a fallback is needed, only recover from **well-defined** exceptions and always report status/metrics clearly.

### Why not just close twice to be sure?

`AutoCloseable.close()` does not require every implementation to be idempotent. With `Socket` and many JDK streams, repeated close may not error, but with custom resources, close can trigger side effects, flush, deregister, or throw exceptions. Clear ownership + TWR gives each owner **a single close path**.

If a buffered wrapper already owns the underlying stream, sometimes TWR on the wrapper alone is enough. If you need to track both the socket and the wrapper (as in the demo), understand that closing the wrapper may close the socket; those JDK types are safe for repeated cleanup, but do not generalize that to custom resources.

## 14. Checklist When Catching `InterruptedException` in Networking

Ask yourself in order:

1. **Is this actually `InterruptedException`?** Or is it `SocketTimeoutException`, `InterruptedIOException`, `ClosedByInterruptException`, or an `IOException` from peer/reset?
2. **Can the method `throws InterruptedException`?** If yes, usually **no catch is needed**; preserve interrupt semantics for the caller.
3. **Who owns the resources?** Close **owned** sockets/streams/channels in TWR/finally; do not close borrowed resources indiscriminately.
4. **If caught because it cannot be rethrown**, call `Thread.currentThread().interrupt()` before returning/throwing unchecked; do not swallow the signal.
5. **Do not continue the normal retry loop** when shutdown has been requested.
6. **Are there pending futures/subscriptions?** Cancel/clean up per their specific contract; do not assume interrupt cleans everything up.
7. **Is a business response/ACK needed?** Do not interpret interrupt/cancel as the server not having executed the transaction.
8. **Are deadlines and I/O limits set?** Configure socket read/connect timeouts, total operation budgets, and graceful-stop deadlines.
9. **Is logging safe?** Preserve primary + suppressed/causes while redacting secrets.
10. **Have error paths been tested?** Test partial acquire, throw in body, throw in close, interrupt during await, channel close from another thread, and resource counts after errors.

**A practical recipe:**

~~~text
ACQUIRE resources with clearly defined ownership
          │
          ▼
WORK within try-with-resources
          │
   success / error / interrupt
          │
          ▼
CLOSE all acquired resources in reverse order
          │
          ▼
PROPAGATE primary exception and preserve suppressed errors
          │
          ▼
If catching InterruptedException without rethrow:
    RESTORE Thread.currentThread().interrupt()
          │
          ▼
RETURN/STOP; avoid launching new work after shutdown request
~~~

This is orchestration logic, not a requirement to catch every `IOException` and set the interrupt flag.

## 15. Traps That Cause Resource Leaks and Lost Interrupts

| Mistake | Why Is It Wrong? | How to Fix |
|---|---|---|
| Calling `close` only on the success branch | I/O/parse errors skip cleanup | TWR immediately after acquisition |
| Creating two resources outside `try` and the second fails | The first resource is leaked | Put both inside TWR |
| Using a simple `finally { resource.close(); }` when the body already threw | Close exception can mask the body exception | TWR, inspect suppressed |
| Checking only `getMessage()`, ignoring `getSuppressed()` | Misses cleanup errors | Preserve primary and suppressed for RCA |
| `catch (InterruptedException e) {}` | Loses stop signal, liveness bug | Rethrow or restore flag + stop |
| `catch (InterruptedException e) { continue; }` | Task loops forever after stop request | Stop/return/propagate |
| Using `Thread.interrupted()` for logging | Clears the interrupt flag | `isInterrupted()` |
| Assuming the flag is still true after `InterruptedException` | Await/sleep usually clears the flag | Restore when not rethrowing |
| Calling `Thread.currentThread().interrupt()` on every `IOException` | Timeout/reset is not an interrupt | Classify exceptions by API |
| Assuming `SocketTimeoutException` must be a thread interrupt | It is an I/O timeout | Handle timeout/retry per policy |
| Assuming every blocking `Socket.read/accept` interrupts like `await` | Depends on API, JDK version, and implementation | Use timeouts/close/channels |
| Assuming `ClosedByInterruptException` does not close the channel | The channel may already be closed | Recreate the channel if continuing |
| Calling `Thread.interrupted()` after `ClosedByInterruptException` to clear the flag | Can lose the stop request | Keep the flag and propagate per policy |
| Assuming `CompletableFuture.cancel(true)` always interrupts the worker | Base CF does not control the worker | Separate cancellation + cleanup |
| Assuming `shutdownNow` forces every task to stop | Best effort only | Cooperative tasks, deadlines/metrics |
| Closing `ServerSocket` and thinking accepted sockets also close | Listener and connections are separate | Track/close each accepted socket |
| Resending a request after timeout without idempotency | Can duplicate server side effects | ACK/idempotency/status lookup |
| Shutting down the entire worker pool because one client sent a bad frame | Wrong error scope | Per-connection cleanup |
| Reusing a closed socket | Closed resources cannot be reopened | Create a new connection when needed |
| Losing ownership between callbacks/futures | Nobody is responsible for cleanup | Define owner before transfer |
| Logging tokens/secret raw payloads on error | Creates new leaks during RCA | Log trace ID + redact |
| Ignoring `OutputStream.close()` errors in durability-critical flows | Data may not be flushed/committed | Track close/flush result and contract |
| Assuming cleanup = rollback | The server may have already received the request | Protocol ACK and transaction policy |

## 16. Testing Error Branches Deterministically

Do not test only the "happy path" when connections succeed. A reliable test suite should include:

1. **Success:** 1–3 resources created; every resource closed exactly once per ownership.
2. **Body throws:** parser throws `IOException`; resources still close in reverse order.
3. **Acquisition failure:** resource A succeeds, B throws; A must close.
4. **Close failure:** body throws, close also throws; primary is preserved and suppressed is recorded.
5. **Close-only failure:** body succeeds, close throws; close error is not silently ignored.
6. **Real TCP invalid payload:** receives `BAD`, parser fails; accepted/socket/listener closed.
7. **Interrupt before await:** flag is set before entering await; still detected, throws exception, and cleans up.
8. **Interrupt during await:** use `CountDownLatch` to synchronize readiness, send interrupt, and verify flag restored and resources closed.
9. **Executor graceful success:** tasks complete, `shutdown` + `awaitTermination` returns true.
10. **Executor timeout:** task may wait indefinitely; `shutdownNow` requests interrupt, test has an outer deadline so CI does not hang.
11. **Socket read timeout:** peer holds connection open without sending data; `setSoTimeout` causes read to throw timeout and clean up.
12. **Channel interruption:** blocking NIO channel is interrupted; verify channel closed, interrupted status true, and contract exception.
13. **Asynchronous channel close:** another thread closes the channel; distinguish from interrupting the worker.
14. **Future cancellation:** observe that future state differs from the actual state of the task/network resource.
15. **Server ACK ambiguity:** server committed but client timed out; retry only when policy/idempotency allows.

For multithreaded tests, prefer `CountDownLatch`, timeouts, and state checks rather than `Thread.sleep` hoping for the right timing. Do not assert that every OS or implementation will return **the exact same socket error message** during a racing shutdown.

## 17. Practice Exercises

1. In what order will TWR with resources A, B, C close if the body throws `IOException`?
2. If creating A succeeds but B throws during initialization in the resource list, is A closed?
3. When the body throws and both `B.close` and `A.close` throw, what is the primary exception? Which API inspects the two close errors?
4. Why can a simple `try/finally` lose the primary error when `close` also throws?
5. How does `Closeable` differ from `AutoCloseable` in the `close` signature?
6. What types of sockets does `SocketFailureDemo` create? Why do all three report closed when the parser receives `BAD`?
7. How can `reader.close()` affect the `accepted Socket`?
8. In `InterruptCleanupDemo`, why does the catch block see the flag as false and then restore it to true?
9. If a method has `throws InterruptedException`, what is usually the simplest handling that preserves the signal?
10. When a method cannot declare a checked interrupt exception, what should it do before returning?
11. How do `Thread.currentThread().isInterrupted()` and `Thread.interrupted()` differ?
12. Can you write `catch (InterruptedException e) { continue; }` in a worker loop? Why or why not?
13. Why shouldn't you set the interrupt flag to true for every `SocketTimeoutException`?
14. If a `SocketChannel` is interrupted while blocking, what happens to the channel and the interrupt flag?
15. How do `ClosedByInterruptException` and `AsynchronousCloseException` differ?
16. Does `CompletableFuture.cancel(true)` always interrupt the processing worker?
17. Does `ExecutorService.shutdownNow()` guarantee terminating every task immediately?
18. `awaitTermination` is interrupted; should you keep waiting without restoring the flag?
19. If the `ServerSocket` listener is closed, do accepted connections automatically close with it?
20. A POST request times out on the client after sending bytes; can you conclude the server has not created the order?
21. When can an error in `OutputStream.close()` have data significance rather than just cleanup?
22. A method is passed a socket borrowed from a connection pool; should it close it in catch by default?
23. If a worker has restored the interrupt flag and then immediately calls a new blocking method, what can happen?
24. Why shouldn't you test interrupt timing using several `Thread.sleep(100)` calls and guessing?
25. Write a skeleton for handling a read request with a deadline, TWR, and proper classification of `IOException` vs `InterruptedException`.

**Suggested answers:**
(1) C→B→A; (2) yes; (3) body error is primary, `getSuppressed()` contains B/A close errors; (4) the finally exception can mask the body error; (5) `Closeable.close` declares `IOException` whereas `AutoCloseable.close` declares `Exception`; (6) listener, sender, accepted; TWR closes all of them; (7) closing the stream can close the socket; (8) `await` clears the flag before throwing `InterruptedException`, catch restores it; (9) rethrow; (10) `Thread.currentThread().interrupt()` then stop/throw unchecked; (11) `isInterrupted` does not clear, `Thread.interrupted` clears; (12) no, loses the stop signal; (13) a timeout does not necessarily involve an interrupt; (14) channel closes, flag is set, `ClosedByInterruptException`; (15) interrupted worker vs close from another thread; (16) no for base CF; (17) no, best effort; (18) no, restore when you must catch; (19) no; (20) no, requires idempotency/status; (21) flush/durability; (22) no, unless ownership was transferred; (23) it may immediately throw interrupt again / not proceed; (24) timing is non-deterministic; (25) create resources in TWR, set timeout, classify errors, clean up, and propagate/restore interrupt per contract.

## 18. Summary

- **Every resource whose ownership is acquired must have a close path** even when failing mid-operation; `try-with-resources` is the default choice.
- **TWR closes in reverse order of opening**, handles partial initialization, and preserves close failures in `getSuppressed()`, preventing body errors from being masked.
- **`InterruptedException` is a stop signal:** propagate it if possible; if caught and not propagated, **restore `Thread.currentThread().interrupt()`**, usually after cleanup, and then stop work.
- **Do not clear the flag unintentionally:** `Thread.interrupted()` clears the flag, `isInterrupted()` does not.
- **Each I/O API has its own semantics:** NIO `ClosedByInterruptException` keeps the interrupt flag and closes the channel; old sockets, selectors, timeouts, and async futures cannot share a single assumption.
- **Executor shutdown must have deadlines**, cleanup, and cooperative tasks; `shutdownNow()` is only best effort.
- **Local cleanup does not replace server application ACK/rollback**, especially when retrying after timeout/cancel.
- **Four Java 17 programs were actually run**: suppressed exceptions/partial acquire, TCP parser failure, `ServerSocket` cleanup after interrupt, and `ExecutorService` graceful shutdown.

### References

- [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Oracle Java SE 17 — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html)
- [Oracle Java SE 17 — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [Oracle Java SE 17 — Thread.interrupt / isInterrupted / interrupted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Oracle Java SE 17 — InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html)
- [Oracle Java SE 17 — InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html)
- [Oracle Java SE 17 — ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html)
- [Oracle Java SE 17 — Socket and ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Oracle Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 17 — CompletableFuture.cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
