# Asserting Status, Headers, and Body Before Documenting

## Learning Objectives

In the **SPRING_REST_DOCS** module, a documentation test must prove that an endpoint fulfills its HTTP contract before generating snippets from that exchange. The three core groups of response assertions are **status code**, **headers**, and **body**. They answer three different questions: what status the server responded with, whether the response metadata is correct, and whether the returned content is correct.

Spring REST Docs records the HTTP request/response and validates the descriptors provided by the test. It does not decide on its own which status is right, which headers must be present, or which JSON values match business rules. Those must be checked with MockMvc, WebTestClient, or REST Assured assertions.

After this lesson, you will be able to:

- Choose the exact status matcher for each endpoint scenario.
- Verify the presence, value, and type of response headers.
- Verify the response body using JSONPath, content assertions, or object assertions.
- Distinguish between a response with no body, JSON null, and a missing field.
- Combine status/header/body assertions with documenting snippets.
- Write assertions for success, error, and no-content responses.
- Avoid overly broad matchers or dependencies on random data.

## 1. Three Assertion Layers in a Response

| Layer | Examples to verify | Common assertions |
| --- | --- | --- |
| Status | Creation returns 201; not found returns 404 | status matcher, statusCode |
| Header | Content-Type is JSON; Location points to the new resource | header matcher, expectHeader, header assertion |
| Body | ID is numeric; name is right; error code is right | JSONPath, body matcher, object comparison |

For example, a product creation endpoint has the contract:

- Returns HTTP 201 Created.
- Returns Content-Type compatible with application/json.
- Returns Location pointing to the newly created resource.
- Body contains `id`, `name`, and `status`.

The test should verify all four of these before considering the operation verified. Checking only status 201 can let a wrong response body or a missing Location slip through.

## 2. Status Assertions: Choosing the Right HTTP Status

### 2.1. Using Specific Status Matchers

With MockMvc:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andDo(document("products-create"));
```

Common matchers:

| Matcher | Status |
| --- | --- |
| isOk() | 200 |
| isCreated() | 201 |
| isAccepted() | 202 |
| isNoContent() | 204 |
| isBadRequest() | 400 |
| isUnauthorized() | 401 |
| isForbidden() | 403 |
| isNotFound() | 404 |
| isConflict() | 409 |
| isTooManyRequests() | 429 |
| isInternalServerError() | 500 |

With WebTestClient, use the corresponding matcher:

```java
.expectStatus().isCreated()
```

With REST Assured:

```java
.then()
.statusCode(201)
```

The list above only covers common scenarios. Use the status defined by the API contract; do not force every creation endpoint to return 201 if the system has a different contract.

### 2.2. Avoiding Overly Broad Status Assertions

The following assertions are weaker when an API has a specific status:

```java
// Only checks that it falls within the 2xx group
.andExpect(status().is2xxSuccessful())
```

```java
// Only checks that the status is in the success range
.then().statusCode(greaterThanOrEqualTo(200))
```

If an endpoint accidentally changes from 201 to 200, a broad assertion can still pass. When the status is part of the contract, prefer a specific matcher. Group matchers are only appropriate when the contract genuinely allows multiple statuses.

### 2.3. Verifying Status Codes for Error Branches

Documentation does not only need happy paths:

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andDo(document("products-not-found"));
```

With validation:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": " ",
                  "price": -1
                }
                """))
    .andExpect(status().isBadRequest())
    .andDo(document("products-create-invalid"));
```

Status assertions ensure the endpoint actually handles error branches according to the contract, while snippets capture the error response for documentation.

## 3. Header Assertions: Verifying Response Metadata

### 3.1. Content-Type

If an endpoint returns JSON, verify the media type:

```java
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
```

`contentTypeCompatibleWith` is suitable when accepting a compatible media type, including parameters such as charset. If the contract requires an exact value with no variants, you can use a stricter matcher:

```java
.andExpect(content().contentType(MediaType.APPLICATION_JSON))
```

WebTestClient:

```java
.expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
```

REST Assured:

```java
.then().contentType(ContentType.JSON)
```

Distinguish between `Content-Type` and `Accept`:

- `Accept` is a request header indicating the response media type the client wants.
- `Content-Type` is a response header indicating the representation media type the server actually sent.

Checking `Accept` in the request does not replace checking `Content-Type` on the response.

### 3.2. Location After Resource Creation

A resource creation endpoint often returns `Location`:

```java
.andExpect(status().isCreated())
.andExpect(header().exists(HttpHeaders.LOCATION))
```

Checking existence alone is not enough when the contract requires a specific URI. You can assert the value:

```java
.andExpect(header().string(
        HttpHeaders.LOCATION,
        endsWith("/api/products/501")
))
```

Or parse the URI and assert its components:

```java
MvcResult result = this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andReturn();

URI location = URI.create(
        result.getResponse().getHeader(HttpHeaders.LOCATION));

assertThat(location.getPath()).isEqualTo("/api/products/501");
```

If the ID is dynamically generated, use a fixture or check a structured pattern/path instead of hardcoding a random ID. `Location` is a URI referencing the resource; avoid accidentally asserting a local machine's host/port as part of the contract if they depend on the environment.

### 3.3. Cache-Control, ETag, and Retry-After

Some headers directly affect how clients use the API:

```java
.andExpect(header().string(
        HttpHeaders.CACHE_CONTROL,
        containsString("no-store")
))
```

```java
.andExpect(header().exists(HttpHeaders.ETAG))
```

```java
.andExpect(header().string(HttpHeaders.RETRY_AFTER, "30"))
```

Only assert headers that belong to the contract or policies the endpoint must guarantee. If headers are added by middleware/proxies depending on the environment, choose the test scope accordingly.

### 3.4. Set-Cookie

If login creates a session cookie:

```java
.andExpect(header().exists(HttpHeaders.SET_COOKIE))
.andExpect(header().string(
        HttpHeaders.SET_COOKIE,
        allOf(
            containsString("SESSION="),
            containsString("HttpOnly"),
            containsString("Secure"),
            containsString("SameSite=Lax")
        )
))
```

The example above illustrates checking key parts of `Set-Cookie`. In a real application, you can parse `Set-Cookie` using an appropriate cookie API to inspect the name, `Path`, `Max-Age`, and attributes rather than relying on the exact header string ordering.

Do not include real session values or refresh tokens in documentation. Tests must use dummy values.

## 4. Body Assertions with JSONPath

### 4.1. Verifying Fields and Values

Response:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90,
  "status": "ACTIVE"
}
```

MockMvc:

```java
.andExpect(jsonPath("$.id").isNumber())
.andExpect(jsonPath("$.name").value("Keyboard"))
.andExpect(jsonPath("$.price").value(129.90))
.andExpect(jsonPath("$.status").value("ACTIVE"))
```

JSONPath checks response content at the field level. Use just enough assertions to protect the important contract:

- Check types when clients depend on them.
- Check exact values when values are deterministic.
- Check field presence when fields are required.
- Check that lists contain matching elements when the endpoint must return results.

### 4.2. Checking Missing, Null, and Empty String Fields

The following three JSON cases are different:

```json
{}
```

```json
{"description": null}
```

```json
{"description": ""}
```

They represent an absent field, a field with a null value, and a field with an empty string, respectively. When the contract distinguishes these cases, assertions must distinguish them as well.

Example checking that a field is present and not null:

```java
.andExpect(jsonPath("$.description").exists())
.andExpect(jsonPath("$.description").value(notNullValue()))
```

Checking an empty string value:

```java
.andExpect(jsonPath("$.description").value(""))
```

If the API allows a field to be omitted, do not use `exists()` as if the field were always required.

### 4.3. Checking Arrays and Nested Objects

```json
{
  "items": [
    {"id": 10, "quantity": 2},
    {"id": 11, "quantity": 1}
  ]
}
```

```java
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items.length()").value(2))
.andExpect(jsonPath("$.items[0].id").value(10))
.andExpect(jsonPath("$.items[0].quantity").value(2))
```

If array ordering is not part of the contract, avoid asserting elements at fixed indices. Instead, check size, presence, or value sets in an order-independent way.

### 4.4. Checking Error Bodies

Error response:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Invalid request",
  "violations": [
    {
      "field": "name",
      "message": "Must not be blank"
    }
  ]
}
```

Assertions:

```java
.andExpect(status().isBadRequest())
.andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
.andExpect(jsonPath("$.violations").isArray())
.andExpect(jsonPath("$.violations[0].field").value("name"))
```

For error lists, avoid depending on order if the API does not guarantee violation ordering. You can check the count or locate elements by field/code.

## 5. Body Assertions via Content or Object Comparison

Not every response requires JSONPath.

### 5.1. Plain Text Responses

```java
this.mockMvc.perform(get("/health/message"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
    .andExpect(content().string("service-ready"))
    .andDo(document("health-message"));
```

### 5.2. Responses Without Content

For an endpoint returning 204:

```java
this.mockMvc.perform(delete("/api/products/{id}", 501))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""))
    .andDo(document("products-delete"));
```

Do not declare `responseFields` for a non-existent body. If a response contains the JSON literal `null`, that is still a body with content and differs from an empty response body.

### 5.3. Object Comparison

In some tests, you can deserialize the response into a DTO and compare:

```java
MvcResult result = this.mockMvc.perform(get("/api/products/{id}", 501))
    .andExpect(status().isOk())
    .andReturn();

ProductResponse actual = objectMapper.readValue(
        result.getResponse().getContentAsString(),
        ProductResponse.class);

assertThat(actual.name()).isEqualTo("Keyboard");
assertThat(actual.status()).isEqualTo(ProductStatus.ACTIVE);
```

This approach is useful when there are many object rules, but do not rely solely on DTO `equals` if `equals` ignores important fields. Be explicit about which fields and relationships belong to the HTTP contract.

## 6. Placing Assertions Before document in MockMvc

With MockMvc, the typical chain is:

1. `perform(...)` executes the request.
2. `andExpect(...)` verifies status, headers, and body.
3. `andDo(document(...))` records the exchange and generates snippets.

Complete example:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": "Keyboard",
                  "price": 129.90
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andExpect(jsonPath("$.id").isNumber())
    .andExpect(jsonPath("$.name").value("Keyboard"))
    .andExpect(jsonPath("$.status").value("ACTIVE"))
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price.")
        ),
        responseFields(
            fieldWithPath("id").description("Product ID."),
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price."),
            fieldWithPath("status").description("Status.")
        )));
```

If any assertion fails, the test fails. Placing `document` after `andExpect` makes the reading flow clear: verify the endpoint first, then record the exchange.

## 7. Placing Assertions and document in WebTestClient

WebTestClient has its own expectation pipeline:

```java
this.webTestClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
            "name", "Keyboard",
            "price", 129.90
    ))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().exists(HttpHeaders.LOCATION)
    .expectBody()
    .jsonPath("$.name").isEqualTo("Keyboard")
    .jsonPath("$.status").isEqualTo("ACTIVE")
    .consumeWith(document("products-create",
        responseFields(
            fieldWithPath("id").description("Product ID."),
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price."),
            fieldWithPath("status").description("Status.")
        )));
```

`expectStatus` and `expectHeader` verify response metadata; `expectBody` verifies the payload; `consumeWith` passes the received exchange to REST Docs to generate snippets.

If the body is not JSON, use `expectBody` with an appropriate type and matching assertions. Do not add JSONPath to endpoints returning `text/plain` or an empty body.

## 8. Assertions with REST Assured and REST Docs

REST Assured commonly uses `given/when/then`. The REST Docs filter records the request/response in the filter chain; `then()` assertions still must execute so the test only passes when the response contract is valid:

```java
given(this.spec)
    .contentType(ContentType.JSON)
    .body("""
            {
              "name": "Keyboard",
              "price": 129.90
            }
            """)
    .filter(document("products-create",
        requestFields(
            fieldWithPath("name").description("Product name."),
            fieldWithPath("price").description("Selling price.")
        )))
    .when()
    .post("/api/products")
    .then()
    .statusCode(201)
    .contentType(ContentType.JSON)
    .header("Location", notNullValue())
    .body("name", equalTo("Keyboard"))
    .body("status", equalTo("ACTIVE"));
```

Unlike MockMvc's `andExpect` followed by `andDo` chain, REST Assured attaches the `document` filter to the request specification before the response assertions in `then()` run. What must be ensured is that the test is only considered passing and snippets are only treated as verified output when all `then()` assertions pass. Check the REST Assured/REST Docs configuration for the exact adapter version in use.

## 9. Assertions and Descriptors: Two Complementary Verification Layers

| Scenario | Assertion | REST Docs descriptor |
| --- | --- | --- |
| Response must have status 201 | status().isCreated() | HTTP response snippet records actual status |
| Response must have Location | header().exists(...) or URI comparison | responseHeaders describes Location semantics |
| Field name must be Keyboard | jsonPath("$.name").value(...) | responseFields describes field name |
| Field status must be published | jsonPath("$.status").exists() | responseFields requires describing status |
| Error code must be correct | jsonPath("$.code").value(...) | responseFields describes error schema |

Assertions do not replace descriptors: a test might verify the body is correct while documentation still fails to explain the fields. Descriptors also do not replace assertions: documentation might list a `status` field without knowing whether `"ACTIVE"` or `"DELETED"` is right for business logic.

On the request side, also check that the request setup sends the right data, content type, and headers, then use request descriptors to validate what is documented.

## 10. Choosing Assertion Strictness

Assertions should be precise enough to protect the contract, without checking unstable details.

| Brittle assertion | Problem | More stable approach |
| --- | --- | --- |
| Comparing the entire JSON string | Property order, whitespace, and formatting change | JSONPath or JSON-aware comparison |
| Comparing Location including local host/port | Test environments have different host/port | Assert path or contract URI components |
| Comparing exact runtime timestamps | Value changes with clock | Use a fixed Clock or check format/range |
| Comparing hardcoded random UUIDs | Each run generates a new ID | Use a dummy ID generator or check format/uniqueness |
| Checking every proxy-generated header | Depends on infrastructure | Only assert headers guaranteed by the endpoint |
| Using any 2xx status | Fails to catch 200 instead of 201 | Assert exact status when specified by contract |

Do not weaken assertions just to reduce test failures. If a value is part of the contract, assert it; if it is only a runtime detail, fix the dependency or verify stable properties of the value.

## 11. Checklist for Response Assertions Before Documenting

- [ ] Status code matches the operation's contract.
- [ ] Content-Type matches the returned representation.
- [ ] Required headers such as Location, ETag, Cache-Control, or Retry-After are asserted when part of the contract.
- [ ] Set-Cookie is checked if the endpoint creates/updates cookies.
- [ ] Key body fields exist and have the right value/type.
- [ ] Nested objects and arrays are checked with meaningful rules.
- [ ] Error responses are checked for status, error code, and violation structure.
- [ ] 204 endpoints are verified to have an empty body.
- [ ] No dependency on random timestamps, UUIDs, ordering, or host/port.
- [ ] Snippets are treated as verified documentation only after behavior has been asserted.

## 12. Hands-On Exercise

1. Create a `POST /api/products` endpoint returning 201, `Location`, and a JSON response.
2. Write a MockMvc test asserting status 201, `Content-Type`, `Location`, and `name`/`status` fields.
3. Add `responseFields` to describe all payload fields.
4. Create a GET endpoint when a resource is not found; assert 404, error code, and message.
5. Create a DELETE endpoint returning 204; assert an empty body and do not declare `responseFields`.
6. Create a login test issuing `Set-Cookie`; assert the cookie name along with important security attributes.
7. Rewrite one test using WebTestClient or REST Assured, preserving all contract assertions.
8. Try changing a status or body value in the endpoint; confirm assertions fail before accepting new documentation.

**Self-Assessment Questions**

1. Why is a specific status matcher better than `is2xxSuccessful` when the contract requires 201?
2. How does response `Content-Type` differ from request `Accept`?
3. When is checking only that `Location` exists insufficient?
4. How does a missing JSON field differ from a null field and an empty string?
5. Why do JSONPath assertions not replace `responseFields`?
6. At what step after expectations does WebTestClient place `document`?
7. Where does the REST Assured `document` filter run relative to `then()` assertions?
8. How can you test timestamps or UUIDs without creating flaky tests?

## Official References

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): status, header, content, and JSONPath expectations.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): exchange, status, header, and body assertions.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): integrating REST Docs into HTTP tests.
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors and payload verification.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): request/response header descriptors.
- [REST Assured](https://rest-assured.io/): status, header, and body assertions with given/when/then.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status code semantics and HTTP components.

**Practical Takeaway:** Before documenting, prove the response is right across three layers: status, headers, and body. Use specific status matchers; check headers that genuinely belong to the contract; verify key body values with JSONPath or object assertions. Then use REST Docs descriptors to ensure the content is fully described. Together, these two verification layers ensure snippets are produced from a verified endpoint rather than merely recording an arbitrary HTTP exchange.
