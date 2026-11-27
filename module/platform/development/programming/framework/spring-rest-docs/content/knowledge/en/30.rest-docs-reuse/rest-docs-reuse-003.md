# Reusing parameter descriptors

## 1. Why reuse parameter descriptors?

In the **Spring REST Docs (SPRING_REST_DOCS)** module, under the **Reuse** chapter, HTTP tests generate snippets describing path parameters, query parameters, and form parameters of a REST API. Many endpoints can share the same parameter conventions: pagination, status filtering, date ranges, or resource identifiers. If each test declares parameter names and descriptions independently, documentation easily becomes inconsistent and hard to update when contracts change.

Spring REST Docs uses ParameterDescriptor to describe parameters. Descriptors are passed to pathParameters(...), queryParameters(...), or formParameters(...) to generate the corresponding snippets and verify actual requests. You can group shared descriptors into factory methods and combine them with operation-specific descriptors.

For example:

```text
GET /api/products?status=ACTIVE&page=0&size=20
GET /api/orders?status=PAID&page=0&size=20
GET /api/users?status=ENABLED&page=0&size=20
```

All three endpoints have page, size, and status, but status means something different for each resource. Reuse needs to keep shared descriptions accurate and allow each resource to provide its own description when semantics differ.

After this lesson, you will be able to distinguish ParameterDescriptor from FieldDescriptor; create factories for path/query/form descriptors; combine shared parameter groups with specific parameters; handle optional, ignored, and relaxed modes; and keep strict validation when contracts change.

The examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**. With WebTestClient or REST Assured, the test integration APIs differ, but ParameterDescriptors can still be organized in shared helpers.

## 2. ParameterDescriptor vs. FieldDescriptor

The two descriptors serve different parts of an HTTP request:

| Type | Target | API Example | Snippet |
| --- | --- | --- | --- |
| Path parameter | ParameterDescriptor | pathParameters(...) | path-parameters.adoc |
| Query parameter | ParameterDescriptor | queryParameters(...) | query-parameters.adoc |
| Form parameter | ParameterDescriptor | formParameters(...) | form-parameters.adoc |
| JSON payload field | FieldDescriptor | requestFields(...) / responseFields(...) | request-fields.adoc / response-fields.adoc |

For example:

```http
POST /api/products?dryRun=true HTTP/1.1
Content-Type: application/json

{"name":"Keyboard","price":89.5}
```

- dryRun is a query parameter, described with ParameterDescriptor.
- name and price are JSON fields in the body, described with FieldDescriptor.

Do not use requestFields(...) to describe query parameters, and do not use queryParameters(...) to describe JSON fields. Choosing the right descriptor ensures snippets accurately reflect where data resides in the HTTP request.

## 3. Creating a factory for shared query parameters

Suppose multiple endpoints support pagination. Create a helper in the test source set:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.request.ParameterDescriptor;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

public final class CommonParameterDescriptors {

    private CommonParameterDescriptors() {
    }

    public static List<ParameterDescriptor> paginationParameters() {
        return List.of(
            parameterWithName("page")
                .description("Page number, zero-based"),
            parameterWithName("size")
                .description("Number of items per page")
        );
    }
}
```

Used in a test:

```java
queryParameters(
    CommonParameterDescriptors.paginationParameters()
)
```

The returned list can be used with overloads that accept Iterable/List descriptors in the corresponding API. If the Spring REST Docs version your project uses only provides a varargs overload at the call site, convert the list to an array with toArray(ParameterDescriptor[]::new).

## 4. Combining shared parameters with specific parameters

A product search endpoint has pagination query parameters along with category and status filters:

```java
static List<ParameterDescriptor> productSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonParameterDescriptors.paginationParameters());

    parameters.add(
        parameterWithName("category")
            .description("Product category to filter by")
    );
    parameters.add(
        parameterWithName("status")
            .description("Product status")
    );
    return parameters;
}
```

Document the operation:

```java
document("products-search",
    queryParameters(productSearchParameters())
)
```

An order listing endpoint can reuse the same pagination while adding customerId and its own status:

```java
static List<ParameterDescriptor> orderSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonParameterDescriptors.paginationParameters());
    parameters.add(
        parameterWithName("customerId")
            .description("Customer ID")
    );
    parameters.add(
        parameterWithName("status")
            .description("Order status")
    );
    return parameters;
}
```

The name status is the same, but the descriptions differ because one refers to products and the other to orders. You should not use a generic description for parameters solely because they share the same name.

## 5. Factories for path parameters

Path parameters typically identify a resource. Several nested endpoints may share userId:

```text
GET /api/users/{userId}/orders
GET /api/users/{userId}/addresses
GET /api/users/{userId}/settings
```

You can create a factory:

```java
static ParameterDescriptor userIdParameter() {
    return parameterWithName("userId")
        .description("User identifier");
}
```

Use in an operation:

```java
pathParameters(
    userIdParameter()
)
```

An endpoint with an additional specific path variable:

```java
pathParameters(
    userIdParameter(),
    parameterWithName("orderId")
        .description("Order ID")
)
```

With MockMvc, use RestDocumentationRequestBuilders to preserve the URI template so REST Docs can recognize path variables. If only the expanded path is stored without retaining the template, the descriptor may fail to identify the parameter name.

## 6. Factories for form parameters

Form parameters reside in the request body, typically form-urlencoded. For instance, several legacy search endpoints might use a locale field:

```http
POST /api/reports/search HTTP/1.1
Content-Type: application/x-www-form-urlencoded

locale=vi&format=csv
```

Factory:

```java
static List<ParameterDescriptor> reportFormatParameters() {
    return List.of(
        parameterWithName("locale")
            .description("Report language"),
        parameterWithName("format")
            .description("Export file format")
    );
}
```

Use with formParameters(...):

```java
document("report-search-form",
    formParameters(reportFormatParameters())
)
```

Do not reuse the same factory for both query and form just because parameter names match. The parameter locations differ and the generated snippets also differ; separate factories by role or name methods clearly, such as commonQueryPaginationParameters() and reportFormParameters().

## 7. Optional, ignored, and relaxed mode

A parameter might not appear in every request. For example, sort is only sent when the user selects sorting:

```java
static List<ParameterDescriptor> productSearchParameters() {
    return List.of(
        parameterWithName("page")
            .description("Page number"),
        parameterWithName("size")
            .description("Page size"),
        parameterWithName("sort")
            .description("Sort field")
            .optional()
    );
}
```

Common states:

| Usage | Meaning |
| --- | --- |
| Default descriptor | Parameter is expected in the request and documented |
| optional() | Parameter may be absent |
| ignored() | Parameter is omitted from the snippet and not verified like a normal descriptor |
| relaxedQueryParameters(...) | Allows query parameters outside the descriptor list |
| relaxedPathParameters(...) | Allows path parameters outside the descriptor list |
| relaxedFormParameters(...) | Allows form parameters outside the descriptor list |

Strict mode helps detect requests containing undocumented parameters or missing required descriptors. This is useful when an operation represents the full contract.

Relaxed mode is useful when documentation focuses on only a subset of parameters or a test is not responsible for documenting the entire request. However, do not use relaxed for every operation because new parameters can enter the API without tests prompting documentation updates.

### Avoiding shared descriptor state

The optional() and ignored() methods configure the descriptor. If you hold a static ParameterDescriptor and mutate its state in a test, other operations may reuse the modified instance. Therefore:

- Prefer factory methods that create fresh descriptors for each operation.
- Only use constants when the descriptor has the exact same configuration everywhere.
- Do not call optional() or ignored() on a shared instance if operations have different requirements.
- Split required and optional factories if contract semantics differ.

## 8. MockMvc example reusing query and path descriptors

Suppose there is an API for listing orders by user:

```java
@GetMapping("/users/{userId}/orders")
List<OrderResponse> findOrders(
        @PathVariable long userId,
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
```

Factory:

```java
public final class OrderParameterDescriptors {
    private OrderParameterDescriptors() {}

    public static ParameterDescriptor userId() {
        return parameterWithName("userId")
            .description("User identifier");
    }

    public static List<ParameterDescriptor> orderSearch() {
        return List.of(
            parameterWithName("status")
                .description("Order status")
                .optional(),
            parameterWithName("page")
                .description("Page number, zero-based"),
            parameterWithName("size")
                .description("Number of items per page")
        );
    }
}
```

Test:

```java
@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void findOrders() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/users/{userId}/orders", 42)
                    .queryParam("page", "0")
                    .queryParam("size", "20")
            )
            .andExpect(status().isOk())
            .andDo(document("user-orders-search",
                pathParameters(OrderParameterDescriptors.userId()),
                queryParameters(OrderParameterDescriptors.orderSearch())
            ));
    }
}
```

This operation uses the path factory for userId and the query factory for status/page/size. Because status is optional, the test can run without sending status. If the server adds an undocumented query parameter, strict query descriptors will raise an error.

## 9. Example reusing form descriptors

Suppose a report search endpoint accepts form-urlencoded:

```java
@PostMapping(
    path = "/reports/search",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
ReportResult search(
        @RequestParam String locale,
        @RequestParam String format) {
    // ...
}
```

Factory:

```java
static List<ParameterDescriptor> reportFormParameters() {
    return List.of(
        parameterWithName("locale").description("Report language"),
        parameterWithName("format").description("Export file format")
    );
}
```

Test:

```java
mockMvc.perform(
        post("/api/reports/search")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("locale", "vi")
            .param("format", "csv")
    )
    .andExpect(status().isOk())
    .andDo(document("report-search",
        formParameters(reportFormParameters())
    ));
```

Set Content-Type to form-urlencoded and use form data so the test matches the contract. If the endpoint accepts a JSON body, use requestFields(...) instead of formParameters(...).

## 10. Organizing helpers and naming conventions

Helpers can be placed in the test source set:

```text
src/
  test/
    java/
      com/example/api/docs/
        CommonParameterDescriptors.java
        ProductParameterDescriptors.java
        OrderParameterDescriptors.java
        ReportParameterDescriptors.java
```

Recommended conventions:

- Factory names clearly express parameter type and scope: paginationQueryParameters(), userPathParameters(), reportFormParameters().
- Share descriptions when name, location, and parameter meaning are all identical.
- Separate factories when parameters share a name but have different meanings per resource.
- Factories return new descriptors when optional/ignored differs.
- Combine lists using ArrayList or composition helpers to add specific parameters.
- Do not make test helpers depend on production services/controllers.

Do not create a single CommonParameters class holding every parameter across the entire system. Overly generic helpers obscure context, leading to inaccurate descriptions even when parameter names match.

## 11. Including parameter snippets in Asciidoctor

Example src/docs/asciidoc/orders.adoc file:

```asciidoc
= Orders API
:toc: left

== Find orders by user

=== Path parameters
include::{snippets}/user-orders-search/path-parameters.adoc[]

=== Query parameters
include::{snippets}/user-orders-search/query-parameters.adoc[]

== Search reports

=== Form parameters
include::{snippets}/report-search/form-parameters.adoc[]
```

The snippets attribute must point to the root generated snippets directory; the remaining path must match the operation ID. If you use a custom outputDir, update the attribute in the build configuration. You can also include http-request.adoc or cURL/HTTPie snippets so readers see the full request alongside the parameter tables.

## 12. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query snippet misses expected parameter | Factory did not add the parameter or test sends a different request. | Compare the actual query string with the descriptors. |
| Path descriptor cannot find placeholder | URI template was lost in the MockMvc request builder. | Use RestDocumentationRequestBuilders and a path template. |
| Form descriptor does not match request | Content-Type is not form-urlencoded or test sends JSON. | Set the appropriate Content-Type and use formParameters(...). |
| Test reports an undocumented parameter | Strict mode detected a parameter outside the descriptors. | Add a description or intentionally use relaxed mode. |
| Test reports a missing required parameter | Descriptor is not optional, yet request did not send it. | Fix the request or mark optional if the contract allows it. |
| An operation unexpectedly becomes optional | Sharing a configured ParameterDescriptor instance. | Create fresh descriptors in a factory per operation. |
| Incorrect meaning despite identical name | Sharing a factory across resources with different meanings. | Split factories by domain/resource. |
| Asciidoctor cannot find snippet | Wrong operation ID, outputDir, or snippets attribute. | Check the generated folder after tests and the include path. |

## 13. Practice exercise

Create three operations:

1. GET /api/products: query parameters category, status, page, size.
2. GET /api/users/{userId}/orders: path parameter userId along with query parameters status, page, size.
3. POST /api/reports/search: form parameters locale and format.

Steps:

1. Create CommonParameterDescriptors with a factory for pagination query parameters.
2. Create ProductParameterDescriptors and OrderParameterDescriptors, combining specific parameters with shared pagination.
3. Create dedicated factories for the userId path parameter and report form parameters.
4. Mark status optional according to the contract; write an additional strict operation to catch undocumented parameters.
5. Try sharing an instance and calling optional() in one place; replace it with a factory returning fresh instances for each operation.
6. Include the three parameter snippets in Asciidoctor alongside request snippets.
7. Run clean test and Asciidoctor; confirm documentation is generated from the current operations.

**Completion criteria:** distinguish ParameterDescriptor from FieldDescriptor; reuse parameters with identical meaning; compose endpoint-specific parameters; manage optional/ignored/relaxed intentionally; strict validation still detects contract changes.

## 14. References

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — ParameterDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/ParameterDescriptor.html)
