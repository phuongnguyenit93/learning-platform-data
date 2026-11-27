# Protobuf Message Size

The size of a Protobuf message determines how much data the application must serialize, parse, hold in memory, and transfer over gRPC. Oversized messages increase bandwidth, allocation, GC pressure, and processing time; tiny messages sent at very high frequency can incur significant per-RPC overhead. You should therefore measure size by wire format and real payloads rather than estimating from field counts or Java object size.

In Spring gRPC, generated stubs and Protobuf marshallers handle the conversion. Developers control most of the size through schema design, data types, element counts, `string`/`bytes` contents, batching strategy, and message limits. This lesson focuses on calculating wire size, reading measurements in Java, and setting safe limits for clients and servers.

## 1. Distinguishing object, Protobuf, and gRPC sizes

A request has several distinct size concepts:

| Concept | Includes | Answers |
| --- | --- | --- |
| Java object size | Object headers, references, fields, collections, and heap-allocated data | How much JVM memory does the request occupy? |
| Protobuf serialized size | Bytes in the Protobuf wire format | How many bytes does the message need after serialization? |
| gRPC message envelope | 1-byte compression flag and 4-byte message length, plus payload | How is the message framed inside the gRPC stream? |
| HTTP/2 transport bytes | DATA frame headers, stream/connection framing, TLS, and related overhead | How many bytes actually cross the transport/network? |

These metrics are not interchangeable. `getSerializedSize()` returns the Protobuf payload size, not the Java object size or total network bytes. gRPC adds framing and HTTP/2; TLS, proxies, and TCP introduce further overhead in lower layers.

In a streaming RPC, each Protobuf message is framed separately within the same HTTP/2 stream. The total data for the stream is the sum of message payloads plus framing/transport overhead, not the size of a single message.

## 2. Wire format size calculation rules

Protobuf does not send field names. Each field appears on the wire as a tag and a value. The tag is computed as:

```text
tag = (field_number << 3) | wire_type
field_size = tag_size + value_size
message_size = sum(field_size of serialized fields)
```

Tags are typically encoded as varints. Common wire types:

| Wire type | Typical data types | Value part |
| --- | --- | --- |
| `0` | `int32`, `int64`, `uint32`, `uint64`, `bool`, enum | Varint |
| `1` | `fixed64`, `sfixed64`, `double` | 8 bytes |
| `2` | `string`, `bytes`, nested message, packed repeated | Varint length + content |
| `5` | `fixed32`, `sfixed32`, `float` | 4 bytes |

Field numbers from 1 to 15 usually have a one-byte tag; field numbers 16 and above can require more bytes. For messages with frequently populated fields, assign low field numbers to important fields during initial schema design. Never change a published field number just to save one byte, as that breaks wire compatibility.

## 3. Varints, length-delimited, and packed fields

**Varint** uses a variable number of bytes depending on value magnitude. Small numbers generally take fewer bytes than large ones. `int32`/`int64` encode negative numbers as signed varints, so negative values typically require many bytes; `sint32`/`sint64` use ZigZag encoding and can be more efficient when negative numbers are common in the domain.

**Length-delimited** uses a varint representing length followed by the payload. This applies to `string`, `bytes`, nested messages, and packed repeated fields. For example, a 5-byte UTF-8 string has a value section consisting of 1 byte for length (when length is small) and 5 bytes of content.

**Packed repeated numeric** groups multiple scalars into one length-delimited region, paying the tag cost only once for the group. Proto3 uses packed encoding by default for eligible repeated scalar types. Even so, parsing still creates and stores each element in a collection; small wire size does not guarantee low heap cost.

## 4. Calculating a sample message size

Consider the schema:

```proto
syntax = "proto3";

message UploadMeta {
  int32 id = 1;
  string name = 2;
  repeated int32 parts = 3;
  bytes digest = 4;
}
```

With `id = 150`, `name = "abc"`, `parts = [1, 2, 300]`, and a 2-byte `digest`, the size breaks down as:

| Field | Components | Bytes |
| --- | --- | ---: |
| `id = 150` | 1-byte tag + 2-byte varint value | 3 |
| `name = "abc"` | Tag 1 + length 1 + 3 UTF-8 data bytes | 5 |
| `parts` packed | Tag 1 + length 1 + varint values (1 + 1 + 2) | 6 |
| `digest` | Tag 1 + length 1 + 2 data bytes | 4 |
| **Total** | Protobuf serialized payload | **18** |

This example shows that size depends on actual values, not just type declarations. If `id` is larger, the varint can take more bytes; if `name` has Unicode characters, UTF-8 byte length can exceed character count; if `parts` has more elements, both the length prefix and data change.

You do not need to compute sizes by hand in application code. This calculation helps explain why payloads vary and lets you sanity-check measurements.

## 5. Factors that make messages grow

| Factor | Effect on wire size | What to consider |
| --- | --- | --- |
| Large varint values | Uses extra bytes for the value | Choose `sint` when semantics and value distribution fit |
| Large field numbers | Tags may take more bytes | Reserve low field numbers for frequent fields in new designs |
| Long `string` | Length prefix and UTF-8 bytes grow | Enforce length limits; never use strings for binary data |
| Large `bytes` | Size roughly equals content bytes plus tag/length | Limit upload size; consider streaming |
| Nested messages | Adds tag, length prefix, and entire child message content | Avoid meaningless wrappers/nesting |
| Many `repeated` elements | Each element must be represented; packing only removes repeated tags | Bound count or split into chunks |
| Many `map` entries | Each entry is a length-delimited child message | Use maps only when key-lookup semantics are needed |
| Many fields with presence | Fields are serialized even at default values when presence is set | Keep presence only when semantics distinguish absent/default |
| Unknown fields | May be retained and re-serialized depending on API/runtime | Watch out when proxying messages across schema versions |

Proto3 scalar fields with default values normally do not appear on the wire unless presence semantics or a corresponding mechanism are used. `optional` can distinguish "not sent" from "sent as 0/empty"; this is useful for business logic but can cause the field to appear on the wire.

`oneof` represents only the selected branch. For `map`, each entry carries a key/value and the overhead of a child message; a large map can therefore consume more bytes than expected. Measure with real data before modifying schemas.

Schemas should be designed for both forward/backward compatibility and performance. Do not reuse deleted field numbers; mark removed fields `reserved` to avoid misinterpreting old data.

## 6. Measuring size with the generated Java API

Generated Protobuf messages provide `getSerializedSize()` to obtain payload size without manually summing fields:

```java
UploadMeta message = UploadMeta.newBuilder()
    .setId(150)
    .setName("abc")
    .addParts(1)
    .addParts(2)
    .addParts(300)
    .setDigest(ByteString.copyFrom(new byte[] {0x01, 0x02}))
    .build();

int protobufBytes = message.getSerializedSize();
```

For the sample message, the expected result is 18 bytes. You can verify via serialization in a unit test:

```java
byte[] encoded = message.toByteArray();

assertEquals(message.getSerializedSize(), encoded.length);
UploadMeta decoded = UploadMeta.parseFrom(encoded);
assertEquals(message, decoded);
```

`toByteArray()` allocates a new byte array, so it fits tests or measurement tools but should not be called on the hot path just to log size. In normal RPCs, the generated marshaller serializes the message automatically. If you need payload metrics, read the size from the message before sending or instrument at the codec boundary in a way that avoids a second serialization.

## 7. Message size and gRPC limits

Client and server must configure inbound message limits suited to the workload. grpc-java provides configuration such as `maxInboundMessageSize(...)` on builders; Spring gRPC starters may expose corresponding properties/customizers depending on version.

Example with grpc-java:

```java
int maxMessageBytes = 8 * 1024 * 1024;

Server server = ServerBuilder.forPort(8443)
    .maxInboundMessageSize(maxMessageBytes)
    .addService(new OrdersService())
    .build();

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .maxInboundMessageSize(maxMessageBytes)
    .useTransportSecurity()
    .build();
```

The 8 MiB value is only an example, not a universal default or recommendation. Check the API and properties of the grpc-java/starter version you use. Inbound limits protect the receiver; applications should still validate outbound payloads before sending and document contract limits for callers.

Limits typically apply per individual gRPC message, not to the total volume of an entire streaming call. A stream can carry many valid messages whose cumulative total is huge. You should therefore add per-stream/per-caller quotas, chunk count limits, deadlines, cancellation, and concurrent stream limits.

Do not raise limits indefinitely just to handle one bad payload. Large messages can allocate many objects after parsing; multiple concurrent messages can grow the heap much faster than wire size suggests.

## 8. Large messages: batch, chunk, or streaming?

When payloads exceed a reasonable limit, choose the transfer pattern based on data characteristics:

| Approach | When appropriate | Trade-offs |
| --- | --- | --- |
| Single unary message | Small/medium payload needing atomic handling and clear bounds | Simple, but the entire message must be buffered/parsed |
| Batch multiple records | Many small items that can be processed in bulk | Reduces RPC count, but increases payload and batching wait time |
| Client/server streaming | Large files, events, or lists that can be split | Requires managing ordering, backpressure, retry/resume, and cancellation |
| Out-of-band object reference | Very large files already in object storage | Shrinks gRPC payload, but adds upload/download steps and access control |

Chunk example:

```proto
message FileChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

service FileService {
  rpc Upload(stream FileChunk) returns (UploadResult);
}
```

Each chunk needs size bounds, a sequence number, and appropriate acknowledgment/completion handling. Do not collect all chunks into a list on the server if the goal is transferring large data with bounded memory. Streaming shrinks individual message size, but does not automatically cap total data or guarantee backpressure if your application builds an unbounded queue.

## 9. Compression does not change Protobuf serialized size

Compression can reduce payload bytes sent over gRPC, but it does not alter `getSerializedSize()` on the original Protobuf message. gRPC framing flags whether a message is compressed, and the transport transmits the compressed payload.

Compression is suitable when payloads are large enough and repetitive, such as text or JSON-like structures. Already compressed data, JPEG/PNG images, or archives rarely shrink further when re-compressed. Compression also consumes CPU and can add latency.

When benchmarking, record separately:

- Protobuf serialized size before compression.
- Compressed payload bytes if measurable at the transport/codec boundary.
- CPU time for encode/decode and compression/decompression.
- End-to-end latency, throughput, and p95/p99.

Do not conclude a message got "smaller" solely from network byte counts without distinguishing original payload from compressed bytes.

## 10. Memory protection and avoiding abnormal payloads

Message size is one piece of resource control. Set per-service/per-method limits and validate fields that can grow without bound:

- Length of strings, bytes, and element counts of `repeated`/`map`.
- Chunk count and total bytes within a stream.
- Concurrent RPCs/streams per caller.
- Message/stream retention time and deadlines.
- Queues between network callbacks and business workers.
- Number of copies and simultaneous retention of objects, byte arrays, and buffers.

A 4 MiB message does not occupy only 4 MiB of heap. Parsing can create a much larger object graph and collections; concurrent calls multiply that consumption. Pick limits based on heap budget, target concurrency, and payload distribution, then verify with load tests.

Do not log entire messages for debugging. For large payloads or sensitive data, log size, method, correlation ID, and non-sensitive metadata; avoid producing an extra serialized copy just for logging.

## 11. Testing size and boundaries

Tests should cover normal sizes, near-limit sizes, and over-limit sizes:

| Test case | What to verify |
| --- | --- |
| Empty/default message | Serialized size matches presence semantics |
| Small/large/negative varints | Size varies as expected with encoding |
| ASCII/Unicode strings | Measured in UTF-8 bytes, not character count |
| Bytes payload | Size equals content plus tag/length |
| Packed repeated | Tag/length and elements encode correctly |
| Nested/map/oneof | Size reflects active branch and actual entry count |
| Just under limit | Server receives and processes successfully |
| At/over limit | Verify boundary behavior and actual runtime status |
| Multiple messages in stream | Each message obeys limit; total stream has its own quota |
| Compression on/off | Distinguish serialized size from compressed bytes |
| Concurrent large calls | Heap, GC, and latency stay within budget |

Unit tests use `getSerializedSize()` and `toByteArray()`/`parseFrom()` round-trips to lock in codec behavior. Integration tests run over a real channel/server to verify inbound limits and the status returned by the runtime. Load tests must use a production-like payload distribution, not just repeat one fixed message.

## 12. Practice exercise

`OrderService` receives a unary request containing 20,000 order lines and a receipt image as `bytes`. Some requests are rejected due to message size, while raising the limit causes sharp increases in heap and GC.

**Tasks:**

1. Use `getSerializedSize()` to measure real payloads and analyze which fields contribute the most bytes.
2. Separate Protobuf serialized size, gRPC envelope, and network bytes when compression is enabled.
3. Set limits for line item count, receipt size, and total inbound message size.
4. Evaluate batching, client streaming, or object storage references for large receipts.
5. Define per-message limits and total quotas for streaming calls.
6. Write tests for under/near/over limits, Unicode strings, packed repeated fields, and concurrent large calls.
7. Use load tests to choose limits based on heap budget, concurrency, and p99 latency.

**Self-check questions:**

- Which data layer does `getSerializedSize()` measure?
- Why is field count alone not enough to predict message size?
- How is a Protobuf tag constructed from field number and wire type?
- When can `sint32` be smaller than `int32`?
- Why must Unicode strings be measured in UTF-8 bytes?
- Which overhead does packed repeated reduce, and which cost does it not reduce?
- How does a per-message limit differ from a whole-stream quota?
- Does compression change `getSerializedSize()`?

**Key takeaway:** Protobuf message size is determined by tags, wire types, values, and actual element counts. Use `getSerializedSize()` to measure the raw payload; distinguish it from gRPC framing and network bytes. Set inbound limits along with stream/concurrency quotas, consider batching/chunking for large payloads, and test boundaries before raising message limits in production.
