# Context Path, Servlet Path, and Request Metadata

When using `MockMvc`, a request has more than just an HTTP method and URL. `DispatcherServlet` also receives Servlet API metadata such as context path, servlet path, path info, query parameters, headers, body, cookies, session, and request attributes. Setting these values accurately lets tests simulate how the application is deployed and how clients send requests.

The path components require the clearest understanding. `requestURI`, `contextPath`, `servletPath`, and `pathInfo` describe different portions of the same path. If the application runs under a context path or `DispatcherServlet` is mapped to a dedicated servlet path, tests must declare those components consistently with the request URI.

## 1. Components of a Servlet Path

The Servlet API provides several properties describing the request path:

- **`requestURI`** is the request path on the server, including the context path and the remaining path segments. The query string is not part of `requestURI`.
- **`contextPath`** is the prefix under which the web application is deployed. An application running at the root context usually has an empty context path; an application deployed under `/shop` has `/shop` as its context path.
- **`servletPath`** is the portion of the path matched by the servlet handling the request.
- **`pathInfo`** is the remaining path after `servletPath` for path-mapped servlets; it may be `null`.
- **Query string** contains the parameters following `?`, such as `?page=2&sort=name`.

For a request handled by a servlet mapped to `/api/*`, suppose the full path is `/shop/api/orders/42`. The values typically look like:

| Property | Value | Meaning |
|---|---|---|
| `requestURI` | `/shop/api/orders/42` | Request path on the server |
| `contextPath` | `/shop` | Application is deployed under `/shop` |
| `servletPath` | `/api` | Portion matching the `/api/*` servlet mapping |
| `pathInfo` | `/orders/42` | Remaining portion after the servlet path |
| Query string | `?expand=items` | Query information, separate from request URI |

The path components can be visualized according to this relationship:

```text
requestURI = contextPath + servletPath + pathInfo

/shop/api/orders/42
  |----| |--| |-------|
  context servlet pathInfo
  path   path
```

This is the common breakdown for path mappings. Exact values depend on the servlet mapping used by the application. With `DispatcherServlet` mapped to `/`, the application path usually resides in `servletPath` and `pathInfo` is typically `null`.

## 2. Setting contextPath, servletPath, and pathInfo in MockMvc

Request builders such as `get(...)`, `post(...)`, and `put(...)` accept the request path. When the application runs at the root context using the default servlet mapping, simply pass the regular path:

```java
mockMvc.perform(get("/orders/42"))
    .andExpect(status().isOk());
```

If the application is deployed under context path `/shop` and `DispatcherServlet` is mapped under `/api/*`, specify the path components explicitly:

```java
mockMvc.perform(get("/shop/api/orders/42")
        .contextPath("/shop")
        .servletPath("/api")
        .pathInfo("/orders/42"))
    .andExpect(status().isOk());
```

Here:

- The URI passed to `get(...)` is the full request path.
- `contextPath("/shop")` simulates where the application is deployed.
- `servletPath("/api")` simulates the segment matching the `/api/*` servlet mapping.
- `pathInfo("/orders/42")` is the remaining path passed to Spring MVC for handling.

These values must match the request path and servlet mapping. If the declared context path or servlet path disagrees with the URI, the mock request may be invalid or Spring MVC may resolve handlers against a different path than expected.

Do not place the query string in `contextPath`, `servletPath`, or `pathInfo`. Configure query parameters separately on the request builder.

## 3. Path Variables and Query Parameters

A path variable is part of the path, usually declared with `@PathVariable`. A query parameter is query data after `?`, usually received with `@RequestParam`.

Controller example:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/orders/{orderId}")
    OrderView findOrder(
            @PathVariable String orderId,
            @RequestParam(defaultValue = "false") boolean includeItems) {
        return new OrderView(orderId, includeItems);
    }
}
```

The test can fill path variable values using a URI template and pass query parameters with `queryParam(...)`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/orders/{orderId}", "ORD-42")
        .queryParam("includeItems", "true"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.orderId").value("ORD-42"))
    .andExpect(jsonPath("$.includeItems").value(true));
```

URI templates let Spring substitute values into the right path variable positions and handle URI encoding via the request builder. For multiple query parameters sharing the same name, pass multiple values:

```java
mockMvc.perform(get("/search")
    .queryParam("tag", "spring", "testing"));
```

`queryParam(...)` explicitly expresses parameters in the query string. `param(...)` sets request parameters on the Servlet request; it is often used when the controller only cares about `@RequestParam` values, including in form-request tests. If a test needs to verify the exact query string or URL construction, use `queryParam(...)` or include the query in the URI.

## 4. Sending HTTP Methods, Headers, and Content Negotiation

The request builder provides methods corresponding to HTTP methods such as `get`, `post`, `put`, `patch`, `delete`, `options`, and `head`. Headers can be added with `header(...)`; multiple values can be passed for the same header.

```java
import org.springframework.http.MediaType;

mockMvc.perform(get("/orders/ORD-42")
        .header("X-Trace-Id", "trace-246")
        .header("X-Client", "web", "mobile")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
```

`accept(...)` describes the response type the client accepts via the `Accept` header. `contentType(...)` describes the data type sent in the request via the `Content-Type` header. These two values have different meanings:

```java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "C-208",
              "total": 250000
            }
            """))
    .andExpect(status().isCreated());
```

`content(...)` sets the request body. When testing JSON, set the appropriate `Content-Type` and send valid JSON; if the controller returns JSON, set `Accept` to indicate the expected response format. When the application uses message converters, testing this way exercises Spring MVC's body reading and data conversion pipeline.

## 5. Cookies, Sessions, and Flash Attributes

Requests can carry information through cookies or sessions. MockMvc supports concise ways to set them up:

```java
import jakarta.servlet.http.Cookie;
import org.springframework.mock.web.MockHttpSession;

MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", "U-17");

mockMvc.perform(get("/account")
        .cookie(new Cookie("locale", "vi"))
        .session(session))
    .andExpect(status().isOk());
```

If you only need to add a few session attributes, use `sessionAttr(...)` or `sessionAttrs(...)` instead of creating a `MockHttpSession` manually:

```java
mockMvc.perform(get("/account")
    .sessionAttr("userId", "U-17"));
```

Flash attributes pass data across a redirect flow. They can be set with `flashAttr(...)` or `flashAttrs(...)`:

```java
mockMvc.perform(get("/orders/complete")
    .flashAttr("notice", "Order saved"));
```

Choose the right storage mechanism according to the controller's contract: cookies are client-sent data in the request; sessions store state bound to a session; flash attributes pass temporary information across redirects; request attributes exist only for the current request.

## 6. Request Attributes and Client Metadata

Some controllers or interceptors read request attributes placed by a filter or an earlier layer. These can be set directly:

```java
mockMvc.perform(get("/internal/report")
    .requestAttr("correlationId", "corr-246"));
```

Other metadata can be configured via the request builder:

```java
import java.util.Locale;

mockMvc.perform(get("/profile")
    .locale(Locale.forLanguageTag("vi-VN"))
    .secure(true)
    .characterEncoding("UTF-8")
    .remoteAddress("192.0.2.10"));
```

These properties help simulate language, secure connections, encoding, and client address that the application may inspect. Set them only when the flow under test actually depends on that metadata.

If you need to set complex data or customize Servlet request behavior, the request builder supports `with(...)` accepting a `RequestPostProcessor`:

```java
mockMvc.perform(get("/profile").with(request -> {
    request.setAttribute("tenantId", "tenant-17");
    return request;
}));
```

For Spring Security applications, post-processors such as `user(...)`, `anonymous()`, or `csrf()` are provided by the Spring Security test library. They require the `spring-security-test` dependency; they are not core methods of the Servlet request builder.

## 7. Using defaultRequest for Shared Metadata

When many requests on the same `MockMvc` instance share common headers or settings, configure `defaultRequest(...)` on the builder:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Test-Client", "mockmvc"))
    .build();
```

Default settings are applied when executing requests; individual requests can still override specific values as needed. Use `defaultRequest` for settings genuinely shared across the test suite, such as `Accept` or a client-identifying header. Case-specific path, method, body, and parameters should be declared inside `perform(...)` so readers can clearly see what request is being sent.

## 8. Distinguishing Request Data Types

| Data | Request builder | Where the application typically reads it |
|---|---|---|
| Path variable | URI template in `get(...)`, `post(...)`, etc. | `@PathVariable` |
| Query parameter | `queryParam(...)` | `@RequestParam` |
| Servlet request parameter | `param(...)` | `getParameter(...)`, `@RequestParam` |
| Header | `header(...)`, `headers(...)` | `@RequestHeader`, `getHeader(...)` |
| Request body | `content(...)` and `contentType(...)` | `@RequestBody`, message converter |
| Cookie | `cookie(...)` | `@CookieValue`, `getCookies()` |
| Session | `session(...)`, `sessionAttr(...)` | `HttpSession`, `@SessionAttribute` |
| Flash attribute | `flashAttr(...)`, `flashAttrs(...)` | `RedirectAttributes`, `FlashMap` |
| Request attribute | `requestAttr(...)`, `requestAttrs(...)` | `@RequestAttribute`, `getAttribute(...)` |
| Locale / secure / remote address | `locale(...)`, `secure(...)`, `remoteAddress(...)` | `LocaleResolver`, `isSecure()`, `getRemoteAddr()` |

Do not substitute one data type for another just because a controller happens to be able to read both. For instance, a value in the query string is not equivalent to a header of the same name; a JSON request body is not equivalent to request parameters. Tests must reflect the exact protocol used by real clients.

## 9. Common Mistakes When Configuring Requests

| Symptom | Cause to check |
|---|---|
| Request does not match handler when the app has a context path | Missing `contextPath(...)` or request URI lacks the deployment prefix |
| Controller does not receive the path portion after servlet mapping | `servletPath(...)` and `pathInfo(...)` do not reflect the actual `DispatcherServlet` mapping |
| Path variable is not bound | URI template does not match `@RequestMapping`, wrong segment count, or path values in wrong positions |
| `@RequestParam` has no value | Mistakenly used path variable, header, or body instead of a request parameter; verify name and parameter setup |
| JSON body is not converted | Missing or wrong `Content-Type`, invalid JSON, or message converter does not support the target type |
| `@RequestHeader` does not receive value | Wrong header name or header was not added to the request |
| Session data does not appear | Request used a different session than expected or session attribute was never set |
| Mock test passes, but real deployed URL fails | Need to verify actual context path and servlet mapping in the deployment environment |

When a request fails to reach the expected controller, inspect in order: HTTP method, request URI, context path, servlet path, path info, and controller mapping. Only then inspect parameters, headers, body, and session. This order distinguishes routing failures from data-binding failures.

## 10. Workflow for Building a Clear MockMvc Request

1. Choose the HTTP method and URI matching the endpoint.
2. If the application has a context path or custom servlet mapping, configure `contextPath`, `servletPath`, and `pathInfo` so they match the request URI.
3. Put path variables in the URI template; use `queryParam` or `param` for request parameters.
4. Add headers, `Accept`, and `Content-Type` per the endpoint's protocol.
5. Send the body with `content(...)` if the endpoint expects data in the request body.
6. Configure cookies, session, flash attributes, or request attributes if business logic requires them.
7. Use result matchers to assert status, headers, content type, and response body.

A well-written MockMvc request shows readers clearly which method the client sent, to which path, under which context and servlet mapping, and where each piece of data lives. Accurately simulating all parts of the Servlet request ensures tests verify both routing and how Spring MVC binds information into the controller.
