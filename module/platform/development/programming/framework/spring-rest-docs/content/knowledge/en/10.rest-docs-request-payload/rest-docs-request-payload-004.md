# Array Fields, Array Elements, and Dynamic Indices in Spring REST Docs

## 1. Why do JSON arrays need dedicated documentation?

In REST APIs, request bodies often contain lists of products, tags, addresses, permissions, or nested data groups. Unlike an object with a fixed set of keys, **an array varies in element count and ordering from request to request**. Therefore, documentation needs to express the general structure of the elements rather than tying descriptions to the first, second, or third position.

In the **Request payload** chapter of **Spring REST Docs**, `requestFields(...)` declares the paths of fields sent in an HTTP request; `fieldWithPath(...)` uses the `[]` notation to reference elements of an array without depending on a specific index. Snippets are generated from HTTP tests using MockMvc, WebTestClient, or REST Assured, then included in Asciidoctor documentation or a Markdown export pipeline in the build/CI.

After this lesson, you will be able to:

- Distinguish between paths pointing to **the entire array**, **any single element**, and **a field of an object inside the array**.
- Document string arrays, object arrays, arrays within arrays, and objects containing multiple array levels.
- Understand why `items[].sku` is preferable to `items[0].sku` when documenting a list contract with dynamic indices.
- Write MockMvc tests that generate `request-fields.adoc`, even when element ordering changes.
- Properly handle empty arrays, absent arrays, `null` elements, optional fields inside elements, and array size constraints.

## 2. Three levels of documentation: array, element, and child field

Suppose the `POST /api/orders` API accepts JSON:

```json
{
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2,
      "options": [
        { "name": "cover", "value": "hard" }
      ],
      "note": "Gift wrap"
    },
    {
      "sku": "PEN-002",
      "quantity": 1,
      "options": [
        { "name": "ink", "value": "blue" }
      ]
    }
  ],
  "tags": ["gift", "standard"],
  "batches": [
    ["A-1", "A-2"],
    ["B-1"]
  ]
}
```

From this JSON, there are three fundamental path levels:

```text
items            -> entire items array
items[]          -> one element of the items array
items[].sku      -> sku field of an object inside items
```

| JSON path | Structure described | Common type |
| --- | --- | --- |
| `items` | Entire list of items | `ARRAY` |
| `items[]` | One item element | `OBJECT` |
| `items[].sku` | SKU of an item element | `STRING` |
| `items[].quantity` | Quantity of an item element | `NUMBER` |
| `items[].options` | Options array of each item | `ARRAY` |
| `items[].options[]` | One option object | `OBJECT` |
| `items[].options[].name` | Name of an option | `STRING` |
| `tags` | Entire list of tags | `ARRAY` |
| `tags[]` | One tag in the list | `STRING` |
| `batches` | Outer array of groups | `ARRAY` |
| `batches[]` | One group, itself an array | `ARRAY` |
| `batches[][]` | One code inside a group | `STRING` |

Note that `items[]` and `items[].sku` are not synonymous: the first path is **the element object**, while the second path is **a field inside that object**. Similarly, `tags` is an array whereas `tags[]` is a string.

### 2.1. Declaring the entire array

```java
import org.springframework.restdocs.payload.JsonFieldType;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("List of items in the order")
```

The `items` path explains the purpose of the list. It does not yet fully describe which properties each element has. Therefore, for public APIs, you should also include child-field descriptors.

### 2.2. Declaring an array element

```java
fieldWithPath("items[]")
        .type(JsonFieldType.OBJECT)
        .description("An item in the order")
```

The `[]` syntax is the key part. It represents a **non-fixed** element position in the array, suitable for a list that may contain one, two, or hundreds of elements.

### 2.3. Declaring fields of each element

```java
fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Product SKU");

fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Order quantity");
```

In the documentation, this serves as **the general structural template** for the object elements. These description rows are not duplicated based on the number of elements in the sample JSON.

> `[]` in a Spring REST Docs path is the syntax for describing array elements. Do not replace it with invented placeholders like `[i]`, `${index}`, or JSONPath syntax `[*]` without checking the rules of the API being used.

## 3. Dynamic indices: why should documentation not be tied to `[0]`?

Consider two requests sharing the same contract, differing only in item order:

**Request A:**

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 },
    { "sku": "PEN-002", "quantity": 1 }
  ]
}
```

**Request B:**

```json
{
  "items": [
    { "sku": "PEN-002", "quantity": 1 },
    { "sku": "BOOK-001", "quantity": 2 }
  ]
}
```

In JSON, the first element is at index `0` and the next is at index `1`. But that index only describes **position within one specific request**. It does not govern what `sku` or `quantity` an item must have.

To document the shared structure across both requests, write:

```java
fieldWithPath("items[].sku")
        .description("Product SKU of each item");

fieldWithPath("items[].quantity")
        .description("Quantity of each item");
```

If documentation points only to `items[0].sku`, the description focuses on the element **at index 0** and fails to clearly express that all elements must follow the same structure. A specific index is occasionally useful when handling errors at a particular element, but it is not the default way to represent the schema of a dynamically sized list.

| Notation | Meaning | Suitable for list API documentation? |
| --- | --- | --- |
| `items` | Entire array | Yes, to describe the list |
| `items[]` | Any element | Yes, to describe the element type |
| `items[].sku` | `sku` field of any element | Yes, to describe the shared structure |
| `items[0].sku` | `sku` field at one specific position | Only use when that position has special meaning in the contract |
| `items[i].sku` | Using `i` as an index variable | Not standard placeholder syntax for `fieldWithPath` |

**Exception example:** if an API defines `coordinates` as `[latitude, longitude]`, positions `0` and `1` have different business meanings. That contract differs from a list of identically structured objects. When documenting it, clearly explain the positional semantics and use techniques suited to your library/version; do not assume every array has interchangeable elements.

### Does `[]` automatically guarantee every element is valid?

Do not infer that simply having `requestFields(fieldWithPath("items[].sku"))` pass means **every** object in `items` has been thoroughly validated. REST Docs checks field coverage and descriptions against the **sample payload**; it is not a JSON Schema validator for all elements and all requests.

To guarantee that every item has a non-blank `sku` and `quantity` greater than 0, you need application-level validation and dedicated tests for cases where an element in the middle or end of the array is invalid.

## 4. Common array patterns

### 4.1. Array of primitive values

```json
{
  "tags": ["urgent", "gift", "fragile"]
}
```

```java
fieldWithPath("tags")
        .type(JsonFieldType.ARRAY)
        .description("Order tags");

fieldWithPath("tags[]")
        .type(JsonFieldType.STRING)
        .description("An order tag");
```

If the contract only needs to say "list of tags", describing just `tags` may suffice. If consumers need to know the type of each tag, allowed values, or the meaning of each element, adding `tags[]` is clearer.

### 4.2. Array of objects with optional fields

```json
{
  "items": [
    { "sku": "A", "quantity": 1, "note": "Priority" },
    { "sku": "B", "quantity": 2 }
  ]
}
```

```java
fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Product SKU");

fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Quantity");

fieldWithPath("items[].note")
        .type(JsonFieldType.STRING)
        .description("Item-specific note")
        .optional();
```

`.optional()` allows the `items[].note` descriptor to lack corresponding data in the sample payload. However, it does not fully express the rule "omitting `note` is permitted on any element". For contracts requiring strict verification, add tests containing multiple elements with different field combinations.

### 4.3. Array of objects containing an array of objects

```json
{
  "items": [
    {
      "sku": "SHIRT-001",
      "options": [
        { "name": "size", "value": "M" },
        { "name": "color", "value": "navy" }
      ]
    }
  ]
}
```

```java
fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("List of items");

fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Item SKU");

fieldWithPath("items[].options")
        .type(JsonFieldType.ARRAY)
        .description("Item options");

fieldWithPath("items[].options[].name")
        .type(JsonFieldType.STRING)
        .description("Option name");

fieldWithPath("items[].options[].value")
        .type(JsonFieldType.STRING)
        .description("Option value");
```

Read `items[].options[].name` from left to right: enter an object in `items`, then enter an object in that item's `options`, and finally reach the `name` field.

### 4.4. Arrays nested inside arrays

```json
{
  "batches": [
    ["A-1", "A-2"],
    ["B-1"]
  ]
}
```

```java
fieldWithPath("batches")
        .type(JsonFieldType.ARRAY)
        .description("List of code groups");

fieldWithPath("batches[]")
        .type(JsonFieldType.ARRAY)
        .description("A code group");

fieldWithPath("batches[][]")
        .type(JsonFieldType.STRING)
        .description("A code belonging to a group");
```

Each pair of `[]` indicates one array level. For more complex structures, such as `groups[]` containing objects with `members[]`, the path to a member's name is `groups[].members[].name`.

### 4.5. Array with mixed element types

Example:

```json
{
  "values": ["A", 10, true]
}
```

This is a mixed array of String, Number, and Boolean. You can describe `values` itself with `JsonFieldType.ARRAY`, but you **should not claim** `values[]` has type `STRING`. If the contract accepts heterogeneous types, clearly document the classification rules and add tests for each type; you may need `JsonFieldType.VARIES` or a dedicated documentation approach depending on the actual structure and the REST Docs version in use. In APIs you design yourself, a uniform structure is usually easier for clients to handle.

## 5. MockMvc test generating `request-fields.adoc`

Assumed implementation setup:

- The project uses Spring Boot 3.x, Java 17, JUnit 5, MockMvc, and Spring REST Docs.
- The `POST /api/orders` endpoint already exists and returns `201 Created` for valid requests.
- Test dependencies `spring-boot-starter-test` and `spring-restdocs-mockmvc` are present.

The test below describes the item list, options list, tags, and nested arrays. The goal is to generate snippets based on the HTTP requests actually sent.

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
class OrderArrayDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
            fieldWithPath("items")
                    .type(JsonFieldType.ARRAY)
                    .description("Items in the order"),
            fieldWithPath("items[].sku")
                    .type(JsonFieldType.STRING)
                    .description("Product SKU"),
            fieldWithPath("items[].quantity")
                    .type(JsonFieldType.NUMBER)
                    .description("Order quantity"),
            fieldWithPath("items[].options")
                    .type(JsonFieldType.ARRAY)
                    .description("Options for the item"),
            fieldWithPath("items[].options[].name")
                    .type(JsonFieldType.STRING)
                    .description("Option name"),
            fieldWithPath("items[].options[].value")
                    .type(JsonFieldType.STRING)
                    .description("Option value"),
            fieldWithPath("items[].note")
                    .type(JsonFieldType.STRING)
                    .description("Item-specific note")
                    .optional(),
            fieldWithPath("tags")
                    .type(JsonFieldType.ARRAY)
                    .description("Order tags"),
            fieldWithPath("tags[]")
                    .type(JsonFieldType.STRING)
                    .description("An order tag"),
            fieldWithPath("batches")
                    .type(JsonFieldType.ARRAY)
                    .description("List of code groups"),
            fieldWithPath("batches[]")
                    .type(JsonFieldType.ARRAY)
                    .description("A code group"),
            fieldWithPath("batches[][]")
                    .type(JsonFieldType.STRING)
                    .description("A code within the group")
    };

    private void verifyAndDocument(String snippetName, String requestJson)
            throws Exception {
        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document(snippetName,
                        requestFields(ORDER_REQUEST_FIELDS)));
    }

    @Test
    void documentOrderWithArrays() throws Exception {
        String requestJson = """
                {
                  "items": [
                    {
                      "sku": "BOOK-001",
                      "quantity": 2,
                      "options": [
                        { "name": "cover", "value": "hard" }
                      ],
                      "note": "Gift wrap"
                    },
                    {
                      "sku": "PEN-002",
                      "quantity": 1,
                      "options": [
                        { "name": "ink", "value": "blue" }
                      ]
                    }
                  ],
                  "tags": ["gift", "standard"],
                  "batches": [["A-1", "A-2"], ["B-1"]]
                }
                """;

        verifyAndDocument("orders-arrays", requestJson);
    }

    @Test
    void documentOrderWithReorderedItems() throws Exception {
        String requestJson = """
                {
                  "items": [
                    {
                      "sku": "PEN-002",
                      "quantity": 1,
                      "options": [
                        { "name": "ink", "value": "blue" }
                      ]
                    },
                    {
                      "sku": "BOOK-001",
                      "quantity": 2,
                      "options": [
                        { "name": "cover", "value": "hard" }
                      ],
                      "note": "Gift wrap"
                    }
                  ],
                  "tags": ["standard", "gift"],
                  "batches": [["B-1"], ["A-1", "A-2"]]
                }
                """;

        verifyAndDocument("orders-arrays-reordered", requestJson);
    }
}
```

Both tests use **the same `FieldDescriptor` array**, while the order of `items`, `tags`, and `batches` is reversed. This illustrates the role of `[]`: the documentation describes **the structure of the elements**, independent of current ordering. Using two distinct snippet names also prevents the two documentation runs from writing to the same directory.

When the tests pass their HTTP assertions and snippet generation, the output typically contains:

```text
build/generated-snippets/
├── orders-arrays/
│   └── request-fields.adoc
└── orders-arrays-reordered/
    └── request-fields.adoc
```

Each directory may also contain other snippets such as `http-request.adoc`, `http-response.adoc`, and `curl-request.adoc` depending on configuration. If the actual endpoint returns a different status code, adjust `.andExpect(...)` to match the contract instead of changing endpoint behavior just to run the example.

### What does this test verify?

It confirms that the sample request is sent to the endpoint, the HTTP status matches expectations, and the descriptors can generate the request fields table. It does not by itself prove that:

- `items` always has at least one element.
- Every element of `items` always has a non-blank `sku`.
- `quantity` is always a positive integer.
- Values in `tags` are unique.
- Each `options` entry has a valid name and non-blank `value`.
- Any permutation of order yields the same business result.

To verify these conditions, add validation and endpoint tests for specific valid and invalid cases.

## 6. Empty arrays, absent fields, and `null` values

The following three requests differ in contract semantics:

```json
{ "items": [] }
```

```json
{}
```

```json
{ "items": null }
```

| Case | JSON meaning | API decision required |
| --- | --- | --- |
| `"items": []` | `items` field is present as an empty array | Is an order list with zero items accepted? |
| `items` omitted | `items` field is not sent | Is it treated as valid or given a default value? |
| `"items": null` | `items` key is present, but its value is `null` | Is `null` allowed or must it be rejected? |

`.optional()` applies to describing a field that **may be absent** in the documented payload. It does not mean the array is allowed to be empty or `null`. Those rules must be expressed in validation and HTTP tests.

With an **empty array**, paths such as `items[].sku` have no elements to match against. Consequently, a documentation test with required child descriptors may fail or lack representative sample data. Good practice is:

1. Generate the field table from a request with representative elements.
2. Write a separate test for `items: []` to confirm the business contract.
3. Write separate tests for omitting `items` and for `items: null`.
4. In the `items` description, state element count limits if any exist.

### Adding Bean Validation to enforce real rules

Example DTO for the create-order API:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

record CreateOrderRequest(
        @NotEmpty List<@Valid OrderItemRequest> items,
        List<@NotBlank String> tags
) {}

record OrderItemRequest(
        @NotBlank String sku,
        @Min(1) int quantity,
        List<@Valid OrderOptionRequest> options,
        String note
) {}

record OrderOptionRequest(
        @NotBlank String name,
        @NotBlank String value
) {}
```

In this example:

- `@NotEmpty` requires `items` to be non-`null` and have at least one element.
- `List<@Valid OrderItemRequest>` enables validation on element objects when the framework runs validation.
- `@NotBlank` is used for strings that must contain content.
- `@Min(1)` requires `quantity` to be at least 1.
- `options` and `tags` are not forced to have elements unless the contract adds further constraints.

The controller must declare `@Valid` appropriately, such as `create(@Valid @RequestBody CreateOrderRequest request)`, along with the validation dependency. Negative HTTP tests are still needed to verify that the server rejects invalid data according to the contract, such as returning `400 Bad Request`.

**Note:** the DTO example illustrates basic rules; to validate that a list contains no `null` elements, enforces uniqueness, or satisfies cross-element relationships, add corresponding constraints and tests.

## 7. Common pitfalls with array paths

### 7.1. Confusing `items.sku` with `items[].sku`

`items` is an array, so you cannot jump straight to `sku` with a dot as if it were an object. You must step through array elements: `items[].sku`.

### 7.2. Confusing `tags` with `tags[]`

`tags` is an array; `tags[]` is an element value. If `tags` contains Strings, describing `tags[]` as `JsonFieldType.ARRAY` misrepresents the data.

### 7.3. Using `*` instead of `[]`

`*` is typically used for **dynamic object key names**, such as `attributes.*`; `[]` is used to traverse **array elements**. Do not use `items.*.sku` in place of `items[].sku` when `items` is an array.

### 7.4. Treating `.optional()` as per-element validation

An `.optional()` descriptor may be absent from the sample payload. It does not replace a rule such as "in every object, `sku` must be present and non-blank". Test cases where the first, middle, or last element is missing an important field, especially for APIs accepting long lists.

### 7.5. Heterogeneous object arrays

If the first element has `{ "sku": "A" }` and the second element has `{ "productCode": "B" }`, a single general table describing only `items[].sku` can be misleading. Clarify whether the API supports element variants; when multiple kinds exist, use a discriminator, validation rules, and documentation per variant.

### 7.6. Documenting only the parent array and assuming it is complete

A descriptor like `fieldWithPath("items")` can be considered by REST Docs to cover its child structure when checking for undocumented fields. Therefore, a passing test does not mean documentation readers know about `sku`, `quantity`, and `options`. For APIs that need to publish a detailed contract, list the important child descriptors.

## 8. Including snippets in Asciidoctor, Markdown, and CI

After the documentation test succeeds, you can include the `orders-arrays/request-fields.adoc` snippet in an Asciidoctor document:

```adoc
= Orders API
:toc: left

== Create order

=== JSON request

include::{snippets}/orders-arrays/http-request.adoc[]

=== Request payload fields

include::{snippets}/orders-arrays/request-fields.adoc[]
```

The `{snippets}` attribute must point to the directory generated by tests, such as `build/generated-snippets`. With Gradle and the Asciidoctor plugin configured in the project, the task wiring looks like:

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

In CI, a sensible pipeline order is:

```text
HTTP tests + REST Docs -> generated snippets -> Asciidoctor/Markdown -> published documentation
```

If a test describing the request fails due to a schema change, the build should fail so stale documentation is not published. If the project outputs **Markdown**, configure the appropriate templates or conversion step; do not assume `request-fields.md` is created out of the box by Spring REST Docs.

## 9. Quick troubleshooting table

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| `items[].sku` descriptor does not match | JSON uses a different array name or the structure is not an array | Compare against actual JSON and fix the path |
| `items.sku` descriptor does not match | Missing `[]` at the array level | Write `items[].sku` |
| Test passes with populated data but fails on empty array | Required child descriptor has no representative element | Create a snippet-generating test with representative elements and a separate empty-array test |
| `tags[]` description has the wrong type | Confused the array itself with an element value | Separate `tags` (`ARRAY`) and `tags[]` (`STRING`) |
| API still accepts `quantity=0` | Only declared descriptors, no validation yet | Add `@Min(1)` and endpoint tests |
| Adding a field to an element causes documentation test to fail | Strict `requestFields` mode detected an undocumented field | Add a descriptor and check the contract |
| Snippet does not appear after running tests | REST Docs, `document(...)`, or `outputDir` not configured | Check configuration and output directory name |
| Documentation does not distinguish fields that can be omitted | Template or description does not show optional status | Explain in `.description(...)` or customize the template |

## 10. Hands-on exercise and self-check questions

Using the test in section 5:

1. **Primitive array:** add `"couponCodes": ["WELCOME", "VIP"]`. Declare `couponCodes` as `ARRAY` and `couponCodes[]` as `STRING`.
2. **Deeper object array:** give each `items` element `"allocations": [{"warehouse": "HCM", "amount": 1}]`. Write three descriptors for the array, `warehouse`, and `amount`.
3. **Reordered elements:** swap element positions in `items` without modifying descriptors. Generate a new snippet under a different name and verify that the `items[].sku` path still works.
4. **Empty array:** send `"items": []` and verify the HTTP status per the contract. If `items` must be non-empty, add validation and a test for the error response.
5. **Optional child field:** add `items[].giftWrap` of type Boolean, present on only some items. Use `.optional()` and test both variants with and without the field.
6. **Build integration:** include `request-fields.adoc` in Asciidoctor and run the test -> documentation chain. Verify that the array fields table is updated after adding `couponCodes`.

Answer these questions before moving to the next lesson:

- How do `items`, `items[]`, and `items[].sku` differ?
- Why should arrays with dynamic indices be documented with `[]`?
- What structure does `batches[][]` represent?
- When `items` is empty, why must documentation tests with child fields be designed carefully?
- Why does `requestFields` not replace `@NotEmpty`, `@NotBlank`, `@Min`, and negative HTTP tests?

**Remember:** An array is a JSON field, while an array element is another structural level. `fieldWithPath("items")` describes the list, `fieldWithPath("items[]")` describes an element, and `fieldWithPath("items[].sku")` describes a field of an element at **any index**. Combining this approach with thorough testing and validation allows Spring REST Docs documentation to keep pace with payload changes in the build/CI.
