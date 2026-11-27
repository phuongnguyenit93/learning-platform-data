# Protecting gRPC Services Against Oversized Messages

In a Spring gRPC service, message size limits are the first line of defense protecting memory, CPU, and process stability when receiving data over the network. An RPC can be syntactically valid Protocol Buffers yet carry a payload large enough to strain the heap, decoder, and worker threads. Consequently, services need gRPC-layer size limits, additional business validation, and appropriate data-transfer designs.

This lesson focuses on configuring inbound message limits on servers and clients, choosing thresholds, handling errors, and writing tests to verify that limits are genuinely enforced at runtime.

## Objectives

After this lesson, you will be able to:

- Distinguish the size of a single gRPC message from HTTP/2 frame sizes and the total volume of a streaming RPC.
- Identify which endpoints require inbound limit configuration.
- Configure `maxInboundMessageSize` using Spring Boot or `grpc-java` APIs.
- Design large uploads/downloads using streaming, chunking, or external storage.
- Test below, at, and above the threshold, and recognize `RESOURCE_EXHAUSTED` errors.

## 1. Why Are Oversized Messages a Risk?

gRPC uses Protocol Buffers to serialize data and transmit it over HTTP/2. A single large message can amplify several costs:

1. **Memory:** incoming network data, intermediate buffers, and decoded Java objects can coexist simultaneously. Heap object footprint is typically larger than wire bytes.
2. **CPU:** decompression, Protobuf decoding, buffer copying, and data validation all consume CPU. Large payloads can stretch processing time for a single RPC.
3. **Garbage Collection:** many large objects or large byte arrays increase allocation and collection pressure.
4. **Concurrency:** multiple clients sending large messages simultaneously can exhaust memory or starve smaller requests.
5. **Attack surface:** an authenticated client can still send anomalous payloads far beyond business needs. Size limits curb the ability of a single request to consume unbounded resources.

For example, if a server permits an 8 MiB message and 100 concurrent RPCs receive messages near the threshold, raw message data alone can occupy around 800 MiB. That is only a baseline estimate; buffers, Protobuf objects, data copies, and application logic can drive heap usage significantly higher.

Message limits are therefore part of overall resource control, alongside concurrency limits, request rate limiting, deadlines, metadata size limits, and business quotas.

## 2. Understanding the Exact Scope of Limits

### 2.1. A Message Is Not an HTTP/2 Frame

A gRPC message may be split across multiple HTTP/2 `DATA` frames on the wire. Message size limits apply to the protocol-level gRPC message, not individual HTTP/2 frame sizes. Tuning frame sizes is not the right mechanism for bounding application payloads.

### 2.2. Limits Apply per Message

`maxInboundMessageSize` caps the maximum size of **a single received message**. For unary RPCs, there is typically one request or response message. For client-streaming, server-streaming, and bidirectional streaming, each message in the stream is checked individually.

For instance, a stream of 500 chunks of 1 MiB each is not capped at 4 MiB total merely because the inbound limit is 4 MiB. Each chunk falls under the limit while the cumulative stream reaches 500 MiB. If business logic requires bounding total upload size, chunk count, or stream duration, the application must enforce those budgets explicitly.

### 2.3. Inbound Applies to the Receiving Side

Inbound limits are a property of the **receiving** side:

| Data Flow | Where to Set the Limit |
| --- | --- |
| Client sends request to server | Server limits inbound messages |
| Server returns response to client | Client limits inbound messages |
| Client-streaming | Server limits each client-sent message |
| Server-streaming | Client limits each server-sent message |
| Bidirectional streaming | Both client and server set inbound limits for their own receiving direction |

An inbound limit on the server does not automatically cap responses the server sends out. If the server sends a response exceeding the client's limit, the client can reject that response. Likewise, an inbound limit on the client does not prevent the server from receiving an oversized request.

`maxInboundMetadataSize` is a separate limit for RPC metadata/headers. It does not replace `maxInboundMessageSize`, which governs Protobuf message bodies.

## 3. Configuration in Spring Boot

Property names depend on the Spring Boot and Spring gRPC versions your application uses. Always check documentation matching your running dependencies; do not mix property names across configuration generations.

### 3.1. Spring Boot 4.1.x

In current Spring Boot 4.1.x configuration, the server uses `spring.grpc.server.inbound.message.max-size`. On the client, limits can be configured per logical channel. The example below sets an 8 MiB limit on the server and the `inventory` channel:

~~~yaml
spring:
  grpc:
    server:
      inbound:
        message:
          max-size: 8MB
    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          inbound:
            message:
              max-size: 8MB
~~~

The server property controls request messages received by the server. The client property controls response messages received by the `inventory` channel. If the application defines multiple channels, configure limits on the specific channels that need to receive large responses.

### 3.2. Spring gRPC 1.0.x

Spring gRPC 1.0.x uses different property names. For the default channel, the corresponding configuration looks like:

~~~yaml
spring:
  grpc:
    server:
      max-inbound-message-size: 8MB
    client:
      default-channel:
        max-inbound-message-size: 8MB
~~~

These two examples represent two version-specific configuration styles. Before applying them, verify your dependency management versions and project application properties. An unsupported property in your active version may be ignored or fail to enforce the intended limit.

## 4. Configuring Directly with grpc-java

When manually constructing a server or channel, call `maxInboundMessageSize(int bytes)` on the corresponding builder. The argument is specified in bytes.

~~~java
private static final int MAX_MESSAGE_BYTES = 8 * 1024 * 1024;

Server server = ServerBuilder.forPort(9090)
        .maxInboundMessageSize(MAX_MESSAGE_BYTES)
        .addService(new InventoryService())
        .build();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("inventory.internal", 9090)
        .useTransportSecurity()
        .maxInboundMessageSize(MAX_MESSAGE_BYTES)
        .build();
~~~

In this example:

- `ServerBuilder.maxInboundMessageSize` caps messages received by the server.
- `ManagedChannelBuilder.maxInboundMessageSize` caps messages received by the client.
- `8 * 1024 * 1024` equals 8 MiB.

When Spring manages server and channel lifecycles, configure limits via the starter's properties or extension points. Do not spin up extra manual servers/channels merely to set limits, as that can create mismatched connection configurations or duplicate resource lifecycles.

Per the `grpc-java` API, the default on `ServerBuilder` and `ManagedChannelBuilder` is 4 MiB when unconfigured. This default may differ across other transports or integration libraries; confirm with your deployed version's documentation and real tests. The API also notes that certain transports may not enforce this limit; the `InProcess` transport is a notable example when writing integration tests.

## 5. Choosing Safe Thresholds

Never raise a limit solely because a single request failed. First determine why a large message is needed and measure actual data sizes.

A threshold-selection process can follow these steps:

1. Measure serialized sizes of representative requests and responses, including valid large cases.
2. Inspect size distributions per endpoint, such as p50, p95, p99, and the largest business-approved case.
3. Choose a threshold slightly above the largest valid case with sensible headroom, while staying within the service's memory and CPU budget.
4. Evaluate consumption when many concurrent RPCs receive messages near the threshold.
5. Document the rationale and commit it to deployment configuration so environments stay consistent.

For example, if an API's largest valid request is around 2 MiB, setting a 64 MiB limit just to suppress errors is unjustified. Conversely, if an RPC legitimately needs 12 MiB payloads, leaving the 4 MiB limit unchanged will reject valid requests. Establish actual requirements and redesign payloads if large transfers are routine.

Never set an arbitrarily huge limit or disable limits in production. Raising the limit increases the resources a single peer can demand per message; it does not magically add memory or processing capacity to the service.

## 6. Designing for Large Business Data Transfers

If payloads regularly exceed reasonable single-message limits, change the transfer pattern.

### 6.1. Chunking Data in a Streaming RPC

For file uploads, clients can send multiple chunks over a client-streaming RPC. Each chunk should have its own maximum size, sequence number, and upload identifier.

~~~proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes content = 3;
}

message UploadSummary {
  string upload_id = 1;
  int64 total_bytes = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadSummary);
}
~~~

Inside the service, validate both individual chunk size and cumulative bytes for the upload. Example total-size check:

~~~java
private static final long MAX_CHUNK_BYTES = 1024L * 1024L;
private static final long MAX_UPLOAD_BYTES = 100L * 1024L * 1024L;

private long acceptChunk(UploadChunk chunk, long receivedBytes) {
    long chunkBytes = chunk.getContent().size();

    if (chunkBytes > MAX_CHUNK_BYTES
            || chunkBytes > MAX_UPLOAD_BYTES - receivedBytes) {
        throw Status.RESOURCE_EXHAUSTED
                .withDescription("Upload exceeds the allowed size")
                .asRuntimeException();
    }

    // Write chunk to storage or process as a stream.
    return receivedBytes + chunkBytes;
}
~~~

Call `acceptChunk` from `StreamObserver.onNext` and store the returned value in a `receivedBytes` variable owned by that observer; each RPC must maintain isolated state, never shared across clients. If validation throws `StatusRuntimeException`, pass the error to `responseObserver.onError` to terminate the RPC. Production implementations also need to handle chunk ordering, duplicate chunks, RPC cancellation, timeouts, checksum verification, and cleaning up aborted uploads. Stream chunks out to storage rather than buffering the entire payload on the heap.

The gRPC message limit must still be set greater than or equal to the valid chunk size. The total upload limit is a separate business rule enforced throughout the stream.

### 6.2. Using Object Storage for Large Files

For files spanning hundreds of MiB or multiple GiB, a better pattern is usually:

1. Client calls an RPC to request upload authorization and receives a time-limited URL from object storage.
2. Client uploads the file directly to object storage using the appropriate upload mechanism.
3. Client calls another RPC submitting the object key, size, checksum, and required metadata.
4. Server verifies access rights, checksum, size, and file state before processing.

This lets gRPC carry control messages and business state while dedicated storage infrastructure handles bulk byte streams.

### 6.3. Paginating Results and Reducing Redundant Data

For responses returning large collections, use pagination or streaming instead of returning the entire list in one unary response. Avoid unnecessary data duplication, avoid Base64-encoding files inside strings, and prefer `bytes` fields when binary transfer is genuinely needed.

## 7. Combining Protocol Limits with Business Validation

gRPC-layer limits shield the endpoint from messages crossing the threshold. They do not replace structural and business-rule validation after a message is received.

For instance, a 2 MiB message may still be invalid if it contains:

- Too many elements in a `repeated` field.
- A `bytes` field exceeding business limits.
- An overly long UTF-8 string; character count does not equal byte count.
- Deeply nested structures or data invalid for the current state.
- Total stream volume exceeding quota even when every chunk is valid.

Define per-RPC budgets: max message size, max element counts, per-field limits on key fields, total stream bytes, concurrent RPCs, and processing time. When rejecting data at the business layer, return a clear status and description so clients can correct requests.

Compression can reduce wire bytes, but should never be treated as a way around message limits. Payloads still must be decompressed and decoded, consuming resources. In particular, never accept unbounded data simply because clients compress before sending.

Beyond message bodies, keep metadata limits reasonable. Metadata is meant for tokens, trace context, and control headers; never use metadata to carry large payloads.

If an API gateway, reverse proxy, or ingress sits in front of the gRPC server, verify limits at every tier. A request might be rejected by the proxy before reaching the application, or rejected by the gRPC runtime after passing the proxy. Align thresholds and error observability across layers.

## 8. Error Handling and Operational Observability

When a message exceeds the inbound limit, `grpc-java` typically terminates the RPC with status `RESOURCE_EXHAUSTED`. Rejection can occur before the service method is invoked, so do not expect service code to always receive the request to inspect its size.

On the client, handle errors via `onError` callbacks or exceptions corresponding to the stub type in use. You can classify `RESOURCE_EXHAUSTED` to surface that the request/response exceeded allowed limits. Never automatically retry the exact same payload at the same size: a deterministic oversized request will exceed the limit on subsequent attempts as well.

Operationally, monitor:

- Count of RPCs rejected for oversized messages, broken down by service and method.
- `RESOURCE_EXHAUSTED` status codes and error rates over time.
- Message size distributions on critical endpoints.
- Heap usage, GC pauses, CPU, and active RPC counts under rising load.
- Errors originating at gateways/ingresses when intermediary layers exist.

Log RPC name, status, estimated size, and correlation/trace IDs where appropriate. Never log full payloads or sensitive data just to diagnose size errors.

## 9. Testing Limits

Good tests verify both configuration wiring and boundary behavior.

### 9.1. Testing Three Size Cases

Given a limit `MAX_MESSAGE_BYTES`, construct messages with serialized sizes:

- Below limit: RPC must succeed when other conditions are valid.
- Equal to limit: verify your exact version's transport and serializer accept the boundary value.
- Above limit: RPC must be rejected; the receiving side must not process the message.

Protobuf Java provides `getSerializedSize()` to inspect a message's serialized byte size:

~~~java
int serializedBytes = request.getSerializedSize();
assertThat(serializedBytes).isLessThanOrEqualTo(MAX_MESSAGE_BYTES);
~~~

This checks the Protobuf message size before sending. To verify the transport limit, send the message over a real gRPC connection and assert the returned status.

### 9.2. Testing Over the Right Transport

Do not rely solely on `InProcess` transport to verify limits. `grpc-java` documentation explicitly notes that `maxInboundMessageSize` may not be enforced by all implementations and cites `InProcess` transport as such a case. Maintain at least one integration test running over the production transport, such as Netty or the corresponding servlet server.

### 9.3. Testing Streaming and Concurrent Load

For streaming RPCs, test specifically:

- A single chunk exceeding the message limit.
- Multiple valid chunks whose cumulative stream exceeds quota.
- Out-of-order, duplicate, or mid-stream cancelled chunks.
- Multiple concurrent streams sending chunks near the threshold.

Also test the client receiving large responses. A server can emit a response valid under server config that still exceeds the client's inbound limit.

## 10. Troubleshooting Procedure for Oversized Message Errors

When a client reports `RESOURCE_EXHAUSTED`, trace these steps:

1. Identify the failing method and direction: request into server or response into client.
2. Measure the actual serialized message size; do not guess from character counts or source file sizes.
3. Check the limit on the receiving endpoint and verify the property actually binds in your running Spring version.
4. Check gateways/ingresses and intermediaries if traffic passes through them.
5. If large payloads are a legitimate requirement, consider a controlled limit increase or migrating to chunked streaming/object storage.
6. Re-test below, at, and above the threshold over the real production transport.
7. Monitor heap, CPU, GC, and error rates after deploying the updated configuration.

## Deployment Checklist

- [ ] Inbound limits identified on server and client for the exact receiving directions.
- [ ] Property names verified against Spring Boot/Spring gRPC versions.
- [ ] Limits remain finite and justified by real payload data.
- [ ] Single-message limits distinguished from total streaming RPC quotas.
- [ ] Business limits enforced on chunks, `bytes` fields, lists, and total upload sizes.
- [ ] Metadata, proxies/ingresses, and intermediaries checked.
- [ ] Tested over real network transport, not solely `InProcess` transport.
- [ ] `RESOURCE_EXHAUSTED`, message sizes, and process resources monitored.

## References

- [Spring Boot Reference — gRPC](https://docs.spring.io/spring-boot/reference/io/grpc.html): server and channel configuration in Spring Boot 4.x.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): list of gRPC properties, including inbound message and metadata limits.
- [Spring gRPC 1.0 — Common Application Properties](https://docs.spring.io/spring-grpc/reference/1.0/appendix.html): property names for Spring gRPC 1.0.x.
- [grpc-java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): server-side `maxInboundMessageSize` API.
- [grpc-java — ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): client-side `maxInboundMessageSize` API.
