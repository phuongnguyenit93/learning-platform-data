# Integrating a Custom AuthenticationProvider with a Filter, AuthenticationManager, and Success/Failure Handlers

## 1. Goal and Scope

A custom `AuthenticationProvider` solves only **one part** of the login process: inspecting one type of `Authentication` and returning an authentication result. For users to actually log in over HTTP, the application must also build a token from the request, forward the token to the manager, handle success/failure results, and decide whether to persist a session.

In **Spring Security Servlet**, the typical links in the chain are:

1. **Filter**: identifies a login request and turns inbound data into an unauthenticated `Authentication`.
2. **AuthenticationManager** (typically `ProviderManager`): selects an `AuthenticationProvider` via `supports(Class<?>)` and requests verification.
3. **AuthenticationProvider**: verifies credentials using rules of the specific mechanism, returning an authenticated `Authentication` or throwing `AuthenticationException`.
4. **SessionAuthenticationStrategy** and **SecurityContextRepository** (when using sessions): handle session fixation, CSRF, and saving `SecurityContext` so subsequent requests recover the identity.
5. **AuthenticationSuccessHandler** / **AuthenticationFailureHandler**: decide the HTTP response, such as JSON 200/401 or an appropriate redirect.

This lesson targets **Java 17+, Spring Boot 3.5.x, Spring Security 6.x, Servlet MVC applications**. The example uses a demo login code from a header to focus on **wiring the components properly**; this is not presented as a production credential storage approach. WebFlux's `AuthenticationWebFilter` and `ReactiveAuthenticationManager` use a different API.

## 2. Overall Flow Diagram

~~~text
Client
  | POST /api/login
  | Header: X-Login-Code: <code>
  | Cookie: JSESSIONID=...
  | Header: X-CSRF-TOKEN: <token>
  v
SecurityFilterChain
  |
  +-- CsrfFilter: blocks POST with missing/invalid CSRF token when using cookies/sessions
  |
  +-- DemoCodeLoginFilter (matches only POST /api/login)
  |      |
  |      +-- reads X-Login-Code
  |      +-- DemoCodeAuthenticationToken.unauthenticated(...)
  |      |
  |      v
  |   AuthenticationManager / ProviderManager
  |      |
  |      +-- provider.supports(DemoCodeAuthenticationToken.class)
  |      |       false -> try another provider
  |      |       true  -> provider.authenticate(token)
  |      |
  |      +-- verify credential
  |      |       invalid -> AuthenticationException
  |      |       valid   -> Authentication with authenticated=true
  |      v
  |   AbstractAuthenticationProcessingFilter
  |      |
  |      +-- Success:
  |      |     SessionAuthenticationStrategy
  |      |     SecurityContextHolder + SecurityContextRepository
  |      |     AuthenticationSuccessHandler -> HTTP 200 JSON
  |      |
  |      +-- Failure:
  |            clear SecurityContextHolder
  |            AuthenticationFailureHandler -> HTTP 401 JSON
  |
  +-- GET /api/me on subsequent request:
        SecurityContextRepository loads context from HttpSession
        AuthorizationFilter verifies authenticated -> controller
~~~

**Clearly distinguish two kinds of handlers:**

- `AuthenticationSuccessHandler` and `AuthenticationFailureHandler` handle **the outcome of an authentication attempt processed by the filter**.
- `AuthenticationEntryPoint` handles when a request to a protected resource is **unauthenticated** (e.g., `GET /api/me` without a valid session).
- `AccessDeniedHandler` typically handles an **authenticated** user with **insufficient permissions** (HTTP 403).
- `CsrfFilter` can return 403 **before the login filter is ever invoked**. Do not assume every login error goes through `AuthenticationFailureHandler`.

## 3. The APIs That Need to Connect

| Component | Input | Output or responsibility |
| --- | --- | --- |
| `AuthenticationFilter` or custom filter | `HttpServletRequest`, request matcher | Creates unauthenticated `Authentication`; calls manager |
| `AuthenticationManager.authenticate(Authentication)` | Unauthenticated `Authentication` | Authenticated `Authentication` or `AuthenticationException` |
| `AuthenticationProvider.supports(Class<?>)` | Java class of the token | Decides whether the provider can inspect that token type |
| `AuthenticationProvider.authenticate(...)` | Token object of the right type | Verifies credentials, returns result or exception/`null` per contract |
| `SecurityContextHolder` | Successful Authentication | Holds identity in the context of the currently executing request/thread |
| `SecurityContextRepository` | `SecurityContext` | Saves/loads context across requests when using sessions |
| `SessionAuthenticationStrategy` | Newly succeeded auth + servlet request/response | Handles session fixation, session limits, CSRF tokens per policy |
| `AuthenticationSuccessHandler` | Request, response, successful auth | HTTP 200/204, redirect, or JSON response |
| `AuthenticationFailureHandler` | Request, response, `AuthenticationException` | HTTP 401, error redirect, safe message |
| `AuthenticationEntryPoint` | Request to protected URL when unauthenticated | Prompts for login or returns HTTP 401 |

**Critical contract:** a filter creates an **unauthenticated** token; the provider never reads roles/`isAuthenticated` from the client. `supports` only picks the matching class, without verifying secrets. Handlers decide the response and do not replace credential verification.

### Why Understand ProviderManager?

A `ProviderManager` can hold multiple providers. It queries `supports(authentication.getClass())` in turn, skips unsupported providers, calls `authenticate` on matching providers, and stops once it gets a successful result. A provider can return `null` to yield handling; depending on exceptions and configuration, the manager may try later providers. If no provider succeeds and no parent manager resolves it, `ProviderNotFoundException` may occur.

Therefore, `ProviderNotFoundException` usually requires checking **token types and manager/provider registration**, rather than just checking passwords. Never “fix” it with `supports(...) { return true; }` for all token types.

## 4. Choosing Filter Integration: Two Valid Approaches

**Approach A — Reuse a built-in filter.** If the custom provider accepts `UsernamePasswordAuthenticationToken`, you can use `formLogin`/`UsernamePasswordAuthenticationFilter` and register the provider in the manager. The built-in filter already parses form-urlencoded `username`/`password` and integrates success/failure and sessions. This fits when the intake looks like standard form login while user verification differs.

**Approach B — A dedicated token/protocol.** If using API keys, OTPs, signed challenges, or a new mechanism, use a dedicated token and a filter reading the exact input data. Spring Security supports pairing `AuthenticationFilter` with `AuthenticationConverter`; another option is extending `AbstractAuthenticationProcessingFilter`.

This exercise picks **`AbstractAuthenticationProcessingFilter`** because it has built-in configuration points: `setAuthenticationManager`, `setSessionAuthenticationStrategy`, `setSecurityContextRepository`, `setAuthenticationSuccessHandler`, and `setAuthenticationFailureHandler`. This directly illustrates all five required components. When using `AuthenticationFilter` instead, pay attention to its session and context persistence mechanisms; do not assume different filters share identical hooks.

## 5. Complete Example: Custom Provider + Login Filter + Manager + Handlers

The demo supports:
- `POST /api/login` accepting an `X-Login-Code` header and CSRF token, returning JSON on login success or failure.
- `GET /api/csrf` letting the client obtain a CSRF token and session cookie before POSTing.
- `GET /api/me` allowing only logged-in users, reading identity from the session.
- A single `DemoCodeAuthenticationProvider` accepting `DemoCodeAuthenticationToken`; the valid credential is `learn-12345` (for demo use only).

Never use `POST /api/login` in a real system with a shared secret hardcoded in source code. Use an identity service/credential store with secret management, auditing, expiration/revocation, and brute-force protection. This is an **HTTP session** model, not a stateless JWT model.

### 5.1. Project Structure and Maven

~~~text
auth-chain-demo/
├── pom.xml
└── src/
    ├── main/java/demo/authchain/AuthChainDemoApplication.java
    └── test/java/demo/authchain/AuthChainDemoApplicationTests.java
~~~

The following `pom.xml` is for **Java 17 and Spring Boot 3.5.7**; the starter manages compatible Spring Security library versions through dependency management:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>auth-chain-demo</artifactId>
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
~~~

For products using newer Spring Boot/Spring Security versions, apply the security patches supported by the project; the example is pinned to the 3.5/6.5 line to illustrate and verify API compatibility.

### 5.2. Complete Java Code

Create file `src/main/java/demo/authchain/AuthChainDemoApplication.java`:

~~~java
package demo.authchain;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthChainDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthChainDemoApplication.class, args);
    }

    // 1. Provider -> Manager: only this provider is invoked for its token.
    @Bean
    AuthenticationManager loginAuthenticationManager() {
        AuthenticationProvider provider = new DemoCodeProvider();
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager loginAuthenticationManager,
            ObjectMapper objectMapper) throws Exception {

        // 2. Repository used to SAVE context on successful login
        // and RELOAD context on subsequent requests with a session.
        SecurityContextRepository contextRepository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        // 3. Using cookies/sessions -> keep CSRF, do not disable it for /api/login.
        CsrfTokenRepository csrfRepository = new HttpSessionCsrfTokenRepository();

        // 4. Filter receives the exact AuthenticationManager above.
        DemoCodeLoginFilter loginFilter =
            new DemoCodeLoginFilter(loginAuthenticationManager);

        loginFilter.setSecurityContextRepository(contextRepository);
        loginFilter.setSessionAuthenticationStrategy(
            new CompositeSessionAuthenticationStrategy(
                List.of(
                    new ChangeSessionIdAuthenticationStrategy(),
                    new CsrfAuthenticationStrategy(csrfRepository)
                )
            )
        );

        // 5. Success: filter already ran session strategy and saved SecurityContext.
        loginFilter.setAuthenticationSuccessHandler(
            (request, response, authentication) -> {
                response.setStatus(HttpServletResponse.SC_OK);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                objectMapper.writeValue(
                    response.getWriter(),
                    Map.of(
                        "status", "authenticated",
                        "principal", authentication.getName()
                    )
                );
            }
        );

        // 6. Failure: do not return secrets or reveal differences about users.
        loginFilter.setAuthenticationFailureHandler(
            (request, response, exception) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                objectMapper.writeValue(
                    response.getWriter(),
                    Map.of("error", "invalid_credentials")
                );
            }
        );

        http
            .authenticationManager(loginAuthenticationManager)
            .securityContext(context ->
                context.securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(errors -> errors.authenticationEntryPoint(
                (request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            // Avoid form/basic filters not serving the demo protocol.
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // Place filter at a known login position in the security chain.
            .addFilterAt(loginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    // Token with dedicated semantics: credential is a code from the client.
    static final class DemoCodeAuthenticationToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private String code;

        private DemoCodeAuthenticationToken(
                Object principal,
                String code,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {
            super(authorities);
            this.principal = principal;
            this.code = code;
            // Only the class's private factory decides the trusted state.
            super.setAuthenticated(authenticated);
        }

        static DemoCodeAuthenticationToken unauthenticated(String code) {
            return new DemoCodeAuthenticationToken(
                "unverified", code, List.of(), false);
        }

        private static DemoCodeAuthenticationToken verified(String name) {
            return new DemoCodeAuthenticationToken(
                name,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_CLIENT")),
                true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return code;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            this.code = null;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Cannot trust an unverified login token");
            }
            super.setAuthenticated(false);
        }
    }

    // Provider understands only DemoCodeAuthenticationToken.
    static final class DemoCodeProvider implements AuthenticationProvider {

        private static final String LEARNING_ONLY_CODE = "learn-12345";

        @Override
        public boolean supports(Class<?> type) {
            return DemoCodeAuthenticationToken.class.equals(type);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (authentication == null ||
                    authentication.getClass() != DemoCodeAuthenticationToken.class) {
                return null;
            }

            DemoCodeAuthenticationToken attempt =
                (DemoCodeAuthenticationToken) authentication;

            if (attempt.isAuthenticated()
                    || !(attempt.getCredentials() instanceof String supplied)
                    || supplied.isBlank()) {
                throw new BadCredentialsException("Invalid credentials");
            }

            byte[] expected =
                LEARNING_ONLY_CODE.getBytes(StandardCharsets.UTF_8);
            byte[] actual =
                supplied.getBytes(StandardCharsets.UTF_8);

            if (!MessageDigest.isEqual(expected, actual)) {
                throw new BadCredentialsException("Invalid credentials");
            }

            // Principal and authorities are decided on the server side.
            return DemoCodeAuthenticationToken.verified("training-client");
        }
    }

    // Filter: matcher + code extraction + calling manager.
    static final class DemoCodeLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        DemoCodeLoginFilter(AuthenticationManager manager) {
            super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response) {

            String code = request.getHeader("X-Login-Code");
            if (code == null || code.isBlank()) {
                throw new BadCredentialsException("Invalid credentials");
            }

            Authentication candidate =
                DemoCodeAuthenticationToken.unauthenticated(code);
            return getAuthenticationManager().authenticate(candidate);
        }
    }

    @RestController
    static class DemoApi {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName()
            );
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            );
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("principal", authentication.getName());
        }
    }
}
~~~

### 5.3. Exact Integration Points in the Code

**(1) Provider and Manager.** The `loginAuthenticationManager()` bean builds a `ProviderManager` containing `DemoCodeProvider`. `DemoCodeProvider.supports(...)` uses exact class comparison so it handles only `DemoCodeAuthenticationToken`. When credentials are wrong, the provider throws `BadCredentialsException`. When valid, it returns a trusted token with a server-supplied principal and authorities. No secret is returned in the result token.

**(2) Filter decides when to authenticate.** `DemoCodeLoginFilter` extends `AbstractAuthenticationProcessingFilter` with a `POST /api/login` matcher. It reads the header, creates an unauthenticated token, and calls `getAuthenticationManager().authenticate(candidate)`. A `GET /api/me` is not “eaten” by this filter or turned into a new login attempt.

**(3) Manager is wired accurately.** The exact same manager object is passed to the filter and declared via `http.authenticationManager(...)`. If there are multiple `SecurityFilterChain` beans, each chain can have its own manager; always check the chain actually handling the URL. Declaring a provider as a Spring bean without connecting it to the manager used by the filter can trigger `ProviderNotFoundException`.

**(4) Handlers decide the response.** When the manager verifies successfully, the filter runs the session strategy, builds/saves the context, and calls the success handler returning `200 OK` with JSON. If authentication fails, the filter calls the failure handler returning `401 Unauthorized` and a consistent JSON response. Never let arbitrary exception messages or raw credentials leak to the client.

**(5) Context and session.** `SecurityContextHolder` serves the current request; `SecurityContextRepository` determines whether identity can be reloaded on subsequent requests. Saving in `HttpSession` and reading from the same repository lets `GET /api/me` see the logged-in user. `RequestAttributeSecurityContextRepository` helps keep the context across dispatches of the same request, while `HttpSessionSecurityContextRepository` persists context across requests.

**(6) Session strategy.** `ChangeSessionIdAuthenticationStrategy` rotates the session ID to mitigate session fixation. `CsrfAuthenticationStrategy` invalidates the old CSRF token upon successful authentication, so the frontend must fetch a new token before subsequent state-changing requests. With `AbstractAuthenticationProcessingFilter`, using `setSessionAuthenticationStrategy` ensures the session strategy runs in the successful authentication flow before the success handler.

**(7) Blocking unauthenticated access.** `.anyRequest().authenticated()` still guards protected endpoints. A `GET /api/me` request lacking a session is not a failed login, so it receives `401` from `AuthenticationEntryPoint` in this configuration.

## 6. Manual Execution and Reading HTTP Responses Properly

In the project directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

The Spring Boot application requires Maven and JDK 17+; it cannot be compiled standalone with `javac` if Spring Security, Jackson, and Jakarta Servlet are missing from the classpath.

First fetch the session cookie and CSRF token:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

The body will have the following **shape**; the actual token is a random per-session string:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<actual-csrf-token>"}
~~~

Send the POST with the cookies and the **actual token** retrieved from the previous step:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -X POST http://localhost:8080/api/login \
  -H 'X-Login-Code: learn-12345' \
  -H 'X-CSRF-TOKEN: <actual-csrf-token>'
~~~

When valid, expect HTTP 200 with JSON content (property order does not matter):

~~~json
{"status":"authenticated","principal":"training-client"}
~~~

Use the updated session cookie to call the protected endpoint:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected:

~~~json
{"principal":"training-client"}
~~~

Other important cases:

| Action | Expected result |
| --- | --- |
| POST with valid code and valid CSRF token | `200 OK`, success JSON, session saved |
| POST with wrong code but valid CSRF | `401 Unauthorized`, `{"error":"invalid_credentials"}` |
| POST missing `X-Login-Code` but valid CSRF | `401 Unauthorized`, same error JSON |
| POST missing/invalid CSRF token | `403 Forbidden` handled by `CsrfFilter` before login filter |
| GET `/api/me` without valid session | `401 Unauthorized` from `AuthenticationEntryPoint` |
| GET `/api/me` with authenticated session | `200 OK` and principal |
| GET `/api/login` | Does not match login filter; if unauthenticated, `401` |
| POST to a URL other than `/api/login` | Does not run login filter; separate authorization/CSRF applies |

**Note:** Do not enter the literal string `<actual-csrf-token>`. On Windows PowerShell, `curl` quoting syntax may differ; use `curl.exe` or an appropriate HTTP client tool. After a successful login, fetch a new CSRF token before making other POST/PUT/PATCH/DELETE calls.

## 7. Testing with MockMvc: Manager, Filter, Handlers, and Session

The following tests serve two goals: verifying **HTTP integration** (right filter, right status, context persistence) and verifying **token type routing** (manager picks only the provider supporting the class). Add `spring-boot-starter-test` and `spring-security-test` in test scope as in `pom.xml` above.

Create `src/test/java/demo/authchain/AuthChainDemoApplicationTests.java`:

~~~java
package demo.authchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthChainDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void loginSucceedsAndSessionWorksOnNextRequest() throws Exception {
        MvcResult result = mvc.perform(post("/api/login")
                .with(csrf())
                .header("X-Login-Code", "learn-12345"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("authenticated"))
            .andExpect(jsonPath("$.principal").value("training-client"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("training-client"));
    }

    @Test
    void incorrectCredentialUsesFailureHandler() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .header("X-Login-Code", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void missingCredentialUsesFailureHandler() throws Exception {
        mvc.perform(post("/api/login").with(csrf()))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void missingCsrfIsRejectedBeforeLoginFilter() throws Exception {
        mvc.perform(post("/api/login")
                .header("X-Login-Code", "learn-12345"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedEndpointWithoutSessionUsesAuthenticationEntryPoint()
            throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void providerSupportsOnlyItsOwnTokenType() {
        var provider = new AuthChainDemoApplication.DemoCodeProvider();

        assertTrue(provider.supports(
            AuthChainDemoApplication.DemoCodeAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
        assertFalse(provider.supports(Authentication.class));
    }

    @Test
    void managerRejectsUnregisteredTokenType() {
        AuthenticationManager manager = new ProviderManager(
            new AuthChainDemoApplication.DemoCodeProvider());

        assertThrows(ProviderNotFoundException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "password")));
    }

    @Test
    void managerRejectsBadCodeEvenWithCorrectTokenClass() {
        AuthenticationManager manager = new ProviderManager(
            new AuthChainDemoApplication.DemoCodeProvider());

        assertThrows(BadCredentialsException.class,
            () -> manager.authenticate(
                AuthChainDemoApplication.DemoCodeAuthenticationToken
                    .unauthenticated("bad")));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected outcome in a suitable environment:** 8 tests pass; no failures/errors. The tests illustrated here are source code to run in the project, not test results already executed on the learner's system.

Why do these tests matter?

- `loginSucceedsAndSessionWorksOnNextRequest` proves the **end-to-end flow**: filter accepts POST, provider checks the code, success handler returns JSON, and context is persisted for later retrieval.
- `incorrectCredentialUsesFailureHandler` isolates the provider-rejection branch from result handling.
- `missingCsrfIsRejectedBeforeLoginFilter` ensures JSON or header login does not silently bypass CSRF when using session cookies.
- `protectedEndpointWithoutSessionUsesAuthenticationEntryPoint` confirms `AuthenticationEntryPoint` handles unauthenticated requests separately from the failure handler.
- `providerSupportsOnlyItsOwnTokenType` and `managerRejectsUnregisteredTokenType` confirm registration and routing by **token class**, preventing a custom provider from accidentally accepting username/password tokens.

If a real project has proxies, context paths, multiple security chains, CORS, logout, or different session policies, add corresponding integration tests.

## 8. Simpler Integration with Built-In Form Login

Not every custom provider requires a new filter. If the task is replacing username/password verification rules while **still using HTML form login**, `UsernamePasswordAuthenticationFilter` already constructs `UsernamePasswordAuthenticationToken` and invokes the manager. Simply register a provider with `supports(UsernamePasswordAuthenticationToken.class)` returning true and configure handlers.

Example **illustrative configuration snippet**, assuming `customUsernamePasswordProvider` is already a valid `AuthenticationProvider`:

~~~java
http
    .authenticationProvider(customUsernamePasswordProvider)
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .successHandler((request, response, authentication) -> {
            response.sendRedirect(request.getContextPath() + "/home");
        })
        .failureHandler((request, response, exception) -> {
            response.sendRedirect(request.getContextPath() + "/login?error");
        })
        .permitAll()
    );
~~~

Notes:
- This is **not** a standalone program; `customUsernamePasswordProvider` and imports must be supplied inside an existing `SecurityFilterChain`.
- The default form login filter reads `username`/`password` from form parameters; it **does not automatically read JSON**.
- If both `DaoAuthenticationProvider` and a custom provider support `UsernamePasswordAuthenticationToken`, you must understand manager ordering and fallback behavior. A provider returning `null` differs from one throwing `BadCredentialsException`; another provider may still be tried depending on the case.
- `sendRedirect` to `/home` is a server-fixed destination. If using `next` or `returnUrl` from the client, validate the target to prevent open redirects.
- Form login strategies are configured by Spring Security per the standard filter mechanism; when building your own filter, review session and context persistence carefully.

Choose reuse when an existing filter already fits the input protocol; choose a custom filter when you have a genuinely different token type and request-parsing mechanism.

## 9. Alternative Option: AuthenticationFilter + AuthenticationConverter

When you want to compose components instead of extending `AbstractAuthenticationProcessingFilter`, Spring Security provides `AuthenticationFilter`:

~~~java
// Illustrates component wiring, not a standalone runnable configuration.
AuthenticationConverter converter = request -> {
    String code = request.getHeader("X-Login-Code");
    if (code == null || code.isBlank()) {
        throw new BadCredentialsException("Invalid credentials");
    }
    return DemoCodeAuthenticationToken.unauthenticated(code);
};

AuthenticationFilter filter = new AuthenticationFilter(manager, converter);
filter.setRequestMatcher(
    new AntPathRequestMatcher("/api/login", "POST"));
filter.setSecurityContextRepository(contextRepository);
filter.setSuccessHandler(successHandler);
filter.setFailureHandler(failureHandler);
~~~

`AuthenticationFilter` is suited for **separating the step of converting a request into an `Authentication`**. However, understand the differences between filters:

- `AuthenticationFilter` has `setSecurityContextRepository`, and by default **does not save** `SecurityContext` unless a repository is configured.
- `AbstractAuthenticationProcessingFilter` in the main example has `setSessionAuthenticationStrategy`, which runs session strategies during successful authentication.
- If replacing the example with `AuthenticationFilter` while still using cookies/sessions, integrate equivalent session fixation and CSRF mechanisms appropriately; do not copy configuration verbatim from one filter to another assuming identical behavior.
- If the mechanism is truly stateless and the client sends a token on **every request**, the authentication model may not need a session repository, but it does need a filter verifying the token on every protected request. You cannot merely return 200 on `POST /api/login` and expect Spring Security to recognize the user on the next request automatically.

## 10. Statefulness, SecurityContext, and Error Flows

### 10.1. What Is Stored and When?

`SecurityContextHolder` defaults to a thread-bound strategy, fitting most standard Servlet requests. It does not automatically mean persistent login. In Spring Security 6, if a custom filter/controller completes authentication itself, **saving `SecurityContext`** into the appropriate repository is a decision you must make explicitly. The main example passes the same `DelegatingSecurityContextRepository` to both the filter and `HttpSecurity`.

Never combine a “stateless” policy with expecting sessions to remember logins:

| Mode | What does the client send next? | Where does context live? |
| --- | --- | --- |
| Session cookie | Session cookie, resent by the browser | Server reads `HttpSession` via repository |
| Stateless bearer token | Token in `Authorization` header on every request | Filter verifies token per request, usually no session stored |
| HTTP Basic | Username/password in header on every request | Basic authentication filter verifies per configuration |
| One-time login returning 200 without saving anything | No new credentials | Next request can result in `401` |

### 10.2. Error Handling and Preventing Information Leaks

- **Authentication failure due to credentials:** use `AuthenticationFailureHandler` to return uniform errors, e.g., `401` and an `invalid_credentials` code. Never echo codes/passwords or reveal whether a user exists.
- **Unauthenticated request to a protected URL:** `AuthenticationEntryPoint`, usually 401 for APIs or redirect to login for web UIs.
- **Authenticated but missing permissions:** `AccessDeniedHandler` and authorization rules (usually 403). Providers never grant authorities just because a client sent a role.
- **CSRF failure:** defaults to 403 usually, occurring before the login handler when the CSRF filter blocks it.
- **Wrong Content-Type or malformed JSON:** if a filter uses a JSON converter, you can distinguish 400/415 from 401 via exception types and handlers. This example does not parse JSON.
- **Internal errors:** do not turn every `RuntimeException` into 401; configure logging/observability and appropriate 5xx responses.

### 10.3. Preventing Session Fixation and Keeping CSRF

With cookie-based logins, session fixation is a risk if the session ID before and after authentication stays the same. `ChangeSessionIdAuthenticationStrategy` rotates the session ID when a session already exists. `CsrfAuthenticationStrategy` clears the old CSRF token on successful authentication to force clients to fetch a fresh token.

If production limits concurrent login sessions, the session strategy needs `SessionRegistry` and proper session tracking/invalidation. If logout exists, ensure session and security context destruction alongside CSRF/token rotation. Never configure only a JSON-returning success handler and assume the entire session lifecycle is handled.

## 11. Common Mistakes When Wiring Components

| Mistake | Symptom or risk | How to fix |
| --- | --- | --- |
| Creating a provider without attaching it to the filter's manager | `ProviderNotFoundException`, even though the provider class exists | Register the provider in the exact manager or configure the right chain |
| Filter accidentally builds `UsernamePasswordAuthenticationToken` for an API key | API key provider rejects token or another provider mis-handles it | Define a dedicated token matching the protocol |
| `supports` always returns `true` | Provider receives wrong token types | Compare exact concrete token class or intentional subtypes |
| Provider marks inbound token authenticated before verifying | Allows privilege escalation | Create a trusted token only after credential verification succeeds |
| Calling provider directly from a controller bypassing manager arbitrarily | Bypasses routing and standard authentication mechanics | Call `AuthenticationManager.authenticate` when building auth flows |
| Success handler returns 200 without saving context | Subsequent `/api/me` request returns 401 | Configure `SecurityContextRepository` for both save and load |
| Custom filter does not run session strategy | Session ID/CSRF not rotated as expected | Use filter hooks or equivalent session mechanisms |
| Registering filter both as `@Bean` (Servlet filter) and via `HttpSecurity.addFilterAt` | Filter may execute twice, in unexpected order | Register only inside `SecurityFilterChain`; if a Bean is needed, disable servlet registration outside the chain |
| Only failure handler configured, no `AuthenticationEntryPoint` | Accessing protected URL without session returns unexpected response | Configure entry point explicitly |
| Disabling CSRF for all APIs just because JSON/headers are used | Session-cookie endpoints become vulnerable to CSRF per threat model | Keep CSRF for cookies/sessions; tailor to actual credential mechanism |
| Success handler takes redirect URL from client | Open redirect after login | Fix or allowlist redirect targets server-side |
| Logging full headers/tokens during debug | Exposes credentials, secrets, or sessions | Redact logs and restrict trace access |
| Setting `SessionCreationPolicy.STATELESS` while expecting `JSESSIONID` login persistence | Subsequent requests lose authentication | Choose stateful or stateless explicitly and test end-to-end |
| Filter runs on every path | Unrelated requests have credentials read or trigger unintended logins | Match exact HTTP method + path, test multiple URLs |
| Not checking multiple `SecurityFilterChain` beans | Filter sits in a chain that does not receive the request | Verify `securityMatcher` and chain ordering match URLs |
| Assuming success handler grants permissions | Post-login user may still lack permissions | Configure authorization based on server-sourced authorities |

## 12. Pre-Production Review and Security Checklist

- [ ] Every login request passes through the right `SecurityFilterChain` and filter matcher.
- [ ] Filter extracts credentials only from the designed source, never putting passwords/tokens into URLs or logs.
- [ ] Filter creates an **unauthenticated** `Authentication` and calls the right `AuthenticationManager`.
- [ ] `ProviderManager` registers the right provider; `supports` aligns with the token class created by the filter.
- [ ] Provider genuinely verifies credentials and returns a server-determined authenticated principal and authorities.
- [ ] Success and failure handlers return production-appropriate status/body/redirects without leaking secrets or stack traces.
- [ ] `AuthenticationEntryPoint` and `AccessDeniedHandler` distinguish unauthenticated state from insufficient permissions.
- [ ] For session login: context is saved to repository and reloaded on subsequent requests; tested with real cookies.
- [ ] Session fixation, CSRF token rotation, and logout/session invalidation are designed consistently.
- [ ] Rate limiting, secret hashing/lookup, credential revocation/rotation, MFA (when needed), auditing, and HTTPS are configured.
- [ ] Integration tests cover valid login, wrong login, wrong token type, CSRF failure, missing session, expired session, and multiple security chains.
- [ ] Filter is not enabled simultaneously in both Servlet container and Spring Security chain via duplicate registration.
- [ ] For stateless: tokens are verified on **every** relevant request rather than relying on a 200 login response.

## 13. Self-Check Questions

1. Why does implementing `AuthenticationProvider` alone without a filter/manager not automatically create a login endpoint?
2. In the example, in what state does the filter create the token and in what state does the provider return it?
3. What information does the manager use to select `DemoCodeProvider`?
4. Why is a POST login returning 200 not enough if session-based login is required? Which component actually persists the context?
5. What is the difference between `AuthenticationFailureHandler` and `AuthenticationEntryPoint`?
6. Why can a POST without a CSRF token receive 403 before ever reaching the provider?
7. When switching to `AuthenticationFilter`, what must be reviewed regarding session strategy and context repository?
8. If form login already creates the right `UsernamePasswordAuthenticationToken`, when is writing a new filter unnecessary?
9. If a user has a valid session but lacks an endpoint's authority, does the provider or authorization make the final decision?
10. What must you test to ensure a new provider does not interfere with other authentication mechanisms in the same application?

## 14. Official Documentation

1. Spring Security 6.5 — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
2. Spring Security 6.5 API — `AuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
3. Spring Security 6.5 API — `ProviderManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
4. Spring Security 6.5 API — `AbstractAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
5. Spring Security 6.5 API — `AuthenticationFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html
6. Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
7. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
8. Spring Security 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
9. Spring Boot — Dependency management and starters: https://docs.spring.io/spring-boot/3.5.7/reference/using/build-systems.html

**Key takeaway:** a custom provider is only one link. A proper login flow connects **request → authentication filter → manager → provider → session/context → success/failure handlers**, and ensures authorization on subsequent requests is still enforced independently.