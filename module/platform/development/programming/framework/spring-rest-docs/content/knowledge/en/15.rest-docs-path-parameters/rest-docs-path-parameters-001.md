# Documenting path parameters with pathParameters

## Lesson Objectives

In **Spring REST Docs**, API documentation is generated from executed HTTP tests. Instead of manually writing a parameter table and hoping it stays accurate, we declare the parts to be documented directly inside the test. When an API path changes and the documentation declaration no longer matches, the test can fail and warn about the discrepancy before the documentation is published.

After this lesson, you will be able to:

- Distinguish **path parameters** from query parameters, request bodies, and HTTP headers.
- Use **pathParameters(...)** together with **parameterWithName(...)** to describe variables in a URI template.
- Generate the **path-parameters.adoc** snippet from a **MockMvc** test, while understanding how to apply it with **WebTestClient** and **REST Assured**.
- Include snippets into **Asciidoctor** documentation and wire documentation generation into the build/CI.
- Diagnose common errors when a URI template and parameter documentation do not match.

## 1. What is a path parameter?

Consider the endpoint:

~~~http
GET /api/orders/42/lines/7
Accept: application/json
~~~

The path definition of the endpoint is:

~~~text
/api/orders/{orderId}/lines/{lineId}
~~~

The two segments **{orderId}** and **{lineId}** are *path parameters*: they identify resources directly within the URI path. In the sample request, the corresponding values are **42** and **7**.

| Element | Example | How to document with Spring REST Docs |
| --- | --- | --- |
| Path parameter | **/orders/{orderId}** | **pathParameters(...)** |
| Query parameter | **/orders?status=OPEN** | **queryParameters(...)** in versions supporting this API |
| Request header | **Authorization: Bearer ...** | **requestHeaders(...)** |
| JSON request body | **{"quantity": 2}** | **requestFields(...)** |
| JSON response body | **{"id": 42}** | **responseFields(...)** |

Important distinction: **@PathVariable** is how Spring MVC binds values from the URL to controller parameters; **pathParameters(...)** is how Spring REST Docs **describes and verifies the documentation** for those variables. A working API does not automatically mean its documentation is complete.

## 2. How pathParameters(...) works

Core syntax inside a test:

~~~java
pathParameters(
    parameterWithName("orderId").description("Order ID"),
    parameterWithName("lineId").description("Order line item ID")
)
~~~

- **pathParameters(...)** creates a snippet describing the group of path parameters.
- **parameterWithName("orderId")** creates a description specifically for the **{orderId}** variable in the URI template.
- **description(...)** provides the business meaning displayed in the documentation table.
- **document("order-line-get", ...)** attaches snippets to a tested request/response and saves them under a directory named after the identifier **order-line-get**.

Documentation generation workflow:

~~~mermaid
flowchart LR
    A["HTTP test with URI template"] --> B["Verify status and data"]
    B --> C["document(..., pathParameters(...))"]
    C --> D["generated-snippets/order-line-get/path-parameters.adoc"]
    D --> E["Asciidoctor: API documentation"]
    E --> F["Build / CI publish"]
~~~

The variables declared in **parameterWithName(...)** must have names matching the URI template. For example, using the name **id** to describe **{orderId}** is incorrect, even if the actual request still returns HTTP 200.

## 3. Complete example with Spring MVC and MockMvc

The example below uses **Java 17+**, **JUnit 5**, **Spring Boot 3.x**, and **spring-restdocs-mockmvc**. With Maven, replace the corresponding build directory with **target/generated-snippets**.

### 3.1. Testing dependencies

In a Spring Boot project using Gradle, you need the Spring Boot test starter and Spring REST Docs for MockMvc:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

If you use Spring Boot dependency management/BOM, you do not need to specify the version of each REST Docs dependency manually when the BOM already manages it. For WebTestClient or REST Assured, substitute the appropriate integration library.

### 3.2. Sample controller

File **OrderLineController.java**:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderLineController {

    @GetMapping("/api/orders/{orderId}/lines/{lineId}")
    OrderLineResponse getLine(
            @PathVariable("orderId") Long orderId,
            @PathVariable("lineId") Long lineId) {
        return new OrderLineResponse(orderId, lineId, 2);
    }
}

record OrderLineResponse(Long orderId, Long lineId, int quantity) {}
~~~

The endpoint returns JSON with the following structure:

~~~json
{
  "orderId": 42,
  "lineId": 7,
  "quantity": 2
}
~~~

In a real system, the controller typically calls a service to fetch data. The hardcoded controller in this example is solely meant to focus on the mechanism for documenting path variables.

### 3.3. Test generating the snippet

File **OrderLineDocumentationTest.java**, placed in the same package as the controller:

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

@WebMvcTest(OrderLineController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderLineDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentGetOrderLine() throws Exception {
        mockMvc.perform(get(
                    "/api/orders/{orderId}/lines/{lineId}",
                    42L, 7L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(42))
            .andExpect(jsonPath("$.lineId").value(7))
            .andDo(document("order-line-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("ID of the order to look up"),
                    parameterWithName("lineId")
                        .description("ID of the line item belonging to the order")
                )
            ));
    }
}
~~~

**Why use RestDocumentationRequestBuilders.get(...)?** When testing with MockMvc, this builder helps Spring REST Docs preserve the *URI template* along with the variable names, such as **{orderId}**, in order to generate the path parameters snippet. Avoid replacing it with a call using an already-expanded URL string such as **/api/orders/42/lines/7**: that string no longer reflects the variable names to be documented.

The test simultaneously verifies the HTTP status code and several key values in the response. Therefore, the snippet is tied to a request/response scenario that actually meets requirements, rather than a manually written example.

### 3.4. Generated output

After running the test, the output directory will have a structure similar to:

~~~text
build/
└── generated-snippets/
    └── order-line-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── httpie-request.adoc
        ├── request-body.adoc
        ├── response-body.adoc
        └── path-parameters.adoc
~~~

The actual number of snippets also depends on the version and configuration. The part to pay attention to in this lesson is **path-parameters.adoc**: it contains a table with parameter names and descriptions taken from the two **parameterWithName(...)** calls. Do not edit generated snippets directly, because the next test run will regenerate their content.

## 4. Verification mechanism and strictness

When using standard **pathParameters(...)**, Spring REST Docs checks the parameter declarations against the URI template. This helps detect missing or inconsistent documentation.

| Scenario | Expected outcome |
| --- | --- |
| URI template contains **{orderId}**, and **parameterWithName("orderId")** is present | Documented |
| URI template also contains **{lineId}** but **lineId** is not described | Strict snippet reports an undocumented parameter |
| Describes **customerId** while the template has no **{customerId}** | Snippet reports that the description does not match the request |
| Correct name but wrong business meaning | The framework cannot infer this automatically; content review is needed |
| There is a path variable you do not want displayed | You can declare the descriptor with **ignored()** to explicitly ignore it |

**ignored()** and **optional()** have different meanings:

~~~java
pathParameters(
    parameterWithName("orderId").description("Order ID"),
    parameterWithName("internalKey").ignored()
)
~~~

The **ignored()** descriptor indicates that the parameter is still recognized but will not be listed in the table. **optional()** marks the description as not required to appear in the tested request sample; it does **not** turn a required **@PathVariable** in the routing configuration into an optional one. For typical path parameters, you should describe all of them completely and keep snippet strictness enabled.

Some Spring REST Docs APIs provide a **relaxedPathParameters(...)** variant to ignore errors caused by parameters present in the request that are not yet documented. Use it only intentionally, because when extending the URI template, documentation can silently omit new variables.

## 5. Multiple path parameters and special cases

A URI template can contain multiple variables and each variable needs to be described according to its exact role:

~~~text
GET /api/shops/{shopId}/products/{productId}/reviews/{reviewId}
~~~

~~~java
pathParameters(
    parameterWithName("shopId").description("Shop ID"),
    parameterWithName("productId").description("Product ID at the shop"),
    parameterWithName("reviewId").description("ID of the review to view")
)
~~~

Do not merge them into a single shared description because API readers need to clearly understand the relationship between each ID. If a variable is a UUID, ULID, or business code, state the format clearly and provide examples in the documentation; **pathParameters(...)** generates documentation and does not automatically validate those data type rules. Add corresponding valid/invalid tests if the format is part of the API contract.

For paths with a query string, separate documentation responsibilities:

~~~http
GET /api/orders/42/lines/7?locale=vi
~~~

- **orderId** and **lineId**: described by **pathParameters(...)**.
- **locale**: is a query parameter; describe it using the query parameter snippet group corresponding to the REST Docs version in use.

If endpoints differ only by HTTP method—for example **GET** and **DELETE** both using **/api/orders/{orderId}/lines/{lineId}**—each test/document call should have its own snippet identifier, such as **order-line-get** and **order-line-delete**. You can reuse helper methods that create descriptors when variable meanings do not change, while still testing each endpoint's behavior.

## 6. Using pathParameters with WebTestClient and REST Assured

**pathParameters(...)** is a shared documentation declaration for URI templates; how it is attached to the test chain varies by HTTP test client.

### WebTestClient

Once Spring REST Docs is configured for **WebTestClient** via **documentationConfiguration(...)**, typical usage is:

~~~java
webTestClient.get()
    .uri("/api/orders/{orderId}/lines/{lineId}", 42L, 7L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-line-webtestclient",
        pathParameters(
            parameterWithName("orderId").description("Order ID"),
            parameterWithName("lineId").description("Line item ID")
        )
    ));
~~~

In the snippet above, **document(...)** is statically imported from **WebTestClientRestDocumentation**; **pathParameters(...)** and **parameterWithName(...)** still belong to **RequestDocumentation**. The test client must have the REST Docs filter attached during setup in order to generate snippets.

### REST Assured

With a **RequestSpecification spec** configured with the Spring REST Docs filter:

~~~java
given(spec)
    .filter(document("order-line-rest-assured",
        pathParameters(
            parameterWithName("orderId").description("Order ID"),
            parameterWithName("lineId").description("Line item ID")
        )
    ))
    .pathParam("orderId", 42L)
    .pathParam("lineId", 7L)
    .when()
    .get("/api/orders/{orderId}/lines/{lineId}")
    .then()
    .statusCode(200);
~~~

Here **document(...)** is an API from **RestAssuredRestDocumentation**. First configure **RequestSpecification** with REST Docs; then the request uses a path containing variable names so the system recognizes them and builds the parameter table.

All three integration approaches lead to the same result: HTTP tests pass and snippets are generated from the observed requests.

## 7. Including snippets in Asciidoctor documentation and the build

Example **src/docs/asciidoc/index.adoc** file:

~~~asciidoc
= Order API
:toc: left
:snippets: {docdir}/../../../build/generated-snippets

== View order line item

GET /api/orders/{orderId}/lines/{lineId}

=== Path parameters

include::{snippets}/order-line-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/order-line-get/http-request.adoc[]

=== HTTP response

include::{snippets}/order-line-get/http-response.adoc[]
~~~

In the example above, **{docdir}** is the directory containing the AsciiDoc document; the relative path fits the Gradle project structure shown. If the build tool already passes a **snippets** attribute, use the attribute from the build to avoid hardcoding paths.

With Gradle and the **org.asciidoctor.jvm.convert** plugin installed, you can configure the dependency as follows:

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

Thanks to **dependsOn**, the documentation generation task will run tests before processing **include** directives. In CI, run both the full test suite and the Asciidoctor task; if a REST Docs test fails or a snippet is missing, the pipeline should stop instead of publishing stale documentation. When using Maven, configure the equivalent in the test lifecycle and Asciidoctor Maven Plugin.

Spring REST Docs generates AsciiDoc snippets directly. If the final documentation page is written in Markdown, you can link/embed through an appropriate publishing tool, or customize snippet templates for that tool; you should **not** assume every Markdown renderer understands Asciidoctor's **include::...[]** syntax.

## 8. Common errors and troubleshooting

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Cannot find URI template info or path parameter snippet is not generated | Using an expanded URL or a request builder that does not preserve the URI template | With MockMvc, use **RestDocumentationRequestBuilders.get("/.../{id}", id)** |
| Undocumented parameter error reported | URI template has a new variable but lacks a descriptor | Add **parameterWithName(...)** with the exact name and business description |
| Documented parameter not found error reported | Wrong descriptor name or template changed | Compare each name in **{...}** and **parameterWithName("...")** |
| Test passes green but no snippet file is produced | REST Docs extension/filter not attached or **document(...)** not called | Check test client configuration and the documentation call |
| Asciidoctor reports missing **path-parameters.adoc** | Test has not run yet or **snippets** path is wrong | Ensure **test → asciidoctor** order and verify file location |
| Documentation describes the wrong meaning for an ID | Tests check technical behavior, not business semantics | Review descriptions, provide examples, and add API-contract tests |

To verify after changing an endpoint, re-run the test that generates the snippet, read **path-parameters.adoc**, and inspect the final HTML output. Just seeing an HTTP 200 test pass is not enough if the **document(...)** part was not executed.

## 9. Hands-on exercise

You have the endpoint:

~~~http
GET /api/teams/12/members/34?includeInactive=false
~~~

Path template:

~~~text
/api/teams/{teamId}/members/{memberId}
~~~

Write a documentation test that includes:

1. Verifying that the request returns a successful HTTP status code and a field in the JSON response.
2. Using **pathParameters(...)** to describe **teamId** and **memberId**, with clear descriptions for each variable.
3. Documenting **includeInactive** separately as a query parameter if the endpoint supports it.
4. Generating a snippet named **team-member-get/path-parameters.adoc**, including it in an **index.adoc** file, and re-running the build.
5. Trying to remove the **memberId** descriptor or renaming it to **id** to observe the verification error, then restoring the correct code.

A sample solution for the path parameters part:

~~~java
pathParameters(
    parameterWithName("teamId").description("ID of the team containing the member"),
    parameterWithName("memberId").description("ID of the member within the team")
)
~~~

**Completion criteria:** the HTTP test passes; the snippet accurately lists both variables; the documentation page renders the path parameters table; and the missing-variable documentation case is caught by the test.

## Key Takeaways

**pathParameters(...)** turns URI template variables into a documentation table that can be verified through tests. Use the right builder and URI template, describe all variables with **parameterWithName(...)**, keep snippets strict, and feed the output into Asciidoctor and CI so your REST API documentation always stays aligned with tested behavior.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/) and [Spring REST Docs API](https://docs.spring.io/spring-restdocs/docs/current/api/).
