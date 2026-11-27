# request-body and response-body

## 1. Roles of the Two Body Snippets

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Default Snippets** chapter, HTTP tests generate snippets from the requests and responses executed by the test. The two snippets request-body.adoc and response-body.adoc focus on the HTTP message payload: the data sent by the client and the data returned by the server.

| Snippet | Content | Question to Answer |
| --- | --- | --- |
| request-body.adoc | Body of the HTTP request | What payload did the client send? |
| response-body.adoc | Body of the HTTP response | What payload did the server return? |

The two snippets help readers view sample data. They do not automatically describe field meanings, validation rules, or the full schema. To explain the JSON/XML structure field by field and bind documentation to the payload, use descriptors such as requestFields(...) and responseFields(...).

Spring REST Docs creates snippets when a test executes a request and records the operation with document(...). Body snippets are useful when the operation actually has a corresponding payload. A GET without a request body usually has no meaningful request body content; a 204 No Content response has no response body to document.

Examples in this lesson use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. The same principles apply to WebTestClient and REST Assured through their corresponding integration modules.

## 2. Distinguishing Body Snippets from HTTP Messages and Field Descriptors

These three layers of information complement each other:

| Layer | Snippet/Descriptor | Content Displayed |
| --- | --- | --- |
| HTTP message | http-request.adoc, http-response.adoc | Method, URI/status, headers, and full body in HTTP context |
| Standalone payload | request-body.adoc, response-body.adoc | Body content separated out |
| Structure description table | request-fields.adoc, response-fields.adoc | Field names, descriptions, and optional/ignored status |

Request example:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Mechanical Keyboard","price":89.5}
```

In this example:

- http-request.adoc shows the method, path, headers, and body in a single message.
- request-body.adoc contains only the JSON payload.
- request-fields.adoc (if the test declares requestFields(...)) generates a table explaining name and price.

Response example:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/products/42

{"id":42,"name":"Mechanical Keyboard","price":89.5}
```

http-response.adoc keeps status/headers together with the payload; response-body.adoc contains only the JSON; response-fields.adoc explains the fields. Use all three when readers need to see the protocol, sample payload, and field meanings.

## 3. request-body.adoc: The Payload Sent by the Client

A request body typically appears with resource creation or update operations such as POST, PUT, and PATCH. The payload may be JSON, XML, form data, multipart, or binary content.

JSON example:

```json
{
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "active": true,
  "tags": ["office", "accessory"]
}
```

This snippet shows readers the sample data sent by the test. It is useful for understanding the payload format, copying a sample request, comparing the payload with Content-Type, and reviewing field changes across API versions.

A body snippet does not replace validation checks. Tests still need assertions for status and key outcomes. Calling document(...) without checking the response or controlling input data can cause documentation to reflect an unintended case.

### Requests Without a Body

A typical GET request sends only method, path, and headers:

```http
GET /api/products/42 HTTP/1.1
Accept: application/json
```

There is no payload to include in request-body.adoc. Depending on the template/version and how the operation is recorded, the body snippet may be empty or not generated with meaningful content. Do not invent a dummy JSON body just so the documentation page has every file.

## 4. response-body.adoc: The Payload Returned by the Server

The response body contains the data the client receives after the request is processed. Example:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "active": true
}
```

This snippet helps readers see what format the server returns and provides a sample payload for testing. For endpoints returning a list, the body may be a JSON array or a wrapper object:

```json
{
  "content": [
    {"id": 42, "name": "Mechanical Keyboard"},
    {"id": 43, "name": "Ergonomic Mouse"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2
}
```

Error responses can also be part of the API contract:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Product 999 does not exist"
}
```

Create separate operations for success and error responses if clients need to know both cases. Do not combine different HTTP outcomes under one operation ID and let the last snippet overwrite the others.

### Responses Without a Body

Some valid responses return no payload:

```http
HTTP/1.1 204 No Content
```

In this situation, response-body.adoc has no data to display or may not be generated depending on configuration/version. http-response.adoc still shows the status and headers. Documentation should clearly state that the endpoint returns no body rather than inventing an empty object that misleads readers about the contract.

## 5. MockMvc Example Generating request-body and response-body

### 5.1. Illustrative Controller

```java
package com.example.catalog;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return new ProductResponse(
            42L, request.name(), request.price()
        );
    }

    record CreateProductRequest(String name, BigDecimal price) {}
    record ProductResponse(long id, String name, BigDecimal price) {}
}
```

### 5.2. Dependencies

With Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.3. POST Test Recording Both Request and Response Body

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets/catalog")
class ProductBodyDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createProduct() throws Exception {
        mockMvc.perform(
                post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "name": "Mechanical Keyboard",
                          "price": 89.50
                        }
                        """)
            )
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
            .andDo(document("products-create"));
    }
}
```

After the test passes, the products-create operation has basic HTTP snippets; the two body files focus on the payloads if the request/response has a body:

```text
build/generated-snippets/
  catalog/
    products-create/
      http-request.adoc
      http-response.adoc
      request-body.adoc
      response-body.adoc
```

outputDir is the explicitly configured root directory; products-create is the operation ID and becomes the subdirectory. Rely on the actual files after the test runs for the exact structure, because some templates or bodyless responses may not produce corresponding content.

### 5.4. Adding Descriptors for JSON Fields

If you want to explain and validate the payload, extend the operation:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

document("products-create",
    requestFields(
        fieldWithPath("name").description("Product name"),
        fieldWithPath("price").description("Selling price")
    ),
    responseFields(
        fieldWithPath("id").description("Product ID"),
        fieldWithPath("name").description("Product name"),
        fieldWithPath("price").description("Selling price")
    )
)
```

REST Docs can generate request-fields.adoc and response-fields.adoc in addition to the two body snippets. The field table serves a different role from the raw payload:

- Body snippets show example data.
- Field descriptors state what each field means.
- Descriptors are checked against the payload recorded by the test; a new undocumented field can fail the test.

If a field can be absent or only appears in one response variant, mark it optional or intentionally ignored using the descriptor API. Do not mark fields ignored indiscriminately to hide unexpected contract changes.

## 6. Body Format and Content-Type

Body snippets should be read together with Content-Type. The same byte sequence can be interpreted differently depending on media type; documentation needs to accurately show the format the endpoint accepts or returns.

| Media type | Payload Example | Key Consideration |
| --- | --- | --- |
| application/json | JSON object, array, scalar | Use field descriptors matching JSON paths |
| application/xml | XML document | Verify encoding, namespaces, and schema |
| text/plain | Plain text | No JSON field descriptors |
| application/x-www-form-urlencoded | Form key/value | Distinguish request parameters from JSON payloads |
| multipart/form-data | Multiple parts, possibly with files | Document each part; avoid printing large binary files |
| application/octet-stream | Byte stream | Usually should not dump raw bytes into documentation |

### JSON and Pretty Printing

You can use preprocessRequest(prettyPrint()) and preprocessResponse(prettyPrint()) to format the body in snippets:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

document("products-create",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint())
)
```

A preprocessor affects the content written to documentation. It does not change the request sent by the test or the response returned by the application. If a test needs to prove a byte-for-byte payload or digital signature, do not use a pretty-printed snippet as evidence of the original bytes.

### XML, Text, and Multipart

For XML or text, the body snippet presents content according to the corresponding template. Ensure the test sends the right Content-Type and the response returns the right Content-Type. Do not mechanically apply JSON-oriented requestFields/responseFields if the payload is not the JSON structure the descriptors expect.

For multipart, each part can contain JSON metadata and a file. Use request-part descriptors to describe part names, content types, and metadata; only include a small, non-sensitive sample file if illustration is needed. Do not put large binary data or real customer files into documentation.

## 7. Formatting, Filtering, and Protecting Body Snippets

Body snippets are captured from operations; test data can therefore appear in artifacts. Before publishing, check for:

- Tokens, passwords, cookies, API keys, or authentication credentials in payloads.
- Real emails, phone numbers, addresses, or personal data.
- Internal IDs, non-public service URLs, or production data.
- Large/binary content that makes documentation hard to read.
- Whether bodies are pretty-printed or redacted consistently.

Spring REST Docs supports operation preprocessors to format or replace content before writing snippets. An example is prettyPrint in the previous section. When sensitive fields need masking, choose a preprocessor suitable for your REST Docs version to replace values before saving. The simplest approach is usually using dedicated dummy fixtures for tests.

Pretty printing and redaction alter documentation representation; they are not security assertions. Tests must still verify that the application does not accidentally return secrets in responses if that is a security requirement.

## 8. Including Body Snippets in Asciidoctor

In src/docs/asciidoc/products.adoc:

```asciidoc
= Products API
:toc: left

== Create product

=== Request payload
include::{snippets}/catalog/products-create/request-body.adoc[]

=== Response payload
include::{snippets}/catalog/products-create/response-body.adoc[]

=== Request fields
include::{snippets}/catalog/products-create/request-fields.adoc[]

=== Response fields
include::{snippets}/catalog/products-create/response-fields.adoc[]
```

The {snippets} attribute must point to the snippet root directory (e.g., build/generated-snippets), not directly to an operation directory. The include path following it must match outputDir, any grouping directory, and the operation ID. If an operation has no body or declares no field descriptors, do not include ungenerated files.

With Markdown, use an appropriate content assembly tool and verify the template extension (.md instead of .adoc if Markdown templates are configured). Asciidoctor include syntax does not work automatically in standard Markdown.

## 9. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| request-body.adoc is the entire HTTP request | It contains only the payload; method/path/headers are in the HTTP message snippet. |
| response-body.adoc explains the JSON schema | It displays the payload; a field table requires responseFields(...). |
| Every operation has both body snippets with content | Bodyless requests/responses may produce empty snippets or no meaningful content. |
| Pretty printing changes the application response | It formats the documentation record, not the runtime response. |
| Content-Type does not matter if the body is JSON | Content-Type is contract metadata and affects how servers/clients process the payload. |
| 204 should have an empty JSON object for consistent docs | 204 No Content has no body; documentation must accurately reflect the contract. |
| Having a body snippet means the schema is fully verified | Validating fields requires descriptors; validating behavior requires assertions. |

## 10. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| request-body.adoc is empty | Request sent no body or body was not configured properly. | Check content, Content-Type, and actual request. |
| response-body.adoc has no content | Response has no body, e.g., 204, or operation stopped before document. | Check response status/body and test report. |
| JSON displays on a single unreadable line | prettyPrint not used or template does not format body. | Use prettyPrint preprocessor if appropriate. |
| request-fields.adoc fails | Payload has an undocumented field or wrong descriptor path. | Update field descriptors; check nested paths/arrays. |
| Body snippet contains tokens or real data | Test uses unsafe fixtures. | Replace with dummy fixtures or redact before writing. |
| Multipart snippet is too large | Large test file or raw binary body recorded verbatim. | Use a small dummy file and part descriptors. |
| Asciidoctor cannot find body file | Wrong outputDir/operation ID or operation did not generate that snippet. | Check directory tree after tests and include paths. |
| Snippet shows wrong format | Incorrect Content-Type or unsuitable template/preprocessor. | Verify headers and body actually sent/received by the test. |

## 11. Hands-on Exercise

Create a Catalog API with two endpoints:

1. POST /api/products: accepts JSON name, price; returns 201 Created and JSON containing id, name, price.
2. GET /api/products/{id}: returns product details JSON.

Perform the following:

1. Write a MockMvc POST test to generate request-body.adoc and response-body.adoc.
2. Add requestFields(...) and responseFields(...); compare the body snippets with the field descriptor tables.
3. Pretty-print request/response JSON and observe the difference in the snippets.
4. Create a 204 No Content case or an error response; verify that body snippets accurately reflect absent/present payloads.
5. Create a multipart upload operation with a small dummy file; use part descriptors and avoid placing large binary files into documentation.
6. Include body and field snippets in Asciidoctor, run clean test, and build the documentation.
7. Audit the output to ensure it contains no credentials or real data.

**Completion criteria:** distinguish body snippets from HTTP messages and field descriptors; explain when a body snippet has data; properly record JSON/XML/text/multipart according to Content-Type; format and protect payloads before publishing; assemble the right snippets in documentation.

## 12. References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/configuration/default-snippets.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
