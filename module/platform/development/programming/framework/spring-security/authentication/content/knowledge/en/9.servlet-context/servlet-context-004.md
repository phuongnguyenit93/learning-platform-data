# SecurityContextRepository: Loading, Saving, and Context Lifespan

**Module:** Spring Security – authentication. **Parent topic:** Servlet Context.

## 1. The Problem: Login Succeeds in the Current Request, Yet the Next Request Gets 401

A common situation in Spring Boot Servlet programming:

~~~java
Authentication verified = authenticationManager.authenticate(token);
SecurityContextHolder.getContext().setAuthentication(verified);
~~~

Within the **current request**, downstream code can see the newly assigned `Authentication`. However, when the browser sends `GET /profile` on the next request, it is treated as unauthenticated.

Why? Because **`SecurityContextHolder` and `SecurityContextRepository` do not do the same job**:

- `SecurityContextHolder` holds the `SecurityContext` **currently in use during the active execution flow** (by default via `ThreadLocal` on the Servlet stack).
- `SecurityContextRepository` defines **where to load from and where to save** the context so it can be used in a subsequent execution, depending on the implementation: request attribute, `HttpSession`, or not saved at all.
- `SecurityContextHolderFilter` reads the repository to supply the context for the request and clears the holder when processing ends. In Spring Security 6, this filter **does not automatically write every change** of the holder back down to the repository.
- A built-in authentication mechanism, such as properly configured form login, can **proactively save the context upon successful login**. When writing a custom login filter/controller, the developer must perform the save step if login needs to persist across requests.

**Core principle: putting `Authentication` into the holder only affects the currently active context; to keep it after the request, you must save to the right repository, at the right time, under the right session policy.**

Never confuse "the user data is still in the database" with "the browser still has an authenticated session": the account store does not replace attaching `Authentication` to subsequent requests.

## 2. Separating Four Roles Before Reading Code

| Component | Function | Storage / Lifecycle Target |
| --- | --- | --- |
| `Authentication` | Principal, authorities, credentials/details, and authenticated status | A specific authentication result; may be placed inside a context |
| `SecurityContext` | Container holding the current `Authentication` | Represents security identity at processing time |
| `SecurityContextHolder` | Lets running code get/set the context through a `SecurityContextHolderStrategy` | Typically **ThreadLocal of the request-processing thread**, not a database or session |
| `SecurityContextRepository` | Loads/saves the context per request/response and backend | May be request attribute, `HttpSession`, a custom store, or no storage |
| `SecurityContextHolderFilter` | Connects the repository with the holder in the Servlet filter chain | Reads before controller and clears holder after request; **does not auto-persist** |
| `SecurityContextPersistenceFilter` | Older approach that could auto-save context when the request ended | Mainly needed to understand migrating legacy apps; **do not combine** with HolderFilter |

Visualization:

~~~text
Browser ---- HTTP REQUEST ----> Spring Security Filter Chain
                                   |
                                   v
                          SecurityContextHolderFilter
                                   |
                  loadDeferredContext(request)
                                   |
                                   v
                      SecurityContextRepository
                        |            |
                        |            +--> HttpSession (if configured)
                        +--> request attribute
                                   |
                                   v
                      SecurityContextHolder (ThreadLocal)
                                   |
                                   v
                      Controller/Service/Authorization
                                   |
                           Authentication verified
                                   |
                      setContext + saveContext
                                   |
                                   v
                      SecurityContextRepository
                                   |
                         reused in next request
                                   |
                            finally: clear holder
~~~

**Meaning:** Holder is the "internal access point for the current processing context"; repository is the "load and save strategy". `saveContext` does not turn `SecurityContext` into business data, and `loadDeferredContext` does not re-verify raw passwords every time by default.

## 3. SecurityContextRepository API: Three Modern Methods and One Legacy Method

Package: `org.springframework.security.web.context`. The `SecurityContextRepository` interface in Spring Security **6.5.11** has these key members:

~~~java
// API signatures abbreviated for learning, not a standalone class.
DeferredSecurityContext loadDeferredContext(HttpServletRequest request);

void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);

boolean containsContext(HttpServletRequest request);

// Legacy/deprecated API:
SecurityContext loadContext(HttpRequestResponseHolder holder);
~~~

**Note:** `loadDeferredContext` is a default method on the interface returning `DeferredSecurityContext`; `loadContext(HttpRequestResponseHolder)` is deprecated. Implementations can override how loading and saving work.

### 3.1. loadDeferredContext(request)

Returns an object that **defers retrieving the context until needed**; it has a `get()` method returning `SecurityContext`, and an `isGenerated()` method indicating whether the context was newly created in the deferred API.

~~~java
DeferredSecurityContext deferred =
        repository.loadDeferredContext(request);

SecurityContext context = deferred.get();
~~~

This is an **illustrative snippet inside a Servlet app with a repository and request**, not a complete Java program. Do not infer that calling `loadDeferredContext` always reads `HttpSession`/database immediately; that is the point of deferred loading.

When the request has no authentication context yet, the repository returns an **empty context**, not null. However, `SecurityContext.getAuthentication()` may be null for an unauthenticated request.

### 3.2. saveContext(context, request, response)

Instructs the repository to **save** the context according to the implementation's policy. For the session repository, this may mean updating an attribute in `HttpSession`; for the request-attribute repo, setting an attribute on the request; for the null repo, a no-op.

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);

repository.saveContext(context, request, response);
~~~

Key point: **pass both request and response**. The repository may need the response to handle HTTP commit/session cookies. When writing custom Servlet login, save **before the response is committed/redirected** to avoid missing `Set-Cookie` or saving too late.

### 3.3. containsContext(request)

Returns `true` if the repository recognizes a context within the scope associated with that request. It is **not** an API to "check whether the user is validly logged in".

For example:

- A request attribute might contain an empty context after logout.
- A session might hold an old context even though the user's roles were revoked in the DB.
- The repository having a context does not mean the user has `ROLE_ADMIN`, is unexpired, or is allowed to access a resource.
- A context from an authentication mechanism might be newly created during the request without yet being saved.

For authorization, use `AuthorizationManager`, `@PreAuthorize`, `Authentication` checks, and current policies; do not rely solely on `containsContext`.

### 3.4. Deprecated loadContext(...)

`loadContext(HttpRequestResponseHolder)` belongs to the older model's implicit load/save and response-wrapper mechanism. In Spring Security 6, understand the modern approach as **deferred loading and explicit save**; do not write new code on the deprecated API just because you saw it in Spring Security 5 examples.

## 4. Four Built-In Repositories: RequestAttribute, HttpSession, Null, and Delegating

| Implementation | Where Is It Stored? | Survives to the Next HTTP Request? | When Appropriate |
| --- | --- | --- | --- |
| `RequestAttributeSecurityContextRepository` | Attribute on the `ServletRequest` object | **No** when the next request is a new request | Preserving context across dispatches of the **same request** (e.g., error dispatch) |
| `HttpSessionSecurityContextRepository` | `SecurityContext` attribute in `HttpSession` | **Yes**, if the browser sends the right session ID and the session is still valid | Form login and web apps using HTTP sessions |
| `NullSecurityContextRepository` | Not saved | **No** | Stateless APIs that should not persist security context across requests |
| `DelegatingSecurityContextRepository` | Delegates to multiple repositories in order | **Depends on delegates** | Combining request attributes and sessions |

### 4.1. Default in Spring Security 6

Spring Security 6 Servlet typically uses:

~~~java
new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
);
~~~

This is an **illustrative object-creation snippet**; Spring Security provides this configuration by default in session-based flows, so you do not need to redeclare it just to "enable session login". The order of delegates matters when loading context. When saving, the delegating repository distributes the save across its delegates.

**Two layers solve two different needs:**

1. Within **a single request** having multiple dispatches (`REQUEST`, `ERROR`, ...), the request attribute helps restore context if the servlet container caused the holder to be cleared in between.
2. Between **two independent HTTP requests**, `HttpSession` lets the browser retain identity after a successful login.

Never call request attributes "cookie-less sessions"; they **do not survive into a new HTTP request**.

## 5. RequestAttributeSecurityContextRepository: Scope Within One Servlet Request

### 5.1. Why Is It Needed?

Suppose an authenticated request encounters an error:

~~~text
GET /orders/42 (authenticated)
      |
      v
Controller/Filter -> throws exception
      |
      v
Servlet ERROR dispatch
      |
      v
/error is rendered within the same request
      |
      +--> May need principal for display or policy enforcement
~~~

In some container handling of `ERROR` dispatches, `SecurityContextHolder` has already been cleared before the error page runs. If the context was stored in a request attribute, the repository can restore it during the same-request dispatch.

### 5.2. What Request Attributes Do Not Do

- Do not issue session cookies.
- Do not make the next request authenticated.
- Do not store identity in a database or Redis.
- Do not guarantee every filter and dispatch type re-runs identically; Servlet dispatcher types and filter chain configuration still apply.
- Do not verify passwords or refresh authorities automatically.

**`RequestAttributeSecurityContextRepository` is a way to keep data scoped to a request**, not a default mechanism to "remember logged-in users".

## 6. HttpSessionSecurityContextRepository: Scope Across Multiple Requests

### 6.1. Reading from Session

When a valid session exists, the repository looks up the saved `SecurityContext` in `HttpSession`; the default key is `SPRING_SECURITY_CONTEXT`. If no valid value is found, it supplies a new/empty context.

Diagram:

~~~text
POST /login (username/password)
     |
     +--> authenticate() succeeds
     +--> saveContext(...) into HttpSession
     +--> Response includes session cookie, e.g. JSESSIONID

GET /account (browser sends JSESSIONID back)
     |
     +--> SecurityContextRepository loads context from session
     +--> SecurityContextHolder is populated
     +--> Authorization sees stored Authentication
~~~

`JSESSIONID` or `SESSION` is a **cookie name depending on the container/Spring Session and configuration**; not every app uses the same name. The cookie only carries the **session identifier**, not the literal `SecurityContext`. The context content is kept server-side according to the configured session store.

### 6.2. loadContext Does Not Always Create a Session

With the standard `HttpSessionSecurityContextRepository`:

- **Reading** context does not automatically create a new session if none exists.
- When **saving** a context considered modified and needing persistence, the implementation **may create a session** if none exists, depending on `allowSessionCreation` and security policy.
- Empty or anonymous contexts may not require creating a session; the implementation uses `AuthenticationTrustResolver` to distinguish anonymous.
- If session creation is disallowed, calling `saveContext` does not force a session to appear.
- **Another** application component (such as a request cache) can still create a session under its own policy.

Therefore, "I saw an `HttpSession` created even with `SessionCreationPolicy.NEVER`" is not enough to conclude `SecurityContextRepository` is malfunctioning. Identify which component called `request.getSession()` or stored a saved request.

### 6.3. Saving in Session Does Not Mean Permissions Are Fresh

If an admin revokes a role after login, `Authentication.getAuthorities()` in the session may still be an old snapshot. The repository **does not automatically invoke `UserDetailsService` on every request**; it is not a cache invalidation mechanism or a token/session revocation system.

If new permissions must take effect promptly, add session invalidation, re-authentication, `authVersion` comparisons, or live status/permission lookups at sensitive points.

## 7. NullSecurityContextRepository: When You Do Not Want to Persist Context

`NullSecurityContextRepository` is an implementation that does not persist context beyond the request. It is commonly used in applications such as:

- Resource servers validating a bearer token on **every HTTP request**.
- HTTP Basic validating credentials on each request in stateless mode.
- API services with `SessionCreationPolicy.STATELESS` that do not rely on server-side login sessions.

~~~java
// Illustrative configuration in a Spring Security Servlet app:
http.sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Spring Security 6 can configure `NullSecurityContextRepository` and avoid using sessions to obtain security context under the stateless policy. **Do not** assume the application will never have any `HttpSession` at all, because other code may still call the Servlet session API depending on configuration, or a custom filter might create a session. Test actual behavior.

**Boundary:** Stateless does not mean the API skips authentication. It means it does not rely on a **security context previously stored in a session**; each request carries its own proof (bearer token, Basic credentials) or corresponding stateless authentication mechanism.

Never store raw bearer tokens or refresh tokens in sessions or logs just for debugging convenience.

## 8. DelegatingSecurityContextRepository: Combining Scopes Without Merging Storage Types

Spring Security 6 uses `DelegatingSecurityContextRepository` to save context to multiple delegates and retrieve it from the appropriate delegate in order. For example, the default is request-attribute first, HttpSession second:

~~~text
                               DelegatingSecurityContextRepository
                                     /                \
                                    v                  v
                  RequestAttributeRepository    HttpSessionRepository
                   (same request/dispatch)     (multiple HTTP requests)
                                    \                  /
                                     \                /
                               SecurityContextHolder
~~~

If you configure a repository with **only `HttpSessionSecurityContextRepository`**, you may lose context restoration benefits during some `ERROR` dispatches. If you use only request attribute, users will not stay logged in across subsequent requests.

**Read order matters:** If the request attribute already has a context, it may be chosen over the session context on the same request. When building a custom delegating repository, specify the exact order and semantics. Never allow a less-trusted delegate to inject an unauthenticated principal/authority into the repository chain.

**Saving is also not guaranteed to succeed everywhere:** custom/remote delegates may fail, hit session limits, or have their own consistency strategies. Decide your failure policy before granting access or redirecting.

## 9. Spring Security 5 vs. 6: Implicit Save vs. Explicit Save

### 9.1. Legacy Model – SecurityContextPersistenceFilter

In the implicit-save model, `SecurityContextPersistenceFilter` loaded the context, tracked changes, and upon request completion/response commit could automatically write it back to the repository. Simply calling:

~~~java
SecurityContextHolder.setContext(context);
~~~

could be enough for the persistence filter to auto-save, depending on older configuration. However, this is migration background, not the default behavior to expect in Spring Security 6.

### 9.2. Modern Model – SecurityContextHolderFilter

Spring Security 6 places `SecurityContextHolderFilter` into the default flow with `requireExplicitSave=true`:

~~~text
request -> load context into holder
               |
               v
       authentication/controller
               |
               +--> setContext(context) only updates holder
               |
               +--> saveContext(context, request, response) if persistence is wanted
               |
               v
       response, filter clears holder
~~~

`SecurityContextHolderFilter` **only loads and clears**; it does not monitor changes and does not auto-save. If custom login only calls `setContext` and redirects, the next request can lose the login. Fix by **saving explicitly before committing the response**.

### 9.3. Migration Configuration

~~~java
// In Spring Security 6 HttpSecurity configuration:
http.securityContext(sc -> sc.requireExplicitSave(true));
~~~

Spring Security 6 already applies this behavior by default in matching configurations; the statement above makes the intent explicit. `requireExplicitSave(false)` can be used as a compatibility option when upgrading legacy code, but you should never put both `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter` in the same chain.

**Note:** Not every built-in authentication mechanism requires you to call `saveContext` manually in a controller. Framework-managed form login already has appropriate hooks. Issues typically happen when you build a custom authentication flow, replace filters, or design a custom login API.

## 10. Runnable Java 17 Demo: Request Attribute, HTTP Session, Stateless, and Logout

This standalone example runs with Gradle using **Spring Security Web 6.5.11**, **Spring Framework Test 6.2.15**, and mock Servlet request/response objects. It needs no server or database and **does not verify real credentials**: the authenticated token is constructed solely from **trusted** demo code to test the exact behavior of `SecurityContextRepository`.

**Never** build an endpoint that lets clients send a username/role and calls `UsernamePasswordAuthenticationToken.authenticated(...)` like the demo; in real systems, you must run `AuthenticationManager.authenticate(...)` before creating a trusted context.

### 10.1. Directory Structure

~~~text
security-context-repository-demo/
├── build.gradle
└── src/main/java/example/ContextRepositoryDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework:spring-web:6.2.15'
    implementation 'org.springframework:spring-test:6.2.15'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.ContextRepositoryDemo'
}
~~~

The Servlet/Spring Test dependencies support the mocks in the program. In real Spring Boot apps, prefer version alignment managed by Boot's BOM instead of copying versions manually from examples.

**File `src/main/java/example/ContextRepositoryDemo.java`:**

~~~java
package example;

import java.util.List;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

public final class ContextRepositoryDemo {

    public static void main(String[] args) {
        // Two repository layers close to Spring Security 6 defaults.
        SecurityContextRepository repository =
                new DelegatingSecurityContextRepository(
                        new RequestAttributeSecurityContextRepository(),
                        new HttpSessionSecurityContextRepository()
                );

        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");
        MockHttpServletResponse loginResponse =
                new MockHttpServletResponse();

        System.out.println("before.contains="
                + repository.containsContext(login));

        // Create an authenticated token only in a trusted demo.
        // In a web app, AuthenticationManager must verify first.
        Authentication trusted =
                UsernamePasswordAuthenticationToken.authenticated(
                        "an", null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(trusted);
        SecurityContextHolder.setContext(context);

        // Holder already has the identity, repository STILL has no data.
        System.out.println("holder.name="
                + SecurityContextHolder.getContext()
                        .getAuthentication().getName());
        System.out.println("beforeSave.contains="
                + repository.containsContext(login));

        // This call is what persists the context into the session.
        repository.saveContext(context, login, loginResponse);

        System.out.println("afterSave.contains="
                + repository.containsContext(login));

        MockHttpSession session = (MockHttpSession) login.getSession(false);
        System.out.println("session.created=" + (session != null));

        // Simulate the filter clearing ThreadLocal after the login request.
        SecurityContextHolder.clearContext();
        System.out.println("holder.afterClear.empty="
                + (SecurityContextHolder.getContext()
                        .getAuthentication() == null));

        // NEW HTTP request with the same session: reads identity.
        MockHttpServletRequest next =
                new MockHttpServletRequest("GET", "/account");
        next.setSession(session);

        SecurityContext restored =
                repository.loadDeferredContext(next).get();

        System.out.println("next.name="
                + restored.getAuthentication().getName());
        System.out.println("next.contains="
                + repository.containsContext(next));

        // Request-attribute-only repository.
        RequestAttributeSecurityContextRepository requestOnly =
                new RequestAttributeSecurityContextRepository();
        MockHttpServletRequest oneRequest =
                new MockHttpServletRequest("GET", "/error");
        requestOnly.saveContext(
                context, oneRequest, new MockHttpServletResponse());

        System.out.println("attribute.sameRequest="
                + (requestOnly.loadDeferredContext(oneRequest).get()
                        .getAuthentication() != null));

        MockHttpServletRequest anotherRequest =
                new MockHttpServletRequest("GET", "/next");
        System.out.println("attribute.nextRequest="
                + (requestOnly.loadDeferredContext(anotherRequest).get()
                        .getAuthentication() != null));

        // Stateless repository that does not save context.
        SecurityContextRepository nullRepository =
                new NullSecurityContextRepository();
        MockHttpServletRequest apiRequest =
                new MockHttpServletRequest("GET", "/api/resource");
        nullRepository.saveContext(
                context, apiRequest, new MockHttpServletResponse());

        System.out.println("null.contains="
                + nullRepository.containsContext(apiRequest));
        System.out.println("null.loadEmpty="
                + (nullRepository.loadDeferredContext(apiRequest).get()
                        .getAuthentication() == null));

        // Logout logic: save an EMPTY context via the corresponding repository.
        SecurityContext empty = SecurityContextHolder.createEmptyContext();
        repository.saveContext(
                empty, next, new MockHttpServletResponse());

        MockHttpServletRequest afterLogout =
                new MockHttpServletRequest("GET", "/account");
        afterLogout.setSession(session);
        System.out.println("afterLogout.empty="
                + (repository.loadDeferredContext(afterLogout).get()
                        .getAuthentication() == null));

        SecurityContextHolder.clearContext();
    }
}
~~~

### 10.2. Running the Program

Use JDK **17+**, a compatible Gradle version, and network access on the first run to download dependencies:

~~~bash
gradle -q run
~~~

With an existing Gradle Wrapper: `./gradlew -q run` or on Windows `gradlew.bat -q run`.

**Expected stdout** from `System.out.println` (excluding library/Gradle logs if enabled by the environment):

~~~text
before.contains=false
holder.name=an
beforeSave.contains=false
afterSave.contains=true
session.created=true
holder.afterClear.empty=true
next.name=an
next.contains=true
attribute.sameRequest=true
attribute.nextRequest=false
null.contains=false
null.loadEmpty=true
afterLogout.empty=true
~~~

### 10.3. Analyzing the Output

- `before.contains=false`: no context in the repository yet.
- `holder.name=an` yet `beforeSave.contains=false`: the holder already sees the authenticated principal, but **it has not been saved yet**; direct proof of the difference between the two components.
- `afterSave.contains=true` and `session.created=true`: the delegating repository saved through request attribute and session.
- `holder.afterClear.empty=true`: clearing ThreadLocal does not erase the context saved in the session.
- `next.name=an`: the new request with the same session loaded the context from the repository.
- `attribute.sameRequest=true`, `attribute.nextRequest=false`: request attribute can serve the same request (including dispatches) but does not persist to a new request.
- `null.contains=false`, `null.loadEmpty=true`: null repository is a no-op; each stateless request must authenticate itself via the configured mechanism.
- `afterLogout.empty=true`: simulates saving an empty context to the repository to clear authentication from the session. **In a real app, use logout support** to also clean up session/cookie/CSRF/remember-me and related components.

**Demo limitations:** The program calls the repository directly on mock requests; it does not run `SecurityContextHolderFilter`, does not send session cookies over the network, does not perform session fixation protection, does not verify passwords, and does not check authorization. The boolean values only illustrate storage semantics; they **do not replace** integration tests against `SecurityFilterChain` in your application.

## 11. Integrating in Spring Boot Servlet: Configuring the Repository Explicitly

For an application using session-based authentication, you can configure:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            SecurityContextRepository contextRepository) throws Exception {

        http
            .securityContext(sc -> sc
                    .securityContextRepository(contextRepository)
                    .requireExplicitSave(true))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is **illustrative integration code**: it requires Spring Config/Security imports, Servlet starter dependencies, and matching templates/login; it is not a standalone program. With Spring Security 6's session-based defaults, most applications **do not need to declare this repository bean themselves**. It is shown here to highlight the `http.securityContext(...).securityContextRepository(...)` hook, not as a recommendation to override defaults unnecessarily.

**Warning:** When customizing `SecurityContextRepository`, ensure the exact same repository instance is used **consistently** by `SecurityContextHolderFilter` and related authentication filters/success handlers. Creating a bean where a controller saves into one instance while the filter loads from another is a hard-to-trace source of bugs.

### 11.1. Session Policies

~~~java
// Illustrative integration snippet, not a standalone class:
http.sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

| Policy | Practical Meaning |
| --- | --- |
| `ALWAYS` | Spring Security proactively creates a session under matching configuration |
| `IF_REQUIRED` | Creates a session when needed by security mechanisms; usually fits web form login |
| `NEVER` | Spring Security does not proactively create a new session, but can use an existing one |
| `STATELESS` | Spring Security neither creates nor uses `HttpSession` to obtain security context; typically pairs with null repository for security |

The actual existence of an `HttpSession` also depends on **Servlet application code, request cache, other filters, and Spring Session**. When debugging, check who calls `getSession()` and whether a saved request exists, rather than blaming everything on the repository.

## 12. Custom Login: The Right Order So Authentication Is Not Lost After Redirect

If you **intentionally** write a login controller or filter and have an `AuthenticationManager` handling credentials, the basic right steps are:

~~~text
Step 1: Receive credentials over HTTPS
Step 2: AuthenticationManager.authenticate(unauthenticated token)
Step 3: If successful, execute required session strategy
Step 4: Create a new SecurityContext holding the verified Authentication
Step 5: Place context into SecurityContextHolder
Step 6: saveContext(context, request, response)
Step 7: Only then redirect / commit the response
~~~

Illustrative flow snippet, **not standalone compilable** (lives inside a service/controller with dependencies and an established session policy):

~~~java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginBody.username(), loginBody.password());

Authentication verified =
        authenticationManager.authenticate(requestToken);

// When building a custom authentication flow, ensure SessionAuthenticationStrategy
// is invoked properly before saving, including session fixation protection.
SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(verified);

securityContextHolderStrategy.setContext(context);

securityContextRepository.saveContext(
        context, httpServletRequest, httpServletResponse);

// Only finish the response/redirect after saving succeeds.
~~~

**Very easy to miss: session fixation protection.** Built-in form login configurations execute the appropriate session strategies. If you write a custom controller calling `authenticate(...)` and `saveContext(...)` directly, you **do not automatically** replicate full `SessionAuthenticationStrategy`, concurrent session control, CSRF, remember-me, and success/failure handling in just a few lines. Either integrate completely or prefer framework-provided login mechanisms.

Never construct a trusted `Authentication` via `UsernamePasswordAuthenticationToken.authenticated(...)` from a client payload **before verification**. That API does not prove the password is valid.

### Why Save Before Redirecting?

If the server calls `sendRedirect(...)` or writes a body causing the HTTP response to be **committed**, creating a new session or setting a cookie afterward may no longer take effect as expected. The explicit-save flow avoids an entire class of early-response-commit bugs seen in the implicit-save model.

## 13. Logout, clearContext, and Saving an Empty State

### 13.1. Clearing the Holder Is Not Deleting the Session

~~~java
SecurityContextHolder.clearContext();
~~~

This operation clears the current thread's holder. If `HttpSession` still stores an authenticated `SecurityContext`, a subsequent request can restore it. Therefore, logout must handle **both holder and persistence**.

Spring Security Servlet provides logout support such as `SecurityContextLogoutHandler` and other handlers to:

- Clear `SecurityContextHolder`.
- Clear/write an empty context via the appropriately configured repository.
- Invalidate the session per policy.
- Handle cookies, remember-me, CSRF tokens, or other integrations if present.

In the explicit-save mechanism, **clearing authentication is also a change requiring persistence**. You can save an empty context when handling logout manually (being careful with repo/session and ordering), but you should not replace full framework logout with a single `saveContext(empty)` line, because session fixation, cookies, tokens, and integrations remain involved.

### 13.2. JWTs and Refresh Tokens Are Separate Flows

If the client holds a still-valid bearer access token, clearing the session cookie or saving an empty context **does not automatically revoke the signed token**. With a stateless resource server, each request carries its own bearer token; revocation requires short TTLs, token versioning/revocation/denylist, or introspection depending on architecture.

Do not promise "log out of all devices" if the system only invalidates a single active session.

## 14. Async, Thread Pools, and Servlet Dispatch: Scope Is Not Global

### 14.1. Default ThreadLocal

`SecurityContextHolder` defaults to the `MODE_THREADLOCAL` strategy. The context is accessible within the same thread without passing parameters, but does not automatically appear on **another thread**.

Example:

~~~java
Authentication auth = SecurityContextHolder.getContext()
        .getAuthentication();
// The snippet above works in the context of the currently processing thread.
// A Runnable executed by an executor on another thread does NOT automatically have auth.
~~~

This is illustrative code, not a claim that all async integrations lose context: Spring Security provides `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and environment-specific propagation integrations.

When using thread pools or `@Async`, use a supported propagation solution, clear the context after the task, and avoid retaining mutable credentials/principals for too long. Do not switch a multi-user server to `MODE_GLOBAL`. `MODE_INHERITABLETHREADLOCAL` is not automatically safe for reused thread pools.

### 14.2. Servlet ERROR/FORWARD/ASYNC Dispatches

An HTTP request can go through multiple dispatch types; the container and filter mappings decide where security filters re-run. The request-attribute repo keeps context on **the same request object** across dispatches. The session repo serves **different HTTP requests**.

Do not equate "same HTTP request" with "same Java thread": asynchronous processing can switch threads, requiring Servlet async integration/context propagation. Some `ERROR` dispatches run after the holder has been cleared; request attributes can help restore it, though you still need proper dispatcher types configured on the filter chain.

### 14.3. Thread Leaks Without Cleanup

If a custom filter calls `SecurityContextHolder.setContext(context)` without cleaning up in `finally` (or runs outside the standard filter chain), a thread pool can reuse the thread for a later request and retain the old identity. In standard Spring Security, filters manage clearing the holder. When writing code outside the chain or in tests, clear the context at the right lifecycle boundary.

~~~java
try {
    SecurityContextHolder.setContext(context);
    // Logic running under the verified identity.
} finally {
    SecurityContextHolder.clearContext();
}
~~~

This is an example of protecting ThreadLocal when **managing context manually**; it does not mean every controller should manually call clear, which would hide the context from downstream filters.

## 15. RequestCache Is Not SecurityContextRepository

At least three concepts are easy to mix up:

| Component | Function |
| --- | --- |
| `SecurityContextRepository` | Saves/loads the **authentication context** |
| `RequestCache` | Saves the original HTTP request to return to after login (e.g., deep link) |
| `HttpSession` | A server-side storage mechanism that **both** may use |

When `JSESSIONID` appears even before login, the cause may be `HttpSessionRequestCache` saving the target URL prior to redirecting to the login page; it does not necessarily mean `SecurityContextRepository` stored an authenticated user.

Spring Security 6 optimizes `RequestCache` reads compared to older versions. If choosing stateless for an API, control both session policy and request cache so saved requests are not accidentally stored and causing unexpected behavior.

**Never use `containsContext` to ask "is there a saved request yet?"**. Those are two different contracts.

## 16. Customizing the Repository: Choose by Need, Do Not Rewrite by Habit

An application may need to store context in another backend for multi-node deployments or distributed sessions. There are two main approaches:

1. Continue using `HttpSessionSecurityContextRepository`, while **moving the session store to Redis/database** via Spring Session or a container-compatible session strategy. Here the repository still relies on `HttpSession`, and only the backing storage changes.
2. Write a custom `SecurityContextRepository` with explicit load/save/contains behavior and network/serialization error handling. This is sensitive work that must respect authorization and session lifecycles.

When designing a custom repository, clarify:

- How identity/session keys are generated; fixation/hijacking protection, TTL, rotation, and cookie flags.
- Whether `loadDeferredContext` does lazy loading; when not found, return an empty context, never null.
- Whether `saveContext` persists durably before reporting success; how committed responses are handled.
- `containsContext` only reflects stored data and does not confirm a long-lived principal's current permissions.
- Whether the repository stores anonymous/empty contexts, which can bloat storage needlessly.
- Which principal implementations are serialized inside `SecurityContext`, and compatibility across multi-version deployments.
- When logout/session expiration occurs, keys/tokens/entries are revoked per policy, avoiding resurrection via cache replication races.
- Key namespacing by app/environment/tenant to prevent collisions and cross-tenant exposure.
- When the store loses connectivity, whether sensitive security operations fail closed or how fallback behaves; never "authenticate anonymous as admin" due to a deserialization error.
- Logging, tracing, and metrics must not contain raw passwords, access tokens, or full principal objects.
- Test concurrency and real multi-node setups, not just unit tests of one implementation.

**A custom repository does not replace `AuthenticationManager` and authorization.** It only decides saving/loading context; if you allow untrusted data to construct an `Authentication(isAuthenticated=true)` and save it, that is a security vulnerability at the authentication source.

## 17. Multi-Chain: One Endpoint Uses This Repo, Another Uses That Repo

In Spring Security Servlet, an application can define multiple `SecurityFilterChain` beans:

~~~text
/api/**          --> stateless bearer auth + NullSecurityContextRepository
/web/**          --> form login + session-based repository
/admin/**        --> web session + revalidation/step-up policy
~~~

This is an **architectural diagram**, not default routing. For each chain, verify:

- Which `securityMatcher` actually matches the request.
- Which `formLogin`, `httpBasic`, `oauth2ResourceServer`, or custom filters exist.
- Which repository serves `SecurityContextHolderFilter` and specific authentication filters.
- Whether `SessionCreationPolicy.STATELESS` is applied to the right chain.
- Whether web-issued cookies/sessions can inadvertently bypass stateless API checks.
- Chain ordering: configure order and matchers precisely, avoiding a "catch-all" chain matching first and preventing specialized chains from running.

**Illustrative integration example:**

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

This snippet is not standalone compilable: it requires OAuth2 resource server dependencies and valid issuer/JWK/decoder configuration. It merely illustrates that stateless APIs should not rely on sessions, **not** a complete production resource server.

## 18. Consistency: A Saved Context Can Carry Stale Permissions

A repository can restore a valid `Authentication` from a session created minutes earlier; that **does not guarantee** the user has not been locked, had roles revoked, or changed tenant membership.

| Change in DB / IdP | What Can the Session Context Hold? | Additional Mechanism Needed |
| --- | --- | --- |
| Admin revokes `ROLE_ADMIN` | `Authentication.getAuthorities()` may still contain the old role | Invalidate/revalidate session or check fresh permissions |
| User is disabled | Old session may continue being restored | Account-status recheck, session revocation |
| Password reset due to suspected compromise | Attacker's session may still be active | Logout all sessions, refresh token revocation, audit |
| Username/email changed | `Authentication.getName()` may be the old name | Use a stable userId, refresh profile/session per policy |
| Tenant switched | Tenant claim/authorities in session may be stale | Tenant membership check, context refresh |
| Redis/session store fails | Cannot load context as before | Degraded/failure policy and monitoring; never auto-grant access |

`UserDetails` cache, `SecurityContextRepository`, session store, and JWT introspection are **different layers**. Evicting `UserDetails` does not delete sessions; clearing ThreadLocal does not revoke JWTs. Keep administrative operations and revocation policies cleanly separated.

## 19. How to Test Properly in Spring Security Servlet

### 19.1. Essential Test Cases

1. **After successful login:** the same request sees the right `Authentication`; the response creates a session/cookie per policy.
2. **Subsequent request:** carrying a valid session cookie loads the right identity/authorities without unnecessary password re-verification.
3. **Omitting saveContext in custom login:** the current login request may see auth, yet the next request stays anonymous; this test catches migration bugs.
4. **Without cookie/session:** a new request does not automatically "remember" the principal.
5. **Stateless:** requests with a bearer token authenticate per request; no security context is persisted in HttpSession.
6. **Logout:** clears holder and session; subsequent requests with the old cookie are no longer authenticated.
7. **RequestAttribute:** `ERROR` dispatch retains context when filter mappings and repo are properly configured, whereas independent requests do not.
8. **Early response commit:** login must save before redirect/commit; inspect cookies and the next request.
9. **SessionCreationPolicy.NEVER:** locate the session-creation source when request cache is active.
10. **Concurrent sessions / session fixation:** session ID must change or be protected per the appropriate strategy after login.
11. **Multi-chain:** verify stateless API and web session matchers properly.
12. **Principal serialization:** if using a distributed session store, verify serialize/deserialize and avoid storing huge JPA entity graphs.
13. **Permission revocation:** change DB role or disable user, and verify the next request loses access within policy/SLO.
14. **Async/errors:** proper context propagation, dispatcher types, and holder cleanup.
15. **Store unavailable:** error handling must not fabricate an identity or silently fail open.

### 19.2. MockMvc Must Execute Through the Spring Security Filter Chain

**Sketch** assertion example, not a standalone test (requires Spring Boot test config, beans, seeded users, and Spring Security Test):

~~~java
// These requests must actually pass through SecurityFilterChain.
MvcResult login = mvc.perform(formLogin().user("an").password("correct"))
        .andExpect(authenticated())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) login.getRequest().getSession(false);

mvc.perform(get("/profile").session(session))
        .andExpect(authenticated());

mvc.perform(logout().session(session))
        .andExpect(unauthenticated());
~~~

When using Spring Security Test's `logout()` helper, confirm the exact version API and how the session is attached; reusing an invalidated session after logout may require a new request/simulated cookie instead of passing an invalid session object. **The snippet above only shows test intent**, not a complete JUnit program.

### 19.3. Useful Logs and Metrics

- `context_repository_load` / `save` / `miss` and backend session read latency.
- Count of custom logins that succeed yet leave the next request unauthenticated.
- `HttpSession` created/invalidated, session store errors, and cross-node read failures.
- Frequency of requests carrying a session whose authorities are stale by version.
- Failures saving after response commit, or redirects resulting in missing session cookies.
- Cases where principals fail to serialize.

Keep audit IDs, request IDs, and error types; **never log full contexts, passwords, bearer tokens, or serialized session objects**.

## 20. Quick Diagnosis Table for Common Errors

| Symptom | Likely Cause | Where to Check |
| --- | --- | --- |
| Login API returns 200, next request gets 401 | Only called `SecurityContextHolder.setContext` without `saveContext` | Explicit save, using the right repository/response |
| Session cookie present, still anonymous | Context was never saved, wrong session ID, expired session, or different filter chain | Inspect `SecurityContextRepository` and cookie/session scope |
| Using `NullSecurityContextRepository` yet expecting login persistence | Stateless repo does not save | Choose a session-based flow or send credentials per request |
| Using only RequestAttributeRepository, next request loses login | Request attribute does not survive to a new request | Add HttpSession delegate if stateful is needed |
| `/error` does not see principal | ERROR dispatch does not restore holder or lacks request-attribute repo | Configure dispatcher/filters and matching repo |
| Save called after `sendRedirect`, cookie missing | Response already committed | Save before response commit |
| Both `SecurityContextPersistenceFilter` and `SecurityContextHolderFilter` in chain | Two mechanisms should not run together | Pick one migration path, never configure both |
| Session suddenly created before login | `RequestCache`, another filter, or app calling `getSession` | Trace creation source rather than blaming repository alone |
| Session restores, yet roles are old | `Authentication` is a snapshot and DB changed | Revoke/revalidate authorities per policy |
| Custom authentication creates session without fixation protection | Skipped `SessionAuthenticationStrategy` | Integrate the strategy or use framework login |
| JWT still works after logout | Clearing session does not revoke access tokens | Token revocation/TTL/version/introspection |
| Context lost inside `@Async` | ThreadLocal does not propagate across thread pools automatically | DelegatingSecurityContext executor/propagation |
| Principal A appears in B's request | ThreadLocal not cleared in custom code | `finally clearContext` and inspect filter chain |
| Declared repository bean yet it has no effect | Filters/login use a different repo instance | Configure on HttpSecurity/filter in the right chain |
| `containsContext=true` misread as login still valid | Method only reports whether storage has a context | Check Authentication/trust and current authorization |
| Logout only calls `clearContext` | Session still retains context | Use logout support, invalidate/save empty context |
| Multi-node sessions drop between nodes | Local sessions unsynchronized or inconsistent cookie routing | Spring Session/distributed store and test routing |
| Read-only requests create many unnecessary sessions | Custom code or request cache proactively creating sessions | Measure session creation and use IF_REQUIRED properly |

## 21. Pre-Production Review Checklist

1. **Specify lifecycle requirements:** session-based, stateless, or hybrid; which requests are allowed to create `HttpSession`.
2. **Choose the repository:** default delegating for Servlet sessions where appropriate, `NullSecurityContextRepository` for stateless when intended.
3. **Document the authentication source:** only a trusted `AuthenticationManager`/provider creates authenticated results.
4. **Explicit save:** custom login after authentication must call `setContext` and `saveContext` before commit; do not rely on implicit save in Spring Security 6.
5. **Consistent repository:** filter chain, authentication filters, logout handlers, and custom controllers use compatible repositories.
6. **Session fixation:** every custom login flow must run the relevant strategy; never assume `saveContext` equals complete login security.
7. **Logout:** clear holder, invalidate session, save empty context per policy; handle remember-me/CSRF/tokens separately as needed.
8. **Request vs. session:** request attributes do not cross to new HTTP requests, sessions depend on cookie/id/TTL; Null does not save.
9. **Thread safety:** never store identity in static/global variables; clear ThreadLocal; propagate context to async via standard mechanisms.
10. **Minimal principal:** never store JPA entity graphs, raw credentials, or secrets in sessions; consider serialization and privacy.
11. **Fresh permissions:** session auth can become stale; design revocation/reauth/permission checks.
12. **Multiple chains:** test matchers/ordering and session policies for each API zone.
13. **Response commit:** test redirects, error dispatches, saved requests, and cookies.
14. **Multi-node:** session backing store, TTL, invalidation, object versions, and fail-closed behavior for sensitive operations.
15. **End-to-end tests:** login → new request → logout → new request; stateless, async, error, concurrency, and failure cases.
16. **Operational observability:** load/save/session created/invalidated metrics, never logging raw security contexts.

## 22. Self-Check Knowledge Questions

**1.** Does `SecurityContextHolder.setContext(context)` automatically save the context into the session by default in Spring Security 6?  
**Answer:** No. `SecurityContextHolderFilter` reads/clears, while custom login must save via `SecurityContextRepository.saveContext(context, request, response)` if persistence is desired.

**2.** How do a request-attribute repo and a session repo differ?  
**Answer:** Request attributes live within a single Servlet request (possibly across dispatches), whereas a session spans multiple HTTP requests sharing an unexpired session ID.

**3.** Does `NullSecurityContextRepository` mean requests are not authenticated?  
**Answer:** No. Stateless requests are still authenticated every time via Basic/Bearer or another mechanism; context is simply not saved for reuse via session.

**4.** Why is `containsContext(request)` insufficient to conclude a user is allowed to view `/admin`?  
**Answer:** It only asks whether the repository has a context; it does not check roles, account status, expiry, or current permissions.

**5.** In Spring Security 6, what two delegates does the default `DelegatingSecurityContextRepository` typically combine?  
**Answer:** `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`.

**6.** If a custom controller calls `authenticate(...)` and `saveContext(...)`, has it fully replaced standard form login?  
**Answer:** No. Session fixation protection/`SessionAuthenticationStrategy`, CSRF, success/failure handlers, concurrent sessions, cookies, and other policies remain.

**7.** A user logs out via `SecurityContextHolder.clearContext()`, yet the next request with the old cookie is still authenticated. Why?  
**Answer:** The old context remains in the session/repository; proper logout support or saving an empty context and invalidating the session is required.

**8.** Why do two requests running on two threads not automatically share context via `SecurityContextHolder`?  
**Answer:** By default the holder uses `ThreadLocal`; context is loaded per request from the repository, and async requires configured propagation.

**9.** An API has `SessionCreationPolicy.NEVER`, yet creates a session. What other cause should be checked?  
**Answer:** `RequestCache` storing a saved request, another filter/app calling `getSession`, or another component; not just the auth repository.

**10.** After an admin removes a role, the session still has the old role. Is `SecurityContextRepository` buggy?  
**Answer:** Not necessarily. It stores an authentication snapshot; authorization freshness requires its own refresh/revocation/revalidation strategy.

**11.** Why should you save before redirecting?  
**Answer:** Response commit can prevent setting the session cookie or writing the context in time; explicit save avoids that race.

**12.** An `ERROR` request needs to see the principal even though the holder was just cleared. Which repository helps?  
**Answer:** `RequestAttributeSecurityContextRepository`, provided it is the same Servlet request with matching filter/dispatcher types.

## 23. Official Documentation References

- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): repository customization, saving authentication manually, statelessness, logout, and `requireExplicitSave`.
- [Spring Security 6.5 – Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/servlet/authentication/persistence.html): RequestAttribute, HttpSession, Null, and Delegating repositories; distinguishing HolderFilter/PersistenceFilter.
- [Spring Security 6.5.11 – SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `loadDeferredContext`, `saveContext`, `containsContext`, and legacy `loadContext`.
- [Spring Security 6.5.11 – HttpSessionSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html): session key, session creation policy, and saving empty/anonymous contexts.
- [Spring Security 6.5.11 – RequestAttributeSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html): request attribute/dispatch scope.
- [Spring Security 6.5.11 – DelegatingSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html): delegated load/save.
- [Spring Security 6.5.11 – SecurityContextHolderFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextHolderFilter.html): loading context into holder, cleanup, and explicit save.
- [Spring Security 6.5 – Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): Spring Security 5 implicit save to 6 explicit save and default repository.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContext`, `SecurityContextHolder`, `Authentication`, and filter chain.
- [Spring Security 6.5 – Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): clearing context, sessions, and handlers.
- [Spring Security 6.5 – Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): transferring SecurityContext to other tasks and cleanup.

**Remember:** `SecurityContextHolder` answers **"which identity is the current request/thread using?"**; `SecurityContextRepository` answers **"where is that context loaded from/saved to, and does it survive to another request?"**. In Spring Security 6, **custom authentication must explicitly save** if it needs to persist across requests. `RequestAttribute` serves the same request/dispatch, `HttpSession` serves multiple requests, `Null` does not save, and `Delegating` coordinates scopes. Session context remains a snapshot and never replaces authorization/revocation policies.
