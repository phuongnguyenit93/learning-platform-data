# Range Requests, ResourceRegion, and 206 Partial Content Responses in Spring MVC

## 1. Why Does HTTP Range Matter?

When a client downloads a video, PDF, or large document, it may need **a slice of bytes** instead of re-downloading the entire file. A video player wants to seek to a new timestamp, a download manager wants to resume an interrupted download, and a PDF viewer may need the range containing metadata or the page being opened.

HTTP supports **Range Requests**, defined in RFC 9110. The client sends a `Range` header, and the server can respond with `206 Partial Content` carrying the exact byte range. In Spring Web MVC, `Resource`, `HttpRange`, `ResourceRegion`, and `ResourceRegionHttpMessageConverter` handle most of this work.

This lesson targets **Spring MVC on the Servlet stack** with **Java 17, Spring Boot 3.3.5, and Spring Framework 6.1.x**. It covers HTTP Range syntax and semantics, Spring auto-range, using `ResourceRegion`, 200/206/416 responses, multi-range, `ETag`/`If-Range`, a runnable Maven app, MockMvc tests, and real-world deployment constraints. WebFlux uses different reactive writers, so MVC controller/converter code does not apply verbatim.

## 2. Understanding Byte Offsets Properly

Suppose a file has exactly 10 ASCII bytes:

```text
Content: A B C D E F G H I J
Offset:  0 1 2 3 4 5 6 7 8 9
Length: 10 bytes
```

The client sends:

```http
GET /api/files/sample HTTP/1.1
Host: localhost:8080
Range: bytes=2-5
```

A valid response when the server honors the Range:

```http
HTTP/1.1 206 Partial Content
Content-Type: text/plain
Accept-Ranges: bytes
Content-Range: bytes 2-5/10
Content-Length: 4

CDEF
```

Explanation:

- `bytes` is the HTTP range unit.
- Both **start byte 2 and end byte 5 are inclusive**: there are `5 - 2 + 1 = 4` bytes.
- `/10` in `Content-Range` is the size of the **entire representation**, not the slice length.
- `Content-Length: 4` is the length of the **actual partial response**. With transfer encoding/chunking, this header is not necessarily always present.
- The real HTTP status is `206`, not `200` with JSON `{"code":206}`.
- The body contains only `CDEF`.

**Ranges are byte-based, not character-based.** In UTF-8, a Vietnamese character can span multiple bytes, so a Range can split inside a single character; a client downloading in parts must assemble all bytes before decoding. With content coding `gzip` or `br`, offsets apply to the **selected representation bytes** (already content-encoded if sent that way); never equate them directly with uncompressed file offsets.

## 3. Four Common Range Forms

```http
Range: bytes=<first>-<last>
Range: bytes=<first>-
Range: bytes=-<suffix-length>
Range: bytes=<first1>-<last1>,<first2>-<last2>
```

For the 10-byte `ABCDEFGHIJ`:

| Header | Interpretation | Part returned |
| --- | --- | --- |
| `bytes=0-3` | From byte 0 through byte 3 | `ABCD` |
| `bytes=2-5` | From byte 2 through byte 5 | `CDEF` |
| `bytes=7-` | From byte 7 to the end | `HIJ` |
| `bytes=-3` | Last three bytes | `HIJ` |
| `bytes=9-99` | From 9, end exceeds total | `J` (clamped at 9) |
| `bytes=0-1,8-9` | Two non-contiguous ranges | `AB` and `IJ` |
| `bytes=10-20` | Starts beyond file end | Unsatisfiable, usually `416` |
| `bytes=5-4` | End before start | Invalid syntax/range |

**`bytes=7-` differs from `bytes=-7`**: the first starts at offset 7 through the end; the second takes the last 7 bytes. If the suffix length exceeds the file length, the valid range may be the entire representation.

A client may send a `Range` header, yet **the server is allowed to ignore it** and return `200 OK` with the full representation in valid scenarios. Never assume sending `Range` guarantees receiving `206`. Malformed ranges, overflows, or requests with hundreds of ranges must be handled by a proper parser and bounds, never by naive `split("-")` and `int` casting.

## 4. 200 OK, 206 Partial Content, 416 Range Not Satisfiable

### 4.1. 200: Returning the Full Resource

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 10
Accept-Ranges: bytes

ABCDEFGHIJ
```

Typical response when no `Range` is sent. `Accept-Ranges: bytes` signals that the server supports byte ranges; this header is **not necessarily** emitted by every range-capable server. A server not supporting ranges may advertise `Accept-Ranges: none`. Absence of the header does not always mean ranges are unsupported.

Do not attach `Content-Range` on a normal 200 to describe the whole file; the RFC defines `Content-Range` semantics for 206/416.

### 4.2. 206: Returning a Partial Slice

```http
HTTP/1.1 206 Partial Content
Content-Type: text/plain
Content-Range: bytes 7-9/10
Content-Length: 3

HIJ
```

A **single-part 206** must carry a `Content-Range` accurately describing the byte slice sent. For `bytes=7-9`, there are 3 bytes. The `Content-Length` header, when emitted, states the response body size, not the total in `/10`.

### 4.3. 416: No Byte Range Satisfiable

```http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */10
```

`bytes */10` indicates the entire current representation is 10 bytes long. This is the RFC-recommended unsatisfied-range format for out-of-bounds range errors. Never return `Content-Range: bytes 20-30/10` because it does not describe an existing range.

A **syntactically invalid** `Range` header and a **syntactically valid but out-of-bounds** `Range` header do not necessarily behave identically everywhere; exact status/body can be shaped by the parser, reverse proxy, and exception handling.

## 5. Multiple Ranges and multipart/byteranges

With:

```http
Range: bytes=0-1,8-9
```

the server can reply with two parts:

```http
HTTP/1.1 206 Partial Content
Content-Type: multipart/byteranges; boundary=demo-boundary

--demo-boundary
Content-Type: text/plain
Content-Range: bytes 0-1/10

AB
--demo-boundary
Content-Type: text/plain
Content-Range: bytes 8-9/10

IJ
--demo-boundary--
```

This example illustrates structure only; real HTTP multipart uses CRLF and a server-generated boundary. Key rules:

- For multiple parts, the outer `Content-Type` is `multipart/byteranges`, **not** `multipart/form-data` (which is for uploads).
- `Content-Range` must appear inside **each part**, not at the top level of the multipart response.
- `Content-Length`, if present, is the size of the **entire multipart body** including boundaries, part headers, and bytes; not just `2+2=4`.
- Servers may coalesce overlapping/adjacent ranges or limit range counts; clients must parse actual `Content-Range` headers rather than assuming exact requested layout.
- Spring's `ResourceRegionHttpMessageConverter` supports writing a single `ResourceRegion` or a collection of `ResourceRegion` objects accordingly.

## 6. Automatic Range Handling in Spring MVC

In Spring MVC 6.1, a controller can return `Resource` or `ResponseEntity<Resource>`. The framework can handle Ranges without the controller **reading the `Range` header or slicing bytes itself**.

```text
GET /files/42
  Range: bytes=2-5
      |
      v
DispatcherServlet -> @GetMapping
      |
      v
Controller returns ResponseEntity<Resource> status 200
      |
      v
Spring parses Range via HttpRange
      |
      v
HttpRange -> List<ResourceRegion>
      |
      v
ResourceRegionHttpMessageConverter writes 206 + 4 bytes
      |
      v
HTTP 206, Content-Range: bytes 2-5/10
```

**Two critical conditions:**

1. The `Resource` is not an `InputStreamResource`.
2. For `ResponseEntity<Resource>`, the **initial status must be 200 OK**.

Therefore, do not do:

```java
// ANTI-PATTERN: setting 206 manually does not trigger MVC auto-range.
return ResponseEntity.status(HttpStatus.PARTIAL_CONTENT)
        .body(resource);
```

If you pre-set status 206 while the body is still the entire `Resource`, the auto-range branch may be bypassed and the response becomes semantically broken. Let Spring start from 200 or implement byte regions and headers manually if you have a special use case.

### Which Resource Types Fit?

| Resource | Suitable for auto-range? | Notes |
| --- | --- | --- |
| `FileSystemResource` | Yes, usually suitable | Real file, has length and reopenable stream |
| `PathResource` | Yes, usually suitable | Needs safe storage path and access checks |
| `ByteArrayResource` | Yes, for small data | Already holds all bytes in RAM |
| `InputStreamResource` | **Do not use for auto-range** | Typically one-shot stream; length/repeatability hard to guarantee |
| Custom `Resource` | Depends on implementation | Needs accurate length and reopenable/seekable stream |

In Spring MVC, auto-range happens at the return-value/converter layer; `HttpRange` and `ResourceRegion` model each slice, and `ResourceRegionHttpMessageConverter` writes the exact bytes. For static assets served via Spring resource handlers, Spring also supports Range requests; do not write unnecessary controllers for public static files.

### What If the Pre-Range Status Is Not 200?

A conditional GET returning `304 Not Modified` does not become `206`. An error response like `404`, `403`, or `500` likewise does not turn into a partial file just because the client sent `Range`. Per the RFC, `Range` is evaluated after preconditions and only when the non-range response would be `200`. Check authorization and representation conditions **before** sending bytes.

## 7. Complete Runnable Maven Project

We build an API serving a single test file containing 10 ASCII bytes `ABCDEFGHIJ`. The controller always returns `ResponseEntity<Resource>` with status 200 on success; Spring automatically selects 200, 206, or 416 based on `Range`. Output is easy to verify because the size and bytes are fixed.

### 7.1. Project Tree

```text
mvc-range-demo/
├── pom.xml
└── src/
    ├── main/java/demo/ranges/
    │   ├── RangeApplication.java
    │   └── SampleFileController.java
    └── test/java/demo/ranges/
        └── SampleFileControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-range-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

**`src/main/java/demo/ranges/RangeApplication.java`**

```java
package demo.ranges;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RangeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RangeApplication.class, args);
    }
}
```

**`src/main/java/demo/ranges/SampleFileController.java`**

```java
package demo.ranges;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/files")
public class SampleFileController {

    private static final byte[] SAMPLE =
            "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII);

    @GetMapping(path = "/sample",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<Resource> sample() {
        Resource resource = new ByteArrayResource(SAMPLE) {
            @Override
            public String getFilename() {
                return "sample.txt";
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"sample.txt\"")
                .body(resource);
    }
}
```

**Why does this example support Range?**

- `SAMPLE` is exactly 10 bytes (ASCII), wrapped in `ByteArrayResource` so streams can be reopened and `contentLength()` retrieved.
- `ResponseEntity.ok()` creates an initial 200 response; Spring MVC can convert it to 206/416.
- `produces=text/plain` and `Content-Type: text/plain` match the file's bytes.
- `Content-Disposition` uses a **server-hardcoded** filename to demonstrate download behavior, never a user-supplied name.
- The controller never reads `Range`, slices arrays manually, or hardcodes `Content-Length` or `Content-Range`. The framework decides per request.
- `ByteArrayResource` is only for small examples: multi-GB files should use `FileSystemResource` or storage-native range reads instead of `Files.readAllBytes()`, which wastes RAM.

### 7.2. Run Commands and HTTP Results

Inside `mvc-range-demo` with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Run the two commands sequentially. The application defaults to `http://localhost:8080`.

**Full resource:**

```bash
curl -i http://localhost:8080/api/files/sample
```

Key response values:

```http
HTTP/1.1 200
Content-Type: text/plain
Accept-Ranges: bytes

ABCDEFGHIJ
```

**First four bytes:**

```bash
curl -i -H 'Range: bytes=0-3' \
  http://localhost:8080/api/files/sample
```

```http
HTTP/1.1 206
Content-Range: bytes 0-3/10
Content-Type: text/plain

ABCD
```

**Last three bytes:**

```bash
curl -i -H 'Range: bytes=-3' \
  http://localhost:8080/api/files/sample
```

Expected `206` with `Content-Range: bytes 7-9/10`, body `HIJ`.

**From byte 7 to the end:**

```bash
curl -i -H 'Range: bytes=7-' \
  http://localhost:8080/api/files/sample
```

Expected `206`, `Content-Range: bytes 7-9/10`, body `HIJ`.

**Out-of-bounds range:**

```bash
curl -i -H 'Range: bytes=20-30' \
  http://localhost:8080/api/files/sample
```

Expected `416` and header `Content-Range: bytes */10` via Spring MVC 6.1's auto-range branch. The error body or other headers depend on framework/config, not a custom demo JSON contract.

**Two non-contiguous ranges:**

```bash
curl -i -H 'Range: bytes=0-1,8-9' \
  http://localhost:8080/api/files/sample
```

Expected `206`, `Content-Type: multipart/byteranges; boundary=...`, each part carrying `Content-Range` with `AB` and `IJ`. The boundary is dynamically generated, so do not hardcode it in tests. For large binaries, use `curl -D headers.txt -o bytes.bin` to avoid printing file bytes to the terminal.

On Windows PowerShell, `curl` may be aliased to another tool depending on the environment; use `curl.exe` when exact curl flags are needed.

## 8. Contract Testing With MockMvc

**`src/test/java/demo/ranges/SampleFileControllerTest.java`**

```java
package demo.ranges;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.ResourceRegion;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRange;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SampleFileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noRangeReturnsWholeResource() throws Exception {
        mvc.perform(get("/api/files/sample"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    HttpHeaders.ACCEPT_RANGES, "bytes"))
           .andExpect(content().bytes(
                    "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void firstFourBytesReturn206() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=0-3"))
           .andExpect(status().isPartialContent())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes 0-3/10"))
           .andExpect(content().bytes(
                    "ABCD".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void suffixRangeSelectsLastThreeBytes() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=-3"))
           .andExpect(status().isPartialContent())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes 7-9/10"))
           .andExpect(content().bytes(
                    "HIJ".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void openEndedRangeSelectsRest() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=7-"))
           .andExpect(status().isPartialContent())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes 7-9/10"))
           .andExpect(content().bytes(
                    "HIJ".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void invalidOffsetReturns416() throws Exception {
        mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=20-30"))
           .andExpect(status().isRequestedRangeNotSatisfiable())
           .andExpect(header().string(
                    HttpHeaders.CONTENT_RANGE, "bytes */10"));
    }

    @Test
    void multipleRangesUseMultipartByteranges() throws Exception {
        MvcResult result = mvc.perform(get("/api/files/sample")
                    .header(HttpHeaders.RANGE, "bytes=0-1,8-9"))
           .andExpect(status().isPartialContent())
           .andReturn();

        String contentType = result.getResponse().getContentType();
        assertTrue(contentType != null &&
                contentType.startsWith("multipart/byteranges;"));

        String body = new String(
                result.getResponse().getContentAsByteArray(),
                StandardCharsets.ISO_8859_1);
        assertTrue(body.contains("Content-Range: bytes 0-1/10"));
        assertTrue(body.contains("Content-Range: bytes 8-9/10"));
        assertTrue(body.contains("AB"));
        assertTrue(body.contains("IJ"));
    }

    @Test
    void httpRangeCreatesCorrectResourceRegion() {
        Resource resource = new ByteArrayResource(
                "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));
        List<HttpRange> ranges = HttpRange.parseRanges("bytes=2-5");
        List<ResourceRegion> regions =
                HttpRange.toResourceRegions(ranges, resource);

        assertEquals(1, regions.size());
        assertEquals(2L, regions.get(0).getPosition());
        assertEquals(4L, regions.get(0).getCount());
    }
}
```

Run:

```bash
mvn test
```

There are **7 test methods**. When all pass on a properly created project, Maven exits with code `0` and typically summarizes `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0`. This educational code is designed against Java 17 and Spring Boot 3.3.5 APIs; this lesson does not claim Maven was executed in the environment where the guide was authored.

MockMvc verifies the MVC pipeline, yet does not fully represent reverse proxies, caches, HTTP compression, connection drops, or multi-GB file streaming. Real binaries need end-to-end tests through an embedded server and CDN/proxy.

## 9. HttpRange and ResourceRegion: The Underlying API

`HttpRange` models the byte ranges requested by the client. You can parse a header:

```java
List<HttpRange> ranges =
        HttpRange.parseRanges("bytes=2-5");
List<ResourceRegion> regions =
        HttpRange.toResourceRegions(ranges, resource);
```

This snippet requires a `resource` variable, imports, and appropriate context; `httpRangeCreatesCorrectResourceRegion` in the tests above shows a complete runnable example.

Other factories:

```java
HttpRange firstFour = HttpRange.createByteRange(0, 3);
HttpRange fromSeven = HttpRange.createByteRange(7);
HttpRange lastThree = HttpRange.createSuffixRange(3);
```

`ResourceRegion` holds the underlying `Resource`, `position`, and `count`:

```java
ResourceRegion region = new ResourceRegion(resource, 2L, 4L);
```

**`count` is the byte count, not the last byte offset.** For `bytes=2-5`: position = 2, count = 4. Passing count = 5 reads an extra 6th byte, causing an off-by-one bug.

`HttpRange.parseRanges` can throw `IllegalArgumentException` on malformed input or too many ranges; `toResourceRegions` computes regions from the Resource's length and can reject unsatisfiable data. Never hand-roll regex parsing without handling suffixes, overflows, comma-separated ranges, and changing content lengths.

`ResourceRegionHttpMessageConverter` writes one or more `ResourceRegion` items to the HTTP response. Use manual `ResourceRegion` handling when you need custom range policies, special backing stores, or custom handling; for standard file downloads, `ResponseEntity<Resource>` with 200 is simpler and less error-prone.

### When Building 206 Responses Manually

If you choose to read the `Range` header and return regions manually, you take responsibility for:

1. Parsing/validating `Range` and the total size of the **exact selected representation**.
2. Checking authorization, preconditions, and `If-Range` with proper semantics.
3. Without `Range`: returning 200 + the whole `Resource`.
4. With one or more valid ranges: returning 206 + exact region(s), content type, and `Content-Range`/multipart.
5. When unsatisfiable: returning 416 + `Content-Range: bytes */total` when appropriate.
6. Never setting a 206 `Content-Length` to the entire file length.
7. Bounding range counts, total bytes, seek costs, header length, and read time.
8. Never wrapping binary responses in a JSON envelope via `ResponseBodyAdvice`.

Unless those specialized responsibilities are truly needed, avoid reimplementing protocol logic Spring already provides.

## 10. If-Range, ETag, and Resource Consistency

A client downloads part of file v1, then the server replaces the file with v2. If the client requests the rest and stitches bytes from two versions together, the resulting file is corrupt. Thus safe **resumable downloads** must ensure all bytes belong to the same version of the representation.

HTTP uses:

- `ETag`: representation validator.
- `Last-Modified`: modification-time metadata.
- `If-None-Match` / `If-Modified-Since`: conditional caching, which can produce `304 Not Modified`.
- `If-Range`: requests applying `Range` **only if the representation still matches the validator**; otherwise, send the full representation.

Example:

```http
GET /api/files/video HTTP/1.1
Range: bytes=1000-
If-Range: "file-version-v7"
```

If `If-Range` matches under **strong validation**, the server may return 206. If it does not match, the server must ignore `Range` and send the full representation (typically 200). **Weak ETags** like `W/"..."` are unsuitable for strong comparison in `If-Range`.

**Spring MVC 6.1 note:** The auto-range path when returning `ResponseEntity<Resource>` observes `Range` and status 200, yet you should **never assume** the application automatically has full `If-Range` handling and snapshot consistency across every Servlet/proxy path. When files can mutate, explicitly test or implement precondition/validator logic at the right layer; never let v1 and v2 stitch together just because HTTP returned 206.

If a conditional GET returns `304`, do not process `Range` as part of a 200. Per the RFC, `Range` is evaluated after preconditions and only applies when the non-range response would be 200.

### Byte-Accurate Strong Validators

A strong ETag should bind tightly to the bytes of the selected representation. Use immutable storage versions or precomputed content digests where appropriate; never compute SHA-256 of an 8GB file from scratch on **every** Range request without cached metadata. When variants differ by `Content-Encoding`, assign distinct validators per representation so two non-identical byte sequences never share an ETag.

## 11. FileSystemResource, PathResource, and Security

The demo uses `ByteArrayResource` because there are only 10 bytes. For real files, use `FileSystemResource` or `PathResource` with real lengths and reopenable streams:

```java
Path file = trustedRoot.resolve(serverOwnedKey).normalize();
if (!file.startsWith(trustedRoot) ||
        !Files.isRegularFile(file) ||
        !Files.isReadable(file)) {
    throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "File not found");
}
Resource resource = new FileSystemResource(file);
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(resource);
```

This is a **snippet** without class/imports or definitions of `trustedRoot`/`serverOwnedKey`; it expresses the pattern only. In practice:

- Check resource access permissions **before** returning the `Resource`.
- Never take raw filenames from the client or request parameters as storage paths. Use server-generated storage keys.
- `Path.normalize()` / `startsWith()` alone is not enough to stop symlink races or TOCTOU; filesystem isolation and security policies are required.
- Set `Content-Disposition` properly and encode filenames safely; avoid using upload original filenames as save paths.
- For user-uploaded files, consider `X-Content-Type-Options: nosniff` and safe served content types so browsers do not execute dangerous content.
- Resources need stable `contentLength` and stable bytes while streaming. If a file changes size between Range calculation and reading, `Content-Range` can become wrong.

For object storage or CDNs with native byte-range support, let the backend/storage serve Ranges directly instead of downloading the whole object into Java and skipping bytes; this is critical for multi-GB files.

## 12. Content-Encoding, Caching, and Proxies

Range offsets apply to **selected representation bytes**. A 1000-byte file might gzip down to 400 bytes; `Range: bytes=0-99` of the gzipped representation cannot be arbitrarily spliced with bytes 0–99 of the uncompressed file.

Compression layers, filters, or CDNs can transform responses and invalidate headers:

- `Content-Range` and `Content-Length` if bytes change.
- `ETag` if the validator no longer identifies the same byte representation.
- `Vary: Accept-Encoding` and `Cache-Control` when proxies cache variants.
- `Content-Type` / `Content-Disposition` / `Accept-Ranges` if a product switches between download and inline views.

For reliable streaming, resume, and video seeking, avoid uncontrolled automatic content-coding transformations on range endpoints, or keep all offsets, validators, and cache keys consistent. Test both directly against the origin and through the proxy/CDN, not just local MockMvc.

## 13. HEAD, Media Players, and Resuming Downloads

**HEAD** returns the same metadata as GET without a response body. It helps clients discover total size, validators, and `Accept-Ranges`. However, ensure `HEAD` truly sends zero body bytes; verify framework, controller, and proxy behavior explicitly.

**Video players** can use Range requests for seeking. Yet HTTP 206 alone does not make a video seekable: the container format, index, and codec must also support it. Likewise, PDF viewers only fetch ranges efficiently when the PDF structure supports progressive access.

**Resume clients:** upon receiving 206 with matching `Content-Range` offset/version, append bytes. If the server returns **200**, treat it as a full representation (replace the temp file instead of appending). Upon 416, inspect total size, validators, and already-downloaded bytes to decide whether the download is complete or must restart; never retry 416 in an infinite loop.

## 14. Performance and Mitigating Range Abuse

- Clients can request hundreds of tiny ranges, causing heavy disk seeks/reads and multipart overhead. Limit range counts, total byte counts, header sizes, timeouts, and request rates where appropriate.
- If the server reads an entire file into `byte[]` just to return one slice, most range benefits are lost. For large files use seekable sources or native range I/O.
- `InputStream.skip()` on some sources may actually read and discard skipped bytes; having a `skip` API does not equate to efficient random access.
- When clients send overlapping or adjacent ranges, servers may coalesce them per the RFC to reduce overhead.
- Every Range request must still pass resource authorization and policies just like a full GET; never leak data simply because only a slice was requested.
- Privately owned files need appropriate `Cache-Control` so shared caches never leak data across users.
- Avoid logging file bodies, range bytes, or access tokens for debugging.

## 15. Common Errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `Range` sent but response is always 200 | Body is not a suitable `Resource`, used `InputStreamResource`, initial status not 200, proxy stripped `Range` | Check `Resource` class, return type, and original HTTP status |
| `206` returned with the entire file | Controller hardcoded status 206 without slicing body | Let Spring auto-range from 200 or use `ResourceRegion` properly |
| `Content-Range` missing or inconsistent | Manually set wrong header or another converter wrote the body | Assert status, bytes, and total length |
| Off-by-one when slicing | Confused `count` with last position | `count = last - first + 1` |
| `416` when starting at total size | Request has `first >= totalLength` | Check `bytes */total` |
| Resumed file is corrupted | Slices came from different file versions | Strong validators and `If-Range` / versioned objects |
| `multipart/byteranges` parsed incorrectly | Treated as `multipart/form-data` or read top-level `Content-Range` | Parse boundary and per-part headers |
| Downloads consume high RAM | Used `Files.readAllBytes` on large files | Use `FileSystemResource`/`PathResource` or native ranged reads |
| Browser fails to seek video | Bad media index, proxy compression, or wrong headers | Inspect media file and range responses end-to-end |
| `Content-Length` too large in 206 | Set to whole file size instead of partial body | Let converter compute partial length |
| MockMvc passes, production fails | Proxy/CDN/HTTP coding/streaming differences | Run end-to-end integration tests |
| Unauthorized file download | Path ID not checked against principal/resource | Enforce authentication, authorization, and storage keys |
| Old/new file chunks mixed | File mutated while being read | Immutable versions/snapshots and `ETag` |
| CPU spikes from hundreds of ranges | Missing range count/size policy | Enforce parser and infrastructure limits |

Quick diagnosis:

1. Inspect status, `Range` request header, `Accept-Ranges`, `Content-Range`, `Content-Length`, and `Content-Type`.
2. Compare current total size and byte offsets against the **selected representation**.
3. Verify the `Resource` has a repeatable stream and accurate `contentLength`.
4. For a single range, compare `last - first + 1` with response bytes.
5. For multiple ranges, check each part's `Content-Range` and dynamic boundary.
6. Compare origin vs proxy responses to isolate compression/caching issues.
7. Check file version/`ETag`/`If-Range` during resume flows.
8. Verify authorization, byte limits, and resource-exhaustion safeguards.

## 16. Self-Check Exercises

1. For a 10-byte resource, what `ResourceRegion.position`, `count`, and body does `bytes=2-5` produce?
2. Why are `bytes=-3` and `bytes=3-` not equivalent?
3. How many bytes are in `Content-Range: bytes 7-9/10`?
4. If you return `ResponseEntity.status(PARTIAL_CONTENT).body(resource)`, does Spring automatically slice the `Resource`?
5. Why is `InputStreamResource` unsuitable for auto-range?
6. What `Content-Range` format can 416 use?
7. May a top-level `Content-Range` be set on a multi-part `multipart/byteranges` response?
8. Why are `If-Range` and strong ETags needed when resuming mutable files?
9. Why do MockMvc tests not replace proxy integration tests?
10. Why does `Content-Encoding` affect byte offsets?
11. May a GET with `Range` bypass access-control checks?
12. On 416, should a client append the error body to its temp file?

**Hints:** (1) Position=2, count=4, `CDEF`. (2) Suffix takes the last 3 bytes; open-ended starts at offset 3. (3) 3 bytes. (4) No; auto-range requires initial status 200 and a suitable `Resource`. (5) One-shot stream cannot reliably report length or be reopened. (6) `bytes */total`. (7) No; each part carries its own `Content-Range`. (8) Avoids splicing bytes from different versions. (9) Compression/cache/container behavior differs from MockMvc. (10) Ranges count encoded representation bytes. (11) No. (12) No; inspect total size and validators.

## 17. References

- [RFC 9110 — Range Requests, Content-Range, 206, and 416](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Spring Framework — Range Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html)
- [Spring Framework 6.1 — HttpRange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/HttpRange.html)
- [Spring Framework 6.1 — ResourceRegionHttpMessageConverter](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/converter/ResourceRegionHttpMessageConverter.html)
- [Spring Framework 6.1 — ResourceRegion Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/support/ResourceRegion.html)
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring MVC 6.1 source — AbstractMessageConverterMethodProcessor](https://github.com/spring-projects/spring-framework/blob/v6.1.14/spring-webmvc/src/main/java/org/springframework/web/servlet/mvc/method/annotation/AbstractMessageConverterMethodProcessor.java)
- [MDN — Range requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)

**Summary:** Clients use `Range` to request byte offsets of a representation. Spring MVC can automatically return `206` and `Content-Range` when a controller returns `Resource`/`ResponseEntity<Resource>` with initial status 200 (except `InputStreamResource`). `HttpRange` models client-requested ranges, `ResourceRegion` holds position/count slices, and `ResourceRegionHttpMessageConverter` writes single/multipart bytes. Production systems must also address authorization, validators, caching, compression, version consistency, and request limits.
