# Building a Large File Ingestion Flow with Size Limits and Resource Cleanup

> **Module:** Spring Boot - web-runtime · **Group:** Integrated Practice. This lesson builds **two file upload APIs** on **Spring Boot 4.1.2, Java 17+**: `multipart/form-data` for browsers and `application/octet-stream` for clients streaming raw bytes. Both share a service that reads via a **bounded buffer**, checks **actual bytes read** (never trusting `Content-Length` alone), computes SHA-256, writes to a staging file, publishes via atomic move, and deletes incomplete files in `finally`. The lesson explains Servlet multipart temporary storage overhead, limits across reverse proxy/Tomcat/app/disk, client disconnects, SIGKILL and janitors, untrusted-content security, JUnit real-port tests, and operational scenarios. **This demo has no authentication, antivirus scanning, or download endpoint; never expose it publicly.**

## 1. Objectives and Success Criteria

Learners will be able to:

1. Distinguish **application-level streaming copy**, **raw Servlet request-body streaming**, **Servlet multipart spooling**, and **proxy buffering**, avoiding the false claim that `MultipartFile.getInputStream()` guarantees end-to-end streaming.
2. Budget **max-file-size, max-request-size, max-parts, per-part headers, actual read bytes, concurrent requests, disk quota, and upload duration**, knowing which layer enforces each bound.
3. Avoid `MultipartFile.getBytes()` or `InputStream.readAllBytes()` for large files; explain heap pressure vs temporary disk pressure.
4. Set up **private stage/ready storage** using server-generated random filenames, never using `getOriginalFilename()` as a path.
5. Use `try-with-resources` for `InputStream`/`OutputStream` and `finally` to clean up `.part` files and semaphore permits even on read/write/move failures.
6. Reject empty bodies (400), exceeded limits (413), saturated writers (429), and unsupported `Content-Encoding` (415); distinguish Spring MVC errors from edge/container rejections that reset connections.
7. Compute SHA-256 in a single copy pass, validate actual byte count/length, and publish only after writing finishes cleanly.
8. Run a Java 17 Maven project containing the MVC controller, service, error advice, and JUnit integration tests on a random TCP port, plus `curl` tests for multipart/raw/oversize cases.
9. Design cleanup after **crash/SIGKILL** using TTL/leases/GC without deleting files belonging to active uploads.
10. Extend cleanly toward object storage, resumable uploads, WebFlux `PartEvent`, antivirus/CDR, tenant quotas, and idempotency.

## 2. Data Flow: Why Is There More Than One Buffer?

~~~text
Browser / CLI / mobile application
      |
      | POST multipart/form-data or application/octet-stream
      v
CDN / WAF / API gateway / Ingress / reverse proxy
      | request size, rate, timeout, body buffering/temp storage
      v
Spring Boot embedded Tomcat :8080
      |
      +-- MULTIPART:
      |     Servlet Part parser
      |     -> max-file-size/max-request-size/parts count
      |     -> memory or servlet temporary file
      |     -> MultipartFile.getInputStream()
      |
      +-- RAW OCTET-STREAM:
            HttpServletRequest.getInputStream()
            -> read as bytes arrive via connector/proxy
      |
      v
UploadService.store()
      | semaphore -> 16 KiB copy loop -> actual byte counter
      | SHA-256 update -> private stage/<random>.part
      | validate full size/nonempty -> close output
      | ATOMIC_MOVE -> private ready/<UUID>.bin
      v
HTTP 201 JSON receipt {id,bytes,sha256}
~~~

In Spring MVC, `MultipartFile` may keep contents in memory or a temporary disk file. Spring Framework Javadoc explicitly states temporary storage is cleared at the end of request processing; developers must copy to persistent storage for anything outliving the request. Therefore:

- `file.getInputStream()` **avoids allocating a full-file `byte[]` in the controller**.
- It **does not guarantee the parser did not already spool the entire file to temp disk before calling the controller**.
- An `application/octet-stream` endpoint reading `HttpServletRequest.getInputStream()` can stream as bytes arrive, though proxies/connectors may still buffer.
- If ingress already buffered the whole body, a 16 KiB buffer in the backend cannot reduce ingress temp pressure.
- Streaming does not mean zero-copy, nor does it automatically prevent disk exhaustion, CPU DoS, or multipart header bombs.

### 2.1. Four File Areas Needing Clear Ownership

| Storage | Example | Ownership / Cleanup |
| --- | --- | --- |
| Reverse proxy temp | Nginx request-body temp | Proxy, not the application |
| Servlet multipart temp | `spring.servlet.multipart.location` | Servlet container/multipart resolver, typically end of request |
| Application staging | `app.upload.root/stage/*.part` | App `finally` and orphan janitor |
| Application ready/quarantine | `app.upload.root/ready/<id>.bin` | Business retention, ACLs, delete jobs |

A single multipart upload can consume disk in the **proxy**, **Servlet temp**, and **app staging** simultaneously. Moving staging to another volume does not eliminate Servlet temp usage. For very large concurrent uploads, monitor disk bytes, inodes, quotas, and every volume rather than only Java heap.

### 2.2. Proper Upload State Lifecycle

~~~text
RECEIVING -> STAGING (.part, private)
                  |
                  +-- size violation ----> REJECTED -> cleanup
                  +-- client abort ------> FAILED -> cleanup
                  +-- disk I/O error ----> FAILED -> cleanup
                  +-- invalid/empty -----> REJECTED -> cleanup
                  |
                  v
              VALIDATED
                  |
                  v
         ATOMIC PUBLISH TO READY
                  |
                  v
          COMMITTED -> HTTP 201
                  |
                  v
         Retention / authorized delete
~~~

Never let consumers read partially written files. If a client loses the 201 response after server commit, the data **may already have been saved**; production requires an idempotency key and persisted receipts to handle retries without creating duplicates. Because this demo lacks a receipt DB, retries can create two files.

## 3. Upload Limits Must Exist at Multiple Layers

### 3.1. Categorizing Thresholds

| Threshold | Controls | Layer |
| --- | --- | --- |
| Edge max body size | Total request sent through proxy | CDN/Ingress |
| Max multipart file | Single file part | Servlet parser |
| Max multipart request | Full multipart body including boundaries/fields | Servlet parser |
| Max parts / per-part headers | Header/metadata amplification | Tomcat parser |
| Max HTTP request headers | Overall request headers | Tomcat/edge |
| Max actual bytes | Bytes read by the app, even without Content-Length | `UploadService` |
| Max concurrent storage copies | Writers actively writing to stage | Semaphore in service |
| Tenant quota | Bytes/day/object count per user or org | DB/shared rate limiter |
| Max on-disk | Tmp, stage, ready, scan quarantine | Filesystem/volume policy |
| Upload timeout | Slow clients, stalled writes, network stalls | Proxy/server/client |
| Max decoded/decompressed content | ZIP/archive/encoded requests | Validator/scanner/parser |

Merely raising `max-file-size` from 1 MB to 50 MB **does not** address concurrent uploads, part floods, disk leaks, or malware. **Edge limits** reject oversized traffic before consuming backend resources, yet once a request reaches the application, exact byte counting is still mandatory.

### 3.2. Spring Boot 4.1.2 Properties on Servlet/MVC

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=52MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.location=${UPLOAD_TMP_DIR:${java.io.tmpdir}}
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true
~~~

Per Spring Boot docs, defaults are `max-file-size=1MB`, `max-request-size=10MB`, and `file-size-threshold=0B`. Spring's `50MB` `DataSize` uses 1024-based units per configuration; this lab adds an exact **52,428,800** byte cap (50 MiB) enforced inside the read loop.

- `file-size-threshold=0B` flushes parts to disk early to avoid holding full files on the heap, though the Servlet parser still receives the multipart payload.
- `max-request-size` must allow for multipart overhead (headers, boundaries, metadata) beyond file bytes; reserve controlled headroom.
- `location` is only **Servlet temp**, separate from `app.upload.root`. If supplying a custom `UPLOAD_TMP_DIR`, create a writable directory first; production should mount a quota-enforced volume.
- `resolve-lazily=true` only defers parsing until the part is accessed—it **does not make upload streaming safer by itself**.
- `strict-servlet-compliance=true` enforces standard `multipart/form-data` Servlet semantics; if `multipart/mixed` is needed, design and test separately.
- Never set `max-file-size=-1` or `max-request-size=-1` just to silence 413 errors.

### 3.3. Tomcat-Specific Hardening

~~~properties
server.tomcat.max-part-count=4
server.tomcat.max-part-header-size=1KB
server.max-http-request-header-size=8KB
~~~

`max-part-count` stops clients from sending thousands of tiny form parts; `max-part-header-size` stops oversized part metadata headers; the global HTTP header limit does not replace them. `server.tomcat.*` properties **do not automatically apply to Jetty or Reactor Netty**. Parse limits may result in HTTP 400/413 or connection resets depending on the connector/proxy.

`server.tomcat.max-swallow-size` governs how unread request bodies are drained after rejection; this explains why oversized uploads sometimes trigger connection resets instead of JSON 413 responses. Never set it to unlimited casually just to "always see 413."

### 3.4. Content-Length: Check Early, Never Trust Alone

A client may send:

~~~http
POST /api/uploads/raw HTTP/1.1
Host: localhost:8080
Content-Type: application/octet-stream
Content-Length: 1024
~~~

With `Transfer-Encoding: chunked`, there is no fixed `Content-Length`, and proxies/HTTP2 frame bodies differently. Clients can also abort mid-stream or misstate lengths. Therefore:

~~~text
if (declaredLength > limit) -> reject early
read repeatedly into small buffer
if (newBytes > limit - bytesAlreadyRead) -> reject before write
after EOF: bytesAlreadyRead must be > 0
if declaredLength >= 0: optionally compare to actual bytes
publish only when all checks passed
~~~

Comparing `newBytes > limit - alreadyRead` avoids `long` overflow from `alreadyRead + newBytes`. For compressed bodies, `Content-Length` reflects **compressed bytes**; the demo rejects non-`identity` raw `Content-Encoding`, whereas production endpoints accepting compressed bodies must bound **decompressed** bytes.

### 3.5. Disk Budget and Semaphores Do Not Block the Parser Before the Controller

Suppose the service allows 3 writers of up to 50 MiB each: **app staging** alone uses up to ~150 MiB. Yet Servlet may already spool 20 multipart requests × 50 MiB before they ever acquire a semaphore permit, and the proxy may buffer even more. Thus 3 permits **does not guarantee only 150 MiB of uploads are in flight**. You still need upstream concurrency/rate limits, per-tenant quotas, disk-free alerts, and shutdown controls. Filesystem free space, inodes, and IOPS can bottleneck before heap.

## 4. Filename and Storage Location Security

### 4.1. Never Use originalFilename as a Path

`MultipartFile.getOriginalFilename()` can be `../../evil.bin`, `C:\fakepath\...`, deceptive Unicode names, or null/empty; it is untrusted client input. Never write:

~~~java
// UNSAFE: user-supplied name can traverse or overwrite files.
Path p = root.resolve(file.getOriginalFilename());
file.transferTo(p);
~~~

Use server-generated random IDs. In this demo, published files are always named `<UUID>.bin` inside private directories:

~~~text
data/
  stage/
    incoming-<random>.part
  ready/
    <uuid>.bin
~~~

`Path.normalize()` alone does not eliminate symlink races if an attacker can write inside the root directory. Production requires admin/platform-provisioned roots, strict user/ACL restrictions preventing untrusted local users from altering staging dirs, and keeping these folders outside the webroot. In multi-tenant storage, verify tenant/owner authorization on every access, delete, or download operation.

### 4.2. Content-Type, Extensions, and SHA-256 Do Not Prove a File Is Safe

- The `MultipartFile.getContentType()` MIME header can be spoofed by clients.
- Extensions can lie; magic bytes are only a preliminary format hint.
- Real JPEG/PNG/PDF/ZIP files can still carry malicious payloads or parser exploits.
- SHA-256 verifies integrity/deduplication, **not** malware absence.
- PDF/Office files need malware scanning/CDR per policy; ZIPs must limit expanded bytes, item counts, and recursion/CPU (ZIP bombs).
- Quarantine files prior to scanning; never publish under public URLs before passing checks.
- For downloads, use opaque IDs + authorization, safe `Content-Disposition`, `X-Content-Type-Options: nosniff`, and block XSS/executable execution.

**This demo accepts opaque bytes only, never parses contents, and provides no download endpoint.** Unscanned uploads must never be treated as safe for other users to open.

## 5. Cleanup and Commit: Normal Paths vs Crashes

### 5.1. try-with-resources

The `InputStream` from `MultipartFile.getInputStream()` must be closed by the caller; the staging `OutputStream` must close before moving. Never hand a `MultipartFile` to a background thread after returning a controller response, because Servlet temp files may already be deleted. For background scanning, first copy into app-owned persistent staging, store metadata/job IDs, and have workers read only app-owned storage.

### 5.2. finally and Atomic Publish

A sound pattern:

~~~java
// Fragment; stagingDirectory and readyDirectory are private Paths.
Path stage = null;
try {
    stage = Files.createTempFile(stagingDirectory, "part-", ".tmp");
    try (OutputStream out = Files.newOutputStream(stage)) {
        // bounded streaming copy + checksum + validators
    }
    Files.move(stage, readyDirectory.resolve("opaque.bin"),
            StandardCopyOption.ATOMIC_MOVE);
    stage = null;
}
finally {
    if (stage != null) Files.deleteIfExists(stage);
}
~~~

When `Files.move(... ATOMIC_MOVE)` is supported on the same filesystem, consumers never observe half-written ready files. **Atomic rename does not equal fsync/power-loss durability**; production may require `FileChannel.force()`, directory metadata sync, DB receipt transactions, or object store commit semantics. If a cross-filesystem move fails, the demo **never silently falls back to a non-atomic copy**.

If `Files.deleteIfExists` fails, never claim cleanup succeeded; alert, increment a cleanup-failure metric, and let the janitor clean up. Where untrusted local users can write or swap symlinks, this API alone does not prevent TOCTOU; strict directory permissions and secure filesystem ops are required.

### 5.3. SIGTERM, SIGKILL, and Orphan Janitors

- On request errors while the JVM stays alive, `try/finally` cleans `.part` files and releases permits.
- On client disconnects, raw `InputStream` may throw `IOException`, though proxy buffering can delay detection.
- On SIGTERM with graceful shutdown, finite uploads can finish within the grace budget if server/app are configured properly.
- On SIGKILL/OOM/crashes, **`finally` never runs**; staged files can linger on persistent volumes or object stores.
- An orphan janitor must check leases, owners, last activity, TTLs, tenants, namespaces, and grace periods—never delete `.part` files based solely on old filesystem mtimes while an upload is still active.

State design in DB/object store:

~~~text
upload_id | tenant_id | stage_key | state
bytes_received | lease_owner | lease_expires_at
checksum | committed_key | created_at | retention_until
~~~

The janitor deletes only when the lease is genuinely expired, the owner is inactive, and a safety delay has passed—never accepting arbitrary client paths. For object-store multipart uploads, call `AbortMultipartUpload` and configure lifecycle rules for incomplete uploads. Ready blobs lacking committed DB receipts require reconciliation; never auto-delete valid business data simply because "no 201 response was sent."

## 6. Spring Boot 4.1.2 / Java 17 Project

Endpoints:

| API | Method | Content-Type | Result |
| --- | --- | --- | --- |
| `/api/uploads/multipart` | POST | `multipart/form-data`, part=`file` | HTTP 201 receipt |
| `/api/uploads/raw` | POST | `application/octet-stream` | HTTP 201 receipt |
| `/api/uploads/health` | GET | text | Smoke test |

No public GET/DELETE file endpoints, auth, or scanner are included. Bind to localhost so an open upload service is never exposed to the Internet.

### 6.1. Project Structure

~~~text
large-upload-lab/
  pom.xml
  src/main/java/com/example/uploadlab/
    LargeUploadApplication.java
    UploadService.java
    UploadController.java
    UploadErrorAdvice.java
  src/main/resources/
    application.properties
  src/test/java/com/example/uploadlab/
    UploadIntegrationTest.java
  data/
    stage/   # auto-created by service
    ready/
~~~

### 6.2. pom.xml

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
    <artifactId>large-upload-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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
~~~

The MVC starter brings Servlet/Tomcat multipart support, Actuator provides health, and the MVC test starter provides JUnit and `@SpringBootTest`. No Apache Commons FileUpload dependency is needed in the demo.

### 6.3. LargeUploadApplication.java

~~~java
package com.example.uploadlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LargeUploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(LargeUploadApplication.class, args);
    }
}
~~~

### 6.4. application.properties

~~~properties
spring.application.name=large-upload-lab
server.address=127.0.0.1
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=52MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.location=${UPLOAD_TMP_DIR:${java.io.tmpdir}}
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true

server.tomcat.max-part-count=4
server.tomcat.max-part-header-size=1KB
server.max-http-request-header-size=8KB

# Exact 50 MiB in bytes; applies to both multipart and raw readers.
app.upload.max-bytes=52428800
app.upload.root=${APP_UPLOAD_ROOT:./data}

management.endpoints.web.exposure.include=health
~~~

In production, `server.address` must not remain `127.0.0.1` if a Service connects via Pod IP. Place Servlet temp on a writable volume with quotas/metrics, and give app root restricted permissions. If a custom `UPLOAD_TMP_DIR` does not exist or is not writable, the multipart parser may fail before the controller runs.

### 6.5. UploadService.java — Bounded Copy + Limits + SHA-256 + Cleanup

~~~java
package com.example.uploadlab;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;
import java.util.concurrent.Semaphore;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class UploadService {

    private final Path stageDir;
    private final Path readyDir;
    private final long maxBytes;

    // Per-instance storage writer limit; not a cluster or tenant quota.
    private final Semaphore slots = new Semaphore(3);

    public record Receipt(String id, long bytes, String sha256) {}

    public UploadService(
            @Value("${app.upload.root}") String rootLocation,
            @Value("${app.upload.max-bytes}") long maxBytes)
            throws IOException {

        if (maxBytes <= 0) {
            throw new IllegalArgumentException("maxBytes must be positive");
        }
        this.maxBytes = maxBytes;

        Path root = Path.of(rootLocation).toAbsolutePath().normalize();
        // Demo assumes root is owned by app/platform, not writable
        // by untrusted local users (enforce via ACLs in production).
        Files.createDirectories(root);
        stageDir = Files.createDirectories(root.resolve("stage"));
        readyDir = Files.createDirectories(root.resolve("ready"));
    }

    public Receipt store(InputStream input, long claimedLength)
            throws IOException {

        if (claimedLength == 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "empty file");
        }
        if (claimedLength > maxBytes) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "declared size too large");
        }

        if (!slots.tryAcquire()) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS,
                    "too many active storage copies");
        }

        Path stage = null;
        try {
            stage = Files.createTempFile(stageDir, "incoming-", ".part");

            MessageDigest sha256 = newSha256();
            long written = 0L;
            byte[] buffer = new byte[16 * 1024];

            try (OutputStream out = Files.newOutputStream(
                    stage, StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (count == 0) {
                        continue;
                    }
                    if (count > maxBytes - written) {
                        throw new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "actual uploaded bytes exceed limit");
                    }
                    out.write(buffer, 0, count);
                    sha256.update(buffer, 0, count);
                    written += count;
                }
            }

            if (written == 0) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "empty file");
            }
            if (claimedLength >= 0 && written != claimedLength) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "declared size does not match actual bytes");
            }

            String id = UUID.randomUUID().toString();
            Path published = readyDir.resolve(id + ".bin");

            // If ATOMIC_MOVE is unsupported, throw and clean up stage;
            // never fall back to a non-atomic copy into ready.
            Files.move(stage, published,
                    StandardCopyOption.ATOMIC_MOVE);
            stage = null;

            return new Receipt(
                    id, written, HexFormat.of().formatHex(sha256.digest()));
        }
        finally {
            try {
                if (stage != null) {
                    Files.deleteIfExists(stage);
                }
            }
            finally {
                // Release permit even if stage cleanup deletion fails.
                slots.release();
            }
        }
    }

    private static MessageDigest newSha256() {
        try {
            // Never share MessageDigest: instances are not thread-safe.
            return MessageDigest.getInstance("SHA-256");
        }
        catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                    "standard SHA-256 unavailable", e);
        }
    }
}
~~~

Key checks:

- `claimedLength` is a hint; raw chunked uploads pass `-1`, making actual byte counting mandatory.
- `maxBytes - written` avoids overflow and throws 413 **before writing an over-limit chunk**.
- The 16 KiB buffer bounds app copy memory, excluding Servlet/proxy buffers.
- `MessageDigest` is instantiated **per request**, avoiding shared mutable state.
- Stage uses a random temp name; `getOriginalFilename()` never touches paths.
- `OutputStream` closes **before moving**, catching write/close/flush errors.
- Atomic move works when supported by the filesystem and both directories share a storage root; if unavailable, fail rather than exposing partial files.
- `stage=null` runs only after the move succeeds. `finally` deletes stage on any thrown exception, including `ResponseStatusException`.
- Nested `finally` ensures `slots.release()` even if cleanup throws `IOException`.
- If the client misses the 201 response, the blob may already be committed; the demo lacks idempotency/DB receipts.
- File-type scanning, tenant authorization, upload count caps, and fsync are absent and must be added before production.

### 6.6. UploadController.java — Two Ingestion Paths

~~~java
package com.example.uploadlab;

import java.io.IOException;
import java.io.InputStream;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {
    private final UploadService service;

    public UploadController(UploadService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public String health() {
        return "upload-demo-ready";
    }

    @PostMapping(
            path = "/multipart",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadService.Receipt> multipart(
            @RequestParam("file") MultipartFile file)
            throws IOException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "empty part");
        }

        // MultipartFile may already be spooled by Servlet parser.
        try (InputStream in = file.getInputStream()) {
            UploadService.Receipt receipt =
                    service.store(in, file.getSize());
            return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
        }
    }

    @PostMapping(
            path = "/raw",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<UploadService.Receipt> raw(
            HttpServletRequest request)
            throws IOException {

        String contentEncoding = request.getHeader("Content-Encoding");
        if (contentEncoding != null
                && !contentEncoding.equalsIgnoreCase("identity")) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "encoded request body unsupported");
        }

        // May be -1 (unknown/chunked); service counts all bytes.
        try (InputStream in = request.getInputStream()) {
            UploadService.Receipt receipt =
                    service.store(in, request.getContentLengthLong());
            return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
        }
    }
}
~~~

With multipart, the Servlet parser has already processed boundaries and `file.getSize()` reports the part size; never try reading `HttpServletRequest.getInputStream()` again after multipart parsing. For raw uploads, `Content-Length` covers the entire body when provided. Neither path **serves files** or uses client-supplied filenames.

### 6.7. UploadErrorAdvice.java

~~~java
package com.example.uploadlab;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadErrorAdvice {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            MaxUploadSizeExceededException ignored) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "multipart_size_limit_exceeded"));
    }
}
~~~

When Spring MVC catches `MaxUploadSizeExceededException`, this advice maps it to 413. If the gateway/Tomcat rejects **before `DispatcherServlet`** or drops the connection due to unread body bytes, the response may differ or reset. `ResponseStatusException` is handled by Spring; exact error JSON shapes are not guaranteed unless you define a formal contract.

## 7. Running Locally and Testing with cURL

### 7.1. Build and Run

~~~bash
java -version
mvn -version
mvn clean verify
mvn spring-boot:run
~~~

Or run the packaged JAR directly:

~~~bash
java -jar target/large-upload-lab-0.0.1-SNAPSHOT.jar
~~~

Never run both commands simultaneously on port 8080. Smoke test:

~~~bash
curl -i http://127.0.0.1:8080/api/uploads/health
curl -i http://127.0.0.1:8080/actuator/health
~~~

The demo endpoint returns exact body:

~~~text
upload-demo-ready
~~~

Actuator status reflects service health and config; health 200 does not prove enough disk space remains for uploads.

### 7.2. Generating Test Data

POSIX/Linux/macOS/WSL:

~~~bash
mkdir -p test-data
dd if=/dev/zero of=test-data/one-mib.bin bs=1048576 count=1
wc -c test-data/one-mib.bin
dd if=/dev/zero of=test-data/over-limit.bin bs=1048576 count=51
wc -c test-data/over-limit.bin
~~~

The first file is **1,048,576 bytes (1 MiB)** and the second is **53,477,376 bytes (51 MiB)**. Never run these commands against production upload endpoints. Use synthetic data to avoid exposing user information.

### 7.3. Successful Multipart POST

~~~bash
curl -i \
  -F "file=@test-data/one-mib.bin;type=application/octet-stream" \
  http://127.0.0.1:8080/api/uploads/multipart
~~~

On success, HTTP status **201** and receipt fields:

~~~json
{
  "id": "26d4331a-6d87-48f5-8927-f9aa594ad2a3",
  "bytes": 1048576,
  "sha256": "(64 hexadecimal characters)"
}
~~~

The ID and digest above are **illustrative placeholders**, not actual outputs; UUIDs are random. The file is saved at `data/ready/<id>.bin`, and `stage` has no leftover file for the completed request.

~~~bash
find ./data/stage -type f
find ./data/ready -type f
sha256sum test-data/one-mib.bin
~~~

Compare the local file's SHA-256 against the receipt. On macOS, use `shasum -a 256` if `sha256sum` is absent. Matching hashes confirm integrity, not benign content.

### 7.4. Successful Raw Stream POST

~~~bash
curl -i \
  -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/one-mib.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

`--data-binary` preserves raw bytes without form encoding. The server reads through `ServletInputStream` with a 16 KiB buffer. If cURL or a proxy buffered the body first, that does not prove end-to-end streaming; measure at the connector/proxy separately when needed.

### 7.5. Oversized Multipart

~~~bash
curl -v \
  -F "file=@test-data/over-limit.bin" \
  http://127.0.0.1:8080/api/uploads/multipart
~~~

With `max-file-size=50MB` and a 51 MiB file, the request must be **rejected** with no ready file created. You may receive HTTP 413 or a connection reset if Tomcat/the edge stops reading the body. Do not hardcode an expectation that every container returns the advice's JSON.

### 7.6. Oversized Raw

~~~bash
curl -v \
  -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/over-limit.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

Raw uploads bypass `spring.servlet.multipart.max-file-size`; the app rejects based on `Content-Length` when present or actual bytes read when absent. If the server rejects before cURL finishes sending, the client may report EOF/reset; the key invariant is **no oversized ready file is published**.

### 7.7. Empty Body and Wrong Content-Type

~~~bash
: > test-data/empty.bin
curl -i -F "file=@test-data/empty.bin" \
  http://127.0.0.1:8080/api/uploads/multipart

curl -i -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/empty.bin \
  http://127.0.0.1:8080/api/uploads/raw

curl -i -X POST -H "Content-Type: text/plain" --data "abc" \
  http://127.0.0.1:8080/api/uploads/raw
~~~

Empty payloads return 400; `text/plain` fails the raw endpoint's `consumes=application/octet-stream`, typically returning 415. If intending to support text/images/PDFs, add content validation/quarantine rather than trusting the request `Content-Type`.

### 7.8. Simulating Client Abort (Not Fully Deterministic)

~~~bash
curl --limit-rate 20k --max-time 2 \
  -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/one-mib.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

cURL times out mid-transfer, though socket/proxy buffering makes the exact moment the server sees EOF nondeterministic. What network fault-injection tests must verify is **zero partial ready blobs**, cleanup of staging and Servlet temp files after request completion, and zero leaked semaphore permits. Never assume from one cURL run that every client abort triggers `IOException` instantaneously.

### 7.9. Testing Chunked / Unknown Content-Length

A client may use `Transfer-Encoding: chunked`; the raw handler sees `getContentLengthLong()=-1` and must count bytes directly. How chunking is sent depends on cURL/runtime:

~~~bash
curl --http1.1 -v \
  -H "Content-Type: application/octet-stream" \
  -H "Transfer-Encoding: chunked" \
  --data-binary @test-data/one-mib.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

Check cURL verbose output to verify **actual** request framing; if a proxy re-frames the body, the test no longer reflects a direct connection. The application counter still enforces the byte limit even without a length header.

## 8. JUnit Integration Tests Against Real Embedded Tomcat

The test below boots a real server on `RANDOM_PORT`, sends bytes via Java 17 `HttpClient`, lowers the app cap to 1 MiB for CI, and isolates storage under `target`. It tests a 2048-byte upload, empty payload, over-limit rejection, and multipart filename traversal, then removes the temp test directory afterward. It **does not test** proxies, OS Servlet temp dirs, SIGKILL, disk-full errors, or virus scanning.

### 8.1. UploadIntegrationTest.java

~~~java
package com.example.uploadlab;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.UUID;
import java.util.stream.Stream;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "app.upload.max-bytes=1048576",
        "spring.servlet.multipart.max-file-size=2MB",
        "spring.servlet.multipart.max-request-size=3MB"
    }
)
class UploadIntegrationTest {

    private static final Path ROOT = Path.of(
            "target", "upload-it-" + UUID.randomUUID());

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @LocalServerPort
    int port;

    @DynamicPropertySource
    static void configureRoot(DynamicPropertyRegistry registry) {
        registry.add("app.upload.root",
                () -> ROOT.toAbsolutePath().toString());
    }

    private HttpResponse<String> post(
            String endpoint, String contentType,
            HttpRequest.BodyPublisher publisher) throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + endpoint))
                .header("Content-Type", contentType)
                .POST(publisher)
                .build();

        return CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void rawSmallFileCommitsAndCleansStage() throws Exception {
        byte[] content = new byte[2048];
        java.util.Arrays.fill(content, (byte) 'A');

        HttpResponse<String> response = post(
                "/api/uploads/raw", "application/octet-stream",
                HttpRequest.BodyPublishers.ofByteArray(content));

        assertEquals(201, response.statusCode(), response.body());
        assertTrue(response.body().contains("\"bytes\":2048"),
                response.body());
        assertEquals(0, stageCount());
        try (Stream<Path> paths = Files.list(ROOT.resolve("ready"))) {
            assertTrue(paths.anyMatch(Files::isRegularFile));
        }
    }

    @Test
    void rawOversizedIsRejectedAndHasNoStage() throws Exception {
        byte[] content = new byte[1_048_577];

        // On local server this typically returns 413. However if the container
        // closes early with unread body bytes, the client may see IOException;
        // evaluate tests alongside connector/transport behavior.
        HttpResponse<String> response = post(
                "/api/uploads/raw", "application/octet-stream",
                HttpRequest.BodyPublishers.ofByteArray(content));

        assertEquals(413, response.statusCode(), response.body());
        assertEquals(0, stageCount());
    }

    @Test
    void multipartIgnoresUntrustedOriginalName() throws Exception {
        String boundary = "----test-" + UUID.randomUUID();
        byte[] file = new byte[256];

        byte[] prefix = (
                "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; "
                + "filename=\"../../evil.bin\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        byte[] suffix = (
                "\r\n--" + boundary + "--\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        HttpRequest.BodyPublisher publisher =
                HttpRequest.BodyPublishers.concat(
                    HttpRequest.BodyPublishers.ofByteArray(prefix),
                    HttpRequest.BodyPublishers.ofByteArray(file),
                    HttpRequest.BodyPublishers.ofByteArray(suffix));

        HttpResponse<String> response = post(
                "/api/uploads/multipart",
                "multipart/form-data; boundary=" + boundary,
                publisher);

        assertEquals(201, response.statusCode(), response.body());
        assertTrue(response.body().contains("\"bytes\":256"),
                response.body());
        assertEquals(0, stageCount());
    }

    @Test
    void emptyRawRejected() throws Exception {
        HttpResponse<String> response = post(
                "/api/uploads/raw", "application/octet-stream",
                HttpRequest.BodyPublishers.noBody());

        assertEquals(400, response.statusCode());
        assertEquals(0, stageCount());
    }

    private static long stageCount() throws IOException {
        try (Stream<Path> paths = Files.list(ROOT.resolve("stage"))) {
            return paths.count();
        }
    }

    @AfterAll
    static void cleanupTestRoot() throws IOException {
        if (Files.notExists(ROOT)) return;
        try (Stream<Path> paths = Files.walk(ROOT)) {
            paths.sorted(Comparator.reverseOrder())
                    .forEach(path -> {
                        try {
                            Files.deleteIfExists(path);
                        }
                        catch (IOException e) {
                            throw new UncheckedIOException(e);
                        }
                    });
        }
    }
}
~~~

**Verification notes:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` runs a real embedded server rather than mocking controllers. `@DynamicPropertySource` assigns an isolated root per test run. `HttpClient` is **not `AutoCloseable` in Java 17**, so do not wrap it in `try-with-resources`. A 1 MiB + 1 raw request is rejected before creating a stage file when `Content-Length` is known; on some connectors early rejection can reset TCP, so environment-specific negative tests may treat transport resets as rejection and verify no partial file exists.

To keep CI 100% deterministic across all HTTP connectors, complement early rejection with a **server-side unit test of `store()`** passing an `InputStream` with claimed length `-1` and 1 MiB + 1 bytes; that forces the application loop to read up to the limit and throw 413 in-process regardless of client unread-body behavior. For a clean Maven/Spring test example, this class demonstrates the HTTP-level outcomes.

Run:

```bash
mvn test
```

Expected: JUnit tests pass with compatible runtime/connectors and a writable `target` directory; exact Surefire output varies by version. **These examples were reviewed for logic, not executed under Maven while authoring.**

## 9. Standalone Java 17: Bounded-Byte Copy

Create `BoundedCopyDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BoundedCopyDemo {

    static long copy(InputStream in, OutputStream out, long max)
            throws IOException {

        byte[] buffer = new byte[4];
        long total = 0;
        int n;

        while ((n = in.read(buffer)) != -1) {
            if (n > max - total) {
                throw new IOException("limit exceeded");
            }
            out.write(buffer, 0, n);
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        byte[] data = "abcdefghij".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ok = new ByteArrayOutputStream();
        System.out.println("copied=" +
                copy(new ByteArrayInputStream(data), ok, 10));
        System.out.println("exact=" + ok.toString("UTF-8"));

        ByteArrayOutputStream limited = new ByteArrayOutputStream();
        try {
            copy(new ByteArrayInputStream(data), limited, 8);
        }
        catch (IOException expected) {
            System.out.println(expected.getMessage());
        }
        System.out.println("partial-bytes=" + limited.size());
    }
}
~~~

Run:

~~~bash
javac --release 17 BoundedCopyDemo.java
java BoundedCopyDemo
~~~

Expected stdout:

~~~text
copied=10
exact=abcdefghij
limit exceeded
partial-bytes=8
~~~

With 10 bytes and a 4-byte buffer, `InputStream` yields 4+4+2. With limit 8, the final chunk is rejected **before writing**, leaving 8 bytes in the output; a real application must delete the partial staging file inside `finally`. This is a standalone Java 17 example without Spring.

## 10. Failure Modes: HTTP, Files, and Process Lifecycle

| Failure | Where Detected | Proper Behavior |
| --- | --- | --- |
| Multipart > file cap | Servlet parser / proxy | Reject, never create ready; 413 or reset |
| Raw > max bytes | `UploadService` | 413 (or transport abort), clean stage |
| Empty upload | Controller / service | 400, do not publish |
| Unsupported Content-Type | Spring mapping | 415 |
| Request `Content-Encoding: gzip` | Raw controller | 415; do not silently decompress |
| Three writers busy | Semaphore | 429; upstream rate still needs bounds |
| Client drops TCP mid-upload | `ServletInputStream`/connector | `IOException`/EOF, clean stage |
| File write throws `IOException`/disk full | `OutputStream` | No 201, cleanup + alert |
| Atomic move unsupported | `Files.move` | Never expose partial file, cleanup |
| SIGTERM / graceful | JVM + Boot + platform | Finish finite requests within budget |
| SIGKILL / OOM | Kernel / orchestrator | `finally` skipped; rely on janitor/retention |
| Lost 201 response | Client retry | Idempotency receipt contract |
| K8s Pod deleted | Platform | Pod-local ephemeral storage lost |
| Multi-pod lookup on another node | Storage architecture | Use shared/object storage |
| Multiple files in one multipart | Parser / route contract | Cap parts and business file count |
| ZIP bomb / PDF exploit | Content scanner | Validate/quarantine before ready |
| Symlink / path traversal | Filesystem / storage layer | Random IDs, trusted root, ACLs |
| DB metadata commit fails after blob move | Business transaction | Reconciliation / compensation |
| Cleanup delete fails | Filesystem | Error metric, orphan janitor |

### 10.1. Client Disconnects

If the client drops before the multipart parser finishes, the controller may never run; the container cleans up Servlet-owned temp files per request lifecycle. If raw streaming breaks mid-read, `read()` throws and `service.finally` cleans up app stage. However, if a proxy already buffered the entire body, the backend can still commit despite client disconnect—require idempotency and receipt lookup rather than assuming client aborts roll back storage.

### 10.2. Disk Full and Permission Errors

If `out.write()`, `out.close()`, or `Files.move` throws `IOException`, no 201 is returned. `finally` tries to delete stage; if deletion also fails, raise an alert and let the janitor clean up. Proxy or Servlet temp disks can fill **before reaching the service**, requiring separate volume metrics. In containers with `readOnlyRootFilesystem=true`, mount writable temp and storage volumes owned by the right UID rather than running the JVM as root.

### 10.3. Shutdown Deadlines

Spring Boot graceful shutdown requires SIGTERM delivered to the Java process. Requests exceeding the grace budget are drained, cancelled, or failed per policy; staged files are deleted if `finally` executes. SIGKILL skips `finally`; on ephemeral Pod volumes files vanish with the Pod, whereas on persistent volumes/object stores orphans remain. Use leases/TTLs and reconciliation to clean up safely instead of blindly deleting any `.part` file.

### 10.4. Atomicity Differs from Durability

An atomic move between stage and ready on the same filesystem ensures consumers see **either the complete blob or nothing** once the rename succeeds. It does not guarantee `fsync`, cross-process metadata transactions, or survival across power loss. On object stores, write to temporary objects/UploadIds, complete multipart uploads after verifying parts/checksums, and only then commit business metadata. Strict durability requires testing commit order and fault injection.

## 11. Production Design: Content Security and Quotas

### 11.1. File Types and Access Control

A public upload endpoint must enforce:

- AuthN/AuthZ, deriving tenant ID from the authenticated principal rather than a request field.
- CSRF if browsers send session cookies, plus proper Origin/CORS policies.
- Rate limits, daily byte budgets, max active upload sessions, and object count caps.
- File type allowlists and strict parser validation (MIME/extension/magic bytes are only partial checks).
- Malware scanning/CDR, quarantine, and decompression bounds for ZIP/XML/Office files.
- Private storage outside webroot, non-executable permissions, and safe download headers.
- Random opaque IDs—never embed user filenames/paths in storage keys.
- Re-scanning files when signatures update if required by your threat model.
- Never logging raw file bytes, Auth headers, cookies, or PII in original filenames.
- Retention, legal holds, user deletion, and GDPR/data-handling policies.

### 11.2. Upload State, Retries, and Idempotency

Production can track:

~~~text
upload_id | tenant_id | idempotency_key_hash | state
stage_key | ready_key | bytes_expected | bytes_actual
sha256 | validated_type | scan_status
created_at | lease_expires_at | retention_until
~~~

States: `RECEIVING → STAGED → SCANNING → READY` or `FAILED/ABORTED`. If a client retries with the same `Idempotency-Key`, return the existing receipt once committed instead of storing a duplicate file. If an upload is still in progress, return 202 or 409 per contract. Scope keys per tenant, validate authorization and TTL; a content hash **does not replace** an idempotency key.

If DB metadata fails to commit after the file move, a reconciliation job handles orphaned ready blobs or runs compensation per policy—never treat cross-DB/filesystem writes as atomic.

### 11.3. Object Storage and Resumable Uploads

For multi-GiB files, consider direct client uploads to object storage via presigned URLs:

~~~text
Client -> app: create upload session (auth/quota)
App -> S3/object store: initiate multipart upload, scoped URLs
Client -> object store: upload parts with checksums
Client -> app: finalize with part ETags
App -> object store: verify + CompleteMultipartUpload
Scanner -> quarantine -> ready
Orphan janitor -> AbortMultipartUpload when TTL expires
~~~

Important caveat: an S3 multipart ETag **must not be assumed to equal the whole-file MD5**. Use provider-supported checksums, validate object size and permissions. Incomplete multipart uploads can incur storage bills until aborted or expired by lifecycle policies. Use `tus` or another resumable protocol for offset-based resume; avoid ad-hoc append-only designs without transactions/idempotency.

## 12. WebFlux/Reactive Has Different Semantics from Servlet MVC

In WebFlux, you work with `FilePart`, `Flux<PartEvent>`, and `DataBuffer`. Multipart properties differ:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=50MB
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.max-parts=4
~~~

These **do not control Servlet `MultipartFile`/Tomcat's parser**. With `Flux<PartEvent>`, Spring WebFlux docs emphasize that `DataBuffer`s must be **consumed, relayed, or released** to avoid leaks; apply backpressure, bounded queues, and cancellation cleanup. Never call `collectList()` on an entire file or run blocking file I/O on the Netty event loop.

API-illustration example (**not complete upload code**):

~~~java
// Hypothetical WebFlux handler fragment:
@PostMapping(value = "/reactive-upload",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> reactive(@RequestBody Flux<PartEvent> events) {
    // windowUntil(PartEvent::isLast), select FilePartEvent,
    // consume DataBuffers in a bounded pipeline, release on cancel,
    // count bytes, write staging, verify, atomic publish.
    return Mono.empty();
}
~~~

This snippet **does not actually consume the incoming data**—it is only a structural skeleton; never ship it to production. A real implementation must compose `DataBufferUtils` with cleanup hooks, handle late cancellation/part boundaries, and enforce per-part caps. "Reactive" alone solves neither disk quotas nor malware.

## 13. Observability, Operations, and Capacity Budgeting

| Metric / Alert | Meaning |
| --- | --- |
| `uploads_started_total` | Total upload attempts |
| `uploads_committed_total` | Successful commits |
| `uploads_rejected_total{reason}` | size/parts/type/auth/concurrency rejections |
| `upload_bytes_received_total` | Actual bytes read, not just header length |
| `upload_duration_seconds` | Upload latency and throughput |
| `upload_active_storage_copies` | Permits currently held |
| `upload_staged_bytes` | Application temp storage pressure |
| `upload_orphan_count/age` | Crash cleanup debt |
| `upload_cleanup_failures_total` | `Files.deleteIfExists`/`AbortMultipartUpload` errors |
| `upload_storage_move_errors_total` | Atomic move/quota/permission errors |
| `servlet_temp_disk_bytes` | Parser temp disk outside app stage |
| `edge_request_body_temp_bytes` | Reverse proxy buffer pressure |
| `disk_free_bytes/inodes` | Remaining capacity before disk full |
| `http.server.requests` | Aggregate HTTP latency/errors |
| `upload_scanner_queue_lag` | Malware scanning backlog |

Not all of these metrics come out of Actuator automatically. Add custom Micrometer gauges/counters, platform volume metrics, and safe logging. **Never tag upload IDs, filenames, user IDs, or raw URLs onto metric labels**: cardinality and PII exposure will explode. Alert when staged bytes or oldest incomplete upload exceeds TTL, filesystem free space runs low, 413/429 spikes, or janitor runs fail.

### 13.1. Illustrative Capacity Math

3 writers × 50 MiB = ~150 MiB max app staging, to which you must add Servlet parser temp, proxy buffering, ready storage, orphan files, rolling deploys, and disk/inode headroom. If 10 concurrent 50 MiB multipart uploads hit Tomcat, Servlet temp can exceed 150 MiB before any controller acquires a permit. Mitigate with gateway rate/concurrency limits, temp volume quotas, per-tenant budgets, and direct-to-object-storage uploads for large objects.

### 13.2. Metadata-Only Logging

Illustrative safe log line:

~~~text
upload_committed id=opaque bytes=1048576 duration_ms=87
~~~

Never log file bytes, raw multipart bodies, bearer tokens, raw client filenames, or secret storage paths. Store full SHA-256 in the DB if needed rather than printing unconditionally to logs. Important audit streams must be durable, not reliant solely on stdout from restarting Pods.

## 14. Required Test Matrix Before Production

| Test | Condition | Expected Outcome |
| --- | --- | --- |
| Small multipart | 1 KiB file | 201, exact bytes/hash, clean stage |
| Small raw | 1 MiB | 201, exact bytes/hash, clean stage |
| Empty file | 0 bytes | 400, nothing in ready |
| Exactly max | 50 MiB | 201 if disk/other policies allow |
| Multipart > cap | 51 MiB | Reject 413 or reset, nothing in ready |
| Raw > cap, known length | `Content-Length` > limit | Reject early, nothing in ready |
| Raw > cap, unknown length | Chunked > limit | Count past limit then reject, clean up |
| Too many parts | > `max-part-count` | Parser rejects, nothing in ready |
| Long part header | > `max-part-header-size` | Rejected at connector |
| Client abort | TCP reset mid-body | Partial stage never reaches ready |
| Slow client | 1 KiB/s | Timeout/quota applied, worker not held indefinitely |
| 4 concurrent uploads | 3 permits | Never >3 active storage writers |
| Disk full | Write throws `IOException` | Cleanup + alert, no 201 |
| Move failed | Cross-filesystem / unsupported | Never expose partial ready file |
| Filename `../` | Untrusted `originalFilename` | Stored only inside private root |
| SIGTERM | Upload in progress | Drains within grace/handoff |
| SIGKILL | Process killed | Orphan janitor/lease recovers |
| Duplicate retry | Lost 201 response | Existing receipt via idempotency |
| ZIP bomb / malware | Malicious payload | Quarantined/rejected by scanner |
| Multi-pod failover | Upload/lookup across pods | Durable shared storage |
| App vs proxy limit | Proxy cap lower than app | Rejected at proper layer, clear tracing |

Do not claim this entire matrix passed just because `mvn test` passed. Fault-injection, network, Kubernetes, and security-scanning tests require dedicated environments. For HTTP 413 vs reset, verifying **no unauthorized ready file exists** matters more than hardcoding identical status responses across all connectors.

## 15. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Immediate 413 above 1 MB | Boot default multipart limit is 1 MB/file | Adjust limits to requirements |
| Still 413 despite app max=50 MB | Edge/Ingress cap is lower | Check limits at every hop |
| `/tmp` fills despite streaming controller | Servlet multipart spooling | Size temp volume/quotas/edge limits |
| Heap OOM on large upload | `getBytes()`/`readAllBytes()`/body logging | Use bounded streaming |
| Raw chunked exceeds cap | Trusted `Content-Length` alone | Count actual bytes |
| Many-part multipart spikes CPU | Unbounded part count/headers | Enforce Tomcat parser limits |
| `.part` files linger after exception | Missing `finally` or failed delete | Cleanup + metrics/janitor |
| `.part` files linger after SIGKILL | `finally` never executed | Lease-based orphan GC |
| Ready file contains partial data | Writing directly to ready path | Write to stage + atomic publish |
| `Files.move ATOMIC_MOVE` fails | Cross-filesystem / unsupported provider | Same FS or object-store commit |
| Filename path traversal | Used `originalFilename` | Server-generated UUID |
| Spoofed MIME | Trusted `Content-Type` | Strict validator/decoder/scanner |
| Small ZIP causes OOM on extract | Unbounded decompression | Enforce decompression limits |
| Socket reset instead of 413 | Tomcat `max-swallow-size` / proxy behavior | Treat as rejection, inspect layer |
| Excessive 429s | Semaphore saturated | Shared quotas / edge concurrency limits |
| Same file uploaded twice | Lost 201, retry lacked idempotency | Durable receipt key |
| Uploaded file vanishes on pod restart | Pod-local ephemeral stage/ready | Use durable shared storage |
| WebFlux `DataBuffer` leak | Unreleased cancelled buffers | Consume/release properly, bound flow |
| Disk full despite tiny app stage | Proxy/Servlet/ready consuming disk | Volume-level metrics |
| Public URL exposes every upload | Files placed inside webroot carelessly | Private storage + ACLs |
| 201 returned before DB commit | Wrong commit order | Reconciliation / saga |

## 16. Production Checklist

### Input / HTTP
- [ ] Multipart file/request/part/header limits configured and aligned with edge caps?
- [ ] Raw body counts actual bytes, handling unknown/chunked `Content-Length`?
- [ ] Connection/read timeouts, rate limits, per-tenant quotas, and max concurrency in place?
- [ ] Servlet/proxy temp directories sized with quotas, metrics, and strict permissions?
- [ ] Zero full-file heap loading and zero raw file logging?

### Storage / Cleanup
- [ ] Server-generated filenames inside private root, ignoring user path input?
- [ ] Stage/ready on the same filesystem or using object-store transactional commits?
- [ ] Streams closed, stage cleaned in `finally`, permits always released?
- [ ] Zero partial ready files on errors; move/disk errors alerted?
- [ ] Lease/TTL janitor handles SIGKILL and incomplete multipart uploads?
- [ ] Retention, deletion, and durable idempotency receipts implemented?
- [ ] Multi-pod deployments use shared durable storage instead of pod-local disks?
- [ ] SHA-256 is not mistaken for antivirus, nor atomic rename for power-loss durability?

### Security
- [ ] AuthN/AuthZ, CSRF policy, tenant ownership, and quotas enforced?
- [ ] MIME/extension/magic/decoder validation + antivirus/CDR as needed?
- [ ] ZIP bomb, XML bomb, and parser resource-exhaustion defenses?
- [ ] Private quarantine, no arbitrary execution of uploads, safe download headers?
- [ ] Untrusted `originalFilename`, `Content-Type`, and forwarded headers never trusted?
- [ ] Logs exclude PII, tokens, and file bytes; metric labels are bounded?

### QA / Operations
- [ ] Real-port JUnit verifies 201, 400, 413, and stage cleanup?
- [ ] `curl` tests cover raw, multipart, boundaries, chunked, and client aborts?
- [ ] Disk full, slow clients, SIGTERM/SIGKILL, and orphan GC tested?
- [ ] Metrics cover staged bytes, oldest orphan, temp free space, and cleanup errors?
- [ ] Runbooks exist for proxy limit hits, disk quotas, and scanner downtime?
- [ ] Code and docs explicitly state the demo omits production scanning/auth?

## 17. Self-Check Questions and Answers

**1.** Does `MultipartFile.getInputStream()` avoid Servlet temporary disk storage?

**Answer:** No; it avoids `getBytes()` copying the whole file onto the app heap, yet the Servlet multipart parser may still spool to temp disk before invoking the controller.

**2.** What are Spring Boot's default Servlet multipart max file/request sizes?

**Answer:** Per docs, **1MB per file, 10MB per request**; raw `application/octet-stream` is unaffected by those properties.

**3.** Why is checking `Content-Length` alone wrong?

**Answer:** Chunked/unknown lengths, proxy transformations/aborts, and untrusted clients mean actual read bytes must be counted.

**4.** When writing a 50 MiB body, why not write directly to the ready path?

**Answer:** Consumers could observe a partial file; write to staging and atomically publish only after full validation.

**5.** Why does `Files.move(...ATOMIC_MOVE)` not prove survival across power loss?

**Answer:** An atomic namespace rename does not automatically `fsync` file/directory metadata or commit a DB transaction.

**6.** On SIGKILL, does `finally` delete `.part` files?

**Answer:** No. A lease/TTL-based janitor is required, taking care not to delete active uploads.

**7.** Does `UploadService` `semaphore=3` cap Tomcat to parsing only three multipart requests at once?

**Answer:** Not completely; the parser can spool requests to temp before the handler calls the service. Edge/connector budgets are also needed.

**8.** Does a matching SHA-256 prove a file contains no malware?

**Answer:** No; hashes verify integrity, while format checks, antivirus, and CDR must run separately.

**9.** Why must `getOriginalFilename()` never be used in filesystem paths?

**Answer:** Client-controlled strings pose path traversal, Unicode/confusable, and overwrite risks; the server must generate opaque IDs.

**10.** Why might a client see a connection reset instead of 413?

**Answer:** Tomcat/proxies may stop swallowing unread body bytes upon rejection, preventing the HTTP error response from reaching the client.

**11.** If a client retries after missing a 201 response, should the server blindly store a new file?

**Answer:** Production should enforce tenant-scoped idempotency receipts and return the already-committed receipt for the same key/request.

**12.** Why can a 50 MiB upload require more than 50 MiB of disk budget?

**Answer:** Proxy body temp, Servlet temp, app stage, ready storage, concurrency, orphans, and disk headroom all add up.

**13.** Does WebFlux `PartEvent` automatically release `DataBuffer`s if a handler ignores the stream?

**Answer:** Never assume that; consume, relay, or release buffers and wire cancel cleanup explicitly per contract.

**14.** To support multi-GiB files, should you just set `max-file-size=-1`?

**Answer:** No; consider direct-to-object-storage multipart/resumable uploads, quotas, checksums, abort cleanup, scanning, and durable state.

## 18. Official References

- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html).
- [Spring Boot 4.1 — Common Application Properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html).
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — Multipart Resolver and Servlet Part](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html).
- [Spring Framework — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html).
- [Spring Framework — MVC Multipart Controller](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html).
- [Spring Framework — WebFlux Multipart and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html).
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
- [JDK 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [JDK 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).
- [JDK 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html).
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload).
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578).
- [RFC 9110 — HTTP Semantics/413](https://www.rfc-editor.org/rfc/rfc9110).
- [Amazon S3 — Multipart Upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html).
- [Kubernetes — Ephemeral Volumes](https://kubernetes.io/docs/concepts/storage/ephemeral-volumes/).

**Conclusion:** Handling large file uploads properly is not just "raising the multipart size limit." You must bound requests at **edge, Servlet, app, and storage**, count actual bytes while streaming, avoid loading full files into arrays, separate **temporary vs staging vs ready**, publish only after completion, clean up resources in `finally`, and run a janitor for crashes/SIGKILL. Uploaded files are untrusted data: keep storage private, enforce validation/scanning, auth/tenant quotas, idempotency, retention, and load/chaos testing before production.