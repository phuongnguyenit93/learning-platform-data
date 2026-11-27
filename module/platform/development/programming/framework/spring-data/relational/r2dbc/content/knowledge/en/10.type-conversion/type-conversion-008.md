# Handling Binary Data, Blob, Clob, and Resource Lifecycle

In Spring Data Relational R2DBC, large binary and text data can be mapped to ordinary Java types such as `byte[]` and `String`, or handled as reactive `Blob` and `Clob` resources from the R2DBC SPI. The two approaches differ significantly in memory usage, how data is read, and connection lifecycle.

For small payloads, `byte[]` or `String` is usually simple and convenient. For large payloads, materializing the entire content onto the heap can create memory pressure. `Blob` and `Clob` enable streaming reads and writes, but they are handles tied to driver/database resources. The application must consume or discard them properly while the connection remains valid, and ensure cleanup runs when the publisher completes, errors, or is canceled.

## 1. Distinguishing Binary Data and Large Character Data

Databases provide multiple column types for storing large content. Exact names and behavior depend on the DBMS:

| Content type | Common Java type | Example SQL types | Characteristics |
|---|---|---|---|
| Small or medium binary data | `byte[]` | `BINARY`, `VARBINARY`, `BYTEA` | Entire content is held in a byte array |
| Large binary data | R2DBC `Blob` | `BLOB`, `BYTEA`, or database-specific LOB types | Can stream reads/writes of `ByteBuffer` chunks |
| Small or medium text | `String` | `VARCHAR`, `TEXT`, `CLOB` | Entire content is held in a Java string |
| Large text | R2DBC `Clob` | `CLOB`, `TEXT`, or large text types | Can stream reads/writes of `CharSequence` chunks |

For example, PostgreSQL typically uses `BYTEA` for binary data and `TEXT` for long text; MySQL has `BLOB` and `TEXT` variants; Oracle has LOB types such as `BLOB` and `CLOB`. How drivers expose these columns as `byte[]`, `String`, `Blob`, or `Clob` is not identical across implementations. Check the documentation for your specific database and R2DBC driver.

Do not pick a Java type solely from the SQL name. Verify driver support, maximum data size, data transfer mechanics, and the application's streaming requirements.

## 2. byte[] and String: The Simple Choice for Bounded Data

For a small image, hash, short document, or size-bounded text content, using `byte[]` and `String` can be an appropriate choice.

Entity example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("document_metadata")
public class DocumentMetadata {

    @Id
    private Long id;

    private String fileName;

    private String contentType;

    private byte[] preview;

    private String description;
}
```

`preview` holds binary data; `description` holds text. When the driver supports the corresponding mapping, Spring Data Relational can read and write these properties as ordinary values.

### 2.1. Advantages and limitations

Advantages:

- Simple Java model, easy to pass across layers.
- Easy to test and serialize when sizes are small.
- No need to manually manage LOB publishers.
- Suitable for metadata, thumbnails, or payloads with explicit size bounds.

Limitations:

- The entire content must be materialized in memory.
- `byte[]` requires a sufficiently large contiguous memory region.
- `String` also retains the entire content and carries JVM character representation overhead.
- When many requests download large files concurrently, heap usage can spike even when the database and connection pool appear healthy.
- Returning a `Mono<byte[]>` does not make reading data streaming merely because the API is reactive.

For example, if an endpoint serves an 80 MB file and has 30 concurrent requests, raw file content alone can require roughly 2.4 GB of memory, before accounting for object overhead, buffers, conversion copies, and other data. Therefore, enforce size limits when using `byte[]` or `String`.

### 2.2. Enforcing size limits

If business rules allow previews of at most 1 MB, validate the size before saving and before reading. Do not trust a client-supplied `Content-Length` header without verifying actual data size.

For text content, consider limits in both network bytes and decoded characters. UTF-8 byte counts differ from character counts, so the two limits are not identical.

## 3. Blob and Clob in the R2DBC SPI

The R2DBC SPI provides two abstractions for large content:

- `io.r2dbc.spi.Blob`: represents large binary content.
- `io.r2dbc.spi.Clob`: represents large character content.

These are reactive types. They are not simply a byte array or string already loaded entirely onto the heap.

Key APIs:

| Type | Reading content | Discarding content and releasing resources |
|---|---|---|
| `Blob` | `stream()` returns a publisher of `ByteBuffer` | `discard()` returns a publisher that completes once discarded |
| `Clob` | `stream()` returns a publisher of `CharSequence` | `discard()` returns a publisher that completes once discarded |

Usage signatures:

```java
import io.r2dbc.spi.Blob;
import io.r2dbc.spi.Clob;

Flux<ByteBuffer> binaryChunks = Flux.from(blob.stream());
Flux<CharSequence> textChunks = Flux.from(clob.stream());
```

`stream()` emits chunks reactively. One chunk does not necessarily correspond to one database row, one network packet, or a fixed size. The driver determines how data is chunked.

### 3.1. Blob for binary data

`Blob` fits content such as original images, PDFs, attachments, media files, or other large binary payloads.

```java
Publisher<ByteBuffer> source = ...;
Blob blob = Blob.from(source);
```

`Blob.from(...)` creates a Blob from a publisher of `ByteBuffer`s. The source publisher is consumed when the driver executes the write operation. Ensure the source can be subscribed to for the operation's lifecycle and do not reuse a one-shot source across multiple writes.

### 3.2. Clob for character data

`Clob` fits large text content such as article bodies, text documents, or long character data.

```java
Publisher<CharSequence> source = ...;
Clob clob = Clob.from(source);
```

Clob emits `CharSequence` chunks. Character encoding during transmission to the database is handled by the driver according to the driver and database contract. Do not manually convert each chunk into bytes using an arbitrary charset without confirming the encoding expected by the column and driver.

## 4. Streaming Reads of Blob and Clob

When reading a LOB, the application can retrieve `Blob` or `Clob` from a `Row`. Consume the stream while the connection remains active.

Example retrieving a `Blob` from a result row at the R2DBC SPI level:

```java
connection.createStatement("SELECT content FROM document WHERE id = $1")
    .bind(0, documentId)
    .execute();
```

The snippet above illustrates creating a statement using PostgreSQL's bind marker syntax. Marker names and positional binding conventions depend on the driver; this SQL syntax does not work across every DBMS.

A fuller streaming pattern keeps the connection open while chunks are consumed:

```java
Flux<ByteBuffer> streamDocument(
        ConnectionFactory connectionFactory,
        long documentId) {

    return Flux.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Flux.from(
                connection.createStatement(
                    "SELECT content FROM document WHERE id = $1")
                    .bind(0, documentId)
                    .execute())
            .concatMap(result -> Flux.from(result.map(
                (row, metadata) -> row.get("content", Blob.class))))
            .concatMap(blob -> Flux.from(blob.stream())),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

In this example:

- `ConnectionFactory.create()` provides a connection reactively.
- `Flux.usingWhen(...)` holds the connection open for as long as the data-reading publisher remains active.
- `Result.map(...)` extracts the `Blob` from the `content` column.
- `blob.stream()` emits `ByteBuffer` chunks.
- Cleanup closes/returns the connection when the stream completes, errors, or is canceled.

This example assumes the query returns one row with a non-null `content` column. Real code must handle missing rows, null columns, multiple rows, and the exact LOB representation returned by the driver.

**Do not retrieve a `Blob` from a query, emit that handle outside, and read its stream after the database operation has ended.** LOBs can depend on the connection or driver resources. Once the connection has been returned to the pool or closed, subsequent reads may fail. Always read or discard LOBs within an active connection scope.

### 4.1. When only needing to skip a LOB

If a query returns a LOB whose content business logic does not need, discard it rather than leaving an unused handle:

```java
Mono<Void> discardDocumentContent(Connection connection, long documentId) {
    return Flux.from(connection.createStatement(
            "SELECT content FROM document WHERE id = $1")
            .bind(0, documentId)
            .execute())
        .concatMap(result -> Flux.from(result.map(
            (row, metadata) -> row.get("content", Blob.class))))
        .concatMap(blob -> Mono.from(blob.discard()))
        .then();
}
```

`discard()` is a reactive operation and must be subscribed to / composed for resource release to finish. Calling the method without wiring its publisher into the pipeline does not guarantee resources are freed.

### 4.2. Clob must also be consumed within connection scope

The pattern for handling Clob mirrors Blob, except the stream emits `CharSequence`:

```java
Flux<CharSequence> streamDocumentText(
        ConnectionFactory connectionFactory,
        long documentId) {

    return Flux.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Flux.from(
                connection.createStatement(
                    "SELECT body FROM document_text WHERE id = $1")
                    .bind(0, documentId)
                    .execute())
            .concatMap(result -> Flux.from(result.map(
                (row, metadata) -> row.get("body", Clob.class))))
            .concatMap(clob -> Flux.from(clob.stream())),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

If the application must assemble the entire Clob into a single `String`, do so only when size is bounded. For large content, process chunk by chunk or write to an appropriate sink to avoid allocating a massive string on the heap.

## 5. Writing Blob and Clob

The R2DBC SPI lets you construct a Blob/Clob from a publisher to stream data into a statement.

### 5.1. Writing a Blob

```java
Mono<Long> saveBinary(
        DatabaseClient databaseClient,
        String fileName,
        Flux<ByteBuffer> content) {

    return Mono.defer(() -> {
        Blob blob = Blob.from(content);

        return databaseClient.sql("""
                INSERT INTO document(file_name, content)
                VALUES (:fileName, :content)
                """)
            .bind("fileName", fileName)
            .bind("content", blob)
            .fetch()
            .rowsUpdated();
    });
}
```

`Mono.defer` constructs the Blob when subscription begins, giving each execution a fresh source publisher as supplied by the caller. If `content` is a one-shot publisher or backed by an already-consumed stream, you cannot assume re-subscribing will yield the same content. Clarify how many times a source publisher may be consumed.

Binding `Blob` only works when the driver and database support the corresponding LOB type. For databases/drivers that only support binary data as `byte[]`, use that type or the driver's dedicated mechanism.

### 5.2. Writing a Clob

```java
Mono<Long> saveText(
        DatabaseClient databaseClient,
        String title,
        Flux<CharSequence> bodyChunks) {

    return Mono.defer(() -> {
        Clob clob = Clob.from(bodyChunks);

        return databaseClient.sql("""
                INSERT INTO article(title, body)
                VALUES (:title, :body)
                """)
            .bind("title", title)
            .bind("body", clob)
            .fetch()
            .rowsUpdated();
    });
}
```

In this example, `bodyChunks` supplies content in chunks. Verify whether the driver supports binding `Clob` and whether the `body` column has a matching type.

### 5.3. Do not convert the entire stream to byte[] before binding

If the data source is already a `Flux<ByteBuffer>`, calling `collectList()` or reducing into a `byte[]` before writing defeats streaming benefits. Materialize only when size is bounded and keeping the entire payload on the heap is an intentional choice.

## 6. Resource Lifecycle of Blob and Clob

LOBs must be treated as lifecycle-managed resources, not ordinary data objects to retain arbitrarily.

Key principles:

1. **Consume or discard.** After receiving a `Blob`/`Clob`, the application must read its stream or call `discard()` if the content is not needed.
2. **Keep the connection open as long as needed.** Some drivers require an open connection to read or write LOBs. Do not emit a handle outward and use it after the connection has been released.
3. **Compose reactive cleanup.** `stream()`, `discard()`, and `Connection.close()` are all publishers; wire them into the pipeline.
4. **Handle cancellation.** If a client aborts a download or a subscriber cancels, cleanup must run to release the LOB and connection.
5. **Do not reuse consumed handles.** LOB publishers may be single-use or tied to driver state; do not assume they can be subscribed to multiple times.
6. **Do not retain ByteBuffers longer than necessary.** Copy data if needed past the current signal, because buffers may be tied to the driver's memory management.

### 6.1. Why handle complete, error, and cancel alike?

Reactive pipelines have three important termination signals:

- `onComplete`: the stream finished reading normally.
- `onError`: the driver or application emitted an error while reading/writing.
- `cancel`: downstream no longer wants data, such as an HTTP client closing its connection.

If cleanup runs only on complete, errors or cancellations can leave connections or LOBs unreleased. Reactor's `usingWhen` operators support cleanup across all three signals.

Connection management skeleton example:

```java
Flux<ByteBuffer> content = Flux.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> readBlobChunks(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
```

The final three callbacks handle complete, error, and cancel, respectively. If an unconsumed LOB remains, the application should invoke driver-appropriate discard/cleanup before the connection is reused. Closing/returning the connection is typically the last line of defense, not a substitute for understanding the driver's LOB lifecycle.

### 6.2. Connection.close() when using a pool

When a connection is acquired from an R2DBC Pool, calling `close()` typically returns the connection to the pool for reuse rather than immediately closing the physical socket. The pool may validate or evict the connection afterward. When managing connections manually, use `ConnectionFactory`/the pool properly and never hold a connection across requests.

With `DatabaseClient`, Spring manages acquiring and releasing connections for ordinary operations. If LOB handling requires a live stream after a query emits results, design the operation so LOB consumption happens within the driver's connection scope. When fine-grained control over that scope is needed, direct R2DBC SPI APIs with `usingWhen` may be more suitable than a mapper returning a LOB handle.

## 7. Memory Bounds When Converting Data

There are three common processing patterns:

| Processing approach | Application memory | Best suited for |
|---|---|---|
| Reading into `byte[]` or `String` | Scales with total content size | Small, bounded data |
| Reading `Blob`/`Clob` by chunk and processing immediately | Can stay near the size of chunks/buffers in flight | Large content, streaming |
| Reading stream then `collectList()`/assembling into one object | Ultimately holds entire content in memory | Only when size is bounded and materialization is required |

Example converting a Blob stream into `byte[]`:

```java
Mono<byte[]> collectSmallBlob(Flux<ByteBuffer> chunks) {
    return chunks
        .reduce(new ByteArrayOutputStream(), (output, buffer) -> {
            ByteBuffer copy = buffer.slice();
            byte[] bytes = new byte[copy.remaining()];
            copy.get(bytes);
            output.write(bytes, 0, bytes.length);
            return output;
        })
        .map(ByteArrayOutputStream::toByteArray);
}
```

This code copies each chunk into a `ByteArrayOutputStream`, then builds a result array. This still materializes the full payload; use it only for small or size-bounded content. `ByteBuffer.slice()` reads a view of the remaining bytes without mutating the original buffer's position.

For large files, process each chunk and write to a streaming destination such as the file system, object storage, or an HTTP response. Avoid accumulating an entire file in `ByteArrayOutputStream` if your goal is conserving heap memory.

## 8. Integrating with WebFlux and Streaming Files to Clients

In a WebFlux application, you can return content as a stream to avoid allocating a massive byte array. However, bear in mind that the database connection may need to remain held for the duration of the client's download.

General flow:

```text
HTTP client
    |
    v
WebFlux handler
    |
    v
Reactive service
    |
    v
R2DBC connection held within usingWhen
    |
    v
Blob.stream() emits ByteBuffer chunks
    |
    v
Convert chunks to DataBuffer / response body
    |
    v
HTTP client receives content
    |
    v
Complete or cancel -> clean up LOB and connection
```

Spring WebFlux typically uses `DataBuffer` to write response bodies. When converting from `ByteBuffer`, use the appropriate buffer factory and follow `DataBuffer` ownership/release rules in your Spring version. Do not release buffers yourself or retain them longer than the framework/driver permits.

A very slow downloading client can prolong connection hold times. If files are large and concurrent downloads are high, this can exhaust the pool even when every SQL query is fast. Consider:

- Enforcing size limits and concurrent download limits.
- Configuring appropriate timeouts for file downloads.
- Using object storage/CDN for large or frequently downloaded files.
- Storing metadata in the database and file content in dedicated storage.
- If streaming from the database is required, monitoring connection hold time and pending acquires.

Storing files directly in the database is not always the best choice. Databases fit when you need transactional consistency between metadata and content, row-level data access permissions, unified backups, or specific business requirements. Object storage is typically better suited for very large files, frequent downloads, or CDN distribution.

## 9. Choosing Between byte[], Blob, String, and Clob

Choose based on size, driver support, and how the application consumes the data:

| Requirement | Usually suitable choice | Reason |
|---|---|---|
| Small thumbnail image | `byte[]` | Simple and size-bounded |
| Large file attachment | `Blob` | Chunked reads/writes, reduces materialization |
| Short description or note | `String` | Easy to manipulate and map |
| Very long text content | `Clob` | Can process by character chunks |
| Only file metadata needed | Regular columns such as name, MIME type, size, checksum | Avoids loading LOB content |
| Large files downloaded frequently | Object storage, database stores metadata | Reduces database connection hold time |

There is no single fixed size threshold for every application. Measure heap usage, concurrent requests, network speed, database latency, and conversion cost. A 100 KB payload may be safe to materialize in one workload, yet cause pressure under thousands of concurrent requests.

## 10. Mapping in Spring Data Relational and Driver Support

Spring Data Relational uses mapping metadata and converters to translate between entities and data types supported by the R2DBC driver. However, support for mapping `byte[]`, `String`, `Blob`, or `Clob` depends on the Spring Data version, R2DBC SPI, and driver.

Before placing a LOB directly on an entity, verify:

- Does the driver support the corresponding SQL type?
- Does the driver return `byte[]`/`String` or `Blob`/`Clob`?
- Does Spring Data conversion transform that type automatically?
- Does the mapping consume the LOB within an appropriate connection scope?
- Are custom converters or direct `DatabaseClient`/R2DBC SPI operations required?

If custom conversion is needed, register converters via `R2dbcCustomConversions` using Spring Data R2DBC's configuration mechanism. Converters must respect reactive semantics and LOB lifecycles. Do not write synchronous converters calling `block()` to gather an entire LOB into a `byte[]` when payloads may be large.

JPA has an `@Lob` annotation, but do not assume that JPA annotation controls R2DBC mapping. Spring Data Relational uses its own mapping and converters. Use types and annotations supported by Spring Data Relational/R2DBC, and verify behavior against the real driver.

With `DatabaseClient`, application-written mappers can explicitly read `byte[]`, `String`, `Blob`, or `Clob`:

```java
databaseClient.sql("SELECT id, content FROM document WHERE id = :id")
    .bind("id", documentId)
    .map((row, metadata) -> row.get("content", byte[].class))
    .one();
```

This example is appropriate only when the driver supports returning the `content` column as `byte[]` and payload sizes are small enough. If the driver returns a LOB handle, read the stream within connection scope rather than assuming `row.get(..., byte[].class)` always converts.

## 11. Handling Binary Data Safely

Binary data is frequently client-uploaded files. Beyond mapping and streaming, the application must verify size, content type, and access permissions accurately.

Practical guidelines:

- Do not trust client-supplied filenames or MIME types; validate against application policies.
- Enforce upload size limits before content consumes excessive resources.
- Compute checksums while streaming if needed to detect corrupted payloads or support deduplication.
- Never log raw content bytes, tokens, or sensitive data.
- Do not buffer an entire upload in memory when you already have a `Flux<ByteBuffer>` source.
- Specify encoding explicitly when converting character data to bytes and vice versa.
- For structured files, inspect actual file format rather than relying solely on file extensions.
- Consider encryption at rest, access permissions, and retention/deletion policies.

If content is stored in the database alongside metadata, decide whether a transaction needs to cover both operations. With object storage, the database and object store typically do not share an ACID transaction; design upload states, orphan file cleanup, and retry/idempotency appropriately.

## 12. Error Handling and Cancellation When Reading/Writing LOBs

LOB streaming can fail mid-stream due to network resets, database timeouts, client disconnects, or buffer read errors. Errors may occur after some chunks have already been sent downstream.

The application must:

1. Let errors propagate through the reactive pipeline.
2. Ensure LOB and connection cleanup runs on error or cancel.
3. Never return a file marked as complete if the stream was interrupted mid-way.
4. When writing to an external system, write to a temporary file or temporary object key and publish only upon completion.
5. If retry is required, decide whether to restart from the beginning or support resume/range requests.
6. For database writes, determine whether the transaction committed before retrying to avoid duplicate records or files.

For large payloads, retrying an entire stream can be costly. If the system needs to resume downloads from a read offset, design a resume, offset, or multipart upload protocol; R2DBC `Blob`/`Clob` do not automatically provide a generic business-level resume mechanism.

## 13. Testing and Observability

LOB testing must run against a real database and driver because representation and streaming depend on the implementation.

Scenarios to test:

- Saving and reading a small Blob using a driver-supported type.
- Saving and reading a large Blob across multiple chunks.
- Saving and reading a Clob containing Unicode characters, Vietnamese diacritics, and multi-byte characters.
- Empty content and nullable columns.
- Canceling a subscription mid-stream.
- Connection drops or timeouts during reads/writes.
- Discarding a LOB that the application does not need to consume.
- Confirming connections return to the pool after complete, error, and cancel.
- Streaming many LOBs concurrently and observing heap, GC, pool acquires, and connection hold time.

Metrics to monitor:

| Metric | Meaning |
|---|---|
| Content size | Detects payloads exceeding limits |
| Chunk count and chunk size | Reveals how the driver segments data |
| Stream duration | Distinguishes slow database from slow downstream |
| Connection hold time | Duration a connection is held while transferring a LOB |
| Pool pending acquires | Detects LOB streams holding too many connections |
| Heap/GC | Detects accidental materialization of full content |
| Stream cancellations and errors | Assesses cleanup effectiveness and stability |

Do not merely check that the returned file has the right content. Verify that the application does not leak connections or retain buffers after the stream finishes.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Reading large files into `byte[]` | Heap grows with file size and request count | Use `Blob.stream()` or object storage |
| Gathering all chunks with `collectList()` | Defeats streaming and retains data in memory | Process chunk by chunk or write to a sink |
| Emitting `Blob` outward and reading after connection release | LOB may no longer be accessible | Consume LOB within connection scope |
| Not calling `discard()` when skipping a LOB | Driver/database resources may remain unreleased | Compose `discard()` into the pipeline |
| Calling `discard()` without subscribing | Cleanup publisher never executes | Wire publisher into pipeline or await in reactive flow |
| Cleaning up only on complete | Errors/cancellations can leak resources | Use `usingWhen` and clean up across all three signals |
| Retaining `ByteBuffer` for later use | Buffer may be tied to driver lifecycle | Process immediately or copy data that must be kept |
| Assuming all drivers support Blob/Clob identically | Runtime mapping or bind errors | Check driver docs and integration tests |
| Using JPA `@Lob` to configure R2DBC | Annotation may have no effect in R2DBC mapping | Use types and conversions supported by Spring Data Relational |
| Streaming slow files through a small connection pool | Connections held too long; other requests wait on acquire | Limit concurrency, stream duration, or move files to object storage |
| Retrying non-idempotent write streams | May write duplicate content or partial states | Use transactions, idempotency keys, and clear upload workflows |

## 15. Selection and Implementation Workflow

When designing features to store or serve large data, follow this sequence:

1. **Identify data type:** binary or text, whether raw bytes must be preserved or character handling is needed.
2. **Identify sizes:** average size, maximum size, and expected concurrent requests.
3. **Check database and driver:** SQL types, supported Java types, and Blob/Clob streaming capabilities.
4. **Choose representation:** `byte[]`/`String` for small bounded content; `Blob`/`Clob` or object storage for large content.
5. **Design connection scope:** hold the connection while reading/writing the LOB and release on complete/error/cancel.
6. **Design load limits:** upload size, concurrency, timeouts, pool capacity, and stream duration.
7. **Design error handling and consistency:** cleanup, retries, idempotency, and incomplete file handling.
8. **Test with the real driver:** verify mapping, streaming, Unicode, cancellation, and resource release.
9. **Monitor production:** heap, GC, file sizes, connection hold time, pending acquires, and stream errors.

## 16. Principles to Remember

- `byte[]` and `String` are simple but materialize full content; use only when size is bounded.
- `Blob` represents large binary data and emits `ByteBuffer`s as a reactive stream.
- `Clob` represents large character data and emits `CharSequence`s as a reactive stream.
- Driver/database capabilities dictate LOB support and mapping; do not assume all drivers behave alike.
- Consume or discard LOBs while the connection remains active.
- Never emit a LOB handle outside connection scope and read its stream afterward.
- Use `usingWhen` or equivalent resource management to clean up on complete, error, and cancel.
- Never call `block()` to consume a LOB inside a reactive pipeline.
- Avoid `collectList()` or assembling full content when streaming is the goal.
- Monitor connection hold times because slow downloading clients can exhaust the pool.
- Consider object storage for large files, frequent downloads, or CDN needs.
- Test with the real database and driver, including cancellation and cleanup.

Handling LOBs in Spring Data R2DBC is not just choosing between `byte[]`, `Blob`, or `Clob`. What matters is balancing payload size, how the driver transfers content, memory consumption, and connection lifecycle. Small bounded data usually suits standard Java types; large data requires streaming, reactive cleanup, and explicit load limits so the application does not hold connections or memory longer than necessary.
