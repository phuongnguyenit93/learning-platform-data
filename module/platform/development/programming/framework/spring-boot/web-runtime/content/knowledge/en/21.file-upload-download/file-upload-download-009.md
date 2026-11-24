# Returning Files with Resource, Content-Disposition, and Proper Content Types in Spring Boot

## 1. Objectives and Expected Outcomes

When a user clicks **Download Report**, **Export CSV**, **Download PDF**, or **Preview a File**, the server must return the **exact file bytes** while telling the browser/client how to handle the response. With **Spring Boot + Spring MVC**, the standard, clean approach is returning `ResponseEntity<Resource>`, setting `Content-Type`, `Content-Disposition`, and related headers under a server-controlled policy.

After this lesson, you will be able to:

1. Choose the appropriate `Resource` for classpath, filesystem, byte arrays, and streams without needlessly loading huge files into RAM.
2. Use `ResponseEntity<Resource>` to control HTTP status, headers, and response body.
3. Distinguish `Content-Type` (data format) from `Content-Disposition` (hinting display vs. download) and set UTF-8 filenames safely.
4. Use `Content-Length` accurately when size is known without breaking streams; understand caching, MIME sniffing, and range requests.
5. Design download APIs around **valid IDs + authorization checks** instead of client-supplied raw paths; prevent path traversal, file leaks, header injection, and wrong MIME types.
6. Run a Java 17+ Spring Boot application and test HTTP headers, status codes, and file bytes.

**Principle:** a proper file response is not just a body with bytes; it requires **correct content, correct MIME, safe download filename, verified access permissions, and proper browser handling**.

## 2. What Components Make Up a File Download HTTP Response?

Example report download response:

```http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=UTF-8
Content-Disposition: attachment; filename="bao-cao.csv"
Content-Length: 24
Cache-Control: no-store
X-Content-Type-Options: nosniff

id,name
1,An
2,Binh
```

**This is solely a protocol illustration**, not a byte-for-byte capture from the Java example: `Content-Length: 24`, data lines, header count, header order, and line endings in a real response must match the actual file size and server configuration. Never hard-code an illustrative `Content-Length` into code.

Role of each component:

| Component | Role | Notes |
| --- | --- | --- |
| `200 OK` | Request succeeded, server returns body | Missing files typically return 404; unauthorized may return 403 or 404 per policy |
| `Content-Type` | Describes media type of returned bytes, e.g., `application/pdf` | Never infer MIME purely from a user-supplied filename |
| `Content-Disposition` | `attachment` suggests saving; `inline` suggests displaying in browser if supported | Does not replace MIME checks and content security |
| `filename`/`filename*` | Suggested filename when saving on the client | Must not contain paths, control characters, or unvalidated input |
| `Content-Length` | Body size in **bytes**, not character count | Set only when known accurately without consuming a one-shot stream |
| `Cache-Control` | Controls response caching | Sensitive private documents typically use `no-store` |
| `X-Content-Type-Options: nosniff` | Tells browser to curb MIME sniffing in certain contexts | Cannot sanitize malicious payloads or fix wrong MIME types |

If a client runs `curl -i`, headers and body appear together in the terminal. For binary files like PDF, ZIP, or XLSX, avoid printing raw bytes to the terminal; use `curl -o result.pdf ...` to save the file.

### 2.1. `Content-Type` Is Not the Filename

A `report.pdf` file should be served as `application/pdf` once the server has verified it is a valid PDF. Serving PDF bytes with `Content-Type: text/html` or `text/plain` makes browsers mishandle them. Conversely, naming an HTML file `report.pdf` does not turn it into a PDF.

Pick the content type from **server-managed verified metadata**, and verify actual format on untrusted uploads when needed. Extensions are only hints; users can easily misname files.

### 2.2. `Content-Disposition` Is Not `Content-Type`

Two responses with identical PDF bytes can serve different intents:

```http
Content-Type: application/pdf
Content-Disposition: inline; filename="guide.pdf"
```

`inline` indicates content **may** be displayed inside the browser (if the browser/plugin and other headers allow). For downloads:

```http
Content-Type: application/pdf
Content-Disposition: attachment; filename="guide.pdf"
```

`attachment` hints that the browser should download it. It is not a guarantee every client shows the exact same save dialog; native apps, browsers, download managers, and `<a download>` attributes can behave differently. For HTML/SVG or untrusted user content, **do not enable inline merely because the client asks for it**: that poses XSS/active-content risks, especially on the same origin as the main app.

## 3. What Is `Resource` and Which Implementation Should You Pick?

`org.springframework.core.io.Resource` is Spring's abstraction for a readable resource. It exposes methods like `exists()`, `isReadable()`, `getInputStream()`, `contentLength()`, `getFilename()`, `getURL()`, and file helpers. It **does not imply** every resource is a `java.io.File` on disk.

| Implementation | Best When | Caveats |
| --- | --- | --- |
| `ClassPathResource` | Files bundled with the app, e.g., `src/main/resources/downloads/guide.txt` | May live inside a JAR; **do not assume `getFile()` works universally** |
| `FileSystemResource` / `PathResource` | Files on a server-controlled filesystem | Requires root policy, authorization, OS permissions, path-traversal/symlink guards |
| `ByteArrayResource` | Small payloads built in RAM, e.g., a few CSV lines | Byte array sits in memory; unsuitable for very large files |
| `InputStreamResource` | One-shot stream when no better resource type fits | Use cautiously; calling `contentLength()` can drain the stream; not repeatable by default |
| `UrlResource` | Specific server-trusted file/URL source | Never pass arbitrary user `https://...` URLs: SSRF and internal-network redirect risks |

Spring MVC uses `ResourceHttpMessageConverter` to stream `Resource` contents into the HTTP response where appropriate. The advantage of `ResponseEntity<Resource>` over `Files.readAllBytes(...)` is avoiding allocating an application `byte[]` holding the entire file in heap before responding (though actual I/O and buffering still depend on the resource/converter/container).

### 3.1. Do Not Confuse `ClassPathResource` with Filesystem Paths

`src/main/resources/downloads/guide.txt` becomes a classpath resource after building (e.g., under `BOOT-INF/classes/downloads/guide.txt` inside a Spring Boot executable JAR). Load it with:

```java
Resource resource = new ClassPathResource("downloads/guide.txt");
```

Do not rely on:

```java
// Not guaranteed to work when the resource is packaged inside an executable JAR.
File file = resource.getFile();
```

`ClassPathResource` can still provide an input stream even when no standalone `File` path exists. That is why returning `Resource` and letting Spring copy the stream is the right pattern.

### 3.2. `InputStreamResource`: Avoid Computing Length on One-Shot Streams

Common pitfall:

```java
// Bug illustration: inputStream may only be readable once.
InputStreamResource body = new InputStreamResource(inputStream);
long size = body.contentLength(); // risks draining the entire stream!
```

Never call `contentLength()` on a single-use stream just to populate `Content-Length`; doing so can consume the bytes needed for the response body. If the source has reliable size metadata, use that metadata; if unknown, **omit Content-Length** and let the container pick HTTP framing. For small in-memory payloads, `ByteArrayResource` may fit better. For streamed generation, `StreamingResponseBody` is another Spring MVC option, requiring awareness of executors, stream lifecycles, and post-commit error handling.

## 4. `Content-Disposition` and Unicode Filenames

Spring provides `org.springframework.http.ContentDisposition` with `attachment()` and `inline()` builders. Example:

```java
ContentDisposition disposition = ContentDisposition.attachment()
    .filename("Spring Boot Guide.txt", StandardCharsets.UTF_8)
    .build();
```

The generated header follows UTF-8 compatible encoding, including the `filename*` parameter per RFC 5987/RFC 6266 in compatible Spring Framework versions. **Never concatenate header strings manually using user-supplied filenames**, such as:

```java
// ANTI-PATTERN: can cause malformed filenames/paths or header injection.
String header = "attachment; filename=\"" + userFilename + "\"";
```

For accented or non-ASCII names:

- `filename="..."` serves as a compatibility fallback for older clients.
- `filename*=UTF-8''...` carries the RFC 5987 percent-encoded name for modern clients.
- Spring `ContentDisposition` handles escaping/encoding; you must still pick a **valid, server-controlled name free of paths or control characters**.
- Download clients vary in `filename*` support; stick to simple ASCII names if legacy client compatibility is essential, and test target browsers/curl.

Never treat filename as a server storage path or guaranteed client destination. In HTTP, it is only a **filename hint**. Clients must handle `/`, `\`, and special names safely; servers must also avoid emitting separators or illegal characters.

In the sample project below, the URL ID selects an **existing metadata record**; the download name comes from the server, never directly from request input.

## 5. Choosing the Right `Content-Type` by Format

Common examples:

| File Type | Appropriate `Content-Type` | Common Disposition |
| --- | --- | --- |
| UTF-8 plain text | `text/plain; charset=UTF-8` | `attachment` to download, `inline` when intentionally viewing text |
| UTF-8 CSV | `text/csv; charset=UTF-8` | Usually `attachment` |
| PDF | `application/pdf` | `inline` when intentionally viewing trusted content; `attachment` to download |
| PNG | `image/png` | `inline` in UI or `attachment` to download |
| JPEG | `image/jpeg` | `inline` or `attachment` |
| ZIP | `application/zip` | Usually `attachment` |
| Excel XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Usually `attachment` |
| Unverified / generic binary | `application/octet-stream` | Usually `attachment` |

These are example media types, not an exhaustive classifier. When files originate from users, **never trust `MultipartFile.getContentType()`** or extensions in `getOriginalFilename()` alone. When security demands it, verify actual content, restrict formats, and apply virus/malware scanning appropriate to the environment.

For sensitive content:

- Use `Content-Disposition: attachment` when preview is unnecessary.
- Consider `X-Content-Type-Options: nosniff` and related security headers.
- Never let users request an arbitrary MIME type via a query parameter.
- CSV files exported from user-entered values can trigger **CSV/formula injection** in spreadsheet apps if a cell begins with `=`, `+`, `-`, or `@`. `Content-Type` and `attachment` **do not mitigate this risk**; sanitize exported cell values per target consumers.
- Never serve user-uploaded HTML/SVG inline on an origin holding session cookies without proper isolation/sanitization.

## 6. Runnable Spring Boot Application Example

This example uses **Java 17+**, **Spring Boot 3.x**, **Spring MVC** with `spring-boot-starter-web`, and default embedded Tomcat. Only two files are permitted for download via IDs `intro` and `table`. Other files on the classpath **do not automatically get download endpoints**.

### 6.1. File Structure

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ DownloadApplication.java
│  │  └─ DownloadController.java
│  └─ resources/
│     ├─ downloads/
│     │  ├─ intro.txt
│     │  └─ table.csv
│     └─ application.properties
└─ test/
   └─ java/com/example/demo/
      └─ DownloadControllerTest.java
```

Primary dependency is `org.springframework.boot:spring-boot-starter-web`; tests use `spring-boot-starter-test`. Create the project via Spring Initializr with Java 17+ and those dependencies. Sample files live under `resources/downloads/` (outside default static roots like `static/` or `public/`).

### 6.2. Main Class

**`src/main/java/com/example/demo/DownloadApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DownloadApplication {
    public static void main(String[] args) {
        SpringApplication.run(DownloadApplication.class, args);
    }
}
```

### 6.3. Controller Returning Resource + Headers

**`src/main/java/com/example/demo/DownloadController.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DownloadController {

    // Server-controlled allowlist of files and metadata, never using URL paths.
    private static final Map<String, FileSpec> FILES = Map.of(
        "intro",
        new FileSpec(
            "downloads/intro.txt",
            "Hướng dẫn Spring Boot.txt",
            MediaType.parseMediaType("text/plain;charset=UTF-8")
        ),
        "table",
        new FileSpec(
            "downloads/table.csv",
            "bao-cao.csv",
            MediaType.parseMediaType("text/csv;charset=UTF-8")
        )
    );

    @GetMapping("/downloads/{id}")
    public ResponseEntity<Resource> download(@PathVariable String id)
            throws IOException {
        return respond(id, false);
    }

    // Allows previewing only a fixed server-chosen text file.
    @GetMapping("/previews/intro")
    public ResponseEntity<Resource> previewIntro() throws IOException {
        return respond("intro", true);
    }

    private ResponseEntity<Resource> respond(String id, boolean preview)
            throws IOException {
        FileSpec spec = FILES.get(id);
        if (spec == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Download not found"
            );
        }

        Resource resource = new ClassPathResource(spec.path());
        if (!resource.exists() || !resource.isReadable()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Resource not available"
            );
        }

        ContentDisposition disposition = preview
            ? ContentDisposition.inline()
                .filename(spec.downloadName(), StandardCharsets.UTF_8)
                .build()
            : ContentDisposition.attachment()
                .filename(spec.downloadName(), StandardCharsets.UTF_8)
                .build();

        return ResponseEntity.ok()
            .contentType(spec.contentType())
            .contentLength(resource.contentLength())
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .header("X-Content-Type-Options", "nosniff")
            .cacheControl(CacheControl.noStore())
            .body(resource);
    }

    private record FileSpec(
        String path,
        String downloadName,
        MediaType contentType
    ) {}
}
```

**`src/main/resources/downloads/intro.txt`** (saved as UTF-8, ending with **one LF newline**):

```text
Hello Spring Boot!
```

**`src/main/resources/downloads/table.csv`** (UTF-8, LF):

```csv
id,name
1,An
2,Binh
```

**`src/main/resources/application.properties`**

```properties
server.port=8080
```

**Detailed explanation of each choice:**

1. **`Map<String, FileSpec>`** acts as an allowlist. The client supplies a logical ID `intro` or `table`, **never a file path, filename, or MIME type**.
2. **`ClassPathResource`** reads resources packaged inside the app even when running from an executable JAR. The controller does not need a `java.io.File`.
3. **`exists()` / `isReadable()`** verify the resource can be served; if missing, the demo returns 404. In production, missing required build assets should trigger internal logs/alerts rather than silently returning not found.
4. **`ContentDisposition.attachment()`** applies to downloads; `/previews/intro` applies `inline()` solely to a trusted server-chosen text file. Never expose a client-controlled `inline` boolean for arbitrary files.
5. **`filename(name, UTF_8)`** produces standards-compliant Unicode headers better than string concatenation. The filename metadata never comes from raw HTTP input.
6. **`contentType(spec.contentType())`** assigns the exact MIME type per file. `text/plain;charset=UTF-8` and `text/csv;charset=UTF-8` are valid media types.
7. **`contentLength(resource.contentLength())`** works here because `ClassPathResource` can reopen streams for small fixed assets. For one-shot streams or large/remote files, **never force the server to read the entire file just to compute length**.
8. **`CacheControl.noStore()`** instructs browsers/proxies not to store the file. This is a conservative default for potentially sensitive documents; public files may use different caching policies for performance.
9. **`nosniff`** restricts browsers from MIME-sniffing. It does not make malicious bytes harmless.
10. **`ResponseEntity<Resource>`** is handled by Spring MVC's HTTP message converter. Never return a path string as the body, and do not wrap unnecessarily in `InputStreamResource`.

**Note on HEAD and byte-range:** HTTP HEAD and `Range` requests have specific behavior depending on resource type, converter, and container. For large file/video resume support, test `206 Partial Content`, `416 Range Not Satisfiable`, `Accept-Ranges`, and `If-Range` explicitly, or rely on static resource handlers/object storage that already support them. Never manually add `Accept-Ranges: bytes` unless the implementation truly serves valid partial content. The demo primarily tests full GET downloads.

## 7. Running and Inspecting HTTP Responses

From the Maven Wrapper project directory:

```bash
java -version
./mvnw spring-boot:run
```

On Windows, use `mvnw.cmd spring-boot:run`. In another terminal:

```bash
curl -i http://localhost:8080/downloads/intro
curl -i http://localhost:8080/downloads/table
curl -i http://localhost:8080/previews/intro
curl -i http://localhost:8080/downloads/unknown
```

Expected:

| URL | Status | MIME | Disposition |
| --- | --- | --- | --- |
| `/downloads/intro` | 200 | `text/plain; charset=UTF-8` | `attachment`; suggested name `Hướng dẫn Spring Boot.txt` |
| `/downloads/table` | 200 | `text/csv; charset=UTF-8` | `attachment`; name `bao-cao.csv` |
| `/previews/intro` | 200 | `text/plain; charset=UTF-8` | `inline` |
| `/downloads/unknown` | 404 | Spring-generated error body; JSON/HTML depending on request and config | No valid file download |

For `/downloads/intro`, the body bytes after headers match `intro.txt` identically:

```text
Hello Spring Boot!
```

The actual content has an LF newline after `!`. The `Content-Disposition` header may contain a fallback `filename=...` and `filename*=UTF-8''...`; **do not assume exact header order, casing, or extra bytes beyond the contract under test**. File hashes and `Content-Length` depend on actual bytes; length is the **UTF-8 byte count**, not Java `String.length()`.

Save the files separately with curl:

```bash
curl -fL -o downloaded.txt http://localhost:8080/downloads/intro
curl -fL -o report.csv http://localhost:8080/downloads/table
```

`-f` fails on many 4xx/5xx responses; `-L` follows redirects. For untrusted URLs, review redirect policies carefully. `-o` picks the **client-side** output name independent of header filenames. If using `curl -OJ` to adopt the server's suggested filename, note that curl versions vary in `filename*` support; do not mistake client behavior for server UTF-8 bugs.

Open `http://localhost:8080/previews/intro` in a browser to see the difference between downloading (`attachment`) and inline text display (`inline`). When previewing PDF/HTML or untrusted content, enforce stricter security policies; never generalize from a text example to enable inline arbitrarily.

## 8. Automated Testing with Spring Boot + MockMvc

Add `spring-boot-starter-test` in test scope. Create:

**`src/test/java/com/example/demo/DownloadControllerTest.java`**

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DownloadControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsTextFileWithExpectedBytes() throws Exception {
        byte[] expected = "Hello Spring Boot!\n"
            .getBytes(StandardCharsets.UTF_8);

        mvc.perform(get("/downloads/intro"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN
            ))
            .andExpect(content().bytes(expected))
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                startsWith("attachment;")
            ))
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                containsString("filename*=")
            ))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"
            ));
    }

    @Test
    void csvUsesCsvMediaTypeAndAttachment() throws Exception {
        mvc.perform(get("/downloads/table"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CONTENT_TYPE, startsWith("text/csv")
            ))
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                startsWith("attachment;")
            ));
    }

    @Test
    void onlyExplicitPreviewIsInline() throws Exception {
        mvc.perform(get("/previews/intro"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CONTENT_DISPOSITION,
                startsWith("inline;")
            ));
    }

    @Test
    void unknownFileIdIsNotExposed() throws Exception {
        mvc.perform(get("/downloads/secret"))
            .andExpect(status().isNotFound());
    }

    @Test
    void contentLengthMatchesReturnedUtf8Bytes() throws Exception {
        byte[] expected = "Hello Spring Boot!\n"
            .getBytes(StandardCharsets.UTF_8);

        mvc.perform(get("/downloads/intro"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CONTENT_LENGTH,
                String.valueOf(expected.length)
            ));
    }
}
```

Run tests:

```bash
./mvnw test
```

With the right project, Spring Boot 3.x version, and UTF-8 file **ending with one LF** as described, the five tests are **expected to pass**. That is the expected verification outcome for learners, **not a report from running tests in a specific repository**.

If byte assertions fail on Windows, check whether your editor converted line endings to **CRLF** (`\r\n`). That changes the file's bytes relative to the `"\n"` literal in the test without being a controller bug. Keep test byte fixtures explicit so they do not depend on editor settings.

What the tests prove: a registered ID returns the file with MIME/attachment/nosniff and exact bytes, while IDs outside the allowlist are unreachable. Production also needs tests for **authentication/authorization**, versioning, paths outside allowed directories, real PDF/ZIP content types, large files, HEAD/Range requests, cache headers, header injection, and error handling.

## 9. Large Files, Streaming, and Resumable Downloads

### 9.1. Avoid `byte[]` When Unnecessary

Pattern that puts heavy pressure on memory for large files:

```java
// Illustrative snippet; path is an already-authorized internal Path.
byte[] bytes = Files.readAllBytes(path);
return ResponseEntity.ok().body(bytes);
```

With hundreds of concurrent downloads of multi-hundred-MB files, holding full byte arrays in heap spikes RAM and GC. Prefer file/path-based Resources when appropriate so Spring streams bytes out.

`ByteArrayResource` remains reasonable for **small, in-RAM generated payloads**, such as a few-KB invoice:

```java
byte[] data = "id,amount\n1,100\n"
    .getBytes(StandardCharsets.UTF_8);

Resource resource = new ByteArrayResource(data);
return ResponseEntity.ok()
    .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
    .contentLength(data.length)
    .header(HttpHeaders.CONTENT_DISPOSITION,
        ContentDisposition.attachment()
            .filename("hoa-don.csv", StandardCharsets.UTF_8)
            .build().toString())
    .body(resource);
```

This is an illustrative snippet inside an appropriate Spring MVC method (requiring imports for Resource, ByteArrayResource, ResponseEntity, ContentDisposition, HttpHeaders, MediaType, and StandardCharsets); not a standalone Java program. Because `ByteArrayResource` backs its stream with a byte array, length calculation is trivial and repeatable.

### 9.2. Data Generated as a Stream

When content is exported incrementally from a database or external system, consider `StreamingResponseBody` in **Spring MVC**:

```java
// Illustrative snippet inside an MVC controller, not a complete endpoint.
StreamingResponseBody stream = outputStream -> {
    exportService.writeCsv(outputStream);
};
return ResponseEntity.ok()
    .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
    .header(HttpHeaders.CONTENT_DISPOSITION,
        ContentDisposition.attachment()
            .filename("export.csv", StandardCharsets.UTF_8)
            .build().toString())
    .body(stream);
```

`exportService` is application-defined; this code needs `StreamingResponseBody`, Spring MVC async executor configuration, and proper stream open/close handling. Distinguish:

- **Resource** represents a readable source, typically suited to existing files.
- **StreamingResponseBody** runs a callback writing to `OutputStream` while sending the response, suited to large/incrementally generated exports.
- If an exception occurs **after HTTP headers/body are committed**, status 200 cannot be changed to 500. Design logging/metrics, error bounds, and cleanup accordingly.
- Always enforce timeouts, max concurrent streams, memory caps, and idle limits. Clients disconnecting mid-stream are normal and must be handled cleanly.

### 9.3. Range Requests, Conditional GET, and Caching

For video, audio, large PDFs, or resumable downloads, clients can send:

```http
Range: bytes=0-1023
```

A server properly supporting byte ranges returns `206 Partial Content` with `Content-Range`, or `416` for unsatisfiable ranges. **Never assume Range works just because an endpoint returns `Resource`** without testing the converter, resource type, and container. Spring MVC supports range handling for suitable resources; for plain static files, `ResourceHttpRequestHandler` and static resource infrastructure are often more convenient. CDNs/object storage can also offload large downloads, provided signed URLs, access control, and expiration are enforced for private data.

Caching:

- `Cache-Control: no-store`: private, sensitive documents that must not be saved by browsers or proxies.
- `Cache-Control: private`: response intended for a single client; **not synonymous with no-store**.
- `Cache-Control: public, max-age=...`: only when the file is genuinely public with an intentional cache TTL.
- `ETag` / `Last-Modified` with `If-None-Match` / `If-Modified-Since` enable `304 Not Modified` when unchanged. ETags must reflect the actual version/bytes of the resource, never unmaintained dummy values.
- When filenames, permissions, or contents vary by user, avoid shared caches or stable unauthenticated URLs that could leak data.

## 10. Security: Paths, Permissions, Filenames, and MIME

### 10.1. Never Concatenate Raw Input into a File Path

Anti-pattern:

```java
// UNSAFE EXAMPLE, never use for downloads.
@GetMapping("/download")
public ResponseEntity<Resource> download(@RequestParam String path) {
    Resource r = new FileSystemResource("/srv/private/" + path);
    return ResponseEntity.ok().body(r);
}
```

This snippet merely illustrates the hazard, not a standalone program. Attackers can supply `../`, encoded sequences, absolute paths, or symlinks to read files outside the intended directory. **Switching to `Resource` does not automatically block path traversal.** You must still control **which resource** is constructed.

Safer approach:

1. Client sends a **document ID**, never any path.
2. Server verifies the current user is authorized to download that document.
3. Server fetches internal metadata: storage key/path, display name, verified MIME, size, and owner/tenant.
4. Storage root is trusted configuration; confirm the canonical path stays inside the root, disallow symlinks escaping the root, and block untrusted writers under the root.
5. Server returns the file via `Resource` with headers built from approved metadata.
6. Missing files return 404; unauthorized files follow your 403/404 policy without leaking internal names or paths.
7. Never expose stack traces, absolute paths, or secrets in error payloads.

For existing filesystem files, a `Path`-based containment check:

```java
// Service snippet, after verifying authorization via document ID.
Path root = Path.of("/srv/app/approved-downloads").toRealPath();
Path file = root.resolve(serverControlledRelativePath).toRealPath();

if (!file.startsWith(root) || !Files.isRegularFile(file)) {
    throw new SecurityException("Outside approved storage");
}
```

`serverControlledRelativePath` must originate from server-side metadata, never from a raw query string. `Path.startsWith(Path)` compares by **path segments**, unlike `String.startsWith` which can confuse `approved-downloads` with `approved-downloads-backup`. `toRealPath()` resolves symlinks on existing paths. **This check alone does not prevent races between check and open (TOCTOU)** if untrusted actors can alter the directory tree; design OS permissions and safe opens per your threat model.

### 10.2. Bound Response Filenames

`ContentDisposition.attachment().filename(..., UTF_8)` encodes headers properly, yet you must still avoid raw client strings containing paths, newlines, control characters, or reserved device names. Best practices:

- Use a server-determined display name, **never the internal storage path as the download name**.
- Strip directory components, cap length, restrict characters, or apply a domain-valid name set.
- Consider an ASCII fallback if legacy clients demand it; test Unicode filenames across supported browsers.
- Never let extensions mislead recipients: a `.pdf` filename carrying HTML/JS or an executable causes dangerous parsing/downloads. Control both MIME and download name.
- Guard against *reflected file download (RFD)* when echoing request parameters into downloadable content or filenames.

### 10.3. Do Not Trust Upload `Content-Type` or Download `Accept`

When allowing users to upload PDFs and download them later:

- Never rely solely on `upload.getContentType()` to assume a file is a valid PDF.
- Never accept `?type=text/html` and copy it into the response `Content-Type`.
- Use the service-stored and verified media type, or fall back to `application/octet-stream` when type is uncertain.
- For untrusted HTML/SVG/scripts, prefer attachment download and consider isolated origins; never enable inline at a user's whim.
- Keep `nosniff` and security headers active; never treat them as a substitute for content validation.

### 10.4. Access Control Does Not Live in Content-Disposition

`Content-Disposition: attachment` only tells browsers how to handle the response; **it does not check who may access the file**. For private documents, enforce authentication/authorization **before** building the response or opening the stream. Check owner/tenant on **every request**; never rely on “hard-to-guess” IDs.

For signed download URLs: limit expiration, object scope, HTTP method, and replayability per system needs; never issue indefinite public URLs for sensitive data. For private content, prevent shared caching or public CDN routing without proper controls.

## 11. Common Mistakes and Remedies

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| API returns filename/path as JSON or text instead of file bytes | Controller returns `String` or descriptor object rather than `Resource` body | Return `ResponseEntity<Resource>` and verify response body |
| Browser displays PDF instead of downloading | `inline` or missing `attachment` | Use `ContentDisposition.attachment()` when download is required |
| Garbled Unicode filenames | Manual `filename=...` concatenation or unsupported client encoding | Use `filename(name, UTF_8)` and test target clients |
| Download has wrong extension and fails to open | Mismatched MIME/name vs. bytes | Maintain accurate verified metadata and validate file types |
| Classpath file works in IDE, fails in executable JAR | Called `resource.getFile()` instead of streaming | Use `ClassPathResource` + `ResponseEntity<Resource>` |
| Downloaded file is empty/truncated | Stream drained when computing length, or one-shot stream reused | Never call `contentLength()` on single-use `InputStreamResource` |
| RAM spikes on concurrent large downloads | `Files.readAllBytes`/`ByteArrayResource` used for huge files | Use file-based Resource or streaming |
| Clients can download files outside allowed directory | Passed client path directly into `FileSystemResource` | Use document ID, root containment, and authorization checks |
| `Content-Length` header mismatches | Counted characters instead of bytes, or file changed mid-read | Measure actual bytes, snapshot file, or omit length when unknown |
| Client sends Range yet server returns full file | Endpoint/Resource/converter lacks partial-content support | Test Range; use static resource handler or CDN where suitable |
| File cached for the wrong user | Wrong cache headers/scope | Use `no-store`/`private` and align authorization with caching |
| Fails only on Vietnamese accented filenames | Legacy client lacks `filename*` support | Check RFC 5987 support and provide ASCII fallback if needed |

## 12. Production Download API Design Checklist

- [ ] Documents are selected by **logical ID**, never by filesystem path from the request.
- [ ] Server authenticates user/tenant and authorizes every document ID before reading.
- [ ] Storage root/Resource type is server-controlled with traversal and symlink defenses.
- [ ] Filenames are server-chosen or sanitized; free of paths, CR/LF, and control characters.
- [ ] `Content-Disposition` uses `attachment`/`inline` by policy, not free-form input; Unicode names properly encoded.
- [ ] `Content-Type` matches verified format; unknown files use `application/octet-stream`.
- [ ] `Content-Length` is sent only when accurate and without draining one-shot streams.
- [ ] `X-Content-Type-Options: nosniff` and appropriate security headers are present.
- [ ] Cache policy distinguishes public vs. sensitive files; no cross-user leaks via shared caches.
- [ ] Large files use appropriate Resource/streaming; timeouts, concurrency caps, and disconnect tracking are in place.
- [ ] Tests cover 200 body bytes, MIME, attachment, UTF-8 filenames, 404/403, and invalid paths.
- [ ] Range/HEAD/conditional requests are tested if promised by the product.
- [ ] Audit logs record ID, actor, size, file type, outcome, and errors **without secrets or sensitive paths**.
- [ ] Exported CSV/XLSX data mitigates formula injection when containing user-supplied values.

## 13. Self-Check Questions

**Q1.** Why return `ResponseEntity<Resource>` instead of `byte[]` for large files?  
**Answer:** Spring can stream/copy bytes from the Resource to the response without requiring the entire file in an application heap byte array; actual efficiency still depends on the resource and HTTP stack.

**Q2.** How do `Content-Type` and `Content-Disposition` differ?  
**Answer:** `Content-Type` describes the byte format (PDF, CSV, text); `Content-Disposition` hints to the browser whether to display inline or save as an attachment and suggests a filename.

**Q3.** Can `getFile()` always be called on a classpath file inside a JAR?  
**Answer:** No. Use `ClassPathResource` via streams or the Resource converter whenever possible.

**Q4.** Why is `filename(name, UTF_8)` better than manual header concatenation?  
**Answer:** The builder handles standard Unicode encoding syntax and escaping; you must still supply a server-controlled name.

**Q5.** When a client sends `/download?path=../../secret`, is passing it to `FileSystemResource` safe?  
**Answer:** No. `Resource` enforces no filesystem boundary by itself. Look up files by ID, verify permissions, and enforce canonical containment/OS permissions.

**Q6.** Should you always set `Content-Length` using `resource.contentLength()`?  
**Answer:** No. On single-use streams, measuring length can consume the stream; only set length when known reliably.

**Q7.** Is returning `Content-Disposition: attachment` enough to protect confidential documents?  
**Answer:** No; you still need authentication, authorization, and a proper cache policy.

**Q8.** Does changing an uploaded HTML file's `Content-Type` to `application/pdf` make it a safe PDF?  
**Answer:** No. MIME and filename must reflect verified content rather than masking actual bytes.

**Q9.** Does a download endpoint returning 200 for every `Range` request properly support resume?  
**Answer:** No. Resume requires accurate `206`/`Content-Range`/`416` handling and byte ranges; test explicitly or use components that support it.

## 14. References

- Spring Framework, *ResponseEntity*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework, *Resources*: https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Framework, `ContentDisposition` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ContentDisposition.html
- Spring Framework, *Static Resources*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot, *Servlet Web Applications*: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring, *Uploading Files* (includes `Resource` download example): https://spring.io/guides/gs/uploading-files/
- MDN, *Content-Disposition*: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition
- RFC 6266, *Use of Content-Disposition in HTTP*: https://www.rfc-editor.org/rfc/rfc6266
- OWASP, *Unrestricted File Upload*: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload

**Conclusion:** In Spring MVC, `ResponseEntity<Resource>` is the maintainable choice when returning existing files. Build `Content-Disposition` with Spring's builder, choose `Content-Type` from trusted metadata, set `Content-Length` only when accurate, and protect downloads via IDs + authorization + storage containment. Test **both response headers and body bytes**, not just whether a browser shows a “Download” prompt.
