# Batching and Message Frequency

In gRPC streaming, **batching** means grouping multiple records or events at the application layer into a single Protobuf message, or grouping multiple small operations into a single processing unit. **Message frequency** is the rate at which the application emits gRPC messages on a stream. Both factors directly affect throughput, latency, CPU, network overhead, memory, and service responsiveness.

In **SPRING_GRPC**, batching is often useful for event ingestion, data synchronization, chunked upload/download, telemetry, and processing multiple records in a stream. However, gRPC does not automatically merge multiple `onNext` calls into a single application message. Each message sent via an observer remains a separate gRPC message; to group records, the Protobuf contract and application code must represent batches explicitly.

## 1. What is application-layer batching?

Suppose a producer has 1,000 small events. There are two ways to transfer them:

- **Unbatched:** emit 1,000 gRPC messages, each containing one event.
- **Batched:** group 100 events into one message and emit 10 gRPC messages.

Batching reduces message envelope handling, callbacks, dispatching, and part of protocol overhead. It can also help the server perform batch database writes. In return, the producer must wait to accumulate data; larger messages require more memory and can lengthen the processing time of a single batch.

Distinctions to keep clear:

- A single gRPC stream can carry many messages.
- A single Protobuf message can hold many logical records via a `repeated` field.
- An application batch is not automatically an atomic transaction.
- A single `onNext` call does not prove the consumer has committed the data.

Therefore, batching is a contract and business-processing decision, not merely a transport optimization trick.

## 2. Message frequency and the throughput/latency trade-off

High message frequency means the application emits many small messages per unit of time. Lower frequency typically means each message carries more records or the producer waits longer before flushing.

| Strategy | Benefits | Costs/risks |
| --- | --- | --- |
| Send each record immediately | Low latency, early processing, small failure blast radius | Many callbacks, framing, scheduling, and small-message overhead |
| Batch by record count | Predictable batch size, usually better throughput | Under low load, records may wait a long time to fill a batch |
| Batch by time interval | Bounds wait time, fits continuous event streams | Batch size fluctuates with load |
| Batch by byte count | Better control over payload and memory | Requires estimating/measuring serialized size |
| Combine count, bytes, and time | Balances throughput, latency, and message limits | Requires managing timers, flushes, and trigger contention |

Sending each small event individually makes per-message fixed costs a significant percentage. Waiting for oversized batches makes the first event wait too long, increasing p95/p99 latency. Optimization must therefore consider messages/s, bytes/s, batch accumulation wait time, and consumer processing time together.

### 2.1. Choosing flush thresholds

A batch is typically flushed when the first of these conditions triggers:

1. **Max count:** enough records accumulated, e.g., 100 events.
2. **Max bytes:** total serialized size nears the allowed threshold, e.g., 256 KiB.
3. **Max wait:** the first record has waited up to the maximum time, e.g., 20 ms.
4. **Lifecycle:** the stream finishes, the client closes input, or a flush is needed before a checkpoint.

These numbers are only illustrative examples. Real thresholds must be benchmarked with your payloads, network, downstream systems, and SLOs.

Under high load, count/bytes triggers usually flush quickly. Under low load, the time trigger ensures events are not held indefinitely just because a batch is not full.

## 3. Designing a Protobuf contract for batching

A batch contract should clearly represent payload contents and acknowledgment capability:

```protobuf
syntax = "proto3";

package telemetry.v1;

service EventIngestService {
  rpc Publish(stream EventBatch) returns (PublishSummary);
}

message Event {
  uint64 sequence = 1;
  string event_type = 2;
  bytes payload = 3;
}

message EventBatch {
  string batch_id = 1;
  repeated Event events = 2;
  uint64 first_sequence = 3;
  uint64 last_sequence = 4;
}

message PublishSummary {
  uint64 accepted_count = 1;
  uint64 rejected_count = 2;
  uint64 last_committed_sequence = 3;
}
```

This example uses client streaming: the client sends multiple `EventBatch` messages and the server returns a summary when the client finishes. The sequence and `batch_id` fields help the server detect sequence gaps, duplicates, or retries.

A real contract must decide:

- Are empty batches allowed?
- Does event ordering inside a batch matter?
- Must sequences be contiguous or are gaps allowed?
- If one record in a batch is invalid, reject the whole batch or return per-event results?
- Does the server acknowledge receipt, processing, or commit?
- Does a batch carry an idempotency key?
- What are the limits on count and serialized bytes?

Do not assume a `repeated` field is always the best choice. If records are very large, require file/chunk transfer, or each record needs independent retries, use separate messages in the stream and checkpoint by sequence.

## 4. Choosing batch size by count and bytes

Limiting record count alone is insufficient. 100 tiny events might occupy only a few KiB, while 100 events with large payloads can exceed the server or client message size limit.

Enforce at least two bounds:

- Max records per batch.
- Max serialized bytes per batch.

With Protobuf Java, compiler-generated messages provide `getSerializedSize()` to estimate the serialized message size. When sizing a batch, include wrapper overhead and message-level Protobuf metadata; never treat raw payload byte sums as the total wire size.

Never produce a batch larger than the configured inbound message limit on client/server. Limits must be agreed across contract/deployment with headroom for wrapper fields. If a single record already exceeds max bytes, reject it explicitly or split it into chunks according to the contract.

## 5. Example batch accumulation in Java

An accumulator can hold the open batch and return completed batches for the caller to send. The example below illustrates count and serialized-byte triggers:

```java
final class EventBatchAccumulator {
    private final int maxEvents;
    private final int maxBytes;
    private final List<Event> pending = new ArrayList<>();
    private int pendingBytes;

    EventBatchAccumulator(int maxEvents, int maxBytes) {
        if (maxEvents < 1 || maxBytes < 1) {
            throw new IllegalArgumentException("Batch limits must be positive");
        }
        this.maxEvents = maxEvents;
        this.maxBytes = maxBytes;
    }

    synchronized List<EventBatch> add(Event event) {
        int eventBytes = event.getSerializedSize();
        if (eventBytes > maxBytes) {
            throw new IllegalArgumentException("Event exceeds batch byte limit");
        }

        List<EventBatch> ready = new ArrayList<>(2);
        if (!pending.isEmpty()
                && (pending.size() >= maxEvents
                    || pendingBytes + (long) eventBytes > maxBytes)) {
            ready.add(detach());
        }

        pending.add(event);
        pendingBytes += eventBytes;

        if (pending.size() >= maxEvents || pendingBytes >= maxBytes) {
            ready.add(detach());
        }
        return ready;
    }

    synchronized Optional<EventBatch> flush() {
        return pending.isEmpty()
            ? Optional.empty()
            : Optional.of(detach());
    }

    private EventBatch detach() {
        EventBatch batch = EventBatch.newBuilder()
            .setBatchId(UUID.randomUUID().toString())
            .addAllEvents(pending)
            .setFirstSequence(pending.get(0).getSequence())
            .setLastSequence(pending.get(pending.size() - 1).getSequence())
            .build();
        pending.clear();
        pendingBytes = 0;
        return batch;
    }
}
```

This is an illustrative accumulator; production code must add sequence ranges, timestamps, total buffer limits, and oversized-record handling. The caller receives batches from `add`/`flush` and sends them on a serialized execution path. Never hold the accumulator lock while performing network or observer calls, because sending may be slow or callbacks may re-enter.

Time-based triggers are typically implemented with a scheduler calling `flush` periodically or a timer started when the batch transitions from empty to non-empty. Timers must be cancelled/reset once a batch is detached. When timer and producer flush concurrently, synchronize so each record belongs to exactly one batch.

## 6. Thread safety and send ordering

Producer, timer, and cancellation callbacks can run on different threads. When mutating a shared accumulator, synchronize state:

- Have a single owner for the open batch, or guard add/detach operations with a lock.
- Detach the batch inside the synchronized section; send the batch after releasing the lock.
- Serialize `onNext` calls on the same `StreamObserver`.
- Do not allow a timer-flushed newer batch to overtake an older batch.
- When a stream cancels, stop the producer and explicitly decide whether held batches are discarded, persisted durably, or retried.

If batches are sent asynchronously via an executor, the send queue must also be bounded. If the accumulator is bounded while the send queue is unbounded, heap can still grow out of control.

Record ordering inside a batch typically follows increasing sequence numbers. If multiple producers generate events concurrently, define where sequence numbers are assigned and which order is authoritative. Never infer business ordering solely from when callbacks execute.

## 7. Time-based flushing and message frequency

Time-based flushing helps when traffic is uneven. A timer can flush a batch when the first record's wait duration reaches max wait. Do not rely on fixed-rate flushing as a guarantee that every batch has identical age; timers can drift under scheduler load or JVM pauses.

The design must decide:

- Whether max wait starts from the first record or the most recent record.
- Whether timer flushes of empty batches are skipped.
- When a stream finishes, whether the final batch flushes before `onCompleted`.
- When a client cancels, whether the final batch is saved for resumption.
- When an error occurs during flush, whether the batch is retained or transitions to pending retry.

If max wait resets on the most recent record, a steady stream of events can delay flushing indefinitely. Measuring from the batch's first record is typically used to enforce a clear latency bound.

## 8. Backpressure and buffer limits

Batching reduces message count but increases the amount of data buffered in memory before flushing. Therefore, batching must pair with backpressure:

- Bound pending record count and bytes.
- Bound the number of batches waiting to be sent.
- When full, pause the producer, throttle, reject, or persist to a durable queue per business requirements.
- Request more inbound messages only when the consumer has capacity if using manual flow control.
- For outbound streams, check readiness before emitting batches.
- Cancel timers, producers, and pending work when the stream closes.

HTTP/2 flow control throttles bytes at the transport layer. It does not prevent the application from building a list of millions of records before calling `onNext`. Bounded buffering is the application's responsibility.

A single batch can exceed the readiness threshold even when the stream was previously ready. The producer should therefore check readiness before sending each batch and keep only a bounded number of pending batches.

## 9. Batch atomicity, acknowledgments, and retries

One gRPC message holding multiple events does not mean the server processes them in a single transaction. The server may:

- Commit the entire batch or roll back the entire batch.
- Commit individual events and return per-event results.
- Accept the batch into a durable queue and process asynchronously.

The contract must state clearly which semantics apply. If the server commits individual events while the client only receives one final status for the entire stream, the client may not know which events committed before an error occurred.

For safe retries:

- Each event has a stable event ID or sequence.
- Each batch keeps a stable batch ID across retries.
- The server retains idempotency/deduplication state for a documented window.
- Acknowledgments specify committed sequences or batch IDs.
- The client resends only unacknowledged portions.
- Retries obey deadlines and retry attempt limits.

Never generate a new batch ID when retrying a batch that was already sent without an ack; doing so makes duplicate detection difficult for the server.

## 10. Handling partial errors in a batch

If a batch has 100 records and one is invalid, the API must define exact behavior:

| Semantics | Behavior |
| --- | --- |
| Atomic batch | Reject the entire batch; no records are committed |
| Per-item result | Process valid records and return status per record |
| Durable enqueue | Ack once the batch is durably stored; business processing happens later |

With per-item results, the response can include sequence, result code, and safe public error descriptions. Do not use a single final status to imply the entire batch failed if part of it already committed.

With atomic batches, ensure the transaction covers exactly the batch's records and bound transaction size. Oversized batches can hold locks long, increase log pressure, and reduce concurrency.

## 11. Compression and message frequency

Larger batches can improve compression efficiency because multiple records with repetitive structure share the same payload. However, compression consumes CPU and can add delay before a message is ready to send.

| Workload | What to consider |
| --- | --- |
| Small events, repetitive fields | Batching can improve compression ratio |
| Already compressed payloads | Extra compression usually adds little value |
| CPU is the bottleneck | Measure carefully before enabling compression |
| Network is the bottleneck | Batching/compression can raise goodput |
| Large messages and latency-sensitive | Cap batch size and accumulation time |

Do not compare bytes/s alone. Measure CPU/message, p95/p99 latency, memory/batch, and goodput. A configuration that cuts network bytes by 30% while doubling CPU may lower overall throughput.

## 12. Combining batching with HTTP/2 flow control

Each batch is a separate gRPC message on the stream. HTTP/2 enforces flow control at stream and connection levels; the gRPC runtime throttles bytes according to windows. The application must coordinate:

1. Build batches within the message size limit.
2. Emit only when stream readiness permits.
3. Keep the number of queued outbound batches bounded.
4. Monitor flow-control wait durations.
5. Do not enlarge batch size to hide a slow consumer.

If the receiver cannot keep up, raising batch size may make each send look more efficient while forcing the receiver to digest larger bursts. Measure consumer processing time and queue depth, not just sender throughput.

## 13. Benchmarking batching and message frequency

Benchmarks should compare multiple configurations under the same workload:

| Experiment | Count limit | Byte limit | Time limit |
| --- | ---: | ---: | ---: |
| A: per-record send | 1 | small | near 0 |
| B: small batch | 16 | 32 KiB | 5 ms |
| C: medium batch | 64 | 128 KiB | 15 ms |
| D: large batch | 256 | 512 KiB | 30 ms |

This is an illustrative test matrix, not default settings. Tune limits based on message size, server max inbound size, downstream batch capacity, and SLOs.

For each configuration, measure:

- Messages/s and logical records/s.
- Payload goodput and wire bytes/s.
- Time from event creation to flush.
- End-to-end latency p50/p95/p99.
- CPU, allocation rate, heap, GC pauses.
- Queue depth, batch fill ratio, and flush counts by count/bytes/time trigger.
- Errors, retries, duplicates, and partial commits.

Warm up before collecting steady-state data. Ramp load gradually and hold long enough to catch growing queues over time. If throughput rises while p99 latency or memory breaches the SLO, that configuration is not a good choice.

## 14. Observability for batching

Useful metrics:

| Metric | Meaning |
| --- | --- |
| Records per batch | Batch fill ratio and grouping efficiency |
| Serialized bytes per batch | Message size distribution |
| Batch flush count by trigger | Which trigger (count/bytes/time/lifecycle) dominates |
| Batch wait duration | How long records wait before flushing |
| Records per second | Business throughput |
| Messages per second | gRPC message frequency |
| Pending records/bytes | Buffer pressure |
| Send queue depth | Whether sending keeps pace with the producer |
| Ack latency | Time from send to commit confirmation |
| Retry/duplicate/partial failure | Correctness and recovery overhead |

Do not use high-cardinality labels like batch ID, event ID, user ID, or resource ID on metrics. Use controlled traces/logs to investigate specific batches; never log sensitive payloads.

Low batch fill ratios can indicate a time trigger that is too short or low traffic. High batch wait durations can come from a large max wait, bursty producers, or delayed timers. Continuously growing pending bytes usually signals that the consumer or network cannot keep up.

## 15. Common design mistakes

| Mistake | Consequence | Better approach |
| --- | --- | --- |
| Assuming gRPC auto-batches multiple `onNext` calls | Fails to reduce logical gRPC message count | Group records into a Protobuf batch in the application |
| Limiting count only | Batches can exceed max message size | Limit both count and serialized bytes |
| Flushing only when batch is full | Low traffic leaves events waiting forever | Add a max wait trigger |
| Unsynchronized flush timer and producer | Duplicate, dropped, or out-of-order batches | Synchronize detach and serialize sends |
| Unbounded send queue | Heap grows even when accumulator is bounded | Bounded send queue and backpressure |
| Treating a batch as an atomic transaction | Clients misinterpret partial commits | Document atomic/per-item/durable enqueue semantics |
| Retrying with a new batch ID | Duplicates are hard to detect | Keep batch/event IDs stable across retries |
| Oversized batches | Higher latency, lock duration, and memory | Benchmark multiple thresholds and cap max bytes |
| Measuring only messages/s | Hides actual logical record rate | Measure records/s, ack, and commit throughput |

## 16. Checklist for choosing batching and message frequency

Before releasing a batched stream, verify:

1. **Goal:** optimizing records/s, payload goodput, CPU, or network?
2. **Contract:** does the batch message define clear IDs, sequences, and semantics?
3. **Triggers:** are count, serialized bytes, and max wait all defined?
4. **Message size:** can a single record or batch exceed inbound limits?
5. **Buffers:** are both accumulator and send queue bounded?
6. **Timers:** is time-based flushing safe alongside concurrent producer/cancellation?
7. **Ordering:** do batches and events follow clear sequence/ordering rules?
8. **Atomicity:** is the entire batch or each event committed individually?
9. **Acknowledgments:** does ack mean received, processed, or committed?
10. **Retries:** are batch ID/event ID stable for deduplication?
11. **Backpressure:** does the producer pause/throttle when the receiver falls behind?
12. **Benchmarks:** have throughput, p95/p99, memory, CPU, and fill ratio been measured?
13. **Observability:** are pending bytes, flush reasons, ack latency, and duplicate rates tracked?

## 17. Key takeaway

Batching groups multiple logical records into one gRPC message to cut fixed overhead and potentially boost throughput. Lower message frequency generally reduces dispatch/callback counts while increasing record wait times and payload sizes. A balanced design combines record count, serialized bytes, and max wait thresholds.

In Spring gRPC, batching must be paired with clear Protobuf contracts, bounded buffers, thread-safe flushing, readiness/flow control, and explicit acknowledgment semantics. A batch is not automatically an atomic transaction; retries require stable batch/event IDs and deduplication. Benchmarks must measure records/s, messages/s, goodput, batch wait, p95/p99 latency, CPU, and memory. Choosing frequency based on workload and SLO increases throughput without sacrificing responsiveness, correctness, or reliability.

### References

- [gRPC – Performance](https://grpc.io/docs/guides/performance/)
- [gRPC – Flow control](https://grpc.io/docs/guides/flow-control/)
- [gRPC Java – Generated code reference](https://grpc.io/docs/languages/java/generated-code/)
- [gRPC Java – API documentation](https://grpc.github.io/grpc-java/javadoc/)
- [Protocol Buffers – Best practices](https://protobuf.dev/best-practices/dos-donts/)
