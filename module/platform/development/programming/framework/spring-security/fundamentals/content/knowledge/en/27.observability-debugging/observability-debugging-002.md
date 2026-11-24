# Identifying the Security Chain and Rules Applied to a Request

> **Scope:** observing, explaining, and debugging `SecurityFilterChain` selection, authentication filters, and `authorizeHttpRequests` rules for an HTTP request in **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**. This guide uses two separate chains for API and web, controlled logging, and integration tests. The goal is to answer with **evidence**: "Which chain did the request enter?", "Which matcher/rule actually matched?", and "At which step was the request rejected?", rather than guessing the cause from the HTTP status alone.

## 1. Three Questions to Separate When a Request Is Blocked

A `GET /api/reports/weekly` request may return 401, 403, 404, or 200. To explain it accurately, answer **in order**:

1. **Which chain was selected?** `FilterChainProxy` iterates through registered `SecurityFilterChain` instances in priority order and uses **the first chain** whose `RequestMatcher` matches the request. Each request passes only through the security filters of the selected chain; remaining chains are not "merged" or evaluated afterward.
2. **Which authentication mechanisms/filters exist in that chain?** For example, the API chain enables `httpBasic`, while the web chain enables `formLogin`. The same user cannot automatically use every mechanism on every path; an API with only HTTP Basic enabled may return 401, whereas a browser chain redirects to `/login`.
3. **Which authorization rule was applied?** After the request passes the preceding steps, `AuthorizationFilter` evaluates the matchers/authorization rules registered in the selected chain **in declaration order**; in a standard `authorizeHttpRequests` configuration, **the first matching rule** determines the permission requirement. If `.anyRequest()` is last, it is a fallback **within that chain**, not a fallback to pick another `SecurityFilterChain`.

There may also be a fourth question: **Was the HTTP response decided before or after authorization?** `CsrfFilter`, the HTTP firewall, an authentication filter, method security, or a controller can block a request at different points. Therefore, a "403" **does not by itself prove** that `hasRole(...)` denied it, and a "404" **does not by itself prove** that the request bypassed Spring Security.

### Two Distinct "First Match" Layers

| Layer | Coordinating Component | How Selection Works | Related Configuration |
| --- | --- | --- | --- |
| Selecting the **SecurityFilterChain** | `FilterChainProxy` | Picks the **first** chain where `chain.matches(request)==true` | `@Order` on `SecurityFilterChain` beans and `http.securityMatcher(...)` |
| Selecting the **authorization rule** within a chain | `AuthorizationFilter` with `AuthorizationManager` | Evaluates `requestMatchers` in order; uses the **first** matching rule | `http.authorizeHttpRequests(auth -> auth.requestMatchers(...).hasRole(...).anyRequest()...)` |
| Authenticating identity | Filter + `AuthenticationManager` | Follows the mechanism of the **selected chain**, e.g., Basic/form | `httpBasic`, `formLogin`, resource server, custom filters |
| Handling outcomes | Entry point/denied handler, exception handler | Depends on authenticated state and error type | `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, MVC advice |

**Note:** `@Order` on a **SecurityFilterChain bean** determines which chain is evaluated earlier/later. The order of `requestMatchers` **inside** `authorizeHttpRequests` is a separate ordering. Writing `@Order(1)` does not make `requestMatchers("/admin/**")` the first rule in every chain.

## 2. Diagram for Determining Chain and Rule

```text
HTTP request
  method=GET, path=/api/reports/weekly, credentials=...
          |
          v
DelegatingFilterProxy -> FilterChainProxy
          |
          +-- SecurityFilterChain @Order(1)
          |      securityMatcher("/api/**")
          |      matches? YES -> SELECT API CHAIN
          |                     |
          |                     +-- Security filters of API chain
          |                     |    (Basic auth, CSRF, ...)
          |                     |
          |                     +-- AuthorizationFilter
          |                          1. GET /api/public       -> no match
          |                          2. GET /api/reports/**   -> MATCH
          |                                    hasRole("REPORT_VIEWER")
          |                          3. GET /api/me           -> skipped
          |                          4. anyRequest           -> skipped
          |
          +-- SecurityFilterChain @Order(2) ANY REQUEST
                 NOT evaluated further because the first chain matched

If the request is GET /dashboard:
  API chain /api/** -> NO
  WEB chain any request -> YES
  WEB authorization -> anyRequest().authenticated()
  WEB authentication -> formLogin, not HTTP Basic
```

The procedure can be written as an investigative algorithm:

```text
S1. Record method + normalized path, plus context/servlet path if any.
S2. List SecurityFilterChain instances in order; identify the first match.
S3. Inspect the filter list of the selected chain (Basic? form? CSRF? JWT?).
S4. Check whether the request stopped at a filter before AuthorizationFilter.
S5. If it reached AuthorizationFilter, find the first matching rule.
S6. Check Authentication, authorities, and the allow/deny reason.
S7. If filter-level allowed it, check method security and controller handling.
S8. Cross-check HTTP status, logs, and tests for a reproducible conclusion.
```

**Counterintuitive example:** If a high-priority API chain has `.securityMatcher("/api/**")` and a final rule `.anyRequest().denyAll()`, a `GET /api/unknown` request is handled by the API chain and **does not fall back to the web chain** to try `.anyRequest().authenticated()`. There is no concept of "if no API rule matches, automatically continue to the next chain": once a chain matches, that chain is responsible.

## 3. Distinguishing securityMatcher, requestMatchers, and @Order

### 3.1. securityMatcher Selects the Scope of the Entire Chain

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

This is an **illustrative configuration snippet**, not a full application. `securityMatcher("/api/**")` restricts the chain to API requests. Within this chain, `anyRequest()` means any request **already routed into the API chain**, not "every request across the whole application."

### 3.2. requestMatchers Selects Rules Inside a Chain

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasRole("REPORT_VIEWER")
        .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
        .anyRequest().denyAll())
```

This is a **configuration snippet belonging to the API chain**. Specific rules come before general rules. Evaluation order:

- `GET /api/public`: matches the first rule, granted `permitAll`.
- `GET /api/reports/weekly`: matches the second rule, requires `ROLE_REPORT_VIEWER`.
- `GET /api/me`: matches the third rule, only requires being authenticated.
- `GET /api/unknown`: matches none of the first three rules, falls into `denyAll`.
- `POST /api/reports/weekly`: the first rules restrict to `HttpMethod.GET`, so they **do not** match and it falls through to `denyAll` **if the request reaches AuthorizationFilter**. On POST, `CsrfFilter` may block it earlier due to a missing token.

If the order is reversed to:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers("/api/reports/**").hasRole("REPORT_VIEWER")
        .anyRequest().denyAll())
```

then the earlier `"/api/**"` rule **swallows all requests** into `permitAll`, and the reports rule below it will never be evaluated. This is a serious misconfiguration; tests must include scenarios where an unauthorized user calls the reports API and gets denied, not just positive cases.

### 3.3. @Order Only Matters Between SecurityFilterChain Beans

`@Order(1)` is typically evaluated before `@Order(2)`. If a chain with a broad `/**` matcher or default "any request" matcher comes before the `/api/**` chain, the API chain behind it may **never be selected**. Place chains with narrower/more specific matchers before broad ones; place the catch-all chain last.

If `securityMatcher(...)` is omitted, `HttpSecurity` typically defaults to matching **every request**. Do not assume "because the bean is named apiChain it only handles API requests"; **the bean name does not determine the URL matcher**.

If **no chain matches**, a request may **not be protected by Spring Security** through `FilterChainProxy`. That is a vulnerability if the developer assumes every request is checked. A safe fallback chain typically uses `anyRequest().authenticated()` or `denyAll()` as required, rather than leaving no chain covering the rest.

## 4. Complete Example: One API Chain + One Web Chain

### 4.1. Observation Goals

Create a demo application with two chains:

- **API chain `@Order(1)`:** handles only `/api/**`; uses HTTP Basic; `/api/public` is public; `/api/reports/**` requires role `REPORT_VIEWER`; `/api/me` requires login; all other API requests are denied.
- **Web chain `@Order(2)`:** handles all remaining URLs; uses form login; `/public` is public; `/admin/**` requires `ADMIN`; all other web URLs require authentication.

Three demo accounts:

| Username | Demo Password | Authorities |
| --- | --- | --- |
| `analyst` | `analyst-pass` | `ROLE_REPORT_VIEWER` |
| `member` | `member-pass` | `ROLE_MEMBER` |
| `admin` | `admin-pass` | `ROLE_ADMIN` |

Without credentials: `GET /api/reports/weekly` typically returns 401 from the Basic entry point, while `GET /dashboard` redirects with 302 to the login page. These two different responses already provide a **clue** about which mechanism applied, but logs and tests are needed to confirm the exact chain and rule.

### 4.2. Declaring Dependencies

Create a Spring Boot 3.x and Java 17+ project (Gradle or Maven). In a `build.gradle` that already has the Spring Boot plugin and repositories configured, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The snippet above is a **dependencies block**, not a complete Gradle build script. `spring-security-test` provides test helpers for form login and HTTP Basic. The example needs no database because it uses `InMemoryUserDetailsManager`.

### 4.3. Runnable Application Code

Create **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("analyst")
                        .password(encoder.encode("analyst-pass"))
                        .roles("REPORT_VIEWER")
                        .build(),
                User.withUsername("member")
                        .password(encoder.encode("member-pass"))
                        .roles("MEMBER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public")
                                .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/reports/**")
                                .hasRole("REPORT_VIEWER")
                        .requestMatchers(HttpMethod.GET, "/api/me")
                                .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/api/public")
    String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/reports/weekly")
    String weeklyReport() {
        return "report-weekly";
    }

    @GetMapping("/api/me")
    String apiMe(Authentication authentication) {
        return "api-user=" + authentication.getName();
    }

    @GetMapping("/public")
    String webPublic() {
        return "web-public";
    }

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication) {
        return "web-user=" + authentication.getName();
    }

    @GetMapping("/admin/panel")
    String adminPanel() {
        return "admin-panel";
    }
}
```

This is **a complete single Java file** whose public class name matches the filename; `SecurityConfig` and `DemoController` are package-private top-level classes in the same `demo` package. Spring Boot scans the beans in this package. The configuration uses standard Spring Security 6.x APIs and Java 17+ syntax.

**The most important part of the code** is `@Order(1)` + `.securityMatcher("/api/**")` on the API chain, and `@Order(2)` with the default catch-all matcher on the web chain. The line `.requestMatchers(HttpMethod.GET,"/api/reports/**").hasRole("REPORT_VIEWER")` runs only when the request has already been routed into the API chain; the role `REPORT_VIEWER` corresponds to authority `ROLE_REPORT_VIEWER` because `hasRole` applies the default prefix automatically.

In this example, `.formLogin(...)` is enabled only on the web chain. Therefore, do **not** assume `/api/reports/weekly` will redirect to `/login` when unauthenticated; that request belongs to the API chain, and the Basic entry point typically returns 401. Likewise, web requests do not automatically accept HTTP Basic just because the API chain enables Basic.

**CSRF:** Both chains keep the default CSRF configuration. All demo endpoints are GET so we can observe chain/rule selection without disabling CSRF. For POST/PUT/DELETE in real applications, analyze CSRF and the authentication model before altering configuration; an HTTP 403 can originate from `CsrfFilter` before authorization rules are checked.

### 4.4. Running and Sending Comparison Requests

Run the project with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Unless configured on another port, the app listens on `http://localhost:8080`. Test each request with curl:

```bash
# Public API -> 200.
curl -i http://localhost:8080/api/public

# API requiring login -> 401 with Basic challenge.
curl -i http://localhost:8080/api/reports/weekly

# API with wrong credentials -> 401.
curl -i -u analyst:wrong-pass \
  http://localhost:8080/api/reports/weekly

# API user with the right role -> 200.
curl -i -u analyst:analyst-pass \
  http://localhost:8080/api/reports/weekly

# Authenticated API user missing role -> 403.
curl -i -u member:member-pass \
  http://localhost:8080/api/reports/weekly

# API /me only requires authenticated -> 200.
curl -i -u member:member-pass \
  http://localhost:8080/api/me

# API path matching no allow rule -> 403 for authenticated user.
curl -i -u member:member-pass \
  http://localhost:8080/api/unknown

# Web public -> 200.
curl -i http://localhost:8080/public

# Web dashboard without login -> redirect to /login (typically 302).
curl -i http://localhost:8080/dashboard

# Web admin without login -> redirect to login, not 403 for authenticated user.
curl -i http://localhost:8080/admin/panel
```

Lines ending in `\` use Bash line continuation syntax. On PowerShell, use `curl.exe` instead of `curl` if `curl` is aliased to `Invoke-WebRequest`; place each `curl.exe` call on one line or use the appropriate line continuation character.

Expected results for **this exact example configuration**:

| Request | Selected Chain | Rule in Chain | Expected HTTP |
| --- | --- | --- | --- |
| `GET /api/public`, anonymous | API | `GET /api/public -> permitAll` | 200, body `api-public` |
| `GET /api/reports/weekly`, anonymous | API | `GET /api/reports/** -> REPORT_VIEWER` | 401 and `WWW-Authenticate: Basic ...` |
| `GET /api/reports/weekly`, analyst with right password | API | Same report role rule | 200, body `report-weekly` |
| `GET /api/reports/weekly`, member with right password | API | Same report role rule | 403 because `ROLE_REPORT_VIEWER` is missing |
| `GET /api/me`, member with right password | API | `GET /api/me -> authenticated` | 200, body `api-user=member` |
| `GET /api/unknown`, member with right password | API | `anyRequest -> denyAll` | 403, does not try web chain |
| `GET /public`, anonymous | Web | `/public -> permitAll` | 200, body `web-public` |
| `GET /dashboard`, anonymous | Web | `anyRequest -> authenticated` | Redirect to `/login` (typically 302) |
| `GET /admin/panel`, member after form-login | Web | `/admin/** -> ADMIN` | 403 |
| `GET /admin/panel`, admin after form-login | Web | `/admin/** -> ADMIN` | 200, body `admin-panel` |

**Do not treat status codes as sole proof:** although 401 commonly appears on Basic APIs and 302 commonly appears on web forms, handlers and entry points can be customized. Always cross-check chain matching, rule matching, and the filter that stopped the request.

## 5. Enabling Logs to See Which Chain Is Evaluated

### 5.1. DEBUG and TRACE in Spring Security

Use a local development profile (for example `src/main/resources/application-local.properties`) or add directly to `application.properties` only when appropriate for the environment:

```properties
# Show filter configurations and requests protected by Spring Security.
logging.level.org.springframework.security=DEBUG

# Trace evaluation of SecurityFilterChain instances and filter order.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE

# When you need a clearer view of authorization decisions, you can temporarily enable:
logging.level.org.springframework.security.web.access.intercept=TRACE
```

If you want finer detail in a lab environment, you can use:

```properties
logging.level.org.springframework.security=TRACE
```

**Do not leave TRACE enabled indiscriminately in production.** Logs can expose URLs, parameters, identifiers, security context contents, and sensitive diagnostic info, or generate high log volume. Enable only for a controlled duration, on the necessary logger scope, with appropriate log access/retention policies and redaction; never log passwords, `Authorization` headers, cookies, bearer tokens, or session IDs.

When running with the `local` profile:

```bash
./gradlew bootRun --args='--spring.profiles.active=local'
```

If using the shared `application.properties`, no profile argument is needed. Specific logger names/details may vary by Spring Security version; focus on the meaning rather than relying on exact wording in a log line.

### 5.2. Lines to Look For

At startup, `DefaultSecurityFilterChain` usually prints each chain's matcher and the list of security filters it contains. When processing a request, `FilterChainProxy` may log patterns like these (these are **illustrative patterns**, not guaranteed exact strings across versions):

```text
DEBUG ... DefaultSecurityFilterChain : Will secure ... with [ ... ]
TRACE ... FilterChainProxy          : Trying to match request against ...
DEBUG ... FilterChainProxy          : Securing GET /api/reports/weekly
TRACE ... FilterChainProxy          : Invoking ...Filter (n/m)
TRACE ... [authorization logger]    : ... checking request matcher ...
DEBUG ... [entry point/handler]     : ... sending authentication challenge ...
```

**How to read this:** a `Securing GET ...` line only says the request entered `FilterChainProxy` and is being secured; it is **not enough** to conclude which matcher or rule allowed or denied it. Look for `Trying to match request against ...` lines and check chain ordering; check the filter list to see whether the chain contains `BasicAuthenticationFilter` or `UsernamePasswordAuthenticationFilter`. Then inspect logs related to authorization, anonymous/authenticated principal, entry points, and denied handlers.

If logs show the request was checked against matchers in sequence and stopped at `/api/**`, conclude it hit the API chain. If the first match is the fallback web chain, check whether the actual path differs from what you expected, whether a chain is missing `securityMatcher`, or whether `@Order` is wrong.

### 5.3. Do Not Enable Debug Mode Without Control

`@EnableWebSecurity(debug = true)` is an extra debug mode for learning environments that can print fairly broad request/filter details. **It is not recommended in production or environments containing secrets**, and it is not a fix. Prefer scoped DEBUG/TRACE and tests first; disable debug once you have collected sufficient evidence.

Also avoid modifying controllers to publicly return "which chain handled this" or "which authorities the user has" just for debugging. Such data can help an attacker map security policies. Recording it in controlled internal logs or test code is more appropriate.

## 6. Determining the Chain via Programmatic Tests

Spring Security exposes `FilterChainProxy.getFilterChains()` to inspect **the list of chains in exact evaluation order**. Each `SecurityFilterChain` has `matches(HttpServletRequest)` and `getFilters()`. To verify this in tests, use the actual request constructed by `MockMvc` rather than passing only a URL string, because matchers can depend on HTTP method, servletPath, dispatcher type, and request attributes.

### 6.1. Integration Tests with MockMvc

Create `src/test/java/demo/SecurityChainSelectionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainSelectionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy securityProxy;

    @Autowired
    @Qualifier("apiChain")
    SecurityFilterChain apiChain;

    @Autowired
    @Qualifier("webChain")
    SecurityFilterChain webChain;

    private SecurityFilterChain firstMatchingChain(
            MockHttpServletRequest request) {
        return securityProxy.getFilterChains().stream()
                .filter(chain -> chain.matches(request))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void apiRequestSelectsFirstApiChain() throws Exception {
        MvcResult result = mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andReturn();

        assertSame(apiChain, firstMatchingChain(result.getRequest()));
    }

    @Test
    void webRequestSelectsFallbackWebChain() throws Exception {
        MvcResult result = mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andReturn();

        assertSame(webChain, firstMatchingChain(result.getRequest()));
    }

    @Test
    void publicApiIsAccessibleWithoutCredentials() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("api-public"));
    }

    @Test
    void anonymousApiReportTriggersBasicChallenge() throws Exception {
        mvc.perform(get("/api/reports/weekly"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void analystWithCorrectRoleCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/weekly")
                        .with(httpBasic("analyst", "analyst-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("report-weekly"));
    }

    @Test
    void validMemberWithoutReportRoleGets403() throws Exception {
        mvc.perform(get("/api/reports/weekly")
                        .with(httpBasic("member", "member-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongBasicCredentialsGet401() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("member", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void apiFallbackDeniesUnknownPath() throws Exception {
        mvc.perform(get("/api/unknown")
                        .with(httpBasic("member", "member-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWebRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login")));
    }

    @Test
    void webFormLoginAllowsMemberDashboard() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("member")
                        .password("member-pass"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/dashboard"))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web-user=member"));

        mvc.perform(get("/admin/panel").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void webAdminCanOpenAdminPage() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("admin")
                        .password("admin-pass"))
                .andExpect(status().isFound())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/admin/panel").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-panel"));
    }
}
```

**Testing the chain objects directly:** `apiRequestSelectsFirstApiChain` and `webRequestSelectsFallbackWebChain` use `MockMvc` to construct the `MockHttpServletRequest`, then iterate over `getFilterChains()` and pick the **first matching chain**. `assertSame(...)` checks against the exact configured chain bean. This is an in-test diagnostic tool and **does not replace** running real requests through `FilterChainProxy`; the accompanying status/body tests verify whether behavior matches what was deduced.

**Note on complex request matchers:** `matches(...)` may depend on requests that have passed through the firewall, servlet mapping, method, dispatcher type, or request attributes. Testing directly against a minimal hand-crafted mock request may not match runtime behavior. For applications with a context path, custom servlet paths, reverse proxies, or multiple servlets, prefer full `MockMvc` tests with real configuration and cross-check `FilterChainProxy` logs.

Run all tests:

```bash
./gradlew test
```

Run only this class:

```bash
./gradlew test --tests demo.SecurityChainSelectionTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.SecurityChainSelectionTest
```

The assertions are expected to pass with **this exact example code**. This is not fixed stdout; test counts and Gradle/JUnit reporting format may vary by tooling. If an assertion fails, keep the failing request unchanged and identify whether the error is in the chain, rule, or filter/handler; do not change the expected status before reading the trace.

### 6.2. Why @WithMockUser Alone Is Not Enough

`@WithMockUser` or `user(...)` is useful when testing *authorization* on a request that already has an identity. However, it **does not prove** that HTTP Basic/form login is configured on the right chain, that `PasswordEncoder` checks passwords, or that the login entry point responds properly.

In this guide, `httpBasic(...)` in MockMvc creates real input credentials for the HTTP Basic filter; `formLogin()` goes through the form-login flow with a valid CSRF token. Assertions that exercise **the chain's actual mechanism** are more informative than simply injecting a mock `Authentication` and seeing 200.

Also do not use a single `@WithMockUser(roles = "REPORT_VIEWER")` test to conclude that all of `/api/**` is secure. Add **negative tests** for `member`/anonymous, unknown paths, and other HTTP methods.

## 7. Procedure for Debugging a Specific Request

Suppose a production API receives `GET /api/reports/weekly` and is unexpectedly denied. Follow this sequence.

### Step 1 — Record the Actual Request Seen by the Server

Safely collect: method, path, context path, servlet path, relevant query keys, dispatcher type, request ID, environment/profile, status, and account name/roles under access-controlled conditions. Never copy passwords, bearer tokens, cookies, or verbatim Authorization headers into tickets or logs.

Verify differences such as:

- `GET /api/reports/weekly` vs `POST /api/reports/weekly`: the HTTP method can cause `requestMatchers(HttpMethod.GET,...)` not to match.
- `/api/reports/weekly` vs `/reports/weekly`: if a gateway strips the `/api` prefix, the API chain may **not** match.
- `/app/api/reports/weekly` when `/app` is the context path: matchers typically operate on application-relative paths rather than simply taking the full browser URL.
- Encoded URLs, slashes, trailing slashes, special servlet mappings: `HttpFirewall` and request matchers may normalize or handle them differently than what you see on the client.

### Step 2 — Inspect the Chains Actually Registered

Find `@Bean SecurityFilterChain`, `@Order`, and `securityMatcher` in **the configuration belonging to the running application**. In startup DEBUG logs, check `DefaultSecurityFilterChain` and each chain's filter list. Do not infer from bean names or class order in a Java file.

If there are multiple chains, build a table:

| Priority | Chain Matcher | Authentication Mechanism | Core Rule |
| --- | --- | --- | --- |
| 1 | `/api/**` | HTTP Basic | Report API requires `REPORT_VIEWER` role |
| 2 | Any request | Form login | `/admin/**` requires `ADMIN` |

This table is for the **demo application**; in a real application, record the actual configuration, including chains contributed by other configuration modules.

### Step 3 — Match Against the Request, Not the URL "in Your Head"

Enable `FilterChainProxy=TRACE` locally and trace matcher attempts. The first matching chain handles the request. If the expected chain does not match, check `@Order`, `securityMatcher`, HTTP method, context/servlet path, and MVC-provided matchers. If no chain matches, treat this as a serious security review issue, not "the request is safe by default."

A request routed through the `/api/**` chain cannot use a form login filter that exists **only in the web chain**. Note that `/login` and `POST /login` in the example belong to the web chain because those URLs do not start with `/api/`; if you configure a form login endpoint inside a chain that only matches `/api/**`, that endpoint must be brought within that chain's scope or the configuration split appropriately.

### Step 4 — Check Whether the Request Stopped Before AuthorizationFilter

Possible cases:

- `HttpFirewall` rejects a dangerous URL: the request may not reach the expected filter list.
- `CsrfFilter` rejects a POST missing a token: usually 403, even if a later `permitAll` rule would allow it.
- HTTP Basic with wrong password: the authentication filter usually delegates to the 401 entry point before authorization decides.
- Form login failure: the failure handler redirects, which does not indicate a URL rule denied it.
- CORS preflight `OPTIONS` blocked: check CORS/filter ordering, not just roles.
- Error from a custom filter or custom exception handler: the final status may differ from the default.

`curl -i` helps show the status and headers like `Location` or `WWW-Authenticate`. However, logs and tests are stronger evidence when handlers are customized.

### Step 5 — If It Reached AuthorizationFilter, Identify the First Rule

Read **in declaration order** within the **selected chain**. For `GET /api/reports/weekly` in the demo:

1. `GET /api/public` → no match.
2. `GET /api/reports/**` → match → requires `ROLE_REPORT_VIEWER`.
3. `GET /api/me` and `anyRequest` are not evaluated for this request.

If `member` has authority `ROLE_MEMBER`, the request is denied. If `analyst` has `ROLE_REPORT_VIEWER`, it is allowed through to the controller. It does not "continue running" later rules to look for a more permissive option. If a `permitAll("/api/**")` rule precedes the report rule, it can make the reports endpoint public as well.

**A matching rule is not the whole story:** `AuthorizationFilter` may allow the request, yet method security (`@PreAuthorize`), a service, or a controller can still deny it afterward. When the status differs from expectations, inspect the layers after the filter chain too.

### Step 6 — Check Authentication Context and Authorities

Inspect identity only in permitted forms: anonymous or authenticated? Which username/principal? Are authorities `ROLE_ADMIN`, `ROLE_REPORT_VIEWER`, or `SCOPE_x`? `hasRole("ADMIN")` by convention requires authority `ROLE_ADMIN`; `hasAuthority("SCOPE_reports.read")` requires that exact authority string. Do not confuse the role `REPORT_VIEWER` with a scope or accidentally prepend `ROLE_` twice.

For browser requests, sessions/cookies can affect the outcome; for Basic, the header is evaluated by the corresponding filter. In the demo, do not use `analyst:analyst-pass` as proof that "the web chain also accepts HTTP Basic"; the web chain only enables form login.

### Step 7 — Verify Conclusions with Positive/Negative Test Pairs

A correct rule must have both **allow** and **deny** evidence:

- Analyst calling report → 200; Member calling the same report → 403.
- Anonymous calling role-protected API → 401; Anonymous calling public API → 200.
- Anonymous calling web dashboard → redirect to login; Member form-login → dashboard 200.
- Member visiting `/admin/panel` → 403; Admin visiting the same endpoint → 200.
- Authenticated member calling `/api/unknown` → 403; proves the `denyAll` fallback did not fall through to the web chain.

If every test returns 403, there may be a global CSRF/config/filter error rather than every rule being right. If every test returns 200, a broad rule may be overly permissive or the tests may be accidentally bypassing the filter chain.

## 8. Common Mistakes When Deducing Chains and Rules

### 8.1. Confusing Chain @Order with URL Rule Order

**Wrong:** "Putting `@Order(1)` on the API chain means `GET /api/reports/**` will apply before every other rule."  
**Right:** Chains are selected using `@Order` + `securityMatcher`; then **within the selected chain**, `requestMatchers` order is evaluated. You must check both.

### 8.2. Confusing securityMatcher with requestMatchers

**Wrong:** "`requestMatchers("/api/**").authenticated()` makes the entire chain handle only API requests."  
**Right:** `requestMatchers` is an authorization rule inside a chain; `securityMatcher` defines the scope of the `SecurityFilterChain` itself. A chain without `securityMatcher` can typically match any request, shadowing chains after it.

### 8.3. Putting a Catch-All First

A match-all chain placed before an API chain will "steal" API requests. An `anyRequest().permitAll()` or `requestMatchers("/**").permitAll()` rule placed before specific rules prevents subsequent rules from taking effect. Put narrow chain matchers first, the fallback chain last, and narrow rule matchers before `anyRequest`.

### 8.4. Assuming Every Request Runs Through Multiple SecurityFilterChain Instances

`FilterChainProxy` selects the first matching chain. A request does not run sequentially through the API chain and then the web chain just because both matchers could match; filters across chains do not accumulate. If you want a mechanism on both API and web, configure it in each chain that needs it or redesign chain scopes.

### 8.5. Assuming 403 Always Means Missing Role

A POST without CSRF can be blocked by `CsrfFilter` before `AuthorizationFilter`. Method security can also throw `AccessDeniedException` after filter-level authorization has passed. Find the first filter/handler that decided to return the error rather than inferring the cause from 403 alone.

### 8.6. Treating 401 and 302 as Guaranteed Chain Signatures

HTTP Basic usually returns 401 and form login usually redirects with 302; however, authentication entry points and handlers can be customized. An application might use the same status across multiple chains. Test the actual chain/rules and read the logs before concluding.

### 8.7. Ignoring HTTP Method

`requestMatchers(HttpMethod.GET, "/api/reports/**")` does not permit POST. The same URL with a different method can fall into `denyAll`; CSRF may also block it earlier. Do not send only GET when investigating POST/PUT/DELETE issues.

### 8.8. Path at Reverse Proxy Differs from Path at the Application

Ingress may strip or add prefixes, and the application may have a context path or custom DispatcherServlet mapping. In logs, determine the path **Spring actually uses for matching**, and avoid trusting arbitrary `X-Forwarded-*` headers from clients outside a trusted proxy. Forwarded header handling must have clear trust boundaries.

### 8.9. Disabling Spring Security via web.ignoring() to Fix 404/403

`web.ignoring()` or excluding requests from all chains can bypass many security protections, unlike `permitAll` inside a chain (which still runs security filters). Prefer `permitAll` for public endpoints that need security headers; only ignore security on appropriate static/specific resources once the implications are understood.

### 8.10. Using DebugFilter/TRACE and Forgetting to Turn It Off

Detailed logging helps with debugging but can generate large log volumes and expose operational details. Turn off tracing after verification, restrict retention/access, and never write credentials into output or send logs containing tokens to unauthorized parties.

## 9. More Complex Cases

### Matchers Combining Method, Header, or Tenant

A `RequestMatcher` does not have to rely solely on path. Depending on the API used, it can combine method, servlet path, IP, or other request attributes. Therefore, reproduce **the entire request context**, rather than sending only a URL string and expecting identical runtime results.

### Multiple Servlets and Path Mappings

If an application has multiple servlets or a mapping other than `/`, inferred matchers may not behave as expected. In Spring Security 6, matcher types such as MVC, Ant, and other options behave differently by environment/configuration; when multiple servlets exist, explicitly specify the appropriate `RequestMatcher`, servlet path, and conditions. Always treat the current reference documentation for your exact version as authoritative.

### ERROR, FORWARD, and ASYNC Dispatches

A request can trigger ERROR/FORWARD/ASYNC dispatches. Depending on filter mappings and security configuration, another authorization or exception check may run beyond the original request. If a controller throws an error and `/error` is also secured, the final response can be confusing. Inspect the dispatcher type and logs; only `permitAll` dispatcher types when consistent with your contract and threat model.

### Method Security and Principal-Dependent Rules

Even when `authorizeHttpRequests` permits a request, `@PreAuthorize("hasRole('ADMIN')")` on a service can still deny it. Pinpoint exactly where the decision occurred: request-level authorization, method-level authorization, or a business exception. Do not alter `requestMatcher` if the real cause is a service policy.

### Profiles and Test Configuration Differing from Production

`@Profile`, `@ConditionalOnProperty`, configuration beans from other modules, or `@Order` differences can change the chain list. Compare the startup filter list in the failing environment against the test environment; do not treat the code of a single module as proof for the entire application context.

## 10. Checklist for Safe Observation and Debugging

1. Record full method, server-side URL/path, context/servlet mapping, dispatcher type, status, and request ID; **do not store secrets**.
2. Determine the order of `SecurityFilterChain` instances; inspect `@Order` and `securityMatcher`. Is there a catch-all at the end?
3. Select the **first** matching chain; do not merge chains.
4. Inspect the chain's filter list: are Basic/form/JWT/CSRF/CORS/exception handlers actually in that chain?
5. Check whether the request was blocked **before** or **inside** `AuthorizationFilter`.
6. If it reached authorization, walk `requestMatchers` **in order**, noting the first matching rule and its permission requirement.
7. Cross-check principal, `isAuthenticated`, and authorities; distinguish `ROLE_` from `SCOPE_`.
8. Check method-level security, controller mappings, and business exceptions if filter-level checks passed.
9. Enable bounded DEBUG/TRACE and inspect the corresponding logs; turn it off after gathering evidence.
10. Write both positive **and** negative tests for URLs, HTTP methods, credentials, roles, and fallbacks.
11. Compare actual configuration in the failing environment with app/test; verify gateway, context path, and servlet mapping.
12. Do not "fix" failures by disabling CSRF, removing security chains, or opening `permitAll` too broadly.

## 11. Self-Check Questions

1. Why do `@Order(1)` and `.securityMatcher("/api/**")` in the API chain serve two different roles? What could happen if `securityMatcher` is omitted?
2. If a request already matched the API chain but matches none of the specific API rules, does Spring Security try the web chain next?
3. If `.requestMatchers("/api/**").permitAll()` is placed before the `/api/reports/**` rule, will the report rule still take effect? Why or why not?
4. An anonymous caller gets 401 on `GET /api/reports/weekly` and 302 on `GET /dashboard`. What details must be checked before concluding the two requests use Basic and form login?
5. An authenticated account receives 403 on `GET /api/unknown`. Does this illustrate a chain fallback or an authorization rule fallback?
6. If a user sends `POST /api/reports/weekly` without a CSRF token and gets 403, can you conclude that `denyAll` ran?
7. What do `FilterChainProxy.getFilterChains()` and `chain.matches(request)` help verify? Why might passing only a URL string be insufficient for custom matchers?
8. A user has authority `ROLE_REPORT_VIEWER`, yet the request returns 403. List three causes to check besides "wrong role."
9. When a gateway strips the `/api` prefix, which chain might handle the request and why? How do you verify the post-proxy path?
10. A `permitAll` endpoint is still blocked on POST without CSRF. Why does `permitAll` not mean "bypass all filters"?
11. Why is `@WithMockUser` insufficient to prove that an HTTP Basic entry point or form login filter is configured on the right chain?
12. If logs show `AuthorizationFilter` permitted a request yet the controller returns 403, which layers do you investigate next?

**Hints:** (1) priority vs match scope; (2) no, once a chain is selected, that chain is used; (3) no, the first rule already matched; (4) check matcher/filter list/entry point/logs; (5) authorization fallback `denyAll`; (6) no, CSRF can block earlier; (7) verifies the first matching chain with full method/path/context; (8) CSRF, method security, custom filter/handler; (9) depends on actual path, may fall into web chain; (10) permitAll is only an authorization decision; (11) mock user bypasses real authentication; (12) method security, custom policy/filter, handlers, and controller/service.

## Official Reference Documentation

- [Spring Security 6.5 — Servlet Architecture: FilterChainProxy, SecurityFilterChain, Logging](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration: Multiple SecurityFilterChain and Matching](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HTTP Requests and matcher order](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — FilterChainProxy API, getFilterChains](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security 6.5 — Servlet Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
- [Spring Security 6.5 — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)