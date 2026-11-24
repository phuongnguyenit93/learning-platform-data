# RequestPostProcessor for Additional Request Data

When sending requests with MockMvc, `MockHttpServletRequestBuilder` methods such as `param(...)`, `header(...)`, `cookie(...)`, `sessionAttr(...)`, and `requestAttr(...)` already cover many common scenarios. However, sometimes a test needs to prepare data using custom logic, set multiple attributes together, or reuse a request customization across many tests. `RequestPostProcessor` provides an extension point for those cases.

A `RequestPostProcessor` receives a `MockHttpServletRequest`, modifies or adds data on the request, and returns the processed request. We attach the processor to the request builder with `.with(...)` before calling `mockMvc.perform(...)`.

## 1. Where Does RequestPostProcessor Run?

The basic flow of a MockMvc test:

```text
MockMvcRequestBuilders.get("/orders")
             |
             v
    MockHttpServletRequestBuilder
             |
             v
       .with(processor)
             |
             v
 RequestPostProcessor.postProcessRequest(request)
             |
             v
       MockMvc.perform(request)
             |
             v
 DispatcherServlet -> Controller -> Response
```

The interface lives in package `org.springframework.test.web.servlet.request` and defines the method:

```java
MockHttpServletRequest postProcessRequest(MockHttpServletRequest request);
```

The processor is invoked on the mock request prepared by the builder. It can add headers, set request attributes, configure a principal, or adjust other Servlet properties. After processing, the processor must return the request so MockMvc can continue executing it.

`RequestPostProcessor` only operates on the request. It does not receive the response and is not the place for assertions on status, body, or response headers. Use `ResultMatcher` methods such as `status()`, `content()`, and `header()` to verify the response.

## 2. When Should `.with(...)` Be Used?

For simple data, prefer the built-in methods on the request builder because they express intent directly:

```java
mockMvc.perform(get("/orders")
        .param("status", "OPEN")
        .header("X-Request-Id", "req-123")
        .cookie(new Cookie("locale", "vi"))
        .sessionAttr("cartId", "cart-42")
        .requestAttr("traceId", "trace-123"));
```

Use `RequestPostProcessor` when:

- You need to set a property for which the builder lacks a convenience method.
- A request needs multiple related values added according to a shared rule.
- The same request preparation logic is reused across many tests.
- Data must be computed or derived from arguments of a factory method.
- You want to encapsulate a test configuration such as tenant, correlation ID, or authentication info.

Do not create a dedicated processor for every simple header or parameter. A short lambda is appropriate when the logic appears in only one test; a factory method or separate class is helpful when the logic is reused.

## 3. Creating a Processor with a Lambda

Because `RequestPostProcessor` has a single method to implement, it can be written as a lambda:

```java
RequestPostProcessor tenantHeader = request -> {
    request.addHeader("X-Tenant-Id", "tenant-42");
    return request;
};
```

Attach the processor to the request:

```java
mockMvc.perform(get("/orders").with(tenantHeader))
        .andExpect(status().isOk());
```

Here, `addHeader(...)` appends a header to the mock request. The controller can read that value via `@RequestHeader` or `HttpServletRequest#getHeader(...)`.

Example of a controller reading the tenant ID:

```java
@RestController
class TenantController {

    @GetMapping("/tenant")
    String tenant(@RequestHeader("X-Tenant-Id") String tenantId) {
        return tenantId;
    }
}
```

Test using the processor:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new TenantController())
        .build();

RequestPostProcessor tenantHeader = request -> {
    request.addHeader("X-Tenant-Id", "tenant-42");
    return request;
};

mockMvc.perform(get("/tenant").with(tenantHeader))
        .andExpect(status().isOk())
        .andExpect(content().string("tenant-42"));
```

The example uses `standaloneSetup` to focus on the controller and processor. If the test needs full Spring MVC configuration, `webAppContextSetup(...)` or an appropriate Spring Boot configuration can be used.

## 4. Adding Different Kinds of Data to the Request

The processor receives `MockHttpServletRequest`, so it can use the mock request's APIs. Common cases include:

### Adding Headers

```java
RequestPostProcessor requestHeaders = request -> {
    request.addHeader("X-Tenant-Id", "tenant-42");
    request.addHeader("X-Correlation-Id", "corr-100");
    return request;
};
```

Use `addHeader(...)` when you want to add headers. If you need to set or replace a header's value in a test, consider the mock request's behavior and avoid having multiple processors write conflicting values to the same header.

### Setting Request Attributes

```java
RequestPostProcessor requestAttributes = request -> {
    request.setAttribute("tenantId", "tenant-42");
    request.setAttribute("featureEnabled", Boolean.TRUE);
    return request;
};
```

Request attributes exist within the scope of the current request. Controllers or interceptors can read them via `@RequestAttribute` or `request.getAttribute(...)`. These are server-side attributes attached to the request; they differ from headers or parameters sent by the client.

### Setting Session Attributes

```java
RequestPostProcessor sessionData = request -> {
    request.getSession(true).setAttribute("cartId", "cart-42");
    return request;
};
```

`getSession(true)` creates a session if the request does not already have one. Data is stored in the session and can persist across multiple requests sharing the same session. If only a single simple session attribute is needed, the builder also has `sessionAttr(...)`; a processor fits when preparing multiple values or applying custom logic.

### Setting a Principal

You can set the mock request's principal to test controllers reading `Principal` or `HttpServletRequest#getUserPrincipal()`:

```java
RequestPostProcessor principal = request -> {
    request.setUserPrincipal(() -> "alice");
    return request;
};
```

This is a principal set directly on the Servlet request. It does not create a Spring Security login session or prove that the security filter chain authenticated the user. For Spring Security tests, use dedicated processors from `spring-security-test` such as `user(...)` when the goal is supplying an `Authentication` to Spring Security.

### Setting Connection Details

```java
RequestPostProcessor httpsRequest = request -> {
    request.setScheme("https");
    request.setSecure(true);
    request.setServerName("api.example.test");
    request.setServerPort(443);
    request.setRemoteAddr("192.0.2.25");
    return request;
};
```

These properties are useful when the application builds absolute URLs, checks for a secure request, or records the client address. This is mock request data; the test creates no real network connection.

## 5. Creating Reusable Processors

When multiple tests share the same rule, encapsulate it in a factory method. The following example takes the tenant ID as a parameter so each request can use a different tenant:

```java
static RequestPostProcessor tenant(String tenantId) {
    return request -> {
        request.addHeader("X-Tenant-Id", tenantId);
        return request;
    };
}
```

Usage across tests:

```java
mockMvc.perform(get("/tenant").with(tenant("tenant-a")))
        .andExpect(status().isOk())
        .andExpect(content().string("tenant-a"));

mockMvc.perform(get("/tenant").with(tenant("tenant-b")))
        .andExpect(status().isOk())
        .andExpect(content().string("tenant-b"));
```

You can create a separate class if the processor takes multiple parameters or has lengthy logic:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

final class TenantRequestPostProcessor implements RequestPostProcessor {

    private final String tenantId;

    TenantRequestPostProcessor(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public MockHttpServletRequest postProcessRequest(MockHttpServletRequest request) {
        request.addHeader("X-Tenant-Id", tenantId);
        return request;
    }
}
```

Invoke this class via `.with(new TenantRequestPostProcessor("tenant-42"))`. A separate class provides a clear name and groups multi-step logic, while a factory method is usually more concise for a small processor.

## 6. Combining Multiple RequestPostProcessors

A request builder can accept multiple `.with(...)` calls:

```java
mockMvc.perform(get("/orders")
        .with(tenant("tenant-42"))
        .with(request -> {
            request.addHeader("X-Correlation-Id", "corr-123");
            return request;
        })
        .with(request -> {
            request.setAttribute("featureEnabled", Boolean.TRUE);
            return request;
        }))
        .andExpect(status().isOk());
```

Processors are applied sequentially on the request builder. Therefore, if two processors modify the same property, the one running later can alter the outcome of the earlier one. Separate responsibilities clearly and avoid having multiple processors write the same header, principal, or attribute unless the test intentionally verifies overriding behavior.

When a group of processors always goes together, you can combine them into a single processor to keep tests readable. Conversely, keeping them separate is helpful when each part can be reused independently.

## 7. Using Spring Security's RequestPostProcessors

Spring Security provides its own `RequestPostProcessor` implementations in the `spring-security-test` module. They are commonly used to prepare security state for MockMvc tests, such as an authenticated user or a CSRF token.

Example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(post("/admin/reports")
        .with(user("alice").roles("ADMIN"))
        .with(csrf()))
        .andExpect(status().isOk());
```

- `user("alice").roles("ADMIN")` supplies an authenticated user along with matching authorities in the Spring Security test context.
- `csrf()` adds a valid CSRF token to the request to pass CSRF verification when security configuration requires a token.

For these processors to take effect as expected, the test needs the `spring-security-test` dependency and MockMvc must be integrated with the Spring Security filter chain—for instance, via `SecurityMockMvcConfigurers.springSecurity()` when building manually or via Spring Boot's MockMvc configuration. If the filter chain does not run, setting a user or CSRF token will not test real security behavior.

Example building MockMvc manually with Spring Security:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`user(...)` is a way to prepare `SecurityContext` for tests. It does not simulate the full login workflow such as submitting username/password to a login endpoint. If you need to test the actual authentication mechanism, send requests through the appropriate endpoint and filter chain.

## 8. RequestPostProcessor vs. Other Ways to Add Data

| Need | Suitable API | Example |
|---|---|---|
| Query parameter | Request builder | `.param("page", "2")` |
| Simple header | Request builder | `.header("X-Trace-Id", "t-1")` |
| Cookie | Request builder | `.cookie(new Cookie("lang", "vi"))` |
| Simple session attribute | Request builder | `.sessionAttr("cartId", "c-1")` |
| Simple request attribute | Request builder | `.requestAttr("tenantId", "t-1")` |
| Data needing logic or multiple properties | `RequestPostProcessor` | `.with(tenantAndTrace("t-1", "trace-1"))` |
| User or CSRF in Spring Security | Security request post-processors | `.with(user("alice")).with(csrf())` |

Builder methods are usually easier to read for individual pieces of data. Processors are useful when encapsulating rules or modifying requests with custom logic.

## 9. Complete Example: Sending Tenant and Correlation ID

Suppose a controller returns information received from the request:

```java
@RestController
class RequestInfoController {

    @GetMapping("/request-info")
    String requestInfo(@RequestHeader("X-Tenant-Id") String tenantId,
                       @RequestHeader("X-Correlation-Id") String correlationId) {
        return tenantId + ":" + correlationId;
    }
}
```

Create a factory method to attach both headers:

```java
static RequestPostProcessor requestInfo(String tenantId, String correlationId) {
    return request -> {
        request.addHeader("X-Tenant-Id", tenantId);
        request.addHeader("X-Correlation-Id", correlationId);
        return request;
    };
}
```

Test:

```java
import org.junit.jupiter.api.Test;

import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RequestPostProcessorTests {

    private final MockMvc mockMvc = MockMvcBuilders
            .standaloneSetup(new RequestInfoController())
            .build();

    @Test
    void addsTenantAndCorrelationHeaders() throws Exception {
        mockMvc.perform(get("/request-info")
                .with(requestInfo("tenant-42", "corr-123")))
                .andExpect(status().isOk())
                .andExpect(content().string("tenant-42:corr-123"));
    }
}
```

The example shows how a processor can bundle multiple headers into a unit named after its business meaning. The test only passes the inputs and verifies the response.

## 10. Common Errors

| Symptom | Common cause | How to resolve |
|---|---|---|
| Processor has no effect | Created the processor but forgot to attach it via `.with(...)` | Attach the processor to the exact request builder passed to `mockMvc.perform(...)` |
| Request fails at runtime | `postProcessRequest` did not return the request | Always return the processed `MockHttpServletRequest` instance |
| Controller cannot read the data | Set a request attribute while the controller reads a header or parameter | Pick the right data channel: header, parameter, request attribute, or session attribute |
| Value gets overwritten | Multiple processors modify the same property | Control execution order and separate responsibilities across processors |
| Data leaks between tests | Shared mutable object or unintended session state | Create fresh data per request; share only immutable processors |
| `user(...)` does not produce expected auth state | Missing `spring-security-test` or security filter chain not running | Add the dependency and integrate Spring Security with MockMvc |
| Request has a principal, yet authorization still fails | Only called `setUserPrincipal(...)` without setting Spring Security's `SecurityContext` | Use the `user(...)` processor when testing Spring Security |

## 11. Usage Principles

- Use direct request builder APIs for simple parameters, headers, cookies, and attributes.
- Use `RequestPostProcessor` when custom logic, multiple related properties, or reusable rules are needed.
- Always return `MockHttpServletRequest` from `postProcessRequest`.
- Create data per request and avoid shared mutable state between tests.
- When combining multiple processors, keep ordering clear and avoid unintended overrides.
- Use `ResultMatcher` to assert the response; processors only prepare the request.
- For Spring Security, use processors from `spring-security-test` and ensure the security filter chain actually participates in MockMvc.

## 12. Key Takeaways

`RequestPostProcessor` is an extension point for customizing `MockHttpServletRequest` before MockMvc executes the request. Attach processors with `.with(...)`; implementations can use lambdas, factory methods, or dedicated classes. It suits adding headers, request/session attributes, principals, or connection metadata with custom logic. For simple data, built-in methods on the request builder are usually easier to read; for authentication state and CSRF, use the dedicated Spring Security processors.

