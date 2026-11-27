# Specifying the Meaning of an Extracted Fragment in Spring REST Docs

## 1. Lesson Objectives

**Spring REST Docs** creates verifiable REST API documentation from HTTP tests executed with **MockMvc**, **WebTestClient**, or **REST Assured**. Successful tests generate snippets for requests, responses, payloads, headers, and parameters. The snippets are compiled into Asciidoctor/Markdown documentation and integrated into build and CI pipelines.

When a large payload has many nested objects, teams often split a branch into a *fragment* (subsection) to keep the overview table concise. However, a fragment with only JSON or a field table does not necessarily help readers understand what it means. This lesson focuses on how to explain **what data an extracted fragment represents, what role it plays in the endpoint's contract, and in what context it should be read**.

There are three layers of information to coordinate:

1. **Description in the parent table:** use `subsectionWithPath(...).description(...)` to explain the branch's role in the root payload.
2. **Explanation in the child document:** use headings and paragraphs before/after the snippet to present context, purpose, and business rules.
3. **Schema description of the fragment:** use `responseFields(beneathPath(...), ...)` or `requestFields(beneathPath(...), ...)` to explain each child field.

`withSubsectionId(...)` only sets the identifier/suffix for the snippet filename. It does not generate a business description on its own. The filename `response-fields-payment.adoc` tells you the snippet belongs to the payment branch, but does not explain whether payment is a payment processing result, a payment request, or a reconciliation record.

After this lesson, you will be able to describe a fragment consistently across overview and detail pages, generate dedicated body/field-table snippets, explain each field in its business context, and maintain strict validation for critical schemas.

## 2. Example: Payment Fragment in an Order Response

Suppose the `GET /orders/ord-520` endpoint returns the response:

```json
{
  "id": "ord-520",
  "status": "PAID",
  "customer": {
    "id": "cus-27",
    "displayName": "Minh Tran"
  },
  "payment": {
    "method": "CARD",
    "status": "CAPTURED",
    "amount": {
      "value": 450000,
      "currency": "VND"
    },
    "card": {
      "brand": "VISA",
      "last4": "4242"
    },
    "capturedAt": "2026-10-20T08:30:00Z",
    "transactionReference": "txn-demo-520"
  },
  "delivery": {
    "state": "PROCESSING",
    "recipient": "Minh Tran"
  }
}
```

The `payment` branch represents **the payment processing outcome associated with the order**, including method, transaction status, amount, masked card details, capture timestamp, and transaction reference code.

```text
GET /orders/{id}
├── id
├── status
├── customer
├── payment  ───────────────┐
└── delivery                │
                            ▼
                 Fragment "payment"
                 ├── method
                 ├── status
                 ├── amount
                 ├── card
                 ├── capturedAt
                 └── transactionReference
```

The documentation needs to preserve both **the position of `payment` in the root response** and **the business meaning of `payment`**. With only JSON, readers see the structure without necessarily knowing how to interpret the status and amount.

## 3. First Layer: Describing Meaning in the Parent Table

In the endpoint overview documentation, use `subsectionWithPath("payment")` with a meaningful description:

```java
responseFields(
    fieldWithPath("id")
        .description("Order identifier"),
    fieldWithPath("status")
        .description("Overall status of the order"),
    subsectionWithPath("customer")
        .description("Identifier and display name of the order's customer"),
    subsectionWithPath("payment")
        .description("Order payment processing outcome, including method, transaction status, amount, and transaction reference"),
    subsectionWithPath("delivery")
        .description("Delivery fulfillment status and recipient")
)
```

The description should answer the question: **what role does this data group play in the endpoint's contract?** Do not merely repeat the object name.

| Weak Description | Meaningful Description |
| --- | --- |
| `Payment info` | Payment processing outcome associated with the order, including method, status, and transaction details |
| `Delivery info` | Delivery fulfillment status and recipient information |
| `Customer info` | Identifier and display name of the customer who placed the order |
| `Amount details` | Processed monetary value along with its corresponding currency code |

`subsectionWithPath(...)` is a field descriptor. Its description appears in the root payload's field table; it does not create a separate detailed table or body snippet.

## 4. Second Layer: Explaining the Fragment in the Child Document

When extracting `payment` with `beneathPath("payment")`, REST Docs can generate a separate body snippet and field table. However, the snippet content itself does not know that `payment` is a payment processing result, nor does it explain what capture or a reference code means.

The child page should include author-written headings and prose:

```asciidoc
== Payment Processing Outcome

The payment fragment describes the processing outcome of the payment associated with the order.
The status field reflects the state of the payment transaction; amount is the
processed monetary value and currency specifies the currency unit. The card branch
displays only the brand and the last four digits to identify the card method.

=== JSON Example

include::{snippets}/orders-get/response-body-payment.adoc[]

=== Payment Fragment Fields

include::{snippets}/orders-get/response-fields-payment.adoc[]
```

The three parts serve different roles:

- The prose paragraph provides business context.
- The JSON shows a concrete example of the returned data.
- The field table explains the schema and each property.

If you embed only the field table, readers may see that `payment` has `status` and `amount` without understanding whether that is the payment status or the order status. The heading and explanatory paragraph bridge this gap.

### 4.1. Explain Accurately, Avoid Guessing

Field names do not always express the full contract. In the example:

- `amount.value` is the transaction's monetary value.
- `amount.currency` is the currency code for that value.
- `card.last4` is the exposed last four digits to identify the card.
- `transactionReference` is the transaction reference ID.
- `capturedAt` is the timestamp when the transaction was captured per the contract.

If the system has specific rules about currency units, timezones, reference generation sources, or capture lifecycle, describe only what is established in the contract. Do not infer business rules solely from field names.

## 5. Complete Example: MockMvc Generating Snippets for the Fragment

The example uses **JUnit 5**, **Java 17+**, Spring MVC Test, MockMvc, and Spring REST Docs. The sample controller returns fixed JSON to focus on snippet generation. A real project should use the application controller and deterministic test fixtures.

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
class PaymentFragmentDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SamplePaymentController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentPaymentMeaningAndFields() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-520")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.payment.status").value("CAPTURED"))
                .andExpect(jsonPath("$.payment.amount.currency").value("VND"))
                .andExpect(jsonPath("$.payment.card.last4").value("4242"))
                .andDo(document("orders-get",
                        // Parent table: explains the role of each branch.
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                subsectionWithPath("customer")
                                        .description("Customer identifier and display name"),
                                subsectionWithPath("payment")
                                        .description("Payment processing outcome including method, status, amount, and transaction reference"),
                                subsectionWithPath("delivery")
                                        .description("Delivery status and recipient")
                        ),
                        // Dedicated detailed field table for payment.
                        responseFields(
                                beneathPath("payment").withSubsectionId("payment"),
                                fieldWithPath("method")
                                        .description("Payment method"),
                                fieldWithPath("status")
                                        .description("Payment transaction status"),
                                fieldWithPath("amount.value")
                                        .description("Processed monetary value"),
                                fieldWithPath("amount.currency")
                                        .description("Currency code"),
                                fieldWithPath("card.brand")
                                        .description("Card brand"),
                                fieldWithPath("card.last4")
                                        .description("Last four digits of the card"),
                                fieldWithPath("capturedAt")
                                        .description("Timestamp when the transaction was captured"),
                                fieldWithPath("transactionReference")
                                        .description("Transaction reference code")
                        ),
                        // Dedicated body snippet for payment.
                        responseBody(
                                beneathPath("payment").withSubsectionId("payment")
                        )
                ));
    }

    @RestController
    public static class SamplePaymentController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> getOrder(@PathVariable("id") String id) {
            if (!"ord-520".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-520",
                      "status": "PAID",
                      "customer": {
                        "id": "cus-27",
                        "displayName": "Minh Tran"
                      },
                      "payment": {
                        "method": "CARD",
                        "status": "CAPTURED",
                        "amount": {
                          "value": 450000,
                          "currency": "VND"
                        },
                        "card": {
                          "brand": "VISA",
                          "last4": "4242"
                        },
                        "capturedAt": "2026-10-20T08:30:00Z",
                        "transactionReference": "txn-demo-520"
                      },
                      "delivery": {
                        "state": "PROCESSING",
                        "recipient": "Minh Tran"
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

### 5.1. Role of Each Handler

**Parent table:** `subsectionWithPath("payment").description(...)` explains what `payment` means in the overall response. This table describes the branch as a business unit.

**Detailed table:** `responseFields(beneathPath("payment"), ...)` extracts the branch to produce a separate table. Paths are relative to the fragment, so write `amount.value` instead of `payment.amount.value`.

**Dedicated body:** `responseBody(beneathPath("payment"))` generates a JSON snippet of the branch. A body snippet does not replace listing fields or validating the schema.

### 5.2. withSubsectionId Is a Name, Not a Description

In the example, `withSubsectionId("payment")` sets the snippet filename suffix:

- `response-fields-payment.adoc`
- `response-body-payment.adoc`

This ID only assists with identification and referencing. Changing it to `payment-result` changes the filenames, but does not automatically change the table descriptions or business explanation content. To help readers understand the fragment, write `description(...)` and surrounding prose around the snippet.

### 5.3. Each Snippet Has Its Own Verification

The parent table covers the `payment` branch; that table may still pass when a new child field appears. The strict detailed table has its own descriptors, so it can catch new undocumented fields.

For example, adding `payment.providerCode`:

- The overview table can still remain valid because `payment` is documented as a subsection.
- The detailed table can fail because `providerCode` lacks a descriptor.
- If the new field belongs to the contract, add a descriptor, explain its meaning, and update the child document.

This is the difference between **describing the meaning of a data group** and **documenting the schema of that data group**.

## 6. Tailoring Content to the Reader

A fragment may be read by API integrators, operators, reconciliation teams, or frontend developers. Avoid stuffing all context into individual field descriptions.

| Reader | Question to Answer | Where to Explain |
| --- | --- | --- |
| Endpoint page reader | What data group is `payment` in the response? | `subsectionWithPath("payment")` description in the parent table |
| API integrator | Which fields exist and what does each field mean? | `responseFields(beneathPath("payment"), ...)` table |
| Someone needing a payload example | What does the actual fragment structure look like? | `responseBody(beneathPath("payment"))` and prose |
| Someone needing business rules | How do statuses transition, and how are amounts interpreted? | Linked contract or business lifecycle documentation |
| Someone navigating content | Which section or page holds the fragment? | Headings, table of contents, anchors, and links |

### 6.1. Authoring Template for a Fragment

A fragment page can follow this structure:

1. **Fragment title:** a clear business name, e.g., "Payment Processing Outcome".
2. **Role:** what information the fragment represents in the request/response.
3. **Location:** the fragment's path in the root payload.
4. **JSON example:** extracted body snippet.
5. **Schema:** field table with descriptions.
6. **Rules or constraints:** units, statuses, optionality, masked data, or presence conditions if defined by the contract.
7. **References:** links to payment status documentation, errors, or separately managed business rules.

Example introductory paragraph:

> The payment fragment describes the payment processing outcome associated with the order. It includes the payment method, transaction status, amount, masked card information, capture timestamp, and reference code. Transaction status transition rules are covered in the payment lifecycle documentation.

Only state rules confirmed by the contract or actual logic; do not deduce that a status or timestamp has a specific meaning solely from a field name.

## 7. Applying to Request Fragments

The same method applies to a `POST /orders` request:

```json
{
  "customerId": "cus-27",
  "delivery": {
    "recipient": "Minh Tran",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    },
    "instructions": "Call upon arrival"
  },
  "items": [
    {
      "sku": "BK-101",
      "quantity": 1
    }
  ]
}
```

The parent-level request table can be:

```java
requestFields(
    fieldWithPath("customerId")
        .description("ID of the customer placing the order"),
    subsectionWithPath("delivery")
        .description("Delivery fulfillment details including recipient, address, and delivery instructions"),
    subsectionWithPath("items")
        .description("List of ordered products")
)
```

Dedicated table for the `delivery` fragment:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Recipient name"),
    fieldWithPath("address.city")
        .description("Delivery city"),
    fieldWithPath("address.country")
        .description("Country code"),
    fieldWithPath("instructions")
        .optional()
        .description("Additional instructions for the courier")
)
```

The detail page should clearly state that `delivery` is used to organize order fulfillment, while the field table shows the data structure. `instructions` is marked optional per the example's assumption; keep this marking only when the contract actually allows omitting the field.

With MockMvc, send JSON via `.contentType(MediaType.APPLICATION_JSON).content(requestJson)` before calling `.andDo(document(...))`. With WebTestClient, attach `document` after `exchange`; with REST Assured, attach the document filter to the configured request specification.

## 8. Combining Snippets and Prose in Asciidoctor

With the identifier `orders-get` and subsection ID `payment`, a page can be authored as follows:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Query information and status of an order.

=== HTTP Response

include::{snippets}/orders-get/http-response.adoc[]

=== Data Groups

include::{snippets}/orders-get/response-fields.adoc[]

=== Payment Processing Outcome

The payment fragment describes the processing outcome of the payment associated with the order.
The status field belongs to the payment transaction; amount contains the processed
monetary value and currency specifies the currency unit.

==== JSON Example

include::{snippets}/orders-get/response-body-payment.adoc[]

==== Fields

include::{snippets}/orders-get/response-fields-payment.adoc[]
```

Explanatory paragraphs are authored inside the Asciidoctor file. `response-body-payment.adoc` contains only the extracted JSON fragment; `response-fields-payment.adoc` contains the declared field table. Snippets do not automatically supply business descriptions in prose.

If the fragment is managed in a separate document, place the heading/explanatory paragraph on that page and link from the endpoint page using anchors or the publishing system's `xref` mechanism. Verify that link targets are actually generated in the output documentation.

## 9. Generating Snippets with WebTestClient and REST Assured

Descriptors in `PayloadDocumentation` follow the same principles across testing tools; only where `document(...)` is attached differs.

### WebTestClient

Assuming `webTestClient` is already configured with Spring REST Docs and `document` is statically imported from `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-520")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-payment",
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Order status"),
            subsectionWithPath("payment")
                .description("Order payment processing outcome"),
            subsectionWithPath("customer")
                .description("Customer information"),
            subsectionWithPath("delivery")
                .description("Delivery information")
        ),
        responseFields(
            beneathPath("payment").withSubsectionId("payment"),
            fieldWithPath("method").description("Payment method"),
            fieldWithPath("status").description("Transaction status"),
            fieldWithPath("amount.value").description("Monetary value"),
            fieldWithPath("amount.currency").description("Currency code"),
            fieldWithPath("card.brand").description("Card brand"),
            fieldWithPath("card.last4").description("Last four digits of card"),
            fieldWithPath("capturedAt").description("Capture timestamp"),
            fieldWithPath("transactionReference").description("Reference code")
        ),
        responseBody(beneathPath("payment").withSubsectionId("payment"))
    ));
```

### REST Assured

Assuming `spec` is a `RequestSpecification` with a REST Docs filter and `document` is statically imported from `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-payment-restassured",
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Order status"),
            subsectionWithPath("payment")
                .description("Order payment processing outcome"),
            subsectionWithPath("customer")
                .description("Customer information"),
            subsectionWithPath("delivery")
                .description("Delivery information")
        )
    ))
    .when()
    .get("/orders/ord-520")
    .then()
    .statusCode(200);
```

These snippets illustrate documentation handlers; they assume client, server, and filter are already configured. A fragment body can be added with `responseBody(beneathPath("payment"))` when the page needs a dedicated JSON example.

## 10. Strict, optional, and Scope Meaning

### 10.1. Each Snippet Has Its Own Validation Boundary

| Response Change | Parent Table with `subsectionWithPath("payment")` | Strict `payment` Detailed Table |
| --- | --- | --- |
| Add `payment.providerCode` | May still pass | Fails if missing a descriptor |
| Add `createdAt` at root | Fails if missing a descriptor | Outside the `payment` scope |
| Remove `payment.status` | May still pass if `payment` still exists | Fails if `status` is required |
| Remove `payment.card.last4` | May still pass | Fails if descriptor is required |
| Remove `payment` completely | Fails if subsection is required | No data available to extract as expected |

The parent table describes `payment` as a block. The detailed table describes child fields. Therefore, you cannot conclude that the fragment schema is fully verified solely because the parent table passes.

### 10.2. optional()

If a field can be absent per the contract:

```java
fieldWithPath("transactionReference")
    .optional()
    .description("Reference code if the transaction has been created")
```

If an entire subsection can be absent:

```java
subsectionWithPath("payment")
    .optional()
    .description("Payment information if the order has initiated a transaction")
```

`optional()` allows the described field to be absent in the test case. However, `beneathPath("payment")` needs the branch to have data to generate the snippet. Thus, use a test with `payment` to generate detailed documentation and a separate test for the variant without `payment`.

### 10.3. ignored() and relaxedResponseFields()

`ignored()` is intended for a known field intentionally excluded from the table. Do not use it to hide an unexplained public field.

`relaxedResponseFields(...)` accepts undocumented fields; consequently, schema changes outside declared descriptors may go undetected. When you need to split a payload into fragments with clear meanings, a strict parent table with subsection descriptors and strict child tables usually indicate the documented scope more accurately.

## 11. Naming Fragments and Snippets

JSON path names and business headings do not have to be identical. For example:

| Path | Reader-Facing Heading | Subsection ID |
| --- | --- | --- |
| `payment` | Payment Processing Outcome | `payment` |
| `delivery` | Delivery Information | `delivery` |
| `customer` | Customer Information | `customer` |
| `items` | Line Items | `items` |

Several guidelines:

- IDs should be short, stable, and independent of long sentences.
- Headings should express business concepts and can be translated into the documentation's language.
- When changing a subsection ID, update the corresponding `include` paths.
- Do not treat a subsection ID as a status, API version, or access permission.
- The branch summary goes in `description(...)`; full explanation goes on the page; field descriptions go in the detailed table.

## 12. Integrating into Build and CI

For a Gradle Groovy DSL project already configured with the Asciidoctor plugin and Spring REST Docs dependencies:

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

In CI, ensure:

1. Tests run and generate snippets before Asciidoctor compiles documentation.
2. Parent and fragment tables use the same fixture when describing the same response.
3. Include paths match the exact identifier and subsection ID.
4. Headings/explanatory paragraphs are stored with the documentation rather than expecting auto-generated snippets to supply context.
5. Fixtures do not contain real payment data or sensitive information.

If publishing Markdown, use templates and Markdown assembly steps appropriate instead of `include::[]` syntax. With Maven, the snippet directory is typically `target/generated-snippets`; the key requirement is that tests must run before the documentation build step.

## 13. Common Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Child page only displays JSON, purpose is unclear | Only included `response-body-payment.adoc` | Add headings and prose explaining the fragment's meaning |
| Filename has `payment` yet readers don't understand what `payment` is | Confused subsection ID with business description | Write `description(...)` in the parent table and prose on the child page |
| Parent table passes even though `payment` has a new field | `subsectionWithPath("payment")` covers descendants in the overview snippet | Maintain a separate strict table using `beneathPath("payment")` |
| Detailed table cannot find `payment.amount.value` | Used root path after extracting `payment` | Use `amount.value` |
| `response-fields-payment.adoc` is not generated | Did not use `responseFields(beneathPath(...))` or ID differs | Check handler and subsection ID |
| Explanation contradicts the API | Written by guessing from field names | Cross-check against the contract and actual logic |
| Link to child page does not work | Anchor/xref does not exist in output | Check heading ID, include, and link |
| Snippet contains sensitive data | Fixture contains real data | Use dummy data and publish only masked portions |
| Documentation stays stale despite fresh test run | Asciidoctor read old snippets or ran before tests | Clean output and configure task dependencies |

## 14. Practice Exercise

Extend `PaymentFragmentDocumentationTest`:

1. **Parent table description:** rewrite the description of `payment` to clearly state the payment's role in the order response. Check whether the description distinguishes it from the order's `status`.
2. **Create a child page:** write a "Payment Processing Outcome" heading, explain `method`, `status`, `amount`, and `transactionReference`. Include `response-body-payment.adoc` and `response-fields-payment.adoc`.
3. **Change the subsection ID:** change `withSubsectionId("payment")` to `withSubsectionId("payment-result")` and update the include names. Confirm the ID only renames the snippets.
4. **Test schema changes:** add `payment.providerCode`. Verify the parent table can still pass while the strict detailed table catches the new field; add a descriptor and explanation.
5. **Test optionality:** remove `transactionReference` from the response and mark `optional()` per the contract; then remove `optional()` to observe the difference.
6. **Test context:** temporarily remove the heading and explanatory paragraph from the child page. Re-add the content and list the questions readers cannot answer when only JSON and a field table remain.
7. **Build compilation:** run `./gradlew clean test asciidoctor` in a configured project; intentionally break an include path to confirm the pipeline detects a missing snippet.

**Completion criteria:** you can explain a fragment's meaning in both the parent table and child page, distinguish a subsection ID from a business description, generate dedicated body/field-table snippets, and use strict tests to protect key schemas.

## 15. Self-Check Questions

**1. What does `subsectionWithPath("payment").description(...)` solve?**

It explains the role of the `payment` branch in the root payload's field table and covers descendant fields in the parent snippet. It does not generate a body or detailed field table.

**2. Does `withSubsectionId("payment")` display a description of `payment`?**

No. It sets the snippet filename identifier/suffix. The fragment's meaning must be explained in `description(...)` or in the child page's heading and prose.

**3. Which API should you use to create a dedicated schema table for `payment`?**

Use `responseFields(beneathPath("payment").withSubsectionId("payment"), ...)` with field paths relative to the fragment. For requests, use `requestFields(...)` accordingly.

**4. Why does the parent table pass while the `payment` table fails?**

The parent table already covers the entire `payment` branch. The `payment` table has its own descriptors and is strict within the extracted scope, so it can catch new undocumented child fields.

**5. Is embedding only the fragment body sufficient to verify the schema?**

No. `responseBody(...)` creates a JSON example. `responseFields(...)` describes and checks fields; business assertions are still needed to verify values and rules.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors, subsection descriptors, extraction, optional fields, and relaxed documentation.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): setting up MockMvc, WebTestClient, REST Assured, snippet generation, and Asciidoctor/build integration.
