# Constraints on Request Fields and Path/Query Parameters

## 1. Objectives

An HTTP request can carry data in a JSON body, a path variable, or a query string. Each location has different binding mechanics, yet all can be subject to constraints such as required presence, length, format, numeric bounds, or business rules.

Example: `GET /api/orders/101/items?page=0&size=20&sku=BOOK-42`. The value `101` is the path variable `orderId`; `page`, `size`, and `sku` are query parameters.

This lesson belongs to the Constraints chapter of SPRING_REST_DOCS. The module produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; and compiles Asciidoctor/Markdown integrated with build and CI.

After this lesson, you will be able to distinguish validation across body DTOs, query models, and method parameters; apply Bean Validation; document constraints with REST Docs descriptors; and test both valid requests and validation errors.

> Data location determines how Spring binds and validates it; REST Docs descriptors determine how that data is presented. Both must be connected through HTTP tests and clear descriptions.

## 2. Three Data Locations and Descriptors

| Location | Example | Validation | REST Docs |
| --- | --- | --- | --- |
| JSON body | `{"quantity":2}` | DTO property | `requestFields(...)` |
| Path | `/api/orders/{orderId}` | Controller parameter/domain lookup | `pathParameters(...)` |
| Query | `?page=0&size=20` | `@RequestParam` or query DTO | `queryParameters(...)` |

`requestFields` documents the body; `pathParameters` documents URI variables; `queryParameters` documents the query string. Descriptors do not validate value ranges themselves. `parameterWithName("page").description("Zero-based page index")` only describes the parameter; it does not reject negative `page` values.

## 3. Constraints on JSON Request Fields

### 3.1. DTO and Bean Validation

~~~java
import jakarta.validation.constraints.*;

public record CreateOrderItemRequest(
    @NotBlank @Size(min = 3, max = 30) String sku,
    @NotNull @Min(1) @Max(100) Integer quantity,
    @Size(max = 250) String note
) {}
~~~

| Field | Constraint | Meaning |
| --- | --- | --- |
| `sku` | NotBlank, Size 3–30 | Product SKU must have non-blank content and valid length. |
| `quantity` | NotNull, Min 1, Max 100 | Required quantity, from 1 to 100. |
| `note` | Size max 250 | Note may be omitted, maximum 250 characters. |

`NotNull` differs from `NotBlank`. `NotNull` forbids null; `NotBlank` is for strings and requires a non-whitespace character. Absent, explicit null, and empty string are distinct states.

Controller enabling validation for the DTO:

~~~java
@PostMapping("/api/orders/{orderId}/items")
public ResponseEntity<OrderItemResponse> addItem(
        @PathVariable long orderId,
        @Valid @RequestBody CreateOrderItemRequest request) {
    OrderItemResponse created = orderService.addItem(orderId, request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

This example requires a Bean Validation provider and appropriate Spring MVC configuration.

### 3.2. Testing and Describing Request Fields

~~~java
mockMvc.perform(post("/api/orders/{orderId}/items", 101)
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"sku":"BOOK-42","quantity":2,"note":"Deliver during business hours"}
            """))
    .andExpect(status().isCreated())
    .andDo(document("order-items-create",
        requestFields(
            fieldWithPath("sku")
                .description("Product SKU; required, 3–30 characters long"),
            fieldWithPath("quantity")
                .description("Quantity; required, from 1 to 100"),
            fieldWithPath("note")
                .description("Optional note; maximum 250 characters")
                .optional()
        )
    ));
~~~

This is a method added to a configured test class. Constraints are written in the description so the default template displays them. `requestFields` checks that descriptors match the payload according to the active mode; `optional()` is a descriptor rule, does not replace Bean Validation, and does not prove the 250-character limit is enforced.

### 3.3. ConstraintDescriptions for DTO Properties

~~~java
ConstraintDescriptions constraints =
    new ConstraintDescriptions(CreateOrderItemRequest.class);

String rules = String.join("; ",
    constraints.descriptionsForProperty("quantity"));

FieldDescriptor quantityField =
    fieldWithPath("quantity").description("Quantity. " + rules);
~~~

`ConstraintDescriptions` resolves property constraints via a Bean Validation Validator. You must pass the results into a descriptor; REST Docs does not automatically insert them into the default table. If the JSON field name differs from the Java property, separate mapping is required. Class-level/cross-field and domain rules require separate documentation/tests.

## 4. Constraints on Path Variables

Example controller:

~~~java
@RestController
@RequestMapping("/api/orders")
@Validated
class OrderItemController {
    @GetMapping("/{orderId}/items")
    public List<OrderItemResponse> listItems(
            @PathVariable @Min(1) @Max(999999999) long orderId) {
        return orderService.listItems(orderId);
    }
}
~~~

This example assumes method validation is enabled according to the Spring version. In many earlier MVC setups, `@Validated` on a bean works with method validation infrastructure; Spring Framework 6.1+ includes dedicated MVC method validation integration. Verify your actual configuration rather than assuming an annotation works merely because it is declared.

A value that fails to parse as `long` can cause a binding/conversion error; a parseable value outside the range can cause a validation error. These are two different failure modes.

Test and descriptor:

~~~java
mockMvc.perform(get("/api/orders/{orderId}/items", 101))
    .andExpect(status().isOk())
    .andDo(document("order-items-list",
        pathParameters(
            parameterWithName("orderId")
                .description("Order ID; positive integer")
        )
    ));
~~~

Use a request builder that preserves the URI template so REST Docs recognizes `orderId`. `pathParameters` generates `path-parameters.adoc` but does not automatically read `@Min`/`@Max` on the controller method argument. Constraints are written explicitly in the description.

| Path | Meaning | Must Test |
| --- | --- | --- |
| `/api/orders/101/items` | Valid ID | Success status/body. |
| `/api/orders/0/items` | Violates `Min(1)` | Validation error. |
| `/api/orders/1000000000/items` | Exceeds `Max` | Validation error. |
| `/api/orders/abc/items` | Cannot convert | Binding/conversion error. |
| `/api/orders/999/items` | In range, resource missing | Domain 404. |

`Min(1)` does not prove the order exists or that the caller has permission to access it.

By default, `ConstraintDescriptions` resolves property constraints on a Java type; do not pass a controller class expecting it to read annotations from method parameters automatically. For path parameters, write descriptions manually, use a helper that reads method annotations, or use custom metadata/templates. Reflection only reads annotations; it does not prove validation is enabled.

## 5. Constraints on Query Parameters

### 5.1. @RequestParam

~~~java
@GetMapping("/api/orders")
public Page<OrderResponse> searchOrders(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
        @RequestParam(required = false)
        @Pattern(regexp = "createdAt,(asc|desc)|total,(asc|desc)") String sort) {
    return orderService.search(page, size, sort);
}
~~~

Example contract: `page` defaults to 0 and is non-negative; `size` defaults to 20, from 1 to 100; `sort` is optional and accepts only values matching the pattern. Method validation must be enabled according to the appropriate Spring version/configuration.

If `size=abc` with target `int`, the error can occur during binding before Bean Validation. `size=101` parses successfully but falls outside the range. Test both separately.

### 5.2. queryParameters Snippet

~~~java
mockMvc.perform(get("/api/orders")
        .queryParam("page", "0")
        .queryParam("size", "20")
        .queryParam("sort", "createdAt,desc"))
    .andExpect(status().isOk())
    .andDo(document("orders-search",
        queryParameters(
            parameterWithName("page")
                .description("Non-negative page index; defaults to 0"),
            parameterWithName("size")
                .description("Items per page; from 1 to 100; defaults to 20"),
            parameterWithName("sort")
                .description("Optional; createdAt or total combined with asc/desc")
                .optional()
        )
    ));
~~~

`queryParameters` generates `query-parameters.adoc`. Descriptors do not automatically pull `Min`, `Max`, `Pattern`, `defaultValue`, or `required` from method arguments. Place those limits into descriptions/helpers/templates.

### 5.3. Query DTO with @ModelAttribute

~~~java
public class OrderSearchQuery {
    @Min(0)
    private Integer page = 0;

    @Min(1)
    @Max(100)
    private Integer size = 20;

    @Pattern(regexp = "createdAt,(asc|desc)|total,(asc|desc)")
    private String sort;

    // getters/setters
}

@GetMapping("/api/orders")
public Page<OrderResponse> search(@Valid @ModelAttribute OrderSearchQuery query) {
    return orderService.search(query);
}
~~~

A query DTO turns parameters into Java properties, fitting `ConstraintDescriptions`:

~~~java
ConstraintDescriptions descriptions =
    new ConstraintDescriptions(OrderSearchQuery.class);
List<String> sizeRules = descriptions.descriptionsForProperty("size");
~~~

Validating model attributes depends on Spring binding/configuration. HTTP tests must prove invalid values are rejected.

`queryParameters` accepts descriptors by HTTP parameter name and does not automatically fetch DTO metadata. You can append descriptions to `parameterWithName`'s description. A helper should accept the HTTP name, Java property name, and business description separately to support differently named mappings.

## 6. Validation Errors and Binding Errors

Example error body per an application's custom contract:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid parameters",
  "violations": [
    {"field":"size","message":"Items per page must be between 1 and 100."}
  ]
}
~~~

This is not a default Spring response; an application may use Problem Details or a custom schema.

~~~java
@Test
void rejectPageSizeAboveMaximum() throws Exception {
    mockMvc.perform(get("/api/orders").queryParam("size", "101"))
        .andExpect(status().isBadRequest())
        .andDo(document("orders-search-invalid-size"));
}
~~~

~~~java
@Test
void rejectNonPositiveOrderId() throws Exception {
    mockMvc.perform(get("/api/orders/{orderId}/items", 0))
        .andExpect(status().isBadRequest())
        .andDo(document("order-items-invalid-id"));
}
~~~

Both tests assume method/model validation is enabled and an exception handler maps violations to `400`. Documentation must follow the actual response.

| Error Type | Example | Meaning |
| --- | --- | --- |
| Binding/conversion | `size=abc` | Cannot convert to the Java type. |
| Constraint validation | `size=101` when max is 100 | Value parses but is out of domain range. |
| Domain validation | Order does not exist | Business rule. |
| Authorization | Caller lacks permission | Access policy. |

## 7. Strictness of Parameter Descriptors

`pathParameters` and `queryParameters` verify actual parameters against descriptors. In strict mode, a parameter present in the request but undocumented can fail snippet generation; a required descriptor missing from the request can also fail.

- `optional()` allows a parameter descriptor to be absent in the documented operation.
- `relaxedPathParameters(...)` and `relaxedQueryParameters(...)` allow extra undocumented parameters.
- Declared descriptors that are not optional must still be satisfied.

`optional()` is a snippet generation rule and does not replace `required=false`, default values, or validation logic in the controller. For body fields, `requestFields` has its own strictness rules. Do not use relaxed descriptors just to turn tests green without reviewing the contract change.

## 8. Presenting Constraints

| Approach | Advantages | Notes |
| --- | --- | --- |
| Write in description | Easy to use with default templates | Must be updated when rules change. |
| `ConstraintDescriptions` + helper | Reuses DTO property metadata | Does not automatically read method parameters. |
| Descriptor attributes + custom template | Provides a consistent constraints column | Requires maintaining templates per version. |

Example: `parameterWithName("orderId").description("Order ID; positive integer; must refer to an existing order")`. This description combines the numeric range and domain lookup; `@Min(1)` only checks the number.

## 9. WebTestClient and REST Assured

### 9.1. WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders?page=0&size=20")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-search-webtestclient",
        queryParameters(
            parameterWithName("page").description("Non-negative page index; defaults to 0"),
            parameterWithName("size").description("Items per page from 1 to 100")
        )
    ));
~~~

This example attaches descriptors; testing `size=101` requires a separate test. Use the `spring-restdocs-webtestclient` module and proper REST Docs configuration.

### 9.2. REST Assured

~~~java
given(spec)
    .filter(document("orders-search-restassured",
        queryParameters(
            parameterWithName("page").description("Non-negative page index; defaults to 0"),
            parameterWithName("size").description("Items per page from 1 to 100")
        )
    ))
    .queryParam("page", 0)
    .queryParam("size", 20)
.when()
    .get("/api/orders")
.then()
    .statusCode(200);
~~~

`spec` must configure the server and REST Docs. The filter can record the operation before final assertions; CI should publish only when the entire test suite passes.

## 10. Asciidoctor, Markdown, and CI

~~~asciidoc
= Orders API

== List Items

=== Path parameters
include::{snippets}/order-items-list/path-parameters.adoc[]

=== HTTP request
include::{snippets}/order-items-list/http-request.adoc[]

=== Query parameters
include::{snippets}/orders-search/query-parameters.adoc[]

=== Request fields
include::{snippets}/order-items-create/request-fields.adoc[]
~~~

Identifiers are examples and must match actual tests. The `snippets` attribute must point to the output directory. Plain Markdown renderers do not natively understand Asciidoctor includes; a template or conversion step is needed.

~~~mermaid
flowchart TD
    A["DTO / path / query constraints"] --> B["HTTP tests: valid + invalid + boundary"]
    B --> C{"Assertions pass?"}
    C -->|No| D["Fail CI"]
    C -->|Yes| E["REST Docs descriptors"]
    E --> F["Generate snippets"]
    F --> G["Render docs"]
    G --> H{"Includes pass?"}
    H -->|No| D
    H -->|Yes| I["Review and publish"]
~~~

When changing min/max, regex, defaults, or required behavior, update tests and descriptions. `ConstraintDescriptions` is useful for DTO properties; method parameters and domain rules require separate helpers/reviews. The render task must run after the snippet-generating test task and must not include stale artifacts.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `@Min` on PathVariable does not run | Method validation not enabled | Check Spring version/config and run HTTP tests. |
| Wrong-type query returns a different error than violation | Binding occurs before validation | Test unparseable inputs separately. |
| `ConstraintDescriptions` does not find `@Min` on controller parameter | Resolver focuses on property constraints | Document method parameters separately. |
| Query snippet lacks min/max | Descriptor only has generic description | Add limits via helper/template. |
| Path snippet missing variable | URI template not preserved or descriptor missing | Use an appropriate request builder. |
| `optional()` used yet server still reports missing | Confusing REST Docs `optional` with controller `required`/default | Synchronize both layers. |
| `size=101` is still accepted | Validation not enabled | Check provider, method validation, and boundary tests. |
| ID within range returns 404 | Resource does not exist | Separate domain lookup from range constraint. |
| Relaxed descriptor hides new parameter | Contract not reviewed | Confirm whether parameter should be public. |
| Docs outdated after changing limits | Manual descriptions not updated | Review snippet diffs in CI. |

## 12. Practice Exercise

Assumed endpoint:

~~~text
GET /api/customers/{customerId}/orders?page=0&size=20&status=PAID
~~~

Contract:

- `customerId`: positive integer; customer must exist and caller must have permission.
- `page`: non-negative integer, defaults to 0.
- `size`: from 1 to 100, defaults to 20.
- `status`: optional, accepts only `PENDING`, `PAID`, `CANCELLED`.

Steps:

1. Choose a validation strategy for path/query parameters.
2. Create a query DTO if appropriate and configure Bean Validation.
3. Write HTTP tests for `customerId=0`, `page=-1`, `size=101`, `size=abc`, and invalid `status`.
4. Distinguish validation, binding, not found, and authorization errors.
5. Use `pathParameters`/`queryParameters` to describe limits, defaults, and optionality.
6. Use `ConstraintDescriptions` for query DTO properties; do not assume it reads controller method parameters.
7. Include snippets in Asciidoctor, review diffs, and ensure CI does not publish when tests, descriptors, or rendering fail.

**Completion criteria:** accurately identify constraint locations, verify with HTTP tests, document path/query/body accurately, and distinguish validation from binding/domain errors.

## References

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
