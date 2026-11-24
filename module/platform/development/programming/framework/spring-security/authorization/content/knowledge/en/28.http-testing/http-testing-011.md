# Verifying Status Codes, Error Responses, and Non-Execution of Business Logic

When testing an HTTP endpoint protected by Spring Security, merely seeing **401** or **403** is not enough. A meaningful test must simultaneously prove three things: **the right HTTP status**, **an error response matching the API contract**, and **that the business processing path is not invoked when access is denied**. This is an HTTP-boundary testing lesson in the **Spring Security – authorization** module, with Servlet/Spring MVC examples using MockMvc, JUnit 5, and Mockito.

## 1. Three Independent Pieces of Evidence to Verify

| Evidence | What to check | Why it is necessary |
| --- | --- | --- |
| HTTP status | 401, 403, 200, 204 per scenario | Informs the client of the request outcome per protocol. |
| Error response | Content-Type, application error code, message, required headers | Client receives a consistent structure; avoids leaking stack traces or sensitive data. |
| Non-execution of business logic | Service/command/repository is not invoked on blocked branches | Prevents state mutations, unauthorized queries, and side effects. |

**401 Unauthorized** usually indicates the request is not validly authenticated. **403 Forbidden** usually indicates the identity is authenticated but lacks permission; 403 can also result from a missing/invalid CSRF token. Actual behavior depends on the authentication mechanism: form-login apps may return **302** to the login page, whereas REST APIs using Basic/Bearer usually return **401**. Therefore, tests must follow the configured API contract rather than forcing one status code on every app.

With HTTP Basic, a 401 response needs an appropriate **WWW-Authenticate** header. For apps using Bearer tokens, testing JWT validation, expired tokens, and challenge headers is another testing layer; a simulated user via `@WithMockUser` does not prove real token verification.

## 2. Interception Points in the HTTP Processing Flow

A Servlet request traverses **SecurityFilterChain** before reaching **DispatcherServlet/Controller**. When an **authorizeHttpRequests** rule denies a request, the normal HTTP handler has not run yet. Spring Security routes authentication or authorization failures to the appropriate error handler, such as **AuthenticationEntryPoint** (401) or **AccessDeniedHandler** (403). Only if the request is accepted does the controller invoke the business service.

~~~mermaid
flowchart LR
    A[HTTP request] --> B[SecurityFilterChain]
    B -->|Blocked| C[HTTP 401/403 + error response]
    B -->|Allowed| D[Controller]
    D --> E[Business service]
    E --> F[HTTP success]
~~~

This is why MockMvc **integrated with Spring Security filters** should be used to prove access control at the HTTP layer. Calling controller methods directly or building standalone MockMvc without security filters can make tests bypass the very layer under test.

Distinguish the interception point: with **`@PreAuthorize` on a service**, the controller may already have run, yet the service body is denied before executing; with **`@PostAuthorize`**, the method may already have executed before being denied. Thus, never deduce "403 means no side effects occurred". Identify the protection boundary and verify the corresponding collaborator/state accurately.

## 3. Minimum Scenario Matrix

Using the illustrative API: `GET /api/payments/{id}` reads info, `POST /api/payments/{id}/approve` performs approval; both require role **APPROVER**. Security enables default CSRF for state-changing requests.

| Request | User / condition | Expected status | Business evidence |
| --- | --- | --- | --- |
| GET /api/payments/p-100 | Unauthenticated | 401 + AUTH_REQUIRED | PaymentService not called. |
| GET /api/payments/p-100 | Authenticated, role VIEWER | 403 + ACCESS_DENIED | PaymentService not called. |
| GET /api/payments/p-100 | Role APPROVER | 200 + valid payload | findById called once. |
| POST /api/payments/p-100/approve | Role APPROVER but missing CSRF token | 403 | PaymentService not called. |
| POST /api/payments/p-100/approve | Role APPROVER with valid CSRF token | 204 | approve called once. |

Do not mix conditions: to test **missing permission on POST**, supply a valid CSRF token first so the CSRF filter does not block early; to test **CSRF**, keep a valid role to isolate the cause. Status 400 (invalid data), 404 (resource not found), or 500 (server error) does not automatically prove the service did not run; many cases require executing business logic before returning those codes.

## 4. Runnable Example with Java 17 and Spring Boot 3.3

The sample project uses Spring MVC + Spring Security 6.x. Place files at the paths shown below. Gradle is installed or the project has a Gradle Wrapper.

**settings.gradle**

~~~groovy
rootProject.name = 'http-security-test-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '0.0.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/httpsecurity/DemoApplication.java**

~~~java
package demo.httpsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/httpsecurity/PaymentService.java**

~~~java
package demo.httpsecurity;

public interface PaymentService {
    String findById(String id);
    void approve(String id);
}
~~~

**src/main/java/demo/httpsecurity/InMemoryPaymentService.java**

~~~java
package demo.httpsecurity;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
class InMemoryPaymentService implements PaymentService {
    private final Set<String> approvedIds = ConcurrentHashMap.newKeySet();

    @Override
    public String findById(String id) {
        return approvedIds.contains(id) ? "approved:" + id : "pending:" + id;
    }

    @Override
    public void approve(String id) {
        approvedIds.add(id);
    }
}
~~~

The in-memory implementation simply lets the project run standalone. In the HTTP test layer below, the service will be replaced with a Mockito mock to detect business invocations. In a real system, the service might update a database, call an API, or publish events; those are side effects that should also be verified in integration tests where appropriate.

**src/main/java/demo/httpsecurity/PaymentController.java**

~~~java
package demo.httpsecurity;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/payments")
public class PaymentController {
    private final PaymentService service;

    public PaymentController(PaymentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public String getPayment(@PathVariable String id) {
        return service.findById(id);
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<Void> approve(@PathVariable String id) {
        service.approve(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

**src/main/java/demo/httpsecurity/HttpSecurityConfig.java**

~~~java
package demo.httpsecurity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class HttpSecurityConfig {
    private static final AuthenticationEntryPoint UNAUTHORIZED =
            (request, response, exception) -> {
                response.setHeader(
                        HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo-api\"");
                writeError(response, 401, "AUTH_REQUIRED",
                        "Authentication required");
            };

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/payments/**").hasRole("APPROVER")
                .anyRequest().denyAll())
            .httpBasic(basic -> basic.authenticationEntryPoint(UNAUTHORIZED))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(UNAUTHORIZED)
                .accessDeniedHandler((request, response, exception) ->
                    writeError(response, 403, "ACCESS_DENIED",
                            "Permission denied")));
        // Keep default CSRF to test POST with/without token.
        return http.build();
    }

    private static void writeError(
            HttpServletResponse response, int status,
            String code, String message) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("""
                {"code":"%s","message":"%s"}
                """.formatted(code, message));
    }
}
~~~

The JSON error contract here is **explicitly declared**. Do not assume Spring Security generates these `code`/`message` fields automatically. In the sample, authentication and insufficient-permission errors from the authorization branch share uniform JSON; the CSRF filter has its own denial path, so the example checks status 403 for CSRF without asserting its body also contains `ACCESS_DENIED`. If all security errors must share one structure, configure and test every failure point.

## 5. HTTP Tests: Status, Body, Headers, and Zero Service Calls

**src/test/java/demo/httpsecurity/PaymentSecurityHttpTest.java**

~~~java
package demo.httpsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PaymentController.class)
@Import(HttpSecurityConfig.class)
class PaymentSecurityHttpTest {
    @Autowired
    private MockMvc mvc;

    @MockBean
    private PaymentService service;

    @Test
    void anonymousRequestReturns401AndNeverCallsBusiness() throws Exception {
        mvc.perform(get("/api/payments/p-100"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo-api\""))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("AUTH_REQUIRED"))
            .andExpect(jsonPath("$.message").value("Authentication required"));

        verifyNoInteractions(service);
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void insufficientRoleReturns403AndNeverCallsBusiness() throws Exception {
        mvc.perform(get("/api/payments/p-100"))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.message").value("Permission denied"));

        verifyNoInteractions(service);
    }

    @Test
    @WithMockUser(roles = "APPROVER")
    void authorizedGetCallsBusinessOnce() throws Exception {
        given(service.findById("p-100")).willReturn("pending:p-100");

        mvc.perform(get("/api/payments/p-100"))
            .andExpect(status().isOk())
            .andExpect(content().string("pending:p-100"));

        verify(service).findById("p-100");
        verifyNoMoreInteractions(service);
    }

    @Test
    @WithMockUser(roles = "APPROVER")
    void missingCsrfReturns403WithoutApproval() throws Exception {
        mvc.perform(post("/api/payments/p-100/approve"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(service);
    }

    @Test
    @WithMockUser(roles = "APPROVER")
    void validCsrfAllowsApproval() throws Exception {
        mvc.perform(post("/api/payments/p-100/approve").with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));

        verify(service).approve("p-100");
        verifyNoMoreInteractions(service);
    }
}
~~~

**Why is this testing approach valuable?**

1. **`@WebMvcTest`** builds the necessary web slice, **`@Import(HttpSecurityConfig.class)`** applies the exact URL rules illustrated, and Spring Boot's MockMvc registers the security filters. Thus, HTTP calls genuinely pass through authorization checks.
2. **`@WithMockUser(roles = "VIEWER")`** supplies an authenticated principal with authority `ROLE_VIEWER` to the test; **`hasRole("APPROVER")`** requires `ROLE_APPROVER`. For the anonymous case, the test omits `@WithMockUser`.
3. Status, Content-Type, header, and JSONPath assertions are independent of service verification. **`verifyNoInteractions(service)`** fails if the mock receives **any invocation** on a blocked branch; thus returning the right status while the controller still hits the service fails the test.
4. Success tests act as **positive controls**: with a valid role, the filter lets the request reach the controller and the real service is called exactly once. Writing only denied tests could let a "deny-everything" misconfiguration pass all tests.
5. For POST, **`.with(csrf())`** supplies a valid token in MockMvc. Missing the token blocks before calling `approve`. This separates CSRF testing from role testing.

In Spring Boot 3.3, **`@MockBean`** is the compatible choice. In newer Spring Boot versions, follow the bean mocking API provided by that release (such as `@MockitoBean`); do not mix annotations/versions arbitrarily. Mockito mocks are managed by Spring Boot across the test context; avoid leaking interaction state from one test to another.

Run in the project directory:

~~~bash
gradle test --tests demo.httpsecurity.PaymentSecurityHttpTest
~~~

If the project already has a Gradle Wrapper, use `./gradlew` on Unix/macOS or `gradlew.bat` on Windows with the same arguments. When configured properly, **all five tests should PASS**; expected HTTP results in order are **401, 403, 200, 403, and 204**. The test command does not start a standalone HTTP server; MockMvc constructs requests/responses inside the Spring test context.

## 6. Distinguishing "Mock Not Called" from "No Side Effects"

**`verifyNoInteractions(service)`** proves the controller did not call the `PaymentService` mock on blocked requests in this test suite. It **does not automatically** prove there were no database writes, message sends, external API calls, or async jobs in other components. Choose evidence matching the real architecture:

- **URL authorization before controller:** mock the service and assert `verifyNoInteractions`/`never` at the boundary right after security.
- **`@PreAuthorize` on service:** measure at the business body or repository; the controller may have run, yet the sensitive operation must be blocked.
- **`@PostAuthorize` or errors raised after processing:** never assume side effects were rolled back automatically; avoid using post-authorization as the sole guard for write operations.
- **Database, queue, external APIs:** add integration tests checking before/after state, record counts, spies, or suitable fakes; test rollback separately if using transactions.
- **Async processing:** await/dispatch and observe the full async lifecycle rather than concluding solely from an early response.

For example, a lone assertion like **`status().isForbidden()`** can PASS even if the service already ran and then threw `AccessDeniedException`. Therefore, inspect post-request state/collaborators and identify at which layer permissions are enforced.

## 7. Designing Reliable Error Tests

A proper error contract may specify **status**, **Content-Type**, **code**, **message**, **requestId**, or **`ProblemDetail`** fields. Concrete fields must match the real API; avoid writing tests relying on default bodies not guaranteed across framework versions. Assert meaningful long-lived values and avoid comparing entire JSON strings if field ordering is not part of the contract.

To keep error responses safe and usable:

- Never return stack traces, internal details, credentials, tokens, or data from the denied resource.
- Keep application error codes stable so clients can handle them; user-facing messages may be localized.
- For Basic authentication, check `WWW-Authenticate` on 401; for Bearer, test challenges per standard and actual resource server config.
- Distinguish 401/403 from authentication, roles, CSRF, and object-level permissions. In some APIs, 404 is used deliberately to avoid leaking resource existence; that must be a designed and tested contract.
- If there are multiple `SecurityFilterChain`s, choose URLs/matchers so tests actually hit the chain under evaluation.

**A common mistake:** using a default 403 as proof of "missing role". A POST without a CSRF token can be blocked before role rules are evaluated. When testing roles with POST, supply a valid token using `csrf()`, then verify role enforcement and non-execution of business logic.

**Another mistake:** disabling filters with `addFilters = false`, calling controllers directly, or mocking 403 outcomes. Those may help unit-test a controller, but they do not prove the authorization filter. Likewise, `@WithMockUser` checks decisions based on simulated principals/authorities; it does not check passwords, JWT signatures, or real OAuth2 logins.

## 8. Workflow to Apply to Other Endpoints

1. **Define the policy:** endpoint, HTTP method, authentication mechanism, role/authority, owner/tenant, and CSRF requirement.
2. **Define the response contract:** status per branch; headers; body or `ProblemDetail`; data that must never be disclosed.
3. **Select business verification points:** service, command handler, repository, events, or data state; mock minimally to detect unintended interactions.
4. **Build a negative + positive control matrix:** anonymous, insufficient permission, sufficient permission, missing/invalid CSRF if applicable, object-owner permissions.
5. **Run tests through the real filter chain:** MockMvc integrated with Spring Security; use mock principals for authorization tests and add separate tests for authentication/token mechanisms.
6. **Assert three dimensions:** status, error contract, no calls/side effects; on positive controls confirm business logic actually executes.
7. **Re-verify when policy changes:** changing URL matchers, roles, `SecurityFilterChain` order, or error handlers must cause relevant tests to catch unintended changes.

### Self-Check Understanding

- If unauthenticated GET returns 401 yet `verifyNoInteractions` fails, we have the right status but **failed to protect the business call**.
- If APPROVER POST returns 403 without `csrf()`, that is not enough proof the user lacks permission; it may be a CSRF rejection.
- If APPROVER receives 200 yet `findById` was never called, revisit the test's endpoint/control because it did not prove the right execution path.
- If the service already updated the database before returning 403, inspect **where authorization is applied, transactions, and where the error is raised**; never assume data automatically rolls back.

## Official Documentation

- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — MockMvc setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — running as a user: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- Spring Security — CSRF testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Boot 3.3 — testing web MVC: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
