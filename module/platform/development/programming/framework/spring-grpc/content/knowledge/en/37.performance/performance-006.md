# Compression and CPU Trade-offs

Compression in gRPC reduces payload bytes transmitted over the network by encoding messages into a smaller representation. In return, the sender spends CPU compressing and the receiver spends CPU decompressing. Consequently, enabling compression can boost goodput when the network is the bottleneck, yet it can lower throughput when CPU, latency, or garbage collection is already the limiting factor.

In **SPRING_GRPC**, compression should be chosen based on each RPC's payload characteristics and workload. Small events, already compressed data, or CPU-bound services typically do not benefit from compressing every message. For streams carrying many records with repetitive structure, compression can significantly cut bandwidth, but you must measure client/server CPU, p95/p99 latency, memory, and actual bytes saved.

## 1. Where does gRPC compression operate?

gRPC runs over HTTP/2 and has its own framing per message. gRPC compression applies at the **message payload** level, not across the entire HTTP/2 connection. Metadata and HTTP/2 frames are not combined into a single compressed block with the message.

Conceptually, a gRPC message contains:

- A one-byte flag indicating whether the message is compressed.
- The wire length of the message payload.
- The Protobuf payload, either identity (uncompressed) or compressed.

At the call level, the sender can select a compression algorithm such as gzip. gRPC metadata uses `grpc-encoding` to indicate the algorithm used for messages and `grpc-accept-encoding` to advertise supported algorithms. Each message also carries its own flag indicating whether that specific payload is compressed.

This allows a single streaming call to carry multiple messages of varying sizes and characteristics. Compression does not guarantee every message becomes smaller; payloads that are already compressed or too small may see no benefit from compressing.

## 2. CPU trade-off: saving network at the cost of compute

A compressed data flow typically passes through these stages:

```mermaid
flowchart LR
    A["Protobuf message"] --> B["Compress on sender"]
    B --> C["TLS + HTTP/2 transport"]
    C --> D["Receive bytes"]
    D --> E["Decompress on receiver"]
    E --> F["Protobuf decode"]
    F --> G["Application processing"]
```

Compression shifts part of the cost from the network to CPU:

| Resource | Without compression | With compression |
| --- | --- | --- |
| Network bytes | Higher | Usually lower if payload compresses well |
| Sender CPU | Minimal compression work | Higher due to encode/compress |
| Receiver CPU | Minimal decompression work | Higher due to decompress |
| Latency per message | Fewer steps | Adds compress/decompress time |
| Memory/allocation | Depends on message and transport | Adds intermediate buffers, depending on implementation |
| Goodput when network-bound | Can be bandwidth-limited | Can rise if byte savings outweigh CPU cost |
| Throughput when CPU-bound | Often higher | Can drop due to CPU saturation |

No single answer fits every workload. If the network is saturated while CPU has headroom, compression can improve total throughput. If CPU is already near saturation, compression can worsen both latency and throughput even though transmitted bytes drop.

### 2.1. Quantitative example

Suppose a Protobuf message is 100 KiB:

- Uncompressed: transmits nearly 100 KiB of payload.
- Compressed to 30 KiB: saves about 70 KiB of payload.
- Sender spends CPU compressing; receiver spends CPU decompressing.

Compressed size ratio:

\[
\text{Compression ratio} =
\frac{\text{Compressed bytes}}{\text{Original bytes}}
\]

In this example, the ratio is 0.30, corresponding to roughly a 70% payload byte reduction. Yet this figure alone does not tell you whether compression is worth enabling. You must know the CPU time to compress/decompress, RTT, bandwidth, concurrent stream count, and latency SLOs.

## 3. Which payloads compress well?

Compressibility depends on entropy and data structure:

| Payload | Typical compressibility | Reason |
| --- | --- | --- |
| JSON/text with repeated fields and keywords | Good | Many repeated substrings |
| Logs/events with uniform structure | Usually good | Repeated field names and data patterns |
| Protobuf containing similar values | Potentially good | Repeated byte patterns and content |
| Small numeric data, packed repeated fields | Depends on distribution | Protobuf already encodes scalars compactly |
| JPEG, PNG, ZIP, gzip, or pre-compressed payloads | Usually poor | Redundancy has already been removed |
| Encrypted or high-entropy data | Usually poor | Little repetitive structure to exploit |
| Very small messages | Usually minimal gain | Compression framing and CPU can exceed byte savings |

Do not decide solely based on the Protobuf format. Protobuf already provides efficient binary encoding for many data types, yet messages can still contain text, repetitive fields, or compressible payloads. Benchmark representative samples rather than guessing from message names or schemas.

## 4. Message size and compression thresholds

Compressing very small messages may bring no benefit because:

- The algorithm must initialize and process buffers.
- Compression headers/framing add some overhead.
- CPU time can exceed time saved on the network.
- Small payloads may lack enough repetition to achieve a good compression ratio.

A practical strategy is to compress only when messages are large enough and the payload class has been proven compressible. There is no universal byte threshold; benchmark on your actual hardware, JVM, algorithm, and network.

If a stream mixes small and large messages, consider a per-call or per-message compression policy if supported by the API/runtime in use. Avoid building complex policies before measurements prove a benefit.

## 5. Choosing a compression algorithm

gRPC uses encoding names so both peers agree on the algorithm. Gzip is a common choice with broad support in gRPC Java. The runtime may support other compressors depending on implementation and configuration.

When choosing, evaluate:

- Compression ratio on real payloads.
- Encode and decode CPU cost.
- Latency across small and large message sizes.
- Memory allocation and GC impact.
- Compatibility between client and server runtimes.
- Observability and operational support for the algorithm in your deployment environment.

Do not assume client and server support the same compressor just because both use gRPC. The receiver must advertise supported algorithms, and the sender should only select a compatible encoding. If an algorithm is unregistered or unsupported by the peer, calls can fail at the transport/protocol layer.

## 6. Enabling compression on a gRPC Java client

In gRPC Java, a stub can select compression for a call using `withCompression`. Unary example:

```java
OrderReply reply = blockingStub
    .withCompression("gzip")
    .getOrder(request);
```

For client-streaming or bidirectional streaming, configure compression on the stub before opening the call:

```java
OrderServiceGrpc.OrderServiceStub compressedStub =
    asyncStub.withCompression("gzip");

StreamObserver<OrderEvent> requestObserver =
    compressedStub.publishEvents(responseObserver);
```

In this example, `withCompression("gzip")` selects the compressor for request messages sent by the client during the call. It does not automatically dictate how the server compresses responses. Response compression is an independent decision on the server side.

Stubs created from a `ManagedChannel` can be reused following the immutable semantics of generated stubs; `withCompression` returns a stub with updated call options. Never create a new channel per message just to enable compression.

### 6.1. Conditional compression

If you have multiple RPC types, you can use a compressed stub only for methods transferring large payloads:

```java
if (payloadSize >= compressionThresholdBytes) {
    return blockingStub
        .withCompression("gzip")
        .upload(request);
}

return blockingStub.upload(request);
```

`compressionThresholdBytes` should be determined by benchmarks and message size policies. Pre-compression request size can be estimated from the Protobuf message's serialized size; do not use Java object size or count only raw byte fields.

Do not enable compression by default for all RPCs when the workload has many small messages, is CPU-sensitive, or carries already compressed payloads.

## 7. Server-side compression

Request compression and response compression are two independent directions:

- Client compresses requests; server must support decompressing the encoding the client sends.
- Server compresses responses; client must advertise the encodings it accepts.

In gRPC Java, the server can choose a response compressor before sending response headers via `ServerCall.setCompression`. Illustrative interceptor example:

```java
public final class GzipResponseInterceptor
        implements ServerInterceptor {

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        call.setCompression("gzip");
        return next.startCall(call, headers);
    }
}
```

This example selects gzip for responses of calls passing through the interceptor. In production, register the interceptor only for services/methods with suitable payloads, ensure the compressor is supported, and test with real clients. Avoid applying global compression to all responses if most responses are small or incompressible.

If a service needs granular per-method or per-message policies, place the decision at the right call boundary and use the compression API of the deployed gRPC Java version. Response compression is never inferred from whether the client compressed the request.

## 8. Compression in streaming

In streaming, a single call can transmit many messages. Compression can substantially reduce total bytes, yet CPU cost accumulates with message count and payload size.

Factors to evaluate:

- Average size and size distribution of messages.
- Whether payload content repeats across messages.
- Messages per second and concurrent stream count.
- Sender and receiver CPU as load increases.
- Small messages mixed with large messages.
- Backpressure and flow-control wait times.
- Handling failed messages or mid-stream cancellation.

gRPC message compression does not mean the compressor retains a shared dictionary across the entire stream. Do not assume earlier messages help compress later messages like a continuous archive; measure according to actual compressor/runtime semantics.

If a stream sends thousands of small messages, compressing each message individually can cost considerable CPU. You can batch records at the application layer before compressing, though batching introduces its own latency, memory, and partial-failure trade-offs. Combine both techniques only when benchmarks prove the overall result is better.

## 9. Compression and TLS

In standard gRPC architectures, messages are compressed at the gRPC layer before data is protected by TLS. TLS encrypts data on the wire; TLS does not automatically compress application payloads.

This means:

- Compression can reduce the bytes TLS must protect and the network must transmit.
- TLS still consumes CPU to encrypt/decrypt records.
- Compression adds CPU on sender and receiver on top of TLS cost.
- If CPU is already heavily utilized by TLS, compression can trigger saturation earlier.

Never disable TLS to boost throughput in production. Benchmark realistic configurations with TLS, certificate validation, and compression matching the deployment environment. Plaintext benchmarks can help isolate a bottleneck in a test lab, but they do not fully represent production costs.

## 10. Message size limits and resource protection

Compression shrinks wire payloads, yet decompressed data can be much larger. Therefore, never use the compressed byte count as the sole limit.

In gRPC Java, clients and servers can configure inbound message size limits via builder APIs such as `maxInboundMessageSize`. Exact values should match the contract and available memory:

```java
ManagedChannel channel = NettyChannelBuilder
    .forAddress("grpc.example.com", 8443)
    .useTransportSecurity()
    .maxInboundMessageSize(8 * 1024 * 1024)
    .build();
```

The 8 MiB limit is illustrative, not a universal recommendation. Configure corresponding limits on both server and client for inbound messages. Inbound limits must guard the post-decompression message size handed to the application; never let a small compressed payload allocate massive heap after decompression.

In addition to message size, bound:

- Message count and total bytes within a stream.
- Processing duration and deadlines.
- Concurrent streams per caller/tenant.
- Application queues and buffers.
- Request rate if the service enforces quotas/rate limits.

These measures defend against decompression bombs and resource exhaustion. Compression must never become a way to bypass quotas or payload limits.

Compression must also be evaluated in your threat model. If a single message combines a secret with caller-controlled data, the compressed size can vary with how much the two parts overlap; an attacker observing response length could infer information about the secret in certain designs. For responses mixing sensitive data with caller-reflected content, consider disabling compression on that message or separating secrets from caller-controlled data. TLS protects content confidentiality but does not completely hide traffic lengths.

## 11. Measuring compression ratio and CPU cost

A useful benchmark measures both network benefits and CPU costs:

| Metric | Interpretation |
| --- | --- |
| Original payload bytes | Message size before compression |
| Compressed payload bytes | Message size after compression |
| Compression ratio | Compressed/original; lower usually saves more bytes |
| CPU time/message | Compression or decompression cost per message |
| CPU utilization | Sender and receiver CPU usage |
| Messages/s | Messages processed per second |
| Payload goodput | Uncompressed payload bytes processed per second |
| Wire bytes/s | Actual network traffic |
| Latency p50/p95/p99 | Impact on response time |
| Allocation/GC | Cost of intermediate buffers and objects |

Do not look at compression ratio alone. One algorithm might cut bytes by 80% while spiking CPU and lowering messages/s. Another might cut bytes by only 40% while keeping latency and CPU steadier and better aligned with SLOs.

### 11.1. Comparing configurations

Run at least these cases:

| Experiment | Compression | Payload |
| --- | --- | --- |
| A | identity | Small messages |
| B | gzip | Small messages |
| C | identity | Large messages with repetitive structure |
| D | gzip | Large messages with repetitive structure |
| E | identity | Already compressed payload |
| F | gzip | Already compressed payload |

Warm up before measuring steady state. Keep stream count, data, TLS, JVM options, CPU quotas, and network identical across runs. Change one variable at a time so you know exactly what difference compression makes.

### 11.2. Deciding by bottleneck

- **Network-bound, spare CPU:** test gzip on large/compressible payloads.
- **CPU-bound:** prefer identity or selective compression; profile encode/decode first.
- **Latency-bound with small messages:** avoid compressing small messages if cost outweighs benefit.
- **Memory/GC-bound:** inspect buffer allocations, message sizes, and concurrent stream counts.
- **Already compressed payloads:** typically use identity to avoid wasted CPU.

These are initial decision heuristics. Final choices must come from benchmarks in a production-like environment.

## 12. Compression and observability

Monitor compression on both sides:

- Call/message counts by encoding.
- Original bytes and compressed bytes by method/payload class.
- Compression ratio across message size distributions.
- Compression CPU on sender and decompression CPU on receiver.
- Messages/s, payload goodput, and wire bytes/s.
- Latency p50/p95/p99.
- Allocation rate, heap, and GC pauses.
- Unsupported compressor, decompression, and message size limit errors.
- Active streams and queue/flow-control wait times.

Avoid high-cardinality metric labels like user ID, request ID, or message ID. Categorize by service, method, encoding, and payload size buckets. If the runtime does not expose compression metrics directly, measure at the application boundary or benchmark harness; state clearly whether byte counts are payload estimates or actual wire bytes.

Never log payload contents just to measure compression. Use byte counters, histograms, and safe trace metadata.

## 13. Common configuration mistakes and misconceptions

| Mistake | Consequence | Better approach |
| --- | --- | --- |
| Enabling gzip for all RPCs | Wastes CPU on small or incompressible payloads | Select per method/size and benchmark |
| Measuring only post-compression bytes | Hides CPU/latency costs | Measure ratio, CPU, p95/p99, and goodput |
| Thinking TLS compresses data automatically | Misunderstands where compression happens | Compression is at gRPC message layer; TLS secures transport |
| Assuming compressing requests compresses responses | One-way config when two-way is expected | Configure request/response independently |
| Limiting only compressed bytes | Decompressed payload can be huge | Set inbound message size and appropriate quotas |
| Compressing gzip/ZIP/JPEG payloads | Higher CPU with minimal byte savings | Use identity for already compressed payloads |
| Assuming a shared dictionary across the whole stream | Inaccurate ratio estimates | Benchmark according to message/runtime semantics |
| Benchmarking without TLS or real load | Results do not represent production | Measure in a production-like setup |
| Registering a custom compressor unsupported by peer | Calls can fail | Verify negotiation and runtime compatibility |

## 14. Checklist for choosing compression in Spring gRPC

Before enabling compression for a method, verify:

1. **Payload:** is the data repetitive/compressible or already compressed/encrypted?
2. **Size:** are messages large enough for benefits to exceed overhead?
3. **Bottleneck:** is network, CPU, latency, memory, or downstream the constraint?
4. **Direction:** do you need request compression, response compression, or both?
5. **Algorithm:** do client and server support the same encoding?
6. **Streaming:** will message rate and concurrent streams overtax CPU?
7. **Limits:** are post-decompression inbound size, stream byte quotas, and deadlines bounded?
8. **Security:** is there risk of decompression bombs or compressing secrets alongside caller-controlled data?
9. **Benchmarks:** have identity vs. gzip been compared on real payloads with TLS?
10. **SLOs:** do throughput, p95/p99 latency, and CPU meet targets?
11. **Observability:** are ratios, byte counters, CPU, GC, and compression errors tracked?
12. **Fallback:** has behavior when a peer lacks compressor support been tested?

## 15. Key takeaway

Compression in gRPC reduces transmitted bytes by compressing individual message payloads; it does not compress the entire HTTP/2 connection and does not replace TLS. Gzip can improve goodput when the network is the bottleneck and payloads contain repetitive structure, but the sender pays CPU to compress and the receiver pays CPU to decompress. Small messages, already compressed payloads, or CPU-bound services rarely suit default-on compression.

In Spring gRPC, select compression by method, request/response direction, message size, and workload. `withCompression("gzip")` configures the compressor for client calls; response compression must be configured separately on the server and use only encodings supported by the peer. Bound post-decompression message sizes, stream counts, and buffers to protect resources. Benchmark identity against gzip under TLS, measuring compression ratio alongside CPU, goodput, p95/p99, and GC. Keep compression only when overall gains outweigh CPU costs and latency SLOs remain intact.

### References

- [gRPC – Compression](https://grpc.io/docs/guides/compression/)
- [gRPC – Performance](https://grpc.io/docs/guides/performance/)
- [gRPC Java – API documentation](https://grpc.github.io/grpc-java/javadoc/)
- [gRPC – Flow control](https://grpc.io/docs/guides/flow-control/)
- [Protocol Buffers – Encoding](https://protobuf.dev/programming-guides/encoding/)
