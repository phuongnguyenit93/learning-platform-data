# Request Body, Multipart, Header, and Codec Limits in Spring Boot

## 1. Objectives and Four Limits You Must Not Equate

A Spring Boot endpoint can receive JSON, forms, uploaded files, binary payloads, or requests carrying huge HTTP headers. Simply raising heap or tweaking an arbitrary "max size" property still leaves the application vulnerable to oversized requests, temp-disk exhaustion, header-parsing overhead, decoder buffers, or excessive concurrent connections.

This lesson belongs to **Performance and Limits** in the **Spring Boot - web-runtime** module. We separate four distinct scopes:

1. **Request body**: the full HTTP request payload—JSON, text, binary, or multipart. Total body limits across gateway, container, and application rarely share one single property.
2. **Multipart upload**: total request size, individual file part size, form fields, part counts, per-part headers, in-memory spill thresholds, and temp disk directories. Servlet and WebFlux handle these differently.
3. **HTTP headers**: request line/URI plus HTTP headers such as `Cookie` and `Authorization`. These limits trigger **before reaching the controller** and differ from multipart part headers.
4. **Codec buffering**: bytes an HTTP message reader/decoder must aggregate in memory to deserialize into an object such as a JSON DTO, `String`, or `byte[]`. It is **not a total request body cap** on every route, especially when streaming.

**Most important takeaway:** `spring.codec.max-in-memory-size=256KB` does not turn every request >256KB into HTTP 413. It configures buffer bounds for **auto-configured WebFlux server/WebClient codecs** when aggregation/decoding is required. `spring.servlet.multipart.max-file-size` applies to Servlet multipart uploads, not arbitrary `@RequestBody` JSON payloads. `server.tomcat.max-swallow-size` controls how much body Tomcat drains after rejecting a request, not "max upload size".

This lesson uses **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x** across two standalone runnable projects: MVC/Tomcat and WebFlux/Reactor Netty. Values like 64KiB and 128KiB in demos are **practical test values**, not universal production defaults. In real deployments, calibrate against API payload contracts, concurrency, memory/disk quotas, and business requirements.

## 2. Limits Apply Across Multiple Layers, Not Just in Controllers

```text
Browser / HTTP client
        │
        │ HTTP headers, Content-Length / Transfer-Encoding, body
        ▼
CDN / API gateway / reverse proxy
        │   - max body size, header limits
        │   - rate/connection/time limits
        │   - authentication, WAF, host validation
        ▼
Embedded server
  Tomcat / Jetty / Undertow / Reactor Netty
        │   - HTTP request line/header decoder limits
        │   - form parser / multipart limits / connection budget
        ▼
Spring Web MVC or WebFlux
        │   - Servlet MultipartResolver or Reactive PartReader
        │   - HttpMessageConverter / HttpMessageReader / Decoder
        │   - @RequestBody, @RequestPart, @RequestParam
        ▼
Controller / Application service
        │   - business max payload, count, schema, byte quota
        │   - file storage, antivirus, transaction, temp cleanup
        ▼
Database / Object storage / downstream
```

**The effective limit is usually the smallest one along the path**, while the error format and status depend on **the first layer that detects the violation**. For example:
- Gateway rejects an oversized body → request **never reaches Spring Boot**.
- Tomcat rejects headers before parsing the request → `@ControllerAdvice` cannot produce your app's JSON error.
- Multipart parser rejects a large file → the controller method may never be invoked.
- WebFlux decoder throws `DataBufferLimitException` → the request reached the web layer, though error mapping depends on configuration.
- Business service rejects a JSON array of 100,000 items → the decoder may have already allocated the whole JSON graph before the service checks it.

**Never rely on a single limit.** Coordinate edge/proxy, server parsers, framework codecs, business validation, disk quotas, concurrent request caps, and timeouts. Any layer can consume significant resources before a downstream layer rejects the request.

## 3. Property Selection Table in Spring Boot 3.3

| Scope | Property / API | Stack | What It Actually Limits |
|---|---|---|---|
| HTTP request headers | `server.max-http-request-header-size` | Tomcat/Netty/embedded server | Header parsing; semantics differ by server |
| HTTP initial line | `server.netty.max-initial-line-length` | Reactor Netty | Request line length |
| Form body | `server.tomcat.max-http-form-post-size` | Tomcat | POST form content parsed by Tomcat; **not a general JSON body limit** |
| Multipart file | `spring.servlet.multipart.max-file-size` | Spring MVC Servlet | Size of each uploaded file |
| Multipart request | `spring.servlet.multipart.max-request-size` | Spring MVC Servlet | Total multipart request size |
| Multipart disk threshold | `spring.servlet.multipart.file-size-threshold` | Spring MVC Servlet | Threshold to spill to disk instead of memory |
| Multipart temp location | `spring.servlet.multipart.location` | Spring MVC Servlet | Intermediate storage path |
| Multipart part count | `server.tomcat.max-part-count` | Tomcat on Boot 3.3 | Number of parts in `multipart/form-data` |
| Multipart part header | `server.tomcat.max-part-header-size` | Tomcat on Boot 3.3 | Header size per multipart part |
| Swallow after rejection | `server.tomcat.max-swallow-size` | Tomcat | Body bytes Tomcat continues draining/discarding after aborting |
| Codec aggregation | `spring.codec.max-in-memory-size` | Auto-configured WebFlux/WebClient | Bytes buffered by decoder/message reader |
| Reactive multipart in-memory | `spring.webflux.multipart.max-in-memory-size` | WebFlux | Non-file part max; file-part disk-spill threshold |
| Reactive multipart disk | `spring.webflux.multipart.max-disk-usage-per-part` | WebFlux | Max disk per spooled file part |
| Reactive multipart count | `spring.webflux.multipart.max-parts` | WebFlux | Number of parts in one multipart request |
| Reactive per-part headers | `spring.webflux.multipart.max-headers-size` | WebFlux | Memory for headers of each multipart part |
| Reactive temp directory | `spring.webflux.multipart.file-storage-directory` | WebFlux | Temp disk directory for the part reader |
| Raw streamed body | `DataBufferUtils.join(buffers, maxByteCount)` or streaming quota | WebFlux | Explicit limit enforced in code; requires release handling |
| Raw Servlet input | Read `ServletInputStream` counting bytes, reject promptly | MVC | Route-specific limit, does not replace container-wide caps |
| Proxy inbound body | `client_max_body_size` (NGINX) | Proxy | Total body accepted by proxy per config |

Application properties in the table follow **Spring Boot 3.3 Common Application Properties**—do not copy Boot 4.x names verbatim without checking. Some defaults differ across servers and versions. **Always verify auto-configuration conditions and the actual server type** before assuming a property takes effect.

## 4. Key Defaults—and What They Do NOT Mean

In Spring Boot **3.3**, notable documented defaults include:

| Property | Default in Boot 3.3 | Notes |
|---|---|---|
| `spring.servlet.multipart.max-file-size` | `1MB` | Per-file limit in Servlet multipart |
| `spring.servlet.multipart.max-request-size` | `10MB` | Total Servlet multipart request |
| `spring.servlet.multipart.file-size-threshold` | `0B` | Typically writes file parts to disk rather than retaining in memory |
| `server.max-http-request-header-size` | `8KB` | Tomcat sums request line + all headers; Netty applies per header per Boot docs |
| `server.tomcat.max-http-form-post-size` | `2MB` | Tomcat POST form parsing |
| `server.tomcat.max-swallow-size` | `2MB` | Swallowing body after abort; not max allowed body |
| `server.tomcat.max-part-count` | `10` | Multipart part count |
| `server.tomcat.max-part-header-size` | `512B` | Per-part header limit |
| `spring.webflux.multipart.max-in-memory-size` | `256KB` | Non-file part limit / file spool threshold |
| `spring.webflux.multipart.max-headers-size` | `10KB` | Per-reactive-part header size |
| `spring.webflux.multipart.max-disk-usage-per-part` | `-1B` | **No per-part disk limit by default** |
| `spring.webflux.multipart.max-parts` | `-1` | **No part count limit by default** |
| `spring.codec.max-in-memory-size` | Unset in Boot | Most codecs default individually to **256KiB** |
| `server.netty.max-initial-line-length` | `4KB` | Request initial line only |

**Unit note:** Spring Boot `DataSize` accepts `KB`, `MB`, `GB`, so pay attention to byte units when comparing. In this lesson we use `64KB` and `128KB` in Boot properties, and `64 * 1024` bytes when counting raw streams in code. Never compare a Java `String.length()` (UTF-16 code units) directly with byte `Content-Length` without UTF-8 encoding.

**Do not assume defaults carry across servers:** Tomcat limits do not apply to Reactor Netty, Jetty, or Undertow. Conversely, `spring.webflux.multipart.*` does not modify Tomcat's `MultipartConfigElement`.

## 5. Distinguishing "Whole Body" Size from "Single Part" Size

An HTTP request can carry different body formats:

```http
POST /api/objects HTTP/1.1
Content-Type: application/json

{"name":"abc","description":"..."}
```

```http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="file"; filename="photo.jpg"
Content-Type: image/jpeg

<binary bytes>
--abc123--
```

For multipart:
- **Total request size** includes boundaries, part headers, form fields, files, and framing.
- **File size** is the bytes of an individual file payload alone.
- **Per-part header size** counts headers like `Content-Disposition` and `Content-Type` inside a part, **distinct from outer HTTP request headers**.
- **Max parts** counts items in the request, not total byte size.
- **In-memory threshold** determines when a file spills to disk, not whether large files are rejected.
- **Disk quota** caps spooled disk usage; if left unconfigured, concurrent large uploads can fill temp disk even while heap remains free.

Example: `max-file-size=64KB` and `max-request-size=128KB` does not guarantee "two 64KB files are always allowed", because multipart boundaries and part headers push the total request past 128KB. To guarantee two files fit, budget total size with appropriate overhead and test with real clients.

**`application/x-www-form-urlencoded` forms are not multipart.** Tomcat's `server.tomcat.max-http-form-post-size` applies to container POST form parsing, not as a uniform cap on JSON, XML, or octet-stream payloads.

## 6. HTTP Request Headers: Parser Limits Fire Before the Controller

A request can carry:
- `Authorization: Bearer ...` or large cookies.
- `Cookie: ...` containing many login/tracking values.
- `X-Forwarded-*` added by reverse proxies.
- Custom tracing/baggage headers.
- A very long URL/query string.
- Repeated header names/values or unusual framing.

Spring Boot 3.3 property:

```properties
server.max-http-request-header-size=8KB
```

**Server semantics differ:** Boot documentation notes Tomcat applies the limit to **the sum of the request line + all header names and values**, whereas Netty applies the limit individually per header. Thus the same `8KB` does not guarantee both servers accept or reject the same multi-header request. Whenever sending large cookies or many headers, test on the exact server implementation and version.

Netty also has:

```properties
server.netty.max-initial-line-length=4KB
```

This applies to the request initial line, **not the payload body**. HTTP/2 and HTTP/3 encode headers differently from HTTP/1.1, so parser and intermediary behavior can differ too.

**When header limits are exceeded:** embedded servers may return `400 Bad Request`, `431 Request Header Fields Too Large`, close the connection, or vary by parser. Never promise a Java `@ExceptionHandler` will always catch it: requests can be rejected **before `DispatcherServlet`/`DispatcherHandler` ever sees them**.

**Do not raise `server.max-http-request-header-size` indefinitely** just because JWTs or cookies are bloating. Check for unnecessary claims/tokens, duplicated headers, proxies appending headers repeatedly, or cookie sprawl. A large header limit multiplied across concurrent connections increases memory and parser overhead.

### 6.1. Outer Request Headers Differ from Multipart Part Headers

```text
HTTP request headers:
  Host, Cookie, Authorization, Content-Type, ...
  limit: server.max-http-request-header-size

Inside multipart body:
  --boundary
  Content-Disposition: form-data; name="file"; filename=...
  Content-Type: application/octet-stream
  [file payload]
  part-header limit: server.tomcat.max-part-header-size
                     or spring.webflux.multipart.max-headers-size
```

With malformed multipart requests, long filenames or oversized part headers can be rejected even when outer HTTP headers are small. **Do not confuse error handling across these two layers.**

## 7. Spring MVC/Tomcat: What Do Multipart and Parser Limits Cover?

With `spring-boot-starter-web`, Spring Boot typically selects MVC + embedded Tomcat. `spring.servlet.multipart.*` configures the Servlet `MultipartConfigElement` and resolver; common controller APIs are `MultipartFile` or Servlet `Part`.

Example configuration:

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.servlet.multipart.file-size-threshold=0B

server.max-http-request-header-size=8KB
server.tomcat.max-part-count=8
server.tomcat.max-part-header-size=1KB
server.tomcat.max-http-form-post-size=256KB
server.tomcat.max-swallow-size=2MB
```

**What each property does:**
- `max-file-size` rejects multipart files exceeding the cap.
- `max-request-size` rejects total multipart uploads exceeding the cap.
- `file-size-threshold` controls temp disk spilling when parsing files.
- `max-part-count` restricts requests with excessive parts.
- `max-part-header-size` blocks oversized per-part headers.
- `max-http-form-post-size` does not cap arbitrary JSON or byte streams.
- `max-swallow-size` only bounds how much body Tomcat **drains/discards** after aborting/rejecting a request so it can handle the connection/response cleanly; it never allows larger valid uploads.
- `server.max-http-request-header-size` limits HTTP request headers before the controller runs.

An oversized upload can trigger `MaxUploadSizeExceededException`, which controller advice can map to HTTP **413**, **though not every failure is guaranteed to reach advice**: containers, proxies, or connection handling may reject earlier. When a client streams a huge body and the server rejects early without swallowing the rest, the client may see a connection reset instead of a JSON error body.

### 7.1. Does Not Automatically Apply to JSON

Example:

```java
@PostMapping("/json")
Map<String, String> json(@RequestBody InputDto input) {
    return Map.of("received", input.message());
}
```

If you only configure `spring.servlet.multipart.max-file-size=64KB`, large JSON requests remain **unprotected by multipart settings**. The HTTP message converter may deserialize the entire payload into an object before your method executes. Enforce edge/gateway body caps, route-specific streaming quotas, or input bounds **before aggregation**.

Do not read `HttpServletRequest.getInputStream()` in a servlet filter and expect to "re-read" `@RequestBody` without a proper wrapper: you will exhaust the stream, break decoding, or introduce unbounded buffering. For a simple binary endpoint, counting bytes while reading inside the controller is a clean illustration.

## 8. Runnable Project A: Spring MVC with Multipart and Raw Body Limits

This Java 17 / Boot 3.3.13 example provides:
- `POST /api/raw`: reads `application/octet-stream` directly from the input stream, **enforcing a 64 KiB cap on actual bytes read** rather than trusting `Content-Length`.
- `POST /api/upload`: accepts a `MultipartFile` enforced by the Servlet parser at 64 KB/file and 128 KB/request.
- `GET /api/ping`: minimal endpoint to test header parsing.
- `@RestControllerAdvice`: returns `ProblemDetail` HTTP 413 for code-detected body limits and `MaxUploadSizeExceededException` reaching MVC.

### 8.1. Project Structure

```text
mvc-limit-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/mvclimits/MvcLimitApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/mvclimits/MvcLimitIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.servlet.multipart.file-size-threshold=0B

server.max-http-request-header-size=8KB
server.tomcat.max-part-count=8
server.tomcat.max-part-header-size=1KB

# Form parsing, NOT a JSON body cap:
server.tomcat.max-http-form-post-size=256KB

# Swallow after request rejection; NOT max accepted body:
server.tomcat.max-swallow-size=2MB
```

**`src/main/java/com/example/mvclimits/MvcLimitApplication.java`:**

```java
package com.example.mvclimits;

import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class MvcLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcLimitApplication.class, args);
    }
}

@RestController
class MvcLimitController {

    private static final long MAX_RAW_BYTES = 64L * 1024;

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @PostMapping(
            path = "/api/raw",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    Map<String, Long> raw(HttpServletRequest request)
            throws IOException {

        // Read in 8 KiB chunks without aggregating the whole body.
        byte[] chunk = new byte[8192];
        long total = 0;

        try (InputStream input = request.getInputStream()) {
            int n;
            while ((n = input.read(chunk)) != -1) {
                if (total > MAX_RAW_BYTES - n) {
                    throw new RawBodyTooLargeException(
                            "Raw body exceeds 64 KiB");
                }
                total += n;
            }
        }

        return Map.of("bytes", total);
    }

    @PostMapping(
            path = "/api/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Long> upload(
            @RequestParam("file") MultipartFile file) {

        // Demo inspects size only, does not store the file.
        return Map.of("bytes", file.getSize());
    }
}

@RestControllerAdvice
class MvcLimitAdvice {

    @ExceptionHandler(RawBodyTooLargeException.class)
    ResponseEntity<ProblemDetail> rawTooLarge(
            RawBodyTooLargeException exception) {
        return response413("Raw body exceeds 64 KiB");
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> multipartTooLarge(
            MaxUploadSizeExceededException exception) {
        return response413("Multipart upload exceeds configured limits");
    }

    private ResponseEntity<ProblemDetail> response413(String detail) {
        ProblemDetail problem = ProblemDetail.forStatus(413);
        problem.setTitle("Payload Too Large");
        problem.setDetail(detail);
        return ResponseEntity.status(413).body(problem);
    }
}

class RawBodyTooLargeException extends RuntimeException {
    RawBodyTooLargeException(String message) {
        super(message);
    }
}
```

**Why this code is valid and properly scoped:**
- One top-level `public class` matching the filename, with package-private classes and exception in the same package.
- Never calls both `request.getReader()` and `getInputStream()`; the raw endpoint has a single consumer.
- `read(chunk)` counts exact bytes rather than `String.length()`. Even when `Content-Length` is missing or wrong (e.g., chunked requests), the loop halts past 64 KiB.
- Checking `total > MAX_RAW_BYTES - n` avoids integer overflow and detects excess bytes before accepting them.
- Raw reading allocates only an 8 KiB chunk rather than a file-sized `byte[]`. However, this is **not a generic cap for all `@RequestBody` endpoints**; it only guards `/api/raw`, which streams manually.
- `MultipartFile` is managed by the Servlet multipart parser; `getSize()` reads metadata without calling `getBytes()` to copy the whole upload into heap.
- `MaxUploadSizeExceededException` can normally be mapped to 413, yet do not expect advice to handle requests rejected earlier by a proxy or container.
- Temp files created by the parser belong to the framework/container; if the app copies uploads to staging files, clean them up on completion, error, and cancellation.

### 8.2. Run and Curl Commands

With JDK 17+ and a Boot 3.3-compatible Gradle:

```bash
gradle bootRun
```

If using the wrapper: `./gradlew bootRun` (Linux/macOS) or `.\gradlew.bat bootRun` (PowerShell).

Create 32 KiB and 80 KiB files on Linux/macOS:

```bash
head -c 32768 /dev/zero > small.bin
head -c 81920 /dev/zero > large.bin
```

**Send small raw payload (valid body):**

```bash
curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @small.bin \
  http://localhost:8080/api/raw
```

**Expected** response: HTTP 200, JSON:

```json
{"bytes":32768}
```

**Send large raw payload (route-specific limit):**

```bash
curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @large.bin \
  http://localhost:8080/api/raw
```

Target is HTTP **413** with `ProblemDetail`; if a proxy/container closes the connection once the app stops reading, some clients may observe a connection reset depending on how they send. On a local test where the request body transmits completely, error mapping is expected to return 413.

**Send small multipart file:**

```bash
curl -i -F 'file=@small.bin' \
  http://localhost:8080/api/upload
```

Expected HTTP 200, JSON `{"bytes":32768}`. You can also test `large.bin` (80 KiB) with `-F`; Servlet multipart's **64 KB/file** cap rejects it even though total request size is under 128 KB.

**Do not use `-d @small.bin` for raw binary tests** when preserving exact bytes; `--data-binary` is the right flag. Never send secrets or sensitive files into demo services.

## 9. MVC Integration Tests Over Real HTTP

These tests separate two limits: **code-counted raw body quota** vs **Servlet-parser multipart quota**. They use `java.net.http.HttpClient` without MockWebServer. For multipart, they send real HTTP wire format instead of `MockMultipartFile`, because plain `MockMvc` does not prove the container enforces limits.

**`src/test/java/com/example/mvclimits/MvcLimitIntegrationTest.java`:**

```java
package com.example.mvclimits;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcLimitIntegrationTest {

    @LocalServerPort
    int port;

    HttpClient client = HttpClient.newHttpClient();

    String uri(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    HttpResponse<String> postRaw(byte[] body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(uri("/api/raw")))
                .header("Content-Type", "application/octet-stream")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    byte[] multipartBody(int fileSize) throws Exception {
        String boundary = "DemoBoundary123";
        String prefix = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; "
                + "filename=\"file.bin\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n";
        String suffix = "\r\n--" + boundary + "--\r\n";

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(prefix.getBytes(StandardCharsets.UTF_8));

        byte[] file = new byte[fileSize];
        Arrays.fill(file, (byte) 'a');
        out.write(file);
        out.write(suffix.getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }

    @Test
    void rawWithinLimit() throws Exception {
        HttpResponse<String> response = postRaw(new byte[32768]);
        assertEquals(200, response.statusCode());
        assertEquals("{\"bytes\":32768}", response.body());
    }

    @Test
    void rawOverLimit() throws Exception {
        HttpResponse<String> response = postRaw(new byte[81920]);
        assertEquals(413, response.statusCode());
    }

    @Test
    void multipartSmallFileIsAccepted() throws Exception {
        String boundary = "DemoBoundary123";
        byte[] body = multipartBody(4096);

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(uri("/api/upload")))
                .header("Content-Type",
                        "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("{\"bytes\":4096}", response.body());
    }
}
```

Run:

```bash
gradle test
```

**Expected:** all three tests pass in a properly configured Boot/Tomcat environment. This is an **expectation derived from the code and contract, not claimed Gradle output**. Here Jackson serializes a single-key `Map.of("bytes", value)` making exact string checks straightforward; adding fields/handlers alters output, so real tests should validate parsed schema rather than raw bytes.

Oversized multipart tests need special care:
- Sending a file >64 KB can raise `MaxUploadSizeExceededException`, mapped by Spring MVC to 413.
- Yet the HTTP transport, proxy, or Tomcat may reject early while the client is still uploading, resulting in a connection reset, 400, or 413 depending on path. Do not write production tests insisting on one exact error body across every server.
- Better to assert "the file is rejected and not saved" while verifying exact status/transport behavior in your target integration environment.

## 10. Codec Buffering in WebFlux: What Happens When Reading JSON?

In Spring WebFlux, HTTP input flows through `HttpMessageReader`/`Decoder` components on `ServerCodecConfigurer`; whenever a codec must aggregate input to construct an object, it buffers. Spring Boot 3.3 offers:

```properties
spring.codec.max-in-memory-size=32KB
```

Boot documentation emphasizes this applies to **auto-configured WebFlux servers and `WebClient` instances**. When unset, many codecs enforce their own **256 KiB** default.

**It does not mean "max total HTTP body is 32 KB".** Examples:

- `@RequestBody Mono<MyDto>`: a single large JSON object must be aggregated in the decoder and can breach the cap → typically `DataBufferLimitException` or related decode failure.
- `@RequestBody Mono<String>`: must aggregate the string → subject to the memory cap.
- `@RequestBody Mono<byte[]>`: decoder aggregates a byte array → subject to the cap.
- Streaming `Flux<MyDto>` from NDJSON: decoded item by item; the cap applies **per object**, not to total infinite stream bytes.
- `@RequestBody Flux<DataBuffer>`: the app receives raw chunks **without mandatory aggregation**, so a 100 MB request can still pass through unless you add a separate total-byte quota.
- WebFlux `FilePart` uploads: governed by multipart reader settings and can spill to disk; do not assume the 32 KB codec cap blocks files over 32 KB.

**Common mistake:** seeing `DataBufferLimitException: Exceeded limit on max bytes to buffer` and setting `spring.codec.max-in-memory-size=-1` app-wide. `-1` disables the cap on supporting decoders, letting malicious requests exhaust heap or cause OOM. Measure legitimate payloads, adjust only the needed consumer/codec in a bounded way, or switch to streaming for genuinely large data.

### 10.1. Do Not Confuse `WebClient` Inbound Decoders with the WebFlux Server

Because the same Boot property affects both the WebFlux server and **Boot auto-configured `WebClient.Builder`s**, raising `spring.codec.max-in-memory-size` globally also raises buffering for downstream **responses**. If one downstream endpoint streams a 1 GB download, use `Flux<DataBuffer>`/`DataBufferUtils.write` or file/resource streaming rather than `bodyToMono(byte[].class)`.

For a specific `WebClient`, customize via `WebClient.Builder.codecs(...)`, but **do not overwrite all default codecs carelessly**, especially when Boot configured JSON codecs, observations, and SSL connectors. Tune only the client that needs it.

## 11. WebFlux Multipart: Memory Threshold, Disk Usage, and Part Count

Spring Boot 3.3 provides dedicated properties for the **reactive multipart reader**:

```properties
spring.webflux.multipart.max-in-memory-size=16KB
spring.webflux.multipart.max-disk-usage-per-part=128KB
spring.webflux.multipart.max-headers-size=2KB
spring.webflux.multipart.max-parts=3
```

**Exact meanings:**
- `max-in-memory-size`: for **non-file parts** (form fields), exceeding it raises `DataBufferLimitException`; for **file parts**, it is the threshold to **spill contents to disk**.
- `max-disk-usage-per-part`: disk ceiling **per spooled file part**; default `-1` means no per-part limit. Note this is not a global disk quota across all users.
- `max-headers-size`: memory limit for **each multipart part's own headers**, not outer HTTP request headers.
- `max-parts`: maximum number of parts allowed, crucial to stop thousands of tiny fields or parts.
- `file-storage-directory`: temp directory where the framework stores parts exceeding the memory threshold; production needs disk quotas and cleanup policies.
- **`PartEvent` streaming** follows a different path: accepting `Flux<PartEvent>` processes parts directly in an event stream instead of spooling like the non-streaming `FilePart` path. Do not assume non-streaming multipart disk/threshold limits automatically protect custom `PartEvent` streaming code; enforce byte/part/header/total quotas inside your pipeline.

With a 100 KB file, 16 KB threshold, and 128 KB per-part disk cap:
- The 100 KB file **is not blocked by the 16 KB threshold**; the reader spools it to disk.
- Above 128 KB disk quota, the parser rejects it.
- Sending 10 tiny file parts triggers `max-parts=3` rejection.
- A text form field over 16 KB can be rejected by the reader **even with no file attached**.

**Do not treat `FilePart.transferTo(path)` as a way to bypass multipart parser limits.** The file has already passed through the multipart reader before your controller receives `FilePart`. To stream multi-gigabyte uploads end-to-end, consider `Flux<PartEvent>` or raw chunks with explicit byte counters, while carefully handling `DataBuffer` ownership and cancellation.

## 12. Runnable Project B: Spring WebFlux, Codecs, and Raw Body Quotas

Standalone WebFlux project using Java 17+, Boot 3.3.13, Reactor Netty. Endpoints:
- `POST /api/json`: reads a JSON object via decoder, illustrating `spring.codec.max-in-memory-size=32KB`.
- `POST /api/raw`: accepts `Flux<DataBuffer>`, aggregates in app code with a **64 KiB** cap via `DataBufferUtils.join(body, maxByteCount)`, and returns **413** when exceeded.
- `POST /api/upload`: accepts `FilePart`, transfers to a temp staging file, measures bytes, and cleans up staging on success/error/cancel via `Mono.usingWhen`. The multipart reader still enforces `spring.webflux.multipart.*`.
- `GET /api/ping`: tests the HTTP header parser.

### 12.1. Structure

```text
webflux-limit-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivelimits/ReactiveLimitApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivelimits/ReactiveLimitIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081

# HTTP headers: NOT a body limit.
server.max-http-request-header-size=8KB
server.netty.max-initial-line-length=4KB

# Codec aggregation limit: NOT a total body limit.
spring.codec.max-in-memory-size=32KB

# Reactive multipart parser:
spring.webflux.multipart.max-in-memory-size=16KB
spring.webflux.multipart.max-disk-usage-per-part=128KB
spring.webflux.multipart.max-headers-size=2KB
spring.webflux.multipart.max-parts=3
```

Do not add `spring-boot-starter-web` to this second project, since Boot normally selects Servlet/MVC when both `web` and `webflux` starters are present. Using `WebClient` as a client is fine, whereas testing a reactive server requires the reactive stack.

### 12.2. Reactive Controller and Staging File Cleanup

**`src/main/java/com/example/reactivelimits/ReactiveLimitApplication.java`:**

```java
package com.example.reactivelimits;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveLimitApplication.class, args);
    }
}

@RestController
class ReactiveLimitController {

    private static final int MAX_RAW_BYTES = 64 * 1024;

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @PostMapping(
            path = "/api/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<Map<String, String>> json(@RequestBody Mono<Message> body) {
        // Decoder may need to aggregate a single JSON object.
        return body.map(item -> Map.of("received", item.message()));
    }

    @PostMapping(
            path = "/api/raw",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    Mono<ResponseEntity<Map<String, Object>>> raw(
            @RequestBody Flux<DataBuffer> body) {

        // join bounds total aggregated bytes.
        // If exceeded, DataBufferLimitException is emitted.
        return DataBufferUtils.join(body, MAX_RAW_BYTES)
                .map(buffer -> {
                    try {
                        int bytes = buffer.readableByteCount();
                        return ResponseEntity.ok(
                                Map.<String, Object>of("bytes", bytes));
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .onErrorResume(
                        DataBufferLimitException.class,
                        error -> Mono.just(
                                ResponseEntity.status(413).body(
                                        Map.<String, Object>of(
                                                "error", "raw body too large"))));
    }

    @PostMapping(
            path = "/api/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<Map<String, Long>> upload(
            @RequestPart("file") FilePart file) {

        // Creating a staging file is a blocking filesystem operation.
        Mono<Path> staging = Mono.fromCallable(
                        () -> Files.createTempFile(
                                "demo-upload-", ".bin"))
                .subscribeOn(Schedulers.boundedElastic());

        return Mono.usingWhen(
                staging,
                path -> file.transferTo(path)
                        .then(Mono.fromCallable(
                                        () -> Map.of(
                                                "bytes", Files.size(path)))
                                .subscribeOn(Schedulers.boundedElastic())),
                ReactiveLimitController::deleteTemp,
                (path, error) ->
                        ReactiveLimitController.deleteTemp(path),
                ReactiveLimitController::deleteTemp);
    }

    private static Mono<Void> deleteTemp(Path path) {
        return Mono.fromCallable(() -> Files.deleteIfExists(path))
                .subscribeOn(Schedulers.boundedElastic())
                .then();
    }
}

record Message(String message) {}
```

**Key points in the code:**
1. `@RequestBody Mono<Message>` uses WebFlux's JSON decoder. A JSON object exceeding the codec aggregation limit can fail **before `body.map(...)` runs**; do not guess the default HTTP status for decode errors without an explicit error policy.
2. `@RequestBody Flux<DataBuffer>` is a **raw chunk stream**. Without `join(maxByteCount)` or another counter, it does not stop at `spring.codec`'s 32 KB limit.
3. `DataBufferUtils.join(body, MAX_RAW_BYTES)` aggregates with a **64 KiB quota**. When exceeded, it signals `DataBufferLimitException`; Spring Framework releases input buffers on error/cancellation per its API contract.
4. When `join` succeeds, the combined `DataBuffer` is consumed by the app and must be released; `finally { DataBufferUtils.release(buffer); }` prevents pooled memory leaks.
5. `onErrorResume(DataBufferLimitException.class, ...)` is **route-specific error mapping** producing an intentional HTTP 413. It does not catch JSON/multipart errors occurring at other layers.
6. `Mono.usingWhen` creates the staging file, runs the transfer, and deletes the file on **completion, error, and cancellation**. Temp files created by the framework's multipart parser are a separate resource managed by the framework.
7. `Files.createTempFile`, `Files.size`, and `Files.deleteIfExists` are blocking filesystem calls; offloading them to `Schedulers.boundedElastic()` keeps the Reactor Netty event loop unblocked.
8. The demo file **is not kept** after returning metadata. In production, persisting uploads requires validation/scanning, durable storage, safe conditional atomic moves, and staging cleanup before committing.
9. Only one top-level `public` class exists in the file; package-private controller and record in the same package are properly component-scanned.

**Cancellation note:** `Mono.usingWhen` cleans up once the resource has been acquired/observed through the publisher. On real filesystems/hosts, still guard against orphan files from process crashes or power loss: cleanup hooks never run on `kill -9` or power loss. A TTL/quota-based sweeper provides backup protection.

### 12.3. Running and Testing with curl

```bash
gradle bootRun
```

Or `./gradlew bootRun` if the Gradle Wrapper is present.

Reuse `small.bin` and `large.bin` created in Section 8:

```bash
curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @small.bin \
  http://localhost:8081/api/raw

curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @large.bin \
  http://localhost:8081/api/raw
```

- Raw 32 KiB: HTTP 200 and `{"bytes":32768}`.
- Raw 80 KiB: HTTP 413 and `{"error":"raw body too large"}` per the `onErrorResume` handler.

Small multipart upload:

```bash
curl -i -F 'file=@small.bin' \
  http://localhost:8081/api/upload
```

Because `max-in-memory-size` is only a 16 KB spool threshold and disk budget is 128 KB, a 32 KB file **is accepted** (spooled to disk) and returns `{"bytes":32768}`, rather than 413 for "exceeding 16 KB". A 200 KB file is rejected by the parser for exceeding `max-disk-usage-per-part`; verify exact status/body against your runtime and error handling.

**Avoid setting `spring.codec.max-in-memory-size=-1` to "fix" the 80 KB raw upload:** the raw route enforces its own independent 64 KiB cap and will still reject it as designed.

## 13. WebFlux Integration Tests: 64 KiB Is an Application Quota

**`src/test/java/com/example/reactivelimits/ReactiveLimitIntegrationTest.java`:**

```java
package com.example.reactivelimits;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveLimitIntegrationTest {

    @LocalServerPort
    int port;

    HttpClient client = HttpClient.newHttpClient();

    HttpResponse<String> postRaw(int size) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(
                        "http://127.0.0.1:" + port + "/api/raw"))
                .header("Content-Type", "application/octet-stream")
                .POST(HttpRequest.BodyPublishers.ofByteArray(
                        new byte[size]))
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void rawBodyBelowLimitReturns200() throws Exception {
        HttpResponse<String> response = postRaw(16 * 1024);
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"bytes\":16384"));
    }

    @Test
    void rawBodyAboveLimitReturns413() throws Exception {
        HttpResponse<String> response = postRaw(80 * 1024);
        assertEquals(413, response.statusCode());
        assertTrue(response.body().contains("raw body too large"));
    }

    @Test
    void exactly64KiBBelongsToAcceptedBoundary()
            throws Exception {
        HttpResponse<String> response = postRaw(64 * 1024);
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"bytes\":65536"));
    }
}
```

Run:

```bash
gradle test
```

**Expected:** all three tests pass when runtime and dependencies match; this is **inferred from the code, not executed output**. Testing over a real `RANDOM_PORT` HTTP server rather than calling controller methods directly exercises the full `Flux<DataBuffer>` + `DataBufferUtils.join` pipeline. Using `contains` avoids coupling assertions to JSON key ordering or whitespace.

The `exactly64KiB` test clarifies that the **maximum allowed size is 65,536 bytes inclusive**, rather than rejecting at the boundary. In production, add tests for `Transfer-Encoding: chunked`, mismatched `Content-Length`, slow-drip chunks, disconnects, and concurrent requests. Never assert millisecond-exact deadlines based on CI network speed.

## 14. Streaming Multipart with `Flux<PartEvent>`

WebFlux supports `@RequestBody Flux<PartEvent>`, letting you process each multipart part sequentially without materializing a full `MultiValueMap<String, Part>` first.

Spring Framework docs describe:
- `FormPartEvent`: form field event.
- `FilePartEvent`: file part event—multiple events may arrive for large files.
- `PartEvent.isLast()` indicates the final event of a part.
- `windowUntil(PartEvent::isLast)` groups events per part.
- `PartEvent.content()` returns a `DataBuffer` that you must **consume, relay, or release**.

**Conceptual snippet, not a complete program:**

```java
@PostMapping(
        path = "/stream-multipart",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> stream(@RequestBody Flux<PartEvent> events) {
    return events
            .doOnNext(event -> {
                DataBuffer buffer = event.content();
                try {
                    // Illustrative byte observation only.
                    // Production must handle part boundaries and quotas.
                    int count = buffer.readableByteCount();
                } finally {
                    DataBufferUtils.release(buffer);
                }
            })
            .then();
}
```

This snippet illustrates **`DataBuffer` ownership only**; it **does not save files, validate schemas, enforce total bytes, distinguish part types, or constitute a production upload endpoint**. Real usage requires per-part and total-request byte counters, max part limits, filename policies, bounded temp storage, lifecycle cleanup, and tests. Never copy this snippet into a project and assume uploads are safe.

**Never use `collectList()`, a `reduce` holding all buffers/events, or unbounded `DataBufferUtils.join` for multi-GB files**, as that defeats streaming. To write files, use `DataBufferUtils.write(..., Path, ...)` or reactive file I/O per contract, managing close/cancel cleanup, byte quotas, filesystem quotas, and orphan sweepers.

With `Flux<PartEvent>`, non-streaming multipart disk-spool settings may **not apply identically**, so test each parser path rather than relying on `max-disk-usage-per-part` to guard custom streaming handlers.

## 15. Proxy/Ingress: Reject Oversized Bodies Before Consuming JVM Resources

When public traffic enters through NGINX, one protective layer looks like:

```nginx
# Fragment inside NGINX server/location config, not a standalone runnable file.
server {
    listen 443 ssl;
    server_name api.example.test;

    # TLS certificate/key, routing, and other policies must still be configured.
    client_max_body_size 256k;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_request_buffering on;

        # Exact timeouts/headers must match topology.
        proxy_read_timeout 60s;
    }
}
```

This is a **config fragment**, incomplete as a production HTTPS server because it lacks `ssl_certificate`/`ssl_certificate_key`, trusted proxy/header rules, authentication, and network ACLs. Do not deploy it verbatim as a full config.

Explanation:
- `client_max_body_size` caps body size at NGINX; rejected requests receive **413** at the edge before Boot ever sees them.
- `proxy_request_buffering on` makes the proxy buffer the body (in memory or temp disk per config). This shields the backend from slow clients while shifting disk/temp pressure onto NGINX; provision quotas and cleanup for the proxy.
- With `proxy_request_buffering off`, the backend receives streamed body chunks earlier; NGINX still enforces body size when determinable, though chunked/slow-client behavior needs testing.
- Cap **headers and URI lengths** at the edge via NGINX directives too, ensuring edge limits are not arbitrarily looser than the backend.
- If a CDN/gateway sits in front of NGINX, requests may be rejected even earlier; not every 413 comes from Spring Boot.

**When your app truly needs 1 GB uploads:** do not just raise every limit to 1 GB. Prefer direct-to-object-storage pre-signed uploads, resumable/chunked uploads, or a dedicated streaming pipeline with quotas, checksums, malware scanning, timeouts, and cleanup. Then the application handles only lightweight metadata/tokens and keeps heap steady.

## 16. Is `Content-Length` Sufficient to Block Large Requests?

**No.** `Content-Length` can be:
- Completely absent on HTTP requests using chunked transfer encoding.
- Untrusted/spoofed by the client before server validation.
- Rewritten, inspected, or stripped by proxies.
- Unreflective of **decompressed byte count**, when the application accepts compressed request bodies.
- Conflicting with `Transfer-Encoding` in malformed requests; rely on standard-compliant servers/proxies to reject request smuggling.

You can reject early based on `Content-Length` **as an optimization**, yet you **must count actual bytes read** in raw streaming paths to enforce a reliable limit. The MVC demo counts `InputStream.read`; the WebFlux demo uses `DataBufferUtils.join(..., maxByteCount)`. For streaming multi-GB files in production, avoid joining in memory and instead count `DataBuffer.readableByteCount()` directly into a bounded writer.

**Units:** wire body bytes differ from decoded `String`/JSON object sizes and from post-transform/decompressed storage sizes. If clients send gzip and the gateway/app decompresses it, cap both **compressed** and **decompressed** bytes to block decompression bombs. Never assume `Content-Length=100KB` means the app uses only 100 KB of heap.

## 17. Status Codes, Exceptions, and Responses When Limits Trigger

| Error / Condition | Likely HTTP Status | Handling Layer |
|---|---|---|
| App detects raw body exceeding quota | **413** if mapped intentionally | Demo controller/handler |
| Spring MVC multipart over file/request limit | Usually **413** when `MaxUploadSizeExceededException` is handled | Servlet multipart + advice |
| WebFlux `DataBufferLimitException` | Depends on error handler; may be 4xx/5xx if unmapped | Codec/reader/handler |
| HTTP request headers too large | **400/431** or connection close depending on server | HTTP decoder/container |
| URI / request line too long | Often **414/400** depending on parser | HTTP decoder |
| Part count / part headers exceeded | 400/413 or parser-specific error | Multipart parser |
| Gateway `client_max_body_size` exceeded | **413** at gateway | Reverse proxy |
| Insufficient temp disk space | Typically 5xx if unmapped; may drop connection | Filesystem/parser/transfer |
| Valid-sized payload with malformed JSON | Usually **400** with proper error handling | JSON decoder/validation |
| Client disconnects mid-body stream | May have no room left for HTTP response | Transport/cancellation |

**Never guarantee every failure returns an app JSON `ProblemDetail`.** Requests rejected by a proxy or header parser before the controller never reach `@ExceptionHandler`. For uploads rejected early while the client is still transmitting, the client may see a connection reset because the container stops reading an oversized body.

For application-generated error responses, return safe details such as:
- `type` and `title="Payload Too Large"`.
- `status=413`.
- `detail` stating the publicly allowed maximum size per policy.
- Safe correlation ID if supported.
- Never echo raw filenames with paths, Authorization headers, request bodies, or stack traces.

To pinpoint exactly which layer rejected a request, correlate proxy access logs with server logs/metrics. Never guess the culprit property from a status code alone.

## 18. RAM, Direct Memory, Disk, and Concurrent Requests

A small per-request cap **does not mean small total resource usage**. Suppose **1,000 concurrent requests** each buffer **256 KiB**: payload buffers alone consume roughly **250 MiB** of memory, before object graphs, codecs, Netty direct buffers, TLS, thread stacks, and caches. Raising the codec cap to 8 MiB across 1,000 concurrent requests could demand roughly **7.8 GiB** just for those 8 MiB buffers.

This is a **simple back-of-the-envelope calculation**, not a JVM/Netty benchmark. Requests may not all hold peak buffers simultaneously; conversely, copies and overhead can push peak usage even higher.

Disk considerations:
- Servlet `file-size-threshold=0B` sends many uploads to temp files.
- WebFlux `max-in-memory-size` is a spool threshold while per-part disk defaults to **-1 (unlimited)**; concurrent parts can fill disk even when every file satisfies business limits.
- With proxy request buffering, the proxy uses its own temp disk too.
- Containers/Kubernetes enforce `ephemeral-storage` quotas on temp volumes; filling them causes 5xx failures or pod eviction.
- App-created staging files need cleanup on success, exception, cancellation, timeout, and crash recovery (sweeper), separate from framework-managed multipart temp files.

Operate these controls together:
1. Max payload per API/tenant/user.
2. Max concurrent uploads and total in-flight bytes.
3. Bounded temp storage + per-user quotas.
4. Rate limits, connection/request timeouts, and upload duration caps.
5. Heap/direct memory metrics, disk usage, and open file descriptors.
6. Orphan file and failed partial-upload cleanup.
7. Alerts on 413/431/5xx spikes, latency, saturation, and rejections.
8. Load tests and chaos/disconnect tests matching real infrastructure.

**Never enlarge heap to fix a full disk**, and never change `spring.codec.max-in-memory-size` to fix an HTTP header parser error; each limit lives at a different layer.

## 19. `DataBuffer` Ownership, Cancellation, and Retained Memory

In WebFlux, `DataBuffer` may wrap a **pooled reference-counted Netty `ByteBuf`**. When reading `Flux<DataBuffer>` directly, follow ownership and release rules strictly. Spring Framework provides `DataBufferUtils.release`, `DataBufferUtils.join`, `DataBufferUtils.write`, and `doOnDiscard` hooks to manage lifecycles.

**Demo pattern:** `DataBufferUtils.join(body, limit)` handles input buffers per its contract. Upon success, the combined buffer enters `map`, where the app reads `readableByteCount()` and releases it inside `finally`. Wrapping a buffer in an async callback and retaining it after the adapter already released it causes use-after-release errors or memory leaks.

**Do not do this:**

```java
// Pseudocode DO NOT USE:
List<DataBuffer> cached = body.collectList().block();
byte[] all = ...;
```

This is unbounded, calling `block()` on a WebFlux event loop risks thread starvation, buffers may leak without release, and memory scales with total body size. For large files, use a streaming writer with byte and in-flight buffer bounds.

**When forwarding a request body downstream via `WebClient`**, clarify who owns and releases each `DataBuffer` after sending, how cancellation propagates, and retry/replay rules. A consumed `Flux` body cannot safely replay on retries; caching it in RAM just for retries breaks memory budgets.

**Cancellation does not roll back side effects:** when a user closes the browser mid-upload, a staging file or metadata row may already exist. Async cleanup on Publisher cancel handles normal cancellation, whereas process crashes skip cleanup hooks. Monitor orphan files and run reconciliation jobs.

## 20. Common Mistakes When Enforcing Limits

| Symptom | Possible Cause | Fix |
|---|---|---|
| 80 KB multipart rejected despite `max-request-size=128KB` | `max-file-size=64KB` per file is smaller | Align both per-file and total request caps with business rules |
| 20 MB JSON enters MVC despite 1 MB multipart max | Multipart properties do not apply to JSON | Enforce total body cap at edge or route/parser level |
| WebFlux 1 MB JSON throws `DataBufferLimitException` | Codec must aggregate and defaults to ~256 KiB | Bounded codec config or streaming/smaller DTOs |
| WebFlux accepts 100 KB file despite 16 KB memory threshold | Threshold triggers disk spill, not rejection | Configure `max-disk-usage-per-part` and total quotas |
| Uploads fill `/tmp` disk | Missing disk quotas or cleanup for temp spool/app staging | Set per-part + total disk quotas, dedicated temp dir, sweeper |
| Header parser blocks before controller | `server.max-http-request-header-size`/URL cap | Shrink tokens/cookies/proxy headers, test parser; advice won't catch it |
| 8 KB headers work on Tomcat, fail on Netty (or vice versa) | Tomcat sums total vs Netty checks per header | Test against target server and protocol |
| 413 seen at CDN, zero logs in Spring | Request rejected before reaching JVM | Check gateway/CDN access logs and request IDs |
| Raising `server.tomcat.max-swallow-size` still rejects 100 MB file | Swallow cap is not max upload size | Fix multipart quotas and ingress policies |
| Large file gets connection reset instead of 413 `ProblemDetail` | Server rejects early while client is still uploading | Test upload lifecycle, swallow settings, proxy buffering |
| Oversized part headers | `max-part-header-size` / `max-headers-size` | Audit filenames/metadata and cap per-part headers |
| Thousands of tiny multipart fields slow parser | Missing `max-parts` or business field count cap | Enforce part count, schema validation, and rate limits |
| WebFlux raw body >32 KB codec cap still succeeds | Raw `Flux<DataBuffer>` skips codec aggregation | Add explicit byte counter / bounded `join(limit)` |
| 500 KB POST form fails while 500 KB JSON succeeds | Tomcat form-post cap differs from JSON path | Understand each parsing path and policy |
| `WebClient` large download hits codec limit | `bodyToMono(byte[].class)` aggregates response | Stream chunks or raise client-specific decoder cap carefully |
| Setting codec cap to `-1` causes OOM | Removes memory protection | Never disable caps globally; size to payloads and concurrency |
| Seeing 413 without knowing which layer emitted it | Proxy, container, and app can all return 413 | Correlate logs and metrics per hop |
| Upload retries create duplicate files | Missing idempotency keys / commit protocol | Deduplicate/transact and clean up temp artifacts |
| Filename contains `../` or absolute path | Trusting client-supplied filename | Generate server-side IDs, sanitize, never join raw paths |
| Small `Content-Length` yet larger body arrives | Framing/transfer-encoding mismatch or untrusted client | Rely on standard HTTP parsers and always count actual consumed bytes |
| Single slow connection holds memory long-term | Slow upload/drip attack, loose timeouts | Idle/read timeouts, rate/concurrency caps, early rejection |

## 21. Boundary Test Matrix Across Layers

| Layer | Boundary Test | What to Verify |
|---|---|---|
| Proxy body | 255 KiB, 256 KiB, 257 KiB | Proxy enforces configured size, correct status/correlation |
| Tomcat multipart file | 64 KB, 64 KB + 1 | Per-file cap applies independently of total multipart request |
| Tomcat multipart request | Total 128 KB vs >128 KB | Boundary and part-header overhead accounted for |
| Tomcat part count | 8 vs 9 parts | Parser rejects excess parts |
| Tomcat part headers | File header just under/over 1 KB | Parser error distinct from HTTP header limit |
| Raw MVC route | 65,536 vs 65,537 bytes | Counts actual bytes read; `Content-Length` not trusted blindly |
| MVC JSON | Large JSON vs multipart limits | Confirm multipart caps do not lull you into ignoring JSON |
| WebFlux codec | 32 KB JSON object vs >32 KB | `DataBufferLimitException` / error policy works |
| WebFlux raw route | 65,536 vs 65,537 bytes | `join(limit)` boundary and buffer release |
| WebFlux multipart file | 16 KB, 32 KB, 128 KB, >128 KB | Disk spill threshold vs per-part disk quota |
| WebFlux part count | 3 vs 4 parts | Reactive parser enforces limit |
| HTTP headers | Headers/URI below and above 8 KB | Tomcat/Netty/proxy semantics on target runtime |
| Chunked upload | Omit `Content-Length` | Limits still enforce via actual bytes / edge |
| Concurrent large uploads | N clients × near-limit payloads | Heap/direct memory/disk/CPU stay within SLO |
| Mid-upload cancel/disconnect | Abort half-way through | Staging cleanup runs, no descriptor leaks |
| Full temp disk | Exhaust quota mid-upload | Clean error response, pod stays healthy |
| Invalid `Content-Type` | Spoofed multipart/JSON payload | 400/415/parse error without logging raw secrets |
| Compression | Small gzip expanding huge | Enforce both compressed and uncompressed quotas |
| HTTPS/HTTP2 ingress | Vary protocol and route | Header/body limits still enforced |

**Do not rely solely on `MockMvc`** to verify Tomcat multipart, parser, or header limits; `MockMvc` bypasses the real network parser. Use `@SpringBootTest(RANDOM_PORT)` with a real HTTP client like the demo, plus end-to-end tests through your running gateway/ingress.

Likewise, WebFlux `WebTestClient.bindToController(...)` does not exercise Reactor Netty's HTTP header decoder or temp disk spooling. Run network integration tests against the actual embedded server.

## 22. Does Raising Limits Mean the App "Supports Large Files"?

Not yet. Raising one limit simply exposes the next bottleneck:
- Raise file size from 1 MB to 100 MB while proxy body cap stays 10 MB → 413 at the proxy.
- Proxy allows 100 MB while Servlet threshold buffers in RAM → heap/disk pressure.
- WebFlux multipart allows 100 MB disk spool while container `ephemeral-storage` is 50 MB → disk full / pod eviction.
- Raise JSON codec cap to 100 MB → 100 concurrent requests demand multi-GB memory and trigger GC pauses.
- Slow client trickles an HTTP body over 10 minutes → connection exhaustion / Slowloris.
- Backend reads uploaded file into `byte[]` to pass to a scanner/downstream → extra full-size memory copy.
- Upload fails and app skips temp cleanup → disk fills steadily over time.

**A more reliable design for large files:**
1. Define clear business contracts for max file size and batch totals.
2. Use streaming or `PartEvent` with explicit quotas; avoid `getBytes()` on large files.
3. Save into staging/quarantine first—never expose publicly before validation/scanning.
4. Stream checksums/hashes and magic-byte content checks as needed.
5. Use server-generated file IDs/paths; never construct storage paths from client filenames.
6. Use atomic moves/commits where possible; clean up on errors and cancellations.
7. Offload very large payloads to resumable or pre-signed object-storage uploads.
8. Enforce per-tenant quotas, concurrency caps, time budgets, and rate limits.
9. Monitor heap/direct memory, multipart temp disk, failed uploads, rejections, and latency.
10. Test the full path across proxy, container, framework, and DB/object storage—not only controller unit tests.

**Never treat raising size limits as a DoS mitigation.** It widens the attack surface unless paired with quotas and validation.

## 23. Security: Untrusted Resources, Parsers, and Client Input

Request-size controls are also a security boundary, not merely performance tuning. Risks include:
- **Denial of service:** floods of oversized bodies, headers, parts, or cookies exhausting memory, CPU, or disk.
- **Multipart filename traversal:** clients sending `filename="../../etc/passwd"`; never concatenate client filenames directly onto storage paths.
- **MIME spoofing:** `Content-Type: image/png` does not prove valid PNG data; inspect magic bytes and scan malware where required.
- **Decompression bombs:** tiny compressed payloads expanding into massive streams.
- **Request smuggling:** `Content-Length`/`Transfer-Encoding` mismatches between proxy and backend; rely on strict standards-compliant HTTP parsers and never hand-roll framing.
- **Disk exhaustion:** leaked temp files and partial failed uploads.
- **Log injection / PII leaks:** untrusted headers, filenames, or raw bodies containing sensitive data or control characters.
- **Tenant starvation:** User A filling shared disk if only per-file limits exist without per-tenant quotas.

Never trust client-supplied `X-Forwarded-*` headers for IP-based quotas; enforce a trusted proxy boundary. Authentication and authorization remain mandatory for uploads; size limits never replace role or ownership checks. For unauthenticated public uploads, evaluate edge rate limits, abuse prevention, malware scanning, and strict quotas carefully.

A 413 response must never reveal absolute temp paths, SQL, tokens, or internal topology. Redact logs with correlation IDs; keep metric tags to finite enums (endpoint template, status, reason) rather than raw filenames or request URLs.

## 24. Observability: Know Which Limit Was Hit

Suggested telemetry:
- **Counters:** `http.request.rejected` tagged by observable `reason` (`body_size`, `multipart_file_size`, `multipart_parts`, `codec_buffer`, `header_size`).
- **HTTP status distribution:** 413/400/431/5xx by URI template, method, and app vs ingress.
- **Payload histograms:** body bytes / per-file bytes, without storing raw payloads.
- **Resource gauges:** heap, Netty direct memory, temp disk usage/quota, open file descriptors, active uploads, and in-flight bytes.
- **Latency:** parser time, upload time, downstream storage commit time, cleanup duration.
- **Cleanup health:** orphan temp file counts, file age/TTL, storage pressure, and repair job results.

Never put filenames, full URIs, request bodies, or arbitrary user IDs into low-cardinality metric labels. A 413 at the proxy generates no `http.server.requests` metric in the JVM, so combine proxy/CDN logs and metrics. If header parsing fails before Spring runs, the app creates no observation context for that request either.

**Alerting aligned with SLOs:** rising 413s may signal client payload bugs or abuse rather than a server crash. Track rejection rates and breakdowns per endpoint and authenticated tenant instead of paging on every expected 413 as if it were a 5xx.

## 25. Production Rollout Checklist

- [ ] Separated **total body**, **per-file**, **multipart request**, **part count**, **header**, and **codec memory** limits.
- [ ] Used the right properties for MVC Servlet vs WebFlux; never copied settings across stacks.
- [ ] Understood Tomcat `max-http-form-post-size` and `max-swallow-size` **are not max JSON upload limits**.
- [ ] Understood WebFlux `spring.codec.max-in-memory-size` does not cap entire streamed bodies.
- [ ] Enforced max body size at gateway/ingress or via counting filters/handlers on large routes.
- [ ] Checked `Content-Length` policy alongside **counting actual bytes read**, including chunked uploads.
- [ ] Set HTTP header and URL/initial-line caps, verified on target server/version.
- [ ] Configured multipart max file, max request, max parts, per-part headers, and disk quotas.
- [ ] Avoided disabling caps with `-1` without alternative quotas and memory/disk testing.
- [ ] Managed `DataBuffer` ownership and release across completion, errors, and cancellations.
- [ ] Bounded all temp buffers/queues; avoided `collectList()` and unbounded `join()`.
- [ ] Added staging file cleanup and crash-recovery orphan reconciliation.
- [ ] Enforced per-user/tenant quotas, max concurrent uploads, rate limits, timeouts, and slow-client guards.
- [ ] Secured filenames/paths, MIME/content checks, authn/authz, and antivirus scanning where needed.
- [ ] Verified 413/431/400/5xx error mapping and metrics at each layer.
- [ ] Tested with real HTTP clients, through CDN/NGINX/ingress, and under concurrent load.
- [ ] Ensured metrics/logs never leak raw headers, filenames, bodies, tokens, or PII.
- [ ] Measured production payload distributions before raising any limits.

## 26. Self-Check Questions

**1. Does `spring.servlet.multipart.max-file-size=1MB` block a 5 MB JSON payload in MVC?**  
No. It is a multipart file limit, not a JSON body limit.

**2. Why is a 100 KB WebFlux `FilePart` still accepted when `spring.webflux.multipart.max-in-memory-size=16KB`?**  
For file parts, 16 KB is the threshold to spill to disk; per-part disk limits and other quotas determine whether the file is accepted.

**3. Does `server.tomcat.max-swallow-size=2MB` mean Tomcat accepts uploads up to 2 MB?**  
No. It controls how many bytes Tomcat drains/discards after aborting/rejecting a request, affecting whether the client receives the error response cleanly.

**4. Does `server.max-http-request-header-size=8KB` have identical semantics on Tomcat and Netty?**  
No. Per Boot 3.3 docs, Tomcat checks total request line + headers, while Netty checks each header individually. Always test on your exact runtime and protocol.

**5. Does `spring.codec.max-in-memory-size=32KB` block a 100 MB `Flux<DataBuffer>` upload?**  
Not automatically. Raw streaming skips codec aggregation; enforce a total cap with a custom byte counter or bounded `join`.

**6. Does `DataBufferLimitException` always produce HTTP 413?**  
Not by default; status mapping depends on framework and handlers. The raw WebFlux demo explicitly maps it to 413.

**7. Why should you configure `max-parts`?**  
Because a request with thousands of tiny fields or files can overwhelm parser metadata, memory, and disk even when each individual part is small.

**8. Why test multipart uploads over the network instead of only with `MockMultipartFile`?**  
`MockMvc` does not necessarily invoke the Servlet container's real multipart parser, so it cannot prove `max-file-size` or `max-request-size` enforcement.

**9. Is `Content-Length` trustworthy enough to block oversized uploads?**  
No. Chunked requests omit `Content-Length`; always count actual bytes read and rely on standard-compliant parsers.

**10. Should you set every limit to `-1` to avoid errors?**  
No. Removing memory/disk caps exposes the service to OOM crashes and disk exhaustion.

**11. Why might HTTP 413 errors occur in production with no entries in application logs?**  
Because a gateway, CDN, proxy, or container parser rejected the request before it ever reached Spring controllers or observations.

**12. To support 2 GB files, is setting `spring.codec.max-in-memory-size=2GB` the right solution?**  
No. Use streaming/chunked/resumable uploads or pre-signed object storage with explicit body/file/disk/time quotas and cleanup.

## 27. Official References

1. **Spring Boot 3.3 — Common Application Properties**: `spring.servlet.multipart.*`, `spring.webflux.multipart.*`, `spring.codec.max-in-memory-size`, `server.max-http-request-header-size`, `server.tomcat.*`, `server.netty.*`. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
2. **Spring Boot / Spring Guide — Uploading Files**: multipart size settings and file lifecycles in MVC. https://spring.io/guides/gs/uploading-files/
3. **Spring Framework — WebFlux Reactive Core, Limits**: Decoder/`HttpMessageReader` `maxInMemorySize` and multipart behavior. https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
4. **Spring Framework — WebFlux Multipart Content / PartEvent**: streaming parts and requirements to consume, relay, or release `DataBuffer`s. https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
5. **Spring Framework — Data Buffers and Codecs**: `DataBufferUtils.join`, reference counting, ownership, and release. https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
6. **Spring Framework 6.1 — `DefaultPartHttpMessageReader` Javadoc**: `setMaxInMemorySize`, `setMaxDiskUsagePerPart`, `setMaxParts`. https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html
7. **Spring Framework 6.1 — `DataBufferUtils` Javadoc**: `join(Publisher, int maxByteCount)` and release semantics. https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
8. **Apache Tomcat 10.1 — HTTP Connector**: `maxPostSize`, `maxSwallowSize`, `maxHttpRequestHeaderSize`, and request parser. https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
9. **NGINX HTTP Core Module — `client_max_body_size`**: body limits before upstream. https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size
10. **RFC 9110 — HTTP Semantics**: 413 Content Too Large and 431 Request Header Fields Too Large per current specification. https://www.rfc-editor.org/rfc/rfc9110.html

**Conclusion:** In the Spring Boot web runtime, **request bodies**, **multipart uploads**, **HTTP headers**, and **codec buffering** are four separate limits governed by different mechanisms. Servlet multipart is managed by `spring.servlet.multipart.*` and the container; WebFlux uses reactive multipart readers and `spring.codec.max-in-memory-size` for decoding; HTTP headers are parsed by the server/proxy before reaching controllers; and raw streaming is only safe when you explicitly count actual bytes read. Production design requires coordinating gateway, parser, codec, disk/heap quotas, concurrency, timeouts, security, and cleanup—never simply bumping one property until large requests stop failing.