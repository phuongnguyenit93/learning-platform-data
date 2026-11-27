# Verifying query parameters appear properly in requests with Spring REST Docs

## 1. Objectives

A search endpoint may publish the parameters `q`, `page`, `size`, and `status`. The documentation states that clients must send `q`, may send `page` and `size`, and may repeat `status`. When the actual request changes, handwritten documentation can quickly become stale:

```http
GET /api/products?q=phone&page=1&size=20&status=ACTIVE HTTP/1.1
Host: api.example.test
Accept: application/json
```

A seemingly small change like adding `sort=price,asc`, renaming `status` to `state`, or accidentally sending `internalFlag=true` can cause the HTTP contract to diverge from the published documentation.

**Spring REST Docs** verifies documentation by matching descriptors against the actual HTTP request sent in a test. With `queryParameters(...)` in its default mode:

- Every query parameter present in the request must be documented or explicitly marked as ignored.
- Every required descriptor must be present in the documented request.
- An `optional()` descriptor may be absent.

In this way, documentation tests detect omitted parameter names or documented parameters that do not appear as required by the contract. This verification is valuable when generating snippets for Asciidoctor/Markdown and running them in build/CI.

In the **SPRING_REST_DOCS** module, examples apply to MockMvc, WebTestClient, or REST Assured. This lesson in the **Query parameters** chapter focuses on verifying the **actual query string**, distinguishing parameter names from values, and intentionally handling valid and mismatched cases.

After this lesson, you will be able to:

1. Understand strict verification in `queryParameters(...)` and failures when requests do not match descriptors.
2. Distinguish query parameters from Servlet request parameters or form parameters.
3. Use `optional()`, `ignored()`, and `relaxedQueryParameters(...)` for their intended purposes.
4. Write positive/negative tests to prove query parameter names appear properly.
5. Generate documentation snippets from test requests and let CI catch contract changes.

## 2. What does `queryParameters(...)` verify?

A basic declaration:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q").description("Search keyword; required"),
    parameterWithName("page").description("Zero-based page index").optional(),
    parameterWithName("size").description("Results per page").optional()
)
```

Spring REST Docs creates `ParameterDescriptor` instances from `parameterWithName(...)`. `queryParameters(...)` generates a snippet for the request's query parameters. When the snippet executes in a test, REST Docs verifies consistency between the names present and the descriptors.

### 2.1. Bidirectional checks

| Scenario | Behavior in default mode |
| --- | --- |
| Request has `q`, descriptor has `q` | Documented |
| Request has `trackingId`, no corresponding descriptor | Error because the request has an undocumented parameter |
| Descriptor has `q`, request lacks `q`, descriptor is not optional | Error because a required parameter is missing |
| Descriptor has `page` and `.optional()`, request lacks `page` | Valid |
| Descriptor `debug` has `.ignored()`, request has `debug` | Parameter is acknowledged but omitted from the snippet table |
| Request has an undocumented name when using `relaxedQueryParameters(...)` | Allowed, if the goal is to document only part of the request |

This check turns snippets into part of HTTP contract testing. For example, if the endpoint starts sending `sort` without the documentation test describing it, default mode catches the change.

### 2.2. REST Docs checks names, not full value validation

`parameterWithName("page")` verifies the name `page`. It does not automatically check:

- Whether the `page` value is an integer.
- Whether `page` is negative or within allowed bounds.
- Whether `status` belongs to the application's enum list.
- Whether a value is empty, whitespace-only, or properly encoded.
- How many times a parameter can repeat or how values combine with AND/OR.

These rules require separate validation and assertions in application tests. Do not treat the success of the documentation step as proof that all values are valid.

## 3. Actual query strings vs. Servlet request parameters

This is the easiest mistake to make when using MockMvc.

### 3.1. Sending a query string properly

Use `queryParam(...)` or put the query string in the URL:

```java
mockMvc.perform(get("/api/products")
        .queryParam("q", "phone")
        .queryParam("page", "1"));

// You can also put the query directly in the URL:
mockMvc.perform(get("/api/products?q=phone&page=1"));
```

Both approaches place data in the query string. When documenting with `queryParameters(...)`, that is what needs to be tested.

### 3.2. Why can `.param(...)` be misleading?

MockMvc provides `.param(...)` to set Servlet request parameters. Servlet parameters can originate from either a query string or an `application/x-www-form-urlencoded` form body; thus calling `.param(...)` alone does not specify where the data comes from.

```java
// This example adds a generic Servlet request parameter:
mockMvc.perform(get("/api/products")
        .param("q", "phone"));

// This example creates an explicit query parameter:
mockMvc.perform(get("/api/products")
        .queryParam("q", "phone"));
```

A controller using `@RequestParam("q")` can receive the value in both ways. However, `queryParameters(...)` is designed for the query string. For tests to accurately represent the URL contract, use `.queryParam(...)` or a URL with `?q=...`.

### 3.3. Query parameters differ from form parameters

| Data location | HTTP example | Spring REST Docs documentation tool |
| --- | --- | --- |
| Query string | `GET /api/products?q=phone` | `queryParameters(...)` |
| Path segment | `GET /api/products/42` | `pathParameters(...)` |
| URL-encoded form body | `POST /api/login` with `username=...` in body | `formParameters(...)` |
| JSON request body | `POST /api/products` with JSON | `requestFields(...)` |
| HTTP header | `Accept-Language: vi` | `requestHeaders(...)` |

Do not substitute `formParameters(...)` for `queryParameters(...)` just because a controller reads both kinds of data via `@RequestParam`. Choose the snippet based on where the parameter actually appears in the HTTP request.

## 4. Required, optional, and ignored descriptors

### 4.1. Required descriptor

If the contract requires clients to always send `q` in the documented request:

```java
queryParameters(
    parameterWithName("q")
        .description("Search keyword; required")
)
```

If the test request omits `q`, REST Docs reports an error. This verifies that the test actually sends the required name.

### 4.2. Optional descriptor

If clients are allowed to omit `page`:

```java
queryParameters(
    parameterWithName("q").description("Search keyword"),
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional()
)
```

When the request includes `q` without `page`, the snippet is still generated. `page` still gets a description row in the table because it is part of the API contract.

`optional()` states that the name may be absent from the test's request. It does not configure a default value in the controller and does not alter `@RequestParam(required = ...)`.

### 4.3. Intentionally ignored descriptor

Some requests may include an internal parameter that is known in advance but not meant for public documentation:

```java
queryParameters(
    parameterWithName("q").description("Search keyword"),
    parameterWithName("debugTrace").ignored()
)
```

`debugTrace` is declared so REST Docs knows the parameter exists, while excluding it from the snippet table. This is an intentional choice; do not use `.ignored()` to hide public parameters that clients need to understand.

### 4.4. Relaxed mode

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedQueryParameters;

relaxedQueryParameters(
    parameterWithName("q").description("Search keyword")
)
```

`relaxedQueryParameters(...)` allows the request to include extra query parameters not listed in the descriptors. Declared descriptors that are not optional must still appear. Relaxed mode is therefore suited for documenting a subset of a request, whereas official API documentation should generally use strict mode to catch newly introduced parameters that were missed.

## 5. Complete example: verifying query parameters with MockMvc

Suppose endpoint `GET /api/products` takes a required `q` and optional `page` and `size`:

### 5.1. Sample controller

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductSearchController {

    @GetMapping("/api/products")
    public String search(
            @RequestParam("q") String query,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size) {

        return "q=" + query + ";page=" + page + ";size=" + size;
    }
}
```

### 5.2. Test documenting a valid request

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ProductQueryParametersDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductSearchController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsQueryParametersThatAppearInRequest() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", "wireless")
                        .queryParam("page", "1"))
                .andExpect(status().isOk())
                .andExpect(content().string("q=wireless;page=1;size=20"))
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Search keyword; required"),
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Page size; defaults to 20")
                                        .optional()
                        )));
    }
}
```

Analysis:

1. The actual request contains two names: `q` and `page`.
2. The descriptors list three names: `q`, `page`, and `size`; `size` is optional so it is not required to appear.
3. The content assertion verifies that `size` defaults to 20 in the controller.
4. `queryParameters(...)` generates a table with all three parameters, even though the request did not send `size`.

This example produces a clear snippet: the documentation informs clients that `size` may be omitted and defaults to 20.

## 6. Testing mismatched cases

A passing documentation test proves that a valid request was documented. To verify strict enforcement, understand common failure scenarios and use them as review criteria.

### 6.1. Request contains an undocumented name

Suppose the request sends `trackingId` without a descriptor:

```java
mockMvc.perform(get("/api/products")
        .queryParam("q", "wireless")
        .queryParam("trackingId", "abc-123"))
    .andExpect(status().isOk())
    .andDo(document("products-search",
        queryParameters(
            parameterWithName("q").description("Search keyword")
        )));
```

In strict mode, the documentation step fails because `trackingId` appeared in the request without being documented or marked ignored. If `trackingId` is part of the public contract, add a descriptor and explain its meaning. If it is an intentional internal parameter, declare `.ignored()` to handle it explicitly.

### 6.2. Required descriptor does not appear

```java
mockMvc.perform(get("/api/products")
        .queryParam("page", "1"))
    .andExpect(status().isBadRequest())
    .andDo(document("products-search",
        queryParameters(
            parameterWithName("q").description("Search keyword; required"),
            parameterWithName("page").description("Page").optional()
        )));
```

In this example, the controller requires `q`; because the request lacks `q`, the controller returns 400. The request does not satisfy the required descriptor. If you are documenting an **error response** as a separate case, use a separate test describing the error request and adjust descriptors to match that case's contract. Never mark `q` as optional just to make a test missing a parameter pass.

### 6.3. Documenting only part of a request

If the test's goal is to document the search portion while `trackingId` is out of scope for documentation:

```java
document("products-search",
    relaxedQueryParameters(
        parameterWithName("q").description("Search keyword")
    )
)
```

This intentionally relaxes checks for undocumented names. Do not use relaxed mode if the test's goal is to catch every newly added query parameter.

## 7. Multi-value requests and verifying repeated names

Given the request:

```http
GET /api/products?status=ACTIVE&status=PREORDER&sort=price,asc&sort=id,asc HTTP/1.1
```

The names `status` and `sort` each appear multiple times. In `queryParameters(...)`, each name needs only one descriptor:

```java
queryParameters(
    parameterWithName("status")
        .description("Product status; repeatable to select multiple statuses"),
    parameterWithName("sort")
        .description("Criterion field,direction; repeatable in priority order")
)
```

REST Docs verifies that the names `status` and `sort` are in the request and creates one description row per name. It does not automatically verify:

- Maximum number of repetitions.
- Preservation of value order during binding.
- Whether values belong to an allowlist.
- Whether multiple statuses combine with OR or AND.

These details must be clearly documented in `description(...)` and verified with application assertions. Specifically, never write two descriptors with the same name just because the request contains two values.

## 8. Reading snippets and integrating with Asciidoctor/CI

With Gradle configured to output snippets to `build/generated-snippets`, the test creates this directory:

```text
build/generated-snippets/
  products-search/
    query-parameters.adoc
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    ...
```

The directory name is derived from the `products-search` identifier. Maven typically uses `target/generated-snippets`; the exact location depends on project configuration.

In `src/docs/asciidoc/products.adoc`:

```asciidoc
= Products API

== Search products

GET /api/products

=== Query parameters

include::{snippets}/products-search/query-parameters.adoc[]

=== Request

include::{snippets}/products-search/http-request.adoc[]
```

The `{snippets}` attribute must point to the snippets directory. If using Markdown, configure `TemplateFormats.markdown()` to generate Markdown snippets and use an appropriate document assembly tool; plain Markdown has no standard include syntax like Asciidoctor.

Build/CI workflow:

1. Add the Spring REST Docs dependency matching your integration: MockMvc, WebTestClient, or REST Assured.
2. Configure the snippets directory as an output of the tests.
3. Configure the Asciidoctor task or documentation rendering step to depend on the test task.
4. Run tests and publish documentation in CI; if descriptors do not match the request, the documentation test fails and the pipeline fails.

Example command once tasks are configured:

```bash
./gradlew test asciidoctor
```

When a new query parameter is added to a request, a documentation test using strict `queryParameters(...)` will catch the missing descriptor. When changing endpoints or parameter names, update both the test request and the documentation descriptions.

## 9. Working with WebTestClient and REST Assured

### 9.1. WebTestClient

With WebTestClient configured for Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder.path("/api/products")
                .queryParam("q", "wireless")
                .queryParam("page", 1)
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("products-search-webclient",
                queryParameters(
                        parameterWithName("q").description("Keyword; required"),
                        parameterWithName("page").description("Zero-based page index").optional(),
                        parameterWithName("size").description("Page size").optional()
                )));
```

`q` and `page` appear in the constructed URI; `size` is optional and may be absent. When adding a query parameter to the URI while forgetting its descriptor in strict mode, the documentation step catches the mismatch.

### 9.2. REST Assured

REST Assured sends query parameters via the request specification API:

```java
given()
    .filter(documentationFilter)
    .queryParam("q", "wireless")
    .queryParam("page", 1)
    .when()
    .get("/api/products")
    .then()
    .statusCode(200);
```

`documentationFilter` represents a filter configured with the Spring REST Docs integration and `document(..., queryParameters(...))`. Calling `.queryParam(...)` alone will not generate snippets unless the documentation filter is attached.

## 10. Common errors and diagnostics

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Controller reads `q`, yet snippet reports no query parameter | Test used `.param(...)` or passed data in a form body | Use `.queryParam(...)` or a real query URL |
| Request containing `sort` causes documentation failure | No `sort` descriptor declared | Add `parameterWithName("sort")` with a description, or use ignored intentionally |
| Request missing `q` causes documentation failure | `q` descriptor is required | Send `q`, or use optional only if the contract genuinely allows absence |
| Documentation table omits an optional parameter | No descriptor declared even though marked optional in the controller | Add an `.optional()` descriptor; REST Docs does not read controller annotations automatically |
| Used `.ignored()`, yet parameter is not handled as expected | Ignored descriptor was not declared in that `document` call or name is wrong | Declare the exact name and inspect the request URI |
| Relaxed mode hides a new public parameter | `relaxedQueryParameters(...)` permits undocumented names | Use strict mode in the primary contract tests |
| Two descriptors created for two values with the same name | Confusing repetition count with parameter name count | Use one descriptor per name and document repetition in `description` |
| Snippet exists, yet HTML page lacks the table | Wrong identifier or include path; docs task ran before tests | Check the `products-search` folder, `{snippets}`, and task dependencies |

## 11. Practice exercise

Design an endpoint:

```http
GET /api/orders?customerId=CU-10&status=PAID&status=SHIPPED&page=0 HTTP/1.1
```

Contract:

- `customerId` is required and accepts only a single value.
- `status` is optional and repeatable; each value accepts only `PENDING`, `PAID`, `SHIPPED`, or `CANCELLED`.
- `page` is optional, defaults to 0, and is non-negative.
- Any other unannounced query parameter must be caught by strict documentation tests.

Tasks:

1. Create a Spring MVC controller using `@RequestParam` for the three names above.
2. Write a MockMvc test using `.queryParam("customerId", "CU-10")`, `.queryParam("status", "PAID", "SHIPPED")`, and `.queryParam("page", "0")`.
3. Document with `queryParameters(...)`; `customerId` required, `status` and `page` optional.
4. Create a test request containing `debug=true` without a descriptor; observe the documentation error, then decide whether to add a descriptor or `.ignored()` according to the contract.
5. Create a test missing `customerId` and verify the request fails the required contract.
6. Generate the snippet, include it in Asciidoctor, and run both tests and rendering in CI.

**Completion criteria:** Documentation tests prove the request contains the exact published names; required parameters are not missing; out-of-contract parameters are detected; the query parameters table is generated from tests and appears on the documentation page.

## 12. Key takeaways

`queryParameters(...)` verifies whether query parameter names in a request are completely documented and whether required descriptors are present. Use `.queryParam(...)` or an actual query URL to test the query string; use `.optional()` for names permitted to be absent, `.ignored()` for known parameters hidden from the table, and `relaxedQueryParameters(...)` only when intentionally documenting part of a request. Combine name checks with value assertions and application validation so Spring REST Docs accurately reflects the HTTP contract.

### References

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring Framework — `@RequestParam` in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
