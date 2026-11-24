# DelegatingSecurityContextRepository and Storing SecurityContext Across Multiple Locations

## 1. Why Does a SecurityContext Need to Be Stored in Multiple Locations?

In Spring Security Servlet, `SecurityContext` holds the `Authentication` representing the identity and authorities currently used to process a request. `SecurityContextHolder` allows code running on a thread to access this context. However, a `ThreadLocal` for the current request is **not** durable storage for the next request, nor does it handle every Servlet container dispatch.

To separate **using the current context** from **reading/writing the context to a storage location**, Spring Security provides the `SecurityContextRepository` interface. The `DelegatingSecurityContextRepository` implementation combines multiple repositories in order: on read, it searches the delegates for a context; on save, it forwards the save request to all delegates.

The two typical delegates in a session-based Servlet application are:

- `RequestAttributeSecurityContextRepository`: stores in an attribute of the **`ServletRequest`** so it can be read again within the same request, including appropriate dispatch scenarios.
- `HttpSessionSecurityContextRepository`: stores in **`HttpSession`** so the context can be restored on subsequent HTTP requests belonging to the same session, if application policy permits.

Key idea: **each location addresses a different lifetime scope**. "Storing across multiple locations" here means coordinating context stores within the Servlet lifecycle, not duplicating all user data into multiple databases.

Lesson goals: distinguish `SecurityContextHolder` from `SecurityContextRepository`; explain why request attributes and sessions can be used together; read load/save ordering; understand `SecurityContextHolderFilter` and explicit save; verify context across requests yourself and avoid configurations that drop sessions.

## 2. Four Concepts Not to Mix Up

| Component | Question it answers | Scope / characteristics |
| --- | --- | --- |
| `Authentication` | Who is authenticated, and what authorities do they hold? | Identity/permission object; can be placed inside `SecurityContext`. |
| `SecurityContext` | Which Authentication does the current security context contain? | Can be created fresh, assigned an Authentication, or restored from a repository. |
| `SecurityContextHolder` | How does code on the current execution thread obtain SecurityContext? | Typically uses `ThreadLocal`; must be cleared properly and does not create cross-request persistence itself. |
| `SecurityContextRepository` | Where is SecurityContext found and stored? | Load/restore interface; a repository may be backed by request attributes, HTTP session, or another mechanism. |

For example, a filter that authenticates successfully can create a context and call:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

This is an **excerpt inside a filter/handler that already has `authentication`, `request`, `response`, and `securityContextRepository`**, not a standalone Java class. It shows two distinct actions:

1. `setContext(context)` makes the `Authentication` visible to processing on the current thread.
2. `saveContext(...)` instructs the context store to persist it so downstream steps or future requests can restore it per the configured mechanism.

Performing step 1 alone **does not guarantee** step 2 happens automatically in Spring Security 6.

## 3. SecurityContextRepository and the Load/Save Contract

In Spring Security 6, the repository interface serves these core operations:

- `loadDeferredContext(HttpServletRequest request)`: supplies a `DeferredSecurityContext` so retrieving the context can be deferred until needed. This is the approach used by modern filters.
- `saveContext(SecurityContext context, HttpServletRequest request, HttpServletResponse response)`: writes the context according to repository policy and request/response state.
- `containsContext(HttpServletRequest request)`: checks whether the repository holds a saved context for that request, per the implementation's semantics.

Older APIs such as `loadContext(HttpRequestResponseHolder)` may appear in legacy code or docs for other versions; do not assume every version follows the exact same path.

`DelegatingSecurityContextRepository` can accept multiple `SecurityContextRepository` instances at construction:

```java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
```

This snippet requires imports from `org.springframework.security.web.context` and runs in a Spring Security Servlet environment; it illustrates combining **two storage locations**, without registering itself into the filter chain.

### 3.1. Read Rule: Search for Context in Order

Mental model for `DelegatingSecurityContextRepository` read behavior:

```text
Need to restore SecurityContext
        |
        v
Delegate #1: RequestAttributeSecurityContextRepository
        |
        +-- context present? ---> use this context
        |
        +-- no -----------------> Delegate #2: HttpSessionSecurityContextRepository
                                      |
                                      +-- context present? ---> use this context
                                      |
                                      +-- no -----------------> empty/default context
```

**Delegate order matters for reads.** A context from request attributes takes priority when available—for example, when preserving context for an `ERROR` dispatch within the same request. If a new request has no attribute, the repository can load the context from the session.

This is a behavioral model for learning and does not promise every implementation invokes `loadContext` eagerly each time: modern versions use `DeferredSecurityContext` to optimize lookups and defer loading.

### 3.2. Write Rule: Forward to All Delegates

When `saveContext(context, request, response)` is called on the composite repository, the save operation is forwarded to **every delegate** according to its own logic:

```text
saveContext(context, request, response)
        |
        +--> RequestAttributeSecurityContextRepository.saveContext(...)
        |
        +--> HttpSessionSecurityContextRepository.saveContext(...)
```

Do not treat this as a synchronous database transaction with rollback: each repository has its own rules, and forwarding `saveContext` to delegates **does not guarantee** every store durably writes a copy. For example, `HttpSessionSecurityContextRepository` may skip creating a session or saving an anonymous/empty context depending on policy and current state.

**Mechanism summary:** load prioritizes the first delegate with a matching context; save distributes the request to all delegates. That is why list order is not merely cosmetic.

## 4. The Two Default Delegates and Each One's Practical Problem

### 4.1. RequestAttributeSecurityContextRepository

A Servlet request may pass through multiple dispatch stages such as `REQUEST`, `FORWARD`, `ERROR`, or `ASYNC`, depending on the application and container configuration. In some containers, the active context is cleared from `SecurityContextHolder` between stages. Even so, data attached to `ServletRequest` remains usable within the related request/dispatch scope.

`RequestAttributeSecurityContextRepository` preserves the context in a request attribute so an appropriate dispatch can restore it.

Typical scenario:

```text
REQUEST /orders/123
  |
  +--> authentication succeeds, context is saved
  |
  +--> controller/servlet throws error
  |
  +--> SecurityContextHolder is cleared at processing boundary
  |
  +--> ERROR dispatch to /error (if mapped)
          |
          +--> loads from request attribute
          |
          +--> Authentication info can still be available
```

The diagram depicts **the repository's purpose**. Whether filters run during an `ERROR` dispatch also depends on dispatcher types, filter mappings, and Spring Security configuration; you cannot assume every application automatically executes this exact sequence.

Request attributes **do not span across a new HTTP request**. A user hitting F5 or sending a subsequent GET will not inherently retain attributes from the previous request.

### 4.2. HttpSessionSecurityContextRepository

`HttpSessionSecurityContextRepository` uses `HttpSession` as the storage location, typically under a Spring Security-managed key (such as `SPRING_SECURITY_CONTEXT`). It restores `Authentication` for subsequent HTTP requests belonging to the same session.

```text
Request #1: POST /login succeeds
    |
    +--> SecurityContext is saved to HttpSession
    |
Response carries appropriate session cookie
    |
    v
Request #2: GET /account, sends session cookie back
    |
    +--> session is found
    +--> SecurityContext is restored from session
    +--> endpoint can receive logged-in principal
```

For restoration to succeed, you need **the same valid session**, an unexpired/non-invalidated session, matching persistence configuration, and the client sending the session cookie or identifier in use. The repository **does not re-verify passwords on every request** when loading from the session.

Important notes:

- The repository does not necessarily create a session for anonymous requests or unchanged contexts. Handling depends on session creation policy and `Authentication` state.
- `SessionCreationPolicy.STATELESS` expresses the requirement not to use HTTP sessions to hold `SecurityContext`; in a stateless API application, do not expect session-stored contexts to survive across requests.
- Multi-node applications need a session-sharing or sticky-routing strategy to preserve logins when requests move between nodes; the repository itself does not give every node shared memory.
- Logout, session expiration, session fixation protection, and concurrency control all affect session lifecycle; understanding the repository alone is not enough to design complete session management.

## 5. Why Use Both RequestAttribute and HttpSession?

Suppose an application uses form login and also wants error pages handled with the proper security context.

If you **use only `RequestAttributeSecurityContextRepository`**, a dispatch within the same request can restore the context, but the next HTTP request cannot rely on the old request attribute. Users may lose their login state after a redirect if no other storage exists.

If you **use only `HttpSessionSecurityContextRepository`**, the context can survive across requests, but certain dispatch flows or cases where no session has been created yet may need the context attached directly to the request for consistent restoration within that lifecycle.

Combining both repositories satisfies both needs without forcing filter authors to synchronize context manually between request attributes and sessions.

| Scenario | Request attribute | HTTP session |
| --- | --- | --- |
| Re-reading within the same supported request/dispatch | Can be useful | Usable if session/context is valid |
| New HTTP request using the same session | Old attribute no longer exists | Can load saved context |
| No HTTP session exists | Can store within current request | Cannot read context from a nonexistent session |
| Session expired or logged out | Running request's attribute may last until end of request | Old context no longer available for new requests |
| Stateless API, client sends token every request | Can hold request-internal context | Normally not used to remember logins |

This table describes storage scopes; whether `SecurityContext` is present at a given instant still depends on whether a filter saved it, dispatcher configuration, session policy, and authentication mechanism.

## 6. Who Actually Reads and Saves: SecurityContextHolderFilter and SecurityContextPersistenceFilter

### 6.1. Common Spring Security 6 Mechanism

In modern configurations, `SecurityContextHolderFilter` uses `SecurityContextRepository` to supply the context to `SecurityContextHolder` during request processing, and clears the holder when the appropriate synchronous branch finishes.

```text
SecurityContextHolderFilter
  |
  +--> repository.loadDeferredContext(request)
  |
  +--> SecurityContextHolder holds deferred context
  |
  +--> remaining security filters / endpoint
  |
  +--> clears SecurityContextHolder at the end
```

**Crucial point:** `SecurityContextHolderFilter` **does not automatically call `saveContext` at the end of a request**. Spring Security 6 favors the **explicit save** model: the component modifying `Authentication` must ensure the context is saved when repository persistence is needed.

In standard login mechanisms such as form login, Spring Security's authentication filter typically saves the context after successful authentication. Thus "needing explicit save" does not mean every form-login application must add `saveContext` calls inside controllers.

### 6.2. Difference from SecurityContextPersistenceFilter

In older configurations or compatibility mode, `SecurityContextPersistenceFilter` loaded the context before the request and had a mechanism to auto-save it back to the repository at request end. Even under that model, response commit timing and wrappers still mattered.

Do not put both filters in the chain just to "make sure it saves". When reading code or logs, verify whether the application uses `SecurityContextHolderFilter` or `SecurityContextPersistenceFilter` and which `requireExplicitSave` setting is chosen.

### 6.3. Why Does Save Timing Matter?

Suppose a custom filter authenticates successfully and calls `response.sendRedirect("/profile")` **before** saving the context. The response can be committed, and a new session or rotated session ID cookie may fail to reach the browser. The next request will lack the context even though earlier code populated `SecurityContextHolder` successfully.

Therefore, with custom authentication mechanisms, create a new context, set `Authentication`, **call `saveContext` before completing/committing the response**, and only then redirect or return a success response.

A helpful ordering diagram:

```text
Verify credentials/token
    |
    v
Create new SecurityContext
    |
    v
context.setAuthentication(result)
    |
    v
SecurityContextHolder.setContext(context)
    |
    v
repository.saveContext(context, request, response)
    |
    v
Commit response / redirect
```

Creating a fresh context with `SecurityContextHolder.createEmptyContext()` also avoids mutating an existing context object that might be shared across concurrent requests via the session.

## 7. Configuring DelegatingSecurityContextRepository in Spring Security Servlet

If you want to **declare both delegates explicitly** instead of relying on version defaults, you can define a repository bean and attach it to `HttpSecurity`.

The following example uses Spring Boot 3.3.x / Spring Security 6.x / Java 17. The class is **part of a Spring application** and does not run standalone via `java SecurityConfig`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

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
            SecurityContextRepository securityContextRepository)
            throws Exception {

        http
            .securityContext(security -> security
                .securityContextRepository(securityContextRepository)
                .requireExplicitSave(true))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learning-only"))
                .roles("USER")
                .build()
        );
    }
}
```

Explanation of each choice:

1. `securityContextRepository()` creates one delegate for request attributes and one delegate for HTTP session **in the exact desired read order**.
2. `securityContext(security -> security.securityContextRepository(...))` binds this repository to the chain's security context management.
3. `requireExplicitSave(true)` makes the explicit-save model explicit. The standard login filter handles saving the context after verification; if you write custom login logic, you must save properly.
4. `formLogin` gives the example a login flow using sessions and redirects. Default form login requires a valid CSRF token on POST `/login`.
5. `PasswordEncoder` and `InMemoryUserDetailsManager` create a sample account. This password is **strictly for learning environments**, not real account provisioning.

**Do not also configure `SessionCreationPolicy.STATELESS` in the same example if the goal is demonstrating login persisted via HTTP session.** APIs authenticating bearer tokens on every request follow a different policy and should not mix models.

## 8. Verifying with a Spring Boot Application and MockMvc

This section expands the `SecurityConfig` class above into a minimal application runnable and testable with Java 17 and Maven. The `pom.xml`, application, controller, and test snippets below form one cohesive example.

### 8.1. Structure

```text
context-repository-demo/
  pom.xml
  src/
    main/java/example/security/
      SecurityDemoApplication.java
      SecurityConfig.java
      DemoController.java
    test/java/example/security/
      SecurityContextRepositoryTest.java
```

### 8.2. Maven Configuration

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>context-repository-demo</artifactId>
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

### 8.3. Bootstrap Class

`src/main/java/example/security/SecurityDemoApplication.java`:

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

### 8.4. Public and Login-Required Endpoints

`src/main/java/example/security/DemoController.java`:

```java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

`/private` receives the `Authentication` supplied by security infrastructure after the context is restored. If unauthenticated, `anyRequest().authenticated()` requires login before the controller is called.

### 8.5. Testing Login Request and Subsequent Request in the Same Session

`src/test/java/example/security/SecurityContextRepositoryTest.java`:

```java
package example.security;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextRepositoryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginStoresContextForNextRequestUsingSameSession()
            throws Exception {
        var loginResult = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "learning-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession saved = loginResult.getRequest().getSession(false);
        assertNotNull(saved, "Successful login needs a session");

        MockHttpSession session = (MockHttpSession) saved;

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));
    }

    @Test
    void requestWithoutSessionIsNotAlreadyLoggedIn()
            throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicRequestDoesNotRequireLogin()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

In the login test, the POST includes `csrf()` to provide a valid token per Spring Security Test configuration. After login succeeds, the test retrieves `MockHttpSession` from the first request and passes it to a new `GET /private` request. When persistence/restoration works, the controller sees principal `learner` and returns body `hello learner`.

**Limitations of this test:** it verifies the integrated outcome of the configured repository and form login; it does not directly prove how many times each delegate was called. To verify individual `saveContext` invocations, use a mock/spy or inspect the repository separately. It also does not test per-container `ERROR` dispatch behavior.

Run in the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Maven startup/build messages include timestamps and machine info, so there is no fixed stdout. **The deterministic results to verify are the assertions:** three passing tests; `GET /public` returns 200 with body `public`; `GET /private` before having a session redirects; `GET /private` with the post-login session returns 200 with body `hello learner`.

## 9. Standalone Java 17 Demo to Observe Delegate Read/Write Ordering

Even without running Spring Boot, you can understand composite behavior through a pure Java model. **This code intentionally defines a custom `Store` interface rather than Spring Security implementations**, with `Map` simulating storage; it demonstrates only lookup priority and save distribution, without pretending to simulate full Servlet/session policies.

Create `DelegatingStorageDemo.java`:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class DelegatingStorageDemo {

    record Identity(String username) {}

    static class Request {
        final Map<String, Identity> attributes = new HashMap<>();
        final Map<String, Identity> session;

        Request(Map<String, Identity> session) {
            this.session = session;
        }
    }

    interface Store {
        Optional<Identity> load(Request request);
        void save(Request request, Identity identity);
    }

    static class RequestAttributeStore implements Store {
        public Optional<Identity> load(Request request) {
            return Optional.ofNullable(request.attributes.get("CONTEXT"));
        }

        public void save(Request request, Identity identity) {
            request.attributes.put("CONTEXT", identity);
        }
    }

    static class SessionStore implements Store {
        public Optional<Identity> load(Request request) {
            return Optional.ofNullable(request.session.get("CONTEXT"));
        }

        public void save(Request request, Identity identity) {
            request.session.put("CONTEXT", identity);
        }
    }

    static class DelegatingStore implements Store {
        private final List<Store> delegates;

        DelegatingStore(List<Store> delegates) {
            this.delegates = delegates;
        }

        public Optional<Identity> load(Request request) {
            for (Store delegate : delegates) {
                Optional<Identity> context = delegate.load(request);
                if (context.isPresent()) {
                    return context; // Prioritize first delegate with data.
                }
            }
            return Optional.empty();
        }

        public void save(Request request, Identity identity) {
            for (Store delegate : delegates) {
                delegate.save(request, identity); // Send to every delegate.
            }
        }
    }

    public static void main(String[] args) {
        Map<String, Identity> sharedSession = new HashMap<>();

        Store repository = new DelegatingStore(List.of(
            new RequestAttributeStore(),
            new SessionStore()
        ));

        Request first = new Request(sharedSession);
        repository.save(first, new Identity("linh"));

        System.out.println("first request: "
            + repository.load(first).orElseThrow().username());
        System.out.println("session stored: "
            + sharedSession.containsKey("CONTEXT"));

        Request second = new Request(sharedSession);
        System.out.println("second request attribute: "
            + second.attributes.containsKey("CONTEXT"));
        System.out.println("second request loaded: "
            + repository.load(second).orElseThrow().username());

        second.attributes.put("CONTEXT", new Identity("local"));
        System.out.println("request first priority: "
            + repository.load(second).orElseThrow().username());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac DelegatingStorageDemo.java
java DelegatingStorageDemo
```

**Exact** stdout with JDK 17+:

```text
first request: linh
session stored: true
second request attribute: false
second request loaded: linh
request first priority: local
```

Explanation: `save` on the composite repository writes to both the request attribute and the session map. On the second request, the new request's attribute is empty, so `load` falls through to the session. When another value is deliberately put into the attribute, the repository returns the first delegate with data, yielding `local`.

This simple model **lacks** Spring's anonymous/session-creation policies, deferred contexts, thread-locals, login filters, and cookie/session IDs. That is why it serves to study the delegation algorithm, while MockMvc above verifies real integration.

## 10. Differences from Other Repositories

Several alternatives or complements to recognize:

**`NullSecurityContextRepository`:** does not persist `SecurityContext` between requests via this store. Useful when an application is genuinely stateless and re-authenticates from a bearer token or equivalent mechanism on every request. Do not combine arbitrarily with session-based login requirements.

**`HttpSessionSecurityContextRepository` alone:** serves the session model, without the extra benefit of the request-attribute delegate in dispatch flows that need it.

**`RequestAttributeSecurityContextRepository` alone:** keeps context scoped to the request, insufficient to "remember login" across HTTP requests using request attributes alone.

**`DelegatingSecurityContextRepository` with custom repositories:** can combine multiple stores when genuinely required. In that case, clarify read precedence, save semantics, per-delegate failures, deletion conditions, consistency, and data protection. Never assume stores synchronize transactionally.

Repository type and ordering should reflect runtime needs. Stateless APIs, traditional session apps, and apps handling error dispatches have different requirements.

## 11. Common Mistakes and How to Fix Them

| Symptom | Cause to check | Fix direction |
| --- | --- | --- |
| After custom authentication succeeds, redirecting to a new page loses login | Only `SecurityContextHolder.setContext` was called, missing `saveContext` in explicit-save mode | Create new context, set `Authentication`, save with the chain's active repository **before** committing the response. |
| First GET sees user, next GET is anonymous | No/expired HTTP session, cookie not sent, stateless mode, or request-only repository | Check session policy, session ID/cookie, and repository in the right `SecurityFilterChain`. |
| Error page loses `Authentication` | Request attribute not saved, context cleared between dispatches, or filters not running for `ERROR` | Check dispatcher mappings and `RequestAttributeSecurityContextRepository`; do not assume all `ERROR` dispatches are secured identically. |
| Configured Delegating repository bean, yet behavior did not change | Bean not wired into the selected `SecurityFilterChain`, or multiple chains exist | Check `securityContext(...securityContextRepository(...))` on the matching chain. |
| Login creates a session, yet context is not loaded | Different session used, cookie path/domain mismatch, session invalidated, or context not saved | Verify same session and save/redirect timing. |
| Debugger sees context in ThreadLocal, yet repository is empty | Holder is current execution context, not storage | Distinguish setting context from explicit save. |
| Trying to use session to pass context between worker threads | Repository manages request/session storage, does not propagate ThreadLocal | Use supported propagation mechanisms when needed; never copy thread-locals arbitrarily. |
| Mutating Authentication on a session-loaded context affects other requests | `SecurityContext` is mutable; concurrent requests can share references | Create a fresh context, set `Authentication`, and save per policy instead of mutating shared context. |
| Confusing 401/403 with repository failing to find context | Authentication filters, `AuthorizationFilter`, and exception translation all affect the response | Locate the exact `SecurityFilterChain`/filter and auth event before blaming the repository. |
| Deleting session, yet same request still has context | RequestAttribute delegate has a different scope; holder may still hold context for the current request | Logout must use Spring Security's standard flow to clear the holder, handle context saving/removal, and invalidate the session properly. |

### Caution When Changing Context Storage Configuration

When migrating from session-based to stateless, review the authentication mechanism, CSRF/session policy, security context repository, and logout/session handling together. Swapping one bean is not enough to ensure the application is truly stateless or that all sessions are disabled.

## 12. Load Testing, Race Conditions, and Safety

`SecurityContextHolder` defaults to thread-bound context. The repository reads/writes when called, but **is not a lock manager** for concurrent requests sharing one session. For example, two browser tabs may send requests simultaneously; if both reference the same mutable `SecurityContext` in the session, mutating `Authentication` directly on that context can cause unpredictable behavior.

Safety rules:

1. Use `SecurityContextHolder.createEmptyContext()` when replacing `Authentication`, then `setContext` and `saveContext`, instead of mutating an existing context without considering sharing.
2. Never store sensitive credentials or unsuitable objects in `Authentication`/session; consider serialization if sessions are distributed.
3. Do not manage session cookies manually via string concatenation or log session IDs/tokens.
4. Keep request attributes, HTTP sessions, and thread-locals within their respective lifetimes; these mechanisms solve different problems.
5. If propagation to async tasks is needed, use Spring Security's supported integration for executors/async and ensure context cleanup; repositories do not make contexts appear on arbitrary threads.

## 13. Step-by-Step Debugging When "SecurityContext Disappears"

When a post-login request is no longer authenticated, check:

1. **Right chain?** The login request and resource request may hit different `SecurityFilterChain` beans. Inspect `securityMatcher`, ordering, and the repository attached to each chain.
2. **Who authenticates?** Ensure the authentication mechanism completes and produces a valid `Authentication`, rather than setting arbitrary variables.
3. **Who saves?** With `SecurityContextHolderFilter`, verify the login filter/handler calls `saveContext` on the repository at the right time before response commit.
4. **Where is it saved?** Check whether request attribute and/or session exists per policy. `HttpSessionSecurityContextRepository` does not automatically create a session in every case.
5. **Which session does the next request use?** Is the cookie/ID sent back, does the session still exist, and was there session fixation rotation or logout?
6. **Who loads?** Can the active chain's repository read the `SecurityContext`; is it overwritten by an empty context or custom logic?
7. **Other dispatches?** Are `ERROR`/`FORWARD`/`ASYNC` mapped to filters? Is the holder cleared at processing boundaries?

You can enable development logging:

```properties
logging.level.org.springframework.security=DEBUG
```

DEBUG helps locate chains/filters in many cases, though it does not guarantee logging every internal decision; set breakpoints in the repository/filter when you need exact load/save timing. With real data, avoid printing cookies, session IDs, or credentials to logs.

## 14. Self-Check Questions

**1. The repository stores in two places, so does every new request start with both places holding the context?**

No. Request attributes belong to individual requests. A new request can only restore context from a cross-request store like the session (if a valid session is used), and may subsequently save into the new request's attributes upon a corresponding save.

**2. If the RequestAttribute repository has a different context from the HttpSession repository, which is read first?**

With the constructor order `RequestAttribute` then `HttpSession` as shown, the first delegate takes precedence if it has a context. That is why constructor order matters.

**3. If you only put Authentication into SecurityContextHolder and exit a handler in Spring Security 6, is the login persisted?**

Not guaranteed. Under `SecurityContextHolderFilter` and explicit save, a component must call `saveContext` at the right time. Standard form login already includes the framework's save logic; custom authentication must handle this itself.

**4. Why can a context exist during an ERROR dispatch even though SecurityContextHolder was cleared?**

Because `RequestAttributeSecurityContextRepository` can store the context on `ServletRequest`, allowing restoration in a dispatch belonging to the same request when filter mappings and configuration permit.

**5. Why doesn't forwarding `saveContext` to every delegate guarantee every delegate writes durably?**

Because each delegate applies its own policy. The session repository may skip creating a session or saving unsuitable contexts; request attributes do not survive into a new request. Delegation does not mean a synchronized transaction.

**6. If an application requires statelessness, should you add `HttpSessionSecurityContextRepository` "just to be safe"?**

No. Per-request re-authentication policy, session management, and context repository must align. Adding session persistence can contradict stateless goals.

## 15. Summary of Core Concepts

- `SecurityContextHolder` is how execution code accesses the context; `SecurityContextRepository` is where the context is read and written.
- `DelegatingSecurityContextRepository` **reads in delegate order** and **forwards save calls to every delegate**, each applying its own policy.
- `RequestAttributeSecurityContextRepository` is useful within the same Servlet request/dispatches; `HttpSessionSecurityContextRepository` enables restoration across new requests using the same session.
- `SecurityContextHolderFilter` in the modern model uses deferred loading and does not auto-save at request end; operations changing `Authentication` must save proactively when persistence is desired.
- When authenticating manually, create a fresh context, set `Authentication`, update the holder, and call `saveContext(context, request, response)` **before response commit**; standard framework login filters typically handle saving already.
- To debug lost logins, verify the exact chain, repository, save timing, session/cookie, reload site, and dispatchers rather than looking only at `SecurityContextHolder` at a single instant.
