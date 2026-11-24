# Verifying Spec Endpoints Return the Right Status Code and Content-Type

An API contract describes more than just JSON data. It also specifies which HTTP status an endpoint returns, which media type the response uses, and what format the client receives in case of an error. If OpenAPI advertises `200` with `application/json` while the running application actually returns `500`, or returns `text/plain` instead of JSON, consumers may fail to handle the response even though the URL and controller still work.

With springdoc-openapi, you can verify the contract at two related layers:

1. **The OpenAPI document:** the operation declares the right status codes and response content types.
2. **The running endpoint:** an actual request receives the right status code, `Content-Type`, and corresponding body structure.

Testing both layers helps detect cases where the documentation is out of sync with the implementation as well as cases where the implementation changed without updating the contract.

## 1. Status Code and Content-Type Are Part of the Contract

Every HTTP response has a status line, headers, and optionally a body. Among these parts:

- **Status code** indicates the processing outcome at the HTTP level, such as `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `404 Not Found`.
- **Content-Type** indicates the media type of the response body, such as `application/json` or `application/problem+json`.
- **Accept** is a request header expressing the media types the client wants to receive; the server can use it for content negotiation.
- **Request Content-Type** describes the format of the body sent by the client, such as `application/json`.

Do not confuse `Accept` with `Content-Type`. Sending `Accept: application/json` from the client does not mean the request body is JSON. Conversely, `Content-Type: application/json` on a request does not guarantee the server will return JSON if the endpoint does not declare or support that format.

Consider an example endpoint for reading an order:

| Scenario | Expected Status | Expected Content-Type |
|---|---:|---|
| Order found | `200 OK` | `application/json` |
| Order not found | `404 Not Found` | `application/problem+json` |
| Malformed request body format | `415 Unsupported Media Type` | May be `application/problem+json` if the application standardizes errors in this format |
| Client requests unsupported media type | `406 Not Acceptable` | Depends on the error handler and negotiation policy |
| Order created successfully | `201 Created` | Usually `application/json` if returning a representation; may have no body depending on the contract |
| Deleted successfully, no body returned | `204 No Content` | No response body, so no Content-Type is needed |

A right status code with the wrong media type is still a contract violation. For example, if a consumer expects JSON to deserialize a `404` response but the server returns an HTML error page, the client may fail when handling the error.

## 2. Describing Status Codes and Media Types in OpenAPI

OpenAPI represents responses by status code under `responses`. Each response can declare `content` with one or more media types.

Example documentation for the get-order endpoint:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Order not found
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ProblemDetail'
~~~

Reading the contract branch by branch:

- When the order exists, the server returns status `200` and a JSON representation conforming to the `OrderResponse` schema.
- When the order does not exist, the server returns `404` and a body with media type `application/problem+json`.
- For a `204` response, typically only `description` is declared without `content` because the response has no body.

Do not declare `200` for every case simply because the controller returns an object. Error, redirect, or empty responses need to be described separately.

## 3. Declaring Responses with Springdoc Annotations

springdoc reads OpenAPI metadata from `swagger-annotations` annotations. You can describe status codes and content types using `@Operation`, `@ApiResponse`, `@Content`, and `@Schema`.

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        summary = "Get order by ID",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Order found",
                content = @Content(
                    mediaType = MediaType.APPLICATION_JSON_VALUE,
                    schema = @Schema(implementation = OrderResponse.class)
                )
            ),
            @ApiResponse(
                responseCode = "404",
                description = "Order not found",
                content = @Content(
                    mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
                    schema = @Schema(implementation = ProblemDetail.class)
                )
            )
        }
    )
    public OrderResponse getById(@PathVariable long id) {
        return orderService.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
~~~

`produces` is a Spring mapping condition that affects content negotiation at runtime. `@ApiResponse` describes the response in OpenAPI. Both declarations should stay consistent, yet they serve two distinct roles: one declares mapping behavior, and the other declares the documentation contract.

When a response supports multiple media types, declare each `@Content` or the corresponding definition in OpenAPI. Never declare `application/json` in an annotation if the controller can actually return HTML or another media type in that same scenario.

## 4. Standardizing Error Responses with ProblemDetail

Spring Framework supports `ProblemDetail` to represent errors according to Problem Details for HTTP APIs. With Spring Boot 3 and above, you can use this type to return structured errors.

Example exception handler:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            exception.getMessage()
        );
        problem.setTitle("Order not found");

        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Setting the content type explicitly helps error responses adhere to the contract. If your application has multiple error types, centralize the mapping between exceptions, status codes, and bodies in one place to avoid each controller returning a different format.

Example body:

~~~json
{
  "type": "about:blank",
  "title": "Order not found",
  "status": 404,
  "detail": "Order 42 does not exist"
}
~~~

If the application uses a custom error format instead of ProblemDetail, describe the custom schema and use the media type matching the actual body. Do not change all errors to `application/problem+json` solely in annotations while the exception handler still returns a different body shape.

## 5. Testing Spring MVC Endpoints with MockMvc

For Spring MVC applications, `MockMvc` dispatches requests through the Spring MVC infrastructure without starting a real HTTP server. It is a solid choice for verifying status, response headers, Content-Type, and body.

Assuming `OrderService` returns an order with ID `42`, a test can check:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderContractTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void getExistingOrderReturns200AndJson() throws Exception {
        mockMvc.perform(
                get("/api/orders/{id}", 42)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

The assertions verify three things:

1. The server returns status `200`.
2. The response has a Content-Type compatible with `application/json`.
3. The body contains the `id` field expected by the contract.

`contentTypeCompatibleWith` checks media type compatibility and will not fail the test merely because the response includes extra parameters such as `charset`. If the contract requires an exact header value, assert the specific header using `header().string(...)` or compare the parsed `MediaType`.

### Testing the 404 Branch

Error tests must verify both status and media type, not just check that the body contains a message:

~~~java
@Test
void getMissingOrderReturns404ProblemJson() throws Exception {
    mockMvc.perform(
            get("/api/orders/{id}", 999)
                .accept(
                    MediaType.APPLICATION_JSON,
                    MediaType.APPLICATION_PROBLEM_JSON
                )
        )
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(404))
        .andExpect(jsonPath("$.title").value("Order not found"));
}
~~~

Here the client accepts both `application/json` and `application/problem+json`: the success response uses JSON, while the error response uses Problem JSON. This is a valid contract if the OpenAPI document declares the `404` response with that exact media type.

If the API uses Spring Security, the test needs appropriate authentication/authorization setup, such as `@WithMockUser` for MVC tests. Otherwise, the request may receive `401` or `403` before reaching the controller and cause the contract test to fail for security reasons.

## 6. Verifying the OpenAPI Document Generated by Springdoc

Testing runtime responses alone is not enough. The documentation itself may be advertising the wrong status or content type. Read `/v3/api-docs` directly instead of only opening Swagger UI.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void openApiDocumentDeclaresExpectedResponses() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ))
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200'].content['application/json']"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404'].content['application/problem+json']"
        ).exists());
}
~~~

This test verifies that the document has a root-level OpenAPI version, a `200` response with `application/json` content, and a `404` response with `application/problem+json` content.

If your project's paths, groups, or media types differ from the example, adjust the JSONPath accordingly. When using API groups, check `/v3/api-docs/{groupName}`. If the documentation endpoint is protected by Spring Security, the test must have permission to read it.

Testing `/v3/api-docs` also helps catch deleted annotations, altered `@ApiResponse` definitions, or controllers no longer scanned by springdoc. This is a document contract check; it does not replace the real endpoint tests in the previous section.

## 7. Testing Spring WebFlux Applications with WebTestClient

For WebFlux applications, you can use `WebTestClient` to send requests and assert responses. When running integration tests against a real server, configure it as follows:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveOrderContractTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void getOrderReturns200AndJson() {
        webTestClient.get()
            .uri("/api/orders/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            )
            .expectBody()
            .jsonPath("$.id").isEqualTo(42);
    }
}
~~~

With WebFlux, the assertion semantics remain the same: verify status, Content-Type, and body. `WebTestClient` can work against a mock server or a live server; choose the initialization approach that matches your test goal. Use `RANDOM_PORT` when you need to verify both the running HTTP server and the actual configuration.

Do not use `MockMvc` for pure WebFlux applications. Pick the test client that matches your web stack so requests flow through the proper infrastructure.

## 8. Verifying Request Content-Type and Accept

The response contract also depends on request headers. Spring mappings can declare `consumes` and `produces`:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderResponse> create(
        @RequestBody CreateOrderRequest request) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.id());

    return ResponseEntity
        .created(location)
        .contentType(MediaType.APPLICATION_JSON)
        .body(created);
}
~~~

Testing a request that sends JSON and receives `201`:

~~~java
mockMvc.perform(
        post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(request))
    )
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", endsWith("/api/orders/42")))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));
~~~

Two negotiation error scenarios must be distinguished:

| Request | Mapping Condition | Typically Expected Result |
|---|---|---|
| Sending `Content-Type: text/plain` to an endpoint that only `consumes: application/json` | Request body does not match an accepted media type | `415 Unsupported Media Type` |
| Sending `Accept: text/html` to an endpoint that only `produces: application/json` | Server cannot produce a representation the client accepts | `406 Not Acceptable` |

These can be verified as follows:

~~~java
mockMvc.perform(
        post("/api/orders")
            .contentType(MediaType.TEXT_PLAIN)
            .content("not-json")
    )
    .andExpect(status().isUnsupportedMediaType());

mockMvc.perform(
        get("/api/orders/{id}", 42)
            .accept(MediaType.TEXT_HTML)
    )
    .andExpect(status().isNotAcceptable());
~~~

Negotiation status codes can be affected by filters, exception handlers, proxies, and content negotiation configuration. Define your application's policy and lock it down with tests. Do not assume every API must return the same error body if the application has not standardized error handling yet.

## 9. The 204 No Content Case

`204 No Content` indicates that the operation succeeded and the response has no body. Because there is no representation, you should not assert `Content-Type: application/json`.

Example delete endpoint:

~~~java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    orderService.delete(id);
}
~~~

Test:

~~~java
mockMvc.perform(delete("/api/orders/{id}", 42))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""));
~~~

Corresponding OpenAPI:

~~~yaml
responses:
  '204':
    description: Order deleted
~~~

Do not declare `content` for a 204 response if the server returns no body. A test expecting JSON on this response would be validating the wrong contract.

## 10. Comparing Runtime Responses Against OpenAPI

A minimal contract test suite should combine document tests and endpoint tests into a matrix:

| Operation | OpenAPI Response | Runtime Assertion |
|---|---|---|
| `GET /api/orders/{id}` when found | `200` + `application/json` | `isOk()` + JSON Content-Type |
| `GET /api/orders/{id}` when not found | `404` + `application/problem+json` | `isNotFound()` + Problem JSON Content-Type |
| Valid `POST /api/orders` | `201` + `application/json` and `Location` | `isCreated()` + JSON + Location |
| `POST /api/orders` with wrong Content-Type | `415` + standardized error format | `isUnsupportedMediaType()` + error media type |
| `DELETE /api/orders/{id}` succeeded | `204`, no content | `isNoContent()` + empty body |

If the documentation declares `200` while the implementation returns `201`, decide which contract is intended and fix either the controller or the documentation. Never change the assertion just to make the test pass without confirming the desired API contract.

When using springdoc, you can maintain the following tests:

- Document tests: verify `responses` has the right status codes and media types.
- Provider tests: call real endpoints and verify status/headers/body.
- Consumer tests: verify clients handle the advertised status codes and media types.

For multi-service systems, consumer-driven contract testing with Pact or Spring Cloud Contract can supplement interaction verification between providers and consumers. These tools do not replace OpenAPI documentation; they verify specific consumer interaction expectations and can run in both sides' pipelines.

## 11. Verifying Responses with Multiple Media Types

An endpoint can support multiple response formats, such as JSON and XML:

~~~java
@GetMapping(
    value = "/{id}",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}
~~~

OpenAPI should advertise both media types if the application can actually serialize both JSON and XML:

~~~yaml
responses:
  '200':
    description: Order found
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
      application/xml:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

Testing both options:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));

mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_XML
    ));
~~~

Only declare `application/xml` in OpenAPI if the application has an XML message converter and the endpoint actually returns XML. The `produces` attribute can cause Spring to select a mapping, yet if no converter supports that media type, the request can still fail.

## 12. Verifying the OpenAPI Endpoint Is Also an HTTP Contract

The documentation endpoint provided by springdoc also has its own status code and Content-Type. For the default JSON document, you can verify:

~~~java
mockMvc.perform(get("/v3/api-docs")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ))
    .andExpect(jsonPath("$.openapi").exists())
    .andExpect(jsonPath("$.paths").exists());
~~~

If the application exposes YAML at `/v3/api-docs.yaml`, check the status, headers, and content according to the exact media type returned by your springdoc version. Do not hard-code `application/yaml` or `text/yaml` by guessing; observe the response of the version in use and lock that contract in your tests.

If the documentation is protected by Spring Security, tests should verify both branches: authorized callers receive `200`, and unauthorized callers receive the appropriate rejection status. This is the HTTP contract of the OpenAPI document itself, separate from the business endpoints' contract.

## 13. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Status is right but Content-Type test fails | Controller or exception handler returns wrong media type | Check `produces`, converters, and `ResponseEntity.contentType` |
| JSON response test fails due to charset | Content-Type comparison is too strict | Use `contentTypeCompatibleWith` if charset does not need to be locked down |
| API returns 404 with an HTML body | Error page or proxy handles error before controller advice | Standardize error handling and check proxy/gateway behavior |
| OpenAPI has 200 but is missing 404 | Missing `@ApiResponse` or exception response description | Declare error responses in annotations/customizers |
| OpenAPI advertises JSON but runtime returns XML | `produces`, message converters, and annotations disagree | Check content negotiation and only advertise runtime-supported media types |
| Test receives 401/403 instead of business status | Security filter blocks request before reaching controller | Set up user/role in tests or review security policy |
| 204 test fails due to missing Content-Type | Test asserts a media type on a bodyless response | Assert only status and empty body |
| JSON request receives 415 | Missing or wrong request `Content-Type`, or `consumes` mismatch | Send the proper `Content-Type` and verify the consumes contract |
| Request receives 406 | `Accept` is incompatible with `produces` | Send a supported Accept header or adjust the contract |
| OpenAPI test returns 404 | Missing springdoc API/UI starter, docs disabled, or path changed | Check dependencies and `springdoc.api-docs.path` |
| Document test passes but runtime endpoint fails | Only checking the OpenAPI file without calling the provider | Add integration tests for actual status/headers/body |
| Swagger UI displays properly yet contract test fails | UI can render documentation even when operation responses are incomplete or wrong | Inspect `/v3/api-docs` JSON and assert directly |

## 14. Integrating Contract Tests into CI

A basic pipeline can follow these steps:

1. Build the application and initialize the Spring test context.
2. Call `/v3/api-docs` to verify the documentation generates successfully.
3. Check that the OpenAPI document contains required operations, response codes, and media types.
4. Call each critical endpoint with valid and invalid requests.
5. Verify status, Content-Type, important headers, and body.
6. Diff the new document against a baseline to detect contract changes.
7. Run consumer contract tests or smoke tests if integrated services exist.
8. Only publish artifacts when both documentation and runtime behavior satisfy the contract.

Status and media type checks usually run quickly, so they fit well in pull-request integration test suites. Tests should cover happy paths, business errors, validation errors, and negotiation behavior if advertised.

## 15. Pre-Release API Checklist

- [ ] Every operation declares an accurate success status code.
- [ ] Key error statuses such as 400, 401, 403, 404, 409, and 415 are described if the API can return them.
- [ ] Every response with a body declares an appropriate media type.
- [ ] Bodyless responses like 204 do not declare unnecessary content.
- [ ] Request `Content-Type` and `Accept` are tested explicitly.
- [ ] Error responses use a consistent format, such as `application/problem+json`.
- [ ] `@ApiResponse`/OpenAPI document aligns with controllers and exception handlers.
- [ ] Integration tests verify actual status codes and Content-Types.
- [ ] OpenAPI JSON tests verify published response codes and media types.
- [ ] Tests configure the appropriate security context when endpoints are protected.
- [ ] Pipeline checks the contract before release.

## 16. Official References

- [springdoc-openapi — Getting Started and Features](https://springdoc.org/) — how to integrate springdoc and export OpenAPI documents from Spring Boot.
- [OpenAPI Specification — Responses Object](https://spec.openapis.org/oas/latest.html#responses-object) — response structure keyed by HTTP status code.
- [OpenAPI Specification — Response Object](https://spec.openapis.org/oas/latest.html#response-object) — response and content descriptions.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — testing Spring MVC requests/responses without a real server.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — testing WebFlux and HTTP endpoints with the reactive test client.
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) — standardizing HTTP errors with ProblemDetail.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — status codes, content negotiation, and HTTP header semantics.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) — the `application/problem+json` format for error responses.

Contract testing with springdoc requires verifying both what OpenAPI advertises and what endpoints actually return. For every response branch, lock down the status code and Content-Type first, then validate the required body and headers; this ensures consumers receive the exact response types promised by the documentation.
