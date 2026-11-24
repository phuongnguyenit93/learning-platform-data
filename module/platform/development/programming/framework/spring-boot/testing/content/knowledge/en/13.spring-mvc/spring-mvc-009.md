# Spring MVC: Multipart, Uploads, and Size Limits in Spring Boot Testing

## Goal

A file-upload API cannot merely return HTTP 200 for a valid file. It must also handle **`multipart/form-data`**, accompanying form fields, JSON metadata, empty files, disallowed media types, oversized payloads, untrusted filenames, and errors from the Servlet container layer. Testing solely with one well-formed `MockMultipartFile` leaves many critical bugs undetected.

This lesson helps you:

- Distinguish multipart requests from JSON or `application/x-www-form-urlencoded` requests.
- Use `@RequestParam`, `@RequestPart`, `MultipartFile`, `MockMultipartFile`, and `MockMvcRequestBuilders.multipart(...)` with the right semantics.
- Write upload tests covering both happy and error paths: missing parts, empty files, invalid `Content-Type`, bad JSON metadata, and payloads exceeding business limits.
- Understand **file size**, **request size**, and **file-size-threshold**, along with the path from `MultipartResolver` to the Servlet container.
- Know why **`MockMvc` alone cannot prove the container enforces `spring.servlet.multipart.max-file-size`**.
- Write tests using **Spring Boot / Java 17 / JUnit Jupiter** across two levels: an MVC slice and HTTP integration with an embedded server on a random port.
- Design security, resource, and error-handling upload tests to avoid common vulnerabilities.
- Diagnose 400/413/415 errors, parsers, proxies, servers, and multipart boundaries in CI.

**Key takeaway:** Test controllers with `MockMvc` to verify business guards and MVC binding; test over **real HTTP** to verify multipart parsing and container-enforced limits. Both layers complement each other—neither should stand in as proof for the other.

## 1. What Is Multipart?

An HTTP `multipart/form-data` request carries multiple **parts**, each with its own headers and data payload, separated by a `boundary` string. Browsers typically use this format when forms include files alongside text fields.

Illustrative request:

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary

--DemoBoundary
Content-Disposition: form-data; name="category"

docs
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

hello
--DemoBoundary--
~~~

This is a **protocol illustration for reading**, not a raw HTTP byte capture showing exact `\r\n` endings. When sent over the wire, the boundary in the header and body must match, and MIME multipart separators use CRLF. Applications or HTTP clients normally handle framing for you.

Distinction:

| Request Type | Typical Body | Controller Typically Receives |
| --- | --- | --- |
| `application/json` | Single JSON document | `@RequestBody SomeDto` |
| `application/x-www-form-urlencoded` | `category=docs&count=2` | `@RequestParam`/`@ModelAttribute` |
| `multipart/form-data` | Multiple parts: fields, files, optional JSON | `@RequestParam`, `@RequestPart`, `MultipartFile` |
| `application/octet-stream` | Single raw byte stream | `@RequestBody byte[]` or `InputStream` per design |

**Do not confuse the request's content type with an individual part's content type.** The overall request has `Content-Type: multipart/form-data`, while the `file` part has `Content-Type: text/plain` and a `metadata` part can have `Content-Type: application/json`.

### Two Concepts of Size

- **Single file size:** byte length of an uploaded file's payload, e.g., `file.getSize()`.
- **Entire multipart request size:** includes all file payloads, metadata, text fields, and framing/header/boundary overhead. It can be **larger than the sum of file sizes**.

Thus, a request carrying three 900 KB files may stay under `max-file-size=1MB` per file while still exceeding `max-request-size` if total data plus overhead surpasses the configured limit.

## 2. How Does Spring MVC Process Multipart?

Typical flow in a Spring Boot Servlet MVC application:

~~~text
HTTP client
    |
    | POST multipart/form-data + boundary
    v
Reverse proxy / load balancer (may enforce its own body limit)
    |
    v
Embedded Servlet container, e.g. Tomcat
    |
    | parses multipart per MultipartConfigElement
    | may enforce maxFileSize/maxRequestSize
    v
DispatcherServlet + MultipartResolver
    |
    | exposes MultipartHttpServletRequest/MultipartFile
    v
Spring MVC argument binding
    |
    +-- @RequestParam("category") String
    +-- @RequestParam("file") MultipartFile
    +-- @RequestPart("metadata") UploadMetadata
    |
    v
Controller -> validation -> service/storage
    |
    v
HTTP response
~~~

Spring MVC provides `MultipartResolver`. On modern Servlet stacks, `StandardServletMultipartResolver` delegates to the **Servlet container's** multipart support. Spring Boot normally configures multipart handling and `spring.servlet.multipart.*` properties for Servlet environments. <u>Container limits</u> can be enforced **before the controller begins running**.

Key testing insights:

1. The parser can reject an oversized or malformed multipart request **before a valid `MultipartFile` is even created**.
2. Once parsed, the controller can enforce **additional business limits**, such as an 8-byte cap in a demo API.
3. Clients/proxies can reject large bodies before the request reaches the application; in that case Spring's `@ControllerAdvice` **never sees the request**.
4. `MockMvc` uses mock Servlet objects to invoke MVC handlers, **opens no socket, and bypasses full Tomcat multipart parsing**.

Therefore, "MockMvc sent a 100 MB file and returned 200" does not prove production upload limits are disabled; and "MockMvc rejected 100 MB because the controller checked `getSize()`" does not prove Tomcat's `max-file-size` is configured properly.

## 3. Which Annotations Receive Files and Metadata?

### `@RequestParam` for Files and Ordinary Form Fields

With one file and one text field:

~~~java
@PostMapping(
        path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<String> upload(
        @RequestParam("file") MultipartFile file,
        @RequestParam("category") String category) {
    return ResponseEntity.ok(category + ":" + file.getSize());
}
~~~

This is an illustrative snippet; imports, controller class, and validation are omitted. `MultipartFile` exposes `getName()`, `getOriginalFilename()`, `getContentType()`, `getSize()`, `isEmpty()`, `getInputStream()`, and `transferTo(...)`. **`getOriginalFilename()` is client-supplied input and must never be trusted as a safe filesystem write path.**

### `@RequestPart` for JSON Metadata

When a `metadata` part carries `Content-Type: application/json`, `@RequestPart` lets Spring deserialize JSON into an object using an `HttpMessageConverter`:

~~~java
@PostMapping(
        path = "/files/with-meta",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<String> uploadWithMeta(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return ResponseEntity.ok(
            metadata.category() + ":" + file.getSize());
}
~~~

This snippet requires `UploadMetadata` and appropriate imports. `@RequestPart` with a DTO differs from `@RequestParam("metadata") String`: the former triggers media-type-driven conversion/JSON binding for the part; the latter reads raw text that you would have to parse manually.

When Bean Validation is on the classpath, you can apply `@Valid @RequestPart("metadata") UploadMetadata metadata` with constraints like `@NotBlank` and `@Size` on the DTO. In Spring MVC 6.x, validation failures on request parts typically turn into HTTP 400 under default handling unless customized. Do not assume `@Valid` runs unless a compatible validation starter/provider is declared.

### Uploading Multiple Files

Example API accepting multiple parts named `files`:

~~~java
@PostMapping(
        path = "/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Integer> batch(
        @RequestParam("files") List<MultipartFile> files) {
    return ResponseEntity.ok(files.size());
}
~~~

This snippet illustrates syntax only, not a production-safe endpoint. Multi-file uploads must validate **each file**, **file count**, **total bytes**, request limits, and processing cost. `@RequestParam("files") List<MultipartFile>` binds parts sharing the exact name `files`; if a client sends `file` or `file[]`, names will not automatically match.

## 4. Spring Boot Multipart Limit Properties

In Spring Boot 3.3 Servlet MVC applications, common properties are:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=1MB
spring.servlet.multipart.max-request-size=10MB
spring.servlet.multipart.file-size-threshold=0B
~~~

These are **typical Boot 3.3 defaults**, shown for explanation; you usually do not need to copy them into `application.properties` if the defaults are acceptable.

| Property | Purpose | Boot 3.3 Default |
| --- | --- | --- |
| `spring.servlet.multipart.enabled` | Enables multipart support in Boot Servlet MVC | `true` |
| `spring.servlet.multipart.max-file-size` | Size limit for **a single uploaded file** | `1MB` |
| `spring.servlet.multipart.max-request-size` | Size limit for the entire multipart request | `10MB` |
| `spring.servlet.multipart.file-size-threshold` | Threshold after which uploaded content is written to temp disk | `0B` |
| `spring.servlet.multipart.location` | Directory for temporary files during parsing | Unspecified; depends on config/OS |
| `spring.servlet.multipart.resolve-lazily` | Whether to defer multipart parsing until parts/parameters are accessed | `false` |

`DataSize` properties typically accept `B`, `KB`, `MB`, and `GB` per Boot's configuration parser. **"1MB" is interpreted by Spring Boot's parser**, so avoid casually assuming it equals one million bytes in boundary tests; for precision, use `B` or inspect `MultipartProperties.getMaxFileSize().toBytes()`.

Example test-specific configuration:

~~~properties
spring.servlet.multipart.max-file-size=4B
spring.servlet.multipart.max-request-size=1KB
~~~

This intentionally tiny configuration demonstrates the boundary: a 3-byte file is allowed by the file limit, while a 5-byte file exceeds `max-file-size`. Total HTTP multipart size, including part headers and boundaries, must stay under `max-request-size=1KB` for valid cases.

### `file-size-threshold` Is Not a Rejection Limit

`file-size-threshold` controls **when the container spills uploaded data to temporary disk**, not "reject files larger than this." Rejection thresholds are `max-file-size` and `max-request-size`. Even with `0B` threshold, the app needs sufficient temp disk space, write permissions, and proper temp-file cleanup.

### Do Not Confuse Byte Size with Character Count in UTF-8

The string `"abc"` is 3 UTF-8 bytes; Vietnamese characters like `"ấ"` encode to multiple bytes. `MultipartFile.getSize()` measures **bytes**, not Java `char` count. Byte-limit tests must build deterministic `byte[]` payloads, using `StandardCharsets.UTF_8` when starting from strings.

### Should Limits Be Set to Unlimited?

Some Boot versions allow `-1` for unlimited servlet multipart limits. That is **not a safe default** for public APIs: huge uploads can exhaust disk space, tie up connections, spike GC/memory pressure, and invite denial of service. When large uploads are required, design streaming, quotas, chunked/multipart protocols, or direct object storage alongside proxy and application limits.

## 5. Choosing the Right Test Layer

| What to Verify | Appropriate Tool | Evidence Obtained |
| --- | --- | --- |
| Binding `file` and `category` to controller | `@WebMvcTest` + `MockMvc multipart` | Routing, argument resolution, HTTP status/JSON |
| Missing file, empty file, wrong part name | `MockMvc` | MVC/controller returns proper error |
| JSON part `metadata` parsed properly | `MockMvc` + `MockMultipartFile` with `application/json` | `@RequestPart` and JSON conversion |
| Files > 8 bytes blocked by business logic | `MockMvc` | Guard inside controller/service works |
| Real Tomcat blocks files > `max-file-size` | `@SpringBootTest(RANDOM_PORT)` + real multipart HTTP client | Parser/container behavior in integrated runtime |
| Total request > `max-request-size` | HTTP integration test with multiple parts/headers | Server-level total-body limit |
| Proxy/CDN blocks oversized bodies | Test through the deployed proxy/gateway | Upstream policy outside the JVM |
| File stored and read back accurately | Storage adapter / object store / test directory integration test | Persistence/storage behavior |
| Malware scanning, content sniffing | Adapter/scanner tests and system integration | Actual payload inspection beyond MIME headers |
| Concurrent load, quotas, disk resources | Resource/load tests with safe fixtures | Resource behavior, never proven by a single MockMvc test |

Do not spin up `@SpringBootTest` for every input-validation check when `@WebMvcTest` suffices; equally, never treat a `MockMultipartFile` as proof that Tomcat rejects oversized multipart requests by byte limit.

## 6. Runnable Example: Spring Boot 3.3.5 + Java 17 + JUnit Jupiter

This is a self-contained project with **12 test methods** across two classes:

- `UploadControllerMvcTest`: 9 tests using `MockMvc`, opening no HTTP port.
- `UploadHttpIntegrationTest`: 3 tests with `@SpringBootTest(webEnvironment=RANDOM_PORT)`, sending **real multipart bodies** via `java.net.http.HttpClient`. Configures `max-file-size=4B` to show the parser/container rejecting payloads before the 8-byte business limit.

The example **does not write files to disk**; it reads tiny text payloads and returns JSON to keep focus on binding and size limits. This is not a complete design for a production document-storage system.

### 6.1. File Layout

~~~text
spring-multipart-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/upload/
    │   ├── UploadApplication.java
    │   ├── UploadController.java
    │   └── UploadLimitAdvice.java
    └── test/java/com/example/upload/
        ├── UploadControllerMvcTest.java
        └── UploadHttpIntegrationTest.java
~~~

Preserve the exact paths and packages when copying files. Gradle Wrapper files should be generated by a compatible Gradle installation or copied from an existing configured repository; never hand-write binary `gradle-wrapper.jar`.

**`settings.gradle`**

~~~groovy
rootProject.name = 'spring-multipart-demo'
~~~

**`build.gradle`** — configured specifically for Java 17, Spring Boot 3.3.5:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring MVC, embedded Tomcat by default, and Jackson. `spring-boot-starter-test` provides JUnit Jupiter, Spring MVC Test/MockMvc, and test utilities. This example persists nothing to a DB, so neither `spring-boot-starter-data-jpa` nor Mockito is needed since the controller has no external dependencies.

**`src/main/java/com/example/upload/UploadApplication.java`**

~~~java
package com.example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {

    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
~~~

Placing `@SpringBootApplication` in the parent package lets Spring Boot tests locate the configuration and scan the controller and advice.

### 6.2. Controller Accepting Files, Fields, and JSON Parts

**`src/main/java/com/example/upload/UploadController.java`**

~~~java
package com.example.upload;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    // Demo business rule; independent of Servlet limits.
    private static final long BUSINESS_LIMIT_BYTES = 8;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadReceipt upload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(
                    value = "category",
                    defaultValue = "general") String category)
            throws IOException {
        return createReceipt(file, category);
    }

    @PostMapping(
            path = "/with-meta",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadReceipt uploadWithMeta(
            @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") MultipartFile file)
            throws IOException {
        return createReceipt(file, metadata.category());
    }

    private UploadReceipt createReceipt(
            MultipartFile file, String category)
            throws IOException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "EMPTY_FILE");
        }

        if (file.getSize() > BUSINESS_LIMIT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "BUSINESS_FILE_LIMIT");
        }

        if (!MediaType.TEXT_PLAIN_VALUE.equals(
                file.getContentType())) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "TEXT_FILE_REQUIRED");
        }

        if (category == null || category.isBlank()
                || category.length() > 24) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "INVALID_CATEGORY");
        }

        // Demo only: max 8 bytes; never read large files
        // fully into memory like this in production.
        String text = new String(
                file.getBytes(), StandardCharsets.UTF_8);

        return new UploadReceipt(
                file.getSize(), category, text);
    }

    public record UploadMetadata(String category) {
    }

    public record UploadReceipt(
            long bytes, String category, String text) {
    }
}
~~~

**Check ordering explained:**

1. Empty file → 400 per demo rules.
2. File > 8 bytes that passed the parser → controller returns 413.
3. File part lacking `text/plain` `Content-Type` → 415.
4. Blank or >24-char `category` → 400.
5. Valid input → returns `UploadReceipt` DTO serialized to JSON by Spring/Jackson.

The `Content-Type` check here is **intentionally simple**: exact match on header `text/plain`. In production, MIME headers are **client-supplied claims**; use content sniffing, format-specific parsers, and real payload validation for risky file types. Never conclude a file is "safe" just because its MIME header looks right.

`file.getBytes()` allocates a byte array in RAM if used unchecked. This example does so only because the **business limit is 8 bytes**. For large files, stream via `getInputStream()`/`transferTo(...)` or storage adapters and enforce infrastructure limits before buffering data.

### 6.3. Advice Converting Container Multipart Size Errors to HTTP 413

**`src/main/java/com/example/upload/UploadLimitAdvice.java`**

~~~java
package com.example.upload;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadLimitAdvice {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, String>> handleLimit(
            MaxUploadSizeExceededException exception) {
        return ResponseEntity.status(
                HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of(
                        "error", "MULTIPART_LIMIT_EXCEEDED"));
    }
}
~~~

This advice handles `MaxUploadSizeExceededException` only once Spring MVC routes the error into exception resolution. It **does not catch all failures** from proxies, servlet containers, or TCP; containers/proxies can abort before Spring constructs a response and return a different error. In the pinned demo tests with small payloads and default embedded Tomcat, the parser surfaces the size limit via Spring MVC to produce HTTP 413.

Do not blindly map all `MultipartException`s to 413: corrupt multipart framing, missing boundaries, I/O failures, or client disconnects are **distinct conditions**. Reserve 413 for explicit size-limit violations; define separate handling for other parser failures.

## 7. MVC Slice Tests with `MockMvc` and `MockMultipartFile`

**`src/test/java/com/example/upload/UploadControllerMvcTest.java`**

~~~java
package com.example.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(UploadController.class)
class UploadControllerMvcTest {

    @Autowired
    private MockMvc mockMvc;

    private static MockMultipartFile textFile(String body) {
        return new MockMultipartFile(
                "file",
                "note.txt",
                MediaType.TEXT_PLAIN_VALUE,
                body.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void validFileAndFormFieldReturnReceipt()
            throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("hello"))
                        .param("category", "docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bytes").value(5))
                .andExpect(jsonPath("$.category").value("docs"))
                .andExpect(jsonPath("$.text").value("hello"));
    }

    @Test
    void emptyFileIsRejected() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingFilePartIsRejected() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .param("category", "docs"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void businessLimitAboveEightBytesReturns413()
            throws Exception {
        // This is the business guard, NOT the container limit.
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("123456789")))
                .andExpect(status().is(413));
    }

    @Test
    void disallowedFileContentTypeReturns415()
            throws Exception {
        MockMultipartFile invalid =
                new MockMultipartFile(
                        "file",
                        "report.bin",
                        MediaType.APPLICATION_OCTET_STREAM_VALUE,
                        new byte[] {1, 2, 3});

        mockMvc.perform(
                multipart("/api/uploads").file(invalid))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void blankCategoryIsRejected() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads")
                        .file(textFile("ok"))
                        .param("category", "   "))
                .andExpect(status().isBadRequest());
    }

    @Test
    void jsonMetadataPartIsDeserialized() throws Exception {
        MockMultipartFile metadata =
                new MockMultipartFile(
                        "metadata",
                        "metadata.json",
                        MediaType.APPLICATION_JSON_VALUE,
                        "{\"category\":\"reports\"}".getBytes(
                                StandardCharsets.UTF_8));

        mockMvc.perform(
                multipart("/api/uploads/with-meta")
                        .file(textFile("abc"))
                        .file(metadata))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bytes").value(3))
                .andExpect(jsonPath("$.category").value("reports"))
                .andExpect(jsonPath("$.text").value("abc"));
    }

    @Test
    void missingMetadataPartReturns400() throws Exception {
        mockMvc.perform(
                multipart("/api/uploads/with-meta")
                        .file(textFile("abc")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonMetadataReturns400() throws Exception {
        MockMultipartFile metadata =
                new MockMultipartFile(
                        "metadata",
                        "metadata.json",
                        MediaType.APPLICATION_JSON_VALUE,
                        "{not-json}".getBytes(
                                StandardCharsets.UTF_8));

        mockMvc.perform(
                multipart("/api/uploads/with-meta")
                        .file(textFile("abc"))
                        .file(metadata))
                .andExpect(status().isBadRequest());
    }
}
~~~

### What Do These Tests Prove?

- **`validFileAndFormFieldReturnReceipt`**: MVC binding extracts the `file` part, the `category` form field, and returns the contracted JSON.
- **`emptyFileIsRejected`**: `MultipartFile.isEmpty()` is handled properly by the controller.
- **`missingFilePartIsRejected`**: a missing required part is rejected by the MVC argument resolver; distinct from a present part containing 0 bytes.
- **`businessLimitAboveEightBytesReturns413`**: 9 bytes are rejected by the **controller guard**, because the business limit is 8 bytes. This **does not prove** `spring.servlet.multipart.max-file-size` is enforced.
- **`disallowedFileContentTypeReturns415`**: the controller validates the part's header, though it does not guarantee the content is genuinely text.
- **`blankCategoryIsRejected`**: invalid form field input is rejected.
- **`jsonMetadataPartIsDeserialized`**: the JSON part is deserialized by Jackson into `UploadMetadata` via `@RequestPart`.
- **`missingMetadataPartReturns400`**: MVC rejects a missing required part.
- **`malformedJsonMetadataReturns400`**: invalid JSON causes a message conversion failure, returning 400 under default handling.

**Total of 9 `@Test` methods in this class.** Tests run MVC handlers on mock requests/responses; no real TCP port is opened and no disk writes occur. Error checks verify **status** only, since default bodies for `ResponseStatusException` and binding errors vary with application error handling.

### An Easy Misconception About `MockMultipartFile`

`MockMultipartFile` is a test implementation of `MultipartFile`. It accepts `byte[]`, part name, filename, and content type and exposes them directly to the handler. `MockMvcRequestBuilders.multipart(...)` uses `MockMultipartHttpServletRequest` to **simulate pre-parsed multipart data**.

As a result:

- A 20 MB `MockMultipartFile` can still reach the controller in `MockMvc` even when Boot configures `max-file-size=1MB`.
- The reason is that **there is no full servlet-container multipart parser/limit enforcement**, not that Boot's property is broken.
- Use MockMvc to test business guards (such as 8 bytes).
- Send **real** HTTP multipart requests through an embedded server or equivalent deployment to test container limits.

Even using `@AutoConfigureMockMvc` inside `@SpringBootTest` while calling `mockMvc.perform(multipart(...))` still runs MockMvc; loading the full context **does not turn simulated requests into real HTTP**.

## 8. HTTP Integration Tests: Verifying Embedded Servlet Container Limits

To test `spring.servlet.multipart.max-file-size`, run the app with an HTTP server and send a real multipart request. In the example below, Spring Boot starts embedded Tomcat on a random port, and Java 17's `HttpClient` constructs a raw multipart body with valid boundaries.

**`src/test/java/com/example/upload/UploadHttpIntegrationTest.java`**

~~~java
package com.example.upload;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.web.servlet.MultipartProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.util.unit.DataSize;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = UploadApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.servlet.multipart.max-file-size=4B",
                "spring.servlet.multipart.max-request-size=1KB"
        })
class UploadHttpIntegrationTest {

    private static final String BOUNDARY = "CaseBoundary";

    @LocalServerPort
    private int port;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private MultipartProperties multipartProperties;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> sendFile(String text)
            throws Exception {

        byte[] prefix = (
                "--" + BOUNDARY + "\r\n"
                + "Content-Disposition: form-data;"
                + " name=\"file\"; filename=\"note.txt\"\r\n"
                + "Content-Type: text/plain\r\n\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        byte[] payload =
                text.getBytes(StandardCharsets.UTF_8);

        byte[] suffix = (
                "\r\n--" + BOUNDARY + "--\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        byte[] body = new byte[
                prefix.length + payload.length + suffix.length];

        System.arraycopy(
                prefix, 0, body, 0, prefix.length);

        System.arraycopy(
                payload, 0, body, prefix.length, payload.length);

        System.arraycopy(
                suffix, 0, body,
                prefix.length + payload.length,
                suffix.length);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/uploads");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header(
                        "Content-Type",
                        "multipart/form-data; boundary=" + BOUNDARY)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void springBindsExplicitMultipartLimits() {
        assertTrue(port > 0);
        assertEquals(
                DataSize.ofBytes(4),
                multipartProperties.getMaxFileSize());
        assertEquals(
                DataSize.ofBytes(1024),
                multipartProperties.getMaxRequestSize());
    }

    @Test
    void realMultipartWithinFileLimitSucceeds()
            throws Exception {

        HttpResponse<String> response = sendFile("abc");

        assertEquals(200, response.statusCode());

        JsonNode json = mapper.readTree(response.body());
        assertEquals(3, json.path("bytes").asLong());
        assertEquals(
                "general",
                json.path("category").asText());
        assertEquals("abc", json.path("text").asText());
    }

    @Test
    void realMultipartAboveContainerLimitReturns413()
            throws Exception {

        // 5B exceeds max-file-size=4B, yet remains below
        // business limit=8B, so the controller is not the cause.
        HttpResponse<String> response = sendFile("abcde");

        assertEquals(413, response.statusCode());
    }
}
~~~

### Reading the Real HTTP Tests

- Test 1 verifies Boot bound **the exact 4B and 1KB settings** into `MultipartProperties`. That alone does not prove the container enforces them, hence the next two tests.
- Test 2 sends 3 bytes in a **valid boundary-framed multipart HTTP request**. The Servlet container parses the part, the controller receives `MultipartFile`, and returns 200 with exact JSON.
- Test 3 sends 5 bytes. Since 5 > `max-file-size=4B` yet 5 < **business limit=8B**, receiving HTTP 413 proves the request was blocked **at or before the server's multipart layer**, routed through `UploadLimitAdvice` into 413.
- `max-request-size=1KB` comfortably accommodates the demo request (including part headers and framing). This test does not yet separately check **exceeding total request size**; the next section explains how to add that test.

Expectations above apply to **Spring Boot 3.3.5, default embedded Tomcat, and this sample project's error advice**. When switching containers, proxies, or connection-swallow settings, oversized requests can be reset before controller/advice emits JSON. In such environments, define the **expected HTTP behavior** and tune integration tests to your real infrastructure; never assert 413 as universal across every container and proxy.

### Why Assemble Multipart Bytes Manually?

So the example requires only Java 17 and standard Boot dependencies. `HttpClient` lacks a built-in high-level multipart builder found in some third-party clients; `prefix/payload/suffix` produces a valid boundary-framed request with CRLFs. Real-world tests may use RestAssured, Apache HttpClient, `TestRestTemplate` with `MultiValueMap`, or another test client; what matters is sending requests through a **real HTTP server and parser**.

**Never cite `"client sends 5 characters"` as proof of byte count** when Unicode is involved: this test uses ASCII, so 5 chars equal 5 UTF-8 bytes. For Unicode data, construct the byte array explicitly and check `payload.length` against the threshold.

## 9. Testing `max-request-size` Separately from `max-file-size`

These two limits deserve **two separate test scenarios**, since a single oversized file can trip the file-level limit before the request-level limit is triggered.

### Separating the Cases

- **File-level case:** one 5-byte file with `max-file-size=4B`, `max-request-size=1KB` → exceeds the per-file limit.
- **Request-level case:** every individual file/part stays **below `max-file-size`**, while the total body (including form fields and boundaries) **exceeds `max-request-size`** → exceeds the total request limit.

To test request-level enforcement, write a dedicated integration test class configured with:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.servlet.multipart.max-file-size=256B",
                "spring.servlet.multipart.max-request-size=180B"
        })
class TotalMultipartSizeLimitExample {
    // Use a real multipart HTTP client.
    // Create multiple small parts and verify total body > 180 bytes.
    // Assert response per Servlet container/advice mapping.
}
~~~

This is an **illustrative configuration snippet**, not a full runnable class and not counted among the project's 12 methods. Depending on filename length, `Content-Disposition`, boundaries, and headers, even one part can consume substantial framing bytes. When testing `max-request-size`:

1. Deliberately construct a body with **multiple parts or enough metadata** so you know the exact total byte count.
2. Verify the actual request body size **exceeds the request limit**.
3. Verify no individual file part **exceeds `max-file-size`**.
4. Send the request through the real embedded server.
5. Verify the infrastructure's error response and ensure the business action **did not succeed**.
6. Never use `MockMvc.multipart(...).file(...).param(...)` to claim Servlet `max-request-size` was tested.

An application behind an upstream proxy with its own request limit can reject payloads before Tomcat sees them. If protecting a public gateway contract, test through that gateway/proxy rather than only the embedded server.

## 10. Which Layers Enforce "Too Large" Limits?

An upload can be rejected at several layers:

~~~text
Client
  |
  v
CDN / API gateway / reverse proxy
  |-- Content-Length/body limits, timeouts, rate limits
  v
Servlet container multipart parser
  |-- maxFileSize, maxRequestSize, temp disk & parser constraints
  v
Spring MVC/controller/service
  |-- isEmpty, content type, business byte limits, owner/ACL
  v
Storage adapter / object store
  |-- quotas, antivirus scanning, file naming, storage policies
  v
Audit, metadata, cleanup
~~~

HTTP 413 typically indicates "Content Too Large / Payload Too Large," yet **you cannot tell which layer blocked the request from the status code alone**. To prove container-level enforcement, design inputs that do **not** trip the app's business guard—like the 5B > 4B yet < 8B test in Section 8. To prove proxy limits, send traffic through the proxy and verify corresponding logs/test metadata.

### Why Multi-Layer Limits Still Matter

Proxy limits stop abuse early before spending JVM resources. Servlet limits protect parsing and temporary storage. Business limits enforce product policies by file type, tenant, or workflow. Storage quotas protect long-term capacity. They **complement rather than replace each other**.

For large/streaming uploads, never let the controller buffer an entire file into RAM before checking size. Enforce declared and streaming byte counts with a counting stream while relying on container/proxy caps to block early and clean up partial writes on failure.

## 11. Binding Errors and HTTP Statuses to Test

| Scenario | Behavior to Verify | Test Level |
| --- | --- | --- |
| Valid `file` part | 2xx + expected metadata | MockMvc and real HTTP |
| Present `file` part with 0 bytes | 400 per demo policy | MockMvc |
| Missing `file` part | MVC reports missing part, usually 400 | MockMvc |
| Misspelled part name `document` | Controller expects `file`, usually 400 | MockMvc |
| Disallowed file `Content-Type` | 415 per demo policy | MockMvc |
| Valid JSON metadata | `@RequestPart` parses DTO properly | MockMvc |
| Missing/corrupt metadata | 400 per MVC/JSON conversion | MockMvc |
| File > 8B business limit | 413 from controller guard | MockMvc |
| File > 4B servlet `max-file-size` yet < 8B | Rejected before success logic | Real HTTP |
| Total multipart > `max-request-size` | Rejected before success handling | Real HTTP |
| Non-`multipart/form-data` request | 415 when handler declares `consumes` | MockMvc/real HTTP |
| Invalid auth | 401/403 per security config | Tests with real Spring Security |
| Malicious filename / spoofed MIME | Cannot write arbitrary paths | Unit/service/storage integration |
| Storage out of space / permission denied | No false success; proper cleanup | Storage/integration |

**Do not conflate "missing file" and "empty file."** With an empty file, the part still exists and `isEmpty()` returns `true`. When the part is completely absent, MVC can throw `MissingServletRequestPartException` before the controller executes. Both paths can return 400 yet originate in **two different processing layers**.

### What Do 400, 413, and 415 Mean in the Sample Lesson?

- **400 Bad Request:** missing required input per contract or empty file/invalid metadata/invalid category.
- **413 Payload Too Large:** exceeds the business byte limit or Servlet multipart byte limit when mapped to this response.
- **415 Unsupported Media Type:** the file part claims a media type disallowed by the demo contract.

Depending on the application, invalid file types may be designed to return 400 or 422; what matters is an **explicit API convention and consistent tests**. The demo chooses 415 for disallowed part types.

## 12. Multipart JSON Metadata and Bean Validation

An upload API may attach multi-field metadata:

~~~json
{
  "category": "reports",
  "description": "Quarterly summary",
  "expiresInDays": 7
}
~~~

To deserialize into a DTO and run Bean Validation, define a Java record:

~~~java
public record DocumentMetadata(
        @NotBlank String category,
        @Size(max = 100) String description,
        @Min(1) @Max(365) int expiresInDays) {
}
~~~

and controller:

~~~java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Void> upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return ResponseEntity.accepted().build();
}
~~~

These two snippets **illustrate an extended design**, not part of the demo project. In real code, add `jakarta.validation.*` imports, a validation provider such as `spring-boot-starter-validation`, and file/storage checks. `@Valid` does not validate `MultipartFile` byte size without a dedicated constraint or custom validation; `@Size` on `description` checks only the metadata field.

In MockMvc tests, metadata is a **JSON part** with `Content-Type: application/json`, not a `param("metadata", "{...}")` string that Spring will always parse as an object. When testing `@RequestPart`, pass a part with the exact name and media type to genuinely exercise `HttpMessageConverter`.

### Validating JSON Metadata vs. Validating Files

- DTO: checks category, description, expiry days, cross-field relationships.
- File: checks byte size, emptiness, extension, MIME header, actual content/magic bytes, checksum, and storage policy.
- Total request: checks part/file count, total size, quotas, and timeouts.
- Actor: checks upload/tenant/quota permissions; never treat client metadata as the source of truth for access control.

A test proving `@Valid` returns 400 when `description` is too long **does not prove** file scanners or container size limits work.

## 13. Filenames, Paths, and Upload Security

`MultipartFile.getOriginalFilename()` is a **client-supplied name**. It can be blank, contain relative/absolute paths, Unicode characters, cross-OS path separators, or strings designed to spoof extensions.

**Never save files by joining paths directly:**

~~~java
// UNSAFE PATTERN: never use in production.
Path destination = uploadDir.resolve(
        multipartFile.getOriginalFilename());
multipartFile.transferTo(destination);
~~~

If the filename is `../../config.properties` or contains unusual separators, this can cause **path traversal** or overwrite existing files without protection. Tests should include malicious filenames and verify they **never directly dictate the storage path**.

Common defense-in-depth strategies:

1. Server generates a fresh storage key, e.g., UUID/random token—**never use raw client filenames as filesystem paths**.
2. Store the display filename separately as metadata, sanitized/escaped for UIs, never as a system path.
3. Restrict file types, sizes, files per request, and per-user/org quotas.
4. Store outside the webroot or in isolated object storage with explicit permissions and lifetimes.
5. Scan content and validate magic bytes/file parsers per policy rather than trusting MIME/extensions.
6. Write to staging/quarantine storage and publish only after validation/scanning and metadata commit succeed.
7. Clean up temp files on mid-request failures without returning success.
8. Never log raw file contents, tokens, personal data, or sensitive paths in CI.

**MockMvc can help test filename inputs and validation logic.** However, filesystem permissions, object-store ACLs, write atomicity, and failure cleanup must be tested at the corresponding storage/integration layer.

### "Spoofed File" Cases to Test

- Filename `report.pdf` whose real bytes are not a PDF.
- MIME `image/png` whose bytes lack the PNG signature.
- Zip archive with extreme decompression ratio (zip bomb).
- Files carrying active payloads, HTML/SVG scripts, or macros.
- Filenames containing `..`, path separators, control characters, or tricky Unicode normalization sequences.
- Repeated part names, duplicate filenames, abnormally long part names.
- Multipart payloads missing closing boundaries or with corrupt headers.
- Client disconnecting mid-upload, storage quota exhausted, or full temp disk.

Not every scenario belongs in one controller test. Put each test at the layer where the failure is observable: parser/container, scanner, storage, or API gateway.

## 14. `MockMultipartFile`, `MockPart`, and Servlet `Part`

`MockMultipartFile` works when controllers accept `MultipartFile`. Spring MVC also supports `jakarta.servlet.http.Part` on the Servlet stack. When testing APIs accepting `Part`, use `MockPart`:

~~~java
MockPart part = new MockPart(
        "file",
        "note.txt",
        "abc".getBytes(StandardCharsets.UTF_8));

part.getHeaders().setContentType(MediaType.TEXT_PLAIN);

mockMvc.perform(
        multipart("/api/uploads/part").part(part))
        .andExpect(status().isOk());
~~~

This snippet illustrates creating `MockPart` and sending it via `multipart(...).part(...)`; the endpoint `/api/uploads/part` **is not in the runnable project**, so define a handler accepting `Part` if practicing with it. `MockPart` belongs to Spring Test.

**Differences to remember:**

- `MultipartFile` is Spring's convenient abstraction for file uploads.
- `Part` is the Jakarta Servlet API.
- Both `MockMultipartFile` and `MockPart` are test doubles; they do not force a real container to parse raw boundaries and enforce all limits.
- Never pick a mock type just to make tests pass easily. Match the **controller's parameter type and testing goal**.

## 15. PUT/PATCH Uploads and Container Differences

`MockMvcRequestBuilders.multipart(...)` defaults to POST; the builder API lets you specify other HTTP methods when needed. However, **do not assume every Servlet container supports multipart parsing on PUT/PATCH the same way as POST**. Standard Servlet parsing and `StandardServletMultipartResolver` vary by media type, HTTP method, container implementation, and Boot/Spring versions.

For public upload APIs using POST, test the standard `multipart/form-data` path first. If business requirements demand PUT/PATCH, write **integration tests on the target container** verifying HTTP method, proxy behavior, and parser together rather than just switching the method in MockMvc.

### Is Form URL-Encoded Multipart?

No. `application/x-www-form-urlencoded` encodes fields in a single flat body; it does not carry binary file payloads separated by multipart boundaries. When a controller specifies `consumes = MULTIPART_FORM_DATA_VALUE`, sending JSON or form URL-encoded data is typically rejected by content type. If an API supports multiple formats, define explicit mappings and test each independently; never loosen `consumes` merely to force a misconfigured test to pass.

## 16. File and Request Limits in Production Architecture

### Memory Usage

Reading whole files with `getBytes()` is convenient in tiny tests but allocates large byte arrays in production. With 100 MB files under concurrency, total RAM can spike sharply. For large uploads, prefer streaming or bounded storage-transfer APIs instead of buffering whole files in memory.

### Temp Disk Resources

With `file-size-threshold=0B`, the container may spill parts to a temporary directory during parsing depending on implementation. Insufficient disk space or missing permissions can fail requests before reaching the controller. CI environments should ensure the temp directory exists, is writable, has enough space, and is cleaned up per lifecycle; MockMvc tests do not reproduce temp-disk pressure.

### Part Counts and Concurrency

Even if every individual file stays below the cap, a request with excessive parts or heavy concurrency still consumes CPU, RAM, file descriptors, and disk. Alongside byte caps, enforce policies for **files per request, total parts, per-tenant byte quotas, rate limiting, and timeouts** at appropriate layers.

### Reverse Proxies Can Reject Early

Systems often sit behind Nginx, Envoy, CDNs, or API Gateways with their own body-size limits and timeouts. If the proxy caps bodies at 2 MB while Boot allows 5 MB, clients still get 413 from the proxy before the controller ever runs. Tests hitting `localhost:<random-port>` directly miss proxy behavior; a deployment E2E test must hit the real public/private entrypoint per contract.

### Status Responses for Oversized Requests

Spring throws exceptions like `MaxUploadSizeExceededException` at the multipart layer. However, servers or proxies may reset connections, return custom error pages, or emit 413 without hitting `@ControllerAdvice`. To avoid brittle implementation-coupled tests, define the **expected scope**:

- In the embedded Tomcat demo: advice catches the size exception → expect HTTP 413.
- Behind a proxy: if policy requires uniform JSON errors, configure the proxy/gateway accordingly; controllers cannot enforce JSON bodies for requests blocked upstream.
- If clients observe `IOException`/connection resets from early rejection, inspect infrastructure before blaming business validation.
- Never treat "HTTP request failed" as sufficient: distinguish **intentional limit enforcement** from timeouts or server crashes.

## 17. Running the Project and Reading Results

From the directory containing `settings.gradle`/`build.gradle` and the Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run just the MVC slice:

~~~bash
./gradlew test --tests 'com.example.upload.UploadControllerMvcTest'
~~~

Run just HTTP integration:

~~~bash
./gradlew test --tests 'com.example.upload.UploadHttpIntegrationTest'
~~~

With the complete project from Sections 6–8, expect **9 + 3 = 12 JUnit `@Test` runs**. Tests do not call `System.out.println`, so there is **no fixed business stdout**; Gradle reports `BUILD SUCCESSFUL` when all tasks succeed, or `UP-TO-DATE` when reusing cached outputs.

View reports:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.upload.UploadControllerMvcTest.xml
    └── TEST-com.example.upload.UploadHttpIntegrationTest.xml
~~~

In multi-project builds, these paths live under the test module's `build` directory. To force re-execution during investigation instead of using cached results:

~~~bash
./gradlew test --rerun-tasks
~~~

If the project lacks a Wrapper, generate one with a compatible installed Gradle version; for the Java 17/Spring Boot 3.3.x demo, for example:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit the scripts and `gradle-wrapper.jar`/`gradle-wrapper.properties` per repository workflow. In existing projects, prefer the repository's existing Wrapper rather than upgrading Gradle just for the demo.

### Manual HTTP Verification with cURL

When the demo app runs for real via:

~~~bash
./gradlew bootRun
~~~

with default settings (without the 4B test properties), you can call:

~~~bash
curl -i \
  -F "file=@note.txt;type=text/plain" \
  -F "category=docs" \
  http://127.0.0.1:8080/api/uploads
~~~

This assumes `note.txt` exists containing **1–8 bytes** and the app is listening on port 8080. If the file is missing or `server.port` changed, adjust the input/port. `@SpringBootTest(properties=...)` on the test class **does not apply to `bootRun`**; those are separate contexts. If `note.txt` exceeds 8 bytes, the controller returns 413 per the business limit.

Example sending a JSON part:

~~~bash
curl -i \
  -F 'file=@note.txt;type=text/plain' \
  -F 'metadata={"category":"reports"};type=application/json' \
  http://127.0.0.1:8080/api/uploads/with-meta
~~~

Quoting syntax differs between Linux/macOS shells and Windows PowerShell/cmd. When tests allocate random ports, never hardcode 8080; read the port from `@LocalServerPort` or logs/test context.

## 18. Common Errors and Diagnostics

| Symptom | Common Cause | Proper Fix |
| --- | --- | --- |
| 415 even though file has right MIME | Request missing `multipart/form-data` or `consumes` mismatch | Check **request Content-Type** and part Content-Type separately |
| 400 `Required part 'file' is not present` | Wrong part name or no file sent | Send `name="file"` matching `@RequestParam("file")` |
| 400 with `@RequestPart` metadata | Missing JSON part, wrong media type, malformed JSON | Send `metadata` part with `application/json` matching DTO |
| MockMvc passes large file with 200 | Simulated request skips container multipart parser/limits | Test business guard or add a real HTTP test |
| MockMvc returns 413 yet runtime accepts large files | Controller guard and Servlet `maxFileSize` are separate policies | Verify actual properties and real HTTP parser |
| `MaxUploadSizeExceededException` | File or request exceeded limit | Check policy, measure byte sizes, map to 413 where appropriate |
| 413 happens before controller/advice | Proxy or container rejected early | Check proxy logs, server limits, and actual route |
| `Connection reset` on large upload | Server/proxy closed socket while body was unread | Inspect network/container, max swallow/timeouts, error policy |
| 1 MB file still rejected | MB vs. B calculation difference, multipart overhead, or `max-request-size` | Use exact byte sizes and test boundaries |
| Multi-file upload exceeds total limit | `max-request-size` smaller than sum of parts + framing | Calculate/build full payload and test request-level limit |
| Temp disk/permission errors | Container spills to temp dir lacking space/permissions | Configure `location`/permissions/space and temp cleanup |
| Passes locally, fails in CI | Port/hostname, temp disk, timeouts, parallel tests | Use `RANDOM_PORT`, isolated fixtures, resource limits, cleanup |
| Downloaded file has wrong name | Used original filename as storage key/path | Generate server-side storage IDs and keep metadata separate |
| Spoofed MIME file slips through | Trusted client-sent header/extension | Use content sniffing, parsers, and scanners |
| Test counts characters instead of bytes | UTF-8 Unicode byte length differs from Java chars | Use `file.getSize()` and real byte arrays |
| Wrong-size upload returns HTTP 200 | Missing business validator or layer misconfiguration | Assert policy violations at the exact layer involved |
| GET to upload endpoint returns 405 | Controller maps POST only | Use matching HTTP method and `multipart(...)` |
| Security tests return 401/403 | Security filter/CSRF requires auth/token | Supply security test fixtures/credentials; never disable security blindly |
| Test fails from filesystem state | Filename/path collisions, uncleaned previous data | Isolate storage fixtures and clean up after tests |

### Step-by-Step Debugging Order

1. **Check HTTP method and request `Content-Type`.** With `consumes=multipart/form-data`, do not send raw JSON.
2. **Check part names and headers.** `file`, `metadata`, and each part's `Content-Type` must match; inspect sanitized request logs.
3. **Determine whether failure occurred before or after the controller.** If business guards never ran, inspect the parser, proxy, size limits, and security.
4. **Check actual byte sizes** of files and total request payloads—never rely on filenames or character counts.
5. **Verify bound configuration** via `MultipartProperties`, non-sensitive config logs, and integration tests.
6. **Check container/proxy.** An Nginx 413 is not the same as an exception handled by controller advice.
7. **Inspect root cause** of `MultipartException`, I/O exceptions, or HTTP errors; never alter expected status merely to make a test green.
8. **Place tests at the right layer.** MockMvc for MVC/business logic, HTTP integration for parser/limits, storage integration for persistence.

## 19. Self-Study Exercises

**Exercise A — Empty file vs. missing part:** Run `emptyFileIsRejected` and `missingFilePartIsRejected`. Explain why both return 400 yet one delivers an empty `MultipartFile` while the other is rejected by MVC argument resolution.

**Exercise B — Business limit boundary:** Send 8-byte and 9-byte files with MockMvc. In the demo code, 8 bytes succeed (with `text/plain` MIME and valid category) while 9 bytes return 413. Explain why this **does not test** container `max-file-size`.

**Exercise C — Servlet limit boundary:** Keep `spring.servlet.multipart.max-file-size=4B` in HTTP integration. Send valid 4-byte and 5-byte multipart requests. Expect 4 bytes to pass the container and 5 bytes to be blocked. Verify the controller's 8-byte business limit proves 5 bytes did not hit the business threshold.

**Exercise D — Total request limit:** Pick a `max-file-size` large enough for each part, and set `max-request-size` smaller than the raw multipart body including fields, files, and boundaries. Run a real HTTP test and explain why checking only `sum(file.getSize())` misses framing and fields.

**Exercise E — JSON part:** Change `metadata` from `application/json` to `text/plain` when the controller expects `UploadMetadata`. Observe the conversion error or 415 depending on MVC config; fix the **part's** `Content-Type` without changing the outer request's `Content-Type` to JSON.

**Exercise F — Multiple files:** Add an endpoint accepting `List<MultipartFile>`. Write tests for zero files, one file, too many files, and excessive total bytes. Specify which cases belong to controller business limits versus Servlet request limits.

**Exercise G — Malicious filenames:** Test `originalFilename` set to `../../secret.txt`. Build a storage abstraction generating server-side IDs and verify the destination path never contains client-controlled path segments. Never write real files outside a test temp directory during practice.

**Exercise H — Storage write failure:** Simulate a storage adapter hitting quota or throwing `IOException` after creating a temp file. Verify the API does not return success and cleans up properly; decide what should use mocks/fakes versus real storage integration tests.

## 20. Checklist for Spring MVC Upload Tests

- [ ] Does the controller distinguish `@RequestParam` form/file parts from `@RequestPart` JSON metadata?
- [ ] Does the HTTP request use `multipart/form-data` with boundaries, and do parts have matching names and media types?
- [ ] Do tests cover both **empty files** and **missing file parts** without conflating them?
- [ ] Do tests verify byte sizes, file types, field validation, and error statuses per contract?
- [ ] Do you avoid treating `MockMultipartFile` as proof of Servlet parser/file-size limit enforcement?
- [ ] Are `max-file-size` and `max-request-size` intentionally configured for tests without adopting unsafe production values?
- [ ] Do you have a **real HTTP integration test** for container-enforced limits when required?
- [ ] Is `file-size-threshold` understood as a spill-to-disk threshold, **not a rejection limit**?
- [ ] Do size tests measure **bytes** rather than character counts or filenames?
- [ ] If behind a proxy/gateway, do you account for proxy limits separately from Boot limits?
- [ ] Do you avoid trusting client `originalFilename`, MIME headers, or extensions as safe?
- [ ] Are large file payloads streamed/bounded with proper quotas, scanning, and cleanup?
- [ ] Do tests cover storage failures, permission errors, temp disk shortages, and concurrency where required?
- [ ] Do Gradle/JUnit reports confirm tests actually executed rather than skipping as `UP-TO-DATE`?
- [ ] Are all test fixtures and files safe, never overwriting production files or data?

## 21. Official References

Use these sources to verify behavior against your exact project dependencies. The demo uses **Spring Boot 3.3.5 / Spring Framework 6.1.x**, so recheck APIs/configs when upgrading or changing Servlet containers:

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.servlet.multipart.max-file-size`, `max-request-size`, `file-size-threshold`, `resolve-lazily`.
- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html): how Boot uses the Servlet `Part` API and upload limit properties.
- [Spring Framework — Multipart Controller Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `@RequestParam`, `@RequestPart`, `MultipartFile`, JSON metadata, and validation.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): `StandardServletMultipartResolver` and container parsers.
- [Spring Framework — MockMvc Performing Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): `multipart(...)` uses mock requests and does not parse real multipart requests.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): scope of MVC tests without a listening server.

**Remember:** `MockMvc.multipart(...)` verifies **Spring MVC binding and controller logic**, yet does not by itself prove **upload size limits enforced by the Servlet container**. Distinguish `max-file-size`, `max-request-size`, business limits, and gateway/proxy limits. For trustworthy upload tests, pick the right layer, verify both success and error responses, test with deterministic byte payloads, and guard storage safely.