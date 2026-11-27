# Cancelling a stream mid-way

## 1. Why cancel a server streaming RPC?

In the **SPRING_GRPC** module, learners build gRPC services in the Spring ecosystem: defining **Protocol Buffers** contracts, generating Java code, implementing unary and streaming RPCs, and managing metadata, deadlines, statuses, interceptors, TLS, integration testing, and performance/reliability monitoring. In the **Server streaming** chapter, the client sends **one request** and the server returns **multiple responses** sequentially within a single RPC. This stream may remain active when the client no longer needs additional data.

Imagine a screen watching report generation progress. The user opens the screen to view updates—10%, 20%, 30%...—and navigates to another page when the report is only at 40%. If the client abandons the open RPC, the server could continue holding subscriptions, buffers, and data-emission tasks even though nobody needs the remaining updates.

**Mid-stream cancellation** is a request to terminate an active RPC before the server finishes on its own. Common scenarios:

- The user closes the screen, cancels the watch action, or changes filters.
- A parent task is cancelled, making dependent gRPC calls unnecessary.
- The client determines it already has enough data for its current decision.
- Client-side processing of a response fails and cannot safely continue.
- The client sets a deadline; once expired, the runtime terminates the RPC and the server must stop related work.

**Important distinction:** cancelling a **watch RPC** does not necessarily mean cancelling the **background business job**. For example, the user stops watching progress, yet the report export task still needs to run to completion. Whether to cancel the underlying job must be designed explicitly in the business contract.

## 2. RPC lifecycle: completion, error, cancellation, and deadline

Server streaming uses `StreamObserver<ResponseT>` callbacks to send responses:

- `onNext(response)`: sends one message; can be called multiple times while the RPC is active.
- `onCompleted()`: ends the stream successfully; the server sends no more responses.
- `onError(error)`: ends due to an error; sends no further messages or other terminal signals.

Client-initiated cancellation is **another termination path**. The server typically receives the cancellation signal from the gRPC runtime via `ServerCallStreamObserver` or `Context`, and then releases resources. The server **does not need and should not attempt** to call `onCompleted()` just to respond to a cancelled client.

~~~mermaid
stateDiagram-v2
    [*] --> Active: Client opens WatchProgress
    Active --> Active: Server onNext(response)
    Active --> Success: Server onCompleted()
    Active --> Error: Server onError(status)
    Active --> Cancelled: Client proactively cancels
    Active --> Deadline: Deadline expires
    Active --> Disconnected: Connection fails
    Success --> [*]
    Error --> [*]
    Cancelled --> [*]
    Deadline --> [*]
    Disconnected --> [*]
~~~

| Cause | Client typically observes | Server must do |
|---|---|---|
| Server sends all responses and closes normally | `onCompleted()` / `OK` status | Stop emitting, release resources |
| Server cannot handle request | `onError(...)`, e.g., `INVALID_ARGUMENT` | Return appropriate status, clean up resources |
| Client proactively cancels while RPC is open | Usually `onError` with `CANCELLED` | Stop sending, unsubscribe, cancel timers/buffers |
| Client deadline expires | Usually `DEADLINE_EXCEEDED` on client | Receive RPC cancellation signal and stop related work |
| Connection/transport lost | May see `UNAVAILABLE` or corresponding code | Clean up resources when runtime reports close/cancel |

Actual status codes depend on which side is observing, the cause, and event timing. For instance, a client might cancel right around the time the server completes; the final outcome could be success or cancellation depending on which event wins the race. Do not write logic assuming both sides always report the exact same code.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant G as Spring gRPC server
    participant P as Producer
    C->>G: WatchProgress(job_id)
    G->>P: Subscribe
    P-->>G: Progress 10%
    G-->>C: onNext(10%)
    P-->>G: Progress 40%
    G-->>C: onNext(40%)
    C-xG: cancel("User closed view")
    G->>P: Unsubscribe / stop timer
    Note over G: Emit no more to cancelled RPC
    Note over P: Background job may keep running
~~~

## 3. Defining Protocol Buffers for the hands-on exercise

Suppose a Spring gRPC service emits progress by job ID. File `src/main/proto/job_progress.proto`:

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
  int32 max_updates = 2;
}

message ProgressEvent {
  string job_id = 1;
  int64 sequence = 2;
  int32 percent = 3;
  string description = 4;
}
~~~

`returns (stream ProgressEvent)` declares **one request, multiple responses**. In the Java build, `protoc` and `protoc-gen-grpc-java` generate message classes, `JobProgressServiceGrpc.JobProgressServiceImplBase`, and client stubs. Protobuf plugin, gRPC Java, and Spring starter configurations must match the project version.

`max_updates` simply creates an easily observable **finite** stream for the example; assume valid values from 1 to 20. In real systems, the server typically subscribes to a data source by `job_id` and may emit progress until the job finishes. Cancellation capability is still needed even for finite RPCs.

## 4. Java client cancelling the stream via ClientCallStreamObserver

With the **asynchronous stub**, a gRPC Java client can use `ClientResponseObserver<RequestT, ResponseT>`. The `beforeStart(...)` method receives a `ClientCallStreamObserver<RequestT>` representing the current call. The client retains this object so it can invoke:

~~~java
call.cancel("User no longer needs progress updates", null);
~~~

This is the **real RPC cancellation** API in the gRPC runtime. It differs from calling `onError(...)` on the client's own observer, closing a UI window, or merely stopping UI updates. Those actions do not guarantee the server-side RPC is cancelled.

### 4.1. Example of a client cancelling itself after the third message

~~~java
package com.example.jobs.client;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class CancelProgressClient {

    public static void main(String[] args) throws InterruptedException {
        // Plaintext is for trusted development environments only.
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .build();

        CountDownLatch terminated = new CountDownLatch(1);

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("job-731")
                    .setMaxUpdates(10)
                    .build();

            JobProgressServiceGrpc.newStub(channel)
                    .withDeadlineAfter(20, TimeUnit.SECONDS)
                    .watchProgress(
                            request,
                            new ClientResponseObserver<WatchProgressRequest,
                                                       ProgressEvent>() {

                                private ClientCallStreamObserver<
                                        WatchProgressRequest> call;
                                private int received;

                                @Override
                                public void beforeStart(
                                        ClientCallStreamObserver<
                                                WatchProgressRequest> stream) {
                                    this.call = stream;
                                }

                                @Override
                                public void onNext(ProgressEvent event) {
                                    received++;
                                    System.out.printf("#%d progress=%d%%%n",
                                            event.getSequence(),
                                            event.getPercent());

                                    if (received == 3) {
                                        // Release the RPC when watching is no longer needed.
                                        call.cancel("Stopped watching progress", null);
                                    }
                                }

                                @Override
                                public void onError(Throwable error) {
                                    System.out.println(
                                            "RPC ended: " + Status.fromThrowable(error));
                                    terminated.countDown();
                                }

                                @Override
                                public void onCompleted() {
                                    System.out.println("RPC completed normally");
                                    terminated.countDown();
                                }
                            });

            if (!terminated.await(25, TimeUnit.SECONDS)) {
                System.err.println("No terminal callback observed in time");
            }
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

With a server emitting one response roughly every half second, the client receives messages 1, 2, and 3 and then calls `cancel`. Normally the client's `onError` callback observes status `CANCELLED`, and `onCompleted` does not fire. If the server happens to complete before cancellation takes effect, the client might observe `onCompleted`; the example sets a deadline and ten updates to reduce that likelihood.

**Code explanation:**

1. `beforeStart` is invoked by the runtime before the RPC begins receiving responses; the client saves `ClientCallStreamObserver` for **this specific RPC**.
2. `onNext` receives each `ProgressEvent` and increments the counter.
3. After the third message, the client calls `call.cancel(...)`. The runtime performs cancellation; the client sends no further protobuf requests.
4. `onError` is where termination via cancellation/error is observed; `onCompleted` is where normal completion is observed. The client should handle exactly **one** outcome according to whichever callback fires.
5. `CountDownLatch` only keeps the console program's channel alive until the terminal callback fires. Do not use `await` to block an event loop or request-handling thread in a Spring application.

`ClientCallStreamObserver.cancel(message, cause)` accepts an explanatory message and an optional cause. Do not put access tokens, sensitive user info, or confidential business data into the error string, as it may be logged.

### 4.2. Cancelling when the user leaves the screen

In a UI or a Spring service, cancellation should be tied to the **watcher object's lifecycle**. Example:

~~~text
Open progress page:
    - create WatchProgress RPC
    - store ClientCallStreamObserver handle of current call

Navigate away / click Stop watching:
    - retrieve active call handle
    - invoke cancel("view disposed", null) once per application policy
    - clear observer reference, release UI subscription

Receive onError / onCompleted:
    - update final state of watch session
    - do not auto-restart if user intentionally cancelled
~~~

Do not use `channel.shutdownNow()` as a routine way to cancel **one** RPC: a channel may be shared by many other calls. `shutdownNow()` is for when the application genuinely wants to shut down the channel and can disrupt other RPCs sharing it.

## 5. Server detecting client cancellation and cleaning up resources

On a gRPC Java server, `ServerCallStreamObserver<ResponseT>` provides key APIs:

- `isCancelled()`: checks whether the RPC has been cancelled.
- `setOnCancelHandler(Runnable)`: registers a callback to perform cleanup when cancellation is signaled.
- `isReady()` and `setOnReadyHandler(...)`: flow-control readiness signals when the client reads slowly; **distinct** from cancellation.

With server streaming, an event source may run on a different thread than the RPC thread. Therefore, do not keep a thread sleeping/waiting around just to emit a message every few seconds. Instead, use a publisher or scheduler with a clear lifecycle, and drop the call-specific subscription/task when the client cancels.

### 5.1. Spring gRPC server example using a scheduler

The service below simulates progress updates every 500 ms. The scheduler is shared at the service level; each RPC holds only one periodic task and cancels it when no longer needed.

~~~java
package com.example.jobs;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
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
        int maxUpdates = request.getMaxUpdates();

        if (jobId.isEmpty() || maxUpdates < 1 || maxUpdates > 20) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                    .withDescription("job_id required; max_updates must be 1..20")
                    .asRuntimeException());
            return;
        }

        ServerCallStreamObserver<ProgressEvent> out =
                (ServerCallStreamObserver<ProgressEvent>) responseObserver;

        // Gate coordinating the cancel callback and the RPC's scheduler.
        Object gate = new Object();
        AtomicBoolean closed = new AtomicBoolean(false);
        AtomicInteger sent = new AtomicInteger(0);
        AtomicReference<ScheduledFuture<?>> scheduled = new AtomicReference<>();

        out.setOnCancelHandler(() -> {
            synchronized (gate) {
                closed.set(true);
            }
            stop(scheduled.get());
            // In production: unsubscribe from this RPC's event source.
        });

        Runnable emit = () -> {
            synchronized (gate) {
                if (closed.get() || out.isCancelled()) {
                    closed.set(true);
                    stop(scheduled.get());
                    return;
                }

                try {
                    int next = sent.incrementAndGet();
                    ProgressEvent event = ProgressEvent.newBuilder()
                            .setJobId(jobId)
                            .setSequence(next)
                            .setPercent(next * 100 / maxUpdates)
                            .setDescription("Demo progress " + next)
                            .build();

                    out.onNext(event);

                    if (next == maxUpdates) {
                        closed.set(true);
                        out.onCompleted();
                        stop(scheduled.get());
                    }
                } catch (RuntimeException failure) {
                    if (!closed.get() && !out.isCancelled()) {
                        closed.set(true);
                        // Do not expose internal exception details to the client.
                        try {
                            out.onError(Status.INTERNAL
                                    .withDescription("Cannot produce progress")
                                    .asRuntimeException());
                        } finally {
                            stop(scheduled.get());
                        }
                    } else {
                        closed.set(true);
                        stop(scheduled.get());
                    }
                }
            }
        };

        ScheduledFuture<?> future = scheduler.scheduleWithFixedDelay(
                emit, 0, 500, TimeUnit.MILLISECONDS);
        scheduled.set(future);

        // A cancel/completion signal may arrive before storing the future.
        if (closed.get()) {
            future.cancel(false);
        }
    }

    private static void stop(ScheduledFuture<?> task) {
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

In a Spring gRPC integration that discovers `BindableService` beans, `@Service` lets Spring manage the server implementation. If the project uses a starter with a different registration mechanism, apply that starter's registration pattern. `@PreDestroy` shuts down the executor when the application stops.

**Points to observe on the server:**

1. The cancel callback only marks `closed`, cancels the timer, and cleans up resources. It does not attempt to emit `onCompleted` or `onError` to an already cancelled client.
2. `gate` coordinates the sender and the cancel callback so response emission cannot run concurrently with application-level cancellation handling.
3. Each `scheduleWithFixedDelay` task runs sequentially relative to itself; large applications still need limits on open RPCs and scheduler/producer/subscription overhead.
4. Once all updates are sent, the server calls `onCompleted()` once and stops the timer. On internal failure before completion, the server calls `onError(Status.INTERNAL...)` if the RPC is still active.
5. `isCancelled()` detects runtime state even if the cleanup callback has not yet executed.
6. `scheduled` might not be assigned yet if the callback fires very early; checking `closed` after registering the future prevents a leaked running timer.

The examples use small payloads only. In real applications, the progress source is usually an event bus or shared data table, and **cancelling the watch subscription** must be separated from **cancelling the report-generation job**. If a client reads slowly, the server must also use flow control (`isReady()`, `setOnReadyHandler(...)`), bounded buffers, and an appropriate backpressure policy.

### 5.2. When multiple emission sources exist concurrently

A broker event callback, a periodic task, and an error handler may simultaneously try to write to `StreamObserver`. `StreamObserver` is not thread-safe by default for concurrent writes from multiple threads.

A stable design typically consists of:

~~~text
Database/Broker event -> bounded queue --+
Timer/status event ----> bounded queue ---+--> single sender --> onNext(...)
                                         |                   --> onCompleted/onError
Client cancellation ----------------------+--> stop sender + unsubscribe + clear queue
~~~

A **single sequential sender** is responsible for emitting messages and one terminal signal; other sources only submit events or update state. When cancellation happens, no new events are admitted to the queue; the sender cancels pending work, frees buffers, detaches listeners, and closes call-related resources. Cleanup operations should be idempotent because cancellation and shutdown can occur nearly simultaneously.

## 6. Cancelling an RPC vs. cancelling a business job

Suppose `StartExport` creates a report-export job and returns `job_id`, while `WatchProgress` returns job status via server streaming:

~~~proto
service ExportService {
  rpc StartExport(StartExportRequest) returns (StartExportReply);
  rpc WatchProgress(WatchProgressRequest) returns (stream ProgressEvent);
  rpc CancelExport(CancelExportRequest) returns (CancelExportReply);
}
~~~

In this diagram, `StartExportRequest`, `StartExportReply`, `CancelExportRequest`, and `CancelExportReply` are additional messages that must be declared in a real proto file. The snippet only illustrates API separation of responsibilities.

| Action | Meaning | Impact on job |
|---|---|---|
| Client cancels `WatchProgress` | No longer needs watch events | **Does not automatically** stop the job |
| Client calls `CancelExport(job_id)` | Requests cancellation of the business job | Server decides whether it can cancel and returns result |
| Stream calls `onCompleted` naturally | Watch session ended normally | Does not necessarily mean the job was cancelled |
| Stream calls `onError` on network drop | Failed to deliver watch results | Job may continue running |

Separating the two actions prevents data loss or killing an important batch job simply because a browser tab closed. Conversely, for computations that exist solely to serve one request (no retained result needed), cancellation can be **intentionally propagated** down to worker tasks to save CPU and I/O.

### Propagating cancellation to child tasks

When the server invokes downstream services or queries a cancellable source, ensure child tasks can observe cancellation. gRPC Java provides `io.grpc.Context` to propagate RPC context across gRPC calls, and `Context.current().isCancelled()` lets related code check cancellation when context is properly propagated across threads.

However, a worker running on an executor does not automatically carry the RPC's context unless the application wraps tasks appropriately. You can use `Context.currentContextExecutor(executor)` or corresponding context propagation APIs; ensure child tasks truly carry the right `Context` and check/listen for cancellation. For independent business jobs, do not bind the job to the watch session's context.

## 7. Proactive cancel, deadline, and connection loss: how do they differ?

### 7.1. Proactive cancel

The client decides it needs no more responses and calls `ClientCallStreamObserver.cancel(...)`. The runtime usually surfaces `CANCELLED` on the client side, while the server sees the RPC cancelled when the notification arrives. Cancellation does not guarantee every buffered byte/message instantly vanishes from the wire or that an already-started callback stops synchronously. Thus, the application must handle callbacks and cancellation occurring close together.

### 7.2. Deadline expiration

Client usage:

~~~java
JobProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchProgress(request, observer);
~~~

The deadline bounds **total RPC duration**, not refreshed after each `onNext`. When the deadline expires, the runtime cancels the RPC; the client usually sees `DEADLINE_EXCEEDED`, while the server is notified of cancellation and must stop related tasks. A stream steadily emitting data can still hit its deadline after 10 seconds.

### 7.3. Connection loss

Network drops, a proxy closing the HTTP/2 stream, or transport failures can terminate the RPC with `UNAVAILABLE` or another status. The moment the server detects it may lag behind when the client actually lost connectivity. Therefore, enforce resource limits, deadlines/timeouts, and cleanup when the runtime reports RPC termination.

**Do not automatically retry a stream that was intentionally cancelled.** Retries are only appropriate when the user or business logic **still wants to continue** and the contract supports safe recovery. For network failures, resuming events from a checkpoint requires sequence/cursor fields paired with a replayable data source.

## 8. What happens to messages received before cancellation?

Suppose the client processed three events and then cancelled:

~~~text
Server intended: #1 → #2 → #3 → #4 → #5 → onCompleted()
Client received: #1 → #2 → #3
Client calls:    cancel("User closed view", null)
Typical result:  onError(CANCELLED)
~~~

The client may **have already executed side effects** for events 1–3, such as updating a database or UI. Cancelling the RPC does not roll back those operations. Conversely, the server having called `onNext(#4)` does not guarantee the client received or processed #4. When the client cancels, buffered responses may never arrive.

If the business process requires every event without gaps, add:

1. A monotonically increasing `sequence` within a defined scope (e.g., per `job_id`).
2. Checkpoints persisted **after** successfully processing an event.
3. A resume API with `after_sequence`/cursor and a history-retaining data store.
4. Duplicate handling (idempotency/deduplication), gap detection, and resync mechanisms.

gRPC **does not automatically guarantee exactly-once processing** of business events. Server `onCompleted` does not mean the client durably persisted the events either; sensitive computations require an application-level acknowledgment mechanism.

## 9. Backpressure when the client decides to stop

A client may choose to **stop receiving altogether** or **only temporarily fail to keep up**; the two situations must be handled differently:

- **No longer wants data:** call cancel. Server stops emitting and releases resources.
- **Wants data but is too slow:** regulate receive demand with `ClientResponseObserver`/`ClientCallStreamObserver.request(n)`, only granting further demand after processing a message; the server must also control data generation rate and buffers.

Client manual flow control example:

~~~java
// Inside ClientResponseObserver.beforeStart(...)
stream.disableAutoRequestWithInitial(1);

// After onNext(event) succeeds:
control.request(1);

// When the user truly stops watching:
control.cancel("Viewer stopped", null);
~~~

`request(1)` controls **the number of responses delivered to the client-side observer**, not sending another protobuf request to the server; it is not a client persistence ACK. Nor does it force the server producer to create only one message. For high-throughput streams, you need bounded queues, `ServerCallStreamObserver.isReady()`, `setOnReadyHandler(...)` callbacks, and proper source throttling.

If the application simply stops calling `request(n)` **without cancelling**, the RPC may stay open and hold resources until a deadline or another cancellation occurs. When the stream is no longer needed, cancel intentionally.

## 10. Testing cancellation from client to server

You can test with gRPC Java's **in-process transport** without opening network ports. To verify that cancellation actually reaches the server, create a test service that sends **one message and intentionally keeps the RPC open**, then have the client cancel immediately upon receiving that message.

JUnit 5 example:

~~~java
import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class CancelProgressStreamTest {

    @Test
    void clientCancellationReachesServer() throws Exception {
        CountDownLatch serverCancelled = new CountDownLatch(1);
        CountDownLatch firstReceived = new CountDownLatch(1);
        CountDownLatch clientTerminal = new CountDownLatch(1);
        AtomicReference<Status.Code> finalStatus = new AtomicReference<>();

        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new JobProgressServiceGrpc.JobProgressServiceImplBase() {
                    @Override
                    public void watchProgress(
                            WatchProgressRequest request,
                            StreamObserver<ProgressEvent> observer) {

                        ServerCallStreamObserver<ProgressEvent> out =
                                (ServerCallStreamObserver<ProgressEvent>) observer;
                        out.setOnCancelHandler(serverCancelled::countDown);
                        out.onNext(ProgressEvent.newBuilder()
                                .setJobId(request.getJobId())
                                .setSequence(1)
                                .setPercent(10)
                                .build());
                        // Keep the stream open so the client can cancel mid-way.
                    }
                })
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("job-731")
                    .setMaxUpdates(10)
                    .build();

            JobProgressServiceGrpc.newStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .watchProgress(
                            request,
                            new ClientResponseObserver<WatchProgressRequest,
                                                       ProgressEvent>() {
                                private ClientCallStreamObserver<
                                        WatchProgressRequest> call;

                                @Override
                                public void beforeStart(
                                        ClientCallStreamObserver<
                                                WatchProgressRequest> stream) {
                                    call = stream;
                                }

                                @Override
                                public void onNext(ProgressEvent response) {
                                    firstReceived.countDown();
                                    call.cancel("Test requested cancellation", null);
                                }

                                @Override
                                public void onError(Throwable error) {
                                    finalStatus.set(Status.fromThrowable(error).getCode());
                                    clientTerminal.countDown();
                                }

                                @Override
                                public void onCompleted() {
                                    finalStatus.set(Status.Code.OK);
                                    clientTerminal.countDown();
                                }
                            });

            assertTrue(firstReceived.await(2, TimeUnit.SECONDS));
            assertTrue(serverCancelled.await(2, TimeUnit.SECONDS));
            assertTrue(clientTerminal.await(2, TimeUnit.SECONDS));
            assertEquals(Status.Code.CANCELLED, finalStatus.get());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**Why does the test keep the server stream open?** If the server had already called `onCompleted()` before the client cancelled, the client could simply observe `OK` and the server would no longer have an active session to receive the cancel callback. By intentionally keeping the stream open, the test accurately verifies the event of **the client proactively terminating a running RPC**, while checking that the server is notified via `setOnCancelHandler`.

This is an in-process gRPC protocol test; it does not test Spring bean registration, interceptors, TLS, or real proxies. In production systems, add Spring Boot integration tests, network-disconnect tests, and checks that subscriptions/workers are closed.

### Recommended project test suite

| Scenario | Outcome to verify |
|---|---|
| Client cancels after first event | Client terminates with cancellation; server receives signal and cleans up resources |
| Cancel near `onCompleted` time | No double terminal signals; completion race handled cleanly |
| Client cancels before first event | Producer does not keep running pointlessly; no leaked listeners |
| Short deadline | Client typically sees `DEADLINE_EXCEEDED`; server stops watching work |
| Server errors after a few events | Client sees error status; does not treat RPC as successful |
| Multiple streams open on one channel | Cancelling one stream does not cancel remaining RPCs |
| Independent job source | Cancelling watch does not stop the job if business rules don't require it |
| Slow-reading client | Bounded backpressure; safe cancellation while buffered |
| Retry/resume after network drop | No duplicate processing or skipped events if contract requires full history |

## 11. Metadata, interceptors, TLS, and operational observability

In the Spring gRPC ecosystem, metadata usually carries authentication credentials, correlation IDs, or **RPC-level** control data. Interceptors can authenticate, authorize `job_id`, log termination status codes, and measure RPC duration. When clients proactively cancel, distinguish `CANCELLED` from server errors and deadlines so operational alerts remain meaningful.

For long-lived streams, pay attention to:

- **TLS/mTLS:** use encrypted connections and verify server identity in production; `usePlaintext()` in examples is only for trusted dev.
- **Authorization:** only callers permitted to view job progress may subscribe to watch it. Knowing `job_id` does not automatically grant read access.
- **Expiring permissions and tokens:** define a policy for streams that remain open after an access token expires or permissions are revoked.
- **Do not leak sensitive data:** log cancellation reasons safely; avoid logging tokens, personal data, or sensitive payloads.

Metrics to monitor:

| Metric | Meaning |
|---|---|
| Open RPCs by method/caller | Capacity and resources that must be sustained |
| RPCs ending in `OK`, `CANCELLED`, `DEADLINE_EXCEEDED`, `UNAVAILABLE` | Distinguish user stoppages, timeouts, and network errors |
| Latency from client cancel to server cleanup | Detect subscriptions or tasks not cancelled promptly |
| Living timers/producers/listeners after cancel | Detect resource leaks |
| Responses sent before cancel | Understand user behavior and traffic |
| Buffer size, readiness, messages/sec | Evaluate impact of slow-reading clients |
| Reconnect/replay rate and duplicate events | Evaluate business resume mechanism |

Do not lump every `CANCELLED` into system errors: some cancellations are completely normal when users leave a screen. However, if cancellation rates spike unexpectedly after proxy or deadline config changes, investigate further with traces and metrics.

## 12. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Only stopping UI updates without cancelling the RPC | Server keeps holding the stream, workers, and resources | Call the real gRPC call's cancel API |
| Closing a shared channel to cancel one stream | Disrupts other active RPCs | Cancel the specific RPC's `ClientCallStreamObserver` |
| Server calling `onCompleted` after client cancels | Emits unnecessary terminal signal, prone to races | Stop producer and clean up on cancellation |
| Not removing subscriptions/timers on cancel | Leaks memory, threads, and data-source connections | Use `setOnCancelHandler` and idempotent cleanup |
| Treating cancellation always as a business error | Noisy false alerts, hard to monitor | Separate cancellation, deadlines, transport, and domain errors |
| Cancelling watch also cancels background job without contract | Unintentionally kills important work | Separate `WatchProgress` and `CancelJob` commands |
| Already cancelled yet still calling `onNext` from another thread | Races, transport errors, wasted work | Coordinate sender, check state, unsubscribe |
| No checkpoint for mandatory complete data | Stream interruption causes missing/duplicate events | Design sequence, cursor, replay, and idempotency |
| Using `request(0)` or stopping `request(n)` as cancellation | RPC may keep holding resources open | Actively cancel when data is no longer needed |

### Self-check questions

1. Why does closing a monitoring screen not necessarily tell the server to stop the stream?
2. How does `ClientCallStreamObserver.cancel(...)` differ from calling `onError(...)` on the client's own observer?
3. Why does the server not need to call `onCompleted()` after receiving a client cancellation notice?
4. Should cancelling `WatchProgress` stop the report generation job? Which layer owns that decision?
5. When `onNext` and cancel occur nearly simultaneously on two threads, what must be protected?
6. How do `CANCELLED` and `DEADLINE_EXCEEDED` differ from the client's perspective?
7. If the client processed three events and then cancelled, how can it resume from the fourth event without duplicate processing?
8. Why should a cancellation test keep the RPC open until the client issues the cancel command?

**Key takeaway:** Cancelling a server streaming RPC means **terminating an active RPC** when the client no longer needs responses. The client uses gRPC's cancellation API, and the server receives the signal to stop the sender, unsubscribe, and release resources; the application must manage races between cancellation, event emission, and stream termination. Distinguish cancellation from deadlines, transport failures, and business cancellation commands, while managing backpressure, statuses, metadata, TLS, testing, and monitoring.
