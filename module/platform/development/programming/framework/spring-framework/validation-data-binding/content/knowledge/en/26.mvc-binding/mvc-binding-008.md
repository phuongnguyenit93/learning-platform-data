# MultipartFile, Multipart Forms, and Missing Fields in Spring MVC

## 1. Goal and real-world scenario

An HTML form submitting a document title and an attachment can look very simple:

```html
<form action="/api/uploads/form"
      method="post"
      enctype="multipart/form-data">
  <label>Title:
    <input type="text" name="title">
  </label>
  <label>File:
    <input type="file" name="file">
  </label>
  <button type="submit">Submit</button>
</form>
```

On the Spring MVC side, however, the following situations are **distinct**:

1. The client does not send the `title` field.
2. The client sends `title` as an empty string `""` or all whitespace.
3. The client does not send the `file` part.
4. The client sends the `file` part without selecting a file or sends a 0-byte file.
5. The client sends a valid file under part name `attachment` instead of `file`.
6. The client sends pure JSON with `Content-Type: application/json` instead of a multipart form.
7. The client sends a JSON metadata part, an uploaded file, and wants Jakarta Validation applied to the metadata.

Lumping all of these into “missing field” easily causes an application to return wrong errors, handle `null` unsafely, or accept an empty file when business rules require non-empty content.

**Lesson objectives:** understand `multipart/form-data` and `MultipartFile`, choose appropriately between `@RequestParam`, `@RequestPart`, and `@ModelAttribute`, distinguish **missing**, **present-but-empty**, and **invalid**, use `BindingResult`/`@Valid`, and test each branch accurately with Spring MVC `MockMvc`.

The primary scope is the **Spring MVC Servlet stack** (Spring Framework 6.x and Spring Boot 3.x with Java 17+). Spring WebFlux uses different APIs such as `FilePart`; do not copy `MultipartFile` examples verbatim into reactive endpoints.

## 2. What is HTTP `multipart/form-data` actually?

A request has a header similar to:

```http
POST /api/uploads/required HTTP/1.1
Content-Type: multipart/form-data; boundary=example-boundary
```

The body consists of multiple *parts*, each with its own headers and content. Simplified example:

```http
--example-boundary
Content-Disposition: form-data; name="title"

Report
--example-boundary
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain

abc
--example-boundary--
```

Where:
- `title` is a **form field**.
- `file` is a **file part** with form field name `file` and client-declared filename `report.txt`.
- `boundary` allows the parser to identify which section belongs to which field.
- Real content can be binary data; the example above only illustrates structure.

**Part names must match.** If a controller declares `@RequestParam("file")`, a part with `name="attachment"` is not treated as the `file` part.

Browsers and HTTP libraries usually generate boundaries automatically. When using `FormData` in JavaScript or `curl -F`, **do not manually set** `Content-Type: multipart/form-data` without a boundary; let the client generate the complete header.

Unlike `application/x-www-form-urlencoded`, multipart can carry file bytes, multiple parts sharing the same name, or a JSON part marked `Content-Type: application/json` for Spring to read via a message converter.

## 3. Multipart flow in Spring MVC

Conceptually:

```text
HTTP POST multipart/form-data
           |
           v
Servlet container + multipart config
           |
           v
MultipartResolver / Servlet part parsing
           |
           v
DispatcherServlet
           |
       Handler method
    /       |        \
@RequestParam @RequestPart @ModelAttribute
    |         |          |
form/file  part +      WebDataBinder
values     converter   form object + files
           |
         validation if triggered
           |
           v
        Controller
```

Spring MVC uses the `MultipartResolver` strategy; on the modern Servlet stack, `StandardServletMultipartResolver` leverages the Servlet container's multipart parsing capabilities. Spring Boot typically auto-configures multipart support when using `spring-boot-starter-web` with default settings, whereas plain Spring Framework requires setting up a resolver and Servlet multipart configuration explicitly.

When a required part is missing, an error can occur during **argument resolution before the controller is invoked**. Conversely, if a `MultipartFile` is bound with `isEmpty() == true`, the controller still runs and you must check business rules.

Do not confuse three stages:
- **Parsing:** reading and splitting the request by boundary; can fail if malformed or exceeding limits.
- **Binding:** assigning `title` and `file` into method parameters or a DTO.
- **Validation:** checking `@NotBlank`, business rule “non-empty file”, and allowed sizes/formats.

## 4. The `MultipartFile` interface

`MultipartFile` lives in package `org.springframework.web.multipart`. Commonly used methods:

| API | Meaning | Notes |
| --- | --- | --- |
| `getName()` | **Field/part name** in the form, e.g., `file` | Used for matching binding; not the real filename |
| `getOriginalFilename()` | Filename declared by the client | May be `null`/empty; **untrusted** for use directly as a storage path |
| `getContentType()` | Content type supplied by the client, may be `null` | Do not treat as definitive proof of file type |
| `isEmpty()` | `true` if no file was selected or uploaded content is empty | Does not reliably distinguish “no file selected” from “0-byte file” |
| `getSize()` | File size in bytes, type `long` | `0` for empty files |
| `getInputStream()` | Reads content as a stream | Suitable for large files without loading all bytes onto the heap |
| `getBytes()` | Reads all bytes into `byte[]` | Be careful with large files; high memory usage |
| `transferTo(...)` | Moves/copies uploaded file to destination | Control paths, server-generated names, permissions, and I/O errors |

**Especially important:**
- `file == null` means **no `MultipartFile` object was bound** at that parameter/property.
- `file != null && file.isEmpty()` means **an object exists** but its content is considered empty. Depending on the client/browser/Servlet container, leaving a file input unselected may send an empty part or omit the part entirely; do not assume one identical behavior across all clients.
- `file != null && !file.isEmpty()` proves content bytes exist, **not** that the content is safe or valid.

Multipart data often relies on temporary request-scoped resources. If you need the file after the HTTP request finishes, save/copy its content to a controlled location while the request is still active.

## 5. Three ways to receive multipart in a controller

### 5.1. `@RequestParam`: simple form fields and file parts

```java
@PostMapping(path = "/required",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @RequestParam("title") String title,
        @RequestParam("file") MultipartFile file) {
    // ...
}
```

`@RequestParam` fits simple `title`/`file` pairs. With the default `required = true`:
- Missing `title` typically causes a missing request parameter error before entering the method body.
- Missing `file` part typically causes a missing request part error.
- `title=""` can still **bind** but fails `@NotBlank` if validation is enabled or checked manually.
- A `file` part present with 0 bytes can bind as a `MultipartFile` whose `isEmpty()` is `true`. `required=true` mainly requires **part presence**, not a non-zero size check.

Field names in HTML, `curl -F`, or JavaScript `FormData.append(name, ...)` must match `title` and `file` exactly.

### 5.2. `@RequestPart`: files and parts needing conversion

`@RequestPart` can also accept `MultipartFile`, and is especially useful when a JSON part is present:

```java
public record Metadata(@NotBlank String label) {}

@PostMapping(path = "/metadata",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> uploadWithMetadata(
        @Valid @RequestPart("metadata") Metadata metadata,
        @RequestPart("file") MultipartFile file) {
    // ...
}
```

If the `metadata` part has `Content-Type: application/json` and body `{"label":"Report"}`, Spring uses an `HttpMessageConverter` (typically Jackson) to convert the JSON into `Metadata`. `@Valid` triggers Bean Validation on the converted object; malformed JSON or an unsupported content type causes an error **before** entering the controller.

Both `@RequestPart("file") MultipartFile file` and `@RequestParam("file") MultipartFile file` are valid for files. The key difference emerges with **object parts**: `@RequestPart` inspects the *part's* content type to read it with a message converter, whereas `@RequestParam` targets parameters and standard type conversion.

### 5.3. `@ModelAttribute`: binding forms into a DTO

When a form has multiple fields:

```java
public class UploadForm {

    @NotBlank(message = "title.blank")
    private String title;

    private MultipartFile file;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public MultipartFile getFile() { return file; }
    public void setFile(MultipartFile file) { this.file = file; }
}
```

Controller:

```java
@PostMapping(path = "/form",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> form(
        @Valid @ModelAttribute UploadForm form,
        BindingResult errors) {
    // ...
}
```

Spring `WebDataBinder` binds matching form fields/files into the DTO. `@Valid` runs supported constraints, such as `@NotBlank` on `title`. `BindingResult` must sit **immediately after** the validated `@ModelAttribute` argument if you want to handle errors locally.

In a newly bound DTO, if the `file` field is absent from the request, typically `form.getFile() == null`; if an empty part arrives, `form.getFile().isEmpty()` is `true`. Never call `form.getFile().isEmpty()` without checking `null` first.

### 5.4. Choosing the API by payload shape

| Client sends | Suitable declaration | Why |
| --- | --- | --- |
| Text field + one file | `@RequestParam String` + `@RequestParam MultipartFile` | Clear and concise |
| Multi-field form + file + DTO validation | `@Valid @ModelAttribute UploadForm` | `WebDataBinder` populates form object |
| JSON metadata part + file | `@Valid @RequestPart Metadata` + `@RequestPart MultipartFile` | `HttpMessageConverter` reads JSON part |
| Multiple files under one field name | `@RequestParam("files") List<MultipartFile>` | Collects multiple files under the same name |
| Optional upload needed | `required=false` or `Optional<MultipartFile>` per argument resolver | Distinguishes missing part from present-but-empty part |

**Avoid using `@RequestBody UploadForm` to read an entire `multipart/form-data` request as if it were pure JSON.** `@RequestBody` reads the request body via message converters; for multipart, choose `@RequestPart` for JSON parts or `@ModelAttribute` for form fields.

## 6. Missing fields, empty fields, and 0-byte files

### 6.1. State comparison table

| Input data | `@RequestParam(required=true)` / `@RequestPart(required=true)` | `required=false` / new DTO |
| --- | --- | --- |
| `title` field omitted | Usually returns **400** due to missing request parameter | `String` may be `null`; `@NotBlank` on DTO catches it if `@Valid` is used |
| `title=""` sent | Argument usually binds; check blank/validation manually | Empty string may still bind |
| `title="   "` sent | Parameter is present; `@NotBlank` rejects whitespace-only | `isBlank()`/`@NotBlank` rejects it |
| No `file` part | Usually **400** due to missing request part | `MultipartFile` may be `null` |
| `file` part present, 0 bytes | Can bind; `file.isEmpty() == true` | Object exists but `isEmpty() == true` |
| Only `attachment` sent when controller expects `file` | Equivalent to **missing `file` part** | `file` is not bound |
| `file` part sent with content | `MultipartFile` object exists, `isEmpty() == false` | Same |

This table describes the typical Spring MVC Servlet flow; how clients encode an unselected HTML file input can vary across clients. Distinguish **missing part** from **empty part** using real requests and tests, not HTML assumptions alone.

### 6.2. `required=false` only drops the presence requirement

```java
@PostMapping(path = "/optional",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Map<String, String> optional(
        @RequestParam(name = "title", required = false) String title,
        @RequestPart(name = "file", required = false) MultipartFile file) {

    String titleState =
            title == null ? "missing"
            : title.isBlank() ? "blank" : "present";

    String fileState =
            file == null ? "missing"
            : file.isEmpty() ? "empty" : "present";

    return Map.of("titleState", titleState, "fileState", fileState);
}
```

This is an **illustrative snippet** of a handler, not a full application. When using `required=false`, the controller decides which parts are required by business logic and can return distinct errors for each state. If empty files must be rejected, check `isEmpty()` whether `required=true` or `required=false`.

In HTML forms, a **named-but-empty** text field differs from a **nonexistent** field. For example:
- `<input name="title" value="">` may submit `title=""`.
- Having no control submitting `title` means no `title` parameter exists.
- An unselected file input may be sent as a part with an empty filename and 0 bytes, or omitted, depending on the client.

### 6.3. Business checks for files

An explicit approach:

```java
if (file == null) {
    // File part was not bound.
    return ResponseEntity.badRequest()
            .body(Map.of("error", "file.missing"));
}
if (file.isEmpty()) {
    // File part is present but has no content.
    return ResponseEntity.badRequest()
            .body(Map.of("error", "file.empty"));
}
```

This is a fragment inside a controller with `file` and Spring/Java collection imports. With `@RequestParam(required=true)`, the `file == null` branch is normally never reached inside the controller because Spring rejects the missing part beforehand; this branch is useful with optional binding or DTOs.

**Do not use `@NotBlank MultipartFile file`:** `@NotBlank` is for `CharSequence` and has no standard validator for `MultipartFile`. `@NotNull` checks only for null, not 0-byte files. Annotations like `@NotEmpty` do not automatically validate `MultipartFile` unless a provider has a matching validator. To enforce “a real file with bytes”, check `isEmpty()` or write a custom constraint validator for `MultipartFile`.

## 7. Runnable Spring Boot 3.5.6 + Java 17 example

This small project has four endpoints:
- `POST /api/uploads/required`: required field and file; checks blank strings and empty files.
- `POST /api/uploads/optional`: returns missing/empty/present states.
- `POST /api/uploads/form`: binds into a DTO via `@ModelAttribute` and handles `BindingResult`.
- `POST /api/uploads/metadata`: JSON part (with `@Valid`) and file part.

The app **does not save uploaded data to disk**; it only validates and returns the byte count. When saving real files, add rules for file types, size limits, storage paths, permissions, and content scanning.

Structure:

```text
multipart-demo/
├── pom.xml
├── src/main/java/demo/upload/
│   ├── UploadApplication.java
│   ├── UploadForm.java
│   └── UploadController.java
└── src/test/java/demo/upload/
    └── UploadControllerTest.java
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>multipart-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

Include the validation starter so `@Valid`/`@NotBlank` are actually processed by a provider. `spring-boot-starter-web` brings in Spring MVC and the embedded Servlet container.

### 7.2. `UploadApplication.java`

```java
package demo.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {

    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
```

### 7.3. `UploadForm.java`

```java
package demo.upload;

import jakarta.validation.constraints.NotBlank;
import org.springframework.web.multipart.MultipartFile;

public class UploadForm {

    @NotBlank(message = "title.blank")
    private String title;

    private MultipartFile file;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public MultipartFile getFile() {
        return file;
    }

    public void setFile(MultipartFile file) {
        this.file = file;
    }
}
```

Do not put `@NotBlank` on `file`: it is not a string. The program intentionally distinguishes null from empty in the controller.

### 7.4. `UploadController.java`

```java
package demo.upload;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    public record Metadata(@NotBlank String label) {}

    @PostMapping(
        path = "/required",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> required(
            @RequestParam("title") String title,
            @RequestParam("file") MultipartFile file) {

        if (title.isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "title.blank"));
        }
        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.empty"));
        }

        return ResponseEntity.ok(
                Map.of("title", title, "bytes", file.getSize()));
    }

    @PostMapping(
        path = "/optional",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Map<String, String> optional(
            @RequestParam(name = "title", required = false)
            String title,
            @RequestPart(name = "file", required = false)
            MultipartFile file) {

        String titleState = title == null
                ? "missing"
                : title.isBlank() ? "blank" : "present";

        String fileState = file == null
                ? "missing"
                : file.isEmpty() ? "empty" : "present";

        return Map.of(
                "titleState", titleState,
                "fileState", fileState);
    }

    @PostMapping(
        path = "/form",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> form(
            @Valid @ModelAttribute UploadForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "title.blank"));
        }

        if (form.getFile() == null) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.missing"));
        }

        if (form.getFile().isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.empty"));
        }

        return ResponseEntity.ok(Map.of(
                "title", form.getTitle(),
                "bytes", form.getFile().getSize()));
    }

    @PostMapping(
        path = "/metadata",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> metadata(
            @Valid @RequestPart("metadata") Metadata metadata,
            @RequestPart("file") MultipartFile file) {

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "file.empty"));
        }

        return ResponseEntity.ok(Map.of(
                "label", metadata.label(),
                "bytes", file.getSize()));
    }
}
```

**Important explanations:**
- In `required()`, Spring handles **missing** part/parameter errors before invoking the handler. The `isBlank()` and `isEmpty()` branches handle data that is **present but fails business rules**.
- In `optional()`, the handler runs even when `file` is missing; it returns `missing` if `file == null` and `empty` if the part has 0 bytes.
- `form()` shows how `WebDataBinder` populates the DTO. `BindingResult` sits **immediately after** `@ModelAttribute`. Because the example only puts `@NotBlank` on `title`, the code returns `title.blank` when binding/validation fails. Real projects should iterate `FieldError`s to return each field's exact error code.
- `metadata()` uses a message converter to parse the JSON part into `Metadata` and `@Valid` checks `label`. Do not send the metadata part as `text/plain` if you expect it to parse as JSON.
- None of the endpoints save files or trust `getOriginalFilename()` as a valid path.

## 8. Testing all cases with MockMvc

`MockMvc` simulates requests passing through Spring MVC without binding a server to a network port. Use `MockMultipartFile` to control precisely **whether a part is present or absent**, and whether its payload size is 0 or positive.

### 8.1. `UploadControllerTest.java`

```java
package demo.upload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadControllerTest {

    @Autowired
    private MockMvc mvc;

    private static MockMultipartFile validFile() {
        return new MockMultipartFile(
                "file", "report.txt", "text/plain",
                "abc".getBytes(StandardCharsets.UTF_8));
    }

    private static MockMultipartFile emptyFile() {
        return new MockMultipartFile(
                "file", "empty.txt", "text/plain", new byte[0]);
    }

    @Test
    void requiredWithFileAndTitleSucceeds() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .file(validFile())
                        .param("title", "Report"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Report"))
                .andExpect(jsonPath("$.bytes").value(3));
    }

    @Test
    void missingRequiredFileIsBadRequest() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .param("title", "Report"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredTitleIsBadRequest() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .file(validFile()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void emptyRequiredFileReachesBusinessCheck() throws Exception {
        mvc.perform(multipart("/api/uploads/required")
                        .file(emptyFile())
                        .param("title", "Report"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("file.empty"));
    }

    @Test
    void optionalMissingFileAndTitleAreVisible() throws Exception {
        mvc.perform(multipart("/api/uploads/optional"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.titleState").value("missing"))
                .andExpect(jsonPath("$.fileState").value("missing"));
    }

    @Test
    void optionalEmptyFileIsDifferentFromMissing() throws Exception {
        mvc.perform(multipart("/api/uploads/optional")
                        .file(emptyFile())
                        .param("title", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.titleState").value("blank"))
                .andExpect(jsonPath("$.fileState").value("empty"));
    }

    @Test
    void modelAttributeRejectsBlankTitle() throws Exception {
        mvc.perform(multipart("/api/uploads/form")
                        .file(validFile())
                        .param("title", "   "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("title.blank"));
    }

    @Test
    void modelAttributeDetectsMissingFile() throws Exception {
        mvc.perform(multipart("/api/uploads/form")
                        .param("title", "Report"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("file.missing"));
    }

    @Test
    void modelAttributeAcceptsValidForm() throws Exception {
        mvc.perform(multipart("/api/uploads/form")
                        .file(validFile())
                        .param("title", "Report"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bytes").value(3));
    }

    @Test
    void jsonMetadataPartIsDeserializedAndValidated()
            throws Exception {

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", "application/json",
                "{\"label\":\"Report\"}"
                        .getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/uploads/metadata")
                        .file(metadata)
                        .file(validFile()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.label").value("Report"))
                .andExpect(jsonPath("$.bytes").value(3));
    }

    @Test
    void missingMetadataPartIsBadRequest() throws Exception {
        mvc.perform(multipart("/api/uploads/metadata")
                        .file(validFile()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void blankJsonMetadataLabelIsBadRequest()
            throws Exception {

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", "application/json",
                "{\"label\":\"\"}"
                        .getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/uploads/metadata")
                        .file(metadata)
                        .file(validFile()))
                .andExpect(status().isBadRequest());
    }
}
```

Run in the `multipart-demo` directory:

```bash
mvn test
```

**Expected:** all 12 test cases pass their defined HTTP status/JSON assertions. Exact Maven output can depend on the environment; do not assume log order. In this example, `missingRequiredFileIsBadRequest` and `emptyRequiredFileReachesBusinessCheck` **share status 400** for different reasons:
- A missing part is blocked by Spring MVC while resolving the required argument.
- An existing-but-empty part reaches the controller and returns business error `file.empty`.

By testing each branch, we avoid confusing the two cases even when they share an HTTP status code.

## 9. Testing real requests with curl

Start the application:

```bash
mvn spring-boot:run
```

Prepare a `report.txt` file containing a few characters. The commands below run in Unix/macOS shells; on Windows PowerShell, use `curl.exe` instead of `curl` to avoid the legacy alias.

### 9.1. Sending valid field and file

```bash
curl -i -F 'title=Report' \
  -F 'file=@report.txt;type=text/plain' \
  http://localhost:8080/api/uploads/required
```

Expected HTTP **200 OK** with JSON having `title="Report"` and `bytes` equal to the actual size of `report.txt`. The byte count varies if the file content differs.

### 9.2. Omitting the file part completely

```bash
curl -i -F 'title=Report' \
  http://localhost:8080/api/uploads/required
```

Expected HTTP **400 Bad Request** because `@RequestParam("file")` is required and the request has no part named `file`. The `required()` handler is normally **not invoked**.

Send the same request to the optional endpoint:

```bash
curl -i -F 'title=Report' \
  http://localhost:8080/api/uploads/optional
```

Expected HTTP **200** with `fileState="missing"`. With `@RequestPart(required=false)`, a missing file is not an automatic error.

### 9.3. Sending a 0-byte file

Create an empty `empty.txt` file, then send it:

```bash
curl -i -F 'title=Report' \
  -F 'file=@empty.txt;type=text/plain' \
  http://localhost:8080/api/uploads/required
```

Expected HTTP **400** with JSON `{"error":"file.empty"}`. The part is present, so `MultipartFile.isEmpty()` is `true` and business code rejects it.

### 9.4. Sending JSON metadata along with a file

```bash
curl -i \
  -F 'metadata={"label":"Report"};type=application/json' \
  -F 'file=@report.txt;type=text/plain' \
  http://localhost:8080/api/uploads/metadata
```

Expected HTTP **200** with `label="Report"` and `bytes` equal to the file size. If the `metadata` part is omitted, the request lacks `@RequestPart("metadata")` and normally gets 400. If `label` is an empty string, `@Valid` + `@NotBlank` returns a validation error.

**Do not manually add `Content-Type: multipart/form-data` when using `-F`**: `curl` generates the proper boundary automatically.

## 10. JavaScript FormData and HTML: why missing differs from empty

In a browser:

```javascript
const titleInput = document.querySelector("#title");
const fileInput = document.querySelector("#file");
const data = new FormData();

data.append("title", titleInput.value);

if (fileInput.files.length > 0) {
  data.append("file", fileInput.files[0]);
}

const response = await fetch("/api/uploads/form", {
  method: "POST",
  body: data
});
```

This illustrative snippet assumes the HTML has two inputs with `id="title"`/`id="file"` and runs inside an async function or an environment supporting top-level `await`.

- `data.append("title", titleInput.value)` always adds the `title` form field, even when `value == ""`.
- The `files.length > 0` check decides **not to append a `file` part** when no file is chosen; the server then sees `file == null` with optional/DTO binding.
- If the user picks an actual 0-byte file, `FormData` still includes the `file` part, and `MultipartFile.isEmpty()` is `true`.
- `fetch` sets `Content-Type` with the boundary automatically. Never set the multipart header manually.

A traditional HTML form submit may handle an unselected file input differently from the conditional JavaScript snippet above. Therefore, **test both requests without the part and requests with a 0-byte part**.

## 11. BindingResult, Bean Validation, and error reporting

### 11.1. What does `@NotBlank` check?

- `@NotBlank String title`: must not be `null`, empty, or whitespace-only.
- `@NotNull MultipartFile file`: verifies only that the object is non-null, **not** its byte count.
- `@Valid @ModelAttribute UploadForm form`: instructs the provider to validate constraints on the DTO.
- `BindingResult`: allows the handler to inspect binding and validation errors. It must be placed **immediately after** the bound/validated object.

Example of reading field errors:

```java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        System.out.println(
                fieldError.getField() + ": "
                        + fieldError.getDefaultMessage());
    }
}
```

This is a fragment inside a handler with `BindingResult errors`. Real applications should translate field errors into a JSON structure with stable codes rather than only logging them.

If `BindingResult` is omitted immediately after a `@Valid @ModelAttribute`/`@RequestPart` argument and validation fails, Spring MVC typically throws `MethodArgumentNotValidException`; if method validation applies due to constraints directly on method parameters/return values, `HandlerMethodValidationException` may be thrown. Choose error handling based on handler signature and Spring version.

### 11.2. Writing a custom “non-empty file” constraint

You can write a custom Jakarta Validation constraint such as `@NonEmptyUpload` and `ConstraintValidator<NonEmptyUpload, MultipartFile>`:

```java
public class NonEmptyUploadValidator
        implements ConstraintValidator<NonEmptyUpload, MultipartFile> {

    @Override
    public boolean isValid(
            MultipartFile file, ConstraintValidatorContext context) {
        return file != null && !file.isEmpty();
    }
}
```

This is an **illustrative core validator snippet**; to compile, define the `@NonEmptyUpload` annotation with `@Constraint(validatedBy=NonEmptyUploadValidator.class)`, `@Target`, `@Retention(RUNTIME)`, `message`, `groups`, `payload`, and import Jakarta Validation/Spring `MultipartFile`. It is not included in the runnable project in section 7.

With this rule, the annotation is placed on the DTO's `MultipartFile` field. If some workflows allow the field to be absent, the constraint can validate only non-empty content while `@NotNull` checks presence; clarify the business contract before writing the validator.

## 12. Common errors and corresponding exceptions

| Condition | Common Spring MVC exception | Typical default response |
| --- | --- | --- |
| Missing required `@RequestParam("title")` | `MissingServletRequestParameterException` | 400 |
| Missing required `@RequestParam("file") MultipartFile` or `@RequestPart("file")` | `MissingServletRequestPartException` | 400 |
| Malformed/unparseable multipart body | `MultipartException` or related multipart error | Typically 4xx/5xx depending on cause and configuration |
| Content type incompatible with `consumes` or converter | `HttpMediaTypeNotSupportedException` | 415 |
| Malformed/unreadable JSON part | `HttpMessageNotReadableException` | 400 |
| `@Valid @RequestPart Metadata` / DTO validation fails | `MethodArgumentNotValidException` (or method validation branch depending on signature) | 400 |
| File exceeds upload limit | `MaxUploadSizeExceededException`/container upload error | Can be mapped to 413 in an appropriate handler |
| File present with `isEmpty()` | **No automatic framework exception** | Controller/custom validator must reject explicitly |

Do not hardcode every case to a single exception. In particular, **missing file** and **empty file** need separate handling if the API contract distinguishes them.

A `@RestControllerAdvice` can standardize errors when needed:

```java
@RestControllerAdvice
class UploadErrorAdvice {

    @ExceptionHandler(MissingServletRequestPartException.class)
    ResponseEntity<Map<String, String>> missing(
            MissingServletRequestPartException e) {

        return ResponseEntity.badRequest().body(
                Map.of("error", "part.missing",
                       "part", e.getRequestPartName()));
    }
}
```

This is an **illustrative snippet independent of section 7's project** (if added to a project, import `@RestControllerAdvice`, `@ExceptionHandler`, the exception, `ResponseEntity`, and `Map`). In real applications, `ProblemDetail` can return a unified error structure. Customizing error responses changes defaults, so keep tests aligned.

## 13. Size limits, formats, and saving files

In Spring Boot 3.x, multipart support is configured via `spring.servlet.multipart.*` properties. Example customization:

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=8MB
spring.servlet.multipart.file-size-threshold=0B
```

This is an **illustrative configuration**, not the defaults. In Spring Boot 3.5, documentation lists defaults of `max-file-size=1MB` and `max-request-size=10MB`; adjust per application needs. Exceeding limits can be blocked **while the parser reads the request**, even before `@Valid` or the controller runs.

Beyond `file.isEmpty()`, production uploads require:
- **Size limits:** check `getSize()` in business logic (if stricter than global settings) and configure parser caps to prevent overload.
- **File types:** `getContentType()` and extensions from `getOriginalFilename()` are client-supplied hints only. Verify real content by inspecting format/magic bytes when needed.
- **Storage names and paths:** generate target names server-side (UUID or server ID), prevent path traversal, normalize and verify the target directory; never use client-supplied strings directly.
- **Storage handling:** consider streaming to avoid holding large files in RAM; move temporary uploads to durable storage within the request lifecycle; handle I/O errors.
- **Access policies:** verify who may upload, allowed data types, read permissions after upload, and malware scanning where required.
- **Recording metadata:** store the original filename only as sanitized display metadata, never as a durable file identifier.

A filename sent to the server **is not a trusted path**. `getOriginalFilename()` may be empty, `null`, or contain client-crafted path segments. Using it directly to write files can cause overwrites or path traversal.

## 14. Debugging checklist when files/fields are “lost” in Spring MVC

1. **Check HTTP Content-Type:** is it `multipart/form-data` with a valid boundary? When using `fetch(FormData)`, let the browser set the header.
2. **Check form field names:** does `name="file"` match `@RequestParam("file")`/`@RequestPart("file")`? Names and casing must match.
3. **Check whether the part is actually sent:** inspect the raw request in tests or use `MockMultipartFile`. Separate missing-part cases from 0-byte-part cases.
4. **Check `required`:** `true` may reject before the controller; `false` requires handling `null` inside the controller.
5. **Check `@ModelAttribute`:** does the DTO have proper setter/constructor binding? Do field names match parameter names? Does `BindingResult` immediately follow the DTO?
6. **Check `@Valid`:** for DTOs with `@NotBlank`, are the provider and validation trigger annotations present? For empty files, do you have a custom rule/`isEmpty()` check?
7. **Check JSON parts:** does the metadata part have `Content-Type: application/json`? Can Jackson deserialize the DTO?
8. **Check upload limits:** is the parser rejecting oversized files before the controller? Check `spring.servlet.multipart.max-file-size` and `max-request-size`.
9. **Check error handlers:** is `@ControllerAdvice` mapping two different errors to the same status/message?
10. **Check stack:** is the app Spring MVC Servlet or WebFlux? `MultipartFile` and `FilePart` belong to separate APIs.

## 15. Practice exercises

1. Change `@RequestParam("file")` to `@RequestParam(name="file", required=false)` on the required endpoint; add a `file == null` branch and verify the custom error with MockMvc.
2. Upload a 0-byte `empty.txt` file that still has a filename. Compare `file.getOriginalFilename()`, `getSize()`, and `isEmpty()`; why does a filename not prove a file has content?
3. Rename the HTML form field from `file` to `attachment` without changing the controller; explain why Spring treats `file` as missing.
4. Remove `@Valid` from `@ModelAttribute UploadForm`; send `title="   "` and check whether `@NotBlank` still runs automatically.
5. Change `@RequestPart("metadata")` to `@RequestParam("metadata") Metadata` without writing a converter; explain why the JSON part is no longer read by `HttpMessageConverter`.
6. Send the metadata part with `text/plain` containing a JSON string. Observe the response when no compatible converter applies, then fix the part's `Content-Type`.
7. Add an endpoint accepting `List<MultipartFile>`, and test 0, 1, and 2 files under the name `files`; do not check list length alone—verify each `MultipartFile.isEmpty()`.
8. Configure a 1MB max file limit; write a test/request exceeding the limit to demonstrate the parser can reject it before the controller.
9. Write a custom constraint for `MultipartFile`, testing both `null` and a 0-byte file, and compare its error handling with `@NotNull`.

**Key takeaway:** `@RequestParam` and `@RequestPart` control **how parts are located/parsed**, `@ModelAttribute` controls **how form fields bind to an object**, and `@Valid`/`BindingResult` control **how DTO errors are validated and read**. A **missing** required part and a **present-but-empty** `MultipartFile` are two distinct states; test and handle them separately according to your API contract.

## References

- [Spring Framework — Multipart requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework — `@ModelAttribute` binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — `MultipartFile` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html)
- [Spring Framework — Controller method validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Multipart application properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot 3.5 — Testing with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)