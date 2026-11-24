# Multipart, FilePart, PartEvent, and Streaming File Processing in Spring WebFlux

## 1. Objectives and Scope

In Spring WebFlux, HTTP file uploads commonly use `multipart/form-data`, yet receiving a single file and streaming tens of gigabytes are two different problems. **`FilePart`** is convenient for accessing a parsed part by name and saving it to a destination, whereas **`PartEvent`** lets you receive multipart data fragments sequentially as a `Flux<PartEvent>`.

By the end of this lesson, you should understand:

- HTTP multipart structure (boundary, field name, filename, media type, form fields, and files).
- How Spring WebFlux `Part`, `FilePart`, `FormFieldPart`, `PartEvent`, `FilePartEvent`, and `FormPartEvent` differ from Servlet MVC `MultipartFile`.
- How to use `@RequestPart`, `@RequestBody Mono<MultiValueMap<String, Part>>`, and `ServerWebExchange.getMultipartData()`.
- How to use `@RequestBody Flux<PartEvent>`, `windowUntil(PartEvent::isLast)`, `switchOnFirst`, `concatMap`, and `DataBufferUtils.release`.
- How to save files with `FilePart.transferTo(Path)` or `DataBufferUtils.write` while managing pooled buffer ownership.
- Limits including `maxInMemorySize`, `maxDiskUsagePerPart`, `maxParts`, total upload size, timeouts, and concurrent uploads.
- How to implement, test, and secure upload endpoints with **Java 17+, Spring Boot 3.x, Spring Framework 6.x**, including HTTP multipart tests with `WebTestClient`.
- The limits of streaming/backpressure; do not mistake non-blocking for infinite memory, disk, or network throughput.

**Scope note:** Exercises use the Spring WebFlux reactive stack (`spring-boot-starter-webflux`), not `spring-boot-starter-web`/Spring MVC. For Boot 4/Framework 7, check API versions again.

## 2. HTTP Multipart: One Body with Multiple Parts

Browser request:

~~~html
<form action="/api/uploads/file" method="post" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">Upload</button>
</form>
~~~

An equivalent MIME-style request simplified for illustration:

~~~http
POST /api/uploads/file HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary

--DemoBoundary
Content-Disposition: form-data; name="note"

report for Q4
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="report.csv"
Content-Type: text/csv

id,name
1,Spring
--DemoBoundary--
~~~

Actual boundary lines have strict CRLF rules; this snippet illustrates the format rather than an exact binary dump.

Each part has a **field name** (`name="file"`), and may carry a **filename** and its own `Content-Type`. Filename and Content-Type are **client-supplied** and must never be trusted for access control, MIME validation, or filesystem paths.

The server selects a part via `@RequestPart("file")`, not by file extension. If the client sends `name="attachment"`, `@RequestPart("file")` will not match and typically fails with 4xx.

HTTP clients should generate proper boundaries via `curl -F`, `MultipartBodyBuilder`, a browser, or WebClient's multipart writer. Never just set `Content-Type: multipart/form-data` and send raw bytes without multipart separators.

## 3. Distinguishing Abstractions and Methods

| Type | Package | Used for |
| --- | --- | --- |
| `Part` | `org.springframework.http.codec.multipart` | Multipart part: `name()`, `headers()`, `content()`, `delete()` |
| `FilePart` | same as above | Parsed file: `filename()`, `transferTo(Path)` |
| `FormFieldPart` | same as above | Text field with `value()` |
| `PartEvent` | same as above | Event carrying headers, `content()`, `isLast()` |
| `FilePartEvent` | same as above | File event; `filename()` |
| `FormPartEvent` | same as above | Form field event; `value()` |
| `DataBuffer` | `org.springframework.core.io.buffer` | A byte buffer, possibly pooled/ref-counted |
| `DataBufferUtils` | same as above | Read/write/release buffers |

In Servlet Spring MVC, `MultipartFile` provides imperative APIs `getBytes()`, `getInputStream()`, and `transferTo(File)`. In WebFlux, `FilePart.content()` returns **`Flux<DataBuffer>`** and `transferTo(Path)` returns **`Mono<Void>`**. Do not copy MVC code into WebFlux and treat the two types as identical.

### Choosing the Right API for the Task

| Need | Choice |
| --- | --- |
| One file or a few named fields | `@RequestPart FilePart` |
| File alongside a JSON metadata part | `@RequestPart FilePart` and `@RequestPart Mono<Meta>` |
| Look up all parts by name | `@RequestBody Mono<MultiValueMap<String, Part>>` or `exchange.getMultipartData()` |
| Process a file chunk-by-chunk / event-by-event | `@RequestBody Flux<PartEvent>` |
| Stream-relay multipart to another service | `PartEvent` + WebClient multipart writer, with buffer management |
| Simply store a parsed file | `FilePart.transferTo(Path)` |
| Very large uploads needing chunked resume | Dedicated resumable protocol/object storage, not just one `FilePart` |

No single option is always fastest. The streaming API reduces the need to buffer an entire file in memory, yet increases responsibility for DataBuffer and cancellation management.

## 4. `@RequestPart`: Accessing Parts by Name

Basic handler:

~~~java
@PostMapping(
        path = "/api/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Void> receive(
        @RequestPart("file") FilePart file,
        @RequestPart("metadata") Mono<DocumentMetadata> meta) {

    return meta.flatMap(m ->
            validateMetadata(m)
                    .then(file.transferTo(chooseServerPath(m))));
}
~~~

**This is an illustrative snippet, not standalone runnable** because `DocumentMetadata`, `validateMetadata`, and `chooseServerPath` are undefined. The main idea: Spring WebFlux decodes the JSON of the `metadata` part when the media type/codec matches, while the file arrives as a `FilePart`. `@Valid` can be used on the metadata DTO when a Bean Validation dependency and constraint annotations are present, with WebFlux's binding error mechanism.

When all parts are needed:

~~~java
Mono<MultiValueMap<String, Part>> parts = exchange.getMultipartData();
~~~

or in a controller:

~~~java
@PostMapping(consumes="multipart/form-data")
public Mono<Void> receiveAll(
        @RequestBody Mono<MultiValueMap<String, Part>> parts) {
    return parts.then();
}
~~~

The second example **only illustrates binding** and must not be treated as safe production file handling: it neither saves files nor performs business validation/cleanup. With `getMultipartData()` or map access, the framework **parses parts into a map** before you access them, possibly buffering small files in memory and spooling large files to temporary disk. Once the raw body is parsed/cached into a map, do not treat the body as a stream you can subscribe to multiple times.

### Why Doesn't FilePart Automatically Mean All Bytes in Heap?

`FilePart` describes a part after parsing; it does not mean Spring reads a 1 GiB file into one `byte[]`. Under Spring 6.x's default part reader, `maxInMemorySize` is the threshold at which file parts spool to disk, while non-file parts are memory-bounded. Thus you still must monitor **temporary disk**, open file descriptors, HTTP ingress limits, upload durations, and concurrent requests.

## 5. `FilePart.transferTo(Path)` and Laziness

~~~java
Mono<Void> write = filePart.transferTo(destination);
~~~

The write executes when the reactive Publisher is subscribed to; the framework subscribes when the controller returns the Mono. Therefore it is **wrong** to call `file.transferTo(dest)`, discard the Mono, and immediately return `"success"`.

Better:

~~~java
return filePart.transferTo(destination)
        .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                .body("stored"));
~~~

`thenReturn` emits the business status only after the transfer succeeds. If the transfer fails, the pipeline emits an error rather than claiming the file was saved.

**Never use the client filename directly as a path:**

~~~java
// ANTI-PATTERN: risk of path traversal and overwrite.
Path unsafe = uploadRoot.resolve(filePart.filename());
return filePart.transferTo(unsafe);
~~~

Filename could be `../secret.txt`, an absolute path, control characters, Unicode spoofing, or a colliding name. The `FilePart.filename()` Javadoc itself warns against using it blindly. Choose a server-managed storage ID:

~~~java
String storageKey = UUID.randomUUID() + ".bin";
Path safe = controlledRoot.resolve(storageKey);
return filePart.transferTo(safe);
~~~

`UUID` reduces collision probability, though it does not replace atomic `CREATE_NEW` when the threat model must prevent any overwrite. `transferTo` may truncate an existing destination file. Production requires storage isolation, OS permissions, symlink/race checks, staging/quarantine, checksums/scanning, and cleanup on failure.

### Do Not Unconditionally Consume FilePart Twice

If you have already read `filePart.content()` to process/hash it, do not assume a subsequent `transferTo()` will re-read a repeatable stream. When both hashing and writing are required, perform a single pass over source buffers or stage first and read the saved file by explicit design.

## 6. `PartEvent`: Streaming Processing Instead of Map Access

A large file upload can emit **multiple `FilePartEvent` instances**, not a single event. Each event has `content()` returning a `DataBuffer`; the final event of a part has `isLast() == true`. A form field typically has one `FormPartEvent`.

Correct pattern:

~~~java
allEvents
    .windowUntil(PartEvent::isLast)
    .concatMap(window ->
        window.switchOnFirst((signal, events) -> {
            // The first signal helps classify FormPartEvent/FilePartEvent.
            // All events in the window still must be processed.
            return events;
        }));
~~~

This snippet illustrates only the Reactor operator chain, **not a complete handler**. Explanation:

1. `windowUntil(PartEvent::isLast)` splits the stream into one window per part.
2. `switchOnFirst` inspects the first event's type without dropping that first event from the downstream sequence.
3. `concatMap` processes windows sequentially, preserving multipart part order and avoiding unnecessary concurrent file writes.
4. For `FilePartEvent`, take `events.map(PartEvent::content)` to relay/write/count in streaming fashion.
5. For `FormPartEvent`, read `value()`, yet **if you own the buffer**, you still must consume/release it properly.
6. **Every received DataBuffer must be consumed, relayed, or released.** Filtering out events without releasing their buffers can leak pooled native memory.

Anti-pattern:

~~~java
// DO NOT DO THIS: takes only the first event, dropping the rest of the file.
return events.filter(e -> e instanceof FilePartEvent).next();
~~~

If a file spans multiple chunks, `next()` reads too few bytes. Cancellation can also leave buffers undelivered to downstream that must be handled via discard/cleanup semantics.

## 7. DataBuffer Ownership, Release, and Writing

In Reactor Netty, a `DataBuffer` may be backed by pooled reference-counted buffers. When a framework decoder processes the bytes completely, it typically manages their lifecycle. However, if custom code directly accesses `PartEvent.content()`, you must manage ownership.

Example **counting bytes then releasing**:

~~~java
long length;
try {
    length = buffer.readableByteCount();
} finally {
    DataBufferUtils.release(buffer);
}
~~~

This is a snippet inside a method that already has `DataBuffer buffer`. `finally` ensures release even if code throws an exception. Never release a buffer before another writer/consumer finishes reading it, and never pass an already-released buffer downstream.

Spring provides:

~~~java
Mono<Void> write = DataBufferUtils.write(
        sourceBuffers, destination,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

This overload writes to a **`Path`**; `sourceBuffers` and `destination` must be declared. **Other overloads return `Flux<DataBuffer>` when writing to `OutputStream`/`WritableByteChannel` and do not auto-release buffers**; read the exact overload Javadoc and use `DataBufferUtils.releaseConsumer()`/doOnNext release where appropriate.

Never let two consumers hold the same `DataBuffer` and both release it without deliberate reference-count management. `doOnDiscard` helps for operators supporting discard, but does not replace releasing on the normal processing path; cancellation, timeouts, and errors all require testing.

**Avoid collecting all bytes:**

~~~java
// ANTI-PATTERN for large files
Mono<List<DataBuffer>> huge = inputBuffers.collectList();
~~~

Without a file-size cap, collecting buffer references rapidly grows memory and causes leaks on error. Streaming avoids this, provided downstream truly consumes incrementally rather than secretly re-aggregating.

## 8. Multipart Readers and Limits to Know

Per Spring Framework 6.2:

- `MultipartHttpMessageReader` provides `MultiValueMap<String, Part>` access using an underlying part reader.
- `DefaultPartHttpMessageReader` handles parsed parts and offers `setMaxInMemorySize`, `setMaxDiskUsagePerPart`, and `setMaxParts`.
- `PartEventHttpMessageReader` reads `Flux<PartEvent>` directly for the event-stream path.

### Limits Table

| Limit | Meaning | What not to assume |
| --- | --- | --- |
| `maxInMemorySize` | In-memory cap for non-file fields; disk-spool threshold for file parts | Does not cap total file size at that threshold |
| `maxDiskUsagePerPart` | Per-file-part disk cap on the corresponding parsed reader | Does not automatically cap files on the PartEvent path |
| `maxParts` | Part count cap on the parsed reader | Does not replace per-user request quotas |
| Max HTTP body | Total bytes at server/gateway | Not synonymous with `maxInMemorySize` |
| Idle/body timeout | Very slow client transfers | Does not replace size quotas |
| Temp disk quota | Prevents staging disk exhaustion | Not achieved by heap limits alone |
| Concurrent upload limit | Simultaneous uploading clients | Non-blocking does not mean infinite |

Setting `maxInMemorySize=-1` disables the limit and can keep data entirely in memory in that reader. Do not "fix" `DataBufferLimitException` with `-1` without enforcing other hard limits.

### Configuration for the `FilePart` Path

~~~java
@Configuration
public class UploadCodecConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        DefaultPartHttpMessageReader partReader =
                new DefaultPartHttpMessageReader();

        partReader.setMaxInMemorySize(64 * 1024);
        partReader.setMaxDiskUsagePerPart(10L * 1024 * 1024);
        partReader.setMaxParts(5);

        configurer.defaultCodecs().multipartReader(
                new MultipartHttpMessageReader(partReader));
    }
}
~~~

This is an illustrative class; the full file with imports is in the next example. **The per-file disk and maxParts limits in this configuration belong to the `@RequestPart` parsed reader**, and do not automatically apply at the same level to `@RequestBody Flux<PartEvent>`. On event-based routes, count bytes yourself and enforce ingress limits, timeouts, and part caps outside the application where needed.

When a parser rejects a request, the status may be 400 or 413 depending on the exception, version, and middleware. If an API requires 413 on every size overflow, add end-to-end tested exception mapping rather than assuming a status without testing.

## 9. Security: Uploads Are Untrusted Input

Even authenticated users can upload dangerous or malformed files. Independent layers are needed:

- **Authentication/authorization** per user/tenant, upload policies, format allowlists, and quotas/retention.
- **Server-generated storage keys**; never use `filename()`, raw path params, or `getOriginalFilename` as a Path.
- **Content-based MIME sniffing/validation** with an allowlist; file extensions and part `Content-Type` headers are client hints.
- **Count actual bytes**; never trust `Content-Length` when requests use streaming/chunking, proxy rewriting, or lying clients.
- **File/virus scanning**, plus archive/zip-bomb checks if the business processes compressed contents.
- **Staging/quarantine** before publishing; publish only after scanning, DB metadata, and owner ACLs all succeed.
- **Limits on parts/file/disk/HTTP timeouts/concurrency**, per-user quotas, rate limiting, and slow-upload protection.
- **Filesystem isolation**; never store in the web root or code directory, keep roots non-writable by clients, and prevent symlinks/TOCTOU.
- **Cookies/CORS/CSRF**: CORS does not replace CSRF if cookie sessions are used; the WebFlux Spring Security chain must protect upload POSTs.
- **Independent download ACLs**; an uploaded file must not become public or inline-renderable by default.
- **Audit** using opaque IDs; never log session cookies, bearer tokens, raw filenames, or sensitive file contents.
- **Cleanup** when writes abort midway, uploads cancel, scans fail, DB metadata errors, or sessions/retries duplicate.

If multi-GiB files or resumable uploads are required, consider presigned object-storage uploads or tus/chunked protocols instead of holding a single HTTP multipart request open indefinitely. `FilePart` does not handle resume itself.

## 10. Complete Example: Java 17+ and Spring Boot 3.x

The demo has **two endpoints**:

- `POST /api/uploads/file` receives a `FilePart`, uses an opaque UUID filename, and writes locally via `transferTo`. Returns **201 Created** once the transfer completes.
- `POST /api/uploads/events/inspect` receives `Flux<PartEvent>`, iterates parts sequentially, counts only file bytes while releasing every buffer; neither saves files nor allocates large byte arrays.
- Configures the parsed multipart reader with a 64 KiB memory threshold, 10 MiB max disk/file, and max 5 parts; the event route enforces 10 MiB bytes/file in the pipeline.
- HTTP tests via `WebTestClient` with multipart builder, verifying stored bytes and receipts.

**Demo limitations:** no virus scanning, authentication/authorization, atomic publish, total-request quota, abandoned-file cleanup, or hard proxy limits. Do not deploy the demo code verbatim to the public internet.

### 10.1. Project and Dependencies

Create a Spring Initializr project (Maven, Java 17+, Spring Boot 3.x) with:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is a **snippet inside `pom.xml`** generated by Spring Initializr, not a standalone Maven file. Avoid adding `spring-boot-starter-web`, since having both MVC and WebFlux starters makes Boot prefer MVC by default.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/UploadCodecConfig.java
src/main/java/com/example/demo/UploadController.java
src/test/java/com/example/demo/UploadControllerTest.java
~~~

### 10.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. UploadCodecConfig.java

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.multipart.DefaultPartHttpMessageReader;
import org.springframework.http.codec.multipart.MultipartHttpMessageReader;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class UploadCodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        DefaultPartHttpMessageReader parsed =
                new DefaultPartHttpMessageReader();
        parsed.setMaxInMemorySize(64 * 1024);
        parsed.setMaxDiskUsagePerPart(10L * 1024 * 1024);
        parsed.setMaxParts(5);
        configurer.defaultCodecs()
                .multipartReader(new MultipartHttpMessageReader(parsed));
    }
}
~~~

### 10.4. UploadController.java

~~~java
package com.example.demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.FilePartEvent;
import org.springframework.http.codec.multipart.PartEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private static final long MAX_FILE_BYTES = 10L * 1024 * 1024;
    private final Path root;

    public UploadController() throws IOException {
        // Runs only once when initializing the application bean.
        root = Path.of("target", "demo-uploads")
                .toAbsolutePath().normalize();
        Files.createDirectories(root);
    }

    @PostMapping(
            path = "/file",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<StoredFile>> upload(
            @RequestPart("file") FilePart part) {

        // Do not use part.filename() to choose the path.
        String key = UUID.randomUUID() + ".bin";
        Path destination = root.resolve(key);

        return part.transferTo(destination)
                .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                        .body(new StoredFile(key, "stored")));
    }

    @PostMapping(
            path = "/events/inspect",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<List<StreamReceipt>> inspect(
            @RequestBody Flux<PartEvent> all) {

        return all.windowUntil(PartEvent::isLast)
                .concatMap(window ->
                        window.switchOnFirst((signal, events) -> {
                            if (!signal.hasValue()) {
                                return events.then(
                                        Mono.<StreamReceipt>empty());
                            }

                            PartEvent first = signal.get();

                            if (first instanceof FilePartEvent) {
                                AtomicLong bytes = new AtomicLong();

                                return events
                                        .map(PartEvent::content)
                                        .map(buffer -> {
                                            try {
                                                long total = bytes.addAndGet(
                                                        buffer.readableByteCount());
                                                if (total > MAX_FILE_BYTES) {
                                                    throw new ResponseStatusException(
                                                        HttpStatus.PAYLOAD_TOO_LARGE,
                                                        "file too large");
                                                }
                                                return total;
                                            } finally {
                                                DataBufferUtils.release(buffer);
                                            }
                                        })
                                        .then(Mono.fromSupplier(() ->
                                                new StreamReceipt(
                                                        "file", bytes.get())));
                            }

                            // Unused field metadata: must still be released.
                            return events.doOnNext(event ->
                                    DataBufferUtils.release(event.content()))
                                    .then(Mono.<StreamReceipt>empty());
                        }))
                .collectList();
    }

    public record StoredFile(String key, String status) {}

    public record StreamReceipt(String type, long bytes) {}
}
~~~

Detailed rationale for these decisions:

1. The constructor creates the directory at startup rather than running blocking filesystem setup on every HTTP request. The directory is for demo only: a production root must be configured/locked down and **must not** allow arbitrary user symlinks.
2. `upload` creates a UUID key without using `FilePart.filename()`. `transferTo` is **returned/composed**; Spring subscribes and returns 201 upon completion.
3. `inspect` reads `Flux<PartEvent>` directly without requiring a multipart map or saving files.
4. `windowUntil(PartEvent::isLast)` guarantees a multi-chunk file is grouped into one window; `switchOnFirst` classifies it, and `concatMap` processes sequentially.
5. `AtomicLong` is **per-part**, not shared across requests. Values accumulate from `readableByteCount()`; if exceeding 10 MiB, it throws `ResponseStatusException(PAYLOAD_TOO_LARGE)`.
6. `finally` releases the received DataBuffer even when throwing the limit error. Form-field buffers are consumed/released rather than filtered away.
7. `collectList()` collects only small `StreamReceipt` objects, never uploaded bytes. For requests with many parts, external ingress/reader limits and quotas must be added; this is not a defense against all unbounded inputs.
8. For upstream or mid-pipeline cancellations/errors, guaranteeing every pooled buffer is released and partial files are deleted requires additional discard handling, integration tests, and staging cleanup design. Do not treat the demo as production-complete.
9. The `upload` path on the parsed reader has a 10 MiB/part disk cap; the `events/inspect` path is not automatically protected by that same config, so it caps bytes itself and still needs an external hard request cap.
10. `ResponseEntity` returns an opaque key rather than exposing a filesystem path. A separate download endpoint must still enforce ACLs if added.

### 10.5. UploadControllerTest.java

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UploadControllerTest {

    @Autowired
    WebTestClient client;

    private static ByteArrayResource testFile(byte[] body) {
        return new ByteArrayResource(body) {
            @Override
            public String getFilename() {
                return "client-name.txt";
            }
        };
    }

    @Test
    void filePartTransferStoresExactBytes() throws Exception {
        byte[] data = "spring reactive\n"
                .getBytes(StandardCharsets.UTF_8);

        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("file", testFile(data))
                .contentType(MediaType.TEXT_PLAIN);

        UploadController.StoredFile receipt = client.post()
                .uri("/api/uploads/file")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(UploadController.StoredFile.class)
                .returnResult().getResponseBody();

        assertNotNull(receipt);
        assertTrue(receipt.key().endsWith(".bin"));
        assertTrue(!receipt.key().contains("client-name.txt"));

        Path stored = Path.of("target", "demo-uploads")
                .toAbsolutePath().normalize().resolve(receipt.key());

        try {
            assertTrue(Files.isRegularFile(stored));
            assertArrayEquals(data, Files.readAllBytes(stored));
        } finally {
            Files.deleteIfExists(stored);
        }
    }

    @Test
    void streamedPartEventsCountActualBytes() {
        byte[] data = "abcd".getBytes(StandardCharsets.UTF_8);
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("note", "demo");
        builder.part("file", testFile(data))
                .contentType(MediaType.TEXT_PLAIN);

        client.post()
                .uri("/api/uploads/events/inspect")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].type").isEqualTo("file")
                .jsonPath("$[0].bytes").isEqualTo(4);
    }

    @Test
    void missingRequiredNamedPartProducesClientError() {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("note", "without file");

        client.post()
                .uri("/api/uploads/file")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
~~~

**Testing highlights:**
- `WebTestClient` uses an embedded server on a random port, building real multipart form requests.
- `ByteArrayResource` is used only in the **client test** for consistent bytes/filename; it does not imply the backend reads whole files into memory.
- Verifies the file is saved under a server opaque key and **exact bytes match**.
- The events route skips the form field and releases its buffer, returning receipt `bytes=4` for file `abcd`.
- Missing `@RequestPart("file")` returns 4xx. The exact error schema/status may depend on Boot/Framework auto-configuration.
- Tests do not measure performance, virus scanning, or concurrency/slow clients; add integration/load/security tests before production.

Run Maven:

~~~bash
./mvnw test
~~~

On Windows use `mvnw.cmd test`; without the wrapper, use `mvn test` if Maven is installed.

## 11. Trying with curl

Start the application:

~~~bash
./mvnw spring-boot:run
~~~

### Save a File

~~~bash
curl -i -F "file=@sample.txt;type=text/plain"   http://localhost:8080/api/uploads/file
~~~

Returns **201 Created** with a body like:

~~~json
{"key":"00000000-0000-0000-0000-000000000000.bin","status":"stored"}
~~~

The UUID in the example is a **format placeholder**; real output is randomized rather than fixed. The file is created under `target/demo-uploads`.

### Read Multipart as a PartEvent Stream

~~~bash
curl -i   -F "note=demo"   -F "file=@sample.txt;type=text/plain"   http://localhost:8080/api/uploads/events/inspect
~~~

Response looks like:

~~~json
[{"type":"file","bytes":4}]
~~~

`4` is an example when `sample.txt` contains 4 bytes, such as `abcd`. For real files, the resulting size equals the number of content bytes read, **not** necessarily the number of visible Unicode characters. Check with `wc -c sample.txt`.

### Wrong Field Name

~~~bash
curl -i -F "attachment=@sample.txt"   http://localhost:8080/api/uploads/file
~~~

The handler requires a named part `file`, so a request with only `attachment` fails to match and usually returns 4xx.

**Shell note:** line-continuation backslashes `\` above are for Linux/macOS/Git Bash. On Windows PowerShell, run `curl.exe` on one line or use PowerShell line continuation syntax. Never place passwords/API tokens in commands or public logs.

## 12. Supplement: WebClient Multipart and Outbound PartEvent

When an application needs to send files upstream, Spring WebFlux WebClient supports `MultipartBodyBuilder`:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("description", "demo");
builder.part("file", new FileSystemResource("/safe/path/data.bin"));

Mono<String> result = webClient.post()
        .uri("/ingest")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .bodyToMono(String.class);
~~~

This is a snippet inside a service with a configured `webClient` and a server-authorized storage file. For remote domains, verify host allowlists, HTTPS, authentication, timeouts, retries, outbound quotas, and whether untrusted headers/filenames are inadvertently forwarded.

Multipart can also be sent via **PartEvent**:

~~~java
Flux<PartEvent> outgoing = Flux.concat(
        FormPartEvent.create("description", "demo"),
        FilePartEvent.create("file", resource));

return webClient.post()
        .uri("/ingest")
        .body(outgoing, PartEvent.class)
        .retrieve()
        .bodyToMono(Void.class);
~~~

This is an illustrative snippet requiring `resource` and `webClient` to be declared. `FilePartEvent.create` can emit multiple events for large files. Never `collectList()` all events to build another multipart request if streaming is the goal.

### Relaying Inbound to Outbound Without Buffering the Entire File

An endpoint receiving `Flux<PartEvent>` can relay it to an outbound WebClient, provided you control:
1. Headers and filenames may contain untrusted input.
2. Pooled buffers: clarify who the final consumer is and ownership/release rules.
3. If upstream fails or the client disconnects, cancel inbound properly.
4. Cap bytes, parts, rates, connections, and timeouts on both ends.
5. Never call `.subscribe()` in the controller and return 200 before upstream upload completes.
6. Never call `.block()` on the Reactor Netty event loop.
7. If upstream returns an error, translate the status and clean up staging/metadata per contract.

## 13. Production Upload Lifecycle: Staging → Scan → Publish

A system may need a workflow:

~~~text
Client
  |
  v
Ingress/WAF: authentication, maximum body size, timeout, rate limit
  |
  v
Spring WebFlux: validate named parts + metadata, quota
  |
  v
Staging file/object (opaque key, isolated storage)
  |
  +-- stream bytes, count, compute hash, enforce hard limit
  |
  +-- file format and malware scanning
  |
  v
Atomic publish / object-store versioning
  |
  v
Database metadata: owner, tenant, ID, size, hash, MIME, state
  |
  v
201 Created / async job status
~~~

**Cleanup on failure is a mandatory responsibility:** a file may be written while the DB metadata insert fails, or the DB commits first and object publishing fails. Build transaction/compensation/garbage-collection workflows such as states `PENDING`, `SCANNING`, `READY`, and `FAILED`. Atomic filesystem renames work only under filesystem conditions; object-storage copy/move is not a POSIX transaction.

With concurrent uploads, guard against collisions, symlinks, path traversal, races, and per-tenant partitions/quotas. For large data and resume requirements, consider tus or presigned chunked uploads with checksum/version/idempotency keys. Never assume an HTTP multipart POST is resumable.

### Timeouts and Status Codes

- `400`: malformed multipart, invalid part name, invalid metadata per contract.
- `401/403`: missing authentication/authorization.
- `413`: request or file exceeds application-defined quota.
- `415`: unsupported content type.
- `422`: HTTP-valid file format failing business validation (API-dependent).
- `429`: exceeded rate limit/concurrency.
- `503`: backend/storage overloaded.

Exact status codes for parser overflow depend on framework/container; **test in reality** rather than claiming every multipart reader exception maps to 413 automatically. Once the response has committed, the server may be unable to switch to an error JSON body; clients must detect incomplete responses/connection failures.

## 14. Common Mistakes and How to Handle Them

| Issue | What went wrong | Right approach |
| --- | --- | --- |
| Using `MultipartFile` in WebFlux | Different Servlet/MVC API | `FilePart` or `PartEvent` |
| Ignoring the Mono from `transferTo` | Pipeline never executes | Return/compose the Mono |
| Using `filename()` as path | Path traversal/overwrite | Server-generated opaque key |
| Trusting client `Content-Type` | Spoofed MIME/extension | Magic-byte/decoder scan |
| Reading only the first event | Multi-chunk file gets truncated | `windowUntil(isLast)`, consume entire window |
| `filter` drops buffers without releasing | Netty pooled memory leak | Consume/release/relay |
| Releasing buffer before write finishes | Use-after-release | Clear ownership and right overload |
| `collectList()` on file buffers | Memory scales with file size | Stream/write buffer by buffer |
| Setting `maxInMemorySize=-1` | Unbounded heap usage | Thresholds and disk quotas |
| Setting only memory threshold | Temp disk can still fill up | maxDiskUsagePerPart, quotas |
| Assuming parsed reader maxParts applies to PartEvent | Event route uses a different reader | Enforce event/byte limits + ingress caps yourself |
| Calling `Files.readAllBytes` on event loop | Blocking + memory | Async APIs/dedicated scheduler or streaming |
| Client fails sending cookies/auth with CORS | Preflight/SameSite/CSRF mismatch | Proper Security/CORS config |
| Testing with raw bytes instead of multipart | Missing boundary/part | `curl -F`/MultipartBodyBuilder |
| Not cleaning up partial files | Orphaned disk files | Staging + doFinally/error cleanup |
| Returning 201 before storage finishes | Publisher not composed | `transferTo(...).thenReturn(...)` |
| Thinking "non-blocking" means unlimited uploads | Pools/IO/disk remain finite | Concurrency budgets, timeouts |
| Making uploaded files public immediately | Missing scanning/download ACL | Publish based on state and owner |

## 15. Review Questions

**1. How does `FilePart` differ from `MultipartFile`?**  
`FilePart` is WebFlux's reactive API; `transferTo` returns `Mono<Void>`. `MultipartFile` is the API typically used in Servlet MVC.

**2. What happens if you call `file.transferTo(path)` without returning or subscribing to the Mono?**  
The file transfer is not guaranteed to run; you must include the Mono in the pipeline that WebFlux subscribes to.

**3. Why is `PartEvent::isLast` important?**  
A single file may span multiple FilePartEvents; `isLast` marks the final event of each part.

**4. What does `switchOnFirst` help with?**  
Inspecting the first event to choose form vs file handling while preserving all events for the consumer.

**5. Why must DataBuffers be released?**  
Pooled buffers are reference-counted; failing to release them can leak off-heap memory.

**6. Does setting `maxInMemorySize=64KiB` mean a 65KiB file is rejected?**  
No: for the default parsed file reader this is normally the disk-spooling threshold; separate maxDiskUsagePerPart and request-size limits are required.

**7. Should you use the original filename to resolve a filesystem path?**  
No. It is client-controlled; use a server-generated storage key.

**8. Is event streaming automatically capped by `DefaultPartHttpMessageReader`'s `maxParts`?**  
Do not assume so. The PartEvent reader and parsed multipart reader are distinct; apply corresponding limits.

**9. Why must receipt byte tests compare byte counts rather than character counts?**  
Because UTF-8/binary data has byte lengths that differ from visible Unicode character counts.

**10. Is `PartEvent` always faster than `FilePart`?**  
No. It changes access semantics and adds buffer management; benchmark latency, memory, disk I/O, and concurrency thoroughly.

## 16. Pre-Production Checklist

1. Pick the right API: named parts → `@RequestPart FilePart`; sequential streaming → `Flux<PartEvent>`.
2. Keep publishers in the return chain; never manually subscribe or block on the event loop.
3. Generate storage IDs on the server, avoid raw filenames, enforce filesystem permissions, and prevent symlinks/races.
4. Read/write DataBuffers with clear ownership, releasing on success, error, cancel, and discard.
5. Enforce limits on bytes/file, parts/request, memory/disk, temp storage, request duration, and max concurrency.
6. Never let spoofed `Content-Type`/filenames bypass MIME/scan rules.
7. Stage/quarantine before scanning/publishing, clean up partial/orphan files, and manage idempotency.
8. For outbound WebClient relays, configure timeouts, connection pool limits, trusted targets, and authentication/headers.
9. For downloads, enforce ACLs and separate Content-Disposition/Range/cache policies.
10. Measure p95/p99 upload latency, HTTP status/error rates, disk usage, memory/Netty buffers, cleanup failures, and proxy size rejections.
11. Test HTTP multipart with WebTestClient/curl, multi-chunk files, empty files, malformed multipart, JSON metadata, missing parts, oversized uploads, and disconnects.
12. Never treat the two-endpoint demo as a complete upload security suite.

## Official Documentation

- [Spring Framework 6.2 — Multipart Content / annotated controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — WebFlux Reactive Core and Multipart Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — FilePart API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/FilePart.html)
- [Spring Framework 6.2 — PartEvent API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html)
- [Spring Framework 6.2 — DefaultPartHttpMessageReader](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html)
- [Spring Framework 6.2 — DataBufferUtils](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.2 — WebClient Multipart request](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-body.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
