# Heap Memory, Direct Memory, and HTTP Read/Write Buffers

## 1. Context: Running Out of Memory Even When Heap Is Not Full

Suppose a Spring Boot service receives files, decodes JSON, calls downstream services with `WebClient`, and returns HTTP files. A dashboard reports **Java heap at only ~50%**, yet the container gets OOMKilled or the server logs:

~~~text
java.lang.OutOfMemoryError: Cannot reserve ... bytes of direct buffer memory
~~~

Another service avoids direct-memory errors, yet after raising the JSON limit from 256 KiB to 50 MiB, GC pauses, latency, and `java.lang.OutOfMemoryError: Java heap space` climb sharply. A third application has a "streaming" `Flux<DataBuffer>` endpoint that calls `collectList()`, unbounded `DataBufferUtils.join()`, or caches `ByteBuf` instances without releasing them, causing memory to grow with client count.

To explain this, we must separate **heap objects**, **native/off-heap/direct memory**, **transport-owned buffers**, **HTTP codec aggregation buffers**, and **kernel/proxy buffers**. These categories interact, yet they are not the same metric and are not governed by a single configuration setting.

This lesson belongs to **Performance and Limits** in the Spring Boot web runtime. After studying it, you will be able to:

1. Distinguish `-Xmx`, `-XX:MaxDirectMemorySize`, process RSS/cgroup memory, Java NIO direct buffers, Netty pooled `ByteBuf`, and socket buffers.
2. Trace the path of an HTTP request/response from socket → decoder → `DataBuffer` → JSON/multipart → controller and back out.
3. Understand why `spring.http.codecs.max-in-memory-size` is not a global HTTP body size cap.
4. Track ownership of pooled `DataBuffer` instances and release them via `DataBufferUtils.release` when **consuming** buffers directly.
5. Compare aggregation vs streaming, backpressure, slow consumers, codec limits, multipart disk spill, and protecting systems from large uploads/downloads.
6. Run a **Spring Boot 3.5.x + Java 17+ + WebFlux** demo with streaming SHA-256 upload, chunked response download, JSON codec limits, and JVM memory observation.
7. Use Micrometer, Reactor Netty allocator metrics, `jcmd`/Native Memory Tracking, and load tests to locate heap/direct memory pressure without blindly expanding memory limits.

> **Version Scope:** Hands-on examples use Spring Boot **3.5.x**, Spring Framework **6.2.x**, and Java **17+**. Boot 3.5 uses **`spring.http.codecs.max-in-memory-size`**. In earlier Boot versions, that property was typically `spring.codec.max-in-memory-size`; do not mix them across versions. For Boot 4.x, check its corresponding property/starter docs. Never assume defaults, allocators, and metric names are identical across all containers and servers.

## 2. Memory Map of a Spring Boot Process

~~~text
Container / host physical memory, cgroup quota
|
+-- Java process address space / RSS
|   |
|   +-- Java HEAP (capped by -Xmx)
|   |   +-- Java objects: DTO, String, byte[], List, Map
|   |   +-- Jackson-decoded JSON object graph
|   |   +-- queues/caches, metadata, Java wrappers of native buffers
|   |
|   +-- JVM non-heap/native memory
|   |   +-- Metaspace, class metadata
|   |   +-- JIT code cache, GC structures
|   |   +-- Thread stacks
|   |   +-- Java NIO direct ByteBuffer allocations
|   |   +-- Native allocations / Netty pooled direct memory
|   |   +-- TLS/native libraries, mmap, and other components
|   |
|   +-- Memory-mapped files / shared libraries / page residency
|
+-- OS kernel memory (socket send/receive buffers, TCP queues)
+-- Sidecars / reverse proxies if sharing the relevant Pod/cgroup
~~~

This diagram is an operational model, not an **absolute mutually exclusive breakdown** across every accounting system. Heap may not yet be committed up to `-Xmx`. Reserved and committed memory differ; RSS does not equal the sum of all "max" flags. Some native memory is not fully tracked by JVM NMT. Kernel socket buffers are accounted for differently depending on Linux and cgroup version.

### Important Limits

| Limit or Statistic | Meaning | What It Does Not Mean |
|---|---|---|
| `-Xmx512m` | Max Java heap capacity ~512 MiB | Does **not** mean the entire process uses ≤512 MiB |
| `-Xms256m` | Initial/min JVM heap sizing | Does not cap direct/native memory |
| `-XX:MaxDirectMemorySize=256m` | Cap for a class of **Java NIO direct-buffer allocations** per JVM | Not a hard cap for **all** off-heap/native allocations |
| Container `memory.max`/memory limit | Memory budget enforced by cgroup | Does not automatically partition heap/direct/native safely |
| Micrometer `jvm.memory.used{area=heap}` | Heap used at sample time | Does not show all Netty direct allocations |
| Java `BufferPoolMXBean` direct | Memory/counters tracked by Java NIO direct buffer pool | Does not necessarily cover native buffers allocated separately by Netty |
| Reactor Netty `used.direct.memory` | Direct allocator reserved bytes per Netty meter | Not equal to total process RSS or JVM heap |

**Common mistake:** assigning a 768 MiB container memory limit, setting `-Xmx768m`, and wondering why the pod gets OOMKilled. The process still needs direct/native memory, metaspace, code cache, thread stacks, and other overhead. Leave **headroom** and validate under real load rather than summing max settings as exact arithmetic.

## 3. What Is Java Heap? What HTTP Data Typically Lives on the Heap?

Heap holds Java objects; the garbage collector reclaims unreachable objects. In a web application:

- `String`, `byte[]`, `Map`, and records/DTOs from JSON decoding typically live on the heap.
- A parsed JSON request can allocate **far more object bytes than the raw JSON size**: strings, collections, indexes, boxing, references, and object headers.
- `@RequestBody byte[]` requires a contiguous byte array for the aggregated body; converting it to `String`, Base64, or a JSON tree can hold **multiple copies simultaneously**.
- A response serialized into a large `byte[]`/`String` before sending also consumes heap.
- An unbounded cache or list accumulation can fill `-Xmx` even when direct buffers and sockets look fine.

Illustrative memory path:

~~~text
HTTP request body on wire: 2 MiB JSON
   |
   +-- inbound network DataBuffers (direct/heap depending on runtime)
   +-- codec aggregation buffer(s)
   +-- Java DTO graph and Strings
   +-- object validation / business copies
   +-- response serialization buffer(s)
~~~

Never assume `2 MiB body = 2 MiB heap`. Copy counts and object expansion depend on converters, JSON shape, JVM, codecs, compression/decompression, and concurrency. JSON containing hundreds of thousands of small elements has much higher overhead than a binary blob of equal byte size.

### Heap OOM and GC Pressure

Symptoms:
- `java.lang.OutOfMemoryError: Java heap space`.
- Heap used sits near `-Xmx`, GC runs frequently while reclaiming little.
- High allocation rate when building or parsing large bodies.
- Endpoints calling `collectList()` and holding entire streams.
- Jackson deserialization creating enormous object graphs.
- Retained heap rises after requests finish due to caches, static collections, or subscriber references.

Distinguish **GC pressure from high allocation throughput** (reclaimable after GC) from a **memory leak from retained references** (post-GC old-gen climbs steadily with clear retainers in a heap dump).

## 4. What Is Direct Memory? Java NIO `ByteBuffer.allocateDirect`

Java NIO offers two fundamental buffer types:

~~~java
import java.nio.ByteBuffer;

ByteBuffer heap = ByteBuffer.allocate(4096);
ByteBuffer direct = ByteBuffer.allocateDirect(4096);

System.out.println(heap.isDirect());   // false
System.out.println(direct.isDirect()); // true
~~~

This is a **Java fragment**; it can sit inside `main` of any Java 17 class. `ByteBuffer.allocate` uses Java heap backing storage; `allocateDirect` requests a buffer the JVM can use more efficiently for certain native I/O operations.

A direct buffer still has a **Java wrapper object on the heap**, while its byte backing resides in **native/off-heap memory**. Direct does not mean "automatically zero-copy everywhere"; actual behavior depends on APIs, kernel, TLS, allocators, OS, scatter/gather I/O, and application transformations. Allocating and freeing direct buffers is expensive, so networking frameworks commonly use **pooling**.

### Distinguishing Allocation and Reclamation

- Heap `byte[]` follows reachability and GC.
- Java NIO direct buffers have native backing storage; reclamation is typically tied to cleaner/GC lifecycles, so do not rely on "GC will run immediately" to survive peak traffic.
- Netty pooled `ByteBuf` uses **reference counting**: you must release it when done. Pools may also keep reserved memory around for reuse after buffers return to the pool.
- Java NIO `-XX:MaxDirectMemorySize` cannot be treated as the sole quota for every native allocation made by a library like Netty; combine it with cgroup/RSS and allocator metrics.

Direct memory excels at network I/O, yet **using direct everywhere is not universally optimal**. Small arrays, JSON business objects, or data processed solely inside Java heap rarely benefit enough from direct allocations.

## 5. Netty `ByteBuf`, Heap, and Pooled Direct Buffers

Spring WebFlux on Reactor Netty typically passes data through Netty `ByteBuf`:

~~~text
NIC/TCP socket -> Netty ChannelPipeline -> ByteBuf
        |
        +--> Netty pooled allocator
        |       +--> heap ByteBuf
        |       +--> direct ByteBuf
        |
        +--> Spring NettyDataBuffer (DataBuffer abstraction)
        |
        +--> HTTP reader/codec / WebFlux handler
~~~

`ByteBuf` differs from `java.nio.ByteBuffer` in ownership semantics. Netty supports pooled/unpooled, direct/heap, composite buffers, separate reader/writer indexes, and reference counting.

### Reserved vs Active Allocator Memory

Reactor Netty exposes metrics:
- `reactor.netty.bytebuf.allocator.used.direct.memory`: bytes **reserved** by the direct allocator.
- `reactor.netty.bytebuf.allocator.active.direct.memory`: bytes **in use** per the pooled allocator.
- Similarly `used.heap.memory` and `active.heap.memory`.
- `direct.arenas`, `heap.arenas`, `threadlocal.caches`, and other pool metrics when available.

For example, after a load burst:
- Active direct memory drops low while **used/reserved** stays high: the pool is retaining chunks/arenas for reuse, **not proof of a leak**.
- Active direct memory **keeps rising after requests complete**, failing to settle after warm-up across repeated runs: suspect unreleased buffers or long-lived streams, while verifying actual active requests and metrics.
- Both active and used grow as connection concurrency rises: may simply be normal workload demand, not a leak.

**Do not compare `used.direct.memory` directly against `-XX:MaxDirectMemorySize`** to claim total native footprint; Netty native allocation mechanisms and Java NIO limits depend on the specific Netty and JDK versions.

## 6. Where Do HTTP Buffers Live?

An HTTP request body passes through multiple layers:

~~~text
Client sends bytes
    |
    v
[OS socket receive buffer]                  (kernel/network)
    |
    v
[Netty ByteBuf / servlet input buffer]      (transport)
    |
    v
[HTTP framing decoder]                      (headers/chunks/frames)
    |
    v
[Spring DataBuffer / InputStream]           (framework)
    |
    +--> [JSON decoder may aggregate input] (codec)
    +--> [Multipart parser: memory/disk]    (codec)
    +--> [Stream directly to sink/storage]  (application)
    |
    v
Controller / service
~~~

And the response in reverse:

~~~text
Business data / file / Publisher<T>
    |
    v
[Serializer / DataBufferFactory]        (HTTP encoder)
    |
    v
[Netty channel outbound buffer]        (I/O queue)
    |
    v
[OS socket send buffer]                (kernel)
    |
    v
Proxy / CDN / client receive buffer
~~~

A request does not live in **one** single buffer. HTTP/1.1 chunked transfer and HTTP/2 DATA frames are wire-framing mechanisms; they **do not** prevent an app from aggregating into a large JSON object. A client sending 100 HTTP chunks to a handler using `@RequestBody byte[]` still forces buffering the entire decoded body.

### TCP Socket Buffers Differ from Application Buffers

- Kernel `SO_RCVBUF`/`SO_SNDBUF` control TCP socket buffering; the OS applies autotuning and separate accounting.
- JVM/Netty inbound/outbound buffers live in user space.
- Codec buffers parse/aggregate payloads into logical objects.
- Reverse proxies maintain their own buffers in a **separate process**.

Hence raising or lowering `server.netty.initial-buffer-size` is not equivalent to "setting a max HTTP body size". In Boot 3.5, that property sets the **initial buffer size for decoding HTTP requests**, not a quota for multipart uploads or JSON object sizes.

## 7. How Spring MVC/Servlet vs WebFlux/Reactive Manage Buffers

| Aspect | Spring MVC + Servlet | Spring WebFlux + Reactor Netty |
|---|---|---|
| Common I/O model | Servlet blocking/async depending on endpoint | Reactive/non-blocking event loop |
| Common body APIs | `HttpServletRequest.getInputStream()`, `@RequestBody` | `Flux<DataBuffer>`, `Mono<DTO>` |
| Transport buffers | Tomcat/Jetty/Undertow implementation | Netty `ByteBuf`/direct allocator |
| JSON decode | `HttpMessageConverter` such as Jackson | `HttpMessageReader`/Decoder |
| Codec limits | Converter/Servlet/container/application limits | `maxInMemorySize` and codec-specific limits |
| Multipart | `MultipartFile`, servlet multipart/temp files | `FilePart`, `PartEvent`, disk spill per config |
| Large downloads | `StreamingResponseBody`, `Resource`/sendfile where applicable | `Flux<DataBuffer>`, `DataBufferUtils.read`, `Resource` |
| Backpressure | Servlet async/output/client flow control | Reactor demand + Netty channel backpressure |
| Buffer ownership | Usually abstracted under `InputStream`/response | Must watch `DataBufferUtils.release` when handling `DataBuffer` directly |
| Common issues | Held Servlet threads, large `byte[]` copies, async queues | Unbounded reactive queues, `DataBuffer` leaks, event-loop blocking |

**Never assume "MVC uses no direct memory":** Tomcat NIO/NIO2, Undertow, or TLS/native libraries still use native/direct buffers. Conversely, WebFlux still allocates many Java heap objects for JSON and business data. Framework choice never removes the need to control memory.

## 8. Spring's `DataBuffer`: Abstraction and Ownership

Spring Framework defines:
- `DataBufferFactory`: allocates or wraps byte buffers.
- `DataBuffer`: represents a byte region with read/write positions, potentially pooled.
- `PooledDataBuffer`: adds reference-counted ownership.
- `DataBufferUtils`: helpers for `join`, `read`, `write`, `retain`, `release`, and related utilities.

When using `@RequestBody Mono<MyDto>` or returning `Mono<MyDto>`, standard codecs normally manage buffer lifecycles automatically. Once you accept `Flux<DataBuffer>` directly or write a custom codec, **your application owns buffer management**.

### The Rule: "Who Consumes Releases?"

- If you **only read** an inbound `DataBuffer` to compute a checksum or byte count, you must release the buffer after reading (if pooled).
- If you **pass a `DataBuffer` downstream for the HTTP writer to consume**, **do not release it before the writer finishes reading**; the writer owns releasing transferred buffers.
- If you allocate a new `DataBuffer` and fail before handing off ownership (e.g., serialization error), release the buffer you still own.
- If you hold a buffer across an asynchronous boundary, `retain` when sharing/holding ownership and release correspondingly; prefer **bounded byte copying** when logic gets complex rather than holding pooled buffers long-term.
- When operators drop/discard buffers on filtering, cancellation, errors, or prefetch, attach `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` at the appropriate place.

### Reference Counting in Pooled Buffers

~~~text
Allocated pooled buffer: refCnt = 1
retain()                -> refCnt = 2
release()               -> refCnt = 1
release()               -> refCnt = 0 => eligible to return to pool
release() one more time -> BUG, may throw IllegalReferenceCountException
~~~

Refcount tracks **logical ownership**, not byte count directly. `DataBufferUtils.release(DataBuffer)` safely handles both pooled and non-pooled buffers (acting as a no-op on non-pooled buffers). However, that **does not make double-releasing safe** on a pooled buffer.

### Why Can Direct Buffers Leak?

A `NettyDataBuffer` can wrap a pooled `ByteBuf`. If application code reads data and forgets to release, `refCnt` stays >0 and the allocator cannot reuse that slice. JVM GC may collect the Java wrapper without fixing a missing refcount decrement when needed; Netty includes a leak detector to help catch these bugs.

**Never "fix" leaks by calling `System.gc()` in a request handler.** Fix ownership, bound concurrency, and inspect metrics first.

## 9. Recommended `DataBuffer` API in Spring 6.2

Spring's `DataBuffer.readableByteBuffers()` (since Spring 6.0.5) returns an iterator that must be **closed** via try-with-resources. You can update SHA-256 without copying the whole body:

~~~java
// Fragment in code that has MessageDigest sha and DataBuffer buffer.
try (DataBuffer.ByteBufferIterator views =
         buffer.readableByteBuffers()) {
    while (views.hasNext()) {
        sha.update(views.next());
    }
} finally {
    DataBufferUtils.release(buffer);
}
~~~

When working directly with codecs, compare `read(byte[])` vs `readableByteBuffers()`:
- `read(byte[])` copies bytes into a Java heap array—convenient, yet creates extra allocations.
- Iterating readable `ByteBuffer` views can avoid copies depending on the backing buffer.
- Never retain `ByteBuffer` views beyond the iteration block and **never** use them after releasing the `DataBuffer`.
- In Spring 6.2, several older `DataBuffer.asByteBuffer()`/`toByteBuffer()` overloads are deprecated; use the newer API per Javadoc to avoid views with unclear lifecycles.

### Never Use Unbounded `DataBufferUtils.join`

~~~java
// RISK: aggregates the entire body; without a bound,
// a client can force the app to hold hundreds of MiB.
Mono<DataBuffer> all = DataBufferUtils.join(incoming);
~~~

If business logic genuinely requires aggregation, set a bound:

~~~java
// Fragment: aggregate at most 1 MiB.
Mono<DataBuffer> bounded = DataBufferUtils.join(
    incoming, 1024 * 1024);
~~~

After receiving the combined `DataBuffer`, code that **consumes** it must release it:

~~~java
return bounded.map(buffer -> {
    try {
        return buffer.readableByteCount();
    } finally {
        DataBufferUtils.release(buffer);
    }
});
~~~

`DataBufferUtils.join(..., maxByteCount)` throws `DataBufferLimitException` when the bound is exceeded. `join` may use composite buffers/zero-copy depending on the backing allocator, yet still retains all chunk data until completion. "Zero-copy" in one operation does not mean near-zero memory footprint.

## 10. WebFlux Codec Aggregation Limit: 256 KiB Default in Many Codecs

Per Spring WebFlux documentation, many codecs default to buffering around **256 KiB** when they must **aggregate** input into one object. Exceeding it can raise:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

In **Spring Boot 3.5**, the documented property is:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
~~~

This property:
- Applies to **auto-configured WebFlux servers** and **auto-configured `WebClient` instances** within Boot's documented scope.
- Governs **the memory limit when a stream must be aggregated**; it is not a process-wide memory quota.
- Does not automatically cap total bytes flowing through a streaming endpoint using `Flux<DataBuffer>`.
- Does not equal max upload limits enforced by reverse proxies, containers, or security gateways.
- Does not necessarily apply to manually built `WebClient.builder()`/clients outside Boot customization.

If your app needs to receive 1 MiB JSON payloads, you might raise it to **2 MiB** after calculating worst-case concurrency, but **never set 100 MiB just to silence an error**. Ask why the endpoint aggregates instead of streaming or using file-based processing.

### Customizing Directly via `WebFluxConfigurer`

If you do not want Boot's global codec property or need framework-level control:

~~~java
// Fragment inside a @Configuration class implementing WebFluxConfigurer.
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs()
              .maxInMemorySize(512 * 1024);
}
~~~

Imports:
- `org.springframework.web.reactive.config.WebFluxConfigurer`
- `org.springframework.http.codec.ServerCodecConfigurer`

Do not add `@EnableWebFlux` merely to tweak codec limits in a Boot WebFlux app; it disables many Spring Boot auto-configurations.

### `WebClient` Has an Independent Client-Side Limit

~~~java
// Fragment when building a WebClient directly.
WebClient client = WebClient.builder()
    .codecs(c -> c.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

If a client uses `retrieve().bodyToMono(String.class)` or `bodyToMono(byte[].class)` on a large response, the codec must aggregate and can hit `DataBufferLimitException`. Raising the client limit does not raise the server limit and vice versa. Prefer `bodyToFlux(DataBuffer.class)` with proper consume/release for large or streaming responses.

### The Limit Is Per Aggregation, Not a Global Concurrency Cap

Suppose 500 concurrent requests each decode nearly 2 MiB of JSON:

~~~text
500 x 2 MiB = 1,000 MiB (~0.98 GiB) theoretical body bytes
~~~

And that excludes decoded Java objects, Netty buffers, TLS, serialization, threads, caches, queues, and GC. `maxInMemorySize=2MB` does **not** cap total concurrent memory at 2 MiB; it limits each individual decoder/object aggregation per its mechanism.

## 11. HTTP Request Body Size, Header Size, and Multipart Are Separate Limits

Do not confuse these limits:

| Mechanism | What It Protects | Example |
|---|---|---|
| `spring.http.codecs.max-in-memory-size` | Data codecs must buffer during aggregation | JSON/String/`byte[]` decoding |
| `spring.webflux.multipart.max-in-memory-size` | In-memory threshold per multipart part (file parts can spill to disk) | Form uploads |
| `spring.webflux.multipart.max-disk-usage-per-part` | Max disk space for a single spooled part | Oversized file part |
| `spring.webflux.multipart.max-parts` | Number of parts per multipart request | Multipart DoS |
| `server.max-http-request-header-size` | HTTP header size per embedded server semantics | Too many cookies/headers |
| `server.netty.initial-buffer-size` | Initial HTTP request decoding buffer | Not a body maximum |
| Reverse proxy `client_max_body_size` (NGINX) | HTTP request body accepted at edge | Edge returns 413 before JVM |
| Application stream byte counting | Total size of a streamed request | Large multipart/raw binary |

In Boot 3.5, WebFlux multipart properties live under `spring.webflux.multipart.*` per Common Application Properties. File parts can spill to **temporary disk** above the in-memory threshold, unlike non-file parts. Bound disk space/quotas, part counts, temp directory permissions, and cleanup.

**Spring MVC/Servlet** uses its own namespace: `spring.servlet.multipart.max-file-size`, `spring.servlet.multipart.max-request-size`, `spring.servlet.multipart.file-size-threshold`. Never use MVC properties expecting to "fix" a WebFlux/Netty app.

### HTTP 413 and `DataBufferLimitException`

HTTP `413 Content Too Large`/`Payload Too Large` signals the server rejected the body due to size. Yet `DataBufferLimitException` from a codec is not guaranteed to automatically become HTTP 413 in every version and handler chain. For stable API contracts, add explicit exception mapping and tests, **and** enforce limits at proxy/server/codec layers as appropriate.

When a request exceeds a limit, the server may respond before the client finishes sending the body, close the connection, or drain according to policy. Never take a single `curl` status code as proof that the entire body was buffered onto the heap.

## 12. HTTP Response Buffers and Backpressure

Inbound reading is only half the story: **outbound writing** also holds buffers. When returning a 100 MiB binary response, there are two ways:

**Aggregate everything first:**

~~~java
// Anti-pattern for large files: loads entire contents into heap.
byte[] bytes = Files.readAllBytes(path);
return ResponseEntity.ok(bytes);
~~~

This is a Java fragment (`path`/imports/handler omitted). It allocates a 100 MiB `byte[]` on the heap, then serialization/transport needs additional buffers and copies.

**Stream in chunks:**

~~~java
// WebFlux fragment once you have a Flux<DataBuffer> body.
return response.writeWith(body);
~~~

Uses a publisher emitting chunks on demand, bounding prefetch/queues and transferring buffer ownership to the HTTP response writer. The whole file never needs to sit on the heap at once.

### Backpressure Does Not Mean "Automatically OOM-Proof"

Reactive Streams provides `request(n)` and `cancel`; when subscribers/HTTP transports slow down, upstream **can** slow emission if the source honors demand. Still, memory can blow up due to:
- Unbounded `onBackpressureBuffer()`.
- `collectList()` over an entire stream.
- High `flatMap` concurrency/prefetch.
- Hot publishers emitting faster than clients consume.
- Message broker/application queues lacking backpressure.
- HTTP/2 multiplexing: many open streams on one connection.
- Separate buffering in compression, TLS, and serialization.
- Growing Netty channel outbound queues when producers ignore writability/demand.

For downloads/streaming, control **bytes retained per connection**, concurrent clients, output queues, and slow-client timeouts. Even a small buffer per connection adds up quickly across 50,000 slow connections.

### HTTP/1.1 Chunked and HTTP/2 Frames

- HTTP/1.1 can use `Transfer-Encoding: chunked` when `Content-Length` is unknown.
- HTTP/2 sends DATA frames and does not use HTTP/1.1 chunked transfer coding.
- One TCP packet or HTTP chunk/frame size **does not guarantee** each `DataBuffer` delivered to your controller has that exact size.
- Proxies can buffer or re-chunk bytes; never build business parsers assuming TCP read or chunk boundaries align with messages. Streams are continuous bytes; use explicit framing such as NDJSON, length prefixes, or multipart protocols when needed.

## 13. Runnable Demo: WebFlux Streaming Upload, Chunked Download, and Memory Snapshot

The demo provides four endpoints:
- `GET /api/stream?chunks=4`: emits **4 chunks × 4096 bytes**, streaming binary via `Flux<DataBuffer>` without allocating a 16 KiB combined array.
- `POST /api/digest`: accepts raw `application/octet-stream` as `Flux<DataBuffer>`, updates **SHA-256 per buffer**, releases each buffer after processing, and enforces an 8 MiB total cap.
- `POST /api/json`: accepts a regular JSON DTO via codec aggregation to contrast with streaming.
- `GET /api/memory`: reads `MemoryMXBean` and Java NIO `BufferPoolMXBean`, **without** pretending NIO direct bytes equal all Netty direct memory.

Uses only **Spring Reactive Web + Actuator**; add the Prometheus registry if scraping is desired.

### 13.1. Project Initialization

Create a Spring Initializr project:
- Java **17+**, Spring Boot **3.5.x**, Gradle, dependencies **Spring Reactive Web (WebFlux)** and **Spring Boot Actuator**.
- Do not add `spring-boot-starter-web` to the reactive demo (when both `web` and `webflux` starters are present, Boot typically selects the Servlet stack).

In the Initializr-generated Gradle project, dependencies should match:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **dependency fragment**, not a complete `build.gradle`. Boot dependency management selects compatible versions. Subsequent source files use package `demo.buffers`.

### 13.2. `application.yml`

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  http:
    codecs:
      max-in-memory-size: 256KB

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

Explanation:
- `max-in-memory-size: 256KB`: tests codec aggregation limits, not a hard cap on all HTTP uploads.
- The demo explicitly caps `/api/digest` at 8 MiB in the controller because it reads a stream rather than relying on the 256 KB codec limit.
- Actuator `metrics`/`prometheus` are for **local runs only**. In production, secure them via private network/auth/mTLS as appropriate; never open diagnostics to the public Internet.

### 13.3. Complete Java File

Create `src/main/java/demo/buffers/BufferRuntimeApplication.java`:

~~~java
package demo.buffers;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class BufferRuntimeApplication {

    private static final int CHUNK_SIZE = 4096;
    private static final int MAX_CHUNKS = 1024;
    private static final long MAX_UPLOAD_BYTES = 8L * 1024 * 1024;

    public static void main(String[] args) {
        SpringApplication.run(BufferRuntimeApplication.class, args);
    }

    public record DigestResult(long bytes, String sha256) { }
    public record JsonRequest(String text) { }
    public record JsonResult(int textLength) { }

    @GetMapping(
        path = "/api/stream",
        produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    public Flux<DataBuffer> stream(
            @RequestParam(defaultValue = "4") int chunks,
            ServerHttpResponse response) {

        if (chunks < 1 || chunks > MAX_CHUNKS) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "chunks must be between 1 and 1024"
            );
        }

        // Flux.range emits on demand; map allocates ONE block
        // when downstream requests it, instead of buffering the whole file.
        return Flux.range(0, chunks)
            .map(i -> {
                byte[] block = new byte[CHUNK_SIZE];
                Arrays.fill(block, (byte) 'A');
                return response.bufferFactory().wrap(block);
            })
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
    }

    @PostMapping(
        path = "/api/digest",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<DigestResult> digest(
            @RequestBody Flux<DataBuffer> body) {

        return Mono.defer(() -> {
            MessageDigest sha;
            try {
                sha = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException ex) {
                return Mono.error(new IllegalStateException(ex));
            }

            AtomicLong total = new AtomicLong();

            return body
                .doOnDiscard(
                    DataBuffer.class, DataBufferUtils::release)
                .handle((buffer, sink) -> {
                    try {
                        long count = total.addAndGet(
                            buffer.readableByteCount());

                        if (count > MAX_UPLOAD_BYTES) {
                            sink.error(new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Upload exceeds 8 MiB"
                            ));
                            return;
                        }

                        // Close iterator, then release the consumed buffer.
                        try (DataBuffer.ByteBufferIterator views =
                                 buffer.readableByteBuffers()) {
                            while (views.hasNext()) {
                                ByteBuffer view = views.next();
                                sha.update(view);
                            }
                        }
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .then(Mono.fromSupplier(() ->
                    new DigestResult(
                        total.get(),
                        HexFormat.of().formatHex(sha.digest())
                    )
                ));
        });
    }

    @PostMapping(
        path = "/api/json",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<JsonResult> json(
            @RequestBody Mono<JsonRequest> incoming) {
        return incoming.map(request ->
            new JsonResult(request.text().length())
        );
    }

    @GetMapping("/api/memory")
    public Map<String, Long> memory() {
        long heapUsed = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        long heapMax = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getMax();

        long nioDirectBytes = ManagementFactory.getPlatformMXBeans(
                    BufferPoolMXBean.class)
                .stream()
                .filter(pool -> "direct".equals(pool.getName()))
                .mapToLong(BufferPoolMXBean::getMemoryUsed)
                .filter(bytes -> bytes >= 0)
                .sum();

        return Map.of(
            "heapUsedBytes", heapUsed,
            "heapMaxBytes", heapMax,
            "nioDirectUsedBytes", nioDirectBytes
        );
    }
}
~~~

**Code structure QA:**
- Single top-level `public class BufferRuntimeApplication` with implicitly static nested records.
- `MessageDigest` is created **per subscription** via `Mono.defer(...)`, never using a mutable singleton hash shared across requests.
- The upload `Flux<DataBuffer>` is consumed buffer by buffer, iterator views are closed, and `DataBufferUtils.release(buffer)` always runs in `finally`.
- Exceeding 8 MiB emits `ResponseStatusException(413)`, releases the current buffer, and terminates the subscription; discarded/buffered items are handled by `doOnDiscard`.
- Download `Flux.range` + `map` does not pre-allocate all buffers before subscription. Buffers are **handed to Spring's HTTP writer**; the controller does not prematurely release transferred buffers.
- `/api/memory` only reads metrics; it does not retain body bytes or allocate huge direct buffers itself.
- The JSON endpoint uses `Mono<JsonRequest>` so the framework decoder manages buffers, contrasting with the raw streaming handler.

**Demo limitation:** each chunk allocates a `byte[4096]`, so chunk-level Java heap allocations and Netty transport copies still occur. "Streaming" here means **not holding the entire 4 MiB response in memory at once**, not zero heap or zero native allocations. If a network/client is slow, the transport may still hold pending buffers until flushed.

### 13.4. Running the Application

From the project root with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The app listens on `http://localhost:8080` if the port is free. Because this demo has no authentication, run it only in a local learning environment and never send sensitive data.

## 14. Testing Streaming Upload with SHA-256

Send the 5 ASCII bytes `hello`:

~~~bash
curl -sS -i \
  -X POST \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'hello' \
  http://localhost:8080/api/digest
~~~

Expected HTTP status **200 OK**, response body **exact in field values**:

~~~json
{
  "bytes": 5,
  "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
}
~~~

JSON key ordering is not guaranteed, whereas the SHA-256 of UTF-8 `hello` is fixed as shown. `bytes=5` because there are 5 ASCII bytes. With multi-byte UTF-8 strings, byte count differs from character count.

### Uploads >256 KiB Still Pass Through the Streaming Endpoint

Because `/api/digest` consumes `Flux<DataBuffer>` chunk by chunk, the 256 KB codec aggregation limit **does not cut off** a 512 KiB payload when no reader is aggregating; the application's 8 MiB cap still applies.

Generate test payload with standard Python locally:

~~~bash
python -c "open('payload.bin','wb').write(b'x' * (512 * 1024))"
~~~

Then send:

~~~bash
curl -sS -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @payload.bin \
  http://localhost:8080/api/digest
~~~

The JSON body will show `"bytes":524288` and the `sha256` of `x` repeated 524,288 times (not hardcoded here without running it). Above **8 MiB**, the controller returns **413**; depending on transport timing, the client may see rejection before finishing transmission.

**Never** generate multi-GiB payloads on production hosts; perform memory stress experiments only in isolated environments with quotas and timeouts.

## 15. Testing Streaming Download with Exact Byte Count

Generate 4 chunks:

~~~bash
curl -sS \
  "http://localhost:8080/api/stream?chunks=4" \
  -o stream.bin
~~~

The file contains exactly:

~~~text
4 chunks × 4096 bytes/chunk = 16384 bytes
~~~

Bash/Linux/macOS:

~~~bash
wc -c < stream.bin
~~~

Expected stdout:

~~~text
16384
~~~

PowerShell:

~~~powershell
(Get-Item .\stream.bin).Length
~~~

Expected stdout:

~~~text
16384
~~~

Use `chunks=1024` for the max **4 MiB** response (1024 × 4096 = 4,194,304 bytes), yet the endpoint **never constructs a single 4 MiB array**. With `chunks=0` or `chunks=1025`, the server returns **400 Bad Request** per demo validation.

**Why is the size exact?** The controller builds each chunk as a 4,096-byte array and emits exactly `chunks` chunks. Wire bytes may include framing overhead (HTTP/1.1 chunked or HTTP/2 frames), but `curl -o stream.bin` writes only the **entity body**, so file size matches on complete transfer.

## 16. Testing JSON Aggregation vs Raw Stream

Small request:

~~~bash
curl -sS -i \
  -H 'Content-Type: application/json' \
  --data-binary '{"text":"hi"}' \
  http://localhost:8080/api/json
~~~

Status **200**, body:

~~~json
{"textLength":2}
~~~

Create JSON exceeding 256 KiB:

~~~bash
python -c "import json; open('large.json','w',encoding='utf-8').write(json.dumps({'text':'x' * 400000}))"
~~~

Send:

~~~bash
curl -sS -i \
  -H 'Content-Type: application/json' \
  --data-binary @large.json \
  http://localhost:8080/api/json
~~~

Spring WebFlux's decoder can emit `DataBufferLimitException` when exceeding the configured aggregation bound. **The final HTTP status/body depends on exception handling and version.** If your production API contract requires HTTP 413, add explicit exception mapping and test it rather than assuming every `DataBufferLimitException` defaults to 413.

### Intentionally Mapping Codec Limits to 413

Spring WebFlux fragment:

~~~java
@RestControllerAdvice
class CodecLimitAdvice {

    @ExceptionHandler(DataBufferLimitException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            DataBufferLimitException ignored) {
        return ResponseEntity
            .status(HttpStatus.PAYLOAD_TOO_LARGE)
            .body(Map.of("error", "CODEC_LIMIT"));
    }
}
~~~

Imports:
- `org.springframework.web.bind.annotation.RestControllerAdvice`
- `org.springframework.web.bind.annotation.ExceptionHandler`
- `org.springframework.core.io.buffer.DataBufferLimitException`
- `org.springframework.http.ResponseEntity`
- `org.springframework.http.HttpStatus`
- `java.util.Map`

This is an **illustrative fragment**, not included in the main runnable file. A decoder error can be wrapped in another exception type or intercepted elsewhere, so production policies must be tested against your actual WebFlux version and CORS/Security/error-handler chain. The goal is returning a clear size error **without disabling `maxInMemorySize`**.

### Do Not Confuse Memory Limits with Business Upload Limits

- `/api/json` uses the JSON decoder: the memory aggregation limit applies when the codec buffers.
- `/api/digest` streams raw bytes: enforces `MAX_UPLOAD_BYTES` directly without buffering the whole body.
- Reverse proxies or firewalls may reject requests even earlier, e.g., `client_max_body_size`.
- Multipart uploads have their own parser thresholds/limits and temp disk logic.

Each path should have **out-of-bounds integration tests** from external clients, not just controller unit tests.

## 17. `WebClient`: `bodyToMono(byte[])` vs `bodyToFlux(DataBuffer.class)`

`WebClient` is a reactive HTTP client usable in either MVC or WebFlux. For large responses, choosing the right representation matters greatly.

### Anti-Pattern: Buffering the Whole Response as `byte[]`

~~~java
// Fragment; WebClient already configured with baseUrl.
Mono<byte[]> bytes = webClient.get()
    .uri("/big-file")
    .retrieve()
    .bodyToMono(byte[].class);
~~~

This forces **aggregating** the body into a byte array, triggers codec memory limits, and causes a large heap allocation. If a server returns 100 MiB, raising `maxInMemorySize` to 200 MiB does not make concurrent requests safe.

### Streaming and Releasing When Consuming Directly

~~~java
// Fragment: use inside a service with a configured WebClient.
AtomicLong total = new AtomicLong();

Mono<Long> downloadedBytes = webClient.get()
    .uri("/big-file")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .doOnNext(buffer -> {
        try {
            total.addAndGet(buffer.readableByteCount());
        } finally {
            DataBufferUtils.release(buffer);
        }
    })
    .then(Mono.fromSupplier(total::get));
~~~

**This fragment assumes a single subscription at a time.** In production, allocate `AtomicLong` **per subscription** (e.g., wrap the pipeline in `Mono.defer(...)`), never share a singleton `AtomicLong` across requests. To save to a file, use `DataBufferUtils.write(...)` with proper post-write release rather than merely counting and discarding bytes.

**Note on response body handling:** when using `exchangeToMono/Flux`, ensure the body is consumed or released across all status branches so pooled response buffers never leak. `retrieve()` and framework codecs handle many error paths, yet custom exchange/filter logic must still verify ownership.

### Avoid Buffering Everything in Operators

Anti-pattern:

~~~java
// RISK: memory scales with the entire response.
return webClient.get()
    .uri("/big-file")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .collectList();
~~~

`collectList()` holds **all buffer references** until the response completes, inflating direct memory and causing leaks if callers forget to release. Similarly, avoid unbounded `onBackpressureBuffer()` before a slow file sink.

## 18. Slow Consumers, Backpressure, and Outbound Queues

Suppose Spring Boot streams data to a client over a slow link:

~~~text
Producer: 50 MiB/s
Network to client: 0.5 MiB/s
Difference: ~49.5 MiB/s must be throttled, dropped, or buffered somewhere
~~~

If the app keeps generating bytes without backpressure, memory queues grow by hundreds of MiB every few seconds. Uploads face the mirror problem if the client sends fast while downstream file/database writes lag.

**Backpressure** signals upstream demand bounds:
- `Flux.range(...)` honors requested counts, making it suitable for chunk-by-chunk generation.
- A hot source or custom publisher **ignoring demand** can outpace consumers and bloat queues.
- `flatMap(..., concurrency)` prefetches and buffers internally; cap concurrency when downstreams are slow.
- `publishOn` uses scheduler queues; do not hop schedulers blindly without measuring.
- `onBackpressureBuffer(max, ...)` enforces an explicit cap; pick drop/error policies matching business rules.
- Reactor Netty channel writability, HTTP/2 flow-control windows, TCP send buffers, and remote read rates all affect **send rate** without replacing application queue design.

For SSE/WebSockets with slow clients, bound the **outbound queue per session**, choose an overflow policy (disconnect slow consumers, coalesce latest values, persist event IDs), and support reconnect/replay per business needs. Never silently drop financial/audit events.

## 19. Budgeting Memory by Concurrency Rather Than Payload Size Alone

A rough budgeting model:

~~~text
Memory used by HTTP workload ≈
  in-flight request count × average retained input buffers
+ active response streams × retained output buffers
+ codec object graph / compression / TLS buffers
+ connection/session state + queues/caches
+ non-HTTP JVM/runtime memory
~~~

Example **strictly for budgeting**:
- 400 concurrent requests.
- Each request retains an average of 256 KiB of aggregating data.
- Raw body bytes alone already reach ~**100 MiB** concurrently.
- If decoded JSON object graphs add 2–4× input size plus transport buffers, actual pressure is far higher.

~~~text
400 × 256 KiB = 102400 KiB = 100 MiB
~~~

This is not an exact formula for heap/direct usage, since requests vary in lifecycle, allocations, and sharing. The point is seeing that **per-request limits do not cap total concurrency**.

### Additional Protective Boundaries

1. Cap concurrent requests/streams per instance.
2. Cap request body sizes at edge, gateway, and application.
3. Cap codec aggregation / per-item sizes.
4. Cap multipart part counts and disk usage.
5. Cap output queues/buffers per client.
6. Apply timeouts/slow-client protection so resources stay bounded.
7. Avoid unbounded caches or `collectList`.
8. Reserve headroom for JVM native/direct/TLS/thread stacks and monitoring.
9. Test traffic spikes, slow uploads/downloads, client cancellations, and repeated runs.
10. Measure **RSS/cgroup + heap + allocator active/used + GC + buffer pools** together.

**Never push `-Xmx` and direct limits right up against the cgroup limit.** Balance real process memory, QoS, GC pauses, and margin against the cgroup OOM killer.

## 20. Observing Heap and Native/Direct Memory with Actuator

With `spring-boot-starter-actuator`, Spring Boot + Micrometer exposes JVM metrics when a supporting registry is active:

~~~bash
curl -sS http://localhost:8080/actuator/metrics
~~~

Look for names such as:
- `jvm.memory.used` / `jvm.memory.max` (heap/nonheap via tags).
- `jvm.gc.pause` and allocation/GC metrics per runtime.
- `jvm.buffer.memory.used` / `jvm.buffer.count` / `jvm.buffer.total.capacity` for Java buffer pools.
- `process.cpu.usage`, `process.files.open` where platform-supported.
- Reactor Netty metrics if corresponding instrumentation is enabled.

Drill-down example:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/jvm.buffer.memory.used"
~~~

`jvm.buffer.memory.used` generally comes from Java `BufferPoolMXBean` (direct/mapped), which **does not necessarily include all native Netty allocations**. Never use this single metric to rule out native memory pressure.

### Prometheus Exposition

~~~bash
curl -sS http://localhost:8080/actuator/prometheus
~~~

Prometheus normalizes names to underscores with unit suffixes, e.g., `jvm_buffer_memory_used_bytes`. **Never assume every meter is present** before configuring instrumentation or across version upgrades; inspect actual runtime names.

Reactor Netty allocator metrics can include:
- `reactor.netty.bytebuf.allocator.used.direct.memory`
- `reactor.netty.bytebuf.allocator.active.direct.memory`
- `reactor.netty.bytebuf.allocator.used.heap.memory`
- `reactor.netty.bytebuf.allocator.active.heap.memory`
- `reactor.netty.eventloop.pending.tasks`

These depend on metrics/allocator instrumentation and Netty version. If `reactor.netty.*` is absent, **do not conclude no Netty direct buffers are used**; verify Reactor Netty metrics enablement and data sources.

### Reading Alongside Process/Container Memory

| Metric | When Rising | Preliminary Meaning |
|---|---|---|
| JVM heap used | DTO/JSON/caches/byte arrays | Rising heap allocations or retained objects |
| JVM GC pause | Frequent GC collections | Allocation rate, heap sizing, or retention pressure |
| NIO direct buffer memory | Tracked Java direct buffers | NIO direct buffer usage |
| Netty active direct | Buffers currently in use | Active request flow or potential refcount leak |
| Netty used/reserved direct | Pool reservation | May stay elevated after warm-up without leaking |
| Process RSS | Total resident physical memory | Includes heap, native, mmap, thread stacks |
| Container memory.current / working set | cgroup memory accounting | Risk of hitting limit / OOMKill |
| HTTP in-flight / connections | Load concurrency | Compare against per-connection buffers |
| Network bytes / latency | Throughput / slow clients | Diagnose queueing and backpressure |

**Never declare a leak from one snapshot.** Run repeated load batches, wait for requests to finish, check whether active memory returns to baseline, and compare post-GC heap and Netty active/reserved alongside concurrency.

## 21. Java Diagnostic Tools: `jcmd`, NMT, and Heap Dumps

### 21.1. Inspecting JVM Flags and Heap

In test environments with JDK tools and attach permissions:

~~~bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
~~~

`<PID>` is a process ID placeholder—substitute the actual PID without angle brackets. `jcmd` may be restricted by container isolation, attach permissions, missing JDK tools, or security policies.

### 21.2. Native Memory Tracking (NMT)

Enable at JVM startup to inspect JVM native memory categories:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -XX:MaxDirectMemorySize=256m \
  -Xmx512m -jar app.jar
~~~

These are **example JVM flags**, not mandatory budgets for every container. Once NMT is enabled, run:

~~~bash
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff
~~~

In Windows PowerShell, run one command per line with the real PID; backslashes in shell examples above are Bash line continuations, not Java syntax. NMT must generally be enabled **at JVM startup** and adds slight overhead; `summary` is less detailed than `detail`.

**NMT limitation:** it tracks JVM native allocations from supported subsystems; not all native memory allocated by external libraries is fully reported. Cross-check with `RSS`, `/proc/<pid>/smaps`, Netty allocator metrics, cgroup memory, and native profilers as needed.

### 21.3. Heap Dump / Java Flight Recorder

When suspecting a heap leak:
- `jcmd <PID> GC.heap_dump /path/heap.hprof` writes a heap dump (can be **huge**, impact performance, and contain sensitive data).
- Java Flight Recorder (JFR) captures allocation hotspots, GC, thread blocking, and event timelines with configurable overhead.
- MAT/YourKit/JProfiler analyze retained size, dominator trees, and paths to GC roots.

**A heap dump does not capture all native bytes**; a Java Netty `ByteBuf` wrapper looks tiny in a heap dump even when backing megabytes of direct memory. Thus when OOMKilled with low post-GC heap, inspect native and process accounting before staring solely at heap dumps.

## 22. Netty Leak Detection: Enable Controlled Checks in Tests

Netty offers `ResourceLeakDetector` to flag unreleased `ByteBuf` instances. Levels like `SIMPLE`, `ADVANCED`, and `PARANOID` trade off CPU and logging overhead.

Example **JVM system property in test environments**:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Do not enable `paranoid` across all production traffic; overhead can be severe. Reactor Netty also logs under `_reactor.netty.channel.LeakDetection` to help trace ownership. Check your exact Netty/Reactor Netty docs and avoid blaming the wrong component from a single log line.

### Symptom Pattern and Investigation

~~~text
Steady HTTP traffic
    |
    +-- Netty active direct rising
    +-- Completed requests return to baseline
    +-- JVM heap stable or slightly rising
    +-- RSS/cgroup steadily climbing
           |
           v
    Suspect unreleased pooled buffers, outbound queues, or native allocations
~~~

High `used.direct.memory` alone is not a leak; the allocator caches arenas/chunks for reuse. Nor does running GC reclaim all leaked pooled `ByteBuf` instances. Audit active buffers, subscribers, cancellation paths, and refcount lifecycles.

## 23. Memory Pressure from Compression, TLS, and Multipart

### HTTP Compression

When the server gzips/deflates responses, compressor state and buffers add overhead. If the app serializes JSON into one large `String` and then compresses it, heap and native allocations overlap. Compression cuts wire bytes at the expense of CPU and peak memory; load-test with realistic response sizes, concurrency, and content types.

### TLS

TLS libraries maintain network/application buffers, handshake state, and certificate/session caches. HTTPS does not automatically require two full copies of every request body, yet it adds native and heap overhead. When TLS terminates at a load balancer, the JVM sees plaintext HTTP upstream while the edge proxy incurs its own memory cost.

### Multipart

A 100 MiB multipart upload can be:
- Rejected at the gateway before hitting the backend.
- Spooled to temporary disk by the multipart parser rather than held in memory.
- Streamed to storage by the handler via `FilePart.transferTo(path)`.
- Or unnecessarily loaded into 100 MiB of RAM via `DataBufferUtils.join`.

In Spring WebFlux, `spring.webflux.multipart.max-in-memory-size` controls the per-part in-memory threshold, `max-disk-usage-per-part` caps per-part disk usage, and `max-parts` limits part count. Spring MVC uses `spring.servlet.multipart.*` with its own semantics and settings.

**Security:** cap file sizes and part counts, sanitize filenames, never trust user-supplied `Content-Type` or extensions, inspect content, scan for malware when required, block path traversal, and enforce temporary disk quotas and permissions. An upload DoS can exhaust **disk** just as easily as heap or direct memory.

## 24. Design Mistakes Leading to Memory Leaks or OOM

| Anti-Pattern | Risk | Replacement |
|---|---|---|
| `@RequestBody byte[]` for 2 GiB uploads | Forces full aggregation; exhausts heap | Stream `Flux<DataBuffer>` + size cap and storage sink |
| `bodyToMono(String.class)` for huge responses | Codec limit / OOM | Bounded streaming, file sink, or chunk processing |
| `collectList()` on millions of `DataBuffer`s | Retains all references and direct memory | Process per chunk, release, and bound queues |
| Unbounded `DataBufferUtils.join(...)` | Memory grows linearly with body | `join` with `maxByteCount` or stream |
| Reading a `DataBuffer` and forgetting to release | Pooled refcount leak | `try/finally` with `DataBufferUtils.release` |
| Releasing before HTTP writer sends it | Use-after-release / `ReferenceCount` errors | Transfer ownership cleanly; writer releases |
| Releasing a pooled buffer twice | `IllegalReferenceCountException` | Clear ownership; release exactly once |
| Caching Netty `ByteBuf` long-term | Retains native memory, brittle lifecycle | Copy bounded data or deserialize object, then release |
| Unbounded `onBackpressureBuffer()` | RAM explodes under slow consumers | Bounded policy with discard/replay semantics |
| High `flatMap` concurrency | Too many concurrent buffers/requests | Bound concurrency and prefetch |
| Raising codec cap to 100 MB for one file | Every request can claim huge memory | Switch API to streaming or file-based transfer |
| Checking only `-Xmx` on container OOMKill | Ignores native/direct/thread stacks | Inspect RSS/cgroup + NMT + allocator gauges |
| Using Java heap dumps for all native bytes | Misses off-heap allocations | Use Netty meters/NMT/native memory tools |
| Setting `-Xmx` near container memory limit | No headroom for native/direct | Budget heap, direct, metaspace, stacks, TLS |
| Leaving Netty paranoid leak detection on everywhere | High CPU and log overhead | Enable in controlled tests/canaries |
| Not canceling subscriptions on client disconnect | Buffers/queues stay retained | Use `onCancel`/`doFinally`, release, and clean up |
| Breaking backpressure with custom hot publishers | Memory grows with producer speed | Bounded queues, rate control, drop/replay policies |

## 25. Investigation Workflow for OOM or Rising GC Latency

1. **Identify the error type and source:** JVM heap OOM, direct-buffer memory OOM, Netty native OOM, container OOMKill, or HTTP 413/500? Each points to a different subsystem.
2. **Inventory memory budgets:** `-Xmx`, `-Xms`, `MaxDirectMemorySize`, cgroup limit, JVM version, OS, and server stack.
3. **Record throughput and concurrency:** requests/sec, active HTTP streams, file uploads, SSE/WS clients, downstream latency.
4. **Compare post-GC heap used** with `RSS` and container memory. Low heap + high RSS points toward native memory.
5. **If WebFlux/Netty:** inspect Netty allocator active/used direct/heap gauges, connection queues, and event-loop pending tasks.
6. **If MVC/Tomcat:** inspect worker threads, connector buffers, in-flight requests, async tasks, and multipart/temp disk.
7. **Find peak-causing endpoints/operations:** JSON aggregation, Base64, `collectList`, multipart, streaming downloads, compression/TLS.
8. **Audit cancellation/error paths:** are buffers released on exceptions, timeouts, and client disconnects?
9. **Enable targeted test profiling:** NMT, JFR, heap dumps, Netty leak detection within safe scope.
10. **Reproduce under load tests:** match concurrency, payload sizes, slow-client behavior, restarts, GC, and warm-up. Compare metrics before/after fixes.
11. **Fix the root cause first:** bound codecs, stream instead of aggregating, release buffers, cap queues, reduce concurrency, plug leaks.
12. **Tune limits only afterward:** adjust `-Xmx`/direct/container quotas based on measured headroom, rolling out with canaries and alerts.

### Distinguishing 4 Common Failure Modes

| Primary Symptom | Likely Cause | Where to Look First |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap live set or allocation rate too high | Heap dump, GC, DTOs/caches/JSON aggregation |
| `Cannot reserve ... direct buffer memory` | Java NIO direct cap/usage exhausted | Direct `BufferPoolMXBean`, JVM flags, Netty/native metrics |
| Netty `OutOfDirectMemoryError` or leak warning | Netty allocator/refcount/cgroup | Active/used Netty memory, buffer ownership |
| Pod OOMKilled without Java OOME | Total cgroup memory exceeded limit | RSS/cgroup, NMT, heap + native breakdown |
| `DataBufferLimitException` | Codec aggregation exceeded `maxInMemorySize` | Decode mode and codec limits, status mapping |
| HTTP `413` from NGINX/WAF before backend | Edge body-size policy | Edge logs/config, do not touch JVM heap yet |

An HTTP 413 response is **not** a JVM OOM—it is often a protective limit working as intended. Never "fix" a 413 by raising server memory everywhere when the endpoint should stream and enforce explicit limits.

## 26. Automated Testing and Load Testing

### 26.1. Integration Tests with `WebTestClient`

In the demo project with `spring-boot-starter-test`, create `src/test/java/demo/buffers/BufferRuntimeApplicationTests.java`:

~~~java
package demo.buffers;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BufferRuntimeApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void digestUsesBoundedStreaming() {
        client.post()
            .uri("/api/digest")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue("hello".getBytes(StandardCharsets.UTF_8))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.bytes").isEqualTo(5)
            .jsonPath("$.sha256").isEqualTo(
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
            );
    }

    @Test
    void streamingOutputHasCorrectByteCount() {
        client.get()
            .uri("/api/stream?chunks=4")
            .exchange()
            .expectStatus().isOk()
            .expectBody(byte[].class)
            .consumeWith(result ->
                assertEquals(16384, result.getResponseBody().length)
            );
    }

    @Test
    void jsonSmallPayloadIsDecoded() {
        client.post()
            .uri("/api/json")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "hi"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.textLength").isEqualTo(2);
    }
}
~~~

**Add missing import to compile:** add `import java.util.Map;` before the class declaration in the test file. It was omitted above for readability, so **include it when copying into real source**. No extra library beyond `spring-boot-starter-test` is required when dependencies match.

Run command:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Passing tests verify the demo's functional behavior, **not that it is leak-free under production load**. Load tests must still inspect allocator metrics, RSS, heap/GC, and cancellation behavior.

### 26.2. Load Tests Must Cover Multiple Client Behaviors

Do not just fire 100 sequential requests. Include:
- 1, 10, 100, and 1,000 concurrent uploads across multiple payload sizes.
- Slow upload senders: drip chunks every few seconds.
- Slow download consumers: deliberately throttle receive rate.
- Mid-upload and mid-download cancellations.
- Uploads right at 8 MiB and over 8 MiB.
- JSON payloads of 10 KiB, 256 KiB, and >256 KiB.
- Multipart requests with many parts and files crossing the disk threshold.
- Long-lived WebSocket/SSE subscribers.
- Restart/cancel/error paths, verifying `active.direct.memory` returns to baseline.

All load tests must enforce **safe bounds and isolated environments**, never targeting production endpoints or files holding personal data. Before launching concurrent uploads, calculate `requests × payload size` and verify network/disk/cgroup limits.

## 27. Safe HTTP Memory Design Checklist

- [ ] Distinguished heap, Java NIO direct, Netty native/pooled, kernel socket, and proxy buffers.
- [ ] Never treated `-Xmx` as the total process cap; reserved native/direct/TLS/stack headroom.
- [ ] Understood ownership of `DataBuffer` and `PooledDataBuffer`, releasing in the consumer.
- [ ] Used `try/finally` and `DataBufferUtils.release` whenever reading and consuming a `DataBuffer`.
- [ ] Avoided releasing buffers handed to an HTTP writer before the writer consumes them.
- [ ] Ensured discarded/canceled buffers are released using `doOnDiscard` as appropriate.
- [ ] Kept `DataBuffer` references out of unbounded lists and caches.
- [ ] Avoided `collectList()` or unbounded `join()` for large requests/responses.
- [ ] Configured `spring.http.codecs.max-in-memory-size` per Boot 3.5 with per-aggregation semantics in mind.
- [ ] Enforced explicit raw body size caps so streaming uploads still have total byte limits.
- [ ] Bounded multipart part count, per-part RAM, and per-part disk usage.
- [ ] Kept header-size, codec, file-size, and connection-buffer limits distinct.
- [ ] Streamed large downloads in chunks or via proper file/`Resource` mechanisms.
- [ ] Verified reactive sources honor backpressure; bounded buffers and `flatMap` concurrency.
- [ ] Tested slow clients, cancellation, and error/timeout stream/buffer cleanup.
- [ ] Monitored heap/GC, JVM BufferPool, Netty direct used/active, and RSS/cgroup together.
- [ ] Applied heap dumps, NMT, and Netty leak detection appropriately per memory region.
- [ ] Ran concurrency + slow-client + cancellation + restart load tests before production.
- [ ] Never raised codec caps, `-Xmx`, or direct memory merely to hide leaks/OOMs without measuring.
- [ ] Protected Actuator/JMX/diagnostic endpoints from public Internet access.

## 28. Review Questions

**1.** Why can a JVM with `-Xmx512m` still be OOMKilled inside a 768 MiB container?

**Answer:** `-Xmx` only caps the Java heap; the process also uses direct/native memory, metaspace, code cache, thread stacks, TLS/transport buffers, and cgroup-accounted pages. Monitor RSS/cgroup and allocate headroom.

**2.** Does `ByteBuffer.allocateDirect` create a Java object?

**Answer:** Yes—there is a wrapper object on the heap, while its byte backing resides in off-heap/native memory. Direct buffers do not automatically guarantee zero-copy for every I/O path.

**3.** If Netty `used.direct.memory` stays high after traffic drops, is there definitely a leak?

**Answer:** No. The pooled allocator may retain reserved chunks/arenas for reuse. Check `active.direct.memory`, live requests, post-warm-up trends, and leak detection.

**4.** Must controllers manually release every `DataBuffer` in WebFlux?

**Answer:** No. When framework codecs or the HTTP writer own the buffer, the framework handles it; when app code directly consumes an inbound `Flux<DataBuffer>` or holds pooled buffers, it must manage retain/release lifecycles.

**5.** Why does `DataBuffer.readableByteBuffers()` require try-with-resources?

**Answer:** The returned iterator has its own lifecycle and must be closed; views must never be retained beyond the iteration or after releasing the `DataBuffer`.

**6.** Does `spring.http.codecs.max-in-memory-size=256KB` reject every 512 KiB upload?

**Answer:** No. It applies when a codec must aggregate. Streaming `Flux<DataBuffer>` routes can exceed 256 KiB, so enforce total byte caps and layer limits explicitly.

**7.** When `@RequestBody Mono<JsonRequest>` decodes an oversized JSON payload, what error can occur?

**Answer:** `DataBufferLimitException` when codec aggregation exceeds its limit. Final HTTP status depends on explicit error mapping and tests per app/framework.

**8.** Why is `collectList()` on `Flux<DataBuffer>` dangerous?

**Answer:** It holds all buffer references until stream completion, scaling memory with the entire body/response and risking pooled refcount leaks if not properly released.

**9.** Does backpressure automatically bound every application queue?

**Answer:** No. Hot producers, unbounded `onBackpressureBuffer`, `flatMap` prefetch, or transport queues can still grow memory. Explicitly bound queues and handle slow consumers.

**10.** Does `jvm.buffer.memory.used` equal Netty direct bytes plus process RSS?

**Answer:** No. JVM `BufferPoolMXBean` only reports the pools it tracks. Netty maintains its own allocator meters, and RSS includes many other native memory regions.

**11.** Why does the SHA-256 demo use `Mono.defer(...)`?

**Answer:** To allocate a fresh `MessageDigest` and counter per subscription/request rather than sharing mutable state across requests or retries.

**12.** Exactly how many response body bytes does `/api/stream?chunks=4` produce?

**Answer:** 4 × 4096 = **16,384 bytes**. HTTP framing overhead is excluded from the entity body saved by `curl -o`.

**13.** When rejecting an upload >8 MiB, how must the current buffer be handled?

**Answer:** Release the received buffer in `finally` and ensure discarded/canceled buffers are also released via hooks, retaining no references after erroring.

**14.** Will raising `-XX:MaxDirectMemorySize` fix a Netty buffer leak?

**Answer:** No. It may delay the crash or shift the failure mode, while ownership bugs remain; Netty native allocations and cgroup budgets must also be considered.

**15.** Why shouldn't you call `Thread.sleep` to throttle throughput and "relieve" memory pressure in WebFlux?

**Answer:** Blocking the event loop cripples connection handling and swells pending queues. Use proper backpressure, rate/concurrency limits, and async processing.

### Extension Exercises

1. Test `/api/digest` with a 512 KiB payload and explain why the 256 KB codec cap does not block the raw streaming path; then test >8 MiB and inspect the status.
2. Replace the download `Flux<DataBuffer>` with a 4 MiB `Mono<byte[]>` and measure heap/GC differences across 50–100 concurrent clients without guessing results beforehand.
3. Write a mid-upload cancellation test to confirm `DataBufferUtils.release` runs for both consumed and discarded buffers.
4. Enable Netty allocator metrics where runtime-supported and track `used.direct.memory` and `active.direct.memory` before, during, and after load.
5. Send a JSON body >256 KiB and map `DataBufferLimitException` to 413 per contract.
6. Test multipart files and observe the memory-vs-disk threshold, part counts, and disk quotas.
7. Set a low container memory limit in a test environment, vary `-Xmx` and `MaxDirectMemorySize` carefully, and measure RSS/GC/allocators without triggering OOM in production.
8. Evaluate long-lived SSE/WebSocket sessions: buffers/queues held per session, slow-consumer policies, and post-disconnect cleanup.
9. Combine JFR/NMT with Micrometer to compare heap/native/transport hotspots over a bounded load test.

## 29. Official References

- [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html)
- [Spring Framework 6.2 — WebFlux Reactive Core, Limits, Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebFlux Config: HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — DataBuffer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html)
- [Spring Framework 6.2 — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Boot 3.5 — Common Application Properties: `spring.http.codecs` / WebFlux multipart](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Actuator Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Reactor Netty — HTTP Server and Buffer Allocator Metrics](https://projectreactor.io/docs/netty/release/reference/http-server.html)
- [Reactor Netty — HTTP Client and ByteBuf Leak Detection](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor — Backpressure and Flux](https://projectreactor.io/docs/core/release/reference/)
- [Oracle JDK 17 — Java Command, `MaxDirectMemorySize`, and NMT](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Diagnostic Command `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Java SE 17 — `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Netty — Reference-counted Objects](https://netty.io/wiki/reference-counted-objects.html)
- [Micrometer — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)

**Conclusion:** Heap, Java direct memory, Netty pooled buffers, and HTTP codec buffers have **different ownership models, limits, and metrics**. For large HTTP payloads, prefer bounded streaming, release `DataBuffer` instances properly when consuming directly, respect backpressure, and keep codec limits distinct from total request limits. Diagnose memory using **heap + direct allocator active/used + RSS/cgroup + concurrency**, rather than staring only at `-Xmx` or a single 413 exception.