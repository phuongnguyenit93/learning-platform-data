# onNext, onError, and onCompleted

## 1. The three callbacks that govern the server streaming lifecycle

In the **SPRING_GRPC** module, we build gRPC services using Protocol Buffers contracts, generate Java code, and integrate servers/clients into the Spring ecosystem. When working with **server streaming**, a single client request can produce multiple responses; the server-side developer controls emitting those responses through a `StreamObserver<ResponseT>` object. The observer's three core methods are:

- **`onNext(value)`:** emits **one** message; can be called zero or more times.
- **`onCompleted()`:** notifies that the server has finished emitting and ends the RPC successfully; carries no additional message.
- **`onError(cause)`:** terminates the RPC due to an error; passes a `Throwable` usually representing an appropriate gRPC `Status`.

In the **Server streaming** chapter, all three methods must be understood as a **lifecycle protocol**, not merely three isolated functions. A server can call `onNext` multiple times, but once it has called either of the two terminal callbacks, it must not emit more messages or invoke another terminal callback.

Example of a server updating report processing progress:

~~~mermaid
sequenceDiagram
    participant C as gRPC Java client
    participant S as Spring gRPC server
    C->>S: WatchProgress(job_id = "job-17")
    S-->>C: onNext(10%)
    S-->>C: onNext(60%)
    S-->>C: onNext(100%)
    S-->>C: onCompleted() / status OK
~~~

If the server encounters an error after sending `10%` and `60%`:

~~~mermaid
sequenceDiagram
    participant C as gRPC Java client
    participant S as Spring gRPC server
    C->>S: WatchProgress(job_id = "job-17")
    S-->>C: onNext(10%)
    S-->>C: onNext(60%)
    S--xC: onError(Status.UNAVAILABLE)
    Note over C: Partial data may have been received; RPC failed
~~~

**Note:** The callback names describe operations in the Java API, not literal strings transmitted over the wire. The gRPC runtime serializes messages using Protocol Buffers over HTTP/2 and transmits the final state via gRPC's status/trailers mechanism.

## 2. Ordering and termination rules

For a normal server-emitted RPC, the server-side callback sequence takes the form:

~~~text
onNext(message1) → onNext(message2) → ... → onNext(messageN) → onCompleted()
                                                    or → onError(cause)
~~~

**N = 0** is allowed: the server may complete successfully without sending any response, or fail before the first response.

| Scenario | Valid? | Explanation |
|---|---|---|
| `onNext(A) → onNext(B) → onCompleted()` | Yes | Two messages, one successful completion |
| `onCompleted()` | Yes | No messages, RPC still succeeds |
| `onError(Status.INVALID_ARGUMENT...)` | Yes | Invalid arguments before sending any data |
| `onNext(A) → onError(Status.UNAVAILABLE...)` | Yes | Emitted partially then encountered an error |
| `onNext(A) → onCompleted() → onNext(B)` | No | Must not emit after completion |
| `onError(...) → onCompleted()` | No | Must not emit two terminal signals |
| `onCompleted() → onCompleted()` | No | Completion must happen exactly once |

~~~mermaid
stateDiagram-v2
    [*] --> Active: Request received
    Active --> Active: onNext(value), 0..N times
    Active --> Completed: onCompleted()
    Active --> Failed: onError(cause)
    Active --> Cancelled: Client cancels / deadline / transport closed
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

The `Cancelled` state in the diagram represents the case where the **runtime or client terminates the RPC**. The server does not necessarily need to call `onError` on the response observer once the client has cancelled; instead, it should stop work and release stream resources.

Rules to remember:

1. **`onNext` is not an acknowledgment that the client has processed the message.** It hands the message to the gRPC runtime for sending; it does not guarantee the receiver has consumed or persisted it.
2. **`onCompleted` is successful completion from the server's perspective.** The client only concludes the RPC succeeded after **actually receiving** the successful termination signal. A network failure occurring after the server calls `onCompleted` can still prevent the client from observing success.
3. **`onError` is a terminal signal.** Once called, the server must not call `onCompleted` or `onNext` again.
4. **Write calls must be serialized.** `StreamObserver` is not thread-safe by default if multiple threads call `onNext`/`onError`/`onCompleted` concurrently for one RPC.
5. **No automatic replay guarantee at the business layer.** If the client received three events and then hit an error, recovering or deduplicating events requires an appropriate sequence/checkpoint contract.

## 3. Protocol Buffers contract for the hands-on example

We build the `WatchProgress` method: one request asks for up to five progress updates, and the server sends `ProgressEvent` messages sequentially and completes.

File `src/main/proto/progress.proto`:

~~~proto
syntax = "proto3";

package progress.v1;

option java_multiple_files = true;
option java_package = "com.example.progress.rpc";
option java_outer_classname = "ProgressProto";

service ProgressService {
  rpc WatchProgress(ProgressRequest) returns (stream ProgressEvent);
}

message ProgressRequest {
  string job_id = 1;
  int32 limit = 2;
}

message ProgressEvent {
  string job_id = 1;
  int32 step = 2;
  int32 percent = 3;
  string detail = 4;
}
~~~

The `stream` keyword goes **before the response type**. When `protoc` and the `protoc-gen-grpc-java` plugin generate code, we get the message classes `ProgressRequest`, `ProgressEvent`, and the service/stub class `ProgressServiceGrpc`. The observer API below is the **gRPC Java** API; build plugin configuration, starters, and service registration in Spring may vary depending on the integration version in use.

## 4. Java server: distinguishing the three callbacks with a concrete service

This is a **finite implementation using simulated data**. Each message is created quickly, with no `sleep` or blocking queries on the RPC handling thread. The code illustrates both the valid flow and the invalid request branch:

~~~java
package com.example.progress;

import com.example.progress.rpc.ProgressEvent;
import com.example.progress.rpc.ProgressRequest;
import com.example.progress.rpc.ProgressServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class ProgressServiceImpl
        extends ProgressServiceGrpc.ProgressServiceImplBase {

    @Override
    public void watchProgress(
            ProgressRequest request,
            StreamObserver<ProgressEvent> responses) {

        String jobId = request.getJobId().trim();
        int limit = request.getLimit();

        if (jobId.isEmpty() || limit < 1 || limit > 5) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription(
                            "job_id must not be blank; limit must be 1..5")
                    .asRuntimeException());
            return; // onError is terminal: emit no further messages.
        }

        for (int step = 1; step <= limit; step++) {
            ProgressEvent event = ProgressEvent.newBuilder()
                    .setJobId(jobId)
                    .setStep(step)
                    .setPercent(step * 100 / limit)
                    .setDetail("Finished step " + step)
                    .build();

            responses.onNext(event);
        }

        responses.onCompleted(); // Only after all steps have been sent.
    }
}
~~~

If a request is sent with `job_id = "job-17"` and `limit = 3`, the client is expected to receive:

~~~text
onNext(ProgressEvent{step=1, percent=33})
onNext(ProgressEvent{step=2, percent=66})
onNext(ProgressEvent{step=3, percent=100})
onCompleted()
~~~

If `limit = 0` is sent, the server calls `onError(INVALID_ARGUMENT)` and returns, emitting **no** events and **never** calling `onCompleted`.

In a Spring gRPC application with automatic `BindableService` registration from the Spring context, the `@Service` bean is managed by Spring. If the project uses a different integration starter, follow that starter's service registration mechanism; the three `StreamObserver` methods still follow the same rules.

**Limitations of the example:** this loop is suitable for demonstrating a small finite stream. Do not use this pattern to push millions of uncontrolled messages, perform long I/O, or block the RPC thread with `Thread.sleep` in a production system. For asynchronous producers, you must manage cancellation, flow control, ordering, and terminal callback counts.

## 5. When to call onNext?

`onNext(T value)` is called whenever **one valid response is ready** for the client. In server streaming, a response may be a new state, a batch of results, a data chunk, a log entry, or a progress milestone.

Practical rules:

- **One call corresponds to one protobuf message.** There is no need to collect all events into a `repeated` list.
- **Zero events may occur.** For example, a filter yields no matches; the server can still call `onCompleted()` successfully.
- **Send order on a single RPC is preserved.** However, the logical ordering of multiple parallel producer sources must be established by the application before emitting.
- **Do not treat `onNext` as durable persistence.** The server must design separate idempotency and resume mechanisms if the client must process every single event.
- **Balance emission speed with reading speed.** An unbounded producer can cause application buffers to balloon, even though HTTP/2 supports flow control.

With a Java gRPC server, you can use `ServerCallStreamObserver<ProgressEvent>` to know when the client can no longer receive and to observe readiness:

~~~java
ServerCallStreamObserver<ProgressEvent> out =
        (ServerCallStreamObserver<ProgressEvent>) responses;

if (out.isCancelled()) {
    return; // Stop producing data for a cancelled RPC.
}

if (out.isReady()) {
    out.onNext(event); // event has already been built from the data source.
} else {
    // Wait for onReady signal, slow down upstream, or buffer with a bound.
}
~~~

The snippet above only illustrates checks inside an **event emission function** where `responses` and `event` are already available. `isReady()` is a flow control API signal, **not** confirmation that the client has processed the message. Never silently drop mandatory business events when the observer is not ready; use a bounded queue, upstream throttling, or storage for replay per contract. When using `setOnReadyHandler`, avoid busy-wait loops; only emit when sending conditions are met again, and continue checking cancellation status.

## 6. When to call onCompleted?

Call `onCompleted()` **once** when the server has emitted all messages and has no further data belonging to that RPC. This callback represents **successful RPC completion**, corresponding to the `OK` status transmitted by gRPC upon normal termination.

Example:

~~~java
// Inside a service method that has already validated the request:
for (ProgressEvent event : events) {
    responses.onNext(event);
}
responses.onCompleted();
~~~

An empty `events` collection is completely valid: `onCompleted()` indicates the query had zero items, yet the query itself succeeded.

Distinguish **transport success** from **business success**. For example, a job might have run and **failed in business logic**, yet the server can still emit an event with status `FAILED` and call `onCompleted()` if the contract treats that as a valid observed outcome. Conversely, failing to find the job, lacking access permission, or being unable to read the data source are appropriate reasons to return a gRPC error status.

Do not use `onCompleted()` to:

- Confirm that a message just sent via `onNext` was processed by the client.
- Hide errors by closing the stream successfully and continuing error handling elsewhere.
- End the stream while another unsynchronized task might still emit on the same RPC.

## 7. When to call onError?

`onError(Throwable t)` terminates the stream when the server **can no longer fulfill the RPC per contract**. Rather than throwing an arbitrary exception onto the RPC thread, server code should intentionally translate errors into a `StatusRuntimeException`:

~~~java
responses.onError(Status.NOT_FOUND
        .withDescription("Job does not exist")
        .asRuntimeException());
return;
~~~

This is an error termination, so you must `return` or ensure no other branches emit further messages. Common status codes:

| Status | Suggested scenario |
|---|---|
| `INVALID_ARGUMENT` | Blank `job_id`, invalid limit parameter |
| `NOT_FOUND` | Requested job does not exist |
| `PERMISSION_DENIED` | Authenticated caller is not permitted to view the job |
| `UNAUTHENTICATED` | Missing or invalid authentication credentials |
| `RESOURCE_EXHAUSTED` | Exceeded stream, memory, or quota limits |
| `UNAVAILABLE` | Data source or dependency temporarily unavailable |
| `INTERNAL` | Internal error not caused by client input |

Example where the data source becomes unreadable **after several messages have already been sent**:

~~~java
// This is a branch inside a producer handling the RPC.
if (sourceUnavailable) {
    responses.onError(Status.UNAVAILABLE
            .withDescription("Progress source unavailable")
            .asRuntimeException());
    return;
}
~~~

`sourceUnavailable` is an illustrative business condition. Even after receiving step 1 and step 2 events, the client may receive `onError` without receiving step 3. Even messages buffered when the error occurs might not reach the client. Therefore, **receiving a few `onNext` calls does not mean the overall RPC succeeded**.

Do not put raw stack traces, tokens, or sensitive internal details directly into `Status.description`. Diagnostic details belong in controlled internal logs/traces. For technical errors, the server can log the root cause and return a safe description to the client.

**Common mistakes:**

~~~java
responses.onError(Status.INTERNAL.asRuntimeException());
responses.onCompleted(); // WRONG: a terminal signal was already sent.
~~~

Or:

~~~java
responses.onCompleted();
responses.onNext(event); // WRONG: the RPC has already terminated.
~~~

When calling `onError`, use a status that accurately reflects the error kind. Never pass `Status.OK` to `onError`; for success, use `onCompleted`.

## 8. The three client-side callbacks and their practical meaning

In an async Java client, we also provide a `StreamObserver<ProgressEvent>`, but it is used to **receive** messages and terminal signals invoked by the gRPC runtime. The server actively invokes callbacks on the server-side response observer; the client does not call `onNext` on its response observer to request more messages.

~~~java
import com.example.progress.rpc.ProgressEvent;
import com.example.progress.rpc.ProgressRequest;
import com.example.progress.rpc.ProgressServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

// channel is a ManagedChannel created and managed by the calling layer.
ProgressRequest request = ProgressRequest.newBuilder()
        .setJobId("job-17")
        .setLimit(3)
        .build();

CompletableFuture<Void> finished = new CompletableFuture<>();

ProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchProgress(request, new StreamObserver<ProgressEvent>() {
            @Override
            public void onNext(ProgressEvent value) {
                System.out.printf("step=%d, percent=%d%%%n",
                        value.getStep(), value.getPercent());
            }

            @Override
            public void onError(Throwable error) {
                System.err.println(
                        "Stream failed: " + Status.fromThrowable(error));
                finished.completeExceptionally(error);
            }

            @Override
            public void onCompleted() {
                System.out.println("Stream completed successfully");
                finished.complete(null);
            }
        });

// Waiting for completion is only for console/test demo purposes.
// Do not block an event-loop or web request-handling thread.
finished.get(12, TimeUnit.SECONDS);
~~~

With a valid request, callbacks are invoked in this sequence:

~~~text
onNext(step=1) → onNext(step=2) → onNext(step=3) → onCompleted()
~~~

With `limit = 0`:

~~~text
onError(StatusRuntimeException: INVALID_ARGUMENT)
~~~

The `CompletableFuture` in the example lets the demo program wait for the result; if an error is received, `get` throws `ExecutionException` wrapping the cause. In a Spring application, the client should reuse channels and structure the async lifecycle via appropriate beans/services. Do not shut down the channel immediately after calling `watchProgress` because the async call returns control immediately while the stream is still running.

The client **does not** wait for `onCompleted` if it has already received `onError`. These are mutually exclusive outcomes. To stop a stream proactively, use gRPC's cancellation API—such as `ClientCallStreamObserver.cancel(...)` in the appropriate client pattern—or manage the deadline. Do not manually call `onError` on the client's response observer to "cancel the RPC"; doing so only affects your own callback code and does not instruct gRPC to cancel the call.

### What if using the blocking stub?

A server streaming blocking stub returns an `Iterator<ProgressEvent>`:

~~~java
var iterator = ProgressServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchProgress(request);

while (iterator.hasNext()) {
    ProgressEvent value = iterator.next();
    System.out.println(value.getPercent());
}
// If the loop exits normally: the client observed successful completion.
~~~

The blocking API does not require the caller to pass callbacks directly. However, the gRPC semantics remain identical: messages correspond to `onNext`, successful completion exhausts the iterator, and errors cause `hasNext`/`next` to throw `StatusRuntimeException`. The calling thread may block while waiting for the next message.

## 9. Cancellation, deadlines, and long-lived streams

Server streaming typically lives longer than unary RPCs. A client may navigate away, drop network connectivity, hit a deadline, or request cancellation while the server is still waiting for the next piece of data. In that event, **do not continue emitting to a cancelled observer**; cancel timers, subscriptions, listeners, cursors, or processing tasks dedicated to that RPC.

On the Java gRPC server side, `ServerCallStreamObserver` provides an API to receive cancellation signals:

~~~java
ServerCallStreamObserver<ProgressEvent> out =
        (ServerCallStreamObserver<ProgressEvent>) responses;

out.setOnCancelHandler(() -> {
    // Cancel subscriptions/timers and release resources belonging to this RPC.
    stopProducingForThisCall();
});
~~~

`stopProducingForThisCall()` here is an application-implemented function. When a producer runs on a different thread/executor, the cancellation callback and the emission callback may race. Use a state flag or synchronization coordination so `onNext` is never called concurrently with termination or after cancellation. Never automatically call `onCompleted` after cancellation.

**Deadlines apply to the entire RPC**, not reset each time the server calls `onNext`. Thus, even a stream steadily emitting data can still terminate with `DEADLINE_EXCEEDED` once the configured time limit expires. The client may observe `CANCELLED` from explicit cancellation, `DEADLINE_EXCEEDED` from timeout, or `UNAVAILABLE` on connection issues; the observed status depends on the cause and timing of the failure.

For stable operations, the system should have policies for:

- Limiting concurrently open streams and buffer sizes.
- Setting appropriate deadlines/idle timeouts aligned with proxy or load balancer configurations.
- Releasing resources across all termination branches: success, error, and cancellation.
- Designing `sequence`/cursors, replay, and deduplication at the data layer when resuming after disconnects is needed; gRPC does not automatically guarantee **exactly once** business event delivery.

## 10. Avoiding race conditions when emitting from multiple threads

Consider this scenario: one data-reading thread wants to call `onNext(event)`, while another thread detects an error and calls `onError(cause)`. Without coordination, both methods could run concurrently, or `onNext` could happen after the terminal callback.

Implementation principles:

1. **Designate a single point responsible for emitting signals:** all messages and terminal signals for an RPC are routed through a sequential queue/executor, or protected by an equivalent synchronization mechanism.
2. **Mark state before terminating:** after choosing `onError` or `onCompleted`, ignore late-arriving events.
3. **Separate business workers and sender:** workers enqueue events into a bounded queue; a single sender consumes in order, respects readiness, and emits the terminal signal at the right time.
4. **Handle cancellation independently of normal completion:** once the client cancels, cleanup must not proceed to emit a success callback.

Pseudocode example for a sequential emitter:

~~~text
producer threads --enqueue--> bounded event queue
                               |
                               v
                         single sender
                         | onNext(event) when ready
                         | onCompleted() when source finishes successfully
                         | onError(status) when source errors
                         + stop + cleanup on cancel
~~~

Do not assume that merely checking an `AtomicBoolean` flag around two separate calls is sufficient to prevent `onNext` and `onError` from interleaving. If calls originate on two different threads, you need atomic coordination across **the entire emit operation**, such as a sequential executor.

## 11. Testing callback lifecycles properly

In addition to unit testing message construction logic, you can test using gRPC's **in-process transport** to exercise real stubs, protobuf serialization, and statuses without opening network ports. The JUnit 5 example below tests both the success path and the error path:

~~~java
import com.example.progress.ProgressServiceImpl;
import com.example.progress.rpc.ProgressEvent;
import com.example.progress.rpc.ProgressRequest;
import com.example.progress.rpc.ProgressServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProgressServiceImplTest {
    @Test
    void streamingCallbacksAndTerminalStatus() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new ProgressServiceImpl())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            var stub = ProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS);

            ProgressRequest valid = ProgressRequest.newBuilder()
                    .setJobId("job-17")
                    .setLimit(3)
                    .build();
            List<ProgressEvent> received = new ArrayList<>();
            stub.watchProgress(valid).forEachRemaining(received::add);

            // Iterator ends normally: client observes OK status.
            assertEquals(List.of(1, 2, 3),
                    received.stream().map(ProgressEvent::getStep).toList());
            assertEquals(100, received.get(2).getPercent());

            ProgressRequest invalid = ProgressRequest.newBuilder()
                    .setJobId("job-17")
                    .setLimit(0)
                    .build();
            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.watchProgress(invalid).hasNext());
            assertEquals(Status.Code.INVALID_ARGUMENT,
                    error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

To run this test, the project needs JUnit 5 along with the gRPC in-process dependency compatible with gRPC Java. In-process tests do not verify Spring's actual service registration, interceptors, TLS, or behavior behind proxies. Add integration tests using the Spring context and real network tests before deployment.

Additional scenarios worth testing:

| Test case | Expectation |
|---|---|
| Stream with 0 events | `onCompleted` succeeds, client receives no events |
| Stream with multiple events | Message count and order are correct |
| Error before first event | Client receives exact gRPC status, no messages |
| Error after a few events | Client receives error status; does not treat partial data as a successful RPC |
| Client cancels while producer is waiting | No remaining timers/subscriptions for the RPC; no further emissions |
| Deadline shorter than stream duration | Client receives deadline exceeded error, server stops work |
| Concurrent producers | No concurrent observer writes; only one terminal signal |
| Slow-consuming client | Buffers and task counts are bounded, no memory explosion |

## 12. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| "Once `onNext` finishes sending, the client has processed it successfully" | `onNext` only hands the message to the gRPC runtime; business acknowledgment needs a separate mechanism |
| "`onCompleted` sends the final message" | The final message must be sent via `onNext`; `onCompleted` only signals successful completion |
| "After `onError`, you can call `onCompleted` to cleanly close the stream" | `onError` already terminates the RPC; do not invoke another terminal callback |
| "Zero events means an error" | Zero events followed by `onCompleted` can be a valid result |
| "If a few `onNext` calls happened, the RPC partially succeeded" | Data may be processed partially, yet the **entire RPC** still has an error status |
| "Java exceptions automatically produce good statuses" | Intentionally map exceptions to an appropriate `Status` and return a safe description |
| "If `isReady()` is false, you can drop all events" | Must follow the contract on data loss, buffering, and replay |
| "When the client cancels, the server calls `onCompleted`" | Client cancellation requires the server to **stop producing and clean up resources** |

### Self-practice questions

1. Why cannot `onCompleted()` and `onError(...)` both appear in the same stream?
2. When a request is valid but yields zero records, should you use `onCompleted()` or `onError(NOT_FOUND)`? What in the contract determines this choice?
3. If the server sends two events and then hits a database error, what outcomes can the client observe?
4. Why cannot `onNext` be called from multiple threads on the same observer without coordination?
5. After the client closes the application, what resources on the server must be released?
6. Is a 10-second deadline refreshed after each `onNext`?

**Key takeaway:** In Spring gRPC server streaming, **`onNext` emits each message**, **`onCompleted` ends successfully**, and **`onError` ends with an error**. A proper contract requires serialized emissions, a single terminal signal, and thorough handling of cancellation, deadlines, backpressure, statuses, security, and testing. This is the foundation for running response streams reliably in real systems.
