# `partWithName` and Describing Request Parts in Spring REST Docs

## 1. Role of `partWithName(...)`

A multipart request splits the request body into multiple named parts. Each part can carry a binary file, a JSON snippet, text, or another type of content. When documenting an upload operation, readers need to know which parts the API expects and the purpose of each part.

In **Spring REST Docs**, `partWithName("...")` creates a descriptor for a part matching its exact name in the multipart request. `requestParts(...)` accepts these descriptors and generates the `request-parts.adoc` snippet.

For example, the endpoint `POST /api/products/{id}/images` accepts two parts:

- `file`: the image to upload.
- `metadata`: JSON containing the image title and description.

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("Product image to upload"),
    partWithName("metadata")
        .description("JSON metadata of the image")
);
```

The standard API name is `partWithName(...)`, in `RequestDocumentation`. This method returns a descriptor for the part; `.description(...)` explains the part's meaning to the client. `requestParts(...)` aggregates the descriptors to document the operation's set of parts.

This lesson belongs to the **Request parts** chapter of SPRING_REST_DOCS: generating REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, then combining snippets with Asciidoctor/Markdown and build/CI.

After this lesson, you will be able to:

- Use `partWithName(...)` to accurately identify a part.
- Write concise descriptions with context about content and purpose.
- Distinguish part descriptors from field descriptors of JSON inside a part.
- Handle required, optional, and ignored parts.
- Organize shared descriptors, avoiding mismatched part names across tests, controllers, and documentation.

## 2. Part Names Must Match the Multipart Request

The name passed into `partWithName(...)` is the part name in the multipart body, typically represented by the `name` parameter of the `Content-Disposition` header.

Example request:

```http
POST /api/products/42/images HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="file"; filename="cover.png"
Content-Type: image/png

<binary image data>
------Boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Book Cover","description":"Cover image for the new edition"}
------Boundary--
```

The part names are `file` and `metadata`. Therefore, the descriptors must use these exact two names:

```java
requestParts(
    partWithName("file").description("Product image"),
    partWithName("metadata").description("JSON metadata")
);
```

The following variations are different and are not automatically equivalent:

- `partWithName("metadata")`
- `partWithName("meta")`
- `partWithName("Metadata")`

The part name must stay consistent across the client, controller, and test. If the controller uses `@RequestPart("metadata")`, the descriptor must also point to `metadata`.

### 2.1. Part Name Is Not the File Name

In a file upload part, `Content-Disposition` can have both `name` and `filename`:

```http
Content-Disposition: form-data; name="file"; filename="cover.png"
```

- `name="file"` is the part name, used in `partWithName("file")`.
- `filename="cover.png"` is the filename provided by the client; it is not the argument to `partWithName(...)`.

If a client changes the filename to `product-cover-final.png` while still sending a part named `file`, the descriptor does not need to change. Filename and related metadata should be documented separately when clients need to know about them.

### 2.2. Do Not Confuse Part Name with JSON Path

For a `metadata` part containing:

```json
{
  "title": "Book Cover",
  "description": "Cover image for the new edition"
}
```

`partWithName("metadata")` identifies **the entire part**. The `title` and `description` paths inside the JSON belong to the scope of `requestPartFields("metadata", ...)`, not arguments to `partWithName(...)`.

## 3. Writing Good Descriptions for Each Part

A part's description should answer three questions:

1. What type of data does the part contain?
2. What is that data used for in the operation?
3. Are there any important requirements the client needs to know right away?

Examples:

| Part Name | Weak Description | Better Description |
| --- | --- | --- |
| `file` | `File` | `Product image to upload` |
| `metadata` | `Data` | `JSON metadata describing the product image` |
| `document` | `Document` | `Signed contract PDF file` |
| `signature` | `Signature` | `Sender's signature image` |
| `attachments` | `List` | `Request attachment files` |

The description can specify formats if the format is part of the contract:

```java
partWithName("file")
    .description("Product image in PNG or JPEG format");
```

However, `.description(...)` only records information for readers. It does not validate MIME type, file contents, size, or binary signatures. These constraints must be checked in the endpoint and in HTTP tests.

### 3.1. Use Consistent Business Terminology

If the documentation refers to `product` as "product", use the same terminology across operations:

- `Product image to upload`
- `Metadata describing the product`
- `Document proving product origin`

Avoid descriptions that merely repeat the part name or use vague words like "data", "info", or "content" without explaining the role.

### 3.2. Keep Descriptions Short; Put Long Rules Separately

One short sentence is usually enough for the parts table:

```java
partWithName("file")
    .description("Product image to upload");
```

If more detailed explanation is needed, write it in the operation section of the Asciidoctor document: accepted formats, size limits, filename handling, virus scanning rules, or required metadata. Do not cram everything into a long, hard-to-read description.

## 4. Required, Optional, and Ignored Descriptors

`partWithName(...)` returns a descriptor with options describing part status.

### 4.1. Required Parts

```java
requestParts(
    partWithName("file")
        .description("Product image to upload"),
    partWithName("metadata")
        .description("JSON metadata of the image")
);
```

In strict `requestParts(...)`, a declared part is required by default. If the sample request omits that part, snippet generation can fail. This is a signal to reconcile the fixture with the API contract.

### 4.2. Optional Parts

Suppose `thumbnail` is only sent by the client when a preview image is provided:

```java
requestParts(
    partWithName("file")
        .description("Product image to upload"),
    partWithName("metadata")
        .description("JSON metadata of the image"),
    partWithName("thumbnail")
        .description("Preview image, if present")
        .optional()
);
```

`.optional()` allows the declared part to be absent in the sample request. It does not mean the part content is allowed to be empty, null, or malformed. Those rules must be defined separately for the contract.

### 4.3. Ignored Parts

A technical part can be acknowledged without being included in the table:

```java
requestParts(
    partWithName("file")
        .description("Product image to upload"),
    partWithName("metadata")
        .description("JSON metadata of the image"),
    partWithName("clientTrace")
        .description("Trace ID used for log correlation")
        .ignored()
);
```

`clientTrace` is declared to prevent treating it as an unhandled part in strict mode, but it does not appear as a row in the snippet. `.ignored()` does not remove the part from the request, does not prevent the server from reading it, and is not a data protection mechanism.

If an ignored part may be absent in the sample payload, combine `.optional()`:

```java
partWithName("clientTrace")
    .description("Trace ID if provided by the client")
    .optional()
    .ignored();
```

### 4.4. Strict and Relaxed Request Parts

If an operation allows unlisted extensible parts, you can use `relaxedRequestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedRequestParts;

relaxedRequestParts(
    partWithName("file").description("Product image"),
    partWithName("metadata").description("JSON metadata")
);
```

With relaxed mode, parts without descriptors are allowed to exist. Declared descriptors must still be present, unless optional. In exchange, tests no longer detect every new undocumented part.

| Mechanism | Declared Part | Extra Undeclared Part | Display |
| --- | --- | --- | --- |
| `requestParts(...)` | Checked against descriptor | Can cause test to fail | Shown, unless ignored |
| `requestParts(...)` + `.ignored()` | Acknowledged but omitted from table | Strict mode still detects | Ignored part not shown |
| `relaxedRequestParts(...)` | Checked against descriptor | Allowed to exist | Only non-ignored descriptors |
| `.optional()` | Allows descriptor to be absent in sample request | Does not affect extra parts | Does not hide the part |

Choose relaxed mode when the multipart contract truly permits extension. For operations with stable public parts, strict mode helps detect new parts so documentation can be updated.

## 5. Complete Example with MockMvc

Suppose the endpoint `POST /api/products/{id}/images` accepts:

- `file`: required image file.
- `metadata`: required JSON.
- `thumbnail`: optional preview file.

The endpoint returns `201 Created` on a valid upload. The project is configured with Spring Boot, JUnit 5, MockMvc, and `spring-restdocs-mockmvc`.

### 5.1. Creating `MockMultipartFile`

```java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile file = new MockMultipartFile(
        "file",
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

The first argument of `MockMultipartFile` is the part name. The second argument is the filename. Therefore, `"file"` must match `partWithName("file")`; `"cover.png"` is not the part name.

In real tests, use a valid PNG fixture if the endpoint checks file format or contents. Arbitrary mock bytes are only suitable for simple examples where the controller does not parse the image.

### 5.2. Generating the `request-parts` Snippet

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

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductImageUploadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProductImageParts() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                validPngBytes()
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

        mockMvc.perform(multipart("/api/products/{id}/images", 42)
                    .file(file)
                    .file(metadata)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("products-upload-image",
                        requestParts(
                                partWithName("file")
                                        .description("Product image to upload"),
                                partWithName("metadata")
                                        .description("JSON metadata describing the image"),
                                partWithName("thumbnail")
                                        .description("Preview image if present")
                                        .optional()
                        )));
    }

    private byte[] validPngBytes() {
        // Returns bytes of a valid PNG fixture in test resources.
        return TestFixtures.validPng();
    }
}
```

The imports and `TestFixtures` fixture are illustrative examples; replace them with your project's actual test resources. What matters is that the part names in `MockMultipartFile` must match the descriptors, and the request must pass through the documented operation.

After the test succeeds, Spring REST Docs generates snippets in:

```text
build/generated-snippets/
└── products-upload-image/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-parts.adoc
```

The names and number of additional snippets depend on configuration. `request-parts.adoc` is the output from `requestParts(...)`.

## 6. Organizing Shared Descriptors

When multiple tests document the same operation or variants of a multipart request, extract descriptors to avoid duplication and accidental drift.

```java
import org.springframework.restdocs.request.RequestPartDescriptor;

import static org.springframework.restdocs.request.RequestDocumentation.partWithName;

private static final RequestPartDescriptor[] PRODUCT_IMAGE_PARTS = {
        partWithName("file")
                .description("Product image to upload"),
        partWithName("metadata")
                .description("JSON metadata describing the image"),
        partWithName("thumbnail")
                .description("Preview image if present")
                .optional()
};
```

Then reuse them:

```java
.andDo(document("products-upload-image",
        requestParts(PRODUCT_IMAGE_PARTS)
));
```

Reusing descriptors is helpful when the same contract is tested across multiple scenarios. However, do not share descriptors across operations where part meanings differ just because they have the same name. Descriptions must fit the contract of the specific operation.

### 6.1. Organizing by Part Group

For large operations with many parts, you can group them in source code:

- Business parts: `file`, `metadata`.
- Supplementary parts: `thumbnail`, `attachments`.
- Technical parts: `clientTrace`.

These groups are purely a code organization technique. In HTTP multipart, all of them are still top-level parts of the request body unless a part's body contains its own nested structure such as JSON or an archive.

## 7. Part Descriptors Do Not Replace Documenting Part Contents

`partWithName("metadata")` only documents the `metadata` part at the multipart level. If that part contains JSON:

```json
{
  "title": "Book Cover",
  "description": "Cover image for the new edition"
}
```

then `requestParts(...)` does not automatically generate a table for the `title` and `description` fields.

There are three levels of documentation:

| API | Content | Snippet |
| --- | --- | --- |
| `requestParts(...)` | Name and meaning of each part | `request-parts.adoc` |
| `requestPartBody("metadata")` | Raw body of the part | `request-part-metadata-body.adoc` |
| `requestPartFields("metadata", ...)` | Fields inside the JSON part | `request-part-metadata-fields.adoc` |

Example:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

.andDo(document("products-upload-image",
        requestParts(PRODUCT_IMAGE_PARTS),
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

`requestPartBody` lets readers view a sample body. `requestPartFields` documents the JSON schema inside the part. These serve two different needs; only add them when API consumers need the corresponding information.

## 8. What Descriptions Do Not Automatically Validate

A description can state `PNG image up to 5 MB`, but `partWithName(...)` does not enforce those conditions. Separate HTTP tests or validation are needed for:

- Allowed content types.
- Whether the file content actually matches the MIME type.
- File size.
- Filename and allowed characters.
- Whether the metadata part is valid JSON.
- Required fields in metadata.
- Whether the filename extension is permitted.

Contract example:

| Part | Required | Content Type | Illustrative Rules |
| --- | --- | --- | --- |
| `file` | Yes | `image/png` or `image/jpeg` | Valid image file, max 5 MB |
| `metadata` | Yes | `application/json` | Non-empty `title` |
| `thumbnail` | No | `image/jpeg` | Preview file, max 1 MB |
| `clientTrace` | No | `text/plain` | Log correlation ID |

The conditions in the table are examples and must be replaced with the real contract. A suite of negative tests should check oversized files, unsupported MIME types, invalid JSON metadata, or missing titles.

## 9. Combining with Asciidoctor and Build/CI

The Asciidoctor document can include the snippets:

```adoc
= Product Image API
:toc: left

== Product Image Upload

=== Request Parts
include::{snippets}/products-upload-image/request-parts.adoc[]

=== Metadata Body
include::{snippets}/products-upload-image/request-part-metadata-body.adoc[]

=== Metadata Fields
include::{snippets}/products-upload-image/request-part-metadata-fields.adoc[]
```

Only include snippets that the tests are configured to generate. If the operation only calls `requestParts(...)`, there are no body or part fields snippets to include.

With Gradle and the Asciidoctor plugin configured, wire the documentation task to the snippet-generating tests:

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
requestParts descriptors
        |
        v
request-parts.adoc
        |
        v
Asciidoctor / Markdown export step
        |
        v
Verify and publish documentation
```

When a new part is added, strict `requestParts(...)` can fail tests if it is not yet documented. The team must decide whether to publish the part, intentionally ignore it, or update the contract. Do not manually edit generated snippets to make the build green.

Spring REST Docs generates AsciiDoc snippets by default. If the project publishes Markdown, a custom template or conversion step is required; `request-parts.md` is not produced by default.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Part not found | `MockMultipartFile` name differs from `partWithName(...)` | Synchronize names across request, controller, and descriptor |
| Test reports undocumented part | A new part exists but strict `requestParts(...)` has not declared it | Add descriptor, intentionally ignore, or relax per contract |
| Test reports missing part | Required descriptor was not sent in sample request | Add the part or `.optional()` if the contract allows it |
| Ignored part still in request | `.ignored()` only hides the row in the snippet | This is expected behavior; it does not remove the part |
| No metadata fields table | Only `requestParts(...)` was called | Use `requestPartFields("metadata", ...)` |
| No JSON body snippet | `requestPartBody("metadata")` was not called | Add it if a sample body is needed |
| Multipart endpoint does not receive file | Wrong part name, filename, or body construction | Check `Content-Disposition`, content type, and request builder |
| Asciidoctor reports missing include | Document includes a snippet not yet generated | Check operation id, test task, and output directory |

## 11. Practice Exercise

Based on `POST /api/products/{id}/images`:

1. Declare `file` and `metadata` using `partWithName(...)`; write descriptions that clearly convey the purpose of each part.
2. Add `thumbnail` as optional and run two tests with and without this part.
3. Add `clientTrace`, marked `.ignored()`. Verify the part is still sent but has no row in `request-parts.adoc`.
4. Change the request part name from `metadata` to `meta` without changing the descriptor. Observe the error, then fix it according to the contract.
5. Add JSON fields `title` and `description` in `metadata`; use `requestPartFields(...)` to describe the inside of the part.
6. Use `requestPartBody(...)` to include raw JSON and distinguish its purpose from the fields table.
7. Write negative tests for wrong MIME type, oversized file, and metadata missing `title`.
8. Include snippets in Asciidoctor and ensure CI runs tests before rendering.

### Self-Assessment Questions

- Does `partWithName("file")` refer to `name` or `filename` in `Content-Disposition`?
- What does a part's `.description(...)` help API consumers understand?
- How does `.optional()` differ from `.ignored()`?
- When should `relaxedRequestParts(...)` be used?
- Why doesn't `requestParts(...)` document JSON fields inside the `metadata` part?
- When should you use `requestPartBody(...)` versus `requestPartFields(...)`?
- Why doesn't the description `image/png` replace tests that validate file contents?

**Remember:** `partWithName(...)` identifies a part by its exact name in the multipart request; `.description(...)` explains the part's purpose; `requestParts(...)` aggregates descriptors and generates the parts table snippet. Part names must match the actual request, while JSON contents inside a part require `requestPartBody` or `requestPartFields` when the documentation needs that level of detail.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): how to document multipart parts and corresponding snippets.
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `partWithName`, `requestParts`, and `relaxedRequestParts`.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): documenting fields inside a JSON part.
