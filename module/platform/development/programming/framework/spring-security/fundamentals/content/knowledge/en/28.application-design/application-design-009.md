# Reviewing Configuration When Adding Endpoints, Roles, or Login Methods

## 1. Why does every small change require a security review?

In a Spring Security application, adding a controller, opening another role, or enabling a new login method can alter **who can access which resources, with which identity kind, and through which filter chain**. Issues rarely stem from a syntax error on one line; they come from gaps between layers: a URL routes properly yet misses `SecurityFilterChain`; a new role is granted too broadly; or a new login mechanism accidentally bypasses checks meant for another flow.

Consider three seemingly independent changes:

- The product team adds `POST /api/reports` to create reports. They only configured rules for `GET /api/reports/summary` and assumed other requests were safe automatically.
- The admin team adds the `REPORT_EDITOR` role. They only updated the role list in the IdP and forgot to check `ROLE_` mapping, role hierarchy, and actual data-operation permissions.
- The platform team enables HTTP Basic, OIDC, or Bearer tokens in an app that previously only had form login. They added the new mechanism without verifying which requests may authenticate with which method, plus CSRF, sessions, redirects, and error handling.

**Configuration review** is the process of comparing intended policy against **how every request is actually handled**, including normal requests, missing authentication, missing permissions, wrong HTTP methods, and undeclared paths. The goal is to **grant exactly the required access without unintentionally expanding the attack surface**.

This lesson belongs to the **Application Design** group of **Spring Security – fundamentals**, using Spring Security Servlet, Java 17+, and Spring Boot 3.x/Spring Security 6.x. For WebFlux, use the corresponding reactive APIs; `HttpSecurity` examples here do not apply directly.

### Learning outcomes

After this lesson, you will be able to:

1. Identify the exact impact of adding an endpoint, changing a role, or adding a login mechanism.
2. Distinguish `SecurityFilterChain` scope from rule ordering inside `authorizeHttpRequests`.
3. Establish a **deny-by-default** policy and test both allowed and forbidden cases.
4. Distinguish `hasRole`, `hasAuthority`, HTTP methods, endpoint-level policies, and service-layer data security.
5. Verify CSRF, CORS, sessions, cookies, redirects, and 401/403 errors when changing login mechanisms.
6. Write regression tests proving a change does not open access on other URLs, roles, or flows.

## 2. Review model: what changed, and how far does the impact reach?

A security change should be described across at least six dimensions:

| Dimension | Question to answer |
| --- | --- |
| **Resource** | Which URLs, HTTP methods, controllers, services, tenants, and data are affected? |
| **Identity** | Anonymous, browser user, service account, or third-party token? Who authenticates it? |
| **Permissions** | Which roles, authorities, scopes, owner/tenant checks, and business conditions allow the action? |
| **Security chain** | Which `SecurityFilterChain` is selected? Does it include the required auth/CORS/CSRF/authorization filters? |
| **State** | What happens to sessions, cookies, CSRF tokens, remember-me, refresh tokens, logout, and lifetimes? |
| **Error contract** | Do 401, 403, login redirects, `WWW-Authenticate`, and JSON responses match the contract? |

Three change types carry distinct **risk signatures**:

| Change type | Common mistakes | Acceptance evidence |
| --- | --- | --- |
| **Adding an endpoint** | Missing rule, overly broad rule, protecting GET while forgetting POST/DELETE, skipping object authorization. | URL × method × actor matrix with allow and deny cases. |
| **Adding/editing a role** | Wrong `ROLE_` prefix mapping, new role unintentionally inheriting admin, old tokens not updated/revoked. | Per-role permission tests, missing-permission tests, and same-resource different-owner tests. |
| **Adding a login mechanism** | API implicitly accepts sessions, browser accepts Bearer like admin, login endpoint outside chain, 302 instead of 401. | Chain-isolation tests, valid/invalid auth, CSRF/CORS, 401/403, session/logout. |

Never start by adding `permitAll()` just to "test-run the endpoint." Write down **who may do what** first, then modify configuration.

## 3. Boundaries to verify when using Spring Security Servlet

### 3.1. Servlet filter chain and SecurityFilterChain

Simplified flow:

```text
HTTP request
    |
    v
Servlet container filters
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |
    +-- SecurityFilterChain @Order(1): e.g., /api/**
    |        -> security filters -> AuthorizationFilter
    |
    +-- SecurityFilterChain @Order(2): browser/fallback
             -> security filters -> AuthorizationFilter
    |
    v
DispatcherServlet -> Controller -> Service
```

`FilterChainProxy` selects **the first `SecurityFilterChain` whose matcher matches**. It **does not combine all chains** that match a request. If an `@Order(1)` chain catches `/api/**`, `/api/**` requests will not continue into the browser fallback chain.

Important trap: `http.securityMatcher("/api/**")` restricts the **entire chain**. If you add an endpoint outside that path without a fallback chain, the endpoint may **go unprotected by Spring Security**. Conversely, if the fallback chain uses `anyRequest().permitAll()`, you have accidentally made a new URL public.

**Recommended strategy:** specify narrow matchers for priority chains, keep a fallback chain with an explicit policy, and avoid accidental public exposure.

### 3.2. `securityMatcher` differs from `requestMatchers`

```java
http
    .securityMatcher("/api/**")                // Select chain
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()    // Select rules inside chain
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
    );
```

- `securityMatcher` determines whether a request uses this chain.
- `requestMatchers` inside `authorizeHttpRequests` determines **the first matching rule** applied **inside the selected chain**.
- `permitAll()` permits per the authorization rule yet **does not skip other security filters**. Protections such as security headers, CSRF, CORS, and custom filters may still apply.
- `web.ignoring()` bypasses the Spring Security filter chain for selected paths; evaluate carefully because header/security protections are lost too. For endpoints or public static resources, prefer `permitAll()`.

### 3.3. Rule ordering can widen permissions

Commonly buggy configuration:

```java
// WRONG in intent: broad rule comes first, making the admin rule below unreachable.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

If `/api/admin/users` matches the first rule, Spring Security only requires login instead of the ADMIN role.

The proper order must go **from specific to general**:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
```

Review any broad rules placed earlier and check separate matchers per HTTP method. `GET /orders` differs in impact from `POST /orders`; a broad `requestMatchers("/orders/**").authenticated()` can grant write access to someone who should only read.

### 3.4. Dispatchers and the method/object layer

HTTP requests can involve `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC` dispatchers. Spring Security 6 uses `AuthorizationFilter` to evaluate relevant request dispatches per configuration. When error pages or forwards are blocked, consider appropriate `dispatcherTypeMatchers` policies—never work around it with `anyRequest().permitAll()`.

Even when an HTTP rule allows `GET /api/orders/{id}` for the VIEWER role, the backend must still verify **whether that order belongs to a tenant/user allowed to view it**. Endpoint authorization does not automatically replace object-level authorization or service-layer permission checks. When multiple code paths call the same service, you can use method security such as `@PreAuthorize` after enabling `@EnableMethodSecurity`, or check permissions directly in the domain/service layer.

## 4. Adding an endpoint: define the policy before adding the controller

Review template when adding an endpoint:

```text
Endpoint: POST /api/reports
Effect: creates a new report
Actor: employee with role REPORT_EDITOR
Authentication: API HTTP Basic in learning example; production considers tokens
Authorization: ROLE_REPORT_EDITOR + creation permission in matching tenant
CSRF: Enabled in example because browsers can auto-send Basic
Body: data validated and size-limited
Response: 200/201 per contract, containing no secrets/stacktraces
Missing authentication: 401 (API)
Authenticated but missing role: 403
Wrong method/unknown URL: must not open access
Tests: editor OK; viewer 403; no credentials 401; no CSRF 403
```

When reviewing changes, build a permission table first:

| HTTP request | Anonymous | REPORT_VIEWER | REPORT_EDITOR | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/reports/summary` | 401 | 200 | 200 | 403 if ADMIN lacks report role |
| `POST /api/reports`, valid CSRF | 401 | 403 | 200 | 403 if ADMIN lacks report role |
| `POST /api/reports`, missing CSRF | 403 from CSRF filter | 403 | 403 | 403 |
| `DELETE /api/reports/7` | Denied | Denied | Denied | Denied |
| `GET /api/unknown` | Denied | Denied | Denied | Denied |

Exact statuses depend on **the filter chain and API contract**. For instance, Spring Security may return 401 for anonymous GET, 403 for authenticated users lacking authority, and 403 for POST missing/invalid CSRF even before authorization runs. In form-login web apps, anonymous requests may get a **302 redirect to `/login`** instead of 401. Never impose identical expectations on APIs and web pages.

### 4.1. Reconcile both URL and HTTP method

Things easily missed:

- Allowing `GET /api/reports` does **not** automatically allow `POST /api/reports`.
- Adding `@DeleteMapping` or `@PatchMapping` to a controller while keeping an overly broad `/api/reports/**` rule can open dangerous permissions.
- A path parameter `{id}` does not automatically grant permission on that resource; ownership/tenant checks are required.
- Avoid URL pattern checks based on `contains("admin")` in custom filters; use proper `RequestMatcher`s and write tests.
- If trailing slashes, encoded paths, context paths, or reverse-proxy rewrites exist, test the actual URL forms delivered by infrastructure to Spring MVC.
- When adding webhooks, file uploads, or streams, check request body sizes, MIME types, replay protection, signatures, and rate limits.
- On create/update endpoints, never pass credentials or tokens in URLs or logs for debugging convenience.

### 4.2. Public endpoints still need protection

A health check or public catalog may use `permitAll()`, yet still requires CORS policies, security headers, rate limits, data minimization, and validation. **Public** does not mean permitted to return sensitive data or bypass the entire security chain. Expose only the exact URLs and methods required.

## 5. Adding roles: review authority mapping and permission bounds

### 5.1. `hasRole` differs from `hasAuthority`

In common configuration:

```java
.requestMatchers("/ui/admin/**").hasRole("ADMIN")
```

`hasRole("ADMIN")` typically requires the `ROLE_ADMIN` authority (Spring Security prepends the default role prefix). Meanwhile:

```java
.requestMatchers("/api/reports/**").hasAuthority("REPORTS_READ")
```

`hasAuthority("REPORTS_READ")` compares the exact authority string without prepending `ROLE_`.

If `UserDetails` is constructed via:

```java
User.withUsername("editor")
    .password(encodedPassword)
    .roles("REPORT_EDITOR")
    .build();
```

it grants the `ROLE_REPORT_EDITOR` authority under the default prefix. When calling `hasRole("REPORT_EDITOR")`, **do not write `hasRole("ROLE_REPORT_EDITOR")`** unless you explicitly configured a custom role prefix. When IdP-issued tokens use `scope`, scopes typically map to authorities shaped like `SCOPE_...` and require matching rules; **never assume JWT scopes equal user roles**.

### 5.2. New roles do not automatically inherit by name

There is no default hierarchy implying:

```text
ROLE_ADMIN > ROLE_REPORT_EDITOR > ROLE_REPORT_VIEWER
```

Role names are just strings. If the application requires a role hierarchy, configure and test it separately. Otherwise, an account holding only `ROLE_ADMIN` **does not automatically have** `ROLE_REPORT_EDITOR` in a `hasRole("REPORT_EDITOR")` check.

In the hands-on example, the policy intentionally **does not infer report permissions from ADMIN**. That choice emphasizes granting permissions **explicitly** and avoiding unreviewed assumptions that "admin can always do everything." Real systems may adopt a hierarchy, provided it is documented and tested.

### 5.3. When roles change at the IdP or database

Check:

1. Is the role source a database, LDAP, IdP, JWT claim, or custom mapper?
2. When a role is removed from an account, do **still-valid** sessions/JWTs retain the old permission until expiration?
3. Do `UserDetailsService`, session, JWT, and API gateway caches need invalidation/revocation?
4. Are roles scoped by environment, tenant, and resource boundaries?
5. Does the new role require MFA or step-up authentication?
6. Who approves grants, expiration, change logs, and revocation workflows?
7. When the required role is absent, does the backend return 403 or follow a special business flow?

**Never solve this by using `anyRequest().authenticated()` and checking roles in the frontend.** A user can call the API directly and bypass the UI.

### 5.4. HTTP, method, and object-level authorization layers

HTTP rules are the first gate, not a substitute for business authorization. For example:

```java
// Excerpt inside service, meaningful only when @EnableMethodSecurity is enabled
// and the permissionService variable is injected from a real bean.
@PreAuthorize("@permissionService.canReadOrder(authentication, #orderId)")
public OrderDto getOrder(long orderId) {
    return orderRepository.findDto(orderId);
}
```

This is a **separate illustration**, not a standalone runnable method in the demo below. To apply it, declare the `permissionService` bean, repository, and DTO, and ensure proxy/method-security interception actually runs. Write integration tests accessing an order from another tenant to verify object-level access.

## 6. Adding a login method: changing the whole flow, not just adding a filter

When an app that originally had only form login begins supporting HTTP Basic, OAuth2 login, Bearer tokens, or passkeys, you must specify **which requests may use which method**.

| Mechanism | Typical target | What to review |
| --- | --- | --- |
| Form login + `HttpSession` | Interactive browser users | CSRF, session fixation, cookies, logout, redirects, and login failures. |
| HTTP Basic | Legacy/limited API needs | HTTPS; browsers can auto-send credentials; CSRF for unsafe requests; never use human passwords as service credentials. |
| OAuth2/OIDC login | Users signing in via IdP | Authorization Code + PKCE per client type; state/nonce, callback/login/logout endpoints inside the right chain. |
| Bearer/JWT Resource Server | APIs receiving access tokens | Signature, issuer, audience, expiry, scope, 401/403, `WWW-Authenticate`; manage tokens separately from sessions. |
| OAuth2 Client Credentials | Workloads calling APIs automatically | Client identity, secret/cert or workload federation, minimal scopes, TTL, and revocation. |
| Passkey/WebAuthn | Interactive users | Challenge/origin/RP ID, account binding, recovery, session lifecycle, and step-up. |

Key design points:

- **Form login** may return `302 /login` for unauthenticated callers. **JSON APIs** typically want clear 401/403 responses. If both mechanisms live in one chain, verify exactly which entry point handles each request.
- **Separating `SecurityFilterChain` by URL** keeps API and browser behavior distinct; remember login/logout/callback URLs must be handled by the matching chain. If a chain matches only `/ui/**` while the login filter listens at `/login`, `POST /login` may fall **outside** that chain.
- If an API **only** accepts Bearer tokens explicitly attached in headers by clients and uses no browser auto-sent credentials, you can design that stateless chain with CSRF disabled after review. If an API uses **cookies or HTTP Basic in browsers**, never assume "stateless = exempt from CSRF."
- CORS is not authorization: for cross-origin frontends, `http.cors()` must handle preflight before authentication; never add wildcard origins to fix 401 errors.
- `OAuth2ResourceServer` validates caller tokens; `OAuth2Client` requests tokens to call downstream APIs; `oauth2Login` handles interactive user sign-in. Those three capabilities are not equivalent.
- `HttpSession` logout does not automatically revoke already-issued JWTs/access tokens. Re-test refresh/revocation/session behavior against the exact contract.
- With multiple login methods, maintain defenses against **improper account linking**, session fixation, credential stuffing, login CSRF, and confused deputy attacks.

## 7. Complete example: two chains, explicit roles, and deny-by-default

We build a learning app with two groups:

**API `/api/**`:** uses HTTP Basic over HTTPS in the example; has two report roles. Keeps CSRF enabled for unsafe methods because browsers can auto-attach Basic credentials. The API sets `SessionCreationPolicy.STATELESS`, yet that **does not automatically exempt CSRF**. For production M2M, prefer OAuth2 Bearer/mTLS over passwords.

**Browser `/ui/**`:** uses form login + sessions; has a home page for authenticated users and an admin page restricted to `ROLE_ADMIN`. A fallback rule denies undeclared URLs.

When adding endpoints/roles/logins, we will use the test suite itself to prove no unintended permissions were opened.

### 7.1. Libraries and layout

A **Spring Boot 3.x / Spring Security 6.x / Java 17+** project with Gradle plugin and wrapper. Add these dependencies in `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the **`dependencies` block inside a Boot project that already applies plugins**, not a full build script. Create the following classes in package `demo.securityreview`.

### 7.2. Entry-point class

File `src/main/java/demo/securityreview/SecurityReviewApplication.java`:

```java
package demo.securityreview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityReviewApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityReviewApplication.class, args);
    }
}
```

### 7.3. Spring Security configuration

File `src/main/java/demo/securityreview/SecurityConfig.java`:

```java
package demo.securityreview;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/summary"
                ).hasAnyRole("REPORT_VIEWER", "REPORT_EDITOR")
                .requestMatchers(
                    HttpMethod.POST, "/api/reports"
                ).hasRole("REPORT_EDITOR")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // INTENTIONALLY do not disable CSRF on Basic API:
        // browsers can automatically attach HTTP Basic credentials.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/error"
                ).permitAll()
                .requestMatchers(
                    "/ui/admin/**"
                ).hasRole("ADMIN")
                .requestMatchers(
                    "/ui/**"
                ).authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/ui/home", true)
            )
            .logout(Customizer.withDefaults());

        // This fallback chain has no securityMatcher, covering remaining URLs.
        // CSRF stays enabled by default for browsers.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-demo"))
                .roles("REPORT_VIEWER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-demo"))
                .roles("REPORT_EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-demo"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Why is this configuration intentional?**

1. `@Order(1)` and `securityMatcher("/api/**")` route the API branch to the API chain; the browser chain does not interfere with the API once matched.
2. `@Order(2)` is a fallback without a restricting matcher, keeping all remaining URLs under security control. `anyRequest().denyAll()` at the end prevents unreviewed new URLs from "opening up."
3. `GET /api/public/ping` is public, yet **GET only**. Other HTTP methods hitting the same URL are not automatically permitted.
4. `GET /api/reports/summary` is for VIEWER or EDITOR. `POST /api/reports` is solely for EDITOR; the policy **does not** infer that ADMIN always holds report permissions.
5. `SessionCreationPolicy.STATELESS` applies to the API: sessions are not used to store `SecurityContext`. HTTP Basic can still be auto-attached by browsers; therefore **CSRF remains enabled**. When deploying a real API, design CSRF token issuance/submission for cookie/Basic clients, or adopt a Bearer architecture without ambient credentials and review before changing policy.
6. The browser chain retains form login, redirects, and CSRF. `/login` sits inside the fallback chain so the form login filter handles that endpoint.
7. If admin has not been granted `ROLE_REPORT_EDITOR`, they cannot POST reports. Letting ADMIN have EDITOR rights is **a design requirement that must be approved**, not an automatic consequence of the role name.
8. Passwords in this example are strictly for testing; never use fixed credentials in production. HTTP Basic requires TLS and proper brute-force protection.

### 7.4. Controller

File `src/main/java/demo/securityreview/DemoController.java`:

```java
package demo.securityreview;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("result", "pong");
    }

    @GetMapping("/api/reports/summary")
    public Map<String, Integer> summary() {
        return Map.of("count", 2);
    }

    @PostMapping("/api/reports")
    public Map<String, Boolean> createReport() {
        return Map.of("created", true);
    }

    @GetMapping("/ui/home")
    public Map<String, String> home(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/ui/admin/panel")
    public Map<String, Boolean> adminPanel() {
        return Map.of("admin", true);
    }
}
```

Note: the controller returns `Map` for simple JSON checks without database dependencies. A real system still needs input validation, transactions, object-level permissions, auditing, rate limiting, and data controls. Never infer that protecting an HTTP path automatically permits access to every record in the service.

### 7.5. Accurate error statuses per flow

| Request | Mechanism | State | Expected |
| --- | --- | --- | --- |
| `GET /api/reports/summary` without credentials | Basic API | Unauthenticated | 401 and appropriate Basic challenge. |
| `GET /api/reports/summary` as viewer | Basic API | Authenticated with role | 200. |
| `POST /api/reports` as viewer + CSRF | Basic API | Authenticated, missing EDITOR role | 403. |
| `POST /api/reports` as editor, missing CSRF | Basic API | Blocked by CSRF protection | 403, despite sufficient role. |
| `POST /api/reports` as editor + CSRF | Basic API | Valid role and CSRF | 200. |
| `GET /ui/home` anonymous | Browser form | Not signed in | Typically 302 redirect to `/login`. |
| `GET /ui/admin/panel` as viewer | Browser form | Missing ROLE_ADMIN | 403. |
| `GET /ui/admin/panel` as admin | Browser form | Has ROLE_ADMIN | 200. |

**Do not confuse 302 with 401:** browser form login may redirect, while a Basic API returns 401. If later adding OAuth2 login or JSON APIs, explicitly align the response/redirect contract rather than letting the frontend guess from an HTML login page.

## 8. Regression testing: adding new things without altering old permissions

Spring Security Test provides `httpBasic()`, `csrf()`, `user()`, and `formLogin()` helpers. The demo uses MockMvc with the Spring Security filter chain via `@SpringBootTest` and `@AutoConfigureMockMvc`.

File `src/test/java/demo/securityreview/SecurityReviewTests.java`:

```java
package demo.securityreview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityReviewTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("pong"));
    }

    @Test
    void privateReportWithoutCredentialsRequiresBasicLogin()
            throws Exception {
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("viewer", "viewer-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void editorCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("editor", "editor-demo")))
            .andExpect(status().isOk());
    }

    @Test
    void viewerCannotCreateReportEvenWithValidCsrf()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("viewer", "viewer-demo"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCannotCreateReportWithoutCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanCreateReportWithCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-demo"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.created").value(true));
    }

    @Test
    void administratorIsNotImplicitlyReportEditor() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("admin", "admin-demo"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void undeclaredApiRouteIsRejectedForAuthenticatedUser()
            throws Exception {
        mvc.perform(get("/api/not-declared")
                .with(httpBasic("editor", "editor-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void undeclaredHttpMethodIsRejectedEvenForEditor()
            throws Exception {
        mvc.perform(delete("/api/reports/7")
                .with(httpBasic("editor", "editor-demo"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousBrowserUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/ui/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void viewerCanReadBrowserHome() throws Exception {
        mvc.perform(get("/ui/home")
                .with(user("viewer").roles("REPORT_VIEWER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("viewer"));
    }

    @Test
    void viewerCannotReadAdminPanel() throws Exception {
        mvc.perform(get("/ui/admin/panel")
                .with(user("viewer").roles("REPORT_VIEWER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminPanel() throws Exception {
        mvc.perform(get("/ui/admin/panel")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.admin").value(true));
    }

    @Test
    void validFormLoginRedirectsToBrowserHome() throws Exception {
        mvc.perform(formLogin()
                .user("viewer")
                .password("viewer-demo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/ui/home"));
    }

    @Test
    void httpBasicIsNotAnAlternativeLoginForBrowserChain()
            throws Exception {
        mvc.perform(get("/ui/admin/panel")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Note on redirect URLs:** when testing with MockMvc, `LoginUrlAuthenticationEntryPoint` typically generates an absolute Location `http://localhost/login` in MockMvc's simulated environment. If your app has a context path, proxy, custom host, or different redirect configuration, assert a pattern/URL matching the real contract. Never replace redirect tests with an assumption that anonymous always returns 403.

Run from the project root where the Gradle wrapper is configured:

```bash
./gradlew test --tests demo.securityreview.SecurityReviewTests
```

The example suite contains **16 tests**. This represents the **document's expected test behavior**, not a claim of execution on the reader's machine. MockMvc tests construct simulated HTTP requests and run the filter chain, without proving all aspects of reverse proxies, browser cookies, or external IdP systems.

**Test coverage by change:**

| Change | Test ensuring new access | Test preventing unintended access |
| --- | --- | --- |
| Adding public GET | Anonymous GET `/api/public/ping` returns 200 | Undeclared DELETE/POST are not opened. |
| Adding report viewer | VIEWER reads summary 200 | VIEWER creating report gets 403. |
| Adding report editor | EDITOR reads and POSTs with CSRF 200 | EDITOR POST missing CSRF gets 403; undeclared DELETE gets 403. |
| Adding/admin role | ADMIN reads UI admin panel | ADMIN does not automatically become REPORT_EDITOR. |
| Enabling Basic for API | HTTP Basic with valid credentials reaches API | API without credentials returns 401, does not redirect to web login. |
| Enabling form login for UI | Form login succeeds, UI roles work | HTTP Basic does not automatically create a browser session. |
| Keeping fallback | New controllers need explicit policy first | Undeclared URLs are denied even when authenticated. |

### 8.1. Why test 401, 403, 302, and 200 together?

- **200** proves legitimate functionality is not broken by mistake.
- **401** proves APIs missing/sending bad credentials challenge according to protocol.
- **403** proves roles/CSRF/default-deny block unauthorized requests.
- **302** (or matching redirect status) proves browsers still follow the form-login flow rather than being altered by API mechanics.
- For creation endpoints, many apps return 201. When updating a controller contract, update assertions to match the intended status and location/body—never change 201 to 200 just to keep an old test green.

**Do not rely solely on `@WithMockUser` to prove login works.** It mocks an `Authentication` to test authorization, without verifying the password encoder, form authentication, or JWT signatures. `formLogin()` tests the login flow at the Spring Security/MockMvc level, while end-to-end login with cookies/MFA/IdP needs dedicated integration tests.

### 8.2. MockMvc does not replace out-of-JVM security testing

The suite above does not automatically verify:

- `Secure`/`HttpOnly`/`SameSite` cookies in real browsers;
- CORS preflight from another origin or gateways handling 401/403 errors;
- JWT issuer/audience/signature when switching to Bearer tokens;
- Race conditions, session fixation, and logout/session timeouts on a real Servlet container;
- Resources cached by CDNs, API gateways, or browser back-forward caches;
- Real data permissions across two tenants and audit logs;
- Reverse proxy path rewrites, hosts/prefixes, and routing edge failures.

These require integration/end-to-end tests in a production-like environment.

## 9. When adding a new login mechanism, which regression tests must be added?

### 9.1. Switching an API from Basic to Bearer tokens

If an API switches from Basic to OAuth2 Resource Server:

- Replace `httpBasic()` with `oauth2ResourceServer(oauth -> oauth.jwt(...))` or the appropriate token mechanism in **the exact API chain**.
- Validate signatures, issuer, audience, expiration, token type, and authority mapping per issuer.
- Test 401 for missing/invalid tokens, 403 for valid tokens lacking scopes, and protocol-compliant `WWW-Authenticate: Bearer` challenges.
- Consider disabling CSRF on the API only if it **does not use** auto-attached cookies/sessions/Basic credentials for unsafe operations. Keep CSRF on the browser chain.
- Write tests preventing browser sessions from substituting for Bearer tokens on `/api/**` and preventing service tokens from accessing human UI pages unless policy permits.
- Verify `Authorization` is never written to URLs, logs, or error responses; Bearer tokens require HTTPS.

**Illustrative method snippet (do not mix directly into the Basic demo):**

```java
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .csrf(csrf -> csrf.disable()) // Only when this API uses Bearer headers exclusively
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll()
    )
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

To run this snippet, the project needs `spring-boot-starter-oauth2-resource-server` and a real `JwtDecoder`/JWK/issuer—you cannot simply paste `oauth2ResourceServer` and assume JWT validation is complete.

### 9.2. Enabling OIDC login for browsers

When adding `oauth2Login()`, review URLs such as `/oauth2/authorization/{registrationId}`, `/login/oauth2/code/{registrationId}`, and logout endpoints. If the browser chain matches only `/ui/**`, authentication endpoints outside that scope may miss the matching filter.

You must test:

- Authorization initiation redirects, callback URI matching the IdP, `state`, PKCE, and `nonce` per protocol.
- Successful login produces the right principal/authorities without auto-granting `ROLE_ADMIN` from unvetted claims.
- Login failures/IdP errors return safe messages without leaking tokens/secrets.
- Session fixation, local logout, IdP logout, and behavior while SSO remains active.
- Account linking: matching emails never prove two accounts belong to the same person unless issuer/subject are verified.
- `/api/**` APIs still return 401/403 per contract without accidentally redirecting to HTML login/IdP.

### 9.3. Adding passkey or MFA login

Verify at two levels:

- **Authentication:** challenges, origin/RP ID, cryptographic verification, anti-replay, account recovery, and session creation.
- **Authorization:** does a passkey/MFA-authenticated session receive the right roles? Do high-risk actions require step-up?

Never auto-grant ADMIN just for "stronger login"; authentication strength and business authorization are two separate concepts.

## 10. Related factors to evaluate after changes

### 10.1. CSRF and method changes

A public GET endpoint should not mutate state. If adding POST/PATCH/DELETE, assess whether browsers auto-send cookies or Basic credentials. In Spring Security Servlet, CSRF is enabled by default to protect state-changing requests. Test:

- POST with a valid token and right role → processed.
- POST with missing or wrong token → 403 before updating data.
- Logout/login follow the proper CSRF lifecycle.
- Never disable CSRF application-wide just to make one POST test pass.

**Note:** `SessionCreationPolicy.STATELESS` alone does not prove an API is immune to CSRF if browsers still auto-send credentials.

### 10.2. CORS and preflight

A frontend on a different origin may need CORS. `OPTIONS` preflight requests normally carry no credentials, so CORS must run before Spring Security demands authentication. Configure `http.cors()`/`CorsConfigurationSource` properly for the chain; never treat `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` as a substitute for a CORS policy.

When using cross-origin cookies, `Access-Control-Allow-Origin` must name specific allowed origins alongside `Access-Control-Allow-Credentials: true` and matching cookie/CSRF policies—never combine wildcard origins with credentials.

### 10.3. Sessions, cookies, remember-me, and logout

Enabling a new login method can create new sessions or change per-request authentication. Review session fixation, idle timeouts, concurrent sessions if applicable, remember-me, and logout. For tokens outside sessions, `HttpSession` logout does not automatically revoke all Bearer tokens.

### 10.4. Error handling and status codes

401 from Basic/Bearer typically needs `WWW-Authenticate`; 403 indicates missing permissions or other defenses such as CSRF. Form login may return a redirect. Never collapse every outcome into 200 + error JSON, and never let exceptions containing credentials/tokens leak to browsers.

### 10.5. Logging, auditing, and sensitive data

Review logs/traces when adding new logins: never log raw `Authorization`, `Cookie`, `Set-Cookie`, passwords, OAuth codes, refresh tokens, or CSRF tokens. Log route templates, safe correlation IDs, actor types, ALLOW/DENY decisions, and standardized error codes. For new roles, audit permission grants and revocations.

### 10.6. Caching and stale permissions

Changing a role in the IdP or database does not immediately change permissions inside already-issued JWTs or sessions. Define TTLs/revocation/invalidation, especially when revoking sensitive permissions. If caching data per user/tenant, prevent stale responses from being shared improperly after role/session changes.

## 11. Pull request review playbook for security changes

Before merging a change:

**Step 1 — Describe the change set.** List which endpoints/roles/login mechanisms are added, modified, or removed, along with actors and business purpose. With multiple services, specify which service issues tokens and which verifies them.

**Step 2 — Trace the request path.** For every URL/method, identify matchers, `SecurityFilterChain`, authentication filters, CSRF/CORS, `AuthorizationFilter`, controllers, method security, and data access.

**Step 3 — Update the permission matrix.** List anonymous, user roles, service principals, and cross-tenant cases. Test not only roles that have access, but also roles that **must be denied**.

**Step 4 — Enforce deny-by-default.** Specific rules before broad rules; fallback chain covers URLs outside specialized chains; unknown URLs/methods never open unintentionally.

**Step 5 — Verify identity data.** Roles/authorities/claims come from verified authentication systems, never from request bodies or arbitrary headers; verify `ROLE_`/`SCOPE_` mapping conventions.

**Step 6 — Check side effects.** CSRF, CORS preflight, cookies, redirects/login pages, logout/sessions, remember-me, caching, and 401/403 errors. If enabling OAuth, check callbacks and token issuer/audience.

**Step 7 — Run regression tests.** At least one allow case and multiple deny cases per change, plus old roles, undeclared URLs, out-of-scope methods, and other actors.

**Step 8 — Observability and rollback plan.** Enable config logging in test environments to inspect filter chains, monitor 401/403/5xx shifts during rollout, and prepare rollback. Never enable `TRACE` logging with tokens/cookies in production.

### Short template for pull requests

```text
Security Change Review
- Endpoint / HTTP method:
- Actor type:
- Auth mechanism:
- Matching SecurityFilterChain:
- Required authority/role/scope:
- Data ownership/tenant rules:
- CSRF/CORS/session/cookie impacts:
- 401/403/redirect contract:
- Positive tests:
- Negative tests:
- Existing behavior intentionally unchanged:
- Auditor/reviewer and rollback plan:
```

This is a descriptive template; never treat filling out a form as a substitute for real testing.

## 12. Common mistakes

1. **Placing `/api/**.authenticated()` before `/api/admin/**.hasRole("ADMIN")`.** The broad rule wins; order from specific to general.
2. **Thinking `securityMatcher` and `requestMatchers` are the same.** One selects the chain; the other selects policies inside the chain.
3. **Having no fallback chain or using `permitAll()` as fallback.** New endpoints may bypass security or open publicly.
4. **Believing `permitAll()` disables all filters.** It does not disable CSRF, CORS, headers, or custom filters.
5. **Adding POST while testing only GET.** Review HTTP methods, CSRF, and write permissions.
6. **Assuming `ROLE_ADMIN` has every permission without defining a hierarchy.** Higher-sounding role names do not automatically grant all authorities.
7. **Mixing up `hasRole("ADMIN")` and `hasAuthority("ADMIN")`.** Verify the `ROLE_` prefix and actual authority granting.
8. **Having role-level access without object-level access.** Enforce tenant/owner checks at the data/service layers.
9. **Enabling Basic, cookies, or remember-me and disabling CSRF because the API is "stateless."** Browsers may auto-send credentials; analyze by credential transport.
10. **Adding login endpoints outside the security chain.** Login/redirect/callback filters may never be invoked.
11. **Enabling OAuth2 login and making all APIs redirect to the IdP.** JSON APIs and browsers need separate entry points by design.
12. **Believing `@WithMockUser` proves JWTs were signed and verified.** Mock authentication tests authorization only.
13. **Allowing all origins to "fix 401."** CORS does not grant permissions; diagnose CORS and authentication separately.
14. **Forgetting to revoke/invalidate when removing a role.** Existing sessions or JWTs can retain privileges until expired or revoked.
15. **Testing only happy paths.** The highest risk lies in unpermitted users/roles/methods slipping through.
16. **Ignoring logs/error contracts when adding login.** Easily leaks tokens, cookies, passwords, or internal system details.

## 13. Hands-on exercise

A system has new requirements:

- Users with `ROLE_SUPPORT` may view `GET /api/tickets/{id}` if the ticket belongs to a tenant they serve.
- Users with `ROLE_TICKET_EDITOR` may `PATCH /api/tickets/{id}` but cannot delete tickets.
- A worker needs to call `POST /api/m2m/ticket-sync` using client credentials rather than an employee session.
- Interactive users begin signing in via OIDC alongside the legacy form login.

Build a policy table answering:

1. Which chains handle `/api/tickets/**`, `/api/m2m/**`, `/ui/**`, and `/login/oauth2/code/**`? Is there a fallback covering remaining URLs?
2. Which rules must come first so a broad `authenticated()` never shadows specific `hasRole`/`hasAuthority` rules?
3. Does reading tickets enforce tenant/owner checks in the service?
4. Does PATCH need CSRF when using sessions/cookies? How does policy differ when the M2M API accepts only Bearer headers?
5. Do service tokens validate issuer, audience, scope, and principal kind? Can they access the employee UI?
6. Are OIDC logins mapped to appropriate authorities without auto-granting ADMIN?
7. Which 200, 201, 302, 401, 403, and 404 cases need testing? Should APIs return JSON or redirects?
8. When `ROLE_TICKET_EDITOR` is revoked, how soon do existing sessions/JWTs lose permission?
9. Can browser UI alone "hide the Delete button" instead of backend authorization? **No.**
10. When an unauthorized request is rejected, do logs include a correlation ID for investigation without storing real tokens/cookies?

Write regression tests covering at least: SUPPORT right tenant; SUPPORT wrong tenant; EDITOR PATCH succeeds; EDITOR missing CSRF blocked; DELETE denied; worker valid token; worker token wrong audience/scope; user session calling M2M blocked; anonymous API; login callback and fallback URLs.

## 14. Conclusion and references

**No change to an endpoint, role, or login mechanism is ever "just a one-line edit"** when security policy spans multiple layers. A thorough review identifies **selected chain, first matching rule, identity source, authorities, data permissions, CSRF/CORS, sessions, and error behavior**—and proves it with both positive **and** negative tests. Without an approved rule, **deny by default** is safer than opening access.

Official documentation for reference when upgrading Spring Security:

- Spring Security — [Java Configuration and multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- Spring Security — [Authorize HttpServletRequests, matcher precedence and denyAll](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- Spring Security — [CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- Spring Security — [Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).
- Spring Security — [CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- Spring Security — [OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/).
- OWASP — [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
- OWASP — [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).