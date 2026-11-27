# subsectionWithPath for Lists or Nested Structures in Spring REST Docs

## 1. Objectives and Use Cases

**Spring REST Docs** generates API documentation from HTTP tests executed with **MockMvc**, **WebTestClient**, or **REST Assured**. When tests pass, the library generates snippets describing the HTTP request, response, payload, headers, and parameters. Development teams assemble these snippets into **Asciidoctor/Markdown** documentation and integrate the documentation generation step into the build and CI pipeline.

This lesson belongs to the **Subsection** chapter and focuses on **`subsectionWithPath(...)` for lists or nested JSON structures**. When an API returns an array of objects where each object contains nested child objects, a flat table document can become long and hard to read. `subsectionWithPath(...)` lets you describe a branch as a single business unit while maintaining verification over other parts of the payload.

For example, an order endpoint returns `items` as a list of line items, each having `pricing` and `options`. Overview documentation only needs one row for `items`. In-depth integration documentation can drill down to `items[].pricing` or individual fields like `items[].sku`.

After this lesson, you will be able to:

- Use `subsectionWithPath("items")` to describe an entire array and the elements inside it.
- Use `subsectionWithPath("items[].pricing")` to describe a repeating child object within each element of an array.
- Distinguish `subsectionWithPath(...)`, `fieldWithPath(...)`, and `beneathPath(...)`.
- Understand why a *strict* payload test can still pass when elements inside a subsection change.
- Design overview and detailed tables for the same endpoint, generate clearly named snippets, and integrate them into Asciidoctor/CI.

## 2. Sample Payload: Array of Objects and Multiple Nesting Levels

Suppose `GET /orders/ord-204` returns:

```json
{
  "id": "ord-204",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "pricing": {
        "unitAmount": 120000,
        "currency": "VND"
      },
      "options": {
        "giftWrapped": true,
        "note": "Morning delivery"
      }
    },
    {
      "sku": "PEN-02",
      "quantity": 1,
      "pricing": {
        "unitAmount": 30000,
        "currency": "VND"
      },
      "options": {
        "giftWrapped": false,
        "note": ""
      }
    }
  ],
  "delivery": {
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    },
    "contact": {
      "name": "Lan",
      "phone": "0900000000"
    }
  },
  "total": {
    "amount": 270000,
    "currency": "VND"
  }
}
```

Viewed as a tree:

```text
response
├── id
├── items                       (array)
│   ├── [0]                     (object)
│   │   ├── sku
│   │   ├── quantity
│   │   ├── pricing             (object)
│   │   │   ├── unitAmount
│   │   │   └── currency
│   │   └── options             (object)
│   │       ├── giftWrapped
│   │       └── note
│   └── [1]                     (similar structure)
├── delivery                    (object)
│   ├── address
│   │   ├── city
│   │   └── country
│   └── contact
│       ├── name
│       └── phone
└── total
    ├── amount
    └── currency
```

There are two meaningful levels of documentation detail:

- **Overview:** `id`, `items`, `delivery`, `total`. Array elements and child objects are grouped into subsections.
- **Selective detail:** list `items[].sku` and `items[].quantity`, while still grouping `items[].pricing` and `items[].options` as subsections; for `delivery`, you can document each field or group a smaller branch.

The `[]` notation in Spring REST Docs JSON paths denotes array elements. `items[].pricing` represents the `pricing` object present in each item, whereas `items[0].pricing` targets one specific element and is usually unsuitable as a general contract for a multi-element list.

## 3. How Does subsectionWithPath Work?

The following two snippets describe the same payload but set different **validation boundaries**.

### 3.1. One Descriptor for the Entire List

```java
responseFields(
    fieldWithPath("id")
        .description("Order ID"),
    subsectionWithPath("items")
        .description("List of line items in the order"),
    subsectionWithPath("delivery")
        .description("Delivery information"),
    subsectionWithPath("total")
        .description("Total order value")
)
```

`subsectionWithPath("items")` is a **field descriptor**. In the current `responseFields` snippet, it documents the `items` branch and treats descendants such as `items[].sku`, `items[].quantity`, and `items[].pricing.unitAmount` as already covered in the documentation. Therefore, the overview table does not need to list every child field.

This **does not mean** every child field of `items` has been checked against a detailed schema. If an item unexpectedly contains a `discountCode` field, the overview table can still pass because `items` covers the whole branch. If the API adds a `createdAt` field at the **root**, the strict overview table will report a missing descriptor for the new field.

### 3.2. Descriptor for a Child Object Inside Each Element

```java
responseFields(
    fieldWithPath("id")
        .description("Order ID"),
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Ordered quantity"),
    subsectionWithPath("items[].pricing")
        .description("Pricing details for each line item"),
    subsectionWithPath("items[].options")
        .description("Options for each line item"),
    subsectionWithPath("delivery")
        .description("Delivery information"),
    subsectionWithPath("total")
        .description("Total order value")
)
```

With this table, the `sku` and `quantity` fields of each item are documented individually; `pricing` and `options` are documented as subsections. The coverage scope of `subsectionWithPath("items[].pricing")` is limited to the `pricing` branch across the elements of `items`, and **does not cover** `items[].sku`, `items[].quantity`, or `items[].options`.

The two approaches should not be mixed loosely in the same snippet if the goal is to enforce child fields. For instance, declaring `fieldWithPath("items[].sku")` alongside `subsectionWithPath("items")` does not guarantee every element has a SKU; you need a detailed validation table with a clear scope and corresponding business assertions.

### 3.3. Distinguishing the Three APIs

| API | Role | Covers descendant fields? | Generates a separate body-portion snippet? |
| --- | --- | --- | --- |
| `fieldWithPath("items[].sku")` | Describes a specific field by path | Does not cover sibling objects/arrays | No |
| `subsectionWithPath("items")` | Describes an entire list branch in the field table | Yes, within the current snippet scope | No |
| `subsectionWithPath("items[].pricing")` | Describes the `pricing` branch of the items | Yes, within each selected branch | No |
| `beneathPath("delivery")` | Extracts a subtree to create a separate snippet | Not a field descriptor | Yes, when combined with `responseBody(...)` |

`subsectionWithPath(...)` is used inside `requestFields(...)` or `responseFields(...)`. To display the **JSON excerpt** of a branch, use `requestBody(beneathPath(...))` or `responseBody(beneathPath(...))`. To describe **each field** inside a branch, combine `beneathPath(...)` with `requestFields(...)` or `responseFields(...)`.

## 4. MockMvc Test Example Generating Snippets

The following example uses **JUnit 5**, **MockMvc**, **Spring MVC**, and **Spring REST Docs**, targeting **Java 17+**. The test and sample controller are placed in the same file so it can be read standalone. The controller returns fixed JSON; in a real project, replace it with your application's controller and deterministic test fixtures.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderItemsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOrderOverview() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-204")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].sku").value("BOOK-01"))
                .andExpect(jsonPath("$.items[1].quantity").value(1))
                .andDo(document("orders-items-overview",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                subsectionWithPath("items")
                                        .description("List of line items"),
                                subsectionWithPath("delivery")
                                        .description("Delivery information"),
                                subsectionWithPath("total")
                                        .description("Total order value")
                        ),
                        responseBody(beneathPath("delivery")
                                .withSubsectionId("delivery"))
                ));
    }

    @Test
    void documentSelectedFieldsInsideItems() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-204")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].pricing.unitAmount")
                        .value(120000))
                .andDo(document("orders-items-detailed",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("items[].sku")
                                        .description("Product SKU"),
                                fieldWithPath("items[].quantity")
                                        .description("Quantity"),
                                subsectionWithPath("items[].pricing")
                                        .description("Line item pricing"),
                                subsectionWithPath("items[].options")
                                        .description("Options for the line item"),
                                subsectionWithPath("delivery")
                                        .description("Delivery information"),
                                subsectionWithPath("total")
                                        .description("Total order value")
                        )
                ));
    }

    @RestController
    public static class SampleOrderController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> findById(@PathVariable String id) {
            if (!"ord-204".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-204",
                      "items": [
                        {
                          "sku": "BOOK-01",
                          "quantity": 2,
                          "pricing": {
                            "unitAmount": 120000,
                            "currency": "VND"
                          },
                          "options": {
                            "giftWrapped": true,
                            "note": "Morning delivery"
                          }
                        },
                        {
                          "sku": "PEN-02",
                          "quantity": 1,
                          "pricing": {
                            "unitAmount": 30000,
                            "currency": "VND"
                          },
                          "options": {
                            "giftWrapped": false,
                            "note": ""
                          }
                        }
                      ],
                      "delivery": {
                        "address": {
                          "city": "Ho Chi Minh City",
                          "country": "VN"
                        },
                        "contact": {
                          "name": "Lan",
                          "phone": "0900000000"
                        }
                      },
                      "total": {
                        "amount": 270000,
                        "currency": "VND"
                      }
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json);
        }
    }
}
```

The tests highlight three important points:

1. **The overview case** uses `subsectionWithPath("items")`: a single row in the table represents the entire list, including the nested objects inside.
2. **The detailed case** uses `items[].sku` and `items[].quantity`: directly displays the fields used by clients while still summarizing the `pricing` and `options` objects.
3. **Two distinct documentation identifiers:** `orders-items-overview` and `orders-items-detailed`. Each `responseFields(...)` call creates `response-fields.adoc` under its respective test identifier. If you want two field tables under the **same** identifier, you need different subsection IDs/scopes; avoid having two handlers overwrite the same snippet filename.

In the example, `jsonPath` assertions verify specific data on at least one element. For a real API, add checks for element counts, calculated amounts, required conditions on every element, and empty-array cases; `subsectionWithPath` does not replace business test logic.

## 5. How Strict Validation Changes by Subsection Boundary

By default, `responseFields(...)` checks the documented fields within the payload scope. A new field without an appropriate descriptor can cause the test to fail. However, a subsection descriptor treats all descendants of that path as documented within the current snippet.

Suppose the following independent changes occur:

| Change in JSON response | Overview test with `subsectionWithPath("items")` | Detailed test using `items[].sku`, `items[].quantity`, and two small subsections |
| --- | --- | --- |
| Add `items[0].color` | May pass: inside the `items` branch | Fails: `color` is undocumented |
| Add `items[1].pricing.tax` | May pass | May pass: `pricing` is covered on each item |
| Add `items[1].options.priority` | May pass | May pass: `options` is covered on each item |
| Add `delivery.instructions` | May pass: `delivery` is a subsection | May pass: detailed test still uses `subsectionWithPath("delivery")` |
| Add `createdAt` at root | Fails when undeclared | Fails when undeclared |
| Remove `items` completely | Fails if `items` remains a required descriptor | Fails if required item descriptors do not appear |

These outcomes describe **field documentation completeness**, not the entire business contract. A response with a wrong child field type, invalid value, or wrong element count requires additional assertions, validation tests, or contract tests.

### The Empty List Case

An endpoint can legitimately return `"items": []`. This case must be considered separately:

- With the overview table `subsectionWithPath("items")`, the `items` path is still present because the array itself exists.
- With a detailed table that only describes paths like `items[].sku`, when there are no elements there is no `sku` field to match in that test case. Required descriptors can cause strict documentation validation to fail.
- Use **one test with a non-empty list of items** to generate the detailed table, and **another test for an empty list** to verify contract behavior. There is no need to force an empty-array test to generate a detailed table for non-existent elements.

Organizing tests this way gives documentation a representative example while behavioral tests still cover the edge case.

## 6. Choosing Paths for Arrays and Deep Objects

### 6.1. Common Patterns

| JSON Structure | Path from Root | Meaning |
| --- | --- | --- |
| Array of line items | `items` | The entire list branch |
| SKU in each line item | `items[].sku` | The `sku` field of an array element |
| Pricing inside each item | `items[].pricing` | Repeating `pricing` child object |
| Unit amount inside each item | `items[].pricing.unitAmount` | Field nested beneath an element's child object |
| Delivery address object | `delivery.address` | Child object of `delivery` |
| City in address | `delivery.address.city` | Leaf field in a nested object |

At the root level, `subsectionWithPath("delivery.address")` covers `delivery.address.city` and `delivery.address.country`, yet **does not** cover `delivery.contact.name`. Similarly, `subsectionWithPath("items[].pricing")` is not responsible for documenting `items[].options`.

### 6.2. When an Array Is at the Response Root

If an endpoint returns an array directly:

```json
[
  {
    "sku": "BOOK-01",
    "pricing": { "unitAmount": 120000, "currency": "VND" }
  },
  {
    "sku": "PEN-02",
    "pricing": { "unitAmount": 30000, "currency": "VND" }
  }
]
```

The path to the `sku` field inside elements of the root array uses `[].sku`, and the path to the child object uses `[].pricing`. Thus you can document it as:

```java
responseFields(
    fieldWithPath("[].sku")
        .description("Product SKU"),
    subsectionWithPath("[].pricing")
        .description("Pricing information for each product")
)
```

The difference from `items[].pricing` is that the root array has no `items` key. When authoring descriptors, start from the **actual JSON** received by the test rather than Java DTO class names.

### 6.3. Child Object of a Child Object

For `delivery`, a detailed table from the root could be:

```java
responseFields(
    fieldWithPath("id")
        .description("Order ID"),
    subsectionWithPath("items")
        .description("List of line items"),
    subsectionWithPath("delivery.address")
        .description("Delivery address"),
    fieldWithPath("delivery.contact.name")
        .description("Delivery contact name"),
    fieldWithPath("delivery.contact.phone")
        .description("Contact phone number"),
    subsectionWithPath("total")
        .description("Total order value")
)
```

This table separates responsibilities more clearly: the `address` object is summarized, while `contact.name` and `contact.phone` are documented in detail. Using only `subsectionWithPath("delivery")` would collapse both `address` and `contact` into one row.

## 7. When to Use beneathPath to Extract a Nested Structure Separately?

`subsectionWithPath(...)` specifies the coverage depth in the **current field table**. If you want your documentation to include a JSON excerpt showing **only the `delivery` section**, use:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;

responseBody(
    beneathPath("delivery").withSubsectionId("delivery")
)
```

This handler was already used in the `documentOrderOverview` test and generates the `response-body-delivery.adoc` snippet. It isolates the `delivery` data; `items` and `total` outside this branch are not included in the extracted body snippet.

To document each field inside `delivery` in a dedicated table:

```java
responseFields(
    beneathPath("delivery").withSubsectionId("delivery-fields"),
    fieldWithPath("address.city")
        .description("Delivery city"),
    fieldWithPath("address.country")
        .description("Country code"),
    fieldWithPath("contact.name")
        .description("Recipient name"),
    fieldWithPath("contact.phone")
        .description("Contact phone number")
)
```

Because `beneathPath("delivery")` already selected the branch, field paths in the detailed table are **relative**: `address.city`, not `delivery.address.city`. The generated snippet is named `response-fields-delivery-fields.adoc`.

For the `items` array, you can create a detailed table directly from the root using `items[].sku`, or select a subtree so the new root has an array type. When selecting a subtree that is an array, descriptors must match the extracted structure—for instance, fields under each element will have the `[]` prefix instead of `items[]`. Confirm this against specific test data and the REST Docs version used in your project.

**Guiding rule:** Use `subsectionWithPath` to decide the **table's depth**, and use `beneathPath` to decide the **JSON portion extracted into a snippet**.

## 8. Applying to Request Payloads

The mechanism is identical with `requestFields(...)`. Suppose `POST /orders` accepts:

```json
{
  "customerId": "cus-17",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "customization": {
        "giftMessage": "Congratulations!"
      }
    }
  ],
  "delivery": {
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  }
}
```

If the overview documentation only needs to list the three branches:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    subsectionWithPath("items")
        .description("Items and accompanying options"),
    subsectionWithPath("delivery")
        .description("Delivery information")
)
```

To validate and document part of each item's fields:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Ordered quantity"),
    subsectionWithPath("items[].customization")
        .description("Product customization"),
    subsectionWithPath("delivery")
        .description("Delivery information")
)
```

The two examples above are **two snippet alternatives**; if you want to generate both tables in the same documentation set, place them under separate identifiers or use a subsection extractor to create uniquely named snippets. For requests, documentation validation helps detect when test clients send fields outside the described structure; controller validation tests are still needed to enforce business rules such as `quantity > 0`.

## 9. optional, ignored, relaxed, and Heterogeneous Data

### 9.1. Optional List Branch

If the contract allows the `items` key to be **completely absent**, you can mark it:

```java
subsectionWithPath("items")
    .optional()
    .description("List of line items, if present")
```

`optional()` allows the field to be absent in the test case. However, an absent `items` key is different from `"items": []`; write a separate test for each case allowed by the API.

### 9.2. Heterogeneous Child Branches Across Elements

If the `options` object only exists on some items, declare the path `items[].options` with `optional()` per the contract, and write test cases for items with and without options. Do not assume that a single `optional()` descriptor replaces verifying required fields on **every** element when element counts and structures vary.

For complex responses, additional assertions or validation can verify that every item has a `sku`, quantity is positive, and currency information is valid. `subsectionWithPath("items")` does not prove these conditions on its own.

### 9.3. ignored and relaxed

- `ignored()` allows a known path to be omitted from the table while still playing its part in accounting for handled fields. It should only be used when excluding that field from publication is intentional.
- `relaxedResponseFields(...)` and `relaxedRequestFields(...)` allow undocumented fields to exist. Convenient when documentation only highlights a few fields, though it reduces the ability to catch unexpected schema changes.
- `subsectionWithPath(...)` keeps tables short **while still applying strict mode to everything outside the covered branch**. Therefore, when you already know the object/array boundary to summarize, this is usually a clearer choice than relaxing the entire payload.

## 10. Generating Snippets and Embedding in Asciidoctor

After running the tests in Section 4, the standard output directory with Gradle is `build/generated-snippets`. The main generated snippets include:

| Path | Source | Purpose |
| --- | --- | --- |
| `orders-items-overview/response-fields.adoc` | Overview `responseFields(...)` | Table of `id`, `items`, `delivery`, `total` |
| `orders-items-overview/response-body-delivery.adoc` | `responseBody(beneathPath("delivery")...)` | JSON excerpt of `delivery` |
| `orders-items-overview/http-response.adoc` | Default HTTP response snippet | Full tested response |
| `orders-items-detailed/response-fields.adoc` | Detailed `responseFields(...)` | Table with paths `items[].sku`, `items[].quantity`, `items[].pricing`, `items[].options` |

A section in `src/docs/asciidoc/orders.adoc` can reference them:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Returns the list of line items, delivery information, and total order value.

=== HTTP Response

include::{snippets}/orders-items-overview/http-response.adoc[]

=== Overview Response Structure

include::{snippets}/orders-items-overview/response-fields.adoc[]

=== Important Fields in the List

include::{snippets}/orders-items-detailed/response-fields.adoc[]

=== Delivery Data Example

include::{snippets}/orders-items-overview/response-body-delivery.adoc[]
```

The `snippets` attribute must point to the REST Docs output directory. Snippet filenames may differ if the project customizes templates or identifiers; verify against the files generated after running tests. The excerpt above uses Asciidoctor templates; if the project uses Markdown, use the corresponding templates and inclusion mechanism.

### Integrating into Gradle and CI

For a project that already applies the Asciidoctor plugin and has appropriate test dependencies, the Gradle configuration (Groovy DSL) may include:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Run:

```bash
./gradlew clean test asciidoctor
```

In CI, make the documentation build step depend on passing tests. That way, contract changes that break tests prevent publishing documentation that no longer matches the HTTP exchange. With Maven, the standard output path is `target/generated-snippets`, and the documentation plugin must be configured accordingly.

## 11. Common Errors and Diagnostics

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Overview test still passes when a field is added to an item | `subsectionWithPath("items")` already covers all child fields | Write a detailed table or assertion when new fields must be controlled |
| Detailed test fails when adding `items[0].color` | Table only describes `sku`, `quantity`, `pricing`, `options` | Add a descriptor for `items[].color` if that is a contract change |
| Test still passes when adding `items[].pricing.tax` | `items[].pricing` is a subsection and covers descendants | Write detailed descriptors for `pricing` when needed |
| Test fails when the `items` array is empty | Paths like `items[].sku` may have no values to match | Use a fixture with items for the detailed snippet, and test empty arrays separately |
| Used `items[0].sku` and missed remaining items | Path selects only a specific element | Use `items[].sku` for a contract applying to the entire list |
| Used `delivery.address.city` inside `responseFields(beneathPath("delivery"), ...)` | Descriptor is written from root even though the extractor already selected `delivery` | Use `address.city` |
| `response-body-delivery.adoc` is missing | `responseBody(beneathPath(...))` was not used or the ID differs from expected | Check handler, identifier, subsection ID, and test output |
| Asciidoctor reports snippet not found | Wrong `snippets` attribute or test step did not run | Align paths and build task ordering |

## 12. Practice Exercise

Apply to the `OrderItemsDocumentationTest` example:

1. **Array boundary:** Add `items[0].color`. Run both tests to observe the difference between `subsectionWithPath("items")` and documenting child fields.
2. **Object-in-array boundary:** Add `items[1].pricing.tax`. Observe that `subsectionWithPath("items[].pricing")` covers the new field; then replace that descriptor with `items[].pricing.unitAmount` and `items[].pricing.currency` and re-check.
3. **Deeply nested object:** In the detailed table, replace `subsectionWithPath("delivery")` with `subsectionWithPath("delivery.address")` alongside `delivery.contact.name` and `delivery.contact.phone`.
4. **Empty array:** Create a variant returning `"items": []` and write a separate test; explain why the test generating the detailed field table should be separated from the empty-array test.
5. **Response body subsection:** Generate and include `response-body-delivery.adoc` in Asciidoctor. Compare it with `http-response.adoc` to confirm only the data portion needing explanation was extracted.
6. **Build/CI:** Run `./gradlew clean test asciidoctor` in a configured project. Read the error if a strict descriptor lacks a field and update the documentation per the actual contract.

**Completion criteria:** learners can explain the differences between paths `items`, `items[].sku`, and `items[].pricing`, identify schema changes that an overview table will overlook, and choose how to document parts of a nested JSON structure separately without making API tables overly long.

## 13. Self-Check Questions

**1. When should you use `subsectionWithPath("items")`?**

When you want to describe the entire list as a single business block and do not require the current table to list every field inside its elements. If the contract needs to control each item's fields, add a detailed test and snippet.

**2. Does `subsectionWithPath("items[].pricing")` cover `items[].sku`?**

No. It covers descendants of `pricing` across items, such as `items[].pricing.unitAmount`. `sku` is a sibling field and must be documented separately in a strict table.

**3. Why can two tests using the same response produce different results when a field is added?**

Because each test uses a **different set of descriptors and subsection boundaries**. The overview test accepts fields inside a covered branch; the detailed test can catch new fields outside the narrower declared subsections.

**4. When you only want the JSON of `delivery`, which API should you call?**

Call `responseBody(beneathPath("delivery"))`. `subsectionWithPath("delivery")` only creates a descriptor in the field table and does not generate a separate extracted body.

**5. Can you rely solely on `subsectionWithPath` to guarantee every item is valid?**

No. It is a payload documentation mechanism. Business correctness such as valid SKUs, totals, positive quantities, and cross-field relationships requires separate assertions or validation tests.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field paths, documenting subsections, completeness checking, and extracting part of a payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): MockMvc/WebTestClient/REST Assured configuration, snippets, Asciidoctor, and build integration.
