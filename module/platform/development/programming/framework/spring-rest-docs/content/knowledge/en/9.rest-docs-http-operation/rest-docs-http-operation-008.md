# Request and Response Formatting When Bodies Are Present

## 1. Lesson Objectives

HTTP requests and responses can carry bodies in many formats: JSON, XML, URL-encoded forms, multipart, plain text, or binary data. With **Spring REST Docs**, tests must send and receive bodies matching the real contract; descriptors document the payload; and documentation is then compiled with Asciidoctor/Markdown and integrated into build and CI pipelines.

This lesson belongs to the **SPRING_REST_DOCS** module, guiding how to generate verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, producing snippets for requests, responses, payloads, parameters, and headers.

After this lesson, you will be able to distinguish bodies from media types, test multiple payload formats, use `requestFields(...)`/`responseFields(...)`, select form/multipart descriptors, handle empty bodies, and integrate snippets into CI.

> Spring REST Docs records the body of the tested HTTP operation. It does not create endpoints, fixtures, or message converters on its own. Descriptors verify that documentation matches payloads; they do not replace all business assertions.

## 2. Bodies and Media Types

The `Content-Type` header describes the media type of the representation in the body. It does not alter the body bytes and does not turn a malformed payload into a valid one.

JSON request:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Spring in Action","price":199000}
~~~

JSON response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/books/102

{"id":102,"title":"Spring in Action","price":199000}
~~~

The request body is sent by the client; the response body is returned by the server. Each direction has its own media type per the contract.

| Media type | Structure | Scenario |
| --- | --- | --- |
| `application/json` | JSON object/array/scalar | REST API business data. |
| `application/problem+json` | Problem Details JSON | Error body per RFC 9457. |
| `application/xml` | XML document | XML system integration. |
| `application/x-www-form-urlencoded` | Encoded name/value pairs | Simple forms. |
| `multipart/form-data` | Multiple parts with own headers/bodies | File uploads and metadata. |
| `text/plain` | Text | Text-based APIs. |
| `application/octet-stream` | Byte sequence | Generic binary data. |
| `image/png`, `application/pdf` | Type-specific binary | Images, PDFs, and file downloads. |

### 2.1. Body, `Content-Type`, and `Content-Encoding`

- **Body:** the actual content of the message.
- **Content-Type:** the representation format, e.g., JSON or XML.
- **Content-Encoding:** how the representation is encoded/compressed, e.g., `gzip`.

`Content-Encoding: gzip` does not change a JSON media type into another type. HTTP clients may automatically decompress before a test reads the body; determine whether the test inspects the decoded representation or raw bytes on the wire.

### 2.2. How Spring Reads and Writes Bodies

In Spring MVC, `HttpMessageConverter` converts HTTP bodies between bytes and Java types. `@RequestBody` reads the body into a DTO/record; response objects are serialized into the body by a converter. Mappings can restrict formats via `consumes` and `produces`.

~~~java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request) {
    BookResponse created = bookService.create(request);
    return ResponseEntity
        .created(URI.create("/api/books/" + created.id()))
        .body(created);
}
~~~

An unsupported media type can result in `415 Unsupported Media Type`; a representation not matching `Accept` can result in `406 Not Acceptable`. Malformed syntax or binding failures typically produce `400 Bad Request`, depending on error handling.

## 3. JSON Request Bodies

### 3.1. JSON Objects and Field Descriptors

Book creation payload:

~~~json
{
  "title": "Spring in Action",
  "price": 199000,
  "available": true
}
~~~

Illustrative dependencies for Spring Boot 3.x, JUnit 5, Java 17+:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

MockMvc test assuming the endpoint and fixtures already exist and return `201 Created`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookBodyDocumentationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateBook() throws Exception {
        mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "title": "Spring in Action",
                      "price": 199000,
                      "available": true
                    }
                    """))
            .andExpect(status().isCreated())
            .andDo(document("books-create",
                requestFields(
                    fieldWithPath("title").description("Book title"),
                    fieldWithPath("price").description("Book price in VND"),
                    fieldWithPath("available").description("Whether the book is on sale")
                )
            ));
    }
}
~~~

`requestFields(...)` serves two roles: generating the payload description table and checking that descriptors match the body. In strict mode, an undocumented field that appears or a documented required field that is missing fails snippet generation unless `optional()`/`ignored()` is appropriately used. Descriptors do not automatically verify `price > 0` or non-empty titles; write separate assertions/validation tests for that.

### 3.2. Nested JSON and Arrays

~~~json
{
  "customer": {"id": 42, "name": "Lan"},
  "items": [
    {"sku": "BOOK-42", "quantity": 2},
    {"sku": "BOOK-77", "quantity": 1}
  ],
  "note": "Deliver during business hours"
}
~~~

Descriptors:

~~~java
requestFields(
    fieldWithPath("customer").description("Customer information"),
    fieldWithPath("customer.id").description("Customer ID"),
    fieldWithPath("customer.name").description("Customer name"),
    fieldWithPath("items").description("List of line items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Quantity"),
    fieldWithPath("note").description("Note")
)
~~~

`items[].sku` documents fields across array elements, unlike the JSONPath assertion `$.items[0].sku`. You can use `subsectionWithPath("customer")` to document an overview of a subtree; decide whether detailed child fields also need listing.

A field that may be absent:

~~~java
requestFields(
    fieldWithPath("title").description("Book title"),
    fieldWithPath("description")
        .description("Description, may be omitted")
        .optional()
)
~~~

`optional()` allows a field to be absent; it is not the same as a JSON `null` value. `ignored()` intentionally omits a field from the table. `relaxedRequestFields(...)` allows extra undocumented fields; use it only when docs intentionally cover part of a payload, never to hide schema drift.

## 4. JSON Response Bodies

Requests and responses use their respective descriptors:

| Direction | API | Snippet |
| --- | --- | --- |
| Request JSON | `requestFields(...)` | `request-fields.adoc` |
| Response JSON | `responseFields(...)` | `response-fields.adoc` |

Illustrative payload:

~~~json
{
  "id": 102,
  "title": "Spring in Action",
  "price": 199000,
  "available": true
}
~~~

A test can verify status, media type, values, and schema:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@Test
void documentGetBook() throws Exception {
    mockMvc.perform(get("/api/books/102")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(102))
        .andExpect(jsonPath("$.title").value("Spring in Action"))
        .andDo(document("books-get",
            responseHeaders(
                headerWithName("Content-Type")
                    .description("Media type of the response body")
            ),
            responseFields(
                fieldWithPath("id").description("Book ID"),
                fieldWithPath("title").description("Book title"),
                fieldWithPath("price").description("Book price"),
                fieldWithPath("available").description("Availability status")
            )
        ));
}
~~~

This method is added to the test class from the previous section, requiring `get` and `status` imports. `jsonPath(...)` checks values; `responseFields(...)` checks and documents the schema. For nested responses, paths like `items[].sku` can be used. Do not rely on response fields to assert domain rules that haven't been checked with assertions.

## 5. XML Requests and Responses

If the endpoint actually supports XML, an example request:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/xml
Accept: application/xml

<book>
  <title>Spring in Action</title>
  <price>199000</price>
</book>
~~~

MockMvc:

~~~java
mockMvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_XML)
        .content("""
            <book>
              <title>Spring in Action</title>
              <price>199000</price>
            </book>
            """))
    .andExpect(status().isCreated())
    .andDo(document("books-create-xml"));
~~~

The example assumes the application has an XML message converter and matching `consumes`/`produces` mappings. Changing only the header while keeping a JSON body does not turn the payload into XML.

Spring REST Docs supports documenting XML payloads using field paths/XPath according to the structure and rules of your library version. Illustrative example:

~~~java
requestFields(
    fieldWithPath("book.title").description("Book title"),
    fieldWithPath("book.price").description("Book price")
)
~~~

Actual paths depend on the root element and namespaces. For XML with namespaces, configure namespace handling appropriately. Always inspect generated snippets; do not apply JSON paths such as `items[].sku` to XML.

## 6. URL-Encoded Forms and Multipart

### 6.1. URL-Encoded Forms

~~~http
POST /api/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&remember=true
~~~

This is a form body, not JSON or a query string. Use `formParameters(...)`:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

.andDo(document("login-form",
    formParameters(
        parameterWithName("username").description("Username"),
        parameterWithName("remember").description("Remember login session")
    )
));
~~~

Place descriptors inside the `document(...)` call of a test sending the proper form media type. Do not use `requestFields(...)` as if the form body were JSON.

### 6.2. Multipart Uploads

Multipart consists of multiple parts; each part can have a name, filename, media type, and content. The HTTP client must generate a proper boundary. Never set `Content-Type: multipart/form-data` without a boundary when constructing requests manually.

~~~java
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

@Test
void documentUploadCover() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
        "file", "cover.png", MediaType.IMAGE_PNG_VALUE,
        new byte[] { 1, 2, 3, 4 }
    );

    mockMvc.perform(multipart("/api/books/42/cover")
            .file(file)
            .param("description", "Book cover"))
        .andExpect(status().isCreated())
        .andDo(document("book-cover-upload",
            requestParts(
                partWithName("file").description("Book cover image")
            )
        ));
}
~~~

The example assumes the endpoint accepts a `file` part and `description` metadata. The byte array is just a fixture. `requestParts(...)` documents each part; if you need to document form fields as well, use appropriate descriptors and verify actual output.

## 7. Plain Text, Binary, and Large Bodies

Plain text request:

~~~http
POST /api/search HTTP/1.1
Content-Type: text/plain
Accept: text/plain

Spring REST Docs
~~~

Use `contentType(MediaType.TEXT_PLAIN)` and `content(...)`; verify responses with `content().string(...)`. Do not use JSON field descriptors for plain text bodies.

A PDF file response might look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-102.pdf"

(binary bytes)
~~~

Tests can compare bytes, checksums, size, or headers. For large files, avoid embedding the entire binary in documentation; document status, media type, `Content-Disposition`, size, and download instructions. Streaming responses need a test strategy based on consuming the stream; `responseFields(...)` does not document binary payloads.

## 8. Encoding and Serialization

JSON bodies can contain Unicode:

~~~json
{"name":"Nguyễn Thị Lan","note":"Giao sách vào buổi sáng"}
~~~

Standardize files and fixtures to UTF-8; verify deserialized values. It is not mandatory to add `charset=UTF-8` to every `application/json` header if the contract does not require it.

Distinguish JSON types:

~~~json
{"quantity":2,"quantityText":"2","available":true,"description":null}
~~~

The number `2`, string `"2"`, boolean `true`, and `null` are distinct. Field descriptors explain position and meaning; they do not replace JSON Schema or type/value assertions. Two JSON payloads differing in whitespace or property order can still be structurally equivalent; if a digital signature or checksum requires exact bytes, verify bytes per the contract.

## 9. Empty Bodies and Special Responses

| Case | Method/status | Rule |
| --- | --- | --- |
| Successful deletion | `204 No Content` | No response body. |
| Cache unchanged | `304 Not Modified` | No response body. |
| HEAD | `HEAD` | No response body; headers may describe the corresponding GET. |
| Error response | `4xx`/`5xx` | May have an error body per contract. |
| File download | `200 OK` | Body may be binary. |

Testing `204`:

~~~java
mockMvc.perform(delete("/api/books/42"))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""));
~~~

Do not declare `responseFields(...)` for a non-existent payload. For `304`, verify validators/headers and an empty body. For `HEAD`, distinguish response metadata from an actual body.

## 10. Preprocessing Bodies and Protecting Data

Spring REST Docs supports preprocessing records used for snippets. `prettyPrint()` makes JSON easier to read; `removeHeaders(...)` strips sensitive headers from documentation; `modifyHeaders()` replaces header values in the recorded exchange.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Replace the document(...) call at the end of the test with:
.andDo(document("books-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie"),
        prettyPrint()
    ),
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        prettyPrint()
    ),
    requestFields(
        fieldWithPath("title").description("Book title"),
        fieldWithPath("price").description("Book price")
    ),
    responseFields(
        fieldWithPath("id").description("Book ID"),
        fieldWithPath("title").description("Book title"),
        fieldWithPath("price").description("Book price")
    )
));
~~~

This replaces an existing `document("books-create", ...)` call; do not add a second call with the same identifier. Payloads must match descriptors, and removed headers must not simultaneously be declared as required in the record.

- Use dummy fixtures; never put real passwords, tokens, cookies, or personal data in public documentation tests.
- Preprocessors only affect the record used to generate snippets, not the original request/response handled by the application.
- If you remove a header from the record, do not document that header as required and present.
- Never use pretty printing or masking to hide a contract-violating payload; assertions must verify the original response.
- For binaries/large files, avoid embedding raw bytes into documentation artifacts.

## 11. WebTestClient and REST Assured

### 11.1. WebTestClient

Example with a client configured for Spring REST Docs:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.post()
    .uri("/api/books")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue("""
        {"title":"Spring in Action","price":199000}
        """)
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.title").isEqualTo("Spring in Action")
    .consumeWith(document("books-create-webtestclient"));
~~~

`bodyValue(...)` supplies the payload; `contentType(...)` sets the request format; `accept(...)` states the desired response format. Requires the `spring-restdocs-webtestclient` module and an appropriate documentation context.

### 11.2. REST Assured

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(spec)
    .filter(document("books-create-restassured"))
    .contentType("application/json")
    .accept("application/json")
    .body("""
        {"title":"Spring in Action","price":199000}
        """)
.when()
    .post("/api/books")
.then()
    .statusCode(201)
    .contentType("application/json");
~~~

`spec` is a `RequestSpecification` configured with the server and REST Docs. Use the `spring-restdocs-restassured` module and appropriate filter/configurer. The filter may record the operation before the final `then()` assertions complete; CI must require all tests to PASS before publishing.

## 12. Authoring Documentation and CI Integration

Asciidoctor can include snippets:

~~~asciidoc
= Books API

== Create Book

=== HTTP request
include::{snippets}/books-create/http-request.adoc[]

=== Request body
include::{snippets}/books-create/request-body.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/books-create/http-response.adoc[]

=== Response body
include::{snippets}/books-create/response-body.adoc[]

=== Response fields
include::{snippets}/books-create/response-fields.adoc[]
~~~

The `snippets` attribute must point to the output directory, such as `build/generated-snippets`. Plain Markdown renderers typically do not understand Asciidoctor include syntax directly; configure a template or conversion/embedding step.

~~~mermaid
flowchart TD
    A["HTTP tests"] --> B{"Status/body assertions pass?"}
    B -->|No| C["Fail pipeline"]
    B -->|Yes| D["Spring REST Docs generates snippets"]
    D --> E["Asciidoctor/Markdown build"]
    E --> F{"Render passes?"}
    F -->|No| C
    F -->|Yes| G["Package / Publish"]
~~~

The authoring/build task must depend on the snippet-generating test task. Manage the output directory to avoid including stale files from an earlier run. If a payload schema changes before descriptors are updated, tests should fail before documentation is published.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `415 Unsupported Media Type` | `Content-Type` is not supported by endpoint/converter | Check `consumes`, converters, and body. |
| `406 Not Acceptable` | `Accept` asks for a representation not provided | Check `produces` and converters. |
| `400 Bad Request` | Malformed JSON/XML syntax or binding/validation failure | Verify payload and error handling. |
| `request-fields.adoc` fails on new field | Payload has an undocumented field in strict mode | Update descriptors or use relaxed mode intentionally. |
| XML fails to parse | Missing converter or wrong media type | Configure XML converter and test endpoint. |
| Multipart boundary error | Manually constructed header missing boundary | Use the HTTP client's multipart builder. |
| JSON Unicode corruption | Fixture/file uses wrong encoding | Standardize on UTF-8 per contract. |
| Binary snippet too large | Entire file embedded in documentation | Document metadata, size, or checksum instead. |
| `204` has JSON descriptors | Assumed response has a body | Assert empty body and remove response fields. |
| Secret appears in snippet | Real data used in fixtures/headers | Use dummy data and preprocessing. |
| CI uses stale snippets | Docs task lacks test dependency or leftover output exists | Wire task dependencies and manage artifacts. |

## 14. Hands-on Exercise

Build documentation for a profile management API:

| Operation | Body/media type | Outcome |
| --- | --- | --- |
| `POST /api/profiles` | JSON with `name`, `email` | `201 Created`, JSON response with `id`. |
| `GET /api/profiles/42` | No request body | `200 OK`, nested JSON response. |
| `POST /api/profiles/import` | Multipart CSV file and metadata | E.g., `202 Accepted` if supported by contract. |
| `POST /api/profiles/form` | URL-encoded form | Response per contract. |
| `GET /api/profiles/999` | No request body | `404 Not Found` and defined error schema. |

Requirements:

1. Write JSON create/get tests; assert status, media type, and key fields.
2. Generate `request-body`, `response-body`, `request-fields`, and `response-fields`.
3. Add an optional field to test `optional()` and an undocumented field to observe strict descriptor failure.
4. Write a multipart test with a dummy file fixture and document the part via `requestParts(...)`.
5. Write a URL-encoded form test, distinguishing form parameters from query parameters.
6. Add a bodyless response (such as `204` if supported by the API) without JSON field descriptors.
7. Include snippets in Asciidoctor; ensure tests pass before the publish step.

**Completion criteria:** accurately identify media types/bodies in both directions; properly document JSON/XML/form/multipart; verify payloads with assertions and descriptors; handle empty bodies, binary payloads, and sensitive data; and integrate test-generated docs into CI.

## References

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — Request Mapping: Consumes and Produces](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
