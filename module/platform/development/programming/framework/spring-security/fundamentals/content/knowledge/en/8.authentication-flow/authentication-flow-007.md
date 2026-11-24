# Post-Authentication Success Handling and Context Persistence Responsibility

> **Core idea:** `AuthenticationManager.authenticate(...)` verifies credentials and returns an accepted `Authentication`. Yet a successful login still involves several tasks at the **web layer**: handling session fixation, placing the authentication into the current `SecurityContext`, **saving the context via `SecurityContextRepository` if later requests need to restore it**, triggering remember-me/events where applicable, and letting `AuthenticationSuccessHandler` decide the response or redirect. In Spring Security 6.x, `SecurityContextHolderFilter` **loads** the context rather than **auto-saving every mutation**. The framework's standard authentication filters handle saving by design; custom login code must understand and perform that part explicitly.

This lesson belongs to the **Authentication Flow** section of **Spring Security – fundamentals**. The primary stack is **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x, Servlet/Spring MVC**. The complete example at the end includes session-based form login and HTTP testing with MockMvc. For WebFlux, Spring Security uses `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`, and the corresponding reactive context/repository mechanisms; do not apply the Servlet `ThreadLocal` model as a universal rule.

## 1. What Should You Master After This Lesson?

1. Explain accurately that **authentication success**, **request security context**, **persistence across requests**, and **success handler** are four separate concepts.
2. Trace the form login flow: `UsernamePasswordAuthenticationFilter` -> `AuthenticationManager` -> successful `Authentication` -> `SessionAuthenticationStrategy` -> `SecurityContextHolder`/`SecurityContextRepository` -> `AuthenticationSuccessHandler`.
3. Know what `SecurityContextHolderFilter` and `SecurityContextRepository` do in Spring Security 6; distinguish this from auto-saving in Spring Security 5.
4. Compare `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository`, and `NullSecurityContextRepository`.
5. Understand why a session cookie is typically a **reference identifier**, not a serialized string of the entire `Authentication`.
6. Use `SavedRequestAwareAuthenticationSuccessHandler` to send users back to their originally requested URL; do not confuse `RequestCache` with where identity is stored.
7. Know when you must call `saveContext(context, request, response)` in custom login, and what supporting concerns must be designed (CSRF, session fixation, concurrent sessions, failure handling, logout).
8. Verify with MockMvc that after login, a subsequent request with the same session is accepted, a fresh request without a session is rejected, bad logins grant no access, logout removes access, and admin roles still apply.

## 2. A Successful Login Happens Across Multiple Layers

```text
Browser sends POST /login
  username, password, _csrf, session cookie (if present)
          |
          v
Servlet Filter Chain / Spring Security
          |
          v
UsernamePasswordAuthenticationFilter
  creates UNAUTHENTICATED UsernamePasswordAuthenticationToken
          |
          v
AuthenticationManager (usually ProviderManager)
          |
          v
AuthenticationProvider (e.g., DaoAuthenticationProvider)
  UserDetailsService + PasswordEncoder + account checks
          |
       +--+-------------------------------------+
       |                                        |
    FAILURE                                  SUCCESS
       |                                        |
       v                                        v
AuthenticationFailureHandler              Authentication result
(clear context, error response...)        trusted principal + authorities
                                               |
                                               v
                                    SessionAuthenticationStrategy
                                    (session fixation/concurrency ...)
                                               |
                                               v
                                    New SecurityContext containing result
                                               |
                           +-------------------+------------------+
                           |                                      |
                           v                                      v
                SecurityContextHolder                   SecurityContextRepository
                (current request)                       (saved if needed later)
                           |                                      |
                           +-------------------+------------------+
                                               |
                                               v
                                  Remember-me / success event
                                  (when configured/applicable)
                                               |
                                               v
                                  AuthenticationSuccessHandler
                                  (redirect, response/status, ...)
                                               |
                                               v
                                    Browser receives response
                                               |
                 GET /me + session cookie on next request
                                               |
                                               v
                                    SecurityContextHolderFilter
                                    restores context from repository
                                               |
                                               v
                                    Authorization -> Controller
```

The diagram depicts the common **Servlet form login processing path**, not an immutable filter list or ordering across every mechanism or version. The essential takeaway: the authentication provider verifies identity; standard authentication filters manage success at the HTTP boundary; the success handler handles the **post-success response**.

**Never conclude:** "Because `AuthenticationManager` returned successfully, Spring saves a session in every case." `AuthenticationManager`'s job is to return a result or throw `AuthenticationException`, **not to build responses, set cookies, redirect, or save context itself** when you call it directly from a service.

## 3. After authenticate() Succeeds, What Has and Has Not Been Done?

Example called inside a custom flow:

```java
Authentication pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

Authentication verified =
    authenticationManager.authenticate(pending);
```

This is a snippet where variables are provided by a trusted caller. If the password is valid and the provider supports it, `verified` is a result carrying the verified principal/authorities. Yet from just those two lines alone, **you cannot conclude**:

- `SecurityContextHolder.getContext().getAuthentication()` now holds `verified`.
- The browser received `JSESSIONID` or the session ID was rotated against session fixation.
- `SecurityContextRepository` wrote the context for subsequent requests to retrieve.
- `AuthenticationSuccessHandler` ran and redirected to the target page.
- A remember-me cookie was set or a login audit event was published.
- The application checked read/write permissions for individual objects belonging to which tenant.

Distinguish clearly:

| Step | Responsible component | What it produces |
| --- | --- | --- |
| Credential verification | `AuthenticationManager`/`AuthenticationProvider` | Successful `Authentication` or exception |
| Session handling right at login | `SessionAuthenticationStrategy` invoked by the authentication mechanism | May rotate session ID, check concurrent sessions |
| Identity in the current request | `SecurityContextHolderStrategy` and `SecurityContext` | Downstream filters/handlers can read the actor |
| Persisting identity for restoration | `SecurityContextRepository` | Context tied to session, request attribute, or other storage |
| Remembering the URL the user intended to open | `RequestCache` | `SavedRequest`, **not** authentication |
| Handling response on login success | `AuthenticationSuccessHandler` | Application-chosen redirect/status/headers/body |
| Remember-me if configured | `RememberMeServices` | Separate continuation login mechanism, usually via cookie |
| Authentication events | `ApplicationEventPublisher` and supporting classes | Signals for auditing/observability if handled |
| Permission checks | `AuthorizationFilter`, method/domain policy | Decision allowing/denying route/action/resource calls |

Setting an `Authentication` into `SecurityContextHolder` only makes it available within **the current execution flow**; it is not a permanent save action. Conversely, a repository may have saved the context from an earlier request, yet on the next request there must be a mechanism to **reload** it and place it into the holder.

## 4. What Does AuthenticationSuccessHandler Actually Do?

### 4.1. The interface

In Servlet:

```java
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
```

This interface receives `HttpServletRequest`, `HttpServletResponse`, and the authenticated `Authentication` to define **post-login behavior**:

```java
// Conceptual signature of the interface.
void onAuthenticationSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication authentication
) throws IOException, ServletException;
```

A handler can:

- Redirect to the URL the user originally tried to visit, such as `GET /orders` before login.
- Redirect to a default page like `/dashboard`.
- Return HTTP `200`/`204` or minimal JSON for a frontend per the designed login protocol.
- Record an audit event **containing no passwords/tokens** or update user login timestamps in a way that does not break transactions.
- Enforce same-origin/allowlist redirect policies rather than trusting a client-controlled external `returnUrl`.

It **does not have a default contract to "put authentication into HttpSession"**. In the standard `AbstractAuthenticationProcessingFilter`/form login flow, the filter already handles creating/setting/saving the context before invoking the success handler per the current framework mechanism. When you write a custom login controller, there is no guarantee that calling a success handler manually will save the context for you.

### 4.2. SavedRequestAwareAuthenticationSuccessHandler

A common scenario:

```text
1. Anonymous: GET /reports/quarter
2. ExceptionTranslationFilter: requires login
3. RequestCache: saves original URL (SavedRequest) if policy permits
4. Browser -> /login
5. POST /login: valid credentials
6. SavedRequestAwareAuthenticationSuccessHandler:
   redirects to /reports/quarter (if saved request is valid)
7. Browser sends GET /reports/quarter with new session
8. Repository loads context; route undergoes normal authorization checks
```

`SavedRequestAwareAuthenticationSuccessHandler` normally prioritizes the request saved by `RequestCache`, if present and valid; otherwise it uses the configured default target URL. You can force a fixed target with `setAlwaysUseDefaultTargetUrl(true)`, though that disables returning to the original page.

**Distinguish clearly:** `RequestCache` stores **the request to replay**. `SecurityContextRepository` stores **the identity context**. The session may hold both pieces of data, yet their purpose and timing differ. If you disable request cache, login can still create a session/authenticated context; you simply lose returning to the pre-login URL.

### 4.3. Example delegating success handler without leaking data

```java
@Bean
AuthenticationSuccessHandler loginSuccessHandler() {
    SavedRequestAwareAuthenticationSuccessHandler delegate =
        new SavedRequestAwareAuthenticationSuccessHandler();
    delegate.setDefaultTargetUrl("/me");

    return (request, response, authentication) -> {
        // Header just for testing that the callback ran; contains no user/secret.
        response.addHeader("X-Lab-Login-Processed", "1");

        // Keep safe redirect behavior from the framework.
        delegate.onAuthenticationSuccess(request, response, authentication);
    };
}
```

This is a complete bean method when placed inside a `@Configuration` class with appropriate imports; a full application example appears in the practical section. The `X-Lab-Login-Processed` header is a learning signal, not a Spring Security requirement or a header to deploy in production. In real apps, auditing should log a stable user ID and success timestamp, limit sensitive data, prevent log injection, and ensure audit logging never exposes passwords/tokens.

### 4.4. Successful login does not have to return 200

Form login typically returns HTTP **302** to the target page. The subsequent GET after redirect returns **200** when handled successfully. For SPAs/APIs you can design a 200 or 204 response, provided the session cookie/CSRF/token contract is defined clearly. Never treat 302 as a failed login; inspect `Location` and the next request.

## 5. SecurityContextHolder, SecurityContext, and SecurityContextRepository

### 5.1. Current context

`SecurityContextHolder` provides the API to get/set the active `SecurityContext`:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication auth = context.getAuthentication();
```

In Servlet, the default strategy is typically `ThreadLocal`; the filter chain manages the context lifecycle per request. Never store `Authentication` in a mutable field of a singleton service or a global static variable. When a servlet worker thread is reused for another request, Spring Security clears the holder along the standard path so Alice's identity does not leak into Bob's request.

### 5.2. Repository is how context is restored

`SecurityContextRepository` is the contract for loading/saving context across requests/responses. Important methods include:

```java
SecurityContext context =
    securityContextRepository.loadContext(
        new HttpRequestResponseHolder(request, response));

securityContextRepository.saveContext(context, request, response);
```

This snippet illustrates the API; Spring Security 6 has a deferred loading mechanism `loadDeferredContext(...)`, usually used by `SecurityContextHolderFilter`. Application code should not call `loadContext(...)` arbitrarily inside a controller just to find the current user; reading from `SecurityContextHolder` or framework injection is clearer and safer.

### 5.3. Common repositories

| Implementation | Where does it store? | Survives across new requests? | When useful |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Security context attribute inside HTTP session | **Yes**, if session is valid and client sends session ID | Form login/session-based apps |
| `RequestAttributeSecurityContextRepository` | Attribute on the Servlet request | **No** across new HTTP requests; can persist across dispatches in the same request | Preserving context across ERROR/FORWARD dispatches as needed |
| `DelegatingSecurityContextRepository` | Combines multiple repositories; default usually includes the two above | Per whichever delegate actually saves | Spring Security 6 Servlet default |
| `NullSecurityContextRepository` | Does not save | **No** | Stateless APIs re-authenticated on every request |
| Custom repository | Cache/DB/storage per custom contract | Depends on design | Specialized infrastructure, managed audit/lifecycle/clustering |

In Spring Security 6, the default repository is usually `DelegatingSecurityContextRepository` combining `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`. A context can be stored in request attributes so error dispatches can still access it, and in the HTTP session so a **subsequent request** restores the identity.

### 5.4. Does the JSESSIONID cookie contain the username and roles?

Normally **no**. The browser holds a session identifier cookie (usually `JSESSIONID`); the server or session storage system maps the session ID to session data, which may contain `SPRING_SECURITY_CONTEXT`. Do not serialize the entire `Authentication` object into a cookie just because you see the browser stay logged in. Even so, the session ID value is a **sensitive credential** because anyone possessing it can hijack the session if protections are absent.

```text
Browser:
  Cookie: JSESSIONID=<session id, actual value not shown>
       |
       v
Server session storage:
  session ID -> SecurityContext(Authentication: alice, ROLE_USER)
       |
       v
SecurityContextRepository.load... -> SecurityContextHolder -> Controller
```

In practice, cookie names and session storage can vary (Spring Session, custom session stores). Do not assume every authentication mechanism relies on server sessions: APIs using Bearer JWTs or stateless HTTP Basic can create a fresh authentication on each request without sessions.

## 6. "Explicit Save" in Spring Security 6: The Most Easily Confused Point

### 6.1. How do Spring Security 5 and 6 differ?

According to Spring Security documentation:

- Previously, `SecurityContextPersistenceFilter` typically loaded the context at the start of a request and had an auto-detection/auto-save mechanism when the request/response completed.
- In **Spring Security 6**, the default is `SecurityContextHolderFilter`: it **loads** the context from `SecurityContextRepository`, makes it available during request processing, and cleans up per lifecycle. It **does not automatically detect and write every modification** back to the session.
- Consequently, when a **custom controller or custom filter** authenticates manually and wants login to survive across requests, the code must **call `SecurityContextRepository.saveContext(...)`** deliberately.
- **Built-in** authentication mechanisms like form login are designed to manage the appropriate save step. You do not need to rewrite session-saving logic just to use standard `formLogin()`.

The transitional configuration `requireExplicitSave(false)` may be seen in legacy systems during migration, yet that is a compatibility option; for new projects, understand and use the modern default rather than relying on implicit auto-saving.

### 6.2. Common mistake: only setting into the holder

```java
Authentication verified = authenticationManager.authenticate(pending);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// MISSING if you want to persist login across subsequent requests:
// securityContextRepository.saveContext(context, request, response);
```

Within the current request, downstream code may see Alice. Once the response completes and a new request arrives, the repository has no saved context, so `GET /me` is treated as unauthenticated again. The symptom can look like the browser "logged in successfully and immediately bounced back to login".

**Remember precisely:** `setContext(...)` operates on the **current holder**; `saveContext(...)` operates on the **persistence strategy**. The two are not interchangeable.

### 6.3. Responsible manual save procedure

The snippet below is only a **technical skeleton** for a fully designed custom login handler; it is **not a standalone production endpoint**:

```java
// Input variables are injected/provided by a trusted mechanism:
// AuthenticationManager authenticationManager;
// SecurityContextHolderStrategy holderStrategy;
// SecurityContextRepository repository;
// SessionAuthenticationStrategy sessionStrategy;
// HttpServletRequest request; HttpServletResponse response;
// String username; String password;

Authentication pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

Authentication verified = authenticationManager.authenticate(pending);

// If session-based login applies, custom mechanism must call appropriate strategy
// for session fixation/concurrency before completing login.
sessionStrategy.onAuthentication(verified, request, response);

SecurityContext context = holderStrategy.createEmptyContext();
context.setAuthentication(verified);
holderStrategy.setContext(context);

// SAVE BEFORE the response is committed (before redirect/body).
repository.saveContext(context, request, response);

// Only then execute the success response/redirect per design.
```

**Never copy this skeleton into a homegrown login API** without integrating CSRF, exception/failure handlers, a genuinely correct session authentication strategy, authentication events, rate limiting, logout/remember-me, response management, and cleanup. Spring Security's built-in mechanisms handle many subtle edge cases; whenever possible, configure `formLogin`/OAuth2/OIDC rather than rebuilding everything from scratch.

### 6.4. Why save before returning a redirect or body?

Once the Servlet response has been **committed**, the server may no longer be able to add `Set-Cookie` for a new session, rotate the session ID, or persist the context via mechanisms needing a response wrapper. If custom login calls `saveContext` **after** writing the response/redirect, the next request may fail to find the right session. The implementation rule is: complete authentication + session strategy + context setup + persistence **before** committing the response.

### 6.5. Creating a new SecurityContext instead of mutating a shared context

In custom authentication flows, prefer:

```java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verified);
SecurityContextHolder.setContext(fresh);
```

Creating a new instance avoids accidentally mutating a context reference that might be shared across a session, another concurrent part of the system, or a different lifecycle. In standard successful authentication, Spring Security's filter performs equivalent steps; this snippet serves to clarify responsibilities.

## 7. When Does SessionAuthenticationStrategy Happen?

`SessionAuthenticationStrategy` handles concerns **right when a principal has just been authenticated**, such as changing the session ID against session fixation or limiting concurrent sessions. In Spring Security 6, the authentication mechanism itself is expected to invoke the appropriate strategy; do not expect `SessionManagementFilter` to detect and run it automatically by default.

### 7.1. Session fixation protection

If an attacker can force a victim to use a known session ID before login, the attacker can hijack the session once the victim logs in. Spring Security Servlet normally rotates the session ID upon login on containers supporting `HttpServletRequest.changeSessionId()`, cutting off reuse of the pre-authentication session ID.

```text
Before login: session ID = S1 (guest)
Valid login:  authenticate Alice + session strategy rotates ID
After login:  session ID = S2 (authenticated)
              S1 must not become a ticket into Alice's session
```

Session fixation protection does not replace credential verification; it protects the **session lifecycle** after authentication succeeds. In a custom login controller, calling the manager + saving context while forgetting the strategy can leave the system missing this protection. Do not disable session fixation protection just because a test observes the session ID changing.

### 7.2. Concurrent session control

An application may cap how many active sessions a user can hold (for instance one session), invalidating older sessions or rejecting new logins. This requires `SessionRegistry` and matching session lifecycle events/strategies; this design sits **outside AuthenticationManager itself**. Depending on `maximumSessions`/`maxSessionsPreventsLogin`, a login with a valid password can still be rejected by session policy. When writing a custom authentication filter, invoke the right strategy and handle `SessionAuthenticationException` properly.

### 7.3. Session policies IF_REQUIRED, NEVER, STATELESS

| Policy | Main operational meaning |
| --- | --- |
| `SessionCreationPolicy.IF_REQUIRED` | Spring Security may create a session when genuinely needed; usually fits form login |
| `SessionCreationPolicy.ALWAYS` | Proactively creates a session per configuration |
| `SessionCreationPolicy.NEVER` | Security does not create a session for context itself, yet may use an existing one; other components may create sessions |
| `SessionCreationPolicy.STATELESS` | Security neither creates nor uses sessions to restore SecurityContext; fits per-request credential APIs |

With `STATELESS`, Spring Security typically configures `NullSecurityContextRepository` for restoration/preventing session context saves, while avoiding storing requests in session. Therefore, **never** expect that simply setting `http.sessionManagement(...STATELESS)` lets form login keep users logged in across requests like a session-based app.

## 8. How Do RequestCache, RememberMe, and SecurityContextRepository Differ?

All three mechanisms can participate in the "stay logged in while using the app" experience, yet their purposes differ:

- **RequestCache** stores the URL/request the user tried to visit before being intercepted; the success handler can redirect so the client re-sends that request. It does not grant permissions or store principals.
- **SecurityContextRepository** saves/restores the context containing `Authentication` per policy (request attribute/session/none). This answers "how does the next request know who logged in?".
- **RememberMeServices** is a re-authentication/continuation mechanism via a remember-me cookie or token as configured. When a session expires, a valid remember-me token can re-authenticate at a different trust level; it does not keep `SecurityContextHolder` alive forever.

A `remember-me authenticated` state may not satisfy `fullyAuthenticated()`. For sensitive actions like changing passwords, transferring funds, or modifying MFA, step-up/re-authentication and stricter policies may be required. `getAuthentication().isAuthenticated()` alone is insufficient in many cases, especially since an anonymous authentication token can return true.

## 9. Runnable Demo: Spring Boot Form Login + Success Handler + Session Repository

This demo uses **Java 17**, **Spring Boot 3.5.16**, and **Spring Security 6.5.x** managed by Boot. This is the final OSS-supported release of the Boot 3.5 line (released in 2026); when creating new production projects, choose an actively supported Boot line and current patches, and review the corresponding migration guides.

The application intentionally uses **form login and HttpSession** because the main topic is persisting context across multiple requests. If you only build stateless Basic/Bearer APIs, apply per-request re-authentication as shown later. Example accounts and passwords are for local environments only.

### 9.1. File structure

```text
login-persistence-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/session/LoginPersistenceApplication.java
    └── test/
        └── java/demo/session/LoginPersistenceApplicationTests.java
```

### 9.2. pom.xml

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
    <artifactId>login-persistence-demo</artifactId>
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

### 9.3. Complete application

Create `src/main/java/demo/session/LoginPersistenceApplication.java`:

```java
package demo.session;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginPersistenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginPersistenceApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class LoginSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    // Spring Security 6 normally has an equivalent default repository.
    // Declared here to clearly see the role of both delegates.
    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    AuthenticationSuccessHandler loginSuccessHandler() {
        SavedRequestAwareAuthenticationSuccessHandler redirect =
            new SavedRequestAwareAuthenticationSuccessHandler();
        redirect.setDefaultTargetUrl("/me");

        return (request, response, authentication) -> {
            // Header illustrating callback, does not echo secrets or roles.
            response.addHeader("X-Lab-Login-Processed", "1");
            redirect.onAuthenticationSuccess(
                request, response, authentication);
        };
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http,
            SecurityContextRepository repository,
            AuthenticationSuccessHandler loginSuccessHandler)
            throws Exception {

        return http
            .securityContext(securityContext ->
                securityContext.securityContextRepository(repository))
            .authorizeHttpRequests(authorize -> authorize
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .formLogin(form -> form
                .successHandler(loginSuccessHandler)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .build();
    }
}

@RestController
class DemoRoutes {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }
}
```

**Why are these lines in the demo important?**

1. `securityContextRepository()` creates a `DelegatingSecurityContextRepository` with request-attribute and HTTP-session delegates, clearly showing both **restoration across request/error dispatches** and **restoration on subsequent HTTP requests**.
2. `.securityContext(...securityContextRepository(repository))` wires the repository into the security chain and relevant authentication filters per Spring Security 6 configuration.
3. `IF_REQUIRED` allows sessions when login requires them. `sessionFixation(changeSessionId())` protects upgrading an anonymous session to an authenticated one.
4. `formLogin(...successHandler(...).permitAll())` enables standard form login processing. Spring Security's filter handles authentication + context setup/persistence; the handler merely adds an illustrative header and delegates to `SavedRequestAwareAuthenticationSuccessHandler` to redirect.
5. `redirect.setDefaultTargetUrl("/me")` picks `/me` when there is no saved request; if the user previously requested a protected URL and the request cache saved it, the handler can return to the original URL.
6. `GET /public` is open, `GET /me` requires login, `GET /admin` requires ROLE_ADMIN. All other routes hit `denyAll`, never opening merely because a session exists.
7. `.logout(...)` uses built-in logout support, where Spring Security handles invalidation/clearing context. When CSRF is enabled, POST logout requires a valid token.
8. In-memory users and sample passwords are for learning only; **never commit production passwords** to source. HTTP form login must run over **HTTPS** on real networks.

### 9.4. Integration test suite: proving context is saved across requests

Create `src/test/java/demo/session/LoginPersistenceApplicationTests.java`:

```java
package demo.session;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistenceApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void formLoginSavesContextAndNextRequestRestoresIt() throws Exception {
        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andExpect(header().string(
                "X-Lab-Login-Processed", "1"))
            .andReturn();

        MockHttpSession resultingSession =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(resultingSession);

        // This is SERVER-SIDE SESSION data, not a cookie holding the user.
        Object saved = resultingSession.getAttribute(
            HttpSessionSecurityContextRepository
                .SPRING_SECURITY_CONTEXT_KEY);

        SecurityContext context =
            assertInstanceOf(SecurityContext.class, saved);

        assertNotNull(context.getAuthentication());
        assertEquals("alice", context.getAuthentication().getName());

        // MockMvc does not carry session automatically across independent requests;
        // we pass the exact session to simulate the browser sending cookies.
        mvc.perform(get("/me").session(resultingSession))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        // Request without a pre-authenticated session is redirected to login.
        mvc.perform(get("/me").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void invalidPasswordNeverCreatesAuthenticatedSession()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

        mvc.perform(get("/me")
                .session(session)
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void adminAuthorizationStillAppliesAfterSessionRestored()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());

        MockHttpSession adminSession = new MockHttpSession();

        mvc.perform(post("/login")
                .session(adminSession)
                .with(csrf())
                .param("username", "admin")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/admin").session(adminSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));
    }

    @Test
    void logoutInvalidatesSessionAndRemovesAuthentication()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // New request has no logged-in session.
        mvc.perform(get("/me").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

**What the tests prove:**

- Login uses **real username/password through `UsernamePasswordAuthenticationFilter`** and `DaoAuthenticationProvider` set up by Spring Security from `UserDetailsService`; unlike `@WithMockUser` which only constructs a mock principal.
- The session is retrieved after login and verified to contain `SPRING_SECURITY_CONTEXT` storing Alice's `Authentication`. This proves **persistence** rather than just "the login request got 302".
- The next request carrying the **same session** reads Alice; a request without a session is sent to login. MockMvc passes `MockHttpSession` between calls to simulate a browser holding the session cookie.
- Custom `AuthenticationSuccessHandler` ran because the login response has `X-Lab-Login-Processed: 1`, yet verifying the handler ran **does not substitute** for testing context persistence.
- Wrong password issues no authenticated session; ROLE_ADMIN still governs requests after the context is restored.
- Logout uses built-in filter support, invalidates the session, and prevents another request from reusing the old session. In real browser clients, also verify cookie/session behavior over HTTP/TLS.
- Tests assert stable statuses/headers/bodies rather than asserting the entire filter list or log contents; expected outcomes also depend on having compatible dependencies/JDK/Maven installed.

### 9.5. Running the demo

In the directory containing `pom.xml`, requiring JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

When run properly, the tests above are expected to pass. This lesson presents code and assertions for learning; do not treat expected outcomes as proof that Maven ran in the current environment.

In a browser, open an incognito window and visit:

```text
http://localhost:8080/public
http://localhost:8080/me
http://localhost:8080/admin
http://localhost:8080/login
```

- `/public` returns `public` without requiring login.
- `/me` redirects to the login form when an anonymous visitor requests HTML.
- Log in with username `alice`, password `demo-pass`; after login, `/me` returns `me:alice`.
- Log in as `admin` in another session to test `/admin` returning `admin-ok`. Alice lacks ROLE_ADMIN so she is denied.
- Use DevTools -> Network to inspect `POST /login` returning a redirect, possibly with `Set-Cookie` for the session; subsequent requests carry the cookie and return content. Never share screenshots/logs containing session cookies.

With curl, **form login is not equivalent to HTTP Basic**. Sending `POST /login` via curl requires extracting/sending the CSRF token and cookie jar from the form/session; using a browser and MockMvc for accurate practice is simpler in this lesson. If you only try:

```bash
curl -i -H "Accept: text/html" http://localhost:8080/me
```

you typically observe a `302` redirect to `/login` without a cookie. Never run `curl -L` and look only at the final HTTP status of the login page (200) to conclude `/me` is public.

**Production:** run HTTPS, set appropriate Secure/HttpOnly/SameSite cookie flags, avoid putting tokens/passwords/session IDs in URLs or logs, and do not use sample accounts.

## 10. What Is Browser Evidence of Persistence?

Observe two independent sessions:

### Before login

```text
GET /me                         -> 302 Location: /login
GET /login                      -> 200 form page
Form includes CSRF token per active mechanism
```

### On successful login

```text
POST /login + valid credentials + CSRF token
  -> authentication provider returns result
  -> session strategy handles session
  -> context is attached + saved
  -> success handler redirects to /me or SavedRequest
Browser follows up with GET /me + current session Cookie
  -> repository loads context
  -> AuthorizationFilter allows through
  -> controller returns "me:alice"
```

### When opening a new incognito window

```text
GET /me, without sending the old session cookie
  -> cannot restore Alice's Authentication
  -> prompted to log in again
```

This differs from **Browser Refresh** within the same logged-in session: the browser automatically sends the cookie so the user remains authenticated. When checking DevTools, never print secret cookies in reports; noting whether the cookie is present/absent suffices. Protect session IDs against fixation and theft, and rotate/invalidate per policy.

## 11. Stateless: Why Not Save Context into a Session?

An API using HTTP Basic or Bearer tokens usually authenticates **on every request**. For example:

```text
GET /api/me
Authorization: Bearer <valid token>
      |
      v
BearerTokenAuthenticationFilter
      |
      v
JwtDecoder / AuthenticationManager / trust validation
      |
      v
Authentication in SecurityContext for this request
      |
      v
Controller reads principal
      |
      v
Request ends; holder is cleared
```

The next request must present valid credentials again. In Spring Security Servlet:

```java
// Snippet of SecurityFilterChain builder for a stateless API.
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

That configuration can lead to `NullSecurityContextRepository` by default in order to avoid sessions. **Do not** force this flow to store full tokens/authentications into a server session when the threat model and API architecture chose stateless. If you deliberately need session persistence for a normally stateless mechanism, configure the repository on the authentication filter itself and verify the behavior rather than assuming it happens automatically.

For a JWT Resource Server, before concluding "login succeeded", you must also validate signature/algorithm, issuer/audience, expiry, and map authorities properly. Form login's success handler **does not run automatically** after each Bearer token request; the filters have different lifecycles. Do not copy handlers/session strategies from form login to JWT without reason.

## 12. Logout: Clearing Context Is Just as Important as Saving It

If context was saved in a session, "logging out" must ensure the session no longer grants access. In Spring Security, `LogoutFilter` and `SecurityContextLogoutHandler` typically help:

- Invalidate the HTTP session per configuration.
- Clear authentication from `SecurityContextHolderStrategy`.
- Clear the context in `SecurityContextRepository`.
- Clean up remember-me/CSRF tokens and publish logout events if configured.
- Then run `LogoutSuccessHandler` or redirect to the logout success URL.

With CSRF protection enabled, `POST /logout` usually requires a CSRF token; `GET /logout` may show a confirmation page. Never assume a bare GET is always a completed logout action.

**Dangerous custom logout bug:**

```java
// Clearing only the holder on the current request is NOT ENOUGH if the session holds a context.
SecurityContextHolder.clearContext();
response.sendRedirect("/login");
```

If the session still holds the authentication, the next request can reload the context and the user remains logged in. Use built-in logout support or execute complete invalidation/repository clearing/remember-me cleanup with the proper lifecycle before committing the response.

Note for SSO/OIDC: "logging out of the local application" and "logging out of the Identity Provider" are two potentially separate operations; when logout involves the IdP, follow the corresponding protocol, state, and redirect policies.

## 13. Common Implementation Mistakes

### 13.1. SuccessHandler returns JSON/redirect before saving context

**Symptom:** POST /login returns success, yet the next request gets 401 or bounces back to /login.

**Cause:** custom controller/login filter did not call repository `saveContext`, or called it too late after the response was committed.

**Fix:** use built-in authentication filters when possible; if custom, complete session strategy + holder + `saveContext` **before** the response, and test with a second request carrying the same cookie/session.

### 13.2. Thinking AuthenticationManager logs the browser in automatically

**Symptom:** A test service calling `authenticate()` gets an authenticated result; the browser still has no session.

**Cause:** the manager only verifies credentials. No filter/controller attached and saved the result in security context for future requests to find.

**Fix:** use standard form login/OIDC or a fully designed custom flow. Test both authentication and persistence/redirects.

### 13.3. Only calling setContext, not saveContext

**Symptom:** Within POST /login you can read the username, yet after redirect the new request loses the identity.

**Cause:** Spring Security 6's default `SecurityContextHolderFilter` does not auto-save modifications.

**Fix:** use a repository capable of saving and call `saveContext(context, request, response)` for custom logins; verify the filter's repository and custom code's repository **are the same compatible mechanism**.

### 13.4. Thinking RequestCache is SecurityContextRepository

**Symptom:** After login it redirects to the right old URL yet still prompts to log in, or login persists yet never returns to the old page.

**Cause:** The two mechanisms are controlled independently. RequestCache only remembers URLs; the repository keeps identity across requests.

**Fix:** test saved URLs separately and test authenticated sessions separately; check session cookies, redirect URLs, and authorization.

### 13.5. Configuring STATELESS for a web app needing sessions

**Symptom:** Form login succeeds on POST yet every subsequent GET remains anonymous.

**Cause:** App uses `SessionCreationPolicy.STATELESS`/`NullSecurityContextRepository`, so context is not persisted across HTTP sessions.

**Fix:** pick the right policy: session login uses IF_REQUIRED/session repo; Bearer APIs use stateless and per-request tokens. If two zones exist, use separate chains with controlled matchers/fallbacks.

### 13.6. Forgetting session fixation protection in custom login

**Symptom:** Session ID does not change when upgrading from anonymous to authenticated, exposing the session to someone holding the old ID.

**Cause:** Skipping `SessionAuthenticationStrategy` or disabling protection.

**Fix:** let the framework handle it or invoke the right strategy; test ID rotation and handle session expiry/concurrent sessions as required.

### 13.7. Relying solely on a success redirect to assume the user has permission

**Symptom:** Alice logs in and then accesses Bob's report because the backend only checked authenticated.

**Cause:** Login success and object authorization are distinct. SuccessHandler does not verify owner/tenant/resource.

**Fix:** service/repository enforces actor + action + resource + tenant/state policies. Test user A accessing resource B even with A's valid session.

### 13.8. Leaking data via logs inside a success handler

**Symptom:** Logs store entire `Authentication`, passwords, refresh tokens, cookies, or sensitive claims.

**Cause:** Uncontrolled `toString()` or logging full headers/forms while debugging.

**Fix:** log minimal stable user ID, timestamp, correlation ID, and outcome; mask secrets, restrict audit access, and limit retention. Never put session IDs in URLs.

### 13.9. Redirecting straight to a client-supplied returnUrl

**Symptom:** After login, the server redirects to an external domain specified by an attacker.

**Cause:** `AuthenticationSuccessHandler` reads `returnUrl` from query/cookie without restricting origin/path.

**Fix:** use `SavedRequestAwareAuthenticationSuccessHandler` or allowlist/same-origin validation on target URLs; prevent open redirects/phishing.

### 13.10. Using @WithMockUser to conclude real session login works

**Symptom:** MockMvc tests return 200 with a mock user, yet real POST /login fails to save a session.

**Cause:** `@WithMockUser` creates a simulated authentication **before the request**; it does not verify passwords or run through the login success handler.

**Fix:** write a **POST /login + CSRF + credentials** test and then use the returned session in a **subsequent GET**, testing failure/logout too.

### 13.11. Using @Async/ThreadLocal and expecting context to propagate automatically

**Symptom:** SuccessHandler running inside the request sees the user, yet a background async task sees none or the wrong user.

**Cause:** Servlet `SecurityContextHolder` defaults to ThreadLocal; thread pools do not safely inherit it automatically.

**Fix:** use appropriate `DelegatingSecurityContextExecutor` wrappers or pass the verified actor ID to the task. For delayed jobs, re-check permissions/expiry and never retain raw credentials.

### 13.12. Forgetting to clear the repository on logout

**Symptom:** User logs out, gets redirected to /login, yet refreshing an old page still grants access.

**Cause:** Only ThreadLocal was cleared; the session still holds the authenticated context.

**Fix:** use Spring Security's logout handler, invalidate the session, and clear repository/remember-me per configuration. Test a follow-up request after logout.

## 14. Recommended Test Matrix When Shipping Login to Production

| Scenario | What to verify | Tooling |
| --- | --- | --- |
| Anonymous hits private route | 302 to login or 401 depending on client/entry point | Browser + MockMvc |
| Valid username/password and CSRF | Login succeeds; handler executes | MockMvc POST /login |
| After login, request with **same session** | Context restored; GET /me returns 200 | MockMvc 2 requests |
| Fresh request **without session** | Does not inherit previous user's identity | MockMvc/integration suite |
| Wrong password | Failure handler, no authenticated context | MockMvc |
| Valid login user, wrong role | 403; login does not replace authorization | MockMvc |
| Session fixation | Session ID rotated on login per policy | MockMvc/browser integration |
| SavedRequest recorded | Redirects to original valid URL | Browser + MockMvc |
| No SavedRequest | Redirects to default target URL | MockMvc |
| POST /logout with valid CSRF | Session invalidated, context cleared | MockMvc |
| POST /logout missing CSRF | Does not log out per CSRF policy | MockMvc |
| Session expired/invalid | Prompted to log in / configured response | Integration test |
| Concurrent logins | Limit or strategy enforced | Multi-session tests |
| Secure/HttpOnly/SameSite cookies | Cookie flags under real HTTPS | Browser/HTTP integration |
| Login behind reverse proxy | Accurate redirect scheme/host | Staging |
| User/role info updated in DB | Cached session permissions updated/revoked per policy | Domain/security tests |

With MFA/step-up authentication, initial login success **does not necessarily** complete a high-privilege login. Represent the challenge state without granting sensitive authorities until the MFA step is verified; once completed, update authentication/session properly avoiding fixation/privilege escalation.

## 15. Self-Check Questions

**Question 1.** Calling `authenticationManager.authenticate(...)` returned a valid token. Why does GET /me on the next request still redirect to login?

**Answer:** The manager only returns a verified authentication. The custom flow may have omitted putting the result into context or calling `SecurityContextRepository.saveContext(...)` before the response. Test both login and the follow-up request.

**Question 2.** Is `AuthenticationSuccessHandler` the component responsible for saving the entire SecurityContext into session?

**Answer:** That is not its primary contract. The handler decides the post-login response/redirect. Standard authentication filters manage context/persistence per configuration; custom controllers must integrate the repository and needed strategies themselves.

**Question 3.** Does Spring Security 6's `SecurityContextHolderFilter` automatically save every `setContext(...)` call?

**Answer:** No. It loads the context and manages the current context scope; persisting changes across requests in custom flows requires calling repository `saveContext(...)`. Standard authentication filters handle this appropriately.

**Question 4.** `RequestCache` saved `/admin` before login. Does that mean the user is automatically granted ROLE_ADMIN after login?

**Answer:** No. Saved requests only handle redirects. Authorization on the follow-up request still checks roles and resources. A user lacking the role may be redirected to that URL and still get 403.

**Question 5.** When using `SessionCreationPolicy.STATELESS`, does keeping a session cookie from earlier make Spring Security restore Alice?

**Answer:** Not under standard stateless policy: sessions are not used to load context. Requests need their own credentials (such as a bearer token) per the configured authentication mechanism.

**Question 6.** Why does the session ID normally change upon successful login?

**Answer:** Protection against session fixation: someone knowing a pre-login session ID must not keep using that ID as an authenticated session. `SessionAuthenticationStrategy` coordinates this.

**Question 7.** After logout, is calling only `SecurityContextHolder.clearContext()` and redirecting enough?

**Answer:** Not if the repository/session still holds the authenticated context. You must clear/invalidate the repository/session and handle remember-me via the proper logout mechanism.

**Question 8.** Does a MockMvc test with `@WithMockUser` returning 200 prove form login saves sessions?

**Answer:** No. That test injects a fake principal, bypassing POST /login and success/persistence. You need sequential tests: valid POST login followed by a private GET using the same session.

## 16. Implementation Checklist for PR Reviews

- [ ] Is login form, Basic, Bearer, OIDC, or custom? Does it use the right filter/manager/provider for that mechanism?
- [ ] Are credentials/claims verified by a trusted source, never taking roles from the client?
- [ ] After success, is there an appropriate `SessionAuthenticationStrategy` for session fixation/concurrency if using sessions?
- [ ] Is `SecurityContextHolderStrategy` set for the current request and cleared per lifecycle?
- [ ] For custom logins needing persistence, is `SecurityContextRepository.saveContext` called **before the response commits**?
- [ ] Do the filter chain's repository and custom code's repository share the same semantics, avoiding saving in one place and reading from another?
- [ ] Are `RequestCache` and `AuthenticationSuccessHandler` cleanly separated from authentication persistence?
- [ ] Do redirects only target allowed URLs, avoiding open redirects via `returnUrl`?
- [ ] Do browsers needing sessions use IF_REQUIRED/HttpSession repository, while stateless APIs use per-request tokens?
- [ ] Do session cookies have sensible Secure/HttpOnly/SameSite flags, HTTPS, expiry, and rotation?
- [ ] Do failed logins create no authenticated context and avoid leaking username existence?
- [ ] Does logout invalidate the session/clear repository/clean remember-me, with proper CSRF policy on POST logout?
- [ ] Do real HTTP tests through the security chain cover 2 requests sharing a session, 1 request without a session, failures, roles, and logout?
- [ ] Are secrets kept out of responses, logs, traces, URLs, and shared test fixtures?
- [ ] Do domain services still verify owner/tenant/ACL when handling data, rather than stopping at login success?

## 17. Key Takeaways

1. **AuthenticationManager returns an authentication result**; it does not create sessions, redirects, or save context into the holder when called directly.
2. **AuthenticationSuccessHandler controls the success response**, and can use `SavedRequestAwareAuthenticationSuccessHandler` to return to the original URL.
3. **SecurityContextHolder is the current context; SecurityContextRepository is the cross-request save/restore mechanism.** `RequestCache` stores URLs/requests, not identities.
4. **Spring Security 6 favors explicit save.** `SecurityContextHolderFilter` does not auto-save every modification; built-in filters handle persistence accordingly, while custom logins need explicit `saveContext`.
5. **SessionAuthenticationStrategy handles post-login session policies** like session fixation/concurrent sessions; custom flows must account for it.
6. **Session-based and stateless flows have different lifecycles.** Form login usually maintains context via HttpSession; stateless HTTP Basic/Bearer re-authenticates on each request.
7. **Logout must also remove saved context**, not just clear the current holder; resource-level authorization is still needed after every session restoration.

## Official Documentation

- [Spring Security 6.5 — Form Login, authentication success flow](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence Migration / Explicit Save](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security 6.5 — Logout Lifecycle](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5.16 release, June 25, 2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
