# RequestAttributeSecurityContextRepository and HttpSessionSecurityContextRepository in Spring Security Servlet

In Spring Security for **Servlet/Spring MVC**, a request may already be authenticated, yet the crucial follow-up question is: **where is the `SecurityContext` holding that authentication kept, and can the next request retrieve it?** Two `SecurityContextRepository` implementations answer this at two different scopes:

- `RequestAttributeSecurityContextRepository`: holds `SecurityContext` in an **attribute of the HTTP request itself**, useful when a request undergoes multiple dispatches such as `ERROR`.
- `HttpSessionSecurityContextRepository`: stores `SecurityContext` in the **HTTP session**, allowing subsequent requests in the **same session** to recover the context when session handling is active.

This lesson covers **security context lifecycle and load/store mechanics** in the Servlet stack. Most examples correspond to Spring Security 6.x / Spring Boot 3.x and Java 17+. For other versions, consult the API documentation for your exact version; pay special attention to **explicit save** behavior changes across generations.

## 1. Three Easily Confused Objects: Authentication, SecurityContext, and Repository

**`Authentication`** represents the identity and verification state: principal, credentials (if still present), authorities, and authenticated flag. After successful authentication, the framework typically places this object into a `SecurityContext`.

**`SecurityContext`** is the container for `Authentication`. An empty context can return `null` from `getAuthentication()`; therefore, **having a `SecurityContext` does not mean a user is logged in**.

**`SecurityContextHolder`** lets current code access the context attached to the execution. On the Servlet stack, the common strategy is thread-based, while web security filters are also responsible for establishing and clearing the holder per request lifecycle. The holder **is not durable storage between two HTTP requests**.

**`SecurityContextRepository`** is responsible for **loading and saving** the context across appropriate boundaries. It is an interface; choosing an implementation determines whether the context is saved in a request attribute, an HTTP session, or not saved at all.

```text
Request begins
    |
SecurityContextHolderFilter
    |-- asks SecurityContextRepository: loadDeferredContext(request)
    |-- installs context lookup mechanism into SecurityContextHolder
    |
Authentication / authorization filters, controllers, services
    |-- read SecurityContextHolder / Authentication as needed
    |-- after authentication, may replace SecurityContext
    |
If persistence is needed: SecurityContextRepository.saveContext(context, request, response)
    |
Request ends: web filter clears SecurityContextHolder
    |
New request: old context exists only if the matching repository saved it
and the new request mechanism has enough info to reload it.
```

In Spring Security 6 with `SecurityContextHolderFilter`, **saving the context is an explicit operation**. Standard authentication filters such as form login handle saving automatically upon successful authentication. If you build a custom login flow with a controller or custom filter, you must understand calling `saveContext`; assigning to the holder alone does not guarantee the context survives after the request.

## 2. RequestAttributeSecurityContextRepository: Scope of a Single HTTP Request

`RequestAttributeSecurityContextRepository` stores the context as an attribute attached to `HttpServletRequest`. No HTTP session is required to hold the context with this implementation.

That leads to three properties:

1. **Within the same request:** processing components and Servlet dispatches using the same request can read the context saved in the request attribute.
2. **Across an error dispatch (`ERROR`):** some Servlet containers clear the holder before initiating a separate dispatch for an error page. The request attribute lets the context be reloaded when the security chain runs for that dispatch, allowing the error handler to know which user authenticated in the original request.
3. **Across to a new HTTP request:** the old request's attributes are no longer storage for a new request. Even if the browser continues sending the same cookie, a request-attribute-only repository will not automatically restore the previous request's context.

For example, a request accesses `/orders/42`, the system saves `Authentication` in a request attribute, and the controller throws an exception leading to an error page:

```text
HTTP request #1
  REQUEST dispatch --------------> context saved in request attribute
                                        |
  ERROR dispatch (same request) --> can reload the same context
                                        |
  response ends ------------------> request attribute lifecycle ends

HTTP request #2
  new request object -------------> DOES NOT have request #1's attribute
```

Note: `ERROR` behavior depends on **whether Spring Security processes that dispatcher type**, authorization rules, how the container dispatches, and when the context was saved. Request attributes preserve context across dispatches of **the same request**; they do not guarantee an access-denied request automatically reaches a privileged error page.

### Not Equivalent to a Request-Scoped Bean

A Spring `@RequestScope` bean is also tied to the request lifecycle, but that does not make it a replacement for `RequestAttributeSecurityContextRepository`. The repository adheres to the `SecurityContextRepository` contract so Spring Security filters can load and save the context. Do not write a custom request-scoped bean and treat it as equivalent to the security repository mechanism.

## 3. HttpSessionSecurityContextRepository: Scope Across Multiple Requests in One Session

`HttpSessionSecurityContextRepository` uses the Servlet API's `HttpSession` to retain the context. When a subsequent request sends a valid session identifier (typically the `JSESSIONID` cookie), the container locates the session and the repository can reload the saved context.

```text
HTTP request #1: authentication succeeds
     |
SecurityContext containing Authentication
     |
HttpSessionSecurityContextRepository.saveContext(...)
     |
HttpSession: SPRING_SECURITY_CONTEXT = SecurityContext
     |
Response + session identifier (if a new session was created)
     |
HTTP request #2 with the same valid session
     |
HttpSessionSecurityContextRepository.loadDeferredContext(request)
     |
SecurityContextHolder -> Authentication from session
     |
Authorization checks permissions -> controller
```

The default attribute name used by Spring Security is `SPRING_SECURITY_CONTEXT`. This is a framework-managed **implementation detail**; business code is discouraged from reading/writing this session attribute directly, as doing so bypasses repository contracts and safety guarantees.

Several points to understand accurately:

- **Does not mean every request creates a session.** The repository avoids creating a session when there is no authenticated context needing persistence; session creation is also affected by configuration and other application components.
- **Does not mean permanent login.** The context can still be lost when the session expires, is invalidated on logout, changes due to concurrency/session fixation policy, or the server restarts without durable/shared sessions.
- **Does not mean replication across all devices.** A session is scoped to a client session, not a shared identity store or SSO.
- **Does not mean all application servers share sessions.** In a multi-instance cluster, you need session affinity or a shared session solution such as Spring Session, alongside cookie protection and operational setup.
- **Does not mean the application can trust context data forever.** When user permissions change or an account is revoked, the application needs a strategy to update/invalidate the context/session per security requirements.

With an empty context or anonymous authentication, the repository can avoid saving a session. Creating an `HttpSession` does not mean a valid `Authentication` has been saved. Conversely, if a session exists but the client fails to send the proper session identifier, the new request cannot locate the old session.

### Session Cookies and Security

When relying on sessions, configure HTTPS and appropriate cookie attributes (`Secure`, `HttpOnly`, `SameSite` depending on flow), enforce CSRF protection for cookie-carried credentials, and handle session fixation, timeouts, and logout. The repository stores the security context **in the server-side session**; it does not by default encrypt the full `Authentication` and place it in a browser cookie.

## 4. Quick Comparison of the Two Repositories

| Criterion | `RequestAttributeSecurityContextRepository` | `HttpSessionSecurityContextRepository` |
|---|---|---|
| Storage location | `HttpServletRequest` attribute | `HttpSession` |
| Lifecycle boundary | One HTTP request, potentially across multiple dispatches | Multiple HTTP requests sharing the same valid session |
| Across `ERROR` dispatch in same request | Supports recovering context from request attribute | Can load context if already saved in session and dispatch has session; do not rely on this alone |
| Across redirect to a new HTTP request | Not automatically preserved | Can be preserved via session |
| Requires session to store | No | Yes, when the context actually needs cross-request session storage |
| Stateless bearer-token API | Useful within a single request/dispatch when needed | Normally not used to retain authentication across requests |
| Misuse risk | Assuming login persists to the next request | Accidentally using server sessions when stateless is intended; stale context when permissions change |
| Meaning of `saveContext` | Writes to current request attribute | Writes to session per repository policy and conditions |

**A single request may need both behaviors simultaneously.** For instance, a successful login must retain state for the next request via session, while also needing `Authentication` available in an `ERROR` dispatch during the current request. That is why Spring Security supports combining repositories.

## 5. DelegatingSecurityContextRepository: Combining Multiple Stores

In common Servlet configurations of **Spring Security 6**, the default mechanism is typically `DelegatingSecurityContextRepository` using **`RequestAttributeSecurityContextRepository` first, then `HttpSessionSecurityContextRepository`**.

```java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
```

This is an **illustrative code snippet**; running it standalone requires a Spring Security Web project and corresponding imports. Conceptual behavior:

- **On load:** searches for a delegate holding a suitable context, prioritizing the first delegate that finds one. With the order above, request attributes can take precedence within the same request before reading the session.
- **On save:** invokes save on the appropriate delegates. With both implementations above, the context can live through the current request and be saved to the session for the next request.
- **Effect:** handles `ERROR` dispatch boundaries and login sessions cleanly. When a redirect triggers a new HTTP request, only the session-backed portion can carry the context across request boundaries.

Do not mistake combining repositories for distributed data synchronization or permanent user storage. Only delegates that are present, configured, and called at the right time participate.

### When Do You Need to Declare a Repository Explicitly?

For many Servlet applications using Spring Security 6 and default form login, **you do not need to create a repository manually** because the framework sets up an appropriate configuration. Override it only for specific tested requirements, such as integrating custom authentication, changing context storage scope, or controlling state in APIs.

Complete configuration class example for a Spring Boot 3.x Servlet app explicitly choosing both delegates:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        return http
            .securityContext(context -> context.securityContextRepository(repository))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

You may remove the unused `SecurityContext` import in the class above; leaving an extra import does not change logic. This configuration example **is not a standalone program compiled only with `javac`**. It requires Spring Boot MVC/Security dependencies, an application entry point, and corresponding controllers. Because this is a web app using form login/sessions, CSRF remains enabled by default; do not disable CSRF just to make login testing easier.

Do not combine this example with `SessionCreationPolicy.STATELESS` and silently expect the session to keep holding the context. If choosing stateless, design the repository and authentication mechanism to match.

## 6. Explicit Save in Spring Security 6: How Important Is saveContext?

Since Spring Security 6, `SecurityContextHolderFilter` is the standard context-loading model. This filter **loads or provides deferred loading for the context and clears the holder**, but **does not automatically save the context after processing logic finishes**. Therefore:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

This makes the current `authentication` visible to code in the same execution flow; **it is not proof that the context was saved to a request attribute or HTTP session**.

If you implement authentication logic yourself and want longer persistence, you need something like:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

This is a **snippet inside a component that already has** `authentication` (safely verified), `request`, `response`, and `securityContextRepository`; it is not a complete login endpoint. Save **before the response is committed** when sending a session cookie, issuing a redirect, or ensuring the context sits in the repository. Never treat a username received from a query parameter as authentication proof.

Distinguish this from older Spring Security 5 examples: `SecurityContextPersistenceFilter` used to manage both loading and automatic saving when the context changed. If following older tutorials to write custom login in Security 6, setting only the holder and redirecting can cause the next request to lose authentication. Check the actual filter configuration and the migration guide for your version.

**Note on standard authentication mechanisms:** Spring Security form login, HTTP Basic, OAuth2 Login, and Resource Server each have their own flows/handlers; do not mechanically inject `saveContext` everywhere. In particular, bearer-token APIs normally re-authenticate every request; saving token authentication in a server session can contradict stateless goals.

## 7. Runnable Demo with Java 17+ and JUnit: Verifying Repositories Directly

This example avoids building an unsafe "mock login" HTTP endpoint. Instead, it uses **MockHttpServletRequest, MockHttpServletResponse, and MockHttpSession** from Spring Test to accurately verify the save/load capabilities of both repositories.

Illustrative setup: **Spring Boot 3.3.5** (managing Spring Security 6.x), **Java 17**, Maven. This is a baseline to reproduce the example, **not a claim that this Boot version is the latest or still under support**. When starting a real project, pick a currently supported version and verify its dependencies, JDK, and exact behavior.

### 7.1. pom.xml

Create a new directory and place `pom.xml` in the root:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-context-repositories-demo</artifactId>
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
    </dependencies>
</project>
```

Spring Test, AssertJ, and JUnit Jupiter dependencies are included via `spring-boot-starter-test`. Do not force Spring Security modules to a version different from the Spring Boot BOM.

### 7.2. Java Test File

Create the exact file `src/test/java/example/securitycontext/SecurityContextRepositoryTest.java`:

```java
package example.securitycontext;

import jakarta.servlet.DispatcherType;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class SecurityContextRepositoryTest {

    private SecurityContext authenticatedContext() {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            )
        );
        return context;
    }

    @Test
    void requestAttributeSurvivesDispatchWithinTheSameRequest() {
        SecurityContextRepository repository =
            new RequestAttributeSecurityContextRepository();

        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        repository.saveContext(authenticatedContext(), request, response);

        assertThat(repository.loadDeferredContext(request)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        // Still the same request object; only changing dispatcher type.
        request.setDispatcherType(DispatcherType.ERROR);
        assertThat(repository.loadDeferredContext(request)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        MockHttpServletRequest nextRequest = new MockHttpServletRequest();
        assertThat(repository.loadDeferredContext(nextRequest)
                .get().getAuthentication())
            .isNull();
    }

    @Test
    void httpSessionPersistsContextAcrossRequestsSharingTheSession() {
        SecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();

        MockHttpServletRequest first = new MockHttpServletRequest();
        repository.saveContext(
            authenticatedContext(), first, new MockHttpServletResponse());

        MockHttpSession session = (MockHttpSession) first.getSession(false);
        assertThat(session).isNotNull();

        MockHttpServletRequest next = new MockHttpServletRequest();
        next.setSession(session);
        assertThat(repository.loadDeferredContext(next)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        // Different request without the same session -> no previous authentication.
        MockHttpServletRequest withoutSession = new MockHttpServletRequest();
        assertThat(repository.loadDeferredContext(withoutSession)
                .get().getAuthentication())
            .isNull();
    }

    @Test
    void delegatingRepositoryCanServeCurrentRequestAndNextSessionRequest() {
        SecurityContextRepository repository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        MockHttpServletRequest first = new MockHttpServletRequest();
        repository.saveContext(
            authenticatedContext(), first, new MockHttpServletResponse());

        assertThat(repository.loadDeferredContext(first)
                .get().getAuthentication().getName())
            .isEqualTo("alice");

        MockHttpServletRequest next = new MockHttpServletRequest();
        next.setSession((MockHttpSession) first.getSession(false));
        assertThat(repository.loadDeferredContext(next)
                .get().getAuthentication().getName())
            .isEqualTo("alice");
    }

    @Test
    void settingTheThreadLocalHolderDoesNotSaveToRepository() {
        SecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();
        MockHttpServletRequest request = new MockHttpServletRequest();

        SecurityContextHolder.setContext(authenticatedContext());
        try {
            // repository.saveContext(...) has not been called.
            assertThat(request.getSession(false)).isNull();
            assertThat(repository.loadDeferredContext(request)
                    .get().getAuthentication())
                .isNull();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

**What the demo verifies:**

- Test 1: request attribute survives within the same request object across a simulated `DispatcherType.ERROR`, but does not exist on a new request object. Changing dispatcher type in a unit test **does not simulate full Servlet container filter dispatching**; verifying an integrated ERROR flow still requires tests running through the Servlet/Spring Security filter chain.
- Test 2: session repository retains authentication across another request given the same `MockHttpSession`; without a session, the old context is not recovered.
- Test 3: delegating repository both serves the current request and persists info via session.
- Test 4: `SecurityContextHolder.setContext` does not replace repository saving. Clearing the holder in `finally` prevents test context leakage into other tests.

### 7.3. Running the Tests

On a machine with JDK 17+ supporting Maven and dependency downloads:

```bash
java -version
mvn -version
mvn test
```

With the exact project structure above, **4 tests are expected to pass** with no compilation errors. Maven stdout varies by environment, plugins, caches, and versions; do not claim a specific build log without running it. These tests do not need to start a web server because they verify the repository contract directly using mock Servlet objects.

**Why not use `javac` alone?** The tests depend on Spring Security Web, Spring Test, JUnit, and AssertJ, so they must be compiled with the Maven-resolved classpath. While a plain JDK-only Java program can run directly with `javac`/`java`, this example is a test module inside a Spring project.

## 8. Choosing a Repository by Session Strategy

Spring Security's `SessionCreationPolicy` helps control how HTTP sessions are used for authentication and security contexts.

| Policy | Purpose | Impact to remember |
|---|---|---|
| `ALWAYS` | Spring Security may proactively create a session | Suitable when stateful/session usage is intentionally designed |
| `IF_REQUIRED` | Creates a session only when needed | Common for websites using login/sessions |
| `NEVER` | Spring Security does not create a session itself, but may use an existing one | Not equivalent to fully stateless |
| `STATELESS` | Spring Security neither creates a session nor uses a session to retrieve SecurityContext | Suitable for APIs re-authenticating every request, e.g., bearer tokens |

`STATELESS` does not automatically disable every mechanism that could create a session across the **entire application**: controllers, Servlet components, or other frameworks can still use sessions if configured to do so. Nor does it **automatically disable CSRF**; CSRF decisions must depend on how clients send credentials, especially when browsers automatically attach cookies.

Contrast example of a bearer-token Servlet API (configuration snippet, not a standalone Java file):

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .build();
}
```

A stateless REST application must add the Resource Server starter and configure a trusted issuer/JWK, plus issuer/audience as required. With such an API, each request supplies and is verified by a bearer token; **never use an HTTP session repository to substitute for token verification**. Security context can still exist within a single request to support endpoint handling and method security.

Conversely, a form-login website normally needs to persist context via session. Choosing only `RequestAttributeSecurityContextRepository` for a session-style login flow breaks authentication recovery on the next request unless an independent mechanism re-establishes the context.

## 9. ERROR Dispatch, FORWARD, Async, and Request Boundaries

A single Servlet request can go through multiple dispatches:

- **`REQUEST`:** processing the incoming request from the client.
- **`FORWARD`:** internal forwarding to another resource within the same request.
- **`ERROR`:** dispatch to an error page upon failure, which may happen after security filters cleared the holder per container ordering.
- **`ASYNC`:** continuing asynchronous processing on another thread/dispatch.

`RequestAttributeSecurityContextRepository` retains data on the request object; however, **do not assume every asynchronous thread automatically carries `SecurityContextHolder`**. With async execution or thread pools, context propagation also involves async integrations, Reactor/Executor wrappers, and security configuration. These are two separate questions: "where is the context stored?" and "which execution points receive the propagated context?".

If a request enters a protected endpoint and forwards to another resource, do not assume authorization rules across dispatcher types are automatically identical. Spring Security can apply filters to configured dispatcher types; define permissions for `FORWARD`/`ERROR` clearly and write tests to avoid accidentally blocking error pages or leaving them too open.

**Example requiring real integration testing:** a valid user hits an endpoint that throws an exception; the error is handled by `/error` after a new dispatch. You want the error page to recognize the right principal without granting access to sensitive data. You must verify simultaneously that (1) filter mapping runs for `ERROR` dispatch; (2) the request attribute is still present; (3) authorization on the `ERROR` endpoint is valid; and (4) the final response leaks no unintended information.

## 10. Save Timing, Fresh Context, and Thread Safety

When logging in manually, create a fresh context via `SecurityContextHolder.createEmptyContext()` and set the verified `Authentication`, rather than mutating a context that could be accidentally shared or in use:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticatedAuthentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

**This is Java pseudocode inside a custom authentication handler**: `authenticatedAuthentication` must come from a valid authentication mechanism; `request`, `response`, and `securityContextRepository` must be injected/supplied in the proper lifecycle. Never treat an arbitrary username string or header as a proven identity.

- **Save before redirect / response commit:** in a session flow, if a new session must be created, the response needs the chance to send the session cookie back to the client.
- **Clear context at request end:** the holder uses a thread-local strategy on the Servlet stack; web security filters clear the holder after the request. Custom thread pools require proper context propagation and cleanup.
- **Logout:** use Spring Security's logout mechanism to remove authentication, handle sessions, and update security context per policy. Merely calling `SecurityContextHolder.clearContext()` on one thread does not necessarily delete the context saved in the session for subsequent requests.
- **Session fixation/concurrency:** session management needs dedicated login protection, rotating session IDs per supported configuration, and limiting concurrent sessions if required by business rules.
- **Permission consistency:** if roles/authorities change while a session remains active, you may need to update the context, re-authenticate, or invalidate the session. The repository is not an automatic IAM permission-sync tool.

Do not call `HttpSession.invalidate()` arbitrarily from scattered places expecting every downstream security context/cookie to be cleaned up properly; use a well-defined, tested logout/session-management mechanism.

## 11. Troubleshooting Common Issues

| Symptom | Mechanism to inspect | How to investigate |
|---|---|---|
| Login returns redirect successfully, but next request is anonymous | Context bound only to request, custom login forgot `saveContext`, or session cookie did not pass through | Inspect active repository, save/load logs, `Set-Cookie`/`Cookie`, redirect timing |
| Error page does not see authenticated `Authentication` | Holder cleared before `ERROR` dispatch, missing request-attribute delegate, or different filter mapping | Inspect dispatch type, request attributes, chain, and `/error` rules |
| Bearer-token API app unexpectedly creates sessions | Flow/form login, CSRF, MVC components, or custom code using `HttpSession` | Check chains, `SessionCreationPolicy`, `JSESSIONID`, and session-creating components |
| `SecurityContextHolder.getContext().getAuthentication()` returns `null` | No `Authentication` for request or not yet loaded | Check security filters, ordering, repository, credentials, and dispatcher type |
| After logout, next request still sees the user | Session context not cleared/invalidated or IdP/login flow re-authenticates | Check logout handlers, session, cookies, remember-me, and SSO |
| User persists across requests despite declaring only request-attribute repository | Another mechanism re-authenticates or a second session/security chain exists | Check `SecurityFilterChain` beans, other filters, bearer/basic credentials |
| Test passes in isolation but fails in full suite | `SecurityContextHolder` not cleared or `MockHttpSession` unexpectedly reused | Clear context in `finally`, isolate mock request/session per test |
| In multi-node cluster, login intermittently drops | Session not shared / missing affinity, differing cookies/secrets | Check Servlet session infrastructure/Spring Session and proxy routing |
| Async thread misses principal | Context not propagated across threads/executors | Check async wrappers and when security context is captured/cleared |

Do not diagnose "session is not working" simply because `SecurityContextHolder` is empty after the response completes. Clearing the holder is normal; the real question is **whether the repository saves and reloads the right context for the next request**.

## 12. Selection Workflow in Servlet Applications

1. **Identify the authentication method:** form login/session, HTTP Basic, OAuth2 Login, or stateless bearer JWT/opaque token. Each mechanism maintains authentication differently.
2. **Determine required lifetime:** current request only, multiple dispatches within the same request, or multiple requests within the same session.
3. **Read the actual configuration:** how many `SecurityFilterChain` beans exist, whether `SecurityContextHolderFilter` or an older filter is used, whether a custom repository is configured, and what the session policy is.
4. **Keep defaults when they meet requirements:** for Spring Security 6 web-login apps, the delegating repository combining request attribute and session usually handles both scopes well.
5. **If using custom authentication:** verify the fresh context is placed in the holder and saved through the repository at the right time, before committing the response.
6. **If stateless:** do not rely on sessions to hold authentication; verify evidence on every request; do not disable CSRF casually if clients still use browser cookies.
7. **Test from both angles:** same request across different dispatches and new requests with/without a session, plus login/logout, error handling, session timeout, and post-redirect behavior.

### Self-Check

**Question 1.** `RequestAttributeSecurityContextRepository` saved the context for a `REQUEST` dispatch. When an `ERROR` dispatch occurs on the same request, can the context be reloaded?  
**Answer:** Yes, if the dispatch genuinely shares the same request attributes and Spring Security/the security chain loads the repository; its primary purpose is preserving context across dispatches of the same request.

**Question 2.** Why can a new request using the same `JSESSIONID` recover authentication from `HttpSessionSecurityContextRepository`?  
**Answer:** Because the server uses the session identifier to locate the `HttpSession` holding the saved context. This depends on a valid session, a previously saved context, and the security repository configuration.

**Question 3.** Custom authentication calls `SecurityContextHolder.setContext(context)` and redirects without calling `saveContext`. Will the next request definitely stay logged in?  
**Answer:** No. Under Spring Security 6's explicit-save model, the holder only serves the current execution; the context must be saved to an appropriate repository to survive across a redirect.

**Question 4.** Should an application using `SessionCreationPolicy.STATELESS` rely on `HttpSessionSecurityContextRepository` to retain JWT authentication?  
**Answer:** No. A stateless Resource Server should validate the bearer token on every request rather than using server sessions to hold authentication state.

**Question 5.** Does using the delegating repository mean every request automatically creates a session?  
**Answer:** No. The `HttpSession` delegate has logic to avoid creating unnecessary sessions; session creation still depends on the context, configuration, and other application components.

**Key takeaway:** `RequestAttributeSecurityContextRepository` handles **lifecycle within a single HTTP request, including other dispatches**; `HttpSessionSecurityContextRepository` handles **restoring `SecurityContext` across multiple requests in the same session**. `DelegatingSecurityContextRepository` can combine both. The repository decides where to store, while web security filters, the authentication mechanism, and `saveContext` calls decide when the context is safely loaded and saved.