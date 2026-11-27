# Do Not Send Large Payloads via Metadata

gRPC metadata is designed to carry **short control information attached to an RPC call**, such as request ID, credentials, locale, or trace context. Metadata travels in HTTP/2 headers/trailers and is processed at the call boundary. It is not a channel for files, large JSON payloads, or business data.

In Spring gRPC, payloads belong in Protocol Buffers messages. When you need to transfer large or continuous data, consider a message with a bytes field, client/server streaming, or storing payloads in object storage and passing a reference via RPC. Choosing the right channel prevents exceeding header limits, reduces memory pressure, and keeps retries, flow control, and security manageable.

## 1. Metadata and Payloads Have Different Roles

A gRPC call has two primary data groups:

| Group | Where transmitted | Example | Characteristics |
| --- | --- | --- | --- |
| Metadata | Request/response headers and trailers | x-request-id, authorization, traceparent | Small, attached to the entire RPC, processed at call boundary |
| Payload | Protobuf request/response messages | order, image_chunk, document_content | Business data, has schema and can span multiple messages |

Example of a document upload request:

```text
Request metadata:
  x-request-id: req-42
  authorization: Bearer <token>

Request message:
  document_id: "doc-100"
  content: <binary document bytes>
```

Request ID and credentials help the server establish context, while the document content is the payload to process. Putting the entire document into metadata forces the system to transport business data through headers before the service receives the request message.

A simple rule: **metadata describes the call; messages carry the call content**. If a value changes per record in a stream, it belongs in a Protobuf message rather than metadata.

## 2. Why Do Large Payloads in Metadata Cause Problems?

Metadata is transported via HTTP/2 headers/trailers. Its size is constrained by multiple components along the path: gRPC client, server, HTTP/2 implementation, reverse proxy, API gateway, and load balancer. Actual limits may differ between development and production environments.

Key risks:

- **Exceeding header limits:** requests may be rejected at the transport or proxy before reaching the server interceptor/service. Applications should not assume they will always receive a specific gRPC status; the outcome depends on whichever component detects the limit.
- **Consuming more space than expected:** binary metadata uses Base64 encoding on the wire, increasing size compared to raw bytes. Base64 is not security encryption.
- **Repeating data on every RPC:** metadata is attached per call. Sending a large configuration or payload on every call transmits and parses the same data repeatedly.
- **Higher header-processing cost:** intermediate components must parse, inspect, and potentially log headers. Large headers increase memory, CPU, and latency overhead.
- **Harder retry and streaming control:** metadata is sent when the call starts, not a chunked delivery mechanism with message-level flow control.
- **Logging and security risk:** proxies, tracing agents, or debug loggers may capture metadata. Sensitive payloads placed in headers can leak unexpectedly.

HTTP/2 includes header compression, yet that **does not turn headers into a store for large payloads** and does not remove header-list size limits. Do not rely on HPACK to transmit files or business data.

Some gRPC documentation recommends keeping request header limits small (for example around 8 KiB in some default setups), though this is not a guaranteed number across every deployment. Check actual limits of the library and every proxy/gateway in use.

## 3. Choosing the Right Transmission Channel

| Requirement | Recommended approach | Why |
| --- | --- | --- |
| Request ID, verified tenant, locale | Short ASCII metadata | This is RPC-level context |
| Small byte data with clear bounds tied to one request | Bytes field in Protobuf message | Payload sits in the proper place and follows message-size policy |
| Moderate payload, single send/receive | Unary RPC with Protobuf message | Simple, easy to validate and process |
| Large file or data produced in parts | Client streaming or server streaming | Sends message by message, leveraging flow control |
| Continuous two-way data exchange | Bidirectional streaming | Each message can be processed as it arrives |
| Very large file requiring resumable upload/download or cross-service sharing | Object storage/file service and RPC passing reference | Decouples file transfer from gRPC's control plane |

There is no universal byte threshold valid for every system. Determine limits based on message-size configuration, infrastructure limits, memory, target latency, and concurrency.

## 4. Moderate Payloads: Put in Protobuf Messages

If data is small enough to fit within configured message limits, declare it in the `.proto` contract. Example:

```protobuf
syntax = "proto3";

service DocumentService {
  rpc StoreDocument(StoreDocumentRequest) returns (StoreDocumentReply);
}

message StoreDocumentRequest {
  string document_id = 1;
  string media_type = 2;
  bytes content = 3;
}

message StoreDocumentReply {
  string document_id = 1;
  int64 stored_bytes = 2;
}
```

The client sends the content in the request message; the server validates size, media type, and access permissions before processing. Metadata still holds only call-level info like request ID or authorization.

This pattern works when payloads are moderate and processing fits within a single RPC. A `bytes` field does not exempt payloads from limits: gRPC still enforces message-size limits, and holding entire byte arrays in memory can create pressure under high concurrency.

## 5. Large Payloads: Use Streaming and Controlled Chunking

When files are large or need incremental transfer, client streaming is often appropriate: the client sends multiple request messages on one RPC, the server processes each chunk and returns a single result upon completion.

An illustrative contract:

```protobuf
syntax = "proto3";

service UploadService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}

message UploadChunk {
  string upload_id = 1;
  uint64 sequence = 2;
  bytes data = 3;
  bytes chunk_sha256 = 4;
  bool last = 5;
}

message UploadResult {
  string upload_id = 1;
  uint64 stored_bytes = 2;
  bytes content_sha256 = 3;
}
```

Fields `upload_id`, `sequence`, checksums, and `last` represent a sample application design. They help the server:

1. Identify the upload session and check the caller has permission to write to the target storage.
2. Detect missing, duplicate, or out-of-order chunks according to defined policy.
3. Verify each chunk's checksum and the full-content checksum upon completion.
4. Mark the upload complete only after all data is received and verified.

Client streaming in Java can send messages via the observer returned by the generated stub:

```java
StreamObserver<UploadChunk> request =
    asyncStub.upload(new StreamObserver<UploadResult>() {
        @Override
        public void onNext(UploadResult result) {
            // Inspect final result from server.
        }

        @Override
        public void onError(Throwable error) {
            // Handle error; retry only per upload policy.
        }

        @Override
        public void onCompleted() {
            // RPC completed.
        }
    });

long sequence = 0;
while (hasMoreChunks()) {
    byte[] chunk = readNextChunk();
    request.onNext(UploadChunk.newBuilder()
        .setUploadId(uploadId)
        .setSequence(sequence++)
        .setData(ByteString.copyFrom(chunk))
        .build());
}
request.onCompleted();
```

This snippet outlines client flow; `hasMoreChunks()`, `readNextChunk()`, `uploadId`, and checksum computation belong to the application. For large data, never read an entire file into a single array before sending. Use bounded buffers and respect gRPC's flow control/backpressure mechanisms to avoid building unbounded chunk queues in memory.

### Things to Design for Streaming Uploads

- **Chunk size:** choose based on message limits, throughput, memory, and latency. Chunks too small increase overhead; chunks too large increase per-call memory and risk exceeding message limits.
- **Flow control:** never emit chunks faster than the server can receive/write. With async APIs, use gRPC readiness/flow-control signals instead of buffering endlessly in a queue.
- **Integrity:** validate size, sequence, and checksums; checksums do not replace caller authentication.
- **Retry/resume:** define whether `upload_id` is idempotent, how already-written chunks are recognized, and which sequence number the client resumes from after failure.
- **Cancellation and timeouts:** handle client cancellation, deadlines, server shutdown, and cleanup of incomplete uploads.
- **Resource limits:** cap total size, concurrent uploads, session lifetime, and temporary storage usage.

Do not split payloads into chunks unnecessarily if they easily fit in a single message and have no resume/streaming needs. Streaming is an architectural choice, not a reason to complicate every request.

## 6. Very Large Payloads: Store Externally and Pass References

For very large files, resumable transfers, cross-service sharing, or long-term storage, using object storage/a file service is usually more effective:

1. The client calls a `CreateUpload` RPC to request a scoped, time-limited upload session or URL.
2. The client transfers the file directly to object storage using the appropriate protocol.
3. The client calls a `CompleteUpload` RPC with upload ID/object key and checksum.
4. The server verifies permissions, upload state, checksum, and object metadata before marking completion.
5. Subsequent business RPCs pass only the short `document_id` or object reference.

Illustration:

```text
Client              Spring gRPC service              Object storage
  |                         |                              |
  |-- CreateUpload -------->|                              |
  |<-- upload session ------|                              |
  |                                                       |
  |---------------------- upload file ------------------->|
  |<--------------------- upload result ------------------|
  |                         |                              |
  |-- CompleteUpload ------>|                              |
  |                         |-- verify object/checksum --->|
  |<-- document ID ---------|                              |
  |                         |                              |
  |-- GetDocument(documentId) ---------------------------->|
```

If using pre-signed URLs, restrict HTTP method, object key, size, content type, and expiration; never log signed URLs. A signed URL is a time-limited credential—anyone holding it while valid can use it within the granted scope. The server must verify permissions at both session creation and completion steps.

An RPC passing a reference does not mean the server trusts any object key supplied by the client. Bind the object to the upload session, verified tenant, and authenticated principal to prevent cross-tenant data access.

## 7. Metadata Limits and Message Limits Are Two Distinct Configurations

Do not confuse header limits with Protobuf message limits:

| Limit | Applies to | What to control |
| --- | --- | --- |
| Metadata/header list size | Request headers and response headers/trailers | Total keys/values, binary metadata after wire encoding, and proxy limits |
| Inbound message size | Messages received by server/client | Size of each Protobuf message |
| Outbound message size | Messages sent by server/client | Size of each Protobuf message |
| Total upload/download | Entire transfer session | Total bytes, chunk count, duration, and temporary storage |

Increasing `maxInboundMessageSize` does not raise metadata limits. Increasing header limits is also not the right fix for a large file. Limits are configured across transport/server/client and proxies depending on versions; align them while keeping finite bounds.

If a system genuinely needs to raise a limit for a controlled case:

- Measure actual sizes and identify which component rejects requests.
- Set clear thresholds across client, server, and gateway/proxy.
- Limit concurrent requests and per-message memory budgets.
- Check status/transport errors when payloads exceed limits.
- Monitor message-size percentiles, rejection rates, and memory utilization.

Never set unlimited bounds just to avoid errors; that opens the door to oversized requests exhausting memory or degrading availability for other calls.

## 8. Security, Errors, and Testing

### Security

- Metadata is not a confidential channel. Use TLS/mTLS for connections and proper credentials for authentication.
- Do not place access tokens, personal data, or sensitive payloads into metadata merely out of convenience.
- Check permissions before writing files or creating object references; a client-supplied tenant ID does not prove permission by itself.
- Enforce limits on total bytes, chunk size, upload duration, and concurrent sessions to mitigate DoS.
- Sanitize file names/content types, inspect actual content, and never trust client-declared extensions.
- Never log payload contents, pre-signed URLs, or full metadata. Log allowed IDs, sizes, durations, and outcomes.

### Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Server interceptor never runs | Proxy/transport rejected headers before RPC reached server | Check gateway logs, header limits, and request size |
| RPC rejected as metadata grows | Total headers exceed one component's limit | Shrink metadata; move payload to message/stream |
| Message rejected despite small metadata | Exceeded inbound/outbound message size | Adjust bounded message size or switch to streaming |
| Memory spikes during uploads | Client/server buffering too many chunks concurrently | Use bounded buffers, flow control, streaming writes |
| Retries create duplicate files | Chunks/uploads are not idempotent | Use upload ID, sequence numbers, and resume state |
| Incomplete file saved | Missing chunks or missing final checksum check | Verify sequences, total bytes, and checksum before completing |
| URL download accesses another tenant's object | Object not bound to principal/tenant | Enforce permissions at create, complete, and download |

### Test Matrix

| Test case | Result to verify |
| --- | --- |
| Small valid metadata | Server receives exact key/value |
| Metadata growing toward limit | Enforcing component rejects cleanly; service does not assume partial receipt |
| Binary metadata | Small byte data restored accurately without manual Base64 |
| Unary message under threshold | RPC completes with intact payload |
| Unary message over threshold | Appropriate error returned; no unintended partial data written |
| Multi-chunk streaming | Ordering, total bytes, and checksum are accurate |
| Duplicate/missing/bad-checksum chunk | Upload rejected or resumed per policy |
| Client cancel/deadline exceeded | Server stops work and cleans temporary resources |
| Concurrent multi-tenant uploads | No mixing of objects, sessions, or data across tenants |
| Expired/unauthorized object storage URL | Upload/download denied |
| Proxy and TLS | Limits, security, and error behavior match deployment environment |

Combine unit tests for chunk/checksum validators, integration tests for gRPC streaming, and tests through real proxies. In-process transport is useful for validating message/interceptor logic, but does not fully emulate HTTP/2 or gateway limits.

## 9. Practice Exercise

A Spring gRPC service accepts PDF files to store invoices. The client currently sends the entire file in metadata `x-invoice-bin`, causing some requests to be rejected at the gateway.

**Requirements:**

1. Explain why binary metadata is unsuitable for large PDFs and why Base64 increases wire size.
2. Propose a Protobuf schema using a unary message for small files and client streaming with chunks for large files.
3. Define chunk size, maximum total size, checksums, sequence numbers, upload ID, and resume policy.
4. Propose object storage/pre-signed URLs when files are very large or require durable uploads.
5. Distinguish metadata limits, per-Protobuf-message limits, and total upload limits.
6. Design tests for oversized metadata, oversized messages, missing chunks, invalid checksums, call cancellation, and cross-tenant access.

**Self-check questions:**

- How does call-scoped metadata differ from Protobuf payloads?
- Why does HPACK not turn metadata into a file transfer channel?
- When should unary `bytes` be used versus streaming?
- Can binary metadata safely carry large files better than ASCII metadata?
- Why limit both chunk size and total upload size?
- Why does increasing the message-size limit not solve header-size limits?
- When using pre-signed URLs, what permissions and expirations must be enforced?

**Key takeaway:** Do not send large payloads via metadata. Reserve headers/trailers for short RPC context; place moderate payloads in Protobuf messages, large data in streaming with flow control and integrity checks, or offload very large files to object storage and exchange references via gRPC. Configure finite limits across metadata, messages, and transfer sessions to protect service reliability.
