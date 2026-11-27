# Distinguishing required, optional, and nullable fields in response payloads

## 1. Lesson objectives

In the **Response payload** chapter of the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Each JSON field needs to describe not only its name and data type, but also **whether it must be present** and **whether it may return a `null` value**.

These two properties are independent:

- **Required (present)**: the response must contain the corresponding JSON key or path.
- **Optional (may be absent)**: the response may omit the key entirely.
- **Nullable**: the key may appear with a JSON `null` value.
- **Non-null**: if the key appears, its value must not be `null`.

The goal of this lesson is to understand these distinctions accurately, configure `responseFields(...)` and `fieldWithPath(...)` appropriately, and combine them with assertions to verify the API contract. This also forms the basis for generating `response-fields.adoc`, authoring Asciidoctor/Markdown documentation, and catching contract changes in build/CI.

> **Core note:** Spring REST Docs provides `FieldDescriptor.optional()` to relax the **presence** condition of a field. It does not have a corresponding `nullable()` modifier to automatically verify whether `null` is allowed or forbidden. Nullability must be clearly documented and tested separately when it matters to the API contract.

## 2. Identifying the three states of a JSON key

Consider three different responses from the same endpoint:

### Field present with a value

```json
{
  "discountCode": "WELCOME10"
}
```

The `discountCode` key **exists**, and its value is a string.

### Field present with a null value

```json
{
  "discountCode": null
}
```

The `discountCode` key **still exists**, even though its value is `null`.

### Field completely absent

```json
{}
```

The response does not contain the `discountCode` key. This is different from `"discountCode": null`: clients can distinguish the two payloads by checking whether the key exists.

The two pairs **required/optional** and **nullable/non-null** produce four contract combinations:

| Field contract | May key be absent? | Is `null` allowed? | Valid examples |
| --- | --- | --- | --- |
| Required, non-null | No | No | `{"orderId":"ORD-304"}` |
| Required, nullable | No | Yes | `{"discountCode":null}` or a string |
| Optional, non-null | Yes | No, if key appears | `{}` or `{"delivery":{"method":"STANDARD"}}` |
| Optional, nullable | Yes | Yes | `{}`, `{"note":null}`, or a string |

Do not treat the following two rules as equivalent:

- "The `discountCode` field must be present, but may hold a `null` value" is **required + nullable**.
- "The `discountCode` field may be omitted from the response" is **optional**, regardless of whether it can be null when present.

This directly affects how clients handle responses. A client might use `containsKey("discountCode")` to distinguish omission from null, whereas a data type that does not support missing values can lose that distinction during deserialization.

## 3. What does `responseFields(...)` verify?

Spring REST Docs describes responses using descriptors:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("orderId")
        .description("Order identifier"),
    fieldWithPath("discountCode")
        .description("Promo code; null if the order has no discount")
)
```

With default `responseFields`:

1. A field that is **declared and not marked optional** but not found in the payload causes snippet generation to fail.
2. A field that **appears in the payload without being documented** can also cause snippet generation to fail.
3. A field **declared with `.optional()`** may be absent without triggering a missing-field error.
4. A path present with a `null` value is different from an absent path; `null` does not automatically mean "optional".

Example of declaring a field that may be absent:

```java
import org.springframework.restdocs.payload.JsonFieldType;

fieldWithPath("delivery")
    .type(JsonFieldType.OBJECT)
    .optional()
    .description("Delivery details; may be absent if delivery has not been selected");
```

**Easy-to-miss detail:** if an optional field **does not appear in the fixture**, Spring REST Docs cannot infer that field's JSON type from the response. To generate a complete snippet, explicitly declare `.type(JsonFieldType.OBJECT)`, `.type(JsonFieldType.STRING)`, or the appropriate type. Adding only `.optional()` resolves the "missing field" error but can still lead to an "unable to determine field type" error.

### 3.1. What does `.type(...)` mean?

`type(JsonFieldType.STRING)` specifies the type description **in the generated documentation**. It is not a general runtime assertion ensuring every response has a string value. When the contract requires a non-null value or a specific type/format, add separate assertions.

Common JSON types:

| `JsonFieldType` | Corresponding JSON data |
| --- | --- |
| `STRING` | `"ORD-304"` |
| `NUMBER` | `125000` |
| `BOOLEAN` | `true`, `false` |
| `OBJECT` | `{"method":"STANDARD"}` |
| `ARRAY` | `[{"sku":"B-01"}]` |
| `NULL` | `null` |
| `VARIES` | Multiple occurrences of a path have different types |

When the fixture only contains `"discountCode": null`, REST Docs may infer the `NULL` type from the data. If the contract allows `discountCode` to be a string or null, specify `STRING` and clearly explain nullability in `description`.

## 4. Designing a response contract for orders

Consider the endpoint `GET /api/orders/304` with two response modes.

**Full version** (`GET /api/orders/304?view=full`):

```json
{
  "orderId": "ORD-304",
  "status": "CONFIRMED",
  "totalAmount": 125000,
  "discountCode": null,
  "delivery": {
    "method": "STANDARD",
    "trackingNumber": null
  },
  "items": [
    {
      "sku": "B-01",
      "quantity": 2,
      "note": null
    }
  ]
}
```

**Compact version** (`GET /api/orders/304?view=compact`):

```json
{
  "orderId": "ORD-304",
  "status": "CONFIRMED",
  "totalAmount": 125000,
  "discountCode": null,
  "items": [
    {
      "sku": "B-01",
      "quantity": 2
    }
  ]
}
```

The two payloads illustrate these field groups:

| Path | Example contract | Explanation |
| --- | --- | --- |
| `orderId` | Required, non-null | Order ID is always needed |
| `status` | Required, non-null | Order status is always present |
| `totalAmount` | Required, non-null | Total amount in VND |
| `discountCode` | Required, nullable | Key is always present; null when no promo applies |
| `delivery` | Optional, non-null if present | Compact mode omits the delivery branch |
| `delivery.method` | Required when `delivery` is present | Condition depends on the parent object |
| `delivery.trackingNumber` | Nullable when `delivery` is present | Null when no tracking number has been assigned yet |
| `items` | Required, non-null | Array of line items |
| `items[].sku` | Required in each item, non-null | Product SKU |
| `items[].quantity` | Required in each item, non-null | Quantity |
| `items[].note` | Optional and nullable | An item may omit the key or hold a null value |

These rules are an **illustrative contract for the sample API**, not universally true for every system. For example, another API might omit `discountCode` altogether when no discount applies, or always return `delivery: null` instead of omitting the key.

## 5. MockMvc testing: verifying both absent and null fields

The following example uses JUnit Jupiter, Spring MVC, Jackson, and `spring-restdocs-mockmvc`. The test controller produces two responses to accurately document both variants of the same contract.

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
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OptionalNullableOrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    private static FieldDescriptor[] orderFields() {
        return new FieldDescriptor[] {
                fieldWithPath("orderId")
                        .description("Order ID, always present"),
                fieldWithPath("status")
                        .description("Order processing status"),
                fieldWithPath("totalAmount")
                        .description("Total order amount, in VND"),

                // Must be present, though the value is allowed to be null.
                fieldWithPath("discountCode")
                        .type(JsonFieldType.STRING)
                        .description("Discount code; null when not applied"),

                // Parent object may be absent in compact responses.
                fieldWithPath("delivery")
                        .type(JsonFieldType.OBJECT)
                        .optional()
                        .description("Delivery details; may be absent"),

                // Child paths may also be absent if the parent object is missing.
                fieldWithPath("delivery.method")
                        .type(JsonFieldType.STRING)
                        .optional()
                        .description("Delivery method when delivery is present"),
                fieldWithPath("delivery.trackingNumber")
                        .type(JsonFieldType.STRING)
                        .optional()
                        .description("Tracking number; null before assignment"),

                fieldWithPath("items")
                        .description("Line items in the order"),
                fieldWithPath("items[].sku")
                        .description("Product SKU in the line item"),
                fieldWithPath("items[].quantity")
                        .description("Product quantity"),

                // May be omitted on an item or hold a null value.
                fieldWithPath("items[].note")
                        .type(JsonFieldType.STRING)
                        .optional()
                        .description("Line item note; may be missing or null")
        };
    }

    @Test
    void documentFullOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 304)
                        .param("view", "full")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-304"))
                .andExpect(jsonPath("$.discountCode").hasJsonPath())
                .andExpect(jsonPath("$.discountCode").value(nullValue()))
                .andExpect(jsonPath("$.delivery.method").value("STANDARD"))
                .andExpect(jsonPath("$.delivery.trackingNumber").hasJsonPath())
                .andExpect(jsonPath("$.delivery.trackingNumber")
                        .value(nullValue()))
                .andExpect(jsonPath("$.items[0].note").hasJsonPath())
                .andDo(document("orders-full-response",
                        responseFields(orderFields())));
    }

    @Test
    void documentCompactOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 304)
                        .param("view", "compact")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.discountCode").hasJsonPath())
                .andExpect(jsonPath("$.discountCode").value(nullValue()))
                .andExpect(jsonPath("$.delivery").doesNotHaveJsonPath())
                .andExpect(jsonPath("$.items[0].note").doesNotHaveJsonPath())
                .andDo(document("orders-compact-response",
                        responseFields(orderFields())));
    }

    @RestController
    static class OrderController {

        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(
                @PathVariable("id") long id,
                @RequestParam(name = "view", defaultValue = "full")
                String view) {

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("orderId", "ORD-" + id);
            body.put("status", "CONFIRMED");
            body.put("totalAmount", 125000);
            body.put("discountCode", null);

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("sku", "B-01");
            item.put("quantity", 2);

            if ("full".equals(view)) {
                item.put("note", null);
                Map<String, Object> delivery = new LinkedHashMap<>();
                delivery.put("method", "STANDARD");
                delivery.put("trackingNumber", null);
                body.put("delivery", delivery);
            }

            body.put("items", List.of(item));
            return body;
        }
    }
}
```

The example uses `LinkedHashMap` because it accepts `null` values and makes **explicitly adding or omitting keys** clear. Java's `Map.of(...)` does not allow null keys or values, so it is unsuitable for creating fixtures with `discountCode: null`.

In a real application, you can replace the sample controller with a real controller and configure `@WebMvcTest`, `@SpringBootTest`, or WebTestClient/REST Assured accordingly. The `fieldWithPath` descriptors and required/optional principles remain the same.

### 5.1. Why do child descriptors also need `optional()`?

`delivery` can be absent in the compact version, so the paths `delivery.method` and `delivery.trackingNumber` do not exist in that version either.

Marking child descriptors with `.optional()` allows **documentation-generating tests for both variants** to succeed. However, this does not automatically enforce the rule "if `delivery` appears, `delivery.method` must be present." The full-variant test needs an assertion such as:

```java
.andExpect(jsonPath("$.delivery.method").isString())
```

If you need to verify conditional rules across many responses, you can inspect a parsed `JsonNode` or use JSON Schema, depending on system requirements.

### 5.2. Distinguishing JSONPath matchers in MockMvc

These matchers are **not synonymous**:

| Matcher | Meaning |
| --- | --- |
| `jsonPath("$.x").hasJsonPath()` | Key/path exists, even if its value is `null` |
| `jsonPath("$.x").doesNotHaveJsonPath()` | Key/path does not exist; even a null value counts as having the path |
| `jsonPath("$.x").exists()` | A **non-null** value exists at the path |
| `jsonPath("$.x").doesNotExist()` | No non-null value found; the key may still exist with a null value |
| `jsonPath("$.x").value(nullValue())` | Observed value is null |
| `jsonPath("$.x").isString()` | Observed value has a string type |

To verify that a **key is present and null**, combine `hasJsonPath()` with `value(nullValue())`. To confirm a **key is truly omitted**, use `doesNotHaveJsonPath()`. Relying only on `doesNotExist()` to prove "the field is absent" is not strict enough because that matcher treats null as non-existent.

The path in `jsonPath("$.delivery.method")` follows Spring Test's JSONPath syntax, whereas the descriptor `fieldWithPath("delivery.method")` uses Spring REST Docs' syntax. Both syntaxes are similar but not identical; for instance, JSONPath includes a `$` prefix.

## 6. Nullable fields and generating type information

Consider the response:

```json
{
  "discountCode": null,
  "trackingNumber": null
}
```

Without specifying a type, REST Docs only sees `null` values. When the documentation should clarify that the value is normally a string, use:

```java
responseFields(
    fieldWithPath("discountCode")
        .type(JsonFieldType.STRING)
        .description("Promo code; key is required, value may be null"),

    fieldWithPath("trackingNumber")
        .type(JsonFieldType.STRING)
        .description("Tracking number; null before the order is handed to the carrier")
)
```

Neither field in the example above has `optional()` because the contract requires the key to always appear. `.type(JsonFieldType.STRING)` only indicates the expected business type in the table; the description explains what a null value means.

If the sample response is `{}` yet you declare an `optional()` field, explicitly specify its type:

```java
fieldWithPath("deliveryDate")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Estimated delivery date, may be omitted; YYYY-MM-DD format");
```

You cannot expect REST Docs to infer `STRING` from a key that does not appear at all. Adding only `optional()` without `type(...)` can trigger a type-resolution error when generating the field table.

### 6.1. Is `JsonFieldType.NULL` needed?

`JsonFieldType.NULL` describes a JSON null value. Use this type when **the null type itself** is what you want to convey. For a field that is "string or null", it is usually better to document the meaningful business type as `STRING`, then explain the possibility of null in `description`. If an API has a field that is intentionally always null, explain why it exists so readers are not confused.

### 6.2. Should you specify both `optional()` and `type(...)`?

Yes, if the key is **allowed to be absent**. `optional()` and `type(...)` solve two different problems:

```java
fieldWithPath("couponDescription")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Promotion description; omitted when no campaign applies");
```

- `optional()`: prevents missing paths from being treated as a descriptor error.
- `type(JsonFieldType.STRING)`: keeps the field table's data type consistent even when the current fixture omits the path.
- `description(...)`: clarifies when the field is absent or null, since neither type nor optional conveys the full rule.

## 7. When a parent object, array, or repeating element may be absent

### 7.1. Parent object may be absent, null, or an object

Three payloads:

```json
{}
```

```json
{"delivery": null}
```

```json
{"delivery": {"method": "STANDARD"}}
```

If `delivery` is allowed to be absent, use:

```java
fieldWithPath("delivery")
    .optional()
    .type(JsonFieldType.OBJECT)
    .description("Delivery details; may be missing or null");

fieldWithPath("delivery.method")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Delivery method when delivery is an object");
```

However, the rule "`delivery.method` is required when `delivery` is an object" must be verified separately in cases where the object is present. When the parent is null, the `delivery.method` path does not exist, so child descriptors must be designed according to the response variants under test.

If the actual contract **requires the `delivery` key to appear** while its value may be null, remove `optional()` from the `delivery` descriptor, while keeping child descriptors optional because the parent may sometimes be null.

### 7.2. Empty array vs. missing array and null array

```json
{"items": []}
```

```json
{}
```

```json
{"items": null}
```

These three responses are not the same:

- `items: []`: key is present, value is an **empty array**.
- `{}`: `items` key is absent.
- `items: null`: key is present, value is null.

If the contract requires `items` to always be an array, the descriptor `fieldWithPath("items")` only documents that the field should exist; `jsonPath("$.items").isArray()` must be used to verify it is genuinely an array, even when empty. When at least one element is required, add a size check.

With `fieldWithPath("items[].sku")`, a fixture with `items: []` has no `sku` value to inspect. When generating detailed documentation, use a fixture containing at least one representative element. The empty-array case and the rule "every element has a `sku`" must be verified with separate assertions.

### 7.3. Some elements have a field, others do not

```json
{
  "items": [
    {"sku": "B-01", "note": "Gift wrap"},
    {"sku": "B-02"},
    {"sku": "B-03", "note": null}
  ]
}
```

A shared descriptor can be:

```java
fieldWithPath("items[].note")
    .optional()
    .type(JsonFieldType.STRING)
    .description("Optional note for each line item, may be null");
```

Finding `items[].note` on some elements does not prove that all elements follow the same presence/null rules. For per-element constraints, parse the JSON into a `JsonNode` and inspect every item, or use JSON Schema. Spring REST Docs helps generate documentation and detect many structural changes; it does not replace full validation of repeating data.

## 8. Null in Java DTOs and serialization

`responseFields` documentation must reflect the **actual JSON returned to clients**, rather than being inferred directly from whether a Java field has type `String`, `Optional<String>`, or a `@Nullable` annotation.

For example, a DTO with a Java null value:

```java
record OrderDto(
    String orderId,
    String discountCode
) {}
```

Might serialize to:

```json
{"orderId":"ORD-304","discountCode":null}
```

However, when Jackson is configured to omit null fields, for instance:

```java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
record OrderDto(
    String orderId,
    String discountCode
) {}
```

the JSON can become:

```json
{"orderId":"ORD-304"}
```

Thus, **the exact same Java null value** can lead to two different response contracts depending on serialization configuration. Settings such as `@JsonInclude`, `@JsonProperty`, naming strategies, custom serializers, and field filters can all affect the actual paths.

Do not mark a field as `optional()` merely because its Java type is nullable. Inspect the JSON produced by HTTP tests first and establish the API's public contract.

## 9. Clearly documenting nullability in snippets and published docs

By default, `response-fields.adoc` renders a table with columns such as **Path**, **Type**, and **Description**. To help readers distinguish "key may be missing" from "value may be null", state it explicitly in `description`:

```java
fieldWithPath("discountCode")
    .type(JsonFieldType.STRING)
    .description("Key is always present; null when no promo code applies");

fieldWithPath("delivery")
    .optional()
    .type(JsonFieldType.OBJECT)
    .description("Omitted in compact responses; an object when present");

fieldWithPath("items[].note")
    .optional()
    .type(JsonFieldType.STRING)
    .description("May be missing or null; string when content is provided");
```

If a project wants two separate columns for "Required" and "Nullable", you can attach custom metadata to descriptors and configure a **custom snippet template** to display them. Example of attaching attributes:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("discountCode")
    .type(JsonFieldType.STRING)
    .attributes(
        key("required").value(true),
        key("nullable").value(true)
    )
    .description("Order promo code");
```

These attributes are **template metadata**; they do not automatically enable validation or appear as columns in the default template. If you use custom metadata, maintain the template and ensure its contents match your API assertions.

Both tests in section 5 generate field tables:

```text
build/generated-snippets/
├── orders-full-response/
│   └── response-fields.adoc
└── orders-compact-response/
    └── response-fields.adoc
```

With Maven, the directory is usually `target/generated-snippets`, and the exact location can be configured. When using Asciidoctor:

```adoc
= Order API
:snippets: build/generated-snippets

== Full response

include::{snippets}/orders-full-response/response-fields.adoc[]

== Compact response

include::{snippets}/orders-compact-response/response-fields.adoc[]
```

These snippets default to Asciidoctor format. When publishing Markdown documentation, an appropriate conversion workflow or template is needed. In build/CI, run snippet-generating tests before the documentation compilation step; if payload changes break tests, outdated documentation should not be published.

## 10. Common mistakes

| Symptom or misconception | Cause | Resolution |
| --- | --- | --- |
| "Field is null so it must be optional" | Confusing a **null value** with an **absent key** | Only use `optional()` when the key is allowed to be omitted |
| Omitting `optional()` from a field that is sometimes absent | Default descriptor requires the path to be present | Add `optional()` as specified by the contract |
| Added `optional()` yet snippet generation fails on type | Fixture lacks the field so type cannot be inferred | Add `type(JsonFieldType...)` |
| A `null` field is documented as `NULL` despite contract saying string or null | REST Docs infers type from the fixture | Set expected type with `.type(JsonFieldType.STRING)` and document null |
| `jsonPath(...).doesNotExist()` used to prove a key was omitted | This matcher also passes for null values | Use `doesNotHaveJsonPath()` |
| `jsonPath(...).exists()` used to prove a null key is present | `exists()` requires a non-null value | Use `hasJsonPath()` |
| `delivery` is optional while child fields remain required | Response lacks parent object so child paths are also missing | Analyze variants; mark child fields optional and test conditional rules separately |
| One item having `note` makes all items appear valid | Repeating path descriptors do not replace per-element checks | Add loop/schema checks |
| Adding `.type(STRING)` and assuming null can no longer be returned | Descriptor type is documentation metadata | Write non-null/type assertions when required by the contract |
| `@JsonInclude(NON_NULL)` configuration breaks tests | Serializer changes field presence | Verify actual JSON, update contract and descriptors |

"Required but allowed to be null" fields often appear for data not yet populated or awaiting processing. "Optional, and non-null if present" fields often appear in minimal response variants. Explain both aspects clearly so integrators do not handle them incorrectly.

## 11. Practice exercise

Use the order example from section 4 and try the following changes:

1. **From null to absent:** remove `discountCode` from the compact response. Keep the descriptor required and observe the failure; if the contract allows omission, update it to `optional()` while keeping `.type(JsonFieldType.STRING)`.
2. **From absent to null:** return `"delivery": null` in the compact version. Compare the results of `jsonPath("$.delivery").doesNotHaveJsonPath()` and `hasJsonPath()`. Adjust assertions to match the intended contract.
3. **Unexpected data type:** replace `"discountCode": null` with `"discountCode": 123`. Keep `type(JsonFieldType.STRING)` and add an assertion to catch the invalid `NUMBER` type.
4. **Conditional parent:** in the full version, remove `delivery.method` while keeping `delivery`. Write an assertion ensuring `method` is a non-null string when the parent object is present.
5. **Empty array:** return `"items": []`. Observe the limitation of `items[].sku` and `items[].quantity` in the documentation fixture; test the empty-array case separately.
6. **Some items missing a field:** add three line items with `note` set to a string, missing key, and null respectively. Verify the `optional()` descriptor, then write assertions for each business rule.
7. **Change serializer:** add `@JsonInclude(Include.NON_NULL)` to a sample DTO. Compare the JSON before and after, then adjust descriptors according to the public contract.
8. **Published documentation:** include snippets in Asciidoctor and ensure the build runs tests before the documentation generation step.

**Completion criteria:** you can distinguish between **key absent**, **key with null value**, and **key with non-null value**; declare `optional()` with the right scope; specify explicit types when they cannot be inferred from fixtures; use appropriate assertions to verify required/non-null/parent-dependent conditions; and integrate response tables into CI-controlled Spring REST Docs documentation.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field validation rules, `optional()`, `ignored()`, JSON types, and snippets.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `optional()` and `type(...)`.
- [Spring Framework — JsonPathResultMatchers](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): differences between `hasJsonPath()`, `exists()`, and `doesNotHaveJsonPath()`.
