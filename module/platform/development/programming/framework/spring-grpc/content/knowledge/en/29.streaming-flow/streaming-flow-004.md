# Inbound Message Size Limits

## Learning Objectives

After this lesson, you will be able to:

- Explain gRPC's inbound message size limit and its per-message scope.
- Configure receive limits on both the server and client using gRPC Java.
- Distinguish message size from HTTP/2 frame size, flow-control windows, metadata size, and total stream volume.
- Choose limits aligned with payloads, streaming chunks, and memory budgets.
- Handle errors when messages exceed the limit and test both transmission directions.
- Combine message-size limits with quotas, concurrency limits, and validation to protect Spring gRPC services.

## 1. Why Must Inbound Messages Be Limited?

A gRPC RPC can carry Protobuf messages containing many fields, large lists, or binary data. If a server accepts messages of arbitrary size, a client can force the server to allocate excessive memory to receive, decode, and process the payload. When multiple clients do this concurrently, heap and CPU can be exhausted before business logic even rejects the request.

An **inbound message size limit** caps the size of each individual message an endpoint agrees to receive. It acts as a protective layer at the gRPC level before the application processes the full message contents.

In **SPRING_GRPC**, this limit must be considered for large unary requests, each chunk in client-streaming, each response in server-streaming, and each message in both directions of bidirectional streaming. You should not raise the limit simply to make **RESOURCE_EXHAUSTED** errors disappear; you need to determine how large a valid payload can be and whether the system has enough memory to handle concurrent requests.

## 2. The Limit Applies Per Message

A stream can transmit many messages. The inbound message size limit applies individually to each received message, not to the cumulative byte total across the entire RPC.

For example, if the limit is 4 MiB:

- A 3 MiB message can be accepted.
- A 5 MiB message exceeds the limit and is rejected.
- A stream of 100 messages, each 1 MiB, can still transmit roughly 100 MiB in total if other limits permit.

Therefore, a message-size limit is not a total quota for an upload or subscription. For long-lived streaming, the application also needs limits on total bytes per RPC, message count, active duration, sending rate, and concurrent streams.

## 3. Server and Client Have Separate Inbound Limits

Inbound is always understood from the perspective of the receiving endpoint:

| Endpoint | Inbound data | Protective limit |
| --- | --- | --- |
| gRPC server | Requests from clients | Size of each request message the server receives. |
| gRPC client/channel | Responses from the server | Size of each response message the client receives. |

For example:

- With client-streaming, the server's inbound limit applies to each request chunk.
- With server-streaming, the client's inbound limit applies to each response.
- With bidirectional streaming, the server limits messages traveling from client to server; the client limits messages traveling from server to client.

The two sides do not automatically share the same configuration. A server accepting large requests/responses does not mean the client accepts that size as well. If the contract permits large messages, configure and test receive limits on both endpoints.

## 4. Configuring with gRPC Java

gRPC Java provides the **maxInboundMessageSize(int)** method on server and channel builders. The parameter is the maximum number of bytes for a single inbound message.

Example configuring a server to receive up to 8 MiB:

~~~java
import io.grpc.Server;
import io.grpc.ServerBuilder;

final int MAX_INBOUND_BYTES = 8 * 1024 * 1024;

Server server = ServerBuilder.forPort(9090)
    .maxInboundMessageSize(MAX_INBOUND_BYTES)
    .addService(new UploadService())
    .build()
    .start();
~~~

Example configuring a client channel to receive responses up to 8 MiB:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

final int MAX_INBOUND_BYTES = 8 * 1024 * 1024;

ManagedChannel channel = ManagedChannelBuilder
    .forAddress("localhost", 9090)
    .maxInboundMessageSize(MAX_INBOUND_BYTES)
    .build();
~~~

In the examples, the server limit controls inbound requests and the channel limit controls inbound responses. Use consistent byte units when converting from application configuration to builders; avoid confusing decimal MB with binary MiB.

Specific builders such as Netty also provide equivalent configuration. If the application uses Spring Boot auto-configuration, configure the builder/factory managed by the starter in use. Property names and extension points depend on the integration library and version; there is no single universal Spring property applicable to every gRPC starter. Do not create a separate server or channel solely to set limits if the application already uses a Spring-managed builder.

## 5. Default Value and Choosing a Limit

Common gRPC Java builders typically default the inbound message size to **4 MiB**. The actual value can depend on version, transport, and integration layer; verify the running configuration rather than relying on implicit defaults.

Choose limits based on:

- The maximum size of a valid business payload.
- The number of RPCs that can be received concurrently.
- The number of messages that may sit waiting in queues.
- The number of data copies that may occur during parsing, validation, or transformation.
- The heap budget allocated to gRPC and other components.
- Latency and CPU cost when decoding/decompressing payloads.

For example, if an 8 MiB request can produce an additional copy in a DTO and another copy in a queue, the real memory cost is much higher than 8 MiB. Limits must be chosen based on expected concurrent load, not just the size of a single request.

## 6. Message Size Differs from HTTP/2 Frame Size and Flow Control

A gRPC message does not necessarily fit inside a single HTTP/2 DATA frame. Messages have their own gRPC framing and can be split across multiple DATA frames; the transport reassembles the bytes before delivering the message up to the gRPC layer.

| Mechanism | What does it limit? |
| --- | --- |
| **Inbound message size** | Size of a single gRPC message permitted by the receiving endpoint. |
| **HTTP/2 maximum frame size** | Maximum payload size of a single HTTP/2 frame. |
| **HTTP/2 flow-control window** | Amount of DATA allowed in flight on a stream and connection before requiring WINDOW_UPDATE. |
| **Inbound metadata size** | Size of received metadata/headers. |
| **Application quota** | Total bytes, message count, or processing duration permitted by business rules. |

Increasing HTTP/2 frame size does not raise the inbound message limit. Increasing the flow-control window also does not allow a message to exceed **maxInboundMessageSize**. Conversely, a message within the size limit may still have to wait because the flow-control window is insufficient.

Metadata is also separate. Never put file contents, large JSON payloads, or binary data into metadata to bypass message limits; metadata has its own limit and is meant for control information such as tokens, trace IDs, or correlation IDs.

## 7. What Happens When a Message Exceeds the Limit?

When the receiving endpoint detects a message exceeding the limit, gRPC terminates the RPC with an error. The typical status is **RESOURCE_EXHAUSTED** with a description noting that the message exceeded the maximum size.

Key points:

- The message is rejected at the receiving layer; the service method may not be invoked for that message.
- With streaming, earlier messages may already have been processed; the oversized message is not delivered to the business callback as a valid message.
- The client observes the RPC status via the error callback or a blocking stub exception.
- Do not retry the exact same unchanged payload against the same limit; retrying only makes sense if you reduce the size, split into chunks, or change the receive policy.

Do not catch **RESOURCE_EXHAUSTED** and silently ignore it to continue processing a stream as if the message had been received. The application must clearly define whether the RPC terminates or has an application-layer recovery mechanism.

## 8. Checking Size Before Sending

Receiver limits are a mandatory safeguard, but the sender should also check sizes to avoid initiating an RPC guaranteed to be rejected.

With Protobuf Java messages, **getSerializedSize()** returns the serialized size of the message:

~~~java
final int MAX_REQUEST_BYTES = 8 * 1024 * 1024;

UploadRequest request = buildRequest();
int serializedSize = request.getSerializedSize();

if (serializedSize > MAX_REQUEST_BYTES) {
    throw new IllegalArgumentException(
        "Upload request exceeds the configured message limit");
}

stub.upload(request);
~~~

This check is useful on clients controlled by your own application. The server must still configure its own limits and validate requests because external clients can skip client-side checks.

**getSerializedSize()** estimates the Protobuf serialized size, not the total object heap memory. It also does not replace receiver-side limit enforcement or business limits such as the maximum number of elements in a list.

## 9. Large Payloads: Raise the Limit or Chunk?

Raising the limit can be appropriate when large payloads are genuinely required, infrequent, and the memory budget has been accounted for. For large data or continuous transfers, chunking via streaming is usually easier to control.

Example upload contract:

~~~proto
syntax = "proto3";

message UploadChunk {
  string upload_id = 1;
  uint64 sequence = 2;
  int64 offset = 3;
  bytes data = 4;
  bytes checksum = 5;
  bool last = 6;
}

message UploadResult {
  string upload_id = 1;
  int64 bytes_received = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
~~~

Each chunk must still stay below the inbound message limit. In addition, the server needs to specify:

- Maximum chunk size and maximum total upload size.
- Ordering via **sequence** or **offset**.
- How checksums are verified and duplicate/missing chunks are detected.
- Behavior during retries or reconnections.
- Upload expiration and per-user/tenant quotas.
- When a chunk is confirmed as durably persisted.

If very large files need to be transferred, another option is storing the file in object storage and sending only the URI, metadata, and checksum over gRPC. This avoids passing the entire file content through Protobuf messages, though it requires designing access permissions, URL expiration, and content verification.

## 10. Message Limits Alone Are Not Enough Against Overload

A client can send many small messages instead of one large message. Therefore, message-size limits must be paired with other limits:

| Limit | Goal |
| --- | --- |
| **Per-message size** | Prevent a single oversized message. |
| **Per-RPC total bytes** | Prevent a stream from sending unbounded total data. |
| **Message count** | Bound the number of chunks or events in one RPC. |
| **Concurrent RPCs** | Bound the number of simultaneously active streams. |
| **Queue capacity/byte budget** | Bound pending data held on the heap. |
| **Deadline/idle timeout** | Prevent RPCs from holding resources for too long. |
| **Rate limit/quota** | Limit request rate and total usage per client/tenant. |

With compressed payloads, the size on the wire and the decompressed size can differ significantly. Compression reduces network traffic but still consumes CPU and memory during decompression. Test with the transport/runtime in use and ensure you have measures to limit post-decompression data or corresponding resources; do not treat compression as a way to bypass message-size limits.

## 11. Testing Inbound Limits

Test at the integration level over a real channel/server or equivalent test harness. Minimum test matrix:

1. A message smaller than the limit is received and processed.
2. A message right at the limit is verified according to the implementation's boundary semantics.
3. A message larger than the limit is rejected with the appropriate status.
4. The server limit is tested separately against inbound requests.
5. The client limit is tested separately against inbound responses.
6. An oversized streaming chunk terminates the RPC per contract.
7. Many small messages within the per-message limit are still constrained by total quota if they exceed application policy.
8. Compressed and uncompressed payloads are tested on the exact production transport/version.

Example client-side verification logic:

~~~java
try {
    UploadResult result = blockingStub.upload(oversizedRequest);
    fail("Expected the server to reject the oversized request");
} catch (StatusRuntimeException ex) {
    assertEquals(
        Status.Code.RESOURCE_EXHAUSTED,
        ex.getStatus().getCode());
}
~~~

This test snippet assumes the server is configured with a limit smaller than the payload and the request travels over a real transport. For streaming, use an observer/test client and verify the terminal callback; do not check only for a synchronous exception.

## 12. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Configuring only the server and forgetting the client | Large responses are still rejected by the client | Configure inbound limits on both endpoints when needed. |
| Confusing per-message limit with total stream limit | Many small chunks can still transfer excessive total data | Add per-RPC byte quotas and message-count limits. |
| Raising the limit very high just to stop errors | Increases heap exhaustion risk under concurrent RPCs | Budget based on payload size and concurrency. |
| Confusing HTTP/2 frame size with gRPC message size | Tuning the wrong layer leaves errors unresolved | Configure **maxInboundMessageSize** on the receiving endpoint. |
| Putting payloads in metadata | Inflates header size and misuses metadata | Use message fields or streaming payloads. |
| Checking only on the client | Untrusted clients can bypass the check | Always enforce limits on the server. |
| Thinking **getSerializedSize()** is heap size | Underestimates real memory usage | Add object overhead, copies, and queue budgets. |
| Ignoring compression and concurrency | Small wire traffic still consumes massive resources | Test decompression and apply quotas/concurrency limits. |

## 13. Practice Exercises

A document ingestion service has an 8 MiB inbound message limit:

1. Configure the server to accept requests up to 8 MiB using a gRPC Java builder.
2. Configure the client channel to accept responses up to 8 MiB.
3. Use **getSerializedSize()** to check requests before sending.
4. Write integration tests for payloads below and above the threshold; verify **RESOURCE_EXHAUSTED** when exceeded.
5. Design a client-streaming upload with chunks up to 1 MiB and a total per-upload quota.
6. Define how to validate sequence, offset, checksum, retries, and cancellation.
7. Explain why message-size limits do not replace total byte limits, concurrent RPC limits, and deadlines.

**Completion criteria:** accurately configure receiver limits, distinguish per-message from per-stream quotas, handle threshold errors, and choose an appropriate chunking strategy for large payloads.

## 14. Key Takeaways

- **maxInboundMessageSize(int)** limits the size of each received message at a gRPC endpoint.
- The server limit protects inbound requests; the client/channel limit protects inbound responses.
- Message limits differ from HTTP/2 frame size, flow-control windows, metadata size, and total stream quotas.
- Oversized messages typically terminate the RPC with **RESOURCE_EXHAUSTED**; the service method may never receive that message.
- Use **getSerializedSize()** to check before sending, while still enforcing limits on the receiver.
- For large payloads, consider chunked client-streaming or object storage; each chunk must still stay under the limit.
- Combine per-message limits with total bytes, message counts, concurrency, queue budgets, rate limits, and deadlines.

Properly calculated inbound message size limits enable Spring gRPC services to reject oversized payloads early, protect memory under concurrent RPCs, and maintain scalability across both unary and streaming APIs.
