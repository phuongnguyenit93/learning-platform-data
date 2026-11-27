# Contracts for Non-Existent Data and Invalid Requests

## 1. Why Write Contracts for Error Branches?

Suppose a web application calls `Order Service` to display an order. In the success case, the producer returns HTTP `200 OK` and JSON containing `orderId`, `status`, and `totalAmount`. If the order does not exist, the consumer needs to know to display "Order not found," letting the user return to the list or try another code. If an order creation request misses required information, the consumer needs to pinpoint which field to fix.

These two error behaviors are part of the **public interface**, not merely internal exception details. A change from HTTP `404` to `500`, from the `code` field to `errorCode`, or from a validation error list to a hard-to-parse string can break the consumer even if the producer's unit tests still pass.

**Spring Cloud Contract** turns expectations between producer and consumer into Groovy/YAML DSL. The tool generates producer-side tests, creates stubs for consumers to test with Stub Runner, and enables integrating those steps into CI. This lesson belongs to the **Statuses and Errors** chapter and focuses on:

- **Non-existent data:** A validly identified resource that cannot be found, typically described with HTTP `404 Not Found`.
- **Invalid requests:** A request whose syntax, parameters, or content do not satisfy the published interface, typically described with HTTP `400 Bad Request`; some APIs choose `422 Unprocessable Content` when content is syntactically valid but cannot be processed semantically.

After completing this lesson, you will be able to choose error branches to protect, define a stable **error response contract**, write HTTP contracts in Groovy/YAML, prepare producer verification, and distinguish the kinds of drift a contract test catches versus those requiring other tests.

> **Key message:** Do not only write contracts for `2xx`. Consumers frequently make critical decisions based on the **status, error code, and body structure** of `4xx` responses.

## 2. First, Distinguish "Does Not Exist" from "Invalid"

Consider two requests:

~~~http
GET /api/orders/ORD-404 HTTP/1.1
Accept: application/json
~~~

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": "",
  "items": [
    { "sku": "BOOK-1", "quantity": 1 }
  ]
}
~~~

The first request has a **valid** method and path, yet there is no order `ORD-404`. The second request has **syntactically** valid JSON, yet `customerId` is an empty string while the API requires a non-empty customer ID. They require **two separate scenarios**.

| Attribute | Non-Existent Data | Invalid Request |
| --- | --- | --- |
| Example | `GET /api/orders/ORD-404` | `POST /api/orders` with `customerId: ""` |
| Problem | Resource not found by identifier | Request violates acceptance rules |
| Illustrative status | `404 Not Found` | `400 Bad Request` |
| Application error code | `ORDER_NOT_FOUND` | `VALIDATION_FAILED` |
| Consumer handling | Show "not found", redirect, or prompt for another ID | Show input validation error, keep form data |
| Producer fixture | Requested resource **does not exist** | Request intentionally violates rules |
| Contract focus | Committed status, error code, resource/path | Status, error code, and invalid field details if used by consumer |

**Not every error corresponds to `400` or `404`.** An API may use `409 Conflict` when resource state disallows an operation, `401 Unauthorized` when valid authentication is missing, `403 Forbidden` when disallowed, or `422 Unprocessable Content` per published policy. Choose based on **HTTP semantics and the actual interface**, rather than changing status codes arbitrarily just to pass tests.

## 3. Design a Stable Error Envelope Before Writing DSL

A usable error body should have a structure stable enough for the consumer to **make decisions**. Here are two custom-designed example responses for `Order Service`:

**Order not found:**

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
~~~

**Invalid request:**

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "customerId",
      "code": "REQUIRED"
    }
  ]
}
~~~

Fields in the example:

| Field | JSON Type | Meaning |
| --- | --- | --- |
| `code` | String | Stable application error code for consumer branching |
| `message` | String | Explanatory text for users or operators; may change by locale |
| `errors` | Array | Validation violations processable per field |
| `errors[].field` | String | Name of the invalid request field |
| `errors[].code` | String | Stable validation error code, e.g., `REQUIRED` or `INVALID_FORMAT` |

This is an **illustrative schema chosen by the project team**; Spring Cloud Contract does not enforce names like `code`, `message`, or `errors`. If the project uses Spring `ProblemDetail`/Problem Details per RFC 9457, write contracts matching **that schema** and the appropriate media type rather than mixing two response formats into an inconsistent contract.

### 3.1. Which Fields Does the Consumer Actually Need?

Not every field visible in JSON needs a strict constraint:

- If the consumer branches on `code: ORDER_NOT_FOUND`, keep that error code stable.
- If the consumer displays its own localized message, the English text `Order not found` may only be descriptive data and **should not be assumed to be an immutable commitment**.
- If the UI highlights the `customerId` input box, ensure the validation field path and name still satisfy the form binding mechanism.
- If `requestId` or a timestamp is server-generated, validate its format rather than pinning an arbitrary ID or timestamp.
- Avoid exposing stack traces, SQL errors, database details, or sensitive data in public error APIs.

A good error structure is usually consistent across endpoints, yet each interaction contract must still describe the **status and the fields the consumer uses for that specific scenario**.

## 4. Groovy Contract for Non-Existent Data: HTTP 404

Suppose the consumer calls the endpoint:

~~~http
GET /api/orders/ORD-404 HTTP/1.1
Accept: application/json
~~~

The producer commits to returning `404` with `ORDER_NOT_FOUND`. Create an illustrative file:

~~~text
src/test/resources/contracts/orders/get_order_not_found.groovy
~~~

Groovy DSL content:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')
    description('Order not found for the requested code')

    request {
        method GET()
        urlPath('/api/orders/ORD-404')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order not found'
        )
    }
}
~~~

**Meaning of the contract:**

1. `request.method` and `urlPath` identify the request sent by the consumer; this is not a mistyped route case.
2. `NOT_FOUND()` represents HTTP status `404`.
3. `Content-Type: application/json` ensures the producer advertises the agreed response format.
4. `body.code` is the error code allowing structured consumer handling.
5. `body.message` appears in the sample because the illustrative API committed to it; if exact wording is unnecessary, relax that constraint appropriately in real implementations.

If the producer returns `200` with body `{"code":"ORDER_NOT_FOUND"}` instead of `404`, the generated contract test must catch the wrong **status**. If the producer returns `404` but omits `code`, the test must also catch the discrepancy in the **response body**.

### 4.1. Naming for Easy Failure Investigation

The name `get_order_not_found` expresses:

- Behavior: `get_order`.
- Scenario: `not_found`.
- Do not tie names to internal Java classes, because contracts protect the HTTP interface rather than controller method names.

Files can reside under an `orders/` group or consumer-specific directories; what matters is that the plugin knows the contract source path and CI executes the generated tests.

## 5. The Same 404 Contract in YAML DSL

If the project chooses YAML DSL, write an equivalent contract:

~~~yaml
name: get_order_not_found
description: Order not found for the requested code
request:
  method: GET
  urlPath: /api/orders/ORD-404
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
    message: Order not found
~~~

Comparing Groovy and YAML:

| Element | Groovy DSL | YAML DSL |
| --- | --- | --- |
| Request method | `method GET()` | `method: GET` |
| Request path | `urlPath('/api/orders/ORD-404')` | `urlPath: /api/orders/ORD-404` |
| Error status | `status NOT_FOUND()` | `status: 404` |
| Media type | `contentType(applicationJson())` | `Content-Type: application/json` |
| Error code | `body(code: 'ORDER_NOT_FOUND')` | `body:` then `code: ORDER_NOT_FOUND` |

Do not enable both a Groovy file and a YAML file with the same name/behavior in the same contract sources just "to be sure." That can produce duplicate mappings or generated tests. For a real project, pick one format or manage overlapping scenarios intentionally.

## 6. Groovy Contract for Invalid Requests: HTTP 400

Suppose the order creation API requires `customerId` to be a non-empty String. The consumer sends **syntactically valid JSON that fails validation**:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "customerId": "",
  "items": [
    { "sku": "BOOK-1", "quantity": 1 }
  ]
}
~~~

The producer commits to returning `400 Bad Request` and an error with code `VALIDATION_FAILED`, specifying `customerId`. Write the contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_missing_customer_id')
    description('Reject order with empty customerId')

    request {
        method POST()
        urlPath('/api/orders')

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            customerId: '',
            items: [
                [sku: 'BOOK-1', quantity: 1]
            ]
        )
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'VALIDATION_FAILED',
            errors: [
                [
                    field: 'customerId',
                    code: 'REQUIRED'
                ]
            ]
        )
    }
}
~~~

### 6.1. Points to Verify

- `request.body.customerId` is an empty string, not a missing field or `null` value.
- `items` is a **JSON array** containing an object, declared as a list containing a map.
- `status BAD_REQUEST()` corresponds to HTTP `400`.
- `errors` is a list: the consumer can iterate and display errors for each field.
- `errors[0].field` and `errors[0].code` are what the UI can use to highlight the input field.

Do not describe a valid order in this contract and just swap `status` to `400`: the test would fail to prove the producer rejects **the right kind of invalid request**.

### 6.2. "Missing Field" Error vs. "Empty String" Error

Three different requests:

~~~json
{"items":[{"sku":"BOOK-1","quantity":1}]}
~~~

~~~json
{"customerId":null,"items":[{"sku":"BOOK-1","quantity":1}]}
~~~

~~~json
{"customerId":"","items":[{"sku":"BOOK-1","quantity":1}]}
~~~

If the API returns the same `REQUIRED` code for all three, you can write separate contracts for the scenarios the consumer genuinely relies on. However, never assume every validation framework returns **the exact same response** for missing fields, nulls, and empty strings. Actual behavior depends on DTOs, validation annotations, exception mapping, and the producer's error policy.

## 7. The Same 400 Contract in YAML DSL

YAML representation of the empty `customerId` scenario:

~~~yaml
name: create_order_missing_customer_id
description: Reject order with empty customerId
request:
  method: POST
  urlPath: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customerId: ""
    items:
      - sku: BOOK-1
        quantity: 1
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: VALIDATION_FAILED
    errors:
      - field: customerId
        code: REQUIRED
~~~

Note the representation:

- `customerId: ""` is an intentional empty String; omitting quotes and value could cause YAML to interpret it as null.
- Both `items` and `errors` are arrays. The `-` marks elements of a YAML sequence.
- Do not replace `errors` with a single object if the client deserializes `List<ValidationError>`.
- Strings that look like booleans, numbers, or null should be quoted when you need to preserve **String type**.

If `errors` has multiple items, error ordering may depend on the framework's validation sequence. Avoid enforcing a specific order unless the API actually guarantees that order; if needed, choose appropriate matchers/tests to avoid flaky tests.

## 8. Malformed JSON Request: Another 400 Case

A validation violation differs from a request that **cannot be parsed**. For example:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId": "CUS-7",
~~~

The body is not valid JSON because it lacks a closing brace. The producer may reject it at the HTTP message converter layer before ever reaching the controller or Bean Validation.

If the consumer needs to distinguish syntax errors, you can design the response:

~~~json
{
  "code": "MALFORMED_JSON"
}
~~~

An illustrative contract in Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_malformed_json')

    request {
        method POST()
        urlPath('/api/orders')

        headers {
            contentType(applicationJson())
        }

        // Intentionally malformed JSON body string
        body('{"customerId": "CUS-7",')
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'MALFORMED_JSON'
        )
    }
}
~~~

**Important condition:** This contract will only pass if the producer **actually implements JSON parse error handling** and returns the exact `MALFORMED_JSON` schema. If Spring Boot returns a different default error structure, do not assume the snippet above will pass immediately. Configure exception handling per the agreed interface or align the contract with the actual published behavior.

Distinguish clearly in your design:

| Error | Example | Where Does It Happen? |
| --- | --- | --- |
| Malformed JSON | `{"customerId": "CUS-7",` | HTTP parser/message converter |
| Field type mismatch | `{"quantity": "abc"}` when DTO expects a number | Deserialization/type conversion |
| Validation violation | `{"customerId": ""}` when empty is disallowed | Bean Validation or business logic |
| Non-existent resource | `GET /api/orders/ORD-404` | Resource lookup |
| State conflict | Cancelling a completed order | Domain/business policy, possibly `409` |

The same HTTP status can serve multiple error kinds. **Application error codes** help the consumer distinguish them when the business requires it.

## 9. Choosing 400, 404, 409, or 422 for the Right Purpose

Do not pick status codes out of habit without agreeing on semantics.

| Status | General Meaning | Example |
| --- | --- | --- |
| `400 Bad Request` | Server cannot/will not process request due to a perceived client error, such as invalid syntax or parameters | Malformed JSON, empty required field per API policy |
| `404 Not Found` | Server cannot find a current representation of the target resource or is unwilling to disclose its existence | Order with valid ID that does not exist |
| `409 Conflict` | Request conflicts with the current state of the target resource | Concurrent updates on same version, state disallows edit |
| `422 Unprocessable Content` | Content has an understood media type and syntax but cannot be processed per its instructions | API chooses `422` for certain semantic/validation errors |
| `401 Unauthorized` | Request lacks valid authentication credentials | Missing or invalid credentials |
| `403 Forbidden` | Server understands the request but refuses to authorize it | Account lacks permission for the operation |
| `500 Internal Server Error` | Server-side failure, not a normal way to represent invalid client input | Infrastructure failure/unhandled bug |

**Important:** There is no hard rule that every validation error must be `422` or every invalid request must be `400`. Projects must pick a consistent policy, publish it to consumers, and encode the corresponding status in contracts.

For resources belonging to another tenant, security policy might decide to **return `404` to avoid disclosing existence** instead of `403`. Contracts must be designed alongside authentication/authorization policies rather than forcing every "resource exists but unauthorized" case to `403`.

### 9.1. 404 Due to Missing Route vs. 404 Due to Missing Resource

If `GET /api/orders/ORD-404` routes properly to the controller yet finds no record, that is a **non-existent data** error.

If the consumer mistakenly calls `GET /api/orderz/ORD-123`, the `404` may be due to a **missing endpoint**. Both scenarios can produce `404` yet **do not necessarily share the same JSON error envelope**, because route error handling and domain error handling may be two different flows in Spring MVC.

Contracts for non-existent resources should use a **valid path** and a fixture ensuring the resource genuinely does not exist. Do not mistype a path and think you are verifying "not found" business logic.

## 10. If Using Problem Details Instead of a Custom Error Envelope

The Spring ecosystem supports the **Problem Details** response format (RFC 9457; superseding RFC 7807), for example:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order matches the supplied identifier",
  "instance": "/api/orders/ORD-404"
}
~~~

Common fields include `type`, `title`, `status`, `detail`, and `instance`. APIs may add extension members per organizational conventions.

With this approach, the contract must use `application/problem+json` if that is the media type published by the producer:

~~~groovy
response {
    status NOT_FOUND()
    headers {
        header('Content-Type', 'application/problem+json')
    }
    body(
        type: 'https://api.example.test/problems/order-not-found',
        title: 'Order not found',
        status: 404,
        detail: 'No order matches the supplied identifier',
        instance: '/api/orders/ORD-404'
    )
}
~~~

**This is an alternative option**, not a mandatory Spring Cloud Contract body format. The main examples in this lesson use the `code/errors` schema to make it easier to illustrate how consumers handle forms. When choosing Problem Details, agree on which extension field or `type` URI serves as the **machine-readable error code**.

If `detail` is localized or embeds changing IDs, consider using a matcher instead of pinning the entire sentence. Avoid coupling to message wording when the consumer only truly needs a stable error code.

## 11. What Must the Producer Do for Generated Tests to Be Meaningful?

Spring Cloud Contract can generate tests from DSL, yet **it does not automatically create exception-handling behavior** for the application. The producer must genuinely return the status/headers/body stated in the contract.

A simple handling flow:

~~~mermaid
flowchart TD
    R["HTTP request"] --> V{"Request valid?"}
    V -- "No" --> B["400 + VALIDATION_FAILED"]
    V -- "Yes" --> L{"Resource exists?"}
    L -- "No" --> N["404 + ORDER_NOT_FOUND"]
    L -- "Yes" --> S["2xx + success data"]
    B --> C["Contract test verifies status + JSON body"]
    N --> C
    S --> C
~~~

This diagram is conceptual. For `POST /api/orders`, there may be no resource lookup step; for `GET` with a path ID, looking up data is more typical. **Do not force the exact same processing chain onto every endpoint.**

### 11.1. Spring MVC Applications Need a Standardized Error Mechanism

A typical implementation may include:

- Request DTOs annotated with `@Valid` and constraints like `@NotBlank`.
- Controllers delegating business operations to services.
- Services throwing domain exceptions, such as `OrderNotFoundException`, when a lookup finds no data.
- `@RestControllerAdvice` translating meaningful exceptions into committed HTTP responses.
- Customizing Spring's parse/body or validation error handling when the API wants a unified error envelope.

Conceptual example of a domain exception handler:

~~~java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> onNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(Map.of(
                    "code", "ORDER_NOT_FOUND",
                    "message", "Order not found"
                ));
    }
}
~~~

This example assumes the application defines `OrderNotFoundException` and imports the right Spring/Java types. It **only illustrates the 404 branch**. For the `400` contract above to pass, you also need a handler or response mapping for validation errors returning `VALIDATION_FAILED` along with `errors[]`. Spring Boot does not use a custom error body identical to the lesson examples by default.

### 11.2. Validation Handling Mechanism

An illustrative DTO:

~~~java
record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderItem> items
) {}

record CreateOrderItem(
    @NotBlank String sku,
    @Positive int quantity
) {}
~~~

The controller must trigger validation where requests are received, for example:

~~~java
@PostMapping("/api/orders")
ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest request) {
    // Execute business logic without bypassing validation
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
~~~

When `customerId` is empty, Bean Validation may produce a `NotBlank` error. If the API wants to translate that into code `REQUIRED`, the producer needs a step **mapping internal validation codes to public codes**. Do not assume the `NotBlank` annotation name automatically turns into `REQUIRED` in the JSON response.

If validation happens in the service layer instead of the controller, the way exceptions are thrown and handled will differ. Contract expectations must align with the **final HTTP response** received by the consumer.

## 12. Configuring the Base Test Class and Fixtures for Both Error Branches

Generated producer tests must run with **reproducible** state, independent of random data.

For the `get_order_not_found` contract:

- The controller must exist at route `GET /api/orders/{id}`.
- Code `ORD-404` must be treated as **non-existent** by the test system.
- The exception handler must return `404` with the agreed error envelope.
- If security is enabled, the test request must go through the appropriate authentication policy or set up an authorized principal.

For the `create_order_missing_customer_id` contract:

- Request JSON must parse into the input object.
- The empty `customerId` constraint must be triggered.
- The handler must return `400`, code `VALIDATION_FAILED`, and an `errors[]` entry reflecting `customerId`.
- The controller must not accidentally accept the request by bypassing validation in a test slice.

### 12.1. Base Class Skeleton Example with MockMvc

In a Spring MVC project using JUnit 5, the base class might start like this:

~~~java
@WebMvcTest(OrderController.class)
@Import(ApiErrorHandler.class)
abstract class ContractVerifierBase {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderQuery orderQuery;

    @BeforeEach
    void setUp() {
        given(orderQuery.findById("ORD-404"))
            .willReturn(Optional.empty());

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

This is an **illustrative skeleton**, not a standalone Java class you can paste into any project without adding packages/imports and application classes. It assumes `OrderQuery.findById` returns `Optional`, the controller converts `Optional.empty()` into `OrderNotFoundException`, and `ApiErrorHandler` handles the exception. Using `@MockitoBean` applies to Spring Framework 6.2+/compatible Spring Boot versions; older projects may need `@MockBean`. Spring Boot, Spring Cloud, and Spring Cloud Contract versions must be compatible with each other.

For the `400` branch relying on `@Valid`, a `@WebMvcTest` properly configured with the controller, validator, and exception handler can verify the full MVC pipeline. If unit tests mock the response directly and bypass the real controller/validation, assess the confidence level: tests might pass without proving the middleware handles invalid requests properly.

## 13. What Should Tests Protect in Error Responses?

### 13.1. Status and Error Code Are Two Independent Layers

A contract should not check only the error code in JSON:

~~~json
{"code": "ORDER_NOT_FOUND"}
~~~

If the producer returns that response with `200`, the client might take the success branch. Therefore, the HTTP status must be verified independently.

Conversely, asserting only `404` without `code` lets the producer silently change the error schema, breaking client body parsing.

### 13.2. Should Exact Message Text Be Checked?

An error code may be fixed while the message is localized:

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng"
}
~~~

If the consumer displays `message` verbatim per the contract, verify its presence/type and language policy. If the consumer uses `code` to display its own translations, pinning every word of `message` creates overly brittle tests.

You can relax the constraint using a matcher. For example:

~~~groovy
response {
    status NOT_FOUND()
    headers {
        contentType(applicationJson())
    }

    body(
        code: 'ORDER_NOT_FOUND',
        message: 'Order not found'
    )

    bodyMatchers {
        jsonPath('$.message', byType())
    }
}
~~~

In this example, `message` is verified **to be a String** rather than forced to equal a specific sentence, while `code` retains a fixed value. However, if the contract truly commits to verbatim wording, `byType()` is too loose; choose matchers based on consumer needs.

### 13.3. Validation Error Lists and Element Ordering

Suppose a request fails on both `customerId` and `items[0].quantity`. The response might contain:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerId", "code": "REQUIRED"},
    {"field": "items[0].quantity", "code": "POSITIVE"}
  ]
}
~~~

If error order is **not guaranteed by the API**, the producer could return the two elements in a different order. A contract that locks the entire list order may fail even though the consumer handles it fine.

Strategy:

1. For initial lessons, write **one simple error per contract**, such as only an empty `customerId`.
2. If the consumer needs to display multiple errors, design array contracts around key properties; understand your tool version's matcher/list semantics.
3. Add integration tests checking the **set of fields/codes** regardless of order if that is the true commitment.
4. Avoid overly broad regexes that lose the ability to detect wrong error fields/codes.

## 14. How Does Stub Runner Help Consumers Test Error Branches?

Stubs generated from contracts help consumers test behavior without running the real producer. With the two example contracts, Stub Runner can serve these interactions:

| Request from Consumer | Stub per Contract | Consumer Should Handle |
| --- | --- | --- |
| `GET /api/orders/ORD-404` | `404` + `ORDER_NOT_FOUND` | Show not-found state |
| `POST /api/orders` with `customerId: ""` matching matcher | `400` + `VALIDATION_FAILED` | Attach error to form |
| Request matching no stub | No response per defined contracts | This is a matching error; do not treat it as the described 404/400 business error |

**Important:** A `404` because **WireMock found no matching mapping** is not equivalent to a `404` with `ORDER_NOT_FOUND` JSON intentionally described by the contract. Consumer tests should assert **both status and error body** rather than just `404`, so an unmatched stub is not mistaken for a valid "not found" response.

When a request uses headers or a body different from the contract, the stub might fail to match. Always inspect `request` matcher conditions and actual stub output before concluding the client handles errors properly.

### 14.1. Verify Consumer Handling, Not Just Receiving the Response

A meaningful consumer test must assert the outcome:

- For `ORDER_NOT_FOUND`, the UI displays a "not found" state or the calling service stops processing the order.
- For `VALIDATION_FAILED`, the form shows the error on `customerId` and does not navigate to success.
- For other errors, the consumer neither swallows exceptions nor treats them as success.

Stubs only simulate communication; **consumer tests** must verify that consumer code reacts properly to those responses.

## 15. Putting Error Contracts into CI

A typical flow:

~~~mermaid
flowchart TD
    A["Contracts: 404 and 400"] --> B["Generate producer tests"]
    B --> C["Run tests against producer"]
    C --> D{"Status, headers, body match?"}
    D -- "No" --> E["Block merge or release"]
    D -- "Yes" --> F["Create versioned stub artifact"]
    F --> G["Consumer CI runs Stub Runner"]
    G --> H["Verify not-found and invalid-input branches"]
~~~

Example Maven command for a project already configured with the verifier plugin and base test class:

~~~bash
./mvnw -B clean verify
~~~

Or with Gradle plugin and corresponding test task:

~~~bash
./gradlew clean build
~~~

These commands are illustrative only; **contracts are not automatically tested** if the build lacks the plugin/dependencies, contract sources are misconfigured, or generated tests are skipped.

### 15.1. What CI Should Guarantee

- Groovy/YAML contracts and related fixtures are tracked in source control.
- Generated producer tests exist for both **success paths** and **error branches the consumer actually relies on**.
- Tests are executed, not just generated or compiled.
- Data/setup ensures `ORD-404` genuinely does not exist and empty `customerId` is genuinely rejected.
- Published error schemas are not silently altered in commits.
- Stubs from the verified producer are published with appropriate versions.
- Consumer CI asserts status and error code/body; unmatched WireMock requests are never treated as valid business errors.
- Authentication, authorization, performance, retries, or real gateway behavior are tested at their appropriate layers.

### 15.2. Which Breaking Changes Can Error Contracts Catch?

| Producer Change | Consumer Impact | How Contract Should React |
| --- | --- | --- |
| `404` changed to `200` when resource missing | Consumer may treat error as success | Generated test fails due to wrong status |
| `400` changed to `500` on invalid input | Consumer may wrongly retry or show system error | Generated test fails due to wrong status |
| `ORDER_NOT_FOUND` changed to `NOT_FOUND` | Consumer branching on old code may break | Test fails if code is constrained |
| `errors` changed from array to String | Consumer cannot read per field | Test fails due to structural mismatch |
| Only `message` wording changed | Likely compatible if client ignores wording | Pick appropriate matcher to avoid false failures |
| Added `traceId` metadata | Usually compatible if consumer ignores unknown fields | No need to lock every field, depending on consumer parser |

**Do not edit a contract just to turn the build green** after changing the producer. First identify which consumers depend on it and whether compatibility, migration, or a new API version is needed.

## 16. Common Mistakes When Writing Contracts for 404/400

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using a non-existent route to "test resource 404" | Fails to test real resource lookup | Use valid route and fixture without record |
| Asserting only `404`, omitting error body | Misses changes to `code` used by consumer | Assert status, media type, and key fields |
| Asserting only error body, omitting status | Producer might return `200` with error JSON | Always constrain the proper status |
| Assuming Spring Boot returns `VALIDATION_FAILED` automatically | Generated test fails against default error response | Configure exception handler/schema or align API contract |
| Treating JSON parse errors and Bean Validation as identical | Errors misclassified, hard to handle | Split contracts by input error type consumer distinguishes |
| Failing to enable `@Valid` | Invalid requests accepted in tests | Ensure MVC validation is active |
| Using `@WebMvcTest` while forgetting `@RestControllerAdvice` | Gets default error response differing from contract | Import/configure the right advice |
| Using `errors` as object when consumer expects array | Form error decoding fails | Keep list schema consistent |
| Overly broad matcher on `code` | Misses error code changes | Match exact business code |
| Unnecessarily pinning verbatim message wording | Translation tweaks fail tests | Assert type/presence as committed |
| Dumping every error into `500` | Consumer does not know how to fix request | Classify errors per HTTP policy |
| Treating unmatched stub `404` as valid not-found | Consumer test passes falsely | Assert error body and verify mapping |
| Test data relying on another environment's database | Flaky tests | Use controlled fixtures, mocks, or test database |
| Returning stack traces/SQL in error body | Leaks internal details | Standardize public responses, log details server-side |

## 17. Hands-On Exercise: Catalog Service and Two Failure Scenarios

Suppose producer `Catalog Service` provides:

1. `GET /api/products/{id}` to look up products.
2. `POST /api/products` to create a new product.

The consumer expects:

- When product `P-404` does not exist: receive `404` with `code: PRODUCT_NOT_FOUND`.
- When creating a product with empty `name`: receive `400` with `code: VALIDATION_FAILED` and error `field: name`, `code: REQUIRED`.

### 17.1. Tasks

1. Write a Groovy contract named `get_product_not_found` for `GET /api/products/P-404`.
2. Write a YAML contract named `create_product_missing_name` for `POST /api/products` with JSON `{"name":"","price":350000}`.
3. Set `Content-Type: application/json` in error responses that return JSON.
4. Prepare producer test fixtures so `P-404` does not exist and validation catches empty `name`.
5. Intentionally change the error code or status in the producer and observe producer verification fail.
6. Use Stub Runner to verify the consumer displays the right not-found and validation branches.
7. Explain why a stub returning `404` **without a `PRODUCT_NOT_FOUND` body** is insufficient proof that the not-found branch was tested properly.

### 17.2. Groovy Hint for Not-Found Error

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product_not_found')

    request {
        method GET()
        urlPath('/api/products/P-404')
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'PRODUCT_NOT_FOUND'
        )
    }
}
~~~

### 17.3. YAML Hint for Invalid Input

~~~yaml
name: create_product_missing_name
request:
  method: POST
  urlPath: /api/products
  headers:
    Content-Type: application/json
  body:
    name: ""
    price: 350000
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: VALIDATION_FAILED
    errors:
      - field: name
        code: REQUIRED
~~~

### 17.4. Self-Assessment Questions

1. Why shouldn't `GET /api/prodcts/P-404` (misspelled path) be used to test a non-existent resource?
2. If Spring Boot returns default error JSON differing from the contract body, where should you fix it?
3. If the producer changes `PRODUCT_NOT_FOUND` to `ITEM_NOT_FOUND` while keeping status `404`, how might consumers be affected?
4. Why does a validation error for `name: ""` differ from a malformed JSON syntax error?
5. When might `422` be a suitable choice instead of `400`?
6. If an error response includes a randomly generated `traceId` field, how should it be constrained?
7. Does a contract test automatically prove users cannot view another tenant's products?
8. How do you avoid mistaking an unmatched WireMock stub for a valid not-found response?

**Hints:** Routes must be valid to test lookup; error envelopes must be genuinely implemented; error codes are the machine-readable interface; `400`/`422` depend on API policy; dynamic data uses matchers; authorization needs security tests; always assert status **along with** expected structure and error codes.

## 18. Checklist Before Considering Error Branches Contracted

- [ ] **Root cause of each error** is clearly identified: non-existent resource, malformed syntax, failed validation, or business conflict.
- [ ] Each contract has a concrete, reproducible request and corresponding error response.
- [ ] `404` for non-existent data is tested via a **valid route** and a fixture missing the resource.
- [ ] `400`/`422` reflects agreed public API policy rather than guessing from the framework.
- [ ] HTTP status and media type match the response body.
- [ ] JSON error codes remain stable if consumers rely on them.
- [ ] `errors` is an array when consumers need a list of errors; field/code follow schema.
- [ ] Messages are not over-constrained when consumers do not depend on exact wording.
- [ ] Optional fields, nulls, and dynamic data are handled intentionally.
- [ ] The producer has matching exception handlers, validation, and test setup.
- [ ] Generated producer tests are actually **generated and executed** in the build.
- [ ] Consumer tests verify status, error body, and error-handling behavior.
- [ ] CI does not publish stubs/producers after verification fails.
- [ ] No stack traces or sensitive data are exposed in public errors.
- [ ] Security, authorization, retry, or resilience policies are tested at the right layers.

## 19. References

- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): DSL for status, headers, request, and response body.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML structure, generated producer tests, and stubs.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matchers for variable response fields.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): HTTP status semantics, including 400, 404, and 409.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): optional standardized error format.

**Key takeaway:** **Resource not found** and **invalid request** are two error interactions requiring dedicated contracts. Verify **the exact request, HTTP status, Content-Type, and error body used by the consumer**. Groovy/YAML DSL only describes commitments; the producer must implement and pass generated tests, while the consumer uses stubs/Stub Runner to prove its error-handling logic. When these steps run in CI, incompatible changes on error branches are caught before release.
