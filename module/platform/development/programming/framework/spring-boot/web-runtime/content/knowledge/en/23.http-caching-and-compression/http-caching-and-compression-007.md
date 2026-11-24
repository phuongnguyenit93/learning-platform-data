# Compression Size Thresholds and Impact on CPU and Latency

**Module:** Spring Boot - web-runtime  
**Parent topic:** HTTP Caching and Compression

## 1. Problem: Why Shouldn't Every Response Be Compressed?

A Spring Boot application returns three kinds of HTTP responses:

- Action-acknowledgment APIs with JSON of only a few hundred bytes.
- List APIs with JSON of tens or hundreds of kilobytes.
- HTML pages, CSS, JavaScript, images, and downloadable files of varying sizes.

When clients support **gzip**, compressing responses can significantly reduce transferred bytes over the network, especially for JSON/HTML/JavaScript containing many repeated strings. Yet compression has a cost: the server must spend **CPU** to encode, may need to buffer data, the client must decompress, and this extra work can increase wait times on worker threads or queues under heavy load.

For very small responses, gzip carries its own headers and metadata, so savings can be smaller than the compute cost—or **the compressed response can even be larger than the original**. If the body is already JPEG/PNG/WebP/MP4/ZIP, recompressing is rarely worthwhile. Conversely, a highly repetitive 500 KB JSON payload over a slow network can benefit substantially.

The **compression threshold** is one of the conditions the server checks before deciding whether to compress a response. In Spring Boot, it is configured via **server.compression.min-response-size**.

After this lesson, you will:

1. Understand **Accept-Encoding**, **Content-Encoding**, **Vary: Accept-Encoding**, and distinguish body compression from HTTP/2 header compression.
2. Know the **server.compression.enabled**, **min-response-size**, and **mime-types** properties in Spring Boot 3.x and their real defaults.
3. Understand threshold limitations when **Content-Length is unknown**, and with streamed responses, proxies, caches, and already-compressed files.
4. Run a **Spring Boot 3.x / Java 17+** example yourself to test small/large JSON with curl.
5. Measure impacts on **CPU, throughput, bandwidth, TTFB, and p95/p99 latency**, choosing thresholds from measurements rather than one fixed number for all systems.

## 2. HTTP Content Negotiation: Compression Happens Only When Conditions Match

The client tells the server which content encodings it understands:

~~~http
GET /api/items HTTP/1.1
Host: example.test
Accept-Encoding: gzip, br
~~~

The server may choose a supported algorithm and respond:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding

<gzip-compressed JSON bytes>
~~~

The line in angle brackets merely describes a binary payload, not literal JSON. The browser decompresses the response per **Content-Encoding** before passing the logical content to the application.

Three key headers:

| Header | Where? | Role |
| --- | --- | --- |
| **Accept-Encoding** | Request | Client advertises algorithms it can decode, e.g., **gzip, br, zstd**; may use **q-values** for priority. |
| **Content-Encoding** | Response | Tells the client which content encoding the server applied, e.g., **gzip**. Absence usually means no declared content encoding was applied. |
| **Vary: Accept-Encoding** | Response | Helps shared caches distinguish representations across different Accept-Encoding values, avoiding serving gzip bytes to clients that cannot decode them. |

**The server is not forced to compress just because the client sends Accept-Encoding: gzip.** It also checks configuration, MIME type, response size, system state, whether content is already compressed, and connector/proxy capabilities.

**Content-Type** stays the original content type, such as **application/json**. **Content-Encoding: gzip** describes the body's encoding form; it is not a new MIME type. When a representation is compressed, **Content-Length (if present) describes the encoded representation's size on the wire**, not the decompressed JSON length. With chunked transfer or HTTP/2 DATA frames, Content-Length may be omitted.

Example when the client declines gzip:

~~~http
GET /api/items HTTP/1.1
Host: example.test
Accept-Encoding: identity
~~~

**identity** means an unencoded representation. The server is permitted to return the original body if valid under negotiation. Proxies/CDNs may transform the representation at a later hop, so always measure the actual response at the client.

### Body Compression Differs from HTTP/2 and HTTP/3 Header Compression

- **gzip/br/zstd via Content-Encoding** operates on the **HTTP representation body** (HTML/JSON/CSS/JS).
- **HTTP/2 HPACK** compresses **header fields** between two HTTP/2 peers; **HTTP/3 QPACK** likewise compresses headers. Neither automatically gzips JSON bodies.
- **Transfer-Encoding: chunked** in HTTP/1.1 is a data transfer framing technique, **not content compression**.
- **TLS** encrypts the transport channel; it does not determine gzip or compression size thresholds.

Therefore, upgrading from HTTP/1.1 to HTTP/2 or enabling TLS **does not replace** response compression configuration.

## 3. server.compression.* Properties in Spring Boot 3.x

According to **Spring Boot 3.3** documentation, the core settings are:

| Property | Spring Boot 3.3 default | Function |
| --- | --- | --- |
| **server.compression.enabled** | **false** | Enables embedded server HTTP response compression when conditions are met. |
| **server.compression.min-response-size** | **2KB (2,048 bytes)** | Minimum **Content-Length** threshold required to consider compressing a response. |
| **server.compression.mime-types** | A list of text/JSON/XML MIMEs | Restricts which response content types are eligible for compression. |
| **server.compression.excluded-user-agents** | No default list | Excludes specific User-Agents from compression when compatibility requires it. |

Spring Boot 3.3's **default mime-types list**:

~~~text
text/html
text/xml
text/plain
text/css
text/javascript
application/javascript
application/json
application/xml
~~~

Some guides only set **server.compression.enabled=true** and assume every response gets gzipped. That is wrong: the client must negotiate a supported encoding, the MIME must be in the list, and the size must satisfy the server's criteria. Types like **image/jpeg**, **image/png**, and **application/zip** are absent from the default list because those formats are already compressed or gain little.

**2KB is not 2,000 bytes.** Spring Boot's DataSize type uses binary sizes: **1KB = 1,024 bytes**, so **2KB = 2,048 bytes**, **4KB = 4,096 bytes**, **16KB = 16,384 bytes**.

### Example: Enabling Compression for JSON/HTML/JS

~~~properties
server.compression.enabled=true
server.compression.min-response-size=4KB

# If mime-types is omitted, Spring Boot 3.3 uses the default list.
# The example below explicitly declares all types to compress:
server.compression.mime-types=text/html,text/plain,text/css,text/javascript,application/javascript,application/json,application/xml,text/xml
~~~

**min-response-size=4KB** is an **experimental choice**, not universally optimal. For a 3 KB JSON payload, this threshold avoids spending effort compressing; for a 100 KB JSON payload, compression usually helps if the network is slow enough and CPU has headroom. Changing the value requires measuring real workloads.

**mime-types** declares the full supported list in this setting; do not assume assigning one MIME type “appends” it to the default list. Avoid overly broad settings, especially adding **application/octet-stream** or arbitrary image/video types.

### Properties You Should Not Guess

**server.compression.min-response-size** is a **response length** threshold, **not** client download bytes per second, CPU speed, or gzip compression level. In Spring Boot 3.3, **there is no standard cross-container property named server.compression.level** to tune gzip level uniformly across Tomcat, Jetty, Undertow, and Reactor Netty. If you need algorithm/level tuning, check the specific connector or proxy/CDN configuration.

Spring Boot 3.3 documentation confirms response compression support for embedded **Tomcat, Jetty, Undertow, and Reactor Netty**, yet each server differs in implementation details. Never assume enabling a Boot flag automatically adds Brotli or Zstandard support on the backend; **gzip** is the common baseline, whereas **br/zstd** depend on server, library versions, or CDN/edge.

## 4. When Is the Threshold Evaluated? The Unknown Content-Length Problem

The property docs define **min-response-size** as the **minimum Content-Length value required for compression**. This phrasing matters: the server needs size information **at decision time**.

For a buffered response with a known length upfront:

~~~text
Content-Length = 1024 B   ; threshold = 4096 B -> usually not compressed
Content-Length = 8192 B   ; threshold = 4096 B -> may be compressed
~~~

However, for streaming responses, async outputs, or incrementally emitted bodies, **Content-Length may not be known upfront**. The connection handler must decide how to write the response while data is still arriving. For example, Tomcat's documentation notes that when compression is enabled and length is unknown, the connector **may still compress** even though intuition says “under 4 KB shouldn't compress”.

Consequently:

- **4KB is not an absolute guarantee that every response under 4KB remains uncompressed.**
- A response sent with a known **Content-Length** can behave differently from one using chunked transfer or a reactive stream.
- Containers/versions/filters/proxies can make compression decisions at different stages.
- If multiple compression layers exist, the final outcome can be altered by a **reverse proxy/CDN**, not just Spring Boot.
- Test using **real HTTP and real environment settings**, not merely by reading application.properties.

For instance, **Flux** in WebFlux, **StreamingResponseBody** in MVC, Server-Sent Events (**text/event-stream**), or per-item flushed responses may have unknown length. Do not assume a 300-byte response below the threshold definitely stays uncompressed; nor assume compression helps streaming, because gzip needs flushing and can increase per-event latency.

### Does Compression Change Content-Length?

If the original response has **Content-Length: 8203**, when the server compresses at the connector, wire bytes become smaller. The server must update or omit Content-Length to match the encoded representation. Do not compare the post-gzip **Content-Length** against the threshold, which was evaluated before or during encoding according to the container's design.

A compressed response can be sent using **Transfer-Encoding: chunked** on HTTP/1.1; **HTTP/2** uses DATA frames. Neither proves compression succeeded or failed: inspect **Content-Encoding** and actual received bytes.

## 5. How Do CPU, Latency, and Bandwidth Trade Off?

Imagine the path when the server compresses:

~~~text
API/Controller produces data
       |
       v
Serialize JSON / render HTML
       |
       v
Compression encoder (CPU + buffer/flush)
       |
       v
Connector, socket, TLS, network
       |
       v
Browser/client decompression (CPU)
       |
       v
Parse JSON, render UI
~~~

On the server, compression competes for CPU against JSON serialization, business logic, garbage collection, TLS, and concurrent requests. When CPU is idle, encoding cost may be tiny. When CPU approaches saturation, a bit of extra CPU **per request** can sharply grow queues and worsen **p95/p99 latency**.

Let:

- **S** = uncompressed body bytes.
- **C** = compressed body bytes.
- **B** = effective network throughput (bytes/second).
- **Tenc** = encoding CPU/wall time; **Tdec** = client-side decoding time.
- **Tbuf** = buffering, flush wait, or coordination delay; **Tqueue** = CPU/network queueing delay under overload.

A simplified comparison model (not an exact equation for every server):

~~~text
Uncompressed: Traw  ~= Tcommon + S / B
Compressed:   Tgzip ~= Tcommon + Tenc + C / B + Tdec + Tbuf

Network time saved ~= (S - C) / B
Compression helps latency if network savings
    exceed added encode + decode + buffer/queue costs.
~~~

**Tcommon** covers largely constant steps such as business processing; in reality CPU and network transfer can **overlap in a pipeline**, so total time is not always a strict sequential sum. **TTFB** can degrade when the encoder buffers until enough data/flush triggers, whereas **time-to-last-byte** can improve thanks to fewer total bytes.

Illustrative example, **not a real benchmark**:

- Original JSON is 50 KB, gzipped to 10 KB → saves 40 KB.
- At 2 MB/s effective throughput, transfer time saves roughly 20 ms.
- If encoding takes 3 ms, decoding 0.5 ms, and buffering 1 ms, the net result can **save roughly 15.5 ms** in a simple additive model.
- On a 100 MB/s network, sending 40 KB less saves only ~0.4 ms; the same encode/decode costs can worsen total latency, especially when server CPU is busy.

The takeaway is not “always disable gzip on LANs”. Because real payloads, CPU, queues, RTT, caches, and browsers differ, **measure in your deployment context**. Repetitive JSON compresses well; near-random data does not share the same ratio.

### Compression Ratio

Definition:

~~~text
Compression ratio (size ratio) = C / S
Bandwidth saved (%) = (1 - C / S) * 100%
~~~

For example, S = 100 KB, C = 25 KB → compressed size is 25% of original, saving 75% of body bytes. Remember **HTTP headers, TLS records, and packet overhead** still exist; total network bytes do not shrink by an exact 75% under all conditions.

### Throughput and CPU Across Many Requests

If a request requires **2 ms extra CPU** for encoding and the server handles **500 requests/second**, theoretical CPU demand rises by roughly **1 CPU-second per second** just for compression (when numbers reflect actual CPU time). This is a load calculation example, not a universal gzip benchmark. Across multiple cores, work can spread out; on a saturated event loop or under cgroup CPU quotas, added CPU also triggers scheduling delays and tail latency.

**A handful of curl requests is not enough to pick a threshold**. Also measure under concurrency, CPU throttling, and p99.

## 6. Which MIME Types Should Be Compressed?

| Data type | Characteristics | Initial decision |
| --- | --- | --- |
| **text/html**, **text/css**, **application/javascript** | Text with heavy repetition, usually saves bytes. | Enable compression if payload is large enough. |
| **application/json**, **application/xml**, **text/plain** | Compressible text data, ratio depends on payload. | Test on real data; usually beneficial. |
| **application/x-ndjson**, **text/event-stream** | Can stream long-lived, needs flushing and per-record latency. | Evaluate codec, buffering, and latency separately; do not blindly apply single-blob JSON policy. |
| **image/jpeg**, **image/png**, **image/webp**, **image/avif** | Formats usually already compressed. | Do not re-gzip by default. |
| **application/zip**, gzip, optimized PDF, MP4 | Likely already compressed or yields minimal gains. | Avoid re-encoding unless real metrics prove value. |
| **application/octet-stream** | Generic MIME, unknown contents. | Do not add just out of a desire to compress everything. |
| **application/pdf** | Depends on structure/internal compression. | Check actual reduction and Range/download traits; rarely a priority. |

**For prebuilt static files**, one option is generating **.br/.gz precompressed assets** at build time/CDN and serving them by Accept-Encoding instead of recompressing the exact same bytes on every request. For immutable paths, precompression cuts runtime CPU. Still, configure **Vary**, **Content-Encoding**, content type, and cache keys properly, along with matching URL fingerprints/ETags. Do not assume enabling `server.compression.enabled` automatically creates `.br` files on disk.

## 7. Complete Spring Boot 3.x + Java 17+ Demo: Testing the 4KB Threshold

This demo uses **spring-boot-starter-web** and default embedded **Tomcat**. It sets a known **Content-Length** upfront so threshold behavior is clear without depending on unknown streaming body sizes.

### 7.1. Dependency

In a Spring Boot 3.x project with Java 17+, Gradle wrapper, and Boot plugin configured, in **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

### 7.2. application.properties

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.compression.enabled=true
server.compression.min-response-size=4KB
server.compression.mime-types=application/json,text/html,text/plain,text/css,text/javascript,application/javascript,application/xml,text/xml
~~~

The 4KB setting is for this example and still requires **Accept-Encoding: gzip** on the request. If you add Spring Security, put a reverse proxy in front, or swap embedded servers, re-evaluate the results.

### 7.3. One Runnable Java File

Create **src/main/java/com/example/compression/CompressionDemoApplication.java**:

~~~java
package com.example.compression;

import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class CompressionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompressionDemoApplication.class, args);
    }
}

@RestController
class CompressionController {

    @GetMapping(
            value = "/api/payload/{characters}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<byte[]> payload(@PathVariable int characters) {
        if (characters < 0 || characters > 65536) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid payload size");
        }

        String json = "{\"data\":\"" + "a".repeat(characters) + "\"}";
        byte[] body = json.getBytes(StandardCharsets.UTF_8);

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                // Sets length before the HTTP connector compresses the response.
                .contentLength(body.length)
                .body(body);
    }
}
~~~

The file has **one public top-level class** matching the filename; package-private **CompressionController** is scanned by Spring Boot in the same package. **String.repeat** has been available since Java 11 and works on Java 17. No extra class files are needed.

All generated JSON bodies are valid and contain ASCII characters. For **N 'a' characters**, **{"data":"..."}** is **N + 11 bytes**, specifically:

| URL | Raw UTF-8 body size | Compared to 4KB threshold |
| --- | --- | --- |
| **/api/payload/256** | **267 bytes** | Smaller than 4,096 bytes |
| **/api/payload/8192** | **8,203 bytes** | Larger than 4,096 bytes |
| **/api/payload/65536** | **65,547 bytes** | Larger than 4,096 bytes |

**CacheControl.noStore()** reduces cache interference while observing the demo; it does not mean every JSON endpoint in production should use no-store. **contentLength(body.length)** lets the container know the uncompressed size; when gzip actually applies, the final Content-Length header on the wire may change or be omitted depending on how the connector sends compressed responses.

**Demo limitation:** repeated **a** characters compress **extremely well**, and do not represent real JSON containing diverse, less-compressible data. The demo verifies configuration; benchmarking needs payloads, sizes, and repetition rates representative of production traffic.

### 7.4. Run the Server

~~~bash
./gradlew bootRun
~~~

On Windows, run **gradlew.bat bootRun** in cmd/PowerShell. Once running, use another Bash terminal to test HTTP.

### 7.5. Test Small and Large, Keeping Raw Encoded Bytes

**Small 267 B test:**

~~~bash
curl -sS -D small.headers -o small.wire \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/payload/256
~~~

**Large 8,203 B test:**

~~~bash
curl -sS -D large.headers -o large.wire \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/api/payload/8192
~~~

**Inspect headers and downloaded bytes:**

~~~bash
grep -iE '^(HTTP/|content-type:|content-encoding:|content-length:|vary:|cache-control:)' \
  small.headers large.headers
wc -c small.wire large.wire
~~~

With default Tomcat and eligible responses:

- **small.headers** normally **lacks Content-Encoding: gzip** because Content-Length 267 B is under 4KB.
- **large.headers** usually includes **Content-Encoding: gzip**; **large.wire** holds gzip bytes, far smaller than 8,203 B because repeated `'a'` compresses heavily.
- **Vary: Accept-Encoding** should be checked whenever compression negotiation happens; if an intermediary handles representations, check both at the client and CDN.
- Wire Content-Length **does not necessarily stay 8,203** after gzip.

**Why avoid --compressed when measuring raw body size?** The **curl --compressed** flag automatically advertises supported encodings **and decompresses the body before writing -o**. That is convenient for checking logical content, yet the saved file **does not represent encoded bytes on the wire**. In the two commands above, we explicitly pass **-H 'Accept-Encoding: gzip'** and save the raw response body without curl auto-decompression.

After confirming **large.headers has Content-Encoding: gzip**, you can verify file validity:

~~~bash
gzip -t large.wire
gzip -cd large.wire | head -c 80
~~~

The first command outputs nothing and exits with code 0 if the gzip bytes are valid; the second prints the start of the decompressed JSON. If the header does not indicate gzip, do not run `gzip -t` and conclude the file/application is broken—investigate why the response was not compressed.

**Test auto-decompressing client:**

~~~bash
curl -sS --compressed \
  http://localhost:8080/api/payload/8192 \
  -o large-decoded.json

wc -c large-decoded.json
~~~

The decoded file is **8,203 bytes** regardless of whether wire transfer was gzipped, assuming valid logical output. This test is **not** a way to measure bandwidth savings.

### 7.6. Compare Against Uncompressed Requests

~~~bash
curl -sS -D identity.headers -o identity.wire \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/api/payload/8192

wc -c identity.wire large.wire
~~~

In an environment without an intermediary transforming responses, **identity.wire** is **8,203 bytes**, while **large.wire** is smaller when gzip actually activates. Exact compressed byte counts depend on the gzip encoder and settings, so do not assert a hardcoded figure.

Use **curl -w** to inspect TTFB and total time:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Encoding: identity' \
  -w 'identity ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  http://localhost:8080/api/payload/8192

curl -sS -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  -w 'gzip ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  http://localhost:8080/api/payload/8192
~~~

**Measurements from a single localhost request are virtually useless for drawing production performance conclusions** due to noise, JVM warm-up, connection setup, and memory caches. They only illustrate how to capture metrics. On Windows without **/dev/null**, substitute an appropriate temp output file or run in a Bash terminal.

## 8. What Happens When Raising or Lowering the Threshold?

Assuming the same server and responses with known Content-Length:

| Change | Possible effect | Risk to measure |
| --- | --- | --- |
| **2KB → 1KB** | More small responses get compressed; saves a few bytes per request. | Higher CPU/QPS cost, gzip overhead, small-payload latency may worsen. |
| **2KB → 4KB** | Skips compressing 2–4KB responses; fewer encode operations. | More transferred bytes for that group, affecting slow-network clients. |
| **4KB → 16KB** | Compresses only larger bodies, reducing work on small/medium requests. | Loses bandwidth savings on compressible 5–15KB JSON payloads. |
| **Very low threshold** | Attempts to compress almost all text responses. | CPU climbs; many tiny payloads shrink negligibly or grow. |
| **Too high threshold** | Less encoder work. | Bandwidth/egress costs and transfer times climb sharply if medium/large text payloads dominate. |

These are likely trends, **not immutable laws**: with unknown Content-Length, containers/proxies may compress differently; HTTP caching, static precompression, and request mix also alter outcomes.

Do not pick a threshold by optimizing **compression ratio** alone. Examine **latency (especially p95/p99)**, throughput, CPU usage, CPU throttling, error rates, and egress costs. The threshold saving the most bytes is not necessarily the one delivering the best user experience.

### Two Contrasting Examples

**Case A — Small, high-throughput API:** An API called thousands of times per second with a 700 B average body. Enabling compression down to a few bytes generates massive encode work for negligible byte savings. Keeping a moderate threshold, cutting request volume, or using caching/HTTP keep-alive can be far more effective.

**Case B — Large JSON dashboard over mobile networks:** A 400 KB response with many repeated fields for clients on weak networks. Compression can slash transferred bytes, improving completion time and data usage. CPU cost may be reasonable, or offloaded to the edge/CDN if the response is cacheable.

Decisions must come from measurements on your traffic, rather than copying either value above as a universal default.

## 9. Buffering, Streaming, and Time to First Byte

A normal HTTP response can be built completely before sending; a streaming response emits incrementally. Compressing streams introduces dedicated trade-offs:

~~~text
Server emits event 1 ----+
Server emits event 2 ----+--> encoder holds buffer? --> flush --> client
Server emits event 3 ----+
~~~

If the gzip encoder waits to fill a buffer before emitting a compressed block, **TTFB** or inter-event gaps at the client can grow. Some connectors/streaming frameworks support flushing, though frequent flushes lower compression ratios and raise overhead.

Cases needing dedicated testing:

- **Server-Sent Events (text/event-stream)**: the goal is usually low per-event arrival latency. If compression batches events, you can exclude SSE routes from compression or tune connector/proxy flushing; not every text MIME type should be compressed.
- **NDJSON (application/x-ndjson)**: may stream per record; balance ratio against latency/buffering across containers and proxies.
- **StreamingResponseBody** in Spring MVC or **Flux<DataBuffer>** in WebFlux: length may be unknown; do not blindly assume a rigid “4KB rule”.
- **Large file downloads**: if files are already compressed, adding gzip wastes CPU without shrinking bytes. If static files already have precompressed `.gz`/`.br` copies, serving the right representation beats runtime compression.
- **HTTP/2 multiplexing**: multiple streams share a connection, yet compression CPU for one stream still contends for shared resources; HPACK header compression does not eliminate body gzip costs.

If proxies like Nginx or CDNs buffer responses, inspect both **server → proxy** and **proxy → browser**. The backend may flush immediately while the edge buffers the response, or the backend sends raw while the edge gzips on output. Measuring only from the browser cannot isolate which stage introduced delay without tracing/metrics.

## 10. Caching and Compression: Avoiding Wrong Representations

When a public cacheable endpoint supports both gzip and identity:

~~~text
GET /assets/app.js (Accept-Encoding: gzip)     -> gzip representation
GET /assets/app.js (Accept-Encoding: identity) -> raw representation
~~~

**Vary: Accept-Encoding** is the key for shared caches to distinguish representations under negotiation. If a CDN omits encoding from its cache key, a client without gzip support may receive unexpected gzip bytes, or cache hits/misses suffer.

**ETag** can be bound to both the representation and its content coding; do not assume one strong ETag applies to two byte-different representations. Verify how your server/CDN handles validators and **304 Not Modified** alongside compression; do not compare raw bytes against encoded bytes and assume an ETag is wrong merely due to length differences.

**Cache-Control** governs storage/reuse, **not whether gzip is enabled/disabled**. For example:

- HTML entrypoints usually need revalidation/short TTLs to pick up references to new assets.
- Fingerprinted assets can be cached long-term and **precompressed** once at build time.
- Private-data APIs need appropriate cache policies; never enable public caching just because gzip is enabled.
- For cached responses, origin compression CPU may only occur on a **cache miss**, so benchmarks must separate warm vs. cold caches.

**Never compress the same response twice.** If the backend already returned **Content-Encoding: gzip**, proxies must not blindly re-gzip without properly handling encoding. CDN/ingress and embedded server configs must clearly divide ownership: origin compresses, edge compresses, or serve precompressed representations.

### Caching Can Mask Compression CPU Cost

An API cached 99% at the CDN with a high TTL can be gzipped once at the edge and distributed thousands of times without making the JVM recompress every request. Conversely, an uncacheable personalized API makes the origin process every request. Thus gzip's CPU impact **depends on which layer actually compresses and the cache hit ratio**, not merely the percentage of traffic sending Accept-Encoding: gzip.

## 11. Proxies/CDNs Can Change Spring Boot Conclusions

Typical topologies:

**A. Client calls Spring Boot directly:** Boot's `server.compression.enabled`, mime, and threshold have clear effect. Measure Content-Encoding, bytes, JVM CPU, and network.

**B. Client → Nginx → Spring Boot:** Nginx may enable gzip, buffer, cache, or forward Accept-Encoding under different rules. Gzip seen by the client might come from **Nginx**, not Boot. Boot may return identity while Nginx compresses; or Boot returns gzip and Nginx passes it through.

**C. Client → CDN/ingress → multiple Spring Boot instances:** Edge picks br/gzip, caches variants, and serves browsers; JVMs may only emit identity internally. Thresholds at the CDN and Boot may differ; define which layer is the source of truth for encoding.

Common pitfalls:

- **CDN compresses JPEG/ZIP files** due to overly broad MIME rules, raising CPU without saving bytes.
- **Missing Vary or wrong cache key**, populating caches with unexpected variants.
- **Brotli enabled only at edge**, while direct localhost testing shows only gzip; falsely concluding Boot “isn't working”.
- **Both origin and proxy compress** while JVM metrics fail to reflect bytes delivered to the client.
- **Proxy response buffering** slows down SSE/streams even as wire bytes shrink.
- **Backend has known Content-Length, proxy streams without known length**, producing different threshold behavior across the two hops.

Capture headers and metrics at **each hop** when investigating high latency.

## 12. Compression and Security

Compression is a performance optimization, yet introduces risk when compressing **secrets alongside attacker-controlled data** in the same response. Size-measuring attacks like **BREACH** exploit ciphertext length changes based on substring similarity inside compressed responses, especially when secret tokens appear alongside reflected input.

Key precautions:

1. Never reflect user-controlled data casually next to sensitive tokens/secrets in the same compressed response.
2. For endpoints embedding **CSRF tokens or secrets** in HTML, assess the threat model and mitigations such as disabling compression on those responses, separating secrets from reflected content, intentional padding, token randomization, rate limiting, or suitable controls.
3. **HTTPS/TLS does not eliminate length side channels**; it protects content confidentiality, yet traffic sizes can still be observed in certain scenarios.
4. **Secure, HttpOnly, SameSite cookies** remain essential, yet do not automatically make a compressed page containing reflected secrets safe.
5. Never log raw bodies containing secrets just to measure compression ratios; measure by size buckets or sanitized data.

Additionally, a client decompressing a tiny response into huge data can face a **decompression bomb** from untrusted sources; clients also need body, decoded-size, and memory limits. **server.compression.*** configures server response compression—not inbound upload/request limits or client decompression caps.

## 13. Benchmark Workflow to Pick min-response-size with Evidence

**Step 1 – Select representative datasets.** Collect response classes: small JSON (0–2 KB), medium (2–16 KB), large (16–256 KB), HTML/JS/CSS, streams, and already-compressed files. Use secret-free test data with repetition characteristics matching production. Avoid benchmarking only the demo's repeated `'a'` string.

**Step 2 – Pick candidate thresholds.** For example, test **disabled**, **2KB**, **4KB**, **8KB**, and **16KB**. Do not pick a candidate merely because it is popular. Keep MIME policy, container, JVM heap, CPU limits, and client environment identical across runs.

**Step 3 – Verify HTTP functionality first.** For each case, confirm:

- Request **Accept-Encoding** is accurate; do not use curl auto-decompression when measuring encoded bytes.
- Response **Content-Encoding** is right; **Vary** and Content-Type are intact.
- Decompressed body matches logical bytes; exclude irrelevant 304/cache hits from measurements.
- Note whether responses have **Content-Length** or stream; record the difference.
- Check whether edge/CDN alters encoding; identify which layer compresses.

**Step 4 – Measure both latency and CPU under concurrency.** Use a suitable load tool (k6, Gatling, wrk/JMeter as fits your project) with a stable JVM warm-up. Capture simultaneously:

| Metric group | Indicators to observe |
| --- | --- |
| **HTTP latency** | p50, p95, p99, **TTFB**, time-to-last-byte, error rate |
| **Throughput** | Requests/s, responses/s, raw and encoded bytes transferred |
| **Server CPU** | CPU usage/time, cgroup throttling, runnable queue, thread/event-loop saturation |
| **Memory** | Heap/direct memory, allocation/GC, buffer sizes, active connections |
| **Network** | Egress bytes/s, client speed, RTT, packet retransmits where relevant |
| **Cache** | Origin vs. CDN hit rate, compressed variant cache hit/miss |
| **Client** | Decode time, CPU on low-end devices, parse/render time, page load effectiveness |

**Step 5 – Test across two network profiles.** Fast local networks can hide byte-reduction gains; mobile or high-latency links make gains clearer. Simulate RTT/bandwidth in a controlled manner; match production HTTP version and TLS. Keep **connection reuse**, cache hit ratio, client count, and endpoint mix consistent.

**Step 6 – Compare against SLO goals.** For example:

- If your SLO is p99 under 200 ms, do not trade a 20% egress cut for p99 breaching the SLO.
- If CPU budget is tight, a higher threshold or CDN precompression may beat compressing every small API.
- If users are typically on slow networks, compressing medium/large responses can yield big wins despite a few ms of encoding time.
- If an SSE endpoint requires events within a few hundred ms, measure per-event arrival and separate compression rules rather than optimizing size blindly.

**Step 7 – Canary and monitor.** Roll out to a fraction of traffic, watching tail latency, CPU throttling, compression ratio, request errors, cache behavior, and network egress. Keep rollback ready if SLOs degrade. Changing a threshold without real-world monitoring is merely a hypothesis, not a proven optimization.

### Measurement Pitfalls to Avoid

- **Running a few localhost curl calls:** too few samples, skewed by JIT warm-up, scheduler, and connection setup.
- **Running --compressed -o file and comparing file sizes:** curl already decompressed it, not measuring wire bytes.
- **Using an all-'a' payload:** artificial ratio that misrepresents real JSON responses.
- **Comparing cache-hit responses against cache-miss responses:** origin CPU and latency differ completely.
- **Not checking Content-Encoding:** you may think you're comparing gzip vs. identity while the server sent the same representation.
- **Looking only at average latency:** compression can worsen **p99** while p50 looks fine.
- **Enabling gzip simultaneously in Boot and CDN without clear ownership:** obscures real resource usage and encoding behavior.
- **Benchmarking images/ZIPs and concluding gzip is useless for JSON:** data entropy differs completely.

## 14. Common Mistakes in Spring Boot Applications

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Set **min-response-size=1KB**, yet responses don't compress | **server.compression.enabled=false**, MIME unlisted, or client lacks matching Accept-Encoding. | Inspect bound properties, Content-Type/Accept-Encoding, and server connector. |
| JSON smaller than threshold still gets gzipped | Streaming response/unknown Content-Length; proxy compresses at edge. | Compare origin vs. edge headers, transfer mode, and actual connector. |
| Compression enabled, yet TTFB gets worse | Encoder buffering, encode CPU, proxy response buffering. | Measure TTFB, flushing, CPU, and stream timeline. |
| Bandwidth drops, p99 jumps sharply | Compression CPU pushes server near saturation or container throttling. | Check CPU throttling, queues, p95/p99; cut compression work or precompress. |
| Gzipping JPEG/MP4 barely shrinks size | Data already compressed, gzip overhead. | Exclude those MIMEs; compare wire bytes before/after. |
| Enabling compression causes SSE updates to arrive in batches | Compression/proxy buffering holds data before flush. | Measure event arrival, review streaming policy, disable compression on SSE if needed. |
| Browser errors due to corrupt response bytes | Cache variant/Vary, Content-Encoding, proxy double compression, or corrupt transform. | Inspect response headers, decode output, and cache keys at each hop. |
| Curl shows un-decompressed body | Client passed Accept-Encoding manually, so curl kept raw compressed bytes. | Use **--compressed** when you want to read decoded content. |
| Enabled gzip in Boot, yet browser sees Brotli | CDN/edge handles Content-Encoding or browser negotiated differently. | Measure origin and edge separately; see who generates br. |
| Small body yet slow response | RTT, TTFB, encode, parse, GC, or business logic is the real bottleneck. | Trace from app to network; don't blame every slowdown on threshold. |
| Compressing responses containing tokens + reflected input | Size side-channel risk. | Assess BREACH and mitigate on sensitive endpoints. |

## 15. Applied Questions

**Scenario 1:** Spring Boot sets **server.compression.enabled=true** and **min-response-size=4KB**. A JSON endpoint returns 1 KB with an exact **Content-Length**. Is it guaranteed to skip gzip? With the default connector checking known Content-Length against the threshold, **usually uncompressed**. Yet with proxies or different implementations, verify the final response; do not treat configuration as an absolute promise across every hop.

**Scenario 2:** The server streams 1 KB JSON without Content-Length. The browser sees **Content-Encoding: gzip** despite the 4KB threshold. Is that a Spring Boot bug? **Not necessarily**: the connector may compress unknown-length responses, or the edge may compress downstream. Inspect origin/edge and streaming behavior.

**Scenario 3:** An 80 KB JSON shrinks to 16 KB with gzip, yet CPU rises from 65% to 95% and p99 latency climbs. Should you always keep gzip because it saves 80% bandwidth? **No.** Weigh SLOs, CPU, concurrency, CDN/precompression, and client impact; adjust thresholds, MIMEs, compression placement, or scale capacity.

**Scenario 4:** A 1 MB PNG file barely shrinks with gzip. Should you crank gzip level to maximum? **No by default**; the format is already compressed, so check if any ratio gain justifies CPU. Usually remove it from the MIME list.

**Scenario 5:** A CDN serves a gzip copy to a client that does not accept gzip. Is the Spring Boot threshold at fault? **Unlikely**; check **Vary: Accept-Encoding** and CDN cache key/variant negotiation.

**Scenario 6:** Output from **curl --compressed** written to a file is 8,203 bytes, matching raw JSON. Does that mean the server didn't compress? **No.** curl may have received gzip and decompressed it before writing the file. Check Content-Encoding and raw wire bytes.

**Scenario 7:** A JSON API is 99% cached at the edge, so the origin compresses only 1% of requests. Where should CPU be measured? **Both edge and origin**, because Boot CPU does not reflect compression work performed at the CDN.

**Scenario 8:** An HTML response contains a secret CSRF token and attacker-controlled text. Should you enable gzip looking only at bandwidth savings? **No**; evaluate the size side-channel threat model and apply mitigations.

## 16. Real-Project Application Checklist

1. Confirm whether your stack is **Spring MVC/Tomcat** or **WebFlux/Reactor Netty**, and which proxies/CDNs compress.
2. Check **enabled**, **min-response-size**, and **mime-types** in running configuration, not just source properties files.
3. Classify responses by **size**, **MIME**, **compression ratio**, **streaming vs. buffered**, and **whether secrets are present**.
4. Verify **Accept-Encoding**, **Content-Encoding**, **Vary: Accept-Encoding**, and actual decoded bodies.
5. Do not gzip already-compressed resources unless measured gains exist.
6. Benchmark candidate thresholds on a representative load profile; inspect **p95/p99**, CPU, and bandwidth, not averages alone.
7. Consider precompression/caching for static assets to offload runtime CPU.
8. Test streams/SSE and unknown Content-Length cases separately.
9. Account for SLOs, CPU quotas, CDN egress bills, and customer networks.
10. Canary changes, monitor metrics, and roll back if latency/error rates degrade.

**Conclusion:** **The compression threshold is neither “lower is always better” nor “higher saves CPU so always better”.** It is a control knob balancing encode/decode/buffering costs against network bytes saved. In Spring Boot 3.3, compression is **off by default** and the **2KB** default threshold only applies once enabled; production decisions must combine MIME types, headers, Content-Length, proxy topology, and real-load benchmarks.

## 17. Official References

- **Spring Boot 3.3 – Embedded Web Servers / Enable HTTP Response Compression:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ (server.compression.enabled, mime-types, min-response-size).
- **Spring Boot 3.3 – Compression API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/Compression.html
- **Apache Tomcat – HTTP Connector compression:** https://tomcat.apache.org/tomcat-10.1-doc/config/http.html (compression with unknown Content-Length, MIME types, connector semantics).
- **MDN – HTTP Compression:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression
- **MDN – Accept-Encoding:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept-Encoding
- **MDN – Content-Encoding:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Encoding
- **MDN – Vary:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary
- **RFC 9110 – HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110 (content codings, representation metadata, and content negotiation).