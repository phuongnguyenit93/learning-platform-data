# MultipartResolver, MultipartFile, and Servlet Multipart Configuration

## 1. The Problem: Receiving an HTTP File Is More Than Reading a Request Body

When a browser or client sends a file to a **Spring Boot MVC/Servlet** application, the request typically uses **Content-Type: multipart/form-data**. The body is no longer a single JSON payload or byte[]; it contains **multiple parts**, each with its own headers and content. One part might be a text field, while another is an uploaded image or document.

The processing pipeline has distinct responsibilities:

- **The Servlet container** (Tomcat/Jetty/Undertow depending on the app) receives the request and provides multipart parsing via the **jakarta.servlet.http.Part** API.
- **MultipartConfigElement** declares Servlet multipart support, size limits, and temporary storage location.
- **MultipartResolver** integrates that parsing with **Spring MVC DispatcherServlet**.
- **StandardServletMultipartResolver** uses the Servlet container's multipart parser.
- **MultipartFile** is the application-facing interface used to inspect metadata and read or transfer a file part's content.
- **The controller and storage layer** validate the data and decide whether to persist the upload or reject it.

Understanding these layers helps answer the right questions: why small files upload fine while large ones fail, why temporary files disappear after the request completes, why the controller isn't even called when the body is too large, and why **MultipartFile.getOriginalFilename()** cannot be used directly as a destination path.

This lesson applies to **Spring Boot 3.3.x + Spring MVC + Jakarta Servlet API + Java 17+**, especially with the default embedded Tomcat from spring-boot-starter-web. **Spring WebFlux** has its own reactive mechanism using **FilePart/Part** in the org.springframework.http.codec.multipart package; do not use the Servlet MultipartResolver as a template for WebFlux.

## 2. How Is a multipart/form-data Request Encoded?

An HTML form sending a text field and a file can look like this:

~~~html
<form action="/api/uploads" method="post" enctype="multipart/form-data">
  <label>Note: <input name="note" type="text"></label>
  <label>File: <input name="file" type="file"></label>
  <button type="submit">Upload</button>
</form>
~~~

On the wire, the client generates a **boundary** to separate parts. A simplified illustration:

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=demoBoundary

--demoBoundary
Content-Disposition: form-data; name="note"

November scan
--demoBoundary
Content-Disposition: form-data; name="file"; filename="scan.txt"
Content-Type: text/plain

hello upload
--demoBoundary--
~~~

The example above is for reading the structure, omitting raw byte transport details; real requests follow proper CRLF line endings and client-generated boundaries. **Do not** manually pass a Content-Type header when using **curl -F**: curl generates the boundary and body in sync. A header declaring multipart with a missing or mismatched boundary can prevent the Servlet parser from splitting parts.

Key points to remember:

1. **name="file"** is the form field name; it must match **@RequestParam("file")** or **@RequestPart("file")**.
2. **filename="scan.txt"** is a client-supplied name. It can be missing, spoofed, contain path segments, odd characters, or exploit strings.
3. **Content-Type: text/plain** on the file part is also client-supplied and does not verify the actual content.
4. A single request can contain **multiple files and multiple fields**, subject simultaneously to per-file limits and total request limits.
5. HTTP multipart does not mean the file is stored durably. The parser may hold content in RAM or a temporary file, and the business layer must explicitly persist it when needed.

Multipart/form-data is not a chunked upload protocol in the sense of resumable uploads. A multipart body can still be transmitted across multiple TCP packets, but packet segmentation does not provide a mechanism to resume an interrupted upload from a mid-stream byte offset.

## 3. Processing Chain: Servlet Container → MultipartResolver → MultipartFile

In a Spring MVC application with multipart enabled:

1. The client constructs a request with **multipart/form-data** and parts.
2. The container reads bytes from the socket, limiting and buffering data according to HTTP and Servlet settings.
3. **DispatcherServlet** looks up a Bean named **multipartResolver**; if the resolver recognizes a multipart request, Spring resolves the parts and wraps the request as a **MultipartHttpServletRequest**.
4. With **StandardServletMultipartResolver**, parsing relies on Servlet **request.getParts()** and **Part**; Spring exposes **MultipartFile** to the controller.
5. Spring MVC binding maps form fields and file parts to annotated parameters like **@RequestParam**/**@RequestPart**.
6. The controller runs validation, transfers the file to persistent storage if accepted, and builds the response.
7. Spring/the Servlet container cleans up temporary multipart resources per the request lifecycle; the application must not retain MultipartFile for later reading.

Diagram:

~~~text
Client multipart/form-data
           |
           v
Web server / Servlet container
           | multipart-config: limits, temp location, threshold
           v
DispatcherServlet
           | multipartResolver
           v
StandardServletMultipartResolver
           | Servlet request.getParts() / Part
           v
MultipartHttpServletRequest
           | MultipartFile, form fields
           v
Controller / Service
           | validate -> persist -> response
           v
Cleanup temporary multipart storage
~~~

This is a responsibility model and does not claim the parser always reads the entire file at the exact same point: **resolve-lazily** and container behavior can shift when parsing and errors occur.

### 3.1. Role of MultipartResolver

**org.springframework.web.multipart.MultipartResolver** is Spring MVC's strategy for detecting and parsing multipart requests. Key methods include:

- **isMultipart(request):** checks whether the request is a multipart type this resolver handles.
- **resolveMultipart(request):** wraps the HttpServletRequest into an appropriate MultipartHttpServletRequest.
- **cleanupMultipart(request):** cleans up temporary parts/resources after processing.

**DispatcherServlet** discovers the resolver by the Bean name **multipartResolver**. In a typical Spring Boot MVC app, auto-configuration prepares the appropriate resolver. You do not need to write this Bean manually every time you build an upload endpoint.

### 3.2. StandardServletMultipartResolver Does Not Set File Limits by Itself

**StandardServletMultipartResolver** is the implementation built on **jakarta.servlet.http.Part**. It does **not** hold max file size or temp directory settings directly on the Bean like a standalone multipart engine. Those limits belong to the Servlet configuration via **MultipartConfigElement**, which Boot creates from **spring.servlet.multipart.***.

Common pitfall: registering only a StandardServletMultipartResolver **without** configuring Servlet multipart support can cause errors in request.getParts() depending on the container. When using Spring Boot starter-web with default configuration, Boot handles both parts.

Since Spring Framework 6, the legacy **CommonsMultipartResolver** is no longer a standard built-in resolver in Spring MVC. Older examples using Apache Commons FileUpload and CommonsMultipartResolver may not apply to Spring Boot 3.x; prefer the Servlet Part-based resolver.

### 3.3. resolve-lazily Changes When Errors Surface

- **resolve-lazily: false** (default): Spring attempts to parse parts when resolving the multipart request; malformed multipart or size-limit errors can occur before the controller runs.
- **resolve-lazily: true:** defers parsing until code actually accesses a file or multipart parameter; errors may surface later.

Lazy parsing does **not** remove size limits and does not turn the parser into end-to-end streaming upload. Nor does it guarantee the controller will always run before any error: reverse proxies and connectors can still reject requests earlier.

### 3.4. strict-servlet-compliance and Cross-Container Portability

By default, StandardServletMultipartResolver may attempt to handle Content-Types starting with **multipart/** broader than multipart/form-data, depending on the container. Some containers handle multipart/mixed differently from Tomcat. Setting **strict-servlet-compliance: true** restricts the resolver to **multipart/form-data**, keeping behavior more consistent with Servlet multipart forms; other multipart types can be handled by specialized code.

Do not assume multipart/mixed requests are supported uniformly across all Servlet containers without testing.

## 4. MultipartFile: Data, Metadata, and Lifecycle

**org.springframework.web.multipart.MultipartFile** represents a received file part in a request. Essential APIs:

| API | Meaning | Risks / Notes |
| --- | --- | --- |
| getName() | Multipart field name, e.g., file | Different from the original filename |
| getOriginalFilename() | Client-supplied filename; may be null | Untrusted; avoid using as a destination Path |
| getContentType() | Client-declared media type; may be null | Insufficient to verify actual file format |
| getSize() | Part size in bytes | Can be 0; still requires server-side limits |
| isEmpty() | No file or file has zero content | Needs a business rule for empty files |
| getBytes() | Reads all bytes into a byte[] | Consumes heap proportional to file size; unsuitable for large files |
| getInputStream() | Opens a stream to read content | Close with try-with-resources; good for copying/streaming |
| transferTo(File) | Transfers file to target; may move or copy depending on provider | Use an absolute target, validate path, call only once |
| transferTo(Path) | Saves to Path via Spring interface | Standard implementation may copy via stream; do not assume File-style move semantics |

MultipartFile storage can reside in **memory** or a **temporary file**. Once the request ends, the system may delete temporary data. Therefore:

- **Do not** place MultipartFile into a session or singleton to read later.
- **Do not** hand MultipartFile off to a background job that runs after the HTTP request finishes and expect the temp file to still exist.
- If async post-response processing is needed, **save the content to durable storage first**, then pass a reliable ID/path/metadata to the job queue.
- If multiple reads are needed, understand the exact implementation and lifecycle; by default, design for a **single controlled read/transfer**.

**MultipartFile** is client-received data, not proof that the file is safe. Business and security validation must happen before exposing it or feeding it to complex parsers.

### 4.1. Why Is getBytes() Dangerous for Large Files?

For example, uploading a 20 MiB file and calling **getBytes()** allocates a byte[] of roughly 20 MiB, potentially on top of parser/buffer copies. With 100 concurrent uploads, heap usage can spike dramatically. Reading via **getInputStream()** and **Files.copy(...)** avoids holding the entire file in an application byte[], even though the Servlet container may have spooled the data to a temp file.

To emphasize: reading via stream in the application **does not mean** the entire HTTP flow is reactive/non-blocking. Spring MVC on Servlet is a different model from WebFlux.

### 4.2. transferTo(...) Is Not an Idempotent Action You Can Repeat

**transferTo(File)** may move the temp file to the destination, copy from memory, or overwrite the destination depending on the implementation. If the underlying resource was moved, a second call can fail. Relative destination paths may be resolved against the Servlet container's temp directory. Therefore:

- Normalize and pick a server-controlled **absolute destination**.
- Do not use getOriginalFilename() directly as the destination.
- Call transferTo **once** as an intentional save operation.
- When you need strict control to prevent overwrites and control write behavior, **getInputStream() + Files.copy(...)** is often clearer.
- If writing fails, remove any incomplete file and return an appropriate error.

## 5. Servlet Multipart Configuration in Spring Boot

### 5.1. Key Properties

In Spring Boot 3.3, the primary property group is **spring.servlet.multipart**:

| Property | Boot 3.3 Reference Default | Effect |
| --- | --- | --- |
| enabled | true | Enables multipart auto-configuration |
| max-file-size | 1MB | Maximum size per file part |
| max-request-size | 10MB | Maximum total size of a multipart request |
| file-size-threshold | 0B | Data threshold above which container writes temp content to disk |
| location | Unset; uses an appropriate temp directory | Directory where the container stores temporary multipart data |
| resolve-lazily | false | Parse parts eagerly or on first access |
| strict-servlet-compliance | false | Only recognize multipart/form-data in the resolver when true |

Note: **max-file-size** and **max-request-size** are two separate limits. For example, a request sending 3 files of 900 KiB each: every file is under 1MB, yet the total request including parts, headers, and boundaries can still exceed a lower **max-request-size**.

Default limits are specific to Spring Boot 3.3, not a guarantee of the entire Servlet API or every Boot version. Check the property metadata for your actual version when upgrading.

### 5.2. Illustrative application.yml

~~~yaml
server:
  port: 8080

spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 2MB
      max-request-size: 3MB
      file-size-threshold: 0B
      resolve-lazily: false
      strict-servlet-compliance: true

demo:
  upload-directory: ./runtime-uploads
~~~

Meaning:

- Each file part must fit within **2MB**.
- The entire multipart request, including files and fields/overhead, must fit within **3MB**.
- The **0B** threshold steers the Servlet multipart mechanism to spool to disk starting at the lowest threshold; exact allocation details still depend on the container.
- **strict-servlet-compliance: true** is shown for cases where you only want to handle standard form multipart/form-data.
- **demo.upload-directory** is a custom property in the sample app for **durable storage**, completely separate from **spring.servlet.multipart.location** for temporary data. Do not confuse these two paths.

**location** is left unset in the example so the container picks a suitable temp directory. If you configure location, use an existing writable directory in your deployment environment with capacity and permissions sized for peak uploads. Only raise file limits after accounting for disk/RAM/network budgets and security.

### 5.3. How Does Spring Boot Configure Servlet Multipart?

In a standard MVC environment, **MultipartAutoConfiguration** uses MultipartProperties to provide a **MultipartConfigElement** and a **StandardServletMultipartResolver** when conditions match and no replacement is defined. MultipartConfigElement is attached to the Servlet registration so the container knows file size/request size/location/threshold. The resolver uses the Bean name multipartResolver so DispatcherServlet discovers it.

These are **two cooperating layers**, not two competing parser libraries. When customizing Servlet registration yourself, ensure multipart-config remains attached to the Servlet receiving uploads. When declaring a custom resolver, verify it aligns with MultipartConfigElement and uses the right Bean name.

If you disable **spring.servlet.multipart.enabled**, Spring Boot stops preparing default multipart support. Do not turn it off just to allow bigger uploads; adjust the limits instead of removing the whole mechanism and relying on accidental defaults.

### 5.4. Reverse Proxy and Web Server Configuration Also Matter

Properties in application.yml are not the first limit a client hits. Nginx/Ingress/API gateways, load balancers, WAFs, and connectors can each impose **body size limits**, **timeouts**, **max header sizes**, and different connection handling. If a proxy blocks an oversized request, your application's Controller and @ControllerAdvice **will never receive that request**.

Likewise, a full temporary disk or exhausted inodes can break uploads even under size limits. Measure and configure the entire upload path, not just Spring properties.

## 6. When to Use @RequestParam, @RequestPart, or Servlet Part?

### 6.1. Single File and Form Field

~~~java
@PostMapping(
        path = "/forms",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> handle(
        @RequestParam("title") String title,
        @RequestParam("file") MultipartFile file
) {
    // Validate title and file, then store.
    return ResponseEntity.accepted().build();
}
~~~

This is a **Controller fragment** assuming relevant annotations/types are imported, not a standalone program. For typical uploads, **@RequestParam("file") MultipartFile** is clear and common. The name **file** must match the multipart part name.

### 6.2. Multiple Files with the Same Field Name

~~~java
@PostMapping(
        path = "/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> batch(
        @RequestParam("files") List<MultipartFile> files
) {
    // Validate file count, each file, total size, then store.
    return ResponseEntity.accepted().build();
}
~~~

The client sends multiple parts with **name="files"**, or a corresponding multi-file form field. **max-file-size** applies per file; **max-request-size** applies to the total request. You also need to **limit the number of files** to prevent a request with thousands of tiny parts from causing overhead; this limit depends on container/policy and application validation.

### 6.3. File with JSON Metadata

~~~java
public record UploadMetadata(String title, String category) {}

@PostMapping(
        path = "/with-metadata",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> uploadWithMetadata(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file
) {
    // JSON part is converted into UploadMetadata by a message converter.
    return ResponseEntity.accepted().build();
}
~~~

This is a **fragment**: the record must sit in a valid Java location, such as a nested record or separate file, along with a Controller, imports, and Jackson/message converter. With **@RequestPart**, the part's headers (especially **Content-Type: application/json**) let the converter decode metadata into an object. If the client sends JSON as text/plain, you may get 415/400 depending on setup; having the right name metadata alone does not make Spring guess JSON.

**@RequestBody** is suitable when the entire request body is a single JSON document or single payload, not for receiving individual file parts in multipart/form-data.

### 6.4. Servlet Part and MultipartHttpServletRequest

You can inject **jakarta.servlet.http.Part** directly from the Servlet API, or use MultipartHttpServletRequest to access parts/parameters after resolution. The Part API offers getInputStream(), getSubmittedFileName(), getSize(), write(...), and delete(); it sits closer to the container. MultipartFile is a convenient Spring facade for controllers/services. Choose **one clear model** and test on the real container.

**Do not confuse** javax.servlet.http.Part from older Java EE docs with **jakarta.servlet.http.Part** in Spring Boot 3.x; Boot 3 uses the Jakarta namespace.

## 7. Complete Java 17+ Application: Receiving and Saving Outside the JAR

The following example is a Maven Spring Boot 3.3.13 + Spring MVC project. Goals:
- Receive **one** multipart/form-data file.
- Reject empty files and enforce limits via Servlet multipart config.
- Never use the client's filename as the storage path.
- Copy via InputStream into a **directory outside the classpath** with a server-generated name.
- Return minimal metadata (stored name and byte count) without publicly exposing the file.
- Illustrate mapping size-limit errors to HTTP 413 in MVC when the exception reaches Spring.

**This is a technical demo, not a complete private document upload service**: production also requires authentication, content inspection, malware scanning, quotas, auditing, and durable storage.

### 7.1. Structure

~~~text
multipart-servlet-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/upload/
    │   └── UploadDemoApplication.java
    └── resources/
        └── application.yml
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>multipart-servlet-demo</artifactId>
    <version>1.0.0</version>

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

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 2MB
      max-request-size: 3MB
      file-size-threshold: 0B
      resolve-lazily: false
      strict-servlet-compliance: true

demo:
  upload-directory: ./runtime-uploads
~~~

The path **./runtime-uploads** resolves relative to the **JVM's working directory**, not the directory containing the JAR. The example uses it for local testing. Production should pass an absolute path to a volume or an appropriate object-storage abstraction.

**src/main/java/com/example/upload/UploadDemoApplication.java**:

~~~java
package com.example.upload;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
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
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class UploadDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadDemoApplication.class, args);
    }
}

@RestController
class UploadController {
    private final Path root;

    UploadController(@Value("${demo.upload-directory}") String configuredPath)
            throws IOException {
        root = Path.of(configuredPath).toAbsolutePath().normalize();
        Files.createDirectories(root);
    }

    @PostMapping(
            path = "/api/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<UploadReceipt> upload(
            @RequestParam("file") MultipartFile file
    ) throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "File must not be empty"
            );
        }

        String generatedName = UUID.randomUUID() + ".bin";
        Path destination = root.resolve(generatedName);

        try (InputStream input = file.getInputStream()) {
            Files.copy(input, destination);
        } catch (IOException error) {
            Files.deleteIfExists(destination);
            throw error;
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadReceipt(
                        generatedName,
                        file.getSize()
                ));
    }

    public record UploadReceipt(String storedName, long sizeBytes) {}
}

@RestControllerAdvice
class UploadExceptionAdvice {
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<Map<String, String>> tooLarge() {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "multipart_too_large"));
    }
}
~~~

### 7.2. Explaining Each Choice in the Code

- **@RequestParam("file") MultipartFile:** Spring MVC binds the exact file part named file based on the multipart resolver.
- **isEmpty():** checks for missing content or an empty file. If the client omits the required part altogether, Spring may raise a missing parameter/part error before entering the method.
- **UUID + .bin:** server-generated storage name; never puts getOriginalFilename into the path, preventing path traversal and client-chosen overwrites. The .bin extension does not validate file format; it simply keeps the demo independent of client extensions.
- **Path.toAbsolutePath().normalize():** resolves the storage root clearly at startup. The folder is a **private directory**, outside classpath:/static and not exposed via WebMvcConfigurer.
- **Files.createDirectories:** creates persistent storage at Bean initialization; if permissions are missing, startup fails loudly rather than silently writing elsewhere.
- **getInputStream() + Files.copy:** copies content without the Controller allocating a large byte[] array. Files.copy does not overwrite an existing destination by default; with UUIDs, collision risk is negligible, though production still needs collision/idempotency handling.
- **try-with-resources:** closes the MultipartFile input stream; if an IOException occurs, attempts to delete the incomplete destination file.
- **ResponseEntity 201:** returned only after the copy succeeds; this **does not** prove the data has been fsynced to all disks/replicas or scanned for safety.
- **MaxUploadSizeExceededException:** when the exception surfaces inside MVC, the advice can return HTTP 413. Containers/proxies may block earlier or reset the connection differently, so never claim every oversized request is guaranteed to return the advice's JSON 413.
- **No download endpoint:** returning a filename in JSON does not make uploaded content public. If adding download later, enforce authorization checks, Content-Disposition, and storage policies.

Distinguish two locations: **temporary files** created by the Servlet container per spring.servlet.multipart.location and threshold; and **durable files** in demo.upload-directory controlled by application code. Once copied, the stored file's lifecycle is independent of the request. Spring does not automatically delete persistent files created by the Controller.

### 7.3. Running Locally and Testing with curl

Inside **multipart-servlet-demo**, requiring JDK 17+, Maven, and port 8080 free:

~~~bash
mvn package
java -jar target/multipart-servlet-demo-1.0.0.jar
~~~

Create **sample.txt** containing the exact 12 ASCII bytes **hello upload**, with no trailing newline. On Linux/macOS:

~~~bash
printf 'hello upload' > sample.txt
~~~

On Windows PowerShell 5.1:

~~~powershell
[System.IO.File]::WriteAllText(
  "sample.txt",
  "hello upload",
  [System.Text.Encoding]::ASCII
)
~~~

Send multipart using curl (on PowerShell, use **curl.exe**):

~~~bash
curl -i -F "file=@sample.txt;type=text/plain" http://localhost:8080/api/uploads
~~~

In this sample app without Spring Security enabled, a valid and successfully saved request returns **HTTP 201 Created** and JSON with two fields: **storedName** (a random UUID with .bin) and **sizeBytes** equal to **12**. The storedName value changes on every call, so a fixed stdout string cannot be shown for all runs.

Check the **runtime-uploads** directory in the running process's working directory. You will see a randomly named file with **12 bytes** of content. Seeing the file here confirms the application copied it; this is **not** the Servlet temp file.

Try sending without a file:

~~~bash
curl -i -X POST http://localhost:8080/api/uploads
~~~

This request has no multipart/form-data part named file; it may be rejected due to **unsupported Content-Type (415)** or a missing part error, depending on exact headers/client. To test the empty-file case in multipart, create an empty file and send it via **curl -F "file=@empty.txt"**; the isEmpty() check returns **400 Bad Request** once the resolver binds the file.

Try an oversized body: create a file **larger than 2 MB** and send it with curl -F; the max-file-size limit is enforced at the Servlet layer. When the error reaches Spring MVC advice, it may return **413 multipart_too_large**. If a proxy or Tomcat rejects/closes the connection early, the client may see a different error. Only increase limits after identifying the blocking layer and resource budget.

### 7.4. Testing Total Request Size and File Count

Even though the example Controller takes one file, the config still bounds the **total multipart request**. When building a multi-file API, test cases where each file is under 2MB while the total exceeds 3MB, or where large text fields push past max-request-size. Both limits should be tested on a real container.

Locally, changing **spring.servlet.multipart.max-file-size** without restarting the application does not guarantee the new config takes effect; limits are attached to the Servlet registration at startup. To change them, update config and restart/redeploy accordingly.

## 8. When Manual Resolver or Servlet Multipart Config Is Needed

With the default Spring Boot starter-web, manual declaration is usually **unnecessary**. However, if you create a custom DispatcherServlet, configure a custom ServletRegistrationBean, or use Spring MVC outside Boot, you must ensure two pieces are in place:

1. **The Servlet registration has multipart-config** (e.g., MultipartConfigElement with temp location and limits).
2. **DispatcherServlet has a resolver named multipartResolver** or corresponding Part binding support.

An **illustrative-only** example declaring a custom resolver in a @Configuration class; if added to Boot, understand how auto-configuration backs off and ensure Servlet properties still apply:

~~~java
@Bean(name = "multipartResolver")
StandardServletMultipartResolver multipartResolver() {
    StandardServletMultipartResolver resolver =
            new StandardServletMultipartResolver();
    resolver.setResolveLazily(false);
    resolver.setStrictServletCompliance(true);
    return resolver;
}
~~~

This is a **fragment**, requiring @Bean and StandardServletMultipartResolver imports inside a configuration class. It does not configure max-file-size, max-request-size, or temp location. When you only want to tune lazy/strict in Spring Boot 3.3, **prefer properties** instead of writing a redundant Bean.

Manual configuration for a Servlet registration outside Boot can use **jakarta.servlet.MultipartConfigElement**, for example:

~~~java
registration.setMultipartConfig(
        new MultipartConfigElement(
                "/srv/myapp/upload-tmp",
                2L * 1024 * 1024,
                3L * 1024 * 1024,
                0
        )
);
~~~

This is also a **fragment** for a valid ServletRegistration.Dynamic, not a standalone program. The temp path must exist and be writable per container requirements. In a normal Boot app, do not mix this in arbitrarily alongside properties; it can create inconsistencies.

## 9. Secure Uploads: Client Input Must Never Become an Arbitrary Path

### 9.1. Never Trust getOriginalFilename()

A client can send a name like a path with **../** segments, an absolute path, misleading Unicode characters, or a string that looks valid yet targets another location. The following is dangerous:

~~~java
// WRONG: anti-pattern illustration only.
Path target = Path.of(uploadRoot, file.getOriginalFilename());
file.transferTo(target);
~~~

It can allow writing outside the root, overwriting existing files, or causing system errors. Even taking the basename via Path.getFileName() is not enough: you still need policies for naming, length, content type, permissions, and destination. The recommendation is to use a **server-side ID** as the stored filename, keeping a bounded/escaped original filename as metadata only if needed for display.

### 9.2. Content-Type and Extension Are Self-Declared Claims

An uploaded file can claim **image/png** while containing HTML, binary code, or malicious payloads. Validation must inspect **actual content**, allowed formats, sizes, compression depth (zip bombs), and domain-specific checks. For image uploads, consider decoding and re-encoding via a safe image library rather than saving and serving raw uploaded bytes as-is. Apply malware scanning where warranted by risk and operations.

Do not let browsers execute user-uploaded files such as HTML/SVG/scripts under a sensitive origin without proper protections. When providing downloads, use Authorization, Content-Disposition attachment where appropriate, a safely determined Content-Type, X-Content-Type-Options, and related security headers.

### 9.3. Never Mix Upload Storage with Static Public Assets

The **src/main/resources/static/** directory is for versioned assets packaged with the code; do not store uploads there. When running an executable JAR, packaged resources are not a normal writable disk directory. If you point **spring.web.resources.static-locations** or a resource handler directly at the upload directory, you risk accidentally making all uploaded files public.

In the example, **runtime-uploads** is outside the classpath with no static mapping. A future download API must look up the ID from DB or trusted metadata, verify file ownership, and resolve the path inside a safe root. In multi-replica production, use object storage, a shared PVC, or a storage service as required—never assume all Pods share one local directory.

### 9.4. Multi-Layer Limits Against Abuse

Alongside max-file-size and max-request-size, consider:

- Maximum files/parts per request and maximum concurrent requests.
- Per-user/tenant quotas, token buckets, and rate limits.
- Body-receive timeouts at proxy/server; prevent slow clients from holding connections open indefinitely.
- Separate temp and main storage partitions; monitor bytes, inodes, permissions, and cleanup.
- Size limits **after decompression/decoding** when handling archives/media.
- Duplicate-file controls, ID/authorization, retention, and policy-based deletion.

Do not set **-1** to disable limits altogether just to silence “file too large” errors during testing; configure limits aligned with resource budgets and defined business scenarios.

## 10. Temp File Lifecycle, Cleanup, and Handoff to Background Processing

### 10.1. Multipart Temp Storage Is Not a Database

When the container spills large parts to the temp directory, that data belongs to the **request handling lifecycle**. Once the request finishes, the multipart resolver/container performs cleanup. You should not retain the temp path or MultipartFile object as a saved document. The temp directory needs enough capacity for concurrent uploads, yet data there must not be treated as durable.

The temp directory may reside on container disk; if the filesystem fills up, uploads fail even with plenty of heap free. Conversely, if the threshold keeps many small files in memory, high concurrency increases heap pressure. Choose threshold and location based on measurements and filesystem capacity, not just single-request speed.

### 10.2. Async Processing After the HTTP Response

Mistake:

~~~java
// WRONG if the task runs after the request while retaining the request's MultipartFile.
jobQueue.submit(() -> parseLater(file.getInputStream()));
return ResponseEntity.accepted().build();
~~~

Not only does the fragment above lack IOException handling and a proper return type, the core idea is flawed: the temp file may be deleted once the request ends, and the input stream may no longer be valid.

The architecturally sound approach: **persist the part first**, record metadata/ID, and enqueue a message/job containing the **persistent resource ID or path**—never pass MultipartFile to a worker. If uploads require antivirus or slow transcoding, consider a **PENDING_SCAN** state in a quarantine zone, publishing only after validation/scanning succeeds.

### 10.3. Safer File Saving in Real Systems

Common practice:
1. Write the upload to an **application-owned temporary file** in a controlled area, never static public.
2. Run validation, scanning, checksum, quota, and metadata checks.
3. Once verified, promote to main storage via a controlled transition (atomic rename/move when the filesystem supports it, or object-storage commit).
4. Persist metadata and results to the DB; clean up rejected or incomplete files.
5. Run a cleanup job for orphaned/temp/expired files in case a process crashes mid-flight.

The runnable example in section 7 copies directly to a random filename for simplicity. It demonstrates the multipart API and does not replace a production quarantine/commit workflow.

## 11. Size Errors, Parse Errors, and HTTP Responses

Common symptoms:

| Symptom | Which layer could it originate from? | How to check |
| --- | --- | --- |
| HTTP 413 before reaching Controller | Proxy, ingress, Servlet parser, Spring MVC exception handling | Inspect proxy/container access logs, size limit properties, test directly against app |
| MaxUploadSizeExceededException | Spring MVC/Spring multipart processing | Check both max-file-size and max-request-size, MultipartConfigElement |
| Malformed multipart request / missing boundary | Client and Servlet parser | Check Content-Type, actual boundary, ensure client uses curl -F properly |
| MissingServletRequestPartException | Request lacks the required part | Match the file part name against @RequestParam/@RequestPart |
| HttpMediaTypeNotSupportedException/415 | Endpoint consumes differs from request Content-Type | Use multipart/form-data, do not send plain JSON |
| getInputStream() or Files.copy throws IOException | Storage/temp/permission/disk | Check mount, permissions, free space, and destination path |
| Empty file yet request succeeds | Form submitted an empty part | Check isEmpty() per business rules |
| File saved in the wrong location | Relative path and working directory | Safely log the absolute normalized path |
| HTTP client gets reset on oversized upload | Container/proxy may close or refuse reading body | Check connector/proxy logs; do not assume advice always returns JSON |
| Temp directory grows continuously | Unfinished requests, failed cleanup, high concurrency, or leftover files | Monitor filesystem, request lifecycle, and upload volume |

When **resolve-lazily=true**, some parse exceptions may appear **when the Controller accesses the file**. When false, they can happen before binding. **@ExceptionHandler** only works when the exception reaches Spring MVC; it cannot handle errors blocked completely by a reverse proxy.

To map MaxUploadSizeExceededException to uniform JSON, use @RestControllerAdvice as shown. For proxy-level limit errors, configure error responses at the corresponding proxy/gateway. Keep sufficient metrics/traces to know which components the request passed through.

## 12. Proper Testing: Happy Path, Boundaries, and Production Scenarios

### 12.1. Manual Testing on Real Embedded Tomcat

To verify Servlet limits, run **a real server** and send multipart requests using curl or an HTTP client. At minimum, test:

1. Valid file under the limit → 201, file has exact byte count.
2. Empty file → 400 per the sample API validation.
3. Missing file part → 4xx error due to missing part/binding or wrong media type.
4. File larger than max-file-size → rejected; record the actual rejecting layer and status/error.
5. Multiple parts exceeding max-request-size → rejected.
6. Bad boundary or Content-Type → parse error / 415 depending on request.
7. External directory unwritable or disk full → server/logs reflect I/O failure, never falsely report success.
8. Concurrent requests → observe disk, heap, latency, and written files.

Some containers enforce separate policies for max part count, max swallow size, and connection handling. Testing with the actual embedded server uncovers differences pure unit tests miss.

### 12.2. MockMvc Tests Binding and Business Logic, Not Container Limits

In unit/integration tests using **MockMvc multipart(...)** and **MockMultipartFile**, you can verify that the Controller receives the file, responds properly, and runs validation. However, mock requests **do not go through the same Servlet container parser and temp storage as real HTTP uploads**, so a passing MockMvc test does not prove MultipartConfigElement, disk spool thresholds, or Tomcat size errors.

Example test fragment:

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file",
        "demo.txt",
        "text/plain",
        "hello upload".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/uploads").file(file))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.sizeBytes").value(12));
~~~

Place this snippet inside a test with MockMvc injected/configured and import MockMultipartFile, StandardCharsets, multipart, status, and jsonPath; **it is not a standalone compilable file**. In test environments, the storage directory should also point to a dedicated temp location so tests do not pollute real data.

### 12.3. Observability in Deployed Environments

Track:
- Upload request counts and 2xx/4xx/5xx rates; separate out 413s.
- File/request sizes, p95/p99 latency, and concurrent upload counts.
- Temp and main storage usage; remaining disk space and inodes.
- Client send rates, timeouts, proxy/connector errors, and IOExceptions.
- Validation/scan duration, job backlog, and pending/orphan file counts.
- Limit configuration drift across environments and replicas.

Never log file contents or sensitive tokens/cookies. Sanitize client-supplied filenames before logging and cap their length to avoid log injection; use a request ID for safe log correlation.

## 13. Distinguishing Servlet Multipart from WebFlux Multipart

Both stacks talk about multipart/form-data, but their APIs are not interchangeable:

| Spring MVC Servlet | Spring WebFlux Reactive |
| --- | --- |
| jakarta.servlet.http.Part | org.springframework.http.codec.multipart.Part |
| org.springframework.web.multipart.MultipartFile | org.springframework.http.codec.multipart.FilePart |
| MultipartResolver / StandardServletMultipartResolver | Reactive multipart decoding via HTTP message readers |
| MultipartConfigElement on Servlet registration | WebFlux codecs/limits and corresponding reactive server |
| InputStream/Files.copy typically blocks on Servlet worker | Flux<DataBuffer>, FilePart.transferTo(...) returning Publisher |
| spring.servlet.multipart.* | Corresponding codec/reactive settings; Servlet multipart group does not control it |

If a project includes both spring-boot-starter-web and spring-boot-starter-webflux, Spring Boot typically prefers Spring MVC unless another application type is configured; verify the **actual web application type** before tuning upload properties. Do not copy MultipartFile/MultipartResolver code into WebFlux and expect it to be non-blocking.

## 14. Pre-Production Checklist for Upload Endpoints

- **Content-Type:** Client sends multipart/form-data with a valid boundary; part names match annotations.
- **Servlet setup:** MultipartConfigElement is actually attached to the Servlet; MultipartResolver is properly configured and Boot auto-configuration is not unintentionally disabled.
- **Limits:** Set max-file-size, max-request-size, part count, quotas, and timeouts at both proxy and app; test against a real server.
- **Temp:** Choose location/threshold based on disk/heap calculations and permissions; monitor cleanup, concurrency, and disk full.
- **Lifecycle:** Read/save MultipartFile during the request; never keep temp references past the response or pass raw MultipartFile to async jobs.
- **Path:** Generate server-side names, never use original filename as a path; protect root, symlinks, overwrites, and partial files.
- **Security:** Authentication/authorization, CSRF for browser forms where needed, allowed file types, content verification, malware scanning, and quotas.
- **Durable storage:** Directory or object storage outside the JAR and outside public static paths, with backup/retention, recovery, and a multi-replica strategy.
- **Errors:** Sensible 4xx/413 messages at the rejecting layer; do not assume all parse errors are caught in the Controller.
- **Tests:** Cover happy path, empty, missing part, wrong media type, oversized, disk failure, concurrency, and post-deploy smoke tests.
- **Observability:** Know whether a request stopped at proxy/container/resolver/binding/service; never log file bodies or sensitive data.

**Remember:** MultipartResolver bridges **DispatcherServlet** and the Servlet multipart parser; **MultipartConfigElement** sets Servlet limits/temp location; **MultipartFile** is the interface for reading a request's file part. A file only persists durably when **the application explicitly saves it** in a managed location after validating data and permissions.

## Official References

- Spring Framework 6 — Multipart Resolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- Spring Framework 6 — Multipart Forms / @RequestParam / @RequestPart: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Framework 6.1 — MultipartFile Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- Spring Framework 6 — StandardServletMultipartResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/multipart/support/StandardServletMultipartResolver.html
- Spring Boot 3.3 — Application Properties, spring.servlet.multipart.*: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html
- Spring Boot — Handling Multipart File Uploads: https://docs.spring.io/spring-boot/how-to/spring-mvc.html
