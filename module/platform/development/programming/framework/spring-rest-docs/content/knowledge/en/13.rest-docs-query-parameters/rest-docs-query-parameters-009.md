# Distinguishing query parameters from path parameters in Spring REST Docs

## 1. Two places for passing data in a URI

A REST API often uses both **path parameters** and **query parameters**. For example:

```http
GET /api/products/42/reviews?rating=5&page=0 HTTP/1.1
Host: api.example.test
Accept: application/json
```

In the URI above, `42` is the product identifier located in the path, while `rating=5` and `page=0` sit after `?` in the query string. In Spring MVC, path values are typically bound with `@PathVariable`, and query string values are typically bound with `@RequestParam`.

Where data is placed determines routing, binding, and which snippet to use when generating documentation. Confusing the two types can prevent the controller from receiving data properly or cause Spring REST Docs to place parameters in the wrong table.

In the **SPRING_REST_DOCS** module, Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. This lesson belongs to the **Query parameters** chapter and helps you classify URI data properly and use `pathParameters(...)` or `queryParameters(...)` accordingly when generating Asciidoctor/Markdown snippets and integrating tests into build/CI.

After this lesson, you will be able to:

1. Identify path parameters, query parameters, and related URI components.
2. Map `@PathVariable` to `pathParameters(...)`, and `@RequestParam` to `queryParameters(...)`.
3. Write a MockMvc test documenting a request with both path and query parameters.
4. Distinguish resource identifiers from filtering, pagination, and sorting criteria.
5. Diagnose common errors when using the wrong snippet or parameter placement.

## 2. What is a path parameter?

A path parameter is a value located in a URL path segment and mapped to a variable in the path template.

Example route template:

```text
/api/products/{productId}
```

Concrete request:

```http
GET /api/products/42 HTTP/1.1
```

Spring MVC binding:

```java
@GetMapping("/api/products/{productId}")
public Product getProduct(@PathVariable Long productId) {
    return productService.findById(productId);
}
```

`{productId}` is a template placeholder; `42` is the concrete value sent by the client in the request. Path parameters typically identify a resource or a component within a resource hierarchy:

| Route template | Path parameter | Meaning |
| --- | --- | --- |
| `/api/products/{id}` | `id` | A specific product |
| `/api/orders/{orderId}/items/{itemId}` | `orderId`, `itemId` | An item belonging to an order |
| `/api/users/{userId}/addresses/{addressId}` | `userId`, `addressId` | An address belonging to a user |

Path parameters are usually part of the route structure. If a product ID is required, a route containing the `{productId}` placeholder does not match when the ID segment is missing.

## 3. What is a query parameter?

A query parameter resides in the query string portion of a URI, starting after `?`. Name/value pairs are usually separated by `&`:

```http
GET /api/products?category=phone&status=ACTIVE&page=0&size=20 HTTP/1.1
```

Here, `category`, `status`, `page`, and `size` are query parameters. Spring MVC usually binds them with `@RequestParam`:

```java
@GetMapping("/api/products")
public ProductPage search(
        @RequestParam(required = false) String category,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return productService.search(category, status, page, size);
}
```

Query parameters usually express options for an operation on a resource or collection:

- Filtering: `status=ACTIVE`, `category=phone`.
- Searching: `q=wireless`.
- Pagination: `page=0&size=20`.
- Sorting: `sort=price,asc`.
- Representation options: `view=summary` or `locale=vi`.

Many query parameters can be absent or repeated depending on the endpoint contract. Default rules, valid values, repetition counts, and conditional dependencies must be explicitly defined in the application.

## 4. Comparing path parameters and query parameters

| Criterion | Path parameter | Query parameter |
| --- | --- | --- |
| Location | Inside the path, typically tied to a `{name}` placeholder | After `?`, as `name=value` pairs |
| Example | `/products/42` | `/products?status=ACTIVE` |
| Spring MVC | `@PathVariable` | `@RequestParam` |
| Spring REST Docs | `pathParameters(...)` | `queryParameters(...)` |
| Default snippet | `path-parameters.adoc` | `query-parameters.adoc` |
| Typical role | Identifies a resource or path element | Filtering, searching, pagination, sorting, options |
| Can it be absent? | A route with a placeholder normally requires the corresponding segment; another route may omit it | Can be optional per contract |
| Can it be repeated? | Not like a repeated query key; a path may have multiple placeholders at different positions | Can repeat the same name, e.g. `tag=java&tag=spring` |

### 4.1. Do not classify by variable name

The name `id` can appear in several locations:

```http
GET /api/products/42/reviews?userId=7&page=0 HTTP/1.1
```

In this example, `42` is the path value for `productId`; `userId=7` and `page=0` are query parameters. The data's meaning alone does not dictate parameter type; **its position in the URI** does. A query parameter named `productId` is still a query parameter if sent after `?`.

### 4.2. Both can be used in the same request

An API to fetch reviews for a product, filtered by rating and paginated:

```http
GET /api/products/42/reviews?rating=5&page=0&size=10 HTTP/1.1
```

The controller can accept:

```java
@GetMapping("/api/products/{productId}/reviews")
public ReviewPage findReviews(
        @PathVariable Long productId,
        @RequestParam(required = false) Integer rating,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "10") int size) {
    return reviewService.findByProduct(productId, rating, page, size);
}
```

When documenting, separate the two descriptor groups according to their positions.

## 5. Spring REST Docs: using the right snippet for each type

Spring REST Docs provides two distinct APIs in `org.springframework.restdocs.request.RequestDocumentation`:

- `pathParameters(...)` documents variables in the URI template.
- `queryParameters(...)` documents names appearing in the query string.

Example:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

document("product-reviews",
    pathParameters(
        parameterWithName("productId")
            .description("ID of the product whose reviews are requested")
    ),
    queryParameters(
        parameterWithName("rating")
            .description("Filter by review rating, from 1 to 5")
            .optional(),
        parameterWithName("page")
            .description("Zero-based page index; defaults to 0")
            .optional(),
        parameterWithName("size")
            .description("Number of reviews per page; defaults to 10")
            .optional()
    )
);
```

When the documentation test passes, Spring REST Docs generates two separate snippets:

```text
product-reviews/
  path-parameters.adoc
  query-parameters.adoc
  http-request.adoc
  http-response.adoc
  curl-request.adoc
```

Each name needs a descriptor in its corresponding group. Do not declare `productId` inside `queryParameters(...)` if the request only has the path segment `/products/42`; nor declare `rating` inside `pathParameters(...)` if it sits after `?`.

### 5.1. Path parameters and requiredness

A route template `/products/{productId}` requires a `productId` value to match the route. Without that segment, the request normally will not reach that handler. Therefore, path descriptors are usually required:

```java
pathParameters(
    parameterWithName("productId")
        .description("ID of the product")
)
```

Do not use `optional()` to mask a route contradiction: if a path placeholder is required in the mapping, the documented request must supply a value. If an endpoint has two distinct routes, document them as separate requests/operations.

### 5.2. Documenting default values for queries

For a query parameter such as `page`:

```java
queryParameters(
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional()
)
```

`optional()` allows the documented request to omit `page`. The text "defaults to 0" is only part of the contract description; the actual default value must reside in controller configuration/logic and be tested separately.

## 6. Complete example: path combined with query in MockMvc

### 6.1. Sample controller

Endpoint fetching reviews for a product; rating and pagination are query parameters:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReviewController {

    @GetMapping("/api/products/{productId}/reviews")
    public String findReviews(
            @PathVariable Long productId,
            @RequestParam(name = "rating", required = false) Integer rating,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "10") int size) {

        return "productId=" + productId
                + ";rating=" + (rating == null ? "ALL" : rating)
                + ";page=" + page
                + ";size=" + size;
    }
}
```

### 6.2. MockMvc setup and documentation test

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
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ReviewDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ReviewController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsPathAndQueryParametersSeparately() throws Exception {
        mockMvc.perform(get("/api/products/{productId}/reviews", 42)
                        .queryParam("rating", "5")
                        .queryParam("page", "0")
                        .queryParam("size", "10"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "productId=42;rating=5;page=0;size=10"))
                .andDo(document("product-reviews",
                        pathParameters(
                                parameterWithName("productId")
                                        .description("ID of the product whose reviews are requested")
                        ),
                        queryParameters(
                                parameterWithName("rating")
                                        .description("Review rating, from 1 to 5")
                                        .optional(),
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Reviews per page; defaults to 10")
                                        .optional()
                        )));
    }
}
```

Request breakdown:

1. `get("/api/products/{productId}/reviews", 42)` replaces the placeholder with path value `42`.
2. `queryParam("rating", "5")`, `queryParam("page", "0")`, and `queryParam("size", "10")` add data after `?`.
3. The response assertion confirms Spring MVC binds both `@PathVariable` and `@RequestParam` correctly.
4. `pathParameters(...)` builds the table for `productId`; `queryParameters(...)` builds the table for `rating`, `page`, and `size`.

With Gradle configured to output snippets to `build/generated-snippets`, the `product-reviews` identifier creates a directory containing:

```text
build/generated-snippets/product-reviews/
  path-parameters.adoc
  query-parameters.adoc
  http-request.adoc
  http-response.adoc
  curl-request.adoc
```

In Maven, the directory is typically under `target/generated-snippets/product-reviews/` when configured accordingly.

## 7. Including both snippets in an Asciidoctor document

In the Asciidoctor page for the reviews API, include both snippet files:

```asciidoc
= Product Reviews API

== Get product reviews

GET /api/products/{productId}/reviews

=== Path parameters

include::SNIPPETS/product-reviews/path-parameters.adoc[]

=== Query parameters

include::SNIPPETS/product-reviews/query-parameters.adoc[]

=== HTTP request

include::SNIPPETS/product-reviews/http-request.adoc[]

=== HTTP response

include::SNIPPETS/product-reviews/http-response.adoc[]
```

In your project configuration, replace the `SNIPPETS` prefix in the example above with the configured snippet path (typically via an Asciidoctor attribute). If using Markdown templates, you can choose `TemplateFormats.markdown()`; the build step will need to assemble snippets using your project's tooling since plain Markdown does not offer a standard `include` syntax like Asciidoctor.

## 8. Common API design mistakes

### 8.1. Putting a resource identifier in the query without reason

Example:

```http
GET /api/products?id=42
```

Not every API using an `id` query parameter is wrong; however, when `id` uniquely identifies a single resource, the route `/api/products/42` usually expresses resource-oriented design more clearly. Query `id` can make sense if a search endpoint supports multiple IDs:

```http
GET /api/products?id=42&id=43
```

Choose the structure based on the business contract, not on a single parameter's name.

### 8.2. Using a path segment for an optional filter

For example, a route `/api/products/status/ACTIVE` may be used when status is a fixed part of the resource hierarchy. If the endpoint is a product list with multiple optional filter criteria, a query such as `/api/products?status=ACTIVE` is usually more flexible. Consider combining multiple filters and how URLs are bookmarked/shared.

### 8.3. Declaring descriptors in the wrong group

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `productId` in `queryParameters(...)` when it is in `/products/42` | REST Docs reports an undocumented query parameter or mismatched descriptor | Move `productId` to `pathParameters(...)` |
| Putting `page` in `pathParameters(...)` when the request uses `?page=0` | REST Docs cannot find the matching path variable | Move `page` to `queryParameters(...)` |
| Request includes query `sort` without a descriptor | Strict query snippet fails | Add the descriptor and description |
| URI template has no `{productId}`, yet descriptor has `productId` | Path descriptor does not match the route template | Fix the route template or descriptor to match the actual endpoint |
| Using fixed URL `/products/42` while wanting to document the placeholder name | No template variable for REST Docs to recognize | Use `get("/products/{productId}", 42)` in MockMvc tests |

## 9. Encoding and data types for path/query

Both path parameters and query parameters can contain characters that must be percent-encoded, though component rules differ. Use a URI builder or HTTP request builder to encode each component properly. Do not encode an entire URI with an encoder meant for query values.

- Path: `/products/42`; the `{productId}` placeholder is replaced by a concrete value.
- Query: `/products?name=wireless%20earbuds`; `%20` represents a space in the query value.
- Data containing `/`, `?`, `&`, or `#` must be handled per component. Do not assume an encoded slash in a path will always be preserved by servers as a character within one segment; proxies and containers may enforce their own policies.

With Spring MVC, type conversion also depends on position while passing through the binding/conversion mechanism. For example:

```java
@GetMapping("/api/products/{productId}")
public Product get(@PathVariable Long productId) { ... }

@GetMapping("/api/products")
public ProductPage find(@RequestParam(defaultValue = "0") int page) { ... }
```

If `productId=abc` or `page=abc`, conversion can fail and the application typically returns HTTP 400. Spring REST Docs does not automatically validate `Long` or `int` values; write separate tests for valid and invalid cases.

## 10. WebTestClient and REST Assured

### 10.1. WebTestClient

With WebTestClient configured for Spring REST Docs, pass path variables via URI template and queries via URI builder:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder
                .path("/api/products/{productId}/reviews")
                .queryParam("rating", 5)
                .queryParam("page", 0)
                .build(42))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("product-reviews-webclient",
                pathParameters(
                        parameterWithName("productId").description("Product ID")
                ),
                queryParameters(
                        parameterWithName("rating").description("Review rating").optional(),
                        parameterWithName("page").description("Zero-based page index").optional()
                )));
```

### 10.2. REST Assured

REST Assured also separates path parameters and query parameters. How the documentation filter is attached depends on your REST Docs integration setup:

```java
given()
        .filter(documentationFilter)
        .pathParam("productId", 42)
        .queryParam("rating", 5)
        .queryParam("page", 0)
        .when()
        .get("/api/products/{productId}/reviews")
        .then()
        .statusCode(200);
```

Inside the documentation filter, declare `pathParameters(...)` for `productId` and `queryParameters(...)` for `rating` and `page`. Calling `pathParam(...)`/`queryParam(...)` alone does not generate snippets; `document(...)` must still be attached to the filter.

## 11. Build and CI

To automate documentation verification:

1. Configure Spring REST Docs for MockMvc, WebTestClient, or REST Assured.
2. Place snippet output in a stable directory such as `build/generated-snippets` (Gradle) or `target/generated-snippets` (Maven).
3. Make the Asciidoctor task depend on the test task and include both `path-parameters.adoc` and `query-parameters.adoc`.
4. Run tests and compile documentation in CI. Changing a route placeholder or adding a query parameter without updating descriptors will be caught by strict documentation tests.

Example Gradle command once the project configures the corresponding tasks:

```bash
./gradlew test asciidoctor
```

For an endpoint using both path and query, changing the `/products/{productId}` route and changing the `?status=...` filter are two distinct contract changes. Tests and documentation should reflect each change in the right snippet group.

## 12. Hands-on exercise

Build documentation for the endpoint:

```http
GET /api/customers/CU-42/orders?status=PAID&status=SHIPPED&page=0&size=10 HTTP/1.1
```

Contract:

- `customerId` is in the path, required, and identifies the customer.
- `status` is an optional, repeatable query parameter; accepts only `PENDING`, `PAID`, `SHIPPED`, or `CANCELLED`.
- `page` and `size` are optional query parameters, defaulting to 0 and 10 respectively.
- `size` is within the range 1–100.

Tasks:

1. Create a controller using `@PathVariable` for `customerId` and `@RequestParam` for `status`, `page`, and `size`.
2. Write a MockMvc test using `get("/api/customers/{customerId}/orders", "CU-42")` and `.queryParam(...)` for the filters.
3. Attach `pathParameters(parameterWithName("customerId")...)` separately from `queryParameters(...)` for the three query parameters.
4. Assert the response contains the bound values and write negative tests for invalid statuses or out-of-range sizes.
5. Generate both snippets, include them in Asciidoctor, and run build/CI.

**Completion criteria:** Path values are not confused with query values; each parameter belongs to the right descriptor group; valid requests generate all snippets; validation/value checks are performed outside descriptors.

## 13. Key takeaways

Path parameters live in path template segments and are typically bound with `@PathVariable`; query parameters sit after `?` and are typically bound with `@RequestParam`. In Spring REST Docs, use `pathParameters(...)` for route placeholders and `queryParameters(...)` for query string names. A single request can use both groups simultaneously; generate two separate snippets and test both binding and value rules before integrating documentation into build/CI.

### References

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — `@PathVariable` in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html)
- [Spring Framework — `@RequestParam` in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
