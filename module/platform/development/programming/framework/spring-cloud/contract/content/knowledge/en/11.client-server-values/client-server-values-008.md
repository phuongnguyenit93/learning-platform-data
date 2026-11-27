# Referencing Request Data in the Response When Supported

## 1. Scenario: The Response Needs to Reflect the Exact Request Received

Consider a service providing an order-intake API. The consumer sends:

~~~http
POST /api/requests?region=HCM HTTP/1.1
Content-Type: application/json
X-Request-ID: REQ-123

{
  "customerId": "CUS-7",
  "quantity": 2
}
~~~

The producer needs to respond:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: REQ-123

{
  "customerId": "CUS-7",
  "quantity": 2,
  "region": "HCM",
  "requestId": "REQ-123",
  "accepted": true
}
~~~

Some response values like `accepted: true` are fixed in this scenario. However, `customerId`, `quantity`, `region`, and `requestId` must come from **the exact request that was sent**. If the consumer sends `CUS-8`, a stub returning fixed `CUS-7` could fail the consumer test or hide the fact that the client mishandles data.

**Spring Cloud Contract** supports referencing request data in the response for HTTP scenarios and compatible stub generation mechanisms. In **Groovy DSL**, we use `fromRequest()`; in **YAML DSL**, we use **Handlebars** expressions `{{{ ... }}}`. These values serve both sides of the contract lifecycle: generated tests verify producer behavior, while stubs use the runtime request to construct a matching response for the consumer.

This lesson belongs to the **Two-Sided Values** chapter in the `SPRING_CLOUD_CONTRACT` module. Scope includes HTTP behavior, Groovy/YAML DSL, producer-side test generation, stub publishing, using Stub Runner, and CI integration to detect incompatible API changes.

After studying this lesson, you will be able to:

- Distinguish fixed values from response values that depend on the request.
- Use `fromRequest()` to extract URL, path, query, header, and JSON body data in Groovy DSL.
- Write equivalent Handlebars expressions in YAML when the syntax is supported.
- Understand why request matchers and response templating must work together.
- Preserve exact data types, handle missing data, and avoid leaking sensitive headers.
- Verify both producer tests and consumer tests with stubs before integrating the contract into CI.

> **Scope note:** Request → response referencing describes how to verify or construct a response within a single HTTP interaction. It does not replace business logic code, does not automatically maintain state across multiple requests, and does not guarantee every stub backend or tool version supports the exact same expression.

## 2. Two-Sided Values: Producer/Consumer and the Meaning of Request Referencing

Spring Cloud Contract distinguishes how a value is used on the **consumer side** versus the **producer side**. For ordinary dynamic values, Groovy DSL provides `value(consumer(...), producer(...))` or `$(consumer(...), producer(...))`.

| Location | Consumer Side (Stub) | Producer Side (Generated Test) |
| --- | --- | --- |
| **Request** | Condition the consumer's request must match; can be a regex | Concrete data the test sends to the producer |
| **Response** | Sample data or template returned by the stub | Value/matcher the generated test uses to verify the producer |

For example: a request has a flexible customer ID on the stub side and a concrete value on the producer test side:

~~~groovy
request {
    method POST()
    url '/api/echo'
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: $(consumer(regex('CUS-[0-9]+')),
                      producer('CUS-7'))
    )
}
~~~

Here the stub can match many customer IDs of the form `CUS-<digits>`, while the generated producer test has deterministic data to send. This is a **two-sided value declaration**, not yet copying the request value into the response.

When you need to **directly reference a request value in the response**, Groovy provides:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: fromRequest().body('$.customerId')
    )
}
~~~

In the DSL, `fromRequest().body('$.customerId')` means **the response must contain the value read from the `customerId` field of the request**. When supported stub generation is used, response templating pulls data from the real request sent to the stub instead of hardcoding a string.

### 2.1. Diagram Comparison

~~~mermaid
flowchart LR
    C["Consumer sends request"] --> S["WireMock Stub"]
    S --> T["Read request field/header/query"]
    T --> R["Build corresponding response"]
    R --> C
    DSL["Contract DSL"] --> STUB["Generate stub and template"]
    DSL --> TEST["Generate producer test"]
    STUB --> S
    TEST --> P["Real producer returns response"]
    P --> A["Assertion based on sample request"]
~~~

Two goals must be verified separately:

1. **Producer verification:** With the sample request sent by the generated test, does the producer respond as specified by the contract?
2. **Consumer verification with stub:** With a request accepted by the matcher, does the stub reflect the request data in the response as described by the DSL, and does the client handle the result properly?

## 3. Data Sources for `fromRequest()` in Groovy

Spring Cloud Contract documentation describes the following methods to reference HTTP request data:

| Groovy Expression | Extracted Data | Example |
| --- | --- | --- |
| `fromRequest().url()` | Request URL and query string | `/api/orders/ORD-123?view=detail` |
| `fromRequest().path()` | Full path | `/api/orders/ORD-123` |
| `fromRequest().path(2)` | Path segment at index 2 (0-based) | `ORD-123` in `/api/orders/ORD-123` |
| `fromRequest().query('view')` | First value of query parameter `view` | `detail` |
| `fromRequest().query('tag', 1)` | Second value of repeated query parameter `tag` | `priority` |
| `fromRequest().header('X-Request-ID')` | First value of the corresponding header | `REQ-123` |
| `fromRequest().header('X-Trace', 1)` | Second value of the corresponding header if present | Second value of `X-Trace` |
| `fromRequest().body()` | Entire request body | JSON or text request |
| `fromRequest().body('$.customerId')` | Value found by JSONPath in the request body | `CUS-7` |
| `fromRequest().body('$.items[0].sku')` | Nested value in JSON request | `BK-1` |

Indices used in `path(index)`, `query(key, index)`, and `header(key, index)` are **0-based indices**. If `/api/orders/ORD-123` is split into three segments `api`, `orders`, `ORD-123`, then `path(0)` is `api` and `path(2)` is `ORD-123`.

Some versions also support `rawUrl()`, `rawPath()`, `rawQuery()`, `rawHeader()`, and `rawBody()` variants. Only use raw variants when you understand content preservation/escaping requirements and have inspected the generated template in your actual project version.

### 3.1. JSONPath Selecting Data from the Request Body

Given request:

~~~json
{
  "customer": {
    "id": "CUS-7",
    "vip": true
  },
  "items": [
    {"sku": "BK-1", "quantity": 2},
    {"sku": "PEN-9", "quantity": 1}
  ]
}
~~~

Some expressions:

~~~groovy
fromRequest().body('$.customer.id')
fromRequest().body('$.customer.vip')
fromRequest().body('$.items[0].sku')
fromRequest().body('$.items[1].quantity')
~~~

Expected results are `CUS-7` (String), `true` (Boolean), `BK-1` (String), and `1` (Number), respectively.

**JSONPath is not an arbitrary business transformation.** It selects values from the request body; to calculate prices, check access permissions, or aggregate other information, the producer must execute that logic and needs corresponding domain/integration tests.

## 4. Complete Groovy Example: Returning Data from Body, Header, and Query

Below is a contract for `POST /api/requests` with three data sources in the request.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('request_echo_customer_and_context')
    description('Response reflects received request data')

    request {
        method POST()

        url('/api/requests') {
            queryParameters {
                parameter 'region': 'HCM'
            }
        }

        headers {
            contentType(applicationJson())
            header('X-Request-ID', 'REQ-123')
        }

        body(
            customerId: 'CUS-7',
            quantity: 2
        )
    }

    response {
        status OK()

        headers {
            contentType(applicationJson())
            header('X-Request-ID',
                   fromRequest().header('X-Request-ID'))
        }

        body(
            customerId: fromRequest().body('$.customerId'),
            quantity: fromRequest().body('$.quantity'),
            region: fromRequest().query('region'),
            requestId: fromRequest().header('X-Request-ID'),
            accepted: true
        )
    }
}
~~~

Meaning of each part:

1. `request.method`, URL, and query define the interaction the consumer actually sends.
2. `customerId` and `quantity` serve as input data for the producer test, as well as the fields checked by the stub request matcher.
3. `response.headers` requires the response to echo the same `X-Request-ID`, a correlation ID pattern used for tracing.
4. `response.body.customerId` and `quantity` reference the sent JSON body data.
5. `response.body.region` reads the query parameter instead of retyping the string `HCM`.
6. `accepted: true` is a fixed scenario value, independent of request fields.

### 4.1. Producer Behavior That Must Be Satisfied

With the described request, the generated test will check conditions equivalent to:

~~~json
{
  "customerId": "CUS-7",
  "quantity": 2,
  "region": "HCM",
  "requestId": "REQ-123",
  "accepted": true
}
~~~

On the producer side, the service must genuinely copy request values into the response. The test will reject a producer that always returns a different customer ID, such as `CUS-99`.

However, **a test running with one sample request does not automatically prove the producer reflects every valid request properly**. If the code hardcodes `CUS-7`, a test with only the `CUS-7` scenario still passes. To protect "echo any customerId" behavior, add test cases with other values or unit/integration tests at the logic layer.

### 4.2. Stub Behavior for the Consumer

When generated with WireMock supporting response templating, the stub can pull `customerId`, `quantity`, `region`, and `X-Request-ID` from the runtime request. Thus, the response can vary depending on inputs **permitted by the stub's matcher**.

If the contract requires an exact body with `CUS-7`, a consumer sending `CUS-8` will not match; templating does not automatically broaden request conditions. To support multiple inputs, design an appropriate request matcher. This is an important distinction between **request-matching capability** and **dynamic response generation**.

## 5. Referencing Path Segments and Repeated Query Parameters

Suppose the consumer sends:

~~~http
GET /api/v1/orders/ORD-123?view=summary&tag=sale&tag=priority HTTP/1.1
~~~

Here the path segments are:

| Index | Segment |
| --- | --- |
| `0` | `api` |
| `1` | `v1` |
| `2` | `orders` |
| `3` | `ORD-123` |

Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_context')

    request {
        method GET()

        url('/api/v1/orders/ORD-123') {
            queryParameters {
                parameter 'view': 'summary'
                parameter 'tag': 'sale'
                parameter 'tag': 'priority'
            }
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: fromRequest().path(3),
            view: fromRequest().query('view'),
            firstTag: fromRequest().query('tag'),
            secondTag: fromRequest().query('tag', 1),
            requestPath: fromRequest().path()
        )
    }
}
~~~

Expected result:

~~~json
{
  "orderId": "ORD-123",
  "view": "summary",
  "firstTag": "sale",
  "secondTag": "priority",
  "requestPath": "/api/v1/orders/ORD-123"
}
~~~

**Points to note:**

- `path(3)` retrieves the fourth segment, not Spring MVC's "`orderId` variable name".
- `query('tag')` and `query('tag', 1)` handle multiple values appearing under the same key.
- If the API does not guarantee the order of repeated query values, do not design a contract that rigidly depends on indices without reason.
- When parsing URLs with percent-encoded characters, test how they are actually decoded in your tool version.
- Referencing syntax does not replace route matching. Two different paths still need a request matcher permitting them.

## 6. Using Request Values Inside Response Strings

Sometimes you need to interpolate a request value into a sentence, such as a note with the user's name:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: fromRequest().body('$.customerId'),
        message: "Request received for ${fromRequest().body('$.customerId')}"
    )
}
~~~

Double quotes in Groovy create a **GString**, allowing `${fromRequest().body('$.customerId')}` inside the sentence. If you use a single-quoted string:

~~~groovy
message: 'Request received for $customerId'
~~~

then `$customerId` is just literal characters and does not reference the request.

A business-meaningful response must consider **which values are safe to return verbatim**. Never echo secrets, passwords, access tokens, or sensitive content simply because the DSL lets you read headers/bodies.

### 6.1. Pass Values Preserving Type Instead of String Concatenation

For JSON request:

~~~json
{"quantity": 2, "active": true}
~~~

if the contract expects response:

~~~json
{"quantity": 2, "active": true}
~~~

use independent reference values:

~~~groovy
body(
    quantity: fromRequest().body('$.quantity'),
    active: fromRequest().body('$.active')
)
~~~

`quantity` can still be verified as a number and `active` as a boolean. Combining everything via string interpolation easily turns numbers/booleans into strings by mistake, breaking the response schema expected by the consumer.

## 7. YAML DSL: Handlebars Instead of `fromRequest()`

When writing contracts in **YAML**, Spring Cloud Contract documentation uses **Handlebars triple braces** to reference the HTTP request in the response:

~~~text
{{{ request.path }}}
{{{ request.query.region.[0] }}}
{{{ request.headers.X-Request-ID.[0] }}}
{{{ jsonpath this '$.customerId' }}}
~~~

In these expressions:

- `request.path` represents the path.
- `request.query.region.[0]` gets the first value of query `region`.
- `request.headers.X-Request-ID.[0]` gets the first value of header `X-Request-ID`.
- `jsonpath this '$.customerId'` extracts a value from the JSON request body.

These are **templates** processed by the tooling when building stubs and verifying. The string `{{{ ... }}}` is not business JSON data that the producer is asked to return literally.

### 7.1. Complete YAML Example

~~~yaml
name: request_echo_customer_and_context
description: Response references JSON body, header, and query from the request
request:
  method: POST
  url: /api/requests
  queryParameters:
    region: HCM
  headers:
    Content-Type: application/json
    X-Request-ID: REQ-123
  body:
    customerId: CUS-7
response:
  status: 200
  headers:
    Content-Type: application/json
    X-Request-ID: '{{{ request.headers.X-Request-ID.[0] }}}'
  body:
    customerId: "{{{ jsonpath this '$.customerId' }}}"
    requestId: '{{{ request.headers.X-Request-ID.[0] }}}'
    region: '{{{ request.query.region.[0] }}}'
    accepted: true
~~~

This is an example equivalent in **intent for reflecting String data** to the Groovy version. In YAML, quotes around templates tell the YAML parser this is a **string containing an expression**. Never write an unquoted template in a position where YAML treats `{` as opening a mapping structure.

For numbers, booleans, or nested objects, ensure templating renders with the **exact JSON type**. Placing a numeric reference inside JSON quotes in a way that turns the response into a String gives the consumer the wrong schema. Inspect the generated WireMock mapping and actual received output when putting non-String types into templates.

### 7.2. Groovy – YAML Comparison Table

| Data from Request | Groovy | YAML Template |
| --- | --- | --- |
| URL and query | `fromRequest().url()` | `{{{ request.url }}}` |
| Full path | `fromRequest().path()` | `{{{ request.path }}}` |
| Path segment at index 1 | `fromRequest().path(1)` | `{{{ request.path.[1] }}}` |
| First query value | `fromRequest().query('region')` | `{{{ request.query.region.[0] }}}` |
| Second query value | `fromRequest().query('tag', 1)` | `{{{ request.query.tag.[1] }}}` |
| First header value | `fromRequest().header('X-Request-ID')` | `{{{ request.headers.X-Request-ID.[0] }}}` |
| Entire body | `fromRequest().body()` | `{{{ request.body }}}` |
| JSON field | `fromRequest().body('$.customerId')` | `{{{ jsonpath this '$.customerId' }}}` |

Documentation also describes the `jsonPath request.body` helper variant in string-based JSON body Groovy examples. Choose a syntax compatible with your **actual DSL and plugin version**, rather than copying a template verbatim from one DSL type to another without testing.

## 8. Templates Do Not Mean Every Request Is Accepted

A common mistake is seeing `fromRequest()` in the response and assuming the stub acts as a universal echo endpoint. In reality, the **stub's request matcher** remains a prerequisite.

Suppose the request DSL declares:

~~~groovy
request {
    method POST()
    url '/api/echo'
    headers {
        contentType(applicationJson())
    }
    body(customerId: 'CUS-7')
}
~~~

The stub may only match a JSON body with `CUS-7`. Sending `CUS-8` will not trigger response templating because the request **may not even match the stub**.

If the consumer is allowed to send multiple customer IDs and needs the exact sent ID echoed back, choose a flexible matcher for the request:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('echo_valid_customer_id')

    request {
        method POST()
        url '/api/echo'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: $(consumer(regex('CUS-[0-9]+')),
                          producer('CUS-7'))
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: fromRequest().body('$.customerId')
        )
    }
}
~~~

On the stub side, pattern `CUS-[0-9]+` allows requests with validly formatted customer IDs. On the producer test side, `CUS-7` is deterministic data to call the endpoint. With a stub backend supporting templating, the response reflects the exact value sent by the consumer at runtime.

However, if API requirements also include authentication, ownership checks, advanced formatting, or order state, **a regex does not replace those rules**. A contract only describes a portion of observable behavior; add tests matching the risk level.

## 9. Referencing in Response Headers

Beyond the JSON body, response headers can also carry information from the request:

~~~groovy
request {
    method GET()
    url '/api/health-details'
    headers {
        header('X-Correlation-ID', 'CORR-123')
    }
}
response {
    status OK()
    headers {
        header('X-Correlation-ID',
               fromRequest().header('X-Correlation-ID'))
    }
}
~~~

This contract pattern is useful when the system **commits to echoing correlation IDs** so clients can correlate logs and trace calls.

Some principles:

1. Only reflect headers **declared safe to return** with a clear purpose.
2. Never echo `Authorization`, session cookies, access tokens, or credentials.
3. If the header can be absent, specify the expectation when absent: omit header in response, return default value, or reject request. Write matching contracts.
4. If a header has multiple values, handle picking the first value or a specific index accurately.
5. HTTP header names are case-insensitive; nevertheless, template syntax and runtime access behavior must be tested in actual integration.

## 10. Missing Values, Null, and Non-JSON Data

### 10.1. JSONPath Finds No Data

Consider:

~~~groovy
body(
    orderId: fromRequest().body('$.orderId')
)
~~~

if the actual request is:

~~~json
{"customerId": "CUS-7"}
~~~

then `$.orderId` finds no field. Do not assume the DSL will return an empty string, `null`, or throw the exact same exception across all versions or stub backends.

For a reproducible contract:

- Ensure the request schema and matcher require the referenced field.
- If the field is optional, write a separate scenario or use a missing-value template expression when **supported by the specific tool**.
- Inspect generated tests and stub runtime behavior when the field is absent.
- Do not include optional fields in the response as mandatory if the real producer makes no such commitment.

### 10.2. `null` Is Not the Same as an Absent Field

Request:

~~~json
{"discountCode": null}
~~~

differs from request:

~~~json
{}
~~~

If the producer echoes `discountCode`, the contract must specify whether `null` is accepted, the field is omitted, or a default value is returned. Plain JSONPath referencing **does not define optional/null policies** for the API.

### 10.3. Text, XML, or Binary Bodies

Examples using `fromRequest().body('$.name')` assume the request is **JSON** compatible with JSONPath. For XML, use an XML/XPath extraction mechanism or suitable test logic; do not apply JSONPath to XML.

For binary uploads (PDF, images, ZIP), returning the raw byte stream or extracting file metadata requires separate verification. Do not assume `fromRequest().body()` and standard response templating fully substitute for binary forwarding or multipart processing.

## 11. Distinguishing "Copying a Value" from "Computing from a Value"

Using `fromRequest()` makes sense when a response value is a **direct reflection** of part of the request, for example:

- Client sends a correlation ID, server echoes the ID for tracing.
- Client sends a reference code, response preserves that code.
- Echo/debug APIs or sandbox endpoints meant to return received input.
- A response field defined as equal to the corresponding request field.

Yet many responses require business logic:

| Request | Expected Response | Should You Use Only Referencing? |
| --- | --- | --- |
| `quantity: 2` | `quantity: 2` | Yes, if purely echoing |
| `quantity: 2`, `unitPrice: 50000` | `totalAmount: 100000` | No, requires pricing logic and tests |
| `customerId: CUS-7` | `customerId: CUS-7` | Yes, if API commits to echoing the ID |
| `customerId: CUS-7` | `vip: true` | No, requires checking profile or business policy |
| `X-Request-ID: REQ-123` | `X-Request-ID: REQ-123` | Yes, if this is a tracing commitment |
| `Authorization: Bearer ...` | Return token in body | Should not be designed this way as it leaks secrets |

A response that looks like an echo does not mean the producer can skip business validation or authorization checks.

## 12. Response Templating Differs Between Stubs and Producer Tests

Distinguish the two processes:

### 12.1. Generated Producer-Side Tests

Spring Cloud Contract generates tests that send a **sample request** described by the DSL. For contracts reflecting request data into the response, generated assertions compare the response returned by the producer against the value read from the corresponding sample request. This verifies behavior at test runtime.

For example: the test sends `customerId: CUS-7`; if the producer returns `customerId: CUS-8`, verification must fail.

However, if the producer only works for one sample value, that test alone does not verify correctness across all accepted inputs. Add more tests if business rules require **data correlation across multiple inputs**.

### 12.2. Generated Consumer-Side Stubs

For WireMock, Spring Cloud Contract can generate stub mappings containing the **response-template transformer**. When the consumer sends a request matching the mapping, WireMock extracts path/header/query/body from the runtime request to build the response.

Illustrative partial mapping example:

~~~json
{
  "response": {
    "status": 200,
    "body": "{\"customerId\":\"{{{jsonpath this '$.customerId'}}}\"}",
    "transformers": ["response-template"]
  }
}
~~~

This snippet only illustrates the **response portion** of a mapping, not a complete WireMock file: a real mapping also needs a `request` section with proper matchers. Names/representations may vary across versions.

If the transformer is not enabled or the stub engine lacks support, the consumer may receive the literal template string instead of the value, or the mapping may fail to run as expected. Therefore, always **test the stub at runtime** after building the artifact.

### 12.3. The "When Supported" Condition

Spring Cloud Contract documentation describes this mechanism for WireMock with response templating (docs note WireMock 2.5.1 or newer is required). With modern Spring Cloud Contract/WireMock versions, use a compatible version combination managed by your project and verify in practice:

1. The DSL is accepted by the plugin when generating tests and stubs.
2. Generated producer tests compile and execute.
3. Stub mappings include the required templating configuration.
4. Stub Runner launches the stub and substitutes placeholders with real request values.
5. Response `Content-Type`, escaping, and data types still match the schema.

Do not assume **every** stub format, messaging protocol, proxy, or test mode interprets Handlebars the same way as WireMock HTTP.

## 13. Data Type and Escaping Pitfalls When Using Templates

### 13.1. Numbers Returned as Strings

Request JSON:

~~~json
{"quantity": 2}
~~~

Consumer expects response:

~~~json
{"quantity": 2}
~~~

Yet a template generating JSON like this:

~~~json
{"quantity": "{{{jsonpath this '$.quantity'}}}"}
~~~

risks outputting `{"quantity":"2"}`, changing a number into a String. In a text-level JSON template, insert numbers **without outer JSON quotes** when preserving numeric type:

~~~text
{"quantity": {{{jsonpath this '$.quantity'}}}}
~~~

The snippet above is a **template example**, not valid JSON before rendering. Inspect the generated mapping and response after Stub Runner executes, especially when the expression resides inside YAML DSL or a JSON string.

### 13.2. Strings with Quotes and Control Characters

A request might contain:

~~~json
{"name": "Lan \"VIP\""}
~~~

If a template injects the raw value into JSON without proper escaping, the response can become malformed JSON. Escaping helpers and strategies depend on context:

- For **JSON values**, preserve valid JSON encoding.
- For **text/plain**, raw data may be needed per agreement.
- For URLs/headers, distinguish decoded values from raw data.
- For XML/HTML content, do not assume JSON escaping suffices.

In Spring Cloud Contract, certain `raw...` variants and helpers such as `escapejsonbody` can assist in corresponding scenarios. Nevertheless, do not add or remove escaping by guesswork. Test with samples containing quotes, backslashes, Unicode, and newlines.

### 13.3. Controlling the Safety of Reflected Data

An API that echoes client-supplied data can become a channel for injecting untrusted data into responses. For web applications, risk also depends on where the response is displayed and how clients handle data. Contract tests should check format/schema; encoding/sanitization and authorization rules need appropriate security tests.

## 14. Common Mistakes and Root-Cause Diagnosis

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Stub returns literal `{{{ ... }}}` | Templating transformer did not run or backend lacks support | Inspect generated WireMock mapping, Stub Runner config, and version |
| Stub does not match new requests | Request matcher is fixed while consumer sends a different value | Adjust matcher to the allowed value range |
| Generated producer test fails | Producer does not reflect the committed field/header/query | Compare actual request, actual response, and contract |
| JSON response has wrong type | Number/boolean turned into String during template rendering | Check quotes and rendered JSON output |
| JSON response fails to parse | Value contains unescaped quotes/backslashes | Use proper helper/encoding and test special inputs |
| Referenced field gets null or no value | Wrong JSONPath or field missing from request | Verify request schema, matcher, and test data |
| Wrong path segment extracted | Miscounted 0-based index | Write an index table for the actual path |
| Repeated query parameter picks wrong element | Called `query('tag')` instead of `query('tag', 1)` | Use the index matching the agreed order |
| Multi-value header picks wrong item | Only took first value or wrong access name | Inspect header list and index syntax |
| JSONPath reference fails on XML | Applied JSONPath to non-JSON data | Use appropriate text/XML handling |
| No generated tests found | Plugin unconfigured, wrong contract path, or skipped | Check generated test count and build logs |
| Stub generated but response is wrong | Behavior mismatch between producer and transformer | Run both producer verification and consumer stub tests |
| Contract too strict | Unnecessarily fixed random headers/IDs | Use matchers and referencing appropriately |
| Contract too loose | Regex accepts invalid data | Tighten matching conditions to actual schema/API |

### 14.1. Diagnosing from Request to Response

When discrepancies occur, trace in order:

1. **Request DSL:** Are Method, URL, query, headers, and body declared accurately?
2. **Runtime request:** What values do the generated test or consumer actually send?
3. **Matcher:** Does the stub accept that request?
4. **Template:** Which field and index is `fromRequest()` or Handlebars reading?
5. **Response:** Does the rendered value have the right data type and encoding?
6. **Producer:** Does business code truly uphold the commitment on echoed data?
7. **Build:** Are generated tests and consumer stub tests actually executed in CI?

Never edit generated Java test files or packaged stub files to hide errors; sustainable fixes belong in the DSL, fixtures, base class, or producer code.

## 15. Practice: Echoing Correlation ID from the Request

Suppose `Payment Gateway Adapter` receives:

~~~http
POST /api/payments/confirm?source=mobile HTTP/1.1
Content-Type: application/json
X-Correlation-ID: CORR-99

{
  "paymentId": "PAY-8",
  "amount": 120000
}
~~~

The agreed API response is:

~~~json
{
  "paymentId": "PAY-8",
  "source": "mobile",
  "correlationId": "CORR-99",
  "confirmed": true
}
~~~

**Tasks:**

1. Write a Groovy contract for the method/path/header/query/body above.
2. Use `fromRequest().body('$.paymentId')`, `fromRequest().query('source')`, and `fromRequest().header('X-Correlation-ID')` in the response.
3. Set the response header `X-Correlation-ID` to the corresponding request value.
4. Convert to YAML using Handlebars; ensure every string template has appropriate YAML quotes.
5. Change the sample body to `PAY-9` to test reflecting the right data; note that the stub's request matcher must accept the new code.
6. Try removing the correlation header and observe the outcome, then decide whether the API allows a missing header or treats it as an invalid request.

### 15.1. Suggested Groovy Solution

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('confirm_payment_with_correlation')

    request {
        method POST()

        url('/api/payments/confirm') {
            queryParameters {
                parameter 'source': 'mobile'
            }
        }

        headers {
            contentType(applicationJson())
            header('X-Correlation-ID', 'CORR-99')
        }

        body(
            paymentId: 'PAY-8',
            amount: 120000
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
            header('X-Correlation-ID',
                   fromRequest().header('X-Correlation-ID'))
        }

        body(
            paymentId: fromRequest().body('$.paymentId'),
            source: fromRequest().query('source'),
            correlationId: fromRequest().header('X-Correlation-ID'),
            confirmed: true
        )
    }
}
~~~

### 15.2. Suggested YAML Solution

~~~yaml
name: confirm_payment_with_correlation
request:
  method: POST
  url: /api/payments/confirm
  queryParameters:
    source: mobile
  headers:
    Content-Type: application/json
    X-Correlation-ID: CORR-99
  body:
    paymentId: PAY-8
    amount: 120000
response:
  status: 200
  headers:
    Content-Type: application/json
    X-Correlation-ID: '{{{ request.headers.X-Correlation-ID.[0] }}}'
  body:
    paymentId: "{{{ jsonpath this '$.paymentId' }}}"
    source: '{{{ request.query.source.[0] }}}'
    correlationId: '{{{ request.headers.X-Correlation-ID.[0] }}}'
    confirmed: true
~~~

Do not keep both Groovy and YAML contracts with the same name and request simultaneously in build sources if only comparing syntax for learning: pick one when running producer verification, or use distinct names/paths and manage matching conditions properly.

### 15.3. Self-Check Questions

1. Why is `fromRequest().body('$.paymentId')` better than literal response `'PAY-8'` when the API commits to echoing the value?
2. If the stub matcher requires exact `PAY-8`, will a consumer sending `PAY-9` get a response from the stub?
3. Where does `{{{ request.headers.X-Correlation-ID.[0] }}}` pull data from, and what does `0` mean?
4. If `amount` is echoed in the response, what must you watch out for so a JSON Number does not turn into a String?
5. Why might a generated producer test using only `PAY-8` miss a bug where code hardcodes `PAY-8`?
6. If the API requires a correlation ID, what response should a test for the missing-header branch expect?
7. If the transformer does not execute on Stub Runner, what symptom is typically observed?

**Answer guidance:** Referencing expresses the input/output relationship; the stub only handles requests matching conditions; index `0` is the first element; data types must be preserved; multiple independent tests are needed to verify generality; missing-header branches need contracts per API policy; unprocessed templates do not resolve to request values.

## 16. Integrating into CI: Verifying Both Sides

A verification workflow can be organized as:

~~~mermaid
flowchart TD
    A["Groovy/YAML contract referencing request"] --> B["Generate producer tests"]
    B --> C["Run against producer"]
    C --> D{"Response expectations match?"}
    D -- "No" --> E["Fail build and review change"]
    D -- "Yes" --> F["Generate and publish versioned stub"]
    F --> G["Consumer uses Stub Runner"]
    G --> H["Send multiple requests fitting matcher"]
    H --> I{"Response reflects data accurately?"}
    I -- "No" --> J["Check matcher, templating, and data types"]
    I -- "Yes" --> K["Consumer contract tests pass"]
~~~

Example producer build command with Maven plugin configured:

~~~bash
./mvnw -B clean verify
~~~

For CI to truly guard compatibility, you should:

- Verify the count of generated tests **executed**, not merely generated.
- For contracts with dynamic echoing, run one or two additional distinct sample requests through Stub Runner to verify the transformer works with the matcher.
- Check the rendered JSON body for accurate String/Number/Boolean/null types and escaping.
- Keep stub artifacts tied to the exact producer-verified version.
- Add business tests if data reflection must hold across all inputs, not just one fixture.
- Review the impact of DSL changes before editing a contract just to make the build green.

## 17. Checklist When Referencing Request Data in Responses

- [ ] Producer and consumer agreed on **which fields are echoed** and which are computed or newly generated.
- [ ] Only reference HTTP request data from sources supported by the DSL and stub backend.
- [ ] Groovy uses accurate `fromRequest().path/query/header/body` with 0-based indices.
- [ ] YAML uses Handlebars syntax `{{{ ... }}}` and documented JSONPath helpers.
- [ ] Request matcher accepts the exact input range the stub is meant to simulate.
- [ ] JSONPath points to an existing field; optional/null fields have clear policies.
- [ ] Response templating preserves exact data types and escaping.
- [ ] Does not echo tokens, session cookies, passwords, or sensitive data outside the contract.
- [ ] Generated producer tests have appropriate sample data and base classes.
- [ ] WireMock stub has been verified with the `response-template` transformer and works through Stub Runner.
- [ ] Tested with alternative inputs to catch hardcoded logic when general echoing is needed.
- [ ] CI runs both producer verification and consumer stub tests, and manages artifact versions.
- [ ] Business calculations, multipart/binary handling, or multi-request state are tested at appropriate layers.

## 18. References

- [Spring Cloud Contract — Dynamic properties, Referencing the Request from the Response](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `fromRequest()`, Handlebars for YAML, response templating principles, and consumer/producer values.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): method, URL, headers, query, request/response body.
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): versions, test/stub generator plugins, and build lifecycle configuration.

**Key takeaway:** When a contract requires the response to reflect a value from the request, use **`fromRequest()` in Groovy** or **Handlebars in YAML** when supported by your tools. Always verify both the **request matcher** and the **response template**, preserve data types, and run producer verification alongside Stub Runner in CI. A contract can describe the input/output relationship, while general business correctness still requires testing at realistic scope.
