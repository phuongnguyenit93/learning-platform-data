# request-fields and response-fields

## Learning Objectives

In the **SPRING_REST_DOCS** module, an API typically exchanges JSON in both directions: the client sends a request body and the server returns a response body. Documentation needs to describe fields, data types, meanings, optionality, and nested structures. Spring REST Docs provides two default snippet categories to record this part of the contract: **request-fields** and **response-fields**.

Both snippets are generated from field descriptors declared by the test. Under default configuration, REST Docs validates descriptors against the actual payload: fields present in the payload must be handled in documentation and descriptors must match observed data. As a result, payload changes can cause documentation tests to fail rather than silently letting documentation go stale.

After this lesson, you will be able to:

- Distinguish request-fields from response-fields.
- Use requestFields and responseFields to generate snippets.
- Declare fieldWithPath, subsectionWithPath, and field description attributes.
- Document optional fields and fields that are present but not published.
- Understand default validation behavior and when to use relaxedRequestFields/relaxedResponseFields.
- Document nested objects, arrays, and payload structures.
- Diagnose errors where descriptors do not match actual requests/responses.

## 1. Two Snippets Describing Both Payload Directions

### request-fields

request-fields describes the fields in the request body sent by the client to the endpoint. Example product creation request:

```json
{
  "name": "Mechanical Keyboard",
  "price": 129.90,
  "category": "ACCESSORIES"
}
```

The test declares field descriptors to specify the path, meaning, and additional information. REST Docs generates the request-fields snippet from those descriptors.

### response-fields

response-fields describes the fields in the response body returned by the server. Example:

```json
{
  "id": 501,
  "name": "Mechanical Keyboard",
  "price": 129.90,
  "category": "ACCESSORIES",
  "createdAt": "2026-11-17T08:30:00Z"
}
```

The response may contain server-generated fields such as id or createdAt that do not appear in the request. Therefore, response descriptors often differ from request descriptors even when the two payloads share several field names.

| Snippet | Description | When Commonly Used |
| --- | --- | --- |
| request-fields | Contract of data sent by the client | POST, PUT, PATCH, or endpoints accepting a JSON body |
| response-fields | Contract of data returned by the server | GET, POST, PUT, or endpoints with a response body |

Do not use request-fields just because a test sends a request. If the endpoint has no request body, you can document path parameters, query parameters, or headers using the corresponding snippets. If the response is 204 No Content, do not create response-fields for a nonexistent body.

## 2. What Is a Field Descriptor?

A field descriptor is a declaration telling REST Docs which field in the payload to record and how to describe it.

| Component | Role |
| --- | --- |
| Field path | Path to the field in the payload, e.g., name or customer.email |
| Description | Meaning of the field for API consumers |
| Type | Data type recorded in the snippet or inferred from the payload |
| Optional | Declares that the field may be absent |
| Ignored | Field present in the payload but not documented in the snippet table |
| Attributes | Additional metadata for custom templates |

Commonly used APIs:

- fieldWithPath("...") creates a descriptor for a field or path.
- subsectionWithPath("...") documents an entire object/subsection as a single unit.
- description("...") assigns an explanation to the descriptor.
- optional() marks a field as potentially absent.
- ignored() handles a field present in the payload without displaying it as a regular field.

## 3. request-fields Example with MockMvc

Suppose the DTO is:

```java
public record CreateProductRequest(
        String name,
        BigDecimal price,
        String category
) {
}
```

MockMvc test:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": "Mechanical Keyboard",
                  "price": 129.90,
                  "category": "ACCESSORIES"
                }
                """))
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name")
                .description("Product name."),
            fieldWithPath("price")
                .description("Product selling price."),
            fieldWithPath("category")
                .description("Product category code.")
        )));
```

REST Docs generates snippets for the products-create operation. Under default configuration, the request-fields snippet contains a table with field path, type, and description. The displayed type is inferred from the payload or can be specified explicitly if needed.

Part of the generated AsciiDoc content looks like:

```asciidoc
|===
|Path|Type|Description

|name
|String
|Product name.

|price
|Number
|Product selling price.

|category
|String
|Product category code.
|===
```

This is an illustrative layout; the displayed type depends on the payload, descriptors, and snippet template of the version in use.

## 4. response-fields Example

Test:

```java
this.mockMvc.perform(get("/api/products/{id}", 501)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        responseFields(
            fieldWithPath("id")
                .description("Server-generated product identifier."),
            fieldWithPath("name")
                .description("Product name."),
            fieldWithPath("price")
                .description("Current selling price."),
            fieldWithPath("category")
                .description("Product category code."),
            fieldWithPath("createdAt")
                .description("Product creation timestamp in ISO-8601 format.")
        )));
```

The response-fields snippet is independent of request-fields. Even though name, price, and category appear in both payloads, descriptions can differ between read and write contexts. Do not reuse a single descriptor list simply because the field paths match if their meanings or optionality differ.

## 5. Optional Fields with optional()

A field may appear in some requests without being required. For example, description:

```java
requestFields(
    fieldWithPath("name")
        .description("Product name."),
    fieldWithPath("price")
        .description("Selling price."),
    fieldWithPath("description")
        .optional()
        .description("Product description; may be omitted.")
)
```

optional() means the field may be absent from the payload while the test remains valid. It does not mean the field must have a null value. The following two payloads are different:

```json
{
  "name": "Keyboard"
}
```

```json
{
  "name": "Keyboard",
  "description": null
}
```

A field that can be omitted and a field sent with a null value are two different states at the JSON level. Documentation should reflect how the API actually handles both if they have different meanings.

For responses, optional() is useful if a field only appears in certain states or resource types. The current test still needs to verify the observed response and corresponding descriptors.

## 6. ignored() Fields — Present in Payload but Not Listed

Sometimes a payload contains fields you do not want published in the documentation table:

- Internal technical fields.
- Metadata outside the focus of the operation.
- Values documented elsewhere.

You can use ignored():

```java
responseFields(
    fieldWithPath("id")
        .description("Product ID."),
    fieldWithPath("name")
        .description("Product name."),
    fieldWithPath("internalVersion")
        .ignored()
)
```

ignored() tells REST Docs that this descriptor is handled without placing it in the snippet description table as a normal field. Unlike optional(), ignored() does not mean the field can be absent; it must still match the tested payload. If you want a field that can both be absent and hidden from display, combine the appropriate states according to the descriptor API of the version in use and verify with tests.

Do not overuse ignored() to hide schema changes. If a field is part of the contract that clients need to know, document it rather than ignoring it.

## 7. Default Behavior: Strict Payload Documentation

requestFields and responseFields enforce completeness validation on the payload:

- Every actual field in the payload must be documented or handled by an appropriate descriptor.
- A descriptor pointing to a field that does not exist in the payload can fail the test.
- Field descriptors that leave part of the payload uncovered will cause the test to report undocumented fields.

This is a key strength of REST Docs: snippets are not merely handwritten text, but are verified against test payloads.

Example actual payload:

```json
{
  "id": 501,
  "name": "Keyboard",
  "status": "ACTIVE"
}
```

Yet descriptors only declare id and name:

```java
responseFields(
    fieldWithPath("id").description("Product ID."),
    fieldWithPath("name").description("Product name.")
)
```

The test may fail because status is undocumented. When the API adds a new field, the author needs to decide: add a description for status, mark it ignored if justified, or choose a relaxed strategy if the documentation intentionally covers only part of the response.

### 7.1. When a Descriptor Points to a Missing Field

If a descriptor declares category but the response lacks category, the test may report that the descriptor path was not found in the payload. Review:

- Does the test fixture have the right data?
- Did the API change its schema?
- Was the field name renamed by Jackson using @JsonProperty?
- Is the field inside a nested object or array?
- Is the descriptor intended for the right operation?

Do not mechanically fix this by marking the field optional if the field is required by the contract.

## 8. relaxedRequestFields and relaxedResponseFields

In some documentation, only part of a payload needs to be documented. REST Docs provides the relaxed API:

```java
relaxedRequestFields(
    fieldWithPath("name")
        .description("Product name.")
)
```

```java
relaxedResponseFields(
    fieldWithPath("id")
        .description("Product ID.")
)
```

Comparison:

| API | Goal | Behavior |
| --- | --- | --- |
| requestFields | Document the full request body | Unhandled fields fail the test |
| responseFields | Document the full response body | Unhandled fields fail the test |
| relaxedRequestFields | Document only the request fields of interest | Allows other unlisted fields |
| relaxedResponseFields | Document only the response fields of interest | Allows other unlisted fields |

For example, a response has id, name, status, createdAt, updatedAt, but the documentation page only explains id and name. relaxedResponseFields may be appropriate if the remaining fields are explained in general documentation or are outside the operation's focus.

### 8.1. Do Not Use Relaxed by Default

If you always use relaxedResponseFields, a new field can appear without causing the test to fail. This reduces the ability to detect API contract changes.

Prefer strict requestFields/responseFields for payloads that documentation should cover completely. Only use relaxed when the team has explicitly decided the snippet is a partial description and has another way to document the remaining fields.

## 9. Documenting Nested Objects

JSON payloads can contain child objects:

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

There are two ways to document this.

### 9.1. Documenting Each Child Field

```java
responseFields(
    fieldWithPath("id")
        .description("Product ID."),
    fieldWithPath("name")
        .description("Product name."),
    fieldWithPath("manufacturer.id")
        .description("Manufacturer ID."),
    fieldWithPath("manufacturer.name")
        .description("Manufacturer name.")
)
```

This approach fits when readers need to understand every property inside the object.

### 9.2. Documenting an Entire Subsection

```java
responseFields(
    fieldWithPath("id")
        .description("Product ID."),
    fieldWithPath("name")
        .description("Product name."),
    subsectionWithPath("manufacturer")
        .description("Manufacturer information.")
)
```

subsectionWithPath documents the entire subsection as a single unit rather than listing every child field in the current table. If you want to document manufacturer in detail, you can create a separate documentation section or another snippet for that structure.

Do not declare both the subsection and its child fields as two independent branches in the same descriptor set if they overlap. Choose the documentation approach suited for each snippet table.

## 10. Documenting Arrays and Objects Inside Arrays

Example response with a list of products:

```json
{
  "items": [
    { "id": 501, "name": "Keyboard" },
    { "id": 502, "name": "Mouse" }
  ]
}
```

You can document fields in array elements using paths:

```java
responseFields(
    fieldWithPath("items")
        .description("List of products."),
    fieldWithPath("items[].id")
        .description("Product ID."),
    fieldWithPath("items[].name")
        .description("Product name.")
)
```

The [] notation represents elements within an array for Spring REST Docs JSON payload field paths. The test must include an array with elements so descriptors can be validated against an actual payload.

If the array is empty in the test response, descriptors for items[].id may not have an actual element to verify as expected. Design fixtures with data representative of the structure you want to document, while keeping separate tests for empty collection cases when needed.

## 11. Overriding Types and Metadata

REST Docs usually infers types from the payload. If you need to specify a type explicitly:

```java
fieldWithPath("price")
    .type(JsonFieldType.NUMBER)
    .description("Selling price in the API's currency unit.")
```

Common JSON types include STRING, NUMBER, BOOLEAN, OBJECT, ARRAY, and NULL. Specifying types explicitly can make documentation consistent, but they must match the actual payload.

You can add attributes:

```java
fieldWithPath("price")
    .type(JsonFieldType.NUMBER)
    .description("Selling price.")
    .attributes(key("constraints").value("Greater than 0"))
```

Attributes are only useful if the snippet template reads and renders that key. Default templates do not automatically display every custom attribute. If you need a dedicated column or row, customize the snippet template.

## 12. Pattern for Organizing Request and Response Descriptors

A test typically places request and response payload descriptors near each other while keeping them separate:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price."),
            fieldWithPath("category").description("Product category.")
        ),
        responseFields(
            fieldWithPath("id").description("Server-generated product ID."),
            fieldWithPath("name").description("Saved product name."),
            fieldWithPath("price").description("Saved selling price."),
            fieldWithPath("category").description("Product category."),
            fieldWithPath("createdAt").description("Creation timestamp.")
        )));
```

In this example, the request has three fields while the response adds id and createdAt. The two descriptor lists reflect two different schemas.

When a test has a response without a body, omit responseFields. When a request has no body, omit requestFields. Do not create empty descriptors just to force every test into the same structure.

## 13. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Test reports undocumented fields | Payload has fields not handled by descriptors | Add descriptors or use ignored/relaxed with a clear rationale |
| Test reports descriptor did not find field | Wrong path or payload lacks the field | Compare against actual JSON, Jackson names, and path |
| Optional field fails test when absent | Not marked optional | Use optional if the field can genuinely be omitted |
| Null field and absent field confused | Confusing optional with allowing null values | Identify and test both cases separately |
| Snippet does not display custom attribute | Template does not render the attribute | Customize the snippet template or fold it into description |
| Nested object lacks child details | Used subsectionWithPath | Use fieldWithPath for each child field if a detailed table is needed |
| Array path does not match | Wrong path syntax or empty array fixture | Check items[].field syntax and provide a representative fixture |
| Response changed yet docs still pass | Using relaxedResponseFields | Consider switching back to strict responseFields |
| request-fields present for bodyless endpoint | Chose wrong snippet for request type | Use parameter/header snippets or remove request-fields |

## 14. Hands-on Exercise

1. Create a POST /api/products endpoint accepting name, price, and category.
2. Write a MockMvc test using requestFields to document the full request body.
3. Have the endpoint return id, name, price, category, and createdAt; use responseFields to document the response body.
4. Add description as an optional field and verify the test still passes when the field is absent.
5. Add an internalVersion field and mark it ignored if you genuinely do not want it shown in the snippet.
6. Add a new field to the response JSON without adding a descriptor yet; observe strict responseFields failing the test.
7. Try relaxedResponseFields and explain the trade-off regarding schema drift detection.
8. Add a manufacturer object and items array; document one with subsectionWithPath and the other with detailed paths.

**Self-assessment questions**

1. Which two parts of an HTTP exchange do request-fields and response-fields describe?
2. Why should request descriptors and response descriptors be kept separate?
3. How does optional() differ from ignored()?
4. What kind of changes do strict requestFields/responseFields help detect?
5. When is relaxedResponseFields an appropriate choice?
6. How do fieldWithPath and subsectionWithPath differ in purpose?
7. What does the items[].id syntax represent?
8. Do custom attributes appear automatically in default snippets?

## Official References

- [Spring REST Docs — Documenting Request/Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): requestFields, responseFields, and relaxed variants.
- [Spring REST Docs — Payload Documentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): API for generating payload field snippets.
- [FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): optional, ignored, type, description, and attributes.
- [JsonFieldType API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/JsonFieldType.html): JSON types used in descriptors.

**Practical conclusion:** Use requestFields and responseFields to document payload contracts in each direction. Start with full descriptors so tests strictly validate payloads; use optional for fields that may be omitted, ignored for fields that do not need to be displayed, and relaxed only when documentation intentionally describes a partial payload. For nested objects and arrays, choose detailed field paths or subsections as appropriate, then run tests to verify snippets accurately reflect the actual JSON.
