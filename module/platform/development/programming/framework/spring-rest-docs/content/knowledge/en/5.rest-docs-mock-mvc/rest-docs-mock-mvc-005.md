# Asserting Status, Headers, and Body Before `document`

## 1. Goal: Documentation Must Be Based on Verified HTTP Results

**Spring REST Docs** generates REST API documentation from HTTP tests using **MockMvc**, WebTestClient, or REST Assured. The tool produces snippets for requests, responses, payloads, parameters, and headers, which are then compiled into Asciidoctor/Markdown documentation in builds and CI. With **MockMvc**, the fundamental operation is `mockMvc.perform(...)`; this lesson focuses on **verifying the response before calling `document(...)`**.

Merely seeing a generated `http-response.adoc` snippet is **not enough** to conclude the API matches its contract. A good documentation test must verify at least three dimensions:

1. **HTTP status:** does the success (`200`/`201`/`204`) or error (`400`/`404`/...) code match the scenario under test?
2. **Headers:** does the response include the expected `Content-Type`, `Location`, `ETag`, trace, or cache headers? Are their values correct?
3. **Body:** does the payload have the expected format, fields, types, and business values to verify? For `204 No Content`, is the body truly empty?

Standard practice:

```java
mockMvc.perform(get("/api/orders/{id}", "ord-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value("ord-101"))
        .andDo(document("orders-get"));
```

`andExpect(...)` causes the test to **fail when HTTP behavior is wrong**. `andDo(document(...))` converts the verified HTTP operation into documentation snippets.

After this lesson, you will be able to write tests for success, resource creation, not-found error, and empty-body responses; select appropriate matchers; diagnose test failures; and include verified snippets into documentation.

## 2. Why Does the Order `andExpect` Before `andDo(document(...))` Matter?

A `ResultActions` chain typically follows this order:

```text
MockMvcRequestBuilders.get/post/delete(...)
                |
                v
         mockMvc.perform(...)
                |
                v
     DispatcherServlet processes request
                |
                v
        Actual Response
                |
          +-----+--------------------+
          |                          |
          v                          v
  andExpect(status())      andExpect(header()/content()/jsonPath())
          |                          |
          +------------+-------------+
                       |
           Only when checks pass
                       |
                       v
             andDo(document(...))
                       |
                       v
       build/generated-snippets/<identifier>/
```

In a normal call chain, if an `andExpect(...)` throws an assertion error, any `andDo(...)` placed **after** it is not executed. This prevents recording an out-of-contract response as a valid API example.

| Component | Function | Can it replace HTTP verification? |
| --- | --- | --- |
| `status().isOk()`, `status().isCreated()`, ... | Verifies status code | This is status verification. |
| `header().string(...)`, `header().exists(...)` | Verifies presence or value of headers | This is header verification. |
| `content().contentTypeCompatibleWith(...)`, `jsonPath(...)` | Verifies content type and body data | This is body verification. |
| `responseHeaders(headerWithName(...))` | Describes headers in snippets | Does not verify specific header values against business requirements. |
| `responseFields(fieldWithPath(...))` | Describes documented payload structure; can detect missing/extra fields | Does not automatically guarantee status or business values of each field. |
| `document("identifier", ...)` | Writes snippets for the HTTP operation | Does not inherently know the expected status/values that the test must assert. |

**Recommended order:** `perform → andExpect(status) → andExpect(header) → andExpect(body) → andDo(document)`. There is no technical requirement to check status before headers, but this sequence is easy to read and diagnose.

## 3. Setting Up MockMvc and Spring REST Docs

The examples use **Java 17+, Spring Boot 3.x, Spring MVC, JUnit Jupiter (JUnit 5)**, and Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If using the Spring Boot BOM, let dependency management select the compatible Spring REST Docs version. For projects not using the BOM, explicitly choose a version compatible with the Spring Framework and JUnit Jupiter versions in use.

In this lesson, `standaloneSetup` creates an independent controller with fixed data to keep assertions clear:

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

`RestDocumentationExtension` supplies `RestDocumentationContextProvider` to `@BeforeEach`, while `documentationConfiguration(...)` configures Spring REST Docs on the MockMvc builder **before `build()`**. The complete example with imports is in the next section.

For projects needing to test converters, security, `@ControllerAdvice`, and real bean wiring, switch to `webAppContextSetup(webApplicationContext)` or use Spring Boot's auto-configured MockMvc. Either way, the rule of **verifying status/headers/body before writing documentation** remains the same.

## 4. Complete Example: GET, POST, 404 Error, and 204 DELETE

We will document an order API covering four scenarios:

| HTTP Request | Status to Assert | Headers to Assert | Body to Assert |
| --- | --- | --- | --- |
| `GET /api/orders/ord-101` | `200 OK` | `Content-Type: application/json`, `ETag: "v3"` | `id`, `status`, `amount` |
| `POST /api/orders` | `201 Created` | `Location: /api/orders/ord-102` and JSON content type | `id`, `item`, `quantity`, `status` |
| `GET /api/orders/missing` | `404 Not Found` | JSON content type | `code` and `message` |
| `DELETE /api/orders/ord-102` | `204 No Content` | No JSON content type | Empty body |

The test class below includes a sample controller right in the file, suitable for reading and running standalone in a Spring MVC project with the dependencies from section 3:

```java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetOrderWhenFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "ord-101")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(HttpHeaders.ETAG, "\"v3\""))
                .andExpect(jsonPath("$.id").value("ord-101"))
                .andExpect(jsonPath("$.status").value("READY"))
                .andExpect(jsonPath("$.amount").value(12500))
                .andDo(document("orders-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Order ID")),
                        responseHeaders(
                                headerWithName(HttpHeaders.ETAG)
                                        .description("Resource version")),
                        responseFields(
                                fieldWithPath("id").description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status"),
                                fieldWithPath("amount")
                                        .description("Order amount"))));
    }

    @Test
    void documentCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .characterEncoding("UTF-8")
                        .content("""
                                {"item":"book","quantity":2}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/orders/ord-102"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("ord-102"))
                .andExpect(jsonPath("$.item").value("book"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.status").value("CREATED"))
                .andDo(document("orders-create",
                        requestFields(
                                fieldWithPath("item")
                                        .description("Ordered item"),
                                fieldWithPath("quantity")
                                        .description("Ordered quantity")),
                        responseHeaders(
                                headerWithName(HttpHeaders.LOCATION)
                                        .description("URI of the newly created order")),
                        responseFields(
                                fieldWithPath("id").description("New order ID"),
                                fieldWithPath("item").description("Item"),
                                fieldWithPath("quantity").description("Quantity"),
                                fieldWithPath("status")
                                        .description("Order status"))));
    }

    @Test
    void documentGetOrderNotFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "missing")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message")
                        .value("Order not found"))
                .andDo(document("orders-get-not-found",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Searched order ID")),
                        responseFields(
                                fieldWithPath("code").description("Error code"),
                                fieldWithPath("message")
                                        .description("Error message details"))));
    }

    @Test
    void documentDeleteOrderNoContent() throws Exception {
        mockMvc.perform(delete("/api/orders/{id}", "ord-102"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andExpect(header().doesNotExist(HttpHeaders.CONTENT_TYPE))
                .andDo(document("orders-delete",
                        pathParameters(
                                parameterWithName("id")
                                        .description("ID of the order to delete"))));
    }

    @RestController
    public static class OrderController {

        @GetMapping(
                value = "/api/orders/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> find(
                @PathVariable("id") String id) {
            if ("missing".equals(id)) {
                return ResponseEntity.status(HttpStatus.NOT_FOUND)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of(
                                "code", "ORDER_NOT_FOUND",
                                "message", "Order not found"));
            }
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ETAG, "\"v3\"")
                    .body(Map.of(
                            "id", id,
                            "status", "READY",
                            "amount", 12500));
        }

        @PostMapping(
                value = "/api/orders",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> create(
                @RequestBody Map<String, Object> request) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .location(URI.create("/api/orders/ord-102"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "id", "ord-102",
                            "item", request.get("item"),
                            "quantity", request.get("quantity"),
                            "status", "CREATED"));
        }

        @DeleteMapping("/api/orders/{id}")
        public ResponseEntity<Void> deleteById(
                @PathVariable("id") String id) {
            return ResponseEntity.noContent().build();
        }
    }
}
```

### Reading the Verification Results

- **Successful GET:** `status().isOk()` verifies `200`; `contentTypeCompatibleWith(APPLICATION_JSON)` verifies the body is JSON; `header().string(ETAG, ...)` matches the resource version; the three `jsonPath(...)` assertions protect important business values. Only then does the test record `orders-get`.
- **POST Creation:** `status().isCreated()` verifies `201`; the `Location` header must point to the new resource; the body must contain the expected ID, item, quantity, and status. `requestFields(...)` describes the input body; `responseFields(...)` describes the output.
- **Not-Found GET:** `404` is the **expected result** of the error scenario, not a sign of failed documentation. The test asserts both error code and message, then generates a separate `orders-get-not-found` snippet set.
- **DELETE:** `204` has an empty response body, so the test asserts an empty string and does not expect a JSON `Content-Type`. Do not use `responseFields(...)` for responses without a payload.

In a real application, controllers and services usually live in `src/main/java`. The example nests the controller inside the test class for self-contained presentation and deterministic data; this test does not verify databases or real wiring.

## 5. Asserting Status: Exact Codes Over Code Families

Common matchers:

| Expectation | Matcher | Scenario |
| --- | --- | --- |
| `200 OK` | `status().isOk()` | Resource read succeeded, returns payload. |
| `201 Created` | `status().isCreated()` | POST created a new resource. |
| `202 Accepted` | `status().isAccepted()` | Asynchronous processing accepted. |
| `204 No Content` | `status().isNoContent()` | DELETE succeeded, no response body. |
| `400 Bad Request` | `status().isBadRequest()` | Invalid request data. |
| `401 Unauthorized` | `status().isUnauthorized()` | Authentication required. |
| `403 Forbidden` | `status().isForbidden()` | User lacks sufficient permissions. |
| `404 Not Found` | `status().isNotFound()` | Resource not found. |
| `409 Conflict` | `status().isConflict()` | Resource state conflict. |
| Custom status | `status().is(422)` | API uses a code without a dedicated matcher. |

`status().is2xxSuccessful()` or `status().is4xxClientError()` only verifies a status **family**. They are useful when the contract permits multiple statuses, whereas endpoint documentation usually needs a specific scenario. For instance, using `is2xxSuccessful()` may miss a `POST` returning `200` instead of `201`.

A common logical mistake is writing:

```java
// Overly broad check: 200 OK passes even though 201 Created is expected.
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"item\":\"book\",\"quantity\":2}"))
        .andExpect(status().is2xxSuccessful());
```

When the contract is `201 Created`, use `status().isCreated()` and also verify `Location` and the response body.

If the same endpoint returns different statuses depending on input data, write **separate tests** with separate identifiers (e.g., `orders-get` and `orders-get-not-found`) so success and error snippets do not overwrite each other.

## 6. Asserting Headers: Presence, Absence, and Exact Values

Headers can determine how clients process responses. Assertions should reflect the contract rather than merely listing header names.

```java
.andExpect(header().exists(HttpHeaders.LOCATION))
.andExpect(header().string(
        HttpHeaders.LOCATION, "/api/orders/ord-102"))
.andExpect(header().string(HttpHeaders.ETAG, "\"v3\""))
.andExpect(header().doesNotExist("X-Debug-Token"))
```

These are **illustrative calls** to chain onto appropriate `ResultActions`, not a sequence to apply blindly to every endpoint.

Key points to note:

- **`Location`:** for `201`, verify the URI of the newly created resource; `header().exists(...)` only confirms the header is present, while `header().string(...)` verifies the expected value.
- **`Content-Type`:** this is also an HTTP header, though it is usually more readable to assert via `content().contentType(...)` or `content().contentTypeCompatibleWith(...)`.
- **`ETag`:** valid ETag values usually include double quotes, e.g., `"v3"`. Match the exact string format published by the endpoint.
- **Dynamic headers:** correlation IDs or request IDs generated randomly should not be checked against a fixed constant in an environment generating dynamic IDs. Check `exists(...)` or use a format matcher, and verify correlation with the request if required by the contract.
- **Sensitive headers:** do not use real tokens, cookies, or secrets in test examples that end up in public snippets.

### Distinguishing `Content-Type` and `Accept` Verification

`Accept` is a **request** header indicating the format the client wants to receive. The **response** `Content-Type` describes the format the server actually returned:

```java
mockMvc.perform(get("/api/orders/{id}", "ord-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
```

Setting `accept(APPLICATION_JSON)` is **not enough** to prove the server returned JSON. If `Content-Type` must strictly equal `application/json`, use `content().contentType(MediaType.APPLICATION_JSON)`. If charset parameters or compatible media types may be present, `contentTypeCompatibleWith(...)` is more flexible.

For `204 No Content`, do not apply JSON content-type matchers as with `200`. Assert the absence of a body and only verify headers that truly belong to the contract.

## 7. Asserting Body: Content, Structure, and Empty Cases

### Using `jsonPath` to Verify Important JSON Data

```java
.andExpect(jsonPath("$.id").value("ord-101"))
.andExpect(jsonPath("$.status").value("READY"))
.andExpect(jsonPath("$.amount").value(12500))
```

The advantage of `jsonPath` is that it does not depend on JSON field ordering. When an API returns a list, you can check an element or element count using JSONPath and appropriate matchers:

```java
// Chained after mockMvc.perform(...), for a body containing items.
.andExpect(jsonPath("$.items[0].id").value("ord-101"))
.andExpect(jsonPath("$.items[0].status").value("READY"))
```

For optional fields, distinguish clearly:

- **Required** field per contract: assert `exists()` or a specific value.
- **Disallowed** field in response: use a matcher verifying absence.
- **Nullable or optional** field: design assertions per contract, avoiding asserting a fixed value when there is no such guarantee.

When verifying the full JSON body, use a JSON matcher supported by the installed test libraries, avoiding raw string comparisons if key order or whitespace does not matter.

### Checking Plain Text or Empty Responses

For an endpoint returning plain text:

```java
mockMvc.perform(get("/api/health"))
        .andExpect(status().isOk())
        .andExpect(content().string("UP"));
```

For `204 No Content`:

```java
mockMvc.perform(delete("/api/orders/{id}", "ord-102"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""))
        .andDo(document("orders-delete"));
```

The `DELETE` snippet above is an abbreviated example **valid only when the endpoint behaves accordingly**. If a `path-parameters.adoc` snippet is needed, add `pathParameters(...)` as in the complete example.

### Why Doesn't `responseFields(...)` Replace `jsonPath(...)`?

Spring REST Docs' `responseFields(...)` checks and documents payload **structure**. It helps catch undocumented fields or descriptors pointing to non-existent fields, but it does not fully express expected business values.

For example, suppose the API returns:

```json
{
  "id": "ord-101",
  "status": "CANCELLED",
  "amount": 12500
}
```

If the test only uses:

```java
responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Status"),
        fieldWithPath("amount").description("Amount"))
```

these descriptors still document the three present fields. However, if the test is supposed to verify a `READY` order, `jsonPath("$.status").value("READY")` is what catches the wrong value. Thus **business assertions and snippet structural checks complement each other**.

## 8. Separating Success and Error Tests Before Generating Documentation

Some errors do not break JSON formatting; for example, an API may return `404` with the payload:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
```

If you only assert `Content-Type` and `responseFields(...)`, a test could record an error response into a success scenario's documentation without noticing the wrong status. Therefore:

```java
mockMvc.perform(get("/api/orders/{id}", "missing"))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
        .andDo(document("orders-get-not-found",
                pathParameters(
                        parameterWithName("id").description("Order ID")),
                responseFields(
                        fieldWithPath("code").description("Error code"),
                        fieldWithPath("message").description("Message"))));
```

For authentication/authorization errors (`401`/`403`), configure the security filter in the test scope and assert the exact expected status and body/headers. If standalone MockMvc has not applied the application's security, a `200` result from the controller cannot serve as evidence that the endpoint requires no authentication.

In CI, documentation tests must not hide failures by removing strict matchers or turning every field into `optional()`/`ignored()`. Those methods are only appropriate when the API contract genuinely allows optional fields or explicitly requires ignoring specific fields.

## 9. How Should You Diagnose Assertion Failures?

### Printing the Result to Inspect the Actual Response

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/orders/{id}", "ord-101")
                .accept(MediaType.APPLICATION_JSON))
        .andDo(print())
        .andExpect(status().isOk());
```

`print()` is helpful for inspecting the request, handler, status, headers, and body when a test fails. Use appropriate test data because logs can expose sensitive headers, cookies, or payloads.

### Common Causes and Resolutions

| Failed Check | Possible Cause | Resolution |
| --- | --- | --- |
| Expected `200` but got `404` | Wrong URL/method or controller not registered | Check `@GetMapping`, URI template, and MockMvc setup. |
| Expected `201` but got `200` | Endpoint returned status violating contract | Fix controller or align contract, then update test and docs. |
| Expected `201` but got `415` | Request `Content-Type` incompatible | Set `contentType(APPLICATION_JSON)`, check `consumes` and converters. |
| Expected JSON but wrong `Content-Type` | Server returned HTML error, plain text, or different converter | Read response, status, and converter/advice configuration. |
| `Location` header wrong or missing | Controller did not set new resource URI | Check `ResponseEntity.created(...)` and expected path. |
| `ETag` header mismatch | ETag string formatting, quotes, or version differs | Check actual header and ETag generation logic. |
| `jsonPath` cannot find field | Body is not expected JSON, field name differs, or response is an error | Check status, actual body, JSONPath, and API contract. |
| `jsonPath` passes but `responseFields` fails | Undocumented field present or descriptor mismatch | Document all actual fields; use `optional()`/`ignored()` when allowed by contract. |
| `204` but body is not empty | Endpoint is returning a payload | Fix controller or update contract if another status is intended. |
| No `generated-snippets` | `document(...)` not called, test stopped at matcher, or REST Docs setup missing | Check test results, extension, and builder before looking at output path. |

If you need to inspect a relatively simple response, you can obtain `MvcResult` after the matchers and read `getResponse().getContentAsString()`, though `status`, `header`, `content`, and `jsonPath` are usually clear enough.

## 10. Compiling Verified Snippets into Documentation

Run tests with Gradle:

```bash
./gradlew test
```

On Windows, you can use `gradlew.bat test`. With default configurations, Gradle snippets are usually in `build/generated-snippets/`; Maven snippets are usually in `target/generated-snippets/`. After running the section 4 example, a condensed directory structure may look like:

```text
build/generated-snippets/
├── orders-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── path-parameters.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
├── orders-create/
│   ├── request-fields.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
├── orders-get-not-found/
│   ├── http-response.adoc
│   └── response-fields.adoc
└── orders-delete/
    └── http-response.adoc
```

This is a **condensed representative list**, not an exhaustive file listing. Spring REST Docs may also create `curl-request.adoc`, `httpie-request.adoc`, `request-body.adoc`, and `response-body.adoc` depending on the version, configuration, and default snippet set.

Asciidoctor example:

```adoc
= Orders API

== Get Order

include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/path-parameters.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-headers.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]

== Create Order

include::{snippets}/orders-create/request-fields.adoc[]
include::{snippets}/orders-create/http-response.adoc[]
include::{snippets}/orders-create/response-headers.adoc[]

== Order Not Found

include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]

== Delete Order

include::{snippets}/orders-delete/http-response.adoc[]
```

The `{snippets}` attribute must point to the correct output directory. If the output product uses Markdown, use appropriate templates/converters or embedding mechanisms because default snippets are usually AsciiDoc. The build/CI sequence should be **HTTP tests → snippet generation → Asciidoctor/Markdown compilation → publishing**, so new documentation is only built after HTTP verifications pass.

## 11. Practice Exercises

1. **Test wrong status:** change `201` in the POST controller to `200` while keeping `status().isCreated()`; explain why the test fails before `document(...)`.
2. **Test header:** remove the `Location` header from POST while keeping `header().string(...)`; fix the controller to restore the contract.
3. **Test body:** change `status: READY` to `CANCELLED` in GET while keeping `jsonPath("$.status").value("READY")`; observe where the failure occurs.
4. **Document errors:** create a `400 Bad Request` test for a request missing a required field; assert status, error JSON structure, and use a separate identifier.
5. **No Content:** intentionally return JSON on DELETE and observe why `content().string("")` fails; restore the `204` response with an empty body.
6. **Integrate documentation:** re-run tests, include `orders-get`, `orders-create`, `orders-get-not-found`, and `orders-delete` into Asciidoctor/Markdown documentation, and wire snippet generation into CI.

**Success criteria:** each test clearly verifies the status, headers, and body required by its scenario; invalid matchers fail the test; snippets are recorded only when all preceding assertions pass; documentation is compiled from freshly generated snippets.

## 12. Checklist Before Calling `document(...)`

- [ ] Determine the exact expected status for each scenario: success, creation, error, or no content.
- [ ] Verify important headers with appropriate matchers, including **values** when specifically required.
- [ ] Verify the response `Content-Type` if the endpoint returns a structured body.
- [ ] Verify business fields/values with `jsonPath(...)` or equivalent content matchers.
- [ ] For `204`, verify an empty body; avoid declaring `responseFields(...)` when there is no payload.
- [ ] Place `andExpect(...)` before `andDo(document(...))` to avoid documenting an out-of-contract response.
- [ ] Document actual fields, parameters, and headers; use separate identifiers per endpoint and error scenario.
- [ ] Ensure build/CI tasks only compile documentation from snippets generated after tests pass.

**Remember:** `andExpect(status/header/body)` protects **the HTTP behavior promised by the application**; `document(...)` records **verified data** to generate documentation. When these two parts are ordered properly, REST API documentation stays verifiable alongside tests and never silently publishes an out-of-contract response.
