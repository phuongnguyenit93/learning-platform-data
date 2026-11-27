# Optional Object Fields and `absent()` in Spring REST Docs

## 1. Why distinguish optional objects from absent objects?

A REST API often has parts of its request body that are only needed in certain situations. For example, an order-creation endpoint allows customers to choose **store pickup** or **home delivery**:

- When `deliveryMode` is `PICKUP`, the client does not need to send the `delivery` object.
- When `deliveryMode` is `SHIP`, the client must send `delivery` with recipient name and address.
- The `gift` object may be omitted in both cases; when present, it holds gift details.

If the documentation always shows `delivery` as a required field, `PICKUP` requests are misrepresented. If `delivery` is merely marked optional without explaining the `SHIP` condition, clients may mistakenly think they can omit the address in every case.

In the **Request payload** chapter of **Spring REST Docs**, this lesson focuses on three related yet distinct tasks:

1. **Documenting** an object that may be absent using `fieldWithPath(...).optional()` in `requestFields(...)`.
2. **Asserting that a JSON key is actually absent** in a sample request, corresponding to the *absent* concept mentioned in the lesson title.
3. **Testing the business contract**: when the object may be omitted, when it must be present, and if present, which child fields are required.

Spring REST Docs generates snippets from HTTP tests via MockMvc, WebTestClient, or REST Assured. Those snippets can be included in Asciidoctor/Markdown documentation and regenerated in the build/CI to detect drift between documentation and tested behavior.

### Important note on the name `absent()`

**`FieldDescriptor` in Spring REST Docs does not have an `.absent()` method**. The relevant methods are `.optional()` and `.ignored()`. Therefore, the following snippet is **not valid Spring REST Docs API**:

```java
// WRONG: FieldDescriptor does not have absent()
fieldWithPath("delivery").description("Delivery information").absent();
```

In this lesson, **absent** means *the JSON key does not appear in the payload*. To document that possibility, use `.optional()`; to verify that a sample request omits the key, use an assertion on the actual JSON. These are two different goals. Do not invent an `absent()` method or confuse it with a function from another testing library.

## 2. Designing the API contract for an optional object

Suppose `POST /api/orders` accepts either of the two requests below.

### 2.1. Home delivery: `delivery` and `gift` objects present

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 42,
  "deliveryMode": "SHIP",
  "delivery": {
    "recipient": {
      "name": "Nguyen Minh An",
      "phone": "0900000000"
    },
    "address": {
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City"
    },
    "instructions": "Call before delivery"
  },
  "gift": {
    "message": "Happy birthday"
  }
}
```

### 2.2. Store pickup: `delivery` and `gift` objects absent

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 42,
  "deliveryMode": "PICKUP"
}
```

Both cases are assumed **valid** and the endpoint returns `201 Created`. The contract requires:

| Path | JSON type | Contract status | Meaning |
| --- | --- | --- | --- |
| `customerId` | Number | Required | Customer placing the order |
| `deliveryMode` | String | Required | `PICKUP` or `SHIP` |
| `delivery` | Object | Conditional | Must be present if `deliveryMode=SHIP`; omitted if `PICKUP` |
| `delivery.recipient` | Object | Conditional | Recipient details for delivery |
| `delivery.recipient.name` | String | Conditional | Recipient name for delivery |
| `delivery.recipient.phone` | String | Optional | Recipient phone number |
| `delivery.address` | Object | Conditional | Address for delivery |
| `delivery.address.street` | String | Conditional | Street address for delivery |
| `delivery.address.city` | String | Conditional | City for delivery |
| `delivery.instructions` | String | Optional | Instructions for the courier |
| `gift` | Object | Optional | Gift information |
| `gift.message` | String | Conditional | Message content if `gift` is sent |

**Conditional** is not a built-in property of `FieldDescriptor`. In a snippet shared between `SHIP` and `PICKUP`, these paths need `.optional()` so `PICKUP` requests are accepted; the "required when shipping" condition must be described in prose and tested with separate business-logic tests.

## 3. Using `.optional()` for both the parent object and child fields

To generate a request fields table from both variants, declare:

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
        fieldWithPath("customerId")
                .type(JsonFieldType.NUMBER)
                .description("Customer ID"),

        fieldWithPath("deliveryMode")
                .type(JsonFieldType.STRING)
                .description("Fulfillment method: PICKUP or SHIP"),

        fieldWithPath("delivery")
                .type(JsonFieldType.OBJECT)
                .description("Delivery details; required when deliveryMode=SHIP")
                .optional(),

        fieldWithPath("delivery.recipient")
                .type(JsonFieldType.OBJECT)
                .description("Recipient details when deliveryMode=SHIP")
                .optional(),

        fieldWithPath("delivery.recipient.name")
                .type(JsonFieldType.STRING)
                .description("Recipient name; required for delivery")
                .optional(),

        fieldWithPath("delivery.recipient.phone")
                .type(JsonFieldType.STRING)
                .description("Recipient phone number, can be omitted")
                .optional(),

        fieldWithPath("delivery.address")
                .type(JsonFieldType.OBJECT)
                .description("Address; required for delivery")
                .optional(),

        fieldWithPath("delivery.address.street")
                .type(JsonFieldType.STRING)
                .description("Street address; required for delivery")
                .optional(),

        fieldWithPath("delivery.address.city")
                .type(JsonFieldType.STRING)
                .description("City; required for delivery")
                .optional(),

        fieldWithPath("delivery.instructions")
                .type(JsonFieldType.STRING)
                .description("Delivery instructions, can be omitted")
                .optional(),

        fieldWithPath("gift")
                .type(JsonFieldType.OBJECT)
                .description("Gift details, can be omitted")
                .optional(),

        fieldWithPath("gift.message")
                .type(JsonFieldType.STRING)
                .description("Gift message; required if gift object is present")
                .optional()
};
```

There are three principles to keep in mind.

**First, `.optional()` is a property of each individual descriptor.** Marking `delivery` as optional does not automatically make `delivery.recipient.name` and `delivery.address.city` optional. If the entire object can be missing in a sample request, the child paths must also be marked appropriately.

**Second, add `.type(JsonFieldType.OBJECT)` for objects that do not always appear.** If a sample request omits the object, Spring REST Docs cannot infer the actual type from that field itself; declaring it explicitly keeps the table output consistent. For child fields, set types explicitly as well since they too may be absent.

**Third, `optional()` does not enforce conditional requiredness rules.** The declaration above allows a `SHIP` request without `delivery` to pass **the snippet's required-field check**, because those descriptors are all optional; it does not ensure the endpoint accepts the request. To protect the business contract, add validation or separate tests.

### When the parent object is present, are child fields required?

Consider three cases:

```json
{ "deliveryMode": "PICKUP" }
```

```json
{
  "deliveryMode": "SHIP",
  "delivery": { "address": {} }
}
```

```json
{
  "deliveryMode": "SHIP",
  "delivery": {
    "recipient": { "name": "An" },
    "address": { "street": "12 Nguyen Hue", "city": "Ho Chi Minh City" }
  }
}
```

The first request is allowed to omit `delivery`. The second request is **invalid under the example contract** because recipient name and required address fields are missing. The third request satisfies the essential delivery fields. However, relying solely on `.optional()` on shared descriptors does not distinguish all three cases. You need business-condition testing at the HTTP handling layer.

## 4. Distinguishing `absent`, `null`, and empty object `{}`

This is the most common source of confusion when documenting JSON objects.

**Completely absent:**

```json
{
  "customerId": 42,
  "deliveryMode": "PICKUP"
}
```

**Key present, value is `null`:**

```json
{
  "customerId": 42,
  "deliveryMode": "PICKUP",
  "delivery": null
}
```

**Key present, value is an empty object:**

```json
{
  "customerId": 42,
  "deliveryMode": "PICKUP",
  "delivery": {}
}
```

| Case | `delivery` key present? | JSON value | Interpretation |
| --- | --- | --- | --- |
| Absent | No | No value | Client omitted the field |
| `null` | Yes | `null` | Client sent the field with a null value |
| `{}` | Yes | Empty object | Client sent an object with no child fields |
| `[]` | Yes | Empty array | Wrong type compared to the object expected by the contract |

Thus, **"allowed to omit the object" does not automatically mean "allowed to send `null`"**. Depending on the API, a `PICKUP` request may be designed to accept both, or only absent. Some applications treat `null` as a signal to clear data during updates, whereas others reject `null`. Make a deliberate decision and test it specifically.

### Asserting absent with Jackson

To assert that a JSON request **does not contain a key name**, use `JsonNode.has(...)` or `isMissingNode()`:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

ObjectMapper mapper = new ObjectMapper();

JsonNode absent = mapper.readTree("""
        {"customerId":42,"deliveryMode":"PICKUP"}
        """);

assertFalse(absent.has("delivery"));
assertTrue(absent.path("delivery").isMissingNode());

JsonNode explicitNull = mapper.readTree("""
        {"customerId":42,"deliveryMode":"PICKUP","delivery":null}
        """);

assertTrue(explicitNull.has("delivery"));
assertTrue(explicitNull.get("delivery").isNull());

JsonNode emptyObject = mapper.readTree("""
        {"customerId":42,"deliveryMode":"PICKUP","delivery":{}}
        """);

assertTrue(emptyObject.has("delivery"));
assertTrue(emptyObject.get("delivery").isObject());
assertTrue(emptyObject.get("delivery").isEmpty());
```

`has("delivery")` returns `true` even when the value is `null`. Therefore, do not use a "value is not null" check to prove a field **is not present at all**. For nested structures, you can check `root.path("delivery").path("address").isMissingNode()`, while also checking the parent object if you need to distinguish an absent subtree from a single missing child field.

### If you encounter `absent()` in other test code

The name `absent()` could be a custom helper, a matcher, or syntax from another library. Do not assume it belongs to Spring REST Docs. For this lesson, use the actual API of the library you are calling:

| Goal | Appropriate API | Where it applies |
| --- | --- | --- |
| Field may be missing in snippet | `fieldWithPath("delivery").optional()` | Spring REST Docs `requestFields(...)` |
| Assert request JSON omits key | `assertFalse(root.has("delivery"))` | JUnit + Jackson, checking request content |
| Assert request JSON omits entire path | `root.path("delivery").isMissingNode()` | Jackson `JsonNode` |
| Assert **response** JSON lacks path completely | `jsonPath("$.delivery").doesNotHaveJsonPath()` | MockMvc response matcher |
| Response has no non-null value at path | `jsonPath("$.delivery").doesNotExist()` | MockMvc response matcher |

The two `jsonPath(...)` matchers in the table apply to the **response body** received by MockMvc; they do not inspect the request body that was sent. `doesNotExist()` allows the path to have a `null` value, whereas `doesNotHaveJsonPath()` requires the path to be genuinely absent, not even present as null. When checking a request, read the request content directly as in the Jackson example instead of applying response matchers to requests.

## 5. MockMvc test with populated object and absent object

Assumptions:

- The project has Spring Boot, JUnit 5, MockMvc, Jackson, and Spring REST Docs MockMvc.
- The `POST /api/orders` endpoint is implemented according to the contract in section 2.
- The endpoint returns `201 Created` for both valid `SHIP` requests and valid `PICKUP` requests.
- The project has `spring-boot-starter-test` and `spring-restdocs-mockmvc` in its test dependencies.

The example below uses a **shared descriptor set**, but two different JSON requests. The `PICKUP` test verifies that `delivery` and `gift` are truly **absent** before sending the HTTP request.

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
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OptionalObjectRequestDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    private static final FieldDescriptor[] FIELDS = {
            fieldWithPath("customerId")
                    .type(JsonFieldType.NUMBER)
                    .description("Customer ID"),
            fieldWithPath("deliveryMode")
                    .type(JsonFieldType.STRING)
                    .description("PICKUP or SHIP"),

            fieldWithPath("delivery")
                    .type(JsonFieldType.OBJECT)
                    .description("Required for delivery; omitted for store pickup")
                    .optional(),
            fieldWithPath("delivery.recipient")
                    .type(JsonFieldType.OBJECT)
                    .description("Recipient for delivery")
                    .optional(),
            fieldWithPath("delivery.recipient.name")
                    .type(JsonFieldType.STRING)
                    .description("Recipient name; required for delivery")
                    .optional(),
            fieldWithPath("delivery.recipient.phone")
                    .type(JsonFieldType.STRING)
                    .description("Recipient phone number")
                    .optional(),
            fieldWithPath("delivery.address")
                    .type(JsonFieldType.OBJECT)
                    .description("Address; required for delivery")
                    .optional(),
            fieldWithPath("delivery.address.street")
                    .type(JsonFieldType.STRING)
                    .description("Street name; required for delivery")
                    .optional(),
            fieldWithPath("delivery.address.city")
                    .type(JsonFieldType.STRING)
                    .description("City; required for delivery")
                    .optional(),
            fieldWithPath("delivery.instructions")
                    .type(JsonFieldType.STRING)
                    .description("Delivery notes")
                    .optional(),

            fieldWithPath("gift")
                    .type(JsonFieldType.OBJECT)
                    .description("Gift details, can be omitted")
                    .optional(),
            fieldWithPath("gift.message")
                    .type(JsonFieldType.STRING)
                    .description("Message when gift is included")
                    .optional()
    };

    @Test
    void documentShippingOrderWithOptionalObjects() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "deliveryMode": "SHIP",
                  "delivery": {
                    "recipient": {
                      "name": "Nguyen Minh An",
                      "phone": "0900000000"
                    },
                    "address": {
                      "street": "12 Nguyen Hue",
                      "city": "Ho Chi Minh City"
                    },
                    "instructions": "Call before delivery"
                  },
                  "gift": {
                    "message": "Happy birthday"
                  }
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-shipping",
                        requestFields(FIELDS)));
    }

    @Test
    void documentPickupOrderWithAbsentObjects() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "deliveryMode": "PICKUP"
                }
                """;

        JsonNode requestBody = objectMapper.readTree(json);
        assertFalse(requestBody.has("delivery"));
        assertFalse(requestBody.has("gift"));

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-pickup",
                        requestFields(FIELDS)));
    }
}
```

### Why use two different snippet names?

Both tests use the same `FIELDS` array, but with different inputs. If both wrote to `orders-create` during test execution, the snippets could overwrite one another and make payload examples harder to inspect. Using separate names keeps a clear record of each scenario:

```text
build/generated-snippets/
├── orders-shipping/
│   ├── http-request.adoc
│   └── request-fields.adoc
└── orders-pickup/
    ├── http-request.adoc
    └── request-fields.adoc
```

Additional snippets such as `http-response.adoc` and `curl-request.adoc` depend on configuration. In the final documentation, you can use `request-fields.adoc` from one scenario to describe the shared contract and include `http-request.adoc` from both scenarios to illustrate present/absent objects.

### What does `requestFields(...)` confirm?

- The declared descriptors are used by Spring REST Docs to generate the documentation table.
- Fields not marked `.optional()` must appear in the sample payload when the snippet is generated.
- In strict mode, **undocumented** fields can cause snippet generation to fail.
- `.optional()` descriptors may be absent in a sample request.

However, a passing snippet-generation test **does not confirm** the rule "`delivery` is required if mode is `SHIP`". That rule must be tested at the business-logic or validation layer.

## 6. Verifying conditional requiredness rules

We want the following three business-logic tests:

| Sent payload | Expected result per example contract |
| --- | --- |
| `PICKUP`, without `delivery` | `201 Created` |
| `SHIP`, with `delivery.recipient.name`, `delivery.address.street`, `delivery.address.city` | `201 Created` |
| `SHIP`, missing `delivery` or missing required address fields | `400 Bad Request` or API-defined error |

With Spring Boot and Jakarta Bean Validation, the conditional part can be expressed via DTOs and validators. The example below illustrates the idea; align annotations, enum types, and error rules with your actual project:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record CreateOrderRequest(
        @NotNull Long customerId,
        @NotBlank String deliveryMode,
        @Valid DeliveryRequest delivery,
        @Valid GiftRequest gift
) {
    @AssertTrue(message = "delivery is required when deliveryMode is SHIP")
    public boolean isDeliveryConsistent() {
        return !"SHIP".equals(deliveryMode) || delivery != null;
    }
}

record DeliveryRequest(
        @NotNull @Valid RecipientRequest recipient,
        @NotNull @Valid AddressRequest address,
        String instructions
) {}

record RecipientRequest(
        @NotBlank String name,
        String phone
) {}

record AddressRequest(
        @NotBlank String street,
        @NotBlank String city
) {}

record GiftRequest(
        @NotBlank String message
) {}
```

In the controller, apply `@Valid` to the input parameter:

```java
@PostMapping("/api/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // Save the order and return the result per the API contract
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

This is an illustrative implementation assuming imports and the validation dependency are already configured. With nested `@Valid`, when `delivery` is present, fields in `DeliveryRequest`, `RecipientRequest`, and `AddressRequest` are validated. When `delivery` is absent, `isDeliveryConsistent()` decides whether it is accepted based on `deliveryMode`.

For a more complex contract, `@AssertTrue` can be replaced with a class-level custom constraint or business logic to express the rule cleanly and reusably. Furthermore, using an enum instead of a free-form string is still recommended if only `SHIP` and `PICKUP` are accepted.

### Negative HTTP test for `SHIP` missing object

```java
@Test
void rejectShippingOrderWithoutDelivery() throws Exception {
    String json = """
            {
              "customerId": 42,
              "deliveryMode": "SHIP"
            }
            """;

    mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().isBadRequest());
}
```

When the endpoint implements validation and error mapping properly, this test must pass. **Do not use the same `201` expectation for invalid requests**. You can generate separate error snippets if the API needs to document validation responses, though that belongs to error HTTP scenarios rather than replacing descriptors for successful requests.

## 7. When to use `subsectionWithPath`, `ignored()`, or `relaxedRequestFields`?

Sometimes an optional object is very large, and overview documentation only needs to state what group of information it holds. In that case, you can consider:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("delivery")
        .description("Delivery details when deliveryMode=SHIP")
        .optional()
```

`subsectionWithPath("delivery")` records the entire `delivery` branch as a subsection. It is suitable for overview documentation because child fields are treated as covered by the subsection-level description. If clients need to know `recipient.name` or `address.city`, provide separate detailed documentation or declare `fieldWithPath(...)` for each field in the table.

Comparing three mechanisms often confused with `.optional()`:

| Mechanism | Primary effect | Means "object is allowed to be absent"? |
| --- | --- | --- |
| `.optional()` | Allows the descriptor to be absent in the documented payload | Yes, at the snippet verification level |
| `.ignored()` | Excludes descriptor from table; field/branch is treated as recognized | Does not express an optional contract |
| `relaxedRequestFields(...)` | Ignores undocumented payload fields | Does not automatically make required descriptors optional |
| `subsectionWithPath("delivery")` | Describes an entire branch under one row | Not automatically optional; `.optional()` can be added |

For API documentation that needs to capture the full request payload, using strict `requestFields(...)` and `.optional()` on the appropriate fields is usually easier to maintain. Over-relaxing checks can allow a new field to appear in JSON without being added to the documentation.

## 8. Including both variants in Asciidoctor or Markdown

After tests pass, you can author the Asciidoctor source:

```adoc
= Orders API
:toc: left

== Create order

`delivery` is an optional object when `deliveryMode=PICKUP`.
When `deliveryMode=SHIP`, recipient and address details must be sent.

=== Store pickup example

include::{snippets}/orders-pickup/http-request.adoc[]

=== Delivery example

include::{snippets}/orders-shipping/http-request.adoc[]

=== Request field descriptions

include::{snippets}/orders-shipping/request-fields.adoc[]
```

You need to configure `{snippets}` to point to the directory containing snippets, typically `build/generated-snippets`. With Gradle and the Asciidoctor plugin installed, the build flow can be declared as:

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

When snippet-generating tests fail, the CI build must stop before publishing documentation. If the project outputs **Markdown**, appropriate Markdown snippet templates or a conversion step are needed; Spring REST Docs in these examples defaults to `.adoc` and does not generate `request-fields.md` automatically.

A separate table in the documentation can clarify conditions that are difficult to express with the default optional column:

| Condition | Related field | Requirement |
| --- | --- | --- |
| `deliveryMode=PICKUP` | `delivery` | May be omitted |
| `deliveryMode=SHIP` | `delivery` | Must be present |
| `delivery` present | `delivery.recipient.name` | Non-blank |
| `delivery` present | `delivery.address.street`, `delivery.address.city` | Non-blank |
| `gift` absent | `gift.message` | Not required |
| `gift` present | `gift.message` | Required per example contract |

If the snippet template in use does not display an "Optional" column, state the status clearly in `.description(...)` or customize the template.

## 9. Common errors and how to fix them

| Situation | Cause | How to fix |
| --- | --- | --- |
| `.absent()` on `FieldDescriptor` fails to compile | Not a Spring REST Docs method | Use `.optional()` and JSON assertions to verify absence |
| `PICKUP` request omitting `delivery` causes snippet generation to fail | `delivery` descriptor or child fields not marked optional | Review all descriptors in the branch that may be absent |
| `delivery` is optional but `delivery.address.city` still reported missing | Parent object's `.optional()` does not propagate to child descriptors | Apply `.optional()` to the appropriate child descriptors |
| `SHIP` omits `delivery` yet documentation test still generates snippet | Descriptors for the conditional branch are all optional | Add validation and a negative test for the `SHIP` condition |
| Assumed `delivery: null` is the same as absent | Key is present even though value is null | Use `JsonNode.has`/`isMissingNode` and define the contract clearly |
| `delivery: {}` is accepted despite missing child fields | No validation for nested fields yet | Use `@Valid`, `@NotNull`, and `@NotBlank` appropriately |
| Table only shows `delivery`, missing recipient/address details | Only documented parent object or subsection | Add child field descriptors meaningful to clients |
| `request-fields.adoc` not found | Did not call `requestFields(...)`, missing REST Docs config, or wrong output path | Check test, snippet name, and `outputDir` |
| Documentation uses `responseFields` for request | Chose the wrong data direction | Use `requestFields(...)` for request bodies |

## 10. Hands-on exercise

Start from the descriptor set and two tests in section 5:

1. **Confirm absent object:** print or assert `JsonNode.has("delivery")` for the three JSON payloads in section 4. Explain why `false` only occurs when the key is truly absent.
2. **Add an optional object:** add `invoice` with `companyName` and `taxCode`; the `invoice` object may be omitted when the customer does not request an invoice. Add descriptors for `invoice` and its child fields with `.optional()` as appropriate; create two requests with and without `invoice`.
3. **Conditional requiredness:** with `deliveryMode=SHIP`, send `delivery` while omitting `delivery.address.city`. Add validation so the API returns an error. Explain why `.optional()` alone does not fully catch this error.
4. **Test `null`:** send `"delivery": null` with `PICKUP`. Clearly decide whether the API contract accepts this situation; write the corresponding test.
5. **Export documentation:** generate both `orders-shipping` and `orders-pickup` snippet directories, include both HTTP requests in Asciidoctor, along with a table of requiredness conditions by `deliveryMode`.
6. **Simulate a contract change:** add `delivery.contactEmail` to the `SHIP` JSON without a descriptor yet. Observe the failure in strict `requestFields` mode, then update the descriptors and documentation.

### Self-check questions

- Why does `delivery.optional()` not make `delivery.address.city` automatically optional?
- How does absent differ from `null` and `{}`?
- Does `FieldDescriptor` have an `.absent()` API? Where should you check to prove a key is not present?
- Why can an object documented as optional still be **conditionally required by business rules**?
- If only the parent object is documented, does the snippet table provide enough information for clients to fill in child fields properly?
- When an API adds a new field to an object, how should CI react?

**Remember:** In Spring REST Docs, `.optional()` is how you document that a field or object **is allowed to be absent** in a sample payload. **Absent** is the actual state of JSON and can be verified with assertions on the request; it is **not** an `.absent()` method on `FieldDescriptor`. When an optional object has conditionally required child fields, combine descriptors, prose explanations, validation, and HTTP tests so the documentation accurately reflects the API contract.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `fieldWithPath`, optional fields, and snippets.
- [Spring REST Docs — `FieldDescriptor` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): actual methods, including `optional()`, with no `absent()`.
- [Spring Framework — `JsonPathResultMatchers` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): distinguishing `doesNotExist()` and `doesNotHaveJsonPath()` on **responses**.
