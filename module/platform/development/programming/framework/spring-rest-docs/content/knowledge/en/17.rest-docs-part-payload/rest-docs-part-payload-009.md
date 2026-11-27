# Verifying Operation-Specific Part Payloads with Spring REST Docs

## 1. Same part name does not mean the same schema

A multipart API may reuse the same part name **metadata** across multiple operations, while the JSON inside that part varies depending on the operation's purpose.

**Creating a new document**

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----CreateBoundary

------CreateBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Spring REST Docs",
  "category": "TECHNICAL",
  "visibility": "TEAM"
}
------CreateBoundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...PDF bytes...
------CreateBoundary--
```

**Updating document information**

```http
PATCH /api/documents/DOC-42 HTTP/1.1
Content-Type: multipart/form-data; boundary=----UpdateBoundary

------UpdateBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "title": "Spring REST Docs - updated edition",
  "visibility": "PRIVATE"
}
------UpdateBoundary--
```

Both requests have a part named metadata, yet their contracts differ:

| Item | Create document | Update information |
| --- | --- | --- |
| HTTP operation | POST /api/documents | PATCH /api/documents/{documentId} |
| title | Required | May be omitted if unchanged |
| category | Required | Not accepted in this operation |
| visibility | Required | May be omitted if unchanged |
| Part file | Required | Not sent |

If a single field table is shared without distinguishing operations, integrators might think category is always allowed during updates or that file is required in both requests. Documentation must accurately reflect the contract of each operation.

Spring REST Docs generates snippets from HTTP tests using MockMvc, WebTestClient, or REST Assured. The **SPRING_REST_DOCS** module creates verifiable REST API documentation, compiles snippets into Asciidoctor/Markdown, and integrates them into build/CI. This lesson belongs to the **Part payload** chapter, focusing on verifying part payloads that vary by operation, assigning distinct snippet identifiers, and selecting appropriate descriptors.

After this lesson, you will be able to:

1. Recognize when the same part name has different schemas across operations.
2. Create separate **requestPartFields(...)** descriptors for each operation.
3. Use **optional()** and **ignored()** accurately according to each request's contract.
4. Choose **relaxedRequestPartFields(...)** when intentionally documenting only part of a payload.
5. Use distinct document identifiers and organize snippets so readers do not get confused.

## 2. Defining the contract per operation

An operation is a specific API usage, typically identified by HTTP method, URI, and intent. Two operations sharing a part name do not necessarily share a schema.

Before writing tests, build a contract table:

| Attribute | createDocument | updateDocumentDetails |
| --- | --- | --- |
| Method/path | POST /api/documents | PATCH /api/documents/{documentId} |
| Part metadata | Required | Required |
| title | Required | Optional |
| category | Required | Not accepted in this request |
| visibility | Required | Optional |
| Part file | Required | Not accepted |
| Goal | Initialize document | Modify attributes |

This table serves as the basis for choosing descriptors and assertions. It also helps decide whether the two operations should share a DTO or require separate request models.

### 2.1. Distinguishing optional from unsupported

- **Optional:** clients are allowed to send or omit the field per contract. If sent, the server processes that field.
- **Unsupported in this operation:** the field does not belong to the operation's request contract, even if another operation uses the same field name.

For example, category is required when creating a document but cannot be changed in the update operation. Do not mark category optional in the update descriptor just because it is absent in the example. If a client sends category, the server must clearly define whether it rejects or ignores it. That behavior must be tested and documented.

### 2.2. Same part name, potentially different schemas

An API might use the metadata part with different schemas:

- Create document: title, category, visibility.
- Update metadata: title, visibility.
- Import inventory: source, version, items.

Do not merge these fields into one large schema if clients cannot send all of them in a single operation. A consolidated doc can serve as reference material, but each operation still needs to describe its specific request.

## 3. Separate descriptors for each operation

Spring REST Docs allows calling requestPartFields(partName, ...) inside each document(...) call. Create a document identifier for each operation:

```java
document("document-create",
    requestPartFields("metadata",
        fieldWithPath("title").description("Document title"),
        fieldWithPath("category").description("Document category"),
        fieldWithPath("visibility").description("Visibility scope")
    )
)
```

For the update operation:

```java
document("document-update-details",
    requestPartFields("metadata",
        fieldWithPath("title").description("New title").optional(),
        fieldWithPath("visibility").description("New visibility scope").optional()
    )
)
```

Each snippet is generated from its corresponding request. The descriptors of the create operation do not affect those of the update operation, even though both use the part name metadata.

### 3.1. Why must document identifiers be separate?

The identifier determines the directory containing the snippets. If two tests write to the same identifier and produce the same snippet filenames, they can cause confusion or overwrite output. Choose names that describe the method/path or intent:

| Operation | Suggested document identifier |
| --- | --- |
| Create document | document-create |
| Update metadata | document-update-details |
| Replace document file | document-replace-file |
| Import data batch | document-import-batch |

Identifier names should remain stable so Asciidoctor includes stay easy to follow.

### 3.2. Documenting both parts and payload fields

If the create request has multiple parts, describe the parts and the metadata schema:

```java
document("document-create",
    requestParts(
        partWithName("metadata").description("Document metadata as JSON"),
        partWithName("file").description("PDF file to upload")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("Document title"),
        fieldWithPath("category").description("Document category"),
        fieldWithPath("visibility").description("Visibility scope")
    )
)
```

The update operation accepts only metadata:

```java
document("document-update-details",
    requestParts(
        partWithName("metadata").description("Attributes to update")
    ),
    requestPartFields("metadata",
        fieldWithPath("title").description("New title; omit if unchanged").optional(),
        fieldWithPath("visibility").description("New visibility scope; omit if unchanged").optional()
    )
)
```

The part list and payload schema must reflect the exact actual request of that operation.

## 4. Using optional() with the right semantics

The optional() descriptor indicates that a field may be absent from the payload being documented. It does not turn a field into an unsupported one, nor does it decide default values or business validation on its own.

Metadata update example:

```json
{
  "visibility": "PRIVATE"
}
```

Descriptors:

```java
requestPartFields("metadata",
    fieldWithPath("title")
        .description("New title; omit if unchanged")
        .optional(),
    fieldWithPath("visibility")
        .description("New visibility scope; omit if unchanged")
        .optional()
)
```

In a partial update operation, both fields can be omitted. Define separately:

- Absent field: retain the existing value.
- Present value: update to the new value.
- Null value: depending on the contract, may clear the value, be rejected, or be treated as unchanged.
- Empty payload with no fields: may be rejected as a no-op.

optional() only describes the possibility of a field being absent in the snippet. Write assertions and validation to prove the rules above.

## 5. Using ignored() when a field is present but unpublished

ignored() is appropriate when a test request contains a known field that public documentation does not need to list. For instance, the system accepts internalTrace for internal integration:

```java
requestPartFields("metadata",
    fieldWithPath("title").description("Document title"),
    fieldWithPath("visibility").description("Visibility scope"),
    fieldWithPath("internalTrace").ignored()
)
```

Do not use ignored() merely to avoid updating a schema. If category is disallowed in the update operation, test what happens when a client sends category and decide the contract: reject with an appropriate error or accept as an internal field. Never silently hide an attribute clients need to know about.

ignored() also does not replace authorization or data protection. It only controls whether the field is included in the snippet.

## 6. When to use relaxedRequestPartFields()?

Strict mode in requestPartFields(...) checks that all fields in the payload are documented and required descriptors are present. In some tests, you only want to document part of the payload while other fields fall outside the scope of that documentation page.

In that case, you can use relaxedRequestPartFields(...):

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestPartFields;

document("document-update-summary",
    relaxedRequestPartFields("metadata",
        fieldWithPath("title").description("New title")
    )
)
```

The request may contain fields other than title; relaxed mode does not require every field present in the payload to have a descriptor. Declared descriptors must still match the content per descriptor rules unless marked optional.

### 6.1. Strict vs. relaxed

| Criterion | requestPartFields(...) | relaxedRequestPartFields(...) |
| --- | --- | --- |
| Field in payload without descriptor | Fails with error | Allowed |
| Required descriptor missing from payload | Fails with error | Still fails unless optional |
| Purpose | Verify complete schema | Document only part of the payload |
| Best suited for | Official operation contract | Overview docs or abbreviated examples |

Do not use relaxed mode for every operation just to make tests pass easily. For public API documentation, strict mode helps detect newly added fields that have not been reviewed.

### 6.2. Relaxed does not model dynamic schemas

If the payload varies by a discriminator, such as kind=PERSON or kind=COMPANY, the two payloads may have different schemas. Document each variant or corresponding operation explicitly. relaxedRequestPartFields(...) only relaxes checks on undocumented fields; it does not model variants, conditional dependencies, or validation.

## 7. Complete example: creating and updating a document

### 7.1. Illustrative controller

Two operations use the same metadata part but distinct request models:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

record CreateDocumentMetadata(String title, String category, String visibility) {}
record UpdateDocumentMetadata(String title, String visibility) {}
record DocumentReceipt(String id, String title, String visibility) {}

@RestController
class DocumentController {

    @PostMapping(path = "/api/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentReceipt create(
            @RequestPart("metadata") CreateDocumentMetadata metadata,
            @RequestPart("file") MultipartFile file) {
        return new DocumentReceipt("DOC-42", metadata.title(), metadata.visibility());
    }

    @PatchMapping(path = "/api/documents/{documentId}", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentReceipt update(
            @PathVariable String documentId,
            @RequestPart("metadata") UpdateDocumentMetadata metadata) {
        return new DocumentReceipt(documentId, metadata.title(), metadata.visibility());
    }
}
```

This is an example of two distinct request models despite sharing the same part name. Real systems must handle optional fields according to update rules and validate empty/null payloads.

### 7.2. Test documenting the create operation

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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentOperationsDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsCreateOperationPayload() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"Spring REST Docs","category":"TECHNICAL","visibility":"TEAM"}
                """.getBytes(StandardCharsets.UTF_8));
        MockMultipartFile file = new MockMultipartFile(
                "file", "guide.pdf", MediaType.APPLICATION_PDF_VALUE,
                "%PDF-demo".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/documents").file(metadata).file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("DOC-42"))
                .andDo(document("document-create",
                        requestParts(
                                partWithName("metadata").description("Document creation metadata"),
                                partWithName("file").description("PDF file of the document")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("title").description("New title"),
                                fieldWithPath("category").description("Document category"),
                                fieldWithPath("visibility").description("Visibility scope")
                        )));
    }
}
```

### 7.3. Test documenting the update operation

```java
@Test
void documentsUpdateOperationPayload() throws Exception {
    MockMultipartFile metadata = new MockMultipartFile(
            "metadata", "", MediaType.APPLICATION_JSON_VALUE,
            """
            {"visibility":"PRIVATE"}
            """.getBytes(StandardCharsets.UTF_8));

    mockMvc.perform(multipart("/api/documents/{documentId}", "DOC-42")
                    .file(metadata)
                    .with(request -> {
                        request.setMethod("PATCH");
                        return request;
                    }))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("DOC-42"))
            .andExpect(jsonPath("$.visibility").value("PRIVATE"))
            .andDo(document("document-update-details",
                    requestParts(
                            partWithName("metadata")
                                    .description("Attributes to update")
                    ),
                    requestPartFields("metadata",
                            fieldWithPath("title")
                                    .description("New title; omit if unchanged")
                                    .optional(),
                            fieldWithPath("visibility")
                                    .description("New visibility scope; omit if unchanged")
                                    .optional()
                    )));
}
```

Both tests use the same part name yet have different document identifiers and descriptors. The create test requires title, category, and visibility; the update test documents only title and visibility, both optional in the example. In a real project, add business assertions confirming that absent fields preserve existing values.

MockMvc multipart(...) creates a POST request by default; when testing a PATCH endpoint, the example uses a request post-processor to switch the HTTP method. If your project uses custom multipart configuration or resolvers, ensure tests run through the actual application configuration.

## 8. Payloads varying by discriminator

Some APIs use the same operation while the payload has variants based on a kind field. For example, the metadata part could be:

```json
{
  "kind": "PERSON",
  "person": {
    "fullName": "Nguyen An",
    "dateOfBirth": "1990-01-10"
  }
}
```

Or:

```json
{
  "kind": "COMPANY",
  "company": {
    "legalName": "Example Company",
    "taxCode": "TAX-100"
  }
}
```

Do not simply declare all person and company fields optional and leave readers to infer the relationship between them. Document variants separately:

| Variant | Required fields | Disallowed fields |
| --- | --- | --- |
| kind=PERSON | person.fullName, person.dateOfBirth | company.* |
| kind=COMPANY | company.legalName, company.taxCode | person.* |

You can create two tests and two document identifiers, such as customer-import-person and customer-import-company. Each test uses strict requestPartFields(...) with its exact variant schema. In the operation description, explain the discriminator and payload selection conditions.

If the contract genuinely allows a superset schema with many optional fields, a unified schema can be documented. However, you must clearly note which fields depend on kind and how fields belonging to another variant are rejected.

## 9. Organizing snippets across multiple operations

Suppose tests generate snippets into build/generated-snippets. The directory structure might look like:

```text
build/generated-snippets/
  document-create/
    request-parts.adoc
    request-part-metadata-fields.adoc
    http-request.adoc
    http-response.adoc
  document-update-details/
    request-parts.adoc
    request-part-metadata-fields.adoc
    http-request.adoc
    http-response.adoc
```

Each operation has its own directory, so common snippet filenames can be kept inside each directory without confusion. Avoid having multiple operations write to the same identifier if they have different schemas or requests.

In Asciidoctor, organize into separate sections:

```asciidoc
= Document API

== Create document

include::{snippets}/document-create/request-parts.adoc[]
include::{snippets}/document-create/request-part-metadata-fields.adoc[]
include::{snippets}/document-create/http-request.adoc[]

== Update document metadata

include::{snippets}/document-update-details/request-parts.adoc[]
include::{snippets}/document-update-details/request-part-metadata-fields.adoc[]
include::{snippets}/document-update-details/http-request.adoc[]
```

Readers clearly see the same part name while both contracts are presented in separate operation sections. The {snippets} variable must be configured to point to the output directory. With Markdown, use TemplateFormats.markdown() and an appropriate snippet assembly step; standard Markdown has no built-in include syntax like Asciidoctor.

## 10. Testing operation-dependent contracts

Each operation should have tests demonstrating valid payloads and critical conditions:

| Check | Create operation | Update operation |
| --- | --- | --- |
| Missing metadata part | Rejected if required | Rejected if endpoint requires part |
| Missing title | Rejected | May be accepted, keeping old title |
| Missing category | Rejected | Field not accepted; define behavior if sent by client |
| File present | Required | Outside contract |
| Field outside schema | Strict descriptor catches during documentation | Strict descriptor catches during documentation |
| Empty payload | Rejected if metadata needs fields | Must clearly define whether no-op is allowed |

Negative tests do not need to use the same document(...) call as the success snippet test. You can write dedicated validation tests to verify HTTP status and error bodies, while documenting error responses according to documentation goals.

### 10.1. Do not share one fixture across all operations

Shared fixtures easily cause update tests to accidentally send category or file even though the update endpoint does not accept them. Create purpose-specific fixtures, for example:

- create-document-metadata.json
- update-document-metadata.json
- person-import-metadata.json
- company-import-metadata.json

What matters is that each fixture represents a clear request contract and is used in its corresponding test.

### 10.2. Verify values, not just structure

requestPartFields(...) confirms that documented fields match the tested payload. It does not verify all business rules. Add assertions to verify:

- visibility only accepts valid values.
- Absent fields in PATCH do not overwrite existing data.
- category cannot be changed if the operation does not support it.
- kind is consistent with the person or company object.
- File only appears in operations allowing uploads.

## 11. WebTestClient and REST Assured

Payload descriptors do not depend on the test client. The test client constructs the multipart request; Spring REST Docs receives the executed request and generates snippets by operation identifier.

### 11.1. WebTestClient

You can create a separate multipart body for the create operation:

```java
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder createParts = new MultipartBodyBuilder();
createParts.part("metadata", """
        {"title":"Spring REST Docs","category":"TECHNICAL","visibility":"TEAM"}
        """)
        .contentType(MediaType.APPLICATION_JSON);
createParts.part("file", new ByteArrayResource("%PDF-demo".getBytes()) {
    @Override
    public String getFilename() {
        return "guide.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(createParts.build()))
        .exchange()
        .expectStatus().isOk();
```

In the document(...) call of the WebTestClient integration, use a distinct identifier and the create operation's metadata descriptors. Create another body builder for PATCH/update rather than reusing the document creation payload.

### 11.2. REST Assured

REST Assured should likewise use separate filters/document identifiers per operation:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"title\":\"Spring REST Docs\","
                        + "\"category\":\"TECHNICAL\",\"visibility\":\"TEAM\"}",
                "application/json")
        .multiPart("file", new File("guide.pdf"))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(200);
```

documentationFilter must be configured per the REST Assured integration and the descriptors of the operation under test. The snippet above illustrates sending the request; it does not define a prebuilt helper. Calling multiPart(...) alone is insufficient to generate snippets without attaching the right documentation filter.

## 12. Common errors and how to fix them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Create and update tests share the same metadata table | Reused same identifier or descriptor despite different contracts | Separate identifiers and descriptors per operation |
| category appears in update request and strict document errors | Request sends field outside update schema | Fix fixture or clarify whether operation supports the field |
| Missing title in update fails documentation | Descriptor not marked optional though contract permits absence | Mark optional for truly optional fields |
| Using ignored to hide category without testing | Confusing internal fields with disallowed fields | Define behavior when field appears and write tests |
| Using relaxedRequestPartFields for all tests | Fails to catch newly added unpublished fields | Use strict for main contracts; relaxed only for partial docs |
| Two discriminator payload types merged into overly broad schema | Not describing relationship between discriminator and fields | Document each variant or clearly describe unified schema |
| One operation's snippets overwrite another's | Reusing same identifier and snippet names | Create separate identifier directories |
| Documentation has right snippet yet wrong optional description | Relying on a single sample fixture | Add absent/null/present tests and document semantics |

## 13. Asciidoctor and CI integration

Workflow:

1. Create a contract table for each operation before writing descriptors.
2. Create dedicated tests and fixtures for each operation or payload variant.
3. Use requestParts(...) to describe parts; use strict requestPartFields(...) for the operation's complete schema.
4. Only use optional() for fields that may be absent; ignored() for known fields intentionally withheld from publication; relaxedRequestPartFields(...) when intentionally documenting part of a payload.
5. Use separate document identifiers so snippets do not collide.
6. Include the right snippets in each operation section of Asciidoctor.
7. Run tests and render documentation in CI. When an operation changes schema, the corresponding test forces that operation's descriptors to be reviewed.

Example Gradle command once tasks are configured:

```bash
./gradlew test asciidoctor
```

If outputting Markdown snippets, configure TemplateFormats.markdown() and assemble snippets with your project's documentation tooling. Markdown lacks a built-in include mechanism like Asciidoctor.

## 14. Hands-on exercise

A media management API has two operations:

**Create media**

```http
POST /api/media
Content-Type: multipart/form-data

Part "metadata" (application/json):
{
  "name": "Team photo",
  "mediaType": "IMAGE",
  "visibility": "TEAM"
}

Part "file" (image/png):
...binary image...
```

**Update media information**

```http
PATCH /api/media/MED-10
Content-Type: multipart/form-data

Part "metadata" (application/json):
{"name":"Engineering team photo"}
```

Perform the following:

1. Define separate metadata schemas for each operation.
2. Create suitable DTOs or request models; do not assume both operations must share one DTO.
3. Write two MockMvc tests using the same part name metadata with different fixtures.
4. Document the create operation with name, mediaType, and visibility; document the update operation with name optional per contract.
5. Use document identifiers media-create and media-update-details.
6. Try sending mediaType in the update; decide whether the server rejects or ignores it and document the exact behavior.
7. Generate separate snippets, include them into two Asciidoctor sections, and run build/CI.

**Completion criteria:** Integrators can determine the exact payload to send for each operation; optional and unsupported fields are not confused; snippets do not overwrite one another; tests prove both schema and actual behavior.

## 15. Key takeaways

Sharing a part name does not imply the payload shares the same schema across all operations. Define contracts by method/path and intent, create dedicated requestPartFields(...) for each document identifier, use optional() for fields that may be absent, ignored() for known fields intentionally left unpublished, and relaxedRequestPartFields(...) when documenting only part of a payload. For discriminator-based variants, clearly describe each schema or dependency rule. Dedicated tests and snippets for each operation keep Spring REST Docs documentation accurately reflecting the exact requests clients must send in build/CI.

### References

- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
