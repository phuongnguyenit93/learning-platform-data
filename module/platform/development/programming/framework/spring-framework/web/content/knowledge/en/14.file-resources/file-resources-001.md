# MultipartResolver and Servlet Container Multipart Configuration in Spring MVC

## 1. Objectives

When a client submits a form containing a file (image, document, CSV, etc.) to a Spring MVC endpoint, the request typically has `Content-Type: multipart/form-data`. For `@RequestParam MultipartFile` or `@RequestPart` to receive the data, not only the controller but also the **Servlet container** and the **`MultipartResolver`** mechanism must work together properly.

After this lesson, you will be able to:

1. Read a multipart structure and distinguish between an **HTTP part**, `jakarta.servlet.http.Part`, `MultipartFile`, and `MultipartHttpServletRequest`.
2. Accurately explain how **`DispatcherServlet` detects the resolver with bean name `multipartResolver`** and how the **Servlet container parses the body**.
3. Configure size limits, the temporary directory, and the disk-write threshold using **Servlet multipart config**, without confusing them with methods on `StandardServletMultipartResolver`.
4. Use `spring.servlet.multipart.*` in **Spring Boot 3.x**, knowing what is auto-configured and when you need to declare a `StandardServletMultipartResolver` bean yourself.
5. Distinguish between `resolveLazily` and `strictServletCompliance` along with their impact on when errors occur and portability.
6. Build a Java 17+ application with standard upload and file-plus-JSON-part upload endpoints, invoke them with `curl -F`, and test them with MockMvc.
7. Identify 400/413/415 errors, size limits, temporary data issues, and risks of spoofed filenames, path traversal, oversized payloads, or malicious files.

**Lesson versions:** Spring Framework **6.x**, Spring Boot **3.x**, Servlet API `jakarta.servlet.*`, Java 17+. Spring Framework 6 removed the legacy `CommonsMultipartResolver`; the implementation covered here is **`StandardServletMultipartResolver`**, which is based on Servlet `Part`. Examples do not apply to Spring WebFlux (WebFlux uses a separate reactive multipart API).

## 2. What is Multipart/form-data?

An HTML file upload form can be written as:

~~~html
<form method="post" action="/api/uploads/simple"
      enctype="multipart/form-data">
  <input type="file" name="file">
  <input type="text" name="note">
  <button type="submit">Upload</button>
</form>
~~~

`enctype="multipart/form-data"` is the difference compared to a standard URL-encoded form. The actual body is split into **parts** using a client-generated boundary:

~~~http
POST /api/uploads/simple HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=demoBoundary

--demoBoundary
Content-Disposition: form-data; name="note"

document
--demoBoundary
Content-Disposition: form-data; name="file"; filename="hello.txt"
Content-Type: text/plain

Hello Spring
--demoBoundary--
~~~

The example above is for **explaining the wire structure**, not to require typing boundaries by hand. In a real request, line endings use CRLF and the file portion can be **binary bytes** rather than human-readable text.

Each part has its own headers. `Content-Disposition` typically contains a `name` matching the form field; a file part may carry a client-supplied `filename`. A part's `Content-Type` indicates the data type declared by the client, but it **does not prove the file is safe or has the true MIME type**.

**Do not manually set** the `Content-Type: multipart/form-data` header when using `curl -F` or JavaScript `FormData`: the client must append the `boundary` matching the body. Setting Content-Type manually without a boundary is a common reason the container fails to parse the request.

## 3. Who Actually Parses Multipart: Container or Spring?

In Spring MVC 6.x:

~~~text
HTTP multipart request
        |
        v
Servlet container (Tomcat/Jetty/Undertow ...)
        |
        v
DispatcherServlet
        |
        +-- looks up bean named "multipartResolver"
        |          |
        |          v
        |  StandardServletMultipartResolver
        |          |
        |          v
        |  Servlet request.getParts() / Part
        |          |
        |          v
        |  MultipartHttpServletRequest
        |
        v
Handler adapter --> @RequestParam MultipartFile /
                    @RequestPart / Part
        |
        v
Controller --> Response
~~~

**Division of responsibilities:**

- **Servlet container** (for example, Boot's embedded Tomcat) provides parsing according to the Servlet multipart API. It is configured on the **servlet registration** via `MultipartConfigElement`, `<multipart-config>` in `web.xml`, or the equivalent Servlet mechanism. This is where **max file size, max request size, temporary storage location, and file size threshold** are set.
- **`StandardServletMultipartResolver`** is Spring MVC's adapter/strategy built on `request.getParts()`. It detects eligible requests, triggers parsing (eagerly or lazily), wraps the request into a `MultipartHttpServletRequest`, and coordinates resource cleanup.
- **`DispatcherServlet`** uses the resolver found by the **fixed bean name `multipartResolver`**. It does not automatically pick a `MultipartResolver` bean with an arbitrary name in a plain MVC configuration.
- **Controller** receives the processed parts as `MultipartFile`, `Part`, form data, or a JSON DTO from an appropriate part.

A Spring resolver **does not replace the Servlet container's parser**. If multipart parsing is not enabled on the servlet registration, merely adding `new StandardServletMultipartResolver()` is usually still not enough.

Conversely, when the Servlet supports `getParts()` but Spring MVC lacks the expected resolver, a controller using `MultipartFile` may not bind properly through the MVC multipart flow; using `Part` directly is a different Servlet-based mechanism. Determine the integration approach rather than randomly changing handler annotations.

## 4. `MultipartResolver` and `StandardServletMultipartResolver`

The `org.springframework.web.multipart.MultipartResolver` interface is the strategy contract with these key methods:

| API | Meaning |
| --- | --- |
| `isMultipart(HttpServletRequest)` | Whether the request matches the resolver's multipart criteria |
| `resolveMultipart(HttpServletRequest)` | Parse/wrap the request into a `MultipartHttpServletRequest` |
| `cleanupMultipart(MultipartHttpServletRequest)` | Clean up temporary resources after processing when appropriate |

`StandardServletMultipartResolver` is the Servlet Part API implementation in Spring MVC 6.x. Two options worth remembering:

### 4.1. `setResolveLazily(boolean)`

- **Default `false`**: Spring attempts to parse parts immediately during the `resolveMultipart` phase. Multipart parsing errors typically occur early, before entering the handler.
- **`true`**: defers parsing until the application accesses a file/parameter/part. Size errors or malformed body errors may be thrown **later**.

Note: lazy does not mean the container strictly never reads the request early; middleware, filters, or other code may access parameters/parts beforehand, triggering processing. What changes primarily is **when Spring requests parsing**. When debugging exceptions, you must understand the request lifecycle.

### 4.2. `setStrictServletCompliance(boolean)`

- **Default `false`**: the resolver attempts to handle `multipart/*` requests depending on the container parser's capabilities.
- **`true`**: only wraps **`multipart/form-data`** requests, allowing other multipart subtypes to be handled by a custom path if needed.

Containers differ on media types other than `multipart/form-data`. According to Spring Javadoc, for example, Tomcat may accept other multipart requests that Jetty does not. Use `strictServletCompliance=true` when you want clear form-upload semantics and higher portability; if the application has a specialized `multipart/mixed` use case, you must design an appropriate handling path yourself.

**Do not treat strict=true as improving file upload security**: it only changes the media type criteria applied by the resolver; it does not scan for viruses or validate file contents.

### 4.3. Declaring the Bean in MVC Without Boot Auto-Config

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.multipart.MultipartResolver;
import org.springframework.web.multipart.support.StandardServletMultipartResolver;

@Configuration
public class MultipartResolverConfig {

    @Bean(name = "multipartResolver")
    public MultipartResolver multipartResolver() {
        StandardServletMultipartResolver resolver =
                new StandardServletMultipartResolver();
        resolver.setResolveLazily(false);
        resolver.setStrictServletCompliance(true);
        return resolver;
    }
}
~~~

This is a **complete Java class** for Spring Framework 6.x, but for uploads to work you also need **Servlet multipart config on the DispatcherServlet registration** and other controller/web context configuration. The bean name `multipartResolver` is a key requirement.

**Do not copy this bean into every Spring Boot application**: Boot 3.x normally registers the resolver automatically when multipart is enabled and auto-configuration conditions are met. Declaring an extra one can unintentionally override behavior configured via properties.

## 5. Servlet Container: Where to Set Limits and the Temporary Directory?

In the Jakarta Servlet API, `MultipartConfigElement` accepts these parameters:

~~~java
new MultipartConfigElement(
        "/var/tmp/my-app-upload", // location
        2L * 1024 * 1024,         // maxFileSize: 2 MiB
        3L * 1024 * 1024,         // maxRequestSize: 3 MiB
        0                         // fileSizeThreshold: write temp to disk
);
~~~

This is an **illustrative Java expression**, not a standalone application file. The size parameters here are **byte counts** in the Servlet constructor, not Spring Boot DataSize strings.

- **`location`**: the directory the container uses to store parts written to disk/temporary files. The directory must exist or be managed by the container in a supported way, be writable by the server process, have sufficient space, and have managed access permissions.
- **`maxFileSize`**: maximum size **per file/part** enforced by the container parser (bytes).
- **`maxRequestSize`**: maximum size of the **entire multipart request**, including all parts and boundary/header overhead; typically needs to be larger than the single-file limit.
- **`fileSizeThreshold`**: threshold before parts are written to disk by the container; a threshold of 0 may cause the container to use disk very early. Exact behavior depends on the container.

**Important:** There is no equivalent `setMaxUploadSize(...)` API on Spring 6's `StandardServletMultipartResolver` to replace Servlet registration limits. Guides configuring `CommonsMultipartResolver#setMaxUploadSize` for older Spring versions **no longer apply** to Framework 6.

### 5.1. Configuring Servlet Registration in Java (Without Boot)

Illustrative example in a plain Spring MVC initializer:

~~~java
import jakarta.servlet.MultipartConfigElement;
import jakarta.servlet.ServletRegistration;
import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class AppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[]{MvcConfig.class};
    }

    @Override
    protected String[] getServletMappings() {
        return new String[]{"/"};
    }

    @Override
    protected void customizeRegistration(
            ServletRegistration.Dynamic registration) {

        registration.setMultipartConfig(new MultipartConfigElement(
                "/var/tmp/my-app-upload",
                2L * 1024 * 1024,
                3L * 1024 * 1024,
                0
        ));
    }
}
~~~

**This is a plain MVC illustration**, not used directly in the hands-on Boot project in section 7. You need to define an appropriate `MvcConfig` config class (containing the resolver and MVC controllers), ensure the directory exists with write permissions, and install a Servlet container for deployment; this file cannot compile on its own without `MvcConfig`.

Depending on the architecture, `<multipart-config>` can also be configured directly in the servlet registration in `web.xml`. For **Spring Boot embedded Servlet**, the preferred approach is the properties in the next section, avoiding duplicate configuration of the same limits in multiple places.

## 6. What Does Spring Boot 3.x Auto-Configure?

With the `spring-boot-starter-web` dependency and multipart enabled, Spring Boot includes **`MultipartAutoConfiguration`**, which is responsible for creating `MultipartConfigElement` and `StandardServletMultipartResolver` when needed, based on `MultipartProperties` (`spring.servlet.multipart.*`). Boot also uses auto-configuration conditions so it does **not** create duplicate beans when the application already defines corresponding custom configurations.

Key distinctions:

| Question | Plain Spring MVC | Typical Spring Boot 3.x |
| --- | --- | --- |
| Who adds the `multipartResolver` bean? | You declare it yourself | Boot typically auto-configures it |
| Who enables multipart on the Servlet? | Initializer / `web.xml` | Boot creates `MultipartConfigElement` |
| Where do upload limits live? | Registration config | `spring.servlet.multipart.max-*` |
| What parses the request body? | Servlet `Part` | Also Servlet `Part` |
| Should `@EnableWebMvc` be added to enable uploads? | Only when plain MVC config is needed | **Not** needed and may disable other auto-config |
| Is the Commons FileUpload library needed? | No | No |

### 6.1. Main Properties in `application.properties`

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true
~~~

**Line-by-line explanation:**

- `enabled=true`: allows Boot to auto-configure multipart handling (typically enabled by default).
- `max-file-size=2MB`: limit per file of about 2 MiB under Boot's `DataSize` mechanism (unit suffixes must be understood per Boot rules, not mistaken for milliseconds or file count).
- `max-request-size=3MB`: limit for the entire request; must account for text/JSON parts and overhead. If 2 files of 2MB each are allowed, a 3MB total request limit is **not enough**.
- `file-size-threshold=0B`: temp-write threshold; another value can be chosen once memory/disk limits are understood.
- `resolve-lazily=false`: parse multipart eagerly at the resolver stage.
- `strict-servlet-compliance=true`: resolver only wraps `multipart/form-data`, avoiding subtype differences across containers.

According to Spring Boot 3.5 `MultipartProperties` documentation, the **defaults** are **1MB** for file size, **10MB** for request size, and **0** for threshold. Do not confuse these defaults with product policy; if the application allows multiple files or varied file types, choose appropriate limits based on your threat model.

### 6.2. Configuring the Temporary Directory

You can add:

~~~properties
spring.servlet.multipart.location=/var/tmp/myapp-multipart
~~~

**Do not enable this line blindly on Windows or machines lacking that directory.** When omitted, Boot/the Servlet container typically uses the default temporary directory. For production, allocate a dedicated directory on a volume with quotas, least-privilege permissions, a cleanup mechanism, and disk space monitoring.

The multipart `location` value is **not** the destination directory for permanent file storage. Do not assume a request succeeded permanently just because the Servlet created a temporary file. For durable storage, the application must explicitly validate and persist the file through its own mechanism.

### 6.3. Do Not Confuse With Other Size Limits

A large request can be blocked before reaching the resolver due to:
- A reverse proxy (e.g., Nginx, API gateway, ingress) having its own body size limit.
- The Servlet connector/container having other parameters or total request limits.
- A WAF / system security layer.
- Application validation / business rules after parsing.

Therefore, `spring.servlet.multipart.max-file-size=2MB` is **not sufficient to guarantee the exact HTTP status** across all deployments. The response could be 413, 400, another error, or a dropped connection before reaching Spring depending on which layer rejects it and how exceptions are handled.

## 7. Runnable Spring Boot 3.x Application

This hands-on example has two endpoints:

- `POST /api/uploads/simple`: accepts a file and a form note.
- `POST /api/uploads/with-json`: accepts a file and a **JSON part** via `@RequestPart`.

To make inspection easy, the controller **does not persist the file permanently**; it only reads metadata to verify the body was parsed/bound properly. This avoids assuming temporary files can be used long after the request ends. Production code must safely persist actual contents after validation.

Create a Spring Initializr project with **Java 17+**, **Spring Boot 3.x**, **Maven**, dependencies **Spring Web** and **Spring Boot Starter Test**; package `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/UploadController.java
src/main/resources/application.properties
src/test/java/com/example/demo/UploadControllerTest.java
~~~

### 7.1. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.2. `application.properties`

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true
~~~

There is no need to manually create a `StandardServletMultipartResolver` bean when keeping this default Boot configuration.

### 7.3. `UploadController.java`

~~~java
package com.example.demo;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    @PostMapping(
            path = "/simple",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> simple(
            @RequestParam("file") MultipartFile file,
            @RequestParam(name = "note", defaultValue = "") String note) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("EMPTY_FILE"));
        }
        if (note.length() > 100) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("NOTE_TOO_LONG"));
        }

        return ResponseEntity.ok(new UploadReceipt(
                file.getOriginalFilename(), file.getSize(), note));
    }

    @PostMapping(
            path = "/with-json",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> withJson(
            @RequestPart("file") MultipartFile file,
            @RequestPart("metadata") UploadMetadata metadata) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("EMPTY_FILE"));
        }
        if (metadata.label() == null ||
                metadata.label().isBlank() ||
                metadata.label().length() > 100) {
            return ResponseEntity.badRequest()
                    .body(new UploadError("INVALID_LABEL"));
        }

        return ResponseEntity.ok(new UploadReceipt(
                file.getOriginalFilename(),
                file.getSize(),
                metadata.label()));
    }

    public record UploadMetadata(String label) {}
    public record UploadReceipt(String originalName, long size, String note) {}
    public record UploadError(String code) {}
}
~~~

**Explanation:**

- `@RequestParam("file") MultipartFile` reads the file part by form field name. `MultipartFile` provides `isEmpty()`, `getSize()`, `getOriginalFilename()`, `getContentType()`, `getInputStream()`, and `transferTo(...)`.
- `@RequestParam("note") String` reads a regular form parameter; in the example `defaultValue=""` allows omitting the note.
- `@RequestPart("metadata") UploadMetadata` uses an **`HttpMessageConverter`** for the part body, typically Jackson when the part declares `Content-Type: application/json`. Do not confuse a JSON part with a form field containing a JSON string without the appropriate content type.
- `@RequestPart("file") MultipartFile` also binds a file part; both `@RequestParam` and `@RequestPart` work well for files, while JSON DTOs should explicitly use `@RequestPart`.
- `file.getOriginalFilename()` is **client-supplied**, may contain path segments or special characters, and must not be trusted to build disk paths. Here it is returned in JSON **only for observing the result**, not as a permanent storage filename.
- `file.getContentType()` comes from the request; it does not verify the true nature of the file. The size and label checks in the example are **illustrative only**; production requires stricter validation.
- `file.isEmpty()` is true for an empty file / zero-content upload, not a malware rule. If zero-byte files are allowed by business logic, adjust the condition.
- This lesson creates no database/storage, so "upload succeeded" in the example means **parsed and metadata read**, not persisted as a resource.

### 7.4. Running and Calling With `curl -F`

Run inside the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if Maven is installed without the wrapper, use `mvn spring-boot:run`.

Create a UTF-8 file containing `Hello Spring` named `hello.txt`. Call:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads/simple"   -F "file=@hello.txt;type=text/plain"   -F "note=demo"
~~~

When the file contains the 12 bytes `Hello Spring`, the expected result is **HTTP 200 OK** and a JSON body equivalent to:

~~~json
{"originalName":"hello.txt","size":12,"note":"demo"}
~~~

Note: if the file has a trailing newline, BOM, or different encoding/bytes, `size` will differ from 12. Do not assume an actual file's size in examples without checking its byte count.

For the endpoint with a JSON part:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads/with-json"   -F "file=@hello.txt;type=text/plain"   -F 'metadata={"label":"report"};type=application/json'
~~~

Expected result is HTTP 200 with `note="report"` and `size=12` if the file is exactly 12 bytes:

~~~json
{"originalName":"hello.txt","size":12,"note":"report"}
~~~

**Do not manually add** `-H "Content-Type: multipart/form-data"` because `curl -F` generates the boundary matching the body automatically.

If the file is missing or a part is misnamed, argument resolution may fail (typically HTTP 400) before `file.isEmpty()` runs. If the file has a name but an empty body, it enters the branch returning JSON `{"code":"EMPTY_FILE"}` provided the request parses successfully.

### 7.5. Sending Multipart From a Browser

~~~javascript
async function sendFile(file, note) {
  const form = new FormData();
  form.append("file", file);
  form.append("note", note);

  const response = await fetch("/api/uploads/simple", {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    throw new Error("Upload failed: " + response.status);
  }
  return await response.json();
}
~~~

The browser automatically generates the boundary when `body` is a `FormData`. To send a JSON part, you can do:

~~~javascript
const form = new FormData();
form.append("file", chosenFile);
form.append(
  "metadata",
  new Blob([JSON.stringify({label: "report"})], {
    type: "application/json"
  })
);

await fetch("/api/uploads/with-json", {
  method: "POST",
  body: form
});
~~~

This is a browser snippet where `chosenFile` has already been obtained from a file input or the File API. `Blob` creates a part with media type `application/json`. You do not need to serialize the entire `FormData` as JSON.

## 8. Testing the Controller With MockMvc

Create the file **`src/test/java/com/example/demo/UploadControllerTest.java`**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(UploadController.class)
class UploadControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readsFormFileAndNote() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "hello.txt",
                "text/plain",
                "Hello Spring".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/uploads/simple")
                        .file(file)
                        .param("note", "demo"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.originalName").value("hello.txt"))
                .andExpect(jsonPath("$.size").value(12))
                .andExpect(jsonPath("$.note").value("demo"));
    }

    @Test
    void readsJsonPartThroughMessageConverter() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "hello.txt", "text/plain",
                "Hello Spring".getBytes(StandardCharsets.UTF_8));

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "",
                "application/json",
                "{\"label\":\"report\"}".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/uploads/with-json")
                        .file(file)
                        .file(metadata))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.size").value(12))
                .andExpect(jsonPath("$.note").value("report"));
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.txt", "text/plain", new byte[0]);

        mockMvc.perform(multipart("/api/uploads/simple")
                        .file(empty))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("EMPTY_FILE"));
    }

    @Test
    void rejectsOversizedNoteByBusinessRule() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "one.txt", "text/plain", new byte[]{65});

        mockMvc.perform(multipart("/api/uploads/simple")
                        .file(file)
                        .param("note", "x".repeat(101)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("NOTE_TOO_LONG"));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

MockMvc verifies **argument binding, file parts, JSON parts, and controller logic** without opening a real HTTP socket. The `readsJsonPartThroughMessageConverter` test proves that the `metadata` part is parsed into a Java record via Jackson when the media type is correct.

### 8.1. Why MockMvc Is Not Enough to Test Container `max-file-size`?

`MockMultipartFile` and `MockMultipartHttpServletRequest` generally construct pre-parsed multipart data in test memory. **They do not simulate the real Servlet connector, disk storage, and multipart parser of Tomcat/Jetty/Undertow.** Therefore, a MockMvc test uploading 5MB may **not** be rejected by `spring.servlet.multipart.max-file-size=2MB` even though production blocks it.

To test actual size limits, you need to:
- Run an **embedded server on a real HTTP socket**, e.g. `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an HTTP client sending real multipart requests.
- Or run the server and use `curl -F` with a file larger than the limit, inspecting both the response **and logs at the container/proxy**.
- Separately test requests larger than `max-request-size`, multiple small files whose total exceeds the limit, zero-byte files, malformed JSON parts, and missing boundaries.

Do not hard-assert 413 in a MockMvc controller slice; the status of an oversized request also depends on **which layer rejects it and how exceptions are handled**.

## 9. The Two Limits: `max-file-size` and `max-request-size`

| Setting | What it measures | Example |
| --- | --- | --- |
| `max-file-size=2MB` | Each individual file | A 2.5MB file may be rejected |
| `max-request-size=3MB` | Total multipart request | Two 1.8MB files may exceed the total |
| `file-size-threshold=0B` | Memory-to-disk threshold per container | May create temporary files immediately |
| Reverse proxy max body | Entire HTTP body before the app | May reject before Spring sees it |
| Controller validation | After request parsing | May reject files even below parser limits |

**Enforce limits in multiple layers:** reverse proxy, Servlet, business logic, and storage quotas. A limit only inside the controller is too late: the container may already have read/spooled huge amounts of data before the handler runs. When accepting multiple files, remember to limit **file count, total size, and aggregate resources per user**.

If multi-GB uploads are required, design specifically for them: streaming, chunked/resumable uploads, direct-to-storage with time-limited signed URLs, quotas, and an anti-malware pipeline. Do not simply raise `max-file-size` to several GB and call `MultipartFile.getBytes()` on the whole file, since `getBytes()` loads the content into the heap.

## 10. Lazy Parsing and Exception Handling

### 10.1. Eager Parsing (Default)

`spring.servlet.multipart.resolve-lazily=false` corresponds to `resolver.setResolveLazily(false)`. When `DispatcherServlet` receives a multipart request, the resolver can request parsing immediately. Size errors, missing boundaries, broken temp directories, or permission errors may occur **before the controller is invoked**.

Therefore, a `try/catch` block inside the handler:

~~~java
@PostMapping("/upload")
public String upload(@RequestParam MultipartFile file) {
    try {
        return "OK";
    } catch (Exception ex) {
        return "ERROR";
    }
}
~~~

This is an **unsuitable pattern for handling all multipart errors**: if parsing fails before entering the method, this `catch` cannot catch the exception. Use MVC exception handling if the exception passes through `DispatcherServlet`; errors rejected by a proxy or container before Spring must be handled at that layer.

### 10.2. Lazy Parsing

`spring.servlet.multipart.resolve-lazily=true` tells Spring to defer parsing until a parameter/file is accessed. It can change the stack trace location and where `MultipartException` is thrown, **does not increase size limits**, and does not make parsing guaranteed to succeed.

Lazy configuration is useful in certain specialized flows, but harder to debug if multiple interceptors/filters access request parameters. Do not enable lazy parsing as a "fix for 413 errors"; inspect the actual limits instead.

### 10.3. `MaxUploadSizeExceededException` and HTTP 413

In cases caught by Spring MVC and recognized as `MaxUploadSizeExceededException`, you can map it to **413 Payload Too Large** via `@RestControllerAdvice`:

~~~java
@RestControllerAdvice
public class UploadExceptionAdvice {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "FILE_TOO_LARGE"));
    }
}
~~~

**This is an additional illustrative class, not part of the runnable app in section 7.** You need to import `org.springframework.web.multipart.MaxUploadSizeExceededException`, `java.util.Map`, `org.springframework.http.HttpStatus`, `ResponseEntity`, `@ExceptionHandler`, and `@RestControllerAdvice`. When the server/Servlet container throws a different exception or a proxy rejects the request before MVC, this handler is **not guaranteed** to run. Log safely and test end-to-end against a real container.

Use `413` when a body exceeding policy can be responded to by the application. Do not rely on every oversized request always producing `MaxUploadSizeExceededException`; some connectors may close the connection or emit an error earlier.

## 11. Temporary Directory, `MultipartFile` Lifecycle, and Durable Storage

`MultipartFile` represents uploaded data for the **current request**, which may reside in memory or a temporary file depending on the parser and threshold.

Key points:
- **Temporary upload storage** is not a durable data store. The framework/container may clean it up after the request completes.
- Do not hold a `MultipartFile` reference in singletons, queues, or async tasks to read after the request has ended. If background work is needed, **move/copy the data into controlled storage first**, with clear transaction/cleanup handling.
- `transferTo(Path/File)` can be used to save data, but move/copy semantics and relative paths depend on the implementation. For reliability, use a normalized absolute path inside an allowed storage area and design appropriate atomic moves.
- Uploaded files are not automatically public resources. Do not serve them back through a static resource handler without access control and proper response `Content-Type`/`Content-Disposition`.
- When an exception occurs mid-flight, application temp files must have cleanup and quotas; the resolver's cleanup for a multipart request does not automatically clean up every copy created by the application.

### 11.1. Never Trust Client-Supplied Filenames

`file.getOriginalFilename()` may contain `../`, path separators, unusual Unicode characters, or duplicate names. In real systems, never write:

~~~java
// UNSAFE
Path target = uploadRoot.resolve(file.getOriginalFilename());
file.transferTo(target);
~~~

This is an **anti-pattern** illustrating path traversal/collision/overwrite risks. Do not merely strip `../` with a simple string replace and assume it is safe; normalize paths, choose server-side names, and enforce clear storage policies.

A better approach is usually:
1. Server generates an **unpredictable random ID**, such as a UUID, as the storage key.
2. If preserving an extension, derive the extension from an allowed-file-type policy and **detect the actual file type** rather than trusting the client's name/Content-Type.
3. Store under a directory outside the public document root, with least-privilege permissions, symlink controls, and canonical path checks.
4. Store the original display name **as untrusted metadata**, and escape it when rendering into HTML or headers.
5. Use `Content-Disposition: attachment` as appropriate when downloading documents that should not render inline; combine with `X-Content-Type-Options: nosniff` and a valid MIME type.

### 11.2. Multi-Layer Upload Validation

- **Size:** enforce limits at proxy/container before the controller, plus per-user/tenant quotas.
- **File type:** client-declared extension + MIME are only hints; check magic bytes/parsers for the true type and block unwanted formats.
- **Malicious content:** antivirus/scanner and sandboxing when appropriate; for images, consider decoding and re-encoding to strip unwanted payloads.
- **Archives:** guard against zip bombs, path traversal in archive entries, and CPU/memory exhaustion.
- **Access control:** authenticate and authorize upload/download operations, and verify ownership.
- **CSRF:** if browser authentication relies on cookies, state-changing POST uploads need proper CSRF protection.
- **Storage:** dedicated directory/volume with quotas, server-side names, backup/lifecycle, and cleanup.
- **Error messages:** never expose absolute paths, storage credentials, or stack traces in error JSON.

Successfully decoding the request body **does not** mean the file is safe to save or open. That belongs to the business/security layer above `MultipartResolver`.

## 12. Common Errors and Diagnosis

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Controller receives null/missing file | Part name differs from `@RequestParam("file")`, missing part, wrong Content-Type/boundary | Compare `name`, `curl -F`, actual request headers |
| Multipart parse error before controller | Container multipart not enabled or malformed body/part | Inspect servlet multipart config, logs, root cause |
| `MaxUploadSizeExceededException` or 413 | Exceeded `max-file-size`, `max-request-size`, or proxy limit | Compare file size and total body against the rejecting layer |
| Small files still exceed `max-request-size` | Multiple parts or overhead; total exceeds limit | Measure entire request, not just the largest file |
| `@RequestPart` JSON returns 415 | `metadata` part lacks `Content-Type: application/json` or missing converter | Use `curl -F 'metadata=...;type=application/json'` |
| Multipart passes controller but file is gone after request | File was in temp storage and got cleaned up | Copy/transfer before the request ends |
| Upload succeeds on Tomcat but fails on Jetty | Multipart subtype/HTTP method parsed differently by containers | Consider `strict-servlet-compliance=true`, test container |
| Added resolver bean but still not parsing | Missing `MultipartConfigElement` on servlet registration | Configure both layers, verify at startup |
| `setMaxUploadSize` fails to compile | Legacy `CommonsMultipartResolver` API | Use Servlet/Boot multipart properties |
| `@RequestBody` DTO fails to read entire multipart | `@RequestBody` is for a single-format body; JSON is a part | Use `@RequestPart` for the JSON part |
| `MockMvc` allows files above size limit | Mocked multipart bypasses container parser | Test with real HTTP on an embedded server |
| Disk full or permission denied | Temp upload location not writable / volume lacks quota | Check server OS user, mounts, and cleanup |
| 400/413/415 inconsistent across environments | Proxy/container/exception handlers differ | Inspect HTTP + logs at each layer |
| Filename has `../` or absolute path | Client controls `getOriginalFilename()` | Generate server-side storage key and validate |
| `multipartResolver` not found | Wrong bean name or different context from `DispatcherServlet` | Verify exact bean name and context |

### Practical Debugging Workflow

1. Verify the **client** sends `multipart/form-data; boundary=...` and the body actually contains parts with the expected names.
2. Verify the **Servlet registration** has multipart enabled, file/request limits set, and a writable temp location.
3. For plain Spring MVC, verify the **`multipartResolver`** bean; for Boot, check auto-config and `spring.servlet.multipart.enabled`.
4. Check `resolve-lazily` (controls when parsing happens); `strict-servlet-compliance` and the container (control media subtypes).
5. Read the root exception at the **proxy/container** and Spring; do not assume every error comes from the controller.
6. Check `@RequestParam`, `@RequestPart`, the JSON part's media type, validation, and file handling.
7. Test with real HTTP using large files, multiple files, and malformed form requests; do not draw limit conclusions from MockMvc.
8. Ensure data is persisted to managed storage if the application needs to keep it; never rely on the temp directory.

## 13. Review Questions

**1. Does `StandardServletMultipartResolver` replace the Servlet container's multipart parser?**

No. It uses the container's `jakarta.servlet.http.Part`/`request.getParts()`. The container must be configured to parse multipart requests.

**2. Why must the resolver bean be named `multipartResolver` in plain Spring MVC?**

Because `DispatcherServlet` looks up the resolver by that conventional bean name. A bean with a different name may not be picked up automatically as the multipart strategy.

**3. What is the right way to enforce a 2 MiB per-file limit in Spring Boot 3.x?**

Set `spring.servlet.multipart.max-file-size=2MB`; the limit is applied to the Servlet multipart configuration. Do not call `setMaxUploadSize` on `StandardServletMultipartResolver` (it does not exist).

**4. Does `resolve-lazily=true` fix oversized upload errors?**

No. It changes when parsing/errors occur, without increasing or removing the container's size limits.

**5. Which media types does `strict-servlet-compliance=true` handle?**

The resolver only wraps multipart form uploads with `multipart/form-data`. Other multipart subtypes are not wrapped by this Spring resolver, which is convenient if the application handles them separately.

**6. Why does MockMvc not prove the Servlet container's size limits?**

Because MockMvc typically supplies pre-built multipart objects without passing through a real HTTP connector/parser. Testing size limits requires a real server and real HTTP multipart requests.

**7. Why must `getOriginalFilename()` never be used directly as a storage path?**

Because the client controls that value; it can cause path traversal, overwrites, invalid filenames, or spoofed extensions. Generate a server-side storage key and validate the actual file type.

## 14. Pre-Deployment Checklist

- Distinguish **Spring MVC's** resolver from the **Servlet container's** parser/limits; configure both layers when not using Spring Boot auto-config.
- On Boot 3.x, prefer `spring.servlet.multipart.*` and only declare a custom bean if there is a clear need.
- Configure `max-file-size`, `max-request-size`, temp `location`, and `file-size-threshold` according to real resources, plus quotas/proxy limits.
- Choose `resolve-lazily` based on desired error-handling point, and `strict-servlet-compliance` based on portability and media subtype requirements.
- Use `@RequestParam MultipartFile` for file/form fields and `@RequestPart` for JSON parts with the appropriate content type.
- Never manually set the multipart Content-Type header when using `curl -F` or browser `FormData`.
- Validate empty files, size, actual type, filename, malicious content, upload permissions, and storage paths.
- Persist files durably before the request finishes if required by business logic; manage temp disk space and cleanup.
- Test both controller logic and real HTTP through the container/proxy, especially oversized uploads and malformed multipart requests.
- Do not use `CommonsMultipartResolver`/Javax Servlet examples from Spring 5 to configure Spring 6/Jakarta.

## Official References

- [Spring Framework 6.2 — Multipart Resolver](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework 6.2 — Multipart Forms](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — StandardServletMultipartResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/multipart/support/StandardServletMultipartResolver.html)
- [Spring Framework — MultipartResolver interface](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/multipart/MultipartResolver.html)
- [Spring Boot 3.5 — MultipartProperties Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Framework 6.0 — Release Notes (CommonsMultipartResolver removed)](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
