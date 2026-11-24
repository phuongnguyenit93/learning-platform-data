# HttpSessionSecurityContextRepository and RequestAttributeSecurityContextRepository

## 1. Why Does Spring Security Have to Persist SecurityContext?

In a Servlet-based Spring Security application, a user's authentication result is typically represented by an `Authentication` stored in `SecurityContext`. `SecurityContextHolder` gives code in the current execution access to this context. However, HTTP is a protocol composed of **multiple separate requests**: a login result in request A does not naturally exist in request B unless the application has a mechanism to store and restore it.

Spring Security uses **`SecurityContextRepository`** to define how `SecurityContext` is retrieved and saved. Two implementations with different lifetimes are:

- **`HttpSessionSecurityContextRepository`:** stores `SecurityContext` in `HttpSession`, allowing subsequent requests sending the same session to reuse the authentication result.
- **`RequestAttributeSecurityContextRepository`:** stores `SecurityContext` as an **attribute on the ServletRequest itself** so it can be restored within the **same request** across dispatch types such as `ERROR` or `FORWARD`; the data **does not survive into a new HTTP request**.
- **`DelegatingSecurityContextRepository`:** combines multiple repositories. In the default configuration described by Spring Security 6, it uses both request attribute and HTTP session to serve both needs above.

**Never equate** a `SecurityContextHolder` variable on a thread, a request attribute, and an HTTP session. They are three places with different lifecycles; understanding this difference resolves bugs like "logged in, yet the next request becomes anonymous", "error page cannot see the user", and "disabled session creation, yet the app still creates a session".

This lesson covers the API, lifecycle, configuration in Spring Security 6.5.x, the explicit-save mechanism, a runnable Java 17 example with mock Servlet requests, test scenarios, and security limits.

## 2. Map of Related Components

```text
 HTTP request                          Spring Security filter chain
      |                                          |
      |                                          v
      |                              SecurityContextHolderFilter
      |                              loads SecurityContext when needed
      |                                          |
      |                          SecurityContextRepository.loadDeferredContext
      |                                          |
      |                       +------------------+-----------------+
      |                       |                                    |
      |                       v                                    v
      |         RequestAttributeSecurityContextRepository    HttpSessionSecurityContextRepository
      |         request.setAttribute(...)                     HttpSession.getAttribute(...)
      |         lives within ServletRequest                  can survive across requests
      |                       |                                    |
      |                       +------------------+-----------------+
      |                                          |
      |                                          v
      |                                 SecurityContextHolder
      |                                          |
      |                               Authentication & authorities
      |                                          |
      |                                     Authorization
      |                                          |
      |                         when new auth needs to be saved:
      |                                          |
      |                          SecurityContextRepository.saveContext
      |                                          |
      v                                          v
 response/redirect                     request attr +/or HTTP session
```

Responsibilities to keep separate:

| Component | Function | Should Not Be Mistaken For |
| --- | --- | --- |
| `SecurityContext` | Holds the `Authentication` currently trusted by the system. | A user database or password store. |
| `SecurityContextHolder` | Provides the access point to the active context, typically thread-bound via a strategy. | Persistent login storage between two HTTP requests. |
| `SecurityContextRepository` | Contract for reading/saving context from an appropriate medium. | Verifying username/password itself. |
| `HttpSessionSecurityContextRepository` | Connects the security context with an HTTP session. | Automatically creating sessions on every request or controlling all cookies itself. |
| `RequestAttributeSecurityContextRepository` | Keeps context in a request attribute so it can be read in another dispatch of the same request. | A mechanism to persist login across multiple requests. |
| `DelegatingSecurityContextRepository` | Forwards save operations to delegates and searches for context across delegates. | A distributed cache or merger of multiple distinct identities. |
| `AuthenticationManager`/provider | Verifies credentials and returns an authenticated `Authentication`. | Storage for `SecurityContext`. |
| `SecurityFilterChain` | Organizes filters handling requests, authentication, authorization, and responses. | Synonymous with HTTP session. |

For example, `DaoAuthenticationProvider` may verify passwords accurately, yet if a **custom login controller** forgets to call `saveContext(...)`, the next HTTP call may still fail to find the login result. Conversely, a request already backed by a session containing a context does not need to re-check the password **on every request** just to display the principal.

## 3. The SecurityContextRepository Contract in Spring Security 6

The `org.springframework.security.web.context.SecurityContextRepository` interface has these key APIs:

```java
DeferredSecurityContext loadDeferredContext(
        HttpServletRequest request);

void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);

boolean containsContext(HttpServletRequest request);
```

These are **API-illustrative signatures**, not an interface you create yourself. `HttpServletRequest` and `HttpServletResponse` live in `jakarta.servlet.http` in Spring Security 6.

### `loadDeferredContext(...)`: Load When Actually Needed

This API returns a `DeferredSecurityContext`; the security context may only be fetched from the repository when code calls `get()`. The benefit is avoiding unnecessary session access or object creation in requests that never read the context.

```java
DeferredSecurityContext deferred =
        repository.loadDeferredContext(request);
SecurityContext context = deferred.get();
Authentication auth = context.getAuthentication();
```

This snippet requires a valid repository and request. When no stored context exists, the repository creates/returns **an empty context**, rather than being required to return `null`. `deferred.isGenerated()` can indicate that it was newly created instead of read from an existing context.

Do not confuse `loadDeferredContext` with a "log in" command. Reading a context does not mean the user is authenticated; `context.getAuthentication()` may be `null`, or the existing authentication may represent anonymous, depending on filters and configuration.

### `saveContext(...)`: Intentional Save Operation

```java
repository.saveContext(context, request, response);
```

With the session repository, the result may be written to `HttpSession`; with the request-attribute repository, it is attached to `ServletRequest`. With delegating, the operation is forwarded to multiple delegates per configuration.

**Important note from Spring Security 6:** `SecurityContextHolderFilter` *only loads*; it does not automatically save every change back to the repository at the end of the request. Code that **authenticates users itself** and wants them to remain logged in on the next request must perform an **explicit save** with the appropriate repository. Standard login filters are designed to handle this per their configuration; that does not mean a custom controller may skip it.

### `containsContext(...)` Is a Storage Query

`containsContext(request)` indicates whether the repository currently holds a context for the request. It **does not prove** that credentials were freshly verified, the account is unlocked, the session is unexpired, or the user is authorized for any resource. To make authorization decisions, use the context and appropriate policies.

### Legacy API `loadContext(HttpRequestResponseHolder)`

Many Spring Security 5 blogs and projects use:

```java
SecurityContext context =
        repository.loadContext(new HttpRequestResponseHolder(
                request, response));
```

This is a **legacy/deprecated API** in Spring Security 6.5.11. For new code, prefer `loadDeferredContext(HttpServletRequest)` and `saveContext(...)`. The response wrappers on the old path relate to implicit saving on response commit, so they should not be mechanically copied into a new explicit-save configuration.

## 4. HttpSessionSecurityContextRepository: Persisting Across Requests

`HttpSessionSecurityContextRepository` stores the security context in an `HttpSession`. The default attribute key is the constant:

```java
HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY
```

The key value is commonly known as `"SPRING_SECURITY_CONTEXT"`. A Servlet session differs from an HTTP request: multiple requests from the same browser can reuse the session via a session ID/cookie if the container and application are configured appropriately.

### 4.1. When Reading from Session

Typical flow:

1. An HTTP request arrives at the application, possibly carrying an existing session identifier cookie.
2. The Servlet container resolves that cookie to a valid `HttpSession`, if one exists.
3. The repository reads the attribute holding `SecurityContext` from the session.
4. If the attribute does not exist or is not a valid SecurityContext, an empty context is created.
5. An existing context can be placed into `SecurityContextHolder` by the security filter for the current request.

**Reading does not force session creation.** Under default configuration, the repository uses `getSession(false)` when reading; a guest request with no session will not create a new session solely from this read. Distinguish **the repository not creating a session on read** from other components such as a CSRF token repository, request cache, view layer, or application code that **may** create a session.

### 4.2. When Saving to Session

In Spring Security 6.5, `saveContext(...)` has optimizations/conditions to avoid unnecessary session creation:

- An empty context does not need to create a new session just to store "not logged in".
- Anonymous authentication should not be used to create a session merely because it appeared in the holder.
- For an authenticated context differing from an empty context, the repository may create a session **if configuration allows**.
- When a session already exists, the repository can write the context into that session's attribute.
- `setAllowSessionCreation(false)` prevents **this repository from creating a new session**, but **does not** prevent it from writing into an already-existing session created by another component.

In other words, `HttpSessionSecurityContextRepository` is a mechanism to save context **to a session when justified**, not a command to create a session on every request. Whether a session ends up being created also depends on other parts of the filter chain and application.

### 4.3. Important Setters

```java
HttpSessionSecurityContextRepository repo =
        new HttpSessionSecurityContextRepository();

repo.setAllowSessionCreation(false);
repo.setDisableUrlRewriting(true);
repo.setSpringSecurityContextKey(
        HttpSessionSecurityContextRepository
                .SPRING_SECURITY_CONTEXT_KEY);
```

This snippet can be used in a class that imports the required types. Meanings:

| Setter | Meaning and Limitations |
| --- | --- |
| `setAllowSessionCreation(false)` | The repository will not create a new session just to save; **it can still use an existing session**. |
| `setDisableUrlRewriting(true)` | Prevents appending the session ID to URLs when response wrappers use URL rewriting. |
| `setSpringSecurityContextKey(...)` | Renames the attribute storing the security context; only change when all readers and writers agree. |
| `setTrustResolver(...)` | Customizes how anonymous/remember-me is recognized for save decisions; do not alter without thorough security tests. |
| `setSecurityContextHolderStrategy(...)` | Aligns with the `SecurityContextHolder` strategy if the app uses a custom context strategy. |

**Do not use `setAllowSessionCreation(false)` as a full replacement for `SessionCreationPolicy.STATELESS`.** This flag affects only one repository; stateless authentication also depends on filter chain policies, request cache, CSRF, authentication filters, and other web components.

### 4.4. A Session Is Not Full Identity or Permanent Permissions

A security context stored in a session contains a **snapshot of Authentication/authorities** at authentication time. If an admin revokes a role in the DB, the old session **does not automatically update** roles just because the next request reads the context again. Refresh/revalidation policies, session invalidation, or live state authorization are required when risk demands.

In multi-instance environments, `HttpSession` requires session affinity or an appropriate shared session store, such as Spring Session/Redis with safe serialization; `HttpSessionSecurityContextRepository` **does not create a distributed session database by itself**. Never store lazy-loaded JPA entities/proxies, raw credentials, or arbitrary sensitive object graphs in the principal just because sessions can serialize.

## 5. RequestAttributeSecurityContextRepository: Scoped to One ServletRequest

`RequestAttributeSecurityContextRepository` stores context via `ServletRequest.setAttribute(...)`, under an attribute name managed by the repository. It can be constructed with the default constructor or a custom attribute name:

```java
RequestAttributeSecurityContextRepository repo =
        new RequestAttributeSecurityContextRepository();

// Or a dedicated attribute name controlled by the application:
RequestAttributeSecurityContextRepository named =
        new RequestAttributeSecurityContextRepository(
                "my.application.securityContext");
```

**Core difference:** a request attribute is not a cookie, not a session attribute, and does not extend a login to the next HTTP request. Each new request has its own set of attributes; a browser sending an old session cookie **does not** cause a request attribute from a prior request to reappear.

### 5.1. Why Is This Repository Needed When SecurityContextHolder Already Exists?

In a Servlet application, a single request can traverse multiple **dispatch types**, for example:

- `REQUEST`: initial request intake.
- `FORWARD`: forwarding to another resource/view.
- `ERROR`: container performing an error dispatch when handling a failure.
- Some `ASYNC` scenarios: asynchronous processing under the Servlet lifecycle.

In some containers, `SecurityContextHolder` may already be cleared before an `ERROR` dispatch starts. Relying solely on the current ThreadLocal means the error page does not know which user encountered the error, so it cannot display or enforce principal-based rules as intended.

**RequestAttributeSecurityContextRepository** allows storing the context in a request attribute; when the same ServletRequest is dispatched again and the matching filter chain reads the repository, the context can be restored.

```text
REQUEST /documents/42
   |
   +--> authentication/filter builds SecurityContext for "lan"
   |
   +--> requestRepo.saveContext(context, request, response)
   |
   +--> controller throws exception
   |
   +--> SecurityContextHolder from previous dispatch is cleared
   |
   +--> ERROR dispatch /error  (same ServletRequest/attributes)
             |
             +--> requestRepo.loadDeferredContext(request)
             |
             +--> can retrieve "lan"'s context to handle error view
```

**There is no guarantee** that every Servlet container, filter dispatcher-type configuration, and security policy will run identically to this diagram in every app. The repository provides in-request storage, but the application must still register filters for the appropriate dispatchers and enforce access rules for error/forward pages.

### 5.2. Scope and Accurate Expectations

| Scenario | RequestAttributeSecurityContextRepository |
| --- | --- |
| Same request, other code re-reads saved context | Yes, if the same request attribute still exists. |
| `ERROR` dispatch of the same ServletRequest | Can restore context when filters/dispatches are properly configured. |
| `FORWARD` within the same request | Can restore via the repository if needed. |
| Next request from the same browser | **No**: the new request attribute lacks the old context. |
| Next request sharing the same HTTP session | **Does not automatically use session**. |
| Application restart | No: the request has ended and the attribute is gone. |
| Stateless API | Can be useful for internal dispatches, not for cross-request persistence. |

Do not try to fix "subsequent request becomes anonymous after login" by replacing the session repository with **request attribute only**. That works against the goal: the request-attribute store intentionally **does not** keep state across new requests.

### 5.3. Do Not Hardcode the Attribute Key by Guessing a String

The request attribute is managed by the repository. Instead of calling:

```java
request.setAttribute("SPRING_SECURITY_CONTEXT", context);
```

call:

```java
requestAttributeRepository.saveContext(context, request, response);
```

The string `"SPRING_SECURITY_CONTEXT"` is normally the **key in HttpSessionSecurityContextRepository**; do not assume it is also the default request attribute name. Use the proper API to avoid key mismatches and saving-condition differences across versions.

## 6. Direct Comparison of the Two Repositories

| Characteristic | HttpSessionSecurityContextRepository | RequestAttributeSecurityContextRepository |
| --- | --- | --- |
| Storage location | `HttpSession` attribute | `ServletRequest` attribute |
| Survives across new HTTP requests | **Yes**, if the same valid session is shared and context was saved | **No** |
| Supports ERROR/FORWARD dispatches of same request | Possible depending on session existence/creation and filter config; not its primary goal | **Primary design goal** |
| Requires session cookie | Persisting across requests typically requires a valid session ID/cookie | No |
| Can create HttpSession | Yes, when saving a context that needs persistence and allowSessionCreation=true | Not merely by saving a request attribute |
| Behavior when response is committed | Session requires proper timing for save/cookie/response | Request attribute does not depend on cookies/response commit for same-request use |
| Durability across server restarts | Depends on session infrastructure | No |
| Typical use | Server-side session-based login | Preserving context across internal dispatches, including error pages |
| Confusion risks | Session fixation, stale authorities, session replication, serialization | Thinking it is a long-term login mechanism, forgetting filter for ERROR dispatch |

**Neither choice is automatically "stronger" in security for all systems.** Which repository to use depends on the authentication model (session-backed vs. per-request), availability, and servlet dispatch requirements.

## 7. DelegatingSecurityContextRepository: Combining Both Scopes

Spring Security 6 documentation describes the default repository as a **`DelegatingSecurityContextRepository`** with two components:

```java
SecurityContextRepository repo =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
```

When `saveContext` is called, the composite repository forwards the save to its delegates. When reading, it searches delegates in configured order and uses the available matching context. With the order above:

1. Same request that just created authentication: request attribute conveniently keeps context for dispatchers.
2. Next HTTP request from the same session: the new request attribute is empty, and the session repo supplies the context saved during the login request.
3. If one delegate has no context, that does not mean the overall request has no context: another repository can still return a result.

A two-request diagram:

```text
POST /login (request A)
   |
   +-- saveContext(authenticated "lan")
   |          |
   |          +--> request A attribute = context("lan")
   |          +--> HttpSession S1       = context("lan")
   |
   +-- response Set-Cookie: JSESSIONID=... (by Servlet container if needed)

GET /private (request B, same session S1)
   |
   +-- request B attribute: none yet
   +-- HttpSession S1:       has context("lan")
   |
   +-- DelegatingSecurityContextRepository loads context("lan")
```

**Important:** sending and receiving a session cookie depends on the container, security config, session management, and HTTP response. Looking only at the repository save call cannot prove the browser definitely received the cookie or that session fixation protection ran.

### Why Does the Request Repo Usually Precede the Session Repo?

Request attributes take priority for **context belonging to the current dispatch**, and the session repo adds cross-HTTP-request persistence. If code saved a new context within the request (for instance, authentication changed on the current request), prioritizing the request repo prevents subsequent dispatches from accidentally falling back to stale session state. Still, concrete outcomes depend on contract and implementation testing, especially if an app customizes multiple delegates.

### SecurityFilterChain Configuration

The following is a **snippet inside a `@Configuration` class**, assuming Spring Security Servlet dependencies are present:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    SecurityContextRepository repository =
            new DelegatingSecurityContextRepository(
                    new RequestAttributeSecurityContextRepository(),
                    new HttpSessionSecurityContextRepository());

    http
        .securityContext(security -> security
            .securityContextRepository(repository)
            .requireExplicitSave(true))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

Imports for `Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and the corresponding repositories are required. This snippet **does not run standalone**: it still needs `@SpringBootApplication`, a user source/`AuthenticationManager`, controllers, and appropriate security policies. Spring Security 6 already provides the combined repository by default; declaring it explicitly like this is mainly useful when modifying, demonstrating, or tightly controlling a filter chain.

**Do not blindly apply `anyRequest().authenticated()` to `/error`, health, static assets, or public APIs without evaluating dispatcher types and desired access rules.** Production configs must distinguish paths and dispatch types.

## 8. Java 17 Runnable Demo: Request Attribute, Session, and Delegating

The following example uses **Spring Security Web 6.5.11**, **Spring Framework 6.2.12 test mocks**, Java 17+, and Gradle. The console program invokes the repositories directly with `MockHttpServletRequest`/`MockHttpServletResponse`, so **no web server, DB, or controller is needed**. It proves the exact storage scope of each repository.

The demo **does not verify passwords**. `Authentication` is pre-built with `UsernamePasswordAuthenticationToken.authenticated(...)` solely to focus on the repository API. In real applications, only a trusted provider/`AuthenticationManager` may determine an authenticated identity; **never take a username from an HTTP request and call the authenticated factory to self-authenticate**.

### 8.1. Project Structure

```text
security-context-repository-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── RepositoryScopeDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'security-context-repository-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.RepositoryScopeDemo'
}
```

Spring Security Web transitively brings in the appropriate core/context dependencies; `spring-test` supplies the Servlet mocks. The versions here are a **chosen illustrative combination** to inspect specific APIs; in real Spring Boot projects, let Boot's dependency management/BOM supply aligned versions instead of pinning individual libraries from a demo.

### 8.2. File `src/main/java/demo/RepositoryScopeDemo.java`

```java
package demo;

import jakarta.servlet.http.HttpSession;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

public final class RepositoryScopeDemo {

    private static SecurityContext userContext(String username) {
        // Demo ONLY: never construct an authenticated token
        // from HTTP data not verified by AuthenticationManager.
        Authentication authenticated =
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        null,
                        AuthorityUtils.createAuthorityList("ROLE_READER"));

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        return context;
    }

    private static String username(SecurityContext context) {
        return context.getAuthentication() == null
                ? "(none)"
                : context.getAuthentication().getName();
    }

    public static void main(String[] args) {

        // A. Request attribute: holds context only on the same request object.
        RequestAttributeSecurityContextRepository requestRepo =
                new RequestAttributeSecurityContextRepository();

        MockHttpServletRequest requestA = new MockHttpServletRequest();
        MockHttpServletResponse responseA = new MockHttpServletResponse();

        System.out.println("request.before="
                + requestRepo.containsContext(requestA));

        requestRepo.saveContext(userContext("lan"), requestA, responseA);
        SecurityContextHolder.clearContext();

        System.out.println("request.saved="
                + requestRepo.containsContext(requestA));
        System.out.println("request.sameRequestUser="
                + username(requestRepo.loadDeferredContext(requestA).get()));
        System.out.println("request.createdSession="
                + (requestA.getSession(false) != null));

        MockHttpServletRequest requestB = new MockHttpServletRequest();
        System.out.println("request.nextRequestHasContext="
                + requestRepo.containsContext(requestB));

        // B. HttpSession: does not automatically create a session on load only.
        HttpSessionSecurityContextRepository sessionRepo =
                new HttpSessionSecurityContextRepository();

        MockHttpServletRequest readOnly = new MockHttpServletRequest();
        sessionRepo.loadDeferredContext(readOnly).get();

        System.out.println("session.loadCreatedSession="
                + (readOnly.getSession(false) != null));

        MockHttpServletRequest loginRequest = new MockHttpServletRequest();
        MockHttpServletResponse loginResponse =
                new MockHttpServletResponse();

        sessionRepo.saveContext(userContext("lan"),
                loginRequest, loginResponse);

        HttpSession session = loginRequest.getSession(false);
        System.out.println("session.createdAfterSave=" + (session != null));

        MockHttpServletRequest nextRequest = new MockHttpServletRequest();
        nextRequest.setSession(session);

        System.out.println("session.nextRequestUser="
                + username(sessionRepo.loadDeferredContext(nextRequest).get()));

        // C. Disallow repository session creation; a request without a session
        // cannot retain Authentication via HttpSession repo.
        HttpSessionSecurityContextRepository noCreate =
                new HttpSessionSecurityContextRepository();
        noCreate.setAllowSessionCreation(false);

        MockHttpServletRequest noSessionRequest =
                new MockHttpServletRequest();
        noCreate.saveContext(userContext("lan"), noSessionRequest,
                new MockHttpServletResponse());

        System.out.println("session.noCreateFlagHonored="
                + (noSessionRequest.getSession(false) == null));

        // D. Delegating repository: saves request attr and session.
        SecurityContextRepository both =
                new DelegatingSecurityContextRepository(
                        new RequestAttributeSecurityContextRepository(),
                        new HttpSessionSecurityContextRepository());

        MockHttpServletRequest current = new MockHttpServletRequest();
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        both.saveContext(userContext("mai"), current, response);

        System.out.println("both.currentRequestHasContext="
                + both.containsContext(current));

        MockHttpServletRequest later = new MockHttpServletRequest();
        later.setSession(current.getSession(false));

        System.out.println("both.nextRequestUser="
                + username(both.loadDeferredContext(later).get()));

        MockHttpServletRequest unrelated = new MockHttpServletRequest();
        System.out.println("both.unrelatedRequestHasContext="
                + both.containsContext(unrelated));

        // E. Null repo: does not store SecurityContext at all.
        SecurityContextRepository none = new NullSecurityContextRepository();
        MockHttpServletRequest noStore = new MockHttpServletRequest();
        none.saveContext(userContext("lan"), noStore,
                new MockHttpServletResponse());
        System.out.println("null.repoHasContext="
                + none.containsContext(noStore));

        SecurityContextHolder.clearContext();
    }
}
```

### 8.3. Running and Expected Stdout

With JDK 17+ and Gradle/Gradle Wrapper supporting Java 17, from the project directory:

```bash
gradle run --quiet
```

Lines printed by the **program**, excluding Gradle and library logs:

```text
request.before=false
request.saved=true
request.sameRequestUser=lan
request.createdSession=false
request.nextRequestHasContext=false
session.loadCreatedSession=false
session.createdAfterSave=true
session.nextRequestUser=lan
session.noCreateFlagHonored=true
both.currentRequestHasContext=true
both.nextRequestUser=mai
both.unrelatedRequestHasContext=false
null.repoHasContext=false
```

### 8.4. Explaining the Output Groups

**Request group:** `saveContext(...)` writes the context onto request A. Re-reading the same request still sees `lan` even after `SecurityContextHolder.clearContext()` was called; that is the difference between context in ThreadLocal and context stored in a request attribute. Request B is a new object lacking A's attribute, so `containsContext` returns false. Saving a request attribute **does not create an HttpSession**.

**Session group:** `loadDeferredContext(...).get()` on a request with no session does not automatically create one. After `saveContext` with authenticated `lan`, a session is created under `allowSessionCreation=true`. When another request uses the same `HttpSession`, the repository reads back that context and gets principal `lan`. A real browser would need to send a valid session ID across requests, while the demo transfers `HttpSession` directly between two mock requests to simulate container cookie resolution.

**No-create group:** `setAllowSessionCreation(false)` prevents the repository from creating a new session. It **does not** mean other Servlet components are forbidden from creating sessions, and if a session already exists, the repo can still use it.

**Delegating group:** a single `saveContext` writes to both request attribute and session. The next request reusing the session still sees `mai`, whereas a completely unrelated request has no context. This is why the two repositories are commonly paired together.

**Null group:** `NullSecurityContextRepository` skips saving; it often fits stateless authentication flows, though it does not by itself dictate the entire `SessionCreationPolicy` or the behavior of every other filter.

**Limitations:** the demo only invokes repositories directly; it does not test password login, real HTTP sessions, redirect responses, session fixation defense, container `ERROR` dispatches, CSRF, or authorization. To test the full filter chain, use integration tests and real HTTP configuration (Section 12).

## 9. SecurityContextHolderFilter and "Explicit Save" in Spring Security 6

This is the most important part when building custom login.

### 9.1. Before and Now

In many Spring Security 5 configurations, `SecurityContextPersistenceFilter` read the context at the start of the request and persisted changes when needed as the request/response completed. That mechanism was complex because the filter had to detect mutations and save before the HTTP response committed.

In Spring Security 6, the default configuration relies on **`SecurityContextHolderFilter`**, which is responsible for **loading**, while code that produces a new authentication must **explicitly save the context** when persistence is desired.

```text
SecurityContextHolderFilter
  |
  +--> repository.loadDeferredContext(request)
  +--> supplies context to SecurityContextHolder
  |
  +--> filter/controller code
  |      |
  |      +--> AuthenticationManager.authenticate(...)
  |      +--> create new SecurityContext
  |      +--> SecurityContextHolder.setContext(context)
  |      +--> repository.saveContext(context, request, response)  <-- IMPORTANT
  |
  +--> when request/dispatch ends, holder is cleared per filter lifecycle
```

**`SecurityContextHolder.setContext(context)` does not automatically persist to the session for the next request.** This is a common cause of the custom-login bug "POST /login OK, GET /me is anonymous again".

### 9.2. Custom Login Pattern with Proper Boundaries

The following is a **service/controller snippet**, not a complete controller with CSRF/session-strategy/rate-limiting. It illustrates the exact order **authenticate → new context → set → save**.

```java
public void finishLogin(
        String username,
        String rawPassword,
        HttpServletRequest request,
        HttpServletResponse response) {

    Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    username, rawPassword);

    Authentication verified =
            authenticationManager.authenticate(input);

    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(verified);

    SecurityContextHolder.setContext(context);
    securityContextRepository.saveContext(context, request, response);
}
```

Assumes `authenticationManager` and `securityContextRepository` are injected from trusted configuration. Only invoke this code **after** authentication succeeds; never build an authenticated token from a client-supplied username yourself.

**Production warning:** writing a login endpoint yourself also requires applying `SessionAuthenticationStrategy` (e.g., session fixation protection), CSRF when using sessions/cookies, failure handling, protecting credentials in requests/logs, login rate limits, and appropriate responses. It is usually better to use standard authentication filters or implement a thoroughly tested custom mechanism rather than copying just four set/save lines.

### 9.3. Why Must You Save Before the Response Commits?

Once a response is committed, the application may no longer have the chance to send the cookie carrying the new session ID or modify required headers. If code creates a new context but only tries to save after `sendRedirect(...)` or after the body flushes, the next request may arrive **before the session is validly written** or without the cookie being sent.

Dangerous pattern:

```java
// Do not save too late:
response.sendRedirect("/home");
securityContextRepository.saveContext(context, request, response);
```

Target pattern:

```java
securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/home");
```

Both snippets illustrate ordering only and are not complete for transactions, session fixation, or exception handling. When using standard filters, let the filter manage saving and redirecting via supported mechanisms.

### 9.4. Do Not Run Both Context Filters

Spring Security 6 documentation recommends an application use **only one of** `SecurityContextHolderFilter` or `SecurityContextPersistenceFilter`, never both simultaneously. Toggling `requireExplicitSave` as a "quick patch" without understanding the flow can cause redundant saves, unpredictable session-update timing, and increased risk at response commit.

## 10. SessionCreationPolicy Is Not Synonymous with a Single Repository

In `HttpSecurity.sessionManagement(...)`, common policies are:

| Policy | Main Meaning | Key Consideration |
| --- | --- | --- |
| `ALWAYS` | Spring Security proactively creates a session. | Should not be used merely to keep context if defaults suffice. |
| `IF_REQUIRED` | Creates a session only when needed. | Usually suits session-backed login. |
| `NEVER` | Spring Security does not create a new session, but may use an existing one. | Does not mean completely stateless; other components may still create sessions. |
| `STATELESS` | Spring Security neither creates nor uses HttpSession to obtain SecurityContext for stateless authentication. | Other filters/integrations must still be checked, and request attributes may still play a role in dispatches. |

**Distinguish carefully:**

- `setAllowSessionCreation(false)` is a property of **a single HttpSessionSecurityContextRepository instance**.
- `SessionCreationPolicy.STATELESS` is a **security configuration choice** affecting session management and related repositories/filters.
- `NullSecurityContextRepository` is a **non-saving** implementation; using it alone does not forbid controllers or other libraries from creating sessions.
- `RequestAttributeSecurityContextRepository` can still help keep context within a current dispatch even when persistence to the next request is **not** desired.

**Do not build a supposedly stateless token/JWT API that accidentally puts authentication into HttpSession** because a custom filter used the session repository. Conversely, **do not switch an entire form-login app to the Null repo** and wonder why login does not persist to the next request.

### Illustrative Configuration for a Stateless API

```java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

This is an **illustrative snippet**, not a complete production template: you must determine API type, CSRF, authentication mechanism, CORS, paths, and error handlers. HTTP Basic sends credentials on every request so it does not require a session; for bearer tokens/JWTs, authentication and filters differ. Not seeing a session in a single test does not prove no production endpoint ever creates a session.

## 11. ERROR/FORWARD Dispatches: Practical Benefits and Configuration Needed

Some errors only surface when a controller throws an exception or the container forwards the request to an error page:

```text
GET /invoice/42
  |
  +-- security filter loads context for user "lan"
  +-- controller throws exception
  +-- holder may be cleared when prior dispatch ends
  +-- container dispatches /error within the same ServletRequest
  +-- page needs current principal
```

Relying solely on ThreadLocal means a cleared context can cause the error page to see anonymous. `RequestAttributeSecurityContextRepository` stores the security context right on the request; when the filter on the next dispatcher loads from the repository, it can restore the context.

However, distinguish carefully:

1. **Saving context:** `RequestAttributeSecurityContextRepository.saveContext(...)` must have been called when needed. If the attribute was never saved, there is nothing to restore.
2. **Running the filter:** `springSecurityFilterChain` must be registered for the desired dispatcher types. Boot/Servlet containers vary in defaults; verify empirically.
3. **Authorization for the error page:** `/error` and dispatcher type `ERROR` may be subject to separate authorization rules; if rules are too strict, the error request can be blocked a second time.
4. **What context is shown:** error pages should only inspect principal fields permitted to be exposed, never dumping `Authentication` or sessions to clients.
5. **Whether the ServletRequest is truly the same request:** request attributes do not survive across a new HTTP request, even with the same URL or cookie.

An illustrative policy permitting error dispatch handling:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .anyRequest().authenticated())
```

This is a **DSL fragment**, requiring `jakarta.servlet.DispatcherType` to be imported and wired into real HTTP configuration. **`permitAll` for ERROR dispatches does not mean you can skip data access controls**: error pages must protect sensitive content and only display data per defined policy.

### Async and ThreadLocal Are a Different Problem

`SecurityContextHolder` uses ThreadLocal under the default strategy; an `@Async` task or app-spawned thread **does not automatically inherit the same context as the initial web thread**. `RequestAttributeSecurityContextRepository` keeps context on the request object, but does not propagate ThreadLocal to arbitrary threads. If context is needed inside an async task, use an appropriate propagation mechanism such as `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` or Spring Security's supported integrations; ensure old request context is not retained beyond the allowed scope.

## 12. Testing the Two Lifecycles Separately

### 12.1. Repository-Level Unit/Integration Tests

Direct tests using `MockHttpServletRequest` should verify:

| Case | Repository | Expectation |
| --- | --- | --- |
| Before save | RequestAttribute | `containsContext(request) == false`. |
| Saved on request A | RequestAttribute | Loading on A sees the saved principal. |
| Request B is a new object | RequestAttribute | Does not see A's context. |
| Read from request without session | HttpSession | Does not auto-create session just from loading context. |
| Save authenticated context | HttpSession | Can create a session when `allowSessionCreation=true`. |
| Request B uses same session | HttpSession | Reads back the saved authentication. |
| No session + allowSessionCreation=false | HttpSession | Repository does not create a new session. |
| Existing session + allowSessionCreation=false | HttpSession | Can still save into the existing session. |
| Save to delegating | Request + Session | Both delegates receive context per design. |
| New request with session but no attribute | Delegating | Retrieves context from session delegate. |
| New request without session | Delegating | Does not automatically get old authentication. |
| Save to Null repository | Null | No context persistence. |

### 12.2. Testing Real Servlet Dispatches

Direct mocked calls **are not enough** to prove the app behaves identically across all containers. When testing `ERROR`/`FORWARD`:

- Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` or a real integration setup with the filter chain.
- Create an endpoint simulating an error after authentication.
- Confirm the request attribute was saved within the same request before the error dispatch, per the chosen login/filter mechanism.
- Verify the controller/error handler sees the right principal when the dispatcher type is `ERROR`.
- Verify error-page authorization rules and confirm no sensitive data leaks.
- Compare behavior with request-only, session-only, and delegating repositories.
- Test unauthenticated users: public error page per policy, no fake principal.
- If multiple filter chains exist, verify the right chain's repository handles the URL.

**Do not rely solely on `@WithMockUser` to conclude cross-request login persistence works.** Mock users usually populate the security context for a test without actually invoking the authentication manager, issuing session cookies, or saving to a repository. It is useful for authorization tests, not for proving real login paths and persistence.

### 12.3. Testing with Real Sessions

For a session-backed app with form login:

1. First unauthenticated request accesses a protected page; redirected/routed to login per policy.
2. Client submits valid password and matching CSRF token.
3. Framework performs authentication, session fixation protection, and saves context before redirecting.
4. Next request sends the new session cookie; reads principal and authorities.
5. Requests without a cookie or after logout receive unauthenticated/anonymous behavior.
6. After session expiry/invalidation, the old context is no longer restored.
7. If scaling across nodes, test session store/replication and serialization.
8. If an admin locks an account, verify the invalidation or revalidation strategy rather than assuming sessions reflect DB changes automatically.

**Note:** asserting specific HTTP 302/401/403 codes depends on form login/Basic configuration and exception handling; do not test repositories alone and assume HTTP statuses.

## 13. Coordinating Logout, Session Fixation, and Cookies

`HttpSessionSecurityContextRepository` **is not the only component** handling these aspects. When using session-backed authentication, the overall configuration must include:

- **Session fixation protection:** after successful login, the container/framework typically changes the session ID under the appropriate strategy. Custom login must not skip `SessionAuthenticationStrategy` just because it called `saveContext`.
- **Secure cookies:** `HttpOnly`, `Secure` when using HTTPS, appropriate `SameSite`, cookie scope, and TTL as required; configure at the servlet container/proxy/session store level.
- **CSRF defense:** form login and state-changing requests relying on cookies/sessions require CSRF protection; `SecurityContextRepository` does not replace CSRF protection.
- **Logout:** properly invalidate or update the session and context per configuration; do not merely clear `SecurityContextHolder` on the thread and consider the old session revoked.
- **Session lifetime:** invalidation, inactivity timeout, and concurrent-login controls if needed.
- **URL session ID:** avoid `;jsessionid` in URLs to reduce ID exposure via logs, referrers, and browser history; use servlet config and `setDisableUrlRewriting` where appropriate.

### Why Is Clearing ThreadLocal Not Enough for Logout?

A controller that only calls:

```java
SecurityContextHolder.clearContext();
```

clears the thread's current context. **If `HttpSession` still holds an authenticated security context**, the next request with the same session can still reload it. Spring Security's standard logout mechanism must handle clearing/invalidating the session, context, remember-me, and related cookies per policy.

With a delegating repository, logout/custom clearing must also consider the request attribute saved on the current dispatch. Never save an old context after logout and expect it not to be restored. It is best to let framework-supported logout handlers perform cleanup, then test both the **same request** and the **next request**.

## 14. Common Configuration Pitfalls

1. **"`SecurityContextHolder` is cross-request storage."** Wrong: ThreadLocal/strategy binds to the current execution context; persistence needs a repository.
2. **"`RequestAttributeSecurityContextRepository` keeps login until tomorrow."** Wrong: only within the same ServletRequest.
3. **"`HttpSessionSecurityContextRepository` creates a session immediately on load."** By default it does not need to create a session just to read.
4. **"`setAllowSessionCreation(false)` makes the entire app stateless."** Wrong: the repository still uses an existing session; other components can create sessions.
5. **"Saving to request attribute automatically saves to session."** No, unless you use delegating or explicitly save to the session repo.
6. **"Saving to session is guaranteed to restore during ERROR dispatches in every case."** Not every container/filter setup preserves the holder; the request repo complements dispatches.
7. **"Spring Security 6 auto-saves any change to the holder."** With `SecurityContextHolderFilter`, explicit save is required for persistence; standard login filters handle their own saving.
8. **"`containsContext=true` means the current user still has permissions."** No; it can be an old snapshot requiring a revalidation policy.
9. **"Authenticated in a custom controller means `saveContext` is unnecessary."** Wrong if session-backed login is wanted on the next request.
10. **"Changing `setSpringSecurityContextKey` needs no coordination."** If readers use the old key, the session will appear to lack a context.
11. **"Using `NullSecurityContextRepository` always means no cookies exist."** No: other app code/containers can still create cookies/sessions.
12. **"For stateful login, just copy the authenticated token example."** No: trusted tokens must come from AuthenticationManager/providers, not a raw client username.
13. **"Request attributes survive in a background job running tomorrow."** No, and ThreadLocal security context does not automatically pass to arbitrary worker threads.
14. **"Session context is a live Hibernate entity."** Principals may be serialized without a transaction; avoid holding ORM proxies/lazy associations.
15. **"Changing roles in the DB updates the session automatically."** No; refresh or revocation is required.
16. **"Skipping session ID rotation after login is fine because the repository saved."** Session fixation defense is a separate, critical responsibility.
17. **"Saving after a committed redirect always succeeds."** No; session cookies/headers may no longer be sendable.
18. **"Registering both context filters is safer."** Spring Security 6 recommends using only one of HolderFilter/PersistenceFilter.
19. **"Delegating means multiple login sessions merge their permissions."** Delegating selects where context is stored/read, not merging authorities across identities.
20. **"Using request repo instead of session repo increases security by default."** It changes semantics; session-backed login will be lost.
21. **"Testing only `@WithMockUser` is enough to verify persistence."** It does not exercise request cookies or real login repository persistence.
22. **"Session cookies are entirely SecurityContextRepository's responsibility."** Cookie ID generation and decoding are primarily handled by the Servlet container/session infrastructure.
23. **"Distributed session backends are created automatically by the repository."** No; supporting infrastructure and configuration are required.
24. **"Anonymous state must be saved to session for every guest."** Default session repository optimizes to avoid saving empty/anonymous contexts needlessly.
25. **"If `/error` is denied, turn off all authorization."** Authorize dispatchers/error pages properly without exposing other data.

## 15. Self-Check Questions

**Question 1.** How do these two repositories differ most in storage scope?

**Answer:** `HttpSessionSecurityContextRepository` uses `HttpSession` and can restore across HTTP requests sharing a session. `RequestAttributeSecurityContextRepository` stores in an attribute of a single ServletRequest, useful across dispatches within that request, but does not survive into a new request.

**Question 2.** Why is the request repo useful for `ERROR` dispatches?

**Answer:** The Servlet container may perform an error dispatch after `SecurityContextHolder` was cleared from the earlier dispatch; the request attribute can still exist on the same ServletRequest, letting filters/repositories reload the context.

**Question 3.** Does `SecurityContextHolderFilter` automatically save context after a custom controller calls `setContext`?

**Answer:** No. Under explicit save, custom authentication mechanisms must call `SecurityContextRepository.saveContext(context, request, response)` if cross-request persistence is desired.

**Question 4.** A guest request reads `HttpSessionSecurityContextRepository.loadDeferredContext(...).get()`. Is a new session guaranteed to be created?

**Answer:** No. The repository can return an empty context without creating a session on read only.

**Question 5.** Does `setAllowSessionCreation(false)` stop the repository from reading/writing an already-existing session?

**Answer:** No. It prevents this repository from creating a new session; an already-existing session can still be used.

**Question 6.** If only the request repo is used for session-backed form login, what happens on the next request?

**Answer:** The login request's attribute does not exist on the new request; authentication is not restored. A session repository or another appropriate persistence mechanism is needed.

**Question 7.** Why is DelegatingSecurityContextRepository commonly used?

**Answer:** It combines request attributes for the same ServletRequest/dispatch with HttpSession to preserve login across new requests, serving two distinct needs.

**Question 8.** After logout, is calling only `SecurityContextHolder.clearContext()` sufficient?

**Answer:** Not if the session still contains authentication; a new request can reload the context. Session/repository/logout handlers must be executed per policy.

**Question 9.** If an admin revokes `ROLE_ADMIN` in the DB, does a user with an active session lose the role immediately?

**Answer:** Do not assume so. Sessions typically hold an Authentication snapshot; a revalidation, invalidation, or live-data authorization strategy is needed.

**Question 10.** A custom controller called `saveContext`, yet subsequent requests are still not logged in. What should be checked?

**Answer:** Whether the repository used is truly session/delegating; whether save ran before response commit; whether a valid session was created; whether the cookie/session ID was sent and returned; whether the filter chain uses the same repository/key; and whether session fixation/CSRF/session store are handled properly.

**Question 11.** In a stateless API, what does `NullSecurityContextRepository` mean?

**Answer:** The repository itself does not store context. It does not by itself forbid the entire application from creating sessions or guarantee no other filter uses sessions.

**Question 12.** Why shouldn't `UsernamePasswordAuthenticationToken.authenticated(...)` be called directly with a username from the login body to create context?

**Answer:** That creates a token marked authenticated without ever proving credentials. Client data must be verified via AuthenticationManager/providers; in the demo, that factory merely simulated a trusted authentication to examine repositories.

**Question 13.** How do `loadContext(HttpRequestResponseHolder)` and `loadDeferredContext(request)` differ in the 6.5 API?

**Answer:** `loadContext` is the legacy/deprecated API tied to request/response wrappers for implicit saving, whereas `loadDeferredContext` is the preferred interface to load context lazily under the modern model.

**Question 14.** Does replacing `SessionCreationPolicy.IF_REQUIRED` with `STATELESS` guarantee an API still keeps login sessions as before?

**Answer:** No. Stateless changes the goal of using sessions to store authentication; for session-based login, choose the corresponding policy/repository and test it.

## 16. Official Documentation

- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository`, `NullSecurityContextRepository`, and filter/save diagrams.
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explicit save, custom authentication, session management, and `SecurityContextHolderFilter`.
- [Spring Security 6.5.11 — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html): session key, session creation conditions, and setters.
- [Spring Security 6.5.11 — RequestAttributeSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html): request-scoped persistence across dispatches, constructors, and `loadDeferredContext`.
- [Spring Security 6.5.11 — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html): composite repository, save/contains/deferred load.
- [Spring Security 6.5.11 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): context read/save contract.
- [Spring Framework 6.2 — MockHttpServletRequest API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/mock/web/MockHttpServletRequest.html): mock Servlet request and `setSession(HttpSession)` used in the example.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): relationship among `AuthenticationManager`, providers, and `SecurityContextHolder`.

**Conclusion:** `HttpSessionSecurityContextRepository` keeps `SecurityContext` **across multiple HTTP requests sharing a session**; `RequestAttributeSecurityContextRepository` keeps context **within a single ServletRequest, including internal dispatches**. `DelegatingSecurityContextRepository` combines both scopes and is the common default in Spring Security 6. When implementing authentication yourself, always separate **verify credentials → create context → save to the right repository**, understand explicit save and response-commit timing, and test the current request, subsequent requests, and real `ERROR` dispatches.