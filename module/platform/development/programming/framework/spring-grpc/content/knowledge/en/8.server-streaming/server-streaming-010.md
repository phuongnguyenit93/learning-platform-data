# Retrying server streams and replayability

## 1. Why retrying a server stream requires dedicated design?

In **SPRING_GRPC**, server streaming lets the client send one request and receive multiple Protocol Buffers responses over the same RPC. This delivery style suits job progress, events, logs, or large query results. However, a stream can break after the client has already received partial data: the server loses connection to its source, a proxy closes the transport, a deadline expires, or the client temporarily drops off the network.

Example of a client watching a job:

~~~text
RPC attempt 1:
  Client -> WatchJob(after_sequence = 0)
  Server -> Event #1
  Server -> Event #2
  Server -> Event #3
  Server -> UNAVAILABLE

RPC attempt 2:
  Client -> WatchJob(after_sequence = 2)
  Server -> Event #3, #4, #5, ...
  Server -> onCompleted()
~~~

The client durably applied up to #2, but had not necessarily finished processing #3. Upon reconnecting, the server replays #3 so the client does not miss it. Thus, an event already transmitted in the previous attempt may appear again; the client must recognize and safely handle duplicates.

**Retry** means initiating a new call after the previous call fails. **Replay** means the server re-emits events already stored in the data source. **Resume** combines the two with a cursor/checkpoint so the new call continues from the confirmed position.

This is the central point: a server stream that has already received partial data cannot be recovered merely by invoking the same stub again or continuing to use the old iterator. To resume accurately, the application must determine **how far it has durably processed**, and the server must be able to re-read data from that position.

## 2. Distinguishing gRPC automatic retries from application-layer resume

gRPC has a configurable retry mechanism for certain errors and conditions. That mechanism is useful before a call is committed under the runtime's retry rules. However, once a server streaming RPC has begun returning responses and is committed, the client should not expect gRPC to automatically replay already-received messages or resume from missing messages.

| Mechanism | Scope | What it solves | What it does not solve |
|---|---|---|---|
| gRPC retry policy | Single RPC before commit per runtime rules | Retries certain policy-eligible errors | Does not replace checkpoints/replay once the stream has emitted data |
| Manual retry | Client starts a new RPC after failure | Lets you choose timing, statuses, and backoff | Does not automatically know which events the client committed |
| Replay from durable store | Server re-reads events by cursor/offset | Re-delivers previously emitted data | Does not automatically prevent duplicate client application |
| Checkpoint-based resume | Client sends applied position in new request | Continues from confirmed point | Requires stable sequences, retention, and gap/duplicate handling |

A server stream may have already sent response headers before emitting its first message; once the RPC is committed, automatic retry cannot arbitrarily start a fresh session without risking duplicated data. Exact behavior also depends on configuration and runtime. Therefore, designing resilience for long streams should rely on **application-layer retries combined with cursors/replay**, rather than assuming the transport will stitch streams back together.

## 3. Contracts require a stable cursor or sequence

For the server to replay, each event needs a stable identifier and position. Example watching job progress:

~~~proto
syntax = "proto3";

package jobs.v1;

option java_multiple_files = true;
option java_package = "com.example.jobs.rpc";

service JobEventService {
  rpc WatchEvents(WatchEventsRequest) returns (stream JobEvent);
}

message WatchEventsRequest {
  string job_id = 1;
  int64 after_sequence = 2;
}

message JobEvent {
  string job_id = 1;
  int64 sequence = 2;
  string event_id = 3;
  string event_type = 4;
  string payload = 5;
}
~~~

Contract conventions:

- `sequence` increments monotonically scoped within a `job_id`.
- `event_id` stays identical for the same event across replays.
- `after_sequence = N` means the server emits only events with sequence **greater than N**.
- The client advances its checkpoint only after the event is applied and durably saved.

For example, if the client committed through sequence 12, it sends `after_sequence = 12`; the server starts emitting from 13. Do not use `last_received_sequence` as a checkpoint if the client processes asynchronously and has not finished persisting the event.

For complex systems, the cursor may be an opaque token rather than an integer. The token can encode partition, offset, snapshot/version, and validation info. Either way, the server must clearly define scope, validity lifetime, and how expired cursors are reported.

**Sequences alone do not create replayability.** The server needs a durable data source to look up events after the requested position. An in-RAM counter on a single instance is insufficient if clients can reconnect to another instance.

## 4. Client checkpoints only after successful processing

There are three distinct positions:

1. **Server emitted:** server called `onNext(event)`.
2. **Client received:** callback/iterator yielded the event.
3. **Client committed:** business change and checkpoint have been durably saved.

Only the third position is a safe resume point. For example, the client receives #13, updates the UI or starts a database write, and crashes before the transaction commits. If the checkpoint already advanced to 13 before the data was persisted, reconnecting will start at #14 and lose #13.

The processing flow should be:

~~~text
Receive event #13
    |
    v
Check event_id and sequence
    |
    v
Apply business change + save checkpoint in transaction
    |
    v
Transaction commits successfully
    |
    v
New checkpoint = 13
~~~

Java pseudocode example:

~~~java
void applyAndCheckpoint(JobEvent event) {
    transactionTemplate.executeWithoutResult(tx -> {
        if (eventStore.wasApplied(event.getEventId())) {
            checkpointStore.advanceIfNeeded(
                    event.getJobId(), event.getSequence());
            return;
        }

        eventStore.apply(event);
        eventStore.markApplied(event.getEventId());
        checkpointStore.advanceIfNeeded(
                event.getJobId(), event.getSequence());
    });
}
~~~

This is illustrative logic; the check, apply, mark, and checkpoint save operations must share one transaction if they live in the same database. If the business side effect lives in another system, use an idempotency key or appropriate inbox/outbox pattern. Never assume two independent writes always succeed together.

When the client has committed #13 but drops before the server knows, a reconnect might still request after #13 or receive #13 again if the checkpoint was not persisted/synced properly. `event_id` and idempotent handling ensure redelivery never causes duplicate side effects.

## 5. Server must read history and switch to live without losing events

A common design bug is reading the backlog first and only then registering a listener for new events:

~~~text
1. Read history up to #100
2. Event #101 arrives
3. Server registers listener

Result: #101 can be missed.
~~~

The server needs a **consistent handoff point** between historical data and the live stream. Depending on the source, options include:

- Using a broker with offsets/cursors and a consumer API supporting resuming from an offset.
- Taking a consistent watermark/snapshot, subscribing to live first, buffering new events, emitting the backlog up to the watermark, and draining the buffer in sequence order.
- Using datastore transactions or subscription mechanisms that guarantee zero gap between reading history and receiving new events.

Subscribe-first-then-replay model:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as gRPC server
    participant E as Event store
    C->>S: WatchEvents(after_sequence = 100)
    S->>E: Register live subscription
    S->>E: Read durable events > 100
    E-->>S: #101, #102
    E-->>S: Live #103 (buffered)
    S-->>C: #101
    S-->>C: #102
    S-->>C: #103
    Note over S,C: Transition to live without creating a gap
~~~

The diagram illustrates the principle without dictating a specific broker API. If the subscription emits events during replay, the server must maintain a bounded buffer, deduplicate by sequence, and use a single sequential sender to call `onNext`. If buffering is impossible or the source lacks a reliable cursor, choose another policy and clearly document recovery limits.

## 6. Client retrying with backoff and checkpoints

When a server stream ends in error, the client must create a **new RPC** with `after_sequence` taken from the durable checkpoint. Never reuse a failed iterator. Retries should use exponential backoff with jitter to prevent many clients from reconnecting simultaneously.

Strategy example:

~~~text
Failure 1: wait randomly ~200–400 ms
Failure 2: wait randomly ~400–800 ms
Failure 3: wait randomly ~800–1600 ms
...
Max backoff cap: e.g., 5 seconds
Total retry time budget: per business budget
~~~

Not every status should be retried:

| Status | Typical handling |
|---|---|
| `UNAVAILABLE` | Can retry with backoff if source outage is transient and cursor remains valid |
| `RESOURCE_EXHAUSTED` | Shed load; retry only after appropriate wait/quota policy |
| `DEADLINE_EXCEEDED` | Re-evaluate time budget; retry only if budget remains and action is safe |
| `CANCELLED` | Do not auto-retry if proactively cancelled by user or parent task |
| `UNAUTHENTICATED` | Refresh credentials per policy before considering calling again |
| `PERMISSION_DENIED` | Do not keep retrying with the same credentials/permissions |
| `INVALID_ARGUMENT` | Fix the request; retrying verbatim will not help |
| `FAILED_PRECONDITION` | May need to resync snapshot or obtain a new cursor per contract |

Status is only one input to the decision. For example, `UNAVAILABLE` may be transient, yet if the data source already purged history, retrying with the same cursor will still fail. `RESOURCE_EXHAUSTED` may include wait guidance; the client must respect quotas instead of hammering retries.

### 6.1. Blocking client example

The following snippet illustrates a reconnect loop. Helpers `isRetryable`, `sleepWithJitter`, and repository/checkpoint components belong to the application and must match your system policy.

~~~java
long checkpoint = checkpointStore.load(jobId);
long retryDelayMs = 200;
long retryDeadline = System.nanoTime()
        + TimeUnit.MINUTES.toNanos(2);

while (System.nanoTime() < retryDeadline) {
    WatchEventsRequest request = WatchEventsRequest.newBuilder()
            .setJobId(jobId)
            .setAfterSequence(checkpoint)
            .build();

    long remainingNanos = retryDeadline - System.nanoTime();
    long attemptNanos = Math.min(
            remainingNanos, TimeUnit.SECONDS.toNanos(20));

    try {
        var responses = JobEventServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(attemptNanos, TimeUnit.NANOSECONDS)
                .watchEvents(request);

        while (responses.hasNext()) {
            JobEvent event = responses.next();

            if (event.getSequence() <= checkpoint) {
                continue; // Possibly a replayed event; deduplicate by event_id.
            }
            if (event.getSequence() != checkpoint + 1) {
                throw new MissingSequenceException(
                        "Expected " + (checkpoint + 1)
                        + " but received " + event.getSequence());
            }

            applyAndCheckpoint(event); // Commit data and checkpoint.
            checkpoint = event.getSequence();
        }

        return; // Iterator exhausted normally: RPC completed successfully.
    } catch (StatusRuntimeException error) {
        if (!isRetryable(error.getStatus())) {
            throw error;
        }

        sleepWithJitter(retryDelayMs);
        retryDelayMs = Math.min(retryDelayMs * 2, 5_000);
    }
}

throw new IllegalStateException("Resume budget exhausted");
~~~

The example assumes `channel`, `jobId`, `checkpointStore`, `applyAndCheckpoint`, `MissingSequenceException`, `isRetryable`, and `sleepWithJitter` are already defined. `applyAndCheckpoint` must return only after the transaction commits. In a real application, catch sequence-gap errors separately to resync or surface a data error; do not treat them as transient errors to retry endlessly.

The loop enforces a two-minute overall deadline and a maximum 20-second deadline per attempt. `System.nanoTime()` is suited for measuring elapsed time within the same process. Backoff must include jitter, cap retry counts/duration, and can reset once a stream session has remained healthy long enough.

`Thread.sleep` inside the helper must run only on a worker thread dedicated to retries, never on an event loop or web request-serving thread.

## 7. When a cursor expires or history is gone

Event sources usually have finite retention. For example, a client goes offline for three days while the server retains events for seven days. If a checkpoint is older than the earliest retained watermark, the server cannot replay the entire missing range.

The server should return a meaningful status, such as `FAILED_PRECONDITION`, with a safe description indicating the client needs to resync a snapshot or start a fresh reading session. Never silently skip old events and call `onCompleted()` as though the data were complete.

A resync flow can be:

1. Client detects the cursor has expired.
2. Client calls an API to fetch a consistent current snapshot.
3. Server returns the snapshot together with watermark sequence `W`.
4. Client atomically persists the snapshot and checkpoint `W`.
5. Client opens a new server stream with `after_sequence = W`.

Crucially, the snapshot and the watermark must correspond to the exact same logical state. If the snapshot is taken at a different point than the watermark, events can be missed or applied twice.

## 8. Retry is not synonymous with exactly-once

After a network error, the client may not know whether the server emitted the last event; the server also does not know whether the client committed the last event. That is why a resume protocol typically must tolerate replay:

- **At-most-once:** avoids duplicate delivery, at the risk of losing events when the client misses the tail.
- **At-least-once:** replays from checkpoint, potentially delivering duplicates; client deduplicates/stays idempotent to prevent repeated side effects.
- **Exactly-once effect:** not a default gRPC guarantee. An effectively exactly-once outcome within a single transaction/business key can be achieved via idempotency, unique constraints, and consistent checkpoints; this requires explicit design.

For most event streams that cannot lose data, at-least-once paired with idempotent processing is the practical choice. Clients must treat `event_id` or `(resource_id, sequence)` as a stable deduplication key.

If an RPC performs a side effect (e.g., creating a job or issuing a payment command), never retry blindly just because the client received `UNAVAILABLE`. Deadlines or transport errors do not prove the server did not execute the side effect. Use idempotency keys and status-query APIs to check the outcome before re-issuing commands.

## 9. Testing retries and replay

Tests must verify both transport flow and durable application state:

| Scenario | Outcome to verify |
|---|---|
| Stream completes normally | Client receives all events and opens no new RPC |
| Server emits #1–#3 then `UNAVAILABLE` | Client saves correct checkpoint and opens a new RPC |
| Client receives #3 without committing | Resume may receive #3 again; no data lost |
| Client committed #3 | New request uses `after_sequence = 3` |
| Replayed event is duplicated | Client deduplicates, no second side effect |
| Sequence skipped | Client detects gap, does not silently advance checkpoint |
| Cursor still valid | Server replays backlog and switches to live without gaps |
| Cursor past retention | Server signals snapshot resync is needed |
| Client proactively cancels | Does not auto-reconnect when user stopped |
| Many clients reconnect together | Backoff/jitter smooths traffic spikes |
| Job triggers side effects | Retry uses idempotency key or checks status first |

An in-process test can configure a server to send two events and terminate with `UNAVAILABLE`, then on the next call replay the second event and send the third event. The test must verify the client applies the second event only once. Beyond transport tests, write integration tests against a real event store or a test double supporting cursors/retention to verify replay-to-live handoff logic.

## 10. Operational observability and security

In Spring gRPC, interceptors and metrics/tracing systems can record method, duration, status, and correlation ID. For retry/replay, add business-layer metrics:

| Metric | Purpose |
|---|---|
| New stream RPCs opened after errors | Monitor reconnect frequency |
| Status of prior attempt | Separate transient vs. non-retryable errors |
| Checkpoint before/after reconnect | Know exact resume position |
| Replayed and duplicate event counts | Measure at-least-once overhead |
| Sequence gaps | Detect lost data or handoff bugs |
| Expired cursor / resync count | Evaluate whether retention is long enough |
| Backoff and recovery duration | Evaluate client experience |
| Queue depth and concurrent stream count | Detect load spikes caused by reconnects |

Use TLS in production environments, authenticate callers, and authorize per `job_id`/resource before allowing replay. A cursor must never serve as the sole proof authorizing data access. Avoid putting tokens, sensitive payloads, or internal details in logs/statuses.

## 11. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Restarting RPC from sequence 0 after every error | Client reprocesses the entire dataset | Resume from committed checkpoint |
| Using last received sequence as checkpoint | Can drop uncommitted events | Persist checkpoint only after durable processing |
| Assuming gRPC auto-replays received responses | Loses data after reconnect | Build cursors and a replay source |
| Server keeping sequences in RAM of one instance | Reconnecting to another instance mismatches order | Stable sequences from an event store |
| Reading backlog first, then subscribing to live | Leaves an event gap | Consistent history/live handoff |
| Retrying every status code | Repeats auth errors, bad requests, or overload | Classify statuses and cap retries |
| No backoff/jitter | Multiple clients cause a retry storm | Exponential backoff, jitter, and quotas |
| Not deduplicating replayed events | Duplicate side effects | Event IDs, idempotency, and transactions |
| Cursor expired yet server returns newer data | Client believes it received full history | Signal resync clearly with an appropriate status |

### Self-check questions

1. Why does a gRPC retry policy not replace resume capability once a server stream has already emitted responses?
2. Should the client save the last received sequence or the last committed sequence?
3. What exact meaning must `after_sequence = 12` have on the server?
4. Why must the server handle the window between reading the backlog and registering the live subscription?
5. When should `UNAVAILABLE` be retried, and why should `PERMISSION_DENIED` not be retried repeatedly?
6. What risk does at-least-once replay introduce, and how does the client handle it?
7. When a cursor is past retention, why is a snapshot needed together with a watermark?

**Key takeaway:** Retrying a server stream means opening a new RPC; replay means re-reading events from durable storage; resume uses checkpoints/cursors to continue past what the client committed. For safe recovery, the server must maintain stable sequences and bridge history to live without gaps; the client must checkpoint after durable processing, deduplicate replayed events, and retry with backoff based on status. gRPC transports the stream, while replayability and idempotency belong to application design.
