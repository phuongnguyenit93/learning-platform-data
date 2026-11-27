# File Upload with Accompanying Metadata in Spring REST Docs

## 1. The File Upload with Metadata Problem

An upload API often needs to receive both a binary file and data describing that file at the same time. For example, a product image upload feature needs to accept:

- `file`: the image bytes.
- `metadata`: JSON containing title, description, display order, or other business information.

If split into two HTTP requests, the client must manage upload and metadata state across multiple steps. With `multipart/form-data`, the client sends both parts in a single request. Each part has its own name and Content-Type, allowing the server to convert each data type appropriately.

Example operation `POST /api/products/{productId}/assets` receiving:

```http
POST /api/products/42/assets HTTP/1.1
Accept: application/json
Content-Type: multipart/form-data; boundary=----AssetBoundary

------AssetBoundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

<PNG image bytes>
------AssetBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{
  "title": "Book Cover",
  "description": "Cover image for the new edition",
  "displayOrder": 1
}
------AssetBoundary--
```

In SPRING_REST_DOCS, we use HTTP tests with MockMvc, WebTestClient, or REST Assured to build real requests, then use Spring REST Docs to generate snippets. For file uploads with metadata, the APIs commonly combined are:

- `requestParts(...)` and `partWithName(...)` to document the parts.
- `requestPartFields("metadata", ...)` to document the JSON fields inside the `metadata` part.
- `requestPartBody("metadata")` if you need to display the raw JSON body.
- `requestHeaders(...)` if you need to document HTTP-level headers such as `Authorization` and `Accept`.

This lesson covers the full flow from contract, controller, and upload tests to Asciidoctor snippets and build/CI. After completing it, you will be able to design an operation accepting file + JSON, verify proper Content-Types, document both the part level and fields inside parts, and catch contract changes via tests.

## 2. Designing the Multipart Contract

Before writing a controller or descriptors, define the name and responsibility of each part.

| Part | Content Type | Required | Content |
| --- | --- | --- | --- |
| `file` | `image/png` or `image/jpeg` | Yes | Product image |
| `metadata` | `application/json` | Yes | Title, description, and display order |
| `thumbnail` | `image/jpeg` | No | Preview image if provided by the client |

Part names are part of the API contract. If the controller expects `@RequestPart("metadata")`, the client must send a part with `name="metadata"`. `filename="cover.png"` is the filename sent by the client; it is not the part name.

**Content-Type exists at two levels:**

- Overall request: `multipart/form-data; boundary=...`.
- Individual parts: `image/png`, `image/jpeg`, or `application/json`.

Do not set `application/json` as the Content-Type for the entire request if the body is multipart containing both a file and JSON. The JSON portion must have `application/json` attached to the `metadata` part itself.

A clear contract also defines how to handle empty files, unsupported MIME types, metadata missing fields, filenames, size limits, and optional parts. `requestParts(...)` can verify whether parts are sent in the sample request, but it does not replace those validation rules.

## 3. Controller Receiving File and JSON via `@RequestPart`

Spring MVC uses `@RequestPart` to extract each part by name. For a JSON part, Spring selects an `HttpMessageConverter` based on the part's Content-Type to convert the body into a DTO.

Example DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AssetMetadata(
        @NotBlank
        @Size(max = 120)
        String title,

        @Size(max = 1000)
        String description,

        Integer displayOrder
) {}
```

Illustrative controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class ProductAssetController {

    private final ProductAssetService assetService;

    ProductAssetController(ProductAssetService assetService) {
        this.assetService = assetService;
    }

    @PostMapping(
        path = "/api/products/{productId}/assets",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<Void> upload(
            @PathVariable Long productId,
            @RequestPart("file") MultipartFile file,
            @Valid @RequestPart("metadata") AssetMetadata metadata) {

        assetService.upload(productId, file, metadata);
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

In the operation above:

- `file` is bound as a `MultipartFile`.
- `metadata` is converted from the JSON part into `AssetMetadata`.
- `@Valid` triggers Bean Validation on the DTO if the validation dependency is configured.
- `consumes = MULTIPART_FORM_DATA_VALUE` restricts the overall request type.

`@RequestPart("metadata")` is required by default. If metadata should be allowed to be absent, both the contract and controller parameter must be designed accordingly, such as `required = false`; marking a descriptor optional in REST Docs does not automatically change controller behavior.

### 3.1. Validating the File in the Service

Never blindly trust the filename or Content-Type sent by the client. You can check basic conditions first:

```java
void validateImage(MultipartFile file) {
    if (file == null || file.isEmpty()) {
        throw new InvalidUploadException("Image file must not be empty");
    }

    String declaredType = file.getContentType();
    if (!MediaType.IMAGE_PNG_VALUE.equals(declaredType)
            && !MediaType.IMAGE_JPEG_VALUE.equals(declaredType)) {
        throw new UnsupportedUploadMediaTypeException(
                "Only PNG and JPEG are supported"
        );
    }

    // If actual format verification is required, inspect bytes
    // using a file-signature detector or appropriate parser.
}
```

These are only basic checks. MIME type is client-declared information; a spoofed file can send `Content-Type: image/png`. The system must verify actual content, enforce size limits, validate filenames, and manage storage and access permissions according to product security requirements.

## 4. Documenting at the Part Level with `requestParts(...)`

`requestParts(...)` documents the list of parts accepted by the operation. Each `partWithName(...)` creates a descriptor for one part:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("Product image to upload; PNG or JPEG"),
    partWithName("metadata")
        .description("JSON metadata describing the product image")
);
```

The `request-parts.adoc` snippet documents part names and their meanings. Part descriptors are required by default in sample requests. If a part may be absent, add `.optional()`; if it should be acknowledged without being displayed, use `.ignored()`.

Example with an optional thumbnail:

```java
requestParts(
    partWithName("file")
        .description("Product image; PNG or JPEG"),
    partWithName("metadata")
        .description("JSON metadata of the image"),
    partWithName("thumbnail")
        .description("Preview image if provided by the client")
        .optional()
);
```

`.optional()` only affects descriptor presence checks during snippet generation. It does not make the controller accept a missing part, nor does it mean a zero-byte file is considered valid.

### 4.1. Strict and Relaxed Request Parts

With `requestParts(...)`, a part present in the request without a descriptor can cause the snippet to fail. This is the right mode for catching new parts that need review. `relaxedRequestParts(...)` allows undeclared extra parts, suitable when the contract intentionally allows extension. Declared descriptors still follow required/optional rules.

Do not switch to relaxed mode just to silence errors when an API adds a new part; decide whether that part belongs to the public contract.

## 5. Describing JSON Inside `metadata` with `requestPartFields(...)`

`requestParts(...)` only describes the `metadata` part at the multipart level. It does not automatically generate a table for `title`, `description`, or `displayOrder`. When clients need to understand the JSON schema, use `requestPartFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields("metadata",
    fieldWithPath("title")
        .description("Image title"),
    fieldWithPath("description")
        .description("Image description")
        .optional(),
    fieldWithPath("displayOrder")
        .description("Image display order")
        .optional()
);
```

Descriptors here point to fields **inside the `metadata` JSON part**, so the paths are `title`, `description`, `displayOrder`; do not add a `metadata.` prefix.

The generated snippet is named after the part, for example:

```text
request-part-metadata-fields.adoc
```

If you want to display the raw sample JSON body, add `requestPartBody("metadata")`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata");
```

The three APIs have distinct scopes:

| API | Question Answered by the Snippet |
| --- | --- |
| `requestParts(...)` | Which parts does the operation accept? |
| `requestPartFields("metadata", ...)` | Which fields are inside the JSON metadata? |
| `requestPartBody("metadata")` | What does a sample metadata payload look like? |

All three can be used together if readers need part names, schema, and a sample body.

## 6. MockMvc: Creating File Parts and JSON Metadata

MockMvc supports `MockMultipartFile` for file uploads and `MockPart` for general parts. Using `MockPart` for metadata makes attaching the `Content-Type: application/json` header explicit.

### 6.1. Creating Multipart Parts

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;

MockMultipartFile filePart = new MockMultipartFile(
        "file",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        TestFixtures.validPng()
);

String metadataJson = """
        {
          "title": "Book Cover",
          "description": "Cover image for the new edition",
          "displayOrder": 1
        }
        """;

MockPart metadataPart = new MockPart(
        "metadata",
        metadataJson.getBytes(StandardCharsets.UTF_8)
);
metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);
```

The names `"file"` and `"metadata"` are the part names. `cover.png` is the filename sent by the client. Set the metadata part's content type to `application/json` so Spring MVC chooses the JSON converter when binding `@RequestPart("metadata") AssetMetadata`.

### 6.2. Complete Test Generating Snippets

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductAssetUploadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentFileAndMetadataUpload() throws Exception {
        MockMultipartFile filePart = new MockMultipartFile(
                "file",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                TestFixtures.validPng()
        );

        String metadataJson = """
                {
                  "title": "Book Cover",
                  "description": "Cover image for the new edition",
                  "displayOrder": 1
                }
                """;

        MockPart metadataPart = new MockPart(
                "metadata",
                metadataJson.getBytes(StandardCharsets.UTF_8)
        );
        metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
                    .file(filePart)
                    .part(metadataPart)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("products-upload-asset",
                        requestHeaders(
                                headerWithName("Accept")
                                        .description("Response format accepted by the client")
                        ),
                        requestParts(
                                partWithName("file")
                                        .description("Product image; PNG or JPEG"),
                                partWithName("metadata")
                                        .description("JSON metadata describing the image")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Image title"),
                                fieldWithPath("description")
                                        .description("Image description")
                                        .optional(),
                                fieldWithPath("displayOrder")
                                        .description("Image display order")
                                        .optional()
                        )
                ));
    }
}
```

`TestFixtures.validPng()` represents a helper reading valid image bytes from `src/test/resources`. Use a real fixture if the application checks file signatures or parses images; a dummy byte sequence may be rejected by the endpoint even when the header declares `image/png`.

`multipart(...)` automatically builds the overall request with `multipart/form-data` and a boundary. The test only needs to set actually needed outer headers, such as `Accept` or `Authorization`; do not assign `image/png` to the overall request.

If using Spring Security, you can add a request post-processor to mock a user or configure an appropriate test token. Never include real tokens in published snippets.

## 7. Snippet Output and Including in Documentation

After the test passes, the output directory can contain:

```text
build/generated-snippets/
└── products-upload-asset/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-headers.adoc
    ├── request-parts.adoc
    ├── request-part-metadata-body.adoc
    └── request-part-metadata-fields.adoc
```

Actual filenames and snippets depend on the configured operation. Only include files that the test actually requests to generate.

Example `src/docs/asciidoc/products.adoc`:

```adoc
= Product Asset API
:toc: left

== Product Image Upload

=== HTTP Request
include::{snippets}/products-upload-asset/http-request.adoc[]

=== Request Parts
include::{snippets}/products-upload-asset/request-parts.adoc[]

=== JSON Metadata
include::{snippets}/products-upload-asset/request-part-metadata-body.adoc[]

=== Metadata Fields
include::{snippets}/products-upload-asset/request-part-metadata-fields.adoc[]

=== HTTP Request Headers
include::{snippets}/products-upload-asset/request-headers.adoc[]
```

The `request-parts.adoc` table explains the file and metadata parts. The `request-part-metadata-fields.adoc` table explains the JSON schema. The body snippet illustrates a concrete example. Combining these three levels helps readers know exactly how to construct the multipart request.

## 8. Validation and Negative Tests

Documenting a successful request is not enough to guarantee the endpoint handles files safely and according to contract. Separate tests should cover error cases:

| Case | Expected Result per Example Contract |
| --- | --- |
| Missing `file` | HTTP 400 |
| Missing `metadata` | HTTP 400 |
| Metadata missing `title` | HTTP 400 |
| Metadata with malformed JSON | HTTP 400 |
| `metadata` with unsuitable Content-Type | Media type/converter error per config |
| Zero-byte file | HTTP 400 |
| Unsupported declared MIME | HTTP 415 or API-defined error |
| MIME is PNG but bytes are not PNG | Rejected if system inspects content |
| File exceeds size limit | HTTP 413 or error response per config |

The status codes above are contract examples; confirm them against your application's actual exception handler and configuration. Use negative tests to prove endpoint behavior rather than inferring it from Spring REST Docs snippet generation.

### 8.1. Testing Metadata Missing a Required Field

```java
@Test
void rejectMetadataWithoutTitle() throws Exception {
    MockMultipartFile filePart = new MockMultipartFile(
            "file",
            "cover.png",
            MediaType.IMAGE_PNG_VALUE,
            TestFixtures.validPng()
    );

    MockPart metadataPart = new MockPart(
            "metadata",
            """
            {"description":"Missing title"}
            """.getBytes(StandardCharsets.UTF_8)
    );
    metadataPart.getHeaders().setContentType(MediaType.APPLICATION_JSON);

    mockMvc.perform(multipart("/api/products/{productId}/assets", 42)
                .file(filePart)
                .part(metadataPart))
            .andExpect(status().isBadRequest());
}
```

This test only passes if the controller enables Bean Validation and the application maps validation errors to `400 Bad Request`. If the project uses structured error responses, you can also assert the error code or body.

### 8.2. Upload Size Limits

Spring Boot lets you configure multipart limits via properties matching the servlet stack, for example:

```properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

The overall request limit should be greater than or equal to the sum of part sizes plus multipart overhead. Exact values must be based on product needs, reverse proxy limits, and storage infrastructure. Tests must confirm the server rejects oversized files rather than relying on configuration alone.

### 8.3. Safe File Storage

Do not use `originalFilename` directly as a storage path. Generate filenames server-side, check content type and file signatures, enforce size limits, store outside publicly executable directories where appropriate, and enforce access control on downloads. Never place files containing real data or secrets into published test fixtures.

## 9. WebTestClient and REST Assured

### 9.1. WebTestClient with a JSON Part

You can create a JSON part using `HttpEntity` with its own headers:

```java
HttpHeaders metadataHeaders = new HttpHeaders();
metadataHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<String> metadataEntity =
        new HttpEntity<>(metadataJson, metadataHeaders);

HttpHeaders fileHeaders = new HttpHeaders();
fileHeaders.setContentType(MediaType.IMAGE_PNG);

HttpEntity<Resource> fileEntity =
        new HttpEntity<>(imageResource, fileHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("file", fileEntity);
parts.add("metadata", metadataEntity);

webTestClient.post()
        .uri("/api/products/42/assets")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("products-upload-asset",
                requestParts(
                        partWithName("file").description("Product image"),
                        partWithName("metadata").description("JSON metadata")
                )
        ));
```

This is a guiding example; resource/filenames and converters depend on payload types. For a JSON part, `HttpEntity` attaches `Content-Type: application/json` specifically to `metadata`.

### 9.2. REST Assured

REST Assured provides ways to build multipart parts with specific content types:

```java
given(this.spec)
        .filter(document("products-upload-asset",
                requestParts(
                        partWithName("file").description("Product image"),
                        partWithName("metadata").description("JSON metadata")
                )))
        .multiPart("file", imageFile, "image/png")
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/products/42/assets")
        .then()
        .statusCode(201);
```

The exact `multiPart(...)` overload must match the REST Assured version used by your project. After building the request, the actual part names and Content-Types on the wire must match the contract and descriptors.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Controller fails to bind metadata DTO | JSON part lacks `application/json` or JSON syntax is invalid | Set proper Content-Type and check converter |
| `requestParts(...)` reports missing part | Required descriptor was not sent by test | Add the part or `.optional()` per contract |
| New part causes snippet to fail | Strict mode encountered an undocumented part | Add descriptor, intentionally ignore, or relax per contract |
| Metadata fields not generated | Only `requestParts(...)` was called | Add `requestPartFields("metadata", ...)` |
| Missing JSON body snippet | `requestPartBody("metadata")` was not called | Add body snippet if needed |
| File rejected despite valid MIME | Bytes do not match format or fixture is invalid | Use a real fixture file and verify content |
| Using `image/png` for entire request | Confusing part media type with outer request | Use `multipart/form-data` at the request level |
| Snippet documents only parts, not JSON schema | Using only `requestParts(...)` | Add `requestPartFields` or link schema |
| Filename treated as part name | Confusing `filename` with `name` | `partWithName` uses the part name |
| Asciidoctor reports missing include | Including a snippet not generated by tests | Check operation ID and test task |

## 11. Build and CI

With Gradle and the Asciidoctor plugin configured, the documentation task must depend on the snippet-generating tests:

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
Multipart HTTP tests
        |
        v
Verify file part + JSON metadata
        |
        +--> Validation / negative tests
        |
        v
Spring REST Docs: requestParts + requestPartFields
        |
        v
Generated snippets
        |
        v
Asciidoctor / Markdown export step
        |
        v
Verify and publish
```

Whenever the metadata DTO, part names, or Content-Type list changes, tests and snippets must be regenerated. Do not manually edit generated snippets to hide discrepancies. CI should run successful upload tests, validation tests, and the documentation rendering step.

Spring REST Docs generates AsciiDoc snippets by default. If the project publishes Markdown, a custom template or conversion step is needed; `request-parts.md` is not created by default.

## 12. Practice Exercise

With the `POST /api/products/{productId}/assets` endpoint:

1. Build a request containing a PNG file and JSON metadata. Ensure request-level Content-Type is multipart and each part has its own media type.
2. Add an `altText` field to the metadata DTO. Update `requestPartFields(...)` and inspect the snippet.
3. Omit `description` from metadata. Mark the descriptor optional and check the documentation test.
4. Send metadata with `Content-Type: text/plain`; verify the endpoint handles it according to contract.
5. Send a file with MIME `image/png` whose bytes are not PNG. Add file content verification and a negative test.
6. Remove the `metadata` part, then remove the `file` part; verify error status codes per contract and distinguish them from snippet errors.
7. Add a size limit and test an oversized file.
8. Include `request-parts`, metadata body, and `metadata-fields` in Asciidoctor; ensure CI runs tests before rendering.

### Self-Assessment Questions

- Why should the file and JSON metadata be two separate parts?
- Which Content-Type does `@RequestPart("metadata")` need for Spring to convert JSON into a DTO?
- What two levels do `requestParts(...)` and `requestPartFields(...)` describe?
- Why don't field descriptors inside a JSON part need a `metadata.` prefix?
- Does a client-declared Content-Type prove the bytes match the format?
- Does `.optional()` in a descriptor make the controller accept a missing part?
- Why are both positive tests and negative tests needed for uploads?
- When the metadata DTO changes, which snippets must be regenerated?

**Remember:** A complete multipart upload must document both the file part and the metadata part. `requestParts(...)` tells what the operation accepts; `requestPartFields("metadata", ...)` explains the JSON schema; `requestPartBody("metadata")` shows a concrete JSON example. Combining these snippets with `@RequestPart`, proper Content-Types, validation, and HTTP tests keeps the documentation aligned with the API's file + metadata upload flow.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts`, part body, and part fields.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestPartFields` and documenting JSON payloads.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): binding parts and converting via `HttpMessageConverter`.
- [Spring Framework — `MultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): filename, content type, size, and bytes of uploaded files.
