# spring.servlet.multipart.*: File Size, Request Size, and Temporary Storage

**Module:** Spring Boot - web-runtime  
**Parent topic:** File upload and download

## 1. The Problem: An Upload Can Fail Before Reaching the Controller

A Spring MVC API accepts images or documents via **multipart/form-data**. A 500 KB file succeeds, while a 2 MB file is rejected; or two 7 MB files are valid individually, yet fail when sent together in one request. Sometimes the application reports out of disk space even though you never explicitly wrote a file to the final storage directory.

To explain these situations, distinguish three questions:

1. **What is the maximum number of bytes allowed per individual file?** → **spring.servlet.multipart.max-file-size**.
2. **How large can the entire HTTP multipart request be, including multiple parts and framing?** → **spring.servlet.multipart.max-request-size**.
3. **While the Servlet container parses the content, where is temporary data stored and above what size is it written to disk?** → **spring.servlet.multipart.location** and **spring.servlet.multipart.file-size-threshold**.

These properties belong to Spring Boot's **Servlet multipart** mechanism. They control resource usage while receiving the body and do not by themselves provide durable file storage, file safety validation, proxy-level limits, or upload handling in WebFlux.

After this lesson, you will be able to read and configure **spring.servlet.multipart.*** properties; write an API accepting **MultipartFile**; test the three limits over real HTTP; distinguish temporary storage from final storage; and handle size-limit errors.

## 2. What Does multipart/form-data Contain?

An HTML form or HTTP client sends data using **multipart/form-data**, where a single request body can hold multiple **parts**. Each part has its own headers (**Content-Disposition**, and optionally **Content-Type**) and body.

~~~http
POST /api/uploads/files HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=boundary123

--boundary123
Content-Disposition: form-data; name="description"

Sample document
--boundary123
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<binary-content-of-report.pdf>
--boundary123--
~~~

This is a logical illustration; on the wire the **boundary** and line-ending bytes are generated properly by the client, while `<binary-content-of-report.pdf>` represents the actual bytes.

**A single request can contain multiple files and form fields**. In Spring MVC, **@RequestParam("file") MultipartFile file** binds one file part; **List<MultipartFile>** binds multiple files sharing a name; **@RequestPart** is helpful when a part carries JSON needing conversion via a message converter.

Upload flow in Spring Boot Servlet:

~~~text
Client / browser
    |
    | POST multipart/form-data
    v
CDN / reverse proxy / ingress (if body limits apply)
    |
    v
Servlet container: Tomcat / Jetty / Undertow
    |
    | MultipartConfigElement:
    |  - maxFileSize
    |  - maxRequestSize
    |  - fileSizeThreshold
    |  - location
    v
Spring MVC multipartResolver and DispatcherServlet
    |
    v
Controller @RequestParam MultipartFile
    |
    v
Business validation, antivirus/content scan, save to final destination
~~~

**Multipart limits can be enforced at the container layer before the controller executes.** Therefore, having the controller call **file.getSize()** to reject large files is only an extra business validation layer and **does not replace** body-ingestion limit settings.

## 3. Table of spring.servlet.multipart.* Properties in Spring Boot 3.x

The defaults below reflect Spring Boot **3.3**:

| Property | Default | Meaning |
| --- | --- | --- |
| **spring.servlet.multipart.enabled** | **true** | Enables multipart auto-configuration on Spring Boot's Servlet stack. |
| **spring.servlet.multipart.max-file-size** | **1MB** | Maximum size of **each uploaded file**. |
| **spring.servlet.multipart.max-request-size** | **10MB** | Maximum size of **the entire multipart request**. |
| **spring.servlet.multipart.file-size-threshold** | **0B** | File data threshold above which the container writes temp content to disk. |
| **spring.servlet.multipart.location** | Unset | Intermediate directory; the container uses a default temp directory when unset. |
| **spring.servlet.multipart.resolve-lazily** | **false** | Parses multipart eagerly by default; **true** defers parsing until file/parameter access. |
| **spring.servlet.multipart.strict-servlet-compliance** | **false** | **true** restricts multipart recognition per the Servlet spec to **multipart/form-data**. |

**The defaults of 1MB, 10MB, and 0B are configuration defaults, not guarantees that storage capacity is always available.** Along the path, nginx, ingress, or proxies may enforce lower ceilings; the Servlet container also has its own limits on connections, part count, body, and disk.

Spring Boot binds sizes using **DataSize**. Common suffixes are **B**, **KB**, **MB**, **GB**. Here these are binary units:

- **1KB = 1,024 bytes**.
- **1MB = 1,048,576 bytes**, so **8MB = 8,388,608 bytes**.
- **1GB = 1,073,741,824 bytes**.

Use strings with explicit units like **8MB** or **256KB**, avoiding bare numbers that make it hard for maintainers to tell bytes from megabytes.

## 4. Difference Between max-file-size and max-request-size

**max-file-size** applies to **each individual file part**. **max-request-size** applies to **the multipart request as a whole**, including file parts, form fields, and framing as measured by the Servlet container.

Suppose:

~~~properties
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=12MB
~~~

| Scenario | Against max-file-size | Against max-request-size | Conclusion |
| --- | --- | --- | --- |
| One 7 MB file | 7 ≤ 8 | Body ~7 MB plus overhead ≤ 12 | Normally valid. |
| One 9 MB file | 9 > 8 | Body may be under 12 | Rejected for **per-file limit**. |
| Two 7 MB files in one request | Each file ≤ 8 | Total over 14 MB > 12 | Rejected for **request limit**. |
| One exact 8 MB file | Right at file limit | Request exceeds 8 MB due to headers/boundaries | Succeeds only if request limit leaves room for overhead. |
| One 11 MB file in a 12 MB request | File > 8 | Total may still be under 12 | Still rejected due to file limit. |

**Do not set max-request-size equal to max-file-size** if the client also sends metadata or multiple parts: even a single file right at the ceiling incurs framing overhead. In practice, leave appropriate headroom for the API contract without opening the total ceiling far beyond actual need.

Limits are independent of **Content-Length**: chunked requests or proxies forwarding segments are still subject to limits as the server reads/parses. Clients can misreport sizes or drop mid-stream; therefore never rely solely on client-supplied headers.

When configuring, the first question must be **what is the largest file and maximum number of files per request allowed by business requirements**, followed by overhead, concurrency, and temporary capacity.

## 5. Temporary Location and Disk-Spill Threshold: location, file-size-threshold

### 5.1. location Is an Intermediate Area, Not Final Storage

**spring.servlet.multipart.location** specifies the directory where the Servlet container stores temporary upload data during parsing. Linux example:

~~~properties
spring.servlet.multipart.location=/tmp/boot-multipart-work
~~~

The path must exist and the application process needs write permission. In a demo, create it first:

~~~bash
mkdir -p /tmp/boot-multipart-work
~~~

On Windows, pick a valid path suitable for the host, such as **C:/upload-demo-temp**, and create that directory before starting. On Docker/Kubernetes, check whether **/tmp** is actually a volume or a size/inode-constrained ephemeral filesystem.

When the request completes, **container-managed temp files are normally cleaned up according to the multipart request lifecycle**. Do not save the temp path in a database for long-term use, and do not keep **MultipartFile** for async processing after the request ends without copying the data to a safe place first.

**Final storage** is an application-defined destination, such as **./var/saved-files**, an object storage bucket, or a file store outside the JVM. **location does not automatically turn into durable data storage**. If an API returns success while relying only on the temporary location, files can vanish after the request finishes or when a container is replaced.

### 5.2. file-size-threshold Is Not a File Size Limit

~~~properties
spring.servlet.multipart.file-size-threshold=256KB
~~~

Meaning: when file data exceeds the threshold per the container's multipart implementation, it is spooled from its initial buffer to **disk**. The default **0B** configures the container to write temporary files to disk immediately under its multipart mechanism. Still, implementations retain internal I/O buffers; do not conclude from **0B** that the app uses zero RAM during uploads.

**A value of 256KB does NOT forbid files larger than 256KB**; it only governs intermediate memory vs. disk buffering. **max-file-size** is the file ceiling. Setting a threshold of several MB lets many concurrent requests hold unspooled data in RAM; evaluate memory, heap/direct buffers, and real workload.

For example, a valid request with a 7MB file under a 256KB threshold: the file is accepted since it is below max-file-size/max-request-size, while temporary data may reside on disk. Once the controller saves durably, the separate stored copy consumes additional disk space.

### 5.3. Capacity Planning for Temporary Storage

Estimate capacity by **concurrency**, not merely the largest single file:

~~~text
Required temp capacity (initial estimate)
≈ active uploads * average temp data per upload
  + headroom for overhead, concurrent writes, retries, and uncleaned requests.
~~~

For instance, with 100 concurrent requests, each potentially using around 8 MB of temporary data: payload alone can take roughly **800 MB**, before metadata, retries, or final storage. If a container's ephemeral storage limit is lower, file-write errors can happen even with free memory/CPU. This is a capacity estimate, **not** a promise that every request consumes the exact file size.

Choosing a temp directory should account for least-privilege write permissions, capacity, inodes, lifecycle, backups, mounts, and monitoring. Do not place temporary uploads next to sensitive config files or inside a directory directly exposed publicly by the server.

## 6. Spring Boot 3.x + Java 17 Demo Configuration

The following example uses **Spring MVC with embedded Tomcat** and **spring-boot-starter-web**. It separates two locations:

- **/tmp/boot-multipart-work**: where the container writes temporary files while parsing multipart (Linux example).
- **./var/saved-files**: where the application explicitly saves files after validating the request.

### 6.1. Dependencies

For a Gradle Spring Boot 3.x project with Java 17+, Gradle wrapper, Spring Boot plugin, and repositories already set up, add to **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter Web provides Spring MVC and the embedded Servlet container by default. You do not need Apache Commons FileUpload to run this demo: Spring MVC in Boot 3 uses the **Servlet Part** mechanism via **StandardServletMultipartResolver**.

### 6.2. application.properties

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=12MB
spring.servlet.multipart.file-size-threshold=256KB
spring.servlet.multipart.location=/tmp/boot-multipart-work
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true

# Destination saved after the app accepts the upload, separate from temp location.
app.upload.storage-dir=./var/saved-files
~~~

**enabled=true** is the default, written explicitly for clarity in this lesson. **strict-servlet-compliance=true** is chosen for a demo accepting only **multipart/form-data**, making behavior more consistent with how the Servlet spec identifies multipart forms; if real business logic needs **multipart/mixed**, evaluate container support and config before enabling it.

**resolve-lazily=false** means parse/limit errors generally surface early when Spring resolves the multipart request. If true, parsing may happen when the controller or framework accesses a part. This flag **does not raise the file ceiling**, does not bypass container limits, and does not guarantee every error hits controller advice.

On other operating systems, replace **spring.servlet.multipart.location** with an existing, writable absolute path before running.

### 6.3. A Runnable Java 17+ Application

Create a single file **src/main/java/com/example/upload/UploadDemoApplication.java**:

~~~java
package com.example.upload;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class UploadDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/uploads")
class UploadController {

    private final Path storageDir;

    UploadController(
            @Value("${app.upload.storage-dir:./var/saved-files}") String directory
    ) throws IOException {
        storageDir = Path.of(directory).toAbsolutePath().normalize();
        Files.createDirectories(storageDir);
    }

    @PostMapping(
            value = "/files",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<StoredFile> upload(
            @RequestParam("file") MultipartFile file
    ) throws IOException {
        if (file.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        // Do not use client-controlled originalFilename as a path.
        String storageKey = UUID.randomUUID() + ".bin";
        Path destination = storageDir.resolve(storageKey);

        try (InputStream input = file.getInputStream()) {
            // Create a new file; do not overwrite existing files.
            Files.copy(input, destination);
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new StoredFile(storageKey, file.getSize()));
    }

    @PostMapping(
            value = "/batch-info",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    UploadSummary batchInfo(
            @RequestParam("files") List<MultipartFile> files
    ) {
        long totalFileBytes = files.stream()
                .mapToLong(MultipartFile::getSize)
                .sum();
        return new UploadSummary(files.size(), totalFileBytes);
    }

    record StoredFile(String storageKey, long bytes) {}

    record UploadSummary(int count, long totalFileBytes) {}
}

@RestControllerAdvice
class UploadErrorHandler {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<Map<String, String>> handleTooLarge(
            MaxUploadSizeExceededException ex
    ) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "multipart size limit exceeded"));
    }
}
~~~

**Explanation:**

- **@RequestParam("file") MultipartFile** binds one file part named **file**. **batch-info** accepts multiple parts with the same name **files** and demonstrates summing file bytes; it does not write files to persistent storage.
- **file.isEmpty()** rejects empty files per the demo requirement. This check does not replace container limits.
- **UUID** generates a storage key independent of **getOriginalFilename()**; it prevents clients from controlling the destination directory, reducing path traversal or overwrite risks.
- **Files.copy(InputStream, Path)** copies data to the final storage directory created in the constructor, whereas temporary files are managed by the Servlet container. Before production, add file-type validation, actual content verification, malware scanning, per-user quotas, authentication/authorization, and error/transaction handling for storage failures.
- **getSize()** is the file part's size in bytes. It differs from **the total multipart request size**, which also includes boundaries, headers, and other fields.
- **@RestControllerAdvice** attempts to return **413 Payload Too Large** when **MaxUploadSizeExceededException** reaches Spring MVC. In practice, a proxy or container may reject the request before the advice layer; therefore **never promise every oversized request receives that exact JSON**.
- The demo uses a single Java file with one public class matching the filename and package-private classes. No separate Controller file is needed for a minimal example.

**Do not use file.getBytes() for large files** unless you truly need all bytes in RAM. **InputStream** allows sequential reading, though the multipart body may already have been buffered/spooled by the container before entering the controller; that differs from end-to-end streaming with zero temporary disk.

### 6.4. Running the Demo

On Linux/macOS or environments with **/tmp**:

~~~bash
mkdir -p /tmp/boot-multipart-work
./gradlew bootRun
~~~

At startup, the app creates **./var/saved-files** if it does not exist. On Windows, change location to a suitable absolute directory and create it; run the OS-appropriate wrapper (**gradlew.bat bootRun** in cmd/PowerShell).

## 7. Testing Three Different Scenarios with curl and Real Files

Use curl with the **-F** flag to send multipart/form-data. On Linux, create binary test files with dd (solely for generating test fixtures):

~~~bash
dd if=/dev/zero of=seven.bin bs=1048576 count=7
dd if=/dev/zero of=nine.bin bs=1048576 count=9
~~~

**seven.bin** is **7,340,032 bytes (7MB)**; **nine.bin** is **9,437,184 bytes (9MB)**.

### Case A: One 7MB File — Succeeds

~~~bash
curl -i -F "file=@seven.bin" http://localhost:8080/api/uploads/files
~~~

Expected response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"storageKey":"<new-uuid>.bin","bytes":7340032}
~~~

The **<new-uuid>** string changes per request; this is an illustrative output format, not a predictable UUID. The result is written to **./var/saved-files**. **7MB < 8MB** and the total request plus overhead is under 12MB, so it normally succeeds.

### Case B: One 9MB File — Exceeds max-file-size

~~~bash
curl -i -F "file=@nine.bin" http://localhost:8080/api/uploads/files
~~~

The 9MB file > 8MB ceiling. Expect rejection due to **max-file-size** even though the total request is under 12MB. When the error reaches the advice, you may see:

~~~http
HTTP/1.1 413 Payload Too Large
Content-Type: application/json

{"error":"multipart size limit exceeded"}
~~~

If the server actually returns a different message, resets the connection, or a proxy returns an HTML 413 page, check **which layer rejected the request** rather than assuming controller advice ran.

### Case C: Two 7MB Files — Each File Valid, Request Too Large

~~~bash
curl -i \
  -F "files=@seven.bin" \
  -F "files=@seven.bin" \
  http://localhost:8080/api/uploads/batch-info
~~~

Each file is 7MB < 8MB. However, total data is ~14MB before multipart overhead > 12MB, so **max-request-size** should block the request. **batch-info** cannot return a normal result.

### Case D: Small Request, File Bytes Differ from Total Request

~~~bash
printf "hello" > tiny.txt
curl -i -F "files=@tiny.txt" -F "files=@tiny.txt" \
     http://localhost:8080/api/uploads/batch-info
~~~

Expected JSON body:

~~~json
{"count":2,"totalFileBytes":10}
~~~

Two files of 5 bytes each. The actual HTTP body is larger than 10 bytes because of boundaries and part headers. This demonstrates that **file.getSize() is not the total HTTP request size**.

### Case E: Equivalent HTML Form

~~~html
<form method="post" action="/api/uploads/files"
      enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Upload</button>
</form>
~~~

The input name must match **@RequestParam("file")**. Sending **application/json** or forgetting **enctype=multipart/form-data** prevents this endpoint from receiving the file as configured and may return 400 or 415. **Content-Type** with boundary must be set properly by the browser/curl; never hardcode a multipart/form-data header that omits the boundary.

## 8. Why Can a 413 Error Come from Many Places?

Not every oversized upload is caught by Spring Boot first. Depending on the architecture:

~~~text
Browser/Client
    |
    v
CDN/WAF          -> body-size policy, upload timeout
    |
    v
Ingress/Nginx    -> client_max_body_size, buffering/temp files
    |
    v
Servlet container -> multipart max-file/max-request, disk temp
    |
    v
Spring MVC        -> MultipartFile, handler validation
    |
    v
Application store -> per-user quota, disk/object-storage policy
~~~

For instance, **Nginx** may have a different **client_max_body_size** from Spring Boot. If the proxy sets 4MB while Spring allows 8MB/file and 12MB/request, a client sending 7MB will be rejected by the proxy **before Spring sees the upload**. Raising max-file-size in Boot will not fix the error in that case.

Various layers may return 413, 400, 500, or terminate the connection depending on server and config. Trace root cause via request IDs, proxy access logs, container error logs, and application logs. If the controller is never invoked, stop adjusting **file.getSize()** and look for **a lower limit upstream**.

**Do not rely solely on a UI showing “Upload failed”**: measure HTTP status, response headers, and identify which layer intercepted the request. For large uploads, proxy buffering, request timeouts, connection timeouts, and slow clients can also produce symptoms distinct from size limits.

## 9. Temporary Files vs. Durable Files: Lifecycle and Ownership

Clearly separate three layers:

| Layer | Owner | Lifecycle | Example |
| --- | --- | --- | --- |
| **Multipart temporary data** | Servlet container/parser | Per request or container cleanup rules | **/tmp/boot-multipart-work** |
| **Application storage** | Business service | System retention/transaction rules | **./var/saved-files**, mounted volume, S3 |
| **Client original filename** | Client-supplied data | Untrusted metadata | **invoice.pdf**, can be manipulated |

After the controller receives **MultipartFile**, if long-term retention is needed, save via **getInputStream()** or **transferTo(...)** to managed durable storage. **MultipartFile.transferTo(...)** may copy or move depending on the implementation and underlying resource; do not assume it can be called repeatedly or that the part stays intact after the request.

**Client-sent filenames are untrusted.** **getOriginalFilename()** can contain paths, unusual characters, or colliding names. Never use it directly as the filename on disk; assign a new ID, keep original metadata separately if permitted, verify file type, and avoid exposing the storage directory publicly.

**Client-declared MIME types are also untrusted**; if restricting to PDFs/images, verify extension/filename, real file signatures, decompression limits, and run malware scanning where appropriate. Multipart upload success only proves the request was received, not that the document is safe.

**Deleting temp files:** do not arbitrarily delete all files in the temp directory while the app is running, because other active requests may be using them. If storage processing is asynchronous, move data to application-managed staging storage before ending the request; never push MultipartFile onto a queue and expect temporary bytes to stick around indefinitely.

## 10. Tuning file-size-threshold: Trading RAM for I/O

A **small threshold (0B or 256KB)** generally avoids holding many large files in memory at the multipart parser layer, at the cost of disk I/O and disk capacity. A **large threshold** can reduce I/O for small files, yet under hundreds of concurrent uploads risks inflating memory footprint. Do not pick values by guesswork.

Example sensible policy for a system accepting images up to 8MB with 20 concurrent uploads:

- Set per-file limit by business need (**8MB**).
- Set request limit sufficient for the parts/images per API (**12MB** in the single-file demo; batch endpoints need a tailored limit if multiple files are allowed).
- Set a small threshold (**0B** or **256KB**) if disk is reliable and you want to curb memory buffering.
- Budget temp disk for concurrency (e.g., 20 × ~8MB ≈ 160MB before overhead), checking container ephemeral storage and inode counts.
- Enforce concurrency/timeouts and user quotas to guard against floods of valid requests.

**0B does not mean zero RAM; 256KB does not mean “each request uses at most 256KB”; 8MB does not mean “each request uses only 8MB of disk.”** These are distinct concepts, and real consumption also depends on container, parsing, copying to final storage, and concurrent requests.

Monitor **disk usage/inodes** at location, filesystem full/read-only state, active upload counts, 413 rates, parse exceptions, request duration, storage copy time, cancelled requests, and heap/direct memory usage.

## 11. Docker/Kubernetes and Multiple Instances

In containers, **/tmp** often belongs to the container filesystem layer or an ephemeral volume. When a pod is recreated, temp files and final files saved on an ephemeral filesystem can be lost. Distinguish:

- **Temporary path:** can use emptyDir/ephemeral volume with an appropriate sizeLimit and pod ephemeral storage limits.
- **Persistent path:** use a persistent volume or object storage when data must survive restarts, rollouts, and multiple replicas.
- **Security context:** the app user must have write permission to the temporary directory; never run containers as root just to bypass permission fixes.
- **Replicas:** if final files are stored on each pod's local disk, subsequent download requests may hit a different pod lacking the data. Use a shared store or designed routing—never treat multipart location as shared storage.
- **Separate quotas:** even with free container memory, temp disk can fill up; even with free disk, final storage can reject writes due to permissions/quotas.

Some systems mount **/tmp** on **tmpfs**, meaning what looks like “writing to disk” actually consumes filesystem-managed RAM. Do not conclude threshold=0 guarantees data always lands on physical disk.

For very large or long-running uploads (hundreds of MB to GB), evaluate **direct-to-object-storage uploads with presigned URLs**, storage-layer multipart/resumable uploads, virus scanning, and confirmation callbacks; do not set max-file-size=-1 and push all traffic through the Servlet container without new safeguards.

## 12. What Do resolve-lazily and strict-servlet-compliance Do?

### resolve-lazily

By default (**false**), Spring MultipartResolver tries to parse the multipart request eagerly. When set to:

~~~properties
spring.servlet.multipart.resolve-lazily=true
~~~

Parsing can be deferred until parameters or files are accessed. This can **shift the timing** and call-stack location where exceptions are thrown, especially for large or malformed requests. **It does not increase accepted sizes** and does not make an invalid request valid.

If code catches errors in filters, interceptors, or advice, test against the real container because eager vs. lazy parsing alters the exception flow; do not assume every MaxUploadSizeExceededException will hit controller advice.

### strict-servlet-compliance

~~~properties
spring.servlet.multipart.strict-servlet-compliance=true
~~~

When enabled, the resolver only accepts multipart requests within standard Servlet **multipart/form-data** scope to avoid cross-container quirks on other multipart types. In form upload demos, this is a solid choice. If an API accepts **multipart/mixed**, verify actual requirements and parser/container behavior; do not enable this flag blindly and then wonder why multipart/mixed isn't processed like multipart/form-data.

### enabled

~~~properties
spring.servlet.multipart.enabled=false
~~~

Setting false disables Spring Boot Servlet multipart auto-configuration. It is **not a way to raise size limits**. If the app needs multipart and you disable auto-config, you take responsibility for configuring Servlet multipart and the resolver yourself; otherwise controllers expecting MultipartFile may fail to work as intended.

## 13. Servlet MVC vs. WebFlux Upload Configuration

**spring.servlet.multipart.*** belongs to the **Servlet Part** system in Spring Boot. When a project uses **spring-boot-starter-web**, MultipartAutoConfiguration typically configures **MultipartConfigElement** and **StandardServletMultipartResolver** so Spring MVC receives **MultipartFile**.

**Spring WebFlux** with Reactor Netty uses a reactive multipart model, such as **FilePart** and **Part** in the **org.springframework.http.codec.multipart** package. This differs from Servlet **MultipartFile/jakarta.servlet.http.Part**. Do not assume **spring.servlet.multipart.max-file-size**, **max-request-size**, and **location** govern WebFlux running on Reactor Netty.

In WebFlux, decoder limits, **maxInMemorySize**, and multipart codec settings are configured in the reactive stack; when working with WebFlux, consult the corresponding docs and verify how data is spooled or streamed. If a project includes both web starter and webflux starter, Spring Boot may default to Servlet MVC; confirm the **actual ApplicationContext/web stack** before adjusting properties.

**Targeting the wrong stack is a common mistake:** setting spring.servlet.multipart.max-file-size=50MB in a WebFlux/Netty service and believing uploads are capped at 50MB has no basis.

## 14. Designing Proper Tests: MockMvc Alone Does Not Verify Container Limits

You can write controller unit tests with MockMultipartFile/MockMvc to verify:

- Whether the mapping binds the **file** part.
- Returning 400 when **file.isEmpty()** is true.
- The service generating a storage key and invoking save logic under mocks.
- Expected JSON response/validation.

However, **MockMvc.multipart(...) typically builds a synthetic request directly**, without passing through a real HTTP request parsed from a socket by the Servlet container. Therefore, a passing MockMvc test **does not prove** that **max-file-size** or **max-request-size** will enforce limits in Tomcat as in production.

To test these ceilings, run integration tests with a **real server and real HTTP client**:

1. Start embedded Tomcat on an HTTP port and verify it loads the expected application.properties.
2. Send a small file under the limit; verify 201 and final saved bytes.
3. Send a file exceeding max-file-size while the request stays under max-request-size; verify rejection at the proper layer.
4. Send two files where each is valid individually yet the total request exceeds max-request-size; verify rejection.
5. Check temp path write permissions, watch disk during upload, and confirm the final file does not depend on temp after the request.
6. Retest through proxy/ingress with real limits; localhost-only tests cannot verify CDN/nginx or body buffering.
7. Test interrupted requests, insufficient temp space, empty files, unusual filenames, and concurrent uploads within safe test-environment bounds.

You do not need to generate infinitely huge test files to “test until the machine crashes”: use a few thoughtfully sized files and isolate the test environment.

## 15. Diagnosing Common Issues

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| 2MB file rejected with default config | Default **max-file-size=1MB**. | Set business-appropriate ceilings; also check proxy and request limits. |
| Two files upload separately, fail together | **max-request-size** smaller than sum of parts. | Sum files + multipart overhead; consider separate batch endpoints or single-file uploads. |
| File matching exact max-file-size fails | Total body with headers/boundary/fields exceeds max-request-size. | Leave appropriate request headroom; measure actual payload size. |
| Controller never reached, only HTTP 413 seen | Proxy or container rejected before handler layer. | Check logs and limits at every hop. |
| Temp directory fills up, no final file appears | Servlet container spools body to **location** before controller saves. | Provision sufficient temp disk/volume; monitor concurrency and cleanup. |
| Upload succeeds then file disappears | Retained temp path/MultipartFile instead of saving durably. | Copy/transfer data to storage with an independent lifecycle during the request. |
| OOM during concurrent uploads | Threshold/buffering too high, app calls **getBytes()**, or holds many request buffers. | Stream reads, lower memory buffering, cap concurrent uploads. |
| WebFlux API ignores Servlet properties | Wrong web stack; codec/decoder config differs. | Confirm Reactor Netty/WebFlux and configure reactive codec limits. |
| Permission denied despite existing directory | App user lacks write permission to location/final store. | Check user/group, mounts, read-only rootfs, SELinux/permissions. |
| Upload error occurs only in Kubernetes | Ephemeral storage, tmpfs, disk quota, ingress limit, or non-shared replica storage. | Inspect pod resources, volumes, ingress, and object storage. |
| Exception handler fails to return expected 413 JSON | Parser/container/proxy threw or dropped connection before Spring advice. | Log and trace the actual request path; do not force every failure into business errors. |
| Client filename used to construct path | Path traversal, name collisions, illegal characters. | Generate a new storage key, validate, and store metadata separately. |

## 16. Self-Check Questions

1. Does **max-file-size=8MB** allow two 7MB files in one request when **max-request-size=12MB**? **No**: each file is valid, but the total request is too large.
2. Does **file-size-threshold=256KB** forbid uploading a 1MB file? **No**: threshold is the disk-spooling boundary, not an accepted size limit.
3. Does **location** replace **storage-dir** in the controller? **No**: location is container-managed intermediate storage; the application must save to durable storage itself.
4. Are **no-store**, HTTP caching, or the static-resource chain directly tied to multipart upload size checks? **They are not size-checking mechanisms.** Multipart is an incoming request body being parsed, whereas static caching concerns serving responses.
5. Is **getOriginalFilename()** safe to use directly as a Path? **No**, because it is client-supplied; generate a new key and validate filename/file type.
6. Why might a 413 bypass **@RestControllerAdvice**? Because the request can be blocked before reaching Spring MVC.
7. Why might small uploads work on a laptop yet fail writing temp files in a pod? **Volumes, quotas, or permissions** may differ.
8. When using **WebFlux/Reactor Netty**, should you default to **spring.servlet.multipart.***? **No**; use the corresponding reactive multipart configuration.
9. Why is **MockMvc** insufficient to prove Servlet multipart limits? Because mock requests do not necessarily pass through the container's real HTTP parser and limits.
10. Should you set **max-file-size=-1** to avoid user errors? Only when another size-limiting, resource, and security mechanism is deliberately designed; for normal public uploads **never drop limits arbitrarily**.

## 17. Official References

- **Spring Boot 3.3 – Common Application Properties, Servlet Multipart:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- **Spring Boot – How-to: Handling Multipart File Uploads:** https://docs.spring.io/spring-boot/how-to/spring-mvc.html
- **Spring Boot – MultipartProperties API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html
- **Spring Framework – MVC Multipart Resolver:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- **Spring Framework – Controller Multipart Forms:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- **Spring Framework – DataSize (binary prefixes):** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/util/unit/DataSize.html
- **Spring Framework – MultipartFile Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/multipart/MultipartFile.html
