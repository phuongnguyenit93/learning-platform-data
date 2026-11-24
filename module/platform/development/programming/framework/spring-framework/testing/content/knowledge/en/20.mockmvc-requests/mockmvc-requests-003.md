# Headers, Cookies, and Session Attributes

When testing controllers with MockMvc, a request can carry several kinds of information beyond the URL and body: HTTP headers, cookies, and session state. These three types of data all enter the request, yet they have different transport mechanisms, lifecycles, and meanings. Tests must set up the exact kind of data the controller actually reads, then verify the outcome on the proper side—request or response.

## Distinguishing Headers, Cookies, and Sessions

| Component | Where it lives | What it is used for | How to supply in MockMvc |
| --- | --- | --- | --- |
| Request header | HTTP request metadata | Content negotiation, language, request id, client info, or tokens | `.header(...)`, `.headers(...)`, `.accept(...)`, `.contentType(...)` |
| Cookie | Name/value pairs sent by the client in the request; the server can return cookies via `Set-Cookie` | User preferences, tracking identifiers, or session id | `.cookie(new Cookie(...))`; verify the response with `cookie()` or the `Set-Cookie` header |
| Session attribute | Server-side data attached to `HttpSession` | State that must persist across multiple requests in the same session | `.session(...)`, `.sessionAttr(...)`, `.sessionAttrs(...)` |

A session is usually identified on the client by a session cookie such as `JSESSIONID`, whereas attributes like `userId` or `cartId` are stored server-side in `HttpSession`. Therefore, sending an arbitrary cookie does not automatically create a session containing the corresponding attributes. In MockMvc, the direct way to test session state is to pass a `MockHttpSession` object into the request.

## Sending Request Headers

`MockHttpServletRequestBuilder` provides `.header(name, values...)` to add one or more values for a header. You can call this method multiple times with the same header name to build a multi-valued header. HTTP header names are case-insensitive.

```java
mockMvc.perform(get("/api/reports")
        .header("X-Tenant-Id", "tenant-a")
        .header("X-Request-Id", "req-123")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
```

Dedicated methods help the request state its intent clearly:

- `.accept(MediaType.APPLICATION_JSON)` sets the `Accept` header, describing the response type the client can accept.
- `.contentType(MediaType.APPLICATION_JSON)` sets `Content-Type`, describing the data type of the request body.
- `.headers(HttpHeaders)` adds a prepared collection of headers to the request.
- `.header(name, value...)` works well when only a few inline headers are needed.

Example using `HttpHeaders` when multiple tests share the same metadata set:

```java
HttpHeaders headers = new HttpHeaders();
headers.set("X-Tenant-Id", "tenant-a");
headers.setAccept(List.of(MediaType.APPLICATION_JSON));

mockMvc.perform(get("/api/reports").headers(headers))
    .andExpect(status().isOk());
```

Do not confuse headers with query parameters or form fields. `.param("page", "2")` sends a parameter; `.header("X-Page", "2")` sends HTTP metadata. Controllers read them using different mechanisms such as `@RequestParam` and `@RequestHeader`.

### Controller Reading Headers

A controller can declare a required header with `@RequestHeader`:

```java
@GetMapping("/api/reports")
ResponseEntity<List<Report>> reports(
        @RequestHeader("X-Tenant-Id") String tenantId) {

    List<Report> reports = reportService.findByTenant(tenantId);
    return ResponseEntity.ok()
            .header("X-Resolved-Tenant", tenantId)
            .body(reports);
}
```

The test both sends the header and checks the response produced by the controller:

```java
mockMvc.perform(get("/api/reports")
        .header("X-Tenant-Id", "tenant-a"))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Resolved-Tenant", "tenant-a"));
```

`header()` in `MockMvcResultMatchers` checks **response headers**. It does not verify the request header sent by the test. If you need to inspect the exact request after MockMvc constructs it, you can read the request from `MvcResult`:

```java
mockMvc.perform(get("/api/reports")
        .header("X-Tenant-Id", "tenant-a"))
    .andDo(result -> assertThat(
            result.getRequest().getHeader("X-Tenant-Id"))
            .isEqualTo("tenant-a"));
```

In typical controller tests, prefer verifying header-dependent behavior or the response produced by the controller. Only inspect the request directly when verifying request-builder setup or a low-level request-processing component.

## Verifying Response Headers

`MockMvcResultMatchers.header()` provides matchers to verify returned headers:

```java
mockMvc.perform(get("/api/reports/42"))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(header().string("Cache-Control", "no-store"))
    .andExpect(header().doesNotExist("X-Debug-Info"));
```

Commonly used checks:

| Matcher | Meaning |
| --- | --- |
| `exists(name)` | The response contains a header with that name |
| `doesNotExist(name)` | The response does not contain that header |
| `string(name, expected)` | The header value equals the expected string |
| `string(name, matcher)` | The header value satisfies a Hamcrest matcher |
| `stringValues(name, values...)` | The list of header values equals the expected values |
| `longValue(name, value)` | The header value can be parsed as a long and equals the expected value |
| `dateValue(name, value)` | The header value is an HTTP date corresponding to the expected timestamp |

For multi-valued headers, use `stringValues` to state the expected list clearly:

```java
mockMvc.perform(get("/api/reports"))
    .andExpect(header().stringValues(
            "X-Report-Tag", "finance", "monthly"));
```

Assert only headers that are part of the endpoint contract or meaningful to the behavior under test. Headers generated by the environment or container can vary across configurations; depending on them often makes tests brittle.

## Sending Request Cookies

To send a cookie in a request, create a `jakarta.servlet.http.Cookie` and pass it via `.cookie(...)`:

```java
Cookie localeCookie = new Cookie("locale", "vi");

mockMvc.perform(get("/preferences")
        .cookie(localeCookie))
    .andExpect(status().isOk());
```

Multiple cookies can be sent at once:

```java
mockMvc.perform(get("/preferences")
        .cookie(
                new Cookie("locale", "vi"),
                new Cookie("theme", "dark")))
    .andExpect(status().isOk());
```

In a request, the browser sends the cookie's name and value. Attributes such as `Path`, `Domain`, `Secure`, and `HttpOnly` are directives in the `Set-Cookie` response; they are not sent back as attributes of each request cookie. Thus, when testing a controller that reads cookies, the test mainly needs the right name and value.

### Controller Reading Cookies

`@CookieValue` binds a cookie into a controller parameter:

```java
@GetMapping("/preferences")
PreferenceView preferences(
        @CookieValue(value = "locale", defaultValue = "vi") String locale) {

    return new PreferenceView(locale);
}
```

The test can confirm that the cookie value affects the response:

```java
mockMvc.perform(get("/preferences")
        .cookie(new Cookie("locale", "en")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("en"));
```

If the cookie is required, also test the missing-cookie case according to the endpoint contract. If `defaultValue` or `required = false` is set, test the corresponding default behavior. Do not test only the valid-cookie case because bugs often surface in missing or malformed branches.

## Creating and Verifying Response Cookies

A controller can add a cookie to the response via `HttpServletResponse.addCookie(...)`:

```java
@PostMapping("/preferences/theme")
void saveTheme(
        @RequestParam String theme,
        HttpServletResponse response) {

    Cookie cookie = new Cookie("theme", theme);
    cookie.setPath("/");
    cookie.setHttpOnly(true);
    cookie.setSecure(true);
    cookie.setMaxAge(60 * 60);

    response.addCookie(cookie);
}
```

Use `MockMvcResultMatchers.cookie()` to check returned cookies:

```java
mockMvc.perform(post("/preferences/theme")
        .param("theme", "dark"))
    .andExpect(status().isOk())
    .andExpect(cookie().exists("theme"))
    .andExpect(cookie().value("theme", "dark"))
    .andExpect(cookie().path("theme", "/"))
    .andExpect(cookie().httpOnly("theme", true))
    .andExpect(cookie().secure("theme", true))
    .andExpect(cookie().maxAge("theme", 3600));
```

Cookie attributes commonly needing verification:

- **Value:** the value the client will send back on matching requests.
- **Path:** restricts the URL paths to which the client sends the cookie.
- **Domain:** restricts the host or domain receiving the cookie.
- **Max-Age:** lifetime in seconds; a negative value typically denotes a session cookie, while `0` instructs deletion of the cookie.
- **Secure:** the client sends the cookie only over secure HTTPS connections.
- **HttpOnly:** prevents client-side JavaScript from reading the cookie via standard cookie APIs.

When deleting a cookie, the response typically sends back a cookie with the same name and matching `Path`/`Domain` scope with `Max-Age=0`. Tests should confirm cookie expiration according to the application's contract; merely checking that the cookie is absent from the response is not enough to prove the client will delete the old cookie.

If the application creates `Set-Cookie` using `ResponseCookie` or writes the `Set-Cookie` header directly, check the corresponding response header. The `cookie()` matcher works with cookies received by the mock response through the cookie API; a manually written `Set-Cookie` header does not necessarily appear in the mock cookie list. When a response contains multiple cookies, inspect each `Set-Cookie` value instead of assuming there is only one header.

`MockMvc` does not run a browser. Thus, matchers verify that the server created the cookie with the desired attributes; they do not simulate whether a browser accepts the cookie, sends it over HTTPS, or enforces browser security policies.

## Setting Session Attributes for a Request

Session attributes are data stored in `HttpSession`. There are two convenient ways to supply such data to MockMvc.

### Using `.sessionAttr(...)` or `.sessionAttrs(...)`

When a test only needs a few session values, the builder can be used directly:

```java
mockMvc.perform(get("/account")
        .sessionAttr("userId", 42L)
        .sessionAttr("displayName", "An"))
    .andExpect(status().isOk());
```

If you already have a map:

```java
Map<String, Object> attributes = Map.of(
        "userId", 42L,
        "displayName", "An");

mockMvc.perform(get("/account")
        .sessionAttrs(attributes))
    .andExpect(status().isOk());
```

These methods keep tests concise when only initial input state is needed. MockMvc creates or reuses a session for the request to hold the supplied attributes.

### Using `MockHttpSession`

When explicit control over the session is needed or the same session must be reused across multiple requests, create a `MockHttpSession`:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", 42L);
session.setAttribute("cartId", "cart-123");

mockMvc.perform(get("/cart").session(session))
    .andExpect(status().isOk());
```

`MockHttpSession` is helpful when a test needs to read, add, modify, or remove attributes before and after a request. You can inspect the request's session attributes using the `request()` matcher:

```java
mockMvc.perform(get("/cart").session(session))
    .andExpect(request().sessionAttribute("userId", 42L))
    .andExpect(request().sessionAttribute("cartId", "cart-123"))
    .andExpect(request().sessionAttributeDoesNotExist("admin"));
```

These matchers verify the session state attached to the processed request. They differ from `header()` and `cookie()`, which inspect HTTP response data.

## Testing Session Persistence Across Multiple Requests

An important scenario is when the first request creates or updates a session and a subsequent request reads that state back. Pass the same `MockHttpSession` instance across requests in the test to simulate the same user session.

For example, a login endpoint stores `userId` in the session and a profile endpoint reads that attribute back:

```java
MvcResult loginResult = mockMvc.perform(post("/login")
        .param("username", "an")
        .param("password", "secret"))
    .andExpect(status().isOk())
    .andReturn();

MockHttpSession session = (MockHttpSession)
        loginResult.getRequest().getSession(false);

assertThat(session).isNotNull();
assertThat(session.getAttribute("userId")).isEqualTo(42L);

mockMvc.perform(get("/account").session(session))
    .andExpect(status().isOk())
    .andExpect(request().sessionAttribute("userId", 42L));
```

Here, the test obtains the session after the login request and passes that same object into the account request. This confirms server-side state is preserved across two calls within the same test.

If the controller creates a session on the first request, `getSession(false)` retrieves the existing session without creating a new one. If the result is `null`, that request did not create a session or no session was attached to the request; re-check the endpoint's expected behavior.

MockMvc does not fully simulate a browser storing and sending `JSESSIONID` over the network. Passing the same `MockHttpSession` is the explicit way to test session-based logic in MVC tests. If the goal is to verify that a real container issues a session cookie, handles cookies over HTTP, and maintains sessions across connections, an integration test running with a real servlet container is required.

## Controller Accessing Session Attributes

Spring MVC allows reading an existing session attribute using `@SessionAttribute`:

```java
@GetMapping("/account")
AccountView account(@SessionAttribute("userId") Long userId) {
    return accountService.findView(userId);
}
```

The test sets the attribute with `.sessionAttr(...)` and checks the response:

```java
mockMvc.perform(get("/account")
        .sessionAttr("userId", 42L))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.userId").value(42L));
```

`@SessionAttribute` is used to access an attribute that already exists in the session. It is not the same as `@SessionAttributes` at the controller level. `@SessionAttributes` specifies model attributes that Spring MVC stores in the session during a controller workflow; when the workflow completes, the controller can call `SessionStatus.setComplete()` to stop storing those attributes. When testing such a controller, verify both that attributes are stored and that state is cleared at the right time.

If the endpoint allows the session attribute to be absent, declare it optional such as `@SessionAttribute(value = "userId", required = false)` or handle the missing case by design. Tests should include both a request with the attribute and a request without it to verify actual behavior.

## Distinguishing Session Attributes, Request Attributes, and Flash Attributes

These three kinds of attributes have different lifecycles:

| Kind | Lifecycle | How to set in MockMvc |
| --- | --- | --- |
| Request attribute | Current single request | `.requestAttr(name, value)` |
| Session attribute | Multiple requests within the same session | `.sessionAttr(name, value)` or `.session(session)` |
| Flash attribute | Typically used to pass data across a redirect to the next request | `.flashAttr(name, value)` |

Do not use `.requestAttr(...)` to simulate login or shopping-cart state that needs to persist across requests. Likewise, flash attributes suit temporary post-redirect data, not long-lived user state. Picking the wrong attribute kind can let a test pass without accurately reflecting the application's data lifecycle.

## Combining Headers, Cookies, and Session in the Same Request

An endpoint may simultaneously read a tenant from a header, a language from a cookie, and a user from the session. MockMvc lets you configure all three on the same request builder:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", 42L);

mockMvc.perform(get("/api/dashboard")
        .header("X-Tenant-Id", "tenant-a")
        .cookie(new Cookie("locale", "vi"))
        .session(session)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tenantId").value("tenant-a"))
    .andExpect(jsonPath("$.locale").value("vi"))
    .andExpect(jsonPath("$.userId").value(42L));
```

When a test fails, identify which data layer caused the failure: header not bound, cookie missing or wrong value, session lacking the attribute, or business logic mishandling the data. Setting up each data kind explicitly speeds up root-cause analysis and avoids substituting cookies for sessions or request attributes for session attributes.

## Common Testing Mistakes

- **Using `header()` to check a request header:** this matcher checks the response. Use `MvcResult.getRequest()` if you genuinely need to inspect the sent request.
- **Passing cookies via an arbitrary header string:** `.cookie(new Cookie(...))` expresses cookie structure accurately and avoids hand-crafting malformed `Cookie` headers.
- **Assuming `HttpOnly` or `Secure` attributes are present on request cookies:** these are attributes of the response `Set-Cookie`; verify them on the response.
- **Using an arbitrary cookie as a substitute for a session:** cookies are client-sent data. Session attributes live in the server-side session object.
- **Creating a new session for every request in the same scenario:** later requests will not see attributes from the earlier session. Reuse the same `MockHttpSession`.
- **Confusing request attributes with session attributes:** request attributes exist only for a single request, whereas session attributes persist across the session.
- **Assuming MockMvc tests browser behavior:** MockMvc verifies requests/responses at the Spring MVC layer and does not execute browser cookie-storage policies.
- **Asserting environment-generated headers without a clear contract:** results can differ between the mock environment and a real servlet container.

## Test Construction Workflow

1. Identify whether the controller reads data via `@RequestHeader`, `@CookieValue`, `@SessionAttribute`, or directly from `HttpServletRequest`/`HttpSession`.
2. Supply the exact input data with `.header(...)`, `.cookie(...)`, `.sessionAttr(...)`, or `.session(...)`.
3. Perform the request and assert the status and response body.
4. Assert response headers with `header()` and response cookies with `cookie()` or the `Set-Cookie` header according to how the application creates cookies.
5. Assert session attributes with `request().sessionAttribute(...)`; when simulating multiple requests, pass back the same `MockHttpSession`.
6. Add cases for missing headers, cookies, or session attributes according to the endpoint contract.
7. If you need to verify real browser or servlet container behavior, move that portion into an appropriate integration test rather than inferring it from a mock response.

Setting up headers, cookies, and session attributes properly enables MockMvc to test how Spring MVC receives HTTP metadata, reads client data, and maintains server-side state. When assertions are likewise placed on the correct request or response side and match the data lifecycle, tests reflect the endpoint contract much more accurately.
