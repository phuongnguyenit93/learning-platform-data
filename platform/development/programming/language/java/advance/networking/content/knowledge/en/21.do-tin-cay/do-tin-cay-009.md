# Graceful Shutdown in Java Networking: Stop Accepting Work, Drain In-Flight Tasks, and Terminate in Order

## 1. Real-World Problem and Goals

A Java HTTP/TCP server is processing requests, with worker threads and connections to databases, message brokers, or other APIs. You need to **stop the service** to deploy a new version, change configuration, reclaim resources, or exit the application. If you simply call `System.exit(0)`, close all sockets, or call `shutdownNow()` immediately, requests currently in progress may be cut off mid-flight. Conversely, if you only wait for all threads to finish on their own while **still accepting new requests**, the shutdown process could drag on forever.

**Graceful shutdown** is the process of **stopping new work intake first, giving already-accepted work an opportunity to complete within a bounded deadline, and then releasing resources in the proper dependency order**. If work cannot finish within the deadline, the system must have a clear **forced-shutdown policy**, rather than waiting indefinitely.

Three core questions of this article:

1. **How do you stop accepting new work?** Stop the listener, mark the service `DRAINING`, update readiness, reject admission, or stop pulling from a queue/broker.
2. **How do you wait for running work?** Distinguish between in-flight requests and queued requests; use `ExecutorService.shutdown()`, `awaitTermination(...)`, track active requests/connections, and enforce an overall deadline.
3. **How do you terminate in order?** Finish responses/ACKs/commits, close accepted connections, worker pools, schedulers, databases/brokers, and finally telemetry; avoid closing a dependency while a handler is still using it.

Common scenarios: restarting an HTTP server, shutting down a TCP server, rolling-deploying a Java service, closing WebSocket sessions, stopping a message consumer, or stopping background tasks. For each case, the **unit of work**, **what constitutes completion**, and **retryability** may differ.

## 2. Abrupt Stop vs. Graceful Shutdown

~~~text
ABRUPT STOP
RUNNING
   |
   +--> close sockets + shutdownNow + exit
          |
          +--> some requests lose their response
          +--> side effects may have occurred, but the client never receives an ACK
          +--> in-flight state is not checkpointed
          +--> flushes/logs are incomplete

GRACEFUL SHUTDOWN
RUNNING
   |
   v
DRAINING / NOT READY
   |   (accept no new work)
   v
STOP INGRESS / LISTENER
   |
   v
DRAIN IN-FLIGHT + QUEUED-IF-ALLOWED
   |   (within overall deadline)
   +-- completed --> flush response/ack/checkpoint
   |
   +-- timed out --> cancel/abort best-effort + reconcile later
   |
   v
CLOSE DEPENDENCIES / RESOURCES
   |
   v
STOPPED
~~~

**It is not an absolute zero-data-loss guarantee.** A machine can lose power, a process can be killed without running hooks, a client can disconnect between commit and response, a database can die, or the drain deadline can expire. Graceful shutdown **reduces risk** during a planned stop; to achieve durable data and avoid duplicate or dropped business processing, you also need **idempotency, transactions, durable queues, retries, and recovery**.

### 2.1. Defining "In-Flight" Is Crucial

- **Accepted TCP connection:** `accept()` has returned, but no request may have been read yet.
- **Active request:** the handler has started executing business logic.
- **Queued task:** already submitted to `ExecutorService`, but no thread is running it yet; `shutdown()` can still let queued tasks run.
- **Streaming session:** a WebSocket/SSE/gRPC stream can stay open arbitrarily long; you cannot wait for "natural completion" forever when the server must stop.
- **Background task:** a job may outlive a request and need to save a checkpoint to resume.
- **Durable message:** the consumer has received a message but has not committed/acked it yet; whether stopping triggers redelivery depends on the broker contract.

Therefore, you must clearly define the **admission cutoff**, **drain scope**, **max wait**, and **forced action**. "Wait for everything to finish" does not mean merely waiting for the thread pool to empty if sockets/streams or work elsewhere still remain.

## 3. Lifecycle States and Invariants

A simple model:

~~~text
NEW -> RUNNING -> DRAINING -> STOPPING -> STOPPED
                       |          ^
                       +-- deadline+
~~~

- `RUNNING`: listener/poller accepts new work; health/readiness allows routing.
- `DRAINING`: accepts no **new business tasks**; already-accepted work is allowed to finish within a bounded time.
- `STOPPING`: stops/blocks ingress sources, finishes or cancels remaining tasks, and closes transports/dependencies.
- `STOPPED`: no threads/sockets/pools belonging to the service remain; some stopped server objects cannot be reused.

In production, transitions should be **monotonic**: do not automatically transition `DRAINING -> RUNNING` once listeners/pools have been closed. Use `AtomicBoolean`/`AtomicReference<State>` to prevent two concurrent shutdown signals from causing double close or overlapping execution.

~~~java
enum State { NEW, RUNNING, DRAINING, STOPPING, STOPPED }

AtomicReference<State> state =
        new AtomicReference<>(State.RUNNING);

// Only one caller is allowed to initiate draining.
boolean firstShutdown = state.compareAndSet(
        State.RUNNING, State.DRAINING);
~~~

This is an **illustrative snippet** inside a class that imports `java.util.concurrent.atomic.AtomicReference`, not a complete program. A real system also needs status/error handling if shutdown fails, and **must not report "stopped" merely because shutdown was called while threads are still running**.

### 3.1. Invariants That Help Testing

When the system enters the draining state:

1. **Accept no new requests/business tasks** after the defined cutoff; requests caught in races must be handled according to a clear policy.
2. **Do not close a dependency** while an already-accepted handler still needs it.
3. **Every accepted task** must have an explicit outcome: completed/acked, failed/retried, cancelled, or checkpointed.
4. **Do not wait indefinitely**; enforce an overall deadline and an escalation mechanism.
5. Shutdown may be called multiple times without **corrupting** already-completed steps.

Checking only `pool.isShutdown()==true` does not prove these conditions, because `isShutdown` means the pool was asked to stop accepting tasks, **not that all tasks have finished**.

## 4. Step 1: Stop Accepting New Work

### 4.1. TCP Server: Close the Listening Socket First

For a server based on `ServerSocket`:

~~~java
ServerSocket listener = new ServerSocket(8080);

// In the shutdown coordinator:
stopping.set(true);
listener.close(); // A blocked accept() will throw SocketException.
~~~

This is an **illustrative snippet**, requiring `ServerSocket` imports and an `AtomicBoolean stopping` variable. Per JDK 17, `ServerSocket.close()` causes a thread blocked in `accept()` to receive `SocketException`; that can be **normal behavior during an intentional shutdown**, not an incident that warrants spamming error logs.

**Crucial point:** closing the **listening socket** prevents **new TCP connections**, but **does not automatically close all already-accepted `Socket`s**. You can continue processing those accepted sockets during the drain window. For each accepted socket, you must define whether additional requests are allowed on a persistent connection; the application gains nothing if it keeps reading indefinitely from an old connection while draining.

### 4.2. Race Between `accept` and `ExecutorService.execute`

~~~java
while (!stopping.get()) {
    Socket client = listener.accept();

    if (stopping.get()) {
        client.close();
        continue;
    }
    try {
        workers.execute(() -> handle(client));
    } catch (RejectedExecutionException rejected) {
        client.close();
    }
}
~~~

This is an **illustrative fragment**; real accept logic must catch `SocketException` from intentional shutdown as well as `IOException`. A race can occur when a connection is accepted **at the exact moment** shutdown begins; therefore, **re-check `stopping` after `accept`**, and handle `RejectedExecutionException` if the pool closed during submission.

Do not reverse the order by calling `workers.shutdown()` while leaving `listener.accept()` open: new requests may be accepted only to be rejected, leaving clients hanging or reset unnecessarily. Strive to **stop ingress first**, then finish queued/running work.

### 4.3. HTTP Server and Readiness

In a load-balanced HTTP service, you typically coordinate:

1. Set **readiness=false** so the load balancer/orchestrator stops routing new traffic to the instance.
2. Start **draining**: reject new admissions per policy, and limit keep-alive/persistent sessions.
3. Stop the HTTP listener/acceptor or call the appropriate server stop API after coordination.
4. Wait for in-flight requests within the deadline; do not cancel immediately while normal completion is still possible.
5. Close dependencies and exit the process.

**Readiness is not an instant wall.** There is propagation delay in updating endpoint tables, already-open connections, or requests already in transit to the instance. You should have an **application-level admission guard** and proxy drain configuration, rather than relying solely on a healthcheck flag.

In Kubernetes, when a Pod is asked to stop, consider the **termination grace period, preStop lifecycle hook, and SIGTERM behavior** of the runtime/load balancer. These are useful orchestration mechanisms, but they **do not replace** application-level management of in-flight tasks. A grace period shorter than the actual drain time will lead to forced termination.

### 4.4. Queue Consumer or Scheduler: Stop "Pulling" First

If a service pulls work from a queue/broker, "stopping intake" usually means **pausing polling**, unsubscribing, or stopping fetches of new messages. Then wait for messages already handed to workers to reach a safe outcome. Only commit offsets/ACKs when consistent with actual completion semantics; do not ACK before data is persisted and then shut down abruptly.

For scheduled jobs, you must stop scheduling new task dispatches; currently running tasks should be drained or checkpointed. `ScheduledExecutorService.shutdown()` has non-trivial semantics and policies for delayed/periodic tasks; check settings such as `ScheduledThreadPoolExecutor.setContinueExistingPeriodicTasksAfterShutdownPolicy` and `setExecuteExistingDelayedTasksAfterShutdownPolicy` if you have explicit requirements.

## 5. Step 2: Wait for Running Work with ExecutorService

JDK 17 provides these core APIs:

| API | Behavior | What Not to Infer |
| --- | --- | --- |
| `shutdown()` | **Stops accepting new tasks**, lets submitted tasks continue per executor policy | **Does not block** waiting for tasks to finish |
| `isShutdown()` | Shutdown has been requested | Does not mean tasks have finished |
| `awaitTermination(timeout, unit)` | **Waits** for the pool to terminate after shutdown, or until timeout/interrupt | Calling it alone **does not shut down the pool** |
| `isTerminated()` | Pool has completely stopped after shutdown; no running/queued tasks remain | Does not guarantee business ACKs were committed outside the pool |
| `shutdownNow()` | Attempts to interrupt running tasks, prevents queued tasks from starting; returns list of unstarted tasks | **Does not force** every task to stop immediately |
| `Future.cancel(true)` | Requests cancellation of a running task if the implementation supports it | Does not guarantee transactional side effects are rolled back |

### 5.1. Standard Two-Phase Sequence

~~~java
static boolean drainPool(
        ExecutorService pool,
        long gentleSeconds,
        long forcedSeconds) {

    pool.shutdown(); // Stop accepting new tasks.
    try {
        if (pool.awaitTermination(gentleSeconds, TimeUnit.SECONDS)) {
            return true; // Finished tasks per pool rules.
        }

        List<Runnable> neverStarted = pool.shutdownNow();
        // Production: log/requeue/checkpoint neverStarted per business rules.

        return pool.awaitTermination(forcedSeconds, TimeUnit.SECONDS);
    } catch (InterruptedException interrupted) {
        pool.shutdownNow();
        Thread.currentThread().interrupt(); // Preserve interrupt status.
        return false;
    }
}
~~~

This is an **illustrative Java 17 method**, requiring `java.util.concurrent.*` and `java.util.List` imports. It is the two-phase pattern recommended in the JDK `ExecutorService` documentation: a **graceful attempt** via `shutdown + awaitTermination`, followed by a **best-effort forced attempt** via `shutdownNow + awaitTermination`.

**Do not report success too early:** `shutdownNow()` may return unstarted tasks, and running tasks may **ignore interrupts**. The method returns `false` if the wait budget expires or it is interrupted; you must record remaining tasks and follow-up actions. For services with data durability, **"the pool has stopped"** also does not mean every message was acknowledged by the database/broker.

### 5.2. `shutdown()` Still Lets Queued Tasks Run

Suppose a pool has two worker threads, two running tasks, and 200 tasks already queued before the cutoff. `shutdown()` **does not discard those 200 tasks**; they can still be executed. If 200 tasks take one minute, a 20-second drain window is not enough. That is why **bounding the queue while RUNNING**, managing admission, and setting per-task timeouts are important.

If policy allows completing **only already-started tasks** while queued tasks must return to a broker, you need an architecture that supports **reclaiming/requeueing unstarted tasks**, rather than assuming `shutdown()` has those semantics by default. `shutdownNow()` returns unstarted `Runnable`s, but returning a `Runnable` does not automatically turn it into a checkpointed broker message; the application must store task IDs and state in a durable store.

### 5.3. Interruption Is a Cooperative Request

A worker can respond cleanly to interrupts:

~~~java
try {
    while (!Thread.currentThread().isInterrupted()) {
        performOneBoundedStep();
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
} finally {
    closeOwnedResources();
}
~~~

This is **illustrative code**; the functions are application helpers. Blocking operations such as `BlockingQueue.take()` and `Thread.sleep()` typically respond with `InterruptedException`. However, a DB driver, socket read, native operation, or CPU loop that does not check for interrupts may **not stop immediately**. With traditional sockets, you need **timed reads, controlled socket closing**, or libraries with appropriate deadline/cancellation semantics.

**Do not use `Thread.stop()`** as a forced-shutdown mechanism: it is unsafe for invariants and locks. Do not assume `shutdownNow()` will "kill threads" or roll back an already-committed transaction.

## 6. Step 3: Close Resources in Dependency Order

Order shutdown by **what still uses what**. A reference order:

~~~text
1. Stop routing/admission/listeners/consumer polling.
2. Await short in-flight critical requests, stop new periodic jobs.
3. Let handlers finish response / persist / ACK; checkpoint resumable jobs.
4. Close accepted client connections and long-lived streams according to policy.
5. Stop worker executors; awaitTermination bounded; escalate if necessary.
6. Close service dependencies after their users stop:
     database pools, outbound HttpClient resources,
     broker producers/consumers, file handles.
7. Flush metrics/traces/logs; stop observability transports.
8. Mark STOPPED; process can exit.
~~~

**There is no single simple order that fits every service.** For example, consumer polling must stop **before** workers drain, yet a broker producer must remain open until workers **publish their final results**. A database connection pool must also stay open while handlers are still committing. When a producer and consumer share a client object, check whether close operations can be separated.

### 6.1. Why Closing the Database Early Is a Bug

~~~text
Thread A: processing order -> preparing to COMMIT
Thread B: receives shutdown -> dbPool.close()
Thread A: commit fails, client may time out
~~~

A safer sequence:

~~~text
stop intake -> existing orders finalize -> pool terminated
           -> close DB pool -> flush logs/metrics -> stopped
~~~

If a task is uncooperative, safe completion cannot be guaranteed past the deadline; instead of pretending to be graceful, you must have recovery (idempotent retries, transaction status checks, dead-letter queues) and concrete metrics.

### 6.2. TCP Listening Socket and Accepted Sockets Have Different Lifecycles

Closing `ServerSocket` to stop `accept()` **does not close** already-accepted client `Socket`s. Each handler should use `try-with-resources`/`finally` to close its own socket once it has sent the ACK or upon timeout/cancellation. If you want forced shutdown after the deadline, track the set of **active sockets** so you can close any that are still blocked (and avoid leaks); note that closing them may cause workers to see `SocketException` as an expected consequence.

### 6.3. A Sent Response Does Not Always Mean Business Work Is Done

A `200 OK` response may have been sent while the database has not yet committed if the code executes in the wrong order. For payments/orders, you must **define the point of success/ACK**, transaction commit, and idempotency. During graceful shutdown, do not emit a "done" ACK when you have only placed a task into a volatile queue and are about to discard the queue. Persist durable results before the client receives confirmation, or explicitly expose `202 Accepted` semantics when a durable background job is running.

## 7. Overall Deadline: Do Not Wait Indefinitely During Deployment

A typical deployment problem has a finite **grace period** from the orchestrator. If you grant each step 30 seconds and add 5 steps together, the total time can exceed the Pod's 30-second budget. Compute against an **absolute deadline**:

~~~text
deadline = shutdownStartedAt + overallBudget

phase A: stop ingress (budget from deadline)
phase B: drain in-flight (remaining budget)
phase C: close dependencies (remaining budget)
phase D: flush telemetry (remaining budget)
phase E: force if necessary before orchestrator kills process
~~~

### 7.1. Use `System.nanoTime()` for Elapsed Intervals

~~~java
long deadline = System.nanoTime()
        + TimeUnit.SECONDS.toNanos(20);

// In the wait step:
long nanosRemaining = deadline - System.nanoTime();
if (nanosRemaining > 0) {
    terminated = workers.awaitTermination(
            nanosRemaining, TimeUnit.NANOSECONDS);
}
~~~

This is an **illustrative snippet**; `workers` and `terminated` are already-declared variables. `System.nanoTime()` is meant for **measuring elapsed intervals** on a monotonic clock, making it more suitable than `System.currentTimeMillis()` when the system clock is adjusted. Avoid overflow when adding overly large budgets; in practice, use finite, small budgets.

### 7.2. When the Deadline Expires, State the Policy Clearly

- Mark the service **not ready**, preventing additional work from being accepted.
- Send best-effort cancellation signals, call `shutdownNow()`, and close sockets/blocking I/O if needed.
- Do not send "success" for uncommitted tasks.
- Record IDs/cursors/attempts needing recovery, if time and storage remain available.
- Emit metrics: `drain_timeout`, `forced_close`, `unfinished_tasks`, and reasons.
- Rely on the broker/DB/idempotency to reconcile indeterminate work after the process restarts.

Do not keep "waiting just a little longer" repeatedly; that is no longer a bounded graceful shutdown. If the process is forcibly killed before flushing, data preservation must come from **durable design while RUNNING**, not solely from a shutdown hook.

## 8. Standalone Java 17+ Example: Stop Accepting, Wait for One Request, and Terminate Workers

The following **GracefulTcpShutdownDemo.java** program is a minimal TCP line-protocol server that binds only to `127.0.0.1` on an ephemeral port. Its purpose is to demonstrate the exact **lifecycle order** without depending on the Internet or external frameworks:

1. The listener accepts one client; a worker reads a `ping` line.
2. The worker signals that processing has started via `CountDownLatch started`, then **waits at the `mayFinish` gate** (this is test synchronization, not real business logic).
3. `main` **stops accepting** via `stopping.set(true)` and `listener.close()`; the acceptor exits after the intentional `SocketException`.
4. `main` calls `workers.shutdown()`. With the handler still waiting on the latch, `awaitTermination(100ms)` returns `false`: work is still in progress.
5. `main` lets the worker finish via `mayFinish.countDown()`; the client receives `ACK:ping`.
6. `main` calls `awaitTermination(5s)` and confirms the pool has terminated; resources are cleaned up.

**The output order is deterministic thanks to the latches**, independent of the random port chosen. This demo illustrates **stopping new connections and completing an already-accepted request**. It **does not** provide HTTP protocol handling, TLS, authentication, production backpressure, or durable transactions.

Save as **GracefulTcpShutdownDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class GracefulTcpShutdownDemo {
    static final AtomicBoolean stopping = new AtomicBoolean();
    static final CountDownLatch started = new CountDownLatch(1);
    static final CountDownLatch mayFinish = new CountDownLatch(1);
    static final CompletableFuture<Void> handlerDone =
            new CompletableFuture<>();

    static void handle(Socket socket) {
        try (socket;
             BufferedReader input = new BufferedReader(
                     new InputStreamReader(
                             socket.getInputStream(),
                             StandardCharsets.UTF_8));
             BufferedWriter output = new BufferedWriter(
                     new OutputStreamWriter(
                             socket.getOutputStream(),
                             StandardCharsets.UTF_8))) {

            socket.setSoTimeout(3000);
            String request = input.readLine();
            if (!"ping".equals(request)) {
                throw new IOException("Expected ping");
            }
            started.countDown();

            // Synchronization gate for DEMO purposes only.
            if (!mayFinish.await(5, TimeUnit.SECONDS)) {
                throw new IOException("Drain deadline exceeded");
            }

            output.write("ACK:" + request);
            output.newLine();
            output.flush();
        } catch (InterruptedException problem) {
            Thread.currentThread().interrupt();
            handlerDone.completeExceptionally(problem);
            return;
        } catch (Exception problem) {
            handlerDone.completeExceptionally(problem);
            return;
        }

        handlerDone.complete(null);
    }

    static void acceptLoop(
            ServerSocket server,
            ExecutorService workers,
            CompletableFuture<Void> acceptDone) {

        try {
            while (!stopping.get()) {
                Socket socket;
                try {
                    socket = server.accept();
                } catch (SocketException closed) {
                    if (!stopping.get()) {
                        throw closed;
                    }
                    break; // Intentional listener close.
                }

                // Race guard: shutdown started right after accept.
                if (stopping.get()) {
                    socket.close();
                    continue;
                }

                try {
                    workers.execute(() -> handle(socket));
                } catch (RejectedExecutionException rejected) {
                    socket.close(); // Do not leak a rejected socket.
                }
            }
            acceptDone.complete(null);
        } catch (IOException problem) {
            acceptDone.completeExceptionally(problem);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);

        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"))) {

            CompletableFuture<Void> acceptDone =
                    new CompletableFuture<>();
            Thread acceptThread = new Thread(
                    () -> acceptLoop(listener, workers, acceptDone),
                    "acceptor");
            acceptThread.start();

            try (Socket client = new Socket(
                         InetAddress.getByName("127.0.0.1"),
                         listener.getLocalPort());
                 BufferedWriter sender = new BufferedWriter(
                         new OutputStreamWriter(
                                 client.getOutputStream(),
                                 StandardCharsets.UTF_8));
                 BufferedReader receiver = new BufferedReader(
                         new InputStreamReader(
                                 client.getInputStream(),
                                 StandardCharsets.UTF_8))) {

                client.setSoTimeout(5000);
                sender.write("ping");
                sender.newLine();
                sender.flush();

                if (!started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Handler did not start");
                }
                System.out.println("in-flight: 1");

                // Step 1: reject new connections.
                stopping.set(true);
                listener.close();
                acceptDone.get(5, TimeUnit.SECONDS);
                acceptThread.join(5000);
                if (acceptThread.isAlive()) {
                    throw new IllegalStateException(
                            "Accept thread alive");
                }
                System.out.println("accepting: stopped");

                // Step 2: pool stops accepting new tasks.
                workers.shutdown();

                // Worker is holding the latch, so it cannot be terminated yet.
                boolean early =
                        workers.awaitTermination(
                                100, TimeUnit.MILLISECONDS);
                System.out.println("still processing: " + !early);

                // Step 3: let the existing request finish before exiting.
                mayFinish.countDown();
                String reply = receiver.readLine();
                if (!"ACK:ping".equals(reply)) {
                    throw new IOException("Bad reply: " + reply);
                }
                handlerDone.get(5, TimeUnit.SECONDS);
                System.out.println("reply: " + reply);

                if (!workers.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Workers did not terminate");
                }
                System.out.println("workers: terminated");
            } finally {
                mayFinish.countDown();
            }
        } finally {
            // Safety cleanup if the demo fails mid-run.
            stopping.set(true);
            mayFinish.countDown();
            workers.shutdownNow();
            workers.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run with **JDK 17+**, no external libraries required:

~~~bash
javac -encoding UTF-8 GracefulTcpShutdownDemo.java
java GracefulTcpShutdownDemo
~~~

Stdout verified with JDK 17 JShell:

~~~text
in-flight: 1
accepting: stopped
still processing: true
reply: ACK:ping
workers: terminated
~~~

### 8.1. Line-by-Line Explanation

- **`in-flight: 1`**: an accepted socket has had its `ping` request read by a worker and begun processing. `CountDownLatch` confirms the state, instead of calling `Thread.sleep(...)` and hoping the worker has started.
- **`accepting: stopped`**: the shutdown coordinator set the flag, closed the listening socket, and waited for the acceptor to exit. Existing accepted sockets are not closed merely because the listener closed.
- **`still processing: true`**: `workers.shutdown()` has been called, yet the worker is still waiting on the latch; `awaitTermination(100 ms)` returns `false`, proving **shutdown neither waits by itself nor interrupts a running task**.
- **`reply: ACK:ping`**: after releasing `mayFinish`, the worker sends the response per the line protocol, flushes, and closes the client socket. The client receives the result before the system asserts that draining is complete.
- **`workers: terminated`**: the worker pool has no running/queued tasks left after the wait deadline. **Only at this point** can we assert that the executor has terminated.

### 8.2. Why Use `CompletableFuture` and `CountDownLatch`?

To make the output independent of scheduler timing. `CountDownLatch started` ensures the request **is in progress** before stopping the listener; `mayFinish` holds the request open to test `awaitTermination`; `handlerDone` propagates worker errors to `main` instead of swallowing them silently in the thread pool; `acceptDone` records whether the acceptor exited or failed.

In production code, **do not create a static pair of latches for all requests**. Use a lifecycle coordinator, active-task counters, structured concurrency/managed executors where appropriate, per-request futures, and durable job IDs. The latches here are an **ordering test tool**, not a pattern for a real multi-client server.

### 8.3. Why Not Call `shutdownNow` Immediately?

If you call `shutdownNow()` right after receiving a request, it may interrupt the worker waiting on the latch. The client will **never receive an ACK**; that is precisely the failure graceful shutdown aims to avoid. In the demo, `shutdownNow()` is only in the **`finally` block for safe cleanup on exception**, after the normal success path has already terminated the pool. Production code needs two phases: `shutdown/await` first, then `shutdownNow/await` after the deadline expires.

### 8.4. Limitations of the Demo

- This is a single-request line protocol, not an HTTP/1.1/WebSocket/gRPC server.
- It binds only to loopback and uses a single client; there is no TLS/authz, quotas, or multiple persistent sockets.
- A 2-thread fixed pool has an **unbounded queue** via `Executors.newFixedThreadPool`; do not use this pattern as-is when a service receives high volumes of untrusted requests.
- `Socket.setSoTimeout(3000)` bounds blocking reads; it **is not an overall request deadline** and does not bound all outbound writes.
- The demo does not persist requests to a durable store; if the process is forcibly killed, an in-flight task may be lost.
- Do not treat `SocketException` after `listener.close()` as a "network failure" when it is an intentional shutdown; however, an unexpected `SocketException` while `RUNNING` still needs logging/alerting.
- Both `awaitTermination` and `acceptDone.get` have timeouts so they do not wait forever; when a task/callback fails, the code detects and reports it to `main`.

## 9. What If You Are Using JDK `HttpServer` Instead of TCP `ServerSocket`?

`com.sun.net.httpserver.HttpServer` provides the `stop(int delay)` method. Per the Java 17 API:

> `stop(delay)` closes the listening socket, prevents the server from processing new exchanges, and then **blocks the caller** until all active exchange handlers have finished **or approximately `delay` seconds have elapsed**, whichever comes first. Afterward, any remaining open TCP connections are closed. A stopped `HttpServer` **cannot be started again**.

**Illustrative snippet**:

~~~java
// assumes server is already started and pool is an application-owned executor
server.stop(10);     // delay is in SECONDS, not milliseconds.
pool.shutdown();     // the pool has its own lifecycle.
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        pool.awaitTermination(2, TimeUnit.SECONDS);
    }
} catch (InterruptedException interrupted) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This is not a standalone method; it requires `server`/`pool` variables and the `TimeUnit` import. Key points to remember:

1. `HttpServer.stop(delay)` **manages the JDK HTTP server's listening socket and exchanges internally**; you do not need to access the underlying `ServerSocket`.
2. `delay` **is a maximum wait in seconds** (after which TCP connections are closed), not a "fixed sleep" and not milliseconds. `stop(0)` may cut off running exchanges immediately.
3. `stop` can block the calling thread. Call it from a shutdown coordinator, **not** from a handler inside the same server, which would deadlock waiting on itself.
4. If you supply a custom `ExecutorService` via `server.setExecutor(pool)`, you must **shut down the pool separately** once the server is no longer dispatching work, or according to your designed lifecycle.
5. `HttpServer.stop` does not automatically wait for **detached asynchronous jobs** that a handler spawned and returned from earlier; track such futures/jobs separately if needed.
6. If a server handler can process an unbounded stream, `stop(delay)` cannot promise every response finishes within the deadline; connections may be cut after the deadline.
7. An `HttpServer` that has been `stop`ped cannot have `start()` called again; restarting requires creating a new instance.

### 9.1. HTTP Responses During the Drain Window

A handler that has already accepted a request should try to **send a valid response**, close the `HttpExchange`, output stream, and dependencies before the deadline. If returning a fixed-length response body, write all bytes; if chunked, close the stream to finish. Do not return `200 OK` if the transaction has not actually completed per contract. If the service is already `DRAINING` and a request arrives, you may return `503 Service Unavailable` with an appropriate `Retry-After` **before committing**, depending on the server/API; do not assume 503 can be sent in every shutdown case because the socket may already be closed.

### 9.2. HTTP Keep-Alive and HTTP/2

An HTTP/1.1 keep-alive TCP connection can carry multiple requests; do not treat "TCP already accepted" as "allow unlimited new requests after cutoff." Web frameworks/proxies must coordinate draining persistent connections. With HTTP/2, mechanisms such as GOAWAY may be supported by the implementation to stop accepting new streams while existing streams continue, but **do not assume the simple JDK `HttpServer` supports HTTP/2/GOAWAY out of the box**. Rely on your actual runtime.

### 9.3. WebSocket/SSE Require Their Own Policy

WebSocket and SSE are long-lived sessions/streams that can run for hours. You cannot simply "wait until every connection closes on its own" before deploying. Send an application signal such as `server-draining` or a WebSocket Close frame (for example, code `1001 Going Away` where appropriate), set a deadline for clients to reconnect/resubscribe, and persist sequences/cursors and durable state for resumption. For SSE, clients may need to reconnect to another node and use event IDs if the server supports them. Closing a connection does not automatically guarantee a message was business-ACKed.

## 10. Shutdown Hook, SIGTERM, and Process Exit Ordering

In Java:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            // Call a single idempotent shutdown coordinator.
            // Do not block indefinitely.
            service.requestShutdown();
        }, "shutdown-hook"));
~~~

This is **illustrative code**; `service` represents an application object with a `requestShutdown` method. A shutdown hook typically runs when the JVM begins an orderly shutdown (such as `System.exit` or a termination signal handled by the JVM/OS), but **is not guaranteed to run when the process is forcibly killed**, the OS crashes, or `Runtime.halt` is called.

### 10.1. Multiple Shutdown Hooks Have No Automatic Ordering

If the application, metrics library, database, and broker each register their own hook, **there is no guarantee they will run sequentially in the order you want**. Hooks may run concurrently during shutdown. For example, a DB pool hook closing before another hook's request handlers finish will cause failures. Use **one lifecycle coordinator** or framework lifecycle that manages the **dependency graph** and termination, rather than relying on luck with hook ordering.

### 10.2. Do Not Call `System.exit` from a Handler to "Stop Gracefully"

An HTTP handler calling `System.exit(0)` immediately upon receiving an admin request can terminate the process while other requests are in-flight. If a control endpoint is needed, it should ask the lifecycle coordinator to transition to draining, return an acknowledgment with clear semantics, and let the coordinator execute shutdown within the deadline. Protect admin endpoints with authentication/authorization and auditing; prevent unauthorized callers from stopping the service.

### 10.3. Signals and Orchestrators

- **SIGTERM** typically indicates a graceful termination request in Unix-like environments; a Java shutdown hook can be used if the runtime is configured properly.
- **SIGKILL** cannot be caught by a Java hook; no cleanup logic runs on a forced kill.
- In containers, the termination grace period is the **total budget** before a forced kill may occur; coordinate readiness, load balancer drain, and internal shutdown time.
- Do not assume OSes/Windows handle signals identically. Test in the real deployment environment.
- Services must have **durable recovery** in case of power loss or a kill with no chance to run shutdown.

## 11. Fault Tolerance: Completing a Request Does Not Mean No Duplicates

A tricky scenario:

~~~text
Client --> POST createOrder(id=77) --> Server
Server --> DB COMMIT succeeds
Server --> sends 201 Created
         X process killed / network lost before client receives response
Client --> retry POST ?
~~~

The client does not know whether the server committed or not. Graceful shutdown can try to send the response, but it does not create an **end-to-end exactly-once** guarantee. For operations with side effects:

- Use a stable **idempotency key** for the same operation when the API supports it.
- Have the server store the processed result keyed by request ID/transaction ID.
- If needed, provide a **status query** endpoint for the client before retrying.
- Database transactions require atomicity and proper cleanup.
- For queues/brokers, commit/ACK and side effects must have a consistency strategy (outbox/inbox, idempotent consumer, or transactions depending on the system).
- After a forced shutdown, data may be in an "unknown" state from the client's perspective; you must **reconcile**, rather than blindly reporting failure or retrying forever.

### 11.1. Message Queue: When to ACK?

Suppose a consumer receives a message, performs a DB update, and ACKs the broker. If it ACKs **before** the DB commit, a crash can lose work. If the DB commits **before** the ACK and then crashes, the broker may redeliver and the DB update runs again. You need an **idempotent handler**, unique constraints, and transactions/outbox/inbox as required to tolerate both directions. A clean consumer shutdown stops polling, drains in-flight work, commits/ACKs what succeeded, and closes the consumer/producer per contract; do not claim "zero messages lost" based solely on `awaitTermination`.

### 11.2. Long-Running Jobs Need Checkpoints

A 2-hour job cannot always finish within a 30-second shutdown grace period. Break it into checkpoints, persist the offset/phase/task ID, and allow a new worker to resume safely. On shutdown, stop accepting new jobs, ask the current job to checkpoint within the deadline, and release leases/locks appropriately. Do not pretend draining is complete just because the thread was interrupted while job state was never saved.

## 12. Observability/Metrics: Knowing Whether You Have Actually Stopped

Useful metrics and logs:

| Signal | What to Track |
| --- | --- |
| `shutdown_state` | RUNNING / DRAINING / STOPPING / STOPPED |
| `readiness` | 0 as soon as new work intake stops |
| `active_requests` / `in_flight_tasks` | Number of tasks actively being processed |
| `queued_tasks` | Number of accepted tasks waiting in the executor |
| `active_connections` | Open sockets/WebSocket/SSE connections |
| `drain_duration_seconds` | Time from cutoff until in-flight work completes |
| `forced_shutdown_count` | Number of times `shutdownNow` or forced socket close was needed |
| `unfinished_tasks` | Tasks remaining or abandoned due to deadline |
| `last_acknowledged_id` | Last cursor/transaction ID committed per policy |
| `response_abort_count` | Responses lost/truncated when connections closed |
| `queue_redeliveries` | Is there a spike after restart? |
| `executor_termination_time` | Were any threads uncooperative during shutdown? |

Log `shutdown_requested`, `admission_closed`, `drain_started`, `drain_completed`/`drain_timeout`, and `dependencies_closed` events, along with remaining deadline and correlation IDs without exposing secrets. Do not log bearer tokens, cookies, bodies containing PII, or credentials.

### 12.1. Readiness Is Different from Liveness

During `DRAINING`, a service may still be **alive and actively finishing requests**, yet should not receive new traffic:

~~~text
/readiness -> FAIL (do not route new requests)
/liveness  -> OK   (process is not wedged; intentionally draining)
~~~

If you fail liveness as soon as draining starts, the orchestrator may restart/kill the process before tasks finish. Exact probe configuration depends on the platform, but **separating the purpose of the two probes** is crucial.

## 13. Common Mistakes When Stopping a Java Server

| Mistake | Symptom | How to Fix |
| --- | --- | --- |
| `System.exit(0)` immediately on signal | Requests cut off mid-flight | Use a lifecycle coordinator and deadline |
| `workers.shutdown()` while still calling `accept()` | Connections accepted then rejected; clients may hang | Stop listener/admission first |
| Calling `awaitTermination` without `shutdown` | Pool may keep accepting work and never terminate | `shutdown` first, `awaitTermination` second |
| Assuming `shutdown()` waits for completion | DB/metrics close while workers are running | Wait on `awaitTermination`/active count |
| Calling `shutdownNow()` immediately on every deploy | In-flight work loses ACK/response | Two-phase graceful then forced |
| Assuming `shutdownNow` stops every thread immediately | Workers remain blocked; process does not exit | Cooperative interrupts, close sockets/deadlines |
| Closing accepted sockets along with the listener | In-flight requests reset | Close listening socket first; drain accepted sockets |
| Treating intentional `SocketException` from `accept()` as a system error | Log spam, false alerts | Check stopping state |
| Ignoring the accept/submit race | Socket leaks or rejected tasks | Check state and catch rejection, close socket |
| Unbounded queue | Shutdown takes too long; OOM before shutdown | Bounded queue/admission while RUNNING |
| Closing DB/broker before handlers commit | Failed transactions, missed ACKs | Follow dependency order |
| Waiting indefinitely on streams/WebSockets | Deploys cannot finish | Drain signal, close deadline, resume |
| Giving every step its own 30s wait | 150s total exceeds grace period | Overall deadline and remaining budget |
| Relying only on shutdown hooks | SIGKILL/power loss loses data | Durable state/idempotency |
| Assuming hooks run sequentially | DB hook closes early | Single ordered coordinator |
| Returning success as soon as a task enters the executor queue | Task is not yet durable | ACK after commit or explicit accepted semantics |
| Confusing client/server timeouts | Risk of duplicate side-effect retries | Idempotency, status lookup, and deadlines |
| Not shutting down schedulers | Jobs keep creating new tasks while pool drains | Stop periodic triggers first |
| Closing logs/tracing before draining | Missing final error logs | Flush after handlers, with a budget |
| Treating `isShutdown` as `isTerminated` | Falsely reports service stopped | Check terminated state and active resources |
| Testing with arbitrary sleeps | Flaky/does not prove ordering | Use latches/barriers, mock timers, and in-flight counters |
| Restarting a stopped `HttpServer` | Does not work | Create a new server instance |

## 14. Scenario Exercises with Answers

### Exercise A — Stopping the TCP Listener While a Client Is Still Processing

A service has one worker reading a request and an accept thread waiting for new connections. During a deploy, should you close all accepted `Socket`s immediately?

**Answer:** No, if you want graceful draining. First stop accepting new connections with `listener.close()`, using a flag to handle the race; then let the current accepted request finish within the deadline, send its response, and close that socket. Once the deadline expires, you may force-close per policy.

### Exercise B — Calling `shutdown()` Then Closing the Database

Code:

~~~java
workers.shutdown();
dbPool.close();
~~~

**Answer:** Likely buggy. `shutdown()` only stops accepting new tasks; it **does not wait for running or queued tasks to finish**. If they still use the DB, closing the pool early causes errors. Wait for termination/draining to finish before closing dependencies.

### Exercise C — `shutdownNow()` Returns 12 Runnables

A team calls `shutdownNow()` after the deadline and receives a `List<Runnable>` of 12 tasks. Does that mean those 12 tasks finished or are guaranteed to roll back?

**Answer:** No. The list represents **unstarted** tasks removed from the queue; it does not automatically persist or requeue them. Already-running tasks were only requested to interrupt and may still be executing. You need task IDs/durable state to handle unfinished work.

### Exercise D — JDK `HttpServer` `stop(10)`

An HTTP request takes 30s. `server.stop(10)` is called in the shutdown coordinator. Will the server wait exactly 10s and guarantee the request succeeds?

**Answer:** No. `stop(10)` waits until active handlers finish **or approximately 10s** (whichever comes first), then closes remaining TCP connections. A 30s request may be cut off. `delay` is in seconds, and the server object cannot be restarted.

### Exercise E — Worker Ignores Interrupts

A worker is blocked indefinitely in a socket read. After `shutdownNow`, the pool does not terminate and `awaitTermination` returns false.

**Answer:** Do not call `shutdownNow` in an infinite loop. Design upfront with read timeouts, socket closing, cancel-aware I/O, and bounded work; at the deadline, close tracked active sockets and record forced aborts/recovery. `Thread.stop` is not a safe solution.

### Exercise F — Queue Consumer ACKs Too Early

A consumer ACKs a message right after placing work into a volatile executor queue; before the worker commits to the DB, the JVM is killed.

**Answer:** The message can be lost because the broker believes it was processed. ACK based on durable outcomes, or design inbox/outbox/idempotency. Graceful shutdown cannot save a process killed before hooks can run.

### Exercise G — Rolling Deploy and Readiness

The application switches to `DRAINING`, yet the load balancer still routes new requests for a few seconds. Is an application-level mechanism still needed?

**Answer:** Yes. Readiness propagation is not instantaneous; add an admission guard, configure proxy/LB draining, and account for persistent connections and request races. Do not shut down the executor before ingress has truly stopped.

### Exercise H — WebSockets Open for Hours

A service has 10,000 WebSocket sessions. The shutdown target is 20s. Can you `awaitTermination` indefinitely for every session to close naturally?

**Answer:** No. Send a server-draining notice, apply an appropriate close/redirect/reconnect policy, persist cursors/subscriptions to a durable store or let clients resubscribe, and enforce a deadline with metrics-tracked forced cleanup.

### Exercise I — Four Steps, 15s Each

A Pod has a 30s grace period; the code waits 15s for the listener, 15s for tasks, 15s for the DB, and 15s for tracing.

**Answer:** The cumulative max budget is 60s, exceeding 30s, so the process may be force-killed before flushing. Use an **overall deadline of 30s or shorter with headroom**, and pass **remaining time** to each step.

### Exercise J — 200 OK Not Received by Client

The server commits an order and sends 200, the connection drops during shutdown, and the client never receives the response and retries the POST.

**Answer:** Risk of duplicate orders even though the server already committed. Use an idempotency key/unique operation ID or status lookup; graceful waiting does not provide exactly-once across all network failures.

### Exercise K — Unpredictable Hook Ordering

A DB framework registers its own shutdown hook; the service also registers a hook to wait for workers. Can you rely on the service hook always running before the DB hook?

**Answer:** Do not rely on it. The JVM does not guarantee sequential ordering across hooks; use a lifecycle coordinator or a framework with dependency ordering.

### Exercise L — `isShutdown` True and `isTerminated` False

After `pool.shutdown()`, you observe `isShutdown()==true` but `isTerminated()==false`.

**Answer:** This is a normal state: new tasks are rejected, but running/queued tasks remain. Continue with `awaitTermination` under a deadline and escalate if needed; do not report `STOPPED`.

### Exercise M — Closing DB Before Broker Producer

Workers finish processing an event, publish the result via a broker, and then update the DB. If shutdown closes the broker producer before workers drain, what fails?

**Answer:** Workers have nowhere to publish, so business steps fail to complete. Close order must follow the work's actual dependencies (publishing before/or after DB per contract/outbox), and both resources must remain available until work stops using them.

### Exercise N — Using `Thread.sleep` to Assume Draining Is Done

After a shutdown signal, `main` calls `Thread.sleep(5000)` and kills the process without measuring active requests.

**Answer:** Sleeping proves nothing about task state; the server might drain in 1s or still have a 20s request running. Use futures, `awaitTermination`, active counts, sockets/tracing, and bounded deadlines.

## 15. Checklist Before Implementing Graceful Shutdown

- [ ] Are `RUNNING -> DRAINING -> STOPPING -> STOPPED` states clear and protected against duplicate shutdowns?
- [ ] Does readiness switch to **not ready** before new traffic routing stops?
- [ ] Have listeners been closed, polling/schedulers stopped, and an application-level admission guard added?
- [ ] Are `accept`/`execute` races and `RejectedExecutionException` handled without leaking sockets?
- [ ] Is the drain scope defined: **running tasks**, **queued tasks**, active streams, delayed jobs?
- [ ] Is there an **overall deadline** with reserved time for closing and telemetry before a forced kill?
- [ ] Do you use `shutdown()` then `awaitTermination(...)`, without confusing `isShutdown` with `isTerminated`?
- [ ] Is `shutdownNow()` called only after the grace window expires, with unfinished work recorded?
- [ ] Do workers support interrupts/deadlines/cancellation and close sockets when needed?
- [ ] Are active sockets/request counters tracked and handler outcomes observed?
- [ ] Do DB/broker/HTTP clients stay alive until tasks finish using them?
- [ ] Are response/ACK/commit semantics and **idempotency keys** in place for requests with side effects?
- [ ] Are queue message ACKs/offset commits correct, and do durable jobs have checkpoints/recovery?
- [ ] Do WebSocket/SSE connections have close/draining signals and a reconnect/resubscribe policy?
- [ ] Do you avoid relying solely on shutdown hooks for data safety under `SIGKILL`?
- [ ] Do you emit metrics/logs: drain duration, active requests, queue size, forced aborts, unfinished IDs?
- [ ] Have you tested service shutdown with 0, 1, and multiple running requests, plus task failures/interrupts?
- [ ] Have you tested rapid repeated termination signals, listener-close races, executor rejections, and timeouts?
- [ ] Have you tested rolling deploys, readiness propagation, proxy keep-alive, pod grace periods, and slow clients?
- [ ] After shutdown, have all threads/file descriptors/sockets/pools terminated with no leaks?

**Conclusion:** In Java networking, stopping a service properly is not **"close everything as fast as possible"**, but rather **"lock the door first, finish serving current guests within a finite budget, and then shut down dependent systems in order"**. `ServerSocket.close()` stops `accept` without killing accepted sockets; `ExecutorService.shutdown()` blocks new tasks without waiting; `awaitTermination` waits with a bound; `shutdownNow` is only best-effort cancellation; `HttpServer.stop(delay)` is its own mechanism bounded in seconds. Recovering from deadlines or kills requires **durable state, idempotency, and observable outcomes**, not just shutdown hooks.

## 16. Official Documentation

- **Oracle Java 17 — ExecutorService:** `shutdown`, `awaitTermination`, `shutdownNow`, and the two-phase shutdown pattern. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Oracle Java 17 — ServerSocket:** `close()` causes a blocked `accept()` to throw `SocketException`. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- **Oracle Java 17 — Socket:** lifecycle/`setSoTimeout` for accepted connections. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- **Oracle Java 17 — HttpServer:** `stop(delay)`, `setExecutor`, `start()`. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- **Oracle Java 17 — ScheduledThreadPoolExecutor:** shutdown policies for delayed/periodic tasks. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
- **Oracle Java 17 — Runtime.addShutdownHook:** JVM lifecycle and shutdown hook limitations. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- **RFC 9110 — HTTP Semantics:** 503 status, retry, and response semantics. https://www.rfc-editor.org/rfc/rfc9110

For a real system, also consult your runtime/proxy/queue/broker documentation and **test shutdown under real load**, because whether clients receive responses or the server preserves durable side effects depends on the entire path and application architecture.