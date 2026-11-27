# Nested fields, arrays, and repeating elements in response payloads

## 1. Lesson objectives

In Spring REST Docs, a JSON response can contain multiple layers of objects and arrays: customer information inside an order, packages inside each shipment, and line items inside each package. To generate verifiable API documentation from HTTP tests, you must specify the exact **path to each field** within that structure.

This lesson belongs to the **Response payload** chapter of the **SPRING_REST_DOCS** module. After completing it, you will be able to:

- Write `fieldWithPath(...)` for nested objects using dot notation.
- Write paths to repeating elements in arrays using `[]`, including multi-level nested arrays.
- Distinguish between root arrays, arrays of primitive values, arrays of objects, and objects with dynamic keys.
- Use `responseFields(...)` to generate a JSON field table from a MockMvc test.
- Understand the limitations of descriptor validation for empty arrays, missing values, or heterogeneous data types.
- Organize and reuse descriptors for repeating structures, and include snippets in Asciidoctor/Markdown within build and CI pipelines.

Similar concepts apply when using WebTestClient or REST Assured; the difference lies in how the test is configured and how the documentation call is attached. This lesson uses MockMvc throughout.

## 2. Multi-level nested response

Suppose the endpoint `GET /api/orders/2048/shipping` returns a `200 OK` response:

```json
{
  "orderId": "ORD-2048",
  "customer": {
    "id": 17,
    "contact": {
      "email": "lan@example.test"
    }
  },
  "shipments": [
    {
      "carrier": "FAST",
      "packages": [
        {
          "packageId": "PKG-1",
          "items": [
            {"sku": "A-01", "quantity": 2},
            {"sku": "A-02", "quantity": 1}
          ]
        },
        {
          "packageId": "PKG-2",
          "items": [
            {"sku": "A-03", "quantity": 4}
          ]
        }
      ]
    },
    {
      "carrier": "STANDARD",
      "packages": [
        {
          "packageId": "PKG-3",
          "items": [
            {"sku": "A-04", "quantity": 1}
          ]
        }
      ]
    }
  ],
  "labels": ["fragile", "priority"],
  "metadata": {
    "route.zone": "HCM"
  }
}
```

You can visualize the JSON tree as follows:

```text
response
├── orderId                             STRING
├── customer                            OBJECT
│   ├── id                              NUMBER
│   └── contact                         OBJECT
│       └── email                       STRING
├── shipments                           ARRAY
│   └── []                              OBJECT, repeated multiple times
│       ├── carrier                     STRING
│       └── packages                   ARRAY
│           └── []                      OBJECT, repeated multiple times
│               ├── packageId           STRING
│               └── items               ARRAY
│                   └── []              OBJECT, repeated multiple times
│                       ├── sku         STRING
│                       └── quantity    NUMBER
├── labels                              ARRAY of STRING
└── metadata                            OBJECT
    └── ['route.zone']                  STRING
```

The key takeaway: `shipments[].packages[].items[].sku` contains **`[]` three times**, because reaching `sku` requires traversing three distinct arrays. Each `[]` represents descending into the array elements at that corresponding level.

## 3. Rules for writing JSON paths

Spring REST Docs' `fieldWithPath("...")` uses its own JSON path syntax. Do not put a leading `$` as in MockMvc's `jsonPath("$.customer.id")` expression.

| Target to document | `fieldWithPath` path | Meaning |
| --- | --- | --- |
| Order ID | `orderId` | Field directly on the root object |
| Customer information | `customer` | Entire `customer` object |
| Customer email | `customer.contact.email` | Traverses two nested objects |
| List of shipments | `shipments` | Array of objects |
| Carrier of each shipment | `shipments[].carrier` | Field inside elements of `shipments` |
| Array of packages per shipment | `shipments[].packages` | Array nested inside objects of an outer array |
| ID of each package | `shipments[].packages[].packageId` | Field across two arrays |
| Array of line items in a package | `shipments[].packages[].items` | Array at the third nesting level |
| Product SKU of each line item | `shipments[].packages[].items[].sku` | Field across three arrays |
| Quantity in each line item | `shipments[].packages[].items[].quantity` | Field across three arrays |
| Classification labels | `labels` | Describes the entire array of strings |
| Key containing a dot | `metadata['route.zone']` | Targets the exact key `route.zone`, not an object `route` containing `zone` |

### 3.1. Nested objects: add a dot for each level

```java
fieldWithPath("customer")
    .description("Customer information for the order");

fieldWithPath("customer.id")
    .description("Customer identifier");

fieldWithPath("customer.contact")
    .description("Contact details");

fieldWithPath("customer.contact.email")
    .description("Customer contact email");
```

The path `customer.contact.email` is completely different from a root-level key named `"customer.contact.email"`. For keys containing a dot directly in their name, you must use bracket notation:

```json
{
  "metadata": {
    "route.zone": "HCM"
  }
}
```

```java
fieldWithPath("metadata['route.zone']")
    .description("Delivery route zone code");
```

You can combine dot and bracket notation in the same path. For example, `metadata['route.zone']` points to the `metadata` object and then to **a single key** named `route.zone`.

### 3.2. Arrays of objects: use `[]` for repeating elements

For `shipments`, each element is an object containing `carrier` and `packages`:

```java
fieldWithPath("shipments")
    .description("Shipments for the order");

fieldWithPath("shipments[].carrier")
    .description("Shipping carrier for each shipment");

fieldWithPath("shipments[].packages")
    .description("Packages in each shipment");
```

Do not document using `shipments[0].carrier` if the API contract applies to **all shipments**, because the number of elements can vary. `[]` represents a generalized path; specific indices are only appropriate when position itself has a fixed contractual meaning.

### 3.3. Multiple array levels: count the array traversals

To describe the product SKU of each line item in each package of each shipment:

```java
fieldWithPath("shipments[].packages[].items[].sku")
    .description("Product SKU of the line item in the package");

fieldWithPath("shipments[].packages[].items[].quantity")
    .description("Product quantity in the line item");
```

Read the path from left to right:

1. `shipments[]` — iterate over each shipment.
2. `packages[]` — within each shipment, iterate over each package.
3. `items[]` — within each package, iterate over each line item.
4. `sku` or `quantity` — the field to document in each line item.

A typical mistake is writing `shipments.packages.items.sku`; that omits the array levels and fails to match the actual response structure.

### 3.4. Arrays of primitive values and root arrays

For `"labels": ["fragile", "priority"]`, you can document the entire array:

```java
fieldWithPath("labels")
    .description("Classification labels for the order");
```

When documenting an array of primitive values, the `description` should clearly state the type and meaning of each value if API consumers need to know; array elements do not have separate field names like objects do.

If the **root of the response is an array**:

```json
[
  {"eventId": "EV-1", "type": "PICKED_UP"},
  {"eventId": "EV-2", "type": "IN_TRANSIT"}
]
```

The correct paths are:

```java
responseFields(
    fieldWithPath("[]").description("Shipping events"),
    fieldWithPath("[].eventId").description("Event ID"),
    fieldWithPath("[].type").description("Event type")
)
```

A leading `[]` indicates that **the root of the response itself is an array**. Do not add prefixes like `events` or `data` if those fields do not exist in the JSON.

### 3.5. Dynamic keys: wildcard `*` vs. array element `[]`

Some APIs return objects indexed by dynamic keys, for example:

```json
{
  "warehouses": {
    "HCM": {"available": 12},
    "HAN": {"available": 8}
  }
}
```

The names `HCM` and `HAN` are **object keys**, not array elements. You can use a wildcard:

```java
responseFields(
    fieldWithPath("warehouses")
        .description("Inventory count by warehouse"),
    fieldWithPath("warehouses.*.available")
        .description("Available stock at each warehouse")
)
```

Use `*` when the key name varies, and use `[]` when the data is actually a JSON array. `warehouses[].available` is wrong in this example because `warehouses` is an object. Avoid overusing wildcards because they can make it harder to see valid keys in the documentation table; also document key naming rules in `description`.

## 4. MockMvc test generating docs for multi-level nested arrays

The full example below uses JUnit Jupiter, Spring MVC, Spring REST Docs MockMvc, and Jackson. Java 17+ is used for `record`; the sample controller returns a deterministic response to generate snippets.

```java
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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class NestedShippingResponseDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ShippingController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentNestedShippingResponse() throws Exception {
        mockMvc.perform(get("/api/orders/{id}/shipping", 2048)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-2048"))
                .andExpect(jsonPath(
                        "$.shipments[0].packages[0].items[0].sku")
                        .value("A-01"))
                .andExpect(jsonPath(
                        "$.shipments[1].packages[0].items[0].quantity")
                        .value(1))
                .andDo(document("shipping-nested",
                        responseFields(
                                fieldWithPath("orderId")
                                        .description("Order ID"),
                                fieldWithPath("customer")
                                        .description("Customer information"),
                                fieldWithPath("customer.id")
                                        .description("Customer ID"),
                                fieldWithPath("customer.contact")
                                        .description("Contact details"),
                                fieldWithPath("customer.contact.email")
                                        .description("Customer email"),
                                fieldWithPath("shipments")
                                        .description("List of shipments"),
                                fieldWithPath("shipments[].carrier")
                                        .description("Shipping carrier"),
                                fieldWithPath("shipments[].packages")
                                        .description("Packages in the shipment"),
                                fieldWithPath(
                                        "shipments[].packages[].packageId")
                                        .description("Package ID"),
                                fieldWithPath(
                                        "shipments[].packages[].items")
                                        .description("Line items in the package"),
                                fieldWithPath(
                                        "shipments[].packages[].items[].sku")
                                        .description("Product SKU in the package"),
                                fieldWithPath(
                                        "shipments[].packages[].items[].quantity")
                                        .description("Product quantity"),
                                fieldWithPath("labels")
                                        .description("Order classification labels"),
                                fieldWithPath("metadata")
                                        .description("Response metadata"),
                                fieldWithPath("metadata['route.zone']")
                                        .description("Delivery route zone code")
                        )
                ));
    }

    @RestController
    static class ShippingController {

        @GetMapping(
                value = "/api/orders/{id}/shipping",
                produces = MediaType.APPLICATION_JSON_VALUE)
        ShippingResponse shipping(@PathVariable("id") long id) {
            return new ShippingResponse(
                    "ORD-" + id,
                    new Customer(17, new Contact("lan@example.test")),
                    List.of(
                            new Shipment("FAST", List.of(
                                    new ShippingPackage("PKG-1", List.of(
                                            new Item("A-01", 2),
                                            new Item("A-02", 1))),
                                    new ShippingPackage("PKG-2", List.of(
                                            new Item("A-03", 4))))),
                            new Shipment("STANDARD", List.of(
                                    new ShippingPackage("PKG-3", List.of(
                                            new Item("A-04", 1)))))),
                    List.of("fragile", "priority"),
                    Map.of("route.zone", "HCM")
            );
        }
    }

    record Contact(String email) {}
    record Customer(long id, Contact contact) {}
    record Item(String sku, int quantity) {}
    record ShippingPackage(String packageId, List<Item> items) {}
    record Shipment(String carrier, List<ShippingPackage> packages) {}
    record ShippingResponse(
            String orderId,
            Customer customer,
            List<Shipment> shipments,
            List<String> labels,
            Map<String, String> metadata) {}
}
```

Meaning of the three operation groups:

- `perform(get(...))` creates a simulated HTTP request, while the controller and Jackson generate the JSON response.
- `andExpect(jsonPath(...))` checks **concrete values** using JSONPath syntax, including indices of specific positions to verify.
- `andDo(document("shipping-nested", responseFields(...)))` declares the **field contract**, validates the paths, and generates `response-fields.adoc`.

In the generated table, `shipments` is documented as an array, `shipments[].packages` is also an array, while `shipments[].packages[].items[].sku` is a string and `...quantity` is a number. The `description` text should reflect the meaning of the data that API integrators need to know.

**Verification scope:** documenting `shipments[].packages[].items[].sku` indicates that this path exists in the test payload. Do not treat it as a guarantee that *every* line item in *every* response contains `sku`. For mandatory per-element constraints or complex business rules, use dedicated assertions or appropriate schema validation.

## 5. Repeating elements do not guarantee elements are always present

Three cases have different impacts on verification:

### 5.1. Array with representative elements

```json
{
  "shipments": [
    {
      "carrier": "FAST",
      "packages": [
        {
          "packageId": "PKG-1",
          "items": [{"sku": "A-01", "quantity": 2}]
        }
      ]
    }
  ]
}
```

This fixture allows deep paths like `shipments[].packages[].items[].sku` and `...quantity` to be resolved. This is usually the right fixture for **structural documentation generation tests**.

### 5.2. Empty array

```json
{
  "shipments": []
}
```

`shipments` is still a real field, but there is no `shipments[].carrier` or `packages` child fields to inspect. If child fields are declared as required, the documentation generation step may fail due to missing fields.

Do not turn all child descriptors into `optional()` just to make an empty fixture pass if the actual contract requires those fields **whenever elements exist**. A more intentional approach is to write a separate test for the empty-list case, while the documentation-generating test uses a fixture with representative structure.

### 5.3. Empty array in one branch while another branch has data

```json
{
  "shipments": [
    {"carrier": "FAST", "packages": []},
    {
      "carrier": "STANDARD",
      "packages": [
        {"packageId": "PKG-3", "items": [{"sku": "A-04", "quantity": 1}]}
      ]
    }
  ]
}
```

The deep paths can still be matched on the second shipment. However, REST Docs descriptor matching does not replace verifying **per-element** rules: for example, whether a shipment is allowed to have no packages, or whether an item must have a quantity greater than 0. These cases must be tested explicitly.

## 6. Optional, null, and data types in repeating structures

Given a sample response:

```json
{
  "shipments": [
    {
      "carrier": "FAST",
      "packages": [
        {"packageId": "PKG-1", "note": null}
      ]
    }
  ]
}
```

If `note` may be omitted or be a string in other responses, you can write:

```java
import org.springframework.restdocs.payload.JsonFieldType;

fieldWithPath("shipments[].packages[].note")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Optional package note; may be absent or null");
```

In this example, `note` has a `null` value, yet the contract expects a string when content is provided. `type(JsonFieldType.STRING)` displays the expected type in the snippet; `optional()` allows the path to be absent. These two are not equivalent.

When a repeating path takes values of multiple JSON types within the same payload, Spring REST Docs may infer the type `VARIES`. This is a signal to review the contract: does the field intentionally allow multiple types, or is the fixture inconsistent? You can specify `type(...)` to display the expected type, while still writing separate checks if every element must strictly share one type.

Distinguish between:

| Payload | Meaning |
| --- | --- |
| `{"note": "Deliver before 17:00"}` | Field is present with a string type |
| `{"note": null}` | Field is present with a JSON `null` value |
| `{}` | Field is absent |
| `{"packages": []}` | `packages` array is present with zero elements |
| `{"packages": null}` | `packages` field is present with `null`, not an array |

If the contract includes rules like "the array always has at least one element", "no element may be null", or "every package must have a packageId", add dedicated tests. Descriptors in the example illustrate documentation structure and do not cover all those constraints.

## 7. Reusing descriptors for repeating elements

When a structure appears across multiple endpoints, avoid duplicating the same descriptions everywhere. Spring REST Docs supports `andWithPrefix(...)` to prepend a path prefix to a group of `FieldDescriptor` instances.

For example, a line item always contains `sku` and `quantity`:

```java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

static FieldDescriptor[] itemFields() {
    return new FieldDescriptor[] {
            fieldWithPath("sku").description("Product SKU"),
            fieldWithPath("quantity").description("Product quantity")
    };
}
```

This group can be used in an endpoint returning **a single line item**:

```java
responseFields(itemFields())
```

Or used inside a multi-level nested shipping response:

```java
responseFields(
        fieldWithPath("orderId").description("Order ID"),
        fieldWithPath("customer").description("Customer"),
        fieldWithPath("shipments").description("Shipments"),
        fieldWithPath("shipments[].packages")
                .description("Packages in each shipment"),
        fieldWithPath("shipments[].packages[].items")
                .description("Line items in each package")
        // Add remaining response descriptors here
).andWithPrefix("shipments[].packages[].items[].", itemFields())
```

The two newly added descriptors have the complete paths:

- `shipments[].packages[].items[].sku`
- `shipments[].packages[].items[].quantity`

**The prefix snippet above illustrates the mechanism**, and is not yet the full list of descriptors for the response in section 2. To use it with strict `responseFields(...)`, you must include all remaining fields (`customer.id`, `shipments[].carrier`, `metadata['route.zone']`, etc.) or intentionally document subsections.

Similarly, you can use:

```java
responseFields(
        fieldWithPath("[]").description("Line items")
).andWithPrefix("[].", itemFields());
```

This works well if the endpoint returns a root array of line items and each element contains the two defined fields.

The main benefit of `andWithPrefix(...)` is using **one canonical descriptor set** across multiple structures: a single object, a root array, or nested arrays. When the meaning of `quantity` changes, you only need to update the base descriptor in one shared place.

## 8. When structures grow too large: `subsectionWithPath` and `beneathPath`

If a branch is too long, you can split the documentation into two levels.

### 8.1. Describing a branch at an overview level

`subsectionWithPath(...)` lets you describe an entire branch along with its child fields in a single line:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("orderId").description("Order ID"),
    subsectionWithPath("customer").description("Customer details"),
    subsectionWithPath("shipments").description("Shipments and packages"),
    fieldWithPath("labels").description("Order labels"),
    subsectionWithPath("metadata").description("Supplementary metadata")
)
```

When `subsectionWithPath("shipments")` is declared, Spring REST Docs considers descendants beneath the `shipments` branch documented within the scope of that snippet check. This is useful for overview tables; readers will not see individual deep package paths in this table. If those details are an important part of the contract, create a sub-table.

### 8.2. Generating a dedicated table for a subsection

`beneathPath(...)` lets you create a snippet documenting only fields inside a child object. For example, extracting `customer.contact`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;

responseFields(
    beneathPath("customer.contact"),
    fieldWithPath("email")
        .description("Customer email")
)
```

Here `email` is a path **relative** to `customer.contact`. Spring REST Docs can generate a separate snippet named like `response-fields-beneath-customer.contact.adoc`. This makes it convenient to embed a focused table into a dedicated documentation page about customer data.

Using `subsectionWithPath` in an overview snippet does not automatically generate a detailed snippet; a separate `document(...)` call with `responseFields(beneathPath(...), ...)` is required when you want a detailed table.

## 9. Common errors when handling repeating elements

| Symptom | Cause | Fix |
| --- | --- | --- |
| `shipments.carrier` not found | `shipments` is an array of objects | Use `shipments[].carrier` |
| `shipments[].packages.packageId` not found | `packages` is also an array | Use `shipments[].packages[].packageId` |
| `shipments[].packages[].items.sku` not found | Missing `[]` on the `items` array | Use `shipments[].packages[].items[].sku` |
| `metadata.route.zone` does not match JSON | Key is literally named `route.zone` | Use `metadata['route.zone']` |
| `warehouses[].available` does not match | `warehouses` is an object with dynamic keys | Consider `warehouses.*.available` |
| Child descriptor not found on empty array | No elements available to inspect child fields | Use a fixture with representative data for doc tests, test empty arrays separately |
| Field table omits branch details | `subsectionWithPath` is used for the entire branch | Replace with child `fieldWithPath` entries or generate a sub-snippet |
| Doc generation test passes while per-element data is wrong | Descriptors do not replace per-element assertions/schema validation | Write dedicated business assertions or schema tests |
| `response-fields.adoc` is not created | Test did not run or REST Docs is misconfigured | Check MockMvc configuration, `document` call, and snippets directory |

For Java DTOs, field names in documentation must reflect the **serialized JSON**. `@JsonProperty` rules, naming strategies, field filters, and `@JsonInclude` conditions can cause field names or field presence to differ from the Java record/class.

## 10. Integrating snippets into documentation and CI

When the `document("shipping-nested", ...)` test succeeds, Spring REST Docs typically places files in Gradle's generated snippets directory:

```text
build/generated-snippets/
└── shipping-nested/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

This list illustrates the relevant files; depending on configuration, other default snippets also exist. With Maven, the standard path is `target/generated-snippets`. You can include the field table in Asciidoctor:

```adoc
= Shipping API
:snippets: build/generated-snippets

== Order shipping details

=== Example HTTP response
include::{snippets}/shipping-nested/http-response.adoc[]

=== JSON response structure
include::{snippets}/shipping-nested/response-fields.adoc[]
```

The build/CI pipeline must run the snippet-generating tests before running the Asciidoctor/documentation packaging step. If a response change causes documentation tests to fail, the pipeline must stop so the team updates the contract before publishing. Final documentation can be converted or authored in Markdown using an appropriate workflow; the default snippet here remains Asciidoctor.

## 11. Practice exercise

Use the response in section 2 as input and implement the following scenarios:

1. Add `shipments[].estimatedDate` (expected date string). Add the descriptor and date-format validation assertions where needed.
2. Add a `shipments[].packages[].dimensions` object with `length`, `width`, and `height`. Write all child paths and document measurement units.
3. Replace the `items` array in one package with `[]`. Predict which deep descriptors might fail to match, then test one fixture with representative structure and one empty fixture.
4. Add `shipments[].packages[].note` which may be missing or `null`. Decide on using `optional()`, specify the type, and describe `null` semantics.
5. Create an endpoint returning a root array of line items. Reuse `itemFields()` with the `"[]."` prefix.
6. Change `metadata` to an object containing dynamic region keys such as `"HCM"`, `"HAN"`. Compare the `*` wildcard with fixed paths.
7. Build an overview table with `subsectionWithPath("shipments")`, then generate a detailed snippet for a sub-branch using `beneathPath(...)`.
8. Include `response-fields.adoc` in Asciidoctor and verify that changes to the fixture are reflected in the documentation after re-running the pipeline.

**Completion criteria:** you can identify each object/array level, place `[]` accurately at every repeating position, handle root arrays and dynamic keys, reuse descriptors with prefixes, and distinguish structural documentation verification from per-element business validation. As a result, complex response payloads can still be documented consistently from HTTP tests in Spring REST Docs.

### References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): JSON field path syntax, root arrays, wildcards, descriptor reuse, subsections, and test examples.
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): `fieldWithPath`, `responseFields`, `subsectionWithPath`, `beneathPath` APIs.
