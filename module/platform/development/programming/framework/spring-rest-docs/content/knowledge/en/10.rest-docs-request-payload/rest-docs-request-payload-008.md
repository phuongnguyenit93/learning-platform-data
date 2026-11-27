# `fieldWithPath` and Writing Concise Descriptions in Spring REST Docs

## 1. The role of paths and descriptions in request fields

When documenting a JSON request with **Spring REST Docs**, each field must answer two questions: where the field sits in the JSON structure and what it means to the API caller.

Spring REST Docs combines two building blocks:

- `fieldWithPath("...")` creates a `FieldDescriptor` pointing to a path in JSON.
- `requestFields(...)` takes those descriptors and generates a snippet describing the request payload.

The name `requestFieldWithPath(...)` sometimes shows up in conversation or makeshift examples, but it is **not a standard Spring REST Docs API**. The correct call is `fieldWithPath(...)` inside `requestFields(...)`.

For example, `POST /api/orders` receives:

```json
{
  "customerId": 42,
  "note": "Deliver after 5 PM",
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
```

We can write:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    fieldWithPath("note")
        .description("Delivery note"),
    fieldWithPath("items")
        .description("List of items"),
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Order quantity")
);
```

`fieldWithPath(...)` identifies the path; `.description(...)` adds meaning; `requestFields(...)` gathers the descriptors into the `request-fields.adoc` snippet. A short description should help clients understand the content and role of the field without repeating the field name in a vague sentence.

After this lesson, you will be able to:
- Correctly distinguish `fieldWithPath` and `requestFields`.
- Write concise, specific descriptions that are consistent in meaning and units.
- Place requiredness, optionality, nullability, and constraint information in the right spot.
- Organize descriptors to avoid duplication and keep snippets maintainable and readable.
- Generate documentation from MockMvc, WebTestClient, or REST Assured tests and include it in an Asciidoctor/Markdown build.

## 2. Structure of a `FieldDescriptor`

A basic descriptor takes the form:

```java
fieldWithPath("fieldPath")
    .description("Description of the field's meaning");
```

You can add type, optionality, ignore status, or custom metadata:

```java
fieldWithPath("quantity")
    .type(JsonFieldType.NUMBER)
    .description("Product quantity")
    .optional();
```

Components:

| Component | Purpose | Notes |
| --- | --- | --- |
| `fieldWithPath("...")` | Identifies the JSON path | Must match actual JSON |
| `.type(JsonFieldType.NUMBER)` | Specifies the displayed type | Does not replace validation |
| `.description("...")` | Explains the field | Keep short, clear, contextual |
| `.optional()` | Allows the field to be absent in the sample payload | Not synonymous with nullable |
| `.ignored()` | Excludes the descriptor from the snippet table | Not a security mechanism |
| `.attributes(...)` | Adds metadata for custom templates to read | Does not appear as a column unless the template uses it |

With `requestFields(...)`, a descriptor not marked `.optional()` is treated as required when matching against the sample payload. Fields that may be absent in some requests need `.optional()` according to the contract.

### 2.1. Distinguishing API names

| Name | Standard Spring REST Docs API? | Role |
| --- | --- | --- |
| `fieldWithPath("items[].sku")` | Yes | Creates a descriptor for one field |
| `requestFields(...)` | Yes | Creates the fields snippet for a request payload |
| `requestFieldWithPath(...)` | No | Not a standard method name |
| `responseFields(...)` | Yes | Creates the fields snippet for a response payload |

For request bodies, do not call `fieldWithPath(...)` alone to generate a snippet. Pass the descriptors into `requestFields(...)` or another appropriate API.

## 3. Principles for writing concise descriptions

A good description should carry enough meaning for readers to understand the field without guessing. You can apply the following principles.

### 3.1. Start with a noun or the data's role

The description should state what data the field represents:

| Weak description | Better description |
| --- | --- |
| `ID` | `Customer ID` |
| `Name` | `Recipient name` |
| `Status` | `Order status` |
| `Date` | `Order creation timestamp` |
| `Data` | `List of items in the order` |

Avoid merely repeating the raw technical name without explanation. For example, `customerId` should not simply be described as "customerId"; readers need to know which customer identifier it is in the API context.

### 3.2. Do not just reword the field name

A description's job is to add meaning, not repeat syntax:

```java
// Weak: only rephrases the name
fieldWithPath("customerId")
    .description("Customer ID");

// Better: explains the referenced entity
fieldWithPath("customerId")
    .description("ID of the customer placing the order");
```

Code identifiers may be in English, while documentation descriptions may be in Vietnamese depending on the project's documentation language. What matters is keeping terminology consistent across operations.

### 3.3. One sentence, one main idea

A basic description usually only needs a noun phrase or a short sentence:

- `ID of the customer placing the order`
- `Email address for order confirmation`
- `Quantity of product ordered`
- `Desired delivery time`

Avoid cramming too many rules into one long sentence. If a field has multiple constraints, separate the meaning and the rules cleanly:

```java
fieldWithPath("quantity")
    .description("Product quantity; integer greater than 0");
```

### 3.4. Include units when numbers could be ambiguous

Numeric fields often need units or conventions:

| Field | Suggested description |
| --- | --- |
| `amount` | `Order total, in VND` |
| `weight` | `Package weight, in grams` |
| `duration` | `Processing time, in seconds` |
| `pageSize` | `Maximum number of records per page` |
| `latitude` | `Latitude in the WGS 84 coordinate system` |

Do not guess units from the field name. They must come from the actual API contract.

### 3.5. Use consistent business terminology

If the project uses "order", do not alternate between "order", "purchase", and "transaction" when referring to the same concept. Similarly, if `customer` is called "customer", fields like `customerId`, `customerName`, and `customerAddress` should maintain matching phrasing.

## 4. Describing fields according to JSON structure

### 4.1. Root-level fields

```json
{
  "customerId": 42,
  "note": "Deliver in the afternoon"
}
```

```java
fieldWithPath("customerId")
    .description("ID of the customer placing the order");

fieldWithPath("note")
    .description("Delivery note");
```

Each description focuses on the field's role in the operation being documented.

### 4.2. Nested objects

```json
{
  "shippingAddress": {
    "recipient": "Nguyen An",
    "city": "Ho Chi Minh City"
  }
}
```

```java
fieldWithPath("shippingAddress")
    .description("Shipping address details");

fieldWithPath("shippingAddress.recipient")
    .description("Recipient name");

fieldWithPath("shippingAddress.city")
    .description("Delivery city");
```

The parent object's description should explain the purpose of the whole group. Child field descriptions should focus on the specific data. Do not reuse the same sentence across all levels.

### 4.3. Arrays and objects inside arrays

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ]
}
```

```java
fieldWithPath("items")
    .description("List of items");

fieldWithPath("items[].sku")
    .description("Product SKU");

fieldWithPath("items[].quantity")
    .description("Order quantity");
```

`items` describes the whole list; `items[].sku` describes the product SKU in each element. Use `[]` to document structures independent of specific indices.

### 4.4. Arrays of primitive values

```json
{
  "tags": ["gift", "priority"]
}
```

```java
fieldWithPath("tags")
    .description("List of order tags");

fieldWithPath("tags[]")
    .description("An order tag");
```

An element description should explain the meaning of each value rather than merely saying "array element".

### 4.5. Special keys

If a JSON key contains a dot in the key name itself, use bracket notation:

```json
{
  "metadata": {
    "campaign.name": "summer"
  }
}
```

```java
fieldWithPath("metadata['campaign.name']")
    .description("Marketing campaign name");
```

Do not use `metadata.campaign.name`, as that syntax expresses nested objects that do not match the sample JSON.

## 5. Writing descriptions for required, optional, and nullable fields

`.description(...)` should focus on the meaning and rules API consumers need to know. `.optional()` is the descriptor option that marks a field as allowed to be absent in the sample payload.

```java
fieldWithPath("couponCode")
    .description("Coupon code; can be omitted")
    .optional();

fieldWithPath("externalReference")
    .description("External reference ID; key is required, null allowed");
```

Do not write "Optional" in the description and forget `.optional()` if the field can actually be absent. Conversely, do not add `.optional()` just to make a test pass when the API requires the field to be present.

| Contract | Descriptor | What should the description say? |
| --- | --- | --- |
| Required, non-null | No `.optional()` | Meaning; add important constraints if needed |
| Optional, non-null | Has `.optional()` | State it can be omitted; if sent, its type/limits |
| Required, nullable | No `.optional()` | State key must always be present, though value may be `null` |
| Optional, nullable | Has `.optional()` | State it can be omitted; if sent, `null` is allowed |

Spring REST Docs does not have a standard `.nullable()` flag on `FieldDescriptor`. If the documentation needs a separate nullable column, use `.attributes(...)` and customize the template; custom metadata does not appear in the table unless the template reads it.

## 6. Complete example: using concise descriptions in MockMvc

Assume the `POST /api/orders` endpoint exists and returns `201 Created` for valid requests. The project already has the `spring-boot-starter-test` and `spring-restdocs-mockmvc` test dependencies.

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Descriptor sets should be separated from test methods for easier reuse and review:

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
    fieldWithPath("customerId")
        .type(JsonFieldType.NUMBER)
        .description("ID of the customer placing the order"),
    fieldWithPath("note")
        .type(JsonFieldType.STRING)
        .description("Delivery note")
        .optional(),
    fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("List of items"),
    fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Order quantity")
};
```

Test class:

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
class OrderRequestFieldsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateOrderRequest() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "note": "Deliver after 5 PM",
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ]
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(ORDER_REQUEST_FIELDS)));
    }
}
```

When the test and snippet generation succeed, Spring REST Docs generates `request-fields.adoc` in `build/generated-snippets/orders-create/`, alongside other HTTP snippets depending on configuration.

Example Asciidoctor include:

```adoc
== Create order

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]
```

## 7. Tips for keeping descriptions short yet informative

### 7.1. Meaning first, rules second

An easy-to-read structure:

`<Meaning>; <important rule if any>`

Examples:
- `Product SKU`
- `Order quantity; integer greater than 0`
- `Order price, in VND`
- `Coupon code; can be omitted`

### 7.2. Move lengthy rules to schema docs or a dedicated section

Do not cram every condition into a description:

```java
// Avoid: too many rules on one line
fieldWithPath("password")
    .description("Password from 12 to 64 characters, must include uppercase, lowercase, digit, special character, must not contain email, must not match last 5 passwords...");
```

Write concisely instead:

```java
fieldWithPath("password")
    .description("Login password; follows the system password policy");
```

Then document the password policy in a separate section where it is easy to update and look up.

### 7.3. Describe only what clients need to know

There is no need to explain internal details such as database table names, Java variable names, or how the system caches data, unless that information affects how clients use the API.

### 7.4. Avoid vague words

Standalone words like "data", "info", "value", and "status" usually lack sufficient meaning. Specify "what data", "whose information", "value in what unit", or "status of which entity".

### 7.5. Maintain a consistent style across operations

You can standardize on conventions:
- Use noun phrases and avoid unnecessarily long sentences.
- End descriptions in a consistent style.
- Write units and formats the same way everywhere.
- Describe parent objects at an overview level and child fields at the specific data level.
- Every optional field must have a matching `.optional()`.

## 8. Reviewing description quality

Before approving a descriptor set, check:

| Review question | Passing sign |
| --- | --- |
| Does the path match the JSON payload? | Snippet test passes against the exact sample request |
| Does the description state what the field is? | Readers understand without guessing from code names |
| Are units present for numeric data where needed? | Money, weight, and duration have clear units |
| Does optionality match the contract? | `.optional()` is only used for fields that can truly be absent |
| Is nullability distinguished? | Description or schema explicitly states if null is accepted |
| Is the parent description repeated on every child field? | Each descriptor conveys its own meaning |
| Is unnecessary internal detail exposed? | Descriptions contain only client-appropriate information |
| Is the description too long? | Complex rules are moved to a dedicated section |

A snippet can be generated successfully even with terrible or vague descriptions. Therefore, content review of descriptions is still necessary alongside Spring REST Docs' technical checks.

## 9. Including snippets in the build and CI

Spring REST Docs typically generates AsciiDoc snippets. When using Gradle and the configured Asciidoctor plugin, the documentation task must depend on the snippet-generating test task:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

Build flow:

```text
MockMvc / WebTestClient / REST Assured tests
                  |
                  v
        requestFields descriptors
                  |
                  v
          request-fields.adoc
                  |
                  v
          Asciidoctor / HTML
                  |
                  v
            CI validation
```

If the team changes `fieldWithPath`, descriptions, or optional state, the snippet is regenerated when tests run. The CI build should verify both documentation tests and Asciidoctor rendering to avoid including stale files or missing snippets.

If the project requires Markdown, configure Markdown templates or a conversion step; do not assume `request-fields.md` is created out of the box.

## 10. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `requestFieldWithPath(...)` fails to compile | Used the wrong API name | Use `fieldWithPath(...)` inside `requestFields(...)` |
| Snippet reports missing field | Wrong path or required descriptor absent in sample request | Compare path against JSON; use `.optional()` if allowed by contract |
| Description repeats field name | Description does not explain business meaning | Write based on the field's role in the operation |
| Numeric description lacks units | Only wrote "Value" or "Quantity" | Add VND, grams, seconds, or the contract unit |
| Description is too long | Stuffed validation and policies into one sentence | Keep the core meaning; move long rules to separate docs |
| Table lacks a nullable column | Default template does not display this metadata | Write it in the description or customize the template |
| Tests run but docs are stale | Asciidoctor ran before tests or did not depend on output | Configure task dependency and snippet inputs |
| Documentation leaks internal details | Used descriptions from class, database, or internal variable names | Rewrite in the contract language clients need |

## 11. Hands-on exercise

Based on the create-order API:

1. Write descriptors for `customerId`, `items`, `items[].sku`, and `items[].quantity` with descriptions of at most one short sentence.
2. Add `amount` in VND. Write a description with the unit, e.g., `Order total amount, in VND`.
3. Add `note` as an optional field. Mark `.optional()` and clearly state that clients can omit it.
4. Create a `deliveryAddress.city` descriptor. Describe the delivery city instead of repeating the technical name.
5. Intentionally use `requestFieldWithPath(...)`, observe the compilation error, and then fix it to `fieldWithPath(...)`.
6. Run the test and open `request-fields.adoc`; review whether the descriptions are easy to understand for someone unfamiliar with the Java DTO structure.
7. Include the snippet in Asciidoctor and inspect the HTML generated after the tests finish.

### Self-check questions

- How do `fieldWithPath(...)` and `requestFields(...)` differ in role?
- Why is `requestFieldWithPath(...)` not a standard API name?
- What should a good description explain beyond the field name?
- When should units be included in a description?
- Are `.optional()` and nullability the same thing?
- Why does a passing snippet-generation test not prove the descriptions are good enough?

**Remember:** `fieldWithPath(...)` identifies a field's location in JSON; `requestFields(...)` uses those descriptors to generate the request payload table. Descriptions should be concise while answering what the field is, who it is for, or in what context it is used; add units and important rules where needed. Good descriptions turn snippets into documentation that API consumers can genuinely use.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): how to use `requestFields`, `fieldWithPath`, and payload snippets.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): descriptor type, description, optionality, and metadata.
