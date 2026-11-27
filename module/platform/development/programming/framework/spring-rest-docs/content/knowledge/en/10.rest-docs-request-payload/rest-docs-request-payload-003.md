# `fieldWithPath` and Nested Field Paths in Spring REST Docs

## 1. Goals and context

Real-world REST APIs rarely accept JSON with only flat fields like `name` and `email`. Payloads commonly contain **nested objects**, **arrays of objects**, nested arrays, and occasionally field names containing dots or dynamically generated keys. If a path is described incorrectly, the API documentation table can miss important fields or documentation generation can fail.

In **Spring REST Docs**, `fieldWithPath(...)` identifies **the location of a field in JSON**, while `requestFields(...)` collects the descriptions into a request body snippet. This mechanism works alongside HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. From those snippets, teams can assemble Asciidoctor/Markdown documentation and regenerate documentation in the build/CI.

This lesson belongs to the **Request payload** chapter and focuses on reading and writing field paths with `fieldWithPath` in complex JSON structures. After studying it, you will be able to:

- Use dot notation to point to fields inside objects.
- Use `[]` to describe array elements and fields inside each element.
- Use bracket notation with quotes for **field names containing dots**.
- Know when to use the `*` wildcard for dynamic keys.
- Write tests that generate `request-fields.adoc`, understand the validation limits of snippets, and handle paths reported as missing.

## 2. Field path map from a real-world JSON

Suppose the order-creation API `POST /api/orders` accepts this request body:

```json
{
  "customer": {
    "id": 42,
    "profile": {
      "displayName": "Nguyen Minh An",
      "contact": {
        "email": "an@example.com"
      }
    }
  },
  "items": [
    {
      "sku": "SHIRT-001",
      "quantity": 2,
      "options": [
        { "name": "color", "value": "navy" }
      ]
    },
    {
      "sku": "SOCK-002",
      "quantity": 1,
      "options": []
    }
  ],
  "tags": ["gift", "priority"],
  "metadata": {
    "source": "mobile",
    "campaign.name": "fall-2026"
  },
  "attributes": {
    "store": "hcm-01",
    "device": "android"
  }
}
```

Picture JSON as a tree: objects contain named branches (keys); arrays contain elements by position. `fieldWithPath` describes **a path through the tree** using Spring REST Docs syntax, not a full JSONPath query expression.

| To describe | Path used with `fieldWithPath` | Explanation |
| --- | --- | --- |
| Customer object | `customer` | Root-level field |
| Customer ID | `customer.id` | Direct child of `customer` |
| Display name | `customer.profile.displayName` | Traverses two nested objects |
| Email | `customer.profile.contact.email` | Traverses three nested objects |
| Entire items array | `items` | The array itself |
| Item SKU | `items[].sku` | `sku` in each object of `items` |
| Option name | `items[].options[].name` | Object in the `options` array inside `items` |
| Entire tags array | `tags` | The array of strings itself |
| Each tag | `tags[]` | One string element of the array |
| Order source | `metadata.source` | Regular key name |
| Key named `campaign.name` | `metadata['campaign.name']` | The dot is **part of the key name** |
| Values in dynamic map | `attributes.*` | `*` matches direct child keys of `attributes` |

The most important point: `items[].sku` does **not** mean "take only the first element". The `[]` notation describes the `sku` field across array elements regardless of specific index. Conversely, `metadata['campaign.name']` preserves `campaign.name` as **a single key name**; writing `metadata.campaign.name` would be interpreted as two levels (`campaign` and `name`), which does not match the sample JSON.

### Distinguishing the four syntax forms

```text
customer.profile.displayName     -> object -> object -> field
items[].sku                      -> array -> each object -> field
metadata['campaign.name']        -> object -> key containing a dot in its name
attributes.*                     -> object -> dynamic child keys
```

There is no need to prepend `$` at the start of the path as in many JSONPath expressions. With Spring REST Docs, write `fieldWithPath("customer.id")`, not `fieldWithPath("$.customer.id")`.

## 3. Dot notation (`.`) and nested objects

This is the most common case:

```json
{
  "account": {
    "id": 100,
    "owner": {
      "name": "Binh",
      "contact": {
        "email": "binh@example.com"
      }
    }
  }
}
```

The corresponding descriptors:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("account")
        .description("Account information");

fieldWithPath("account.id")
        .description("Account ID");

fieldWithPath("account.owner")
        .description("Account owner");

fieldWithPath("account.owner.name")
        .description("Account owner name");

fieldWithPath("account.owner.contact.email")
        .description("Account owner email");
```

Each segment between dots is a JSON key belonging to an object. The path does not depend on Java class names or DTO field names; it must match the **actual JSON sent over HTTP**. For example, if a DTO has a `displayName` property but Jackson is configured with `@JsonProperty("display_name")`, the descriptor must point to `display_name`:

```java
fieldWithPath("account.owner.display_name")
        .description("Display name matching the JSON field name");
```

### Keys containing dots: use bracket notation

The following two JSON payloads are not equivalent:

```json
{ "config": { "logging.level": "INFO" } }
```

```json
{ "config": { "logging": { "level": "INFO" } } }
```

Their corresponding paths are:

```java
// Literal key "logging.level"
fieldWithPath("config['logging.level']")
        .description("Log level");

// Key "level" nested inside object "logging"
fieldWithPath("config.logging.level")
        .description("Log level");
```

Similarly, a root-level key whose name contains a dot can be described using bracket notation such as `fieldWithPath("['request.id']")`.

**Rule of thumb:** a dot outside quotes in path syntax separates levels; a dot *inside a quoted key name* is part of the field name. You can use bracket notation for regular key names if you want, though dot notation is easier to read when keys have no special characters.

## 4. `[]` syntax and array levels

### 4.1. Array of objects

Given the JSON:

```json
{
  "products": [
    { "id": "P-01", "quantity": 2 },
    { "id": "P-02", "quantity": 3 }
  ]
}
```

The paths are:

```java
fieldWithPath("products")
        .description("List of products");

fieldWithPath("products[].id")
        .description("Product ID");

fieldWithPath("products[].quantity")
        .description("Quantity of each product");
```

`products[].id` expresses the same structure appearing across array elements. It is unnecessary and usually undesirable to list `products[0].id`, `products[1].id` just to document the general schema of a list. What matters is that each object in the array follows the API contract.

### 4.2. Array of primitive values

If the JSON contains:

```json
{
  "tags": ["spring", "documentation"]
}
```

There are two distinct levels of description:

```java
fieldWithPath("tags")
        .description("List of tags");

fieldWithPath("tags[]")
        .description("A tag in the list");
```

`tags` describes the entire array. `tags[]` describes each element, which in this case is a String. Distinguish these two levels clearly when you want the documentation to explain both the list as a whole and each individual value.

### 4.3. Arrays inside arrays

Given the JSON:

```json
{
  "groups": [
    ["A", "B"],
    ["C"]
  ]
}
```

You can describe it as:

```java
fieldWithPath("groups")
        .description("Code groups");

fieldWithPath("groups[]")
        .description("A code group, represented as an array");

fieldWithPath("groups[][]")
        .description("A code within a group");
```

Each pair of `[]` represents one array level. When encountering multi-level arrays mixed with objects, read the path from left to right, stepping through each level in the exact order of the sample structure.

### 4.4. Array of objects containing an array of objects

In the order-creation example, the path `items[].options[].value` consists of:

1. `items[]`: an element of the items array;
2. `options[]`: an element of that item's options array;
3. `value`: a field belonging to the option object.

```java
fieldWithPath("items[].options[].value")
        .description("Value of each product option");
```

**When generating snippets, provide sample data with at least one element in the branches you need to document.** If every `options` array is empty, the test has no actual values to match descriptors like `items[].options[].name` and `items[].options[].value`. Testing the empty-array case should be a separate scenario according to the contract.

## 5. The `*` wildcard when key names vary

Not every JSON object has a fixed list of keys. An API may accept an attribute map:

```json
{
  "attributes": {
    "store": "hcm-01",
    "device": "android",
    "campaign": "holiday"
  }
}
```

If the contract allows clients to send **arbitrary keys whose values share the same type**, you can use the wildcard:

```java
fieldWithPath("attributes")
        .description("Map of additional attributes");

fieldWithPath("attributes.*")
        .description("Value of an additional attribute");
```

Here, `*` represents child keys at the corresponding level of the `attributes` object. Its purpose is to describe **a map structure with dynamic key names**, not to automatically generate separate descriptions for every key. Clearly document key naming rules, value constraints, and disallowed keys if the API enforces such conditions.

Comparison:

| JSON object | Descriptor | Meaning |
| --- | --- | --- |
| `{ "attributes": {"store": "hcm"} }` | `attributes.store` | Only the specific `store` key |
| `{ "attributes": {"store": "hcm"} }` | `attributes.*` | Keys belonging to the `attributes` map |
| `{ "items": [{"sku": "A"}] }` | `items[].sku` | The `sku` field of objects in the array |

`*` does not mean the same thing as `[]`: the wildcard represents varying **field names**, whereas `[]` traverses **array elements**. If the map holds values of mixed types, document the contract more explicitly and consider appropriate descriptors or a controllable DTO structure instead of assuming homogeneous values.

## 6. Complete MockMvc example: generating snippets for multi-level payloads

This section uses Spring Boot 3.x, JUnit 5, Java 17, and Spring REST Docs MockMvc. Assume the `POST /api/orders` endpoint already exists and returns **HTTP 201 Created** for valid requests. The `spring-boot-starter-test` and `spring-restdocs-mockmvc` dependencies are required in the test configuration.

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

The test sends the exact JSON request from section 2 and documents the important paths:

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
class OrderNestedPayloadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentNestedOrderRequest() throws Exception {
        String requestJson = """
                {
                  "customer": {
                    "id": 42,
                    "profile": {
                      "displayName": "Nguyen Minh An",
                      "contact": {
                        "email": "an@example.com"
                      }
                    }
                  },
                  "items": [
                    {
                      "sku": "SHIRT-001",
                      "quantity": 2,
                      "options": [
                        { "name": "color", "value": "navy" }
                      ]
                    },
                    {
                      "sku": "SOCK-002",
                      "quantity": 1,
                      "options": []
                    }
                  ],
                  "tags": ["gift", "priority"],
                  "metadata": {
                    "source": "mobile",
                    "campaign.name": "fall-2026"
                  },
                  "attributes": {
                    "store": "hcm-01",
                    "device": "android"
                  }
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("orders-nested-request",
                        requestFields(
                                fieldWithPath("customer")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Customer information"),
                                fieldWithPath("customer.id")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Customer ID"),
                                fieldWithPath("customer.profile")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Customer profile"),
                                fieldWithPath("customer.profile.displayName")
                                        .type(JsonFieldType.STRING)
                                        .description("Display name"),
                                fieldWithPath("customer.profile.contact")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Contact information"),
                                fieldWithPath("customer.profile.contact.email")
                                        .type(JsonFieldType.STRING)
                                        .description("Contact email"),

                                fieldWithPath("items")
                                        .type(JsonFieldType.ARRAY)
                                        .description("List of order items"),
                                fieldWithPath("items[].sku")
                                        .type(JsonFieldType.STRING)
                                        .description("Product SKU"),
                                fieldWithPath("items[].quantity")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Quantity"),
                                fieldWithPath("items[].options")
                                        .type(JsonFieldType.ARRAY)
                                        .description("Item options"),
                                fieldWithPath("items[].options[].name")
                                        .type(JsonFieldType.STRING)
                                        .description("Option name"),
                                fieldWithPath("items[].options[].value")
                                        .type(JsonFieldType.STRING)
                                        .description("Option value"),

                                fieldWithPath("tags")
                                        .type(JsonFieldType.ARRAY)
                                        .description("Order tags"),
                                fieldWithPath("tags[]")
                                        .type(JsonFieldType.STRING)
                                        .description("A tag"),
                                fieldWithPath("metadata")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Order metadata"),
                                fieldWithPath("metadata.source")
                                        .type(JsonFieldType.STRING)
                                        .description("Order creation source"),
                                fieldWithPath("metadata['campaign.name']")
                                        .type(JsonFieldType.STRING)
                                        .description("Campaign name"),

                                fieldWithPath("attributes")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Extended attributes"),
                                fieldWithPath("attributes.*")
                                        .type(JsonFieldType.STRING)
                                        .description("Extended attribute value")
                        )));
    }
}
```

After the test passes its HTTP expectations and the documentation step, the output directory typically looks like:

```text
build/generated-snippets/
└── orders-nested-request/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-fields.adoc
```

Depending on REST Docs configuration, the directory may contain additional snippets such as `curl-request.adoc`, `httpie-request.adoc`, or `request-body.adoc`. `request-fields.adoc` is the snippet created from `requestFields(...)` in this example.

### Verification sequence

1. MockMvc sends the JSON request to the endpoint in the test environment.
2. `.andExpect(status().isCreated())` verifies the HTTP status expected by the example.
3. `requestFields(...)` matches the descriptors against the sample request payload to generate the fields table.
4. Paths with data are written to the snippet with their field name, type, and description.
5. If both the test and snippet generation succeed, Asciidoctor can include the table from the output directory.

**Important limitation:** Spring REST Docs validates documentation coverage against the actual payload sent in the test. It is **not** a general-purpose JSON Schema validator: declaring `.type(JsonFieldType.STRING)` and `.description("...")` primarily serves documentation and does not automatically ensure that real-world API requests always have the right types or satisfy business constraints.

## 7. Required fields, optional fields, and branches that do not always appear

By default, a descriptor declared with `fieldWithPath(...)` is **required during the documentation step**. If the sample request omits a field documented as required, snippet generation can fail.

When the contract permits omitting a field, use `.optional()`:

```java
fieldWithPath("customer.profile.contact.phone")
        .type(JsonFieldType.STRING)
        .description("Phone number, can be omitted")
        .optional()
```

For example, `phone` is not present in the JSON from section 2, yet this descriptor can still be included in the table thanks to `.optional()`.

When **an entire object** may be absent, examine the optionality of the descriptors inside it. For example:

```java
fieldWithPath("shipping")
        .type(JsonFieldType.OBJECT)
        .description("Shipping details, optional")
        .optional(),

fieldWithPath("shipping.receiverName")
        .type(JsonFieldType.STRING)
        .description("Recipient name when shipping is provided")
        .optional(),

fieldWithPath("shipping.address.city")
        .type(JsonFieldType.STRING)
        .description("Shipping city")
        .optional()
```

Marking the parent object optional does not automatically make child descriptors optional. If a child field has a constraint like "required **when** the parent object is present", verify it further with tests/validation, because `.optional()` alone cannot express that full condition.

Further distinctions:

- **Key absent:** the field is genuinely missing from the JSON.
- **Key present with `null` value:** the JSON still contains the field name, but its value is `null`; whether `null` is allowed or rejected belongs to the contract and validation.
- **Key present with an empty object/array:** the branch exists, but there may be no elements or child fields to describe.
- **Key present with the wrong type:** can cause inaccurate documentation if you rely only on `.type(...)`; add business-logic and validation tests.

In documentation tests, use a representative sample request containing all branches so every important path is demonstrated. Variants where optional branches are absent or arrays are empty should have separate tests to verify API behavior.

## 8. `fieldWithPath` vs. `subsectionWithPath`

When an object is large, you may choose to document a branch as a single block:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("customer.profile")
        .description("Customer profile details");
```

`subsectionWithPath(...)` is used to describe **the entire subtree beneath** a path without requiring every child field to be listed individually in the current snippet. This is useful when there are separate sub-documents or when only an overview table is needed.

Meanwhile:

```java
fieldWithPath("customer.profile.displayName")
        .description("Display name");

fieldWithPath("customer.profile.contact.email")
        .description("Contact email");
```

lets the documentation table explicitly list the fields clients need to know. When detailed documentation is desired, declare each meaningful field individually.

Note: in Spring REST Docs, documenting **a parent object or array** can cause child fields to be treated as covered when checking for undocumented fields. Therefore, a passing `requestFields` test **does not automatically prove that every child field has its own description**. Design the descriptor table at the level of detail API consumers need.

## 9. Recognizing wrong paths and reading errors

Suppose the payload is:

```json
{
  "items": [{ "sku": "BOOK-001" }],
  "metadata": { "campaign.name": "back-to-school" }
}
```

The following paths show common mistakes:

| Wrong descriptor | Problem | Correct form |
| --- | --- | --- |
| `item[].sku` | Wrong key name `items` | `items[].sku` |
| `items.sku` | Skipped the array level | `items[].sku` |
| `items[0].sku` | Bound to a specific index instead of describing the general structure | `items[].sku` |
| `metadata.campaign.name` | Split the `campaign.name` key into two objects | `metadata['campaign.name']` |
| `attributes[]` | Treated a dynamic-key map as an array | `attributes.*` |
| `$.items[].sku` | Used a typical JSONPath prefix | `items[].sku` |

Other errors:

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Test reports undocumented field | JSON has a new key with no descriptor yet | Add `fieldWithPath` and clearly describe the structure |
| Test reports missing field | Wrong path, wrong casing, or a required field missing from the sample | Compare the path directly against actual JSON; add `.optional()` only when the contract allows it |
| Cannot document `items[].options[].value` | No element in the `options` array of the sample request | Send a test with a representative element and test empty arrays separately |
| Key containing a dot fails to match | Used dot notation instead of quoted brackets | Write `metadata['campaign.name']` |
| Some child fields do not appear in the table | Documented only the parent object or used `subsectionWithPath` | Declare detailed descriptors for each field to be published |
| HTTP test succeeds but no `request-fields.adoc` | Did not call `document(..., requestFields(...))` or different output path | Check REST Docs configuration and the snippets directory |
| Table describes correctly but API still accepts bad data | Documentation does not replace validation | Add Bean Validation and appropriate HTTP error tests |

In default `requestFields(...)` mode, undocumented fields cause errors. You can use `relaxedRequestFields(...)` when you intentionally want to describe only part of the JSON, but that allows extra undocumented fields and can hide contract changes.

## 10. Reusing in WebTestClient, REST Assured, and build documentation

The common part across all three testing approaches is the description itself:

```java
requestFields(
        fieldWithPath("items").description("List of items"),
        fieldWithPath("items[].sku").description("Product SKU")
)
```

The difference lies in **where snippet generation is attached to the HTTP test flow**:

| Tool | How documentation is attached (illustrative) |
| --- | --- |
| MockMvc | `.andDo(document("orders", requestFields(...)))` |
| WebTestClient | `.expectBody().consumeWith(document("orders", requestFields(...)))` |
| REST Assured | `.filter(document("orders", requestFields(...)))` |

Each uses `document(...)` and configuration from its **corresponding Spring REST Docs integration module**. For example, MockMvc uses `MockMvcRestDocumentation.document`, WebTestClient uses `WebTestClientRestDocumentation.document`, and REST Assured uses `RestAssuredRestDocumentation.document`.

When integrating with Asciidoctor, you can write `src/docs/asciidoc/api.adoc`:

```adoc
= Orders REST API
:toc: left

== Create order

=== HTTP request
include::{snippets}/orders-nested-request/http-request.adoc[]

=== Request body fields
include::{snippets}/orders-nested-request/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-nested-request/http-response.adoc[]
```

You must configure the `{snippets}` attribute to point to the generated directory, such as `build/generated-snippets`. The build should run the snippet-generating tests **before** running Asciidoctor and ensure the rendering task depends on that output. In CI, a change that breaks documentation tests must fail the build. If you want to publish Markdown, add appropriate Markdown templates or a conversion step; the default snippet format in these examples is `.adoc`.

## 11. Hands-on exercise

Using the order-creation JSON from section 2 and the MockMvc test from section 6:

1. **Add a nested field:** add `customer.profile.contact.phone` to the JSON and declare `fieldWithPath("customer.profile.contact.phone")`. Then remove the field from the JSON, add `.optional()`, and verify the documentation test still passes.
2. **Add an array level:** each item has `warehouseAllocations: [{"warehouseId":"HCM","quantity":1}]`. Write descriptors for `items[].warehouseAllocations`, `items[].warehouseAllocations[].warehouseId`, and `items[].warehouseAllocations[].quantity`.
3. **Try a key containing a dot:** add `"build.version": "1.2"` to `metadata`. Intentionally write `metadata.build.version`, observe the error, then change it to `metadata['build.version']`.
4. **Try a dynamic-key map:** add `"channel": "partner"` to `attributes`; check whether the `attributes.*` descriptor fulfills the goal of describing the map. Explicitly state that the map values are Strings.
5. **Inspect the exported documentation:** run the test, open `request-fields.adoc`, and verify that descriptions exist for objects, arrays, nested fields, dotted keys, and dynamic attributes. Include the snippet in Asciidoctor to inspect the final table.

### Self-check questions

- Why does `items[].sku` express a list contract better than describing each array index individually?
- When does `metadata['campaign.name']` differ from `metadata.campaign.name`?
- How does `attributes.*` differ from `attributes[]`?
- Is having a descriptor for `items` alone enough for **readers** to understand `sku`, `quantity`, and `options`?
- Why are validation tests still needed even when `requestFields` generates the table successfully?

**Key takeaway:** `fieldWithPath` points to **the actual JSON structure sent over HTTP**. Dots represent nested objects, `[]` represents array levels, `['...']` syntax preserves special key names, and `*` supports maps with dynamic key names. Using these paths accurately yields detailed, reproducible request payload snippets and makes discrepancies easy to catch in the build/CI pipeline.
