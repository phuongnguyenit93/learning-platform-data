# Retrying server streaming and stream position

## 1. Why does server streaming need stream position?

In **Spring gRPC**, a server-streaming RPC receives one request and emits multiple response messages. For example, a client subscribes to order updates, and the server sends events sequentially with increasing sequence numbers. If the connection drops after the client has processed part of the data, the client needs to know where to resume from.

Retrying a server-streaming RPC does not automatically mean continuing from the last received response. A new RPC typically starts over from the initial request. If the request does not carry a continuation position, the client may receive old data again; if it blindly skips too much data, the client may miss events.

**Stream position** is the point in the logical data stream that the client has processed or from which it wants the server to resume emitting. It can be represented by a sequence, an offset, or a server-issued resume token.

This lesson focuses on three things:

- Understanding the limits of automatic retry for server streaming once the RPC has committed.
- Designing a position/cursor to open a new RPC and resume from the acknowledged point.
- Handling replays, duplicates, gaps, checkpoints, and retention so events are neither lost nor applied with duplicate side effects.

## 2. Automatic retry is not resume

A gRPC retry policy operates at the RPC level. The runtime can replay a call when the call is **uncommitted**, the status matches the retry policy, and attempt/deadline budget remains. A call is considered committed when the client receives response headers or the request exceeds the retry buffer limit.

For server streaming:

- The client sends an initial request, and the server starts the response stream.
- The server may send response headers before or together with the first message.
- Once the client receives headers, the call has committed; errors occurring afterward do not cause gRPC to automatically replay the entire stream.
- Even if no response message has arrived yet, if headers have reached the client, the call may already be committed.

Therefore, you should not build reliability for a long-lived stream simply by raising `maxAttempts`. Automatic retry can be helpful for errors occurring very early, before commitment; **resuming after the stream has started is the application's responsibility**.

| Situation | Can automatic retry apply? | How to handle |
| --- | --- | --- |
| Server fails before call commits, retryable status | Possibly, if policy and budget allow | Let the gRPC runtime retry |
| Client has received response headers | Does not replay a committed call | Open a new RPC using stream position |
| Client processed multiple events then connection dropped | Does not recover from last event via retry policy | Resume from a durable checkpoint |
| Client receives an already-processed event again | Possible during at-least-once resume | Deduplicate by event ID/sequence |
| Cursor past retention | Cannot continue from the old position | Reset snapshot or return error requiring resync |

## 3. Defining stream position clearly

A position must answer the question: **which event will the server start emitting from?** There are two common approaches:

1. **Explicit sequence/offset:** the client sends `after_sequence = 120`; the server starts from sequence 121.
2. **Opaque resume token:** the server issues a token representing the emitted position; the client sends the token back without needing to understand its internal structure.

A sequence is easy to observe and useful when a stream has a linear order. A resume token is more suitable when the position depends on partitions, filters, snapshots, or storage implementation. Tokens should be generated and validated by the server; do not let clients freely tamper with offsets.

A good contract must specify:

- Where the sequence starts and what scope it increments within: entire stream, tenant, partition, or subscription.
- Whether the position means **after the processed event** or **the next event to receive**.
- Which stream/filter/version the token is bound to and whether it expires.
- What error the server returns when a position is no longer valid and how the client must reset.
- Whether events have stable IDs for deduplication across reconnects.

In the example below, `after_sequence` means the client has successfully processed up to that sequence; the server emits starting from the next sequence. `resume_token` carries the same semantics, but as opaque server-issued data.

## 4. Protobuf contract for resume

Example `order_events.proto`:

```proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.v1";

service OrderEvents {
  rpc Watch(WatchRequest) returns (stream OrderEvent);
}

message WatchRequest {
  string tenant_id = 1;
  string order_id = 2;
  oneof position {
    int64 after_sequence = 3;
    string resume_token = 4;
  }
}

message OrderEvent {
  string event_id = 1;
  int64 sequence = 2;
  string resume_token = 3;
  string order_id = 4;
  string event_type = 5;
  bytes payload = 6;
}
```

This contract uses server streaming: one request specifies the order and starting position, and the server emits multiple events. After each event, the server returns a sequence and token representing the position **after that event**.

Several important rules:

- `event_id` stays stable across replays; do not generate a new UUID every time the server replays the same event.
- `sequence` increases monotonically within the stream scope defined by tenant/order and must not be reused for another event.
- `resume_token` is opaque; the client only stores and sends it back, without parsing or manually incrementing the token.
- The new request must preserve the subscription scope (tenant, order, and filters). Changing a filter may produce a different logical stream, making the old position inapplicable.
- If using sequence, `after_sequence=120` means the server starts at 121, not replaying 120.

In distributed systems with multiple partitions, a single sequence may be insufficient. In that case, the token can encode a per-partition offset vector or a specific storage cursor.

## 5. Server: read events from position and continue emitting

The server must validate the cursor before starting the stream. With an explicit sequence, query the event store with `sequence > afterSequence`, preserve ordering, and emit each event. With a token, the server decodes/validates the token and translates it into an internal position.

Pseudocode for a Spring gRPC service:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class OrderEventsGrpcService
        extends OrderEventsGrpc.OrderEventsImplBase {

    private final OrderEventStore eventStore;
    private final ResumeTokenCodec tokenCodec;

    public OrderEventsGrpcService(
            OrderEventStore eventStore,
            ResumeTokenCodec tokenCodec) {
        this.eventStore = eventStore;
        this.tokenCodec = tokenCodec;
    }

    @Override
    public void watch(
            WatchRequest request,
            StreamObserver<OrderEvent> responseObserver) {
        ServerCallStreamObserver<OrderEvent> output =
                (ServerCallStreamObserver<OrderEvent>) responseObserver;

        StreamPosition position;
        try {
            position = resolvePosition(request);
        } catch (InvalidResumeTokenException error) {
            output.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid resume_token")
                    .asRuntimeException());
            return;
        } catch (PositionExpiredException error) {
            output.onError(Status.OUT_OF_RANGE
                    .withDescription("stream position retention expired")
                    .asRuntimeException());
            return;
        }

        EventSubscription subscription = eventStore.subscribe(
                request.getTenantId(),
                request.getOrderId(),
                position);

        Object writeLock = new Object();
        AtomicBoolean terminal = new AtomicBoolean();
        output.setOnCancelHandler(() -> {
            synchronized (writeLock) {
                terminal.set(true);
                subscription.close();
            }
        });
        subscription.start(event -> {
            synchronized (writeLock) {
                if (terminal.get() || output.isCancelled()) {
                    terminal.set(true);
                    subscription.close();
                    return;
                }
                try {
                    output.onNext(toProto(event,
                            tokenCodec.tokenAfter(event)));
                } catch (RuntimeException sendError) {
                    terminal.set(true);
                    subscription.close();
                }
            }
        }, error -> {
            synchronized (writeLock) {
                if (terminal.get()) {
                    return;
                }
                terminal.set(true);
                subscription.close();
                if (!output.isCancelled()) {
                    output.onError(Status.UNAVAILABLE
                            .withDescription("event source temporarily unavailable")
                            .asRuntimeException());
                }
            }
        }, () -> {
            synchronized (writeLock) {
                if (terminal.get()) {
                    return;
                }
                terminal.set(true);
                subscription.close();
                if (!output.isCancelled()) {
                    output.onCompleted();
                }
            }
        });
    }

    private StreamPosition resolvePosition(WatchRequest request) {
        return switch (request.getPositionCase()) {
            case AFTER_SEQUENCE ->
                    eventStore.validatePosition(request.getAfterSequence());
            case RESUME_TOKEN ->
                    tokenCodec.decodeAndValidate(
                            request.getResumeToken(),
                            request.getTenantId(),
                            request.getOrderId());
            case POSITION_NOT_SET -> eventStore.initialPosition(
                    request.getTenantId(), request.getOrderId());
        };
    }
}
```

Types like `OrderEventStore`, `EventSubscription`, `StreamPosition`, and `ResumeTokenCodec` are application abstractions that must be implemented for the actual database or broker. `writeLock` and `terminal` ensure event, error, completion, and cancellation callbacks do not write concurrently or emit after a terminal event. The code highlights these responsibilities:

- Validate the position before reading data.
- Register the subscription from the exact position, rather than reading from the beginning by default when the client sends a cursor.
- Close the subscription when the client cancels or the stream finishes.
- Do not emit anything after a terminal event.
- Distinguish a malformed cursor from a valid cursor whose retention has expired.

In production, the response writer must also have a bounded queue and handle `isReady()`/`setOnReadyHandler()` if the event source can emit faster than the client reads. Never let broker callbacks invoke `onNext()` concurrently from multiple threads.

## 6. Client: checkpoint after successful processing

The client should not save a new position immediately upon receiving an event if applying the event has not finished. If the client crashes after writing the checkpoint but before updating business data, the next resume will skip an unprocessed event.

Safe rules:

1. Receive the event.
2. Check event ID/sequence to detect duplicates or gaps.
3. Apply the business change.
4. Persist the applied data and checkpoint in the same transaction if in the same database.
5. Only after commit treat that position as the continuation point.

Pseudocode:

```java
void onEvent(OrderEvent event) {
    consumerTransaction.execute(() -> {
        if (processedEventRepository.exists(event.getEventId())) {
            return; // Replay: do not apply side effects again.
        }

        long expected = checkpointRepository.currentSequence(
                event.getOrderId()) + 1;
        if (event.getSequence() != expected) {
            throw new SequenceGapException(expected, event.getSequence());
        }

        applyOrderChange(event);
        processedEventRepository.insert(event.getEventId());
        checkpointRepository.save(
                event.getOrderId(),
                event.getSequence(),
                event.getResumeToken());
    });
}
```

This is pseudocode: the transaction must cover the business change, dedup record, and checkpoint together. If these parts live in different stores, a coordination protocol such as inbox/outbox is needed, or you accept at-least-once with an idempotent consumer.

### 6.1. Why must checkpointing come after processing?

| Order | Failure | Consequence |
| --- | --- | --- |
| Save checkpoint first, process after | Process crashes after checkpoint | Event is skipped on resume |
| Process first, checkpoint after, no dedup | Process crashes between steps | Event is replayed and side effects may repeat |
| Processing + dedup + checkpoint in one transaction | Process crashes before commit | All three roll back; event is safely replayed |
| Processing + dedup + checkpoint in one transaction | Process crashes after commit | Resumes from next event; duplicate is recognized |

The practical goal is usually **at-least-once delivery with idempotent processing**, not network-level exactly-once delivery.

## 7. Reconnect and resume on the client

When the response observer receives `onError`, the client creates a new RPC using the latest durable checkpoint. Do not rely on a cursor stored only in RAM because the process can crash.

Pseudocode:

```java
void openSubscription(String tenantId, String orderId) {
    Checkpoint checkpoint =
            checkpointRepository.load(tenantId, orderId);

    WatchRequest.Builder request = WatchRequest.newBuilder()
            .setTenantId(tenantId)
            .setOrderId(orderId);

    if (checkpoint != null && !checkpoint.resumeToken().isBlank()) {
        request.setResumeToken(checkpoint.resumeToken());
    } else if (checkpoint != null) {
        request.setAfterSequence(checkpoint.sequence());
    }

    stub.withDeadlineAfter(10, TimeUnit.MINUTES)
            .watch(request.build(), new StreamObserver<>() {
        @Override
        public void onNext(OrderEvent event) {
            processAndCheckpoint(event);
        }

        @Override
        public void onError(Throwable error) {
            scheduleReconnect(error);
        }

        @Override
        public void onCompleted() {
            // Stream completed normally; only reconnect if the subscription
            // is defined as continuous and the caller is still interested.
        }
    });
}
```

This is a skeleton pattern; ensure only one reconnect loop exists per subscription, cancel timers when the caller stops, and never open multiple concurrent streams sharing the same checkpoint.

The reconnect policy should:

- Retry transient errors such as `UNAVAILABLE` with exponential backoff and jitter.
- Not reconnect indefinitely on authentication errors or invalid requests.
- Use a reasonable deadline for each stream RPC; for long-lived subscriptions, proactively reconnect before operational limits if the system requires it.
- Keep the same tenant, filter, and subscription identity when reusing an old cursor.
- Distinguish `onError` from `onCompleted`: normal completion is not necessarily an error requiring retry.

## 8. Handling duplicates, gaps, and expired cursors

Resuming may commonly replay the last received or processed event, depending on cursor semantics and checkpoint timing. The client must have clear rules:

- **Duplicate:** if the same `event_id` has already been processed, skip side effects, while still verifying sequence/cursor consistency.
- **Gap:** received sequence is greater than expected sequence; stop applying subsequent data and recover from checkpoint or request a snapshot.
- **Out-of-order:** if the source does not guarantee ordering, a bounded buffer or partition-specific checkpoint is required. Do not sort globally if events have causal relationships.
- **Expired cursor:** the server no longer retains the required events. The client must fetch a fresh snapshot and receive a new position as the starting point.
- **Invalid token:** token has a bad signature, wrong tenant/filter, or was tampered with; reject rather than falling back to a default cursor.

An opaque cursor should be bound to tenant, stream identity, filter, and schema version. If a token can be guessed or modified, a client could access events outside its authorized scope.

## 9. Snapshots and event streams must not leave gaps

Some APIs both return a current snapshot and watch new events. If the server reads the snapshot and only then subscribes to the stream, events emitted between the two steps can be lost. If it subscribes to the stream and then reads the snapshot without a consistent boundary, the client may process duplicate or out-of-order events.

A common design:

1. The server creates a snapshot at a **high-water mark** (H).
2. The server returns the snapshot together with a cursor representing position (H).
3. The client applies the snapshot and saves checkpoint (H).
4. The client opens the server stream from `after_sequence=H`, receiving events with sequences greater than (H).

Snapshot creation and the high-water mark must be consistent against the same data source or log mechanism. Otherwise, sequence (H) does not prove the snapshot includes every preceding change cleanly.

## 10. Testing retry and stream position

Tests should cover both stream interruption and recovery:

| Scenario | Assertion |
| --- | --- |
| Stream sends sequences 1–5 then disconnects | Client opens a new RPC from the committed checkpoint |
| Last event received but processing not yet committed | Checkpoint does not advance; event is replayed |
| Event committed but response is replayed | Dedup prevents a second side effect |
| Sequence jumps from 5 to 7 | Client detects the gap, does not silently skip 6 |
| Resume token belongs to another tenant | Server rejects the token |
| Cursor still within retention | Server starts from the event immediately after position |
| Cursor past retention | Server returns reset/snapshot error per contract |
| Snapshot + tail | No events lost between snapshot and stream subscription |
| Failure before receiving headers | Automatic retry may occur if policy allows |
| Failure after receiving headers | Client uses application-layer reconnect/resume |
| Caller cancels subscription | Server-side stream and subscription are closed |

Tests should verify **committed side-effect counts**, not just event callback counts. When checkpoint and business state share the same database, simulate crashes before/after commit to verify no events are lost and none are applied twice.

## 11. Common mistakes

1. **Raising `maxAttempts` to recover long streams.** Automatic retry does not replay committed calls.
2. **Saving the position immediately upon receiving an event.** Crashing before processing finishes can lose data.
3. **Using sequences without defining scope.** A per-partition sequence cannot be compared like a global offset.
4. **Generating a new event ID on replay.** The client cannot recognize duplicates.
5. **Skipping event deduplication.** Resuming can repeat side effects.
6. **Trusting `NOT_FOUND` from a lagging replica.** It can falsely conclude a command/event does not exist.
7. **Not binding tokens to tenant/filter.** Can lead to reading the wrong scope or access vulnerabilities.
8. **Subscribing to the stream after snapshot without a high-water mark.** Events in the gap may be lost.
9. **Reconnecting without backoff.** An outage can trigger an application-layer retry storm.

## 12. Practice exercises

For `orders.v1.OrderEvents/Watch`:

1. Add monotonically increasing sequences and stable event IDs per order stream.
2. Implement a request accepting `after_sequence` or `resume_token`; clearly specify that the position means after the processed event.
3. Write a client that persists the checkpoint in the same transaction as order updates and dedup records.
4. Interrupt the stream after sequence 5, reconnect, and verify the server emits from 6.
5. Simulate a crash after receiving an event but before commit; verify the event is replayed.
6. Simulate an expired cursor; implement snapshot/reset and resume tailing from the high-water mark.
7. Verify that a token cannot be reused across tenants or filters.

**Completion criteria:** learners distinguish automatic retry from application resume, define stream positions unambiguously, persist checkpoints durably after processing, detect duplicates/gaps, and recover streams without dropping or repeating side effects.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry commitment, retry buffer, and replay limits.
- [gRPC Core Concepts](https://grpc.io/docs/what-is-grpc/core-concepts/): RPC lifecycle and server streaming.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): RPC-ending statuses.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
