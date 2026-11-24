# Size Limits and Passing References Instead of Large Payloads

> Scope: designing bounded RSocket payloads, understanding frame size and fragmentation, streaming data with backpressure, and using object references to transfer large files via object storage.

## 1. Objectives

After this lesson, you will be able to:

- Distinguish frame size, single-message payload size, and total data size of a stream.
- Explain RSocket's 24-bit frame limit and the role of fragmentation/reassembly.
- Configure fragment thresholds and maximum reassembled payload limits in RSocket Java.
- Use `Flux` and `RSocketRequester.data(Publisher)` to transmit multiple chunks with backpressure.
- Choose when to send data inline, stream chunks, or send a reference to object storage.
- Design large uploads/downloads using upload intents, signed URLs, multipart transfers, and checksum verification.
- Test sizes, memory usage, timeouts, stream cancellation, and object access permissions.

## 2. Distinguishing Frame, Message, and Stream

In RSocket, these three concepts are related but not synonymous:

- A **Frame** is the unit of data on the wire. A frame has a header, frame type, flags, and optionally metadata/data.
- A **Logical message/payload** is the content an application sends in a single request or a single `onNext` emission. One logical payload may span multiple frames if fragmented.
- A **Stream** is the sequence of events in an interaction. For example, `REQUEST_STREAM` creates an initial request and the responder then sends multiple payloads; `REQUEST_CHANNEL` allows both sides to stream payloads.

A request-response interaction can carry a single large payload. RSocket can split that payload into multiple frames at the protocol layer and then reassemble them before the application receives the complete payload. Therefore, fragmentation does not automatically turn a large message into an application-level stream of independent items.

When designing size limits, clearly ask whether you are limiting:

1. The maximum size of a single frame on the transport.
2. The maximum size of a single logical payload after reassembly.
3. The size of each element in an application stream.
4. The total volume or duration of the entire upload/download.

These limits must work together. A low frame limit does not limit the total size of a fragmented message; limiting the number of stream elements does not limit total bytes if each element can be arbitrarily large.

## 3. RSocket Frame Limits

### 3.1. Protocol Limit

RSocket defines a 24-bit Frame Length field for transports that require framing. The maximum unsigned value is `16,777,215` bytes. According to the protocol specification, an entire RSocket frame including header and payload must not exceed `16,777,215` bytes, even when the underlying transport preserves message boundaries and does not need a Frame Length field.

Over TCP, the Frame Length is prepended before the frame, and the prefix field itself is not counted in the frame length. WebSocket already preserves message boundaries so this prefix is omitted. Transport framing rules do not alter the maximum size of an RSocket frame.

This is a protocol ceiling, not a target application payload size. Headers, metadata, encoding overhead, and transport or proxy limits all consume part of the budget. A system may enforce significantly lower limits to control memory usage and latency.

### 3.2. Practical System Limits

Size can be constrained at multiple layers:

| Layer | Example Limits to Check |
| --- | --- |
| RSocket protocol | Maximum frame size of 16,777,215 bytes |
| RSocket Java | Transport max frame length, fragment MTU, max inbound reassembled payload |
| WebSocket transport | Max frame/message payload of the WebSocket server, client, or proxy |
| Network edge | Load balancer, ingress, gateway, firewall, and timeouts |
| Serialization | Encoded size; JSON/base64 can inflate data size |
| Application | Allowed file size, tenant quota, chunk count, processing time, and memory |

Do not assume every component uses the same limit. Verify configurations on the requester, responder, transport, and intermediate infrastructure. If a proxy caps WebSocket messages at 64 KiB, the fact that the RSocket protocol allows larger frames will not let the request pass through that proxy.

### 3.3. Size After Serialization

Limits must be calculated on the actual encoded data, not solely on the Java object or original file size. For example:

- JSON adds field names, delimiters, and escape sequences.
- Base64-encoding binary data increases byte count compared to the raw bytes.
- Composite metadata, routes, and authentication metadata also take up space.
- Compression can reduce wire bytes, yet still consumes CPU and memory for compression/decompression.

Do not use compression as a substitute for size limits. Also limit decompressed data and watch for compressed payloads with abnormal expansion ratios.

## 4. Fragmentation and Reassembly

### 4.1. How It Works

The protocol allows fragmenting `REQUEST_*` frames and `PAYLOAD` frames when content does not fit within the target frame size. The `F` (Follows) flag indicates that more fragments follow. For a fragmented request, the initial request frame is sent first, followed by subsequent fragments carried in `PAYLOAD` frames. Metadata must be transmitted completely before data.

Once all fragments arrive, the implementation reassembles them into the logical payload and hands it to the processing layer. Fragments of the same payload do not count as separate demand messages: one fragmented payload still corresponds to one element under stream flow control.

### 4.2. Fragmentation Is Not Application-Level Streaming

Suppose an application sends a 40 MB `byte[]` in a request-response call. With fragmentation, RSocket can transmit that content in smaller frames. However, the receiving side still must reassemble the entire 40 MB logical payload before the handler processes it.

This can cause:

- Higher peak memory usage as multiple fragments and the reassembled payload coexist during processing.
- Longer wait times before the handler can begin working.
- Increased GC pressure if the payload is copied multiple times.
- Higher risk of a single request consuming a large share of the memory budget.

Fragmentation is useful for fitting transport MTUs or frame limits. It does not replace streaming when large data should be processed incrementally.

### 4.3. Configuring Fragmentation in RSocket Java

`RSocketConnector.fragment(mtu)` sets the MTU threshold above which frames are split into fragments. `RSocketServer.fragment(mtu)` provides the corresponding server-side setting. In Spring Boot with a standalone RSocket server, `spring.rsocket.server.fragment-size` configures the server's fragment size.

Requester configuration example:

```java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.fragment(64 * 1024))
        .tcp("localhost", 9898);
```

Standalone server configuration example in Spring Boot:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
      fragment-size: 64KB
```

The `64 KiB` values above are configuration examples, not mandatory or optimal values for every environment. Choose an MTU based on transport, proxies, latency, throughput, and benchmark results. Both sides must agree on frame limits each side can receive.

### 4.4. Limiting Payload Size After Reassembly

RSocket Java provides `maxInboundPayloadSize(...)` on `RSocketConnector` and `RSocketServer` to cap payload size after reassembly. If unconfigured, the reassembled payload limit may not be bounded by this option.

There is an important constraint: `maxInboundPayloadSize` must be greater than or equal to `Transport.maxFrameLength()`, because a single frame could otherwise exceed the reassembly limit if configured smaller than the transport frame limit.

Example when building an RSocket server manually:

```java
RSocketServer.create(acceptor)
        .fragment(64 * 1024)
        .maxInboundPayloadSize(32 * 1024 * 1024)
        .bind(transport);
```

The 32 MiB figure illustrates a specific policy and must be checked against `Transport.maxFrameLength()` of the transport in use. Do not copy this value without verifying frame limits. In production, set a threshold large enough for a single frame while still bounding total reassembled payloads within your memory budget.

### 4.5. When Should Fragmentation Be Used?

Use fragmentation when a single payload has a finite, well-bounded size and must traverse a transport with a smaller MTU than that payload. Do not use fragmentation as the default solution for very large files or unpredictable data sizes.

## 5. Streaming Data in Chunks

### 5.1. RSocket Backpressure

RSocket implements Reactive Streams semantics over the network. For `REQUEST_STREAM` and `REQUEST_CHANNEL`, the requester sends demand; the responder should emit only as many elements as the receiver has requested. Demand is expressed in number of messages, not total bytes.

Consequently, backpressure controls memory effectively only when each stream element also has a bounded size. A stream of 10 elements where each element is 100 MB can still create severe memory pressure.

Choose a fixed chunk size or an upper bound per element. Starting around 64–256 KiB can serve as a benchmark baseline in some systems, though you should benchmark with real payloads, concurrent connections, latency, and throughput. This is a benchmarking suggestion, not a protocol limit.

### 5.2. Choosing the Interaction Type

| Interaction | Usage Pattern |
| --- | --- |
| Request-Response | Send metadata or one small request, receive one result |
| Request-Stream | Send one small request, receive multiple chunks or records |
| Request-Channel | Send multiple chunks while receiving streamed ACKs/progress or results |
| Fire-and-Forget | Send a small notification needing no business response |

For downloads, `REQUEST_STREAM` fits when the client sends one request containing an object ID and the server emits multiple chunks. For uploads needing ACKs or progress, `REQUEST_CHANNEL` lets the client send chunks while the server emits corresponding responses. If an upload needs only one final result, design the interaction to match the cardinality supported by Spring RSocket; do not collect the entire input stream into one huge object just to return a single response.

### 5.3. Sending Streams with RSocketRequester

`RSocketRequester.RequestSpec.data(Object)` accepts a Reactive Streams `Publisher`, including `Flux` and `Mono`. For multi-element publishers, you can specify the element type using the `data(publisher, elementClass)` overload to avoid inferring the type for each element.

Example client sending `ByteBuffer` chunks and receiving an ACK stream:

```java
Flux<ByteBuffer> chunks = readFileInChunks(path, 128 * 1024);

Flux<UploadAck> acknowledgements = requester
        .route("asset.upload.{uploadId}", uploadId)
        .data(chunks, ByteBuffer.class)
        .retrieveFlux(UploadAck.class);
```

`readFileInChunks` represents a publisher reading the file in bounded buffers. The publisher must read incrementally rather than calling `Files.readAllBytes` before building the `Flux`. Emitted `ByteBuffer` instances must keep their contents intact until the encoder finishes processing them.

The responder can receive a chunk stream and process it sequentially:

```java
record UploadAck(long sequence, String status) {}

@MessageMapping("asset.upload.{uploadId}")
Flux<UploadAck> upload(
        @DestinationVariable String uploadId,
        Flux<ByteBuffer> chunks) {

    return chunks.index()
            .concatMap(indexed ->
                    storage.append(uploadId, indexed.getT1(), indexed.getT2())
                            .thenReturn(new UploadAck(indexed.getT1(), "stored")));
}
```

This illustrates the contract; `storage.append(...)` is the application's chunk-persistence API. `concatMap` processes sequentially to preserve chunk order and limit concurrent writes. If using `flatMap`, bound concurrency and prefetch while ensuring the storage layer supports concurrent writes safely.

For `UploadAck`, both sides need a matching codec in `RSocketStrategies`. `ByteBuffer` is supported by built-in codecs; record types need an appropriate codec such as JSON, CBOR, or Protobuf. Do not serialize byte arrays into Base64 JSON if the goal is efficient binary transfer.

### 5.4. Stream Downloads

A download can be modeled as a stream of buffers:

```java
Flux<ByteBuffer> fileChunks = requester
        .route("asset.download.{assetId}", assetId)
        .retrieveFlux(ByteBuffer.class);
```

The server emits buffers incrementally from a file/object stream. The client writes each buffer to the target file or storage. Avoid `.collectList()`, `.reduce(...)` into one giant byte array, or holding all chunks in memory before writing.

If the client simply needs the file, it can download directly from object storage via a signed URL instead of routing all bytes through the RSocket service. RSocket can still return status, metadata, or download tickets.

### 5.5. Controls Needed When Streaming

- Cap individual chunk size and maximum chunk count.
- Bound concurrent write operations and prefetch.
- Use real backpressure; avoid switching to unbounded queues or buffering the entire stream.
- Cancel streams when the client disconnects or the upload session expires.
- Record sequence numbers to detect missing, duplicate, or out-of-order chunks.
- Use per-chunk checksums or whole-object checksums to detect corrupted data.
- Define timeouts and idempotent retry policies; retrying a chunk must not duplicate content.
- Close files, channels, and buffers properly across their lifecycle; if using Netty reference-counted/zero-copy buffers, follow release rules strictly.

## 6. Passing References Instead of Large Data

### 6.1. Separating Control Plane and Data Plane

For large files, a typically more efficient approach uses RSocket for control and object storage for data:

- **Control plane over RSocket:** create upload sessions, check permissions, return upload instructions, notify completion, query status, and grant download access.
- **Data plane over object storage:** transfer bytes directly to S3-compatible storage, Google Cloud Storage, Azure Blob Storage, or an equivalent storage service.

Services do not need to receive and forward entire files unless mandatory processing is required. This reduces memory copies, CPU usage, network hops, and load on RSocket services.

### 6.2. What Should a Reference Contain?

An internal reference can describe an object without carrying the file contents:

```java
public record AssetReference(
        String assetId,
        String version,
        long sizeBytes,
        String mediaType,
        String sha256) {}
```

`assetId` is an opaque server-managed identifier. `version` references an immutable version. `sizeBytes`, `mediaType`, and `sha256` support contract verification. Internal bucket names or storage keys do not necessarily belong in public references.

A reference must not be treated as an access token. When receiving `assetId`, the server must still verify principal, tenant, object status, and read/write permissions. Never trust client-declared `sizeBytes`, `mediaType`, or checksums without verifying them against the actual stored object.

### 6.3. Upload Flow via Signed URL

A common upload workflow:

1. Client sends RSocket request `asset.upload.prepare` with filename, expected size, media type, and checksum if available.
2. Server authenticates the user, checks quota/tenant, enforces file limits, and creates an upload session.
3. Server issues a signed URL or multipart upload grant scoped to the exact object key, exact HTTP method, and a short expiration; returns the URL with upload ID and required headers.
4. Client uploads bytes directly over HTTPS to object storage. For large files, use multipart/resumable uploads so incomplete parts can be resumed.
5. Client sends RSocket request `asset.upload.complete` with upload ID, part ETags, or required checksum.
6. Server verifies object state in storage, actual size, checksum, owner/tenant, and content checks such as malware scanning if needed.
7. Upon successful verification, the server marks the object ready and returns `AssetReference`.

Control contract example:

```java
record UploadPrepare(String fileName, long sizeBytes, String mediaType) {}
record UploadGrant(String uploadId, URI uploadUri, Instant expiresAt) {}
record UploadComplete(String uploadId, String checksum) {}

Mono<UploadGrant> grant = requester
        .route("asset.upload.prepare")
        .data(new UploadPrepare(fileName, sizeBytes, mediaType))
        .retrieveMono(UploadGrant.class);
```

`uploadUri` is a capability granting narrowly scoped write access. Anyone possessing the URL can exercise that permission until it expires or is revoked as supported by the storage provider. Never log full URLs in logs, analytics, or exceptions. Grant access only for a specific object/method and short duration; use multipart grants when uploading in parts.

Never accept an arbitrary URL from a client and have the backend fetch it unchecked. If the backend must fetch a user-supplied URL, enforce anti-SSRF policies: allowlist schemes/hosts, block private/link-local/metadata addresses, control redirects, and cap bytes/time.

### 6.4. Download Flow

1. Client sends `asset.download.prepare` with `assetId` and desired version.
2. Server checks read permissions, tenant, object status, and retention policy.
3. Server generates a short-lived GET-only signed URL for the exact object/version.
4. Client downloads directly from storage over HTTPS and streams it to disk.

If watermarking, decryption, transformation, or filtering is required before returning data, the service can stream the object from storage through a processing pipeline and emit chunks via RSocket. Backpressure, size limits, and timeouts are still required there.

### 6.5. Securing Object References

An unpredictable `assetId` does not replace authorization. Always:

- Verify access permissions each time a signed URL is issued.
- Bind objects to tenant/owner in the database and enforce that relationship.
- Issue signed URLs with short TTLs and specific method and object scopes.
- Never treat a signed URL as a public URL or store it as a permanent identifier.
- Keep storage object keys server-side; clients only need opaque IDs.
- Verify size, checksum, and version before marking an upload complete.
- Configure lifecycle rules for abandoned uploads, incomplete multipart uploads, and expired objects.
- Protect objects with encryption at rest and least-privilege storage permissions.
- Validate media type from actual file contents when appropriate; do not trust file extensions alone.

## 7. Choosing the Right Strategy

| Scenario | Recommended Transfer | Reason |
| --- | --- | --- |
| Metadata, commands, small bounded objects | Inline in one RSocket payload | Simple, fewer round trips |
| Moderate single payload larger than frame MTU | Bounded fragmentation | Remains one logical message; no manual chunk management |
| Data generated or consumed incrementally | `Flux` chunks via Request-Stream/Channel | Backpressure regulates transfer rate |
| Large files, long uploads/downloads, or multipart/resume needed | Object storage + reference/signed URL | Avoids holding files in RSocket services and leverages storage capabilities |
| Data requiring processing before storage or delivery | Stream through service with bounded buffers | Service inspects/transforms without loading the whole file into RAM |

No single size threshold fits every application. Pick inline limits based on memory budget, concurrency, transport, and latency. One service may cap JSON requests at a few tens of KiB, while another pipeline allows stream chunks of a few hundred KiB; that is a system policy, not an RSocket default limit.

## 8. Common Errors and Diagnosis

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Frame rejected or connection closed | Frame exceeds protocol/transport limit | Measure encoded frame size; inspect max frame settings on both sides and proxies |
| Small requests work, large files fail | Reassembled payload exceeds limit or out of memory | Inspect fragment MTU and `maxInboundPayloadSize` |
| Fragments are sent yet handler receives one huge payload | Confusing fragmentation with application streaming | Switch to `Flux` chunks or object references |
| WebSocket fails while TCP succeeds | WebSocket container/proxy has a smaller max message/frame limit | Inspect WebSocket frame payload length and gateway limits |
| RAM grows proportionally to total file size | Using `readAllBytes`, `collectList`, `join`, or unbounded buffers | Switch to incremental read/write; bound prefetch and concurrency |
| Duplicate chunks after upload retry | Missing sequence/idempotency key or non-idempotent commit logic | Track upload ID + chunk index/checksum and handle duplicates safely |
| File upload succeeds yet server never recognizes it | Client skipped complete call or server did not verify object state | Use an upload state machine and verify storage before marking READY |
| User reads another tenant's object | Relying on object ID or signed URL without owner checks | Verify tenant/owner before issuing signed URLs |
| Signed URL expires mid-upload | TTL shorter than upload duration or multipart grants not renewed | Issue per-part URLs, renew grants with auth, or start a new session |
| Checksum mismatch | Client/server hashed different representations or missed bytes | Explicitly specify checksum over raw bytes, encoding, and algorithm |

## 9. Metrics and Testing

Monitor at minimum:

- Payload size after serialization and largest frame size.
- Reassembled payload sizes and limit-exceeded counts.
- Average/maximum fragments per payload.
- Chunk counts, chunk sizes, throughput, and upload/download durations.
- Active request counts, storage write concurrency, and queue depth.
- Heap usage, direct memory, GC pauses, and Netty buffer leaks.
- Upload success rate, abandoned multipart uploads, checksum mismatches, and retries.
- Signed URLs issued, lifetimes, and authorization failures; never log secret URLs.

The test suite should cover:

1. Payloads smaller than the inline limit process normally.
2. Payloads just below and just above application limits produce expected results.
3. Payloads fragmented across multiple frames reassemble accurately.
4. Reassembled payloads exceeding `maxInboundPayloadSize` are rejected cleanly.
5. Requests over TCP and WebSocket are tested against real transport limits.
6. Multi-chunk streams preserve order and stay within memory bounds under slow consumers.
7. Cancelling a stream releases file handles, buffers, and upload sessions.
8. Retrying the same chunk does not create duplicate or out-of-order data.
9. Multipart uploads missing parts or failing checksums are not marked READY.
10. Expired signed URLs or wrong HTTP method/object requests are rejected by storage.
11. Unauthorized users/tenants cannot obtain references or signed URLs for other objects.
12. Files exceeding quota, maximum chunks, or upload timeout are rejected per policy.

Do not test only with one small sample file locally. Measure with concurrent connections and network speeds close to production.

## 10. Design Checklist

- [ ] Distinguished frame limit, payload reassembly limit, and stream element limit.
- [ ] Measured serialized size including metadata.
- [ ] Inline payloads have explicit business size caps.
- [ ] Fragment MTU is compatible with transports and proxies.
- [ ] `maxInboundPayloadSize` is configured and greater than or equal to `Transport.maxFrameLength()`.
- [ ] Large payloads are streamed in bounded chunks or stored outside RSocket.
- [ ] Streams enforce backpressure, bounded concurrency, and finite prefetch.
- [ ] Whole files are not buffered into RAM via `readAllBytes`, `collectList`, or unbounded buffers.
- [ ] Chunks include sequence/idempotency and checksums where needed.
- [ ] Object references use opaque IDs/versions without exposing internal storage keys.
- [ ] Signed URLs have narrow method/object scope and short TTLs.
- [ ] Server validates permissions, quota, size, checksum, and object state.
- [ ] Lifecycle cleanup exists for abandoned uploads and incomplete multipart uploads.
- [ ] Metrics track payload sizes, memory, throughput, retries, and errors.

## 11. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, backpressure, `RSocketRequester`, `data(Publisher)`, and codecs.
- [RSocket Protocol — Framing](https://github.com/rsocket/rsocket/blob/master/Protocol.md#framing): frame headers and the 24-bit frame limit.
- [RSocket Protocol — Fragmentation and Reassembly](https://github.com/rsocket/rsocket/blob/master/Protocol.md#fragmentation-and-reassembly): `F` flag, metadata/data order, and fragment reassembly.
- [RSocket Java — RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): `fragment(mtu)`, `maxInboundPayloadSize`, and payload decoder.
- [RSocket Java — RSocketServer API](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocketServer.html): server-side fragmentation and reassembled payload limits.
- [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.rsocket.server.fragment-size` and RSocket server properties.

Exact thresholds depend on RSocket Java version, Spring Boot, transport, and proxies. Check the Javadoc of the dependency version in use before deploying limit configurations.
