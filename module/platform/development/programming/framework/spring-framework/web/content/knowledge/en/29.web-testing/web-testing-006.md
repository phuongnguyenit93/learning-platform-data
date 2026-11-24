# Testing Multipart, CORS, and Conditional Requests in Spring Web

## 1. Scope and objectives

These three request categories can easily “look like they work” while still breaking at the protocol boundary:

1. **Multipart:** an HTTP request consisting of multiple parts (files and form/JSON data). Tests must verify part names, filenames, per-part content types, contents, validation rules, and processing results, while understanding the difference between mock multipart and real payload parsing.
2. **CORS (Cross-Origin Resource Sharing):** browsers ask the server whether another origin is allowed to access a resource. You must test both **preflight OPTIONS** and **actual requests**; an HTTP 200 alone does not prove a browser will let JavaScript read the response.
3. **Conditional requests:** clients send headers such as `If-None-Match` or `If-Modified-Since` to avoid re-downloading unchanged data, or `If-Match` to prevent overwriting a stale version. Tests must distinguish `200`, `304 Not Modified`, `412 Precondition Failed`, and when required `428 Precondition Required`.

This lesson prioritizes **Spring MVC (Servlet stack)** with `MockMvc`, JUnit 5, and Spring Boot 3.x / Java 17+. Near the end, equivalent guidance is provided for WebFlux / `WebTestClient` and tests running on a real server.

Remember the three layers to check:

| Layer | Question |
| --- | --- |
| HTTP protocol | Are method, URI, multipart boundaries, status, and headers right? |
| Spring handling | Do controller binding, converters, validation, CORS configuration, and cache condition logic execute properly? |
| Browser/container/infrastructure | Does the browser accept CORS, does the servlet container parse real multipart, and do proxies/caches handle headers properly? |

`MockMvc` is highly effective for the second layer, but does not replace all testing at the last layer.

## 2. Choosing the right testing style

- **Plain Java unit test:** calls service/controller methods directly to verify business logic; does not verify request mapping, multipart argument binding, CORS handlers, or MVC-generated status/headers.
- **`MockMvc` with `@WebMvcTest`:** runs MVC dispatching via mock Servlet requests/responses and loads a web application context slice; well suited for request binding, controller advice, converters, validation, preflight/actual CORS, and conditional responses.
- **`MockMvcBuilders.standaloneSetup(...)`:** fast and tests specified controllers, though configs/filters/advice are not automatically loaded as in the full app. To test global CORS via `WebMvcConfigurer` or the Spring Security filter chain, supply the matching configuration explicitly.
- **`@SpringBootTest` + `@AutoConfigureMockMvc`:** keeps the full Spring context and most filters, useful when endpoints depend on security/DB/other services. Still uses mock Servlet requests and does not open a real HTTP socket.
- **`@SpringBootTest(webEnvironment=RANDOM_PORT)` + real HTTP client:** runs the Servlet container and multipart parser, catching size limits, encoding/boundary bugs, proxy/client behavior, and networking issues. Use `TestRestTemplate` or an appropriate HTTP test client; add browser tests when browser CORS policies must be verified.

With the code below, use `@WebMvcTest` for fast, deterministic tests, then supplement with smoke/integration tests against a real server for paths that mocks do not simulate.

## 3. Multipart: what to understand before writing tests

A request with `Content-Type: multipart/form-data; boundary=...` contains multiple parts. Each part can have `Content-Disposition`, a field name, filename, `Content-Type`, and its own content. Example:

~~~http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=xyz

--xyz
Content-Disposition: form-data; name="file"; filename="notes.txt"
Content-Type: text/plain

hello
--xyz
Content-Disposition: form-data; name="tag"

quarterly
--xyz
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"description":"report"}
--xyz--
~~~

Three common binding styles in MVC:

- `@RequestPart("file") MultipartFile file`: reads a file part, accessing `getOriginalFilename()`, `getContentType()`, `getSize()`, `getBytes()`, or stream.
- `@RequestParam("tag") String tag`: reads a text form field.
- `@RequestPart("metadata") Metadata metadata`: reads a **JSON part** via an HTTP message converter; the part must have an appropriate content type, typically `application/json`.

`@RequestParam` for text forms and `@RequestPart` for JSON objects are not completely interchangeable. If the server expects a JSON part while the client sends plain form text, the converter may return a media type or binding error.

### Building requests properly with MockMvc

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file", "notes.txt", "text/plain",
        "hello".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/upload")
        .file(file)
        .param("tag", "quarterly"))
        .andExpect(status().isOk());
~~~

`multipart(...)` builds a `MockMultipartHttpServletRequest` pre-populated with parts/files supplied by the test. **MockMvc does not parse a raw boundary-delimited multipart stream**: this test proves the controller and binding work with constructed mock parts, but does not verify the real parser, Servlet container max file size, or multipart sending from real browsers/clients.

### JSON part alongside a file

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file", "notes.txt", MediaType.TEXT_PLAIN_VALUE,
        "hello".getBytes(StandardCharsets.UTF_8));

MockMultipartFile metadata = new MockMultipartFile(
        "metadata", "", MediaType.APPLICATION_JSON_VALUE,
        "{\"description\":\"report\"}"
            .getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/upload")
        .file(file)
        .file(metadata)
        .param("tag", "quarterly"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.description").value("report"));
~~~

The name `metadata` must match `@RequestPart("metadata")`; when using a JSON DTO, the part content type must be compatible with the converter. Avoid testing a JSON part only via `.param("metadata", "...")` and assuming JSON deserialization was verified.

### Important multipart cases

| Test | Input data | Expected |
| --- | --- | --- |
| Happy path | File with valid key, content type, tag, and optional JSON part | 2xx with accurate returned fields |
| Missing required part | No `file` | Usually `400 Bad Request` when `@RequestPart(required=true)` |
| Empty file | File with zero bytes | Status per app validation, e.g., 400 |
| Wrong content type | `application/octet-stream` file when business logic only accepts `text/plain` | 415 or 400 per contract |
| Wrong field name | Sending `upload` instead of `file` | Missing `file` part → 400 |
| Invalid JSON part | `metadata` with malformed JSON syntax or wrong types | Conversion/binding error, usually 400 |
| Oversized file | Real file exceeding `spring.servlet.multipart.max-file-size` | End-to-end test to go through multipart parser/Servlet container |
| Dangerous filename | `../secret.txt`, very long names, Unicode | Never trust `getOriginalFilename()`; sanitize and enforce server-side paths |
| Size/memory | Large files, many parts | Integration/resource-limit tests, not just assertions on mocks |

Do not compare raw multipart strings containing randomly generated boundaries. Prefer asserting the semantics of each part or capturing requests through a real HTTP server.

## 4. CORS: how preflight differs from actual requests

**Origin** = scheme + host + port. `https://ui.example` and `https://api.example` are two different origins even though both use HTTPS. CORS is a **browser** policy governing whether JavaScript at one origin may read responses from another origin; it does not replace server-side authentication/authorization.

A preflight is typically an `OPTIONS` request with:

~~~http
OPTIONS /api/upload HTTP/1.1
Origin: https://ui.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-trace-id
~~~

A valid response may contain:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: content-type,x-trace-id
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

`Access-Control-Allow-Methods` presentation and scope can vary by Spring/configuration; assert the key elements rather than relying on non-business header ordering.

Preflight is handled directly by Spring MVC CORS processing before invoking the business controller method. If preflight is rejected, the browser usually **does not send the actual request**. However, a tool like `curl` or `MockMvc` can still intentionally send the actual request independently: CORS is not a barrier against non-browser clients.

Actual request:

~~~http
POST /api/upload HTTP/1.1
Origin: https://ui.example
Content-Type: multipart/form-data; boundary=...
~~~

The response needs a matching `Access-Control-Allow-Origin` so the browser allows frontend JS to read the response. For disallowed origins, Spring may return `403 Invalid CORS request`, yet a browser can also block when the server returns 200 without CORS headers; **browser behavior cannot be inferred from status alone**.

### CORS tests should cover

1. Preflight from allowed origin, allowed method/headers: success status and accurate `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`.
2. Actual request from allowed origin: business endpoint runs and response includes `Access-Control-Allow-Origin`.
3. Preflight from disallowed origin: rejected (in default MVC, typically 403).
4. Disallowed method or requested headers: preflight rejected.
5. `Vary: Origin` so shared caches do not mistakenly reuse responses across origins.
6. Credentialed CORS if using cookies/sessions: echo only allowed origins, `Access-Control-Allow-Credentials: true`; **never use wildcard `*` for `allowOrigins` together with credentials**.
7. When Spring Security is present: CORS handles preflight before auth/filters trigger login; configure `http.cors(...)` and CSRF separately for state-changing requests.

MVC annotation example:

~~~java
@CrossOrigin(
    origins = "https://ui.example",
    methods = {RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT},
    allowedHeaders = {"Content-Type", "X-Trace-Id", "If-Match"},
    exposedHeaders = {"ETag"},
    maxAge = 3600
)
@RestController
class ApiController {
    // Endpoints...
}
~~~

`exposedHeaders` determines which headers beyond CORS-safelisted response headers JavaScript is allowed to read (such as `ETag`). `Access-Control-Allow-Headers` tells the browser which request headers it may send. These two settings serve **different purposes**.

## 5. Conditional requests: 304, 412, 428

A GET response can carry validators:

~~~http
HTTP/1.1 200 OK
ETag: "v7"
Last-Modified: Wed, 01 Jan 2025 00:00:00 GMT
Content-Type: application/json

{"version":7,"content":"first"}
~~~

Client validating cache:

~~~http
GET /api/doc HTTP/1.1
If-None-Match: "v7"
~~~

If the representation still has ETag `"v7"`, the server returns `304 Not Modified`, usually with no response body; the client keeps using its cached copy. If the value differs, the server returns the new content, usually `200 OK`.

Corresponding date header:

~~~http
GET /api/doc HTTP/1.1
If-Modified-Since: Wed, 01 Jan 2025 00:00:00 GMT
~~~

If the resource has not been modified since that date, the server can return 304. HTTP dates have only **one-second resolution**; ETags are usually better suited for resources changing multiple times within one second. `If-None-Match` takes precedence over `If-Modified-Since` when both are present.

### ETag: strong/weak and quotes

- Strong validator: `ETag: "v7"`. Used to compare representation identity and as a precondition to prevent lost updates.
- Weak validator: `ETag: W/"v7"`. Useful for semantic cache validation; **do not use weak comparison to satisfy `If-Match`** because `If-Match` requires strong comparison.
- In Spring, `ResponseEntity.ok().eTag("v7")` can add quotes automatically, yet tests should assert the exact HTTP header `"v7"`.
- ETag must change along with actual representation/version changes. A constant ETag for changing data is a cache contract bug.

### Preventing lost updates with If-Match

Two clients read version 7; client A updates to version 8. If B tries to overwrite based on version 7, the server should reject it:

~~~http
PUT /api/doc HTTP/1.1
If-Match: "v7"
Content-Type: application/json

{"content":"client B's edit"}
~~~

When the current ETag is already `"v8"`, the response is `412 Precondition Failed` and no change may occur. If business rules **require** clients to use If-Match and the request omits the header, `428 Precondition Required` can be returned.

| Scenario | Expected |
| --- | --- |
| Unconditional GET | 200 + body + ETag/Last-Modified |
| GET + matching `If-None-Match` | 304, empty body |
| GET + stale `If-None-Match` | 200, new body |
| GET + fresh enough `If-Modified-Since` | 304, empty body |
| PUT + matching strong ETag `If-Match` | Write new version; response per API, e.g., 204 |
| PUT + stale/wrong `If-Match` | 412, **do not mutate state** |
| PUT missing `If-Match` when required by API | 428, do not mutate state |
| PUT + `If-Match: W/"v7"` | Must not be accepted as a strong match |

Two common Spring MVC approaches:

- Return `ResponseEntity.ok().eTag(...).lastModified(...).body(...)`; Spring checks conditional GET/HEAD against the validators to produce 304.
- Explicitly invoke `WebRequest.checkNotModified(etag, lastModified)` when fine-grained flow control is needed; this method can support 304 for GET/HEAD and 412 for state-modifying requests.

For real data updates, the `If-Match` check must be **atomic with the write operation** (optimistic locking, compare-and-swap, or `WHERE version = ?` in the DB). Simply doing `if (currentVersion.equals(ifMatch))` followed by a separate write without locking/CAS still has a race condition.

## 6. Runnable sample project: Spring Boot 3.x + MockMvc

The sample below combines all three feature groups into one project using Java 17+ and Maven. The controller uses in-memory state for demonstration, needing no database, browser, or external network to run tests.

Structure:

~~~text
web-request-tests/
  pom.xml
  src/main/java/demo/WebRequestTestsApplication.java
  src/main/java/demo/ApiController.java
  src/test/java/demo/ApiControllerTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>web-request-tests</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

The project uses JUnit 5, Spring Test, and AssertJ/Hamcrest via `spring-boot-starter-test`; `MockMvc` comes from Spring Test. Spring Security is omitted in the demo to keep pure MVC CORS clear.

### 6.2. src/main/java/demo/WebRequestTestsApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRequestTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRequestTestsApplication.class, args);
    }
}
~~~

### 6.3. src/main/java/demo/ApiController.java

~~~java
package demo;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@CrossOrigin(
    origins = "https://ui.example",
    methods = {RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT},
    allowedHeaders = {"Content-Type", "X-Trace-Id", "If-Match"},
    exposedHeaders = {"ETag"},
    maxAge = 3600
)
public class ApiController {
    private static final long INITIAL_TIME =
            Instant.parse("2025-01-01T00:00:00Z").toEpochMilli();

    private final AtomicReference<State> document =
            new AtomicReference<>(new State(7, "first", INITIAL_TIME));

    record State(long version, String content, long modifiedAt) {
        String etag() {
            return "\"v" + version + "\"";
        }
    }

    public record Metadata(String description) {}
    public record UploadReceipt(
            String filename, long bytes, String tag, String description) {}
    public record DocResponse(long version, String content) {}
    public record UpdateRequest(String content) {}

    // Keeps tests order-independent: each test starts from version 7.
    void reset() {
        document.set(new State(7, "first", INITIAL_TIME));
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<UploadReceipt> upload(
            @RequestPart("file") MultipartFile file,
            @RequestParam("tag") String tag,
            @RequestPart(value = "metadata", required = false)
                    Metadata metadata) {

        if (file.isEmpty() || tag.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        if (!MediaType.TEXT_PLAIN_VALUE.equals(file.getContentType())) {
            return ResponseEntity.status(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE).build();
        }

        return ResponseEntity.ok(new UploadReceipt(
                file.getOriginalFilename(),
                file.getSize(),
                tag,
                metadata == null ? null : metadata.description()));
    }

    @GetMapping(
        path = "/api/doc",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<DocResponse> getDocument() {
        State current = document.get();

        return ResponseEntity.ok()
                .eTag(current.etag())
                .lastModified(current.modifiedAt())
                .body(new DocResponse(
                        current.version(), current.content()));
    }

    @PutMapping(
        path = "/api/doc",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Void> updateDocument(
            @RequestHeader(value = HttpHeaders.IF_MATCH, required = false)
                    String ifMatch,
            @RequestBody UpdateRequest request) {

        if (request == null || request.content() == null
                || request.content().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        if (ifMatch == null) {
            return ResponseEntity.status(
                    HttpStatus.PRECONDITION_REQUIRED).build();
        }

        while (true) {
            State current = document.get();

            // Only an exact strong ETag is allowed to update.
            if (!current.etag().equals(ifMatch)) {
                return ResponseEntity.status(
                        HttpStatus.PRECONDITION_FAILED).build();
            }

            State next = new State(
                    current.version() + 1,
                    request.content(),
                    Instant.now().toEpochMilli());

            // CAS prevents versions from being overwritten across racing requests.
            if (document.compareAndSet(current, next)) {
                return ResponseEntity.noContent().build();
            }
        }
    }
}
~~~

**Why is this logic easy to test?**

- File upload does not need to write to the filesystem; filename, size, tag, JSON part, and status can all be inspected. In real products, sanitize filenames, validate MIME by content if needed, and enforce size/storage limits.
- `@CrossOrigin` restricts the exact demo origin; browser requests from another origin must pass CORS processing.
- GET includes strong `ETag` and `Last-Modified`; Spring MVC handles conditional requests when returning `ResponseEntity`.
- PUT requires `If-Match` and uses CAS instead of a non-atomic check-and-set; tests can confirm state stays unchanged after 412.
- `reset()` only supports the in-memory test demo. Production apps should manage data/versions with persistence that provides optimistic locking.

### 6.4. src/test/java/demo/ApiControllerTest.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(ApiController.class)
class ApiControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ApiController controller;

    private static final String ALLOWED = "https://ui.example";
    private static final String DENIED = "https://evil.example";

    @BeforeEach
    void resetState() {
        controller.reset();
    }

    private MockMultipartFile textFile() {
        return new MockMultipartFile(
                "file", "notes.txt", MediaType.TEXT_PLAIN_VALUE,
                "hello".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void multipartFileAndFormField() throws Exception {
        mvc.perform(multipart("/api/upload")
                .file(textFile())
                .param("tag", "quarterly"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.filename").value("notes.txt"))
            .andExpect(jsonPath("$.bytes").value(5))
            .andExpect(jsonPath("$.tag").value("quarterly"))
            .andExpect(jsonPath("$.description").doesNotExist());
    }

    @Test
    void multipartWithJsonPart() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                "{\"description\":\"report\"}"
                        .getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/upload")
                .file(textFile())
                .file(metadata)
                .param("tag", "quarterly"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.description").value("report"));
    }

    @Test
    void missingFileReturns400() throws Exception {
        mvc.perform(multipart("/api/upload")
                .param("tag", "quarterly"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void emptyFileReturns400() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.txt", MediaType.TEXT_PLAIN_VALUE,
                new byte[0]);

        mvc.perform(multipart("/api/upload")
                .file(empty)
                .param("tag", "quarterly"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongPartContentTypeReturns415() throws Exception {
        MockMultipartFile binary = new MockMultipartFile(
                "file", "raw.bin", "application/octet-stream",
                new byte[]{1, 2, 3});

        mvc.perform(multipart("/api/upload")
                .file(binary)
                .param("tag", "quarterly"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void corsPreflightAllowed() throws Exception {
        mvc.perform(options("/api/upload")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-trace-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("POST")))
            .andExpect(header().exists(HttpHeaders.VARY));
    }

    @Test
    void corsPreflightDeniedOrigin() throws Exception {
        mvc.perform(options("/api/upload")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void corsPreflightDeniedHeader() throws Exception {
        mvc.perform(options("/api/upload")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-not-allowed"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualCorsRequestCarriesAllowOrigin() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS, "ETag"));
    }

    @Test
    void actualCorsRequestDeniedOrigin() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.ORIGIN, DENIED))
            .andExpect(status().isForbidden());
    }

    @Test
    void unconditionalGetReturnsValidators() throws Exception {
        mvc.perform(get("/api/doc"))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.ETAG, "\"v7\""))
            .andExpect(header().exists(HttpHeaders.LAST_MODIFIED))
            .andExpect(jsonPath("$.version").value(7))
            .andExpect(jsonPath("$.content").value("first"));
    }

    @Test
    void matchingIfNoneMatchReturns304WithoutBody() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.IF_NONE_MATCH, "\"v7\""))
            .andExpect(status().isNotModified())
            .andExpect(header().string(HttpHeaders.ETAG, "\"v7\""))
            .andExpect(content().string(""));
    }

    @Test
    void staleIfNoneMatchReturns200WithBody() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.IF_NONE_MATCH, "\"v6\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void ifModifiedSinceCanReturn304() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.IF_MODIFIED_SINCE,
                        "Wed, 01 Jan 2025 00:00:00 GMT"))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void missingIfMatchReturns428() throws Exception {
        mvc.perform(put("/api/doc")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isPreconditionRequired());

        mvc.perform(get("/api/doc"))
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void staleIfMatchReturns412WithoutMutation() throws Exception {
        mvc.perform(put("/api/doc")
                .header(HttpHeaders.IF_MATCH, "\"v6\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isPreconditionFailed());

        mvc.perform(get("/api/doc"))
            .andExpect(jsonPath("$.content").value("first"))
            .andExpect(header().string(HttpHeaders.ETAG, "\"v7\""));
    }

    @Test
    void weakIfMatchDoesNotPassStrongComparison() throws Exception {
        mvc.perform(put("/api/doc")
                .header(HttpHeaders.IF_MATCH, "W/\"v7\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isPreconditionFailed());
    }

    @Test
    void matchingIfMatchUpdatesVersion() throws Exception {
        mvc.perform(put("/api/doc")
                .header(HttpHeaders.IF_MATCH, "\"v7\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/doc"))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.ETAG, "\"v8\""))
            .andExpect(jsonPath("$.version").value(8))
            .andExpect(jsonPath("$.content").value("edited"));
    }
}
~~~

Each test runs independently starting from version 7 thanks to `@BeforeEach`. Tests do not rely on method order and need no sleep or fake clock to compare date/time state.

**Note on 428:** `MockMvcResultMatchers.status().isPreconditionRequired()` is available in Spring Test versions matching HTTP status 428; if using another Spring version, you can substitute `status().is(428)`. In this Spring Boot 3.5 demo, that status API is supported by Spring Test.

### 6.5. Running the tests

In the project directory, with JDK 17+ and Maven:

~~~bash
mvn test
~~~

Passing criteria: test methods receive the statuses and headers matching assertions; Maven completes with `BUILD SUCCESS` and zero failures/errors. The number of tests depends on the test file you save; the example above has 18 `@Test` methods. These are **expected results when the code is configured as described**, not a real execution log.

To inspect error details when a test fails, check `target/surefire-reports`, MVC output via `MockMvcResultHandlers.print()` in the test being debugged, or the test stack trace. Never alter assertions to match accidental values just to turn tests green; verify the API contract first.

## 7. Differences that cause false-positive tests

### 7.1. Mock multipart does not check boundaries/parsers

The `MockMultipartFile` builder creates in-memory file parts directly and does not verify the HTTP parser splitting bytes across boundaries. Thus unit/slice tests can pass even when real uploads fail because:

- The multipart resolver/container is disabled or configured differently.
- `max-file-size`/`max-request-size` is exceeded.
- Boundary is wrong or missing, or overall content type is wrong.
- Filename encoding and binary payloads fall outside normal cases.

Mitigation: add at least one integration test using a real HTTP client hitting `RANDOM_PORT`, sending real multipart data and asserting the response; add an oversized-file case to verify HTTP status/exception mapping. Parser limits may be enforced before the controller runs.

### 7.2. CORS is browser enforcement

`MockMvc` can verify that Spring emitted `Access-Control-Allow-Origin` or rejected a preflight; it is **not a browser**. Test in a real browser or browser automation when integrating cookies, redirects, different domains/ports, SameSite, `credentials: "include"`, Service Workers, proxies, or security filters. A request sent via `curl` from a forbidden origin can still go through at the HTTP level; the browser is what enforces CORS to prevent JS access.

### 7.3. @WebMvcTest has a narrow scope

If CORS is configured via `WebMvcConfigurer` or `CorsFilter` outside the controller slice, `@WebMvcTest(ApiController.class)` needs to import the right config. When Spring Security is present, filters may reject preflight before reaching MVC; use `@Import(SecurityConfig.class)` where appropriate or `@SpringBootTest + @AutoConfigureMockMvc`. In security-enabled tests, set up CSRF and mock users only where matching the contract. Never use `@AutoConfigureMockMvc(addFilters=false)` to evaluate production CORS/security behavior and treat it as sufficient.

### 7.4. Conditional GET is not the same as write concurrency control

`GET If-None-Match` returning 304 saves bandwidth, yet does not prove `PUT If-Match` handles concurrent writes properly. With a DB, integrate an optimistic locking version column and test two concurrent updates; ensure the losing request does not mutate state. ETag must change whenever the representation changes, and private/public caching must match user data sensitivity.

### 7.5. Not checking all headers/bodies

Asserting only `status().isOk()` is insufficient for protocol semantics. Check CORS response headers, ETag/Last-Modified, empty body on 304, JSON part binding, and unchanged state after 412/428. Status 200 on multipart does not prove filename/MIME/data accuracy.

## 8. Additional testing: methods, headers, and cache behavior

### Multipart with another HTTP method

By default `multipart("/api/upload")` creates a POST. If an endpoint accepts PUT/PATCH multipart, select the method explicitly and verify request mapping:

~~~java
mvc.perform(multipart("/api/upload")
        .file(textFile())
        .with(request -> {
            request.setMethod("PUT");
            return request;
        }))
    .andExpect(status().isMethodNotAllowed());
~~~

Because the demo controller only declares `@PostMapping`, `PUT` is valid mock request syntax yet the path has no PUT method, so 405 is expected. If business requirements allow PUT multipart, write `@PutMapping` accordingly and update the expected status. Whether the container's parser supports real PUT multipart must still be checked end-to-end under your Servlet/framework setup.

### CORS preflight and custom headers

If the frontend sends `X-Trace-Id`, preflight must list `x-trace-id` in `Access-Control-Request-Headers`. The server only returns `Access-Control-Allow-Headers` for allowed headers. With `@CrossOrigin(allowedHeaders=...)`, tests should check both accepted and rejected headers.

If JavaScript needs to read `ETag`:

~~~javascript
const response = await fetch("https://api.example/api/doc", {
    mode: "cors"
});
const etag = response.headers.get("ETag");
console.log(etag);
~~~

In the demo, `@CrossOrigin(exposedHeaders={"ETag"})` lets browser JS read ETag when the frontend runs from origin `https://ui.example`. Without exposed headers, JS cannot read ETag even though DevTools still shows the response header.

### Combined conditional headers

Prioritize testing `If-None-Match` when sending both ETag and date. Per HTTP semantics, `If-None-Match` takes precedence over `If-Modified-Since`; do not conclude the server is buggy when it ignores the date while an ETag is present. Add cases for weak headers, malformed dates, HEAD, clock precision, and proxy caching if your API depends on them.

### How is ETag formatted?

`ETag: "v7"` is a header that includes quotation marks; `If-None-Match: v7` without quotes is not equivalent to a valid entity-tag. Start tests using the actual header value received by the HTTP client from GET, then pass that exact value in the subsequent request.

## 9. Testing guidance for Spring WebFlux and WebTestClient

If the endpoint uses **Spring WebFlux** instead of Spring MVC, use `@WebFluxTest` or `WebTestClient` with the appropriate mock or server binding:

~~~java
webTestClient.get()
        .uri("/api/doc")
        .header(HttpHeaders.IF_NONE_MATCH, "\"v7\"")
        .exchange()
        .expectStatus().isNotModified()
        .expectBody().isEmpty();
~~~

CORS preflight tests still use `OPTIONS` with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`:

~~~java
webTestClient.options()
        .uri("/api/upload")
        .header(HttpHeaders.ORIGIN, "https://ui.example")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://ui.example");
~~~

These are **integration snippets**: `webTestClient` must be a bean/test fixture pointing to a correspondingly configured WebFlux controller. CORS and conditional behavior are similar in principle, though server exchange, buffering, and multipart abstractions differ from MVC.

To build a WebTestClient multipart request, use `MultipartBodyBuilder`:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("tag", "quarterly");
builder.part("file", new ByteArrayResource(
        "hello".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "notes.txt";
    }
}).contentType(MediaType.TEXT_PLAIN);

webTestClient.post()
        .uri("/api/upload")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchange()
        .expectStatus().isOk();
~~~

This snippet needs `org.springframework.util.MultiValueMap` via builder, `org.springframework.core.io.ByteArrayResource`, and `BodyInserters`, along with a matching real endpoint. When testing WebFlux handlers, the inbound file object may be `FilePart` instead of Servlet `MultipartFile`. Never copy a Servlet `MultipartFile` controller verbatim to WebFlux and assume it works.

## 10. Pre-release testing checklist

| Group | Minimum cases | Evidence |
| --- | --- | --- |
| Multipart | File with valid name/type/content, form field, and JSON part | Status + accurate bound/processed fields |
| Multipart errors | Missing file, empty, wrong MIME, malformed JSON part | 400/415 per API |
| Multipart integration | Boundary, parser, oversized file, Unicode filename, storage | HTTP test against real server |
| CORS preflight | Allowed origin/method/headers | OPTIONS + CORS response headers |
| CORS rejection | Disallowed origin/headers/method | OPTIONS rejected, no accidental wildcard |
| CORS actual | GET/POST from allowed origin | Business response + Allow-Origin |
| Credentials/Security | Cookies/session/CSRF/auth filters | Filter chain and browser integration |
| Conditional GET | No header, matching/stale ETag, Last-Modified | 200 / 304 + ETag + proper body |
| Conditional mutation | Matching/stale/missing/weak If-Match | 204 / 412 / 428, accurate state/version |
| Concurrency | Two requests updating the same version | Only one update succeeds |
| Cache/proxy | Vary, Cache-Control, CDN/shared cache | Never serve another origin/user's data |

**Rule:** test the **request** (method/headers/parts), test the **response** (status/headers/body), and test **state** after the request. For multipart, add parser integration; for CORS, add browser/security validation; for conditional writes, add atomic version/concurrency validation.

## 11. References

- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Spring Framework — Performing Requests, Multipart: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/requests.html
- Spring Framework — Defining Expectations: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html
- Spring Framework — CORS (MVC): https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Framework — HTTP Caching (MVC): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html
- RFC 9110 — HTTP Semantics, conditional requests: https://www.rfc-editor.org/rfc/rfc9110.html
