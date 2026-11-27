# Documenting a Subsection of a Response Payload in Spring REST Docs

## 1. Lesson Objectives

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests run with **MockMvc**, **WebTestClient**, or **REST Assured**. Snippets are generated from the request and response of an executed test case, then included in Asciidoctor/Markdown documentation and the build/CI pipeline.

Within the **Subsection** topic group, this lesson focuses on one specific question:

> When a JSON response has multiple nested branches, how can you extract a single branch and accurately document the fields inside it?

For example, an order retrieval endpoint might return order info, total amount, items, and payment details. Overview documentation needs to present the response structure; the `payment` section specifically needs a readable JSON excerpt and field description table. Both documentation forms can be generated from **a single test execution**.

After this lesson, you will:

- Understand the role of `subsectionWithPath(...)` when documenting a response at the overview level.
- Use `beneathPath(...)` with `responseBody(...)` to generate a snippet for a single part of the response.
- Use `beneathPath(...)` with `responseFields(...)` to document each field of the selected branch using relative paths.
- Recognize the schema changes that strict tests can catch.
- Author the snippets into Asciidoctor and ensure the documentation build step depends on the test execution step.

## 2. Sample Data: Order Retrieval API Response

Suppose `GET /orders/ord-1042` returns HTTP `200 OK` with the `Content-Type: application/json` header and body:

```json
{
  "id": "ord-1042",
  "status": "PAID",
  "total": {
    "amount": 1250000,
    "currency": "VND"
  },
  "payment": {
    "method": "CARD",
    "state": "CAPTURED",
    "card": {
      "brand": "VISA",
      "last4": "4242"
    },
    "transactionId": "txn-demo-001"
  },
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
```

In this example:

- `id` and `status` are root-level information.
- `total`, `payment`, and `items` are child branches.
- The `payment` branch contains information about the payment method, state, masked card details, and transaction ID.

The `payment` branch is the **subsection** we want to present separately. REST Docs provides two complementary approaches to do this:

| Goal | Call | Meaning |
| --- | --- | --- |
| Mention `payment` as a block in the overview table | `subsectionWithPath("payment")` inside `responseFields(...)` | Documents a branch at the overview level, including its descendants for that snippet's field validation. |
| Generate only the JSON of `payment` | `responseBody(beneathPath("payment"))` | Extracts the body segment at the selected path. |
| Create a detailed table of fields belonging to `payment` | `responseFields(beneathPath("payment"), ...)` | Describes and validates fields inside the subsection; descriptor paths are relative to the root of the extracted branch. |

**Important distinction:** `subsectionWithPath` is a **descriptor** representing an entire branch, whereas `beneathPath` is an **extractor** that selects a branch to produce a body snippet or field table. `subsectionWithPath` does not automatically generate separate JSON for the branch and does not thoroughly verify child fields.

## 3. MockMvc Test Generating Three Documentation Snippets

This is a self-contained example using **JUnit 5**, **MockMvc**, **Spring MVC**, and **Spring REST Docs**. The simulated controller returns a fixed JSON response to keep focus on the snippet generation mechanism. In a real application, use your actual controller with deterministic test data.

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
class OrderResponseDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentPaymentSubsection() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "ord-1042")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.payment.state").value("CAPTURED"))
                .andDo(document("orders-get",

                        // (1) Root-level response overview.
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                subsectionWithPath("total")
                                        .description("Total amount and currency"),
                                subsectionWithPath("payment")
                                        .description("Payment information"),
                                subsectionWithPath("items")
                                        .description("Items belonging to the order")
                        ),

                        // (2) JSON portion dedicated to payment.
                        responseBody(beneathPath("payment")
                                .withSubsectionId("payment")),

                        // (3) Detailed field table inside payment.
                        responseFields(
                                beneathPath("payment")
                                        .withSubsectionId("payment"),
                                fieldWithPath("method")
                                        .description("Payment method"),
                                fieldWithPath("state")
                                        .description("Payment processing state"),
                                fieldWithPath("card.brand")
                                        .description("Card brand"),
                                fieldWithPath("card.last4")
                                        .description("Last four digits of the card"),
                                fieldWithPath("transactionId")
                                        .optional()
                                        .description("Transaction ID if already available")
                        )
                ));
    }

    @RestController
    public static class SampleOrderController {

        @GetMapping(value = "/orders/{orderId}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> getOrder(
                @PathVariable String orderId) {

            if (!"ord-1042".equals(orderId)) {
                return ResponseEntity.notFound().build();
            }

            String response = """
                    {
                      "id": "ord-1042",
                      "status": "PAID",
                      "total": {
                        "amount": 1250000,
                        "currency": "VND"
                      },
                      "payment": {
                        "method": "CARD",
                        "state": "CAPTURED",
                        "card": {
                          "brand": "VISA",
                          "last4": "4242"
                        },
                        "transactionId": "txn-demo-001"
                      },
                      "items": [
                        {
                          "sku": "BOOK-001",
                          "quantity": 2
                        }
                      ]
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(response);
        }
    }
}
```

The test requires JUnit Jupiter, Spring MVC Test, and `spring-restdocs-mockmvc` on the classpath. The example uses Java 17+ because of text blocks. When applying this to a real controller, asserting HTTP status, headers, and business data before `document(...)` remains essential so that snippets reflect a valid response.

### 3.1. Overview Response Table

The section:

```java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("status").description("Order status"),
    subsectionWithPath("total").description("Total amount and currency"),
    subsectionWithPath("payment").description("Payment information"),
    subsectionWithPath("items").description("Items belonging to the order")
)
```

generates a table describing the five root-level components. `subsectionWithPath("payment")` informs REST Docs that this branch is already described at an overview level, so fields like `payment.card.last4` do not have to appear as individual rows in the overview table. Similarly, `total.amount` and `items[].sku` sit beneath two overview-documented subsections.

This keeps the introductory table concise, but comes with a limitation: with only this table, if the API adds `payment.providerCode`, the test may **fail to detect** the new child field because the subsection descriptor covers the entire branch. To preserve fine-grained verification, the next part adds a dedicated table for `payment`.

### 3.2. Dedicated Body Snippet for the Subsection

The section:

```java
responseBody(beneathPath("payment").withSubsectionId("payment"))
```

selects the `payment` branch in the response and instructs REST Docs to generate a separate body snippet. The excerpt corresponds to the data:

```json
{
  "method": "CARD",
  "state": "CAPTURED",
  "card": {
    "brand": "VISA",
    "last4": "4242"
  },
  "transactionId": "txn-demo-001"
}
```

This is the **conceptual content of the selected branch**; the final text formatting depends on how REST Docs extracts it and the snippet template in use. The key point is that the excerpt no longer contains `id`, `status`, `total`, and `items` from the root-level response.

`withSubsectionId("payment")` sets a recognizable ID so the snippet name stays stable and convenient for Asciidoctor `include` directives.

### 3.3. Detailed Field Table and Relative Paths

When using:

```java
responseFields(
    beneathPath("payment").withSubsectionId("payment"),
    fieldWithPath("method").description("Payment method"),
    fieldWithPath("state").description("Payment processing state"),
    fieldWithPath("card.brand").description("Card brand"),
    fieldWithPath("card.last4").description("Last four digits of the card"),
    fieldWithPath("transactionId").optional()
        .description("Transaction ID if already available")
)
```

REST Docs inspects **the portion of the response beneath `payment`**. Consequently, descriptor paths must be calculated from the root of the subsection:

| Accessed from root response | Path in `responseFields(beneathPath("payment"), ...)` |
| --- | --- |
| `payment.method` | `method` |
| `payment.state` | `state` |
| `payment.card.brand` | `card.brand` |
| `payment.card.last4` | `card.last4` |
| `payment.transactionId` | `transactionId` |

If you mistakenly write `fieldWithPath("payment.state")` in the detailed table, REST Docs will look for a `payment` field **inside** the extracted `payment` section, causing a documentation failure.

`optional()` on `transactionId` allows a valid response that does not yet have a transaction ID. In the current example, the response includes that field; to accurately verify optionality, you should add another test with a payment state that has not yet generated a transaction ID.

## 4. Snippet Names and Embedding in Asciidoctor

With the identifier `orders-get`, the test above generates the related snippets in the configured output directory, typically `build/generated-snippets/orders-get/` with Gradle:

| Snippet | Content |
| --- | --- |
| `http-response.adoc` | The full HTTP response, including status, headers, and body. |
| `response-body.adoc` | The entire response body. |
| `response-fields.adoc` | Overview table describing the five root-level components. |
| `response-body-payment.adoc` | Body of the response portion selected by `beneathPath("payment")`. |
| `response-fields-payment.adoc` | Table of fields inside `payment`. |

The names of the last two snippets come from `withSubsectionId("payment")`. If you omit `withSubsectionId`, REST Docs derives the subsection ID from the path in the form `beneath-<path>`; the filenames depend on that default ID. Therefore, set an explicit ID when you need stable, meaningful filenames for your documentation.

Example `src/docs/asciidoc/orders.adoc` file:

```asciidoc
= Orders API
:toc: left

== GET /orders/{orderId}

Query order status and payment information.

=== Sample HTTP Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response Fields

include::{snippets}/orders-get/response-fields.adoc[]

=== Payment JSON Details

include::{snippets}/orders-get/response-body-payment.adoc[]

=== Payment Fields

include::{snippets}/orders-get/response-fields-payment.adoc[]
```

The `snippets` attribute must be configured to point to the snippet output directory. The authoring example above uses the default Asciidoctor format. To use Markdown snippets, you must configure the corresponding template/output and adjust how files are combined in the documentation.

## 5. Integrating into Build and CI

A core principle of Spring REST Docs is that **documentation is tied to HTTP tests**. If a test fails because the API returns an incorrect payload or misses a required field, the documentation build should not publish stale snippets as if they were still valid.

Gradle example (Groovy DSL), assuming the project already applies the Asciidoctor plugin and the `test` task already has the REST Docs dependency:

```groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

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

In CI, you can run:

```bash
./gradlew clean test asciidoctor
```

The CI environment must have the appropriate JDK, test dependencies, and documentation generation plugin. The command above runs tests before building Asciidoctor, preventing documentation from being published when relevant test cases fail. For Maven projects, the typical snippet path is `target/generated-snippets`, and the build lifecycle should be configured so tests run before the documentation generation step.

To make CI more reliable, keep test data deterministic and avoid writing responses containing real sensitive data into snippets. This example uses only dummy data, with `card.last4` instead of a full card number.

## 6. What Does Strict Response Documentation Catch?

`responseFields(...)` performs strict validation by default. Fields within the snippet's scope must have matching descriptors unless you intentionally use a relaxation mechanism.

| Scenario | What Can Happen |
| --- | --- |
| Adding `payment.gatewayReference` to JSON without adding a descriptor in the `beneathPath("payment")` table | The test fails due to an undocumented field. |
| Removing `payment.state` while the `state` descriptor remains required | The test fails because a documented field is missing. |
| Removing `payment.transactionId` when the descriptor has `optional()` | The field table remains valid. |
| Adding `total.tax` while only `subsectionWithPath("total")` exists in the root table | The overview table may still pass because the `total` branch is covered. |
| The endpoint response changes to an empty body in a test using `beneathPath("payment")` | The branch cannot be extracted as expected; verify the scenario and path. |

Related descriptors:

- **`fieldWithPath("x")`:** documents a field by JSON path.
- **`subsectionWithPath("x")`:** documents the entire `x` branch and counts descendants in the branch as documented for the current snippet.
- **`optional()`:** marks a field as allowed to be absent from the response.
- **`ignored()`:** allows a known field not to appear in the table while still being handled in document validation; should be used deliberately.
- **`relaxedResponseFields(...)`:** relaxes constraints on undocumented fields; useful for selective documentation, but can easily miss schema changes if overused.
- **`beneathPath("x")`:** selects a subtree for `responseBody(...)` or `responseFields(...)` to operate within that scope.

For example, if `payment` has an extra custom field that should not appear in the table, you can use `ignored()` on that exact path instead of relaxing the entire snippet. If the API has a fixed contract, a strict detailed table helps catch unexpected changes early.

## 7. Handling Paths for Objects and Arrays

### Nested Objects

JSON field paths use dots to denote object levels. When documenting from the root, use `payment.card.brand`; when `payment` has been extracted via `beneathPath`, use `card.brand`. For JSON keys that literally contain a dot (e.g., `"card.brand"` as the full key name), use special key path syntax rather than treating the dot as an object separator.

### Arrays in the Response

Given the response:

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 },
    { "sku": "PEN-002", "quantity": 1 }
  ]
}
```

If you want to document the fields of each array element directly from the **root**, you can use:

```java
responseFields(
    fieldWithPath("items[].sku")
        .description("Product SKU"),
    fieldWithPath("items[].quantity")
        .description("Quantity")
)
```

The `[]` notation represents array elements. For large responses with many groups, you can combine an overview table with detailed documentation for each group; before using `beneathPath(...)` on an array structure, confirm that the path points to the exact portion to extract and that descriptors are declared relative to that extracted portion.

### Responses with Multiple Variants

An API may return different structures depending on order status:

- `PAID` has `payment.transactionId`.
- `PENDING` does not yet have `payment.transactionId`.
- `CANCELLED` may omit `payment` altogether.

If the contract genuinely allows these variants, write **the corresponding HTTP tests**. For the variant without `payment`, do not call the `beneathPath("payment")` extractor because the branch to extract does not exist. Only use `optional()` when the field itself is optional per the contract; `optional()` cannot conjure an absent subsection for an extractor to process.

## 8. Equivalents with WebTestClient and REST Assured

Payload extraction and descriptors belong to `PayloadDocumentation`, so the subsection documentation strategy remains the same. What mainly changes is where the `document(...)` handler is attached to the HTTP exchange.

**WebTestClient:** assuming `webTestClient` is already configured with Spring REST Docs and `document` is statically imported from `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-1042")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.payment.state").isEqualTo("CAPTURED")
    .consumeWith(document("orders-webtestclient",
        responseFields(
            beneathPath("payment").withSubsectionId("payment"),
            fieldWithPath("method").description("Method"),
            fieldWithPath("state").description("State"),
            fieldWithPath("card.brand").description("Card brand"),
            fieldWithPath("card.last4").description("Last four digits"),
            fieldWithPath("transactionId").optional()
                .description("Transaction ID")
        )
    ));
```

**REST Assured:** assuming `spec` is a `RequestSpecification` with a configured REST Docs filter and `document` is statically imported from `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-restassured",
        responseBody(
            beneathPath("payment").withSubsectionId("payment")
        )
    ))
    .when()
    .get("/orders/ord-1042")
    .then()
    .statusCode(200);
```

All three tools use a real HTTP exchange in the test to obtain data for snippet generation; the snippets above only illustrate how to attach response snippets and do not replace the full test environment setup.

## 9. Common Errors When Documenting a Response Subsection

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `responseFields` reports a missing field or invalid path | Used `payment.state` in a table that already extracted `payment` | Change path to `state` because paths are relative to the subsection. |
| `responseFields` reports an undocumented field | JSON returned an extra field inside a strict subsection | Add a descriptor or deliberately mark it `ignored()` when appropriate. |
| Test passes even though the response has a new child field | The overview table only has `subsectionWithPath(...)` | Add a `responseFields(beneathPath(...), ...)` table to verify the branch. |
| `response-body-payment.adoc` is not generated | `responseBody(beneathPath(...))` was not called or the ID changed | Check the identifier, subsection ID, and test run output. |
| Cannot extract `payment` | The test case's response lacks the branch or the path has wrong casing | Check the received body and the response variant's contract. |
| Asciidoctor reports a missing snippet | Wrong `snippets` path, tests did not run, or filename mismatch | Check build configuration, output directory, and actual filenames. |
| Snippet contains data that should not be public | Test used real user or transaction data | Use dummy fixtures and remove/redact sensitive data before generating docs. |

## 10. Practice Exercise

Starting from `OrderResponseDocumentationTest` in Section 3:

1. **Strict verification:** add `payment.gatewayReference` to the controller JSON without changing the descriptors. Run the test and observe the undocumented field error; then declare `fieldWithPath("gatewayReference").description("Payment gateway reference code")` in the detailed table.
2. **Optional verification:** remove `transactionId` from the response; keep `optional()` and verify the documentation still builds. Remove `optional()` and re-run to see the difference.
3. **Document another branch:** add `responseBody(beneathPath("total").withSubsectionId("total"))` and a `responseFields(beneathPath("total").withSubsectionId("total"), ...)` table for `amount` and `currency`. Update Asciidoctor to include the two new snippets.
4. **Verify variants:** write a test for an unpaid order where `payment.transactionId` is not yet present. Only record snippets when HTTP status and business data assertions pass.
5. **Build integration:** run `./gradlew clean test asciidoctor` and open the exported HTML page. Compare the snippets against the response body used by the test.

**Completion criteria:** you can explain why `subsectionWithPath` does not guarantee checking all child fields, choose `beneathPath` to extract a JSON portion, use relative paths in the detailed field table, and verify response schema changes via test results.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): how to document fields and subsections in request/response payloads.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): test configuration, snippet templates, Asciidoctor, and build integration.
