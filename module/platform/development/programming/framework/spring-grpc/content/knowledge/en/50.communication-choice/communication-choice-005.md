# Choosing Client Streaming for Uploads or Batches

Client streaming fits when a client needs to send **multiple messages within the same RPC** and the server only needs to return **a single aggregated result** after receiving all the data. This model is commonly used for chunked file uploads, bulk data imports, or sending a large stream of records without bundling everything into a single unary request.

The decision point is not just whether the data is large or small. Choose client streaming when data is generated or read sequentially on the client side, the server can process each message incrementally, and the business logic can finalize the result at the end of the stream. If the client needs per-part feedback while still sending, consider bidirectional streaming.

## 1. Understanding the Client Streaming Model

In a client-streaming RPC, the client sends a sequence of request messages and then closes the send half by completing the stream. The server receives messages via callbacks, processes them, and sends back exactly one final response.

Basic sequence:

1. The client opens the RPC.
2. The client sends the first message to declare upload or batch metadata.
3. The client sends chunks or records sequentially.
4. The client calls **onCompleted()** to signal that all requests have been sent.
5. The server validates the end-of-stream data, completes the business operation, and returns one response.
6. The client receives the response and then the completion callback.

Calling **onCompleted()** only means the client has finished sending requests. It does not confirm that the server has persisted the data successfully. The client should only confirm a successful upload after receiving a successful response from the server.

| RPC Type | Data Sent by Client | Data Returned by Server | Best Fit |
|---|---|---|---|
| Unary | One request | One response | One command or a small, clearly bounded payload |
| Server streaming | One request | Multiple responses | Client sends query criteria, server returns multiple results |
| Client streaming | Multiple requests | One response | Uploads, imports, batches needing one aggregated result |
| Bidirectional streaming | Multiple requests | Multiple responses | Both sides need continuous exchange, per-part feedback, or flow control |

For example, an application sending a 500 MB file can split the file into chunks and send them over a single client-streaming RPC. The server writes each chunk to temporary storage, verifies the checksum after receiving everything, and returns an upload ID and storage reference. The file never needs to be assembled into one giant byte array in client or server memory.

## 2. When Should You Choose Client Streaming?

Choose client streaming when most of the following hold:

- The data consists of multiple parts that can be sent sequentially: file chunks, import records, events, or items in a batch.
- The client can keep reading data while the RPC is open instead of building the entire payload upfront.
- The server can process or store parts incrementally as they arrive.
- The business outcome can be returned once at the end, such as bytes stored, checksum, accepted count, and rejected count.
- One RPC represents a clear unit of work for applying deadlines, authentication, quotas, and status tracking.

Do not choose client streaming solely because you want to "send a lot of data". Consider other patterns in these cases:

- Use unary if the request is small, has a strict size bound, requires atomic handling, and a single request/response keeps the contract simpler.
- Use server streaming if the client sends only one request but needs to receive a long list or stream of results from the server.
- Use bidirectional streaming if the client needs acknowledgements, progress updates, or per-chunk/record results while continuing to send.
- Use a resumable upload protocol if the upload session must survive across multiple RPCs or client restarts. A single client-streaming RPC does not inherently provide resume capability.

A useful question when choosing an RPC type is: **does the server need to reply before the client finishes sending?** If not, client streaming is often the natural choice. If yes, determine whether bidirectional streaming is needed or whether progress can be separated into another status-query RPC.

## 3. Designing the Protocol Buffers Contract

For uploads, separate file metadata from chunk data. The first message declares the upload session; subsequent messages carry data. Use **oneof** to make each message's payload type explicit.

Example contract:

~~~proto
syntax = "proto3";

package files.v1;

option java_multiple_files = true;
option java_package = "com.example.files.v1";

service FileService {
  rpc Upload(stream UploadRequest) returns (UploadResponse);
}

message UploadRequest {
  oneof payload {
    UploadStart start = 1;
    UploadChunk chunk = 2;
  }
}

message UploadStart {
  string upload_id = 1;
  string file_name = 2;
  string content_type = 3;
  int64 expected_size_bytes = 4;
  bytes expected_sha256 = 5;
}

message UploadChunk {
  uint64 sequence = 1;
  bytes data = 2;
}

message UploadResponse {
  string upload_id = 1;
  int64 stored_size_bytes = 2;
  bytes sha256 = 3;
  string object_reference = 4;
}
~~~

This contract expresses an important rule: the first message must be **start**, followed by **chunk** messages. The server must reject the stream if a chunk arrives before initialization, if there are invalid duplicate initializations, or if sequences violate agreed rules.

The fields serve distinct purposes:

- **upload_id** identifies an upload session and helps correlate when the client checks status.
- **expected_size_bytes** lets the server verify expected size and enforce quotas early.
- **expected_sha256** allows content verification after all data is received.
- **sequence** helps detect missing, duplicate, or out-of-order chunks.
- **object_reference** is the reference to the stored resource; avoid returning internal server filesystem paths unnecessarily.

Not every upload requires **upload_id**, checksums, and sequence numbers. Keep the fields that ensure integrity or serve business needs. For a simple stream over one connection, message order is inherently preserved within the RPC; sequence numbers are useful when validating data at the application layer, tracking progress, or supporting resume across multiple RPCs.

### Designing for Batches

For data imports, the same principle applies: the first message declares the batch, and subsequent messages carry records. Condensed example:

~~~proto
service ImportService {
  rpc Import(stream ImportRequest) returns (ImportSummary);
}

message ImportRequest {
  oneof payload {
    ImportStart start = 1;
    ImportRecord record = 2;
  }
}

message ImportStart {
  string batch_id = 1;
  string idempotency_key = 2;
}

message ImportRecord {
  uint64 sequence = 1;
  string external_id = 2;
  bytes payload = 3;
}

message ImportSummary {
  string batch_id = 1;
  int64 accepted = 2;
  int64 rejected = 3;
  repeated RecordError sample_errors = 4;
}

message RecordError {
  uint64 sequence = 1;
  string code = 2;
  string message = 3;
}
~~~

If records have a stable structure, describe them with explicit Protocol Buffers messages instead of **bytes payload**. Only use an opaque payload when the format is managed by another layer or multiple schemas must be supported.

The final response should contain aggregated counts and a bounded sample of errors. Do not pack millions of errors into the final response; the response is itself a gRPC message subject to size limits. For large error reports, store the report as a separate resource and return a reference for the client to download later.

## 4. Stream Protocol Conventions

Before implementing, document the rules both client and server must follow:

- The first message is the initialization message (**start**).
- Accept chunks or records only after initialization succeeds.
- Sequences start from a defined value, typically 0 or 1, and increment per message.
- Clearly specify whether empty chunks are valid. Usually there is no need to send empty chunks.
- Specify maximum total size, maximum per-chunk size, maximum record count, and maximum stream duration.
- When the client calls **onCompleted()**, the server verifies total bytes, record count, checksum, and business conditions before committing.
- When the client cancels or sends an error, the server cleans up temporary data or keeps a checkpoint per the designed resume policy.
- The server returns only one final response while the RPC is still active and processing has completed.

Do not use **onCompleted()** as a custom application-defined end message. It is gRPC's half-close signal. If the business logic needs a trailer containing client-declared total record count or checksum, place that information in **start** or in an explicit final message defined in the schema; then still call **onCompleted()** to close the send stream.

For batches, decide upfront whether the batch is **all-or-nothing** or **partial success**. All-or-nothing means publishing results only when the entire batch is valid. Partial success means individual records can be accepted or rejected independently, and the final response summarizes both groups. Clients must understand this policy so a successful RPC response is not misinterpreted as every record succeeding.

## 5. Sending a Stream from a Java Client

With a generated async stub, a client-streaming method takes a **StreamObserver** to receive the final response and returns a **StreamObserver** for the client to send request messages.

The following example illustrates reading a file in 64 KiB chunks:

~~~java
StreamObserver<UploadRequest> requestObserver =
        asyncStub.withDeadlineAfter(5, TimeUnit.MINUTES)
                .upload(new StreamObserver<UploadResponse>() {
                    @Override
                    public void onNext(UploadResponse response) {
                        // Confirm upload only after receiving this response.
                        System.out.println("Stored: " + response.getObjectReference());
                    }

                    @Override
                    public void onError(Throwable error) {
                        // Record the RPC error and update upload status.
                    }

                    @Override
                    public void onCompleted() {
                        // Server has finished the response stream.
                    }
                });

try (InputStream input = Files.newInputStream(filePath)) {
    UploadStart start = UploadStart.newBuilder()
            .setUploadId(uploadId)
            .setFileName(filePath.getFileName().toString())
            .setContentType(contentType)
            .setExpectedSizeBytes(Files.size(filePath))
            .build();

    requestObserver.onNext(
            UploadRequest.newBuilder().setStart(start).build());

    byte[] buffer = new byte[64 * 1024];
    long sequence = 0;
    int count;

    while ((count = input.read(buffer)) != -1) {
        UploadChunk chunk = UploadChunk.newBuilder()
                .setSequence(sequence++)
                .setData(ByteString.copyFrom(buffer, 0, count))
                .build();

        requestObserver.onNext(
                UploadRequest.newBuilder().setChunk(chunk).build());
    }

    requestObserver.onCompleted();
} catch (IOException | RuntimeException error) {
    requestObserver.onError(error);
    throw error;
}
~~~

This is a minimal example to clarify the API. In a real application, handle the response asynchronously with callbacks, futures, or appropriate coordination; do not block an event loop or web request thread just waiting for the stream to finish. Also ensure only one control thread calls **onNext**, **onCompleted**, or **onError** on the same request observer unless properly synchronized.

**withDeadlineAfter(...)** sets a deadline for the entire RPC. Choose the duration based on data size, expected bandwidth, storage speed, and server processing time. A deadline that is too short aborts valid uploads mid-flight; one that is too long can hold resources open when a client fails.

### Do Not Send Faster Than Transport Capacity

The loop above reads and sends continuously. For small files or test loads, this is easy to follow. For large files or slow networks, the producer can generate messages faster than the transport can send; queued data increases memory usage.

In grpc-java, you can use **ClientResponseObserver** to obtain **ClientCallStreamObserver** in **beforeStart(...)**. Check **isReady()** and register **setOnReadyHandler(...)** to read and send the next chunk only when the stream is ready. Keep the number of pending chunks bounded and serialize reading/sending. The ready callback may fire multiple times; the producer must avoid running two send loops concurrently.

An effective structure separates the data source into a bounded producer and a single sender. The sender pulls the next chunk only when gRPC signals readiness. Thus, disk read speed is throttled to the RPC's transmission capacity.

## 6. Receiving and Processing a Stream on the Server

The generated service base class provides a method taking **StreamObserver<UploadRequest>** and returning an observer for the server to receive request messages. The server can process each message in **onNext**, and only send **UploadResponse** after the **onCompleted** callback.

The processing flow should follow these steps:

1. On receiving the first message, verify upload permissions, **upload_id**, file name, content type, quota, and expected size.
2. Create temporary storage or an upload session. Do not publish the file as a complete resource yet.
3. For each chunk, validate the message type, sequence, chunk size, and total bytes. Write the chunk to temporary storage and update the checksum.
4. On receiving **onCompleted()**, verify the actual total size and checksum, then commit or publish the resource.
5. Return exactly one response with the final result and call **onCompleted()** on the response observer.
6. If **onError()** is received or the RPC is canceled, close files, release resources, and delete temporary data or save a checkpoint per the chosen policy.

The core logic can be separated into a business service such as **UploadSession**, responsible for **start**, **writeChunk**, **commit**, and **abort**. The gRPC service only coordinates callbacks and maps business errors to gRPC statuses. This allows testing file-storage logic independently of transport.

Do not hold the entire upload content in a **ByteArrayOutputStream** if sizes can be large. Stream to a temporary file, object storage, or a memory-bounded sink. If disk writes are slow, avoid blocking gRPC callback threads for long; use a bounded executor and throttle inbound flow control so the server does not accept more messages than it can process.

In grpc-java, when you need to control how many request messages the server receives ahead of time, use manual inbound flow control via **ServerCallStreamObserver**: disable auto-request and only request more messages after finishing previous ones. Enable this mechanism only when you thoroughly understand callback lifecycles and executor coordination; otherwise, forgetting to request more messages can stall the stream.

## 7. Deadlines, Cancellation, and Error Statuses

Client streaming is an RPC that spans the entire duration of data transmission. Treat deadlines, cancellation, and cleanup as part of the operational contract.

Commonly appropriate statuses:

| Status | When to Use |
|---|---|
| **INVALID_ARGUMENT** | Malformed message, missing start, wrong sequence, or checksum mismatch |
| **UNAUTHENTICATED** | Client has not provided valid authentication credentials |
| **PERMISSION_DENIED** | Client is authenticated but lacks permission to upload or import |
| **RESOURCE_EXHAUSTED** | Quota, size, count, or resource limit exceeded |
| **DEADLINE_EXCEEDED** | RPC exceeded the configured deadline |
| **CANCELLED** | Client or caller proactively canceled the RPC |
| **UNAVAILABLE** | Dependent component temporarily unable to serve |
| **INTERNAL** | Unexpected server-side error; do not expose internal details |

When the client cancels or the deadline expires, the server must stop processing as soon as possible and release resources. Check cancellation status before expensive operations, especially when writing data or calling storage services. If temporary data might remain after an abrupt process termination, implement TTL-based cleanup.

Do not return **OK** status simply because the server received all messages. Return success only after checksums, quotas, validation, and necessary commit operations succeed. If writing data succeeds but publishing fails, the response must reflect the actual state so the client is not misled.

## 8. Retries, Idempotency, and Upload Resumability

A client-streaming RPC does not automatically become a resumable upload protocol. When a connection drops mid-stream, the client may not know up to which chunk the server persisted. Resending the entire stream can waste bandwidth or create duplicate data if the server committed but the response was lost.

Design one of the following policies:

- **Single-attempt upload:** if the RPC fails, discard the temporary session and have the client restart from the beginning. Use for small files or when retransmission cost is acceptable.
- **Idempotent upload:** the client sends a stable **upload_id** or idempotency key. The server recognizes duplicate requests and avoids creating duplicate resources.
- **Resumable upload:** the server saves checkpoints by **upload_id** and returns how many bytes or sequences were received via a separate query RPC. The client opens a new RPC and resumes from the confirmed position.
- **Deduplicated batch:** use **batch_id** and stable record identifiers so the server recognizes already-processed records when the client retries.

Do not assume gRPC automatic retries will safely replay a partially sent stream. Retry capability also depends on retry policies, whether the RPC was committed, and whether request data is still buffered. For large uploads, design application-layer idempotency and resume if required by business needs.

For batches, define transaction boundaries. If one record fails, does the server halt the whole batch or continue processing remaining records? If partial success is accepted, clearly define which records committed and how the client queries or retries the failed subset. Never rely on clients guessing state after a network error.

## 9. Chunk Size, Limits, and Performance

Client streaming avoids creating one gigantic request, but each message still has size limits. gRPC inbound/outbound limits, channel/server settings, proxies, and gateways can all impose limits. Configure and test limits across every hop instead of assuming streams permit unlimited message sizes.

Practical guidelines:

- Start testing with moderate chunk sizes, such as 64–256 KiB, then benchmark on real infrastructure to find the balance between overhead and memory.
- Set size limits for individual chunks and total upload size.
- Never pack an entire file into one protobuf message. HTTP/2 framing at the transport layer does not remove gRPC message size limits.
- For batches with many small records, consider grouping a bounded number of records into one message to reduce overhead while keeping size limits and per-record processing intact.
- Enable compression only when data compresses significantly. Already compressed data like ZIP, JPEG, or video usually saves little while consuming CPU.
- Measure throughput, latency, memory, CPU, chunk counts, and server processing time; benchmark with file sizes and concurrency close to real load.

A stream can hold server connections and resources for a long time. Therefore, limit concurrent uploads per client or tenant, total in-flight bytes, send rate, and idle time without progress. Flow control regulates in-flight data; quotas and deadlines protect the system from long-lived resource-hogging sessions.

## 10. Security and Access Control

Uploads and imports often carry sensitive data. Apply TLS or mTLS per the deployment model, authenticate clients, and authorize per resource or tenant. Metadata can carry tokens or identity information, but should not contain file contents or large payloads.

On the server side:

- Authenticate and authorize before allocating temporary storage resources.
- Sanitize file names; never use client-supplied names directly to build filesystem paths.
- Validate content type and actual format if required by business rules.
- Limit sizes, chunk counts, record counts, concurrent streams, and per-tenant quotas.
- Avoid logging payloads, tokens, or personal data.
- Ensure incomplete data cannot be accessed as a published resource.

If clients can send data from untrusted sources, scan for malware or malicious content per system procedures before moving files into official production flows.

## 11. Integrating in a Spring gRPC Application

Protocol Buffers defines the contract, and the Java code-generation plugin generates service base classes, stubs, and message types. The server implements the generated client-streaming method from the contract; the client uses an async stub to send the sequence of messages.

In a Spring application, register the gRPC service implementation and configure channels/client stubs according to the Spring gRPC starter or version in use. Ensure client interceptors, default deadlines, TLS, authentication, and tracing are attached to the right channels. Having an interceptor as a Spring bean does not guarantee every channel uses it; verify your starter's registration mechanism.

Keep file or batch processing in a separate Spring business service. The gRPC adapter layer focuses on receiving the stream, validating protocol rules, and passing data to the service. The business service manages upload sessions, storage, transactions, and idempotency. This structure lets you test storage logic without starting a gRPC server.

Never hold a database transaction open for the entire time a client sends a large file. A stream can last minutes and hold connections or locks. Instead, store parts temporarily, then run a short transaction at the final commit step. For batches, choose per-batch or per-record transactions based on consistency requirements and rollback capability.

## 12. Testing Client Streaming

Tests should cover stream contracts, data integrity, errors, and load:

1. Send a valid upload with start and multiple chunks; verify the final response has the exact size and checksum.
2. Send a stream without start or with a chunk before start; verify the server returns **INVALID_ARGUMENT**.
3. Send missing, duplicate, or out-of-order sequences; verify the handling policy is enforced.
4. Send an empty file, an exact-limit file, and an over-limit file.
5. Disconnect or cancel the RPC mid-stream; verify temporary data is cleaned up or checkpoints are saved properly.
6. Corrupt the checksum; verify the server does not publish invalid data.
7. Resend the same idempotency key; verify no duplicate resource is created.
8. Slow down the server or client to test flow control and memory usage.
9. Test deadlines, authentication, quotas, and multiple concurrent uploads.
10. For batches, test both all-or-nothing and partial success according to the published policy.

An in-process gRPC server/channel is useful for testing interceptors, message ordering, and statuses. However, in-process tests do not cover TLS, proxies, gateways, HTTP/2, or network size limits. Add integration tests using a production-like deployment setup for transport-related concerns.

## 13. Operational Observability

Track each RPC with aggregated metrics:

- Streams started, completed, canceled, and failed by status.
- Bytes, chunks, or records received.
- Data reception duration and commit duration.
- Throughput, concurrent streams, and timed-out sessions.
- Uploads retried or resumed, batches with rejected records.

Use trace context to link operations in an upload or batch with downstream dependencies. Do not use **upload_id**, file names, tenant IDs, or user IDs as metric labels if they have high cardinality. You may record a sanitized reference ID in controlled logs to look up a specific session. Never log payloads or credentials.

Distinguish transmission time from post-stream processing time. A long-running RPC might result from a slow client upload, slow server storage writes, or an expensive commit step. Measuring phases separately helps pinpoint the bottleneck.

## 14. Quick Decision Guide

| Need | Choice |
|---|---|
| Send one small payload, immediate result | Unary |
| Send a large file in chunks, only need a result after everything arrives | Client streaming |
| Send many records, only need total succeeded/failed counts at the end | Client streaming |
| Need feedback or acknowledgement per chunk while still sending | Bidirectional streaming |
| Send one query and receive a long list of results | Server streaming |
| Need to resume upload after disconnection | Client streaming combined with an application-layer resume protocol |

Production readiness checklist:

- [ ] Contract clearly specifies initialization message, chunks/records, and final response.
- [ ] Size limits exist per message, total payload, record count, and stream duration.
- [ ] Server processes incrementally without holding large payloads in heap.
- [ ] Client and server have flow control matched to producer/consumer rates.
- [ ] Checksum or integrity verification exists when required by business logic.
- [ ] Cancellation, cleanup, deadlines, and statuses are defined.
- [ ] Retry, idempotency, transaction, and resume policies are defined.
- [ ] Tests cover stream failures, disconnects, concurrent load, and size limits.
- [ ] TLS, authentication, quotas, and safe logging are configured.
- [ ] Metrics and traces distinguish transmission time from processing time.

Client streaming is the right choice for uploads or batches when the client sends multiple data parts and the server only needs to finalize one result at the end. Solution quality depends on a clear stream contract, incremental processing, flow control, resource bounds, and recovery policies when an RPC does not complete.
