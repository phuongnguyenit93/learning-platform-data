# Documenting Multipart Requests with `requestParts`

## 1. What is a Multipart Request?

An HTTP request may need to send multiple types of content in a single call. For example, a product image upload feature needs to send a binary image file alongside JSON metadata such as image name, description, display order, or product ID. Sending everything as a plain JSON payload is unsuitable for binary file data; sending the file and metadata in two separate requests can make the upload workflow more complex.

`multipart/form-data` solves this problem by splitting the request body into multiple **parts**. Each part has its own name and can have its own headers and content type. For example:

- `image` part: image file, content type `image/png`.
- `metadata` part: JSON describing the image, content type `application/json`.

In **Spring REST Docs**, `requestParts(...)` generates a snippet describing the parts supported by an operation. Descriptors are created using `partWithName(...)`. An HTTP test using MockMvc, WebTestClient, or REST Assured sends an actual multipart request; Spring REST Docs matches the parts in the request against the descriptors and then generates `request-parts.adoc`.

This lesson belongs to the **Request parts** chapter of SPRING_REST_DOCS. After completing it, you will be able to:

- Understand the structure of a multipart request and the role of each part.
- Declare `requestParts(partWithName(...))` to document the name and purpose of a part.
- Use MockMvc to build a request containing a file and JSON metadata.
- Distinguish between `requestParts`, `requestPartBody`, and `requestPartFields`.
- Handle required, optional, ignored, and relaxed parts.
- Include multipart snippets in Asciidoctor and build/CI.

## 2. Structure of `multipart/form-data`

An upload request can be logically represented as follows:

```text
POST /api/images
Content-Type: multipart/form-data; boundary=...

Part: image
Content-Disposition: form-data; name="image"; filename="cover.png"
Content-Type: image/png

<bytes of the image file>

Part: metadata
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Book Cover",
  "description": "Cover image for the new edition"
}
```

Each part has at least a name. For a part containing a file, the `Content-Disposition` header usually includes `filename`; `Content-Type` indicates the content format. For a JSON metadata part, the body is JSON text and `Content-Type` is usually `application/json`.

| Part | Content | Example Content Type | Purpose |
| --- | --- | --- | --- |
| `image` | Image file bytes | `image/png` | Image to upload |
| `metadata` | JSON | `application/json` | Descriptive information for the image |
| `thumbnail` | Thumbnail image bytes | `image/jpeg` | Preview image, can be optional |

**The part name is part of the API contract.** If the server expects a part named `metadata`, a client sending `meta` will not be equivalent. The descriptor in Spring REST Docs must use the exact name sent in the multipart request.

## 3. `requestParts(...)` and `partWithName(...)`

Spring REST Docs provides two methods in `org.springframework.restdocs.request.RequestDocumentation`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
```

A basic descriptor:

```java
partWithName("image")
        .description("Image file to upload");
```

Grouping descriptors into a snippet:

```java
requestParts(
        partWithName("image")
                .description("Image file to upload"),
        partWithName("metadata")
                .description("JSON metadata of the image")
);
```

`requestParts(...)` generates the `request-parts.adoc` snippet, which contains a table describing the parts supported by the operation.

In strict mode:

- A part present in the request without a descriptor can cause the test to fail.
- A descriptor describing a required part that is missing from the request will also cause the test to fail.
- An `.optional()` descriptor allows the documented part to be absent in the sample request.
- An `.ignored()` descriptor acknowledges the part without including it in the snippet and avoids errors caused by the part lacking a description row.

For an operation that only needs to document certain parts, `relaxedRequestParts(...)` allows undocumented parts to appear without failing the test. Declared part descriptors must still be present, unless marked optional.

### 3.1. Required and Optional Parts

For example, the `thumbnail` part is only present in some requests:

```java
requestParts(
        partWithName("image")
                .description("Main image file"),
        partWithName("metadata")
                .description("JSON information of the image"),
        partWithName("thumbnail")
                .description("Preview image if provided by the client")
                .optional()
);
```

`.optional()` here applies to **the presence of the part**. It does not mean the part's body is allowed to be an empty string or JSON `null`. Those are different content rules and need to be documented/tested separately.

### 3.2. Parts Acknowledged but Excluded from the Snippet

If a request contains a known technical part that the operation does not need to display:

```java
partWithName("clientTrace")
        .description("Trace ID sent by the client")
        .ignored();
```

This part is acknowledged but does not become a row in `request-parts.adoc`. If it may be absent in the sample payload, `.optional()` and `.ignored()` can be combined.

### 3.3. Strict vs. Relaxed

| API | Undeclared Part | Declared Part Missing |
| --- | --- | --- |
| `requestParts(...)` | Can cause the test to fail | Must be present, unless optional |
| `relaxedRequestParts(...)` | Allowed to exist | Must be present, unless optional |
| `.ignored()` on descriptor | Part is acknowledged and not displayed | Follows the descriptor's presence rules |
| `.optional()` on descriptor | Does not change handling of extra parts | Allows the documented part to be absent |

Only use relaxed mode when the contract intentionally allows additional parts or the operation is illustrating a subset. For public APIs with a stable structure, strict mode helps detect new parts that need review.

## 4. Creating Multipart Requests with MockMvc

The following example assumes an endpoint `POST /api/images` that accepts two parts:

- `image`: required PNG file.
- `metadata`: required JSON.

The endpoint returns `201 Created` when the upload succeeds. The project is configured with Spring Boot, JUnit 5, MockMvc, and the `spring-restdocs-mockmvc` dependency.

### 4.1. Building the Parts in a Test

Use `MockMultipartFile` to create a file part and a JSON part:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile image = new MockMultipartFile(
        "image",
        "cover.png",
        MediaType.IMAGE_PNG_VALUE,
        imageBytes
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

The first parameter of `MockMultipartFile` is the **part name**. It must match the name accepted by the controller and documented by the descriptor. The file name is the second parameter; the content type is the third parameter.

### 4.2. Attaching `requestParts(...)` to an Operation

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ImageUploadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentImageUploadParts() throws Exception {
        byte[] imageBytes = new byte[] { 1, 2, 3, 4 };

        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                imageBytes
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

        mockMvc.perform(multipart("/api/images")
                    .file(image)
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("images-upload",
                        requestParts(
                                partWithName("image")
                                        .description("PNG image file to upload"),
                                partWithName("metadata")
                                        .description("JSON metadata of the image")
                        )));
    }
}
```

The byte array in the example is just mock data to demonstrate the test flow. For applications that validate real file formats, use a valid image fixture instead of four arbitrary bytes. The HTTP status assertion must match the contract of the actual endpoint.

When the test runs successfully, Spring REST Docs generates the snippets:

```text
build/generated-snippets/
└── images-upload/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-parts.adoc
```

Additional snippets such as cURL or HTTPie depend on configuration. `request-parts.adoc` is the parts table generated from `requestParts(...)`.

## 5. How `requestParts` Differs from `requestPartBody` and `requestPartFields`

A multipart request has multiple levels of information. Documenting only the part names is not the same as documenting the body inside those parts.

| API | Purpose | Snippet |
| --- | --- | --- |
| `requestParts(...)` | Documents the parts and the meaning of each part | `request-parts.adoc` |
| `requestPartBody("metadata")` | Includes the body of the `metadata` part in the documentation | `request-part-metadata-body.adoc` |
| `requestPartFields("metadata", ...)` | Documents the JSON fields inside the `metadata` part | `request-part-metadata-fields.adoc` |

### 5.1. Recording the Body of a JSON Part

When you want readers to see the raw JSON content of the `metadata` part:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

.andDo(document("images-upload",
        requestParts(
                partWithName("image").description("Image file"),
                partWithName("metadata").description("JSON metadata")
        ),
        requestPartBody("metadata")
));
```

The part body snippet lets readers see a sample payload for that specific part. It is useful when the JSON structure is meaningful but does not yet require a field-by-field description table.

### 5.2. Documenting Fields Inside a JSON Part

If `metadata` has a schema that clients need to understand, use `requestPartFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

.andDo(document("images-upload",
        requestParts(
                partWithName("image").description("Image file"),
                partWithName("metadata").description("JSON metadata")
        ),
        requestPartFields("metadata",
                fieldWithPath("title")
                        .description("Image title"),
                fieldWithPath("description")
                        .description("Image description")
                        .optional()
        )
));
```

`requestPartFields("metadata", ...)` checks the JSON structure **inside the `metadata` part**. The descriptors here are `FieldDescriptor` instances, so you use `fieldWithPath(...)` just like when documenting a regular JSON request. It does not document the part names of the multipart request; that role still belongs to `requestParts(...)`.

Generated snippets:

```text
request-parts.adoc
request-part-metadata-body.adoc
request-part-metadata-fields.adoc
```

Not every operation needs all three. Choose based on what the reader needs:

- Only need to know that the operation accepts a file and metadata: `requestParts(...)`.
- Need to see sample JSON inside `metadata`: add `requestPartBody("metadata")`.
- Need to understand the JSON schema: add `requestPartFields("metadata", ...)`.

### 5.3. Part Names Across APIs Must Match

If a part is created with the name `metadata`, the calls must be consistent:

```java
requestParts(partWithName("metadata").description("JSON metadata"));

requestPartBody("metadata");

requestPartFields("metadata",
        fieldWithPath("title").description("Image title"));
```

Renaming it in one place to `meta` will point to a different part or fail to find the corresponding part.

## 6. Using WebTestClient and REST Assured

Descriptors used for `requestParts(...)` are not tied specifically to MockMvc. Each integration module has its corresponding way to attach the snippet.

### 6.1. WebTestClient

A multipart request can be built using `BodyInserters.fromMultipartData(...)`:

```java
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("image", imageResource);
parts.add("metadata", metadataResource);

webTestClient.post()
        .uri("/api/images")
        .body(BodyInserters.fromMultipartData(parts))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .consumeWith(document("images-upload",
                requestParts(
                        partWithName("image").description("PNG image file"),
                        partWithName("metadata").description("JSON metadata")
                )));
```

When uploading files, the `Resource` containing the file should provide an appropriate filename if the endpoint requires a filename in `Content-Disposition`. The content type of each part should also be configured according to how `HttpEntity` or the corresponding resource is built in the application.

### 6.2. REST Assured

With REST Assured, the documentation filter is placed on the request specification:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(this.spec)
        .filter(document("images-upload",
                requestParts(
                        partWithName("image").description("PNG image file"),
                        partWithName("metadata").description("JSON metadata")
                )))
        .multiPart("image", imageFile)
        .multiPart("metadata", metadataJson, "application/json")
        .when()
        .post("/api/images")
        .then()
        .statusCode(201);
```

How parts are constructed specifically depends on the REST Assured overload used and the library version. The key requirement is that the sent part names must match the descriptors and documentation must be attached to the actual request.

## 7. Optional, Ignored, and Relaxed for Request Parts

### 7.1. Optional Part

For example, `thumbnail` is not required:

```java
requestParts(
        partWithName("image").description("Main image"),
        partWithName("metadata").description("JSON metadata"),
        partWithName("thumbnail")
                .description("Preview image if present")
                .optional()
);
```

If an upload test does not send `thumbnail`, the snippet can still be generated because the descriptor is marked optional. If the test sends this part, the descriptor still documents it.

### 7.2. Ignored Part

```java
requestParts(
        partWithName("image").description("Main image"),
        partWithName("metadata").description("JSON metadata"),
        partWithName("clientTrace")
                .description("Tracing ID")
                .ignored()
);
```

`clientTrace` is acknowledged but does not appear in the request parts table. If the part may be absent, `.optional()` should be combined according to the contract. `.ignored()` does not make a part optional, nor does it remove the part from the actual request.

### 7.3. Relaxed Request Parts

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedRequestParts;

relaxedRequestParts(
        partWithName("image").description("Main image"),
        partWithName("metadata").description("JSON metadata")
);
```

With relaxed mode, undocumented parts are allowed to exist. Declared parts must still be present if not optional. Choose relaxed mode when an operation intentionally focuses on a subset of parts or allows extensible parts by contract. Do not use it to hide a new business-meaningful part that the documentation should expose.

## 8. Content Type Checking and Validation of Each Part

`requestParts(...)` documents the name and purpose of a part. It does not automatically guarantee that:

- The `image` part is actually a valid PNG image.
- The `metadata` part is valid JSON or contains all required fields.
- The file does not exceed the size limit.
- The filename, extension, and MIME type match the actual content.
- An optional part satisfies related conditions when present.

These checks need to be implemented in the endpoint and verified with separate HTTP tests. For example, JSON metadata can be checked with `requestPartFields(...)`, but business rules such as a non-empty title or a maximum description length still require validation.

A contract table for the upload operation:

| Part | Required | Content Type | Rules |
| --- | --- | --- | --- |
| `image` | Yes | `image/png` | Valid PNG file, max 5 MB |
| `metadata` | Yes | `application/json` | JSON with required `title` |
| `thumbnail` | No | `image/jpeg` | Preview image, max 1 MB |
| `clientTrace` | No | `text/plain` | Used only for log correlation |

The size values, MIME types, and rules in the table are examples; replace them with your API's real contract.

For `metadata`, you can add:

```java
requestPartFields("metadata",
        fieldWithPath("title")
                .description("Image title"),
        fieldWithPath("description")
                .description("Image description")
                .optional()
);
```

You should add negative tests to verify the server handles missing `image`, invalid JSON metadata, unsupported MIME types, or oversized files properly.

## 9. Asciidoctor and Build/CI

After tests generate the snippets, the Asciidoctor document can include the parts table:

```adoc
= Image API
:toc: left

== Image Upload

=== Request Parts

include::{snippets}/images-upload/request-parts.adoc[]

=== JSON Metadata

include::{snippets}/images-upload/request-part-metadata-body.adoc[]

=== Metadata Fields

include::{snippets}/images-upload/request-part-metadata-fields.adoc[]
```

Only include snippets that the tests actually generate. If the operation only uses `requestParts(...)`, the part body and part fields snippets will not exist.

With Gradle and the Asciidoctor plugin configured, the documentation task needs to depend on the test task that generates snippets:

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
Multipart HTTP test
        |
        v
requestParts / requestPartBody / requestPartFields
        |
        v
Generated snippets
        |
        v
Asciidoctor / Markdown conversion step
        |
        v
Verify and publish documentation
```

When a new part is added to an endpoint, strict `requestParts(...)` can cause the test to fail if the part is not yet documented. The team needs to decide whether to publish the part, intentionally ignore it, or update the contract. Do not manually edit generated snippets to make CI green.

Spring REST Docs generates AsciiDoc snippets by default. If you want to publish Markdown, you need a separately configured Markdown template or conversion step; there is no `request-parts.md` file by default.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Part not found in descriptor | Part name in `MockMultipartFile` differs from `partWithName(...)` | Synchronize part names across request, controller, and descriptor |
| Test reports undocumented part | Multipart request has a new part not yet declared in strict `requestParts(...)` | Add a descriptor, intentionally ignore, or relax per contract |
| Test reports missing part | Required descriptor was not sent in the sample request | Add the part or mark `.optional()` if the contract allows it to be omitted |
| Ignored part still present in HTTP request | `.ignored()` only hides the row in the snippet | This is expected behavior; it does not remove the part from the request |
| JSON metadata lacks a fields table | Only `requestParts(...)` was called | Add `requestPartFields("metadata", ...)` |
| Missing metadata body snippet | `requestPartBody("metadata")` was not called | Add the snippet if the docs need a sample body |
| `requestPartFields` reports undocumented field | JSON inside the part has a new field or wrong path | Update field descriptors to match the part's JSON |
| Multipart endpoint does not receive file | Wrong part name, missing filename, or malformed body construction | Check `Content-Disposition`, content type, and request construction |
| Asciidoctor reports missing include | Including a snippet not generated by tests | Check operation name, test task, and configured snippets |

## 11. Practice Exercise

Based on the `POST /api/images` endpoint:

1. Create two required parts `image` and `metadata`, then generate `request-parts.adoc`.
2. Add `thumbnail` as an optional part. Run one test with `thumbnail` and one test without sending `thumbnail`.
3. Add `clientTrace` and mark it `.ignored()`. Verify the part is still sent to the endpoint but does not appear in the table.
4. Add `title` and `description` fields to the JSON metadata. Use `requestPartFields("metadata", ...)` to generate the fields table.
5. Use `requestPartBody("metadata")` to include the raw JSON body.
6. Intentionally rename the part from `metadata` to `meta` in the request without changing the descriptor. Observe the error, then update the contract or fixture appropriately.
7. Write negative tests for an oversized file, wrong content type, and metadata missing `title`.
8. Include the parts and metadata snippets in Asciidoctor; verify CI runs tests before rendering documentation.

### Self-Assessment Questions

- Which level of a multipart request does `requestParts(...)` document?
- What part of the request must `partWithName("metadata")` match?
- How do `.optional()` and `.ignored()` differ on a part?
- When should `relaxedRequestParts(...)` be used?
- Why does `requestParts(...)` not replace `requestPartFields(...)`?
- What different information do `requestPartBody("metadata")` and `requestPartFields("metadata", ...)` generate?
- Why are negative tests needed for MIME type and file size?

**Remember:** `requestParts(...)` documents **the parts** of a multipart request by name and meaning. When you need to document the contents of a part, use `requestPartBody(...)` to display the body or `requestPartFields(...)` to describe the fields inside. Combining these snippets with real upload tests, validation, and build/CI keeps multipart request documentation aligned with the API contract.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): `requestParts`, `relaxedRequestParts`, request part body, and request part fields.
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `requestParts`, `relaxedRequestParts`, and `partWithName`.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): documenting JSON payload fields.
