# Serialization and Deserialization Costs

In gRPC, Java objects are not sent directly over the network. The client converts a message into a byte sequence using the Protobuf wire format (**serialization**); the server reads the bytes and reconstructs the message (**deserialization**). For the response direction, the process runs in reverse. Both steps consume CPU and memory on every RPC, so they can become a bottleneck when requests are small but at very high frequency, or when payloads are large with many nested fields.

In Spring gRPC, generated stubs and Protobuf marshallers handle the conversion for the application. Optimizing effectively requires understanding costs from the schema, payload size, object allocation, buffer copying, and compression. Measuring the codec in isolation and measuring the full RPC are two different things; you cannot infer production performance solely from the time it takes to call `toByteArray()`.

## 1. Where do serialization and deserialization happen?

For a unary RPC, the general flow is:

```text
Client application
   Java request object
          |
          v
   Protobuf serialization
          |
          v
   gRPC framing / optional compression
          |
          v
   HTTP/2 transport -> network
          |
          v
   gRPC framing / optional decompression
          |
          v
   Protobuf deserialization
          |
          v
Server application
   Java request object
```

The response follows the reverse path. In grpc-java, generated stubs use the marshaller bound to the message type to write and read messages. Applications usually only need to build the request, call the stub, and process the response; you should not manually serialize to bytes and send them as another RPC unless there is a specific requirement.

Costs to distinguish:

- **Serialization CPU:** traversing fields, writing tags, lengths, and values to output.
- **Deserialization CPU:** reading tags, decoding values, constructing messages and collections.
- **Allocation:** creating builders, messages, lists/maps, strings, and buffers.
- **Copying:** moving data between objects, byte arrays, buffers, and the transport layer.
- **Compression:** adding CPU to compress/decompress, which may reduce bytes transmitted over the network.
- **Network:** transmitting bytes, subject to latency, bandwidth, and congestion.

These components may overlap or be handled through internal buffers depending on the implementation. When profiling, measure across the right boundaries rather than adding up non-independent numbers.

## 2. How the Protobuf wire format affects size and CPU

Protobuf encodes each field as a tag and a value. The tag contains the field number and wire type; the value can be varint, fixed-width, or length-delimited. Field names and whitespace in the `.proto` file are not sent on the wire, so binary messages are typically smaller than JSON with repeated field names.

Example:

```proto
syntax = "proto3";

message OrderSummary {
  int64 order_id = 1;
  string status = 2;
  int32 item_count = 3;
  repeated int64 item_ids = 4;
  bytes receipt = 5;
}
```

Size depends on actual values, not just the number of fields:

- Fields with default values in proto3 are typically not serialized unless presence semantics must be preserved.
- Varints use a variable number of bytes depending on the magnitude of the value.
- Field numbers from 1 to 15 have a one-byte tag; larger field numbers may require more bytes.
- `string`, `bytes`, nested messages, and packed repeated fields are length-delimited and require an additional length prefix.
- `fixed32`/`sfixed32` always use 4 value bytes; `fixed64`/`sfixed64` use 8 bytes.

For integers that can be negative, a negative `int32` typically costs 10 bytes due to sign extension in varint encoding. If the data domain contains many negative numbers and efficient representation is needed, `sint32` using ZigZag encoding can be smaller. Only change types when the data semantics allow it.

Do not optimize field numbers or numeric types mechanically. Differences in wire size must be weighed against schema complexity, compatibility, and actual data.

## 3. Designing messages to reduce unnecessary overhead

The schema affects both byte count and the number of objects created during parsing:

| Design | Possible impact | Considerations |
| --- | --- | --- |
| Repeating many small fields in a message | Many tags/values and accessor/object state | Group data sensibly; avoid creating fields just to wrap a single value unnecessarily |
| Deep nested messages | Multiple parse passes and child objects | Keep structure aligned with the domain; avoid nesting that adds no value |
| Large `repeated` | Creating collections and elements during parsing | Limit size/count; use streaming if data naturally splits into multiple parts |
| Large `map` | Creating map entries and hash structures | Use maps only when key lookup is needed; repeated entries or other structures may fit better depending on access patterns |
| `string` for binary data | UTF-8 encode/decode and string validation | Use `bytes` for binary content |
| Repeating metadata in every item | Increased payload and parse work | Move shared metadata up to a message envelope if semantics allow |
| Very large field numbers | Tags may be longer | Choose sensible field numbers from the start; do not change public field numbers just to save a few bytes |

For numeric `repeated` fields, Protobuf proto3 uses packed encoding by default for eligible scalar types, which reduces repeated tags. However, parsing still has to create values for every element. A list of hundreds of thousands of elements can consume significant CPU and heap even when the wire payload is relatively compact.

`oneof` can model mutually exclusive choices and avoid sending multiple unused branches. `optional` or presence semantics are useful when you need to distinguish "not provided" from "provided with default value"; do not drop presence just to save bytes if doing so changes business meaning.

Schemas should be designed for both forward/backward compatibility and performance. Do not reuse deleted field numbers; mark removed fields `reserved` to prevent misinterpreting old data.

## 4. Payload size and allocation in Java

Large messages cost more than just network bytes. During parsing, Protobuf creates the message object and may also create:

- `String` for string fields.
- `ByteString` for `bytes` fields.
- collections for `repeated` and `map` fields.
- nested messages for nested structures.
- builders or intermediate buffers when constructing/writing messages.

Many small RPCs can create greater allocation pressure than one large RPC with the same total bytes, because each call also has its own framing, metadata, callbacks, and object lifecycle. Conversely, a single huge message can cause heap spikes, GC pauses, and tail latency.

Example of checking serialized message size:

```java
OrderSummary summary = OrderSummary.newBuilder()
    .setOrderId(1042L)
    .setStatus("CONFIRMED")
    .setItemCount(3)
    .addItemIds(11L)
    .addItemIds(12L)
    .addItemIds(13L)
    .build();

int encodedSize = summary.getSerializedSize();
byte[] encoded = summary.toByteArray();

OrderSummary decoded = OrderSummary.parseFrom(encoded);
```

`getSerializedSize()` is useful for observing wire size. `toByteArray()` allocates a new byte array; calling it on the hot path just to measure or log introduces extra allocation and copying. In normal RPCs, let the generated marshaller manage serialization. `parseFrom(byte[])` is appropriate for codec tests or existing byte data; you do not need to call it manually for responses received from generated stubs.

Do not hold onto the object graph, byte array, and a `ByteString` copy of the same payload longer than necessary. For large uploads/downloads, consider streaming or bounded batching rather than accumulating the entire content in the heap.

## 5. Strings, bytes, and data conversion

`string` in Protobuf is UTF-8. If an application starts with `byte[]`, converts it to `String`, and then encodes it back to UTF-8, it can create unnecessary objects and copies. If the content is an image, file, compressed blob, or binary token, use `bytes`.

Example:

```proto
message DocumentChunk {
  string file_name = 1;
  bytes content = 2;
  int32 sequence = 3;
}
```

In Java, the generated API uses `ByteString` for `bytes`. `ByteString` is immutable and suitable for safely sharing data; however, creating it from a `byte[]` may still require copying to preserve immutability. Do not assume that using `ByteString` automatically means zero-copy.

For large data, design streaming RPCs with finite chunk sizes, backpressure/flow control, and total size limits. Chunks that are too small increase message count, framing, and callbacks; chunks that are too large increase peak memory and wait time per message. Choose the size by benchmarking on real payloads.

## 6. Compression: fewer network bytes, more CPU

Compression can reduce bytes transmitted, especially for text or repetitive payloads. However, the client and server spend CPU compressing/decompressing and may allocate new buffers.

| Payload characteristics | Compression may help when | Be cautious when |
| --- | --- | --- |
| JSON/text or highly repetitive fields | Payload is large enough and bandwidth is the bottleneck | CPU is already saturated or latency budget is very tight |
| Already compressed binary data | Rarely reduces further significantly | Re-compressing only adds CPU and sometimes increases size |
| Small messages | Usually negligible benefit | Framing/compression overhead is large relative to payload |
| Streaming many messages | Can reduce network traffic | Per-message compression CPU increases latency and lowers throughput |

Do not enable compression for every RPC by default without measuring. You can select a compressor on the client call or stub using the grpc-java API in use; the server must support the corresponding mechanism. Also consider resource risks when decompressing untrusted payloads: bound message sizes and processing resources.

Evaluate compression using at least three metrics: CPU time, bytes on wire, and end-to-end latency. A 70% payload reduction is not a win if CPU doubles and p99 latency degrades.

## 7. Unary and streaming have different cost profiles

A unary RPC sends one request and receives one response. With small payloads, per-call costs such as call creation, metadata, serialization, and scheduling can make up a significant share. Batching multiple items into a single request can reduce call count, but increases payload size and batch waiting latency.

A streaming RPC sends multiple messages within a single call. It can amortize call setup overhead, yet each message still needs serialization/deserialization and is subject to flow control. Streaming does not automatically save CPU; its benefits usually come from fewer calls, data pipelining, and bounded per-chunk memory.

| Exchange pattern | Common hot spots | What to measure |
| --- | --- | --- |
| Unary, small payload, high QPS | Allocation/call overhead and scheduling | Throughput, CPU/request, allocation/request |
| Unary, large payload | Encode/decode, copying, network, and GC | CPU/message, serialized bytes, heap/GC |
| Server streaming | Parsing many responses, slow consumer | Message rate, queue depth, flow-control wait |
| Client/bidi streaming | Buffering and callback lifecycle | In-flight messages, memory per stream, cancellation |

Do not collect every message of a stream into a list just to process them later if you can process them incrementally. Doing so negates the bounded-memory benefit of streaming and can cause an `OutOfMemoryError`.

## 8. Measuring the codec separately and end-to-end

A codec benchmark answers "How much CPU and allocation does Protobuf encode/decode cost?" An RPC benchmark answers "How long does it take client-server to complete a request under realistic conditions?" These two measurements should be kept separate.

A minimal JMH benchmark:

```java
import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class ProtobufCodecBenchmark {

    private OrderSummary message;
    private byte[] payload;

    @Setup
    public void setup() throws Exception {
        message = OrderSummary.newBuilder()
            .setOrderId(1042L)
            .setStatus("CONFIRMED")
            .setItemCount(3)
            .addItemIds(11L)
            .addItemIds(12L)
            .addItemIds(13L)
            .build();
        payload = message.toByteArray();
    }

    @Benchmark
    public byte[] serialize() {
        return message.toByteArray();
    }

    @Benchmark
    public OrderSummary deserialize() throws Exception {
        return OrderSummary.parseFrom(payload);
    }

    @Benchmark
    public int serializedSize() {
        return message.getSerializedSize();
    }
}
```

This is an illustrative benchmark; configure appropriate JMH forks, warmup, measurement iterations, and profilers. Use payloads representative of production, not just a single fixed small message. Return results from benchmark methods so JMH consumes them and avoids dead-code elimination. Do not put `toByteArray()` in `@Setup` if the goal is to measure serialization; for deserialization, prepare the byte array ahead of time so you only measure parsing.

Also measure:

- Allocation rate and bytes allocated/op.
- GC count, pause time, and heap occupancy.
- CPU profile to determine how much time encode/decode methods consume.
- Payload sizes at p50/p95/p99, not just a single average sample.

For end-to-end testing, invoke the generated stub against a test server over the appropriate transport, isolating client serialization, network, server deserialization, and business handler time if the tracing/benchmark harness permits. Measure p50/p95/p99 latency, throughput, and error rate. Run with TLS, compression, and payload sizes matching the target environment.

## 9. How to optimize based on metrics

A practical workflow:

1. **Establish a baseline:** record throughput, latency percentiles, CPU, allocation, GC, and bytes/message.
2. **Break down payloads:** measure by method and size bucket; find messages with abnormal serialized size or allocation.
3. **Profile CPU/heap:** use JFR or an equivalent profiler to identify whether encode/decode, copying, builders, string conversion, or compression is the bottleneck.
4. **Change one variable at a time:** schema, batch size, chunk size, compression, or how messages are built.
5. **Re-measure on the same workload:** keep client count, concurrency, payload distribution, and runtime settings constant.
6. **Verify compatibility:** schema changes must preserve field numbers, wire compatibility, and semantics.
7. **Monitor production:** confirm improvements do not degrade p99, error rate, or heap usage.

Options often worth trying:

- Use `bytes` for binary data instead of converting through `String`.
- Avoid repeating shared metadata in every element.
- Bound `repeated` sizes and chunk sizes.
- Choose `sint32` when small signed/negative numbers are frequent and the schema allows it.
- Use compression only when reducing network bytes is worth the CPU cost.
- Process streams chunk-by-chunk to keep memory bounded.
- Avoid calling `toByteArray()` just to log or measure size on the hot path.

Do not change a public contract just to shave off a few bytes if the benefit is negligible. Optimization must be balanced against schema readability, legacy client compatibility, and operational cost.

## 10. Message limits and resource protection

Oversized payloads can put heap pressure on both client and server, especially under high concurrency. Set inbound/outbound message limits appropriate for the business domain and grpc-java version, such as `maxInboundMessageSize` on the builder or the equivalent starter configuration.

Limits should not be chosen arbitrarily:

- Too low: valid requests get rejected.
- Too high: a handful of clients can consume large amounts of heap and increase GC pauses.
- Unbounded element counts: moderately sized messages can still allocate many objects during parsing.
- Unbounded concurrent streams: total memory can grow with the number of active streams.

For large uploads/downloads, use bounded chunking, per-caller quotas, and deadlines/cancellation. Check size before deep parsing if there is a gateway or admission control layer available; do not rely solely on validation after the entire object graph has already been allocated.

## 11. Performance measurement and testing matrix

| Scenario | Variables to vary | Metrics to observe |
| --- | --- | --- |
| Small vs. large payload | 1 KB, 64 KB, 1 MB, or representative tiers | CPU, latency, serialized bytes |
| Flat vs. nested schema | Field count and message depth | Encode/decode time, allocation |
| Repeated count | Increasing element count | Parse time, heap, GC |
| String vs. bytes | Same data as text/binary | Allocation, conversion CPU |
| Compression on/off | Compressible and incompressible payloads | CPU, wire bytes, p99 |
| Unary vs. streaming | Call count, chunk size, message count | Throughput, memory/stream, latency |
| Concurrency | Number of clients and concurrent RPCs | CPU saturation, GC, queueing |
| Realistic TLS/compression | Production configuration | End-to-end latency and CPU |

Performance tests must warm up the JVM and connections before sampling; run long enough to reduce initial JIT/GC noise. Use the same payload distribution, call count, and environment across comparisons. Do not compare a local run against a cluster run and attribute the entire difference to Protobuf.

## 12. Practice exercise

`OrderService` receives requests containing a list of 5,000 items, product descriptions as `string`, and receipt images as Base64. Server CPU is high, GC pauses are increasing, and p99 latency exceeds the target. The team is considering enabling compression and switching to streaming.

**Tasks:**

1. Measure the serialized size and allocation of the current request; separate encode, decode, and end-to-end RPC costs.
2. Evaluate migrating receipt images from Base64 `string` to `bytes`; identify where copies are still being created.
3. Analyze the 5,000-element `repeated` field and the feasibility of batching or stream chunking.
4. Benchmark compression with realistic payloads, comparing CPU, wire bytes, and p99 latency.
5. Use JMH for the codec and JFR/profiler for the server; keep workload and payload distribution stable.
6. Set limits on message size, element count, chunk size, and concurrency to protect the heap.
7. Verify wire compatibility and legacy clients before changing the schema.

**Self-check questions:**

- How does serialization/deserialization differ from network latency?
- Why can Protobuf messages with the same number of fields have different wire sizes?
- When can `sint32` be more efficient than `int32`?
- Why can calling `toByteArray()` on a hot path increase allocation?
- How can compression reduce bytes transmitted yet increase CPU?
- Does streaming automatically reduce parsing cost?
- Why is it necessary to measure p95/p99 and allocation rather than only average time?
- In what ways can a JMH codec benchmark not replace an end-to-end RPC benchmark?

**Key takeaway:** Serialization and deserialization costs depend on schema, field values, payload size, allocation, and copying in Java. Protobuf is usually compact but not free; compression trades CPU for network bytes, while streaming changes how load is split and memory is managed. In Spring gRPC, measure the codec in isolation and the RPC end-to-end with realistic payloads, profile CPU/GC, and optimize one variable at a time while preserving wire compatibility and resource limits.
