# Missing Field Descriptors Cause Test Failures

## Learning Objectives

In the **SPRING_REST_DOCS** module, `request-fields` and `response-fields` do more than generate payload description tables. By default, they also check whether all fields appearing in the HTTP payload have been handled in descriptors. If an endpoint returns an extra field that the documentation does not mention yet, the documentation test can fail. This mechanism helps teams detect schema drift and forces authors to decide whether to publish the new field, intentionally ignore it, or document only part of the payload.

After this lesson, you will be able to:

- Explain why a missing field descriptor causes strict payload snippets to fail.
- Distinguish an undocumented field from a descriptor pointing to a non-existent field.
- Use `fieldWithPath`, `subsectionWithPath`, `optional`, and `ignored` for their intended purposes.
- Choose between `requestFields`/`responseFields` and their relaxed variants.
- Handle nested objects, arrays, and new fields in responses.
- Read REST Docs error messages to identify which descriptors need updating.
- Maintain strict documentation checks as an API evolves.

## 1. Why Does REST Docs Validate Field Descriptors?

Suppose an API returns this response:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90
}
```

The test documents the response:

```java
this.mockMvc.perform(get("/api/products/{id}", 501)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        responseFields(
            fieldWithPath("id").description("Product ID."),
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price.")
        )));
```

The descriptors cover all three fields. REST Docs can generate `response-fields.adoc` from that payload and those descriptors.

Suppose the endpoint is changed to also return `status`:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90,
  "status": "ACTIVE"
}
```

If the test still only describes `id`, `name`, and `price`, strict `responseFields` detects that `status` has not been handled and fails the documentation test. The author must decide:

- Add a descriptor and explain `status` in the documentation.
- Mark `status` as `ignored` if there is a clear reason not to publish that field.
- Use `relaxedResponseFields` if the operation intentionally documents only part of the response.

The key point: a new field cannot silently slip into the payload while making full documentation appear up to date. The test requires the team to review schema changes before accepting the documentation.

## 2. Strict requestFields and responseFields

The two default APIs:

```java
requestFields(
    fieldWithPath("name").description("Product name."),
    fieldWithPath("price").description("Selling price.")
)
```

```java
responseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name.")
)
```

Strict payload snippets perform two-way matching:

1. **Payload to descriptor:** fields in the payload must be described or handled by an appropriate descriptor. Undocumented fields can cause the snippet to fail.
2. **Descriptor to payload:** declared paths must exist in the payload, unless the descriptor is marked `optional`. Misspelled or absent descriptors can also cause the test to fail.

| Scenario | Typical strict mode behavior |
| --- | --- |
| Payload has a new field without a descriptor | Reports undocumented field |
| Descriptor declares a non-existent path | Reports descriptor path not found |
| Descriptor has optional and field is absent | Accepted |
| Descriptor has ignored and field is present | Handled but omitted from the description table |

Strict mode is the appropriate default when a snippet is expected to fully document the operation's payload.

## 3. Example Failure When a Response Has a New Field

Actual response:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90,
  "status": "ACTIVE"
}
```

Old descriptors:

```java
responseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name."),
    fieldWithPath("price").description("Selling price.")
)
```

When running the test, REST Docs may report that the payload contains undocumented fields, specifically `status`. The exact error wording may vary by version and payload structure, but the resolution path is to inspect the reported field list and compare it against the actual response.

Update the descriptors:

```java
responseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name."),
    fieldWithPath("price").description("Selling price."),
    fieldWithPath("status").description("Current status of the product.")
)
```

If `status` is part of the contract clients rely on, this is the right fix. Re-run the documentation test to verify the new field is included in the snippet.

## 4. New Fields in Requests

Suppose the initial request is:

```json
{
  "name": "Keyboard",
  "price": 129.90
}
```

The API adds a `currency` field:

```json
{
  "name": "Keyboard",
  "price": 129.90,
  "currency": "VND"
}
```

If `requestFields` does not yet have a descriptor for `currency`, the test detects that the payload contains an undocumented field. This is helpful because a new request field can change how clients construct data.

Updated descriptors:

```java
requestFields(
    fieldWithPath("name").description("Product name."),
    fieldWithPath("price").description("Selling price."),
    fieldWithPath("currency").description("ISO 4217 currency code.")
)
```

If `currency` is only sent when clients want to override the default unit, the descriptor can be marked `optional`:

```java
fieldWithPath("currency")
    .optional()
    .description("Currency code; may be omitted to use the default unit.")
```

`optional` allows the field to be absent in the test payload; if the field appears, it is still documented. Do not use `optional` to handle a new field without first knowing whether it is genuinely optional.

## 5. fieldWithPath and subsectionWithPath for Nested Objects

Nested payload:

```json
{
  "id": 501,
  "name": "Keyboard",
  "manufacturer": {
    "id": 8,
    "name": "Acme"
  }
}
```

### 5.1. Describing Each Nested Field

```java
responseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name."),
    fieldWithPath("manufacturer.id")
        .description("Manufacturer ID."),
    fieldWithPath("manufacturer.name")
        .description("Manufacturer name.")
)
```

When using detailed field paths, you must cover the nested fields of the object the snippet is describing. If the API adds `manufacturer.country` and descriptors do not handle it yet, strict mode can report the new field.

### 5.2. Describing an Entire Subsection

If there is no need to list each child field in the current table, use `subsectionWithPath`:

```java
responseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name."),
    subsectionWithPath("manufacturer")
        .description("Manufacturer information.")
)
```

`subsectionWithPath` marks the entire child object as a documented section. When using it, child fields are covered by the subsection descriptor instead of needing separate entries in the same table.

Choose one approach depending on your goal:

- Use detailed `fieldWithPath` if readers need to know every property.
- Use `subsectionWithPath` if documentation only needs to explain the object as a single unit.

Avoid both describing a subsection and adding overlapping child descriptors in the same descriptor set unless intentionally supported by REST Docs.

## 6. Arrays and Objects Inside Arrays

Response:

```json
{
  "items": [
    {"id": 10, "name": "Keyboard"},
    {"id": 11, "name": "Mouse"}
  ]
}
```

Descriptors:

```java
responseFields(
    fieldWithPath("items").description("List of products."),
    fieldWithPath("items[].id").description("Product ID."),
    fieldWithPath("items[].name").description("Product name.")
)
```

The path `items[].name` describes the `name` field within elements of the array. If the API adds `category` to each element, strict descriptors can detect that field and require an update.

If you want to describe the entire element as a substructure, consider a subsection descriptor suited to the payload and verify it with tests. With an empty array, the fixture provides no sample element to validate inner paths; write a documentation test with representative data when element schema documentation is needed.

## 7. optional(), ignored(), and relaxed: Not the Same Meaning

These three options are often used interchangeably, yet they solve different problems.

| Approach | When to use | Undeclared new fields |
| --- | --- | --- |
| Add field descriptor | Field is part of the published contract | Clearly documented |
| optional() | Field is known but may be absent | Still detected if another field is undocumented |
| ignored() | Field is known and intentionally omitted from the snippet table | Only the ignored field is handled |
| relaxedRequestFields/relaxedResponseFields | Intentionally documenting only part of the payload | Other unlisted fields are ignored |

### 7.1. optional()

Example:

```java
fieldWithPath("description")
    .optional()
    .description("Description; may be absent.")
```

The descriptor still appears in the snippet table when present. `optional` only adjusts whether the field is required to appear in the test payload.

### 7.2. ignored()

Example:

```java
fieldWithPath("internalVersion").ignored()
```

This field is handled during payload validation but is not rendered like a regular documented field. `ignored` is not a way to mark an optional field, nor does it automatically allow that field to be absent.

Use `ignored` when a field has been evaluated and there is a deliberate reason not to show it in the current table. For sensitive fields, also check whether the API should even return that field; `ignored` is only a snippet display choice, not a security measure.

### 7.3. relaxedRequestFields and relaxedResponseFields

Example response wanting to highlight only `id` and `name`:

```java
relaxedResponseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name.")
)
```

The payload may contain other fields not listed by descriptors without failing the test for missing descriptions. However, declared paths must still be valid in the payload unless marked `optional`.

Relaxed mode fits perspective-based documentation or partial schemas. Switching strict to relaxed merely to make a test pass reduces your ability to catch new fields.

## 8. When to Add a Descriptor vs. When to Use Relaxed?

Use these questions to decide:

1. Does the new field help clients send requests or understand responses? If yes, add a descriptor with a clear description.
2. Is the field already defined as optional in the contract? If yes, use `optional`.
3. Is the field reviewed and intentionally excluded from the table? If yes, consider `ignored`.
4. Does the documentation page intentionally describe only part of the payload while the rest is explained elsewhere? If yes, relaxed may fit.
5. Unsure why the field appeared? Keep strict mode and investigate the schema and behavior before changing descriptors.

For example, a response contains a new `debug` field. Do not automatically mark it `ignored`. First determine whether that field leaks internal data, belongs to the public API, and needs to be removed from the response. A documentation decision does not replace API design review.

## 9. Reading and Resolving Descriptor Errors

When a test fails, work through it in order:

### Case A: Undocumented Field in Payload

1. Read the field/path name reported in the error.
2. Inspect the test's actual response/request body.
3. Determine whether the new field is an intentional change, an internal field, or an unintended serialization artifact.
4. Add a descriptor, `ignored`, or switch to relaxed per contract decisions.
5. Re-run the test and inspect the generated snippet.

### Case B: Descriptor Path Does Not Exist

1. Check spelling and casing of the field path.
2. Inspect the actual JSON, including names serialized by Jackson.
3. Check which object or array the field lives in.
4. Determine whether the field was removed/renamed or simply absent in the fixture.
5. If the field can genuinely be absent, use `optional`; otherwise fix the DTO/fixture or descriptor according to the contract.

### Case C: Nested Payload Changes

1. Identify whether the field is at the root, in a child object, or inside an array element.
2. Match descriptor paths against the JSON structure.
3. Choose detailed `fieldWithPath` or `subsectionWithPath`.
4. Add fixtures with enough representative data for the nested structure.

Do not resolve failures by adding `ignored` to every missing field. That destroys the valuable signal from strict mode.

## 10. Full Example: API Adds a Field to the Response

Initially:

```java
this.mockMvc.perform(get("/api/orders/{id}", 7001))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7001))
    .andDo(document("orders-get",
        responseFields(
            fieldWithPath("id").description("Order ID."),
            fieldWithPath("total").description("Order total amount.")
        )));
```

After an API change, the response includes `currency`:

```json
{
  "id": 7001,
  "total": 250000,
  "currency": "VND"
}
```

The old test lacks assertions and a descriptor for `currency`. Strict `responseFields` detects the unhandled new field. Update the test:

```java
this.mockMvc.perform(get("/api/orders/{id}", 7001))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7001))
    .andExpect(jsonPath("$.currency").value("VND"))
    .andDo(document("orders-get",
        responseFields(
            fieldWithPath("id").description("Order ID."),
            fieldWithPath("total").description("Order total amount."),
            fieldWithPath("currency").description("Currency code of the total amount.")
        )));
```

The change is verified at two layers:

- Assertions confirm the `currency` value matches the fixture/contract.
- Descriptors ensure `currency` is explained in the documentation.

If `currency` is only optional information, the test needs an additional case where the response omits `currency` and an `optional` descriptor. Optionality cannot be concluded solely from a single sample response containing the field.

## 11. Distinguishing REST Docs Errors from Endpoint Assertion Failures

A documentation test can fail for multiple reasons:

| Error type | Example | Where to fix |
| --- | --- | --- |
| HTTP assertion | Status is not 200 as expected | Endpoint, test data, or contract |
| Body/header assertion | Wrong JSON value or missing Content-Type | Endpoint behavior |
| Missing field descriptor | Payload has a new undocumented field | Descriptors or schema |
| Descriptor path invalid | Describes a non-existent field | Path, fixture, or optional |
| Snippet generation | Cannot write file, misconfigured snippet | REST Docs/test setup |
| Asciidoctor include | Include points to a non-existent file | Operation ID, snippet name, or build path |

Read the error type before fixing. If a status assertion fails, adding a descriptor will not solve the problem. If a strict snippet reports an undocumented field, adding more JSONPath assertions without updating descriptors will not resolve that failure either.

## 12. Workflow for Reviewing Schema Changes

When a documentation test reports a missing field descriptor:

1. Inspect the diff of the DTO/controller/serializer and the actual JSON.
2. Determine whether the field belongs to the public contract.
3. Check the field's name, type, nullability/optionality, and meaning.
4. If the field is public, add a descriptor and assertions for important values/types.
5. If the field should not be public, fix the response or serializer instead of merely marking it `ignored`.
6. If the field has been reviewed and falls outside this table's scope, consider `ignored` or relaxed and state the reason clearly in code review.
7. Run documentation tests and compile the docs to verify both snippets and includes.

Strict mode turns payload changes into an intentional review point. It does not automatically judge whether a new schema is good or bad; the development team still evaluates the meaning of the change.

## 13. Hands-On Exercise

1. Create a `GET /api/products/{id}` endpoint returning `id`, `name`, and `price`.
2. Write strict `responseFields` for all three fields and get the test passing.
3. Add `status` to the JSON response without updating descriptors yet; observe the undocumented field failure.
4. Add a `status` descriptor and a JSONPath assertion for the value `ACTIVE`.
5. Add a `manufacturer` object; try describing each nested field with `fieldWithPath`.
6. Switch to `subsectionWithPath` and observe the difference in the snippet.
7. Add a `description` field that may be absent; use `optional` and test payloads both with and without the field.
8. Add an `internalVersion` field; try `ignored` after deciding why it should not be published.
9. Try `relaxedResponseFields` in another test and explain which schema changes strict mode would catch that relaxed mode misses.

**Self-Assessment Questions**

1. Why does strict `responseFields` fail a test when the payload gains a new field?
2. How does strict mode validate both payload-to-descriptor and descriptor-to-payload?
3. How does `optional` differ from `ignored`?
4. How does `subsectionWithPath` help handle nested objects?
5. Why can `relaxedResponseFields` allow a new field to go undetected?
6. When should you add a descriptor instead of using `ignored`?
7. What issues can a non-existent descriptor path indicate?
8. Why are JSONPath assertions and field descriptors two distinct verification layers?

## Official References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `responseFields`, relaxed variants, field descriptors, and nested payloads.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): API for creating payload snippets.
- [FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): `description`, `optional`, `ignored`, and attributes.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): verifying HTTP exchanges and generating snippets.

**Practical Takeaway:** When strict `requestFields` or `responseFields` reports a missing descriptor, treat it as a prompt to review a payload change. Add a descriptor if the field belongs to the contract, `optional` if it may be absent, `ignored` if you deliberately exclude it from display, or relaxed when documentation intentionally covers only a subset. Keep strict mode on operations that require complete documentation so tests continue catching schema drift.
