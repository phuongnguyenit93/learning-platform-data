# `@RequestPart` for a JSON Part in Multipart

A file upload API often needs to receive both structured data and binary content simultaneously. For example, a user submits document details such as title, document category, and effective date as JSON alongside a PDF file. With Spring MVC, you can declare each part using `@RequestPart`: Spring uses an `HttpMessageConverter` to convert the JSON part into a Java object and binds the file part to `MultipartFile`.

When using `springdoc-openapi`, the request body should be described as `multipart/form-data`, where each part is a property of the schema. The JSON part should be advertised with content type `application/json`; the file part needs a `string` schema with format `binary`. These two descriptions help Swagger UI and client generators understand the multipart structure.

## 1. Multipart consists of parts with separate content types

A `multipart/form-data` request is divided into multiple parts. Each part has a name, its own headers, and its own content. The browser or HTTP client sends a boundary to separate the parts.

Example of a document upload request with two parts:

| Part name | Content-Type | Content | Java receiving type |
| --- | --- | --- | --- |
| `metadata` | `application/json` | JSON containing title, document category, and business details | `DocumentMetadata` |
| `file` | `application/pdf` or supported file type | Bytes of the uploaded file | `MultipartFile` |

The overall HTTP request has media type `multipart/form-data`. Individual parts can have different media types. This is why the JSON part must be sent with `Content-Type: application/json` so Spring selects the appropriate JSON converter.

## 2. Distinguishing `@RequestPart` and `@RequestParam`

Both annotations can appear in the same endpoint, yet they serve different binding mechanisms:

| Annotation | Primary processing | Suitable use case |
| --- | --- | --- |
| `@RequestPart` | Reads the part and uses `HttpMessageConverter` based on the part's content type to convert to the target type | JSON/XML or structured content inside multipart; files bound to `MultipartFile`. |
| `@RequestParam` | Binds request parameters or multipart fields via Spring's conversion mechanism | Simple fields like `String`, numbers, Booleans; can also be used with `MultipartFile`. |

For a JSON part that needs deserialization into a DTO and Bean Validation, `@RequestPart` expresses intent more clearly:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<Void> upload(
    @Valid @RequestPart("metadata") DocumentMetadata metadata,
    @RequestPart("file") MultipartFile file
) {
    documentService.upload(metadata, file);
    return ResponseEntity.accepted().build();
}
```

Spring reads the part named `metadata`, checks the part's `Content-Type`, and uses the matching converter to construct `DocumentMetadata`. The `file` part is bound as `MultipartFile`. If JSON is sent as a plain string with `@RequestParam String metadata`, the application has to parse that string manually; when direct JSON deserialization is needed, `@RequestPart` is the natural choice.

## 3. Creating a DTO for the JSON part

Define a DTO describing the metadata to submit:

```java
public enum DocumentCategory {
    CONTRACT,
    INVOICE,
    REPORT
}

public record DocumentMetadata(
    @NotBlank
    @Size(max = 120)
    String title,

    @NotNull
    DocumentCategory category,

    @PastOrPresent
    LocalDate effectiveDate
) {}
```

When the JSON part is converted into the DTO, Jackson handles deserialization and Bean Validation checks constraints if the controller attaches `@Valid` and the application has a validation provider configured. `@NotBlank`, `@Size`, `@NotNull`, and `@PastOrPresent` enforce data conditions at runtime; springdoc can reflect several of these constraints in the OpenAPI schema.

The JSON part must match the DTO structure, for example:

```json
{
  "title": "Sales contract",
  "category": "CONTRACT",
  "effectiveDate": "2026-11-20"
}
```

If `effectiveDate` is sent as a date string, Jackson's Java Time configuration must support `LocalDate`. JSON formatting and query parameter formatting use different conversion mechanisms; `@DateTimeFormat` on a query parameter does not replace Jackson configuration for a JSON body.

## 4. Declaring a controller receiving a JSON part and a file part

A Spring MVC endpoint can receive both parts as follows:

```java
@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private final DocumentService documentService;

    DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Upload document with JSON metadata")
    ResponseEntity<DocumentResponse> upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("file") MultipartFile file
    ) {
        DocumentResponse created = documentService.upload(metadata, file);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Key details:

- `consumes = MediaType.MULTIPART_FORM_DATA_VALUE` restricts the endpoint to accept overall requests with media type `multipart/form-data`.
- `@RequestPart("metadata")` requires a part named `metadata`; Spring converts the JSON part into `DocumentMetadata`.
- `@Valid` triggers validation for the DTO after successful deserialization, provided method validation/Bean Validation is properly configured.
- `@RequestPart("file")` binds the part named `file` into `MultipartFile`.
- `HttpStatus.CREATED` determines the actual response; OpenAPI annotations describe the corresponding response for clients.

The name in `@RequestPart` must match the exact part name sent by the client. If the client sends `document` while the controller expects `metadata`, Spring cannot find the part and the request fails.

## 5. Describing the multipart schema in OpenAPI

Springdoc can infer the request body from `@RequestPart` and `MultipartFile` parameters. When a JSON object part is involved, inspect the generated specification to ensure the schema and encoding are accurate. You can declare the request body explicitly using OpenAPI annotations.

Create a model solely for describing the multipart shape:

```java
@Schema(name = "UploadDocumentMultipart")
public class UploadDocumentMultipartSchema {

    @Schema(description = "Document metadata, sent as JSON")
    public DocumentMetadata metadata;

    @Schema(
        description = "Binary document file",
        type = "string",
        format = "binary"
    )
    public String file;
}
```

This model serves as a documentation schema. The controller still binds data using `@RequestPart` and `MultipartFile`; the `String file` field in the model is not a Java parameter used to read file bytes.

Declare the request body and encoding:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
@Operation(
    summary = "Upload document with JSON metadata",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "Send metadata as JSON and file content in the same request",
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = UploadDocumentMultipartSchema.class),
            encoding = @Encoding(
                name = "metadata",
                contentType = MediaType.APPLICATION_JSON_VALUE
            )
        )
    )
)
ResponseEntity<DocumentResponse> upload(
    @Valid @RequestPart("metadata") DocumentMetadata metadata,
    @RequestPart("file") MultipartFile file
) {
    DocumentResponse created = documentService.upload(metadata, file);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
```

Here:

- `@Content(mediaType = "multipart/form-data")` specifies the media type of the entire request body.
- `@Schema(implementation = UploadDocumentMultipartSchema.class)` publishes the object schema containing `metadata` and `file`.
- `@Encoding(name = "metadata", contentType = "application/json")` describes the `metadata` part as containing JSON.
- `format = "binary"` indicates that the `file` property is binary file content.

OpenAPI annotations live in `io.swagger.v3.oas.annotations.*`. OpenAPI's `@RequestBody` annotation differs from `org.springframework.web.bind.annotation.RequestBody`; the example uses the fully qualified name to avoid confusion.

The OpenAPI specification typically has a structure like:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        properties:
          metadata:
            $ref: '#/components/schemas/DocumentMetadata'
          file:
            type: string
            format: binary
      encoding:
        metadata:
          contentType: application/json
```

Verify that the schema has accurate part names, object/binary types, and JSON encoding for `metadata`. Component names or how springdoc splits schemas may vary by configuration; the structure above illustrates the essential information required.

## 6. Sending requests with `curl`

You can test the endpoint from the terminal using `curl`:

```bash
curl -X POST "http://localhost:8080/api/documents" \
  -F 'metadata={"title":"Sales contract","category":"CONTRACT","effectiveDate":"2026-11-20"};type=application/json' \
  -F 'file=@contract.pdf;type=application/pdf'
```

The `-F` option constructs the parts of a multipart request. The `metadata` part is tagged with `type=application/json` so Spring picks the JSON message converter. The `file` part reads content from `contract.pdf` and attaches the file's content type.

Do not manually set an overall `Content-Type: multipart/form-data` header when using `curl -F`. Curl must generate the header with a `boundary` and use that exact boundary to separate parts. Overriding the header without providing a matching boundary can prevent the server from parsing the request.

## 7. Rendering multipart in Swagger UI

When OpenAPI describes a request body as `multipart/form-data` with an object schema, Swagger UI can render form fields. The `file` property with `type: string` and `format: binary` is usually presented as a file picker. The `metadata` property is an object; encoding `application/json` indicates this part contains JSON.

The exact input UI depends on the bundled Swagger UI version and how the schema is generated. After configuring, open Swagger UI and check:

1. The operation displays the `multipart/form-data` media type.
2. There is a file picker field for the `file` part.
3. Valid JSON data can be entered for the `metadata` part as supported by the UI.
4. The outgoing request has accurate part names and the metadata part carries `Content-Type: application/json`.
5. The server binds the DTO and `MultipartFile` as expected.

If the UI does not render the JSON object field as desired, inspect `/v3/api-docs` first. If the schema and `encoding` are already accurate, the discrepancy may lie in how that Swagger UI version handles multipart input. Use `curl` or an HTTP client to verify the server independently of the UI.

## 8. Validation and file limits

The JSON part and file part should be checked separately because they have different characteristics.

For metadata, use Bean Validation on the DTO:

```java
public record DocumentMetadata(
    @NotBlank @Size(max = 120) String title,
    @NotNull DocumentCategory category
) {}
```

For files, verify at a minimum:

- Whether the file is empty (`file.isEmpty()`).
- Whether the size exceeds business limits (`file.getSize()`).
- Whether the filename and extension comply with policy.
- Whether the content type belongs to the accepted list.
- Whether the actual content matches an allowed format; do not blindly trust client-supplied filenames or headers.

Example basic validation in a service:

```java
void validateFile(MultipartFile file) {
    if (file.isEmpty()) {
        throw new InvalidUploadException("File must not be empty");
    }

    if (file.getSize() > 10 * 1024 * 1024) {
        throw new InvalidUploadException("File exceeds 10 MB");
    }

    if (!MediaType.APPLICATION_PDF_VALUE.equals(file.getContentType())) {
        throw new InvalidUploadException("Only PDF is accepted");
    }
}
```

This is only basic checking. `getContentType()` reads client-provided metadata and can be spoofed; systems should inspect file signatures or use a proper format-analysis library before processing contents. Overall multipart limits should also be configured in Spring Boot, such as `spring.servlet.multipart.max-file-size` and `spring.servlet.multipart.max-request-size` in Servlet MVC applications.

## 9. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Missing `metadata` part | Part name mismatches `@RequestPart` | Synchronize names across controller, client, and OpenAPI schema. |
| JSON part fails to deserialize | Part lacks `Content-Type: application/json`, malformed JSON, or incompatible DTO | Check part headers, payload, and Jackson configuration. |
| `415 Unsupported Media Type` error | No converter matches the part or overall request content type | Check `consumes`, per-part content types, and message converters. |
| `400 Bad Request` error | Missing required part, invalid JSON, or validation failure | Check request, `@Valid`, and how the app maps errors. |
| Swagger UI shows file as a plain string | File schema lacks `format: binary` | Declare the file property as `type: string`, `format: binary`. |
| Swagger UI sends metadata as `text/plain` | JSON part encoding not described or UI handles it inadequately | Check `encoding.metadata.contentType` in OpenAPI and test with curl. |
| Request exceeds size limit | Multipart configuration or gateway/proxy limit is lower than file size | Align limits across application, reverse proxy, and infrastructure. |

## 10. Rules of thumb

- Use `consumes = multipart/form-data` on endpoints receiving multiple parts.
- Use `@RequestPart` when a JSON part must be converted into a DTO via `HttpMessageConverter`.
- Attach `@Valid` to JSON DTOs and declare appropriate constraints.
- Describe the request body as a multipart object; file parts use `type: string`, `format: binary`.
- Use `@Encoding` to publish the dedicated `contentType` for JSON parts.
- Verify `/v3/api-docs`, Swagger UI, and real requests using an HTTP client.
- Verify file contents and size limits at runtime; do not rely on client-declared schemas or content types.

`@RequestPart` connects each part of a multipart request to its corresponding Java type. When schemas and encodings are accurately described in OpenAPI, clients clearly understand which JSON part to send, which file part to attach, and each part's content type. API reliability still depends on the server deserializing, validating, and inspecting files in accordance with the published contract.

## References

- [Spring Framework – Multipart Resolver and `@RequestPart`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [OpenAPI Specification – Multipart Request Body](https://spec.openapis.org/oas/latest.html)
- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
- [Swagger Annotations – `@Content`, `@Encoding`, and `@Schema`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
