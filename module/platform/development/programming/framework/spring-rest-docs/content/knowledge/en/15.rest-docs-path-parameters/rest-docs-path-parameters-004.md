# Distinguishing path parameters from query parameters

## Lesson Objectives

In a REST API, both **path parameters** and **query parameters** are passed via the URL, yet they live in different positions and serve different purposes. When writing documentation with **Spring REST Docs**, accurately distinguishing between these two groups is essential for generating accurate snippets from HTTP tests.

This lesson belongs to the **SPRING_REST_DOCS** module: creating verifiable REST API documentation through **MockMvc**, **WebTestClient**, or **REST Assured**, then compiling request, response, and parameter snippets into **Asciidoctor/Markdown** and integrating with the build and CI pipeline.

After this lesson, you will be able to:

- Identify path parameters and query parameters within the same URL.
- Explain how the two parameter types affect **routing** and **business logic**.
- Distinguish **@PathVariable** from **@RequestParam** in Spring MVC.
- Document the same request using **pathParameters(...)** and **queryParameters(...)** in Spring REST Docs.
- Properly describe **required**, **optional**, **default-valued**, or **multi-value** query parameters.
- Test missing-parameter scenarios and diagnose common errors during snippet generation or documentation builds.

## 1. Analyzing a concrete URL

Consider a product search request:

~~~http
GET /api/stores/store-09/products?category=BOOK&page=1
Accept: application/json
~~~

The application can define the URI template:

~~~text
/api/stores/{storeId}/products
~~~

Split into two parts:

~~~text
GET /api/stores/store-09/products ? category=BOOK & page=1
    |-------------------------|   |--------------------|
            path part                  query part
    {storeId} = store-09         category = BOOK
                                 page = 1
~~~

A **path parameter** is a value placed into a variable in the path pattern, such as **{storeId}**. A **query parameter** is a name/value pair in the query string after the **?** character, such as **category=BOOK** or **page=1**.

| Characteristic | Path parameter | Query parameter |
| --- | --- | --- |
| Example | **/api/stores/{storeId}** | **?category=BOOK&page=1** |
| Position | Inside the path segments | In the query part after **?** |
| Syntax | Variable name **{...}** in the URI template | **name=value**, pairs typically separated by **&** |
| Common purpose | Identify a resource or resource scope | Filter, sort, paginate, select representation, or processing options |
| Spring MVC | **@PathVariable** | **@RequestParam** |
| Spring REST Docs | **pathParameters(...)** | **queryParameters(...)** |
| Typical generated snippet | **path-parameters.adoc** | **query-parameters.adoc** |
| Requiredness | A variable must usually be present to match the route containing that segment | May be required, optional, or have a default value depending on the API contract |

Both parameter groups can appear on the same request, and sharing a name does not make them equivalent. In the example above, **storeId** identifies the store to search, whereas **category** and **page** control the returned product list.

## 2. Why the two parameter types cannot substitute for each other

### 2.1. Path parameters participate in path matching

With the route:

~~~java
@GetMapping("/api/stores/{storeId}/products")
~~~

The request **GET /api/stores/store-09/products** has the segment **store-09** in the exact position of **{storeId}**. The request **GET /api/stores/products** does not match this pattern because it lacks the segment for the store ID. Adding **?storeId=store-09** to the URL does not automatically fill in the missing path segment.

Another controller could declare the route **/api/stores/products**, but that is a different routing contract. **@PathVariable(required = false)** does not automatically make a URI segment present in the pattern skippable.

### 2.2. Query parameters do not create extra path segments

With the same route above, both of the following URLs can match the same handler:

~~~http
GET /api/stores/store-09/products?category=BOOK
GET /api/stores/store-09/products?category=BOOK&page=1
~~~

**page** can be optional and default to **0**. Conversely, **category** can be required if the API mandates specifying a product category. Missing a required query parameter does not necessarily prevent the route from matching: the handler may already be selected, and the **binding/validation** step reports an error for the missing data.

This also means **query parameters are not always optional**. Requiredness rules depend on the API contract and application declarations.

### 2.3. Choosing path or query when designing an API

Suppose the system has the following operations:

| Task | Suggested URL design | Reason |
| --- | --- | --- |
| View order with ID 42 | **GET /api/orders/42** | The ID identifies the order resource |
| View line item 7 of order 42 | **GET /api/orders/42/lines/7** | Two IDs locate the resource in the hierarchy |
| List open orders | **GET /api/orders?status=OPEN** | **status** is a filter condition on the collection |
| Go to page 3, 20 items per page | **GET /api/orders?page=3&size=20** | Controls how a slice of the list is fetched |
| Retrieve order details in Vietnamese | **GET /api/orders/42?locale=vi** | Chooses how a resource is represented |

These are **common design conventions**, not absolute rules of HTTP. A query parameter can also deeply affect business results; what matters is maintaining a consistent, clear, and tested URL contract.

## 3. Parameter binding in Spring MVC

The following example combines a required path parameter with a required query parameter and an optional query parameter with a default value:

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StoreProductsController {

    @GetMapping("/api/stores/{storeId}/products")
    List<ProductResponse> listProducts(
            @PathVariable("storeId") String storeId,
            @RequestParam("category") String category,
            @RequestParam(value = "page", defaultValue = "0") int page) {
        return List.of(
            new ProductResponse("product-31", storeId, category, page)
        );
    }
}

record ProductResponse(
        String id, String storeId, String category, int page) {}
~~~

In this example:

- **storeId** is in the pattern **/api/stores/{storeId}/products**, so it is bound by **@PathVariable("storeId")**.
- **category** is bound by **@RequestParam("category")**; by default **required = true**, so requests missing **category** typically return HTTP **400 Bad Request**.
- **page** is also bound by **@RequestParam**, but **defaultValue = "0"** allows omitting the parameter from the URL and receiving **0**.

The outcomes below assume the controller above is the only matching mapping and the application does not customize exception handling:

| Request | Expected behavior |
| --- | --- |
| **/api/stores/store-09/products?category=BOOK&page=1** | HTTP 200; **storeId=store-09**, **category=BOOK**, **page=1** |
| **/api/stores/store-09/products?category=BOOK** | HTTP 200; **page** uses default **0** |
| **/api/stores/store-09/products?page=1** | HTTP 400 due to missing required query parameter **category** |
| **/api/stores/products?category=BOOK** | Does not match the route with **{storeId}**; typically returns HTTP 404 |
| **/api/stores/store-09/products?category=BOOK&page=abc** | Route matches, but converting **abc** to **int** typically causes HTTP 400 |

Distinguishing the three processing layers:

~~~mermaid
flowchart TD
    A["GET /api/stores/store-09/products?category=BOOK&page=1"] --> B{"Path matches /api/stores/{storeId}/products?"}
    B -->|No| C["Does not enter this handler"]
    B -->|Yes| D["Bind storeId from path"]
    D --> E["Bind category and page from query"]
    E --> F{"Missing required value / wrong type?"}
    F -->|Yes| G["Return error, e.g. HTTP 400"]
    F -->|No| H["Invoke handler, build response"]
~~~

Spring MVC's **@RequestParam** can also read data from request parameters in other request types, such as form data. Therefore, the annotation name alone does not guarantee that the parameter always lives in the query string. When documenting an **HTTP query string**, Spring REST Docs uses **queryParameters(...)**; for form requests, use the form parameter documentation mechanism appropriate for your REST Docs version.

## 4. Spring REST Docs: two snippet groups for one request

To document the URL **/api/stores/store-09/products?category=BOOK&page=1**, use **pathParameters(...)** for **storeId** and **queryParameters(...)** for **category** and **page**:

~~~java
pathParameters(
    parameterWithName("storeId")
        .description("ID of the store containing the products")
),
queryParameters(
    parameterWithName("category")
        .description("Product category to search; e.g. BOOK"),
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional()
)
~~~

Both snippets use **parameterWithName(...)**, while the outer method determines the kind of data being documented:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
~~~

**pathParameters(...)** checks descriptors against the variable names in the URI template. **queryParameters(...)** checks descriptors against parameters in the query string. Each group produces its corresponding snippet file when passed to **document(...)**.

**Version note:** examples in this lesson use the **queryParameters(...)** API from modern Spring REST Docs versions (3.x). In older REST Docs guides or projects, you may see **requestParameters(...)**. When upgrading, check the corresponding API because query parameters and form parameters are separated in newer versions.

### 4.1. Why does page use optional() while category does not?

The API requires **category** to select the product type; therefore its descriptor is not marked optional. **page** has a default value in the controller, so marking it with **optional()** is appropriate: tests with a URL omitting **page** can still generate the endpoint's documentation.

Note that **optional()** in Spring REST Docs only adjusts **requiredness for documentation verification**. It does not change **@RequestParam(required = ...)**, does not supply a default value, and does not alter controller behavior. When updating the API contract, keep handler code, tests, and descriptors synchronized.

### 4.2. Why you shouldn't use relaxed...() out of habit

REST Docs provides non-strict verification variants such as **relaxedPathParameters(...)** and **relaxedQueryParameters(...)**. They allow omitting undocumented parameters while snippet-generating tests still pass, depending on the case.

If the goal is **verifiable REST API documentation**, prefer strict **pathParameters(...)** and **queryParameters(...)** with a complete list of descriptors. When someone adds a new query parameter, the documentation test will remind the development team to update the contract rather than silently skipping an important change.

## 5. Complete example with MockMvc

The example below uses **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, **spring-restdocs-mockmvc**, and the controller from section 3. Minimal Gradle dependency configuration when the project already uses Spring Boot BOM/dependency management:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Create **StoreProductsDocumentationTest.java** in the same package as the controller:

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
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StoreProductsController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class StoreProductsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentPathAndQueryParameters() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products", "store-09")
                    .queryParam("category", "BOOK")
                    .queryParam("page", "1")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].storeId").value("store-09"))
            .andExpect(jsonPath("$[0].category").value("BOOK"))
            .andExpect(jsonPath("$[0].page").value(1))
            .andDo(document("store-products-get",
                pathParameters(
                    parameterWithName("storeId")
                        .description("ID of the store containing the products")
                ),
                queryParameters(
                    parameterWithName("category")
                        .description("Product category to search; e.g. BOOK"),
                    parameterWithName("page")
                        .description("Zero-based page index; defaults to 0")
                        .optional()
                )
            ));
    }

    @Test
    void pageIsOptionalAndDefaultsToZero() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products", "store-09")
                    .queryParam("category", "BOOK"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].page").value(0));
    }

    @Test
    void categoryIsRequired() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products", "store-09")
                    .queryParam("page", "1"))
            .andExpect(status().isBadRequest());
    }
}
~~~

In this test, two details are easily confused:

1. **get("/api/stores/{storeId}/products", "store-09")** is the **Spring REST Docs** request builder, which preserves the URI template so it recognizes the **storeId** name. Calling **get("/api/stores/store-09/products")** with an already-expanded URL does not provide the same template information.
2. **.queryParam("category", "BOOK")** and **.queryParam("page", "1")** place values onto the request's query string. This is the explicit choice when you need a **queryParameters(...)** snippet. Do not confuse it with **.param(...)**, because setting a request parameter does not necessarily represent the exact same query string.

The first test verifies HTTP 200, JSON values, and generates both snippets; the remaining two tests verify the business semantics of optional **page** and required **category**. Spring REST Docs itself does not validate the business correctness of **description(...)** text or the default value **0**; assertions must still be written.

### 5.1. Generated files

After running the tests, the example directory will contain:

~~~text
build/
└── generated-snippets/
    └── store-products-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── path-parameters.adoc
        └── query-parameters.adoc
~~~

This is an abbreviated list; configuration and versions may generate additional default snippets. The two generated documentation tables have content equivalent to:

**Path parameters**

| Parameter | Description |
| --- | --- |
| **storeId** | ID of the store containing the products |

**Query parameters**

| Parameter | Description |
| --- | --- |
| **category** | Product category to search; e.g. BOOK |
| **page** | Zero-based page index; defaults to 0 |

Do not edit files in **generated-snippets** directly: they are artifacts regenerated from tests. Descriptions should be updated in **parameterWithName(...).description(...)** inside the test.

## 6. Notable query parameter scenarios

### 6.1. Parameters that can appear multiple times

Example:

~~~http
GET /api/articles?tag=java&tag=spring
~~~

If the application accepts multiple tags via **@RequestParam List<String> tag**, this is still a single **query parameter name `tag`** appearing multiple times in the query string. Document one descriptor for that name:

~~~java
queryParameters(
    parameterWithName("tag")
        .description("Article filter tag; may be specified multiple times")
        .optional()
)
~~~

Do not create two descriptors with the same name just because the request has two values **java** and **spring**. Add tests confirming how the controller handles repeated values, because **queryParameters(...)** does not automatically validate rules for collecting, sorting, or deduplicating them.

### 6.2. Present-but-empty parameter vs. absent parameter

Compare:

~~~text
/api/search
/api/search?q=
/api/search?q=java
~~~

These three requests can have different meanings if the API distinguishes between *not passed*, *empty string passed*, and *content passed*. **optional()** in REST Docs does not govern the handling policy for these values; the controller must define clear rules and have corresponding tests.

### 6.3. URL encoding and sensitive data

Query values containing spaces, **&**, **=**, or special characters must be encoded according to URI rules. For example, to pass a search query **A&B** as a single value, the client must encode the **&** inside the value so it is not interpreted as a parameter separator.

Similarly, path segments containing **/** or reserved characters must be designed and encoded carefully. Both path and query are parts of the URL that can appear in logs and access histories; do not place passwords, access tokens, or secrets in either location.

## 7. Same idea with WebTestClient and REST Assured

Other test clients still use **pathParameters(...)** and **queryParameters(...)**; the difference lies in how requests are built and how the documentation generator is attached.

### 7.1. WebTestClient

With **WebTestClient** configured for REST Docs, for instance via **documentationConfiguration(...)**:

~~~java
webTestClient.get()
    .uri("/api/stores/{storeId}/products?category=BOOK&page=1", "store-09")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("store-products-webtestclient",
        pathParameters(
            parameterWithName("storeId")
                .description("Store ID")
        ),
        queryParameters(
            parameterWithName("category")
                .description("Product category to search"),
            parameterWithName("page")
                .description("Page index, defaults to 0")
                .optional()
        )
    ));
~~~

Here **document(...)** belongs to **WebTestClientRestDocumentation**. The value **store-09** is passed into the URI template; **category** and **page** are in the query string. In real projects, prefer the client's URI builder API to properly encode complex query values.

### 7.2. REST Assured

With a **RequestSpecification spec** configured with Spring REST Docs:

~~~java
given(spec)
    .filter(document("store-products-rest-assured",
        pathParameters(
            parameterWithName("storeId")
                .description("Store ID")
        ),
        queryParameters(
            parameterWithName("category")
                .description("Product category to search"),
            parameterWithName("page")
                .description("Page index, defaults to 0")
                .optional()
        )
    ))
    .pathParam("storeId", "store-09")
    .queryParam("category", "BOOK")
    .queryParam("page", 1)
    .when()
    .get("/api/stores/{storeId}/products")
    .then()
    .statusCode(200);
~~~

In the REST Assured example, **document(...)** belongs to **RestAssuredRestDocumentation**. **pathParam(...)** supplies the path variable value, while **queryParam(...)** adds query parameters; the two descriptor groups document them accordingly.

## 8. Compiling documentation and integrating into build/CI

Example **src/docs/asciidoc/index.adoc** file using the generated snippets:

~~~asciidoc
= Store Products API
:toc: left

== Product list by store

GET /api/stores/{storeId}/products?category=BOOK&page=1

=== Path parameters

include::{snippets}/store-products-get/path-parameters.adoc[]

=== Query parameters

include::{snippets}/store-products-get/query-parameters.adoc[]

=== HTTP request

include::{snippets}/store-products-get/http-request.adoc[]

=== HTTP response

include::{snippets}/store-products-get/http-response.adoc[]
~~~

The example above assumes the build passes the **snippets** attribute pointing to **build/generated-snippets**. If using **Gradle** with the **org.asciidoctor.jvm.convert** plugin already installed:

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

With this configuration, the Asciidoctor task depends on running tests and receives the path to snippets. In **CI**, run tests before building and publishing documentation. If someone renames **{storeId}** or adds a query parameter without updating descriptions, strict snippet checks can help detect the out-of-sync documentation contract.

If the final output uses **Markdown**, you need a conversion step or a snippet-embedding approach suitable for your Markdown build tool. The **include::...[]** syntax is an **Asciidoctor** directive, not standard Markdown syntax.

## 9. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| **storeId** not recognized by REST Docs | Used a fixed URL instead of a URI template in the MockMvc test | Use **RestDocumentationRequestBuilders.get("/.../{storeId}", value)** |
| **queryParameters(...)** does not see the parameter | Test only set a request parameter without creating a matching query string | With MockMvc, prefer **.queryParam(name, value)** |
| Path parameter reported missing | Forgot **parameterWithName("storeId")** | Declare the exact variable name from the path template |
| Query parameter reported missing | Request added **category** or **page** without describing it | Add the descriptor in **queryParameters(...)** |
| Calling **/api/stores/products?storeId=store-09** fails to match route | Moved ID from path to query while mapping still has **/{storeId}** | Send the URL matching the contract or design another mapping |
| Missing **category** returns HTTP 400 | Controller requires this query parameter | Pass category or change the contract to make it optional |
| Missing **page** still succeeds | Controller defines **defaultValue = "0"** | Document page as optional and note the default value |
| **query-parameters.adoc** not found when building page | Test did not generate snippet or **snippets** path is wrong | Check **document(...)**, test output, and Asciidoctor configuration |
| Description states **page** starts at 1 while code defaults to 0 | Documentation has wrong business meaning | Fix **description(...)** and add an assertion verifying the default value |

## 10. Hands-on exercise

Design an endpoint to retrieve a list of transactions for an account:

~~~http
GET /api/accounts/12/transactions?type=DEBIT&page=2&size=10
~~~

Proposed contract:

- **accountId** is in the URI template **/api/accounts/{accountId}/transactions** and identifies the account owning the transactions.
- **type** is a required query parameter specifying the transaction type.
- **page** is an optional query parameter, defaulting to **0**.
- **size** is an optional query parameter, defaulting to **20**.

Practice tasks:

1. Write a controller with **@PathVariable("accountId")**, **@RequestParam("type")**, **@RequestParam(defaultValue = "0")** for **page**, and **@RequestParam(defaultValue = "20")** for **size**.
2. Write a MockMvc test for the full URL, asserting HTTP 200 and a few values from the response.
3. Attach **document(...)** with **pathParameters(...)** and **queryParameters(...)**, generating both **path-parameters.adoc** and **query-parameters.adoc** under the **account-transactions-get** directory.
4. Test missing **page/size** to verify defaults; test missing **type** to verify the error caused by the required query parameter.
5. Try passing **?accountId=12** while omitting the **/12** segment in the path; explain why the request does not automatically match the detail route.
6. Include both snippets in Asciidoctor documentation and verify the execution order of tests before building HTML.

Solution for the descriptor part:

~~~java
pathParameters(
    parameterWithName("accountId")
        .description("ID of the account owning the transactions")
),
queryParameters(
    parameterWithName("type")
        .description("Required transaction type, e.g. DEBIT or CREDIT"),
    parameterWithName("page")
        .description("Zero-based page index, defaults to 0")
        .optional(),
    parameterWithName("size")
        .description("Maximum number of transactions per page, defaults to 20")
        .optional()
)
~~~

**Completion criteria:** all four parameters are classified accurately; the controller handles required/optional cases properly; tests verify status and data; both snippet tables contain accurate parameter names, roles, and default values.

## Key Takeaways

A **path parameter** is a variable inside the path pattern, typically used to identify resources and required in its corresponding position to match the route. A **query parameter** appears after **?** and usually controls filtering, pagination, or result representation; it can be required or optional depending on the API contract. In Spring REST Docs, describe them with **pathParameters(...)** and **queryParameters(...)** in HTTP tests to produce separate snippets, then bring those snippets into Asciidoctor/Markdown documentation alongside your build and CI pipeline.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html), and [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html).
