# Documenting Multipart Uploads with Request Parts

## 1. Capstone Problem

A document management API allows clients to upload a file along with metadata describing that file. The request uses `multipart/form-data` with two parts:

- `file`: binary file content, for example a PDF.
- `metadata`: JSON describing the display title, document category, and tags.

Example request:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="file"; filename="contract.pdf"
Content-Type: application/pdf

<binary file bytes>
--...
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Service Contract",
  "category": "LEGAL",
  "tags": ["signed", "customer"]
}
--...--
```

If you only document the overall request body, readers cannot easily tell what each part is named, which media type it expects, which part is required, or which fields the JSON metadata contains. Spring REST Docs provides request parts and request part descriptors to document each part of a multipart request.

The **SPRING_REST_DOCS** module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests generate request, response, payload, parameter, and header snippets, which are then assembled into Asciidoctor/Markdown and integrated into the build and CI. This lesson belongs to the **Capstone Practice** chapter, combining multipart requests, part metadata, validation, and upload contract documentation.

After this lesson, you will build a multipart request containing a file and JSON metadata, document the name/description/required status of each part, document fields inside the JSON part, inspect part headers/payloads, and assemble snippets into Asciidoctor.

## 2. Designing the Upload API

Endpoint:

```http
POST /api/documents
Content-Type: multipart/form-data
```

| Part | Content type | Required | Meaning |
| --- | --- | --- | --- |
| file | application/pdf | Yes | PDF file to store |
| metadata | application/json | Yes | Document metadata |

Metadata:

```json
{
  "title": "Service Contract",
  "category": "LEGAL",
  "tags": ["signed", "customer"]
}
```

Success response:

```http
HTTP/1.1 201 Created
Location: /api/documents/doc-1001
Content-Type: application/json

{
  "id": "doc-1001",
  "title": "Service Contract",
  "fileName": "contract.pdf",
  "contentType": "application/pdf",
  "size": 24576
}
```

The examples use fake filenames and data. Do not use real customer documents or sensitive content in documentation tests.

## 3. Controller Receiving Request Parts

Metadata DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

public record DocumentMetadata(
        @NotBlank @Size(max = 120) String title,
        @NotBlank String category,
        @NotEmpty List<@NotBlank String> tags
) {}
```

Response DTO:

```java
public record DocumentResponse(
        String id,
        String title,
        String fileName,
        String contentType,
        long size
) {}
```

Controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import java.net.URI;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<DocumentResponse> upload(
            @RequestPart("file") MultipartFile file,
            @Valid @RequestPart("metadata") DocumentMetadata metadata) {

        DocumentResponse result = new DocumentResponse(
                "doc-1001", metadata.title(), file.getOriginalFilename(),
                file.getContentType(), file.getSize());
        return ResponseEntity.created(
                URI.create("/api/documents/" + result.id())).body(result);
    }
}
```

This controller illustrates the contract. A real application needs to validate size limits, content types, file signatures, filenames, and store files securely. REST Docs records the behavior verified by tests; it does not perform those security checks itself.

## 4. Preparing the MockMvc Test

With Spring MVC, create a `MockMultipartFile` for each part. The `file` part carries file bytes; the `metadata` part carries JSON bytes and content type `application/json`.

```java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Setting up MockMvc:

```java
@ExtendWith(RestDocumentationExtension.class)
class DocumentUploadDocumentationTests {
    @Autowired WebApplicationContext context;
    MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Creating parts:

```java
MockMultipartFile filePart = new MockMultipartFile(
        "file", "contract.pdf", MediaType.APPLICATION_PDF_VALUE,
        "fake-pdf-content".getBytes(StandardCharsets.UTF_8));

MockMultipartFile metadataPart = new MockMultipartFile(
        "metadata", "", MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "title": "Service Contract",
          "category": "LEGAL",
          "tags": ["signed", "customer"]
        }
        """.getBytes(StandardCharsets.UTF_8));
```

In this example, the file bytes are fake data so there is no need to commit a real PDF. If the endpoint checks the PDF signature, the fixture must be a valid test PDF containing no sensitive data.

## 5. Documenting Request Parts

`requestParts(...)` describes the parts of a multipart request:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

mockMvc.perform(multipart("/api/documents")
        .file(filePart)
        .file(metadataPart))
    .andExpect(status().isCreated())
    .andDo(document("documents/upload",
        requestParts(
            partWithName("file").description("PDF file to upload"),
            partWithName("metadata").description("JSON metadata of the document")
        )
    ));
```

The `request-parts.adoc` snippet lists the documented parts. Parts are required by default; optional parts need to be marked:

```java
requestParts(
    partWithName("file").description("PDF file to upload"),
    partWithName("metadata").description("JSON metadata of the document"),
    partWithName("thumbnail").optional()
            .description("Optional preview image")
)
```

The descriptor list must match the contract. A part present in the request without documentation can cause the test to fail; a descriptor for a part missing from the request can also cause the test to fail. This mechanism helps catch drift between documentation and requests.

## 6. Documenting Fields Inside a JSON Part

`requestParts(...)` documents the presence and meaning of each part. To document the JSON structure inside the `metadata` part, use `requestPartFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields(
    "metadata",
    fieldWithPath("title").description("Display title of the document"),
    fieldWithPath("category").description("Document category"),
    fieldWithPath("tags").description("List of tags"),
    fieldWithPath("tags[]").description("A single tag of the document")
)
```

In a complete test:

```java
mockMvc.perform(multipart("/api/documents")
        .file(filePart)
        .file(metadataPart))
    .andExpect(status().isCreated())
    .andDo(document("documents/upload",
        requestParts(
            partWithName("file").description("PDF file to upload"),
            partWithName("metadata").description("JSON metadata of the document")
        ),
        requestPartFields(
            "metadata",
            fieldWithPath("title").description("Display title"),
            fieldWithPath("category").description("Document category"),
            fieldWithPath("tags").description("List of tags"),
            fieldWithPath("tags[]").description("A single tag")
        )
    ));
```

Spring REST Docs validates descriptors against the part's JSON payload. If you add a `retentionDays` field without updating the descriptor, the test can report an undocumented field. If a descriptor describes a field absent from the payload, the test can also fail.

### 6.1. Nested Fields

Metadata may contain:

```json
{
  "title": "Service Contract",
  "owner": {
    "department": "LEGAL",
    "reference": "CASE-42"
  }
}
```

Document it:

```java
requestPartFields(
    "metadata",
    fieldWithPath("title").description("Title"),
    fieldWithPath("owner").description("Owning unit information"),
    fieldWithPath("owner.department").description("Department"),
    fieldWithPath("owner.reference").description("Reference code")
)
```

`relaxedRequestPartFields(...)` allows undocumented fields without failing the test. Only use relaxed descriptors when intentionally documenting a subset of the contract; for strictly controlled contracts, prefer full `requestPartFields(...)`.

## 7. Documenting Part Headers and File Content

A part may have its own `Content-Disposition` and `Content-Type`. Use `requestPartHeaders(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.requestPartHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

requestPartHeaders(
    "file",
    headerWithName("Content-Disposition")
        .description("Part name and submitted filename"),
    headerWithName("Content-Type")
        .description("Media type of the file")
)
```

Not every client or multipart encoder produces identical part headers. Inspect the actual snippet to see which headers are recorded. Document the headers that matter to the contract.

### 7.1. Documenting the Request Part Body

If a part is JSON, you can generate a dedicated body snippet:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata")
```

This snippet is useful when you want to display the raw JSON metadata alongside the field descriptor table. Do not use `requestPartBody` for large binary files or data unsuitable for printing in documentation; a file part usually only needs its name, media type, and purpose documented.

## 8. Documenting the Response and Location

A success response should document the status, `Location` header, and payload:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseHeaders(
    headerWithName("Location").description("URI of the newly created document"),
    headerWithName("Content-Type").description("Media type of the response")
);

responseFields(
    fieldWithPath("id").description("Document ID"),
    fieldWithPath("title").description("Title"),
    fieldWithPath("fileName").description("Filename"),
    fieldWithPath("contentType").description("Media type of the file"),
    fieldWithPath("size").description("File size in bytes")
)
```

Combine `requestParts`, `requestPartFields`, `requestPartHeaders`, `requestPartBody`, and response descriptors in the operation's `document(...)` call to generate a complete set of snippets.

## 9. Testing Multipart Errors

API documentation should show common input errors:

| Scenario | Example status | Meaning |
| --- | --- | --- |
| Missing `file` part | 400 Bad Request | Request is missing a required part |
| Missing `metadata` part | 400 Bad Request | Metadata is required |
| Malformed metadata JSON | 400 Bad Request | Unable to deserialize the part |
| Unsupported file media type | 415 Unsupported Media Type | Wrong content type |
| File exceeds size limit | 413 Payload Too Large | Size exceeds policy |
| Invalid metadata | 400 Bad Request | Validation failed |

Example documenting a validation error:

```java
mockMvc.perform(multipart("/api/documents")
        .file(filePart)
        .file(new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"","category":"LEGAL","tags":[]}
                """.getBytes(StandardCharsets.UTF_8))))
    .andExpect(status().isBadRequest())
    .andDo(document("documents/upload-invalid-metadata"));
```

The status and error body depend on the application's exception handler. Document the actual response; do not copy the example status if the controller or advice returns a different one.

## 10. REST Assured Example

REST Assured builds multipart requests with `multiPart(...)`:

```java
given()
        .multiPart("file", new File("src/test/resources/contract.pdf"),
                "application/pdf")
        .multiPart("metadata",
                """
                {"title":"Service Contract",
                 "category":"LEGAL",
                 "tags":["signed","customer"]}
                """,
                "application/json")
        .filter(document("documents/upload",
                requestParts(
                    partWithName("file").description("PDF file"),
                    partWithName("metadata").description("JSON metadata")
                ),
                requestPartFields(
                    "metadata",
                    fieldWithPath("title").description("Title"),
                    fieldWithPath("category").description("Category"),
                    fieldWithPath("tags").description("List of tags"),
                    fieldWithPath("tags[]").description("A single tag")
                )))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(201);
```

`multiPart(...)` overload signatures can vary across REST Assured versions. Pick the overload matching your dependency and check the `Content-Type` of each part in the request snippet. Use test fixture files with fake content.

## 11. WebTestClient Example

WebTestClient can construct a multipart body with `MultipartBodyBuilder`:

```java
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.core.io.ByteArrayResource;

MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("file", new ByteArrayResource(
        "fake-pdf-content".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "contract.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

builder.part("metadata", metadata)
        .contentType(MediaType.APPLICATION_JSON);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchange()
        .expectStatus().isCreated();
```

Attach the Spring REST Docs WebTestClient documentation filter/configuration to the client and document the operation according to your project's integration. WebTestClient's multipart encoding may differ from MockMvc; inspect the actual snippets to confirm part names, filenames, and media types.

## 12. Asciidoctor Include Snippets

After tests run, the output may contain:

```text
build/generated-snippets/
  documents/upload/
    curl-request.adoc
    http-request.adoc
    http-response.adoc
    request-parts.adoc
    request-part-metadata-fields.adoc
    request-part-file-headers.adoc
    request-part-metadata-body.adoc
    response-headers.adoc
    response-fields.adoc
```

Specific snippet names depend on descriptors and templates. Check the actual output directory rather than assuming all files in the example are generated.

Asciidoctor example:

```asciidoc
= Document API

== Upload Document

=== Request
include::{snippets}/documents/upload/http-request.adoc[]

=== Request parts
include::{snippets}/documents/upload/request-parts.adoc[]

=== Metadata fields
include::{snippets}/documents/upload/request-part-metadata-fields.adoc[]

=== Response
include::{snippets}/documents/upload/http-response.adoc[]
include::{snippets}/documents/upload/response-fields.adoc[]
```

The `snippets` attribute must point to the output root, for example `build/generated-snippets`. If your version/template uses different snippet names, update the includes to match the actual files.

## 13. Build and CI

Overall workflow:

1. Run multipart HTTP tests.
2. Verify that request parts and JSON part descriptors pass.
3. Generate request/response snippets.
4. Render Asciidoctor.
5. Check include paths and required snippet files.
6. Scan output to ensure no real files, tokens, or customer data are present.

Gradle example:

```bash
./gradlew clean test asciidoctor
```

File verification example:

```bash
test -f build/generated-snippets/documents/upload/request-parts.adoc
test -f build/generated-snippets/documents/upload/http-request.adoc
test -f build/generated-snippets/documents/upload/http-response.adoc
```

If using Maven, run the configured lifecycle so tests complete before Asciidoctor, such as `mvn clean verify`. Do not let stale files in the output root keep the build green when multipart tests stop generating snippets.

## 14. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Part does not appear in snippet | Part name in test differs from descriptor | Compare `file`/`metadata` names |
| REST Docs reports undocumented part | Request includes an undescribed part | Add a descriptor or mark `optional` per contract |
| JSON part fails to parse | Wrong `Content-Type` or invalid JSON | Set `application/json` on the metadata part |
| Request part fields snippet not generated | `requestPartFields(...)` was not called | Add descriptors for the JSON part |
| New field causes test failure | Payload contains an undocumented field | Update contract descriptors |
| Uploaded file has no filename | Multipart resource does not provide a filename | Set a filename on the file part |
| Test passes but snippet lacks part headers | `requestPartHeaders` not used or header absent | Inspect actual part headers |
| Asciidoctor include fails | Wrong snippet filename or identifier | Inspect output root and fix the include |
| Multipart request too large | Inappropriate test fixture or limit | Use a small fixture and test limits separately |

## 15. Capstone Exercise

Build the `POST /api/documents` API with two required parts:

- `file`: PDF, with clear filename and media type.
- `metadata`: JSON containing `title`, `category`, and `tags`.

Complete:

1. Write a controller accepting two `@RequestPart` parameters.
2. Create a MockMvc test with `MockMultipartFile` for `file` and `metadata`.
3. Use `requestParts(...)` to document part names/descriptions.
4. Use `requestPartFields(...)` to document metadata fields.
5. Use `requestPartHeaders(...)` to check `Content-Disposition` and `Content-Type` if they belong to the contract.
6. Use `requestPartBody(...)` if you need to display the raw JSON metadata.
7. Document the 201 response, `Location`, and response fields.
8. Write tests for missing parts or invalid metadata to document error responses.
9. Generate snippets and include them in Asciidoctor.
10. Run a clean build and verify in CI that all snippets are present.

**Completion criteria:** Integrators know which parts to send, their names, content types, and metadata structure; file and metadata are tested in a single multipart request; success and error responses are documented; snippets are generated from tests and Asciidoctor includes them properly.

## 16. Remember

A multipart upload is a single HTTP request containing multiple independent parts. Use `requestParts(...)` to describe parts, `requestPartFields(...)` to describe fields of a JSON part, `requestPartHeaders(...)` to describe part-specific headers, and `requestPartBody(...)` when you need to show the part's content. Write tests with fake file fixtures and UTF-8 JSON metadata, verify the response and `Location`, and include snippets in Asciidoctor. When the contract changes, descriptors must change alongside tests; CI should run a clean test and render pass to catch undocumented parts or missing snippets.

### References

- [Spring REST Docs — Documenting Request Parts](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — Multipart Resolver and Multipart Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
