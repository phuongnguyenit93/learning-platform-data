# Configuring httpBasic, Realm, and WWW-Authenticate Responses

> **Context:** Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC on the **Servlet stack**. This lesson focuses on enabling HTTP Basic via `HttpSecurity.httpBasic(...)`, configuring a **realm** with `BasicAuthenticationEntryPoint`, understanding the **`WWW-Authenticate`** header, distinguishing 200/401/403, and verifying with `curl` and `MockMvc`. Examples use in-memory accounts for localhost; never use sample passwords or unencrypted HTTP in production.

## 1. Learning Objectives

You will be able to:

1. Explain the pair of headers: `Authorization: Basic ...` on the **request** and `WWW-Authenticate: Basic realm="..."` on the **response**.
2. Enable `httpBasic` in Spring Security 6 using the lambda DSL (without deprecated `WebSecurityConfigurerAdapter`).
3. Set a fixed, meaningful realm and observe HTTP **401 Unauthorized** with a challenge when unauthenticated or given wrong credentials.
4. Distinguish **401** (valid credentials required) from **403 Forbidden** (authenticated but lacking permissions).
5. Write automated tests proving the header/status and avoid confusing security configuration errors with routing issues.
6. State the security limits of Basic: Base64 **does not encrypt data**, TLS must be used, and clients often resend credentials on subsequent requests.

## 2. What Is HTTP Basic?

HTTP Basic is an **HTTP authentication scheme**. When sending credentials, the client creates a `username:password` string, Base64-encodes it, and attaches it to the request header:

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Authorization: Basic bGVhcm5lcjpkZW1vLXBhc3M=
```

This Base64 string corresponds to the sample credentials: `learner:demo-pass`. It is **not encryption**, not a signature, and not an expiring access token: anyone who reads the header can decode the credentials. Therefore, **HTTPS is mandatory** when deploying outside a personal machine, even on internal networks.

For a resource requiring authentication when valid credentials are not yet present, the server returns **401** with a **challenge** telling the client which authentication type to use:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="TrainingAPI"
```

Meaning of each part:

- **`HTTP/1.1 401 Unauthorized`:** historically named “Unauthorized”, yet usually means the request has not been **validly authenticated**.
- **`WWW-Authenticate`:** a response header from the server describing one or more schemes the client can use to authenticate. For Basic, the challenge includes the `Basic` scheme and the `realm` parameter.
- **`realm="TrainingAPI"`:** the name of the *protection space* chosen by the server; helps the user agent understand the credential scope for the challenge. It is **not a password, role, trusted tenant ID, or an authorization check**.
- **`Authorization: Basic ...`:** the request header a client sends when attempting authentication. It **does not appear automatically just because the server enabled httpBasic**; the client must supply credentials or respond to the challenge.

The same URL can involve two request rounds: first without `Authorization` → 401 + challenge; client resends with `Authorization` → server checks username/password and either allows it through or returns 401 again.

### Realm Is Neither a Username nor a Spring Security Matcher Scope

`realm` is HTTP protocol metadata describing a protection space to the client. Changing `"TrainingAPI"` to `"PrivateArea"` **only changes the challenge the client sees**; it does not change `SecurityFilterChain`, add roles, block endpoints, or manage users.

A realm should be **stable, fixed, short, and clean ASCII**. Never put client-controlled data directly into a realm since it is part of an HTTP header; never use a realm to pass sensitive information. Browsers may store/resend Basic credentials for the protection space they recognize; exact behavior depends on the user agent and can make the “logout” experience differ from form login.

## 3. Servlet Flow: Who Sends 401 and WWW-Authenticate?

In Spring Security Servlet, `BasicAuthenticationFilter` reads an `Authorization` header with the `Basic` scheme, builds an unauthenticated `UsernamePasswordAuthenticationToken`, and calls `AuthenticationManager`. A common manager is `ProviderManager`, which may delegate to `DaoAuthenticationProvider`, `UserDetailsService`, and `PasswordEncoder` to verify the password.

When no credentials are provided, the request still passes through other filters; at the HTTP authorization step, Spring Security detects that the endpoint requires `authenticated()`. `ExceptionTranslationFilter` hands the unauthenticated case to `AuthenticationEntryPoint`. For Basic, `BasicAuthenticationEntryPoint` sends HTTP **401** along with `WWW-Authenticate`.

When credentials are invalid, `BasicAuthenticationFilter` itself may catch `AuthenticationException` and invoke the configured entry point. When credentials are valid but lack a required role, the authorization step typically returns **403** via `AccessDeniedHandler`; this is **not** a request to resend a password.

```mermaid
flowchart TD
    A[HTTP client] --> B[Servlet Container]
    B --> C[Spring Security filter chain]
    C --> D{Has Authorization Basic?}
    D -->|Yes| E[BasicAuthenticationFilter]
    E --> F[AuthenticationManager / AuthenticationProvider]
    F -->|Invalid credentials| J[BasicAuthenticationEntryPoint: 401 + WWW-Authenticate]
    F -->|Valid| G[Authenticated principal]
    D -->|No| H[Continue to authorization]
    G --> H
    H --> I{authorizeHttpRequests rules}
    I -->|Public permitAll| K[Spring MVC controller]
    I -->|Unauthenticated, login required| J
    I -->|Logged in but insufficient permission| L[403 Forbidden]
    I -->|Authorized| K
    K --> M[200 + response body]
```

**Important point:** `permitAll()` allows anonymous access at the authorization step, but **does not disable BasicAuthenticationFilter**. Thus, a client sending an **invalid** `Authorization: Basic` header even to a public endpoint can receive **401**, even though the same endpoint without any header returns 200.

## 4. Configuring a Spring Boot 3.x Project for Practice

Create a project from Spring Initializr with **Java 17 or 21**, **Spring Boot 3.x**, Gradle (Groovy DSL), and dependencies **Spring Web**, **Spring Security**, **Spring Boot Starter Test**, and **Spring Security Test**. The corresponding dependencies inside `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the **dependencies block**, not the full `build.gradle`; plugins, repositories, and the Boot version are provided by the Initializr project. Keep the included Gradle wrapper with the project.

File layout to create:

```text
src/
├── main/java/com/example/basic/
│   ├── BasicDemoApplication.java
│   ├── BasicSecurityConfig.java
│   └── DemoController.java
└── test/java/com/example/basic/
    └── BasicAuthHttpTest.java
```

### 4.1. Startup Class

**`src/main/java/com/example/basic/BasicDemoApplication.java`**

```java
package com.example.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
```

Place the `@SpringBootApplication` class in the root package `com.example.basic` so Spring discovers controllers and security configuration.

### 4.2. Configuring SecurityFilterChain and Realm

**`src/main/java/com/example/basic/BasicSecurityConfig.java`**

```java
package com.example.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationEntryPoint;

@Configuration
public class BasicSecurityConfig {

    @Bean
    BasicAuthenticationEntryPoint basicEntryPoint() {
        BasicAuthenticationEntryPoint entryPoint =
                new BasicAuthenticationEntryPoint();
        entryPoint.setRealmName("TrainingAPI");
        entryPoint.afterPropertiesSet();
        return entryPoint;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            BasicAuthenticationEntryPoint basicEntryPoint
    ) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest()
                            .authenticated()
                )
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(basicEntryPoint))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(basicEntryPoint))
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}
```

**Explanation of each security-relevant part:**

1. **`basicEntryPoint()`** declares a `BasicAuthenticationEntryPoint` bean with realm `"TrainingAPI"`. `setRealmName(...)` sets the protection space name, and `afterPropertiesSet()` validates the realm configuration. When `commence(...)` is called, the entry point sends HTTP **401** and `WWW-Authenticate: Basic realm="TrainingAPI"`.
2. **`authorizeHttpRequests`** makes `GET /api/public` public; `GET /api/admin` requires `ROLE_ADMIN`; all remaining requests must be authenticated. Matcher order matters: specific rules before `anyRequest()`.
3. **`httpBasic(basic -> basic.authenticationEntryPoint(...))`** enables HTTP Basic for this chain and supplies the entry point handling HTTP Basic authentication failures.
4. **`exceptionHandling(ex -> ex.authenticationEntryPoint(...))`** uses the same entry point to handle unauthenticated access to protected endpoints. Configuring both explicitly keeps the challenge consistent for requests without credentials and requests with invalid credentials in this lesson.
5. **Form login is not enabled** in the demo chain, so protected endpoints do not redirect to `/login`. This is an intentional choice for `curl`/API clients.
6. **PasswordEncoder** uses Spring Security's standard encoding mechanism; passwords are encoded before entering the in-memory user store. Never store plaintext passwords in real deployments.
7. **`roles("ADMIN")`** creates authority `ROLE_ADMIN`, matching `hasRole("ADMIN")`. User `learner` lacks this role.

Do not call `csrf.disable()`: all primary tests in this lesson use `GET`, so there is no need to disable CSRF protection. When extending to `POST`/`PUT`/`DELETE`, decide CSRF policy based on sessions/cookies and how clients send credentials. HTTP Basic **does not automatically make POST requests safe from CSRF**.

**Remember:** `BasicAuthenticationEntryPoint` is used to build challenge responses; it **does not verify passwords**. Password verification belongs to `AuthenticationManager`/`AuthenticationProvider`. `realm` serves only the protocol/challenge.

### 4.3. Public, Authenticated, and ADMIN-Restricted Controller

**`src/main/java/com/example/basic/DemoController.java`**

```java
package com.example.basic;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/private")
    public String privateEndpoint(Principal principal) {
        return "PRIVATE_OK: " + principal.getName();
    }

    @GetMapping("/api/admin")
    public String adminEndpoint(Principal principal) {
        return "ADMIN_OK: " + principal.getName();
    }
}
```

The controller only defines routes and bodies; it **does not make a URL public** just by naming the method `publicEndpoint`. Actual rules live in `SecurityFilterChain`. `Principal` reveals the authenticated request's identity once the controller is allowed to execute.

## 5. Running the App and Reading HTTP Responses

In the project directory with the Gradle wrapper:

```bash
# Linux / macOS
./gradlew bootRun

# Windows PowerShell
.\gradlew.bat bootRun
```

Once running, the embedded Servlet container typically listens on `http://localhost:8080` if `server.port` is unchanged. Open a second terminal while keeping the app running in the first.

In PowerShell, use `curl.exe` to avoid the `curl` alias in some Windows PowerShell versions. All commands below use **simulated credentials, running on localhost only**.

### Test 1 — Public, No Authorization Sent

```bash
curl -i http://localhost:8080/api/public

# Windows PowerShell:
curl.exe -i http://localhost:8080/api/public
```

**Expected:** HTTP **200 OK**, exact body:

```text
PUBLIC_OK
```

The request still traverses security filters, yet `permitAll()` lets the controller handle it. There is no `WWW-Authenticate` on the 200 response for this endpoint in this sample configuration.

### Test 2 — Protected, No Credentials

```bash
curl -i http://localhost:8080/api/private
```

**Expected:** HTTP **401** with the key header:

```http
HTTP/1.1 401
WWW-Authenticate: Basic realm="TrainingAPI"
```

Do not assume an exact error body because Spring Boot/the container may produce a JSON/HTML error page or empty body depending on the environment. The challenge header and status are what to inspect. `privateEndpoint` was not called.

### Test 3 — Username Present but Wrong Password

```bash
curl -i -u learner:wrong-pass http://localhost:8080/api/private
```

**Expected:** **401**, still containing `WWW-Authenticate: Basic realm="TrainingAPI"`. Even though the client sent `Authorization`, failed authentication causes the entry point to issue the challenge again. Do not distinguish “wrong password” from “non-existent username” in overly detailed messages to prevent user enumeration.

### Test 4 — Valid Username/Password

```bash
curl -i -u learner:demo-pass http://localhost:8080/api/private
```

**Expected:** HTTP **200** and body:

```text
PRIVATE_OK: learner
```

Here `curl -u` generates `Authorization: Basic ...`. `BasicAuthenticationFilter` authenticates and Spring Security forwards the request to Spring MVC. `Principal.getName()` is `learner`.

### Test 5 — Logged In but Missing ADMIN Role

```bash
curl -i -u learner:demo-pass http://localhost:8080/api/admin
```

**Expected:** HTTP **403 Forbidden**, because `learner` only has `ROLE_USER`. This case is already authenticated, so **it is not a new Basic challenge** in the demo's default flow. Resending the same password does not grant additional roles.

### Test 6 — ADMIN Login

```bash
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

**Expected:** HTTP **200** and body:

```text
ADMIN_OK: admin
```

Same `/api/admin` endpoint, yet the outcome changes based on the caller's authorities. `realm` remains `TrainingAPI` and does not decide who is an admin.

### Test 7 — Public Endpoint with Deliberately Invalid Basic Credentials

```bash
curl -i -u learner:wrong-pass http://localhost:8080/api/public
```

**Expected:** **401** in this configuration, because `BasicAuthenticationFilter` processes the present Basic header and fails **before** the `permitAll()` authorization step. Compare with Test 1 (no header → 200) so you do not mistakenly think a public endpoint always lets any bad `Authorization` header through.

## 6. Result Table to Remember

| Request | Authorization header | Expected status | `WWW-Authenticate` | Interpretation |
|---|---|---:|---|---|
| `GET /api/public` | None | **200** | None | Endpoint permits anonymous access |
| `GET /api/private` | None | **401** | `Basic realm="TrainingAPI"` | Unauthenticated, challenge issued |
| `GET /api/private` | Invalid Basic | **401** | `Basic realm="TrainingAPI"` | Authentication failed |
| `GET /api/private` | `learner:demo-pass` | **200** | None | Authenticated and allowed |
| `GET /api/admin` | `learner:demo-pass` | **403** | Typically none | Authenticated but missing `ROLE_ADMIN` |
| `GET /api/admin` | `admin:admin-pass` | **200** | None | Has `ROLE_ADMIN` |
| `GET /api/public` | Invalid Basic | **401** | `Basic realm="TrainingAPI"` | Filter checks header before permitAll |

**Do not test by comparing the entire 401/403 response body:** servers may format it differently across Spring Boot versions, content negotiation, and error handling. What to assert is **status + `WWW-Authenticate` on 401**, and **200 + controller body** when permitted.

### When Does 302 Appear Instead of 401?

With form login configured, a browser may receive `302 Found`, a `Location: /login` header, and be redirected to a login page. That is a different mechanism from HTTP Basic. In our demo we **only enable HTTP Basic and configure an explicit entry point** so 401/challenge behavior is consistent. If an application uses both form login and Basic, inspect request matchers, content negotiation, and which entry point is selected in each context.

## 7. Automated Testing with MockMvc

Alongside manual `curl` tests, you can boot the Spring Boot test context and send requests through Spring MVC + Security filters using `MockMvc`. Test dependencies were added in section 4. Never just call controller Java methods directly: that bypasses `SecurityFilterChain` and `WWW-Authenticate`.

**`src/test/java/com/example/basic/BasicAuthHttpTest.java`**

```java
package com.example.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void protectedEndpointSendsBasicChallenge() throws Exception {
        mvc.perform(get("/api/private"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"TrainingAPI\""));
    }

    @Test
    void invalidPasswordSendsBasicChallengeAgain() throws Exception {
        mvc.perform(get("/api/private")
                    .with(httpBasic("learner", "wrong-pass")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"TrainingAPI\""));
    }

    @Test
    void validBasicCredentialsAllowProtectedEndpoint() throws Exception {
        mvc.perform(get("/api/private")
                    .with(httpBasic("learner", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PRIVATE_OK: learner"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("learner", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("ADMIN_OK: admin"));
    }

    @Test
    void invalidBasicHeaderCanBlockPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public")
                    .with(httpBasic("learner", "wrong-pass")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"TrainingAPI\""));
    }
}
```

Run tests:

```bash
# Linux / macOS
./gradlew test

# Windows PowerShell
.\gradlew.bat test
```

**Expected:** Gradle reports `BUILD SUCCESSFUL` and seven tests pass when the project matches the sample files. This is the **expected outcome when running the project**, not a claim that the code was executed in the documentation environment.

The `httpBasic(...)` test helper builds a real Basic header for `MockMvc`. Asserting `header().string(HttpHeaders.WWW_AUTHENTICATE, ...)` verifies the exact realm rather than checking only status 401. This is valuable when refactoring security config and accidentally dropping the Basic challenge.

## 8. Other Ways to Configure Realm and Key Considerations

### 8.1. When Default Basic Is Enough

Minimal configuration:

```java
http.httpBasic(Customizer.withDefaults());
```

This is a **snippet inside HttpSecurity configuration**, not a standalone Java file. It enables HTTP Basic with defaults, including a framework-configured entry point. If no custom realm is declared, Spring Security's default realm name may appear in the challenge. Do not hardcode a “guessed” realm name into tests; configure an explicit realm when you need a stable contract.

### 8.2. When You Need to Change the Realm

In the demo, replace `entryPoint.setRealmName("TrainingAPI")` with `"OperationsAPI"`, restart, and call `GET /api/private` without credentials. The status remains **401**, but the header changes to:

```http
WWW-Authenticate: Basic realm="OperationsAPI"
```

The realm name does not alter `hasRole`, `permitAll`, endpoints, or user lists. Browsers may handle cached credentials under the new protection space; do not treat changing the realm as a password or session revocation mechanism.

### 8.3. Why Configure the Same Entry Point in Both httpBasic and exceptionHandling?

In HTTP Basic there are at least two reasons a challenge is needed:

- **Invalid credentials in BasicAuthenticationFilter:** the filter already read `Authorization` and authentication failed.
- **No credentials on a protected endpoint:** the filter may not authenticate anyone, and the login requirement is detected when authorization handles the anonymous request.

Configuring the same `BasicAuthenticationEntryPoint` in both places gives consistent challenge control. When building complex apps (with form login, Bearer tokens, multiple security chains), **do not blindly assign one global entry point** for every request type; configure per `SecurityFilterChain` or matching request matcher instead.

### 8.4. Multiple SecurityFilterChains and Different Realms

An application may have separate API and web chains. In that case:

- Use `http.securityMatcher("/api/**")` to scope the API chain; another fallback chain protects non-API URLs.
- Only the **first matching** chain is picked by `FilterChainProxy`. Chain order / `@Order` affects the outcome.
- Chains may use different entry points or schemes, but **realm does not select a chain**. If a URL mistakenly falls into a web chain with form login, the response may be 302 rather than 401.
- Never create a chain solely for `/api/**` and accidentally leave other URLs outside Spring Security. Every sensitive route must be covered by an appropriate chain.

In the single-chain demo, all endpoints belong to the same `SecurityFilterChain`; hence test results can be compared directly.

## 9. Explaining Common Errors

### 9.1. `401` Missing `WWW-Authenticate`

Check whether 401 was produced by `BasicAuthenticationEntryPoint` or by a controller, proxy, or custom error handler. If custom code calls `response.setStatus(401)` without setting the challenge, a Basic client will not receive the authentication requirement. In apps with multiple entry points, verify `exceptionHandling` and `httpBasic` point to the active chain's intended entry point.

Additionally, a proxy/gateway might return 401 before the app or strip headers when forwarding. Compare direct service calls against calls through the gateway, enable only safe HTTP logging, and never log raw Authorization headers in production.

### 9.2. Basic Header Present but Still 401

Verify the hostname/port/path, username/password, password encoding mechanism, and that the client actually sent the header. `Authorization: Basic ...` carries username/password, **different from** `Authorization: Bearer ...`. If using `curl -u`, supply the exact demo credentials.

If passwords are stored as BCrypt while `PasswordEncoder` checks another format, authentication will fail. In real applications, establish clear encoding standards, controlled migrations, and never log passwords to debug.

### 9.3. `GET /api/public` Unexpectedly Returns 401

First try **sending no header**. If a request without credentials returns 200 while sending invalid Basic returns 401, that matches the example's behavior because the Basic filter processes present credentials before `permitAll`.

If **no credentials still returns 401**, check whether the matcher matches the HTTP method and path, whether the `SecurityFilterChain` bean is loaded, whether `server.servlet.context-path`/gateway prefixes exist, and whether another chain intercepts the request first.

### 9.4. `403` Instead of `401`

Authenticated without the required role is typically **403**. When `learner` accesses `/api/admin`, resending the same credentials does not add `ROLE_ADMIN`. On the other hand, `403` on `POST` may be caused by CSRF rather than permissions. Never disable CSRF blindly just to change status codes; inspect the method, cookies/sessions, and CSRF token.

### 9.5. Browser Shows a Popup or Keeps Sending Credentials

Browsers can show a Basic challenge dialog and remember credentials for the protection space. HTTP Basic **has no built-in “logout” equivalent to invalidating a session**. Calling a logout endpoint does not guarantee the browser clears cached credentials; design an appropriate auth mechanism (often form login/OIDC) if the product needs predictable logout.

When debugging, use `curl` or a clean browser profile to avoid stale credentials. Never pass real passwords on command lines in shared environments where shell history/process inspection could expose them.

### 9.6. `WWW-Authenticate` Casing or Formatting Differences

HTTP header names are case-insensitive per protocol; header values may include additional parameters depending on server and configuration. In the demo we use `BasicAuthenticationEntryPoint` with a static realm for exact testing. In other environments, prioritize checking protocol semantics and configured parameters rather than relying on the exact ordering of all headers.

### 9.7. 404 Masked by 401

With `anyRequest().authenticated()`, `GET /api/does-not-exist` without Basic credentials can receive 401 **before MVC checks whether a controller exists**. Try valid credentials before concluding a route exists. A nonexistent URL will not necessarily return 404 immediately if a Security filter blocks it first.

## 10. Securing HTTP Basic in Real Systems

1. **Always use HTTPS/TLS:** Base64 does not hide passwords; every intermediary seeing request headers after TLS termination must be properly secured.
2. **Never hardcode passwords:** in-memory users/roles and `demo-pass` are for practice only. Use proper identity stores, secrets management, password encoders, and MFA if your threat model demands it.
3. **Never log Authorization:** watch out for reverse proxies, observability/tracing, error reports, and `curl -v`. Never paste captures containing credentials into public tickets.
4. **Never confuse realm with permissions:** Authorization belongs in `authorizeHttpRequests` and/or method security. A realm does not control roles, accounts, JWTs, or tenants.
5. **Do not assume Basic guarantees statelessness:** Basic commonly sends credentials per request, but session persistence depends on security/session configuration. For stateless APIs, configure and test the session policy explicitly.
6. **Add rate limiting and brute-force protection:** a public-facing Basic endpoint on the Internet can face continuous password guessing. Implement monitoring, throttling, controlled lockout policies, and account enumeration protection.
7. **Evaluate CSRF per client model:** browsers may automatically attach Basic credentials in certain contexts; assess CSRF for state-changing operations. Do not auto-disable `csrf` simply because HTTP Basic is used.
8. **Consider client UX:** Basic fits some scripts, diagnostics, or internal APIs over TLS, but is not ideal for browser apps needing login/logout UX and MFA. For modern apps, consider secure session form login, OIDC, or OAuth2 resource servers depending on architecture.
9. **Distinguish `Authorization` from `WWW-Authenticate`:** the first carries client credentials; the second carries the server challenge. Never echo credentials into responses.
10. **Rotate/revoke passwords:** when Basic credentials leak, change passwords or lock accounts and manage parallel sessions/tokens if multiple auth methods exist; changing the realm does not revoke leaked secrets.

## 11. Self-Verification Exercises

**Exercise 1.** Change the realm from `TrainingAPI` to `InternalAPI`. Keep users/roles unchanged. Compare HTTP status, `WWW-Authenticate`, and `/api/admin` access results.  
**Result:** the challenge header changes realm; permissions still follow `hasRole("ADMIN")`.

**Exercise 2.** Call `/api/private` three times: no credentials, wrong password, right password. For each call, record status, presence of `WWW-Authenticate`, and response body.  
**Result:** 401 + challenge; 401 + challenge; 200 + `PRIVATE_OK: learner`.

**Exercise 3.** Call `/api/public` without a header and with a wrong Basic password. Why can you get two different statuses?  
**Result:** `permitAll()` does not bypass `BasicAuthenticationFilter`; an invalid header can still trigger authentication failure.

**Exercise 4.** Access `/api/admin` as `learner` then `admin`.  
**Result:** 403 and 200; realm is not an authorization mechanism.

**Exercise 5.** Remove `exceptionHandling(ex -> ex.authenticationEntryPoint(...))` and retry with both browser clients and `curl`. Observe which challenge gets picked in your Spring Security version, then restore the explicit configuration.  
**Goal:** understand that entry point selection can be influenced by multiple authentication mechanisms and request matchers.

**Exercise 6.** Add `GET /api/unknown` without a controller. Call it without credentials and with valid credentials.  
**Goal:** distinguish 401 from the security filter vs 404 from Spring MVC, avoiding misdiagnosing routes.

## 12. Key Takeaways

- Enable **HTTP Basic** in Spring Security 6 Servlet via `http.httpBasic(...)`.
- **`BasicAuthenticationEntryPoint`** configures the `realm` and sends **401 + `WWW-Authenticate: Basic realm="..."`** when clients need authentication.
- **`Authorization: Basic ...`** is sent by the client; Base64 does not secure passwords. **Use HTTPS.**
- **401**: missing or invalid credentials, typically needing a Basic challenge. **403**: authenticated but insufficient permission; typically no new Basic challenge needed.
- **`permitAll()`** does not remove Security filters; an invalid Basic header can still make a public endpoint return 401.
- Realm **does not replace** `authorizeHttpRequests`, roles, password encoders, or session security.
- Good tests check **HTTP status, `WWW-Authenticate`, controller body**, and role-based behavior; not just a single 200 status.

**Final principle:** `httpBasic` enables the protocol, `BasicAuthenticationEntryPoint` describes the challenge via realm, `AuthenticationManager` verifies identity, and authorization rules decide which resources can be accessed. These responsibilities are separate yet cooperate on the same HTTP request.