# Coordinating Compression Across Application, Reverse Proxy, and CDN

An HTTP request in a modern Spring Boot system typically passes through multiple layers: **application (origin)** → **reverse proxy/ingress** → **CDN/edge** → **browser**. All three of the first layers can compress responses with gzip, Brotli, or another algorithm. Without intentional configuration, you can waste CPU, corrupt `Content-Encoding`, or cache the wrong variants. The result can be decoding errors, clients without algorithm support receiving compressed content, poor cache hit rates, or personal data leaking into shared caches.

**Core principle:** clearly assign **which layer owns compression for each resource group and network hop**, uphold the HTTP `Accept-Encoding` / `Content-Encoding` / `Vary` contract, and design caches around **representation variants**. You do not always want compression enabled simultaneously in Spring Boot, NGINX, and the CDN.

This lesson belongs to the *HTTP Caching and Compression* topic of Spring Boot web-runtime. Examples use **Spring Boot 3.x, Java 17+, Spring MVC, NGINX, and a CDN supporting edge compression**. Properties and Brotli or Zstandard support vary by server/CDN/version; verify documentation for your deployed versions before going to production.

## 1. Learning Objectives

After this lesson, you will be able to:

- Read and explain `Accept-Encoding`, `Content-Encoding`, `Vary: Accept-Encoding`, `Content-Type`, `Content-Length`, and `Cache-Control`.
- Distinguish *response compression* from *HTTP transfer framing* and *TLS*; understand why already-compressed data should not be recompressed.
- Decide when to compress in Spring Boot, a reverse proxy, or a CDN, distinguishing public static assets from dynamic APIs and responses containing personal data.
- Configure `server.compression.*` in Spring Boot 3.x and gzip compression in NGINX when the application returns uncompressed bodies.
- Coordinate CDN cache keys with gzip/Brotli/identity variants; understand why setting `Vary` alone is insufficient if a CDN/custom cache is misconfigured.
- Practice using `curl` to inspect compression, cache headers, bodies, and transfer efficiency across each hop.
- Recognize failures: double compression, missing `Vary`, wrong `Content-Length`, variant-mismatched ETags, byte ranges, and sensitive responses risking side channels.
- Measure p95 latency, CPU, wire size, and cache hits before choosing a solution.

## 2. Layered Architecture and Compression Placement

Consider a deployment path:

```text
[Spring Boot origin :8080]
    |
    | HTTP between origin and proxy
    v
[NGINX / Ingress / Reverse Proxy]
    |
    | HTTP(S) between proxy and CDN/origin shield
    v
[CDN / Edge cache]
    |
    | HTTPS to browser
    v
[Browser / HTTP client]
```

In practice, the CDN sits **in front of** the reverse proxy in the request direction: browser → CDN → reverse proxy → app. The diagram above depicts **the response path from app out to browser**. Each arrow is a hop that can carry identity data or data with a content coding applied. A CDN may cache encoded representations or re-encode for clients if product policies and capabilities allow.

| Layer | Decision authority | Advantages of compressing there | Trade-offs to consider |
| --- | --- | --- | --- |
| Spring Boot | Knows endpoints, MIME types, business context | Compresses dynamic responses at origin, useful if app→proxy link is slow | JVM CPU/memory cost, repeated work across replicas, not all connectors support all codings |
| Reverse proxy (e.g., NGINX) | Knows upstreams, routes, response headers | Centralizes policy, offloads app CPU, compresses across multiple origins | Must handle already-compressed bodies, caching, ETags, and sensitive content properly |
| CDN / edge | Knows viewer device type, `Accept-Encoding`, and cache | Compresses close to client, reuses cached objects, often supports Brotli | Features vary by CDN; origin/CDN cache policies must stay aligned; won't fix all origin bugs |
| Build pipeline for static files | Knows assets are immutable at build time | Can generate `.gz`/`.br` once at high compression levels | Server/CDN must negotiate variants and emit proper headers; never serve compressed files to unsupported clients |

A well-designed system usually has **one primary “owner” of compression per response from the client's perspective**, with clear policies at every hop. That does not mean every hop must send identity: if the app already compressed the payload with a valid coding, proxies/CDNs can **pass through** that exact representation without recompressing it.

## 3. Understanding HTTP Content Negotiation Accurately

### 3.1. Client States What It Supports: Accept-Encoding

A request can send:

```http
GET /api/catalog HTTP/1.1
Host: example.com
Accept-Encoding: br, gzip;q=0.8, identity;q=0.1
```

`br` is Brotli, `gzip` is GZIP; `identity` means no content coding applied. `q` is a preference weight from 0 to 1; `q=0` means the client rejects that coding. The server/CDN chooses one valid supported coding; do not assume it must pick `br` if Brotli is unsupported. Rules when the header is **absent** differ from an empty header or one containing `identity;q=0`; consult RFC 9110 instead of writing a naive parser like `String.contains("gzip")`.

Examples:

- `Accept-Encoding: gzip`: client accepts gzip; origin may compress if size/MIME criteria match.
- `Accept-Encoding: identity`: requests uncompressed representation; do not send `Content-Encoding: gzip`.
- `Accept-Encoding: gzip;q=0`: gzip is **forbidden** despite the string containing `gzip`.
- `Accept-Encoding: br, gzip`: client supports both; CDN may choose br if supported and policy allows.
- `Accept-Encoding` does not determine cacheability; cache storage also depends on response status and `Cache-Control`.

### 3.2. Server Announces Applied Coding: Content-Encoding

A compressed response may include:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: public, max-age=60
```

The response body here is **gzip-encoded bytes**. The browser decodes per `Content-Encoding` before handing application content to JavaScript or the renderer. A `curl --compressed` request also advertises codings supported by that curl build and **decompresses the body before printing**, while still displaying `Content-Encoding` in headers. If you run plain `curl -H 'Accept-Encoding: gzip'` and print the body, raw output will look like binary garbage.

**`Content-Type`** describes the media type of the decoded representation, such as JSON or HTML; **`Content-Encoding`** describes the content encoding transformation. `application/json` does not become `application/gzip` merely because JSON is gzipped for transport.

### 3.3. Vary: Accept-Encoding Is Core to Correct Caching

When a URL can return different representations depending on request `Accept-Encoding`, the response should declare:

```http
Vary: Accept-Encoding
```

Meaning: a standards-compliant cache must check `Accept-Encoding` on the original request and the incoming request before reusing a stored response. The same URL can have at least two variants:

```text
GET /app.js + Accept-Encoding: gzip
  -> Content-Encoding: gzip
  -> bytes G

GET /app.js + Accept-Encoding: identity
  -> no Content-Encoding
  -> bytes I

G and I do not have the same byte sequence.
Cache must not mistake G for I.
```

If a cache keys solely on URL while ignoring `Vary` or mishandling encoding normalization, it can serve gzip bytes to an identity-only client. The result can be decoding errors, failed JS/CSS loading, or unreadable responses.

**CDN note:** some CDNs normalize/whitelist `Accept-Encoding` and build separate cache keys for gzip/Brotli; configure per **product documentation**. Seeing `Vary: Accept-Encoding` on the origin **is not enough** to guarantee the CDN is configured properly. When a response also varies by `Accept-Language` or other content negotiation, review the full cache policy to prevent cache key explosion.

### 3.4. Do Not Confuse Content-Encoding with Transfer-Encoding

- `Content-Encoding: gzip`: body representation is compressed; the coding affects how the content is decoded.
- `Transfer-Encoding: chunked` in HTTP/1.1: a framing technique to send bodies in chunks; does not mean gzip.
- HTTP/2 and HTTP/3 use their own framing mechanisms and do not use HTTP/1.1 `Transfer-Encoding: chunked`.
- TLS encrypts the transport and provides channel confidentiality; gzip/Brotli shrinks data **before transport** at the HTTP representation layer. HTTP compression does not replace TLS.

A response can be both gzip-encoded and HTTP/1.1 chunked. Conversely, a chunked response without `Content-Encoding` still has an identity body if no other content coding applies.

## 4. Choosing Who Compresses: Four Practical Topologies

### Option A — Compress at Spring Boot, Proxy and CDN Pass Through

```text
Boot -> (gzip bytes) -> NGINX pass-through -> CDN/cache variant -> Browser
```

Use when the origin needs to compress itself because the origin→proxy/CDN link is bandwidth-constrained, dynamic responses are uncacheable yet large, or the proxy lacks desired compression features. Spring Boot configures compression, and the proxy avoids recompressing bodies that already have `Content-Encoding`. Caches at proxy/CDN (where allowed) must separate variants or cache one representation per contract.

Trade-off: compression CPU runs on every JVM; if the origin emits gzip for everyone, the CDN may not automatically convert it to Brotli. Never assume a CDN automatically recompresses already-coded responses; check each product. If the edge wants Brotli while origin only speaks gzip, letting the origin send identity so the edge chooses is often better.

### Option B — App Returns Identity, Reverse Proxy Compresses

```text
Boot identity -> NGINX gzip per viewer Accept-Encoding -> CDN/Browser
```

Fits when you want centralized policy across multiple apps, the app is CPU-bound, or you want less compression config inside each Spring service. NGINX can request identity from upstream by **not forwarding the client's `Accept-Encoding` down to origin**; it then gzips according to client requests based on MIME type and size. Be careful not to strip `Accept-Encoding` incoming from clients to NGINX: only override the header **on the NGINX→origin hop** if your topology needs it.

When a CDN sits in front of NGINX, NGINX sees requests from the CDN; the CDN may normalize `Accept-Encoding` on the hop to NGINX. Inspect actual requests and CDN cache policies rather than guessing from browser headers alone.

### Option C — App and Reverse Proxy Return Identity, CDN Compresses at Edge

```text
Boot identity -> Reverse proxy identity -> CDN (br/gzip) -> Browser
```

This is a popular approach for **public static assets** and cacheable public JSON: the edge sees viewer capabilities and compresses once close to users while caching appropriate variants. The origin spends less compression CPU; in exchange, origin-to-CDN links carry more bytes on cache misses. With fast intra-region/private origin networks and high CDN cache hit ratios, this is often worth evaluating first.

Skipping origin compression does not mean the CDN automatically compresses: you must enable compression options, configure cache policies, MIME/size rules, and verify in practice. If the CDN does not support a coding for a response type, clients receive identity or another valid coding.

### Option D — Precompress Static Assets at Build Time

```text
Build JS/CSS -> app.js + app.js.gz + app.js.br
                              |
                       Edge/proxy picks right variant
                              |
                           Browser
```

Used for buildable, content-hashed static JS/CSS/HTML. High-level Brotli compression in CI achieves great size reduction with zero runtime compression CPU. However, the server must emit the proper `Content-Encoding: br` or `gzip`, preserve the original `Content-Type`, and fall back to identity for unsupported clients. Creating `.br` files and serving them as `application/octet-stream` solves nothing.

NGINX has `gzip_static` to serve `.gz`, **though it is not always compiled in by default**; static Brotli requires a dedicated module or server/CDN support. Do not enable `gzip_static always` unconditionally unless a decompression fallback exists for unsupported clients.

### Quick Selection Table

| Response type | Usually preferred compression point | Cache policy | Notes |
| --- | --- | --- | --- |
| Hashed JS/CSS filenames | Build/CDN, or NGINX static | Long `public, max-age`, `immutable` when filename is versioned | Serve matching br/gzip/identity per viewer |
| Frequently updated public HTML | CDN or NGINX | Short TTL / conditional revalidation | ETag, Vary, purge on update |
| Large public JSON | CDN if cacheable; otherwise NGINX/app | Depends on data, e.g., `public, max-age=60` | Never mis-cache per-user data |
| JSON with cookies/login and personal data | App/NGINX per dedicated security policy; avoid shared cache | `private` or `no-store` per sensitivity | BREACH/secret reflection, Cache-Control, and CDN bypass |
| Real-time SSE/streaming | Usually limit high-latency compression/buffering | Usually not shared-cached | Latency, flushing, proxy buffering |
| Pre-compressed JPEG/PNG/WebP/AVIF, MP4, ZIP/PDF | Usually do not re-gzip | Per-asset caching | Little gain and wastes CPU; range/download |
| Very small payloads | Usually do not compress | Per business rules | gzip header overhead, CPU exceeds saved bytes |

This table is a starting guide, not an absolute rule. Benchmark with your real payload sizes, data types, network, CPU, TTFB, and CDN hit rate.

## 5. Spring Boot 3.x: Configuring Compression in the Application

Spring Boot 3.3 offers these properties:

```properties
server.compression.enabled=true
server.compression.mime-types=text/html,text/plain,text/css,application/json,application/javascript,application/xml
server.compression.min-response-size=1KB
```

The properties in the example **modify the origin application's config**. If choosing Option B/C (compressing at proxy/CDN), set `server.compression.enabled=false` or omit it because Boot 3.3 defaults to **false**.

Per the Spring Boot 3.3 properties reference:

- `server.compression.enabled`: defaults to `false`.
- `server.compression.min-response-size`: defaults to **`2KB`**, specifying the `Content-Length` threshold.
- `server.compression.mime-types`: defaults to `text/html`, `text/xml`, `text/plain`, `text/css`, `text/javascript`, `application/javascript`, `application/json`, and `application/xml`.
- `server.compression.excluded-user-agents`: list of user agents excluded from compression where supported by the container.

Enabling the property does not mean **every response** is compressed. Actual behavior depends on the embedded server (Tomcat/Jetty/Undertow/Reactor Netty), MIME type, content, size, headers, client support, and streaming behavior. Spring Boot supports HTTP response compression across these embedded servers, but **do not assume those properties produce Brotli**: check which codings your active runtime supports. In the Spring MVC/Tomcat example, the goal is demonstrating gzip.

When moving to Spring WebFlux/Reactor Netty, the app can use the same Boot property group depending on version, yet the execution path is reactive and requires measuring CPU/event-loop/streaming separately. Do not mix MVC servlet filters with reactive handlers just to get compression.

## 6. Runnable Java 17+ Example: A Spring Boot Origin

The example provides a JSON response long enough to observe compression, a short response, and a non-cacheable demo response. Data is statically constructed for testing with no personal data or secrets.

### 6.1. Create the Project

Use [Spring Initializr](https://start.spring.io/) to create a Java 17+ project with **Spring Boot 3.x**, Gradle/Groovy, and the **Spring Web** dependency. In the generated `build.gradle`, the dependencies section is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a Gradle snippet, **not a complete `build.gradle`**. Initializr provides the Boot plugin, dependency management, repositories, Java toolchain, and Gradle Wrapper. For Spring Boot 4.x, check that major version's starters/properties.

Create the structure:

```text
src/main/
├── java/demo/
│   └── CompressionDemoApplication.java
└── resources/
    └── application.properties
```

### 6.2. Java Source

File `src/main/java/demo/CompressionDemoApplication.java`:

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CompressionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompressionDemoApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping(
            value = "/api/catalog",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<String> catalog() {
        StringBuilder json = new StringBuilder("{\"items\":[");

        for (int i = 0; i < 300; i++) {
            if (i > 0) {
                json.append(',');
            }
            json.append("{\"id\":")
                    .append(i)
                    .append(",\"category\":\"books\"")
                    .append(",\"title\":\"Spring Boot Guide\"}");
        }

        json.append("]}");
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic())
                .body(json.toString());
    }

    @GetMapping(
            value = "/api/small",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String small() {
        return "ok";
    }

    @GetMapping(
            value = "/api/no-store",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> noStore() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body("no-store-example");
    }
}
```

Explanation:

1. `@SpringBootApplication` in package `demo` picks up `DemoController` in the same package. Only the startup class is `public`, so two classes in one Java file is valid.
2. `catalog()` constructs valid JSON with 300 simple elements, needing no database. Repetitive content compresses very well; this endpoint only serves **mechanism verification**, not a representative production benchmark.
3. `ResponseEntity` declares `Cache-Control: public, max-age=300` for hypothetical public JSON. **Do not** copy that policy to endpoints carrying per-user information.
4. `small()` produces a short response unlikely to be compressed due to the size threshold.
5. `noStore()` demonstrates `Cache-Control: no-store`; it only controls caching and **does not forbid HTTP compression**. To prevent transforms/compression, use dedicated policies and check every layer.
6. Do not manually set `Content-Encoding` or `Content-Length`; the embedded server/proxy is responsible for choosing and emitting proper headers when compressing.

### 6.3. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Only for Scenario A: Spring Boot performs compression
server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json,text/html,text/css,application/javascript
```

This is the origin-compression config for experiment A. When switching to NGINX compression in section 8, change to `server.compression.enabled=false` and **restart the application**; do not leave both enabled just hoping for “stronger compression”.

### 6.4. Launch

From the project directory:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Spring Boot runs on `http://localhost:8080` if the port is free. The classes require Spring Framework on the classpath, so plain `javac CompressionDemoApplication.java` will not work; Gradle Wrapper compiles and runs with dependencies.

### 6.5. Verify Content Negotiation with curl

In another terminal, request gzip support:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/catalog
```

With curl on Linux/macOS, expect a `200 OK` response with `Content-Type: application/json`, `Cache-Control: public, max-age=300`, and, if the response qualifies and the container compresses, `Content-Encoding: gzip`. Header `Vary: Accept-Encoding` should be present when representations vary by encoding; inspect actual output because header emission depends on runtime/filters.

Request identity:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/api/catalog
```

Expect a response **without** `Content-Encoding: gzip`. Compare actual wire bytes against the gzip request to assess savings. A `Content-Length` header may be absent on streaming/chunked responses; do not force one just to make compression trigger.

Read content with curl auto-decompression:

```bash
curl -sS --compressed http://localhost:8080/api/catalog
```

The output is (very long) JSON with 300 items. `curl --compressed` advertises codings compiled into that curl build and decodes the body; if curl lacks `br` support, do not treat it as proof that the server cannot send Brotli to browsers.

Request the small response:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/small
```

The `ok` body is very short; with a 1KB threshold, it is normally uncompressed. **Do not rely on length alone** to define exact HTTP contracts: runtimes may enforce additional rules around MIME, `Content-Length`, and streaming.

On Windows PowerShell: use `curl.exe`, replace `/dev/null` with `NUL`, and keep commands on one line or use PowerShell line continuation. Example:

```powershell
curl.exe -sS -D - -o NUL -H "Accept-Encoding: gzip" http://localhost:8080/api/catalog
```

### 6.6. Verify “Compression Does Not Equal Caching”

```bash
curl -sS -D - -o /dev/null http://localhost:8080/api/no-store
```

The response carries `Cache-Control: no-store` as coded. Even with compression enabled globally, this header **does not disable compression**; it asks caches not to store the content. Conversely, `Cache-Control: public` does not force compression. These are two independent decisions: **whether the response may be stored** and **which coding encodes the response**.

## 7. Rules for Choosing MIME, Size, and Compression Level

### 7.1. Which Data Types Compress Well

Repetitive text (HTML, CSS, JS, JSON, XML, plain text, SVG text) usually benefits from gzip/Brotli. Pre-compressed formats such as JPEG, PNG, WebP, AVIF, MP4, ZIP, and many PDFs rarely shrink meaningfully when gzipped again. Compression is a transformation; added CPU can outweigh benefits when payloads are small or incompressible.

In proxies/CDNs, the MIME list must cover your origin's content types. If APIs return `application/problem+json` or vendor JSON `application/vnd.example+json`, matching against `application/json` depends on server/module; test in practice and add exact types when needed. For `application/octet-stream`, do not blindly gzip arbitrary binary payloads without evidence.

### 7.2. Minimum Compression Threshold

Gzip incurs header/footer bytes and CPU overhead. Payloads of a few dozen bytes are rarely worth compressing. Spring Boot 3.3 defaults to a 2KB threshold when compression is enabled; NGINX has `gzip_min_length`. Do not tune both thresholds trying to hit the same target if one layer is designated to emit identity.

Keep **pre-compression size** and **post-compression size** distinct. The configured threshold decides when compression starts, whereas `Content-Length` (if sent) on an encoded response must reflect the actual encoded bytes sent for that representation, not the original JSON/HTML length. With streaming or when compression begins after headers, the server may not know the encoded length upfront and uses appropriate framing.

### 7.3. Compression Level and CPU

Higher gzip levels burn more CPU and add compression latency to save a few extra bytes, with diminishing returns. For dynamic content under tight p95 latency, choose a balanced level; static files can be precompressed in CI at high levels. There is no “gzip level 9 is always best” for every workload.

Measure at least:

- CPU percent and compression time per node.
- Payload bytes before/after compression and savings ratio.
- TTFB, p50/p95/p99 end-to-end latency, throughput requests/s.
- Cache hit/miss and origin invocation count.
- Spring Boot memory and GC if compressing/buffering in the JVM.
- Traffic and bandwidth costs across hops with different billing rates.

One fast localhost request does not prove compression helps over 4G mobile networks or on CPU-constrained pods. Benchmark under concurrent load too.

## 8. NGINX Reverse Proxy: Compressing Once at the Proxy

This section demonstrates **Option B** with Spring Boot returning identity bodies and NGINX gzip-compressing per client request. Requires NGINX installed and configuration access; the server block belongs inside NGINX's `http` context.

**In the Spring Boot app:** change the property to:

```properties
server.compression.enabled=false
```

Then restart Boot. Add an illustrative NGINX block:

```nginx
server {
    listen 8081;
    server_name localhost;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_comp_level 5;
    gzip_types
        text/plain
        text/css
        application/json
        application/javascript
        application/xml;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Applies only on the NGINX -> Spring Boot hop.
        # Tells origin to return identity so the proxy owns compression.
        proxy_set_header Accept-Encoding "";
    }
}
```

This is **one server block**, not a complete `nginx.conf`. It assumes NGINX and the app run on the same host; if NGINX runs in another container, `127.0.0.1:8080` points inside the NGINX container itself, **not** Spring Boot. In Docker/Kubernetes, replace the upstream with the proper service DNS name and port.

Key facts to know:

1. `gzip on` enables NGINX runtime gzip for eligible responses.
2. `gzip_types` adds MIME types; `text/html` is already handled by NGINX by default when gzip is on.
3. `gzip_min_length 1024` sets the threshold, evaluated by NGINX from the response's `Content-Length` per docs; if that header is absent, actual behavior may differ from known-length bodies.
4. `gzip_vary on` adds `Vary: Accept-Encoding` when gzip/gzip_static/gunzip are active.
5. `proxy_set_header Accept-Encoding ""` **clears the header on the upstream request**, guiding the origin to return identity where supported. NGINX **still sees** the client/CDN `Accept-Encoding` on the incoming request to NGINX to decide compression.
6. `gzip_comp_level 5` is an illustrative level needing CPU/latency measurement; do not treat it as universally optimal.
7. By default NGINX **does not re-gzip an already gzip-encoded response** under normal gzip handling; however, custom filters/modules or misdeclared origin headers can still cause bad encoding. Explicitly picking one primary compression layer simplifies debugging.

**Note on `gzip_proxied`:** the directive name is easily misunderstood. NGINX checks whether requests came from an upstream proxy via the `Via` request header, then decides whether to compress responses matching those conditions (e.g., `gzip_proxied no-cache no-store private expired auth`). It does **not simply mean** “compress every response fetched via `proxy_pass`”. Enable only values aligned with your proxy chain and cache policy; do not use `gzip_proxied any` unconditionally without analysis.

### 8.1. Test at NGINX and Compare with Origin

With origin on `:8080` returning identity and NGINX on `:8081`:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8081/api/catalog
```

Expect (when eligible) headers from NGINX to client containing `Content-Encoding: gzip` and `Vary: Accept-Encoding`.

Meanwhile calling the origin directly:

```bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/catalog
```

With `server.compression.enabled=false` and no other filter, the origin response **lacks** `Content-Encoding: gzip`. Comparing the two outputs identifies which layer compressed.

After editing NGINX, validate syntax with `nginx -t` and reload via your environment's management method (systemd, container rollout, etc.). Do not casually restart production servers just to test a snippet.

### 8.2. What If the Origin Already Compressed?

If choosing **Option A**, remove the upstream identity override and configure the proxy to handle/forward encoded responses cleanly. Do not compress the payload again just because the proxy also has `gzip on`. If the CDN wants Brotli while origin already sent gzip, explicitly decide one of three paths:

- Accept serving gzip to viewers if supported and the CDN preserves headers properly.
- Let CDN/origin negotiate variants they mutually support.
- Have origin return identity so the CDN chooses Brotli/gzip.

“Decompressing gzip then recompressing to Brotli” is **transcoding**, which can cost significant CPU and alter representation metadata; do not treat it as free or assume every CDN performs it automatically.

## 9. CDN and Caching: Content Variants by Accept-Encoding

### 9.1. Same URL, Different Bodies

For `/assets/app.4d92.js`, a viewer may send:

```http
Accept-Encoding: br, gzip
```

The CDN may return:

```http
HTTP/2 200
Content-Type: application/javascript
Content-Encoding: br
Vary: Accept-Encoding
Cache-Control: public, max-age=31536000, immutable
```

Another client supporting only gzip may receive `Content-Encoding: gzip` or identity. **Never** reuse br bytes for a client that does not support br. `immutable` is only appropriate when resource names are truly versioned/content-hashed; never put long-term `immutable` on `/index.html` that updates at the same URL.

A compliant cache evaluates hits using the URL and `Vary` conditions. A CDN's cache policy may **normalize** Accept-Encoding options to avoid countless equivalent keys; details vary across providers. Do not blindly add every request header to cache keys, as that destroys hit rates.

### 9.2. Concrete Example with Amazon CloudFront

Per CloudFront documentation, to enable automatic CDN compression you can:

1. Enable **Compress objects automatically** on the appropriate cache behavior.
2. Use a cache policy with **Gzip** and **Brotli** enabled.
3. CloudFront automatically factors supported encodings into cache key/origin requests under that setting.
4. Test with a viewer sending `Accept-Encoding: br, gzip` and a viewer sending only `gzip`, while verifying real cache hits.

CloudFront generally prefers Brotli when viewers support both gzip and Brotli under permitted product rules. However, an origin response already carrying `Content-Encoding` may not be recompressed by CloudFront like an identity response, and an object **cached before compression was enabled** will not necessarily be recompressed immediately. Check version docs/behavior and invalidate when changing configuration.

This example gives practical rules, **not** a complete CloudFront/Terraform/CloudFormation tutorial. On Cloudflare, Fastly, Azure Front Door, or other CDNs, setting names, br/zstd/gzip support, cache key normalization, and transforms differ.

### 9.3. Public and Private Caches Must Never Mix

Compression is one thing; *sharing content across multiple users* is another.

| Response | Usually appropriate Cache-Control | CDN consequence |
| --- | --- | --- |
| Public hashed JS/CSS | `public, max-age=31536000, immutable` | Long cache, purge/version by hash |
| Frequently updated public catalog list | `public, max-age=60` or fitting TTL | Cacheable if policy permits |
| Pages/JSON with personal information | `private` or `no-store` as required | Shared CDN must not reuse private data |
| APIs with Authorization | Usually bypass shared cache, unless explicitly designed per RFC | Do not cache merely because the request “looks like GET” |
| Responses with Set-Cookie/user context | Special/cautious policy | Prevent CDN accidentally duplicating cookies or per-user content |

`Cache-Control: private` prevents **shared caches** from storing responses per standard semantics, yet private browser caches may still store depending on other directives. `no-store` tells caches not to store; it fits when not even the browser cache should retain sensitive bodies. Do not treat `private` and `no-store` as synonyms.

Do not merely add `Vary: Cookie` and assume CDN caching of personal content is safe. Varying by Cookie creates enormous cache cardinality and still fails if the cache ignores or mis-normalizes cookies. For authenticated/private responses, the safer default is **bypassing shared caching** unless strict data isolation has been explicitly engineered.

### 9.4. Purge/Invalidation and Variants

When purging a CDN URL, know whether the product purges **all variants** or just one cache-key form. If identity/gzip/br are cached separately, purging or versioning must keep them consistent. Hashed assets are usually easier than manual purges; mutable HTML at the same URL typically needs short TTLs or sound revalidation.

## 10. ETag, 304, and Content-Length When Representations Change

### 10.1. ETag Must Match the Encoded Variant

For instance, a JS file's identity body and gzip body have **different bytes**. Under HTTP, strong validators identify byte-level representations of the encoded form. Never assign the same **strong ETag** to two byte-different representations and expect safe byte-range/revalidation semantics.

Illustration:

```http
# Identity representation
Content-Type: application/javascript
ETag: "app-42-identity"
Vary: Accept-Encoding

# Gzip representation
Content-Type: application/javascript
Content-Encoding: gzip
ETag: "app-42-gzip"
Vary: Accept-Encoding
```

An intermediary transforming the body may need to adjust/weaken/remove strong ETags or use proper validator handling. **Weak ETag** (prefixed with `W/`) has weaker semantics, yet should not be assumed to solve every cache-key issue. It is best to check how your server/proxy/CDN handles validators rather than forcing one fixed ETag across all encodings.

### 10.2. 304 Not Modified Has No Body

`304 Not Modified` lets clients/caches reuse a stored response when validators match. When a gzip variant is cached and revalidated, metadata such as `Vary`, `ETag`, and cache directives must remain consistent with the target representation. Do not manually attach `Content-Encoding: gzip` alongside another variant's `Content-Length` on a 304 response and cause caches to corrupt metadata.

### 10.3. Content-Length of Encoded Data

If an identity JSON body is 20,000 bytes while gzip shrinks it to 2,000 bytes, `Content-Length` on the gzip response (if emitted) must reflect **2,000 encoded bytes**, not 20,000. If unknown before headers are sent, the server can omit Content-Length and use HTTP-version-appropriate framing. Avoid custom filters setting Content-Length from the original string before the compressor runs.

When a proxy decompresses or changes coding, it must ensure `Content-Length`, `Content-Encoding`, validators, and body-bound metadata are accurately updated or removed; that is why standard compression modules beat hand-rolled headers.

### 10.4. Range Requests and Compressed Content

HTTP `Range: bytes=...` on an encoded representation applies byte offsets to the **encoded representation's bytes**, not the decompressed text offsets. Therefore, arbitrarily compressing or switching codings while serving `206 Partial Content` can break download resumption. Be especially careful with video, PDFs, archives, download managers, and CDN range caching.

For resources needing range/resume, prefer servers/CDNs with standards-compliant range + content-coding support, or keep identity where appropriate. Never “gzip every 206 response” with a custom filter. Verify `Accept-Ranges`, `Content-Range`, `ETag`, and real client decoding.

## 11. Precompressed Assets: Saving CPU While Delivering Properly

A build pipeline can emit three files:

```text
app.4d92.js       -> identity
app.4d92.js.gz    -> gzip
app.4d92.js.br    -> Brotli
```

A **properly configured** reverse proxy/CDN selects the file matching `Accept-Encoding`, keeps `Content-Type: application/javascript`, adds the matching `Content-Encoding`, and emits `Vary: Accept-Encoding`. Do not expose `/app.4d92.js.br` as the public URL for all clients if the server does not signal encoding properly.

NGINX offers `ngx_http_gzip_static_module` to serve `.gz`:

```nginx
location /assets/ {
    root /srv/site;
    gzip_static on;
    gzip_vary on;
}
```

This **snippet** requires root/path to match the real filesystem layout and an NGINX binary compiled with `gzip_static` (not every build enables it). It locates the matching `.gz` file for eligible clients; if no precompressed copy exists or the client lacks support, the identity file must exist. `.br` handling is a separate module/feature and is not enabled by `gzip_static on`.

**Do not assume “precompressed = always smaller”**: check output sizes and drop a variant if savings are negligible. Prebuilding fits immutable assets, rarely per-user/per-request JSON.

Spring Boot has a resource chain for precompressed resources (e.g., `spring.web.resources.chain.compressed` in 3.x), yet it only applies to static resources served by resource handling. Do not treat it as a replacement for dynamic API compression or CDN cache policies. Choose **one place to serve static variants** (app, proxy, or CDN) to avoid conflicts.

## 12. Compression and Streaming/SSE Responses

Not every stream should be optimized primarily for total bytes.

Examples:

- **Server-Sent Events (SSE)**: applications need low-latency event flushing. Gzip or proxy buffering can hold data waiting to fill a block and delay browser event delivery.
- **Streaming JSON/NDJSON**: streaming compression can save bandwidth yet increase latency; test flushing and backpressure.
- **Downloads/ranges**: recompressing may yield little benefit and complicates Content-Range.
- **gRPC**: uses its own protocol compression rules and gRPC proxy handling; do not assume HTTP `Content-Encoding` rules for JSON transfer verbatim.
- **WebSocket**: uses per-message deflate/extensions, distinct from gzipping an entire HTTP handshake response body.

For SSE endpoints, usually prioritize **consistent latency and zero buffering**; you may need to exclude `text/event-stream` from compression and configure reverse proxy/CDN bypass or stream passthrough per product. Do not disable `gzip off` site-wide just for a couple of streaming routes, yet never compress/buffer all routes globally without testing.

## 13. Security Risks: Compressing Sensitive Content

### 13.1. BREACH and Length Side Channels

HTTP response compression over HTTPS can create a **side channel** when one response combines a **secret** (such as a CSRF token) with data an attacker can cause the server to reflect, allowing the attacker to observe response length changes. This is the BREACH attack class; TLS still encrypts contents, yet ciphertext lengths can leak statistical information.

Mitigations depending on threat model:

- Omit secrets from responses unless necessary.
- Avoid reflecting attacker-controlled text alongside secrets in the same compressed response.
- Disable HTTP response compression on **sensitive routes** or responses mixing secrets + untrusted input, across **every layer that can compress**, not just Spring Boot.
- Maintain CSRF protection, token/session/cookie defenses, rate limiting, and architectural controls.
- Verify whether the CDN recompresses a response the app intentionally left as identity.

`Cache-Control: no-store` **does not disable compression**. `Cache-Control: no-transform` has standard semantics asking intermediaries not to alter content, useful when you genuinely need compliant proxies/CDNs not to transform payloads; still **verify the real configuration**. Do not expect a single header to cure every CDN rule.

### 13.2. Never Public-Cache Authenticated Content

If an API responds based on cookies or Authorization and contains private info, attaching `Cache-Control: public` just to boost cache hits is a severe risk. On sensitive responses, `no-store` or `private` paired with proper CDN bypass generally matters far more than shaving a few extra bytes via compression.

### 13.3. Never Blindly Trust Client-Declared Content-Encoding

On **request bodies** (uploads), `Content-Encoding` can indicate a compressed request payload; that is separate from response compression. Backends/proxies may not automatically decompress requests; if supported, enforce **post-decompression size limits** to prevent decompression bombs. Never read `Accept-Encoding` on a request to guess how to decompress the request body: it declares which **responses** the client accepts, not how the request body is encoded.

## 14. Caching and Compression Must Be Verified Across All Three Layers

A common failure happens when each team tests only its own layer:

- App tests show valid gzip.
- NGINX tests show 200 responses.
- CDN tests show cache hits.
- Yet users receive the wrong compressed variant because cache policy ignored Accept-Encoding.

Therefore, build a test matrix across **hops** and **client types**.

### 14.1. Minimum Test Matrix

| Target called | Accept-Encoding | Expected when response is large enough / compressible |
| --- | --- | --- |
| Origin Boot compression enabled | `gzip` | Gzip if container supports and policy matches |
| Origin Boot compression disabled | `gzip` | Identity |
| NGINX gzip enabled + origin identity | `gzip` | Gzip generated by NGINX |
| NGINX gzip enabled + origin identity | `identity` | Identity, no Content-Encoding gzip |
| CDN with Brotli and gzip | `br, gzip` | Valid coding chosen by CDN, typically br when policy supports |
| CDN receiving gzip-only viewer | `gzip` | Gzip or valid identity, never br |
| CDN receiving identity | `identity` | Must not return gzip/br body |
| Personal API | `gzip` or `br` | Not shared-cached by CDN; compressed per security policy |
| Short response / unsupported MIME | `gzip` | Usually identity per threshold/filter |
| SSE/streaming | Any | Not batched long, event latency meets target |

Do not test with only one URL and one browser; test at least HTML, JS/CSS, large JSON, small JSON, personal responses, 304, and downloads/ranges where used.

### 14.2. Using curl While Preserving Raw Bytes

To verify whether a gzip response actually carries compressed bytes:

```bash
curl -sS -D headers.txt -o body.bin \
  -H 'Accept-Encoding: gzip' \
  https://example.com/api/catalog
```

Open `headers.txt`; if `Content-Encoding: gzip` is present, `body.bin` contains compressed bytes. Use `gzip -dc body.bin` on machines with GNU gzip to decompress; or send a second request with `curl --compressed` to inspect decoded text:

```bash
curl -sS --compressed https://example.com/api/catalog
```

Do not attempt to gunzip `body.bin` if headers report `identity` or another coding like `br`. On Windows, use `curl.exe` and a suitable decompression tool. Remember HTTP 304 can occur if requests include conditional headers; avoid sending `If-None-Match` when measuring 200 body bytes.

### 14.3. Compare Headers, Not Just Bodies

```bash
curl -sS -I -H 'Accept-Encoding: gzip' https://example.com/app.js
curl -sS -I -H 'Accept-Encoding: identity' https://example.com/app.js
```

`-I` sends **HEAD**; not every proxy/cache handles HEAD identically to GET. Use GET with `-D - -o /dev/null` when verifying real compression because some servers differ on Content-Length, body, or policies for HEAD. Check these headers:

- `Content-Encoding`: final coding delivered to the client.
- `Vary`: request headers determining the representation.
- `Content-Type`: original media type.
- `Content-Length`: bytes of the encoded response if present.
- `Cache-Control` and `Age`: cacheability and age of cached copy.
- CDN-specific headers like `X-Cache`/`CF-Cache-Status` if provided by the vendor: hit/miss/edge status (names vary).
- `ETag`/`Last-Modified`: revalidation and variant consistency.
- `Server-Timing` or supporting metrics: distinguish origin vs. edge time where available.

### 14.4. Sequential Two-Client Test Scenario

1. Request `Accept-Encoding: gzip` from the CDN, saving headers and bytes.
2. Immediately call the **same URL** with `Accept-Encoding: identity`.
3. If the CDN hits, confirm the second body is identity with no `Content-Encoding: gzip`.
4. Call with gzip again and confirm successful decompression matching the decoded identity representation.
5. If the CDN supports Brotli, repeat with `Accept-Encoding: br`, confirming br is never served to gzip-only clients.
6. Repeat across cache expiration/revalidation, invalidation, and new version deployments.
7. For personal data, test two distinct users and verify the CDN **never** reuses user A's private response for user B.

The last step tests data security, not just compression correctness.

## 15. Observing Performance and Analyzing Metrics

### 15.1. Metrics to Track at Each Hop

| Metric | How to interpret |
| --- | --- |
| Uncompressed response bytes | Total logical payload bytes before compression |
| Encoded response bytes | Actual wire bytes for the content coding |
| Compression saving % | `(1 - encoded/original) × 100%` when original > 0 |
| App CPU / proxy CPU / edge costs | Which layer bears compression work |
| CDN cache hit ratio | Share of responses served from edge, affected by variant keys |
| p95/p99 TTFB | Time to first byte; can increase due to buffering |
| p95/p99 total time | Total client response completion time |
| Origin bandwidth | Bytes between app/proxy/CDN, different from viewer bandwidth |
| 4xx/5xx / decode failures | Issues from negotiation, caching, or servers |

Measured example: 100 KB identity JSON, 18 KB gzip, 15 KB br. Gzip saves 82%, br saves 85% compared to identity. **This is an arithmetic example, not a universal benchmark.** If CPU to produce br is too high or CDN hit rate is 99%, compressing br at Spring Boot on every request may lose to edge compression.

### 15.2. Quick Spot Measurements with curl

Use curl to inspect timings and download size:

```bash
curl -sS -o /dev/null \
  -w 'code=%{http_code} download=%{size_download}B total=%{time_total}s\n' \
  -H 'Accept-Encoding: gzip' \
  https://example.com/api/catalog
```

`size_download` measures downloaded body bytes from curl/libcurl's perspective and can differ from decompressed application data; confirm curl mode and actual body. `time_total` covers a single end-to-end request; p95/p99 requires many controlled samples rather than conclusions from one run.

Before comparing, hold route, TLS handshake reuse/keep-alive, edge geography, cache hit/miss, concurrency, content size, and server version steady. Separate **fast cache hits** from **compression size savings**, because the two can mask each other's effects.

### 15.3. Recommended Rollout Order

- **Baseline:** record headers/byte sizes/latency/CPU and cache hits before changing anything.
- **Assign owners:** define the compression layer for each route group (public/private/static/dynamic).
- **Enable compression at one layer:** app OR NGINX OR CDN, not blindly everywhere at once.
- **Verify HTTP correctness:** Accept-Encoding variants, Vary, status, Content-Type, ETag, 304, 206/ranges.
- **Verify security:** private responses bypass shared cache; secret-reflecting routes are not dangerously compressed.
- **Load test:** CPU/bandwidth/TTFB/p95/p99 across near and distant networks.
- **Canary rollout:** watch decode errors/cache hits before full rollout.
- **Keep rollback ready:** disable compression at the newly enabled layer without causing other app/CDN layers to emit broken metadata.

## 16. Common Errors and Remediation

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `Content-Encoding: gzip`, yet browser cannot read it | Body is not gzip, double-encoded, or truncated bytes | Inspect raw bytes, proxy transforms, Content-Length |
| Client sent only `identity`, yet received gzip | Proxy/CDN ignored Accept-Encoding or bad cache key | Fix negotiation and variant caching |
| High CDN cache hit rate, yet random JS/CSS errors | Missing `Vary`, cache variants mixed | Check `Vary: Accept-Encoding` and CDN cache policy |
| Compression enabled, yet response is not gzipped | MIME mismatch, small payload, unsupported request, different status/connector | Check properties, Content-Type, Accept-Encoding, actual bytes |
| 2KB API response shows no gzip | Threshold, Content-Length, or container/streaming | Test larger body and verify headers |
| Origin sends gzip, NGINX `gzip on` shrinks size no further | NGINX normally does not re-gzip already-gzipped bodies | Pick one compression point; measure CPU rather than expecting “double compression” |
| p95 TTFB climbs after enabling compression | Buffering, encode CPU, or resource contention | Lower level, compress at edge, exclude SSE |
| 304/ETag misbehaves | Validators not tied to variant | Generate/map ETags per variant, preserve Vary, test revalidation |
| Download resume fails after compression | Range offsets of encoded vs. identity representation | Check 206/Content-Range, avoid arbitrary transforms |
| Private data appears for another user | Shared cache mis-cached authenticated response | Bypass CDN shared cache, fix Cache-Control, and purge |
| `no-store` present, yet response still gzipped | `no-store` does not forbid compression | Use dedicated compression policy/`no-transform` when needed |
| Every Spring pod's CPU spikes after enabling gzip | Origin compressing every request | Consider proxy/CDN or precompression |
| Brotli not selected despite browser support | CDN/module disabled, origin pre-gzipped, or stale cache | Check edge policy and how CDN handles encoded origins |
| Cache hit rate drops after adding Vary | Too many encoding/header variants | Use CDN normalization; avoid unnecessary Vary fields |
| `.gz` file downloads as binary file | Server failed to emit valid Content-Encoding/Content-Type | Configure precompressed resource serving properly |

## 17. Self-Check Exercises

**Exercise 1 — same URL, two clients.** Client A sends `Accept-Encoding: gzip`; client B sends only `identity`. The CDN caches one gzip body by URL. What went wrong?  
**Answer:** Cache key/`Vary` ignored representation variants; B does not accept gzip. Fix content negotiation and cache variant policy.

**Exercise 2 — where to put gzip?** A public website has rarely changing hashed JS/CSS and high CDN hit rates. Should gzip be enabled on every Spring Boot pod?  
**Hint:** Not necessarily. Prefer precompressing assets at build time or compressing at CDN/edge, check cache policies, and measure bandwidth/CPU. Origin gzip may bring minimal benefit when most requests hit the CDN.

**Exercise 3 — user-data API.** `GET /account` returns personal info authenticated by cookie. Should you set `Cache-Control: public, max-age=3600` just so the CDN compresses fast?  
**Answer:** No. Compression and caching decisions are independent; never let shared caches reuse personal responses. Use `private`/`no-store` and CDN bypass as required.

**Exercise 4 — Content-Length.** Identity JSON is 12,000 bytes, gzip is 1,900 bytes, and a filter manually sets `Content-Length: 12000` on the encoded response. Valid?  
**Answer:** No. Content-Length of an encoded representation, if emitted, must match the bytes actually transmitted. Let the server/proxy compression module manage it.

**Exercise 5 — ETag.** Two byte-different identity and gzip variants share the same strong ETag. Is that okay?  
**Answer:** Violates strong validator semantics across distinct encoded representations. Manage validators per representation or use intermediary-appropriate handling; still keep `Vary`.

**Exercise 6 — no-store.** A response has `Cache-Control: no-store`, yet NGINX still gzips the body. Is NGINX violating `no-store`?  
**Answer:** No. `no-store` governs caching, not forbidding response compression. To prevent transforms, apply suitable compression rules and review `no-transform`.

**Exercise 7 — streaming.** After enabling gzip on ingress, SSE receives events in big batches instead of real time. What to check?  
**Answer:** Ingress/CDN buffering and compression flush, MIME type, route bypass, and streaming settings; do not simply raise timeouts when data is stuck in compressor/buffers.

**Exercise 8 — NGINX header.** Why use `proxy_set_header Accept-Encoding "";` on the NGINX→Boot hop in Option B?  
**Answer:** So the origin prefers returning identity, keeping NGINX as the chosen compression layer. Viewer headers arriving at NGINX still govern NGINX's gzip decision; check how upstream proxies/CDNs modify headers too.

**Exercise 9 — compressing better by doing it twice.** Spring Boot already sends `Content-Encoding: gzip`. Is enabling gzip in the CDN to “compress further” a sensible optimization?  
**Answer:** Generally no. Use pass-through, contract-compliant transcoding if truly needed, or move compression ownership to the edge; recompressing already-compressed data wastes CPU without shrinking size.

**Exercise 10 — Brotli and origin.** Browsers support br/gzip, yet the CDN only receives gzip from origin. Can you guarantee browsers always get br?  
**Answer:** No. It depends on whether the CDN transcodes or only compresses identity origin responses, cache policies, MIME/size, and already-cached objects; inspect headers at the browser.

## 18. Production Readiness Checklist

- [ ] URLs grouped into public static, public dynamic, private/authenticated, streaming, and already-compressed binaries.
- [ ] Primary compression layer designated per group: Boot, NGINX, CDN, or build.
- [ ] `server.compression.enabled` enabled only where Spring Boot is actually assigned compression duty.
- [ ] MIME types, thresholds, and algorithms verified against the actual runtime/version.
- [ ] Proxies do not blindly recompress encoded bodies and do not strip/corrupt `Content-Encoding`.
- [ ] `Vary: Accept-Encoding` is present whenever representations vary by client negotiation.
- [ ] CDN cache policies distinguish/normalize variants properly; URL alone is not the sole cache key when codings differ.
- [ ] Private/authenticated responses stay out of shared caches; cookies and Authorization checked.
- [ ] `Content-Length`, `ETag`, 304/206/ranges, and `Content-Type` remain consistent across layers.
- [ ] No wasted compression on already-compressed files; static hashed assets have proper cache lifetimes/versioning.
- [ ] SSE/streaming measured for buffering/flush latency; sensitive routes assessed for BREACH risks.
- [ ] Tested gzip, br (when available), identity, and compression-incapable clients on the same URL at each hop.
- [ ] Tested cache hit/miss, invalidation, and rolling deployments across multiple asset versions.
- [ ] Measured saved bytes, CPU, p95/p99 TTFB, total latency, edge hit ratio, and decode errors before/after.
- [ ] Able to roll back compression at one layer without breaking HTTP correctness at other layers.

## Official Documentation

1. [Spring Boot 3.3 — Common Application Properties / Server Compression](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
2. [Spring Boot 3.3 — Web Server Compression](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
3. [NGINX — ngx_http_gzip_module](https://nginx.org/en/docs/http/ngx_http_gzip_module.html)
4. [NGINX — Compression and Decompression](https://docs.nginx.com/nginx/admin-guide/web-server/compression/)
5. [NGINX — gzip_static module](https://nginx.org/en/docs/http/ngx_http_gzip_static_module.html)
6. [Amazon CloudFront — Serve compressed files](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/ServingCompressedFiles.html)
7. [RFC 9110 — HTTP Semantics: Accept-Encoding, Content-Encoding, Vary, Range](https://www.rfc-editor.org/rfc/rfc9110)
8. [RFC 9111 — HTTP Caching: Vary, Cache-Control, no-transform](https://www.rfc-editor.org/rfc/rfc9111)

**Conclusion:** effective HTTP compression does not mean “turn on gzip everywhere”. Choose the **right compression layer**, keep content negotiation and metadata consistent, manage caches by **encoding variant**, and strictly separate public from private data. A simple, measurable, standards-compliant setup beats a multi-layer transformation chain that is hard to control.