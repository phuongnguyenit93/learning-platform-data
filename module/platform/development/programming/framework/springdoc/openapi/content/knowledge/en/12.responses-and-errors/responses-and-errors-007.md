# File Downloads, Binary Data, and `Content-Disposition`

Not every API response is JSON. Many endpoints need to return PDF, images, CSV, Excel, ZIP, or a binary data stream. In Spring Boot, a controller can return data as `Resource`, `byte[]`, or `StreamingResponseBody`; the HTTP response must set the right media type and headers describing how browsers should handle the file. In an OpenAPI document, the response body is described by its media type and binary schema, while `Content-Disposition` is declared as a response header.

With `springdoc-openapi`, documenting these details clearly helps Swagger UI, client generators, and API consumers understand how the endpoint serves files. The contract must also describe error responses, because a file-download endpoint can still return `404`, `403`, or server errors as JSON.

## 1. File-Download Responses Differ from JSON Responses

A JSON response typically has a body containing an object or array serialized from a DTO. A file-download response has a body consisting of raw file bytes. Example:

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-2026.pdf"
Content-Length: 48291

%PDF-1.7...
```

Key headers:

| Header | Role |
|---|---|
| `Content-Type` | Indicates the content's media type, e.g., `application/pdf`, `text/csv`, or `application/octet-stream` |
| `Content-Disposition` | Hints whether browsers should display inline or download, and can suggest a filename |
| `Content-Length` | Indicates body size in bytes when known |
| `Cache-Control` | Controls caching; especially important for private documents |
| `Content-Range` | Describes the byte range returned in a partial response |
| `Accept-Ranges` | Indicates the server supports byte-range requests when actually implemented |

`Content-Disposition` is HTTP response metadata, not part of the file content or body schema. Likewise, `Content-Type` is represented under `content` of the OpenAPI Response Object via media types rather than being redeclared as a regular header.

## 2. Choosing a Return Type in Spring MVC

Spring MVC supports several response return types. Your choice depends on file size, data source, and how the application manages streams.

| Return type | Suitable when | Notes |
|---|---|---|
| `ResponseEntity<Resource>` | File resides on the filesystem, storage, or a source representable as `Resource` | Can supply content type, content length, and disposition via headers |
| `ResponseEntity<byte[]>` | Small content already loaded in memory | Simple, though all bytes reside in heap memory |
| `ResponseEntity<ByteArrayResource>` | Small data already available as a byte array while preferring the `Resource` abstraction | Still consumes memory proportional to file size |
| `ResponseEntity<InputStreamResource>` | Data is read from an existing stream | Stream is typically single-read; take care when calculating content length |
| `ResponseEntity<StreamingResponseBody>` | Large files or data generated/read sequentially | Writes directly to the output stream without holding the entire file in heap |

For large files, avoid loading the entire content into a `byte[]` just to return the response. Use `FileSystemResource` or `StreamingResponseBody` to reduce memory pressure. With single-read streams, avoid calling operations that might consume the stream before the response is written.

## 3. `Content-Disposition`: `attachment` and `inline`

The `Content-Disposition` header describes how content is delivered in the HTTP response.

### `attachment`

`attachment` tells the browser to treat the content as a file to download. The `filename` parameter suggests a file name:

```http
Content-Disposition: attachment; filename="report.csv"
```

This is a common choice for endpoints serving reports, invoices, backups, or documents users should save locally.

### `inline`

`inline` allows the browser to render the content directly inside the window if the browser supports that media type:

```http
Content-Disposition: inline; filename="manual.pdf"
```

For example, PDFs or images can be displayed directly. `inline` is only a presentation hint; the browser, plugins, security policies, and `Content-Type` still determine actual rendering behavior.

### Filenames and Unicode Characters

Filenames may contain Vietnamese diacritics or non-ASCII characters. Encode them properly per HTTP rules, typically via the `filename*` parameter under RFC 5987/RFC 6266 alongside a fallback `filename` when needed. Never build header strings by concatenating unvalidated filenames directly.

Spring provides the `ContentDisposition` builder to construct the header:

```java
import org.springframework.http.ContentDisposition;
import java.nio.charset.StandardCharsets;

ContentDisposition disposition = ContentDisposition.attachment()
        .filename("hoa-don-thang-11.pdf", StandardCharsets.UTF_8)
        .build();

String headerValue = disposition.toString();
```

The builder handles filename formatting according to framework rules. Test the actual header with your target browsers and clients, especially when full Unicode filenames are needed.

## 4. Returning Files with `ResponseEntity<Resource>`

This is a common approach when files already exist on the filesystem or in a storage abstraction. The example below assumes `fileService` checks access permissions and supplies metadata plus a readable `Resource`.

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DocumentController {

    private final FileService fileService;

    DocumentController(FileService fileService) {
        this.fileService = fileService;
    }

    @GetMapping("/api/files/{fileId}/download")
    ResponseEntity<Resource> download(@PathVariable UUID fileId) throws IOException {
        StoredFile file = fileService.findReadableFile(fileId);
        Resource resource = fileService.openResource(fileId);

        if (!resource.exists() || !resource.isReadable()) {
            throw new FileNotFoundException("File not found");
        }

        String safeName = safeDownloadName(file.downloadName());
        ContentDisposition disposition = ContentDisposition.attachment()
                .filename(safeName, StandardCharsets.UTF_8)
                .build();

        MediaType mediaType = MediaType.parseMediaType(file.contentType());

        return ResponseEntity.ok()
                .contentType(mediaType)
                .contentLength(resource.contentLength())
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .body(resource);
    }

    private String safeDownloadName(String suppliedName) {
        if (suppliedName == null || suppliedName.isBlank()) {
            return "download.bin";
        }
        String leaf = suppliedName.replace('\\', '/');
        leaf = leaf.substring(leaf.lastIndexOf('/') + 1);
        leaf = leaf.replaceAll("[\\r\\n\\p{Cntrl}]", "_").trim();
        return leaf.isBlank() ? "download.bin" : leaf;
    }
}
```

`FileService` and `StoredFile` are illustrative application types; `FileNotFoundException` is a standard JDK exception. In real implementations:

- `findReadableFile` must verify the user has permission to read the file.
- Public IDs should map to storage locations through the service; never accept arbitrary filesystem paths from requests.
- Filenames must be sanitized before placing them in headers, stripping paths and control characters.
- `contentType` must come from trusted metadata or content inspection rules; never blindly trust user-uploaded values.
- Set `Content-Length` only when the exact size is known without accidentally consuming the stream.

If the file type is fixed, you can declare `produces`, such as `produces = MediaType.APPLICATION_PDF_VALUE`. If an endpoint serves multiple file types based on metadata, choose the content type at runtime and document all supported media types in OpenAPI.

## 5. Returning Small Payloads with `byte[]`

When content is small and already generated in memory, you can return `byte[]` directly:

```java
@GetMapping("/api/reports/summary")
ResponseEntity<byte[]> downloadSummary() {
    byte[] content = reportService.createSummaryCsv();

    ContentDisposition disposition = ContentDisposition.attachment()
            .filename("summary.csv", StandardCharsets.UTF_8)
            .build();

    return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/csv"))
            .contentLength(content.length)
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .body(content);
}
```

`byte[]` is easy to use and its length is immediately available for `Content-Length`. However, the file is held in application memory; with many concurrent requests or large files, total heap usage can spike quickly. Use this only when sizes are appropriately bounded.

## 6. Streaming Large Files with `StreamingResponseBody`

`StreamingResponseBody` writes data incrementally to the response output stream. Example:

```java
@GetMapping("/api/exports/{exportId}/download")
ResponseEntity<StreamingResponseBody> downloadExport(
        @PathVariable UUID exportId) {

    ExportMetadata metadata = exportService.getReadableExport(exportId);
    StreamingResponseBody body = outputStream ->
            exportService.copyTo(exportId, outputStream);

    ContentDisposition disposition = ContentDisposition.attachment()
            .filename(safeDownloadName(metadata.fileName()), StandardCharsets.UTF_8)
            .build();

    return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(metadata.contentType()))
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .body(body);
}
```

The example omits `Content-Length` because the size may not be known ahead of time. When the server and data source know the exact size, you can set that header; otherwise let the HTTP server manage response framing.

When streaming:

- Do not close the `OutputStream` supplied by Spring; the framework manages the stream lifecycle.
- Close source streams inside the service using try-with-resources.
- Handle read/write errors and log without exposing sensitive data.
- Never set status `200` and only check access permissions inside the callback; complete authentication and authorization before writing the body starts.
- Configure executors and timeouts suitable for download durations.
- Test concurrent downloads, client disconnects, and mid-stream failures.

With `InputStreamResource`, keep in mind that the stream may be single-read. Calling `contentLength()` in framework or application code can consume the stream depending on the resource type. For files on disk, `FileSystemResource` is usually preferable because it can access metadata and open streams on demand.

## 7. Describing Binary Responses in OpenAPI

OpenAPI describes response bodies by media type. For OpenAPI 3.0 documents, the common convention for binary file content is schema `type: string`, `format: binary`.

PDF response example:

```yaml
paths:
  /api/files/{fileId}/download:
    get:
      summary: Download PDF file
      parameters:
        - name: fileId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: PDF file content
          headers:
            Content-Disposition:
              description: Suggested filename for download
              schema:
                type: string
                example: 'attachment; filename="invoice.pdf"'
            Content-Length:
              description: Body size in bytes if provided
              schema:
                type: integer
                format: int64
          content:
            application/pdf:
              schema:
                type: string
                format: binary
        '404':
          description: File not found
```

For arbitrary files without a specific media type, use `application/octet-stream`. For CSV, use `text/csv`; for ZIP, use `application/zip`; for images, use the appropriate media type such as `image/png`.

In OpenAPI 3.1, the Schema Object is based on JSON Schema 2020-12, and describing binary content differs from OpenAPI 3.0's `format: binary` convention. Keywords such as `contentMediaType` and `contentEncoding` describe the media type or encoding of string-encoded content where applicable; they do not replace the response media type under `content`. Support across Swagger UI, validators, and client generators also varies; verify the actual OpenAPI version emitted by springdoc alongside your project toolchain.

## 8. Declaring Binary Responses and Headers with Springdoc Annotations

You can document file responses directly on controllers using `@ApiResponse`, `@Content`, `@Schema`, and `@Header`.

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.headers.Header;

@Operation(summary = "Download PDF invoice")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "PDF invoice content",
        headers = {
            @Header(
                name = "Content-Disposition",
                description = "Filename used by browsers when downloading",
                schema = @Schema(
                    type = "string",
                    example = "attachment; filename=\"invoice.pdf\""
                )
            ),
            @Header(
                name = "Content-Length",
                description = "Content size in bytes",
                schema = @Schema(type = "integer", format = "int64")
            )
        },
        content = @Content(
            mediaType = "application/pdf",
            schema = @Schema(type = "string", format = "binary")
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Invoice not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(responseCode = "403", description = "Not authorized to download invoice")
})
@GetMapping("/api/invoices/{invoiceId}/download")
ResponseEntity<Resource> downloadInvoice(@PathVariable UUID invoiceId) {
    // Retrieve Resource and return with appropriate Content-Type and Content-Disposition.
    throw new UnsupportedOperationException("Illustrative example");
}
```

`ApiError` is an illustrative application error DTO. Key points to note:

- `content` describes the body per media type; `application/pdf` or `application/octet-stream` is the media type key.
- The binary `schema` describes file content; do not use a JSON DTO schema for a binary body.
- `headers` describes `Content-Disposition` and `Content-Length` if the endpoint provides them.
- `Content-Type` is already represented by the media type key in `content`; do not duplicate it as a normal header.
- Error responses can have their own JSON schemas, independent of the file-based success response.

If a controller returns `Resource`, springdoc may infer a response that does not match file semantics in certain configurations or versions. Declare the response explicitly and inspect the generated JSON/YAML to confirm the schema is binary.

## 9. Safe Filenames and Preventing Header Injection

Never take an arbitrary filename string directly from a request and interpolate it into `Content-Disposition`. Filenames can contain path separators, newline characters, or control characters. Placing unsafe input into headers can corrupt headers or open response-splitting risks.

Guidelines:

- Storage names and file paths must be managed by the server; clients should only select files via IDs or validated identifiers.
- Strip paths (`../`, `\\`, `/`) from display names; keep only the leaf filename, and never use that display name to resolve storage paths.
- Remove CR, LF, and control characters.
- Use the `ContentDisposition` builder instead of concatenating header strings manually.
- Provide a fallback name if the filename is blank or invalid.
- Never leak absolute paths, internal buckets, or storage details in response headers.
- Do not trust file extensions to determine content; verify media types from trusted metadata or actual content.

Sanitizing the filename in the example only protects the display name. File access authorization and path-traversal prevention must be enforced in the storage/service layer where IDs map to authorized file objects.

## 10. Media Types and Downloaded Content

`Content-Type` must reflect the actual content type. Common media types:

| File type | Common media type |
|---|---|
| PDF | `application/pdf` |
| CSV | `text/csv` |
| ZIP | `application/zip` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| JSON | `application/json` |
| Unspecified binary | `application/octet-stream` |

If the media type is uncertain, `application/octet-stream` is the generic choice for binary data. Do not use `application/octet-stream` for every file when the application knows the exact content type and browsers need to render it inline.

With `inline`, browsers typically need the exact media type to render content. For example, PDFs require `application/pdf`; returning `application/octet-stream` causes many browsers to download the file instead of displaying it directly.

## 11. CORS and Reading Filenames from JavaScript

When frontend and API sit on different origins, browsers receive `Content-Disposition`, but JavaScript cannot read that header unless the server exposes it via CORS.

Configuration example:

```http
Access-Control-Expose-Headers: Content-Disposition, Content-Length
```

In Spring MVC, declare this through `CorsConfiguration` or the endpoint's CORS configuration. `Access-Control-Expose-Headers` only affects whether JavaScript can read response headers; it does not decide whether the browser triggers a download.

Frontends using `fetch` typically read the response body as a `Blob`, create a temporary object URL, and trigger the download. To obtain the server-suggested filename, the frontend reads `Content-Disposition` after it is exposed. Handle both `filename` and `filename*` for full Unicode support.

## 12. Error Responses on File-Download Endpoints

File-download endpoints can still return standard errors:

| Status | Scenario |
|---|---|
| `400 Bad Request` | Invalid ID or parameters |
| `401 Unauthorized` | Unauthenticated |
| `403 Forbidden` | User lacks permission to read the file |
| `404 Not Found` | File does not exist or is not visible to the caller |
| `416 Range Not Satisfiable` | Requested byte range is invalid when the server supports ranges |
| `500 Internal Server Error` | Error retrieving or generating file content |

Errors should be returned using the API's consistent error representation, such as `application/problem+json` or a dedicated error DTO. Do not return an HTML error page from a reverse proxy when clients expect a JSON error schema, unless that is a documented gateway policy.

Never start streaming the body before checking permissions or verifying that the file exists. Complete authentication, authorization, and metadata checks before sending the `200 OK` headers; once the body stream begins, the server cannot cleanly switch the response to error JSON.

## 13. Supporting Byte-Range Downloads

For large files or seekable media, clients may send a `Range` header to request a slice of data. If the server supports it, the response can be `206 Partial Content` with `Content-Range`, and possibly `Accept-Ranges: bytes`.

Partial response example:

```http
HTTP/1.1 206 Partial Content
Content-Type: video/mp4
Accept-Ranges: bytes
Content-Range: bytes 0-999/5000
Content-Length: 1000

...first 1000 bytes...
```

Do not declare `206` or `Accept-Ranges` in documentation merely because a file is readable as a `Resource`. The endpoint must genuinely handle `Range` requests and return the exact byte segments and headers. If range requests are not implemented, document only the full `200` response.

When supporting ranges, add `206` and `416` responses to OpenAPI and test valid ranges, out-of-bounds ranges, and multi-range requests according to what the server supports.

## 14. Security and Caching for Downloads

Files can contain personal data, contracts, financial reports, or internal records. Download endpoints must enforce the same authorization policies as corresponding data-read endpoints.

- Authenticate callers and verify permissions on the specific requested file.
- Never allow clients to supply arbitrary filesystem paths or object storage keys.
- Never rely on predictable sequential IDs as the sole access control; always verify ownership and access rights.
- For sensitive files, consider `Cache-Control: private, no-store` per security policy.
- Never log file contents, tokens, or sensitive information.
- Validate media types and actual contents, especially for user-uploaded files.
- Do not use `inline` for untrusted content if browsers could execute or render malicious payloads unexpectedly.
- When using time-limited signed URLs, restrict expiration time, file scope, and permissions.

`Content-Disposition: attachment` reduces the chance of direct browser rendering, but it never replaces content validation, access checks, or appropriate security headers.

## 15. Testing File-Download Responses

After implementing the endpoint, verify the body, headers, and OpenAPI documentation:

1. Call the endpoint with a valid file and confirm status `200`.
2. Verify `Content-Type` matches the actual content.
3. Verify `Content-Disposition` specifies `attachment` or `inline` as required and includes a valid filename.
4. If `Content-Length` is present, compare it against the actual byte count received.
5. Open the downloaded file in an appropriate application to verify it is neither truncated nor corrupted.
6. Test Unicode filenames across target browsers.
7. Call as an unauthorized user and confirm the expected error response.
8. If using CORS, confirm JavaScript can read `Content-Disposition` when needed.
9. If streaming, test large files, client disconnects, and concurrent requests.
10. If supporting ranges, test `206`, `Content-Range`, and `416`.
11. Download `/v3/api-docs` or `/v3/api-docs.yaml`, confirming the success response has a binary media type, documented headers, and error responses with appropriate schemas.
12. Verify Swagger UI and your client generator handle the binary response as expected.

HTTP tools such as curl can inspect headers and save the body:

```bash
curl -fS -D response-headers.txt \
  http://localhost:8080/api/files/550e8400-e29b-41d4-a716-446655440000/download \
  -o downloaded-file.pdf
```

`-D` saves response headers so you can inspect `Content-Type` and `Content-Disposition`; `-o` writes the body to a file. If the endpoint requires a bearer token, include the `Authorization` header per your security configuration.

## 16. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Downloaded file has a random or wrong name | Missing `Content-Disposition` or improperly encoded filename | Use `ContentDisposition` builder and inspect headers |
| Browser renders PDF instead of downloading | Using `inline` or missing attachment disposition | Set `Content-Disposition: attachment` when download is desired |
| File is corrupted | Wrong content type, stream already read, missing bytes, or stream closed early | Check data source and stream lifecycle |
| Large files spike heap memory | Loading the entire file into `byte[]` | Use `Resource` or `StreamingResponseBody` |
| Wrong `Content-Length` | Computed from a non-rereadable stream or set inaccurately | Set only when byte count is known for certain |
| Garbled Unicode filename | Incompatible header encoding or client behavior | Use UTF-8 builder and test `filename*` in target browsers |
| Swagger UI documents body as an object | Springdoc inferred from return type instead of desired binary schema | Declare `@ApiResponse` and `@Content` explicitly |
| Client cannot read filename via fetch | CORS does not expose `Content-Disposition` | Configure `Access-Control-Expose-Headers` |
| Unauthorized access to private files | Checking ID only or skipping file-level authorization | Enforce authorization in the service before opening the stream |
| Broken header with special filenames | Concatenating untrusted input directly into header string | Sanitize names and use `ContentDisposition` |

## 17. Design Principles

- Use `Resource` or streaming for large files; use `byte[]` only when size is bounded.
- Choose `Content-Type` matching actual content; use `application/octet-stream` when no specific type applies.
- Use `attachment` to trigger downloads and `inline` when browsers should attempt rendering.
- Build `Content-Disposition` with Spring's `ContentDisposition` builder, supporting UTF-8 filenames and sanitizing names before adding them to headers.
- Set `Content-Length` only when the size is exact and obtaining it does not consume the stream.
- Describe binary bodies by media type in OpenAPI; describe `Content-Disposition` as a response header.
- Document JSON error responses separately from file-based success responses.
- Do not declare range responses unless the server genuinely supports byte ranges.
- Check access permissions before sending any body bytes; never let clients pick storage paths.
- Keep OpenAPI schemas, runtime headers, and browser/client download behavior synchronized.

## Conclusion

File-download endpoints must deliver exact byte content alongside accurate `Content-Type` and `Content-Disposition` headers. Spring MVC can use `Resource`, `byte[]`, or `StreamingResponseBody` depending on size and data source. springdoc-openapi documents the body using media types with binary schemas, while `Content-Disposition` and other headers are declared in the Response Object. During implementation, sanitize filenames safely, support UTF-8, enforce authorization before streaming, and verify both headers and actual contents so the OpenAPI contract matches what clients receive.
