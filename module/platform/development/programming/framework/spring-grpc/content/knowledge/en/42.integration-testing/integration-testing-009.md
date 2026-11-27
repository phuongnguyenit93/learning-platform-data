# Testing Message Size Limits

## Learning Objectives

After this lesson, you will be able to:

- Explain gRPC message size limits and distinguish them from metadata limits.
- Identify which endpoint enforces the limit for each request/response direction.
- Configure maxInboundMessageSize for the gRPC server and client.
- Use Protobuf getSerializedSize() to construct byte-accurate boundary test payloads.
- Test below-limit, at-limit, and over-limit messages over TCP.
- Test limits for both unary and streaming RPCs.
- Handle RESOURCE_EXHAUSTED status, memory pressure, and total stream resource limits.

## 1. Why Limit Message Size?

gRPC transmits Protobuf messages over HTTP/2. An oversized request or response can consume substantial memory while being received, decoded, parsed into objects, and held in processing queues. When many large RPCs arrive concurrently, the server can rapidly grow its heap, trigger GC pressure, or exhaust resources.

maxInboundMessageSize caps the size of a single message accepted by an endpoint. This limit applies on the receiving side: the server checks requests from clients; the client checks responses from servers. It protects the transport from a single oversized message, though it does not automatically cap total bytes across an entire stream or total queued work in the application.

In **SPRING_GRPC**, verify limits with integration tests through generated stubs against a running server. Calling the service method directly bypasses transport and fails to test rejection of oversized messages.

## 2. Message Size Differs from Payload Size and Metadata Size

A Protobuf message is serialized into a byte stream according to the wire format. Serialized size includes field tags, length prefixes, field values, and encoding overhead. Therefore, the length of a bytes field or UTF-8 string does not necessarily equal getSerializedSize().

Key concepts to distinguish:

| Limit | What is bounded | Common gRPC Java configuration |
| --- | --- | --- |
| Inbound message size | A single incoming Protobuf message | maxInboundMessageSize(...) |
| Inbound metadata size | Call metadata/headers | maxInboundMetadataSize(...) |
| Application queue/buffer | Total data held by the application | Bounded queues, byte budgets, admission control |
| Stream/business quota | Total messages or total bytes in a session | Business logic and per-call state |

Do not use maxInboundMetadataSize to limit request bodies. Conversely, raising the message limit does not allow arbitrarily large metadata. The two limits protect different regions of the call.

## 3. Limits Are Enforced on the Receiving Side

Each transmission direction has its own receiving endpoint:

| RPC direction | Receiving endpoint | Limit to check |
| --- | --- | --- |
| Client sends request to server | gRPC server | Server maxInboundMessageSize |
| Server sends response to client | gRPC client channel | Client maxInboundMessageSize |
| Client-streaming request | gRPC server, per request message | Server limit |
| Server-streaming response | gRPC client, per response message | Client limit |
| Bidirectional stream | Both server and client | Configure limits on both sides |

The server inbound limit does not cap the server's outbound responses. If the server sends an oversized response, the client's inbound limit decides whether the client accepts that message.

For streams, the limit typically applies per message, not to the cumulative bytes of the entire session. A stream of many small messages can still accumulate large amounts of data; the application must enforce additional stream, queue, and time quotas.

## 4. Configuring Server Inbound Message Size

With a self-managed gRPC Java Netty server, configure the limit before building:

~~~java
private static final int SERVER_MAX_MESSAGE_BYTES = 1024 * 1024;

Server server = NettyServerBuilder.forPort(0)
    .maxInboundMessageSize(SERVER_MAX_MESSAGE_BYTES)
    .addService(inventoryService)
    .build()
    .start();
~~~

The value in the example is 1 MiB for illustration; production must choose limits based on valid payload sizes, memory budgets, and expected concurrency. Never raise the limit just to make an oversized test pass.

In Spring gRPC, the server may be auto-configured by the starter. Set the exact property or customizer supported by your starter and version. Property names are not uniform across all starters; do not copy an unverified configuration key. Integration tests should obtain the port from the Spring-managed server rather than spinning up a second server solely to change limits.

## 5. Configuring Client Inbound Message Size

The client channel controls the size of responses it accepts:

~~~java
private static final int CLIENT_MAX_MESSAGE_BYTES = 1024 * 1024;

ManagedChannel channel = NettyChannelBuilder
    .forAddress("127.0.0.1", grpcServer.port())
    .maxInboundMessageSize(CLIENT_MAX_MESSAGE_BYTES)
    .usePlaintext()
    .build();
~~~

If using a different transport builder, check the corresponding API for your gRPC Java version. Configure the limit explicitly on the test client so results do not depend on dependency defaults.

Do not confuse the client inbound limit with a limit on outgoing client requests. When the client sends a large request, the server is the receiving endpoint, and the server limit determines whether the request is accepted.

## 6. Measuring Exact Protobuf Size

Use getSerializedSize() on the generated message to determine its wire-format size:

~~~java
UploadRequest request = UploadRequest.newBuilder()
    .setUploadId("batch-17")
    .setPayload(ByteString.copyFrom(payload))
    .build();

int serializedBytes = request.getSerializedSize();
~~~

payload.length is only the size of the bytes field itself. The message also includes field tags, length prefixes, and other fields. Boundary tests should compare getSerializedSize() against the configured limit.

There is no need to call toByteArray() just to measure size because that allocates an extra byte array copy. For large messages, that temporary copy can increase memory pressure inside the test itself.

## 7. Designing Near-Boundary Test Messages

A test suite should include at least three cases:

- Message smaller than the limit: accepted.
- Message whose serialized size equals the limit: accepted if the transport/API specifies an inclusive limit.
- Message at least one byte larger than the limit: rejected.

Example helper to build requests and verify sizes before sending:

~~~java
UploadRequest requestWithPayload(byte[] payload) {
    return UploadRequest.newBuilder()
        .setUploadId("boundary-test")
        .setPayload(ByteString.copyFrom(payload))
        .build();
}

assertTrue(requestWithPayload(payloadBelow)
    .getSerializedSize() < SERVER_MAX_MESSAGE_BYTES);

assertEquals(SERVER_MAX_MESSAGE_BYTES,
    requestAtLimit.getSerializedSize());

assertTrue(requestWithPayload(payloadAbove)
    .getSerializedSize() > SERVER_MAX_MESSAGE_BYTES);
~~~

Do not assume payload length equals message size. If you need an exact N-byte message, adjust the payload size and re-check getSerializedSize() until hitting the threshold. Also test multiple field types such as strings, bytes, and repeated fields because varint/length prefixes can step message size non-linearly.

## 8. Testing Oversized Requests on the Server

When a client sends a request larger than the server inbound limit, server transport rejects the message before the service handler runs. The client typically receives RESOURCE_EXHAUSTED.

~~~java
@Test
void rejectsRequestLargerThanServerLimit() {
    UploadRequest oversized = requestWithPayload(payloadAboveLimit);
    assertTrue(oversized.getSerializedSize() > SERVER_MAX_MESSAGE_BYTES);

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.uploadUnary(oversized));

    assertEquals(
        Status.Code.RESOURCE_EXHAUSTED,
        Status.fromThrowable(error).getCode());
    assertEquals(0, uploadService.invocationCount());
}
~~~

A counter or spy confirming the handler was never called is critical proof: the request was rejected at the transport layer before business logic. Do not assert only that the client threw an exception, as the error might have come from service-level validation instead of the size limit.

Exact status and error descriptions can vary by transport/version; assert the status code and handler behavior rather than relying on the full error string.

## 9. Testing Oversized Responses on the Client

To test the client inbound limit, have the server return a response larger than the client channel's limit. The server may have already executed the business method and produced the response; client transport is the side rejecting the message.

~~~java
ManagedChannel smallLimitChannel = NettyChannelBuilder
    .forAddress("127.0.0.1", grpcServer.port())
    .maxInboundMessageSize(CLIENT_MAX_MESSAGE_BYTES)
    .usePlaintext()
    .build();

InventoryGrpc.InventoryBlockingStub smallLimitStub =
    InventoryGrpc.newBlockingStub(smallLimitChannel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);

StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> smallLimitStub.download(
        DownloadRequest.getDefaultInstance()));

assertEquals(
    Status.Code.RESOURCE_EXHAUSTED,
    Status.fromThrowable(error).getCode());
~~~

Close smallLimitChannel in a finally block or teardown. This test proves the client rejects oversized responses; it does not prove the server did not execute the business logic. For operations with side effects, consider idempotency and avoid blind retries after response-receive failures.

## 10. Testing Streaming Message Sizes

Inbound message limits apply to each individual message in a stream:

- Client-streaming: server checks each request message.
- Server-streaming: client checks each response message.
- Bidirectional: each side checks messages received from the peer.

A client-streaming test can send a small message first, followed by an oversized message. The stream must terminate with an error; the server must not continue processing subsequent messages once transport has closed the call.

For server-streaming, tests should record any valid responses received before the oversized message (if any), then assert the terminal error. Clients must not treat the stream as normally completed just because a few initial messages arrived.

Per-message limits do not cap the total number of messages. If each message is 100 KiB and the stream sends thousands of messages, total data can still grow very large even though every individual message is under the limit.

## 11. Compression and Decompressed Size

Compression reduces bytes sent over the network but does not make the decompressed message smaller. When evaluating limits, consider the size of the message the receiver must decode and parse, not only compressed wire bytes.

If the application enables gzip or another compressor, add tests with compression enabled and highly compressible payloads. Verify that the receiver still enforces appropriate message limits and does not accept decompressed payloads exceeding the design budget.

Do not write tests based on HTTP/2 frame sizes or compressed byte counts as a substitute for getSerializedSize(). Protobuf message size, compression, and HTTP/2 framing are distinct layers.

## 12. Message Size Does Not Replace a Memory Budget

Serialized size does not equal heap footprint. When receiving a message, the runtime may hold buffers, decoded representations, and the Protobuf object graph; the application may also copy data into queues or domain objects.

Therefore:

- Choose message limits based on heap budget and concurrent RPC count.
- Use bounded queues and byte budgets for pending work.
- Limit total bytes or total elements within a stream.
- Enforce deadlines and cancellation to free long-running calls.
- Avoid copying large messages multiple times; use streaming/chunking when appropriate.
- Emit metrics on message sizes, rejection counts, and queue depth without logging sensitive payloads.

If the business requirement involves transferring large files or blobs, prefer splitting them into chunks with sequences/offsets and bounding each chunk. The server should enforce total upload size, chunk count, user quota, and completion timeout.

## 13. Distinguishing Message Limits from Metadata Limits

Metadata is sent in HTTP/2 headers/trailers and has its own limit. For example, authorization tokens, trace IDs, or tenant IDs belong to metadata; they are not part of the Protobuf message body.

If metadata exceeds its limit, the call may be rejected before the method handler runs, but that is not proof that maxInboundMessageSize works. Likewise, an oversized request body should not be worked around by raising maxInboundMetadataSize.

Test the two limits independently if the application needs to verify both. For auth metadata, keep tokens compact and never use a large message limit to mask oversized metadata/headers.

## 14. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Configuring only the server limit | Client may still reject large responses per its own limit | Configure inbound limits on both receivers. |
| Thinking server inbound limit caps outbound responses | Response tests do not reflect client config | Use client maxInboundMessageSize for responses. |
| Comparing payload length to message limit | Off-by-several-bytes due to tags/length prefixes/other fields | Use getSerializedSize(). |
| Testing only huge messages | Misses off-by-one boundary bugs | Test below-limit, at-limit, and over-limit. |
| Asserting only that an exception occurred | Unclear whether transport or business handler rejected it | Assert status code and invocation counter. |
| Treating per-message stream limit as total stream bytes | Many small messages can accumulate excessive data | Add total stream quotas and byte budgets. |
| Ignoring compression | Fails to check decompressed payload size | Test with compressors and highly compressible payloads. |
| Confusing message limit with metadata limit | Misconfigured protection layer | Test maxInboundMetadataSize separately. |
| Raising limits just to pass tests | Increases memory pressure and DoS risk | Pick limits from API contracts and resource budgets. |

## 15. Message Size Testing Matrix

An integration test suite should cover:

1. Unary request smaller than server limit: succeeds.
2. Unary request equal to server limit: confirms boundary behavior.
3. Unary request larger than server limit: RESOURCE_EXHAUSTED, handler does not run.
4. Unary response larger than client limit: client receives size error, confirming server method executed.
5. Client-streaming with one over-limit request message: stream terminates with error.
6. Server-streaming with one over-limit response message: client does not observe normal stream completion.
7. Bidirectional stream checks limits independently in both directions.
8. Compression-enabled test checks post-decompression size enforcement.
9. Oversized metadata tested separately against inbound metadata limits.
10. Queue/stream quotas tested separately to bound cumulative data.

Each test must set deadlines, close channels, and use a stable server lifecycle. Do not share mutable counters across parallel tests without synchronization or explicit resets.

## 16. Hands-On Exercise

Create an integration test for an upload/download service:

1. Configure server inbound message limit and client inbound message limit with explicit values.
2. Construct Protobuf requests with bytes payloads and measure with getSerializedSize().
3. Send requests below the limit, at the limit, and above the limit; check responses/statuses.
4. Use an invocation counter to verify over-limit requests never reach the service handler.
5. Produce a response larger than the client limit and confirm the client rejects it.
6. Repeat with client-streaming and server-streaming to verify per-message enforcement.
7. Enable compression and verify limits when the receiver decodes messages.
8. Enforce total upload/queue limits separately from per-message limits.
9. Close the channel and let Spring manage server shutdown.

**Completion criteria:** tests identify the exact receiver enforcing each limit, measure serialized size accurately, separate message limits from metadata limits, verify transport status/rejection, and bound total stream resources.

## 17. Takeaways

- maxInboundMessageSize bounds a single message at the receiving endpoint; the server checks requests and the client checks responses.
- Client and server require independent inbound limits per data direction.
- Use Protobuf getSerializedSize() to measure wire-format bytes; payload length is not the full message size.
- Test below, at, and above the limit; verify both status codes and whether the handler ran.
- For streaming, limits apply per message; enforce separate quotas for total stream size and queues.
- Compression does not eliminate the need to bound decompressed messages.
- Metadata has its own separate limit, such as maxInboundMetadataSize.
- Message size does not equal heap footprint; also design byte budgets, backpressure, deadlines, and cancellation.
- Choose limits according to API contracts and resource budgets, never raising them arbitrarily to pass tests.

Testing message size limits ensures Spring gRPC services reject oversized payloads at the right endpoint, protect memory, and maintain consistent unary/streaming behavior under large-payload workloads.
