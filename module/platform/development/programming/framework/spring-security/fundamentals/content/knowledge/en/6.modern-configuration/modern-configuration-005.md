# Distinguishing Chain Selection from Access Rule Selection

> **Key point in modern Spring Security configuration:** There are two different "matches." `http.securityMatcher(...)` determines **which `SecurityFilterChain` is responsible for the request**; whereas `requestMatchers(...)` inside `authorizeHttpRequests(...)` determines **which authorization rule that request must satisfy inside the already-selected chain**. Confusing these two selection levels can cause endpoints to bypass all security filters or place a valid rule in a chain that never runs.

This lesson belongs to the **Modern Configuration** group of **Spring Security – fundamentals**, focusing on **Spring MVC/Servlet, Spring Security 6.x** applications. Examples use Java 17 and the `SecurityFilterChain`/`HttpSecurity` configuration API; WebFlux has a similar structure but uses `SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange`, and WebFlux-specific matchers.

## 1. Objectives

After this lesson, you can:

1. Explain precisely what `securityMatcher`, `requestMatchers`, `anyRequest`, and `@Order` do, and in what order.
2. Predict the chain/rule and expected outcome for requests with varying paths, HTTP methods, and authentication states.
3. Understand why `anyRequest().denyAll()` in a chain with `securityMatcher("/api/**")` **cannot** protect `/admin` outside that chain's scope.
4. Design multiple chains following **specific first, catch-all last**, avoiding requests slipping outside Spring Security.
5. Recognize when filter-provided form login/logout URLs lie outside `securityMatcher`, breaking login endpoints.
6. Build a small application yourself and test allowed cases, 401, 403, wrong methods, CSRF, and routes outside the API.
7. Decide when to split into multiple chains and when **one chain** with multiple authorization rules suffices.

## 2. Two Levels of Decision-Making

An example request:

```http
GET /api/reports HTTP/1.1
Host: localhost:8080
Authorization: Basic ...
```

For Servlet, the simplified flow:

```text
HTTP request
    |
    v
Servlet FilterChain
    |
    v
DelegatingFilterProxy -> FilterChainProxy (Spring Security)
    |
    +-- [LEVEL 1: SELECT SECURITY FILTER CHAIN]
    |      Try @Order(1) chain: match("/api/**")?
    |         YES -> pick API chain, stop checking lower chains
    |         NO  -> try next chain
    |      Fallback chain: matches all requests
    |
    v
Security filters belonging to ONE selected chain
    |
    +-- Authentication, SecurityContext, CSRF, ...
    |
    +-- [LEVEL 2: SELECT AUTHORIZATION RULE]
    |      For API chain:
    |        GET  /api/reports -> REPORT_READ?
    |        POST /api/reports -> REPORT_WRITE?
    |        GET  /api/admin   -> ROLE_ADMIN?
    |        remaining API requests -> DENY
    |
    +-- Allow: proceed to Spring MVC controller
    +-- Deny: 401 / 403 / redirect depending on context
```

Note: Level 1 **does not grant access by itself**. Selecting a chain only decides which filters and policies apply. Level 2 makes the HTTP authorization decision. After passing Level 2, the service still needs to check permissions on the object, tenant, and business state. Neither level automatically knows which customer owns report number 42.

### 2.1. Comparison Table

| Aspect | Chain selection | Access rule selection (request authorization) |
| --- | --- | --- |
| Typical API | `http.securityMatcher("/api/**")` | `http.authorizeHttpRequests(a -> a.requestMatchers(...).hasAuthority(...))` |
| Where it happens | `FilterChainProxy` selects `SecurityFilterChain` | `AuthorizationFilter` uses `AuthorizationManager` inside the chain |
| Question answered | "Which chain handles the request?" | "May this request reach the handler?" |
| Data used to match | `RequestMatcher`, typically path and possibly method or custom conditions | `RequestMatcher` per rule, typically path + method |
| Ordering | Chain priority via `@Order`; **first matching chain** | Declaration order; **first matching rule** inside that chain |
| When no match | Try next chain; if none left, no Spring Security chain protects it | Try next rule; reaches `anyRequest()` if declared |
| Effect of `anyRequest()` | Does not change chain selection scope | Covers only requests **already inside the current chain** |
| Result | One filter set applied or no chain at all | `permitAll`, `denyAll`, `authenticated`, `hasRole`, `hasAuthority`... |
| Common mistake | Missing catch-all; endpoints fall outside Spring Security | Broad rule placed first; specific rules never evaluated |

**The two "first match" levels are not the same.** A request enters only **the first selected `SecurityFilterChain`**, and then evaluates **the first matching rule** in that chain's authorization section. If that rule denies, Spring Security **does not try a subsequent chain to see if it allows**.

## 3. Understanding Each API Accurately

### 3.1. `securityMatcher(...)`: Lifetime Scope of the Entire Chain

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

This code is a **snippet** inside a Spring configuration class; a complete runnable program is provided in Section 7.

- `securityMatcher("/api/**")` replaces the chain's default matcher with a condition applying to paths starting with `/api/`.
- When `GET /api/reports` arrives, this chain **can be selected** (unless a higher-priority chain already matched).
- When `GET /admin` arrives, this chain **does not accept the request**; `anyRequest().authenticated()` here **never gets a chance to run**.
- A chain **declaring no `securityMatcher`** defaults to a matcher matching every request; hence it is typically used as a fallback.
- `securityMatcher` inspects requests when selecting a chain; it is neither "registering controller paths" nor "enabling roles."

With Java matcher overloads, you can pass a concrete `RequestMatcher` if you must evaluate HTTP method, servlet path, host, or complex conditions. Do not use a path-only matcher and assume it only accepts GET: if the path matches, POST/DELETE also enter the chain, and internal authorization rules then decide.

### 3.2. `requestMatchers(...)`: Conditions for Individual Rules

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports")
        .hasAuthority("REPORT_READ")
    .requestMatchers(HttpMethod.POST, "/api/reports")
        .hasAuthority("REPORT_WRITE")
    .anyRequest().denyAll()
)
```

Inside the **already-selected chain**:

1. Spring Security checks `GET /api/reports` first; if it matches, requires authority `REPORT_READ`.
2. If it does not match, checks `POST /api/reports`; if it matches, requires `REPORT_WRITE`.
3. Remaining requests in the **current chain** hit `denyAll`.
4. Rules after the first matching rule are **not** evaluated; there is no "collect all roles from multiple rules and decide together."

For example, if Alice has `REPORT_READ` but lacks `REPORT_WRITE`, Alice can call GET, yet cannot call POST merely because the URL is the same. Changing the HTTP method changes the operation requiring authorization. For POST, PUT, PATCH, DELETE, **CSRF protection** can also block requests independently of permissions, depending on authentication mechanism and configuration.

### 3.3. `anyRequest()`: Remainder of the Chain, Not of the Entire App

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .anyRequest().denyAll()
    );
```

Exact meaning:

- `GET /api/public` enters the API chain and is allowed by the rule.
- `GET /api/private` enters the API chain and is denied by `denyAll` unless another specific rule matches.
- `GET /admin` **does not enter the API chain**; whether it is protected depends on other chains.
- Even though `/api/public` has `permitAll`, it still passes through relevant chain filters (e.g., security headers, and CSRF if the request is a POST with CSRF enabled).

This is why **you cannot replace a catch-all SecurityFilterChain with a single `anyRequest().denyAll()` line inside a narrow chain**.

### 3.4. `@Order`: Order in Which Chains Are Tried

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception { /* ... */ }

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception { /* ... */ }
```

This code only illustrates signatures; `/* ... */` represents bodies provided in the complete example.

- The `@Order(1)` chain is tried before a chain without `@Order` (which usually comes after chains with explicit precedence).
- The first matching chain is selected, even if the user's roles **do not satisfy that chain's policy**.
- Once the first chain matches and denies, **there is no "try the next chain" step**.
- A high-priority catch-all placed before the API chain can "swallow" all requests: the API chain will never run.
- Do not rely on bean names or method order in the Java file to guess chain precedence.

### 3.5. `securityMatchers(...)` and Custom `RequestMatcher`

`HttpSecurity` also provides `securityMatchers(...)` to configure a set of chain-level matchers. It serves **the same chain-selection level** as `securityMatcher`, differing only in syntax when multiple patterns exist. `requestMatchers(...)` inside `authorizeHttpRequests` remains the **rule-selection level**.

```java
// CHAIN-level snippet: chain dedicated to two API branches.
http.securityMatchers(matchers -> matchers
    .requestMatchers("/api/**", "/internal/**"));
```

When combining overloads or matcher builders, verify the exact API and semantics of your running Spring Security version; do not blindly chain `securityMatcher(...)` calls expecting conditions to accumulate. For custom request matchers, ensure they rely only on trustworthy inputs (normalized paths, servlet path, method...), never trusting client-supplied `X-Role` or `X-User` headers to grant access.

**Further distinction:** `web.ignoring()`/`WebSecurityCustomizer` removes requests from the Spring Security filter chain; `permitAll` allows requests **at the authorization step inside the chain**. For static resources or public endpoints, usually prefer `permitAll` so related protective filters still run.

## 4. Predicting Behavior on a Two-Chain Map

Suppose an application has:

```text
@Order(1) API CHAIN
  securityMatcher("/api/**")
  GET  /api/reports -> REPORT_READ
  POST /api/reports -> REPORT_WRITE
  GET  /api/admin   -> ROLE_ADMIN
  anyRequest        -> denyAll

FALLBACK CHAIN
  securityMatcher: not declared -> matches all remaining requests
  GET /public       -> permitAll
  GET /profile      -> authenticated
  anyRequest        -> denyAll
```

The table below assumes the account is authenticated when a user is named, and a valid CSRF token is sent when required.

| Request | Selected chain | Selected rule | Outcome if... |
| --- | --- | --- | --- |
| `GET /api/reports` | API | `REPORT_READ` | Reader has `REPORT_READ` -> `200` |
| `GET /api/reports` | API | `REPORT_READ` | Admin only has `ROLE_ADMIN` -> `403` |
| `POST /api/reports` | API | `REPORT_WRITE` | Writer has `REPORT_WRITE` + valid CSRF -> `200` |
| `POST /api/reports` | API | `REPORT_WRITE` | Reader lacks permission -> `403` |
| `GET /api/admin` | API | `ROLE_ADMIN` | Admin has right role -> `200` |
| `GET /api/admin` | API | `ROLE_ADMIN` | Reader has `REPORT_READ` -> `403` |
| `GET /public` | Fallback | `permitAll` | No login -> `200` |
| `GET /profile` | Fallback | `authenticated` | Anonymous -> `401` with HTTP Basic |
| `GET /profile` | Fallback | `authenticated` | Logged-in Reader -> `200` |
| `GET /unknown` | Fallback | `denyAll` | Reader -> `403` |
| `GET /api/unknown` | API | `denyAll` | Reader -> `403` |
| `DELETE /api/reports` | API | `denyAll` | Even Writer with `REPORT_WRITE` is blocked |

In an application configured with HTTP Basic, requests missing credentials typically receive `401` with a `WWW-Authenticate` header; authenticated requests lacking an authority typically receive `403`. With form login/sessions, browsers may receive a `302` redirect. `AuthenticationEntryPoint`, CSRF, error handlers, and proxy setups can affect details, so write integration tests for your actual project.

**Walkthrough for GET `/api/admin`:** Even if fallback supposedly had a stronger "admin" policy, fallback **is never tried** because `/api/**` selected the API chain. Every rule for `/api/admin` must live inside the API chain or in method/service policies applied after passing the chain.

## 5. Dangerous Case: One Narrow Chain with No Fallback

```java
@Configuration
class IncompleteSecurityConfig {
    @Bean
    SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This snippet compiles when placed in a project with appropriate imports and starters, yet **the configuration lacks protection for the rest of the app**. Because `GET /internal/export` does not match `/api/**`, that request **is not governed by `onlyApi`'s Spring Security chain**. If a `/internal/export` controller exists with no other safeguard, the endpoint risks unauthorized access. `anyRequest().denyAll()` inside `onlyApi` cannot rescue paths outside its scope.

Common fix:

```java
@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Or if the application **does not need different filter mechanisms across areas**, use **a single chain**, omit `securityMatcher(...)`, and place multiple `requestMatchers(...)` inside one `authorizeHttpRequests(...)`. That is usually simpler and less risky when the number of routes is modest.

## 6. When Do You Need Multiple Chains vs. One Chain?

One chain with multiple authorization rules suffices when endpoints share the same login/session style, CSRF, CORS, security headers, and core filters. Example:

```java
@Bean
SecurityFilterChain oneChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/reports")
                .hasAuthority("REPORT_READ")
            .requestMatchers(HttpMethod.POST, "/api/reports")
                .hasAuthority("REPORT_WRITE")
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Multiple chains become useful when **the security mechanisms at the filter level themselves differ**, for example:

- An API accepts only Bearer tokens as a Resource Server, while the admin UI uses OIDC browser login/sessions.
- Admin endpoints require a different set of authentication filters and session policy than a stateless API.
- An internal endpoint group uses a set of custom filters or a distinct CSRF/CORS policy for concrete reasons.
- Different policies are needed **at the chain level**, not merely different role requirements.

Do not create a separate chain for every role if all chains actually use the same filters and only swap `hasRole(...)`. Those differences belong in **`requestMatchers`**. Every extra chain increases what must be tested: out-of-scope paths, selection order, CSRF, entry points, login/logout endpoints, static files, fallback, and unlisted requests.

## 7. Complete Application: Java 17, Spring Boot 3.5.16

This example uses Spring Boot **3.5.16** and Spring Security 6.5.x managed by the BOM to present the stable `SecurityFilterChain` DSL. Spring Boot 3.5.16 was released in June 2026 as the final OSS release of the 3.5.x line; for new production projects, choose a Spring Boot branch that is still supported and receiving patches. The in-memory accounts and sample passwords are **for local/test use only**.

### 7.1. Project Structure

```text
matcher-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/demo/matching/MatchingApplication.java
    └── test/java/demo/matching/MatchingApplicationTests.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>matcher-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. `MatchingApplication.java` — Two Explicit Chains

Create `src/main/java/demo/matching/MatchingApplication.java`:

```java
package demo.matching;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
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
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MatchingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatchingApplication.class, args);
    }

    // Chain 1: dedicated to /api/**, evaluated before fallback.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF remains enabled by default; POST requires a valid token.
            .build();
    }

    // Chain 2: no securityMatcher => accepts all remaining requests.
    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Allow servlet ERROR dispatch to render error responses;
                // the original request is still subject to the chain's rules.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .authorities("REPORT_READ").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("REPORT_READ", "REPORT_WRITE").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN").build()
        );
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/api/reports")
    String readReport(Authentication authentication) {
        return "report:" + authentication.getName();
    }

    @PostMapping("/api/reports")
    String writeReport(Authentication authentication) {
        // Illustrates permission to perform POST only; no database write.
        return "written-by:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "admin-ok";
    }
}
```

**Exact explanation:**

1. `@Order(1)` and `securityMatcher("/api/**")` cause the API chain to be tried first; all paths with that prefix are evaluated inside this chain. Other paths go to fallback.
2. `requestMatchers(GET, "/api/reports")` does not open another chain. It is evaluated **only after the request has entered the API chain**, and then requires `REPORT_READ`.
3. `requestMatchers(POST, "/api/reports")` sets a distinct rule for the write operation. Even though `writer` holds `REPORT_WRITE`, a POST missing a CSRF token can still get `403` from `CsrfFilter`.
4. `GET /api/admin` requires `ROLE_ADMIN`; `hasRole("ADMIN")` adds the `ROLE_` prefix by default convention. `admin` does not have `REPORT_READ`, so `admin` cannot call `GET /api/reports`.
5. `anyRequest().denyAll()` in the API chain only blocks requests that matched `/api/**`; fallback blocks undeclared paths outside the API.
6. `DispatcherType.ERROR` is permitted in fallback so the Servlet container's error dispatch can render error responses. This does not open arbitrary public URLs; the original request must still pass the rules.
7. Both chains use HTTP Basic solely for learning chain selection. In real applications, passwords/tokens must travel over HTTPS, alongside proper authentication, resource-ownership authorization, rate limits, and safe logging.
8. No `formLogin` is declared in this example, so browsers receive no default form login from these chains; anonymous Basic clients receive a `401` challenge.

### 7.4. `MatchingApplicationTests.java` — Proving Both Selection Levels

Create `src/test/java/demo/matching/MatchingApplicationTests.java`:

```java
package demo.matching;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MatchingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void fallbackAndApiHaveDifferentPathScopes() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/profile")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:reader"));

        // /unknown is outside /api/** so fallback denies it.
        mvc.perform(get("/unknown")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());

        // /api/unknown is inside /api/** so the API chain denies it.
        mvc.perform(get("/api/unknown")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiRulesDependOnMethodAndAuthority() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:reader"));

        // ROLE_ADMIN does not automatically imply REPORT_READ.
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        // Unpermitted method is denied.
        mvc.perform(delete("/api/reports")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postRequiresBothPermissionAndCsrf() throws Exception {
        // Writer has REPORT_WRITE but lacks CSRF token.
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Valid CSRF but reader lacks REPORT_WRITE.
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());

        // Both proper permission and valid CSRF token.
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("written-by:writer"));
    }
}
```

This test suite verifies **real behavior** through the Spring Security filter chain and controller without asserting internal filter class names. `httpBasic(...)` constructs an HTTP Basic header processed by the application's real `UserDetailsService`/`PasswordEncoder`. `csrf()` supplies a valid token in test requests; in a browser/session product, clients must obtain the token through the configured mechanism. Do not use `@WithMockUser` to conclude that password verification works, because mock users bypass credential verification.

### 7.5. Running It

In the directory containing `pom.xml`, with JDK 17+ and a Spring Boot-compatible Maven:

```bash
mvn test
mvn spring-boot:run
```

With the app running locally, try (older Windows PowerShell may need `curl.exe`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader http://localhost:8080/profile
curl -i http://localhost:8080/api/reports
curl -i -u reader http://localhost:8080/api/reports
curl -i -u admin http://localhost:8080/api/admin
curl -i -u admin http://localhost:8080/api/reports
```

Use `curl -u reader` / `curl -u admin` so curl prompts for the password interactively; enter `demo-pass` in the **local** environment. Never embed secrets directly in commands to avoid storing them in command history. Expected results in order: `200` with body `public`; `401`; `200 profile:reader`; `401`; `200 report:reader`; `200 admin-ok`; `403`.

For POST, `curl -u writer -X POST http://localhost:8080/api/reports` without a CSRF token typically returns `403`. Do not disable CSRF just to make curl POST return 200; the `MockMvc` tests above verify both token and permission. To integrate a real form/browser, choose a `CsrfTokenRepository`, expose the token, and send the proper token/credentials per your threat model.

**Result reliability:** error HTTP bodies/headers may vary by Boot/version/proxy, while tests verify the defined status codes and success bodies. The code uses Spring Security 6.5 APIs, not yet updated to Spring Security 7 APIs; check the corresponding migration guide when upgrading versions.

## 8. Ordering Trap: Broad Chain Prioritized Over Narrow Chain

Conceptually flawed configuration:

```java
// Example of a bad layout; the two methods below are snippets, not a complete app.
@Bean
@Order(1)
SecurityFilterChain allFirst(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiLater(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

`allFirst` has no `securityMatcher`, so it matches every URL. `/api/private` is captured by priority-1 chain; Spring Security **never proceeds** to `apiLater`. The result can be an unintentionally public API even though the code appears to declare `hasRole("ADMIN")` elsewhere.

**Fix:** put narrow API chains first and fallback last. Also inspect rules inside each chain rather than relying on "naming the class AdminSecurityConfig" to enforce protection.

Another error is placing a broad rule before a narrow rule inside **the same chain**:

```java
.authorizeHttpRequests(a -> a
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Here, as soon as `/api/admin/settings` matches `/api/**`, the subsequent `hasRole("ADMIN")` rule **is never evaluated**. Instead, place `/api/admin/**` rules before broad rules and carefully consider whether `/api/**` should be public at all.

## 9. Filter-Provided Endpoints Trap: Login/Logout

`formLogin()` can provide an endpoint handling `POST /login`, and Spring Security can generate a `GET /login` page under default configuration. However, if you write:

```java
http
    .securityMatcher("/secured/**")
    .authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
```

then `GET /login` and `POST /login` **do not belong to `/secured/**`**. That chain does not accept the default login requests, so its filters cannot serve or handle them. Without a suitable endpoint in another chain, login can return 404 or be denied by fallback. This is a consequence of **chain selection**, not a missing `requestMatchers(...).permitAll()`.

Solutions:

- Choose matchers covering the actual login/logout URLs with matching policies, or use one broad chain for the browser area.
- When configuring custom login URLs, check `loginPage(...)`, `loginProcessingUrl(...)`, and logout URLs; if using a custom login page, the application must provide the corresponding HTML/controller.
- Submit the login form with a CSRF token per configuration when CSRF protection applies.
- Write tests for **the login page, POST login, logout, and callbacks** rather than testing only business routes.
- Do not put `permitAll("/login")` inside a `/secured/**` chain expecting `/login` to enter that chain; rules cannot expand a chain's matcher scope.

Related point: `permitAll` does not mean Spring Security skips all filters; `web.ignoring()` is the way to exclude requests from the security chain, and is generally unsuitable as a default for public resources.

## 10. Matcher Details That Can Make Production Differ from Local

### 10.1. HTTP Method

`.requestMatchers("/api/reports").hasAuthority("REPORT_READ")` typically matches paths without pinning the HTTP method. If the app later adds `POST /api/reports`, this path-only rule can accidentally allow POST under read permission. Declare `requestMatchers(HttpMethod.GET, ...)` and `requestMatchers(HttpMethod.POST, ...)` with distinct permissions when operations differ.

### 10.2. Query Parameters

Standard path matchers do not treat `?id=42` as ownership authorization. `GET /api/reports?id=42` and `GET /api/reports?id=43` match the same URL rule; the service must verify ID, owner, tenant, and ACLs server-side. If you need to match query parameters at the HTTP policy level, use a custom `RequestMatcher`, without replacing domain resource checks.

### 10.3. Servlet Path, Context Path, and Multiple DispatcherServlets

Spring Security matchers generally evaluate paths per Servlet rules rather than full browser URLs including scheme/host/port. When an app uses a non-default context path, multiple servlets, or special servlet mappings, path/string matcher behavior can differ from expectations. Verify `DispatcherServlet` mapping, servlet path, URL normalization, encoded slashes, path traversal, and Spring Security version. Use a concrete `RequestMatcher` when you need clarity on what is matched.

Do not inspect `request.getRequestURI()` with `startsWith("/api")` inside a custom filter as a quick substitute for framework-normalized matchers.

### 10.4. Dispatcher Type: REQUEST, ERROR, FORWARD

`AuthorizationFilter` can also apply to internal dispatches. When Spring MVC dispatches to an error page or forwards to a view, an overly tight rule can replace the error response with another 403. Where appropriate, allow `DispatcherType.ERROR` and `FORWARD` explicitly while **never opening the original request outside protection**. Test exception/error dispatches, not just successful GETs.

### 10.5. CORS and CSRF Across Multiple Chains

CORS preflight (OPTIONS) may carry no credentials, whereas CSRF typically validates state-changing requests. CORS/CSRF settings must live on the chain that actually handles the request. If the API chain is selected, do not assume the fallback chain's CORS/CSRF will run afterward. Pick strategies based on authentication type: cookie/session differs from explicitly attached Bearer token APIs. Test OPTIONS, POST/PUT/DELETE, and realistic cross-origin requests.

### 10.6. Framework Upgrades

Newer Spring Security releases may change which matcher implementation is selected automatically (for instance with Spring MVC or `PathPatternRequestMatcher.Builder`). The examples in this lesson use string overloads supported by Spring Security 6.5; when upgrading to Spring Security 7 or switching stacks, consult the migration guide for matcher/path handling and re-run negative tests. Never replace configurations with broad wildcards during an upgrade.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `securityMatcher` on the only chain with no fallback | Out-of-scope paths bypass Spring Security | Add a catch-all chain or remove the narrow matcher |
| Placing fallback `@Order(1)` before API | API chain is never selected | Give specialized chains higher priority than broad chains |
| Assuming a 403 chain falls through to another chain | Misunderstanding execution and debugging | Only the first matching chain runs; fix rules in that chain |
| Placing `requestMatchers("/api/**").permitAll()` before admin rule | Admin endpoints can become public | Put specific rules before broad rules |
| Using path-only matchers for all methods | READ permission may apply to WRITE | Match the appropriate `HttpMethod` |
| Treating `anyRequest().denyAll()` in API as blocking the whole app | Pages/endpoints outside API left exposed | Add a fallback covering everything else |
| Form login URL outside `securityMatcher` | Login is not handled by that chain | Include login URLs in chain scope or design login explicitly |
| Misinterpreting CSRF 403 as a matcher miss | Disabling protection or fixing the wrong layer | Check CSRF independently of permissions |
| Sending static resources through `web.ignoring` unnecessarily | Loses security headers and chain filters | Use `permitAll` when appropriate |
| Splitting too many chains per role | Easy to miss matchers and divergent policies | Use one chain with multiple request rules if filters match |
| Checking URLs without checking resources | IDOR/BOLA, cross-tenant data leaks | Check owner/tenant/action/state in service/repository |
| Writing only happy-path tests | Unintended public endpoints go unnoticed | Test anonymous, wrong role, wrong method, paths outside chain |

## 12. Systematic Configuration Review Workflow

Whenever adding endpoints or splitting chains, follow this order:

1. **List requests to protect:** path, HTTP method, servlet mapping, session/token, login/logout/health/actuator/webhook endpoints.
2. **Determine security mechanisms:** do these requests genuinely need different filters? If not, prefer one chain with multiple rules.
3. **Order chains properly:** `@Order(1)` for specialized chains, then other narrow chains, and **a fallback with no narrow matcher**.
4. **Trace which chain each request enters:** do not look at roles first; inspect `securityMatcher` and `@Order`. If no chain matches, fix that gap.
5. **Trace authorization rules inside the chain:** read `requestMatchers` top to bottom; the first matching rule decides. End the chain with `anyRequest().denyAll()` or an intentional fallback policy.
6. **Verify other filters:** are HTTP Basic, form login, CSRF, CORS, session, headers, OAuth2/JWT, and custom filters present on the actual chain?
7. **Write negative tests:** anonymous; user lacking permission; different method; URL outside chain; missing CSRF; error dispatch; different tenant/owner identity.
8. **Verify transport and business logic:** HTTPS protects credentials, and services verify owner/tenant. URL matchers do not replace those layers.
9. **Review after upgrades:** matcher implementations, Boot auto-configuration, and filter-provided endpoints can change; verify with real behavioral tests.

### Minimum Multi-Chain Test Matrix

| Scenario | What it must prove |
| --- | --- |
| URL inside API, valid permission | Request succeeds |
| URL inside API, wrong permission | Does not fall back to another chain |
| URL inside API, wrong HTTP method | GET permission is not mistakenly accepted for POST |
| URL outside API, anonymous | Governed properly by fallback policy |
| URL outside API, valid user lacking access | Denied by fallback |
| API with POST, CSRF enabled | Missing token is blocked despite sufficient permission |
| Login/logout/CSRF URLs | Filters and endpoints align with the chain |
| Existing resource owned by someone else | Service denies even when chain allows the action |
| Newly added endpoint | Denied by default if no rule is defined |
| Multiple servlets/dispatchers/errors | Matchers and error rendering behave as intended |

## 13. Thought Exercises and Answers

**Question 1.** Chain A has `securityMatcher("/api/**")` and `anyRequest().denyAll()` inside it. There is no Chain B. Will `GET /internal/secrets` be denied by Spring Security?

**Answer:** You cannot conclude it is denied by Spring Security, because Chain A does not match. Without another chain, that path **is not protected by any Spring Security chain**. A fallback or single overarching chain is needed.

**Question 2.** Chain A `@Order(1)` matches `/api/**` and requires `ROLE_USER`. Chain B `@Order(2)` matches `/api/admin/**` and requires `ROLE_ADMIN`. Admin lacks `ROLE_USER`. Which chain handles `GET /api/admin/dashboard`?

**Answer:** Chain A handles it because it matches first; the admin request may get 403 for lacking `ROLE_USER`. Chain B is never tried. Fix matchers/order: put the narrow admin chain before the broad API chain, or place the admin rule inside the API chain.

**Question 3.** Inside one chain, `requestMatchers("/api/**").permitAll()` appears before `requestMatchers("/api/admin/**").hasRole("ADMIN")`. What happens to admin paths?

**Answer:** The broad rule matches first and allows them, so the admin rule is never evaluated. Reorder the rules and restrict `permitAll` to genuinely public endpoints.

**Question 4.** Is `anyRequest().denyAll()` always safe if no other rules are configured?

**Answer:** It denies all requests **selected by the current chain**, yet has no effect on paths outside the chain. Moreover, deny-all can prevent login, error handling, and needed assets from running; design an appropriate allowlist.

**Question 5.** On a REST API POST, a user has `REPORT_WRITE` yet receives 403. Is `securityMatcher` wrong?

**Answer:** Not necessarily. The request may have selected the right chain, while `CsrfFilter` blocked it for missing a token, or another policy denied it. Check logs and test with/without `csrf()` before changing matchers.

**Question 6.** When you only need `/api/admin/**` restricted to ADMIN and `/api/user/**` restricted to USER while every route shares the same HTTP Basic filter, do you need two SecurityFilterChains?

**Answer:** Usually no. One chain with two properly ordered `requestMatchers` and `anyRequest().denyAll()` suffices; splitting chains helps when filter sets or security mechanisms truly differ between groups.

**Question 7.** You use `securityMatcher("/secured/**")` + `formLogin(withDefaults())`, and `GET /login` fails. Why?

**Answer:** `/login` does not match `/secured/**`, so the filter in that chain cannot serve the default login URL. Design login endpoints inside a properly protected/permitted scope and provide a controller if using a custom login page.

## 14. Key Takeaways

- **Select the chain first, authorize the request second.** `securityMatcher` and `requestMatchers` are not interchangeable.
- **Two first-match steps:** only the first matching chain runs; only the first matching rule in that chain decides HTTP authorization.
- **`anyRequest` lives only inside the current chain**; a catch-all fallback is critical when using multiple chains.
- **Filters do not accumulate across chains.** Each chain must independently configure authentication, CSRF, headers, and appropriate policies.
- **Split into multiple chains only when filter-level differences are needed;** if only URL permissions differ, multiple rules in one chain are easier to reason about.
- **Test denial cases too** and enforce owner/tenant checks in services, because URL policies alone do not guarantee per-resource authorization.

## References

- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity, securityMatcher vs requestMatchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HTTP Requests, Security Matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Servlet Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — MockMvc Security Test Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — MockMvc CSRF Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Boot 3.5.16 release and OSS support](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
