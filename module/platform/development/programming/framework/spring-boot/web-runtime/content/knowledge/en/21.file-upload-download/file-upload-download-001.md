# Multipart in HTTP and Differences from JSON Content

## 1. The Problem to Solve

An API that receives order details usually only needs JSON. However, an API that receives an avatar image, a PDF document, or a CSV file also has to receive **binary file content**. If we send a file inside a JSON string, we have to convert the bytes into a text representation such as Base64, which makes the payload larger and increases memory demand. HTTP offers another mechanism: `multipart/form-data`, which allows a single request to contain **multiple parts**, each with its own name, headers, and content.

In Spring Boot, understanding the HTTP format properly determines how you write the controller:
- With `Content-Type: application/json`, use `@RequestBody` to read and convert the entire body into a Java object.
- With `Content-Type: multipart/form-data; boundary=...`, use `@RequestParam`, `@RequestPart`, and `MultipartFile` in Spring MVC, or `FilePart`/`Part` in Spring WebFlux.
- When sending **JSON metadata alongside a file**, the metadata part can carry `Content-Type: application/json` so that `@RequestPart` decodes it using the JSON converter.

This lesson belongs to the **file upload and download** context of the Spring Boot web runtime. After this lesson, you will be able to read a raw multipart request, distinguish JSON/multipart/raw binary bodies, run a Java 17 upload endpoint yourself, understand size-limit configuration, and recognize common errors related to security, memory, temporary storage, and HTTP status codes.

> **Practical versions:** the standalone runnable example uses Java 17+ and **Spring Boot 3.5.x, Spring MVC** with the `spring-boot-starter-web` starter. On Spring Boot 4.x, choose the `spring-boot-starter-webmvc` starter. Differences between Servlet and WebFlux are explained separately; do not mix MVC's `MultipartFile` with WebFlux's `FilePart`.

## 2. “HTTP Body” Does Not Mean “JSON”

An HTTP request has a method, URL, headers, and a body (if present). `Content-Type` describes how to interpret the body. JSON data is only **one content format**, not the only mechanism in HTTP.

### 2.1. A Regular JSON Body

An example request sending an object:

~~~http
POST /api/documents/metadata HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "title": "Report",
  "category": "finance"
}
~~~

Everything after the blank line between headers and body is **a single JSON document**. Spring MVC can read it directly with:

~~~java
// Fragment inside a @RestController, not a standalone program.
@PostMapping(
    path = "/api/documents/metadata",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Metadata create(@RequestBody Metadata metadata) {
    return metadata;
}
~~~

`@RequestBody` relies on an `HttpMessageConverter` (usually the Jackson JSON converter) to convert the entire body into `Metadata`. If the client sends invalid JSON, mismatched data types, or inappropriate headers, the controller might not even be invoked.

### 2.2. A multipart/form-data Body

An example request carrying **JSON metadata** and a **file**:

~~~http
POST /api/documents HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary

--DemoBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Report","category":"finance"}
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<byte-content-of-the-PDF-file>
--DemoBoundary--
~~~

This is a **structural HTTP illustration**, not something meant to be copied verbatim over the wire: the placeholder `<byte-content-of-the-PDF-file>` represents actual PDF bytes, and in wire format line breaks use CRLF (`\r\n`). An HTTP client will generate a valid boundary and emit properly formatted bytes.

Key differences:
1. The outer header has `Content-Type: multipart/form-data` and the required parameter `boundary=DemoBoundary`.
2. Each part begins with `--DemoBoundary`, followed by part headers, a blank line, and its own body.
3. `Content-Disposition: form-data; name="metadata"` identifies the **field name**. The `file` field also has `filename="report.pdf"`, which is only information reported by the client.
4. `Content-Type: application/json` is **on the metadata part**; `application/pdf` is **on the file part**. Each part's Content-Type can differ from the outermost Content-Type.
5. The closing delimiter `--DemoBoundary--` appends two trailing hyphens. The boundary is chosen so that the delimiter does not collide with any part's content.

**Do not confuse the boundary with the filename or field name.** The client chooses the boundary string, and it must match exactly between the outer header and the delimiters. Per RFC 7578, `multipart/form-data` uses the MIME multipart mechanism, where each part must have a `Content-Disposition` containing `name`; file parts usually include `filename`. Other part headers depend on the content and are not guaranteed to always be present.

## 3. Comparison Table: JSON vs. Multipart

| Criterion | `application/json` | `multipart/form-data` |
|---|---|---|
| Nature | A single JSON document as the request body | Body composed of multiple parts separated by a boundary |
| Common purpose | Structured data: metadata, business commands, lists | Forms containing files, or files and metadata in the same request |
| Binary data | Usually requires Base64/strings or another protocol | File bytes can stay directly in binary form |
| Outer header | `Content-Type: application/json` | `Content-Type: multipart/form-data; boundary=...` |
| Per-part headers | No separate parts | Each part has `Content-Disposition`, and may have `Content-Type` |
| Receiving in Spring MVC | `@RequestBody Dto` | `@RequestPart Dto`, `@RequestParam`, `MultipartFile` |
| Receiving in WebFlux | `@RequestBody Mono<Dto>`/Dto | `@RequestPart`, `Part`, `FilePart`, `Flux<PartEvent>` |
| Browser form | JSON is usually constructed in JavaScript | `<form enctype="multipart/form-data">` or JavaScript `FormData` |
| Payload size | Very well suited for structured text data | Suitable for files, though multipart also has header/boundary overhead |
| Validation | Field types, schema, Bean Validation | Validate each part, JSON metadata, and file bytes separately |
| Inspection/debugging | Easy to read in a JSON viewer | Must inspect parts, field names, content types, and boundary |
| When to prefer | No file bytes needed | Need to send files and attributes in the same request |

**There is no rule saying “multipart is always better than JSON.”** JSON is simpler for APIs that only accept metadata. Multipart is useful when multiple items or binary files are sent in one request. There are also APIs that accept **a single raw binary file** using `Content-Type: application/octet-stream`, though in that case there is no mechanism for splitting parts as in multipart.

### JSON Containing Base64 Is Still JSON

An API might accept:

~~~json
{
  "filename": "report.pdf",
  "contentBase64": "JVBERi0xLjQK..."
}
~~~

This approach is valid if the API contract specifies it, but it is not multipart. When encoding binary data as Base64, the data typically grows by nearly **33%** (excluding the JSON wrapper), while increasing encode/decode CPU cost and string/byte copies in memory. Do not assume Base64 provides security or encryption; it is merely a data representation encoding.

For example, a 3 MiB file can turn into a Base64 string of roughly 4 MiB. For large files, streaming multipart or a binary-body endpoint is usually more appropriate, depending on data-control requirements.

## 4. Easily Confused Names and Headers

| Component | Example | Meaning |
|---|---|---|
| Outer media type | `multipart/form-data` | The entire body is multipart |
| Outer boundary | `boundary=----client123` | Client-generated delimiter string; must match the raw body |
| Part field name | `name="file"` | Matches `@RequestPart("file")` or `@RequestParam("file")` |
| Part filename | `filename="photo.jpg"` | Client-reported name; **must not be trusted** when saving |
| Part media type | `Content-Type: image/jpeg` | Client-declared content type; must be verified if security-sensitive |
| Part body | Image bytes | Actual content of the file |
| Request length | `Content-Length` or equivalent transfer framing | Outer size/transfer framing; does not replace server multipart limits |
| Closing delimiter | `--boundary--` | Marks the end of the multipart body |

The names `metadata` and `file` in the controller are the API contract. If the client sends `name="upload"` while the handler requires `@RequestPart("file")`, the server will report that the `file` part is missing. Renaming the Java variable alone does not change the part name the client must send; the value in the annotation is the contract.

**Note on the JSON part's Content-Type:** JSON metadata is an independent part, so if you want `@RequestPart("metadata") Metadata` to automatically deserialize JSON, that part should carry `Content-Type: application/json`. If the client only sends a `text/plain` string containing JSON text, Spring might not select the JSON converter and may return `415 Unsupported Media Type`. Use `@RequestPart("metadata") String` to handle plain text if the contract is designed that way, or fix the client to send the JSON part with the proper media type.

## 5. Choosing the Right Annotation in Spring MVC

### `@RequestBody` — the entire body is JSON

~~~java
@PostMapping(
    path = "/api/metadata",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Metadata postMetadata(@RequestBody Metadata metadata) {
    return metadata;
}
~~~

Appropriate when **the entire HTTP body** is just JSON. Do not put a `@RequestBody Metadata` parameter and expect Spring to automatically split `multipart/form-data` into a JSON part and a file part.

### `@RequestParam` — form fields or files

~~~java
// Spring MVC fragment; requires importing MultipartFile and RequestParam.
@PostMapping(
    path = "/api/simple-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public String upload(
    @RequestParam("description") String description,
    @RequestParam("file") MultipartFile file
) {
    return description + ": " + file.getSize();
}
~~~

When a form has a text field `description` and a file field `file`, `@RequestParam` is the straightforward choice. Spring MVC supports `MultipartFile` or `jakarta.servlet.http.Part` for files and can bind `List<MultipartFile>` when multiple files share the same field name.

### `@RequestPart` — a part requiring message conversion

~~~java
// Spring MVC fragment; metadata part must be sent as application/json.
@PostMapping(
    path = "/api/upload-with-meta",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public String upload(
    @RequestPart("metadata") Metadata metadata,
    @RequestPart("file") MultipartFile file
) {
    return metadata.title() + " (" + file.getSize() + " bytes)";
}
~~~

`@RequestPart` is useful when metadata is a complex JSON object requiring an `HttpMessageConverter`. It can be combined with `@Valid`/Bean Validation on the DTO; metadata validation **does not replace** file validation.

### `@ModelAttribute` — bind form data into an object

A simple form with text attributes and a `MultipartFile` can also be bound into a form object. Use it when you want form data structured as a JavaBean; use `@RequestPart` when the client explicitly sends a JSON subpart that needs deserialization.

**Do not mix annotations out of habit:** choose based on the outer media type, each part's media type, and the data type.

## 6. Runnable Lab: Standalone JSON vs. Multipart with File + JSON

Create a **Spring Boot 3.5.x**, Java 17+ project using Spring Initializr, Gradle build type, with the **Spring Web** dependency. Initializr generates `build.gradle` and the Gradle wrapper. For Boot 4.x, use the corresponding `spring-boot-starter-webmvc` dependency.

If adding the dependency to an existing Boot 3.5 project that already has the plugin and dependency management configured, the Gradle fragment is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Create a single Java file at `src/main/java/demo/upload/UploadDemoApplication.java`:

~~~java
package demo.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@RestController
public class UploadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(UploadDemoApplication.class, args);
    }

    public record Metadata(String title) { }

    public record Receipt(String title, long bytes, boolean received) { }

    @PostMapping(
        path = "/api/metadata",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Metadata json(@RequestBody Metadata metadata) {
        return metadata;
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public Receipt upload(
            @RequestPart("metadata") Metadata metadata,
            @RequestPart("file") MultipartFile file) {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "File must not be empty");
        }

        return new Receipt(metadata.title(), file.getSize(), true);
    }
}
~~~

This code **runs out of the box** in a Boot MVC application with the dependency configured. It only inspects and returns file info, **without writing files to disk**; that keeps the experiment focused on how HTTP multipart is parsed. In production, after validation you need to decide on the storage mechanism, ID generation, authorization, and safe file handling.

Run from the project root directory:

~~~bash
./gradlew bootRun
~~~

On Windows, use `gradlew.bat bootRun`.

### 6.1. Sending JSON

The following command uses `curl` in Bash/macOS/Linux:

~~~bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"title":"Demo"}' \
  http://localhost:8080/api/metadata
~~~

**Expected JSON response body:**

~~~json
{"title":"Demo"}
~~~

### 6.2. Sending Multipart

Create an ASCII file of exactly 3 bytes:

~~~bash
printf 'abc' > sample.txt
~~~

Send JSON metadata **as one part** and the file **as another part**:

~~~bash
curl -sS \
  -F 'metadata={"title":"Demo"};type=application/json' \
  -F 'file=@sample.txt;type=text/plain' \
  http://localhost:8080/api/upload
~~~

**Expected JSON response body:**

~~~json
{"title":"Demo","bytes":3,"received":true}
~~~

Explanation of each part:

- `-F` tells curl to construct `multipart/form-data` and an appropriate boundary.
- `metadata=...;type=application/json` ensures the metadata part has the JSON media type, allowing Spring to deserialize it into the `Metadata` record.
- `file=@sample.txt;type=text/plain` sends the **3-byte file content**, not the literal string `@sample.txt`; the `@` sign is curl's syntax when using `-F`.
- `@RequestPart("file") MultipartFile` reads the `file` part; `file.getSize()` returns the number of bytes received in this example.
- The server returns JSON because of `@RestController` and the JSON converter, even though **the request is multipart**. Request and response media types do not have to match.

If running from Windows PowerShell, use `curl.exe` instead of Windows PowerShell 5.1's `curl` alias and adjust quoting accordingly. The `printf` command is POSIX; you can create `sample.txt` with the exact three bytes `abc` using an editor without adding a trailing newline.

### 6.3. Comparing with an HTTP Inspector

Try sending JSON to the URL that only accepts multipart:

~~~bash
curl -i -H 'Content-Type: application/json' \
  -d '{"title":"Demo"}' \
  http://localhost:8080/api/upload
~~~

Because `/api/upload` declares `consumes=multipart/form-data`, this request does not match the media type and typically returns **415 Unsupported Media Type**. This is a **header/body contract** error, not a Java record controller bug or a missing file on disk.

Try omitting the JSON content type from the metadata part. Depending on curl and the converter, the server may fail to deserialize metadata into `Metadata` and report a media type error; inspect each part's headers with `curl -v` or an HTTP inspector tool before changing annotations.

## 7. Browser Clients: HTML Forms and JavaScript FormData

### Standard HTML Form

~~~html
<form method="post" action="/api/upload" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">Send</button>
</form>
~~~

This form only sends a file; it **does not send a JSON metadata part**, so it does not fully satisfy the endpoint in section 6. It illustrates that `enctype="multipart/form-data"` is how a browser submits form content containing files. You can design the server to accept text fields via `@RequestParam` instead of a JSON part, or use JavaScript as shown below.

### JavaScript Sending a File and a JSON Part

The following snippet is a **browser-side fragment**; assume the page has `<input id="file" type="file">` and the user has selected a file:

~~~javascript
const selected = document.querySelector("#file").files[0];
if (!selected) {
  throw new Error("Choose a file first");
}

const form = new FormData();
form.append(
  "metadata",
  new Blob([JSON.stringify({ title: "Demo" })],
           { type: "application/json" })
);
form.append("file", selected);

const response = await fetch("/api/upload", {
  method: "POST",
  body: form
});
if (!response.ok) {
  throw new Error("Upload failed: " + response.status);
}
const receipt = await response.json();
console.log(receipt);
~~~

**Do not manually set the `Content-Type: multipart/form-data` header in `fetch`** when using `FormData`: the browser must generate the boundary and fill the `boundary` parameter into the header. If you manually set the header without a boundary matching the body, the server cannot split the parts and the request may fail with 400. Using `FormData` also does not automatically validate file types or user permissions.

For cross-origin APIs, there are also CORS/preflight and cookie/credentials policies that must be configured independently. A request with a valid body can still be blocked by CORS or Security.

## 8. Multiple Files, Empty Files, and Complex Metadata

### Multiple Files with the Same Part Name

Per RFC 7578, a client can send **multiple parts with the same `name="files"`**, each carrying one file. In Spring MVC:

~~~java
// Controller fragment, not a standalone Java program.
@PostMapping(
    path = "/api/bulk-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public int uploadMany(@RequestPart("files") List<MultipartFile> files) {
    return files.size();
}
~~~

Client:

~~~bash
curl -sS \
  -F 'files=@a.txt' \
  -F 'files=@b.txt' \
  http://localhost:8080/api/bulk-upload
~~~

The command assumes `a.txt` and `b.txt` exist. You do not create a JSON array containing files or use arbitrary different part names. Do not confuse `files` with `file` in the annotation.

### Empty Files, Missing Files, and 0-Byte Files

- **Missing part**: the controller requires `@RequestPart("file")` but the request has no `name="file"`; Spring typically returns 400 because a required part is missing.
- **Part present but empty**: `file.isEmpty()` is true when there is no data or no file was selected in how the request is represented; the example in section 6 explicitly returns 400.
- **Valid 0-byte file**: some business domains still allow this (e.g., marker files), so `isEmpty()` is not a universal rule. Define the contract per endpoint.
- **Empty or missing filename**: `MultipartFile.getOriginalFilename()` can be null or empty depending on the client; do not rely on the filename to decide whether actual data is present.

### Multi-Field JSON Metadata

~~~json
{
  "title": "Monthly Report",
  "category": "finance",
  "tags": ["internal", "2026"],
  "notify": false
}
~~~

This is still **one JSON part**. Spring will deserialize that structure into a compatible DTO/record if the media type is correct and a JSON converter is present. DTO validation can be enabled with `@Valid @RequestPart("metadata")` when Bean Validation and corresponding constraints are added. Afterward, you **still must** validate the file separately from the DTO: size, format, permissions, count, and virus scanning according to business rules.

## 9. Spring MVC: Multipart Resolver, Lifecycle, and Upload Limits

Spring Boot MVC uses the Servlet container's multipart support (such as Tomcat) and configures a resolver so `multipart/form-data` parts are parsed before argument resolvers pass them into the controller. Normally, the MVC starter provides this mechanism and you do not need to write a MIME parser yourself.

**Spring Boot MVC defaults** per current documentation:
- `spring.servlet.multipart.enabled=true`: enables multipart.
- `spring.servlet.multipart.max-file-size=1MB`: limit **per file**.
- `spring.servlet.multipart.max-request-size=10MB`: limit for **the entire multipart request**, including files/parts and overhead.
- `spring.servlet.multipart.file-size-threshold=0B`: threshold at which buffered file data spills to disk.
- `spring.servlet.multipart.location`: **temporary/intermediate** directory used during parsing, not the final business storage path.

An **illustrative configuration** for an API allowing files up to 5MB and requests up to 6MB:

~~~yaml
spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 5MB
      max-request-size: 6MB
      file-size-threshold: 0B
~~~

For multipart with metadata, the total request is larger than the raw file size due to headers, boundaries, and other parts; choose `max-request-size` appropriately, and do not default it to equal `max-file-size` if there are multiple files or large metadata.

**Limits span multiple layers:** reverse proxy/CDN/ingress, servlet container, Spring multipart parsing, application validation, and filesystem/object storage can all enforce different size limits. Choose consistent thresholds and know which layer is likely to reject before the controller. Oversized uploads are commonly surfaced as **413 Payload Too Large**, though the actual HTTP status/error body may differ depending on exception handlers, proxies, and containers.

**The temporary directory is not business storage.** Multipart content may be buffered in memory or written to a temp file depending on the implementation/threshold. Once the request finishes processing, temporary data can be deleted; to keep the file, you must copy/transfer it to persistent storage before the request ends.

### Do Not Read Entire Files into Heap Unnecessarily

~~~java
// MVC fragment: large files can consume a lot of memory with getBytes().
byte[] bytes = file.getBytes();
~~~

`getBytes()` loads the entire content into a byte array; it is unsuitable for many concurrent large files. You can use `getInputStream()` to process as a stream or `transferTo(...)` to save. These still require validation and resource management; they do not guarantee file safety by themselves.

Example fragment saving a file with a server-generated name:

~~~java
// Fragment executed after validating permissions and file type.
// uploadDir already exists, is outside public static folders, and has proper permissions.
Path target = uploadDir.resolve(
    java.util.UUID.randomUUID() + ".bin"
);
try (InputStream in = file.getInputStream()) {
    java.nio.file.Files.copy(in, target);
}
~~~

`uploadDir`, `InputStream`, and `Path` above are variables/imports from a real service; **not a standalone program**. A random name avoids trusting paths from `getOriginalFilename()`, while production also needs atomic creation, quotas, cleanup, content inspection, idempotency, and DB metadata coordination.

## 10. Spring WebFlux: Using FilePart, Part, and Reactive Processing

Spring WebFlux does not use Servlet `MultipartFile` as its primary API. Common types include:
- `Part`: interface for a part of a multipart request.
- `FilePart`: part carrying a file; provides `filename()` and `transferTo(Path)` returning `Mono<Void>`.
- `@RequestPart("metadata") Metadata`: can deserialize a JSON part; `Mono<Metadata>` can also be used depending on handling.
- `@RequestBody Mono<MultiValueMap<String, Part>>`: processes the collection of parts.
- `@RequestBody Flux<PartEvent>`: processes multipart data as a stream of parts/events; requires properly managing/releasing `DataBuffer` to avoid memory leaks.

Example **standalone fragment for a WebFlux application** (do not mix into the MVC app in section 6):

~~~java
// Assume this is a method in a @RestController of a WebFlux application.
// /srv/app/uploads already exists and the app has write permission on the host.
@PostMapping(
    path = "/api/reactive-upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<Void> upload(@RequestPart("file") FilePart file) {
    Path target = Path.of(
        "/srv/app/uploads",
        UUID.randomUUID().toString() + ".bin"
    );
    return file.transferTo(target);
}
~~~

The corresponding imports are `org.springframework.http.codec.multipart.FilePart`, `org.springframework.http.MediaType`, `reactor.core.publisher.Mono`, `java.nio.file.Path`, `java.util.UUID`, and MVC-style annotations from `org.springframework.web.bind.annotation` executed by WebFlux. This is an example of **using FilePart**, without validation/authorization or production storage management. `transferTo` returns a `Mono<Void>` pipeline; Spring subscribes and executes it when handling the request—avoid calling `block()` on the event loop.

**WebFlux** multipart configuration differs from Servlet:

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 256KB
      max-headers-size: 10KB
      max-parts: 50
~~~

These properties tune per-part memory usage, header size, and part count according to the codec/implementation of the Boot version. They are **not** Tomcat MVC's `spring.servlet.multipart.max-file-size`. The `max-in-memory-size` threshold governs how parts are processed/buffered, **not** a maximum total upload size limit.

If you need to enforce file size limits at the business level in WebFlux, you must check parser/server/gateway limits, track received data size within the flow, or apply storage policies. With `Flux<PartEvent>`, every buffer must be consumed, forwarded, or released; reading only the first event and dropping the rest can retain memory/resources.

## 11. File Upload vs. File Download

In the context of “file upload and download,” the two HTTP directions should be separated:

| Flow | Common HTTP | Typical Body |
|---|---|---|
| **Upload**: client sends file to server | `POST`/`PUT` | `multipart/form-data` for file + fields, or `application/octet-stream` for raw file |
| **Download**: server sends file to client | `GET` | A binary body with an appropriate `Content-Type`, possibly with `Content-Disposition: attachment` |
| **Metadata**: exchanging file attributes | `GET`/`POST`/`PATCH` per API | `application/json` |

A single file download **does not need multipart** just because it is a file. The response can be `application/pdf` or `application/octet-stream` with `Content-Disposition: attachment; filename=...`. Conversely, an upload API can return JSON containing the file ID, size, and processing status. **Request media type and response media type do not have to be the same.**

## 12. Security: Client Filename, MIME, Content, and Limits

Receiving a file means receiving **untrusted data**. Multipart is only a packaging format; it does not verify safety by itself.

1. **Do not trust `filename`:** the client-supplied value may contain path separators, `..` sequences, control characters, or colliding names. Generate a server-side storage ID and store the original name separately with proper escaping when displayed; never call `Path.of(uploadDir, file.getOriginalFilename())` and write directly.
2. **Do not trust client `Content-Type`:** `image/jpeg` can be sent even when the payload is HTML or an executable. When business rules require an allowlist, combine content signature checks/file parsers, allowed file types, output extensions, and verified MIME types.
3. **Limit size and part count:** reject at the gateway and server, not just with `if (file.getSize() > limit)` after the server has already buffered the file. Set max file/max request sizes, rate limits, timeouts, and quotas, and guard against floods of many small files.
4. **Authorize before saving or publishing:** enforce authentication, owner/resource authorization, CSRF protection for browser sessions, CORS controls, and never place private uploads in public static resources.
5. **Store in a safe area:** use a directory outside the web root with least-privilege filesystem permissions or private object storage; plan for antivirus/malware scanning, quarantining, lifecycle cleanup, encryption, and auditing according to business sensitivity.
6. **Mitigate content risks:** archives that expand enormously upon extraction (zip bombs), malformed images/CSVs/PDFs targeting parsers, dangerous extensions, and HTML/SVG containing scripts served on the same origin. When downloading, set `Content-Disposition`, `X-Content-Type-Options: nosniff`, and an appropriate cache policy.
7. **Watch memory/temp disk:** many concurrent uploads can exhaust temp disk or RAM; monitor disk space, I/O errors, active upload counts, and processing duration. Container temp storage may be wiped on pod restart.
8. **Protect metadata and idempotency:** saving the file and saving the DB record can fail independently. Design for orphan-file handling, retries, and IDs to avoid duplicate uploads.

**Keep in mind:** “valid multipart” only confirms the parser could read the body; storing and serving files safely requires multiple independent controls.

## 13. Common HTTP Errors and Root-Cause Investigation

| Symptom | Common Cause | How to Check |
|---|---|---|
| **400 Bad Request**, missing part | `@RequestPart("file")` but client sent `name="upload"` or omitted the file | Inspect each part's `Content-Disposition name`; match the annotation exactly |
| **400** during parsing | Missing/mismatched boundary between header and body, or truncated multipart body | Do not manually set Content-Type with `FormData`; inspect the raw request |
| **415 Unsupported Media Type** | Sent a full JSON body to an endpoint with `consumes=multipart/form-data` | Check the outer header and `consumes` |
| **415** on JSON part | Metadata is text/plain/octet-stream while controller expects a JSON-deserialized DTO | Set `Content-Type: application/json` on the **metadata part** |
| **413 Payload Too Large** | Exceeded proxy/server/multipart limit, or gateway blocked before Spring | Check limits at each layer and inspect error source logs |
| **400** on JSON metadata DTO | Malformed JSON, field type mismatch, or validation failure | Inspect conversion/validation exception and part payload |
| **401/403** | Security/filter, CSRF, or user not authorized to upload | Check Security rules, session/token, logs, and CORS |
| **500 / I/O error** | Temp directory out of disk space, permission error, or broken storage | Check disk space, filesystem permissions, and storage logs |
| Received **0-byte** file | Client selected an empty file, used `-F file=path` instead of `file=@path`, or read the wrong part | Check curl syntax, `isEmpty()`, and `getSize()` |
| Form fields arrive but file is missing | HTML missing `enctype="multipart/form-data"` or wrong `name` | Inspect DevTools Network and Request payload |
| Buffer error in WebFlux | Misused reactive API, `DataBuffer` not consumed/released | Review the publisher chain and part codec limits |

**Investigation workflow:** check HTTP method + URL → outer `Content-Type` header → boundary → each `Content-Disposition name` → per-part Content-Type → controller annotations → container/parser limits → Security → storage. Putting a breakpoint in the controller without inspecting the raw request easily misses errors occurring before the controller is ever called.

Do not force every error into the same status code. Spring MVC/WebFlux, proxies, servers, Bean Validation, and exception handlers can emit different specific statuses and bodies. Observe the actual behavior and attribute the error to the right layer.

## 14. Measuring and Testing Uploads

To verify an upload API handles real load, measuring HTTP 200 alone is not enough. Observe:

- **Sizes**: small, exact max size, over max size, many parts, many files, empty files, and MIME-mismatched files.
- **Timing**: time spent receiving body, parsing, validating, scanning, writing to storage, committing metadata, and responding.
- **Resources**: heap, direct buffers, temp disk, container I/O, connection count, network, and timeouts.
- **Safety**: filenames containing `../`, `.jpg` files with non-image content, malicious archives, unauthorized users, and duplicate upload IDs.
- **Resilience**: client disconnecting mid-upload, retrying the same request, storage failure, pod restart, and slow scanning.
- **Responses**: 2xx when valid, 4xx for invalid/oversized requests, 5xx for server faults; clear error messages without leaking paths or stack traces.

Compact test case examples:

| Test | Request | What to Verify |
|---|---|---|
| Valid JSON | `Content-Type: application/json` + JSON metadata | Metadata endpoint returns JSON |
| Valid multipart | File + JSON part with `application/json` | Upload endpoint returns the expected receipt |
| Missing file part | Metadata only | Returns appropriate missing-part error |
| Wrong outer Content-Type | JSON sent to multipart-only route | Not routed as multipart; typically 415 |
| Metadata part wrong media type | JSON text but part marked text/plain | Converter/validation reflects the contract mismatch |
| Exceeds max file size | File > `spring.servlet.multipart.max-file-size` | Blocked at the right layer and file is not saved |
| Unsafe filename | `filename="../../a.txt"` | Storage does not use the client path directly |
| Large file in WebFlux | Realistic multi-part payload | Does not hold the entire file in memory just because the handler is reactive |

## 15. Self-Check Questions

**1.** When sending a `multipart/form-data` request with metadata and a file, must the entire body have `Content-Type: application/json`?

**Answer:** No. The outer Content-Type is `multipart/form-data; boundary=...`; only the metadata part carries `Content-Type: application/json`.

**2.** Why should you use `fetch(..., { body: formData })` without manually setting the multipart Content-Type?

**Answer:** The browser must generate the boundary and put the exact same value in both the header and the body. Setting Content-Type manually without a boundary or with the wrong boundary causes server parsing failures.

**3.** In MVC, when do you use `@RequestBody` instead of `@RequestPart`?

**Answer:** `@RequestBody` is for the **entire body** (such as JSON). `@RequestPart` is for **a single part** inside a multipart request, which can also deserialize a JSON part.

**4.** Can you send two files with the same part name?

**Answer:** Yes. Send two parts both with `name="files"` and receive them with `List<MultipartFile>` in MVC.

**5.** Is `MultipartFile.getOriginalFilename()` safe to use as the file storage path?

**Answer:** No. The value is client-supplied; generate a server-side storage name/ID and protect against path traversal, collisions, and unauthorized access.

**6.** In Spring Boot MVC, do `max-file-size=5MB` and `max-request-size=6MB` mean any number of files under 5MB each can be uploaded freely?

**Answer:** No. The total of all files plus other parts and multipart overhead must fit within **6MB** (in addition to proxy/container limits).

**7.** When an API uses WebFlux, do you receive files with Spring MVC's `MultipartFile` like in the Servlet example?

**Answer:** That is not the primary WebFlux handler type. Use `FilePart`/`Part` or `Flux<PartEvent>` for reactive multipart.

**8.** Is multipart required to download a PDF?

**Answer:** No. A GET response can send a PDF with `Content-Type: application/pdf` and `Content-Disposition: attachment`; multipart is only needed when a business protocol involves multiple parts.

## 16. References

- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [Spring Framework — MVC Multipart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — MVC @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux Multipart Content and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/)
- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)

**Core takeaway:** JSON represents **one structured payload**; multipart represents **multiple parts that may have different content types** within a single HTTP body. A correct upload contract aligns the outer Content-Type, boundary, field names, per-part media types, parser limits, and safe file-storage rules.
