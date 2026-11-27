# Ensuring every field appearing in the payload is handled

## 1. Why must the entire response be controlled?

In the **SPRING_REST_DOCS** module, Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Payloads can change when the server adds fields, renames properties, expands objects, or serializes extra metadata. If tests only document a few key fields, unexpected changes can slip into the API without review.

`responseFields(...)` in default (strict) mode validates the actual payload in the test against the list of `FieldDescriptor` instances. Every field present requires an explicit decision: document it for clients, intentionally ignore it, or cover it with a subsection. Conversely, required descriptors must match a path; fields allowed to be absent must be marked `optional()`.

The goal is to ensure no new field silently appears without being reviewed.

## 2. Strict mechanism of `responseFields`

Example payload:

```json
{
  "id": "ORD-1200",
  "status": "CONFIRMED",
  "customer": {
    "id": "CUS-17",
    "displayName": "Customer 17"
  },
  "items": [
    {"sku": "BK-01", "quantity": 2}
  ],
  "totalAmount": 250000,
  "internalTraceId": "trace-1200"
}
```

A strict descriptor set handles every field as follows:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    fieldWithPath("customer").description("Customer details"),
    fieldWithPath("customer.id").description("Customer ID"),
    fieldWithPath("customer.displayName")
        .description("Customer display name"),
    fieldWithPath("items").description("Line items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Quantity"),
    fieldWithPath("totalAmount").description("Total amount in VND"),
    fieldWithPath("internalTraceId").ignored()
)
```

| Field | Decision | Reason |
| --- | --- | --- |
| id, status | Document | Public fields clients need to understand |
| customer, customer.id, customer.displayName | Document | Customer information structure |
| items, items[].sku, items[].quantity | Document | Array and per-element data |
| totalAmount | Document | Total amount and unit |
| internalTraceId | Ignore | Operational metadata not needed in public table |

In strict mode, a field appearing in the payload that has not been handled by a descriptor causes snippet generation to fail. A required descriptor whose path does not appear can also fail the test. This two-way check detects both added fields and removed fields.

Strict mode only validates the specific payload tested. It does not automatically prove every business rule or every production response variant; separate fixtures and assertions are needed for those branches.

## 3. Making a decision for each field

| Decision | Declaration | When to use |
| --- | --- | --- |
| Publish to clients | `fieldWithPath(...).description(...)` | Field belongs to the contract clients need to understand |
| Allow absence | `.optional()`, add `.type(...)` when needed | Field may legitimately not appear |
| Present but not published | `.ignored()` | Known field excluded from the table |
| Cover an entire branch | `subsectionWithPath(...)` | Branch details are documented elsewhere |
| Allow unlisted fields | `relaxedResponseFields(...)` | Intentionally documenting only part of the payload |

### 3.1. Public fields

```java
fieldWithPath("status")
    .description("Order processing status");
```

Descriptions should explain meaning, units, format, valid values, or usage as needed.

### 3.2. Internal fields

```java
fieldWithPath("internalTraceId").ignored()
```

This descriptor records that the field is intentionally handled without appearing in the table. Ignoring does not strip the field from the HTTP response or mask data. If a field must not be sent to clients, update the DTO/serialization and write tests prohibiting its presence.

### 3.3. Fields allowed to be absent

```java
fieldWithPath("deliveryNote")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Delivery note, may be absent");
```

`optional()` relaxes the presence requirement in the sample payload. If the field is absent in the fixture, REST Docs cannot infer its type from data; declare `.type(...)` when needed. Optional does not automatically specify whether a JSON `null` value is permitted.

### 3.4. Subsection

```java
subsectionWithPath("customer")
    .description("Customer details; see Customer response documentation");
```

A subsection accounts for an object/array branch and its descendants as a single unit. Use it when child fields have dedicated documentation. If clients need the details of `customer.id` and `customer.displayName` right here, declare each child field individually.

## 4. Detecting new fields and missing fields

### 4.1. New field

Initial payload:

```json
{"id": "ORD-1200", "status": "CONFIRMED"}
```

Server adds `sourceChannel`:

```json
{
  "id": "ORD-1200",
  "status": "CONFIRMED",
  "sourceChannel": "MOBILE"
}
```

If strict descriptors still only list `id` and `status`, snippet generation detects that `sourceChannel` is unhandled and fails. The team should review: add a description if it is a public field; ignore it if it is valid unpublished metadata; or fix the DTO if the field should not be in the response.

Do not switch to relaxed mode just to silence the error before understanding why the new field appeared.

### 4.2. Missing required field

Descriptor:

```java
fieldWithPath("customer.email")
    .description("Contact email");
```

Fixture:

```json
{
  "customer": {
    "id": "CUS-17",
    "displayName": "Customer 17"
  }
}
```

The `customer.email` path does not exist. If email is required, the implementation or fixture does not match the contract. If email is allowed to be absent, document it clearly:

```java
fieldWithPath("customer.email")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Customer email, may not be provided");
```

Do not mark every descriptor optional just to make tests pass, as doing so loses the ability to catch missing required fields.

## 5. Nested objects, arrays, and repeating fields

Nested object:

```json
{
  "customer": {
    "id": "CUS-17",
    "profile": {
      "displayName": "Customer 17",
      "locale": "vi-VN"
    }
  }
}
```

Paths can be `customer`, `customer.id`, `customer.profile.displayName`, and `customer.profile.locale`. If the profile branch has separate documentation, use `subsectionWithPath("customer.profile")`.

Object array:

```json
{
  "items": [
    {"sku": "BK-01", "quantity": 2, "warehouseCode": "HCM"},
    {"sku": "BK-02", "quantity": 1, "warehouseCode": "HAN"}
  ]
}
```

Repeating element paths use `[]`:

```java
responseFields(
    fieldWithPath("items").description("Line items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Quantity"),
    fieldWithPath("items[].warehouseCode")
        .description("Dispatch warehouse code")
)
```

If `warehouseCode` is internal metadata, replace its descriptor with `.ignored()`. Documenting the parent array does not automatically cover child fields that need to be published.

### 5.1. Multi-level nested arrays

```json
{
  "shipments": [
    {
      "packages": [
        {
          "packageId": "P-01",
          "items": [{"sku": "BK-01", "quantity": 2}]
        }
      ]
    }
  ]
}
```

Detailed paths include `shipments`, `shipments[].packages`, `shipments[].packages[].packageId`, `shipments[].packages[].items`, `shipments[].packages[].items[].sku`, and `shipments[].packages[].items[].quantity`. Each array layer needs a corresponding `[]`; the fixture must have elements at every documented level.

### 5.2. Empty arrays and root arrays

`{"items": []}` still has the `items` field, so the array itself can be documented. The fixture has no child fields like `items[].id` to match. Separate the test generating detailed element documentation from the empty-list test.

If the root response is `[]`:

```java
responseFields(
    fieldWithPath("[]").description("List of products"),
    fieldWithPath("[].id").description("Product ID"),
    fieldWithPath("[].name").description("Product name")
)
```

With an empty root array, there are no elements to document in detail; use a fixture with representative objects and test the empty case separately.

## 6. MockMvc example: detecting unhandled fields

The example uses JUnit Jupiter, MockMvc, Jackson, and `spring-restdocs-mockmvc`:

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
class StrictResponseFieldsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void everyResponseFieldHasAnExplicitDecision() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 1200)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-1200"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andDo(document("orders-strict-fields",
                        responseFields(
                                fieldWithPath("id").description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                fieldWithPath("customer")
                                        .description("Customer details"),
                                fieldWithPath("customer.id")
                                        .description("Customer ID"),
                                fieldWithPath("customer.displayName")
                                        .description("Customer name"),
                                fieldWithPath("totalAmount")
                                        .description("Total amount in VND"),
                                fieldWithPath("internalTraceId").ignored()
                        )
                ));
    }

    @RestController
    static class OrderController {
        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(@PathVariable("id") long id) {
            Map<String, Object> customer = Map.of(
                    "id", "CUS-17",
                    "displayName", "Customer 17");

            Map<String, Object> response = new LinkedHashMap<>();
            response.put("id", "ORD-" + id);
            response.put("status", "CONFIRMED");
            response.put("customer", customer);
            response.put("totalAmount", 250000);
            response.put("internalTraceId", "trace-1200");
            return response;
        }
    }
}
```

When `sourceChannel` is added to the response without a descriptor, the strict snippet-generating test fails. After review, either add a description or ignore it intentionally. If the field should not be in the public API, fix the response and add an assertion verifying the path does not exist.

The test above only verifies a specific HTTP fixture. APIs with multiple variants need separate tests for newly created, paid, cancelled orders, differing access permissions, or empty collections.

## 7. Representative fixtures for structure

| Goal | Fixture should include | Reason |
| --- | --- | --- |
| Root field | Object with root field | Resolves path |
| Nested object | Parent and child fields | Verifies nested paths |
| Object array | At least one element | Observes element paths |
| Nested array | Elements at every level | Verifies multi-level paths |
| Absent optional | Fixture omitting that field | Proves optionality |
| Nullable | Key with null value | Distinguishes null from missing |
| Ignored branch | Payload containing actual branch | Verifies ignore decision |
| Root array | Non-empty array | Documents child paths |

Do not force a single fixture to represent mutually exclusive business branches. For example, an order cannot be both PAID and CANCELLED if the contract forbids it. Create separate tests and snippets for each state.

Example identifiers:

```text
orders-created-response
orders-paid-response
orders-cancelled-response
orders-empty-collection
```

## 8. Descriptor review checklist

- [ ] Every field appearing in the fixture is documented, ignored, or covered by a subsection.
- [ ] No new public field lacks a description.
- [ ] Nested object paths match the serialized JSON.
- [ ] Array paths use `[]` at the correct levels.
- [ ] Required fields are not arbitrarily marked optional.
- [ ] Fields allowed to be absent have `optional()` and an explicit type when needed.
- [ ] Nullable fields are distinguished from missing fields.
- [ ] Ignored internal fields have a reason; sensitive data is removed from real responses.
- [ ] Fixtures contain sample elements for repeating paths.
- [ ] Important response variants have separate tests/snippets.
- [ ] Strict mode is preserved wherever new fields must be detected.
- [ ] Asciidoctor uses fresh snippets from the same test run.

## 9. Strict vs. relaxed

Default `responseFields(...)` suits contracts where changes must be controlled. `relaxedResponseFields(...)` suits cases where you intentionally publish only part of the payload or have a contract migration reason.

| Characteristic | Strict `responseFields` | Relaxed `relaxedResponseFields` |
| --- | --- | --- |
| Undeclared payload field | Can cause snippet generation to fail | Permitted |
| Required descriptor with missing path | Can cause snippet generation to fail | Must still match, unless optional |
| Ignored field | Must be declared explicitly | May be omitted since unlisted fields are allowed |
| Detecting new fields | Better suited for managed contracts | Weaker because unexpected fields can slip through |
| Use case | Complete contract documentation | Partial documentation or migration |

Relaxed mode is not a catch-all fix for broken descriptors. If using relaxed mode, maintain separate schema/assertions controlling the required parts of the payload.

## 10. Snippets and CI

When the `document("orders-strict-fields", ...)` test succeeds, snippets typically reside in the generated snippets directory. With Gradle:

```text
build/generated-snippets/
└── orders-strict-fields/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

With Maven, the common directory is `target/generated-snippets`. Output location is configurable and additional default snippets may be generated.

Asciidoctor embeds the response alongside the field table:

```adoc
= Order API
:snippets: build/generated-snippets

== View order

=== HTTP response
include::{snippets}/orders-strict-fields/http-response.adoc[]

=== Response fields
include::{snippets}/orders-strict-fields/response-fields.adoc[]
```

Build order: compile tests, run HTTP tests to generate snippets, fail if strict descriptors do not cover the payload, and only then compile Asciidoctor and package. When a new field fails the test, reviewers decide whether to publish, intentionally ignore, or remove it from the response. When publishing Markdown, use an appropriate template/converter; the default snippet is Asciidoctor.

## 11. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test reports an undocumented new field | Payload changed without updating descriptors | Review; document or intentionally ignore |
| Test reports a documented field not found | Fixture lacks path, wrong path, or serializer renamed key | Inspect JSON; fix fixture/path or mark optional per contract |
| Only parent object documented | No decision made for child fields | Add child descriptors or a subsection |
| Array field not found | Missing `[]` or empty array | Fix path and fixture |
| All descriptors marked optional | Fails to catch missing required fields | Mark optional only per contract |
| Switched to relaxed to pass the build | Skips reviewing new fields | Keep strict mode or state reason for relaxed |
| Sensitive field ignored | Confused documentation with security | Remove field from response and write tests |
| Stale snippet published | Docs task ran before tests | Generate snippets before Asciidoctor |

## 12. Practice exercise

Using the order response from section 2:

1. Add `sourceChannel` without updating descriptors. Run the strict test and explain the error.
2. Decide whether `sourceChannel` is public or internal. Write a description or mark it ignored.
3. Remove `customer.displayName` from the fixture while keeping the required descriptor. Observe the error; decide whether it is truly optional.
4. Add `items[].warehouseCode`; document or ignore the exact path.
5. Change `items` to an empty array. Separate the empty-case test from the element-structure test.
6. Add a `promotion` object. Compare documenting child fields with `subsectionWithPath("promotion")`.
7. Try relaxed mode with only `id` and `status`; add a new field and compare against strict mode.
8. Generate separate snippets for paid orders and cancelled orders.
9. Include snippets in Asciidoctor and verify tests run before publishing.

**Completion criteria:** you can read a JSON response and make an explicit decision for every field; understand strict errors when payloads add fields or drop required fields; structure nested/array/optional/null fixtures; choose strict or relaxed intentionally; and make build/CI catch unreviewed response changes.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): payload documentation rules, field descriptors, optional, ignored, and relaxed response fields.
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `responseFields`, `relaxedResponseFields`, `subsectionWithPath`, and payload helpers.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `optional()`, `ignored()`, and `type(...)`.
