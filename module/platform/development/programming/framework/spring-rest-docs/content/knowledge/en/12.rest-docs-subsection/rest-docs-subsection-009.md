# Avoiding Missing Documentation When a Subsection Changes Structure in Spring REST Docs

## 1. The Problem: An Overview Table Can Stay Green When a Child Schema Changes

**Spring REST Docs** creates verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. When a test runs successfully, the library generates snippets describing requests, responses, payloads, headers, and parameters. The snippets are compiled into Asciidoctor/Markdown documentation and integrated into the build and CI pipeline.

When a payload has large objects or nested arrays, `subsectionWithPath(...)` keeps the overview field table concise. However, there is an important risk: a subsection descriptor treats **descendant fields of that branch as already documented in the current snippet**. If a new field appears inside the branch, the overview table may still pass even though the documentation has not yet explained the new field.

For example, a response table declares only:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    subsectionWithPath("payment")
        .description("Payment processing outcome")
)
```

If the response adds `payment.providerCode` or `payment.refundState`, the overview table may still be valid because the entire `payment` branch is covered. API integrators might not realize the contract just changed.

This lesson shows how to avoid missing documentation when a subsection changes by:

- distinguishing the parent table from detailed schema tables;
- creating strict snippets for critical subsections;
- verifying JSON types, paths, and business rules with separate assertions;
- organizing tests for optional fields, absent branches, empty arrays, and variant structures;
- using CI to enforce updating documentation alongside API changes.

## 2. Understanding the Exact Validation Boundary of a Subsection

Suppose `GET /orders/ord-650` returns the response:

```json
{
  "id": "ord-650",
  "status": "PAID",
  "payment": {
    "method": "CARD",
    "state": "CAPTURED",
    "amount": {
      "value": 820000,
      "currency": "VND"
    },
    "card": {
      "brand": "VISA",
      "last4": "4242"
    }
  },
  "delivery": {
    "recipient": "Mai Le",
    "address": {
      "city": "Can Tho",
      "country": "VN"
    }
  }
}
```

An overview table can be declared as:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    subsectionWithPath("payment")
        .description("Payment processing outcome"),
    subsectionWithPath("delivery")
        .description("Delivery information")
)
```

The table has four rows. It validates the described root-level fields, including the presence of required branches. However, it does not require listing every descendant such as `payment.method`, `payment.amount.value`, or `payment.card.last4`.

Distinguish them as follows:

| Descriptor | Described Boundary | Changes That May Go Undetected by This Snippet |
| --- | --- | --- |
| `fieldWithPath("id")` | One specific field | New fields at other paths still require descriptors |
| `subsectionWithPath("payment")` | The entire `payment` branch and its descendants | New child fields inside `payment` |
| `subsectionWithPath("delivery.address")` | The `address` branch inside `delivery` | New fields beneath `delivery.address` |
| `responseFields(beneathPath("payment"), ...)` | Fields declared in the detailed `payment` snippet | New child fields within `payment` if no matching descriptor exists |
| `responseBody(beneathPath("payment"))` | Body extracted from `payment` | A body snippet itself does not check schema completeness |

A passing test only proves that the descriptors in **that snippet** match the payload under REST Docs rules. It does not prove that every child branch has been documented elsewhere.

## 3. Two-Layer Strategy: Overview and Detailed Schema

For important subsections, there should be two tables serving two purposes:

**The overview table** tells readers which data groups the response contains and what each group means. `subsectionWithPath` fits well here.

**The strict detailed table** lists fields inside the subsection to catch schema changes. Use `responseFields(beneathPath(...), ...)` with detailed descriptors.

Example `payment` table:

```java
responseFields(
    beneathPath("payment").withSubsectionId("payment"),
    fieldWithPath("method")
        .description("Payment method"),
    fieldWithPath("state")
        .description("Payment transaction state"),
    fieldWithPath("amount.value")
        .description("Monetary amount value"),
    fieldWithPath("amount.currency")
        .description("Currency code"),
    fieldWithPath("card.brand")
        .description("Card brand"),
    fieldWithPath("card.last4")
        .description("Last four digits of the card")
)
```

Paths are relative to the root of the extracted subsection. In the `payment` table, use `amount.value` instead of `payment.amount.value`. This table is strict within the `payment` scope: if the response adds `payment.providerCode` without a descriptor, the test can fail and require a documentation update.

If a child field is itself a large object needing separate management, you can use a subsection at a deeper level or create a separate table for that branch. Choose boundaries so there are no unguarded gaps between the overview table and the detailed tables that the contract needs to protect.

### 3.1. Every Important Branch Should Have Clear Ownership

Not every object needs a detailed table. A small, stable, or internal branch can be explained at the overview level. However, branches affecting integration, money, authentication, authorization, processing states, or user data usually need detailed verification.

Illustrative ownership matrix:

| Branch | Documentation to Maintain | Reason |
| --- | --- | --- |
| `payment` | Strict detailed table | Field changes can affect reconciliation or payment state |
| `delivery` | Strict detailed table | Integrators need to know recipient and address |
| `metadata` (internal) | May use only an overview subsection | Not every internal key belongs to the public contract |
| `items[]` | Field table for each element | Clients need SKU, quantity, and price |
| `audit` | Depends on public scope | May need separate documentation if the endpoint exposes audit data |

This is a documentation design decision based on the contract; not every subsection needs a detailed snippet just to increase the file count.

## 4. MockMvc Example: Overview Test and Detailed Test

The example uses JUnit 5, Java 17+, Spring MVC Test, and Spring REST Docs. The sample controller returns fixed JSON to demonstrate snippet generation; in a real project, replace it with your application's controller and fixtures.

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
class OrderSubsectionContractTest {

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
        mockMvc.perform(get("/orders/{id}", "ord-650")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ord-650"))
                .andExpect(jsonPath("$.payment").isMap())
                .andDo(document("orders-get-overview",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                subsectionWithPath("payment")
                                        .description("Payment processing outcome"),
                                subsectionWithPath("delivery")
                                        .description("Delivery information")
                        )
                ));
    }

    @Test
    void documentPaymentContract() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-650")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.payment.method").value("CARD"))
                .andExpect(jsonPath("$.payment.amount.value").isNumber())
                .andExpect(jsonPath("$.payment.card.last4").value("4242"))
                .andDo(document("orders-get-payment",
                        responseFields(
                                beneathPath("payment")
                                        .withSubsectionId("payment"),
                                fieldWithPath("method")
                                        .description("Payment method"),
                                fieldWithPath("state")
                                        .description("Transaction state"),
                                fieldWithPath("amount.value")
                                        .description("Monetary amount value"),
                                fieldWithPath("amount.currency")
                                        .description("Currency code"),
                                fieldWithPath("card.brand")
                                        .description("Card brand"),
                                fieldWithPath("card.last4")
                                        .description("Last four digits of the card")
                        ),
                        responseBody(
                                beneathPath("payment")
                                        .withSubsectionId("payment")
                        )
                ));
    }

    @RestController
    static class SampleOrderController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        ResponseEntity<String> getOrder(@PathVariable("id") String id) {
            if (!"ord-650".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-650",
                      "status": "PAID",
                      "payment": {
                        "method": "CARD",
                        "state": "CAPTURED",
                        "amount": {
                          "value": 820000,
                          "currency": "VND"
                        },
                        "card": {
                          "brand": "VISA",
                          "last4": "4242"
                        }
                      },
                      "delivery": {
                        "recipient": "Mai Le",
                        "address": {
                          "city": "Can Tho",
                          "country": "VN"
                        }
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

The two tests have two distinct identifiers because they generate independent snippet sets:

- `orders-get-overview`: overview table and subsections.
- `orders-get-payment`: detailed schema table and body for `payment`.

In a project, you can use the same identifier if you have designed a single test/document operation with non-colliding handlers and snippet names. The example above separates identifiers to clarify test boundaries; avoid letting two unrelated tests write to the same snippet filename.

## 5. Testing Schema Drift: Adding a New Field Inside a Subsection

Suppose the API adds:

```json
{
  "payment": {
    "providerCode": "BANK-X"
  }
}
```

If you run only the overview test `orders-get-overview` with `subsectionWithPath("payment")`, the new child field might not cause that snippet to fail. That is the exact gap that needs to be controlled.

When running the detailed test `orders-get-payment`, the strict table only declares `method`, `state`, `amount.value`, `amount.currency`, `card.brand`, and `card.last4`. Because `providerCode` appears under `payment` without being described, the detailed test can fail and force the team to update the contract.

Workflow for handling the change:

1. Determine whether the new field belongs to the public API contract or is purely an internal detail.
2. If public, add a `fieldWithPath("providerCode")` descriptor to the `payment` table with a clear description.
3. Update related payload examples or business documentation.
4. If needed, add assertions for the field's format/value; descriptors only verify documentation structure and do not replace business testing.
5. Re-run tests and build the documentation so snippets stay updated alongside the change.

If the new field does not belong to the public contract, make an explicit handling decision; you can use `ignored()` for a known field intentionally excluded from the table. Do not use `ignored()` as a shortcut to avoid updating documentation.

## 6. Do Not Rely Only on Field Documentation to Check Types and Values

Field documentation verifies paths and field descriptions. It does not replace every required assertion about runtime schemas and business logic.

For example, `fieldWithPath("amount.value")` does not automatically guarantee the unit is Vietnamese Dong, does not confirm the amount is positive, and does not prove the total is calculated correctly. Combine it with:

```java
.andExpect(jsonPath("$.payment.amount.value").isNumber())
.andExpect(jsonPath("$.payment.amount.currency").value("VND"))
.andExpect(jsonPath("$.payment.card.last4").value(org.hamcrest.Matchers.matchesPattern("\\d{4}")))
```

These assertions check important types/values for the specific fixture. If you need to check conditions such as positive amounts, use appropriate matchers or deserialize the response into an object and assert business rules. Do not make the documentation describe a contract stricter than what the API actually enforces.

### 6.1. Verify Objects Remain Objects

A response that changes `payment` from an object to a string or array is not equivalent to the previous contract. You can use a JSON assertion to verify `payment` is an object while using the field table to verify specific paths.

### 6.2. Verify Arrays and Elements

For an `items` subsection that is an array of objects, detailed documentation can use `items[].sku` and `items[].quantity`. However, separate assertions are needed for:

- element count if specified by the API;
- each item having a valid SKU;
- quantity satisfying its valid range;
- nested fields like `pricing` having the right type and unit;
- element order if order is part of the contract.

`subsectionWithPath("items")` does not verify any of those conditions.

## 7. Avoiding Gaps When a Subsection Has Optional or Variant Structures

### 7.1. Optional Fields Inside a Subsection

If `payment.transactionReference` appears only after a transaction is created, declare:

```java
fieldWithPath("transactionReference")
    .optional()
    .description("Reference code once the transaction has been created")
```

`optional()` allows the field to be absent in the test case; it does not mean the field can have any arbitrary type or content.

You should have tests for both states—with a reference code and without a reference code—if both are valid states in the contract. The documentation snippet should clearly indicate that the field may be absent.

### 7.2. When the Entire Subsection Can Be Absent

If `payment` does not exist for unpaid orders, the parent descriptor can use:

```java
subsectionWithPath("payment")
    .optional()
    .description("Payment information if the order has initiated a transaction")
```

The detailed test using `beneathPath("payment")` requires a payload that actually contains `payment` in order to extract and document it. Do not use this extractor in a test for a response variant lacking the branch. Instead:

- test with `payment`: generate the body snippet and detailed table;
- test without `payment`: verify the response against the contract without invoking the extractor for the absent branch.

### 7.3. Empty Arrays

`"items": []` is different from omitting the `items` key. If a detailed table describes `items[].sku` and `items[].quantity`, an empty-array fixture has no elements to match those fields against. Use a test with at least one item to generate the schema snippet and a separate test verifying an empty array if the API allows it.

### 7.4. Union or Multi-Variant Structures

A subsection can change shape depending on transaction type. For instance, `payment.method` as `CARD` has `card.last4`, while `BANK_TRANSFER` has `bankReference`. Avoid merging two different structures into a single field table that assumes every path is always present.

You can organize this by having:

- an overview table for `payment`;
- detailed tables for each variant or discriminator;
- tests with data for each variant;
- `optional()` descriptors only when a field is genuinely optional in the shared contract.

If the API defines an explicit discriminator, the documentation must explain how readers select the matching table/shape.

## 8. Applying to Request Subsections

The risk of missing descriptions also appears in requests. Suppose `POST /orders` accepts:

```json
{
  "customerId": "cus-25",
  "delivery": {
    "recipient": "Mai Le",
    "address": {
      "city": "Can Tho",
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

Overview request table:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Customer ID"),
    subsectionWithPath("delivery")
        .description("Information for order fulfillment"),
    subsectionWithPath("items")
        .description("Line items in the order")
)
```

Detailed request table for `delivery`:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Recipient"),
    fieldWithPath("address.city")
        .description("Delivery city"),
    fieldWithPath("address.country")
        .description("Country code"),
    fieldWithPath("instructions")
        .optional()
        .description("Additional instructions for delivery")
)
```

The overview table does not catch every new field inside `delivery`. The strict detailed table will catch undocumented new fields. For requests, also test business validation such as customer existence, valid SKU, positive quantity, and required address.

## 9. Snippet Names and Documentation Authoring

Assuming the operation identifier `orders-get-payment` and subsection ID `payment`, the key snippets live under `build/generated-snippets/orders-get-payment/`:

| File | Content |
| --- | --- |
| `response-fields-payment.adoc` | Verified `payment` field table |
| `response-body-payment.adoc` | Extracted `payment` body |
| `http-response.adoc` | Full HTTP response if the test generates default snippets |

An Asciidoctor page can include:

```asciidoc
== GET /orders/{id}

=== Overview Response

include::{snippets}/orders-get-overview/response-fields.adoc[]

=== Payment Contract

payment is the payment processing outcome associated with the order.
The fields and JSON example are extracted from the same test case response.

include::{snippets}/orders-get-payment/response-body-payment.adoc[]
include::{snippets}/orders-get-payment/response-fields-payment.adoc[]
```

The prose "payment is the payment processing outcome..." is written manually to explain meaning. Snippets supply only data and descriptor tables.

If the documentation uses multiple pages, move the details into a Payment page and link from the Order page using your publishing system's anchor/`xref`. The build must compile both the main page and the detail page to catch missing snippets/`include` directives.

## 10. Integrating Gradle and CI to Catch Missing Documentation

For a project already configured with the Asciidoctor plugin and Spring REST Docs dependencies, you can wire the build as follows (Groovy DSL):

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

1. Both overview tests and detailed subsection tests run.
2. Asciidoctor runs after the tests that generate snippets.
3. `include` directives use the exact operation identifier and subsection ID.
4. Stale snippets from an earlier build are never used to document a new API.
5. When a strict table fails, whoever changed the schema must update the descriptors, prose, and related examples.

With Maven, the snippet directory is usually `target/generated-snippets`; configure plugins so the documentation build step depends on tests. If using Markdown, pick templates and Markdown assembly steps suited to your project pipeline.

### 10.1. What CI Can and Cannot Check

| Check | Can REST Docs/Build Support It? | What Needs to Be Added |
| --- | --- | --- |
| New field outside documented subsections | Yes, parent strict table | Add descriptor |
| New field inside a subsection covered by the parent table | Only when a strict detailed snippet exists | Detailed table for the subsection |
| Required JSON path missing | Yes, non-optional descriptor | Review contract/optionality |
| Monetary amount calculated correctly | Not from field descriptors alone | Business assertions |
| Link to child page exists | Documentation build can catch missing `include` files | Check `xref`/anchors if the pipeline does not validate them |
| Business meaning in Description is accurate | Cannot verify automatically | Content/QA review |
| Examples contain no sensitive data | Not guaranteed automatically | Dummy fixtures and data checks |

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Added a child field yet test still passes | Only `subsectionWithPath` exists in the parent table | Create a strict table using `beneathPath` |
| Detailed table reports an undocumented field | Payload has a new field or descriptors are incomplete | Determine whether the field belongs to the contract; add a descriptor or handle explicitly |
| Detailed table reports a missing required field | Field is absent or path is wrong | Check against response and use `optional()` only if allowed by contract |
| Cannot extract subsection | Branch is absent from fixture or path is wrong | Generate snippet from a test containing the branch; test absent variants separately |
| Body snippet exists but no field table | Only called `responseBody(...)` | Add `responseFields(...)` to document the schema |
| Assertions pass yet schema docs miss fields | Assertions check only a few values | Add strict descriptors for the entire scope to protect |
| Strict table passes even though a new known non-public field exists | Descriptor intentionally uses `ignored()` | Record the decision and rationale in docs/review |
| New field skipped due to relaxed mode | `relaxedResponseFields` does not check undescribed fields | Use strict mode when catching schema drift is needed |
| CI docs differ from local results | Non-deterministic test data or stale snippets | Use fixed fixtures, clean outputs, and verify task dependencies |

## 12. Practice Exercise

Use `OrderSubsectionContractTest` in Section 4 and perform:

1. **Change a field inside `payment`:** add `providerCode` to the controller JSON. Verify the overview test can still pass while the strict detailed test catches the new field.
2. **Update the contract:** add the `fieldWithPath("providerCode")` descriptor to the `payment` table, describe its meaning, and re-run.
3. **Change a type:** change `payment.amount.value` from a number to a string. Write an assertion checking numeric type and observe the test catching the change.
4. **Optional field:** remove `payment.transactionReference` from the response fixture. Add an `optional()` descriptor if the contract allows it; try removing `optional()` to compare.
5. **Absent subsection:** create a response where `payment` has not been initiated yet. Write a separate test checking the response and do not invoke the `payment` extractor in that test.
6. **Empty array:** create a response with `items: []`. Separate the empty-array test from the test generating the element schema table.
7. **CI:** run `./gradlew clean test asciidoctor` in a configured project, confirming both overview and detailed snippets are generated and included.

**Completion criteria:** you can explain why a parent table can pass when a child field changes, create strict tables for important subsections, handle optional/variant cases properly, and set up the build to catch missing documentation when the contract changes.

## 13. Self-Check Questions

**1. Why can `subsectionWithPath("payment")` hide a new field?**

Because that descriptor covers the entire `payment` branch and its descendants in the current snippet. The parent table does not list individual child fields separately.

**2. How can you catch new child fields?**

Create a strict table using `responseFields(beneathPath("payment"), ...)` and list the fields required by the contract.

**3. Does `responseBody(beneathPath("payment"))` validate the schema sufficiently?**

No. It extracts the body; strict field tables are what enforce field documentation.

**4. Should you mark every field optional so tests don't fail?**

No. `optional()` must reflect the actual contract. Overusing it strips the documentation of its ability to catch missing required fields.

**5. What if a subsection is absent?**

Use a separate test for the variant without the subsection. Detailed snippets using `beneathPath` should be generated from tests that include the branch to extract.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field/subsection descriptors, paths, optional fields, and relaxed documentation.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): test configuration, snippets, Asciidoctor, and build integration.
