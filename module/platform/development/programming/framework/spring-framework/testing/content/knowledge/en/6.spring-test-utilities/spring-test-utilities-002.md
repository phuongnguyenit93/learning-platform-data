# MockHttpServletRequest, MockHttpServletResponse and MockHttpSession

Spring Framework Test provides three mock Servlet API objects for testing web code without starting a real servlet container:

- `MockHttpServletRequest` simulates an HTTP request entering the application.
- `MockHttpServletResponse` captures the status, headers, cookies, and response body produced by the code.
- `MockHttpSession` simulates a server-side session and stores attributes in memory.

These classes belong to the `org.springframework.mock.web` package in the `spring-test` module. They are useful when testing a component that works directly with `HttpServletRequest`, `HttpServletResponse`, or `HttpSession`, such as a servlet, filter, interceptor, adapter, or a helper that reads request information.

They are also the foundation used by many higher-level Spring web testing utilities. However, creating these three objects yourself does not mean running all of Spring MVC: the test only controls the objects passed directly to the code under test.

## 1. What do the three objects simulate?

| Class | Role | Data commonly set or read |
|---|---|---|
| `MockHttpServletRequest` | Simulates a request sent to a servlet | HTTP method, URI, context path, servlet path, query string, parameters, headers, cookies, body, locale, principal, session, and request attributes. |
| `MockHttpServletResponse` | Simulates a response produced by a servlet | Status, headers, cookies, content type, encoding, body, redirect, error, and committed state. |
| `MockHttpSession` | Simulates a server-side session | Session id, attributes, creation time, last accessed time, new state, and maximum inactive interval. |

Common relationship:

```text
Test
 │
 ├── creates MockHttpServletRequest
 │       └── holds parameters, headers, body, cookies, session...
 │
 ├── creates MockHttpServletResponse
 │       └── records status, headers, cookies, body...
 │
 └── calls component under test
         ├── reads request
         ├── may mutate session
         └── writes response
```

These objects implement part of the Servlet API contract in a test environment. They do not open sockets, do not send HTTP over the network, and do not require a real running Tomcat, Jetty, or other servlet container.

## 2. Dependencies and packages

The mock servlet objects are provided by the `spring-test` module. In a Spring Boot application, the `spring-boot-starter-test` dependency typically brings Spring Test onto the test classpath. In a Spring Framework project without Boot, you can declare `org.springframework:spring-test` directly in test scope alongside JUnit Jupiter and your preferred assertion library.

Gradle example when declaring dependencies manually:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
```

Key imports:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockServletContext;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.HandlerInterceptor;
import static org.assertj.core.api.Assertions.assertThat;
```

The examples below also use Servlet API types such as `Cookie`, `HttpServletRequest`, `HttpServletResponse`, and `HttpSession`, along with standard Java types such as `StandardCharsets`, `Locale`, and `List`. Servlet API imports must match the namespace of the version in use: Spring Framework 6.x uses `jakarta.servlet`; Spring Framework 5.x uses `javax.servlet`.

These mocks are independent of starting an `ApplicationContext`. A test can instantiate them via constructors and pass them to the code under test. If the test needs Spring MVC dispatching, use MockMvc; if it only needs a servlet request/response to call a component directly, there is no need to create a context just to get these three objects.

## 3. Creating and configuring MockHttpServletRequest

`MockHttpServletRequest` lets you set up a request in a repeatable way. The test does not need to build raw HTTP strings; it only sets the method, URI, parameters, headers, body, and related properties.

### 3.1. Initializing the request

You can use the default constructor or a constructor accepting a servlet context, HTTP method, and request URI. When you need to test resource lookup or servlet context attributes, you can pass an explicit `MockServletContext`:

```java
MockServletContext servletContext = new MockServletContext();
MockHttpServletRequest request = new MockHttpServletRequest(
        servletContext,
        "POST",
        "/shop/orders"
);
```

If the component under test does not depend on a specific servlet context, the simpler constructor is usually sufficient:

```java
MockHttpServletRequest request = new MockHttpServletRequest();
request.setMethod("GET");
request.setRequestURI("/orders");
```

Set related properties together so the test expresses the actual request the application receives. For example, a request to an endpoint under the `/shop` context path:

```java
MockHttpServletRequest request = new MockHttpServletRequest(
        "GET",
        "/shop/orders/42"
);
request.setContextPath("/shop");
request.setServletPath("/orders/42");
```

In the Servlet API, these values have distinct meanings:

| Property | Example | Meaning |
|---|---|---|
| Request URI | `/shop/orders/42` | The request path received by the server, usually including the context path. |
| Context path | `/shop` | The root path under which the application is deployed; can be an empty string. |
| Servlet path | `/orders/42` | The portion of the path mapped to the servlet. |
| Path info | `null` or remaining path | Additional path information after the servlet path in mapping styles that support it. |
| Query string | `page=2&size=20` | The query portion of the URL, excluding the `?` sign. |

Do not assign path properties arbitrarily if the test is verifying URL parsing or servlet mapping logic. An inconsistent set of values can cause the test to simulate a request that is unlikely to occur in a real container.

### 3.2. Query parameters and form parameters

Request parameters are set with `setParameter` or `addParameter`. Use `setParameter` when a single value suffices; use `addParameter` when one name has multiple values.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/orders");
request.setParameter("page", "2");
request.setParameter("size", "20");

assertThat(request.getParameter("page")).isEqualTo("2");
assertThat(request.getParameter("size")).isEqualTo("20");
```

For multi-valued parameters:

```java
request.addParameter("status", "PAID", "SHIPPED");

assertThat(request.getParameter("status")).isEqualTo("PAID");
assertThat(request.getParameterValues("status"))
        .containsExactly("PAID", "SHIPPED");
```

The Servlet API provides parameters as strings. Converting them to numbers, dates, or enums is the responsibility of request-handling code or Spring MVC argument resolvers when running through DispatcherServlet. When calling a helper directly, the test needs to verify that helper's own conversion logic.

### 3.3. Headers, cookies, and connection info

You can set headers using `addHeader` or `setHeader`, cookies using `setCookies`, and connection properties such as scheme, server name, port, secure flag, or remote address.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/profile");
request.addHeader("X-Request-Id", "req-123");
request.addHeader("Accept", "application/json");
request.setScheme("https");
request.setServerName("example.test");
request.setServerPort(443);
request.setSecure(true);
request.setRemoteAddr("192.0.2.10");
request.setCookies(new Cookie("theme", "dark"));
```

These properties are useful when code needs to build absolute URLs, determine whether a request is secure, read a request id, inspect cookies, or handle client addresses. They are only values the test sets on the object. They do not prove that a proxy, load balancer, or real container actually forwarded those headers and addresses correctly.

When testing code that relies on user information, you can set a principal or remote user on the request. However, setting a principal directly is not equivalent to running the Spring Security filter chain or verifying a real token.

### 3.4. Request body and encoding

To simulate a request with a body, set the content type, character encoding, and byte content:

```java
String json = """
        {"sku":"SKU-1","quantity":2}
        """;

MockHttpServletRequest request = new MockHttpServletRequest("POST", "/orders");
request.setContentType("application/json");
request.setCharacterEncoding(StandardCharsets.UTF_8.name());
request.setContent(json.getBytes(StandardCharsets.UTF_8));
```

Code using `getInputStream()` or `getReader()` can read the content from the mock request. When data contains non-ASCII characters, specify the encoding explicitly to avoid making the test depend on the environment's default encoding.

Setting `Content-Type` describes the body format, while `setCharacterEncoding` defines how text is interpreted. For JSON, tests should use UTF-8 bytes and declare an appropriate content type. Parsing JSON in a Spring MVC controller still requires message converters; merely creating a mock request and calling a helper does not trigger Jackson automatically.

### 3.5. Request attributes and locale

Request attributes are data attached to a single request during processing, unlike parameters sent by the client and session attributes that persist across multiple requests.

```java
request.setAttribute("correlationId", "corr-456");
request.setLocale(Locale.forLanguageTag("vi-VN"));

assertThat(request.getAttribute("correlationId")).isEqualTo("corr-456");
assertThat(request.getLocale()).isEqualTo(Locale.forLanguageTag("vi-VN"));
```

Request attributes are commonly used by filters, interceptors, or servlets to pass data to subsequent processing steps. Locale can be used to test code that selects messages or formats values by language.

## 4. Reading and verifying MockHttpServletResponse

`MockHttpServletResponse` records whatever the code writes to the response. Tests can inspect status, headers, cookies, content type, encoding, and body without receiving a response over real HTTP.

### 4.1. Status and headers

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.setStatus(HttpServletResponse.SC_CREATED);
response.setHeader("Location", "/orders/42");
response.addHeader("X-Request-Id", "req-123");

assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_CREATED);
assertThat(response.getHeader("Location")).isEqualTo("/orders/42");
assertThat(response.getHeader("X-Request-Id")).isEqualTo("req-123");
```

Distinguish between `setHeader` and `addHeader`: setting replaces the header value for that name, whereas adding appends another value. This matters for repeatable headers, such as certain list-style headers or `Set-Cookie`.

### 4.2. Content type, character encoding, and response body

A response can write content through a writer or an output stream. For example:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.setContentType("text/plain");
response.setCharacterEncoding(StandardCharsets.UTF_8.name());
response.getWriter().write("Đã tạo đơn hàng");

assertThat(response.getContentType()).isEqualTo("text/plain");
assertThat(response.getCharacterEncoding()).isEqualTo("UTF-8");
assertThat(new String(response.getContentAsByteArray(), StandardCharsets.UTF_8))
        .isEqualTo("Đã tạo đơn hàng");
```

`getContentAsByteArray()` allows reading the written bytes. When comparing text, decode the bytes with the exact charset the response uses. Some Spring Test versions also provide `getContentAsString()`; use the API appropriate for the declared Spring version.

A servlet response does not allow code to arbitrarily mix obtaining a writer and an output stream on the same response. Tests should mirror how the component under test is actually used. If the code calls `getWriter()`, verify the result via the written body instead of obtaining another output stream afterward.

### 4.3. Cookies, redirects, and error responses

The mock response captures added cookies, redirect URLs, and error information:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.addCookie(new Cookie("session-hint", "created"));
response.sendRedirect("/login");

assertThat(response.getRedirectedUrl()).isEqualTo("/login");
```

For an error response:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
response.sendError(HttpServletResponse.SC_NOT_FOUND, "Order not found");

assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_NOT_FOUND);
assertThat(response.getErrorMessage()).isEqualTo("Order not found");
```

Helpers like `sendRedirect` and `sendError` let tests verify the code's response intent. They do not actually navigate a browser or send an error page over the network.

### 4.4. Buffer and committed state

A response has a content buffer. Operations such as flushing the buffer or sending an error/redirect can affect the committed state according to the Servlet API contract. This matters when code needs to know whether headers or status can still be modified.

For example:

```java
MockHttpServletResponse response = new MockHttpServletResponse();
assertThat(response.isCommitted()).isFalse();

response.flushBuffer();

assertThat(response.isCommitted()).isTrue();
```

Do not test internal buffer details of the mock deeply if that behavior is not an application responsibility. When you need to prove actual container interaction, add tests running through a real server.

## 5. Managing sessions with MockHttpSession

`MockHttpSession` simulates server-side session storage. Tests can add, read, or remove attributes, check the session id, or verify invalidation state without exchanging real session cookies through a browser.

### 5.1. Creating a session and storing attributes

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", "user-42");
session.setAttribute("cartCount", 3);

assertThat(session.getAttribute("userId")).isEqualTo("user-42");
assertThat(session.getAttribute("cartCount")).isEqualTo(3);
```

Session attributes are commonly used to store information tied to a user session, such as a shopping cart or wizard state. In tests, set only the attributes that the code under test actually uses.

### 5.2. Attaching a session to a request

A request can create a session when calling `getSession()` or `getSession(true)`. Calling `getSession(false)` only retrieves an existing session and returns `null` if the request does not yet have one.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/cart");

assertThat(request.getSession(false)).isNull();

HttpSession createdSession = request.getSession(true);
createdSession.setAttribute("cartId", "cart-100");

assertThat(request.getSession(false)).isSameAs(createdSession);
assertThat(request.getSession().getAttribute("cartId")).isEqualTo("cart-100");
```

If you need to start with an existing session, create a separate `MockHttpSession` and attach it to the request:

```java
MockHttpSession existingSession = new MockHttpSession();
existingSession.setAttribute("userId", "user-42");

MockHttpServletRequest request = new MockHttpServletRequest("GET", "/account");
request.setSession(existingSession);

assertThat(request.getSession(false)).isSameAs(existingSession);
```

This is how you simulate a second or subsequent request in the same session. If a test needs to verify that the application creates a new session, start with a request without a session so you do not accidentally skip the session-creation branch.

### 5.3. Removing attributes and invalidating

A session can remove individual attributes with `removeAttribute` or terminate with `invalidate`:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("userId", "user-42");
session.setAttribute("cartId", "cart-100");

session.removeAttribute("cartId");
assertThat(session.getAttribute("cartId")).isNull();

session.invalidate();
assertThat(session.isInvalid()).isTrue();
```

After invalidation, the session is no longer valid. When testing logout or session expiration handling, verify application behavior such as clearing login state, disassociating the session, or generating the appropriate response. Do not continue operating on an invalidated session as if it were still active normally.

### 5.4. Session lifecycle properties

`MockHttpSession` provides APIs to set or read details such as id, creation time, last accessed time, new status, and maximum inactive interval. These properties are useful when code needs to inspect session metadata.

Example setting the maximum inactive interval:

```java
MockHttpSession session = new MockHttpSession();
session.setMaxInactiveInterval(900);

assertThat(session.getMaxInactiveInterval()).isEqualTo(900);
```

This value simulates session timeout configuration. It does not cause the mock to run a background timer and automatically expire like a container's session store. To test real expiration policies, test the session management layer or the corresponding container environment.

## 6. Combining request, response, and session in a unit test

The following example illustrates a servlet-style handler that reads a request, updates a session, and writes a response. The goal is to test code that uses the Servlet API directly; the test calls the method with two prepared mock objects.

```java
public class CartHandler {

    public void addItem(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        String sku = request.getParameter("sku");
        if (sku == null || sku.isBlank()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "Missing sku");
            return;
        }

        HttpSession session = request.getSession();
        @SuppressWarnings("unchecked")
        List<String> items = (List<String>) session.getAttribute("items");
        if (items == null) {
            items = new ArrayList<>();
            session.setAttribute("items", items);
        }
        items.add(sku);

        response.setStatus(HttpServletResponse.SC_ACCEPTED);
        response.setContentType("text/plain");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("Added " + sku);
    }
}
```

Test for the success case:

```java
@Test
void addsItemToSessionAndWritesResponse() throws Exception {
    CartHandler handler = new CartHandler();
    MockHttpServletRequest request = new MockHttpServletRequest("POST", "/cart/items");
    MockHttpServletResponse response = new MockHttpServletResponse();
    request.setParameter("sku", "SKU-1");

    handler.addItem(request, response);

    assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_ACCEPTED);
    assertThat(new String(response.getContentAsByteArray(), StandardCharsets.UTF_8))
            .isEqualTo("Added SKU-1");
    @SuppressWarnings("unchecked")
    List<String> items = (List<String>) request.getSession(false).getAttribute("items");
    assertThat(items).containsExactly("SKU-1");
}
```

Test for the missing parameter case:

```java
@Test
void rejectsMissingSkuWithoutCreatingSession() throws Exception {
    CartHandler handler = new CartHandler();
    MockHttpServletRequest request = new MockHttpServletRequest("POST", "/cart/items");
    MockHttpServletResponse response = new MockHttpServletResponse();

    handler.addItem(request, response);

    assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_BAD_REQUEST);
    assertThat(request.getSession(false)).isNull();
}
```

Notice that the test can observe all three state areas: the incoming request data, the mutated session, and the written response. The test does not need to create a `DispatcherServlet`, controller beans, or an application context because it calls the handler directly.

## 7. Using mock servlet objects with filters and interceptors

These objects are also useful when testing a component that accepts Servlet API types directly. For example, a filter that reads a header and sets a request attribute can be invoked with mock request/response objects and a mock `FilterChain`. Similarly, a `HandlerInterceptor` can be invoked directly to verify its decision to allow or reject request processing.

When calling a filter or interceptor directly, the test must provide all arguments required by that component. If a filter needs `FilterConfig`, you can use the corresponding mock utility such as `MockFilterConfig`; if you need to simulate a chain, you can use `MockFilterChain` in Spring Test. Create only the supporting objects that the logic under test uses.

Simple example with an interceptor:

```java
class RequestIdInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        String requestId = request.getHeader("X-Request-Id");
        if (requestId == null || requestId.isBlank()) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            return false;
        }

        request.setAttribute("requestId", requestId);
        return true;
    }
}
```

Direct test:

```java
@Test
void storesRequestIdWhenHeaderIsPresent() throws Exception {
    RequestIdInterceptor interceptor = new RequestIdInterceptor();
    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/orders");
    MockHttpServletResponse response = new MockHttpServletResponse();
    request.addHeader("X-Request-Id", "req-123");

    boolean proceed = interceptor.preHandle(request, response, new Object());

    assertThat(proceed).isTrue();
    assertThat(request.getAttribute("requestId")).isEqualTo("req-123");
}
```

Calling `preHandle` directly verifies the interceptor's logic. It does not prove that the interceptor is registered properly in the MVC configuration or invoked in the expected order across the full request pipeline. Those things require tests through MockMvc or a context test.

## 8. When code uses RequestContextHolder

Some Spring code does not accept the request as a parameter and instead retrieves information from `RequestContextHolder`. In that case, creating a `MockHttpServletRequest` alone is not enough: the test must bind the request to the current thread using `ServletRequestAttributes`.

```java
MockHttpServletRequest request = new MockHttpServletRequest("GET", "/profile");
MockHttpServletResponse response = new MockHttpServletResponse();
request.setAttribute("tenantId", "tenant-1");

RequestContextHolder.setRequestAttributes(
        new ServletRequestAttributes(request, response)
);
try {
    // Call the service/helper that reads the current request from RequestContextHolder.
} finally {
    RequestContextHolder.resetRequestAttributes();
}
```

Always clean up thread-bound request attributes in a `finally` block. Otherwise, test state can leak into another test when the test engine reuses threads. You can use a helper or extension to encapsulate binding/unbinding if multiple tests need the same mechanism.

This binding only sets the request context for the test thread. It does not run the servlet filter chain, does not create request-scoped beans unless an appropriate Spring context is initialized, and does not automatically configure the Spring Security context.

## 9. Boundaries with MockMvc and a real server

The three mock objects are useful at the Servlet API level, while MockMvc provides a higher testing layer. MockMvc sends requests through Spring MVC's `DispatcherServlet` in a test environment and lets you verify processing results across the MVC flow.

| Testing approach | What is tested | When to use |
|---|---|---|
| Direct calls with `MockHttpServletRequest`/`MockHttpServletResponse` | Logic of a servlet, filter, interceptor, or helper that accepts Servlet API types directly. | When you want to isolate a component and control request/session/response yourself. |
| MockMvc | Spring MVC flow through DispatcherServlet, mappings, argument resolvers, validation, message converters, interceptors, and configured exception handling. | When you need to test MVC endpoints without opening a real HTTP port. |
| Real server over HTTP | HTTP and servlet container integration, network ports, server configuration, filter/container behavior, and real running components. | When you need to prove end-to-end behavior through a server. |

For example, if you want to verify that `@GetMapping` is mapped properly, `@RequestParam` is bound, JSON is serialized, or an exception handler is applied, use MockMvc. Calling a controller method directly with a mock request does not activate those MVC mechanisms.

If you want to test cookies/sessions across multiple real HTTP requests, container behavior, or proxy configuration, test through a server. `MockHttpSession` only simulates state in memory and does not automatically exchange cookies between client and server.

## 10. Common limitations and misconceptions

### Thinking a mock request ran through a servlet container

A mock request is only an object created in the JVM. It does not go through Tomcat/Jetty, does not traverse a socket, is not mapped to a servlet by the container, and does not automatically run filters. To test those steps, use MockMvc at the Spring MVC layer or a real server at the HTTP/container layer.

### Thinking a mock response sent data to a browser

The body and headers are stored inside the response object for the test to inspect. No browser or client receives them. A redirect URL is also only recorded information for assertions.

### Confusing request parameters, request attributes, and session attributes

The three kinds of data have different lifecycles:

| Type | Source or scope | Example |
|---|---|---|
| Parameter | Values sent by the client in query/form | `page=2`, `sku=SKU-1`. |
| Request attribute | Data attached to a single request during processing | Correlation id added by a filter. |
| Session attribute | Data attached to a session across multiple requests | User id or cart id. |

Placing data into the session instead of a request attribute by mistake may let a test pass for a single request while failing to reflect the actual application design.

### Thinking a mock session expires automatically

Setting `maxInactiveInterval` only sets a metadata value. A mock session does not fully simulate container session-expiration scanning, distributed storage, cookie renewal, or concurrent request handling.

### Thinking a principal on the request equals Spring Security

Setting a user/principal directly on a mock request can help test a helper that reads user info. It does not replace running the security filter chain, authentication providers, authorization rules, or token decoders.

### Using mock servlet objects for WebFlux

`MockHttpServletRequest` and `MockHttpServletResponse` simulate the Servlet API, which fits the Spring MVC/Servlet stack. Spring WebFlux has its own request/response abstractions. For WebFlux, prefer `WebTestClient` and the appropriate mock server/exchange utilities.

### Setting inconsistent request data

If a test checks URLs, mappings, or redirects, set the request URI, context path, servlet path, and query string consistently. A request whose URI includes a context path while the context path is not properly set can cause assertions not to reflect real requests.

## 11. How to choose a tool based on the test question

- Need to test a helper reading headers, parameters, or request attributes? Create a `MockHttpServletRequest` and call the helper directly.
- Need to test code writing status, cookies, or response bodies? Create a `MockHttpServletResponse` and inspect the output.
- Need to test session-scoped state logic? Attach a `MockHttpSession` to the request and check session attributes.
- Need to test a filter/interceptor on its own? Call the component directly with mock servlet objects and needed collaborators.
- Need to test controller mappings, validation, message conversion, or exception handling? Use MockMvc.
- Need to test the server, network, container, or real cookie exchange? Run tests through an HTTP server.

When using these three mock classes, set up the exact parts of the request the code reads, assert only on the response/session parts belonging to the behavior to verify, and keep test state isolated across runs. This way, Spring Test provides a lightweight Servlet API environment for testing web logic without starting the entire application.
