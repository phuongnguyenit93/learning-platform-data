# Verifying parameter names match actual routes

## Lesson Objectives

A Spring REST Docs test may successfully generate a path parameters table, yet the documentation can still be wrong if **the variable name in the descriptor, the URI template used to construct the request, and the actual controller route are inconsistent**. For example, the controller declares `/api/orders/{orderId}`, while the test uses `/api/orders/{id}` and descriptor `parameterWithName("orderId")`. A good test needs to catch this mismatch before documentation enters the build or CI.

This lesson belongs to the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating request, response, payload, parameter, and header snippets; compiling Asciidoctor/Markdown documentation and integrating it into the build/CI pipeline.

After this lesson, you will be able to:

- Distinguish variable names across **controller mappings**, **test request URI templates**, and **REST Docs descriptors**.
- Understand the verification scope of `pathParameters(...)`: it checks descriptors against the URI template information of the documented request.
- Write tests invoking real controllers to detect when a route or variable name has changed.
- Detect errors such as misspelled names, missing descriptors, extra descriptors, wrong path prefixes, and incompatible mappings.
- Build shared helpers or conventions to reduce situations where a name changes in one place and is forgotten in another.
- Generate stable snippets, include them in Asciidoctor, and ensure CI runs tests before building documentation.

## 1. Three places where variable names must stay synchronized

Suppose an API retrieves order details:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
    // ...
}
~~~

To generate accurate documentation, the following three places must be consistent:

| Declaration site | Correct example | Responsibility |
| --- | --- | --- |
| Controller mapping | `/api/orders/{orderId}` | Defines the route mapped by Spring |
| URI template in HTTP test | `get("/api/orders/{orderId}", 42L)` | Builds a request with a variable named `orderId` |
| REST Docs descriptor | `parameterWithName("orderId")` | Describes the variable displayed in the snippet |

In the controller, `@PathVariable("orderId")` binds the Java variable to the path variable name. In the test, **RestDocumentationRequestBuilders.get(...)** preserves the URI template so Spring REST Docs knows the variable name. The descriptor **parameterWithName("orderId")** documents that exact name.

Verification flow:

~~~mermaid
flowchart TD
    A["Controller mapping: /api/orders/{orderId}"] --> B["MockMvc request template: /api/orders/{orderId}"]
    B --> C["Spring selects handler and binds orderId"]
    C --> D["document(..., pathParameters(...))"]
    D --> E["REST Docs checks descriptors against request template"]
    E --> F["path-parameters.adoc"]
    C --> G["HTTP status and response assertions"]
    G --> H["Test confirms actual route works properly"]
~~~

Key takeaway: **REST Docs sees the request URI template passed to the test client; it does not read controller source code to compare mapping strings automatically**. Actually sending the request through Spring MVC/WebFlux and asserting the response is what tests the deployed route. Therefore, you must combine descriptor validation with HTTP assertions.

## 2. Correct example with MockMvc

The example uses **Spring Boot 3.x**, **Java 17+**, **JUnit 5**, and **spring-restdocs-mockmvc**. Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{orderId}")
    OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
        return new OrderResponse(orderId, "OPEN");
    }
}

record OrderResponse(Long id, String status) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentGetOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("OPEN"))
            .andDo(document("order-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Order identifier")
                )
            ));
    }
}
~~~

The test uses **RestDocumentationRequestBuilders.get(...)** instead of the standard MockMvc builder to retain the URI template. The request runs through the real Spring handler, asserts status and response, and only then generates the snippet. As a result, the test can catch when the route no longer matches or the handler returns data violating the contract.

## 3. When variable names diverge

### 3.1. Test template uses a different name from the controller

Suppose the controller is still:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
    // ...
}
~~~

Yet the test writes:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42L))
~~~

The name `id` in the request template does not match the mapping's variable name. At runtime, Spring MVC may still match the route positionally and bind the value to the controller mapping depending on placeholder resolution; however, the URI template received by REST Docs carries the name **id**. If the descriptor instead reads:

~~~java
pathParameters(
    parameterWithName("orderId").description("Order ID")
)
~~~

REST Docs will detect that the descriptor does not match the variable name in the request template; snippet generation can fail with a parameter-not-found or undocumented-request-parameter error depending on version and specifics.

**Fix:** use the exact same name `orderId` in both the test URI template and the descriptor. Do not rely on the request happening to route to the controller as proof that documentation is accurate.

### 3.2. Misspelled descriptor or extra descriptor

Both mapping and test template use `{orderId}`, yet the descriptor says:

~~~java
pathParameters(
    parameterWithName("id").description("Order ID")
)
~~~

The name `id` is not in the template. With `pathParameters(...)` in default strict mode, REST Docs reports an error because the descriptor does not correspond to a request path parameter.

Similarly, if the template has `{orderId}` and `{lineId}` while the test only describes `orderId`, `lineId` is missing documentation. Declare all of them completely:

~~~java
pathParameters(
    parameterWithName("orderId").description("Order ID"),
    parameterWithName("lineId").description("Order line item ID")
)
~~~

### 3.3. Java variable name does not have to match the URI name

A Java parameter name may differ from the URI variable name if the annotation specifies the binding explicitly:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long id) {
    return new OrderResponse(id, "OPEN");
}
~~~

In this case, the descriptor is still:

~~~java
parameterWithName("orderId").description("Order ID")
~~~

Do not use `parameterWithName("id")` just because the Java variable is named `id`. Path parameter documentation describes **names in the URI template**, not local Java variable names.

## 4. Mapping changed while old test remains

A common refactoring mistake is changing the mapping:

~~~java
@GetMapping("/api/purchases/{purchaseId}")
PurchaseResponse getPurchase(
        @PathVariable("purchaseId") Long purchaseId) {
    // ...
}
~~~

while leaving the test unchanged:

~~~java
get("/api/orders/{orderId}", 42L)
~~~

If checks only validate descriptors against the old template, a documentation test might still attempt to document **orderId**, yet the request no longer hits the current route—typically receiving 404. Tests must assert a successful status and meaningful response fields to catch this error.

When changing a route, update all of these together:

1. Controller mapping.
2. `@PathVariable` annotation if the variable name changed.
3. URI template in the test.
4. `parameterWithName(...)` descriptors.
5. Snippet name or documentation includes if the snippet identifier changed.
6. Tests covering routing, access permissions, and resource relationships.

A snippet name like **order-get** is an identifier chosen by the development team; REST Docs does not infer it from the URL. If you rename the snippet ID to **purchase-get**, update the **include** path in Asciidoctor as well.

## 5. Verifying the right route and path parameter relationships

With a nested endpoint:

~~~text
/api/orders/{orderId}/lines/{lineId}
~~~

The controller can bind:

~~~java
@GetMapping("/api/orders/{orderId}/lines/{lineId}")
OrderLineResponse getLine(
        @PathVariable("orderId") Long orderId,
        @PathVariable("lineId") Long lineId) {
    return service.getLine(orderId, lineId);
}
~~~

Tests must describe both variables:

~~~java
mockMvc.perform(get(
        "/api/orders/{orderId}/lines/{lineId}",
        42L, 7L))
    .andExpect(status().isOk())
    .andDo(document("order-line-get",
        pathParameters(
            parameterWithName("orderId")
                .description("ID of the order containing the line item"),
            parameterWithName("lineId")
                .description("ID of the line item to retrieve from the order")
        )
    ));
~~~

Yet route matching and accurate snippets still do not prove **lineId 7 belongs to orderId 42**. The service/repository must query by both keys or verify the relationship before returning data. Add tests for these scenarios:

| Data | Behavior to verify |
| --- | --- |
| Order 42 has line 7 | Returns successfully |
| Order 42 does not have line 7 | Does not return data from another line |
| Line 7 belongs to order 99, request uses order 42 | Returns error per contract (typically 404) |
| Order 42 does not exist | Returns not-found error per contract |
| Missing `lineId` segment | Does not match detail route unless another route exists |

Verifying resource relationships is the responsibility of business tests, not a feature of `pathParameters(...)`.

## 6. Using shared helpers to reduce drift

For APIs with multiple tests targeting the same route, you can extract the URI template and descriptors into a constant or helper inside the test:

~~~java
private static final String ORDER_URI =
    "/api/orders/{orderId}";

private static PathParametersSnippet orderPathParameters() {
    return pathParameters(
        parameterWithName("orderId")
            .description("Order identifier")
    );
}
~~~

When used:

~~~java
mockMvc.perform(get(ORDER_URI, 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get", orderPathParameters()));
~~~

The example requires static imports:

~~~java
import org.springframework.restdocs.request.PathParametersSnippet;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
~~~

A shared helper reduces duplicated strings and descriptions, yet **does not automatically ensure the controller mapping always matches** the test constant. Make sure tests invoke the initialized application, assert HTTP status and responses, and organize tests by endpoint so reviewers notice when mappings change.

Avoid building complex reflection machinery just to read controller annotations and auto-generate descriptors unless the project has a clear need. That increases complexity and can hide tests that are not actually calling the right route.

## 7. Keeping test requests, descriptors, and documentation on one contract

For each endpoint, follow a consistent convention:

| Component | Authoritative source to check |
| --- | --- |
| HTTP method and route | Application mapping annotation or functional route |
| Path variable name | Placeholder in URI template |
| Test value | Value conforming to type and business rules |
| Descriptor | Placeholder name and API consumer description |
| Assertion | Status, response, validation, and business conditions |
| Snippet ID | Unique, stable name for documentation includes |
| Asciidoctor page | Corresponding snippet path and endpoint description |

A documentation test should include at least:

- One valid request hitting the actual route.
- Status assertions and assertions on key response fields.
- Complete descriptors for path variables.
- Separate tests for invalid types, missing variables, or invalid business relationships if those behaviors are part of the published contract.

For endpoints with query parameters or headers, document them in their corresponding groups:

~~~java
document("order-get",
    pathParameters(
        parameterWithName("orderId").description("Order ID")
    ),
    queryParameters(
        parameterWithName("includeLines")
            .description("Whether to return the list of line items")
            .optional()
    ),
    requestHeaders(
        headerWithName("Accept")
            .description("Response media type accepted by the client")
    )
)
~~~

The extended snippet above requires static imports for **queryParameters(...)**, **requestHeaders(...)**, and **headerWithName(...)**. It demonstrates that one request can have multiple documented groups; never put query parameters or headers inside `pathParameters(...)`.

## 8. Testing with WebTestClient and REST Assured

The variable-name synchronization principle stays the same as with MockMvc: the request URI template must match the route under test, and descriptors must use placeholder names.

### 8.1. WebTestClient

In a test configured with Spring REST Docs integration:

~~~java
webTestClient.get()
    .uri("/api/orders/{orderId}", 42L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("Order identifier")
        )
    ));
~~~

Here **document(...)** is imported from **WebTestClientRestDocumentation**. The client must be set up with REST Docs configuration before executing the test. Asserting a successful HTTP status confirms the request matched a valid handler.

### 8.2. REST Assured

With a **RequestSpecification spec** configured with REST Docs:

~~~java
given(spec)
    .filter(document("order-rest-assured",
        pathParameters(
            parameterWithName("orderId")
                .description("Order identifier")
        )
    ))
    .pathParam("orderId", 42L)
    .when()
    .get("/api/orders/{orderId}")
    .then()
    .statusCode(200);
~~~

Here **document(...)** is imported from **RestAssuredRestDocumentation**. **pathParam("orderId", 42L)** supplies the request value; **parameterWithName("orderId")** describes the placeholder name. `spec` must be configured with the corresponding REST Docs filter and setup.

## 9. Integrating snippets with Asciidoctor and CI

After tests run, snippets can be placed under:

~~~text
build/generated-snippets/order-get/
├── path-parameters.adoc
├── http-request.adoc
└── http-response.adoc
~~~

In **src/docs/asciidoc/index.adoc**:

~~~asciidoc
= Orders API
:toc: left

== Get order

GET /api/orders/{orderId}

=== Path parameters

include::{snippets}/order-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/order-get/http-request.adoc[]

=== HTTP response

include::{snippets}/order-get/http-response.adoc[]
~~~

Gradle Groovy DSL configuration example, assuming the **org.asciidoctor.jvm.convert** plugin is already applied:

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

In CI, the flow should include:

1. Compile and run REST Docs tests.
2. Fail the build if a route does not match, an assertion fails, or snippets fail to generate.
3. Run Asciidoctor after snippets exist.
4. Publish documentation only when all required steps succeed.

If the final documentation is Markdown, use a suitable converter or snippet-embedding mechanism; the `include::...[]` directive belongs to Asciidoctor, not standard Markdown syntax.

## 10. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| REST Docs reports descriptor not found | Name in `parameterWithName(...)` differs from URI template | Use the exact placeholder name, including case |
| Request runs yet no snippet is generated | `document(...)` not called, wrong config, or missing URI template | Use REST Docs request builders and check configuration |
| Test returns 404 after changing mapping | Test URI was not updated | Sync the test template with the new route |
| Test returns 400 when path has letters instead of numbers | Binding to Long fails | Supply a value of the right type and test invalid inputs separately |
| Documentation displays old variable name | Descriptor or test template not updated | Update mapping, request template, and descriptor together |
| Missing row in path parameters table | Forgot to describe one variable of a multi-level route | Add descriptors for every placeholder |
| Snippet generated yet returns wrong child resource | Service only checks child ID | Verify parent-child relationship using both IDs |
| Asciidoctor reports missing snippet | Snippet ID in include does not match document ID | Synchronize names in `document(...)` and `include::...` |

## 11. Hands-on exercise

Given a controller with the route:

~~~text
GET /api/projects/{projectId}/tasks/{taskId}
~~~

Perform the following:

1. Write a controller using **@PathVariable("projectId")** and **@PathVariable("taskId")**.
2. Create a MockMvc test with **RestDocumentationRequestBuilders.get("/api/projects/{projectId}/tasks/{taskId}", 12L, 34L)**.
3. Assert the HTTP status and the **projectId** and **taskId** fields in the JSON response.
4. Call **document("project-task-get", pathParameters(...))** with two descriptors named **projectId** and **taskId** exactly.
5. Try changing the test template to **/api/projects/{id}/tasks/{taskId}** while keeping the **projectId** descriptor; explain the error REST Docs may report.
6. Try changing the controller mapping to **/api/workspaces/{projectId}/tasks/{taskId}** without updating the test; verify the success assertion fails because the old route no longer exists.
7. Verify the service does not return a task belonging to another project.
8. Include snippets in Asciidoctor and run in order: test → asciidoctor.

Sample descriptors:

~~~java
pathParameters(
    parameterWithName("projectId")
        .description("ID of the project owning the task"),
    parameterWithName("taskId")
        .description("ID of the task within the project")
)
~~~

**Completion criteria:** test template matches the deployed route; descriptors match placeholder names; real requests return proper responses; mismatched names and mappings are caught; documentation builds from test-generated snippets.

## Key Takeaways

To ensure parameter names match actual routes, keep **mapping placeholders**, **HTTP test URI templates**, and **names in parameterWithName(...)** synchronized. Spring REST Docs validates descriptors against the request URI template; tests hitting real controllers and asserting status/responses verify the route actually works. For nested routes, also check parent-child ID relationships. Integrate these tests into build/CI so route changes that omit documentation updates are caught prior to publication.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html), and [Spring MVC URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
