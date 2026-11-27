# Documenting Multiple Operations in One Test

## Objectives

With **MockMvc** and **Spring REST Docs**, a single test can send multiple HTTP requests via multiple `mockMvc.perform(...)` calls. Each request can represent a distinct API **operation**, such as listing items, fetching details, and creating a resource. To document all of them thoroughly, call **document(...)** after each request and assign each operation a unique **snippet identifier**.

This lesson belongs to the **SPRING_REST_DOCS** module: generating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; producing snippets for requests, responses, payloads, parameters, and headers; compiling Asciidoctor/Markdown; and integrating into the build and CI pipeline.

After this lesson, you will be able to:

- Execute multiple MockMvc requests within the same test method.
- Attach **document(...)** to each `ResultActions` result to generate separate snippets.
- Name operations meaningfully and avoid colliding snippet identifiers.
- Document different methods or endpoints without mixing their requests/responses.
- Separate setup, assertions, and descriptors so tests remain readable.
- Include multiple snippet groups in Asciidoctor and ensure CI builds all documentation.

## 1. One Operation Corresponds to One HTTP Execution

Suppose an order management API supports:

| Operation | HTTP Request | Purpose |
| --- | --- | --- |
| List orders | `GET /api/orders` | Retrieve list |
| View order | `GET /api/orders/{orderId}` | Retrieve a single order |
| Create order | `POST /api/orders` | Create a new resource |

In MockMvc, each request is executed via a **`mockMvc.perform(...)`** call. Spring REST Docs attaches snippet generation to the request's result using **`andDo(document(...))`**:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk())
    .andDo(document("orders-list"));

mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get"));
~~~

The two **`document(...)`** calls use different identifiers, so the list snippets are placed in the **`orders-list`** directory, while the detail snippets are placed in **`order-get`**.

Key point: **a single test method can contain multiple operations, but each operation must be documented on its corresponding request**. Calling `document(...)` only once on the last request causes REST Docs to generate snippets solely for that final request; it does not automatically collect earlier requests in the same method.

## 2. Unique Identifier per Operation

The first parameter of **`document("...")`** is the snippet identifier name. For example:

~~~java
document("orders-list")
document("order-get")
document("order-create")
~~~

Output is typically generated under:

~~~text
build/generated-snippets/
├── orders-list/
├── order-get/
└── order-create/
~~~

Each directory can contain `http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, and other enabled or declared snippets.

| Identifier Naming Style | Assessment |
| --- | --- |
| `orders-list`, `order-get`, `order-create` | Clear, conveys the operation |
| `test1`, `test2`, `result` | Hard to understand when reading documentation and build output |
| Reusing `order` for both GET and POST | Easily writes to the same snippet location, causing confusion or overwrites |
| `orders-list-v1`, `orders-list-v2` | Useful when genuinely documenting two different contracts |

If two requests call **the same identifier**, they write to the same output location. Depending on snippet writer configuration and test execution, contents may be overwritten or cause conflicts. Never reuse an identifier to combine multiple operations: assign a distinct name to each operation.

## 3. Complete Example: Multiple Operations in One Test Method

The example below uses **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, and **spring-restdocs-mockmvc**. Test dependencies in Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Spring Boot dependency management/BOM can manage compatible versions. The sample controller has three operations:

~~~java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    List<OrderResponse> listOrders() {
        return List.of(new OrderResponse(42L, "OPEN"));
    }

    @GetMapping("/api/orders/{orderId}")
    OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
        return new OrderResponse(orderId, "OPEN");
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    OrderResponse createOrder(@RequestBody CreateOrderRequest request) {
        return new OrderResponse(43L, request.description());
    }
}

record OrderResponse(Long id, String status) {}
record CreateOrderRequest(String description) {}
~~~

To illustrate documentation generation, the controller returns fixed data. A real application would use services/repositories to read and write data.

### 3.1. Test Containing Three Requests and Three Documentation Calls

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderOperationsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentListGetAndCreateOperations() throws Exception {
        // Operation 1: GET collection
        mockMvc.perform(get("/api/orders")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(42))
            .andDo(document("orders-list"));

        // Operation 2: GET one resource
        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("OPEN"))
            .andDo(document("order-get"));

        // Operation 3: POST create resource
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "description": "OPEN"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(43))
            .andDo(document("order-create"));
    }
}
~~~

In the method above:

- **The first request** sends GET to the collection and generates snippets under **orders-list**.
- **The second request** sends GET to a single resource, passes the **orderId** path variable, and generates snippets under **order-get**.
- **The third request** sends POST with a JSON body, receives HTTP 201, and generates snippets under **order-create**.

Each `perform(...)` call has its own assertions and a corresponding `andDo(document(...))` call. As a result, three request/response sets are recorded independently. Omitting `document("orders-list")` still tests the collection GET operation, but generates no documentation snippets for it.

### 3.2. Documenting Path Parameters and Request Fields

For the detail GET, you can add a path parameter descriptor:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;

// Replace andDo(document("order-get")) with:
.andDo(document("order-get",
    pathParameters(
        parameterWithName("orderId")
            .description("Order ID to look up")
    )
));
~~~

For POST, document the JSON body with **requestFields(...)**:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

.andDo(document("order-create",
    requestFields(
        fieldWithPath("description")
            .description("Order description")
    )
));
~~~

Place these descriptors in the **`document(...)`** call of the corresponding operation. Do not put `orderId` into the collection POST because that request has no path variable; likewise, do not put the `description` body field into `pathParameters(...)`.

### 3.3. Response Fields per Operation

To document JSON responses, add separate **responseFields(...)** calls:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

.andDo(document("order-get",
    pathParameters(
        parameterWithName("orderId")
            .description("Order ID to look up")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Order status")
    )
));
~~~

The response of the list GET is an array, so descriptors must describe element structure—for example, **`[]._id`** is not a valid field path if the actual field name is **id**. For a JSON payload containing an array of objects, use **`[].id`** and **`[].status`** according to Spring REST Docs field path syntax:

~~~java
responseFields(
    fieldWithPath("[].id").description("Order ID"),
    fieldWithPath("[].status").description("Order status")
)
~~~

Each operation has its own response contract. Do not copy the response field list from detail GET to list GET or POST if their response structures differ.

## 4. Comparing Multiple Operations in One Test vs. Multiple Test Methods

You can group multiple requests into a single test method, as in the example above. However, it is **not mandatory** to put every operation in one method. Splitting into multiple test methods is often better when each operation has different setup, data, or test conditions.

| Criterion | Multiple operations in one method | One operation per method |
| --- | --- | --- |
| Setup | Can share data and fixtures | May repeat setup or use helpers |
| Readability | Shows a sequential request flow | Each test focuses on one behavior |
| On test failure | May stop at the first failing operation | Only the affected method fails |
| REST Docs documentation | Still requires a separate identifier per document call | Separate identifier per test |
| Best suited for | Closely linked flows with shared setup | Independent operations or many scenarios |

**Recommendation:** group requests when they form a meaningful flow and shared setup genuinely helps. If list GET, detail GET, and create POST can be tested independently, three separate test methods are usually easier to maintain. Either way, document each request individually.

## 5. Organizing Helpers to Reduce Repetition

If multiple operations share configuration or descriptors, create small helpers in the test:

~~~java
private static PathParametersSnippet orderIdParameter() {
    return pathParameters(
        parameterWithName("orderId")
            .description("Order ID to look up")
    );
}
~~~

Required imports:

~~~java
import org.springframework.restdocs.request.PathParametersSnippet;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
~~~

Then:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get", orderIdParameter()));
~~~

Helpers should only consolidate repeated descriptions or setup, without hiding the request, assertions, and identifier. Test readers should still be able to see:

- Which HTTP method and URI the request uses.
- Which identifier saves the operation.
- Which assertions prove the response is correct.
- Which descriptors are included in the snippets.

## 6. Common Mistakes When Documenting Multiple Operations

### 6.1. Only Documenting the Last Operation

Example:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get"));
~~~

The test makes two requests, but only detail GET is documented. Attach **`andDo(document(...))`** to the first `perform` call if you need documentation for the collection GET.

### 6.2. Reusing the Same Snippet Identifier

~~~java
mockMvc.perform(get("/api/orders"))
    .andDo(document("order"));

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"description\":\"OPEN\"}"))
    .andDo(document("order"));
~~~

GET and POST write to the same name **order** despite having different requests/responses. Use **orders-list** and **order-create**, then include the exact corresponding directories in the documentation.

### 6.3. Missing Descriptors Matching the Operation

If detail GET has a path parameter but the test only calls `document("order-get")`, the path parameters snippet will not be generated. Add **pathParameters(...)** when the operation has path variables. Conversely, do not declare descriptors not present in the request template.

### 6.4. Order-Dependent Data Setup

If POST creates an order and then GET reads the newly created order, the test may depend on execution order and shared state. Ensure the test uses deterministic data, or extract the ID from the POST response to construct the subsequent GET within the same scenario. Avoid having one test method rely on data created by another test method; test ordering must not become an implicit requirement of the suite.

### 6.5. Leftover Stale Snippets

When renaming an identifier from **order** to **order-get**, update both **`include::...`** in Asciidoctor and ensure the build uses snippet outputs from the current test run. Leftover snippets on disk can allow documentation to build even when new tests fail to generate what you expect.

## 7. WebTestClient and REST Assured

This lesson focuses on MockMvc, but the principle of **one document call and unique identifier per operation** applies equally to other test clients.

### WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-list-webtestclient"));

webTestClient.get()
    .uri("/api/orders/{orderId}", 42L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-get-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("Order ID")
        )
    ));
~~~

These are excerpts from tests configured with REST Docs for **WebTestClient**; `document(...)` is imported from **WebTestClientRestDocumentation**.

### REST Assured

~~~java
given(spec)
    .filter(document("orders-list-rest-assured"))
    .when()
    .get("/api/orders")
    .then()
    .statusCode(200);

given(spec)
    .filter(document("order-get-rest-assured",
        pathParameters(
            parameterWithName("orderId").description("Order ID")
        )
    ))
    .pathParam("orderId", 42L)
    .when()
    .get("/api/orders/{orderId}")
    .then()
    .statusCode(200);
~~~

In REST Assured, each request has its own **document(...)** filter; **spec** must be configured with Spring REST Docs integration. `document(...)` here is imported from **RestAssuredRestDocumentation**.

## 8. Combining Multiple Operations into Asciidoctor

After running tests, the snippets directory may have this structure:

~~~text
build/generated-snippets/
├── orders-list/
│   ├── http-request.adoc
│   └── http-response.adoc
├── order-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── path-parameters.adoc
└── order-create/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-fields.adoc
~~~

In **src/docs/asciidoc/orders.adoc**:

~~~asciidoc
= Orders API
:toc: left

== List Orders

GET /api/orders

=== Request

include::{snippets}/orders-list/http-request.adoc[]

=== Response

include::{snippets}/orders-list/http-response.adoc[]

== View an Order

GET /api/orders/{orderId}

=== Path parameters

include::{snippets}/order-get/path-parameters.adoc[]

=== Request

include::{snippets}/order-get/http-request.adoc[]

=== Response

include::{snippets}/order-get/http-response.adoc[]

== Create Order

POST /api/orders

=== Request fields

include::{snippets}/order-create/request-fields.adoc[]

=== Request and response

include::{snippets}/order-create/http-request.adoc[]
include::{snippets}/order-create/http-response.adoc[]
~~~

Each documentation section uses the snippet identifier matching its operation. Never use a single shared snippet path for the whole API when each request needs its own independent request/response set.

### 8.1. Wiring Tests to Asciidoctor in Gradle

Gradle Groovy DSL example when the **org.asciidoctor.jvm.convert** plugin is configured:

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

In CI, run snippet-generating tests before building documentation. If an operation no longer runs or an assertion fails, the build must halt before publishing documentation. You can verify output by confirming the **orders-list**, **order-get**, **order-create** directories and included snippets are present after the test step.

If the final documentation is Markdown, a compatible conversion or embedding mechanism is needed; **`include::...[]`** syntax belongs to Asciidoctor, not standard Markdown.

## 9. Practice Exercise

A book management application has three operations:

~~~text
GET /api/books
GET /api/books/{bookId}
POST /api/books
~~~

Requirements:

1. Write a single test method calling all three requests with **MockMvc**.
2. Add assertions for status and at least one response field in each operation.
3. Call **document(...)** three times with identifiers **books-list**, **book-get**, and **book-create**.
4. Use **pathParameters(...)** for the detail GET operation; use **requestFields(...)** for POST create.
5. Verify each snippet directory is generated separately and does not accidentally contain requests/responses from another operation.
6. Include the snippets in an Asciidoctor file with three sections.
7. Try changing one identifier in the test without updating the include; observe the Asciidoctor task reporting a missing snippet.

Sample descriptor for detail GET:

~~~java
pathParameters(
    parameterWithName("bookId")
        .description("Book ID to look up")
)
~~~

**Completion criteria:** one test method with three HTTP executions; each operation has assertions and a distinct document identifier; snippets are generated in the right groups; Asciidoctor documentation includes the matching requests/responses.

## Remember

MockMvc allows a single test method to execute multiple HTTP operations. For Spring REST Docs to generate complete documentation, call **`andDo(document(...))`** after each request, give each operation a **distinct identifier**, and declare descriptors matching that request. Each snippet set should accurately reflect the method, URI, headers, payload, and response of one operation. Then include each set in the right Asciidoctor section and connect the test task to build/CI so documentation is built from tested requests.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs MockMvc API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html), and [MockMvc API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/MockMvc.html).
