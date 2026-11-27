# Documenting File Size or Type Errors in Spring REST Docs

## 1. Why Document Upload Errors?

A multipart upload endpoint typically restricts the size and types of files accepted. For example, an API accepting product images may only allow PNG/JPEG, cap each file at 5 MB, and return an error when a client sends a PDF or an oversized file.

These rules are part of the REST API contract. Clients need to know:
- Which file types are supported.
- Size limits applied per file or across the entire request.
- Which HTTP status is returned when a media type is invalid or the payload exceeds the limit.
- The error response structure, stable error codes, and helpful information to fix the request.

In **SPRING_REST_DOCS**, HTTP tests using MockMvc, WebTestClient, or REST Assured produce evidence for documentation. For multipart uploads, `requestParts(...)` documents request parts; `responseFields(...)`, `responseHeaders(...)`, and status snippets can document error outcomes. An error test can simultaneously verify the API responds properly and generate snippets to include in Asciidoctor/Markdown.

This lesson explains how to document file size and type errors, focusing on two common scenarios:

- `413 Payload Too Large` (the current reason phrase commonly used is **Content Too Large**) when content exceeds the limit.
- `415 Unsupported Media Type` when the request or a part uses a media type unsupported by the operation.

After this lesson, you will be able to design an upload contract, validate MIME type and size, write negative tests, document error responses, and recognize MockMvc's limitations for errors originating at the servlet container or reverse proxy.

## 2. Designing the Contract for an Upload Endpoint

Suppose `POST /api/products/{productId}/assets` accepts an image file and JSON metadata.

| Component | Example Contract |
| --- | --- |
| `file` part | Required, one image file |
| Accepted Content-Type | `image/png`, `image/jpeg` |
| Maximum file size | 5 MiB |
| `metadata` part | Required, `application/json` |
| Success response | `201 Created` |
| Unsupported media type | `415 Unsupported Media Type` |
| File exceeds business limit | `413 Content Too Large` |
| Error response structure | `code`, `message`, `status`, `path` |

The numbers and statuses here are **illustrative contract examples**. Projects should clearly define:
- Whether limits are measured in bytes, KiB/MiB, or another unit; use bytes in validation logic to avoid ambiguity.
- Whether the limit applies per file or to the total multipart request.
- Whether multipart overhead and metadata count toward the limit.
- The list of permitted media types.
- Which error the API returns when the client declares a valid MIME type but the bytes do not match the format.
- Whether error codes remain stable across versions.

Example error response:

```json
{
  "code": "FILE_TOO_LARGE",
  "message": "File must not exceed 5 MiB",
  "status": 413,
  "path": "/api/products/42/assets"
}
```

For unsupported media type:

```json
{
  "code": "UNSUPPORTED_FILE_TYPE",
  "message": "Only PNG and JPEG images are supported",
  "status": 415,
  "path": "/api/products/42/assets"
}
```

Use stable error codes so clients can handle errors programmatically. Messages can evolve for clarity; clients should not depend on exact message string matching.

## 3. Distinguishing Request Content-Type and Part Content-Type

Multipart has Content-Type at two layers:

```http
POST /api/products/42/assets HTTP/1.1
Content-Type: multipart/form-data; boundary=----UploadBoundary

------UploadBoundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

<binary bytes>
------UploadBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Book Cover"}
------UploadBoundary--
```

- `multipart/form-data; boundary=...` is the Content-Type of the **entire request**.
- `image/png` is the Content-Type of the **file part**.
- `application/json` is the Content-Type of the **metadata part**.

If an endpoint only accepts multipart, `consumes` is normally `MediaType.MULTIPART_FORM_DATA_VALUE`. This does not automatically restrict individual part media types. The application still needs to check `file.getContentType()` or use an appropriate converter for the JSON part.

When the overall request uses a type unsupported by the endpoint, Spring MVC can return `415` before the controller is invoked. When the file part has an invalid media type, the controller/service or conversion layer must check and map the error according to the contract. Both cases can return 415, yet differ in cause and error details.

## 4. Checking File Type: MIME Type and Actual Content

### 4.1. Client-Declared Content-Type

With `MultipartFile`, the application can read the value declared by the client:

```java
String declaredType = file.getContentType();
```

Allowlist check example:

```java
private static final Set<String> ALLOWED_IMAGE_TYPES =
        Set.of("image/png", "image/jpeg");

void validateDeclaredMediaType(MultipartFile file) {
    String contentType = file.getContentType();

    if (contentType == null || !ALLOWED_IMAGE_TYPES.contains(contentType)) {
        throw new UnsupportedFileTypeException();
    }
}
```

Match against an explicit allowlist rather than accepting all `image/*`. A client-declared MIME value does not prove the bytes actually conform to that format.

### 4.2. Checking Signatures or Parsing Content

A client can send a text file while setting the `Content-Type: image/png` header. Checking only the header lets a spoofed file slip past validation.

When the contract requires the file to actually be PNG or JPEG, inspect the file signature or parse it with an appropriate library. Conceptual example:

```java
void validateImageContent(byte[] bytes) {
    if (!imageSignatureDetector.isPng(bytes)
            && !imageSignatureDetector.isJpeg(bytes)) {
        throw new InvalidFileContentException();
    }
}
```

`imageSignatureDetector` is an illustrative component; choose a library and validation rules suited to your project. Checking magic bytes helps identify format but does not replace all content safety checks. If real image processing is required, try decoding to confirm valid structure and enforce image dimensions after decoding.

### 4.3. Naming Errors by Cause

| Scenario | Example Error | Illustrative Status |
| --- | --- | --- |
| MIME type not in allowlist | `UNSUPPORTED_FILE_TYPE` | 415 |
| Declared MIME valid, but bytes have wrong format | `INVALID_FILE_CONTENT` | 400 |
| File size exceeds business limit | `FILE_TOO_LARGE` | 413 |
| Malformed metadata JSON | `INVALID_METADATA` | 400 |
| Metadata part has unsuitable Content-Type | `UNSUPPORTED_PART_MEDIA_TYPE` | 415 |

The status for malformed content must be defined consistently. Some APIs may use 422 for unprocessable content; what matters is a clear contract and tests confirming the actual status/error code.

## 5. Checking File Size

`MultipartFile` provides `getSize()` and `isEmpty()`. You can enforce a limit in bytes:

```java
private static final long MAX_IMAGE_SIZE = 5L * 1024 * 1024;

void validateFileSize(MultipartFile file) {
    if (file.getSize() > MAX_IMAGE_SIZE) {
        throw new FileTooLargeException(MAX_IMAGE_SIZE);
    }
}
```

`5 MiB` equals `5 * 1024 * 1024` bytes. Distinguish:
- Absent file: the part was not sent.
- Empty/zero-byte file: the part is present, with size 0.
- Oversized file: the part is present and `getSize()` exceeds the limit.

If the contract requires a non-empty file, check `isEmpty()` separately. Do not use `isEmpty()` to conclude a part is absent.

### 5.1. Per-File Limit vs. Total Request Limit

Multiple layers of limits can exist:

| Layer | Limited Target | Example |
| --- | --- | --- |
| Business validation | Single file | `file.getSize() <= 5 MiB` |
| Multipart resolver/container | Single uploaded file | `max-file-size` |
| Multipart resolver/container | Total multipart request | `max-request-size` |
| Reverse proxy/API gateway | Entire HTTP request body | Body limit at gateway |

If an endpoint accepts multiple files, a 5 MiB limit per file does not mean the total request is capped at 5 MiB. Conversely, the total multipart request can exceed an individual file limit because it contains multiple files and overhead.

### 5.2. Multipart Configuration in Spring Boot

With the servlet stack, common properties are:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

`max-file-size` caps the size of a single file; `max-request-size` caps the total multipart request. These values must coordinate with reverse proxy, gateway, and infrastructure limits.

Container configuration can reject a request before the controller ever receives `MultipartFile`. Therefore, a unit-style MockMvc test invoking MVC directly does not always reproduce errors raised by the container or gateway. Distinguish:
- Checking business size in controller/service: can be tested reliably with MockMvc.
- Checking multipart resolver/container/proxy limits: requires integration tests with actual runtime configuration or testing through an appropriate integration environment.

## 6. Mapping Exceptions to a Stable Error Response

Example exceptions:

```java
public class FileTooLargeException extends RuntimeException {
    private final long maxBytes;

    public FileTooLargeException(long maxBytes) {
        super("Uploaded file exceeds the allowed size");
        this.maxBytes = maxBytes;
    }

    public long getMaxBytes() {
        return maxBytes;
    }
}

public class UnsupportedFileTypeException extends RuntimeException {
}
```

Error DTO:

```java
public record ApiError(
        String code,
        String message,
        int status,
        String path
) {}
```

Example `@RestControllerAdvice`:

```java
@RestControllerAdvice
class UploadExceptionHandler {

    @ExceptionHandler(FileTooLargeException.class)
    ResponseEntity<ApiError> handleFileTooLarge(
            FileTooLargeException exception,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "FILE_TOO_LARGE",
                "File must not exceed the configured size limit",
                413,
                request.getRequestURI()
        );

        return ResponseEntity.status(413).body(body);
    }

    @ExceptionHandler(UnsupportedFileTypeException.class)
    ResponseEntity<ApiError> handleUnsupportedType(
            UnsupportedFileTypeException exception,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "UNSUPPORTED_FILE_TYPE",
                "Only PNG and JPEG images are supported",
                415,
                request.getRequestURI()
        );

        return ResponseEntity.status(415).body(body);
    }
}
```

Illustrative example; in real code you can use `HttpStatus.PAYLOAD_TOO_LARGE` or the corresponding status enum for your Spring version, and you need to import `HttpServletRequest`. Framework HTTP status constant names can vary between versions; check your project's API before using them.

Do not expose stack traces, internal storage paths, bucket names, or sensitive parser details to clients. Log internally with a correlation ID and expose public error responses using stable error codes.

## 7. MockMvc: Testing Wrong File Type and Generating Error Snippets

Suppose `POST /api/products/{id}/assets` returns `415` when the `file` part lacks an allowed MIME type. The request still contains valid JSON metadata.

### 7.1. Building a Request with an Unsupported MIME Type

```java
MockMultipartFile wrongType = new MockMultipartFile(
        "file",
        "notes.txt",
        MediaType.TEXT_PLAIN_VALUE,
        "not an image".getBytes(StandardCharsets.UTF_8)
);

MockPart metadata = new MockPart(
        "metadata",
        """
        {"title":"Test asset"}
        """.getBytes(StandardCharsets.UTF_8)
);
metadata.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

### 7.2. Documenting Status and Error Body

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(wrongType)
        .part(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isUnsupportedMediaType())
    .andExpect(jsonPath("$.code").value("UNSUPPORTED_FILE_TYPE"))
    .andDo(document("products-upload-unsupported-file-type",
        requestParts(
            partWithName("file")
                .description("Image file; only PNG or JPEG accepted"),
            partWithName("metadata")
                .description("JSON metadata of the asset")
        ),
        responseFields(
            fieldWithPath("code").description("Stable error code"),
            fieldWithPath("message").description("Error description"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Request path that caused the error")
        )
    ));
```

Corresponding static imports:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
```

This test simultaneously asserts status and error code while generating snippets for request parts/response fields. `responseFields(...)` must match the actual error JSON exactly. If the response has extra fields, strict mode may require documenting or intentionally ignoring them.

You can add `responseHeaders(...)` when the error response has contract headers to publish, such as `Content-Type` or a correlation header.

## 8. MockMvc: Testing Files Exceeding Business Limits and Generating Snippets

To reliably test size with MockMvc, the application must have business validation based on `MultipartFile.getSize()` before processing/storing the file.

Example 5 MiB limit:

```java
private static final int MAX_FILE_BYTES = 5 * 1024 * 1024;

void validateSize(MultipartFile file) {
    if (file.getSize() > MAX_FILE_BYTES) {
        throw new FileTooLargeException(MAX_FILE_BYTES);
    }
}
```

Creating an oversized byte array:

```java
byte[] oversizedBytes = new byte[MAX_FILE_BYTES + 1];

MockMultipartFile oversizedFile = new MockMultipartFile(
        "file",
        "large.png",
        MediaType.IMAGE_PNG_VALUE,
        oversizedBytes
);
```

Test and snippet:

```java
mockMvc.perform(multipart("/api/products/{id}/assets", 42)
        .file(oversizedFile)
        .part(metadata)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isPayloadTooLarge())
    .andExpect(jsonPath("$.code").value("FILE_TOO_LARGE"))
    .andDo(document("products-upload-file-too-large",
        requestParts(
            partWithName("file")
                .description("Product image; 5 MiB limit"),
            partWithName("metadata")
                .description("JSON metadata of the asset")
        ),
        responseFields(
            fieldWithPath("code").description("Error code"),
            fieldWithPath("message").description("Error description"),
            fieldWithPath("status").description("HTTP status"),
            fieldWithPath("path").description("Request path")
        )
    ));
```

This is a business validation test. It creates a request larger than the limit checked by application code; it does not necessarily test the servlet container's `max-file-size` limit. If the container blocks the request before MVC receives it, the result can differ and requires integration testing against real server configuration.

When using large byte arrays, keep fixtures just large enough for fast tests. There is no need to create huge files if the contract only needs to verify exceeding the threshold by one byte.

## 9. Testing Spoofed MIME Bytes and Corrupted Files

A useful test declares a valid MIME type while sending invalid contents:

```java
MockMultipartFile fakePng = new MockMultipartFile(
        "file",
        "fake.png",
        MediaType.IMAGE_PNG_VALUE,
        "this is plain text".getBytes(StandardCharsets.UTF_8)
);
```

The MIME header says `image/png`, yet the bytes are plain text. If the API checks signatures or decodes images, the test must verify the error response per contract, for example:

```java
.andExpect(status().isBadRequest())
.andExpect(jsonPath("$.code").value("INVALID_FILE_CONTENT"));
```

Do not use this test to prove `415` for unsupported MIME: the header is `image/png`, so the cause is invalid file content. Classifying errors accurately helps clients know whether to change Content-Type or choose a different file.

## 10. Organizing Error Snippets and Asciidoctor

Suppose the tests generate operation IDs:
- `products-upload-unsupported-file-type`
- `products-upload-file-too-large`

The snippet directory can contain:

```text
build/generated-snippets/
├── products-upload-unsupported-file-type/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-parts.adoc
│   └── response-fields.adoc
└── products-upload-file-too-large/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-parts.adoc
    └── response-fields.adoc
```

Generated snippet filenames depend on the document snippets attached in the test. If a test does not call `requestParts(...)` or `responseFields(...)`, the corresponding directory will not contain those files.

Example document `src/docs/asciidoc/products.adoc`:

```adoc
= Product Asset API
:toc: left

== File Upload Errors

=== File Uses Unsupported Media Type

HTTP request:
include::{snippets}/products-upload-unsupported-file-type/http-request.adoc[]

Response:
include::{snippets}/products-upload-unsupported-file-type/http-response.adoc[]

Error fields:
include::{snippets}/products-upload-unsupported-file-type/response-fields.adoc[]

=== File Exceeds Size Limit

HTTP request:
include::{snippets}/products-upload-file-too-large/http-request.adoc[]

Response:
include::{snippets}/products-upload-file-too-large/http-response.adoc[]

Error fields:
include::{snippets}/products-upload-file-too-large/response-fields.adoc[]
```

You can include `request-parts.adoc` if you need to show the multipart structure of the failing request. Weigh the level of detail worth publishing; not every error section needs to repeat the entire request contract.

### 10.1. Documenting Limits in a Table

Add a static or centrally maintained contract section:

```adoc
=== Supported File Rules

|===
|Rule |Value

|Media type
|`image/png`, `image/jpeg`

|Maximum size per file
|5 MiB

|Unsupported file type
|HTTP `415`, code `UNSUPPORTED_FILE_TYPE`

|Oversized file
|HTTP `413`, code `FILE_TOO_LARGE`
|===
```

This table states the policy for clients. To prevent stale documentation, values must be reviewed alongside validation/configuration and tests. Error response snippets prove the test response; they do not automatically pull the 5 MiB limit from application config.

## 11. Testing Container and Reverse Proxy Limits

Upload limits can be enforced at multiple layers:

1. Business validation in the controller/service.
2. Multipart resolver and servlet container.
3. Reverse proxy, ingress, or API gateway.
4. Storage infrastructure or file-scanning services.

MockMvc is suitable for verifying business validation because requests pass through mock MVC. However, if a request exceeds `spring.servlet.multipart.max-file-size`, the servlet container may reject it right at the multipart parsing step. MockMvc does not guarantee identical reproduction of a real container across all configurations.

To test those limits:
- Run the application with an embedded server and real multipart configuration.
- Send HTTP requests through an integration client, such as `WebTestClient` against a running server or REST Assured.
- Verify status/error body at the layer that actually returns the response.
- If a proxy/gateway owns the limit, test in an environment containing that proxy/gateway.

Do not assume every layer returns the same JSON error body. The container or proxy may return a different response than `@RestControllerAdvice`; if a uniform error contract is desired, configure error handling at the proper layer.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `text/plain` file is accepted | Missing MIME allowlist check | Add validation and 415 test |
| Fake PNG file is still accepted | Trusting only `getContentType()` or filename | Check bytes/signature and test content |
| MockMvc test fails to reproduce container 413 | Request blocked before MVC in real environment | Add integration test running server with multipart limit |
| Oversized file returns 400 instead of 413 | Inconsistent exception mapping | Standardize error mapping per contract |
| Error response has new field breaking snippet | Strict `responseFields(...)` detects undocumented field | Add descriptor or intentionally ignore |
| `requestParts(...)` reports missing part in error test | Error fixture does not send all required part descriptors | Send other valid parts or mark optional per contract |
| Error body is not JSON | Container/proxy returns HTML or empty body | Document actual response from the originating layer |
| Returning `415` for spoofed MIME file | Confusing declared media type with file content | Separate unsupported media type from invalid file content |
| Limits in docs drift from config | Editing one place and forgetting the other | Manage contract centrally and test boundaries |
| Test creating huge byte arrays slows down | Using files much larger than threshold | Create only `maxBytes + 1` for business validation |

## 13. Build and CI

With Gradle and the Asciidoctor plugin configured, the documentation task must depend on snippet-generating tests:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

CI flow:

```text
Multipart negative tests
        |
        +--> Unsupported MIME type -> 415
        |
        +--> File exceeds business size -> 413
        |
        +--> Spoofed MIME / corrupted content -> error per contract
        |
        v
Spring REST Docs generates request/response snippets
        |
        v
Asciidoctor / Markdown conversion step
        |
        v
Verify and publish documentation
```

If you have integration tests verifying container/proxy limits, run them in the appropriate profile or stage. Those tests should confirm responses from a real environment, while MockMvc tests continue checking business validation and generating stable snippets.

Spring REST Docs generates AsciiDoc snippets by default. If the project publishes Markdown, a custom template or conversion step is required; `.md` snippets are not generated by default.

## 14. Practice Exercise

With the `POST /api/products/{id}/assets` endpoint:

1. Define an allowlist of `image/png` and `image/jpeg`, and choose a 5 MiB limit per file.
2. Write a test sending `text/plain` and assert error code `UNSUPPORTED_FILE_TYPE`, status 415.
3. Write a test using `maxBytes + 1` to verify business size validation, status 413.
4. Send MIME `image/png` with text bytes; verify the API detects invalid content and returns a distinct error code.
5. Add `requestParts(...)` and `responseFields(...)` to generate snippets for both error responses.
6. Include request, response, and error fields in Asciidoctor.
7. Run an integration test against an embedded server to confirm the servlet container multipart limit; compare the response with business validation.
8. Update the policy table when changing the allowlist or limits; re-run tests and CI builds.

### Self-Assessment Questions

- How does the multipart request's Content-Type differ from the file part's Content-Type?
- Why don't a `.png` filename and `image/png` header prove the bytes are PNG?
- When should 415 be returned versus an invalid file content error?
- What two targets do `max-file-size` and `max-request-size` limit?
- Why doesn't a MockMvc business size test replace a container integration test?
- What do `requestParts(...)` and `responseFields(...)` contribute to upload error documentation?
- If a proxy returns 413 before the request reaches the controller, can `@RestControllerAdvice` handle that response?
- How do you keep limit tables in documentation synchronized with validation and configuration?

**Remember:** Documenting upload errors requires clearly stating accepted media types, size limits, and error response structure. Use MockMvc tests for application-checked rules and Spring REST Docs to generate request/response snippets; test separately through a real server or proxy when limits are enforced before MVC. MIME headers, filenames, and file bytes are three distinct pieces of information that must be verified at the appropriate layer.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): documenting request parts.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): request/response fields and payload snippets.
- [Spring Framework — `MultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): size, content type, filename, and file bytes.
- [Spring Boot — Servlet Web Server](https://docs.spring.io/spring-boot/reference/web/servlet.html): servlet application configuration; also see multipart properties for your project's Boot version.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): definitions of status 413 Content Too Large and 415 Unsupported Media Type.
