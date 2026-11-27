# path-parameters, query-parameters, and form-parameters

## 1. Three Parameter Locations in an HTTP Request

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Default Snippets** chapter, HTTP tests generate snippets to document the API contract. A request can carry parameters in the URL path, in the query string, or in the form data section of the request body. Spring REST Docs provides dedicated descriptors for each type:

| Parameter Type | Descriptor | Snippet | Data Location |
| --- | --- | --- | --- |
| Path parameter | pathParameters(...) | path-parameters.adoc | Placeholder in URI template, e.g., /users/{id} |
| Query parameter | queryParameters(...) | query-parameters.adoc | Query section after ?, e.g., ?page=2&size=20 |
| Form parameter | formParameters(...) | form-parameters.adoc | Form body, typically with media type application/x-www-form-urlencoded |

These three types cannot be used interchangeably at will. Path parameters typically identify resources; query parameters typically filter, sort, or paginate; form parameters typically receive data from HTML forms or form-urlencoded clients. A JSON body has its own structure and is typically documented with requestFields(...), not formParameters(...).

Spring REST Docs generates descriptor snippets when the test calls document(...) with the corresponding descriptors. Simply sending a request without declaring descriptors will not cause these parameter tables to appear automatically. Examples in this lesson use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**.

## 2. Path Parameters: Variables Inside the URI Template

A path parameter is part of the endpoint path:

```text
GET /api/users/{userId}/orders/{orderId}
```

For a specific call, placeholders are replaced with values:

```text
GET /api/users/42/orders/9001
```

Path parameters are appropriate when values are part of a resource's identifier or hierarchy. For example, userId identifies the user and orderId identifies an order belonging to that user.

Declaring descriptors:

```java
pathParameters(
    parameterWithName("userId").description("User ID"),
    parameterWithName("orderId").description("Order ID")
)
```

REST Docs generates path-parameters.adoc, typically a table containing parameter names and descriptions. Descriptors can mark parameters as optional or ignored depending on the contract and test cases.

### MockMvc Example

```java
mockMvc.perform(
        RestDocumentationRequestBuilders
            .get("/api/users/{userId}/orders/{orderId}", 42, 9001)
    )
    .andExpect(status().isOk())
    .andDo(document("users-order-find",
        pathParameters(
            parameterWithName("userId").description("User ID"),
            parameterWithName("orderId").description("Order ID")
        )
    ));
```

With MockMvc and Spring Framework 6.1 or earlier, use methods from RestDocumentationRequestBuilders to preserve the URI template in the request so REST Docs can retrieve placeholder names. If another builder drops the template, the request may retain only the expanded path and path parameter documentation will be unable to identify variable names. For newer Spring Framework versions, check your project version's documentation.

Path parameters typically fit endpoints such as:

```text
GET    /api/products/{id}
PATCH  /api/products/{id}
DELETE /api/products/{id}
GET    /api/users/{userId}/orders/{orderId}
```

Optional filters or sorting choices usually fit query parameters better when they are not part of the resource identification structure.

## 3. Query Parameters: Filtering, Pagination, and Controlling Results

Query parameters appear after ? in the URL. Multiple parameters are separated by &:

```text
GET /api/products?category=keyboard&page=0&size=20&sort=name,asc
```

Common use cases:

- Filtering: category, status, active.
- Pagination: page, size, cursor.
- Sorting: sort, direction.
- Representation choices: locale, include, fields.

Declaring query descriptors:

```java
queryParameters(
    parameterWithName("category")
        .description("Product category to filter by"),
    parameterWithName("page")
        .description("Page number, starting from 0"),
    parameterWithName("size")
        .description("Number of items per page"),
    parameterWithName("sort")
        .description("Sort field and direction")
)
```

The generated snippet is query-parameters.adoc. It documents query parameters, not a table for path or form data.

### MockMvc Example

```java
mockMvc.perform(
        get("/api/products")
            .queryParam("category", "keyboard")
            .queryParam("page", "0")
            .queryParam("size", "20")
    )
    .andExpect(status().isOk())
    .andDo(document("products-search",
        queryParameters(
            parameterWithName("category").description("Product category"),
            parameterWithName("page").description("Page number"),
            parameterWithName("size").description("Page size")
        )
    ));
```

If another request builder/client builds the query string directly in the URI, descriptors must still match the parameter names received by the operation.

### Optional and Relaxed Mode

A query parameter may not appear in every request, such as sort or locale. Mark it optional when the contract allows omission:

```java
parameterWithName("sort")
    .description("Sort field")
    .optional()
```

In strict mode, a parameter present in the request but undocumented can cause snippet generation to fail; a required descriptor absent from the request can also fail the test. This is the mechanism that keeps documentation in sync with tested requests.

When you only want to document a subset of parameters in a scenario, use the corresponding relaxed API, such as relaxedQueryParameters(...). Relaxed mode ignores undocumented parameters; use it intentionally to avoid masking undocumented query parameters added to the API.

## 4. Form Parameters: Form Data in the Request Body

Form parameters are sent in the body, typically with the header:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=linh&rememberMe=true
```

Distinguishing query and form parameters:

| Criterion | Query parameter | Form parameter |
| --- | --- | --- |
| Location | URL after ? | Request body |
| Media type | Part of the URL | Typically application/x-www-form-urlencoded |
| Example | /products?page=0 | username=linh&rememberMe=true |
| Descriptor | queryParameters(...) | formParameters(...) |
| Snippet | query-parameters.adoc | form-parameters.adoc |

Form parameters commonly appear in login forms, legacy search forms, HTML forms, or legacy-compatible endpoints. If an endpoint accepts JSON such as {"username":"linh"}, use requestFields(...) to document the JSON, not form parameter descriptors.

Declaring form descriptors:

```java
formParameters(
    parameterWithName("username").description("Username"),
    parameterWithName("rememberMe")
        .description("Whether to remember the login session")
)
```

The generated snippet is form-parameters.adoc. The formParameters(...) API has been in Spring REST Docs since version 3.0.0; for older projects, check compatibility before using it.

### MockMvc Example

```java
mockMvc.perform(
        post("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("username", "linh")
            .param("rememberMe", "true")
    )
    .andExpect(status().isOk())
    .andDo(document("login-form",
        formParameters(
            parameterWithName("username").description("Username"),
            parameterWithName("rememberMe")
                .description("Remember login session")
        )
    ));
```

MockMvc .param(...) adds a request parameter; for form-urlencoded POST requests, form values are sent in the form body. Set the appropriate Content-Type so the test accurately reflects how clients send data.

Form parameters can also be optional:

```java
parameterWithName("rememberMe")
    .description("Remember login session")
    .optional()
```

If the form contains a sent parameter that is undocumented, strict formParameters(...) can cause the operation to fail. Use relaxedFormParameters(...) when a scenario only needs to document a subset; remaining parameters are ignored.

## 5. Complete Example: Path and Query in One Endpoint

A search API can use both path and query parameters at the same time:

```java
@GetMapping("/users/{userId}/orders")
List<OrderResponse> findOrders(
        @PathVariable long userId,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page) {
    // ...
}
```

Test:

```java
mockMvc.perform(
        RestDocumentationRequestBuilders
            .get("/api/users/{userId}/orders", 42)
            .queryParam("status", "PAID")
            .queryParam("page", "0")
    )
    .andExpect(status().isOk())
    .andDo(document("user-orders-search",
        pathParameters(
            parameterWithName("userId").description("User ID")
        ),
        queryParameters(
            parameterWithName("status")
                .description("Filter by status").optional(),
            parameterWithName("page").description("Page number")
        )
    ));
```

A simple form endpoint:

```java
@PostMapping(
    path = "/login",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
ResponseEntity<Void> login(
        @RequestParam String username,
        @RequestParam(required = false) String returnTo) {
    // ...
    return ResponseEntity.ok().build();
}
```

Test:

```java
mockMvc.perform(
        post("/api/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("username", "linh")
            .param("returnTo", "/dashboard")
    )
    .andExpect(status().isOk())
    .andDo(document("login-form",
        formParameters(
            parameterWithName("username").description("Username"),
            parameterWithName("returnTo")
                .description("Return path").optional()
        )
    ));
```

In a real project, ensure controller mappings and tests use the same context path/API prefix. Do not record real passwords or tokens in form snippets; login examples should use dummy credentials.

## 6. Validating Descriptors and Contracts

Parameter snippets do more than generate tables; descriptors also validate the request recorded by the test.

| Scenario | Typical Strict Mode Behavior |
| --- | --- |
| Request has an undocumented parameter | Test fails because documentation does not cover the parameter |
| Descriptor is required but request lacks the parameter | Test fails because descriptor does not match the operation |
| Descriptor is optional and request omits the parameter | Accepted |
| Descriptor is ignored | Not shown in the snippet while preventing an error from that parameter |
| Using relaxed descriptor | Parameters outside the documented list are ignored |

Strict mode is appropriate when an operation represents the complete contract. Relaxed mode is useful when multiple endpoints share parameters or a test focuses on only one group of parameters. If relaxed is used everywhere, the API can add parameters without documentation reflecting them.

Create separate operations for meaningful variants: default search, search with filters/sorting, form submission with optional fields absent, and form submission with all fields present. When variants differ in contract, separating operation IDs keeps documentation clear and prevents snippets from overwriting each other.

## 7. Including Parameter Snippets in Asciidoctor

Example src/docs/asciidoc/users.adoc file:

```asciidoc
= Users API
:toc: left

== Find user's orders

=== Path parameters
include::{snippets}/user-orders-search/path-parameters.adoc[]

=== Query parameters
include::{snippets}/user-orders-search/query-parameters.adoc[]

== Login via form

=== Form parameters
include::{snippets}/login-form/form-parameters.adoc[]
```

The {snippets} attribute must point to the root generated-snippets directory. The path following it must match the operation ID passed to document(...). If a custom outputDir is set, update the snippets attribute accordingly.

You can also include HTTP request, cURL, or HTTPie for the same operation so readers can view the full request alongside parameter tables.

## 8. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| path-parameters.adoc not generated | pathParameters(...) not called, or URI template lost. | Declare descriptors and use a request builder that preserves templates. |
| Missing query-parameters.adoc | Wrong API used or queryParameters(...) not added. | Use RequestDocumentation.queryParameters(...) for query strings. |
| Missing form-parameters.adoc | Sent JSON body or formParameters(...) not called. | Send form-urlencoded and declare the proper descriptors. |
| Test reports undocumented parameter | Request has an undocumented parameter in strict mode. | Add descriptors or use relaxed mode intentionally. |
| Test reports required parameter not found | Descriptor is not optional while request omits it. | Fix the test or mark optional if the contract allows it. |
| Form parameter not recognized | Content-Type/body is not form-urlencoded. | Set application/x-www-form-urlencoded and send form data properly. |
| Query is in URL but missing from table | Descriptor does not list query parameter or client built a different request than expected. | Compare the request snippet and descriptors. |
| Asciidoctor cannot find snippet | Wrong operation ID, outputDir, or snippets attribute. | Check the directory after tests and include paths. |

## 9. Hands-on Exercise

Create an Orders API including:

1. GET /api/users/{userId}/orders: path parameter userId, query parameters status, page, and size.
2. POST /api/login: accepts form-urlencoded containing username, password, and rememberMe.
3. Write MockMvc tests for both endpoints; use pathParameters(...), queryParameters(...), and formParameters(...) respectively.
4. Create cases where status and rememberMe are optional; verify tests still pass when they are absent.
5. Intentionally send an extra undocumented parameter to observe strict mode failing, then add the descriptor or move only the necessary test to relaxed mode.
6. Include the three parameter snippets in Asciidoctor and place them beside the corresponding request snippets.
7. Verify no real passwords/tokens appear in snippets and run clean test along with Asciidoctor.

**Completion criteria:** distinguish path, query, and form parameters by transmission location; use the three descriptors properly; explain strict/relaxed/optional; read the three corresponding snippet files; documentation is regenerated from tests in build/CI without leaking authentication details.

## 10. References

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
