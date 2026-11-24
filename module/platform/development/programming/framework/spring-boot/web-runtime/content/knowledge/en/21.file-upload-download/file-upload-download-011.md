# Separating User Upload Directories from Source Code and Public Resources

## 1. Why Must Upload Storage Be Separated?

In Spring Boot, Java source code, HTML templates, static assets, and user-uploaded files have **different origins, trust levels, and lifecycles**. Application code and resources are versioned in Git, packaged into a JAR/WAR, and deployed. Uploads arrive via HTTP requests, may hold personal data or malicious content, and must be stored, deleted, and access-controlled independently of software releases.

If an application writes uploads into `src/main/resources/static/uploads`, `src/main/resources/public`, `src/main/webapp`, or a folder alongside source code, three common risks follow:

1. **File exposure:** resources may be served directly through static resource mapping or a reverse proxy without checking ownership or ACLs.
2. **Data loss or stale versions:** resources in a JAR are build inputs, while containers/instances get replaced. Files written into source or build outputs are not automatically bundled into a running JAR and can disappear on redeploy.
3. **Blurred trust boundaries:** client files sit right next to templates, scripts, and public assets, opening the door to content spoofing, XSS, overwrites, and misconfiguration.

**Design principle:** user uploads are **untrusted runtime data** and require a dedicated storage area outside the source tree, outside the classpath, and outside the public webroot. Private files must only be read via authenticated and authorized services/APIs; files meant to be public must pass through a separate publishing workflow.

```text
Repository / Build                              Runtime storage
-----------------------------------------       ----------------------------
src/main/java/...                               /var/lib/myapp/private-files/
src/main/resources/application.properties         245ab...uuid
src/main/resources/static/brand.svg               1902c...uuid
src/main/resources/templates/home.html            71e80...uuid
          |                                                ^
          v                                                |
       bootJar                                        Upload service
          |                                                ^
          v                                                |
     application.jar                         POST /api/files + validation
          |
          +--> GET /brand.svg = static public asset
          +--> GET /api/files/{id} --> authz --> private file
```

This layout places the **public vs. private decision at the HTTP and metadata layer**, rather than relying on whether a user knows a physical filename.

## 2. Directory Classification and How Spring Boot Serves Files

| Directory / Path | Purpose | Store Private Uploads Here? |
| --- | --- | --- |
| `src/main/java/` | Java source code | No |
| `src/main/resources/static/` | Static CSS/JS/images/HTML served via static mapping | No |
| `src/main/resources/public/` | Other static resources | No |
| `src/main/resources/META-INF/resources/` | Default static location | No |
| `src/main/resources/resources/` | Default static location | No |
| `src/main/resources/templates/` | Thymeleaf/FreeMarker templates, etc. | No |
| `src/main/webapp/` in WAR | Servlet web application content | No |
| `build/`, `target/`, `BOOT-INF/classes/` | Build outputs or JAR resources | No |
| `java.io.tmpdir`/multipart temp | Intermediate request files | Not for long-term storage |
| `/var/lib/myapp/private-files/` on dedicated volume | User files with restricted OS permissions | Yes |
| Private object storage bucket | Data bytes protected by API/storage policies | Yes |

By default, Spring Boot MVC serves static resources from classpath locations such as `/static`, `/public`, `/resources`, and `/META-INF/resources` (on the classpath). When `src/main/resources/static/logo.png` is built, it is normally reachable at `GET /logo.png` under default static settings. Placing a customer's `invoice.pdf` there lets anyone with the URL fetch it through generic static handling.

Do not treat `templates/` as safe storage simply because static mapping does not serve it directly. Templates can be rendered by template engines, packaged into JARs, and cached. User uploads must never become template-engine inputs or risk overwriting release assets.

Beyond Spring Boot, also audit **NGINX/Apache/CDN**. An `alias` or static location on a reverse proxy pointing to a private directory still leaks files even if no Spring controller maps `/uploads`.

## 3. Classpath, Filesystem, and HTTP URLs Are Not the Same

Distinguish three domains:

- **Classpath resources:** files Java/Spring loads via `classpath:`, packaged into Gradle/Maven outputs or `BOOT-INF/classes` and dependency JARs.
- **Runtime filesystem:** drives/volumes that the live process can read/write, such as `/var/lib/myapp/private-files/`. This sits outside the application JAR.
- **HTTP URL:** routes mapped by controllers, static handlers, or reverse proxies. A URL does not exist automatically merely because a file sits on disk.

```text
classpath:/static/banner.png  -> MVC static handler       -> GET /banner.png
file:/srv/data/private/abc    -> NO public mapping        -> No direct URL exists
GET /api/files/{uuid}        -> controller + authz        -> private storage
```

**Do not** register a `ResourceHandler` serving `/uploads/**` from a private directory when business logic requires user/tenant checks. Doing so bypasses service authorization, scan status, retention, auditing, and dedicated response headers.

If a file genuinely belongs in public marketing/galleries, build a dedicated public storage/publishing pipeline. Never make an entire private directory world-readable or open an alias just for quick downloads.

## 4. Why Source Paths and Working Directories Are Not Durable Storage

The following code is architecturally broken:

```java
// Anti-pattern: writing uploaded files into the application source tree.
Path destination = Path.of(
        "src/main/resources/static/uploads", "contract.pdf");
```

The path above is a **relative path** resolved against `user.dir`/the process working directory. While running in an IDE it might land in your repository, yet when `java -jar` starts from elsewhere it can point to a nonexistent folder. Files written into source folders never get patched into a packaged JAR: a JAR contains a **build-time snapshot of resources**.

In an executable Spring Boot JAR, classpath resources live inside `BOOT-INF/classes`, not a regular writable directory tree. Never call `Resource.getFile()` on arbitrary classpath resources assuming a writable physical path exists inside a JAR.

In Docker/Kubernetes, a container's writable layer rarely survives container replacement; across multiple replicas, local disks differ. Uploading to instance A and downloading from instance B yields 404. Thus **separating from source** must go hand in hand with **separating from deployment lifecycles** using persistent volumes, shared/network storage, or object storage.

## 5. Multipart Staging Is Completely Different from Permanent Storage

Spring MVC handles HTTP `multipart/form-data` via Servlet multipart parsing. Controllers receive `MultipartFile`, while the Servlet container buffers the upload in memory or **temporary disk** before the service saves it.

In Spring Boot 3.3, common properties include:

```properties
# Spring Boot 3.3 defaults to 1MB/file and 10MB/request.
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
spring.servlet.multipart.file-size-threshold=0B

# Only where the multipart parser may write TEMPORARY content.
# spring.servlet.multipart.location=/var/tmp/myapp-multipart
```

**`spring.servlet.multipart.location` is not a long-term user storage directory.** It is only a per-request intermediate workspace whose lifecycle is managed by the multipart parser/container. Never keep references to temp files or expose those paths to users. Copy/transfer into the application's private root while the request is valid.

`MultipartFile` provides `getInputStream()`, `getSize()`, `getOriginalFilename()`, `getContentType()`, and `transferTo(...)`. Keep in mind:

- `getOriginalFilename()` is **client-supplied** and may be `../../etc/passwd`, contain path separators, or dangerous extensions. Javadoc advises against using it directly for write paths.
- `getContentType()` is client-declared and **does not verify actual bytes**.
- Never call `file.getBytes()` for large files to pull everything onto the heap when streaming works.
- `transferTo(...)` varies by implementation/container and target path; the app must still control directories, permissions, keys, and cleanup.

For large uploads, alongside Spring multipart limits you need reverse proxy size limits, timeouts, temp-directory disk quotas, concurrency caps, and per-user/tenant quotas. Never counter DoS risks simply by raising max-file-size to unlimited.

## 6. Separating Storage and Metadata Cleanly

A small, clear architecture with separated responsibilities:

```text
POST /api/files
  -> Authentication / authorization to upload
  -> Multipart validation, size, type, scanning policy
  -> Storage service creates opaque file ID
  -> Bytes stored in private directory/bucket
  -> Metadata saved: fileId, ownerId, storageKey, size, status
  -> 201 Created + fileId

GET /api/files/{fileId}
  -> Authentication
  -> Load metadata
  -> Check owner/tenant/ACL, status, retention
  -> Resolve server-controlled storageKey
  -> Stream bytes with safe download headers
```

Metadata models should distinguish:

| Field | Role |
| --- | --- |
| `file_id` | Logical ID used in APIs, e.g., UUID |
| `storage_key` | Server-generated filename/object key, **never taken from request** |
| `owner_id`, `tenant_id` | Authorization bindings |
| `original_filename` | Display name; must escape/sanitize and never use as path |
| `detected_media_type` | Policy-verified content type |
| `size_bytes`, `sha256` | Size and integrity |
| `status` | `PENDING_SCAN`, `AVAILABLE`, `REJECTED`, `DELETING`... |
| `created_at`, `retention_until` | Auditing and lifecycle |

A UUID is not a password. Hard-to-guess IDs can still leak in URLs, logs, or other APIs. **Never allow downloads solely because a client knows a UUID**; verify permissions against metadata. Logically deleted or unscanned files must be blocked unless policy explicitly permits.

## 7. Configuring Private Storage via Absolute Paths

Example Linux production layout:

```text
/opt/myapp/application.jar
/etc/myapp/application-prod.yml
/var/lib/myapp/private-files/      # private, independent persistence
/var/log/myapp/
```

`application.properties` configuration:

```properties
app.upload.root=${UPLOAD_ROOT}

spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

# Only for local demo; production has dedicated network + security config.
server.address=127.0.0.1
server.port=8080
```

`UPLOAD_ROOT` must be set by the operator to an **absolute path outside the repository, static locations, webroot, and build artifacts**. Requiring the environment variable prevents the app from silently writing uploads into the current working directory.

On Linux, provision the folder under a service account:

```bash
sudo install -d -m 700 -o myapp -g myapp /var/lib/myapp/private-files
```

Use this only when the `myapp` account exists and the app genuinely runs under it. On Windows, pick an absolute volume/path and matching NTFS ACLs. Ensure the running process has required read/write rights and untrusted users/processes cannot plant symlinks or alter files inside the directory.

With multiple app instances, storage must use a **consistently accessible shared volume** or object storage. Never depend on hostnames or working directories.

## 8. Never Use Original Filenames as Storage Paths

Client names can contain:

```text
portrait.jpg
../../application.properties
C:\Windows\system.ini
invoice.pdf.exe
<script>alert(1)</script>.html
```

Wrong approach:

```java
// Do not do this:
Path target = root.resolve(file.getOriginalFilename());
```

This risks path traversal, overwrites, dangerous names, Windows/Linux separator mismatches, or data leaks. `Paths.get(name).getFileName()` still leaves extension, overwrite, and identifier collision risks unresolved.

Instead, generate a **random server-controlled storage key**:

```java
UUID id = UUID.randomUUID();
Path target = privateRoot.resolve(id.toString());
```

Use `Files.newOutputStream(target, CREATE_NEW, WRITE)` instead of blindly overwriting. If UIs need the original name, store it separately in metadata after capping length and escaping for HTML, JSON, and HTTP header contexts. When an extension is needed, derive it via allowlists/content verification rather than trusting client extensions as proof of format.

For attachment downloads, using a server-chosen filename works fine too. When returning original filenames per business rules, build `Content-Disposition` with Spring's API builder to handle escaping/encoding and avoid header injection.

## 9. Runnable Spring Boot 3.3 Example: Storing Private Files by UUID

This example uses Java 21, Spring Boot 3.3.13, and Gradle Wrapper. It is intended for **learning and loopback execution**, without authentication, metadata DB, or malware scanning. Before production, add those layers and remove loopback-only network restrictions deliberately.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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
```

**`src/main/java/com/example/upload/UploadApplication.java`:**

```java
package com.example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
```

**`src/main/java/com/example/upload/PrivateFileStorage.java`:**

```java
package com.example.upload;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class PrivateFileStorage {
    private static final long MAX_BYTES = 5L * 1024 * 1024;
    private final Path root;

    public PrivateFileStorage(@Value("${app.upload.root}") String directory)
            throws IOException {
        Path configured = Path.of(directory);
        if (!configured.isAbsolute()) {
            throw new IllegalArgumentException(
                    "app.upload.root must be absolute");
        }
        Files.createDirectories(configured);
        this.root = configured.toRealPath();
    }

    public SavedFile save(MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File must not be empty");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("File exceeds 5 MiB");
        }

        UUID id = UUID.randomUUID();
        Path target = root.resolve(id.toString());
        boolean created = false;
        long copied;

        try {
            try (OutputStream out = Files.newOutputStream(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                created = true;
                try (InputStream in = file.getInputStream()) {
                    copied = in.transferTo(out);
                }
            }
            if (copied > MAX_BYTES) {
                throw new IllegalArgumentException("File exceeds 5 MiB");
            }
        } catch (IOException | RuntimeException error) {
            if (created) {
                try {
                    Files.deleteIfExists(target);
                } catch (IOException cleanup) {
                    error.addSuppressed(cleanup);
                }
            }
            throw error;
        }
        return new SavedFile(id, copied);
    }

    public Path find(UUID id) throws IOException {
        Path file = root.resolve(id.toString());
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw new NoSuchFileException(id.toString());
        }
        return file;
    }

    public record SavedFile(UUID id, long bytes) {
    }
}
```

Analysis:

- `app.upload.root` must be an absolute path. The constructor creates the directory and resolves `toRealPath()` on the existing location. **Operators must still ensure** the path sits outside source/webroot and directory permissions are locked down.
- The filename on disk **is solely a UUID**. Even if a client sends `../../application.yml`, data lands at `root.resolve(UUID)` with zero client path components.
- `CREATE_NEW` refuses to overwrite existing paths. `boolean created` flips true only after opening the output stream succeeds; if opening fails because a path exists, cleanup will not delete an existing file.
- The input stream is closed; `transferTo` streams bytes; `catch` attempts to delete partial files on copy failure. Checking actual copied bytes reinforces `MultipartFile.getSize()` and parser limits.
- `find` accepts only a `UUID` and checks regular file with `NOFOLLOW_LINKS` to reject symlinks. Even so, if another process can modify the directory, a race condition remains between check and read. Strict permissions remain a prerequisite.
- This service lacks metadata/ACL; production must verify authorization before calling `find`, never relying on unguessable UUIDs alone.

**`src/main/java/com/example/upload/UploadController.java`:**

```java
package com.example.upload;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
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

@RestController
@RequestMapping("/api/files")
public class UploadController {
    private final PrivateFileStorage storage;

    public UploadController(PrivateFileStorage storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<PrivateFileStorage.SavedFile> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(storage.save(file));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Resource> download(@PathVariable UUID id)
            throws IOException {
        // Production: check metadata + owner/tenant/ACL before this line.
        Path path = storage.find(id);
        Resource data = new FileSystemResource(path);
        String disposition = ContentDisposition.attachment()
                .filename(id + ".bin", StandardCharsets.UTF_8)
                .build().toString();

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(Files.size(path))
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .body(data);
    }
}
```

The controller serves downloads **by ID**, accepting no raw paths. `Content-Disposition: attachment` tells browsers to download instead of rendering as HTML; `application/octet-stream` avoids trusting client MIME; `nosniff` adds content-sniffing protection; `no-store` is a sensible cache policy for private files.

Those headers **do not replace** authentication/authorization. Because the demo lacks security, it binds only to `server.address=127.0.0.1`. Real deployments must run metadata lookup and authorization before opening files.

**`src/main/java/com/example/upload/UploadProblemHandler.java`:**

```java
package com.example.upload;

import java.nio.file.NoSuchFileException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadProblemHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    ProblemDetail invalidFile(IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Invalid or oversized file");
    }

    @ExceptionHandler(NoSuchFileException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ProblemDetail missingFile(NoSuchFileException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "File not found");
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    @ResponseStatus(HttpStatus.PAYLOAD_TOO_LARGE)
    ProblemDetail tooLarge(MaxUploadSizeExceededException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.PAYLOAD_TOO_LARGE, "Multipart limit exceeded");
    }
}
```

HTTP errors never leak absolute file paths. In larger projects, scope exception handlers specifically to upload controllers so unrelated `IllegalArgumentException`s in other modules are not turned into file error messages.

**`src/main/resources/application.properties`:**

```properties
app.upload.root=${UPLOAD_ROOT}
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
server.address=127.0.0.1
server.port=8080
```

## 10. Running and Verifying Files Stay Outside Source

On Linux/macOS, create a directory **outside the project** for the demo:

```bash
mkdir -p /tmp/myapp-upload-demo
chmod 700 /tmp/myapp-upload-demo
export UPLOAD_ROOT=/tmp/myapp-upload-demo
./gradlew bootRun
```

`/tmp` is only for development because it lacks durability guarantees; production uses `/var/lib/myapp/private-files` on a durable volume.

On Windows PowerShell:

```powershell
$env:UPLOAD_ROOT = Join-Path $env:TEMP "myapp-upload-demo"
New-Item -ItemType Directory -Force -Path $env:UPLOAD_ROOT
.\gradlew.bat bootRun
```

Create any `sample.txt` in another terminal and upload:

```bash
curl -i -F "file=@sample.txt" http://127.0.0.1:8080/api/files
```

On success, `201 Created` returns JSON with a UUID `id` and actual `bytes`. **There is no fixed stdout** for the UUID since the server generates a new one each time. Grab the actual ID from JSON and download:

```bash
curl -fS -o downloaded.bin \
  http://127.0.0.1:8080/api/files/REPLACE_WITH_REAL_UUID
```

Replace `REPLACE_WITH_REAL_UUID` with the UUID string from the response. `downloaded.bin` should match `sample.txt` byte-for-byte. On the server, the file lives in `UPLOAD_ROOT` under the UUID name—**not** inside `src/main/resources/static`, `public`, `templates`, or next to `UploadApplication.java`.

Try a suspicious client-declared filename with curl:

```bash
curl -F 'file=@sample.txt;filename=../../index.html' \
  http://127.0.0.1:8080/api/files
```

Because the storage key is server-generated, nothing traverses via `../../`. Across restarts on the same machine with the same `UPLOAD_ROOT`, demo files persist as long as the OS has not cleared the folder. Across different instances lacking shared storage, persistence is not guaranteed.

This example is solely for learning local storage separation. Never expose this unauthenticated API to the Internet.

## 11. Authorization on File Reads Is Mandatory

Production requires a metadata/ACL layer. Illustrative flow:

```text
Authenticated user
       |
       +--> GET /api/files/{id}
       |
       +--> Find file metadata by id
       +--> Check tenantId, ownerId, role, shared-with list
       +--> Check status == AVAILABLE, not deleted/expired
       +--> Map trusted storageKey to file/object
       +--> Stream download + audit
```

The following Java pseudocode is **not a standalone program** since `FileMetadata`, repository, and access policy are domain components you must implement:

```java
FileMetadata meta = metadataRepository.findById(fileId)
        .orElseThrow(FileNotFoundException::new);

if (!accessPolicy.canRead(authentication, meta)) {
    throw new AccessDeniedException("Not allowed");
}

Path file = privateStorage.find(meta.storageId());
return streamAuthorizedFile(file);
```

Even with hard-to-guess UUIDs, you must still block User B from reading User A's files. Some products return 404 identically for nonexistent and unauthorized files to avoid disclosing existence; apply that rule consistently if chosen.

If issuing signed URLs for S3-compatible storage, check authorization **before signing**, and keep TTL and permissions tight. Never log signed URLs, tokens, or user credentials into broadly accessible logs.

When uploads belong to accounts/tenants, control **create, read, state transitions, and delete** separately. Read access must never implicitly grant delete or public-publish permissions.

## 12. Layers of Malicious-File Checking

Moving files outside the webroot is necessary but insufficient. When accepting client content:

1. Use a business-aligned **file-type allowlist**, such as JPEG/PNG/PDF. Never rely on extension blocklists like `.exe`, given double extensions and unusual Unicode names.
2. Verify **actual file signatures/formats** where needed. `Content-Type` headers and filenames are merely client input.
3. Set size limits at proxies, Spring multipart, and storage; for ZIP/PDF/images, also bound decompression ratios, page counts, pixel dimensions, and entry counts.
4. Apply malware scanning, sandboxing, or CDR when file types and threat models require it. Keep files in `PENDING_SCAN`/quarantine until cleared.
5. Never render untrusted HTML/SVG/PDF directly on the same origin as the application without safeguards; use conversion, isolated origins, or CSP.
6. Set per-user/tenant quotas, rate limits, upload timeouts, concurrency caps, and cleanup on aborted requests.
7. With cookie-based authentication, enforce CSRF protection properly; CORS does not stop CSRF on its own.
8. Audit at the level of file ID, actor, size, and status; never log raw file bytes or secrets.

A file named `image.png` can carry HTML bytes or malicious payloads. Never take an extension or multipart `getContentType()` as permission to render inline.

For private downloads, `attachment`, `octet-stream`, `nosniff`, and `no-store` help, yet you still must verify permissions and content before serving. Browser behavior also depends on client versions, so never treat response headers as absolute protection.

## 13. Path Traversal, Symlinks, and Race Conditions

When clients influence storage paths, they can pass `../`, absolute paths, Windows/Linux separators, or colliding names to read/overwrite outside the root. The safer design is **accepting zero paths from clients**.

Where business requirements force relative paths, validate, normalize, enforce containment under a trusted root, and handle symbolic links. Yet `path.normalize().startsWith(root)` is only one layer: if an attacker can swap a symlink between check and open, a race (TOCTOU) remains.

The section 9 example uses UUID filenames, `CREATE_NEW` on write, and `Files.isRegularFile(..., NOFOLLOW_LINKS)` on read. Still, an **environmental precondition** is that the private directory and ancestor paths cannot be modified by untrusted processes. If your threat model covers hostile local users, use OS-appropriate safe handle-open mechanisms or object storage with tight IAM.

Never expose a delete API accepting raw absolute filesystem paths. Delete by ID and authorized metadata using only server-managed storage keys.

`Files.createDirectories(...)` does not configure all desired security ACLs. Operators must manage owner/group/mode on Linux or NTFS ACLs on Windows, mount options, and backup policies.

## 14. File Bytes and Database Metadata Do Not Share a Transaction

`@Transactional` for JDBC/JPA does not automatically roll back `Files.write`, `Files.move`, or S3 uploads alongside DB rollbacks. An upload can produce:

- Bytes written successfully, DB commit fails → **orphan file**.
- Metadata committed first, storage write fails → dangling record pointing to a missing file.
- Client times out and retries → duplicate files without idempotency.
- Metadata deleted successfully, object delete fails → stray file remains in storage.
- Container dies mid-copy → partial file or stuck pending record.

Production flows should use **explicit states and cleanup**:

```text
NEW/PENDING
    -> write bytes to staging/quarantine
    -> validate/checksum/scan
    -> publish/mark AVAILABLE
    -> [downloadable only when AVAILABLE]
    -> DELETING/DELETED when expired or requested
```

Note that `Files.move` with `ATOMIC_MOVE` can only be atomic on filesystems supporting it and usually offers no atomicity across separate volumes. Catch `AtomicMoveNotSupportedException`; moving files does not turn DB and filesystem into a distributed transaction.

Run a scheduled reconciliation job to detect metadata missing bytes, orphan files, or stale pending uploads, using idempotent retries and audited cleanup. With object storage, design around the provider's upload/multipart completion semantics rather than assuming object writes and DB inserts form one ACID step.

## 15. Data Must Outlive Containers and Build Artifacts

When packaging with Docker, uploads must not live inside the container image or writable container layer. Example Docker Compose showing a **dedicated volume**:

```yaml
services:
  web:
    image: example/myapp:1.0
    environment:
      UPLOAD_ROOT: /data/private-files
    ports:
      - "8080:8080"
    volumes:
      - user_uploads:/data/private-files

volumes:
  user_uploads:
```

This is a deployment illustration, not a complete production config: `server.address=127.0.0.1` in the demo must be adjusted so the container accepts port-mapped traffic, and **the API must be secured** before exposing to networks.

A Docker named volume preserves data across container restarts on the **same host**, yet does not provide multi-host shared storage, automatic backups, or high availability.

In Kubernetes:

- Inspect `PersistentVolumeClaim` and the actual storage driver.
- Distinguish `ReadWriteOnce` vs. `ReadWriteMany` across multiple pods/nodes.
- Align UID/GID, volume permissions, mount paths, and node affinity.
- Never assume every pod shares one local filesystem.
- Configure backups/restores and volume-loss recovery plans.
- At scale, use private object storage with object keys in metadata, IAM, and clear signed-download policies.

A good deployment test: upload a file before a release, replace the image/container, then download the same file ID. If the file disappears, fix storage persistence and metadata—never “fix” the controller to read from `static`.

## 16. Handling Genuinely Public Files Safely

Some user files **are meant to be public** (approved product photos, banners, brochures). Separate their pipeline:

```text
Private original uploads
  -> validate content
  -> scan/moderate
  -> transform (thumbnail, image conversion, safe document)
  -> publish approved derivative to public storage/CDN
```

Originals and public derivatives have **distinct permissions and lifecycles**. Never expose the entire private upload root publicly just because some images need public display. Public assets may require content sanitization, strict MIME types, CSP, and separate origins to mitigate XSS.

When revoking public access or deleting originals per policy, account for derived files, CDN/edge caches, and backup retention. Never claim complete deletion while copies persist under backup retention schedules.

## 17. Testing: Client Filenames Never Alter the Storage Path

With `spring-boot-starter-test`, you can run JUnit 5 and `MockMultipartFile`. This test **uses an isolated temporary filesystem** without needing a live server or production root.

**`src/test/java/com/example/upload/PrivateFileStorageTest.java`:**

```java
package com.example.upload;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class PrivateFileStorageTest {
    @TempDir
    Path tempDir;

    @Test
    void neverUsesOriginalFilenameAsStoragePath() throws Exception {
        Path root = tempDir.resolve("private").toAbsolutePath();
        PrivateFileStorage storage = new PrivateFileStorage(root.toString());

        MockMultipartFile uploaded = new MockMultipartFile(
                "file",
                "../../index.html",
                "text/html",
                "hello".getBytes(StandardCharsets.UTF_8));

        PrivateFileStorage.SavedFile saved = storage.save(uploaded);
        Path stored = storage.find(saved.id());

        assertThat(Files.readString(stored)).isEqualTo("hello");
        assertThat(stored.getFileName().toString())
                .isEqualTo(saved.id().toString());
        assertThat(stored.startsWith(root.toRealPath())).isTrue();
        assertThat(Files.exists(tempDir.resolve("index.html"))).isFalse();
    }
}
```

Run from the project root:

```bash
./gradlew test
```

If the environment allows file creation and source matches the example, the test **PASSES**, with no fixed UUID stdout. This test proves the original filename is not used as a path; it does not verify authorization, malware scanning, or durability.

Key integration tests to add for production: User A uploads and User B is denied reading the same ID; oversized uploads create no files; `PENDING_SCAN` cannot be downloaded; symlinks are rejected; restarts/redeploys keep data on durable volumes; requests to `/uploads/...` cannot bypass policy; concurrent uploads do not overwrite each other; partial files are cleaned up.

## 18. Diagnosing Upload and Download Failures

| Symptom | Suspected Cause | What to Check |
| --- | --- | --- |
| Upload returns 201 yet file isn't in source/static | Likely **working as designed** | Check `UPLOAD_ROOT` and actual storage key |
| File vanishes after container redeploy | Saved to writable container layer without volume | Check mounts, PVCs, object storage |
| Uploaded to instance A, 404 from instance B | Separate local instance storage | Use shared or object storage |
| File exists on disk yet API returns 403 | Authorization or OS permissions | Check user/tenant/ACL and service UID |
| Upload returns 413 | Multipart/proxy request size limit | Check Spring and ingress limits |
| `AccessDeniedException` on write | Directory/volume ACL/UID mismatch | Check app account, permissions, mount options |
| `NoSuchFileException` on download | Wrong root, stale metadata, or expired file | Check absolute root, key, and retention |
| Private file readable at `/uploads/...` | Static handler, proxy alias, or public bucket | Remove public mapping; audit webroot/IAM |
| HTML file renders inline instead of downloading | Unsafe Content-Type/Content-Disposition | Prefer attachment + octet-stream + nosniff |
| Metadata exists without bytes | DB/file coordination error or premature cleanup | Check status, audit logs, and reconciliation |
| Disk full while private root has free space | Multipart **temp staging** uses a different disk | Check `spring.servlet.multipart.location`, `java.io.tmpdir` |
| Works in IDE, fails in JAR | Used relative path or JAR-packed resource | Check absolute root, working dir, artifact |
| New container/image serves old file version | Local cache, different node, or stale metadata/replica | Check instance, storage key, and cache policy |

Trace a single ID end-to-end: `POST` → metadata → storage key → disk/object → authorization → `GET`. Never “fix” failures by making an entire directory public or opening read/write permissions for all users.

## 19. WebFlux vs. Servlet Differences at the Upload Layer

In Spring MVC/Servlet, controllers typically use `MultipartFile` and `spring.servlet.multipart.*` properties. In Spring WebFlux, reactive APIs use `FilePart`, `Part`, or `PartEvent` alongside `spring.webflux.multipart.*`.

Regardless of stack, storage principles remain identical: store outside source/static/webroot, use server-generated keys, enforce authz, quotas, scanning, metadata, durability, and cleanup. WebFlux does not magically make untrusted client bytes safe.

In WebFlux, avoid calling blocking `Files.copy`, `Files.newOutputStream`, or JDBC/JPA directly on Netty event-loop threads. Use `FilePart.transferTo(Path)` with server-controlled roots/keys or suitable storage clients, handling errors and partial cleanup; when blocking APIs are unavoidable, offload to a scheduler built for blocking I/O.

If both MVC and WebFlux are on the classpath, Spring Boot generally picks **Servlet** by default when inferring the web application type. Confirm the active stack before tuning multipart properties.

## 20. Common Misconceptions

**“`spring.servlet.multipart.location` is a permanent storage directory.”** No; it is temporary workspace for multipart parsing.

**“The file is inside `static/`, yet the URL is hard to guess so it's safe.”** No; URLs/filenames are not ACLs. Static handlers serve files directly to anyone knowing the path.

**“`templates/` isn't public, so use it for private uploads.”** No; templates are build/engine resources, not user-data storage.

**“With `.gitignore`, keeping uploads inside the project is fine.”** No; Git ignore does not prevent static serving, build packaging, data loss on redeploy, or Docker cleanup.

**“Calling `MultipartFile.getOriginalFilename()` and normalizing is enough.”** No; overwrite, weird extension, Unicode, and platform path quirks remain. Use server-generated opaque IDs.

**“UUIDs are security.”** No; a UUID is an identifier; verify owner/tenant/ACL before serving bytes.

**“DB rollback via `@Transactional` rolls back the filesystem automatically.”** No; use states, cleanup/reconciliation, and idempotency.

**“Storing outside source guarantees persistence.”** Only if storage is properly mounted/backed up/replicated and not on an ephemeral writable layer.

**“An `attachment` header replaces read permissions.”** No; it only influences browser handling. Authorization is an application decision.

**“Using WebFlux uploads removes the need to inspect content.”** No; every client upload is untrusted.

## 21. Operations and Self-Assessment Checklist

Before releasing upload/download features, verify the essentials:

1. Storage paths reside **outside** `src/`, `build/`, static locations, public webroot, and JARs.
2. `UPLOAD_ROOT` is provided by operators as an absolute path with proper ACLs and durable mounts.
3. Clients **never dictate** full paths or storage keys; server-generated filenames are unique and created with `CREATE_NEW`/object preconditions.
4. Sizes, MIME/formats, scanning/quarantine, quotas/rate limits/CSRF match the threat model.
5. Downloads look up metadata and verify authn/authz per owner/tenant/ACL/status before opening files.
6. Private endpoints are not exposed directly by Spring `ResourceHandler`, reverse proxies, CDNs, or bucket ACLs.
7. Sensitive file responses include headers curbing inline interpretation and inappropriate caching.
8. Partial/orphan file handling, deletion/retention, idempotency, and DB consistency are designed.
9. Backups, restores, post-restart/redeploy persistence checks, and multi-instance behavior are verified.
10. Tests cover traversal, ownership, multipart limits, write errors, and download policies.

**Self-check questions:**

- Why shouldn't user invoices be placed under `src/main/resources/static/uploads`, even if only authenticated users can upload?
- How does `spring.servlet.multipart.location` differ from `app.upload.root`?
- Why is `server.address=127.0.0.1` only appropriate for local demos and not a substitute for production authorization?
- When two pods have separate local filesystems, why can an upload on A return 404 on B despite running the exact same JAR?
- Why must raw original filenames never be turned into a `Path` and written under the root?
- File bytes finished copying, then database metadata rolled back: how should this be handled?
- If an asset is genuinely public, how do you publish an approved copy without opening the private store?
- Why do `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff` not replace read authorization?

**Remember:** user files are runtime data with their own permissions and lifecycles. Store them outside source/classpath/public resources, address storage via server-generated IDs, enforce authorization on downloads, and deploy durable storage independent of application artifacts.

### References

- Spring Boot 3.3 — Servlet Web Applications, Static Resources: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties (multipart): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — Multipart Forms: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Framework 6.1 — `MultipartFile` JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- OWASP — File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- Java 17 — `Files` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
