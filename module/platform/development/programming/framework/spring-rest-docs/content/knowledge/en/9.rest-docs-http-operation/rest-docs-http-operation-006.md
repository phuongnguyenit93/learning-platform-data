# Status, Headers, and Body in Responses

## 1. Lesson Objectives

In an **HTTP operation**, the client sends a request and the server returns an **HTTP response**. A response contains three pieces of information to read together:

1. **Status code:** the server communicates the result of processing the request.
2. **Response headers:** metadata about data representation, caching, redirection, newly created resources, or processing conditions.
3. **Response body:** the returned content, if that response type permits and carries a payload.

This belongs to the **HTTP operation** chapter of the `SPRING_REST_DOCS` module. The overarching goal is generating **verifiable** REST API documentation from HTTP tests using **MockMvc, WebTestClient, or REST Assured**; producing snippets for requests, responses, payloads, parameters, and headers; and authoring Asciidoctor/Markdown documentation in build and CI pipelines.

After this lesson, you will be able to:

- Analyze the status line, response headers, and body from `http-response.adoc`.
- Distinguish `200`, `201`, `202`, `204`, `304`, and `4xx`/`5xx` responses.
- Verify status, headers, and payload with independent assertions, then generate `response-headers.adoc` and `response-fields.adoc`.
- Understand when a response must **have no body**, regardless of whether a test might want to document extra data.
- Use `responseFields(...)`, `optional()`, `ignored()`, and `relaxedResponseFields(...)` intentionally.
- Integrate real snippets into Asciidoctor and ensure documentation is only published after tests pass.

> Spring REST Docs records **the response received by the HTTP test**; it does not guess outcomes from controller method names or API prose. A generated snippet does not prove business correctness if the test lacks appropriate assertions.

## 2. Structure of an HTTP Response

Suppose `GET /api/orders/101` returns an order. An illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v3"
Cache-Control: private, max-age=60

{"id":101,"state":"PAID","amount":250000,"items":[{"sku":"BOOK-42","quantity":2}]}
~~~

| Component | Example | Role |
| --- | --- | --- |
| Displayed HTTP version | `HTTP/1.1` | How the snippet represents the response; does not imply production only supports HTTP/1.1. |
| Status code | `200` | Numeric code classifying the request outcome. |
| Reason phrase | `OK` | Descriptive phrase in HTTP/1.1 syntax; not business data for assertions to rely on. |
| `Content-Type` | `application/json` | Media type of the body representation. |
| `ETag` | `"order-v3"` | Validator used in caching and conditional requests when supported by the API. |
| `Cache-Control` | `private, max-age=60` | Caching policy advertised by the server. |
| Blank line | After headers | Separates headers from the body in HTTP/1.1 text representation. |
| Response body | Order JSON | Data returned by the API to the caller. |

The example above is solely to explain structure. Header order, presence of `Date`/`Content-Length`, charset, JSON formatting, and reason phrase depend on the client/server, configuration, and preprocessors. If a test uses HTTP/2 or HTTP/3, the protocol does not transmit an `HTTP/1.1 200 OK` status line like the illustrative text; the status value is encoded per the respective protocol mechanism.

**These three components relate to one another but do not substitute for one another:** `200 OK` does not prove the body matches the schema; `Content-Type: application/json` does not prove the JSON contains valid data; valid-looking JSON does not prove the server returned the right status.

## 3. HTTP Status Groups and Business Semantics

| Group | HTTP meaning | Common examples |
| --- | --- | --- |
| `1xx` | Informational/protocol processing continuing | `100 Continue`, `101 Switching Protocols` |
| `2xx` | Request successfully processed according to specific semantics | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Redirection or reusing cached representation/mechanism | `301`, `302`, `304 Not Modified`, `307`, `308` |
| `4xx` | Request rejected or cannot be fulfilled due to client-side conditions | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` |
| `5xx` | Server or a server processing layer failed to fulfill the request | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` |

Status groups provide initial orientation; **exact semantics reside in the specific code and the API contract**.

### 3.1. Statuses to Distinguish

| Status | Usage example | What to assert/document |
| --- | --- | --- |
| `200 OK` | Successfully fetching an order | Body and `Content-Type` if the response has a representation. |
| `201 Created` | Creating a new order | Status, `Location` if defined by the API, body containing ID if present. |
| `202 Accepted` | Submitting an asynchronous processing task | Only guarantees accepted for processing; document how to check progress. |
| `204 No Content` | Deletion succeeded, no body returned | Status `204` and an empty response body. |
| `304 Not Modified` | Conditional request and representation unchanged | Matching cache/validator headers, **no response body**. |
| `400 Bad Request` | Malformed syntax or invalid parameters/body per contract | Status and safe, clear error details. |
| `401 Unauthorized` | Missing or invalid authentication credentials | Authentication requirement, `WWW-Authenticate` when applicable. |
| `403 Forbidden` | Server refuses to execute request | Authorization rules; may intentionally restrict error details. |
| `404 Not Found` | Requested URI/resource not found | Status and error payload per contract. |
| `409 Conflict` | Duplicate code or state conflict | Error code/conflict details for client handling. |
| `422 Unprocessable Content` | Syntactically understood data cannot be processed semantically | Error fields and messages per API design. |
| `429 Too Many Requests` | Rate limit reached | `Retry-After` if provided by the server. |
| `500 Internal Server Error` | Unspecified server error | Safe error body; do not leak stack traces/secrets. |
| `503 Service Unavailable` | Service temporarily unavailable | `Retry-After` if present; describe retry guidance. |

**Two common misconceptions:**

- `201` indicates a resource was created; `202` only indicates the request was accepted, **without guaranteeing background work has finished**.
- `204` is success **with no response body**. Never add JSON to a `204` response just to make documentation look "complete".

A `POST` endpoint may return `200`, `201`, or `202` depending on the API contract. Spring REST Docs does not force every `POST` to return `201`. Similarly, calling the same `DELETE` repeatedly may return `204` the first time and `404` afterwards depending on endpoint policy; that does not negate the method's idempotency under HTTP semantics.

### 3.2. "Error" Does Not Mean Looking Only at Status

A test might return `200` while the JSON is missing a critical field, `Location` is wrong, or `amount` is incorrect. Therefore, when the goal is verifiable API documentation, always consider three layers of assertions:

1. **Status**: in the group/code matching the contract.
2. **Headers**: media type, location, validator, or caching policy as expected.
3. **Body**: present or empty, matching schema, data types, and key values.

## 4. Reading and Documenting Response Headers

HTTP response headers are metadata describing how the client should handle the response. Key headers to understand:

| Header | Purpose | Examples and notes |
| --- | --- | --- |
| `Content-Type` | Media type of the body, if present | `application/json`, `application/problem+json`, `text/plain`. |
| `Location` | Locates a newly created resource or redirect target | `/api/orders/102` or an absolute URI; interpreted per status semantics. |
| `ETag` | Validator of a representation | E.g., `"order-v3"`; quotes are part of ETag syntax. |
| `Last-Modified` | Last modification timestamp of the representation | Can be used with conditional `If-Modified-Since` requests. |
| `Cache-Control` | Caching policy directives | `no-store`, `private, max-age=60`. |
| `Vary` | Tells caches which request headers affect the representation | E.g., `Vary: Accept-Language`. |
| `WWW-Authenticate` | Challenge for the authentication scheme | Important for `401` under HTTP authentication. |
| `Retry-After` | Suggested wait time/timestamp before retrying | Often accompanies `429` or `503`. |
| `Content-Disposition` | How attached/downloaded content should be handled | E.g., file downloads; verify safe filename/encoding. |
| `Content-Length` | Size of the body transferred under the corresponding mechanism | May be absent; do not assume it is always present. |
| `Set-Cookie` | Instructs the client to store a cookie | Never put real session cookies in public snippets. |

HTTP field names are case-insensitive per protocol semantics, though values and combining rules vary per header. Some responses contain multiple headers with the same name; for example, **`Set-Cookie` cannot simply be comma-joined** like typical list-valued headers.

### 4.1. `Content-Type` and Content Negotiation

Client can send:

~~~http
GET /api/orders/101 HTTP/1.1
Accept: application/json
~~~

Server returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":101,"state":"PAID"}
~~~

`Accept` belongs to the **request**; `Content-Type` belongs to the **response**. They play distinct roles. If the API supports multiple formats, the server may select a representation based on `Accept`; tests should verify the actual response rather than inferring it solely from the request header.

In MockMvc, `content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` works well when the API may return `application/json;charset=UTF-8` or a compatible media type. If the contract demands an exact media type, reflect that in the assertion. For `application/problem+json`, assert the appropriate Problem Details media type instead of assuming every error returns `application/json`.

### 4.2. `Location` and `201 Created`

The response when creating a resource might be:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/102
Content-Type: application/json

{"id":102,"state":"PENDING"}
~~~

This is a specific contract example: the API creates an order and returns a relative URI in `Location`. Another API might return an absolute URI or define a different payload. Tests must assert values according to the **actual contract**, rather than hardcoding one assumption across all APIs.

### 4.3. `ETag` and Conditional Responses

A resource read request might receive:

~~~http
HTTP/1.1 200 OK
ETag: "order-v3"
Content-Type: application/json

{"id":101,"state":"PAID"}
~~~

Then the client sends:

~~~http
GET /api/orders/101 HTTP/1.1
If-None-Match: "order-v3"
~~~

If the validator still matches per endpoint rules, the server can return:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-v3"
Cache-Control: private, max-age=60
~~~

`304` tells the client it may reuse the cached representation per HTTP caching semantics; it **carries no response body**. This is a different HTTP operation from a normal `GET` returning `200`. Write separate tests for both branches if the API supports conditional requests.

## 5. Response Body: Data Formats, Field Types, and Empty Cases

### 5.1. JSON Objects and JSON Arrays

An illustrative JSON object response:

~~~json
{
  "id": 101,
  "state": "PAID",
  "amount": 250000,
  "items": [
    {
      "sku": "BOOK-42",
      "quantity": 2
    }
  ]
}
~~~

To document fields in a JSON response, Spring REST Docs uses `responseFields(...)` with paths:

| REST Docs JSON path | Illustrative type | Explanation |
| --- | --- | --- |
| `id` | number | Order ID. |
| `state` | string | Business state. |
| `amount` | number | Total amount in the currency unit published by the API. |
| `items` | array | List of line items. |
| `items[].sku` | string | Product SKU on each line item. |
| `items[].quantity` | number | Quantity on each line item. |

`items[].sku` is REST Docs' field path syntax for array elements, **different from the JSONPath assertion `$.items[0].sku`** which targets a specific index. If the response is a root-level JSON array, appropriate paths can be `[]` and `[].id`.

For XML bodies, REST Docs requires a compatible `application/xml` media type to parse and document fields via XPath. If an API returns binary/streaming data or non-JSON/XML content, consider dedicated body snippets and descriptions; do not assume `responseFields(...)` can always parse the payload.

### 5.2. Absent Body

HTTP cases to pay attention to:

- `204 No Content`: no response body.
- `304 Not Modified`: no response body.
- `HEAD` request: response has no body, though it may contain metadata describing the response a corresponding `GET` would return.
- A `200` response can validly have an empty body per contract; do not equate status `200` with the presence of JSON.

Therefore, for bodyless responses, assert an empty body and **do not use `responseFields(...)` to describe non-existent JSON**. Documentation can simply include `http-response.adoc` or explain it in prose.

### 5.3. Error Responses and Problem Details

For `GET /api/orders/999`, an API may return an error following [Problem Details for HTTP APIs (RFC 9457)](https://www.rfc-editor.org/rfc/rfc9457.html):

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Order 999 was not found",
  "instance": "/api/orders/999"
}
~~~

The body above is **only an example contract**, not auto-generated by Spring REST Docs and not a default format guaranteed in every Spring Boot application. Standard members like `type`, `title`, `status`, `detail`, and `instance` carry meanings defined by the RFC; an API may also include extension fields or use a custom error format. Tests and descriptions must follow the real response.

Never expose stack traces, tokens, queries containing secrets, or internal details in public error bodies. Verifiable documentation needs tests for error branches matching expected behavior, not only happy-path examples.

## 6. Response Snippets in Spring REST Docs

An HTTP test recorded with `document("identifier")` can generate six default snippets; when appropriate descriptors are added, tabular snippets appear as well:

| Snippet | Content |
| --- | --- |
| `http-response.adoc` | Status line, response headers, and body in one HTTP representation. |
| `response-body.adoc` | Only the recorded response body. |
| `response-headers.adoc` | Table describing headers declared via `responseHeaders(...)`. |
| `response-fields.adoc` | Table describing payload fields declared via `responseFields(...)`. |
| `http-request.adoc` | Method, URL, headers, and body of the corresponding request. |
| `curl-request.adoc` | `curl` command to try the corresponding request. |
| `httpie-request.adoc` | HTTPie command to try the corresponding request. |
| `request-body.adoc` | Body of the corresponding request. |

The six default snippets are `curl-request`, `httpie-request`, `http-request`, `http-response`, `request-body`, and `response-body`. The two tabular snippets `response-headers` and `response-fields` only appear if the test declares descriptors or the project is configured to generate them accordingly.

**There is no default snippet that automatically lists every status an endpoint can return.** One `http-response` records **one response from one operation**. If an endpoint has both `200` and `404`, create tests with distinct identifiers and compose them into documentation sections.

## 7. Complete MockMvc Example: Verifying Status, Headers, and JSON Body

### 7.1. Initial Conditions

Example for **Spring Boot 3.x, Spring MVC, JUnit 5, and Java 17+**, with dependencies:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

If the project uses Spring Boot dependency management, let it manage compatible versions.

**Assumption:** the application already exposes `GET /api/orders/101`, fixtures pre-create order `101`, and the response matches the JSON in section 5.1. The response also includes:

~~~http
Content-Type: application/json
ETag: "order-v3"
Cache-Control: private, max-age=60
~~~

These are conditions of the example, **not built-in behavior of REST Docs**. If the application does not provide those headers/cache validators or fixtures, the test below will fail and must be updated to match the actual contract.

### 7.2. Test with All Three Assertion Layers

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderResponseDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentOrderFound() throws Exception {
        mockMvc.perform(get("/api/orders/101")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(header().string(HttpHeaders.ETAG, "\"order-v3\""))
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "private, max-age=60"))
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.state").value("PAID"))
            .andExpect(jsonPath("$.amount").value(250000))
            .andExpect(jsonPath("$.items[0].sku").value("BOOK-42"))
            .andExpect(jsonPath("$.items[0].quantity").value(2))
            .andDo(document("orders-get-success",
                responseHeaders(
                    headerWithName(HttpHeaders.CONTENT_TYPE)
                        .description("Media type of the response body"),
                    headerWithName(HttpHeaders.ETAG)
                        .description("Validator of the order representation"),
                    headerWithName(HttpHeaders.CACHE_CONTROL)
                        .description("Caching policy of the response")
                ),
                responseFields(
                    fieldWithPath("id").description("Order ID"),
                    fieldWithPath("state").description("Order state"),
                    fieldWithPath("amount")
                        .description("Total amount in VND"),
                    fieldWithPath("items").description("List of line items"),
                    fieldWithPath("items[].sku").description("Product SKU"),
                    fieldWithPath("items[].quantity")
                        .description("Product quantity")
                )
            ));
    }
}
~~~

Key points:

1. `status().isOk()` verifies exact `200`.
2. `contentTypeCompatibleWith(...)` checks response media type; `header().string(...)` verifies `ETag` and `Cache-Control` values per the illustrative contract.
3. `jsonPath(...)` asserts important JSON values independently of the field table description.
4. `responseHeaders(...)` generates `response-headers.adoc` to **explain** headers; header descriptors do not replace assertions on header values.
5. `responseFields(...)` generates `response-fields.adoc` while verifying that the field list matches the payload in strict mode.
6. `document("orders-get-success", ...)` uses a stable identifier to group the operation's snippets.
7. `andDo(...)` follows the `andExpect(...)` calls: when an assertion fails, the documentation step at the end does not run.

If a response is produced with variable data like timestamps, dynamic IDs, or non-fixed `ETag`s, use deterministic fixtures or assertions matching contract properties instead of relying on incidental environment values.

### 7.3. File Structure and Generated Content

After the test passes, typical output is:

~~~text
build/generated-snippets/
└── orders-get-success/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
~~~

Roles of the four snippets directly tied to this lesson:

- `http-response.adoc` shows the actual recorded response.
- `response-body.adoc` isolates the body for separate display.
- `response-headers.adoc` explains the headers documented by the test.
- `response-fields.adoc` explains the schema of the documented JSON.

**Illustrative** content of `orders-get-success/http-response.adoc`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v3"
Cache-Control: private, max-age=60

{"id":101,"state":"PAID","amount":250000,"items":[{"sku":"BOOK-42","quantity":2}]}
~~~

Header order, JSON formatting, reason phrase, and additional headers may differ. To see **exactly** what the test generated, open the file in the output directory after running the test.

## 8. Documenting Different Outcomes

### 8.1. `201 Created`: Status, `Location`, and Body

Suppose `POST /api/orders` with valid JSON returns `201 Created`, `Location: /api/orders/102`, and body:

~~~json
{"id":102,"state":"PENDING"}
~~~

Inside the test class configured in section 7, add the static import:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
~~~

And a separate test method:

~~~java
@Test
void documentOrderCreated() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {"productId":"BOOK-42","quantity":1}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().string(HttpHeaders.LOCATION, "/api/orders/102"))
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(102))
        .andExpect(jsonPath("$.state").value("PENDING"))
        .andDo(document("orders-create",
            responseHeaders(
                headerWithName(HttpHeaders.LOCATION)
                    .description("URI of the new order"),
                headerWithName(HttpHeaders.CONTENT_TYPE)
                    .description("Format of the response body")
            ),
            responseFields(
                fieldWithPath("id").description("New order ID"),
                fieldWithPath("state").description("Initial state")
            )
        ));
}
~~~

The ID `102` must come from a fixture or predictable ID generator in **the application under test**. If the database assigns IDs dynamically, design fixtures and assertions so tests do not depend on execution order; never present a fabricated ID as a real response.

**Verification point:** status `201` indicates creation succeeded; `Location` and the body per the illustrative contract help clients locate the new resource. Do not assume `Location` or a body is mandatory in every creation API without checking its specific contract.

### 8.2. `204 No Content`: No Body to Document

Suppose `DELETE /api/orders/101` returns `204` and an empty body. Add import:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
~~~

Test:

~~~java
@Test
void documentOrderDeleted() throws Exception {
    mockMvc.perform(delete("/api/orders/101"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""))
        .andDo(document("orders-delete"));
}
~~~

The `http-response.adoc` snippet may look like:

~~~http
HTTP/1.1 204 No Content
~~~

If the server sends valid headers, they may still appear in the snippet. **Do not declare `responseFields(...)`** for non-existent JSON. `response-body.adoc` may be empty; do not treat that file's existence as proof that the response had a payload.

### 8.3. `304 Not Modified`: Status and Validator

If the application supports ETags and conditional requests, you can test:

~~~java
@Test
void documentOrderNotModified() throws Exception {
    mockMvc.perform(get("/api/orders/101")
            .header(HttpHeaders.IF_NONE_MATCH, "\"order-v3\""))
        .andExpect(status().isNotModified())
        .andExpect(header().string(HttpHeaders.ETAG, "\"order-v3\""))
        .andExpect(content().string(""))
        .andDo(document("orders-not-modified",
            responseHeaders(
                headerWithName(HttpHeaders.ETAG)
                    .description("ETag of the validated representation")
            )
        ));
}
~~~

This example has a **prerequisite**: the endpoint must implement an appropriate validator mechanism. If the endpoint ignores `If-None-Match` and returns `200`, never change the expectation to `304` just to make docs look nicer.

With `304`, the response has no body; do not generate a `response-fields` table for this case. Similarly, when testing `HEAD`, distinguish metadata that may be returned from the **response body that is not sent**.

### 8.4. `404 Not Found`: Status and Error Body

Suppose the API returns concrete Problem Details as in section 5.3; you can add:

~~~java
@Test
void documentOrderNotFound() throws Exception {
    mockMvc.perform(get("/api/orders/999")
            .accept(MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(jsonPath("$.status").value(404))
        .andExpect(jsonPath("$.title").value("Order not found"))
        .andDo(document("orders-get-not-found",
            responseFields(
                fieldWithPath("type").description("Problem type URI"),
                fieldWithPath("title").description("Error title"),
                fieldWithPath("status").description("HTTP status code"),
                fieldWithPath("detail").description("Error explanation"),
                fieldWithPath("instance")
                    .description("Path of the problem occurrence")
            )
        ));
}
~~~

If the real application does not return Problem Details or all of these fields, adapt the test and descriptors to match the **actual response**. `APPLICATION_PROBLEM_JSON` and the illustrative schema are not automatic requirements imposed by REST Docs.

Separate `orders-get-success` and `orders-get-not-found` into **two identifiers** so snippets for the `200` and `404` branches of the same endpoint do not overwrite each other.

## 9. Response Descriptors: Strict, Optional, Ignored, Relaxed

### 9.1. `responseHeaders(...)` Checks Declared Headers

REST Docs uses:

~~~java
responseHeaders(
    headerWithName(HttpHeaders.CONTENT_TYPE)
        .description("Media type of the response body"),
    headerWithName(HttpHeaders.ETAG)
        .description("Validator used for caching")
        .optional()
)
~~~

Under standard behavior:

- A documented header **not marked optional** must be present in the response; if missing, snippet generation fails.
- An `.optional()` header may be absent.
- **Other undeclared headers** do not fail the `response-headers` snippet by default. The table contains only the documented headers.

For example, if the API also returns `Date`, `response-headers` does not force you to list `Date` unless you want to explain it. To verify the **value** of `ETag` or `Location`, add an appropriate `header().string(...)` assertion; descriptors only document presence and meaning.

### 9.2. `responseFields(...)` Validates Payload Structure

Example:

~~~java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("state").description("State"),
    fieldWithPath("amount").description("Total amount"),
    fieldWithPath("items").description("Line items list"),
    fieldWithPath("items[].sku").description("Item SKU"),
    fieldWithPath("items[].quantity").description("Quantity")
)
~~~

In default (*strict*) mode, if the response contains an undocumented field or a **documented required field** is absent from the payload, snippet generation fails. Consequently, when the response schema changes, tests warn that documentation is out of date.

Variants to understand clearly:

| Tool | When to use | Effect |
| --- | --- | --- |
| `.optional()` | Field is occasionally absent | Does not fail solely because the field is missing. |
| `.ignored()` | Field is present but shouldn't appear in the table | Omitted from the snippet while avoiding an undocumented-field error. |
| `relaxedResponseFields(...)` | Only want to document part of a payload | Ignores **extra undocumented** fields, while still requiring non-optional descriptors to match. |
| `subsectionWithPath("items")` | Only want an overview of part of the payload tree | Child fields inside that subtree count as documented when using a subsection descriptor. |
| `fieldWithPath("items[].sku")` | Document a field inside array elements | Uses REST Docs' JSON field path syntax. |

Example of an optional field:

~~~java
responseFields(
    fieldWithPath("id").description("Order ID"),
    fieldWithPath("state").description("State"),
    fieldWithPath("note").description("Optional note").optional()
)
~~~

This snippet illustrates the **descriptor**, not a drop-in replacement for the full list in the larger example if the response also contains `amount` and `items` without descriptors. In strict mode, those fields would fail the test.

### 9.3. Descriptors Do Not Validate Business Values

`fieldWithPath("amount").description("Total amount in VND")` does not prove that amount is greater than 0, equals the sum of line items, or is actually in VND. Nor does `fieldWithPath("state")` prove state belongs to a valid enum.

Add business assertions such as `jsonPath("$.amount").value(250000)`, boundary/validation tests, or appropriate validators. Avoid switching `responseFields(...)` wholesale to relaxed mode just to keep tests green when the API changes, as doing so hides schema drift.

## 10. Preprocessing Responses: Clear Presentation and Data Protection

Snippets generated from HTTP tests can contain variable headers, cookies, trace IDs, timestamps, or hard-to-read JSON bodies. Spring REST Docs supports **`preprocessResponse(...)`** to transform **the record used in documentation**.

Example replacing the `.andDo(document(...))` call at the end of a test chain with JSON formatting and sensitive-header removal:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

// Inside a test that already has .andExpect(...) assertions:
.andDo(document("orders-get-success",
    preprocessResponse(
        modifyHeaders()
            .remove("Set-Cookie")
            .remove("X-Internal-Trace"),
        prettyPrint()
    ),
    responseHeaders(
        headerWithName(HttpHeaders.CONTENT_TYPE)
            .description("Media type of the JSON response"),
        headerWithName(HttpHeaders.ETAG)
            .description("Representation validator"),
        headerWithName(HttpHeaders.CACHE_CONTROL)
            .description("Caching policy")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("state").description("State"),
        fieldWithPath("amount").description("Total amount"),
        fieldWithPath("items").description("Line items list"),
        fieldWithPath("items[].sku").description("Item SKU"),
        fieldWithPath("items[].quantity").description("Quantity")
    )
));
~~~

This is a **replacement for the `document(...)` call**, not a second call added with the same identifier. It assumes assertions on `ETag` and `Cache-Control` have passed, and those headers remain present in the record after preprocessing.

Key principles:

- Use **dummy fixtures** from the start; never put real cookies, tokens, or personal data in HTTP tests used for public documentation.
- `prettyPrint()` improves JSON readability but does not fix application logic or replace assertions.
- If you remove a header from the documented response, do not simultaneously declare it as required in `responseHeaders(...)`, unless another configuration satisfies the descriptor.
- When you need to keep a header to explain its meaning while masking its value, consider `modifyHeaders().set("X-Trace-Id", "example-trace")` on an existing header.
- Preprocessors do not alter the **original response** returned by the application during the test; do not use masked output as proof that the server sent the replacement value.
- For bodies containing variable data, prefer deterministic fixtures or deliberate preprocessors; never use content replacement to hide API contract bugs.

## 11. WebTestClient and REST Assured

Spring REST Docs integrates with multiple HTTP test clients. Syntax for generating snippets differs, yet all three record an **HTTP operation**.

### 11.1. WebTestClient

Assuming `webTestClient` is already configured with Spring REST Docs and `GET /api/orders/101` returns `200` with JSON and `ETag` per contract:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/orders/101")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().valueEquals(HttpHeaders.ETAG, "\"order-v3\"")
    .expectBody()
    .jsonPath("$.id").isEqualTo(101)
    .jsonPath("$.state").isEqualTo("PAID")
    .consumeWith(document("orders-get-webtestclient",
        responseHeaders(
            headerWithName(HttpHeaders.ETAG)
                .description("Representation validator")
        ),
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("state").description("State"),
            fieldWithPath("amount").description("Total amount"),
            fieldWithPath("items").description("Line items list"),
            fieldWithPath("items[].sku").description("Item SKU"),
            fieldWithPath("items[].quantity").description("Quantity")
        )
    ));
~~~

This snippet assumes the response matches the payload shown in section 5.1 and the client is configured with REST Docs. The integration module is `spring-restdocs-webtestclient`; configure the extension/configurer for Spring WebFlux or how the client is bound in your project.

### 11.2. REST Assured

With REST Assured, Spring REST Docs uses a **filter** to record operations. Example with a `RequestSpecification` `spec` already configured for base URL, port, and REST Docs:

~~~java
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

// spec: RequestSpecification configured for the test server and REST Docs.
given(spec)
    .filter(document("orders-get-restassured",
        responseHeaders(
            headerWithName("ETag").description("Order validator")
        )
    ))
    .accept("application/json")
.when()
    .get("/api/orders/101")
.then()
    .statusCode(200)
    .header("ETag", "\"order-v3\"")
    .body("id", equalTo(101))
    .body("state", equalTo("PAID"));
~~~

This integration uses the `spring-restdocs-restassured` module and corresponding filter configuration. The filter records the operation during request execution, potentially **before assertions in `then()`**; therefore, only treat documentation as valid and publishable when **all tests/the entire pipeline PASS**.

### 11.3. Comparing Where Verification and Documentation Happen

| Client | Verify status/headers/body | Record snippet |
| --- | --- | --- |
| MockMvc | `andExpect(status...)`, `header(...)`, `jsonPath(...)` | `andDo(document("..."))` |
| WebTestClient | `expectStatus(...)`, `expectHeader(...)`, `expectBody()` | `consumeWith(document("..."))` |
| REST Assured | `then().statusCode(...)`, `header(...)`, `body(...)` | Filter `document("...")` |

The three clients do not necessarily share identical default headers or transport behavior. Do not demand byte-for-byte identical output when the goal is simply verifying the REST API contract.

## 12. Authoring Asciidoctor/Markdown Documentation

An Asciidoctor page can clearly present each tested status:

~~~asciidoc
= Orders API

== Get an Order

=== Success: 200 OK

HTTP request:
include::{snippets}/orders-get-success/http-request.adoc[]

HTTP response:
include::{snippets}/orders-get-success/http-response.adoc[]

Response headers:
include::{snippets}/orders-get-success/response-headers.adoc[]

Response fields:
include::{snippets}/orders-get-success/response-fields.adoc[]

=== Not Found: 404 Not Found

include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]

== Create Order: 201 Created

include::{snippets}/orders-create/http-response.adoc[]
include::{snippets}/orders-create/response-headers.adoc[]

== Delete Order: 204 No Content

include::{snippets}/orders-delete/http-response.adoc[]

== Not Modified: 304 Not Modified

include::{snippets}/orders-not-modified/http-response.adoc[]
~~~

The Asciidoctor `snippets` attribute must be configured by the build to point to the right snippet output directory (e.g., `build/generated-snippets`). If documentation sources live in another directory, adjust relative paths and plugin settings accordingly.

With plain Markdown renderers, `include::{snippets}/...[]` syntax does not work automatically. If you want to author in Markdown, use an appropriate template or conversion/embedding step. The core principle is **sourcing data from freshly executed HTTP tests**.

### 12.1. Pipeline Ensuring Verifiable Documentation

~~~mermaid
flowchart TD
    A["Run HTTP tests"] --> B{"Status/header/body assertions pass?"}
    B -->|No| C["CI fails, do not publish"]
    B -->|Yes| D["Spring REST Docs generates snippets"]
    D --> E["Asciidoctor/Markdown build"]
    E --> F{"Include and render succeed?"}
    F -->|No| C
    F -->|Yes| G["Package or publish docs"]
~~~

Configure the documentation build task to depend on the snippet-generating test task and fail the pipeline when tests fail or snippets are missing. **Leftover stale snippets** from a prior run can make documentation pages look valid when the current operation no longer runs; projects must manage output directories, task dependencies, and artifacts so publications reflect the current test run.

### 12.2. How Much Verification Is Enough?

- Assert **status** for every major branch.
- Assert **essential headers** and relevant business values: `Location`, `ETag`, media type, caching policy if part of the contract.
- Assert **body** and matching schema; never document JSON fields on bodyless statuses.
- Write separate tests for **happy path**, **resource not found**, validation errors, conflicts, and conditional branches if supported by the API.
- Generate snippets for each scenario using stable identifiers; include them on a doc page explaining how clients recognize and handle each result.

## 13. Common Pitfalls

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `http-response.adoc` shows `404` instead of `200` | Missing resource in fixture, wrong URL, or mismatched endpoint | Fix fixture/request; add `status().isOk()` to catch early. |
| `200` received but JSON has wrong fields/values | Test only checks status | Add `jsonPath(...)` and `responseFields(...)`. |
| `response-headers.adoc` is not generated | Missing `responseHeaders(...)` | Declare headers to describe inside `document(...)`. |
| Test reports missing header in snippet | Required header descriptor not returned by server | Check contract, real response, and preprocessing. |
| `Date` or `Server` header missing from table | Those headers were not declared in descriptors | Only add them if needed to explain the contract; the table does not auto-list all headers. |
| `response-fields.adoc` reports undocumented field | JSON gained a new field, wrong path, or missing descriptor | Update schema/descriptors; use relaxed mode only intentionally. |
| `204`/`304` shown with a JSON body | Wrong snippet included or endpoint violates HTTP semantics | Verify identifier and remove body from response per contract. |
| Status `201` but `Location` is wrong | Test lacks header assertion or URI built incorrectly | Assert exact `Location` or matching pattern. |
| `Content-Type` differs from expectation | API changed representation or uses another media type | Use appropriate assertion and update contract without overly brittle matching. |
| Error response leaks stack trace/secrets | Exception handler returns internal details | Fix error handler, fixtures, and snippet generation workflow. |
| Unstable `ETag` makes test flaky | Test data or validator depends on variable data | Use deterministic fixtures and contract-appropriate validator assertions. |
| CI publishes stale snippets even when tests fail | Docs task lacks test dependency, leftover output | Configure task dependencies/outputs; fail pipeline on test or include errors. |

## 14. Hands-on Exercise

Suppose you are building an inventory API with these HTTP operations:

| Request | Expected status | Headers/body to verify | Identifier |
| --- | --- | --- | --- |
| `GET /api/inventory/42` | `200 OK` | JSON `Content-Type`, body `sku`/`available`/`quantity` | `inventory-get` |
| `POST /api/inventory` | `201 Created` | `Location`, body with new ID | `inventory-create` |
| `DELETE /api/inventory/42` | `204 No Content` | Empty body | `inventory-delete` |
| `GET /api/inventory/999` | `404 Not Found` | Error body per chosen schema | `inventory-not-found` |
| `GET /api/inventory/42` with `If-None-Match` | `304 Not Modified` if validator matches | `ETag`, empty body | `inventory-not-modified` |

Tasks:

1. Prepare stable API endpoints and fixtures; write tests for at least the first four branches, adding the `304` branch if the API supports conditional requests.
2. Assert status, meaningful headers, and schema-compliant body. Use `content().string("")` to check empty-body cases in MockMvc.
3. Attach `document(...)` with independent identifiers. For `200`, `201`, and `404`, generate `response-fields.adoc` from appropriate descriptors; for `204`/`304`, do not document a JSON body.
4. Intentionally add an undocumented field to the `200` response without adding it to `responseFields(...)` to observe strict failure; then update docs to match.
5. Open `http-response.adoc`, `response-headers.adoc`, and `response-fields.adoc`. Explain the difference between the **response recording** and the **contract description tables**.
6. Try adding `prettyPrint()` inside `preprocessResponse(...)` and verify that assertions on the real response behave identically.
7. Include snippets in Asciidoctor, run the pipeline, and verify documentation is not published if an assertion fails.

**Completion criteria:** you can explain status, headers, and body for each response; never document a body for bodyless statuses; generate accurate snippets from verified tests; and wire documentation generation into build/CI to minimize drift between API and docs.

## References

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
