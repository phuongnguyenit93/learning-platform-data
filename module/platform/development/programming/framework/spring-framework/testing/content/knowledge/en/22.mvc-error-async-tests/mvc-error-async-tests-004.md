# Testing the Filter Chain and Request Rejection Paths

In a Spring MVC application, a request can be rejected before `DispatcherServlet` ever calls a controller. Servlet filters, Spring Security, and request-protection components can check authentication credentials, access permissions, CSRF tokens, CORS, or application-specific rules. Consequently, testing controllers in isolation is not enough to prove that invalid requests are properly blocked.

`MockMvc` can run requests through the filters registered in the test environment. When configured properly, tests can verify which filters executed, which paths allow the request through, which paths return a rejection response, and whether the controller was inadvertently invoked.

## 1. How Does a Request Traverse the Filter Chain?

In a Servlet application, filters are invoked before the target servlet. A request passes through the filter chain in registration order; each filter can process the request, modify the response, pass the request to the next filter, or terminate the chain.

```text
HTTP request
    |
    v
Servlet container
    |
    v
Servlet Filter A
    |
    v
DelegatingFilterProxy
    |
    v
Spring Security FilterChainProxy
    |
    v
Matching SecurityFilterChain
    |
    +--> Security filters
    |       - SecurityContext
    |       - Authentication
    |       - CSRF
    |       - Authorization
    |
    v
DispatcherServlet
    |
    v
Controller
```

This is a high-level diagram. An application can have multiple Servlet filters before or after Spring Security; their exact positions depend on registration method and ordering configuration. `DelegatingFilterProxy` bridges from the Servlet container to a Spring-managed filter bean. In Spring Security, that bean is typically `FilterChainProxy`.

`FilterChainProxy` can hold multiple `SecurityFilterChain` instances. For each request, it selects the first chain whose `securityMatcher` matches. Inside that chain, security filters run in the order arranged by Spring Security. If a filter rejects the request, downstream filters and the controller may not be invoked.

This creates two selection layers to distinguish:

- `securityMatcher(...)` determines which `SecurityFilterChain` handles the request.
- `requestMatchers(...)` inside `authorizeHttpRequests(...)` determines the authorization rules applied within the selected chain.

The declaration order of authorization rules matters: Spring applies the first matching rule. Broad catch-all rules like `anyRequest()` are usually placed last.

## 2. Common Rejection Paths

A request can be blocked for many reasons. Each reason can produce a different status and should be tested separately.

| Situation | Typical result | Handling component |
|---|---|---:|
| Unauthenticated access to a protected endpoint | `401 Unauthorized` or `302` login redirect depending on config | Authentication entry point |
| Authenticated but lacking permission | `403 Forbidden` | Access denied handler |
| Missing or invalid CSRF token on a protected request | `403 Forbidden` | `CsrfFilter` |
| Disallowed origin in CORS preflight | Typically `403 Forbidden` | CORS processing/filter |
| Invalid API key, tenant, or request signature | Per contract, typically `401` or `403` | Custom filter |
| Rate limit exceeded | Can be `429 Too Many Requests` | Rate limiting filter or gateway |

Do not collapse all cases into a generic assertion like `is4xxClientError()`. An endpoint should return `401` when unauthenticated and `403` when the user is authenticated but lacks permission. If form login is configured, an unauthenticated request may be redirected to the login page instead of receiving `401`; tests must reflect the application's authentication entry point.

## 3. Configuring Spring Security for Test Paths

The example below secures `/api/**` endpoints. The public endpoint allows anonymous access, the admin endpoint requires the `ADMIN` role, and remaining endpoints require an authenticated user. HTTP Basic is enabled so requests without credentials receive a `401` response in this API example.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

CSRF remains enabled by default. This is intentional so tests can verify the path that rejects state-changing requests missing a token. For browser/session applications, do not disable CSRF just to make tests easier to run. If an API uses non-cookie bearer tokens and has an appropriate CSRF policy, CSRF configuration may differ; base it on how credentials are automatically sent by the browser.

Example controller with corresponding endpoints:

```java
@RestController
@RequestMapping("/api")
class ApiController {

    private final OrderService orderService;

    ApiController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/admin/report")
    String report() {
        return "admin report";
    }

    @PostMapping("/orders")
    ResponseEntity<Void> createOrder() {
        orderService.create();
        return ResponseEntity.created(URI.create("/api/orders/42")).build();
    }
}
```

The tests below focus on whether the filter chain permits or rejects requests before the controller executes business logic.

## 4. Testing SecurityFilterChain with MockMvc

With Spring Boot, `@AutoConfigureMockMvc` adds filters from the application context to `MockMvc` by default. Thus, if the application has a Spring Security filter chain, `MockMvc` requests pass through that security chain.

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityFilterChainTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void permitsPublicEndpointWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());
    }

    @Test
    void rejectsAnonymousRequestToProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void rejectsAuthenticatedUserWithoutAdminRole() throws Exception {
        mockMvc.perform(get("/api/admin/report"))
                .andExpect(status().isForbidden())
                .andExpect(authenticated());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void permitsUserWithAdminRole() throws Exception {
        mockMvc.perform(get("/api/admin/report"))
                .andExpect(status().isOk())
                .andExpect(authenticated());
    }

    @Test
    @WithMockUser
    void rejectsStateChangingRequestWithoutCsrfToken() throws Exception {
        mockMvc.perform(post("/api/orders"))
                .andExpect(status().isForbidden());

        verify(orderService, never()).create();
    }

    @Test
    @WithMockUser
    void acceptsStateChangingRequestWithValidCsrfToken() throws Exception {
        mockMvc.perform(post("/api/orders").with(csrf()))
                .andExpect(status().isCreated());

        verify(orderService).create();
    }
}
```

These tests verify distinct paths:

1. Public request passes through the security chain and is permitted.
2. Protected request without authentication is rejected with `401`.
3. Logged-in user lacking the required role is rejected with `403`.
4. User with the matching role is permitted access.
5. POST request missing a CSRF token is blocked before reaching the service.
6. POST request with a valid CSRF token reaches the controller and service.

`@WithMockUser` creates an `Authentication` for the test. It is suitable for testing authorization rules, but does not test password verification, JWT decoding, or HTTP Basic credential parsing. If the goal is to test real authentication, send credentials in the request, such as `.with(httpBasic("alice", "secret"))`, and configure the corresponding `UserDetailsService` or `AuthenticationProvider`.

The `spring-security-test` dependency must be present on the test runtime classpath to use `@WithMockUser`, `csrf()`, `httpBasic()`, and Spring Security Test request/result postprocessors:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

## 5. Testing a Custom Servlet Filter

Beyond Spring Security, an application may have custom filters to check tenants, API keys, correlation IDs, or rate limits. A filter can terminate a request without calling `FilterChain.doFilter`.

Example filter requiring the `X-Tenant` header to have the value `acme`:

```java
import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

class TenantHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        if (!"acme".equals(request.getHeader("X-Tenant"))) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Unknown tenant");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
```

When the header is invalid, the filter writes a `403` response and returns. If it still called `filterChain.doFilter`, the downstream controller could continue running and the request would no longer be properly blocked.

### Testing the Filter Standalone

You can test both branches using Servlet mock objects and a `FilterChain` that records whether the filter forwarded the request:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class TenantHeaderFilterTest {

    private final TenantHeaderFilter filter = new TenantHeaderFilter();

    @Test
    void stopsChainWhenTenantHeaderIsMissing() throws Exception {
        var request = new MockHttpServletRequest("GET", "/tenant/data");
        var response = new MockHttpServletResponse();
        var chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response,
                (servletRequest, servletResponse) -> chainCalled.set(true));

        assertEquals(403, response.getStatus());
        assertFalse(chainCalled.get());
    }

    @Test
    void continuesChainWhenTenantHeaderIsValid() throws Exception {
        var request = new MockHttpServletRequest("GET", "/tenant/data");
        request.addHeader("X-Tenant", "acme");
        var response = new MockHttpServletResponse();
        var chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response,
                (servletRequest, servletResponse) -> chainCalled.set(true));

        assertTrue(chainCalled.get());
    }
}
```

This is a unit test for the filter's logic. It verifies whether the filter calls the next chain, but does not prove the filter is registered with the right URL pattern, dispatcher type, or ordering in the application. To test the filter participating in an MVC request, attach it to `MockMvc`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new TenantController())
        .addFilters(new TenantHeaderFilter())
        .build();

mockMvc.perform(get("/tenant/data"))
        .andExpect(status().isForbidden());
```

`standaloneSetup` does not automatically load all filters from the application context. Any filters under test must be added explicitly with `addFilters(...)`. For the real running application, verify the filter is registered with the intended URL mapping and order.

## 6. Ensuring Filters Actually Run in MockMvc

A common reason security tests give misleading results is that filters are not included in `MockMvc`.

With Spring Boot:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FilterIntegrationTest {
    // MockMvc receives Filters from the application context by default.
}
```

`@AutoConfigureMockMvc` has an `addFilters` attribute, which defaults to `true`. If you set `@AutoConfigureMockMvc(addFilters = false)`, filters in the application context will not be added to the `MockMvc` chain. The test can then call straight into the controller and bypass Spring Security or custom filters.

When building `MockMvc` manually from a `WebApplicationContext`, you can apply the Spring Security configurer:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` integrates `FilterChainProxy` and enables security testing utilities. If you build `standaloneSetup` manually, you must add filters or the security chain via appropriate configuration; merely injecting `MockMvc` does not guarantee security filters are always automatically active.

In `@WebMvcTest`, if the `SecurityFilterChain` configuration lives outside the slice's component scan scope, import it with `@Import(...)`. If a test intentionally disables filters, understand that it only tests the MVC handler, not filter rejection paths.

## 7. Testing Multiple SecurityFilterChains

An application may split security policies by path—for instance, APIs using bearer tokens while admin pages use form login. When multiple `SecurityFilterChain` beans exist, `@Order` and `securityMatcher` determine which chain is evaluated first and which matches the request.

Example configuring two chains:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/api/public/**").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/**")
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Requests to `/api/orders` are handled by the first API chain. Requests to `/dashboard` do not match the API chain, so evaluation continues and the web chain handles them. If the broad `/**` chain were placed first, the API chain might never be selected.

When testing multiple chains, create at least one representative request per zone and assert the chain-specific behavior. For example, an anonymous API request should receive `401`, whereas an anonymous web request might receive a `302` redirect to the login page. If both receive the same result, recheck matchers and chain ordering.

## 8. Checking Filter Ordering and Short-Circuit Paths

Filter order affects when a request is authenticated, logged, CSRF-checked, or rejected. Spring Security provides methods like `addFilterBefore`, `addFilterAfter`, and `addFilterAt` to position custom filters relative to built-in security filters.

Example:

```java
http.addFilterBefore(apiKeyFilter, UsernamePasswordAuthenticationFilter.class);
```

When a filter depends on a value produced by an earlier filter, the test must verify that ordering. You can observe a header or a test-only event to confirm a filter ran; avoid relying on internal details that are not part of the application's contract.

A proper rejection path typically has two properties:

1. A response is created with the status, headers, and body specified by the contract.
2. Downstream components are not executed.

For a controller calling a service, you can verify the service is never called:

```java
mockMvc.perform(post("/api/orders"))
        .andExpect(status().isForbidden());

verify(orderService, never()).create();
```

This is a crucial assertion because merely asserting `403` does not prove business logic was prevented from running. A filter could set a status code and still call down the chain; verifying interactions catches that bug.

## 9. CORS, CSRF, and Requests Rejected Before the Controller

### CSRF

When CSRF is enabled, state-changing requests such as POST, PUT, PATCH, or DELETE typically require a valid token. Tests should cover both missing-token and valid-token cases:

```java
mockMvc.perform(post("/api/orders"))
        .andExpect(status().isForbidden());

mockMvc.perform(post("/api/orders").with(csrf()))
        .andExpect(status().isCreated());
```

This snippet assumes the request already has valid authentication and the endpoint is authorized. If the request is unauthenticated, the result can depend on filter order and exception handling configuration; isolate each condition to pinpoint the exact cause of rejection.

You can test an invalid token with `.with(csrf().useInvalidToken())`. This test confirms that both missing and wrong tokens are rejected.

### CORS Preflight

Browsers may send an `OPTIONS` request before the actual request to ask whether the server permits the intended origin, method, and headers. Preflight tests must send the corresponding headers:

```java
mockMvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, "https://client.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
        .andExpect(header().exists(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS));
```

If the origin or method is disallowed, the test must verify that the response is rejected according to the CORS configuration. Ensure CORS is processed before Spring Security authorization in your application setup; if preflight requires logging in first, browsers will be unable to execute the actual request.

## 10. Dispatcher Types, Async, and Error Dispatch

Servlet filters can be mapped for dispatcher types such as `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, and `INCLUDE`. A filter registered only for `REQUEST` may not execute during another dispatch type.

`OncePerRequestFilter` controls running once per request and skips async dispatches as well as error dispatches by default via its corresponding check methods. If a filter needs to run on those branches, consider overriding `shouldNotFilterAsyncDispatch()` or `shouldNotFilterErrorDispatch()` and ensure its registration includes the needed dispatcher types.

When an MVC endpoint returns an asynchronous result, `MockMvc` can use `asyncDispatch(...)` to inspect the final result. If the goal is to verify a filter ran during `ASYNC` dispatch, record invocation counts or dispatch state in the test and configure the filter accordingly. Do not infer from a passing async test that every filter ran across all dispatcher types.

Similarly, an error dispatch may traverse a different filter path than the original request. When an application has a custom error filter, test the error handling path separately and avoid accidentally processing an error twice.

## 11. Common Mistakes When Testing the Filter Chain

### Disabling All Filters in Tests

`@AutoConfigureMockMvc(addFilters = false)` makes tests skip filters. This may be fine for a controller-focused test, but not when the goal is to test authorization, CSRF, or custom filters. Use the default configuration or add the required filters.

### Using Standalone MockMvc and Expecting Spring Security to Run

`MockMvcBuilders.standaloneSetup(...)` does not automatically load the full application context or security chain. Add filters via `addFilters(...)` or use `webAppContextSetup(...)` with `springSecurity()` when testing the application's real security context.

### Checking Only the Status Without Checking That the Chain Stopped

A `403` response alone does not prove the controller was not called. Verify no interactions on the service/controller on rejection paths, especially for POST/PUT/DELETE.

### Confusing 401 and 403

`401` relates to authentication; `403` relates to access permissions of an authenticated principal or another rejection policy like CSRF. However, form login may redirect `302`, and custom entry points may alter the response. Write assertions based on the actual configuration.

### Using `@WithMockUser` to Conclude Passwords or Tokens Are Valid

`@WithMockUser` sets a principal for the test and bypasses credential verification. To test Basic authentication, a JWT decoder, or an API key, send real credentials per the application's mechanism and verify the authentication provider or filter handles them.

### Registering a Custom Filter Twice

A filter registered directly with the Servlet container and also added to a `SecurityFilterChain` can run twice. This can produce duplicate logs, read the body multiple times, or reject requests unexpectedly. Choose a single owner for registration and test how many times the filter executes. If the filter belongs solely to the Spring Security chain, configure it so the container does not register it a second time.

### Failing to Test Multiple SecurityFilterChains

A test covering only an endpoint in the first chain can miss a catch-all chain accidentally intercepting requests. With multiple chains, test representative paths for each chain and their specific rejection branches.

### Assuming `@ControllerAdvice` Handles All Filter Errors

Filters run before `DispatcherServlet`, so exceptions thrown in a filter do not automatically pass through `@ControllerAdvice`. Spring Security has dedicated filters to handle authentication and access denied exceptions within the security chain. For custom filters, proactively convert errors into responses or use an error-handling mechanism appropriate for the Servlet layer.

## 12. Layered Testing Strategy

Not every filter needs the same type of test. You can split testing across three layers:

| Layer | Tools | What is verified |
|---|---|---|
| Filter unit test | `MockHttpServletRequest`, `MockHttpServletResponse`, fake `FilterChain` | Allow/reject conditions, status, headers, and whether the next chain is called. |
| MVC/security integration test | `MockMvc` with real filter chain in application context | Registration in test context, matchers, security ordering, authentication, authorization, CSRF, and pre-controller responses. |
| Server/container test | `@SpringBootTest(RANDOM_PORT)` and HTTP client | Registration and mapping in embedded container, dispatcher behavior, and real HTTP interaction. |

Unit tests verify filter logic quickly. `MockMvc` verifies how filters cooperate with Spring MVC and Spring Security. Server tests add evidence about the Servlet container and HTTP transport when those behaviors carry significant risk.

## 13. Checklist for Filter and Rejection Path Tests

- [ ] Are the filters under test actually included in `MockMvc`?
- [ ] Does the test hit the intended `SecurityFilterChain` for the requested URL?
- [ ] Are the order of `SecurityFilterChain`s and request matchers correct?
- [ ] Are both public and protected endpoints tested?
- [ ] Are anonymous requests distinguished from authenticated users lacking permissions?
- [ ] Are missing, invalid, and valid CSRF tokens tested when CSRF is enabled?
- [ ] Is it verified that a custom filter stops the chain when rejecting a request?
- [ ] Is it verified that the controller/service is not called on rejection paths?
- [ ] When using `@WithMockUser`, does the test avoid claiming it verified real credentials?
- [ ] If multiple chains exist, is a representative request tested for each chain?
- [ ] If a filter depends on async/error dispatch, are dispatcher types and `OncePerRequestFilter` policies tested?
- [ ] If Servlet container verification is needed, is there an appropriate real-server test?

Testing the filter chain must prove both sides of the decision: valid requests are forwarded properly, and invalid requests are blocked before business logic runs. Combining unit tests for custom filters with `MockMvc` integration tests for Spring Security catches matcher, filter-ordering, authentication, authorization, and CSRF bugs right inside the application's pipeline.
