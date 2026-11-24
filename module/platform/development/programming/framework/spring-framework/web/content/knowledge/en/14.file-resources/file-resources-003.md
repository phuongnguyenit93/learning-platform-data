# Size Limits, File Counts, File Types, and Untrusted Filenames in Spring MVC

## 1. Objectives and Scope

Uploading is not merely receiving a `MultipartFile` object and writing bytes to disk. The client controls the payload, filename, and many HTTP headers, and may intentionally send too many files, oversized files, spoofed formats, malformed metadata, or a document that expands to gigabytes when decoded. The API needs defense in depth to prevent resource exhaustion, file overwrites, path traversal, XSS, and data exposure.

This lesson focuses on **Spring MVC (Servlet stack), Java 17+, Spring Boot 3.x / Spring Framework 6.x**, covering:

- Distinguishing limits for a **single file**, a **multipart request**, **file/part counts**, quotas, and concurrency.
- Configuring `spring.servlet.multipart.max-file-size`, `max-request-size`, `file-size-threshold`, and the roles of the Servlet container and proxy.
- Checking `MultipartFile.isEmpty()`, `getSize()`, file type, magic bytes, and content via trusted parsers.
- Why `getContentType()` and `getOriginalFilename()` are **untrusted** data.
- Generating random storage keys, storing outside the webroot, handling rollback/cleanup, scanning/quarantine, and download authorization.
- Distinguishing HTTP 400/413/415 errors and where each error is detected.
- Building a runnable Spring Boot 3 example with curl, MockMvc, a test scenario matrix, and a production checklist.

**Security boundary:** The code example only accepts PNG/JPEG and checks magic bytes without an image decoder or antivirus; it is **not safe enough to automatically serve user images in production**. In real deployments, you must perform full file-structure validation, pixel/CPU bounds, re-encoding, malware scanning, and risk-based access control.

## 2. Path of a Multipart Upload

```text
Client: multipart/form-data
         |
         v
Reverse proxy / CDN / WAF
  [body bytes, rate limit, timeouts, connection limits]
         |
         v
Servlet container (Tomcat / Jetty / Undertow)
  [parse parts, temp space, header and part limits]
         |
         v
Spring multipart handling
  [MultipartConfigElement / StandardServletMultipartResolver]
  [spring.servlet.multipart.*]
         |
         v
Spring MVC controller
  @RequestParam("files") List<MultipartFile>
         |
         v
Application policy
  [1..3 files, no empty, <=2 MiB each]
  [allowlist type + signature + full format validation]
         |
         v
Private staging / AV / CDR / decoder / metadata
         |
         v
Private accepted storage, authorized download
         |
         v
JSON response with server-generated ID, never raw path
```

Each layer defends against a different problem. `max-file-size` does not replace a limit on the number of multipart parts; a `files.size()` check only runs **after the parser has processed the request**; antivirus alone does not replace rate limiting. Real systems need consistent limits from the edge to the service.

### Difference Between Files and Multipart Parts

A `multipart/form-data` request has many parts: files, text strings, hidden fields, and metadata. Many non-file parts still force the parser to consume RAM/CPU/disk. Therefore, a policy of "at most three files" is **different from** "at most three parts"; you must control both part count at the container and file count in the application.

## 3. MultipartFile: Which Values Are Trustworthy?

Controller example:

```java
@PostMapping(path = "/api/uploads",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @RequestParam("files") List<MultipartFile> files) {
    // Enforce policy in the service and store in a private area.
}
```

This is only a controller snippet; the full application follows later.

| API | Meaning | Things to note |
| --- | --- | --- |
| `getName()` | Parameter/part name, e.g., `files` | Do not use as a path |
| `getOriginalFilename()` | Name declared by the **client** | Untrusted, may contain `../` or backslashes |
| `getContentType()` | MIME declared by the client for the **part** | Easily spoofed, may be null |
| `getSize()` | Byte size received for the file | Must check, though already past parsing |
| `isEmpty()` | Empty or no file selected | Enforce policy if empty files are disallowed |
| `getInputStream()` | Byte stream of the uploaded file | Must close stream; avoid loading huge files onto heap |
| `transferTo(Path/File)` | Moves/copies part elsewhere depending on implementation | Only pass server-generated paths |

`getOriginalFilename()` is specifically warned about in the Spring Javadoc: it may contain path elements or malicious characters, so never use the raw name on the filesystem. Never use `getContentType()` as proof that the bytes are PNG/PDF. Headers are client-controlled.

`MultipartFile` is tied to the lifecycle of the multipart request. Do not hold this object in a background queue to read after the request finishes; if async scanning is needed, copy to a dedicated staging area and pass only the storage ID to the worker.

## 4. Configuring Limits in Spring Boot 3

```properties
spring.servlet.multipart.enabled=true

# Max 2 MiB per file
spring.servlet.multipart.max-file-size=2MB

# Max total multipart request 7 MiB
spring.servlet.multipart.max-request-size=7MB

# Threshold to spill multipart content to temp disk
spring.servlet.multipart.file-size-threshold=0B

# Custom property of the sample application
app.upload.directory=./private-uploads
```

Meaning:

- `max-file-size` limits each file in the multipart request; Boot 3.x default is typically **1MB**.
- `max-request-size` limits the entire request including file bytes, text fields, boundaries, and per-part headers; Boot 3.x default is typically **10MB**.
- `file-size-threshold` controls when data is written to disk; it is **not** an upload size limit.
- `spring.servlet.multipart.location` can specify the **temporary** directory for the multipart parser; do not confuse temp space with durable storage.
- `app.upload.directory` is a custom setting for this demo, not a built-in Spring Boot storage service.

If three files × 2MiB = 6MiB, a 7MiB request limit leaving room for overhead is a reasonable example for a lesson, **not a guarantee that every valid multipart request fits**. Filenames/field metadata and proxy overhead can change total bytes.

### Limits at the Edge and Servlet Container

A reverse proxy may reject bodies smaller than the Boot config. The container can have its own policies for multipart part counts, request parameters, header sizes, read timeouts, and temp storage directory. Configuration differs across Tomcat/Jetty/Undertow **and across versions**; do not invent a single property for all of them. Always consult the documentation for the exact server you run.

An app-level `getSize()` check does not stop the parser from reading a huge request before the service runs. Thus all three tiers—**gateway / multipart container / application**—should enforce ceilings.

## 5. Limiting File Count and Quotas

Example API contract: **1–3 files per request**. A post-parse check:

```java
if (files == null || files.isEmpty()) {
    throw rejected("At least one file is required");
}
if (files.size() > 3) {
    throw rejected("At most three files are allowed");
}
```

This is a snippet inside the service defined below. Counting files is useful for business rules, yet does not stop a request containing thousands of **text parts**. Production may also need:

- Multipart part/field count, max length per field, and total metadata bytes.
- File count and total bytes per user/day, per tenant, and total storage quota.
- Upload rate and concurrent request limits; timeouts for slow-sending clients.
- Concurrent decode/antivirus task limits; CPU/RAM/disk budgets.
- Item count and total bytes **after decompression**, preventing ZIP bombs.
- Pixel count and frame count for images/videos to stop tiny files from decoding into massive buffers.

These limits must live at the layer that actually sees them: the container does not know per-user business quotas, while a post-parse service cannot stop all parser costs.

## 6. File Type Validation: Extension, MIME, Signature, and Decoder

| Signal | Example | Reliability |
| --- | --- | --- |
| Original filename extension | `avatar.png` | Low: client can change it |
| `MultipartFile.getContentType()` | `image/png` | Low: client can spoof it |
| Magic bytes | PNG: `89 50 4E 47 0D 0A 1A 0A` | Preliminary check, still spoofable |
| Full decoding and validation | Safe image parser reads full structure | Stronger, still needs resource bounds |
| Re-encode/scan/CDR | Produce clean image or strip active content | Format-appropriate defense in depth |

### Magic Bytes Do Not Mean an Image Is Safe

PNG has an 8-byte signature, and JPEG typically starts with `FF D8 FF`. An 8-byte file with the exact PNG header and no image data passes a signature check without being a real image. A file with a valid header can still contain metadata, malformed chunks, or parser-exploit payloads.

In this demo, `detectSignature` only verifies that the leading bytes match an allowed format; it does **not** guarantee a valid PNG/JPEG. Production needs a full decoder, resolution/pixel/frame caps, decompression-bomb protection, re-encoding, and malware scanning tailored to risk.

Do not expand an allowlist to SVG, PDF, DOCX, ZIP, or EXE just by adding a few magic bytes. Each format brings active content, macros, archive entries, parser quirks, and distinct policies.

### Request Content-Type Differs From File Part MIME

The request `Content-Type: multipart/form-data` describes the envelope. `Content-Type: image/png` on an individual part is the client's declared file type. An endpoint with `consumes=multipart/form-data` receiving the wrong envelope typically returns **415 Unsupported Media Type**; if the multipart parses but a file part's bytes violate policy, the application may return **400 Bad Request**.

## 7. Untrusted Original Filenames

Strings that must never be used as file paths:

```text
../../etc/passwd
..\..\windows\system.ini
report.pdf.exe
avatar.PNG
.htaccess
CON
photo.jpg:payload
name%2e%2e%2fsecret.png
Very long name / confusing Unicode / control chars
```

Risks include path traversal, file overwrites, special device names, Windows Alternate Data Streams, collisions on case-insensitive filesystems, visually equivalent Unicode names, HTTP header injection via `Content-Disposition`, and XSS when displaying names in HTML.

**Safest strategy:** Generate a server-side storage key, and **never use getOriginalFilename to determine the path**. For example, `Files.createTempFile(privateRoot, "uploaded-", ".png")` after the server verifies the type. If you want to store the original name for display, keep it in separate metadata, restrict bytes/characters by policy, normalize Unicode, and escape per output context; never use it as an authorization key or extension source.

Simply calling `Paths.get(originalFilename).getFileName()` does not eliminate all risks: the name can still be a device name, overly long, colliding, or full of Unicode tricks and control characters. Never use the client name to save files even after stripping `../`.

## 8. Safe Storage and Lifecycle

Separate four logical zones:

1. **Temporary multipart space**: created by the container during parsing, temporary lifetime.
2. **Private staging/quarantine**: files received but not yet fully verified.
3. **Accepted private storage**: files that passed policy and scanning, with metadata/owner/tenant.
4. **Authorized delivery**: download API accepts an opaque ID, verifies permissions, and emits safe headers.

On a filesystem, use a directory **outside the webroot** and create no public static mapping to the upload directory. Only the application process should write to the required area without execute permissions; avoid any filesystem path under user control. On object storage, keep buckets/objects private by default; consider short-lived presigned URLs only after authorization and scanning.

When a failure occurs mid-way through multiple files, delete all files created during the request. If the application crashes or a DB commit fails, run a cleanup/orphan-reconciliation job because filesystems and databases do not share an ACID transaction. Unscanned uploads must never be publicly served.

## 9. Example API Contract

```text
POST /api/uploads
Content-Type: multipart/form-data
1..3 file parts sharing name = "files"
Each file non-empty, max 2 MiB
Only PNG/JPEG allowed by preliminary signature
When part MIME is declared, it must match signature
Stored filename is server-generated; never expose raw path
```

Example success JSON (`id` and `size` are illustrative):

```json
{
  "files": [
    {
      "id": "uploaded-483927102931.png",
      "mediaType": "image/png",
      "size": 1024
    }
  ]
}
```

The demo returns HTTP `201 Created` once files are stored privately under the preliminary policy; `id` is an internal storage key, **not a public URL**. In systems requiring async scanning, you can return `202 Accepted` + a job ID and pending status before allowing downloads.

## 10. Runnable Spring Boot 3 Java 17+ Application

Create a Spring Initializr Maven project with Java 17+, `spring-boot-starter-web`, and `spring-boot-starter-test` (test scope). No database needed. Files are placed in package `com.example.demo`:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  UploadRejectedException.java
  UploadService.java
  UploadController.java
  UploadExceptionHandler.java
src/main/resources/application.properties
src/test/java/com/example/demo/UploadControllerTest.java
```

### 10.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 10.2. UploadRejectedException.java

```java
package com.example.demo;

import org.springframework.http.HttpStatus;

public class UploadRejectedException extends RuntimeException {
    private final HttpStatus status;

    public UploadRejectedException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
```

This exception represents only **policy-rejected input**. An `IOException` while writing to disk must not be blindly converted into HTTP 400, because that may be a server failure.

### 10.3. UploadService.java

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class UploadService {

    private static final int MAX_FILES = 3;
    private static final long MAX_FILE_BYTES = 2L * 1024 * 1024;
    private static final byte[] PNG_MAGIC = {
        (byte) 0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };

    private final Path root;

    public UploadService(Environment environment) {
        String directory = environment.getProperty(
                "app.upload.directory", "./private-uploads");
        this.root = Path.of(directory).toAbsolutePath().normalize();
    }

    public List<UploadedFile> store(List<MultipartFile> files)
            throws IOException {

        if (files == null || files.isEmpty()) {
            throw rejected("At least one file is required");
        }
        if (files.size() > MAX_FILES) {
            throw rejected("At most three files are allowed");
        }

        // Validate the entire list before creating stored files.
        List<Kind> types = new ArrayList<>();
        for (MultipartFile file : files) {
            if (file.isEmpty()) {
                throw rejected("Empty files are not allowed");
            }
            if (file.getSize() > MAX_FILE_BYTES) {
                throw new UploadRejectedException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Each file must be at most 2 MiB");
            }

            // Never use getOriginalFilename() as a file path.
            Kind kind = detectSignature(file);
            String declared = file.getContentType();
            if (declared != null && !declared.isBlank()
                    && !kind.mediaType().equals(
                        declared.toLowerCase(Locale.ROOT))) {
                throw rejected(
                    "Declared type does not match detected type");
            }
            types.add(kind);
        }

        Files.createDirectories(root);
        List<Path> created = new ArrayList<>();
        List<UploadedFile> results = new ArrayList<>();

        try {
            for (int i = 0; i < files.size(); i++) {
                Kind kind = types.get(i);
                Path destination = Files.createTempFile(
                        root, "uploaded-", "." + kind.extension());
                created.add(destination);

                try (InputStream in = files.get(i).getInputStream()) {
                    Files.copy(in, destination,
                            StandardCopyOption.REPLACE_EXISTING);
                }

                results.add(new UploadedFile(
                    destination.getFileName().toString(),
                    kind.mediaType(), Files.size(destination)));
            }
            return List.copyOf(results);
        } catch (IOException | RuntimeException error) {
            for (Path path : created) {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException cleanupError) {
                    error.addSuppressed(cleanupError);
                }
            }
            throw error;
        }
    }

    private Kind detectSignature(MultipartFile file) throws IOException {
        byte[] header;
        try (InputStream in = file.getInputStream()) {
            header = in.readNBytes(8);
        }

        if (Arrays.equals(header, PNG_MAGIC)) {
            return new Kind("image/png", "png");
        }
        if (header.length >= 3
                && (header[0] & 0xFF) == 0xFF
                && (header[1] & 0xFF) == 0xD8
                && (header[2] & 0xFF) == 0xFF) {
            return new Kind("image/jpeg", "jpg");
        }
        throw rejected("Only PNG and JPEG signatures are permitted");
    }

    private UploadRejectedException rejected(String message) {
        return new UploadRejectedException(
                HttpStatus.BAD_REQUEST, message);
    }

    private record Kind(String mediaType, String extension) {}

    public record UploadedFile(
            String id, String mediaType, long size) {}
}
```

Code analysis:

- At most three `MultipartFile` items and at most 2MiB/file; total part count for the request requires a separate container limit.
- `getSize()` provides defense in depth **after** the parser; the parser enforces configured max sizes.
- `detectSignature` reads up to the first 8 bytes and performs a preliminary PNG/JPEG check. **It does not validate the whole image.**
- The client-declared part MIME is only cross-checked as an extra condition, never trusted to establish safety.
- Never reads the original filename or uses the client extension to construct destination paths.
- `Files.createTempFile` generates a server-side name strictly inside the server-controlled directory.
- `Files.copy` writes to the newly created temp file; `REPLACE_EXISTING` here writes only to a file **the server just created**, never overwriting a client-chosen path.
- If copying fails, it attempts to delete all files created in the request; periodic cleanup is still needed for crashes or DB failures.
- The code does not set explicit permissions or guard against adversarial symlinks inside the directory: production must manage ownership, use a private volume, and ensure other users cannot modify the directory.
- Storage failures can still happen in the service, in which case you must not return "file type invalid" but log and report an appropriate system error.

**Do not expose this sample directly on the Internet as a public API without full authn/authz/quotas/scanning/decoding.** Returning an upload ID does not mean the file is ready for download.

### 10.4. UploadController.java

```java
package com.example.demo;

import java.io.IOException;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final UploadService service;

    public UploadController(UploadService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UploadResponse> upload(
            @RequestParam("files") List<MultipartFile> files)
            throws IOException {

        List<UploadService.UploadedFile> saved = service.store(files);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadResponse(saved));
    }

    public record UploadResponse(
            List<UploadService.UploadedFile> files) {}
}
```

The controller handles HTTP status and JSON, and never accepts a user-supplied storage path. If the required `files` part is missing completely, Spring MVC can reject with 400 during argument resolution **before the service runs**.

### 10.5. UploadExceptionHandler.java

```java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadExceptionHandler {

    @ExceptionHandler(UploadRejectedException.class)
    public ResponseEntity<ApiError> rejected(
            UploadRejectedException ex) {
        return ResponseEntity.status(ex.getStatus())
                .body(new ApiError(
                    "UPLOAD_REJECTED", ex.getMessage()));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiError> oversized(
            MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(new ApiError(
                    "UPLOAD_TOO_LARGE",
                    "Multipart request exceeds configured limits"));
    }

    public record ApiError(String code, String message) {}
}
```

If a multipart parsing exception reaches the MVC resolver, this advice can return 413. If a proxy or container rejects **before `DispatcherServlet`**, the advice cannot catch the original error: the response body may differ or the connection may be closed. Do not catch all `Exception` types and return 400; disk-full/IO errors belong to infrastructure failures.

### 10.6. application.properties

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=7MB
spring.servlet.multipart.file-size-threshold=0B
app.upload.directory=./private-uploads
```

`./private-uploads` is for the demo only. Production uses a dedicated volume outside the webroot, restricted process permissions, scanning, and cleanup.

### 10.7. Running the Application

```bash
./mvnw spring-boot:run
```

PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

This command requires a Maven Boot project with wrappers and dependencies; do not run `javac UploadService.java` standalone without the Spring classpath.

## 11. curl: Testing Uploads and Errors

### 11.1. One PNG File

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@photo.png;type=image/png"
```

If `photo.png` is a small file with a PNG signature, the app returns 201 and JSON with `files[0].id`, `mediaType`, and `size`. Do not assert a random ID. The demo does not decode the entire image yet.

### 11.2. Two Files

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.jpg;type=image/jpeg"
```

Repeat the same part name `files` to populate `List<MultipartFile>`. Do not manually set a boundary header when using `curl -F`; curl generates the matching boundary itself.

### 11.3. Disallowed Type

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@notes.txt;type=text/plain"
```

If bytes do not match PNG/JPEG signatures: `400 Bad Request` with `UPLOAD_REJECTED`. Renaming the extension/MIME to png does not turn the bytes into an image, though an attacker can also forge magic bytes; that is why decoders and scanners are required.

### 11.4. Four Files in One Request

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.png;type=image/png"
```

If the request stays below multipart limits, the service returns **400** because count >3. If total bytes exceed `max-request-size`, the parser/gateway may reject early with 413. Do not rely on processing order to assume four files always yield 400.

### 11.5. File >2MiB

A request with an oversized file may be blocked by the multipart parser before the controller, typically HTTP **413** via the corresponding framework/container mapping. With `MockMultipartFile` in MockMvc, parser limits are not fully simulated; the service size check can still be tested separately.

### 11.6. Wrong Request Content-Type

```bash
curl -i http://localhost:8080/api/uploads \
  -H "Content-Type: application/json" \
  --data '{"files":[]}'
```

Typically **415** because the endpoint only accepts `multipart/form-data`. Do not confuse the envelope media type with each part's `image/png`.

## 12. MockMvc Testing

Create `src/test/java/com/example/demo/UploadControllerTest.java` in a project with `spring-boot-starter-test`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.upload.directory=./target/test-private-uploads",
    "spring.servlet.multipart.max-file-size=2MB",
    "spring.servlet.multipart.max-request-size=7MB"
})
@AutoConfigureMockMvc
class UploadControllerTest {

    @Autowired MockMvc mvc;

    private static final byte[] PNG_HEADER = {
        (byte) 0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };

    private MockMultipartFile png(String filename) {
        return new MockMultipartFile(
            "files", filename, "image/png", PNG_HEADER);
    }

    @Test
    void serverNameDoesNotUseClientPath() throws Exception {
        mvc.perform(multipart("/api/uploads")
                .file(png("../../client-name.png")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.files[0].mediaType")
                .value("image/png"))
            .andExpect(jsonPath("$.files[0].id",
                not(containsString("client-name"))));
    }

    @Test
    void rejectsFourFiles() throws Exception {
        mvc.perform(multipart("/api/uploads")
                .file(png("a.png"))
                .file(png("b.png"))
                .file(png("c.png"))
                .file(png("d.png")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("UPLOAD_REJECTED"));
    }

    @Test
    void rejectsSpoofedMime() throws Exception {
        MockMultipartFile fake = new MockMultipartFile(
            "files", "photo.png", "image/png",
            "not a PNG".getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/uploads").file(fake))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
            "files", "empty.png", "image/png", new byte[0]);

        mvc.perform(multipart("/api/uploads").file(empty))
            .andExpect(status().isBadRequest());
    }

    @Test
    void applicationRejectsOverTwoMiB() throws Exception {
        MockMultipartFile huge = new MockMultipartFile(
            "files", "large.png", "image/png",
            new byte[2 * 1024 * 1024 + 1]);

        mvc.perform(multipart("/api/uploads").file(huge))
            .andExpect(status().isPayloadTooLarge());
    }
}
```

Run:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

**Test limitations:** `PNG_HEADER` is only 8 bytes, not a complete PNG image. These tests verify **preliminary policy logic** (not full file-format security). When adding a decoder, use valid image fixtures and corrupted files in tests. MockMvc does not replace container multipart limits; testing app-layer oversized checks differs from testing parser/proxy 413 responses.

Test files are stored under `target/test-private-uploads`; Maven `clean` can wipe `target`, or use a dedicated volume/temp folder in CI. With Spring Security, you must add mock identity and an appropriate CSRF token: HTTP 403 can occur before the controller.

## 13. Where Must Real HTTP Testing Happen?

An HTTP integration test through embedded Tomcat/Jetty or staging ingress should cover:

- Invalid or missing multipart boundaries; mid-request disconnects.
- `max-file-size` and `max-request-size` at the parser (not only in the service).
- Very high total multipart part counts even with few files.
- Proxy body limits, timeouts, and slow-uploading clients.
- Full temp disk; unwritable directory.
- Unusual/oversized headers, filenames with control characters/Unicode.
- Concurrent uploads exceeding rate/quota limits.
- Scanner/decoder failures or timeouts.
- Error responses occurring before `@RestControllerAdvice` can run.

You can use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with a real HTTP client, or start the app and run `curl` from a test harness. When a reverse proxy exists, test through the **exact production ingress**; calling loopback alone bypasses many policies.

## 14. When Serving Uploaded Files

Uploading to private storage does not mean a file is safe to serve. When adding a download/preview API:

1. Map an opaque ID to server-side metadata and path; never use client-sent names to construct paths.
2. Authenticate the user and **check permissions on the specific file/tenant** at download time.
3. Never expose the upload directory via a public static resource mapping.
4. Allow downloads only after the file has passed validation/scan policies; enforce a quarantine state.
5. Set `Content-Type` from the **verified** type, never trusting the upload request's MIME.
6. Use `Content-Disposition: attachment` for formats capable of active content; encode header filenames safely and never inject raw control characters.
7. Consider `X-Content-Type-Options: nosniff` and CSP/an isolated origin.
8. For images meant to render inline, prefer decoding/re-encoding before serving.
9. Design cache policies appropriate for private data; avoid arbitrary public caching.
10. Implement cleanup/retention and abuse reporting.

A random filename does not replace authorization. IDs can leak via logs, browser history, or shared links; private resources still require permission checks on every request.

## 15. Attack Scenarios and Defense Layers

| Scenario | Risk | Verification / Defense |
| --- | --- | --- |
| 20MB file sent to 2MB-max API | Bandwidth/temp exhaustion | Parser and edge size limits |
| 500 1KB files | Too many files | App file count + container part count |
| 1 file and 10,000 text fields | Too many multipart parts | Container/parameter limits |
| `avatar.png.exe` | Double extension | Ignore raw name, allowlist |
| `../../secret` | Path traversal | Server-generated key, private root |
| `image/png` with text bytes | MIME spoofing | Signature + decoder |
| Valid PNG magic with invalid body | Header spoofing | Full image decoding/re-encode |
| 100KB ZIP decompressing to 10GB | Decompression bomb | Uncompressed bytes, entry/depth limits |
| 5KB image declaring 100000×100000 pixels | Image bomb | Pixel cap and CPU/memory budget |
| PDF containing JavaScript | Active content | Restrict format, sanitize/CDR/sandbox |
| Ultra-long filename / Unicode trick | Metadata/FS confusion | Ignore in path, validate metadata |
| Same name 100 times | Overwrite | Random unique generated path |
| Concurrent uploads from many clients | Resource exhaustion | Rate, quota, concurrency limits |
| DB insert fails after saving file | Orphan file | Compensating cleanup |
| Interrupted upload | Temp leftovers | Lifecycle expiry/cleanup |
| File made public immediately upon receipt | Malware/XSS | Private quarantine + approval |
| Unauthorized download | Data exposure | Ownership/tenant checks |

No single "valid file extension" check replaces defense in depth.

## 16. Production File Inspection Architecture

It can be divided into checkpoints:

**Pre-multipart-parsing checkpoint:** gateway/container bounds bytes, timeouts, part counts, rates, and connections.

**Post-parse checkpoint:** service enforces file count/empty/size/type/metadata limits and user quotas; never uses client filenames as paths.

**Quarantine checkpoint:** file goes to private staging, undergoes full decoding, pixel/resource caps, malware scanning, CDR/re-encoding, and timeouts. A failing scanner should not default to allowing the file.

**Publish checkpoint:** only policy-compliant files move to accepted/private storage with owner, scan status, checksum, and retention. If database and filesystem updates partially fail, cleanup/reconciliation is required.

**Download checkpoint:** authenticate, authorize, set safe headers/content disposition, and enforce rate and cache policies.

If scanning is asynchronous, the response can use HTTP `202 Accepted` with a job ID and pending status, without implying the file is already downloadable. Queues should carry only the storage key and required metadata, never holding `MultipartFile`/`ServletRequest` past the HTTP lifecycle.

## 17. Why Uploaded Byte Size Alone Is Not Enough to Bound Resources

A small file can become huge or extremely CPU-intensive after analysis:

- Tightly compressed ZIPs, deep directory hierarchies, nested archives.
- Images with abnormal pixel dimensions or oversized metadata chunks.
- Complex PDFs with fonts/vectors/embedded objects that exhaust parser RAM.
- Video codecs/bitstreams causing extreme CPU decode costs.
- HTML/SVG/scripts containing active content, creating browser risks if rendered inline.

Enforce budgets **after decompression/decoding** and cap parser/AV concurrency. Never call `MultipartFile.getBytes()` on large files across many concurrent requests when streaming is possible. Account for both stored bytes and processing cost in quotas.

## 18. HTTP Errors and Exceptions

| Error | Common status | Where detected |
| --- | --- | --- |
| Missing file part | 400 | MVC argument binding |
| Empty file / too many files | 400 | Service policy |
| Disallowed file type | 400 per demo | Service policy |
| File exceeds size in service | 413 | Service policy |
| Multipart request too large | Usually 413 | Parser/exception resolver |
| Proxy rejects body | Possibly 413 / connection close | Edge |
| Wrong envelope Content-Type | 415 | MVC request mapping |
| Missing authentication/authorization | 401/403 | Security filters |
| Disk full / staging failure | 500 or designed server status | Storage/infrastructure |
| Async scan not finished | 202 (if designed) | Workflow |
| Malformed multipart syntax | Usually 400, parser-dependent | Container/framework |

A single request can violate multiple conditions. Never assume "file count is always checked before file size": the parser or edge may reject before the service runs. Default error JSON bodies also vary across Tomcat/Boot/advice/proxies.

## 19. Common Anti-Patterns

1. Checking `getSize` only in the controller; too late for earlier parser costs.
2. Lacking an app file-count limit and a container part-count limit.
3. Setting `max-request-size = max-file-size × file count` exact; forgetting multipart overhead.
4. Treating client-declared `Content-Type` as real proof.
5. Trusting original `.png` extensions while skipping magic bytes and decoders.
6. Checking only magic bytes and bypassing scans; malformed files can still have valid headers.
7. Using `getOriginalFilename` to build directories or paths.
8. Only stripping `../` and trusting the rest of the filename.
9. Storing uploads inside the webroot or granting execute permissions.
10. Placing raw filenames in response headers without escaping.
11. Allowing downloads before scanning finishes.
12. Leaving parser quotas, concurrency, or CPU time unbounded.
13. Failing to check uncompressed bytes or pixel dimensions.
14. Logging raw multipart bodies, tokens, and sensitive filenames.
15. Assuming a request without `Content-Length` is safe.
16. Calling `MultipartFile.getBytes()` on many large files, causing heap pressure.
17. Failing to clean up temp/orphan files after errors or crashes.
18. Skipping download authorization just because filenames are randomized.
19. Catching all exceptions as 400, hiding disk-full/IO errors.
20. Relying on MockMvc as proof of parser/gateway size limits.
21. Using async callbacks to read `MultipartFile` after the request lifecycle.
22. Lacking scan state/versioning policies for new file formats.

## 20. Pre-Production Checklist

### HTTP and System

- [ ] `consumes=multipart/form-data` and endpoints have authentication/authorization.
- [ ] Max file bytes, max multipart request bytes, part counts, and field limits defined at gateway/container/app.
- [ ] User/tenant quotas, rates, and concurrency bounded.
- [ ] Dedicated temp disk, sufficient quota, timeouts, cleanup, and tight permissions.
- [ ] HTTP integration tests for size limits, malformed boundaries, 413/415, and edge policies.

### Content and Metadata

- [ ] File count, empty check, per-file size, and business rules validated.
- [ ] Format allowlist per business need; never trust client extension/MIME.
- [ ] Magic bytes **and** full decoder/parser/scan matching the risk profile.
- [ ] Caps on pixels, frames, uncompressed bytes, CPU/memory/time.
- [ ] Never use `getOriginalFilename()` as a path or storage key.
- [ ] Original name metadata, if stored, is normalized, length-bounded, and escaped.
- [ ] Malware scanning/quarantine/CDR or re-encoding as needed.

### Storage and Download

- [ ] Dedicated storage, not public webroot, no execute permissions.
- [ ] Server-generated object ID, collision-safe and non-overwriting.
- [ ] Owner/tenant/status/expiry tracked, transactional cleanup, and orphan sweeper.
- [ ] Downloads always authorized and emit appropriate `Content-Type`/`Content-Disposition`/`nosniff`.
- [ ] Never expose content while scanning is incomplete.
- [ ] Logging and error responses leak no paths, exceptions, or sensitive data.
- [ ] Test abuse, traversal, malformed content, and multi-tenant access.

## 21. Self-Check Exercises

**1.** How does `max-file-size` differ from `max-request-size`?

**Answer:** One limits each individual file, while the other limits the entire multipart request including bytes and overhead. Neither replaces the other.

**2.** Does `files.size() <= 3` limit all multipart parts?

**Answer:** No; other text parts can still be numerous. Container/parser limits are required.

**3.** Is the MIME from `MultipartFile.getContentType()` trustworthy?

**Answer:** No. It is sent by the client; you need allowlists, signatures, and real content inspection.

**4.** Are 8 PNG magic bytes at the start of a file enough to certify safety?

**Answer:** No. They can be spoofed, corrupted, or malicious; full decoding and resource limits are needed.

**5.** When the filename is `../../secret`, what should you do?

**Answer:** Never use the original name as a path. Generate a server-decided key in private storage; if storing the original name as metadata, sanitize and control it separately.

**6.** When uploading four small files, why might you see 413 instead of 400?

**Answer:** The parser or gateway may reject the request based on total bytes before the controller counts the files.

**7.** Can a large `MockMultipartFile` test Tomcat's `max-file-size`?

**Answer:** Not fully. It tests the app check; you must run real HTTP tests to verify the parser/container.

**8.** Should disk-full errors be mapped to 400?

**Answer:** No; that is a system error requiring a server error response, cleanup, and telemetry.

**9.** Is a random filename enough to protect a download API?

**Answer:** No. You still must verify the user/tenant, scan status, and read permissions.

**10.** If a scanner runs in the background, what should the API return?

**Answer:** It can return `202` + a job ID/pending state per the contract, without letting the client download the file until it passes.

## 22. References

- Spring Boot 3 MultipartProperties: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html
- Spring Framework 6.2 MultipartFile Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- Spring Framework Multipart Resolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- Spring Framework multipart form arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Framework MVC error responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Unrestricted File Upload: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload
- RFC 7578 multipart/form-data: https://www.rfc-editor.org/rfc/rfc7578.html
- Jakarta Servlet specification: https://jakarta.ee/specifications/servlet/
