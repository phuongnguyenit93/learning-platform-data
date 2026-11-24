# HTTP Integration Testing: Uploads, Downloads, and Large Responses in Spring Boot

## 1. Problem to solve

An API can return valid JSON for ordinary requests and still fail when clients **upload files**, **download files**, or receive **large responses**. Failures often lie not in simple business calculations, but at the HTTP boundary: `multipart/form-data` encoding, part names, size limits, the servlet container's parser, bytes corrupted by codecs, `Content-Disposition`, `Content-Length`, `Range` handling, or interrupted streams.

This lesson focuses on **sending real HTTP requests and verifying the full response** in Spring Boot, rather than stopping at mocking a service and asserting Java values.

Three primary scenarios:

1. **Upload:** client sends a binary file via multipart; server reads the exact part, filename, and byte count, returning the expected response/`Location`.
2. **Download:** server returns **byte-for-byte accurate** content, status, media type, and headers; downloading a file is not merely inspecting a DTO with an ID.
3. **Large response:** server writes multiple chunks; the client test **consumes via a stream** without buffering everything into a huge `byte[]` and verifies total byte count, integrity, and completion status.

We will compare `MockMvc` with **real HTTP via `@SpringBootTest(webEnvironment = RANDOM_PORT)`**, then build a Java 17+ / Spring Boot 3.5.x application storing small files in RAM for illustration alongside an endpoint streaming large responses with `StreamingResponseBody`.

### Expected outcomes

- Understand `multipart/form-data`, `MultipartFile`, `MockMultipartFile`, and how to test uploads over real HTTP.
- Recognize `MockMvc`'s limitation: it constructs simulated multipart requests and **does not run the servlet container's real multipart parser**.
- Test HTTP 201, 200, 206, 400, 404, 413, and 415 according to explicit contracts.
- Verify `Location`, `Content-Type`, `Content-Disposition`, `Content-Length`, and when applicable `Content-Range`.
- Verify downloads **byte-for-byte** with `assertArrayEquals`, without converting binary data to `String`.
- Use `StreamingResponseBody` + `HttpClient.BodyHandlers.ofInputStream()` for large responses.
- Understand memory, timeouts, async dispatch, `Range`, security, filename validation, cleanup, and what each test type actually proves.

## 2. Choosing the test level: MockMvc or real HTTP?

| Test level | How it runs | What it tests well | What it does not prove |
| --- | --- | --- | --- |
| Service unit test | Instantiates real service with fake/mock storage | Naming rules, size checks, checksums, saved state | Multipart parser, MVC binding, HTTP headers |
| `@WebMvcTest` + `MockMvc` | Web MVC slice, mock request/response | Mapping, part names, validation, status, controller JSON/headers/bytes | Container multipart limits, real TCP, client encoding |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Broader Boot context, mock servlet request | Controller + real beans in context, no open port | Real container parser, network, proxies, socket streaming |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Embedded HTTP server and client over loopback | Multipart wire format, HTTP headers/status, body and stream over TCP | Production reverse proxy/CDN, cloud storage, edge TLS if unconfigured |
| Integration with real storage/antivirus | HTTP server + test DB / object storage / scan service | Real persistence, streaming, retries, cleanup contracts | Not necessarily equivalent to production load and topology |

**Important:** `MockMvcRequestBuilders.multipart(...)` builds a `MockMultipartHttpServletRequest` with pre-populated parts. It **does not parse raw multipart bytes** the way Tomcat does when receiving a request over TCP. Therefore, a passing MockMvc upload test does not prove that boundaries, the parser, and `spring.servlet.multipart.max-file-size` on the real server are right.

In this hands-on lesson, MockMvc tests quickly verify MVC branches; `RANDOM_PORT` tests verify end-to-end from **JDK `HttpClient` → TCP → embedded server → controller**. The two test layers complement rather than replace each other.

## 3. HTTP multipart: understand the request before testing

`multipart/form-data` splits a request body into multiple *parts*, separated by a `boundary`. Each part has its own headers; part names matter because controllers typically bind `@RequestParam("file")` or `@RequestPart("file")`.

Example structure of a file request:

~~~http
POST /api/files HTTP/1.1
Content-Type: multipart/form-data; boundary=BoundaryTest202

--BoundaryTest202
Content-Disposition: form-data; name="file"; filename="tiny.bin"
Content-Type: application/octet-stream

<bytes of tiny.bin>
--BoundaryTest202--
~~~

The snippet above is a **structural illustration**, not a complete raw request with exact CRLF and `Content-Length`. In a real request, protocol lines must be separated by `\r\n`; payload bytes can include `0x00`, `0x0A`, and `0xFF` and must not be converted to text. Either the client builds the body/boundary or you must construct them to match precisely.

### 3.1 Three Content-Types often confused

- **Overall request:** `multipart/form-data; boundary=...`.
- **File part:** e.g., `application/octet-stream` or `image/png`, supplied by the client and untrusted.
- **Response after upload:** usually `application/json` with ID/metadata; downloads may return `application/octet-stream`.

Do not use `application/json` as the request `Content-Type` when sending a `MultipartFile`; never trust the client-declared MIME type as proof that file contents are safe.

### 3.2 MultipartFile, RequestParam, and RequestPart

Spring MVC supports:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<?> upload(@RequestParam("file") MultipartFile file) {
    // ...
}
~~~

This is an **illustrative controller skeleton**; it needs proper annotations/imports and a method body to be a real file. For a typical file part, `@RequestParam("file")` suffices. `@RequestPart` is useful when binding a JSON part into a DTO via a converter, especially for requests combining **JSON metadata + a file**.

In the Spring Boot servlet stack, multipart configuration is handled by Boot on top of `jakarta.servlet.http.Part` / container support; do not confuse it with WebFlux's `FilePart`, `PartEvent`, or `Flux<DataBuffer>`.

### 3.3 Cases you must test

| Input | What to check |
| --- | --- |
| Valid `file` part with binary bytes | 201/200 per contract, ID, download location, intact bytes |
| Empty file | 400 or explicitly designed status |
| Missing `file` part | 400 (typically missing required argument), no data persisted |
| Wrong request `Content-Type` | 415 if the endpoint only consumes multipart |
| Size exceeding application limit | 413 in the sample contract |
| Size exceeding servlet container limit | Status/exception handling **over real server**, may depend on container |
| Filename containing `../` or backslashes | Safe name without path segments and no writes outside target directory |
| Unclosed multipart boundary / malformed headers | Clear client error, no corrupt records created |
| Duplicate part names or multi-file upload | Contract must explicitly define single file, file list, or rejection |

Spring Boot 3.5 defaults for servlet multipart are **1MB per file**, **10MB per request**, and a disk-threshold of **0B**. These are server multipart initialization settings, not constraints automatically enforced by `MockMultipartFile`.

## 4. Proper downloads must protect bytes and headers

A download is not just `ResponseEntity.ok(file)` returning JSON. For binary content, typically return a `Resource` with response headers:

~~~java
Resource body = new ByteArrayResource(data);
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .contentLength(data.length)
        .header(HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                        .filename("tiny.bin")
                        .build()
                        .toString())
        .body(body);
~~~

This snippet is an **illustration inside a controller** that has `data`, `Resource`, `ByteArrayResource`, and imports. In the complete example in Section 9, the controller returns `ResponseEntity<Resource>`.

Key assertions:

- **Status:** `200 OK` for full resource download, `404` if ID does not exist, `206 Partial Content` for supported valid ranges.
- **Content-Type:** `application/octet-stream` or a safely verified media type.
- **Content-Disposition:** `attachment; filename="tiny.bin"` instructs browsers to download; Unicode filenames require proper encoding and escaping.
- **Content-Length:** actual **byte count** of the body when known upfront. Never use `String.length()` for file byte counts.
- **Content:** compare original `byte[]` with downloaded bytes via `assertArrayEquals`, or checksum combined with byte count for large files.

If the response is PNG/PDF/ZIP, **never call `getContentAsString()` or `new String(bytes)` to compare**, because character decoding can alter or corrupt bytes. Files containing `0x00` are not C-style null-terminated strings.

### Range and resumable downloads

HTTP `Range: bytes=2-4` requests a slice of a resource. When supported, the response is typically:

~~~http
HTTP/1.1 206 Partial Content
Content-Range: bytes 2-4/6
Content-Length: 3
~~~

The three response bytes correspond to indices 2, 3, and 4 of a 6-byte file. Spring MVC has built-in HTTP Range support for `Resource` or `ResponseEntity<Resource>` **provided** the response status is 200 and the `Resource` supports repeated reads; **`InputStreamResource` is unsuitable** for this automatic Range handling.

Do not assume every `StreamingResponseBody` automatically understands `Range`. If a video/media API requires resume, test 206, `Content-Range`, byte boundaries, and 416 for unsatisfiable ranges per contract; use an appropriate `Resource` or dedicated range logic.

## 5. Large responses: "no OOM" is its own contract

Suppose an endpoint returns 5MB of JSON or a 100MB file: if the controller builds `byte[] output = new byte[100_000_000]` before sending, that is **not streaming at the application layer**, even if the socket later splits packets on the wire.

By contrast, `StreamingResponseBody` lets the controller write chunks incrementally to an `OutputStream`:

~~~java
StreamingResponseBody body = output -> {
    byte[] buffer = new byte[8192];
    for (int chunk = 0; chunk < 100; chunk++) {
        output.write(buffer);
    }
    output.flush();
};
~~~

This snippet is an **illustrative pattern**, writing 100 zero-filled chunks totaling `819_200` bytes. In the hands-on code, we write a deterministic pattern `byte[index] = index mod 256` so we can verify **every byte** without holding a large body in RAM.

**`StreamingResponseBody`** in Spring MVC uses asynchronous request processing on an executor; that does not automatically mean WebFlux non-blocking I/O. In production, configure an appropriate `AsyncTaskExecutor`, timeouts, thread pools, and concurrency limits; slow streaming writers can tie up threads and resources for a long time.

### 5.1 Choosing the right HTTP client handler

| Client / API | Consumption behavior | For large files |
| --- | --- | --- |
| JDK `BodyHandlers.ofByteArray()` | Buffers entire response into a `byte[]` | Only use when files have a small bounded limit |
| JDK `BodyHandlers.ofString()` | Decodes bytes as text | Never use for binary downloads |
| JDK `BodyHandlers.ofInputStream()` | Reads incrementally via `InputStream`; must close stream | Ideal for verifying large downloads in chunks |
| JDK `BodyHandlers.ofFile(path)` | Writes response directly to disk | Useful when verifying real file output and disk size |
| MockMvc `content().bytes(...)` | Uses mock response buffer inside JVM | Suitable for small bodies; does not prove TCP streaming |
| WebClient `bodyToMono(byte[].class)` | Aggregates entire body in reactive client | Unsuitable for huge responses; can hit codec buffer limits |

Verify large responses using **total byte count + block-by-block comparison or digest**, never an assertion checking only `200`; a response can be truncated or corrupted mid-stream after sending an initial 200 status.

### 5.2 Content-Length and Transfer-Encoding

- If the server knows the exact size upfront and does not compress/transform it, it can set `Content-Length` to the exact total bytes.
- If length is unknown, the server may use **chunked transfer coding** in HTTP/1.1, or different framing in HTTP/2. Do not assume `Content-Length` is always present.
- Compression (`gzip`) can make bytes **on the wire** differ from bytes **after decompression**. Tests must be clear about which representation they inspect.
- Do not assert `Transfer-Encoding: chunked` solely because a controller uses `StreamingResponseBody`; framing depends on HTTP version, container, proxies, and compression.
- Once headers are sent, mid-stream errors may surface as truncation/`IOException` on the client because the server can no longer change status from 200 to 500. Always **read to EOF** and verify the full byte count.

## 6. Test data must catch encoding corruption

Do not only upload `"hello"` and assume binary files are safe. Construct data with tricky bytes:

~~~java
byte[] payload = {
        0, 10, 13, 65, 127, (byte) 0x80, (byte) 0xFF
};
~~~

This snippet is a **Java test fixture**. It includes a null byte, line feed, carriage return, and non-ASCII bytes; bugs caused by converting bytes through `String`/UTF-8 will show up immediately.

For large responses, choose a pattern that can be verified independently:

~~~text
index:  0   1   2   ...  254 255 256 257
byte:   00  01  02  ...  FE  FF  00  01
~~~

For a 2MiB + 37-byte stream, the test can verify at index `i` that `(actualByte & 0xFF) == (i & 0xFF)`. There is no need to allocate a 2MiB expected array; an 8KiB buffer and counter suffice. For production-like payloads without a fixed pattern, use a **precomputed SHA-256 checksum or one computed independently from the source fixture**, also checking size and metadata when needed.

**Matching checksums do not replace every assertion**: you still must check HTTP status, `Content-Type`, disposition, access permissions, and that the right file was served.

## 7. Sample API design: small file store plus large stream

We will build a mini Spring Boot 3.5.x MVC application:

~~~text
POST /api/files          multipart form-data; part "file"
  -> validate empty, size, filename
  -> store small bytes in an in-memory store (demo)
  -> 201 Created + Location + JSON receipt

GET /api/files/{id}
  -> 200 + octet-stream + Content-Disposition
  -> body is a Resource to test bytes/Range
  -> 404 if ID does not exist

GET /api/files/large?size=N
  -> 200 + Content-Length=N, streaming repeating pattern 0..255
  -> 400 if N is outside 1..16MiB
~~~

**Intentional demo limits:**

- The upload API accepts at most **512KiB** by application rule; even though the container allows up to 1MB, the application returns 413 if over 512KiB. `MultipartFile.getBytes()` is used strictly because of this small limit.
- In-memory storage and the ID counter are simple fixtures, **not a production design**: they do not survive restarts, do not scale horizontally, and lack quotas/TTL/ACLs.
- Generated large responses up to **16MiB** are not stored files; they are synthesized streams to demonstrate byte/EOF verification.
- Spring Security is omitted in this example; production applications must enforce authorization per file owner/tenant.
- All tests run locally without connecting to cloud storage, DBs, or networks beyond loopback.

### Status and header choices

| Endpoint | Success | Rejection |
| --- | --- | --- |
| `POST /api/files` | 201, `Location: /api/files/F-n`, JSON `id,filename,size` | 400 empty/missing file; 413 over 512KiB; 415 wrong media type |
| `GET /api/files/F-n` | 200, octet-stream, attachment filename, `Content-Length` | 404 non-existent ID |
| `GET /api/files/F-n` with `Range` | 206, `Content-Range` and exact byte slice (supported by `Resource`) | 416 if range is unsatisfiable per API |
| `GET /api/files/large?size=N` | 200, streams N bytes, `Content-Length` | 400 if N is invalid |

### Directory tree

~~~text
src/
  main/
    java/example/filehttp/
      FileHttpApplication.java
      StoredFile.java
      UploadReceipt.java
      InMemoryFileStore.java
      FileController.java
  test/
    java/example/filehttp/
      FileMockMvcTest.java
      FileLiveHttpTest.java
    resources/
      application.properties
~~~

This example uses **Java 17+**, Spring Boot **3.5.x**, JUnit Jupiter, `spring-boot-starter-web`, and `spring-boot-starter-test`. Do not add the WebFlux starter: this is a Servlet MVC / `StreamingResponseBody` example; if a real application uses WebFlux, see Section 15 for comparison.

## 8. Complete production code for the mini application

### 8.1 FileHttpApplication.java

~~~java
package example.filehttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FileHttpApplication {
    public static void main(String[] args) {
        SpringApplication.run(FileHttpApplication.class, args);
    }
}
~~~

Boot discovers the controller and store in the same package via component scanning. Tests use this root application and do not need an extra `@SpringBootApplication` in tests.

### 8.2 StoredFile.java

~~~java
package example.filehttp;

public record StoredFile(
        String id,
        String filename,
        byte[] content) {
}
~~~

The record holds bytes in the demo. For large production files, store metadata and storage keys separately and stream from disk/object storage; never hold entire files in long-lived records or beans.

### 8.3 UploadReceipt.java

~~~java
package example.filehttp;

public record UploadReceipt(
        String id,
        String filename,
        long size) {
}
~~~

The response DTO is serialized to JSON by Jackson; never return internal filesystem paths to callers.

### 8.4 InMemoryFileStore.java

~~~java
package example.filehttp;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class InMemoryFileStore {
    private final AtomicLong ids = new AtomicLong();
    private final ConcurrentMap<String, StoredFile> data =
            new ConcurrentHashMap<>();

    public StoredFile save(String filename, byte[] content) {
        String id = "F-" + ids.incrementAndGet();
        StoredFile saved = new StoredFile(
                id, filename, content.clone());
        data.put(id, saved);
        return saved;
    }

    public Optional<StoredFile> find(String id) {
        StoredFile found = data.get(id);
        if (found == null) {
            return Optional.empty();
        }
        return Optional.of(new StoredFile(
                found.id(), found.filename(),
                found.content().clone()));
    }
}
~~~

Cloning prevents tests from accidentally mutating stored arrays through shared references. `ConcurrentHashMap` and `AtomicLong` support operations within **a single JVM**, **not** uniqueness across server instances or persistent storage durability. In real systems, use a DB/object store with proper IDs and access control.

### 8.5 FileController.java

~~~java
package example.filehttp;

import java.io.IOException;
import java.net.URI;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/files")
public class FileController {
    private static final long MAX_UPLOAD = 512L * 1024;
    private static final int MAX_STREAM = 16 * 1024 * 1024;
    private final InMemoryFileStore store;

    public FileController(InMemoryFileStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadReceipt> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        if (file.getSize() > MAX_UPLOAD) {
            return ResponseEntity.status(
                    HttpStatus.PAYLOAD_TOO_LARGE).build();
        }

        String filename = safeFilename(file.getOriginalFilename());
        StoredFile saved = store.save(filename, file.getBytes());

        return ResponseEntity
                .created(URI.create("/api/files/" + saved.id()))
                .body(new UploadReceipt(
                        saved.id(), filename, saved.content().length));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Resource> download(
            @PathVariable("id") String id) {

        return store.find(id)
                .map(file -> {
                    Resource resource =
                            new ByteArrayResource(file.content());

                    return ResponseEntity.ok()
                            .contentType(
                                    MediaType.APPLICATION_OCTET_STREAM)
                            .contentLength(file.content().length)
                            .header(HttpHeaders.CONTENT_DISPOSITION,
                                    ContentDisposition.attachment()
                                            .filename(file.filename())
                                            .build()
                                            .toString())
                            .body(resource);
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping(
            path = "/large",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> large(
            @RequestParam("size") int size) {

        if (size < 1 || size > MAX_STREAM) {
            return ResponseEntity.badRequest().build();
        }

        StreamingResponseBody body = output -> {
            byte[] block = new byte[8192];
            int offset = 0;

            while (offset < size) {
                int count = Math.min(block.length, size - offset);
                for (int i = 0; i < count; i++) {
                    block[i] = (byte) ((offset + i) & 0xFF);
                }
                output.write(block, 0, count);
                offset += count;
            }
            output.flush();
        };

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(size)
                .body(body);
    }

    private static String safeFilename(String untrusted) {
        String raw = untrusted == null ? "" :
                untrusted.replace('\\', '/');
        String base = raw.substring(raw.lastIndexOf('/') + 1);
        String safe = base.replaceAll("[^A-Za-z0-9._-]", "_");

        if (safe.isBlank() || safe.equals(".")
                || safe.equals("..")) {
            return "upload.bin";
        }
        return safe.length() <= 80
                ? safe : safe.substring(safe.length() - 80);
    }
}
~~~

**Reading the details accurately:**

- `upload` rejects empty files and files >512KiB before calling `getBytes()`. Container rejection of files >1MB happens **at an earlier layer** and may never reach the controller.
- `safeFilename` converts `\` to `/`, keeps only the basename and allowlisted characters; never pass raw `getOriginalFilename()` directly into a filesystem path. This is only basic filename sanitization, not a substitute for antivirus or authorization.
- `download` returns `ResponseEntity<Resource>` with `ByteArrayResource`; binary bodies bypass Jackson. `Content-Disposition` uses the builder to quote/escape the filename.
- `large` does not allocate `byte[size]`; it reuses an 8KiB buffer and writes incrementally. `Content-Length` is accurate because `size` is known upfront; for streams of unknown length, never fabricate a fake length.
- `StreamingResponseBody` uses async Servlet processing; production requires async support and a properly tuned executor. If a client disconnects mid-stream, writing can throw `IOException`; never assume the entire file was delivered.

**Resource protection:** `MAX_STREAM` prevents requests from asking for infinite streams; real systems also need quotas, rate limits, authentication, backpressure/connection limits, and timeouts.

## 9. Test configuration for multipart and the application

File `src/test/resources/application.properties`:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=1MB
spring.servlet.multipart.max-request-size=2MB
spring.servlet.multipart.file-size-threshold=0B
~~~

Because the application caps uploads at 512KiB, a multipart request with 512KiB + 1 byte (yet under 1MB) reaches the controller and receives **413 from the application rule**, rather than relying on container exceptions. This makes the 413 test deterministic and container-independent.

To test the servlet parser's real **`max-file-size = 1MB` limit**, write a real HTTP test with a payload larger than 1MB and appropriate error mapping; MockMvc's mock multipart does not prove parser limits. You may need `MaxUploadSizeExceededException` handling and container-specific configuration when requests exceed the limit.

Never point test files at production paths or create container storage from production environments in CI. In this example, no disk directory is used for long-term uploaded file storage.

## 10. MockMvc: fast checks for uploads, downloads, and small streams

File `src/test/java/example/filehttp/FileMockMvcTest.java`:

~~~java
package example.filehttp;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@DisplayName("MockMvc tests multipart and download controller")
class FileMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    @DisplayName("Upload returns 201 and download matches byte-for-byte")
    void uploadsAndDownloadsBinary() throws Exception {
        byte[] original = {0, 10, 13, 65, 127, (byte) 0xFF};
        MockMultipartFile part = new MockMultipartFile(
                "file", "tiny.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                original);

        MvcResult uploaded = mvc.perform(
                        multipart("/api/files").file(part))
                .andExpect(status().isCreated())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.filename").value("tiny.bin"))
                .andExpect(jsonPath("$.size").value(original.length))
                .andReturn();

        JsonNode receipt = mapper.readTree(
                uploaded.getResponse().getContentAsByteArray());
        String id = receipt.path("id").asText();

        assertFalse(id.isBlank());
        assertEquals("/api/files/" + id,
                uploaded.getResponse().getHeader(HttpHeaders.LOCATION));

        mvc.perform(get("/api/files/{id}", id))
                .andExpect(status().isOk())
                .andExpect(content().contentType(
                        MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"tiny.bin\""))
                .andExpect(header().longValue(
                        HttpHeaders.CONTENT_LENGTH, original.length))
                .andExpect(content().bytes(original));
    }

    @Test
    @DisplayName("Empty file is rejected with 400")
    void rejectsEmptyUpload() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                new byte[0]);

        mvc.perform(multipart("/api/files").file(empty))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Exceeding 512KiB app limit returns 413")
    void rejectsOversizedUpload() throws Exception {
        byte[] tooLarge = new byte[512 * 1024 + 1];
        MockMultipartFile part = new MockMultipartFile(
                "file", "oversized.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                tooLarge);

        mvc.perform(multipart("/api/files").file(part))
                .andExpect(status().is(413));
    }

    @Test
    @DisplayName("Filename with path traversal is reduced to safe basename")
    void sanitizesUntrustedFilename() throws Exception {
        MockMultipartFile part = new MockMultipartFile(
                "file", "../../unsafe.bin",
                MediaType.APPLICATION_OCTET_STREAM_VALUE,
                new byte[]{1});

        mvc.perform(multipart("/api/files").file(part))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.filename").value("unsafe.bin"));
    }

    @Test
    @DisplayName("Downloading missing ID returns 404")
    void returns404ForMissingFile() throws Exception {
        mvc.perform(get("/api/files/F-not-present"))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("Non-multipart request is rejected with 415")
    void rejectsWrongUploadMediaType() throws Exception {
        mvc.perform(post("/api/files")
                        .contentType(MediaType.APPLICATION_OCTET_STREAM)
                        .content(new byte[]{1, 2, 3}))
                .andExpect(status().is(415));
    }

    @Test
    @DisplayName("StreamingResponseBody uses async dispatch in MockMvc")
    void smallGeneratedStreamUsesAsyncDispatch() throws Exception {
        int size = 257;

        MvcResult async = mvc.perform(get("/api/files/large")
                        .param("size", Integer.toString(size)))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(async))
                .andExpect(status().isOk())
                .andExpect(header().longValue(
                        HttpHeaders.CONTENT_LENGTH, size))
                .andExpect(content().bytes(pattern(size)));
    }

    private static byte[] pattern(int size) {
        byte[] bytes = new byte[size];
        for (int i = 0; i < size; i++) {
            bytes[i] = (byte) (i & 0xFF);
        }
        return bytes;
    }
}
~~~

**There are 7 `@Test` methods.** In the first test, bytes containing `0x00` and `0xFF` catch accidental text conversions. The download test asserts status, `Content-Type`, `Content-Disposition`, `Content-Length`, and the **entire byte array**.

### Why is `asyncDispatch` needed?

`StreamingResponseBody` is handled asynchronously by Spring MVC. In MockMvc, the initial request returns with `asyncStarted()`; once the async result is ready, the test calls `asyncDispatch(result)` to complete response processing as a second dispatch. With a real HTTP client, the caller simply reads the body until EOF without triggering a separate dispatch.

**Major limitation:** MockMvc writes the body into a mock response buffer, so a passing `smallGeneratedStreamUsesAsyncDispatch` **does not prove the server streams 16MiB over TCP with steady memory**. That evidence requires the live test in Section 11.

### Why can 413 be tested in MockMvc here?

Because `FileController` has its own rule `file.getSize() > 512KiB`, not because MockMvc simulates Tomcat's multipart size limit. A test relying solely on `spring.servlet.multipart.max-file-size` with no controller rule **should not expect** `MockMultipartFile` to be rejected by the container.

## 11. Real HTTP: multipart wire upload and large stream download

File `src/test/java/example/filehttp/FileLiveHttpTest.java`:

~~~java
package example.filehttp;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("Real HTTP: multipart, bytes, Range, large responses")
class FileLiveHttpTest {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    @DisplayName("Real multipart upload/download and 206 Range check")
    void realMultipartRoundTripAndRange() throws Exception {
        byte[] source = {
                0, 10, 13, 65, 127, (byte) 0xFF
        };
        String boundary = "BoundaryTest202";
        byte[] body = multipartBody(
                boundary, "file", "real.bin", source);

        HttpRequest upload = HttpRequest.newBuilder(url("/api/files"))
                .header("Content-Type",
                        "multipart/form-data; boundary=" + boundary)
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> uploaded = http.send(
                upload,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(201, uploaded.statusCode());
        assertTrue(uploaded.headers()
                .firstValue("Content-Type").orElse("")
                .startsWith("application/json"));

        JsonNode receipt = mapper.readTree(uploaded.body());
        String id = receipt.path("id").asText();
        assertFalse(id.isBlank());
        assertEquals("real.bin",
                receipt.path("filename").asText());
        assertEquals(source.length,
                receipt.path("size").asInt());

        String location = uploaded.headers()
                .firstValue("Location").orElseThrow();
        assertEquals("/api/files/" + id,
                URI.create(location).getPath());

        // URI.resolve handles both relative and absolute Location values.
        URI downloadUri = url("/").resolve(location);

        HttpResponse<byte[]> downloaded = http.send(
                HttpRequest.newBuilder(downloadUri)
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofByteArray());

        assertEquals(200, downloaded.statusCode());
        assertEquals("application/octet-stream",
                downloaded.headers()
                        .firstValue("Content-Type").orElse(""));
        assertEquals("attachment; filename=\"real.bin\"",
                downloaded.headers()
                        .firstValue("Content-Disposition").orElse(""));
        assertEquals(source.length,
                downloaded.headers()
                        .firstValueAsLong("Content-Length").orElse(-1));
        assertArrayEquals(source, downloaded.body());

        HttpResponse<byte[]> ranged = http.send(
                HttpRequest.newBuilder(downloadUri)
                        .header("Range", "bytes=2-4")
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofByteArray());

        assertEquals(206, ranged.statusCode());
        assertEquals("bytes 2-4/" + source.length,
                ranged.headers()
                        .firstValue("Content-Range").orElse(""));
        assertArrayEquals(Arrays.copyOfRange(source, 2, 5),
                ranged.body());
    }

    @Test
    @DisplayName("Large stream verified byte-by-byte in blocks without buffering body")
    void consumesLargeResponseWithoutMaterializingWholeBody()
            throws Exception {
        int size = 2 * 1024 * 1024 + 37;

        HttpRequest request = HttpRequest.newBuilder(
                        url("/api/files/large?size=" + size))
                .header("Accept", "application/octet-stream")
                .timeout(Duration.ofSeconds(30))
                .GET()
                .build();

        HttpResponse<InputStream> response = http.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        assertEquals(200, response.statusCode());
        assertEquals("application/octet-stream",
                response.headers()
                        .firstValue("Content-Type").orElse(""));
        assertEquals(size,
                response.headers()
                        .firstValueAsLong("Content-Length").orElse(-1));

        long count = 0;
        byte[] chunk = new byte[8192];

        try (InputStream stream = response.body()) {
            int n;
            while ((n = stream.read(chunk)) != -1) {
                for (int i = 0; i < n; i++) {
                    int actual = chunk[i] & 0xFF;
                    int expected = (int) ((count + i) & 0xFF);
                    if (actual != expected) {
                        fail("Byte mismatch at index " + (count + i));
                    }
                }
                count += n;
            }
        }

        assertEquals(size, count);
    }

    @Test
    @DisplayName("Application rejects >512KiB upload over real HTTP")
    void realServerRejectsApplicationSizeLimit() throws Exception {
        byte[] tooLarge = new byte[512 * 1024 + 1];
        String boundary = "BoundaryTooLarge202";
        byte[] body = multipartBody(
                boundary, "file", "big.bin", tooLarge);

        HttpRequest request = HttpRequest.newBuilder(url("/api/files"))
                .header("Content-Type",
                        "multipart/form-data; boundary=" + boundary)
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<Void> response = http.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertEquals(413, response.statusCode());
    }

    @Test
    @DisplayName("Out-of-range stream size receives 400")
    void rejectsInvalidLargeResponseSize() throws Exception {
        HttpResponse<Void> response = http.send(
                HttpRequest.newBuilder(
                                url("/api/files/large?size=16777217"))
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(400, response.statusCode());
    }

    @Test
    @DisplayName("Downloading missing ID over TCP returns 404")
    void returns404ForMissingDownload() throws Exception {
        HttpResponse<Void> response = http.send(
                HttpRequest.newBuilder(
                                url("/api/files/F-never-created"))
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(404, response.statusCode());
    }

    private URI url(String relativePath) {
        return URI.create(
                "http://127.0.0.1:" + port + relativePath);
    }

    private static byte[] multipartBody(
            String boundary,
            String field,
            String filename,
            byte[] payload) throws Exception {

        ByteArrayOutputStream out = new ByteArrayOutputStream();

        String preamble = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + field
                + "\"; filename=\"" + filename + "\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n";
        String epilogue = "\r\n--" + boundary + "--\r\n";

        out.write(preamble.getBytes(StandardCharsets.US_ASCII));
        out.write(payload);
        out.write(epilogue.getBytes(StandardCharsets.US_ASCII));

        return out.toByteArray();
    }
}
~~~

**There are 5 `@Test` methods.** When they run, Spring Boot starts the embedded server on a random port (injected via `@LocalServerPort`), and JDK `HttpClient` sends HTTP requests over loopback.

### Reading each test's exact evidence

1. **`realMultipartRoundTripAndRange`:** builds valid multipart boundary/headers/body, POSTs over TCP, asserts 201 and JSON, then GETs from `Location` and verifies all bytes, `Content-Disposition`, and `Content-Length`. Next, sends `Range` and verifies 206 + 3 bytes.
2. **`consumesLargeResponseWithoutMaterializingWholeBody`:** uses `BodyHandlers.ofInputStream()`, an 8KiB buffer, and a counter. It checks **every single byte** of a 2MiB + 37-byte response without holding the whole body in a `byte[]`. Reading to EOF catches truncated streams.
3. **`realServerRejectsApplicationSizeLimit`:** payload >512KiB yet under the 1MB parser limit; verifies HTTP 413 from the controller rule through the real server.
4. **`rejectsInvalidLargeResponseSize`:** requests >16MiB stream limit, checking 400 without making the server emit a giant body.
5. **`returns404ForMissingDownload`:** non-existent ID does not return a successful binary body.

**Client resource note:** with `BodyHandlers.ofInputStream()`, you must read and close the `InputStream`. Leaving it unclosed can prevent connections from returning cleanly and exhaust the connection pool in large suites. If a test intentionally aborts mid-stream, close the stream and verify expected behavior; do not treat cancellation as a file upload rollback.

**Memory distinction:** `multipartBody(...)` in the live test **does allocate a `byte[]`** for the request, which is fine since this test file is bounded at 512KiB. For **multi-GB uploads**, use a streaming request body publisher or file-based client rather than assembling the entire multipart body in RAM.

## 12. Running Gradle and expected results

In a Spring Boot 3.5.x project with managed plugins/versions, add to `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **configuration snippet**, not a complete `build.gradle`. With Java 17+ toolchain, the starters supply `spring-webmvc`, the embedded servlet container, `spring-test`, Jackson, and JUnit Jupiter.

Run both test classes:

~~~bash
./gradlew test --tests example.filehttp.FileMockMvcTest --tests example.filehttp.FileLiveHttpTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.filehttp.FileMockMvcTest --tests example.filehttp.FileLiveHttpTest
~~~

**Expected outcome:** a total of **12 JUnit Jupiter methods PASS** (7 MockMvc + 5 live HTTP) in a project with matching packages and dependencies, without Spring Security or custom configs altering the contract. The tests **print no custom application stdout**; Spring Boot logs and Gradle reports vary by version, machine, and random port. `BUILD SUCCESSFUL` is the expected build result, not a previously recorded run log.

If running in a project that already has Spring Security, HTTP endpoints may be blocked by auth/CSRF. Add matching security policies and test credentials/`spring-security-test` rather than disabling filters globally just to get 200.

### Differences between MockMvc and real server are important signals

- MockMvc upload PASS, live upload FAIL → check boundary/CRLF, multipart resolver, and container limits.
- MockMvc download bytes match, live download truncated → check server/network/timeouts/framing/stream writer.
- Live response status 200 yet body missing bytes → check whether the client **read the entire stream** and compare against `Content-Length`.
- `Content-Disposition` header looks right yet browser fails to download → check filename encoding, CORS, cross-origin download policy, MIME, CSP, and browser behavior.
- 206 download has wrong `Content-Range` → check `Resource` type, underlying 200 status, range parser, conditional headers, and proxies.

## 13. When responses are genuinely huge: safe test design

### 13.1 Avoid `byte[]` on both sides

Using `ByteArrayResource` is suitable **for small uploaded files**. For 5GB files, production should use:

- `FileSystemResource` or a `Resource` reading lazily from disk, once access is authorized.
- `StreamingResponseBody` writing chunks from an `InputStream` or object storage.
- `ResourceRegion` / `ResponseEntity<Resource>` under the right conditions when supporting ranges.
- Presigned object-storage URLs for direct downloads when architecture permits, with proper TTLs and ACLs.

Never call `file.getBytes()`, `Files.readAllBytes(...)`, or `bodyToMono(byte[].class)` for massive files. They duplicate payloads and spike heap usage. `Content-Length` says nothing about how much memory was used to build the body.

### 13.2 Verify by checksum instead of copying the file into test heap

When there is no simple byte formula, verify a hash:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
long total = 0L;

try (InputStream in = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        digest.update(buffer, 0, n);
        total += n;
    }
}

byte[] sha256 = digest.digest();
assertEquals(expectedSize, total);
assertArrayEquals(expectedSha256, sha256);
~~~

This is an **illustrative snippet** inside a test that already has `HttpResponse<InputStream> response`, `expectedSize`, and `expectedSha256`, needing `MessageDigest` and assertion imports. The expected hash must be computed **independently** from the source fixture or a trusted value; if the test computes the expected hash by calling the same server function under test, both could share the same bug.

This test only holds an 8KiB buffer and digest state instead of reading a 5GB file into RAM. Also verify `Content-Type`, owner authorization, disposition, and status.

### 13.3 Do not claim "no heap growth" from a single request

Reading a stream in chunks proves the **test client does not intentionally buffer the entire body**, yet it does not automatically prove server heap stays bounded. To evaluate production memory:

- Test sufficiently large files and multiple concurrent connections in a controlled environment.
- Monitor heap/RSS/GC and native/direct buffers, not just a one-off `Runtime.freeMemory()` check.
- Inspect thread pool / executor queues when clients are slow or drop off.
- Enforce resource limits (upload size, active streams, disk quotas, timeouts) and test rejection behavior.
- Verify whether the object-storage API/client genuinely streams or buffers internally.
- When throughput/latency is a goal, separate performance/load tests from the basic unit/CI suite.

Never use `Thread.sleep(...)` to simulate an indefinitely slow client. For slow/throttled tests, use controlled client/server setups, explicit deadlines, and observable metrics.

### 13.4 EOF, timeouts, cancellation, and HTTP failures

For large downloads, tests must read until `InputStream.read(...) == -1`; if `Content-Length` is 2MiB yet only 1MiB arrives, **that is a failure**, even if the initial status was 200.

On a real wire:

- `HttpRequest.timeout(Duration)` bounds one aspect of request timing; timeout behavior during stream reads can depend on the `BodyHandler` and JDK version. For long streams, manage an overall operation deadline per test design.
- Errors after headers are sent can appear as `IOException`/truncation; the server cannot change the status to 500 once the response is committed.
- If a client cancels/closes the stream, the server may see broken pipe or connection reset. Do not let the test suite treat that as an unexpected business exception when testing intentional cancellation.
- For interrupted uploads, clean up temporary files/partial objects and transactions, and never mark metadata "complete" until all bytes are received.

## 14. HTTP Range, ETag, and caching

Large files/videos often need **resumable downloads** via `Range`:

~~~http
GET /api/files/F-1
Range: bytes=1000-1999
~~~

On success, the server returns 206 with that 1,000-byte slice; `Content-Range` describes the offsets and total size. The live test in Section 11 uses a small file and `bytes=2-4` to prove this exact protocol.

Beyond `Range`, production may use:

- **ETag:** content version identifier, useful for `If-None-Match` and `If-Range`.
- **Last-Modified:** caching/revalidation, requiring consistent clocks and metadata.
- **Accept-Ranges: bytes:** advertise only when the server actually serves ranges.
- **416 Range Not Satisfiable:** range outside file bounds, optionally with `Content-Range: bytes */size`.
- **206 multipart/byteranges:** when multiple byte ranges are requested, `Content-Type` can be `multipart/byteranges` with its own boundary, **distinct from upload `multipart/form-data`**.
- **HEAD:** some clients fetch metadata without downloading the body; test headers, empty body, and `Content-Length` per contract.

Do not claim `StreamingResponseBody` automatically handles `Range`; the `large` endpoint in the example generates a sequential stream and **is not designed for Range requests**. If resume is needed, use random-access storage or compute exact stream offsets, testing both valid and invalid ranges.

## 15. Spring WebFlux: same goal, different API

If an application uses Spring WebFlux, uploads typically use `FilePart` or `PartEvent`, and large responses may return `Flux<DataBuffer>`. Do not copy `MultipartFile`/`StreamingResponseBody` controllers verbatim from MVC to WebFlux without adapting the architecture.

A WebFlux upload sample (illustrative only; destination and cleanup must be managed):

~~~java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<Void>> upload(
        @RequestPart("file") FilePart file) {
    Path target = Path.of("/controlled-test-storage", "safe.bin");
    return file.transferTo(target)
            .thenReturn(ResponseEntity.accepted().build());
}
~~~

This snippet is **not a standalone file**: it requires `Mono`, `FilePart`, `Path`, `ResponseEntity`, controller mappings, and an existing directory; the target path is illustrative and must not be used in production. Real implementations must check permissions, filename validation, temp files, size limits, and I/O errors.

When working with `Flux<DataBuffer>` or `PartEvent`, buffers must be properly consumed/forwarded/**released** per contract to avoid memory leaks. Non-blocking reactive code does not exempt you from buffer management.

### WebTestClient for large responses

`WebTestClient` offers a convenient `expectStatus`/`expectHeader`/`expectBody` DSL, though `expectBody(byte[].class)` or `bodyToMono(byte[].class)` can buffer the whole body and hit `maxInMemorySize`. For streaming responses, use `returnResult(...)` and consume `Flux<DataBuffer>` while ensuring buffers are released, or use a streaming HTTP client.

**Do not fix `DataBufferLimitException` by raising `maxInMemorySize` indefinitely across all tests.** First examine whether the API should stream, whether the client is aggregating unnecessarily, and what limit fits the contract.

## 16. Upload/download security and mandatory production tests

This is a high-risk area because the server accepts untrusted input and returns content that browsers may interpret specially.

### 16.1 Upload

- **Filename traversal:** clients can send `../../etc/passwd` or `C:\temp\evil.exe`. Never concatenate raw filenames into filesystem paths. Normalize to basename, allowlist characters, and store under generated storage keys.
- **Spoofed media types:** a client can declare `image/png` for an executable. Use file-signature sniffing and proper policies; never trust `MultipartFile.getContentType()` as safety proof.
- **Size limits:** enforce per-file, per-request, part count, disk thresholds, and total quotas; container limits and application rules are two separate layers.
- **Zip bombs, decompression, parser bugs:** if the server decompresses archives or parses images/PDFs, enforce post-decompression size limits, entry counts, depth limits, and timeouts.
- **Virus scanning and quarantine:** accepting an upload does not mean "ready for public download"; isolate scan status when policy requires it.
- **Authorization/tenant isolation:** attach ownership to files and check permissions before saving or reading; guessable IDs must never grant access.
- **Temp file cleanup:** failed/timed-out uploads must delete temp files or partial objects to prevent filling disks.
- **Metadata/XSS:** escape filenames in responses/`Content-Disposition`; if rendering filenames in HTML, encode for the HTML context.

### 16.2 Download

- Test **401/403** when unauthenticated/unauthorized; use `404` when hiding object existence per policy.
- Check `Content-Disposition: attachment` for untrusted content; if `inline` is intentional, enforce CSP, accurate MIME, and `X-Content-Type-Options: nosniff` per policy.
- Never return local filesystem paths, temporary credentials, or long-lived signed URLs in responses/logs.
- Never serve another owner's byte array/stream for an ID, especially if cache keys omit tenant IDs.
- With `Range` and caching, check authorization **before** returning any partial bytes; `Range` is never a way to bypass ACLs.

### 16.3 Example tests to add when production has auth

| Case | Expectation |
| --- | --- |
| User A downloads User B's file | 403 or 404 per security contract, zero bytes returned |
| Anonymous upload when auth required | 401/403, nothing written to storage |
| CSRF on form upload | Only valid tokens succeed if policy requires CSRF |
| Filename with slashes, backslashes, quotes, CRLF, Unicode | No traversal or header injection |
| Upload exceeding total quota even with small files | Semantic error status; no half-written state |
| Declared MIME contradicts actual file bytes | Rejected or quarantined per policy |
| Download with stale ETag / invalid Range | 200/206/304/416 per contract |
| Client disconnects mid-download | Resource/stream closed and metrics record the error |

The mini example does not configure Security; do not treat it as a production default.

## 17. Common pitfalls when testing uploads, downloads, and large responses

**1. Using MockMvc and claiming the multipart parser was tested.**  
MockMvc creates a `MockMultipartHttpServletRequest` without parsing raw multipart over the embedded container. Add at least one `RANDOM_PORT` test.

**2. Using `content().string(...)` or `BodyHandlers.ofString()` for binary files.**  
Text decoding can alter bytes. Use byte arrays for small files and `InputStream`/checksums for large files.

**3. Checking only status 200 without verifying `Content-Disposition` or bytes.**  
A controller can return an error HTML/JSON page with the wrong status, or right headers with a corrupted body. Assert everything in the contract.

**4. Comparing new IDs against hardcoded literals.**  
IDs may be generated dynamically. Parse the ID/`Location` from the upload response and use it to download; never depend on test order or an ID starting at `F-1`.

**5. Uploading oversized files in MockMvc and expecting `spring.servlet.multipart.max-file-size` to reject them.**  
`MockMultipartFile` bypasses the container parser. Only test application rules in MockMvc; test parser limits over real HTTP.

**6. Measuring file size by character count.**  
`String.length()` counts UTF-16 code units, not UTF-8 bytes or binary byte counts. Use `MultipartFile.getSize()`, `byte[].length`, or bytes read from the stream.

**7. Trusting client-supplied filenames.**  
Creates path traversal and header injection risks. Normalize, allowlist, use storage-generated keys, and re-verify resolved paths per policy.

**8. Returning a wrong `Content-Length` for streams.**  
Clients may hang waiting for more data or treat the response as truncated. Only set it when the exact byte count to be written is certain; otherwise let the container frame the response.

**9. Testing "streaming" by reading the entire response into a `byte[]`.**  
The test may still pass for small sizes, yet it fails to prove the client avoids OOM. Use `ofInputStream()`/`ofFile()` and read to EOF.

**10. Asserting chunked transfer just because `StreamingResponseBody` is used.**  
HTTP/1.1 vs HTTP/2, `Content-Length`, and compression can produce different framing. Test the data contract rather than pinning transport-level framing headers unless required.

**11. Forgetting `asyncDispatch` with MockMvc streaming.**  
The response is not finished when async starts. Call `request().asyncStarted()`, then `asyncDispatch(...)`, and assert the final response.

**12. Leaving HTTP `InputStream` unclosed.**  
Risks leaking connections and failing to return connections to the pool. Use try-with-resources and read to EOF.

**13. Assuming status 200 guarantees the full body arrived.**  
Mid-stream failures after commit surface only as premature EOF/`IOException`. Verify total byte count and checksum/bytes at stream end.

**14. Testing 413 with payloads exceeding the container max and expecting controller handlers to always run.**  
The container can reject the request before the controller, with container-dependent response/connection behavior. To test business limits, stay below container max; test parser limits separately.

**15. Testing real HTTP while expecting `@Transactional` to roll back server writes.**  
Client and server run on different threads/transactions; test-thread rollback does not undo commits made in the HTTP handler. Use isolated test storage and explicit cleanup.

**16. Setting overly tight timeouts or `Thread.sleep` to wait on streams.**  
Causes flaky CI failures. Use reasonable deadlines, explicit completion/EOF checks, verify async executors, and avoid arbitrary blocking.

**17. Sharing a mutable in-memory store across tests without accounting for caching.**  
`@SpringBootTest` contexts can be reused. Tests should read IDs from responses rather than hardcoding IDs or relying on global row counts; clean up stateful operations.

**18. Confusing upload `multipart/form-data` with `multipart/byteranges`.**  
They are completely different formats/use cases; `multipart/byteranges` is a response format for multiple byte ranges, not form field uploads.

## 18. QA workflow for a Spring Boot file endpoint

1. **Define the contract:** method/URI, part names, status codes, size limits, headers, response schema/bytes.
2. **Choose two test layers:** MockMvc for fast branches, `RANDOM_PORT` for raw multipart/container/streaming.
3. **Use binary fixtures:** include `0x00`, CR/LF, and non-ASCII bytes; never only ASCII text.
4. **Real upload request:** valid boundary/CRLF, multipart content type, `file` part, filename, and bytes.
5. **Assert upload response:** 201, JSON metadata, `Location`; rely strictly on the actual response ID.
6. **Download using the newly created ID:** verify 200, `Content-Type`, `Content-Disposition`, `Content-Length`, and intact bytes.
7. **Test negative cases:** empty/missing part, wrong media type, exceeding app limit, parser limit, not found, unauthorized.
8. **Test Range if supported:** 206, `Content-Range`, exact byte slice, invalid range.
9. **Test large responses:** request a valid bounded size; read with a fixed buffer, verify block-by-block/hash, EOF, and total bytes.
10. **Test async/timeouts:** MockMvc streaming needs `asyncDispatch`; live clients must enforce deadlines and close `InputStream`.
11. **Test resource usage separately:** heap, temp disk, executor, load, slow clients, cancellation if the API has high-load risks.
12. **Test real storage/security:** quotas, permissions, virus scanning, object store, path traversal/ACLs.
13. **Separate evidence:** MockMvc does not prove TCP; live HTTP with an in-memory store does not prove cloud storage, antivirus, or CDN behavior.
14. **Keep CI reliable:** random ports, independent fixtures and cleanup, zero production credentials.

### Final checklist

- [ ] Client genuinely sends `multipart/form-data` with matching boundary and part name.
- [ ] At least one upload test runs against a real server, not solely `MockMultipartFile`.
- [ ] Empty, missing, wrong media type, and oversized cases are tested per status contract.
- [ ] Input filenames are never used directly as filesystem paths or unescaped response headers.
- [ ] Upload 201/`Location`/JSON metadata response is accurate and leaks no storage paths.
- [ ] Downloads assert **bytes** without converting binary data to `String`.
- [ ] `Content-Type`, `Content-Disposition`, and `Content-Length` are checked when contracted.
- [ ] `Range`/206/`Content-Range` are tested if the endpoint supports resume.
- [ ] Large-response tests stream in chunks or write to file without materializing the full body in test heap.
- [ ] Total bytes/EOF/checksums are verified; initial 200 status is not treated as sufficient.
- [ ] MockMvc async tests use `asyncDispatch` when needed.
- [ ] Server multipart limits and application rules are tested **separately**.
- [ ] Authorization/tenant checks, storage quotas, and cleanup are tested at the proper layers in production.
- [ ] Random ports and ID/fixture ordering are never hardcoded between test methods.
- [ ] Strategies exist for timeouts, cancellation, task executors, and resource monitoring.
- [ ] Test project matches the API's Java/Spring Boot versions and imports; never mix MVC `MultipartFile` with WebFlux `FilePart`.

**Conclusion:** Upload/download testing is valuable when it completes the full loop of **multipart request → server handling → status/Location → download → byte-for-byte match**. For large bodies, test over real HTTP with a **streaming client**, not merely status checks or mock response buffers. Combine MockMvc and `RANDOM_PORT` to catch bugs in both MVC logic and protocol/container layers, while verifying security and resource limits at their corresponding layers.

### Official references

- [Spring Framework — Multipart MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `MultipartFile`, `@RequestParam`, `@RequestPart`, and multipart binding.
- [Spring Boot 3.5 — Servlet Multipart Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.servlet.multipart.max-file-size`, `max-request-size`, threshold.
- [Spring Boot — Handling Multipart Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): upload handling and container limits.
- [Spring Framework — MockMvc Performing Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): `multipart(...)` uses mock servlet requests without raw multipart parsing.
- [Spring Framework — Testing Async MVC Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): `request().asyncStarted()`, `asyncDispatch(...)`.
- [Spring Framework — MVC Async and Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `StreamingResponseBody`, async executor, timeouts.
- [Spring Framework — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html): `Resource`/`ResponseEntity<Resource>`, `206`, `InputStreamResource` limits.
- [Spring Framework — Response Body with Resource](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): `Resource` responses and streaming notes.
- [Java 17 HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP requests/responses, `BodyPublishers`/`BodyHandlers`.
- [Spring Framework — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `FilePart` and `PartEvent`, releasing `DataBuffer`.