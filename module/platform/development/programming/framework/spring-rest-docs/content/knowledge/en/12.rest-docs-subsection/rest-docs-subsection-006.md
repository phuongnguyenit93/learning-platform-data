# Distinguishing Subsection Documentation from Field Documentation in Spring REST Docs

## 1. Context and Objectives

**Spring REST Docs** generates verifiable REST API documentation based on real HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. When a test passes, the tool generates snippets for requests, responses, payloads, headers, and parameters. Those snippets are then included in Asciidoctor/Markdown documentation and built alongside the application in the build and CI pipeline.

This lesson belongs to the **Subsection** chapter and answers an important question: **When should you document individual fields, when should you document an entire subsection, and when should you extract a subsection into a separate snippet?**

Three concepts are frequently confused:

1. **Field documentation:** uses `fieldWithPath(...)` inside `requestFields(...)` or `responseFields(...)` to describe a specific JSON path.
2. **Subsection documentation:** uses `subsectionWithPath(...)` to describe a JSON branch consisting of an object or array and treats descendant fields of that branch as documented within the current field table.
3. **Subsection extraction:** uses `beneathPath(...)` to select part of a payload, then combines it with `requestFields(...)`, `responseFields(...)`, `requestBody(...)`, or `responseBody(...)` to generate a separate snippet.

After this lesson, you will know how to write descriptors matching your desired documentation depth, understand strict validation boundaries, specify paths correctly when documentation is extracted separately, and decide when to add API contract tests.

## 2. Shared Example: A Response with Multiple Data Levels

Suppose the `GET /orders/ord-314` API returns JSON:

```json
{
  "orderId": "ord-314",
  "state": "READY",
  "customer": {
    "id": "cus-10",
    "displayName": "An Pham",
    "contact": {
      "email": "an@example.test",
      "phone": "+84900000000"
    }
  },
  "items": [
    {
      "sku": "BK-101",
      "quantity": 2,
      "pricing": {
        "unitAmount": 50000,
        "currency": "VND"
      }
    },
    {
      "sku": "PN-002",
      "quantity": 1,
      "pricing": {
        "unitAmount": 10000,
        "currency": "VND"
      }
    }
  ],
  "total": {
    "amount": 110000,
    "currency": "VND"
  }
}
```

The fields sit across multiple levels:

```text
response
├── orderId
├── state
├── customer
│   ├── id
│   ├── displayName
│   └── contact
│       ├── email
│       └── phone
├── items[] 
│   ├── sku
│   ├── quantity
│   └── pricing
│       ├── unitAmount
│       └── currency
└── total
    ├── amount
    └── currency
```

An endpoint overview page may only need to state the five top-level components. Meanwhile, API integrators need to know what `customer.contact.email`, `items[].sku`, or `items[].pricing.unitAmount` mean. These two needs lead to **two different documentation depths**.

## 3. Comparison Table of Core APIs

| Tool | Definition | What Does It Check? | When Should You Use It? |
| --- | --- | --- | --- |
| `fieldWithPath("orderId")` | Descriptor for a single field at a specific path | Presence of the described field (unless optional), plus strict rules for other fields in the snippet | Leaf fields that need clear explanation |
| `fieldWithPath("customer.contact.email")` | Descriptor for a deeply nested field in an object | Specific path to email; does not intentionally skip sibling fields | Detailed schema documentation |
| `subsectionWithPath("customer")` | Descriptor for the entire `customer` branch | Branch exists (unless optional); descendants are treated as documented **in that snippet** | Concise overview table; details will be described elsewhere |
| `subsectionWithPath("items[].pricing")` | Descriptor for the `pricing` object of array elements | Covers descendant fields of the `pricing` branch | Describing a repeating object at an overview level |
| `beneathPath("customer")` | Extractor for part of a payload | Selects a subtree; not a field descriptor itself | Generating a separate body snippet or field table for `customer` |
| `responseFields(...)` | Handler generating a response field table | Strict by default across the documented payload scope | Documenting and verifying response fields |
| `requestFields(...)` | Handler generating a request field table | Strict by default across the documented payload scope | Documenting and verifying request fields |

**Key point of distinction:** `fieldWithPath` and `subsectionWithPath` both create **field descriptors** placed inside `requestFields`/`responseFields`; `beneathPath`, by contrast, **does not describe any field**. It only selects the part of the payload that another snippet processes.

### 3.1. Field Documentation: Stating the Concrete Data Contract

For example, if you want to describe key fields in detail:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Order ID"),
    fieldWithPath("state")
        .description("Processing state"),
    fieldWithPath("customer.id")
        .description("Customer ID"),
    fieldWithPath("customer.displayName")
        .description("Customer display name"),
    fieldWithPath("customer.contact.email")
        .description("Contact email"),
    fieldWithPath("customer.contact.phone")
        .description("Contact phone number"),
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Quantity of each line item"),
    fieldWithPath("items[].pricing.unitAmount")
        .description("Unit price of each item"),
    fieldWithPath("items[].pricing.currency")
        .description("Currency of the unit price"),
    fieldWithPath("total.amount")
        .description("Order total amount"),
    fieldWithPath("total.currency")
        .description("Currency of the total amount")
)
```

The table has many rows, which is appropriate when **this page is the source of detailed schema documentation**. The path `items[].sku` selects the `sku` field across elements of the `items` array; the path `items[0].sku` only refers to the first element and is unsuitable for documenting a variable-length list.

In a strict table, if the response adds `customer.loyaltyTier` or `items[].discount` without a matching descriptor, the test can fail. This is useful behavior when you need to detect unexpected schema changes.

### 3.2. Subsection Documentation: Presenting the Meaning of an Entire Group

An overview page only needs five rows:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Order ID"),
    fieldWithPath("state")
        .description("Processing state"),
    subsectionWithPath("customer")
        .description("Customer information; see customer documentation"),
    subsectionWithPath("items")
        .description("List of line items"),
    subsectionWithPath("total")
        .description("Total order value")
)
```

In this table, `subsectionWithPath("customer")` treats `customer.id`, `customer.displayName`, `customer.contact.email`, and other descendants as already documented. `subsectionWithPath("items")` behaves similarly for all fields inside the item list. Therefore, the overview snippet can remain valid even if the response adds a child field inside `customer` or `items`.

However, if the response adds `createdAt` at the **root**, the strict overview table will not treat `createdAt` as belonging to `customer`, `items`, or `total`; the test can fail until a descriptor is added or an explicit handling decision is made.

`subsectionWithPath(...)` fits when describing an entire branch as a **business concept**, but does not replace child schema documentation if clients need to know every field.

### 3.3. Subsection Extraction: Creating a Dedicated Snippet for a Branch

If you want a standalone table for `customer`:

```java
responseFields(
    beneathPath("customer").withSubsectionId("customer-details"),
    fieldWithPath("id")
        .description("Customer ID"),
    fieldWithPath("displayName")
        .description("Display name"),
    fieldWithPath("contact.email")
        .description("Contact email"),
    fieldWithPath("contact.phone")
        .optional()
        .description("Contact phone number, if available")
)
```

Here, `beneathPath("customer")` extracts the `customer` branch as the validation scope for a separate snippet. Subsequent field descriptors use paths **relative to the extracted branch**: `id`, `displayName`, `contact.email`, `contact.phone`. Writing `customer.contact.email` in a table that has already extracted `customer` will look in the wrong place.

If you want to add a JSON example of just that branch:

```java
responseBody(
    beneathPath("customer").withSubsectionId("customer-details")
)
```

The body snippet displays the JSON inside the `customer` branch, whereas the `responseFields(beneathPath(...), ...)` table describes the branch's fields. **A body snippet does not validate field completeness on its own**; to protect the schema, keep a strict field table or suitable assertions.

## 4. Complete Example with MockMvc

The example uses **JUnit 5**, **Java 17+**, **MockMvc**, **Spring MVC**, and **Spring REST Docs**. The sample controller returns fixed JSON to focus on the documentation mechanism. A real project should replace the sample controller with configured controllers and application test fixtures.

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
class OrderPayloadDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrdersController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOverviewAndCustomerDetails() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "ord-314")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-10"))
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(jsonPath("$.total.amount").value(110000))
                .andDo(document("orders-get",

                        // (1) Overview table: describes all top-level data groups.
                        responseFields(
                                fieldWithPath("orderId")
                                        .description("Order ID"),
                                fieldWithPath("state")
                                        .description("Processing state"),
                                subsectionWithPath("customer")
                                        .description("Customer information"),
                                subsectionWithPath("items")
                                        .description("Line items"),
                                subsectionWithPath("total")
                                        .description("Total order value")
                        ),

                        // (2) Detailed table for the customer branch.
                        responseFields(
                                beneathPath("customer")
                                        .withSubsectionId("customer-details"),
                                fieldWithPath("id")
                                        .description("Customer ID"),
                                fieldWithPath("displayName")
                                        .description("Display name"),
                                fieldWithPath("contact.email")
                                        .description("Contact email"),
                                fieldWithPath("contact.phone")
                                        .optional()
                                        .description("Phone number, if available")
                        ),

                        // (3) Dedicated JSON excerpt for the customer branch.
                        responseBody(
                                beneathPath("customer")
                                        .withSubsectionId("customer-details")
                        )
                ));
    }

    @RestController
    public static class SampleOrdersController {

        @GetMapping(value = "/orders/{orderId}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> getOrder(
                @PathVariable("orderId") String orderId) {

            if (!"ord-314".equals(orderId)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "orderId": "ord-314",
                      "state": "READY",
                      "customer": {
                        "id": "cus-10",
                        "displayName": "An Pham",
                        "contact": {
                          "email": "an@example.test",
                          "phone": "+84900000000"
                        }
                      },
                      "items": [
                        {
                          "sku": "BK-101",
                          "quantity": 2,
                          "pricing": {
                            "unitAmount": 50000,
                            "currency": "VND"
                          }
                        },
                        {
                          "sku": "PN-002",
                          "quantity": 1,
                          "pricing": {
                            "unitAmount": 10000,
                            "currency": "VND"
                          }
                        }
                      ],
                      "total": {
                        "amount": 110000,
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

### 4.1. What Each Part Handles

**`status().isOk()` and `jsonPath(...)`:** assertions ensure the endpoint returns the expected HTTP status and key business values. They are required because field documentation does not verify total calculations, order states, or item quantity rules on its own.

**Overview `responseFields(...)`:** creates a concise table of root-level fields/branches. `subsectionWithPath("customer")`, `subsectionWithPath("items")`, and `subsectionWithPath("total")` let each branch occupy a single row.

**`responseFields(beneathPath("customer"), ...)`:** creates another table for child fields. This table has an independent strict scope; the fact that the overview table covered `customer` does not cause the detailed table to ignore new fields.

**`responseBody(beneathPath("customer"))`:** creates a dedicated body excerpt to place on the customer detail page. It does not replace the schema table.

### 4.2. Why Can There Be Two Field Tables in One Test?

Each `responseFields(...)` call generates a separate snippet. The overview table gets the default name `response-fields.adoc`, while the extracted table with `withSubsectionId("customer-details")` is named `response-fields-customer-details.adoc`. Both snippets share one actual response, yet have **different documentation depths and validation scopes**.

If you want to document `items` in detail, you can create another test/snippet with descriptors `items[].sku`, `items[].quantity`, and `items[].pricing.unitAmount`. Avoid declaring two handlers with the same default snippet name under the same identifier: each piece of documentation needs a distinct output name to stay manageable.

## 5. The Same Change Can Produce Different Verification Results

Suppose the test in Section 4 runs against several response variants:

| Variant | Overview Table | Detailed `customer` Table | Reason |
| --- | --- | --- | --- |
| Add `customer.loyaltyTier` | May still pass | Fails in strict mode if `loyaltyTier` is undeclared | Subsection in overview table covers child fields; detailed table has its own descriptors |
| Add `customer.contact.social` | May still pass | Fails if `contact.social` is undeclared | New field falls within the detailed table's validation scope |
| Add `items[0].discount` | May still pass | Unrelated | `items` is covered in the overview; detailed table selects `customer` |
| Add `createdAt` at root | Fails if no descriptor | Unrelated | New field sits outside the declared subsections |
| Remove `customer.displayName` | Overview table may still pass if `customer` remains | Fails because `displayName` is required | Detailed table checks specific fields |
| Remove `customer.contact.phone` | Overview table may still pass | Passes because descriptor has `optional()` | Per contract, phone field may be absent |
| Remove `customer` completely | Overview table fails when `customer` is required | Cannot extract subsection to generate detailed table as expected | Path extractor needs the corresponding branch data |

**Strictness depends on each snippet's scope and descriptors.** "Test passed while documenting a subsection" should not be interpreted as every field inside that subsection having been thoroughly verified.

### What If the Remaining Parts Are Already Documented Elsewhere?

This scenario is very common. On the `GET /orders/{orderId}` page, the overview table only needs to list `customer` and point to a "Customer Schema" section. In that dedicated section, use the detailed snippet generated by `responseFields(beneathPath("customer"), ...)`. Both snippets can be generated from the same test, keeping documentation concise and reducing duplication.

The description line "see Customer Schema" does not cause REST Docs to automatically verify that the target document exists. You must include or link properly in Asciidoctor/Markdown and configure the build to fail on missing snippets.

## 6. Be Careful with Objects, Arrays, and Relative Paths

### 6.1. Nested Objects

In the root response:

- `customer`: path of the customer object.
- `customer.contact`: path of the contact object.
- `customer.contact.email`: path of the email field.

In the root table, `subsectionWithPath("customer.contact")` only covers the `contact` branch. If you still want a strict root-level table, other fields such as `customer.id` and `customer.displayName` need appropriate descriptors.

When using `beneathPath("customer")`, the corresponding field paths are `id`, `displayName`, and `contact.email`. When using `beneathPath("customer.contact")`, they become `email` and `phone`.

### 6.2. Arrays with Object Elements

Important paths:

| Structure | Path from Root |
| --- | --- |
| Entire list of line items | `items` |
| Product SKU of each item | `items[].sku` |
| Quantity of each item | `items[].quantity` |
| Pricing object inside each item | `items[].pricing` |
| Unit price of each item | `items[].pricing.unitAmount` |

Example selective table from the root:

```java
responseFields(
    fieldWithPath("orderId")
        .description("Order ID"),
    fieldWithPath("state")
        .description("Status"),
    subsectionWithPath("customer")
        .description("Customer information"),
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Quantity"),
    subsectionWithPath("items[].pricing")
        .description("Pricing info for each item"),
    subsectionWithPath("total")
        .description("Total value")
)
```

This is a different configuration from `subsectionWithPath("items")`: the table can catch a new undocumented field like `items[].note`, while still deliberately grouping `pricing` data.

**Empty array case:** `items: []` has the `items` key but contains no `items[].sku` fields. If a snippet requires fields on each element, a test using an empty array is unsuitable for generating that detailed table. Generate detailed docs from a fixture containing elements and keep a separate test verifying the empty-array response.

### 6.3. Paths for Special Keys

Standard dot notation separates object levels. If a real JSON key contains a literal dot—such as `"contact.email"` directly inside an object—you need the corresponding bracket notation like `['contact.email']` instead of treating the dot as a level separator. Always compare descriptor paths against the actual JSON received in the test.

## 7. Optional, Ignored Fields, and Relaxed Documentation

### 7.1. optional()

When a field is genuinely optional according to the contract:

```java
fieldWithPath("contact.phone")
    .optional()
    .description("Phone number, if available")
```

In the extracted `customer` table, the relative path is `contact.phone`. `optional()` allows this field to be absent; it does not exempt other fields from validation and does not mean the JSON can arbitrarily have the wrong type or violate business constraints.

If **the entire `customer` subsection** may be absent, the descriptor in the overview table can use `subsectionWithPath("customer").optional()`. When generating a detailed table with `beneathPath("customer")`, pick a test where that branch is present; a test for the variant without `customer` must be structured separately.

### 7.2. ignored()

`ignored()` allows declaring a known field while intentionally **excluding it from the documentation table**:

```java
fieldWithPath("internalTraceCode")
    .ignored()
```

This is useful when a fixture payload contains a technical field that public documentation does not need to explain. However, do not use `ignored()` just to mask unintended missing-descriptor errors. Skipping a field should be a decision grounded in the API contract.

### 7.3. relaxedResponseFields and relaxedRequestFields

If the goal is merely to introduce a couple of fields without requiring the entire payload to be described, you can use:

```java
relaxedResponseFields(
    fieldWithPath("orderId").description("Order ID"),
    fieldWithPath("state").description("Status")
)
```

`relaxedResponseFields(...)` allows fields without descriptors to exist without failing the snippet's **completeness check**. Consequently, a new `createdAt` field at the root may go unnoticed by this table. Declared required fields are still checked according to their descriptors.

Comparison:

| Need | Preferred Approach | Limitation to Know |
| --- | --- | --- |
| Document all key fields on the current page | Strict `responseFields(fieldWithPath(...), ...)` | Table can grow long for deeply nested JSON |
| Document data groups while child fields have separate docs | Strict `responseFields(subsectionWithPath(...), ...)` | Overview table does not validate child field details |
| Select only a subset of fields; allow unlisted remaining fields | `relaxedResponseFields(...)` | May miss field changes outside the declared scope |
| Intentionally exclude a specific known field from the table | `ignored()` on the descriptor | Does not replace deciding which schema to publish |

These same rules apply to `requestFields(...)` and `relaxedRequestFields(...)` when documenting request payloads.

## 8. Comparing with Request Field Documentation

Suppose the `POST /orders` endpoint receives the request:

```json
{
  "customerId": "cus-10",
  "items": [
    {
      "sku": "BK-101",
      "quantity": 2
    }
  ],
  "delivery": {
    "recipient": "An Pham",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  }
}
```

**Request overview** table:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Ordering customer"),
    subsectionWithPath("items")
        .description("Line items"),
    subsectionWithPath("delivery")
        .description("Delivery information")
)
```

**Detailed request** table for the `delivery` branch:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Recipient name"),
    fieldWithPath("address.city")
        .description("City"),
    fieldWithPath("address.country")
        .description("Country code")
)
```

To build the test with MockMvc, send the request with `.contentType(MediaType.APPLICATION_JSON).content(requestJson)`, assert status before calling `.andDo(document("orders-create", ...))`. When the test succeeds, `request-fields.adoc` and `request-fields-delivery.adoc` can be generated under the same identifier.

**The difference between request and response does not lie in subsections:** descriptor declarations remain identical, except request documentation verifies the payload sent by the client while response documentation verifies the payload returned by the server.

## 9. Generating Snippets and Assembling into Asciidoctor Documentation

With the `documentOverviewAndCustomerDetails` test in Section 4, output is typically placed at `build/generated-snippets/orders-get/` in a Gradle project configured with Spring REST Docs:

| Snippet | Generated By | Role |
| --- | --- | --- |
| `http-response.adoc` | Default HTTP response snippet | Displays the full tested response |
| `response-body.adoc` | Default response body snippet | Displays the full response JSON |
| `response-fields.adoc` | Root-level `responseFields(...)` | Overview table with `customer`, `items`, `total` |
| `response-fields-customer-details.adoc` | `responseFields(beneathPath("customer").withSubsectionId("customer-details"), ...)` | Detailed field table for `customer` |
| `response-body-customer-details.adoc` | `responseBody(beneathPath("customer").withSubsectionId("customer-details"))` | JSON extracted separately from `customer` |

Default snippets and exact paths depend on project configuration. The `customer-details` suffixes in the table above are determined by `withSubsectionId(...)`.

Example `src/docs/asciidoc/orders.adoc`:

```asciidoc
= Order API
:toc: left

== GET /orders/{orderId}

Look up an order with its list of products and customer information.

=== HTTP Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response Data Groups

include::{snippets}/orders-get/response-fields.adoc[]

=== Customer JSON

include::{snippets}/orders-get/response-body-customer-details.adoc[]

=== Customer Fields

include::{snippets}/orders-get/response-fields-customer-details.adoc[]
```

The `include::{snippets}/...[]` directive belongs to Asciidoctor; the `snippets` attribute must point to the directory generated by REST Docs. If the details live in another document, you can move the two `include` directives for `customer` to a customer fragment/page and link from the endpoint page. Splitting pages does not change the snippet inputs.

## 10. Integrating into Gradle and CI

For a project that already applies the Asciidoctor plugin, JUnit, and the `spring-restdocs-mockmvc` dependency, a Gradle example (Groovy DSL) can bind the documentation generation step to the test execution step:

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

The project needs to configure REST Docs to write snippets to the matching `snippetsDir`, and Asciidoctor to use the exact `snippets` attribute. Then in CI you can run:

```bash
./gradlew clean test asciidoctor
```

If a new field breaks a strict table, the test will fail and the test-dependent documentation build step cannot succeed. An `include` pointing to the wrong snippet file should also be treated as a documentation error in the pipeline. With Maven, the snippet generation path is typically `target/generated-snippets`; the test dependency principle remains the same.

If the project uses Markdown as its output format, choose the corresponding Markdown templates/snippets and assembly step. The `include::[]` examples in this lesson are for Asciidoctor.

## 11. Using with WebTestClient or REST Assured

Payload documentation APIs in `PayloadDocumentation` can be reused across all three testing options; the main difference is where the `document(...)` handler is attached to the HTTP exchange.

### WebTestClient

Assuming `webTestClient` is already configured with Spring REST Docs and `document` is statically imported from `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-314")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-webtestclient",
        responseFields(
            fieldWithPath("orderId").description("Order ID"),
            fieldWithPath("state").description("Status"),
            subsectionWithPath("customer").description("Customer"),
            subsectionWithPath("items").description("Line items"),
            subsectionWithPath("total").description("Total amount")
        ),
        responseFields(
            beneathPath("customer").withSubsectionId("customer-details"),
            fieldWithPath("id").description("Customer ID"),
            fieldWithPath("displayName").description("Display name"),
            fieldWithPath("contact.email").description("Email"),
            fieldWithPath("contact.phone").optional()
                .description("Phone number if available")
        )
    ));
```

### REST Assured

Assuming `spec` is a `RequestSpecification` configured with the REST Docs filter and `document` is statically imported from `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-restassured",
        responseFields(
            fieldWithPath("orderId").description("Order ID"),
            fieldWithPath("state").description("Status"),
            subsectionWithPath("customer").description("Customer"),
            subsectionWithPath("items").description("Line items"),
            subsectionWithPath("total").description("Total amount")
        )
    ))
    .when()
    .get("/orders/ord-314")
    .then()
    .statusCode(200);
```

These two snippets illustrate where to attach the documentation handler; before running, each project must configure the corresponding client/filter, server, or controller test. The ability to produce overview and detailed field tables does not depend on how the HTTP request is sent.

## 12. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `response-fields.adoc` table is too long | Documented every nested field directly inside a single overview table | Use `subsectionWithPath` on major branches and create separate detailed tables when needed |
| Added `customer.vipLevel` yet overview table still passes | `subsectionWithPath("customer")` covers descendants in the overview table | Use a strict `responseFields(beneathPath("customer"), ...)` table to catch new fields |
| Adding `createdAt` at root makes test fail | New field does not belong to any documented subsection | Add a descriptor if the field belongs to the contract |
| Detailed table cannot find `customer.contact.email` | `customer` was extracted, yet the path is still written from the root | Use `contact.email` |
| Separate snippet for `customer` does not exist | Only called `subsectionWithPath("customer")` | Add `responseFields(beneathPath("customer")...)` or `responseBody(beneathPath("customer"))` |
| Test using an empty array fails when documenting `items[].sku` | There are no elements containing a `sku` field | Generate the detailed table from a fixture with items; test empty arrays in another case |
| Documentation still passes when response has many new fields | Used `relaxedResponseFields(...)` without other checks | Use strict mode and descriptors with clear subsection boundaries |
| Asciidoctor cannot find `response-fields-customer-details.adoc` | Wrong subsection ID, identifier, or snippet directory | Compare generated filenames with `include` directives |
| Test has right values but wrong schema | Used only assertions on a few fields and skipped schema documentation | Combine business assertions with strict field documentation |

## 13. Practice Exercise

Follow these steps in order to test your understanding of each technique's **scope**:

1. **Create a full table:** replace the `subsectionWithPath("customer")`, `subsectionWithPath("items")`, and `subsectionWithPath("total")` descriptors with detailed `fieldWithPath(...)` descriptors. Observe the row count in `response-fields.adoc`.
2. **Create a summary table:** restore the overview table and keep the detailed `customer` table. Verify that both `response-fields.adoc` and `response-fields-customer-details.adoc` are generated.
3. **Add a field inside a subsection:** add `customer.loyaltyTier` to the JSON. Observe why the overview table can remain valid while the strict detailed table fails. Add the new detailed descriptor.
4. **Add a field at the root:** add `createdAt` to the JSON. Verify that the strict overview table catches the field outside existing subsections.
5. **Change the extractor scope:** replace `beneathPath("customer")` with `beneathPath("customer.contact")`, update the detailed descriptors to `email` and `phone`, and update the subsection ID and `include` directives.
6. **Test variants:** try a response without `customer.contact.phone` using an `optional()` descriptor, then try removing `optional()`. Write another test for the case where all of `customer` is absent if the contract allows it.
7. **Compile documentation:** run `./gradlew clean test asciidoctor` after configuring the project, then inspect the HTML to compare the overview table, extracted JSON, and detailed table.

**Completion criteria:** you clearly distinguish the meaning of `fieldWithPath`, `subsectionWithPath`, and `beneathPath`; explain why strict tables at different scopes can produce different outcomes; and create API documentation that is both readable and backed by tests protecting key schemas.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): rules for documenting fields, subsections, JSON paths, and request/response payload completeness.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): integrating MockMvc, WebTestClient, REST Assured, snippets, and building documentation.
