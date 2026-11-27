# RequestPartFields for Fields in a JSON Part

## 1. When a multipart request has a part containing JSON

An upload endpoint often accepts multiple pieces of data within the same HTTP request. For example, the client sends an image file and a JSON part containing the image's metadata. This is a **multipart/form-data** request:

- the `image` part contains the binary file;
- the `metadata` part contains JSON describing the title, description, image category, and copyright information.

With **Spring REST Docs**, `requestPartFields(partName, descriptors...)` is used to document the fields inside the payload of a request part. This API belongs to `PayloadDocumentation` and works similarly to `requestFields(...)`, except its scope is limited to the payload of the specified part.

This lesson focuses on `requestPartFields` and distinguishes between three levels of multipart documentation:

| Goal | API | Generated content |
| --- | --- | --- |
| Describe which parts are sent in the multipart request | `requestParts(...)` with `partWithName(...)` | Table of part names and descriptions |
| Display the body of a part | `requestPartBody("metadata")` | Snippet containing the body of the metadata part |
| Describe each field in the JSON part | `requestPartFields("metadata", ...)` | Table of fields of the JSON metadata part |

After this lesson, you will be able to:

- create a multipart request containing a file and JSON using MockMvc;
- use `requestPartFields` to document fields inside a JSON part;
- understand strict validation rules as well as optional, ignored, and relaxed fields;
- generate dedicated body and field snippets for a part;
- structure Asciidoctor documentation and integrate snippet generation into build/CI;
- identify errors caused by mismatched part names, incorrect content types, invalid JSON, or mismatched field paths.

## 2. API contract example

Suppose the `POST /images` endpoint accepts two parts:

```text
POST /images
Content-Type: multipart/form-data

Part: image
  Content-Type: image/png
  Filename: cover.png
  Body: bytes of the image file

Part: metadata
  Content-Type: application/json
  Body:
```

```json
{
  "title": "Product cover image",
  "description": "Image showcasing the product in the store",
  "category": "PRODUCT",
  "copyright": {
    "owner": "Example Store",
    "license": "INTERNAL"
  }
}
```

Each part is a separate section of the multipart request. The `image` part is processed as a file; the `metadata` part has a JSON media type and contains a structured object.

The metadata field table will consist of:

| Path | Meaning |
| --- | --- |
| `title` | Image title |
| `description` | Image description |
| `category` | Image category |
| `copyright.owner` | Copyright owner |
| `copyright.license` | License type |

The key point is that these paths are relative to the **JSON root of the metadata part**. Do not write `metadata.title` or `metadata.copyright.owner` in `requestPartFields("metadata", ...)`, because the part name is already specified separately in the first argument.

## 3. Distinguishing requestParts, requestPartBody, and requestPartFields

The three APIs address complementary needs.

### 3.1. Describing the presence and purpose of each part

`requestParts(...)` belongs to `RequestDocumentation`. It describes the parts supported by the endpoint:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("image")
        .description("Image file to upload"),
    partWithName("metadata")
        .description("JSON metadata of the image")
)
```

The generated snippet is named `request-parts.adoc`. It answers the question "which parts does the request have?", without listing fields inside the JSON metadata.

### 3.2. Capturing the body of a part

`requestPartBody("metadata")` generates a snippet containing the body of the selected part:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata")
```

For the metadata part, the generated snippet is named `request-part-metadata-body.adoc`. It is useful when the documentation needs to display the raw sample JSON.

### 3.3. Describing fields in a JSON part

`requestPartFields("metadata", ...)` generates a field table:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields(
    "metadata",
    fieldWithPath("title").description("Image title"),
    fieldWithPath("description").description("Image description"),
    fieldWithPath("category").description("Image category")
)
```

The generated snippet is named `request-part-metadata-fields.adoc`. When using `requestPartFields`, Spring REST Docs validates the payload of the metadata part against the descriptors. It does not document the file bytes of the image part.

## 4. Complete example with MockMvc

The example below uses JUnit 5, Java 17+, Spring MVC Test, MockMvc, and Spring REST Docs. The controller accepts a file and JSON metadata; file storage handling is simplified to focus on how to document multipart requests.

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
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ImageUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new ImageUploadController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadImageWithJsonMetadata() throws Exception {
        MockMultipartFile image = new MockMultipartFile(
                "image",
                "cover.png",
                MediaType.IMAGE_PNG_VALUE,
                "fake-png-content".getBytes()
        );

        String metadataJson = """
                {
                  "title": "Product cover image",
                  "description": "Image showcasing the product in the store",
                  "category": "PRODUCT",
                  "copyright": {
                    "owner": "Example Store",
                    "license": "INTERNAL"
                  }
                }
                """;

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                metadataJson.getBytes()
        );

        this.mockMvc.perform(multipart("/images")
                        .file(image)
                        .file(metadata)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("images-upload",
                        requestParts(
                                partWithName("image")
                                        .description("PNG image file to upload"),
                                partWithName("metadata")
                                        .description("JSON metadata describing the image")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Image title"),
                                fieldWithPath("description")
                                        .description("Image description"),
                                fieldWithPath("category")
                                        .description("Image category"),
                                fieldWithPath("copyright.owner")
                                        .description("Copyright owner"),
                                fieldWithPath("copyright.license")
                                        .description("License type")
                        )
                ));
    }

    @RestController
    static class ImageUploadController {

        @PostMapping(
                value = "/images",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<Map<String, String>> upload(
                @RequestPart("image") MultipartFile image,
                @RequestPart("metadata") Map<String, Object> metadata) {

            if (image.isEmpty()) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.status(201)
                    .body(Map.of("id", "img-100"));
        }
    }
}
```

### 4.1. Why does metadata need content type application/json?

When creating `MockMultipartFile` for the metadata part, set:

```java
new MockMultipartFile(
    "metadata",
    "",
    MediaType.APPLICATION_JSON_VALUE,
    metadataJson.getBytes()
)
```

The part name is `metadata` and the media type is `application/json`. This tells Spring MVC that the part has JSON content so it can convert it to the parameter type declared in `@RequestPart("metadata")`.

If the part is sent as `text/plain` or without an appropriate media type, conversion to a `Map` or DTO may fail before REST Docs runs documentation. That is a binding/HTTP handling error, not a `requestPartFields` error.

### 4.2. Why use RestDocumentationRequestBuilders.multipart?

The static import in the example is:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
```

Spring REST Docs' multipart builder supports documentation integration for requests built with MockMvc. Use the correct API import for this MockMvc example; do not confuse it with multipart builders intended for other test client types.

### 4.3. Why does the controller accept a Map?

The example uses `@RequestPart("metadata") Map<String, Object>` to make it clear that the JSON part is converted into an object. In a real project, you should use a strongly typed DTO with validation, such as `ImageMetadata`, to protect the contract. REST Docs reads the multipart payload sent in the test; it does not require using a Map in the controller.

## 5. Reading the generated snippets

With the operation identifier `images-upload`, the relevant snippets are typically written to `build/generated-snippets/images-upload/`:

| Snippet | Source | Content |
| --- | --- | --- |
| `request-parts.adoc` | `requestParts(...)` | Table of image and metadata parts |
| `request-part-metadata-body.adoc` | `requestPartBody("metadata")` | JSON body of the metadata part |
| `request-part-metadata-fields.adoc` | `requestPartFields("metadata", ...)` | Table of fields in the JSON metadata |
| `http-request.adoc` | Default HTTP request snippet | Executed multipart request |
| `http-response.adoc` | Default HTTP response snippet | HTTP response of the endpoint |

Part snippet names are derived from the part name. For example, part `metadata` produces `request-part-metadata-fields.adoc`; part `manifest` will produce `request-part-manifest-fields.adoc`.

### 5.1. Embedding in Asciidoctor

Example `src/docs/asciidoc/images.adoc`:

```asciidoc
= Image API
:toc: left

== POST /images

Upload an image file along with JSON metadata.

=== Request parts

include::{snippets}/images-upload/request-parts.adoc[]

=== Sample JSON metadata

include::{snippets}/images-upload/request-part-metadata-body.adoc[]

=== Metadata fields

include::{snippets}/images-upload/request-part-metadata-fields.adoc[]

=== HTTP response

include::{snippets}/images-upload/http-response.adoc[]
```

The `request-parts` table explains the role of each part. The body snippet shows readers the sample JSON. The field table clarifies the schema and type/meaning of each field through descriptions and is verified by tests.

If only the field table is needed, `requestPartBody` can be omitted. If only listing the parts without documenting the JSON content is needed, `requestParts` may be sufficient. Choose snippets based on reader needs rather than always adding every snippet type.

## 6. Strict rules of requestPartFields

By default, `requestPartFields` operates in strict mode for the selected part's payload:

- If the JSON contains a field without a descriptor, the test fails.
- If a descriptor documents a required field that is absent from the JSON, the test fails.
- If a field is marked `optional()`, that field may be absent.
- If a descriptor is a subsection, the descendants of that branch are considered documented in the current snippet.

For example, if metadata is updated with:

```json
{
  "title": "Cover image",
  "description": "Product image",
  "category": "PRODUCT",
  "visibility": "PUBLIC"
}
```

Yet the table only lists `title`, `description`, and `category`, a strict test can fail because `visibility` has not been documented. This is a good signal for the team to update the documentation when the contract changes.

### 6.1. optional()

If `description` is not required:

```java
fieldWithPath("description")
    .optional()
    .description("Additional description for the image, if provided")
```

Only use `optional()` when the contract allows clients to omit the field. Do not use it as a workaround to make a test pass when the fixture is wrong or a path is misspelled.

### 6.2. ignored()

If there is a known internal field that you do not want to appear in the table:

```java
fieldWithPath("internalSource")
    .ignored()
```

The field is treated as intentionally ignored and does not appear in the snippet. Only use this for fields that genuinely do not belong in public documentation; do not overuse it to hide an unreviewed schema change.

### 6.3. relaxedRequestPartFields()

If documenting only a subset of fields in a specific scenario, you can use:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestPartFields;

relaxedRequestPartFields(
    "metadata",
    fieldWithPath("title").description("Image title"),
    fieldWithPath("category").description("Image category")
)
```

In relaxed mode, undocumented fields do not cause the test to fail. Declared descriptors are still checked according to required/optional rules. This is an option for documentation focusing on just a few fields, though the ability to detect new fields in the part is reduced compared to strict mode.

## 7. JSON parts with nested objects and arrays

`requestPartFields` uses the same path syntax as payload documentation. For example, suppose metadata contains:

```json
{
  "title": "Cover image",
  "dimensions": {
    "width": 1600,
    "height": 900
  },
  "tags": [
    "product",
    "campaign"
  ],
  "variants": [
    {
      "name": "thumbnail",
      "format": "WEBP"
    },
    {
      "name": "original",
      "format": "PNG"
    }
  ]
}
```

The paths can be documented as:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Image title"),
    fieldWithPath("dimensions.width")
        .description("Image width in pixels"),
    fieldWithPath("dimensions.height")
        .description("Image height in pixels"),
    fieldWithPath("tags")
        .description("List of image tags"),
    fieldWithPath("variants[].name")
        .description("Variant name"),
    fieldWithPath("variants[].format")
        .description("File format of the variant")
)
```

A dot denotes a nested object; `[]` denotes array elements. Paths are resolved from the **JSON part root**, without the `metadata` part name prefix.

If a large nested object should be summarized, you can use `subsectionWithPath("dimensions")` in the descriptor to describe the entire branch. When finer detail is needed, add the corresponding fields in a separate snippet or design the table so important parts are checked strictly. Do not declare a subsection covering an entire branch while expecting that same snippet to catch every new child field.

## 8. Part names and paths must match the actual request

`requestPartFields("metadata", ...)` extracts the payload from the part named `metadata`. If the actual request sends the name `meta`, REST Docs will not automatically infer that they are the same part. Part names are typically determined by:

- the name in `MockMultipartFile("metadata", ...)`;
- the client's part name;
- the name in the controller parameter `@RequestPart("metadata")`;
- the name passed to `requestPartFields("metadata", ...)`.

These names must match according to the contract.

Another common mistake is using a full path that includes the part name:

```java
// Incorrect: the part name is already specified separately.
requestPartFields("metadata",
    fieldWithPath("metadata.title").description("Title")
);

// Correct: the path starts from the JSON root of the part.
requestPartFields("metadata",
    fieldWithPath("title").description("Title")
);
```

If the path does not match the JSON, the test may report missing documented fields or undocumented fields. Inspect the actual JSON of the part before changing descriptors.

## 9. Using requestPartFields with WebTestClient and REST Assured

The `requestPartFields` API resides in `PayloadDocumentation`, so descriptors do not depend specifically on MockMvc. How the multipart request is constructed and how `document` is attached varies by test client.

### 9.1. WebTestClient

Example creating a multipart body with `BodyInserters.fromMultipartData`:

```java
MultiValueMap<String, Object> multipartData = new LinkedMultiValueMap<>();
multipartData.add("image", imageResource);
multipartData.add("metadata", metadataMap);

webTestClient.post()
    .uri("/images")
    .body(BodyInserters.fromMultipartData(multipartData))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("images-upload",
        requestPartFields("metadata",
            fieldWithPath("title").description("Image title"),
            fieldWithPath("category").description("Image category")
        )
    ));
```

`webTestClient` must be configured with the Spring REST Docs documentation filter before performing the exchange. The variables `imageResource`, `metadataMap`, and the client are test data/configuration prepared in advance. To create a reliable multipart file, you can use `ByteArrayResource` overriding `getFilename()`.

### 9.2. REST Assured

With REST Assured, use `multiPart` to send the file and JSON part, then attach snippets via the filter:

```java
Map<String, Object> metadata = new HashMap<>();
metadata.put("title", "Product cover image");
metadata.put("category", "PRODUCT");

RestAssured.given(this.spec)
    .accept("application/json")
    .filter(document("images-upload",
        requestPartFields("metadata",
            fieldWithPath("title").description("Image title"),
            fieldWithPath("category").description("Image category")
        )
    ))
    .multiPart("image", new File("cover.png"), "image/png")
    .multiPart("metadata", metadata)
    .when()
    .post("/images")
    .then()
    .statusCode(201);
```

The snippets above illustrate where the handler is placed. A complete test needs to set up the server/spec/client and dependencies according to the project configuration. The JSON part needs to be sent with an appropriate media type and serialization so the payload observed by REST Docs is the expected JSON.

## 10. Common errors

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Part `metadata` not found | Part name in request differs from `requestPartFields` argument | Align names across `MockMultipartFile`, client, controller, and descriptor |
| Cannot document fields | Path has `metadata.` prefix even though part is already selected | Use relative path from JSON part root |
| JSON part fails to convert | Wrong media type or invalid JSON body | Use `application/json` and verify valid JSON |
| Test reports undocumented fields | Payload has new field or descriptor is missing | Add descriptor or intentionally use subsection/ignored |
| Test reports missing required field | Descriptor path is wrong or field is actually absent | Check JSON; mark optional if contract allows |
| Only request-parts snippet exists, no field table | Only `requestParts(...)` was called | Add `requestPartFields(...)` |
| Body snippet exists without field table | Only `requestPartBody(...)` was called | Add `requestPartFields(...)` |
| No snippet files after test | Test never reached `document`, wrong operation ID, or different output directory | Check assertions, `document(...)`, and output configuration |
| Empty array causes fields inside array not to be found | Fixture has no element containing path `items[].x` | Generate schema from test with elements; test empty array separately |

## 11. Asciidoctor and CI integration

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

In CI, verify that:

1. Multipart tests run successfully and reach the `document(...)` handler.
2. Part names in the request match the part name in `requestPartFields`.
3. JSON parts have an appropriate content type and valid payload.
4. Strict field tables catch new fields or missing required fields.
5. Asciidoctor reads the exact snippet directory just generated.
6. Body/field snippets are included with the exact names in the documentation.

With Maven, the snippet directory is typically `target/generated-snippets`; the documentation compilation step must run after the tests that generate snippets.

## 12. Hands-on exercise

Extend `ImageUploadDocumentationTest`:

1. **Create multipart:** send the `image` file part and `metadata` JSON part, setting the correct content type for each part.
2. **Document parts:** use `requestParts(...)` to describe the purpose of `image` and `metadata`.
3. **Document body:** use `requestPartBody("metadata")` to generate the JSON snippet.
4. **Document fields:** use `requestPartFields("metadata", ...)` to describe `title`, `description`, `category`, and `copyright`.
5. **Test a new field:** add `metadata.visibility` without declaring a descriptor. Observe the strict test fail; then update the documentation.
6. **Test optional:** remove `description` from JSON and use `optional()` per contract; remove optional to observe the result.
7. **Nested paths:** add `dimensions.width` and `variants[].format` and document them using relative paths.
8. **Rename part:** change `metadata` to `details` in the request; synchronize the controller, `requestPartBody`, and `requestPartFields`.
9. **Build documentation:** run `./gradlew clean test asciidoctor` in the configured project and verify snippets are included.

**Completion criteria:** you can distinguish between the part table, part body, and part field table; generate the `request-part-metadata-fields.adoc` snippet; explain paths relative to the JSON part root; and use strict/optional/relaxed appropriately according to the contract.

## 13. Self-check questions

**1. What does `requestPartFields("metadata", ...)` document?**

It documents the fields inside the payload of the part named `metadata` in a multipart request.

**2. What is the generated snippet named?**

For the `metadata` part, the field table is named `request-part-metadata-fields.adoc`. The part body is named `request-part-metadata-body.adoc`.

**3. Do you need to write `metadata.title` in the descriptor?**

No. The part name is already a separate argument. Field paths start from the JSON root of the part, so use `title`.

**4. How does requestParts differ from requestPartFields?**

`requestParts` describes the list of parts in a multipart request; `requestPartFields` describes the fields in the JSON/body of a specific part.

**5. When should relaxedRequestPartFields be used?**

When documentation only focuses on a subset of fields and accepts undocumented fields being present. For contracts that need to detect schema drift, prefer strict mode.

**6. Does requestPartFields document the bytes of an image file?**

No. It documents fields of a part payload. A file part can be described by its name, purpose, and metadata using `requestParts`; do not put binary image content into the JSON metadata table.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, request part body, request part fields, strict/relaxed, and snippet names.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): signatures of `requestPartFields` and `relaxedRequestPartFields`.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): test configuration, snippets, and documentation integration.
