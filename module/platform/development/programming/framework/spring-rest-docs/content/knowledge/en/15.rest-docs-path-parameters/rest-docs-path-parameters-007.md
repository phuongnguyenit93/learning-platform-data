# Nested URI templates and path parameters

## Lesson Objectives

In REST APIs, resources are often organized in parent-child relationships. For example, a store has many products, an order has many line items, or an account has many transactions. The path expresses that relationship using multiple segments and multiple variables:

```text
/api/stores/{storeId}/products/{productId}
/api/orders/{orderId}/lines/{lineId}
/api/accounts/{accountId}/transactions/{transactionId}
```

These are **nested resource URIs**. When writing tests with **Spring REST Docs**, every variable in the path needs to be identified and described accurately using **pathParameters(...)** and **parameterWithName(...)**. The documentation must help API consumers understand which resource each ID identifies, how they relate to one another, and when nested endpoints should be used.

This lesson belongs to the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**, generating snippets for requests, responses, payloads, parameters, and headers, then compiling Asciidoctor/Markdown and integrating into build/CI.

After this lesson, you will be able to:

- Read and design URI templates with multiple path parameters.
- Distinguish a **parent ID** from a **child ID**, and understand the meaning of each path segment.
- Declare complete descriptors for nested path parameters.
- Test that a child resource actually belongs to the parent resource.
- Distinguish parent-not-found, child-not-found, and child-not-belonging-to-parent errors.
- Evaluate when to nest URIs, when to use flat URIs, or when to combine both.
- Generate and embed **path-parameters.adoc** snippets into API documentation.

## 1. Recognizing nested URI templates

Suppose a system manages stores and products. A store has many products; a product in a store has its own ID. An API retrieving one product's details might use:

```http
GET /api/stores/store-09/products/product-31
Accept: application/json
```

Corresponding URI template:

```text
/api/stores/{storeId}/products/{productId}
```

Breaking down each segment:

| Position | Literal or variable | Meaning |
| --- | --- | --- |
| 1 | `api` | API prefix |
| 2 | `stores` | Collection of stores |
| 3 | `{storeId}` | Parent store identifier |
| 4 | `products` | Collection of products belonging to the store |
| 5 | `{productId}` | Child product identifier |

The two variables **storeId** and **productId** are two distinct path parameters. The value **store-09** binds to the parent variable; **product-31** binds to the child variable. Descriptor names must match the URI template variable names exactly:

```java
pathParameters(
    parameterWithName("storeId")
        .description("ID of the store containing the product"),
    parameterWithName("productId")
        .description("ID of the product belonging to the store")
)
```

Do not declare `parameterWithName("id")` for both variables or use runtime values like `store-09` and `product-31` as descriptor names. Spring REST Docs needs **the variable names in the template**, not the actual request values.

### 1.1. What does a nested path express?

The path above communicates that the caller is accessing a product within the scope of a specific store. It expresses resource placement by parent-child hierarchy, yet the URI itself **does not guarantee** that the product truly belongs to that store. The application must still verify the relationship in data.

Example:

| Request | Expected meaning |
| --- | --- |
| `GET /api/stores/store-09/products/product-31` | Get product 31 in store 09 |
| `GET /api/stores/store-12/products/product-31` | Get product 31 if it belongs to store 12 |
| `GET /api/stores/store-09/products/product-999` | Does product 999 exist in store 09? |
| `GET /api/stores/store-999/products/product-31` | Does store 999 exist? |

If the product exists but belongs to **store-12**, a request using **store-09** must not return the product data just because **productId** is valid. The service must verify both keys or query by the **storeId + productId** relationship.

## 2. Designing endpoints for nested resources

A common API structure:

```text
/api/orders/{orderId}/lines
/api/orders/{orderId}/lines/{lineId}
/api/accounts/{accountId}/transactions
/api/accounts/{accountId}/transactions/{transactionId}
```

| Endpoint | Operation |
| --- | --- |
| `GET /api/orders/{orderId}/lines` | List line items belonging to an order |
| `GET /api/orders/{orderId}/lines/{lineId}` | Retrieve one line item in an order |
| `POST /api/orders/{orderId}/lines` | Create a line item in an order |
| `DELETE /api/orders/{orderId}/lines/{lineId}` | Remove a line item from an order |

Each variable describes part of the resource scope. For detail endpoints, **orderId** identifies the parent order, and **lineId** identifies the child line item within that order.

### 2.1. A child ID may be globally unique yet still need the parent ID

Even when **lineId** is a globally unique UUID, a nested URI can still be useful because it conveys business context and lets the server verify the relationship:

```text
/api/orders/{orderId}/lines/{lineId}
```

If an API only needs to identify the line item without depending on order context, a flat endpoint such as **/api/order-lines/{lineId}** may also fit. The choice depends on the contract, access control, resource organization, and client needs.

Do not nest overly deeply out of habit. A URI like **/companies/{companyId}/departments/{departmentId}/teams/{teamId}/members/{memberId}/devices/{deviceId}** can be awkward to use and tightly couples clients to internal hierarchy. Keep only the parent levels truly necessary to define resource scope or context.

### 2.2. Parent-child URIs do not enforce access control on their own

Users can change **orderId** or **lineId** in the URL. Having an ID in the path does not prove the caller is authorized to read that resource. The backend must check:

- Is the caller permitted to view the parent order?
- Does the child line item actually belong to the stated order?
- Is the caller permitted to act on the line item within that order?

These are business and security checks in the service/authorization layer. **pathParameters(...)** only documents the variables; it does not verify ownership and does not prevent unauthorized access.

## 3. Implementing controller and service for nested routes

The example below uses **Spring Boot 3.x**, Java 17+, **Spring MVC**, and **JUnit 5**. The controller retrieves a line item inside an order:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class OrderLineController {

    private final OrderLineService service;

    OrderLineController(OrderLineService service) {
        this.service = service;
    }

    @GetMapping("/api/orders/{orderId}/lines/{lineId}")
    OrderLineResponse getLine(
            @PathVariable("orderId") Long orderId,
            @PathVariable("lineId") Long lineId) {
        return service.getLine(orderId, lineId);
    }
}

record OrderLineResponse(Long orderId, Long lineId, int quantity) {}
```

The service must use both IDs when resolving the line item:

```java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class OrderLineService {

    OrderLineResponse getLine(Long orderId, Long lineId) {
        // Sample data illustration: line 7 only belongs to order 42.
        if (!orderId.equals(42L)) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found");
        }

        if (!lineId.equals(7L)) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order line not found");
        }

        return new OrderLineResponse(orderId, lineId, 2);
    }
}
```

In a real system, replace the illustrative logic with a repository query conditioned on **both orderId and lineId**, for example querying a line item with **id = lineId AND order_id = orderId**. Such a query ensures the line item is fetched within the right order scope.

### 3.1. Distinguishing error scenarios

| Scenario | Meaning | Typical behavior |
| --- | --- | --- |
| Missing **orderId** in the path | Does not match the detail URI template | Usually 404 if no other route exists |
| **orderId** has wrong Long type | Path variable binding fails | Usually 400 |
| Parent order does not exist | Parent resource not found | 404 |
| Child line item does not exist in order | Child resource not found within parent scope | 404 |
| Line item exists but belongs to another order | Invalid parent-child relationship for the request | Usually returns 404 to avoid leaking out-of-scope resources; another policy may be chosen per contract |
| Caller is not authorized to access | Authorization failure | 403 or 404 depending on security policy |

Specific HTTP status codes depend on the API contract and the application's error-handling mechanism. What matters is that **tests and documentation remain consistent with the chosen behavior**.

## 4. Documenting multiple path parameters with Spring REST Docs

Spring REST Docs uses **pathParameters(...)** to describe all variables in a URI template. For the route:

```text
/api/orders/{orderId}/lines/{lineId}
```

the corresponding descriptors:

```java
pathParameters(
    parameterWithName("orderId")
        .description("ID of the order containing the line item"),
    parameterWithName("lineId")
        .description("ID of the line item to retrieve from the order")
)
```

Descriptions should clarify the roles of parent ID and child ID. Two descriptions like **"Order ID"** and **"Line item ID"** are better than repeating variable names, but can be even clearer: "ID of the order containing the line item" and "ID of the line item to retrieve from the order".

Descriptors must satisfy:

1. Names match **{orderId}** and **{lineId}** exactly.
2. Do not put runtime values like **42** or **7** into descriptor names.
3. Each variable has its own description; avoid merging multiple IDs into one generic descriptor.
4. State the parent-child relationship explicitly if it is an important precondition for calling the endpoint.

## 5. MockMvc test example generating snippets

Add test dependencies in Gradle if the project does not already have them:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

With Spring Boot dependency management/BOM, compatible versions can be managed by the BOM. Example test placed in the same package as the controller:

```java
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderLineController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderLineDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderLineService service;

    @Test
    void documentGetOrderLineInOrder() throws Exception {
        given(service.getLine(42L, 7L))
            .willReturn(new OrderLineResponse(42L, 7L, 2));

        mockMvc.perform(get(
                "/api/orders/{orderId}/lines/{lineId}",
                42L, 7L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(42))
            .andExpect(jsonPath("$.lineId").value(7))
            .andExpect(jsonPath("$.quantity").value(2))
            .andDo(document("order-line-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("ID of the order containing the line item"),
                    parameterWithName("lineId")
                        .description("ID of the line item to retrieve from the order")
                )
            ));
    }
}
```

In the example above:

- **RestDocumentationRequestBuilders.get(...)** preserves the URI template with variable names. This is the builder to use with MockMvc so Spring REST Docs recognizes **orderId** and **lineId**.
- The two values **42L** and **7L** are request data; the order of values matches the order of variables in the template.
- **given(...).willReturn(...)** isolates the controller test with a mocked service; this test verifies routing, binding, response, and snippets. The rule checking whether the line item belongs to the order is tested separately in the service.
- **document("order-line-get", ...)** generates snippets for the executed request.

### 5.1. Generated snippets

Example directory:

```text
build/generated-snippets/
└── order-line-get/
    ├── path-parameters.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    └── curl-request.adoc
```

This is an abbreviated list; other default snippets may be generated depending on configuration. The **path-parameters.adoc** table has content equivalent to:

| Parameter | Description |
| --- | --- |
| **orderId** | ID of the order containing the line item |
| **lineId** | ID of the line item to retrieve from the order |

Do not edit generated files inside **generated-snippets** directly. Update descriptors in the test and re-run tests to regenerate the content.

## 6. Testing integrity of the parent-child relationship

A passing snippet-generating test is not enough to ensure the API will not return a line item from another order. Service tests or integration tests are needed to verify data relationships.

Example with Mockito in a service unit test:

```java
@Test
void doesNotReturnLineBelongingToAnotherOrder() {
    // Assuming data: line 7 belongs to order 42.
    assertThatThrownBy(() -> service.getLine(99L, 7L))
        .isInstanceOf(ResponseStatusException.class)
        .extracting(error ->
            ((ResponseStatusException) error).getStatusCode())
        .isEqualTo(HttpStatus.NOT_FOUND);
}
```

The snippet above must be placed in a test class that initializes the service or appropriate mock repositories. With a real repository, it is better to test that the query is constrained by both keys rather than loading the child by **lineId** and forgetting to verify **orderId**.

Scenarios you should cover:

| Scenario | Test goal |
| --- | --- |
| Parent exists, child belongs to parent | Returns child info successfully |
| Parent does not exist | Returns not-found result per contract |
| Parent exists, child does not exist | Does not return child data |
| Parent exists, child exists but belongs to another parent | Does not leak out-of-scope data |
| User lacks permission on parent | Rejects according to authorization policy |

If the system uses **@ControllerAdvice** or a standard error response, tests should assert both the HTTP code and the error structure published by the API.

## 7. Multi-level path parameters and deeper nesting

Example API for managing line items:

```text
/api/companies/{companyId}/orders/{orderId}/lines/{lineId}
```

Then the descriptors must include all three variables:

```java
pathParameters(
    parameterWithName("companyId")
        .description("ID of the company owning the order"),
    parameterWithName("orderId")
        .description("ID of the order belonging to the company"),
    parameterWithName("lineId")
        .description("ID of the line item belonging to the order")
)
```

Tests must verify that **orderId belongs to companyId** and **lineId belongs to orderId**. If you only check each ID's existence individually, the API still risks returning the wrong resource across an invalid parent-child link.

When multiple levels exist:

- Maintain descriptor order matching their appearance in the URI template so readers can cross-reference easily.
- Fully describe the role of each level.
- Do not omit a parent variable if clients need it to specify the resource scope properly.
- Evaluate URL depth and coupling to the internal data model.

If a parent ID is only used for scope checking and does not need to appear in the table, REST Docs provides the **ignored()** descriptor. However, only hide it when documentation elsewhere clearly explains how to pass that variable:

```java
pathParameters(
    parameterWithName("tenantId").ignored(),
    parameterWithName("orderId")
        .description("Order ID within the tenant"),
    parameterWithName("lineId")
        .description("Line item ID within the order")
)
```

**ignored()** does not make the parent variable optional during routing and does not skip access-control checks in the application.

## 8. WebTestClient and REST Assured

The same group of descriptors can be used with other HTTP test clients.

### 8.1. WebTestClient

With WebTestClient configured with Spring REST Docs integration:

```java
webTestClient.get()
    .uri("/api/orders/{orderId}/lines/{lineId}", 42L, 7L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-line-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("ID of the order containing the line item"),
            parameterWithName("lineId")
                .description("Line item ID within the order")
        )
    ));
```

Here **document(...)** belongs to **WebTestClientRestDocumentation**. The client must be configured through the REST Docs mechanism, e.g., **documentationConfiguration(...)**. The two variables in **uri(...)** preserve the template names and receive values in order.

### 8.2. REST Assured

With a **RequestSpecification spec** configured with REST Docs:

```java
given(spec)
    .filter(document("order-line-rest-assured",
        pathParameters(
            parameterWithName("orderId")
                .description("ID of the order containing the line item"),
            parameterWithName("lineId")
                .description("Line item ID within the order")
        )
    ))
    .pathParam("orderId", 42L)
    .pathParam("lineId", 7L)
    .when()
    .get("/api/orders/{orderId}/lines/{lineId}")
    .then()
    .statusCode(200);
```

Here **document(...)** belongs to **RestAssuredRestDocumentation**. The two **pathParam(...)** calls supply values; the descriptors describe the two variable names. REST Docs configuration and the request filter must be initialized before running the test.

## 9. Including snippets in Asciidoctor and build/CI

File **src/docs/asciidoc/index.adoc** can include:

```asciidoc
= Order API
:toc: left

== Get order line item

GET /api/orders/{orderId}/lines/{lineId}

=== Path parameters

include::{snippets}/order-line-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/order-line-get/http-request.adoc[]

=== HTTP response

include::{snippets}/order-line-get/http-response.adoc[]
```

Gradle Groovy DSL example when the project already has the **org.asciidoctor.jvm.convert** plugin installed:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

The dependency ensures tests generate snippets before Asciidoctor processes **include** directives. In CI, publish documentation only if both REST Docs tests and the documentation build task succeed. If **{lineId}** is renamed and you forget to update the descriptor or test URI, the error can be caught right at the test step.

Spring REST Docs generates AsciiDoc snippets by default. If the final documentation is published as Markdown, you need a conversion mechanism or compatible snippet templates; the **include::...[]** syntax belongs to Asciidoctor, not standard Markdown.

## 10. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Missing a path parameter in snippet | Forgot descriptor for a nested variable | Declare each **parameterWithName(...)** |
| Descriptor reported as not found | Misspelled name or case mismatch | Match exact names in the URI template |
| Line item from another order is returned | Service only looks up by **lineId** | Check both **orderId** and **lineId** together |
| Handler not found | Request is missing parent or child ID segment | Check the URI template and request |
| HTTP 400 when passing ID | Value cannot convert to Java type | Check path variable type and passed value |
| Snippet has IDs but descriptions are vague | Descriptions only repeat technical names | Describe parent-child roles and identifier scope |
| Docs lack path parameters table | **document(...)** not called, wrong URI builder, or missing config | Check test client and snippet output |
| Asciidoctor cannot find snippet | Tests have not run or wrong **snippets** attribute | Ensure test → asciidoctor order and verify path |
| Deeply nested URI is hard for clients to use | Overusing data relations to structure paths | Consider flat endpoints or reduce nesting depth |

## 11. Hands-on exercise

Design an API for managing comments on articles:

```text
GET /api/articles/{articleId}/comments/{commentId}
POST /api/articles/{articleId}/comments
```

Requirements:

1. Create a detail controller accepting **articleId** and **commentId** via **@PathVariable**.
2. Create a MockMvc test for the detail request, checking the status and both ID fields in JSON.
3. Use **pathParameters(...)** to separately describe the article ID and comment ID; generate the snippet named **article-comment-get**.
4. Write a service test ensuring the comment belongs to the specified article; a comment that exists but belongs to another article must not be returned as a valid resource.
5. Create a test for the comment creation route; only **articleId** is a path parameter. Comment data belongs in the request body and must not be documented as a path parameter.
6. Include **path-parameters.adoc**, **request-fields.adoc**, and required snippets in Asciidoctor documentation.
7. Run test → Asciidoctor in build/CI; verify documentation is regenerated from tests.

Sample descriptors for the detail endpoint:

```java
pathParameters(
    parameterWithName("articleId")
        .description("ID of the article containing the comment"),
    parameterWithName("commentId")
        .description("ID of the comment to retrieve within the article")
)
```

**Completion criteria:** URI template and request include all variables; descriptors match each name; service verifies parent-child ownership; snippets accurately express the meaning of both IDs; tests and documentation succeed in the pipeline.

## Key Takeaways

Nested URI templates such as **/api/orders/{orderId}/lines/{lineId}** represent child resources scoped under a parent resource. Each variable is an independent path parameter and requires its own **parameterWithName(...)** descriptor inside **pathParameters(...)**. Documenting variable names accurately is only part of the contract: business tests must also verify child-belongs-to-parent ownership, access permissions, and not-found cases. By generating snippets from MockMvc, WebTestClient, or REST Assured and embedding them into Asciidoctor and CI, documentation reliably reflects how the API identifies nested resources.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html), and [Spring MVC URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
