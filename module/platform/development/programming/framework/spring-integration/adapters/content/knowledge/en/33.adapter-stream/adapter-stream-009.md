# Buffer size and performance

## 1. Problem: one `bufferSize` parameter does not solve every bottleneck

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`. As data flows through files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, we must preserve message contracts, handle errors, and manage connection lifecycles. In the **Adapter Stream** chapter, **Buffer size and performance** explains the impact of buffer sizes on **throughput, latency, memory, GC, I/O call counts, and backpressure**.

Consider an application reading a 10 GiB file via `InputStream`, turning it into `Message<byte[]>` items, and writing to an `OutputStream`. If each message holds just 1 byte, message creation/dispatch overhead and I/O calls can be huge. If each message holds 64 MiB, peak memory, consumer wait times, queue size, and failure recovery can spiral out of control.

```text
Disk / Pipe / Socket / SDK
           |
      InputStream
           |
      I/O buffering             (A) java.io / source buffer
           |
 ByteStreamReadingMessageSource
           |
      bytesPerMessage           (B) payload bytes per Spring Message
           |
       Inbound poller
           |
      MessageChannel
           |
    [QueueChannel capacity]     (C) number of pending messages
           |
       Transform/Validate
           |
     ByteStreamWritingMessageHandler
           |
      output buffering          (D) java.io / handler buffer
           |
      OutputStream
           |
      External reader
```

**These four items—(A), (B), (C), (D)—are distinct knobs.** Never lump them together as "bufferSize" and bump everything to 64 KiB without measuring. For text sources, there are also **charset decoder buffers**, **max line lengths**, and **record parsers**; for file/remote targets, there are **filesystem caches, TCP socket buffers, SDK batching, and business ACKs**.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish `BufferedInputStream`, `BufferedOutputStream`, `BufferedReader`, `BufferedWriter`, and buffers configured on Spring Integration adapters.
2. Explain `ByteStreamReadingMessageSource.setBytesPerMessage(...)`, `setShouldTruncate(...)`, and the `bufferSize` constructor.
3. Configure `ByteStreamWritingMessageHandler(OutputStream, int)` and its character stream counterpart.
4. Predict trade-offs when buffers are too small or too large: message count, allocations, latency, throughput, and memory.
5. Calculate memory budgets from chunk size, queue capacity, concurrency, reassemblers, and parsers.
6. Never confuse **buffer boundaries** with **framing, line/record boundaries, EOF, or transactions**.
7. Build Spring Boot Java DSL and XML byte-flow configurations with testable parameters.
8. Write tests verifying byte counts, partial reads, UTF-8 splits, and proper microbenchmarking.
9. Set SLO/metric targets, experiment with multiple buffer levels, and make measurement-driven decisions.
10. Choose File/SFTP/TCP/JMS/Kafka or specialized adapters when optimizing over protocols with dedicated ACKs/sessions/offsets.

## 2. How Java I/O buffering works

### 2.1. `InputStream` and `BufferedInputStream`

`InputStream.read()` reads a single byte, whereas `InputStream.read(byte[],off,len)` requests **up to** `len` bytes (with no guarantee of returning all `len` bytes in one call). `BufferedInputStream` maintains a Java-layer buffer to reduce calls down to the underlying source when the app makes small reads.

```java
import java.io.BufferedInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (InputStream input = new BufferedInputStream(
        Files.newInputStream(Path.of("data/input.bin")),
        16 * 1024)) {

    byte[] chunk = new byte[4096];
    int n;
    while ((n = input.read(chunk)) != -1) {
        // Process exactly n bytes, NOT the entire chunk.length.
        consume(chunk, 0, n);
    }
}
```

This snippet is a **Java I/O pattern**: `consume(...)` is an application-provided method. Never pass `chunk` directly to asynchronous code and then overwrite it on the next loop iteration; copy the actual bytes needed or use a pooled/owned buffer strategy.

**Buffering reduces overhead in certain workloads**, yet does not make file reads network-free or transactional. If the underlying source is an in-memory `ByteArrayInputStream`, adding `BufferedInputStream` may not improve performance and can just add extra copying.

### 2.2. `OutputStream` and `BufferedOutputStream`

`BufferedOutputStream` accumulates small writes before pushing them to the sink. In workloads with many small messages, this can cut I/O call overhead.

```java
import java.io.BufferedOutputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (OutputStream output = new BufferedOutputStream(
        Files.newOutputStream(
                Path.of("data/output.bin"),
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE),
        16 * 1024)) {

    output.write(new byte[] {0x41, 0x42, 0x43});
    output.flush();
}
```

`flush()` pushes data out of the buffer layer per Java I/O contracts; **it does not mean `fsync`, remote receiver ACK, or database commit**. `close()` ends the stream and may flush, yet can also throw `IOException`. Opening output with `TRUNCATE_EXISTING` intentionally overwrites old data—only appropriate when the contract allows it.

### 2.3. Double buffering: adding another layer is not always better

```text
FileInputStream
    -> BufferedInputStream(8 KiB)
        -> ByteStreamReadingMessageSource(input, 16 KiB)
            -> byte[4 KiB] payload
```

Depending on the adapter's implementation, you may end up running **two buffering layers** without noticeably reducing underlying source calls, while increasing memory and copies. Similarly, a `BufferedOutputStream` outside a handler that already buffers can obscure flush/close behavior.

Assign a single **resource owner** for the chain, map out every buffer layer in use, and measure before and after removing redundant layers. Never assume "more buffers always mean faster".

### 2.4. `Reader`/`Writer` handle characters, not raw bytes

| API | Unit handled | Buffer belongs to layer |
| --- | --- | --- |
| `BufferedInputStream` | Byte | Java I/O |
| `BufferedOutputStream` | Byte | Java I/O |
| `BufferedReader` | UTF-16 code units / lines | Character I/O |
| `BufferedWriter` | UTF-16 code units | Character I/O |
| `InputStreamReader` | Decodes bytes → characters | Charset decoder |
| `OutputStreamWriter` | Encodes characters → bytes | Charset encoder |
| Spring `Message<byte[]>` | One byte payload | Messaging |
| Spring `Message<String>` | One `String` payload | Messaging |

**Byte buffer sizes** and **character buffer sizes** do not convert by a fixed multiplier in UTF-8: one Unicode code point can take 1–4 bytes and 1–2 UTF-16 code units. Never use `String.length()` to compute length prefixes for byte-oriented protocols.

## 3. Four sizes to distinguish

| Symbol | Parameter | What it tunes | What it does NOT guarantee |
| --- | --- | --- | --- |
| `B_in` | Input stream buffer | Batched reads from source | One read = one record |
| `C_msg` | `bytesPerMessage` | How many bytes the source tries to read per Spring message | Payload always equals `C_msg` |
| `Q` | `QueueChannel(capacity)` | Max waiting **messages** | `Q × C_msg` equals total heap |
| `B_out` | Output stream buffer | Coalescing small writes | Return from write means remote committed |

In addition, define:

- `F_max`: **max frame/record bytes**, bounding parsers/reassemblers.
- `N`: number of **in-flight** messages outside the queue.
- `E`: number of queued executor tasks.
- `R`: number of data copies across decode/transform/serialization.
- `L_target`: end-to-end latency per SLO.

### Example not to confuse

```text
B_in  = 8 KiB
C_msg = 64 KiB
Q     = 32 messages
B_out = 8 KiB
```

Here the queue can hold roughly **2 MiB of payloads** if every message is a full 64 KiB, **excluding** headers, object wrappers, in-flight messages, decoder state, and I/O buffers. Having `B_in=8 KiB` does not shrink messages to 8 KiB, nor does `Q=32` mean total backlog is only 32 KiB.

## 4. ByteStreamReadingMessageSource in Spring Integration 6.5

In Spring Integration **6.5.x**, the primary class is:

```java
import java.io.InputStream;
import org.springframework.integration.stream.ByteStreamReadingMessageSource;

InputStream input = /* InputStream owned by the application */;

ByteStreamReadingMessageSource source =
        new ByteStreamReadingMessageSource(input, 8192);

source.setBytesPerMessage(4096);
source.setShouldTruncate(true);
```

API verified against **Spring Integration Reference 6.5** and Javadoc:

- Constructor `ByteStreamReadingMessageSource(InputStream)`.
- Constructor `ByteStreamReadingMessageSource(InputStream, int bufferSize)`.
- Setter `setBytesPerMessage(int)`, **defaulting to 1024 bytes**.
- Setter `setShouldTruncate(boolean)` to trim payloads when actual bytes read are fewer than the initial array size.

**Constructor `bufferSize` and `setBytesPerMessage` are two separate settings.** For large files, you can test pairs like `(8 KiB, 4 KiB)`, `(16 KiB, 16 KiB)`, or `(64 KiB, 16 KiB)`, though there is no guarantee the largest numbers win in every environment.

### 4.1. When `read(...)` returns only a partial chunk

```text
Requested bytesPerMessage: 8192 bytes
Actual bytes read:         2751 bytes
shouldTruncate(true):      payload length should reflect 2751 bytes
```

An `InputStream` can return fewer bytes than requested **without reaching EOF**. Over networks/pipes, short reads are normal. `shouldTruncate(true)` is crucial so downstream never treats unwritten padding bytes as valid payload. Never use `payload.length == bytesPerMessage` to infer a complete record.

### 4.2. Why can many tiny chunks be slow?

Suppose a file has `D` bytes and each message holds roughly `C_msg` bytes; the number of messages generated is approximately:

\[
N_{\mathrm{messages}}\approx \left\lceil D/C_{\mathrm{msg}}\right\rceil
\]

When `C_msg` is small, every message incurs fixed overhead:

- Allocating `Message<byte[]>`, headers, and possibly array copies.
- Poller `receive()` calls and channel dispatches.
- Header propagation, tracing, and metrics.
- Transformer/handler invocations.
- Queue enqueue/dequeue when buffered channels are used.
- Exception checks and audit logging.

Do not guess nanoseconds per Spring message; **measure messages/sec, bytes/sec, allocation/GC, and latency** on your actual flow. Performance does not scale linearly with `C_msg` because reads can be short, handlers have fixed overhead, and sinks have their own limits.

### 4.3. Large chunks do not automatically produce large records

`bytesPerMessage=64*1024` can read **multiple NDJSON lines in one chunk** or just **part of a JSON object**. For UTF-8 text, a multibyte character can still split across two chunks. You must use framing/reassemblers or stateful streaming decoders, bounded by **`maxFrameBytes`**, before schema parsing.

```text
Input UTF-8 for "Đ": C4 90

Chunk A ends: ... C4
Chunk B starts: 90 ...

decodeStrict(A) -> truncated UTF-8 error
decodeStrict(B) -> continuation byte error

reassemble -> C4 90 -> decode -> "Đ"
```

Raising chunk size lowers the probability of splitting a character, yet **does not eliminate boundary issues**. Framing is a contract; buffering is just an optimization.

## 5. ByteStreamWritingMessageHandler: output buffering

In Spring Integration 6.5:

```java
import java.io.OutputStream;
import org.springframework.integration.stream.ByteStreamWritingMessageHandler;

OutputStream destination = /* stream provided by the application */;

ByteStreamWritingMessageHandler handler =
        new ByteStreamWritingMessageHandler(destination, 8192);
```

The constructor takes `OutputStream` and an optional `bufferSize`; the handler is a `MessageHandler` writing **`byte[]`** payloads to the stream. It can be wired via `@ServiceActivator`, Java DSL `.handle(...)`, or an XML outbound channel adapter.

### 5.1. Writing many small messages

```text
Message #1: 100 bytes
Message #2: 200 bytes
Message #3: 300 bytes
        |
ByteStreamWritingMessageHandler
        |
OutputStream with buffering
        |
External destination receives byte stream
```

Coalescing writes at the buffer layer **does not automatically add delimiters**. The reader sees a contiguous stream of bytes; if three separate records are needed, design newlines, length prefixes, or protocol serialization. `bufferSize` is not a frame size.

### 5.2. Higher throughput can trade off latency

For a sink needing immediate delivery per event, enlarging buffers can hold data in Java memory longer **depending on flush behavior**. For a batch file closed at job end, buffering is more beneficial. Inspect how your specific handler/wrapper flushes in your runtime version and measure **time-to-visible** at the reader, not just producer throughput.

### 5.3. Distinguishing write / flush / close / durability

| Action | Meaning | Does NOT guarantee |
| --- | --- | --- |
| `MessageChannel.send()` | Channel accepted message per channel semantics | Receiver committed |
| `OutputStream.write(...)` | Asked I/O layer to write bytes | Fsynced to disk |
| `BufferedOutputStream.flush()` | Pushed bytes from Java buffer to lower layer | Remote reader processed |
| `OutputStream.close()` | Ends resource; may flush/release | Multi-system transaction completed |
| `FileChannel.force(...)` | Requests byte/metadata sync per filesystem contract | Atomic file publication |
| Business ACK | Receiver replies per protocol | Durability depends on ACK contract |

**Never claim exactly-once delivery** just because a `write()` or `flush()` call returned without throwing.

## 6. CharacterStreamReader/Writer: character buffers and oversized lines

`CharacterStreamReadingMessageSource` accepts a `Reader` and exposes constructor:

```java
import java.io.Reader;
import org.springframework.integration.stream.CharacterStreamReadingMessageSource;

Reader reader = /* UTF-8 Reader created by the application */;
CharacterStreamReadingMessageSource source =
        new CharacterStreamReadingMessageSource(reader, 8192, true);
```

The `8192` argument is **`BufferedReader`'s character capacity**, not wire byte size. The `true` argument enables **blocking to detect EOF** and publishing `StreamClosedEvent`. With `false` (the default), `receive()` can return `null` when `Reader.ready()==false` **without confirming EOF**.

### 6.1. Reader buffer is not a max line size

`BufferedReader.readLine()` can accumulate a line far larger than 8192 chars; it does not reject oversized lines automatically. If a partner sends a 500 MiB line with no newline, the application still risks OOM despite `bufferSize=8192`. Enforce a **bounded line parser** or byte/file caps before unbounded accumulation.

### 6.2. CharacterStreamWritingMessageHandler

```java
import java.io.Writer;
import org.springframework.integration.stream.CharacterStreamWritingMessageHandler;

Writer writer = /* Writer provided by the application */;

CharacterStreamWritingMessageHandler handler =
        new CharacterStreamWritingMessageHandler(writer, 8192);

handler.setShouldAppendNewLine(true);
```

Here `bufferSize=8192` does not decide the charset: when using `OutputStreamWriter`, encoding was chosen when creating the `Writer`. `setShouldAppendNewLine(true)` appends a newline after each message; do not enable it if payloads already include a delimiter.

**Text buffering and binary buffering are distinct.** When analyzing byte throughput, count bytes after UTF-8 encoding rather than using `String.length()` as a byte count.

## 7. Spring Boot Java DSL: configuring three independent sizes

This sample application uses **Java 17+** and Spring Boot managing a compatible **6.5.x** Spring Integration release. The job reads a fixed binary file and writes to another file using two stream adapters. It is meant for comparing buffer sizes and verifying correctness—**not** a production file-sync solution with checkpoints or atomic renames.

### 7.1. Dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-stream</artifactId>
    </dependency>
</dependencies>
```

Do not mix Spring Integration artifacts from multiple versions. Stream classes in this example use **6.5**'s `org.springframework.integration.stream` package; check Javadoc when upgrading to another framework line.

### 7.2. application.yml

```yaml
app:
  copy:
    input-path: ${STREAM_INPUT_PATH:./data/source.bin}
    output-path: ${STREAM_OUTPUT_PATH:./data/copied.bin}
    input-buffer-bytes: ${STREAM_INPUT_BUFFER_BYTES:8192}
    bytes-per-message: ${STREAM_BYTES_PER_MESSAGE:16384}
    output-buffer-bytes: ${STREAM_OUTPUT_BUFFER_BYTES:8192}
    poll-delay-ms: ${STREAM_POLL_DELAY_MS:25}
```

These parameters let you vary **one variable at a time**. Input and output **must be different paths**, the input file must exist, and paths must come from trusted operators—never arbitrary filenames from user requests. `poll-delay-ms` also affects throughput, so keep it fixed when comparing `bytes-per-message` alone.

### 7.3. Java configuration

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.stream.ByteStreamReadingMessageSource;
import org.springframework.integration.stream.ByteStreamWritingMessageHandler;

@SpringBootApplication
@EnableIntegration
public class StreamBufferSizingApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamBufferSizingApplication.class, args);
    }

    @Bean(name = "copyInput", destroyMethod = "close")
    public InputStream copyInput(
            @Value("${app.copy.input-path}") String path)
            throws IOException {

        return Files.newInputStream(
                Path.of(path).toAbsolutePath().normalize());
    }

    @Bean(name = "copyOutput", destroyMethod = "close")
    public OutputStream copyOutput(
            @Value("${app.copy.input-path}") String inputPath,
            @Value("${app.copy.output-path}") String outputPath)
            throws IOException {

        Path source = Path.of(inputPath).toAbsolutePath().normalize();
        Path target = Path.of(outputPath).toAbsolutePath().normalize();
        if (source.equals(target)) {
            throw new IllegalArgumentException(
                    "Input path and output path must differ");
        }
        if (target.getParent() != null) {
            Files.createDirectories(target.getParent());
        }
        // Demo: intentionally replace prior output contents.
        return Files.newOutputStream(
                target,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }

    @Bean
    public IntegrationFlow binaryCopyFlow(
            @Qualifier("copyInput") InputStream input,
            @Qualifier("copyOutput") OutputStream output,
            @Value("${app.copy.input-buffer-bytes:8192}")
                    int inputBufferBytes,
            @Value("${app.copy.bytes-per-message:16384}")
                    int bytesPerMessage,
            @Value("${app.copy.output-buffer-bytes:8192}")
                    int outputBufferBytes,
            @Value("${app.copy.poll-delay-ms:25}")
                    long pollDelayMs) {

        validateBytes("inputBufferBytes", inputBufferBytes);
        validateBytes("bytesPerMessage", bytesPerMessage);
        validateBytes("outputBufferBytes", outputBufferBytes);
        if (pollDelayMs < 1 || pollDelayMs > 60_000) {
            throw new IllegalArgumentException(
                    "Invalid poll delay");
        }

        ByteStreamReadingMessageSource source =
                new ByteStreamReadingMessageSource(
                        input, inputBufferBytes);
        source.setBytesPerMessage(bytesPerMessage);
        source.setShouldTruncate(true);

        ByteStreamWritingMessageHandler writer =
                new ByteStreamWritingMessageHandler(
                        output, outputBufferBytes);

        return IntegrationFlow.from(
                    source,
                    endpoint -> endpoint
                            .id("binaryCopyInbound")
                            .poller(Pollers.fixedDelay(
                                            Duration.ofMillis(pollDelayMs))
                                    .maxMessagesPerPoll(1)))
                .handle(writer)
                .get();
    }

    private static void validateBytes(String name, int bytes) {
        if (bytes < 1 || bytes > 1024 * 1024) {
            throw new IllegalArgumentException(
                    name + " must be in [1, 1048576]");
        }
    }
}
```

Place this class in `StreamBufferSizingApplication.java` with a compatible Spring Boot build setup. This is a **synchronous flow** driven by the inbound poller. There is no `QueueChannel` between source and sink: when the writer slows down, the poll cycle slows down too, providing call-stack backpressure.

### 7.4. Layer-by-layer breakdown

| Code line | Function | Note |
| --- | --- | --- |
| `new ByteStreamReadingMessageSource(input, inputBufferBytes)` | Configures input adapter with given buffer size | Distinct from `bytesPerMessage` |
| `setBytesPerMessage(bytesPerMessage)` | Target payload size for `Message<byte[]>` | Does not create framing |
| `setShouldTruncate(true)` | Keeps payload sized to actual bytes read | Does not mean a complete record |
| `Pollers.fixedDelay(...)` | Paces polling frequency | Not a read/write timeout |
| `.maxMessagesPerPoll(1)` | Caps messages per poll cycle | Total throughput also depends on scheduler |
| `.handle(writer)` | Sends message to output handler | No ACK from external system |
| `new ByteStreamWritingMessageHandler(output, outputBufferBytes)` | Configures byte output to stream | Verify flush/durability separately |

### 7.5. Ownership and output correctness

`@Bean(destroyMethod="close")` instructs Spring to close resource beans when the context closes. Verify the cleanup contracts of the source/handler in your runtime version so **two owners never double-close an SDK stream**. For the Java files in this example, closing buffers/resources in order still requires coordination with **active poll cycles**; never call `context.close()` blindly the moment one chunk finishes reading.

When comparing input and output files, wait until the flow finishes and verify the output is flushed/closed. **Do not take file existence on disk as proof that copying finished.** The example does not auto-stop the app on EOF; a production batch job needs a completion coordinator and drain policy.

### 7.6. Testing multiple configurations

| Run | `inputBufferBytes` | `bytesPerMessage` | `outputBufferBytes` | Purpose |
| --- | ---: | ---: | ---: | --- |
| Baseline | 8192 | 1024 | 8192 | Measure with SI's default chunk size |
| B | 8192 | 4096 | 8192 | Reduce Spring message count |
| C | 8192 | 16384 | 8192 | Increase chunk while holding I/O buffer |
| D | 16384 | 16384 | 8192 | Test input buffer independently |
| E | 16384 | 16384 | 32768 | Test output buffer independently |
| F | 65536 | 65536 | 65536 | Check if throughput drops or latency worsens |

**This is an experiment matrix, not an executed benchmark table.** Keep the input file, machine/CPU, storage, JDK, worker count, GC, poller delay, and cache state constant across comparisons. Run F is not guaranteed to beat Run C.

## 8. XML: configuring source, handler, and poller buffers

Structurally equivalent to Java DSL, XML requires application-provided `InputStream` and `OutputStream` beans (e.g., Java `@Bean`s with cleanup):

```xml
<beans:beans
    xmlns:beans="http://www.springframework.org/schema/beans"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:int="http://www.springframework.org/schema/integration"
    xsi:schemaLocation="
        http://www.springframework.org/schema/beans
        https://www.springframework.org/schema/beans/spring-beans.xsd
        http://www.springframework.org/schema/integration
        https://www.springframework.org/schema/integration/spring-integration.xsd">

    <!-- copyInput / copyOutput: resource beans managed by the app. -->
    <beans:bean id="binarySource"
                class="org.springframework.integration.stream.ByteStreamReadingMessageSource">
        <beans:constructor-arg ref="copyInput"/>
        <beans:constructor-arg value="8192"/>
        <beans:property name="bytesPerMessage" value="16384"/>
        <beans:property name="shouldTruncate" value="true"/>
    </beans:bean>

    <int:channel id="binaryCopyChannel"/>

    <int:inbound-channel-adapter
            id="binarySourceAdapter"
            ref="binarySource"
            channel="binaryCopyChannel">
        <int:poller fixed-delay="25"
                    max-messages-per-poll="1"/>
    </int:inbound-channel-adapter>

    <beans:bean id="binarySink"
                class="org.springframework.integration.stream.ByteStreamWritingMessageHandler">
        <beans:constructor-arg ref="copyOutput"/>
        <beans:constructor-arg value="8192"/>
    </beans:bean>

    <int:outbound-channel-adapter
            id="binarySinkAdapter"
            channel="binaryCopyChannel"
            ref="binarySink"/>
</beans:beans>
```

This is an **integration XML fragment**, since `copyInput` and `copyOutput` must be defined elsewhere. Never enable both this XML and section 7's Java DSL concurrently reading the same `InputStream`: they would compete for read positions and corrupt results.

### When is the XML stream namespace useful?

Spring Integration also offers the `int-stream` namespace for stdin/stdout/stderr, suited to simple CLI text/binary pipelines. However, check tuning attributes against **your version's XSD** rather than assuming every Java setter name is a valid XML attribute. For this use case, explicit source/handler beans and generic channel adapters make each buffer clearly visible.

## 9. Pollers and MessageChannels also affect performance

### 9.1. Pollers govern receive cadence

With `SourcePollingChannelAdapter`:

```java
Pollers.fixedDelay(Duration.ofMillis(50))
       .maxMessagesPerPoll(1)
```

If each poll produces one small message, a 50 ms `fixedDelay` creates a **theoretical ceiling** of ~20 messages/second on one poller assuming zero overlap. With 1024-byte chunks, simple maximum throughput is only ~20 KiB/second! That shows why you should **never benchmark buffers while a poller caps throughput**; processing time and scheduler jitter lower it even further.

To measure real chunk impact, identify whether the poller, disk source, or sink is the bottleneck. Tuning `maxMessagesPerPoll` and schedules can raise throughput, yet also lengthens how long a single poll holds a thread.

### 9.2. DirectChannel vs. bounded QueueChannel

| Channel | Performance trait | Risk |
| --- | --- | --- |
| `DirectChannel` | Synchronous dispatch, minimal queue overhead | Producer/poller held when handler is slow |
| `QueueChannel(capacity)` | Allows bounded message buffering between two pollers | Memory backlog, timeouts, and not durable |
| `ExecutorChannel` | Can decouple caller/worker | Task queue must be bounded; test ordering/rejection |
| `RendezvousChannel` | Zero-capacity handoff | Blocks sender until a receiver arrives |

`QueueChannel(32)` caps at **32 messages**, not 32 KiB. With `bytesPerMessage=64 KiB`, queue payloads alone reach nearly **2 MiB** when full, before counting objects/headers/in-flight items. With an unbounded executor or parser, memory can grow much higher.

### 9.3. Distinguishing batching from enlarging buffers

Increasing `bytesPerMessage` reduces Spring message counts for the same byte volume, but does not automatically create a **database batch** of records. A 64 KiB chunk may hold many records, a partial record, or compressed bytes. If you want JDBC batching, batch **parsed records** per transaction policy; never equate byte chunks with business event counts.

### 9.4. Backpressure and post-read failures

`InputStream.read()` may have pulled bytes from the source before `QueueChannel.send()` blocks or times out. **Retrying by calling `source.receive()` again does not recover the old bytes.** For critical sources, use durable staging/checkpoints tied to committed records and idempotent consumers instead of inflating queue capacity to hide errors.

## 10. Estimating memory and allocation

Let:

- `C`: average or capped `byte[]` payload size (bytes/message).
- `Q`: max queued messages.
- `N`: max concurrently processed messages.
- `H`: average overhead per Spring message and headers.
- `B`: total allocated I/O buffers.
- `P`: memory for parsers, reassemblers, decoded text, and objects.

Estimated flow-related memory:

\[
M_{\mathrm{peak}}\;\approx\; (Q+N)(C+H) + B + P
\]

This is a sizing model, **not an exact memory profiler**. Using average `C` can underestimate peaks when record sizes are skewed; object headers and GC overhead also vary across JVMs.

### Sample calculation table

| `C` | `Q` | Queue payload memory alone when full |
| ---: | ---: | ---: |
| 1 KiB | 64 | 64 KiB |
| 4 KiB | 64 | 256 KiB |
| 16 KiB | 64 | 1 MiB |
| 64 KiB | 64 | 4 MiB |
| 256 KiB | 64 | 16 MiB |

Increasing chunk size 64× without adjusting queue capacity increases **queue payload memory capacity** 64×. If a reassembler buffers a 100 MiB record and a parser builds a massive JSON tree, even a tiny queue can OOM.

### 10.1. Allocation and GC

For a finite file of ~`D` bytes and average chunk size `C`:

\[
N_{\mathrm{message}}\approx D/C
\]

More messages mean more wrapper, `MessageHeaders`, and dispatch allocations. Yet overly large chunks can trigger allocation spikes, humongous object pressure in certain GC setups, extra copying, and tail-latency spikes. There is no single universal "humongous" threshold across all JVMs/GCs; inspect GC logs/JFR.

### 10.2. Off-heap and OS buffers

Heap metrics do not capture kernel page cache, socket send/receive buffers, direct `ByteBuffer`s, or native SDK allocations. If a process shows high RSS with stable heap, inspect off-heap/native memory and external I/O buffers rather than only tuning heap size.

### 10.3. Avoid creating accidental extra copies of a chunk

A flow can simultaneously hold:

```text
raw byte[]
   -> copied byte[] for frame
      -> new String (UTF-8 decode)
         -> business DTO / JSON tree
            -> new encoded byte[]
               -> destination buffer
```

Avoid logging raw payloads or converting back and forth between bytes and `String` needlessly. If business logic handles binary, keep `Message<byte[]>`; if it needs text, decode once **after assembling records**; if persisting to a database, batch validated records.

## 11. Buffer size, throughput, and latency: a non-monotonic curve

A common belief is "larger buffers are always faster". In reality, gains rise sharply from tiny to moderate sizes, then **saturate or degrade** as size grows further.

```text
Throughput
 ^
 |                 ________   saturation region (illustrative)
 |              __/        \\__
 |          ___/
 |      ___/
 |_____/________________________> bytesPerMessage / buffer size
   very small    moderate       very large
```

This diagram is **conceptual**, not benchmark data. The real curve depends on the filesystem, SSD/HDD, sockets, SDKs, GC, pollers, CPU, compression, and serialization.

### 11.1. When is a buffer too small?

- Message count grows, making Spring Messaging fixed overhead large relative to payloads.
- Tiny reads/writes can increase kernel/SDK overhead without another buffering layer.
- Pollers or channel dispatch consume a high CPU share.
- Per-message metrics/tracing/logging become a bottleneck.

**Exception:** if the source is a pipe with tiny records and a strict low-latency SLO, small messages may be the right choice; never force excessive accumulation just to chase throughput.

### 11.2. When is a buffer too large?

- Larger payload byte arrays inflate memory and backlog when queues count by message.
- Partially filled buffers may wait depending on flush/read behavior.
- Each message represents a heavy unit of work, hurting fairness for other flows on the same thread/scheduler.
- Failures after reading a huge chunk are hard to replay on non-seekable sources.
- Large copies/serialization trigger GC pressure or tail-latency spikes.
- An oversized message can exceed downstream DB/HTTP/broker limits even if raw streams allow it.

### 11.3. Throughput is not latency

| Metric | Question |
| --- | --- |
| **Throughput** | How many bytes/records finish per second? |
| **Latency P50/P95/P99** | How long does one record take from source to commit/ACK? |
| **Time to first record** | Once initial data arrives, how soon does the consumer see a record? |
| **Queue residence time** | How long does a record sit waiting in a queue? |
| **GC pause / CPU** | Does the JVM have enough headroom to sustain load? |
| **Memory peak/RSS** | Do buffers stay within the memory budget? |
| **Error rate** | Are timeouts, rejections, partial writes, or retries climbing? |

A 64 KiB setting may boost batch throughput while hurting latency for small events. Tune according to **user SLOs**: finishing a batch file under 2 minutes differs from delivering telemetry lines within 100 ms.

### 11.4. I/O call count is not always syscall count

Calling `BufferedInputStream.read(byte[])` 1,000 times does not mean the JVM made 1,000 kernel `read` syscalls: the wrapper serves reads from its internal buffer. Conversely, one Java call into a network SDK can trigger many underlying operations. Measure Java call counts, syscalls, and socket/file latency **with proper tools**, rather than guessing from code alone.

## 12. Designing valid benchmarks

A useful performance benchmark verifies **correctness** first:

1. Keep the binary fixture file **immutable**, with known `fileSize` and checksum.
2. Ensure output never overwrites input; verify output bytes after each run.
3. Fix worker counts, queue policies, JDK/GC, storage, and stream ownership.
4. Record **throughput, P95/P99 latency, allocations, GC, CPU, peak memory**, and message counts.
5. Include warm-up, multiple iterations, and distinguish cold-cache vs. warm-cache runs.
6. Change **only one parameter** per experiment group.
7. Evaluate **large files**, **small messages**, **long records**, **slow consumers**, and **short trailing chunks**.
8. Avoid per-chunk logging inside benchmark loops: loggers can become the bottleneck.

### 12.1. Separate three kinds of benchmarks

| Test type | What it measures | What it does NOT prove |
| --- | --- | --- |
| **JDK-only copy** | Cost of `InputStream`/`OutputStream` and Java buffering | Spring Messaging overhead |
| **In-memory Spring flow** | Source/message/channel/handler overhead | Disk/network performance |
| **Production-like end-to-end** | Storage, serialization, queues, consumers, network, ACKs | Automatically pinpointing bottlenecks without telemetry |

Testing `ByteArrayInputStream` + `ByteArrayOutputStream` and concluding "64 KiB is optimal for SFTP" is wrong: SFTP has its own encryption, sessions, network latency, remote disks, and connection pools.

### 12.2. JDK baseline file copy for comparison

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Objects;

public final class BufferedFileCopy {

    private BufferedFileCopy() {
    }

    public static long copy(
            Path source, Path destination,
            int ioBufferSize, int copyChunkSize)
            throws java.io.IOException {

        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        if (source.toAbsolutePath().normalize().equals(
                destination.toAbsolutePath().normalize())) {
            throw new IllegalArgumentException(
                    "Source and destination must differ");
        }
        if (ioBufferSize < 1 || copyChunkSize < 1) {
            throw new IllegalArgumentException(
                    "Buffer sizes must be positive");
        }

        try (InputStream in = new BufferedInputStream(
                    Files.newInputStream(source), ioBufferSize);
             OutputStream out = new BufferedOutputStream(
                    Files.newOutputStream(
                        destination,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING,
                        StandardOpenOption.WRITE),
                    ioBufferSize)) {

            byte[] buffer = new byte[copyChunkSize];
            long totalBytes = 0;
            int n;

            while ((n = in.read(buffer)) != -1) {
                if (n == 0) {
                    // Do not emit an empty message; allow the source to make progress.
                    // For an InputStream with prolonged 0-byte reads, add a
                    // dedicated deadline/policy to avoid a busy loop.
                    continue;
                }
                out.write(buffer, 0, n);
                totalBytes += n;
            }
            out.flush();
            return totalBytes;
        }
    }
}
```

**This is a Java I/O baseline**, without Spring Integration. It isolates `ioBufferSize` and `copyChunkSize` to compare against the Spring flow. Use standalone files and clean up outputs after testing; never run against production data that could be overwritten. `Files.copy(...)` is also a useful baseline, though its implementation optimizes differently and must be noted explicitly.

### 12.3. Measuring time carefully

Example of a local timing measurement:

```java
long startNanos = System.nanoTime();
long copiedBytes = BufferedFileCopy.copy(
        sourcePath, outputPath, 8192, 16384);
long elapsedNanos = System.nanoTime() - startNanos;

double seconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = copiedBytes / (1024.0 * 1024.0) / seconds;
```

This is an **illustrative snippet** given existing `sourcePath`/`outputPath` `Path` variables. A single run is never a trustworthy benchmark. Warm up, repeat across iterations, capture distributions, lock down cache conditions, check correctness, and compare against baselines. JMH suits **Java microbenchmarks**, while end-to-end Spring Integration requires realistic workloads with telemetry.

### 12.4. Avoiding benchmark biases

- **Page cache:** the second run can look faster because the file sits in OS cache.
- **Disk contention:** other apps reading/writing the same storage skew results.
- **JIT warm-up:** early iterations run slower due to class loading and JIT compilation.
- **GC:** allocation spikes and pauses distort tail latency.
- **Network variance:** SFTP/HTTP/TCP do not have fixed RTTs.
- **Logging:** a debug log per message can erase buffering gains.
- **Poller ceiling:** a high `fixedDelay` makes you benchmark the scheduler instead of disk.
- **Validation cost:** parsing JSON/CSV can outweigh raw byte copying.
- **File size:** tiny files do not represent long streaming workloads.

### 12.5. Configuration ladder to test

Test `bytesPerMessage` at `1 KiB, 4 KiB, 16 KiB, 64 KiB, 256 KiB`. At each level, vary `input/output buffer size` independently while holding everything else constant. You do not need to test every combination upfront if test cost is high; narrow in on the sweet spot using throughput + P99 latency + memory.

If moving from 16 KiB to 64 KiB improves throughput by only 1% while multiplying queue memory by 4× and hurting P99, 64 KiB is likely not worth it. The **1%** figure here is a hypothetical scenario illustrating a trade-off decision, not a measured benchmark finding.

## 13. JUnit 5: source returns exact bytes, including the final chunk

Test with in-memory data to verify **correctness before measuring performance**.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.integration.stream.ByteStreamReadingMessageSource;
import org.springframework.messaging.Message;

class StreamChunkSizingTest {

    @Test
    void readsAllBytesWithoutPaddingInLastChunk() {
        byte[] original = new byte[8193];
        for (int i = 0; i < original.length; i++) {
            original[i] = (byte) (i % 251);
        }

        ByteStreamReadingMessageSource source =
                new ByteStreamReadingMessageSource(
                        new ByteArrayInputStream(original),
                        512);
        source.setBytesPerMessage(4096);
        source.setShouldTruncate(true);

        ByteArrayOutputStream captured =
                new ByteArrayOutputStream();
        int messages = 0;
        int lastPayloadLength = -1;

        Message<byte[]> message;
        while ((message = source.receive()) != null) {
            byte[] chunk = message.getPayload();
            assertTrue(chunk.length > 0);
            assertTrue(chunk.length <= 4096);
            lastPayloadLength = chunk.length;
            captured.write(chunk, 0, chunk.length);
            messages++;
        }

        assertArrayEquals(original, captured.toByteArray());
        assertEquals(3, messages);
        assertEquals(1, lastPayloadLength);
    }
}
```

With a finite `ByteArrayInputStream`, the test expects three chunks **4096 + 4096 + 1**. This test **was not executed in STEP 4**; against another `InputStream` exhibiting short reads, there may be more than three chunks while preserving total bytes and order. Thus asserting an exact chunk count only fits fixtures with deterministic read behavior.

### 13.1. Testing a short-read source

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class SmallReadInputStream extends InputStream {

    private final ByteArrayInputStream delegate;

    public SmallReadInputStream(byte[] data) {
        this.delegate = new ByteArrayInputStream(data);
    }

    @Override
    public int read() {
        return delegate.read();
    }

    @Override
    public int read(byte[] b, int off, int len) throws IOException {
        if (len == 0) {
            return 0;
        }
        // Deliberately cap each read to at most 3 bytes.
        return delegate.read(b, off, Math.min(len, 3));
    }
}
```

This class simulates a source that always returns tiny fragments; in direct Java I/O tests, `read(buffer)` must not be assumed to fill `buffer.length`. When wired into a Spring source with buffering, **verify actual runtime behavior** rather than assuming a 1-to-1 mapping between wrapper reads and underlying reads.

### 13.2. Testing integrity matters more than chunk count

For any source, assertions should prioritize:

1. `sum(payload.length) == original.length` (when the source is finite and error-free).
2. Reassembled bytes match the original byte **order** identically.
3. No trailing `0` padding bytes in the final chunk.
4. No unexpected empty messages.
5. EOF/completion handled per the source contract.

Counting chunks is only for performance analysis; never let business logic require an exact chunk count unless the protocol mandates it.

## 14. JUnit 5: measuring BufferedInputStream's impact on downstream calls

`CountingInputStream` counts calls **down to the underlying source**, not OS kernel syscalls:

```java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class CountingInputStream extends FilterInputStream {

    private long singleByteReads;
    private long blockReads;

    public CountingInputStream(InputStream delegate) {
        super(delegate);
    }

    @Override
    public int read() throws IOException {
        singleByteReads++;
        return in.read();
    }

    @Override
    public int read(byte[] b, int off, int len) throws IOException {
        blockReads++;
        return in.read(b, off, len);
    }

    public long getSingleByteReads() {
        return singleByteReads;
    }

    public long getBlockReads() {
        return blockReads;
    }
}
```

Wrapping a `CountingInputStream` in `BufferedInputStream` and calling single-byte `read()` on the outer stream drastically reduces delegate calls compared to unbuffered single-byte reads. A test can verify:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import org.junit.jupiter.api.Test;

class BufferReadCallTest {

    @Test
    void bufferReducesReadsToDelegateInThisFixture()
            throws Exception {

        byte[] fixture = new byte[8192];
        CountingInputStream counted =
                new CountingInputStream(
                    new ByteArrayInputStream(fixture));

        try (BufferedInputStream buffered =
                new BufferedInputStream(counted, 1024)) {

            int bytesRead = 0;
            while (buffered.read() != -1) {
                bytesRead++;
            }
            assertEquals(fixture.length, bytesRead);
        }

        assertTrue(counted.getBlockReads() > 0);
        assertTrue(counted.getBlockReads() < fixture.length);
    }
}
```

This is a **logic test about buffering layers**, not run in STEP 4. It **does not** prove fewer OS syscalls because the delegate is `ByteArrayInputStream`. When measuring real file/network I/O, use profilers or OS counters.

## 15. Testing output buffering, flush, and incomplete data

Output can have buffers in the **handler**, **Java wrapper**, **OS**, and **SDK**. To understand flushing, start with an in-RAM JDK test:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class OutputBufferTest {

    @Test
    void flushMakesBufferedBytesVisibleToUnderlyingSink()
            throws Exception {

        ByteArrayOutputStream sink =
                new ByteArrayOutputStream();

        try (BufferedOutputStream buffered =
                new BufferedOutputStream(sink, 8192)) {

            buffered.write(
                    "Đã thanh toán".getBytes(
                        StandardCharsets.UTF_8));

            // BufferedOutputStream is holding bytes smaller than
            // the buffer size per JDK behavior.
            assertEquals(0, sink.size());

            buffered.flush();
            assertArrayEquals(
                    "Đã thanh toán".getBytes(
                            StandardCharsets.UTF_8),
                    sink.toByteArray());
        }
    }
}
```

This test **illustrates a specific JDK `BufferedOutputStream` class**; it does not replace testing `ByteStreamWritingMessageHandler` on your Spring Integration runtime version. Some handlers/wrappers flush eagerly per message, while other sinks flush/commit per session. **Never assume raising buffer size keeps Java bytes buffered until close**; verify with tests or the implementation of the component in use.

### When must you flush?

| Use case | Appropriate policy |
| --- | --- |
| Temporary batch file export | Flush/close when finished, then publish atomically per contract |
| Line-oriented console text | Include delimiters/newlines; verify reader sees lines promptly |
| Request–reply network stream | Flush per frame/protocol; enforce timeouts and ACKs |
| SDK object upload | Follow SDK flush/commit/complete/abort APIs |
| Durability-critical writes | Use durable storage/transactions and fsync/ACKs as required |

**Never flush after every single byte** as it destroys batching; yet **never delay flushing too long** if the protocol expects frame-by-frame replies (otherwise deadlock occurs: writer awaits ACK while reader awaits unflushed bytes).

## 16. Case study: tuning a Vietnamese NDJSON pipeline

Suppose the source is an NDJSON file where each line is a UTF-8 JSON object containing Vietnamese names or notes. A byte adapter reads 16 KiB chunks and downstream parses JSON.

### 16.1. Flawed initial configuration

```text
ByteStreamReadingMessageSource
    bytesPerMessage = 16384
          |
          v
new String(chunk, UTF_8)
          |
          v
parseOneJsonObject(text)
```

This fails because:

1. A 16 KiB chunk can contain multiple JSON lines.
2. One JSON object can span two or more chunks.
3. A multibyte UTF-8 character can split across two chunks.
4. `bytesPerMessage` is not `maxLineLength` and carries no EOF/commit semantics.

### 16.2. Proper pipeline

```text
InputStream
    |
ByteStreamReadingMessageSource
    |
Message<byte[]> chunks
    |
Bounded LF / frame assembler
    |  maxLineBytes=1 MiB, pending-timeout=policy
    v
Complete UTF-8 record bytes
    |
CharsetDecoder(REPORT)
    |
Valid String per line
    |
JSON parser + schema validation
    |
Domain event with stable eventId
    |
Durable inbox / idempotent consumer
```

When binary handling is unnecessary and the contract is truly **one line of text per record**, consider `CharacterStreamReadingMessageSource` with a UTF-8 `Reader`. Still, standard `BufferedReader.readLine()` does not cap line length on its own, so untrusted inputs still need a bounded parser/size cap.

### 16.3. What should you tune?

- If CPU spends too much time on Spring message wrappers, try raising `bytesPerMessage` moderately.
- If the parser stitches too many chunks per record, pick clean framing and max record caps rather than blindly enlarging buffers.
- If downstream DB writes are slow, enlarging input buffers will not fix the bottleneck; improve batching/transactions/consumer throughput at the DB layer.
- If queues fill up, throttle intake or scale consumers within budget; never make queues unbounded.
- If P99 latency climbs due to oversized messages, test smaller chunks or ordered independent record handling.
- If peak memory rises because the parser accumulates huge lines, cap `maxLineBytes` before decoding/parsing.

## 17. Case study: slow TCP/SDK output

An SDK provides an `OutputStream` to a device. The app writes continuous small binary frames. Suppose you start with `ByteStreamWritingMessageHandler(destination, 8192)` and raise it to `65536`:

| Observation | Do NOT jump to conclusion | Check further |
| --- | --- | --- |
| Producer throughput increases | Receiver is processing faster | Receiver ACKs and network backlog |
| `write()` returns early | Frame already left the machine | Wrapper/OS send buffers, flushing |
| Bytes become visible late | Just enlarge buffers more | Does protocol need per-frame flush? |
| TCP timeouts increase | Larger buffers are always faulty | Server rate limits, congestion, sessions |
| GC drops | No memory bottleneck left | Queues/in-flight/parsers and RSS |
| Failures after many frames | Sent data can safely auto-retry | Partial writes, sequences, idempotency |

**Note:** an `OutputStream` is not a full TCP transport adapter. When you need connection pooling, framing, reply correlation, reconnects, and timeouts, choose the **TCP outbound adapter/gateway** with a `TcpConnectionFactory` and proper serializer/deserializer. Similarly, pick SFTP/HTTP/JMS/AMQP/Kafka adapters when requirements belong to those protocols.

## 18. Error handling and the truth about partial reads/writes

### 18.1. A partial read is not an error

An `InputStream.read(buffer)` call returning 200 bytes for an 8192-byte buffer **can be completely normal**. Do not retry blindly or discard remaining bytes. Record `n` and process exactly `n` bytes; on the message source, use `shouldTruncate(true)` and proper framing.

### 18.2. A partial write can be a serious failure

`OutputStream.write(bytes)` has no multi-message transaction/rollback. Writing half a frame and then hitting `IOException` makes retrying the whole frame risk duplicates or protocol corruption; you need reconnect/reframe rules, stable sequence/event IDs, ACKs, and idempotency.

```text
frame = [length][eventId][payload]
             |
       write first half
             |
         I/O failure
             |
       retry whole frame?
             |
  receiver may see corrupt/duplicate stream
```

Therefore, **enlarging buffers for throughput must never replace a recovery strategy**.

### 18.3. Full queue after reading

When using `QueueChannel` after the source:

```text
source.receive() reads chunk
       |
channel.send(chunk, timeout) fails
       |
chunk is already read from InputStream
```

Do not call `source.receive()` again expecting to retry the old chunk. For replayable sources (immutable files), checkpoint by **committed records**, not bytes merely read into a buffer. For non-replayable sockets/stdin, use durable staging if event loss is unacceptable.

### 18.4. Exceptions do not always reach errorChannel

On `DirectChannel`, downstream handler exceptions can propagate back to the caller/poller. On polling endpoints or async flows, error routing depends on configuration and error handlers. Never assume every `IOException` during Spring bean close turns into an `ErrorMessage` on the global `errorChannel`.

When benchmarking, track **errors and failed messages** instead of ignoring them; a version that looks "faster" because it drops payloads or swallows exceptions is invalid.

## 19. EOF, lifecycle, and shutdown when buffers exist

### 19.1. Stopping the poller does not flush output

`SmartLifecycle.stop()` stops the endpoint per contract; it is not proof that all buffers are empty. For queued flows:

```text
Stop inbound poller
      |
      v
Wait until queued + in-flight business work drain
      |
      v
Flush output buffered resources
      |
      v
Close owned output / input resources
      |
      v
Mark completed only after required ACK/commit
```

`QueueChannel.getQueueSize()==0` can still coincide with **a consumer holding an uncommitted dequeued message**. Track `inFlight`, transactions, and pending outboxes.

### 19.2. Byte source vs. character source EOF differences

- `ByteStreamReadingMessageSource` reads an `InputStream` and emits byte chunks; it does not emit `StreamClosedEvent` by default like a character source with EOF detection enabled.
- `CharacterStreamReadingMessageSource` supports `blockToDetectEOF=true` and can publish `StreamClosedEvent`; events can repeat if the poller keeps running, so deduplicate and stop cleanly.
- `Reader.ready()==false` does not prove EOF.

Never close streams inside a listener while downstream is still processing. In the file-copy demo, never read the output file back while the app is still writing, before buffers flush/close.

### 19.3. Never close System.in/System.out from a module

Standard streams normally belong to the JVM or runtime logging and are shared by other components. Creating `BufferedOutputStream(System.out)` and closing it from a handler can break logging or other CLI features. Close only streams that the **resource owner is authorized to close**, with explicit policies for SDK/session streams.

### 19.4. Power loss and SIGKILL

Spring cleanup hooks cannot run if the process dies abruptly. When durability matters, persist events/offsets to durable storage and maintain recovery mechanisms independent of `flush()`/`close()`. For production File outbound, use temporary suffixes, atomic publication, filesystem-appropriate fsync, or adapters/gateways supporting proper file policies.

## 20. Observability when tuning buffers

### 20.1. Suggested metrics

| Suggested metric | Unit | Explanation |
| --- | --- | --- |
| `stream_bytes_read_total` | bytes | Bytes read by the source |
| `stream_chunks_emitted_total` | messages | `Message<byte[]>` items emitted |
| `stream_chunk_payload_bytes` | histogram | Distribution of actual payload sizes |
| `stream_bytes_written_total` | bytes | Bytes handed to writer; not yet an ACK |
| `stream_messages_per_second` | messages/s | Dispatch/poller rate and overhead |
| `stream_throughput_mib_per_second` | MiB/s | Payload throughput |
| `stream_end_to_end_latency_seconds` | seconds | From record receipt to commit/ACK |
| `stream_queue_depth` | messages | Waiting backlog, excluding in-flight |
| `stream_inflight_count` | messages | Currently processing in consumers |
| `stream_buffer_allocated_bytes` | bytes | Application-tracked buffers |
| `stream_gc_pause_seconds` | seconds | GC impact |
| `stream_copy_errors_total` | events | Source/decoder/sink failures |
| `stream_send_block_seconds` | seconds | Time blocked sending to a full queue |
| `stream_partial_frames_total` | frames | Incomplete records per protocol |

These are **suggested metrics**, not a list of all built-in Spring Integration meters. Spring Integration and Micrometer offer management/observation support; check existing meters before adding custom ones. Never use raw payloads, event IDs, customer names, or full file paths as high-cardinality labels.

### 20.2. Evaluating against SLOs

Never pick the winning configuration on throughput alone. Build a decision table:

| Test config | Throughput | P99 latency | Max heap/RSS | Errors/timeouts | Meets SLO? |
| --- | --- | --- | --- | --- | --- |
| 1 KiB | *Measure* | *Measure* | *Measure* | *Measure* | *Evaluate* |
| 4 KiB | *Measure* | *Measure* | *Measure* | *Measure* | *Evaluate* |
| 16 KiB | *Measure* | *Measure* | *Measure* | *Measure* | *Evaluate* |
| 64 KiB | *Measure* | *Measure* | *Measure* | *Measure* | *Evaluate* |
| 256 KiB | *Measure* | *Measure* | *Measure* | *Measure* | *Evaluate* |

**Never fabricate numbers** in a benchmark table without running tests; the best setting depends on the workload. Draw conclusions only after repeated reliable measurements under identical conditions.

## 21. Troubleshooting: buffer size and performance

| Symptom | Possible cause | How to verify/fix |
| --- | --- | --- |
| Larger buffer yields no throughput gain | Poller `fixedDelay` or downstream DB is the bottleneck | Measure poll rate and business commits/sec |
| Larger `bytesPerMessage` spikes heap | Queue counts by message; each payload is larger | Check queue depth × payload size and peak memory |
| Final chunk has trailing 0 bytes | Payload not truncated to actual bytes read | Enable `setShouldTruncate(true)` |
| Some messages shorter than `bytesPerMessage` | `InputStream.read(...)` returned a short read | Handle `payload.length` properly; do not treat as EOF |
| Random JSON parse failures | Passing raw byte chunks straight to JSON parser | Reassemble/frame before decoding/parsing |
| Vietnamese text turns into `U+FFFD` | UTF-8 split across chunks or wrong charset | Strict decoder preserving state across chunks |
| Output file missing bytes while running | Sitting in output buffer or flow unfinished | Verify flush/close/lifecycle |
| `write()` fast yet receiver sees data late | OS/SDK buffers, network congestion, missing frame flush | Measure time-to-visible and ACKs |
| Flushing every byte spikes CPU | Loses batching benefits | Flush per frame/protocol/SLO |
| `readLine()` uses 8 KiB buffer yet OOMs | A single line can outgrow the buffer | Bounded line length and input quotas |
| Queue holds only 16 messages yet OOMs | Unbounded decoder/JSON parser/executor | Cap max frame and max task queue |
| `DirectChannel` slows down with slow sink | Synchronous dispatch | Consider bounded queue/workers while keeping order |
| `ExecutorChannel` raises throughput but scrambles order | Parallel workers break total order | Partition/sequence/single-owner |
| `QueueChannel` stays full | Consumer stopped or slower than producer | Check consumer poller, latency, exceptions |
| `send(timeout)` failure loses bytes | Source already read chunk before enqueue | Durable staging/checkpoints; stop intake |
| RAM test fast yet production slow | Disk/SSD/network/SDK/crypto differ from RAM | Run production-like benchmarks |
| Second run abnormally fast | OS page cache or JIT warm-up | Separate warm/cold cache; repeat iterations |
| Larger chunks cause GC spikes | Large arrays, copies, JSON trees | JFR/GC logs; cut allocations |
| `String.length()` corrupts length prefix | Counts UTF-16 units instead of bytes | UTF-8 encode first, then read `byte[].length` |
| Writer fails after flush | Disk full, broken pipe, closed session | Classify error and mark uncertain state |
| Empty or shorter-than-expected messages | EOF, short read, or parser bug | Inspect actual bytes and fixture validation |
| Output file wiped on restart | Opened with `TRUNCATE_EXISTING` | Switch to proper publish/recovery policy |
| EOF reached yet app stays running | Byte source/poller lacks completion coordinator | Stop intake, drain, flush/close |
| Buffer optimal on Linux but poor on Windows | Different filesystem/drivers/caches/charsets | Benchmark on the target deployment OS |
| High JVM RSS with normal heap | Direct buffers, OS page cache/native SDK | Check native memory and OS metrics |

### Concise diagnostic sequence

1. **Verify data correctness:** do input and output bytes match?
2. **Map all buffers:** which Java/Spring/SDK layers are buffering?
3. **Locate the bottleneck:** CPU, disk, network, queue, GC, or DB handler?
4. **Check the poller:** is `fixedDelay`/`maxMessagesPerPoll` capping message rate?
5. **Compare `C_msg` vs. `B_in`/`B_out`:** are you tuning the wrong knob?
6. **Check downstream framing:** does a chunk hold multiple or partial records?
7. **Check peak memory:** queues, in-flight items, parsers, executors, and native buffers.
8. **Check latency/flushing:** when did the receiver actually observe bytes?
9. **Check error/recovery:** how is already-read-but-unhanded-off data handled?
10. **Benchmark under control:** repeat runs, check SLOs, never assume max size is optimal.

## 22. Which adapter to choose when performance sits at another layer?

| Need | Appropriate approach | Why not just raise Stream buffers? |
| --- | --- | --- |
| Reading an SDK-provided Java `InputStream` | `ByteStreamReadingMessageSource` | Lets you tune chunks/pollers; SDK still has its own semantics |
| Reading continuously arriving files in a directory | **File inbound adapter** | Scanners/filters, file completion, locking |
| Writing each message to its own file | **File outbound adapter** | Filenames, modes, temporary suffixes |
| Remote SFTP/FTP/SMB files | Remote file adapters | Sessions, retries, remote transfer semantics |
| HTTP request–reply or streaming | HTTP/WebFlux depending on use case | Status codes, timeouts, network/backpressure protocols |
| TCP framing/reconnects | TCP inbound/outbound adapter/gateway | Connection factories, serializers/deserializers |
| JMS/AMQP queues | JMS/AMQP adapters | Prefetch, ACK/redelivery, listener concurrency |
| Kafka topics | Kafka adapters | Consumer polls/offsets, partitions/producer batching |
| Database operations | JDBC adapter/gateway | Transactions, JDBC batch sizes, connection pools |
| Metrics/logs | Logging framework/appender | Rotation, async buffers, retention |

For example, if a Kafka producer blocks waiting for broker ACKs, increasing buffers on a `ByteStreamWritingMessageHandler` (which is not a Kafka producer adapter) **has nothing to do with Kafka `batch.size` or `linger.ms`**. Likewise, SFTP throughput depends on sessions, encryption, and remote servers, not solely Java `BufferedInputStream`.

## 23. Practical checklist for choosing buffer sizes

Before promoting a new configuration to production, verify:

- [ ] You know whether payloads are **binary** or **UTF-8 text** and the framing contract.
- [ ] You distinguish `B_in`, `bytesPerMessage`, `Q`, `B_out`, and max record size.
- [ ] You calculated **peak memory** across queue capacity, concurrency, and parsers.
- [ ] You measured both **throughput** and **P95/P99 latency**, not just messages/s.
- [ ] You benchmarked both **small records** and **large records**, not a single fixture.
- [ ] You tested **short reads**, final chunks, and EOF.
- [ ] You tested **UTF-8 split across chunks** or equivalent protocol framing.
- [ ] You tested **slow consumers**, bounded queue saturation, and send timeouts.
- [ ] You tested **flushing** and time-to-visible at a real sink.
- [ ] You tested **partial writes/`IOException`** and recovery policies.
- [ ] You assigned a single **resource owner** managing `close()`.
- [ ] You designed shutdown as **stop intake → drain → flush → close**.
- [ ] You have event IDs/idempotency/checkpoints where loss or duplication is unacceptable.
- [ ] You have metrics/alerts for queue depth, GC, latency, and errors.
- [ ] You tested in a production-like environment and recorded baseline/rollback plans.

## 24. Practice exercises

1. Explain the difference between `BufferedInputStream(8192)` and `bytesPerMessage(8192)`.
2. Explain why `QueueChannel(64)` caps message count rather than directly capping bytes.
3. Use `InputStream.read(byte[])` and process only the actual `n` bytes instead of the whole buffer when `n` is small.
4. Create `ByteStreamReadingMessageSource` with constructor `bufferSize=4096` and `bytesPerMessage=16384`.
5. Enable `setShouldTruncate(true)` and verify the last chunk of a file has no extra padding bytes.
6. Use an 8193-byte fixture with `bytesPerMessage=4096` and verify total bytes read.
7. Swap `ByteArrayInputStream` for `SmallReadInputStream` and explain why chunk count can change.
8. Wrap a source with `CountingInputStream` then `BufferedInputStream` to count reads reaching the delegate.
9. Use `BufferedFileCopy.copy(...)` as a JDK I/O baseline.
10. Compare an in-memory Spring Integration flow with a JDK-only copy on the same payload.
11. Test `bytesPerMessage` at 1/4/16/64 KiB and record **throughput, CPU, GC, and peak heap**.
12. Hold `bytesPerMessage` fixed while varying input buffer and output buffer separately.
13. Using section 7's Spring Boot flow, change `poll-delay-ms` and observe the message-rate ceiling.
14. Configure the XML source/handler equivalent to the Java DSL flow.
15. Insert `QueueChannel(16)` between inbound and consumer, and calculate the memory budget with 64 KiB payloads.
16. Add a 200 ms slow consumer and observe how `DirectChannel` vs. `QueueChannel` affects the poller differently.
17. Explain why a 64 KiB chunk can still contain half a JSON record.
18. Reassemble UTF-8 bytes of a multibyte character split across two chunks.
19. Write a bounded assembler with `maxFrameBytes` and missing-delimiter timeouts.
20. Feed an oversized input line and prove an 8 KiB `BufferedReader` does not prevent OOM without a line limit.
21. Compare `new String(bytes, UTF_8)` with a strict `CharsetDecoder` on malformed bytes.
22. Test output buffering before and after `flush()` with `ByteArrayOutputStream`.
23. Compare `flush()`, `FileChannel.force(...)`, atomic rename, and business ACK.
24. Simulate a partial write followed by `IOException` and describe retry and framing risks.
25. Count committed business records rather than merely raw chunks read.
26. Simulate a full queue after the source has read, and propose durable handoff to prevent data loss.
27. Measure **P99 latency** while throughput rises with large buffer sizes.
28. Compare warm-cache vs. cold-cache benchmark results.
29. Use JFR/GC logs to pinpoint allocation hotspots as message size increases.
30. Identify a case where enlarging input buffers does not help because the DB is the bottleneck.
31. Design graceful shutdown with a backlog and verify queue empty + in-flight zero.
32. Pick File/SFTP/TCP/JMS/AMQP/Kafka adapters when sessions, ACKs, or offsets are needed.

### Self-check questions

**Q1. What is `ByteStreamReadingMessageSource`'s default `bytesPerMessage`?**  
1024 bytes per the Spring Integration Stream Reference 6.5.

**Q2. Do constructor `ByteStreamReadingMessageSource(InputStream, int)` and `setBytesPerMessage(int)` mean the same thing?**  
No. The constructor's second parameter configures the source's internal buffer; the setter specifies how many bytes the source tries to read per `Message<byte[]>`.

**Q3. What does `setShouldTruncate(true)` do?**  
It ensures the payload reflects the exact number of bytes read when a read returns fewer bytes than the requested buffer size.

**Q4. Is a 16 KiB chunk automatically a JSON record?**  
No. Record boundaries are defined by framing/schemas, not chunk size.

**Q5. Does `QueueChannel(32)` hold at most 32 bytes or 32 messages?**  
32 waiting Spring messages, with varying payload sizes.

**Q6. Why can overly small buffers be slow?**  
They increase small reads/writes, Spring message counts, and dispatch/header/allocation overhead.

**Q7. Why can overly large buffers cause problems?**  
They raise peak memory, time-to-first-result, queued bytes, and GC pressure, hurting latency and fairness.

**Q8. Does an 8 KiB `BufferedReader` block a 100 MiB line?**  
No. You need an independent max line/record length limit.

**Q9. Does `flush()` mean fsync or remote ACK?**  
No. They are completely different levels of confirmation.

**Q10. Should you tune for throughput or latency?**  
Tune for your **system's SLO**, typically balancing throughput, P95/P99 latency, memory, errors, and durability.

**Q11. Is a poller required when `ByteStreamReadingMessageSource` connects to `DirectChannel`?**  
Yes. The pollable source needs an endpoint/poller; the downstream handler on `DirectChannel` does not need its own poller.

**Q12. Does raising `bytesPerMessage` automatically make DB batches larger?**  
No. Byte chunks and business records are different units.

**Q13. Can you retry `source.receive()` to recover a chunk rejected by a full queue?**  
Not by default. The `InputStream` has already advanced; you need a replayable source, staging, or checkpoints.

**Q14. Why must you test against real files/networks?**  
In-RAM tests do not faithfully reproduce OS I/O, networks, SDKs, encryption, latency, or caching under real workloads.

**Q15. Is EOF enough to declare a job completed while queues remain non-empty?**  
No. You must drain in-flight work, flush/close, and confirm commits per contract.

**Q16. What makes a performance evaluation untrustworthy?**  
Running only once, skipping output byte verification, measuring throughput while ignoring GC/latency/errors, or changing multiple parameters at once.

## 25. Takeaways

**Buffer size and performance** in Spring Integration is a **multi-layered** concern—not finding one magic number like 8192 or 65536 that "fits every system". `ByteStreamReadingMessageSource` provides a buffer-sizing constructor and `setBytesPerMessage(...)` (defaulting to **1024 bytes/message**); `ByteStreamWritingMessageHandler` provides `(OutputStream, bufferSize)`. For character streams, `BufferedReader`/`BufferedWriter` manage character buffers, while UTF-8 charsets and record lengths remain separate contracts.

**Core principles**:

1. Separate **I/O buffers**, **message chunks**, **queue capacity**, **record/frame sizes**, and **output buffers**; never mistake one knob for another.
2. **Never assume one read equals one record:** enable `shouldTruncate(true)` for exact bytes read, plus proper framing and decoders when text/JSON spans chunks.
3. **Measure before tuning:** track throughput, P99 latency, message rate, GC, peak RSS, memory backlog, and errors on the same workload.
4. **Maintain backpressure and reliability:** bound queues, use checkpoints/durable staging if source reads can be lost, and use event IDs/idempotency for retries.
5. **Shut down cleanly:** stop intake → drain → flush → close, and never equate `flush()` with `fsync` or a business ACK.

When the bottleneck lives in JDBC, TCP, SFTP, HTTP, JMS, AMQP, or Kafka, tuning that protocol/adapter layer helps far more than cranking up Java I/O buffers. Base final choices on your specific application's **SLOs and measurements**.

### References

- [Spring Integration 6.5 Reference — Stream Support](https://docs.spring.io/spring-integration/reference/6.5/stream.html)
- [Spring Integration 6.5 API — ByteStreamReadingMessageSource](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/ByteStreamReadingMessageSource.html)
- [Spring Integration 6.5 API — ByteStreamWritingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/ByteStreamWritingMessageHandler.html)
- [Spring Integration 6.5 API — CharacterStreamReadingMessageSource](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/CharacterStreamReadingMessageSource.html)
- [Spring Integration 6.5 API — CharacterStreamWritingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/CharacterStreamWritingMessageHandler.html)
- [Spring Integration 6.5 Reference — Message Channels](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html)
- [Spring Integration 6.5 Reference — Pollers](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html)
- [Java SE 17 — BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html)
- [Java SE 17 — BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html)
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [Java SE 17 — BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [Java SE 17 — FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean))
- [Oracle Java 17 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html)
