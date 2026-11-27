# File Parts and Binary Payloads in Spring REST Docs

## 1. Characteristics of a file part in a multipart request

A file upload endpoint typically accepts **multipart/form-data** requests. A request contains one or more parts, each with its own name, headers, and body. For a file part, the body is usually a sequence of bytes representing a PDF, image, audio, or other binary data.

For example, the `POST /documents` endpoint receives a part:

```text
Part name: file
Filename: handbook.pdf
Content-Type: application/pdf
Body: bytes of the PDF file
```

Unlike a JSON part, a file's content is not a JSON object composed of fields that can be described with `fieldWithPath(...)`. File bytes may contain complex format structures, non-printable characters, binary metadata, or compressed data.

Spring REST Docs provides `requestParts(...)` and `partWithName(...)` to describe the **presence and purpose of a file part** in a multipart request. Tests can still verify the filename, media type, size, or file content using standard assertions.

This lesson focuses on:

- describing a file part in a multipart request;
- creating deterministic dummy binary file data for testing;
- validating the filename, content type, size, and processing outcome;
- distinguishing file parts from JSON/text parts;
- deciding when to use `requestPartBody(...)` and when to avoid putting binary bodies into snippets;
- using MockMvc, WebTestClient, or REST Assured to generate documentation;
- protecting documentation and CI from real data, overly large files, or sensitive information.

## 2. Describing a file part with requestParts

`requestParts(...)` generates the `request-parts.adoc` snippet describing the parts supported by the resource. Each `partWithName(...)` specifies the part name and describes its purpose:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("PDF file of the document to upload")
)
```

This table informs readers that the request requires a part named `file` to send a PDF document. It describes **multipart structure at the part level**, not the schema of the bytes inside the file.

If the endpoint also accepts a `metadata` JSON part, both can be described:

```java
requestParts(
    partWithName("file")
        .description("PDF file to upload"),
    partWithName("metadata")
        .description("JSON information describing the file")
)
```

Readers then understand the role of each part. JSON metadata can be documented separately with `requestPartFields("metadata", ...)`; file bytes are not treated as a set of JSON fields.

### 2.1. File part details and the request-parts table do not replace each other

A multipart contract typically includes the following attributes:

| Attribute | Meaning | How to verify or document |
| --- | --- | --- |
| Part name | Name sent by the client in the multipart body | `partWithName("file")` |
| Filename | Filename supplied by the client | Assertion on `MultipartFile.getOriginalFilename()`; explain conventions in documentation |
| Content-Type | Media type of the file part | Assertion on `MultipartFile.getContentType()`; describe accepted file types |
| Size | Number of bytes in the file | Assertion on `MultipartFile.getSize()`; document upload limits |
| Byte content | Actual data of the file | Assertion/hash or processing test; not necessarily embedded as bytes in documentation |
| Actual format type | Internal file structure, e.g., PDF/PNG | Verify with an appropriate parser/validator; do not trust only filename or Content-Type |

The `request-parts.adoc` snippet mainly provides a table of part names and descriptions. Use API prose, assertions, and business validation checks to clarify the remaining attributes. Do not assume the snippet automatically creates a complete table for filename, media type, and size if handlers do not document those details.

## 3. Creating dummy binary files for testing

Avoid using real files from a developer's machine or internal documents. Create small, deterministic fixtures containing no sensitive data.

With MockMvc, `MockMultipartFile` takes the part name, filename, content type, and byte array:

```java
byte[] pdfBytes = new byte[] {
    0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34,
    0x0A, 0x25, (byte) 0xE2, (byte) 0xE3, (byte) 0xCF, (byte) 0xD3
};

MockMultipartFile file = new MockMultipartFile(
    "file",
    "handbook.pdf",
    "application/pdf",
    pdfBytes
);
```

The array above is only a short byte fixture illustrating binary data transfer; it is **not a complete PDF for testing a PDF parser**. If the controller or service needs to parse the PDF, use a small, valid PDF fixture managed in test resources with a clear origin.

For a dummy image file, a separate byte array and corresponding content type can be used. What matters is matching the fixture to the test objective:

- testing multipart request/binding: small bytes may suffice;
- testing a format parser: an actually valid sample file is needed;
- testing size limits: create a byte array of the appropriate size;
- testing file security: a dedicated test suite for spoofed files, invalid content, or forbidden file types is needed.

Do not use a file named `.pdf` whose bytes are not a PDF and then conclude the application has validated the format. Filename and Content-Type are client-supplied metadata; they do not prove the actual content.

## 4. MockMvc example: documenting a file part and verifying metadata

The example uses JUnit 5, Java 17+, Spring MVC Test, and Spring REST Docs. The sample endpoint receives a PDF file and returns the inspected metadata. File storage is simplified so the lesson focuses on multipart documentation.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentFileUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadPdfFile() throws Exception {
        byte[] pdfBytes = new byte[] {
            0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34, 0x0A
        };

        MockMultipartFile file = new MockMultipartFile(
                "file",
                "handbook.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                pdfBytes
        );

        this.mockMvc.perform(multipart("/documents")
                        .file(file)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.filename").value("handbook.pdf"))
                .andExpect(jsonPath("$.contentType")
                        .value(MediaType.APPLICATION_PDF_VALUE))
                .andExpect(jsonPath("$.size").value(pdfBytes.length))
                .andDo(document("documents-upload",
                        requestParts(
                                partWithName("file")
                                        .description("PDF file to upload")
                        )
                ));
    }

    @RestController
    static class DocumentController {

        @PostMapping(
                value = "/documents",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, Object>> upload(
                @RequestPart("file") MultipartFile file) {

            if (file.isEmpty()) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.status(201).body(Map.of(
                    "filename", file.getOriginalFilename(),
                    "contentType", file.getContentType(),
                    "size", file.getSize()
            ));
        }
    }
}
```

This example performs three distinct tasks:

1. `requestParts(...)` creates a table describing the part named `file`.
2. `jsonPath` confirms the server received the fixture's exact filename, content type, and size.
3. The sample controller returns metadata for test verification; in a real application, the response might only return a document ID or upload status.

The request-parts table does not automatically turn filename, media type, and size into verified columns. The assertions above confirm how the application received the file in this test case. If those attributes are part of the contract clients must understand, explain them further on the API page.

## 5. Should requestPartBody be used for binary files?

`requestPartBody("file")` can generate a body snippet for a request part. This feature is useful when the part body is human-readable text or JSON. For a binary file such as PDF, PNG, ZIP, or audio, rendering bytes as text is usually unhelpful:

- data may contain non-printable bytes;
- the snippet may be very long or unreadable;
- some formats may be compressed or encrypted;
- the file may contain private metadata or sensitive content;
- documentation may bloat and become hard to review.

Therefore, for a file part, it is usually better to describe the part with `requestParts(...)` and use assertions to verify metadata/content. There is no need to call `requestPartBody("file")` just to prove the file was sent.

Appropriate example for a JSON part:

```java
requestPartBody("metadata")
```

This JSON section can be rendered clearly in a snippet. For a file part:

```java
requestParts(
    partWithName("file")
        .description("PDF file of the document")
)
```

If the product genuinely needs to publish a sample file for clients to download, manage that sample file as a separate artifact/example file in the documentation release process. Do not use a body snippet as a mechanism to distribute binary files unless the format and rendering are explicitly controlled.

## 6. File part alongside JSON metadata

A real-world endpoint often receives both a file and metadata:

```text
POST /documents
multipart/form-data
├── file: handbook.pdf (application/pdf, binary)
└── metadata: application/json
    ├── title
    ├── category
    └── visibility
```

The test can document both parts:

```java
.andDo(document("documents-upload",
    requestParts(
        partWithName("file")
            .description("PDF file to upload"),
        partWithName("metadata")
            .description("JSON metadata describing the document")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Title"),
        fieldWithPath("category").description("Document category"),
        fieldWithPath("visibility").description("Visibility scope")
    )
));
```

The part table shows that the request has `file` and `metadata`. The part fields table documents only the JSON metadata. Do not use `requestPartFields("file", ...)` for PDF content because file bytes do not have a JSON field structure.

You can add `requestPartBody("metadata")` to display sample JSON. The documentation then has three clear layers: part table, sample JSON metadata, and metadata schema table.

## 7. Testing file limits and rules

Spring REST Docs generates documentation; it does not replace upload validation. Beyond `requestParts`, endpoints typically require business checks:

| Rule | Recommended test |
| --- | --- |
| Required file | Send request without the `file` part and verify appropriate error |
| Non-empty file | Send zero-byte file and verify response |
| Size limit | Send files smaller than, equal to, and larger than the threshold |
| Accepted file types | Verify declared content type and/or actual format |
| Filename | Test empty names, long names, special characters, and safe handling |
| Duplicate filenames | Verify overwrite or renaming rules |
| File content | Test parser, checksum, or processing results per business logic |
| Upload permissions | Verify users can only upload to authorized areas |

For example, size-limit tests do not necessarily need to generate the same public snippet. You can separate documentation tests for the success scenario from validation/error tests covering edge cases. If you need to document an error, use a distinct identifier like `documents-upload-too-large` to avoid overwriting the success snippet.

### 7.1. Content-Type does not verify actual format

A part with `Content-Type: application/pdf` only reflects the media type declared by the client. A client can send arbitrary content with that header. The application must validate the format per product security requirements, such as checking magic bytes or parsing with an appropriate library.

Similarly, a filename ending in `.pdf` does not guarantee the bytes are a PDF. API documentation should clearly state which file types the endpoint accepts, what the size limits are, and what information is validated, based on actual behavior.

### 7.2. Fixtures for binary data

Use small, deterministic fixtures that can be constructed from byte arrays or valid test resource files. Never use real documents containing personal data, contracts, customer data, or proprietary content in snippets or the repository.

If a test needs a valid file for a parser, the test resource file should be small and well-scoped. If you only need to verify multipart wiring, a minimal byte fixture may suffice; do not describe it as a complete format-compliant file.

## 8. File parts with WebTestClient

With WebTestClient, a multipart body is typically built using `BodyInserters.fromMultipartData` with a `MultiValueMap`. To send a file resource with a filename, you can use `ByteArrayResource` overriding `getFilename()`:

```java
byte[] pdfBytes = new byte[] {
    0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34
};

Resource pdf = new ByteArrayResource(pdfBytes) {
    @Override
    public String getFilename() {
        return "handbook.pdf";
    }
};

HttpHeaders fileHeaders = new HttpHeaders();
fileHeaders.setContentType(MediaType.APPLICATION_PDF);

HttpEntity<Resource> filePart = new HttpEntity<>(pdf, fileHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("file", filePart);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents-upload",
        requestParts(
            partWithName("file")
                .description("PDF file to upload")
        )
    ));
```

WebTestClient must be configured with the REST Docs documentation filter on the builder before calling `build()`. The snippet above illustrates creating the multipart file part and the documentation handler; imports, server/client setup, and context provider must be declared according to your project's test configuration.

If the API requires JSON metadata, add a `metadata` part as an object or `HttpEntity` with Content-Type `application/json`. Ensure the test sends the exact media type expected by the server.

## 9. File parts with REST Assured

REST Assured supports sending file parts via `multiPart`:

```java
RestAssured.given(this.spec)
    .accept("application/json")
    .filter(document("documents-upload",
        requestParts(
            partWithName("file")
                .description("PDF file to upload")
        )
    ))
    .multiPart("file", new File("handbook.pdf"), "application/pdf")
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

`spec` must be configured with the REST Docs filter according to your project's REST Assured integration. The `handbook.pdf` file must be a deterministic test fixture, not a path to a private file on a developer's machine. If using a byte array or input stream, confirm that the `multiPart` overload sends the expected filename and media type.

## 10. Snippet names and Asciidoctor documentation

With the operation identifier `documents-upload`, `requestParts(...)` creates `request-parts.adoc` in the operation directory:

```text
build/generated-snippets/
└── documents-upload/
    ├── request-parts.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

If the test also documents a `metadata` part, there may additionally be:

```text
request-part-metadata-body.adoc
request-part-metadata-fields.adoc
```

The Asciidoctor document can be written as:

```asciidoc
= Document API
:toc: left

== POST /documents

Upload a PDF file. Clients send the file in the `file` part
with media type `application/pdf`.

=== Supported parts

include::{snippets}/documents-upload/request-parts.adoc[]

=== Result

include::{snippets}/documents-upload/http-response.adoc[]
```

Prose explaining filename, size, and format limits should be written based on the actual contract. The `request-parts` snippet does not automatically describe all file validation rules.

## 11. Gradle and CI integration

With Gradle Groovy DSL, assuming the project already has Spring REST Docs, tests, and the Asciidoctor plugin configured:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Run:

```bash
./gradlew clean test asciidoctor
```

CI should verify:

1. Tests create file fixtures and multipart requests successfully.
2. Part names in the request match `partWithName`.
3. Assertions for filename, content type, size, or critical content pass.
4. The `request-parts` snippet is generated from the current tests.
5. Asciidoctor includes the exact operation identifier and snippet name.
6. No real files or sensitive data are committed into generated snippets or the repository.

If the build uses Maven, the snippet directory is typically configured as `target/generated-snippets`; the documentation compilation step must run after the tests that generate snippets.

## 12. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `file` part not found | Name in `MockMultipartFile`/client differs from descriptor | Align part name across client, controller, and `partWithName` |
| Test receives file with empty filename | Multipart client/resource did not supply a filename | Set filename in `MockMultipartFile` or `Resource` |
| Unexpected Content-Type | File part lacks media type or client serializes differently | Inspect part headers and use `HttpEntity` when needed |
| File part documented as JSON | Using `requestPartFields` for binary bytes | Only use `requestPartFields` for parts with structured payloads |
| Body snippet contains unreadable characters | Calling `requestPartBody` for PDF/PNG/binary | Only generate body snippets for human-readable text/JSON parts |
| Test passes even with wrong file format | Checking only filename/content type | Parse or verify actual content per contract |
| Overly large upload tests slow down build | Uncontrolled fixture size | Use small fixtures and dedicated limit tests |
| Documentation leaks file content | Using real files or putting binary bodies into snippets | Use dummy data; only document part descriptions and metadata assertions |
| Asciidoctor missing `request-parts` | Test didn't generate snippet, wrong identifier, or output directory | Check tests, operation ID, and include path |

## 13. Hands-on exercise

Create `DocumentFileUploadDocumentationTest`:

1. Create a `file` part using `MockMultipartFile` with filename `handbook.pdf`, media type `application/pdf`, and dummy fixture bytes.
2. Use `requestParts(partWithName("file"), ...)` to describe the role of the file.
3. Add assertions for filename, content type, and file size; if a parser requires a valid PDF, use a valid PDF fixture instead of a minimal byte array.
4. Test an empty filename and an empty file; verify the endpoint handles them per contract.
5. Test a file exceeding the limit; create a separate error test and document it with a distinct operation identifier if needed.
6. Add a JSON `metadata` part; document the part list, JSON body, and fields with the corresponding handlers.
7. Avoid calling `requestPartBody("file")` on the binary fixture; try it in a sandbox to see why the snippet is unsuitable for published documentation.
8. Include `request-parts.adoc` in Asciidoctor and run `./gradlew clean test asciidoctor`.

**Completion criteria:** you can document a file part at the multipart level, separately validate filename/media type/size/content, distinguish file bytes from JSON fields, and choose snippets that keep documentation readable without exposing real data.

## 14. Self-check questions

**1. Which API describes a file part in a multipart request?**

Use `requestParts(partWithName("file").description(...))`. It describes the part and its role in the request.

**2. Does requestParts validate that file bytes match the right format?**

No. It documents the presence/purpose of the part. Actual format must be verified by a parser, magic bytes, or appropriate validation.

**3. Should requestPartBody("file") be used for PDFs or images?**

Normally no. Binary bodies are hard to read and may expose data. Only use body snippets for text/JSON parts whose content readers need to inspect.

**4. How do you verify filename and Content-Type?**

Use assertions on `MultipartFile.getOriginalFilename()` and `getContentType()`, or inspect request part headers in the test. Explain supported rules in the documentation.

**5. Is a file with Content-Type application/pdf guaranteed to be a PDF?**

No. That is merely the media type declared by the client. The application must validate the actual content if required by the contract or security policies.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): documenting request parts, part body, and part fields with MockMvc, WebTestClient, and REST Assured.
- [Spring Framework — Multipart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): how Spring MVC binds multipart requests and file parts.
- [Spring Framework — RequestPart](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): mapping parts to controller parameters and processing via `HttpMessageConverter`.
