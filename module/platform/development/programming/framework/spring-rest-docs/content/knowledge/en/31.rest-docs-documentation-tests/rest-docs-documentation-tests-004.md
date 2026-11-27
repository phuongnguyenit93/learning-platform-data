# Detecting Extra Fields in Requests or Responses

## 1. Why Detect Undocumented Fields?

An API's payload can change over time. A developer adds a new field to a request DTO or response model, yet forgets to update the documentation. When that happens, clients reading the docs will not know the new field exists, what it means, or whether they are allowed to send it.

Spring REST Docs helps detect this kind of drift through descriptor validation. When using `requestFields(...)` or `responseFields(...)` in strict mode, fields that appear in the payload without being described can fail the documentation test. The test forces the team to review the new field before updating the docs.

In **SPRING_REST_DOCS**, the module produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. These tests generate snippets for requests, responses, payloads, parameters, and headers; the documentation is then compiled with Asciidoctor/Markdown and integrated into build/CI. The **Documentation Tests** chapter focuses on turning payload changes into clear verification signals.

This lesson explains how to detect extra fields in requests or responses, how to handle valid new fields, and when to use `ignored()` or `relaxedRequestFields(...)` / `relaxedResponseFields(...)`.

After this lesson, you will be able to:

- Understand how strict field documentation validates payloads.
- Recognize errors when requests or responses contain undocumented fields.
- Distinguish extra fields from missing required field descriptors.
- Use `ignored()` when a field is known but does not need to appear in the table.
- Intentionally use relaxed mode when additional fields are allowed.
- Structure tests to catch contract changes and update snippets in CI.

## 2. Strict Mode: Descriptors Must Cover the Payload

Example product creation request:

```json
{
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "active": true
}
```

Test describing the fields:

```java
requestFields(
    fieldWithPath("name").description("Product name"),
    fieldWithPath("price").description("Selling price"),
    fieldWithPath("active").description("Whether the product is active for sale")
);
```

With `requestFields(...)`, Spring REST Docs validates the request payload against the descriptor set. If the payload contains an additional `category` field but the descriptors do not include `category`, snippet generation will fail with a `SnippetException`-style error indicating an undocumented field.

This is very helpful when a DTO is extended:

```json
{
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "active": true,
  "category": "ACCESSORY"
}
```

If the test still uses the old descriptors, strict mode reports that `category` is undocumented. The team must decide whether:
- `category` is part of the public contract and needs to be added to documentation;
- it is a known internal field that should be acknowledged without being included in the table;
- or the operation genuinely allows extensible fields that do not need documenting in this snippet.

Do not silence the error immediately. A new field can impact clients, validation, compatibility, or persisted data.

## 3. Detecting Extra Request Fields with MockMvc

Suppose `POST /api/products` accepts JSON and returns `201 Created`.

```java
@Test
void documentCreateProduct() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Mechanical Keyboard",
                  "price": 1290000,
                  "active": true,
                  "category": "ACCESSORY"
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("products-create",
            requestFields(
                fieldWithPath("name")
                    .description("Product name"),
                fieldWithPath("price")
                    .description("Selling price"),
                fieldWithPath("active")
                    .description("Active status")
            )
        ));
}
```

In this example, the request includes `category`, while the descriptors do not. When Spring REST Docs creates the request fields snippet, strict validation detects the extra field and the documentation test fails.

The exact message depends on the version, but it usually identifies one or more undocumented payload paths. Read the paths in the exception to determine which field just appeared.

### 3.1. Updating Descriptors When the Field Belongs to the Contract

If `category` is a field clients are allowed to send, add a descriptor:

```java
requestFields(
    fieldWithPath("name")
        .description("Product name"),
    fieldWithPath("price")
        .description("Selling price"),
    fieldWithPath("active")
        .description("Active status"),
    fieldWithPath("category")
        .description("Product category")
);
```

Re-run the test. Once the payload and descriptors match, the snippet is generated with the new field.

This is an intentional review workflow: changing a DTO/request payload drives changes to test descriptors and documentation. If the new field should not be public yet, revisit the DTO or mapping instead of casually adding it to the docs.

## 4. Detecting Extra Response Fields

The same mechanism applies to responses. Suppose the endpoint returns:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "stock": 18
}
```

The test only describes the first three fields:

```java
responseFields(
    fieldWithPath("id").description("Product ID"),
    fieldWithPath("name").description("Product name"),
    fieldWithPath("price").description("Selling price")
);
```

If the response adds `stock`, strict `responseFields(...)` detects the undocumented field. This matters because a new response field can be a public contract change, even if the endpoint still returns `200 OK`.

MockMvc example:

```java
@Test
void documentGetProduct() throws Exception {
    mockMvc.perform(get("/api/products/{id}", 42)
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("products-get",
            responseFields(
                fieldWithPath("id")
                    .description("Product ID"),
                fieldWithPath("name")
                    .description("Product name"),
                fieldWithPath("price")
                    .description("Selling price")
            )
        ));
}
```

If the response fixture has `stock` while the descriptors do not, generating the response fields snippet fails. Add `fieldWithPath("stock").description(...)` if that field belongs to the response contract.

Strict mode detects new fields; it does not decide whether a field should be public. That decision still requires API review.

## 5. Distinguishing Extra Fields from Missing Fields

There are two distinct validation directions:

1. **Extra field in payload:** the payload contains a path that the descriptors have not declared.
2. **Missing required field in payload:** a descriptor declares a field, but the sample request/response lacks that path.

Example:

| Payload | Descriptors | Strict result |
| --- | --- | --- |
| Has `name`, `price` | Describes `name`, `price` | Matches |
| Also has `category` | Only describes `name`, `price` | Undocumented extra field |
| Only has `name` | Describes `name`, `price` | `price` is missing if descriptor is required |
| Has `name`, no `note` | `note` is `.optional()` | Valid |
| Has `name`, has `internalCode` | `internalCode` is `.ignored()` | Recognized, omitted from table |

By default, a field descriptor is treated as required in the documented payload. If a field may be absent, use `.optional()`:

```java
fieldWithPath("note")
    .description("Additional note")
    .optional();
```

`.optional()` does not permit undeclared extra fields. It only allows that field's descriptor to be absent from the sample payload.

## 6. Using `ignored()` When a Field Is Known but Should Not Appear in the Table

Sometimes a payload contains technical fields or fields that do not need to appear in the table, yet the team still wants strict mode to recognize them. In that case, use `.ignored()`:

```java
requestFields(
    fieldWithPath("name")
        .description("Product name"),
    fieldWithPath("price")
        .description("Selling price"),
    fieldWithPath("internalTrace")
        .description("Internal trace ID")
        .ignored()
);
```

`internalTrace` is declared in the descriptors, so it is no longer an unknown field. However, it will not appear as a row in the snippet.

This differs from relaxed mode:
- `.ignored()` explicitly declares a specific field and excludes it from the table.
- Relaxed mode permits fields without descriptors to appear in the payload.

If the field may be absent, you can combine `.optional().ignored()`:

```java
fieldWithPath("internalTrace")
    .description("Internal trace ID if present")
    .optional()
    .ignored();
```

Only use `ignored` for reviewed fields. Do not use it to hide a new public field that the documentation ought to explain.

## 7. When to Use Relaxed Mode?

Spring REST Docs provides:

- `relaxedRequestFields(...)`
- `relaxedResponseFields(...)`

These APIs still generate snippets from declared descriptors, while allowing the payload to contain additional undescribed fields. This is useful when:
- An endpoint has an extensible payload and the current page only documents part of it.
- There are auxiliary fields managed by another module.
- The team is documenting a subset of a large response.
- The API intentionally supports compatible extension fields that clients can ignore.

Example:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
    fieldWithPath("name")
        .description("Product name"),
    fieldWithPath("price")
        .description("Selling price")
);
```

If the payload adds `category`, `internalCode`, or other fields, relaxed mode will not fail the test merely because those fields are not listed in descriptors.

### 7.1. Trade-offs of Relaxed Mode

Relaxed mode reduces the ability to detect payload drift. When a developer adds a new field, tests may still pass even though documentation never mentions it.

Therefore:
- Use strict mode for complete public API contract documentation.
- Use relaxed mode when intentionally documenting only part of a payload.
- Explicitly note which part of the payload is covered and which is not.
- Consider adding separate contract tests to monitor important fields if snippets require relaxed mode.

Do not switch to relaxed just to make a test "green" after strict mode catches a new field. First determine what the new field means.

## 8. Strict vs. Relaxed: Comparison Table

| Mechanism | Described fields | Undescribed extra fields | Absent descriptor fields |
| --- | --- | --- | --- |
| `requestFields(...)` | Validated and displayed | Can fail the test | Required ones can fail the test |
| `responseFields(...)` | Validated and displayed | Can fail the test | Required ones can fail the test |
| `.optional()` | Documented when present | Does not affect extra fields | Allows descriptor to be absent |
| `.ignored()` | Recognized | Does not affect other fields | Still required unless optional |
| `relaxedRequestFields(...)` | Documented | Allowed to exist | Descriptors still obey optional |
| `relaxedResponseFields(...)` | Documented | Allowed to exist | Descriptors still obey optional |

Strict/relaxed is a snippet-level choice. Optional/ignored is a descriptor-level property. Understanding the right scope helps avoid missing fields that should be published.

## 9. Nested Fields and Arrays

Extra fields do not only occur at the root level. Example response:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "supplier": {
    "id": 7,
    "name": "Acme",
    "country": "VN"
  },
  "tags": ["keyboard", "accessory"]
}
```

If descriptors only describe:

```java
responseFields(
    fieldWithPath("id").description("Product ID"),
    fieldWithPath("name").description("Product name"),
    fieldWithPath("supplier.id").description("Supplier ID"),
    fieldWithPath("supplier.name").description("Supplier name"),
    fieldWithPath("tags").description("List of tags")
);
```

Strict mode can detect that `supplier.country` is undocumented. Paths must be read according to the actual JSON structure, not the Java property name if Jackson renamed it.

For arrays of objects, use paths like `items[].sku` and `items[].quantity`. If a new field `items[].discount` is introduced, descriptors must also be updated when strict snippets document array elements completely.

If a child object is documented as a holistic block via `subsectionWithPath(...)`, child-field rules may differ from listing each field individually. Choose the approach based on the desired level of detail and verify the output with tests.

## 10. Example Detecting Extra Fields in Both Request and Response

One operation can generate both request fields and response fields. Strict descriptors on both sides detect drift independently:

```java
mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "Mechanical Keyboard",
              "price": 1290000,
              "active": true
            }
            """))
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Product name"),
            fieldWithPath("price").description("Selling price"),
            fieldWithPath("active").description("Active status")
        ),
        responseFields(
            fieldWithPath("id").description("Product ID"),
            fieldWithPath("name").description("Product name"),
            fieldWithPath("price").description("Selling price"),
            fieldWithPath("active").description("Active status")
        )
    ));
```

If the request adds `category` without a descriptor, the request snippet fails. If the response adds `stock` without a descriptor, the response snippet fails. Having valid descriptors on one side does not automatically validate the other side.

That is why request and response descriptors should be kept separate, even when both payloads share field names.

## 11. How to Handle Tests Reporting Extra Fields

When a strict snippet reports an undocumented field:

1. Read the exact path mentioned in the exception.
2. Identify whether the field comes from the request or the response.
3. Inspect the DTO, serializer, or mapping producing that field.
4. Determine whether the field belongs to the public API contract.
5. If yes, add a descriptor with a clear explanation of its meaning.
6. If it should not be published yet must be recognized, use `.ignored()` with a clear rationale.
7. If the operation intentionally documents only part of the payload by design, consider relaxed mode and state the scope explicitly.
8. Re-run the test to regenerate snippets and review the diff.

Example adding a field:

```java
fieldWithPath("category")
    .type(JsonFieldType.STRING)
    .description("Product category");
```

If the new field is an accidental leak of internal data, do not immediately add `.ignored()`. Consider removing the field from the response or fixing the serializer/mapping before updating documentation.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test reports undocumented field | Payload has a new path missing from descriptors | Review the field, then add a descriptor or intentionally ignore it |
| Used `.optional()` but extra field still fails | Optional only applies to declared descriptors | Add a descriptor for the extra field or use relaxed per contract |
| Used `.ignored()` but field is still required | Ignored does not automatically make a field optional | Add `.optional()` if the sample payload may omit it |
| Relaxed test passes but docs miss key fields | Relaxed allows extra fields | Use strict mode or add separate contract tests |
| Request fields pass but response fields fail | Both payloads are validated independently | Update descriptors on the failing side |
| Nested field not found | Descriptor path does not match actual JSON | Use the full path such as `supplier.country` |
| Array field mismatch | Incorrect path syntax | Use `items[].sku` for array elements |
| Java field name differs from JSON | Jackson naming strategy or `@JsonProperty` renames it | Document the JSON path on the wire |
| Internal field appears in response | DTO/serializer unintentionally exposes data | Fix the response model; do not hide leaks with ignored |
| Test does not run document snippet | Test only asserts HTTP without registering `document(...)` | Attach snippets and descriptors to the operation |
| CI misses changes | Tests are not executed or snippets use relaxed mode | Check task dependencies and strict coverage |

## 13. Asciidoctor and Build/CI Integration

When strict tests pass, field snippets are generated under the operation directory:

```text
build/generated-snippets/
└── products-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
```

Asciidoctor page including snippets:

```adoc
= Product API
:toc: left

== Create Product

=== Request fields
include::{snippets}/products-create/request-fields.adoc[]

=== Response fields
include::{snippets}/products-create/response-fields.adoc[]
```

With Gradle and the Asciidoctor plugin configured:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

CI workflow:

```text
HTTP documentation tests
          |
          v
requestFields / responseFields
          |
          v
Compare payload with descriptors
          |
          +---- Undocumented extra field -> Test FAIL
          |
          +---- Missing required descriptor -> Test FAIL
          |
          v
Generated snippets
          |
          v
Asciidoctor / Markdown export step
          |
          v
Review and publish
```

CI only catches drift if documentation tests are run and snippets use strict mode. If every operation switches to relaxed mode, new fields can slip through without review.

## 14. Hands-On Exercise

For the `POST /api/products` endpoint:

1. Write a request JSON with `name`, `price`, and `active`.
2. Use `requestFields(...)` to describe those exact three fields and run the test.
3. Add a `category` field to the request without adding a descriptor yet; observe the strict mode failure.
4. Add a descriptor for `category` and confirm the snippet is generated.
5. Add `internalTrace` to the test payload, declare `.ignored()`, and confirm the field does not appear in the table.
6. Try omitting the `note` field declared `.optional()`; confirm the test still generates snippets.
7. Add a `stock` field to the response without updating `responseFields(...)`; observe the response snippet error.
8. Try `relaxedResponseFields(...)`, observe the test allowing extra fields, and evaluate whether that choice fits the contract.
9. Create a nested `supplier.country` field and verify the descriptor path.
10. Run tests in CI and confirm the build fails when a new public field has not been reviewed.

### Self-Assessment Questions

- What does strict `requestFields(...)` detect when a payload gains a new field?
- Does `responseFields(...)` validate the request or the response?
- How does an extra field differ from a missing required descriptor?
- Does `.optional()` allow undeclared fields?
- How does `.ignored()` differ from relaxed mode?
- When should `relaxedRequestFields(...)` or `relaxedResponseFields(...)` be used?
- Why must nested field paths match the JSON on the wire?
- If a new field is leaked internal data in the response, should you simply mark it `ignored`?
- Which step must CI run to detect payload drift?

**Remember:** Strict `requestFields(...)` and `responseFields(...)` turn undocumented fields into failure signals in documentation tests. When a payload adds a field, review its meaning and decide whether to publish, ignore, or relax it according to the contract. `.optional()` handles descriptors that may be absent; `.ignored()` handles known fields omitted from the table; relaxed mode permits additional undescribed fields.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `responseFields`, relaxed fields, and field descriptors.
- [Spring REST Docs — `PayloadDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): API for documenting request/response payloads.
- [Spring REST Docs — `FieldDescriptor` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `optional`, `ignored`, and field descriptor metadata.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): including generated snippets in documentation.
