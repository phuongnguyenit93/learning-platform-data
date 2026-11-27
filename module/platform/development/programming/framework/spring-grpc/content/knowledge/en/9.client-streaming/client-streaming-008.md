# Limiting message count and batch size

**Chapter:** Client streaming  
**Scope:** Spring gRPC (`SPRING_GRPC`) — designing Protocol Buffers contracts, generating Java code, and controlling resources for RPCs that receive multiple requests and return one response.

## 1. Why must client streaming have limits?

Client streaming allows one RPC to receive many request messages before the server returns the final result. This mechanism is convenient for data ingestion, chunked file uploads, or sending sensor readings in batches. However, if a client can send unbounded messages or an arbitrarily large message, a single RPC can monopolize bandwidth, memory, CPU, file descriptors, and server processing time for far too long.

A single limit such as "maximum 10 MB" is not specific enough. You must distinguish **three independent budgets**:

1. **Message count in one RPC:** limits how many times the server receives `onNext()`.
2. **Size of each message:** limits a single protobuf message.
3. **Total size of the entire batch:** limits the total data sent within one RPC.

Example policy for a data ingestion service:

| Budget | Illustrative limit | Purpose |
| --- | ---: | --- |
| Messages / RPC | 1,024 messages | Blocks streams with too many tiny items |
| Serialized size / message | 256 KiB | Blocks an oversized single message |
| Total serialized size / batch | 8 MiB | Blocks excessive total batch data |

These numbers are **illustrative policy values**, not gRPC or Spring gRPC defaults. A real system must choose limits based on payloads, server capacity, latency, user quotas, and downstream system constraints.

## 2. Three limits address three different overload modes

### 2.1. Limiting message count

A client can send millions of tiny messages. Even if each message is only a few bytes, each delivery still incurs protobuf decoding, callback dispatch, validation, logging, state updates, and potentially a database operation. Limiting message count protects CPU and per-RPC operation volume.

Common check:

```java
if (messageCount >= MAX_MESSAGES) {
    reject(Status.RESOURCE_EXHAUSTED, "Batch has too many messages");
    return;
}
// Increment only after the request is validated and accepted.
messageCount++;
```

If `MAX_MESSAGES = 1_024`, the server accepts at most 1,024 messages. Once 1,024 have been accepted and a 1,025th arrives, the server rejects the RPC. Checking before incrementing prevents off-by-one boundary errors.

### 2.2. Limiting individual message size

A protobuf message can contain `bytes` fields, large strings, or deeply nested items. Without a per-message limit, a single request can trigger a memory spike during decoding and processing.

On Java classes generated from protobuf, `getSerializedSize()` returns the message's serialized size in bytes:

```java
long messageBytes = request.getSerializedSize();
if (messageBytes > MAX_MESSAGE_BYTES) {
    reject(Status.RESOURCE_EXHAUSTED, "Message too large");
    return;
}
```

This size includes all serialized protobuf fields, such as `batch_id`, `sequence`, `payload`, and field encoding overhead. It is **not** the exact byte count on the wire: HTTP/2 framing, headers, compression, and transport can make wire bytes differ. State explicitly in your quota contract whether limits are measured by serialized protobuf size or by `payload.size()` alone.

### 2.3. Limiting total batch size

A batch may contain many messages that are each below the per-message limit yet exceed a safe total together. Therefore, the server needs a separate cumulative byte counter:

```java
if (messageBytes > MAX_BATCH_BYTES - batchBytes) {
    reject(Status.RESOURCE_EXHAUSTED, "Batch exceeded byte limit");
    return;
}
batchBytes += messageBytes;
```

The expression `MAX_BATCH_BYTES - batchBytes` avoids adding before comparing, reducing overflow risk when summing two large values. Use `long` for the cumulative counter; do not use `int` if total bytes could exceed 32-bit integer range.

### 2.4. Why can't one limit replace all three?

| Scenario | Message count limit only | Per-message limit only | Total batch limit only |
| --- | --- | --- | --- |
| Millions of tiny messages | Can block | Does not block | Blocks once bytes exceed threshold, but may burn CPU beforehand |
| One gigantic message | Does not block | Blocks | Can block, but message may already be received/decoded depending on layer |
| Many small messages, huge total | Blocks only if enough messages | Does not block | Accurately blocks total bytes |
| Many messages near max size | Caps count | Does not cap total | Caps total bytes |

All three quotas should be checked together before a message enters the accumulator or gets written to storage.

## 3. Message size at the protobuf layer vs. transport layer

Business limits and transport limits are related but distinct:

- **Business limits** are defined by the service: max messages, max bytes per message, and max bytes for the whole batch.
- **gRPC server inbound message limit** is enforced at the transport layer. If a message exceeds this threshold, gRPC can reject it before invoking the service's `onNext()`.
- **Total batch limit** is cumulative state across multiple requests; a transport single-message limit cannot compute this sum on its own.
- **HTTP/2 flow control** regulates in-flight data and transport receive capacity; it does not replace message-count or total-batch quotas.

In gRPC Java, the server builder provides `maxInboundMessageSize(int)` to configure the server-level inbound message limit. With Spring gRPC, configure the corresponding builder/customizer according to the starter version in use; property names or configuration extension points can vary across versions. Do not assume a generic YAML property without verifying your library version.

The transport inbound limit should be set **at least large enough to allow the advertised business message limit**, while not far exceeding server capacity. If the transport limit is lower, requests can be rejected before the service's quota logic runs. If the transport limit is much higher, the service must still enforce its own per-message limit.

With `getSerializedSize()`, the application measures protobuf size prior to compression. The transport may compress payloads; do not use compressed wire bytes as a business quota if your goal is bounding decoding cost and data-structure size. Also, gRPC's inbound message limit is a transport protection mechanism, not a limit on all resources consumed by business logic.

## 4. Defining a batch in the Protocol Buffers contract

Consider an event ingestion service. One RPC carries `BatchItem` messages sharing one `batch_id` with increasing sequence numbers; the server returns a receipt containing the accepted message count and total serialized bytes.

Create `src/main/proto/batch_ingest.proto`:

```proto
syntax = "proto3";

package ingest.v1;
option java_package = "com.example.ingest.grpc";
option java_multiple_files = true;

service BatchIngestService {
  rpc Upload(stream BatchItem) returns (BatchReceipt);
}

message BatchItem {
  string batch_id = 1;
  uint32 sequence = 2;
  string source = 3;
  bytes payload = 4;
}

message BatchReceipt {
  string batch_id = 1;
  int64 accepted_messages = 2;
  int64 accepted_serialized_bytes = 3;
}
```

Here, `accepted_serialized_bytes` is explicitly defined as the sum of `getSerializedSize()` for accepted `BatchItem` messages. It is **not** the sum of payload bytes alone, nor HTTP/2 wire bytes. If business logic needs file content bytes, add a separate field and sum `payload.size()`.

After running the protobuf compiler and gRPC Java plugin, `BatchItem`, `BatchReceipt`, and `BatchIngestServiceGrpc` are generated. Never hand-write message or stub classes.

## 5. Checking quotas in the Spring gRPC server

The example below uses three policy constants: 1,024 messages, 256 KiB serialized per message, and 8 MiB serialized for the entire batch. The service only counts and validates in memory; it does not write to a database or buffer all payloads. Each RPC has its own accumulator.

```java
package com.example.ingest.server;

import com.example.ingest.grpc.BatchIngestServiceGrpc;
import com.example.ingest.grpc.BatchItem;
import com.example.ingest.grpc.BatchReceipt;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class BatchIngestGrpcService
        extends BatchIngestServiceGrpc.BatchIngestServiceImplBase {

    private static final long MAX_MESSAGES = 1_024L;
    private static final long MAX_MESSAGE_BYTES = 256L * 1024L;
    private static final long MAX_BATCH_BYTES = 8L * 1024L * 1024L;

    @Override
    public StreamObserver<BatchItem> upload(
            StreamObserver<BatchReceipt> responseObserver) {

        return new StreamObserver<>() {
            private String batchId;
            private long messageCount;
            private long batchBytes;
            private int nextSequence;
            private boolean terminated;

            @Override
            public void onNext(BatchItem item) {
                if (terminated) return;

                // Validate structure and consistency before consuming quota.
                if (item.getBatchId().isBlank()
                        || item.getSource().isBlank()
                        || item.getPayload().isEmpty()) {
                    fail(Status.INVALID_ARGUMENT, "Invalid BatchItem");
                    return;
                }
                if (batchId != null && !batchId.equals(item.getBatchId())) {
                    fail(Status.INVALID_ARGUMENT,
                            "All messages must share the same batch_id");
                    return;
                }
                if (item.getSequence() != nextSequence) {
                    fail(Status.INVALID_ARGUMENT,
                            "Non-contiguous sequence");
                    return;
                }

                // getSerializedSize() is the serialized protobuf size.
                long messageBytes = item.getSerializedSize();

                if (messageBytes > MAX_MESSAGE_BYTES) {
                    fail(Status.RESOURCE_EXHAUSTED,
                            "A single message exceeded the 256 KiB limit");
                    return;
                }
                if (messageCount >= MAX_MESSAGES) {
                    fail(Status.RESOURCE_EXHAUSTED,
                            "Batch exceeded the 1,024-message limit");
                    return;
                }
                // Compare before adding to avoid overflow.
                if (messageBytes > MAX_BATCH_BYTES - batchBytes) {
                    fail(Status.RESOURCE_EXHAUSTED,
                            "Batch exceeded the 8 MiB limit");
                    return;
                }

                // Consume quota only after all checks pass.
                batchId = item.getBatchId();
                messageCount++;
                batchBytes += messageBytes;
                nextSequence++;
            }

            @Override
            public void onError(Throwable cause) {
                // Inbound stream failed/cancelled: stop accumulator, clean up if any.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) return;
                if (messageCount == 0) {
                    fail(Status.INVALID_ARGUMENT, "Empty batch");
                    return;
                }

                BatchReceipt receipt = BatchReceipt.newBuilder()
                        .setBatchId(batchId)
                        .setAcceptedMessages(messageCount)
                        .setAcceptedSerializedBytes(batchBytes)
                        .build();

                terminated = true;
                responseObserver.onNext(receipt);
                responseObserver.onCompleted();
            }

            private void fail(Status status, String reason) {
                if (terminated) return;
                terminated = true;
                responseObserver.onError(
                        status.withDescription(reason).asRuntimeException());
            }
        };
    }
}
```

### Order of checks matters

1. Validate required fields, `batch_id`, and `sequence`.
2. Measure the message's serialized size.
3. Check the **per-message** limit.
4. Check the **message count** limit.
5. Check the **total batch bytes** limit using overflow-safe subtraction.
6. Only after every condition passes, increment counters and update state.

This ensures rejected messages do not increment `messageCount` or `batchBytes`. When a quota is exceeded, the server terminates with `RESOURCE_EXHAUSTED` and returns no success `BatchReceipt`. Structural or sequence errors use `INVALID_ARGUMENT`.

### Why not store all messages in a List?

This example aims to show how to limit and count. If the service stored every `BatchItem` in a `List`, an 8 MiB batch quota limits serialized size, yet actual Java heap usage could be substantially higher due to object overhead, byte arrays, references, and collection structures. If you need per-message processing, process/write incrementally with bounded buffers; if atomic whole-batch processing is needed, use bounded staging and an explicit cleanup policy.

## 6. The client should also check before sending

The server is the authoritative quota enforcer; client-side preflight checks avoid transmitting a batch that is guaranteed to be rejected. The client can maintain the same three counters while reading from the data source rather than buffering the entire batch in RAM.

A small helper for a sequential producer:

```java
import com.example.ingest.grpc.BatchItem;

final class BatchBudget {
    static final long MAX_MESSAGES = 1_024L;
    static final long MAX_MESSAGE_BYTES = 256L * 1024L;
    static final long MAX_BATCH_BYTES = 8L * 1024L * 1024L;

    private long count;
    private long totalBytes;

    void checkAndConsume(BatchItem item) {
        long size = item.getSerializedSize();
        if (size > MAX_MESSAGE_BYTES) {
            throw new IllegalArgumentException("Message too large");
        }
        if (count >= MAX_MESSAGES) {
            throw new IllegalArgumentException("Exceeded maximum message count");
        }
        if (size > MAX_BATCH_BYTES - totalBytes) {
            throw new IllegalArgumentException("Batch too large");
        }

        count++;
        totalBytes += size;
    }
}
```

The producer calls `checkAndConsume(item)` **before** `requestObserver.onNext(item)`. If the check fails, the producer stops reading the source and cancels the open RPC; do not call `onCompleted()` to turn an incomplete batch into a success. This helper is strictly a client-side check; clients can be modified or bypassed, so the server must still validate every request.

If the client has already sent part of the batch before discovering it exceeds the batch limit, the current RPC cannot erase already-sent messages from the transport. Cancel the RPC and handle it according to your batch policy (discard staging, query status, or repartition data into new batches). Do not silently open a new RPC with the same data if the server has side effects without idempotency.

## 7. Choosing limit numbers based on resource budgets

Do not pick quotas merely because a number is easy to remember. Start from realistic payloads and operational targets:

### 7.1. Sizing messages

- Measure serialized protobuf sizes of typical and worst-case messages.
- Include in-message metadata such as `batch_id`, `source`, sequence, and optional fields.
- Identify any `bytes` fields that might carry large payloads or nested data.
- Set limits below thresholds that strain memory/CPU, yet high enough for legitimate payloads.

### 7.2. Sizing batches and message counts

If the average payload is around 4 KiB and the max batch is 8 MiB, byte capacity allows roughly 2,048 messages; however, a 1,024-message quota stops it earlier. When payloads are tiny, the message count limit still protects CPU and callback overhead. When a single message is huge, the per-message quota blocks it before the batch total hits the cap.

The three constraints can be written as:

\[
\begin{aligned}
N &\leq N_{\max} \\
S_i &\leq S_{\text{message,max}} \quad \forall i \\
\sum_{i=1}^{N} S_i &\leq S_{\text{batch,max}}
\end{aligned}
\]

Where \(S_i\) is the serialized protobuf size of the \(i\)-th message, not raw source file bytes or post-compression wire bytes.

### 7.3. Accounting for concurrent load

An 8 MiB/batch limit does not mean the server uses only 8 MiB. If 200 concurrent RPCs each hold staging buffers near 8 MiB, staged data alone approaches 1.6 GiB, before counting heap/object overhead, transport buffers, and the rest of the application.

Therefore, also evaluate:

- Maximum concurrent open RPCs per user/tenant or service-wide.
- Total memory, temp file, and staging disk quotas across the entire server.
- Concurrent write tasks and database connection pool limits.
- Backpressure policies when internal queues fill up.
- Maximum lifetime of a batch and overall RPC deadline.

**Per-RPC quotas must be paired with system-wide quotas.** Otherwise, a client can open many concurrent streams to multiply total resource consumption.

## 8. Batch limits differ from flow control and deadlines

These mechanisms complement one another:

| Mechanism | What does it control? | What does it NOT replace? |
| --- | --- | --- |
| Message/batch quota | Total volume of work allowed in one RPC | Does not throttle instantaneous send rate |
| HTTP/2/gRPC flow control | Send/receive readiness and transport buffer pressure | Does not cap total message count or business byte total |
| Deadline | Maximum duration for the entire RPC | Does not cap message/byte count if the client sends very fast |
| Concurrent RPC / global quota | Total concurrent work | Does not replace per-batch limits |

With gRPC Java, the client can use `ClientResponseObserver` and `ClientCallStreamObserver.isReady()`/`setOnReadyHandler()` to emit data according to transport readiness. That prevents pushing too fast, yet a single batch can still exceed 8 MiB without business-level counters.

Deadlines span stream opening, sending messages, server processing, and receiving the receipt. Set reasonable deadlines to prevent streams from being held open too long; deadlines are not the sole tool for bounding resources.

## 9. Error statuses and behavior at quota boundaries

| Scenario | Recommended status | Notes |
| --- | --- | --- |
| Single message serialized size exceeded | `RESOURCE_EXHAUSTED` | Request exceeded resource budget |
| Total batch bytes exceeded | `RESOURCE_EXHAUSTED` | Rejects whole RPC under the example contract |
| Message count exceeded | `RESOURCE_EXHAUSTED` | Next request after reaching quota is rejected |
| Missing `batch_id`, malformed payload | `INVALID_ARGUMENT` | Client must fix data |
| Non-contiguous sequence | `INVALID_ARGUMENT` | Not a capacity error |
| Transport inbound message limit exceeded | gRPC transport rejects before service handles | Observed status depends on transport error; service may never receive `onNext` |
| Deadline expires while sending | Typically `DEADLINE_EXCEEDED` on client | Batch may have been partially processed |
| Client actively cancels | Typically `CANCELLED` | Stop producer and clean up |

Pick a consistent policy for the entire batch: for example, **fail-fast** whenever any message exceeds quota, without returning a partial success receipt. If the business requires partial acceptance, the response contract must clearly express accepted count, rejected count, and how to query status; never use an ambiguous `OK` status.

## 10. Testing message count and size boundaries

In-process testing can verify business quotas inside the service. The test below uses JUnit 5, `grpc-inprocess`, and protobuf-generated classes. The example calls the server via an async stub and asserts that the first message beyond the limit receives `RESOURCE_EXHAUSTED`.

```java
package com.example.ingest;

import com.example.ingest.grpc.BatchIngestServiceGrpc;
import com.example.ingest.grpc.BatchItem;
import com.example.ingest.grpc.BatchReceipt;
import com.example.ingest.server.BatchIngestGrpcService;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BatchQuotaTest {

    @Test
    void rejectsMessageBeyondCountLimit() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new BatchIngestGrpcService())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            CompletableFuture<Status.Code> ended = new CompletableFuture<>();
            StreamObserver<BatchReceipt> responses = new StreamObserver<>() {
                @Override
                public void onNext(BatchReceipt receipt) {
                    ended.completeExceptionally(
                            new AssertionError("Must not return receipt"));
                }

                @Override
                public void onError(Throwable error) {
                    ended.complete(Status.fromThrowable(error).getCode());
                }

                @Override
                public void onCompleted() {
                    ended.completeExceptionally(
                            new AssertionError("Must not complete OK"));
                }
            };

            StreamObserver<BatchItem> requests =
                    BatchIngestServiceGrpc.newStub(channel).upload(responses);

            // Server limit is 1,024; the 1,025th message must be rejected.
            for (int i = 0; i < 1_025; i++) {
                requests.onNext(item(i));
            }

            assertEquals(Status.Code.RESOURCE_EXHAUSTED,
                    ended.get(3, TimeUnit.SECONDS));
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }

    private static BatchItem item(int sequence) {
        return BatchItem.newBuilder()
                .setBatchId("batch-test")
                .setSequence(sequence)
                .setSource("sensor-a")
                .setPayload(com.google.protobuf.ByteString.copyFromUtf8("x"))
                .build();
    }
}
```

To test the two byte quotas separately:

1. **Per-message:** build a `BatchItem` with a payload large enough that `getSerializedSize() > 256 KiB`; assert the server returns `RESOURCE_EXHAUSTED`.
2. **Per-batch:** send messages that are each under 256 KiB yet whose combined serialized size exceeds 8 MiB; assert the server rejects the exact message crossing the threshold.
3. **Exact boundary:** send a batch with exactly 1,024 messages and total serialized size exactly 8 MiB (if constructible with matching payloads); confirm the policy accepts at `<=`.
4. **Invalid sequence:** send sequence 0 then 2; assert `INVALID_ARGUMENT`, not misclassified as a quota error.
5. **Concurrency:** two RPCs each within quota; verify one RPC's quota is not accidentally added to the other's.

In-process testing does not replace testing inbound message limits on real transport. Write an integration test against a server configured with `maxInboundMessageSize`, send a message exceeding the transport limit, and confirm the service does not process that message. Also measure heap, CPU, and staging files under concurrent RPCs; checking status codes alone is not enough to prove limits protect resources.

## 11. Quota design checklist for a service

- [ ] Clearly define whether a message is measured by `getSerializedSize()`, `payload.size()`, or another criterion.
- [ ] Enforce a per-RPC message count limit.
- [ ] Enforce a serialized size limit per message.
- [ ] Enforce a total batch byte limit using a `long` counter and overflow-safe comparisons.
- [ ] Configure transport inbound limits compatible with business quotas.
- [ ] Validate quotas on the server before consuming resources or persisting data.
- [ ] Preflight on the client to avoid sending batches guaranteed to be rejected.
- [ ] Pair per-RPC quotas with concurrency and system-wide quotas.
- [ ] Set deadlines, flow control, and queue bounds.
- [ ] Test below threshold, at exact threshold, above threshold, and under concurrent RPCs.
- [ ] Record metrics for message count, serialized bytes, batch duration, and status; avoid logging sensitive payloads.

## 12. Self-practice

1. A batch has 800 messages of 12 KiB each. Under the lesson's policy, which limit triggers first: message count, per-message size, or total batch bytes?
2. Why does `getSerializedSize()` differ from `payload.size()`? When should each metric be exposed in `UploadReceipt`?
3. If transport `maxInboundMessageSize` is smaller than the service's 256 KiB limit, what happens to a 200 KiB request? Why might the service never receive `onNext()`?
4. A client sent 500 messages and then discovered the batch total exceeded quota. Why can't you just drop the last message and still treat the current batch as valid?
5. A server allows 8 MiB per batch and 500 concurrent batches. Compute the maximum raw data budget under that policy and propose a concurrency limit suited to realistic heap/staging capacity.

**Remember:** A client streaming RPC needs at least three business quotas: **message count**, **serialized size per message**, and **total serialized batch bytes**. Validate on the server before processing, use `long` and overflow-safe comparisons, configure compatible transport inbound limits, and combine flow control, deadlines, and concurrency quotas to protect the entire service.
