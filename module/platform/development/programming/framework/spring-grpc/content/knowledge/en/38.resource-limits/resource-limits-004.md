# Number of messages in a stream

## Learning Objectives

After this lesson, you can:

- Explain message-count limits in a streaming RPC and distinguish them from message-size limits.
- Determine which messages are counted on the inbound side, outbound side, or both directions.
- Design per-stream counters without sharing a counter across requests.
- Reject over-threshold messages before executing business logic or emitting further responses.
- Combine message-count limits with byte quotas, deadlines, flow control, and concurrent stream limits.
- Handle terminal states, cancellation, and cleanup properly when a stream exceeds its quota.
- Choose appropriate statuses and design safe client retry/resume behavior.
- Test N and N+1 boundaries for client-streaming, server-streaming, and bidirectional streaming.

## 1. Why limit the number of messages in a stream?

In **SPRING_GRPC**, streaming RPCs allow a call to exchange many messages over a long period. Client-streaming receives multiple requests and returns a single result; server-streaming receives a single request and emits multiple responses; bidirectional streaming exchanges multiple messages in both directions.

Limiting the size of a single message does not limit the number of messages in a stream. For example, each message may be only 1 KiB, yet a client continuously sends millions of messages. The server still has to dispatch callbacks, validate, update counters, access storage, or call downstreams. CPU usage, database writes, event publishing, logs, and queue memory can rise sharply.

**Number of messages in a stream** is the number of messages permitted to be sent or received within the lifecycle of a single RPC. The application must clearly define which direction the limit applies to and when messages are counted:

- **Inbound messages:** messages going from the client to the server.
- **Outbound messages:** messages going from the server to the client.
- **Combined messages:** total messages in both directions, used only when the contract explicitly defines a shared budget.

With bidirectional streaming, separate limits should be set for inbound and outbound; a total budget can be added if you need to bound the cost of the entire session. Do not assume an inbound limit automatically applies to responses.

~~~mermaid
flowchart TD
    A["Open streaming RPC"] --> B["Authenticate and authorize method"]
    B --> C["Create per-stream counter"]
    C --> D{"New message?"}
    D -- "No" --> E["Wait, cancel, or deadline"]
    D -- "Yes" --> F{"Counter has quota left?"}
    F -- "No" --> G["RESOURCE_EXHAUSTED"]
    F -- "Yes" --> H["Increment counter"]
    H --> I["Validate and authorize message"]
    I --> J["Process or emit response"]
    J --> D
    G --> K["Stop stream and clean up"]
~~~

Counters must be bound to a specific RPC. Do not store the current message count in a mutable field of a singleton service, because multiple concurrent streams could overwrite or accumulate into each other's counters.

## 2. Distinguishing message count from other limits

Resource limits protect different aspects:

| Limit | Unit | What is controlled |
| --- | --- | --- |
| Max message size | Bytes/message | Size of a single message |
| Max messages per stream | Messages/RPC | Number of messages in one stream |
| Total bytes per stream | Bytes/RPC | Total data in the stream |
| Stream concurrency | Streams/instance or tenant | Number of open streaming RPCs |
| Rate limit | Messages or bytes/time unit | Sending rate |
| Deadline/maximum lifetime | Time | Duration the call and resources are held |
| Flow control/backpressure | In-flight messages | Producer speed relative to consumer |

For example, a stream sends 100,000 messages of 200 bytes each. A message-size limit does not prevent a high message count; a byte quota can bound total payload while still allowing very many small messages that cause callback overhead. Conversely, a message-count limit can cap the number of messages, yet a few large messages can still consume significant memory. Therefore, combining count limits and byte limits is usually necessary.

Flow control also does not replace a message-count limit. Flow control regulates how many messages are in transit or awaiting processing at a time; once the consumer finishes processing, the client can keep sending more messages until the stream ends. A message-count limit bounds the total number of messages over the entire RPC.

## 3. Defining counting scope by streaming type

Each RPC type has different message directions:

| RPC type | Inbound at server | Outbound at server | Limits typically needed |
| --- | --- | --- | --- |
| Unary | One request | One response | Usually no separate stream count needed; still has message-size limit |
| Client-streaming | Multiple requests | One final response | Inbound message count and total bytes |
| Server-streaming | One request | Multiple responses | Outbound message count and total bytes |
| Bidirectional | Multiple requests | Multiple responses | Inbound and outbound counts; optional combined budget |

With client-streaming, count each request message the server receives in onNext. With server-streaming, count each response before calling onNext on the response observer. With bidirectional streaming, maintain two independent counters because request and response counts can differ.

If the contract defines a combined budget, document clearly which messages count toward the budget and the update order. For example, an incoming request and an outgoing response could consume from one unit; however, this accounting is often hard for clients to predict. Two separate directional limits are usually easier to operate and debug.

## 4. Setting limits at the application boundary

grpc-java provides limits such as max inbound message size and flow control, but you should not assume the transport automatically enforces a total message-count quota for every stream. Maximum message count is typically an application policy, because each method has a different meaning and workload.

Examples:

- A batch upload might allow at most 5,000 item messages.
- An event subscription might allow at most 20,000 events before the client must reconnect with a cursor.
- A command stream might limit 500 commands per session.
- A telemetry stream might limit message count by duration and tenant quota.

Set policies per method and data type. Do not use a single overly large value across all RPCs just to avoid per-API configuration. If a method legitimately needs a high message count, clearly define its quota, lifetime, resume semantics, and downstream cost.

A policy can describe limits by full method name:

~~~java
public interface StreamMessageLimitPolicy {
    long maxInboundMessages(String fullMethodName);
    long maxOutboundMessages(String fullMethodName);
}
~~~

Undeclared methods must have explicit behavior: use a conservative default or reject the stream per policy. Do not let new methods accidentally have an unlimited quota.

In the **Spring gRPC** ecosystem, the policy can be injected into service adapters or interceptors as a bean. If the server is managed by a starter, register the policy/handler through the extension point supported by your starter version; do not stand up a second server just to work around configuration. Integration tests must start the Spring application context to confirm the message-limit bean is actually used by the running service.

## 5. Thread-safe per-stream counters

A counter should have a positive limit and an atomic consume operation. Use long to avoid int's smaller range on long streams:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class MessageBudget {

    private final long maximum;
    private final AtomicLong consumed = new AtomicLong();

    public MessageBudget(long maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException(
                    "maximum must be positive");
        }
        this.maximum = maximum;
    }

    public boolean tryConsume() {
        while (true) {
            long current = consumed.get();

            if (current >= maximum) {
                return false;
            }

            if (consumed.compareAndSet(current, current + 1)) {
                return true;
            }
        }
    }

    public long consumed() {
        return consumed.get();
    }

    public long remaining() {
        return Math.max(0, maximum - consumed.get());
    }
}
~~~

When the counter is at N-1, the Nth message is accepted and the counter becomes N. The (N+1)th message is rejected. Do not increment first and compare afterward with a non-atomic operation if callbacks can run from multiple producers.

Create one MessageBudget per direction of each stream. Do not share a single static AtomicLong across all RPCs, or one caller's quota will be consumed by other callers.

Even though grpc-java usually serializes callbacks for a single call, the application may emit responses from multiple threads or use multiple producers. If multiple threads call the outbound observer, serialize message sending and counter updates; StreamObserver is not safe for concurrent writes by default.

## 6. Client-streaming: counting incoming request messages

With client-streaming, the server receives multiple requests via StreamObserver. Count before validating and running the use case so message N+1 causes no side effects:

~~~java
@Override
public StreamObserver<UploadItemRequest> uploadItems(
        StreamObserver<UploadSummary> responseObserver) {

    MessageBudget inbound =
            new MessageBudget(MAX_UPLOAD_MESSAGES);

    return new StreamObserver<>() {
        private boolean terminal;
        private long accepted;

        @Override
        public synchronized void onNext(UploadItemRequest request) {
            if (terminal) {
                return;
            }

            if (!inbound.tryConsume()) {
                terminal = true;
                responseObserver.onError(
                        Status.RESOURCE_EXHAUSTED
                                .withDescription("Stream message limit reached")
                                .asRuntimeException());
                cleanupUpload();
                return;
            }

            try {
                validateAndAuthorize(request);
                uploadUseCase.process(request);
                accepted++;
            } catch (RuntimeException failure) {
                terminal = true;
                responseObserver.onError(mapError(failure));
                cleanupUpload();
            }
        }

        @Override
        public synchronized void onError(Throwable error) {
            if (!terminal) {
                terminal = true;
                cleanupUpload();
            }
        }

        @Override
        public synchronized void onCompleted() {
            if (terminal) {
                return;
            }

            terminal = true;
            responseObserver.onNext(
                    UploadSummary.newBuilder()
                            .setAcceptedCount(accepted)
                            .build());
            responseObserver.onCompleted();
            cleanupUpload();
        }
    };
}
~~~

This illustrative example must be adapted to your use case and application threading rules. In a real implementation, cleanup should be idempotent; errors at any step must not emit terminal signals multiple times. If processing messages asynchronously, bound the number of queued tasks as well and preserve ordering or parallel semantics allowed by the contract.

The key point is that the message count is consumed before any business side effect. If the counter is incremented only after processing, an (N+1)th message could still be written before detecting that the quota was exceeded.

## 7. Server-streaming: counting responses before emitting

With server-streaming, one request produces multiple responses. The outbound counter is created per call and checked before each onNext:

~~~java
public void watchEvents(
        WatchRequest request,
        StreamObserver<EventResponse> responseObserver) {

    MessageBudget outbound =
            new MessageBudget(MAX_RESPONSE_MESSAGES);

    try {
        for (Event event : eventSource.read(request)) {
            if (!outbound.tryConsume()) {
                responseObserver.onError(
                        Status.RESOURCE_EXHAUSTED
                                .withDescription("Stream message limit reached")
                                .asRuntimeException());
                return;
            }

            responseObserver.onNext(toResponse(event));
        }

        responseObserver.onCompleted();
    } catch (RuntimeException failure) {
        responseObserver.onError(mapError(failure));
    }
}
~~~

In the synchronous example, the loop stops immediately when the quota runs out. With an asynchronous event source, cancel the subscription when the quota runs out or when the client cancels the call. Do not keep reading from a broker/database only to discard responses, because the data source still consumes resources.

If the API needs to continue from the last position, responses should include a cursor or sequence. Upon reaching the message limit, the client can open a new stream from the next cursor instead of asking the server to keep an infinite stream.

## 8. Bidirectional streaming: two independent counters

With bidirectional streaming, both client and server can send multiple messages. One inbound request can trigger zero, one, or many outbound responses. Therefore, do not assume request count equals response count.

Create two budgets:

~~~java
MessageBudget inbound =
        new MessageBudget(MAX_REQUEST_MESSAGES);

MessageBudget outbound =
        new MessageBudget(MAX_RESPONSE_MESSAGES);
~~~

Inside the request callback:

~~~java
if (!inbound.tryConsume()) {
    terminate(Status.RESOURCE_EXHAUSTED);
    return;
}

validateAuthorizeAndProcess(request);
~~~

Before sending a response:

~~~java
if (!outbound.tryConsume()) {
    terminate(Status.RESOURCE_EXHAUSTED);
    return;
}

responseObserver.onNext(response);
~~~

If the contract includes a combined budget, add a third counter and consume according to published rules. Avoid updating only the inbound counter while emitting many responses beyond the outbound quota; each direction must be controlled separately.

If the server sends responses from worker threads, use an outbound serializer or sequential executor to ensure the observer is not called concurrently. Terminal state must also be atomic/synchronized to avoid emitting both onError and onCompleted.

## 9. Handling limit exceedance

When message N+1 arrives, the application can terminate the stream with **RESOURCE_EXHAUSTED**. This status represents that a quota or resource limit has been hit.

Distinguish:

| Cause | Status/behavior |
| --- | --- |
| Exceeds stream's maximum message count | **RESOURCE_EXHAUSTED** |
| Exceeds total bytes or business quota | **RESOURCE_EXHAUSTED** |
| Malformed message or invalid field | **INVALID_ARGUMENT** |
| Caller lacks permission to send message | **PERMISSION_DENIED** |
| Invalid credentials | **UNAUTHENTICATED** |
| Deadline expires | **DEADLINE_EXCEEDED** |
| Client cancels stream | **CANCELLED** |

Do not use **INVALID_ARGUMENT** for every quota exceedance case. A message may be completely schema-valid while the stream has exhausted its budget. Conversely, the second message might be rejected for an invalid field even though count quota remains.

Do not expose internal quotas, other tenants' counts, or sensitive policy details in the status description. Clients should rely on the status code and stable reason codes if provided by the API.

## 10. Partial success or terminate the whole stream?

A message exceeding the quota can terminate the entire RPC, or the API can use an item-level protocol to reject one item and continue. These two semantics are different and must be defined in the contract.

**Terminate stream** fits when message count is a hard cap for the entire session. Once N messages are reached, message N+1 terminates the stream with RESOURCE_EXHAUSTED. The client needs to open a new stream if quota/a new session is available.

**Reject item and continue** fits when the server enforces quotas per batch or independent item and the contract allows per-item results. However, if the message count itself is the total quota for the stream, continuing to accept messages after exhausting the quota breaks the limit. Avoid returning item-level errors while still processing an unbounded number of subsequent items.

If using partial success, limit accepted items, rejected items, total bytes, and stream duration. You can close the stream after a number of consecutive rejections to prevent clients from using item-level errors to probe policy or burn CPU.

## 11. Combining count limits with byte quotas, rate limits, and flow control

A stream can send many small messages or a few large messages. Complementary limits are needed:

- **Message count:** caps total number of message processing invocations.
- **Total bytes:** caps total payload.
- **Max message size:** caps a single oversized message.
- **Rate limit:** caps overly high message/byte rates.
- **Flow control:** limits in-flight messages.
- **Deadline/idle timeout:** limits how long resources are held.
- **Stream concurrency:** limits concurrent streams.

For example, an upload might allow at most 2,000 chunks, each at most 256 KiB, total upload at most 100 MiB, maximum duration 10 minutes, and at most 3 concurrent uploads per tenant. Each limit protects a distinct dimension.

When updating total bytes, use long and check for overflow before adding. With distributed per-tenant quotas, updates must be atomic so two streams do not consume past the cap together.

Flow control does not replace a count limit: a stream can send one message at a time, wait for the server to finish processing, then send the next, eventually sending millions of messages. The count limit bounds that total number of iterations.

## 12. Deadlines, cancellation, and cleanup

A stream can end before reaching the message limit due to deadline, client cancellation, or downstream error. Every terminal path must release subscriptions, queues, timers, and quotas.

With server streaming, cancellation can be observed via ServerCallStreamObserver:

~~~java
if (responseObserver instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.setOnCancelHandler(() -> {
        subscription.cancel();
        cleanupStreamState();
    });
}
~~~

When the message limit is exceeded, stop the producer source immediately. When the client cancels, do not keep reading messages from a broker just to discard them. With client-streaming, do not buffer all messages if the use case can process item by item.

Principles:

- Use a terminal guard so the stream terminates only once.
- Idempotent cleanup on completion, error, cancellation, and quota exceeded.
- Cancel futures/subscriptions/producers when the stream ends.
- Do not retain the RPC's principal or Context in long-lived background jobs.
- Release the concurrency permit when the call finishes.
- Do not emit more onNext calls after onError/onCompleted.

If work must continue after the RPC ends, create an independent job with its own identity, quota, deadline, and state rather than extending the stream lifecycle to hold resources.

## 13. Client retry and resume upon reaching the message limit

Clients should not automatically retry the entire stream from the beginning upon receiving RESOURCE_EXHAUSTED. If the server already processed some messages, retrying can create duplicate side effects.

For uploads or event ingestion, use:

- **Sequence number:** identifies message order.
- **Idempotency key:** identifies an already processed operation or item.
- **Resume cursor:** continues from the position confirmed by the server.
- **Acknowledgement:** server confirms committed messages.
- **Transfer/session ID:** links reconnected streams belonging to the same operation.

With server-streaming, responses can include the latest cursor. When the stream hits the count limit, the client opens a new stream from that cursor. With bidirectional streams, the two directions may need independent sequences.

Retries should use backoff and jitter while respecting new quotas. If the server rejects because a stream exhausted its message budget, reconnecting only helps when the contract grants a new session or allows resuming; repeatedly opening new streams without changing the cursor/quota only repeats the error.

## 14. Observing message counts in operations

Track by method and quota tier:

- Average and p95/p99 inbound/outbound message count per stream.
- Number of streams terminated due to message-count limits.
- Number of messages rejected as N+1.
- Total bytes and message counts together.
- Stream duration and message rate.
- Active stream count and queued callback count.
- RESOURCE_EXHAUSTED status rate by method.
- Reconnect/resume rate after hitting quota.

Metrics should use method, direction, and status as labels with controlled cardinality. Do not use arbitrary stream IDs, request IDs, or user IDs as metric labels. Logs may record controlled correlation IDs for investigation, but never log sensitive payloads.

If many streams terminate right at the limit, that may be normal contract behavior or a sign the limit is too low. Compare limit hits against throughput, downstream cost, and reconnect frequency before adjusting.

## 15. Testing N and N+1 boundaries

Tests must verify the exact number of accepted messages:

| Messages sent | Expectation when limit is N |
| --- | --- |
| 0 | Stream may complete if contract allows an empty stream |
| N-1 | Accepted |
| N | Nth message accepted |
| N+1 | Over-threshold message rejected; business logic does not run for that message |

Cover each direction:

- Client-streaming: send N requests, then request N+1.
- Server-streaming: source emits N responses, then response N+1.
- Bidirectional: test inbound and outbound budgets independently.
- Combined budget: if present, test total requests + responses.
- Concurrent streams: stream A's counter does not reduce stream B's quota.
- Cancellation before reaching N: cleanup and permit release occur.
- Retry/resume: no duplicate processing of committed messages.

Key assertions:

1. Counter does not exceed N.
2. Message N is processed exactly once.
3. Message N+1 causes no side effects.
4. RPC ends with RESOURCE_EXHAUSTED if the contract chooses termination.
5. No onNext after a terminal signal.
6. Cleanup and permit release happen exactly once.
7. Two concurrent streams have independent counters.

Use in-process gRPC tests or transport integration tests with generated stubs. Control streams using CountDownLatch, CyclicBarrier, or test observers instead of Thread.sleep. Check both application counters and downstream state to catch messages processed before the quota check.

For Spring application tests, start the starter-managed server configuration, inject a policy with a small limit (e.g., N=2), open a stream via a generated stub, and send N+1 messages. Verify the third message does not enter the use case, the client receives the contract status, and admission/cleanup beans are wired. This test complements in-process tests with manually constructed interceptor chains because it verifies the real Spring configuration.

## 16. Hands-on exercises and self-check questions

### Hands-on exercises

1. Create a client-streaming method receiving UploadItemRequest and set a 1,000-message limit.
2. Create a MessageBudget using AtomicLong/CAS with a separate instance per stream.
3. Increment the counter before validation/use case; reject message N+1 with RESOURCE_EXHAUSTED.
4. Create a server-streaming method limiting response count and stopping the source when quota runs out.
5. For bidirectional streaming, set separate inbound and outbound budgets.
6. Combine max message size, total bytes, deadline, and stream concurrency.
7. Add cancellation cleanup, terminal guards, and resume cursors for long uploads.
8. Write integration tests for N-1, N, N+1, two concurrent streams, and cancellation.

### Self-check questions

**1. How does a message count limit differ from max message size?**  
Message count limits the number of messages in one RPC; max message size limits the bytes of each message.

**2. Where should client-streaming count?**  
In the callback receiving request messages, before validating and executing side effects.

**3. Where should server-streaming count?**  
Right before emitting each response via the observer.

**4. Does bidirectional streaming need one counter or two?**  
Usually separate inbound and outbound counters are needed; add a combined budget only if the contract explicitly defines it.

**5. Which status is appropriate when the message-count quota is exceeded?**  
RESOURCE_EXHAUSTED.

**6. Does flow control replace a count limit?**  
No. Flow control limits in-flight messages; a count limit bounds total messages across the entire stream.

**7. Why must counters be per-stream?**  
So one RPC does not consume another RPC's quota and to avoid mixing state across tenants/callers.

**8. Should the client retry the whole stream after RESOURCE_EXHAUSTED?**  
Not automatically. Sequences, idempotency, and resume cursors are needed to avoid reprocessing committed data.

## Summary

Limiting the number of messages in a stream controls the total number of message exchanges in a single RPC. Clearly define inbound/outbound directions, create a separate counter per stream, and consume quota before running business logic or emitting responses. Client-streaming, server-streaming, and bidirectional streaming have different counting points; bidirectional usually needs two separate budgets. Combine message count with byte quotas, max message size, rate limits, flow control, deadlines, and stream concurrency to protect resources. When the threshold is exceeded, terminate with RESOURCE_EXHAUSTED per contract, clean up all resources, and support resume/idempotency if clients need to continue. Integration tests must verify N-1, N, N+1, side effects, cancellation, and isolation between concurrent streams.
