# Handling Oversized, Malformed, or Aborted Requests During File Upload and Download

## 1. Context: File Transfer Errors vs. Business Processing Errors

An **upload** endpoint receives data from an HTTP client (typically `multipart/form-data` or a raw request body) and may persist it to disk, object storage, or another service. A **download** endpoint reads data and streams it back to the client. Both can fail right before, during, or after byte transfer:

1. **Size limit exceeded:** the body or a file/part exceeds the accepted ceiling; proxies, web servers, multipart parsers, or the application can reject it.
2. **Malformed format:** wrong outer HTTP `Content-Type`; missing/mismatched multipart `boundary`; missing required part; file payload does not match an allowed type; invalid checksum.
3. **Aborted mid-transfer:** client loses network, cancels the request, hits a timeout, proxy drops the connection, disk fills up, or the storage service fails while reading/writing/sending bytes.

These three cases must be handled **according to when they occur**. A controller can only return a response while the HTTP connection is still open and the response is uncommitted. Once the client closes the socket, attempting to return error JSON may fail; instead, clean up temp files, record state, and design for retry/idempotency.

Example upload flow:

~~~text
Client
  |
  | POST /files, multipart/form-data
  v
Reverse proxy / ingress / CDN [body limit, timeout, WAF]
  |
  v
Embedded server Tomcat/Netty [HTTP parser, connection limits]
  |
  v
Spring MVC MultipartResolver or WebFlux multipart reader
  |
  v
Controller/service [file type, content, business limits]
  |
  v
Temp file/stream -> validate -> durable write -> commit metadata
  |
  v
Response 201 + fileId (if connection is still active)
~~~

A request **blocked at the proxy** may never reach Spring Boot. A multipart request **failing during parsing** may never invoke the controller. And committing an upload successfully while the client loses the response **does not mean** the upload failed: server and client can observe two different outcomes.

## 2. Picking the Right HTTP Status for Each Error Type

| Scenario | Status to Consider | Notes |
| --- | --- | --- |
| Request body exceeds server-accepted limit | **413 Content Too Large** | May come from proxy/container before the app; older reason phrase is “Payload Too Large” |
| Outer `Content-Type` not supported by endpoint | **415 Unsupported Media Type** | E.g., endpoint requires multipart but client sends `application/json` |
| Multipart missing `boundary`, malformed part, missing required field | **400 Bad Request** | Some failures cause the server to close the connection before responding |
| File part declares an unsupported type | **415** or **422** per API contract | Contract must explicitly define policy for each error class |
| Request is structurally valid, file content fails semantic rules | **422 Unprocessable Content** | E.g., claims PDF yet bytes lack valid structure |
| Insufficient permission to access/upload/download | **401/403** | Keep authentication/authorization separate from format validation |
| File missing on download | **404 Not Found** | Never return an empty file with status 200 |
| Out of storage space or storage dependency down | **500/503** by nature | Log internally; never leak paths or stack traces to client |
| Timeout before full HTTP request received | **408 Request Timeout** possible | May surface merely as connection reset depending on server/proxy |
| Gateway timeout calling upstream | **504 Gateway Timeout** | Does not guarantee backend failed to commit the upload |
| Client closes connection before completion | **No HTTP status guaranteed at client** | Server may see IOException/broken pipe or proxy log `499` (non-IANA code) |

**413 is not a catch-all check for bad content.** Oversized payloads are a *size* issue; wrong headers are a *media type/structure* issue; malicious or invalid file payloads require *content validation*. Once a client disconnects, you cannot promise “always return 400/500.”

HTTP/1.1 may use `Content-Length` or chunked transfer framing, while HTTP/2 and HTTP/3 use frames. Never trust client-declared `Content-Length` unconditionally: requests can be truncated or stalled, and servers/parsers must enforce limits while reading actual bytes. Per RFC 9110, if a server detects an oversized body it may terminate the connection; the client may observe a transport error rather than a clean 413 JSON response.

## 3. Enforcing Size Limits Across Multiple Layers

### 3.1. Spring Boot Servlet / Spring MVC

With `spring-boot-starter-web`, multipart uploads are handled via the Servlet `Part` API and `MultipartResolver`. Standard properties:

~~~properties
# src/main/resources/application.properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
~~~

- `max-file-size`: limit **per file part**. Spring Boot 3.3 default is **1MB**.
- `max-request-size`: limit for **the entire multipart request**. Default is **10MB**. Covers all parts and multipart framing overhead, not just file bytes.
- `file-size-threshold`: threshold for spilling uploaded data to temporary disk. Default **0B**. This is **not** a maximum upload limit.
- `location`: if configured, sets the temp directory for the multipart parser; directory must exist with proper permissions. Defaults to an environment/container-chosen temp location.
- `resolve-lazily`: controls when multipart parsing executes; it can shift **when exceptions occur**, not the size limits themselves.

Set `max-request-size` sufficiently higher than `max-file-size` to accommodate headers, metadata, and valid parts. If an API allows multiple files, enforce a **total cap** alongside the per-file cap. For instance, a 2MB file plus metadata can exceed a request limit set tightly to 2MB.

A classic mistake is bumping `spring.servlet.multipart.max-file-size` to 100MB while leaving `max-request-size` at 10MB, causing requests over 10MB to fail. Conversely, raising only `max-request-size` will not permit a single file larger than `max-file-size`.

Checking size in the controller (e.g., `file.getSize()`) is a **supplemental business guard**, not a replacement for the multipart parser: by the time the controller sees `MultipartFile`, the server/parser may already have read or spooled the request. Enforce limits early at ingress, container/parser, and finally in domain logic.

### 3.2. Proxies, API Gateways, and Containers

Upstream hops impose their own body caps and timeouts (e.g., NGINX `client_max_body_size`), so in practice **the lowest limit along the path** rejects the request first.

Logical example:

~~~text
Gateway limit: 5MB
Spring multipart max-request-size=20MB
Business rule max-file-size=8MB
=> A 6MB request may be blocked with 413 by the gateway before reaching Spring.
~~~

Many setups also cap connection counts, rates, request headers, body read timeouts, temp disk space, and per-account quotas. Keep limits aligned across layers so you don't raise Spring's limit while forgetting the proxy. When seeing 413 with no controller logs, inspect ingress/proxy and server access logs.

### 3.3. When Should Limits Be Raised?

Never set “unlimited” just because files are large. For very large files, evaluate **controlled direct-to-object-storage uploads**, multipart/resumable uploads, or chunking with IDs and checksums rather than buffering everything through the JVM. If large files must pass through, calculate peak concurrent upload volume, quotas, bandwidth, temp space, and cleanup policies.

## 4. Malformed Input Happens at Two Distinct Levels

### 4.1. Malformed HTTP / Multipart Syntax

A valid multipart upload request (logical HTTP/1.1 form) looks like:

~~~http
POST /files HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="file"; filename="sample.pdf"
Content-Type: application/pdf

%PDF-1.4...
--abc123--
~~~

Every part delimiter must match the `boundary` in the header. If the header declares `boundary=abc123` while the body uses a different marker, lacks the closing boundary, lacks required `Content-Disposition`, or cuts off mid-stream, the multipart parser may fail **before the controller runs**.

Do not hand-assemble multipart strings when standard client libraries exist. With cURL, use `-F "file=@sample.pdf;type=application/pdf"` so cURL generates the `boundary` and framing properly; do not manually add a `Content-Type: multipart/form-data` header lacking a boundary.

### 4.2. Invalid File Content Despite Valid Multipart

Client-supplied `filename="report.pdf"` and `Content-Type: application/pdf` **do not prove a file is a PDF**. Filenames can be spoofed, MIME headers altered, and bytes arbitrarily crafted. Validate per application policy, for example:

- Accept only allowlisted media types.
- Check initial file signatures/magic bytes (e.g., PDFs typically start with `%PDF-`), without treating 5 bytes as complete format verification.
- For complex formats, use a trusted parser/library to verify actual structure, bound depth/elements, and strip scripts or macros when needed.
- Scan for malware per policy and guard against **zip bombs**, high decompression ratios, excessive entry counts, and recursion depth in compressed archives.
- Verify hashes when the transfer protocol provides authenticated checksums; checksums detect corruption/mismatch, not whether content is benign.
- Never use `MultipartFile.getOriginalFilename()` as a target path. It is untrusted input that can contain path separators, confusing Unicode, control characters, or `../`. Generate server-side IDs/filenames.

**Suggested status policy:** wrong outer `Content-Type` → 415; missing part/malformed multipart → 400; content exceeds size limit → 413; parseable file violating type/acceptance rules → 422; wrong file part MIME may use 415 per contract. Not every multipart error defaults to 415.

## 5. Spring Boot MVC Example: Validate, Stage to Temp, Commit Atomically

This example demonstrates a **safe error-handling workflow** rather than a complete production storage service. The app accepts **one PDF file up to 2 MiB** via `multipart/form-data`, checks headers and magic signature, **writes to a temporary file inside the target directory**, and renames to publish. If the upload fails to complete, it attempts to remove the temporary file.

### 5.1. Structure and Dependencies

~~~text
safe-files/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/demo/files/UploadSafetyApplication.java
    │   └── resources/application.properties
    └── test/java/demo/files/UploadSafetyHttpTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'safe-files'
~~~

`build.gradle` (Java 17+ and Spring Boot 3.3.13 example):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
~~~

### 5.2. Complete Java Code

File `src/main/java/demo/files/UploadSafetyApplication.java`:

~~~java
package demo.files;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class UploadSafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadSafetyApplication.class, args);
    }
}

@RestController
@RequestMapping("/files")
class FileController {
    private static final long MAX_BYTES = 2L * 1024 * 1024;
    private static final byte[] PDF_MAGIC =
            "%PDF-".getBytes(StandardCharsets.US_ASCII);

    // Example uses a fixed directory controlled by the application.
    private final Path root = Path.of("storage").toAbsolutePath().normalize();

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Receipt> upload(@RequestPart("file") MultipartFile file)
            throws IOException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "File is empty");
        }

        // Business guard, in addition to limits set on the multipart parser.
        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
        }

        // Part Content-Type is only client-declared information.
        if (!MediaType.APPLICATION_PDF_VALUE.equalsIgnoreCase(
                file.getContentType())) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "Only application/pdf is accepted");
        }

        try (InputStream in = file.getInputStream()) {
            byte[] magic = in.readNBytes(PDF_MAGIC.length);
            if (!Arrays.equals(PDF_MAGIC, magic)) {
                throw new ResponseStatusException(
                        HttpStatus.UNPROCESSABLE_ENTITY,
                        "File does not have a PDF signature");
            }
        }

        Files.createDirectories(root);
        Path temporary = Files.createTempFile(
                root, "upload-", ".part");
        boolean committed = false;

        try {
            long copied;
            try (InputStream in = file.getInputStream()) {
                copied = Files.copy(
                        in, temporary,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            if (copied != file.getSize()) {
                throw new IOException("Incomplete file copy");
            }
            if (copied > MAX_BYTES) {
                throw new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
            }

            // Server-generated final name: prevents path traversal.
            String fileName = UUID.randomUUID() + ".pdf";
            Path destination = root.resolve(fileName);

            try {
                Files.move(temporary, destination,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                // If filesystem does not support atomic rename:
                Files.move(temporary, destination);
            }

            committed = true;
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(new Receipt(fileName, copied));
        } finally {
            if (!committed) {
                Files.deleteIfExists(temporary);
            }
        }
    }

    @GetMapping(path = "/{fileName}",
            produces = MediaType.APPLICATION_PDF_VALUE)
    ResponseEntity<Resource> download(@PathVariable String fileName)
            throws IOException {

        // Accept only the filename format generated by this API.
        if (!fileName.matches("[0-9a-f-]{36}\\.pdf")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid file ID");
        }

        Path path = root.resolve(fileName).normalize();
        if (!path.startsWith(root) || !Files.isRegularFile(path)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "File not found");
        }

        Resource resource = new FileSystemResource(path);
        String disposition = ContentDisposition.attachment()
                .filename(fileName)
                .build().toString();

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .contentLength(Files.size(path))
                .body(resource);
    }

    record Receipt(String fileName, long bytes) {
    }
}

@RestControllerAdvice
class FileApiErrors {
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ApiError> oversized(MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(new ApiError("FILE_TOO_LARGE",
                        "Upload exceeds the configured size limit"));
    }

    @ExceptionHandler(MultipartException.class)
    ResponseEntity<ApiError> malformed(MultipartException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_MULTIPART",
                        "Multipart request is invalid"));
    }

    record ApiError(String code, String message) {
    }
}
~~~

**Explaining each error boundary:**

1. `spring.servlet.multipart.*` lets the container/parser block large requests before `upload` runs. `MaxUploadSizeExceededException` is a subclass of `MultipartException`; the more specific size handler takes precedence to return 413 when the exception reaches the Spring MVC exception resolver.
2. `@PostMapping(consumes = "multipart/form-data")` declares the endpoint's body type; requests with the wrong outer media type typically return 415. `@RequestPart("file")` requires a part named `file`; a missing part usually returns 400.
3. The `file.getSize()` guard enforces business policy even if parser limits change or unit tests bypass container limits.
4. Checking part MIME and 5 magic bytes is an **illustrative layer only**. A malicious file can still begin with `%PDF-`. Production must add full parser validation, malware scanning, and storage policies.
5. The `storage` directory is only for the demo, outside `src/main/resources/static`; Spring Boot does not serve it publicly by default. Real apps need download authorization checks and durable storage; **a UUID filename does not replace authorization**.
6. `Files.createTempFile` allocates an isolated file; `Files.copy` writes data; `Files.move` promotes it to the final name **after copying succeeds**. Use atomic rename when the filesystem supports it; fallbacks may lack atomicity on some platforms. Do not treat a file move as a cross-database/object-storage transaction.
7. `finally` attempts to delete `.part` if an IOException or validation error throws **after creating the temp file**. If the JVM/process is killed or power fails, finally will not execute; run a scheduled cleanup job for stale temp files.
8. `ResponseEntity<Resource>` in download streams via a resource instead of loading the file into heap with `Files.readAllBytes`. If the client stops reading mid-stream, an error can happen **after the controller method returns**.
9. There is no blanket `@ExceptionHandler(IOException.class)`: storage failures should be classified and logged internally, whereas client-closed sockets must not be reported as validation failures. In the demo, unhandled IOExceptions follow default server error handling while a response can still be sent.

### 5.3. Running and Observing Results

With the project's Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Create a minimal PDF-signature file to **test the flow** (not a complete PDF document, yet passes the demo's 5-byte guard):

~~~bash
printf '%s\n' '%PDF-1.4' 'demo bytes' > tiny.pdf
curl -i -F "file=@tiny.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

**Expected demo API response:** HTTP **201 Created**, JSON shaped like:

~~~json
{
  "fileName": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.pdf",
  "bytes": 20
}
~~~

`fileName` is a **UUID format example**, different on every run. `bytes` matches the exact byte count produced on your system; do not hard-code 20 in tests since file generation/newlines can differ. A production API performing full PDF validation would reject this illustrative `tiny.pdf` because it is not a valid PDF document.

Use the returned `fileName` to fetch it:

~~~bash
curl -i -o received.pdf \
  "http://localhost:8080/files/<actual-fileName>"
~~~

In the real command, replace `<actual-fileName>` with the UUID name from JSON without angle brackets `<>`. On download, successful status is 200, with `Content-Type: application/pdf` and `Content-Disposition: attachment; filename="..."`; the body streams into `received.pdf`.

**Important note on `curl -i -o`:** `-i` prepends HTTP headers to the output file. To save raw PDF bytes cleanly, use `curl -fL -o received.pdf "URL"` and inspect headers separately with `curl -I "URL"`. Never compare checksums of a file created with `curl -i -o` against the original.

Part MIME error example:

~~~bash
curl -i -F "file=@tiny.pdf;type=text/plain" \
  http://localhost:8080/files
~~~

Expect **415**, as the demo rejects parts declaring `text/plain`. The multipart framing itself is valid; this enforces **inner part type** policy.

Fake PDF example:

~~~bash
printf 'not a PDF\n' > fake.pdf
curl -i -F "file=@fake.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

Expect **422** because `%PDF-` does not match. `fake.pdf` is never published to final storage.

Wrong outer `Content-Type` example:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -d '{"file":"hello"}' \
  http://localhost:8080/files
~~~

Expect **415**, because the endpoint requires `multipart/form-data`.

Oversized file example (Linux/macOS, requires `dd`):

~~~bash
dd if=/dev/zero of=huge.pdf bs=1M count=3
curl -i -F "file=@huge.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

With a 3 MiB file and `max-file-size=2MB`, expect rejection for **exceeding the size limit**. You may observe 413 or a connection error if the parser/container/proxy aborts early; custom JSON from `FileApiErrors` only appears when the exception reaches the resolver while a response can still be written.

## 6. Java Tests: Testing Format and Size Policies

Add JUnit 5 tests (`spring-boot-starter-test` is already included). File `src/test/java/demo/files/UploadSafetyHttpTest.java`:

~~~java
package demo.files;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadSafetyHttpTest {
    @Autowired
    MockMvc mvc;

    @Test
    void acceptsDemoPdfSignature() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "ok.pdf", "application/pdf",
                "%PDF-1.4\n".getBytes(StandardCharsets.US_ASCII));

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.fileName").exists());
    }

    @Test
    void rejectsWrongPartMediaType() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "ok.txt", "text/plain",
                "text".getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsInvalidSignature() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.pdf", "application/pdf",
                "not-pdf".getBytes(StandardCharsets.US_ASCII));

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isUnprocessableEntity());
    }

    @Test
    void rejectsBusinessSizeLimit() throws Exception {
        byte[] bytes = new byte[2 * 1024 * 1024 + 1];
        MockMultipartFile file = new MockMultipartFile(
                "file", "huge.pdf", "application/pdf", bytes);

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isPayloadTooLarge());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.files.UploadSafetyHttpTest
~~~

`MockMvc` tests construct simulated multipart requests without passing through **real Tomcat HTTP parsing and limits**. Thus, the 2MiB+1 test here verifies the controller's **business guard**. To genuinely test `spring.servlet.multipart.max-file-size`, gateway 413s, timeouts, HTTP framing, and dropped connections, write **integration tests against a real running server**, ideally behind proxy/container settings matching deployment.

Tests create `storage/*.pdf` inside the working directory on success. In demos, you can isolate tests to a temp directory; production requires managed storage and retention rules. Never run integration tests writing into real production storage.

## 7. Requests Aborted Mid-Transfer: What Actually Happens?

### 7.1. Client Disconnects Mid-Upload

For example, the browser tab closes, the user cancels, a client times out, or the network drops after sending part of the body:

~~~text
Client                 Server / multipart parser       Storage
  | POST multipart body ... |
  |------------------------->| temporarily receives bytes  |
  |----- partial send ------>|                               |
  X client disconnect        | socket read EOF/reset         |
                             | parser fails or               |
                             | subscription is cancelled     |
                             | cleanup temporary files       |
                             | no response can be guaranteed |
~~~

If the parser has not finished, **the controller may never be called**. Some servers return 400/408; others close the socket and log an exception or access entry. There is no single universal status code for client disconnects. NGINX commonly logs **499 Client Closed Request** in access logs, though 499 **is not a standard HTTP status sent to clients by the app**.

An upload claiming `Content-Length` of 10 MiB that drops after 2 MiB is an **incomplete request**, never a valid 2 MiB file to commit. When using streaming APIs, commit only after receiving real completion and verifying length, checksum, and final markers per contract.

**Never attempt to “resume” a plain `POST multipart/form-data` by replaying only the remaining bytes** unless the server implements a resume protocol. Each POST is normally an independent request. Resumable uploads require upload session IDs, offsets, chunk validation, checksums, expiry, commit/abort handling, and an explicit protocol such as tus or object-storage multipart upload.

### 7.2. Client Disconnects Mid-Download

On the download side, the controller may have sent `200 OK` headers and begun streaming when the client drops. Once the response is **committed**, Spring cannot turn it into a `500` JSON body or alter status headers. The server typically sees IOException, “broken pipe,” “connection reset,” or cancellation signals; the client receives a truncated file and must verify length/hash.

For large downloads, `Content-Length` lets clients detect truncation when available; checksums (published over a trusted channel) catch data corruption better. To resume downloads, the server must support **HTTP Range**/`Accept-Ranges`, return `206 Partial Content` for valid ranges, `416 Range Not Satisfiable` for invalid ranges, and use `ETag`/`If-Range` to avoid splicing chunks across file versions. **Spring does not turn arbitrary custom responses into resumable downloads** merely because `Content-Length` is set.

### 7.3. Server Succeeds While Client Fails

This can happen:

~~~text
Server saves file and commits metadata successfully
        |
        v
Server begins sending HTTP 201
        |
        X connection drops before client receives body
        |
        v
Client: “doesn't know if upload succeeded”
Server: already holds the complete file
~~~

If the client blindly retries POST and each attempt generates a new file, **unwanted duplicates** accumulate. Production designs should use an `Idempotency-Key` or stable `uploadId` bound to the user/permissions and checksum. The client can query status via an authenticated GET instead of re-uploading an already-committed file. Never rely on an HTTP status the client *failed to receive* to infer business state.

## 8. Temp Files, Cleanup, and Safe Commit

A common state pipeline:

~~~text
RECEIVING
   |
   v
TEMPORARY file (not public)
   |
   +--> validate size, type, checksum, security
   |
   v
READY TO COMMIT
   |
   v
MOVE / object-storage finalize + metadata commit
   |
   v
COMPLETED (file published)
~~~

On **failure**, enforce explicit state transitions:

~~~text
RECEIVING / VALIDATING -> FAILED / ABORTED
                            |
                            v
                   cleanup temp file/quota
                            |
                            v
                  record state for retry
~~~

Key design considerations:

- **Per-request temp file:** never let concurrent requests write to the same user-supplied name; use UUIDs, unique IDs, or secure temp-file primitives.
- **Store outside static roots:** never place unvalidated files in `src/main/resources/static` or public web directories.
- **Atomic rename when supported:** on the same filesystem, promote temp to final via `Files.move(..., ATOMIC_MOVE)` when appropriate; fallbacks do not offer the same guarantee. Object storage has its own upload-completion model rather than filesystem renames.
- **Delete on exception/cancel:** use `try/finally` or framework resource cleanup; in reactive code, use cancellation-aware resource lifecycles. In-process cleanup never covers `kill -9`, JVM crashes, or power loss: run scheduled cleanup/quotas for expired `.part` files.
- **DB and file commits do not share a transaction by default:** file save can succeed while DB fails, or vice versa; use a state machine, compensation/repair jobs, and idempotency.
- **Handle storage errors:** `ENOSPC`/disk full, permission denied, quota exceeded, hash mismatch, and antivirus failure must produce clear errors and never return 201.
- **Account for occupied resources:** multipart parsers can consume disk/memory even before the controller sees a file. Quotas must cover temp files, final files, concurrent uploads, and container ephemeral storage.
- **Clean up aborted downloads:** downloads rarely create server temp files, yet streams and readers must be closed; dynamically generated temp archives need dedicated lifecycle management.

A controller's `finally` block will not execute if the client disconnects **before the multipart parser finishes**; the parser/container has its own cleanup lifecycle. Nor is the controller called when a proxy rejects early.

## 9. Spring WebFlux: Limits and Cancellation Differ from Servlet MVC

Apps built on `spring-boot-starter-webflux` use a reactive model: controllers can accept `FilePart` (multipart file), stream data via `Mono`/`Flux`, and propagate connection cancellation down reactive subscriptions. **Never treat `MultipartFile` and `spring.servlet.multipart.*` properties as if they control pure WebFlux.**

Example Spring Boot WebFlux configuration:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=5MB
spring.webflux.multipart.max-parts=4
~~~

**How semantics differ from Servlet:**

- `max-in-memory-size` limits memory buffering for **non-file parts**; for **file parts**, it sets the threshold for spilling to disk. **It does not mean** “all uploaded files are capped at 256KB.”
- `max-disk-usage-per-part` limits disk usage **per part** when the multipart reader writes to disk.
- `max-parts` caps part count in a request, protecting against requests with huge numbers of parts.
- `spring.codec.max-in-memory-size` governs codec buffering (e.g., aggregating a body into an object) and **does not replace all** dedicated multipart limits.
- On streaming `PartEvent` paths, know which limits apply or are bypassed; enforce byte caps and quotas at the ingestion layer when skipping default aggregation.

**Illustrative snippet** for WebFlux `FilePart`, not a standalone controller:

~~~java
@PostMapping(
        path = "/reactive-files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> upload(@RequestPart("file") FilePart file) {
    Path destination = /* server-generated safe temp path */;
    return file.transferTo(destination);
}
~~~

This snippet intentionally omits validation, filenames, cleanup, size quotas, and commit logic: **do not use verbatim in production**. Its point is to highlight that `FilePart.transferTo(Path)` returns `Mono<Void>`, so you must **return/compose** the publisher for WebFlux to subscribe and handle completion/error/cancellation; never call `.block()` on the event loop or call `subscribe()` detached and immediately return 201.

When working directly with `Flux<DataBuffer>` to stream content, follow **reference-counted** buffer ownership rules: release buffers (`DataBufferUtils.release`) when you own them, avoiding leaked buffers on error/cancel paths. Many Spring helpers handle this automatically; never release buffers whose ownership was transferred to an API, as double-release is also a bug.

### Cancellation and Cleanup in WebFlux

When a browser aborts an upload, the subscription receives a **cancel** signal; this differs from `onError`. Using only `doOnError(...)` to delete temp files misses cancellations. Use scoped cleanup like `usingWhen(...)` with complete/error/cancel branches for app-owned resources, or handle `doFinally(SignalType)` carefully. **Never run blocking filesystem operations directly on the event loop**; offload to a suitable scheduler when required. After completion, verify size/hash/format before returning 201.

In Spring WebFlux, exception mapping typically runs through reactive `@RestControllerAdvice`/`@ExceptionHandler` and WebExceptionHandlers; exact exception types for quotas/parsers differ from Servlet `MaxUploadSizeExceededException`, such as `DataBufferLimitException` or multipart parsing exceptions. **Do not copy an MVC `MaxUploadSizeExceededException` handler expecting it to catch all WebFlux errors.** Inspect the real exceptions emitted by your Spring version and map statuses per contract.

## 10. Testing Mid-Transfer Aborts and Real Failures

### 10.1. Controlled Manual Testing

To simulate a client dropping mid-upload, send a file **smaller than the server limit**, throttle bandwidth intentionally, and let cURL time out; perform this in a test environment, never against live data.

Linux/macOS example:

~~~bash
dd if=/dev/zero of=slow.pdf bs=1024 count=1500
printf '%s' '%PDF-' | dd of=slow.pdf conv=notrunc status=none
curl --limit-rate 1024 --max-time 2 \
  -F "file=@slow.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

Depending on OS/cURL and loopback behavior, the outcome **may** be a cURL timeout error, 413 if another layer has a lower limit, or another error. This reproduces the scenario manually; for deterministic automated testing, use fault injection or a test proxy controlling socket closure.

Key check to verify: if the request does not complete, no partial file may appear under a final name; `.part` temp files must be removed by lifecycle cleanup or a sweeper job. Never require clients to receive JSON after a socket has closed.

### 10.2. Distinguishing Three Test Layers

| Test Layer | What It Verifies | What It Does Not Prove |
| --- | --- | --- |
| Unit tests for guards/validators | MIME/signature checks, size, filename, and 422/415 errors | Real HTTP parser or proxy |
| `MockMvc` tests | Controller mapping, handlers, response contracts, app-level guards | Real socket/container limits, cancellation, streaming uploads |
| Real HTTP tests with embedded server | Multipart parser + networking + Spring handlers | Production proxy/ingress policies unless proxy is included |
| End-to-end via reverse proxy | Actual 413/timeouts, upload rules, and cleanup under deployment | Does not prove every network failure mode without fault injection and concurrency load |

Cases to include in a real deployment test suite:

1. 0B file; 1 byte under limit; exact limit; 1 byte over limit.
2. Total request (multiple parts/metadata) exceeding `max-request-size` even when each file is valid.
3. Missing file part, wrong field name, missing boundary, malformed multipart, wrong outer content-type.
4. Spoofed MIME; fake extension; invalid signature; corrupted real PDF; archive with extreme expansion ratio.
5. Concurrent uploads; per-user quota limits; retries with the same idempotency key.
6. Client disconnecting before parser completes, mid-temp-write, and post-commit before receiving 201.
7. Server disk full, permission denied, object storage timeout; verify no invalid final file persists.
8. Download aborted mid-stream; verify client detects missing bytes, server closes resources, and re-download succeeds.
9. Proxy returning 413 early; verify client handles the error even when the app logs nothing in the controller.
10. Process restart mid-upload; stale `.part` cleanup does not accidentally delete active uploads.

## 11. Observability: Recording Real Causes Without False 5xx Alerts

Useful fields in logs and metrics:

- System-generated or policy-validated `requestId`/traceId; authenticated user/tenant ID if present.
- Endpoint, method, status, and **rejecting layer** (proxy/container/parser/app/storage).
- Error category: `SIZE_LIMIT`, `INVALID_MULTIPART`, `UNSUPPORTED_TYPE`, `CONTENT_VALIDATION`, `CLIENT_DISCONNECT`, `STORAGE_FAILURE`.
- Actual bytes received/sent when measurable accurately; client-*declared* bytes are untrusted metadata.
- Upload/download duration, active uploads, temp file/quota usage, and failed cleanups.
- Business state `RECEIVING`, `VALIDATING`, `COMMITTED`, `FAILED`, `ABORTED` for retry handling rather than guessing from HTTP status alone.

Never log raw file bytes, bearer tokens, full multipart bodies, unsanitized user filenames, or sensitive paths. A `broken pipe` from a user closing a browser tab is not automatically a 500 business failure requiring a page alert. Conversely, a sudden spike in client aborts can signal network issues, timeouts, or overly slow server responses.

Watch request correlation carefully: a proxy can reject a request **before the app logs anything**, so correlate ingress access logs with server/application metrics.

## 12. Decisions on Retries and Resumability

**Retrying the whole request** is simple yet safe only when the operation prevents duplicates, for example:

- Client sends an `Idempotency-Key` or stable upload token bound to identity and upload intent.
- Server tracks state by key: `IN_PROGRESS`, `COMPLETED`, `FAILED`, with TTL and concurrency controls.
- If a prior request committed, retry returns the **same stored result** or status; never write a second copy.
- Store checksum/object metadata to distinguish two requests reusing a key with different payloads.
- Large uploads use explicit chunk/resume protocols: exact offsets, chunk checksums, full-file verification, commit markers, and orphaned-chunk cleanup.

For downloads, simple retries from byte 0 may suffice for small files; large files benefit from range/resume downloads and verifying content remains unchanged across chunks. **Never send a `Range` header in a POST upload** expecting Spring Boot to treat it as a resumable upload.

## 13. Upload/Download API Design Checklist

1. Are **per-file, total request, part count, quota/rate, and timeout limits** explicitly aligned across proxy, container, Spring, and business rules?
2. Are **outer media type**, **part media type**, file signature, and true content structure all checked separately?
3. Are paths built from `getOriginalFilename()` avoided, and are incomplete uploads hidden from access?
4. Are temp files/commits driven by explicit states with cleanup on exception, cancel, and crash?
5. When a client loses a response, are there status-lookup APIs and idempotency keys to avoid duplicates?
6. Do download APIs set appropriate `Content-Length`, `Content-Type`, `Content-Disposition`, authorization checks, and checksum/range support where needed?
7. Are storage/antivirus/quota errors handled cleanly without prematurely returning 201?
8. Do handlers distinguish 413/400/415/422, and does monitoring account for proxy rejections bypassing the controller?
9. Do tests go through real networking/proxies for limit/abort cases instead of relying solely on `MockMvc`?
10. Do logs/metrics capture error categories and stages without leaking file contents or misclassifying client aborts as server bugs?

## 14. Self-Check Questions

**Scenario A:** Spring `max-file-size=20MB`, but ingress limits 5MB, and a 7MB upload fails. Can changing the controller fix it?

**Answer:** No. The proxy can block with 413 before the request reaches the controller. Adjust the **ingress limit** if policy permits, aligned with Spring limits.

**Scenario B:** Valid multipart body, file named `invoice.pdf`, part header says `application/pdf`, yet bytes start with `NOTPDF`. Should it be saved?

**Answer:** No. Client-supplied filename and MIME are not proof; the validator example returns 422 because the signature fails. Production should use deeper parsing/scanning.

**Scenario C:** Client sent nearly the entire file and abruptly lost network; the server never saw completion. Should the temp file be renamed to final and 201 returned?

**Answer:** No. The file has not been verified complete; abort/clean up, or retain chunks within an explicit stateful **resume protocol**. Once disconnected, returning 201/400 is not guaranteed anyway.

**Scenario D:** Server committed the file, client missed the 201, and client retries the same content. How do you avoid duplicates?

**Answer:** Idempotency key/upload ID + queryable status. The server resolves outcome by key and checksum regardless of whether the client received the response.

**Scenario E:** An `@RequestPart MultipartFile` endpoint ran on MVC; you migrate to WebFlux and configure `spring.servlet.multipart.max-file-size`. Is that sufficient?

**Answer:** No. WebFlux uses `FilePart`, its own multipart reader, and separate properties. Configure memory/disk/parts limits, business quotas, and cancellation-safe cleanup.

**Scenario F:** Download returned `200 OK` headers, and mid-stream the client closed the connection. Can you change the response to a 500 JSON error?

**Answer:** No. Once committed, response status and headers cannot change; the client may see a truncated file or socket error, while the server closes read resources and records the disconnect.

## 15. Official Documentation

- [Spring Boot — Uploading Files](https://spring.io/guides/gs/uploading-files/): Spring MVC multipart integration and `spring.servlet.multipart.max-file-size`, `max-request-size`.
- [Spring Boot 3.3 — MultipartProperties](https://docs.spring.io/spring-boot/docs/3.3.0-SNAPSHOT/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html): 1MB/file, 10MB/request defaults, location/threshold.
- [Spring Framework 6.1 — MaxUploadSizeExceededException](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/multipart/MaxUploadSizeExceededException.html): size exception in MVC.
- [Spring Framework — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): multipart reader, resource limits, `DataBuffer`, and cancellation.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html): Servlet/WebFlux multipart and codec settings.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics of 413, 415, 422, timeouts, and committed response constraints.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): multipart handling in Spring MVC.

**Remember:** resilient upload/download handling enforces limits early, validates actual content types, stages to temp and commits only on success, cleans up on errors and disconnects, and designs retries with idempotency. Never assume every failure flows through the controller or every aborted request receives an HTTP error response.
