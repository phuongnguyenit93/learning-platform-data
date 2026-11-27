# Deadline of a server stream

## 1. What duration does a deadline bound?

In the **SPRING_GRPC** module, we build gRPC services using Protocol Buffers contracts, generate Java code, and integrate clients/servers with Spring. When learning **Server streaming**, the client sends one request and then receives multiple responses over time. The stream may return a long list, progress updates, or continuous event notifications. Such an RPC risks holding connections, buffers, and server tasks for too long without a time bound.

**Deadline** is the latest point in time an RPC is allowed to continue before being considered expired. In gRPC Java, clients typically set a deadline using `withDeadlineAfter(...)` before invoking the RPC. This time limit applies to the **entire call**, from the moment the RPC starts until it finishes, and is **not reset after each response**.

Example of a client opening a progress-watching stream with a 5-second deadline:

~~~text
Time:         0s       1s       2s       3s       4s       5s
              |--------|--------|--------|--------|--------|
Client:       WatchProgress(request)
Server:                #1       #2                #3
                                                   |
Deadline:                                              X
Client:       onNext   onNext   onNext       ...    onError(DEADLINE_EXCEEDED)
~~~

This is an illustrative diagram: exact message timing depends on the system. Even if the server has already sent several messages and is still capable of sending more, when the RPC deadline expires the client typically receives status `DEADLINE_EXCEEDED`; the server must stop work dedicated to that watch session.

**Key point:** a deadline is not the maximum interval *between two messages*. With a 5-second deadline, receiving a response every 1 second does not reset the clock back to 5 seconds.

After this lesson, learners should be able to:

- Set deadlines on blocking and asynchronous gRPC Java stubs.
- Distinguish RPC deadlines, per-message wait timeouts, cancellation, and business-defined time limits.
- Understand how gRPC propagates the time budget to the server and downstream calls.
- Handle expired streams on the client and stop producers on the Spring gRPC server.
- Design retry/reconnect, testing, and monitoring when long RPCs may return partial data.

## 2. Differences between deadline, timeout, idle timeout, and cancellation

| Concept | Scope | Example | Behavior when triggered |
|---|---|---|---|
| **RPC deadline** | One entire RPC, measured from start until outcome | `withDeadlineAfter(5, SECONDS)` | Runtime cancels expired RPC; client usually sees `DEADLINE_EXCEEDED` |
| **Per-message wait timeout** | Waiting interval for the next message | App requires at least one event every 10 seconds | Must design a custom timer/monitor; not synonymous with gRPC deadline |
| **Connection/proxy idle timeout** | Connection or stream idle per infrastructure policy | Load balancer closes connections without traffic for too long | Can produce transport errors like `UNAVAILABLE` or lead to cancellation |
| **Proactive cancellation** | Client decides to stop an open RPC | User closes the watch screen | Client calls cancel API; server cleans up resources |
| **Business time limit** | Task or processing session independent of connection | Job must complete within 30 minutes | Business logic decides fail, retry, status update, or continuation |

A report-export job may run for 15 minutes while each `WatchProgress` session lasts only 30 seconds before reconnecting. Thus, **job lifetime** and **job-watching RPC lifetime** are two independent concepts. A `WatchProgress` deadline does not automatically cancel the background job unless the system explicitly binds that behavior in business logic.

For example, if the user stops watching progress at second 3 of an RPC with a 10-second deadline: the client should **cancel immediately** rather than waiting until second 10. Conversely, a client wishing to watch for several minutes needs a reconnect policy, appropriate deadlines, and a recoverable event source.

## 3. Illustrative Protocol Buffers contract

We use a server streaming method for watching progress:

~~~proto
syntax = "proto3";

package jobs.v1;

option java_multiple_files = true;
option java_package = "com.example.jobs.rpc";
option java_outer_classname = "JobProgressProto";

service JobProgressService {
  rpc WatchProgress(WatchProgressRequest) returns (stream ProgressEvent);
}

message WatchProgressRequest {
  string job_id = 1;
  int32 max_updates = 2; // Small limit for finite example only.
}

message ProgressEvent {
  string job_id = 1;
  int64 sequence = 2;
  int32 percent = 3;
  string detail = 4;
}
~~~

`returns (stream ProgressEvent)` means the client sends one `WatchProgressRequest`, while the server can call `onNext` multiple times. After running `protoc` and the `protoc-gen-grpc-java` plugin, the project has Java classes such as `WatchProgressRequest`, `ProgressEvent`, and `JobProgressServiceGrpc`.

**A deadline is not a mandatory field in protobuf.** gRPC clients transmit timing budgets via the RPC-level deadline/timeout mechanism. Do not add a custom `deadline_ms` field to messages merely to replace standard deadlines, unless the business contract genuinely requires an independent time parameter.

The `sequence` field helps the client recognize already-processed progress and detect duplicates/gaps when reconnecting. However, gRPC itself does not store history or replay lost responses. Resuming requires designing a cursor API and durable storage.

## 4. Java client setting a deadline on a blocking stub

A server streaming blocking stub returns `Iterator<ProgressEvent>`. The client can read each message via `hasNext()` and `next()`; these operations can block the thread while waiting for the next payload. The deadline applies while waiting on the iterator as well.

~~~java
package com.example.jobs.client;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public final class BlockingDeadlineClient {

    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext() // Use only in trusted dev environments.
                .build();

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("report-42")
                    .setMaxUpdates(20)
                    .build();

            // Create a stub with a deadline right before making this RPC.
            var stub = JobProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(3, TimeUnit.SECONDS);

            Iterator<ProgressEvent> updates = stub.watchProgress(request);

            while (updates.hasNext()) {
                ProgressEvent update = updates.next();
                System.out.printf("event=%d, progress=%d%%%n",
                        update.getSequence(), update.getPercent());
            }

            System.out.println("RPC completed successfully");
        } catch (StatusRuntimeException error) {
            Status status = error.getStatus();
            if (status.getCode() == Status.Code.DEADLINE_EXCEEDED) {
                System.err.println("WatchProgress exceeded its deadline");
            } else {
                System.err.println("WatchProgress failed: " + status);
            }
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

In this example, the server may send several messages before the client hits `DEADLINE_EXCEEDED`. The client prints `RPC completed successfully` only if the iterator finishes normally. **Receiving a few responses does not mean the entire RPC succeeded**.

`withDeadlineAfter(3, TimeUnit.SECONDS)` returns **a new stub** with a relative duration converted into a deadline at configuration time. Do not create a stub with a short deadline early on and reuse it across many RPCs over a long period: later calls could start with an already-expired deadline. Typically, create the deadline-configured stub right before each call and reuse the `ManagedChannel`.

Port `9090` is an example; use your project's actual Spring gRPC server port. `usePlaintext()` is unsuitable for production environments that must be protected with TLS.

## 5. Async client: processing data before the deadline and handling expiration

With the asynchronous stub, `watchProgress(...)` returns control immediately and the client receives data through `StreamObserver<ProgressEvent>`:

~~~java
import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

// channel is a ManagedChannel already created and managed externally.
WatchProgressRequest request = WatchProgressRequest.newBuilder()
        .setJobId("report-42")
        .setMaxUpdates(20)
        .build();

CompletableFuture<Void> done = new CompletableFuture<>();

JobProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS)
        .watchProgress(request, new StreamObserver<ProgressEvent>() {
            @Override
            public void onNext(ProgressEvent event) {
                System.out.println("Progress " + event.getPercent() + "%");
            }

            @Override
            public void onError(Throwable error) {
                System.err.println("Terminal status: "
                        + Status.fromThrowable(error));
                done.completeExceptionally(error);
            }

            @Override
            public void onCompleted() {
                done.complete(null);
            }
        });

// Synchronous waiting is only for console or test illustration.
// Do not block an event-loop/request thread in a web application.
try {
    done.get(5, TimeUnit.SECONDS);
} catch (java.util.concurrent.ExecutionException error) {
    System.err.println("RPC did not complete successfully");
} catch (java.util.concurrent.TimeoutException error) {
    System.err.println("Local wait timed out");
}
~~~

There are **two distinct timers** here:

- `withDeadlineAfter(3, SECONDS)` is the deadline of the **gRPC RPC**. Upon expiration, the runtime usually invokes `onError` with `DEADLINE_EXCEEDED`.
- `done.get(5, SECONDS)` is the **wait limit of the Java code**. If it expires, only the `get` call throws `TimeoutException`; this **does not automatically cancel the RPC**. To stop the RPC, invoke the appropriate cancellation API.

In async systems you can use `ClientResponseObserver`, save the `ClientCallStreamObserver` from `beforeStart`, and call `cancel(...)` when the user no longer needs data or when client processing fails. Do not call `onError` on the client's own observer as a cancel command.

### A deadline is not a measure of "how long since the last message"

Suppose the client sets a 60-second deadline to watch events. The server steadily sends one message every 2 seconds. At second 60, the RPC can still expire even though the last message just arrived at second 58.

If the requirement is **"if no new event arrives within 15 seconds, alert or reconnect"**, add an application-level **idle-message timer**. This timer resets whenever a valid event arrives, unlike a gRPC deadline which bounds the overall lifetime of the RPC.

## 6. How does a deadline travel from client to server?

gRPC supports propagating time budgets at the RPC level. When a client sets a deadline, the runtime can propagate the **remaining** time to the server via gRPC control metadata (in HTTP/2, the `grpc-timeout` header). This header is managed by the library; applications normally **must not manually create or alter** that reserved header.

Transmitting the remaining duration avoids depending strictly on client and server system clocks being perfectly synchronized. As the request traverses the network, proxies, or downstream calls, the remaining budget decreases.

On a Java server, you can inspect the deadline of the RPC context:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (deadline == null) {
    System.out.println("No deadline supplied to this RPC");
} else {
    long remainingMs = deadline.timeRemaining(TimeUnit.MILLISECONDS);
    System.out.println("Remaining RPC budget: " + remainingMs + " ms");
}
~~~

`deadline == null` means the current context has no deadline; never assume every client has supplied a time limit. `remainingMs` can be 0 or negative once the deadline has expired. Do not read the deadline once when the RPC opens and assume the remaining value stays constant throughout the stream.

When the RPC exceeds its deadline, the runtime marks/cancels the associated context. Server code can check:

~~~java
Context context = Context.current(); // Captured inside the RPC handling context.

if (context.isCancelled()) {
    // Stop reading the data source and release work for this RPC.
    return;
}
~~~

If work is dispatched to another executor, `Context.current()` called inside a worker thread may no longer be the original RPC's context without propagation. You can **capture** the context when receiving the request and check the captured object, or use gRPC `Context` executor/callback wrappers to propagate context properly.

**Client and server do not necessarily report the same status.** A client hitting a deadline usually sees `DEADLINE_EXCEEDED`, whereas the server usually observes RPC **cancellation** via context or `ServerCallStreamObserver`. The server must not wait to receive an `onError(DEADLINE_EXCEEDED)` event on its response observer before cleaning up.

## 7. Spring gRPC server must stop the producer when the RPC expires

The server's primary responsibility is to stop emitting responses, stop timers/subscriptions, and reclaim resources when the RPC is cancelled by a deadline or by the client. Do not treat deadlines as solely a client-side concern.

Example service emitting a simulated update every 250 ms. The task continues until all messages are sent or the RPC is cancelled. A scheduler is used so the RPC handling thread is not blocked while waiting for updates.

~~~java
package com.example.jobs;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class JobProgressServiceImpl
        extends JobProgressServiceGrpc.JobProgressServiceImplBase {

    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(4);

    @Override
    public void watchProgress(
            WatchProgressRequest request,
            StreamObserver<ProgressEvent> responseObserver) {

        String jobId = request.getJobId().trim();
        int limit = request.getMaxUpdates();

        if (jobId.isEmpty() || limit < 1 || limit > 20) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                    .withDescription("job_id required; max_updates must be 1..20")
                    .asRuntimeException());
            return;
        }

        ServerCallStreamObserver<ProgressEvent> out =
                (ServerCallStreamObserver<ProgressEvent>) responseObserver;
        Context rpcContext = Context.current(); // Capture before leaving RPC thread.

        Object gate = new Object();
        AtomicBoolean closed = new AtomicBoolean(false);
        AtomicInteger sent = new AtomicInteger(0);
        AtomicReference<ScheduledFuture<?>> taskRef = new AtomicReference<>();

        out.setOnCancelHandler(() -> {
            synchronized (gate) {
                closed.set(true);
            }
            cancel(taskRef.get());
            // Real apps must also unsubscribe from this RPC's progress source.
        });

        Runnable sendTick = () -> {
            synchronized (gate) {
                if (closed.get() || out.isCancelled()
                        || rpcContext.isCancelled()) {
                    closed.set(true);
                    cancel(taskRef.get());
                    return;
                }

                // Demo generates data at send time so it can skip a tick.
                // For real business events, retain/replay if loss is unacceptable.
                if (!out.isReady()) {
                    return;
                }

                try {
                    int step = sent.incrementAndGet();
                    ProgressEvent event = ProgressEvent.newBuilder()
                            .setJobId(jobId)
                            .setSequence(step)
                            .setPercent(step * 100 / limit)
                            .setDetail("Generated step " + step)
                            .build();

                    out.onNext(event);

                    if (step == limit) {
                        closed.set(true);
                        out.onCompleted();
                        cancel(taskRef.get());
                    }
                } catch (RuntimeException failure) {
                    if (!closed.get() && !out.isCancelled()
                            && !rpcContext.isCancelled()) {
                        closed.set(true);
                        try {
                            out.onError(Status.INTERNAL
                                    .withDescription("Cannot send progress")
                                    .asRuntimeException());
                        } finally {
                            cancel(taskRef.get());
                        }
                    } else {
                        closed.set(true);
                        cancel(taskRef.get());
                    }
                }
            }
        };

        ScheduledFuture<?> task = scheduler.scheduleWithFixedDelay(
                sendTick, 0, 250, TimeUnit.MILLISECONDS);
        taskRef.set(task);

        // Cancel may arrive before the future is stored into taskRef.
        if (closed.get()) {
            task.cancel(false);
        }
    }

    private static void cancel(ScheduledFuture<?> task) {
        if (task != null) {
            task.cancel(false);
        }
    }

    @PreDestroy
    public void shutdown() {
        scheduler.shutdownNow();
    }
}
~~~

In a Spring gRPC version that automatically registers Spring beans implementing `BindableService`, `@Service` enrolls the service in the gRPC server. With other starters or integration libraries, follow that library's service registration approach. Using `StreamObserver` and `Context` belongs to the gRPC Java API, independent of how beans are registered.

### Why do we need Context, a cancel handler, and a synchronization lock together?

1. **`rpcContext`** is captured right as the request is handled and retained so the scheduler task can check cancellation status even when running on another thread.
2. **`setOnCancelHandler`** stops the task when the runtime signals the RPC is cancelled, including proactive cancellations and typically deadline expirations.
3. **`gate`** coordinates event emission and the cancellation callback, preventing an `onNext` task from running concurrently with application-level cleanup.
4. **`closed`** is a terminal state flag preventing emissions after completion/cancellation and handling the race where cancellation occurs before the future is stored.
5. **`@PreDestroy`** stops the scheduler when the Spring context closes; a service must never spawn unbounded threads per subscriber.

Examples with schedulers, timers, or broker callbacks must design **idempotent cleanup**: invoking release multiple times remains safe. If the client has already cancelled, the server need not try to emit `onCompleted` or `onError` to an RPC already terminated on the receiver side.

### Role of backpressure

`ServerCallStreamObserver.isReady()` indicates the send path is ready to accept more data per the runtime; it does not confirm the client has finished applying the event. In the example, events are **generated fresh on each tick**, so skipping a tick when unready loses no events from an external source.

With real event sources, **do not drop events merely because `isReady() == false`**. You need bounded queues, upstream integration with backpressure, event storage for replay, or a latest-state policy documented in the contract. Backpressure and deadlines answer two different questions: whether the client can keep up, and how long the RPC is permitted to live.

## 8. Deadlines when the server calls another service downstream

Suppose `WatchProgress` on the Spring server must call a downstream RPC to fetch data. If upstream has 800 ms remaining, calling downstream with a 10-second timeout **does not grant upstream any extra time**. The parent call's deadline still expires after its remaining budget, regardless of whether the child service has finished.

A time budget is needed across the entire chain:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring gRPC service A
    participant B as gRPC service B
    C->>A: WatchProgress (deadline 3s)
    Note over A: Deadline/Context has ~2.6s left when handling
    A->>B: FetchStage (deadline does not exceed remaining budget)
    B-->>A: Stage response
    A-->>C: ProgressEvent
    Note over C,A: If total RPC exceeds 3s, client may receive DEADLINE_EXCEEDED
~~~

In gRPC Java, context and deadlines can be propagated to child calls when the **Context** is preserved; stubs can also be created with tighter deadlines. Do not assume the parent RPC's context automatically follows arbitrary workers/executors. Propagate context properly, verify deadlines are applied downstream, and keep a **small reserve budget** for remaining processing.

Principle example:

~~~java
// Executed inside the parent RPC's proper context, before downstream call.
Deadline incoming = Context.current().getDeadline();
if (incoming != null) {
    long remainMs = incoming.timeRemaining(TimeUnit.MILLISECONDS);
    long reserveMs = 100; // Illustrative time reserved for post-processing.

    if (remainMs <= reserveMs) {
        // Do not initiate a downstream call already nearly out of time.
        throw Status.DEADLINE_EXCEEDED
                .withDescription("Insufficient remaining deadline")
                .asRuntimeException();
    }

    var downstreamStub = downstreamBaseStub
            .withDeadlineAfter(remainMs - reserveMs, TimeUnit.MILLISECONDS);
    // Invoke downstream immediately with the new stub, inside the propagated context.
}
~~~

This is an illustrative snippet: `downstreamBaseStub` and the follow-up invocation are defined by the application. If an error must be handled inside the server streaming `StreamObserver`, convert budget exhaustion into **one** terminal `onError(Status.DEADLINE_EXCEEDED...)` (if the RPC is still active), stop the producer, and clean up. Never let an exception leak out of a scheduler thread and continue sending responses afterward.

## 9. Choosing deadlines for finite streams vs. long-lived watch streams

No single deadline fits every server streaming RPC. Start from business requirements and real metrics.

| Server streaming type | Goal | Selection guideline |
|---|---|---|
| Incrementally returning a small result set | Receive all data quickly with a clear end | Overall deadline based on target latency plus headroom |
| Large data-scanning query | Return processed chunks gradually | Deadline sufficient for scan; if very long, design cursor/resumable pagination |
| Watching progress of a multi-minute job | UI always has fresh info | Moderate watch session durations with checkpointed reconnect; job lives independently |
| Continuous events with no fixed end | Keep subscription while needed | Define session TTL/refresh, idle timeout, cancel, and reconnect; do not rely on a single infinite RPC |
| Potentially expensive stream | Bound open RPCs and resources | Reasonable deadline combined with buffer limits, quotas, and concurrent stream caps |

For example, a system targets 2-second UI responsiveness, while background jobs typically take 20 minutes. A unary `StartJob` RPC returning `job_id` quickly, followed by the client opening a streaming `WatchJob` with per-session deadlines of a few tens of seconds and contract-based reconnection, can be far easier to operate than holding one RPC open for 20 minutes. Numbers are illustrative design examples and must be measured on real infrastructure.

With **no deadline**, an RPC may stay alive for a very long time when the source emits no events and neither side closes; however, proxies, networks, and other timeouts can still terminate it. Thus, omitting a deadline is not a reliable way to guarantee a stream lives forever.

### When the client reads slowly

If a stream takes 2 seconds for the server to generate all messages, yet the client needs 12 seconds to process them sequentially, a 5-second deadline can still terminate the RPC before the application finishes. In gRPC Java, client-side manual inbound flow control such as `ClientResponseObserver` with `request(1)` regulates callback delivery rate, but **does not extend the deadline**.

If every event must be kept, you need durable storage and checkpoints. If the client persistently lags behind, choose batching, compression, producer throttling, smaller message sizes, or proactive termination and resume; merely increasing the deadline does not solve unbounded memory growth.

## 10. How do deadlines affect already-received data?

Suppose the client processed events with sequences 1, 2, 3 and then timed out:

~~~text
Server intended: #1 -> #2 -> #3 -> #4 -> #5 -> onCompleted()
Client sees:     #1 -> #2 -> #3 -> onError(DEADLINE_EXCEEDED)
~~~

Events 1–3 may already have produced side effects like database writes. **A deadline does not automatically roll back** work the client already performed; meanwhile, events 4–5 might never reach the client even if the server called `onNext`. The client must distinguish:

- **Observed progress:** events already read.
- **Processed and persisted progress:** events actually applied successfully.
- **RPC termination:** receiving `onCompleted`/`OK`, or receiving an error status like `DEADLINE_EXCEEDED`.

If business logic must process every event and avoid duplicates:

1. Server assigns sequences using stable rules and stores necessary history.
2. Client persists a checkpoint **only after successfully processing** an event.
3. API allows sending `after_sequence` when opening a new session; server guarantees reading the backlog and subscribing to live events without gaps.
4. Client deduplicates/remains idempotent when receiving previously processed events; checks for gaps if strict contiguous ordering is required.

This is **application-layer** design. gRPC does not automatically guarantee *exactly once processing* across retries/reconnects.

### Is retrying always appropriate after DEADLINE_EXCEEDED?

No. For read-only query RPCs and replayable cursor sources, controlled retries are usually feasible. However, if the request triggers a side effect, a client-side deadline **does not prove the server has not executed that side effect**. Blind retries can create duplicate actions. Write commands require idempotency keys, job state, and result-checking mechanisms before retrying.

When reconnecting to resume watching, verify whether the user still wants updates. If the user intentionally stopped watching, **do not** automatically start a new stream just upon seeing `CANCELLED`.

## 11. Testing deadlines with gRPC in-process

To test deadlines accurately, write tests that do not depend on how many events the scheduler and network happen to send before expiration. One approach is creating a test server stream that **stays open without sending responses**, then setting a short client deadline and verifying gRPC actually terminates the RPC.

JUnit 5 example using gRPC Java's in-process transport:

~~~java
import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class ServerStreamDeadlineTest {

    @Test
    void deadlineEndsOpenServerStreamAndCancelsServerCall()
            throws Exception {
        CountDownLatch serverCancelled = new CountDownLatch(1);
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new JobProgressServiceGrpc
                        .JobProgressServiceImplBase() {
                    @Override
                    public void watchProgress(
                            WatchProgressRequest request,
                            StreamObserver<ProgressEvent> observer) {
                        ServerCallStreamObserver<ProgressEvent> out =
                                (ServerCallStreamObserver<ProgressEvent>) observer;
                        out.setOnCancelHandler(serverCancelled::countDown);
                        // Intentionally send neither onNext nor onCompleted:
                        // The RPC ends solely due to the client deadline.
                    }
                })
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("report-42")
                    .setMaxUpdates(1)
                    .build();

            var stub = JobProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.watchProgress(request).hasNext());

            assertEquals(Status.Code.DEADLINE_EXCEEDED,
                    error.getStatus().getCode());
            assertTrue(serverCancelled.await(2, TimeUnit.SECONDS));
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test confirms the **client sees deadline exceeded** and the **server receives the cancellation event**. It does not verify the Spring context, interceptors, TLS, proxies, or cleanup of a real data source. When using an async server, add tests verifying timers, cursors, subscriptions, and buffers are released after deadline expiration.

Additional test scenarios to add:

| Test case | Expected result |
|---|---|
| Deadline longer than finite emission time | Client receives all events and `onCompleted` succeeds |
| Deadline shorter than total emission time | Client receives `DEADLINE_EXCEEDED`, possibly with partial data |
| Stream with steady messages before deadline | Still expires at total deadline, does not reset per event |
| Deadline expires before first response | No events received; server cleans up |
| Client cancels before deadline | Typically sees `CANCELLED`, does not wait for deadline |
| Cancel and completion occur close together | Only one valid outcome, safe cleanup |
| Slow producer and slow-reading client | Quotas/buffers stable, deadline respected |
| Downstream service call | Does not exceed remaining upstream budget; context propagates properly |
| Through real proxy/TLS | Deadlines and error codes observed properly under real network conditions |
| Retry after deadline | Deduplication/checkpointing works; no duplicate side effects |

With Spring gRPC, add integration tests that boot Spring Boot to verify service registration, metadata/interceptors, and endpoint configuration. Real network tests reveal effects of proxy idle timeouts, TLS, and disconnects; in-process does not simulate all those conditions.

## 12. Monitoring and security for streams with deadlines

Deadlines are a reliability safeguard, yet **observability** is needed to know whether they are configured appropriately. In the Spring gRPC ecosystem, interceptors, tracing, and metrics can record RPC duration, termination codes, response counts, and open stream counts.

| Metric to observe | Meaning |
|---|---|
| `DEADLINE_EXCEEDED` by method/client | Are streams routinely timing out, or is one client group setting overly short deadlines |
| `CANCELLED` and `UNAVAILABLE` | Distinguish proactive cancellation from transport failures |
| Actual RPC duration | Latency and stream duration distribution |
| Responses received before expiration | Assess how much data clients actually receive |
| Remaining deadline budget when server receives request | Detect long network, proxy, or downstream delays |
| Producers/timers still alive after call ends | Detect resource leaks |
| Queue depth, `isReady()`, concurrent stream count | Detect backpressure or overload beyond capacity |
| Reconnect counts, sequence gaps/duplicates | Verify reliability when using time-bounded sessions |

**Do not automatically assume every `DEADLINE_EXCEEDED` is a server bug.** Clients may choose overly short deadlines, networks may have high latency, clients may process responses slowly, or the system may be overloaded. Inspect metrics from both sides and diagnose root cause before adjusting limits.

Regarding security:

- Use **TLS** in production and verify server certificates; use mTLS if policy requires it.
- Use metadata/interceptors to authenticate and authorize per `job_id` or stream topic—do not rely on deadlines as an authorization mechanism.
- Limit concurrent streams, message sizes, and quotas per caller to prevent clients from holding many long-lived RPCs open.
- Do not log tokens or sensitive contents into deadline/status logs. gRPC control metadata should only be handled by compatible libraries and middleware.

## 13. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| "Deadline is a per-response timeout." | A gRPC deadline applies to the **entire RPC**; arriving messages do not reset the clock. |
| "Server is sending steadily so the stream cannot expire." | The stream can still time out at the exact configured deadline. |
| "`onNext` succeeding means the client saved the event." | This is not a business-level data processing ACK. |
| "`CompletableFuture.get(timeout)` automatically cancels gRPC." | It only bounds waiting in Java; to cancel the RPC, call cancel. |
| "When the deadline expires, the server calls `onCompleted` cleanly." | Server stops producer and cleans up; do not emit success for a cancelled RPC. |
| "Client reports `DEADLINE_EXCEEDED`, so server always reports the exact same." | The server usually observes context/RPC cancellation. |
| "Adding `deadline_ms` in protobuf is enough." | Standard gRPC deadlines are configured at the call/stub and transport layers. |
| "Setting a very long deadline solves a slow client." | Backpressure, bounded buffers, and quotas are still mandatory. |
| "Retrying after a deadline is always safe." | Can cause duplicate side effects without idempotency/cursors. |
| "A stub with a deadline configured upfront can be reused forever." | Deadlines are anchored to configuration time; configure close to call time. |

### Self-practice questions

1. With a 5-second deadline and a server emitting a response every second, does the stream automatically extend after each response?
2. How does `withDeadlineAfter(3, SECONDS)` differ from `future.get(3, SECONDS)`?
3. Why does the client see `DEADLINE_EXCEEDED` while the server may only receive cancellation?
4. When a server runs workers on another executor, why must gRPC `Context` be propagated/captured?
5. Why does the deadline of a job-watching stream not necessarily terminate the background job?
6. A client processed sequences 1–3 before timing out. What must be added to resume safely from 4?
7. If a proxy closes a stream due to idle timeout before the deadline, will the error necessarily be `DEADLINE_EXCEEDED`?
8. What measurements help distinguish an overly short deadline from an overloaded server?

**Key takeaway:** A server streaming deadline is a time limit **for the entire RPC**, set by the client at call time and observable by the server via gRPC `Context`. Deadlines do not reset after `onNext`, do not guarantee all emitted responses will be received, and do not replace flow control or proactive cancellation. In Spring gRPC, the server must stop producers and clean up when streams expire; clients must handle partial data, statuses, controlled retries, TLS security, and reliability monitoring.
