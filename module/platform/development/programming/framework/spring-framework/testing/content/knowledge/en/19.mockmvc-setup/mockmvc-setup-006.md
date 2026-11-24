# Registering Filters and Execution Order in MockMvc

Filters are part of the Servlet request processing pipeline. A filter can inspect or modify a request before it reaches `DispatcherServlet`, and then process the response as the call returns back up the filter chain. When writing tests with MockMvc, you need to register the filters that requests must pass through and control their ordering so test results reflect the intended configuration.

This lesson focuses on registering filters with MockMvc, mapping filters by URL, and verifying execution order. Examples use JUnit Jupiter and Spring Framework 6 or later; for Spring Framework 5.x, replace `jakarta.servlet.*` imports with the corresponding `javax.servlet.*` imports.

## 1. Where Do Filters Sit in the Request Flow?

In a Spring MVC application, a request typically passes through the following chain:

```text
HTTP request
    |
    v
Filter A
    |
    v
Filter B
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> Controller
    |
    v
HTTP response returns back through Filter B, then Filter A
```

Filters run before `DispatcherServlet`, so they can handle Servlet-level concerns such as encoding, CORS, authentication, logging, correlation IDs, or wrapping requests/responses. A filter calls `filterChain.doFilter(request, response)` to pass control to the next filter. Once the downstream filter completes, execution returns to the statements after that call.

Filters differ from `HandlerInterceptor`: interceptors belong to the Spring MVC pipeline and operate around handlers/controllers; filters belong to the Servlet pipeline and run before `DispatcherServlet`. If you need to test logic that depends on the selected handler, an interceptor may be a better fit. If you need to test behavior at the Servlet request/response level, test the filter.

## 2. Choosing How to Build MockMvc

MockMvc has two common setup methods:

| Builder Method | When to Use | How to Register Filters |
|---|---|---|
| `standaloneSetup(...)` | Testing one or a few controllers with minimal MVC configuration | Call `addFilters(...)` or `addFilter(...)` on the builder |
| `webAppContextSetup(webApplicationContext)` | Testing with the loaded Spring MVC configuration and application context | Call `addFilters(...)` or `addFilter(...)` on the builder when filters must participate in MockMvc requests |

Standalone example:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilters(new CharacterEncodingFilter("UTF-8", true))
        .build();
```

Example using `WebApplicationContext`:

```java
@Autowired
private WebApplicationContext webApplicationContext;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .addFilters(characterEncodingFilter, auditFilter)
        .build();
```

`standaloneSetup` does not load the entire application configuration automatically. The test must supply the controllers, controller advice, converters, argument resolvers, and filters needed for the scenario. `webAppContextSetup` uses MVC configuration from the context, but when building MockMvc manually, explicitly register the filters the test must pass through rather than assuming any filter bean automatically appears in the builder's filter chain.

## 3. Registering One or More Filters

`MockMvcBuilders` returns a builder with filter registration methods:

- `addFilters(Filter... filters)` registers a group of filters applied to every request executed by MockMvc.
- `addFilter(Filter filter, String... urlPatterns)` registers a filter for the specified URL patterns.

Example registering multiple filters:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilters(encodingFilter, requestLoggingFilter, authenticationFilter)
        .build();
```

With this registration method, filters are placed into the chain in the order they are passed. Therefore, list order matters: `encodingFilter` runs before `requestLoggingFilter`, followed by `authenticationFilter`. When you need a readable and stable order, pass all filters in a single `addFilters(...)` call in the desired sequence.

Registering a filter by URL pattern:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilter(apiAuditFilter, "/api/*")
        .build();
```

In the example, `apiAuditFilter` is mapped to URLs matching `/api/*`. A request such as `/api/orders` matches the pattern; a request to `/health` does not. URL patterns are part of Servlet mapping configuration, so choose patterns matching the URLs the test sends.

When a filter serves only a group of endpoints, specific mapping helps the test express the filter's exact scope. When a filter should run for every endpoint in the test, `addFilters(...)` is more concise.

## 4. Filter Ordering and How Requests Traverse the Chain

A Servlet filter chain has two observable directions:

- **Inbound:** the first filter runs first. Then the filter calls `filterChain.doFilter(...)` to hand off to the next filter.
- **Outbound:** after downstream processing finishes, filters resume executing code after the `doFilter` call in reverse order.

Suppose `firstFilter` then `secondFilter` are registered; the trace typically looks like:

```text
first:before
second:before
controller
second:after
first:after
```

This ordering explains why an outer filter can measure the total elapsed time of inner filters and the controller, or wrap the response for post-processing once downstream work completes.

### Example Verifying Order with MockMvc

A simple filter recording entry and exit points:

```java
import java.io.IOException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

class TraceFilter extends OncePerRequestFilter {

    private final String name;
    private final List<String> trace;

    TraceFilter(String name, List<String> trace) {
        this.name = name;
        this.trace = trace;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {
        trace.add(name + ":before");
        try {
            filterChain.doFilter(request, response);
        } finally {
            trace.add(name + ":after");
        }
    }
}
```

Controller used in the test:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PingController {

    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
```

Test asserting the response and filter order:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class FilterOrderTests {

    @Test
    void filtersRunInRegistrationOrder() throws Exception {
        List<String> trace = new ArrayList<>();

        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new PingController())
                .addFilters(
                        new TraceFilter("first", trace),
                        new TraceFilter("second", trace))
                .build();

        mockMvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));

        assertEquals(Arrays.asList(
                "first:before",
                "second:before",
                "second:after",
                "first:after"), trace);
    }
}
```

This test verifies two things simultaneously: the endpoint still returns the expected content and the filter chain executes in registration order. `try/finally` in the filter ensures the exit trace is recorded even when downstream throws an exception; placing logging after `doFilter` without `finally` would skip that log when an exception occurs.

## 5. Ordering When Using Spring Boot

In Spring Boot tests, `@AutoConfigureMockMvc` has an `addFilters` attribute. Its default value is `true`, meaning filters from the application context are added to MockMvc. You can disable adding filters when the test only needs to verify MVC without running the filter chain:

```java
@WebMvcTest(PingController.class)
@AutoConfigureMockMvc(addFilters = true)
class PingControllerTests {

    @Autowired
    private MockMvc mockMvc;

    // Tests
}
```

To have the test skip filters configured in the context:

```java
@WebMvcTest(PingController.class)
@AutoConfigureMockMvc(addFilters = false)
class PingControllerWithoutFiltersTests {
    // Tests focused only on the MVC handler.
}
```

Disable filters only when that matches the intended test scope. For instance, if the application uses Spring Security, disabling filters can prevent test requests from traversing the security filter chain, causing results not to reflect the application's authentication/authorization behavior.

When using Spring Boot to register filters for the Servlet container, order is typically controlled with `FilterRegistrationBean#setOrder(...)` or `@Order` on the filter bean. Lower order values have higher priority and run earlier. Use `FilterRegistrationBean` when you need explicit URL patterns, dispatcher types, or order:

```java
@Bean
FilterRegistrationBean<AuditFilter> auditFilterRegistration() {
    FilterRegistrationBean<AuditFilter> registration =
            new FilterRegistrationBean<>(new AuditFilter());
    registration.addUrlPatterns("/api/*");
    registration.setOrder(20);
    return registration;
}
```

This is Spring Boot's filter registration configuration. If a test creates a MockMvc builder manually and calls `.addFilters(first, second)`, treat the order in that builder call as the order the test requires; do not rely on `@Order` to override an order passed explicitly there.

## 6. Filters Can Short-Circuit Requests

A filter is not required to call `filterChain.doFilter(...)`. It can generate a response itself and terminate the chain, such as when a request fails a precondition:

```java
public class HeaderGuardFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {
        if (request.getHeader("X-Client-Token") == null) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        filterChain.doFilter(request, response);
    }
}
```

The test can verify that the request is blocked:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new PingController())
        .addFilters(new HeaderGuardFilter())
        .build();

mockMvc.perform(get("/ping"))
        .andExpect(status().isForbidden());
```

When a filter blocks a request, subsequent filters and the controller are not invoked. If you need to confirm that, you can use a mock collaborator or a test flag to prove the handler did not run.

## 7. Checking Mapping and Avoiding Duplicate Registration

When a test shows a filter is not running, review the following points:

- Was the filter registered on the exact MockMvc instance the test is using?
- Does the request URL match the URL pattern passed to `addFilter(...)`?
- Is the test using `@AutoConfigureMockMvc(addFilters = false)`?
- Does the filter have conditions that skip the request, such as checking headers, paths, or dispatcher types?
- Was the filter registered twice—both through Boot configuration and via `addFilters(...)`—causing it to run repeatedly?

Duplicate registration can produce duplicate logs, alter the response, or cause invocation-count assertions to fail. Choose one clear registration mechanism for each filter in the test setup.

With `OncePerRequestFilter`, the filter is designed by default to avoid running multiple times within a single request dispatch. Even so, behavior across async dispatches or error dispatches also depends on the relevant hooks and dispatcher types. If a test involves async requests, test that dispatch flow separately rather than inferring from a normal synchronous request.

## 8. Practical Scenarios

| Need | Suggested Setup | What to Assert |
|---|---|---|
| Every request must use UTF-8 encoding | Register `CharacterEncodingFilter` via `addFilters(...)` | Request/response encoding or returned Vietnamese content |
| Only API endpoints need auditing | Use `addFilter(auditFilter, "/api/*")` | Filter runs for `/api/...` and does not run for URLs outside the pattern |
| Verify authentication runs before controller | Register the security filter chain in MockMvc | Unauthenticated requests are rejected; valid requests reach the handler |
| Measure or trace the entire request | Place trace filter before the filters to observe | Trace shows the expected inbound/outbound order |
| Test controller without considering filters | With Spring Boot, consider `addFilters = false` | Assertions reflect only the handler and MVC configuration in test scope |

## 9. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| Filter is not invoked | Not registered in MockMvc or URL does not match mapping | Use `addFilters(...)` or fix the URL pattern |
| Filter runs after another filter unexpectedly | Order passed to the builder is wrong | Reorder the arguments in `addFilters(...)` |
| Filter runs twice | Registered via multiple mechanisms or multiple dispatches | Remove duplicate registration; inspect dispatcher types |
| Controller is not invoked | Filter blocked the request or did not call `filterChain.doFilter(...)` | Inspect blocking conditions and the forwarding branch |
| Boot test lacks application's security behavior | `addFilters` is disabled or security filter is absent from test context | Enable filter registration and load the proper security configuration |
| Filter exit log is missing on error | Code after `doFilter` is not inside `finally` | Use `try/finally` when cleanup or exit logging is required |

## 10. Takeaways

Register filters for MockMvc using `addFilters(...)` when a filter applies to all requests, or `addFilter(filter, urlPatterns...)` when restricting by URL. With manual builders, registration order determines the order filters enter the chain. Filters run pre-downstream logic in registration order and post-downstream logic in reverse order. In Spring Boot, `@AutoConfigureMockMvc(addFilters = true)` brings filters from the application context into MockMvc; filter order in Boot configuration can be controlled via `FilterRegistrationBean` or `@Order`. Test the filter chain with real MockMvc requests to ensure tests run the intended configuration.

