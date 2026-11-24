# Response Status Codes, Headers, and Cookies

In Spring MVC testing, asserting the response body alone is not enough. An endpoint must also return the right HTTP status code, headers, and cookies so that the client understands the processing outcome, navigates to the next request, persists state, or enforces security policies. `MockMvc` provides result matchers to verify these components directly on the response produced by `DispatcherServlet`.

For example, two endpoints can both return JSON containing order information while carrying different HTTP semantics: creating a new order should return `201 Created` and a `Location` header; querying an existing order successfully typically returns `200 OK`; a successful deletion with no content can return `204 No Content`. Checking only the JSON may cause a test to miss a broken HTTP contract.

## 1. Structure of an HTTP Response

An HTTP response consists of three main parts:

```text
HTTP/1.1 201 Created
Content-Type: application/json
Location: /orders/42
X-Request-Id: req-abc123
Set-Cookie: session=...; Path=/; HttpOnly; Secure

{"id":42,"status":"CREATED"}
```

- **Status code** indicates the protocol-level processing outcome, such as `200`, `201`, `204`, `400`, `401`, `403`, `404`, or `500`.
- **Headers** provide metadata about the response, content format, caching, redirection, versioning, rate limits, or tracing information.
- **Cookies** are sent via the `Set-Cookie` header, allowing the server to instruct the client to store a value and send it back on matching requests.
- **Body** holds the returned payload, such as JSON, XML, HTML, or may be empty.

Each part has its own meaning. A status code does not replace the body; a `Location` header does not create a resource on its own; a cookie in the response does not prove that a browser actually stored it. Tests should verify the exact contract that the application is responsible for producing.

## 2. Verifying Status Codes

Spring MVC allows controllers to specify the status using `ResponseEntity`, `@ResponseStatus`, `ResponseStatusException`, or an exception handler. `MockMvc` verifies the status via the `status()` matcher.

### Using `ResponseEntity` to Express Outcomes

Example controller for creating orders:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderView> create(@RequestBody CreateOrder request) {
        OrderView created = orderService.create(request);
        URI location = URI.create("/orders/" + created.id());

        return ResponseEntity.created(location)
                .body(created);
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> find(@PathVariable long id) {
        return ResponseEntity.ok(orderService.find(id));
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

The factory methods `created`, `ok`, and `noContent` make the response semantics explicit. A test can verify each status:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": "P-100", "quantity": 2}
                        """))
        .andExpect(status().isCreated());

mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk());

mockMvc.perform(delete("/orders/42"))
        .andExpect(status().isNoContent());
```

This snippet illustrates three different status contracts. In real tests, configure the data or mock service appropriately so the request executes the intended business branch.

### Commonly Used Status Matchers

| Matcher | Status | Common Meaning |
|---|---:|---|
| `status().isOk()` | 200 | Request succeeded and usually includes a response body. |
| `status().isCreated()` | 201 | A new resource was created. |
| `status().isAccepted()` | 202 | Request was accepted for later processing. |
| `status().isNoContent()` | 204 | Processing succeeded with no response body. |
| `status().isBadRequest()` | 400 | Request is invalid. |
| `status().isUnauthorized()` | 401 | Missing or invalid authentication credentials. |
| `status().isForbidden()` | 403 | Request was authenticated or identified, but access is denied. |
| `status().isNotFound()` | 404 | Resource or matching route was not found. |
| `status().isConflict()` | 409 | Conflict with the current state of the resource. |
| `status().isInternalServerError()` | 500 | Server-side error not handled with a more specific response. |

For status codes without a dedicated matcher, use `status().is(418)` or the corresponding code. This is useful when the application defines a custom status or wants to check an exact HTTP code.

### Testing Errors and Exception Mapping

An exception can be mapped to a status using `@ResponseStatus`:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class OrderNotFoundException extends RuntimeException {

    OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}
```

Or use `@RestControllerAdvice` to control the error response:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("ORDER_NOT_FOUND", exception.getMessage()));
    }
}

record ApiError(String code, String message) {
}
```

The test should assert both the status and the error structure:

```java
mockMvc.perform(get("/orders/999"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
        .andExpect(jsonPath("$.message").value("Order 999 was not found"));
```

This ensures the exception handler translates errors into the expected HTTP contract and that clients receive a stable error code. Avoid asserting only `status().is4xxClientError()` when the API specifically requires `404`; an overly broad matcher can hide cases where the application accidentally returns `400` or `403`.

### Status 204 and Empty Response Body

`204 No Content` indicates a response with no content. When an endpoint uses this status, assert both the status and an empty body:

```java
mockMvc.perform(delete("/orders/42"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Do not expect JSON `{}` or a message string on a `204` response. If the client needs a confirmation payload, consider returning `200 OK` with an appropriate body.

## 3. Verifying Response Headers

Headers can directly affect how clients process a response. Spring provides the `header()` matcher to assert that a header exists, is absent, or has an expected value.

### The `Location` Header on Resource Creation

By HTTP convention, a `201 Created` response typically points to the URI of the newly created resource via the `Location` header:

```java
mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": "P-100", "quantity": 2}
                        """))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andExpect(header().string(HttpHeaders.LOCATION, "/orders/42"));
```

If the API returns an absolute URI, verify the exact scheme, host, port, and path specified by the application contract. A MockMvc test does not by itself prove that a proxy or forwarded-header configuration in deployment will produce the right host or scheme.

### Content Format and Caching Headers

Commonly checked headers include:

| Header | Purpose | What to Verify |
|---|---|---|
| `Content-Type` | Response content media type | Correct media type, e.g. `application/json`. |
| `Cache-Control` | Caching policy | Directives such as `no-store`, `private`, `max-age`. |
| `ETag` | Representation validator | Tag value is generated and changes with the representation. |
| `Last-Modified` | Time the representation changed | Valid date-time value when the API uses this validator. |
| `Location` | Resource URI or redirect target | Correct path according to the contract. |
| `WWW-Authenticate` | HTTP authentication challenge | Correct scheme and challenge parameters when returning `401`. |
| `Vary` | Request headers affecting the response/cache key | Required values, such as `Accept` or `Origin`. |
| `X-Request-Id` | Request identifier for tracing | Header is generated or propagated according to policy. |

Example verifying content type and caching policy:

```java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL,
                containsString("no-store")));
```

`contentTypeCompatibleWith` is appropriate when the response may include parameters such as `charset=UTF-8`. If the contract requires an exact media type including parameters, use `content().contentType(...)` or assert the header value as required.

### Checking Header Existence, Absence, and Value

Common usage patterns:

```java
mockMvc.perform(get("/orders/42"))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(header().string("X-Request-Id", "req-abc123"))
        .andExpect(header().doesNotExist("X-Debug-Token"));
```

HTTP header names are case-insensitive. Using constants from `HttpHeaders` for standard headers reduces typos; for custom application headers, centralize header names as constants if they are used in multiple places.

If a header is generated dynamically, such as a request ID or timestamp, avoid hard-coding unstable values. You can check that the header exists, matches a format, or relates to known data. Only assert an exact value when the test controls the source that generates it.

### Redirects and the `Location` Header

A redirect typically returns a `3xx` status along with `Location`. Both can be verified:

```java
mockMvc.perform(post("/login"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(HttpHeaders.LOCATION, "/dashboard"));
```

If you want to verify the exact redirect URL, `redirectedUrl("/dashboard")` is also a dedicated matcher. Distinguish redirects from `201 Created` responses: both can include `Location`, but their status codes and protocol semantics are different.

## 4. Verifying Response Cookies

The server sends cookies to the client via the `Set-Cookie` header. Cookies can hold a session identifier, refresh token, UI preferences, or appropriate state data. Cookie attributes govern the scope in which they are sent back and the level of data protection.

### Cookies Added via the Servlet API

If a controller calls `HttpServletResponse.addCookie`, MockMvc stores the cookies in `MockHttpServletResponse`. They can be verified using the `cookie()` matcher:

```java
@RestController
class PreferenceController {

    @PostMapping("/preferences/theme")
    ResponseEntity<Void> saveTheme(
            @RequestParam String theme,
            HttpServletResponse response) {

        Cookie cookie = new Cookie("theme", theme);
        cookie.setPath("/");
        cookie.setMaxAge(60 * 60);
        cookie.setHttpOnly(true);
        cookie.setSecure(true);
        response.addCookie(cookie);

        return ResponseEntity.noContent().build();
    }
}
```

The test verifies the cookie value and attributes:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;

mockMvc.perform(post("/preferences/theme")
                .param("theme", "dark"))
        .andExpect(status().isNoContent())
        .andExpect(cookie().exists("theme"))
        .andExpect(cookie().value("theme", "dark"))
        .andExpect(cookie().path("theme", "/"))
        .andExpect(cookie().maxAge("theme", 3600))
        .andExpect(cookie().httpOnly("theme", true))
        .andExpect(cookie().secure("theme", true));
```

These matchers verify cookies created in the mock response. They do not prove that a browser stored the cookie or will send it back on subsequent requests.

### Cookies Created with `ResponseCookie` and the `Set-Cookie` Header

Spring provides `ResponseCookie` for creating cookies in an immutable style, which is convenient when the `SameSite` attribute is needed:

```java
ResponseCookie refreshCookie = ResponseCookie.from("refresh_token", token)
        .httpOnly(true)
        .secure(true)
        .sameSite("Strict")
        .path("/auth")
        .maxAge(Duration.ofDays(7))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, refreshCookie.toString())
        .body(new TokenResponse(accessToken));
```

`ResponseCookie` is formatted into a `Set-Cookie` header string. With this approach, assert the header rather than assuming the cookie will appear in the Servlet cookie list of the response:

```java
mockMvc.perform(post("/auth/refresh"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                HttpHeaders.SET_COOKIE,
                allOf(
                        containsString("refresh_token="),
                        containsString("HttpOnly"),
                        containsString("Secure"),
                        containsString("SameSite=Strict"),
                        containsString("Path=/auth"))));
```

This test demonstrates verifying directives in the header. If a response includes multiple cookies, each cookie is typically sent in its own `Set-Cookie` header; do not join them into a single comma-separated string because an `Expires` attribute may contain a comma. When verifying multiple cookies, assert individual header values or use cookie matchers for cookies added via the Servlet API.

### Security Meaning of Cookie Attributes

| Attribute | Effect | How to Verify |
|---|---|---|
| `HttpOnly` | Browser JavaScript cannot read the cookie via `document.cookie`. | Assert the `HttpOnly` directive or the `httpOnly` matcher. |
| `Secure` | Browser sends the cookie only over secure connections per cookie rules. | Assert the `Secure` directive or the `secure` matcher. |
| `SameSite` | Controls cookie transmission in cross-site contexts. | Check the `SameSite=Lax`, `Strict`, or `None` directive. |
| `Path` | Restricts the path scope for which the cookie is sent. | Verify the `Path` value. |
| `Domain` | Specifies which hosts/domains are allowed to receive the cookie. | Verify the `Domain` value if the application sets it. |
| `Max-Age` / `Expires` | Defines the cookie lifetime. | Verify the lifetime or expiration time according to policy. |

For cookies containing a session ID, refresh token, or sensitive data, check `HttpOnly`, `Secure`, `SameSite`, `Path`, and lifetime according to the application's security requirements. Do not check only for the cookie's existence.

`SameSite=None` requires the cookie to have `Secure` under modern browser rules. A header test can verify that the server emits both directives; verifying that a browser accepts the cookie still requires browser-level testing if the product requires it.

### Incoming Cookies vs. Outgoing Cookies

Two testing directions must be distinguished:

- `.cookie(new Cookie("theme", "dark"))` on the request builder sends a cookie **to the controller**.
- `cookie().value("theme", "dark")` on the result matcher verifies a cookie **returned by the controller**.

Example testing that the server reads an incoming cookie:

```java
mockMvc.perform(get("/preferences/theme")
                .cookie(new Cookie("theme", "dark")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.theme").value("dark"));
```

To simulate multiple requests with session state, you can keep `MockHttpSession` or cookies from a response and attach them to the next request. This tests application logic in a mock environment; it does not fully replicate a real browser's cookie jar, `SameSite` enforcement, domain matching, or security behavior.

## 5. Verifying Headers and Cookies in Common HTTP Flows

### Conditional GET and ETag

An ETag is a validator representing a version of a resource. A client can send `If-None-Match`; if the representation has not changed, the server can return `304 Not Modified` so the client uses its cached copy.

A test can verify both the initial response and the conditional request:

```java
MvcResult first = mockMvc.perform(get("/catalog/items/42"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ETAG))
        .andReturn();

String etag = first.getResponse().getHeader(HttpHeaders.ETAG);

mockMvc.perform(get("/catalog/items/42")
                .header(HttpHeaders.IF_NONE_MATCH, etag))
        .andExpect(status().isNotModified());
```

This example assumes the endpoint implements conditional requests and returns the same ETag when the representation has not changed. If the controller or service computes the ETag itself, ensure the test uses deterministic data for repeatable results.

### Authentication Error Responses

When an API uses HTTP Basic or another authentication scheme, a `401 Unauthorized` response may require a `WWW-Authenticate` header so the client knows how to authenticate:

```java
mockMvc.perform(get("/api/private"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().exists(HttpHeaders.WWW_AUTHENTICATE));
```

For APIs using Bearer tokens, you can verify the `Bearer` scheme and any challenge parameters published by the application. Do not enforce this header on `403 Forbidden` responses; `401` and `403` represent two different situations.

### CORS and the `Vary` Header

If an API supports CORS, tests can send `Origin` and verify the returned CORS headers, such as `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, or `Access-Control-Allow-Credentials` as configured.

```java
mockMvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, "https://client.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS));
```

For responses that vary by `Origin`, the `Vary: Origin` header may be required so intermediate caches do not mistakenly reuse responses across origins. Testing CORS via MockMvc verifies that Spring filters/configuration emit the expected headers; it does not replace browser testing for CORS enforcement.

## 6. Combining Multiple Matchers in One Test

A solid response test typically asserts status, key headers, cookies, and body together. The following example illustrates an order-creation contract:

```java
mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Correlation-Id", "corr-001")
                .content("""
                        {"productId": "P-100", "quantity": 2}
                        """))
        .andExpect(status().isCreated())
        .andExpect(header().string(HttpHeaders.LOCATION, "/orders/42"))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("CREATED"));
```

If the endpoint also issues cookies, you can chain cookie matchers or `Set-Cookie` header matchers depending on how the cookie is created. Focus on the properties that belong to the API contract. Asserting every default framework header can make tests brittle across framework upgrades when business behavior has not changed.

You can separate request execution from assertions using `MvcResult` when you need to extract a value from a response and reuse it in a subsequent request, as in the ETag example. For independent assertions, chaining matchers in a single `andExpect` chain keeps expected outcomes readable in one place.

## 7. Common Mistakes When Verifying Responses

### Checking Only the Body and Skipping the Status

An endpoint can return valid JSON with the wrong status, such as returning `200` instead of `201` on resource creation, or returning a body on a successful delete when `204` is expected. Assert the status that matches the semantics of the operation.

### Using Overly Broad Matchers

`is2xxSuccessful()` only proves the status is in the 2xx range. If the API requires `201 Created`, that matcher will still accept `200 OK` or `204 No Content`. Use a specific matcher whenever the contract specifies an exact code.

### Checking `Location` Without Checking the Status

The `Location` header can appear in redirect responses or other scenarios. When testing resource creation, verify both `201 Created` and the resource URI. When testing a redirect, verify a `3xx` status and the navigation target.

### Assuming `cookie()` Matchers Check Every `Set-Cookie` Header

Cookies added via `HttpServletResponse.addCookie` are stored in the mock response's cookie list and work with `cookie()` matchers. Cookies formatted manually as a `ResponseCookie` string and set via a header must be verified via `header().string(...)` or an equivalent header check. These two ways of writing response cookies should not be conflated.

### Comparing Full Dynamic Headers Literally

Headers such as `Date`, `Expires`, request IDs, or tokens can change with time and across test runs. Check existence, format, or stable properties instead of comparing an uncontrolled value verbatim.

### Thinking MockMvc Tests Browser Cookie Storage

MockMvc only shows that the simulated response contains the expected cookies/headers. It does not run a browser cookie jar, enforce `SameSite` policies, or prove that cookies are sent back over a real HTTPS connection. When browser behavior must be verified, add appropriate browser or HTTP integration tests.

### Forgetting Headers Added by Filters or Security

Some headers are added by filters, Spring Security, CORS configuration, or reverse proxies. If a MockMvc test does not include those filters in the chain, assertions may fail or miss the behavior being verified. Check whether the test configuration actually registers the relevant filters.

## 8. Organizing Tests Around the API Contract

For each endpoint, you can outline the response contract in a brief table before writing assertions:

| Scenario | Status | Headers/Cookies to Check | Body |
|---|---:|---|---|
| Resource created successfully | 201 | `Location`, `Content-Type`, request ID if present | Representation of the new resource. |
| Resource read successfully | 200 | `Content-Type`, cache/ETag if present | Current representation. |
| Deleted successfully | 204 | Headers only if required by contract | Empty. |
| Invalid input | 400 or specified status | `Content-Type` | Error code and validation details. |
| Unauthenticated | 401 | `WWW-Authenticate` if required by scheme | Error details per contract. |
| Unauthorized | 403 | Security policy headers if present | Appropriate error details. |
| Not found | 404 | `Content-Type` | Stable error code. |

Not every endpoint needs every header or cookie. Include in the table only the properties that genuinely matter to clients. Then use `MockMvc` to verify both success and error branches, especially edge cases such as newly created resources, empty responses, expired cookies, or requests with validators.

## 9. Assertion Checklist

- [ ] Specific status code matches the operation's semantics.
- [ ] `201 Created` response includes `Location` when the contract requires the new resource URI.
- [ ] `204 No Content` response contains no body.
- [ ] `Content-Type` is compatible with the format declared by the API.
- [ ] Cache, ETag, CORS, authentication, or correlation headers are verified when part of the contract.
- [ ] Dynamic headers are checked using stable conditions instead of random values.
- [ ] Cookies have the right name, value, path, domain, and lifetime.
- [ ] Sensitive cookies include protective attributes such as `HttpOnly`, `Secure`, and `SameSite` per policy.
- [ ] Tests distinguish cookies added via the Servlet API from cookies set directly in the `Set-Cookie` header.
- [ ] Tests do not assume MockMvc has verified a real browser, proxy, or HTTP connector.

Verifying status codes, headers, and cookies helps Spring MVC tests cover more of the HTTP contract published by a controller. `MockMvc` lets you precisely verify responses generated by Spring within the test context; for behavior that depends on a browser, proxy, or real servlet container, add tests at that appropriate layer.
