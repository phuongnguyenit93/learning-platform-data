# partFields and Describing Part Structure in Spring REST Docs

## 1. How is a multipart request structured?

Many endpoints accept **multipart/form-data** payloads. A single request can carry multiple parts, each with its own name, headers, and body. For example, a document upload endpoint receives a `file` part containing a PDF file and a `metadata` part containing JSON describing the document.

Spring REST Docs provides two levels of description that must be distinguished:

- `requestParts(...)` together with `partWithName(...)` describes the **part structure**: part names, purposes, and whether a part is required.
- `requestPartFields(...)` describes the **fields inside a part's payload**, typically used for JSON parts.
- `requestPartBody(...)` generates a snippet containing the body of a part to present a sample payload.

The phrase "partFields" in the lesson title refers to the group of features describing parts and part fields. In the current Spring REST Docs API, there is no generic method named `partFields(...)`. Use the right method for each scope:

| Scope | Correct API | Output |
| --- | --- | --- |
| List of parts in a multipart request | `requestParts(partWithName(...), ...)` | `request-parts.adoc` |
| Fields inside a JSON part | `requestPartFields("metadata", ...)` | `request-part-metadata-fields.adoc` |
| Body of a part | `requestPartBody("metadata")` | `request-part-metadata-body.adoc` |

After this lesson, you will be able to document multipart structures, describe nested JSON fields, choose strict/relaxed mode, mark parts or fields optional, and integrate snippets into Asciidoctor/CI.

## 2. Contract example: uploading a document with metadata

Suppose the `POST /documents` endpoint accepts a multipart request consisting of:

```text
POST /documents
Content-Type: multipart/form-data

Part "file"
  Content-Type: application/pdf
  Filename: handbook.pdf
  Body: bytes of the PDF file

Part "metadata"
  Content-Type: application/json
  Body: JSON describing the document
```

JSON of the `metadata` part:

```json
{
  "title": "Employee Handbook",
  "description": "Internal onboarding and policy guide",
  "documentType": "HANDBOOK",
  "owner": {
    "team": "People Operations",
    "contactEmail": "people@example.test"
  },
  "tags": [
    "onboarding",
    "policy"
  ]
}
```

There are two structural levels here. The multipart level has two parts: `file` and `metadata`. The JSON level has the fields `title`, `description`, `documentType`, `owner`, and `tags`. The part table helps readers understand which data sections the endpoint expects; the field table explains the schema inside `metadata`.

## 3. Describing part structure with requestParts and partWithName

`requestParts(...)` generates the `request-parts.adoc` snippet. Each `partWithName("...")` describes a part supported by the endpoint:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("file")
        .description("PDF file to upload"),
    partWithName("metadata")
        .description("JSON metadata describing the document")
)
```

A part description should answer what the part is used for. For instance, "JSON metadata describing the document" is more helpful than "Metadata data". This table does not list `title`, `owner`, or `tags`; those fields belong to the JSON part's payload and are documented in a dedicated section.

### 3.1. Required parts and optional parts

By default, documented parts must be present in the test request. If the request sends an undocumented part, strict documentation also causes the test to fail. If a part is genuinely optional per the contract, use `optional()` on the part descriptor:

```java
requestParts(
    partWithName("file")
        .description("PDF file to upload"),
    partWithName("metadata")
        .description("Document description metadata")
        .optional()
)
```

`optional()` here allows the **entire metadata part** to be absent. It differs from `fieldWithPath("description").optional()` in `requestPartFields`, which only allows a single field inside the JSON to be absent.

### 3.2. Intentionally ignoring a part

If the test request includes a known technical part that you do not want to appear in the table:

```java
requestParts(
    partWithName("file").description("Document file"),
    partWithName("metadata").description("JSON metadata"),
    partWithName("internalTrace").ignored()
)
```

`ignored()` records that the part is known and intentionally excluded from the snippet. Only use this when the part does not belong in published documentation; do not use it to hide a new unreviewed part.

### 3.3. Relaxed mode for the part list

If you only want to document a subset of parts in a scenario, you can use `relaxedRequestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedRequestParts;

relaxedRequestParts(
    partWithName("file")
        .description("Document file")
)
```

In relaxed mode, undocumented parts do not fail the test. Declared descriptors are still subject to presence/optional rules. When you need to verify the complete multipart contract, prefer strict `requestParts`.

## 4. Describing fields inside a JSON part

`requestPartFields` belongs to `PayloadDocumentation`. It takes a part name and field descriptors:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields(
    "metadata",
    fieldWithPath("title")
        .description("Document title"),
    fieldWithPath("description")
        .description("Short description"),
    fieldWithPath("documentType")
        .description("Document type"),
    fieldWithPath("owner.team")
        .description("Team owning the document"),
    fieldWithPath("owner.contactEmail")
        .description("Contact email of the owning team"),
    fieldWithPath("tags[]")
        .description("Tags attached to the document")
)
```

The generated snippet is named `request-part-metadata-fields.adoc`. Paths are relative to the **JSON root of the metadata part**, excluding the part name. Therefore, use `owner.team`, not `metadata.owner.team`.

### 4.1. Nested objects and subsections in a JSON part

If `owner` is a large structured object, an overview table can collapse the entire branch:

```java
requestPartFields(
    "metadata",
    fieldWithPath("title")
        .description("Document title"),
    subsectionWithPath("owner")
        .description("Document owner team information"),
    fieldWithPath("tags[]")
        .description("Document tags")
)
```

`subsectionWithPath("owner")` covers descendant fields of `owner` in this snippet. If a separate detailed table for `owner` is needed, you can use the overload accepting a subsection extractor:

```java
requestPartFields(
    "metadata",
    beneathPath("owner").withSubsectionId("owner"),
    fieldWithPath("team")
        .description("Owning team"),
    fieldWithPath("contactEmail")
        .description("Contact email")
)
```

The detailed table uses paths relative to the extracted branch. Since `owner` is already selected, the descriptors are `team` and `contactEmail`, without the `owner.` prefix.

### 4.2. Arrays in a JSON part

For a payload:

```json
{
  "title": "Employee Handbook",
  "tags": ["onboarding", "policy"],
  "attachments": [
    {
      "name": "cover",
      "format": "PDF"
    },
    {
      "name": "appendix",
      "format": "PDF"
    }
  ]
}
```

You can document fields of all elements using paths with `[]`:

```java
requestPartFields(
    "metadata",
    fieldWithPath("title").description("Document title"),
    fieldWithPath("tags[]").description("Tags"),
    fieldWithPath("attachments[].name")
        .description("Attachment name"),
    fieldWithPath("attachments[].format")
        .description("File format")
)
```

Paths are still relative to the JSON root of the part. If the list is empty, there are no elements to match fields inside the array; use a fixture with elements to generate the schema table and test the empty list case separately.

## 5. Generating a body snippet for a part

`requestPartBody("metadata")` creates the `request-part-metadata-body.adoc` snippet containing the part's body. It is useful when documentation needs an intact JSON example:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("metadata")
```

The body snippet shows sample data but does not check field completeness by itself. If the goal is to protect the schema, combine the body snippet with strict `requestPartFields`. If only presenting the data structure is needed, the field table may suffice without necessarily including the body.

## 6. Complete example with MockMvc

The example uses JUnit 5, Java 17+, Spring MVC Test, and Spring REST Docs. The controller accepts a PDF file alongside JSON metadata. File storage handling is simplified to focus on multipart documentation.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
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
class DocumentUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void uploadDocument() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "handbook.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                "fake-pdf-content".getBytes()
        );

        String metadataJson = """
                {
                  "title": "Employee Handbook",
                  "description": "Internal onboarding and policy guide",
                  "documentType": "HANDBOOK",
                  "owner": {
                    "team": "People Operations",
                    "contactEmail": "people@example.test"
                  },
                  "tags": ["onboarding", "policy"]
                }
                """;

        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                metadataJson.getBytes()
        );

        this.mockMvc.perform(multipart("/documents")
                        .file(file)
                        .file(metadata)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andDo(document("documents-upload",
                        requestParts(
                                partWithName("file")
                                        .description("PDF file to upload"),
                                partWithName("metadata")
                                        .description("JSON metadata describing the document")
                        ),
                        requestPartBody("metadata"),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Document title"),
                                fieldWithPath("description")
                                        .description("Short description"),
                                fieldWithPath("documentType")
                                        .description("Document type"),
                                fieldWithPath("owner.team")
                                        .description("Owning team"),
                                fieldWithPath("owner.contactEmail")
                                        .description("Contact email"),
                                fieldWithPath("tags[]")
                                        .description("Document tags")
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
        ResponseEntity<Map<String, String>> upload(
                @RequestPart("file") MultipartFile file,
                @RequestPart("metadata") Map<String, Object> metadata) {

            if (file.isEmpty()) {
                return ResponseEntity.badRequest().build();
            }
            return ResponseEntity.status(201)
                    .body(Map.of("id", "doc-100"));
        }
    }
}
```

### 6.1. Media type of the JSON part

The `metadata` part is created with `MediaType.APPLICATION_JSON_VALUE`. This signals Spring MVC to select a message converter matching the `@RequestPart("metadata")` parameter. If the media type is wrong or the JSON body is invalid, an error may occur during binding before REST Docs runs the field descriptors.

Distinguish HTTP binding/conversion errors from documentation errors. REST Docs can only validate part fields after the request reaches the documentation step.

### 6.2. MockMvc's multipart builder

The example uses the import:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.multipart;
```

This is the multipart request builder provided by Spring REST Docs for MockMvc. Use the corresponding integration builder so the request is processed within REST Docs' documentation context.

## 7. Generated snippets and how to assemble them in Asciidoctor

With the operation identifier `documents-upload`, the relevant snippets are typically located in `build/generated-snippets/documents-upload/`:

| File | Generated by | Role |
| --- | --- | --- |
| `request-parts.adoc` | `requestParts(...)` | Table of part names and descriptions |
| `request-part-metadata-body.adoc` | `requestPartBody("metadata")` | JSON body of metadata |
| `request-part-metadata-fields.adoc` | `requestPartFields("metadata", ...)` | Metadata field table |
| `http-request.adoc` | Default HTTP snippet | Tested multipart request |
| `http-response.adoc` | Default HTTP snippet | HTTP response of the endpoint |

Example `src/docs/asciidoc/documents.adoc`:

```asciidoc
= Document API
:toc: left

== POST /documents

Upload a document file along with descriptive metadata.

=== Request parts

include::{snippets}/documents-upload/request-parts.adoc[]

=== Metadata JSON example

include::{snippets}/documents-upload/request-part-metadata-body.adoc[]

=== Metadata field structure

include::{snippets}/documents-upload/request-part-metadata-fields.adoc[]

=== HTTP response

include::{snippets}/documents-upload/http-response.adoc[]
```

Prose around the snippets explains that the `file` part contains document bytes while the `metadata` part contains JSON. Snippets provide the data and schema; headings/paragraphs clarify their roles.

## 8. Strict, optional, ignored, and relaxed

Distinguish strict validation at the part-list level from strict validation at the field level:

| Scenario | API | Behavior |
| --- | --- | --- |
| Request has an undocumented part | `requestParts(...)` | Strict mode fails the test |
| Descriptor has a required part that request omits | `requestParts(...)` | Test fails |
| JSON part has an undocumented field | `requestPartFields(...)` | Test fails |
| Descriptor has a required field missing from JSON | `requestPartFields(...)` | Test fails |
| Field marked optional is absent | `requestPartFields(...)` | Accepted |
| Part marked optional is absent | `requestParts(...)` | Accepted |
| Undocumented part in relaxed mode | `relaxedRequestParts(...)` | Ignored |
| Undocumented field in relaxed mode | `relaxedRequestPartFields(...)` | Ignored |

`ignored()` differs from `optional()`: `ignored` excludes a known item from the snippet; `optional` allows that item to be absent. Relaxed mode allows undocumented items to appear. Choose the mechanism based on the contract rather than using them merely to make tests pass.

### 8.1. New field in the JSON part

If `classification` is added to `metadata` while the strict table has not declared it, the test may fail. If the field belongs to the public contract, add a descriptor and description. If the JSON is an open schema and a scenario only needs to focus on a few fields, relaxed mode may be suitable, but the documentation should explicitly state that the table does not cover every field.

### 8.2. Optional part and optional field are two different levels

If the entire `metadata` part can be absent, mark the `metadata` part optional in `requestParts`. If the part itself is required yet a field such as `description` can be omitted, mark that field optional in `requestPartFields`. If the part is absent, there is no payload from which to generate a field table for that part; write a separate test for the variant without metadata.

## 9. Part names and paths must match the actual request

The part name is the key REST Docs uses to locate the payload. The following places must align:

- `MockMultipartFile("metadata", ...)`;
- `@RequestPart("metadata")`;
- `requestParts(partWithName("metadata"))`;
- `requestPartBody("metadata")`;
- `requestPartFields("metadata", ...)`.

If the client sends `details` while the test documents `metadata`, REST Docs will not automatically map the two names.

Field paths start from the JSON part root:

```java
// Incorrect: repeating the part name in the field path.
requestPartFields("metadata",
    fieldWithPath("metadata.title").description("Title")
);

// Correct: metadata is already selected in the first argument.
requestPartFields("metadata",
    fieldWithPath("title").description("Title")
);
```

An incorrect path can cause missing documented field or undocumented field errors. Compare against the actual JSON of the part before modifying descriptors.

## 10. Using with WebTestClient and REST Assured

### 10.1. WebTestClient

Build a multipart body with `BodyInserters.fromMultipartData`. When sending a file resource, you can use `ByteArrayResource` and override `getFilename()` to supply the filename.

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
Resource fileResource = new ByteArrayResource("fake-pdf".getBytes()) {
    @Override
    public String getFilename() {
        return "handbook.pdf";
    }
};
parts.add("file", fileResource);
parts.add("metadata", metadataMap);

webTestClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("documents-upload",
        requestParts(
            partWithName("file").description("PDF file"),
            partWithName("metadata").description("JSON metadata")
        ),
        requestPartFields("metadata",
            fieldWithPath("title").description("Title"),
            fieldWithPath("documentType").description("Document type")
        )
    ));
```

WebTestClient must be configured with the Spring REST Docs documentation filter before the exchange. The example focuses on sending multipart requests and placing the handlers; `parts`, `metadataMap`, and the client are prepared in the test.

### 10.2. REST Assured

With REST Assured, use `multiPart` to send each part and attach handlers in the filter:

```java
RestAssured.given(this.spec)
    .accept("application/json")
    .filter(document("documents-upload",
        requestParts(
            partWithName("file").description("PDF file"),
            partWithName("metadata").description("JSON metadata")
        ),
        requestPartFields("metadata",
            fieldWithPath("title").description("Title"),
            fieldWithPath("documentType").description("Document type")
        )
    ))
    .multiPart("file", new File("handbook.pdf"), "application/pdf")
    .multiPart("metadata", metadataMap)
    .when()
    .post("/documents")
    .then()
    .statusCode(201);
```

The examples assume the client/filter, server, and REST Docs dependencies are already configured. The metadata part must be serialized with the exact media type required by the endpoint.

## 11. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Part not found | Part name between client and descriptor does not match | Align names across client, controller, and document handlers |
| Part table missing a part | `partWithName` not declared or relaxed mode is active | Add descriptor and use strict mode if full control is needed |
| Part table exists without JSON fields | Only `requestParts` was called | Add `requestPartFields` |
| JSON body exists without field table | Only `requestPartBody` was called | Add `requestPartFields` |
| Field path not found | Path repeats part name or does not match JSON | Use path relative to JSON part root |
| JSON fails to convert | Wrong media type or part body | Use `application/json` and verify JSON |
| File part treated as JSON | Wrong media type/binding | Use appropriate file media type; do not document file bytes as JSON fields |
| New field not detected | Using relaxed mode or subsection covering the branch | Use strict mode and detailed descriptors when needed |
| Asciidoctor missing snippet | Wrong operation ID, part name, or output directory | Inspect generated filenames and include paths |

## 12. Build and CI integration

With Gradle Groovy DSL, assuming the project has configured Spring REST Docs, tests, and the Asciidoctor plugin:

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

In CI, verify:

1. Multipart tests execute and reach the `document(...)` handler.
2. Part names in the request match the arguments to `requestParts`, `requestPartBody`, and `requestPartFields`.
3. JSON parts have the right media type and a valid payload.
4. Strict tables detect new parts/fields or missing required items.
5. Asciidoctor reads the exact snippet directory just generated.
6. Snippets are included with the exact operation identifier and part name.

With Maven, the snippet directory is typically `target/generated-snippets`; the documentation build step must run after the tests generating snippets.

## 13. Hands-on exercise

Create `DocumentUploadDocumentationTest` and perform the following:

1. Send a multipart request with `file` and `metadata` parts, setting appropriate filenames and media types.
2. Use `requestParts` to describe the purpose and requirement status of each part.
3. Use `requestPartBody("metadata")` to generate a JSON snippet.
4. Use `requestPartFields("metadata", ...)` to document `title`, `description`, `owner`, and `tags`.
5. Add a `metadata.classification` field without declaring a descriptor; observe the strict test fail.
6. Mark the `description` field optional if the contract allows it, then test the case where the field is absent.
7. Mark the `metadata` part optional if the endpoint allows omitting the entire part; write a separate test for the variant without the part.
8. Switch `requestParts` to `relaxedRequestParts` and add an undocumented part; compare strict vs. relaxed.
9. Include `request-parts.adoc`, `request-part-metadata-body.adoc`, and `request-part-metadata-fields.adoc` in Asciidoctor.
10. Run `./gradlew clean test asciidoctor` in the configured project.

**Completion criteria:** distinguish part-level multipart structure from the JSON schema inside a part, use `requestParts`/`requestPartFields`/`requestPartBody` properly, specify names/paths accurately, and explain strict, optional, ignored, and relaxed modes according to the contract.

## 14. Self-check questions

**1. Which API describes the list of parts in a multipart request?**

`requestParts(partWithName(...), ...)`. It generates a table of part names and descriptions.

**2. Which API documents fields inside a JSON part?**

`requestPartFields("metadata", ...)`. Field paths are relative to the JSON root of the part.

**3. Is `partFields(...)` a Spring REST Docs method?**

It is not a generic method name in the API. Use `requestParts` for the part list and `requestPartFields` for fields inside a part.

**4. What are the snippet names for the part table and the metadata field table?**

The part table is `request-parts.adoc`; the metadata field table is `request-part-metadata-fields.adoc`.

**5. When should relaxedRequestParts and relaxedRequestPartFields be used?**

When documentation focuses on a subset of parts or fields and allows other items to appear undocumented. For contracts requiring full control, prefer strict mode.

**6. Should requestPartFields be used to document the bytes of a file?**

No. `requestPartFields` describes fields of a structured payload, usually JSON. File parts are documented at the part level; do not turn binary content into a JSON field table.

## References

- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): request parts, part body, part fields, strict/relaxed, and snippet names.
- [RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html): `requestParts`, `partWithName`, and part descriptors.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `requestPartFields`, `requestPartBody`, and subsection extractors.
