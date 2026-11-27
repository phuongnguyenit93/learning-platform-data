# `ignore` and Fields That Do Not Need Operation-Level Documentation in Spring REST Docs

## 1. The problem: a payload has many fields, but the operation only needs to describe some

A REST API may receive JSON containing business data alongside metadata for operations, tracing, backward compatibility, or client-version extensions. API consumers need to understand fields like `customerId` and `items`, but they do not necessarily need separate rows for `clientTraceId`, `legacySource`, or `internalFlags` in every operation's request fields table.

For example, `POST /api/orders` receives:

```json
{
  "customerId": 42,
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ],
  "clientTraceId": "trace-7f91",
  "legacySource": "mobile-v1",
  "internalFlags": {
    "migration": false
  }
}
```

With **Spring REST Docs**, there are three common choices:

- `.ignored()` on `FieldDescriptor`: recognizes a known field while excluding it from the fields snippet table.
- `relaxedRequestFields(...)`: documents part of the payload and permits other fields without descriptors.
- Not calling `requestFields(...)` if the operation does not need a field-by-field table; you can include only the HTTP request or request body in the documentation.

These three choices affect payload verification differently. Choosing the right mechanism keeps the documentation focused on what API consumers need, while preserving useful checks on the request contract.

## 2. `.ignored()` in `FieldDescriptor`

`fieldWithPath(...)` creates a descriptor for a JSON path. Call `.ignored()` to mark a descriptor so it does not appear in the fields snippet.

```java
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Correlation ID used for tracing")
        .ignored();
```

When the descriptor is passed to `requestFields(...)`, the `clientTraceId` field is recognized in the documentation configuration, yet does not become a row in `request-fields.adoc`.

Example:

```java
requestFields(
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
        .description("Quantity"),
    fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Technical trace ID")
        .ignored()
);
```

The snippet table presents the published descriptors; `clientTraceId` does not appear in the table.

### 2.1. Ignore does not mean optional

These two methods answer two independent questions:

| Method | Question | Effect |
| --- | --- | --- |
| `.ignored()` | Should the descriptor be displayed in the snippet? | Hides the field from display |
| `.optional()` | Is the descriptor allowed to be absent in the sample payload? | Allows the field to be absent during documentation |

If the field is always present in the payload but does not need to be published, `.ignored()` is sufficient. If a technical field may or may not appear depending on the client, combine both:

```java
fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Client-supplied trace ID")
        .optional()
        .ignored();
```

In this case, `.optional()` allows the field to be absent from the sample request; `.ignored()` keeps the field out of the fields table when it does appear. Do not add `.optional()` solely to silence a test failure if the actual contract requires the field to always be present.

### 2.2. Ignoring an object or a branch

A technical branch can be treated as a single unit:

```json
{
  "internalFlags": {
    "migration": false,
    "sourceRegion": "ap-southeast"
  }
}
```

```java
fieldWithPath("internalFlags")
        .type(JsonFieldType.OBJECT)
        .description("Internal operational metadata")
        .ignored();
```

When you only want to skip an entire branch, you can declare the descriptor at the object level. If some child fields still need to appear in the documentation, design the descriptors at that level of detail rather than ignoring the entire parent object.

### 2.3. When should you use it?

| Scenario | Example | Recommended approach |
| --- | --- | --- |
| Known technical field, no need to explain to clients | `clientTraceId` | `.ignored()` |
| Legacy field still accepted for compatibility | `legacySource` | `.ignored()` if it does not need to be published on this operation |
| Field may be missing, and if present still need not be shown | `clientTraceId` | `.optional().ignored()` |
| Field with business meaning to clients | `couponCode`, `deliveryMode` | Document fully, do not ignore |
| Sensitive or secret field | `internalToken` | Review the contract and data transmission; `.ignored()` is not a security measure |

Do not use `.ignored()` to hide an important field simply because a descriptor is missing or a test is failing. If clients need to know a field can be sent, its data type, and its constraints, document that field.

## 3. Comparing strict fields, ignored fields, and relaxed fields

### 3.1. `requestFields(...)`: strict checking

```java
requestFields(
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("items").description("List of items")
)
```

With `requestFields(...)`, Spring REST Docs checks the payload against the descriptors. In strict mode, a field present in JSON without a description can cause snippet generation to fail. This is a useful signal when the team wants every new field reviewed before updating documentation.

### 3.2. `requestFields(...)` combined with `.ignored()`

```java
requestFields(
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("items").description("List of items"),
    fieldWithPath("clientTraceId")
        .description("Technical trace ID")
        .ignored()
)
```

The known field is explicitly declared in the operation and omitted from the table. Strict mode still serves to catch any other unhandled fields. This approach works well when only a few known technical fields need to be excluded from the table.

### 3.3. `relaxedRequestFields(...)`: allowing undeclared fields

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
    fieldWithPath("customerId").description("Customer ID"),
    fieldWithPath("items").description("List of items")
)
```

`relaxedRequestFields(...)` is appropriate when an operation only documents part of the payload and accepts other fields without descriptors. For example, a `preferences` object designed as an extensible map where new keys may appear across client versions.

Declared descriptors still retain their own presence rules. If a required descriptor is absent from the sample payload, use `.optional()` when the contract allows it.

### 3.4. Comparison table

| Mechanism | Declared fields | Payload fields not yet declared | Displayed fields |
| --- | --- | --- | --- |
| `requestFields(...)` | Checked against descriptors | Can cause snippet generation to fail | Yes, except ignored descriptors |
| `requestFields(...)` + `.ignored()` | Recognized but excluded from table | Still caught by strict mode | Only non-ignored fields |
| `relaxedRequestFields(...)` | Described per descriptors | Allowed to exist | Only declared descriptors |
| No fields snippet generated | No field-level check via this snippet | No field-level check via this snippet | No table |

Selection rules:

- Use `.ignored()` when you know exactly which fields do not need publishing, yet still want strict mode to catch other extra fields.
- Use `relaxedRequestFields(...)` when the payload has an extensible section that cannot be enumerated upfront and that is an intentional part of the contract.
- Do not call `requestFields(...)` if the operation does not require a field-level table; use a sample request or body snippet when appropriate.

## 4. Example operation with technical metadata

Suppose the create-order endpoint has the following contract:

- `customerId` and `items` are business data that must be published.
- `clientTraceId`, `legacySource`, and `internalFlags` are known technical metadata that do not need to appear in the table.
- Any new field not yet reviewed by the team must be caught in strict mode.

### 4.1. Declaring descriptors

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
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

    fieldWithPath("clientTraceId")
        .type(JsonFieldType.STRING)
        .description("Log correlation ID")
        .ignored(),
    fieldWithPath("legacySource")
        .type(JsonFieldType.STRING)
        .description("Legacy client source name")
        .ignored(),
    fieldWithPath("internalFlags")
        .type(JsonFieldType.OBJECT)
        .description("Internal flags")
        .ignored()
};
```

If `legacySource` may be absent in some requests, the descriptor can be written as:

```java
fieldWithPath("legacySource")
    .type(JsonFieldType.STRING)
    .description("Legacy client source name")
    .optional()
    .ignored()
```

### 4.2. MockMvc test

The example assumes the project already has Spring Boot, JUnit 5, MockMvc, and the `spring-restdocs-mockmvc` dependency; the `/api/orders` endpoint returns `201 Created` for valid payloads.

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
class OrderIgnoredFieldsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentPublicFieldsAndIgnoreTechnicalFields() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ],
                  "clientTraceId": "trace-7f91",
                  "legacySource": "mobile-v1",
                  "internalFlags": {
                    "migration": false
                  }
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-create-public-fields",
                        requestFields(ORDER_REQUEST_FIELDS)));
    }
}
```

After the HTTP test and snippet generation succeed, `request-fields.adoc` only shows the business descriptors. Ignored fields do not become rows in the table.

If `newClientOption` is added to the JSON without changing descriptors, strict `requestFields(...)` can detect the unhandled field. The team needs to decide whether to document it, intentionally ignore it, or update the contract. Do not automatically switch the whole operation to relaxed mode just to make the build green.

### 4.3. Ignoring does not make a field safe

`.ignored()` only affects the documentation snippet. It does not:

- Remove the field from the HTTP request.
- Prevent the application from reading or storing the field.
- Mask the field in logs, tracing, or databases.
- Encrypt or protect sensitive data.
- Control client authorization to send the field.

If a field holds tokens, personal data, or secret values, design the contract, authentication, authorization, logging, and storage securely. Hiding a row in `request-fields.adoc` is not a security control.

## 5. Operations without a fields table: documenting only the request body

Not every operation needs a field-by-field table. An endpoint might accept an opaque payload, pass-through data, or content defined in a separate schema or document.

If an operation only needs to illustrate the body, you can use the body snippet without calling `requestFields(...)`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestBody;

mockMvc.perform(post("/api/imports")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json))
    .andExpect(status().isAccepted())
    .andDo(document("imports-create",
        requestBody()
    ));
```

`requestBody()` generates a snippet of the request body content; it does not produce a path/type/description table like `requestFields(...)`. When only an HTTP example is needed, an operation can also use `http-request.adoc` and skip a separate body snippet if that content is already sufficient.

The Asciidoctor source can include:

```adoc
== Import data

=== HTTP request
include::{snippets}/imports-create/http-request.adoc[]

=== Request body
include::{snippets}/imports-create/request-body.adoc[]
```

Check the configuration and version of Spring REST Docs in use to confirm snippets are generated with the exact names and format included by the documentation. If clients need to know the meaning of each field, a sample body alone is insufficient; provide a `requestFields(...)` table or a clearly linked schema.

## 6. When to use `relaxedRequestFields(...)`?

Suppose an API has a `preferences` object that allows key extensions:

```json
{
  "customerId": 42,
  "preferences": {
    "newsletter": true,
    "theme": "dark",
    "futureFlag": "enabled"
  }
}
```

Currently the operation only wants to publish `customerId` and `preferences.newsletter`, while other properties are designed to expand across client versions:

```java
relaxedRequestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    fieldWithPath("preferences.newsletter")
        .description("Whether to receive the newsletter")
)
```

Fields such as `preferences.theme` and `preferences.futureFlag` are allowed to be present even without descriptors. This is a suitable choice for extensible maps or multi-version payloads.

In return, a new field can appear without causing the snippet to fail. Therefore:

- Only use relaxed mode when extensibility is an intentional part of the contract.
- Clearly document which section has an open schema and where clients can find its rules.
- Write dedicated tests for critical keys, valid values, and limits.
- Do not use relaxed mode for an entire public payload if the team wants to catch every schema change.

### Comparison with wildcards

If the extensible portion is a map of uniform type, you can use `fieldWithPath("attributes.*")` to describe dynamic child keys, depending on the JSON structure. Wildcards describe a known group of paths; relaxed mode permits undeclared fields. These two approaches do not replace each other in every situation.

## 7. Fields that do not need documentation in one operation

Descriptors belong to the snippet of a specific operation. A field might be documented on a telemetry endpoint while being ignored on the create-order endpoint. That makes sense if the field's meaning and contract are documented in another easy-to-find location.

| Operation need | Approach | Result |
| --- | --- | --- |
| Important field clients must know | `fieldWithPath(...).description(...)` | Row appears in the table |
| Known field that does not need to be shown | `.ignored()` | Recognized, no row in the table |
| Field that may be absent and need not be shown | `.optional().ignored()` | May be absent and is not displayed |
| Accept unlisted extra fields | `relaxedRequestFields(...)` | No descriptor needed for extra fields |
| Only need a body example | `requestBody()` or HTTP request snippet | No field-level table |
| Out-of-contract field still sent by clients | Review contract, deprecate, or reject per policy | Avoid hiding unsupported data |

There is no rule that a field must be documented identically in every operation. However, if clients rely on a field to build valid requests, documentation in at least one easy-to-find place must explain its meaning, scope, and support status.

## 8. Common errors and how to fix them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Technical field still appears in the table | Forgot `.ignored()` or passed the wrong descriptor | Mark the specific descriptor with `.ignored()` |
| Test reports an undocumented field | Strict mode encountered an extra field | Add a descriptor, ignore the known field, or intentionally use relaxed mode |
| `.ignored()` mistaken for allowing a missing field | Confused hiding a row with optionality | Add `.optional()` if the field may be absent |
| Relaxed mode lets a new field slip through | Extra fields are intentionally permitted | Use relaxed only for extensible parts; add separate tests |
| No fields table even though per-field meanings are needed | Only generated `requestBody()` | Add `requestFields(...)` or a dedicated schema |
| Used ignore to hide a sensitive field | Assumed omission from snippet equals security | Review request handling, logging, authorization, and storage |
| Table lacks child field details | Documented only the parent object or ignored the whole branch | Declare child descriptors that need to be published |
| `request-body.adoc` not found | Body snippet not generated or different output name | Check `requestBody()`, output directory, and snippet name |

## 9. Including snippets in Asciidoctor and CI

After snippet-generating tests pass, Asciidoctor documentation can include both the fields table and body snippets:

```adoc
= Orders API
:toc: left

== Create order

=== Public request fields
include::{snippets}/orders-create-public-fields/request-fields.adoc[]

=== Request body of the import operation
include::{snippets}/imports-create/request-body.adoc[]
```

With Gradle and the Asciidoctor plugin configured, the documentation task must depend on the snippet-generating tests:

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

Typical CI flow:

```text
HTTP tests
   |
   v
Spring REST Docs snippets
   |
   v
Asciidoctor / Markdown conversion step
   |
   v
Validate and publish documentation
```

If a strict snippet fails due to a new field, the team must decide whether that field should be published, intentionally ignored, or whether the contract is expanding. Do not switch all `requestFields` to `relaxedRequestFields` just to get a green build, as that loses the signal that detects payload changes.

Spring REST Docs typically generates AsciiDoc snippets by default. If the project needs Markdown, configure the appropriate Markdown templates or conversion step; do not assume a `request-fields.md` file exists by default.

## 10. Hands-on exercise

Using the create-order endpoint in section 4:

1. Add a String field `clientVersion` to the payload and a `.ignored()` descriptor. Run the test and verify the field does not appear in `request-fields.adoc`.
2. Remove `clientTraceId` from the sample request, add `.optional().ignored()`, run the test, and confirm the descriptor still works.
3. Add `unexpectedFlag` without a descriptor. Observe strict `requestFields(...)` catching the new field; decide whether to document, ignore, or reject it.
4. Create an import operation that only needs a sample body, use `requestBody()`, and include the snippet in Asciidoctor. Compare it with a fields table.
5. Use `relaxedRequestFields(...)` for an extensible `preferences` object. Add a new key and observe how it differs from strict mode.
6. Examine a simulated sensitive field. Explain why `.ignored()` does not protect the data from requests, logs, or storage systems.

### Self-check questions

- What problem does `.ignored()` solve? Does it make a field optional?
- Which two properties does `.optional().ignored()` combine?
- How does `relaxedRequestFields(...)` differ from `requestFields(...)` when the payload has undeclared fields?
- When an operation does not need a fields table, which snippet can provide the request body?
- Why does ignoring a sensitive field not make sending or logging that field safe?
- In CI, when a strict snippet fails because of a new field, what should the team review before changing the checking mode?

**Remember:** `.ignored()` lets you recognize a known field while keeping it out of the snippet table; `.optional()` allows a field to be absent from the sample payload; `relaxedRequestFields(...)` permits unlisted fields; and `requestBody()` is suitable when only the body content is needed. Choose the mechanism according to the operation's goal so documentation stays focused while retaining useful verification signals.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `relaxedRequestFields`, `requestBody`, and payload descriptions.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): descriptors, `.ignored()`, and `.optional()`.
