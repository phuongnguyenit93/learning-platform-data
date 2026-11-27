# Nullable Fields and Nullability in Spring REST Docs

## 1. Why is `null` not synonymous with an optional field?

In a REST API that accepts JSON, the following two questions have different meanings:

1. **Is the JSON key required to appear in the request?** This is *presence*, i.e., whether the field path is required or optional.
2. **If the key appears, is its value allowed to be JSON `null`?** This is *nullability*, i.e., whether `null` values are allowed.

For example, an API may require clients to always send the `externalReference` key, while allowing its value to be `null` when the order is not yet linked to an external system. Another field like `couponCode` may be **omitted**, yet if sent, it must be a valid string code and cannot be `null`.

In the **Request payload** chapter of **Spring REST Docs**, `fieldWithPath(...)` and `requestFields(...)` describe JSON fields on the tested HTTP request. `.optional()` controls the **field-can-be-absent** rule during snippet generation; it is **not** a nullable declaration. Documentation is generated from MockMvc, WebTestClient, or REST Assured tests, then compiled into Asciidoctor/Markdown and integrated into the build and CI to be regenerated whenever the API changes.

After this lesson, you will know how to:

- Distinguish **absent**, `null`, empty strings, empty objects, and empty arrays.
- Build a contract table based on two independent axes: **required** and **nullable**.
- Describe the type of a nullable field using `JsonFieldType`, `.type(...)`, and `.description(...)`.
- Write MockMvc tests that generate `request-fields.adoc` with both `null` values and omitted optional fields.
- Inspect JSON requests with Jackson; combine Bean Validation and negative tests to protect rules that cannot be verified by snippets alone.
- Organize nullability information in published documentation and the build/CI pipeline.

## 2. The required × nullable matrix: four distinct contracts

Let's use a JSON object containing only a `value` field to illustrate.

| Key required? | `null` allowed? | Valid payloads | Invalid payloads |
| --- | --- | --- | --- |
| Yes | No | `{ "value": "A" }` | `{}` or `{ "value": null }` |
| Yes | Yes | `{ "value": "A" }` or `{ "value": null }` | `{}` |
| No | No | `{}` or `{ "value": "A" }` | `{ "value": null }` |
| No | Yes | `{}`, `{ "value": "A" }`, or `{ "value": null }` | Values of wrong type/violating other constraints |

The matrix above describes an **assumed API contract**. Invalid cases are only rejected by the API when the application actually implements validation and has tests verifying it.

Spring REST Docs provides `.optional()` to describe the **may-be-absent axis**; a descriptor without `.optional()` is required under snippet generation rules. `FieldDescriptor` **has no standard `.nullable()` method** to automatically enforce whether `null` is valid. Therefore, you need to describe nullability in prose, in metadata/templates if you want a dedicated column, and in data-handling tests.

### An easily misunderstood example

```java
fieldWithPath("couponCode")
        .type(JsonFieldType.STRING)
        .description("Coupon code, can be omitted; if sent must be a string")
        .optional();
```

`.optional()` means that **omitting `couponCode`** still allows snippet generation to succeed. It does not mean `{"couponCode":null}` is valid under business rules. If a client sends `null`, the API must explicitly decide how to handle it and test that case separately.

```java
fieldWithPath("externalReference")
        .type(JsonFieldType.STRING)
        .description("Key must always be sent; value may be null when no external reference exists yet");
```

This descriptor **does not have** `.optional()` because the key must exist in the sample request. However, the contract allows a `null` value. To ensure the server requires this key to actually be present while permitting `null`, you must check it at the request-handling layer, because an ordinary Java DTO can collapse both *absent* and *explicit null* into the same Java `null` value.

## 3. Distinguishing absent, `null`, empty string, `{}`, and `[]`

Consider five simple requests:

**A — Key absent**

```json
{ "customerId": 42 }
```

**B — Key present with JSON null value**

```json
{ "customerId": 42, "note": null }
```

**C — Key present with empty string**

```json
{ "customerId": 42, "note": "" }
```

**D — Key present with empty object**

```json
{ "customerId": 42, "note": {} }
```

**E — Key present with empty array**

```json
{ "customerId": 42, "note": [] }
```

| Form | `note` key present? | JSON value type | Decision required |
| --- | --- | --- | --- |
| Absent | No | Does not exist | Is the client allowed to omit it? |
| `null` | Yes | `null` | Does null have a special meaning, or is it rejected? |
| `""` | Yes | String | Is an empty string valid? |
| `{}` | Yes | Object | Is an empty object the right type with sufficient properties? |
| `[]` | Yes | Array | Is an empty list allowed? |

**Do not treat these five forms as equivalent.** For instance, in a PATCH-style update API, **omitting a key** might mean "keep unchanged", while **a key with a null value** might mean "clear the value". However, that meaning depends on the PATCH style and specific contract; do not assume it applies automatically to every endpoint.

In particular, **"optional" does not imply "nullable"**, and **"nullable" does not imply "optional"**.

### How does Jackson help tell the difference?

When inspecting JSON requests, Jackson's `JsonNode` provides clear methods:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;

ObjectMapper mapper = new ObjectMapper();

JsonNode absent = mapper.readTree("{\"customerId\":42}");
JsonNode explicitNull = mapper.readTree(
        "{\"customerId\":42,\"note\":null}");
JsonNode emptyString = mapper.readTree(
        "{\"customerId\":42,\"note\":\"\"}");

assertFalse(absent.has("note"));
assertTrue(absent.path("note").isMissingNode());

assertTrue(explicitNull.has("note"));
assertTrue(explicitNull.get("note").isNull());

assertTrue(emptyString.has("note"));
assertTrue(emptyString.get("note").isTextual());
assertEquals("", emptyString.get("note").asText());
```

`has("note")` returns `true` when the field is present, **even when its value is `null`**. `hasNonNull("note")` returns `false` both when the field is absent and when its value is `null`, so **it cannot be used on its own to distinguish the two cases**.

```java
assertFalse(absent.hasNonNull("note"));
assertFalse(explicitNull.hasNonNull("note"));
assertTrue(emptyString.hasNonNull("note"));
```

Similarly, `path("note")` returns a `MissingNode` if the field is absent, but returns a `NullNode` if the JSON contains `note: null`. When testing for **true absence**, `isMissingNode()` is more accurate than comparing `.asText()` against an empty string.

## 4. What is `JsonFieldType.NULL`?

Spring REST Docs supports the `JsonFieldType` values: `STRING`, `NUMBER`, `BOOLEAN`, `OBJECT`, `ARRAY`, `NULL`, and `VARIES`. When no type is declared explicitly, the library tries to infer the type by inspecting the request payload under test.

Example:

```json
{
  "customerId": 42,
  "comment": null
}
```

The `comment` field currently has a JSON `null` value. With a sample request containing only this value, the inferred type may be displayed as `null` in the table. **That does not mean the field's contract only allows `null`**. Another request might send the string `"Pack carefully"`.

If the contract says `comment` is **string or null**, choose the base type explicitly:

```java
fieldWithPath("comment")
        .type(JsonFieldType.STRING)
        .description("Note; may be a string or null");
```

Note:

- `.type(JsonFieldType.STRING)` formats **the type recorded in the documentation**; it does not turn `null` into a string.
- `JsonFieldType.NULL` describes a JSON `null` value, **not a nullable flag** to combine with `STRING`.
- `JsonFieldType.VARIES` expresses a field with values of multiple types in observed payloads; this also **does not replace the API's nullability rules**.
- If the API only permits String or null, state that clearly in the description and test both valid and invalid forms.

An example with an array containing two value types:

```json
{ "labels": [null, "urgent"] }
```

When using the `labels[]` path, type inference depends on the observed elements; values of different types can change the documented type. For a contract with a known base type, declaring it explicitly and describing nullability prevents documentation from depending on a single sample payload. If the API does **not** allow null elements, add a test rejecting this example; a descriptor does not replace per-element validation.

## 5. Practical scenario: an order-creation API with multiple nullability patterns

Suppose `POST /api/orders` accepts:

```json
{
  "orderId": 710,
  "contact": {
    "email": "an@example.com",
    "phone": null
  },
  "externalReference": null,
  "couponCode": "WELCOME",
  "gift": {
    "message": null
  }
}
```

Illustrative contract rules:

| Field path | Required? | Nullable? | Rule |
| --- | --- | --- | --- |
| `orderId` | Yes | No | Numeric order ID |
| `contact` | Yes | No | Contact details object |
| `contact.email` | Yes | No | Non-blank email |
| `contact.phone` | No | Yes | Can be omitted; string or null |
| `externalReference` | Yes | Yes | Key must always be present; string or null |
| `couponCode` | No | No | Can be omitted; if sent must be a non-blank string |
| `gift` | No | Yes | Can be omitted; object or null |
| `gift.message` | No | Yes | Can be absent; if present, string or null |

Another valid payload under the example contract:

```json
{
  "orderId": 711,
  "contact": {
    "email": "binh@example.com"
  },
  "externalReference": null
}
```

In the second request, `contact.phone`, `couponCode`, and `gift` are all **absent**. Meanwhile, `externalReference` is still present with value `null`, because the contract defines it as **required + nullable**.

### Spring REST Docs descriptors

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_FIELDS = {
        fieldWithPath("orderId")
                .type(JsonFieldType.NUMBER)
                .description("Order ID, required and must not be null"),

        fieldWithPath("contact")
                .type(JsonFieldType.OBJECT)
                .description("Contact details, required and must not be null"),

        fieldWithPath("contact.email")
                .type(JsonFieldType.STRING)
                .description("Email, required and non-blank"),

        fieldWithPath("contact.phone")
                .type(JsonFieldType.STRING)
                .description("Phone number, can be omitted or sent as null")
                .optional(),

        fieldWithPath("externalReference")
                .type(JsonFieldType.STRING)
                .description("Key is required; value is string or null"),

        fieldWithPath("couponCode")
                .type(JsonFieldType.STRING)
                .description("Coupon code; can be omitted, but must not be null when sent")
                .optional(),

        fieldWithPath("gift")
                .type(JsonFieldType.OBJECT)
                .description("Gift details; can be omitted, object or null")
                .optional(),

        fieldWithPath("gift.message")
                .type(JsonFieldType.STRING)
                .description("Gift message; can be omitted, string or null")
                .optional()
};
```

The fields `contact.phone`, `couponCode`, `gift`, and `gift.message` all need `.optional()` because the sample JSON may omit them. `externalReference` is **not** marked optional because the contract requires that key to exist in the sample request, even though its value can be `null`.

**Important limitation:** Descriptors describe data and check whether fields are documented in the sample request. They do not automatically enforce all rules in the contract table above. In particular, `.type(JsonFieldType.STRING)` is not a non-null validator, and `.optional()` is not permission to send null.

## 6. MockMvc tests with `null` and absent fields

The example below assumes the project has Spring Boot 3.x, Java 17, JUnit 5, Spring REST Docs, and that the `POST /api/orders` endpoint is implemented to return **HTTP 201 Created** for the two valid payloads in section 5.

Test dependencies typically include:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

The test uses `@AutoConfigureRestDocs` to generate snippets in `build/generated-snippets`:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderNullabilityDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private static final FieldDescriptor[] ORDER_FIELDS = {
            fieldWithPath("orderId")
                    .type(JsonFieldType.NUMBER)
                    .description("Order ID; required, non-null"),
            fieldWithPath("contact")
                    .type(JsonFieldType.OBJECT)
                    .description("Contact details; required, non-null"),
            fieldWithPath("contact.email")
                    .type(JsonFieldType.STRING)
                    .description("Email, required and non-blank"),
            fieldWithPath("contact.phone")
                    .type(JsonFieldType.STRING)
                    .description("Phone number; optional, nullable")
                    .optional(),
            fieldWithPath("externalReference")
                    .type(JsonFieldType.STRING)
                    .description("Key always required; string or null"),
            fieldWithPath("couponCode")
                    .type(JsonFieldType.STRING)
                    .description("Optional; if sent must be a non-blank string")
                    .optional(),
            fieldWithPath("gift")
                    .type(JsonFieldType.OBJECT)
                    .description("Gift object, optional and nullable")
                    .optional(),
            fieldWithPath("gift.message")
                    .type(JsonFieldType.STRING)
                    .description("Message, optional and nullable")
                    .optional()
    };

    @Test
    void documentOrderWithExplicitNullValues() throws Exception {
        String json = """
                {
                  "orderId": 710,
                  "contact": {
                    "email": "an@example.com",
                    "phone": null
                  },
                  "externalReference": null,
                  "couponCode": "WELCOME",
                  "gift": {
                    "message": null
                  }
                }
                """;

        JsonNode root = objectMapper.readTree(json);
        assertTrue(root.path("contact").has("phone"));
        assertTrue(root.path("contact").path("phone").isNull());
        assertTrue(root.has("externalReference"));
        assertTrue(root.path("externalReference").isNull());
        assertTrue(root.path("gift").path("message").isNull());

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-nullability-explicit-null",
                        requestFields(ORDER_FIELDS)));
    }

    @Test
    void documentOrderWithOptionalFieldsAbsent() throws Exception {
        String json = """
                {
                  "orderId": 711,
                  "contact": {
                    "email": "binh@example.com"
                  },
                  "externalReference": null
                }
                """;

        JsonNode root = objectMapper.readTree(json);
        assertFalse(root.path("contact").has("phone"));
        assertFalse(root.has("couponCode"));
        assertFalse(root.has("gift"));
        assertTrue(root.has("externalReference"));
        assertTrue(root.path("externalReference").isNull());

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-nullability-absent",
                        requestFields(ORDER_FIELDS)));
    }
}
```

When both the HTTP status and documentation checks succeed, Spring REST Docs creates directories matching the two snippet names:

```text
build/generated-snippets/
├── orders-nullability-explicit-null/
│   └── request-fields.adoc
└── orders-nullability-absent/
    └── request-fields.adoc
```

There are usually other snippets such as `http-request.adoc`, `http-response.adoc`, and `curl-request.adoc`, depending on project configuration. Use two distinct names to keep the **explicit null** and **absent** examples separate.

In both tests, `requestFields(ORDER_FIELDS)` shares the same descriptors while using different test data. Running Jackson assertions before `mockMvc.perform(...)` **proves directly in the test** whether the outgoing payload contains `null` values or actually omits keys, rather than relying only on prose descriptions.

### What else needs to be tested?

The two passing tests do not yet prove that:

- The API rejects `couponCode: null` when the contract states it is non-nullable.
- The API rejects a request **missing the `externalReference` key** when that key is required.
- The API rejects `contact: null` or `contact.email: null`.
- The API handles `gift: null` and `gift: {}` according to the contract.
- The API distinguishes a PATCH with a null key from one without the key if this is an update endpoint.

These cases require separate HTTP tests expecting errors or success per the contract.

## 7. When do you need validation and key-presence checks?

### 7.1. Bean Validation handles many non-null rules well

With Jakarta Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record OrderRequest(
        @NotNull Long orderId,
        @NotNull @Valid ContactRequest contact,
        String externalReference,
        String couponCode,
        @Valid GiftRequest gift
) {}

record ContactRequest(
        @NotBlank @Email String email,
        String phone
) {}

record GiftRequest(String message) {}
```

In the controller, when receiving `@Valid @RequestBody OrderRequest request`, validation can ensure:

- `orderId` and `contact` are not Java `null` after binding.
- `contact.email` is non-blank and matches email format according to the annotations used.
- `contact.phone`, `gift`, and `gift.message` may be null unless further constrained.

However, **`externalReference` is "required + nullable"**: `String externalReference` in an ordinary record receives Java `null` for both JSON missing the key and JSON with `"externalReference": null`. Hence, simply using `@NotNull` would **violate** the contract, while declaring no constraint fails to check key presence.

### 7.2. Checking required + nullable at the JSON object level

To distinguish **absent** and **explicit null** before binding, you can inspect `JsonNode` or use a presence-tracking deserialization mechanism:

```java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

void requireExternalReferenceKey(JsonNode requestBody) {
    if (!requestBody.has("externalReference")) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "externalReference must be present, even when null"
        );
    }
}
```

This method illustrates the **presence** check. A real application integrates it in a controller, deserializer, or input-validation layer while also enforcing other constraints before processing the order. If using OpenAPI or JSON Schema, you can list the field in `required` while also allowing a `null` type, and verify with an appropriate validator.

### 7.3. Checking optional but non-null when present

For `couponCode`, the contract allows omitting it while rejecting `null`:

```java
void requireNonNullWhenPresent(JsonNode requestBody) {
    if (requestBody.has("couponCode")
            && requestBody.path("couponCode").isNull()) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "couponCode must not be null when supplied"
        );
    }
}
```

If the contract also requires a non-blank String matching a coupon format, additionally check `isTextual()`, content, and business rules. Do not treat `.type(JsonFieldType.STRING)` in REST Docs as enforcing those conditions.

### 7.4. Negative tests

Once the application implements these rules, you should have tests such as:

| Request sent to endpoint | Expected result per example contract |
| --- | --- |
| Missing `orderId` | HTTP 400 |
| `"contact": null` | HTTP 400 |
| `"contact": { "email": null }` | HTTP 400 |
| Missing `externalReference` | HTTP 400 |
| `"externalReference": null` | HTTP 201 |
| Missing `couponCode` | HTTP 201 |
| `"couponCode": null` | HTTP 400 |
| Missing `gift` | HTTP 201 |
| `"gift": null` | HTTP 201 if allowed by contract |

The HTTP status codes in the table are **illustrative expectations**; they only occur when the endpoint implements validation and corresponding error mapping. Spring REST Docs does not automatically return HTTP 400 when it detects unexpected descriptors or documented types.

## 8. Nullable objects and nullable array elements

### 8.1. Parent object can be null, child field can disappear

Consider:

```json
{
  "gift": null
}
```

And:

```json
{
  "gift": {
    "message": null
  }
}
```

In the first payload, `gift` is present with value `null`, but `gift.message` cannot be resolved as a nested object path. If the `gift.message` descriptor is also used for this payload, it must be marked optional for that scenario or documented in a separate snippet.

In the second payload, the `gift` object is present and the child field `message` is also present with value `null`.

```java
fieldWithPath("gift")
        .type(JsonFieldType.OBJECT)
        .description("Gift details, can be omitted or null")
        .optional();

fieldWithPath("gift.message")
        .type(JsonFieldType.STRING)
        .description("Message, can be omitted or null")
        .optional();
```

If the API requires `message` whenever `gift` is an object, `.optional()` in a shared snippet cannot fully express that condition. In that case, also test `{ "gift": {} }` and verify the API responds properly.

### 8.2. Null array elements

Example:

```json
{
  "contacts": [
    { "type": "EMAIL", "value": "an@example.com" },
    null
  ]
}
```

`contacts` is an array, yet not every element is an object. Although the `contacts[].type` descriptor may find data in this sample request, that does not automatically mean the second element is valid.

If the contract **forbids null in the list**, use Bean Validation with an element constraint and a corresponding test:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;

record ContactListRequest(
        List<@NotNull @Valid ContactItem> contacts
) {}

record ContactItem(String type, String value) {}
```

When the controller enables validation, the `@NotNull` constraint on each element rejects null elements. You can add `@NotEmpty` to the list itself if at least one element is required. Keep in mind the validation dependency requirements and container-element constraint support for your framework version.

If the API **allows null elements**, the documentation must explain the meaning of null and test scenarios with varied elements. Do not use an object element descriptor that misleads readers into assuming the list is always uniform when the contract allows null elements.

## 9. Displaying nullability in the documentation table

By default, `requestFields(...)` generates a table with information such as `Path`, `Type`, and `Description`, depending on the snippet template. **Do not assume a "Nullable" column is available by default**. There are two practical options:

### 9.1. State it explicitly in `.description(...)`

```java
fieldWithPath("externalReference")
        .type(JsonFieldType.STRING)
        .description("Key is required; null allowed");

fieldWithPath("couponCode")
        .type(JsonFieldType.STRING)
        .description("Optional; if sent must be a non-null string")
        .optional();
```

This is simple, readable, and works with the default template.

### 9.2. Attach metadata to customize the template

Spring REST Docs allows adding attributes to descriptors via `.attributes(...)`. For example:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("externalReference")
        .type(JsonFieldType.STRING)
        .description("External reference ID")
        .attributes(key("nullable").value("Yes"));

fieldWithPath("couponCode")
        .type(JsonFieldType.STRING)
        .description("Coupon code")
        .optional()
        .attributes(key("nullable").value("No"));
```

You can then customize the REST Docs `request-fields` template to read the `nullable` attribute and display a corresponding column. **Custom attributes do not appear automatically** in snippets if the active template does not reference them. If you also want a "Required" column, align how optionality is rendered in the template as well.

For client-facing documentation, displaying both properties clearly is recommended:

| Field | Required | Nullable | Type |
| --- | --- | --- | --- |
| `externalReference` | Yes | Yes | String |
| `couponCode` | No | No | String |
| `gift` | No | Yes | Object |
| `contact.email` | Yes | No | String |

When changing a field from nullable to non-nullable, update the contract, validation, tests, and snippets together.

## 10. Including snippets in Asciidoctor and CI

Example source document `src/docs/asciidoc/api.adoc`:

```adoc
= Orders REST API
:toc: left

== Create order

=== Request for fields with null values
include::{snippets}/orders-nullability-explicit-null/http-request.adoc[]

=== Request when optional fields are omitted
include::{snippets}/orders-nullability-absent/http-request.adoc[]

=== Request field descriptions
include::{snippets}/orders-nullability-explicit-null/request-fields.adoc[]
```

The `{snippets}` attribute must point to `build/generated-snippets` or wherever tests store their output. With Gradle and the Asciidoctor plugin configured:

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

The verification chain should be:

```text
Build / CI
    |
    v
HTTP tests (MockMvc / WebTestClient / REST Assured)
    |
    v
Spring REST Docs generates request-fields.adoc
    |
    v
Asciidoctor renders HTML
    |
    v
Publish documentation
```

If the project needs to output **Markdown**, use appropriate snippet templates or a conversion step from AsciiDoc; this example does not create `request-fields.md` by default. Documentation test failures must fail the build to avoid publishing a field table out of sync with the tested payload.

## 11. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Table shows type `null` for a field that is actually String or null | REST Docs inferred the type from a sample request containing only `null` | Set `.type(JsonFieldType.STRING)` and explain nullability |
| Used `.optional()` to assert nullability | Confused the presence axis with nullability | State nullability in the description and add tests sending `null` |
| Documentation test passes yet API accepts `couponCode: null` against contract | Missing non-null check when key is present | Add validation/checking logic and negative tests |
| DTO does not distinguish absent `externalReference` from explicit null | Both deserialize to Java `null` | Inspect `JsonNode.has`, use a custom deserializer, or track presence |
| `gift: null` causes `gift.message` descriptor to fail as missing | Child path does not exist when parent object is null | Mark child descriptors optional or separate documentation scenarios |
| Array has null element yet server accepts it | No per-element constraint | Use a container-element constraint and test requests with null |
| Documentation lacks a nullable column | Default snippet template does not use `nullable` metadata | Write it in the description or customize the template |
| `JsonFieldType.NULL` mistaken for "nullable string" | Confused an observed JSON value with the type contract | Distinguish literal null from a nullable string/object |
| Used `jsonPath(...).doesNotExist()` to verify absent request field | That is a **response** matcher with special null semantics | Inspect the request body with Jackson or request assertions |
| `request-fields.adoc` not found | Did not pass `requestFields(...)` to `document(...)` or wrong output path | Check REST Docs configuration and snippet output directory |

## 12. Hands-on exercise and self-check

Start from the MockMvc test in section 6.

1. **Required + nullable:** remove the `externalReference` key from the JSON while keeping its descriptor without `.optional()`. Observe the documentation step failure; then add an HTTP test ensuring the server rejects requests missing the key.
2. **Optional + non-nullable:** add `"couponCode": null` in a sample request. Write a test expecting an error per the contract after adding validation; explain why `.optional()` does not reject null.
3. **Inspect with Jackson:** run `has`, `hasNonNull`, `isNull`, and `isMissingNode` assertions on JSON with `"phone": null` and JSON without `phone`. Write a one-line explanation for each result.
4. **Nullable object:** send `"gift": null`, then send `"gift": {"message": null}`. Compare the presence of the `gift.message` path and test results.
5. **Nullable array element:** try adding `null` to `contacts` and add a `List<@NotNull ...>` constraint to demonstrate the endpoint rejects null elements when required by the contract.
6. **Documentation:** add a nullable column via metadata/template or state it clearly in the description. Generate snippets, include them in Asciidoctor, and verify both `null` and `absent` examples appear in the HTML documentation.

### Self-check questions

- How does a **required + nullable** field differ from an **optional + non-nullable** field?
- Why is `JsonFieldType.NULL` not a nullable flag?
- Why does `.optional()` not replace tests that send `null`?
- When do `JsonNode.has("phone")` and `JsonNode.hasNonNull("phone")` return different results?
- Why does a Java record with a `String` field typically fail to distinguish JSON absent from explicit null?
- In a build/CI workflow, how do you prevent nullability changes from making documentation stale?

**Remember:** In Spring REST Docs, `.optional()` answers **"can this field be absent from the JSON?"**, whereas *nullability* answers **"when present, can this field carry a JSON `null` value?"**. These two properties are independent. Combining `requestFields` descriptions, `JsonFieldType` types, JSON assertions, validation, and HTTP tests keeps REST API documentation clear and verifiable in the build/CI.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, optional fields, and JSON type inference.
- [Spring REST Docs — FieldDescriptor](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `type(Object)`, `optional()`, and field metadata.
- [Spring REST Docs — JsonFieldType](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/JsonFieldType.html): `NULL`, `STRING`, `VARIES`, and other types.
