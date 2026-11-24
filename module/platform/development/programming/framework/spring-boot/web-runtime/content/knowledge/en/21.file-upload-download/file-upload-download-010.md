# Range Requests, Resuming Downloads, and Support Limits by Resource Response Type in Spring Boot

**Context:** Spring Boot → web-runtime → File upload and download. This lesson covers HTTP byte-range requests, **resuming downloads (resume)**, statuses `200/206/416`, the headers `Range`, `Content-Range`, `Accept-Ranges`, and `If-Range`, differences across Spring MVC and Spring WebFlux response types, testing with `curl`, safe handling, and performance limits. The primary example uses **Java 17, Spring Boot 3.5.16, Spring Framework 6.2.x, Maven, Servlet/Spring MVC**. WebFlux code is marked as a separate illustration.

## 1. The Problem: Why Must Large File Downloads Support Partial Transfers?

If a server always sends an entire file starting from byte zero, a client that downloaded 900 MB of a 1 GB file before losing network would have to re-download all 1 GB. **HTTP Range requests** let clients request **one or more byte spans of a representation**. That allows browsers, download managers, and media players to:

- resume downloading from the already-received offset, provided the file version on the server has not changed;
- fetch only the segment needed when seeking in video/audio playback;
- split a download into multiple controlled segments;
- reduce re-transmitted bytes after connection drops.

**Having HTTP streaming does not automatically mean resume is supported.** Streaming chunks incrementally to save memory differs from **random access** by byte offset. How you construct the HTTP response determines whether Spring handles `Range` automatically.

~~~text
Client already has 0..499 (500 bytes)
          │
          └── GET /files/report.bin
              Range: bytes=500-
                        │
                        ▼
                 Does server support Range?
                    │               │
                    ▼               ▼
               206 Partial       200 OK (sends full file)
               Content           Client must NOT append blindly
                    │
                    ▼
               Content-Range: bytes 500-999/1000
               Body has final 500 bytes
                    │
                    ▼
          Client verifies version, offset,
          and length, then assembles 1,000 bytes
~~~

Range is for **reading part of a response**. It is not a resumable **upload** technique: chunked uploads use offsets, session/upload tokens, and dedicated methods (such as the tus protocol or object-storage multipart uploads). Never confuse `Range` download requests with `Content-Range` on PUT uploads without an explicit API contract.

## 2. HTTP Byte Ranges per RFC 9110

### 2.1. Key Headers

| Header | Direction | Role | Example |
| --- | --- | --- | --- |
| **`Range`** | Request | Client requests one or more spans of the representation | `Range: bytes=0-1023` |
| **`Accept-Ranges`** | Response | Server advertises supported range unit | `Accept-Ranges: bytes` |
| **`Content-Range`** | `206`/`416` Response | Returned span and total representation length | `Content-Range: bytes 0-1023/10000` |
| **`If-Range`** | Request with `Range` | Return the span only if the representation is unchanged; otherwise expect full body | `If-Range: "file-v5"` |
| `ETag` | Response | Representation validator; prefer a **strong ETag** for safe byte appending | `ETag: "file-v5"` |
| `Last-Modified` | Response | Modification timestamp; usable for conditional requests | `Last-Modified: Wed, 21 Oct 2015 07:28:00 GMT` |
| `Content-Length` | Response | Byte count of **the current response body**, usually smaller than the full file on `206` | `Content-Length: 1024` |
| `Content-Disposition` | Response | Hints browser inline vs. attachment and filename | `attachment; filename="report.pdf"` |

**`bytes` counts octets (bytes), not characters, lines, or code points.** Indices start at **0**, and the end position is **inclusive**. For an exact 26-byte file containing the ASCII string `ABCDEFGHIJKLMNOPQRSTUVWXYZ`:

| Request Header | Byte Positions | Expected Body |
| --- | --- | --- |
| `Range: bytes=0-4` | 0 through 4 | `ABCDE` (5 bytes) |
| `Range: bytes=10-14` | 10 through 14 | `KLMNO` (5 bytes) |
| `Range: bytes=20-` | 20 through end | `UVWXYZ` (6 bytes) |
| `Range: bytes=-4` | Last 4 bytes | `WXYZ` |
| `Range: bytes=0-2,23-25` | 2 disjoint spans | `ABC` and `XYZ`, typically multipart body |
| `Range: bytes=100-` | Starts past the 26-byte EOF | Unsatisfiable, typically `416` |

If a client sends `Range: bytes=20-50` for a 26-byte file, the valid span is clamped to **20–25**, with `Content-Range: bytes 20-25/26`. It never reads byte 50 past EOF.

### 2.2. Three Core Statuses

**`200 OK`**: the server returns the complete representation. This happens when the client sent no `Range`, the server does not support Range, the server chooses to ignore `Range`, or `If-Range` failed to match on a compliant implementation. On receiving 200, a resuming client **must not append** the body to the partial file; it must replace it with the complete version after verification.

**`206 Partial Content`**: the server satisfied `Range`. For a **single** span, the response includes `Content-Range` describing the slice and total length. Hypothetical example (headers like Date omitted):

~~~http
GET /files/alphabet HTTP/1.1
Host: localhost:8080
Range: bytes=10-14

HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Type: text/plain
Content-Range: bytes 10-14/26
Content-Length: 5

KLMNO
~~~

`Content-Length: 5` describes **the 206 response body**; the full file remains 26 bytes per `Content-Range`. Never mistake 5 for the total file length.

**`416 Range Not Satisfiable`**: none of the requested ranges is satisfiable, or the server rejects an excessive/unreasonable range set. When the total length of 26 bytes is known, a helpful response is:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */26
~~~

Per RFC 9110, a server **may ignore `Range`** and return 200 in some situations; therefore clients must inspect actual status and headers rather than assuming malformed ranges always produce 416.

### 2.3. A Request with Multiple Ranges

Example:

~~~http
Range: bytes=0-2,23-25
~~~

The server may return `206` with `Content-Type: multipart/byteranges; boundary=...`. Each part carries `Content-Range` and its matching bytes. This is a **multipart response for multiple download ranges**, distinct from `multipart/form-data` used for **form/file uploads**.

~~~http
HTTP/1.1 206 Partial Content
Content-Type: multipart/byteranges; boundary=demo

--demo
Content-Type: text/plain
Content-Range: bytes 0-2/26

ABC
--demo
Content-Type: text/plain
Content-Range: bytes 23-25/26

XYZ
--demo--
~~~

The snippet above is a **human-readable illustration**; boundary, CRLF, and generated headers will differ in real responses. Never blindly append a multipart response body straight onto a file. The client must parse each part and write at the exact offset. Servers may also reject requests with too many tiny, overlapping, or abusive ranges.

### 2.4. `Accept-Ranges` Is Only a Signal

`Accept-Ranges: bytes` announces that the server expects to support byte ranges; `Accept-Ranges: none` signals no support. **Absence of `Accept-Ranges` does not automatically prove lack of support**, nor does its presence guarantee every future request returns 206. CDNs, reverse proxies, content encoding, or resource versions can alter behavior.

The reliable way to verify is **sending an actual `Range` request** and checking status `206`, `Content-Range`, and body length.

## 3. Resuming Requires Representation Integrity Checks

Suppose a client downloaded 500 bytes of version A. While disconnected, the server publishes version B with different contents at the same URL. If the client simply requests `Range: bytes=500-` and appends to the old 500 bytes, the resulting file becomes **half A + half B**—corrupted while still having the exact expected length.

### 3.1. `If-Range` in HTTP

**If the client retains a strong ETag** from the initial download, it can send:

~~~http
GET /files/report HTTP/1.1
Range: bytes=500-
If-Range: "sha256-or-version-of-A"
~~~

On an `If-Range`-compliant server:
- Validator still matches: returns **206** for the requested slice.
- Validator no longer matches: ignores Range and returns **200** with the complete new representation. The client **replaces** its temp file instead of appending.
- No reliable validator available: the client should use versioned immutable URLs, verify metadata/checksum before resuming, or restart the download.

**`If-Range` is not `If-None-Match`.** `If-None-Match` is a cache/GET conditional that can return `304 Not Modified`, whereas `If-Range` decides between **partial 206** and **full 200**. Per the RFC, never send `If-Range` without `Range`. **Never use a weak ETag** (such as `W/"abc"`) in `If-Range`; HTTP dates are usable only when qualifying as strong validators.

### 3.2. Practical Framework Version Caveats

Spring Framework provides **automatic Range support** for many `Resource` responses, yet **not every version guarantees complete handling of all `If-Range` branches**. Specifically on **Spring Framework 6.2.x** (paired with Spring Boot 3.5.x), **explicitly test the scenario where the validator changes mid-download**; do not infer from working basic 206 Range responses that `If-Range` works out of the box. Spring Framework added **“Honor If-Range for resource range requests” (#37218)** in the 7.1 line; do not assume that behavior exists in 6.2.

When downloads require strict consistency on Boot 3.5, practical strategies are:
1. **Immutable versioned URLs or object keys:** give each file version a distinct ID/version and never mutate bytes under an existing ID mid-download.
2. **Application-level metadata checks** before serving a range: verify the client's ETag/version matches the served object; on mismatch return full 200 or instruct a restart per the API contract.
3. **Checksums** and total byte verification after download completes; discard mismatched files.
4. **Integration tests for `Range` + `If-Range` with your proxy/CDN** on the exact Spring Framework/Boot versions deployed, not just parser unit tests.

Never use `Content-Length` as a validator: two different file versions can **have the exact same byte length**.

### 3.3. Client-Side Resume Algorithm

A solid download client should:
1. Record the URL, version/strong ETag, and total size alongside the temporary file.
2. If no partial data exists, send a normal GET or initial range and write bytes to a temp file.
3. After a disconnect, read the current temp file length `N`, and send `Range: bytes=N-` with `If-Range`/version where supported.
4. On `206`: verify `Content-Range` starts at **exact offset N** and total length/validator match; only then append bytes.
5. On `200`: discard the old temp file and write the **entire** new body from byte 0.
6. On `416`: inspect `Content-Range: bytes */L`; if `N=L` the file may already be complete, **yet still verify checksum/version**; if `N>L` or validator differs, restart.
7. On network error/`5xx`/`429`: retry with bounded attempts, exponential backoff, and timeouts; never splice unverified data.
8. Verify total size and checksum before renaming the temp file to its final artifact name.

For dynamically regenerated URLs, random access only makes sense if the server maintains **a stable snapshot** across requests.

## 4. When Does Spring MVC Support Automatic Range Handling?

Spring MVC parses `Range` via `HttpRange` and builds `ResourceRegion` objects written by `ResourceRegionHttpMessageConverter`. Endpoints returning appropriate **`Resource`** types get automatic Range support without manually slicing offsets or setting status 206.

Practical conditions in Spring Framework:
- `@ResponseBody`/`@RestController` method returns **`Resource`** or **`ResponseEntity<Resource>`**.
- With `ResponseEntity<Resource>`, the initial status must be **`200 OK`** for Spring to convert it to 206 on a valid Range.
- The Resource must **not** be an `InputStreamResource` (including single-read streams).
- MVC's static resource handler also supports Range for appropriate static assets.
- Default or compatible message converters/handlers must remain active; custom response writing bypasses this path.

### 4.1. Comparing Response Types and Auto-Range Support

| Return Approach | Characteristics | Auto `Range`? | When to Use |
| --- | --- | --- | --- |
| **`ResponseEntity<Resource>` + `FileSystemResource`** | Bounded file, repeatable/seekable reads | **Yes**, when initial status is 200 | Files on disk needing partial downloads |
| **`ResponseEntity<Resource>` + `ByteArrayResource`** | Bytes already in RAM, repeatable stream | **Yes**, when initial status is 200 | Small files already buffered in memory |
| **`ClassPathResource`** via controller/resource handler | Classpath/JAR resource, reopenable | **Usually yes**, if converter handles the Resource | Packaged assets or small/medium files |
| Static resource in `src/main/resources/static/` | Built-in Boot resource handler | **Yes** for eligible static assets | Public CSS/JS/images/files |
| **`InputStreamResource`** | Single-use stream, no general random access | **No** via auto-range mechanism | One-way proxies/streams from stream-only sources |
| **`ResponseEntity<byte[]>`** | Byte array written directly by converter | **No**, not a Resource | Small payloads not needing Range |
| **`StreamingResponseBody`** (MVC) | Writes directly to async output stream | **No** by type alone | Large/dynamically generated streams; handle Range yourself if needed |
| `HttpServletResponse.getOutputStream()` | Full manual control of body/status | **No**, developer responsible | Specialized streaming logic |
| `ResponseEntity<Flux<DataBuffer>>` (WebFlux) | Reactive buffer stream | **No** via Flux type | Reactive streams or data proxying |
| `ResponseEntity<Resource>` (WebFlux) | Reactive HTTP writer supporting Resource | **Yes**, under eligible Resource conditions | Reactive file/download endpoints |

**Note:** `FileSystemResource` streams from disk without loading the whole file into RAM. `ByteArrayResource` supports Range, yet **holds the whole file in memory**; never construct `ByteArrayResource(Files.readAllBytes(veryLargeFile))` for multi-GB files. With `InputStreamResource`, even if you know the file length and set `Content-Length`, that **does not make a one-shot stream seekable/repeatable**.

For static assets inside JARs, resources may require locating and reopening streams, so random-access performance differs from plain filesystem files or CDNs. **Protocol support does not imply fast seek performance on every backend.**

### 4.2. Headers That Do Not Enable Range

`Content-Disposition: attachment` controls the **download** vs. inline hint; it **does not** enable Range. `Content-Type` does not enable Range either. Manually adding `Accept-Ranges: bytes` to a `byte[]` response **will not** slice the body by Range. You need an actual processing path that parses Range and writes only the requested slice.

If a controller returns `ResponseEntity.status(HttpStatus.CREATED).body(resource)` or an error status, do not expect Spring to convert it to 206 on Range requests: Resource auto-range triggers when the initial response status is **200**.

## 5. Runnable Java 17 Example: Three Endpoints Serving the Same 26-Byte String

This example uses **Spring Boot 3.5.16**, released on Maven Central, with Java 17+ and Maven 3.6.3+. No database or upload is needed. It intentionally demonstrates **3 ways of returning the same content** to contrast Range behavior directly.

### 5.1. Project Structure

~~~text
range-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/rangedemo/
   │  ├─ RangeDemoApplication.java
   │  └─ FileDownloadController.java
   └─ resources/static/
      └─ alphabet.txt  (optional, created with exact 26 bytes as in step 5.5)
~~~

### 5.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>range-demo</artifactId>
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

### 5.3. `src/main/java/com/example/rangedemo/RangeDemoApplication.java`

~~~java
package com.example.rangedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RangeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RangeDemoApplication.class, args);
    }
}
~~~

### 5.4. `src/main/java/com/example/rangedemo/FileDownloadController.java`

~~~java
package com.example.rangedemo;

import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/files")
public class FileDownloadController {
    private static final byte[] ALPHABET =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ".getBytes(StandardCharsets.US_ASCII);

    // Path 1: Resource - Spring MVC turns 200 -> 206 automatically on valid Range.
    @GetMapping("/resource")
    public ResponseEntity<Resource> asResource() {
        Resource resource = new ByteArrayResource(ALPHABET);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"alphabet.txt\"")
                .body(resource);
    }

    // Path 2: byte[] - full body returned even if client sends Range.
    @GetMapping("/bytes")
    public ResponseEntity<byte[]> asBytes() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(ALPHABET);
    }

    // Path 3: StreamingResponseBody - one-way stream, no auto-range.
    @GetMapping("/stream")
    public ResponseEntity<StreamingResponseBody> asStream() {
        StreamingResponseBody stream = out -> out.write(ALPHABET);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(stream);
    }
}
~~~

**Why does the example use `ByteArrayResource` even though large files should use FileSystemResource?** This is a **tiny 26-byte fixture** to inspect byte ranges precisely. For real files, use seekable/range-capable storage and `FileSystemResource` or an equivalent Resource; never keep multi-GB files in `byte[]`.

Spring MVC routes `ResponseEntity<Resource>` through its dedicated Resource handler/converter; `ResponseEntity<byte[]>` goes through the byte-array converter; `StreamingResponseBody` uses a separate async streaming path. Same bytes, different return types, different Range behavior.

### 5.5. Optional: Static File for the Static Resource Handler

To test Range on Spring Boot's static files, create a **26-byte file with no trailing newline** at `src/main/resources/static/alphabet.txt`.

In bash:

~~~bash
mkdir -p src/main/resources/static
printf %s ABCDEFGHIJKLMNOPQRSTUVWXYZ > src/main/resources/static/alphabet.txt
~~~

In Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path src/main/resources/static
[System.IO.File]::WriteAllBytes(
  "src/main/resources/static/alphabet.txt",
  [System.Text.Encoding]::ASCII.GetBytes("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
)
~~~

When running, `GET /alphabet.txt` hits the **static resource handler**, not `FileDownloadController`. If your editor appends a trailing newline, the file becomes **27 bytes**, changing the total length reported in Content-Range. Creating the file with the commands above guarantees exactly 26 bytes.

### 5.6. Running the Application

From `range-demo`:

~~~bash
java -version
mvn spring-boot:run
~~~

Once listening on default port 8080, open another terminal (e.g., bash, or `curl.exe` in PowerShell) and test:

~~~bash
curl -i http://localhost:8080/files/resource
curl -i -H "Range: bytes=0-4" http://localhost:8080/files/resource
curl -i -H "Range: bytes=10-14" http://localhost:8080/files/resource
curl -i -H "Range: bytes=20-" http://localhost:8080/files/resource
curl -i -H "Range: bytes=-4" http://localhost:8080/files/resource
curl -i -H "Range: bytes=100-" http://localhost:8080/files/resource
~~~

Expected observations under **default configuration**:

| Request | Expected Status | Key Body / Headers |
| --- | --- | --- |
| No `Range` | **200** | Body `ABCDEFGHIJKLMNOPQRSTUVWXYZ`, 26 bytes total |
| `bytes=0-4` | **206** | `ABCDE`, `Content-Range: bytes 0-4/26` |
| `bytes=10-14` | **206** | `KLMNO`, `Content-Range: bytes 10-14/26` |
| `bytes=20-` | **206** | `UVWXYZ`, `Content-Range: bytes 20-25/26` |
| `bytes=-4` | **206** | `WXYZ`, `Content-Range: bytes 22-25/26` |
| `bytes=100-` | **416** (typically per framework) | `Content-Range: bytes */26` when provided |

The sample body **has no trailing newline**; `curl -i` may show your shell prompt right after `Z`. Other headers such as Date/Connection/Transfer-Encoding vary by HTTP server and environment.

Compare the two paths without automatic Range support:

~~~bash
curl -i -H "Range: bytes=0-4" http://localhost:8080/files/bytes
curl -i -H "Range: bytes=0-4" http://localhost:8080/files/stream
~~~

In the example, both endpoints return **200 OK** with **all 26 bytes** because neither implements manual Range parsing. `StreamingResponseBody` may write via an async executor; whether `Content-Length` is present depends on how the Servlet response is flushed. Never infer 206 merely because a response arrives in multiple network chunks.

For the optional `alphabet.txt` static file:

~~~bash
curl -i -H "Range: bytes=0-4" http://localhost:8080/alphabet.txt
~~~

With the exact 26-byte static file, expect **206** and `ABCDE` while static resource mapping is active and unaltered by security/proxies. Do not confuse the URL `/alphabet.txt` with `/static/alphabet.txt`.

**Testing multi-range:**

~~~bash
curl -i -H "Range: bytes=0-2,23-25" http://localhost:8080/files/resource
~~~

The response can be `206 multipart/byteranges`, with each part carrying its own `Content-Range`. The boundary string is framework-generated and not predictable byte-for-byte.

### 5.7. Testing Resume with curl on Immutable Content

Using bash in a suitable temporary directory:

~~~bash
# Step 1: intentionally fetch only the first ten bytes
curl -fsS -H "Range: bytes=0-9" \
  http://localhost:8080/files/resource -o alphabet.txt

# Step 2: curl resumes from the current file's byte offset
curl -fS -C - \
  http://localhost:8080/files/resource -o alphabet.txt

# Step 3: verify total length and contents
wc -c alphabet.txt
cat alphabet.txt
~~~

Stdout from `wc -c` includes the filename and shows **26 bytes** after appending succeeds (exact whitespace formatting varies by platform). `cat` prints `ABCDEFGHIJKLMNOPQRSTUVWXYZ` with no trailing newline. `-C -` tells curl to inspect the existing output file's length and request a resume; if the server refuses or returns incompatible headers, curl errors instead of corrupting the file. **In real products**, clients still must verify ETag/version/checksum and status codes to prevent mixing two file versions.

To test multiple clients, network drops, proxies, and 416 handling, write automated integration tests rather than trusting one manual curl run.

## 6. Serving Files from the Filesystem: `FileSystemResource`

An endpoint serving files saved on disk can return `ResponseEntity<Resource>` with `FileSystemResource` instead of `ByteArrayResource` to avoid loading entire files onto the heap. **Illustrative snippet**, assuming the service layer resolved the ID, verified permissions, and returned a **valid server-controlled `Path`**:

~~~java
// Integration snippet; requires imports and authorization service in a real project.
@GetMapping("/downloads/{id}")
public ResponseEntity<Resource> download(@PathVariable String id) {
    Path approvedPath = downloadService.resolveAuthorizedPath(id);
    Resource resource = new FileSystemResource(approvedPath);

    if (!resource.exists() || !resource.isReadable()) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"download.bin\"")
            .body(resource);
}
~~~

Resolve paths **from server metadata/storage** after authorization rather than taking user input and passing it to `Path.of(userInput)`. Verify canonical containment, guard against symlinks/traversal when paths vary, and never expose absolute server paths to clients. Rate limits, timeouts, and auditing can also be applied.

**Race/version note:** `FileSystemResource` can open a file while it is being overwritten on disk. If content or length changes between Range requests (or mid-stream), resuming can splice inconsistent bytes. For critical downloads, store files under **immutable versioned keys**, or serve snapshots alongside matching strong ETags/checksums.

For very large files, `FileSystemResource` fits when files actually live on local/mounted filesystems. If files live in S3/GCS/remote object storage, prefer **presigned download URLs** or properly Range-proxying streams instead of downloading the whole object into RAM and wrapping it in `ByteArrayResource`.

## 7. WebFlux: Similar Conditions, Different Writers from MVC

Spring **WebFlux** also handles Range automatically when an annotated controller returns `Resource` or `ResponseEntity<Resource>` (initial status 200, not `InputStreamResource`) and for eligible static resources. WebFlux uses `HttpRange`, `ResourceRegionEncoder`, and `ResourceHttpMessageWriter`, differing from Servlet MVC converters.

**WebFlux snippet** (does not belong in section 5's MVC project; use a project with `spring-boot-starter-webflux`):

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveDownloadController {

    @GetMapping("/reactive/file")
    Mono<ResponseEntity<Resource>> file() {
        Resource body = new ByteArrayResource(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ".getBytes(StandardCharsets.US_ASCII));
        return Mono.just(ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(body));
    }
}
~~~

`Mono<ResponseEntity<Resource>>` tells Spring the body is a `Resource`, enabling the WebFlux writer to handle Range. Changing the body to `Flux<DataBuffer>` turns the pipeline into a **sequential buffer stream**; it does not automatically translate client `Range` headers into 206. Proxying or streaming objects with resume requires handling offsets, total size, headers, and preconditions manually, or delegating to a storage API supporting HTTP Range.

**Non-blocking WebFlux does not make every storage backend seekable.** Running blocking disk reads or JDBC on the event loop stalls threads; when writing manual streams, use reactive APIs or proper schedulers and release `DataBuffer` per Spring's contract. For standard/static files, prefer the built-in Resource writer over rolling custom buffer pipelines.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Spring Boot usually chooses **MVC/Servlet application type**, so verify the active stack before drawing conclusions.

## 8. `ResourceRegion` and Handling Range Manually When Needed

### 8.1. Why Does `ResourceRegion` Exist?

`ResourceRegion` represents a slice of a Spring `Resource` defined by a **start position** and a **byte count**. `HttpRange` parses incoming Range headers and constructs regions:

~~~java
// Conceptual snippet, not a complete handler.
List<HttpRange> ranges = HttpRange.parseRanges("bytes=0-4,10-14");
List<ResourceRegion> regions = HttpRange.toResourceRegions(ranges, resource);
~~~

In Spring MVC, `ResourceRegionHttpMessageConverter` writes regions to the response; in WebFlux, `ResourceRegionEncoder` and `ResourceHttpMessageWriter` participate. **Do not** treat the snippet above as a complete endpoint: you still have to manage 200/206/416 selection, media types, multipart boundaries, Content-Range, Content-Length, HEAD, security, conditional validators, and abusive inputs.

Hand-rolling parsers/formatters has sharp edges: `bytes=-N`, `bytes=N-`, multi-range, start>end, integer overflow, out-of-bounds, 0-byte files, If-Range, duplicate/overlapping spans, media types, and compression. Exhaust built-in Resource handling first; write custom logic only when storage or domain requirements demand it.

### 8.2. Serving Files from Object Storage or Upstream HTTP

When the backend proxies an object store supporting `Range`:
1. Client sends Range and optional If-Range/version.
2. Backend authenticates, authorizes, and looks up the user's object/version.
3. Backend forwards an appropriate Range to upstream (or invokes byte-range SDK APIs), capping range count/offsets per policy.
4. Read upstream status/headers; **never** hardcode `206` solely because you sent Range.
5. Forward or accurately reconstruct `Content-Range`, `Content-Type`, `Content-Length`, validators, and body; for multipart, preserve boundaries and each part.
6. If upstream returns **200 full**, the client-facing backend must never spoof 206 unless it explicitly sliced bytes and computed exact headers itself.
7. Handle cancellation/backpressure so connections and streams do not linger after client disconnects.

For very large files, presigned URLs directly to object storage/CDN beat funneling every byte through the JVM. If the backend must gate access, mint short-lived URLs after authorization with tight TTL and scope.

## 9. Method Semantics, Caching, and Content Encoding Limits

### 9.1. Range Applies to GET; HEAD Inspects Metadata Only

Per HTTP, `Range` is defined for **GET**. Servers must ignore `Range` on methods where its semantics do not apply, such as POST. `HEAD` retrieves representation headers without a body; it is useful for inspecting total size/ETag, **not for downloading byte ranges**.

Do not confuse `HEAD + Range` with resuming a slice. Always use **GET** to resume downloads.

### 9.2. Preconditions Have a Defined Precedence

Preconditions such as `If-None-Match`/`If-Modified-Since` are evaluated before Range. When GET would return `304 Not Modified`, the server need not process Range into 206 for that request. `If-Range` is specific to partial downloads; it checks whether the representation changed and (if so) permits sending the full representation.

Never mix `If-Range`, `If-Match`, and `If-None-Match` blindly without understanding that outcomes can be **200, 206, 304, 412, or 416** depending on headers and resource state.

### 9.3. `Content-Encoding: gzip` Complicates Byte Offsets

`Range: bytes=...` indexes **the selected representation data**, including content coding if transmitted with `Content-Encoding`. For example, if a server transmits a gzip-compressed response, offsets in the gzip stream **do not match** offsets in the uncompressed file. Therefore:
- resuming clients should request the **same representation variant** (content encoding, ETag, URL/version);
- during testing, send `Accept-Encoding: identity` when checking byte offsets directly against an uncompressed file;
- proxies/CDNs that compress or transform responses can alter validators and lengths;
- `Vary: Accept-Encoding` and per-variant ETags must stay consistent to avoid corrupting assembled bytes;
- serving a compressed archive like `.zip` does not mean the HTTP response uses `Content-Encoding: gzip`—those are two distinct layers.

### 9.4. HTTP Chunked Transfer Is Not Range

`Transfer-Encoding: chunked` (HTTP/1.1) is a **wire framing mechanism** for responses, not a way for clients to request bytes from offset 500 to EOF. A 200 chunked response can stream long payloads smoothly yet still offers **no random access**. HTTP/2 and HTTP/3 have their own framing while preserving `Range`/`206` semantics at the HTTP layer.

### 9.5. CDNs and Reverse Proxies

Ranges may be served by the app, a reverse proxy, or a CDN. Behind Nginx/Envoy/load balancers, verify:
- whether `Range`/`If-Range` headers are forwarded;
- whether the proxy strips or alters `Content-Encoding`, `ETag`, or `Content-Length`;
- whether redirects drop authorization headers or alter versioned URLs;
- whether `206`, `416`, and multipart responses remain valid under caching;
- whether cache and authorization policies prevent private-file leaks;
- whether proxy timeouts/limits abort long downloads.

If direct app calls return 206 while CDN calls return 200, compare response headers and proxy caching/transformation rules before changing controller code.

## 10. Performance and Safety When Allowing Partial Downloads

**More ranges is not better.** A request containing thousands of tiny or overlapping ranges can force the server into repeated seeks/reads and inflate multipart response bodies. Restrict range counts and request sizes per actual risk, use built-in parsers, rate limits, and ingress caps.

**Memory cost:** avoid `Files.readAllBytes` for large files, especially under concurrent downloads. Serving 100 concurrent users each with a 200 MB `ByteArrayResource` creates massive heap pressure. Use file-based Resources, container-supported zero-copy, object storage, or CDNs, and benchmark real workloads.

**Storage cost:** random reads across HDDs, object stores, network filesystems, and JARs carry very different costs. Supporting 206 does not guarantee fast seeks or cheap cloud GETs. For segmented clients, choose adequately sized chunks, bound parallel fan-out, and monitor bandwidth/request costs.

**Paths and permissions:** never let users pass `/etc/passwd` or `../secrets` directly as file paths. Use opaque file IDs with service authorization, normalize paths, defend against symlinks/traversal, and serve only from approved directories. Never expose uploaded files publicly just by dropping them into `src/main/resources/static` or a static-mapped directory.

**Download headers:** `Content-Disposition: attachment` fits when browsers should download files; sanitize filenames, Unicode, and guard against header injection. `Content-Type` must be accurate or fall back to `application/octet-stream` for generic binary; apply `X-Content-Type-Options: nosniff`, CSP, and safe origin policies for user uploads.

**Stable files:** use IDs/versions, immutable snapshots, ETags/hashes, and final checksums. If a file mutates mid-download, no client append algorithm can keep it consistent.

**System resources:** enforce network/storage timeouts, cap concurrent connections, and monitor throughput, p95 download latency, memory/GC, HTTP 206/416 ratios, cancellations, and upstream errors. An app can slice ranges properly yet still saturate bandwidth or file descriptors.

## 11. Decision Table: Choosing How to Serve a Resource

| Requirement | Recommended Choice | Why |
| --- | --- | --- |
| Public CSS/JS/images/files from JAR | Static resource handler or CDN | Spring Boot configures Range out of the box for eligible resources |
| File on disk needing resume | `ResponseEntity<Resource>` + `FileSystemResource` | Known length/repeatable reads, auto-range on status 200 |
| Small file already in byte[] | `ByteArrayResource` | Easy to test, Spring handles Range; avoid for very large files |
| Row-by-row streamed output of unknown length (live CSV/reports) | `StreamingResponseBody` (MVC) or `Flux<DataBuffer>` (WebFlux) | Sequential stream; **no auto-resume**, so build a snapshot first if needed |
| Single-read DB BLOB stream | One-way stream, or stage to file/object first | Cannot guarantee seek/length/reopen; materialize a stable resource for resume |
| Large file in S3/GCS | Presigned URL or controlled Range proxy | Offloads byte transfer and leverages storage-native Range |
| Media player seeking | Stable file/representation, working Range, proper media container | Players request varying byte offsets over time |
| Multiple file versions at one URL | Versioned URLs, proper ETag/If-Range, integration tests | Prevents splicing bytes across versions |

Distinguish **dynamically generated files** from **pre-generated immutable files**. A CSV report queried live from a DB on every GET can change row order or size between requests, rendering Range unsafe. If users need resume, generate and store a snapshot with an ID, size, hash, and TTL, then serve the snapshot as a file/resource.

## 12. Common Issues and Investigation Guide

| Symptom | Common Cause | What to Do |
| --- | --- | --- |
| Sent `Range` yet always get **200** | Returned `byte[]`, `StreamingResponseBody`, `InputStreamResource`, non-200 initial status, or proxy stripped Range | Inspect actual return type, endpoint, and proxy path |
| `206` yet body has wrong bytes | Buggy manual offset math (end is inclusive) or upstream returned different data | Check `Content-Range`, 0-based offsets, and checksums |
| Resumed file corrupted despite matching size | Spliced bytes across two versions or gzip vs. identity variants | Use strong validators, immutable URLs, and checksums |
| `416` when resuming | Local offset exceeds current file length, file mutated, or out-of-bounds range | Inspect `Content-Range: bytes */L` and verify local size/version |
| Cannot assemble multi-range response | Body is `multipart/byteranges`, not raw contiguous bytes | Parse each part with its `Content-Range` |
| `Content-Length` is 1024 while full file is 100 MB | Viewing a `206` partial response | Read total length from `Content-Range` |
| Missing `Content-Length` | Long/unknown-length stream with dynamic transfer framing | Do not assume “no stream”; use separate metadata if resuming |
| `Accept-Ranges: bytes` present yet Range never yields 206 | Advertised header does not guarantee every case | Test real GET Range, cache rules, and proxies |
| Returned `ResponseEntity<Resource>` yet no 206 | Underlying body is `InputStreamResource` or custom converter/wrapper | Use a repeatable Resource, status 200, and check stack |
| Browser restarts full download after network drop | URL/file mutated, Range unsupported, or client lacks resume support | Inspect network traces, `Range`, `If-Range`, and versioned URLs |
| `206` direct from app, `200` via CDN | Proxy caching/normalization/compression interfering | Compare headers direct vs. CDN and check cache config |
| Media player cannot seek video | Range broken, wrong MIME, or bad media container metadata | Verify Range + Content-Type + media container index/moov placement |
| `byte[]` downloads cause OutOfMemoryError | Full files held on heap across concurrent requests | Switch to FileSystemResource/object storage/streaming |
| Wrong-version `If-Range` still returns `206` on older app | Implementation did not fully honor validator | Use immutable snapshots/URLs or custom check; test version changes |
| `HEAD` differs from GET | Custom handler/response emitted inconsistent metadata | Compare GET vs. HEAD headers; avoid wrong manual Content-Length |
| `Range` with thousands of spans slows server | Resource abuse/DoS via many tiny ranges | Limit ranges, rate limit, and monitor I/O |

### Minimal Verification Workflow

1. Send GET without Range: record status, `Content-Length`, `ETag`/`Last-Modified`, `Content-Encoding`, and received file hash.
2. Send `Range: bytes=0-4`: verify **206**, `Content-Range`, and exact 5 bytes.
3. Send `Range: bytes=-4`: verify suffix range.
4. Send `Range: bytes=100000000-` on a small fixture: observe **416**/`Content-Range` and application error handler.
5. Test `Range: bytes=0-2,23-25`: verify multipart response if returned.
6. Compare `/files/resource` against `/files/bytes` and `/files/stream` to see differences.
7. For production resume, change the version between two GETs, send `If-Range`, and verify the client **does not append** a 200 body.
8. Test via proxy/CDN and with `Accept-Encoding: identity` and `gzip` (if enabled).
9. Test authorization on the same file, file deleted mid-download, client aborting mid-stream, and concurrency load.

## 13. Self-Check Questions

1. For a 1,000-byte file, a client sends `Range: bytes=500-`. If supported, what are the ideal `Content-Range` and `Content-Length`?
2. Why does `Range: bytes=0-4` return **5 bytes** rather than 4?
3. For a 26-byte file, what does `Range: bytes=-4` return?
4. Why can `ResponseEntity<byte[]>` return full 200 even when a client sends `Range`?
5. Why does `InputStreamResource` lack automatic Range support like `FileSystemResource`?
6. A client has 400 old bytes and receives a full-body 200 response on resume: what must it do?
7. Do `If-Range` and `If-None-Match` share the same semantics?
8. If a response is gzip-compressed over HTTP, do Range byte offsets point into the original uncompressed bytes or the selected encoded representation?
9. Why does `Content-Disposition: attachment` not mean the server supports resume?
10. An app returns `StreamingResponseBody` to export live CSVs. How should its architecture change to support safe resume?
11. Both MVC and WebFlux support auto-range for `Resource`, but which framework writers/converters differ?
12. When `Range` requests multiple spans, what can the response `Content-Type` be?
13. If the static handler returns `206` yet a controller endpoint returns `200`, what do you inspect first?
14. Why is checking total file size after concatenating insufficient to prove versions were not mixed?
15. When serving a 10 GB file, why is `FileSystemResource` generally preferable to `ByteArrayResource(Files.readAllBytes(...))`?
16. If a project uses Spring Boot 3.5 / Framework 6.2, what must you do before relying on `If-Range` for safe resumes?

**Core answers:** (1) `bytes 500-999/1000` and body length 500; (2) end is inclusive and indexing is 0-based; (3) `WXYZ`; (4) `byte[]` does not trigger Resource auto-range; (5) single-use stream lacks standard seek/reopen; (6) replace the temp file with the full body, never append; (7) no, If-Range chooses partial vs. full while If-None-Match is a cache conditional; (8) selected representation after content coding; (9) only hints filename/display; (10) generate an immutable snapshot first and serve as a Resource/object; (11) MVC uses ResourceRegionHttpMessageConverter while WebFlux uses ResourceRegionEncoder/ResourceHttpMessageWriter; (12) `multipart/byteranges`; (13) return body type, initial status, and active converter/route; (14) different contents can share the same size; (15) avoids blowing up heap and supports repeatable reads; (16) integration-test version mutations and use immutable objects/versions or explicit validator handling.

## 14. Official References

- **RFC 9110 — HTTP Semantics, Sections 13–15:** https://www.rfc-editor.org/rfc/rfc9110.html — `Range`, `If-Range`, `206`, `416`, `Content-Range`.
- **Spring Framework — Spring MVC Range Requests:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html — `Resource` and `ResponseEntity<Resource>` conditions, `InputStreamResource` exception.
- **Spring Framework — WebFlux Range Requests:** https://docs.spring.io/spring-framework/reference/web/webflux/range.html — reactive resource writing and `ResourceRegionEncoder`.
- **Spring Framework — MVC static resources:** https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html — how Spring resolves and serves static resources.
- **Spring Framework Javadoc — InputStreamResource:** https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/io/InputStreamResource.html — single-use stream behavior.
- **Spring Boot 3.5 System Requirements:** https://docs.spring.io/spring-boot/3.5/system-requirements.html — Java 17+, Framework 6.2.x, and compatible Maven.
- **Spring Framework issue #34490:** https://github.com/spring-projects/spring-framework/issues/34490 — example 416/static-handler fix in 6.2.9; use a properly patched release.
- **Spring Framework enhancement #37218 (If-Range):** https://github.com/spring-projects/spring-framework/issues/37218 — why `If-Range` compatibility must be verified per version rather than inferred from `206`.
- **MDN — HTTP range requests:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests — client/server examples and streaming/resume.
