# When the Remaining Parts Are Documented Elsewhere

## 1. Context: Large API Documentation Needs to Be Split into Multiple Parts

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. Once tests succeed, snippets covering the HTTP request, response, payload, parameters, and headers can be assembled into **Asciidoctor/Markdown**, and then integrated into the build and CI pipeline.

This lesson belongs to the **Subsection** chapter and focuses on the scenario where **one documentation page explains only part of a payload, while the remaining parts are explained in detail on another page or in another documentation section**.

A large response might include order details, customer info, delivery info, and total amount. If every field is placed into a single table, readers struggle to find information, explanations get duplicated across endpoints, and documentation becomes hard to reuse. In such cases, you need to clearly separate:

- **Overview table:** describes the endpoint's contract at a high level, pointing out the data groups.
- **Detailed tables:** describe the fields inside each group, which may appear in another chapter/page.
- **Documentation links:** guide readers from the overview table to the detailed documentation.
- **Tests:** verify that data groups are documented within their intended scope.

**Learning objective:** understand how to combine `subsectionWithPath(...)`, `beneathPath(...)`, and `responseFields(...)`/`requestFields(...)` to split documentation while still catching unintended payload changes; and know when to use `relaxedResponseFields(...)` or `ignored()`.

## 2. Example: One Response, Multiple Documentation Pages

Suppose the `GET /orders/ord-120` endpoint returns a `200 OK` response:

```json
{
  "id": "ord-120",
  "status": "PAID",
  "customer": {
    "id": "cus-8",
    "name": "Lan Nguyen",
    "contact": {
      "email": "lan@example.test"
    }
  },
  "delivery": {
    "recipient": "Lan Nguyen",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  },
  "total": {
    "amount": 250000,
    "currency": "VND"
  }
}
```

Instead of building one long table for the entire response, the documentation is organized as follows:

```text
Order API Documentation
├── GET /orders/{id}
│   ├── Full HTTP response example
│   ├── id: order ID
│   ├── status: status
│   ├── customer: see "Customer Information"
│   ├── delivery: see "Delivery Information"
│   └── total: see "Amount Conventions"
├── Customer Information
│   ├── customer.id
│   ├── customer.name
│   └── customer.contact.email
├── Delivery Information
│   ├── delivery.recipient
│   ├── delivery.address.city
│   └── delivery.address.country
└── Amount Conventions
    ├── total.amount
    └── total.currency
```

The detailed tables in the sections below can use snippets generated from **the same test**. Each table still retains the ability to validate fields within its own scope.

In the overview table, use:

```java
responseFields(
    fieldWithPath("id")
        .description("Order ID"),
    fieldWithPath("status")
        .description("Order status"),
    subsectionWithPath("customer")
        .description("Customer information; see Customer Information"),
    subsectionWithPath("delivery")
        .description("Delivery information; see Delivery Information"),
    subsectionWithPath("total")
        .description("Total amount; see Amount Conventions")
)
```

`subsectionWithPath("customer")` represents **the entire `customer` child object**, including descendants like `customer.name` and `customer.contact.email`. Similarly, the descriptors for `delivery` and `total` cover their respective branches.

The overview table is in **strict** mode by default: root-level fields like `id`, `status`, and the subsections are documented; if the response unexpectedly adds a `promotionCode` field at the root level, the test can fail because there is no descriptor for it. However, the overview table does not automatically police every field inside each subsection: adding `customer.vipLevel` can still pass for the **overview snippet**. To protect child schemas, create separate detailed snippets.

## 3. Two Complementary Tools

| Spring REST Docs API | Role | When to Use |
| --- | --- | --- |
| `fieldWithPath("id")` | Describes a specific field | The field is explained directly in the current table |
| `subsectionWithPath("customer")` | Describes an entire branch and treats child fields as documented in the current snippet | A large branch has a detailed table/page elsewhere |
| `beneathPath("customer")` | Selects the payload portion under a path as input for a separate snippet | You want to generate a body or detailed field table for the branch |
| `responseFields(beneathPath(...), ...)` | Validates and describes fields by paths relative to the selected branch | Documenting a response child schema |
| `requestFields(beneathPath(...), ...)` | Same, but applied to a request | Documenting a request child schema |
| `responseBody(beneathPath(...))` | Generates a body excerpt for only the selected branch | You want to include a readable JSON example on the detail page |

**Distinctions to keep in mind:**

- `subsectionWithPath(...)` is a **field descriptor**. It does not produce a separate child JSON file or a new detailed table.
- `beneathPath(...)` is a **subsection extractor**. When combined with `responseFields(...)` or `requestFields(...)`, descriptors inside use **relative paths**: from `customer`, write `contact.email` instead of `customer.contact.email`.
- Writing in a description that a group is "documented elsewhere" is only informational for human readers. **Spring REST Docs does not automatically verify links between two pages**; the development team must generate the detailed snippets and assemble the documentation accurately.

## 4. Complete Example: MockMvc Test Generating Both Overview and Detailed Sections

The example below uses **JUnit 5**, **Java 17+**, **MockMvc**, **Spring MVC**, and **Spring REST Docs**. The sample controller returns fixed data so you can observe the snippets directly; in a real project, replace the sample controller with your business controller and deterministic test fixtures.

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
class OrderSplitDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOverviewAndSeparatedSections() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-120")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer.id").value("cus-8"))
                .andExpect(jsonPath("$.delivery.address.country").value("VN"))
                .andExpect(jsonPath("$.total.amount").value(250000))
                .andDo(document("orders-get",

                        // (1) Overview table: child objects are subsections.
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                subsectionWithPath("customer")
                                        .description("Customer; see Customer section"),
                                subsectionWithPath("delivery")
                                        .description("Delivery; see Delivery section"),
                                subsectionWithPath("total")
                                        .description("Total amount; see Amount section")
                        ),

                        // (2) Detailed table to be embedded in the Customer page.
                        responseFields(
                                beneathPath("customer")
                                        .withSubsectionId("customer"),
                                fieldWithPath("id")
                                        .description("Customer ID"),
                                fieldWithPath("name")
                                        .description("Display name"),
                                fieldWithPath("contact.email")
                                        .description("Contact email")
                        ),

                        // (3) Detailed table to be embedded in the Delivery page.
                        responseFields(
                                beneathPath("delivery")
                                        .withSubsectionId("delivery"),
                                fieldWithPath("recipient")
                                        .description("Recipient"),
                                fieldWithPath("address.city")
                                        .description("Delivery city"),
                                fieldWithPath("address.country")
                                        .description("Country code")
                        ),

                        // (4) Detailed table to be embedded in the Amount page.
                        responseFields(
                                beneathPath("total")
                                        .withSubsectionId("total"),
                                fieldWithPath("amount")
                                        .description("Amount (smallest unit per contract)"),
                                fieldWithPath("currency")
                                        .description("Currency code")
                        ),

                        // (5) Dedicated body example for the Customer page.
                        responseBody(
                                beneathPath("customer")
                                        .withSubsectionId("customer"))
                ));
    }

    @RestController
    public static class SampleOrderController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> findById(@PathVariable String id) {
            if (!"ord-120".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-120",
                      "status": "PAID",
                      "customer": {
                        "id": "cus-8",
                        "name": "Lan Nguyen",
                        "contact": {
                          "email": "lan@example.test"
                        }
                      },
                      "delivery": {
                        "recipient": "Lan Nguyen",
                        "address": {
                          "city": "Ho Chi Minh City",
                          "country": "VN"
                        }
                      },
                      "total": {
                        "amount": 250000,
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

You need JUnit Jupiter, Spring MVC Test, and `spring-restdocs-mockmvc` on the test classpath, along with configuration for the snippet output location. The sample code uses Java text blocks and therefore requires Java 17+.

In this test, there are **four distinct `responseFields(...)` calls**. Each call produces a snippet: the overview table uses the default ID, while the three detailed tables use subsection IDs so they do not overwrite one another. The `jsonPath` assertions verify several important business values; strict field tables help validate the schema, but do not replace business or API validation tests.

### 4.1. Root-Level Table Covers Branches Explained Elsewhere

From the response root, the overview table documents five parts: `id`, `status`, `customer`, `delivery`, and `total`. Because the child objects are described with `subsectionWithPath`, Spring REST Docs does not require child fields to appear as rows in the **overview table**.

This approach works well when the `GET /orders/{id}` page needs to introduce the response structure, while customer/delivery/currency contracts already have dedicated in-depth explanations.

### 4.2. Each Detailed Table Has Its Own Paths

When declaring `responseFields(beneathPath("customer").withSubsectionId("customer"), ...)`, REST Docs operates on the extracted `customer` branch. The detailed table has:

| Field shown in detailed table | Full path in root response |
| --- | --- |
| `id` | `customer.id` |
| `name` | `customer.name` |
| `contact.email` | `customer.contact.email` |

Similarly, with `beneathPath("delivery")`, the paths are `recipient`, `address.city`, `address.country`; with `beneathPath("total")`, the paths are `amount`, `currency`.

Important technical point: **each detailed table is independently strict**. The root-level table covers all of `customer`; the detailed `customer` table can still fail if a new `customer.phone` field appears without a descriptor. Coverage in one snippet does not relax other snippets.

### 4.3. A Separate Body Is Just an Example; Only Field Tables Validate Schema

`responseBody(beneathPath("customer").withSubsectionId("customer"))` generates a text snippet of the body portion extracted from `customer`. It helps readers inspect a shorter JSON structure compared to the full HTTP response, but `responseBody(...)` itself does not require a list of descriptors to validate every field.

If you want both the body displayed on a page and the schema verified, combine the **body snippet** with the **field snippet** of the same subsection as shown in the example. When a documentation page only needs the field table, you can omit the body snippet.

## 5. Generated Snippets and How to Lay Them Out

Suppose REST Docs output is configured to `build/generated-snippets` and uses the default Asciidoctor templates. When the test passes, the key files will be under `build/generated-snippets/orders-get/`:

| File | Generated By | Intended Location in Docs |
| --- | --- | --- |
| `http-response.adoc` | Tested HTTP exchange | `GET /orders/{id}` endpoint page |
| `response-fields.adoc` | Root-level `responseFields(...)` | Endpoint page, overview table |
| `response-fields-customer.adoc` | `responseFields(beneathPath("customer")...)` | Customer detail page |
| `response-fields-delivery.adoc` | `responseFields(beneathPath("delivery")...)` | Delivery detail page |
| `response-fields-total.adoc` | `responseFields(beneathPath("total")...)` | Amount conventions page |
| `response-body-customer.adoc` | `responseBody(beneathPath("customer")...)` | Payload example on Customer page |

**Note:** `withSubsectionId("customer")` determines the snippet filename suffix. If no ID is set, REST Docs uses a default name based on `beneathPath` and the path. Therefore, `include` directives must reference the actual generated filenames.

### 5.1. Endpoint Page Containing Only the Overview

Example `src/docs/asciidoc/orders.adoc`:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Look up an order by its identifier.

=== Sample Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response Data Groups

include::{snippets}/orders-get/response-fields.adoc[]

See details at:

* <<customer-fields,Customer Information>>
* <<delivery-fields,Delivery Information>>
* <<money-fields,Amount Conventions>>

include::fragments/customer-fields.adoc[]
include::fragments/delivery-fields.adoc[]
include::fragments/money-fields.adoc[]
```

Here, the fragments are included **after** the overview table to form a multi-section Asciidoctor document. If the project uses **separate HTML pages**, replace the anchor references with `xref` links matching your project's Asciidoctor/Antora configuration. Do not use anchor links to a page that is not included.

### 5.2. Customer Fragment Containing Its Own Field Table

`src/docs/asciidoc/fragments/customer-fields.adoc`:

```asciidoc
[[customer-fields]]
== Customer Information

The customer branch contains the identifier and contact information
of the customer associated with the order.

=== Customer JSON Example

include::{snippets}/orders-get/response-body-customer.adoc[]

=== Customer Fields

include::{snippets}/orders-get/response-fields-customer.adoc[]
```

### 5.3. Delivery and Amount Fragments

`src/docs/asciidoc/fragments/delivery-fields.adoc`:

```asciidoc
[[delivery-fields]]
== Delivery Information

Fields describing the recipient and address of the order.

include::{snippets}/orders-get/response-fields-delivery.adoc[]
```

`src/docs/asciidoc/fragments/money-fields.adoc`:

```asciidoc
[[money-fields]]
== Amount Conventions

amount is an integer; currency is the currency code.
The application must clearly specify the unit of amount in the contract.

include::{snippets}/orders-get/response-fields-total.adoc[]
```

**Result:** the overview table stays concise, while readers can still find complete schema tables in other sections. All snippets in this example are generated from **a single tested HTTP exchange**, reducing the risk of manually written tables contradicting one another.

## 6. What Does "Documented Elsewhere" Mean for Strict Validation?

In Spring REST Docs, `responseFields(...)` and `requestFields(...)` are **strict** by default: a new field within the snippet's scope that is not covered by an appropriate descriptor will cause the test to fail. Writing "see other documentation" inside `description(...)` **does not change** this behavior.

Compare the scenarios when the API changes:

| Change in response | Overview table | Related detailed table |
| --- | --- | --- |
| Add `createdAt` at root level | May fail: missing descriptor for the new root field | Subsection tables do not see this root field |
| Add `customer.vipLevel` | May still pass: `customer` is already covered | Strict `customer` table may fail due to missing `vipLevel` descriptor |
| Add `delivery.address.street` | May still pass: `delivery` is already covered | Strict `delivery` table may fail due to missing `address.street` |
| Remove `total.currency` | Overview table may still pass if `total` still exists | `total` table may fail because required `currency` field is missing |
| Remove `customer` completely | Overview table may fail because required `customer` subsection is missing | `beneathPath("customer")` extractor no longer has data to extract as expected |

Each detailed table has its own scope; that is why you should combine **overview documentation + strict tables for key branches** when the API needs schema guarantees.

### No Automatic Link Checking Between Pages

Spring REST Docs does not parse Asciidoctor pages to confirm that every row in an overview table has a valid link to detailed documentation. Nor does it require `customer-fields.adoc` to exist just because the `customer` descriptor says "see Customer section".

Therefore, the build pipeline should both run tests to generate snippets and compile the documentation to catch `include` directives with missing files. You can add link, anchor, or rendered-output checks in CI if the project has multiple pages.

### What If Detailed Documentation Does Not Exist Yet?

If you only declare `subsectionWithPath("customer")` at the root without writing a `customer` table, the root-level strict test can still pass. The documentation is only complete at the **overview** level and does not verify the contract of individual customer fields.

If the team genuinely plans to put details on another page, generate the detailed snippet and cross-reference within the same publishing workflow. If the entire schema is already documented in another module, you should still have tests confirming that the current endpoint conforms to that schema, especially when data can vary by endpoint.

## 7. When to Choose relaxedResponseFields or ignored?

There are three approaches commonly confused when a document only discusses part of a response.

### 7.1. Use subsectionWithPath When You Know the Scope of the Remaining Parts

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Status"),
    subsectionWithPath("customer")
        .description("See Customer Information"),
    subsectionWithPath("delivery")
        .description("See Delivery Information"),
    subsectionWithPath("total")
        .description("See Amount Conventions")
)
```

This fits the example structure: the remaining groups are **clearly named**. A new field outside these groups can still cause the strict test to fail.

### 7.2. Use relaxedResponseFields When You Only Want a Few Fields Without Controlling the Rest

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
    fieldWithPath("id")
        .description("Order ID"),
    fieldWithPath("status")
        .description("Status")
)
```

`relaxedResponseFields(...)` does not require every appearing field to be documented. Remaining fields are ignored in the completeness check, including any new root field. Declared descriptors must still match the payload according to their constraints.

This option suits a page that only introduces a couple of fields and intentionally avoids enforcing completeness on that page. **It does not guarantee** that the omitted fields are actually documented elsewhere. If you want to split documentation into named subsections, the approach in `7.1` is clearer and better verified.

Similarly, `relaxedRequestFields(...)` applies to request payloads when the documentation selectively describes only a few fields.

### 7.3. Use ignored for Fields That Should Not Appear in the Table

```java
responseFields(
    fieldWithPath("id")
        .description("Order ID"),
    fieldWithPath("status")
        .description("Status"),
    fieldWithPath("internalFlag")
        .ignored(),
    subsectionWithPath("customer")
        .description("See Customer Information"),
    subsectionWithPath("delivery")
        .description("See Delivery Information"),
    subsectionWithPath("total")
        .description("See Amount Conventions")
)
```

This example assumes the actual payload contains `internalFlag`, a known technical field. `ignored()` indicates that the field is accounted for in documentation validation without appearing in the table. Only use this when intentionally withholding a field from publication; if the field is part of a public contract already documented on another page, `subsectionWithPath(...)` with a link usually expresses intent better.

### Comparison Table for Choosing an Approach

| Practical Need | Preferred API | What to Keep in Mind |
| --- | --- | --- |
| Name a child object and point to detailed docs | `subsectionWithPath("object")` | Root-level table does not validate internal object details |
| Generate a dedicated validation table for an object | `responseFields(beneathPath("object"), ...)` | Use relative paths and a distinct subsection ID |
| Only want an illustrative JSON snippet of the object | `responseBody(beneathPath("object"))` | Body snippet does not validate every field on its own |
| Document only a few fields, allowing unlisted fields | `relaxedResponseFields(...)` | May miss new root fields |
| Intentionally exclude a known field from the table | `ignored()` | Not equivalent to documenting the schema elsewhere |

## 8. When Request Parts Are Documented on Another Page

The same split can be applied to the request of `POST /orders`:

```json
{
  "customerId": "cus-8",
  "delivery": {
    "recipient": "Lan Nguyen",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  },
  "payment": {
    "method": "CARD",
    "token": "tok_example_only"
  }
}
```

The order creation page wants to focus on the customer ID and briefly mention the two blocks explained elsewhere:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    subsectionWithPath("delivery")
        .description("Delivery information; see Delivery section"),
    subsectionWithPath("payment")
        .description("Payment information; see Payment section")
)
```

The delivery page can embed a dedicated field table generated by the handler:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Recipient"),
    fieldWithPath("address.city")
        .description("City"),
    fieldWithPath("address.country")
        .description("Country code")
)
```

In the MockMvc test for the POST endpoint, these handlers are passed into the same `document("orders-create", ...)` call, producing snippets named `request-fields.adoc` and `request-fields-delivery.adoc`. The request data is provided via `.contentType(MediaType.APPLICATION_JSON).content(requestJson)`, followed by HTTP status assertions before `.andDo(document(...))`.

**Note:** detailed request snippets require fixture data containing the branch to extract. If an optional branch is absent in one use case, generate the detailed docs from a test case that includes the branch and write a separate behavioral test for requests without the branch.

Never use real payment token values in fixtures or published snippets. The example data in this lesson is strictly dummy data.

## 9. WebTestClient and REST Assured Follow the Same Principles

`PayloadDocumentation` provides `fieldWithPath`, `subsectionWithPath`, `beneathPath`, and payload handlers for all three HTTP testing choices. The main difference is how `document(...)` is attached.

**WebTestClient:** assuming `webTestClient` is already configured with Spring REST Docs and `document` is statically imported from `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-120")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-webtestclient",
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Status"),
            subsectionWithPath("customer").description("See Customer section"),
            subsectionWithPath("delivery").description("See Delivery section"),
            subsectionWithPath("total").description("See Amount section")
        ),
        responseFields(
            beneathPath("customer").withSubsectionId("customer"),
            fieldWithPath("id").description("Customer ID"),
            fieldWithPath("name").description("Name"),
            fieldWithPath("contact.email").description("Email")
        )
    ));
```

**REST Assured:** assuming `spec` is a `RequestSpecification` configured with the REST Docs filter and `document` is statically imported from `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-restassured",
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Status"),
            subsectionWithPath("customer").description("See Customer section"),
            subsectionWithPath("delivery").description("See Delivery section"),
            subsectionWithPath("total").description("See Amount section")
        )
    ))
    .when()
    .get("/orders/ord-120")
    .then()
    .statusCode(200);
```

The snippets above are examples of **documentation handlers** and do not include the full setup of the test client/request specification. The data source for snippets remains the executed HTTP exchange, keeping documentation updated alongside tests.

## 10. Integrating Asciidoctor/Markdown into Gradle and CI

After tests generate snippets, the documentation build process must run **after** the test step. For example, with Gradle Groovy DSL, assuming the project already applies the Asciidoctor plugin and has the Spring REST Docs dependency:

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

You can run:

```bash
./gradlew clean test asciidoctor
```

This configuration links test execution to documentation authoring. If a test fails due to a missing descriptor in a detailed table, the test-dependent documentation build step is blocked. If an Asciidoctor page includes a snippet file that has not been generated, compilation should fail so the team updates the identifier or path.

Several operational rules:

1. **Generate snippets from tests with deterministic fixtures.** Avoid relying on dynamic data or real accounts that could cause JSON samples to change unexpectedly.
2. **Choose meaningful subsection IDs.** For example `customer`, `delivery`, and `total` to keep filenames readable and easy to reference.
3. **Build documentation from freshly generated snippets.** Run a clean build or manage cleanup of stale snippets to avoid documentation referencing old files from a previous run.
4. **Verify links between pages.** In Asciidoctor, anchor links only work if the target actually exists in the rendered document; for multi-page setups, configure appropriate cross-page linking.
5. **Avoid manually duplicated descriptions.** When an object is explained in a dedicated section, use `include` on snippets rather than copying field tables across multiple pages.
6. **Clarify shared contracts.** If `customer` appears across multiple endpoints, confirm that data and constraints match; referencing shared documentation does not replace tests verifying each endpoint's behavior.

In Maven projects, the typical snippet directory is `target/generated-snippets`. Whether using Maven or Gradle, the key condition is that running tests, generating snippets, and building documentation must use a consistent output path.

When generating Markdown documentation, choose templates/snippets and file inclusion mechanisms appropriate for the Markdown pipeline. The `include::{snippets}/...[]` examples in this lesson use Asciidoctor.

## 11. Common Errors

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Overview table passes when `customer` gains a new field | `subsectionWithPath("customer")` covers descendants in the overview snippet | Check a separate strict table for `customer` to detect changes |
| Test reports a new `createdAt` field is undocumented | Field was added at root level, outside the described subsections | Add a root-level descriptor if permitted by the contract |
| Detailed table reports `customer.name` missing | `beneathPath("customer")` was selected, yet the path still has the `customer.` prefix | Write `name` in the detailed table |
| Cannot find `response-fields-customer.adoc` | `responseFields(beneathPath(...))` handler was not used or the subsection ID differs | Check handler code, filename, and snippets directory |
| Page says "see Customer section" but link does not work | Target is not included or anchor is wrong | Check `include::fragments/customer-fields.adoc[]` and ID `[[customer-fields]]` |
| Test passes despite many undocumented fields | Used `relaxedResponseFields(...)` on a page intended to be strict | Use a subsection descriptor at the appropriate branch or add a strict detailed table |
| Documentation shows an outdated field table | Build used snippets from a previous run | Clean output appropriately, re-run tests, and rebuild docs |
| Subsection is absent in a response variant | Fixture lacks the branch while a handler uses `beneathPath(...)` | Generate detailed snippets in a test with the branch; write another test for the variant without it |
| Multiple pages repeat descriptions and become inconsistent | Manually copying field tables | Use shared fragments or snippet references and verify equivalent contracts |

## 12. Practice Exercise

Extend `OrderSplitDocumentationTest` with the following tasks:

1. **Detect a new root field.** Add `createdAt` to the response. Verify the strict overview table reports it as undocumented; add the appropriate descriptor and re-run.
2. **Detect a new field in a subsection.** Add `customer.vipLevel`. Compare the overview table result with the detailed `customer` table. Add the `vipLevel` descriptor to the dedicated table, then update the customer page content.
3. **Actually split pages.** Create `orders.adoc`, `fragments/customer-fields.adoc`, `fragments/delivery-fields.adoc`, and `fragments/money-fields.adoc` per the example. Verify that anchors from the overview table navigate to the detailed sections in HTML.
4. **Compare strict and relaxed.** Temporarily replace the overview table with `relaxedResponseFields(...)` containing only `id` and `status`. Add a new root field to see if the test still catches that change; then restore the version with subsection descriptors.
5. **Apply to requests.** Write a `POST /orders` test generating root-level `request-fields.adoc` and `request-fields-delivery.adoc` for the `delivery` branch. Compare relative paths against the original JSON.
6. **Build/CI.** Run `./gradlew clean test asciidoctor` in a configured project. Intentionally rename a snippet in an `include` directive to verify whether the pipeline catches missing snippet documentation.

**Completion criteria:** you can explain why documenting part of a payload on another page is not synonymous with skipping schema validation, place `subsectionWithPath` in overview tables and `beneathPath` in detailed tables, and construct consistent `include` paths.

## 13. Self-Check Questions

**Question 1. If `customer` is documented on another page, is calling `relaxedResponseFields(...)` sufficient?**

Not necessarily. `relaxedResponseFields` allows unlisted fields to exist without raising completeness errors. If you want the overview table to stay strict for the remaining fields, use `subsectionWithPath("customer")` and the necessary descriptors. To genuinely validate the `customer` schema, create a detailed snippet or appropriate tests.

**Question 2. Does `subsectionWithPath("customer")` generate `response-fields-customer.adoc`?**

No. It creates one row in the current field table and covers the child branch for that table's validation. A detailed snippet can be generated with `responseFields(beneathPath("customer").withSubsectionId("customer"), ...)`.

**Question 3. If the overview table passes, does the `customer` table definitely pass?**

No. Each table has its own scope and descriptors. The overview table can allow a new field under `customer`, while a strict detailed table can catch that the field is undocumented.

**Question 4. Does using an `include` directive guarantee the entire schema is verified?**

No. `include` is a documentation assembly step. Verification comes from HTTP tests and snippet handlers. You must ensure snippets contain complete descriptors for the scope that needs validation.

**Question 5. What if a subsection is optional or absent?**

You can use `optional()` on a contract-appropriate descriptor to allow the field to be absent. However, `beneathPath(...)` requires actual data to generate a detailed snippet, so use a test case containing the subsection for documentation and another test case for the variant without the subsection.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptions, documenting subsections, strict/relaxed field documentation, and extracting part of a payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): integrating MockMvc, WebTestClient, REST Assured, snippets, Asciidoctor, and the build workflow.
