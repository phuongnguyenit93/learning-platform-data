# @RequestPart and Multipart Parameters in Spring MVC

## Objectives

After this lesson, you will be able to explain what parts make up `multipart/form-data`, when to use `@RequestPart` instead of `@RequestParam` or `@ModelAttribute`, receive files and JSON metadata in the same HTTP request, declare required/optional parts, handle multiple files, validate inputs, configure size limits, and test uploads with MockMvc.

This lesson focuses on **Spring MVC running on the Servlet stack**, using **Java 17+**, **Spring Boot 3.x**, and `jakarta.servlet`. Spring WebFlux has the `FilePart` type and its own reactive mechanism; do not replace `MultipartFile` in the MVC examples below with `FilePart`.

## 1. What is a multipart request?

A request with a `multipart/form-data` body consists of multiple **parts**. Each part has its own headers (such as `Content-Disposition`, `Content-Type`) and its own payload data. The *request*'s `Content-Type` header contains a `boundary` so the server can identify boundaries between parts.

Simplified example (the boundary string is illustrative only):

~~~http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=BoundaryDemo

--BoundaryDemo
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Spring MVC","category":"notes"}
--BoundaryDemo
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

Hello Spring!
--BoundaryDemo
Content-Disposition: form-data; name="comment"
Content-Type: text/plain

first upload
--BoundaryDemo--
~~~

In this request, `metadata`, `file`, and `comment` are **part names**. A part can hold a string, JSON, a binary file, or other content. `filename` is metadata sent by the client, not a trusted path for writing files.

On the Spring MVC server side, multipart requests are processed by the Servlet container and the `MultipartResolver` mechanism so the controller can access individual parts. Spring Boot typically auto-configures multipart support when Spring MVC is present; if you configure Spring MVC/Servlet manually, you may need to declare a `MultipartResolver` and Servlet multipart configuration.

**Note:** Do not manually set the request header `Content-Type: multipart/form-data` without a `boundary`. Let `curl -F`, browser `FormData`, or an HTTP client generate matching boundaries and bodies.

## 2. What does `@RequestPart` read and how does binding work?

An endpoint can declare:

~~~java
@PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String upload(
        @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return metadata.title() + ": " + file.getSize();
}
~~~

This is an illustrative snippet inside a controller; `DocumentMetadata` needs to be defined separately.

- `@RequestPart("metadata")` locates the part with **name = metadata** and uses an `HttpMessageConverter` matching **that part's** `Content-Type` to convert the body into `DocumentMetadata` (e.g., JSON via Jackson).
- `@RequestPart("file") MultipartFile` retrieves the uploaded data as a Spring `MultipartFile` object, providing `getInputStream()`, `getSize()`, `getContentType()`, `getOriginalFilename()`, `isEmpty()`, and `transferTo(...)`.
- You can also accept `jakarta.servlet.http.Part` with Servlet multipart parsing when Servlet APIs and part headers are needed.
- `name` and `value` are two ways to specify the part name; `@RequestPart("metadata")` is shorthand for `@RequestPart(name = "metadata")`.
- `required = true` is the default; a missing required part typically causes **400 Bad Request** (`MissingServletRequestPartException`). `required = false` allows the part to be absent, making a reference parameter `null`; `Optional<T>` can be used per Spring's binding support.
- **There is no `defaultValue` attribute on `@RequestPart`**. If you want a fallback, handle it after binding or use an appropriate input mechanism.

`@RequestPart` is very close to `@RequestBody` in **converting payloads via message converters**, except `@RequestBody` targets the entire request body, whereas `@RequestPart` targets **a specific part** inside a multipart body. Each part's `Content-Type` header matters: JSON metadata should specify `application/json`; sending JSON as `text/plain` is not guaranteed to bind to a JSON DTO.

## 3. Comparing `@RequestPart`, `@RequestParam`, `@ModelAttribute`, and `@RequestBody`

| Scenario | Common choice | Reason |
| --- | --- | --- |
| Upload form with a string `description` field and a file | `@RequestParam String description`, `@RequestParam MultipartFile file` | Simple form parameter binding; Spring MVC supports multipart files with `@RequestParam` |
| Uploading a file alongside a `metadata` part carrying JSON | `@RequestPart UploadMetadata metadata`, `@RequestPart MultipartFile file` | JSON part is deserialized via `HttpMessageConverter` |
| Multi-field HTML form bound into an object | `@ModelAttribute UploadForm form` (with a `MultipartFile` field) | Data binding from form fields into object properties |
| Pure JSON request body, no multipart | `@RequestBody UploadMetadata metadata` | Converts the single body of the HTTP request |
| Low-level Servlet API needed | `@RequestPart Part part` or `HttpServletRequest` | Works directly with `Part` and Servlet API metadata |

Both `@RequestParam MultipartFile` and `@RequestPart MultipartFile` can receive files. **The sharpest difference is with a JSON object inside a part:** `@RequestPart` reads the payload according to the part's media type to apply a converter; `@RequestParam` is geared toward request parameters and form-data type conversion.

Do not send JSON in a part and assume `@ModelAttribute` will automatically decode that JSON like a `@RequestPart` DTO. Conversely, if the frontend sends regular `title` and `category` fields, an `@ModelAttribute` DTO may be more suitable than assembling them into JSON.

## 4. Runnable Spring Boot 3.x example: JSON metadata + single file

Create a Maven project via Spring Initializr, choosing **Java 17 or higher**, **Spring Boot 3.x**, and the **Spring Web** and **Validation** dependencies; if you want to run the tests below, add **Spring Boot Starter Test**. `spring-boot-starter-web` provides Spring MVC, Tomcat, and JSON support; `spring-boot-starter-validation` provides Jakarta Bean Validation.

Minimal structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/UploadController.java
src/main/resources/application.properties
src/test/java/com/example/demo/UploadControllerTest.java
~~~

**`src/main/java/com/example/demo/DemoApplication.java`**

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

**`src/main/java/com/example/demo/UploadController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadResult> create(
            @Valid @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") MultipartFile file,
            @RequestPart(name = "comment", required = false) String comment) {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "File must not be empty");
        }

        UploadResult result = new UploadResult(
                metadata.title(),
                metadata.category(),
                comment,
                file.getSize(),
                file.getContentType());

        // Only report receipt success; the example does not save the file to disk.
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(path = "/many",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Long> many(
            @RequestPart("files") List<MultipartFile> files) {

        if (files.isEmpty() || files.stream().anyMatch(MultipartFile::isEmpty)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Files must not be empty");
        }

        return Map.of(
                "count", (long) files.size(),
                "totalBytes",
                files.stream().mapToLong(MultipartFile::getSize).sum());
    }

    public record UploadMetadata(
            @NotBlank String title,
            @NotBlank String category) {
    }

    public record UploadResult(
            String title,
            String category,
            String comment,
            long bytes,
            String mediaType) {
    }
}
~~~

Points to note:

1. `consumes = MediaType.MULTIPART_FORM_DATA_VALUE` declares that the endpoint handles `multipart/form-data` requests; plain JSON requests do not match this media type.
2. The `metadata` part must contain JSON matching the `UploadMetadata` record. The `@Valid` annotation enforces `@NotBlank`; invalid metadata typically returns **400**.
3. `file` is a required part in terms of presence. However, an empty file part **can still exist**, so check `file.isEmpty()` separately.
4. `comment` is an optional part; an absent part can yield `null`. If the application wants `""`, normalize it in business logic.
5. The returned result only demonstrates **binding/validation and metadata**; the file **has not been saved**. For a real file-saving API, you need a storage service, authorization checks, and file security policies.
6. `mediaType` from `file.getContentType()` is client-declared metadata and may be `null` or inaccurate; do not rely on it as proof of file type.

**`src/main/resources/application.properties`** (illustrative limits)

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=10MB
~~~

The `max-file-size` limit applies per file; `max-request-size` applies to the entire multipart request, including part payloads and overhead. Spring Boot typically enables multipart by default. Common defaults when unconfigured are **1MB/file and 10MB/request**, though you should verify against your version and deployment config.

In the project directory, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run`; if there is no Maven Wrapper, use `mvn spring-boot:run` once Maven is installed.

Create a sample file `note.txt` containing `Hello Spring!` in a way appropriate for your OS, then send the request:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads" \
  -F 'metadata={"title":"Spring MVC","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=text/plain' \
  -F 'comment=first upload'
~~~

The command above uses shell syntax supporting `\` line continuations (Linux/macOS/Git Bash). On PowerShell, run `curl.exe` on a single line or using PowerShell's line-continuation syntax; quoting and escaping inside `-F` must also match the shell. In particular, `;type=application/json` attaches the media type to the **metadata part**, not to the entire request.

A successful response has HTTP status **201 Created**. Illustrative body, assuming a UTF-8 file of exactly 13 bytes (the string `Hello Spring!` with no newline):

~~~json
{
  "title": "Spring MVC",
  "category": "notes",
  "comment": "first upload",
  "bytes": 13,
  "mediaType": "text/plain"
}
~~~

If the created file has a newline or different content, `bytes` will change; JSON property order has no significance. When `comment` is omitted, default Jackson configuration typically represents `comment: null`.

## 5. Connecting a frontend with `FormData`

When using a browser, `FormData` constructs the multipart body. Example in a frontend where `fileInput` points to an `<input type="file">`:

~~~javascript
const file = fileInput.files[0];

const form = new FormData();
form.append("metadata", new Blob(
  [JSON.stringify({ title: "Spring MVC", category: "notes" })],
  { type: "application/json" }
));
form.append("file", file);
form.append("comment", "first upload");

const response = await fetch("/api/uploads", {
  method: "POST",
  body: form
});

if (!response.ok) {
  throw new Error("Upload failed: HTTP " + response.status);
}
console.log(await response.json());
~~~

Using a `Blob` with `type: "application/json"` ensures Spring sees the metadata part as JSON and can select the converter. If you only use `form.append("metadata", JSON.stringify(object))`, the browser sends a **text field**, usually lacking an appropriate JSON media type and potentially causing DTO conversion errors.

**Do not manually declare** the request `Content-Type` when using `fetch` with `FormData`; the browser automatically sets the multipart boundary. When frontend and backend are on different origins, consider CORS, credentials/cookie configuration, and CSRF per Spring Security; frontend handling does not replace server-side security policies.

## 6. Single file, multiple files, and Servlet `Part`

For a single file, common parameter types are:

~~~java
@RequestPart("file") MultipartFile file
@RequestParam("file") MultipartFile file
@RequestPart("file") jakarta.servlet.http.Part file
~~~

These are **parameter declarations**, used inside an appropriate handler method. `MultipartFile` is Spring's abstraction; `Part` is the Servlet API, offering `getInputStream()`, `getSize()`, `getSubmittedFileName()`, and `getHeader(...)`. Do not use `org.springframework.http.codec.multipart.FilePart` in Spring MVC: that is the abstraction for WebFlux.

If a part name appears multiple times, you can receive multiple files via `List<MultipartFile>` or `MultipartFile[]`. Example using the `/api/uploads/many` endpoint above:

~~~bash
curl -i -X POST "http://localhost:8080/api/uploads/many" \
  -F 'files=@first.txt' \
  -F 'files=@second.txt'
~~~

Both parts use **name = files**. The response body contains `count = 2` and the total byte size of both files. Do not confuse this with two parts named `file1` and `file2`, as they **do not automatically** bind to the same `files` parameter.

To receive files with different part names, you can use `@RequestParam MultiValueMap<String, MultipartFile>` or `Map<String, MultipartFile>` without specifying a parameter name (distinction: a regular map keeps only one value per name, while a multivalue map keeps a list). Only use this when the API genuinely allows dynamic part names; for APIs with fixed names, explicit parameters are easier to control.

**Do not treat `file.getSize() > 0` as proof of a valid file.** A file can be non-empty while its content, filename, encoding, or format is still dangerous or invalid for business rules.

## 7. Handling missing parts, wrong formats, or oversized requests

| Scenario | Common cause | Response/result |
| --- | --- | --- |
| Missing required `metadata` or `file` | Wrong field name or client did not send part | Typically **400**, `MissingServletRequestPartException` |
| Missing `comment` | Declared `required=false` | Controller receives `null` |
| `metadata` is not valid JSON | `HttpMessageConverter` fails to read JSON | Typically **400** with unreadable body error |
| Syntactically valid JSON failing `@NotBlank` | Jakarta Bean Validation on `@Valid @RequestPart` | Typically **400**, `MethodArgumentNotValidException` |
| JSON metadata sent with `Content-Type: text/plain` | No matching converter for the DTO | Typically **415 Unsupported Media Type** |
| Request uses `application/json` instead of `multipart/form-data` | Does not match handler's `consumes` | Typically **415 Unsupported Media Type** |
| Empty file part | Part exists but has zero bytes | Example controller explicitly returns **400** |
| File or entire request exceeds limit | Multipart parser/container rejects it | Upload/size error; **413 Content Too Large** is the appropriate status when configured/mapped |
| Multipart request has malformed boundary | Parser cannot split parts | Multipart parse error; status depends on container and error handler config |

The statuses in the table represent **typical behavior**, not a guarantee of specific error bodies across all Spring Boot, Servlet container, reverse proxy, or custom exception handler configurations. For oversized uploads, `MaxUploadSizeExceededException` can occur; HTTP 413 depends on how the stack handles and maps the exception. Server/proxy configuration (such as body size limits) may reject the request before it reaches the controller.

If you want to standardize error bodies for the API, use `@RestControllerAdvice` and map the exact exceptions needed. Avoid catching generic `Exception` everywhere and converting it into 200 or 400, as that masks server errors. For multipart validation, you can place `BindingResult` immediately after a `@Valid @RequestPart` DTO parameter if you genuinely need to handle validation errors inside the handler, but that branch must be carefully designed and tested.

## 8. Testing `@RequestPart` with MockMvc

Requires `spring-boot-starter-test`. Add **`src/test/java/com/example/demo/UploadControllerTest.java`**:

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

    private static MockMultipartFile metadata(String json, String contentType) {
        return new MockMultipartFile(
                "metadata",
                "",
                contentType,
                json.getBytes(StandardCharsets.UTF_8));
    }

    private static MockMultipartFile file() {
        return new MockMultipartFile(
                "file",
                "note.txt",
                "text/plain",
                "Hello".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void uploadsValidJsonAndFile() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata(
                                "{\"title\":\"Spring MVC\",\"category\":\"notes\"}",
                                "application/json"))
                        .file(file())
                        .file(new MockMultipartFile(
                                "comment",
                                "",
                                "text/plain",
                                "first upload".getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Spring MVC"))
                .andExpect(jsonPath("$.category").value("notes"))
                .andExpect(jsonPath("$.comment").value("first upload"))
                .andExpect(jsonPath("$.bytes").value(5));
    }

    @Test
    void missingRequiredFileReturnsBadRequest() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata(
                                "{\"title\":\"Spring MVC\",\"category\":\"notes\"}",
                                "application/json")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidJsonMetadataReturnsBadRequest() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata("{invalid-json", "application/json"))
                        .file(file()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void beanValidationRejectsBlankTitle() throws Exception {
        mockMvc.perform(multipart("/api/uploads")
                        .file(metadata(
                                "{\"title\":\"\",\"category\":\"notes\"}",
                                "application/json"))
                        .file(file()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsTwoFilesWithSamePartName() throws Exception {
        MockMultipartFile one = new MockMultipartFile(
                "files", "a.txt", "text/plain", new byte[] {1, 2});
        MockMultipartFile two = new MockMultipartFile(
                "files", "b.txt", "text/plain", new byte[] {3});

        mockMvc.perform(multipart("/api/uploads/many")
                        .file(one).file(two))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2))
                .andExpect(jsonPath("$.totalBytes").value(3));
    }
}
~~~

Run tests:

~~~bash
./mvnw test
~~~

Notice that `MockMultipartFile`'s first argument is the part name: `"metadata"`, `"file"`, and `"comment"` must **match the annotation names exactly**. `MockMultipartFile("metadata", "", "application/json", ...)` ensures the JSON part is read by the matching converter. In the multi-file test, both files must share the name `"files"`.

**MockMvc limitations:** tests primarily verify argument resolution, conversion, validation, and controller logic. Real Servlet container upload handling, temporary storage, reverse-proxy body limits, and oversized upload errors should also be integration-tested with a real server.

## 9. Storing files safely in production applications

The example above intentionally **does not save** files. When implementing storage, pay attention to:

1. **Never concatenate `getOriginalFilename()` directly into a destination path.** The original filename is client-controlled and may be empty, contain path separators, or include `../` sequences. Generate an independent storage name (e.g., UUID), use an explicitly configured directory, and enforce permissions.
2. **Enforce size limits at multiple layers.** Configure `spring.servlet.multipart.max-file-size` and `spring.servlet.multipart.max-request-size` appropriately, and align them with Servlet container/reverse proxy limits. When processing images/videos or multiple files, design appropriate timeouts and quotas.
3. **Do not trust client-declared MIME types or extensions alone.** Verify content type from actual bytes (magic bytes/appropriate parsers), whitelist allowed formats, consider malware scanning when needed, and bound extraction operations on archives.
4. **Do not treat temporary files as long-term storage.** `MultipartFile` may be buffered in memory or on disk and normally has a request-scoped lifecycle. When persistence is needed, read the stream/copy to managed storage during request processing and enforce resource cleanup policies.
5. **Do not call `getBytes()` on large files just to copy them.** Consider `getInputStream()` and bounded streaming/copying to reduce memory pressure; handle resources and I/O exceptions properly.
6. **Protect the endpoint.** Enforce authentication, authorization, quotas, safe metadata logging, and CSRF checks in browser contexts; never let clients dictate arbitrary storage paths or file ownership.
7. **Serve downloads safely.** When serving user-uploaded files, configure appropriate content types, `Content-Disposition`, and browser security headers to reduce risks of active content execution.
8. **Do not treat multipart uploads as atomic transactions.** If saving a file succeeds and writing to the database fails (or vice versa), implement rollback/cleanup/compensation strategies to avoid orphaned files.

You can write to disk via `transferTo(...)`, but that method does not replace path sanitization and validation. If using cloud object storage, design limits/streaming to fit the SDK and enforce bucket access controls.

## 10. Common errors and self-diagnosis

- **`MissingServletRequestPartException`:** double-check the exact name in `-F "metadata=..."` or `form.append("metadata", ...)` against `@RequestPart("metadata")`; verify the request is properly multipart with a boundary.
- **415 error when metadata is already JSON:** inspect the `Content-Type` **of the metadata part itself** in the Network tab or HTTP client; use `application/json`.
- **DTO is null or not bound as expected:** compare JSON property names against the record/POJO, Jackson config, and constructor/binding; distinguish sending a JSON part from multiple text fields.
- **Sending multipart from frontend but server does not receive it:** do not manually set the overall request `Content-Type` when using `FormData`; check CORS/credentials and proxy limits.
- **Empty file:** check whether the client selected a file, `MultipartFile.isEmpty()`, and whether a 0-byte file is valid under business rules.
- **400 error even though all parts are present:** malformed JSON, failed validation, or matching part name with incompatible media type/content; inspect exception logs and error responses.
- **Size limit exceeded:** check `max-file-size`, `max-request-size`, and proxy/server limits; do not raise limits indefinitely just to silence errors.
- **Multiple files only receive one:** ensure repeated parts share the exact `files` part name and the handler accepts `List<MultipartFile>` or an appropriate collection type.

## 11. Selection and implementation checklist

1. Verify the request is genuinely `multipart/form-data` and the frontend/client generates a valid boundary.
2. For JSON metadata, use a `@RequestPart` DTO and attach `Content-Type: application/json` to the **part**; for simple text form fields, consider `@RequestParam` or `@ModelAttribute`.
3. For files, use `MultipartFile` or `jakarta.servlet.http.Part`; set exact part names and appropriate `required` settings.
4. Validate JSON data, non-emptiness, and file contents; enforce per-file and per-request limits; never trust client-supplied filenames or MIME types.
5. Test valid requests, missing parts, invalid JSON/validation, multiple files, and size limits in a real runtime environment.

## Official references

- [Spring Framework — Multipart in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html#howto.webserver.configure-multipart-file-uploads)
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
