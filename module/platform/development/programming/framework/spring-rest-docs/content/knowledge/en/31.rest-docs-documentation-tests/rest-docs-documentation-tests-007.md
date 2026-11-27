# Testing Success, Failure, and Boundary Endpoint Cases

## Learning Objectives

In the **SPRING_REST_DOCS** module, documentation tests must prove that an endpoint behaves properly across important scenarios while generating snippets describing the verified request and response. A test suite containing only happy paths is rarely enough: clients also need to know how the API responds when requests are invalid, resources do not exist, users lack permission, or data sits right at allowed boundaries.

This lesson guides designing three scenario groups:

1. **Success (happy path):** valid request and the endpoint performs the expected action.
2. **Failure (negative path):** request or context fails conditions and the endpoint returns an error per contract.
3. **Boundary values:** data right at the allowed limits and just outside those limits.

After this lesson, you will be able to:

- Design success, failure, and boundary scenario sets for an endpoint.
- Choose status codes and assertions fitting each scenario.
- Test validation and business rules at boundaries.
- Separate operation IDs for differing responses so snippets do not overwrite one another.
- Use REST Docs to document both success responses and error responses.
- Keep tests independent with deterministic data sufficiently representative of the API contract.

## 1. Why Are All Three Scenario Groups Needed?

Suppose a product creation endpoint takes `name` and `price`. A test that only sends valid data proves a product can be created, yet leaves questions unanswered:

- Is a blank `name` rejected?
- Is `price` equal to 0 valid?
- Is a negative `price` rejected?
- Is a `name` at the exact length limit accepted?
- Does a `name` one character past the limit return a properly structured error?
- Is a request missing a required field handled properly?

Good API documentation tells integrators both how to make successful calls and how to handle errors. The test suite must also guard boundaries so validation changes do not accidentally widen or narrow the contract.

| Group | Goal | Example |
| --- | --- | --- |
| Success | Verify standard flow | Valid POST returns 201 and new resource |
| Failure | Verify rejection conditions | Invalid POST returns 400 |
| Boundary | Verify allowed limits | Name at exact max length accepted; max+1 rejected |

Not every value needs its own documentation test. Select cases meaningful to the public contract, then supplement with more detailed unit/validation tests if data combinations grow too large.

## 2. Defining the Contract Before Writing Tests

Before writing scenarios, tabulate the expected behavior:

| Condition | HTTP outcome | What to verify |
| --- | --- | --- |
| Valid request | 201 Created | Location, response body, resource created |
| Missing name | 400 Bad Request | Error code and violation field |
| Whitespace-only name | 400 Bad Request | Validation error for name |
| Negative price | 400 Bad Request | Validation or business rule error |
| Price at exact min/max | 201 Created | Boundary value accepted |
| Price out of range | 400 Bad Request | Error clearly identifies field/condition |
| Resource absent on GET | 404 Not Found | Error response |
| Insufficient permissions | 403 Forbidden or specified status | Security error response |

Statuses in the table are examples. An API may use different statuses or error schemas; tests must follow the real contract rather than forcing the project into an unagreed convention.

## 3. Preparing the Sample DTO and Endpoint

Example DTO:

```java
public record CreateProductRequest(
        @NotBlank
        @Size(min = 2, max = 80)
        String name,
        @NotNull
        @DecimalMin("0.01")
        @DecimalMax("1000000.00")
        BigDecimal price
) {
}
```

Controller:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    @PostMapping
    ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductResponse created = this.productService.create(request);
        URI location = URI.create("/api/products/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}
```

This example assumes the application has a Bean Validation provider, an exception handler standardizing errors, and a service creating resources. The `name`/`price` limits are illustrative policies; real projects must choose them per business requirements.

## 4. Success Scenario: Happy Path

### 4.1. Sending a Valid Request

Request:

```json
{
  "name": "Mechanical Keyboard",
  "price": 129.90
}
```

MockMvc test:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": "Mechanical Keyboard",
                  "price": 129.90
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(header().string(
            HttpHeaders.LOCATION,
            endsWith("/api/products/501")))
    .andExpect(jsonPath("$.id").value(501))
    .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
    .andExpect(jsonPath("$.price").value(129.90))
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price.")
        ),
        responseFields(
            fieldWithPath("id").description("Server-generated product ID."),
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price.")
        )));
```

This test checks status 201, JSON `Content-Type`, `Location`, response body, and request/response descriptors.

### 4.2. Verifying Business Side Effects

If the test runs against a real test repository/database, you can verify the resource was persisted:

```java
assertThat(productRepository.findById(501L))
        .isPresent()
        .get()
        .extracting(Product::getName)
        .isEqualTo("Mechanical Keyboard");
```

If using a mock service, verify the service was invoked with parsed data:

```java
verify(productService).create(argThat(request ->
        request.name().equals("Mechanical Keyboard")
                && request.price().compareTo(new BigDecimal("129.90")) == 0
));
```

Choose a verification approach appropriate for the test's scope. Do not pretend to verify persistence if the repository has been replaced by a mock.

## 5. Failure Scenario: Validation Errors

### 5.1. Missing Required Field

Request missing `name`:

```json
{
  "price": 129.90
}
```

Test:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "price": 129.90
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
    .andExpect(jsonPath("$.violations").isArray())
    .andExpect(jsonPath("$.violations[*].field")
            .value(hasItem("name")))
    .andDo(document("products-create-missing-name",
        responseFields(
            fieldWithPath("code").description("Error code."),
            fieldWithPath("message").description("Error message."),
            fieldWithPath("violations").description("List of validation errors."),
            fieldWithPath("violations[].field").description("Invalid field name."),
            fieldWithPath("violations[].message").description("Error description.")
        )));
```

Descriptors must match the actual error JSON. If the API uses `errors` instead of `violations` or a different structure, update paths to match the real response.

### 5.2. Whitespace-Only String

Request:

```json
{
  "name": "   ",
  "price": 129.90
}
```

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(invalidNameJson))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
    .andExpect(jsonPath("$.violations[*].field")
            .value(hasItem("name")))
    .andDo(document("products-create-blank-name",
        responseFields(errorDescriptors)));
```

This test differs from missing `name`. It verifies `@NotBlank` rejects strings containing only whitespace. If you want to document each error case thoroughly, use separate operation IDs.

### 5.3. Invalid Data Must Not Mutate State

Besides the 400 response, you can verify that the service did not create a resource:

```java
verify(productService, never()).create(any());
```

Or check that the repository has no matching record in an integration test. This is an important behavioral assertion: an invalid request must not create partial data.

## 6. Failure Scenario: Business and Resource Errors

Validation does not cover every failure. A request can be well-formed yet violate business rules.

For example, product code already exists:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(validRequestJson))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("PRODUCT_ALREADY_EXISTS"))
    .andDo(document("products-create-conflict",
        responseFields(
            fieldWithPath("code").description("Business error code."),
            fieldWithPath("message").description("Error message.")
        )));
```

Scenarios commonly needing documentation:

| Scenario | Example outcome | What to assert |
| --- | --- | --- |
| Resource does not exist | 404 | Error code and message |
| Conflicting data | 409 | Domain error code |
| Unauthenticated | 401 | Error body and WWW-Authenticate if present |
| Insufficient permissions | 403 | Error body and action not performed |
| Rate limit exceeded | 429 | Error body and Retry-After if in contract |
| Dependency temporarily unavailable | 503 | Error response and retry semantics if applicable |

There is no need to write documentation tests for every internal exception. Focus on public error branches that clients can handle.

## 7. Boundary Value Scenarios

### 7.1. Boundary Value Analysis

For a min/max limit, important values are typically:

- min - 1: just below the lower limit.
- min: exact lower limit.
- min + 1: just above the lower limit.
- max - 1: just below the upper limit.
- max: exact upper limit.
- max + 1: just above the upper limit.

Not every data type represents min - 1 or max + 1 the same way. For strings, use length; for numbers, use the smallest step matching precision; for dates, use the day or time unit specified by the API.

### 7.2. String Length Boundaries

For `name` with length from 2 to 80:

| Length | Expected result |
| --- | --- |
| 1 | Invalid |
| 2 | Valid |
| 3 | Valid |
| 79 | Valid |
| 80 | Valid |
| 81 | Invalid |

Example test helper:

```java
private String repeat(char value, int length) {
    return String.valueOf(value).repeat(length);
}
```

Checking max:

```java
String nameAtMax = repeat('A', 80);
String nameOverMax = repeat('A', 81);

this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(productJson(nameAtMax, "10.00")))
    .andExpect(status().isCreated())
    .andDo(document("products-create-name-max"));

this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(productJson(nameOverMax, "10.00")))
    .andExpect(status().isBadRequest())
    .andDo(document("products-create-name-over-max",
        responseFields(errorDescriptors)));
```

If the same test class uses a real database, clean up data or use separate fixtures so subsequent runs do not fail on duplicate constraints.

### 7.3. Monetary Boundaries

For `price` between 0.01 and 1,000,000.00:

| Value | Expected result |
| --- | --- |
| 0.00 | Invalid |
| 0.01 | Valid |
| 0.02 | Valid |
| 999,999.99 | Valid |
| 1,000,000.00 | Valid |
| 1,000,000.01 | Invalid |

With `BigDecimal`, compare using `compareTo` when scale differences should be ignored:

```java
assertThat(actualPrice.compareTo(new BigDecimal("0.01"))).isZero();
```

Do not use `double` to represent money in assertions if the contract uses exact decimals. Also align on whether the API accepts JSON decimals, permitted scale, and rounding rules.

### 7.4. Collection Boundaries

If an API allows 1 to 50 elements:

| Element count | Result |
| --- | --- |
| 0 | Invalid |
| 1 | Valid |
| 49 | Valid |
| 50 | Valid |
| 51 | Invalid |

Besides collection size, check null elements, duplicates, and invalid elements if those cases belong to the contract.

## 8. Separating Operation IDs by Scenario

Each differing response needs its own operation ID so snippets do not overwrite each other:

| Scenario | Suggested operation ID |
| --- | --- |
| Created successfully | products-create |
| Missing name | products-create-missing-name |
| Blank name | products-create-blank-name |
| Name over max | products-create-name-over-max |
| Price under min | products-create-price-under-min |
| Price over max | products-create-price-over-max |
| Duplicate product code | products-create-conflict |

Example includes:

```asciidoc
== Product Created Successfully
include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]

== Request Missing Name
include::{snippets}/products-create-missing-name/http-response.adoc[]
include::{snippets}/products-create-missing-name/response-fields.adoc[]

== Name Exceeds Limit
include::{snippets}/products-create-name-over-max/http-response.adoc[]
include::{snippets}/products-create-name-over-max/response-fields.adoc[]
```

Do not use the same operation ID for success tests and validation error tests. `http-response.adoc` or `response-fields.adoc` files can be overwritten depending on test execution order.

## 9. Using Parameterized Tests and a Test Matrix

Parameterized tests work well for checking multiple boundary values:

```java
@ParameterizedTest
@ValueSource(ints = {1, 81})
void rejectsNameOutsideLengthRange(int length) throws Exception {
    String name = "A".repeat(length);

    this.mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content(productJson(name, "10.00")))
        .andExpect(status().isBadRequest());
}
```

The test above verifies multiple inputs without generating snippets for every single case. If you want to document responses, use a stable operation ID per scenario or a dedicated test representing the error group. Do not generate IDs from every runtime value if that creates hundreds of unnecessary directories.

A test matrix can track cases:

| Field | Value | Group | Expected |
| --- | --- | --- | --- |
| name | missing | Negative | 400 |
| name | blank | Negative | 400 |
| name | 1 char | Boundary below | 400 |
| name | 2 chars | Boundary min | 201 |
| name | 80 chars | Boundary max | 201 |
| name | 81 chars | Boundary above | 400 |
| price | 0.00 | Boundary below | 400 |
| price | 0.01 | Boundary min | 201 |
| price | 1,000,000.00 | Boundary max | 201 |
| price | 1,000,000.01 | Boundary above | 400 |

A test matrix helps spot coverage gaps, though you should avoid an oversized Cartesian product when fields are independent.

## 10. MockMvc, WebTestClient, and REST Assured

### 10.1. MockMvc

MockMvc places assertions before `document`:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(validRequestJson))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.name").value("Keyboard"))
    .andDo(document("products-create"));
```

### 10.2. WebTestClient

WebTestClient uses `exchange` and expectations:

```java
this.webTestClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .jsonPath("$.name").isEqualTo("Keyboard")
    .consumeWith(document("products-create"));
```

### 10.3. REST Assured

REST Assured places the `document` filter in the request chain and assertions in `then`:

```java
given(this.spec)
    .contentType(ContentType.JSON)
    .body(request)
    .filter(document("products-create"))
    .when()
    .post("/api/products")
    .then()
    .statusCode(201)
    .body("name", equalTo("Keyboard"));
```

The REST Docs adapter must be compatible with the project's REST Assured and Spring REST Docs versions. Regardless of which client is used, the principle stays the same: the test must fail if the status/body violates the contract.

## 11. Independent Tests and Deterministic Data

Documentation tests produce snippets used in documentation; unstable data causes unnecessary documentation churn.

Do:

- Prepare explicit fixtures for each scenario.
- Clean the database or reset mock state between tests.
- Avoid depending on execution order.
- Never use real timestamps, UUIDs, tokens, or sessions in snippets.
- Fix `Clock`/ID generators when exact values are needed.
- Use distinct operation IDs for differing responses.
- Document only representative boundary cases; keep exhaustive checks in validation/unit tests.

If a test uses a real repository, verify both before and after states to guarantee negative cases do not create data. If using mocks, verify the service was not called or was called along the expected branch.

## 12. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Happy path passes yet API is wrong | Only asserts status without checking body/headers | Assert key fields and headers |
| Invalid request still creates resource | Validation not enabled or service fails to enforce rule | Check `@Valid`, provider, and side effects |
| Max boundary behaves inconsistently | Built string/decimal with wrong unit or scale | Use explicit length and `BigDecimal` |
| Test fails on descriptor error | Error payload differs from declared paths | Compare against actual JSON and update descriptors |
| Error snippet overwritten | Multiple scenarios share the same operation ID | Separate operation IDs |
| Test depends on stale data | Database not reset or fixtures collide | Clean up state and use independent fixtures |
| Assertions depend on violation order | API does not guarantee error ordering | Look up violations by field/code instead of index |
| Test matrix explodes | Combining every value across every field | Select independent boundaries and pairwise combinations when appropriate |
| Docs only show success responses | No operations written for public errors | Add error documentation tests |
| Test passes yet snippet is unrepresentative | Fixture lacks realistic structure | Pick sample data containing nested/array fields |

## 13. Hands-On Exercise

1. Create a `POST /api/products` endpoint with bounded `name` and `price`.
2. Write a happy-path test asserting 201, `Location`, and response body; create operation `products-create`.
3. Write a test for missing `name` asserting 400 and error body; create a separate operation.
4. Write tests for whitespace-only `name` and negative `price`.
5. Test `name` at min, max, min-1, and max+1 lengths.
6. Test `price` at min, max, and just outside both limits.
7. Verify invalid requests neither create a resource nor invoke the service's create method.
8. Include success and error response snippets in separate AsciiDoc sections.
9. Run the tests multiple times and verify snippet output remains stable.

**Self-Assessment Questions**

1. Why is a happy path insufficient to protect an API contract?
2. How does a validation failure differ from a business conflict?
3. Which values around min/max does boundary value analysis select?
4. Why is it important to check side effects of invalid requests?
5. When should you assign a separate operation ID to a boundary case?
6. Do parameterized tests always need to generate snippets for every input?
7. How can you prevent tests from depending on the order of validation violations?
8. Why is documenting selected public error responses helpful to clients?

## Official References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): HTTP tests and snippet generation.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): integrating documentation tests and snippets.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): enabling validation in Spring.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): status, header, and body assertions.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP exchanges.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, groups, and validation metadata.

**Practical Takeaway:** Build documentation tests across three groups: success, failure, and boundary values. For each group, assert status, headers, body, and side effects per contract; use distinct operation IDs for differing responses; and use REST Docs to document verified requests/responses. This ensures documentation guides clients on both proper usage and how to handle invalid data or contexts.
