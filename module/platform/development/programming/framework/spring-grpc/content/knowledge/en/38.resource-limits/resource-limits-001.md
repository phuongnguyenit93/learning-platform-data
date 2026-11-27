# max inbound message size

## Learning Objectives

After this lesson, you can:

- Explain how max inbound message size limits the size of each incoming gRPC message.
- Distinguish server-side limits from client-side limits and configure the right data direction.
- Set byte limits in the grpc-java builder and integrate them with a Spring-managed server.
- Distinguish protobuf payload, gRPC message, HTTP/2 frame, and total stream data.
- Evaluate the impact of compression, large messages, and streaming types.
- Design chunking, quotas, and validation for large data.
- Test messages below, equal to, and above the threshold to verify transport behavior.

## 1. What is max inbound message size?

In **SPRING_GRPC**, an RPC transmits data as gRPC messages serialized from protobuf. A message can contain strings, bytes, nested messages, or collections. If the server receives an overly large message, parsing and holding the data in memory can increase heap usage, garbage collection, and processing time; many concurrent large requests can even cause resource exhaustion.

**max inbound message size** is the maximum size limit of a single message that an endpoint accepts receiving. This is a limit at the gRPC runtime layer, checked when the message is deframed/read before the service handler processes its contents. It creates an early barrier to reject messages exceeding the threshold.

Two directions must be distinguished:

- **Server inbound limit:** limits the message the client sends to the server. This is typically the critical limit for API requests.
- **Client inbound limit:** limits the message the server sends back to the client. It protects the client application from overly large responses.

Configuring a limit on one side does not automatically configure the other side. If the client can send an 8 MiB request but the server only accepts 2 MiB, the client needs to know this contract to avoid sending data that is guaranteed to be rejected. If the server returns large responses, the client also needs an appropriate inbound limit.

## 2. Configuring limits on the server and client

In grpc-java, the builder provides the maxInboundMessageSize(int) method with the unit in **bytes**. Example of setting a server limit at 8 MiB:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;

public final class GrpcServerFactory {

    private static final int MAX_INBOUND_BYTES = 8 * 1024 * 1024;

    public Server createServer(int port) {
        return NettyServerBuilder.forPort(port)
                .maxInboundMessageSize(MAX_INBOUND_BYTES)
                .build();
    }
}
~~~

The 8 MiB figure is an example. Choose the threshold based on the largest valid request size, concurrent request count, heap/container limits, and data size after decompression. Do not increase the limit just to make an abnormal request succeed.

On the client, configure the limit for responses received from the server:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

public final class GrpcChannelFactory {

    private static final int MAX_RESPONSE_BYTES = 12 * 1024 * 1024;

    public ManagedChannel createChannel(String host, int port) {
        return NettyChannelBuilder.forAddress(host, port)
                .maxInboundMessageSize(MAX_RESPONSE_BYTES)
                .build();
    }
}
~~~

Here, MAX_RESPONSE_BYTES applies to messages going from the server back to the client. It does not make the server accept larger requests.

With other transports or builders, the specific API may reside on the corresponding builder. Configure the builder that actually creates the server/channel. In a Spring gRPC application, the server is usually managed by a starter; apply the limit through the server builder customizer/configurer extension point supported by your starter version. Property names or hooks may differ across starters and versions, so do not copy a property that is not published by your project's version. Verify the configuration with an integration test against an actual server.

Default values may depend on the grpc-java version and transport. Explicitly set your application's limits rather than treating library defaults as a stable contract.

## 3. The limit applies to a gRPC message, not an HTTP/2 frame

A gRPC message is transmitted inside HTTP/2 DATA frames. One message can be split across multiple frames; HTTP/2 frame boundaries are not protobuf message boundaries.

Therefore:

- maxInboundMessageSize limits a single gRPC message received/decoded according to the runtime's mechanism.
- It is not a limit on the size of a single HTTP/2 frame.
- It is not the total byte count of the entire RPC or stream.
- A stream can contain many messages, each below the threshold, while the total data is still very large.
- Metadata/headers are a separate part of the protocol; do not use the message-size limit as a substitute for metadata limits or header count limits.

For example, a client-streaming RPC sends 10,000 messages of 256 KiB each. Each message can be below a 1 MiB limit, yet the total stream data is approximately 2.5 GiB. Therefore, a single-message limit does not replace a total stream quota, message count limit, rate limit, or deadline.

### 3.1. Protobuf payload and message size

For a generated protobuf message, getSerializedSize() returns the size of the serialized protobuf payload in bytes:

~~~java
int payloadBytes = request.getSerializedSize();

if (payloadBytes > MAX_INBOUND_BYTES) {
    throw new IllegalArgumentException("Request is too large");
}
~~~

This is a useful way for the client to check before sending or for the application to record metrics. However, a client-side check is not a security barrier: a caller can bypass the official client and send a raw gRPC request. The server must still configure transport limits.

Do not equate getSerializedSize() with the HTTP/2 size on the wire. Framing, compression, and transport layers have their own overhead. Use the same byte unit and test on the actual grpc-java transport to confirm the real boundary.

## 4. Compression does not eliminate the need for limits

gRPC can compress messages to reduce data transmitted over the network. A small compressed payload can expand significantly when decompressed. Looking only at bytes on the wire can cause an application to underestimate the memory needed to parse the message.

When setting limits, consider the decompressed message size that the runtime must process. Do not raise the limit just because gzip or another compressor is enabled. Compression can reduce bandwidth, but it does not proportionally reduce the heap required for decoded protobuf objects.

Points to control:

- Choose a threshold suitable for the content size after decompression.
- Enable only the compressors/decompressors that are needed.
- Disallow compression types that are not supported or controlled by the system.
- Limit concurrency and request rate to avoid decompressing many large messages simultaneously.
- Monitor CPU, heap, and decompression time when compression is enabled.

A message that does not exceed the threshold can still consume significant CPU or create a large object graph. A message-size limit is one layer of protection, not a mechanism against all forms of resource exhaustion.

## 5. Choosing limits based on contract and resource budget

There is no single threshold suitable for every RPC. An order lookup API might only need a few KiB; a batch submission API might need a few MiB; a file upload API should be designed with chunks instead of raising a single message to hundreds of MiB.

When choosing a threshold, consider:

1. **Contract:** the largest valid request/response that the API genuinely needs.
2. **Memory:** serialized size can be significantly smaller or larger than the object graph on the heap after parsing.
3. **Concurrency:** how many large messages can be processed concurrently on one instance.
4. **Compression:** size after decompression and required CPU.
5. **Latency:** parsing, validating, and processing a large message can exceed the deadline.
6. **Deployment:** heap limit, container memory, autoscaling, and node resource limits.
7. **Client population:** compatibility of older clients with the new threshold.

You can roughly estimate memory from message size and concurrency, but do not assume heap usage equals the exact serialized byte count. Protobuf objects, strings, collections, byte arrays, copy buffers, and business objects have their own overhead. Measure via load tests with near-threshold payloads in a production-like environment.

For example, if an instance has 1 GiB of heap dedicated to the workload, you cannot divide 1 GiB by 8 MiB and conclude it can handle 128 concurrent messages. Requests also use memory for channels, connections, caches, threads, domain objects, and responses. Reserve headroom and set independent concurrency/quotas.

## 6. Configuration does not replace application-level validation

Transport limits protect the total size of a single message. They do not guarantee that every field has a valid or business-appropriate value.

Example protobuf request:

~~~proto
message ImportBatchRequest {
  string tenant_id = 1;
  repeated string external_ids = 2;
  bytes attachment = 3;
}
~~~

A message below the threshold can still contain:

- Too many elements in external_ids.
- An extremely long string in a single field.
- Deeply nested fields causing high CPU usage during processing.
- An attachment whose size is inappropriate for the use case.
- Data that is valid protobuf but invalid according to business rules.

After the transport accepts the message, the application still needs to check individual field sizes, element counts, schema depth/complexity, tenant, and access permissions. Set specific business limits, such as at most 500 IDs in a batch or at most 256 KiB for an attachment field, if required by the contract.

Do not use a very large message threshold as a substitute for bounded schema design. Splitting large operations into smaller RPCs/chunks usually makes retries, progress tracking, flow control, and cleanup easier to manage.

## 7. Large data: use chunking instead of raising limits indefinitely

For large files or payloads, design client-streaming or bidirectional streaming in chunks. For example:

~~~proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

message UploadResult {
  string upload_id = 1;
  int64 bytes_received = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
~~~

Each chunk should have a clear maximum size, smaller than the server's inbound message limit. The server verifies sequence, upload ownership, tenant, quota, and total bytes before writing the chunk.

A safe upload flow can:

1. Create an upload session with a total quota and expiration time.
2. Verify that the principal is authorized to upload to the resource/tenant.
3. Receive each chunk within the size limit.
4. Check sequence and total bytes before saving.
5. Write the chunk to object storage or a staging area using a safe mechanism.
6. Upon completion, verify checksum and metadata, then finalize.
7. Cancel the session and release temporary data when the client cancels or the upload expires.

Chunking does not automatically limit the total upload. You must add a total quota, chunk count limit, upload duration limit, concurrent upload limit, and cleanup for abandoned sessions. Do not assemble all chunks into one large byte array on the heap if you can stream them to storage.

## 8. Streaming: per-message limits and total stream limits

For streaming RPCs, maxInboundMessageSize is applied to each incoming message. A client-streaming call can send very many messages of valid size whose total data exceeds the service's capacity.

Therefore, multiple layers must work together:

| Limit | What it protects |
| --- | --- |
| **max inbound message size** | Maximum size of a single message |
| **Maximum messages per stream** | Maximum number of messages in one RPC |
| **Total bytes per stream** | Total data received over the entire stream |
| **Deadline/maximum stream lifetime** | How long the stream is allowed to exist |
| **Concurrent stream limit** | Concurrent streams per server/tenant |
| **Rate limit** | Rate of sending messages or bytes |
| **Flow control/backpressure** | Producer speed relative to consumer capacity |
| **Application quota** | Business-level total capacity, e.g., file upload size |

The total byte counter must use a sufficiently large numeric type such as long, check for overflow, and update before causing side effects. With multiple concurrent streams, per-tenant quotas must be updated atomically so two streams do not exceed the limit together.

When a stream exceeds its total quota, the service can terminate with RESOURCE_EXHAUSTED according to the contract. When a single message exceeds the max inbound limit, the transport usually rejects the message before the service handler receives it.

## 9. Status when a message exceeds the limit

When an inbound message is larger than the configured threshold, grpc-java usually terminates the RPC with status RESOURCE_EXHAUSTED. The service implementation may never receive that request message, because the error is detected at the deframer/transport layer before invoking the handler.

The client should distinguish:

- **Message exceeds transport limit:** check serialized size and the server's receive limit configuration.
- **Total quota exceeded:** check total bytes, message count, or operation quota.
- **Field violates contract:** the server received the message, but application validation rejected it, usually using INVALID_ARGUMENT or a contract-appropriate status.
- **Missing upload permission:** use PERMISSION_DENIED, not RESOURCE_EXHAUSTED.

Do not rely on grpc-java's specific status description because the wording can change across versions/transports. Use the status code and server-side logs for classification. If the client sees RESOURCE_EXHAUSTED, do not automatically retry the same payload; retrying does not make the message smaller and can cause unnecessary duplicate requests.

For mutations, consider idempotency. When a connection drops or a deadline expires, the client cannot always know how much data the server committed. Chunked uploads should have an upload ID, sequence, and a clear resume/idempotency mechanism.

## 10. Observability and operations

To operate limits effectively, monitor:

- Number of RPCs rejected due to oversized messages by method.
- Serialized message sizes near the threshold and p50/p95/p99 percentiles.
- Total bytes and message count per stream.
- Heap usage, allocation rate, GC pauses, and OOMs.
- CPU usage during decompression/protobuf parsing.
- Concurrent stream count, stream duration, and cancellation count.
- Rate of RESOURCE_EXHAUSTED categorized by cause.

Avoid logging full payloads or sensitive bytes for diagnostics. Log only method, size, transport/status, policy-sanitized tenant identifier, and necessary trace IDs. Do not put high-cardinality request IDs or tenant IDs into metric labels if it causes metrics explosion.

When adjusting limits, change them incrementally and compare rejection rates, heap, CPU, and latency. A limit set too low breaks valid clients; a limit set too high increases the blast radius when large requests or many concurrent requests arrive.

## 11. Testing size boundaries

You must test exact boundaries rather than just sending a small request and concluding the configuration works.

Suppose the server limit is 1 MiB:

| Payload | Expectation |
| --- | --- |
| Smaller than limit | Server receives and processes |
| Equal to limit | Verify behavior based on actual serialized size and transport |
| Larger than limit | Transport rejects; usually RESOURCE_EXHAUSTED |
| Many small messages in a stream | Each message is received; total quota is checked separately |
| Compressed message with large decompressed payload | Bounded by the runtime's receive-size enforcement |
| Response exceeds client inbound limit | Client rejects response |

Use protobuf generated messages and getSerializedSize() to build payloads near the threshold. Remember that a bytes field adds a tag and length prefix in serialized protobuf, so the length of the byte array does not equal the entire serialized size.

Example of a client-side check before sending:

~~~java
int serializedBytes = request.getSerializedSize();

if (serializedBytes > configuredServerLimitBytes) {
    throw new IllegalArgumentException(
            "Request exceeds the server message-size contract");
}
~~~

This is only a convenience validation on the client. Tests must send an over-limit request to a real server or an in-process transport configured with the same receive limit to verify that the server rejects independently of any client-side check.

Tests should cover:

1. Valid requests below the threshold are processed.
2. Over-threshold requests do not enter the service handler.
3. The status code observed on the client matches the transport/version.
4. Client inbound limit is tested independently of server inbound limit.
5. Streaming total data exceeding quota even when each message is small.
6. Compression does not bypass the limit.
7. Spring application test verifying the actual builder configuration was applied.

## 12. Common pitfalls

| Pitfall | Consequence | Mitigation |
| --- | --- | --- |
| Thinking server inbound limit bounds responses | Client receives oversized responses | Configure client inbound limit separately |
| Treating the limit as an HTTP/2 frame limit | Setting threshold at the wrong layer | Understand this is a single gRPC message limit |
| Raising the limit very high for file uploads | Heap and GC spike sharply | Use chunked streaming and total quotas |
| Looking only at compressed byte count | Payload expands greatly when decompressed | Evaluate decompressed size and CPU |
| Assuming streams have an automatic total limit | Many small messages create a huge stream | Count total bytes/messages and set deadlines |
| Validating only on the client | Raw clients bypass the check | Server transport limit and application validation |
| Checking only total message size | A single field or collection is too large for business logic | Set separate limits for fields and element counts |
| Retrying rejected payloads | Repeating errors that cannot self-resolve | Shrink/split payload or adjust contract |
| Configuring Spring property for wrong starter | Server runs with unexpected defaults | Use version-supported builder hook and integration tests |

## 13. Hands-on exercises and self-check questions

### Hands-on exercises

1. Choose a specific server inbound limit, such as 1 MiB, and configure it on the grpc-java server builder.
2. Configure a separate client inbound limit for responses.
3. Create a protobuf request with a bytes field and use getSerializedSize() to construct payloads below, near, and above the threshold.
4. Write an integration test proving that over-threshold requests do not enter the service handler.
5. Create a chunked client-streaming upload, limiting bytes per chunk and total upload bytes.
6. Add chunk count quota, upload duration limit, concurrent stream limit, and cleanup on cancellation.
7. Enable compression in tests and verify receive-size enforcement still protects the message.
8. In a Spring gRPC application test, verify that the builder customizer/extension point actually applies the limit.

### Self-check questions

**1. What does max inbound message size limit?**  
The maximum size of a single gRPC message that an endpoint receives.

**2. Does the server inbound limit restrict responses the server sends to the client?**  
No. The client must configure its own inbound limit to restrict received responses.

**3. What is the configuration unit?**  
Bytes.

**4. Can a stream exceed multiple GiB even when every message is below the limit?**  
Yes. The limit applies per message; total byte quotas, message counts, durations, and rate limits are needed for the stream.

**5. Does compression make large payloads safe by default?**  
No. You must consider decompressed size, CPU, and memory required for parsing.

**6. Why should large file uploads use chunks?**  
Chunks keep messages small, supporting retry/resume, progress tracking, and flow control; total quotas and cleanup are still required.

**7. What status usually appears when an inbound message exceeds the threshold?**  
Usually RESOURCE_EXHAUSTED; rely on the status code and logs, not on parsing a specific description.

**8. Why is a client-side getSerializedSize check insufficient?**  
The client can be bypassed or spoofed. The server must enforce the receive limit at the transport layer.

## Summary

max inbound message size limits the size of **each incoming gRPC message**. The server configures the limit for requests received from clients; the client configures the limit for responses received from the server. The unit is bytes, and a message limit is not the same as an HTTP/2 frame limit or the total data of a streaming RPC. When choosing a threshold, consider the decompressed payload, protobuf object overhead, concurrency, heap, and latency. Large data should be chunked and paired with total quotas, flow control, deadlines, and cleanup. Testing boundaries on the actual grpc-java transport and verifying the real Spring configuration prevents applications from unintentionally running with unsuitable default limits.
