# Stopping accept, Completing In-Flight Requests, and Shutting Down a TCP Server Gracefully

## 1. Why is shutting down a server not just calling `close()`?

A Java server using `ServerSocket` typically runs a loop: waiting for a connection with `accept()`, handing the accepted socket to a handler, reading a message, processing it, and returning a response. When the service needs to stop (deployment, maintenance, resource reclamation, execution time limit), a hasty shutdown can create the following situations:

- The server stops right after a client has sent a request, leaving the request half-processed.
- The client waits forever for a response, or sees the connection closed without knowing whether the server executed the business logic.
- Worker threads keep running because `ServerSocket.close()` **does not automatically close** sockets that were already returned by `accept()` earlier.
- `accept()` is blocked, the executor has not been terminated, or a client handler's read thread waits indefinitely, preventing the JVM from exiting.
- The server still accepts new connections while the worker pool is already shutting down, leading to rejected tasks and hard-to-manage sockets.

**Graceful shutdown** is the process of taking a service out of the state of accepting new work, **allowing in-flight work to complete within a bounded time**, and then closing connections, executors, and auxiliary resources. It is **not synonymous** with waiting indefinitely, and it cannot guarantee that every request completes before a hard deadline.

Objectives of this lesson: know how to **stop `accept` first**, distinguish **listening sockets from accepted client sockets**, organize **draining of running handlers**, set up **timeouts and forced shutdown**, write executable Java 17 code, and avoid confusing "server stopped" with "every client definitely received a response."

## 2. Three different lifecycle layers

| Component | Typical Java API | Role | During shutdown |
|---|---|---|---|
| **Listening socket** | `ServerSocket` and `accept()` | Listens on IP:port, accepts new TCP connections | **Close the listener** so it stops accepting |
| **Accepted client socket** | `Socket` returned by `accept()` | Byte-exchange channel with a connected client | Let in-flight requests complete within the deadline, then close each socket individually |
| **Handler / thread pool** | `ExecutorService`, `Future`, task | Reads frames, validates, processes business logic, writes response | Stop accepting new tasks after the accept loop stops, wait for running tasks, then handle timeout/force |

The following two statements have completely different semantics:

- `serverSocket.close()`: stops the listening socket; a thread blocked on `ServerSocket.accept()` is typically woken up with a `SocketException`. **Already-accepted sockets continue to exist independently**.
- `clientSocket.close()`: closes an accepted client connection. If the handler is still reading/writing, it may encounter EOF, `SocketException`, or an I/O error and fail to complete the request.

Therefore, calling `close()` on the listener **does not automatically clean up everything**, while closing all client sockets immediately can cut off work that you want to finish.

### States to include in the design

```text
RUNNING
  | accepting connections and processing requests
  v
QUIESCING / STOP_ACCEPTING
  | rejecting new work, closing listener, letting accept loop terminate
  v
DRAINING
  | waiting for accepted handlers to complete within deadline
  |                  \
  | all work done      \ timed out
  v                    v
TERMINATED          FORCED_STOP
  |                    | closing remaining sockets, requesting task cancellation
  +--------------------+
           |
     closing final resources
```

**QUIESCING** means pausing the acceptance of new work; **DRAINING** means completing the work currently in progress. In long-lived connection protocols (keep-alive), "stop accepting new TCP connections" is **not enough**: on existing sockets, the server also needs a rule not to start new requests after entering the draining state, while still allowing in-progress requests to finish.

## 3. Correct shutdown order and why

A controllable sequence of actions:

1. **Mark as stopping**: set the `accepting=false` state (or transition state via `AtomicBoolean`/state machine), preventing logic from continuing to register new work. In a real system, simultaneously update readiness or the mechanism that drains traffic from the load balancer.
2. **Close `ServerSocket`**: release the listener so the thread blocked on `accept()` wakes up. If a `SocketException` occurs **because we proactively closed it**, this is an expected shutdown outcome and should not be logged as an unhandled error.
3. **Wait for the `accept` loop to finish**: use `Future.get()`/`join()` as appropriate. This step ensures no code path can still submit new connections to the worker pool before we lock down the pool.
4. **Stop accepting new handlers with `ExecutorService.shutdown()`**: already-submitted tasks continue running; new tasks will be rejected. **Do not use `shutdownNow()` immediately** if the goal is to finish in-flight requests.
5. **Drain with a deadline** using `awaitTermination(timeout, unit)` or a mechanism that waits for in-flight requests. Ensure handlers know when they must finish, respond, close the socket, and release DB/locks.
6. **If the deadline is exceeded**, cancel according to policy: close remaining active accepted sockets to unblock I/O, use `shutdownNow()` to request interruption, wait a short additional period, and clearly report what remains. This is a *forced shutdown* and must not be presented as a completed drain.
7. **Release final resources**: close independent resources (selector if using NIO, thread executors, connection pool/DB once handlers are no longer using them, metrics/logging last), report the final status, and terminate the process.

### Why not `shutdown()` the pool before stopping accept?

There is a race:

```text
Thread A (shutdown): workers.shutdown()
Thread B (accept):   socket = listener.accept()
Thread B:            workers.execute(handle(socket))
                   -> RejectedExecutionException
```

The server just accepted a client but cannot run its handler. If that socket is not closed, resources will leak; if the client is waiting for a result, it may time out. The design must **stop/wait for the accept loop first**, then shut down the worker pool; and **even then, still handle `RejectedExecutionException`** for rejections caused by resource limits or races.

### Race between the stop flag and `accept()`

A socket can be returned from `accept()` right as another thread begins shutdown. Therefore, do not check `accepting` only before the call: **check again after `accept()` returns**; if already shutting down, close the newly accepted socket instead of submitting a new handler. This narrows the window of accepting work after deciding to stop.

There is no way to turn the entire TCP/network stack, queues, and application code into a single atomic operation with just one boolean. The load balancer, reverse proxy, and application layers must coordinate around the policy of stopping new work.

## 4. Java APIs for graceful shutdown

| API | Primary effect | Notes |
|---|---|---|
| `AtomicBoolean.compareAndSet` or `set` | Publishes the shutdown state flag to threads | Must be synchronized with accept/submit ordering; does not interrupt blocking I/O |
| `ServerSocket.close()` | Closes the listener, causing blocking `accept()` to fail when the socket is closed | Affects only the listening socket, does not close accepted sockets |
| `Future.get(timeout, unit)` | Waits for the accept-orchestration task to finish or reports exception/timeout | If the task fails unexpectedly, `ExecutionException` lets you detect it |
| `ExecutorService.shutdown()` | Stops accepting new tasks; already-submitted tasks are allowed to run | Does not automatically cancel running work |
| `ExecutorService.awaitTermination(...)` | Waits for tasks to complete after shutdown | Returns `false` on timeout; does not automatically force stop |
| `ExecutorService.shutdownNow()` | Attempts to stop work by interrupting threads; returns unstarted tasks | **Does not guarantee** that a handler blocked on I/O will stop immediately |
| `Socket.close()` | Closes an accepted connection and releases resources | Can cause blocked `read/write` calls to throw an exception |
| `Socket.setSoTimeout(...)` | Bounds the wait time for certain socket read operations | Does not bound total handler time or `accept()` |
| `CountDownLatch` | Synchronizes start/finish points in examples/tests | Not a required component of a production server |

**Distinguishing `shutdown` from `shutdownNow`:** the name `shutdownNow` is misleading; the API provides *best-effort interruption*, not a reliable "kill thread" mechanism. With classic blocking socket I/O, **closing the socket** is often necessary to unblock handlers waiting for data from the client. For handlers running CPU logic or calling external libraries, a separate cancellation/deadline design is required.

**DB pool shutdown order:** do not close the data pool while handlers are still committing/rolling back transactions. If forcing is unavoidable, there must be a consistent policy for transactions and recovery; graceful TCP shutdown by itself does not guarantee data durability.

## 5. Java 17+: runnable program that stops accept while completing in-flight requests

The example runs on **loopback**, requiring no DNS, Internet, framework, or external libraries. There are two executors: one for the `accept()` loop and a pool for handlers. A client sends `WORK`; the handler confirms it has started processing but waits on a latch to simulate unfinished work. The main thread proactively **stops accept first**, then lets the handler finish and waits for the pool to drain. Thanks to `CountDownLatch`, the example does not rely on `Thread.sleep` or "hoping for the best."

Create the file **`GracefulTcpStopDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class GracefulTcpStopDemo {
    static final class TcpService implements AutoCloseable {
        private final ServerSocket listener;
        private final ExecutorService acceptExecutor =
                Executors.newSingleThreadExecutor();
        private final ExecutorService workers =
                Executors.newFixedThreadPool(2);
        private final Set<Socket> activeSockets =
                ConcurrentHashMap.newKeySet();
        private final AtomicBoolean accepting =
                new AtomicBoolean(true);
        private final AtomicReference<Throwable> handlerFailure =
                new AtomicReference<>();
        private Future<?> acceptFuture;

        final CountDownLatch jobStarted = new CountDownLatch(1);
        final CountDownLatch releaseJob = new CountDownLatch(1);

        TcpService() throws IOException {
            listener = new ServerSocket(
                    0, 8, InetAddress.getLoopbackAddress());
        }

        int port() {
            return listener.getLocalPort();
        }

        void start() {
            acceptFuture = acceptExecutor.submit(() -> {
                try {
                    while (accepting.get()) {
                        Socket socket = listener.accept();
                        if (!accepting.get()) {
                            socket.close();
                            break;
                        }
                        activeSockets.add(socket);
                        try {
                            workers.execute(() -> handle(socket));
                        } catch (RejectedExecutionException rejected) {
                            activeSockets.remove(socket);
                            try {
                                socket.close();
                            } catch (IOException ignored) {
                                // Best effort cleanup.
                            }
                            if (accepting.get()) {
                                throw rejected;
                            }
                        }
                    }
                } catch (SocketException error) {
                    // Closing the listener during shutdown wakes up accept().
                    if (accepting.get()) {
                        throw new UncheckedIOException(error);
                    }
                } catch (IOException error) {
                    throw new UncheckedIOException(error);
                }
            });
        }

        private void handle(Socket socket) {
            try (socket) {
                socket.setSoTimeout(5_000);
                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                socket.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                socket.getOutputStream(),
                                StandardCharsets.UTF_8));

                String request = in.readLine();
                if (!"WORK".equals(request)) {
                    throw new IllegalArgumentException("Bad request");
                }

                jobStarted.countDown();
                if (!releaseJob.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Work deadline");
                }

                out.write("OK COMPLETED\n");
                out.flush();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                handlerFailure.compareAndSet(null, error);
            } catch (Exception error) {
                handlerFailure.compareAndSet(null, error);
            } finally {
                activeSockets.remove(socket);
            }
        }

        void stopAccepting()
                throws IOException, InterruptedException,
                       ExecutionException, TimeoutException {
            accepting.set(false);
            listener.close();
            // Wait for the accept loop to exit the listener before shutting down the pool.
            acceptFuture.get(5, TimeUnit.SECONDS);
            acceptExecutor.shutdown();
            workers.shutdown();
        }

        boolean awaitDrain(long timeoutMillis)
                throws InterruptedException {
            if (workers.awaitTermination(
                    timeoutMillis, TimeUnit.MILLISECONDS)) {
                return true;
            }

            // Deadline exceeded: this is a forced shutdown, no longer graceful.
            for (Socket socket : activeSockets) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                    // Best effort cleanup.
                }
            }
            workers.shutdownNow();
            return false;
        }

        void checkHandler() {
            Throwable error = handlerFailure.get();
            if (error != null) {
                throw new IllegalStateException("Handler failed", error);
            }
        }

        @Override
        public void close() {
            accepting.set(false);
            releaseJob.countDown();
            try {
                listener.close();
            } catch (IOException ignored) {
                // Closing twice is harmless.
            }
            for (Socket socket : activeSockets) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                    // Best effort cleanup.
                }
            }
            acceptExecutor.shutdownNow();
            workers.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try (TcpService server = new TcpService()) {
            server.start();

            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(), server.port())) {
                client.setSoTimeout(5_000);
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                client.getOutputStream(),
                                StandardCharsets.UTF_8));
                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.UTF_8));

                out.write("WORK\n");
                out.flush();

                if (!server.jobStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Job did not start");
                }
                System.out.println("Request is in flight");

                server.stopAccepting();
                System.out.println("Accept loop stopped");

                // Let the accepted request complete AFTER stopping accept.
                server.releaseJob.countDown();
                boolean drained = server.awaitDrain(5_000);
                if (!drained) {
                    throw new IllegalStateException(
                            "Drain deadline exceeded");
                }
                server.checkHandler();
                System.out.println("Existing request completed");

                System.out.println(
                        "Client response: " + in.readLine());
            }
        }
    }
}
```

Compile/run with **JDK 17 or newer**, in the directory containing the file:

```bash
javac -encoding UTF-8 GracefulTcpStopDemo.java
java GracefulTcpStopDemo
```

Output on a system that allows TCP loopback:

```text
Request is in flight
Accept loop stopped
Existing request completed
Client response: OK COMPLETED
```

### Why does the example prove the correct order?

1. `new ServerSocket(0, ..., loopback)` opens a listener on an ephemeral port; the client uses that exact port. A dedicated `ExecutorService` runs the `accept()` loop.
2. After `accept()` creates a client socket, `workers.execute(...)` hands it to the handler. The handler reads the `WORK` line, counts down `jobStarted`, and **does not yet return a response** because it waits on `releaseJob`.
3. `main` only proceeds to shutdown after `jobStarted.await(...)` succeeds: meaning a request is genuinely **inside the handler**. The line "Request is in flight" therefore does not depend on an arbitrary `sleep`.
4. `stopAccepting()` sets `accepting=false`, **closes the listener**, waits for `acceptFuture.get(...)` to finish, and only then calls `workers.shutdown()`. `ServerSocket.accept()` is woken up by closing the listener; the `SocketException` caused by the proactive close is recognized as expected.
5. The **already-accepted** client socket **is not closed** in the step above. Only when `main` calls `releaseJob.countDown()` does the handler write `OK COMPLETED\n`, flush, and close the socket.
6. `awaitDrain(...)` waits for accepted handlers to finish. If the deadline is exceeded, it closes remaining active sockets and calls `shutdownNow()`, returning `false` so the caller can distinguish **forced** from **graceful**. The normal path returns `true`.
7. `main` checks that there were no handler errors, and then the client reads `OK COMPLETED`. The outer `try-with-resources` closes both the client socket and the service wrapper, with safe idempotent cleanup.

**Determinism of the output:** the latches guarantee the order *handler starts → accept stops → handler completes*. This test is not a multi-client simulation or a benchmark of a real service under load. Depending on security and network configuration, loopback sockets may still be disallowed; in that case, the program reports an environment error instead of trying to fake a result that did not happen.

### What the example intentionally does not do

- Does not accept new requests on the same long-lived connection: the handler reads only **one** frame per socket.
- Does not accept or track thousands of clients, and has no backpressure/strictly bounded task queue; `newFixedThreadPool` uses an unbounded internal queue, which is **not** an optimal architecture for untrusted traffic.
- Does not handle TLS, authentication, databases, transactions, metrics, readiness, or orchestration.
- Does not guarantee the client has read the response the moment the worker has flushed; that is verified separately when the client actually calls `readLine()`.
- Does not promise the handler successfully sent every byte when force-stopped. The force path is explicitly reported and may lose in-flight requests.

## 6. Conditions for draining to truly complete

Before waiting for tasks, you must define the **unit of work**: a socket, a request, or a transaction? These are not always the same.

### One connection carrying multiple requests

If the server allows multiple requests on a single TCP connection (keep-alive or request-pipelined protocols), stopping acceptance of **new connections** does not mean stopping **new requests on old sockets**. You can apply the following policy:

- Starting from **QUIESCING**, do not begin new requests, even over already-open sockets; or apply protocol-level boundaries such as a `GOAWAY` message (if the protocol supports it).
- Allow requests that have **already been received and marked in-progress** to complete within a deadline.
- Send a close notice/final response per the protocol contract, then close the connection when appropriate.
- For clients that have connected but **not yet sent a complete frame**, enforce read timeouts and frame size limits; do not let an idle or slow-sending connection hold the process forever.

If the program has 10 open clients but only 3 requests have entered business logic, "draining connections" differs from "draining in-flight requests." For critical APIs, an in-flight counter and protocol state represent progress more accurately than merely counting sockets.

### Asynchronous work and queues

If a handler offloads work to another executor, a message queue, or an async database call, the handler finishing **does not by itself prove** that downstream work is complete. You must clearly define the "completion" milestone (received, enqueued, committed, or persisted at another system), then wait or hand off responsibility appropriately.

**Do not close the DB connection pool too early** while handlers are still committing. Conversely, you also cannot wait forever if a transaction or external API hangs; timeouts/cancellation are needed at each layer.

## 7. Drain timeout, forced shutdown, and business correctness

Set the overall wait time according to a **shutdown budget**, for example 30 seconds for traffic draining and processing, plus a small margin for cleanup. Those numbers are **operational decisions**, not Java defaults. A production configuration may be longer or shorter depending on SLAs, request characteristics, and the orchestrator's grace period.

| Situation | Appropriate response |
|---|---|
| All handlers complete before the deadline | Record graceful drain, close related connections/pools, and exit |
| A client has not sent a complete request | Apply read timeout, frame limits, and close that connection per policy |
| A handler calls an external service for too long | Trigger a separate timeout/cancellation; do not rely solely on `awaitTermination` |
| Drain deadline exceeded | Close active sockets, call `shutdownNow()`, log unfinished tasks, transition to forced state |
| Handler does not respond to interrupt | Do not treat `shutdownNow()` as success; interrupt I/O via close/cancellation or let the orchestrator terminate the process |
| Process is killed abruptly or loses power | No graceful guarantee; transactions/recovery/idempotency must tolerate interruption |

**Especially important:** When a client does not receive a response before the server stops, the processing state may be **unknown to the client**. The server may have updated the DB and then lost the connection before the response was read; blind client retries can create duplicate effects. For operations with side effects, idempotency keys, durable transactions, and lookup/reconciliation APIs are needed according to business requirements.

### What does closing a socket mean?

- `ServerSocket.close()` stops the listener; it does not wait for all client handlers to complete.
- `Socket.close()` releases the server-side endpoint; it may cause the client to see EOF/an error, **not a business-level notification that the operation failed or succeeded**.
- `Socket.shutdownOutput()` half-closes the send direction if the protocol needs to signal no more bytes in that direction, but **a TCP FIN does not replace an application response/ACK**.
- Do not arbitrarily use `SO_LINGER` to "guarantee delivery"; linger settings, RST, and close timing have OS-specific behavior. To let the client know a business operation succeeded, there must be an application-layer confirmation mechanism.

## 8. Integrating into a real application lifecycle

### 8.1. Stop signals and readiness

A containerized service typically receives termination signals or events from a framework/orchestrator. The process usually needs to coordinate:

1. Switch readiness to **not accepting new traffic** so the load balancer stops routing requests to it.
2. Allow a window for the readiness state to propagate through the orchestration system, simultaneously or subsequently stopping accept per policy.
3. Stop accept and other entrypoints (HTTP listener, queue consumer, scheduled jobs).
4. Drain in-flight requests within the allowed time.
5. Close DB/queue clients, executors, logging, and remaining components in dependency order.
6. Exit with an appropriate status code and telemetry.

Closing only the internal listener while the proxy continues sending traffic to the instance will cause connection errors for clients. Therefore, the server lifecycle is **not separate** from load balancing and routing mechanisms.

### 8.2. JVM shutdown hook

Java supports `Runtime.getRuntime().addShutdownHook(Thread)` to run cleanup code when the JVM goes through a normal shutdown sequence. However:

- Hooks are not guaranteed to run on `SIGKILL`, power loss, or OS-level forced process termination.
- A shutdown hook has a limited time budget from the environment; you should not assume it can wait indefinitely.
- Avoid deadlocks: a hook must not wait on a thread that is itself waiting on the hook or a resource the hook has locked.
- There should be **a single lifecycle controller** and an idempotent stop method. Do not let multiple hooks close the same resource in an uncoordinated order.
- The demo actively calls `stopAccepting()` in `main` to prove deterministic results; it does not need to send signals or depend on JVM shutdown timing.

In Spring/Netty/Servlet container applications, prefer the lifecycle/graceful shutdown mechanisms supported by the framework rather than directly manipulating a `ServerSocket` managed by the framework.

### 8.3. Backpressure and resource limits

Do not spawn unbounded `new Thread` instances per connection. Use a bounded-size pool/queue or appropriate async I/O; under overload, enforce a clear rejection policy and **close rejected sockets**. During shutdown, prevent task submission once `shutdown` has started. Connections waiting for `accept` in the OS backlog are not the same as in-flight work already accepted by the application.

### 8.4. Logging, metrics, and observing progress

Useful indicators: `RUNNING/QUIESCING/DRAINING/TERMINATED` state, listener open/closed, active TCP connections, in-flight requests, queued requests, completed/aborted task counts, drain duration, and forced shutdown rate. Log the reason for closing a socket, but avoid exposing sensitive payload data.

## 9. Common design mistakes

| Mistake | Consequence | Correct approach |
|---|---|---|
| Calling `ServerSocket.close()` and assuming the server is done | Accepted sockets and handlers keep running | Track active sockets/tasks, shut down executor, drain |
| Calling `workers.shutdownNow()` immediately on stop signal | Cuts off in-flight requests | Stop accept first, `shutdown` pool, wait within deadline |
| Calling `workers.shutdown()` before the accept loop exits | New sockets may be accepted but submission is rejected | Stop and join the accept loop then shut down pool; catch `RejectedExecutionException` |
| Only setting `running=false` while a thread is blocked on `accept()` | Accept loop may never wake up | Close the listener to wake up `accept()` |
| Not re-checking the flag after `accept()` returns | Accepts extra work right during shutdown | Re-check state; if stopping, close the newly accepted socket |
| Treating every `SocketException` during shutdown as a system error | False error alerts for proactive listener close | Distinguish expected-close from abnormal accept errors |
| Setting no deadline | A slow client or hung handler keeps the process alive forever | Read timeouts, cancellation, and overall shutdown budget |
| Using only `shutdownNow()` to stop I/O | Blocking socket I/O may not respond as intended | Close active sockets on force, check remaining live tasks |
| Counting sockets as counting transactions | Ignores queues/async work/in-flight requests | Define completion milestones at the application layer |
| Closing the DB pool before handlers finish | Handlers fail mid-transaction | Drain workers/commits per contract before closing dependencies |
| Assuming `flush()` means the client received the response | Client may still disconnect/time out | Design application-level confirmation and idempotency if needed |
| Not removing the instance from the load balancer | Proxy keeps sending traffic to the stopping server | Coordinate readiness and traffic draining |

## 10. Self-check exercises

**Question 1.** After calling `serverSocket.close()`, can sockets from earlier `accept()` calls still be active?

**Answer:** Yes. The listening socket and accepted client sockets are different sockets. Client socket lifecycles must be managed separately.

**Question 2.** Why must we wait for the accept loop to stop before calling `workers.shutdown()`?

**Answer:** To prevent the accept loop from continuing to submit new tasks once the pool is rejecting them, which causes `RejectedExecutionException` and can leave newly accepted sockets unclosed.

**Question 3.** Does `ExecutorService.shutdown()` cancel running requests?

**Answer:** No. It stops accepting new tasks, while already-submitted tasks continue to run. `awaitTermination` lets you wait for them after shutdown.

**Question 4.** Does `awaitTermination(5, SECONDS)` returning `false` mean the server has shut down?

**Answer:** Not necessarily. It only indicates that tasks did not finish within the deadline; you need a forced stop/socket-closing policy and clear reporting of remaining tasks.

**Question 5.** Why must accepted sockets be closed in the forced stop branch even after calling `shutdownNow()`?

**Answer:** Interruption does not guarantee unblocking all classic blocking socket read/write calls. Closing the socket can wake up blocked I/O, allowing the handler to exit.

**Question 6.** If a server still has keep-alive connections but stops accepting new sockets, can it be considered to be accepting no new requests?

**Answer:** No. Existing sockets can still receive new requests if handlers continue reading from them. You must enforce a rule against starting new requests on those connections, or send a protocol-level drain notice.

**Question 7.** A command committed to the DB, but the client lost the response during server shutdown. Can it be retried immediately without idempotency?

**Answer:** It should not be. The client's state is unknown; operations with side effects need request identification, idempotency, and lookup/reconciliation capabilities.

**Question 8.** In the example, why is the execution result deterministic without using `Thread.sleep`?

**Answer:** `jobStarted` guarantees the handler has actually entered its work, `releaseJob` prevents completion before stopping accept, and `Future.get`/`awaitTermination` confirm that accept/worker orchestration has finished.

## 11. Takeaways

**Shutting down a TCP server in the right order = stop accepting new work → interrupt blocking accept → confirm accept loop has stopped → submit no more handlers → wait for in-flight requests to complete within a deadline → handle leftovers with forced stop if needed → close resources.**

`ServerSocket.close()` **does not** automatically close accepted client `Socket`s. `ExecutorService.shutdown()` **is different from** `shutdownNow()`. `Socket.close()` and TCP FIN **do not** prove that a business operation succeeded or that the client read the response. For protocols with multiple requests per connection, clearly distinguish **stopping connection acceptance** from **stopping new requests**. In real operations, coordinate application lifecycle, timeouts, readiness, idempotency, and storage so that server deployments and shutdowns are both safe and observable.

References: Java SE 17 API `java.net.ServerSocket`, `java.net.Socket`, `java.util.concurrent.ExecutorService`, `java.util.concurrent.Future`; RFC 9293 (*Transmission Control Protocol*).