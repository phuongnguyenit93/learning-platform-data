# Validating Filenames, Content Types, and Storage Paths When Uploading Files in Spring Boot

> **Scope:** Within the **File upload and download** group of **Spring Boot - web-runtime**, this lesson shows how to treat multipart uploads as untrusted input, validate filenames, content types, and target directories, prevent overwrites or arbitrary paths, and manage resource limits. The hands-on example uses **Spring Boot 4.1.2**, **Java 17+**, Maven, and **Spring MVC**. The protection principles apply to WebFlux/object storage; file ingestion APIs differ across stacks.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish `MultipartFile.getOriginalFilename()`, `MultipartFile.getContentType()`, filename extensions, **file signatures (magic bytes)**, and actual data structure.
2. Recognize **path traversal**, spoofed names, double extensions, file overwrites, symlinks, public paths, and storing executable files.
3. Design an **allowlist** for names/formats, generate storage names using server-issued UUIDs or IDs, and control storage locations with `Path`.
4. Set limits on request size, per-file size, decoded content, and resource quotas; distinguish the multipart parser's temporary storage from durable storage.
5. Build a runnable endpoint accepting PNGs that checks declared MIME, byte signature, size, and decoded content, then **re-encodes** before saving a new file.
6. Analyze remaining constraints: antivirus, file scanning, access control, downloads, PDF/Office documents, ZIP, SVG, decode overload, and file–database consistency.

## 1. Trust Boundary of multipart/form-data

When a browser or API client sends:

~~~http
POST /api/images/upload HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=----demo

------demo
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

[binary file data]
------demo--
~~~

both `filename="avatar.png"` and `Content-Type: image/png` on the **multipart part** are controlled by the client. Spring MVC exposes these two values via `MultipartFile`, yet receiving the data **does not automatically make them trustworthy**. A client can declare `image/png` for a script file, a malformed file, or a polyglot file.

Distinguish three levels:

| Level | Example | Meaning |
| --- | --- | --- |
| **Client declaration** | `filename="avatar.png"` and `Content-Type: image/png` | Input for preliminary filtering, **can be spoofed** |
| **Verified format** | PNG magic bytes, parser accepts PNG, valid dimensions | Stronger evidence of file type; does not mean malware-free |
| **Server-managed identity and permissions** | Random ID, private storage path, per-user/tenant permissions | Decides which file is saved and who may read it later |

Recommended processing pipeline:

~~~text
HTTP client
   |
   v
Gateway / Reverse proxy
   +-- authentication, request-body limit, rate limit (if configured)
   |
   v
Servlet multipart parser
   +-- spring.servlet.multipart.max-file-size
   +-- spring.servlet.multipart.max-request-size
   +-- server memory / temporary disk
   |
   v
@RestController receives MultipartFile
   |
   +-- Check user permissions and quota
   +-- Check original filename (metadata only)
   +-- Check declared Content-Type (untrusted data)
   +-- Bounded read of bytes and verify magic bytes
   +-- Parse actual content with an appropriate parser
   +-- Enforce dimensions/pages/entries/CPU/RAM limits
   +-- Scan or re-encode if file type permits
   +-- Generate server-side storage name
   +-- Write to private storage with CREATE_NEW
   +-- Record metadata: owner, type, size, status
   |
   v
HTTP 201 + opaque ID (never return absolute path)
~~~

**No single check is enough:** extension, MIME, signature, decoder, directory outside webroot, scanning, and authorization are complementary layers of defense.

### Semantics of Spring APIs

- `MultipartFile.getName()`: the **form field** name for the file, such as `"file"`, not the original filename.
- `MultipartFile.getOriginalFilename()`: client-supplied filename, which can be `null` or empty; Spring docs warn it may contain paths and `..` sequences.
- `MultipartFile.getContentType()`: client-declared part media type, which can be `null`.
- `MultipartFile.getSize()`: size of the file part provided by the multipart parser.
- `MultipartFile.getInputStream()`: reads actual bytes; manage the stream and never read unboundedly into heap.
- `MultipartFile.transferTo(...)`: can transfer content into a target file, yet **does not perform** the application's validation, anti-path-traversal, content scanning, or overwrite-prevention policies.

Do not confuse `multipart/form-data` (Content-Type of the **entire request**) with `image/png` (Content-Type of the **part**).

## 2. Filenames: Validate Metadata, Never Use for Storage Names

### 2.1. Dangerous Filename Patterns

~~~text
../../application.properties
..\..\secret.txt
/var/app/config.yaml
C:\Windows\temp\evil.exe
file.png.exe
report.pdf.jsp
photo.php%00.png
avatar.png:alternate-stream
NUL.png
CON.png
.
..
photo.png.
photo.png 
dir/photo.png
dir\photo.png
Profile photo.png
PHOTO.PNG
~~~

Risks include:

- **Traversal:** `../` and `..\` can escape the intended directory if concatenated directly into a path. On Windows, UNC paths and drive letters also apply.
- **Double extension:** checking `.png` anywhere in the string mistakenly accepts `file.png.exe`; use an allowlist for the **final extension** together with a parser.
- **Null/control/encoded characters:** multi-layer encoding or NUL bytes may be interpreted differently across libraries; never “patch” via simple `replace("../", "")` calls.
- **Device and special names:** `CON`/`NUL`, colons, control characters, trailing dots or spaces have special meanings on certain filesystems.
- **Unicode:** NFC/NFD normalization differences, homoglyphs, case-insensitivity, or byte-length limits can cause collisions.
- **Valid localized names:** `Profile photo.png` may suit UX, yet should not become the literal filename on disk; if displayed, store as separate metadata and escape for HTML/HTTP headers.

**Recommended policy:** enforce a filename allowlist when giving helpful errors to clients, yet **always use a server-generated storage name**, even when the filename passes validation.

### 2.2. Why Taking Only the Basename Is Not Enough

The following does not solve the full problem:

~~~java
// Illustrates a common approach; do not use as an upload write path.
String original = file.getOriginalFilename();
String base = Path.of(original).getFileName().toString();
Path destination = uploadRoot.resolve(base);
~~~

`Path.getFileName()` follows the host OS's semantics: `\` is a separator on Windows, not always on Linux; `Path.of(...)` may throw on illegal characters. Even if it yields `avatar.png`, a file with that name may already exist and get overwritten. Special names, symlinks, and races remain. The better approach is **never using the original name as a target path component**.

If the app must preserve original names in metadata, normalize Unicode to NFC, cap byte length and allowed characters, and display only after context-appropriate escaping. Never drop raw original names straight into logs, HTML, or `Content-Disposition` without handling.

### 2.3. Using Random, Server-Formatted Filenames

~~~text
originalFilename (metadata): "avatar.png"
storedFilename (server ID):   "1bc30dd3-c831-4c3c-9c68-ac3b17de6515.png"
storageRoot (config trusted): /srv/app/private-uploads
absolute storedPath:         /srv/app/private-uploads/1bc30dd3-c831-4c3c-9c68-ac3b17de6515.png
client-visible ID:           1bc30dd3-c831-4c3c-9c68-ac3b17de6515.png
~~~

UUID makes collision probability negligible, yet `CREATE_NEW` is still needed to prevent overwriting any existing file. UUID is only an **identifier**, not proof the user is authorized to download the file. Database metadata should track owner, tenant, verified media type, size, checksum if needed, and scan status.

## 3. Multi-Layer Content Type Verification

### 3.1. Feature-Specific Allowlists

Accept only the exact formats required by the feature—for example, avatars only allow `.png` and `.jpg`. If you do not genuinely need SVG, HTML, Office, ZIP, PHP, JSP, EXE, etc., do not enable them. Blocklisting a handful of dangerous extensions fails to cover every executable variant.

For a **PNG-only** feature, the check order can be:

1. Filename matches syntax/length rules and ends with `.png` (case-insensitive policy).
2. Declared part MIME is `image/png`, used only for early rejection.
3. Byte signature matches PNG.
4. Image parser can actually read it, confirming format and valid dimensions.
5. Where possible, decode to a raster image and re-encode into a fresh PNG.
6. Use server-generated `UUID.png` and write only into private storage.

### 3.2. File Signatures (Magic Bytes)

| Type | Common Signature | What Remains Unverified |
| --- | --- | --- |
| PNG | `89 50 4E 47 0D 0A 1A 0A` | Chunk/CRC structure, pixel dimensions, parser safety, trailing payloads |
| JPEG | `FF D8 FF` | Decoder/EXIF/ICC, image integrity |
| GIF | `GIF87a` or `GIF89a` | Frames/animation, decoded dimensions |
| PDF | `%PDF-` usually at start | Embedded content, JavaScript, objects, malicious payloads |
| ZIP | Signature variants like `PK 03 04` | Entries, decompression bombs, Zip Slip, inner payload types |
| OOXML Office | ZIP container with specific entries | Not every ZIP is a valid DOCX/XLSX |

A file with a valid signature can still be corrupted, carry appended data, or be a **polyglot** (valid under multiple formats). Dedicated parsers/decoders, limits, and scanning remain essential.

### 3.3. Declared MIME vs. Served MIME

The upload part's Content-Type can be spoofed by the client, for example:

~~~bash
curl -F "file=@payload.txt;filename=photo.png;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Sending `image/png` in the HTTP request does not turn text into a PNG. Conversely, on download, the backend must **derive response Content-Type from server-verified metadata**: never echo back the raw `getContentType()`.

### 3.4. Parsers and Resource Limits

Using an image decoder is a much stronger verification layer than magic bytes. However, a tiny compressed image can decode into a massive bitmap. Check:

- File size before/after parsing; re-encoded output can be larger than input.
- Width, height, and total pixels; frame count for GIF/multi-page images.
- Decode time, CPU, heap, concurrent uploads; keep decoder libraries patched.
- Metadata rules (EXIF, color profiles, orientation) and whether truncated/corrupt files are rejected.
- Antivirus or content disarm when accepting files that cannot be safely re-encoded.

Never promise that an extension regex or a set of magic bytes suffices to stop malware.

## 4. Storage Paths: Trusted Root, Fresh Generated Name, No Overwrites

### 4.1. Lexical Path Traversal Prevention

If you must compute a path from an ID, check `normalize()`/`startsWith()`:

~~~java
// Illustrative; root is an admin-managed and previously protected absolute Path.
Path target = root.resolve(candidateName).normalize();
if (!target.getParent().equals(root)) {
    throw new SecurityException("Invalid target path");
}
~~~

Lexical checks alone are **insufficient** if an attacker can create or swap symlinks or ancestor directories. For normal uploads, the destination name is wholly server-generated without separators, avoiding any client-supplied path component.

### 4.2. Symlinks and TOCTOU

If an untrusted actor has write access to the directory, they can plant a symlink or swap a directory between check time and open time (**time-of-check to time-of-use**). `Path.normalize()` does not follow symlinks, and `toRealPath()` only reflects state at the moment of the call rather than locking the filesystem permanently.

Operational rules:

- Create a private directory owned by the service account/administrator with least-privilege permissions.
- Never allow untrusted processes to modify the directory or its parents (especially on shared hosts).
- Use `StandardOpenOption.CREATE_NEW` to create new files; when the threat model includes local adversaries, use platform-appropriate directory-relative safe opens or object-store policies.
- Never automatically grant web-readable access to every file in storage.
- Enforce quotas and alerts for disk-full, read-only filesystems, and permission drift.

### 4.3. Distinguishing Temporary Storage from Long-Term Storage

Spring MVC's multipart parser may buffer uploaded data in RAM or temporary files, deleting it when the request finishes. `spring.servlet.multipart.location` is only a **temporary location**, not business storage. The app must validate and write to its own storage.

If storing in object storage such as S3, Blob Storage, or GCS, the same principles hold: private bucket, server-generated keys, never let clients pick arbitrary buckets/keys, IAM policies, checksums, and scan states. With presigned uploads, enforce content-length/type conditions upfront and **re-verify post-upload** before publishing.

## 5. Size Limits and Resource-Exhaustion Attacks

Spring Boot supports:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
~~~

- `max-file-size` limits each individual file part.
- `max-request-size` limits the entire multipart request including parts and overhead.
- Reverse proxies, load balancers, and web servers add upstream limits.
- The service should still read streams with a bound for defense-in-depth, and enforce per-user/tenant quotas.

In Java 17:

~~~java
// Illustrative snippet inside a service method; MAX_BYTES is app-chosen.
try (InputStream in = file.getInputStream()) {
    byte[] data = in.readNBytes(MAX_BYTES + 1);
    if (data.length > MAX_BYTES) {
        throw new ResponseStatusException(
                HttpStatus.PAYLOAD_TOO_LARGE, "Upload too large");
    }
}
~~~

By the time the controller executes, the Servlet multipart parser may already have received/spooled the data. Therefore **parser and proxy limits** should be enabled upfront to curb resource consumption from huge requests.

Limits on **decoded/decompressed size** matter just as much as original file limits. A 100 KiB image can expand to millions of pixels; a few-MB ZIP can decompress to gigabytes; a crafted PDF can burn CPU for a long time. Limit part counts, archive depth, page/frame counts, concurrency, timeouts, and parser memory.

## 6. Complete Example: PNG Upload Endpoint with Spring MVC

This app demonstrates **accepting PNGs only** for a clear, deterministic policy. The demo rejects filenames with paths, dangerous characters, double extensions, and wrong declared MIME; verifies the PNG signature, format via `ImageIO`, and width×height; re-encodes; and writes into a private directory under a fresh UUID name. Invalid PNGs are never saved to the destination.

**Diagram:**

~~~text
POST /api/images/upload
    -> MultipartFile
    -> validateOriginalName
    -> getContentType == image/png
    -> bounded read <= 2 MiB
    -> PNG signature + ImageIO reader
    -> dimensions <= 4,000,000 pixels
    -> decode BufferedImage
    -> re-encode PNG
    -> random UUID.png + CREATE_NEW
    -> 201 {id,sizeBytes,width,height}
~~~

### 6.1. Structure

~~~text
safe-upload/
  pom.xml
  src/main/java/com/example/safeupload/
    SafeUploadApplication.java
    ImageUploadService.java
    ImageUploadController.java
  src/main/resources/
    application.properties
~~~

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>safe-upload</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

`spring-boot-starter-webmvc` includes Spring MVC and the Servlet container required for `MultipartFile`. The Boot parent manages dependency versions. On Spring Boot 3.x, typically use the corresponding `spring-boot-starter-web` starter. Commons FileUpload is not needed for standard Servlet multipart handling.

### 6.3. `SafeUploadApplication.java`

~~~java
package com.example.safeupload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeUploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeUploadApplication.class, args);
    }
}
~~~

### 6.4. `ImageUploadService.java`

~~~java
package com.example.safeupload;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Iterator;
import java.util.UUID;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ImageUploadService {
    private static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final long MAX_PIXELS = 4_000_000L;
    private static final byte[] PNG_SIGNATURE = {
        (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
    };

    private final Path storageRoot;

    public ImageUploadService(
            @Value("${app.upload.directory}") String configuredDirectory)
            throws IOException {
        Path configured = Path.of(configuredDirectory)
                .toAbsolutePath().normalize();

        // Admin-managed config, never read from request.
        Files.createDirectories(configured);
        if (!Files.isDirectory(configured, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(configured)) {
            throw new IOException("Unsafe upload directory");
        }
        storageRoot = configured.toRealPath();
    }

    public SavedImage save(MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw badRequest("PNG file is required");
        }

        validateOriginalName(file.getOriginalFilename());

        if (!"image/png".equalsIgnoreCase(file.getContentType())) {
            throw badRequest("Declared type must be image/png");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
        }

        byte[] bytes;
        try (InputStream in = file.getInputStream()) {
            bytes = in.readNBytes(MAX_BYTES + 1);
        }
        if (bytes.length > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
        }

        if (bytes.length < PNG_SIGNATURE.length
                || !Arrays.equals(
                        Arrays.copyOf(bytes, PNG_SIGNATURE.length),
                        PNG_SIGNATURE)) {
            throw badRequest("File is not PNG");
        }

        // Decoder checks structure and blocks images with excessive pixels.
        BufferedImage image = decodePng(bytes);

        // Server-generated target file, containing no user filename.
        String generatedName = UUID.randomUUID() + ".png";
        Path target = storageRoot.resolve(generatedName).normalize();

        if (!target.getParent().equals(storageRoot)) {
            throw new IOException("Invalid upload target");
        }

        boolean opened = false;
        boolean completed = false;
        try {
            try (OutputStream out = Files.newOutputStream(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                opened = true;
                if (!ImageIO.write(image, "png", out)) {
                    throw new IOException("PNG encoder unavailable");
                }
            }
            completed = true;
        } finally {
            if (opened && !completed) {
                Files.deleteIfExists(target);
            }
        }

        return new SavedImage(
                generatedName, Files.size(target),
                image.getWidth(), image.getHeight());
    }

    private static void validateOriginalName(String name) {
        // Demo restricts to short ASCII names with a single trailing dot + png extension.
        if (name == null
                || !name.matches(
                        "[A-Za-z0-9][A-Za-z0-9_-]{0,79}\\.[Pp][Nn][Gg]")) {
            throw badRequest("Unsafe or unsupported filename");
        }
    }

    private static BufferedImage decodePng(byte[] bytes) {
        try (ImageInputStream stream = ImageIO.createImageInputStream(
                new ByteArrayInputStream(bytes))) {
            if (stream == null) {
                throw badRequest("Image stream unavailable");
            }
            Iterator<ImageReader> it = ImageIO.getImageReaders(stream);
            if (!it.hasNext()) {
                throw badRequest("Unsupported image data");
            }

            ImageReader reader = it.next();
            try {
                reader.setInput(stream, true, true);
                if (!"png".equalsIgnoreCase(reader.getFormatName())) {
                    throw badRequest("Actual format is not PNG");
                }

                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                if (width <= 0 || height <= 0
                        || (long) width * height > MAX_PIXELS) {
                    throw badRequest("Image dimensions exceed limit");
                }

                BufferedImage image = reader.read(0);
                if (image == null) {
                    throw badRequest("Cannot decode image");
                }
                return image;
            } finally {
                reader.dispose();
            }
        } catch (IOException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid PNG structure", ex);
        }
    }

    private static ResponseStatusException badRequest(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }

    public record SavedImage(
            String id, long sizeBytes, int width, int height) {}
}
~~~

**Code explanation:**

- The filename regex permits only a short ASCII basename, one trailing dot, and a case-insensitive `.png` extension. `abc.php.png`, `../../file.png`, `photo.png.exe`, `file:name.png`, spaces, and path separators are all rejected. The ASCII rule is an **intentional demo choice**, not a requirement against international names; localized names can be stored as metadata after safe handling.
- `getContentType()` is an early check **not trustworthy alone**. Magic bytes and `ImageIO` verify further.
- `readNBytes(MAX_BYTES + 1)` avoids reading unboundedly into RAM. The multipart parser is also bounded by properties. For large uploads that cannot sit in RAM, design streaming/quarantine and a separate scanner.
- `ImageIO.getImageReaders` + `getWidth/getHeight` verify pixel counts before decoding. Re-encoding via `ImageIO.write` strips extraneous data from the original file, though **it is not a standalone security measure**.
- `MAX_PIXELS=4_000_000` is illustrative; a 4-million-pixel bitmap can still take tens of MB or more depending on the decoder. Measure resource usage under real concurrency.
- `UUID.randomUUID() + ".png"` lets the server choose the storage name, `CREATE_NEW` prevents accidental overwrites, and `target.getParent().equals(storageRoot)` adds defense-in-depth in code.
- The `opened/completed` flags delete incomplete files only if this request actually created the file. If `CREATE_NEW` fails because a file already existed, it will not delete someone else's file.
- `Files.createDirectories(...)` is only safe when the storage root and parent directories are **admin-controlled**, with no untrusted local actor able to swap symlinks. The demo does not address every race on untrusted shared filesystems.
- `SavedImage` exposes the ID name and verified properties; never expose absolute server paths.

### 6.5. `ImageUploadController.java`

~~~java
package com.example.safeupload;

import java.io.IOException;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.example.safeupload.ImageUploadService.SavedImage;

@RestController
@RequestMapping("/api/images")
public class ImageUploadController {
    private final ImageUploadService service;

    public ImageUploadController(ImageUploadService service) {
        this.service = service;
    }

    @PostMapping(
            path = "/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<SavedImage> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        SavedImage saved = service.save(file);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
~~~

The controller never builds paths from input; it forwards the part to the service and returns HTTP **201 Created** upon completion. Validation errors map via `ResponseStatusException`. Other I/O errors (such as out of disk space) typically become 5xx; production should standardize error responses without leaking real paths.

### 6.6. `application.properties`

~~~properties
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB

# Illustrative private folder: under the home directory of the account running the app.
# Production must set dedicated permissions and keep it separate from static/webroot.
app.upload.directory=${user.home}/private-uploads-demo
~~~

`app.upload.directory` is a custom property read by `@Value`; it is not the multipart parser's temp location. To change the temp folder, configure `spring.servlet.multipart.location` with appropriate permissions.

### 6.7. Running and Testing

In the `safe-upload` directory, run:

~~~bash
mvn spring-boot:run
~~~

Prepare a valid PNG file `photo.png` in the directory where you invoke curl. Send:

~~~bash
curl -i \
  -F "file=@photo.png;filename=photo.png;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Success status is **201 Created**, with JSON formatted like (illustrative format only; actual metrics depend on the image):

~~~json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.png",
  "sizeBytes": 12345,
  "width": 640,
  "height": 480
}
~~~

The physical file is saved under a UUID name inside `private-uploads-demo` in the JVM account's home directory, distinct from the client's filename. Output size may differ from input because the image is re-encoded.

Test double extension:

~~~bash
curl -i \
  -F "file=@photo.png;filename=photo.png.exe;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Expect **400** because the name is rejected.

Test traversal:

~~~bash
curl -i \
  -F "file=@photo.png;filename=../../config.png;type=image/png" \
  http://localhost:8080/api/images/upload
~~~

Expect **400**; the application creates no file at `../../`.

Test spoofed MIME:

~~~bash
curl -i \
  -F "file=@photo.png;filename=photo.png;type=text/plain" \
  http://localhost:8080/api/images/upload
~~~

Expect **400** from the declared MIME check. If a client declares `type=image/png` with non-PNG bytes, the signature/decoder check blocks it.

In Windows PowerShell, use `curl.exe`:

~~~powershell
curl.exe -i -F "file=@photo.png;filename=photo.png;type=image/png" http://localhost:8080/api/images/upload
~~~

Package and run the JAR:

~~~bash
mvn package
java -jar target/safe-upload-0.0.1-SNAPSHOT.jar
~~~

With Spring, running bare `javac` is insufficient because the Maven classpath supplies the required Spring libraries.

### 6.8. Statuses and Causes to Distinguish

| Scenario | Expected Outcome | Stage |
| --- | --- | --- |
| Valid PNG, valid filename/MIME | **201**, JSON with server-generated ID | Controller and service |
| Name has `../`, `\`, double extension | **400** | Filename validation |
| Declared MIME is `text/plain` | **400** | Metadata validation |
| Missing PNG signature | **400** | Byte validation |
| Decoder cannot read image | **400** | Format validation |
| Width×height exceeds limit | **400** | Resource validation |
| Upload exceeds max file/request size | Typically oversized error response, possibly **413**, depending on exception mapping/container | Multipart parser, before controller |
| Directory unwritable or disk full | Typically **5xx**, needs server logs/alerts | Storage I/O |

In production, add `@RestControllerAdvice` or a unified exception handler for consistent error statuses/bodies; never disclose filesystem paths, stack traces, or untrusted input in error messages.

## 7. Remaining Limitations of the Example

The example demonstrates a **multi-layer validated PNG upload path**, not a full production upload system.

- **Authentication/authorization:** endpoints must restrict who can upload and into whose store; avoid unauthenticated public upload endpoints without quotas.
- **Quotas:** cap request rate, file counts, total bytes per tenant, concurrent uploads, and decode CPU/time.
- **Output quota:** re-encoding a PNG can produce a file larger than 2 MiB; consider bounded stream encoding, disk quotas, lower pixel limits, or staging and measuring before publishing.
- **Antivirus/scanning:** a parser-valid image can still carry exploits targeting downstream consumers; scan commensurate with risk.
- **Quarantine:** upload into an isolated zone, scan, and promote to ACTIVE only after passing all checks; clean up rejected items.
- **Database consistency:** if file creation succeeds and DB write fails, an orphan appears; if DB writes first and file fails, metadata points to a missing file. Use staging, states, and idempotent cleanup/retries.
- **File permissions:** ensure the storage root and ancestors are not writable by untrusted accounts; new file permissions inherit environment/umask/ACL settings, so audit OS config.
- **Atomic publishing:** if other readers can guess IDs or multiple actors share a filesystem, write in private staging and atomic-move into a read-only area when ready.
- **Server-side threat model:** keep ImageIO and encoders patched, limit request rates, and monitor parsers; re-encoding is not antivirus.
- **Business metadata:** retain owner, checksum, verified MIME, actual written size, upload timestamp, retention, status, and audit events.

## 8. When You Must Support PDF, Office, SVG, ZIP, or Video

| Format | Specific Risks to Check | Handling Approach |
| --- | --- | --- |
| JPEG | EXIF, image dimensions, color profiles, metadata, parser | Image decoder, pixel cap, re-encode, optional metadata stripping |
| PDF | Embedded files/JS, page count, parser flaws, external links | PDF parser, page/resource limits, scan/CDR, sandboxed rendering |
| DOCX/XLSX/PPTX | ZIP container, external relationships, embedded objects | Office library, validate entries, scan; never check `PK` alone |
| SVG | XML, scripts, external resources, active content | Enable only if essential; dedicated sanitizer, CSP, cautious serving |
| ZIP/TAR | Zip Slip, symlinks, recursive archives, decompression bombs | Cap entries/depth/ratio/output bytes; check every entry path |
| MP4/video | Parser/transcoder, codecs, duration, CPU/disk | Sandbox ffmpeg, resource/time budgets, normalize/scan |
| HTML | XSS and active content if served inline | Never put arbitrary HTML in public static; escape/attachment |
| CSV | Formula injection when opened in spreadsheets | Sanitize cell values on export and set content disposition policy |

**ZIP Slip** is a vulnerability where an entry name like `../../config.txt` is extracted into `root.resolve(entryName)` without verifying containment. When archives are permitted, validate every entry, symlinks, and total extracted resource budgets.

**PDF/Office:** a valid signature does not guarantee the absence of malware or active content; pick a maintained parser library, inspect page/object counts, and bound processing. Depending on the system, apply content disarm and reconstruction or asynchronous scanning before allowing others to download.

**Never use regex to parse complex file formats.** Filename regexes are only a preliminary guard on metadata, not content verification.

## 9. Download: Re-Checking the Path from Storage to Client

A successful upload does not mean any client may call `/download?path=...` to read arbitrary files. A download endpoint should:

1. Accept a **server-issued file ID**, never arbitrary absolute/relative filesystem paths.
2. Look up metadata and verify owner/tenant, read permission, file status (e.g., ACTIVE post-scan), and retention.
3. Retrieve the storage key from verified metadata, validate key format if needed, and resolve inside the trusted root.
4. Set response `Content-Type` from the **verified** content type, never reflecting the original upload's `getContentType()`.
5. Consider `Content-Disposition: attachment` to prevent browsers from rendering untrusted content inline, plus `X-Content-Type-Options: nosniff`; escape/encode filenames in HTTP headers.
6. Stream with quotas/timeouts, proper cache control, and auditing without logging secrets or tenant paths.

An unguessable UUID alone **is not** authorization. If a browser renders uploaded HTML/SVG on the same origin without proper isolation, XSS risks emerge; configure response policies appropriate to the actual content.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `uploadRoot.resolve(file.getOriginalFilename())` | Traversal, collisions, writing to wrong directories | Generate storage names from UUID or internal IDs |
| Calling `Path.getFileName()` and saving immediately | Still client-supplied, special names/collisions remain | Keep only for display; server generates the path |
| Allowing extension via `name.contains(".png")` | Accepts `photo.png.exe` | Validate full extension allowlist + parse actual content |
| Trusting `getContentType()` | Spoofed MIME | Verify magic signature + format parser |
| Checking signature alone | Corrupt files, polyglots, resource bombs slip through | Parse, cap resources, re-encode/scan |
| Assuming `normalize().startsWith(root)` stops symlinks | Races or links redirecting outside root | Private root, OS/ACL permissions, safe open |
| Writing files with replace/truncate | Overwrites existing files | `CREATE_NEW`, random file IDs |
| Putting uploads in `static/` or webroot | Bypasses auth, files served directly | Private storage and authorized downloads |
| Checking size only in controller | Multipart parser/gateway already spent resources | Proxy + servlet multipart + service limits |
| Unbounded pixels/pages/entries | Decompression bombs / CPU / memory exhaustion | Decoder resource budgets |
| Reading every file into unbounded `byte[]` | OOM or GC pressure | Bounded reads or streaming |
| Re-encoding without checking output size | Saved file size can grow | Disk/byte quotas, staging |
| Using original filename unescaped in HTML/headers | XSS, response splitting, or encoding errors | Context-appropriate encoding/escaping |
| Publishing upload immediately on receipt | Unscanned/unauthorized file gets downloaded | Quarantine and publish state machine |
| Ignoring partial writes | Junk/orphan files | Cleanup on error, staged publishing |
| No per-user/tenant limits | Disk fill / cost abuse | Auth, rate limits, storage quotas, auditing |

## 11. Self-Check Questions

**Q A:** A file is named `photo.png` and declares `Content-Type: image/png`. Is that enough to trust it as a safe image?

**Answer:** No. Filename and MIME are client input. Verify bytes, run a parser/decoder, enforce size and file-type limits, and scan/transform as risk requires.

**Q B:** Why is `Path.of(name).getFileName()` not guaranteed completely safe?

**Answer:** The name can still be unsuitable for the OS, collide, or interact with symlinks; path separators also differ across platforms. Storage names should be backend-generated.

**Q C:** Is `target.normalize().startsWith(root)` enough to block all path traversal?

**Answer:** No. Lexical checks do not stop symlinks or TOCTOU races if parents are writable by untrusted actors. Private roots and OS permissions are essential.

**Q D:** Does a 50 KiB PNG still need pixel dimension limits?

**Answer:** Yes. Compressed size and decoded bitmap size differ dramatically; limit width, height, pixel count, and concurrency.

**Q E:** Is `spring.servlet.multipart.location` a permanent storage directory?

**Answer:** No. It is the multipart parser's temporary area; durable storage location is decided by the application.

**Q F:** If a file already has a random UUID, does download still need authorization checks?

**Answer:** Yes. UUID is a collision-avoiding identifier, not an access control mechanism.

**Q G:** Should you accept ZIP files solely because their magic bytes start with `PK`?

**Answer:** No. Validate archive structure, entries, decompressed byte totals, symlinks, Zip Slip, recursion, and malware.

## 12. Official Documentation

- [Spring Boot — Spring MVC multipart upload](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)
- [Spring Boot — Common Application Properties: servlet.multipart](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework — MultipartFile API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html)
- [Spring Framework — Multipart forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Guides — Uploading Files](https://spring.io/guides/gs/uploading-files/)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload)
- [Java SE 17 — java.nio.file.Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 17 — ImageIO](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/imageio/ImageIO.html)

**Principle:** clients may supply metadata and bytes, yet **must never dictate the storage path or trusted file type**. The backend validates format using a bounded parser, generates a fresh storage ID, writes to a private root with strict OS permissions and `CREATE_NEW`, and serves downloads only after checking permissions and file status.
