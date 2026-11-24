# Testing FORWARD, ERROR, ASYNC, and Error-Handling Endpoints in Spring Security (Servlet)

> Scope: **HTTP authorization** testing of a Spring MVC application running on Servlet with Spring Security. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x (`jakarta.servlet`). This is a **Servlet**-side testing lesson and does not apply verbatim to WebFlux.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish an HTTP request from a client from internal **dispatches** (`REQUEST`, `FORWARD`, `ERROR`, `ASYNC`).
2. Explain when `SecurityFilterChain` and `AuthorizationFilter` are invoked on subsequent dispatches.
3. Write tests proving `FORWARD` does not accidentally open access to endpoints requiring higher permissions.
4. Write tests for error handling: original endpoints preserve their error codes, `/error` renders on `ERROR` dispatches yet does not become a public endpoint when called directly.
5. Test both phases of Spring MVC async and the presence of `SecurityContext` when running a `Callable`.
6. Know the limits of `MockMvc` and choose real servlet container tests when end-to-end behavior must be proven.

## 2. Understanding Requests and Dispatcher Types Correctly

A single external HTTP connection can pass through the servlet pipeline multiple times:

| `DispatcherType` | When it occurs | What to test |
| --- | --- | --- |
| `REQUEST` | Client sends the initial request | Authentication and authorization of the initial URL/HTTP method |
| `FORWARD` | App calls `RequestDispatcher.forward(...)` or forwards to an internal view | Whether **the forward target's** permissions remain protected |
| `ERROR` | Container dispatches to the error page/`/error` after an error or `sendError` | Whether the original error renders properly instead of being replaced by a new 401/403 |
| `ASYNC` | Servlet async completes and re-dispatches to produce the response | Permissions and security context during response completion/emission |
| `INCLUDE` | `RequestDispatcher.include(...)` | If `include` is used, define authorization rules too; do not infer from FORWARD |

Examples of processing flows—**not** three new HTTP requests from the client:

```text
GET /demo/forward (REQUEST, has USER permission)
  -> controller forward("/views/landing")
     -> /views/landing (FORWARD, check destination permission)
        -> HTTP 200

GET /demo/fail (REQUEST, has USER permission)
  -> controller sends 500 error
     -> /error (ERROR, render error)
        -> HTTP 500 to client

GET /demo/async (REQUEST, has USER permission)
  -> controller returns Callable, request switches to async
  -> Callable runs on another thread
  -> /demo/async (ASYNC dispatch, completes response)
     -> HTTP 200
```

Distinguish **two configuration layers**:

- **Servlet filter registration:** the container only invokes the Spring Security filter for registered dispatcher types. Spring Boot has the `spring.security.filter.dispatcher-types` property. In Boot 3.3–3.5, property docs list defaults `request,error,async,forward,include`; however, always check your actual version, overrides, and `FilterRegistrationBean`.
- **Authorization rules:** once a dispatch enters Spring Security, `authorizeHttpRequests(...)` and `dispatcherTypeMatchers(...)` decide permit/deny per request. `AuthorizationFilter` is designed to evaluate subsequent dispatches as well. Writing a matcher cannot make up for a dispatcher type missing from servlet filter registration.

Matcher order matters: **the first matching rule** decides access. `dispatcherTypeMatchers(ERROR).permitAll()` placed before `anyRequest().denyAll()` lets error dispatches proceed; **GET /error from a browser still has type REQUEST**, so it is not allowed merely because of the ERROR rule.

**Authorization warning:** the `dispatcherTypeMatchers(FORWARD, ERROR).permitAll()` pattern in Spring docs is useful when all forwards only render safe views. If the app can forward to `/admin/**` or sensitive business endpoints, `permitAll()` for **all** FORWARDs can bypass target URL checks. Test actual flows and relax permissions only within demonstrably safe bounds; the example below **does not** permit all FORWARDs.

## 3. Test Contract: What Counts as a PASS?

| Scenario | Expectation |
| --- | --- |
| Anonymous calls `GET /demo/forward` or `/demo/async` | 401 in the sample HTTP Basic config |
| USER calls `/demo/forward`, forwards to `/views/landing` | 200, body `VIEW_OK` |
| USER calls `/demo/forward-admin`, target is `/admin/report` | 403, **must not return** secret data |
| USER calls `/admin/report` directly | 403 |
| USER calls `/demo/async` | Async starts; after `asyncDispatch` returns 200 and expected principal |
| USER calls `/demo/fail` | 500 error response; `/error` renders error info rather than being wrongly blocked |
| Anonymous sends `GET /error` as a normal request | 401 per HTTP Basic and sample `denyAll` rule |
| Simulated request with `DispatcherType.ERROR` to `/error` | 500 per original status, proving the ERROR rule allows processing |

Code 401 is only the expectation of **the sample application using HTTP Basic**. With form login, unauthenticated requests may return 302; authenticated requests lacking permission usually return 403. Tests must follow the actual `AuthenticationEntryPoint`/`AccessDeniedHandler` rather than hardcoding 401 across all configs.

## 4. Sample Application for Running Tests

The following dependencies are needed in a Spring Boot project with a compatible plugin/BOM configuration:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The classes below share package `com.example.dispatch`. Create the entry point:

**`src/main/java/com/example/dispatch/DispatchDemoApplication.java`**

```java
package com.example.dispatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/dispatch/SecurityConfig.java`**

```java
package com.example.dispatch;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Only internal ERROR may render without login.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                // Sensitive destinations must keep their own rules, even when forwarded to.
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/demo/**", "/views/**").hasRole("USER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

There is no `dispatcherTypeMatchers(FORWARD).permitAll()`. If a USER attempts to forward to `/admin/report`, the destination still requires role ADMIN. `hasRole("USER")` maps to authority `ROLE_USER`; `hasRole("ADMIN")` maps to `ROLE_ADMIN`.

**`src/main/java/com/example/dispatch/DemoController.java`**

```java
package com.example.dispatch;

import java.io.IOException;
import java.util.concurrent.Callable;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoController {
    @GetMapping("/demo/forward")
    public void forwardView(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        request.getRequestDispatcher("/views/landing").forward(request, response);
    }

    @GetMapping("/demo/forward-admin")
    public void forwardAdmin(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        request.getRequestDispatcher("/admin/report").forward(request, response);
    }

    @GetMapping("/views/landing")
    public String landing() {
        return "VIEW_OK";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "TOP_SECRET";
    }

    @GetMapping("/demo/async")
    public Callable<String> async() {
        return () -> "ASYNC_OK:"
                + SecurityContextHolder.getContext().getAuthentication().getName();
    }

    @GetMapping("/demo/fail")
    public void fail() {
        throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Demo failure");
    }
}
```

`/demo/fail` uses `ResponseStatusException` to produce a 500 error. In a servlet container, `sendError` can trigger an `ERROR` dispatch to Spring Boot's default error page, usually at `/error`. An `@ExceptionHandler` returning `ResponseEntity` directly is a **different branch**: the error can be handled within Spring MVC without an `ERROR` dispatch. Choose matching test cases accordingly.

To keep the demo independent of Boot-version defaults, explicitly declare the filter dispatcher types:

**`src/main/resources/application.properties`**

```properties
spring.security.filter.dispatcher-types=request,error,async,forward,include
```

This is a servlet filter setting, **not** an `authorizeHttpRequests` rule. In real apps, inspect all custom `FilterRegistrationBean`s, `SecurityFilterChain`s, `securityMatcher`s, and servlet container deployment; never treat this properties line alone as proof of security.

Users for testing are provided separately so test passwords never enter production configuration.

**`src/test/java/com/example/dispatch/TestUsers.java`**

```java
package com.example.dispatch;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
class TestUsers {
    @Bean
    UserDetailsService testUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}pw")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}pw")
                .roles("USER", "ADMIN")
                .build()
        );
    }
}
```

`{noop}` stores passwords in plain text **for test fixtures only**; never use it for real accounts.

## 5. MockMvc: Testing Rules and the Async Lifecycle

`MockMvc` is very fast for checking security rules and request handling in Spring MVC. However, it runs on mock servlets **without a real container**. `forwardedUrl(...)` only verifies that a forward URL was requested; it **does not** prove the container executed the forward to the target handler or re-applied filters. Similarly, MockMvc usually does not automatically perform error-page dispatches after `sendError`. For async, `asyncDispatch` must be called explicitly.

**`src/test/java/com/example/dispatch/DispatchSecurityMockMvcTest.java`**

```java
package com.example.dispatch;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.RequestDispatcher;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestUsers.class)
class DispatchSecurityMockMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReachProtectedSource() throws Exception {
        mvc.perform(get("/demo/forward"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void forwardedUrlIsRecordedButDestinationIsNotExecuted() throws Exception {
        mvc.perform(get("/demo/forward"))
            .andExpect(status().isOk())
            .andExpect(forwardedUrl("/views/landing"));

        // Do not infer that destination handler /views/landing ran.
    }

    @Test
    @WithMockUser(roles = "USER")
    void simulatedForwardToAdminIsDenied() throws Exception {
        mvc.perform(get("/admin/report").with(req -> {
                req.setDispatcherType(DispatcherType.FORWARD);
                return req;
            }))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void asyncRequestCompletesWithTheExpectedPrincipal() throws Exception {
        MvcResult pending = mvc.perform(get("/demo/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("ASYNC_OK:alice"));
    }

    @Test
    void directRequestToErrorEndpointIsNotPublic() throws Exception {
        mvc.perform(get("/error"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void simulatedErrorDispatchCanRenderTheOriginal500() throws Exception {
        mvc.perform(get("/error").with(req -> {
                req.setDispatcherType(DispatcherType.ERROR);
                req.setAttribute(RequestDispatcher.ERROR_STATUS_CODE,
                    HttpStatus.INTERNAL_SERVER_ERROR.value());
                req.setAttribute(RequestDispatcher.ERROR_REQUEST_URI, "/demo/fail");
                return req;
            }))
            .andExpect(status().isInternalServerError());
    }
}
```

Explanation of key assertions:

- `@AutoConfigureMockMvc` inside `@SpringBootTest` uses the context's filter chain; `spring-security-test` supplies `@WithMockUser` and request post-processors. If building `MockMvcBuilders` manually, integrate `springSecurity()` or the appropriate filter chain.
- `with(req -> req.setDispatcherType(FORWARD))` creates **a mock request with type FORWARD** to test the matcher. It does not perform a real forward from the source URL, nor does it prove servlet mappings invoked the filter in a container.
- `asyncStarted()` confirms the handler returned async processing; `asyncDispatch(pending)` runs the completion phase. Asserting only 200 on the first request is incomplete.
- `SecurityContextHolder` inside `Callable` holding username `alice` is evidence that the context was propagated to the execution thread. Spring Security supports `Callable` integration in Spring MVC; with `DeferredResult` completed by an application-managed thread, context propagation is **not automatically equivalent**, requiring mechanisms like `DelegatingSecurityContextExecutor` and dedicated tests.
- `RequestDispatcher.ERROR_STATUS_CODE` is an error-dispatch attribute; simply calling `GET /error` **does not** represent `ERROR` because by default it is still `REQUEST`.
- If testing `POST`/`PUT`/`DELETE` with default CSRF, add `.with(csrf())` for valid requests and a test for missing/invalid CSRF tokens; never disable CSRF just to make tests pass.

## 6. Real Servlet Container: Proving Forward/Error/Async End-to-End

This test section is **mandatory when you need conclusions about authorization on real FORWARD and ERROR dispatches**. Start the server on a random port; `TestRestTemplate` sends HTTP externally while Tomcat/Jetty/Undertow handles internal dispatcher routing.

**`src/test/java/com/example/dispatch/DispatchSecurityHttpTest.java`**

```java
package com.example.dispatch;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestUsers.class)
class DispatchSecurityHttpTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void forwardToSafeViewSucceeds() {
        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .getForEntity("/demo/forward", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("VIEW_OK");
    }

    @Test
    void forwardMustNotBypassAdminAuthorization() {
        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .getForEntity("/demo/forward-admin", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(response.getBody()).doesNotContain("TOP_SECRET");
    }

    @Test
    void authorizedAdminCanReachForwardDestination() {
        ResponseEntity<String> response = http.withBasicAuth("admin", "pw")
            .getForEntity("/demo/forward-admin", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("TOP_SECRET");
    }

    @Test
    void asyncDispatchCompletesAndRetainsIdentity() {
        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .getForEntity("/demo/async", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("ASYNC_OK:reader");
    }

    @Test
    void errorDispatchPreserves500InsteadOfSecurityFailure() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .exchange("/demo/fail", HttpMethod.GET,
                new HttpEntity<Void>(headers), String.class);

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(response.getBody()).contains("\"status\":500");
    }

    @Test
    void directErrorUrlIsStillDenied() {
        ResponseEntity<String> response = http
            .getForEntity("/error", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
```

These tests make clear distinctions:

- `GET /demo/forward` must receive **the destination handler's body**, not just the forward name. The `forward-admin` test prevents privilege escalation; testing `GET /admin/report` directly alone is insufficient because it does not verify the FORWARD path.
- `GET /demo/fail` must produce a 500 error with `/error` JSON error fields. If a filter blocks error dispatch, the status/body will differ; inspect **body, status, logs, and dispatcher type** when debugging.
- `GET /error` sent from a client is a `REQUEST` and is blocked. Permitting internal error rendering does not mean exposing a public endpoint.
- `GET /demo/async` returns a body containing the identity from `Callable`, catching security context loss in worker threads.

Run tests using the created project's Gradle wrapper:

```bash
./gradlew test --tests '*DispatchSecurityMockMvcTest' --tests '*DispatchSecurityHttpTest'
```

On Windows PowerShell/cmd:

```powershell
.\gradlew.bat test --tests '*DispatchSecurityMockMvcTest' --tests '*DispatchSecurityHttpTest'
```

The examples above are self-contained fixtures for **app/test code**, while building requires the project's Spring Boot plugin, repositories, and dependency management config. Only consider tests PASSING after running against real dependency versions/containers; do not treat sample code as proof of execution in your environment.

## 7. Extended Cases to Distinguish

### 7.1. When Controllers Have `@ControllerAdvice` or `@ExceptionHandler`

An `@ExceptionHandler` catching errors and returning `ResponseEntity.status(500)...` can resolve the response directly on `REQUEST`, **without needing** a container ERROR dispatch. Tests for that handling path should assert HTTP status, error payload, absence of leaked exceptions/stack traces, and endpoint permissions. To test `DispatcherType.ERROR`, trigger conditions leading to `sendError` or real container error dispatch, or construct a deliberate ERROR mock.

### 7.2. When Async Requests Encounter Errors

A `Callable` throwing an exception and `DeferredResult.setErrorResult(...)` are usually processed by Spring MVC in the async redispatch phase; errors may pass through `@ExceptionHandler` or go to the container error page depending on handling. Test **all** of `asyncStarted()`, `asyncDispatch(...)`, error status/body, and permissions. If the app spawns its own threads/`CompletableFuture`/`DeferredResult`, do not assume `SecurityContextHolder` (typically `ThreadLocal`-based) propagates automatically; propagate the context safely and verify in tests.

### 7.3. When Multiple `SecurityFilterChain`s Exist

`securityMatcher(...)` selects which **filter chain** applies; `requestMatchers(...)` inside only selects **rules** within that chain. Each dispatch can have a different URI/path or different match. Verify that both the `REQUEST` and `FORWARD`/`ERROR`/`ASYNC` dispatches match the intended filter chain. Configuring `web.ignoring()` or excluding a path from filter chains drops other protections; prefer clearly scoped rules.

### 7.4. When Using Permit Rules for FORWARD

You may allow FORWARDs for specific identified internal views; however, test **sensitive destinations** and never use `dispatcherTypeMatchers(FORWARD).permitAll()` by default when the app can forward to higher-privilege business APIs. Never assume that because an initial request passed authorization, all subsequent internal targets have the same sensitivity.

### 7.5. When Logs or Tests Report Unexpected 401/403/500

Check in order:

1. Which `DispatcherType` does the actual request carry; is it a client request or an internal dispatch?
2. Does the servlet container invoke the Spring Security filter on that type (`spring.security.filter.dispatcher-types` and filter registration)?
3. Which `SecurityFilterChain` was selected; which matcher matched **first**?
4. Do the principal/authorities still exist during the dispatch/worker thread phase?
5. Was the error handled by an MVC resolver or routed to `/error`? Is there a recursive error dispatch?
6. Does the login mechanism use HTTP Basic, form login, bearer token, or a custom entry point? Determine the expected 401, 302, or 403 from that.

You can enable `logging.level.org.springframework.security=DEBUG` **in the test environment** to inspect the filter chain and access decisions; also observe request URI, dispatcher type, and response status without logging credentials/tokens.

## 8. Checklist Before Concluding Completion

- [ ] Test `REQUEST` for anonymous, USER, and ADMIN according to the rules.
- [ ] Test `FORWARD` to a normal view **and** forwarding to a higher-privilege endpoint; verify secret data is not leaked.
- [ ] Do not mistake MockMvc's `forwardedUrl` for proof that the container actually executed the target.
- [ ] Test `ERROR` with the right dispatcher type/attributes; test `/error` on `REQUEST` separately.
- [ ] Test both status **and body** for real errors, avoiding a 401/403 on the error page masking the root error.
- [ ] Test both phases `asyncStarted` → `asyncDispatch`, final body, and principal inside `Callable`.
- [ ] If using `DeferredResult`/custom threads, test `SecurityContext` propagation as well.
- [ ] Verify filter dispatcher mapping and authorization matcher order on your active Boot/Security version.
- [ ] Have at least one HTTP test with an embedded servlet container for real `FORWARD`/`ERROR` flows.

## 9. Official Reference Sources

- Spring Security — Authorize HttpServletRequests (authorization by dispatcher type): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot — Common Application Properties (`spring.security.filter.dispatcher-types`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Framework — MockMvc vs End-to-End Tests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/vs-end-to-end-integration-tests.html
- Spring Framework — Test Async Requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
- Spring Security — Spring MVC Async Integration: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html

**Pass criteria:** learners can prove via executable tests that an authorized `REQUEST` does not open a `FORWARD` path to sensitive endpoints, `ERROR` dispatches preserve the true error, and `ASYNC` completes with the expected identity and permissions.