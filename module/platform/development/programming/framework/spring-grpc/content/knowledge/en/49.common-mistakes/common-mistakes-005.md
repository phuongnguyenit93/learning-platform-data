# Making Messages Too Large to Avoid Schema Design

## 1. Why is an oversized Protobuf message a problem?

In **SPRING_GRPC**, Protobuf defines the contract between client and server. A common design mistake is stuffing too much data into a single request/response: tens of thousands of records, unbounded repeated fields, or entire large binary files. This looks simple because the client only needs one RPC, but it pushes memory, serialization, network, queueing, and database processing costs onto a single call.

A large message can cause:

- Increased allocations and garbage collection on both client and server.
- Higher latency before the server can process the first record because the entire message must be received and parsed.
- Increased heap pressure when multiple large RPCs run concurrently.
- Network bursts that force small RPCs to compete for resources.
- Difficult retries because resending a huge payload takes time and may repeat side effects.
- Responses so large that the client, proxy, or server refuses to accept them.
- As the schema keeps adding fields for different use cases, the message turns into an unclear, hard-to-evolve contract.

Do not raise message limits just to avoid deciding how to split resources, paginate, or stream. Design contracts that reflect reasonable work sizes and bound the resources consumed by each RPC.

## 2. Message size vs. HTTP/2 frame size and flow control

A gRPC message is framed in gRPC framing and then transmitted over HTTP/2 DATA frames. A single large message can be split across multiple frames; HTTP/2 frame limits do not equate to whole-message size limits.

Distinguish between:

| Concept | Meaning |
| --- | --- |
| Protobuf message size | Serialized data size for one gRPC message |
| HTTP/2 frame size | Size of a single frame on the transport |
| HTTP/2 flow control | Mechanism regulating the volume of DATA in flight |
| gRPC max inbound message size | Maximum message size an endpoint accepts on receipt |
| Application quota | Business limits such as item count, total bytes, or rows processed |

Flow control regulates data transmission, but it does not turn a giant message into a small payload. When the message is reassembled and parsed, the receiver still needs memory for the corresponding data and object graph.

Inbound limits are configured separately on the client and server. One side accepting large messages does not mean the other side will. The contract should specify a maximum size less than or equal to the configured limits of all involved endpoints and proxies.

## 3. Signs a schema is packing too much data

A message may be too large or overly overloaded when:

- A request contains a collection with no element count limit.
- A response returns the entire history instead of a single page.
- A `bytes` field carries large files, archives, or huge JSON payloads.
- A message has multiple field groups serving distinct operations.
- The client must resend the entire object even for a partial update.
- A response bundles multiple types of data when the caller only needs one.
- Repeatedly raising message size limits is the only way to keep an RPC succeeding.

Not every message with many fields is wrong. A command requiring many business fields can be completely legitimate. The problem is unbounded data size and scope, or a contract lumping disparate workflows into one message.

## 4. Design small, bounded requests and responses

For large collections, the API should support pagination instead of returning all records in a single message:

```proto
message ListOrdersRequest {
  string customer_id = 1;
  int32 page_size = 2;
  string page_token = 3;
}

message ListOrdersResponse {
  repeated OrderSummary orders = 1;
  string next_page_token = 2;
}

message OrderSummary {
  string order_id = 1;
  string status = 2;
  int64 created_at_epoch_ms = 3;
}
```

The server must enforce a hard cap on `page_size`. For example, if a client requests 10,000 items while the API allows at most 200, the server can clamp it per contract or return `INVALID_ARGUMENT`. The rule must be consistent and documented.

Page tokens should be opaque to the client and carry enough information to resume the query, such as a cursor/sort key and filter scope. Avoid arbitrary offset pagination on rapidly changing data if missing or duplicate records are a risk; cursor pagination is typically more stable.

Responses should include only the fields the caller needs. If the caller needs a summary, do not send the full entity with blobs, audit trails, and nested relationships.

## 5. Do not use one giant message for multiple operations

A "god message" request might contain fields for create, update, search, import, and export all at once. The client must guess which field combinations make sense, the server must validate many branches, and the schema becomes confusing.

Instead:

- Create request/response messages per operation and use case.
- Use nested sub-messages to reuse stable structures.
- Use `oneof` when choices are genuinely mutually exclusive.
- Use `FieldMask` for partial updates if the contract requires patch semantics.
- Separate control metadata from business payload.
- Do not add fields just to avoid designing a separate RPC when semantics differ.

For example, `oneof` fits when a data source can be either a URL or inline text, but never both at the same time:

```proto
message ImportSource {
  oneof source {
    string object_uri = 1;
    bytes inline_data = 2;
  }
}
```

Even when using `oneof`, `inline_data` still requires a size limit. `oneof` solves schema selection; it does not bound payload size by itself.

## 6. Large files and binaries should go through object storage

Do not send videos, archives, raw images, or multi-megabyte/gigabyte files inside a gRPC message just because Protobuf has a `bytes` type.

A generally suitable pattern:

1. Client asks the server to create an upload session or obtain upload details.
2. Server authenticates the caller, checks quota, and issues an upload ID along with a time-limited URL/token.
3. Client uploads the file directly to object storage over the appropriate channel.
4. Client calls a finalize RPC with upload ID, object key, size, and checksum.
5. Server verifies object existence, metadata, and access permissions.
6. Application service writes resource metadata to the database.

The RPC can carry a reference to the object rather than the entire file:

```proto
message CompleteUploadRequest {
  string upload_id = 1;
  string object_key = 2;
  int64 content_length = 3;
  bytes sha256 = 4;
}

message CompleteUploadReply {
  string resource_id = 1;
  string state = 2;
}
```

The client should not be allowed to freely choose the object key if doing so could overwrite another tenant's objects. The server must bind the upload session to the tenant, user, resource type, expiry, and quota. Do not log presigned URLs or upload tokens.

If files are small and the contract enforces a low limit, inline `bytes` can still be reasonable. Decide based on maximum size, concurrency, and memory budget rather than the convenience of a single example.

## 7. When continuous transfer is needed, use streaming with bounded chunks

gRPC streaming fits when data is produced or consumed incrementally. Each message in the stream still needs a bounded size; streaming does not mean an unbounded single message.

Example client-streaming upload:

```proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bytes checksum = 4;
  bool final_chunk = 5;
}

message UploadResult {
  string resource_id = 1;
  int64 bytes_received = 2;
}

service UploadService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
```

The server processes one chunk at a time instead of buffering the entire file in the heap. Each chunk should have an explicit maximum byte size; the limit must leave headroom for metadata fields, Protobuf overhead, and compression behavior.

With bidirectional streaming, the server can send a receipt/ack for each sequence so the client knows which chunks were durably stored. With client-streaming that returns only one final response, the client needs a resume/status query mechanism if the connection drops mid-transfer.

## 8. Design a resumable chunk protocol

A multi-chunk upload requires clear semantics:

- `upload_id` identifies the session.
- `sequence` increases monotonically with chunk order.
- `checksum` verifies chunk integrity.
- Server stores a checkpoint/receipt after a chunk is durably written.
- Duplicate sequence with the same checksum returns the previous receipt.
- Duplicate sequence with different content is rejected.
- Finalization succeeds only when all chunks are present and total bytes/checksum match.
- Sessions have expiry, quotas, and cleanup for abandoned uploads.

Do not rely solely on message ordering within a single stream if the client can reconnect. Sequence numbers enable the server to detect missing, duplicate, or out-of-order chunks.

If chunks are written to object storage, the database checkpoint must reflect the actual object state. Handle crashes between writing the object and recording the checkpoint using stable object keys, checksums, and a reconciliation process.

## 9. Backpressure and bounded buffering

Streaming reduces the need to hold the entire payload in memory, but only if the application processes incrementally and controls rate.

If the server reads faster than the database/object storage can write, or the producer emits messages faster than the consumer processes them, internal queues can grow unbounded. In that case, streaming still causes `OutOfMemoryError`.

Practices:

- Use a bounded queue if decoupling chunk receipt from worker processing.
- Request/read more messages only when downstream has capacity.
- Apply gRPC flow control when using async streaming.
- Do not accumulate all chunks into a `List`/`ByteArrayOutputStream` for large files.
- Limit concurrent streams and total buffered bytes.
- Cancel the stream when the client loses authorization, exceeds quota, or hits the deadline.
- Monitor queue depth, in-flight bytes, and per-chunk processing time.

HTTP/2 flow control regulates bytes on the transport; application-level backpressure is still necessary to protect the database, object storage, and heap.

## 10. Configure inbound message limits deliberately

gRPC Java lets you configure inbound message limits. Example with Netty server:

```java
int maxInboundBytes = 8 * 1024 * 1024;

NettyServerBuilder server = NettyServerBuilder
    .forPort(8443)
    .maxInboundMessageSize(maxInboundBytes)
    .addService(uploadService);
```

The client also has its own inbound limit for responses:

```java
ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal", 8443)
    .maxInboundMessageSize(8 * 1024 * 1024)
    .useTransportSecurity()
    .build();
```

The example illustrates the gRPC Java Netty API; package/imports and how builders attach to Spring Boot depend on the starter in use. In Spring, configure servers/channels via builder customizers or properties supported by the starter to keep lifecycles consistent.

The server inbound limit applies to requests received from clients; the client inbound limit applies to responses received from the server. Raising the limit on the client does not make the server accept larger requests, and vice versa.

Choose limits based on the contract and capacity testing. Do not set hundreds of megabytes just because one current request failed with `RESOURCE_EXHAUSTED`. If a high limit is needed for one operation type, consider a dedicated endpoint/service or streaming instead of relaxing limits for all RPCs.

## 11. Compression does not replace payload design

gzip or other compression can reduce bytes sent over the network for compressible data. However, compression does not eliminate costs:

- The client still needs to serialize the message.
- The server still needs to decompress and parse it.
- The decompressed payload still consumes memory.
- CPU increases due to compression/decompression.
- Already-compressed or high-entropy data may shrink very little.
- Untrusted payloads can create resource pressure during decompression.

Do not raise message sizes just because compressed bytes are small. Understand which layer enforces limits in the library/driver in use and test with real compressed payloads. Application limits based on uncompressed logical bytes and record counts are still required.

Compression can also increase latency for small messages; enable it only when benchmarks show a net benefit.

## 12. Business limits and resource protection

Transport message limits do not replace application quotas. A small message can still ask the server to do huge amounts of work, such as an enormous `page_size`, complex filters, or repeated expensive queries.

Set limits on:

- Maximum items in repeated fields.
- Total bytes/string length in a request.
- Page size and page token validity.
- Chunk count, size per chunk, and total upload size.
- Concurrent streams/uploads per principal/tenant.
- Processing time and deadlines.
- Records exported/imported in one operation.
- Total memory/buffer allowed to be consumed.

Exceeding request limits may be `INVALID_ARGUMENT` if the caller sent values violating the contract; exceeding quota or capacity may be `RESOURCE_EXHAUSTED`. Do not use one status for every kind of limit; choose according to published semantics.

## 13. Schema evolution when splitting messages

When refactoring large messages into smaller requests/responses or adding pagination/streaming, preserve compatibility:

- Never change published field numbers.
- Never reuse deleted field numbers/names; mark them `reserved`.
- Add new fields additively with clear default semantics.
- Keep the old RPC during migration if legacy clients still use it.
- Create a new RPC for different semantics rather than silently changing the meaning of an old field.
- Use versioned packages/services when the contract requires incompatible changes.
- Collect telemetry on client versions and usage before removing old APIs.

A migration can add `ListOrdersPaged` alongside legacy `ListAllOrders`, transition clients in waves, and only then deprecate the old API. Do not change an existing response from "entire list" to "one page" without changing the contract.

## 14. Observing message size and performance

Track request/response sizes per RPC method and percentile, not just averages:

- Serialized message bytes p50/p95/p99.
- Item counts in repeated fields.
- Chunk size and total upload bytes.
- `RESOURCE_EXHAUSTED`/message-too-large errors.
- Serialization/deserialization CPU and latency.
- Heap allocation, GC pauses, and in-flight bytes.
- Stream concurrency, queue depth, and backpressure wait.
- RPC latency/deadlines/cancellations per method.

Do not use user ID, resource ID, or upload ID as metric labels. When investigating a specific request, use trace/log correlation with masked data.

Alert when p99 message size approaches limits, message-too-large errors rise, or heap/GC climbs with concurrency. A single large message may succeed; multiple concurrent large messages expose capacity issues.

## 15. Testing limits and load

A useful test suite should include:

| Scenario | What to verify |
| --- | --- |
| Request under limit | RPC processes normally |
| Request exceeds server inbound limit | Rejected before application handler per runtime behavior |
| Response exceeds client inbound limit | Client receives appropriate error without hanging call |
| Page size exceeds quota | Server clamps or returns INVALID_ARGUMENT per contract |
| Very large repeated field | Application caps record count/bytes |
| Chunk at limit | Streaming receives and writes incrementally |
| Chunk exceeds limit | Rejected without exhausting heap |
| Slow-reading client | Backpressure prevents unbounded queue growth |
| Client disconnects mid-upload | Checkpoint allows resume without duplicate writes |
| Invalid checksum | Chunk/finalize is rejected |
| Compression on/off | CPU, latency, and message limits are measured |
| Concurrent large RPCs | Heap, GC, pools, and p99 remain within SLO |

Use generated payloads of deterministic sizes and load test with realistic concurrency. Check both server and client inbound limits; testing one side does not prove the other side is configured properly.

## 16. Review checklist

- Every RPC has explicit limits on record count, bytes, or page size.
- Requests/responses contain only data needed for the use case.
- Large collections use cursor pagination or appropriate streaming.
- Large binaries use object storage/references or chunked streams.
- Streaming chunks have size caps, sequence numbers, checksums, and resume semantics.
- Application backpressure and bounded buffering are implemented.
- Client and server inbound message limits are configured deliberately.
- Message size is not confused with HTTP/2 frame size or flow control.
- Compression is benchmarked and not used to hide unbounded payloads.
- Per-tenant/principal quotas protect CPU, heap, database, and storage.
- Schema refactors preserve field numbers and compatibility.
- Metrics track message size, GC, stream concurrency, and `RESOURCE_EXHAUSTED`.
- Tests cover oversize payloads, concurrency, slow consumers, and interrupted uploads.

In **SPRING_GRPC**, making messages too large to avoid schema design increases memory pressure, latency, and failure risk under load. Bound payloads per use case, use pagination for collections, object storage for large files, and checkpointed chunk streaming when continuous transfer is needed. Configure inbound message limits as a last line of defense; they do not replace quotas, backpressure, or a well-designed contract.
