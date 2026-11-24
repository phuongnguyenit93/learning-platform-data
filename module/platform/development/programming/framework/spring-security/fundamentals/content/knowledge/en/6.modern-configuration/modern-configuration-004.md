# Distinguishing Authentication, Authorization, and Protection Configuration in Spring Security

In a Spring Security application, many settings live inside the same `SecurityFilterChain` method, making it easy for beginners to assume they are all "checking login." In reality, you are declaring at least **three independent yet collaborating groups of responsibilities**:

1. **Authentication:** verifies *who is making the request* based on what evidence; produces a trusted `Authentication` identity.
2. **Authorization:** decides *what that identity is allowed to do* with a specific URL, method, or resource.
3. **Protection mechanisms (exploit protections / security hardening):** reduces the chance that requests, responses, sessions, or browsers are abused, such as CSRF, security headers, session management, and related hardening settings.

All three groups serve security, yet they answer three different questions. **A valid login does not automatically grant admin privileges; having admin privileges also does not make a POST missing a CSRF token valid.** A request reaches business logic only after the appropriate check layers have accepted it.

This lesson uses **Spring Boot 3, Spring Security 6, Spring MVC/Servlet, Java 17+** to illustrate modern configuration APIs with `SecurityFilterChain` and `HttpSecurity`. Some APIs change across version lines; if you are using Spring Boot 4/Spring Security 7 or Spring WebFlux, you must select documentation matching your version and application model.

## 1. Looking at a Configuration to Spot the Three Responsibility Groups

The snippet below is an *illustrative sketch* inside a Spring `@Configuration` class:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        // Authorization: who may access which path?
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        // Authentication: handle Basic credentials.
        .httpBasic(Customizer.withDefaults())
        // Exploit protection: verify CSRF when applicable.
        .csrf(Customizer.withDefaults())
        .build();
}
```

Here:

- `.httpBasic(...)` enables reading username/password from HTTP Basic and passing them to authentication components.
- `.authorizeHttpRequests(...)` sets the **must be permitted to access** conditions for URLs; `authenticated()`, `hasRole(...)`, `permitAll()` are *authorization rules*.
- `.csrf(...)` enables/retains CSRF policy for state-changing requests. Servlet Spring Security normally enables CSRF by default; writing it explicitly helps learners observe it.
- `.build()` builds a `SecurityFilterChain` containing the corresponding security filters.
- These settings do not by themselves define who is USER/ADMIN, whose password is correct, who owns a record, or where CSRF tokens come from. They must collaborate with other beans and business classes.

**Do not infer filter order directly from the order of DSL calls in code.** Spring Security assembles filters according to its own architecture; a request can be blocked by CSRF before controllers or application permission checks are called. Read actual results, rules, and the built filter chain rather than treating the three DSL calls as three sequentially executed statements.

### 1.1. Quick Comparison Table

| Purpose | Question | Common components | Outcome when unmet |
| --- | --- | --- | --- |
| **Authentication** | "Who is the caller? Are credentials valid?" | `httpBasic`, `formLogin`, `UserDetailsService`, `PasswordEncoder`, `AuthenticationManager`, `AuthenticationProvider`, `oauth2ResourceServer` | Fails to establish a trusted identity; HTTP APIs usually return 401 or web redirects to login |
| **Authorization** | "Is this identity allowed to access/run this action?" | `authorizeHttpRequests`, `requestMatchers`, `hasRole`, `hasAuthority`, `@EnableMethodSecurity`, `@PreAuthorize`, `AuthorizationManager` | Usually 403 if authenticated but lacking permission |
| **Exploit protection** | "Do the request/response/session pass safety checks?" | `csrf`, `headers`, `cors`, `sessionManagement`, and suitable cookie/TLS settings | For instance, POST missing CSRF token is usually 403; header/cookie policies may not map to a single status code |

**Note on CORS and sessions:** CORS is a browser mechanism controlling cross-origin access, not authentication/authorization. Session management governs the lifecycle and storage of authentication; it sits at the boundary of several groups, yet does not decide permissions on a specific record. Holistic system security also requires input validation, parameterized queries, output encoding, rate limiting, secret management, and business controls.

## 2. Understanding Security Decisions on a Request

Suppose Alice has logged in, holds authorities `ROLE_USER` and `note:write`, but does not have `ROLE_ADMIN`. A request can encounter the following checks:

```text
HTTP request
     |
     v
FilterChainProxy -> select matching SecurityFilterChain
     |
     +-- Applicable request protection checks (e.g., CSRF on POST)
     |
     +-- Authentication: check Basic/form/token/session if needed
     |       |
     |       +-- success -> SecurityContext holds Authentication
     |       +-- failure -> handle login challenge/401/redirect
     |
     +-- Request authorization: allowed to access this URL?
     |       |
     |       +-- missing permission -> 403/appropriate handler
     |
     v
Controller -> Service
                 |
                 +-- Method/domain authorization:
                 |     valid operation? owner? tenant? state?
                 |
                 v
           Execute business logic and return response
     |
     +-- Appropriate response headers and browser protection layers
```

The diagram describes **responsibilities**, without promising an exact filter order. Components such as `CsrfFilter`, `BasicAuthenticationFilter`, `AuthorizationFilter`, and `ExceptionTranslationFilter` operate as Spring Security assembles the chain. Not every request traverses every step: a public GET may need no authentication, while a request with invalid CSRF can be stopped very early.

### 2.1. Real Request Matrix

| Request | Authentication | Authorization | Protection | Sample outcome |
| --- | --- | --- | --- | --- |
| Anonymous GET `/api/public` | Not required | `permitAll()` | Appropriate filters/headers still run | 200 |
| Anonymous GET `/api/me` | No credentials | Endpoint requires login | CSRF not required since GET is safe | 401 with HTTP Basic |
| Alice GET `/api/me` | Valid Basic | `authenticated()` passes | Appropriate protections apply | 200 |
| Alice GET `/api/admin` | Valid Basic | Missing `ROLE_ADMIN` | CSRF is not the cause | 403 |
| Admin GET `/api/admin` | Valid Basic | Has `ROLE_ADMIN` | Appropriate protections | 200 |
| Alice POST `/api/notes` without CSRF | Valid Basic | May have permission to create notes | CSRF rejects | 403 |
| Alice POST `/api/notes` with CSRF | Valid Basic | URL rule and method policy pass | Valid CSRF | 200 in demo |
| Viewer POST `/api/notes` with CSRF | Valid Basic | Method policy lacks `note:write` | CSRF passes | 403 |

Notably, **two responses with the same 403 status can originate from different layers**: missing authority, missing object permission, or an invalid CSRF token. Seeing 403 alone is not enough to conclude which rule needs fixing.

## 3. Authentication Configuration: Establishing a Trusted Identity

### 3.1. Configuring Credential Reception Mechanisms

An application can accept credentials through different mechanisms:

| Mechanism | Common configuration | What the client sends | Outcome/characteristics |
| --- | --- | --- | --- |
| HTTP Basic | `http.httpBasic(Customizer.withDefaults())` | Header `Authorization: Basic ...` | Provider checks username/password; unauthenticated API usually gets 401 + Basic challenge |
| Form login | `http.formLogin(Customizer.withDefaults())` | Username/password via `POST /login` form | Unauthenticated web usually redirects to `/login`; session can retain context |
| OAuth2 Resource Server JWT | `http.oauth2ResourceServer(oauth -> oauth.jwt(...))` | `Authorization: Bearer ...` | Must verify token, signature, issuer/audience, expiry, and appropriate scope mapping |
| OAuth2/OIDC login | `http.oauth2Login(Customizer.withDefaults())` | Redirect flow to identity provider | App creates/restores identity from the login flow |
| Custom provider | `AuthenticationProvider` or equivalent mechanism | Custom credentials | Must validate trusted sources and evidence |

The entries above are **authentication options**, not a list to enable all at once. Enabling multiple mechanisms on the same chain can require explicitly designing `AuthenticationEntryPoint`, session policy, request matchers, and client boundaries.

### 3.2. What Do UserDetailsService and PasswordEncoder Do?

`UserDetailsService` looks up user information by username for mechanisms that use it. It can return `UserDetails` with username, password hash, account status flags, and authorities. `PasswordEncoder` is responsible for checking a raw password against a stored hash, such as BCrypt.

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("demo-alice-pass"))
        .authorities("ROLE_USER", "note:write")
        .build();
    return new InMemoryUserDetailsManager(alice);
}
```

This is a Spring Boot configuration snippet requiring imports for `User`, `UserDetails`, `UserDetailsService`, `PasswordEncoder`, `BCryptPasswordEncoder`, and `InMemoryUserDetailsManager`. Passwords are hashed for storage; the provider compares using `matches`. Never store plaintext passwords or hardcode real passwords in production. Demo passwords are for localhost learning only.

**Do not confuse:**

- `UserDetailsService` retrieves user records; by itself it does not define which URLs may be accessed.
- `PasswordEncoder` handles passwords; it does not decide permission to read orders.
- `AuthenticationManager` / `AuthenticationProvider` performs verification; the resulting `Authentication` holds the identity and trusted `GrantedAuthority` values upon successful authentication.
- `SecurityContextHolder` provides access to the current `Authentication` according to the appropriate model. Never construct an `Authentication` with `authenticated=true` from a client-sent JSON body.

### 3.3. AuthenticationEntryPoint Handles Unauthenticated Callers

When the client needs to be prompted to authenticate, Spring Security can use an `AuthenticationEntryPoint`:

- HTTP Basic: typically returns **401 Unauthorized** with a `WWW-Authenticate` header.
- Form login: typically returns **302 Redirect** to the `/login` page.
- Bearer token: typically returns 401 with the corresponding Bearer challenge when the token is missing/invalid.

HTTP example:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
```

May receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The realm name and other headers depend on configuration. Do not hardcode the realm string across every test. **Basic only Base64-encodes username/password**, so HTTPS is required in real deployments; Base64 is not encryption.

### 3.4. Authentication Configuration Does Not Create Access Policies

If a user logs in successfully via Basic, what is proven is that the credentials were accepted by the provider. That user does **not by default** gain permission to call `/api/admin` or view another user's report. The authorization step must rely on authorities/roles and specific resources where needed.

## 4. Authorization Configuration: Defining What Is Permitted

### 4.1. Rules by HTTP Request

`authorizeHttpRequests` defines access conditions based on request matchers:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
    .requestMatchers(HttpMethod.POST, "/api/notes").authenticated()
    .anyRequest().denyAll()
)
```

Analysis:

- `permitAll()` makes an endpoint public with respect to **access permission**; it does not remove the request from the entire security filter chain.
- `authenticated()` requires the user to be authenticated in Spring Security's sense, without requiring a specific role.
- `hasRole("ADMIN")` by default checks for authority **`ROLE_ADMIN`**. `hasAuthority("ROLE_ADMIN")` checks that exact string, while `hasAuthority("ADMIN")` checks the string `ADMIN`.
- `anyRequest().denyAll()` denies requests without a matching rule; suitable when exposed endpoints should be explicitly allowlisted.
- Rules are evaluated in **declaration order**. Specific matchers must come before broad matchers.
- Matchers can be scoped by HTTP method; GET is normally used for reads, POST for side effects. Do not assume GET is always safe if a controller violates semantics and mutates data.

**`securityMatcher` differs from `requestMatchers`:** when multiple `SecurityFilterChain`s exist, `securityMatcher` decides **which whole chain** handles a request; `requestMatchers` inside `authorizeHttpRequests` decides **rules** for requests inside that chain. If no chain matches, the request can bypass Spring Security. Always provide an appropriate fallback chain.

### 4.2. Method Security and Business Policies

Not every business invocation arrives through a single controller. A service may be called from an API, a message consumer, or a background job. Therefore, Spring Security supports method security:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
    // Other bean configuration if needed
}

@Service
class NoteService {
    @PreAuthorize("hasAuthority('note:write')")
    public String create(Authentication authentication) {
        return "created by " + authentication.getName();
    }
}
```

These are two **fragments**, requiring imports, beans, and service calls through a Spring proxy. `@EnableMethodSecurity` activates processing for the relevant annotations; if a method is called internally via **self-invocation** within the same object, the Spring AOP proxy may not apply the annotation as expected. Test services across realistic boundaries.

`@PreAuthorize` places **authorization** on the method, unlike `httpBasic` which handles **authentication** at the HTTP boundary. When method security denies a call, an authenticated request can receive 403 via the appropriate exception handling mechanism.

### 4.3. Permissions on a Specific Object

Suppose Alice and Bob both have `ROLE_USER` and `order:read`. Both can enter the read-order endpoint, yet that does not guarantee both may access **the same order ID**. The backend must also verify:

```text
authenticatedPrincipal
AND hasAuthority("order:read")
AND sameTenant(principal, order)
AND (isOwner(principal, order) OR hasAuthority("order:read:any"))
AND businessStateAllowsOperation(order)
```

Hiding a UI button, checking only `hasRole("USER")`, or using random IDs does not replace object-level authorization. Domain policies must obtain owner/tenant from the server and the verified principal. This is also how IDOR/Broken Object Level Authorization bugs are prevented.

### 4.4. Denying Missing Permissions vs. Unable to Determine Permissions

- Valid authentication evidence, policy concludes insufficient role/permission -> **DENY**, typically 403.
- External authorization service times out or a required policy is missing -> **UNAVAILABLE**; never silently turn into ALLOW.
- Missing rule for a sensitive endpoint -> default deny or fail fast on misconfiguration, never fall back to `permitAll()`.
- Owner/tenant query returns no reliable result -> do not grant access to the protected resource.

**Fail closed** means blocking an action from proceeding when no trustworthy ALLOW decision exists; it does not mean every error must return 403 literally. Dependency failures may need 503 depending on the API contract.

## 5. Protection Mechanisms: Reducing Request, Response, and Session Abuse

### 5.1. CSRF: Verifying Request Intent in the Right Context

**Cross-Site Request Forgery** happens when another site exploits the browser's automatic attachment of credentials (such as session cookies) to trick a victim into sending a state-changing request. Logging in validly and having write permission are not enough to guarantee a POST was genuinely intended by the user.

In Servlet Spring Security, **CSRF protection is enabled by default** for unsafe HTTP methods such as POST, PUT, PATCH, and DELETE. It can be written explicitly:

```java
.csrf(Customizer.withDefaults())
```

A POST request missing or having an invalid CSRF token for the active mechanism is usually blocked with **403**, even when valid credentials are sent. Tests should use `with(csrf())` to supply a valid token when intending to test downstream layers.

**Points to remember:**

- `permitAll()` is only an authorization decision; a public POST can still be rejected by CSRF.
- `hasRole("ADMIN")` does not disable CSRF for admins.
- `SessionCreationPolicy.STATELESS` does not by itself prove CSRF is unnecessary. Risk depends on whether clients attach credentials automatically.
- For APIs that strictly accept bearer tokens explicitly added to headers by the client—using neither cookies/sessions nor auto-attached Basic credentials—you can evaluate omitting CSRF within that exact scope. The decision must come from the threat model and actual authentication mechanism.
- CORS **does not replace** CSRF. Certain requests can still be dispatched from external sites even if JavaScript cannot read the response.
- CSRF does not cure XSS. If malicious script runs inside the trusted origin itself, it can perform arbitrary actions with the user's permissions.

Do not disable CSRF application-wide just to "fix" a POST returning 403. Check the request method, token issuance mechanism, how tokens are sent, and client type before changing policy.

### 5.2. Security Headers: Browser-Side Protections

Spring Security includes mechanisms that write several HTTP response headers by default, such as:

| Header / policy | Purpose | Limitation |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Reduces dangerous MIME type sniffing | Does not fix XSS or broken authorization |
| `X-Frame-Options: DENY` in common default configurations | Mitigates clickjacking via frames | Must review the application's embedding/iframe needs |
| `Strict-Transport-Security` (HSTS) on HTTPS | Encourages browsers to use HTTPS only for the origin per policy | Does not protect initial HTTP before HSTS/preload, does not check permissions |
| Cache-control headers | Restricts caching of sensitive responses by default | Applications may override caching policies |
| `Content-Security-Policy` (CSP) when **configured by the app** | Reduces certain script/content injection risks | Not enabled with a tailored policy for every app automatically; does not replace output encoding |

Example CSP configuration for an application managing its own frontend assets (illustrative only; allowed scripts/styles must be evaluated yourself):

```java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; object-src 'none'")
    )
)
```

Do not copy an arbitrary CSP into production and assume the UI will work; test report-only/violations, your application's actual assets, and browser impact. Spring Security does not automatically fix SQL injection, output escaping, owner/tenant bugs, or vulnerable dependencies.

### 5.3. CORS: Cross-Origin Browser Policy, Not User Permissions

`cors(...)` configures CORS integration with Spring Security when a browser client runs on another origin. CORS governs, under browser rules, how an origin may send/read cross-origin requests and preflights; it neither verifies user identity nor grants data permissions.

Illustrative points:

- If origin `https://app.example` is allowed to call the API, **user Alice must still log in** if the API is private.
- If Alice has a valid token but lacks permission to view `order/123`, **authorization must still deny access**.
- A command-line client is not constrained by browser CORS; the backend still needs authentication/authorization.
- CORS allowing credentials applies only when the policy specifies explicit origins and compatible settings, never arbitrarily using a wildcard with cookies.

Putting `cors(Customizer.withDefaults())` alone does not replace a `CorsConfigurationSource` or valid CORS setup tailored to your application. You must define allowed origins, methods, headers, and credential policies. OPTIONS preflight requests usually need handling before security steps demanding credentials, because preflight does not carry login credentials the same way actual requests do.

### 5.4. SessionManagement, Cookies, and State

`sessionManagement(...)` governs session policies such as creating, restricting, or avoiding HTTP sessions for the security context. With form login, a session can persist login across requests. With a resource server API, authentication usually comes from a bearer token on each request.

These choices concern **how identity is stored/restored**, not `hasRole` or owner/tenant rules. Session cookies for browser applications should set `Secure` over HTTPS, `HttpOnly`, and `SameSite` according to the threat model, with proper lifecycle/logout handling. Never use the mere presence of a cookie as proof of successful login.

### 5.5. HTTPS, Password Hashing, and Controls Outside the Framework

Even a complete SecurityFilterChain does not by itself guarantee:

- Data transmitted over HTTPS/TLS in transit and connections to trusted dependencies;
- Input validation (e.g. `@Valid`) and parameterized queries preventing SQL injection;
- Context-aware output encoding / template escaping preventing XSS;
- Rate limiting, quotas, request size limits, and abuse protection;
- Object-level authorization, tenant isolation, and business-state checks;
- Useful logging/auditing that does not leak passwords, tokens, or session IDs;
- Consistent transactions, idempotency for side-effecting operations, and permission revocation workflows.

**Authentication, authorization, and exploit protection do not compete; they defend different assets and boundaries.**

## 6. Complete Spring Boot 3 Application Example

This example demonstrates all three groups in a single **Servlet/Spring MVC** application. It uses three accounts:

- `writer` has `ROLE_USER` and `note:write`;
- `viewer` has only `ROLE_USER`;
- `admin` has `ROLE_ADMIN`.

Policy:

| Endpoint | Request rule | Method rule | CSRF |
| --- | --- | --- | --- |
| `GET /api/public` | Public | None | GET needs no token |
| `GET /api/me` | Authenticated | None | GET needs no token |
| `GET /api/admin` | `ROLE_ADMIN` | None | GET needs no token |
| `POST /api/notes` | Authenticated | `note:write` at service | POST requires valid token in demo |

### 6.1. Dependencies

Create a **Spring Boot 3 + Java 17+** project using Spring Web and Spring Security. In `build.gradle` (Groovy DSL) with the Spring Boot plugin already configured, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the `dependencies` section, not a full Gradle build script. For Maven, use `spring-boot-starter-parent` or the matching BOM and the same dependencies in test scope. Do not declare an independent Spring Security version when Boot dependency management manages it.

### 6.2. Main Application

Create `src/main/java/example/securitylayers/SecurityLayersApplication.java`:

```java
package example.securitylayers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLayersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLayersApplication.class, args);
    }
}
```

### 6.3. SecurityConfig: Authentication + Authorization + Protection

Create `src/main/java/example/securitylayers/SecurityConfig.java`:

```java
package example.securitylayers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails writer = User.withUsername("writer")
            .password(encoder.encode("demo-writer-pass"))
            .authorities("ROLE_USER", "note:write")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("demo-viewer-pass"))
            .authorities("ROLE_USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .authorities("ROLE_ADMIN")
            .build();

        return new InMemoryUserDetailsManager(writer, viewer, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Three easily confused parts to highlight:

1. **Authentication**: `userDetailsService(...)` defines the sample users and stored authorities; `passwordEncoder(...)` creates BCrypt; `httpBasic(...)` enables reading Basic headers for Spring Security to authenticate. These users are learning examples; never use hardcoded passwords in production.
2. **Request authorization**: `authorizeHttpRequests(...)` requires `ROLE_ADMIN` on GET admin; GET me and POST notes require a logged-in user; undeclared methods/endpoints are denied.
3. **Method authorization**: `@EnableMethodSecurity` enables `@PreAuthorize` on services; specifically POST notes additionally checks `note:write`.
4. **Exploit protection**: `csrf(Customizer.withDefaults())` preserves CSRF protection for POST; appropriate default security headers are still written by Spring Security if not overridden.
5. **Never infer authz from client-supplied fields**: a username in the request body, an `X-Role` header, or an `isAdmin` field must never become a verified authority.

Note: `hasRole("ADMIN")` searches for `ROLE_ADMIN` by default. `User.withUsername(...).authorities("ROLE_ADMIN")` assigns that exact string. `hasAuthority("ROLE_ADMIN")` also matches, while `hasAuthority("ADMIN")` will not match this admin user.

### 6.4. Controller and Service: Distinguishing URL Rules from Method Rules

Create `src/main/java/example/securitylayers/ApiController.java`:

```java
package example.securitylayers;

import java.util.Map;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class ApiController {

    private final NoteService noteService;

    ApiController(NoteService noteService) {
        this.noteService = noteService;
    }

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin only");
    }

    @PostMapping("/notes")
    Map<String, String> createNote(Authentication authentication) {
        return Map.of(
            "result",
            noteService.create(authentication)
        );
    }
}

@Service
class NoteService {

    @PreAuthorize("hasAuthority('note:write')")
    public String create(Authentication authentication) {
        // Demo only returns a string; real applications write to a DB.
        return "created by " + authentication.getName();
    }
}
```

Here:

- `GET /api/admin` is protected at the HTTP layer: `hasRole("ADMIN")`.
- `POST /api/notes` only requires login at the HTTP layer, yet when the controller invokes the `NoteService` bean, `@PreAuthorize` additionally checks the `note:write` authority.
- CSRF checks still run in the web filter chain; even `writer` with `note:write` is rejected if POST lacks a token.
- `NoteService` is a separate bean invoked by the controller via dependency injection, allowing Spring method security to apply to the method. Do not call a `@PreAuthorize` method via `this.method()` inside the same bean and assume a proxy enforced it.
- The demo logic has no owner/tenant/data persistence yet. In an API with real data, add domain authorization and verify no unauthorized side effects occur.

### 6.5. Running the Application and Observing with curl

From a Spring Boot project with the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

Assume the app runs on `http://localhost:8080`. The passwords below are for local use only:

```bash
# Public GET: 200, body {"message":"public"}
curl -i http://localhost:8080/api/public

# Private GET without credentials: 401, Basic challenge
curl -i http://localhost:8080/api/me

# Authenticated writer: 200, body {"user":"writer"}
curl -i -u writer:demo-writer-pass http://localhost:8080/api/me

# Writer lacking ROLE_ADMIN: 403
curl -i -u writer:demo-writer-pass http://localhost:8080/api/admin

# Admin with right role: 200, body {"message":"admin only"}
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin

# Writer has note:write but POST lacks CSRF token: 403
curl -i -X POST -u writer:demo-writer-pass \
  http://localhost:8080/api/notes
```

The last Bash command uses a `\` line continuation. In PowerShell, put the URL on the same line or use PowerShell's own syntax; do not copy Bash line continuations into PowerShell.

To test a **successful POST with CSRF**, this lesson uses MockMvc `with(csrf())` to avoid manually juggling session/token lifecycles with curl. In a real browser/session app, the client must retrieve the token from the configured repository/handler and send it back in the proper header or form parameter.

Real HTTP Basic must be used over HTTPS; `curl -u` can expose passwords in shell history/process lists, so the hardcoded passwords above are demo values only. Never write real Authorization headers with credentials or session IDs into public documents.

## 7. Thoroughly Testing All Three Groups with Spring Security Test

Add `spring-security-test` in test scope to use `httpBasic()` and `csrf()`. Create `src/test/java/example/securitylayers/SecurityLayersTest.java`:

```java
package example.securitylayers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityLayersTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validCredentialsProduceIdentity() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("writer", "demo-writer-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("writer"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("writer", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void roleDecidesAdminAccess() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("writer", "demo-writer-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void missingCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("writer", "demo-writer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndAuthorityAllowPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("writer", "demo-writer-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result")
                .value("created by writer"));
    }

    @Test
    void validCsrfButMissingMethodAuthorityIsDenied()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("viewer", "demo-viewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test --tests example.securitylayers.SecurityLayersTest
```

In PowerShell:

```powershell
.\gradlew.bat test --tests example.securitylayers.SecurityLayersTest
```

**Expected:** all **8 test methods** pass with the exact code/config/controller shown in the example, given a properly set up Boot 3 environment and test dependencies. This is a **code-based expectation**, not a log from a tool run in this lesson; actual Gradle task counts and output may differ.

The tests verify in order:

| Test | Group tested | What it proves |
| --- | --- | --- |
| Public GET | Request authorization | `permitAll()` still lets anonymous callers in |
| Anonymous private GET | Authentication + entry point | Unauthenticated callers are challenged to authenticate |
| Valid Basic | Authentication | Provider accepts credentials and creates identity |
| Invalid Basic | Authentication | Invalid credentials are rejected |
| Admin role | Request authorization | Logged-in users lacking the role are still denied |
| POST missing CSRF | Exploit protection | Having write permission is insufficient if the request lacks a token |
| POST valid CSRF + writer | Protection + method authorization | Meeting all conditions reaches the service |
| POST valid CSRF + viewer | Method authorization | A valid token does not grant `note:write` |

### 7.1. Why Can Both Missing CSRF and Missing Authority Return 403?

`status().isForbidden()` only confirms the **HTTP result**, without identifying which filter produced it. To isolate the cause in this lesson, we construct two distinct requests:

- Writer has `note:write` but **supplies no CSRF** -> 403 at the request protection layer.
- Viewer **has valid CSRF** but lacks `note:write` -> 403 at method security.

That comparison is far better than always omitting `with(csrf())` and wondering why every authority test returns 403 because CSRF stopped it first.

### 7.2. How @WithMockUser Differs from httpBasic()

`@WithMockUser` or `with(user("..."))` puts a simulated user into the security context to test authorization; it **does not prove real usernames/passwords are verified by the provider**. `httpBasic(...)` adds a Basic header so the request passes through the configured HTTP Basic mechanism, suitable when testing authentication and authorization together.

Never treat a passing `@WithMockUser(roles = "ADMIN")` test as proof that real users can log in or that JWT issuer/scope verification works properly.

### 7.3. Testing That No Unauthorized Side Effects Occur

The example controller returns a string and writes no data. In real production apps, 401/403/CSRF tests must also verify:

- No order or note records are inserted/updated/deleted;
- No events are published to queues or payment providers called;
- No other tenant's data is written;
- Business logic does not execute when policy denies the request;
- No passwords/tokens or sensitive data leak in error responses/logs.

An HTTP 403 is not enough to prove safety if side effects already happened before the exception was returned.

## 8. Standalone Java 17 Example: A Mental Model of the Three Layers

If you do not have a Spring Boot environment handy, the Java program below **does not use real Spring Security** and instead simulates the three check gates. It clarifies the difference between being unauthenticated, denied permission, and failing request protection.

Create **`ThreeLayersModel.java`**:

```java
import java.util.Set;

public class ThreeLayersModel {

    enum Decision {
        ALLOW,
        UNAUTHENTICATED,
        FORBIDDEN,
        CSRF_REJECTED,
        DENY_UNKNOWN
    }

    record Actor(
        String name,
        boolean authenticated,
        Set<String> authorities
    ) {}

    record Request(
        String method,
        String path,
        boolean csrfValid
    ) {}

    static Decision decide(Actor actor, Request request) {
        if (request == null || request.method() == null
                || request.path() == null) {
            return Decision.DENY_UNKNOWN;
        }

        if ("GET".equals(request.method())
                && "/api/public".equals(request.path())) {
            return Decision.ALLOW;
        }

        boolean knownGet = "GET".equals(request.method())
                && ("/api/me".equals(request.path())
                    || "/api/admin".equals(request.path()));
        boolean knownPost = "POST".equals(request.method())
                && "/api/notes".equals(request.path());

        if (!knownGet && !knownPost) {
            return Decision.DENY_UNKNOWN;
        }

        // Simulate part of exploit protection for POST.
        if (knownPost && !request.csrfValid()) {
            return Decision.CSRF_REJECTED;
        }

        // Simulate authentication.
        if (actor == null || !actor.authenticated()) {
            return Decision.UNAUTHENTICATED;
        }

        // Simulate authorization.
        Set<String> rights = actor.authorities();
        if (rights == null) {
            return Decision.FORBIDDEN;
        }

        if ("/api/admin".equals(request.path())
                && !rights.contains("ROLE_ADMIN")) {
            return Decision.FORBIDDEN;
        }

        if (knownPost && !rights.contains("note:write")) {
            return Decision.FORBIDDEN;
        }

        return Decision.ALLOW;
    }

    static void print(String label, Actor actor, Request request) {
        System.out.println(label + ": " + decide(actor, request));
    }

    public static void main(String[] args) {
        Actor writer = new Actor(
            "writer", true, Set.of("ROLE_USER", "note:write")
        );
        Actor viewer = new Actor(
            "viewer", true, Set.of("ROLE_USER")
        );

        print("Public GET", null,
            new Request("GET", "/api/public", false));
        print("Anonymous private GET", null,
            new Request("GET", "/api/me", false));
        print("Writer admin GET", writer,
            new Request("GET", "/api/admin", false));
        print("Writer POST without CSRF", writer,
            new Request("POST", "/api/notes", false));
        print("Viewer POST with CSRF", viewer,
            new Request("POST", "/api/notes", true));
        print("Writer POST with CSRF", writer,
            new Request("POST", "/api/notes", true));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac ThreeLayersModel.java
java ThreeLayersModel
```

**Exact stdout according to program logic:**

```text
Public GET: ALLOW
Anonymous private GET: UNAUTHENTICATED
Writer admin GET: FORBIDDEN
Writer POST without CSRF: CSRF_REJECTED
Viewer POST with CSRF: FORBIDDEN
Writer POST with CSRF: ALLOW
```

The model uses an `Actor` record with code-constructed authenticated/authority flags; it **does not verify passwords, tokens, sessions, or CSRF tokens**. Therefore it is only for learning the decision flow and **must never replace Spring Security in production**. In particular, `csrfValid` is a simulated flag in the program; never trust a client-sent `csrfValid=true` field as proof of valid CSRF.

In a real application, Spring Security receives the request, authenticates credentials, checks CSRF via the token repository/handler, and evaluates authorization; domain services must also enforce object permissions. Actual execution order can differ from the simulation, yet all required conditions must be met.

## 9. Which Configuration Changes Affect Which Group?

### 9.1. Enabling Form Login Instead of HTTP Basic

```java
// Authentication policy for web browsers:
.formLogin(Customizer.withDefaults())
```

Compared to `httpBasic`, unauthenticated behavior changes: with form login, browsers usually redirect to `/login`, whereas Basic usually returns a 401 challenge. **Roles and URL permissions do not change automatically** just from picking another authentication mechanism. Configure the security chain and client type properly; do not assume every browser always gets 302 when multiple entry points exist.

### 9.2. Changing authenticated() to hasRole("ADMIN")

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

This is an **authorization change**: a logged-in user lacking `ROLE_ADMIN` will be denied. It does not change how passwords are checked, enable/disable CSRF, or alter password hashing.

### 9.3. Adding CSRF for POST

```java
.csrf(Customizer.withDefaults())
```

This is a request protection mechanism; validly authenticated users can still be blocked for a missing/invalid token. Only when the threat model clearly explains credential sources, client types, and request scope should you consider custom exceptions or ignore matchers. Never disable globally to dodge test failures.

### 9.4. Configuring Security Headers

```java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; object-src 'none'")
    )
)
```

This is a browser protection setting. It does not create users, grant `ROLE_ADMIN`, change method policies, or guarantee application output is safe from XSS. Test thoroughly against the frontend.

### 9.5. Allowing CORS While Still Requiring Login

An origin allowed by CORS only means the browser may use cross-origin resources under policy. Private APIs still must verify credentials and principal permissions. If a frontend calls an API with cookies from another origin, evaluate `SameSite`, CORS credentials, CSRF, and trust boundaries together.

### 9.6. Configuring a Stateless API

`SessionCreationPolicy.STATELESS` directs Spring Security not to create/use an HTTP session to store/restore the SecurityContext for requests in that chain. Yet if a frontend/browser still carries auto-attached credentials, merely adding the word "stateless" does not eliminate all CSRF risks. Nor does stateless automatically restrict roles, scopes, or tenants.

## 10. Analyzing Common Configuration Mistakes

| Mistake | Confused groups | Consequence | Fix |
| --- | --- | --- | --- |
| Treating `httpBasic()` as allowing all users | Authentication vs authorization | Valid users access sensitive endpoints unintentionally | Add `authorizeHttpRequests` and clear object policies |
| Treating `hasRole("ADMIN")` as verifying admin password | Authorization vs authentication | Confusing rule role with provider | Configure provider/user store/token verifier separately |
| Calling `hasRole("ROLE_ADMIN")` with default prefix | Authorization | Prefix gets doubled or rule fails to match | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Setting `anyRequest().permitAll()` too broadly | Authorization | Unintended endpoints become public | Specific rules and `anyRequest().denyAll()` when appropriate |
| Disabling CSRF because POST tests return 403 | Exploit protection | Forged requests can succeed in cookie-based apps | Use `with(csrf())`, issue tokens properly, evaluate threat model |
| Treating CORS as a permission system | Browser protection vs authorization | Non-browser clients or same-origin requests bypass broken policy | Always verify identity/permissions on the server |
| Trusting `X-User-Id`, `roles`, or `isAdmin` from client | Authentication/authorization | Identity spoofing, privilege escalation | Use verified principal and trusted authority sources |
| Using `web.ignoring` unnecessarily for public routes | Chain protection | Skips security headers/filters on those routes | Prefer `permitAll()` for public resources |
| Protecting only URLs, forgetting service/object checks | Authorization | IDOR/BOLA, reading wrong tenant | Method/domain authorization and scoped queries |
| Assuming CSP enables itself / stops all XSS | Exploit protection | False sense of security | Choose an appropriate CSP and context-aware output escaping |
| Assuming every 403 means a missing role | Diagnostic error | Fixing the wrong layer, possibly disabling needed protection | Analyze request, filter chain, CSRF, permissions, and logs |
| Falling back to `permitAll()` when policy is missing | Authorization/config | Privilege bypass when configuration breaks | Fail fast or deny by policy |
| Two chains with wrong matchers/`@Order` | Chain selection | Requests hit the wrong mechanism or go unprotected | Test chain matching and add an appropriate fallback |
| Copying old `WebSecurityConfigurerAdapter` config | API version | Fails to compile on Boot 3/Security 6 | Use `SecurityFilterChain` bean and matching version docs |

### 10.1. Why Is permitAll() Not the Same as Bypassing Spring Security?

`permitAll()` is an **authorization decision** for a request passing through `SecurityFilterChain`. Appropriate filters and header writers can still participate. Meanwhile, configuring Spring Security to ignore a request completely can cause it to skip the chain's security protections. For public endpoints or static resources, prefer `permitAll()` unless there is a clear technical reason and the impact is understood.

### 10.2. Why Can You Not Check Roles Only in Controllers?

An admin operation might be invoked via REST, a scheduled job, or an asynchronous flow. If policy lives only in the controller, other call paths can bypass it. Depending on architecture, use HTTP authorization, method security, and domain policies where business logic executes for complete coverage.

### 10.3. Why Can a CSRF Error Hide a Permission Error?

Suppose `viewer` lacks `note:write` and sends a POST without a CSRF token. The request can be blocked by `CsrfFilter` before `@PreAuthorize` runs, so the test only sees 403 without **proving** method security rejected the missing authority. To test authorization specifically, supply a valid CSRF token in the test while keeping `viewer` lacking the authority.

### 10.4. Why Does Spring Security Not Complete the Threat Model by Itself?

The framework supplies security building blocks, yet it does not know all of your assets and business rules. A valid Spring Security config can still contain logic bugs—for example, account A reading B's order because a repository queries only by ID. Identify subject, action, resource, owner, tenant, state policy, and business conditions, then test those exact denial cases.

## 11. How to Read an Unfamiliar SecurityConfig

When opening a project's configuration class, follow this order:

1. **Identify Servlet vs. reactive:** `HttpSecurity` belongs to Servlet, whereas WebFlux uses `ServerHttpSecurity` and `SecurityWebFilterChain`.
2. **Count the chains:** how many `SecurityFilterChain` beans exist? How do `securityMatcher` and `@Order` partition URLs? Is there a fallback?
3. **Locate authentication mechanisms:** `httpBasic`, `formLogin`, `oauth2ResourceServer`, `oauth2Login`, or custom filters/providers. Where do identities/credentials come from?
4. **Locate user store/token verifier:** `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, `JwtDecoder`, issuer/audience, and authority mapping.
5. **Locate request authorization:** `authorizeHttpRequests`, matchers, rule order, `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, and fallback.
6. **Locate method/domain authorization:** `@EnableMethodSecurity`, `@PreAuthorize`, service policies, and owner/tenant checks.
7. **Locate exploit protections:** `csrf`, `headers`, `cors`, `sessionManagement`, cookie policies, HTTPS, and browser settings.
8. **Locate exception handling:** `AuthenticationEntryPoint` for unauthenticated callers; `AccessDeniedHandler` for denied callers; form redirects vs. JSON APIs.
9. **Verify with tests:** anonymous, wrong credentials, user lacking authority, POST lacking CSRF, different owner/tenant, blocked side effects.
10. **Inspect runtime evidence:** actual chain selected, actual headers/status, sanitized logs; never infer from a single annotation or status code.

### 11.1. Pre-Release Configuration Checklist

- Are the authentication provider/identity source, credential policy, and secret storage clearly defined?
- Are all important endpoints and methods authorized, with an appropriate default deny?
- Are login privileges separated from business-operation permissions, avoiding overly broad roles?
- Do state-changing requests have CSRF protection matching the cookie/credential mechanism?
- Does CORS allow only required origins and avoid being mistaken for authorization?
- Have security headers been verified on real responses, with a tailored CSP if needed?
- Do cookies/sessions/tokens have proper lifetimes, timeouts, revocation, and secure flags?
- Are owner, tenant, object state, and scoped data checks enforced in services/repositories?
- Do regression tests cover 401/403, form login if used, valid/invalid CSRF, object permissions, and side effects?
- When configuration or an authorization service fails, are sensitive actions blocked rather than allowed through?
- Do tests use the right versions, dependencies, and an appropriate integration environment?
- Is there a monitoring plan that avoids logging raw credentials, tokens, or session IDs?

## 12. Self-Check

**Question 1.** A `GET /api/admin` request sends valid Basic username/password, but the user only has `ROLE_USER`. Which group fails? Expected HTTP status?

**Question 2.** Why does replacing `httpBasic` with `formLogin` usually change unauthenticated browser responses from a Basic challenge to a redirect without changing any `hasRole` rules?

**Question 3.** Why can a POST from `writer`, even when authenticated and holding `note:write`, still be rejected without a CSRF token?

**Question 4.** Why does an origin allowed by CORS not mean users from that origin can view every record?

**Question 5.** What is the difference between `securityMatcher` and `requestMatchers` when multiple `SecurityFilterChain`s exist?

**Question 6.** What does `@PreAuthorize("hasAuthority('note:write')")` protect? Does it check the user's password?

**Question 7.** If Alice has `order:read`, what stops her from reading Bob's order in the same tenant?

**Question 8.** Why might a POST test without a CSRF token fail to prove that a `@PreAuthorize` rule works?

**Question 9.** Does `permitAll()` turn off all security filters and headers for a request?

**Question 10.** To protect users from XSS/SQL injection, can you just write `authorizeHttpRequests` and `csrf` without validating input/output or parameterizing database queries?

**Suggested answers:**

1. Authentication succeeds, but authorization denies due to missing `ROLE_ADMIN`; usually 403.
2. Because that changes the **authentication entry point mechanism**, not the authorization rules.
3. CSRF protects state-changing requests in the applicable context, independently of valid identity/authorities.
4. CORS is a browser cross-origin policy; the backend must still authenticate, check permissions, and verify object ownership.
5. `securityMatcher` selects the whole chain, while `requestMatchers` sets rules inside the selected chain.
6. It protects a Spring bean method, checking authorities in the current Authentication; it does not verify passwords itself.
7. Domain/object authorization based on owner/tenant and policies in the service/repository.
8. The request may be blocked by CSRF before reaching the method; to test authorization separately, supply a valid CSRF token.
9. No; `permitAll()` is only an allow decision within the chain.
10. No; Spring Security's exploit protections are complementary layers—you still need validation, parameterized queries, output encoding, and domain policies.

### Official References

- [Spring Security – Java Configuration / SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security – Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security – MockMvc Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
