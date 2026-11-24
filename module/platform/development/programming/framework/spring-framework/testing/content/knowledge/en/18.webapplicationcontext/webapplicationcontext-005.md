# Preparing Request Attributes for Request-Scoped Beans

## 1. Why Do Request-Scoped Beans Need Request Attributes?

In a Spring web application, a bean with `request` scope has a separate instance created for each HTTP request. Accesses to the bean within the same request receive the same instance; when the request ends, Spring runs any destruction callbacks registered for that bean and removes the instance from the request scope.

For example, an application might store request correlation information, temporary form data, or a context object that only makes sense during a single HTTP call. This data should not be shared across concurrent requests.

To implement this scope, Spring needs to know which request is currently active and where to store request attributes. In a Servlet application, that information is represented by `ServletRequestAttributes` and provided through `RequestContextHolder`.

When running in a normal HTTP processing flow, `DispatcherServlet` sets up the request context for processing. Other integration approaches may use `RequestContextListener` or `RequestContextFilter`. In tests that invoke a bean directly, no Servlet request automatically passes through these components. Therefore, the test must create a mock request and bind request attributes to the current thread manually.

## 2. Related Components

| Component | Role |
|---|---|
| `RequestAttributes` | Abstract contract for reading, writing, and removing attributes scoped to a request or session. |
| `ServletRequestAttributes` | Spring's adapter for `HttpServletRequest` and `HttpServletResponse`; provides request attributes in a Servlet environment. |
| `RequestContextHolder` | Holds the current `RequestAttributes` per execution thread so components such as request scope can look up the active request. |
| `MockHttpServletRequest` | Spring Test's mock Servlet request, suitable for preparing requests in tests without opening an HTTP port. |
| `@RequestScope` | Declares a bean whose lifecycle is tied to a single HTTP request. |

`RequestContextHolder` uses a thread-bound storage mechanism. As a result, setting attributes on one thread does not automatically make the request context present on another thread. Because of this characteristic as well, tests must clean up the context after running to avoid leaking state to subsequent tests.

## 3. Setting Up Request Attributes in Tests

The basic workflow consists of four steps:

1. Create a `MockHttpServletRequest`.
2. Wrap that request with `ServletRequestAttributes`.
3. Register the attributes with `RequestContextHolder` before accessing the request-scoped bean.
4. Complete the request and clear the context in a `finally` block.

The example below illustrates a bean that stores a correlation ID at request scope. When called multiple times within the same request, the bean returns the same ID; another request gets its own instance and ID.

```java
import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestCorrelation {

    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

If the bean is injected through a scoped proxy, the proxy looks up the instance belonging to the current request when a method is invoked. This allows another singleton to hold a reference to the proxy while still receiving the right instance per request.

A focused test can set up the request context directly as follows:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@SpringJUnitConfig
@WebAppConfiguration
class RequestCorrelationTest {

    @Configuration
    @Import(RequestCorrelation.class)
    static class TestConfig {
    }

    @Autowired
    private RequestCorrelation correlation;

    @Test
    void usesOneInstanceWithinARequestAndANewInstanceForAnotherRequest() {
        String firstRequestId = invokeInRequest();
        String secondRequestId = invokeInRequest();

        assertNotEquals(firstRequestId, secondRequestId);
    }

    private String invokeInRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        ServletRequestAttributes attributes = new ServletRequestAttributes(request);

        RequestContextHolder.setRequestAttributes(attributes);
        try {
            String firstCall = correlation.id();
            String secondCall = correlation.id();

            assertEquals(firstCall, secondCall);
            return firstCall;
        } finally {
            attributes.requestCompleted();
            RequestContextHolder.resetRequestAttributes();
        }
    }
}
```

The test snippet above assumes `correlation` is a bean obtained from a Spring web application context with request scope registered. In a real project, you can use `@SpringJUnitConfig` combined with web context configuration, or `@SpringBootTest` if you need to test application configuration. You cannot simply instantiate a Java object with `new RequestCorrelation()` and expect `@RequestScope` to work on its own: scope is managed by the Spring container.

If you want to verify two requests explicitly in the same test, invoke the bean within two separate context setups as in the example. Each newly created `ServletRequestAttributes` corresponds to a new request. Calling the bean twice while the same attributes are bound verifies instance stability within the same request.

## 4. Reading and Writing Request Attributes Directly

Sometimes a test's goal is to verify that a component reads an attribute pre-populated on the request. You can set attributes on the mock request before binding attributes:

```java
MockHttpServletRequest request = new MockHttpServletRequest();
request.setAttribute("tenantId", "tenant-42");

ServletRequestAttributes attributes = new ServletRequestAttributes(request);
RequestContextHolder.setRequestAttributes(attributes);
try {
    Object tenantId = RequestContextHolder.currentRequestAttributes()
            .getAttribute("tenantId", RequestAttributes.SCOPE_REQUEST);

    // Perform assertion with tenantId.
} finally {
    attributes.requestCompleted();
    RequestContextHolder.resetRequestAttributes();
}
```

In this example, `RequestAttributes.SCOPE_REQUEST` specifies that the storage scope is the request. `RequestContextHolder.currentRequestAttributes()` returns the context bound to the current thread. If no context has been set up yet, this method throws `IllegalStateException` because there are no active request attributes.

You can use `RequestContextHolder.setRequestAttributes(attributes, true)` to enable `InheritableThreadLocal` mode. However, do not use this option as a general fix for asynchronous processing: thread pools reuse threads and the request lifecycle may not match the task lifecycle. For background tasks, pass the required data explicitly or use a dedicated context propagation mechanism.

## 5. Cleaning Up the Lifecycle Properly

The two cleanup operations in the example serve different purposes:

- `attributes.requestCompleted()` informs `ServletRequestAttributes` that request processing has finished. It allows registered request-completion callbacks and attribute-destruction callbacks to execute.
- `RequestContextHolder.resetRequestAttributes()` removes the context from the current thread, preventing the previous test's request from affecting the next test.

Place both operations inside `finally` so they still run if an assertion or code under test throws an exception. Clearing the context without signaling request completion may prevent lifecycle callbacks from running as expected. Signaling completion without resetting the holder may leave the thread holding a reference to stale attributes.

Do not call `resetRequestAttributes()` before code that needs the request context has finished running. When testing multiple sequential requests, complete and reset the current request before binding attributes for the next request.

## 6. When Should MockMvc Be Used?

Setting up `RequestContextHolder` manually fits when testing a bean or service that needs a request context without simulating the full HTTP dispatch process. If you need to test controllers, filters, interceptors, argument resolvers, or integrated HTTP handling flows, use `MockMvc`.

`MockMvc` dispatches requests through the Spring MVC processing chain in a mock Servlet environment. `DispatcherServlet` sets up and manages the request context during dispatch, so tests usually do not need to call `RequestContextHolder.setRequestAttributes()` themselves.

Example of testing a controller with `MockMvc`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RequestControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void handlesRequestWithRequestScopedDependencies() throws Exception {
        mockMvc.perform(get("/request-info"))
                .andExpect(status().isOk());
    }
}
```

The `/request-info` path here is an example and must exist in the application under test. If the test only needs to confirm that a bean retrieves a prepared request attribute, manual setup is shorter and more focused. If you need to confirm behavior at the HTTP boundary, `MockMvc` provides more appropriate coverage.

## 7. Common Errors

| Symptom | Common cause | How to resolve |
|---|---|---|
| `No thread-bound request found` or `IllegalStateException` when retrieving request attributes | Code accesses request scope outside an active request or the test has not bound attributes. | Create `ServletRequestAttributes` and call `RequestContextHolder.setRequestAttributes()` before accessing the bean; or run through `MockMvc`. |
| `Scope 'request' is not active` | The bean is invoked when request scope is not active, or the bean is not managed in a suitable web application context. | Verify that the context registers web scopes and the request context is set up at the right time. |
| Test passes in isolation but fails or becomes order-dependent in a suite | Stale request attributes remain bound on the thread due to missing cleanup. | Use `try/finally`, calling `requestCompleted()` and `resetRequestAttributes()`. |
| Two requests unexpectedly share data | Data is stored in a singleton/static field, or the test reuses the same request attributes. | Create a fresh request and attributes for each request; keep isolated data in a request-scoped bean or request attributes. |
| Background task does not see the request context | The request context is bound to the request-handling thread and does not automatically propagate safely to thread pools. | Pass required data explicitly or design an appropriate context propagation mechanism for the task. |

One distinction to make: `@RequestScope` and reading an attribute from `HttpServletRequest` are related but not identical. `@RequestScope` controls the lifecycle of a bean instance in Spring. `request.setAttribute(...)` merely places a value on the current request. A bean can use request attributes, but setting an attribute does not automatically turn a regular bean into a request-scoped bean.

## 8. Checklist When Writing Tests

- [ ] The bean under test is created and managed by a Spring container that supports web scopes.
- [ ] Each mock request has its own `MockHttpServletRequest` and `ServletRequestAttributes`.
- [ ] The request context is bound before the first access to the request-scoped bean or proxy.
- [ ] Accesses within the same request happen while the same attributes remain active.
- [ ] The request is completed and `RequestContextHolder` is reset inside `finally`.
- [ ] Tests create a new request when verifying that data or instances are not shared across requests.
- [ ] Use `MockMvc` if the goal is to test Spring MVC's HTTP processing chain.

## 9. Conclusion

To test request-scoped beans independently of a web server, create a `MockHttpServletRequest`, wrap it in `ServletRequestAttributes`, and bind it to `RequestContextHolder` before calling the bean. After testing, complete the attributes and clear the context in `finally`. This approach reproduces the request context that request scope needs while keeping tests isolated with a clear lifecycle.
