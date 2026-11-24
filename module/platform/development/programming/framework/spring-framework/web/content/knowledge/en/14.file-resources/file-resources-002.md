# Receiving MultipartFile, Part, and Combining Files With JSON Data in Spring MVC

## 1. Objectives and Context

Many APIs receive not just JSON or just a file, but **a file along with structured metadata** in the same HTTP request. For example, a client wants to create a document with `title`, `category` properties, and the file `note.txt`:

- `title`, `category`: business data validated with Bean Validation.
- `file`: uploaded bytes, plus client-supplied filename and Content-Type.
- The server needs to process both metadata and file in one operation, while managing security and size limits.

In **Spring Web MVC on the Servlet stack**, there are three common parameter types:

1. `MultipartFile`: Spring's abstraction for reading a file part's metadata and content.
2. `jakarta.servlet.http.Part`: Jakarta Servlet's native abstraction for each multipart part, independent of `MultipartFile`.
3. `@RequestPart` with a Java DTO: uses `HttpMessageConverter` to decode **the body of a single part** such as JSON into a DTO.

After this lesson, you will be able to explain HTTP multipart boundaries/headers, distinguish `@RequestParam`, `@ModelAttribute`, `@RequestPart`, and `@RequestBody`, implement an API accepting JSON + file, write tests with MockMvc, choose safe file-saving APIs, and handle validation/security/limits.

The main examples use **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**, and `spring-boot-starter-web`. The Spring code examples are Servlet MVC and do not apply verbatim to WebFlux (`FilePart`/a different reactive stack).

## 2. What is multipart/form-data?

An HTTP request can have a body containing **multiple parts**. Each part has a `Content-Disposition` header, may have a `Content-Type`, and has its own payload. The outer envelope carries the `multipart/form-data` media type and a `boundary`:

```http
POST /api/uploads/mixed HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary
Accept: application/json

--DemoBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{"title":"Notes","category":"notes"}
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

ABC
--DemoBoundary--
```

This is an **illustrative wire-format representation**: real HTTP multipart uses `CRLF` to separate headers/bodies and boundaries, and file bytes may not be text. When using `curl -F` or browser `FormData`, the client picks the boundary, builds headers, and encodes the body automatically. **Do not manually set a `Content-Type: multipart/form-data` header without a boundary** when the client library builds the multipart body itself; a malformed header can prevent the server from parsing the request.

Distinguish two media type layers:

- **Outer** `Content-Type: multipart/form-data; boundary=...` declares the body is multipart.
- **Part `metadata`** has `Content-Type: application/json`; the Jackson converter can read it into `UploadMetadata`.
- **Part `file`** has `Content-Type: text/plain` or `application/octet-stream`; with `MultipartFile`/`Part`, the server typically receives bytes and decides how to validate them rather than deserializing into a JSON DTO.
- `Content-Disposition: form-data; name="metadata"` identifies the part name. The name must match `@RequestPart("metadata")`; `filename` is only client-supplied metadata and is untrusted.

A file and JSON metadata reside in **one request**, but that does not mean saving the file + saving to the database is an atomic transaction. If writing the file succeeds while writing to the database fails, you need cleanup/compensation or a reliable workflow to avoid leaving orphan files.

### Multipart is Not JSON Containing a File

A JSON request:

```json
{"title":"Notes","fileBase64":"QUJD"}
```

is different from multipart. Base64 inflates the payload and requires decoding; multipart is better suited when transmitting file bytes alongside text/JSON parts. If an API is small and only accepts strings, plain JSON may still suffice. Choosing multipart should be based on the **HTTP contract** and how clients send data.

## 3. From Servlet Part to Controller Arguments

In Spring MVC 6.x, `StandardServletMultipartResolver` integrates the Servlet container's `jakarta.servlet.http.Part` parser into `DispatcherServlet`. Spring Boot MVC usually registers the resolver and `MultipartConfigElement` automatically, so controllers do not initialize a multipart parser themselves. This mechanism is used here to distinguish a **file part** from a **JSON metadata part**; resolver configuration, the `multipartResolver` bean name, eager/lazy parsing, and Servlet container policies are covered in depth in the chapter's `MultipartResolver` lesson.

```text
POST multipart/form-data
       |
Servlet container -> parsed Parts / temporary storage
       |
Spring MVC MultipartResolver
       |
       +-- "file"     -> MultipartFile or Servlet Part
       |
       +-- "metadata" (Content-Type: application/json)
                        -> HttpMessageConverter -> UploadMetadata DTO
                        -> @Valid / Bean Validation
       |
Controller -> service -> HTTP response
```

Returned values are not guaranteed safe just because the parser succeeded: the controller still needs validation, authorization, and storing the file into dedicated storage. For JSON parts, **each part's `Content-Type`**, not only the outer `multipart/form-data`, determines whether a converter can read the DTO.

### Required Configuration for the Example to Run

The Maven example in section 7 has `application.properties` enforcing multipart limits directly in the Servlet configuration:

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=5MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.strict-servlet-compliance=true
```

`max-file-size` applies per file; `max-request-size` applies to the entire multipart envelope, including metadata and other parts. `file-size-threshold` only controls the memory/temporary-disk threshold, not a long-term quota. `strict-servlet-compliance` restricts the resolver to `multipart/form-data` and does not verify file contents. If `resolve-lazily` is not explicitly set, parsing normally occurs eagerly by default; enabling lazy parsing may change **when parsing errors occur**, without increasing size limits.

Proxy, Servlet container, and memory/disk limits still apply independently; `MockMvc` does not simulate a full real HTTP multipart parser. Tests for limits and upload protections must use a real server/container in a controlled environment.

## 4. MultipartFile: Spring MVC's Primary API

`org.springframework.web.multipart.MultipartFile` provides:

| Method | Meaning |
| --- | --- |
| `getName()` | Form field/part name, e.g., `file` |
| `getOriginalFilename()` | Client-declared filename; **untrusted** |
| `getContentType()` | Client-declared MIME type; may be null or spoofed |
| `isEmpty()` | No file was selected or zero bytes, depending on request |
| `getSize()` | Content size in bytes |
| `getBytes()` | Reads entire content into a `byte[]` — avoid for large files |
| `getInputStream()` | Reads content as a stream; should be closed after use |
| `transferTo(File/Path)` | Transfers content to a target file per specific contract/implementation |

When a handler receives:

```java
@PostMapping(path = "/upload",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String upload(@RequestParam("file") MultipartFile file) {
    // ...
}
```

this is an illustrative method that must be placed inside a controller with imports. `@RequestParam` can be used with `MultipartFile` and form fields. `@RequestPart("file") MultipartFile` is also valid. For simple files, both usually resolve the same file part; `@RequestPart` becomes more important when **a part contains JSON that a converter must read into a DTO**.

### MultipartFile Content Is Scoped to the Request Lifetime

File bytes may be held in RAM or a container-managed temporary file. Once the request finishes, temporary data may be deleted. Therefore:

- If needed after the request, move the content into application-controlled storage while the request is still active.
- Do not store a `MultipartFile` in a singleton field or pass it to an async job expecting the stream to remain open.
- Never equate `getOriginalFilename()` with the filename saved on disk. Filenames can contain slashes, backslashes, dots, unusual Unicode, or path traversal sequences such as `../../secret.txt`.
- For large files, `getBytes()` can create memory pressure; use streams or a dedicated streaming/upload mechanism when appropriate.
- Do not assume `getContentType()` reflects the true content; it is client metadata.

## 5. jakarta.servlet.http.Part: Lower-Level Servlet API

`jakarta.servlet.http.Part` is the standard Servlet API abstraction. Typical operations:

```java
String name = part.getName();
String filename = part.getSubmittedFileName();
String contentType = part.getContentType();
long size = part.getSize();
try (InputStream in = part.getInputStream()) {
    // Read the required bytes.
}
```

This is only a snippet, requiring `import java.io.InputStream` and an existing `Part part` parameter. Besides these methods, `Part` has `getHeader(s)`, `write(String)`, and `delete()`. `write`/`delete` interact with the container's multipart mechanism; pay attention to relative storage/location rules and portability.

In a controller:

```java
@PostMapping(path = "/part",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String inspect(@RequestPart("file") Part file) {
    return file.getName() + ":" + file.getSize();
}
```

This method is illustrative only; in a `@RestController` the string is the response body, whereas in a `@Controller` without `@ResponseBody` the string may be interpreted as a view name. `Part` is useful when you need the standard Servlet API or access to part headers; `MultipartFile` is more convenient in pure Spring MVC projects.

### MultipartFile or Part?

| Need | Usually reasonable preference |
| --- | --- |
| Most Spring MVC upload APIs | `MultipartFile` |
| Servlet API independent of Spring's multipart abstraction | `jakarta.servlet.http.Part` |
| Inspect raw headers of a part | `Part` or request multipart headers API |
| A few MB of file data, streaming needed | Both provide an input stream |
| Upload JSON metadata into a DTO | **`@RequestPart("metadata") UploadMetadata`** |
| Receive multiple files under the same field name | `List<MultipartFile>` or array |
| HTML form with text fields + file | `@ModelAttribute` or `@RequestParam` for fields, `MultipartFile` for file |

There is no need to convert every `Part` into a `MultipartFile` by copying bytes into RAM just to "standardize". Pick one clear abstraction per contract/controller.

## 6. @RequestPart for Combining JSON Metadata and a File

When a multipart request has a JSON part `metadata` and a file part `file`:

```java
@PostMapping(path = "/mixed",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @Valid @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    // ...
}
```

`@RequestPart("metadata") UploadMetadata` differs from `@RequestParam String metadata`:

- `@RequestPart` for a DTO uses `HttpMessageConverter` to read **the part's body** based on the **part's Content-Type**, similar to `@RequestBody` for a whole JSON request body.
- `@RequestParam("metadata") String` receives a raw text parameter; turning it into a DTO typically requires manual JSON parsing, without the standard converter path of `@RequestPart`.
- `@RequestPart("file") MultipartFile` binds the file directly. File bytes are not automatically read by Jackson into a DTO.
- `@Valid` on metadata triggers Spring constraint validation after converter deserialization; if validation fails without a `BindingResult` to handle it, it typically returns `400 Bad Request`.
- `consumes="multipart/form-data"` applies to the **outer request**, while the JSON part must have `Content-Type: application/json`. A client sending a JSON string whose part is tagged `text/plain` can trigger `415 Unsupported Media Type` for the DTO.

Comparison:

| Annotation | Typically used to read | Mechanism |
| --- | --- | --- |
| `@RequestBody Dto` | A request with a JSON body | JSON converter on the whole request |
| `@RequestPart("metadata") Dto` | A multipart part with JSON content | JSON converter **on that individual part** |
| `@RequestPart("file") MultipartFile` | A part containing a file | Multipart argument handling |
| `@RequestParam("file") MultipartFile` | A form file field | Multipart argument handling |
| `@RequestParam String title` | A form field / query parameter | Parameter conversion/binding |
| `@ModelAttribute UploadForm` | Form fields and file properties | `WebDataBinder` property/constructor binding |

**Do not place `@RequestBody UploadMetadata` alongside `@RequestPart MultipartFile` expecting the JSON converter to read metadata from a separate JSON block inside the multipart body.** The overall request body is a multipart envelope, not a single JSON document. You must use `@RequestPart` for the JSON part.

## 7. Complete Runnable Spring Boot Example: JSON + File + Servlet Part

This example receives a small text file and JSON metadata. The server returns a JSON receipt containing `title`, actual byte count read, and SHA-256 digest (to illustrate stream processing, **not an antivirus mechanism**). There is also a separate endpoint demonstrating `Part` and a simple form endpoint with `@RequestParam`.

### 7.1. Maven Project Tree

```text
mvc-upload-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/upload/
    │   │   ├── UploadApplication.java
    │   │   └── UploadController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/upload/
        └── UploadControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-upload-demo</artifactId>
    <version>1.0.0</version>
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

**`src/main/resources/application.properties`**

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=5MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.strict-servlet-compliance=true
```

For this demo, files exceeding 2 MB will be rejected via multipart limits before or during argument resolution. The exact HTTP status/body of an upload size error can depend on the handler/container; test it and add exception advice for a production contract if you want a uniform response.

**`src/main/java/demo/upload/UploadApplication.java`**

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

### 7.2. Controller With Three Input Styles

**`src/main/java/demo/upload/UploadController.java`**

```java
package demo.upload;

import jakarta.servlet.http.Part;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    public record UploadMetadata(
            @NotBlank @Size(max = 80) String title,
            @NotBlank String category) {}

    public record UploadReceipt(
            String title,
            String category,
            long byteCount,
            String sha256) {}

    @PostMapping(
            path = "/mixed",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UploadReceipt> mixed(
            @Valid @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") MultipartFile file)
            throws IOException, NoSuchAlgorithmException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "File is empty");
        }
        // Demo check on declared MIME only; does not replace content sniffing.
        if (!MediaType.TEXT_PLAIN_VALUE.equals(file.getContentType())) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "Only declared text/plain files are accepted");
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        long size = 0;
        try (InputStream input = file.getInputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
                size += count;
            }
        }

        UploadReceipt receipt = new UploadReceipt(
                metadata.title(), metadata.category(),
                size, HexFormat.of().formatHex(digest.digest()));

        return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
    }

    @PostMapping(
            path = "/part",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Long> servletPart(
            @RequestPart("file") Part part) throws IOException {

        long count;
        try (InputStream input = part.getInputStream()) {
            count = input.transferTo(OutputStream.nullOutputStream());
        }
        return Map.of("byteCount", count);
    }

    @PostMapping(
            path = "/simple",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> simple(
            @RequestParam("description") String description,
            @RequestParam("file") MultipartFile file) {

        if (description.isBlank() || file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload");
        }
        return Map.of(
                "description", description,
                "byteCount", file.getSize());
    }
}
```

**Checking what each piece means:**

1. `UploadMetadata` is a Java 17 record; Jackson reads the JSON part with `Content-Type: application/json` into the record.
2. `@Valid` enforces `@NotBlank` and `@Size` before the controller executes business logic. If `title` or `category` is missing, `400` is typically returned due to `MethodArgumentNotValidException`.
3. `MultipartFile` provides the byte stream and metadata. The example only accepts declared `text/plain` to demonstrate a `415` scenario; this check **does not protect** against MIME spoofing or malicious content.
4. `MessageDigest SHA-256` reads the file in 8192-byte chunks and computes the digest without calling `getBytes()`. However, the Servlet container still has buffering/temp-file mechanisms; reading a stream in the controller does not mean the request is always end-to-end streaming.
5. `byteCount` is the actual byte count read, not the number of Unicode characters or `String.length()`.
6. `servletPart` receives `jakarta.servlet.http.Part` and uses Java's `InputStream.transferTo(OutputStream.nullOutputStream())` to count bytes in the stream. This demonstrates Servlet Part without **persisting data permanently**.
7. `simple` illustrates a `description` form field and a `file` upload via `@RequestParam`. There is no need for a JSON DTO part for a simple text field.
8. The controller never uses `getOriginalFilename()` as a path and does not save files to the server. This is an intentional choice to avoid poor security examples; section 11 covers real storage rules.

One compile check: `InputStream.transferTo(OutputStream)` has existed since Java 9; `OutputStream.nullOutputStream()` since Java 11; `HexFormat` since Java 17. On Java 17, all of these APIs are valid.

### 7.3. Running the Project and Creating a Sample File

In the `mvc-upload-demo` directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Run the two commands **sequentially**. You need JDK 17+ and a working Maven installation. After starting the app on `localhost:8080`, create a test file:

```bash
printf 'ABC' > note.txt
```

This command uses a Bash or equivalent shell and writes the exact three ASCII bytes `A`, `B`, `C` **with no trailing newline**. On PowerShell, create it using a byte array instead of `Set-Content` (because that cmdlet can alter encoding or append a newline).

Upload JSON + file with curl:

```bash
curl -i -X POST 'http://localhost:8080/api/uploads/mixed' \
  -H 'Accept: application/json' \
  -F 'metadata={"title":"Notes","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=text/plain'
```

`curl -F` automatically creates `multipart/form-data` and the boundary; **do not** manually add `-H 'Content-Type: multipart/form-data'`. `type=application/json` on the metadata part is the decisive detail that allows the JSON converter to read the record.

Expected main response:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"title":"Notes","category":"notes","byteCount":3,"sha256":"b5d4045c3f466fa91fe2cc6abe79232a1a57cdf104f7a26e716e0a1e2789df78"}
```

This is the SHA-256 of the exact ASCII bytes `ABC`. If the file has a newline or different encoding, `sha256` and `byteCount` will differ. JSON key order and whitespace are not a fixed contract; when testing, compare JSON fields.

### 7.4. Uploading With Servlet Part

```bash
curl -i -X POST 'http://localhost:8080/api/uploads/part' \
  -F 'file=@note.txt;type=text/plain'
```

Response body:

```json
{"byteCount":3}
```

Here Spring passes the `file` part directly to `Part`; the controller does not need `MultipartFile`. If you use `Part.write(String)` for real storage, review the container/multipart temp-location rules and never use the raw client filename as the save path.

### 7.5. Regular Form Field + File

```bash
curl -i -X POST 'http://localhost:8080/api/uploads/simple' \
  -F 'description=Meeting notes' \
  -F 'file=@note.txt;type=text/plain'
```

Expected response:

```json
{"description":"Meeting notes","byteCount":3}
```

Unlike `/mixed`, the `description` field is an ordinary text form field rather than a JSON document; `@RequestParam` is a better fit.

### 7.6. Error Cases to Observe

**Empty file:**

```bash
: > empty.txt
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"Empty","category":"notes"};type=application/json' \
  -F 'file=@empty.txt;type=text/plain'
```

Expected `400 Bad Request` due to `file.isEmpty()`. `: > empty.txt` is Bash syntax; on PowerShell use another way to create a 0-byte file.

**Invalid metadata:**

```bash
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=text/plain'
```

Expected `400` due to `@NotBlank`. The shape of the error body depends on Boot/MVC exception handling configuration; the demo does not define a custom error JSON schema.

**JSON part with wrong media type:**

```bash
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"Demo","category":"notes"};type=text/plain' \
  -F 'file=@note.txt;type=text/plain'
```

Typically returns `415 Unsupported Media Type`: the outer body is still valid multipart, but `HttpMessageConverter` cannot read an `UploadMetadata` DTO from a `text/plain` part. Do not confuse this with the file's `text/plain` content type, since the file part is received as raw bytes.

**File declaring another MIME type:**

```bash
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"Demo","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=application/octet-stream'
```

Expected `415` from the controller's own check. If a client declares `text/plain` while the real content is malware or binary, the demo controller **cannot detect it** from the header alone; you must apply content-validation and file-scanning policies when storing or granting access to files.

### 7.7. Browser Client With FormData

An HTML form for files:

```html
<form method="post" action="/api/uploads/simple"
      enctype="multipart/form-data">
    <input name="description" type="text" required>
    <input name="file" type="file" required>
    <button type="submit">Upload</button>
</form>
```

This form POSTs multipart data to `/simple`. Because the server returns JSON, the browser will display the JSON response; in a real product you might redirect/render a view or use JavaScript.

With `fetch` and a JSON part:

```javascript
const metadata = {title: "Notes", category: "notes"};
const fileInput = document.querySelector("#file");
const file = fileInput.files[0];

const data = new FormData();
data.append(
  "metadata",
  new Blob([JSON.stringify(metadata)], {type: "application/json"})
);
data.append("file", file);

const response = await fetch("/api/uploads/mixed", {
  method: "POST",
  body: data
});

if (!response.ok) {
  throw new Error("Upload failed: HTTP " + response.status);
}
const receipt = await response.json();
console.log(receipt);
```

This is a **browser JavaScript snippet** assuming an input `id="file"` exists in the DOM; it is not a standalone runnable script without the input and script context. `FormData.append("metadata", Blob application/json)` ensures the JSON part carries the proper media type. **Do not manually set the outer `Content-Type` in fetch**; the browser generates the matching boundary automatically. Check that `file` exists and validate its size on the client for better UX, but the server must still validate independently.

## 8. Testing Multipart, JSON Converters, and Servlet Part With MockMvc

MockMvc provides `MockMultipartFile` and `MockPart` to simulate an HTTP multipart request. This is a good way to verify behavior without running a real server port.

**`src/test/java/demo/upload/UploadControllerTest.java`**

```java
package demo.upload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadControllerTest {

    @Autowired
    MockMvc mvc;

    private MockMultipartFile metadata(String json, String mime) {
        return new MockMultipartFile(
                "metadata", "", mime,
                json.getBytes(StandardCharsets.UTF_8));
    }

    private MockMultipartFile file(String mime, byte[] content) {
        return new MockMultipartFile(
                "file", "note.txt", mime, content);
    }

    @Test
    void acceptsJsonMetadataAndTextFile() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"Demo\",\"category\":\"notes\"}",
                        "application/json"))
                    .file(file("text/plain",
                        "ABC".getBytes(StandardCharsets.UTF_8))))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.title").value("Demo"))
           .andExpect(jsonPath("$.category").value("notes"))
           .andExpect(jsonPath("$.byteCount").value(3))
           .andExpect(jsonPath("$.sha256").value(
               "b5d4045c3f466fa91fe2cc6abe79232a1a57cdf104f7a26e716e0a1e2789df78"));
    }

    @Test
    void invalidJsonMetadataFailsValidation() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"\",\"category\":\"notes\"}",
                        "application/json"))
                    .file(file("text/plain", new byte[]{65})))
           .andExpect(status().isBadRequest());
    }

    @Test
    void nonJsonMetadataPartIsUnsupported() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"Demo\",\"category\":\"notes\"}",
                        "text/plain"))
                    .file(file("text/plain", new byte[]{65})))
           .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void emptyFileIsRejected() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"Demo\",\"category\":\"notes\"}",
                        "application/json"))
                    .file(file("text/plain", new byte[0])))
           .andExpect(status().isBadRequest());
    }

    @Test
    void servletPartIsRead() throws Exception {
        MockPart part = new MockPart(
                "file", "note.txt",
                "ABC".getBytes(StandardCharsets.UTF_8));
        part.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        mvc.perform(multipart("/api/uploads/part").part(part))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.byteCount").value(3));
    }

    @Test
    void ordinaryMultipartFieldsCanUseRequestParam()
            throws Exception {
        mvc.perform(multipart("/api/uploads/simple")
                    .param("description", "notes")
                    .file(file("text/plain", new byte[]{65, 66})))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.description").value("notes"))
           .andExpect(jsonPath("$.byteCount").value(2));
    }
}
```

Run:

```bash
mvn test
```

The test suite defines **6 test methods**. When they pass on a properly created project, Maven exits with code `0`; logs typically report something like `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`. These tests verify MVC argument resolution and converters; **`MockMvc` is not equivalent to a real proxy/container** for upload limits, temporary filesystems, network streaming, oversized multipart parsing, or security filters. Add integration tests through an embedded server and reverse proxy for production uploads.

### Why Does the Mock Test Need the Metadata Part's Own Content-Type?

`MockMultipartFile("metadata", "", "application/json", ...)` sets the metadata part's MIME type to JSON. If the part is declared as `text/plain`, `@RequestPart UploadMetadata` needs a converter that understands reading the DTO from `text/plain`, which normally does not exist. When inspecting raw multipart payloads, look at **part headers**, not only the outer `multipart/form-data`.

### Testing Sizes and Encodings

Running `mvn test` above does not guarantee that a 3MB upload will always return a specific status through real Tomcat. `MockMvc` typically bypasses the container's size-parsing mechanism. Real tests through an HTTP server should include:

- 0-byte files, files right at the 2MB threshold, and oversized files.
- Total request size (multiple parts) exceeding `max-request-size`.
- Filenames containing `../`, `\\`, Unicode/emoji, and excessive length.
- Spoofed MIME headers vs magic bytes.
- JSON parts missing `Content-Type`, wrong charset, malformed JSON, and DTO constraint violations.
- Clients aborting uploads mid-transfer, network timeouts, retries, and concurrent requests.
- Untrusted file contents containing scripts, HTML, executables, archive bombs, or file-format exploits.

## 9. Multiple Files and Part Names

If the frontend sends multiple files under the same name `files`:

```java
@PostMapping(
        path = "/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public List<Long> batch(
        @RequestParam("files") List<MultipartFile> files) {
    return files.stream().map(MultipartFile::getSize).toList();
}
```

This is an illustrative method inside `@RestController`, requiring imports for `List`, `MultipartFile`, `RequestParam`, `PostMapping`, and `MediaType`. A client can call:

```bash
curl -F 'files=@a.txt' -F 'files=@b.txt' \
  'http://localhost:8080/api/uploads/batch'
```

However, the `/batch` endpoint **is not part of the runnable project in section 7** unless you explicitly add that method to the controller; the curl command applies specifically to this illustrative variant. With multiple files, enforce total size limits, part count limits, and concurrency limits, and avoid holding all byte arrays in RAM.

If a request carries both JSON metadata and multiple files, declare `@Valid @RequestPart("metadata") Dto metadata` and `@RequestPart("files") List<MultipartFile> files`; ensure the frontend uses matching names and the JSON part content type.

## 10. @ModelAttribute for Form Fields and a File on One Bean

In traditional HTML forms, you can bind text fields together with `MultipartFile` into one object:

```java
public class UploadForm {
    @NotBlank
    private String title;
    private MultipartFile file;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public MultipartFile getFile() { return file; }
    public void setFile(MultipartFile file) { this.file = file; }
}
```

Method in `@Controller`:

```java
@PostMapping(path = "/forms", consumes = "multipart/form-data")
public String handle(
        @Valid @ModelAttribute("uploadForm") UploadForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "uploads/new";
    }
    // Check file != null, !file.isEmpty() and handle storage.
    return "redirect:/uploads/done";
}
```

These two code blocks are **illustrative snippets**, lacking imports, controller class/templates, and full persistence logic. `@ModelAttribute` uses `WebDataBinder` to bind fields `title` and `file` to the DTO; `@Valid` can validate `title`, while `MultipartFile` needs dedicated file validation rules (or a custom validator). `BindingResult` should immediately follow the validated parameter.

**When to choose which approach?**

- HTML form with text + file, no JSON part: `@ModelAttribute UploadForm` or multiple `@RequestParam`s is usually most natural.
- API with JSON metadata + file, needing nested DTOs and Bean Validation: `@RequestPart("metadata") Dto`.
- Raw file without metadata: `@RequestParam MultipartFile` / `@RequestPart MultipartFile`.
- Header/container-level control of a part: `Part`.

Do not force a form text field into a JSON string and parse it manually just to reuse a DTO if the UX/API does not call for a JSON part.

## 11. Safe File Storage: Production Design

The example in section 7 **does not store files**; it only processes the stream. When actually saving files, design defense-in-depth layers:

### 11.1. Never Trust Client-Supplied Filenames

`getOriginalFilename()` or `Part.getSubmittedFileName()` is **client-sent** metadata. Never use it directly as a path:

```java
// ANTI-PATTERN: filename could be "../../secrets.txt".
Path target = uploadsDir.resolve(file.getOriginalFilename());
file.transferTo(target);
```

This snippet is **unsafe** and must never be used in production. Names can contain path separators, unusual encodings, reserved names, `..`, or Unicode normalization quirks; joining paths introduces path traversal or overwrite vulnerabilities.

A better design: generate a server-side storage key (UUID/random), and retain the client name separately as metadata after sanitizing and limiting length/charset. If downloads must use the original name, encode `Content-Disposition` safely; never concatenate raw filenames into headers.

Conceptual example (not yet a complete upload service):

```java
String storageKey = java.util.UUID.randomUUID().toString();
Path root = Path.of("/srv/app-upload-data").toAbsolutePath();
Path target = root.resolve(storageKey).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("Invalid upload target");
}
```

You must inspect and manage **filesystem symlinks**, permissions, path existence/atomic creation, and race conditions; a lone `startsWith` check does not solve every risk. Server-owned keys eliminate most path injection, but do not replace filesystem permissions. Use a directory outside the web root so uploaded content is never automatically served as static resources.

### 11.2. MIME, Extension, and Actual Content

`file.getContentType()` and `.pdf`/`.png` extensions are not proof of real content. For permitted file types:

1. Inspect declared MIME + extension (advisory only, never final).
2. Read magic bytes or parse the file structure with an appropriate library; bound parser/resource usage.
3. Accept only an allowlist of formats required by the business domain.
4. If files may be malicious, scan for malware through an appropriate pipeline.
5. Set proper download `Content-Type` and `Content-Disposition`, and restrict browser sniffing (e.g., `X-Content-Type-Options: nosniff`).
6. For images/videos, consider transcoding/re-encoding through a safe pipeline to reduce embedded payload risks.
7. Never treat client-submitted file data as executables, trusted HTML, or server-side templates.

### 11.3. Size Limits and Resource Exhaustion

Limits must exist across multiple layers: reverse proxy, ingress/API gateway, Servlet parser, application policy (file type/count/size), storage quota, parser CPU/memory, upload timeout, and total concurrent uploads. The multipart parser may write temporary data to disk; a system running out of disk space due to many size-valid files also suffers DoS.

Using `file.getBytes()` loads the entire content onto the heap. Using a stream avoids one kind of memory copy, yet the multipart request may still be buffered temporarily; it does not equate to end-to-end streaming from network to object storage. For multi-GB files, consider resumable/chunked uploads or direct-to-object-storage with short-lived upload URLs and clear security policies.

### 11.4. JSON Metadata Must Also Be Validated and Authorized

Allow the client to submit only permitted fields. Never bind metadata directly to a JPA entity containing `ownerId`, `role`, `tenantId`, or `approved` and trust those values. Derive identity/tenant from the authentication context and verify access permissions before attaching the file to a resource.

If metadata specifies a client-supplied `ownerId`, the backend must still verify the user is authorized to act on that owner. `@Valid` and converters ensure syntax/constraints, **never authorization**.

### 11.5. Storage + Database Are Not Automatically Atomic

A robust workflow can look like:

```text
1. Validate authentication, authorization, and metadata
2. Check file count/size/type
3. Write file to staging/quarantine using a server-generated key
4. Scan/parse according to policy
5. Write DB metadata + PENDING/READY status in a transaction
6. Publish the file only when status is READY
7. On failure: cleanup/compensation, controlled retry
```

This is an architectural sequence, not a promise of filesystem + SQL atomicity. If the DB commit fails after the file is written, cleanup is required; if file storage fails after the DB record is created, state tracking/retries or compensation are needed. Never expose download URLs before the file is accepted.

### 11.6. Security Context and CSRF

For session/cookie-based web apps using Spring Security, multipart form POSTs usually require CSRF protection; file uploads are no exception. APIs using bearer tokens rather than cookies follow a different policy. The Boot demo does not add Spring Security, so it does not demonstrate a production CSRF strategy.

If uploads are allowed from another browser origin, design CORS with strict origin/method/header allowlists; CORS does not authenticate callers or prevent CSRF.

## 12. Exception Handling and HTTP Status Codes

| Error | Common source | Typical status |
| --- | --- | --- |
| Missing required part | `@RequestPart("file")` or `metadata` not sent | `400 Bad Request` |
| Malformed JSON part | Jackson converter cannot parse metadata | `400 Bad Request` |
| JSON part declared as `text/plain` | No converter reads the DTO for that media type | `415 Unsupported Media Type` |
| `@Valid` metadata fails | `MethodArgumentNotValidException` | `400 Bad Request` |
| Empty file per demo policy | Controller throws `ResponseStatusException(BAD_REQUEST)` | `400` |
| File has disallowed declared MIME | Controller policy in demo | `415` |
| File exceeds size limit | Multipart resolver/container, `MaxUploadSizeExceededException` depending on config | Usually `413 Payload Too Large` when mapped appropriately; verify environment |
| Outer Content-Type is not multipart | `consumes=multipart/form-data` mismatch | `415` |
| Disk full, I/O or scanner failure | Storage/server | `5xx`; never expose server paths/stack |
| File/metadata belongs to another tenant | Authorization in service layer | `403` or `404` per security policy |

**Never promise a single status code across every multipart environment**: size-limit errors can occur at the reverse proxy/container before entering the controller/advice, and once a response is committed its status cannot be changed. If the API requires a stable error contract, test end-to-end and configure error responses at the right layer.

An illustrative handler for size limits in MVC, **not required** to run the demo:

```java
@RestControllerAdvice
public class UploadErrorAdvice {
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ProblemDetail> tooLarge(
            MaxUploadSizeExceededException exception) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.PAYLOAD_TOO_LARGE,
                "Uploaded content exceeds the configured limit.");
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(p);
    }
}
```

This snippet belongs in a separate file and requires imports for `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, `HttpStatus`, and `MaxUploadSizeExceededException`. This handling path only applies if the exception reaches the MVC resolver; rejections by a reverse proxy beforehand will never reach this advice. `ProblemDetail` is part of Spring 6.x supporting RFC 9457.

## 13. Common Mistakes When Combining JSON With Files

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@RequestPart Dto` gets 415 even though body looks like JSON | JSON part has `text/plain`/missing Content-Type, no converter supports it | Send `metadata` part with `application/json` |
| `MissingServletRequestPartException` | Wrong part name or part omitted | Check `name="metadata"` and `@RequestPart("metadata")` |
| Outer multipart request fails to parse | Missing/wrong boundary header, client manually set Content-Type | Let browser/curl generate boundary automatically |
| `@RequestBody Dto` fails to parse multipart request | Trying to read the entire multipart body as JSON | Use `@RequestPart` for the JSON part |
| File always has size 0 | Empty file or client sent wrong field | Check `file.isEmpty()`, raw part bytes, and field name |
| `ByteCount` differs from `String` length | Unicode charset / newlines / binary | Count bytes from input stream, never use `String.length()` |
| JSON validation does not run | Forgot `@Valid` or validation dependency | Add `@Valid` and `spring-boot-starter-validation` |
| Metadata valid but file unprotected | Only validated DTO, skipped content/policy checks | Enforce authz, size, MIME/magic, and scanning |
| Upload returns HTML error, client expects JSON | Exception happened outside controller/advice | Unify error handling across MVC + proxy/container |
| Large upload spikes RAM | Used `file.getBytes()` or buffered entire payload | Enforce size limits, use streaming/appropriate storage pipeline |
| Duplicate filename overwrites existing file | Trusted `getOriginalFilename()` | Generate server-side UUID/storage key |
| File has `Content-Type: image/png` but is a script | Trusted client header | Inspect bytes and parse safely, never execute files |
| Binding `Part` fails | Differing Servlet multipart config/resolver/container | Confirm Boot multipart enabled, Servlet API, and part name |
| File disappears in async job | Multipart temp cleanup after request | Move into durable storage before returning/queuing |
| Metadata/DB saved but file save failed | No compensation workflow | Use staging + transaction state + cleanup |
| 413 never reaches `ControllerAdvice` | Proxy/container rejected early | Test limits at every layer; configure error policy |

Debugging workflow:

1. Check the HTTP request's **outer Content-Type** and boundary first.
2. Inspect each part: `Content-Disposition name`, filename, **part Content-Type**, and byte count.
3. Match part names with `@RequestPart` / `@RequestParam`.
4. If the DTO fails to deserialize, check the converter and 400/415 error; if the DTO is valid but the file fails, inspect the upload policy.
5. Review multipart limits at the proxy, Servlet/container, and Boot layers.
6. For production, verify storage state, cleanup, scanning, and authorization; never log raw file bytes, tokens, or PII.

## 14. Which API Design Should You Choose?

| Scenario | Recommended approach |
| --- | --- |
| Single file upload without metadata | `@RequestParam("file") MultipartFile` or `@RequestPart` |
| File upload + a few form text fields | `@RequestParam` or `@ModelAttribute UploadForm` |
| File upload + nested JSON metadata | `@Valid @RequestPart("metadata") Dto` + `@RequestPart("file") MultipartFile` |
| Need Servlet-native access | `jakarta.servlet.http.Part` |
| Multiple files under one field | `List<MultipartFile>` with count limit |
| WebFlux application | `FilePart` and reactive codecs, not MVC `MultipartFile` |
| Very large files | Streaming/resumable/direct-to-storage architecture, never `getBytes()` |
| API needing upload + business transaction | Staging, state machine, compensation, idempotency |
| Need real format verification | File signature/parser/sandbox scanning, not just client MIME |
| Browser client using `fetch` | `FormData` + JSON `Blob` with `application/json`; let browser generate boundary |

## 15. Self-Check Exercises

1. How do the two `Content-Type` values differ between the outer multipart request and the JSON part?
2. Why can `@RequestPart("metadata") UploadMetadata` deserialize JSON while `@RequestParam("metadata") String` does not automatically become a DTO?
3. When should you use `MultipartFile`, and when should you use Servlet `Part`?
4. Why can `@RequestBody UploadMetadata` not replace `@RequestPart` in a multipart request?
5. Is a file with `filename="../../etc/passwd"` or Content-Type `image/png` trustworthy?
6. Why should an upload service not retain a `MultipartFile` to read its stream after the request finishes?
7. When using `curl -F` or `fetch(FormData)`, why should you not manually set an outer `Content-Type` without a boundary?
8. Does `@Valid` detect malware or path traversal in filenames?
9. Why is a `MockMvc` size test no substitute for real testing through a Servlet container?
10. Why is "file upload succeeded but database insert failed" not solved by a simple SQL transaction alone?
11. Why is returning `byteCount` by reading `InputStream` safer than `String.length()` for binary data?
12. If the metadata part sends `text/plain` while its body is `{"title":"..."}`, what information does Spring use to select a converter?

**Hints:** (1) Outer `multipart/form-data` carries a boundary; the JSON part is `application/json`. (2) `RequestPart` applies `HttpMessageConverter` to the part; `RequestParam String` reads plain text. (3) Spring convenience vs Servlet-native API. (4) The whole body is a multipart envelope, not JSON. (5) No, both filename and MIME are client-supplied. (6) Temp content may be cleaned up after the request. (7) The payload boundary must match the header. (8) No, those belong to independent policy/security layers. (9) Container/proxy and temporary disk handling differ from mocks. (10) Filesystem/object storage is not part of the same DB transaction. (11) Byte count does not depend on character encoding. (12) The part's `Content-Type` and converters supporting the Java target type.

## 16. Official References

- [Spring Framework 6.1 — Multipart Resolver](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework — Multipart Forms and @RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.1 — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/multipart/MultipartFile.html)
- [Spring Framework 6.1 — RequestPart Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html)
- [Spring Framework 6.1 — RequestPartMethodArgumentResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestPartMethodArgumentResolver.html)
- [Spring Boot 3.3 — Common Application Properties, Multipart](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [Jakarta Servlet — Part API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/part)
- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)

**Conclusion:** With `multipart/form-data`, Spring MVC passes file parts into `MultipartFile` or `Part`, while JSON parts can be decoded via `@RequestPart Dto` through `HttpMessageConverter`. A production-ready upload API requires clear MIME and part-name contracts, DTO validation, byte/size/authorization checks, safe storage, and an error/cleanup plan; uploading is an HTTP, data, and security problem, not just calling `getBytes()`.
