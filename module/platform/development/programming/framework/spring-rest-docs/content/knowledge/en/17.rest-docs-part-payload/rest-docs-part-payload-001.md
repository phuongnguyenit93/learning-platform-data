# Documenting the Body of a Request Part in Spring REST Docs

## 1. Multipart requests with multiple content parts

A document upload API may accept both a binary file and a metadata part describing that file at the same time. Clients typically send the request in `multipart/form-data` format:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary123

------Boundary123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Spring Guide",
  "category": "TECHNICAL",
  "visibility": "TEAM"
}
------Boundary123
Content-Disposition: form-data; name="file"; filename="spring-guide.pdf"
Content-Type: application/pdf

...binary PDF content...
------Boundary123--
```

The request has two parts:

- metadata: a JSON payload containing title, category, and visibility.
- file: binary PDF content, with its own filename and media type.

If the documentation only lists the `POST /api/documents` endpoint and a generic multipart example, the client still does not know the name of each part, which part is required, which fields the metadata contains, which fields may be omitted, or which values are accepted.

**Spring REST Docs** supports documenting multipart requests at multiple levels. `requestParts(...)` describes the parts present in the request. `requestPartFields(...)` describes the payload structure inside a part whose content is an object, typically JSON. Combining these two APIs ensures the documentation specifies both which parts make up the request and the body of the metadata part specifically.

The **SPRING_REST_DOCS** module generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. This lesson belongs to the **Part payload** chapter, focusing on documenting the body of a request part and integrating the generated snippets into Asciidoctor/Markdown, the build, and CI.

After this lesson, you will be able to:

1. Distinguish between describing multipart parts and describing the payload inside a part.
2. Use `requestParts(...)` to document the name, purpose, and requirement status of each part.
3. Use `requestPartFields(...)` to document the fields in the body of a part.
4. Write MockMvc tests for multipart requests containing JSON metadata and file uploads.
5. Generate snippets and include them in your API documentation.

## 2. Two layers of documentation: part and part payload

### 2.1. Describing parts with requestParts(...)

A part is an independent section within a multipart request. Each part has its own name, headers, and body. For example:

| Part name | Content-Type | Body |
| --- | --- | --- |
| metadata | application/json | JSON object describing the document |
| file | application/pdf | Bytes of the PDF file |

We document them using `requestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("metadata")
        .description("Document metadata, sent as JSON"),
    partWithName("file")
        .description("Document file to upload")
)
```

This group of descriptors lets the documentation list the parts, explain their purpose, and verify the parts sent in the request. It does not describe the fields inside the JSON metadata.

### 2.2. Describing a part's body with requestPartFields(...)

When a part has a structured JSON payload, you can document each field:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields("metadata",
    fieldWithPath("title").description("Document title"),
    fieldWithPath("category").description("Document category"),
    fieldWithPath("visibility").description("Visibility scope")
)
```

The first argument `"metadata"` identifies the name of the part containing the payload to describe. The subsequent `FieldDescriptor` arguments describe the body structure of this specific part. Do not confuse it with `requestFields(...)`, which describes the payload of the main request body.

### 2.3. When to use which API?

| API | Scope | Example |
| --- | --- | --- |
| requestParts(...) | Name and description of each part in a multipart request | metadata, file |
| requestPartFields("metadata", ...) | Fields inside the payload of the metadata part | title, category, visibility |
| requestFields(...) | Fields in a regular main request body | JSON body of the request |
| requestHeaders(...) | HTTP request headers | Authorization, Accept |
| responseFields(...) | Fields in the response payload | documentId, status |

For binary parts like a PDF file, you typically describe the part using `requestParts(...)` and state the file rules (format, size limit, filename) in the description. `requestPartFields(...)` is intended for payloads with field structures; do not use it to list bytes inside a binary file.

## 3. Structure of requestPartFields(...)

The `requestPartFields(...)` API takes a part name and a list of descriptors. These descriptors use the same `FieldDescriptor` model as other payload snippets in Spring REST Docs:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("Display name of the document"),
    fieldWithPath("category")
        .description("Category: TECHNICAL, BUSINESS, or OTHER"),
    fieldWithPath("visibility")
        .description("Scope: PRIVATE or TEAM")
)
```

Some commonly used descriptors:

| Descriptor | Meaning |
| --- | --- |
| fieldWithPath("title") | Describes the field with path `title` |
| description("...") | Explains the meaning of the field |
| optional() | The field may be absent from the payload being documented |
| type(JsonFieldType.STRING) | Declares the data type to display in the snippet |
| attributes(...) | Adds metadata for custom templates |
| subsectionWithPath("properties") | Describes an object/subsection as a single unit without listing each child field |

Example with an optional field:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Document title"),
    fieldWithPath("description")
        .description("Additional description")
        .optional()
)
```

If the request part in the test omits `description`, the descriptor remains valid because it is marked optional. This does not automatically alter application validation or make arbitrary field values valid.

### 3.1. Nested fields

The metadata payload might look like this:

```json
{
  "title": "Spring Guide",
  "owner": {
    "id": 42,
    "displayName": "Engineering"
  },
  "tags": ["java", "spring"]
}
```

You can describe each nested field:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Title"),
    fieldWithPath("owner.id").description("Owner ID"),
    fieldWithPath("owner.displayName").description("Owner display name"),
    fieldWithPath("tags").description("List of tags")
)
```

Field paths use dot notation to traverse into nested objects. If you want to describe the entire `owner` object as a group without listing its child fields in detail, you can use `subsectionWithPath("owner")` and explain the structure in the description.

### 3.2. Arrays and repeated elements

For a payload:

```json
{
  "attachments": [
    {"name": "diagram.png", "mediaType": "image/png"},
    {"name": "notes.txt", "mediaType": "text/plain"}
  ]
}
```

Describe the array element structure with:

```java
requestPartFields("metadata",
    fieldWithPath("attachments").description("List of attached files"),
    fieldWithPath("attachments[].name").description("File name"),
    fieldWithPath("attachments[].mediaType").description("File media type")
)
```

The `[]` notation represents array elements. For complex structures, verify the exact JSON path provided by the actual payload.

## 4. Example endpoint receiving a JSON part and a file

Suppose the `POST /api/documents` API receives JSON metadata along with a file. Illustrative DTO:

```java
public record DocumentMetadata(
        String title,
        String category,
        String visibility) {
}
```

Controller:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
class DocumentController {

    @PostMapping(
            path = "/api/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public DocumentReceipt upload(
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("file") MultipartFile file) {

        return new DocumentReceipt(
                "DOC-1001",
                metadata.title(),
                file.getOriginalFilename(),
                file.getSize());
    }
}

record DocumentReceipt(
        String documentId,
        String title,
        String filename,
        long size) {
}
```

`@RequestPart("metadata")` instructs Spring to read the `metadata` part using an appropriate message converter. Because this part has `Content-Type` `application/json`, the JSON can be deserialized into `DocumentMetadata`. `@RequestPart("file")` receives the file content via `MultipartFile`.

## 5. MockMvc test documenting the body of a request part

### 5.1. Preparing the multipart request

With MockMvc, use `MockMultipartFile` to create each part. Set separate `Content-Type` values for `metadata` and `file`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

MockMultipartFile metadataPart = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "title": "Spring Guide",
          "category": "TECHNICAL",
          "visibility": "TEAM"
        }
        """.getBytes(StandardCharsets.UTF_8));

MockMultipartFile filePart = new MockMultipartFile(
        "file",
        "spring-guide.pdf",
        MediaType.APPLICATION_PDF_VALUE,
        "%PDF-demo".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/documents")
        .file(metadataPart)
        .file(filePart));
```

In this sample test, the file part uses illustrative bytes to focus on multipart binding; a real system needs a valid sample file if there is a PDF content inspection step.

### 5.2. Complete documentation test

```java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

@ExtendWith(RestDocumentationExtension.class)
class DocumentUploadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsMetadataPartPayload() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {
                  "title": "Spring Guide",
                  "category": "TECHNICAL",
                  "visibility": "TEAM"
                }
                """.getBytes(StandardCharsets.UTF_8));

        MockMultipartFile file = new MockMultipartFile(
                "file",
                "spring-guide.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                "%PDF-demo".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/documents")
                        .file(metadata)
                        .file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.documentId").value("DOC-1001"))
                .andExpect(jsonPath("$.title").value("Spring Guide"))
                .andExpect(jsonPath("$.filename").value("spring-guide.pdf"))
                .andDo(document("document-upload",
                        requestParts(
                                partWithName("metadata")
                                        .description("Document metadata as JSON"),
                                partWithName("file")
                                        .description("PDF file to upload")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("title")
                                        .description("Document title"),
                                fieldWithPath("category")
                                        .description("Category: TECHNICAL, BUSINESS, or OTHER"),
                                fieldWithPath("visibility")
                                        .description("Visibility scope: PRIVATE or TEAM")
                        )));
    }
}
```

The key elements inside `document(...)` are:

1. `requestParts(...)` documents the two parts `metadata` and `file`.
2. `requestPartFields("metadata", ...)` documents the three fields in the body of the `metadata` part.
3. The `jsonPath(...)` assertions verify that the controller bound the metadata and filename properly. Generating snippets alone does not prove business rules or successful file storage.

The first parameter of `MockMultipartFile` is the part name. This name must match `@RequestPart("metadata")`, `@RequestPart("file")`, and the names in the descriptors. The `metadata` part must have `application/json` so Spring selects the converter to read JSON; the file has the appropriate media type according to the upload contract.

## 6. Generated snippets and how to include them in Asciidoctor

With the identifier `document-upload`, Spring REST Docs generates snippets for the documented sections. Relevant files typically include:

```text
build/generated-snippets/
  document-upload/
    request-parts.adoc
    request-part-metadata-fields.adoc
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    ...
```

Exact snippet filenames depend on the snippet/template format and Spring REST Docs version. `request-parts.adoc` contains the table of parts; the field snippet for the `metadata` part contains the table of fields declared in `requestPartFields(...)`.

An Asciidoctor documentation page can include them as follows:

```asciidoc
= Document API

== Upload document

POST /api/documents

=== Request parts

include::{snippets}/document-upload/request-parts.adoc[]

=== Metadata part payload

include::{snippets}/document-upload/request-part-metadata-fields.adoc[]

=== HTTP request

include::{snippets}/document-upload/http-request.adoc[]
```

The `{snippets}` variable must point to the snippet output directory. If the project uses Markdown, you can select `TemplateFormats.markdown()` for snippets and use an appropriate Markdown assembly step; standard Markdown does not have a built-in include mechanism like Asciidoctor.

## 7. Nested payloads, optional fields, and ignored fields

`requestPartFields(...)` shares the same descriptor mechanism as other request/response field snippets.

### 7.1. Optional fields

Payload:

```json
{
  "title": "Spring Guide",
  "category": "TECHNICAL"
}
```

If `visibility` can be absent in a documentable request payload:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Title"),
    fieldWithPath("category").description("Category"),
    fieldWithPath("visibility")
        .description("Visibility scope; defaults to TEAM")
        .optional()
)
```

The `optional` descriptor allows the field to be absent in the test payload while keeping its description in the table. The default value `TEAM` must be enforced and tested separately by the application.

### 7.2. Ignored fields

When a payload contains a known technical field that you do not want to appear in the documentation table:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Title"),
    fieldWithPath("internalChecksum").ignored()
)
```

An `ignored` field is recognized without being documented as a public field. It should not be used to hide fields that clients need to know about.

### 7.3. Describing only a subsection

For objects with multiple child fields:

```json
{
  "title": "Spring Guide",
  "owner": {
    "id": 42,
    "team": "Engineering"
  },
  "audit": {
    "createdBy": "user-7",
    "createdAt": "2026-11-01T09:00:00Z"
  }
}
```

You can document each field using its full path or describe a child object with `subsectionWithPath("owner")`. If the API intends to publish the full `owner` structure, listing `owner.id` and `owner.team` gives consumers a clearer understanding of the schema.

## 8. Distinguishing part descriptor errors from payload descriptor errors

| Symptom | Error scope | How to handle |
| --- | --- | --- |
| Request sends part `thumbnail` but `requestParts(...)` descriptors do not include this name | Undocumented part | Add `partWithName("thumbnail")` or handle per contract |
| Request is missing part `metadata` while descriptor requires it | Missing required part | Send the part or mark optional if the API allows it |
| Metadata payload has field `author` not present in descriptors | Undocumented field inside part | Add `fieldWithPath("author")` |
| Descriptor expects `visibility` but JSON lacks that field | Documented field missing from test payload | Add the field to the fixture or use `optional()` if accurate to contract |
| Metadata part sent as `text/plain` when controller expects JSON | Message converter fails to read in expected format | Assign `Content-Type` `application/json` to the part |
| File part passed to `requestPartFields(...)` | Confusing binary payload with object payload | Document file with `requestParts(...)`, explaining media type, filename, and size |
| Part snippet generated without metadata table | Only called `requestParts(...)`, omitted `requestPartFields(...)` | Add snippet describing the part's body |

## 9. Notes on multipart testing

**Part names must be consistent.** The name in the multipart request, `@RequestPart`, `requestParts(...)`, and the first argument of `requestPartFields(...)` must refer to the exact same part.

**Per-part Content-Type matters.** JSON metadata should have `application/json`; files can use specific media types like `application/pdf` or `image/png`. Do not rely solely on the overall request `Content-Type` being `multipart/form-data`.

**JSON parts and file parts serve different roles.** One part can be parsed into a DTO and have its fields documented; a file part is typically a byte stream or `MultipartFile`. If the API accepts an additional text part, specify its charset/format in the description.

**Do not depend on a specific boundary.** The boundary is generated by the HTTP client; tests and documentation should focus on part names, payloads, and media types rather than hardcoding the boundary into the contract.

**Upload validation requires separate tests.** File type, maximum size, filename, file content, virus scanning, and upload permissions are application rules. Descriptors only describe payloads and do not replace tests for security/validation conditions.

## 10. WebTestClient and REST Assured

`requestParts(...)` and `requestPartFields(...)` describe the same multipart request concept, even though request construction differs across test clients.

### 10.1. WebTestClient

With WebTestClient configured for Spring REST Docs, use a multipart inserter to send parts. General example:

```java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
bodyBuilder.part("metadata", """
        {"title":"Spring Guide","category":"TECHNICAL","visibility":"TEAM"}
        """)
        .contentType(MediaType.APPLICATION_JSON);
bodyBuilder.part("file", new ByteArrayResource("%PDF-demo".getBytes()) {
    @Override
    public String getFilename() {
        return "spring-guide.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(bodyBuilder.build()))
        .exchange()
        .expectStatus().isOk();
```

When documenting, attach the `requestParts(...)` and `requestPartFields("metadata", ...)` snippets to the `document(...)` mechanism of the WebTestClient integration. WebTestClient must be configured with REST Docs beforehand; the snippet above illustrates creating the multipart request.

### 10.2. REST Assured

REST Assured supports sending multipart parts via `multiPart(...)` overloads. Illustrative example:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"title\":\"Spring Guide\",\"category\":\"TECHNICAL\","
                        + "\"visibility\":\"TEAM\"}",
                "application/json")
        .multiPart("file", new File("spring-guide.pdf"))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(200);
```

The `documentationFilter` filter must be configured with the Spring REST Docs integration and a snippet list containing `requestParts(...)` and `requestPartFields(...)`. Exact syntax of the multipart overload depends on the REST Assured version; verify the actual `Content-Type` of the part in the sent request.

## 11. Build, Asciidoctor, and CI

Implementation workflow:

1. Choose the Spring REST Docs integration matching your test client (`spring-restdocs-mockmvc`, `spring-restdocs-webtestclient`, or `spring-restdocs-restassured`).
2. Write multipart tests sending both the JSON part and the file part, verifying the response and documenting the parts.
3. Configure a snippet directory such as `build/generated-snippets` as the output of the test task.
4. Make the Asciidoctor task depend on the test task and include `request-parts.adoc`, the metadata field snippet, and the necessary HTTP snippets.
5. Run tests alongside the documentation rendering step in CI to catch undocumented changes to part names or the metadata schema.

Example Gradle command when tasks are configured:

```bash
./gradlew test asciidoctor
```

When the metadata payload changes, a test with strict `requestPartFields(...)` will require updating descriptors if a new field appears or a documented field is missing. This is a useful mechanism to keep the part payload schema synchronized with test requests.

## 12. Hands-on exercise

Design the endpoint:

```http
POST /api/media
Content-Type: multipart/form-data

Part "metadata" (application/json):
{
  "name": "Team photo",
  "description": "Group photo",
  "labels": ["team", "2026"]
}

Part "image" (image/png):
...binary image...
```

Contract:

- `metadata` is required and is a JSON object.
- `name` is required; `description` is optional; `labels` is an optional array of strings.
- `image` is required and accepts PNG only; size limit is defined by the application.

Steps:

1. Create a metadata DTO and a controller accepting `@RequestPart("metadata")` along with `@RequestPart("image")`.
2. Write a MockMvc test creating `MockMultipartFile` instances for the JSON metadata and PNG file.
3. Use `requestParts(...)` to describe both parts; use `requestPartFields("metadata", ...)` to describe `name`, `description`, and `labels`.
4. Try omitting `description` from the JSON and marking its descriptor optional; try omitting `name` and verify the application rejects it.
5. Add tests for invalid media types or file sizes; assert that server validation returns an appropriate error.
6. Generate snippets and include them in an Asciidoctor page; run tests together with documentation rendering in CI.

**Completion criteria:** The documentation clearly distinguishes the two parts, describes the metadata schema, reflects required/optional fields, and tests verify actual binding/validation.

## 13. Key takeaways

A multipart request contains multiple parts; `requestParts(...)` describes each part, while `requestPartFields("partName", ...)` describes the structured payload inside the selected part. Use `requestFields(...)` for a standard main request body, not as a substitute for documenting a multipart part's body. Combine MockMvc/WebTestClient/REST Assured, application assertions, and Asciidoctor/Markdown snippets so upload documentation stays verifiable in the build/CI.

### References

- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring Framework — Multipart Resolver and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
