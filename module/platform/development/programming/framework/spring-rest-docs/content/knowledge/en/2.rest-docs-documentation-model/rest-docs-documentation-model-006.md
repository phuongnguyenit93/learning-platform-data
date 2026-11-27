# Distinguishing Actual Response Data from Contract Descriptions

A JSON response might contain `"status": "CONFIRMED"`, yet from that single response alone, we **cannot conclude** that `CONFIRMED` is the only valid status, that every order has this status, or that a client is always authorized to view the order. A response shows **what happened in one call**; an API contract defines **what the server commits to the client under defined conditions**.

This distinction is especially important in **Spring REST Docs**. The library records requests and responses while running HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**, and uses descriptors to generate snippets for payloads, parameters, headers, requests, and responses. Afterward, Asciidoctor/Markdown combines snippets with business explanations and contract rules into complete documentation. Confusing observed data with the contract can fill documentation with untested promises or leave out cases that clients actually have to handle.

This lesson belongs to the **Documentation Model** chapter of the `SPRING_REST_DOCS` module. The focus is on understanding three layers—**the actual response**, **the contract description**, and **the test evidence connecting those two layers**—so you can write documentation that is both accurate and verifiable in build and CI.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish a concrete response from the HTTP/JSON contract of an operation.
2. Identify what can be inferred from observed status codes, headers, and payloads, as well as what cannot be inferred.
3. Use assertions and Spring REST Docs descriptors to verify the declared parts of a contract.
4. Distinguish **an absent field**, **a field with value `null`**, **a fixed value in an example**, and **a field's valid value domain**.
5. Write separate tests for success and error responses, combining snippets with business descriptions.
6. Understand the impact when a response changes and what to review before publishing documentation via CI.

## 2. An Actual Response Is an Observation; A Contract Is a Set of Rules

Suppose an order management service returns a response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: demo-req-001

{
  "id": 91,
  "status": "CONFIRMED",
  "total": 189000,
  "currency": "VND",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
```

This is **one concrete observation**: some request ran in an environment, at a specific moment, and returned those values. If a test records this response, Spring REST Docs can generate an `http-response.adoc` snippet containing that example.

However, **the contract** may also need to answer:

- Which endpoint, method, and access conditions lead to the `200` response?
- Does `id` identify an order or a payment transaction? Can it change?
- Which values are valid for `status`, and when can it transition from one state to another?
- Does `total` already include tax, shipping fees, and discounts? What is the numeric unit?
- Can `items` be empty? What naming rules apply to each `sku`?
- When does the API return `404`, `403`, or `409`? What structure does the error body have?
- Is the `X-Request-Id` header always present, and does the client need to send it back when contacting support?
- If the response varies by time, version, or caller permissions, what is the applicability scope of the schema?

One execution reveals only **a single data point** among possible scenarios. The contract must define **the set of accepted behaviors** and how clients should handle them.

### 2.1. Three Layers That Must Be Connected Without Being Conflated

| Layer | Nature | Example | Responsibility |
| --- | --- | --- | --- |
| **Actual response** | Data emitted by the server during a single test run | `200` and JSON for order `91` | Proves the test observed a concrete outcome |
| **Assertions and descriptors** | Conditions checked by the test and structural parts documented | `status().isOk()`, `jsonPath("$.status").value("CONFIRMED")`, `responseFields(...)` | Causes the test to fail when checked behavior drifts from expectations |
| **Contract description** | Commitments regarding behavior, semantics, limits, and applicability | How `total` is calculated; when `404` is returned | Helps clients integrate accurately and guides developers on what else to test |

Do not treat a sample response as **the complete contract**. Nor should you treat a written contract description as **proof that it has been implemented**. Spring REST Docs connects them through tests, yet the level of assurance depends on **the assertions, descriptors, and scenarios tested**.

### 2.2. HTTP Status Differs from Business Status Fields

In the example, there are two uses of “status” with two different meanings:

- `HTTP/1.1 200 OK` is the **HTTP status** of the call: the server successfully processed the request in HTTP terms.
- `"status": "CONFIRMED"` is the **business status** of the order inside the JSON.

A `200` response does not mean the order is confirmed; a `DRAFT` order can also be returned with `200` if a query API succeeds. Conversely, an operation that confirms an order might return `409 Conflict` when the current business state forbids the transition. The contract must explain both layers.

## 3. What Can Be Inferred from a Sample Response?

An HTTP snapshot contains many observed details, yet it does not reveal full optionality or value domains.

| Detail seen in response | What can be stated accurately | What cannot yet be concluded |
| --- | --- | --- |
| `200 OK` | This call succeeded | Every request to the same route receives `200` |
| `Content-Type: application/json` | This response was sent with JSON media type | The API supports no other media types or versions |
| `X-Request-Id: demo-req-001` | The header was present in this call | The header is always present, uses this exact format, and never repeats |
| `"id": 91` | The `id` field is present with numeric value `91` | IDs are always positive, globally unique, or immutable |
| `"status": "CONFIRMED"` | The current response contains this specific string | `CONFIRMED` is the only enum value or the default status |
| `"total": 189000` | The `total` field has a numeric value in the example | Units, taxes, rounding rules, limits, and calculation formula |
| `"items":[...]` | This time the list has one element | The array is always non-empty, ordered consistently, or unbounded |
| `discount` is not seen | The field does not appear in the example | The field is forbidden in all responses or absent when a promotion applies |

A common mistake is writing “the API always returns one element in `items`” just because the example has one element, or marking `total` as required just because the current sample includes it. Optionality and requirements must come from **the defined contract**, then be expressed and verified by tests.

### 3.1. An Example Value Is Not a Contract Constraint

You can state:

> The example response contains `"id": 91`.

But if documentation states:

> Every API call returns `"id": 91`.

that is an entirely different commitment—and almost certainly wrong for an API managing multiple orders. Likewise, seeing `total` as a JSON number does not by itself define maximum amounts, decimal precision, or zero-total conditions.

Distinguish **illustrative values** from **guaranteed properties** in both explanations and tests. Tests should fix fixtures for reproducibility, while documentation must clarify which values are merely examples.

### 3.2. A Schema Is Not Enough to Express All Business Rules

A simple JSON schema can say `status` is a string and `total` is a number. Yet rules like “only `CONFIRMED` orders may be shipped”, “customers can only view their own orders”, or “`total` equals the sum of line items after discounts” are **business invariants**. They need prose explanations, appropriate data models, and corresponding behavioral tests.

Even more detailed schemas can express enums, lengths, or patterns, while constraints tied to state, permissions, and cross-resource logic still typically require tests and business documentation.

## 4. Where Does Spring REST Docs Record Responses and Contract Descriptions?

An HTTP test can send a request via MockMvc, WebTestClient, or REST Assured and receive a response. With Spring REST Docs, calling `document("operation-id", ...)` attaches documentation snippets to **the operation just executed**.

```text
                       Agreed contract rules
                                 │
               ┌─────────────────┴─────────────────┐
               ▼                                   ▼
           Assertions                         Descriptors
     status/header/JSON values         path/query/header/fields
               │                                   │
               └─────────────────┬─────────────────┘
                                 │
Tested request ──► Application ──► Actual response
                                 │
                                 ▼
                      document("orders-get-200", …)
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
            http-response.adoc        response-fields.adoc
             (observed data)          (description table)
                    └────────────┬────────────┘
                                 ▼
                       Asciidoctor / Markdown
                       + business explanation
                                 │
                                 ▼
                          Complete API page
```

The parts serve distinct functions:

- `http-response.adoc` contains **the response example** recorded from the operation, potentially formatted by display preprocessors.
- `response-fields.adoc` is generated from `responseFields(...)`, carrying **field descriptions** declared by the author and checked against the payload.
- `response-headers.adoc` is generated if the author declares `responseHeaders(...)`.
- Assertions like `jsonPath(...)` check **values and conditions** that descriptors alone cannot guarantee.
- Business prose in the Asciidoctor/Markdown page explains **semantics, applicability conditions, and consequences** that snippets cannot deduce on their own.

For example, `fieldWithPath("total").type(JsonFieldType.NUMBER).description("Total amount")` documents the numeric type and basic meaning of the field; it does not verify the pricing calculation or tax rate. If you need to prove a calculation rule, you must write appropriate business assertions/tests.

## 5. MockMvc Example: Response Data and Field Descriptions Are Two Separate Things

This example uses Java 17+, JUnit 5, Spring MVC Test, and Spring REST Docs 3.x-style APIs. A small controller returns order `91` to provide deterministic data; nonexistent IDs return an error JSON. Fixing test data makes it easy to trace snippet origins and **does not imply a real API should hardcode IDs**.

### 5.1. Lesson Controller

```java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    record OrderItem(String sku, int quantity) {}

    record OrderView(
        long id,
        String status,
        int total,
        String currency,
        List<OrderItem> items
    ) {}

    record ErrorView(String code, String message) {}

    @GetMapping(
        value = "/api/orders/{orderId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<?> getOrder(@PathVariable long orderId) {
        if (orderId != 91L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorView(
                    "ORDER_NOT_FOUND",
                    "Order does not exist"
                ));
        }

        OrderView view = new OrderView(
            91L,
            "CONFIRMED",
            189000,
            "VND",
            List.of(new OrderItem("BOOK-01", 2))
        );

        return ResponseEntity.ok()
            .header("X-Request-Id", "demo-req-001")
            .body(view);
    }
}
```

The controller has two **distinct actual responses** depending on the fixture:

- `GET /api/orders/91` returns `200` and an `OrderView`.
- `GET /api/orders/999` returns `404` and an `ErrorView`.

Despite sharing the same route, the two payloads differ in structure and meaning. Separate documentation operations must be created so readers never mistake a success response for an error response.

### 5.2. Success Test Verifies Values and Documents Structure

The following test requires concrete values via `andExpect(...)` and documents the structure with `document(...)`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setup(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new OrderController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getOrderSuccess() throws Exception {
        mockMvc.perform(
                get("/api/orders/{orderId}", 91L)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(
                header().string("X-Request-Id", "demo-req-001")
            )
            .andExpect(jsonPath("$.id").value(91))
            .andExpect(
                jsonPath("$.status").value("CONFIRMED")
            )
            .andExpect(jsonPath("$.total").value(189000))
            .andExpect(
                jsonPath("$.items[0].sku").value("BOOK-01")
            )
            .andDo(document("orders-get-200",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Order identifier")
                ),
                responseHeaders(
                    headerWithName("X-Request-Id")
                        .description("ID supporting request tracing")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Order ID"),
                    fieldWithPath("status")
                        .type(JsonFieldType.STRING)
                        .description("Business status"),
                    fieldWithPath("total")
                        .type(JsonFieldType.NUMBER)
                        .description("Monetary amount of the order"),
                    fieldWithPath("currency")
                        .type(JsonFieldType.STRING)
                        .description("Currency code"),
                    fieldWithPath("items")
                        .type(JsonFieldType.ARRAY)
                        .description("List of line items"),
                    fieldWithPath("items[].sku")
                        .type(JsonFieldType.STRING)
                        .description("Product SKU"),
                    fieldWithPath("items[].quantity")
                        .type(JsonFieldType.NUMBER)
                        .description("Product quantity")
                )
            ));
    }
}
```

The imports here cover the main parts of the test. `OrderController` from the previous snippet needs to reside in a matching package with the test or be imported from application code. The project needs compatible Spring REST Docs, Spring MVC Test, and JUnit Jupiter dependencies; the snippet output path is configured in the build.

**Why use `RestDocumentationRequestBuilders.get`?** Spring REST Docs' request builder retains the `/api/orders/{orderId}` URI template so `pathParameters(...)` can document the `orderId` variable. If you use a request builder that does not keep the template, the path parameter snippet may fail to resolve the variable.

### 5.3. Error Test Confirms a Different Response Contract

Add the following method to the same `OrderDocumentationTest`:

```java
@Test
void getOrderNotFound() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 999L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isNotFound())
        .andExpect(
            jsonPath("$.code").value("ORDER_NOT_FOUND")
        )
        .andExpect(
            jsonPath("$.message").value("Order does not exist")
        )
        .andDo(document("orders-get-404",
            pathParameters(
                parameterWithName("orderId")
                    .description("Order identifier")
            ),
            responseFields(
                fieldWithPath("code")
                    .type(JsonFieldType.STRING)
                    .description("Machine-readable error code"),
                fieldWithPath("message")
                    .type(JsonFieldType.STRING)
                    .description("Human-readable error explanation")
            )
        ));
}
```

Here, the `404` response **has a JSON body**, because the controller was designed that way. In another application, `404` might have no body or use a different error schema. Do not infer an error schema from an HTTP status code; observe the response and verify the real contract.

The two operations produce separate snippet groups:

```text
generated-snippets/
├── orders-get-200/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── path-parameters.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── orders-get-404/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

The list above highlights directly relevant files; depending on configuration, default snippets such as `curl-request.adoc`, `httpie-request.adoc`, `request-body.adoc`, and `response-body.adoc` are also generated.

## 6. What Do Assertions, Descriptors, and Business Descriptions Check?

In the `getOrderSuccess` test, the following three statements refer to `status` at three different levels:

```java
.andExpect(status().isOk())

.andExpect(jsonPath("$.status").value("CONFIRMED"))

fieldWithPath("status")
    .type(JsonFieldType.STRING)
    .description("Business status")
```

- `status().isOk()` verifies that the **HTTP status is 200** during the test call.
- `jsonPath("$.status").value("CONFIRMED")` verifies **the value of the `status` field** in the fixture's JSON.
- `fieldWithPath("status")...` creates **a structural description of the field** and participates in response documentation validation.

Even if all three pass, that still does not prove the contract only allows `CONFIRMED` or that every `CONFIRMED` order meets invoicing criteria. To publish an enum or state transition rule, verify the business requirements and write tests suited to those constraints.

### 6.1. Descriptors Do Not Automatically Verify Business Formulas

Suppose `total` must equal the sum of line-item values after discounts plus tax. The descriptor:

```java
fieldWithPath("total")
    .type(JsonFieldType.NUMBER)
    .description("Total amount of the order")
```

only documents a numeric field in the response. If the server uses the wrong formula yet still returns a valid number, the descriptor can still pass. `jsonPath("$.total").value(189000)` guards one fixture's value; to protect the general formula, write tests covering discounts, taxes, quantities, rounding, and boundary cases.

When presenting official documentation, explicitly state **units, included charges, taxes/fees, and rounding rules** per the contract. Do not deduce these from the literal values `189000` or `VND`.

### 6.2. Strict Documentation vs. Partial Documentation

Under common Spring REST Docs usage:

- `responseFields(...)` enforces strict documentation checks on the payload structure: an undocumented field can fail the test; a field documented as required yet missing can also cause an error.
- `relaxedResponseFields(...)` allows documenting only a subset of fields of interest; remaining fields do not trigger undocumented-field failures.
- `optional()` is for fields that may be absent per the contract; do not add it merely to dodge test failures.
- `ignored()` is used when you intentionally omit a component from documentation output; do not use it to hide meaningful contract changes.

In the example response, seven field paths are documented by the test. If the controller starts returning `discountAmount` without declaring it in `responseFields(...)`, strict documentation testing catches the missing description. That forces the author to decide: does the new field belong to the public contract, what are its type and meaning, and which assertions or documentation updates are needed?

**Spring REST Docs' strict checking is not synonymous with a full JSON Schema validator.** It does not automatically enforce constraints such as enums, regex patterns, value ranges, cross-field invariants, or authorization rules.

## 7. Absent Fields, `null`, Empty Strings, and Optionality: Four Different Meanings

The most easily misunderstood cases often involve not the value of `id`, but **the presence** of a field.

### 7.1. Four Sample Responses

Suppose the API has a `note` field. These four JSON payloads are not equivalent:

**Case A — field omitted from payload:**

```json
{"id":91,"status":"CONFIRMED"}
```

**Case B — field present with value `null`:**

```json
{"id":91,"status":"CONFIRMED","note":null}
```

**Case C — field present with an empty string:**

```json
{"id":91,"status":"CONFIRMED","note":""}
```

**Case D — field present with content:**

```json
{"id":91,"status":"CONFIRMED","note":"Deliver during office hours"}
```

| Field state | Observed behavior | Contract question to answer |
| --- | --- | --- |
| Absent | Client does not receive the `note` key | Is it optional depending on order type, version, or role? |
| Present and `null` | Key exists with no value | Is `null` a valid state or a serialization bug? |
| Empty string | Value exists with zero length | Are empty strings permitted or should the field be omitted? |
| Non-empty string | Contains a specific value | Are there length, character, or format constraints? |

If the contract says `note` may be omitted, the descriptor can use `optional()`, yet **optional does not explain the meaning of `null` on its own**. Business prose must tell clients whether `null` and a missing key mean the same thing. If that difference affects client applications, write tests for both forms.

### 7.2. Declaration Rules Must Originate from the Contract

Illustrative descriptor for an optional field:

```java
fieldWithPath("note")
    .type(JsonFieldType.STRING)
    .description(
        "Delivery note; may be omitted when no note has been set"
    )
    .optional()
```

This declaration states that the field may **be absent** from the response while keeping the documentation test valid. It does not guarantee the field is always non-null when present, does not prove the string is non-empty, and does not guarantee responses for other roles behave identically. If the contract includes those constraints, document and test them accordingly.

Similarly, `items: []` means the `items` field **is present as an empty array**, which differs from omitting the `items` field altogether. In APIs with pagination or field-level redaction, this distinction can affect client logic.

## 8. Distinguishing a Single Case from a Multi-Scenario Contract

A public API rarely has only one response. For the same `GET /api/orders/{orderId}`, a contract may distinguish:

| Scenario | Possible HTTP status | Payload shape | What needs explanation |
| --- | --- | --- | --- |
| Order exists and caller is authorized | `200 OK` | Order JSON | Fields, units, status, and access permissions |
| Not found or hidden by policy | `404 Not Found` | Error JSON or no body | Not-found conditions and handling |
| Missing or invalid authentication credentials | `401 Unauthorized` | Per API error schema | Required authentication mechanism |
| Known identity lacking permission | `403 Forbidden` | Per API error schema | Disallowed roles or scopes |
| State conflict during update | `409 Conflict` | Business error JSON | How to reload state or adjust the action |

The `401`, `403`, and `409` rows are **scenarios to consider if supported by the API**, not behaviors proven by the illustrative controller/test in section 5. The real contract determines which statuses and payloads the endpoint uses.

A single `200` test cannot represent every response. Proper documentation requires dedicated operations for scenarios meaningful to clients, using clear identifiers such as `orders-get-200` and `orders-get-404`. Each scenario can have its own response field table.

### 8.1. Do Not Conflate HTTP Status with Business Outcome

A particularly dangerous mistake is writing “`status=CONFIRMED` means HTTP `200`”. A `CANCELLED` order can still be queried via `GET` and return `200`; conversely, a `POST` that confirms an order might succeed with another HTTP status per the contract, such as `200` or `204`. Clearly describe **which request** and **which action** alter business state.

### 8.2. Test Scope Defines Evidence Scope

MockMvc `standaloneSetup` in the example runs against a standalone controller instance; it does not verify the database, security filters, or production configuration. If the contract states “only the order owner can view the order”, test with security configuration and appropriate ownership data. WebTestClient or REST Assured can observe other layers of the application depending on how they bind or call a running server, yet neither automatically proves rules that tests do not assert.

## 9. When Response Data Changes, How Must Documentation React?

Consider changes that may occur in an API:

| Actual change | What the sample test can catch | What needs updating |
| --- | --- | --- |
| `status` changes from `CONFIRMED` to `CANCELLED` on fixture `91` | `jsonPath("$.status")` assertion fails | Verify business rules, fixture, and assertion; review descriptions |
| Response adds `discountAmount` | Strict `responseFields(...)` fails | Decide if field belongs to contract, add descriptor/tests |
| `total` changes from JSON number to string | Type descriptor `NUMBER` no longer matches | Align on new type, check compatibility, and update client docs |
| `total` formula changes while fixture still outputs `189000` | Current test may still pass | Add boundary/diverse scenario tests and update business rules in docs |
| `X-Request-Id` header no longer appears | Header assertion and response header descriptor fail | Confirm if contract changed and update documentation |
| `items` becomes an empty array | `items[0].sku` assertion fails | Review fixture input and handle empty arrays per contract |
| Added `403` response for another role | `200` test does not catch it automatically | Write role tests and add authorization/error documentation |

In practice, some changes are backward-compatible for clients while others are breaking changes. Evaluation must rest on **the public contract** and how clients consume it, not solely on whether documentation tests pass. For instance, adding a JSON field is tolerated by many clients, though it may break strict schema-validating consumers; changing a field's type or removing a required field typically carries higher risk.

### 9.1. Workflow When a Mismatch Is Detected

When snippets, tests, or documentation show signs of divergence:

1. **Observe the exact failure:** which status, header, or field changed? Did a fixture or test configuration change?
2. **Verify the intended contract:** is the difference an implementation bug or a new API requirement?
3. **Update the right place:** if the implementation is wrong, fix the code; if the contract changed intentionally, update assertions, descriptors, business prose, and related examples.
4. **Expand tests if needed:** add cases for `null`, missing fields, roles, states, numeric boundaries, or errors.
5. **Regenerate snippets and compile:** run from a clean output directory and inspect the complete documentation page.
6. **Assess compatibility:** if clients already depend on the old behavior, apply an appropriate versioning/migration policy.

Do not update every assertion to turn green against a new response before checking whether that behavior is intended. Conversely, never keep stale documentation just because an older test version used to pass.

## 10. Combining Response Snippets and Contract Descriptions in a Documentation Page

An Asciidoctor page for the orders API can combine tested responses with author-written explanations:

```asciidoc
[[orders-get]]
=== Look up an order

GET /api/orders/{orderId} returns the current representation
of an order that the caller is authorized to access.

==== Sample request

include::{snippets}/orders-get-200/http-request.adoc[]

==== Path parameter

include::{snippets}/orders-get-200/path-parameters.adoc[]

==== Successful response (HTTP 200)

include::{snippets}/orders-get-200/http-response.adoc[]

==== Response headers

include::{snippets}/orders-get-200/response-headers.adoc[]

==== Response JSON fields

include::{snippets}/orders-get-200/response-fields.adoc[]

status is the business status; the set of values and transition
rules must be defined in the contract.

total must be clearly explained regarding currency, taxes, fees, and rounding.
Values in the response example do not represent all orders.

==== Not found (HTTP 404)

include::{snippets}/orders-get-404/http-request.adoc[]

include::{snippets}/orders-get-404/http-response.adoc[]

include::{snippets}/orders-get-404/response-fields.adoc[]
```

In this example, the `include::{snippets}/...[]` directives use **Asciidoctor** syntax; the build must set the `snippets` attribute pointing to the output directory. For Markdown, you need a snippet injection/conversion step or compatible templates; do not assume every Markdown renderer understands `include::...[]`.

The paragraphs explaining `status` and `total` act as **placeholders for the contract**. In real documentation, fill in confirmed rules rather than leaving vague promises or guesses inferred from sample responses.

### 10.1. Example Data Can Be Normalized, While the Contract Must Stay Accurate

Spring REST Docs supports preprocessors, such as `preprocessResponse(prettyPrint())` to format responses, or mechanisms to replace/remove values unsuitable for public docs. Normalization helps when responses contain random request IDs, timestamps, test-environment hostnames, or sensitive data.

Keep in mind:

- A post-processed snippet is **a display form of the tested interaction**, not necessarily byte-for-byte identical to the raw response.
- Assertions should verify protected behavior on the real test response, independent of output formatting.
- Never use preprocessing to mask changes in data types, statuses, or contract fields.
- Never put passwords, real tokens, session cookies, or personal data into public snippets.

If a randomly generated request ID is replaced with `demo-req-001` in the docs, make clear it is an **illustrative value**. The contract must still describe the format and lifecycle of the request ID if clients depend on it.

## 11. Which Parts of Documentation Do Build and CI Verify?

A typical documentation pipeline:

```text
Source + agreed contract
            │
            ▼
     HTTP documentation tests
      ├── Assertions
      └── Descriptor validation
            │
        ┌───┴────┐
        │        │
      FAIL      PASS
        │        │
    Stop build   ▼
          generated-snippets/
                 │
                 ▼
            Compile pages
       Asciidoctor / Markdown
                 │
                 ▼
        Check includes, links,
       sensitive data, content
                 │
                 ▼
              Publish
```

With Gradle, snippet output typically lives in `build/generated-snippets`; with Maven, typically `target/generated-snippets`, depending on configuration. The documentation compilation step must depend on the snippet-generating tests, use the right output directory, and fail on broken includes. In CI, ensure snippets are regenerated from the source being built so skipped tests cannot silently reuse leftover files.

This step increases confidence in **HTTP examples and structure tables**. However, passing tests and clean page rendering **do not automatically verify** a business rule that was never written as an assertion or reviewed by contract owners.

### 11.1. Clear Division of Review Responsibilities

| Role / activity | Questions to verify |
| --- | --- |
| Endpoint developer | Do requests/responses, statuses, and schemas match the intended implementation? |
| Test author | Which values/constraints do assertions protect, and which cases remain uncovered? |
| Descriptor author | Do fields, types, optional/ignored flags, and headers accurately reflect the contract? |
| Business domain owner | Are enums, access rules, taxes/fees, lifecycle, and error codes accurate? |
| CI maintainer | Do tests run before rendering, is output clean, and are includes valid? |
| Documentation reviewer | Is the page clear, free of contradictions, and free of sensitive data leaks? |

In small projects, one person may wear multiple hats. What matters is answering these questions before treating the documentation as an official contract.

## 12. Common Mistakes

| Claim or symptom | Issue | How to resolve |
| --- | --- | --- |
| “The example shows `200`, so the endpoint always returns `200`” | Confuses one observation with the entire response space | Document conditions and important error cases |
| “`status` is a string, so any string is valid” | Data type is not equivalent to valid value domain | Define the enum and test values/transition rules |
| “The field appears in the test, so it is always required” | Ignores variations by role, state, or version | Verify contract, use `optional()` appropriately, and test variants |
| “`null` and an omitted field mean the same thing” | Clients may handle them differently | Explicitly document nullability and field presence |
| “`responseFields(...)` passed, so the pricing formula is right” | Descriptors primarily verify documented structure | Write tests for pricing math, rounding, and boundaries |
| New response contains an unknown field, test fails | Descriptors were not updated for the change | Confirm contract change and update descriptions if valid |
| No test fails when the meaning of `total` changes | Semantic change did not alter types/schema | Review business logic and add appropriate assertions |
| Page only embeds `http-response.adoc` | Missing applicability conditions and field explanations | Add contract rules, statuses, and error codes |
| Snippets reflect an earlier build | Tests did not run or output was not cleaned | Wire task dependencies and regenerate outputs in CI |
| Public docs contain sensitive traces or tokens | Observed data was not scrubbed properly | Use dummy fixtures, inspect, and safely normalize snippets |

## 13. Hands-On Exercise: Proving Claims About Responses

Suppose the team wants to publish a contract for `GET /api/orders/{orderId}`:

> If the order exists and the caller is authorized, the API returns `200` with fields `id`, `status`, `total`, `currency`, and `items`. If not found, the API returns `404` with error fields `code` and `message`. `status` is the business status; `total` is the monetary amount calculated under the system's financial rules.

**Practice tasks:**

1. Write two HTTP tests for `200` and `404` responses, choosing distinct identifiers in `document(...)`.
2. For `200`, assert the HTTP status, media type, and key values; document all contract response fields.
3. For `404`, assert `code`/`message` matching the real error and generate separate snippets.
4. Add an `items=[]` case and verify the client receives **an empty array**, rather than an omitted field.
5. If the contract has an optional `note` field, design two cases—**with `note`** and **without `note`**—and decide whether `null` is valid.
6. Try adding `discountAmount` to the response without updating descriptors. Observe the strict field documentation error, then update the contract if the change is intentional.
7. Try modifying the `total` calculation while keeping the same JSON type. Explain why descriptors alone cannot protect the formula and add appropriate business tests.
8. Include snippets in an Asciidoctor page, add sections on status semantics, currency, errors, and access conditions; run the build from a clean output directory.

**Passing criteria:** every claim can be classified clearly as **observed data**, **a condition verified by assertions/descriptors**, or **a contract rule needing verification and additional tests**. The documentation never generalizes rules from a single sample response.

## 14. Takeaways

- An **actual response** describes the result of one request in a concrete test scenario; an **API contract** describes the set of behaviors and data clients are entitled to rely on.
- `http-response.adoc` is an observed example; `response-fields.adoc` is a description table from descriptors; **assertions** verify values and conditions chosen by the author.
- **Field type, presence, `null`, concrete values, and business meaning** are distinct properties that must be explained accurately.
- A single `200` test does not prove error responses, authorization rules, or all business states; dedicated test operations are needed.
- Spring REST Docs together with Asciidoctor/Markdown and CI regenerates grounded documentation from tests, yet **verifiability is only as strong as the test scope, descriptors, assertions, and accuracy of the documented business rules**.
