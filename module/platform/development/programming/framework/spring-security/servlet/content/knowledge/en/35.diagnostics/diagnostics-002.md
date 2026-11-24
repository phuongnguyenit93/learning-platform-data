# Enabling DEBUG, TRACE, or Debug Mode in a Controlled Environment — Spring Security Servlet

## 1. The Problem: When HTTP Status Alone Is Not Enough to Diagnose

In a **Spring Security Servlet** application, the same HTTP symptom can stem from multiple mechanisms:

- **401 Unauthorized**: no valid `Authentication`, incorrect credentials, or an `AuthenticationEntryPoint` responded.
- **403 Forbidden**: the user is authenticated but unauthorized, **or** a state-changing request was blocked by CSRF protection, **or** another component denied it.
- **302 Redirect**: the web application redirects to form login, OAuth2/OIDC login, or another target; it is not synonymous with 401.
- **400 Bad Request**: the path was rejected by `HttpFirewall` or the servlet container; the fault is not necessarily in the Controller.
- **404 Not Found**: missing route, wrong context path/prefix, or another layer handled the request; not sufficient proof that `FilterChainProxy` ran.
- **200 OK** on a public endpoint without expected security headers: the request may have traversed a different filter chain, been bypassed entirely, or had headers overwritten by a proxy.

When such situations occur, **DEBUG/TRACE logging** helps observe **FilterChainProxy**, authentication, authorization, exception handling, method security, and request processing. However, enabling it too broadly can log sensitive information, generate massive logs, slow down the system, and violate data security policies.

**Goal of this guide:** know which log level to enable, on which logger, when to use Spring Security's web debug filter, how to analyze the logs, how to retest with controlled requests, and how to restore safe configuration after diagnosis.

The context is **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**, without WebFlux. Configuration syntax and example class names apply only to the corresponding supported versions; actual log output may vary across releases.

## 2. Distinguishing DEBUG, TRACE, and Web Debug Mode

### 2.1. Spring Boot/SLF4J Logger Levels

Spring Boot typically manages logs by category/package/class through the integrated logging framework (Logback by default with the starter). A logger has an effective level such as **INFO**, **DEBUG**, or **TRACE**.

| Level | Typically Useful Content | Cost and Caveats |
| --- | --- | --- |
| **INFO** | General events and important warnings | Suitable as a production baseline, but usually lacks filter-level detail |
| **DEBUG** | Security chain selection info, request being secured, some authN/authZ decisions | Increases log volume; exact detail depends on class/version |
| **TRACE** | Finer step-by-step detail, such as per-filter invocations or decision points | High log volume; enable only on narrow scopes and for short periods |
| **WARN/ERROR** | Warnings and errors | Insufficient to understand the full path of a successful or denied request |

**TRACE includes DEBUG messages along with TRACE messages from the enabled logger**. However, not every class logs at every level, and logs are not a stable API contract. Do not build test suites asserting a specific log sentence assuming Spring Security must always emit that exact phrase.

Enabling general logging:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

This generally causes loggers under **org.springframework.security** to emit DEBUG information, which does not mean logging full HTTP payloads; it also **does not guarantee** no secrets appear from other components.

To inspect filter chain details without enabling TRACE across the entire application:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Choose a narrow logger before widening—for example **org.springframework.security.web**, **org.springframework.security.authorization**, or **org.springframework.security.authentication**. In a real application, follow the logger names that actually appear to refine further rather than guessing that a package always emits one exact event type.

### 2.2. Spring Security Web Debug Filter: Different from TRACE Logger

Spring Security Servlet also has a **web security debug mode**, enabled via **WebSecurityCustomizer / WebSecurity.debug(true)** or an equivalent configuration such as **@EnableWebSecurity(debug = true)** in an appropriate configuration class.

This mode can create a **DebugFilter** with very detailed information about the request and security filter chain, helpful when you do not know which chain a request enters. **It carries a special safety warning: not for production environments.** Output may include headers, request details, or sensitive security information. It is **not** a neutral drop-in replacement for INFO logging.

Three distinct options:

| How to Enable | Meaning | Recommendation |
| --- | --- | --- |
| **logging.level.org.springframework.security=DEBUG** | Enables DEBUG for the logger category | First step when diagnosing; restrict by profile and duration |
| **logging.level.org.springframework.security.web.FilterChainProxy=TRACE** | Traces FilterChainProxy details | Test requests only and narrow logger scope |
| **web.debug(true)** or **@EnableWebSecurity(debug=true)** | Enables Spring Security Web's debug filter | Isolated local/staging only; never enable by default in production |

**Spring Boot `--debug` / `debug=true` is something else.** It primarily expands Spring Boot's own diagnostics, including the auto-configuration condition evaluation report and certain core loggers; you cannot infer that Spring Security filters have TRACE or `DebugFilter` enabled. For security diagnostics, configure **logging.level...** or web debug explicitly.

### 2.3. There Is No Safe “Single DEBUG Button” for Every Issue

A 401 may require authentication loggers; a permission-based 403 requires authorization loggers; a request failing to select a chain calls for `FilterChainProxy` and `securityMatcher`; a firewall-blocked request may require **org.springframework.security.web.firewall** or container logs; and a request that never reached the application produces no Spring Security logs at all.

**The sound strategy** is starting from the HTTP status, a minimal reproducible request, identifying the suspected layer, and then raising the log level on the matching category. Never enable **logging.level.root=TRACE** or dump all headers/tokens into logs “just in case”.

## 3. What Is a Controlled Environment?

“Enable only in a controlled environment” must have concrete operational rules, not just adding the word **DEBUG** to a profile name.

An appropriate diagnostic environment requires:

1. **Access isolation**: local machine, dedicated staging, or test environment with network/identity restrictions; no unrelated public traffic.
2. **Test data**: synthetic accounts, test secrets/tokens, non-production PII; avoid production data copies.
3. **Small logger scope**: one package/class for a short window rather than the entire root logger.
4. **Collection limits**: do not paste detailed logs into public issue trackers, chat channels, or broadly readable dashboards; govern retention and access.
5. **No credential logging**: never log `Authorization`, `Cookie`, `Set-Cookie`, tokens, session IDs, passwords, OTPs, OAuth2 `code`/`state`, or sensitive request bodies. Do not assume default logging masks every field.
6. **Rollback plan**: record the previous log level, who enabled it, when it was turned on, when it will be turned off, and how to verify it is off.
7. **Incident response plan**: if a token/session/secret is accidentally logged, treat it as an event requiring log containment and revocation/rotation review, not merely deleting a console line.

**Do not enable Spring Security's DebugFilter in production** simply to handle an urgent incident. Prefer less intrusive telemetry such as request IDs, HTTP status codes, aggregated security events, and tightly scoped loggers. For production environments, any log change requires clear approval processes and data boundaries.

## 4. Configuring a Diagnostic Profile Without Affecting Defaults

### 4.1. Separating Log Config from Production application.yml

Keep **src/main/resources/application.yml** for standard settings without enabling application-wide TRACE. Create a dedicated file:

**src/main/resources/application-security-diagnostics.yml**

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Spring Boot applies this file when the **security-diagnostics** profile is active. Separating the profile makes it clear to the team that the config is diagnostics-only; however, **a profile does not create a security boundary by itself**. A profile name does not prevent accidental deployment to production.

Run in a project with Gradle wrapper:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=security-diagnostics'
~~~

On Windows PowerShell (in the project root directory):

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=security-diagnostics"
~~~

**Do not** change production `application.yml` to TRACE and forget to revert it. For an authorization failure, you can replace `FilterChainProxy` TRACE with the narrower **org.springframework.security.authorization** logger. Exact logger names and event details depend on the Spring Security features in use.

### 4.2. Enabling a Logger Temporarily via Startup Argument

When only one category is needed:

~~~bash
./gradlew bootRun --args='--logging.level.org.springframework.security=DEBUG'
~~~

Or enable TRACE solely for `FilterChainProxy` during a test run:

~~~bash
./gradlew bootRun --args='--logging.level.org.springframework.security.web.FilterChainProxy=TRACE'
~~~

This is **startup configuration**; the example arguments alter the app started in that run, not a separate already-running process. Be careful in k8s/CI environments: arguments may persist in deployment manifests, process metadata, or job logs. Never pass secrets on the command line.

### 4.3. Enabling Web Debug Only in an Isolated Profile

If `DebugFilter` output is genuinely needed, a Spring configuration can look like:

**src/main/java/com/example/securitydiagnostics/WebDebugOnlyConfiguration.java**

~~~java
package com.example.securitydiagnostics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Configuration(proxyBeanMethods = false)
@Profile("security-debug")
public class WebDebugOnlyConfiguration {

    @Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        // Isolated local/staging only, DO NOT enable in production.
        return web -> web.debug(true);
    }
}
~~~

In a Spring Boot Servlet environment with proper Spring Security Web configuration, the `WebSecurityCustomizer` bean is applied by the framework to **WebSecurity**. If using this profile, verify that the debug filter actually runs and review the output locally in a test environment. Never include the **security-debug** profile in the system's default profiles.

When reproducing by activating both profiles:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=security-diagnostics,security-debug'
~~~

**Warning:** The web debug filter can expose sensitive information from requests or `SecurityContext`. Do not ship these logs to centralized logging without access controls, retention policies, and proper filtering. Even if the logging framework masks certain fields in one version, that does not guarantee all records are harmless.

### 4.4. Why Boot --debug Is Not a Security Diagnostic Check

The command:

~~~bash
./gradlew bootRun --args='--debug'
~~~

can provide an auto-configuration condition report or extra framework logs, useful when a `SecurityFilterChain` bean is not created as expected. However, if you want to observe individual filters executing, **`--debug` alone is insufficient grounds to draw conclusions**. Inspect targeted Spring Security loggers and the web debug option in a controlled environment when needed.

## 5. Demo App: Spring Boot 3.x / Security 6.x / Java 17+

To show the difference between authentication and authorization, create three endpoints:

- **GET /public/ping**: public, returns **pong**.
- **GET /private/me**: requires login, returns the username.
- **GET /private/admin**: requires role **ADMIN**.

The example uses **HTTP Basic** and a dummy user so no IdP/SSO/JWT setup is required. In a real system, the login mechanism may differ; the principles around loggers and filter chains still apply, though exact log entries and entry points will vary.

### 5.1. Gradle Dependencies

In **build.gradle** of a Boot 3.x project that already has Gradle wrapper:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ensure the project uses Java 17+ and configures Spring Boot plugin/dependency management matching your version. The block above is the **dependencies** section to add, not a complete standalone `build.gradle` file.

### 5.2. Main Application and SecurityFilterChain

File **src/main/java/com/example/securitydiagnostics/SecurityDiagnosticsApplication.java**:

~~~java
package com.example.securitydiagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDiagnosticsApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/private/me").authenticated()
                        .requestMatchers(HttpMethod.GET,
                                "/private/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // User for local testing only; never expose publicly.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-demo-password"))
                        .roles("USER")
                        .build());
    }
}

@RestController
class DiagnosticController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/private/me")
    String currentUser(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/private/admin")
    String admin() {
        return "admin only";
    }
}
~~~

**Key points from the configuration:**

1. **Spring Security filters** still apply to public endpoints. **`permitAll()`** is not **`web.ignoring()`**: publicly accessible requests can still receive Spring Security's security headers.
2. Endpoint **/private/me** requires `Authentication`; missing credentials in an HTTP Basic configuration typically result in **401**.
3. User `alice` has **ROLE_USER** and not **ROLE_ADMIN**. Therefore GET **/private/admin** with valid Basic credentials is expected to receive **403**.
4. **There are no state-changing endpoints** in this example, so CSRF does not need to be disabled. In apps with cookies/sessions and POST/PUT/DELETE, CSRF failure is a separate diagnostic path.
5. The password here is local demo data only; never place production credentials in source code, READMEs, or sample commands.
6. The security configuration enforces authorization even while logging is enabled. **Enabling DEBUG is never a way around a 401/403**, and rules must never be relaxed to `permitAll` “for easier testing”.

### 5.3. Running Three Control Requests

Start the app with the diagnostics profile and use another terminal.

GET public:

~~~bash
curl -i 'http://localhost:8080/public/ping'
~~~

Expected: **200** and body **pong**.

GET private without credentials:

~~~bash
curl -i 'http://localhost:8080/private/me'
~~~

Expected: **401 Unauthorized**, usually with **WWW-Authenticate: Basic ...**. Exact body and header details depend on configuration and version.

GET private with demo user:

~~~bash
curl -i -u alice:local-demo-password \
  'http://localhost:8080/private/me'
~~~

Expected: **200** and body **hello alice**.

GET admin with demo user lacking privileges:

~~~bash
curl -i -u alice:local-demo-password \
  'http://localhost:8080/private/admin'
~~~

Expected: **403 Forbidden**. This is the policy's intended security behavior, not an error to “fix” by disabling authorization.

**Safety note:** The **`-u alice:...`** syntax uses a dummy credential on localhost only. With real credentials, never pass passwords on the command line or in CI logs where they may appear in shell history or process listings; use secure secret delivery and HTTPS connections.

## 6. Reading DEBUG/TRACE Along the Request Path

### 6.1. FilterChainProxy and Chain Selection

**FilterChainProxy** is the centerpiece of Spring Security Servlet filtering. With TRACE enabled, you may see entries like:

~~~text
DEBUG ... FilterChainProxy : Securing GET /private/me
TRACE ... FilterChainProxy : Invoking ... (filter ...)
DEBUG ... FilterChainProxy : Secured GET /private/me
~~~

This is an **illustrative log pattern**, not output guaranteed to appear verbatim. Filter names, indices, loggers, threads, timestamps, formatting, and presence of individual lines vary by Spring Security version and configuration.

Questions to answer:

- Did the request reach **FilterChainProxy**?
- Which matcher selected which `SecurityFilterChain`?
- Which filters appear in that chain?
- Did the request stop at Authentication, Authorization, CSRF, `ExceptionTranslationFilter`, or get rejected earlier?
- Did the request proceed to `DispatcherServlet`/controller?

If **no logs appear** despite enabling the right category, do not conclude “security has no effect”. The logger may be overridden, the request may not have reached the app, another filter may have blocked early, tests may lack the filter chain, or logs may be routed elsewhere.

### 6.2. Authentication: Why 401?

A private request missing Basic credentials typically passes through:

~~~text
GET /private/me
   │
   ├─ SecurityContext has no authenticated user yet
   ├─ Authentication-related filters do not produce a valid Authentication
   ├─ Authorization requires authenticated()
   └─ ExceptionTranslationFilter / AuthenticationEntryPoint
        → 401 + WWW-Authenticate (for HTTP Basic)
~~~

Do not rely on a single “AnonymousAuthenticationFilter ...” message to assert the final cause. Inspect the full filter path, security rules, entry point, and HTTP response.

Depending on login type:

- **HTTP Basic**: missing or invalid credentials usually return **401**.
- **formLogin**: accessing a protected URL from a browser may return **302 to /login**.
- **OAuth2 Resource Server Bearer**: an invalid token may return **401** with **WWW-Authenticate: Bearer**.
- **OAuth2 Login/OIDC**: may redirect to the IdP authorization endpoint; protect **code, state, nonce, client_secret, and tokens** in logs.

Do not normalize every status mentally into one pattern: the same policy can produce different HTTP symptoms depending on `AuthenticationEntryPoint` and application type.

### 6.3. Authorization: Why 403?

A request from `alice` to **/private/admin** has an `Authentication` but lacks the required role. HTTP security authorization evaluates **hasRole("ADMIN")**, whereas `alice` only has `ROLE_USER`, so the request is denied.

At the authorization layer, logs often help identify **the active rule** and decision state; however, log messages must not be your sole evidence. Prove it by testing both an authorized user and an unauthorized user against the same endpoint.

**403 does not only mean wrong role.** A POST can be blocked earlier by CSRF; a CORS preflight with a disallowed origin can also return 403; method security can throw `AccessDeniedException` from the service layer. Identify the filter/handler or layer that actually produced the response.

### 6.4. Multi-SecurityFilterChain Pitfalls

If the system has multiple chains:

~~~text
Request /api/orders
   → chain with securityMatcher("/api/**")
   → Bearer authentication

Request /admin/panel
   → chain with securityMatcher("/admin/**")
   → form login

Request /unknown
   → fallback chain (if present)
~~~

**`securityMatcher`** determines whether **the entire chain applies**; **`requestMatchers`** inside `authorizeHttpRequests` determines permissions once the request is already inside the chain. A URL matching no chain may not receive the filters or headers you assume.

When diagnosing, check:

1. Chain order (**@Order**, matcher precedence).
2. Which matcher receives the actual URL, including context path or path prefix behind a proxy.
3. The selected chain's `AuthenticationEntryPoint`.
4. Whether a fallback chain exists; never assume the chain for **/api/** also protects **/admin/**.
5. Whether **web.ignoring()** is configured. If a URL is ignored, requests may skip security filters and header writers.
6. If the controller is never invoked, whether the request was blocked earlier or denied inside a method-security proxy.

DEBUG/TRACE helps answer these, but **adding integration tests for each path** turns the conclusion into a repeatable control.

### 6.5. CSRF, CORS, and HttpFirewall

These failures can resemble authorization errors if you inspect only status codes:

| Category | Symptoms | Checkpoints |
| --- | --- | --- |
| **CSRF** | Cookie-session POST/DELETE returns 403 while GET still works | `CsrfFilter`, token repository, session/cookie, whether method is safe |
| **CORS preflight** | Browser OPTIONS returns 401/403 even when GET works with a valid token | `CorsFilter`, `CorsConfigurationSource`, `Origin`, `Access-Control-Request-Method`/Headers |
| **HttpFirewall** | Paths with semicolons/%2F/%5C/dot segments are rejected | `RequestRejectedException`, `StrictHttpFirewall`, and container URI parsing |
| **Security headers** | Response 200 but missing CSP/HSTS or nosniff | Chain header writers, HTTPS detection, reverse proxy, edge-generated responses |
| **Method security** | HTTP chain allows, yet service method throws `AccessDeniedException` | `@EnableMethodSecurity`, `@PreAuthorize`, AOP proxy/self-invocation |
| **Session/async context** | Main request has user, but worker thread sees no `Authentication` | `SecurityContextHolder` ThreadLocal, executor propagation |

**HttpFirewall** can handle the request before any filter chain is selected. If the container or reverse proxy already rejected a non-standard URI, Spring Security logs will contain no matching event. Use raw HTTP tests and outer-layer logs to pinpoint where the request was blocked.

**HSTS** is normally emitted only for secure requests. If TLS terminates at a reverse proxy and the backend sees internal HTTP, missing HSTS may involve trusted forwarded headers or edge configuration rather than DEBUG not being verbose enough.

## 7. Testing with MockMvc: Verifying Behavior Instead of Asserting Log Text

A reliable observability setup combines **diagnostic logging** and **regression tests**. Logging aids investigation, while tests prove the security configuration works properly.

Create **src/test/java/com/example/securitydiagnostics/SecurityDiagnosticsTest.java**:

~~~java
package com.example.securitydiagnostics;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "logging.level.org.springframework.security=DEBUG"
})
@AutoConfigureMockMvc
class SecurityDiagnosticsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointWithoutCredentialsIs401() throws Exception {
        mvc.perform(get("/private/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAuthenticate() throws Exception {
        mvc.perform(get("/private/me")
                    .with(httpBasic(
                            "alice", "local-demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("hello alice"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleIs403() throws Exception {
        mvc.perform(get("/private/admin")
                    .with(httpBasic(
                            "alice", "local-demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/private/me")
                    .with(httpBasic(
                            "alice", "incorrect-password")))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests com.example.securitydiagnostics.SecurityDiagnosticsTest
~~~

PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.securitydiagnostics.SecurityDiagnosticsTest
~~~

**Expectation:** five tests pass on a properly configured Spring Boot 3.x / Spring Security 6.x project. They verify HTTP **200/401/403** across different requests, rather than **asserting a specific DEBUG message**. None of these tests run `DebugFilter` because the **security-debug** profile is not activated.

**This is the static expectation of the example, not an executed run result.** If you want to verify logging, you can use output-capture in a separate test, but avoid asserting verbatim internal log sentences that can change across framework versions. It is better to assert HTTP responses, `Authentication`/authorities, and side effects, using logs only to diagnose why a test failed.

### Checking the Filter Chain in MockMvc

**`@SpringBootTest` + `@AutoConfigureMockMvc`** builds a Spring Test context and typically registers filters in MockMvc according to Boot's configuration, so tests traverse the Spring Security filter chain. If you manually call:

~~~java
MockMvcBuilders.standaloneSetup(controller).build();
~~~

standalone MockMvc does not automatically include **`FilterChainProxy`** merely because the project has the Spring Security dependency. The code above is only a snippet without a declared **controller** variable, illustrating an anti-pattern when testing a controller in isolation.

If constructing MockMvc manually, configure it with **`springSecurity()`** or register the proper `FilterChainProxy`, and ensure `SecurityContextHolder` is handled properly. Do not attribute results from a standalone setup test to production Spring Security policy.

### Reading Logs for a Single Test Case

Before running a test, tag a specific request via the test method or a **secret-free** request ID. Observe:

1. That a request was actually sent.
2. HTTP status and response headers.
3. Logs matching the exact thread/trace ID and timestamp.
4. Which filter chain matched the route.
5. Whether `Authentication` was built or why it was rejected.
6. Which authorization rule was evaluated or why execution never reached it.
7. If a controller/service has side effects, verify they do not run when denied.

A passing status test does not prove every log message always appears; conversely, very detailed logs never replace negative security tests.

## 8. Adjusting Loggers at Runtime via Actuator (Only If Permitted)

In an isolated staging environment, Spring Boot Actuator provides a **loggers** endpoint to inspect effective logger levels and change log levels at runtime without restarting. This is a **sensitive administrative surface**: if public users can invoke it, they can inflate log verbosity or interfere with observability.

Additional dependency in **build.gradle** (beyond the example's dependencies):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Example dedicated profile **src/main/resources/application-local-loggers.yml**:

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: "health,loggers"
~~~

Use only in a **trusted local environment**. Loopback here is the **loopback interface where the process runs**; inside a container/k8s pod, `127.0.0.1` is scoped to that network namespace and does not by itself form a complete administrative access control system. Production requires protecting the endpoint with authentication/authorization, network policies, TLS, and auditing if runtime log-level changes are allowed at all.

Assuming the app runs locally with the **local-loggers** profile, inspect the logger:

~~~bash
curl -i \
  'http://127.0.0.1:9091/actuator/loggers/org.springframework.security.web.FilterChainProxy'
~~~

Temporarily enable TRACE for that exact category:

~~~bash
curl -i -X POST \
  'http://127.0.0.1:9091/actuator/loggers/org.springframework.security.web.FilterChainProxy' \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":"TRACE"}'
~~~

After reproducing with **just a few test requests**, **restore the previous configuration level**. If the category originally inherited its level from its parent (had no explicit `configuredLevel`), you can clear the override with:

~~~bash
curl -i -X POST \
  'http://127.0.0.1:9091/actuator/loggers/org.springframework.security.web.FilterChainProxy' \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":null}'
~~~

Sending **`null`** clears the logger's direct level override so it inherits again; it does **not** set `OFF`. If `configuredLevel` was previously `INFO` or `DEBUG`, restore the exact recorded value rather than defaulting to `null`.

**Never expose the loggers endpoint publicly just for debugging convenience.** Use local loopback, an SSH tunnel, or controlled admin infrastructure, block Internet access, and avoid putting admin tokens into shell history. Under stricter policies, runtime logger updates in production must be disallowed altogether.

## 9. An Auditable Diagnostic Workflow

### Step 1 — Minimal Reproduction Without Real Data

Record:

- URL and method, e.g. **GET /private/admin**.
- Test principal and expected authorities; never record raw Basic passwords, Bearer JWTs, or session cookies.
- Relevant HTTP status and response headers.
- Timestamp, deployment, and sanitized request/correlation ID.
- TLS/proxy/path prefix setup if applicable.

Set the expectation: user **alice** without `ROLE_ADMIN` must receive **403**. “User reported 403” alone is not enough to conclude there is a bug.

### Step 2 — Choose the Lowest Diagnostic Level

Start with:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

If you need to know which filters are invoked, temporarily add:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

If you need to trace method authorization, inspect loggers in **org.springframework.security.authorization** or the specific category emitting events. Narrower is always better than enabling TRACE everywhere.

### Step 3 — Send One Request and Compare Outcomes

~~~text
Request: GET /private/admin
Credential: test account alice
Expected: HTTP 403

Observe:
- Did it reach FilterChainProxy?
- Which SecurityFilterChain was selected?
- Did HTTP Basic create an Authentication for alice?
- Did Authorization require ROLE_ADMIN?
- Why was it denied?
- Did the controller run?
~~~

Log lines are directional signals; verify with HTTP tests, context checks, temporary local breakpoints if needed, and authoritative policy data.

### Step 4 — Widen by One Layer If Needed

If the request **does not appear** in Spring Security logs:

- Check reverse proxy, WAF, load balancer, and servlet container logs.
- Check URL context path/public prefix and rewrite rules.
- Check `SecurityFilterChain` matchers, `web.ignoring`, or the MockMvc test context.
- Check logging appenders, sampling, and dynamic logger levels.

If the request reaches Spring Security but never reaches the controller:

- Inspect authentication/authorization rules, CSRF, CORS, firewall, and exception handling.
- Compare a succeeding request and a failing request **on the same path**.
- Never disable security rules just to prove the controller works.

### Step 5 — Disable Logging, Verify, and Record Findings

- Revert the logger category or disable the **security-diagnostics / security-debug** profile.
- Confirm the **effective logger level** has returned to baseline and `DebugFilter` is no longer active.
- Do not retain sensitive sample headers/payloads in issues, screenshots, build artifacts, or log aggregators.
- If credentials were captured unexpectedly, follow the incident response policy.
- Document the root cause, policy fix, and a regression test **independent of log strings**.
- Monitor log volume, latency, and disk impact while diagnostics were active.

This is an **observe → hypothesize → test → restore** workflow, not tweaking config until HTTP 200 appears.

## 10. Risks of Detailed Security Logging

### 10.1. Sensitive Data and Personal Data

Security logs can appear alongside these fields from the framework, application, gateway, access logs, or custom filters:

- **`Authorization: Bearer ...`**, **`Authorization: Basic ...`**, `Cookie`, `Set-Cookie`, session identifiers.
- OAuth2/OIDC authorization codes, ID tokens, access tokens, refresh tokens, **`state`**, **`nonce`**.
- Passwords, OTPs, reset tokens, API keys, private URLs with sensitive query parameters.
- Usernames, roles/authorities, IPs, detailed URLs, tenant IDs, or request metadata.
- Payloads or claims containing personal data.

Although some Spring Security logs or serializers mask certain values, **never assume every version masks all sensitive data**. Never enable request/response body logging on authentication endpoints in environments with real data. Keep logs off public access, encrypt in transit/at rest per policy, and limit retention.

**Specific warning for `web.debug(true)`:** `DebugFilter` can print/dump fields that regular DEBUG logging does not emit. The “not for production” warning must be treated as an operational boundary, not merely a suggestion.

### 10.2. Performance and Operational Impact

TRACE can generate log entries for multiple filters **per request**, multiplied by concurrent traffic. Even when CPU and heap appear sufficient, log appenders, I/O, and log shippers can saturate. Consequences include:

- Increased latency, I/O, storage usage, and logging costs.
- Difficulty spotting important signals in high-volume log noise.
- Accidentally shipping secrets into centralized storage.
- Delayed or dropped logs due to overloaded queues/appenders.
- Altered timing of race/async bugs, making issues harder to reproduce.

Use log sampling, narrow loggers, small test traffic, and scheduled automatic rollback. Never assume TRACE is “read-only” and therefore free of system impact.

### 10.3. Correlation IDs: Enough to Trace Without Leaking Secrets

A random request ID generated or validated by a trusted tier helps correlate **`proxy → servlet → security → controller`** records. Log only the request ID, path template, status, timing, and generic error code rather than raw credentials.

Never take an untrusted **`X-Request-ID`** straight from the Internet as unsanitized log query data; attackers can inject control characters and cause log injection. Normalize or regenerate the ID at trusted ingress. When using MDC in async threads, ensure context propagation and cleanup; neither `DebugFilter` nor `SecurityContextHolder` automatically propagates MDC across arbitrary executors.

## 11. Troubleshooting: Picking the Right Logger for the Symptom

| Symptom | What to Inspect | Controlled Action |
| --- | --- | --- |
| **401** with HTTP Basic | Were credentials processed, and which `AuthenticationEntryPoint` responded? | Spring Security DEBUG; compare test requests with missing/wrong/valid Basic credentials |
| **401** with Bearer JWT | Did the decoder validate signature, `exp`, `iss`, `aud`? | DEBUG on OAuth2 Resource Server/JWT category; never log raw tokens |
| **302** to unexpected login | Which chain selected `formLogin`/OAuth2 login? | TRACE `FilterChainProxy` and check `AuthenticationEntryPoint` |
| **403** even when user seems to have role | Actual authorities, matchers, method-security policy | Narrow DEBUG/TRACE authorization logger; test valid/invalid roles |
| **403** on POST while GET works | CSRF, CORS, or endpoint authorization | Inspect `CsrfFilter`/`CorsFilter` and functionally required request headers |
| **404** on public route behind proxy | Path prefix rewrite, context path, matching | Edge/container logs + `FilterChainProxy`; not just controller logs |
| Request missing from Spring logs | Proxy/container blocked or log category not enabled | Check network layer and effective logger level |
| **400** on paths with `%2F`, `;`, `%5C` | `HttpFirewall` or servlet container | Compare `RequestRejectedException` logs with container HTTP parser |
| Missing **security headers** | Filter chain bypassed/ignored, gateway-generated response, insecure HTTP | Check chain, header writers, and final edge response |
| **@PreAuthorize** does not run | Self-invocation, method security not enabled, proxy mismatch | Test through real bean/proxy and check `@EnableMethodSecurity` |
| **@Async** loses `Authentication` | ThreadLocal does not automatically cross worker threads | Check executor and `DelegatingSecurityContextAsyncTaskExecutor` |
| TRACE explodes log volume | Scope too broad or high traffic | Narrow category, sample requests, revert promptly |
| No output despite DEBUG enabled | Profile inactive, logger overridden, appender/sampling, request hit another process | Check effective logger config/Actuator and target instance |

**Important:** never treat absence of logs as proof of no attack, and never treat a “Secured ...” line as proof that data authorization is right. You still need to verify permissions at role, tenant, ownership, and real-route levels.

## 12. Checklist Before, During, and After Enabling Debug

**Before enabling:**

- Define the bug, reproducing request, and expected status.
- Choose an isolated local/staging environment, use dummy credentials, and block real user traffic.
- Pick the narrowest category and lowest level that meets the goal.
- Record baseline logger levels and ensure rollback permission.
- Verify log destination, who has read access, and retention/redaction rules.
- With Actuator, restrict network/identity and never expose the loggers endpoint publicly.
- Avoid **`web.debug(true)`** wherever production data exists.

**While enabled:**

- Send the minimum number of requests; never send real tokens/secrets.
- Cross-check status, headers, request ID, filter chain, and rejection layer.
- Distinguish authentication, authorization, CSRF, CORS, and firewall.
- Avoid changing security rules just to “make the test request green”.
- Watch log volume and performance; stop immediately on signs of data exposure or overload.

**After enabling:**

- Revert the profile/logger and confirm the debug filter is gone.
- Re-verify HTTP behavior with log-independent regression tests.
- Contain/purge any sensitive logs per security policy and evaluate secret rotation if needed.
- Document root cause, fix, regression tests, and long-term observability points.
- Never leave TRACE/DEBUG enabled indefinitely on shared staging or production.

**Conclusion:** DEBUG and TRACE are tools to **see security decisions clearly**, not a fix by relaxing permissions. In Spring Security Servlet, prefer **category-scoped DEBUG loggers**, escalating to **narrow TRACE** only when filter-level detail is required; **`web.debug(true)`** belongs strictly in isolated environments due to exposure risk. Once investigation ends, disable diagnostics, protect logs, and turn findings into repeatable security tests.
