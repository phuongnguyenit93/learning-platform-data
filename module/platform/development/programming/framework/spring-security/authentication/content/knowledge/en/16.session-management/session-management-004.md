# SessionAuthenticationStrategy and the Responsibilities of the Login Mechanism in Spring Security

## 1. Why Is Understanding SessionAuthenticationStrategy Necessary?

A user submitting a username/password and receiving HTTP 200 after login **is not enough** to conclude that the session management flow is secure. If the login mechanism is customized, the application must also determine:

- Does the old session ID need to be changed to defend against **session fixation**?
- How many active sessions is a single account allowed to have?
- Does the new session need to be registered in `SessionRegistry` to support concurrent session limits?
- Does the CSRF token issued before login need to be refreshed when the identity changes?
- Is the post-authentication `SecurityContext` persisted so subsequent requests recognize the user?
- What happens when a session strategy rejects continuing the login?

In Spring Security Servlet, the `SessionAuthenticationStrategy` interface is the extension point for `HttpSession`-related behaviors **at the moment a new authentication succeeds**.

~~~java
public interface SessionAuthenticationStrategy {
    void onAuthentication(
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response
    ) throws SessionAuthenticationException;
}
~~~

The three parameters of `onAuthentication` are the verified `Authentication` result, the servlet request, and the response. The strategy **is not responsible for verifying passwords itself**, nor **for deciding whether the user is authorized for a URL**. Those are the responsibilities of `AuthenticationManager`/`AuthenticationProvider` and the authorization system.

**Special note for Spring Security 6:** `SessionManagementFilter` is no longer included in the default configuration as before. Therefore, **the authentication mechanism** is typically responsible for calling `SessionAuthenticationStrategy` when a new authentication occurs. When writing a custom login filter/controller, do not expect another filter to automatically detect the authentication and perform all session tasks for you.

Scope of this lesson: **Java 17+, Spring Boot 3.x / Spring Security 6.x, Servlet applications**; focusing on the moment of successful login, not to be confused with general servlet container session management or reactive WebFlux.

## 2. Precisely Separating Responsibilities

| Component | Responsibility | Does Not Do on Its Own |
| --- | --- | --- |
| `AuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, or custom filter | Reads login request, creates unauthenticated token, calls manager, handles result | Does not decide all business authorization policies |
| `AuthenticationManager` / `AuthenticationProvider` | Verifies credentials, returns authenticated `Authentication` or throws error | Does not automatically write context to HTTP session just because auth succeeded |
| `SessionAuthenticationStrategy` | At new authentication time: session fixation, concurrency, CSRF token lifecycle, `HttpSession`-related actions | Does not replace saving `SecurityContext` |
| `SecurityContextHolder` | Holds `Authentication` in the `SecurityContext` of the currently executing request/thread | Does not guarantee the next request has the same context |
| `SecurityContextRepository` | Saves/loads `SecurityContext`, e.g., via `HttpSession` | Does not rotate session IDs or enforce session limits |
| `AuthenticationSuccessHandler` | Builds the HTTP response after successful authentication | Does not guarantee strategy/repository were called if a custom filter forgot to configure them |
| `AuthenticationFailureHandler` | Returns response for authentication errors or session errors caught by the filter per contract | Does not replace `AuthenticationEntryPoint` for unauthenticated requests |
| Servlet container | Issues/manages `HttpSession`, `JSESSIONID` cookie, `changeSessionId()` | Does not decide Spring Security roles/permissions |
| `AuthorizationFilter` / method security | Decides whether a request/method has sufficient permissions | Not responsible for logging in or rotating session IDs |

A complete session-based login flow:

~~~text
POST /login
    |
    v
Authentication Filter
    |
    +-- Create Authentication.unauthenticated(...)
    |
    v
AuthenticationManager / Provider
    |
    +-- failure -> FailureHandler, do not invoke session success strategy
    |
    +-- success -> Verified Authentication
                         |
                         v
             SessionAuthenticationStrategy
               | protect against session fixation
               | check/register concurrent sessions
               | refresh CSRF token when appropriate
                         |
               +-- session rejected -> SessionAuthenticationException
               |                         |
               |                         v
               |                    FailureHandler
               |
               v
       SecurityContextHolder + SecurityContextRepository
                         |
                         v
              AuthenticationSuccessHandler
                         |
                         v
                HTTP response + cookie
                         |
            Next request sends cookie
                         |
                         v
          SecurityContextRepository loads context
                         |
                         v
                   Authorization
~~~

**Ordering matters:** when the session strategy rejects a login, you must neither save a logged-in context nor send a success response. With `AbstractAuthenticationProcessingFilter`, the framework provides the proper hook to run the strategy after `attemptAuthentication` returns and before `successfulAuthentication`.

## 3. Contract of SessionAuthenticationStrategy in Spring Security 6

`SessionAuthenticationStrategy#onAuthentication` receives the `Authentication` result and may:

1. Leave the request/session unchanged if no change is needed.
2. Rotate the session ID or migrate the session upon successful login.
3. Check the user's session count policy and reject if the threshold is exceeded.
4. Register the newly authenticated session into `SessionRegistry`.
5. Invalidate the old CSRF token to require a new token after the identity change.
6. Throw `SessionAuthenticationException` when continuing authentication in the current session is not allowed.

This strategy should not be called on **every authenticated request**; it is designed for **a new authentication event**. Otherwise, rotating the session ID or clearing the CSRF token on every request can cause the application to malfunction and increase load.

### Why Did Spring Security 6 Change How It Is Invoked?

In common Spring Security 5 configurations, `SessionManagementFilter` could detect a new authentication by comparing `SecurityContextHolder` and `SecurityContextRepository`, and then invoke the session strategy. That approach often required reading the session on every request. In Spring Security 6, the authentication mechanism is expected to invoke the strategy **directly upon authenticating**, reducing unnecessary session checks on non-login requests.

Official Spring Security 6 documentation explicitly states that several previous `sessionManagement` DSL options no longer work in the old way, such as attaching a strategy via `sessionAuthenticationStrategy` on `SessionManagementFilter`. With a custom authentication filter, use that filter's proper hook or call `onAuthentication` at the right moment in the flow you own.

Do not conclude that "enabling `http.sessionManagement(...)` means all custom filters automatically receive the same strategy." You must know whether the specific filter calls it.

## 4. Key Implementations

### 4.1. ChangeSessionIdAuthenticationStrategy

`ChangeSessionIdAuthenticationStrategy` uses `HttpServletRequest.changeSessionId()` (Servlet 3.1+) to replace the existing session ID while keeping appropriate session attributes. This prevents **session fixation**: an attacker tries to make a victim use a pre-known session ID, and then the victim logs in without the ID changing.

~~~text
Before login:
  Session ID = S1, unauthenticated

After successful authentication:
  Session ID = S2, authentication bound to session S2
  S1 can no longer be used as the logged-in user's session
~~~

If **there was no prior session**, the strategy usually has no old ID to replace; after login, `HttpSessionSecurityContextRepository` may create a new session when saving the context. Therefore, a session fixation test must **proactively create a pre-login session** and compare the ID before and after.

Other options:
- `SessionFixationProtectionStrategy` can invalidate/migrate to a new session and transfer attributes per policy.
- Spring Security's default configuration on modern servlet containers typically uses `changeSessionId`.
- Disabling session fixation protection just because a test app fails to retain cookies is unsafe. Check HTTPS, session cookies, proxies, and proper cookie-preserving clients instead.

### 4.2. ConcurrentSessionControlAuthenticationStrategy

`ConcurrentSessionControlAuthenticationStrategy` uses `SessionRegistry` to check the principal's number of active sessions, such as a maximum of one or two sessions. Depending on policy, it can reject the new session (throwing `SessionAuthenticationException`) or mark the old session as expired so the new session is allowed.

~~~text
User A has 1 active session
Policy maximumSessions=1
  ├── exceptionIfMaximumExceeded=true
  │      -> reject the second login
  └── exceptionIfMaximumExceeded=false
         -> allow new login, old session is marked expired
~~~

Marking a session expired in `SessionRegistry` does not mean the servlet container immediately destroys the session cookie. A component such as `ConcurrentSessionFilter` is needed to handle requests from expired sessions along with a registry cleanup mechanism. Without `HttpSessionEventPublisher` or an equivalent session-destroy listener, the registry can keep "ghost" sessions, leading to inaccurate limits.

**This is an optional policy.** Not every application should limit to one session, because browsers, devices, and shared accounts have different requirements. The business decision, how principals are identified, and a consistent `SessionRegistry` are key parts of the design.

### 4.3. RegisterSessionAuthenticationStrategy

`RegisterSessionAuthenticationStrategy` registers the principal and current session ID into `SessionRegistry` **after** concurrency control and session fixation protection have passed. If registered before the ID is rotated, the registry may store the wrong ID or require extra updates.

Proper strategy order when concurrency control is needed:

~~~text
ConcurrentSessionControlAuthenticationStrategy
                ↓
ChangeSessionIdAuthenticationStrategy
                ↓
RegisterSessionAuthenticationStrategy
                ↓
CsrfAuthenticationStrategy (if used)
~~~

`CompositeSessionAuthenticationStrategy` can run these delegates in exact order, stopping if one delegate throws an exception.

### 4.4. CsrfAuthenticationStrategy

`CsrfAuthenticationStrategy` clears the current CSRF token via `CsrfTokenRepository` upon successful authentication, ensuring the pre-login token does not remain the active token for the authenticated session. This is essential when the application relies on **HTTP session cookies** and protects forms/state-changing HTTP methods with CSRF.

In a CSRF-enabled flow:
1. Client fetches a CSRF token before login.
2. POST login includes the cookie and valid CSRF token.
3. Authentication succeeds; the session strategy clears the old CSRF token.
4. Client must fetch a new token before the next POST/PUT/PATCH/DELETE (depending on how the application renders and handles tokens).

Do not use `csrf.disable()` as a way to "fix 403 errors" when a custom login request is missing a CSRF token. Return or render the token according to protocol and send it from the frontend.

### 4.5. CompositeSessionAuthenticationStrategy

`CompositeSessionAuthenticationStrategy` is how you combine multiple session policies without writing a class that calls each strategy manually. It iterates through delegates in declared order:

~~~java
SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        new ChangeSessionIdAuthenticationStrategy(),
        new CsrfAuthenticationStrategy(csrfRepository)
    ));
~~~

This snippet is **only a configuration sample**: it requires imports, `csrfRepository`, and a login filter. If the first strategy throws `SessionAuthenticationException`, subsequent strategies do not run; the filter must route the error into the appropriate failure branch.

### 4.6. NullAuthenticatedSessionStrategy

`NullAuthenticatedSessionStrategy` performs no session work upon authentication. It can suit a **completely stateless** authentication mechanism, but **does not** make the system stateless on its own: you must configure `SessionCreationPolicy.STATELESS`, a non-session repository, per-request bearer token verification, CSRF per threat model, and ensure no cookie-based authentication mechanism accidentally triggers a session.

Do not use the null strategy as a "way to silence session fixation errors" in a cookie/session application.

## 5. Integrating with Each Login Mechanism: Who Must Call the Strategy?

### 5.1. Standard Form Login

With standard `http.formLogin(...)` configuration, Spring Security creates and configures `UsernamePasswordAuthenticationFilter` and related components. In this standard mechanism, the framework integrates session strategies such as session fixation and other enabled policies. Application authors normally do not need to call `onAuthentication` manually.

~~~java
http.formLogin(form -> form
    .defaultSuccessUrl("/home", true)
    .permitAll()
);
~~~

This is a **configuration snippet**, not a standalone program. If the application uses standard form login and needs concurrent session limits, prefer configuring the official `sessionManagement` DSL rather than creating unrelated `SessionRegistry` instances yourself.

### 5.2. Filter Extending AbstractAuthenticationProcessingFilter

This is the demo mechanism. After `attemptAuthentication` returns a successful `Authentication`, the filter invokes the `SessionAuthenticationStrategy` attached via `setSessionAuthenticationStrategy`; it then creates/saves the context and invokes the success handler.

~~~java
customFilter.setSessionAuthenticationStrategy(
    compositeSessionStrategy);
customFilter.setSecurityContextRepository(
    securityContextRepository);
~~~

These are two **distinct, complementary** configurations. One handles the session lifecycle; the other handles context persistence.

### 5.3. AuthenticationFilter + AuthenticationConverter

`AuthenticationFilter` fits when you want to extract reading `HttpServletRequest` into an `AuthenticationConverter`. However, do not assume every filter shares the same setters and lifecycle. In Spring Security 6, `AuthenticationFilter` has `setSecurityContextRepository`; the session authentication mechanism must be designed explicitly, such as using a success handler responsible for invoking the appropriate session strategy **before responding with success** per the filter's API/lifecycle, or choosing a mechanism that already supports the corresponding hook. If adding session logic in a handler, ensure 200 is not sent before the strategy has a chance to reject the login and account for when the context is saved.

For applications needing multiple session policies or strict session fixation, `AbstractAuthenticationProcessingFilter` with its direct hook is often easier to verify.

### 5.4. Custom Controller Calling AuthenticationManager

A `@PostMapping("/login")` endpoint can parse JSON with `@RequestBody` and call `AuthenticationManager`. However, if it does not use a standard login filter, the application must handle everything itself:
- Check CSRF per the cookie/session mechanism.
- Authenticate and obtain `Authentication`.
- Call the session strategy at the right time.
- Create `SecurityContext` and save it via `SecurityContextRepository`.
- Handle `AuthenticationException` and `SessionAuthenticationException` before returning a success result.
- Never let the client dictate principal/roles.

Do not merely call `SecurityContextHolder.getContext().setAuthentication(result)` and assume the next request is logged in: no repository may have saved the context.

### 5.5. OAuth2/OIDC, SAML, Remember-Me, and Pre-Auth

Built-in mechanisms configured by Spring Security have their own filters and lifecycles. Do not blindly inject a global `SessionAuthenticationStrategy` running on every callback just because a callback succeeded; you must understand the corresponding filter, cookies, state, nonce, and security context. When deeply customizing or writing your own authentication mechanism, check its hooks/session policy and context persistence.

A remember-me authentication restored from a cookie on a subsequent request is not the same as a fresh interactive form login. You should not needlessly rotate the session ID on every remember-me request.

### 5.6. JWT Resource Server and Stateless APIs

If an API uses a bearer JWT sent **on every request** and the policy is stateless, there is no "session login" to which Servlet session fixation or concurrent-session control applies. The resource server verifies the token and builds a context for the current request; session strategies meant for form cookies are usually irrelevant.

Do not use `SessionAuthenticationStrategy` to control how many JWTs remain active if access tokens are not tied to `HttpSession`; use TTL, refresh tokens, rotation, revocation/introspection, or token issuance policies instead.

## 6. Complete Java 17 Example: Custom Login with Explicit Session Strategy

To see the effect of each step without depending on IdP infrastructure, the example uses **form-urlencoded login via a custom endpoint** `POST /api/login` with username/password in the body. `AuthenticationManager` uses `DaoAuthenticationProvider` and BCrypt. The filter is written intentionally to demonstrate **attaching `SessionAuthenticationStrategy` manually**; in a real project where standard form login meets your needs, use the built-in `formLogin`.

The application provides:
- `GET /api/csrf`: fetches the CSRF token and creates a pre-login session.
- `POST /api/login`: authenticates username/password, rotates the session ID, refreshes the CSRF token, and saves `SecurityContext`.
- `GET /api/me`: resource accessible only to logged-in users.
- Failure handler returns JSON 401; unauthenticated access to protected endpoints also returns 401 via the entry point.

### 6.1. Structure and Maven

~~~text
session-strategy-demo/
├── pom.xml
└── src/
    ├── main/java/demo/session/SessionStrategyApplication.java
    └── test/java/demo/session/SessionStrategyApplicationTests.java
~~~

The `pom.xml` file uses **Java 17**, Spring Boot 3.5.7 (managing Spring Security 6.5.x):

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
    <artifactId>session-strategy-demo</artifactId>
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

In production, use a Spring Boot version maintained by your team with up-to-date security patches. The version here is pinned so learners have a consistent reference configuration.

### 6.2. Java Implementation File

Create `src/main/java/demo/session/SessionStrategyApplication.java`:

~~~java
package demo.session;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
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
public class SessionStrategyApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionStrategyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // For learning only. In production, use an appropriate user store/IdP.
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        SecurityContextRepository contextRepository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        CsrfTokenRepository csrfRepository =
            new HttpSessionCsrfTokenRepository();

        // Policy invoked after credentials are verified,
        // before saving SecurityContext / returning the success response.
        SessionAuthenticationStrategy sessionStrategy =
            new CompositeSessionAuthenticationStrategy(
                List.of(
                    new ChangeSessionIdAuthenticationStrategy(),
                    new CsrfAuthenticationStrategy(csrfRepository)
                )
            );

        // This filter is created locally inside SecurityFilterChain,
        // not registered as a standalone servlet filter that would run a second time.
        ExampleLoginFilter loginFilter = new ExampleLoginFilter(manager);

        loginFilter.setSessionAuthenticationStrategy(sessionStrategy);
        loginFilter.setSecurityContextRepository(contextRepository);

        loginFilter.setAuthenticationSuccessHandler(
            (request, response, authentication) -> {
                response.setStatus(HttpServletResponse.SC_OK);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.getWriter().write(
                    "{\"status\":\"authenticated\"}"
                );
            }
        );

        loginFilter.setAuthenticationFailureHandler(
            (request, response, exception) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.getWriter().write(
                    "{\"error\":\"login_failed\"}"
                );
            }
        );

        http
            .authenticationManager(manager)
            .securityContext(context ->
                context.securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(errors -> errors.authenticationEntryPoint(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // Insert only into the Spring Security chain at the login position.
            .addFilterAt(
                loginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    static final class ExampleLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        ExampleLoginFilter(AuthenticationManager manager) {
            super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response) {

            String username = request.getParameter("username");
            String password = request.getParameter("password");
            if (username == null || username.isBlank()
                    || password == null || password.isEmpty()) {
                throw new BadCredentialsException("Invalid credentials");
            }

            return getAuthenticationManager().authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    username, password
                )
            );
        }
    }

    @RestController
    static final class Api {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            // CsrfFilter provides CsrfToken as a request attribute.
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
            return Map.of("username", authentication.getName());
        }
    }
}
~~~

### 6.3. Why Must All Three Things Be Configured?

**Task 1 — Authentication:** `ExampleLoginFilter` accepts POST, constructs `UsernamePasswordAuthenticationToken.unauthenticated`, and calls the manager. `DaoAuthenticationProvider` uses `UserDetailsService` + BCrypt to check the password. Prior to this point, there is no basis to associate the session with an authenticated user.

**Task 2 — Session strategy:** `loginFilter.setSessionAuthenticationStrategy(sessionStrategy)` connects the filter to `ChangeSessionIdAuthenticationStrategy` and `CsrfAuthenticationStrategy`. Because the filter extends `AbstractAuthenticationProcessingFilter`, the framework invokes the strategy after `attemptAuthentication` succeeds. If the strategy throws an error, the request takes the failure path instead of returning success.

**Task 3 — Saving and loading context:** `loginFilter.setSecurityContextRepository(contextRepository)` persists the result on successful login; `http.securityContext(...).securityContextRepository(contextRepository)` provides the way to read the context back on the next request. A `SecurityContextHolder` that lives only during the current request is not enough without persistence.

Merely changing the session ID does not mean the user is logged in. Likewise, merely saving the context does not automatically rotate the session ID. All three parts are required in a stateful design.

### 6.4. Why Use the Same CSRF Repository?

`CsrfFilter` validates POST tokens against `HttpSessionCsrfTokenRepository`. `CsrfAuthenticationStrategy` must clear tokens from the **same store type/configuration** for a consistent CSRF lifecycle. If one place uses a cookie repository while the other uses a session repository, the token may not refresh as expected.

This example intentionally uses the session repository and a simple `GET /api/csrf` endpoint so behavior is easy to observe. In an SPA using CSRF cookies and JavaScript, you may need `CookieCsrfTokenRepository` along with a `CsrfTokenRequestHandler` tailored to your SPA policy. Do not copy this CSRF design into production without checking your frontend, CORS, and cookie policy.

## 7. Testing HTTP Manually and Observing the Session

In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

The program uses multiple Spring/Jakarta dependencies, so **it cannot compile standalone with `javac`** without assembling the classpath. Maven manages dependencies and runs the application.

### 7.1. Create a Session Before Logging In

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

The response may carry `Set-Cookie: JSESSIONID=...` and JSON:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<actual-token>"}
~~~

Keep the actual cookie and token. Do not send the placeholder string verbatim. At this step the session already exists, but does not yet contain an authenticated user.

### 7.2. Send the Login Request

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'X-CSRF-TOKEN: <actual-token>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=student' \
  --data-urlencode 'password=demo-password' \
  http://localhost:8080/api/login
~~~

When credentials are valid, expect `200 OK`:

~~~json
{"status":"authenticated"}
~~~

Note that the session cookie can change after login. The client itself must accept the new `Set-Cookie` and continue sending the new cookie. Reusing the old ID or omitting the cookie will not demonstrate that the successful login was persisted for the next request.

### 7.3. Call the Resource After Login

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected:

~~~json
{"username":"student"}
~~~

Trying a wrong password with a valid CSRF token leads to `401 Unauthorized` with body `{"error":"login_failed"}`. A POST missing the CSRF token is typically rejected by `CsrfFilter` with `403 Forbidden` before reaching `ExampleLoginFilter`.

After successful login, call `GET /api/csrf` again with the new cookie to obtain a valid token for subsequent POSTs. When session ID rotation is configured, tests should verify that the session ID actually differs from before rather than checking only JSON 200.

## 8. Integration Testing the True Responsibilities of the Login Mechanism

A test that only calls `AuthenticationManager.authenticate(...)` and sees a valid password **does not prove** that session fixation protection or context persistence ran. You must test through the filter chain.

Create the file `src/test/java/demo/session/SessionStrategyApplicationTests.java`:

~~~java
package demo.session;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionStrategyApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginRotatesExistingSessionAndPersistsContext()
            throws Exception {

        // Create an unauthenticated session using the CSRF endpoint.
        MvcResult before = mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) before.getRequest().getSession(false);
        assertNotNull(session);
        String previousId = session.getId();

        String csrfToken = JsonPath.read(
            before.getResponse().getContentAsString(), "$.token");

        MvcResult login = mvc.perform(post("/api/login")
                .session(session)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header("X-CSRF-TOKEN", csrfToken)
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("authenticated"))
            .andReturn();

        MockHttpSession afterLogin =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(afterLogin);
        assertNotEquals(previousId, afterLogin.getId());

        // A NEW request must read the user back from SecurityContextRepository.
        mvc.perform(get("/api/me").session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void badCredentialsUseFailureHandler() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "incorrect"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("login_failed"));
    }

    @Test
    void missingCredentialsUseFailureHandler() throws Exception {
        mvc.perform(post("/api/login").with(csrf()))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("login_failed"));
    }

    @Test
    void missingCsrfIsDeniedBeforeLoginFilter() throws Exception {
        mvc.perform(post("/api/login")
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedEndpointRequiresSessionAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void csrfEndpointReturnsHeaderNameAndToken() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isString());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected when the project is built properly:** 6 tests pass, with no failures or errors. This is test code provided for learners to execute; it is not a claim that the tests have already been run in the learner's environment.

When using Spring Security Test, `.with(csrf())` simulates a valid POST. However, to meaningfully test session fixation, the first test uses a **real CSRF token and session within the same MockMvc flow**, and then observes whether `changeSessionId()` rotates the ID. Testing only "successful login returns 200" will not catch a filter that forgot to invoke the session strategy.

If you want to test CSRF token rotation, verify the actual token stored in `CsrfTokenRepository` before and after login; note that Spring Security can return a **masked token** in HTML/API responses, so merely comparing the displayed strings across two requests sometimes does not prove the backing token was cleared. Add repository-level tests or verify that the old token is rejected after a new request obtains a token per the chosen policy.

## 9. Case with Concurrent Session Limits

Suppose the product requires **one active session per account**. Adding only `ChangeSessionIdAuthenticationStrategy` is not enough; it only prevents fixation and does not count sessions.

A configuration **illustrating the idea** (not a complete standalone concurrency configuration) might look like:

~~~java
SessionRegistry sessionRegistry = new SessionRegistryImpl();

ConcurrentSessionControlAuthenticationStrategy concurrency =
    new ConcurrentSessionControlAuthenticationStrategy(sessionRegistry);
concurrency.setMaximumSessions(1);
concurrency.setExceptionIfMaximumExceeded(true);

SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        concurrency,
        new ChangeSessionIdAuthenticationStrategy(),
        new RegisterSessionAuthenticationStrategy(sessionRegistry),
        new CsrfAuthenticationStrategy(csrfRepository)
    ));

loginFilter.setSessionAuthenticationStrategy(strategy);
~~~

Relevant imports:

~~~java
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.authentication.session.ConcurrentSessionControlAuthenticationStrategy;
import org.springframework.security.web.authentication.session.RegisterSessionAuthenticationStrategy;
~~~

**Mandatory additions to consider in production:**
- Use **the same `SessionRegistry`** for the control strategy, registration strategy, and the filter handling expired sessions.
- Configure `ConcurrentSessionFilter` or an equivalent expired-session handler; if using the standard DSL, check how the framework configures it automatically.
- Register `HttpSessionEventPublisher` or a suitable listener so the registry updates when a session is destroyed.
- If the system runs multiple instances, an in-memory `SessionRegistryImpl` per node is insufficient to enforce a cluster-wide limit; use a compatible distributed session store and control mechanism.
- Ensure stable `principal.equals/hashCode`. Two principal objects for the same user that are not equal under `equals` will corrupt session counting.
- When rejecting due to exceeding the limit, return a clear error from the failure handler without leaking another user's session or device info.
- Ensure sessions are invalidated on logout and account lock; also test session expiration due to timeout.

The recommended order has a reason: check concurrency **before unnecessarily creating/rotating a session**, rotate the ID to prevent fixation, register the final ID into the registry, and then handle the CSRF lifecycle.

## 10. Why Should You Not Call SessionAuthenticationStrategy Twice?

A common mistake occurs when a developer configures the strategy on the filter *and* calls it again inside the success handler:

~~~java
// Do not do both in the same success flow.
loginFilter.setSessionAuthenticationStrategy(strategy);

loginFilter.setAuthenticationSuccessHandler((req, res, auth) -> {
    strategy.onAuthentication(auth, req, res); // Called a second time!
    res.setStatus(200);
});
~~~

Running it twice can cause:
- The session ID rotates a second time; observed cookies/sessions become confusing.
- The CSRF token gets cleared or replaced again at the wrong moment.
- Concurrency counters/registries get updated more than once or suffer race-condition bugs.
- Tests pass "intermittently" depending on filter/handler order.

**Rule:** designate **a single owner** for calling `onAuthentication` in each new authentication flow. With `AbstractAuthenticationProcessingFilter`, that point is usually the `setSessionAuthenticationStrategy` hook. The success handler should only prepare the response after auth/strategy/context are complete.

Do not call the strategy inside `UserDetailsService` or `AuthenticationProvider`, because those classes do not own the servlet request/response and can be used in non-HTTP contexts.

## 11. Distinguishing SessionAuthenticationException from Password Errors

Although both can route to the failure handler, **their causes and operational actions differ**:

| Scenario | Where it originates | Meaning |
| --- | --- | --- |
| Wrong password | `AuthenticationProvider` / `AuthenticationManager` | Identity could not be verified |
| Provider does not support token | `ProviderManager` | Misrouted/misregistered authentication mechanism |
| Session limit exceeded | `ConcurrentSessionControlAuthenticationStrategy` | Credentials may be valid, yet policy forbids a new session |
| Missing/invalid CSRF token | `CsrfFilter` | State-changing request failed CSRF validation |
| Request to protected resource without session | `AuthenticationEntryPoint` | Authentication required |
| Has session yet lacks authority | Authorization / `AccessDeniedHandler` | Authenticated, yet insufficient permissions |

In public APIs, you can keep a simple message like `login_failed` to avoid disclosing sensitive state. However, internal logs should distinguish "bad credentials" from "session limit exceeded" using **safe error codes**, without logging passwords, CSRF tokens, or full session IDs.

`SessionAuthenticationException` is an `AuthenticationException`, so `AbstractAuthenticationProcessingFilter` can route it to the authentication failure branch instead of the success handler. If writing a custom controller/filter, catch and forward the exception before sending a success response; do not persist the context before the session strategy has a chance to reject.

## 12. Common Mistakes and How to Fix Them

| Mistake | Symptom | How to fix |
| --- | --- | --- |
| Only calling `manager.authenticate` then returning HTTP 200 | Next request may 401, session fixation unhandled | Run strategy at the right time and save context |
| Assuming `SessionManagementFilter` always invokes the strategy | Custom login skips session fixation/concurrency | In Spring Security 6, the authentication mechanism itself is responsible for calling it |
| Using `http.sessionManagement().sessionAuthenticationStrategy(...)` like old configs | Does not apply to custom filter, or rejected | Configure on the specific authentication mechanism's hook |
| Configuring only `SecurityContextRepository` | Login is remembered, yet old session ID is not rotated | Add session fixation strategy |
| Configuring only `ChangeSessionIdAuthenticationStrategy` | ID rotates, yet next request loses auth | Configure saving/loading `SecurityContext` |
| Using `NullAuthenticatedSessionStrategy` in a cookie app to dodge errors | Bypasses essential session protection | Choose the right session policy and fix the root cause |
| Calling `onAuthentication` on every authenticated request | Session ID/CSRF constantly reset | Call only when completing a new authentication |
| Calling strategy in both filter and success handler | Duplicate session processing | Pick a single invocation point |
| Placing `RegisterSessionAuthenticationStrategy` before fixation | Registry holds stale session ID | Concurrency check → rotate ID → register session |
| Using `ConcurrentSessionControlAuthenticationStrategy` without registry lifecycle | Old sessions never cleaned up and counts drift | Configure registry, session-check filter, session destroy events |
| Using an in-memory registry across multiple instances expecting global limits | Limits bypassed across nodes | Compatible distributed session store/registry |
| Assuming a pre-login CSRF token works forever | POST request after login gets 403 | Refresh token upon successful login |
| `csrf.disable()` just because frontend sends JSON | Opens CSRF attack surface when using cookies | Keep CSRF and send the token properly |
| Relying on bearer JWTs yet expecting `SessionRegistry` to count tokens | No corresponding Servlet session | Use token issuance/revocation mechanisms |
| Testing login returning 200 without testing cookies/session ID | Misses fixation and context persistence | Create session beforehand, compare IDs, and GET protected resource afterward |
| Registering custom filter as a Servlet bean AND adding to SecurityFilterChain | Filter may run twice | Register once at the intended position |
| Sending `JSESSIONID` via URL rewriting | Can leak session ID in URLs/logs/links | Prefer cookies and proper servlet policy |
| Using plain HTTP to carry login session cookies | Risk of session hijacking | End-to-end HTTPS, proper Secure/HttpOnly/SameSite cookies |

## 13. Practical Design Questions

### What if there is no session before login?

When a login POST request does not carry a valid session, `ChangeSessionIdAuthenticationStrategy` may have no old session to alter. `HttpSessionSecurityContextRepository` can create a new session to store authentication if policy allows. This is not a session fixation failure: there was no old ID for an attacker to fixate. To verify ID rotation, tests must proactively create a session before login.

### Can an app use both session form login and stateless JWTs together?

Yes. However, organize them into appropriate `SecurityFilterChain` beans by endpoint, e.g., `/web/**` using sessions and CSRF, and `/api/**` using stateless bearer tokens; verify `securityMatcher` ordering and repos/CSRF/entry points. Do not apply a stateful session strategy across bearer requests and assume token lifecycles are controlled.

### When a session expires, does SessionAuthenticationStrategy run again?

No. It normally runs **upon a new authentication event**. Requests to a protected URL with an expired session cookie are treated as unauthenticated; if re-authentication is required and succeeds, the session strategy runs during that new authentication. `InvalidSessionStrategy` and `SessionInformationExpiredStrategy` serve separate scenarios involving invalid sessions or concurrency-expired sessions.

### Does changing the session ID cause all session attributes to be lost?

`ChangeSessionIdAuthenticationStrategy` uses the `changeSessionId()` API on the same session and normally retains attributes. Other invalidate/migrate strategies have their own attribute-transfer policies. Do not rely on a "migrate everything" assumption if the application stores sensitive data in the session; decide explicitly which attributes should survive login.

### Why do concurrency limits still fail to work despite configuring the strategy?

You may be missing `RegisterSessionAuthenticationStrategy`, the active `SessionRegistry`, `ConcurrentSessionFilter`, session destroy notifications, principal equality, or a shared store across multiple instances. If using the standard DSL, verify it attaches to **the right authentication filter**; with custom filters, do not look only at the `maximumSessions(1)` line.

### Should SessionAuthenticationStrategy assign authorities itself?

No. It receives an already successful `Authentication` to decide session-related actions. Authorities must be loaded/normalized by the authentication/authorization system beforehand. Calling `onAuthentication` does not grant `ROLE_ADMIN`, verify passwords, or replace `hasAuthority`.

## 14. Pre-Production Testing Checklist

- [ ] Identify all authentication flows (form, custom login, OAuth2, SAML, remember-me, API tokens), and who calls the session strategy in each.
- [ ] Custom filter accepts only the intended path/method, constructs an unauthenticated token, and calls the right manager.
- [ ] Session strategy runs **after** credential verification succeeds and **before** the success response.
- [ ] Do not call `onAuthentication` redundantly from two different components.
- [ ] If using cookies/sessions, enable session fixation protection; create a pre-login session to test ID rotation.
- [ ] If using concurrency limits, configure the same registry, control/fixation/register order, cleanup, and expired-session handling.
- [ ] If using CSRF, share the same `CsrfTokenRepository` between filter and strategy; old tokens are refreshed per policy.
- [ ] `SecurityContextRepository` is configured to save on login and load on subsequent requests.
- [ ] On bad credentials or strategy rejection, do not save an authenticated context and do not return status 200.
- [ ] Tests distinguish 401 from bad login, 401 from unauthenticated resource access, 403 from CSRF/authorization, and session limit errors.
- [ ] Configure HTTPS, cookie flags, session TTL, logout, invalidation, trusted proxies, and safe redirects.
- [ ] For multi-instance deployments, ensure sessions/registry have a distributed strategy and refresh/invalidation support.
- [ ] For stateless JWTs, verify the token on every request and do not create HTTP sessions by default.
- [ ] Have secure metrics/logs for login success/failure, rotation, and session policy without logging secrets.

## 15. Self-Check Questions

1. Is `SessionAuthenticationStrategy` the component that checks passwords? Why or why not?
2. What did Spring Security 6 change about the default role of `SessionManagementFilter`?
3. Why must a custom login filter know **when** to call `onAuthentication`?
4. What is the difference between `SecurityContextRepository` and `ChangeSessionIdAuthenticationStrategy`?
5. Why does a session fixation test need an existing session before sending the login POST?
6. With `maximumSessions=1`, why do you need control, registration, expired-session handling, and cleanup together?
7. What happens if one strategy inside `CompositeSessionAuthenticationStrategy` throws `SessionAuthenticationException`?
8. With session cookies, why is a new CSRF token needed after successful login?
9. When can `NullAuthenticatedSessionStrategy` be an appropriate choice, and does it make the application stateless on its own?
10. How do you distinguish a credential login failure, a session limit error, and an unauthenticated request to a protected endpoint?
11. Why is a success handler returning 200 not enough to guarantee the context was persisted?
12. If an application has both web forms and JWT bearer APIs, should it use the exact same session strategy for every request?

## 16. References

1. Spring Security 6.5 — Authentication Persistence and Session Management (Spring Security 6 changes, session fixation): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
2. Spring Security 6.5 API — `SessionAuthenticationStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html
3. Spring Security 6.5 API — `CompositeSessionAuthenticationStrategy` and delegate ordering: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/CompositeSessionAuthenticationStrategy.html
4. Spring Security 6.5 API — `AbstractAuthenticationProcessingFilter` (success lifecycle, session strategy, repository): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
5. Spring Security 6.5 — Concurrent Sessions Control: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html#_concurrent_sessions
6. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
7. Spring Security 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
8. Spring Security 6.5 API — `ChangeSessionIdAuthenticationStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ChangeSessionIdAuthenticationStrategy.html
9. Spring Security 6.5 API — `CsrfAuthenticationStrategy`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfAuthenticationStrategy.html

**Principle to remember:** `SessionAuthenticationStrategy` is one step of a **new login event**, and in Spring Security 6, **the authentication mechanism must ensure it is called at the right time**. When using session cookies, wire credential verification, session management, `SecurityContext` persistence, and response handling together cleanly; do not mistake these responsibilities for a single operation.