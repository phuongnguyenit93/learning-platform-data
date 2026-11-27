# max outbound message size

## Learning Objectives

After this lesson, you can:

- Explain how max outbound message size limits the size of a gRPC message that an endpoint sends.
- Distinguish outbound limits on the sender from max inbound message size on the receiver.
- Configure send limits for client calls using the grpc-java API appropriate for your version.
- Identify receive limits for client responses and server requests.
- Check protobuf size before sending or emitting responses.
- Distinguish message size from HTTP/2 frames, compression, and total streaming data.
- Design chunking, quotas, and boundary tests to avoid sending oversized messages.

## 1. What is max outbound message size?

In **SPRING_GRPC**, an RPC sends requests or responses as gRPC messages serialized from Protocol Buffers. A message can contain bytes, strings, nested messages, or collections. If an endpoint constructs an overly large message, serializing, buffering, and transmitting the data can increase memory usage, CPU, latency, and network pressure.

**max outbound message size** is the maximum size limit of a single message that a sender is permitted to send on an RPC. It controls the outgoing data direction from the current endpoint. This concept needs to be understood alongside the receive limit on the other end:

- **Outbound limit:** limits the message created and sent by the sender.
- **Inbound limit:** limits the message that the receiver accepts receiving.

The two limits are related but not identical. Configuring outbound on the client does not automatically increase the server's receive capacity; configuring inbound on the client does not restrict requests the client sends out.

For example, a client sends a large request to a server. The client is the sender of the request, and the server is the receiver. When the server returns a response, the server becomes the sender and the client is the receiver. Each direction can have different limits.

## 2. Understanding limits by request and response direction

| Message | Sender | Receiver | Limits to consider |
| --- | --- | --- | --- |
| Unary request | gRPC client | gRPC server | Client outbound and server inbound |
| Unary response | gRPC server | gRPC client | Server-side send behavior and client inbound |
| Client-streaming request | gRPC client | gRPC server | Client per-message outbound and server per-message inbound |
| Server-streaming response | gRPC server | gRPC client | Server-side send behavior and client per-message inbound |
| Bidirectional request | gRPC client | gRPC server | Client outbound and server inbound |
| Bidirectional response | gRPC server | gRPC client | Server-side send behavior and client inbound |

In grpc-java, receive limits are typically configured on the endpoint receiving data:

- Server inbound limit bounds requests that the server receives from clients.
- Client inbound limit bounds responses that the client receives from servers.

Some versions of grpc-java provide a per-call outbound limit via CallOptions and generated stubs, such as **withMaxOutboundMessageSize(int)**. The exact API must match the grpc-java version your project uses. If your version does not provide a per-call outbound option, you may need to enforce limits in the application before sending and rely on the receive limit configured on the receiver.

Do not assume that every server builder or Spring gRPC starter has a property named max-outbound-message-size. Receive configuration and send configuration may live in different APIs. Check the API of the transport/starter in use and verify with integration tests.

## 3. Configuring outbound limits for client calls

When your grpc-java version provides an outbound option API on generated stubs, you can set a limit for messages the client sends in a call:

~~~java
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

ManagedChannel channel = NettyChannelBuilder
        .forAddress("orders.internal", 9090)
        .maxInboundMessageSize(4 * 1024 * 1024)
        .build();

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel)
                .withMaxOutboundMessageSize(2 * 1024 * 1024);
~~~

In the example:

- maxInboundMessageSize on the channel limits responses the client receives from the server.
- withMaxOutboundMessageSize on the stub limits messages the client sends in the call, if the API exists in the version in use.
- The two numbers are independent because requests and responses can have different sizes.

Do not confuse channel inbound configuration with outbound requests. If a request is larger than the server's receive limit, the server can still reject it even if the client outbound option permits sending larger messages. Therefore, the contract must align between the client's send limit and the server's receive limit.

If the application creates stubs via a Spring bean or factory, set CallOptions where the stub is created to match each type of RPC. For APIs requiring multiple limit tiers, you can create separate factories for uploads, batches, and regular requests instead of using one large threshold for every method.

## 4. Server sends response: client inbound limit is the receiving barrier

When the server sends a response, the client is the receiver. The client can configure a receive limit on the channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress("orders.internal", 9090)
        .maxInboundMessageSize(8 * 1024 * 1024)
        .build();
~~~

This limit protects the client from oversized responses. It is not an outbound setting on the server.

On the server side, the application can check the serialized response size before calling onNext:

~~~java
private void sendResponse(
        GetReportResponse response,
        StreamObserver<GetReportResponse> observer) {

    int serializedBytes = response.getSerializedSize();

    if (serializedBytes > MAX_REPORT_BYTES) {
        observer.onError(
                Status.RESOURCE_EXHAUSTED
                        .withDescription("Response exceeds the message-size contract")
                        .asRuntimeException());
        return;
    }

    observer.onNext(response);
    observer.onCompleted();
}
~~~

This is an application-boundary check, useful for returning an intentional error before sending. It does not replace the client's receive limit: another client could ignore application conventions or call using a raw gRPC client. The receiver must still protect itself.

If the server needs to send many large responses, consider server-streaming with smaller individual responses instead of a single response containing the entire result. The client still needs an appropriate inbound limit for each response message.

## 5. Checking protobuf size before sending

Generated protobuf messages provide getSerializedSize() to retrieve the serialized payload size in bytes:

~~~java
int serializedBytes = request.getSerializedSize();

if (serializedBytes > MAX_REQUEST_BYTES) {
    throw Status.RESOURCE_EXHAUSTED
            .withDescription("Request exceeds the message-size contract")
            .asRuntimeException();
}

blockingStub.submitOrder(request);
~~~

This check helps the application reject early before calling the transport and provides an error message aligned with the API contract. However, this is not the sole security boundary. A caller can use another client and bypass validation. The server inbound limit must still be configured on the server.

For responses, the server can also check getSerializedSize() before calling onNext. For client-streaming, check each message before sending; for server-streaming, check each response before emitting.

The serialized protobuf size does not necessarily equal the total bytes on the wire. gRPC has framing, compression, and HTTP/2 transport. Treat getSerializedSize() as a useful measurement of the protobuf payload for contracts and testing, not a measurement of HTTP/2 frames.

## 6. Outbound limit, inbound limit, and HTTP/2 framing

A gRPC message is framed inside a gRPC message envelope and transmitted over HTTP/2 DATA frames. One message can span multiple frames; one frame does not equal one protobuf message.

The limits have distinct meanings:

- **Outbound message limit:** the sender bounds the message it creates to send.
- **Inbound message limit:** the receiver bounds the message it accepts.
- **HTTP/2 frame size:** transport-layer limit of a frame, not the protobuf message size.
- **Metadata limit:** limit on metadata/headers, separate from the message body.
- **Stream quota:** limit on total bytes or message count within a long-lived RPC.

Do not use HTTP/2 frame size to infer max outbound message size. Do not assume a 5 MiB message will fit in a single 5 MiB frame; the transport can split a message across multiple frames.

When client and server have incompatible configurations, a message may be permitted by the sender yet rejected by the receiver. Set the outbound limit on the sender equal to or lower than the receiver's published receive limit so errors are caught early, while keeping the receiver limit as the final barrier.

## 7. Compression and message size

Compression reduces the number of bytes transmitted over the network, but that does not mean large messages become free. The receiver needs to decompress and parse the content; the decompressed payload can be much larger than the data on the wire.

When evaluating outbound limits:

- Check the serialized protobuf size created by the sender.
- Determine at which stage grpc-java applies outbound limits for your version/transport.
- Do not rely on compressed size as a substitute for payload limits.
- On the receiver, configure inbound limits and monitor memory after decompression.
- Test compressed payloads with high expansion ratios in controlled tests.

Compression can reduce bandwidth, yet it still requires CPU for compression/decompression and memory to hold protobuf objects. Do not raise outbound limits simply because gzip is enabled.

## 8. Streaming: per-message limits do not bound the total stream

For streaming RPCs, outbound message limits are typically applied per outgoing message. A stream can send thousands of messages of valid size whose total data is still very large.

Multiple limits must be combined:

| Limit | Purpose |
| --- | --- |
| **Max outbound message size** | Maximum size of each message the sender sends |
| **Receiver max inbound message size** | Maximum size of each message the receiver accepts |
| **Maximum messages per stream** | Maximum number of messages in one RPC |
| **Total bytes per stream** | Total data transmitted within the stream |
| **Maximum stream lifetime** | How long the stream is allowed to stay open |
| **Concurrent stream limit** | Concurrent streams per server/tenant |
| **Rate limit** | Rate of sending messages or bytes |
| **Flow control/backpressure** | Throttling the producer based on consumer capacity |

The total byte counter should use a sufficiently large numeric type like long and update safely when multiple callbacks may run concurrently. Per-tenant quotas must be updated atomically so multiple streams do not exceed the limit together.

When a stream exceeds its total quota, the service can terminate with RESOURCE_EXHAUSTED according to the contract. Do not use max outbound message size as a substitute for total quotas or rate limits.

## 9. Large data should be chunked

If a response or request needs to contain a large file, a large batch, or a large dataset, consider chunked streaming instead of sending a single message.

Example chunked upload/download contract:

~~~proto
message DataChunk {
  string transfer_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

message TransferResult {
  string transfer_id = 1;
  int64 total_bytes = 2;
}

service TransferService {
  rpc Upload(stream DataChunk) returns (TransferResult);
  rpc Download(DownloadRequest) returns (stream DataChunk);
}
~~~

Each chunk has a clearly bounded size, lower than the outbound and inbound limits of both sides. In addition, you need to:

1. Limit total bytes and chunk count.
2. Check sequence to detect missing or duplicate chunks.
3. Verify access permissions for the transfer ID and tenant.
4. Use a checksum to verify content after reassembly.
5. Support retry/resume using transfer ID and sequence.
6. Clean up temporary data on cancellation or expiration.
7. Avoid assembling all data into one large byte array on the heap if you can stream directly to storage.

Chunking improves memory usage, progress tracking, and resumability, but it does not automatically bound total data. Separate quotas and deadlines are needed.

## 10. Choosing outbound thresholds based on contract and resources

There is no single threshold suitable for every method. An order detail response may only need a few KiB; a report export may need several MiB; file data should use chunks.

When choosing an outbound limit, consider:

- Largest valid payload size according to the API contract.
- Receive limit of the opposite endpoint.
- Heap and object overhead after serialization/parsing.
- Number of concurrent RPCs and open streams.
- Compression, CPU, and network bandwidth.
- Deadline and serialization time.
- Compatibility with older clients.
- Per-tenant quotas and deployment limits.

Do not calculate concurrency by simply dividing heap by message size. Protobuf objects, byte arrays, buffers, serialization copies, domain objects, and responses can make actual memory usage larger than the payload. Measure with load tests using near-threshold messages and production-like concurrent RPC counts.

If changing limits, clearly publish the new limit to clients. Raising the server-side receive limit without considering memory or lowering client-side outbound limits can cause some older clients to fail.

## 11. Status and error handling when messages are too large

If the sender's outbound option rejects an over-threshold message, or the receiver's inbound limit rejects a message, the RPC usually terminates with RESOURCE_EXHAUSTED. Exact detection timing and description content may depend on the grpc-java version and transport.

Distinguish these scenarios:

| Cause | Typical status/behavior | Handling approach |
| --- | --- | --- |
| Sender outbound limit exceeded | Usually RESOURCE_EXHAUSTED on the call | Shrink message or split into chunks |
| Receiver inbound limit exceeded | Usually RESOURCE_EXHAUSTED on receiver | Respect receive contract or adjust in a controlled manner |
| Field violates API rules | INVALID_ARGUMENT or contract error | Fix input/schema |
| Total stream exceeds quota | RESOURCE_EXHAUSTED | Reduce total data or request appropriate quota |
| Caller lacks permission to send data | PERMISSION_DENIED | Follow authorization workflow |
| Deadline expires during serialization/transmission | DEADLINE_EXCEEDED | Optimize payload or timeout per contract |

Do not parse free-form status descriptions to drive client logic; use Status.Code and stable reason codes if the API provides them. Do not retry the exact same payload that exceeded the limit because retrying does not shrink the payload. For mutations or uploads, use idempotency/sequence to handle connection drops after part of the data has already been received.

## 12. Observing outbound message size

Track sent message sizes by method and RPC type:

- Serialized size p50/p95/p99 and ratio near the threshold.
- Number of calls ending with RESOURCE_EXHAUSTED.
- Message count and total bytes per stream.
- Serialization, compression, and transmission time.
- Heap allocation, GC pauses, and CPU.
- Concurrent stream count and stream duration.
- Number of client upload retries/resumes.

Do not log full payloads or sensitive bytes. Log only method, serialized size, status, trace ID, and policy-sanitized tenant identifier. Avoid using high-cardinality request IDs or tenant IDs as metric labels.

If the sender frequently hits the threshold, review the contract and schema before raising the limit. A response containing tens of thousands of records should probably be paginated or moved to streaming instead of allowing larger messages.

## 13. Testing outbound and receiver boundaries

Tests must check both sender and receiver because the two limits protect different sides.

Suppose the contract sets outbound max to 1 MiB and receiver inbound max to 1 MiB:

| Scenario | Expected result |
| --- | --- |
| Client sends request smaller than limit | Server receives and processes |
| Client creates request larger than outbound option | Client call is rejected per grpc-java version behavior |
| Client sends request allowed by outbound option but larger than server inbound | Server rejects receipt |
| Server returns response smaller than client inbound limit | Client receives response |
| Server returns response larger than client inbound limit | Client rejects receipt |
| Many small messages exceed total stream quota | Application terminates stream per quota |
| Chunks are within limit but total transfer exceeds quota | Transfer is rejected and cleaned up |
| Compression enabled | Boundaries are still enforced per runtime semantics |

Use generated protobuf messages and getSerializedSize() to construct payloads below, near, and above the threshold. The length of a bytes field does not equal the serialized size of the entire message because protobuf also includes tags and length prefixes.

Example of testing payload size:

~~~java
DataRequest request = DataRequest.newBuilder()
        .setPayload(ByteString.copyFrom(payload))
        .build();

int serializedBytes = request.getSerializedSize();
assertTrue(serializedBytes > 0);
~~~

Do not test only application prechecks. Use grpc-java in-process or transport integration tests to verify that outbound options and receiver inbound limits are enforced by the runtime. With Spring gRPC, start the actual channel/server configuration in tests to verify that customizers/beans set the receive limits in the right direction.

Key assertions:

1. Sender does not emit messages exceeding the configured outbound limit.
2. Receiver rejects messages exceeding the inbound limit.
3. Large server responses are blocked by the client receive limit.
4. Service handler does not process messages rejected by the transport.
5. Total stream quota operates independently of per-message limits.
6. Compression does not bypass resource guards.
7. Status codes are checked without relying on descriptions.

## 14. Common pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Confusing outbound with inbound | Configuring the wrong data direction | Identify sender and receiver for each RPC |
| Thinking channel inbound limit bounds outgoing requests | Requests can still be larger than server can receive | Configure sender outbound if API supports it and server inbound |
| Assuming server builder always has an outbound property | Using non-existent property/API in transport | Check API version; use receiver limits and application guards |
| Only checking getSerializedSize on the client | Raw clients bypass validation | Enforce at the transport receiver |
| Only limiting individual messages in a stream | Total stream can still be huge | Add total bytes/messages quota |
| Using compression to allow larger messages | Heap/CPU after decompression increases | Limit payloads and monitor decompression |
| Sending one huge response | Poor memory, latency, and retry behavior | Pagination or chunked streaming |
| Retrying over-limit payloads | Repeating errors that cannot self-resolve | Reduce payload or change contract |
| Testing only stubs without a real server | Missing receive limit/wiring bugs | Integration test through gRPC runtime and Spring configuration |

## 15. Hands-on exercises and self-check questions

### Hands-on exercises

1. Set a client outbound limit using the API of your current grpc-java version if generated stubs support it.
2. Configure a server inbound limit to protect incoming client requests.
3. Configure a client inbound limit to protect incoming server responses.
4. Create protobuf requests/responses with a bytes field and measure getSerializedSize().
5. Write tests with payloads below, near, and above the outbound option; repeat with receiver inbound limits.
6. Build chunked server-streaming or client-streaming, limiting each chunk and total transfer.
7. Add stream quotas, deadlines, cancellation, and cleanup when limits are exceeded.
8. Write a Spring integration test verifying the channel/server builder is configured in the right direction.

### Self-check questions

**1. What does max outbound message size limit?**  
The maximum size of a single gRPC message that a sender is allowed to send in a call.

**2. Does an outbound limit replace the receiver's inbound limit?**  
No. The sender limit controls outgoing messages; the receiver inbound limit is the final barrier upon receipt.

**3. When the client sends a request, who is the receiver?**  
The server. The server inbound message limit controls requests the server accepts.

**4. When the server sends a response, who is the receiver?**  
The client. The client inbound message limit controls responses the client accepts.

**5. Does getSerializedSize() measure HTTP/2 frames?**  
No. It measures the serialized protobuf payload; gRPC framing and HTTP/2 transport have their own structures.

**6. Does a per-message limit bound total streaming?**  
No. Total bytes, message count, lifetime, concurrency, and rate quotas are also needed.

**7. What status commonly occurs when outbound/inbound message limits are exceeded?**  
Usually RESOURCE_EXHAUSTED; exact behavior depends on the grpc-java version and transport.

**8. Why are integration tests through the runtime needed?**  
To verify that outbound options, receiver inbound limits, and Spring wiring are actually applied, rather than only testing application prechecks.

## Summary

max outbound message size limits the size of each gRPC message sent by a sender. You must identify the request/response direction accurately: when the client sends a request to the server, the server inbound limit protects the receiving side; when the server sends a response to the client, the client inbound limit protects the receiving side. A grpc-java version may provide per-call outbound options on CallOptions/generated stubs; verify the actual API rather than assuming every server builder has an outbound property. Combine send limits, receive limits, serialized payload checks, chunking, and total stream quotas to control memory, latency, and resource exhaustion. Integration tests must verify both sender and receiver under real Spring configuration.
