# Content Types of Individual Parts in Spring REST Docs

## 1. Two Levels of Content-Type in a Multipart Request

A `multipart/form-data` request can contain image files, PDFs, JSON metadata, and plain text in a single HTTP body. Each piece of content can have its own media type, so it is necessary to distinguish:

- **Request-level Content-Type** describes the entire HTTP body as multipart and contains the boundary to separate parts.
- **Part-level Content-Type** describes the content format of a specific part, such as `image/png`, `application/pdf`, or `application/json`.

Example endpoint `POST /api/products/42/assets` accepting an image file and JSON metadata:

```http
POST /api/products/42/assets HTTP/1.1
Accept: application/json
Content-Type: multipart/form-data; boundary=----AssetBoundary

------AssetBoundary
Content-Disposition: form-data; name="image"; filename="cover.png"
Content-Type: image/png

<PNG image bytes>
------AssetBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{
  "title": "Book Cover",
  "description": "Cover image for the new edition"
}
------AssetBoundary--
```

In this example, `multipart/form-data; boundary=...` is the request's Content-Type. `image/png` and `application/json; charset=UTF-8` are the Content-Types inside individual parts.

| Location | Example | Meaning |
| --- | --- | --- |
| HTTP request | `multipart/form-data; boundary=...` | Overall body has multiple parts |
| `image` part | `image/png` | Part content is a PNG image |
| `metadata` part | `application/json; charset=UTF-8` | Part content is JSON |
| `document` part | `application/pdf` | Part content is a PDF |

Do not set `Content-Type: image/png` at the request level when the request has multiple parts of different types. The outer Content-Type must indicate multipart format; each individual part declares its own media type.

This lesson belongs to the **Request parts** chapter of SPRING_REST_DOCS. This module practices producing verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, then integrating snippets into Asciidoctor/Markdown and build/CI workflows.

After this lesson, you will be able to:

- Distinguish request-level Content-Type from part-level Content-Type.
- Configure media types for file and JSON parts in tests.
- Understand the roles of `requestParts(...)`, `requestPartBody(...)`, and `requestPartFields(...)`.
- Verify MIME types, file contents, and JSON part deserialization.
- Write positive and negative tests for parts with different media types.
- Publish media type rules in documentation without confusing description with validation.

## 2. Request-Level Content-Type and Boundary

A multipart request typically has an outer header:

```http
Content-Type: multipart/form-data; boundary=----AssetBoundary
```

The boundary is a string marking the start and end positions of parts in the body. The HTTP client or multipart builder normally generates the boundary and ensures the value in the header matches the body contents.

Do not pick a boundary yourself and assemble the body manually without a specific reason. If the header declares a boundary different from the actual boundary in the body, the server cannot parse the parts properly.

In MockMvc, when using:

```java
mockMvc.perform(multipart("/api/products/42/assets")
        .file(image)
        .file(metadata))
```

the Spring test builder constructs the multipart request and sets the appropriate request-level Content-Type. Do not assign `image/png` to the overall request; that media type must be attached to the corresponding `MockMultipartFile`.

If the API only accepts multipart requests, the controller can declare:

```java
@PostMapping(
    path = "/api/products/{id}/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @PathVariable Long id,
        @RequestPart("image") MultipartFile image,
        @RequestPart("metadata") AssetMetadata metadata) {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

`consumes = MULTIPART_FORM_DATA_VALUE` constrains the overall request type. It does not state that the `image` part must be PNG or the `metadata` part must be JSON; those conditions must be defined and checked separately.

## 3. Specifying Content-Type for Each Part with MockMvc

`MockMultipartFile` has a constructor accepting part name, filename, content type, and bytes:

```java
new MockMultipartFile(
    "image",
    "cover.png",
    MediaType.IMAGE_PNG_VALUE,
    imageBytes
);
```

Important parameters:

| Parameter | Example | Role |
| --- | --- | --- |
| `name` | `image` | Part name in the multipart request |
| `originalFilename` | `cover.png` | Filename sent by the client |
| `contentType` | `image/png` | Content-Type of the part |
| `content` | `imageBytes` | Part content |

Example creating two parts with different types:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        validPngBytes
);

String metadataJson = """
        {
          "title": "Book Cover",
          "description": "Cover image for the new edition"
        }
        """;

MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        metadataJson.getBytes(StandardCharsets.UTF_8)
);
```

The name `image` is the part name that must match `@RequestPart("image")` and `partWithName("image")`. The filename `cover.png` is not the part name. Content-Type `image/png` is attached to the image part, while `application/json` is attached to metadata.

### 3.1. Using `MediaType` Constants or Exact MIME Strings

Spring provides commonly used constants:

```java
MediaType.IMAGE_PNG
MediaType.IMAGE_JPEG
MediaType.APPLICATION_PDF
MediaType.APPLICATION_JSON
MediaType.TEXT_PLAIN
MediaType.MULTIPART_FORM_DATA
```

You can use `MediaType.IMAGE_PNG_VALUE` when an API expects a Content-Type string. For custom media types or vendor media types, such as `application/vnd.example.asset+json`, use the exact value published in the contract.

Do not infer Content-Type solely from the filename extension. `cover.png` could be sent with a different MIME type; filename and headers are client-declared data, not proof that the bytes are genuinely PNG.

## 4. Documenting Parts and Content-Type

Spring REST Docs provides APIs at different levels:

| API | What It Documents |
| --- | --- |
| `requestParts(...)` | Parts accepted by the operation |
| `partWithName("image")` | Name and description of a single part |
| `requestPartBody("metadata")` | Body of the `metadata` part |
| `requestPartFields("metadata", ...)` | Fields inside the JSON part |
| `requestHeaders(...)` | HTTP request-level headers |

Example:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("image")
        .description("Product image; send as PNG or JPEG"),
    partWithName("metadata")
        .description("JSON metadata describing the image")
);
```

`requestParts(...)` generates the `request-parts.adoc` snippet describing part names and meanings. It **does not automatically verify** that `image` actually has `Content-Type: image/png`, nor does it automatically generate a standard MIME type column from `MockMultipartFile.getContentType()`.

Therefore, if each part's Content-Type is an important part of the contract, state it clearly in the description or in a separate contract table, for example:

| Part | Accepted Content-Type | Role |
| --- | --- | --- |
| `image` | `image/png`, `image/jpeg` | Product image |
| `metadata` | `application/json` | Image descriptive info |
| `caption` | `text/plain` | Optional caption |

This table is documentation content maintained by the team; to keep it accurate, tests must check the actual request parts.

### 4.1. Documenting the JSON Body Separately

`requestParts(...)` does not create a table for the `title` and `description` fields inside `metadata`. Use:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

.andDo(document("assets-upload",
        requestParts(
            partWithName("image").description("PNG or JPEG image"),
            partWithName("metadata").description("JSON metadata")
        ),
        requestPartBody("metadata"),
        requestPartFields("metadata",
            fieldWithPath("title")
                .description("Image title"),
            fieldWithPath("description")
                .description("Image description")
                .optional()
        )
));
```

The generated snippets can include:

```text
request-parts.adoc
request-part-metadata-body.adoc
request-part-metadata-fields.adoc
```

Snippet names are generated based on the API and part name. Only include snippets that the tests actually request to be generated.

### 4.2. Outer Headers Remain a Different Scope

If you need to document `Authorization`, `Accept`, or request-level Content-Type, use `requestHeaders(...)`:

```java
requestHeaders(
    headerWithName("Authorization")
        .description("Authentication bearer token"),
    headerWithName("Accept")
        .description("Response format accepted by the client"),
    headerWithName("Content-Type")
        .description("Multipart request body")
)
```

`requestHeaders(...)` does not replace recording the Content-Type of each part. Media types inside individual parts should appear in the sample request, contract table, or a custom snippet if an auto-generated table is needed.

## 5. Complete MockMvc Example

Assume the `POST /api/products/{id}/assets` endpoint accepts:

- `image`: valid PNG or JPEG.
- `metadata`: JSON part with required `title` and optional `description`.
- Success response: `201 Created`.

The project requires Spring Boot, JUnit 5, MockMvc, and `spring-restdocs-mockmvc`.

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

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
class ProductAssetContentTypeDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentImageAndJsonPartContentTypes() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                TestFixtures.validPng()
        );

        String metadataJson = """
                {
                  "title": "Book Cover",
                  "description": "Cover image for the new edition"
                }
                """;

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                metadataJson.getBytes(StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/api/products/{id}/assets", 42)
                    .file(image)
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("products-upload-asset",
                        requestParts(
                                partWithName("image")
                                        .description("PNG or JPEG image"),
                                partWithName("metadata")
                                        .description("JSON metadata of the image")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Image title"),
                                fieldWithPath("description")
                                        .description("Image description")
                                        .optional()
                        )
                ));
    }
}
```

`TestFixtures.validPng()` is an illustrative helper and must be replaced with a valid PNG image in test resources. If the endpoint checks file signatures, an arbitrary byte sequence may be rejected even when Content-Type is declared as `image/png`.

The test above generates the parts snippet, JSON body, and JSON fields. It **does not automatically generate a Content-Type table for individual parts**. Content-Type is specified when creating `MockMultipartFile`; endpoint validation and other tests must confirm the server accepts the expected media types.

## 6. Checking Content-Type in the Controller

When the controller receives a file part as `MultipartFile`, the application can check the Content-Type declared by the client:

```java
private void validateImageContentType(MultipartFile image) {
    String contentType = image.getContentType();

    if (!MediaType.IMAGE_PNG_VALUE.equals(contentType)
            && !MediaType.IMAGE_JPEG_VALUE.equals(contentType)) {
        throw new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "Only PNG and JPEG images are supported"
        );
    }
}
```

This checks the MIME header sent by the client. It does not confirm that the bytes are genuinely a PNG or JPEG image. If you need to guarantee the content format, check the file signature or parse the content with an appropriate image library; do not rely solely on Content-Type or filename.

### 6.1. JSON Part and `HttpMessageConverter`

When a controller receives metadata via `@RequestPart` as a DTO:

```java
@PostMapping(
    path = "/api/products/{id}/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @PathVariable Long id,
        @RequestPart("image") MultipartFile image,
        @Valid @RequestPart("metadata") AssetMetadata metadata) {

    // Validate the file and save the asset.
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Spring MVC uses an `HttpMessageConverter` matching the part's Content-Type to convert the JSON body into `AssetMetadata`. If the JSON part declares the wrong media type or the body is not valid JSON, conversion can fail before the controller executes.

Example DTO:

```java
import jakarta.validation.constraints.NotBlank;

record AssetMetadata(
        @NotBlank String title,
        String description
) {}
```

Validation must be enabled and the appropriate dependency must be present for `@Valid` to enforce constraints. `requestPartFields(...)` helps document the JSON but does not automatically check that `title` is non-blank; validation and negative tests verify that rule.

## 7. Writing Negative Tests for Media Type and Content

A thorough set of upload tests should verify both the Content-Type header and the actual bytes.

| Case | Illustrative Result | Reason |
| --- | --- | --- |
| PNG with MIME `image/png`, valid PNG bytes | Succeeds | Correct media type and format |
| JPEG with MIME `image/jpeg`, valid JPEG bytes | Succeeds if contract permits | Supported format |
| Image part with MIME `text/plain` | `415` or error per contract | Unsupported Content-Type |
| Declared MIME `image/png` but bytes are not PNG | Rejected if checking file signature | Do not trust client-declared MIME |
| Metadata with `application/json` and valid JSON | Succeeds | Converter can deserialize |
| Metadata with `text/plain` when endpoint expects JSON | Rejected per converter configuration | Mismatched media type |
| Metadata JSON missing `title` | Validation error | Violates DTO contract |

Example test for an image part with wrong MIME:

```java
@Test
void rejectUnsupportedImageMediaType() throws Exception {
    MockMultipartFile image = new MockMultipartFile(
            "image",
            "cover.txt",
            MediaType.TEXT_PLAIN_VALUE,
            "not an image".getBytes(StandardCharsets.UTF_8)
    );

    MockMultipartFile metadata = new MockMultipartFile(
            "metadata",
            "",
            MediaType.APPLICATION_JSON_VALUE,
            """
            {"title":"Book Cover"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/products/{id}/assets", 42)
                .file(image)
                .file(metadata))
            .andExpect(status().isUnsupportedMediaType());
}
```

Asserting `415` is only appropriate if the endpoint maps unsupported media types to `Unsupported Media Type`. If the application specifies a different error response or the controller returns `400`, write the test according to the real contract.

Another test should send `image/png` with invalid bytes to ensure the server does not trust the header alone. That is file content validation, not a Spring REST Docs feature.

## 8. WebTestClient and REST Assured

### 8.1. WebTestClient

With WebTestClient, you can attach separate headers to each part using `HttpEntity` inside `MultiValueMap`:

```java
HttpHeaders metadataHeaders = new HttpHeaders();
metadataHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<String> metadataPart =
        new HttpEntity<>(metadataJson, metadataHeaders);

HttpHeaders imageHeaders = new HttpHeaders();
imageHeaders.setContentType(MediaType.IMAGE_PNG);

HttpEntity<Resource> imagePart =
        new HttpEntity<>(imageResource, imageHeaders);

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("image", imagePart);
parts.add("metadata", metadataPart);

webTestClient.post()
        .uri("/api/products/42/assets")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("products-upload-asset",
                requestParts(
                        partWithName("image").description("PNG or JPEG image"),
                        partWithName("metadata").description("JSON metadata")
                )
        ));
```

This snippet illustrates attaching media types per `HttpEntity`; imports, resource filenames, and converters should be adjusted to fit the project's payload types and WebTestClient setup. The outer Content-Type remains `multipart/form-data`.

### 8.2. REST Assured

REST Assured has multipart overloads that accept a part's content type:

```java
given(this.spec)
        .filter(document("products-upload-asset",
                requestParts(
                        partWithName("image").description("PNG or JPEG image"),
                        partWithName("metadata").description("JSON metadata")
                )))
        .multiPart("image", imageFile, "image/png")
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/products/42/assets")
        .then()
        .statusCode(201);
```

Check the exact overload against your project's REST Assured version. What matters is verifying that the Content-Type is actually attached to each part on the wire, not just passed in the test builder.

## 9. Explicitly Documenting Content-Type

Since `requestParts(...)` focuses on part names and descriptions, you can include the MIME type directly in the description:

```java
requestParts(
    partWithName("image")
        .description("Product image; Content-Type image/png or image/jpeg"),
    partWithName("metadata")
        .description("JSON metadata; Content-Type application/json")
);
```

If the table needs a dedicated column, create a contract table in Asciidoctor:

```adoc
=== Content-Type of Each Part

|===
|Part |Content-Type |Rule

|`image`
|`image/png`, `image/jpeg`
|Bytes must be a valid image in one of the two formats

|`metadata`
|`application/json`
|JSON with required `title` field
|===
```

This table clarifies the contract for clients. To keep the table from going stale, tests should verify each accepted media type and the rejected media types.

If you need a table auto-generated from test requests, you can build a custom snippet from `OperationRequestPart.getHeaders()`; the custom implementation must define its own output, template, and header handling. Do not assume `request-parts.adoc` has a Content-Type column by default.

## 10. Asciidoctor and Build/CI

You can include the snippets generated by tests:

```adoc
= Product Asset API
:toc: left

== Uploading Image and Metadata

=== Parts
include::{snippets}/products-upload-asset/request-parts.adoc[]

=== Metadata Body
include::{snippets}/products-upload-asset/request-part-metadata-body.adoc[]

=== Metadata Fields
include::{snippets}/products-upload-asset/request-part-metadata-fields.adoc[]

=== Media Type Contract
See the Content-Type table for each part in the multipart contract section.
```

With Gradle and the Asciidoctor plugin configured:

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
        +--> Verify outer Content-Type
        |
        +--> Verify individual part Content-Types
        |
        +--> requestParts / requestPartBody / requestPartFields
        |
        v
Generated snippets
        |
        v
Asciidoctor / Markdown export step
        |
        v
Verify and publish documentation
```

When the contract changes from PNG-only to PNG/JPEG, update controller validation, positive/negative tests, and documentation tables together. Do not manually edit generated snippets to make CI green. Spring REST Docs generates AsciiDoc by default; Markdown requires a separate template or conversion step.

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Request rejected for wrong outer Content-Type | Setting `image/png` on the whole request | Use `multipart/form-data`; set MIME types per part |
| Metadata fails to deserialize to DTO | Part lacks `application/json` or JSON body is invalid | Set content type and verify converter |
| `request-parts.adoc` lacks MIME type column | Default snippet describes parts, not a media type table | Document in description/contract table or custom snippet |
| `.png` file still rejected | Header or bytes do not match supported format | Check both MIME type and file signature |
| File declares valid MIME but fake bytes | Trusting client-supplied Content-Type | Add actual content verification |
| `requestHeaders(...)` only shows multipart | Documenting request-level headers | Document per-part MIME in contract table or custom snippet |
| JSON part test fails converter | JSON part has mismatched content type | Set `application/json` and verify converter module |
| Asciidoctor missing snippet | Test did not generate snippet or include name is wrong | Check operation ID and task dependencies |

## 12. Practice Exercise

With the `POST /api/products/{id}/assets` endpoint:

1. Create an `image` part with `image/png` and a `metadata` part with `application/json`. Confirm the outer request remains `multipart/form-data`.
2. Change `image`'s Content-Type to `text/plain`; write a test confirming the server rejects it per contract.
3. Send an `image/png` header with non-PNG bytes. Add file signature validation and a negative test.
4. Change metadata's Content-Type to `text/plain`; confirm the JSON DTO is not deserialized as a valid request.
5. Add `requestPartFields("metadata", ...)` to document `title` and `description`.
6. Write an Asciidoctor table listing accepted Content-Types for each part.
7. If an auto-generated table is required, design a custom snippet reading headers from `OperationRequestPart`.
8. Run documentation tests and negative tests before Asciidoctor renders docs in CI.

### Self-Assessment Questions

- How does the overall request's Content-Type differ from a part's Content-Type?
- Which layer does the boundary belong to?
- Which parameter of `MockMultipartFile` accepts the part's Content-Type?
- Does `requestParts(...)` automatically validate or generate a MIME type column?
- Why can a file with a `.png` filename and `image/png` header still not be a valid PNG image?
- When should you use `requestPartFields(...)` instead of only `requestParts(...)`?
- What must be checked when modifying the list of accepted MIME types?

**Remember:** `multipart/form-data` is the Content-Type of the overall request; each part can carry its own Content-Type. Setting MIME types in the request builder only creates headers for the test, while the endpoint must validate both media type and content. `requestParts(...)` documents parts; use a contract table or custom snippet if you need to publish each part's Content-Type in a dedicated column.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts and multipart documentation.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): body and fields of a JSON part.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): how Spring MVC converts part content using converters.
- [Spring Framework — `MultipartFile` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html): filename, content type, and uploaded file content.
