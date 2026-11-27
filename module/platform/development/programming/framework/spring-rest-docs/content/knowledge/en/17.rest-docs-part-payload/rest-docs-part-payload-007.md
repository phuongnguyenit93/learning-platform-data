# Distinguishing the Request Body from a Part Body in Spring REST Docs

## 1. An HTTP request can contain multiple body layers

For a regular JSON request, the request body is the payload following the HTTP headers. However, with `multipart/form-data`, the HTTP request body is an envelope containing boundaries, per-part headers, and the content of each part:

```http
POST /api/documents HTTP/1.1
Host: api.example.test
Content-Type: multipart/form-data; boundary=----DocBoundary

------DocBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Spring REST Docs","visibility":"TEAM"}
------DocBoundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

...binary PDF bytes...
------DocBoundary--
```

In the request above:

- **The request body** is the entire multipart envelope, from the opening boundary to the closing boundary.
- **The body of the `metadata` part** is specifically the JSON string.
- **The body of the `file` part** is specifically the bytes of the PDF file.

If the documentation calls this request a “JSON request”, integrators might send a single JSON body instead of multipart. Conversely, if you need to explain the JSON schema of `metadata`, describing only the overall request body will not help readers identify the fields inside that part.

Spring REST Docs generates snippets from HTTP tests using MockMvc, WebTestClient, or REST Assured. The **SPRING_REST_DOCS** module helps create verifiable REST API documentation, assemble snippets into Asciidoctor/Markdown, and integrate them into build/CI. This lesson belongs to the **Part payload** chapter, focusing on distinguishing the request-level body from the body of a part.

After this lesson, you will be able to:

1. Distinguish an HTTP request body from the body of a multipart part.
2. Choose the right API among `requestBody()`, `requestFields(...)`, `requestPartBody(...)`, and `requestPartFields(...)`.
3. Understand the role of `requestParts(...)` and part headers.
4. Write MockMvc tests for regular JSON requests and multipart requests.
5. Assemble the right snippets into documentation and avoid misrepresenting the request structure.

## 2. Scope of a body in HTTP

`Content-Type` describes how to interpret the body of an HTTP message:

| Request | Content-Type | HTTP-level body |
| --- | --- | --- |
| `POST /api/products` sending JSON | `application/json` | A single JSON document |
| `PUT /api/profile` sending XML | `application/xml` | A single XML document |
| `POST /api/documents` sending multipart | `multipart/form-data; boundary=...` | Multipart envelope containing multiple parts |
| `POST /api/search` without payload | No body or empty body depending on request | No payload to describe |

For a standard JSON request:

```http
POST /api/products HTTP/1.1
Content-Type: application/json

{"name":"Keyboard","price":75}
```

The entire JSON object is the request body. You can describe that payload using `requestFields(...)` and/or an appropriate body snippet.

With multipart, the HTTP body contains multiple parts. Each part has its own headers and body; for example, JSON is the body of the `metadata` part while the PDF file is the body of the `file` part. A part's Content-Type does not change the overall Content-Type of the request: the request remains `multipart/form-data`.

## 3. Four payload snippets to distinguish

The APIs below belong to `org.springframework.restdocs.payload.PayloadDocumentation`:

| API | Documented scope | Usage example |
| --- | --- | --- |
| `requestBody()` | Body of the entire HTTP request | Display the request body as a snippet |
| `requestFields(...)` | Fields in the main request payload, usually JSON | Describe `name`, `price` in a JSON body |
| `requestPartBody("metadata")` | Body of the part named `metadata` | Display the raw JSON/text/XML of the part |
| `requestPartFields("metadata", ...)` | Fields inside the `metadata` part's body | Describe `title`, `visibility` of the JSON part |

The two API groups do not replace each other. `requestFields(...)` takes no part name argument because it operates on the request-level payload. `requestPartFields(...)` requires a part name to locate the payload to document.

### 3.1. Standard request body

For a JSON body:

```json
{
  "name": "Keyboard",
  "price": 75
}
```

Field descriptors:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("name").description("Product name"),
    fieldWithPath("price").description("Product price")
)
```

Here `name` and `price` belong to the main JSON body of the request.

### 3.2. Body of a multipart part

For a `metadata` part containing JSON:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;

requestPartFields("metadata",
    fieldWithPath("title").description("Document title"),
    fieldWithPath("visibility").description("Visibility scope")
)
```

The part name `"metadata"` tells Spring REST Docs where to find the nested body. If the part name is omitted or misspelled, the descriptors will not point to the payload being documented.

### 3.3. Complete body examples

To display the raw JSON of the main body, use `requestBody()`. For a JSON part specifically, use `requestPartBody("metadata")`:

```java
requestBody()
requestPartBody("metadata")
```

Do not assume a snippet of the full request body will automatically split multipart sub-payloads into standalone examples. When you need to show a part's body, declare the corresponding part snippet.

## 4. Multipart envelope and part structure

A multipart body has the general shape:

```text
--boundary
part headers

part body
--boundary
part headers

part body
--boundary--
```

A part typically has:

- `Content-Disposition`: form field name, optionally accompanied by `filename`.
- `Content-Type`: media type of the part's content.
- Other headers if used by the contract or application.
- Body: text, JSON, XML data, or binary bytes.

Part name, headers, and body are three distinct aspects. `requestParts(...)` describes the parts; `requestPartBody(...)` describes the content; `requestPartFields(...)` describes the schema of the content.

## 5. Spring MVC model: @RequestBody and @RequestPart

### 5.1. JSON request body with @RequestBody

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record ProductInput(String name, int price) {}

@RestController
class ProductController {
    @PostMapping(path = "/api/products", consumes = MediaType.APPLICATION_JSON_VALUE)
    ProductInput create(@RequestBody ProductInput input) {
        return input;
    }
}
```

`@RequestBody` binds to the main body of the HTTP request. When documenting this JSON payload, `requestFields(...)` is typically used.

### 5.2. Multipart part with @RequestPart

```java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

record DocumentMetadata(String title, String visibility) {}
record DocumentReceipt(String id, String title, String filename) {}

@RestController
class DocumentController {
    @PostMapping(path = "/api/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    DocumentReceipt upload(
            @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("file") MultipartFile file) {
        return new DocumentReceipt("DOC-42", metadata.title(), file.getOriginalFilename());
    }
}
```

`@RequestPart("metadata")` instructs Spring to read the body of the `metadata` part via an appropriate message converter. `@RequestPart("file")` receives the uploaded file. Even though the controller receives a `DocumentMetadata` object, its JSON is still a **part body**, not the entire HTTP request body.

`@RequestParam` typically binds query parameters or form parameters. Do not infer that every controller parameter belongs to the main request body; consider the data's position in the HTTP message and the binding mechanism.

## 6. Example A: documenting a standard JSON body

Here is a MockMvc test for a JSON request body:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ProductRequestBodyDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsJsonRequestFields() throws Exception {
        mockMvc.perform(post("/api/products")
                        .contentType("application/json")
                        .content("""
                                {"name":"Keyboard","price":75}
                                """))
                .andExpect(status().isOk())
                .andDo(document("product-create",
                        requestFields(
                                fieldWithPath("name").description("Product name"),
                                fieldWithPath("price").description("Product price")
                        )));
    }
}
```

For a JSON request, `requestFields(...)` documents the object payload. You can add `requestBody()` if the documentation page needs a snippet containing the intact body; choose snippets according to your project's goals and template format.

## 7. Example B: documenting the body of a multipart part

### 7.1. Preparing parts

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile metadata = new MockMultipartFile(
        "metadata", "", MediaType.APPLICATION_JSON_VALUE,
        """
        {"title":"Spring REST Docs","visibility":"TEAM"}
        """.getBytes(StandardCharsets.UTF_8));

MockMultipartFile file = new MockMultipartFile(
        "file", "guide.pdf", MediaType.APPLICATION_PDF_VALUE,
        "%PDF-demo".getBytes(StandardCharsets.UTF_8));
```

The first parameter of `MockMultipartFile` is the part name. It must match `@RequestPart("metadata")`, `@RequestPart("file")`, and the `partWithName(...)` descriptors.

### 7.2. MockMvc test across multiple scopes

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
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class DocumentMultipartDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new DocumentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsPartAndItsJsonPayload() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                """
                {"title":"Spring REST Docs","visibility":"TEAM"}
                """.getBytes(StandardCharsets.UTF_8));
        MockMultipartFile file = new MockMultipartFile(
                "file", "guide.pdf", MediaType.APPLICATION_PDF_VALUE,
                "%PDF-demo".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/documents").file(metadata).file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("DOC-42"))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("document-upload",
                        requestParts(
                                partWithName("metadata").description("Metadata as JSON"),
                                partWithName("file").description("PDF file to upload")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("title").description("Document title"),
                                fieldWithPath("visibility").description("Visibility scope")
                        ),
                        requestPartBody("metadata")
                ));
    }
}
```

Inside `document(...)`, the three snippets have distinct responsibilities:

1. `requestParts(...)` describes the two parts `metadata` and `file`.
2. `requestPartFields("metadata", ...)` describes the JSON schema inside `metadata`.
3. `requestPartBody("metadata")` creates a body example specifically for the `metadata` part.

Do not declare `requestFields(...)` for `title` and `visibility` in this test: they belong to JSON inside a multipart part. Likewise, do not use `requestBody()` in place of `requestPartBody("metadata")` when the intent is to display the JSON metadata separately.

## 8. Should the entire multipart body be documented with requestBody()?

The multipart envelope is the HTTP request body at the protocol level. However, putting the entire envelope into a text snippet is rarely helpful:

- Boundaries may be dynamically generated by clients, so specific boundaries should not be treated as contract values.
- File parts may contain binary data, which does not render well in text snippets.
- Per-part headers can easily get lost inside a long body block.
- Readers generally need to know the name, type, and schema of each part to build valid requests.

For multipart endpoints, a common presentation approach is:

| Need | Recommended snippet |
| --- | --- |
| List parts and describe their purpose | `requestParts(...)` |
| Show JSON/text body of a part | `requestPartBody("partName")` |
| Explain JSON fields of a part | `requestPartFields("partName", ...)` |
| Describe HTTP request headers | `requestHeaders(...)` |
| Describe per-part headers | Describe in the parts table or separate docs if required by the API |

Only use a request-level body snippet when it genuinely helps readers understand the request. For multipart, documenting part by part is usually clearer and easier to maintain.

## 9. Snippet output and Asciidoctor

With the identifier `document-upload`, the output typically contains these relevant snippets:

```text
build/generated-snippets/
  document-upload/
    request-parts.adoc
    request-part-metadata-fields.adoc
    request-part-metadata-body.adoc
    http-request.adoc
    http-response.adoc
    ...
```

Exact filenames should be checked in the output of the Spring REST Docs version and template format used by your project. Do not guess snippet names and place them into include directives without verifying the files exist.

Example Asciidoctor page:

```asciidoc
= Document API

== Upload document

=== Request parts

include::{snippets}/document-upload/request-parts.adoc[]

=== Metadata schema

include::{snippets}/document-upload/request-part-metadata-fields.adoc[]

=== Metadata body example

include::{snippets}/document-upload/request-part-metadata-body.adoc[]

=== HTTP request

include::{snippets}/document-upload/http-request.adoc[]
```

The `{snippets}` variable must point to the snippet output directory. The name `request-part-metadata-body.adoc` is an example based on naming conventions; verify the exact name after running tests before hardcoding the path.

If using Markdown, configure `TemplateFormats.markdown()` for snippets and use a suitable content assembly step. Standard Markdown lacks a built-in include syntax like Asciidoctor.

## 10. WebTestClient and REST Assured

Snippet scopes remain identical across test clients: the main body and a part body are two different concepts. What changes is how the multipart request is constructed and how the documentation snippet is attached to the test.

### 10.1. WebTestClient

`MultipartBodyBuilder` creates each part along with its Content-Type:

```java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder parts = new MultipartBodyBuilder();
parts.part("metadata", """
        {"title":"Spring REST Docs","visibility":"TEAM"}
        """)
        .contentType(MediaType.APPLICATION_JSON);
parts.part("file", new ByteArrayResource("%PDF-demo".getBytes()) {
    @Override
    public String getFilename() {
        return "guide.pdf";
    }
}).contentType(MediaType.APPLICATION_PDF);

webTestClient.post()
        .uri("/api/documents")
        .body(BodyInserters.fromMultipartData(parts.build()))
        .exchange()
        .expectStatus().isOk();
```

In a test integrated with REST Docs, attach `requestParts(...)`, `requestPartFields("metadata", ...)`, and `requestPartBody("metadata")` to WebTestClient's `document(...)` snippet handler. The snippet above illustrates creating the request; `webTestClient` must be configured with REST Docs beforehand.

### 10.2. REST Assured

REST Assured lets you configure each part:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"title\":\"Spring REST Docs\",\"visibility\":\"TEAM\"}",
                "application/json")
        .multiPart("file", new File("guide.pdf"))
        .when()
        .post("/api/documents")
        .then()
        .statusCode(200);
```

The documentation filter must be configured to generate the corresponding part and payload snippets. Calling `multiPart(...)` alone is not enough to produce snippets without attaching a filter configured with `requestParts(...)`, `requestPartFields(...)`, or `requestPartBody(...)`.

## 11. Common errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Used `requestFields(...)` for JSON metadata but snippet finds no fields | JSON is inside a part, not the main JSON request body | Use `requestPartFields("metadata", ...)` |
| `requestBody()` does not create a dedicated JSON example for metadata | Snippet is scoped to the entire request body | Use `requestPartBody("metadata")` |
| Documentation calls a multipart request a JSON request | Confusing the part's content type with the overall request Content-Type | Clearly state the request is multipart and the metadata part is JSON |
| Request parts table has names but no payload structure | Only used `requestParts(...)` | Add `requestPartFields(...)` or `requestPartBody(...)` |
| JSON part fails to parse | Part lacks proper Content-Type or body is invalid JSON | Set `application/json` and verify the fixture |
| Request body snippet contains hard-to-read boundaries | Attempting to fit the entire multipart envelope into one text example | Document parts, payloads, and media types separately |
| Binary file appears as unreadable characters | Using a body snippet for binary data | Document file metadata; do not dump bytes into documentation |
| Asciidoctor reports missing snippet | Guessed include name does not match actual output | Check snippet directory after tests and fix the include |

## 12. Build and CI

Implementation workflow:

1. Declare the Spring REST Docs dependency matching MockMvc, WebTestClient, or REST Assured.
2. Write tests for JSON request bodies and multipart requests with separate JSON/file parts.
3. Choose the right descriptor group: `requestFields(...)` for main JSON requests; `requestParts(...)`, `requestPartFields(...)`, and `requestPartBody(...)` for multipart.
4. Configure a snippet directory such as `build/generated-snippets` (Gradle) or `target/generated-snippets` (Maven).
5. Configure the Asciidoctor task to depend on the test task and include the exact generated snippets.
6. Run tests and render documentation in CI; the pipeline detects when a body or part schema changes without updating descriptors.

Example Gradle command once corresponding tasks are configured:

```bash
./gradlew test asciidoctor
```

When an endpoint switches from a single JSON body to multipart, that is a major HTTP contract change: clients must change how they send the request, the overall media type, and how each part is constructed. Tests, descriptors, and API usage guides must all be updated.

## 13. Hands-on exercise

Design two endpoints:

**Endpoint A — JSON body**

```http
POST /api/reports
Content-Type: application/json

{"name":"Monthly report","format":"PDF"}
```

**Endpoint B — Multipart**

```http
POST /api/reports/import
Content-Type: multipart/form-data

Part "metadata" (application/json):
{"name":"Monthly report","format":"PDF"}

Part "file" (application/pdf):
...binary content...
```

Steps:

1. Create a controller for Endpoint A using `@RequestBody ReportInput`; document with `requestFields(...)`.
2. Create a controller for Endpoint B using `@RequestPart("metadata") ReportInput` and `@RequestPart("file") MultipartFile`.
3. Write MockMvc tests for both endpoints.
4. For Endpoint B, use `requestParts(...)`, `requestPartFields("metadata", ...)`, and `requestPartBody("metadata")`.
5. Compare the two documentation pages: same JSON schema, yet in one case it is the main request body and in the other it is a part's body.
6. Include snippets, run tests, and render documentation in CI.

**Completion criteria:** Clearly specify whether a body belongs to the request level or part level; use the right descriptors for both endpoints; field tables and body examples match test requests; readers know how to send either a JSON body or a multipart envelope.

## 14. Key takeaways

The body of an HTTP request is the message-level content. For multipart, it is an envelope containing multiple parts, each with its own headers and body. `requestBody()` and `requestFields(...)` apply to request-level payloads; `requestPartBody(partName)` and `requestPartFields(partName, ...)` apply to the payload of a single part; `requestParts(...)` describes the parts. Choosing the right scope ensures Spring REST Docs documentation accurately describes how clients must send requests while keeping payload examples and schemas verifiable from tests in build/CI.

### References

- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework — RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
