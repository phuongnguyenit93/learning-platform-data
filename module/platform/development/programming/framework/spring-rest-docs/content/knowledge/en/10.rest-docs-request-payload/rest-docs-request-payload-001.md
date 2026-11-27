# Documenting Request Payloads with `requestFields`

## 1. Why document request payloads from tests?

When an API accepts JSON, writing request examples in documentation alone is not enough: examples can become outdated after the controller or DTO changes. **Spring REST Docs** solves this problem by generating documentation from actual executed HTTP tests. If a test fails its request/response expectations or the payload description does not match the sample data, documentation generation fails. As a result, the documentation and the tested behavior share a single point of verification.

In the **Request payload** chapter, `requestFields(...)` is the central tool for describing the fields of a request body, especially a **JSON request body**. You can use it with MockMvc, WebTestClient, or REST Assured through the corresponding Spring REST Docs integration.

After this lesson, you will be able to:

- Identify JSON field paths, including nested objects and array elements.
- Write a MockMvc test that both verifies the API and generates the `request-fields.adoc` snippet.
- Distinguish between documented required fields, optional fields, ignored fields, and relaxed documentation.
- Include snippets in Asciidoctor documentation and the build/CI pipeline to prevent stale documentation.

## 2. What does `requestFields` describe?

Suppose the system has a `POST /api/orders` API with the following sample request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 42,
  "items": [
    { "sku": "BOOK-001", "quantity": 2 },
    { "sku": "PEN-002", "quantity": 1 }
  ],
  "note": "Deliver during business hours"
}
```

We want to generate a documentation table with content equivalent to:

| Field path | JSON type | Required | Description |
| --- | --- | --- | --- |
| `customerId` | Number | Yes | ID of the customer placing the order |
| `items` | Array | Yes | List of items |
| `items[].sku` | String | Yes | Product SKU of each item |
| `items[].quantity` | Number | Yes | Quantity of each item |
| `note` | String | No | Delivery note |

Spring REST Docs creates these descriptions using `PayloadDocumentation.requestFields(...)` combined with `FieldDescriptor` instances produced by `fieldWithPath(...)`.

In the **strict mode** of `requestFields`, snippet generation fails when the sample request contains an undocumented field or is missing a field declared as required in the documentation. `optional()` fields are allowed to be absent; `ignored()` fields are recognized but do not appear in the documentation table. Note that documenting **a parent object or array** can cause its child fields to be considered covered, so if you want detailed structural control, you must also declare the important child fields.

`requestFields` checks **documentation coverage for the payload sent in the test**. It does not replace Bean Validation, business-logic testing, or a comprehensive JSON Schema validator. For example, `.type(JsonFieldType.NUMBER)` determines the type displayed in the snippet; it should not be treated as a standalone input data type validation.

## 3. Setting up Spring REST Docs with MockMvc

For a Spring Boot project using Gradle and MockMvc, you need the Spring REST Docs test dependency along with the Spring Boot test starter (with the actual version managed by the project or BOM):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

In a Spring Boot 3.x project, you can configure the test using `@SpringBootTest`, `@AutoConfigureMockMvc`, and `@AutoConfigureRestDocs`. The example below assumes the `POST /api/orders` endpoint is already implemented and returns HTTP `201 Created` for a valid payload. Adjust the path, data, and status code to match your actual API.

## 4. Writing a test that documents a request with `requestFields`

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderApiDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateOrderRequest() throws Exception {
        String requestBody = """
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 },
                    { "sku": "PEN-002", "quantity": 1 }
                  ],
                  "note": "Deliver during business hours"
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestBody))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(
                                fieldWithPath("customerId")
                                        .type(JsonFieldType.NUMBER)
                                        .description("ID of the customer placing the order"),
                                fieldWithPath("items")
                                        .type(JsonFieldType.ARRAY)
                                        .description("List of items"),
                                fieldWithPath("items[].sku")
                                        .type(JsonFieldType.STRING)
                                        .description("Product SKU"),
                                fieldWithPath("items[].quantity")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Order quantity"),
                                fieldWithPath("note")
                                        .type(JsonFieldType.STRING)
                                        .description("Delivery note")
                                        .optional()
                        )
                ));
    }
}
```

Execution flow of the test:

1. MockMvc sends an HTTP request containing the actual JSON to the Spring application initialized for testing.
2. `andExpect(status().isCreated())` verifies that the API returns the expected status code.
3. `document("orders-create", ...)` selects the snippet directory name; `requestFields(...)` provides the list of fields to describe.
4. If both the test and the documentation step succeed, Spring REST Docs generates snippets in `build/generated-snippets/orders-create/`.

Typical files include `http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, `httpie-request.adoc`, and, because `requestFields` was declared, **`request-fields.adoc`**. The exact list depends on the project's snippet configuration. The content of `request-fields.adoc` is a table describing the fields based on the test's `FieldDescriptor` definitions.

### Field path structure

| JSON structure | Path syntax | Notes |
| --- | --- | --- |
| `{ "email": "a@example.com" }` | `email` | Root-level field |
| `{ "address": { "city": "Hanoi" } }` | `address.city` | Field inside a nested object |
| `{ "tags": ["java", "spring"] }` | `tags` or `tags[]` | `tags` describes the entire array; `tags[]` describes the elements |
| `{ "items": [{ "sku": "A" }] }` | `items[].sku` | The `sku` field inside each object of the array |
| `{ "groups": [["a", "b"]] }` | `groups[][]` | Elements inside a nested array |

When writing a descriptor for `items[].sku`, there should be at least one element in `items` in the sample request so that the field actually appears and is verified. With an empty list, required child field descriptors may be treated as having no corresponding data. Design a separate test for the empty-list case according to your API rules.

## 5. Controlling how individual fields are documented

### 5.1. Optional fields: `optional()`

```java
fieldWithPath("note")
        .type(JsonFieldType.STRING)
        .description("Delivery note, can be omitted")
        .optional()
```

This declaration allows **the sample request to omit** `note` while snippet generation still succeeds. It reflects that the caller is permitted to omit the field according to the API contract. If you need to verify that the API handles the absence of `note` properly, write an additional test that sends a payload without `note`.

### 5.2. Technical fields you do not want to display: `ignored()`

```java
fieldWithPath("clientTraceId")
        .description("Internal trace ID")
        .ignored()
```

A field declared with `ignored()` is treated as known to avoid an undocumented-field error, but it does not appear in the generated documentation table. Only use this when there is a clear reason; if the client needs to send this field as part of the public contract, document it normally.

### 5.3. Describing a large branch: `subsectionWithPath(...)`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("shippingAddress")
        .description("Shipping address details")
```

`subsectionWithPath` records an entire JSON branch as a single entry in the documentation. It is useful when you want to introduce a complex structure at a high level or split the documentation into multiple sections. The trade-off is that child fields are not listed individually in this table; when the API contract requires describing each component, use specific paths such as `shippingAddress.city` and `shippingAddress.postalCode`.

### 5.4. Relaxing extra-field checks: `relaxedRequestFields(...)`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
        fieldWithPath("customerId").description("Customer ID"),
        fieldWithPath("items").description("List of items")
)
```

`relaxedRequestFields` **does not fail when the sample payload contains undocumented fields**. However, declared required descriptors must still be found in the payload. This approach is suitable when you only want to document part of a request; for public APIs that require a complete contract, prefer strict `requestFields` so new undocumented fields are caught easily.

### 5.5. Types and data constraints

`fieldWithPath(...).type(JsonFieldType.STRING)` keeps the table consistent and readable, especially when a sample value may be `null`. If `.type(...)` is not set, Spring REST Docs usually infers the type from the sample payload. Common values include `STRING`, `NUMBER`, `BOOLEAN`, `OBJECT`, `ARRAY`, `NULL`, and `VARIES`.

Conditions such as "quantity must be greater than 0" or "SKU must not be blank" do not become input validation rules through `.description(...)` alone. You must enforce them with Bean Validation and endpoint tests, while stating the condition clearly in the description, for example:

```java
fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Product quantity; integer greater than 0")
```

You can also add metadata with `.attributes(...)` and customize the snippet template to display columns like "Example", "Allowed values", or "Constraints". **Custom metadata does not appear automatically** in the default table unless the template supports it.

## 6. Using with WebTestClient and REST Assured

The `requestFields(...)`, `fieldWithPath(...)`, `optional()`, and `ignored()` APIs are shared payload-description components. The main difference lies in how the documentation generator is attached to the HTTP test:

| Test tool | Documentation hook | Suitable for |
| --- | --- | --- |
| MockMvc | `.andDo(document("orders-create", requestFields(...)))` | Spring MVC, in-application HTTP testing |
| WebTestClient | `.expectBody().consumeWith(document("orders-create", requestFields(...)))` | Spring WebFlux or testing with WebTestClient |
| REST Assured | `.filter(document("orders-create", requestFields(...)))` before sending the request | Tests written with REST Assured syntax |

In each variant, you must use the `document` method from the corresponding integration and configure REST Docs before calling it. For instance, MockMvc's `document` is in `MockMvcRestDocumentation`, WebTestClient's is in `WebTestClientRestDocumentation`, and REST Assured's is in `RestAssuredRestDocumentation`. Do not mix these static imports in the same example.

## 7. Including snippets in Asciidoctor documentation and the build

Spring REST Docs typically generates snippets in AsciiDoc format (`.adoc`). In a source document, such as `src/docs/asciidoc/api.adoc`, you can include them:

```adoc
= Order API
:toc: left

== Create order

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request body fields
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]
```

The `{snippets}` attribute must point to the directory containing the test output. Example Gradle configuration with the Asciidoctor plugin already installed in the project:

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

With this configuration, the `asciidoctor` task runs after `test`, reads the newly generated snippets, and produces HTML documentation. In CI, run the test and documentation tasks configured for the project; if documentation tests fail, the build must fail to avoid publishing inaccurate documentation. With Maven, the idea is the same: define the snippet directory and run tests before rendering Asciidoctor.

If the project wants to output **Markdown** documentation, you need to configure the appropriate templates/snippets or conversion step. By default, do not assume a `request-fields.md` file is created; the common snippet filename in this example is `request-fields.adoc`.

## 8. Common errors and how to fix them

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Reports undocumented fields | Payload has a new field but is missing a descriptor | Add the corresponding `fieldWithPath`; avoid using `relaxedRequestFields` just to hide the error |
| Reports missing declared fields | Test sends a payload missing a field required by a descriptor | Check the test data and JSON paths; use `optional()` if the field is truly not required |
| Cannot find `items[].sku` | Used `items.sku` or the sample array is empty | Use the `[]` syntax and representative sample data |
| HTTP test passes but no `request-fields.adoc` | Did not call `document(..., requestFields(...))`, REST Docs not configured, or reading the wrong output directory | Check test configuration, `document`, and `outputDir` |
| Asciidoctor reports missing include file | Documentation ran before tests or `{snippets}` points to the wrong path | Make the documentation task depend on the test task and align the snippet directory |
| Documented types/constraints do not match reality | `.type(...)` and description do not automatically validate all business rules | Add validation/negative-case tests and update descriptions per the API contract |

## 9. Hands-on exercise

On the create-order endpoint in the example:

1. Add the `couponCode` field (string, optional) to the sample request and to the descriptors using `fieldWithPath("couponCode").optional()`; verify the snippet contains a row describing this field.
2. Remove `couponCode` from the sample request and re-run the test to confirm that the test still generates documentation successfully.
3. Add a new field `salesChannel` to the JSON **without** adding a descriptor yet; observe the documentation failure in strict `requestFields` mode. Then add the descriptor and re-run.
4. Include `request-fields.adoc` in the Asciidoctor document; verify that the fields table appears in the rendered output.

**Remember:** Every time a new field is added to a test's request JSON, strict `requestFields` produces a signal to update the documentation. Combined with HTTP tests, data validation tests, and CI builds, snippets become a verifiable part of the REST API contract.
