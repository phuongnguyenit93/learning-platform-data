# Buffer Limits, Fragmentation, and Large Payloads in RSocket

## Objectives

After this lesson, you will be able to:

- Distinguish frame size, reassembled payload size, and codec memory limits.
- Explain how RSocket fragmentation works and why fragmentation does not turn a large payload into a stream that can be processed piece by piece.
- Configure fragmentation thresholds and inbound payload limits in RSocket Java through Spring Framework.
- Choose among a single payload, protocol-level fragmentation, application-level chunking, and external storage.
- Use Reactive Streams backpressure to limit how much data is processed concurrently.

This lesson belongs to the **Spring Framework - messaging** topic, within the **RSocket Lifecycle** context. The focus is buffer limits, fragmentation, and safe transmission of large data.

## 1. Payload, Frame, and Buffer Are Three Different Concepts

RSocket transmits messages over a byte-stream connection such as TCP or WebSocket. An RSocket message has a **data** part and a **metadata** part. Metadata typically carries the route, MIME types, or routing and security information; data carries business content.

In Spring Framework, **RSocketRequester** provides a high-level API for sending and receiving objects. **RSocketStrategies** selects encoders and decoders to convert objects into data/metadata and vice versa. On the receiving side, **@MessageMapping** routes requests to handlers. Underneath those abstractions, RSocket Java operates on **Payload** and protocol frames.

Distinguish:

- **Payload** is the logical message the application sends or receives.
- **Frame** is the packaged data unit transmitted over the connection. A single payload can span one frame or multiple frames.
- **Buffer** is the memory region holding bytes during reception, reassembly, decoding, processing, or sending. Buffers may reside on the heap or in direct memory managed by the networking library.

Therefore, a 5 MB payload can be transmitted across many small frames, yet the application still receives one logical 5 MB payload after the library reassembles the fragments. Splitting into frames does not automatically reduce the data that must be buffered to decode a single payload.

## 2. Limit Layers to Check

No single parameter controls all size limits. Identify which layer raises an error before changing configuration.

| Layer | Parameter or Concept | Control Scope | Question to Answer |
|---|---|---|---|
| Transport | Maximum frame length | Frames the transport can accept | Does an individual frame exceed the transport limit? |
| RSocket fragmentation | MTU/fragment size | Threshold to split frames when sending | Does the payload need splitting into smaller frames? |
| RSocket reassembly | Maximum inbound payload size | Total payload after reassembling received fragments | What is the largest allowed logical message in bytes? |
| Spring codec | Maximum in-memory size | Data the codec must buffer to decode/encode | Does the decoder have to gather too many bytes before building an object? |
| Application | Chunk size, concurrency, queue capacity | Data and work held concurrently by the application | How many payloads/chunks are being processed at once? |

These limits are independent in purpose:

1. Lowering the MTU or enabling fragmentation lets a payload travel over the transport in multiple frames.
2. Inbound payload limits protect the step that reassembles fragments into a single logical message.
3. Codec limits protect the step that buffers and decodes data into objects.
4. Concurrency and queue limits protect total memory when multiple requests are active together.

Raising one limit does not automatically raise the others. For instance, increasing the allowed inbound payload size does not make the decoder accept a buffer larger than the decoder's own limit.

## 3. RSocket Fragmentation and Reassembly

### 3.1. Mechanism

When a payload or request frame exceeds the configured fragmentation threshold, RSocket can split it into multiple fragments for transmission. The **Follows** flag indicates whether more fragments follow the current one.

For a fragmented request:

1. The first frame still carries the original request type, such as REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL, or REQUEST_FNF.
2. Subsequent frames use PAYLOAD to continue carrying the remainder.
3. Intermediate fragments set the Follows flag. The final fragment leaves this flag unset.
4. The receiver reassembles the parts into a logical payload before passing it to the request-handling layer.

For a fragmented PAYLOAD frame, the fragment sequence consists of PAYLOAD frames. Per protocol rules, metadata is transmitted completely before the data section. Fragmentation does not change request credits: one logical payload still counts as one message toward request(n), even when sent across multiple fragments.

### 3.2. What Does Fragmentation Solve?

Fragmentation is useful when:

- A single payload is larger than the frame size you want to send.
- The transport or network infrastructure has a suitable frame threshold smaller than the payload.
- You want to avoid sending a very large frame on a byte-stream connection.

Fragmentation does not solve:

- The total size of the logical payload.
- The decoder's need to buffer data to construct a complete object.
- The application holding many large payloads simultaneously.
- Streaming a very large file so parts can be processed and released as soon as they arrive.

The receiver must still reassemble the payload. Consequently, a large payload can still consume significant memory even though individual frames are small.

### 3.3. Configuration from Spring RSocketRequester

Spring lets you customize the RSocket Java connector via the builder's **rsocketConnector** callback. The example below sets a 64 KiB fragmentation threshold and a 32 MiB reassembled inbound payload limit:

```java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector
        .fragment(64 * 1024)
        .maxInboundPayloadSize(32 * 1024 * 1024))
    .tcp("localhost", 7000);
```

These are illustrative values to explain the API, not defaults suitable for every system. Choose based on actual payload sizes, transport, concurrent connections, and memory budget.

Meaning of the two methods:

- **fragment(mtu)** sets the threshold for RSocket to split large frames into fragments when sending.
- **maxInboundPayloadSize(bytes)** sets the inbound payload size limit after reassembly. This limit applies to the logical payload, not just individual fragments.

RSocket Java requires maxInboundPayloadSize to be no smaller than the transport's maximum frame length. Otherwise, a single inbound frame could exceed the reassembly limit and the configuration would be invalid. Check the transport in use and rsocket-core version before finalizing values.

Receiving policies must be configured on both sides of the connection. For example, the client's inbound limit protects the client when receiving responses; the server's inbound limit protects the server when receiving requests. The sender's fragmentation settings must be compatible with the peer's receiving capacity.

When using Spring Boot, the builder and RSocketStrategies may be auto-configured. You can still customize the connector via callbacks or customizer mechanisms provided by your Spring Boot version. Do not assume an HTTP/WebFlux property automatically replaces limits on the RSocket transport.

## 4. Spring Codec Memory Limits

RSocket fragmentation belongs to the protocol layer. Spring codecs belong to the byte-to-object conversion layer. These two layers can produce two different kinds of errors.

Spring Core provides **DataBuffer**, **DataBufferFactory**, **DataBufferUtils**, **Encoder**, and **Decoder**. RSocketStrategies aggregates encoders/decoders used for data and metadata. Codecs may need to buffer a certain number of bytes before decoding, such as when constructing a single JSON object.

If a codec must buffer more bytes than its configured limit allows, the application may encounter:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

This error indicates that the codec's buffering operation exceeded its limit. It is not synonymous with an RSocket frame exceeding maximum frame length, nor does it by itself prove fragmentation was not enabled.

Example configuring a Jackson JSON decoder with a 4 MiB limit and registering it in RSocketStrategies:

```java
Jackson2JsonDecoder jsonDecoder = new Jackson2JsonDecoder();
jsonDecoder.setMaxInMemorySize(4 * 1024 * 1024);

RSocketStrategies strategies = RSocketStrategies.builder()
    .decoders(decoders -> decoders.add(jsonDecoder))
    .build();
```

This is a codec configuration snippet; ensure the decoder is registered in the proper order and selected for the connection's MIME type. If the application uses Spring Boot auto-configuration, you can customize RSocketStrategies via an **RSocketStrategiesCustomizer** appropriate for your version.

Do not mechanically raise codec limits. First determine:

- Which codec is decoding the payload.
- Whether the codec buffers the entire message or can decode incrementally.
- Whether the large payload comes from data or metadata.
- Whether the format can be changed or switched to streaming/chunking.
- How much memory each request and concurrent requests can consume.

A codec with a higher limit only allows a single decode to hold more bytes. It does not shrink the payload and does not control concurrent request counts.

## 5. Choosing How to Transfer Large Data

### 5.1. Using a Single Payload

Use a single payload when the data has a finite, well-bounded size and must be processed as a complete object, such as an update command or a moderately sized record.

The advantage is a simple model: encode once, send one request, decode once. The drawback is that the receiver must accept and process the entire logical payload. Do not use this approach for very large files or potentially unbounded data.

### 5.2. Using Protocol Fragmentation

Use fragmentation when you still want a single logical message but need to transmit it in smaller frames. The application continues working with one payload after reassembly.

This is a solution for frame/transport limits, not an application-level incremental streaming solution.

### 5.3. Using Application-Level Chunking

For files or large data, split the data into bounded-size chunks at the application layer. Each chunk is an independent piece of data that the receiver can validate, write to storage, and release before receiving the next part.

A practical chunk model should include:

- transferId to identify the transfer.
- sequence to determine chunk order.
- bytes containing the chunk data.
- Maximum chunk size.
- Completion indicator or total chunk count / total size if needed by the application protocol.
- Checksum to detect corrupted or missing data.
- Policies for handling duplicate chunks, out-of-order chunks, timeouts, and retries.

Example shape of a Spring RSocket handler receiving a chunk stream:

```java
@Controller
class FileUploadController {

    @MessageMapping("files.upload")
    Mono<UploadResult> upload(Flux<FileChunk> chunks) {
        return chunks
            .concatMap(chunk -> storage.append(chunk))
            .then(storage.complete());
    }
}
```

This is an illustrative skeleton; **FileChunk**, **UploadResult**, and **storage** are application-defined types/services. With a Flux input, the handler receives a stream of messages under the Request-Channel model. **concatMap** processes each chunk sequentially and preserves order. The storage API must finish writing a chunk before requesting further processing; do not collect the entire Flux into a List.

If parallel processing is needed, set bounded concurrency and ensure ordering/write safety. Do not replace concatMap with unbounded flatMap just to increase throughput.

### 5.4. Java 17 Example: Splitting and Joining a Byte Array

The following standalone example illustrates application-level chunk boundaries. It uses a small byte array to verify the algorithm; for large files in production, stream data from file or storage instead of loading the entire file into a byte array first.

Save as **PayloadChunkingDemo.java**:

```java
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PayloadChunkingDemo {

    static List<byte[]> split(byte[] source, int chunkSize) {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        List<byte[]> chunks = new ArrayList<>();
        for (int offset = 0; offset < source.length; offset += chunkSize) {
            int end = Math.min(offset + chunkSize, source.length);
            chunks.add(Arrays.copyOfRange(source, offset, end));
        }
        return chunks;
    }

    static byte[] join(List<byte[]> chunks) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        for (byte[] chunk : chunks) {
            output.write(chunk, 0, chunk.length);
        }
        return output.toByteArray();
    }

    public static void main(String[] args) {
        byte[] source = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};

        List<byte[]> chunks = split(source, 4);
        byte[] restored = join(chunks);

        System.out.println("chunks=" + chunks.size());
        System.out.println("restored=" + Arrays.equals(source, restored));
    }
}
```

Compile and run with Java 17 or newer:

```bash
javac PayloadChunkingDemo.java
java PayloadChunkingDemo
```

Exact output:

```text
chunks=3
restored=true
```

The 10-byte data is split into three chunks of 4, 4, and 2 bytes respectively. When joined in the right order, the resulting byte array matches the original data. In a file transfer application, add transferId, sequence, checksum, and error handling; the example above only verifies basic split/join logic.

### 5.5. External File Storage and Passing References

If the payload is a very large file, transfer the file through object storage or a dedicated storage service, and send a small message over RSocket containing:

- Reference ID or URI.
- Size and checksum.
- Content type.
- Access permission or time-limited token.

This approach reduces pressure on RSocket connections and service memory. Ensure proper access controls, URL expiration, data integrity, and temporary file cleanup procedures.

## 6. Backpressure and Memory Budget

RSocket supports Reactive Streams semantics for Request-Stream and Request-Channel. The receiver signals demand with request(n); the sender should emit only as many messages as downstream requested. Backpressure helps pace rates between producer and consumer.

Backpressure does not replace single-payload limits. A single message can still be huge even when demand is one. Likewise, if the application calls collectList(), cache(), block(), or pushes all chunks into an unbounded queue, the benefits of streaming are lost.

Manage both factors simultaneously:

1. Maximum size of each payload or chunk.
2. Number of payloads/chunks and requests processed concurrently.

A rough memory budget model to begin designing:

```text
Memory pressure
≈ concurrent requests
  × (reassembled payload
     + decoded object
     + temporary copies
     + queued work)
```

This is an estimation model, not an exact measurement formula. Decoded objects can be much larger than raw JSON bytes; encoders/decoders or copy operations can also allocate extra temporary regions. If using buffer pooling or direct memory, do not look only at heap usage to conclude the application has no memory pressure.

Useful practices:

- Set explicit inbound payload limits on every endpoint.
- Size chunks according to throughput, latency, and memory budget.
- Bound concurrency, prefetch, and queue capacity.
- Use reactive pipelines to process and release chunks early.
- Avoid retaining references to chunks after processing finishes.
- Monitor heap, direct memory, garbage collection, and concurrent request counts.
- Use zero-copy only when you fully understand buffer lifecycles. With PayloadDecoder.ZERO_COPY in RSocket Java, data and metadata may be retained slices of the underlying buffer; low-level processing code must release payloads promptly to avoid memory leaks.

## 7. Diagnosing Errors at the Right Layer

| Symptom | Likely Layer | How to Check |
|---|---|---|
| Frame rejected as too large | Transport/frame length | Check maximum frame length and outbound frame size. |
| Fragment reassembly error or payload exceeds limit | RSocket reassembly | Check maxInboundPayloadSize on the receiver and logical payload size. |
| DataBufferLimitException | Spring codec | Identify the active decoder/encoder and its codec buffer limit. |
| Sharp heap/direct memory growth under high load | Application, codec, or buffers | Check concurrency, queues, decoded objects, copies, and buffer lifecycles. |
| Stream slows down or stalls midway | Backpressure or downstream | Check demand, storage write speed, timeouts, cancellation, and subscriber errors. |
| Corrupted or missing reassembled data | Application-level chunking | Check transferId, sequence, checksum, final chunk, and duplicate retries. |

When investigating, record data and metadata sizes in bytes, reassembled payload size, fragment count, processing time, and concurrent request count. Do not log full payload contents if data may contain sensitive information.

## 8. Procedure for Choosing and Tuning Limits

1. Measure actual payload sizes on both sending and receiving sides; separate data from metadata where possible.
2. Identify frame limits of the active transport.
3. Choose a fragmentation threshold suited to the transport and network environment.
4. Set maxInboundPayloadSize large enough for the largest valid payload, while no smaller than the transport's maximum frame length.
5. Check the selected codec in RSocketStrategies and its buffer limit.
6. Calculate the budget across concurrent requests, decoded objects, and temporary memory.
7. If payloads are still too large to hold as one object, switch to application-level chunking or external storage.
8. Test with payloads near the limit, over the limit, high concurrency, cancellation, and mid-transfer disconnections.
9. Observe heap, direct memory, latency, throughput, and decode errors under realistic load.

Do not set every limit to a huge value or remove limits altogether. Limits are part of the contract between producer and consumer, and serve as a resource guardrail.

## 9. Common Misconceptions

- **Enabling fragmentation is enough to send files of any size.** False: the receiver still reassembles the payload and needs enough memory for the logical message.
- **MTU and maxInboundPayloadSize are the same value.** False: MTU determines frame-splitting thresholds; maxInboundPayloadSize bounds reassembled payloads.
- **Raising maxInboundPayloadSize will fix DataBufferLimitException.** Not necessarily: that is a codec limit and must be checked separately.
- **One request(n) credit corresponds to one fragment.** False: fragmentation does not increase message credit consumption; one logical payload remains one message.
- **Using Flux means data is always processed in a streaming manner.** False if code collects Flux into memory, creates unbounded queues, or retains every chunk.
- **Zero-copy is always safe and always faster.** False if code does not properly manage buffer lifecycles and releases.
- **Increasing concurrency always increases throughput.** False when storage, CPU, or memory is saturated; high concurrency can raise latency and memory pressure.

## 10. Pre-Production Checklist

- [ ] Distinguished frame, fragmentation, reassembly, and codec limits.
- [ ] Set inbound payload limits on both client and server per their receiving roles.
- [ ] maxInboundPayloadSize is no smaller than the transport's maximum frame length.
- [ ] MTU/fragment size tested against the real transport.
- [ ] Codecs in RSocketStrategies have limits matching valid payloads.
- [ ] Large payloads evaluated for chunking or object storage.
- [ ] Chunks have transferId, sequence, and integrity verification.
- [ ] Backpressure, concurrency, and queues are all bounded.
- [ ] Tested near-limit payloads, over-limit payloads, high concurrency, and cancellation.
- [ ] Observed heap, direct memory, latency, throughput, and buffer errors.
- [ ] No sensitive payload content logged.

## Conclusion

Fragmentation solves frame-size limits by splitting one logical message into multiple frames. Reassembly still reconstructs the complete payload, so inbound payload limits and codec buffer limits continue to matter independently. For very large data, application-level chunking combined with backpressure usually enables processing and releasing data incrementally; for files, external storage with reference passing can be a better fit.

## References

- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [RSocket Protocol - Fragmentation and Reassembly](https://rsocket.io/about/protocol/)
- [Spring Boot Reference - RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Java - RSocketConnector API source](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java)
