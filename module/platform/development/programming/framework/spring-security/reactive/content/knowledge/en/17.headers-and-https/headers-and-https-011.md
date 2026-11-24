# Header, Request Body, and File Upload Size Limits in WebFlux and Server Layers

> **Parent topic:** Headers and HTTPS in **Spring Security reactive / Spring WebFlux**. This lesson distinguishes limits across the **HTTP server**, **WebFlux codecs**, **multipart parser**, **application business rules**, and **reverse proxies**. Primary examples use **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring Security 6.x, and Reactor Netty**. Some property names in Spring Boot **3.4 and earlier** differ from Boot 3.5; this lesson highlights those changes. The limits in the examples are for learning and are not recommended production defaults.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish limits on **HTTP request line / headers**, **actual body bytes**, **codec decoding buffers**, and **individual multipart files/parts**.
2. Configure `server.max-http-request-header-size` and `server.netty.max-initial-line-length` in Spring Boot 3.5.
3. Use `spring.http.codecs.max-in-memory-size` to cap codec memory usage when aggregating input; understand why it is **not a total size limit for every HTTP body**.
4. Configure `spring.webflux.multipart.max-in-memory-size`, `max-disk-usage-per-part`, `max-parts`, and `max-headers-size`, and understand each threshold.
5. Build a POST endpoint bounding **actual bytes read** via `DataBufferUtils.join(Publisher<DataBuffer>, maxByteCount)`, returning `413 Payload Too Large` when exceeded and releasing `DataBuffer`s properly.
6. Handle `FilePart` uploads safely without using client filenames as storage paths, distinguishing temporary storage from final storage.
7. Explain why `Content-Length` is insufficient to guard against oversized bodies due to chunked transfers, proxies, or post-decompression byte sizes differing from declared headers.
8. Keep **Spring Security WebFlux** authentication/authorization/CSRF active and test application limits with `WebTestClient`.
9. Recognize statuses you may encounter (`400`, `401`, `403`, `413`, `414`, `415`, `431`, `5xx`) and situations where the server closes the connection before WebFlux is invoked.
10. Design multi-layer limits across the **TLS terminator, ingress/reverse proxy, server decoder, codecs, multipart reader, and service/storage quotas** to mitigate overload/DoS.

## 2. One Phrase "Request Size" Has Multiple Meanings

Limits across a WebFlux stack do not replace one another.

| Layer | Example limit | Scope and effect | Does not guarantee |
| --- | --- | --- | --- |
| HTTP server decoder | Request line, header field length/size | Blocks abnormal requests **before** WebFlux controllers run | Does not cap total body bytes |
| WebFlux codec | `max-in-memory-size` | Stops **buffering input** beyond the threshold for aggregating codecs/readers | Not a universal quota for streamed files or all bodies |
| WebFlux multipart parser | Non-file part buffer, file spill threshold, disk per part, part count, part headers | Bounds resources while parsing `multipart/form-data` | Does not replace a whole-request multipart limit across all parts |
| Application endpoint | `MAX_RAW_BYTES`, `MAX_FILES`, `MAX_USER_QUOTA` | Size rules for resources **actually processed** | Cannot save the server if parser/proxy exhausts resources earlier |
| Ingress/reverse proxy | Request body, URL/header, connections/bandwidth/timeouts | Rejects early before the app, reducing upstream cost | Does not enforce business quotas if app config is wrong |
| Security | Authentication, authorization, CSRF, rate limits | Who may send requests and how often | Does not cap payload sizes on its own |
| Storage | Total file size, file count, retention, disk quota | Prevents disk exhaustion and runaway costs | Does not stop oversized HTTP headers |

**Core principle:** A request can have **valid headers yet a huge body**, or a massive file can stream **without filling codec buffers** while still filling up disk. Therefore, enforce bounds at every layer.

### 2.1 The Critical Trio of Limits

1. **Header budget:** how many bytes are permitted in header fields and the request line (details depend on server/protocol).
2. **Memory aggregation budget:** how many bytes a codec may buffer to decode an object or form value.
3. **Body/file budget:** maximum payload bytes accepted **in total** and per upload, including streaming or requests omitting `Content-Length`.

Never mistake the 256 KB default codec buffer for "the API only accepts files under 256 KB." With multipart uploads, **file parts larger than the threshold** typically spill to temporary disk rather than being rejected at 256 KB.

## 3. Request Path and Where Limits Apply

```text
Browser / curl / service client
        |
        | HTTPS request (headers + body)
        v
TLS terminator / CDN / ingress
        |  - limits URL, headers, body bytes, rate, timeouts
        |  - may return 413/431/400 before request reaches backend
        v
Reactor Netty HTTP decoder
        |  - request line, HTTP headers, validation
        |  - if exceeded: request may be rejected or connection closed
        v
Spring WebFlux WebFilter pipeline
        |
        +-- Spring Security WebFilterChain
        |       - authentication, authorization, CSRF
        |       - unauthorized users rejected before business handlers
        |
        +-- Handler / codec / multipart reader
        |       - decoded form/JSON memory budget
        |       - multipart per-part disk & count limits
        |       - body aggregation and DataBuffer lifecycle
        |
        +-- Application rules / quotas
        |       - total body bytes, file type, owner, tenant,
        |         max uploads/user, object storage, virus scanning
        v
Service / storage
```

**Never rely on a single layer.** A proxy sets `client_max_body_size`, yet staging tests bypass the proxy? Calling the backend directly can accept payloads you thought were blocked. Conversely, an app uses `DataBufferUtils.join(..., 1024)` while a massive HTTP request header still consumes resources **before reaching the endpoint**; configure the server/gateway too.

### 3.1 When HTTPS Terminates at a Proxy

With TLS offloading, browsers connect via **HTTPS to the proxy**, while the Netty app may receive internal HTTP. Limits for TLS handshakes, header compression, body bytes, and connections must be enforced at **the layer receiving that traffic**. The backend still needs its own caps in case of internal callers or ingress config changes.

Never conclude "we have HTTPS so large bodies can't cause DoS"; HTTPS protects transit confidentiality and integrity—it **does not** replace size limits, rate limiting, timeouts, or disk quotas.

## 4. HTTP Request Header and Request Line Limits in Spring Boot/Netty

In a Spring Boot 3.5 app running Reactor Netty, you can set:

```yaml
server:
  max-http-request-header-size: 8KB
  netty:
    max-initial-line-length: 4KB
```

**Meaning of each property:**

- `server.max-http-request-header-size` bounds request headers in the embedded server; **default is typically 8 KB** in Spring Boot 3.5. Whether this means "total" or "per header" **depends on the web server**. Spring Boot 3.5 docs explicitly note: **Netty applies the threshold to each individual header**, whereas Tomcat accounts for the request line and combined headers differently. Therefore, never claim Netty's 8 KB limit is always the sum across all fields.
- `server.netty.max-initial-line-length` caps the HTTP/1.1 **request initial line** (method, request target, HTTP version), defaulting e.g. to 4 KB. This differs from total URL limits a gateway/CDN may apply.
- HTTP/2 uses header framing/compression and separate controls; never assume thresholds across all servers and protocols match HTTP/1.1. Test against your exact Reactor Netty version, HTTP/1.1 vs. HTTP/2, and production ingress.

### 4.1 Where Do Oversized Request Headers Come From?

Common sources:

- `Authorization: Bearer <JWT>` stuffed with excessive claims, nested permissions, or bloated token strings.
- `Cookie` carrying too many session/tracking cookies combined by the browser into one huge header.
- `X-Forwarded-*` / trace headers or custom metadata repeated across proxies.
- Filenames/metadata misplaced into custom headers where clients send very long strings.
- Abnormal hosts/request targets, duplicate/conflicting `Content-Length`, folded/invalid headers, or attackers sending many header names.

Do not reflexively bump header limits to 64 KB so JWTs/cookies can bloat indefinitely. First shrink tokens/claims, prune unnecessary cookies, review proxy impact, and restrict client headers. Headers carrying tokens or cookies are sensitive: **never enable logging of raw `Authorization`/`Cookie` when debugging size limits**.

### 4.2 Request Line Limits Are Not Body Limits

`GET /api/search?filter=...` with a 10 KB query can be rejected by the decoder before reaching WebFlux. Yet `POST /api/search` with a 10 MB JSON body has a short request line and is unaffected by `server.netty.max-initial-line-length`. Bound each dimension at the appropriate layer.

Never stuff PII, access tokens, or large document payloads into query strings just to dodge body limits. URLs commonly appear in browser history, access logs, proxies, and telemetry.

### 4.3 What Happens When Headers Exceed the Limit?

HTTP defines `431 Request Header Fields Too Large` (RFC 6585), `414 URI Too Long`, and `400 Bad Request`, and servers may reject or close connections before WebFlux dispatches.

There is **no guarantee** Reactor Netty always returns 431 when a header exceeds configuration. The decoder may throw an exception, close the connection, or emit a status varying by version/protocol/proxy. Because this happens **before application WebFilters run**, `@RestControllerAdvice` or `ServerAuthenticationEntryPoint` cannot always turn it into a neat JSON error.

**Testing rule:** verify the request is blocked and app resources stay protected; do not hardcode 431 if real environments sometimes return 400 or transport errors.

### 4.4 Can You Configure Reactor Netty Directly?

When decoder tuning beyond Boot properties is needed, Reactor Netty offers `HttpServer.httpRequestDecoder(...)`, for example:

```java
// Alternative snippet when Netty-specific tuning is genuinely needed.
@Bean
WebServerFactoryCustomizer<NettyReactiveWebServerFactory> nettyDecoder() {
    return factory -> factory.addServerCustomizers(
        httpServer -> httpServer.httpRequestDecoder(decoder ->
            decoder.maxHeaderSize(8192)
                   .maxInitialLineLength(4096)
                   .validateHeaders(true)
        )
    );
}
```

This is a **snippet inside `@Configuration`**, requiring imports:

```java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.context.annotation.Bean;
```

Code targets Boot 3.x + Reactor Netty 1.x. If you already set the corresponding Boot properties, **do not also declare a customizer with conflicting values** to avoid ordering ambiguity. Never mistake `maxHeaderSize` for a total body limit; Netty's legacy `maxChunkSize` is a decoder chunk setting (deprecated in some versions), **not a replacement for upload quotas**.

## 5. WebFlux Codec In-Memory Limits

Certain `Decoder` / `HttpMessageReader` implementations must **buffer bytes in memory** before producing an object—e.g., JSON with long strings/tokens, URL-encoded forms, `@RequestBody byte[]`, or splitting records from a stream.

In **Spring Boot 3.5.x**, the standard property is:

```yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
```

**Version detail:** In **Spring Boot 3.4.x and earlier 3.x**, the equivalent property is named `spring.codec.max-in-memory-size`. Starting in Boot **3.5**, *Common Application Properties* uses `spring.http.codecs.max-in-memory-size`. Check the exact properties appendix for your running version; never blindly set both names assuming both apply.

### 5.1 What Exactly Does This Limit Apply To?

The WebFlux codec limit caps **decoding buffers**, not "abort any body as soon as total bytes > 256 KB." Depending on the reader/decoder:

- For a single buffered JSON object, the limit applies to the bytes aggregated for parsing.
- For `application/x-www-form-urlencoded`, form payloads are aggregated.
- For a `Flux<Pojo>` stream of separate JSON objects, the limit may apply **per object/token**, not across all objects combined.
- For `Flux<DataBuffer>` reading raw bytes directly, the framework can forward chunks without aggregating into one whole-request buffer; **you must bound total bytes separately** if the endpoint requires it.
- For multipart requests, file parts can spill to disk rather than being capped by `max-in-memory-size`; see the multipart section.

### 5.2 DataBufferLimitException

When codec/buffer aggregation exceeds its threshold, Spring Framework throws `DataBufferLimitException`. This signals that the byte limit for **an aggregation/decoding operation** was exceeded. Do not assume a single fixed HTTP status: depending on where it is thrown, it may be wrapped into an input-processing exception or reach framework error handling.

For public APIs, map **genuinely identified size exceptions** to `413 Payload Too Large` with a generic message. Avoid catching every `Exception` and returning 413, which hides server bugs or permission errors.

### 5.3 Is Raising max-in-memory-size the Way to Fix File Uploads?

Usually **no**. Bumping `max-in-memory-size` to `100MB` lets a single large request exert extreme RAM pressure, especially under concurrency. For file uploads, use streaming/spooling with file-specific limits; never buffer entire files into `byte[]` or `String`.

Quick cost estimate: if 50 concurrent requests each buffer 8 MB, buffers alone consume roughly 400 MB, before counting Java objects, framework overhead, and heap fragmentation. Numbers are illustrative estimates; benchmark realistically and set concurrency/rate limits and container memory budgets.

## 6. Bounding Actual Body Bytes: Content-Length Is Not Enough

`Content-Length` is **client-supplied metadata**. It helps reject **early** when present and over limit, yet **is never sufficient as the sole enforcement mechanism**:

- Clients can send `Transfer-Encoding: chunked` without `Content-Length`.
- Proxies can alter body framing and headers.
- Decompressed byte counts can differ from wire byte counts.
- Clients can send forged lengths or conflicting headers; HTTP decoders/proxies handle anomalies differently.
- Streaming endpoints receive data over time without knowing final size from initial headers.
- Multiple file parts combined can exceed a total budget even if every individual part is under limit.

To **cap total payload at the application**, count or limit **actual bytes read by the consumer**; to stop huge payloads early, also configure limits at the ingress/server.

### 6.1 A Small Java Mental Model for "Size Limits"

Consider two requests:

```http
POST /api/raw HTTP/1.1
Content-Type: application/octet-stream
Content-Length: 100
```

and

```http
POST /api/raw HTTP/1.1
Transfer-Encoding: chunked
Content-Type: application/octet-stream
```

These are **HTTP header excerpts only**, lacking bodies or chunk framing and not complete copy-paste raw requests. Both can deliver a 100-byte payload. A filter checking only `Content-Length` misses the chunked case. A consumer bounding bytes while reading the body enforces limits on **both**.

### 6.2 When to Use DataBufferUtils.join(body, maxByteCount)?

`DataBufferUtils.join(Publisher<DataBuffer>, int maxByteCount)` aggregates `DataBuffer`s into one composite buffer **up to the specified byte maximum**; if exceeded, it emits `DataBufferLimitException`. It releases accumulated buffers on error/cancellation. Upon successful join, the caller owns the composite buffer and must **release it after reading**.

This technique suits **small request bodies** that the app must read as a whole, such as budgets of 1 KiB, 32 KiB, or a few MB. It is **not suitable for multi-GB files**, since all permitted bytes still accumulate into one aggregated buffer. For large files, stream chunks, count bytes, spool to disk/object storage, and enforce quotas.

### 6.3 Do Not Misuse DataBuffer

Netty typically uses pooled/reference-counted buffers. If consuming `DataBuffer` manually, never leak them; when handled by normal WebFlux codecs, the framework manages their lifecycle. When calling `DataBufferUtils.join` directly, release the result after reading; never release before reading or retain references across untracked async callbacks.

**Proper pattern:**

```java
return DataBufferUtils.join(request.getBody(), MAX_BYTES)
    .map(buffer -> {
        try {
            return buffer.readableByteCount();
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    });
```

This is a **snippet inside a body-handling method** using `ServerHttpRequest request` and constant `MAX_BYTES`, not a standalone file. When the body exceeds the limit, `join` emits an error; endpoint error mapping can turn it into 413. A full runnable project follows below.

## 7. Multipart Uploads in Spring WebFlux: Multiple Distinct Thresholds

Spring Boot 3.5 provides dedicated properties for WebFlux multipart:

```yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 4MB
      max-headers-size: 8KB
      max-parts: 3
```

**Each property has distinct semantics:**

| Property | Meaning | What it does NOT mean |
| --- | --- | --- |
| `max-in-memory-size` | Memory budget for **non-file parts**, and the threshold where file parts **spill to temporary disk** | Files larger than 64 KB are always rejected |
| `max-disk-usage-per-part` | Maximum disk space **per spooled file part** | Whole request total ≤ 4 MB |
| `max-headers-size` | Memory cap for headers **of each multipart part** | Outer HTTP request headers are bounded by this property |
| `max-parts` | Maximum number of parts in a multipart request | Byte size per part or whole request |
| `file-storage-directory` | Temporary directory for multipart parsing | Safe final storage location or default quota |

A multipart POST can contain file parts, text fields, metadata, per-part headers, boundaries, and framing bytes. Two 3 MB file parts are each under a 4 MB per-part cap, yet **their sum exceeds 4 MB** before even counting metadata. To cap the whole request, configure **ingress body limits** and/or an **application total byte budget**.

### 7.1 Notable Defaults

Per Spring Boot 3.5 Common Application Properties:

- Multipart `max-in-memory-size` defaults to roughly **256 KB**.
- Multipart `max-headers-size` defaults to roughly **10 KB**.
- `max-disk-usage-per-part` defaults to **-1**, meaning **unlimited** by this property.
- `max-parts` defaults to **-1**, meaning **unlimited** by this property.

That is why production upload apps must never assume "framework defaults are safe enough." Configure limits explicitly, especially when temporary multipart files share a volume with the application.

### 7.2 Do Not Use Servlet Properties for WebFlux

The properties:

```properties
spring.servlet.multipart.max-file-size=4MB
spring.servlet.multipart.max-request-size=6MB
```

are **Spring MVC/Servlet mechanisms**, not global limits for Spring WebFlux/Reactor Netty. Never copy them from a Servlet tutorial assuming WebFlux enforces upload sizes. Spring Boot documents two distinct property groups.

### 7.3 FilePart and PartEvent Are Two Different Paths

- `@RequestPart("file") FilePart`: WebFlux's multipart parser builds a `FilePart`, allowing `file.transferTo(Path)`. Parser properties govern temporary storage and per-part disk caps.
- `@RequestBody Flux<PartEvent>`: **streaming multipart events**. Content arrives as chunks in `FilePartEvent`; conventional reader spooling/disk limits **do not automatically apply identically**, because temporary files are not necessarily created. You must count bytes, part counts, header/metadata limits, release `DataBuffer`s, and enforce storage quotas for streaming parsers per your exact docs/version.

**Warning:** `FilePart.filename()` is untrusted input. Never do `targetDir.resolve(file.filename())` and write directly, risking path traversal, collisions, overwrites, and malicious content. Generate a **server-assigned filename**, restrict content types/extensions by policy, and inspect file contents post-upload. Never blindly trust client `Content-Type`.

### 7.4 Temporary Storage vs. Application Storage

WebFlux's parser may spool files to temporary disk **before the controller receives `FilePart`**. Calling `transferTo` moves the file to your chosen destination. Monitor quotas and disk capacity at **both temporary and final storage**, check ownership/permissions, and ensure cleanup on errors/cancellations. In containers, temporary storage often shares an overlay filesystem that fills quickly.

An HTTP 201 upload response does not mean a file is virus-free or ready to publish. In real products, publish only after scanning/validating and enforcing resource permissions.

## 8. Complete Java 17+ Project — Headers, JSON, Raw Body, and File Upload

This lab demonstrates four behaviors:

1. HTTP headers and request line bounded by Netty via properties.
2. JSON decoding bounded by the codec memory budget.
3. POST `/api/raw` rejected **by the endpoint itself** when the body exceeds **1024 bytes**, even without `Content-Length`.
4. Multipart `/api/files` bounded by parser config, then written by the controller to a demo directory using a server-generated name.

The API includes HTTP Basic to illustrate the Spring Security layer. **CSRF remains enabled by default**; POST integration tests use `spring-security-test` to supply tokens, while raw curl POSTs without CSRF receive 403. In machine-to-machine APIs using bearer tokens without browser ambient credentials, a conditional CSRF policy may be designed; this lesson avoids disabling CSRF globally just to make tests pass.

### 8.1 Build Dependencies

Generate a project from Spring Initializr with Java 17, **Spring Boot 3.5.x**, Gradle Groovy, and dependencies: Reactive Web, Security, Test, Security Test.

Inside `build.gradle` (alongside the Boot plugin and dependency management):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add Servlet `spring-boot-starter-web`, preventing Spring Boot from choosing MVC. `ServerHttpSecurity`/`SecurityWebFilterChain` belong to WebFlux, not Servlet's `HttpSecurity`/`SecurityFilterChain`.

### 8.2 Configuration File: application.yml

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  max-http-request-header-size: 8KB
  netty:
    max-initial-line-length: 4KB

spring:
  http:
    codecs:
      max-in-memory-size: 256KB
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 4MB
      max-headers-size: 8KB
      max-parts: 3
```

Values here are **illustrative samples**, not recommendations for every API. You also need total quotas at the gateway; tune properties per profile, traffic, and storage capacity. **This is Boot 3.5.x syntax.** On Boot 3.4, replace `spring.http.codecs.max-in-memory-size` with `spring.codec.max-in-memory-size` per that version's docs rather than keeping both randomly.

### 8.3 Source Layout

```text
src/main/java/com/example/payloadlimits/
  PayloadLimitsApplication.java
  SecurityConfig.java
  PayloadController.java
src/main/resources/
  application.yml
src/test/java/com/example/payloadlimits/
  PayloadLimitsHttpTest.java
```

Keep each `public class` in its own file under `com.example.payloadlimits`. Code relies on Reactor/WebFlux libraries and must run via the Gradle project, **not plain `javac`**. To avoid external accounts or services, demo uploads write to `build/upload-demo` for testing only.

### 8.4 PayloadLimitsApplication.java

`src/main/java/com/example/payloadlimits/PayloadLimitsApplication.java`:

```java
package com.example.payloadlimits;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PayloadLimitsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PayloadLimitsApplication.class, args);
    }
}
```

### 8.5 SecurityConfig.java: Auth Before Business Data

`src/main/java/com/example/payloadlimits/SecurityConfig.java`:

```java
package com.example.payloadlimits;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/ping").authenticated()
                .pathMatchers(HttpMethod.POST, "/api/**").hasRole("UPLOAD")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var uploader = User.withUsername("uploader")
            .password(encoder.encode("uploader-demo-password"))
            .roles("UPLOAD")
            .build();

        var viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-password"))
            .roles("VIEW")
            .build();

        return new MapReactiveUserDetailsService(uploader, viewer);
    }
}
```

**Explanation:** HTTP security does not enforce body size limits. It authenticates Basic credentials and requires `ROLE_UPLOAD` on POST endpoints. Unauthenticated calls to `GET /api/ping` receive 401; authenticated `viewer` lacking upload permission receives 403 on POSTs carrying a valid CSRF token. Never send Basic passwords over plain HTTP on real networks; this demo uses localhost with dummy users.

In production, restrict who may upload, enforce per-user/tenant size quotas, and rate-limit even authorized roles. Having upload permission **never** entitles a user to unlimited RAM, disk, or bandwidth.

### 8.6 PayloadController.java: Truly Bounded Raw Body

`src/main/java/com/example/payloadlimits/PayloadController.java`:

```java
package com.example.payloadlimits;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class PayloadController {

    private static final int MAX_RAW_BYTES = 1024;

    public record SizeReceipt(int bytes) {}
    public record NoteInput(String text) {}
    public record NoteReceipt(int chars) {}
    public record UploadReceipt(String id) {}

    @GetMapping(value = "/public/health", produces = "text/plain")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping(value = "/api/ping", produces = "text/plain")
    public Mono<String> ping() {
        return Mono.just("secured");
    }

    @PostMapping(
        value = "/api/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    public Mono<ResponseEntity<SizeReceipt>> raw(
            ServerHttpRequest request) {

        return DataBufferUtils.join(
                request.getBody(), MAX_RAW_BYTES
            )
            .map(buffer -> {
                try {
                    int count = buffer.readableByteCount();
                    return ResponseEntity.ok(new SizeReceipt(count));
                }
                finally {
                    // Caller must release the joined DataBuffer after use.
                    DataBufferUtils.release(buffer);
                }
            })
            .switchIfEmpty(
                Mono.just(ResponseEntity.ok(new SizeReceipt(0)))
            )
            .onErrorMap(
                DataBufferLimitException.class,
                error -> new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Raw body exceeds 1024 bytes", error
                )
            );
    }

    @PostMapping(
        value = "/api/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<NoteReceipt>> notes(
            @RequestBody Mono<NoteInput> body) {

        // JSON decoding path uses WebFlux codecs.
        return body.map(note ->
            ResponseEntity.ok(new NoteReceipt(
                note.text() == null ? 0 : note.text().length()
            ))
        );
    }

    @PostMapping(
        value = "/api/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file) {

        MediaType contentType = file.headers().getContentType();
        if (contentType == null
                || !MediaType.TEXT_PLAIN.isCompatibleWith(contentType)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "Only text/plain uploads are accepted in this demo"
            ));
        }

        // DO NOT build storage paths from client-supplied file.filename().
        String id = UUID.randomUUID().toString();
        Path directory = Path.of("build", "upload-demo");
        Path target = directory.resolve(id + ".txt");

        return Mono.fromCallable(() -> Files.createDirectories(directory))
            .subscribeOn(Schedulers.boundedElastic())
            .then(file.transferTo(target))
            .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadReceipt(id)));
    }
}
```

### 8.7 Analyzing the Controller

**`raw` endpoint:**

- `ServerHttpRequest.getBody()` is a `Flux<DataBuffer>` yielding **actual received** body bytes. It does not need `Content-Length` to detect when 1024 is exceeded.
- `DataBufferUtils.join(body, 1024)` caps total bytes **the endpoint will aggregate**. Only requests ≤ 1024 bytes succeed.
- After joining, `DataBufferUtils.release(buffer)` runs in `finally` to avoid holding pooled buffers. On failure/cancellation, the utility manages releasing accumulated buffers.
- `DataBufferLimitException` maps to `ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE, ...)`, so if uncommitted, WebFlux returns **413**.
- `switchIfEmpty` handles zero-byte bodies by returning 0. If business logic requires a non-empty body, return 400 via explicit validation.
- To bound large uploads, **never** call `join(..., Integer.MAX_VALUE)`; 1024 here is intentionally small for testing, not a general-purpose threshold.

**`notes` endpoint:**

- `@RequestBody Mono<NoteInput>` triggers JSON codec decoding. `spring.http.codecs.max-in-memory-size` limits bytes buffered by the codec, depending on the JSON decoder and payload shape.
- `note.text().length()` counts UTF-16 Java characters in the string, **not** HTTP request bytes. Never use it as business-level JSON payload size enforcement.
- To cap total JSON document bytes regardless of structure, enforce actual body limits at the gateway or a byte-counting layer, and also check post-decompression size when compressed inputs are accepted.

**`upload` endpoint:**

- The Spring WebFlux multipart parser reads the file part under `application.yml` limits for standard parser paths. `file.transferTo(target)` writes the file to the chosen path.
- Rather than using `file.filename()` on disk, we generate a server-side UUID. Restricting extensions/paths is only a first step; a client-supplied `text/plain` header **does not prove** the file is valid plain text.
- `Files.createDirectories` is blocking filesystem I/O; the example wraps it in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` to avoid blocking the Netty event loop.
- Demo code **omits** antivirus scanning, per-user disk quotas, partial-file cleanup on errors, timeouts, and publication lifecycles—all essential before production.
- A 4 MB **per-part** multipart limit does not cap the entire multipart request. With multiple file parts, enforce whole-request quotas at the ingress and application where strict bounds apply.

## 9. Testing WebFlux and Spring Security with WebTestClient

We use a **mock WebFlux context** with the Spring Security filter chain and `spring-security-test` generating CSRF tokens for POSTs. This test **does not verify Netty's decoder header budget** because traffic does not traverse Netty sockets; it verifies controller body quotas, method/route security, CSRF, and multipart handling at the WebFlux layer.

Create `src/test/java/com/example/payloadlimits/PayloadLimitsHttpTest.java`:

```java
package com.example.payloadlimits;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class PayloadLimitsHttpTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHealthIsAvailableWithoutPassword() {
        client.get()
            .uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("ok");
    }

    @Test
    void protectedPingNeedsAuthentication() {
        client.get()
            .uri("/api/ping")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void exactly1024RawBytesAreAccepted() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[1024])
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.bytes").isEqualTo(1024);
    }

    @Test
    void rawBodyAbove1024BytesIsRejectedWith413() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[1025])
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE);
    }

    @Test
    void uploaderCanDecodeSmallJson() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/notes")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.chars").isEqualTo(5);
    }

    @Test
    void authenticatedViewerCannotUpload() {
        client.mutateWith(csrf())
            .post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[20])
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void uploadWithoutCsrfIsForbidden() {
        client.post()
            .uri("/api/raw")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(new byte[20])
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void smallTextMultipartUploadIsAccepted() {
        var builder = new MultipartBodyBuilder();

        var data = new ByteArrayResource(
            "hello file".getBytes(StandardCharsets.UTF_8)
        ) {
            @Override
            public String getFilename() {
                return "client-supplied-name.txt";
            }
        };

        builder.part("file", data)
            .contentType(MediaType.TEXT_PLAIN);

        client.mutateWith(csrf())
            .post()
            .uri("/api/files")
            .headers(h -> h.setBasicAuth(
                "uploader", "uploader-demo-password"))
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .body(BodyInserters.fromMultipartData(builder.build()))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").exists();
    }
}
```

Run:

```bash
./gradlew test --tests '*PayloadLimitsHttpTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*PayloadLimitsHttpTest'
```

**Expected outcome:** tests pass when the Boot 3.5/WebFlux/Security project is created as shown. This is an **expectation derived from the example code, not output of a build run in the authoring environment**. A passing upload test creates a file in `build/upload-demo`; use only for the demo and clean up afterward.

### 9.1 Why Use `csrf()` in POST Tests?

Spring Security WebFlux enables CSRF protection on state-changing HTTP methods by default. Sending a POST with valid credentials but no CSRF token returns 403 **before reaching `PayloadController`**, preventing you from testing the 1024-byte limit.

`SecurityMockServerConfigurers.csrf()` injects a valid token in the mock `WebTestClient` security flow. This keeps security intact in the demo rather than "fixing" tests via app-wide `csrf(...disable())`. With real browsers, manage tokens/cookies/sessions properly; mock CSRF tests **do not prove by themselves** that production browser flows are safe.

### 9.2 Why Doesn't This Test Prove the 8 KB Header Limit?

`WebTestClient.bindToApplicationContext(...)` simulates HTTP exchanges in-process with Spring Security and **bypasses the Reactor Netty decoder**. Hence it cannot verify Netty rejecting headers > 8 KB. To test server-level request-line/header limits, use a **real port** or network client calling the running app with real config, optionally through curl/HTTP clients and the gateway.

### 9.3 Testing Netty Headers in Integration/E2E

Start the real server with `./gradlew bootRun` and send via an HTTP client:

- A request with a custom `X-Large` header of roughly **12,000 ASCII characters**.
- A request with a request target/query exceeding **4 KB**.
- Normal requests with small headers to confirm the app still responds cleanly.
- An equivalent HTTP/2 request **if** TLS/server supports HTTP/2.
- A request through the real reverse proxy or ingress if production uses a gateway.

**Safe outcomes to verify:** over-limit requests are rejected at the decoder/gateway without consuming downstream resources; status may be 400/414/431 or the client may observe connection closure depending on environment. **Do not** require `@ExceptionHandler` to return `ProblemDetail`, as failures happen before Spring WebFlux.

Each embedded server has its own semantics. Never use a Netty test case to "prove" Tomcat/MVC or a CDN gateway shares identical thresholds.

## 10. Manual Testing with curl and the CSRF Boundary

Start the server:

```bash
./gradlew bootRun
```

Default URL is usually `http://localhost:8080` if port 8080 is available.

Test public and protected endpoints:

```bash
curl -i http://localhost:8080/public/health
curl -i http://localhost:8080/api/ping
curl -i -u uploader http://localhost:8080/api/ping
```

The third command makes curl **prompt interactively for the password**; enter `uploader-demo-password`. Never pass real passwords directly on the CLI or send Basic credentials over public HTTP.

For `POST /api/raw`, a plain curl sending 1025 bytes **without a CSRF token** will return 403, **not reflecting the 413 body limit**. That is security working properly before the controller. Use the mock integration test with `csrf()` in section 9 or a browser/session flow with a valid CSRF token—**never disable CSRF casually**.

If a service-to-service upload API uses no browser ambient credentials, production architecture can define a **separate security chain** for Bearer JWT/service identities with an appropriate CSRF policy per threat model; disabling CSRF app-wide just so curl POSTs work is discouraged.

## 11. Interpreting HTTP Statuses for Oversized Requests

| Code/status or symptom | Possible origin | Meaning |
| --- | --- | --- |
| `413 Payload Too Large` | App limit/gateway/properly mapped parser | Request body exceeded limit and was rejected |
| `431 Request Header Fields Too Large` | Server/gateway choosing this status | Header too large per policy |
| `414 URI Too Long` | Request target/query too long | Not a body-size error |
| `400 Bad Request` | Invalid header/protocol/multipart syntax | Not necessarily size-related; inspect logs |
| `401 Unauthorized` | Missing/invalid Basic authentication | Can occur before the app reads the body |
| `403 Forbidden` | Lacks upload role or CSRF | Not automatically an oversized body |
| `415 Unsupported Media Type` | App rejects content type or codec | Distinct from oversized file |
| `5xx` | Server error, resource exhaustion, unmapped exception | Needs ops investigation; never treat 5xx as 413 |
| Connection close/reset | Early decoder/gateway/transport rejection | Not always accompanied by a parseable response body |

**Ordering note:** if a request is both **unauthenticated** and **oversized**, the final status depends on which layer rejects first. A proxy might reject with 413 before the app sees the request, whereas an authentication WebFilter might return 401 before consuming the body. **Never write tests requiring every layer to return one identical status regardless of path.**

### 11.1 Does Returning 413 "Save Transmitted Bytes"?

If a client already streamed a large body to the proxy before the backend detected the limit, network bandwidth may already have been consumed. Blocking at the ingress helps when possible; `Expect: 100-continue` lets some clients wait for approval before sending bodies, though not all clients/servers/proxies use or honor it.

`413` expresses a **payload rejection policy**, not a guarantee that the server finished reading the body or consumed zero resources.

## 12. Reverse Proxy / Ingress / HTTPS Layer

Many systems place **Nginx** in front of WebFlux. Illustrative directives:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    # Block large request bodies before backend per ingress policy.
    client_max_body_size 5m;

    # HTTP header/request-line buffers per Nginx semantics.
    client_header_buffer_size 1k;
    large_client_header_buffers 4 8k;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

This is an **Nginx snippet showing where limits sit**, not a complete production server config: you still need certificates/keys, TLS versions/ciphers, proxy timeouts, real IP/forwarded headers, trusted upstreams, compatible HSTS, and routing. Do not copy and deploy as-is.

**Why must proxies also enforce limits?**

- Internet clients can open many connections, trickle data slowly, and push huge byte streams before the app reads them.
- TLS termination, decompression, HTTP/2 header compression, and buffering can consume resources at the proxy.
- Requests traverse multiple hops with different caps. If a proxy allows 20 MB while Netty/app allows 4 MB, the backend still pays connection and initial parsing costs.
- When uploads stream through a proxy, proxy limits must account for **actual payload** and vendor semantics; never mistake timeouts or `proxy_request_buffering off` for body quotas.

### 12.1 Consistent Multi-Layer Policy

Suppose product requirements specify **max 5 MiB total per upload request**, max 4 MiB per file part, and up to two files:

- Ingress: reject **total request body** > 5 MiB.
- Multipart parser: prevent any single part from using > 4 MiB of disk; set `max-parts` to cover actual files **plus form fields**, avoiding mistaking "2 files" for "2 parts" when metadata fields exist.
- App: verify total file bytes, per-user quotas, content types/magic bytes, and owner/tenant.
- Storage: publish only scanned and validated files; enforce quotas and retention.
- Security: allow uploads only for identities holding `ROLE_UPLOAD`/scopes; rate-limit request counts and bandwidth per principal/IP thoughtfully.

Account for **multipart boundaries and metadata** so valid uploads are not blocked unexpectedly. If the business limit is 4 MiB of file content, total request size exceeds 4 MiB due to framing; set ingress caps slightly above the file budget and validate exact file bytes in the app.

### 12.2 HTTPS and Header Limits

HTTPS protects headers and bodies between clients and the TLS terminator, yet `Authorization`, `Cookie`, and upload metadata can still leak if gateways log raw headers. Minimize sensitive logging, protect internal hops with TLS where needed, and verify hop trust when using `X-Forwarded-*`.

Never inflate header budgets just to cram more sensitive claims into JWTs. Keep JWTs compact, use reference tokens/session handles or backend lookups at scale, and never let clients supply `X-User-Role`, `X-Tenant`, or `X-Forwarded-Proto` to be trusted as IdP/proxy assertions.

## 13. Byte-Level Multipart Limits: Harder Than "Max File Size"

### 13.1 Part Count Differs from File Count

Multipart form:

```text
multipart/form-data
  - file: photo.png    (file part)
  - title: "Hello"     (form field)
  - tags: "one,two"    (form field)
```

already has **3 parts** despite having only **1 file**. Setting `spring.webflux.multipart.max-parts=2` rejects it even for tiny files. Size budgets based on the real form schema, not just file count.

### 13.2 Spill Threshold Is Not a File Cap

A 100 KiB file when `max-in-memory-size=64KB` spills to temporary disk rather than failing at 64 KB. It is blocked only when hitting another cap like `max-disk-usage-per-part`, or a whole-request limit at the ingress/application.

Test: files just under the memory threshold, above the threshold yet under the disk cap, over the disk cap, many parts, and abnormal part headers. Never treat `max-in-memory-size` as a "file size limit" label.

### 13.3 `FilePart.transferTo` Is Not an Antivirus

`file.transferTo(target)` merely moves bytes to a path; it does not scan for malware, check MIME magic bytes, validate extensions, sanitize payloads, or enforce upload quotas. For Internet uploads, land files in **private quarantine/staging storage**, scan/validate before publishing, reject dangerous executables per business policy, and never execute or serve raw HTML under a trusted origin.

### 13.4 Streaming `PartEvent` Requires a Custom Byte Counter

When using `Flux<PartEvent>` to stream multipart without spooling to `FilePart`, do not assume conventional parser disk caps still apply identically. You must **sum actual `DataBuffer.readableByteCount()`**, enforce per-part and total limits, and handle backpressure, timeouts, cleanup, and buffer release on rejection.

**Architectural pseudocode:**

```text
Receive PartEvent stream
  -> check part count + per-part headers
  -> for each file part:
       validate filename/metadata limits
       accumulate bytes actually read (not just Content-Length)
       if per-file or total cap exceeded:
          stop consuming, cancel subscription, clean up temp file
          return 413 if response uncommitted
       if valid:
          stream bytes to quarantine storage (bounded resources)
  -> scan/validate
  -> atomically publish or mark ready
```

This is **pseudocode**, not production code; avoid writing a naive byte-counting `WebFilter` that leaks pooled `DataBuffer`s. Test cancellation, disk I/O errors, and chunked uploads lacking `Content-Length`.

## 14. A Quota Strategy Built to Withstand Load

Request size is just one resource dimension. Example per-user upload API budget:

| Limit | Example planning value | Mitigates |
| --- | --- | --- |
| Request header | 8 KB at server + aligned ingress | Cookie/JWT/header flooding |
| Request line | 4 KB at Netty + aligned gateway | Abnormal queries/paths |
| JSON buffered segment | 256 KB | JSON/form memory pressure |
| Raw body endpoint | 1 KB in demo; varies by business | Total bytes actually processed |
| Multipart file part | 4 MB temp in demo | Disk fill from a single file |
| Multipart part count | 3 parts in demo | Part explosion |
| Total upload request | 5 MiB at edge (architecture sample) | Multi-file/metadata requests |
| Total storage per principal | e.g., 100 MiB, per real policy | Single user exhausting disk |
| Concurrent uploads | e.g., max 2 active/user | Parallel disk/CPU spikes |
| Upload bandwidth/rate | Per SLO and threat model | Slow clients or bursts |
| Request/idle timeout | Per network/mobile/upload use case | Slowloris and hanging subscriptions |

**Values in this table are not configurations to copy blindly.** Derive thresholds from product profile, real traffic, server specs, RAM, temp disk, object-storage quotas, and user needs. Per-user/tenant concurrency limits require shared state across multi-replica deployments.

### 14.1 Concurrency Bugs Bypass Size Budgets

Suppose a user is allowed 4 MB/file, yet opens 1,000 uploads in parallel. Each per-file check passes while consuming ~4 GB of disk or exhausting file descriptors before user quotas trigger. Enforce **concurrency controls**, queues, rate limits, and aggregate quotas—not merely per-request caps.

### 14.2 Compression Bombs and Expansion Ratios

When accepting compressed payloads (gzip/zip), wire bytes and **decompressed bytes** can differ dramatically. A 5 MB network body cap does not mean decompressed output stays 5 MB. When backends extract archives or decompress requests, bound **decoded bytes**, entry counts, path depth, CPU/time budgets, and zip-entry path traversal.

The same applies to image processing: a 2 MB compressed image can expand into hundreds of MB of bitmap memory. Size limits never replace content validation and decompression-ratio checks.

### 14.3 CPU Timeouts and Backpressure

Reactive backpressure paces pipeline flow, yet does not stop attackers from tying up sockets, disk, or DB connections. Use bounded queues, timeouts, parallelism caps, and circuit breakers suited to the workload. Never perform blocking filesystem or virus-scanning work directly on the Netty event loop.

## 15. Common Questions and Misconfigurations

| Symptom | Likely error/misconception | Resolution |
| --- | --- | --- |
| 1 MB upload succeeds despite `max-in-memory-size=64KB` | Normal: file part spilled to disk | Check `max-disk-usage-per-part` and total body quota |
| Upload over 4 MB rejected | Parser per-part disk cap or ingress | Check which layer's status/logs fired; never assume every case is 413 |
| 1025-byte POST gets 403 instead of 413 | Missing CSRF or upload role | Use `csrf()` in tests; check auth/rules |
| Small `Content-Length` yet stream stays huge | Checked only header or chunked | Bound actual body bytes read |
| Huge JWT triggers 400/431/connection close | Netty/proxy header limit | Shrink token/claims; raise limit only after capacity/security review |
| Raising `spring.http.codecs.max-in-memory-size` doesn't fix uploads | Codec memory is not total file cap | Configure multipart/file limits and ingress |
| Used `spring.servlet.multipart.max-file-size` in WebFlux | Servlet-only property | Use `spring.webflux.multipart.*` |
| `spring.codec.max-in-memory-size` ignored in Boot 3.5 | Property renamed in 3.5 | Use `spring.http.codecs.max-in-memory-size` for your version |
| Only tested mock `WebTestClient`; 12 KB header still passes | Mock bypasses Netty decoder | Test on random port or `bootRun` + real HTTP client |
| App returns 401 on large-body request | Security rejected before reading body | Expected; test quotas with authenticated + valid CSRF |
| Uploads succeed yet disk grows forever | Temp/partial files uncleaned, no retention | Add quarantine, cleanup, quotas, metrics |
| Malicious filename containing `../` | Joined client filename into storage path | Generate UUID; validate display names separately |
| `text/plain` file contains binary | Client `Content-Type` untrusted | Inspect content, signatures, scan |
| Multipart with 2 files and 2 fields blocked at `max-parts=3` | `max-parts` counts both files and fields | Size against real multipart schema |
| Client gets connection reset instead of JSON 431 | Decoder/proxy rejected pre-app | Do not rely on `@ControllerAdvice` for decoder errors |
| Browser fetch upload fails CORS | CORS preflight/headers disallowed | Configure `CorsWebFilter` and auth separately; never `permitAll` API |
| `WebClient` throws `DataBufferLimitException` on download | Client codec memory budget, not server upload limit | Configure `WebClient` codec limit or stream response |
| 5 MB upload under app cap gets 413 at reverse proxy | Edge cap smaller than payload + framing | Align budgets across layers |
| Checked `max-disk-usage-per-part` only, yet requests send many files | No whole-request cap | Enforce edge total cap + app quota |
| HTTP/2 headers behave differently from HTTP/1.1 | Decoders/protocols/gateways differ | Test the exact production protocol |
| HTTPS works properly yet DoS still occurs | TLS does not bound resources | Add rate limits, timeouts, byte budgets, quotas |
| Disabled CORS/CSRF to "fix 403" | Masks security flaw and opens attacks | Diagnose root cause before altering policies |

## 16. Self-Check Questions

**Q1.** Does setting `spring.http.codecs.max-in-memory-size=256KB` reject every file > 256 KB?

**Answer:** No. It governs codec buffering, and multipart files can spill to disk or stream. Enforce separate per-file, disk, total-body, and user quotas.

**Q2.** Is `spring.webflux.multipart.max-in-memory-size=64KB` a 64 KB max file size?

**Answer:** No. It is the memory/spill threshold for file parts and the memory cap for non-file parts. File parts can exceed it by spilling to disk up to `max-disk-usage-per-part`.

**Q3.** With Netty `server.max-http-request-header-size=8KB`, must the sum of all headers always be ≤ 8 KB?

**Answer:** Do not assume that. Spring Boot docs state Netty applies the threshold per individual header, while Tomcat semantics differ. HTTP versions/proxies may also enforce separate limits; test your actual stack.

**Q4.** `Transfer-Encoding: chunked` omits `Content-Length`. How do you block bodies > 1 KB?

**Answer:** Count/limit bytes **as the real stream is read**, e.g., `DataBufferUtils.join(request.getBody(), 1024)` for small bodies, or a streaming byte counter with proper cleanup.

**Q5.** When `DataBufferUtils.join` succeeds, who releases the `DataBuffer`?

**Answer:** The consumer/code receiving the joined buffer is responsible for releasing it after processing, e.g., `DataBufferUtils.release(buffer)` in `finally`. The utility releases accumulated buffers on error or cancellation.

**Q6.** A multipart request has two files and two text fields—is `max-parts=3` enough?

**Answer:** No. That is **4 parts** (before counting protocol details), so the request can be rejected even with only two files.

**Q7.** Can a WebFlux backend use `spring.servlet.multipart.max-request-size` to cap total uploads?

**Answer:** No. Servlet properties do not control WebFlux's multipart parser; set whole-body caps at the ingress and in the WebFlux app stack.

**Q8.** Why can 413 occur before the controller without passing through `@RestControllerAdvice`?

**Answer:** Proxies, HTTP decoders, or early filters can reject requests before the WebFlux dispatcher. Application handlers cannot rewrite responses that never reached them.

**Q9.** Why does an over-limit POST get 403 in a test lacking CSRF?

**Answer:** Security rejects the POST before the endpoint reads the body. To test size limits, send an authenticated request with the right role and a valid CSRF token in mock `WebTestClient`.

**Q10.** Is a file with `Content-Type: text/plain` and filename `myfile.txt` safe to publish publicly?

**Answer:** No. Client-supplied metadata can be forged, and the file may hold binaries/malware. Quarantine safely, scan/validate, and enforce access control before publishing.

**Q11.** Can 4 MB files uploaded 1,000 times in parallel cause DoS even with a proper per-file cap?

**Answer:** Yes. You need concurrency limits, total disk quotas, rate limits, and cleanup—not just per-file caps.

**Q12.** Does HTTPS automatically block oversized headers or bodies?

**Answer:** No. TLS encrypts transport; it does not enforce business resource limits. TLS terminators/ingresses and WebFlux servers need explicit limits.

## 17. Production Checklist

- [ ] Confirm the HTTP server is actually WebFlux Reactor Netty, not accidentally Spring MVC/Servlet.
- [ ] Pin your Boot version and use **the right codec property** (`spring.http.codecs.max-in-memory-size` in 3.5+; `spring.codec.max-in-memory-size` in 3.4).
- [ ] Cap request headers and request lines at server/edge, verifying Netty semantics and HTTP/2.
- [ ] Never log raw `Authorization`/`Cookie`, and never raise header limits just to accommodate bloated tokens.
- [ ] Set JSON/form codec buffering limits, understanding they are **not body size limits**.
- [ ] For raw streaming bodies, enforce total bytes based on **actual `DataBuffer` bytes** or edge policies.
- [ ] For multipart uploads, enforce per-part disk usage, part count, part headers, and total request size across layers.
- [ ] Test part counts including **fields + files** plus multipart framing overhead.
- [ ] Never use `FilePart.filename()` in server-side paths; generate storage targets server-side.
- [ ] Enforce quotas, permissions, partial-file cleanup, and retention on temporary upload storage.
- [ ] If streaming `PartEvent`, implement byte counters, buffer release, backpressure, and cancellation cleanup.
- [ ] Confirm oversized requests fail at the right layer; verify HTTP status/connection closure on real servers/gateways.
- [ ] Keep authentication/authorization and CSRF intact when testing POSTs.
- [ ] Include tests for small bodies, exact boundary, over-limit, unauthenticated, denied-role, and multipart uploads.
- [ ] Check post-decompression and archive-extraction sizes; guard against zip bombs and huge bitmap allocations.
- [ ] Deploy HTTPS/TLS properly, accept forwarded headers only from trusted proxies, and keep secrets out of logs.
- [ ] Enforce rate limits, concurrent upload caps, bandwidth/timeout budgets, disk alerts, and 413/400/431 monitoring.
- [ ] Align budgets across CDN/gateway/ingress/app/storage, with rollback plans if rollout causes false positives.

## 18. Summary

**Size limiting in WebFlux is not a single parameter.** Separate clearly:

1. **Headers/request line:** `server.max-http-request-header-size` and `server.netty.max-initial-line-length`, plus gateway limits.
2. **Memory aggregation:** Boot 3.5 uses `spring.http.codecs.max-in-memory-size`; never treat it as "max HTTP body size."
3. **Multipart:** `spring.webflux.multipart.max-in-memory-size` is a memory/spill threshold; `max-disk-usage-per-part` applies per part; `max-parts` counts parts without replacing a total request cap.
4. **Actual body bytes and quotas:** count/bound consumed bytes, cap total requests at the ingress, and enforce per-user file/storage/concurrency quotas.
5. **Security:** HTTPS protects the channel, Spring Security decides who may upload, and resource limits stop valid-identity requests from being oversized or resource-exhausting.

**Remember:** Never rely solely on `Content-Length`, never treat `max-in-memory-size` as `max-file-size`, never use `spring.servlet.multipart` in WebFlux, and never grant an authenticated user unlimited uploads. Test with both **mock `WebTestClient`** for policies/codecs and **real HTTP via Netty/proxies** for decoders/edge layers.

### Official References

- [Spring Boot 3.5 — Common Application Properties: server request header, Netty, codec, and WebFlux multipart](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.4 — Application Properties (spring.codec.max-in-memory-size)](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [Spring Framework 6.2 — WebFlux Reactive Core, Codecs, Multipart Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebFlux Multipart Content and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — DataBufferUtils.join(Publisher, maxByteCount)](https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.2 — DataBuffer handling and reference counts](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html)
- [Reactor Netty — HTTP Server request decoder](https://projectreactor.io/docs/netty/release/reference/http-server.html)
- [Spring Boot 3.5 — NettyReactiveWebServerFactory API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [MDN — 413 Content Too Large / 431 Request Header Fields Too Large](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/413)
