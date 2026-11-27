# Documenting errors when a resource ID does not exist

## Lesson Objectives

A request may match a route and pass the right **resource ID** type, yet the requested resource does not exist. For example, **GET /api/orders/9999** can match the **/api/orders/{orderId}** route and convert **9999** into a **Long**, yet the service finds no order. APIs typically return **404 Not Found** in that case.

With **Spring REST Docs**, tests can document both successful requests and error responses. When recording a resource-not-found error, accurately describe the path parameter, HTTP status code, and error response structure so callers know which resource was looked up, what the error means, and how to handle it.

This lesson belongs to the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; compiling Asciidoctor/Markdown documentation and integrating it into build/CI.

After this lesson, you will be able to:

- Distinguish a **non-existent resource ID** from an unmatched route, a malformed ID, and an authorization error.
- Design a stable **404** response without leaking internal details.
- Write tests for both existing-resource IDs and non-existent-resource IDs.
- Use **pathParameters(...)** together with response snippets to document an error-producing request.
- Generate response body, response fields, and HTTP response snippets from tests.
- Verify the error contract using MockMvc, WebTestClient, or REST Assured.
- Include error snippets into Asciidoctor documentation and CI pipelines.

## 1. 404 due to missing resource vs. 404 due to missing route

Consider the endpoint:

~~~text
GET /api/orders/{orderId}
~~~

Both of the following requests may receive HTTP **404**, yet for different reasons:

| Request | Stage | Meaning |
| --- | --- | --- |
| **GET /api/orders/9999** | Route matches, ID binds; service queries and finds no order | **Resource not found** |
| **GET /api/missing/9999** | No handler matches the path | **Route not found** |

Other errors also produce different HTTP codes:

| Request | Cause | Typical status code |
| --- | --- | --- |
| **GET /api/orders/abc** when controller expects **Long** | Value cannot convert to ID type | **400 Bad Request** |
| **POST /api/orders/42** when only GET mapping exists | Method not supported on that resource path | **405 Method Not Allowed** |
| **GET /api/orders/42** without caller permission | Not authorized to access the resource | **403 Forbidden** or sometimes **404** under policies hiding resource existence |
| **GET /api/orders/9999** when ID is valid but no record exists | Resource not found | **404 Not Found** |

The actual status code returned depends on other routes, exception handlers, and the application's security policy. Therefore, tests should not merely assert that a request "failed"; clearly verify the **cause** and the **HTTP contract** published by the API.

~~~mermaid
flowchart TD
    A["GET /api/orders/9999"] --> B{"Route /api/orders/{orderId} matches?"}
    B -->|No| C["No handler: typically 404"]
    B -->|Yes| D["Bind orderId"]
    D --> E{"Is ID the right type?"}
    E -->|No| F["Binding error: typically 400"]
    E -->|Yes| G["Service looks up order"]
    G --> H{"Resource found?"}
    H -->|No| I["Resource not found: 404"]
    H -->|Yes| J["Return success response"]
~~~

This distinction matters when writing documentation: a **404 due to non-existent ID** must pass through the right route and right data type before arising from the resource-lookup layer.

## 2. Designing a stably structured error response

Do not return stack traces, table names, SQL, file paths, or internal details in error responses. The API should return a stable structure containing enough information for clients to identify the error.

Example response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found",
  "resource": "order",
  "resourceId": "9999"
}
~~~

| Field | Meaning |
| --- | --- |
| **code** | Stable error code for client branching logic |
| **message** | Human-readable message for users or clients |
| **resource** | Type of resource not found |
| **resourceId** | Requested ID value, if API policy permits exposing it |

For some multi-tenant APIs or sensitive resources, do not confirm whether an ID exists in another tenant. In that case, you can use the exact same **404** response for both "does not exist" and "outside authorized visibility scope" to avoid information leakage.

Another option is using the HTTP **Problem Details** standard (RFC 9457), with fields such as **type**, **title**, **status**, **detail**, and **instance**. If the application chooses this format, document the exact media type and structure the API actually returns. Do not mix two error formats on the same endpoint without an explicit contract.

## 3. Implementing controller and exception handler

The example uses **Spring Boot 3.x**, **Java 17+**, Spring MVC, and a custom domain exception.

### 3.1. Exception and response model

~~~java
class OrderNotFoundException extends RuntimeException {
    private final Long orderId;

    OrderNotFoundException(Long orderId) {
        super("Order not found");
        this.orderId = orderId;
    }

    Long getOrderId() {
        return orderId;
    }
}

record ApiError(
    String code,
    String message,
    String resource,
    String resourceId
) {}
~~~

The service throws an exception when the resource does not exist:

~~~java
import org.springframework.stereotype.Service;

@Service
class OrderService {

    OrderResponse getOrder(Long orderId) {
        // Illustration: only order 42 exists in sample data.
        if (!orderId.equals(42L)) {
            throw new OrderNotFoundException(orderId);
        }
        return new OrderResponse(orderId, "OPEN");
    }
}

record OrderResponse(Long id, String status) {}
~~~

The controller only handles mapping and delegates to the service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{orderId}")
    OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
        return orderService.getOrder(orderId);
    }
}
~~~

The exception handler translates domain errors into structured HTTP responses:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order not found",
            "order",
            exception.getOrderId().toString()
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

In a real project, the service queries a repository instead of checking a hardcoded ID. The exception handler must conform to the API's shared response standard. If the application already has a shared **@ControllerAdvice**, add the error handler there rather than creating competing handlers.

## 4. Writing tests for success and not-found cases

A 404 test must prove that the request **hit the right route**. With MockMvc, use **RestDocumentationRequestBuilders.get(...)** with the URI template and pass an ID value of a valid type.

### 4.1. Dependency configuration

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

The example assumes Spring Boot dependency management/BOM manages compatible versions. If using Maven, configure the corresponding dependencies and the snippets directory in **target/generated-snippets**.

### 4.2. Test generating snippet for successful response

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void documentExistingOrder() throws Exception {
        given(orderService.getOrder(42L))
            .willReturn(new OrderResponse(42L, "OPEN"));

        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andDo(document("order-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("ID of the order to look up")
                )
            ));
    }
}
~~~

This is the success test to pair with error documentation. In the next examples, add test methods to the same class above.

### 4.3. 404 test for non-existent resource ID and generating error snippets

~~~java
@Test
void documentOrderNotFound() throws Exception {
    given(orderService.getOrder(9999L))
        .willThrow(new OrderNotFoundException(9999L));

    mockMvc.perform(get("/api/orders/{orderId}", 9999L)
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
        .andExpect(jsonPath("$.resourceId").value("9999"))
        .andDo(document("order-get-not-found",
            pathParameters(
                parameterWithName("orderId")
                    .description("ID of the order to look up")
            ),
            responseFields(
                fieldWithPath("code")
                    .description("Stable error code for clients"),
                fieldWithPath("message")
                    .description("Error message"),
                fieldWithPath("resource")
                    .description("Type of resource not found"),
                fieldWithPath("resourceId")
                    .description("Requested resource ID")
            )
        ));
}
~~~

The static imports for `fieldWithPath(...)` and `responseFields(...)` are already declared in the import section of **OrderDocumentationTest**. In the error snippet:

- **pathParameters(...)** still describes **orderId** because the request goes through the detail route.
- **responseFields(...)** describes the error payload received by the client.
- **andExpect(status().isNotFound())** verifies the HTTP status code.
- **andExpect(jsonPath(...))** verifies the response has the expected error code and ID.

The default **http-response.adoc** snippet displays the status, headers, and response body. **responseFields(...)** adds a table describing the JSON structure so readers understand each field in the error payload.

### 4.4. Do not call this a routing error

In the test above, the URL **/api/orders/9999** has the right template and the ID **9999** converts to **Long**. The mocked service throws **OrderNotFoundException**, and the handler produces HTTP 404. This is **resource not found**.

If you want to test a non-existent route, use a different request such as **GET /api/missing/9999**, and assert 404 separately. Do not attach an **orderId** descriptor to that request if its URI template does not contain that variable.

## 5. Snippets useful for documenting errors

Spring REST Docs generates several useful snippets for errors:

| Snippet | Contents |
| --- | --- |
| **path-parameters.adoc** | Names and descriptions of request path variables |
| **http-request.adoc** | Request method, URI, and headers |
| **http-response.adoc** | Response status, headers, and body |
| **response-body.adoc** | Raw or formatted response body |
| **response-fields.adoc** | Table describing the error payload structure |

Expected generated directory:

~~~text
build/generated-snippets/
└── order-get-not-found/
    ├── path-parameters.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── response-body.adoc
    └── response-fields.adoc
~~~

The actual list depends on default snippets and the snippets you request inside **document(...)**. Spring REST Docs normally generates default snippets such as **http-request.adoc** and **http-response.adoc** when integrated properly; payload snippets must be declared explicitly.

### 5.1. Using strict responseFields

With:

~~~java
responseFields(
    fieldWithPath("code").description("Error code"),
    fieldWithPath("message").description("Message")
)
~~~

Spring REST Docs checks documented fields against the response payload in strict mode. If the response also includes **resource** and **resourceId** without describing them, the snippet can report undocumented fields.

If the response has extra fields you do not yet want to document in the current lesson, consider the **ignored()** descriptor or **relaxedResponseFields(...)** only when genuinely justified. For public API contracts, prefer documenting all fields so error structure changes are caught early.

## 6. Documenting errors in Asciidoctor

In **src/docs/asciidoc/index.adoc**, you can create a dedicated section for the 404 error:

~~~asciidoc
== Get order by ID

=== Path parameters

include::{snippets}/order-get/path-parameters.adoc[]

=== Successful response

include::{snippets}/order-get/http-response.adoc[]

=== When the order does not exist

Request:

include::{snippets}/order-get-not-found/http-request.adoc[]

Path parameters:

include::{snippets}/order-get-not-found/path-parameters.adoc[]

Response:

include::{snippets}/order-get-not-found/http-response.adoc[]

Error response fields:

include::{snippets}/order-get-not-found/response-fields.adoc[]
~~~

This lets readers see both the success response and error response for the same endpoint. Both cases use distinct snippet IDs to avoid overwriting generated files.

### 6.1. Gradle integration

The example below assumes the **org.asciidoctor.jvm.convert** plugin is already configured:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

The Asciidoctor task must run after the snippet-generating tests. In CI, a failing test assertion, missing snippet, or undocumented response structure change must halt the pipeline before publishing documentation.

For final output in Markdown, use a suitable conversion system or include mechanism. **include::...[]** is Asciidoctor syntax, not standard Markdown syntax.

## 7. Testing with WebTestClient and REST Assured

The principle stays the same: send a request with a URI template, verify the HTTP status and response body, and attach path parameters together with response fields snippets.

### 7.1. WebTestClient

In a test where REST Docs is configured for **WebTestClient**:

~~~java
webTestClient.get()
    .uri("/api/orders/{orderId}", 9999L)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .consumeWith(document("order-not-found-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("ID of the order to look up")
        ),
        responseFields(
            fieldWithPath("code").description("Stable error code"),
            fieldWithPath("message").description("Error message"),
            fieldWithPath("resource").description("Resource type"),
            fieldWithPath("resourceId").description("Requested resource ID")
        )
    ));
~~~

Here **document(...)** is imported from **WebTestClientRestDocumentation**. The client must be configured with REST Docs beforehand; **pathParameters(...)** and **responseFields(...)** still use the shared documentation API.

### 7.2. REST Assured

With a **RequestSpecification spec** configured with REST Docs:

~~~java
given(spec)
    .filter(document("order-not-found-rest-assured",
        pathParameters(
            parameterWithName("orderId")
                .description("ID of the order to look up")
        ),
        responseFields(
            fieldWithPath("code").description("Stable error code"),
            fieldWithPath("message").description("Error message"),
            fieldWithPath("resource").description("Resource type"),
            fieldWithPath("resourceId").description("Requested resource ID")
        )
    ))
    .pathParam("orderId", 9999L)
    .when()
    .get("/api/orders/{orderId}")
    .then()
    .statusCode(404);
~~~

Here **document(...)** belongs to **RestAssuredRestDocumentation**. **pathParam(...)** assigns the ID value; the snippets record the **orderId** variable and the error payload. You can add JSON content assertions if the test needs to verify specific error codes.

## 8. Best practices when documenting 404

### 8.1. Keep error responses stable

Clients usually rely on machine-readable error codes rather than human-language sentences that may change across locales. Prefer a stable **code**, use message for display purposes, and avoid making tests overly brittle on exact wording if the API does not commit to fixed messages.

### 8.2. Do not expose sensitive data

Never return stack traces, SQL queries, table names, server information, or data belonging to resources the caller is not authorized to view. The **resourceId** field should only appear if security policy allows echoing back the ID sent by the client itself. In multi-tenant systems, be careful not to reveal that a resource exists in another tenant.

### 8.3. Distinguish type-conversion errors from not-found errors

Sending ID **abc** to **@PathVariable Long** typically causes a 400 error before the service executes a lookup. An ID like **9999** that is type-valid yet matches no data produces a 404 from the service. Both cases should have separate tests because they represent two distinct failure modes.

### 8.4. Do not make documentation tests depend on unstable data

Snippet-generating tests should use fixed fixtures, mocks, or reproducible test data. Using a shared database or uncontrolled random IDs can make 404 outcomes pass intermittently, making documentation and CI flaky.

## 9. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Valid-ID request unexpectedly returns 404 | Test data is missing or service mock is misconfigured | Create explicit fixtures and verify mock invocations |
| Test expects 404 but receives 400 | Malformed ID or binding failure occurs before the service | Use a type-valid ID when testing resource-not-found |
| 404 test does not generate path snippet | URI template not used or **document(...)** missing | Use REST Docs request builders and descriptors |
| response-fields snippet reports missing/extra fields | Descriptors do not match error payload | Update descriptions or use ignored/relaxed intentionally |
| Error response contains a stack trace | Handler returns internal exception | Map exceptions to a safe public response |
| Non-existent route shares snippet ID with missing resource | Tests do not separate causes | Use distinct snippet IDs and document scenarios clearly |
| Documentation displays stale response | Snippets were not regenerated or old output remained | Ensure tests are a dependency of Asciidoctor and clean builds when needed |
| ID existing in another account is still returned | Query filters only by child ID | Scope queries by owner/tenant and test ownership |

## 10. Hands-on exercise

Given the API:

~~~text
GET /api/customers/{customerId}
~~~

Contract:

- **customerId** is a UUID.
- If the customer exists, return HTTP 200 and customer JSON.
- If the UUID is valid but no customer exists, return HTTP 404 with a payload containing **code**, **message**, **resource**, and **resourceId**.
- If the UUID is malformed, return HTTP 400.

Perform the following:

1. Write a controller/service and an exception handler for **CustomerNotFoundException**.
2. Write a successful MockMvc test using URI template **/api/customers/{customerId}**, generating snippets with **pathParameters(...)**.
3. Write a test for a valid but non-existent UUID, asserting 404 and the error payload fields; use snippet ID **customer-not-found**.
4. Write a test for a malformed UUID, asserting 400; explain why it is not a resource-not-found error.
5. Include **path-parameters.adoc**, **http-response.adoc**, and **response-fields.adoc** in Asciidoctor.
6. Run tests and build docs; try removing one response field descriptor and observe how REST Docs detects the payload mismatch.

Sample descriptors for the error case:

~~~java
pathParameters(
    parameterWithName("customerId")
        .description("UUID identifying the customer")
),
responseFields(
    fieldWithPath("code").description("Stable error code"),
    fieldWithPath("message").description("Error message"),
    fieldWithPath("resource").description("Resource type"),
    fieldWithPath("resourceId").description("Requested UUID")
)
~~~

**Completion criteria:** tests distinguish 200, 404 due to non-existent resource, and 400 due to malformed ID; snippets accurately describe path parameters and error response; documentation builds cleanly from test-generated snippets.

## Key Takeaways

When a **resource ID has a valid type yet no resource exists**, APIs typically return **404 Not Found** after the route matches and the service performs a lookup. Distinguish this case from non-existent routes, 400 binding errors, and authorization errors. In Spring REST Docs, use **pathParameters(...)** to describe the requested ID, combined with **responseFields(...)** and **http-response.adoc** to capture the error payload. Test both success and not-found cases with stable data, then embed snippets into Asciidoctor and CI so the error contract stays continuously verified.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring Framework @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptions.html), and [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).
