# Intentionally ignoring response fields in Spring REST Docs

## 1. The role of ignore in payload documentation

In the **Response payload** chapter of the **SPRING_REST_DOCS** module, JSON responses may contain both public data and technical metadata. Clients need to know the order ID, status, and total amount, whereas an internal trace ID, processing node name, diagnostic timing, or cache flags may not belong in the contract you want to publish.

Example:

```json
{
  "id": "ORD-9001",
  "status": "CONFIRMED",
  "totalAmount": 250000,
  "internalTraceId": "trace-7a91",
  "debug": {
    "sourceNode": "node-03",
    "timingMs": 12,
    "flags": {"cacheHit": true}
  }
}
```

Spring REST Docs provides `FieldDescriptor.ignored()` to mark a known path so it is intentionally omitted from the `response-fields.adoc` table. Use `fieldWithPath("internalTraceId").ignored()` for a single field or `subsectionWithPath("debug").ignored()` to exclude an entire branch.

**Scope:** ignoring is a snippet documentation decision. It does not strip fields from the HTTP response, hide data bytes, change serialization, or provide security.

## 2. Basic syntax

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    fieldWithPath("totalAmount").description("Total amount in VND"),
    fieldWithPath("internalTraceId").ignored()
)
```

The `id`, `status`, and `totalAmount` fields are displayed. `internalTraceId` is recognized as an intentionally ignored field and does not appear as a regular description row. Explicit declaration lets reviewers see that the field was consciously evaluated.

Example inside a MockMvc test:

```java
.andDo(document("orders-get",
    responseFields(
        fieldWithPath("id").description("Order identifier"),
        fieldWithPath("status").description("Order processing status"),
        fieldWithPath("totalAmount").description("Total amount in VND"),
        fieldWithPath("internalTraceId").ignored()
    )
))
```

In strict mode of `responseFields(...)`, payload fields must be either documented or intentionally handled. Do not ignore all fields just to keep a few rows without evaluating the contract impact.

## 3. Distinguishing ignore, optional, and relaxed

| Mechanism | Purpose | Included in table? | Meaning |
| --- | --- | --- | --- |
| Default `fieldWithPath(...)` | Document field | Yes | Field is described; missing required fields or undocumented fields can fail the test |
| `optional()` | Allow a documented field to be absent | Yes if present in fixture | Relaxes the requirement for the path to exist in the sample response |
| `ignored()` | Recognize field without publishing it in the table | No | Intentionally excludes the field from the snippet |
| `relaxedResponseFields(...)` | Document part of a payload | Only declared fields | Allows unlisted fields |

### 3.1. Ignore does not mean optional

If a field is always present but does not need to be published, use:

```java
fieldWithPath("internalTraceId").ignored()
```

If a field may be absent, yet clients need to understand its meaning when present, use:

```java
fieldWithPath("deliveryNote")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Delivery note, may be absent");
```

`optional()` is about path presence. `ignored()` is about omitting a field's description from the table. Do not substitute one for the other just to make tests pass.

### 3.2. Ignore vs. relaxed

When you know exactly which debug branch to exclude:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    subsectionWithPath("debug").ignored()
)
```

When you only want to describe part of a response and allow other unlisted fields:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status")
)
```

Relaxed mode is useful for partial documentation, but new fields can appear without failing tests. If only a few specific paths should be omitted from publication, strict mode paired with ignored descriptors makes reviews clearer.

## 4. Ignoring nested objects

Payload:

```json
{
  "id": "ORD-9001",
  "status": "CONFIRMED",
  "debug": {
    "sourceNode": "node-03",
    "timingMs": 12,
    "flags": {"cacheHit": true}
  }
}
```

You can ignore the entire branch:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    subsectionWithPath("debug").ignored()
)
```

A subsection descriptor signals the intent to exclude `debug` and all its descendants from the table. If the branch contains a public field, do not ignore the entire object. Select specific paths instead:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    subsectionWithPath("debug")
        .description("Support information exposed to clients"),
    fieldWithPath("debug.requestId")
        .description("Request ID for contacting support"),
    fieldWithPath("debug.internalTraceId").ignored(),
    fieldWithPath("debug.sourceNode").ignored()
)
```

Only use this approach if `debug.requestId` truly belongs to the public contract. The parent object's name does not automatically determine whether every child field is public or internal.

## 5. Ignoring fields in repeating arrays

Response:

```json
{
  "items": [
    {
      "sku": "BK-01",
      "quantity": 2,
      "warehouseCode": "HCM-01",
      "stockSnapshot": 18
    },
    {
      "sku": "BK-02",
      "quantity": 1,
      "warehouseCode": "HAN-02",
      "stockSnapshot": 7
    }
  ]
}
```

Document the fields clients need and ignore internal metadata inside each element:

```java
responseFields(
    fieldWithPath("items").description("List of line items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    fieldWithPath("items[].quantity").description("Product quantity"),
    fieldWithPath("items[].warehouseCode").ignored(),
    fieldWithPath("items[].stockSnapshot").ignored()
)
```

The path still needs `[]` because `items` is an array. If an entire internal branch on each element should be ignored:

```json
{
  "items": [
    {
      "sku": "BK-01",
      "internal": {
        "source": "ERP",
        "syncBatch": "B-2026-11"
      }
    }
  ]
}
```

```java
responseFields(
    fieldWithPath("items").description("Line items"),
    fieldWithPath("items[].sku").description("Product SKU"),
    subsectionWithPath("items[].internal").ignored()
)
```

With an `"items": []` fixture, child paths have no representative element. Use a non-empty fixture for structural documentation tests and test empty arrays separately.

## 6. Complete MockMvc example

The example uses JUnit Jupiter, MockMvc, Jackson, and the `spring-restdocs-mockmvc` dependency. The controller returns both public fields and diagnostic metadata; the test documents only the portion clients need.

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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderIgnoreInternalFieldsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentPublicOrderFieldsOnly() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 9001)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-9001"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.internalTraceId").isString())
                .andExpect(jsonPath("$.debug.sourceNode").isString())
                .andDo(document("orders-public-fields",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                fieldWithPath("totalAmount")
                                        .description("Total amount in VND"),
                                fieldWithPath("items")
                                        .description("Line items"),
                                fieldWithPath("items[].sku")
                                        .description("Product SKU"),
                                fieldWithPath("items[].quantity")
                                        .description("Product quantity"),
                                fieldWithPath("internalTraceId").ignored(),
                                subsectionWithPath("debug").ignored(),
                                fieldWithPath("items[].stockSnapshot").ignored()
                        )
                ));
    }

    @RestController
    static class OrderController {

        @GetMapping(value = "/api/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> getOrder(@PathVariable("id") long id) {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("id", "ORD-" + id);
            body.put("status", "CONFIRMED");
            body.put("totalAmount", 250000);
            body.put("items", List.of(
                    Map.of("sku", "BK-01", "quantity", 2,
                           "stockSnapshot", 18),
                    Map.of("sku", "BK-02", "quantity", 1,
                           "stockSnapshot", 7)
            ));
            body.put("internalTraceId", "trace-7a91");
            body.put("debug", Map.of(
                    "sourceNode", "node-03",
                    "timingMs", 12,
                    "flags", Map.of("cacheHit", true)
            ));
            return body;
        }
    }
}
```

Two behaviors to understand:

- The `jsonPath("$.internalTraceId").isString()` assertion confirms the actual response still contains internal metadata.
- The `fieldWithPath("internalTraceId").ignored()` descriptor ensures that metadata does not appear in the snippet table.

Ignoring does not remove data from the HTTP body. Anyone receiving the response can still read those bytes. If data must not be exposed, update the DTO/serializer, enforce access control, or strip the data before sending.

## 7. Ignore is not a security mechanism

Suppose a response contains:

```json
{
  "id": "CUS-17",
  "displayName": "Customer 17",
  "email": "customer@example.test",
  "accessToken": "secret-token",
  "passwordHash": "hash-value"
}
```

If `accessToken` or `passwordHash` appears in the response, calling `ignored()` only hides them from the description table. It **does not remove, encrypt, or mask** the data in the response and does not prevent client access.

For fields that must never be exposed publicly:

1. Do not emit real values in the response expecting documentation ignore to hide them.
2. Modify the DTO/projection or serializer so the field is not serialized over HTTP.
3. Enforce authorization and test that unauthorized users do not receive the field.
4. Use synthetic data in fixtures; never put real personal info or secrets in snippets.
5. Write assertions verifying sensitive paths are not returned.

Example:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.accessToken").doesNotExist())
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
```

If a key could exist with a null value and still violate a "must not be returned" contract, parse the response into a `JsonNode` and verify `!node.has("accessToken")`. Checking for a non-null value is not the same as proving the key is completely absent.

## 8. When to ignore vs. when to remove from the response

| Scenario | Approach | Reason |
| --- | --- | --- |
| Trace ID allowed publicly for support lookups | Can ignore from the table if not needed by clients | Reduces documentation noise |
| Debug metadata meant only for internal environments | Consider removing from public responses | Avoids expanding the contract |
| Password hash, access token, or secret | Remove from response and write leak-prevention tests | Ignoring does not protect data |
| Legacy field still returned for compatibility | Document or ignore based on versioning policy | Changes must be managed |
| Unexpected field from an unknown source | Investigate first before ignoring | Could be a serialization bug or data leak |
| Important public field when wanting a shorter table | Use a subsection or reference page | Do not drop needed info without alternative docs |

If clients begin relying on an ignored field, that field may have effectively become part of the real contract. Changing or removing it will require compatibility assessment.

## 9. Keeping strict contracts vs. using relaxed mode

### 9.1. Listing intentionally ignored fields in strict mode

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    fieldWithPath("internalTraceId").ignored(),
    subsectionWithPath("debug").ignored()
)
```

This makes known and intentionally excluded fields explicit. If another field without a descriptor or unhandled branch appears in the payload, strict mode still helps catch that change.

### 9.2. Using `relaxedResponseFields` for partial documentation

```java
relaxedResponseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status")
)
```

Relaxed mode permits unlisted fields. It fits when a test only intends to record part of a structure or during contract transitions. The trade-off is that new fields can appear without documentation tests catching them. When only one branch needs to be omitted from the table, `ignored()` inside strict `responseFields` is easier to audit.

Use `ignored()` for fields you want omitted from the table. Use `optional()` for fields you want shown in the table that may be absent, adding `type(...)` if the fixture cannot infer the type.

## 10. Reusing descriptors

When multiple endpoints share the same technical metadata, you can extract descriptors:

```java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

static FieldDescriptor[] operationalFields() {
    return new FieldDescriptor[] {
        fieldWithPath("internalTraceId").ignored(),
        subsectionWithPath("debug").ignored()
    };
}
```

Then combine them with public descriptors:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status")
).and(operationalFields());
```

This example only applies when responses actually share the same structure. If another endpoint uses `metadata.traceId` instead of `internalTraceId`, provide a separate descriptor. Reuse is only valid when both path and semantics match.

## 11. Snippets and published documentation

After the `document("orders-public-fields", ...)` test runs, the response field snippet is typically located at:

```text
build/generated-snippets/
└── orders-public-fields/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

These are the relevant files; depending on configuration, other default snippets exist. With Maven, the directory is typically `target/generated-snippets`.

The `response-fields.adoc` table contains only documented fields; `ignored()` descriptors do not appear as rows. It can be included in Asciidoctor:

```adoc
= Order API
:snippets: build/generated-snippets

== View order

=== HTTP response
include::{snippets}/orders-public-fields/http-response.adoc[]

=== Published payload fields
include::{snippets}/orders-public-fields/response-fields.adoc[]
```

The build/CI pipeline must run HTTP tests before the Asciidoctor step so snippets are generated from the latest response. If a response adds an unhandled field in strict mode, the test should fail so the team decides whether to publish the field, intentionally ignore it, or remove it from the actual response. When publishing Markdown, use an appropriate converter or template; the default snippet is Asciidoctor.

## 12. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Internal field still appears in the table | `ignored()` was not called | Mark that specific descriptor as ignored |
| Using `ignored()` to bypass an absent field | Confused with optional | Use `optional()` if you want to document a potentially missing field |
| Entire debug branch disappears despite public child fields | Ignored too broad a subsection | Select individual internal fields or document public child fields |
| New fields go undetected | Used overly broad relaxed mode | Return to strict mode and declare ignores explicitly |
| Sensitive field remains in HTTP response | Assumed `ignored()` removes the field | Fix DTO/serialization/access control and add non-exposure tests |
| Used `items.stockSnapshot` for an object array | Omitted array element notation | Use `items[].stockSnapshot` |
| Ignored an array branch with an empty fixture | No sample element to verify child paths | Run doc tests with representative elements |
| Reusing descriptors across endpoints fails | Different paths/schemas | Separate descriptors or apply accurate prefixes |
| Snippets do not update | Tests did not run or build ordering is wrong | Run snippet-generating tests before Asciidoctor |

## 13. Practice exercise

Using the order response from section 6:

1. Add `internalRequestId` at the root. Use `fieldWithPath("internalRequestId").ignored()` and confirm the field has no row in the table.
2. Add `diagnostics` with `timingMs`, `sourceNode`, and `cacheHit`. Use `subsectionWithPath("diagnostics").ignored()` to exclude the whole branch.
3. Promote `diagnostics.requestId` to public. Replace ignoring the entire subsection with individual descriptors: document `requestId` and ignore the remaining internal fields.
4. Add `items[].warehouseCode` and `items[].stockSnapshot`. Ignore both paths while still documenting `items[].sku` and `items[].quantity`.
5. Try `relaxedResponseFields` with only `id` and `status`. Add an unexpected field and observe why relaxed mode can miss it.
6. Emit `accessToken` in the HTTP response and mark it ignored. Verify it is still visible in the response body and write an assertion ensuring the public API does not return tokens.
7. Create two endpoints with different debug structures. Decide which descriptors can be reused.
8. Include the snippet in Asciidoctor, verify the table shows only published fields, and confirm the pipeline still fails when a new unhandled public field appears in strict mode.

**Completion criteria:** you can mark known fields or subsections that should not appear in the table; distinguish ignore from optional and relaxed; avoid confusing documentation ignore with response security; preserve strict checks for the rest of the payload; and maintain test-generated snippets in build/CI.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): documenting payloads, descriptors, optional and ignored fields.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `ignored()`, `optional()`, and `type(...)` APIs.
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `responseFields`, `relaxedResponseFields`, `subsectionWithPath`, and payload helpers.
