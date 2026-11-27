# Errors after emitting partial data

## 1. A stream can fail after the client has already received data

In **SPRING_GRPC**, gRPC services use Protocol Buffers contracts and generated Java code to communicate between clients and servers in the Spring ecosystem. With **server streaming**, the client sends one request, and the server emits multiple responses sequentially over the same RPC. Unlike a unary call, server streaming may have already delivered part of the result before encountering an error.

For example, a client requests an account's transaction history. The server sends the first three transactions, but the data source loses connectivity before reading the fourth transaction:

~~~text
Client sends:  WatchLedger(account_id = "A-42")

Server emits:  #1  DEPOSIT  100
               #2  PAYMENT  25
               #3  REFUND   10
               X   Database connection lost

RPC ends:      onError(UNAVAILABLE)
~~~

The client may have already received and processed three transactions, yet **the overall RPC did not complete successfully**. It must distinguish received data from a complete result. If the client merely displays an error message and discards the three received responses, already-processed data may appear lost from the user's perspective. If the client treats the three responses as a complete result, it may make incorrect decisions because unread transactions remain.

This topic focuses on understanding and handling **errors after emitting partial data**:

- The meaning of sent responses, received responses, and applied responses.
- How the server ends a stream with an error status after several `onNext` calls.
- How the client preserves partial progress without marking the RPC complete.
- Distinguishing stream-wide errors from single-item errors.
- Designing sequences, checkpoints, and resume to prevent lost or duplicate data.
- Testing the case where a few responses are received before an error status arrives.

## 2. Three milestones that must not be equated

When a stream fails, asking "how far did the server send?" is not the same as "how far did the client process?". There are at least three distinct milestones:

| Milestone | Meaning | How can it be verified? |
|---|---|---|
| **Server emitted** | Server called `responseObserver.onNext(event)` | Server-side logs/metrics |
| **Client received** | Client-side `onNext(event)` callback or iterator yielded the message | Client-side logs/metrics |
| **Client durably applied** | Client business logic successfully processed and persisted result/checkpoint | Storage state or application-layer ACK |

For instance, the server called `onNext(#4)`, but the connection dropped before the client received that message. The server cannot rely solely on calling `onNext` to conclude the client saved #4. Conversely, the client may have received #3, yet failed before its own database write completed.

~~~mermaid
flowchart LR
    A["Server onNext(#1..#3)"] --> B["gRPC / HTTP/2 transport"]
    B --> C["Client callback receives #1..#3"]
    C --> D["Client processes and saves checkpoint"]
    D --> E["Applied up to sequence 2"]
    A -. "Data source failure after #3" .-> F["onError(UNAVAILABLE)"]
    F --> C
~~~

The diagram illustrates one scenario: the client received up to #3 but only durably persisted up to #2. When the RPC fails, the safe resume point may be #2, not #3. The client must base its checkpoint on **its own processing outcome**, not on how many messages the server produced or how many callbacks started.

## 3. Termination rule: onNext followed by onError

Server streaming uses `StreamObserver<ResponseT>`:

- `onNext(response)` emits one message. The server can call it multiple times while the RPC is active.
- `onCompleted()` ends the RPC successfully when no more responses remain.
- `onError(throwable)` ends the RPC with an error and corresponding gRPC status.

A stream can validly terminate in this sequence:

~~~text
onNext(event #1)
onNext(event #2)
onNext(event #3)
onError(Status.UNAVAILABLE)
~~~

After `onError`, the server must not call `onNext` or `onCompleted`. `onError` is a terminal signal. On a normally functioning transport, responses sent before the terminal status are observed in order before the client receives the termination callback. However, if the transport fails, the client may receive only a subset of in-flight messages.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring gRPC server
    participant DB as Data source
    C->>S: WatchLedger(account_id)
    S->>DB: Read next entries
    DB-->>S: Entry #1
    S-->>C: onNext(#1)
    DB-->>S: Entry #2
    S-->>C: onNext(#2)
    DB-->>S: Entry #3
    S-->>C: onNext(#3)
    DB--xS: Connection lost
    S-->>C: onError(UNAVAILABLE)
    Note over C: Keep partial progress; RPC is incomplete
~~~

Crucial point: **an error after data does not erase responses the client already received**. Yet those responses do not turn a failed RPC into a successful RPC either.

## 4. Protocol Buffers contract needs item identification

A stream that can recover after failure needs a way to identify each item and its order. Example reading a transaction ledger:

~~~proto
syntax = "proto3";

package ledger.v1;

option java_multiple_files = true;
option java_package = "com.example.ledger.rpc";
option java_outer_classname = "LedgerProto";

service LedgerService {
  rpc ReadLedger(ReadLedgerRequest) returns (stream LedgerEntry);
}

message ReadLedgerRequest {
  string account_id = 1;
  int64 after_sequence = 2;
}

message LedgerEntry {
  string account_id = 1;
  int64 sequence = 2;
  string entry_id = 3;
  string entry_type = 4;
  int64 amount_minor_units = 5;
}
~~~

`sequence` is an incrementing number scoped per account; `after_sequence` asks the server to emit only items after a saved checkpoint. For example, if the client has applied up to #2, it opens a new session with `after_sequence = 2` to continue from #3.

This contract **only declares resume capability**; it does not automatically provide it. The server must have a data source supporting sequence-based replay, retain history long enough, and ensure zero gaps when transitioning from reading history to receiving live events.

A useful sequence must have these properties:

1. **Stable:** replaying the same item retains the same sequence and ID.
2. **Scoped:** define whether sequence increments per account, job, or partition; do not use an unscoped counter.
3. **Deterministic order:** if business logic requires ordering, the server must query or sort by that rule.
4. **Verifiable:** the client can detect duplicate or skipped sequences.
5. **Not synonymous with ACK:** sequence indicates item position, while the client checkpoint records which items were durably applied.

Do not rely solely on timestamps as a cursor if multiple events can share a timestamp, clocks across sources differ, or backdated entries can be inserted. Monotonically increasing IDs or stably ordered composite keys are usually easier to recover with.

## 5. Server emitting partial data then terminating with an error status

The example service below reads data from a source that can fail mid-iteration. The key illustration is **never calling `onCompleted()` when the source fails**; the server terminates with an unsuccessful status.

~~~java
package com.example.ledger;

import com.example.ledger.rpc.LedgerEntry;
import com.example.ledger.rpc.LedgerServiceGrpc;
import com.example.ledger.rpc.ReadLedgerRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

import java.util.Iterator;
import java.util.stream.Stream;

@Service
public class LedgerServiceImpl
        extends LedgerServiceGrpc.LedgerServiceImplBase {

    private final LedgerRepository repository;

    public LedgerServiceImpl(LedgerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void readLedger(
            ReadLedgerRequest request,
            StreamObserver<LedgerEntry> responses) {

        String accountId = request.getAccountId().trim();
        if (accountId.isEmpty() || request.getAfterSequence() < 0) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid account_id or after_sequence")
                    .asRuntimeException());
            return;
        }

        try (Stream<LedgerRow> rows =
                     repository.streamAfter(accountId, request.getAfterSequence())) {
            Iterator<LedgerRow> iterator = rows.iterator();

            while (iterator.hasNext()) {
                LedgerRow row = iterator.next();
                responses.onNext(toProto(row));
            }
        } catch (DataAccessException sourceFailure) {
            // Some responses may already have been emitted before the source error.
            // The terminal status for the whole RPC is an error; do not call onCompleted().
            responses.onError(Status.UNAVAILABLE
                    .withDescription("Ledger source became unavailable")
                    .asRuntimeException());
            return;
        }

        // Only complete successfully after reading and closing the data source normally.
        responses.onCompleted();
    }

    private LedgerEntry toProto(LedgerRow row) {
        return LedgerEntry.newBuilder()
                .setAccountId(row.accountId())
                .setSequence(row.sequence())
                .setEntryId(row.entryId())
                .setEntryType(row.entryType())
                .setAmountMinorUnits(row.amountMinorUnits())
                .build();
    }
}
~~~

`LedgerRepository` and `LedgerRow` are illustrative application types. In a real project, `streamAfter(...)` must return a closeable resource and handle RPC cancellation. The example focuses on data-access failure: if `iterator.hasNext()` or `iterator.next()` throws `DataAccessException` after emitting several responses, the server calls `onError(UNAVAILABLE)` and never calls `onCompleted()`.

Design points:

- **Validate before emitting:** request errors are returned before the first response.
- **Map source errors:** `UNAVAILABLE` fits when a dependency is temporarily unavailable; another code may be more appropriate for data corruption or programming bugs.
- **Do not leak exceptions:** status descriptions must not contain SQL, hostnames, credentials, or stack traces. Technical details go into controlled internal logs/traces.
- **One terminal signal:** the error branch calls `onError` and returns; the success branch calls `onCompleted` after the source stream closes cleanly.
- **Partial data is real:** responses already received by the client may be retained; the server cannot roll back client side effects.

This synchronous code illustrates the source-failure flow. If queries can block for long or streams are long-lived, design an async producer, cancellation handler, and backpressure. Never hold an RPC thread waiting indefinitely on a data source.

### 5.1. Choosing a status when failing after partial data?

The status must describe why **the RPC could not complete**, not just that one item had a problem:

| Status | Example | What the client should understand |
|---|---|---|
| `UNAVAILABLE` | Database or downstream service temporarily lost connection | Can retry later if source and contract allow resume |
| `INTERNAL` | Unexpected error in server processing | RPC failed; server investigation needed |
| `RESOURCE_EXHAUSTED` | Server out of quota or exceeded resource limit | Can back off/wait per policy |
| `PERMISSION_DENIED` | Read permission rejected | Do not retry with same identity/permissions |
| `NOT_FOUND` | Account or source object does not exist | No data to continue with that identifier |
| `DATA_LOSS` | Corrupted data or integrity loss detected | Handle per data policy, do not retry blindly |

`INVALID_ARGUMENT` is usually appropriate for malformed requests before the stream starts. If a serious integrity error is detected mid-stream, choose the status per contract and error semantics; never use `OK` to mask incomplete data.

## 6. Client receiving messages and then encountering onError

With the asynchronous stub, the client supplies a `StreamObserver<LedgerEntry>`. The `onNext` callback may fire multiple times before `onError` signals RPC failure.

~~~java
import com.example.ledger.rpc.LedgerEntry;
import com.example.ledger.rpc.LedgerServiceGrpc;
import com.example.ledger.rpc.ReadLedgerRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.atomic.AtomicLong;

AtomicLong lastApplied = new AtomicLong(0);

ReadLedgerRequest request = ReadLedgerRequest.newBuilder()
        .setAccountId("A-42")
        .setAfterSequence(lastApplied.get())
        .build();

LedgerServiceGrpc.newStub(channel)
        .withDeadlineAfter(30, TimeUnit.SECONDS)
        .readLedger(request, new StreamObserver<LedgerEntry>() {
            @Override
            public void onNext(LedgerEntry entry) {
                // applyIdempotently must complete and durably persist the checkpoint.
                applyIdempotently(entry);
                lastApplied.set(entry.getSequence());
            }

            @Override
            public void onError(Throwable error) {
                Status status = Status.fromThrowable(error);
                System.err.println("Ledger stream failed: " + status);
                System.err.println(
                        "Last successfully applied sequence: " + lastApplied.get());
                // Report to caller that this is a partial result, not completion.
            }

            @Override
            public void onCompleted() {
                System.out.println("Ledger stream completed successfully");
                // Only here mark this read pass as complete.
            }
        });
~~~

The example assumes `channel`, `TimeUnit`, and `applyIdempotently(...)` are defined. In real applications, keep data updates and checkpoint persistence consistent: if data is applied but the checkpoint is not saved, resuming may redeliver the event; hence the apply step must be idempotent or share a transaction with the checkpoint.

**Do not set completion state inside `onNext`.** `onNext` only proves the callback received one message. Only `onCompleted` represents normal RPC completion. If `onError` occurs, the client must retain partial state and report the final error to the calling layer.

### 6.1. Blocking stub can also throw an error after a few messages

With a blocking stub, responses are read via `Iterator<LedgerEntry>`. If the server terminates with an error status after some messages, the client can retrieve earlier messages and then encounter `StatusRuntimeException` when checking/reading the next element:

~~~java
var iterator = LedgerServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(30, TimeUnit.SECONDS)
        .readLedger(request);

long lastApplied = 0;
try {
    while (iterator.hasNext()) {
        LedgerEntry entry = iterator.next();
        applyIdempotently(entry);
        lastApplied = entry.getSequence();
    }
    markReadCompleted();
} catch (StatusRuntimeException error) {
    System.err.printf("Read failed after sequence %d: %s%n",
            lastApplied, error.getStatus());
    markReadPartial(lastApplied, error.getStatus());
}
~~~

The snippet requires importing `StatusRuntimeException`, `TimeUnit`, and application functions. Never place `markReadCompleted()` inside the loop: if the final status is an error, the client must not report that the entire history was read.

## 7. Stream-wide error or single-item error?

This is an important API design decision. Not every failure while processing one item should fail the entire RPC.

### 7.1. Stream-wide error

Use a terminal gRPC status when the server can no longer provide results per contract:

- The data source is no longer reachable.
- The server loses permission to access a required resource.
- The snapshot/cursor is no longer valid and cannot continue.
- Data is no longer trustworthy enough to emit subsequent parts.

Example: three transactions were emitted, then the database loses connectivity. The server calls `onError(UNAVAILABLE)`. The client receives partial results and must decide whether to resume, display, or discard received parts per business policy.

### 7.2. Single-item error while the stream continues

If each item is independent and the contract permits per-item outcomes, errors can be represented inside the message itself. For example, a report processes 100 records; record 12 is invalid, yet the remaining 99 can still be processed:

~~~proto
message ItemResult {
  int64 sequence = 1;
  string item_id = 2;
  bool succeeded = 3;
  string error_code = 4;
  string error_message = 5;
}

service BatchService {
  rpc ProcessItems(ProcessItemsRequest) returns (stream ItemResult);
}
~~~

In this design, an `ItemResult` can report `succeeded = false`; the server continues emitting other results and calls `onCompleted()` if the overall processing session ends per contract. **An item error is stream data; a stream-wide error is the RPC's terminal status.**

Do not send `onError` for a predictable, independently handled item error if the client is expected to keep going. Conversely, do not disguise a catastrophic source failure as a `succeeded = false` message and keep emitting incomplete or inconsistent data.

| Question | If answer is "yes" | Suggested design |
|---|---|---|
| Items are independent; one item failing doesn't affect the rest? | Yes | Per-item result message, ending with `onCompleted` |
| Remaining results cannot be determined after source error? | Yes | Terminal `onError` with appropriate status |
| Client must have the entire result set before using it? | Yes | Stage results and commit only on `onCompleted` |
| Client may use received results even if the rest fail? | Yes | Incremental apply, checkpoint, and resume |

## 8. Resuming after failure: sequence and checkpoint

When a stream fails after emitting partial data, retrying from the beginning can cause duplicate processing. A resume contract typically uses sequence numbers:

~~~text
Attempt 1:
    Client sends after_sequence = 0
    Server emits #1, #2, #3
    Server fails -> onError(UNAVAILABLE)
    Client durably applies only #1, #2

Attempt 2:
    Client sends after_sequence = 2
    Server emits #3, #4, #5, ...
    Server onCompleted()
~~~

The starting point for the second attempt is the **persisted checkpoint**, not the highest sequence the server produced or the client merely saw in a callback. In the example, #3 may be re-emitted because the client has not yet confirmed applying it.

### 8.1. Checkpoint rules

1. Receive event.
2. Validate sequence and ID.
3. Apply business change idempotently.
4. Write checkpoint after the change has been committed.
5. Only then consider the sequence applied.

If data and checkpoints live in the same database, update them within a single transaction. If they reside in separate systems, use an appropriate deduplication/idempotency or outbox/inbox strategy; never assume two independent writes always succeed together.

Client-side logic example:

~~~java
void applyAndCheckpoint(LedgerEntry entry) {
    transactionTemplate.executeWithoutResult(tx -> {
        if (ledgerStore.wasApplied(entry.getEntryId())) {
            return; // Replayed event; do not apply a second time.
        }

        ledgerStore.apply(entry);
        checkpointStore.save(
                entry.getAccountId(), entry.getSequence());
    });
}
~~~

This is pseudocode depending on your application's transaction and repository setup. `wasApplied`, `apply`, and `save` must uphold a consistent invariant together; saving checkpoints without deduplicating by ID/sequence allows retries to cause duplicate side effects.

### 8.2. Server must ensure gapless transition from history to live events

With a continuous event source, the server may read historical events after `after_sequence`, then subscribe to new events. If those two steps are not atomic:

~~~text
Read history up to #10
             #11 arrives
Register subscription
~~~

Event #11 may be missed between the two steps. The fix depends on the system: broker offsets/consumers, watermarked snapshots, subscribing first and filtering by sequence, or consistent datastore cursors. After resuming, the client should detect gaps if it expects sequence 11 but receives 12.

**There is no free replay in gRPC.** gRPC transports messages over an RPC; history retention, cursors, replay, and deduplication are responsibilities of the application or underlying event system.

## 9. Should the client keep or discard partial results?

No single policy fits every domain. Two common models exist:

### 9.1. Incremental apply: each valid response has independent value

For example, validated transactions recorded in a ledger. The client can apply each event idempotently and save a checkpoint. When the stream fails, committed events remain valid; the next connection resumes from the checkpoint.

Pros:

- Data is usable early.
- Reduces how many results must be held in memory.
- Can resume from saved progress.

Requirements:

- Stable sequences, unique IDs, and idempotent operations.
- Checkpoints must never advance ahead of committed data.
- Replay and gap/duplicate handling mechanisms.

### 9.2. Stage then commit: publish only when the stream finishes

For example, generating an aggregate report that requires every part before publishing. The client writes responses into a temporary staging area without marking the report complete. Upon `onCompleted`, the client verifies sequence completeness and commits/publishes. Upon `onError`, staging data is either kept for resume or discarded per policy.

Pros:

- Users never see an incomplete report mistaken for finished.
- Whole-dataset validation can run before publishing.

Trade-offs:

- Requires staging memory or storage.
- Requires cleaning up expired temporary data.
- May require resume instead of restarting from scratch.

| Characteristic | Incremental apply | Stage then commit |
|---|---|---|
| Early use of responses | Yes | Not published externally yet |
| Mid-stream error handling | Keep committed parts, resume | Retain staging or discard |
| Idempotency need | High | Still needed when resuming |
| Memory footprint | Potentially low if processed per event | Potentially high if staged in RAM; use storage |
| Example | Ledger events, independent states | Summary file, snapshot requiring completeness |

## 10. Retrying after a partial error: do not retry blindly

An `UNAVAILABLE` error may be transient, yet it does not automatically prove retrying from scratch is safe. Answer:

- Does the request have side effects, or is it read-only?
- Were responses before the error already applied by the client?
- Does the server retain history by sequence?
- Does the client have durable checkpoints and idempotent operations?
- Is the cursor still valid and historical data still within retention?

If the request is read-only with a stable cursor, the client can retry from the last committed `after_sequence`, using backoff and a retry limit. If the request triggers a task or side effect, use an idempotency key and inspect task status before calling again.

**Do not assume gRPC's automatic retry will recover a server stream after responses have already been received.** gRPC's built-in retry mechanism has specific commitment rules and configuration; it does not replace application-level cursors/checkpoints. Design and explicitly test reconnect/resume behavior.

## 11. Testing errors after emitting partial data

An important test has the server emit two messages and then terminate with `UNAVAILABLE`. The client must read both messages before receiving the terminal error. You can use gRPC **in-process transport** to verify stubs, serialization, and statuses without opening network ports.

~~~java
import com.example.ledger.rpc.LedgerEntry;
import com.example.ledger.rpc.LedgerServiceGrpc;
import com.example.ledger.rpc.ReadLedgerRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class PartialLedgerStreamTest {

    @Test
    void clientReceivesPartialMessagesThenTerminalError() throws Exception {
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new LedgerServiceGrpc.LedgerServiceImplBase() {
                    @Override
                    public void readLedger(
                            ReadLedgerRequest request,
                            StreamObserver<LedgerEntry> out) {
                        out.onNext(LedgerEntry.newBuilder()
                                .setAccountId(request.getAccountId())
                                .setSequence(1)
                                .setEntryId("entry-1")
                                .build());
                        out.onNext(LedgerEntry.newBuilder()
                                .setAccountId(request.getAccountId())
                                .setSequence(2)
                                .setEntryId("entry-2")
                                .build());

                        // Simulate data source failure after two responses.
                        out.onError(Status.UNAVAILABLE
                                .withDescription("Source interrupted")
                                .asRuntimeException());
                    }
                })
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            ReadLedgerRequest request = ReadLedgerRequest.newBuilder()
                    .setAccountId("A-42")
                    .setAfterSequence(0)
                    .build();

            var iterator = LedgerServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .readLedger(request);

            List<Long> received = new ArrayList<>();
            assertEquals(1L, iterator.next().getSequence());
            received.add(1L);
            assertEquals(2L, iterator.next().getSequence());
            received.add(2L);

            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class, iterator::hasNext);

            assertEquals(List.of(1L, 2L), received);
            assertEquals(Status.Code.UNAVAILABLE, error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

The test verifies **two responses received before the error status**. It does not prove the application durably saved those two responses, nor does it fully simulate real network disruptions. Spring Boot integration tests and tests over real transport/proxies remain necessary to verify data sources, cleanup, TLS, and disconnect behavior.

### Additional test cases to include

| Scenario | Expectation |
|---|---|
| Error before first response | Client receives only terminal error status |
| Error after one or more responses | Client keeps received parts and sees error status |
| Source ends normally | Client receives all responses then `onCompleted` |
| Item error while stream continues | Item error message received; RPC can end `OK` |
| Client fails to process a message | Checkpoint not saved before processing succeeds |
| Resume from checkpoint | No lost events; replayed events deduplicated |
| Skipped sequence | Client detects gap and does not mark complete |
| Server loses connection after `onNext` | Client does not assume final message was applied |
| Source fails while closing cursor | RPC does not emit `onCompleted` if reading/closing source failed per contract |

## 12. Observing partial errors in a Spring gRPC environment

Merely counting total failed RPCs won't tell whether errors happen before or after data was emitted. Collect signals per method and correlation ID:

| Metric | Purpose |
|---|---|
| Responses emitted by server before terminal error | Know how much data preceded the failure |
| Last sequence received by client | Know what the client observed |
| Last sequence committed/checkpointed by client | Identify the safe resume point |
| Terminal status (`UNAVAILABLE`, `INTERNAL`, ...) | Categorize termination cause |
| Reconnect/resume count | Assess data source stability |
| Duplicates and sequence gaps | Detect replay or history-to-live handoff bugs |
| RPC duration and failure timing | Find time/load-related failure patterns |
| Queue depth and source wait time | Distinguish overload from dependency failures |

In Spring gRPC, interceptors and tracing/metrics systems can record method, duration, and status. To analyze partial data, the application must log sequence/cursor info at the business level. Never write access tokens, sensitive payloads, or exceptions containing internal details into public metadata/logs.

`UNAVAILABLE` status often suggests a temporarily unreachable dependency; `INTERNAL` may indicate an unexpected server bug. However, do not jump to conclusions from status alone. Cross-reference data source logs, server message emission timestamps, client callbacks, and checkpoints.

## 13. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `onCompleted()` after data source throws an error | Client thinks stream is complete | Terminate with an appropriate `onError` |
| Client marking success inside `onNext` | Incomplete results may be published | Mark RPC complete only inside `onCompleted` |
| Discarding all received messages on `onError` | Loses validly processed data | Choose incremental apply or staging per business rules |
| Retrying from start without deduplication | Duplicate side effects or records | Checkpoints, cursors, and idempotency |
| Using in-RAM sequence on one server instance | Reconnecting to another instance breaks ordering | Stable sequences from shared datastore |
| Returning stack traces/SQL in status description | Leaks internal information | Safe status descriptions; log details internally |
| Treating one item's error as a stream-wide error | Loses independent processable items | Represent per-item outcomes in message |
| Treating a source-wide failure as an item error | Continues emitting incomplete data | Use terminal status when contract cannot be met |
| Tracking only server-sent response count | Unknown how far client received/applied | Track both received sequence and committed checkpoint |

### Self-check questions

1. Server called `onNext` three times and then called `onError(UNAVAILABLE)`. May the client mark the whole RPC as successful?
2. Why can the number of server-emitted responses exceed the number of responses durably processed by the client?
3. When should an item's error live in the payload instead of terminating the entire stream?
4. Should the client send `after_sequence` equal to the last received sequence or the last committed sequence? Why?
5. If the client applies an event and crashes before saving the checkpoint, what can happen upon resume?
6. Why does gRPC not automatically guarantee exactly-once processing after a stream error?
7. What must the server guarantee when transitioning from reading history to receiving live events so no sequence is missed?

**Key takeaway:** An error after emitting partial data causes the RPC to fail, yet it does not erase responses the client already received or side effects already committed. The server must return the proper terminal status and never call `onCompleted` after an error. The client must distinguish received data from applied data, save checkpoints safely, and resume only when supported by sequences/cursors and a replayable data source. This is the foundation for controlled partial-result handling in Spring gRPC server streaming.
