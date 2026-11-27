# Documenting JSON fields in responses with Spring REST Docs

## 1. Why document individual JSON fields?

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. The **Response payload** section focuses on the data the server actually returns. When a response has a JSON structure, API integrators need to know exactly which fields exist, their data types, business meaning, which fields may be absent, and the structure of nested objects/arrays.

Spring REST Docs provides `responseFields(...)` and `fieldWithPath(...)` to bind those descriptions to a tested HTTP exchange:

```java
responseFields(
    fieldWithPath("orderId").description("Order ID"),
    fieldWithPath("customer.email").description("Customer email"),
    fieldWithPath("items[].sku").description("SKU of each line item")
)
```

Each declaration is a **`FieldDescriptor`**. In the default configuration, Spring REST Docs validates descriptors against the actual JSON; undocumented fields or missing required fields can cause the documentation generation test to fail. When the test passes, the `response-fields.adoc` snippet can be included in Asciidoctor documentation and integrated into the build/CI pipeline.

Field descriptions are part of the API contract. However, they do not automatically verify all business rules, such as whether `totalAmount` equals the sum of line items or whether `status` only takes allowed values. Such conditions require separate assertions or checks.

## 2. A realistic sample response

Consider the endpoint `GET /api/orders/1024` returning HTTP `200 OK` and the following payload:

```json
{
  "orderId": "ORD-1024",
  "status": "CONFIRMED",
  "customer": {
    "id": 15,
    "email": "lan@example.test"
  },
  "items": [
    {
      "sku": "BK-1",
      "quantity": 2,
      "unitPrice": 125000
    },
    {
      "sku": "BK-2",
      "quantity": 1,
      "unitPrice": 90000
    }
  ],
  "totalAmount": 340000,
  "coupon": null,
  "labels": ["new", "online"],
  "metadata": {
    "trace.id": "req-1024"
  },
  "hasMore": false
}
```

The payload contains top-level fields, nested objects, an array of objects, an array of strings, a `null` value, a boolean, and even a property name containing a dot. Each form requires choosing the appropriate path so Spring REST Docs recognizes it accurately.

## 3. Path syntax of `fieldWithPath`

`fieldWithPath("...")` uses **paths based on the JSON structure**, not Java getter names, database column names, or full JSONPath expressions like `$.customer.id`.

| JSON to document | Spring REST Docs path | Explanation |
| --- | --- | --- |
| `"orderId": "ORD-1024"` | `orderId` | Top-level field |
| `"customer": {...}` | `customer` | Entire customer object |
| `"customer": {"id": 15}` | `customer.id` | Field inside a nested object |
| `"items": [...]` | `items` | Entire array of items |
| `"items": [{"sku": "BK-1"}]` | `items[].sku` | `sku` of object elements within the array |
| `"labels": ["new", "online"]` | `labels` | Array of strings, typically documented as an `ARRAY` field |
| `"metadata": {"trace.id": "..."}` | `metadata['trace.id']` | JSON key containing a dot, requiring brackets and quotes |
| `"hasMore": false` | `hasMore` | Top-level boolean field |

### 3.1. Dots and brackets

For ordinary property names, use dot notation:

```java
fieldWithPath("customer.email")
    .description("Customer contact email");
```

Spring REST Docs also supports bracket notation, which is useful when key names contain dots, spaces, or special characters. For example, the following two structures are **different**:

```json
{
  "customer": {
    "email": "lan@example.test"
  },
  "customer.email": "legacy@example.test"
}
```

```java
fieldWithPath("customer.email")
    .description("Email inside the customer object");

fieldWithPath("['customer.email']")
    .description("Top-level field whose name contains a dot");
```

A dot inside a key name wrapped in `['...']` does not navigate down into a child object. Similarly, `metadata['trace.id']` points to **a single key** named `trace.id` inside the `metadata` object.

### 3.2. Object arrays and the `[]` notation

Given:

```json
{
  "items": [
    {"sku": "BK-1", "quantity": 2},
    {"sku": "BK-2", "quantity": 1}
  ]
}
```

You can document the array and each element's properties:

```java
fieldWithPath("items").description("Line items in the order");

fieldWithPath("items[].sku")
    .description("Product SKU of each line item");

fieldWithPath("items[].quantity")
    .description("Quantity of products in each line item");
```

The `[]` notation represents array elements, suitable for responses with a variable number of items. Avoid hardcoding only `items[0].sku` if the API contract applies to every line item; paths with a specific index are only appropriate when there is a specific reason to document a fixed position.

**Empty arrays require special attention.** If the sample response contains `"items": []`, there are no elements to match `items[].sku`. With required descriptors, the documentation test may fail. Choose a fixture with representative elements to document the structure; test empty arrays in a separate test.

### 3.3. Responses whose root is an array

Not every API returns an object at the root level. Given the response:

```json
[
  {"id": 1, "name": "Pen"},
  {"id": 2, "name": "Notebook"}
]
```

You can document the root array and its element properties:

```java
responseFields(
    fieldWithPath("[]").description("List of products"),
    fieldWithPath("[].id").description("Product ID"),
    fieldWithPath("[].name").description("Product name")
)
```

When documenting a root array, paths do not have a prefix such as `data` or `items` because those prefixes do not exist in the actual JSON.

## 4. Complete MockMvc test

The example below uses JUnit Jupiter, MockMvc, and `spring-restdocs-mockmvc`. The data is constructed directly inside the test controller to clarify the relationship between the response JSON and the descriptor list. Jackson must be on the classpath so Spring MVC serializes `Map` to JSON.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderJsonFieldsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOrderResponseFields() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 1024)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-1024"))
                .andExpect(jsonPath("$.items[0].quantity").value(2))
                .andExpect(jsonPath("$.totalAmount").value(340000))
                .andDo(document("orders-get-json-fields",
                        responseFields(
                                fieldWithPath("orderId")
                                        .description("Unique identifier of the order"),
                                fieldWithPath("status")
                                        .description("Order processing status"),
                                fieldWithPath("customer")
                                        .description("Customer information"),
                                fieldWithPath("customer.id")
                                        .description("Customer ID"),
                                fieldWithPath("customer.email")
                                        .description("Customer contact email"),
                                fieldWithPath("items")
                                        .description("List of line items"),
                                fieldWithPath("items[].sku")
                                        .description("Product SKU of the line item"),
                                fieldWithPath("items[].quantity")
                                        .description("Product quantity"),
                                fieldWithPath("items[].unitPrice")
                                        .description("Unit price in VND"),
                                fieldWithPath("totalAmount")
                                        .description("Total order amount in VND"),
                                fieldWithPath("coupon")
                                        .type(JsonFieldType.STRING)
                                        .optional()
                                        .description("Promo code, may be absent or null"),
                                fieldWithPath("labels")
                                        .description("Labels for classification"),
                                fieldWithPath("metadata")
                                        .description("Supplementary response metadata"),
                                fieldWithPath("metadata['trace.id']")
                                        .description("Request trace lookup ID"),
                                fieldWithPath("hasMore")
                                        .description("Whether more paginated data is available")
                        )
                ));
    }

    @RestController
    static class OrderController {
        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(@PathVariable long id) {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("orderId", "ORD-" + id);
            payload.put("status", "CONFIRMED");
            payload.put("customer", Map.of(
                    "id", 15,
                    "email", "lan@example.test"));
            payload.put("items", List.of(
                    Map.of("sku", "BK-1", "quantity", 2,
                           "unitPrice", 125000),
                    Map.of("sku", "BK-2", "quantity", 1,
                           "unitPrice", 90000)));
            payload.put("totalAmount", 340000);
            payload.put("coupon", null);
            payload.put("labels", List.of("new", "online"));
            payload.put("metadata", Map.of("trace.id", "req-1024"));
            payload.put("hasMore", false);
            return payload;
        }
    }
}
```

Here there are two intentionally different types of paths:

- In the assertion `jsonPath("$.items[0].quantity")`, JSONPath syntax starts from the root `$` and accesses the first element to verify data.
- In the documentation `fieldWithPath("items[].quantity")`, Spring REST Docs describes the `quantity` field of array elements without tying the contract to the first element.

The `coupon` value is `null` in the fixture, but the contract expects it to be a string promo code when present. Therefore, the descriptor uses `type(JsonFieldType.STRING)` so the documentation displays the expected type, and `optional()` when the API allows omitting the field altogether in another response. These two traits serve distinct purposes.

In a Spring Boot application, you can replace the test controller with a real controller using `@WebMvcTest` or `@SpringBootTest` along with the appropriate REST Docs configuration. Descriptors can still be used with WebTestClient/REST Assured; only the test setup and how the documentation action is attached change.

## 5. Understanding and specifying JSON field types

Spring REST Docs usually infers field types from the recorded JSON. The table below lists the types in `JsonFieldType`:

| Type | Example | When to use |
| --- | --- | --- |
| `STRING` | `"ORD-1024"` | Character strings, identifiers, timestamps represented as strings |
| `NUMBER` | `125000`, `2.5` | JSON numbers, including integers and decimals |
| `BOOLEAN` | `true`, `false` | Boolean values |
| `OBJECT` | `{"id": 15}` | JSON objects |
| `ARRAY` | `["new", "online"]` | JSON arrays |
| `NULL` | `null` | Actual null values |
| `VARIES` | A field with multiple types in sample data | When the field type varies across processed elements/contexts |

For example, a `coupon` field that only returns `null` in the fixture is usually insufficient to infer that its business contract is a string; declaring it explicitly keeps the generated table from being misleading:

```java
fieldWithPath("coupon")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Promo code, if applied");
```

Beyond the JSON type, descriptions can clarify units and formatting. For instance, `totalAmount` is a `NUMBER`, yet readers still need to know whether the amount is in VND or the smallest currency unit; `createdAt` is a `STRING`, yet readers need to know whether it uses ISO 8601 and which time zone; `status` is a `STRING`, yet the valid values must be published. Do not leave such semantics to be guessed from the data type alone.

**Distinguish between two verification layers:** `type(...)` controls the type information used in the generated documentation; when you need to guarantee that data conforms to a required type or format, write corresponding assertions or schema validation. Do not treat the field table as proof of all formatting and business rules.

## 6. Required, optional, ignored, and `null` fields

By default, a field descriptor represents a field that must be found in the sample response. Useful modifiers include:

```java
fieldWithPath("invoiceNumber")
    .optional()
    .description("Invoice number, only present after issuance");

fieldWithPath("debug.traceId")
    .optional()
    .ignored();
```

| Scenario | Declaration | Meaning |
| --- | --- | --- |
| Field must appear | `fieldWithPath("orderId")` | Describes a required field in the documentation fixture |
| Field may not appear | `fieldWithPath("coupon").optional()` | Allows the path to be absent |
| Field appears but should not show in table | `fieldWithPath("debug.traceId").ignored()` | Marks as handled without adding it to the field table |
| Field is only `null` in fixture, expected to have another type | `.type(JsonFieldType.STRING)` | Specifies the expected type to display |
| Child fields of an optional object | Document child paths with an appropriate strategy | Avoids requiring child fields when the entire parent object may be absent |

Distinguish between three payloads:

```json
{"coupon": "SAVE10"}
```

```json
{"coupon": null}
```

```json
{}
```

The first case has a string, the second case **has the field with a `null` value**, and the last case **does not have the field**. `optional()` addresses the possibility that the field may be missing; it does not replace documenting the semantics of `null` or validating allowed values.

When a parent object may be absent (for example, `shippingAddress` is only present for delivery orders), design the sample response and child descriptors consistently. If you need to document the entire address structure in depth, use a fixture containing `shippingAddress` and verify the required child fields. If the documentation only needs to describe the address branch at a high level, see how `subsectionWithPath` is used below.

## 7. Documenting each field or just a whole branch?

There are three common options:

**Document in detail** when API consumers need the internal structure:

```java
responseFields(
    fieldWithPath("customer").description("Customer"),
    fieldWithPath("customer.id").description("Customer ID"),
    fieldWithPath("customer.email").description("Contact email")
)
```

**Document a subsection** when you want to treat an entire branch as a single documentation entry:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("orderId").description("Order ID"),
    subsectionWithPath("customer")
        .description("Customer details, documented in a separate guide")
)
```

`subsectionWithPath("customer")` covers the `customer` branch and its child fields during documentation validation. In return, this snippet does not list `customer.id` and `customer.email` individually.

**Document only a subset** when there is a valid reason to accept other undocumented fields:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
    fieldWithPath("orderId").description("Order ID"),
    fieldWithPath("status").description("Order status")
)
```

`relaxedResponseFields` does not fail simply because the response contains fields outside the list; declared fields must still be found unless marked `optional()`. This choice involves a trade-off: new fields may appear without the documentation test detecting them. For public APIs where contract changes must be tracked, prefer `responseFields` in default mode and explicitly declare any branches to be ignored.

## 8. Designing field descriptions useful to integrators

A good descriptor answers **what the field is used for**, rather than merely translating the variable name.

| Path | Too generic description | More useful description |
| --- | --- | --- |
| `orderId` | ID | Unique identifier used to look up the order |
| `status` | Status | Processing status; for example `PENDING`, `CONFIRMED`, `CANCELLED` if supported by the API |
| `items[].quantity` | Quantity | Number of units ordered in a line item; must be greater than 0 if enforced by the API |
| `items[].unitPrice` | Price | Unit price of one product unit, in VND |
| `totalAmount` | Total | Total amount payable in VND, according to the service's calculation rules |
| `coupon` | Coupon | Applied promo code; absent or `null` when no promotion is applied |

Enumerated values, currency units, rounding rules, sensitivity levels, and the meaning of `null` values must be confirmed against the actual API contract before publication. The examples here only illustrate writing style and do not establish business commitments for a live system.

A self-review checklist when writing descriptors:

1. Paths match the serialized JSON, including key names produced by `@JsonProperty` or naming strategies.
2. For arrays of objects, paths place `[]` in the exact right position.
3. Keys containing dots are written in bracket notation.
4. Data types, formats, units, and potentially missing values are clearly described.
5. Internal or sensitive data is not inadvertently exposed in the **sample response** and published documentation.
6. Descriptions do not depend on internal implementation details that API integrators do not need to know.

## 9. Generating field tables and including them in Asciidoctor

With the identifier `orders-get-json-fields` in the `document(...)` call, a standard build generates:

```text
build/generated-snippets/
└── orders-get-json-fields/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

These are the typical files relevant to the example; the actual list depends on snippet configuration. With Maven, the default directory is usually `target/generated-snippets`; the path can also be reconfigured.

The table in `response-fields.adoc` typically shows three main columns: **Path**, **Type**, and **Description**. Each row comes from the descriptors and the tested data. In an Asciidoctor document:

```adoc
= Order API
:snippets: build/generated-snippets

== View order

=== HTTP response
include::{snippets}/orders-get-json-fields/http-response.adoc[]

=== JSON fields
include::{snippets}/orders-get-json-fields/response-fields.adoc[]
```

Make sure the test task generating snippets finishes before the Asciidoctor compilation task. In CI, a test failure caused by a mismatch between the response and descriptors should fail the pipeline to prevent publishing documentation that does not reflect the current contract. If the project wants to present final documentation in Markdown, an appropriate conversion pipeline or template is required; the default `response-fields.adoc` snippet remains Asciidoctor.

## 10. Common errors when documenting JSON

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Reports undocumented response fields | New key added, missing descriptor for child field, or wrong path used | Check the actual JSON and add a descriptor with the correct path; consider `subsectionWithPath` when appropriate |
| Reports declared field did not appear | Wrong path, renamed key, field excluded from JSON, or empty array | Inspect the serialized payload; fix the path or use `optional()` if omission is genuinely allowed |
| `items.sku` does not match an object array | Missing array notation | Use `items[].sku` |
| `metadata.trace.id` does not match key `trace.id` | Dot inside the **key name** is interpreted as a nested level | Use `metadata['trace.id']` |
| Table shows `NULL` type even though contract specifies string | Fixture only contains `null` | Consider `.type(JsonFieldType.STRING)` and document `null` semantics |
| Field description lacks unit or format | Only repeated the property name | Add unit, valid values, time format, and business meaning |
| `response-fields.adoc` not found | Test has not run, `document` was not called, or output location differs from expected | Check test status and generated snippets directory configuration |
| Stale documentation content after DTO change | Documentation step runs before tests or lacks task dependency | Configure the build to generate snippets before compiling documentation |

## 11. Practice exercise

Starting from the order response in section 2, perform each change:

1. Add `"createdAt": "2026-11-17T02:00:00Z"` to the response. Re-run the test in default mode, observe the missing descriptor error; add a description specifying the time format and time zone.
2. Change `metadata` from `{"trace.id": "..."}` to `{"trace": {"id": "..."}}`. Update the corresponding path from `metadata['trace.id']` to `metadata.trace.id` and explain why the two paths are not equivalent.
3. Try `"items": []`. Observe the difference between documenting the `items` array and the child descriptors `items[].sku`; separate the fixture used for generating structural documentation from the empty-array test case.
4. Return a root array instead of an object and write `responseFields(...)` using `[]` along with `[].id`, `[].name`.
5. Add an optional `deliveryNote` field. Test once with the field present and once with it absent, and note when `optional()` should be used.
6. Include `response-fields.adoc` in an Asciidoctor document and verify the table updates after modifying the response.

**Expected outcome:** you can read any JSON response, determine the right path for scalar fields, objects, arrays, root arrays, and special keys; write descriptors with accurate types and meanings; distinguish missing fields from `null`; and maintain response tables generated from HTTP tests within the build/CI pipeline.
