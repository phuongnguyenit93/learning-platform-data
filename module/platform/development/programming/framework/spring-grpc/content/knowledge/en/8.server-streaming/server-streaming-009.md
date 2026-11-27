# Response size and memory limits

## 1. Per-response size limits vs. total stream limits

In **SPRING_GRPC**, a server streaming RPC sends one request and returns multiple Protocol Buffers responses. Splitting results into multiple messages lets the client process them incrementally, but it does not automatically keep memory usage low. A single oversized response can still require substantial memory to construct objects, serialize, buffer, transmit, deserialize, and process. Many small responses can also bloat memory if the application collects all of them into an unbounded list or queue.

Therefore, separate two concepts:

- **Per-response size:** the byte size of one protobuf message after serialization. This is the message limit enforced by the receiver's inbound configuration.
- **Total stream data:** the cumulative size of all responses over the entire RPC. A stream can transfer many gigabytes across thousands of small messages without any single message exceeding the limit.

Example of a document download service:

~~~text
One DownloadDocument RPC
  response #1: 256 KiB chunk
  response #2: 256 KiB chunk
  response #3: 256 KiB chunk
  ...
  response #400: 256 KiB chunk

Size per message: 256 KiB
Total data: roughly 100 MiB
~~~

A 1 MiB message limit does not mean the total stream is capped at 1 MiB. Conversely, if the server sends one response containing an entire 100 MiB file, the client would have to receive one massive message even though the stream has only one response.

**Design goal:** bound individual message size, bound pending data per stream, and bound concurrent streams so memory usage remains predictable.

## 2. One large message consumes memory across multiple layers

When the server creates a protobuf response, data can exist simultaneously in several forms:

1. The protobuf object and nested child objects on the Java heap.
2. Serialized byte payloads or buffers managed by the marshaller/runtime.
3. gRPC and HTTP/2 transport buffers.
4. Deserialized message instances on the client.
5. Application-created buffers or queues on the client for deferred processing.

The number of copies and how long each is retained depend on the implementation, transport, and how the application handles messages. Never assume an object's heap footprint equals the exact protobuf byte size on the wire.

~~~mermaid
flowchart LR
    A["Data source"] --> B["Protobuf object"]
    B --> C["Serialization buffer"]
    C --> D["gRPC / HTTP/2 buffers"]
    D --> E["Client protobuf object"]
    E --> F["Client processing queue"]
    F --> G["Process / persist result"]
~~~

If the application reads all results into a `List<LargeResponse>` before processing, memory grows with the total number of responses rather than per-message size. If the `onNext` callback merely appends messages to an unbounded queue, the client can still run out of memory even when the server sends small messages.

## 3. Configuring message limits on the right receiving side

gRPC Java configures **inbound message size** limits. The word "inbound" is crucial: the limit is enforced on whichever side is **receiving** the message.

| Configuration | Limit applies to |
|---|---|
| `ManagedChannelBuilder.maxInboundMessageSize(bytes)` | Messages the client receives from the server, including server streaming responses |
| `ServerBuilder.maxInboundMessageSize(bytes)` or transport builder equivalent | Messages the server receives from the client, such as requests |

Thus, setting `maxInboundMessageSize` on the server does not directly cap outbound responses sent by the server. For server streaming, the client needs an appropriate inbound limit; simultaneously, the server should enforce an application-level limit on responses before emitting.

Example of a gRPC Java client capping each inbound response at 512 KiB:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .usePlaintext() // Use only in trusted development environments.
        .maxInboundMessageSize(512 * 1024)
        .build();
~~~

If the client receives a message exceeding the limit, the RPC fails instead of continuing to accept that message. The exact status code should be observed on the client and never inferred solely from a server log.

Example of configuring server inbound request limits:

~~~java
Server server = NettyServerBuilder.forPort(9090)
        .maxInboundMessageSize(1024 * 1024)
        .addService(progressService)
        .build()
        .start();
~~~

This caps messages **received by the server** at 1 MiB. It helps protect the server against oversized requests, but does not replace response limits on the client. In a Spring gRPC application, builder/transport settings must be configured via the extension points of the starter in use; never assume identical property names across starters and versions.

Do not rely on library defaults as your memory policy. Choose explicit limits tailored to payload sizes, concurrent streams, and the service's memory budget.

## 4. Application-layer limits before calling onNext

Transport limits protect the receiver, yet the server should still enforce a maximum response size per contract. Java protobuf messages expose `getSerializedSize()` to compute the exact serialized byte size of that message.

~~~java
private static final int MAX_RESPONSE_BYTES = 256 * 1024;

private void emit(
        FeedEvent event,
        StreamObserver<FeedEvent> responses) {

    int serializedBytes = event.getSerializedSize();
    if (serializedBytes > MAX_RESPONSE_BYTES) {
        responses.onError(Status.RESOURCE_EXHAUSTED
                .withDescription("Response exceeds the application size limit")
                .asRuntimeException());
        return;
    }

    responses.onNext(event);
}
~~~

This is an **application-defined** limit per response. `getSerializedSize()` measures serialized protobuf bytes, not total heap, object graphs, transport buffers, or queues. If a message was already built from a massive byte array, checking after construction does not undo the memory already allocated.

For large payloads, check source size **before building the protobuf object**:

~~~java
if (sourcePayload.length > MAX_CHUNK_BYTES) {
    throw new IllegalArgumentException("Source payload exceeds chunk limit");
}

ByteString payload = ByteString.copyFrom(sourcePayload);
DataChunk chunk = DataChunk.newBuilder()
        .setPayload(payload)
        .build();
~~~

`ByteString.copyFrom` creates immutable data but may also allocate a copy. When the data source is already large, read in bounded chunks rather than loading the entire payload into a `byte[]` before splitting. Splitting only after reading an entire file onto the heap does not eliminate the peak memory spike during reading.

## 5. Splitting large payloads into small responses

If a record or file can exceed a single message's limit, design application-level chunking. Each response carries a slice of the payload plus identifying info so the client can reassemble it:

~~~proto
syntax = "proto3";

package files.v1;

option java_multiple_files = true;
option java_package = "com.example.files.rpc";

service FileDownloadService {
  rpc Download(DownloadRequest) returns (stream DataChunk);
}

message DownloadRequest {
  string file_id = 1;
}

message DataChunk {
  string file_id = 1;
  uint64 sequence = 2;
  bytes payload = 3;
  bool last = 4;
}
~~~

Suppose the application limit per message is 256 KiB. The server reads the source in blocks of at most 256 KiB, attaches `file_id` and `sequence`, and emits each `DataChunk`. The client writes each chunk directly to the destination file or storage upon arrival instead of buffering all chunks into a `ByteArrayOutputStream`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as gRPC server
    participant F as File source
    C->>S: Download(file_id)
    loop Each chunk within size limit
        S->>F: Read next chunk
        F-->>S: bytes
        S-->>C: DataChunk(sequence, payload)
        Note over C: Write chunk to storage
    end
    S-->>C: onCompleted()
~~~

Chunking must clearly specify:

- Maximum chunk size and how a shorter final chunk is handled.
- Where `sequence` starts and whether it increments contiguously.
- How completion is determined: `last`, known chunk count, or terminal `onCompleted`.
- How integrity is verified: per-chunk checksum or whole-file checksum.
- How errors are resumed: cursor/sequence, temporary files, and overwrite/append rules.

You do not necessarily need both `last` and `onCompleted` if the contract does not require both. `onCompleted` signals the RPC succeeded; `last` is payload data and can be helpful when the protocol needs to mark the final slice explicitly. If the stream fails after chunk #8, the client must not treat the file as complete just because some chunks arrived.

For very large files or content requiring durable storage, consider storing files in object storage and using gRPC to return metadata, controlled URLs, or small chunks. gRPC streaming does not have to carry every byte of a huge file.

## 6. Bounding queue memory and concurrent streams

A per-message limit alone is not enough. Budget memory by the number of open streams and the number of messages that can wait in queues.

A simple estimation model:

\[
M \approx S \times (B + Q \times B_q + W) + M_{\text{shared}}
\]

Where:

- \(S\): number of concurrent streams.
- \(B\): estimated memory for the message actively being processed per stream.
- \(Q\): maximum messages queued per stream.
- \(B_q\): average size of a queued message.
- \(W\): auxiliary per-stream working memory.
- \(M_{\text{shared}}\): shared buffers/caches and baseline overhead.

For example, assume 200 concurrent streams, each with one in-flight message and at most four queued messages, all around 256 KiB. The payload portion alone is roughly:

~~~text
200 streams × (1 + 4) messages × 256 KiB
≈ 250 MiB
~~~

This figure excludes object overhead, serialization/deserialization copies, queue nodes, TLS/transport buffers, caches, and other requests. It illustrates how even a four-message queue per stream consumes significant memory as stream count scales.

**Bound queues by both item count and byte count.** A 100-item queue may be safe for 1 KiB messages yet dangerous if each message approaches 10 MiB. A weighted queue can reject additional messages once total bytes exceed the budget.

When a queue is full, the policy must be explicit:

| Data type | Possible policies |
|---|---|
| Mandatory events to retain completely | Pause upstream if possible, persist durably for replay, or close RPC with an appropriate status |
| State needing only the latest value | Coalesce older updates per contract |
| Best-effort telemetry | Sample or drop data per published policy |
| Quota-exceeding tasks | Shed load, cap concurrent streams, or return `RESOURCE_EXHAUSTED` |

Never let queues grow unboundedly hoping the garbage collector will handle it. GC cannot reclaim messages still referenced inside a queue.

## 7. Combining flow control with buffer limits

A gRPC Java server can use `ServerCallStreamObserver.isReady()` and `setOnReadyHandler(...)` to know when the write path can accept more data. This prevents the sender from continuously pushing messages while the transport is unready:

~~~java
ServerCallStreamObserver<DataChunk> out =
        (ServerCallStreamObserver<DataChunk>) responseObserver;

out.setOnReadyHandler(() -> scheduleDrain());

private void drain() {
    while (!queue.isEmpty() && out.isReady() && !out.isCancelled()) {
        out.onNext(queue.remove());
    }
}
~~~

This snippet illustrates the idea; `queue` must be bounded and `scheduleDrain()` must coordinate a sequential sender. Never call `onNext` concurrently from a producer and a readiness callback. When the queue fills, throttle the producer or apply the data policy; `isReady() == false` does not automatically stop a broker or event-producing thread.

On the client, the default `onNext` callback can keep firing while the application offloads messages into a separate queue. If the consumer processes slowly, that queue still grows. When receive speed must match processing speed, use `ClientResponseObserver` and manual inbound flow control:

~~~java
stream.disableAutoRequestWithInitial(1);

@Override
public void onNext(DataChunk chunk) {
    writeChunkAndFinish(chunk, error -> {
        if (error == null) {
            control.request(1); // Request more only after processing completes.
        } else {
            control.cancel("Cannot persist chunk", error);
        }
    });
}
~~~

This is pseudocode: `control` is the `ClientCallStreamObserver` saved in `beforeStart`, and `writeChunkAndFinish` is an async application method. Do not call `request(1)` immediately after enqueueing into an unbounded queue; replenish demand after work genuinely completes or after space opens in a bounded queue.

Flow control and memory limits complement each other:

- Flow control throttles data flowing through the transport.
- Manual demand limits responses delivered to client callbacks.
- Bounded queues protect application memory.
- Producer backpressure or storage/replay controls data at the source.

## 8. Compression does not replace message limits

gRPC can compress messages to reduce wire bytes. However, do not treat compression as a solution for oversized responses:

- Server and client still must construct/decompress payloads for processing.
- Payloads may be incompressible or already compressed (images, video, archives).
- Compression increases CPU cost and can create peak memory spikes during processing.
- Uncompressed data size and logical protobuf size still require limits.

Compression fits repetitive payloads with substantial bandwidth savings. It does not replace application size limits, inbound message limits, chunking, or bounded queues.

## 9. Testing response sizes and memory

Test per-message limits, total stream limits, and queue bounds separately:

| Test case | Outcome to verify |
|---|---|
| Response smaller than limit | Client receives normally |
| Response right at application limit | Accepted per size policy |
| Response larger than application limit | Server does not call `onNext`; terminates with defined status |
| Response exceeds client inbound limit | Client rejects oversized message and RPC fails |
| Many small responses, large total stream | Stream succeeds when each message is valid and resources are processed incrementally |
| Slow client | Queue does not exceed byte/item bounds |
| Many concurrent streams | Total memory stays within load-test budget |
| Final chunk shorter than standard chunk | Client writes exact size and finishes file |
| Stream fails between chunks | File not marked complete; resumes by sequence if supported |
| Incompressible payload | CPU and memory stay within budget when compression is enabled |

In-process tests are useful for verifying chunking logic, ordering, and statuses. To measure memory, throughput, and transport effects, run load tests with many concurrent streams, realistic payload size distributions, fast/slow readers, and observe heap/queues. Never measure only bytes on the wire and conclude heap usage is safe.

## 10. Design checklist

- [ ] Set a byte limit **per response** at the application layer.
- [ ] Configure client inbound message limit to match maximum response size.
- [ ] Configure server inbound request limit separately; do not confuse it with outbound response limits.
- [ ] Split large payloads into chunks before loading everything onto the heap.
- [ ] Bound queues by both item count and total bytes.
- [ ] Cap concurrent streams and budget memory under load.
- [ ] Ensure producers can pause/slow down or persist durably when consumers lag.
- [ ] Avoid accumulating all responses into a client collection unless necessary.
- [ ] Include sequence/checksums and a resume policy if full data delivery is required.
- [ ] Test responses near/above limits, slow clients, and concurrent streams.

**Key takeaway:** Server streaming reduces the need to pack an entire result set into one response, but it does not bound memory automatically. Limit **each message's** size, chunk large payloads, bound queues by bytes and count, control concurrent streams, and throttle producers to consumer capacity. Inbound message size limits must be placed on the proper receiving side; a server limit on requests does not bound responses received by the client.
