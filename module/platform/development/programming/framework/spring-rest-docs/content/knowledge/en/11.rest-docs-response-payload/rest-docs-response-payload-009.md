# Designing descriptions independent of JSON field ordering

## 1. Why should you not depend on key ordering in a JSON object?

In the **Response payload** chapter of the **SPRING_REST_DOCS** module, `responseFields(...)` documents JSON fields via `fieldWithPath(...)`. A common design mistake is assuming keys must appear in the exact order shown in a fixture or in the declaration order of properties in a Java DTO.

A JSON object is an unordered collection of name/value pairs. Member order carries no meaning in the JSON data model. Thus, the following two payloads represent the exact same object:

```json
{
  "id": "ORD-2100",
  "status": "CONFIRMED",
  "totalAmount": 250000
}
```

```json
{
  "totalAmount": 250000,
  "id": "ORD-2100",
  "status": "CONFIRMED"
}
```

When documenting responses with Spring REST Docs, descriptors specify **the path and meaning of a field**, not its byte offset or key order inside the JSON object. If a contract only changes key ordering while keeping names, structure, and values per path intact, that is not a schema change.

This lesson focuses on:

- Distinguishing object key ordering from array element ordering.
- Writing descriptors by stable path without relying on field position in JSON.
- Organizing fixtures and DTOs so tests do not depend on insertion or serialization order.
- Distinguishing descriptor declaration order from response key order.
- Verifying responses by path/value instead of raw JSON string comparisons.
- Keeping Spring REST Docs snippets stable in build and CI.

## 2. Three kinds of ordering to distinguish

| Kind of order | Meaningful in JSON contract? | Example | How to handle |
| --- | --- | --- | --- |
| Key order in an object | No | Whether `id` appears before or after `status` | Do not write tests dependent on key order |
| Element order in an array | Potentially yes | Whether a line item is at index 0 or 1 | Test ordering if business rules define it |
| `FieldDescriptor` declaration order | Affects snippet organization/presentation | `id` declared before `status` | Order descriptors intentionally for readability |

Do not assume that because JSON objects have unordered keys, every JSON structure is unordered. Arrays are ordered sequences of positioned elements; for endpoints returning lists sorted by creation date, priority, or display order, clients may rely on that order.

### 2.1. A JSON object is not an indexed list of fields

Example object:

```json
{
  "customer": {
    "id": "CUS-18",
    "displayName": "Customer 18"
  },
  "orderId": "ORD-2100"
}
```

The paths are still `orderId`, `customer.id`, and `customer.displayName`. There are no paths like `field[0]` or `field[1]` for object key order.

For `responseFields`, declaring:

```java
responseFields(
    fieldWithPath("orderId").description("Order ID"),
    fieldWithPath("customer").description("Customer"),
    fieldWithPath("customer.id").description("Customer ID"),
    fieldWithPath("customer.displayName")
        .description("Customer display name")
)
```

works across payloads with different key orders, as long as paths and data structures remain valid.

### 2.2. JSON arrays are ordered

Array payload:

```json
{
  "items": [
    {"sku": "BK-01", "quantity": 2},
    {"sku": "BK-02", "quantity": 1}
  ]
}
```

`items[0]` and `items[1]` are two distinct positions. The generalized descriptor:

```java
responseFields(
    fieldWithPath("items").description("List of line items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Quantity")
)
```

describes the field structure of repeating elements, without asserting that BK-01 must come first. If the API guarantees sorting, write separate assertions for the order:

```java
.andExpect(jsonPath("$.items[0].sku").value("BK-01"))
.andExpect(jsonPath("$.items[1].sku").value("BK-02"))
```

If the API does not guarantee order, avoid position-specific assertions. You can check the presence of values or the set of product SKUs instead of enforcing an arbitrary order.

## 3. Write descriptors by path name, not by key position

A descriptor should identify a path directly:

```java
fieldWithPath("orderId")
    .description("Order identifier");

fieldWithPath("status")
    .description("Order processing status");

fieldWithPath("totalAmount")
    .description("Total amount in VND");
```

There is no "first field" or "second field" API in `fieldWithPath` that depends on object key positions. Avoid writing custom logic that picks from a list of field names by response position to build descriptors.

With nested objects, paths still reflect field names:

```json
{
  "pricing": {
    "currency": "VND",
    "payableAmount": 320000,
    "discountAmount": 50000
  }
}
```

```java
responseFields(
    fieldWithPath("pricing").description("Pricing details"),
    fieldWithPath("pricing.currency").description("Currency code"),
    fieldWithPath("pricing.payableAmount")
        .description("Total amount payable in VND"),
    fieldWithPath("pricing.discountAmount")
        .description("Discount amount in VND")
)
```

Whether the serializer writes `currency` before `payableAmount` or vice versa, the paths stay the same. If the JSON name changes from `payableAmount` to `amountDue`, that is a contract change; update descriptors, assertions, and documentation, as it is not an ordering issue.

## 4. Descriptor order and how documentation tables are organized

The declaration order of descriptors expresses the test author's intent. A logically grouped list makes snippets easier to read and review:

```java
responseFields(
    // Resource identification
    fieldWithPath("orderId").description("Order ID"),
    fieldWithPath("status").description("Order status"),

    // Customer
    fieldWithPath("customer").description("Customer details"),
    fieldWithPath("customer.id").description("Customer ID"),
    fieldWithPath("customer.displayName")
        .description("Display name"),

    // Totals
    fieldWithPath("pricing").description("Pricing details"),
    fieldWithPath("pricing.subtotalAmount")
        .description("Merchandise total before discounts/fees, VND"),
    fieldWithPath("pricing.discountAmount")
        .description("Discount amount, VND"),
    fieldWithPath("pricing.payableAmount")
        .description("Amount payable, VND")
)
```

Do not try to reorder descriptors to mimic serializer key order just to make two lists look alike. Group by business meaning or object structure; when fields are added to the schema, reviewers can easily see where they belong.

If you want snippet tables to have a consistent display order, standardize descriptor declaration order in tests and project templates. The goal is documentation consistency. Display order must never be interpreted as a wire-level constraint on JSON objects.

## 5. MockMvc example: changing key order while keeping the contract intact

The following example uses JUnit Jupiter, MockMvc, Jackson, and `spring-restdocs-mockmvc`. The controller returns the same data while constructing maps in two different key-insertion orders based on a query parameter. Both tests use the same descriptors.

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ResponseFieldOrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    private static org.springframework.restdocs.payload.FieldDescriptor[]
    orderDescriptors() {
        return new org.springframework.restdocs.payload.FieldDescriptor[] {
            fieldWithPath("orderId").description("Order ID"),
            fieldWithPath("status").description("Order status"),
            fieldWithPath("totalAmount")
                .description("Total amount in VND")
        };
    }

    @Test
    void documentOrderWithFirstKeyOrder() throws Exception {
        mockMvc.perform(get("/api/order").param("layout", "first")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-2100"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.totalAmount").value(250000))
                .andDo(document("order-fields-layout-first",
                        responseFields(orderDescriptors())));
    }

    @Test
    void documentOrderWithSecondKeyOrder() throws Exception {
        mockMvc.perform(get("/api/order").param("layout", "second")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-2100"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.totalAmount").value(250000))
                .andDo(document("order-fields-layout-second",
                        responseFields(orderDescriptors())));
    }

    @RestController
    static class OrderController {

        @GetMapping(value = "/api/order",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(
                @RequestParam(name = "layout", defaultValue = "first")
                String layout) {

            Map<String, Object> body = new LinkedHashMap<>();

            if ("second".equals(layout)) {
                body.put("totalAmount", 250000);
                body.put("status", "CONFIRMED");
                body.put("orderId", "ORD-2100");
            } else {
                body.put("orderId", "ORD-2100");
                body.put("status", "CONFIRMED");
                body.put("totalAmount", 250000);
            }
            return body;
        }
    }
}
```

Key observations:

- `LinkedHashMap` preserves insertion order during serialization, allowing the fixture to produce two different key arrangements for demonstration.
- Both tests share `orderDescriptors()`; they assert via JSON paths and values rather than comparing raw JSON strings.
- Both responses have identical paths and data. Changing key order requires no descriptor changes.
- Separate snippet identifiers let reviewers inspect each HTTP exchange. In practice, if there is no reason to document two variants that differ only in key order, one representative fixture suffices; do not add redundant tests solely to exercise serializer ordering.

This example illustrates independence from object key ordering. It does not recommend adding a `layout` query parameter to a real API just to alter serialization order.

## 6. Why should you not compare raw JSON strings?

An assertion like:

```java
.andExpect(content().string(
    "{\"orderId\":\"ORD-2100\",\"status\":\"CONFIRMED\","
  + "\"totalAmount\":250000}"))
```

depends on key ordering and string formatting. It can fail even when the response carries the exact same valid JSON object.

Instead, verify properties using JSON paths:

```java
.andExpect(jsonPath("$.orderId").value("ORD-2100"))
.andExpect(jsonPath("$.status").value("CONFIRMED"))
.andExpect(jsonPath("$.totalAmount").value(250000))
```

Or parse into a JSON tree when comparing multiple values:

```java
JsonNode body = objectMapper.readTree(
        result.getResponse().getContentAsString());

assertEquals("ORD-2100", body.path("orderId").asText());
assertEquals("CONFIRMED", body.path("status").asText());
assertEquals(250000, body.path("totalAmount").asInt());
```

Structural comparison of `JsonNode` objects is normally independent of member order; however, when arrays are nested inside, element order is preserved and can affect equality results.

If you need to verify a set of required fields, check each path or use a schema validator. Do not write tests that only count keys when clients also depend on accurate types, values, and nested structures.

## 7. Java DTOs and serializers

Key order during serialization can depend on:

- The type of object/map returned and its iteration order.
- JSON library settings and custom serializers.
- Annotations or naming strategies affecting field names.
- Property sorting settings if the application explicitly enables them.
- Library upgrades or DTO structural refactoring.

Do not treat the current key order in Jackson output as an API guarantee unless the system truly has a special formatting requirement outside the JSON data model. If a client relies on key order to parse JSON, that client is built on an assumption incompatible with the format.

A typical DTO:

```java
record OrderResponse(
    String orderId,
    String status,
    long totalAmount
) {}
```

produces a JSON object with corresponding fields. To test the contract, use paths matching serialized JSON names rather than record parameter positions. If the application uses `@JsonProperty` to rename `totalAmount` to `amountDue`, descriptors must use the final JSON key.

Example:

```java
@JsonProperty("amountDue")
long totalAmount
```

Here the path to document is `amountDue`. This is a field-name change, completely different from whether `totalAmount` appears before or after `status`.

## 8. Reusable descriptors and stability

If multiple endpoints share the same response contract, you can extract a reusable descriptor set:

```java
static FieldDescriptor[] basicOrderFields() {
    return new FieldDescriptor[] {
        fieldWithPath("orderId")
            .description("Order ID"),
        fieldWithPath("status")
            .description("Order status"),
        fieldWithPath("totalAmount")
            .description("Total amount in VND")
    };
}
```

Then reuse it across multiple tests:

```java
responseFields(basicOrderFields())
```

The benefit is consistent description ordering, and when a field's meaning changes, you can update it in one place. However, reuse only when **both schema and business meaning are genuinely identical**. A field named `status` in an order response and in a payment response may follow different lifecycles; do not share descriptors merely because paths or names look alike.

When an endpoint adds its own field, you can combine shared descriptors with extra ones:

```java
responseFields(basicOrderFields()).and(
    fieldWithPath("paymentStatus")
        .description("Payment status")
)
```

This example illustrates the composition mechanism. In strict mode, every actual field in the response must still be handled; shared descriptors do not exempt you from full payload coverage.

## 9. Array element ordering is a different story

Given the response:

```json
{
  "items": [
    {"sku": "BK-01", "position": 1},
    {"sku": "BK-02", "position": 2}
  ]
}
```

Swapping the two elements changes the array:

```json
{
  "items": [
    {"sku": "BK-02", "position": 2},
    {"sku": "BK-01", "position": 1}
  ]
}
```

This is not just object presentation—it is a change in array element order. If the API guarantees sorting by `position`, test it:

```java
.andExpect(jsonPath("$.items[0].position").value(1))
.andExpect(jsonPath("$.items[1].position").value(2))
```

If the API does not guarantee order, avoid fixed-index assertions. You can check the set of values by parsing the array and comparing after sorting in the test, or verify elements are present without requiring specific positions.

With `responseFields`, the descriptor `items[].sku` describes the same field across elements. It does not enforce array sort order. Ordering guarantees require separate explanation and assertions.

## 10. Stable fixtures and snippets in CI

To avoid noise caused by key ordering:

1. Verify contracts by path and value, avoiding rigid JSON string comparisons unless specifically justified.
2. Use clearly structured fixtures; if using an insertion-ordered map, use it only to keep test data readable or test a specific serializer scenario.
3. Keep descriptor lists grouped by business domain and consistent across endpoints sharing the same contract.
4. Do not treat key-order changes as breaking changes.
5. Test array ordering separately if the API defines sorting rules.
6. Run REST Docs tests before Asciidoctor; review snippet diffs alongside code and descriptor changes.

Example Gradle snippet layout:

```text
build/generated-snippets/
├── order-fields-layout-first/
│   ├── http-response.adoc
│   └── response-fields.adoc
└── order-fields-layout-second/
    ├── http-response.adoc
    └── response-fields.adoc
```

With Maven, the default directory is usually `target/generated-snippets`. Output location is customizable.

Asciidoctor can include the response and field table:

```adoc
= Order API
:snippets: build/generated-snippets

== Order response

=== HTTP response
include::{snippets}/order-fields-layout-first/http-response.adoc[]

=== Response fields
include::{snippets}/order-fields-layout-first/response-fields.adoc[]
```

In final documentation, there is no need to keep two examples differing only in key order if that adds no value for readers; keep one representative snippet. Having two tests in this lesson only demonstrates that descriptors resolve by path name rather than key position.

Build/CI should run snippet-generating HTTP tests before compiling Asciidoctor. If a path is renamed or a field disappears, strict descriptors and assertions catch it; if only object key order flips, path-based tests continue to pass.

## 11. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test fails after serializer reorders keys | Assertion compares raw JSON string | Use JSON paths or parse JSON objects |
| Descriptors written to follow Java field order | Confused DTO parameter order with JSON paths | Use paths matching serialized JSON names |
| Array order changes undetected | Missing order assertion despite sorting contract | Verify indices/order or business sorting rules |
| Test enforces array order despite no contract guarantee | Relied on accidental fixture order | Assert set membership instead of positions |
| Documentation table row order changes unexpectedly | Descriptors reordered or template changed | Standardize descriptor declaration order and templates |
| Renamed field mistaken for key-order change | Confused key order with path/name | Update contract, descriptors, and versioning if needed |
| Strict test misses new field | Used overly broad relaxed mode | Use strict mode and handle new fields intentionally |
| Snippets differ solely due to fixture data | Unstable fixture | Normalize fixtures and vary only what is under test |

## 12. Practice exercise

Using an order response with `orderId`, `status`, and `totalAmount`:

1. Create two `LinkedHashMap` instances with different key insertion orders but identical values. Return both from a test endpoint and verify the same set of JSON path assertions passes for both.
2. Write an assertion comparing raw JSON strings and observe it fail when key order is reversed despite the object being unchanged. Replace it with path-based assertions.
3. Declare `FieldDescriptor` entries in a shared method used by both tests; keep descriptor order stable.
4. Rename `totalAmount` to `amountDue` via serializer/DTO. Observe that this is an actual path change and update the descriptor.
5. Create an `items` array with two elements. Reorder the elements; write assertions verifying order if required by the contract, or checking set membership if not.
6. Create a nested `pricing` object with monetary fields in different key orders. Verify that `pricing.*` descriptors continue to work.
7. Generate snippets and inspect which changes affect the field table and which only alter response key order.

**Completion criteria:** you can distinguish object key ordering from array ordering; understand that descriptors operate by path; avoid raw JSON string assertions; organize readable, stable descriptors; and test only the ordering guarantees actually defined by the API contract.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): documenting payloads by field path and generating response fields snippets.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): definitions of JSON objects, arrays, and ordering semantics.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): testing responses with MockMvc and path-based assertions.
