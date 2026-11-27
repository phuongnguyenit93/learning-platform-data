# Optimizing Serialization, Data Compression, and Payload Size

In serverless applications, a request or event often crosses multiple boundaries: client, API Gateway, Java function, queue, event bus, database, and other services. Every time data crosses a boundary, the system may have to serialize objects into bytes, transmit them over the network, deserialize them on the receiving side, and allocate extra memory. Larger payloads increase transmission time, serialization CPU, memory allocation, and storage/transfer costs.

Payload optimization is not just compressing JSON. Development teams need to choose the exact data to send, the right format, a safe serialization method, a strategy for large data transfers, and a compression policy backed by measurements. Smaller payloads can cut network latency, yet overly aggressive compression burns CPU, increasing invocation duration or lengthening processing time.

This lesson explains how to design lean DTOs and event payloads, choose between JSON/Avro/Protobuf, optimize Jackson, apply gzip or Brotli in the right places, handle large data via object storage with the event reference pattern, and measure impact on serverless Java.

## Learning Objectives

After this lesson, you will be able to:

- Explain serialization, deserialization, and how payload size affects latency, CPU, memory, and cost.
- Design DTOs containing only the data required for each API or event contract.
- Choose JSON, Avro, Protobuf, or binary formats based on interoperability and schema requirements.
- Optimize Jackson safely without altering data semantics.
- Compress HTTP requests/responses and messages using gzip or another appropriate algorithm.
- Use content negotiation and proper headers for HTTP compression.
- Recognize when not to compress and how to set thresholds based on benchmarks.
- Handle binary/large payloads using object storage and the event reference pattern.
- Enforce size limits, decompression ratios, and memory bounds when receiving untrusted payloads.
- Measure serialization duration, compressed size, network time, and end-to-end latency.
- Test schema compatibility, backward compatibility, and performance before release.

## 1. How Does Serialization Affect Serverless Performance?

**Serialization** converts an in-memory object into a form that can be transmitted or stored—typically JSON, Protobuf, Avro, or raw bytes. **Deserialization** performs the reverse to reconstruct objects for the application.

An HTTP request may pass through:

~~~mermaid
flowchart LR
    A["Java object / DTO"] --> B["Serialize"]
    B --> C["Payload bytes"]
    C --> D["Network / Gateway"]
    D --> E["Payload bytes"]
    E --> F["Deserialize"]
    F --> G["Java DTO"]
~~~

Processing time for a request can include:

- Selecting and mapping data into a DTO.
- Serializing the DTO into bytes.
- Compressing the payload if configured.
- Transmitting bytes over the network or broker.
- Decompressing at the consumer.
- Deserializing bytes into a DTO.
- Validating the schema and converting into a domain model.

Large payloads can cause the following impacts:

| Impact | Why It Happens |
|---|---|
| Higher network latency | More bytes must travel across gateways, brokers, and services |
| Higher CPU usage | Serializing, parsing, and compressing require CPU |
| Memory pressure | Buffers, byte arrays, and object graphs occupy heap |
| Increased GC | Many temporary objects/strings are allocated and collected |
| Heavier cold start | Initializing libraries or processing large payloads adds upfront work |
| Expensive retries | Large messages must be retransmitted/stored multiple times |
| Higher cost | Network egress, logs, storage, and request processing may increase |

Not every large payload benefits from compression. If the data is a JPEG image, video, or ZIP file, it is already compressed, and applying gzip again may only burn CPU with almost zero byte reduction.

### A Simple Cost Model

Transfer time depends on payload size and effective bandwidth:

~~~text
Transfer time ≈ payload bytes / effective bandwidth
~~~

This is only an idealized estimate; real transfers also involve TLS, round trips, congestion, queuing, gateway overhead, and throughput limits. Compression reduces byte count while adding CPU time for compression and decompression.

Therefore, compare total time:

~~~text
Total time =
  serialization
  + compression
  + network transfer
  + decompression
  + deserialization
  + application processing
~~~

Do not evaluate optimizations solely by percentage byte reduction. What matters is end-to-end latency, throughput, memory, and total flow cost.

## 2. Payload Design: Send Only What the Consumer Needs

Often the most effective way to shrink a payload is to drop unneeded data before serializing.

A common mistake is serializing a database entity or domain aggregate directly. That object may contain:
- Nested relationships the consumer never uses.
- Lazy-loaded collections that trigger extra queries.
- Internal fields or sensitive information.
- Unneeded audit metadata.
- Heavy data such as history lists, images, or files.
- ORM- or framework-coupled structures.

Instead, create purpose-built DTOs.

### Entities and DTOs Have Different Responsibilities

For example, an internal entity might hold detailed fields:

~~~java
public class OrderEntity {
    private String id;
    private String customerId;
    private String internalNote;
    private String paymentToken;
    private List<OrderLineEntity> lines;
    private List<OrderAuditEntity> auditHistory;
    private CustomerEntity customer;
    // ORM mapping and persistence methods
}
~~~

Do not serialize this object directly for an API or event. A public DTO might retain only the required fields:

~~~java
import java.util.List;

public record OrderSummaryResponse(
        String orderId,
        String status,
        long totalAmount,
        String currency,
        List<OrderLineResponse> lines) {
}

public record OrderLineResponse(
        String sku,
        int quantity) {
}
~~~

DTOs help control:
- Which fields are allowed to leave the service.
- Which fields are required in the contract.
- Whether data should be flattened.
- Version/schema evolution.
- Response size and sensitive data exposure.

Do not force a single DTO across every endpoint when each consumer needs a different dataset. A detail API may need more fields than a list API; an `OrderPlaced` event may only need a minimal snapshot for consumers to do their work.

### Use Projections and Pagination

If an API only needs a list of orders, do not load the entire history and relationships only to strip fields in a mapper. Use a database projection/query that fetches only the required columns.

For large collections:
- Use pagination or cursors.
- Enforce a maximum page size.
- Return only needed fields.
- Provide a detail endpoint for data fetched on demand.
- Avoid returning an array of tens of thousands of items in a single response.

Pagination reduces the size of each response and helps bound memory. Cursor pagination is generally more stable than offset pagination on continuously changing datasets, depending on sorting and indexes.

### Do Not Shrink Payloads to the Point of Obscurity

Shortening field names from `customerId` to `c` may save a few JSON bytes while making contracts hard to read and evolve. Compression usually shrinks repeated key names substantially. Prefer clear schemas, tailored DTOs, and measured compression over arbitrary field-name encoding.

## 3. Choosing a Serialization Format

No single format is best for every flow. The decision depends on interoperability, schema evolution, size, encode/decode speed, and tooling.

| Format | Advantages | Limitations | Best Fit |
|---|---|---|---|
| JSON | Human-readable, ubiquitous, broad support | Repeated field names, payloads typically larger than binary | HTTP APIs, webhooks, cross-language integrations |
| Protobuf | Compact binary, explicit schema, code generation | Requires schema management, not directly readable | Service-to-service, gRPC, high-throughput events |
| Avro | Schema evolution and writer/reader schemas | Requires schema distribution or registry | Event streaming, data pipelines |
| CBOR | Binary representation of data structures | Less common than JSON in some ecosystems | IoT or environments needing binary representation |
| Java native serialization | Direct integration with legacy Java objects | Java coupling, hard versioning, deserialization risks | Avoid for new APIs/messages |

### JSON

JSON fits well when an API must interoperate with browsers, mobile apps, webhooks, or multiple languages. Using JSON does not mean serializing every field of an internal object.

Prefer clear DTOs, data types with stable semantics, well-defined optional fields, schema validation at boundaries, and excluding confidential data.

### Protobuf

Protobuf uses field numbers in its wire format, so payloads are typically small and decode efficiently. However, keep field numbers stable and never reuse deleted numbers. Consumers must handle unknown fields according to runtime and contract rules.

Example:

~~~protobuf
syntax = "proto3";

message OrderSummary {
  string order_id = 1;
  string status = 2;
  int64 total_amount_minor = 3;
  string currency = 4;
}
~~~

The name `total_amount_minor` expresses money in the currency's smallest unit, such as cents or whole currency units per the contract. Do not write just `amount` if consumers could misinterpret the unit. For VND, clearly specify whether whole dong or scaled units are used.

### Avro

Avro uses schemas during both writing and reading; reader/writer schema resolution supports data evolution. If consumers need to read older messages, older schemas must remain available and defaults must reflect accurate semantics.

### Avoid Java Native Serialization for Event Contracts

Java native serialization couples payloads to Java class structures and the Java runtime, hinders cross-system interoperability, and breaks easily when classes change. Deserializing untrusted objects can also introduce severe security risks via gadget chains. For HTTP and message brokers, use explicit schema-based formats like JSON, Avro, or Protobuf and validate inputs.

## 4. Optimizing JSON with Jackson

Jackson is a widely used Java library for JSON serialization/deserialization. Optimization should focus on DTOs, explicit configuration, and reusing ObjectMapper.

### Reuse ObjectMapper

Do not create a new ObjectMapper per request. Configure a shared mapper during initialization and do not mutate its configuration while handling requests.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonSupport {
    private JsonSupport() {
    }

    public static ObjectMapper createMapper() {
        return new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }
}
~~~

Once configured, an ObjectMapper can be safely reused across threads. If using Spring Boot, the framework typically manages the mapper; there is no need to instantiate another unless custom serializer settings are required.

### Serialize Only Necessary Fields

You can use `@JsonInclude` to omit null fields if the contract permits:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CustomerSummary(
        String customerId,
        String displayName,
        String optionalPhone) {
}
~~~

Omit nulls only when consumers treat an omitted field identically to an explicit null. In some contracts, null carries distinct semantics such as clearing a value or unknown state; stripping it automatically can alter semantics.

Do not apply `NON_EMPTY` globally if empty strings or empty collections carry business meaning.

### Avoid Unintended ORM Relationship Serialization

Entities with lazy relationships can trigger N+1 queries during serialization or cause circular references. Map to DTOs in the service/application layer using projection queries. Avoid letting the JSON serializer decide when to hit the database.

### Dates, Times, and Decimals

- Use ISO-8601/UTC for timestamps when the contract requires an instant in time.
- Distinguish `Instant`, `LocalDate`, and `LocalDateTime`; they do not share timezone semantics.
- For money, use integer minor units or decimal strings per the contract to avoid floating-point precision loss.
- Do not convert money to `double` just to shrink payloads.
- Specify scale, rounding, and currency clearly.

### Streaming Instead of Buffering Entire Payloads

For large payloads that must still be processed in a single request, streaming can reduce peak memory compared to serializing the entire payload into a byte array. Jackson supports writing JSON to an OutputStream:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.OutputStream;

public final class JsonWriter {
    private final ObjectMapper mapper;

    public JsonWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(Object value, OutputStream output) throws Exception {
        try (JsonGenerator generator =
                     mapper.getFactory().createGenerator(output)) {
            mapper.writeValue(generator, value);
        }
    }
}
~~~

This snippet assumes the method owns the output stream; if the framework manages the stream, do not close the stream here—manage only the generator according to the appropriate lifecycle. In serverless HTTP, response streaming depends on gateway/runtime capabilities, and not all integrations support response streaming.

Streaming avoids holding the entire serialized payload on the heap, but it does not eliminate gateway or broker payload limits. If the consumer needs the entire document before processing, streaming at the producer does not necessarily reduce memory at the consumer.

## 5. Measure Serialization Before Optimizing

Do not guess which serializer is faster. Build benchmarks with production-like objects and payloads.

Measure at least:
- Serialization duration.
- Deserialization duration.
- Byte size before compression.
- Byte size after compression.
- Peak memory/allocation if profiling tools are available.
- CPU time or CPU utilization under load.
- End-to-end latency and throughput.

A simple measurement in Java:

~~~java
long started = System.nanoTime();
byte[] json = objectMapper.writeValueAsBytes(response);
long serializeNanos = System.nanoTime() - started;

long payloadBytes = json.length;
~~~

This code illustrates a single measurement; never draw performance conclusions from one sample. Benchmarks need JVM warm-up, many iterations, representative data, and separation of microbenchmarks from network/load tests. For Java microbenchmarks, JMH is more appropriate than hand-rolled loops because it handles warm-up, dead-code elimination, and measurement harnesses.

### Calculating Size Reduction Ratio

~~~text
Compression ratio = compressed bytes / original bytes
Size reduction (%) = (1 - compression ratio) × 100
~~~

For example, 200 KB of JSON compressed to 40 KB:
- Compression ratio = 0.20.
- Size reduction = 80%.

Byte reduction ratio does not reflect CPU cost. Measure compression/decompression time and p95/p99 as well.

### Compare on Identical Data

When comparing JSON vs. Protobuf or gzip vs. uncompressed:
- Use the same logical data.
- Use the same schema/semantics.
- Measure both encode and decode.
- Use the same hardware/runtime and JVM options.
- Run sufficient warm-up and measurement iterations.
- Record payload size and duration.
- Verify the outputs are data-equivalent.

Do not compare gzipped JSON against uncompressed Protobuf and conclude Protobuf is always better. Comparisons must reflect the real pipeline.

## 6. Data Compression: gzip, Brotli, and Algorithm Selection

Compression shrinks the bytes that must be transmitted or stored. Common formats:

| Algorithm | Characteristics | When to Use |
|---|---|---|
| gzip/DEFLATE | Broad compatibility, well supported in HTTP and Java | JSON/text APIs, repetitive message payloads |
| Brotli | Usually compresses text/web well, multiple quality levels and CPU trade-offs | Web responses when client/gateway supports it |
| Zstandard (zstd) | Flexible speed and compression ratio, common in data pipelines | Service-to-service or event pipelines with support |
| No compression | Zero compression/decompression CPU cost | Small payloads or already-compressed data |

Do not pick an algorithm based solely on maximum compression ratio. Higher compression levels typically cost more CPU and can raise latency. Benchmark on real payload types.

### When Does Compression Help?

Compression usually helps with JSON having many repeated keys/values, XML or text logs, large payloads over slow networks, and large frequently downloaded responses.

Compression usually offers little benefit for JPEG, PNG, WebP, MP4, ZIP, gzip, or already-compressed files; very small payloads; random or encrypted data; or flows requiring ultra-low latency with tight CPU budgets.

### Setting a Compression Threshold

There is no universal byte threshold for every service. You can start benchmarking across sizes such as 1 KB, 4 KB, 16 KB, and 64 KB, then set the threshold based on payload size, CPU/memory allocation, actual compression ratio, latency budget, bandwidth, and network cost.

Compress only when measured gains outweigh CPU and overhead costs. Skip compression when payloads fall below the threshold or when the content type does not compress effectively.

## 7. gzip Compression in Java

Java provides `GZIPOutputStream` and `GZIPInputStream`. The example below compresses a payload already in memory; use only for size-bounded payloads.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

public final class GzipCompression {
    private GzipCompression() {
    }

    public static byte[] compress(byte[] input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(input);
        }

        return output.toByteArray();
    }
}
~~~

Decompression:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;

public final class GzipDecompression {
    private GzipDecompression() {
    }

    public static byte[] decompress(byte[] compressed) throws IOException {
        try (GZIPInputStream gzip = new GZIPInputStream(
                     new ByteArrayInputStream(compressed));
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            byte[] buffer = new byte[8192];
            int read;
            while ((read = gzip.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }

            return output.toByteArray();
        }
    }
}
~~~

This is a minimal example for small, trusted data. For payloads arriving from untrusted clients or brokers, never decompress unbounded data into memory. Limit decompressed byte count, processing time, and the decompressed/compressed ratio to defend against decompression bombs.

### Streaming Compression

For large data, pipe the compressed stream directly into the destination stream instead of holding input, compressed bytes, and output on the heap at the same time.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.zip.GZIPOutputStream;

public final class GzipStreaming {
    private GzipStreaming() {
    }

    public static void compress(
            InputStream input,
            OutputStream destination) throws IOException {

        try (GZIPOutputStream gzip = new GZIPOutputStream(destination)) {
            input.transferTo(gzip);
        }
    }
}
~~~

If the framework or caller owns destination, closing GZIPOutputStream will close destination. If you need to keep destination open, wrap it in a non-closing stream or manage the lifecycle explicitly. Streaming is effective only when both source and destination truly support streaming; if an SDK or gateway buffers the whole body, memory usage can still spike.

## 8. HTTP Content Negotiation and Headers

HTTP compression requires agreement between client and server. The client advertises supported encodings via `Accept-Encoding`; the server selects an appropriate encoding and declares it in `Content-Encoding`.

Client request:

~~~http
GET /api/orders HTTP/1.1
Accept: application/json
Accept-Encoding: gzip, br
~~~

Gzip-compressed response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
Content-Length: 842
~~~

Key headers:

| Header | Role |
|---|---|
| `Accept-Encoding` | Client lists content codings it can accept |
| `Content-Encoding` | Encoding applied to the representation, e.g., gzip |
| `Content-Type` | Data type after decompression, e.g., application/json |
| `Vary: Accept-Encoding` | Caches distinguish representations by encoding |
| `Content-Length` | Byte length of the transmitted body after content encoding, if known upfront |

If the response is compressed, Content-Length must be the compressed byte length. If streaming without knowing the length upfront, do not set the old Content-Length; let the server/framework choose the appropriate framing mechanism.

### Clients Not Supporting an Encoding

The server should not send gzip if the client does not accept that encoding. `Accept-Encoding` may carry quality values such as `gzip;q=1, br;q=0.8`. HTTP libraries/frameworks normally handle negotiation; if implementing manually, parse the header accurately and fall back to identity when permitted.

### Caching and Vary

If the same URL serves both gzip and identity responses, intermediate caches must know the representation depends on `Accept-Encoding`. The `Vary: Accept-Encoding` header helps caches pick the right variant. Without it, a client may receive raw gzip bytes without knowing to decompress, or a cache may serve the wrong representation.

### Avoid Double Compression

If an API Gateway, load balancer, CDN, or framework already compresses the response, do not compress it again in the handler. Double compression rarely helps and wastes CPU. Assign a single owner for compression and inspect headers on the final response.

## 9. Request and Response Compression in Spring Boot

Spring Boot can configure HTTP response compression via server settings. Example:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - application/json
      - application/xml
      - text/html
      - text/plain
    min-response-size: 2KB
~~~

Exact configuration depends on the embedded server and Spring Boot version. Verify the active server, content types, and actual response headers. `min-response-size` is an illustrative threshold; benchmark to choose a value.

If a gateway/CDN already compresses responses, decide on compression at a single layer. For request compression, the server must support reading `Content-Encoding` and decompressing before parsing the body; configuring response compression does not automatically mean request bodies are decompressed.

### Handling Content-Encoding in an Adapter

An HTTP adapter can:
1. Read `Content-Encoding`.
2. Accept only supported encodings.
3. Bound compressed body size before decompressing.
4. Decompress with decompressed-byte limits and deadlines.
5. Parse JSON and validate schema.
6. Return appropriate 400/413/415 errors if encoding or payload is invalid.

Do not blindly trust the `Content-Length` header because requests can be chunked or the header may be inaccurate. Enforce actual byte limits while reading the stream.

## 10. Payload Budgets for HTTP and Serverless Triggers

Each platform and integration has its own limits for requests/responses, invocation payloads, messages, or events. Limits can vary by API type, trigger, region, account quota, and product version. Before finalizing a payload contract, verify current limits along your exact path: client → gateway → function, producer → broker → consumer, and function → downstream service.

Do not design assuming every service allows the same body size. A payload valid at API Gateway may exceed an event source or downstream SDK limit.

### Setting a Payload Budget

Example internal budget:

| Payload Type | Illustrative Design Target | Action When Exceeded |
|---|---:|---|
| HTTP response list | ≤ 100 KB | Pagination or field selection |
| HTTP request JSON | ≤ 256 KB | Reject with 413 or move upload to object storage |
| Event message | ≤ 64 KB | Trim event or send object reference |
| Metadata | ≤ 8 KB | Remove repeated fields and unneeded data |

These are illustrative design targets, not AWS or Google Cloud product limits. Choose budgets sufficiently below platform limits to leave room for envelopes, encoding, and contract evolution.

### Multi-Layer Limits

Account for:
- HTTP body before and after compression.
- API Gateway or event source envelopes.
- Base64 expansion if binary is encoded as text.
- Message attributes/headers.
- Retry, batching, and DLQ behavior.
- Response size after serialization.
- Buffers and memory when an SDK reads the entire body.

If a trigger delivers batches of multiple messages, total batch payload may exceed limits even when each individual message is small.

## 11. Base64 and Binary Payloads

Base64 encodes bytes into ASCII characters for transmission over text-only channels. It increases size by roughly one-third before envelope/JSON overhead.

For an N-byte input, Base64 typically requires roughly:

~~~text
Encoded size ≈ 4 × ceil(N / 3)
~~~

For example, a 3 MB binary becomes roughly 4 MB in Base64, excluding JSON field names and metadata.

Do not Base64-encode large files just to stuff them into a JSON event. Use binary HTTP uploads when supported by gateway/clients, multipart uploads, time-limited presigned URLs, or direct uploads to object storage. After uploading, the producer emits an event containing the object reference.

With API Gateway/Lambda or serverless adapters, binary payload handling may follow specific rules. Verify binary media types, encoding settings, and body limits for each integration.

## 12. Large Payloads: The Object Storage Pointer Pattern

When a large payload exceeds message budgets, a common pattern is storing the bytes in object storage and sending a small event containing a reference.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Object storage
    participant Q as Queue / Event bus
    participant C as Consumer function
    P->>S: Upload object
    S-->>P: Object key / version
    P->>Q: Publish event with reference
    Q->>C: Deliver small event
    C->>S: Get object using workload identity
    S-->>C: Stream object bytes
    C->>C: Process and record result
~~~

The reference event can contain:

~~~json
{
  "eventId": "evt-1042",
  "eventType": "com.example.document.uploaded",
  "schemaVersion": "1.0",
  "data": {
    "bucket": "orders-documents",
    "objectKey": "prod/2026/11/doc-1042.json",
    "objectVersion": "v-17",
    "contentType": "application/json",
    "contentLength": 5242880,
    "checksumSha256": "..."
  }
}
~~~

The consumer uses its runtime identity to read the exact object. When using object keys, ensure:
- Keys or versions cannot be overwritten unintentionally.
- A checksum is included to verify contents.
- IAM allows reading only the intended bucket/prefix.
- Object retention is long enough for retries/replays.
- A lifecycle policy cleans up objects once no longer needed.
- Event and object creation happen in a controlled order.
- Failures where object upload succeeds but event publishing fails are handled.

Do not embed access keys or long-lived credentials in events. If using presigned URLs, restrict expiration and permissions, and avoid logging URLs; for internal consumers, workload identity is usually easier to audit.

### Handling Consistency and Orphan Objects

A producer may upload an object successfully yet fail to publish the event, leaving an orphan object. You can record upload/publish status metadata in a database, use an outbox to retry event publishing, apply lifecycle cleanup for unreferenced objects after a safe grace period, and use immutable object keys tied to the business operation.

A consumer might receive an event before the object is readable if the event was published too early or a specific integration has different consistency semantics than expected. Design bounded retries and verify storage semantics; do not assume every GetObject error is permanent.

## 13. Compressing Events/Messages

Message compression can reduce stored and transmitted bytes, provided brokers and consumers agree on the encoding.

A message envelope can carry metadata:

~~~json
{
  "eventId": "evt-2001",
  "eventType": "com.example.report.generated",
  "schemaVersion": "1.0",
  "contentEncoding": "gzip",
  "contentType": "application/json",
  "payload": "<compressed bytes encoded according to transport contract>"
}
~~~

`payload` in the example is a placeholder describing the contract, not a literal string to publish. If the broker only accepts text JSON, compressed bytes usually must be Base64-encoded, adding roughly one-third to size. Check total size after Base64 and the envelope; compressing first and Base64-encoding does not guarantee the final payload is smaller than the original JSON in all cases.

If the broker supports binary message bodies, you can send compressed bytes directly and store encoding/content type in message attributes or an outer envelope. All consumers must understand the same contract. Never change the encoding of an event still read by older consumers without a migration plan.

### Batching

Batching can reduce per-message overhead and increase throughput, however:
- Total batch size must stay within trigger/broker limits.
- One failing message may affect the whole batch depending on acknowledgment semantics.
- Use partial batch responses if supported by the platform and the consumer wants to retry only failed items.
- Measure per-message processing and batch duration separately.
- Avoid oversized batches that raise memory/cold starts or delay acknowledgments.

Compressing a batch sometimes achieves better ratios than compressing individual messages due to repeated fields, but it reduces independent processing/retry granularity and forces consumers to decompress the whole batch. Use it only when semantics and failure models permit.

## 14. Safety When Receiving Payloads and Decompressing

Payloads from clients, webhooks, queues, or event buses may be malformed or intentionally crafted to exhaust resources.

### Size Limits

- Bound compressed body size before buffering the entire body.
- Bound decompressed bytes during decompression.
- Bound nesting depth, collection length, and string length per schema.
- Enforce timeouts/deadlines for parsing and validation.
- Bound batch size and concurrency.
- Reject payloads exceeding limits before constructing large object graphs.

### Decompression Bombs

A tiny compressed payload can expand into massive data. Never check only compressed length; count actual bytes while reading the decompressed stream and abort if the limit is exceeded.

Example wrapper counting decompressed bytes for use in an adapter:

~~~java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class LimitedInputStream extends FilterInputStream {
    private final long maxBytes;
    private long count;

    public LimitedInputStream(InputStream input, long maxBytes) {
        super(input);
        if (maxBytes <= 0) {
            throw new IllegalArgumentException("maxBytes must be positive");
        }
        this.maxBytes = maxBytes;
    }

    @Override
    public int read() throws IOException {
        int value = super.read();
        if (value != -1) {
            add(1);
        }
        return value;
    }

    @Override
    public int read(byte[] buffer, int offset, int length)
            throws IOException {
        int read = super.read(buffer, offset, length);
        if (read > 0) {
            add(read);
        }
        return read;
    }

    private void add(int bytes) throws IOException {
        count += bytes;
        if (count > maxBytes) {
            throw new IOException("decompressed payload exceeds limit");
        }
    }
}
~~~

Wrap `GZIPInputStream` to count decompressed bytes:

~~~java
try (var file = Files.newInputStream(path);
     var gzip = new GZIPInputStream(file);
     var limited = new LimitedInputStream(gzip, 10L * 1024 * 1024)) {
    // Parse from limited stream; stop if exceeding 10 MiB.
}
~~~

This example enforces a byte count limit; real applications also need timeouts, nesting/object count limits, and proper exception handling. If a parser does not read the stream to completion, you cannot guarantee the payload stayed within total limits; ensure full consumption or control parser lifecycle.

### Do Not Trust Client MIME Types

Clients can declare `Content-Type: application/json` while sending arbitrary bytes. Validate actual encoding, content type, and schema. For file uploads, use an allowlist of file types and inspect contents according to business rules.

### Compression Side-Channels

Compressing responses can create side-channel risks in scenarios where a response combines secrets and attacker-controlled data inside the same compression context. If an endpoint reflects input alongside secrets in the same response, evaluate BREACH-style risks; disable compression on sensitive responses or separate the data/responses by design.

Do not log compressed bodies or secrets for debugging. Use correlation IDs and sanitized metadata.

## 15. Compression, CPU, and Serverless Cost

Serverless typically bills by resources and execution duration according to the provider's model. Compression shrinks network bytes while increasing CPU usage and potentially extending invocation duration.

| Scenario | How Compression Can Help | What to Measure |
|---|---|---|
| Large JSON, many repeated fields | Reduces network and message bytes | Compression/decompression CPU, p95 |
| Small payloads | Low byte savings | Header/CPU overhead |
| Already-compressed images/ZIPs | Minimal further reduction | CPU rises while bytes barely change |
| CPU-bound functions | May increase duration | CPU utilization and execution time |
| Network-bound | Can reduce end-to-end latency | Transfer duration and throughput |
| Large queue backlogs | Can reduce storage/transfer | Consumer CPU and batch throughput |

If a function is CPU-limited, high compression levels can degrade p99. If the network link is slow and payloads are large, gzip can improve end-to-end latency despite extra CPU.

Do not optimize a single function's cost if it shifts costs to other producers/consumers. Measure combined producer + broker + consumer and network egress.

### Choosing Compression Level

Gzip offers compression levels trading off speed vs. ratio. Higher levels generally consume more CPU. Benchmark the default level, a low speed-focused level, and a high size-focused level. Do not default to the highest level for all requests. Skip compression on small responses; for large batches or text files, higher levels may make sense when CPU headroom exists and bandwidth is the bottleneck.

## 16. Observing Serialization and Payloads in Production

Useful metrics:

| Metric | Meaning |
|---|---|
| `serialization.duration` | Time to serialize objects |
| `deserialization.duration` | Time to parse payloads |
| `payload.bytes` | Size before compression |
| `payload.compressed_bytes` | Size after compression |
| `compression.duration` | Time spent compressing |
| `decompression.duration` | Time spent decompressing |
| `compression.ratio` | Compressed/original size |
| `payload.rejected_total` | Count of payloads exceeding limits or invalid format |
| `queue.message.age` | Message age when received by consumer |
| `http.response.size` | Response size |

Metric labels should stay low-cardinality, such as content type, encoding, route template, event type, and outcome. Do not put object keys, customer IDs, request IDs, or full checksums into labels.

### Structured Logging

Log essential metadata:
- Event type/schema version.
- Payload size and compressed size.
- Encoding.
- Duration.
- Correlation/trace ID.
- Validation result or error category.

Do not log full payloads by default. If debugging is needed, use anonymized fixtures in test environments.

### Tracing

You can create dedicated spans:
- `payload.serialize`
- `payload.compress`
- `http.client.send`
- `payload.decompress`
- `payload.deserialize`
- `object_storage.get`

Traces reveal how much of root latency comes from CPU/serialization and whether it overlaps with networking. Do not create spans per field; keep spans at meaningful boundaries.

## 17. Testing Size, Compatibility, and Performance

A test verifying only that an object deserializes is insufficient. Test payloads across multiple sizes and schema versions.

### Unit Tests

- DTOs contain only permitted fields.
- Null/empty fields conform to the contract.
- JSON serialization produces expected field names, types, and timestamp formats.
- Gzip output decompresses and restores equivalent data.
- Over-limit payloads are rejected.
- Unknown fields/enums follow policy.
- Binary/base64 payloads remain within budget after encoding.

### Contract Tests

- Producer serializes according to the published schema version.
- New consumers read old schema fixtures.
- Old consumers ignore new fields if required by the contract.
- Protobuf field numbers are never reused.
- Avro reader defaults carry valid semantics.
- Event compression metadata matches actual bytes.
- Object reference events contain valid keys/versions/checksums.

### Performance Tests

Run scenarios for:
- Payloads of 1 KB, 10 KB, 100 KB, and near-budget sizes.
- Uncompressed JSON vs. gzip.
- JSON vs. Protobuf/Avro if used.
- Warm JVM and cold starts.
- Low and high concurrency.
- Compressible and incompressible payloads.
- Small and large batches.
- Consumers decompressing/parsing under retries.

Record p50/p95/p99, throughput, CPU, memory allocation, GC, and bytes transferred. Run identical workloads before and after changes.

### Example gzip Round-Trip Test

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import org.junit.jupiter.api.Test;

class GzipCompressionTest {
    @Test
    void restoresOriginalBytes() throws Exception {
        byte[] original = ("orderId,status,currency\n"
                + "ord-1,CONFIRMED,VND\n").repeat(100).getBytes(
                        java.nio.charset.StandardCharsets.UTF_8);

        byte[] compressed = GzipCompression.compress(original);
        byte[] restored = GzipDecompression.decompress(compressed);

        assertArrayEquals(original, restored);
        org.junit.jupiter.api.Assertions.assertTrue(
                compressed.length < original.length);
    }
}
~~~

The assertion that compressed is smaller than original holds only for repetitive fixtures like this example. Do not expect that for every payload; random or already-compressed data may not shrink.

## 18. Payload Optimization Workflow

A practical workflow:

1. Measure baseline: payload bytes, serialization duration, network latency, CPU, memory, and p95/p99.
2. Identify redundant fields: review API/event contracts and what consumers actually use.
3. Build DTOs/projections: fetch only needed data and apply pagination.
4. Choose format: keep JSON when interoperability matters; evaluate Protobuf/Avro for suitable flows.
5. Benchmark compression: compare gzip/Brotli/zstd by payload and runtime.
6. Set thresholds and payload budgets: base them on platform limits and SLOs.
7. Add validation/limits: compressed bytes, decompressed bytes, nesting, timeouts.
8. Verify compatibility: old/new consumers, DLQ, and replays.
9. Canary release: monitor bytes, CPU, p95/p99, errors, and cost.
10. Keep a rollback path: consumers can still read previously published messages.

Do not change serialization format and schema simultaneously without a migration plan. When switching from JSON to Protobuf, use content types/schema IDs and support both formats on consumers during the transition, or introduce a new route/topic version.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Serializing ORM entities directly | Bloated payloads, exposed internal fields, N+1 queries | Use DTOs and projections |
| Compressing every payload | Higher CPU, small payloads see no gain | Benchmark and set thresholds |
| Re-compressing images/ZIPs | Wastes CPU with negligible byte savings | Inspect content type/encoding |
| Creating ObjectMapper per request | Allocation and startup overhead | Reuse a configured mapper |
| Buffering large files into byte[] | Heap pressure and GC | Stream or use object storage |
| Base64-encoding large files into JSON | Roughly one-third size inflation | Binary upload/object reference |
| Sending huge objects over queues | Hits message limits, costly retries | Metadata + object reference |
| Stripping null/empty outside contract | Alters semantics | Define missing/null/empty behavior |
| Double compressing at handler and gateway | Wastes CPU, hard-to-handle responses | Assign a single compression owner |
| Unbounded decompression | Decompression bombs, OOM | Enforce compressed/decompressed size limits |
| Using Java native serialization for events | Tight coupling and deserialization risks | Use JSON/Avro/Protobuf |
| Measuring only compression ratio | Misses CPU/latency trade-offs | Measure end-to-end and percentiles |
| Changing schemas without compatibility tests | Old consumers fail or misbehave | Schema registry, fixtures, expand-contract |

## 20. Serialization, Compression, and Payload Checklist

- [ ] APIs/events use dedicated DTOs; ORM entities or domain aggregates are never serialized directly.
- [ ] Only fields needed by the consumer are sent.
- [ ] Pagination/projections are used for large collections.
- [ ] Schemas document required, optional, null, enum, units, and time semantics.
- [ ] Format (JSON/Avro/Protobuf) is chosen for interoperability and throughput.
- [ ] Java native serialization is not used for untrusted payloads.
- [ ] ObjectMapper is configured once and reused.
- [ ] Null/empty handling does not unintentionally alter contracts.
- [ ] Serialization/deserialization duration is measured.
- [ ] Compression is benchmarked by payload size and content type.
- [ ] HTTP uses Accept-Encoding, Content-Encoding, and Vary properly.
- [ ] Payloads are not compressed twice across layers.
- [ ] Both compressed and decompressed body sizes are bounded.
- [ ] Timeouts and parsing/nesting limits protect against untrusted payloads.
- [ ] Binary payloads are not unnecessarily Base64-encoded.
- [ ] Large payloads are stored in object storage while events carry references.
- [ ] Object references include valid keys/versions/checksums and lifecycle policies.
- [ ] Queue batch/message sizes stay within platform budgets.
- [ ] Consumers support old/new schemas and previously published encodings.
- [ ] Unit, contract, load, and cold-start tests exist.
- [ ] Bytes, CPU, memory, p95/p99, and network costs are monitored after rollout.

## Self-Check

1. Through which mechanisms can serialization and deserialization increase serverless latency?
2. Why should you not serialize ORM entities directly into API responses or events?
3. When is JSON a better fit than Protobuf, and when is a binary schema advantageous?
4. Why can you not strip all null or empty fields by default?
5. Does a good compression ratio guarantee better end-to-end latency?
6. Which headers do HTTP clients and servers use to negotiate compression?
7. Why must you enforce both compressed-size and decompressed-size limits?
8. Roughly how much does Base64 inflate a payload, and when should you use object storage?
9. What metadata does an object-reference event need for consumers to read safely and verify contents?
10. Why must retries and DLQs maintain support for older schemas/encodings?
11. When does streaming reduce memory, and why does it not automatically eliminate gateway limits?
12. Which metrics must be measured to decide whether to enable gzip on a route?

Serialization and payloads are part of the data path, so optimization must start from contracts and real consumer needs. Lean DTOs, suitable formats, thresholded compression, and streaming/object storage reduce bytes and memory; decompression limits, schema compatibility, and p95/p99 measurement keep changes safe. Retain an optimization only when measurements prove overall latency, throughput, or cost improves while business semantics remain intact.
