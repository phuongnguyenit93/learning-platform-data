# Configuring server.compression.enabled and Which Content Types Are Compressed

## 1. Goal and Context

In a Spring Boot application, the server can compress the **HTTP response body** before transmitting it to a browser or API client. For HTML, CSS, JavaScript, JSON, or XML with repetitive characters, compression typically reduces network transfer size. However, compression consumes additional CPU and may offer no benefit for small responses or already-compressed files such as JPEG, PNG, or ZIP.

**Starting point:**

~~~properties
server.compression.enabled=true
~~~

That configuration line **enables response compression capability** on the embedded web server, though it does not guarantee every response will carry `Content-Encoding: gzip`. Actual compression depends on HTTP negotiation, `Content-Type`, response size, response type, container capabilities, and proxy/CDN layers.

After this lesson, you will be able to:

1. Explain `Accept-Encoding` and `Content-Encoding`, and distinguish response compression from caching and request compression.
2. Accurately use `server.compression.enabled`, `server.compression.mime-types`, and `server.compression.min-response-size`.
3. Read Spring Boot 3.3's eight default compressible MIME types and customize them to add or remove suitable types.
4. Build a runnable Java 17+ Spring MVC application to test JSON, large/small text, and binary payloads.
5. Use `curl` to inspect headers, save raw gzip bytes, decompress them, and compare sizes.
6. Troubleshoot cases where gzip does not appear, `Content-Length` changes, caching proxies, already-compressed files, streaming/SSE, and security.
7. Identify support boundaries across Tomcat, Jetty, Undertow, Reactor Netty, and reverse proxies.

The main examples use **Spring Boot 3.3.5, Java 17+, Spring MVC + embedded Tomcat**. Spring Boot 3.3 documentation also lists response compression support for **Tomcat, Jetty, Undertow, and Reactor Netty**; detailed behavior on each container still needs verification in deployment.

## 2. Where Does HTTP Response Compression Happen?

High-level model:

~~~text
Client
  |
  | GET /api/text/large
  | Accept-Encoding: gzip
  v
Spring Boot web server
  |
  | Controller / static resource handler
  | produces response body and Content-Type
  v
HTTP response compression (if eligible)
  |
  | Content-Encoding: gzip
  | Payload is compressed bytes
  v
Proxy / CDN (if present)
  |
  v
Client receives gzip -> decompresses -> processes content
~~~

In an application with an embedded server, Spring Boot passes `server.compression.*` settings down to the container's compression mechanism. Normal controllers simply return the body; there is no need to compress manually with `GZIPOutputStream`, set `Content-Encoding`, and emit gzip bytes by hand.

HTTP has three easily confused sets of concepts:

| Property | Meaning | Example |
| --- | --- | --- |
| `Content-Type` | Data type **after decoding content coding**, telling the client whether it is HTML, JSON, PNG, etc. | `application/json` |
| `Accept-Encoding` (request) | Content codings the client accepts and their preferences | `gzip, br;q=0.8` |
| `Content-Encoding` (response) | Mechanism used to encode/compress the response body | `gzip` |
| `Transfer-Encoding` | Mechanism for transferring HTTP/1.1 messages, such as chunked | `chunked` |
| `Cache-Control` | Response caching policy | `public, max-age=3600` |

**Do not confuse `Content-Encoding` with `Content-Type`.** A gzipped JSON response can still look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

The actual body is gzip bytes; the client decompresses it before parsing JSON.

`Transfer-Encoding: chunked` is not a compression algorithm. A response can be both chunked and gzipped, or chunked without compression. In HTTP/2, framing differs from HTTP/1.1, so do not infer compression from the presence or absence of `Transfer-Encoding`.

**Transport compression and caching are two independent concerns.** Enabling gzip does not enable caching; setting `Cache-Control` does not enable gzip. The same URL can have multiple representations (identity/gzip) by `Accept-Encoding`; shared caches must handle variants properly.

## 3. server.compression.enabled: Enabling/Disabling Response Compression

Spring Boot 3.3 defines the property:

~~~properties
server.compression.enabled=false
~~~

**The default value is `false`**: with default Spring Boot and no other layer handling it, responses are normally sent uncompressed.

To enable:

~~~properties
server.compression.enabled=true
~~~

Equivalent in `application.yml`:

~~~yaml
server:
  compression:
    enabled: true
~~~

When set to `true`, the server is **permitted** to compress responses that satisfy all conditions. This does not mean “force every request to receive gzip”:

- The client may not request a coding supported by the server, or may reject it.
- The response's `Content-Type` may not be in `mime-types`.
- The response may be smaller than `min-response-size`.
- Some responses have no body, stream in a special way, are precompressed, or are excluded by the container.
- Reverse proxies/CDNs may alter the coding ultimately observed by the client.

This property applies to **HTTP responses** emitted by the web server. It does **not** automatically decompress HTTP requests carrying `Content-Encoding: gzip`, does not replace WebClient's client-side gzip handling, and does not create `.zip` archives.

## 4. server.compression.mime-types: Which Content Types Are Compressed?

Spring Boot 3.3 declares **eight default MIME types** for response compression:

~~~properties
text/html
text/xml
text/plain
text/css
text/javascript
application/javascript
application/json
application/xml
~~~

This is the **default property value** when you enable compression without customizing `mime-types`. Per Boot 3.3 documentation, they include:

| MIME type | Typical response | Why it usually compresses well |
| --- | --- | --- |
| `text/html` | Static HTML or template-rendered pages | Many repeated tags, attributes, and text |
| `text/xml` | XML marked as text | Repeated tag structures |
| `text/plain` | Text, logs, or plain-text reports | Repeated character data |
| `text/css` | CSS stylesheets | Repeated property names, selectors, and whitespace |
| `text/javascript` | Legacy JavaScript MIME | Textual source code |
| `application/javascript` | Standard JavaScript | Textual JS source code |
| `application/json` | JSON APIs | Repeated keys, structural punctuation, and text |
| `application/xml` | XML APIs | Repeated tag structures |

Within the same system, large JSON usually compresses well, whereas a few dozen bytes of JSON may **not be worth compressing**. Matching the MIME type is a necessary condition, **not** proof that `Content-Encoding: gzip` will appear.

### 4.1. Overriding the Default List

Suppose you only want to compress HTML and JSON:

~~~properties
server.compression.enabled=true
server.compression.mime-types=text/html,application/json
server.compression.min-response-size=1KB
~~~

With that configuration, `text/plain` responses are no longer eligible, even if 100 KB long. This is a common customization mistake: `mime-types` in Spring Boot 3.3 **replaces the default list**, rather than appending to it.

If you want to add `image/svg+xml` while keeping the defaults, list them all explicitly:

~~~properties
server.compression.enabled=true
server.compression.mime-types=text/html,text/xml,text/plain,text/css,text/javascript,application/javascript,application/json,application/xml,image/svg+xml
~~~

**SVG** is XML-based and text-heavy, so it usually compresses effectively. By contrast, do not add every `image/*` just thinking “more types is better”: JPEG, PNG, GIF, WebP, and AVIF images are already compressed; running gzip on top rarely helps and wastes CPU.

Types such as `application/problem+json`, `application/manifest+json`, `application/graphql-response+json`, `application/wasm`, or `font/woff2` can appear in real applications. **Do not assume** `application/json` automatically covers every `+json` suffix MIME type. Check the list, container MIME matching behavior, and actual runtime output before adding them.

### 4.2. MIME Selection Guide by Content Characteristics

| Content type | Usually appropriate decision |
| --- | --- |
| HTML, CSS, JavaScript | Enable compression when responses are large enough |
| JSON, XML APIs | Usually beneficial for large bodies or repetitive structures |
| Text, CSV, SVG | Can be beneficial; add exact MIME if absent from the list |
| JPEG, PNG, WebP, AVIF | Usually no extra gzip needed |
| ZIP, gzip, 7z, Brotli files | Already compressed; recompressing is rarely worthwhile |
| MP4, WebM, MP3, AAC | Pre-compressed media formats; prefer streaming/range handling |
| PDF | Many PDFs have compressed internal streams; measure in practice |
| `application/octet-stream` | Unknown binary content; do not enable unconditionally |
| `text/event-stream` (SSE) | Be cautious: buffering/compression can increase event latency |

**The MIME type emitted by the server is what gets checked.** A `.json` URL suffix is not enough to prove a response has `Content-Type: application/json`; a controller might return text, XML, or binary. Conversely, an extensionless API can still return JSON. Inspect actual headers with `curl -i`.

### 4.3. Charset Is Not a Separate MIME Type

A response may declare:

~~~http
Content-Type: text/plain;charset=UTF-8
~~~

In terms of base media type, that is `text/plain` with a charset parameter. In standard container mechanisms, compression matching inspects the appropriate MIME type and does not require adding `text/plain;charset=UTF-8` as a separate entry. Still, test your container/version when using custom MIME types with unusual parameters.

## 5. server.compression.min-response-size: Minimum Size Threshold

Spring Boot 3.3 documents the default value:

~~~properties
server.compression.min-response-size=2KB
~~~

In Boot's DataSize format, `2KB` equals **2048 bytes**. You can configure another threshold:

~~~properties
server.compression.min-response-size=1KB
~~~

or:

~~~properties
server.compression.min-response-size=4096B
~~~

Meaning: the minimum response size eligible for compression consideration. Property documentation describes this threshold in terms of **`Content-Length`**; depending on the container, unknown-length/chunked responses may be treated differently from responses with a known `Content-Length`. Therefore, do not apply a naive rule like “any body with more than 2,048 Java characters will definitely be gzipped”.

**Measured in bytes, not display characters:**

- A 1,024-character ASCII string typically takes 1,024 bytes in UTF-8.
- Vietnamese characters in UTF-8 can occupy multiple bytes per character.
- Serialized JSON can include escape sequences, so serialized byte length can differ from `String.length()`.
- If the application does not know `Content-Length` before streaming, threshold decisions depend on runtime characteristics.

For example, with a `1KB` threshold, `text/plain` eligible, and a gzip-accepting client:

| Response | Expected outcome |
| --- | --- |
| 2-byte body, `Content-Length: 2` | Normally not compressed because it is below threshold |
| 700-byte body, `Content-Length: 700` | Normally not compressed |
| 5,000-byte body, `Content-Length: 5000` | Eligible for gzip if all other conditions are met |
| 8,000-byte body, unconfigured `image/png` MIME | Not compressed merely because the body is large |
| Large body, yet client does not accept gzip | Must not force gzip when client declines it |
| Unknown `Content-Length` beforehand | Must check container behavior; do not infer from Java String |

A very low threshold wastes CPU and can occasionally make payloads **larger** due to gzip headers/trailers. A very high threshold misses many JSON/text responses that would genuinely benefit. Decide using measured data.

## 6. Content Negotiation: Accept-Encoding and Content-Encoding

**The client sends** the encodings it accepts:

~~~http
GET /api/text/large HTTP/1.1
Host: localhost:8080
Accept-Encoding: gzip
~~~

**The server responds**, if it chooses gzip:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Following the headers are the gzip bytes; the body is no longer readable plain UTF-8 text until decompressed. The headers illustrated above show the typical form; exact `Vary`, `Content-Length`, `Transfer-Encoding`, or additional headers depend on server and proxy.

### 6.1. q-values and identity

Common values:

~~~http
Accept-Encoding: gzip
Accept-Encoding: gzip, br;q=0.8
Accept-Encoding: gzip;q=1.0, identity;q=0.5
Accept-Encoding: gzip;q=0
Accept-Encoding: identity
~~~

- `gzip`: client accepts gzip.
- `br`: client supports Brotli; this does **not** guarantee Spring Boot's embedded server will choose Brotli when enabling the compression property.
- `q` (0 to 1): preference/acceptance weight for the coding. `q=0` means that coding is not acceptable.
- `identity`: use no content encoding to compress the body. Send `Accept-Encoding: identity` when testing uncompressed responses.
- A request missing `Accept-Encoding` should not be treated as a definitive gzip test: the HTTP specification and real implementations have subtle differences. To test cleanly, explicitly send `gzip` or `identity`.

**Do not confuse with `Accept: application/json`.** `Accept` specifies the **media type** the client wants; `Accept-Encoding` specifies the **content coding** on the transferred bytes. A client can send both simultaneously:

~~~http
Accept: application/json
Accept-Encoding: gzip
~~~

Each header serves a distinct purpose.

### 6.2. gzip, br, and Servers

In Spring Boot 3.3, setting `server.compression.enabled=true` alone **does not promise every coding is supported**. Gzip is the standard baseline testable with Tomcat. Brotli may be provided by a CDN/reverse proxy or precompressed resource handling, so do not assume dynamic Brotli compression is automatically enabled across all embedded servers.

Inspect `Content-Encoding` at the **final output** and verify which layer performed compression. An identity upstream can be Brotli-compressed by a CDN for browsers; a gzip upstream can be decompressed and recompressed by a proxy.

## 7. Runnable Example — Spring Boot 3.3.5 + Tomcat + Java 17

The following lab demonstrates four cases:

1. Large `text/plain`, above threshold, client requests gzip.
2. Small `text/plain`, same MIME yet below threshold.
3. Large `application/json`, inside the compressible MIME list.
4. Large `application/octet-stream`, **outside** the lab's compressible MIME list.

No database, template engine, or compression library beyond Spring Boot is required.

### 7.1. Project Structure

~~~text
compression-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/compression/
    │   ├── CompressionDemoApplication.java
    │   └── CompressionController.java
    └── resources/
        ├── application.properties
        └── static/
            └── index.html
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compression-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` brings in Spring MVC and embedded Tomcat by default in the lab version. Server compression is managed by Boot/the embedded container; there is no need to write a manual gzip Servlet filter.

### 7.3. application.properties

**`src/main/resources/application.properties`:**

~~~properties
server.port=8080

# Enable compression on the embedded web server
server.compression.enabled=true

# Compress only text/plain, JSON, and HTML in this lab
server.compression.mime-types=text/plain,application/json,text/html

# 1 KB = 1024 bytes
server.compression.min-response-size=1KB
~~~

This configuration **differs from the default eight MIME types**: we intentionally narrow it to three types so the effect of `mime-types` is obvious. If CSS/JS/XML also need compression in a real application, include those MIME types as well.

### 7.4. Startup Class

**`src/main/java/com/example/compression/CompressionDemoApplication.java`:**

~~~java
package com.example.compression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CompressionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompressionDemoApplication.class, args);
    }
}
~~~

### 7.5. Controller for Text, JSON, and Binary

**`src/main/java/com/example/compression/CompressionController.java`:**

~~~java
package com.example.compression;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CompressionController {

    private static final String LARGE_TEXT =
            "Spring Boot response compression works for large text. "
                    .repeat(300);

    @GetMapping(value = "/text/large",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> largeText() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(
                        LARGE_TEXT.getBytes(StandardCharsets.UTF_8).length)
                .body(LARGE_TEXT);
    }

    @GetMapping(value = "/text/small",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> smallText() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(2)
                .body("OK");
    }

    @GetMapping(value = "/json/large",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> largeJson() {
        return Map.of(
                "message",
                "Spring Boot JSON compression example. ".repeat(300)
        );
    }

    @GetMapping(value = "/binary",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> binary() {
        // 8192 zero bytes would compress very well mathematically,
        // but the MIME is not in the configured list.
        byte[] bytes = new byte[8192];
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(bytes.length)
                .body(bytes);
    }
}
~~~

**Code explanation:**

- `GET /api/text/large` has an ASCII body exceeding the `1KB` threshold; the controller sets `Content-Length` from actual UTF-8 bytes so the test does not have to guess size.
- `GET /api/text/small` returns `OK`, exactly **2 bytes**, intentionally below the threshold.
- `GET /api/json/large` returns a `Map`; Jackson (managed by Spring Boot Web) serializes it to JSON, and `Content-Type: application/json` matches the list.
- `GET /api/binary` has 8192 zero bytes—technically trivial to gzip, yet `application/octet-stream` is unlisted and thus **ineligible for compression** in this lab's configuration.
- None of the code directly uses `GZIPOutputStream` or sets `Content-Encoding`. We want to test the server's built-in response compression mechanism.
- JSON responses may not have a known `Content-Length` upfront; if gzip does not appear in a specific environment, inspect headers and server behavior. The large text endpoint with explicit `Content-Length` is the core test case.

### 7.6. A Static HTML File

**`src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>HTTP compression demo</title>
</head>
<body>
  <h1>Testing HTTP compression with Spring Boot</h1>
  <p>This is a static HTML page served by Spring Boot.</p>
  <p>
    <a href="/api/text/large">Large text</a>
    <a href="/api/text/small">Small text</a>
    <a href="/api/json/large">Large JSON</a>
  </p>
</body>
</html>
~~~

HTML has type `text/html` yet is quite small, so with a `1KB` threshold, `GET /` may not be gzipped. This difference is intentional: **an allowed MIME type does not mean every HTML page will be compressed**.

### 7.7. Run the Application

In the `compression-demo` root directory with JDK 17+ and Maven 3.x installed, run:

~~~bash
mvn spring-boot:run
~~~

Once embedded Tomcat starts listening on port 8080, test the URLs:

~~~text
http://localhost:8080/
http://localhost:8080/api/text/large
http://localhost:8080/api/text/small
http://localhost:8080/api/json/large
http://localhost:8080/api/binary
~~~

No reverse proxy is needed for the lab; hit `localhost:8080` directly to isolate the embedded server's compression layer.

## 8. Testing gzip Properly with curl

Some HTTP tools **automatically decompress** responses and display plain text even when the server returned gzip. Therefore, inspect **headers and raw bytes** separately.

### 8.1. Request gzip and Save the Raw Response

In a second terminal (Bash/zsh on Linux/macOS):

~~~bash
curl --http1.1 -sS \
  -H "Accept-Encoding: gzip" \
  -D headers-gzip.txt \
  -o body-gzip.bin \
  http://localhost:8080/api/text/large
~~~

This command requests gzip **without passing `--compressed`**, so `curl` writes the **raw response body bytes received** into `body-gzip.bin`.

Check headers:

~~~bash
cat headers-gzip.txt
~~~

With the Tomcat lab properly configured and an eligible response, expect:

~~~http
HTTP/1.1 200
Content-Type: text/plain
Content-Encoding: gzip
~~~

Status line/headers vary by container version, and `Vary`, `Transfer-Encoding`, or other headers may appear. **These are the headers to look for, not a byte-for-byte stdout promise.**

Decompress bytes to verify:

~~~bash
gzip -dc body-gzip.bin | head -c 160
~~~

The decompressed text begins with:

~~~text
Spring Boot response compression works for large text.
~~~

Note the phrase repeats many times; `head -c 160` prints only the opening snippet. Do not compare `body-gzip.bin` size with source character count; compare it with the byte size of the identity response.

### 8.2. Request Uncompressed as a Control

~~~bash
curl --http1.1 -sS \
  -H "Accept-Encoding: identity" \
  -D headers-plain.txt \
  -o body-plain.txt \
  http://localhost:8080/api/text/large
~~~

With `identity`, do not expect `Content-Encoding: gzip`. Reading `body-plain.txt` shows the original ASCII text.

Compare file sizes:

~~~bash
wc -c body-gzip.bin body-plain.txt
~~~

Highly repetitive content achieves a very high compression ratio; the gzip file is normally much smaller than the plain file. **Do not hardcode an exact byte figure**, since gzip headers, containers, and versions can differ.

### 8.3. Reading the Body Automatically Decompressed by curl

~~~bash
curl --http1.1 -i --compressed \
  http://localhost:8080/api/text/large
~~~

`--compressed` requests encodings supported by that `curl` build and **automatically decompresses the response for display**. This is convenient for inspecting content, yet **unsuitable for saving and counting gzip bytes on the wire**. Some `curl` builds advertise multiple encodings such as gzip/br/zstd if compiled with those libraries; to isolate `gzip`, explicitly pass `Accept-Encoding: gzip` as in section 8.1.

Even when `--compressed` decodes the body, headers printed by `-i` will still show `Content-Encoding: gzip` from the original response. Do not see readable text on screen and conclude the server did not compress.

### 8.4. 2-Byte Test: Same MIME, Different Size

~~~bash
curl --http1.1 -i -H "Accept-Encoding: gzip" \
  http://localhost:8080/api/text/small
~~~

Exact expected body:

~~~text
OK
~~~

With `Content-Length: 2` and a `1KB` threshold, Tomcat normally **does not** attach `Content-Encoding: gzip`. If the server still compresses it, check whether a proxy, filter, or different container is overriding settings.

### 8.5. JSON Test: MIME in the List

~~~bash
curl --http1.1 -i --compressed \
  http://localhost:8080/api/json/large
~~~

Expect a JSON response containing the `message` key with a long repeated string; when the web server determines compression applies, `Content-Encoding: gzip` may appear. Depending on whether `Content-Length` is known before writing and how the runtime applies thresholds, verify the actual result.

### 8.6. Binary Test: Large Yet Excluded MIME

~~~bash
curl --http1.1 -sS \
  -H "Accept-Encoding: gzip" \
  -D headers-binary.txt \
  -o body-binary.bin \
  http://localhost:8080/api/binary
~~~

In the lab, `Content-Type` is `application/octet-stream` and outside `mime-types`, so gzip is not expected. `body-binary.bin` contains zero bytes that are unprintable in a terminal; **do not run `curl -i` and dump raw binary to stdout** to inspect it. Check:

~~~bash
wc -c body-binary.bin
cat headers-binary.txt
~~~

The original payload is 8192 bytes. The goal is to prove compression decisions are not based solely on byte count.

### 8.7. Testing on PowerShell

Windows PowerShell defines a built-in `curl` alias in some versions. Use `curl.exe` instead of `curl`:

~~~powershell
curl.exe --http1.1 -i --compressed http://localhost:8080/api/text/large
curl.exe --http1.1 -i -H "Accept-Encoding: identity" http://localhost:8080/api/text/small
curl.exe --http1.1 -sS -H "Accept-Encoding: gzip" -D headers-gzip.txt -o body-gzip.bin http://localhost:8080/api/text/large
~~~

If you need to inspect raw gzip bytes on Windows, use a gzip-capable decompression tool/library, or use `curl.exe --compressed` to verify the decompressed body rather than reading raw bytes directly.

## 9. Toggling Compression Without Editing Java Code

To compare the exact same code, build the JAR:

~~~bash
mvn clean package
~~~

Stop the Maven-launched instance first, then run with compression enabled:

~~~bash
java -jar target/compression-demo-0.0.1-SNAPSHOT.jar \
  --server.compression.enabled=true
~~~

Stop the process and run with compression disabled:

~~~bash
java -jar target/compression-demo-0.0.1-SNAPSHOT.jar \
  --server.compression.enabled=false
~~~

In the lab's Java/Spring Boot version, the command-line argument `--server.compression.enabled=false` overrides the property in `application.properties`. On Windows, put the command on one line if your shell does not support backslash line continuation.

Check `/api/text/large` again with `curl -H "Accept-Encoding: gzip"` before and after. When disabled **at the embedded server**, do not expect `Content-Encoding: gzip` from the embedded server. If gzip still appears in production, a reverse proxy, CDN, filter, or upstream component is likely compressing; isolate each layer before concluding the property had no effect.

**Do not run two processes on port 8080**. To run them side by side, pass `--server.port=8081` to one process and adjust the URL accordingly.

## 10. Vary Header and Caches: Avoiding Serving the Wrong Variant

Compressed and uncompressed responses for the same URL have **different bytes**, even when the decompressed logical content is identical. Shared caches must know which encoding the client accepts.

Key header:

~~~http
Vary: Accept-Encoding
~~~

It indicates that the representation depends on `Accept-Encoding`; caches must inspect this request header when selecting a stored version. If a cache/CDN ignores `Vary`, it may send gzip bytes to a client that does not accept gzip or serve a suboptimal representation.

**Verify in practice:** do not assume every embedded server/reverse proxy emits `Vary` identically across all response paths. When behind a CDN, check `Vary`, cache keys, Accept-Encoding normalization rules, and test both gzip and identity clients against **the same URL**.

Example:

~~~text
GET /api/catalog
  Accept-Encoding: gzip
  -> Content-Encoding: gzip

GET /api/catalog
  Accept-Encoding: identity
  -> no Content-Encoding
~~~

Both requests can return **equivalent JSON content**, yet the body bytes differ.

Distinguish:

- `Cache-Control`: determines whether, where, and for how long a response may be cached.
- `ETag`/`Last-Modified`: support conditional requests and validating stored copies.
- `Vary`: request headers that must be examined when selecting a cached version.
- `Content-Encoding`: coding applied to the current response's bytes.

**Nuance with ETag:** a strong ETag tied to a specific byte representation must stay consistent with the cached/served representation. Compressing dynamically after the framework has already computed an ETag can cause issues if an ETag representing uncompressed bytes is reused as a strong validator for compressed bytes. Test ETags/conditional requests end-to-end, using weak validators or appropriate proxy/server handling when needed rather than assuming an ETag automatically works “across all encodings”.

A personalized response may require `Cache-Control: private` or `no-store` per data policy; **enabling gzip does not make caching safe or private**.

## 11. Difference Between Dynamic Compression and Precompressed Files

There are two common ways to deliver compressed assets:

**A. Dynamic compression from the web server:**

~~~text
static/app.js (original)
  -> embedded server reads JS
  -> selects gzip based on MIME/size/Accept-Encoding
  -> HTTP response Content-Encoding: gzip
~~~

Core configuration:

~~~properties
server.compression.enabled=true
~~~

**B. Precompressed static resources:**

~~~text
static/app.js
static/app.js.gz
static/app.js.br
  -> static resource resolver selects precompressed file
  -> HTTP response with matching Content-Encoding
~~~

In the Spring MVC resource chain, Boot 3.3 has a dedicated property:

~~~properties
spring.web.resources.chain.compressed=true
~~~

This property looks up **already-compressed resources** such as `.gz` or `.br` in the resource chain when properly configured, and it is **distinct from** `server.compression.enabled`. Enabling the compressed resource chain **does not automatically generate** `app.js.gz` or `app.js.br`. A build/deploy step must emit the compressed files and resource handling must be verified.

What to avoid:

- Do not dynamically recompress a payload already carrying `Content-Encoding: gzip`, causing double compression.
- Do not serve `app.js.gz` as if it were normal JavaScript without appropriate `Content-Encoding` and `Content-Type`.
- Do not assume dynamic Brotli is enabled by `server.compression.enabled=true` merely because the resource chain can pick precompressed `.br` files.
- CDNs may handle compression outside the application; clearly assign primary compression ownership to save CPU and avoid conflicting configs.

## 12. Spring MVC and WebFlux: Similarities and Differences

Spring Boot supports server compression across multiple embedded servers. Practical points:

| Stack / server | Spring Boot config | Notes |
| --- | --- | --- |
| Spring MVC + embedded Tomcat | `server.compression.*` | Container decides gzip by MIME, size, Accept-Encoding, and status |
| Spring MVC + Jetty | `server.compression.*` | Uses its own compression implementation; headers/thresholds can differ |
| Spring MVC + Undertow | `server.compression.*` | Encoding mechanism integrated with the server |
| Spring WebFlux + Reactor Netty | `server.compression.*` | Compression at Netty HTTP server, not a Servlet filter |
| Spring WebFlux on Servlet runtime | `server.compression.*` if Boot-supported runtime | Do not infer stack from reactor package; check the actual server running |

You can port the MVC lab project to WebFlux using the appropriate starter and reactive handlers, yet **do not** copy `HttpServletRequest`, Servlet filters, or MVC `Content-Length` strategies into WebFlux assuming identical behavior. In WebFlux, responses can be streamed, changing when total size becomes known.

Enabling compression **does not turn blocking I/O into non-blocking I/O** and does not limit concurrency. Under high CPU load and large payloads, gzip compression can become a bottleneck; measure RPS, CPU, latency, and bytes transferred.

## 13. Which Responses Require Extra Caution?

### 13.1. SSE and Streaming

**Server-Sent Events (SSE)** typically use `Content-Type: text/event-stream` and emit many small events. If you include this type in the compression list, buffering/flushing behavior may delay events, making clients perceive “the server is not sending data”.

Prioritize **event latency** and verify flushing before enabling compression for SSE. In most applications, keeping `text/event-stream` out of the compressible MIME list is the practical choice. Likewise, large-file streaming requires evaluating backpressure/ranges/caching instead of blindly enabling gzip.

### 13.2. Images, Video, and Compressed Archives

Types such as `image/jpeg`, `image/png`, `video/mp4`, and `application/zip` are already compressed. Adding gzip costs CPU with negligible savings. For videos and large files, also consider `Range`/`Content-Range`, seekability, and CDN behavior. Never force all binary responses through gzip.

### 13.3. Bodyless Responses

Statuses `204 No Content`, `304 Not Modified`, and standard `HEAD` responses have no normal response body to compress. Do not treat the absence of `Content-Encoding` on these responses as evidence that compression is disabled.

### 13.4. Pre-Encoded Responses

If a controller manually returns compressed bytes with `Content-Encoding`, servers/proxies must know not to recompress them. Do not mix “compression in the controller” with “container compression” without a clear design. For file downloads, send the proper MIME/coding for the file rather than attaching `Content-Encoding` arbitrarily to every zip file.

### 13.5. HTTP Over HTTPS

HTTP response compression still runs **before TLS encryption**. It is not the same as TLS-level compression (which should stay off). However, compressing HTTPS pages that place secrets alongside attacker-controlled data can create length-based leaks such as **BREACH** attacks. See the security section.

## 14. Security Concerns: Side Channels When Compressing Sensitive Content

Gzip saves bytes by exploiting repeated substrings. Compressed response sizes can leak information **when secrets are reflected in the same response as attacker-controlled data** and an attacker can measure response lengths across repeated attempts.

Risk example:

~~~text
Dynamic HTML/JSON response containing:
  secret token / CSRF token / sensitive data
  + attacker-controlled text snippet
  -> compressed together with gzip
  -> compressed size varies with repeated strings
~~~

Risks such as BREACH depend on the attack model, input control, and length observability. **Do not conclude that every gzipped response leaks secrets**, nor assume HTTPS eliminates size side channels.

Mitigations to consider based on risk:

1. Omit unnecessary secrets from HTML/JSON; avoid placing them next to arbitrarily reflected input whenever possible.
2. Restrict compression on genuinely sensitive endpoints or separate secret data from reflected content if architecture allows.
3. Use appropriate tokens and CSRF, SameSite, and authorization layers; these alone do not replace side-channel analysis.
4. For responses containing secrets, consider padding/randomization or dedicated compression policies if your threat model requires it.
5. When using a CDN/proxy, inspect outer layers rather than only Spring Boot properties. Disabling gzip at the origin is insufficient if the CDN re-enables it on sensitive responses.

**MIME type selection is no substitute for authorization.** Disabling compression on `application/json` does not give a private API authentication or access control. Compression is a transport optimization; application security is a broader concern.

## 15. Performance Tuning and Measurement

To decide thresholds and compressible types, measure **the same workload** before and after enabling compression at appropriate observation points.

| Metric | What to measure | Interpretation |
| --- | --- | --- |
| Response bytes before/after compression | Byte reduction per MIME and endpoint | Do not rely solely on highly compressible lab files |
| CPU and time spent compressing | Per-request compression cost | High RPS and large payloads can drive CPU up |
| Latency p50/p95/p99 | Client-experienced latency | Gzip may not improve latency when server CPU is saturated |
| Throughput/RPS, error rate | Capacity under real load | Compression can help network while limiting CPU |
| Cache hit ratio | Whether proxy/CDN/browser caches hit | Caching can offload the origin far more than gzip |
| Bandwidth and download time | Especially on mobile/high-latency networks | Compressing large text usually pays off |
| Body size distribution | How many responses fall below/above threshold | Basis for choosing `min-response-size` |

### 15.1. Example Savings Calculation

Suppose measurements show an identity JSON response of 120,000 bytes and gzip of 18,000 bytes:

~~~text
Bytes saved = 120000 - 18000 = 102000 bytes
Savings ratio = 102000 / 120000 = 85%
~~~

This is an **arithmetic example**, not a lab measurement. Results depend on data. For a 50-byte response, gzip may fail to shrink the payload; that is why thresholds and MIME filters exist.

### 15.2. Load Testing Checklist

- Keep JDK, Spring Boot version, CPU, replica count, network, and request distribution identical.
- Compare multiple runs: warm up JVM/JIT, record p50/p95/p99, CPU, RPS, and bytes transferred.
- Break down by `Content-Type` and response size; do not compare “whole API” numbers across shifting workloads.
- Test slow/low-bandwidth networks because wire savings behave differently than localhost.
- Check whether a proxy/CDN already compresses; avoid misattributing edge behavior to `server.compression`.
- For streaming and secret-bearing responses, prioritize latency/security constraints over maximizing compression ratio.

**Practical guideline:** start by enabling gzip for common text MIMEs with a moderate threshold, then measure before and after. Expand the MIME list or lower the threshold only when data demonstrates a net win.

## 16. Common Configuration Pitfalls

| Symptom | Possible cause | Troubleshooting step |
| --- | --- | --- |
| `server.compression.enabled=true` is set, yet no gzip appears | Client did not request it, MIME excluded, body below threshold, different server/proxy | Send `Accept-Encoding: gzip`, check `Content-Type` and body length |
| JSON compresses, yet CSS does not | `mime-types` overridden with only `application/json` | Add `text/css` to the list |
| 5 MB JPG file does not compress | JPEG is not in default MIMEs and is already compressed | Usually expected, sensible behavior |
| Small file does not compress | `min-response-size` is set higher | Measure bytes, do not use character count as threshold |
| Browser shows plain text, looks uncompressed | Browser/`curl --compressed` already decompressed it | Inspect `Content-Encoding` in Network tab/raw headers |
| `curl -i` prints garbled characters | Requested gzip without client auto-decompression | Use `--compressed` or save gzip bytes and decompress |
| Gzip appears even with server property off | CDN/proxy/another filter is compressing | Hit origin directly to isolate |
| Added `br` to `Accept-Encoding`, yet server only sends gzip | Embedded server/stack lacks dynamic Brotli | Check supported codings, precompressed resources, and CDN |
| Another client receives wrong gzip from cache | Cache does not manage `Vary: Accept-Encoding` properly | Check `Vary` and cache keys |
| `Content-Length` disappears/changes on gzip | Compression alters body bytes; may switch to chunked | Do not assume absence of Content-Length is an error |
| SSE events arrive late after enabling compression | Compression or proxy buffering/flushing | Avoid compressing SSE and check flushing |
| CPU climbs and RPS drops despite fewer bytes | Excessive compression CPU overhead | Raise threshold, narrow MIMEs, offload to proxy |
| Works in local test, uncompressed in production | Proxy strips/rewrites coding, different server, or different profile | Compare configs, `Accept-Encoding`, and per-hop headers |
| Static JS is not compressed | Returned MIME is unlisted or file is below threshold | Check `Content-Type`, size, and path |
| Gzip header present on unreadable response | Client is parsing compressed bytes as plain JSON | Use an HTTP client with decompression, not raw `JSON.parse` on binary gzip |

### 16.1. Reliable Diagnostic Sequence

1. **Identify the actual web server:** Tomcat/Jetty/Undertow/Reactor Netty and Spring Boot version. Inspect startup logs, dependencies, and deployment config.
2. **Confirm bound properties:** `enabled`, `mime-types`, `min-response-size` in the active profile/environment. CLI args, environment variables, and config servers can override them.
3. **Send targeted requests:** `Accept-Encoding: gzip` to test compression and `Accept-Encoding: identity` as a control, against **the same URL**.
4. **Read response headers:** `Content-Type`, `Content-Encoding`, `Vary`, and `Content-Length`/`Transfer-Encoding` if present.
5. **Test a known large body:** the `/api/text/large` endpoint from the lab has plain text and an explicit `Content-Length`, avoiding threshold/chunking ambiguity.
6. **Isolate hops:** call the origin directly, then through the reverse proxy/CDN; see which layer alters the response.
7. **Measure real performance:** CPU, p99, bytes transferred, and errors—never conclude from a single successful gzip response.

## 17. Self-Check and Exercises

**Question 1.** Does Spring Boot 3.3 enable compression by default? What are the default threshold and MIME list?

**Question 2.** Why doesn't `GET /api/text/small` in the lab gzip, even though `text/plain` is listed?

**Question 3.** After setting `server.compression.mime-types=application/json`, is a 200KB CSS file still eligible for compression?

**Question 4.** Distinguish `Accept: application/json` from `Accept-Encoding: gzip`.

**Question 5.** A 10MB `application/octet-stream` response contains repeated bytes. Is large size alone enough for the server to compress it?

**Question 6.** How do you inspect raw gzip bytes with `curl` without letting `curl` decompress them when saving to a file?

**Question 7.** Why is `Vary: Accept-Encoding` critical for reverse proxy/CDN caches?

**Question 8.** An HTTP response has `Content-Type: application/json`, `Content-Encoding: gzip`, and `Transfer-Encoding: chunked`. What three distinct things do those headers describe?

**Question 9.** Is enabling `spring.web.resources.chain.compressed=true` the same as `server.compression.enabled=true`? Does either automatically generate `.br` or `.gz` files?

**Question 10.** Why shouldn't gzip be unconditionally enabled for SSE, PNGs, and responses mixing secrets with untrusted reflected input?

**Guided answers:**

1. No; `enabled=false`, default threshold `2KB=2048 bytes`, default MIMEs are `text/html`, `text/xml`, `text/plain`, `text/css`, `text/javascript`, `application/javascript`, `application/json`, `application/xml`.
2. Body `OK` is only 2 bytes, below `1KB`; matching MIME alone is insufficient.
3. No. Setting `mime-types` explicitly replaces the default list; only JSON remains listed.
4. `Accept` states the data media type desired; `Accept-Encoding` states which byte encoding/compression algorithms the client accepts.
5. No. `application/octet-stream` is absent from the lab's list; client coding acceptance and container rules also apply.
6. Use `curl -H "Accept-Encoding: gzip" -D headers.txt -o body.gz URL` **without** `--compressed`; verify Content-Encoding then decompress the file.
7. Caches can store byte-different gzip and identity representations for the same URL and must distinguish them by request header.
8. JSON is the media type; gzip is the content coding; chunked is the HTTP/1.1 message transfer framing.
9. No. The resource chain selects precompressed files when configured and present; server compression compresses dynamic responses. Neither property generates compressed files during the build.
10. SSE needs low-latency flushing; PNG is already compressed; secrets mixed with attacker-controlled input can leak through compressed response sizes.

## 18. Practical Summary

- `server.compression.enabled=true` **enables HTTP response compression capability**, without forcing every response to gzip.
- `server.compression.mime-types` picks **which Content-Types are eligible**. In Boot 3.3, eight text/JS/JSON/XML MIMEs are default; customizing the property **replaces** that list.
- `server.compression.min-response-size` controls the **byte threshold**, defaulting to `2KB`; behavior when `Content-Length` is unknown depends on the container.
- `Accept-Encoding` on requests and `Content-Encoding` on responses govern content-coding negotiation; `Content-Type` remains the data type.
- Test with `curl -H "Accept-Encoding: gzip"` + raw body output; use `curl --compressed` to view decompressed content.
- Compression, HTTP caching, precompressed files, and CDNs are **separate layers**. Verify `Vary`, proxies, and actual codings.
- Optimize across **bytes, CPU, latency, caching, and security**, not compression ratio alone. Avoid blindly enabling compression on arbitrary binaries, SSE, or sensitive responses without risk review.

## 19. Official References

- Spring Boot 3.3 — Embedded Web Servers, *Enable HTTP Response Compression* (supported servers, 2048 bytes, and eight default MIMEs): https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Common Application Properties, `server.compression.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — `Compression` API (`getMimeTypes`, `getMinResponseSize`, `getEnabled`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/Compression.html
- Spring Framework — Static Resources / encoded resource resolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- RFC 9110 — HTTP Semantics, Accept-Encoding, Content-Encoding, and Vary: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9111 — HTTP Caching (Vary and variants): https://www.rfc-editor.org/rfc/rfc9111.html