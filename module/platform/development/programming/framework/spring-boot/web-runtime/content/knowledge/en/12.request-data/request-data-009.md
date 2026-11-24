# Streaming Large Payloads Instead of Buffering Them in Memory

## 1. Problem and Goals

In Spring Boot, an HTTP request body might be a few kilobytes of JSON, or it might be a multi-hundred-megabyte CSV file, multi-gigabyte video, backup archive, telemetry feed, or stream of records. If an API reads **the entire body into a `byte[]`, `String`, or `List`** before processing, memory usage scales with payload size and concurrent requests. Many simultaneous large uploads quickly trigger heavy garbage collection, heap exhaustion, or degraded server throughput.

**Streaming** means reading a chunk of data, processing or writing that chunk to its destination, and repeating with the next chunk. The goal is to keep per-request memory bounded rather than holding the entire payload on the JVM heap.

```text
Full buffering:
Client -> Web server -> huge byte[] -> processing -> storage
                         ^ large body sits in heap

Streaming:
Client -> Web server -> small buffer -> storage
                            |
                      loop read/write
```

Streaming does not mean *zero buffering*. TCP/TLS, proxies, containers, codecs, multipart parsers, filesystems, or downstream SDKs may still buffer at some level. Distinguish **avoiding full heap buffering** from **avoiding temporary disk usage**.

## 2. Why Stream Large Data?

| Aspect | Full buffering | Streaming |
|---|---|---|
| Object size | Can equal full request size | Usually holds only the current buffer/record |
| When processing starts | After receiving/deserializing everything | While the request is still arriving |
| Memory cost | Scales with payload × concurrency | Depends on buffer, prefetch, concurrency, and sink |
| I/O | Simpler to code, may require large copies | Can pipe network directly to file/storage |
| Size checks | Often checked after reading everything | Can count bytes and abort mid-stream |
| Record handling | Can hold one large list | Can process record by record if format allows |
| Complexity | Low | Must handle cancellation, timeouts, backpressure, partial files |

If 20 concurrent requests each allocate a 200 MiB array, raw byte arrays alone take roughly 4 GiB before object headers, GC overhead, and runtime buffers. A loop using a 64 KiB buffer per request holds only about 1.25 MiB **managed directly by the loop** across 20 requests; that does not mean total process RAM equals that number alone.

Streaming is especially effective when writing files, computing incremental checksums, relaying to object storage, or processing record streams. For small JSON objects, `@RequestBody Dto` remains simpler and appropriate.

## 3. Operations That Accidentally Buffer the Whole Body

In Spring MVC:

```java
@PostMapping("/raw")
public void upload(@RequestBody byte[] body) {
    // body has already been buffered into a byte array
}
```

```java
byte[] allBytes = multipartFile.getBytes();
```

`MultipartFile.getBytes()` allocates a byte array for the entire file, even if the multipart resolver previously wrote the file part to a temporary disk file.

In WebFlux:

```java
Mono<byte[]> all = request.bodyToMono(byte[].class);
Mono<String> text = request.bodyToMono(String.class);
Mono<List<Item>> items = itemFlux.collectList();
```

Even though it starts from a `Flux`, `collectList()` still collects every element into memory. `DataBufferUtils.join(...)` is likewise an aggregation operation, unsuitable when forwarding a large file within bounded memory.

Do not assume the word `reactive` solves memory pressure by itself if an aggregation step sits at the end of the pipeline.

## 4. HTTP-Layer Streaming and Application Streaming Are Different Things

HTTP/1.1 can use `Content-Length` or `Transfer-Encoding: chunked`. HTTP/2 uses DATA frames with its own flow control. However:

- A client sending chunked encoding does not guarantee the controller receives every chunk immediately; proxies, containers, or decoders may buffer.
- Network chunk size does not necessarily match the bytes returned by one `InputStream.read()` or one `DataBuffer`.
- `Content-Length` may be missing or may not reflect what the server reads before validation fails.
- Never rely on `Content-Length` as the sole size limit; count **actual bytes received**.
- Proxies or API gateways may reject oversized requests before they ever reach Spring Boot.

Solving this requires designing the entire **pipeline from HTTP parser to sink**, not merely tweaking a single header.

## 5. Choosing the Right API by Request Type

| Data type / web stack | Typically suitable approach |
|---|---|
| Small JSON on MVC | `@RequestBody Dto` |
| Raw binary on MVC | `HttpServletRequest.getInputStream()` with a read/write loop |
| Multipart file on MVC | `MultipartFile.getInputStream()` or `transferTo(...)` |
| Raw binary on WebFlux | `@RequestBody Flux<DataBuffer>` into a streaming sink |
| Multipart on WebFlux | `@RequestPart FilePart`, `FilePart.transferTo(Path)` |
| Multipart needing immediate per-part/buffer handling | `@RequestBody Flux<PartEvent>` |
| Multiple JSON records | NDJSON/JSON Lines, `Flux<Record>` if codec supports it |
| Relaying data to object storage | Streaming/async multipart SDK with bounded in-flight parts |
| Data requiring complex whole-file validation | May require staging to a temp file before commit |

**Raw body** (`application/octet-stream`) and **multipart** (`multipart/form-data`) are different request formats. A controller expecting `MultipartFile` cannot handle a raw body; likewise `@RequestBody Flux<DataBuffer>` for raw uploads does not parse form fields or filenames.

## 6. Spring MVC/Servlet: Copying the Request Body with a Buffer

Example Spring Boot 3.5, Java 17 project with `spring-boot-starter-web`. File `src/main/java/com/example/streaming/RawUploadController.java`:

```java
package com.example.streaming;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class RawUploadController {

    private static final long LIMIT = 50L * 1024 * 1024;

    @PostMapping(
        path = "/api/upload/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Map<String, Object>> upload(
            HttpServletRequest request) throws IOException {

        Path directory = Path.of("uploads")
                .toAbsolutePath().normalize();
        Files.createDirectories(directory);
        Path destination = Files.createTempFile(
                directory, "raw-", ".bin");

        byte[] buffer = new byte[64 * 1024];
        long total = 0;

        try (InputStream in = request.getInputStream();
             OutputStream out = Files.newOutputStream(destination)) {

            int count;
            while ((count = in.read(buffer)) != -1) {
                if (total > LIMIT - count) {
                    throw new ResponseStatusException(
                            HttpStatus.PAYLOAD_TOO_LARGE,
                            "Request body exceeds 50 MiB");
                }
                out.write(buffer, 0, count);
                total += count;
            }
        } catch (IOException | RuntimeException failure) {
            try {
                Files.deleteIfExists(destination);
            } catch (IOException cleanupError) {
                failure.addSuppressed(cleanupError);
            }
            throw failure;
        }

        return ResponseEntity.ok(Map.of(
            "storedAs", destination.getFileName().toString(),
            "bytes", total));
    }
}
```

Analysis:

1. The request is read via the Servlet `InputStream`; no `byte[]` holds the whole file.
2. `byte[64 * 1024]` is reused, keeping memory held by the controller nearly constant.
3. A single `read()` may return fewer bytes than the buffer size; write only `count` bytes.
4. Checking `total > LIMIT - count` enforces **actual bytes received** and avoids integer overflow.
5. The file path is chosen server-side via `Files.createTempFile`, never trusting a client-supplied filename.
6. Success is returned only after reading completes and the output stream closes.
7. On I/O failure or limit breach, the partial file is deleted on a best-effort basis.

This is still **blocking I/O**. A Servlet request normally occupies a worker thread while `read` or `write` blocks. Buffered streaming avoids heap exhaustion, **not** meaning Spring MVC turns into a non-blocking event loop.

This educational example omits authentication, per-user quotas, antivirus checks, checksums, staging/publish workflows, and orphaned temp-file cleanup if the process is killed. Add those in production.

## 7. Main Class, Running, and Testing MVC

File `src/main/java/com/example/streaming/StreamingApplication.java`:

```java
package com.example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
```

In `pom.xml` with Spring Boot parent/dependency management, include:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Create a test file on Linux/macOS:

```bash
printf 'Hello streaming\n' > sample.bin
./mvnw spring-boot:run
```

In another terminal:

```bash
curl -i -H 'Content-Type: application/octet-stream' \
  --data-binary @sample.bin \
  http://localhost:8080/api/upload/raw
```

When running on port 8080, the response has status 200 and a JSON body **shaped like**:

```json
{"storedAs":"raw-<random-name>.bin","bytes":16}
```

The actual filename changes per request. `Hello streaming` is 15 ASCII bytes plus one newline, totaling 16 bytes. `curl -i` also prints response headers; JSON key order may vary.

To test the byte limit, create a file larger than 50 MiB and send it with `--data-binary`. The example returns **413 Payload Too Large**, though how proxies or connectors handle remaining body bytes or connection resets can affect what the client observes on the wire.

## 8. Spring MVC Multipart: MultipartFile Does Not Force Full Heap Retention

A form upload approach:

```java
@PostMapping(
    path = "/api/upload/form",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Map<String, String>> form(
        @RequestParam("file") MultipartFile file)
        throws IOException {

    Path dir = Path.of("uploads").toAbsolutePath();
    Files.createDirectories(dir);
    Path target = Files.createTempFile(dir, "form-", ".bin");

    try (InputStream in = file.getInputStream();
         OutputStream out = Files.newOutputStream(target)) {
        in.transferTo(out);
    }
    return ResponseEntity.ok(Map.of(
        "storedAs", target.getFileName().toString()));
}
```

This is an **illustrative controller method** requiring imports for `MultipartFile`, `@RequestParam`, `PostMapping`, `MediaType`, `ResponseEntity`, `Map`, `Path`, `Files`, `InputStream`, `OutputStream`, and `IOException`. Add cleanup, error handling, and size validation for production.

`InputStream.transferTo(OutputStream)` uses a buffer while copying, avoiding loading the whole file into a `byte[]`. `MultipartFile.transferTo(Path/File)` can also work; implementations may copy or move from a temp file.

With Spring Boot 3.5 Servlet multipart, example properties:

```properties
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=55MB
spring.servlet.multipart.file-size-threshold=0B
```

Boot 3.5 defaults: `max-file-size` is **1MB**, `max-request-size` is **10MB**, and threshold is **0**. A low threshold writes file parts to temporary disk via the servlet multipart mechanism instead of keeping them in heap. **However**, the multipart resolver may process and write temp files before the method receives `MultipartFile`. Thus `getInputStream()` avoids a huge `byte[]` in your code, yet does not prove socket bytes stream straight to the final destination without temp files.

Multipart client request:

```bash
curl -i -F "file=@sample.bin" \
  http://localhost:8080/api/upload/form
```

## 9. WebFlux: Flux<DataBuffer> for Raw Request Bodies

Spring WebFlux supports `@RequestBody` with reactive types to stream and process bodies. With Spring Boot 3.5 + Java 17, the project uses `spring-boot-starter-webflux` instead of the Servlet starter.

Dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

File `src/main/java/com/example/reactive/RawReactiveUploadController.java`:

```java
package com.example.reactive;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.UUID;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class RawReactiveUploadController {

    private static final Path DIR = Path.of("uploads")
            .toAbsolutePath().normalize();

    @PostMapping(
        path = "/api/upload/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<Map<String, String>> upload(
            @RequestBody Flux<DataBuffer> body) {

        Path target = DIR.resolve(
                "reactive-" + UUID.randomUUID() + ".bin");

        return Mono.fromCallable(() -> {
                Files.createDirectories(DIR);
                return target;
            })
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(path ->
                DataBufferUtils.write(
                    body, path, StandardOpenOption.CREATE_NEW)
                .thenReturn(Map.of(
                    "storedAs",
                    path.getFileName().toString())));
    }
}
```

This is a complete Java class, but must run **inside a Spring Boot WebFlux project** with a main class. Place a `@SpringBootApplication` main class under root package `com.example.reactive`, structured like the MVC example.

- `Flux<DataBuffer>` delivers sequential buffers; nothing aggregates the body into a `byte[]`.
- `Files.createDirectories` can block, so it runs on `boundedElastic` instead of the event loop.
- `DataBufferUtils.write(Publisher<DataBuffer>, Path, OpenOption...)` writes the stream to a file via an async channel and returns `Mono<Void>` signaling completion.
- In Spring Framework 6.2, the `write` overload accepting **Path** uses a releasing consumer for DataBuffers it writes successfully. **Do not confuse** this with overloads returning `Flux<DataBuffer>` for writing to channels/output streams: those overloads do not release buffers automatically.
- `CREATE_NEW` prevents overwriting existing files; the UUID filename is server-generated.
- `.thenReturn(...)` builds the response only after the file writer finishes successfully.

**Important:** this code illustrates streaming raw bodies, yet **lacks byte-count limits, partial-file cleanup on error/cancellation, auth, and quotas**. Never deploy it as a production upload API without adding those safeguards.

Do not place both the MVC and WebFlux controllers at the same URL in one project to test both: use two independent projects or explicit web application types for clean comparison.

## 10. DataBuffer Pooling and Release Responsibility

Netty can use pooled, reference-counted buffers. If a `DataBuffer` is retained too long or never released after processing, the application can leak **direct memory** even when heap metrics look normal.

Spring Framework provides utilities:

- `DataBufferUtils.release(buffer)`: releases if the buffer is pooled/reference-counted.
- `DataBufferUtils.retain(buffer)`: increments the reference count when keeping a buffer across another lifecycle.
- `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`: helps release buffers dropped by Reactor operators before consumption, depending on operators and pipeline structure.

Never double-release. When a writer takes release responsibility, do not add `doOnNext(DataBufferUtils::release)` thinking "earlier release is safer"; the buffer could be freed before the writer finishes writing it.

Operators like `filter`, `skip`, `flatMap`, `buffer`, and `window` can introduce discard paths or hold multiple elements. When manipulating raw buffers directly, consult ownership docs and test cancellation, errors, and slow subscribers.

**Safe choice:** for standard file uploads, prefer higher-level APIs like `FilePart.transferTo` rather than managing raw byte buffers manually across complex operators.

## 11. WebFlux Multipart: FilePart.transferTo

For `multipart/form-data`, Spring WebFlux provides `FilePart`:

```java
package com.example.reactive;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class ReactiveMultipartController {

    private static final Path DIR = Path.of("uploads")
            .toAbsolutePath().normalize();

    @PostMapping(
        path = "/api/upload/file",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<Map<String, String>> upload(
            @RequestPart("file") FilePart part) {

        Path target = DIR.resolve(
                "multipart-" + UUID.randomUUID() + ".bin");

        return Mono.fromCallable(() -> {
                Files.createDirectories(DIR);
                return target;
            })
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(path -> part.transferTo(path)
                .thenReturn(Map.of(
                    "storedAs",
                    path.getFileName().toString())));
    }
}
```

This class runs in a Java 17 WebFlux project with the matching starter and main class. Test client:

```bash
curl -i -F "file=@sample.bin" \
  http://localhost:8080/api/upload/file
```

`FilePart.transferTo(Path)` is a convenient API for moving/copying a file part without the controller calling `getBytes()`. However, the multipart parser may use a **memory threshold and temporary disk** before transfer. That avoids holding the entire file in heap under sensible limits, though it does not mean "zero temp disk" or "zero-copy socket-to-file".

Never append `part.filename()` directly into a filesystem path. Client-supplied filenames can contain path traversal or unsafe characters; the example uses a server-side UUID. For large production uploads, add cleanup on `transferTo` failure, quotas, file-type checks, checksums, and post-validation publishing.

## 12. True Event-Based Multipart: Flux<PartEvent>

Spring Framework supports reading multipart sequentially via `@RequestBody Flux<PartEvent>`. A `FormPartEvent` represents a form field; a large file emits multiple `FilePartEvent` items, each carrying a `DataBuffer`, with the final event of the part having `isLast() == true`.

Flow:

```text
multipart/form-data
        |
        v
Flux<PartEvent>
    |
    +--> FormPartEvent
    +--> FilePartEvent #1 (buffer)
    +--> FilePartEvent #2 (buffer)
    +--> FilePartEvent #3 (isLast = true)
        |
        v
Sequential processing / relay / write to storage
```

A snippet splitting events per part:

```java
Flux<PartEvent> events = ...;
Flux<Flux<PartEvent>> parts =
        events.windowUntil(PartEvent::isLast);
```

This is **only a mechanism snippet**: `events` comes from a WebFlux endpoint, and each part must be consumed by a real handler. When using `PartEvent`, **every body buffer must be consumed, relayed, or released**; skipping buffers can leak Netty memory.

`PartEvent` fits scenarios needing true event-stream multipart handling without materializing each part into a temp-disk `FilePart`. It is harder than `FilePart.transferTo` because you must manage cross-part state, headers, quotas, part boundaries, and buffer lifecycles.

## 13. Codec Memory Limit Is Not a Total Request Limit

In Spring Boot 3.5:

```properties
spring.http.codecs.max-in-memory-size=512KB
```

This property caps the bytes a codec may buffer when aggregation is required in WebFlux servers and Boot-configured `WebClient` instances. When unspecified, codecs use their defaults—often around **256 KiB**.

Key facts:

- With `@RequestBody Mono<MyDto>`, the decoder must aggregate the payload to build the object.
- With NDJSON `Flux<MyDto>`, the decoder may buffer **one record**, so a single huge record still hits the limit.
- With `Flux<DataBuffer>` streaming straight to a file, `max-in-memory-size=512KB` **does not mean** total raw request size is capped at 512KB.
- If `DataBufferLimitException` occurs, inspect whether code or a codec is aggregating too much; never raise the limit indefinitely to mask bad aggregation design.

In Spring MVC, `spring.http.codecs.max-in-memory-size` does not cap Servlet multipart files. Use `spring.servlet.multipart.*` or embedded server/proxy settings instead.

## 14. WebFlux Multipart: Memory and Temp Disk Limits

Spring Boot 3.5 supports:

```properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=50MB
spring.webflux.multipart.max-parts=4
spring.webflux.multipart.max-headers-size=10KB
```

Meaning:

| Property | What it controls |
|---|---|
| `max-in-memory-size` | Max memory per part; larger files spill to temp disk past this threshold |
| `max-disk-usage-per-part` | Max temp disk usage for a single buffered part |
| `max-parts` | Maximum multipart parts per request |
| `max-headers-size` | Memory cap for headers of each multipart part |

Boot 3.5 defaults: `max-in-memory-size` is 256KB; `max-disk-usage-per-part` **-1B** and `max-parts` **-1** indicate no limit. When exposing public upload endpoints, set intentional bounds.

These settings do not impose per-user total quotas or overall disk caps. With direct `Flux<PartEvent>` streaming, temp-file limits may not apply in the same way as `FilePart`; count bytes and enforce limits within the active pipeline.

## 15. Backpressure, Blocking, and Concurrency

**Backpressure** lets a downstream subscriber request only as much data as it can handle, preventing reactive sources from flooding the pipeline. When the storage sink is slower than the network, proper backpressure keeps in-flight buffers bounded.

```text
Network Flux<DataBuffer>
         |
   demand/backpressure
         |
    async file writer
         |
   bounded in-flight data
```

However, patterns like these defeat streaming:

```java
body.collectList();  // buffers all data
```

```java
body.flatMap(buffer -> uploadPart(buffer), 1000);
```

The second `flatMap` is an **illustrative snippet**: excessive concurrency spawns too many in-flight operations, driving up RAM and queues. Choose sensible concurrency/prefetch values and handle buffer ownership properly.

**Never call** `Thread.sleep()`, `InputStream.read()`, blocking JDBC, or `.block()` directly on the WebFlux event loop. If you must integrate a blocking SDK, isolate it on `Schedulers.boundedElastic()` with concurrency limits and monitoring. In Servlet MVC, blocking I/O is normal, yet thread usage and timeouts still need monitoring.

## 16. Total Byte Limits and Content-Length

Protect the server in layers:

1. Reverse proxy/WAF/Ingress caps request size and upload duration.
2. Embedded server caps timeouts, connections, headers, and applicable body limits.
3. Application checks authentication, upload permissions, and tenant quotas.
4. Streaming code **counts actual bytes received**, aborting if the limit is exceeded.
5. Storage enforces disk/object quotas, staging cleanup, and checksums.

`Content-Length` helps reject oversized payloads early, yet may be absent or untrustworthy. Never rely on it as the **only safeguard**. The Spring MVC example in Section 6 checks every `read()` and returns HTTP **413 Payload Too Large** beyond 50 MiB.

The WebFlux raw example in Section 9 does not yet enforce a total byte limit; before deploying, add byte counting prior to writes, ensure discarded buffers are released properly, delete incomplete files, and return errors matching your contract. Never mistake multipart disk thresholds for a total body size limit.

## 17. Aborted Uploads, I/O Errors, and File Staging

Uploads can fail mid-transfer due to browser close, proxy timeout, full disk, slow upstream, client cancellation, or server restart.

A safe workflow:

```text
Input stream
    |
    v
Server-generated staging path
    |
    +---- error/cancel/quota -> delete + audit
    |
    v
Verify byte count / checksum / file type / malware
    |
    v
Atomic move or publish object
    |
    v
Commit metadata + success response
```

Staged files should never be publicly downloadable before validation completes. On success, move to the final location atomically where the filesystem supports it, or complete the object-storage multipart upload.

In reactive pipelines, cleanup with `onError`, `doFinally`, and `usingWhen` must handle cancellation reliably; blocking filesystem operations should run on a blocking-safe scheduler. If the process is killed abruptly, cleanup callbacks **are not guaranteed to run**; schedule a TTL sweeper job for orphaned staging files.

The educational examples above show the primary data path rather than a complete production upload service; these safety steps are essential additions.

## 18. Streaming to Object Storage or Processing Record by Record

Instead of local files, data can stream straight downstream:

```text
HTTP body -> bounded buffers -> incremental checksum
          -> asynchronous multipart SDK -> object storage
```

Verify whether the SDK genuinely streams or silently buffers everything into a `byte[]`. For multipart uploads, memory usage can reach **part size × concurrent uploading parts**, plus overhead. Bounding concurrency and prefetch is mandatory.

For multi-record payloads, consider **NDJSON** (JSON Lines) instead of one giant JSON array:

```text
{"id":1,"value":"a"}
{"id":2,"value":"b"}
{"id":3,"value":"c"}
```

A WebFlux record-streaming snippet:

```java
@PostMapping(
    path = "/events",
    consumes = "application/x-ndjson")
public Mono<Void> receive(
        @RequestBody Flux<EventDto> records) {
    return records.concatMap(eventService::save).then();
}
```

This is an **illustrative method** inside a WebFlux controller requiring `EventDto` and `eventService.save` returning a reactive publisher. `concatMap` processes items sequentially rather than calling `collectList()`; if `save` uses blocking JDBC, isolate that blocking work properly.

In streaming JSON, the decoder still buffers **one record**, so cap individual record sizes too. A single 100 MB record defeats streaming even if the overall request is a stream.

## 19. Testing: Functionality, Memory, and Integrity

Thorough testing should cover:

- **Small files:** send 16 bytes, verify the response and destination file contain exactly 16 bytes.
- **Boundary sizes:** requests just below, equal to, and above the limit.
- **Integrity:** compare SHA-256 of the source file and stored file.
- **Concurrency:** multiple simultaneous uploads while measuring heap, direct memory, threads, disk, and throughput.
- **Client disconnect:** cancel mid-upload, confirm no incomplete file is published.
- **Slow uploads:** test slow body transmission, timeouts, and quotas.
- **Disk full:** verify error handling, cleanup, and logging.
- **Proxy path:** test through real CDN/Ingress/Gateway layers since each hop can buffer or reject.
- **Reactive buffer leaks:** test errors and cancellation on custom `DataBuffer` pipelines.
- **Sensible responses:** check statuses, JSON error structure, and no leaked sensitive details.

Create a 1 MiB file on Linux/macOS:

```bash
dd if=/dev/zero of=one-mib.bin bs=1048576 count=1
```

Upload raw:

```bash
curl -i -H 'Content-Type: application/octet-stream' \
  --data-binary @one-mib.bin \
  http://localhost:8080/api/upload/raw
```

Upload multipart to WebFlux:

```bash
curl -i -F "file=@one-mib.bin" \
  http://localhost:8080/api/upload/file
```

Verify checksum:

```bash
sha256sum one-mib.bin uploads/<actual-filename>
```

Substitute the actual filename from the response; if bytes were saved faithfully, both hashes match.

## 20. MockMvc Tests for the Servlet Example

With `spring-boot-starter-test` in the Spring Boot 3.5 MVC project, file `src/test/java/com/example/streaming/RawUploadControllerTest.java`:

```java
package com.example.streaming;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RawUploadControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void countsBytesWithoutLoadingWholeFile() throws Exception {
        mvc.perform(post("/api/upload/raw")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .content("abc".getBytes(StandardCharsets.UTF_8)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.bytes").value(3));
    }
}
```

Run in the project:

```bash
./mvnw test
```

This test verifies status and byte count; it **does not** validate network chunking or memory profiles. Because the example writes locally, real test suites should isolate storage to a temp directory, clean up test files, and check checksums. For WebFlux, use `WebTestClient` instead of `MockMvc`; to verify backpressure or cancellation, write dedicated reactive pipeline tests.

## 21. Common Issues and Troubleshooting

| Symptom | Cause | How to investigate |
|---|---|---|
| Heap grows with file size | `getBytes()`, `byte[]`, `collectList()`, `join()` | Locate aggregation step; switch to buffered/record streaming |
| `DataBufferLimitException` | Codec buffered content past limit | Inspect body type, codec, record size; do not raise limit endlessly |
| Temp disk fills up | Multipart parser spills parts to disk | Configure per-part disk limits, quotas, cleanup |
| WebFlux event loop stalls | Blocking filesystem/JDBC/SDK on wrong scheduler | Use async APIs or bounded `boundedElastic` |
| Direct memory climbs | Pooled `DataBuffer` retained or leaked | Audit lifecycle, cancellation, and leak detector |
| Slow uploads despite healthy heap | Slow storage sink or network | Measure per-hop latency, throughput, concurrency |
| Partial files left behind | Missing cancel/error cleanup or process kill | Add staging, cleanup, and background sweeper |
| 413 returned despite backend allowing size | Proxy/CDN/WAF has a lower limit | Check limits across every hop |
| Multipart fails before controller | Multipart resolver exceeded max-file/request-size | Inspect properties and container logs |
| Uploaded file has wrong checksum | Wrong byte count written, partial write, retry bug | Verify byte counts, checksums, atomic publish |

**Do not treat every symptom by raising memory limits.** Increasing `spring.http.codecs.max-in-memory-size` lets aggregation retain more memory—the exact outcome you want to avoid for large payloads.

## 22. Security and Operations

Uploads are untrusted input; enforce:

1. Authentication/authorization, quotas, and rate limits per user/tenant.
2. Never use original filenames for disk paths; generate server-side names and sanitize metadata.
3. Never trust client-sent MIME types; verify magic bytes/content format where needed.
4. Cap disk, inodes, total in-flight uploads, timeouts, and request lifetimes.
5. Publish only after checksum, malware scanning, and required validation pass.
6. Never log raw bodies, tokens, or personal data; log request ID, byte count, and duration.
7. Set TTL policies and sweep abandoned staging files.
8. For object storage, apply least-privilege SDK credentials and time-limited signed URLs.
9. Verify hashes when relaying data upstream to detect mid-stream truncation.
10. Monitor heap, direct memory, disk, network, connection pools, and event-loop saturation.

For multi-gigabyte uploads, consider **pre-signed URLs** letting clients upload straight to object storage while the backend confirms metadata. This keeps heavy traffic out of Spring Boot, though you must still enforce permissions, content types, sizes, and URL expiration.

## 23. Takeaways and References

**Takeaway:** Streaming means **not holding the entire request body in RAM**. In MVC, use `InputStream`/buffers or multipart transfers; in WebFlux, use `Flux<DataBuffer>`, `FilePart.transferTo`, or `Flux<PartEvent>` for buffer-level multipart processing. Memory still needs bounds, and production systems need byte counting, backpressure, quotas, cleanup, and integrity checks.

- Spring Framework — WebFlux reactive, limits, DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — Multipart WebFlux, FilePart, PartEvent: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework — DataBufferUtils Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Framework — MVC @RequestBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC Multipart: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — MultipartProperties: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html
- Spring Boot 3.5 — ReactiveMultipartProperties: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveMultipartProperties.html
