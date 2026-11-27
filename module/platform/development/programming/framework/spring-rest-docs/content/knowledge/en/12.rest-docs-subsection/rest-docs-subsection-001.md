# Documenting a Subsection of a Request Payload in Spring REST Docs

## 1. Objectives and Context

**Spring REST Docs** generates REST API documentation from actual HTTP tests running through **MockMvc**, **WebTestClient**, or **REST Assured**. When a test succeeds, the tool produces *snippets* describing the request, response, payload, headers, and parameters. These snippets can be included in Asciidoctor or Markdown documentation and run as part of the build/CI pipeline.

This lesson belongs to the **Subsection** group and focuses on **documenting a subsection of a request payload**: a JSON request may contain multiple nested branches, yet readers sometimes only need to inspect the shipping address branch, payment information, or a specific group of properties.

After this lesson, you will be able to:

- Distinguish between giving a high-level overview of a branch and extracting that branch to document it in detail.
- Use `subsectionWithPath(...)`, `beneathPath(...)`, `requestFields(...)`, and `requestBody(...)` for their intended purposes.
- Create a MockMvc test that generates multiple snippets from the same request and include them in Asciidoctor documentation.
- Understand how required fields, undocumented fields, optional fields, and invalid path errors are verified.

## 2. Three Ways to View a Payload Subsection

Suppose the `POST /orders` endpoint receives the following JSON:

```json
{
  "customerId": "cus-17",
  "shippingAddress": {
    "recipient": "Nguyen Lan",
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
```

Here, `shippingAddress` is a **subsection** (child branch) of the payload. There are three distinct needs:

| Need | Suitable API | Result |
| --- | --- | --- |
| Only introduce `shippingAddress` as a data block | `requestFields(subsectionWithPath("shippingAddress").description(...))` | The field table has one row for `shippingAddress`; its child fields are considered documented within *that snippet*. |
| Display the shipping address JSON separately | `requestBody(beneathPath("shippingAddress"))` | The body snippet contains only the extracted JSON portion. |
| Explain each field inside the shipping address | `requestFields(beneathPath("shippingAddress"), fieldWithPath(...), ...)` | A separate table for the fields of `shippingAddress`; paths in the table are **relative** to the selected branch. |

**Important distinction:**

- `subsectionWithPath("shippingAddress")` is a *field descriptor*. It tells REST Docs that the `shippingAddress` branch and all of its descendants are considered documented in the current field table; by itself, it **does not generate a separate JSON snippet**.
- `beneathPath("shippingAddress")` is a *subsection extractor*. It extracts the branch so that `requestBody(...)` can output the body or `requestFields(...)` can validate and describe the fields **inside** that branch.
- Both can be used together: an overview table documents the request at the root level, a detailed table documents the shipping address, and a separate body snippet helps readers see the data structure.

## 3. Complete Example with MockMvc

The example below uses **JUnit 5**, **Java 17+**, **MockMvc**, and the Spring REST Docs extension. The sample controller is declared directly inside the test so the example remains independent of business logic and a database. In a real project, replace the sample controller with your application's controller/bean.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new ExampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentShippingAddressSubsection() throws Exception {
        String requestJson = """
                {
                  "customerId": "cus-17",
                  "shippingAddress": {
                    "recipient": "Nguyen Lan",
                    "street": "12 Nguyen Hue",
                    "city": "Ho Chi Minh City",
                    "postalCode": "700000"
                  },
                  "items": [
                    { "sku": "BOOK-01", "quantity": 2 }
                  ]
                }
                """;

        this.mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",

                        // (1) Document the request at the root level.
                        requestFields(
                                fieldWithPath("customerId")
                                        .description("ID of the customer creating the order"),
                                subsectionWithPath("shippingAddress")
                                        .description("Shipping address"),
                                subsectionWithPath("items")
                                        .description("List of ordered items")
                        ),

                        // (2) Extract only the JSON portion of shippingAddress.
                        requestBody(beneathPath("shippingAddress")
                                .withSubsectionId("shipping")),

                        // (3) Document the subsection fields in detail.
                        requestFields(
                                beneathPath("shippingAddress")
                                        .withSubsectionId("shipping"),
                                fieldWithPath("recipient")
                                        .description("Recipient name"),
                                fieldWithPath("street")
                                        .description("Street address and house number"),
                                fieldWithPath("city")
                                        .description("Delivery city"),
                                fieldWithPath("postalCode")
                                        .optional()
                                        .description("Postal code, can be omitted")
                        )
                ));
    }

    @RestController
    static class ExampleOrderController {

        @PostMapping("/orders")
        public ResponseEntity<Map<String, String>> create(
                @RequestBody Map<String, Object> request) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "ord-001"));
        }
    }
}
```

Requirements for the code to run: the test classpath must include JUnit Jupiter, Spring MVC Test, and Spring REST Docs MockMvc; the project must have a configured snippet output directory (commonly `build/generated-snippets`). This example uses a JSON request: `contentType(MediaType.APPLICATION_JSON)` allows REST Docs to identify the payload type properly.

### Explaining the Key Decisions

**(1) The root-level table validates the structure.** `requestFields(...)` is *strict* by default: if an undocumented field appears in the request, the test can fail. `customerId` is documented directly, while `shippingAddress` and `items` use `subsectionWithPath(...)` so their respective child fields are treated as covered. The overview table has only three main rows, making it suitable for introducing the request shape.

**(2) Slicing the body portion to highlight.** `requestBody(beneathPath("shippingAddress").withSubsectionId("shipping"))` generates a snippet containing the JSON for the address branch alone. In this case, its content is equivalent to:

```json
{
  "shippingAddress": {
    "recipient": "Nguyen Lan",
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  }
}
```

The snippet retains the `shippingAddress` element name so readers can see where this branch sits. It does not contain `customerId` or `items`.

**(3) The detailed table independently validates the selected branch.** Because the extractor selects `shippingAddress`, the corresponding paths are `recipient`, `street`, `city`, and `postalCode`—**not** `shippingAddress.recipient` or `shippingAddress.city`. `postalCode` is marked `optional()`: if this field is absent, the test still passes; the remaining three fields must be present in the test case's payload.

A common point of confusion: using `subsectionWithPath("shippingAddress")` in the root-level table **does not disable** detailed validation in the third table. Each `requestFields(...)` is a separate snippet with its own scope and descriptors. Therefore, you can have both a high-level overview and a full field-level verification of the branch.

## 4. Generated Snippets and How to Author the Documentation

With the identifier `orders-create` and subsection ID `shipping`, when the test runs successfully, REST Docs generates (in addition to the default snippets) the following main files inside `build/generated-snippets/orders-create/`:

| File | Content |
| --- | --- |
| `http-request.adoc` | The actual HTTP request tested. |
| `request-body.adoc` | The full request body (default snippet). |
| `request-fields.adoc` | Root-level field table: `customerId`, `shippingAddress`, `items`. |
| `request-body-shipping.adoc` | Extracted body for the `shippingAddress` branch only. |
| `request-fields-shipping.adoc` | Detailed field table for `recipient`, `street`, `city`, `postalCode`. |

If you do not call `withSubsectionId("shipping")`, the default subsection ID takes the form `beneath-<path>`. For example, the path `shippingAddress` generates filenames such as `request-body-beneath-shippingAddress.adoc` and `request-fields-beneath-shippingAddress.adoc`. Using a readable ID keeps snippet filenames stable even when a path is intentionally renamed.

In an Asciidoctor documentation file, with the `snippets` attribute pointing to the output directory, you can write:

```asciidoc
= Create Order
:toc: left

== POST /orders

Create an order from a customer ID, shipping address, and list of items.

=== HTTP Request Example
include::{snippets}/orders-create/http-request.adoc[]

=== Overview Request Structure
include::{snippets}/orders-create/request-fields.adoc[]

=== Shipping Address JSON
include::{snippets}/orders-create/request-body-shipping.adoc[]

=== Shipping Address Fields
include::{snippets}/orders-create/request-fields-shipping.adoc[]
```

The following Gradle configuration example (Groovy DSL) assumes the project already applies the Asciidoctor plugin and has `test`/`asciidoctor` tasks. It illustrates the build relationship: the documentation is built after the tests generate the snippets.

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

In a real build, you must configure REST Docs to write snippets to the same directory and pass the `snippets` attribute to Asciidoctor. If you choose Markdown templates instead of Asciidoctor, the file extension and snippet include syntax will differ; the examples in this lesson use the default Asciidoctor configuration.

## 5. Which Approach Should You Choose in Each Situation?

### Only Need to Describe the Meaning of an Entire Block

For example, an API accepts flexible metadata, but at the overview level you only need to state "custom customer metadata":

```java
requestFields(
    fieldWithPath("name").description("Display name"),
    subsectionWithPath("metadata")
        .description("Group of custom attributes")
)
```

`subsectionWithPath` keeps the table concise. On the other hand, this test does not verify individual child fields of `metadata`; if the internal structure matters, add a detailed snippet/test.

### Need to Describe Each Property of a Payload Section

Use `beneathPath` with `requestFields`:

```java
requestFields(
    beneathPath("shippingAddress")
        .withSubsectionId("shipping-details"),
    fieldWithPath("recipient").description("Recipient name"),
    fieldWithPath("street").description("Street address and house number"),
    fieldWithPath("city").description("City"),
    fieldWithPath("postalCode").optional().description("Postal code")
)
```

This is a good choice when client implementers need to know the exact schema of a specific block, especially for large requests.

### Only Need to Extract a Readable JSON Example

Use `requestBody(beneathPath(...))`. The body snippet helps readers visualize the child payload, but **does not replace** documenting and validating individual fields with `requestFields(...)` if schema protection is needed.

## 6. Path Rules and Impact on Verification

### Absolute Paths vs. Relative Paths

Using the JSON from the start of the lesson:

| Context | Valid Path | Meaning |
| --- | --- | --- |
| Root-level `requestFields(...)` | `shippingAddress.city` | Points from the root to the city. |
| Root-level `requestFields(...)` | `shippingAddress` | Points to the entire address branch. |
| `requestFields(beneathPath("shippingAddress"), ...)` | `city` | Points to the city inside the extracted branch. |
| `requestFields(beneathPath("shippingAddress"), ...)` | `postalCode` | Points to the postal code inside the extracted branch. |

For JSON arrays, path syntax uses `[]`: for example, `items[].sku` and `items[].quantity` when documenting at the root level. For keys containing dots, you can use bracket notation like `['shipping.address']` so the dot is interpreted as part of the key. Paths must match the actual JSON structure; REST Docs does not infer field names from Java DTOs.

### Strict, Optional, Ignored, and Relaxed

- **`requestFields(...)` (strict):** fails if there is an undocumented field within the validation scope or if a documented required field does not appear. With `beneathPath`, the scope applies to the selected subsection.
- **`optional()`:** accepts an absent field; should be used for data where the contract allows clients to omit it, not as a way to mask a misspelled path.
- **`ignored()`:** allows a field/branch to be considered covered without appearing in the table. Should only be used when intentionally excluding it from documentation; one example is a known internal technical field.
- **`relaxedRequestFields(...)`:** does not fail on undocumented fields. It still checks the presence of declared required descriptors. Useful for scenario-specific documentation, but less effective than strict mode for catching unintended schema changes.
- **`subsectionWithPath(...)`:** covers the entire child branch within that snippet; suitable for high-level presentation. If you want to verify child fields, declare an additional detailed snippet using `beneathPath(...)`.

A notable change example: a developer adds `shippingAddress.country` to the request. The overview table using `subsectionWithPath("shippingAddress")` will still pass, whereas the **strict** detailed table using `beneathPath("shippingAddress")` can fail because `country` is undocumented. As a result, schema changes force authors to update the documentation or explicitly decide why the new field is not documented.

### When the Subsection Is Absent

`beneathPath("shippingAddress")` must be able to find the corresponding branch in the request used to generate the snippet. If the API allows omitting `shippingAddress` entirely, use a **test case with an address** to generate the detailed documentation and a separate test case to verify request behavior **without an address**. Do not simply add `optional()` to the root-level descriptor and assume the extractor will always work when the branch does not exist.

## 7. Applying with WebTestClient or REST Assured

Payload documentation mechanics live in `PayloadDocumentation`, so field descriptors and extractors can be reused across testing tools. What changes is where `document(...)` is attached to the request/response.

**With WebTestClient**, assuming `webTestClient` is already configured with Spring REST Docs:

```java
webTestClient.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(requestJson)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders-webtestclient",
        requestFields(
            beneathPath("shippingAddress").withSubsectionId("shipping"),
            fieldWithPath("recipient").description("Recipient name"),
            fieldWithPath("street").description("Street address and house number"),
            fieldWithPath("city").description("City"),
            fieldWithPath("postalCode").optional().description("Postal code")
        )
    ));
```

In this snippet, `document` is statically imported from `WebTestClientRestDocumentation`. The test needs to configure `WebTestClient` with REST Docs before running.

**With REST Assured**, assuming `spec` is a `RequestSpecification` already configured with the Spring REST Docs filter:

```java
RestAssured.given(spec)
    .contentType("application/json")
    .body(requestJson)
    .filter(document("orders-restassured",
        requestBody(beneathPath("shippingAddress")
            .withSubsectionId("shipping"))
    ))
    .when()
    .post("/orders")
    .then()
    .statusCode(201);
```

Here, `document` is statically imported from `RestAssuredRestDocumentation`. What all three approaches share is generating snippets from an **actual tested HTTP exchange**, rather than crafting static examples by hand.

## 8. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Test reports an undocumented field | Strict `requestFields` encountered a new field or missing descriptor | Add a descriptor, or use `subsectionWithPath`/`ignored` when genuinely intentional. |
| Test reports a missing required field | Incorrectly declared path, field missing from payload, or wrong nesting level | Compare actual JSON against the path; with `beneathPath`, use a **relative** path. |
| Subsection not found | `beneathPath` points to the wrong branch or the test case did not send that branch | Check key name/casing and the test's request data. |
| Missing `request-fields-shipping.adoc` | `requestFields(beneathPath(...))` was not called or the test did not reach `document` | Check REST Docs configuration and the subsection ID name. |
| Asciidoctor cannot `include` snippet | Wrong `snippets` attribute, wrong output directory, or docs step ran before tests | Check paths and the `asciidoctor -> test` task dependency. |
| Added a child field yet test still passes | Only root-level `subsectionWithPath` exists, without a strict detailed table | Add `requestFields(beneathPath(...), ...)` to validate the child schema. |

## 9. Practice Exercise

Extend the `POST /orders` example in order:

1. Add `country` to `shippingAddress` in the JSON and re-run the test. Observe the strict detailed snippet reporting an undocumented field; then add `fieldWithPath("country").description("Country code")`.
2. Remove `postalCode` from the request. Verify the test still passes because the descriptor has `optional()`; then temporarily remove `optional()` to observe the missing required field error.
3. Change the subsection ID from `shipping` to `delivery` in both `requestBody` and `requestFields`. Update the corresponding `include` directives in Asciidoctor.
4. Write an additional test for the case where the request does not contain `shippingAddress` per the application contract; do not use the branch extractor in that test.

**Completion criteria:** you can explain why the root-level table still passes when a child field is added, why the strict detailed table can fail, and how to use a dedicated body snippet together with a dedicated field table without manually duplicating JSON into the documentation.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): describes `subsectionWithPath`, `beneathPath`, `requestBody`, `requestFields`, JSON paths, and field validation rules.
- [Spring REST Docs — Reference](https://docs.spring.io/spring-restdocs/reference/): guide to configuration, snippet generation, and integrating documentation into the build.
