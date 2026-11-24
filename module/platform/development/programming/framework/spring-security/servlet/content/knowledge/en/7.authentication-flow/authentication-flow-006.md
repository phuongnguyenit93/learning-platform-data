# AuthenticationFilter, AuthenticationConverter, and AuthenticationManagerResolver in Spring Security Servlet

In Spring Security Servlet, HTTP authentication is more than "reading username/password and comparing". A system may accept multiple request shapes, multiple proof-of-identity methods, or multiple user realms/tenants that must be verified by different authentication managers. The **`AuthenticationFilter` – `AuthenticationConverter` – `AuthenticationManagerResolver`** trio separates those three decisions into clear responsibilities: **filtering requests that require authentication**, **converting an HTTP request into an unverified `Authentication`**, and **selecting the `AuthenticationManager` to verify that `Authentication`**.

This lesson belongs to the **Authentication Flow** track of **Spring Security – Servlet**, using modern APIs of Spring Security 6.x, Java 17+, and Spring Boot 3.x. The runnable example below uses Spring Boot 3.3.5 and HTTP form parameters to focus on the contract of the three components; it does **not** implement a production login system, user database, or login token/session issuance.

## 1. Objectives and Responsibility Map

After this lesson, you should be able to explain:

1. When `AuthenticationFilter` participates in a request and when it **continues without attempting authentication**.
2. What `AuthenticationConverter.convert(HttpServletRequest)` receives and must return; the meaning of `null`, an unauthenticated token, and `AuthenticationException`.
3. How `AuthenticationManagerResolver<HttpServletRequest>` chooses an `AuthenticationManager` based on **the request's context**, while the manager/provider performs credential verification.
4. How the `Authentication` result is handed to success/failure handling; why a success handler may terminate the HTTP response **without invoking a controller**.
5. How to integrate the filter into `SecurityFilterChain`, choosing the right order, scope, session policy, and CSRF handling.
6. How to test valid credentials, wrong credentials, missing fields, mismatched managers, and requests not requiring authentication.

| Component | Primary Input | Output / Effect | Not Its Responsibility |
| --- | --- | --- | --- |
| `AuthenticationFilter` | Servlet request/response + chain and collaborators | Decides whether to attempt authentication, invokes converter/resolver/manager, handles success/failure | Does not define password verification logic for every application |
| `AuthenticationConverter` | `HttpServletRequest` | An `Authentication` requesting verification, or `null`/appropriate error | Does not verify passwords or grant trusted authorities |
| `AuthenticationManagerResolver<C>` | A context of type `C`; here `HttpServletRequest` | The `AuthenticationManager` to use in that context | Does not itself turn a request into an authenticated user |
| `AuthenticationManager` | `Authentication` created by converter | Authenticated `Authentication` or `AuthenticationException` | Does not select HTTP URLs or parse JSON when given only an `Authentication` |
| `AuthenticationProvider` | `Authentication` type supported by the provider | Verifies according to specific policy | Must not trust roles sent by the client |
| `SecurityFilterChain` | Request matcher + configured security filters | Filter set protecting the request | Not equivalent to an `AuthenticationManager` |

Core point: **converter converts; resolver routes; manager verifies; filter orchestrates**. Within a valid authentication request, all four happen sequentially, yet they should never be collapsed into one snippet that reads form fields and sets `isAuthenticated=true`.

## 2. Position in the Servlet Filter Chain

In a Spring MVC application, Servlet filters run before controllers. Spring Security uses `DelegatingFilterProxy` to bridge to `FilterChainProxy`, which selects the `SecurityFilterChain` matching the request.

~~~text
HTTP request
    |
Servlet container / DelegatingFilterProxy
    |
FilterChainProxy
    |  select SecurityFilterChain by matcher and order
    v
... filters before AuthenticationFilter ...
    |
AuthenticationFilter
    |-- RequestMatcher does not match ----> next filter
    |
    |-- RequestMatcher matches
        |
        v
    AuthenticationConverter.convert(request)
        |-- null -------------------------> next filter
        |-- AuthenticationException ------> failure handler
        |
        v
    Authentication request (usually unauthenticated)
        |
        v
    AuthenticationManagerResolver.resolve(request)
        |
        v
    AuthenticationManager.authenticate(authentication)
        |-- AuthenticationException ------> failure handler
        |
        v
    Verified Authentication result
        |
        v
    SecurityContext / repository per configuration
        |
        v
    AuthenticationSuccessHandler -> response
~~~

This is a **logical diagram**, not a runtime log with a fixed class sequence. Actual filter ordering depends on configurers, version, and registered filters. When a request does not match `RequestMatcher`, neither the converter nor the resolver needs to run. If the converter returns `null`, `AuthenticationFilter` lets the request proceed instead of treating `null` automatically as "wrong password". When a request **is** attempted as authentication with invalid credentials, the manager or converter must report failure per contract.

**Distinguish two phases clearly:**

- **Startup:** create `AuthenticationFilter`, converter, resolver/managers, and success/failure handlers, then build `SecurityFilterChain`.
- **Request time:** the filter receives each request matching its matcher; converter, resolver, and manager are invoked per matching request.

Startup configuration can reuse pre-built managers and providers. Never construct a new BCrypt encoder, database client, or entire `AuthenticationManager` **on every request** just for the resolver to make a routing decision.

## 3. AuthenticationFilter: Orchestrator, Not Password Verifier

`org.springframework.security.web.authentication.AuthenticationFilter` is a filter supporting per-request authentication models. Two common constructors are:

~~~java
// When all matching requests use the same AuthenticationManager:
AuthenticationFilter single = new AuthenticationFilter(manager, converter);

// When choosing a manager per request:
AuthenticationFilter routed = new AuthenticationFilter(resolver, converter);
~~~

Those two lines are **illustrative snippets**: `manager`, `resolver`, and `converter` must be properly defined instances. The resolver's generic type in Servlet examples is `AuthenticationManagerResolver<HttpServletRequest>`.

### 3.1. RequestMatcher Is the First Gate

The filter can accept a `RequestMatcher` to decide which requests should attempt authentication:

~~~java
filter.setRequestMatcher(request ->
    "POST".equals(request.getMethod())
        && "/login".equals(request.getServletPath()));
~~~

This example targets a Servlet application mounted at root with matching servlet paths. When a context path, custom servlet mapping, proxy, or multi-servlet setup exists, use a matcher compatible with actual routing. The runnable example later uses a helper that strips the context path from the URI for transparent testing.

Do not register a custom login filter that tries to read credentials on **every GET/POST**. Specify the HTTP method, path, content type, and conditions belonging to the authentication protocol you actually support.

### 3.2. Success and Failure Branches

When the converter builds an authentication request and the manager authenticates successfully, the filter processes the authentication result and invokes `AuthenticationSuccessHandler`. The handler can:

- Return HTTP 200 with a confirmation body.
- Redirect after form login.
- Perform additional steps required by the designed authentication flow.

Conversely, `AuthenticationFailureHandler` can return 401, handle error messages, or redirect appropriately. There is no guarantee that after the success handler the request **always** continues to an MVC controller. In the example below, the handler **actively writes 200** at the login endpoint; no controller handles that endpoint.

**Be careful with persistence:** a successful `Authentication` in one request does not automatically keep subsequent requests logged in permanently. State persistence depends on session policy, `SecurityContextRepository`, token issuance/transmission mechanisms, or cookies. A stateless flow that merely verifies credentials might issue neither a session nor a token.

## 4. AuthenticationConverter: From HTTP Data to an Authentication Request

`org.springframework.security.web.authentication.AuthenticationConverter` is a functional interface used to create an `Authentication` from an `HttpServletRequest`.

Contract shape:

~~~java
Authentication convert(HttpServletRequest request);
~~~

A good converter answers these questions:

- Where does identity proof reside: form fields, Basic header, bearer token, client certificate, or a dedicated header?
- Does this request carry credentials matching a supported protocol?
- Which fields are required, what are the input bounds, and how are structural errors reported?
- Which `Authentication` type does `AuthenticationManager`/`Provider` expect?
- How do we avoid logging, storing, or exposing raw secrets beyond the necessary lifecycle?

### 4.1. Example Converter for Form Username/Password

~~~java
AuthenticationConverter converter = request -> {
    String username = request.getParameter("username");
    String password = request.getParameter("password");

    if (username == null || username.isBlank()
            || password == null || password.isBlank()) {
        throw new BadCredentialsException("Missing credentials");
    }

    return UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);
};
~~~

The snippet above is a **code fragment** requiring Spring Security and Servlet imports, placed in an appropriate configuration location. It creates a token with `principal=username` and `credentials=password` with `isAuthenticated()==false`. It does **not** verify the password or grant authorities. Calling `unauthenticated(...)` clearly conveys that the token is only a request for verification.

**Important:** never call `UsernamePasswordAuthenticationToken.authenticated(...)` inside a converter to grant roles based on client-sent body/headers. An "authenticated" token must result from the component that actually checks the proof and determines trusted authorities.

### 4.2. When to Return null? When to Throw an Exception?

The two behaviors are not equivalent:

- `return null`: the converter **creates no authentication request**. For `AuthenticationFilter`, this is normally the signal to skip the authentication attempt and let the filter chain continue. Useful for converters inspecting requests that may optionally lack credentials.
- Throwing `AuthenticationException` (e.g., `BadCredentialsException`): this request **is treated as a failed authentication attempt**. The filter can dispatch to the failure handler.
- Returning an unauthenticated `Authentication`: sufficient data exists to ask the manager to verify. True success or failure depends on the manager/provider.

Choose behavior based on the protocol. At a dedicated login endpoint, missing username/password should be treated as a login failure; in this lesson's example, the converter throws `BadCredentialsException` and the failure handler returns 401. In a filter checking an optional token on public endpoints, `null` may be more suitable. Do not conflate the two cases.

### 4.3. A Converter Is Not the Only Input Validator

A converter can check shape and format, but that alone does not secure the system. The manager/provider still must verify passwords, user status, tenant membership, or token signatures. If fields like `role` or `isAdmin` appear in the request, never copy them into trusted authorities.

Form parameters are used here to keep the example concise. When designing JSON login, you need a converter that reads the JSON body cleanly once, enforces content type/encoding and body size limits; avoid writing a filter that consumes the request body and prevents downstream filters/controllers from reading it. For HTTP Basic, standard built-in components already exist; do not hand-roll a Basic converter merely to replace well-maintained framework support.

## 5. AuthenticationManagerResolver: Selecting a Manager per Request

`AuthenticationManagerResolver<C>` answers "given this context, which manager should be used?". In Servlet applications, the context is typically `HttpServletRequest`:

~~~java
AuthenticationManagerResolver<HttpServletRequest> resolver = request -> {
    String path = request.getServletPath();
    if (path.startsWith("/tenant-a/")) {
        return tenantAManager;
    }
    if (path.startsWith("/tenant-b/")) {
        return tenantBManager;
    }
    throw new BadCredentialsException("Unsupported authentication area");
};
~~~

This is an **illustrative snippet** for selecting among pre-built managers; `tenantAManager` and `tenantBManager` must be supplied from trusted configuration. A request without a matching manager must be handled explicitly; never silently fall back to an overly permissive manager.

### 5.1. The Resolver Does Not Authenticate the Request

The resolver only returns the executor. Diagrammatically:

~~~text
request path /login/alpha -> alpha manager
request path /login/beta  -> beta manager

alpha manager + ("alice", valid password) -> authenticated
alpha manager + ("bob", beta's valid password) -> rejected
beta manager  + ("bob", valid password) -> authenticated
~~~

A request selecting `alpha manager` does not prove the caller belongs to alpha. **The caller chose the URL**. `alpha manager`/provider itself must verify credentials and permissions appropriate for tenant alpha. Relying solely on `X-Tenant`, `Host`, or client-supplied values to grant roles is a trust-boundary vulnerability.

### 5.2. When Should You Use a Resolver?

- Two authentication areas use different configurations or user stores.
- Multi-tenant systems need to select credential verification sources or providers for a tenant identified under proper policy.
- APIs handle multiple token types/issuers and must choose a manager from safely verified context.
- An application has per-request authentication requirements while keeping converter/filter composition clear.

**A resolver is unnecessary for simple applications.** If all login requests use a single manager, `AuthenticationFilter(authenticationManager, converter)` is usually clearer.

Some mechanisms already include specialized resolvers/filters, such as resource servers with bearer tokens. Use Spring Security's standard tools when they meet your needs instead of rewriting JWT/issuer/signature verification manually.

### 5.3. Common Resolver Design Mistakes

| Design | Problem |
| --- | --- |
| Creating a new `AuthenticationManager`, hashing passwords, and opening DB clients per request | Wastes resources, inconsistent behavior; the resolver should select pre-configured managers |
| Automatically choosing an "open" manager when tenant is missing | Fail-open: may bypass verification |
| Trusting `X-Tenant: admin` as proof the user is admin | Self-asserted headers are not proof of identity or privilege |
| Using tenant A's manager without binding credentials to tenant A | Risks cross-tenant access |
| Swallowing exceptions and returning successful authentication | Turns errors into authentication bypasses |
| Choosing a manager from a host header set by an untrusted proxy | Vulnerable to host-header / proxy-header spoofing |
| Duplicating authorization logic inside the resolver | Mixes authentication routing with authorization; hard to audit |
| Defining too many managers when one suffices | Increases complexity and configuration drift |

## 6. Comparison with Built-in Mechanisms and the Role of the Filter Chain

Not every Spring Security project needs a custom `AuthenticationFilter`.

| Need | Reasonable Starting Point | Notes |
| --- | --- | --- |
| HTTP Basic username/password | `http.httpBasic(...)` | Uses standard HTTP Basic filter and matching provider |
| Web page form login | `http.formLogin(...)` | Provides form/login flow and standard success/failure/session handling |
| OAuth2 Login | `oauth2Login(...)` | Delegates complex flow to the framework |
| JWT Resource Server | `oauth2ResourceServer(...jwt(...))` | Verifies bearer tokens/issuers with the dedicated stack |
| Specialized login endpoint (form/headers/custom token) | `AuthenticationFilter + AuthenticationConverter` | Full control over protocol adapter and response |
| Per-request manager selection | `AuthenticationManagerResolver<HttpServletRequest>` | Ensure each manager still authenticates independently |
| Different mechanisms and filter sets per URL | Multiple `SecurityFilterChain`s with `securityMatcher` and `@Order` | Do not confuse chain selection with manager selection |

**Two independent selections:**

1. `FilterChainProxy` selects the first **`SecurityFilterChain`** matching the request, via `securityMatcher` and chain order.
2. If that chain contains `AuthenticationFilter` and the request matches the filter's `RequestMatcher`, the resolver selects the **`AuthenticationManager`**.

The resolver does not do the work of `securityMatcher`, and the chain matcher does not verify credentials itself. When debugging multi-chain/multi-tenant systems, inspect both decisions in order.

A filter inserted at a given position in the chain still requires proper authorization rules. Never assume "having an authentication filter means every endpoint is protected". When a request is not handled by the custom filter, other filters and authorization rules still determine the final response.

## 7. Complete Java 17+ Example: Two Tenants, One AuthenticationFilter

This locally runnable example uses one `AuthenticationFilter` for two endpoints:

- `POST /login/alpha`: alpha manager accepts `alice / alpha-pass`.
- `POST /login/beta`: beta manager accepts `bob / beta-pass`.
- `GET /public/ping`: public endpoint needing no converter/resolver.
- Successful login requests return **200** and a short body for observation; failures return **401**.
- The flow is intentionally **stateless, creates no login session, and issues no token**. A successful login call does not mean a subsequent request is automatically logged in.

**Illustrative security scope:** users/passwords are local only, hashed with BCrypt for provider verification; the API has no database, rate limiting, 2FA, or production auditing. In real products, never hardcode passwords or tenant credentials as shown below.

### 7.1. Directory Structure

~~~text
auth-filter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/authfilter/
    │   ├── AuthFilterDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   └── PublicController.java
    └── test/java/demo/authfilter/
        └── AuthenticationFilterTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'auth-filter-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

The security starter brings in compatible core/web/config/crypto modules via Spring Boot dependency management. `spring-security-test` in test scope supports MockMvc integration; do not add it to production runtime.

### 7.2. Application Entry Point

File `src/main/java/demo/authfilter/AuthFilterDemoApplication.java`:

~~~java
package demo.authfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthFilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthFilterDemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration: Converter, Resolver, and Filter

File `src/main/java/demo/authfilter/SecurityConfiguration.java`:

~~~java
package demo.authfilter;

import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationConverter loginConverter() {
        return request -> {
            String username = request.getParameter("username");
            String password = request.getParameter("password");

            if (username == null || username.isBlank()
                    || password == null || password.isBlank()) {
                throw new BadCredentialsException("Missing credentials");
            }

            return UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
        };
    }

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> managerResolver(
            PasswordEncoder encoder) {

        // Hashes are generated once when the bean initializes, not on every request.
        String alphaHash = encoder.encode("alpha-pass");
        String betaHash = encoder.encode("beta-pass");

        AuthenticationManager alphaManager =
            localManager("alice", alphaHash, "TENANT_ALPHA", encoder);

        AuthenticationManager betaManager =
            localManager("bob", betaHash, "TENANT_BETA", encoder);

        return request -> {
            String path = applicationPath(request);

            if ("/login/alpha".equals(path)) {
                return alphaManager;
            }
            if ("/login/beta".equals(path)) {
                return betaManager;
            }

            throw new BadCredentialsException(
                "Unsupported login endpoint");
        };
    }

    private static AuthenticationManager localManager(
            String expectedUser,
            String encodedPassword,
            String authority,
            PasswordEncoder encoder) {

        return candidate -> {
            Object raw = candidate.getCredentials();

            if (!(raw instanceof String suppliedPassword)) {
                throw new BadCredentialsException(
                    "Invalid credentials");
            }

            if (!expectedUser.equals(candidate.getName())
                    || !encoder.matches(
                        suppliedPassword, encodedPassword)) {
                throw new BadCredentialsException(
                    "Invalid credentials");
            }

            // Only the manager that verified credentials constructs the trusted result.
            return UsernamePasswordAuthenticationToken.authenticated(
                expectedUser,
                null,
                List.of(new SimpleGrantedAuthority(authority)));
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationConverter loginConverter,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        AuthenticationFilter loginFilter =
            new AuthenticationFilter(resolver, loginConverter);

        // The filter attempts authentication only on these exact two POST endpoints.
        loginFilter.setRequestMatcher(
            SecurityConfiguration::isLoginRequest);

        loginFilter.setSuccessHandler((request, response, result) -> {
            response.setStatus(200);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write(
                "authenticated:" + result.getName());
        });

        loginFilter.setFailureHandler((request, response, exception) ->
            response.sendError(401, "Invalid credentials"));

        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            // Demo only returns a login result without creating sessions/cookies.
            // Do not copy this CSRF exemption into apps using session login.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                "/login/alpha", "/login/beta"))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/login/alpha", "/login/beta")
                    .permitAll()
                .anyRequest().denyAll())

            .addFilterAt(
                loginFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    private static boolean isLoginRequest(
            HttpServletRequest request) {

        if (!"POST".equals(request.getMethod())) {
            return false;
        }

        String path = applicationPath(request);
        return "/login/alpha".equals(path)
            || "/login/beta".equals(path);
    }

    private static String applicationPath(
            HttpServletRequest request) {

        // getRequestURI includes the context path; strip it to compare URLs.
        String uri = request.getRequestURI();
        String contextPath = request.getContextPath();
        return uri.substring(contextPath.length());
    }
}
~~~

Step-by-step explanation in creation and execution order:

1. Spring Boot creates the `PasswordEncoder` bean (BCrypt).
2. `loginConverter()` defines how to read form fields and build an unauthenticated token.
3. `managerResolver()` creates two configured managers; the resolver **only selects** based on the pre-restricted path.
4. `securityFilterChain(...)` builds an `AuthenticationFilter` with the converter and resolver.
5. The filter matcher selects only `POST /login/alpha` and `POST /login/beta`; public GET endpoints are not intercepted as login attempts.
6. With valid credentials, the manager returns `UsernamePasswordAuthenticationToken.authenticated(...)` with the trusted username principal, null credentials, and a **server-assigned** tenant authority. The converter never assigns authorities itself.
7. The success handler returns 200 and the response body; the failure handler returns 401. The login endpoints have **no** controller mappings.
8. `SessionCreationPolicy.STATELESS` emphasizes that the example does not store login state in an HTTP session. Since no token is issued, the response only proves that single request was authenticated.
9. The CSRF exemption applies strictly to these two demo endpoints and pairs with the design that uses no authentication cookies/sessions. In real browser session logins, evaluate **login CSRF** and typically keep CSRF protection instead of copying this exemption.
10. `addFilterAt(loginFilter, UsernamePasswordAuthenticationFilter.class)` places the custom filter at the framework's known security slot for username/password authentication. This sets **ordering**, not a guarantee that every filter at that position is automatically removed if you also enable form login. Avoid configuring two filters competing for the same endpoint.

In Java 17, `instanceof String suppliedPassword` is pattern matching; it guarantees the encoder is only called when credentials are actually a string. The manager never uses the raw password after checking, and the authenticated token is constructed with `null` credentials. This demo uses lambda managers; real applications should use proper providers/user stores, hashing policies, lockout/rate limiting, auditing, and safe credential handling.

### 7.4. Controller Only for the Public Endpoint

File `src/main/java/demo/authfilter/PublicController.java`:

~~~java
package demo.authfilter;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

There is no controller for `/login/alpha` or `/login/beta`. The filter itself intercepts the login POST and the success/failure handlers build the HTTP response. If the filter is accidentally left out of `SecurityFilterChain`, login URLs will fall through to policy/handler routing differently, and tests will catch it.

## 8. MockMvc: Testing Converter, Manager Selection, and HTTP Outcomes

File `src/test/java/demo/authfilter/AuthenticationFilterTests.java`:

~~~java
package demo.authfilter;

import jakarta.servlet.http.HttpServletRequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFilterTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    AuthenticationConverter loginConverter;

    @Autowired
    AuthenticationManagerResolver<HttpServletRequest> resolver;

    @Test
    void converterOnlyCreatesAnAuthenticationRequest() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/login/alpha");

        request.addParameter("username", "alice");
        request.addParameter("password", "alpha-pass");

        Authentication candidate = loginConverter.convert(request);

        assertFalse(candidate.isAuthenticated());
        assertEquals("alice", candidate.getPrincipal());
        assertEquals("alpha-pass", candidate.getCredentials());
        assertTrue(candidate.getAuthorities().isEmpty());
    }

    @Test
    void resolverSelectsManagerThatVerifiesCredentials() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/login/alpha");

        Authentication candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alpha-pass");

        Authentication verified =
            resolver.resolve(request).authenticate(candidate);

        assertTrue(verified.isAuthenticated());
        assertEquals("alice", verified.getName());
        assertNull(verified.getCredentials());
        assertEquals("TENANT_ALPHA",
            verified.getAuthorities().iterator().next().getAuthority());
    }

    @Test
    void publicRequestIsNotHandledAsLogin() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void alphaAcceptsItsOwnCredentials() throws Exception {
        mockMvc.perform(post("/login/alpha")
                .param("username", "alice")
                .param("password", "alpha-pass"))
            .andExpect(status().isOk())
            .andExpect(content().string("authenticated:alice"));
    }

    @Test
    void betaAcceptsItsOwnCredentials() throws Exception {
        mockMvc.perform(post("/login/beta")
                .param("username", "bob")
                .param("password", "beta-pass"))
            .andExpect(status().isOk())
            .andExpect(content().string("authenticated:bob"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(post("/login/alpha")
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void alphaCredentialsCannotLoginThroughBeta() throws Exception {
        mockMvc.perform(post("/login/beta")
                .param("username", "alice")
                .param("password", "alpha-pass"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingPasswordIsRejectedByConverter() throws Exception {
        mockMvc.perform(post("/login/alpha")
                .param("username", "alice"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

The eight tests provide three levels of evidence:

| Test group | Verified behavior | What must NOT be inferred |
| --- | --- | --- |
| Converter unit | Request with form fields becomes an unauthenticated `Authentication` with empty authorities | Does not prove the password is correct |
| Resolver + manager unit | Alpha manager from request path actually verifies credentials and grants authority | Does not prove filter order or HTTP integration |
| MockMvc public | Public request is not hijacked by the custom filter | Does not mean all endpoints are public |
| MockMvc login success | Filter matcher + converter + resolver + manager + success handler cooperate properly | Does not prove the user has a session/token for future requests |
| MockMvc login failure | Wrong password, wrong manager, or missing field returns 401 | Does not mean all web errors must return 401 |

`@AutoConfigureMockMvc` in this integration test hooks MockMvc into the `ApplicationContext`'s Spring Security filter chain. When building MockMvc manually, verify security filters are applied; otherwise tests may skip authentication filters and diverge from the Servlet runtime.

### 8.1. Running the Application

If a compatible Gradle version is installed and the files above are in place:

~~~bash
gradle test
gradle bootRun
~~~

With the project's Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows, use `gradlew.bat test` and `gradlew.bat bootRun`. Spring classes come from dependencies, so running `javac`/`java` directly without the corresponding classpath will not work. When tests PASS, Gradle normally reports build success; do not fix exact log wording, runtime duration, or line counts because they depend on the environment.

### 8.2. Testing Endpoints with curl

The application runs on `http://localhost:8080` by default in a learning environment if the port has not been changed:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i -X POST http://localhost:8080/login/alpha \
  -d 'username=alice&password=alpha-pass'
curl -i -X POST http://localhost:8080/login/beta \
  -d 'username=bob&password=beta-pass'
curl -i -X POST http://localhost:8080/login/alpha \
  -d 'username=alice&password=wrong'
curl -i -X POST http://localhost:8080/login/beta \
  -d 'username=alice&password=alpha-pass'
curl -i -X POST http://localhost:8080/login/alpha \
  -d 'username=alice'
~~~

This sends **form-urlencoded** bodies via curl's `-d` option; the converter reads them with `request.getParameter(...)`. On Windows PowerShell, if the `curl` alias differs from the curl binary, use `curl.exe`. These password strings are strictly for local demo use; with any real account, use HTTPS and avoid embedding secrets in shell history.

| Request | Expected HTTP status | Success body |
| --- | --- | --- |
| GET `/public/ping` | 200 | `pong` |
| POST `/login/alpha`, alice/alpha-pass | 200 | `authenticated:alice` |
| POST `/login/beta`, bob/beta-pass | 200 | `authenticated:bob` |
| POST `/login/alpha`, alice/wrong | 401 | Do not rely on error body |
| POST `/login/beta`, alice/alpha-pass | 401 | Do not rely on error body |
| POST `/login/alpha`, missing password | 401 | Do not rely on error body |

Do not expect a redirect or session cookie on login success, because the example's handler and session policy do not create them. Endpoints outside this list are protected by the `denyAll()` rule in the same chain; if unauthenticated requests need 401 instead of 403, configure an authentication entry point / authorization behavior intentionally rather than inferring from the table above.

## 9. Reading Two Kinds of "Success" Accurately

To avoid semantic errors, distinguish:

- **Converter success:** built an `Authentication` request from HTTP data. It is not yet authenticated.
- **Authentication success:** manager/provider verified credentials and returned a trusted `Authentication`.
- **Success handler response success:** the filter decided the HTTP response of *the authentication endpoint*. It **does not automatically** prove the user can access every future resource.

For instance, calling POST `/login/alpha` and receiving HTTP 200 only proves credentials were accepted by alpha manager *on that request*. Because the sample app is stateless and issues no token, the client has no new proof to automatically call another endpoint on the next request. In a real flow, maintaining login state requires a clear contract: session cookie + appropriate repository, or a signed/issued token verified on subsequent requests, etc.

### 9.1. When Is SecurityContextRepository Used?

In session-backed form login flows, successful authentication typically needs to place the trusted `Authentication` into `SecurityContext` and persist it via an appropriate repository for subsequent requests to reuse. Modern Spring Security versions emphasize **explicit** context saving at the point of authentication. `AuthenticationFilter` integrates with `SecurityContext`/Repository and handlers, though persistence depends on repository configuration, session policy, and mechanism used.

If you customize the repository, keep it aligned with how other filters load context, session fixation protection, CSRF, logout, and session storage. Never write `SecurityContextHolder.getContext().setAuthentication(result)` alone and assume every future request is logged in.

### 9.2. When Should Processing Continue to a Controller?

If the goal is to **authenticate every API request** and then let a controller handle it, you need a filter architecture and success behavior suited for per-request authentication, or standard filters like `BasicAuthenticationFilter`/bearer token filters. In this example, `AuthenticationSuccessHandler` actively writes the response and terminates the login request, so it does **not** act as a transparent "header checker" across the pipeline for all API requests.

Attaching a 200-returning success handler to a filter matched against all URLs can prevent controllers from **ever being called**. Check the filter's contract before replacing standard filters with a custom filter.

### 9.3. When Can a Converter Returning null Still Produce 401/403 Later?

If the converter returns `null`, the authentication filter normally continues the chain. A downstream authorization rule may still block a request lacking an authenticated principal. Thus the HTTP outcome **depends on the entire chain**; you cannot conclude `null => 200` or `null => 401` just by looking at the converter.

In this lesson, missing password at the login endpoint throws `BadCredentialsException` so the failure handler explicitly returns 401; that is the example's protocol choice, not a universal rule for all converters.

## 10. Techniques for Choosing a Manager: Path, Header, Tenant, Token

A resolver can inspect path, request headers, query params, host, issuer, or other metadata; **data used to select a manager is not inherently trustworthy**. Decisions should follow these principles:

1. Maintain an explicit allowlist of valid values and a default **deny** policy when no manager matches.
2. Reuse pre-configured managers and providers; never construct expensive objects per request.
3. Enforce tenant/issuer boundaries inside the manager during authentication, not only at routing time.
4. If using `Host`, forwarded headers, or gateway metadata, ensure proxies are truly trusted and normalize those sources.
5. If selecting a manager based on a JWT issuer, verify signatures and issuer/audience via trusted mechanisms; never trust unverified JWT payloads as authority claims.
6. Never let an overly permissive "default" manager handle misrouted requests.
7. Include **cross-tenant** tests: credentials from tenant A must never be accepted by tenant B's manager.
8. Never put passwords or header tokens into logs; to observe routing, log non-sensitive paths/manager IDs and overall outcomes.

Illustrative trust-boundary scenario:

~~~text
Client: POST /login/beta
        username=alice&password=alpha-pass

Filter: path matches login endpoint
Converter: builds authentication request principal=alice
Resolver: selects beta manager
Beta manager: checks against beta credentials -> rejected
Failure handler: HTTP 401
~~~

Claiming `alice` in the request or deliberately choosing the beta path does not make beta manager grant `TENANT_BETA`. This is the strength of separating routing from verification.

## 11. Common Errors and Diagnostic Directions

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Filter never runs | `RequestMatcher` does not match; another chain was selected; filter not added to chain | HTTP method/path, `securityMatcher`, `@Order`, `addFilterAt` |
| Converter always returns null | Header/param missing or parser mismatches content type | Actual request, form field names, null vs exception contract |
| `Authentication` created yet still 401 | Manager/provider rejected credentials; resolver selected wrong manager | Token type, password encoder, manager selection |
| Request with valid password fails cross-tenant | Resolver chose a manager backed by a different user store | Verify tenant routing / identity binding |
| Response 200 yet controller never runs | Success handler ended the request | Auth filter flow, handler design |
| Next request behaves as not logged in | No session/token saved or stateless policy | Repository, session, token flow |
| POST always 403 before converter | CSRF filter blocked unsafe request | CSRF configuration, cookie/session client model |
| Client-declared role gets accepted | Converter/provider trusted payload | Never assign trusted authorities from unverified sources |
| Two filters handle the same endpoint | Custom filter overlaps form login/Basic configurer | Filter ordering, URL matchers, overlapping configurers |
| Resolver builds a new manager per request | Factory placed inside resolve callback | Create managers at bean init; resolve only selects |
| Manager does not support `Authentication` type | Converter builds token unsupported by provider | Provider `supports(...)`, manager architecture |
| Logs contain raw credentials | Overly broad request/form/token logging | Redact, reduce security logging, never print Authorization |
| Converter tests pass while MockMvc fails | Tested parsing only, not filter/chain/handler | Integration tests with the security filter chain |
| MockMvc returns 200 while runtime differs | MockMvc missing filter chain or different context config | `@AutoConfigureMockMvc` / apply `springSecurity()` |

### 11.1. Debugging in Request Order

Do not start by "disabling CSRF" or "adding permitAll to every URL". Verify step by step:

1. Does the URL/method belong to the right `SecurityFilterChain`?
2. Does that chain contain `AuthenticationFilter` at the expected position?
3. Does the filter's `RequestMatcher` match the request?
4. Does `AuthenticationConverter` read the right fields/headers and create an unauthenticated token?
5. Which manager did the resolver choose? Is it within the designed allowlist?
6. Did the manager actually verify credentials/issuer/user state/tenant binding?
7. What principal and authorities does the resulting `Authentication` carry? Are sensitive credentials removed?
8. How did the failure/success handler respond? Are status codes accurate without leaking secrets?
9. If subsequent requests must stay logged in, is there a clear session/token/repository mechanism?
10. Did authorization or CSRF in another filter deny the request before or after the authentication attempt?

**Do not read a stack trace as proof of valid/invalid roles** before identifying the exact failure path. If a request is blocked early by the CSRF filter, the converter may never have executed. If a request hits another chain, the custom filter was never even evaluated.

### 11.2. Enabling Logs for Observation (Learning Environment)

You can use the property:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

At startup, look for details on the security filter chain and configured filters. At request time, observe the security traversal and statuses, without assuming every version prints identical log lines. Avoid overly broad debug/trace logging in production, and especially avoid logging raw passwords, tokens, or session cookies. Test over HTTPS whenever non-demo credentials are involved.

When using an IDE debugger, set breakpoints in the converter, resolver, manager lambda, and success/failure handler callbacks. A valid alpha login should hit all four steps in order; a public GET should hit none of the login callbacks.

## 12. Hands-On Exercises

1. Trace the path of `POST /login/alpha` in order: matcher → converter → resolver → manager → success/failure handler. Note the input and output types at each step.
2. Replace `return UsernamePasswordAuthenticationToken.unauthenticated(...)` with an authenticated token granting authorities directly inside the converter. Explain why this is a dangerous anti-pattern (do not deploy to production).
3. Write a unit test: missing username causes the converter to throw `BadCredentialsException`; why did the demo choose an exception rather than `null`?
4. Try submitting `alice/alpha-pass` to the beta endpoint; explain why the resolver **selects a manager** yet authentication still fails.
5. Add a gamma tenant with its own user/secret and dedicated manager, ensuring fallback does not grant permissions. Write full tests for valid gamma, invalid gamma, and alpha credentials sent to gamma.
6. Verify the filter matcher accepts only POST; try calling GET on the same URL and explain why the final outcome can come from authorization/MVC rather than the login filter.
7. If you want login to persist via session, list the architectural changes that must be evaluated: repository, session fixation, CSRF, cookies, logout, and security context lifecycle. Do not merely add a single `setAuthentication(...)` line.
8. Explain why `addFilterAt` is not a "drop-in replacement for form login" in every configuration. When two filters target the same URL, how would you debug it?
9. Convert the form-urlencoded example to JSON: what must the converter handle regarding content type, body reading, parsing exceptions, and sensitive credential data?
10. When adding a JWT API, should you use built-in resource server configuration or hand-roll a converter + manager? Which signature, issuer, audience, and key rotation checks must never be skipped?
11. For an endpoint restricted to users with `TENANT_ALPHA`, where must the authorization rule be enforced? Why does the resolver picking alpha manager not replace an authorization rule?
12. Explain the difference between the 401 status returned by the failure handler in the example and a 403 returned by CSRF/authorization from another filter. Diagnose from logs without exposing passwords.

## 13. Pre-Production Checklist for Custom Authentication Flows

- [ ] Clear justification for a custom filter over `httpBasic`, `formLogin`, or OAuth2/resource-server support.
- [ ] URL/method/content type matched accurately; filter chain covers all protected resources.
- [ ] Converter creates an **unauthenticated request** and never trusts client-declared roles/tenants.
- [ ] Resolver fails closed, selects from pre-configured managers, and never creates managers per request.
- [ ] Manager/provider thoroughly verifies secrets, user state, and tenant/issuer bindings; no hardcoded credentials.
- [ ] Proper password hashing/`PasswordEncoder` used for password credentials; rate limiting/lockout applied as needed.
- [ ] Success/failure handling is intentional, with statuses and responses leaking no secrets.
- [ ] Session/token/refresh/logout and `SecurityContext` persistence are explicitly designed.
- [ ] CSRF evaluated against the cookie/session and browser client model, never disabled unconditionally.
- [ ] HTTPS enforced, along with safe audit logging, metrics, and cross-tenant tests.
- [ ] Tests cover converter, manager selection, valid/invalid credentials, and HTTP integration through the Spring Security filter chain.
- [ ] Authentication success is separated from authorization; endpoints still enforce explicit authorization rules.

**Summary:** `AuthenticationFilter` decides which requests are processed and orchestrates the authentication attempt; `AuthenticationConverter` translates HTTP input into an unverified `Authentication` request; `AuthenticationManagerResolver` chooses the appropriate manager by context; **the manager/provider proves identity**, and then success/failure handling determines the HTTP response and configured context persistence mechanism. Mastering this boundary is the foundation for extending Servlet authentication flows without introducing vulnerabilities by mixing up routing, verification, sessions, and authorization.
