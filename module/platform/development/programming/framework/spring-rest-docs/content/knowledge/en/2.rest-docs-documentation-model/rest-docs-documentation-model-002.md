# Operation as the Unit Combining Calls, Snippets, and Descriptions

In **Spring REST Docs**, API documentation is generated from actually executed HTTP tests. The unit bridging tests and documentation is the **operation**: a single HTTP exchange with its corresponding request, response, and test context. Spring REST Docs uses the operation's data together with author-declared descriptions to generate **snippets**; Asciidoctor documentation or a Markdown compilation process then pulls those snippets into a complete API page.

This topic belongs to the **Documentation Model** chapter of the `SPRING_REST_DOCS` module. The broader goal of the module is to create verifiable REST API documentation from MockMvc, WebTestClient, or REST Assured, generate snippets for requests, responses, payloads, parameters, and headers, and wire that process into the build and CI. This lesson focuses on **the link from one operation → snippets → explanations for API integrators**.

## 1. Learning Outcomes

After completing this lesson, you can:

1. Explain why a route is not synonymous with a documentation operation.
2. Distinguish between the request/response captured from a test, author-supplied descriptions, and generated snippets.
3. Use `document("operation-id", ...)` to bind descriptions to the exact HTTP interaction.
4. Identify which snippets are needed for an endpoint and include them in Asciidoctor documentation.
5. Organize multiple operations for success and error cases and ensure CI can regenerate the documentation.

## 2. An Operation Connects Three Layers

To visualize this, consider an endpoint that reads an order:

```http
GET /api/orders/101?includeItems=true HTTP/1.1
Accept: application/json
```

A single request execution might receive:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: req-docs-001

{
  "id": 101,
  "status": "CONFIRMED",
  "total": 150000,
  "items": [
    {"sku": "BK-01", "quantity": 2}
  ]
}
```

To turn this exchange into useful documentation, three layers of information are needed:

| Layer | Source of information | Role | Example |
| --- | --- | --- | --- |
| **Tested call** | Request and response in an HTTP test | Provides observed facts about method, URI, headers, payload, status | `GET /api/orders/101` receives `200 OK` |
| **Contract description** | Test author declares descriptors | Explains the meaning of parameters, fields, headers; detects mismatches between payload and descriptions | `orderId` is the order ID, `items[].sku` is the item SKU |
| **Documentation snippets** | Spring REST Docs processes the operation and descriptors | Outputs documentation fragments for a single exchange | `http-request.adoc`, `response-fields.adoc`, `path-parameters.adoc` |

A documented test can be illustrated as:

```text
HTTP Test
   ├── sends request ───────────┐
   ├── receives response ───────┤
   ├── behavior assertions      │
   └── document("orders-get", …)│
                                ▼
                         Recorded Operation
                         + descriptors
                                │
                                ▼
                  generated-snippets/orders-get/
                    ├── http-request.adoc
                    ├── http-response.adoc
                    ├── path-parameters.adoc
                    ├── query-parameters.adoc
                    ├── request-headers.adoc
                    ├── response-headers.adoc
                    └── response-fields.adoc
                                │
                                ▼
                       API Documentation Page
                    (Asciidoctor or Markdown)
```

Key point to remember: **an operation is not a single snippet file**. One operation can generate multiple snippets, each reflecting a different view. And **snippets do not replace explanatory prose**: a field table tells you what `items[].sku` is, while the documentation page should still explain when an order exists, authorization conditions, possible return statuses, and business rules.

### 2.1. How Does an Operation Differ from a Route, an HTTP Method, and a Test Case?

- **Route**: a path pattern, such as `/api/orders/{orderId}`.
- **HTTP method + route**: the kind of action that can be performed, such as `GET /api/orders/{orderId}`.
- **Test case**: a program that sets up data, sends a request, checks the response, and may call `document(...)`.
- **Documented operation**: the data of **a single request/response** recorded by a test, placed under a snippet identifier, and explained with descriptors.

If two tests both call `GET /api/orders/{orderId}`—one receiving `200` and the other receiving `404`—they are two separate documented scenarios. Conversely, if a single test calls the same endpoint multiple times, each call is recorded as a separate interaction; you should not assume that “one test always corresponds to one operation”.

### 2.2. Role of the Operation Identifier

When you write:

```java
.andDo(document("orders-get", /* descriptors */))
```

`orders-get` is the identifier used to group the snippets for this interaction. The output path typically looks like:

```text
build/generated-snippets/orders-get/      (Gradle)
target/generated-snippets/orders-get/     (Maven)
```

This is **not a route name** automatically generated by the application. The test author chooses an identifier that is stable and meaningful. You should use scenario-distinguishing names such as `orders-get-success`, `orders-get-not-found`, `orders-create-valid`, and `orders-create-invalid` when multiple outcomes need to be documented.

Avoid having multiple independent tests running in parallel write to the **same** identifier if they produce different content: files with the same name in the snippet directory risk overwriting each other and making documentation dependent on test execution order.

## 3. Where Are Descriptions Attached to an Operation?

Spring REST Docs can generate request/response snippets from recorded HTTP data, but it **cannot know on its own** what `orderId` means in the domain or which values the `status` field allows. The author supplies that information through the documentation descriptor API:

| Descriptor group | Common API | Generated snippet |
| --- | --- | --- |
| URI template variables | `pathParameters(parameterWithName(...))` | `path-parameters.adoc` |
| Query parameters | `queryParameters(parameterWithName(...))` | `query-parameters.adoc` |
| Request headers | `requestHeaders(headerWithName(...))` | `request-headers.adoc` |
| Response headers | `responseHeaders(headerWithName(...))` | `response-headers.adoc` |
| Request JSON fields | `requestFields(fieldWithPath(...))` | `request-fields.adoc` |
| Response JSON fields | `responseFields(fieldWithPath(...))` | `response-fields.adoc` |
| HTTP examples | Generated automatically from the operation on `document(...)` | `http-request.adoc`, `http-response.adoc` |
| Body, sample commands | Generated from the operation when applicable | `request-body.adoc`, `response-body.adoc`, `curl-request.adoc`, `httpie-request.adoc` |

A descriptor typically consists of a **name/path**, **data type** (where applicable), **description**, and attributes such as `optional()` or `ignored()`. For example:

```java
fieldWithPath("items[].sku")
    .type(JsonFieldType.STRING)
    .description("Product SKU for each line item")
```

The path `items[].sku` is a rule that selects a nested field inside each element of the `items` array; it is not a literal JSON property name. For some payloads, you also need to document the parent node, such as `items` with type `ARRAY`.

Descriptions in snippets must match the **actual request and response of the operation itself**. If the test does not send `X-Customer-Id`, do not declare a snippet describing that header as actually present in the operation, unless it fits the optional mechanism and an established contract.

## 4. End-to-End Example: An Order-Reading Operation with MockMvc

The example below uses JUnit 5, Spring MVC Test, and Spring REST Docs. The controller is defined directly in the test so readers can see all the data: order `101` has status `CONFIRMED`, a total amount, and one line item; any other ID returns `404`.

> In a real application, the controller usually fetches data from a service/repository. Fixtures, permissions, and test data must be controlled so every build yields consistent results.

### 4.1. Minimal Controller for the Example

```java
@RestController
class OrderController {

    @GetMapping(
        value = "/api/orders/{orderId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderView> getOrder(
            @PathVariable long orderId,
            @RequestParam(defaultValue = "false") boolean includeItems) {

        if (orderId != 101L) {
            return ResponseEntity.notFound().build();
        }

        List<OrderItem> items = includeItems
            ? List.of(new OrderItem("BK-01", 2))
            : List.of();

        OrderView body = new OrderView(
            101L, "CONFIRMED", new BigDecimal("150000"), items
        );

        return ResponseEntity.ok()
            .header("X-Request-Id", "req-docs-001")
            .body(body);
    }

    record OrderView(
        long id, String status, BigDecimal total, List<OrderItem> items
    ) {}

    record OrderItem(String sku, int quantity) {}
}
```

Most projects place `OrderController` and its DTOs in separate files. To use this example, you need the corresponding imports for `BigDecimal`, `List`, `MediaType`, `@RestController`, `@GetMapping`, `@PathVariable`, `@RequestParam`, and `ResponseEntity`. Java `record` DTOs suit Java 17 and above with a Spring/Jackson environment that supports records.

### 4.2. Test Combining Assertions and Descriptors

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new OrderController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getOrder_createsVerifiedSnippets() throws Exception {
        mockMvc.perform(
                get("/api/orders/{orderId}", 101L)
                    .queryParam("includeItems", "true")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.items[0].sku").value("BK-01"))
            .andDo(document("orders-get-success",
                pathParameters(
                    parameterWithName("orderId")
                        .description("ID of the order to retrieve")
                ),
                queryParameters(
                    parameterWithName("includeItems")
                        .description("Whether to return the line items")
                        .optional()
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Response format accepted by the client")
                ),
                responseHeaders(
                    headerWithName("X-Request-Id")
                        .description("Correlation ID for tracing the request")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Order ID"),
                    fieldWithPath("status")
                        .type(JsonFieldType.STRING)
                        .description("Status of the order"),
                    fieldWithPath("total")
                        .type(JsonFieldType.NUMBER)
                        .description("Total amount in the currency defined by the API"),
                    fieldWithPath("items")
                        .type(JsonFieldType.ARRAY)
                        .description("Line items, may be empty"),
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

Here, `get` must be imported from `org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get`. This builder preserves URI template information so `pathParameters(...)` can document `{orderId}`. Using a request builder that does not preserve the template can prevent the path parameter table from being generated as intended.

Key static imports:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Types such as `MockMvc`, `MockMvcBuilders`, `RestDocumentationExtension`, `RestDocumentationContextProvider`, and `JsonFieldType` must also be imported from their respective libraries. Tests using `RestDocumentationExtension` require the Spring REST Docs dependency and snippet output configuration in the project.

### 4.3. Analyzing the Exact Responsibility of Each Part

| Code in test | Effect | Consequence for documentation |
| --- | --- | --- |
| `perform(get(...))` | Sends a request using a URI template | Produces actual HTTP data for the operation |
| `queryParam("includeItems", "true")` | Determines which query parameter the request has | The request snippet will display that parameter |
| `andExpect(status().isOk())` | Verifies a successful response | Test fails if the status is wrong |
| `andExpect(jsonPath(...))` | Verifies critical business values | Test fails if JSON values are unexpected |
| `document("orders-get-success", ...)` | Attaches an identifier and descriptors to the interaction | Generates files in the `orders-get-success` directory |
| `responseFields(...)` | Describes the schema of the received JSON response | Generates the field table and validates descriptions against the payload |

Having only `andExpect(status().isOk())` is **not enough** to guarantee that `status` in JSON is `CONFIRMED`. And having only `responseFields(...)` does **not replace** assertions checking business values. The two mechanisms complement each other.

In the commonly used strict field-documentation mode, Spring REST Docs fails when the response has an undocumented field or when a field required to be documented is missing. Fields that are genuinely optional can be marked with `optional()`. When you only want to document part of a structure, `relaxedResponseFields(...)` is available, though that choice gives up catching newly added fields missing from documentation. For a public endpoint, you should document all fields belonging to the contract.

## 5. Same Route, Multiple Operations by Handling Scenario

An order not existing is a different scenario from reading an order successfully. Document it in a separate test:

```java
@Test
void getOrder_notFound() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 999L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isNotFound())
        .andDo(document("orders-get-not-found",
            pathParameters(
                parameterWithName("orderId")
                    .description("ID of the order to retrieve")
            )
        ));
}
```

With the sample controller, the `404` response has no JSON body. Therefore, this test does not declare `responseFields(...)` for a hypothetical error payload that does not yet exist. If the actual system returns a body such as:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
```

then the test and `responseFields(...)` of the error operation must describe **that exact** error schema, while asserting the status and key error code.

| Scenario | Identifier | Request | Result | What needs explanation |
| --- | --- | --- | --- | --- |
| Order exists | `orders-get-success` | `GET /api/orders/101?includeItems=true` | `200`, order JSON | Fields, `includeItems` option, headers |
| Order does not exist | `orders-get-not-found` | `GET /api/orders/999` | `404`, no body in example | Not-found condition |
| Not authorized to view | `orders-get-forbidden` (if supported by API) | `GET /api/orders/101` with insufficient-privilege identity | `403` per contract | Authorization condition, error format |

The third row illustrates an **operation to consider adding**, not yet implemented in the sample controller. Do not write it as a real response example until a running test exists and the contract is confirmed.

In documentation for a route, you can use one overview section and subsections presenting each scenario. Do not reuse the same `200` response block to illustrate a `404`.

## 6. How Are Snippets Generated from an Operation?

After tests finish, output typically resides at a path determined by the build tool, for example:

```text
build/generated-snippets/
├── orders-get-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   ├── httpie-request.adoc
│   ├── request-body.adoc
│   ├── response-body.adoc
│   ├── path-parameters.adoc
│   ├── query-parameters.adoc
│   ├── request-headers.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── orders-get-not-found/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    └── path-parameters.adoc
```

The actual filenames depend on the requested snippet types and the Spring REST Docs version/configuration. Files representing bodies may be empty if the operation has no body. Do not rely on every operation generating every parameter, field, and header table.

### 6.1. Snippets of Observed Data

`http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, and `httpie-request.adoc` are primarily used to provide **API call examples** for readers. Because the data comes from a tested operation, it reflects the host, port, query, headers, and body sent/received by the test.

For example, the `http-response.adoc` snippet of `orders-get-success` shows `200`, `X-Request-Id`, and the order JSON. A hand-written sentence like “the response contains the order status” cannot replace this evidence of the payload's actual shape.

### 6.2. Descriptor-Generated Snippets

`response-fields.adoc` does not simply copy JSON. It is a **descriptive table** of fields from `fieldWithPath(...)`, containing path, type, optionality, and explanation. Similarly, `path-parameters.adoc` describes `orderId`; `query-parameters.adoc` describes `includeItems`.

A field being present in the response is **not enough** for the field table to know how to name and explain it in domain terms. Conversely, a well-written descriptor that does not match the payload should be caught by tests. That is why an operation forms the bridge between HTTP reality and readable documentation.

### 6.3. Templating to Standardize Across Operations

When there are many endpoints, you can configure default snippets or use helpers to build recurring descriptors (such as common errors, pagination, and correlation headers). The goal is to keep terminology and descriptions consistent.

However, avoid trying to reuse the exact `responseFields(...)` set of a success operation across all error operations: the response schema and the meaning of individual fields may differ. Reuse what is genuinely shared, and keep what differs specific to each scenario.

## 7. From Operation to Readable Documentation Page

Spring REST Docs generates snippets during the test step; a documentation page must **embed snippets into context**. AsciiDoc example:

```asciidoc
[[orders-get]]
=== Look up an order

Call the API to retrieve an order by its ID. If not found, the API returns 404.
The includeItems parameter indicates whether to include the list of line items.

==== Success — HTTP 200

.Request
include::{snippets}/orders-get-success/http-request.adoc[]

.Path parameters
include::{snippets}/orders-get-success/path-parameters.adoc[]

.Query parameters
include::{snippets}/orders-get-success/query-parameters.adoc[]

.Request headers
include::{snippets}/orders-get-success/request-headers.adoc[]

.Response
include::{snippets}/orders-get-success/http-response.adoc[]

.Response headers
include::{snippets}/orders-get-success/response-headers.adoc[]

.Response fields
include::{snippets}/orders-get-success/response-fields.adoc[]

==== Not found — HTTP 404

.Request
include::{snippets}/orders-get-not-found/http-request.adoc[]

.Response
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

Here `{snippets}` is an attribute set by the build to point to the generated snippets directory. When two includes reference `orders-get-success`, they display two views of **the same operation**.

If the project outputs Markdown documentation, you need a conversion or snippet-injection step compatible with your Markdown tooling. The `include::{snippets}/...[]` directive is Asciidoctor syntax and is not supported by default in all Markdown compilers.

### 7.1. Which Descriptions Must Be Written in Prose?

Snippets list observed data and field tables, while hand-written prose should answer things beyond a sample request:

- **When it is called:** what behavior is the endpoint for, and who is allowed to access it?
- **Conditions and constraints:** what constitutes a valid `orderId`, and what is the default of `includeItems`?
- **Business meaning:** `status` is a state in the order lifecycle; which currency and rounding rules does `total` use?
- **Possible outcomes:** which cases return `200`, `404`, `403`; is there an error body?
- **Relationships to other APIs:** if creating/updating an order is needed, which operation should the reader navigate to?

The test in our example already has a default `includeItems=false` on the controller; the documentation must state this default explicitly because a test running only `includeItems=true` cannot reveal all cases on its own. If the actual currency or format is not yet determined, the author must verify the contract before publishing it as a public commitment.

## 8. Connecting Operations to Build and CI

A typical pipeline has the following dependency chain:

```text
Compile application and tests
         │
         ▼
Run HTTP tests (MockMvc/WebTestClient/REST Assured)
         │
         ├── If assertion or snippet validation fails → build fails
         │
         ▼
Generate generated-snippets/<operation-id>/
         │
         ▼
Compile AsciiDoc or process Markdown
         │
         ├── If an include file is missing → compilation or check error
         │
         ▼
Output HTML/PDF/documentation pages for publishing
```

For Gradle, the documentation compilation task must depend on the `test` task (or whichever test task generates snippets) and take the snippet directory as input. With Maven, connect the test phase and documentation plugin in the appropriate lifecycle. In CI, run from a clean environment and verify both tests and the compilation step, preventing leftover snippets from an older build from masking a test that is no longer executed.

A build pipeline does not replace business contract review. It ensures examples and descriptor tables are generated from current tests, while coverage depends on which operations are included in the test suite.

### 8.1. Data to Normalize Before Publishing

Test requests and responses may contain internal hostnames, random ports, tokens, cookies, emails, or real identifying information. Because that data lives inside the operation, documentation generation could inadvertently expose it on public pages.

Spring REST Docs supports preprocessors to present examples more consistently, such as `preprocessRequest(...)`, `preprocessResponse(...)`, and `prettyPrint()`; data replacement/removal mechanisms can be applied when preparing snippets. Use safe dummy fixtures, normalize URIs, and strip or mask sensitive data before publishing. Any display adjustment for documentation must be intentional to avoid making examples misrepresent the real contract.

## 9. Common Mistakes and How to Spot Them

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Treating route `GET /orders/{id}` as enough for all cases | Not distinguishing `200`, `404`, `403` scenarios | Create separate test operations and identifiers for key behaviors |
| `path-parameters.adoc` fails or misses `orderId` | Request builder does not preserve URI template | Use `RestDocumentationRequestBuilders` with the `{orderId}` template |
| HTTP response has a new field but docs stay unchanged | Using relaxed descriptors or skipping validation | Use strict descriptors for contract fields; update descriptors alongside code |
| Documentation has a field table but does not explain when errors happen | Only inserting snippets, missing contextual prose | Clearly write out rules and conditions for each operation |
| `response-fields.adoc` does not appear | Test does not call `responseFields(...)` or did not run | Add descriptors to the right `document(...)` call and check the test task |
| Snippet directory has mixed results from two tests | Two tests share an identifier while producing different content | Give distinct names and avoid collisions under parallel execution |
| Documentation build succeeds even though new test fails | Page uses leftover snippets from a previous build | Force the compilation task to depend on tests and verify on a clean build |
| Examples show real tokens or internal hosts | Request/response data inserted verbatim | Use safe fixtures, normalize, and filter snippet data |
| Field marked `optional()` just to make the test pass | Description does not reflect real API constraints | Mark optional only when the field can genuinely be absent |

Another common mistake is confusing a **request parameter** with a **JSON field**. `includeItems` in `?includeItems=true` belongs in `queryParameters(...)`, whereas `items[].sku` in the JSON body belongs in `responseFields(...)`. Each kind is documented with its corresponding API and snippet; using the wrong one causes the documentation to misrepresent the HTTP structure.

## 10. Hands-On Exercise

Suppose you need to write documentation for `GET /api/orders/{orderId}` and `POST /api/orders`:

1. **Choose operations:** list at least two outcomes of `GET` (`200` and `404`) and two meaningful outcomes of `POST` (for example `201` and `400`).
2. **Name identifiers:** use distinct, scenario-clear names to avoid overwriting snippets.
3. **Write tests:** for each operation, set up deterministic data, send the request, and assert the status and key business values.
4. **Attach descriptors:** use `pathParameters`, `queryParameters`, `requestHeaders`, `requestFields`, `responseHeaders`, and `responseFields` when the corresponding element is present and part of the contract.
5. **Compile documentation:** organize the page by endpoint and scenario; include the appropriate snippets; add prose explanations.
6. **Run a clean build:** confirm the snippets are present, the documentation page builds, and an out-of-contract change causes either tests or snippet generation to fail.

**Check question:** if the `response-fields` table accurately documents two fields, but the actual JSON response adds a third public field, what should happen? With strict documentation, the test must catch the undocumented field. After verifying that this is an intentional contract change, update both the relevant assertions and descriptors, then regenerate the documentation.

## 11. Summary

- An **operation** is a tested and recorded HTTP exchange; an **identifier** binds that operation to a stable snippet directory.
- One operation can generate multiple **snippets**: request, response, parameters, headers, payload. **Descriptors** add meaning and help verify alignment between data and documentation.
- A **documentation page** combines snippets with business explanations, applicability conditions, and a list of success/error scenarios.
- Connecting tests → snippets → Asciidoctor/Markdown → CI keeps documentation reproducible and verifiable, with confidence proportional to the scope of the tests written.
