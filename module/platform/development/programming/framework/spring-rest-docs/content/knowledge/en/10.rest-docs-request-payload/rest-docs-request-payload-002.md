# Documenting Required and Optional JSON Fields in Spring REST Docs

## 1. Lesson goals

When a REST API accepts JSON, the documentation must answer two questions: **which fields must the client send** and **which fields can be omitted**. If the documentation does not clearly distinguish between these two groups, API consumers may easily send incomplete data, and maintainers may accidentally change the request contract without noticing.

With **Spring REST Docs**, documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. In the **Request payload** chapter, `requestFields(...)` declares the fields of the JSON request, and `fieldWithPath(...).optional()` marks fields that may be absent. These descriptions become snippets that can be included in Asciidoctor documentation or a Markdown export pipeline and verified in the build/CI.

After this lesson, you will know how to:

- Distinguish between *required* and *optional* fields at the Spring REST Docs documentation level.
- Write descriptors for JSON fields at the root level, in nested objects, and in arrays.
- Prove with tests that an optional field can be either present or absent.
- Avoid confusing documentation with `optional()` with application input validation.
- Recognize errors caused by missing descriptors, missing required fields, and improper handling of `null` values.

## 2. What do required and optional fields mean?

Consider the `POST /api/customers` contract for creating a customer:

```json
{
  "fullName": "Nguyen Minh An",
  "email": "an@example.com",
  "address": {
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City"
  },
  "preferences": {
    "newsletter": true
  }
}
```

The assumed contract of the endpoint is as follows:

| JSON path | Data type | Status | Description |
| --- | --- | --- | --- |
| `fullName` | String | Required | Customer full name |
| `email` | String | Required | Valid email address |
| `address` | Object | Required | Contact address |
| `address.street` | String | Required | House number and street name |
| `address.city` | String | Required | City |
| `address.apartment` | String | Optional | Apartment number or floor |
| `phone` | String | Optional | Contact phone number |
| `preferences` | Object | Optional | Communication preferences |
| `preferences.newsletter` | Boolean | Optional | Whether to receive the newsletter |

Here, the sample request does not include `phone` or `address.apartment`, yet it is still valid under the defined contract. The `preferences` object appears in the sample, though the client is allowed to omit this entire object.

Spring REST Docs conventions:

- `fieldWithPath("email")`: **required by default**. If this path is not present in the sample request being documented, generating the snippet for that descriptor fails.
- `fieldWithPath("phone").optional()`: **optional in the documentation**. The sample request may omit `phone` and snippet generation is still allowed to succeed.
- `fieldWithPath("preferences.newsletter").optional()`: child fields are also allowed to be absent, including when the parent object does not appear.

Important: this is a rule that **checks field presence in the sample payload for documentation generation**. It does not automatically force the controller to return HTTP 400 when a client omits a field, nor does it replace `@NotNull`, `@NotBlank`, `@Valid`, or business rules.

## 3. Using `fieldWithPath` and `optional()` properly

The descriptors for the example above can be written as follows:

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] CUSTOMER_FIELDS = {
        fieldWithPath("fullName")
                .type(JsonFieldType.STRING)
                .description("Customer full name"),

        fieldWithPath("email")
                .type(JsonFieldType.STRING)
                .description("Valid email address"),

        fieldWithPath("address")
                .type(JsonFieldType.OBJECT)
                .description("Contact address"),

        fieldWithPath("address.street")
                .type(JsonFieldType.STRING)
                .description("House number and street name"),

        fieldWithPath("address.city")
                .type(JsonFieldType.STRING)
                .description("City"),

        fieldWithPath("address.apartment")
                .type(JsonFieldType.STRING)
                .description("Apartment number or floor")
                .optional(),

        fieldWithPath("phone")
                .type(JsonFieldType.STRING)
                .description("Contact phone number")
                .optional(),

        fieldWithPath("preferences")
                .type(JsonFieldType.OBJECT)
                .description("Communication preferences")
                .optional(),

        fieldWithPath("preferences.newsletter")
                .type(JsonFieldType.BOOLEAN)
                .description("Whether to receive the newsletter")
                .optional()
};
```

In this snippet:

1. Descriptors without `.optional()` are treated as required by default.
2. `.description(...)` explains the meaning of the field to documentation readers; state business rules clearly when needed.
3. `.type(JsonFieldType.X)` determines the type displayed in the documentation. **Do not use `.type(...)` as full JSON Schema validation** or as a replacement for validation tests.
4. For the optional `preferences` object, both the descriptor for the **parent object** and that for the **child field that may be absent** are marked `.optional()`.

### 3.1. Rules for nested objects

Suppose `address` is required while `address.apartment` is optional:

```java
fieldWithPath("address")
        .type(JsonFieldType.OBJECT)
        .description("Contact address"),

fieldWithPath("address.city")
        .type(JsonFieldType.STRING)
        .description("City"),

fieldWithPath("address.apartment")
        .type(JsonFieldType.STRING)
        .description("Apartment number")
        .optional()
```

If the request omits `address`, the `address` and `address.city` descriptors no longer have matching data, so the documentation test must fail. If the request includes `address` and `address.city` but omits `address.apartment`, that case is allowed.

Conversely, when a branch such as `preferences` can be omitted entirely, marking only the parent object `.optional()` **does not guarantee** that all child field descriptors are optional. Each descriptor has its own requiredness; inspect and mark child paths according to the contract.

### 3.2. Rules for JSON arrays

Consider another request with a `contacts` field:

```json
{
  "contacts": [
    { "type": "EMAIL", "value": "an@example.com" },
    { "type": "PHONE", "value": "0900000000", "label": "Personal" }
  ]
}
```

Paths to fields inside each array element use the `[]` syntax:

```java
fieldWithPath("contacts")
        .type(JsonFieldType.ARRAY)
        .description("List of contact methods"),

fieldWithPath("contacts[].type")
        .type(JsonFieldType.STRING)
        .description("Contact method type"),

fieldWithPath("contacts[].value")
        .type(JsonFieldType.STRING)
        .description("Contact value"),

fieldWithPath("contacts[].label")
        .type(JsonFieldType.STRING)
        .description("Display label")
        .optional()
```

`contacts[].label` is a field that may be missing in some elements. However, `.optional()` on a descriptor **does not fully express** rules such as "each element must have `type` and `value`", "the array must contain at least one element", or "a contact type can only appear once". Those conditions require DTO validation and separate business-logic tests.

With an empty array, child field paths such as `contacts[].type` have no sample data to observe. Use a request with representative elements when generating the detailed description table, and write separate tests for empty-array or missing-array cases.

## 4. MockMvc test example generating documentation from actual JSON

The example below uses Spring Boot, JUnit 5, and Spring REST Docs with MockMvc integration. It assumes `POST /api/customers` already exists, accepts JSON matching the contract above, and returns `201 Created` when the request is valid. The project needs `spring-boot-starter-test` and `spring-restdocs-mockmvc` in its test dependencies.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.FieldDescriptor;
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
class CustomerRequestDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    private static final FieldDescriptor[] CUSTOMER_FIELDS = {
            fieldWithPath("fullName")
                    .type(JsonFieldType.STRING)
                    .description("Customer full name"),
            fieldWithPath("email")
                    .type(JsonFieldType.STRING)
                    .description("Valid email address"),
            fieldWithPath("address")
                    .type(JsonFieldType.OBJECT)
                    .description("Contact address"),
            fieldWithPath("address.street")
                    .type(JsonFieldType.STRING)
                    .description("House number and street name"),
            fieldWithPath("address.city")
                    .type(JsonFieldType.STRING)
                    .description("City"),
            fieldWithPath("address.apartment")
                    .type(JsonFieldType.STRING)
                    .description("Apartment number or floor")
                    .optional(),
            fieldWithPath("phone")
                    .type(JsonFieldType.STRING)
                    .description("Contact phone number")
                    .optional(),
            fieldWithPath("preferences")
                    .type(JsonFieldType.OBJECT)
                    .description("Communication preferences")
                    .optional(),
            fieldWithPath("preferences.newsletter")
                    .type(JsonFieldType.BOOLEAN)
                    .description("Whether to receive the newsletter")
                    .optional()
    };

    @Test
    void documentCreateCustomerWithSomeOptionalFieldsMissing() throws Exception {
        String requestJson = """
                {
                  "fullName": "Nguyen Minh An",
                  "email": "an@example.com",
                  "address": {
                    "street": "12 Nguyen Hue",
                    "city": "Ho Chi Minh City"
                  },
                  "preferences": {
                    "newsletter": true
                  }
                }
                """;

        mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("customers-create",
                        requestFields(CUSTOMER_FIELDS)));
    }

    @Test
    void documentCreateCustomerWithoutPreferences() throws Exception {
        String requestJson = """
                {
                  "fullName": "Tran Binh",
                  "email": "binh@example.com",
                  "address": {
                    "street": "85 Le Loi",
                    "city": "Da Nang"
                  }
                }
                """;

        mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("customers-create-minimal",
                        requestFields(CUSTOMER_FIELDS)));
    }
}
```

Both tests share the same descriptor set while sending different request variants. The first test omits `phone` and `address.apartment`; the second test also omits all of `preferences`. If the endpoint actually returns `201` and the field descriptions match the payload, Spring REST Docs generates snippets in two directories:

```text
build/generated-snippets/
├── customers-create/
│   └── request-fields.adoc
└── customers-create-minimal/
    └── request-fields.adoc
```

The list of other files in each directory depends on the project's snippet generation configuration. Giving each document a distinct name prevents the two tests from overwriting the same output set. The fields table can be included in Asciidoctor with:

```adoc
== Create customer

=== Request fields

include::{snippets}/customers-create/request-fields.adoc[]
```

The `{snippets}` variable must be configured to point directly to `build/generated-snippets`. When exporting Markdown documentation, you need the appropriate templates or conversion step; do not assume that Spring REST Docs creates `request-fields.md` out of the box.

**Note on the "Required" column:** `.optional()` affects how REST Docs evaluates field presence during documentation generation. Whether the generated table has an "Optional/Required" column depends on the snippet template in use. To make this clearly visible to readers, write explicit descriptions or customize the template to display this information.

## 5. Distinguishing absent fields, `null`, and empty values

The following three payloads have different meanings:

```json
{
  "fullName": "Nguyen Minh An",
  "email": "an@example.com",
  "address": { "street": "12 Nguyen Hue", "city": "Ho Chi Minh City" }
}
```

```json
{
  "fullName": "Nguyen Minh An",
  "email": "an@example.com",
  "address": { "street": "12 Nguyen Hue", "city": "Ho Chi Minh City" },
  "phone": null
}
```

```json
{
  "fullName": "Nguyen Minh An",
  "email": "an@example.com",
  "address": { "street": "12 Nguyen Hue", "city": "Ho Chi Minh City" },
  "phone": ""
}
```

| Case | Payload meaning | What to verify |
| --- | --- | --- |
| No `phone` key | Client did not send a value | Is a default applied or is it ignored? |
| `"phone": null` present | Client sent the key with JSON `null` | Does the API accept `null`? |
| `"phone": ""` present | Client sent an empty string | Does the API accept an empty string? |

`.optional()` is used to state that **the path may be absent from the sample payload**. It does not assert that the API must accept any `null`, `""`, `" "`, or other JSON types. That responsibility belongs to the contract, validation, and endpoint tests.

For a required field like `email`, "must be present" is still not enough: it usually also needs to be "non-blank" and "a valid email format". For example, the DTO can use Jakarta Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record CreateCustomerRequest(
        @NotBlank String fullName,
        @NotBlank @Email String email,
        @NotNull @Valid AddressRequest address,
        String phone,
        PreferencesRequest preferences
) {}

record AddressRequest(
        @NotBlank String street,
        @NotBlank String city,
        String apartment
) {}

record PreferencesRequest(Boolean newsletter) {}
```

This is an **illustrative example of input constraints**, not required REST Docs configuration. The controller needs to enable the appropriate validation, for example via `@Valid` on `@RequestBody`. When using this DTO, the validation dependency must be present in the project. Rules beyond `@NotBlank` must also be clearly defined, such as what format the phone number requires and how `newsletter` is handled when absent.

You should write separate tests for:

- Missing `email` or `address`: the endpoint returns a validation error per the contract (usually HTTP 400 when configured properly).
- Empty or malformed `email`.
- Absent `phone`, `preferences`, or `address.apartment`: the endpoint still processes the request validly.
- `phone: null` and `phone: ""`: the endpoint handles them according to the published rules.

These tests verify **API behavior**, whereas `requestFields` checks **how well the sample payload is documented**. Combining both yields a reliable request contract.

## 6. Situations that easily cause misunderstandings

### 6.1. Conditionally required fields

For example, the rule "if `deliveryMethod` is `SHIP`, `shippingAddress` must be present; if it is `PICKUP`, `shippingAddress` may be absent".

If you set:

```java
fieldWithPath("shippingAddress")
        .description("Shipping address")
        .optional()
```

then Spring REST Docs allows the path to be absent when generating the snippet, **but it does not check the `deliveryMethod == SHIP` condition**. Test both valid variants and the missing-address variant when `SHIP` separately, and describe the condition in prose or a documentation table. For complex APIs, separate schemas or validation rules per variant may be needed.

### 6.2. A parent object hiding child details

For example:

```java
fieldWithPath("address")
        .description("Contact address")
```

In some documentation styles, declaring a parent-level object can be treated as covering its child fields when checking for undocumented fields. Therefore, relying solely on the test not failing **does not prove** that every child field is explained. When the contract requires details, declare `address.street`, `address.city`, and `address.apartment` as in the main example.

If you intentionally want to present an entire branch under a single documentation row, you can use `subsectionWithPath("address")`; in that case, separate documentation is needed to explain the child fields if API consumers need to know them.

### 6.3. `ignored()` and `relaxedRequestFields(...)` are not synonymous with optional

```java
fieldWithPath("internalTrace")
        .description("Technical trace ID")
        .ignored()
```

`ignored()` means the field is recognized but **excluded from the description table**, which is useful when a technical field does not need to be published. It does not by itself declare that the field may be absent under the API contract.

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
        fieldWithPath("email").description("Customer email"),
        fieldWithPath("phone").description("Phone number").optional()
)
```

`relaxedRequestFields(...)` allows the sample request to contain **undocumented fields**. It still requires declared required descriptors to appear in the payload. By contrast, `optional()` only changes the presence requirement **for that specific descriptor**. For public API documentation that needs to capture all fields, prefer strict `requestFields(...)`.

### 6.4. "Required" in documentation does not mean "cannot be `null`"

Do not infer from `fieldWithPath("email")` that a request with `email: null` will definitely be rejected by the server. That behavior must be decided at the DTO/validation layer and tested. When describing the contract, explicitly state conditions such as "required, non-blank string, valid email format" instead of letting readers guess from the field name.

## 7. Common errors and how to fix them

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Snippet generation test reports missing `phone` | Forgot `.optional()` for a field omitted in the sample request | Confirm the contract and add `.optional()` if truly optional |
| Test reports missing `preferences.newsletter` | `preferences` object is optional, but the child field descriptor is still required | Mark child descriptors that may be absent with `.optional()` |
| Adding `nickname` to JSON causes test failure | Strict `requestFields(...)` detected an undocumented field | Add a descriptor and describe its required/optional status |
| Documentation test passes, yet the API still accepts missing `email` | Corresponding validation or business checks are not implemented | Add validation and HTTP tests for required fields |
| Table lacks a required/optional column | The active snippet template does not render the `optional` attribute | Describe it clearly in `description(...)` or customize the template |
| Sample request has an empty array, hard to verify child fields | No representative element for paths such as `items[].sku` | Create a test with populated elements and a separate empty-array test |
| HTTP test runs but does not generate `request-fields.adoc` | Missing `document(..., requestFields(...))` or REST Docs configuration | Check test integration, snippet name, and `outputDir` |

Errors related to missing or undocumented fields usually occur during the snippet-generation step while running tests. Therefore, CI should run documentation tests before rendering Asciidoctor. When `requestFields` reports an error, treat it as an opportunity to reconcile the API contract with the DTO and actual requests rather than blindly relaxing all checks.

## 8. Hands-on verification

Extend the create-customer API:

1. Add `referralCode` of type String, **optional**. Add the descriptor with `.optional()`, without adding the field to the sample request. Run the test and confirm snippet generation succeeds.
2. Also send `referralCode` in the sample request. Run the test again and verify the same descriptor set still works.
3. Change the contract so that `address.postalCode` is **required**. Add the descriptor without `.optional()`, intentionally omit the field from the sample request, observe the documentation test failure, and then add valid data so the test passes.
4. Create a test sending `email: ""` or omitting `email` to verify that the API rejects invalid input according to validation constraints, rather than relying only on `requestFields`.
5. Include the `customers-create/request-fields.adoc` snippet in Asciidoctor and verify that optional field information is displayed clearly according to your project's template/descriptions.

**Completion criteria:** You only use `.optional()` for fields allowed to be absent in the contract; for required fields, documentation tests demonstrate their presence; conditions such as non-blank, valid format, or conditional requiredness are verified by appropriate API tests. The request payload table is regenerated in the build whenever the API changes.
