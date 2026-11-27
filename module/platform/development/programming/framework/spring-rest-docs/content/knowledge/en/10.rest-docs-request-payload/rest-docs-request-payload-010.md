# Matching Actual Payloads Against Field Descriptors in Spring REST Docs

## 1. Objective

Spring REST Docs generates documentation from HTTP tests. For JSON requests, `requestFields(...)` uses `FieldDescriptor` instances to validate and describe the payload structure sent in the test. As a result, when JSON changes without documentation being updated, the test can detect the discrepancy before documentation is published.

The two primary APIs are:

- `fieldWithPath("...")`: creates a descriptor for a JSON path.
- `requestFields(...)`: accepts descriptors and generates the `request-fields.adoc` snippet.

Example `POST /api/orders` accepts:

```json
{
  "customerId": 42,
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ],
  "note": "Deliver after 5 PM"
}
```

Declaration:

```java
requestFields(
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("items").description("List of items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Order quantity"),
    fieldWithPath("note").description("Delivery note")
)
```

This lesson belongs to the Request payload chapter of SPRING_REST_DOCS: creating verifiable REST API documentation from MockMvc, WebTestClient, or REST Assured, then integrating snippets with Asciidoctor/Markdown and build/CI.

After this lesson, you will be able to analyze the payload used to generate snippets, spot extra or missing fields, fix wrong paths, distinguish strict and relaxed modes, and design tests that catch contract drift.

## 2. Which payload is matched?

With MockMvc, the payload is usually passed via `.content(...)`:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andDo(document("orders-create",
        requestFields(ORDER_FIELDS)
    ));
```

Spring REST Docs uses the request recorded in the operation to generate snippets. With WebTestClient and REST Assured, documentation is likewise attached to the actual HTTP request through the corresponding integration module.

Descriptors must follow the JSON wire format. Property names in a Java DTO do not necessarily match the key names after Jackson serialization.

Example:

```java
record CreateOrderRequest(
        @JsonProperty("customer_id") Long customerId,
        String note
) {}
```

Outgoing JSON:

```json
{
  "customer_id": 42,
  "note": "Deliver after 5 PM"
}
```

Correct descriptor:

```java
fieldWithPath("customer_id")
        .description("Customer ID");
```

A `customerId` descriptor does not match the JSON key `customer_id`. When a test uses a Java object rather than raw JSON, the output also depends on `ObjectMapper`, naming strategies, annotations, modules, and serialization configuration. Therefore, when investigating a mismatch, inspect the actual JSON content being sent.

## 3. How descriptors are matched

The processing flow can be modeled as follows:

```text
Request body in HTTP test
          |
          v
Read JSON structure
          |
          v
Match FieldDescriptor
          |
          +--> Path is already described
          |
          +--> Extra undocumented field
          |
          +--> Required descriptor but field is absent
          |
          v
Generate request-fields.adoc or report an error
```

With strict `requestFields(...)`:

- Fields present in the payload must be documented or covered by an appropriate descriptor.
- Required descriptors must find a matching field in the sample payload.
- `.optional()` allows a descriptor to be absent from the sample payload.
- `.ignored()` recognizes a field while excluding it as a row from the table.
- New undocumented fields can cause snippet generation to fail.

A descriptor at a parent object or subsection level can be treated as covering its child structure during extra-field checks. Therefore, a passing test does not prove every child field has its own description. If clients need to know `items[].sku`, `items[].quantity`, and other properties, declare them explicitly.

| Concept | Meaning | API |
| --- | --- | --- |
| Path matching | Path points to the exact JSON field | `fieldWithPath(...)` |
| Presence | Can the field be absent? | `.optional()` |
| Visibility | Does the field appear in the table? | `.ignored()` |
| Unspecified fields | Are undeclared fields accepted? | `relaxedRequestFields(...)` |
| Type display | Type shown in the snippet | `.type(JsonFieldType.X)` |
| Business validation | Is the data valid per business rules? | Bean Validation and API tests |

## 4. Common types of mismatches

### 4.1. New field in the payload

Payload:

```json
{
  "customerId": 42,
  "note": "Deliver in the afternoon",
  "discountCode": "WELCOME"
}
```

Descriptors do not yet include `discountCode`:

```java
requestFields(
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("note").description("Delivery note")
)
```

Strict mode can report `discountCode` as undocumented. Decide:

- Add a descriptor if clients need to use the field.
- Use `.ignored()` if the field is known but does not need to be published on this operation.
- Use `relaxedRequestFields(...)` if the contract intentionally allows unlisted extensions.

Do not switch to relaxed mode just to make the test pass. First determine the meaning of the new field and its impact on the contract.

### 4.2. Required descriptor, but payload is missing the field

Sample payload:

```json
{ "customerId": 42 }
```

Descriptor:

```java
fieldWithPath("note")
        .description("Delivery note");
```

If `note` is truly optional, add `.optional()`:

```java
fieldWithPath("note")
        .description("Delivery note")
        .optional();
```

If the contract requires `note`, the fixture must add the field. Do not use `.optional()` to hide a test payload missing required data.

### 4.3. Wrong name or wrong object level

Payload:

```json
{
  "shippingAddress": {
    "city": "Hanoi"
  }
}
```

Wrong path `shipping.address.city`; right path `shippingAddress.city`. Paths must match the exact JSON key names, case sensitivity, and object hierarchy.

### 4.4. Wrong array syntax

Payload:

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ]
}
```

`items.sku` skips the array level; use `items[].sku`. The `[]` notation describes an element at any position. If the array is empty, there is no representative element for child descriptors; create a snippet-generating test with a sample element and a separate empty-array test.

### 4.5. Absent vs. null

JSON without key:

```json
{ "customerId": 42 }
```

JSON with key set to null:

```json
{ "customerId": 42, "note": null }
```

`.optional()` states that the field is allowed to be absent in the sample payload; it is not a nullable flag. If the contract permits String or null, state that clearly and write corresponding tests. An ordinary Java DTO may not distinguish absent from explicit null after binding; if the difference matters, inspect the JSON before binding or use a presence-tracking mechanism.

## 5. MockMvc example detecting contract drift

Assume `POST /api/orders` exists and returns `201 Created` on valid requests; the project already has Spring Boot, JUnit 5, MockMvc, and the `spring-restdocs-mockmvc` dependency.

### 5.1. Descriptors

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_FIELDS = {
        fieldWithPath("customerId")
                .type(JsonFieldType.NUMBER)
                .description("Customer ID"),
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
};
```

### 5.2. Snippet-generating test

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderPayloadContractDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateOrderRequest() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ],
                  "note": "Deliver after 5 PM"
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(ORDER_FIELDS)));
    }
}
```

When the HTTP request and descriptors align, the snippet is generated at `build/generated-snippets/orders-create/request-fields.adoc` along with other snippets depending on configuration.

If `discountCode` is added to the JSON without updating descriptors, strict mode can report an undocumented field. If a new descriptor is added while the fixture lacks the field, use `.optional()` only when the contract permits absence; if the field is required, update the fixture.

### 5.3. Testing variants with and without an optional field

```java
@Test
void documentOrderWithoutOptionalNote() throws Exception {
    String json = """
            {
              "customerId": 42,
              "items": [
                { "sku": "BOOK-001", "quantity": 2 }
              ]
            }
            """;

    mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().isCreated())
            .andDo(document("orders-create-without-note",
                    requestFields(ORDER_FIELDS)));
}
```

Use separate snippet names so the two tests do not overwrite each other's output. Two tests with the same descriptors demonstrate one variant with `note` and one variant with `note` absent.

## 6. Strict, relaxed, ignored, and subsection

### Strict `requestFields(...)`

Use when you want every field in the payload reviewed. Suitable for public APIs whose contracts need review upon changes.

### `relaxedRequestFields(...)`

```java
relaxedRequestFields(
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("items").description("List of items")
)
```

Undeclared fields are allowed to exist. In exchange, the test no longer serves as a guardrail catching every new field.

### `.ignored()`

```java
fieldWithPath("clientTraceId")
        .description("Internal tracing ID")
        .ignored();
```

Known field excluded from display in the table. If it may be absent, add `.optional()`. These two properties do not replace each other.

### `subsectionWithPath(...)`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("shippingAddress")
        .description("Shipping address details");
```

Used to describe an entire object branch as a subsection. If API consumers need to know individual child fields, declare `shippingAddress.street` and `shippingAddress.city` individually or link to a detailed schema.

## 7. Checking types and serialized payloads

`FieldDescriptor` can specify the displayed type:

```java
fieldWithPath("quantity")
        .type(JsonFieldType.NUMBER)
        .description("Order quantity");
```

Common types are `STRING`, `NUMBER`, `BOOLEAN`, `OBJECT`, `ARRAY`, `NULL`, and `VARIES`. `.type(...)` is information for the snippet, not a JSON Schema validator. If a payload sends `"quantity": "2"` as a String while the contract requires Number, validation and API tests are needed to catch it.

Jackson can affect the outgoing JSON:

- `@JsonProperty` changes key names.
- A naming strategy can turn camelCase into snake_case.
- `@JsonInclude` can drop null fields during serialization.
- Default values in a DTO/builder can make the fixture differ from expectations.

On a mismatch, inspect the actual JSON being sent directly before editing descriptors.

## 8. Request preprocessors

Spring REST Docs supports operation preprocessors to normalize requests or responses before writing snippets. Example pretty print:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.andDo(document("orders-create",
        preprocessRequest(prettyPrint()),
        requestFields(ORDER_FIELDS)
));
```

Distinguish the request sent to the endpoint from the preprocessed request written to the snippet. Pretty print primarily formats JSON for readability. If a preprocessor alters the body or strips fields, ensure the snippet still accurately reflects the contract clients use. Do not strip a field from a snippet and assume it was verified just like the original request.

Prefer fake fixtures and never use real secret data. A preprocessor that masks data in snippets does not automatically protect logs or test reports.

## 9. Workflow for investigating mismatch errors

1. Read the test JSON and confirm key names, types, and structure.
2. Read the descriptors and check paths, `[]`, and casing.
3. Classify the error: extra field, missing required field, empty branch, or inconsistent type.
4. Check the contract: required, optional, nullable, or ignored.
5. Fix the fixture, descriptor, or validation to match the contract.
6. Re-run the documentation test and inspect the newly generated snippet.

| Symptom | Cause | Fix |
| --- | --- | --- |
| Undocumented field | JSON has a new field | Add descriptor, intentionally ignore, or use relaxed if contract is open |
| Required field missing | Fixture lacks field or wrong path | Check JSON and `.optional()` per contract |
| Nested path mismatch | Wrong key name or object level | Match the JSON wire format |
| Array path mismatch | Missing `[]` or empty array | Use array path and a fixture with elements |
| Child field has no separate row | Parent object/subsection covers the branch | Add detailed descriptors if needed |
| Wrong displayed type | Inferred from non-representative sample payload | Declare type explicitly and test validation |
| Test payload differs from sent JSON | Jackson config or preprocessor | Inspect request after serialization |
| Stale snippet | Test did not run or stale output | Check tasks and snippet output directory |

## 10. Build and CI

With Gradle and the configured Asciidoctor plugin:

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

Asciidoctor document:

```adoc
= Orders API

== Create order

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]
```

CI flow:

```text
HTTP tests
   |
   v
Spring REST Docs matches payload and descriptors
   |
   v
Generated snippets
   |
   v
Asciidoctor / Markdown export step
   |
   v
Verify and publish
```

If you want to review snippet changes in pull requests, you can archive the output as an artifact or diff against reviewed documentation. Never edit auto-generated snippets by hand to hide a mismatch; fix the fixture or descriptor that serves as the source.

Spring REST Docs typically generates AsciiDoc snippets. If Markdown is needed, configure templates or a conversion step; do not assume `request-fields.md` will exist by default.

## 11. Hands-on exercise

1. Add `discountCode` to the JSON without adding a descriptor yet. Observe strict `requestFields(...)` detecting the new field.
2. Add the descriptor and clearly describe its meaning for clients.
3. Remove `note` from the JSON. Since its descriptor already has `.optional()`, verify the snippet still generates.
4. Change `items[].sku` to `items.sku`, observe the error, then fix it.
5. Rename JSON key `customerId` to `customer_id`. Update the descriptor to match the wire format.
6. Send `quantity` as a String instead of a Number. Add validation and a negative test.
7. Use `prettyPrint()` and compare the snippets before and after.
8. Include the snippet in Asciidoctor and ensure the documentation task depends on tests.

### Self-check questions

- Which data does `requestFields(...)` match descriptors against?
- Why must descriptors follow the JSON wire format instead of Java property names?
- When does a new field cause a strict snippet to fail?
- How do `.optional()`, `.ignored()`, and `relaxedRequestFields(...)` differ?
- Why does a parent object descriptor not guarantee that every child field has its own description?
- Does `.type(JsonFieldType.NUMBER)` replace validation?
- How do preprocessors affect snippets?

**Remember:** `FieldDescriptor` is the descriptive contract that Spring REST Docs uses to match against test payloads. Strict `requestFields(...)` helps catch new fields or descriptors that no longer align. `.optional()`, `.ignored()`, and relaxed mode should only be used in accordance with the contract. Combining representative HTTP fixtures, business validation, and CI builds keeps REST API documentation continuously verifiable.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `fieldWithPath`, relaxed fields, and payload snippets.
- [Spring REST Docs — Operation Preprocessors](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html): normalizing requests/responses before writing snippets.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): descriptor, type, optional, ignored, and attributes.
