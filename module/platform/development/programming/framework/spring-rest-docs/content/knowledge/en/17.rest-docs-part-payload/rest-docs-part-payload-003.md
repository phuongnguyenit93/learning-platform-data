# partBody and Raw Part Data in Spring REST Docs

## 1. When do you need to document the entire body of a part?

Multipart requests allow clients to send multiple content sections within a single HTTP request. For example, a data import API receives a JSON `manifest` part, a text `signature` part, and a `file` part containing binary data:

```http
POST /api/imports HTTP/1.1
Content-Type: multipart/form-data; boundary=----ImportBoundary

------ImportBoundary
Content-Disposition: form-data; name="manifest"
Content-Type: application/json

{"source":"warehouse","version":2,"items":[{"sku":"A-10","quantity":5}]}
------ImportBoundary
Content-Disposition: form-data; name="signature"
Content-Type: text/plain; charset=UTF-8

approved-by=ops;batch=2026-11
------ImportBoundary
Content-Disposition: form-data; name="file"; filename="inventory.csv"
Content-Type: text/csv

sku,quantity
A-10,5
------ImportBoundary--
```

In the API documentation, you may need three levels of description:

- Name and purpose of each part: `requestParts(...)`.
- Field structure of a JSON part: `requestPartFields("manifest", ...)`.
- Body content of a part as an intact block: `requestPartBody("manifest")`.

Integrators may need to see the raw manifest JSON or properly formatted signature string to build compatible requests. A field table cannot show the entire sample payload; `requestPartBody(...)` generates a dedicated body snippet for the selected part.

**Spring REST Docs** generates snippets from HTTP tests. In the **SPRING_REST_DOCS** module, this technique is applied with MockMvc, WebTestClient, or REST Assured so multipart documentation stays verifiable and is integrated into Asciidoctor/Markdown as well as the build/CI. This lesson belongs to the **Part payload** chapter, focusing on `requestPartBody(...)` and the raw data of a part.

After this lesson, you will be able to:

1. Understand how `requestPartBody(partName)` documents the body content of a specific part.
2. Distinguish raw body snippets from `requestPartFields(...)` and `requestParts(...)`.
3. Write multipart MockMvc tests to generate snippets for JSON, text, or XML parts.
4. Determine when a body snippet is appropriate and when to describe metadata instead of dumping binary content.
5. Include part snippets in documentation and verify them in CI.

## 2. Three levels of describing a multipart request

Suppose the request consists of `manifest`, `signature`, and `file`:

| Description level | Spring REST Docs API | Content shown |
| --- | --- | --- |
| Which parts are present? | `requestParts(...)` | Part names and descriptions |
| Which field schema does the part body have? | `requestPartFields("manifest", ...)` | Fields and paths in the JSON payload |
| What content does the part body contain? | `requestPartBody("manifest")` | Body content of the part as a standalone snippet |

Combined example:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

document("inventory-import",
    requestParts(
        partWithName("manifest").description("JSON manifest of the import batch"),
        partWithName("signature").description("Verification signature from the operations team"),
        partWithName("file").description("CSV file containing inventory data")
    ),
    requestPartFields("manifest",
        fieldWithPath("source").description("Data source"),
        fieldWithPath("version").description("Schema version"),
        fieldWithPath("items").description("List of items")
    ),
    requestPartBody("manifest"),
    requestPartBody("signature")
);
```

The three snippet groups complement one another. `requestParts(...)` describes the parts, `requestPartFields(...)` explains the JSON schema, and `requestPartBody(...)` shows readers the complete sample payload for each selected part. You do not have to choose only one API if the documentation genuinely needs all three perspectives.

## 3. Syntax of requestPartBody(...)

`requestPartBody(...)` belongs to `org.springframework.restdocs.payload.PayloadDocumentation` and takes the name of the part to document:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;

requestPartBody("manifest")
```

The name `manifest` must match the part name in the multipart request. For example, the controller declares `@RequestPart("manifest")`, the request builder creates a part named `manifest`, and the snippet uses that same name.

A dedicated body snippet helps present the payload as a sample document. By default snippet naming conventions, the file generated for a part is named `request-part-{partName}-body.adoc`, such as:

```text
request-part-manifest-body.adoc
request-part-signature-body.adoc
```

Check the actual filenames in the snippet directory generated by your project's Spring REST Docs version and configuration before writing fixed include paths.

### 3.1. requestPartBody is not requestBody

`requestBody()` describes the main body of the HTTP request. In a multipart request, the main body is the entire multipart content with boundaries and multiple parts. `requestPartBody("manifest")` selects the body of only the `manifest` part, without documenting the entire multipart envelope.

### 3.2. requestPartBody is not requestPartFields

If the JSON part has the structure:

```json
{
  "source": "warehouse",
  "version": 2,
  "items": [
    {"sku": "A-10", "quantity": 5}
  ]
}
```

`requestPartBody("manifest")` lets readers see the sample JSON payload. `requestPartFields("manifest", ...)` creates a table describing paths such as `source`, `version`, `items[].sku`, and `items[].quantity`. If clients need both a complete example and field-by-field explanations, use both.

### 3.3. Raw data does not mean byte-for-byte

The API name emphasizes the part's body, but a documentation snippet should not be treated as a binary dump capable of restoring every original byte. Spring REST Docs processes payloads according to its snippet mechanism and content type. For JSON/XML/text, the output is suitable to read as sample content; for binary data, rendering it as text may be meaningless or inappropriate. Use part-description snippets and separate documentation for file formats when needed.

## 4. Example: documenting a JSON manifest with requestPartBody

### 4.1. Illustrative controller

The controller receives the manifest as a JSON string so the example focuses on the part's body:

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ImportController {

    @PostMapping(
            path = "/api/imports",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ImportReceipt importData(
            @RequestPart("manifest") String manifest,
            @RequestPart("signature") String signature) {

        return new ImportReceipt("IMP-2026-001", manifest.length(), signature);
    }
}

record ImportReceipt(String importId, int manifestLength, String signature) {}
```

In a real application, the JSON part can be converted to a DTO with `@RequestPart("manifest") ImportManifest`. Using `String` in the example highlights the body without depending on schema mapping logic.

### 4.2. Creating multipart parts in MockMvc

`MockMultipartFile` lets you configure the part name, filename, content type, and body bytes:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile manifest = new MockMultipartFile(
        "manifest",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "source": "warehouse",
          "version": 2,
          "items": [
            {"sku": "A-10", "quantity": 5}
          ]
        }
        """.getBytes(StandardCharsets.UTF_8));

MockMultipartFile signature = new MockMultipartFile(
        "signature",
        "",
        MediaType.TEXT_PLAIN_VALUE,
        "approved-by=ops;batch=2026-11".getBytes(StandardCharsets.UTF_8));
```

`filename` is left empty because the two parts above are text payloads, not file uploads. The Content-Type must match each part's format.

### 4.3. Test documenting the raw part body

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
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ImportPartBodyDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ImportController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsRawManifestAndSignatureBodies() throws Exception {
        MockMultipartFile manifest = new MockMultipartFile(
                "manifest",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {
                  "source": "warehouse",
                  "version": 2,
                  "items": [
                    {"sku": "A-10", "quantity": 5}
                  ]
                }
                """.getBytes(StandardCharsets.UTF_8));

        MockMultipartFile signature = new MockMultipartFile(
                "signature",
                "",
                MediaType.TEXT_PLAIN_VALUE,
                "approved-by=ops;batch=2026-11".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/imports")
                        .file(manifest)
                        .file(signature))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.importId").value("IMP-2026-001"))
                .andExpect(jsonPath("$.signature").value("approved-by=ops;batch=2026-11"))
                .andDo(document("inventory-import",
                        requestParts(
                                partWithName("manifest")
                                        .description("JSON manifest of the import batch"),
                                partWithName("signature")
                                        .description("Text signature from the operations team")
                        ),
                        requestPartBody("manifest"),
                        requestPartBody("signature")
                ));
    }
}
```

In the test:

1. Each `MockMultipartFile` creates an independent part.
2. `requestParts(...)` documents the names and purposes of both parts.
3. `requestPartBody("manifest")` generates a snippet containing the manifest body; `requestPartBody("signature")` generates the signature body snippet.
4. Response assertions confirm the request was received and processed by the controller as in the example. If you need to prove the entire manifest was parsed properly, add assertions for the corresponding fields.

## 5. Using requestPartBody for JSON, XML, and text

### 5.1. JSON part

JSON is usually an appropriate choice when the body is structured and readers need to see the complete sample payload:

```java
requestPartBody("metadata")
```

Set the part's Content-Type to `application/json`. If you also want to add a field definition table:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Object name"),
    fieldWithPath("enabled").description("Activation status")
)
```

The JSON example conveys the overall shape; the field table explains each field.

### 5.2. XML part

An API integrating with legacy systems might accept XML:

```xml
<shipment>
  <reference>SHIP-100</reference>
  <warehouse>HCM-01</warehouse>
  <quantity>5</quantity>
</shipment>
```

The part should have an appropriate Content-Type, such as `application/xml`. When documented with `requestPartBody("shipment")`, the snippet displays the sample XML so integrators can reproduce the payload. If the contract requires an XSD schema or specific namespace, publish the schema and explain it in the endpoint documentation.

### 5.3. Text part

Text example:

```text
approved-by=ops;batch=2026-11
```

`text/plain` parts typically do not need JSON field descriptors. `requestPartBody("signature")` is suitable for documenting the complete string, delimiters, and encoding conventions. If the string contains secrets, tokens, or personal data, do not use real data in the snippet; replace it with safe mock fixtures.

## 6. When should you not dump a part body?

### 6.1. Binary files

For a file part:

```http
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

...binary bytes...
```

Do not rely on a text snippet from `requestPartBody("file")` to present the content of a PDF, image, ZIP, or other binary file. Instead:

- Use `requestParts(...)` to describe the part.
- Document the filename, media type, size rules, and format in the appropriate description.
- If sample files need to be provided, distribute fixtures/documentation assets through a separate project workflow.

### 6.2. Overly large payloads

Do not put thousands of lines of JSON or XML onto an API page just to demonstrate the format. You can use `requestPartBody(...)` for a small representative sample, then describe size limits, pagination, or schemas separately. If the payload has many structures, consider field snippets and linked schema files.

### 6.3. Payloads containing sensitive data

Published snippets may be read by people outside the development team. Use dummy data—never include access tokens, passwords, real signatures, or real user data in test payloads. `requestPartBody(...)` does not automatically mask data.

## 7. Combining part bodies with other snippet types

Complete multipart documentation can include:

| Snippet | Purpose |
| --- | --- |
| `request-parts.adoc` | Names and descriptions of the parts |
| `request-part-manifest-body.adoc` | Sample body of the manifest |
| `request-part-signature-body.adoc` | Sample body of the signature |
| `request-part-manifest-fields.adoc` | Field table of the manifest if `requestPartFields(...)` is used |
| `http-request.adoc` | Overall HTTP request |
| `http-response.adoc` | HTTP response |
| `response-fields.adoc` | Fields of the JSON response if documented |

Specific snippet filenames are determined by Spring REST Docs and the template format. After running tests, inspect the actual output files in `generated-snippets` and use the exact paths in your documentation page.

In Asciidoctor:

```asciidoc
= Import API

== Import batch

=== Request parts

include::{snippets}/inventory-import/request-parts.adoc[]

=== Manifest body

include::{snippets}/inventory-import/request-part-manifest-body.adoc[]

=== Signature body

include::{snippets}/inventory-import/request-part-signature-body.adoc[]

=== HTTP request

include::{snippets}/inventory-import/http-request.adoc[]
```

The `{snippets}` variable must point to the output folder. If using Markdown, select Markdown templates and use an appropriate snippet-assembly tool; standard Markdown does not have a built-in `include` directive like Asciidoctor.

## 8. Common errors and diagnostics

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Part not found to create body snippet | Name in `requestPartBody("manifest")` does not match request | Align part name across `MockMultipartFile`, controller, and descriptor |
| Request parts snippet exists but no body snippet | Only `requestParts(...)` was declared | Add `requestPartBody(partName)` for parts needing a body example |
| Using `requestPartFields(...)` but a full JSON example is needed | Field table does not show the complete sample payload | Add `requestPartBody(...)` |
| Body snippet contains unreadable content | Documenting a binary part | Only document file metadata; do not dump bytes onto the page |
| JSON part fails to parse before snippet generation | Content-Type or JSON body does not suit converter/controller | Send properly formatted `application/json` part and verify binding |
| Body snippet does not reflect values clients must send | Test fixture differs from contract or description is outdated | Use fixtures representing the contract, asserting and documenting the same request |
| Included file reports missing | Guessed wrong snippet name or identifier | Check actual output folder and fix include path |
| Snippet exposes real data | Test fixture uses tokens or user data | Replace with dummy data before publishing |

## 9. WebTestClient and REST Assured

`requestPartBody(...)` is a payload snippet descriptor; the test client integration is responsible for building the multipart request and attaching `document(...)`.

### 9.1. WebTestClient

WebTestClient can construct a multipart body using `MultipartBodyBuilder`. Example illustrating how to send parts:

```java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("manifest", """
        {"source":"warehouse","version":2}
        """)
        .contentType(MediaType.APPLICATION_JSON);
builder.part("signature", "approved-by=ops;batch=2026-11")
        .contentType(MediaType.TEXT_PLAIN);

webTestClient.post()
        .uri("/api/imports")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchange()
        .expectStatus().isOk();
```

In a test configured with REST Docs, attach the `requestPartBody("manifest")` and `requestPartBody("signature")` snippets to the `document(...)` call using the WebTestClient integration API. The example above illustrates request construction; `webTestClient` must be configured with Spring REST Docs beforehand.

### 9.2. REST Assured

REST Assured supports multipart via `multiPart(...)`:

```java
given()
        .filter(documentationFilter)
        .multiPart("manifest",
                "{\"source\":\"warehouse\",\"version\":2}",
                "application/json")
        .multiPart("signature", "approved-by=ops;batch=2026-11", "text/plain")
        .when()
        .post("/api/imports")
        .then()
        .statusCode(200);
```

`documentationFilter` must be configured with Spring REST Docs and corresponding descriptors including `requestPartBody(...)`. Verify the multipart overload and how snippets are attached for the REST Assured version integrated in your project.

## 10. Build and CI

Basic workflow:

1. Declare the Spring REST Docs integration matching your test client: `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient`, or `spring-restdocs-restassured`.
2. Create multipart tests with representative part payloads, defining the Content-Type for each part.
3. Attach `requestParts(...)` and `requestPartBody(...)`; add `requestPartFields(...)` if a field schema is needed.
4. Configure a snippet directory such as `build/generated-snippets` (Gradle) or `target/generated-snippets` (Maven) as output.
5. Make the Asciidoctor task depend on the test task; include the exact generated body snippets.
6. Run tests and render documentation in CI to catch renamed parts, changed bodies, or missing snippets/includes.

Example Gradle command once tasks are configured:

```bash
./gradlew test asciidoctor
```

When the sample body changes, the snippet is regenerated from the test. If the contract changes, update fixtures, assertions, and descriptions to ensure the documentation reflects supported requests.

## 11. Hands-on exercise

Design the `POST /api/batches` endpoint accepting three parts:

- `metadata`: JSON containing `batchId`, `createdBy`, `labels`.
- `checksum`: `text/plain` containing a SHA-256 hex string.
- `archive`: binary ZIP file.

Requirements:

1. Create a controller accepting `@RequestPart("metadata")`, `@RequestPart("checksum")`, and `@RequestPart("archive")`.
2. Write a MockMvc test creating three `MockMultipartFile` instances with corresponding Content-Types.
3. Use `requestParts(...)` to describe all three parts.
4. Use `requestPartBody("metadata")` and `requestPartBody("checksum")` to generate body snippets; do not dump ZIP content via text snippets.
5. If you need to explain the metadata structure, add `requestPartFields("metadata", ...)`.
6. Assert that the response or service invocation receives the expected `batchId` and `checksum`; do not use real checksums or secret data in fixtures.
7. Include the body snippets in Asciidoctor and run tests along with documentation rendering in CI.

**Completion criteria:** Readers can see example bodies for `metadata` and `checksum`, clearly understand that the `archive` part is a binary file, part names and Content-Types match the actual request, and snippets are generated from tests.

## 12. Key takeaways

`requestPartBody(partName)` documents the body of a selected part as a standalone payload snippet. Use `requestParts(...)` to introduce part names and `requestPartFields(...)` to explain the field schema of a JSON/object payload; combine all three when documentation needs to describe part names, sample bodies, and data structures. For binary parts, prefer describing the name, filename, Content-Type, and file constraints rather than dumping bytes into documentation. Connect multipart tests, Asciidoctor/Markdown snippets, and CI so part body examples always originate from verified test requests.

### References

- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
