# Verifying Large Uploads and Downloads Without Buffering Entire Files in Memory

In **Spring WebFlux**, handling large files requires keeping data streaming from the moment a request arrives until it is written to storage, and from reading storage until sending the response. The goal is for memory to hold only a bounded number of buffers, rather than creating a byte array or list containing the entire file.

There are three common upload options:

- **`FilePart.transferTo(Path)`**: fits standard multipart forms. The multipart reader can spill large file parts to temporary files based on configured thresholds; the application moves the file to its final storage location.
- **`Flux<PartEvent>`**: processes multipart sequentially event by event and buffer by buffer. This is the choice for direct streaming, handling many parts, or relaying data without collecting the whole multipart body into a map.
- **`@RequestBody Flux<DataBuffer>`**: fits raw uploads whose body is a byte stream, such as `application/octet-stream`.

For downloads, you can return `FileSystemResource` so the Resource message writer reads the file incrementally, or construct a `Flux<DataBuffer>` via `DataBufferUtils.read` and write it to the response. Clients must also consume the response as a stream, such as `bodyToFlux(DataBuffer.class)`, writing each buffer to disk.

This lesson focuses on designing, verifying, and operating large upload/download streams, including backpressure, buffering, checksums, multipart limits, cancellation, error handling, and tests that do not aggregate responses into RAM.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish streaming uploads/downloads from reading the entire file into `byte[]`.
2. Use `FilePart.transferTo` to store multipart files with bounded RAM usage.
3. Use `Flux<PartEvent>` to process multipart part by part and buffer by buffer.
4. Use `Flux<DataBuffer>` and `DataBufferUtils.write/read` for raw uploads/downloads.
5. Return `Resource` so WebFlux writes large files as a stream.
6. Preserve backpressure by returning publishers and avoiding manual `block()`/`subscribe()`.
7. Manage DataBuffer ownership, release buffers promptly, and handle cancellation.
8. Configure memory thresholds, disk quotas, part counts, and request limits.
9. Verify content via chunked size and SHA-256 calculation.
10. Write WebTestClient tests for large uploads/downloads without using `expectBody(byte[].class)` to aggregate the response.
11. Distinguish functional tests from real memory measurement using load tests, JFR, and metrics.

## 2. Why Should You Avoid Buffering the Whole File in RAM?

The simple but dangerous approach is reading the entire request body into a byte array:

~~~java
@PostMapping("/upload")
Mono<String> upload(@RequestBody Mono<byte[]> body) {
    return body.flatMap(bytes -> {
        // Write all bytes to a file.
        return save(bytes);
    });
}
~~~

With a 500 MiB file, this approach can require an array of at least 500 MiB per request, before counting copies, object overhead, the multipart parser, and concurrent requests. Ten concurrent requests can create gigabytes of pressure.

A similar mistake on the download side is:

~~~java
byte[] bytes = Files.readAllBytes(path);
return ResponseEntity.ok(bytes);
~~~

It loads the entire file onto the heap before the response is sent.

The streaming approach maintains a small sequence of buffers:

~~~text
Upload:
HTTP chunks
   |
   v
WebFlux DataBuffer stream
   |
   v
FilePart / PartEvent / Flux<DataBuffer>
   |
   v
File writer
   |
   v
Disk

Download:
Disk
   |
   v
Resource writer / DataBufferUtils.read
   |
   v
DataBuffer stream
   |
   v
HTTP response chunks
   |
   v
Client
~~~

When downstream is slow, backpressure keeps upstream from emitting data unboundedly. Memory usage generally depends on buffer size, queued buffer count, prefetch level, concurrent requests, and intermediate layers. Streaming dramatically lowers heap requirements, though it does not automatically cap total file size, disk usage, or concurrency.

## 3. Upload Approaches in Spring WebFlux

### 3.1. Multipart with FilePart

For browser forms or REST multipart requests, receive the file via `FilePart`:

~~~java
@PostMapping(
    path = "/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<UploadReceipt> upload(@RequestPart("file") FilePart file) {
    Path destination = createServerSidePath();

    return file.transferTo(destination)
        .then(Mono.fromCallable(() -> inspect(destination)));
}
~~~

`FilePart.transferTo(Path)` returns `Mono<Void>`. The publisher completes once the file has been transferred to the destination or emits an error. The code never turns the file into a `byte[]`.

With the default multipart reader, file parts exceeding `maxInMemorySize` are written to temporary disk storage; thus this is a bounded-memory model that may use temporary disk space. The application then moves the part to its final storage location. Account for potential disk spikes while both the temporary file and final file exist simultaneously.

Advantages:

- Short, readable controller API.
- Suits multipart forms with metadata and a few files.
- No need to manage individual DataBuffers manually.
- Easy to combine with validation and form fields.

Limitations:

- The multipart reader still has to parse the request structure.
- With named-part access or multi-part maps, the framework may need to parse and retain metadata/part collections.
- If you need to process each part immediately on arrival or relay large files directly, `PartEvent` fits better.

### 3.2. Multipart Streaming with PartEvent

Spring WebFlux supports `@RequestBody Flux<PartEvent>` for sequential multipart processing. A form field emits a `FormPartEvent`; a file upload emits one or more `FilePartEvent` instances. Large files can be split across many DataBuffer events.

The final event of each part has `isLast() == true`. You can use `windowUntil(PartEvent::isLast)` to split the stream by part, followed by `switchOnFirst` to determine whether a part is a field or a file.

~~~java
@PostMapping(
    path = "/streaming-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<Void> uploadStreaming(@RequestBody Flux<PartEvent> allEvents) {
    return allEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
            partEvents.switchOnFirst((signal, events) -> {
                if (!signal.hasValue()) {
                    return events.then();
                }

                PartEvent event = signal.get();

                if (event instanceof FormPartEvent formEvent) {
                    String value = formEvent.value();

                    // Process field; consume/release content buffer.
                    return events
                        .map(PartEvent::content)
                        .doOnNext(DataBufferUtils::release)
                        .then();
                }

                if (event instanceof FilePartEvent fileEvent) {
                    String originalFilename = fileEvent.filename();

                    // Choose a server-generated destination, never use filename as path.
                    Path destination = createServerSidePath();

                    Flux<DataBuffer> content =
                        events.map(PartEvent::content);

                    // The Path overload consumes and releases written buffers.
                    return DataBufferUtils.write(content, destination);
                }

                return Mono.error(
                    new IllegalArgumentException("Unsupported part event")
                );
            })
        )
        .then();
}
~~~

This snippet illustrates how to structure streaming; helper functions for path generation, permission checks, metadata persistence, and failed-file cleanup must be implemented by the application. Never use `originalFilename` as a filesystem path. When processing `PartEvent`, you must consume, relay, or release content buffers for every part, even unused fields; ignoring buffers can cause leaks.

Use `concatMap` to process parts sequentially when ordering and bounded concurrency matter. If processing in parallel, account for part order, disk I/O, open file limits, and concurrently held buffers.

### 3.3. Raw Upload with Flux<DataBuffer>

If the client sends a raw byte stream instead of multipart, the controller can accept `Flux<DataBuffer>`:

~~~java
@PostMapping(
    path = "/raw",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
Mono<Void> uploadRaw(@RequestBody Flux<DataBuffer> body) {
    Path destination = createServerSidePath();
    return DataBufferUtils.write(body, destination);
}
~~~

`DataBufferUtils.write(Publisher<DataBuffer>, Path)` returns `Mono<Void>` completing when writing finishes. The Path overload manages releasing written buffers. If you use an overload taking a channel or OutputStream, read its contract carefully: some overloads return a Flux of buffers and do not release them automatically.

Raw uploads carry no part names, filenames, or multipart metadata. If file metadata is needed, pass it via headers or a separate endpoint and validate it.

## 4. FilePart.transferTo and File Storage Location

### 4.1. Never Use Client-Sent Filenames as Paths

Filenames in multipart requests are client-controlled data. Never write:

~~~java
Path destination = uploadDirectory.resolve(file.filename());
~~~

Names can contain path separators, traversal sequences, or special characters. Instead, generate an ID on the server:

~~~java
UUID id = UUID.randomUUID();
Path destination = uploadDirectory.resolve(id + ".bin");
~~~

If you need to keep the original name for display, store it separately as validated metadata; never use it to determine the storage path.

### 4.2. Creating Directories and Performing Blocking I/O

Operations such as `Files.createDirectories`, `Files.size`, and reading checksums through `InputStream` are blocking. In WebFlux, never run them directly on the event loop. Use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` for blocking I/O blocks.

`FilePart.transferTo` is a reactive API; return the publisher and compose it with subsequent steps:

~~~java
return Mono.fromCallable(() -> Files.createDirectories(uploadDirectory))
    .subscribeOn(Schedulers.boundedElastic())
    .then(file.transferTo(destination))
    .then(Mono.fromCallable(() -> inspect(destination))
        .subscribeOn(Schedulers.boundedElastic()));
~~~

Do not call `block()` or manually `subscribe()` inside the controller to wait for file writes. When returning the publisher, WebFlux manages subscriptions, errors, and cancellation tied to the request.

### 4.3. Verifying the File After Upload

Do not rely solely on `transferTo` completing. A receipt can include a server-generated ID, byte size, and SHA-256 hash.

To compute SHA-256 for large files, read the file in chunks:

~~~java
static String sha256(Path path) throws IOException {
    MessageDigest digest;
    try {
        digest = MessageDigest.getInstance("SHA-256");
    }
    catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException(ex);
    }

    try (InputStream input = Files.newInputStream(path)) {
        byte[] chunk = new byte[64 * 1024];
        int read;

        while ((read = input.read(chunk)) != -1) {
            digest.update(chunk, 0, read);
        }
    }

    return HexFormat.of().formatHex(digest.digest());
}
~~~

Only 64 KiB is held in the read array at a time. Never use `Files.readAllBytes` or allocate a buffer equal to the entire file size to compute a hash.

Size and checksums help verify integrity after writing. If the client sends an expected checksum, compare it against the server-computed checksum before marking the file ready.

## 5. Downloading Large Files

### 5.1. Returning FileSystemResource

A simple way to serve files from disk is returning `FileSystemResource`:

~~~java
@GetMapping("/{id}")
Mono<ResponseEntity<Resource>> download(@PathVariable UUID id) {
    Path path = uploadDirectory.resolve(id + ".bin");

    return Mono.fromCallable(() -> {
        if (!Files.isRegularFile(path)) {
            return ResponseEntity.<Resource>notFound().build();
        }

        Resource resource = new FileSystemResource(path);

        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .contentLength(Files.size(path))
            .header(
                HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                    .filename(id + ".bin")
                    .build()
                    .toString()
            )
            .body(resource);
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

`ResourceHttpMessageWriter` reads the Resource and writes content as a stream. There is no need to allocate a `byte[]` holding the entire file. `Files.size` is invoked on boundedElastic because it is a filesystem operation.

Use `Resource` when you simply need to serve a file. Use `DataBufferUtils.read` when you need to control chunk sizes, transform bytes, or integrate with a byte-level pipeline.

### 5.2. Downloading with DataBufferUtils.read

When you need control over chunk size or the response pipeline, you can read the file as a Flux<DataBuffer>:

~~~java
@GetMapping("/stream/{id}")
Mono<Void> downloadStream(
        @PathVariable UUID id,
        ServerWebExchange exchange) {

    Path path = uploadDirectory.resolve(id + ".bin");

    return Mono.fromCallable(() -> Files.size(path))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(size -> {
            ServerHttpResponse response = exchange.getResponse();

            response.getHeaders().setContentType(
                MediaType.APPLICATION_OCTET_STREAM
            );
            response.getHeaders().setContentLength(size);

            Flux<DataBuffer> body = DataBufferUtils.read(
                path,
                response.bufferFactory(),
                64 * 1024
            );

            return response.writeWith(body);
        });
}
~~~

This snippet assumes the file already exists; applications must handle `NoSuchFileException` and return 404 per the API contract. `DataBufferUtils.read` reads the file into buffers of up to roughly 64 KiB each. `writeWith` consumes the publisher and writes to the response; once buffers are handed to the response writer, the controller must not release them again.

### 5.3. Content-Length, Chunked Transfer, and Ranges

- If the file size is known, set `Content-Length` so clients know the expected byte count.
- If the size is unknown upfront or the stream is generated dynamically, the server can use the transfer framing appropriate for the HTTP version.
- If resuming is supported, design Range/Content-Range and 206 Partial Content properly according to standard. Never return 206 unless you actually slice the requested byte range.
- For static files or object storage, consider dedicated file/range serving mechanisms instead of reimplementing the entire protocol yourself.

## 6. Streaming Uploads and Downloads with WebClient

Clients can also accidentally buffer entire bodies into RAM.

### 6.1. Uploading from a Resource

You can send multipart data with `FileSystemResource`:

~~~java
Mono<UploadReceipt> result = webClient.post()
    .uri("/api/files")
    .body(BodyInserters.fromMultipartData(
        "file",
        new FileSystemResource(sourcePath)
    ))
    .retrieve()
    .bodyToMono(UploadReceipt.class);
~~~

The Resource is read incrementally to produce the request body. Avoid reading the file first with `Files.readAllBytes` and sending a byte array.

### 6.2. Downloading into a File

Do not use `bodyToMono(byte[].class)` for large files. Use `bodyToFlux(DataBuffer.class)` and `DataBufferUtils.write`:

~~~java
Mono<Void> download = webClient.get()
    .uri("/api/files/{id}", id)
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .as(buffers -> DataBufferUtils.write(buffers, destination));
~~~

The Path overload completes once buffers have been written and released. The publisher only runs when subscribed to; return the publisher to the caller so lifecycle and cancellation are managed.

If you need to handle HTTP errors before writing the file, use `exchangeToMono`/`exchangeToFlux` to inspect the status and choose how to consume the body appropriately. Never ignore error response bodies without releasing/consuming them properly.

## 7. Multipart Limits and Resource Bounds

Streaming does not mean removing all limits. An upload might consume very little heap while still filling the disk, holding file descriptors, or saturating bandwidth for too long.

With Spring Boot WebFlux, multipart properties can be configured in `application.properties`:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=1GB
spring.webflux.multipart.max-parts=10
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.file-storage-directory=./var/multipart-tmp
~~~

Meaning:

| Property | Meaning |
| --- | --- |
| max-in-memory-size | Memory threshold for non-file parts; for file parts, the threshold before spilling content to disk. |
| max-disk-usage-per-part | Disk limit for each part saved to disk. |
| max-parts | Limit on the number of parts in one multipart request. |
| max-headers-size | Limit on header size per part. |
| file-storage-directory | Directory for temporary parts exceeding the memory threshold. |

These settings are not total request size limits across every layer. Also set limits at the reverse proxy/gateway, server connector, and business layer. Check disk quotas and temp directory permissions. Ensure the storage directory exists and the process has write permission.

With `PartEvent` streaming, part content is handled directly per event; the multipart reader's temporary file mechanism does not apply in the same way. In that mode, the application is responsible for consuming/relaying/releasing buffers and managing destination files.

### 7.1. maxInMemorySize Is Not Total File Size

Do not interpret `max-in-memory-size=256KB` as "maximum file upload 256 KiB". With the default multipart reader:

- Non-file parts exceeding the limit may be rejected.
- File parts exceeding the threshold are written to disk.
- Separate disk quotas govern how much part data can be stored.
- max-parts limits the number of parts, not bytes.
- Gateway/server still need limits on total request size and receive duration.

If `max-in-memory-size=-1` is set, content may be retained completely in memory; this is unsuitable for large files in production.

### 7.2. Concurrency Limits and Timeouts

Beyond file size, manage concurrent uploads/downloads, minimum transfer rates or maximum receive durations, temporary file counts and free disk space, open file descriptors/channels, retries and connection hold durations, per-user/tenant quotas, and cleanup of incomplete uploads.

Do not set concurrency too high simply because each request uses little heap. Disk I/O, network, and file descriptors still have finite limits.

## 8. Backpressure, Cancellation, and DataBuffer Ownership

### 8.1. Keep the Pipeline Reactive

For backpressure to take effect:

- Return Mono/Flux from controllers/services.
- Use publisher composition operators like map, flatMap, concatMap, and then.
- Never subscribe manually to run in the background.
- Never collect all DataBuffers into a List.
- Never call join on an entire large file.
- Never cache body streams without explicit bounds and a clear reason.

`collectList()`, `reduce` into one large array, or `DataBufferUtils.join` on the entire body turns streaming into aggregation. Use them only when data is small and bounded with enforced limits.

### 8.2. Release Buffers According to Ownership

Some servers such as Reactor Netty use pooled, reference-counted DataBuffers. When your code receives DataBuffers directly:

- If you consume them yourself without passing them to another writer, release after reading finishes.
- If you pass the publisher to `DataBufferUtils.write(Path)`, that overload manages releasing written buffers.
- If you pass buffers to `response.writeWith`, the response writer takes over writing and releasing per contract; the controller must not release them again.
- If you use a `DataBufferUtils.write` overload taking a channel or OutputStream, read its contract because some overloads return buffers and do not release them automatically.
- If buffers can be discarded due to filter, skip, error, or cancellation, custom pipelines need appropriate cleanup such as `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` in the right place.

Never release twice and never use a buffer after releasing it. Buffer ownership is the responsibility of the code that received or transferred it.

### 8.3. Cancellation

Clients can disconnect mid-transfer. When that happens, the publisher may receive cancellation; the file being written may be incomplete.

Applications should let cancellation propagate through the publisher chain, close channels/streams when the publisher terminates or is canceled, mark incomplete files or write to a temporary name, rename to the official file only after upload completes and checksum matches, clean up partial files via cleanup logic or scheduled maintenance, and never mark file metadata as ready before writing finishes.

A safe pattern is writing to a file with a temporary suffix, verifying size/checksum, and then moving/renaming to the official location. If an atomic move is needed, verify filesystem support and that source and destination share the same filesystem.

## 9. Verifying Content Without Loading the Whole File into RAM

### 9.1. Size

After the upload finishes, use `Files.size(path)` to retrieve the byte count. Size should be compared against Content-Length or client-sent metadata, though client values must never be trusted without actual verification.

### 9.2. Checksum

Compute SHA-256 in chunks using `MessageDigest.update(byte[], offset, length)` or `update(ByteBuffer)`. For download streams, update the digest per DataBuffer and release each buffer immediately.

### 9.3. Comparing Source and Destination

For a transfer test:

1. Create a source file by writing small blocks.
2. Compute the source file's SHA-256 via streaming.
3. Upload the source as a Resource.
4. Compare size and checksum in the receipt.
5. Download the stored file as Flux<DataBuffer>.
6. Accumulate byte count and update checksum as each buffer arrives.
7. Release each buffer immediately after reading.
8. Compare the final byte count and checksum against the source.

This verifies content end-to-end without holding the entire source file or response in RAM. Checking only status 200/201 can miss truncated or corrupted files.

### 9.4. Verifying Response Headers

Download tests should verify status 200 for existing files, the right Content-Type, Content-Length matching actual size, appropriate Content-Disposition if the API requires attachment, status 404 for nonexistent IDs, and if Range is supported, test 206, Content-Range, and returned byte counts.

## 10. Runnable Java 17 Example: Large File Upload and Download

This example uses Java 17, Spring Boot 3.3.5, and WebFlux. Files are stored in the demo's own temporary directory; production should use storage with clear quotas, permissions, and lifecycle management.

### 10.1. Project Structure

~~~text
large-file-demo/
├── build.gradle
├── src/main/resources/application.properties
├── src/main/java/demo/LargeFileApplication.java
├── src/main/java/demo/FileController.java
└── src/test/java/demo/FileTransferTest.java
~~~

### 10.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 10.3. application.properties

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=1GB
spring.webflux.multipart.max-parts=10
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.file-storage-directory=./var/multipart-tmp
~~~

### 10.4. LargeFileApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LargeFileApplication {

    public static void main(String[] args) {
        SpringApplication.run(LargeFileApplication.class, args);
    }
}
~~~

### 10.5. FileController.java

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

record UploadReceipt(UUID id, long sizeBytes, String sha256) {}

@RestController
@RequestMapping("/api/files")
class FileController {

    static final Path STORAGE_DIR = Path.of(
        System.getProperty("java.io.tmpdir"),
        "webflux-large-file-demo"
    );

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file) {

        UUID id = UUID.randomUUID();
        Path destination = STORAGE_DIR.resolve(id + ".bin");

        return Mono.fromCallable(() -> Files.createDirectories(STORAGE_DIR))
            .subscribeOn(Schedulers.boundedElastic())
            .then(file.transferTo(destination))
            .then(Mono.fromCallable(() -> {
                long size = Files.size(destination);
                String hash = sha256(destination);
                return new UploadReceipt(id, size, hash);
            }).subscribeOn(Schedulers.boundedElastic()))
            .map(receipt -> ResponseEntity
                .created(URI.create("/api/files/" + id))
                .body(receipt));
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<Resource>> download(
            @PathVariable UUID id) {

        Path path = STORAGE_DIR.resolve(id + ".bin");

        return Mono.fromCallable(() -> {
            if (!Files.isRegularFile(path)) {
                return ResponseEntity.<Resource>notFound().build();
            }

            Resource resource = new FileSystemResource(path);

            return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(Files.size(path))
                .header(
                    HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                        .filename(id + ".bin")
                        .build()
                        .toString()
                )
                .body(resource);
        }).subscribeOn(Schedulers.boundedElastic());
    }

    private static String sha256(Path path) throws IOException {
        final MessageDigest digest;

        try {
            digest = MessageDigest.getInstance("SHA-256");
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }

        try (InputStream input = Files.newInputStream(path)) {
            byte[] chunk = new byte[64 * 1024];
            int read;

            while ((read = input.read(chunk)) != -1) {
                digest.update(chunk, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Key points in the controller:

- The ID is server-generated; client filenames are never used as paths.
- `FilePart.transferTo` writes the file without allocating a byte array equal to file size.
- `Files.size` and SHA-256 calculation are blocking file I/O, so they run on boundedElastic.
- `FileSystemResource` is handed to the writer; WebFlux reads the file as a stream.
- The receipt includes size and checksum so clients/tests can verify integrity.
- The demo omits database persistence, antivirus scanning, authorization, and failed-file cleanup; add those steps per real storage policies.

### 10.6. FileTransferTest.java

The following test creates an 8 MiB source file using 64 KiB buffers, sends it as a FileSystemResource, then receives the download response chunk by chunk as DataBuffers. The test only sums bytes and updates a digest; it does not use `expectBody(byte[].class)` to aggregate the response.

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class FileTransferTest {

    @Autowired
    WebTestClient client;

    @Test
    void uploadsAndDownloadsLargeFileAsAStream() throws Exception {
        Path source = Files.createTempFile("large-source-", ".bin");
        UUID uploadedId = null;

        try {
            long expectedSize = createLargeFile(source, 8L * 1024 * 1024);
            String expectedHash = sha256(source);

            UploadReceipt receipt = client.post()
                .uri("/api/files")
                .body(BodyInserters.fromMultipartData(
                    "file",
                    new FileSystemResource(source)
                ))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(UploadReceipt.class)
                .returnResult()
                .getResponseBody();

            assertNotNull(receipt);
            uploadedId = receipt.id();

            assertEquals(expectedSize, receipt.sizeBytes());
            assertEquals(expectedHash, receipt.sha256());

            FluxExchangeResult<DataBuffer> download = client.get()
                .uri("/api/files/{id}", uploadedId)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.APPLICATION_OCTET_STREAM
                    )
                .expectHeader()
                    .contentLength(expectedSize)
                .returnResult(DataBuffer.class);

            MessageDigest downloadedDigest =
                MessageDigest.getInstance("SHA-256");

            Mono<Long> downloadedBytes = download.getResponseBody()
                .map(buffer -> {
                    try {
                        int count = buffer.readableByteCount();
                        ByteBuffer view = buffer.asByteBuffer();
                        downloadedDigest.update(view);
                        return (long) count;
                    }
                    finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .reduce(0L, Long::sum);

            StepVerifier.create(downloadedBytes)
                .expectNext(expectedSize)
                .verifyComplete();

            String downloadedHash =
                HexFormat.of().formatHex(downloadedDigest.digest());

            assertEquals(expectedHash, downloadedHash);
        }
        finally {
            Files.deleteIfExists(source);

            if (uploadedId != null) {
                Files.deleteIfExists(
                    FileController.STORAGE_DIR.resolve(uploadedId + ".bin")
                );
            }
        }
    }

    private static long createLargeFile(Path path, long size)
            throws IOException {

        byte[] chunk = new byte[64 * 1024];

        for (int i = 0; i < chunk.length; i++) {
            chunk[i] = (byte) (i % 251);
        }

        try (OutputStream output = Files.newOutputStream(path)) {
            long written = 0;

            while (written < size) {
                int count = (int) Math.min(
                    chunk.length, size - written
                );
                output.write(chunk, 0, count);
                written += count;
            }
        }

        return size;
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest =
            MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] chunk = new byte[64 * 1024];
            int read;

            while ((read = input.read(chunk)) != -1) {
                digest.update(chunk, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

The test does not store the response into a byte array. Each DataBuffer is counted, fed into SHA-256, and immediately released. `StepVerifier` confirms the total byte count equals the source size and the final checksum matches. The upload source is a Resource on disk, not an 8 MiB byte array.

### 10.7. Running the Application and Tests

Run tests:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

Run the server:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

The test above verifies the data path and integrity. It does not by itself prove an absolute heap ceiling; to measure real memory usage, run concurrent load with large files and observe heap/direct memory.

## 11. Testing with WebTestClient Without Accidentally Aggregating

### 11.1. Avoid expectBody(byte[])

This aggregates the response in memory:

~~~java
.expectBody(byte[].class)
~~~

It works for small responses, but it is not the way to test multi-gigabyte downloads.

Instead, receive the stream:

~~~java
FluxExchangeResult<DataBuffer> result =
    client.get()
        .uri("/api/files/{id}", id)
        .exchange()
        .expectStatus().isOk()
        .returnResult(DataBuffer.class);
~~~

Then consume each buffer, compute byte counts/checksums, and release the buffers.

### 11.2. Testing Uploads with Resource

Use `FileSystemResource` in the multipart inserter. Avoid `Files.readAllBytes(sourcePath)` and `bodyValue(byteArray)` in large-file tests, because the test client itself would allocate a huge array.

### 11.3. Testing Cancellation and Errors

Alongside the happy path, write tests for nonexistent file IDs, clients canceling downloads mid-stream, uploads exceeding disk/part limits, multipart requests missing the file, write errors or disk full, checksum mismatches, and filename traversal.

When testing cancellation, verify temporary files or partial destination files are marked/deleted according to policy. Do not write a test that only asserts status while ignoring leftover resources.

## 12. Measuring and Observing Memory Under Heavy Load

A single functional test is not enough to conclude an application uses little RAM under load. To verify the memory envelope:

1. Create files at multiple sizes, such as 100 MiB, 1 GiB, and near the business limit.
2. Run multiple concurrent uploads/downloads, not just a single request.
3. Measure heap usage and GC with JFR or Java Flight Recorder.
4. Monitor direct memory when using Reactor Netty pooled buffers.
5. Track disk usage, file descriptors, write throughput, and request durations.
6. Check memory after clients cancel requests and after all requests finish.
7. Compare memory growth with concurrent request count, not solely with file size.
8. Enable Netty leak detection in test environments when hunting DataBuffer leaks; detailed modes carry performance overhead.

If memory grows nearly proportionally to file size, look for aggregation points like byte[], collectList, join, cache, or bodyToMono. If memory grows with concurrency, inspect prefetch, queues, buffer sizes, concurrent transfer counts, and retained publishers.

## 13. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `Files.readAllBytes` for upload/download | The entire file is loaded into the heap | Use FilePart, Resource, or a DataBuffer stream |
| Using `@RequestBody byte[]` for large files | The request body is aggregated into a single array | Use `FilePart` or `Flux<DataBuffer>` |
| Using `expectBody(byte[].class)` in large download tests | The test itself buffers the whole response in RAM | Use `returnResult(DataBuffer.class)` and consume buffer by buffer |
| Calling `collectList()` on DataBuffers | Retains many buffers until the stream ends | Process each buffer and release immediately |
| Calling `DataBufferUtils.join` for unbounded files | Aggregates the body into one large buffer | Use `DataBufferUtils.write` or Resource |
| Using client filenames as paths | Path traversal or file overwrites | Generate IDs/paths on the server |
| Not limiting disk usage | Concurrent uploads can fill the disk | Configure maxDiskUsagePerPart, quotas, and cleanup |
| Configuring only maxInMemorySize and thinking total file size is capped | Large file parts can still spool to disk | Configure disk, request, and business limits separately |
| Returning byte[] instead of Resource | Server must hold the entire file on the heap | Return FileSystemResource or Flux<DataBuffer> |
| Calling block/subscribe in controllers | Blocks the event loop or detaches request lifecycle | Compose publishers and return them |
| Releasing DataBuffer twice | IllegalReferenceCountException or freed-buffer access | Track ownership; do not release after handoff |
| Forgetting to release buffers when handling manually | Direct memory leak | Release after reading; use doOnDiscard where appropriate |
| Not handling cancellation | Partial files or held resources remain | Clean up in lifecycle hooks and use temporary files |
| Checking only status 201/200 | Fails to catch truncated/corrupted files | Verify size and checksum |
| Testing only one request | Misses concurrency pressure | Run load tests and measure heap/direct memory |
| Using FilePart when sequential multipart processing is needed | Parser may process collections/part metadata first | Use `Flux<PartEvent>` when per-part streaming is required |
| Using WebClient bodyToMono for large files | Client aggregates the response | Use bodyToFlux(DataBuffer.class) and write to disk |

## 14. Large Upload/Download Implementation Checklist

Before deploying the endpoint to production, verify:

1. **Data path:** does data stay streaming from request to disk and from disk to response?
2. **API:** is FilePart, PartEvent, Flux<DataBuffer>, or Resource the right choice?
3. **Aggregation:** do any byte[], readAllBytes, collectList, join, or bodyToMono calls buffer the entire file?
4. **Buffers:** are chunk size and queued buffer count bounded?
5. **Ownership:** is each buffer consumed, released, or transferred to a writer exactly once?
6. **Backpressure:** does a slow downstream prevent upstream from emitting unboundedly?
7. **Disk:** are multipart temp directory, quotas, free space, and cleanup configured?
8. **Security:** are filename, content type, extension, authorization, virus scanning, and path traversal handled?
9. **Integrity:** are size and checksum verified before marking a file complete?
10. **Cancellation:** does mid-transfer client disconnect close streams and clean up partial files?
11. **Download headers:** do Content-Type, Content-Length, Content-Disposition, and Range match the contract?
12. **Tests:** does WebTestClient upload via Resource and consume responses via DataBuffer?
13. **Load:** have large files and concurrent requests been tested while monitoring heap/direct memory/disk?
14. **Operations:** are metrics, non-sensitive logs, disk alerts, and cleanup mechanisms in place?

**Remember:** a genuinely streaming transfer never holds the entire file in a single Java object. Use `FilePart.transferTo` for simple multipart uploads, `PartEvent` when sequential multipart processing is needed, `Flux<DataBuffer>` for raw byte streams, and `Resource`/`DataBufferUtils.read` for downloads. Verify transfers using chunked size and checksums; in tests, consume each DataBuffer and release immediately. Memory, disk, concurrency, and request-duration limits are separate parts of the same design.

## References

- Spring Framework — Multipart Content and PartEvent: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework — Reactive Core, Multipart Limits and DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework — DataBufferUtils API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Boot — Common Application Properties, WebFlux Multipart: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Framework — WebClient Request Body and Multipart Streaming: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html
