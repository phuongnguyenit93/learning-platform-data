# Verifying Caching or Compression When Responses Are Streamed in Spring Boot

## 1. Objectives and Questions to Answer

An API **returning a streaming response** does not necessarily finish generating all content before starting transmission. The server can write incrementally—such as a progressively generated CSV report, log stream, long data feed, or **Server-Sent Events (SSE)**.

When enabling HTTP caching or GZIP compression, you must inspect the **actual path from server to client**, rather than merely reading controller code or checking enabled properties:

1. Is the response **cached**? Are browser/CDN/proxy caches permitted to store, reuse, or revalidate it?
2. Is the response **compressed**? When the client sends `Accept-Encoding: gzip`, does the server truly return `Content-Encoding: gzip` with valid GZIP bytes, or only uncompressed text?
3. If streaming, do data chunks arrive **incrementally over time**? Or are they buffered in the application, container, proxy, cache filter, or compression layer until nearly the end?
4. What affects `Content-Length`, `Transfer-Encoding: chunked`, HTTP/2, `ETag`, and `Vary`?
5. How do you write a **runnable Java 17+ Spring Boot MVC** example, test it with curl, and write real HTTP integration tests rather than drawing conclusions from MockMvc?

**Principle:** streaming is **how the body is emitted**, caching is the **policy for storing/reusing HTTP responses**, and compression is the **wire encoding of the body representation**. The three concerns are independent yet can interact via buffering, HTTP headers, and proxies.

## 2. Distinguishing Streaming, Caching, Compression, and Chunked Transfer

| Concept | Meaning | Observable headers/signals | Do not misunderstand |
| --- | --- | --- | --- |
| Streaming | Application can emit body parts before all data is ready | Byte arrival timing, `flush`, stream completion | Does not automatically mean “no cache” or “no compression” |
| HTTP caching | Browser/proxy allowed to store and reuse responses per policy | `Cache-Control`, `ETag`, `Last-Modified`, `Age`, `Vary`, `304` | `Cache-Control` is not compression |
| HTTP compression | Transferred content uses a content coding such as gzip | Request `Accept-Encoding`, response `Content-Encoding: gzip`, GZIP bytes | `Content-Type` does not become `application/gzip`; underlying MIME stays |
| Chunked transfer | HTTP/1.1 sends body in chunks when total length is unknown upfront | `Transfer-Encoding: chunked` (if used) | Chunked is not GZIP; HTTP/2 does not use this header |
| SSE | Text event stream using `text/event-stream`, often long-lived | `Content-Type: text/event-stream` and `data: ...` lines | Not a JSON array that must buffer completely to decode |
| Conditional request | Client asks whether representation is still current | `If-None-Match`, `If-Modified-Since`, `304` response | Does not mechanically fit continuously changing streams |

An HTTP/1.1 response can be **both chunked and gzipped**:

```text
Application writes incrementally
        |
        v
GZIP compressor -> compressed bytes
        |
        v
HTTP/1.1 chunked framing -> network
        |
        v
Client strips chunked framing -> gunzips GZIP -> reads content
```

In HTTP/2 and HTTP/3, data travels in those protocols' own frames **without `Transfer-Encoding: chunked`**; that does not mean streaming or compression is lost.

**Absence of `Content-Length` alone does not prove streaming:** a response can be buffered upfront and still sent chunked by the container. Conversely, a finite streamed response may know its size beforehand. Look at **byte arrival timing** and buffering along the path.

## 3. Streaming in Spring MVC and Spring WebFlux

### 3.1. Spring MVC / Servlet

Spring MVC offers several ways to return data incrementally:

- `StreamingResponseBody`: callback writing to the response's `OutputStream`, fitting progressively generated file exports or custom payloads. Spring runs it asynchronously; writing to the servlet stream remains blocking I/O on a dedicated task thread.
- `ResponseBodyEmitter`: emits multiple objects/fragments and lets the framework convert them into the HTTP body.
- `SseEmitter`: MVC-style SSE support, emitting multiple `text/event-stream` events.
- `Resource`, `ResponseEntity<Resource>`: fits existing files; **can** be read and streamed incrementally, which differs from callbacks generating continuous live data.
- `ResponseEntity<StreamingResponseBody>`: declares cache/content-type headers alongside a streaming body.

Callback example (snippet only; needs an enclosing controller and imports):

```java
StreamingResponseBody body = outputStream -> {
    outputStream.write("part A\n".getBytes(StandardCharsets.UTF_8));
    outputStream.flush();
    outputStream.write("part B\n".getBytes(StandardCharsets.UTF_8));
    outputStream.flush();
};
return ResponseEntity.ok()
    .cacheControl(CacheControl.noStore())
    .body(body);
```

`flush()` pushes bytes past Java/Servlet buffering at that moment, yet **does not guarantee the client receives them immediately**: gzip wrappers, web servers, proxies, TLS, and networks can still buffer or coalesce writes. When using `StreamingResponseBody`, configure an appropriate executor for MVC async handling under load, and monitor timeouts and client disconnects.

### 3.2. Spring WebFlux / Reactor

WebFlux can return `Flux<T>` / `Flux<ServerSentEvent<T>>`. For `text/event-stream` or NDJSON, the framework encodes items as a stream; serializing a `Flux` as a standard JSON array may buffer depending on media type/converters.

Illustrative snippet only, **not a standalone runnable class**:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(n -> ServerSentEvent.<String>builder()
            .id(Long.toString(n))
            .data("tick-" + n)
            .build());
}
```

Requires importing `Flux`, `ServerSentEvent`, `Duration`, and appropriate annotations. `Flux.interval` generates scheduled items without blocking the Netty event loop via `Thread.sleep`. This example stream is infinite; clients cancel the subscription on disconnect.

**Do not directly apply MVC `StreamingResponseBody` patterns to Netty WebFlux**; the two stacks differ in I/O, threading, and buffer control. Still, the semantics of `Cache-Control`, `Content-Encoding`, `Vary`, and end-to-end HTTP testing remain largely the same.

## 4. Caching When the Response Is a Stream

### 4.1. Are Streams Always Forbidden from Caching?

**No.** A streamed response can still be a **finite, stable resource**, such as a version-frozen CSV export. If HTTP cache policies permit and the response completes cleanly, a cache can store a copy and reuse/revalidate it when eligible.

Conversely, **live event streams, per-request/per-user feeds, or continuously changing data** generally should not be retained by shared caches. Sending bytes incrementally does not turn private data into “public” data.

| Response type | Usually appropriate policy | Why |
| --- | --- | --- |
| Personal SSE, real-time feeds, sensitive data | `Cache-Control: no-store` | Prevents compliant caches from storing responses |
| User-specific dashboard eligible for private cache | `private` and contract freshness/validators if truly needed | Prevents shared caches from reusing across users |
| Public file exports / versioned snapshots | `public, max-age=...` and properly computed `ETag`/`Last-Modified` | Stable representation suitable for caching |
| Resources needing revalidation every time yet storable | `no-cache` with suitable validator | `no-cache` **does not mean do not store** |
| Content that proxies must not transform | `no-transform` can be added | Governs representation transforms; **does not replace** `no-store` |

`no-store` and `no-cache` are easily confused:

- **`no-store`**: compliant caches must avoid storing request/response per directive rules. Use for private streams or where retention is unacceptable.
- **`no-cache`**: allows storage yet forbids serving another request without successful origin validation (or corresponding RFC rules).
- **`private`**: shared caches must not store; private browser caches may store if other directives allow.
- **`public`**: allows shared cache storage under appropriate conditions; apply only when certain no per-user data leaks.
- **`max-age=N`**: representation TTL/freshness; does not mean an active stream terminates or transfers faster.

In Spring MVC:

```java
// Snippet: used on ResponseEntity in a controller.
return ResponseEntity.ok()
    .cacheControl(CacheControl.noStore())
    .body(streamingBody);
```

Do not casually enable response caching on **infinite streams**, because a complete cache entry may never finish; some proxies/caching layers even attempt to buffer the entire response, preventing browsers from seeing incremental data.

### 4.2. ETag and Last-Modified: Need a Stable Representation

`ETag` is a validator enabling `If-None-Match`; GET/HEAD can receive `304 Not Modified` with **no body** when unchanged. `Last-Modified` / `If-Modified-Since` also provide conditional requests.

For a **versioned** snapshot whose ETag is known from metadata before streaming bytes, conditional requests can be evaluated **before** starting expensive streaming work. However, for time-varying streams or per-request dynamic feeds:

- Never hardcode a fake static `ETag` across byte-different outputs.
- Never turn on full-stream buffering just to compute a checksum when the goal is incremental emission and low memory.
- Never expect a live streaming request to return `304` merely because no new event arrived a moment ago.
- For gzip vs. identity content codings, byte representations differ; **strong ETags** must respect byte-for-byte uniqueness per representation. If a validator expresses semantic equivalence across encodings, consider a **weak ETag** per HTTP semantics and application needs.
- Never enable `ETag` without a coherent version definition and proper conditional request handling.

Spring MVC provides `ResponseEntity.eTag(...)` and `WebRequest.checkNotModified(...)` for finite resources. Choose strong/weak validators per the HTTP contract, including `Vary` when variants exist.

### 4.3. Watch Out for `ShallowEtagHeaderFilter`

`ShallowEtagHeaderFilter` computes an ETag from the **generated body** using `ContentCachingResponseWrapper`. This normally requires **caching/buffering the entire response before sending**, saving bandwidth on revalidation without saving body-generation CPU, and can **break real-time streaming**.

If an application registers this filter:

- Check whether it covers `/stream/**`, `/events`, or large file APIs.
- For streams not needing ETags, **exclude those paths** from the filter, or call `ShallowEtagHeaderFilter.disableContentCaching(request)` **before writing the response** per Spring API.
- Never blindly wrap every streaming response in `ContentCachingResponseWrapper` for logging or hashing; the wrapper holds the body in memory and prevents `flush()` from reaching clients promptly.
- If using async, inspect filter dispatch types (`ASYNC`) and lifecycles; improper registration breaks responses.
- Once the body commits, many headers/statuses cannot be changed. Decide cache policies/validators **before emitting bytes**.

## 5. HTTP Compression While Streaming

### 5.1. Negotiating Content-Encoding

A client can request:

```http
GET /demo/stream HTTP/1.1
Host: localhost:8080
Accept-Encoding: gzip
```

If the server qualifies for compression and picks gzip, the response looks like:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: no-store
Transfer-Encoding: chunked
```

This is an **HTTP/1.1 illustration**, not a guaranteed exact header set: `Transfer-Encoding: chunked` depends on version/container/length and can be changed by proxies; unlisted headers may also appear. **The body after these headers is GZIP bytes**, not directly readable text lines. Only after the client decodes the content coding does the user see text.

**Distinguish:**

- `Accept-Encoding` is client capability/preference; it **does not prove** the server compressed.
- `Content-Encoding: gzip` plus a valid GZIP signature/stream proves **compressed content on the wire**.
- `Content-Type: text/plain` still describes the **decoded** media type; it does not change to `application/gzip` when compressed.
- `Vary: Accept-Encoding` informs caches that compressed and uncompressed variants must be kept separate on reuse.
- `Content-Length` (if present) on a **gzip response** must be the compressed representation's byte count, **not** the uncompressed text byte count.
- Never manually set `Content-Length` to Java string length or pre-compression bytes when the container will gzip the stream.
- On HTTP/2/3, `Content-Encoding: gzip` can appear **without** chunked transfer coding.

### 5.2. Spring Boot Configuration

Example with **compatible Spring Boot 3.x, Java 17+, embedded Tomcat (default in spring-boot-starter-web)**:

```properties
server.port=8080

# Enable HTTP compression on the embedded web server.
server.compression.enabled=true

# Only allow compressing suitable data types in this demo.
server.compression.mime-types=text/plain,application/json

# Lower threshold to verify easily in local environment.
server.compression.min-response-size=1B

# Configure appropriate timeout for MVC async.
spring.mvc.async.request-timeout=30s
```

Spring Boot provides these properties to configure compression, yet **the actual compression decision belongs to the connector/container and request-response conditions**. Verify your exact Boot version, Tomcat/Jetty/Undertow/Netty, HTTP protocol, MIME, response status, `Accept-Encoding`, size, and proxies.

Per Spring Boot 3.5 documentation, `server.compression.enabled=false` by default; default MIMEs cover common text/JSON/XML types and default size threshold is `2KB`. For streams with **unknown Content-Length**, size evaluation and compression timing depend on implementation; **do not infer purely from `min-response-size`** that every small stream will be compressed.

In the demo, `mime-types` **omits `text/event-stream`**. That is intentional: SSE needs prompt event delivery and streaming compression can add buffering/latency; do not force SSE compression just to shave a few bytes. In real systems, proxies/CDNs must also avoid compressing/buffering SSE against latency goals.

### 5.3. GZIP and Buffering

Streamed compression **can still** emit output bytes incrementally; however, compressors buffer, batch writes before emitting blocks, and spend CPU. Calling `flush()` in Spring/Servlet does not mean gzip bytes hit the client instantly. GZIP encoders can emit sync flushes differently depending on configuration; reverse proxies can buffer further.

Therefore measure:

1. **TTFB** — when the first byte arrives at the client.
2. **Time between chunks/events** — observed intervals between data parts.
3. **Total download time** and throughput.
4. **Bytes transferred**: did gzip actually shrink size? For tiny payloads, gzip headers can make total bytes **larger**.
5. **Server CPU/memory**, response buffers, concurrent clients, and connection lifetime.

Do not pick “gzip” or “no gzip” by intuition: for large, highly compressible logs or JSON, gzip can help; for low-latency SSE or already-compressed data (ZIP, JPEG, PNG), extra compression rarely helps and can hurt.

## 6. Runnable Spring Boot MVC Example Application

The example provides **three endpoints**:

- `GET /demo/stream`: finite text emitted incrementally in a stream; **`Cache-Control: no-store`**, allowing GZIP inspection.
- `GET /demo/events`: finite SSE with two events, **no-store**; excluded from the demo's compression MIME list.
- `GET /demo/snapshot`: **stable, versioned** content with short-term public caching and a weak ETag to demonstrate revalidation in contrast to live streaming.

Uses **Spring Boot 3.5.x, Java 17+**, dependencies `spring-boot-starter-web` and `spring-boot-starter-test`. Default embedded server is Tomcat. Create the project via Spring Initializr using the Maven wrapper. If targeting Spring Boot 4.x, check that version's test/auto-configuration packages and starters rather than assuming identical imports.

### 6.1. File Structure

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ StreamCacheApplication.java
│  │  └─ StreamController.java
│  └─ resources/application.properties
└─ test/java/com/example/demo/
   └─ StreamHttpIntegrationTest.java
```

### 6.2. Configuration File

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.compression.enabled=true
server.compression.mime-types=text/plain,application/json
server.compression.min-response-size=1B
spring.mvc.async.request-timeout=30s
```

### 6.3. Main Class

**`src/main/java/com/example/demo/StreamCacheApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamCacheApplication.class, args);
    }
}
```

### 6.4. Controller

**`src/main/java/com/example/demo/StreamController.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/demo")
public class StreamController {

    @GetMapping(value = "/stream", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<StreamingResponseBody> stream() {
        StreamingResponseBody body = output -> {
            for (int index = 1; index <= 4; index++) {
                String chunk = "part=" + index
                    + ";payload=" + "JAVA".repeat(1000) + "\n";

                output.write(chunk.getBytes(StandardCharsets.UTF_8));
                output.flush();

                if (index < 4) {
                    pause();
                }
            }
        };

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(
                "text/plain;charset=UTF-8"))
            .cacheControl(CacheControl.noStore())
            .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_ENCODING)
            .body(body);
    }

    @GetMapping(value = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> events() {
        StreamingResponseBody body = output -> {
            for (int index = 1; index <= 2; index++) {
                String event = "event: tick\n"
                    + "id: " + index + "\n"
                    + "data: hello-" + index + "\n\n";
                output.write(event.getBytes(StandardCharsets.UTF_8));
                output.flush();

                if (index < 2) {
                    pause();
                }
            }
        };

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    @GetMapping(value = "/snapshot",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> snapshot() {
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .cacheControl(
                CacheControl.maxAge(60, TimeUnit.SECONDS).cachePublic()
            )
            .eTag("W/\"snapshot-v1\"")
            .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_ENCODING)
            .body("snapshot=v1\n");
    }

    private static void pause() throws IOException {
        try {
            Thread.sleep(150);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IOException("Streaming interrupted", ex);
        }
    }
}
```

**Exact explanation:**

1. `StreamingResponseBody` generates the body as writing runs on the MVC async worker, rather than building a 16KB string inside the controller and returning once.
2. `output.flush()` attempts to push chunks at four points; `pause()` makes intervals between writes easier to observe. **`Thread.sleep` is strictly for demo use**, not how production streaming should work.
3. `stream()` sets `no-store` **before sending bytes**, fitting on-demand content that browsers/proxies should not store. It omits `Content-Length` because encoded length is unknown.
4. `Vary: Accept-Encoding` helps caches distinguish encoding variants if cache policies change later. Alongside `no-store`, Vary does not replace no-store.
5. `events()` produces valid SSE text: each event has `event:`, `id:`, `data:`, and **a blank line terminating the event**. This is finite SSE for demo; production SSE runs longer and needs heartbeats, backpressure, and reconnect logic.
6. `snapshot()` intentionally **does not** stream: it models a versioned, short-cached resource with weak ETag `W/"snapshot-v1"` to avoid claiming byte-identity across content codings. Spring MVC supports conditional requests with `ResponseEntity` ETags; do not force 304 onto live streams.
7. Endpoints run over local **HTTP** for easy testing. Production needs HTTPS, authentication/authorization for private data, proper timeouts, and secret-compression risk review.

**Note on executors:** Spring Framework docs recommend configuring an appropriate `TaskExecutor` for MVC async streaming rather than relying on the default development executor under heavy load. This small example skips pool tuning to keep the code focused. For many long-lived stream clients, measure active threads and set concurrency limits, timeouts, queues, graceful shutdown, and client-disconnect handling.

## 7. Manual Testing with curl: Observing Real Headers and Bytes

Start the application:

```bash
java -version
./mvnw spring-boot:run
```

On Windows use `mvnw.cmd spring-boot:run`; when PowerShell aliases `curl`, use `curl.exe`. The examples below use Bash/Unix syntax.

### 7.1. Uncompressed Baseline

Request identity coding:

```bash
curl --http1.1 -sS -D identity-headers.txt \
  -H 'Accept-Encoding: identity' \
  -o identity.txt \
  http://localhost:8080/demo/stream
```

Inspect `identity-headers.txt`:

- Expect `HTTP/1.1 200`.
- `Content-Type: text/plain;charset=UTF-8` (spacing/casing may vary).
- `Cache-Control: no-store`.
- **Normally no** `Content-Encoding: gzip` when requesting `identity`.
- `Vary: Accept-Encoding`.
- `Transfer-Encoding: chunked` may appear if Tomcat streams unknown-length bodies over HTTP/1.1; **do not write rigid invariants requiring that header**.

`identity.txt` contains four parts:

```text
part=1;payload=JAVAJAVAJAVA...
part=2;payload=JAVAJAVAJAVA...
part=3;payload=JAVAJAVAJAVA...
part=4;payload=JAVAJAVAJAVA...
```

The ellipses `...` are just shorthand for illustration; **the real file repeats `"JAVA"` 1000 times per part** (without `...`). The demo omits timestamps or UUIDs so bytes stay deterministic across requests, aiding gzip vs. identity comparison.

### 7.2. Request GZIP and Verify Payload

```bash
curl --http1.1 -sS -D gzip-headers.txt \
  -H 'Accept-Encoding: gzip' \
  -o response.gz \
  http://localhost:8080/demo/stream
```

**Do not add `--compressed` to this command**: depending on the tool, `--compressed` auto-decompresses before writing `-o`, tricking you into thinking the saved file is compressed when it actually contains text.

Verify `gzip-headers.txt` has `Content-Encoding: gzip`. Then decompress the raw body:

```bash
gzip -dc response.gz > decoded.txt
cmp identity.txt decoded.txt
wc -c identity.txt response.gz
```

Expect `cmp` to output nothing and exit with code **0** when both files match byte-for-byte. With `"JAVA"` repeated heavily, `response.gz` is much smaller than `identity.txt`; exact numbers depend on GZIP implementation rather than a fixed constant.

You can check the first two GZIP bytes with a hex tool (typically `1f 8b`), yet **do not rely solely on magic bytes**: successful decompression and byte comparison remain more reliable.

If the response lacks `Content-Encoding: gzip`, **do not jump to “Spring doesn't support streaming gzip”**. Recheck `server.compression.enabled`, actual MIME, size/length, HTTP request headers, container, filters, and proxies. Whether streaming responses compress can vary by connector and version.

### 7.3. `curl --compressed` and the Auto-Decompression Trap

```bash
curl --http1.1 --compressed -sS \
  -D auto-headers.txt \
  -o auto-decoded.txt \
  http://localhost:8080/demo/stream
```

`--compressed` requests a content coding supported by curl and **automatically decompresses** received data. Thus `auto-decoded.txt` will be **decompressed text** even while server headers show `Content-Encoding: gzip`. Concluding “no compression happened” from that output file is a mistake.

For accurate verification, combine **wire response headers, raw bytes**, decompression, and comparison with the identity copy.

### 7.4. Observing Incremental Delivery, Not Just Status 200

To observe the uncompressed text stream:

```bash
curl --http1.1 --no-buffer \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/demo/stream
```

`--no-buffer` (short `-N`) disables **curl's** output buffering, though it does not disable container, GZIP, or reverse-proxy buffers. Since the app writes and flushes roughly every 150 ms, you may see chunks arrive in waves; visibility also depends on terminal/network.

Record total time and TTFB with curl:

```bash
curl --http1.1 -sS -o /dev/null \
  -w 'ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/demo/stream
```

`time_starttransfer` measures time to first byte per curl's mechanism; it **does not show gaps between every chunk**. To measure real chunk latency, use a streaming reader that timestamps each received chunk, or direct network tracing. Flushing writes in Java does not guarantee every write becomes its own network chunk or client read.

### 7.5. SSE: Avoiding Compression and Buffering When Low Latency Is Required

```bash
curl --http1.1 -N -i \
  -H 'Accept: text/event-stream' \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/demo/events
```

Expected under the demo config:

- `Content-Type: text/event-stream`.
- `Cache-Control: no-store`.
- **No** `Content-Encoding: gzip` because compression MIME list **excludes** `text/event-stream`.
- Body consists of two `tick` events separated by a blank line, not a JSON array.
- Data may arrive in two writes ~150 ms apart at the app, though proxies or networks can coalesce them.

When deploying behind Nginx or a buffering proxy, inspect proxy buffering/caching/compression per location. For example, **`X-Accel-Buffering: no`** is recognized by certain Nginx configs to control buffering; it is **not a universal standard honored by every proxy**. For SSE, design heartbeats, cache bypass, idle timeouts, and proxy streaming settings for your real infrastructure.

### 7.6. Revalidation on the Snapshot Endpoint

First fetch the ETag:

```bash
curl -i \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/demo/snapshot
```

The response may look like:

```http
HTTP/1.1 200 OK
Cache-Control: max-age=60, public
ETag: W/"snapshot-v1"
Content-Type: text/plain
Vary: Accept-Encoding
```

Actual header ordering/casing varies. Next send `If-None-Match`:

```bash
curl -i \
  -H 'Accept-Encoding: identity' \
  -H 'If-None-Match: W/"snapshot-v1"' \
  http://localhost:8080/demo/snapshot
```

With Spring MVC and the sample controller, expect **304 Not Modified**, **no response body**. Compare with `/demo/stream`: that endpoint omits ETag because it has no storage/reuse policy, even though its demo output happens to look deterministic.

**Do not use that request to “prove the CDN cache works”**: curl does not keep an HTTP cache like browsers; it only demonstrates the origin supports conditional requests. To prove browser/CDN/proxy caching, test **through that exact cache layer** and inspect cache behavior/metrics.

## 8. Integration Testing Over Real HTTP, Not Just MockMvc

### Why Are End-to-End Tests Needed?

`MockMvc` is great for testing controllers, Spring-assigned headers, and async dispatches, yet it **does not run the real HTTP connector of embedded Tomcat/Jetty**, and does not prove HTTP compression, chunked framing, or network buffering actually occur. For compression and streaming, you need at least one **integration test opening a real port** or running curl against a real server.

Create the file:

**`src/test/java/com/example/demo/StreamHttpIntegrationTest.java`**

```java
package com.example.demo;

import java.io.ByteArrayInputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamHttpIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpResponse<byte[]> get(String path, String acceptEncoding)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri(path))
            .header("Accept-Encoding", acceptEncoding)
            .GET()
            .build();

        return client.send(request, HttpResponse.BodyHandlers.ofByteArray());
    }

    @Test
    void streamedResponseDeclaresNoStore() throws Exception {
        HttpResponse<byte[]> response = get(
            "/demo/stream", "identity"
        );

        assertEquals(200, response.statusCode());
        assertTrue(
            response.headers().firstValue("Cache-Control")
                .orElse("").contains("no-store")
        );
        assertTrue(
            response.headers().firstValue("Vary")
                .orElse("").contains("Accept-Encoding")
        );
        String body = new String(
            response.body(), StandardCharsets.UTF_8
        );
        assertTrue(body.contains("part=1;payload="));
        assertTrue(body.contains("part=4;payload="));
        assertTrue(body.endsWith("\n"));
    }

    @Test
    void gzipIsAppliedToStreamOverRealHttp() throws Exception {
        HttpResponse<byte[]> response = get(
            "/demo/stream", "gzip"
        );

        assertEquals(200, response.statusCode());
        assertEquals(
            "gzip",
            response.headers().firstValue("Content-Encoding")
                .orElse("")
        );

        // JDK HttpClient returns received body bytes; gunzip explicitly.
        String decoded;
        try (GZIPInputStream gzip = new GZIPInputStream(
                new ByteArrayInputStream(response.body()))) {
            decoded = new String(
                gzip.readAllBytes(), StandardCharsets.UTF_8
            );
        }

        assertTrue(decoded.contains("part=1;payload="));
        assertTrue(decoded.contains("part=4;payload="));
        assertTrue(decoded.endsWith("\n"));
    }

    @Test
    void eventStreamIsNotCompressedInThisConfiguration()
            throws Exception {
        HttpResponse<byte[]> response = get(
            "/demo/events", "gzip"
        );

        assertEquals(200, response.statusCode());
        assertTrue(
            response.headers().firstValue("Content-Type")
                .orElse("").startsWith("text/event-stream")
        );
        assertTrue(
            response.headers().firstValue("Cache-Control")
                .orElse("").contains("no-store")
        );
        assertTrue(
            response.headers().firstValue("Content-Encoding").isEmpty()
        );

        String body = new String(
            response.body(), StandardCharsets.UTF_8
        );
        assertTrue(body.contains("data: hello-1\n\n"));
        assertTrue(body.contains("data: hello-2\n\n"));
    }

    @Test
    void snapshotSupportsConditionalGet() throws Exception {
        HttpResponse<byte[]> initial = get(
            "/demo/snapshot", "identity"
        );
        assertEquals(200, initial.statusCode());

        String etag = initial.headers().firstValue("ETag")
            .orElseThrow();

        HttpRequest conditional = HttpRequest.newBuilder(
                uri("/demo/snapshot"))
            .header("Accept-Encoding", "identity")
            .header("If-None-Match", etag)
            .GET()
            .build();

        HttpResponse<byte[]> response = client.send(
            conditional, HttpResponse.BodyHandlers.ofByteArray()
        );
        assertEquals(304, response.statusCode());
        assertEquals(0, response.body().length);
    }
}
```

**Note on imports:** `@Autowired` and `Environment` are unused in the test class above so they can be removed for clean code; they do not cause compilation errors, though they are unnecessary in a real project.

Run tests when **no other instance locks a fixed port**, since `@SpringBootTest(RANDOM_PORT)` starts its own embedded server on a random port:

```bash
./mvnw test
```

All four tests are **expected to pass with Spring Boot 3.5.x + embedded Tomcat and compression configured as shown**. That is the design expectation, **not a claim that tests were executed in a live repository**. If the gzip test fails:

- First check `Content-Encoding` and the active server type.
- Check whether the project uses default Tomcat or switched to Jetty/Undertow.
- Verify `application.properties` was actually loaded and not overridden by profiles/env vars.
- Verify the endpoint's `Content-Type` matches `server.compression.mime-types`.
- Check that the client sent `Accept-Encoding: gzip`, with no reverse proxy or filter re-encoding/decoding.
- Never “fix” the test by removing the GZIP assertion just to make it green; the test targets the exact feature you want to verify.

**Test scope:** `HttpClient.send(...ofByteArray())` waits for the **entire** body before asserting. It proves gzip headers and decompressed bytes are right, **yet does not prove incremental chunk arrival**. To measure arrival latency, add a `BodyHandlers.ofInputStream()` test/client reading the stream over time or use direct network tracing. CDN/proxy cache checks must also run against the real cache layer.

## 9. Pitfalls That Make Tests “Pass Locally, Fail in Production”

### 9.1. Reverse Proxies, CDNs, and Response Buffering

Common path:

```text
Spring Boot MVC (flush)
       |
       v
Embedded Tomcat / gzip
       |
       v
Nginx / API gateway / CDN (may buffer, recompress, cache)
       |
       v
TLS / network
       |
       v
Browser / curl / EventSource
```

A proxy can accumulate multiple chunks before sending, even when the application flushes properly. A CDN can apply gzip/brotli, add `Vary`, or cache according to its own config. Therefore test both **direct-to-app** and **through production-like URLs**, comparing headers, TTFB, and event spacing.

Some proxies buffer responses by default; for SSE, disable buffering on that specific location and ensure idle timeouts exceed intervals between heartbeats/events. Never change global proxy settings just for one endpoint without considering resources, security, and other services.

### 9.2. Missing `Content-Length` and Handling Mid-Stream Errors

When total stream bytes are unknown or the body will be compressed, **never set `Content-Length` manually** from character counts or uncompressed size. HTTP/1.1 can use chunked transfer; HTTP/2 uses its own frames. Once the server commits headers/body, an exception mid-stream usually cannot cleanly change status 200 to 500. Clients may see dropped connections or truncated streams.

Production systems should have:

- Logs/metrics for stream **start – completion – error – client disconnect**.
- Formats with explicit completion markers or terminal events if the domain must detect complete streams.
- Timeouts, backpressure, concurrent stream limits, resource cleanup, and cancellation.
- No leaked stack traces/file paths/secrets inside error data events.
- For progressively generated file exports, consider building the complete file first if integrity hashes, verification, and accurate download resume are required.

### 9.3. GZIP and Length-Based Information Leakage

If a compressed response mixes **secrets** (CSRF tokens, session credentials, sensitive info) with attacker-controlled text whose body length the attacker can observe, compression can contribute to **compression side channels** (related to attack classes such as BREACH). Do not enable gzip casually on every sensitive endpoint solely to save bandwidth.

Mitigate per threat model: avoid mixing secrets with controllable output, reduce observability and enforce CORS/CSRF controls, and consider disabling compression on risky endpoints; TLS **does not eliminate** length inference on compressed responses.

### 9.4. Shared Caches Leaking User Data

`Cache-Control: public` on personalized responses or `Authorization`/cookie-dependent exports is dangerous if proxy/cache keys do not isolate users. `Vary: Accept-Encoding` only separates gzip vs. identity; it **does not** replace authorization or `private`/`no-store`.

A stream returning per-tenant/per-user data should be treated as sensitive by default unless explicitly designed as a public representation. Do not test only an uncached first request and declare caching safe; test across multiple users, requests, and URL/query/header cache-key dimensions.

### 9.5. Chunk Boundary Tests Can Be Misled by Client Read Behavior

A single `write()` call does not map 1:1 to:

- one HTTP/1.1 chunk,
- one HTTP/2 DATA frame,
- one TCP packet,
- one client network read callback.

Layers can split or coalesce writes. When parsing event streams, rely on **formats with explicit delimiters/framing** such as SSE (blank lines between events) or NDJSON (one JSON object per line), never buffer sizes or `read()` boundaries.

### 9.6. “Server Compression Enabled” Does Not Mean Every Response Is Gzipped

Check every condition:

1. Did the client send `Accept-Encoding` accepting that coding?
2. Is `Content-Type` in the compressible MIME list?
3. Did the response exceed the threshold and satisfy container rules?
4. Is there a status, range, prior content coding, or unsuitable scenario?
5. Did a proxy/CDN decompress, recompress, or rewrite headers?
6. Did the test client automatically decompress the response before passing the body to your assertion?

Do not judge from **output file size after auto-decompression**. Compare wire headers, raw encoded bytes, and decompressed output.

## 10. Streaming Cache and Compression Testing Checklist

| Question | How to verify | Passing criteria |
| --- | --- | --- |
| Is the response genuinely streaming or returned only at completion? | `curl -N`; streaming client timestamping bytes, check proxy buffering | Bytes/events arrive incrementally per app SLA |
| Do cache headers match the policy? | `curl -D headers.txt`, inspect `Cache-Control` | Live/private streams -> usually `no-store` |
| Did a cache store or wrongly replay a stream? | Test via browser/CDN/proxy and check metrics/cache status | Disallowed content is never stored/reused |
| Is GZIP applied when requested? | `Accept-Encoding:gzip` + `Content-Encoding:gzip`, raw `.gz` | Real bytes gunzip cleanly and match identity |
| Is it uncompressed when not requested? | `Accept-Encoding: identity` | No gzip content coding, readable body |
| Does `Vary` distinguish variants? | Check `Vary: Accept-Encoding` where applicable | Cache never mixes gzip/identity copies |
| Does SSE maintain low latency? | `curl -N`, proxy config, and event timestamps | Not unintentionally compressed/buffered |
| Is `Content-Length` accurate? | Compare raw bytes, check status/coding | Never set wrong length, especially after compression |
| Is HTTP/1.1 chunked confused with GZIP? | Check `Transfer-Encoding` and `Content-Encoding` | Understand the two distinct layers |
| Is the snapshot cacheable? | Request `If-None-Match` with ETag | Bodyless 304 when resource unchanged |
| Does ShallowEtag filter hurt streams? | Inspect wrappers/filters and response latency/memory | Never buffer entire stream just to compute ETag |
| Did tests run over a real HTTP connector? | `@SpringBootTest(RANDOM_PORT)` or curl against real Tomcat | Verifies compression/transfer on the wire |
| Are mid-stream errors and disconnects handled? | Test connection drops, timeouts, fault injection | No resource leaks, accurate logs/metrics |
| Can inputs/secrets cause side channels or cache leaks? | Audit sensitive endpoints and compression/cache policies | No unsafe compression/caching of sensitive data |

## 11. Misconceptions to Avoid

**“Using `StreamingResponseBody` means the response cannot be cached.”** False. HTTP cacheability depends on policy, representation type, and cache ability to hold a complete response, not the Java return type alone.

**“`no-cache` means do not store.”** False. `no-store` targets no storage; `no-cache` targets revalidation before reuse.

**“Setting `server.compression.enabled=true` gzips every response.”** False. MIME, size, `Accept-Encoding`, container, and proxies decide; measure actual responses.

**“Seeing `Transfer-Encoding: chunked` means it is compressed.”** False. Chunked is HTTP/1.1 framing, not gzip.

**“No `Transfer-Encoding: chunked` means it is not streaming.”** False. HTTP/2/3 do not use chunked, and HTTP/1.1 has other body-framing mechanisms.

**“`curl --compressed` writes a gzipped file.”** False in typical usage: curl **auto-decompresses**, so `-o` receives decoded content.

**“Calling `flush()` means browsers see events immediately.”** False. GZIP, proxy buffering, TLS, and networks can delay or batch writes.

**“Computing ETags for streams with a filter is free.”** False. `ShallowEtagHeaderFilter` computes from the full body and can buffer, defeating incremental delivery.

**“ETags for gzip and identity always share one strong tag.”** Unsafe under strong validator semantics. Byte-different representations can need distinct strong ETags; weak ETags express broader semantic equivalence per HTTP contracts.

**“MockMvc tests prove compression works on the wire.”** False. MockMvc skips the real Tomcat HTTP connector; use integration tests or curl.

**“Seeing `Cache-Control: no-store` guarantees the CDN won't cache.”** It is the standard directive, yet real cache/proxy configs still need testing, especially against override rules or misconfigurations.

## 12. Self-Check Questions

1. **Do streaming responses default to `Cache-Control: no-store`?** No. Set it explicitly according to data class and policy.
2. **Can a finite CSV stream with a stable version be cached?** Yes, if policy and validators suit, the cache receives the complete representation, and no forbidden private data is present.
3. **Should SSE always be compressed to save bandwidth?** No. SSE must weigh latency and buffering, and usually stays uncompressed when prompt event delivery is the priority.
4. **The client sends `Accept-Encoding: gzip`, yet the response lacks `Content-Encoding`—is that definitely a bug?** No. The server may choose identity when compression rules are not met or not configured.
5. **Should `Content-Length` be the byte count before or after gzip?** If present on a gzipped response, it must reflect the bytes of the actual encoded representation sent per HTTP semantics, not the original text length.
6. **If `curl --compressed` outputs readable text, did the server skip compression?** No; curl may have decompressed it.
7. **Can `ShallowEtagHeaderFilter` slow down client receipt?** Yes. It can buffer the entire response before transmitting, defeating streaming goals.
8. **Does one `output.write` equal one HTTP chunk?** No. Multiple buffering/framing layers exist with no 1:1 guarantee.
9. **Which endpoint in the demo should be queried to verify 304?** `/demo/snapshot` with `If-None-Match`. The live `/demo/stream` uses `no-store` and has no ETag.
10. **Should a cookie/user-dependent response be shared-cached just because `Vary: Accept-Encoding` is set?** No. `Vary` for content coding does not isolate users; proper authorization and `private`/`no-store` policies are required.

## 13. Official Documentation for Reference

- Spring Boot 3.5, *Common Application Properties*: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/ (see `server.compression.*` and `spring.mvc.async.request-timeout`).
- Spring Framework, *Asynchronous Requests (Spring MVC)*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html (see `StreamingResponseBody`, `SseEmitter`, and async executors).
- Spring Framework, *HTTP Caching (MVC)*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html (see `CacheControl`, `ETag`, `Last-Modified`, and `304`).
- Spring Framework, *HTTP Caching (WebFlux)*: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html.
- Spring Framework, `ShallowEtagHeaderFilter` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html (see `disableContentCaching`).
- RFC 9110, *HTTP Semantics*: https://www.rfc-editor.org/rfc/rfc9110 (see Content-Encoding, Accept-Encoding, Vary, ETag, and framing).
- RFC 9111, *HTTP Caching*: https://www.rfc-editor.org/rfc/rfc9111 (see meanings of `no-store`, `no-cache`, `private`, `public`).
- MDN, *Content-Encoding*: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Encoding.
- MDN, *Server-sent events*: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events.

**Conclusion:** to verify caching or compression when Spring Boot streams response bodies, separate **cache policy**, **wire-compressed content**, and **actual client byte/event arrival timing**. Choose `Cache-Control` per data characteristics, use `Vary` when variants exist, verify `server.compression.*` configs, exclude buffering ETag filters from live streams, and test through a real HTTP connector. Compare direct-to-app against reverse proxy/CDN paths before concluding your production setup streams, compresses, and caches properly.