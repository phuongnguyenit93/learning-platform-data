# Streaming Large Files and Memory Limits by Web Stack

> Scope: Spring Boot web-runtime, Java 17+, Spring Boot 3.3 / Spring Framework 6.1. Focuses on large file uploads, differences between Spring MVC on Servlet and Spring WebFlux on Reactor Netty, heap/direct memory limits, temporary disk spooling, and confirming upload completion.

## 1. Objectives

After this lesson, you will be able to:

1. Explain why uploading 1 GiB does not require allocating a 1 GiB array in application memory.
2. Distinguish streaming from the socket, streaming from a multipart part spooled to temporary disk by the parser, and streaming via reactive DataBuffers.
3. Distinguish total request limits, per-file sizes, multipart part counts, memory thresholds, codec aggregation limits, and disk quotas.
4. Write a Spring MVC handler using MultipartFile and HttpServletRequest.getInputStream() without calling getBytes().
5. Write a WebFlux handler using FilePart.transferTo(Path) and Flux<DataBuffer> to receive files without collecting all bytes.
6. Explain when DataBuffers must be released, how to use PartEvent, and how to handle cancellation.
7. Design tests for oversized payloads, client disconnects, concurrent uploads, and observe heap, direct memory, disk, and latency.

## 2. Streaming Upload vs. “Complete File Received”

A client sends 500 MiB over HTTP. The server can read data in ~64 KiB blocks, write them to a temporary file, and only promote that temporary file to a valid file once all bytes arrive and content checks pass.

~~~text
client
  |
  | HTTP request body (multipart or raw binary)
  v
proxy / ingress / load balancer
  |  (may buffer request in RAM or disk)
  v
HTTP server (Servlet container or Reactor Netty)
  |
  +--> multipart parser, if multipart
  |      (may hold in RAM or spool to disk)
  |
  v
controller / reactive pipeline
  |
  | chunks / input stream / FilePart / DataBuffer
  v
private temporary file
  |
  | upload finished + verify size/checksum/format
  v
published file / object storage / metadata
~~~

“Streaming” is a strategy that avoids accumulating the entire payload in memory at a given processing stage. Always specify **which layer is streaming**: client to proxy, proxy to container, container to handler, or handler to storage. A handler reading MultipartFile.getInputStream() in 64 KiB chunks saves heap, yet the file part may already have been parsed and stored by the container before the handler ran.

Conversely, accepting byte[] or String for large bodies, calling MultipartFile.getBytes(), unbounded DataBufferUtils.join(), or Flux<DataBuffer>.collectList() creates memory pressure proportional to file size. The larger the files and the higher the concurrency, the greater the risk of OutOfMemoryError and GC pauses.

### Two Common Request Styles

| Style | Content-Type | Payload | API Choice |
|---|---|---|---|
| Multipart form | multipart/form-data | One or more file parts, with boundaries, headers, and form fields | MVC: MultipartFile; WebFlux: FilePart or Flux<PartEvent> |
| Raw binary | application/octet-stream | Entire body consists of one file's bytes | MVC: HttpServletRequest.getInputStream(); WebFlux: Flux<DataBuffer> |

With multipart, **one file's size** does not necessarily equal **the request size**. The request also carries boundaries, headers, fields, and possibly multiple files. For raw bodies, multipart configuration properties may not apply. Both styles require overall traffic-limit policies at the proxy and application layers.

## 3. Why Content-Length Alone Is Not Enough to Limit Uploads

The Content-Length header allows early rejection when a body exceeds allowed limits, but it must not be your sole protection:

- Clients can send requests without Content-Length depending on HTTP version/framing.
- Content-Length on a multipart message measures **the entire body**, not just the file part's exact bytes.
- Proxies can alter transfer framing, buffer, or impose their own body limits.
- An untrusted client can supply metadata inconsistent with actual data; the server must enforce limits based on bytes actually parsed/read.
- On error paths, partial bytes may already have been written to a temporary file requiring cleanup.

Therefore, enforce limits via the **multipart parser and/or an actual byte counter**. Use Content-Length as a fast-fail hint when present, never as a replacement for counting received bytes.

## 4. Spring MVC/Servlet: How Is MultipartFile Created?

Apps with spring-boot-starter-web run Spring MVC on an embedded Servlet container, most commonly Tomcat. Boot 3.3 configures multipart via the Servlet Part API and StandardServletMultipartResolver. For multipart/form-data requests, the container parses parts to supply MultipartFile / Part to the controller.

~~~text
POST multipart/form-data
   |
   v
Servlet multipart handling
   |
   +-- small parts: may stay in RAM
   +-- large parts: spool to temp disk per threshold/container
   |
   v
@RequestParam("file") MultipartFile
   |
   +-- getSize(): size metadata
   +-- getInputStream(): read part bytes
   +-- transferTo(...): move/copy content to target storage
   |
   v
application storage
~~~

Spring Boot 3.3 defaults:

| Property | Default | Meaning |
|---|---|---|
| spring.servlet.multipart.enabled | true | Enables multipart handling |
| spring.servlet.multipart.max-file-size | 1MB | Maximum size per file |
| spring.servlet.multipart.max-request-size | 10MB | Maximum total multipart request size |
| spring.servlet.multipart.file-size-threshold | 0B | Threshold for writing file parts to disk per container |
| spring.servlet.multipart.location | No fixed path configured | Intermediate multipart storage location |
| spring.servlet.multipart.resolve-lazily | false | Controls when the resolver parses parts |

**file-size-threshold=0B does not mean total RAM usage is zero.** Socket/TLS buffers, metadata, objects, and runtime overhead still exist; the setting mainly governs where part contents are stored. Once the multipart parser spools a part, reading getInputStream() in blocks avoids loading the whole file back onto the controller's heap.

### Configuring a 32 MiB File Demo

In the MVC app's src/main/resources/application.properties:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=32MB
spring.servlet.multipart.max-request-size=34MB
spring.servlet.multipart.file-size-threshold=0B
~~~

The 34MB cap leaves headroom over 32MB for multipart boundaries and metadata in a **single-file demo**. This is not a formula for multi-file uploads. If temp storage lives on a dedicated quota-managed mount, point spring.servlet.multipart.location to an existing directory writable by the container.

Do not set -1 (unlimited) for file size or request size just to bypass 413 errors on large uploads. First determine expected load, disk limits, concurrency, upload rates, and timeouts.

## 5. Runnable Spring MVC Example: Multipart and Raw Streaming

Prepare a **separate Spring Boot 3.3 + Java 17+ project** with starter-web. Dependency section in build.gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Assume the project already configures the Spring Boot Gradle plugin, repositories, and dependency management. Create the main class at src/main/java/example/mvcupload/MvcUploadApplication.java:

~~~java
package example.mvcupload;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class MvcUploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcUploadApplication.class, args);
    }

    @RestController
    public static class UploadController {
        private static final long MAX_BYTES = 32L * 1024 * 1024;
        private static final Path STORAGE =
                Path.of(System.getProperty("java.io.tmpdir"),
                        "mvc-upload-lab");

        @PostMapping(
                path = "/upload/multipart",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
        @ResponseStatus(HttpStatus.CREATED)
        public Receipt multipart(
                @RequestParam("file") MultipartFile file)
                throws IOException {
            if (file.isEmpty()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Empty file");
            }
            if (file.getSize() > MAX_BYTES) {
                throw new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE, "Too large");
            }
            try (InputStream in = file.getInputStream()) {
                return save(in);
            }
        }

        @PostMapping(
                path = "/upload/raw",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
        @ResponseStatus(HttpStatus.CREATED)
        public Receipt raw(HttpServletRequest request)
                throws IOException {
            try (InputStream in = request.getInputStream()) {
                return save(in);
            }
        }

        private Receipt save(InputStream input) throws IOException {
            Files.createDirectories(STORAGE);
            Path temporary = Files.createTempFile(
                    STORAGE, "partial-", ".tmp");

            try {
                byte[] block = new byte[64 * 1024];
                long total = 0;
                try (OutputStream output =
                             Files.newOutputStream(temporary)) {
                    int n;
                    while ((n = input.read(block)) != -1) {
                        if (n == 0) {
                            continue;
                        }
                        if (n > MAX_BYTES - total) {
                            throw new ResponseStatusException(
                                    HttpStatus.PAYLOAD_TOO_LARGE,
                                    "Too large");
                        }
                        output.write(block, 0, n);
                        total += n;
                    }
                }

                if (total == 0) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "Empty file");
                }
                String id = UUID.randomUUID() + ".bin";
                Files.move(temporary, STORAGE.resolve(id));
                return new Receipt(id, total);
            } finally {
                Files.deleteIfExists(temporary);
            }
        }

        public record Receipt(String id, long bytes) { }
    }
}
~~~

### Explaining Each Decision in the MVC Code

- MultipartFile merely exposes a part already managed by the multipart infrastructure. getSize() can reject early **after parsing**, while save() still counts actual bytes read. If a part already exceeds container limits, the handler is usually never invoked.
- The raw endpoint reads HttpServletRequest.getInputStream() up to 64 KiB at a time and writes immediately to a temp file. The 64 KiB array **does not grow with file size**; reading from the socket can block the Servlet worker thread if the client is slow.
- The check n > MAX_BYTES - total avoids integer overflow while counting. The file is renamed only after reaching normal EOF, passing size checks, and finishing writes.
- The temporary file resides in the same directory as the final file so Files.move is usually cheaper than a cross-filesystem copy. However, Java does not guarantee every Files.move is atomic or fsynced to disk; use explicit storage guarantees if strict durability is required.
- finally deletes the temporary file on size violation, read error, write error, or move failure. When move succeeds, the old temp path no longer exists, so deleteIfExists leaves the final file untouched.
- The ID is server-generated via UUID rather than using MultipartFile.getOriginalFilename() as a path. Client filenames can be unsafe or cause overwrites.
- Storing under java.io.tmpdir is only for labs. Production needs a dedicated volume/object storage, restricted permissions, quotas, cleanup, and scanning.

**Do not call MultipartFile.getBytes()** in this example. It allocates a byte array for the entire file content. Even when the multipart part was spooled to disk, calling getBytes() pulls the entire file back onto the heap.

Run on Linux/macOS with `./gradlew bootRun` or Windows with `gradlew.bat bootRun`. The application listens on port 8080 by default unless changed.

## 6. MVC Multipart Is Not Direct HTTP Streaming to the Controller

The two endpoints take different paths:

~~~text
Multipart:
socket -> container multipart parser -> RAM/disk part storage
      -> MultipartFile.getInputStream() -> 64KiB buffer -> temp -> final

Raw:
socket -> HttpServletRequest.getInputStream()
      -> 64KiB buffer -> temp -> final
~~~

In multipart, reading getInputStream() in blocks is **application-layer streaming**, yet does not guarantee the controller sees bytes as soon as they arrive on the socket. In Servlet implementations, the container may finish parsing before exposing MultipartFile.

In raw mode, the controller reads incrementally from ServletInputStream, though read() uses traditional blocking Servlet I/O. With 100 very slow clients, worker threads, timeouts, and connection limits become critical resources. If a reverse proxy enables request buffering, even raw requests may be buffered by the proxy before reaching the app.

The spring.servlet.multipart.* limits do not automatically apply to **raw bodies**; therefore raw handlers need an explicit byte counter and gateways need body caps and timeouts. Never assume max-file-size=32MB protects an application/octet-stream endpoint.

## 7. Spring WebFlux: Differences Across FilePart, DataBuffer, and PartEvent

With **spring-boot-starter-webflux** and Reactor Netty, handlers can receive files via different abstractions:

| API | Content-Type | Meaning | Pitfalls |
|---|---|---|---|
| FilePart | multipart/form-data | Multipart reader manages part and provides transferTo(Path) returning Mono<Void> | Parser may still buffer part in RAM/disk; not a raw socket API |
| Flux<DataBuffer> | application/octet-stream | Reactive stream of raw body byte buffers | Never unbounded collectList/join; must manage release/cancellation |
| Flux<PartEvent> | multipart/form-data | Receives part events sequentially; can forward segments immediately | Must separate parts, consume/release all buffers, enforce byte cap yourself |

Reactive backpressure lets stages coordinate pace by demand, yet **is not a quota**. If disk fills up, the controller queues excessively, or buffers are retained without release, the app can still exhaust resources.

### WebFlux Limits in Boot 3.3

| Property | Default | Description |
|---|---|---|
| spring.webflux.multipart.max-in-memory-size | 256KB | Caps aggregation of non-file parts; file parts spill to disk above threshold |
| spring.webflux.multipart.max-disk-usage-per-part | -1B | Uncapped disk usage per spooled part by default |
| spring.webflux.multipart.max-parts | -1 | Uncapped number of parts by default |
| spring.webflux.multipart.max-headers-size | 10KB | Limits multipart headers per part |
| spring.webflux.multipart.file-storage-directory | spring-multipart folder under system temp | Temp directory for spooling multipart reader; **ignored for streaming PartEvent** |
| spring.codec.max-in-memory-size | No global Boot override; many codecs default to 256KB | Limit when a codec must **aggregate** input in auto-configured WebFlux server/WebClient |

Example src/main/resources/application.properties in a WebFlux lab project:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=32MB
spring.webflux.multipart.max-parts=4
spring.webflux.multipart.max-headers-size=10KB
spring.codec.max-in-memory-size=256KB
~~~

256KB on the multipart reader **does not mean** a 5 MiB file is rejected: file content can be spooled to disk. Nor is it a 256KB cap on total request heap, since HTTP buffers, metadata, JSON codecs, socket buffers, and other work still consume memory.

max-disk-usage-per-part applies to file parts spooled to disk by the parser, not as a global request cap. For raw Flux<DataBuffer> and streaming PartEvent, the app must count received bytes. Never set max-in-memory-size=-1 just to accept large files, as that can keep entire parts in RAM.

## 8. Runnable Spring WebFlux Example: Two Ways to Receive Large Files

Create a **separate** project using Java 17+, Spring Boot 3.3, and only the WebFlux starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

If both starter-web and starter-webflux are present, Boot usually selects MVC/Servlet by default; the example below requires the WebFlux server so behavior matches the description.

Create src/main/java/example/reactiveupload/ReactiveUploadApplication.java:

~~~java
package example.reactiveupload;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveUploadApplication {
    public static void main(String[] args) throws IOException {
        Files.createDirectories(UploadController.STORAGE);
        SpringApplication.run(ReactiveUploadApplication.class, args);
    }

    @RestController
    public static class UploadController {
        private static final long MAX_BYTES = 32L * 1024 * 1024;
        private static final Path STORAGE =
                Path.of(System.getProperty("java.io.tmpdir"),
                        "webflux-upload-lab");

        @PostMapping(
                path = "/upload/part",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
        public Mono<ResponseEntity<Receipt>> part(
                @RequestPart("file") FilePart file) {
            return save(file::transferTo);
        }

        @PostMapping(
                path = "/upload/raw",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
        public Mono<ResponseEntity<Receipt>> raw(
                @RequestBody Flux<DataBuffer> requestBody) {
            AtomicLong count = new AtomicLong();

            Flux<DataBuffer> checked = requestBody
                    .<DataBuffer>handle((buffer, sink) -> {
                        int size = buffer.readableByteCount();
                        if (size > MAX_BYTES - count.get()) {
                            DataBufferUtils.release(buffer);
                            sink.error(new ResponseStatusException(
                                    HttpStatus.PAYLOAD_TOO_LARGE,
                                    "Too large"));
                        } else {
                            count.addAndGet(size);
                            sink.next(buffer);
                        }
                    })
                    .doOnDiscard(DataBuffer.class,
                            DataBufferUtils::release);

            return save(path ->
                    DataBufferUtils.write(checked, path));
        }

        private Mono<ResponseEntity<Receipt>> save(
                Function<Path, Mono<Void>> writeToFile) {
            return Mono.usingWhen(
                    Mono.fromCallable(() ->
                            Files.createTempFile(
                                    STORAGE, "partial-", ".tmp"))
                        .subscribeOn(Schedulers.boundedElastic()),

                    temp -> writeToFile.apply(temp)
                            .then(Mono.fromCallable(() -> publish(temp))
                                    .subscribeOn(
                                            Schedulers.boundedElastic()))
                            .map(receipt -> ResponseEntity
                                    .status(HttpStatus.CREATED)
                                    .body(receipt)),

                    this::removeTemp
            );
        }

        private Receipt publish(Path temp) throws IOException {
            long size = Files.size(temp);
            if (size == 0) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Empty file");
            }
            if (size > MAX_BYTES) {
                throw new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE, "Too large");
            }

            String id = UUID.randomUUID() + ".bin";
            Files.move(temp, STORAGE.resolve(id));
            return new Receipt(id, size);
        }

        private Mono<Void> removeTemp(Path temp) {
            return Mono.fromRunnable(() -> {
                        try {
                            Files.deleteIfExists(temp);
                        } catch (IOException ex) {
                            throw new UncheckedIOException(ex);
                        }
                    })
                    .subscribeOn(Schedulers.boundedElastic())
                    .then();
        }

        public record Receipt(String id, long bytes) { }
    }
}
~~~

### Why Does the WebFlux Code Have Two Separate Paths?

**/upload/part** accepts FilePart. The multipart reader decides whether to keep parts in RAM or temp disk based on multipart properties. FilePart.transferTo(Path) returns Mono<Void> to finish writing without calling block() in the controller. After transfer, the app verifies the actual size and publishes the file.

**/upload/raw** accepts a Flux<DataBuffer>. Each DataBuffer holds a byte chunk. The handle operator increments an AtomicLong counter per accepted buffer. If exceeding 32 MiB, the incoming buffer is released immediately and the pipeline signals an error. Buffers passed to DataBufferUtils.write(Path) are written and released by the Path-overload API. doOnDiscard frees DataBuffers dropped on cancel/error inside operators that support discard.

**Do not confuse DataBufferUtils.write overloads:** the overload writing to Path returning Mono<Void> has different completion/release semantics from overloads taking OutputStream or WritableByteChannel returning Flux<DataBuffer>, which **do not automatically release** source buffers; code calling the latter must ensure release itself.

**Mono.usingWhen** manages the temporary file resource reactively: supplies the path, executes the writer, and runs cleanup on all terminal paths (success, error, cancel). Blocking calls Files.createTempFile, Files.size, Files.move, and Files.deleteIfExists are shifted onto boundedElastic instead of the Netty event loop. FilePart.transferTo may still use internal file storage or its own worker; never assume the entire write path is “zero-copy.”

**Receipt is created only after the writer completes and publishing succeeds.** FilePart max-disk-usage-per-part still guards the parser before the controller sees FilePart. The raw path uses its own counter and gets no multipart parser protection. Client cancels, disk errors, or process crashes can leave temp files behind; monitor and run periodic cleanup outside the request lifecycle.

**Demo limitations:** storage under java.io.tmpdir is only for local labs. It omits authentication, virus scanning, checksums, per-user quotas, metadata transactions, filesystem durability, and direct-to-object-storage. Never expose these endpoints as a production service using just this demo code.

Run the project with `./gradlew bootRun` (Unix) or `gradlew.bat bootRun` (Windows).

## 9. When to Use PartEvent Instead of FilePart?

In WebFlux, @RequestBody Flux<PartEvent> is the event-level multipart streaming API. A file part can emit multiple FilePartEvents; FormPartEvent represents a form field. PartEvent.isLast() marks the final event **of the current part**. Thus you can use windowUntil to split events per part, switchOnFirst to inspect the part type, and process subsequent DataBuffers sequentially.

Structural pattern to recognize the API (not a complete file-saving handler):

~~~java
// Inside a WebFlux controller with Flux<PartEvent> events:
events.windowUntil(PartEvent::isLast)
      .concatMap(partEvents ->
          partEvents.switchOnFirst((signal, window) -> {
              if (signal.hasValue()) {
                  PartEvent first = signal.get();
                  // Inspect FormPartEvent or FilePartEvent.
                  // Consume/relay/release the entire window.
              }
              return window;
          }));
~~~

The snippet only illustrates windowing structure; import PartEvent properly, handle error/cancel, and implement actual storage before use. **Do not** copy it into an endpoint and claim files are saved. Ignoring an event without releasing content() can leak direct memory when Netty uses pooled DataBuffers.

Special note: spring.webflux.multipart.file-storage-directory applies to spooled multipart parsing, **not to PartEvent streaming** per Boot 3.3 documentation. PartEvent streaming requires limiting part count, bytes, header/form metadata, receive timeouts, and storage resources yourself; do not assume max-disk-usage-per-part automatically protects streaming uploads.

For standard forms that just need to save files, FilePart.transferTo is usually clearer. PartEvent fits better when you need to read/process/relay each segment as it arrives and are ready to take responsibility for buffer lifecycles.

## 10. Why Does Raw Flux<DataBuffer> Require Careful Release?

Spring WebFlux DataBuffer can wrap a Netty ByteBuf backed by pooled direct memory with reference counting. If code collects buffers into a list or drops them without releasing properly, memory/native allocations may never return to the pool; heap graphs sometimes do not reveal the leak.

Distinguish:

- FilePart.transferTo(Path): lets the framework API write the file and manage resources per the method contract.
- DataBufferUtils.write(Publisher<DataBuffer>, Path): works with a buffer stream and signals completion; check the exact contract of the overload you call.
- Consuming DataBuffer manually in map/subscribe: must release once read; if using filter/skip/flatMap where discard/cancel can happen, attach appropriate doOnDiscard.
- DataBufferUtils.join() aggregates buffers: **never use unbounded** for multi-GiB payloads; it has an overload taking maxByteCount, though that still differs from direct streaming.
- Passing to WebClient / ServerHttpResponse: clarify buffer ownership and who releases after relay; never retain/release arbitrarily.

If direct memory climbs after many aborted uploads, audit pooled buffers and cleanup rather than simply raising JVM -Xmx. Enabling appropriate Netty leak detection in tests can help locate held buffers, though it adds overhead and does not replace load/disconnect tests.

## 11. Memory Budget and Throughput Must Scale with Concurrency

Suppose an MVC raw upload uses a byte[64 KiB] array per active request. With 200 concurrent requests, **the controller arrays alone** consume:

~~~text
200 x 64 KiB = 12,800 KiB = 12.5 MiB
~~~

This **does not mean** total memory for 200 uploads is 12.5 MiB: there are still thread stacks (MVC), socket buffers, TLS, multipart parsers, JVM overhead, OS page cache, object metadata, DB connections, direct/native memory, and intermediate libraries.

If switched to MultipartFile.getBytes() for 100 MiB files across 200 concurrent uploads, just one full-file copy per request needs:

~~~text
200 x 100 MiB = 20,000 MiB, nearly 19.5 GiB
~~~

Before counting additional copies and GC. Streaming eliminates a major memory multiplier, yet does not remove every bottleneck.

**Disk bandwidth** is also a cap: if storage sustains 100 MiB/s real write throughput and each file is 20 MiB, ideal write-bound throughput is around 5 files/s before overhead. When a multipart parser spools to a temp file and the app copies to final storage, the same payload may incur multiple reads and writes. Files.move on the same filesystem is usually cheap, whereas moving across filesystems may not be atomic and can fail or be unsupported.

For WebFlux, monitor both heap **and** direct memory, outstanding DataBuffers, event-loop lag, queues, connection counts, file handles, temp disk, pending writes, and bandwidth. Backpressure does not guarantee bounded storage if the application keeps accepting new uploads beyond system capacity.

## 12. Large File Uploads Need an Explicit State Lifecycle

A practical lifecycle:

~~~text
RECEIVED REQUEST
   |
   v
authenticate + authorize + quota
   |
   v
allocate private temp / upload session ID
   |
   v
stream bytes + count + optional incremental checksum
   |
   +---- size exceeded / timeout / I/O error / cancel
   |             |
   |             v
   |        close + release + cleanup
   |
   v
stream complete
   |
   v
verify actual size, checksum, type, malware scan
   |
   v
publish file / object key
   |
   v
commit metadata and ownership
   |
   v
201 Created / confirmed upload
~~~

Request acceptance and file publication are two separate milestones. If a client disconnects after sending 90% of the body, the partial file must never appear under the final name. Temporary files keep those states distinct. Apps combining a database and object storage need **compensation/outbox/idempotency** when file publication and metadata commit are not a single transaction.

- **Timeouts:** total deadline, idle timeout, minimum transfer rate, and max concurrent uploads. A client sending 1 byte every few seconds can tie up a connection for a long time.
- **Cancellation:** in MVC, the next read may throw IOException; in WebFlux, a cancel signal arrives. Instant detection of client disconnect is not guaranteed.
- **Disk full:** writes fail; cleanup may fail too. Log failures, alert on remaining capacity, and run scheduled cleanup for leftovers.
- **Process crash:** finally or Mono.usingWhen will not run if the process is killed abruptly; add scheduled cleanup based on temp file/session age.
- **Retries:** prevent retries from creating endless duplicates. Consider idempotency keys and resumable/chunked upload protocols for multi-GiB files.
- **Checksums:** compute SHA-256 incrementally per block during streaming or after saving, comparing against client checksums per your trust model.
- **Malware/type checks:** client-declared Content-Type and extension are untrusted; check magic bytes and scan content in isolation where business policy requires.

Do not pull the entire file onto the heap just to compute a checksum or inspect MIME. Read sequentially multiple times or chain a bounded-memory digest/validator pipeline.

## 13. Hands-On Testing via curl

Create a 5 MiB sample file on Linux/macOS:

~~~bash
dd if=/dev/zero of=sample.bin bs=1048576 count=5
~~~

On Windows PowerShell:

~~~powershell
$bytes = New-Object byte[] (5 * 1024 * 1024)
[System.IO.File]::WriteAllBytes('sample.bin', $bytes)
~~~

The PowerShell command allocates 5 MiB **on the machine generating the fixture**, not inside the upload API. The resulting file is exactly 5 × 1,048,576 = **5,242,880 bytes**.

Run **one** of the two applications at a time; both default to port 8080.

For the MVC app:

~~~bash
curl -i -F "file=@sample.bin" http://localhost:8080/upload/multipart

curl -i -H "Content-Type: application/octet-stream" --data-binary @sample.bin http://localhost:8080/upload/raw
~~~

For the WebFlux app:

~~~bash
curl -i -F "file=@sample.bin" http://localhost:8080/upload/part

curl -i -H "Content-Type: application/octet-stream" --data-binary @sample.bin http://localhost:8080/upload/raw
~~~

On Windows PowerShell, if curl is an alias, use curl.exe. On multipart endpoints, -F generates the multipart Content-Type and boundary; the raw endpoint uses --data-binary to preserve raw bytes.

A successful response returns **HTTP 201 Created** and a JSON body with a random id and bytes = 5242880, for example:

~~~json
{"id":"550e8400-e29b-41d4-a716-446655440000.bin","bytes":5242880}
~~~

The UUID here is **only an illustrative example**, not a deterministic output string. Verify the file actually exists with the right size and checksum rather than trusting status alone.

### Testing Failure Cases

- Empty file: the demo handler rejects with HTTP 400 once it reaches the handler.
- 40 MiB file: exceeds the 32 MiB limit; verify the server rejects at the appropriate layer (proxy, parser, or counter).
- Just under, exact threshold, and 1 byte over threshold: catch off-by-one comparison bugs.
- Two file parts when the controller expects one: test max-parts and total request-size.
- Very long multipart field: test header limits and non-file part aggregation.
- Cancel curl mid-upload: verify `.tmp` files are gone when lifecycle cleanup runs, and have a sweeper job for abrupt process termination.
- Test through ingress/reverse proxy: compare time-to-first-byte and disk usage against direct calls to spot request buffering.

**Never assume every limit violation returns 413.** Depending on container, multipart parser, exception handlers, proxies, and configuration, errors map differently. If the API contract mandates 413, add appropriate ExceptionHandler/ProblemDetail mappings and dedicated integration tests.

## 14. Load Testing Uploads: Measure Bytes/s and Concurrent Sessions

Uploads differ from typical JSON APIs. 100 requests/s could mean 100 × 1 KiB files or 100 × 1 GiB files; RPS alone does not reflect throughput volume.

In every test run, record:

- File size distribution (p50, p95 size), raw vs. multipart, client upload rate, concurrent sessions.
- Offered requests/s, completed uploads/s, accepted bytes/s, written bytes/s, error/timeout/cancel rates.
- p50/p95/p99 upload completion time and, where needed, time-to-first-byte/processing start.
- JVM heap, GC pauses, Netty direct memory, outstanding DataBuffer counts, Servlet workers, queues/boundedElastic.
- Disk write throughput, free space, inodes, temp files, object-storage latency, proxy buffering.
- Warm-up, steady-state, overload stress, and post-spike recovery phases.

A 30-second test with one fast client does not prove the system survives many slow clients concurrently. Test **slow uploads**, **cancellations**, and **soak runs** (multi-hour runs in test environments where appropriate) to uncover memory/file leaks. Cap rates and connections so you do not exhaust shared test infrastructure.

### Success Criteria

Sustainable upload capacity under a given configuration is the offered upload rate / concurrent upload count that meets target completion times and error rates over an extended duration, with stable disk/heap/native memory/queues and no runaway temp-file buildup. Never label a few-second peak burst as “maximum sustainable throughput.”

## 15. Security and Operational Risks

**Never trust client filenames.** MultipartFile.getOriginalFilename() or FilePart.filename() can include path fragments, special characters, or duplicates. If storing the original name as metadata, normalize and display safely; **the actual storage path** should be server-generated inside a restricted-permission directory.

**Never treat extension/MIME as proof of content.** Uploaded files can carry scripts, malware, zip bombs, malicious images, or polyglots. Scan, validate, and isolate per business requirements, especially before serving back publicly.

**Authorize before ingesting or publishing.** For large files, check user authentication, per-user quotas, rate limits, and expected limits early. Enforce ownership on read/delete later; never treat predictable or even opaque IDs alone as authorization.

**Storage and cleanup are part of the API.** Provision quotas/retention for temp and final storage, clean up on error and process crash, and watch file-descriptor limits, symlink/hardlink races, directory permissions, object stores, and backups. Multipart payloads with many tiny parts can also cause DoS even when each file is small.

**Do not disable limits for the sake of “streaming.”** Streaming reduces heap retention, yet does not bound disk, network, request rate, or duration. Quotas, Content-Length fast-reject, actual byte counting, and concurrency controls remain essential.

## 16. Common Errors Troubleshooting Table

| Symptom | Likely Cause | Concrete Action |
|---|---|---|
| Multipart file > 1MB rejected in MVC | Default max-file-size=1MB | Configure controlled max-file-size and max-request-size; check proxies |
| 20MB multipart fails despite max-file-size=32MB | Lower max-request-size or gateway cap; overhead or multiple parts | Inspect actual exception and check every layer |
| 5 MiB file in WebFlux throws DataBufferLimitException | Body aggregated into decoder/byte[]/String, or non-file part exceeded limit | Use FilePart/Flux<DataBuffer> properly; do not raise codec limit indefinitely |
| WebFlux multipart fills temp disk | max-disk-usage-per-part=-1, missing quotas/cleanup | Set max-disk-usage-per-part, max-parts, and storage quotas |
| Oversized raw upload still written | Only configured spring.servlet.multipart.* | Add raw byte counter and gateway body cap |
| Heap grows with file size | getBytes(), collectList(), join, or full-body copy | Switch to InputStream/transferTo/DataBuffer streaming |
| Direct memory climbs after cancels | DataBuffer unreleased / missing doOnDiscard | Audit buffer lifecycle, leak detection, and cancellation |
| Upload duration rises, CPU stays low | Waiting on client/disk/connection pool/threads | Measure I/O throughput, worker queues, and slow clients |
| WebFlux event loop stalls | Blocking Files.* or sync SDK inside reactive callbacks | Offload blocking operations off the event loop |
| Corrupted file after client cancel | Wrote directly to final file without cleanup | Stage in temp + publish on completion + cancel cleanup |
| Existing file overwritten | Used client filename or reused IDs | Generate server-side UUID/ID; check ownership and collisions |
| Proxy upload slower than direct | Proxy body buffering, timeouts, TLS, or network | Compare ingress config and trace end-to-end data path |

## 17. Implementation Decision Rules

**Spring MVC with standard multipart forms:** use MultipartFile, configure size/threshold limits, read getInputStream in blocks or transferTo when suitable. Never call getBytes() on large files. Monitor Servlet worker threads and multipart temp storage.

**Spring MVC needing raw body:** read HttpServletRequest.getInputStream() with a bounded buffer, count bytes, write to temp. It saves heap but remains blocking I/O, so guard concurrency and timeouts.

**Spring WebFlux multipart:** use FilePart.transferTo(Path), multipart memory/disk/parts limits, and handle Mono completion/errors. Offload blocking filesystem metadata ops if invoked in the pipeline.

**Spring WebFlux raw:** use @RequestBody Flux<DataBuffer> with a proper writer, count bytes yourself, ensure buffer release/discard/cancel. Never turn the reactive stream into a full List<DataBuffer>.

**Event-by-event streaming multipart:** Flux<PartEvent> when immediate relay/processing is required, accepting responsibility for per-part limits, content buffers, cleanup, and error handling.

**Multi-GiB files and object storage:** evaluate resumable/multipart protocols, presigned upload URLs fitting your security/business model, post-upload scan/checksum, and aborting incomplete sessions. Do not route every byte through the JVM unless the server needs to inspect it.

## 18. Review Questions

**Q1.** Does calling MultipartFile.getInputStream() in Spring MVC guarantee zero temporary disk usage?  
**Answer:** No. The Servlet container may already have spooled the file part. Reading via stream only avoids loading the whole payload onto the controller's heap.

**Q2.** Does file-size-threshold=0B mean zero bytes are held in RAM?  
**Answer:** No. It governs part spooling, not HTTP/TLS/metadata buffers or runtime overhead.

**Q3.** Is setting spring.codec.max-in-memory-size=2GB the standard way to upload a 2GB file?  
**Answer:** No. That is the codec aggregation limit; streaming and multi-layer hard caps are the right design.

**Q4.** Does max-disk-usage-per-part=32MB in WebFlux automatically block a 40MB raw upload?  
**Answer:** No. Raw Flux<DataBuffer> bypasses multipart file-part spooling; enforce actual byte limits in your pipeline.

**Q5.** Does FilePart.transferTo returning Mono<Void> mean the file has been virus-scanned?  
**Answer:** No. The Mono only signals completion or failure of transferring bytes. Validation, scanning, publishing, and metadata are separate business steps.

**Q6.** Why must you clean up on cancellation?  
**Answer:** Partial payload bytes may already sit on disk; leaving them fills temp storage or exposes incomplete data.

**Q7.** If MVC code allocates only a 64 KiB array, is total upload memory guaranteed to stay within 64 KiB per request?  
**Answer:** No. Container, sockets, proxies, thread stacks, TLS, multipart parsers, and other layers also consume memory.

**Q8.** Does WebFlux backpressure automatically cap total bytes per upload?  
**Answer:** No. Backpressure regulates consumption pace; byte caps and quotas must be implemented independently.

**Q9.** Can Content-Length serve as your only size limit?  
**Answer:** No. The header may be absent or framing may change; parsers and application logic must count/limit actual data.

**Q10.** Does passing 100 RPS with 1 KiB uploads prove the system handles 100 RPS with 1 GiB uploads?  
**Answer:** No. Measure file size distribution, bytes/s, concurrency, disk speed, memory, and error SLOs.

## 19. Official Documentation

- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): Servlet multipart, WebFlux multipart, and codec limits.
- [Spring Boot – Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): Servlet Part auto-configuration and file/request limits.
- [Spring Framework – Servlet Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): StandardServletMultipartResolver and container parsing.
- [Spring Framework – WebFlux Multipart Content](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): FilePart, PartEvent, and multipart streaming.
- [Spring Framework – WebFlux Request Body](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html): reactive request-body streaming.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffers and release responsibilities.
- [Spring Framework 6.1 DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): write, join, and release overloads.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): request bodies, Content-Length, and HTTP message semantics.
