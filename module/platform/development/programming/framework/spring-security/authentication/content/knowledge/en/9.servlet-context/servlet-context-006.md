# DelegatingSecurityContextRepository: Combining Storage Locations

## Overview

In Spring Security Servlet, `SecurityContext` holds the `Authentication` for the request currently being processed. The challenge is that this context may need to be restored across **two different time scopes**:

1. **Within the same servlet request:** the container transitions to `FORWARD`, `ERROR`, or another dispatch; the `SecurityContextHolder` from the prior execution may already have been cleared.
2. **In a subsequent HTTP request:** the browser sends a session cookie after an earlier login; the server needs to look up the authentication from `HttpSession`.

`DelegatingSecurityContextRepository` combines multiple implementations of the `SecurityContextRepository` interface to serve both. In Spring Security 6's default Servlet configuration, the delegate pair is:

~~~java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
~~~

`RequestAttributeSecurityContextRepository` holds the context via a **request attribute** within the same servlet request; `HttpSessionSecurityContextRepository` holds the context via **HTTP session** across requests; `DelegatingSecurityContextRepository` **saves to its delegates** and **loads in configured order**.

**Key takeaway:** *Request attributes carry context across dispatches within the same request; HTTP sessions serve new requests; Delegating combines both without building a separate authentication system.*

This lesson belongs to the **Servlet Context** group of the *Spring Security - authentication* module. The content describes Spring Security 6.x and Spring Boot 3.x on Java 17+. Do not apply these Servlet interfaces verbatim to WebFlux, which uses `ServerSecurityContextRepository`.

After this lesson, you will be able to explain each repository's responsibilities, read/write ordering, the difference between `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter`, the explicit-save mechanism, and session-based vs. stateless scenarios; as well as run an application and unit tests yourself to verify.

## 1. Foundational Concepts

| Component | Role | Do Not Confuse With |
| --- | --- | --- |
| `Authentication` | Principal, authorities, and authentication details | Not a session store |
| `SecurityContext` | Holds one `Authentication` for the security context | Does not auto-save across requests |
| `SecurityContextHolder` | Provides context for the current execution | Not a persistence store |
| `SecurityContextHolderStrategy` | How the holder binds context to a thread/execution | Not a servlet request attribute |
| `SecurityContextRepository` | Contract for reading/writing context from storage | Not `AuthenticationManager` |
| `RequestAttributeSecurityContextRepository` | Stores on a server-side request attribute | Not client-sent headers/parameters |
| `HttpSessionSecurityContextRepository` | Saves into `HttpSession` | Not a JWT/refresh token |
| `DelegatingSecurityContextRepository` | Coordinates multiple repositories | Not database replication |
| `SecurityContextHolderFilter` | Loads context for the request via repository | Does not auto-save context at end of request in explicit-save mode |

Authentication and persistence are two distinct duties. `AuthenticationManager` and providers verify username/password or tokens, then create a trusted authentication. The repository **only writes/loads the result**. A user existing in the DB or having a `SecurityContext` does not prove all access permissions; authorization also checks authorities and account policies.

Example:

~~~text
HTTP login:
  client sends credentials
       |
       v
  Authentication filter
       |
       v
  AuthenticationManager/Provider -> verifies proof
       |
       v
  Authentication succeeds
       |
       v
  SecurityContextHolder -> used in current request
       |
       v
  SecurityContextRepository.saveContext(...)
       |
       v
  DelegatingSecurityContextRepository
       |                          |
       v                          v
  Request attribute          HTTP session
~~~

**Never** construct an authenticated token from an unverified username and pass it to the repository. Doing so bypasses real authentication, even if saving and restoring the context appears to work.

## 2. The SecurityContextRepository Contract

Key methods from `org.springframework.security.web.context.SecurityContextRepository`:

~~~java
// Abbreviated API signatures for learning; not a standalone Java file.
DeferredSecurityContext loadDeferredContext(
    HttpServletRequest request
);

void saveContext(
    SecurityContext context,
    HttpServletRequest request,
    HttpServletResponse response
);

boolean containsContext(HttpServletRequest request);

// Legacy deprecated API:
SecurityContext loadContext(
    HttpRequestResponseHolder holder
);
~~~

### 2.1. loadDeferredContext: Load When Needed

~~~java
// Fragment inside a method with repository and request.
DeferredSecurityContext deferred =
    repository.loadDeferredContext(request);
SecurityContext current = deferred.get();
boolean generated = deferred.isGenerated();
~~~

`loadDeferredContext(...)` allows deferring the actual read from the repository. `get()` returns the context; `isGenerated()` indicates whether the context was newly generated rather than already present in the store. It does not return a `null` context; if no stored identity is found, an empty context is used per strategy.

With a delegating repo, selecting a delegate follows configuration order: check the first store; if no existing context is found, check the next. It does not search for the "newest context" by timestamp, merge authorities from multiple sources, or pick the principal with the highest privileges.

### 2.2. saveContext: Forward to Multiple Delegates

~~~java
repository.saveContext(context, request, response);
~~~

If this repository is a composite of request attribute and HTTP session, the operation above is forwarded to both delegates. One saves in the request object; the other saves into the session **if the context and session policy permit**. You cannot assume save always creates a new session, because `HttpSessionSecurityContextRepository` avoids creating useless sessions for empty/anonymous contexts.

Do not treat `saveContext` as a two-phase transaction: if you add custom Redis/DB backends, this interface does not provide rollback across independent stores.

### 2.3. containsContext: Has Data, Not Necessarily Has Permission

`repository.containsContext(request)` indicates whether a context exists in the matching store. A `true` result **does not mean** `Authentication.isAuthenticated()` is valid, the account is not disabled, or the user may enter `/admin`. Authorization must use configured security rules, never `containsContext` as an access condition.

## 3. Precedence Order: Reading Differs from Writing

Suppose:

~~~java
SecurityContextRepository repo =
    new DelegatingSecurityContextRepository(
        requestAttributeRepository,
        sessionRepository
    );
~~~

When **reading**:

~~~text
repo.loadDeferredContext(request)
   |
   +--> RequestAttributeSecurityContextRepository
   |       has existing context -> pick it
   |       none                 -> continue
   |
   +--> HttpSessionSecurityContextRepository
   |       has existing context -> pick it
   |       none                 -> new/empty context
   |
   v
SecurityContext for SecurityContextHolder
~~~

When **writing**:

~~~text
repo.saveContext(context, request, response)
   |
   +--> requestAttributeRepository.saveContext(...)
   |
   +--> sessionRepository.saveContext(...)
~~~

This is a **read first matching source, write to all sources** mechanism. Hence delegate order is a meaningful decision. A custom delegate placed before session that holds an old context can shadow a newer session context. The repository does not resolve this inconsistency by comparing privileges or timestamps.

### 3.1. Example: Bob in Request, Alice in Session

In an illustrative unit test, the session contains Alice, while the current request has a request attribute containing Bob. A composite placing the request store before the session will pick Bob. A new HTTP request creates a fresh request object without the previous request's attribute, so reusing the session restores Alice.

~~~text
Request R1:
  session = Alice
  attribute = Bob
  composite load -> Bob

Request R2, same session arriving via browser:
  session = Alice
  R1's attribute does not exist
  composite load -> Alice
~~~

This is an **ordering test pattern**—never treat it as a valid account-switching mechanism. In production, if the application intentionally switches identity, it must have valid authentication/policy and save the context consistently to the proper repositories; never just edit an attribute to "log in as Bob".

## 4. RequestAttributeSecurityContextRepository: Same Request, Multiple Dispatches

Request attributes are server-side data attached to `ServletRequest`. Dispatches such as `DispatcherType.REQUEST`, `DispatcherType.FORWARD`, and `DispatcherType.ERROR` can belong to the same request. In some containers, when an error occurs, the holder has already been cleared before the error dispatch is handled.

~~~text
HTTP request #1
  REQUEST dispatch:
    Alice authenticated
    saveContext(...) -> request attribute of #1 holds Alice
    controller throws error

  ERROR dispatch of request #1:
    old holder may have been cleared
    repository can restore Alice from attribute

HTTP request #2
  completely new request attribute
  does not carry request #1's attribute
~~~

`RequestAttributeSecurityContextRepository` helps an error page or forward handler see the principal **within the same request**. Still, understand the conditions: the context must have been saved, the filter chain/dispatcher type must have a chance to reload it, and the container must handle the dispatch accordingly. It **does not guarantee** every error page automatically knows the user.

### 4.1. Request Attribute Alone Does Not Preserve Login Across Refreshes

~~~java
// Configuration fragment inside SecurityFilterChain.
http.securityContext(sc -> sc
    .securityContextRepository(
        new RequestAttributeSecurityContextRepository()
    )
);
~~~

Refreshing the browser or clicking a link sends a new HTTP request; the previous request's server-side attribute is not sent along. Without another store or per-request re-authentication, the user becomes anonymous. That is why this repository alone is not used in place of sessions for multi-request form login.

## 5. HttpSessionSecurityContextRepository: Next Request

`HttpSessionSecurityContextRepository` stores the context in `HttpSession`, by default under the key `SPRING_SECURITY_CONTEXT`. The Servlet container manages the session and the `JSESSIONID` cookie, while Spring Security manages the `SecurityContext` contents.

~~~text
POST /login:
  filter/provider authenticates Alice
  session stores SecurityContext Alice
  browser keeps session cookie

GET /me:
  browser sends cookie with session ID
  server locates session
  session repository returns SecurityContext Alice
  holder filter loads context
  controller sees Authentication Alice
~~~

Having a `JSESSIONID` **does not prove** the user is logged in: a session can also be created for CSRF, request cache, or other application data. Only a valid authenticated context together with matching authorization grants access.

### 5.1. Does Not Always Create a Session

`HttpSessionSecurityContextRepository` tries to avoid creating unnecessary sessions. Per the API, loading does not create a new session just to read; when saving, it creates a session if the context is non-empty/non-anonymous and policy allows. `setAllowSessionCreation(false)` can prevent the repository from creating a new session, though it does not stop other code from creating one.

When you need to *check* whether a session exists, use:

~~~java
HttpSession existing = request.getSession(false);
~~~

Never call `request.getSession()` just to check, because it can create a new session and mislead debugging.

### 5.2. Session Fixation and Multiple Nodes

Upon successful login, standard Spring Security form login integrates session fixation protection, typically rotating the session ID on modern servlet containers. Writing custom login and only calling saveContext may not provide complete protection.

If the application runs on multiple nodes and sessions reside in node A's memory, a request hitting node B can lose authentication. `DelegatingSecurityContextRepository` **does not automatically share sessions across nodes**. Sticky sessions or a shared session backend/storage, such as Spring Session when appropriate, are required.

Never store raw passwords or secrets in the principal/session. A distributed session store may require serializable objects, so principals/contexts should be small, stable, and compliant with serialization policies.

## 6. Spring Security 6 and Explicit Save

In Spring Security 5, configurations typically used `SecurityContextPersistenceFilter`, which had a mechanism to automatically write back changed contexts at request end or before response commit. Spring Security 6 uses `SecurityContextHolderFilter` by default; the new filter **loads** context into the holder and **does not auto-save**.

| Filter | Loads Context | Saves Context |
| --- | --- | --- |
| `SecurityContextPersistenceFilter` | Yes | Can auto-save under the legacy mechanism |
| `SecurityContextHolderFilter` | Yes | **No**; requires explicit save when persistence is wanted |

Do not configure both simultaneously on the same chain.

### 6.1. What Is requireExplicitSave?

Spring Security 6 applies the model corresponding to `requireExplicitSave(true)` by default. You can write it explicitly:

~~~java
http.securityContext(sc -> sc
    .requireExplicitSave(true)
    .securityContextRepository(repository)
);
~~~

This is an illustrative configuration assuming `HttpSecurity http` and `SecurityContextRepository repository` already exist. This line does not mean **every read** must save again. Only when code **creates or modifies the context and wants it saved** across requests/dispatches should `saveContext` be called at the right time.

### 6.2. Why Does Custom Login Often Lose the Session?

The following snippet only puts the context into the holder:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
// Missing repo.saveContext(...); next request may be anonymous.
~~~

With verified custom authentication, the fuller pattern is:

~~~java
// Fragment: requires AuthenticationManager, SecurityContextRepository,
// HttpServletRequest/HttpServletResponse, and credential inputs.
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context, request, response
);
~~~

Only a **verified AuthenticationManager/provider** may create a trusted authentication. This snippet is still **not a complete production HTTP login**: session authentication strategy, session fixation, CSRF, rate limiting, success/failure handlers, and auditing remain. Use standard login filters whenever appropriate.

Saving must happen **before the HTTP response commits**, so the session/cookie can be set properly. If you bind one repository in the holder filter while custom login saves to a different instance, the next request may not see the context.

### 6.3. Stateless Authentication Filters Can Have Their Own Repository

Configuring `http.securityContext(...securityContextRepository(repo))` affects the holder filter and filters participating in persistence like form login; some stateless authentication mechanisms (such as Basic/Bearer) have their own repository. Do not assume that merely declaring a `SecurityContextRepository` bean makes every filter save sessions. Inspect the filter chain per URL and actual policy.

## 7. Runnable Spring Boot Java 17+ Program

Let's write a Spring Boot MVC app using **built-in** form login to observe session persistence across multiple requests. The delegate pair is explicitly configured even though it is also the default in Spring Security 6.

### 7.1. Create the Project

On Spring Initializr, select Maven, Spring Boot 3.x, Java 17 (or 21), package `com.example.demo`, and dependencies **Spring Web**, **Spring Security**. That gives `spring-boot-starter-web` and `spring-boot-starter-security` in `pom.xml`.

Create **`src/main/java/com/example/demo/ContextRepositoryApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ContextRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextRepositoryApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain security(
        HttpSecurity http,
        SecurityContextRepository repository
    ) throws Exception {
        return http
            .securityContext(sc -> sc
                .requireExplicitSave(true)
                .securityContextRepository(repository)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "Hello " + authentication.getName();
        }
    }
}
~~~

The code illustrates the right boundaries:

- `UserDetailsService` supplies the account; the password is BCrypt-hashed when initializing the demo.
- `formLogin(withDefaults())` enables the standard login filter; the form includes a proper CSRF token, and the authentication provider verifies the password.
- The composite repository places request attribute **before** session and is attached to `HttpSecurity`.
- `SecurityContextHolderFilter` uses the repository to load; the form login filter handles saving on success.
- The `/me` controller receives the `Authentication` created by Spring Security, without performing login itself.

Do not use hardcoded demo accounts or the password `demo-pass` in production. Never disable CSRF just to run an example.

### 7.2. Run the Application

In the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Test in a browser, since browsers automatically keep session cookies and form login has CSRF:

1. Open `http://localhost:8080/public`: receives body `public`.
2. Open `http://localhost:8080/me` while anonymous: redirected to `/login`.
3. Enter username **alice**, password **demo-pass**; submit.
4. Visit/refresh `/me`: body **`Hello alice`**. This is a new HTTP request, proving context restoration via session.
5. Open an incognito window without sharing cookies: `/me` prompts for login again.
6. Log out via the default UI, then visit `/me` again: no longer authenticated.

Do not send a POST login without CSRF via curl and assume the repository is broken. And refreshing does not prove the previous request's request attribute was sent to the new request — **it is not**.

### 7.3. Illustrative Timeline

~~~text
R1 GET /me (anonymous)
  request attribute: none
  session: no authentication yet
  -> redirect to login

R2 POST /login (valid form)
  provider verifies alice
  form login creates SecurityContext Alice
  saveContext into request attribute R2 + session
  -> redirect on success

R3 GET /me (browser has cookie)
  new request attribute: empty
  session: Alice
  -> load context Alice, controller "Hello alice"

R4 GET /me (different browser without that session cookie)
  request attribute: empty
  corresponding authenticated session: none
  -> redirect to login
~~~

A session may already have been created for the CSRF token or request cache before login; that does not mean the user is authenticated.

## 8. Unit Tests for Both Stores and Ordering

The browser proves the session. To observe **writing to both** and **request attribute precedence** directly, you can use Spring Test mocks without a real servlet container.

In `pom.xml`, ensure:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/com/example/demo/DelegatingRepositoryTest.java`**:

~~~java
package com.example.demo;

import java.util.List;

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

import static org.junit.jupiter.api.Assertions.*;

class DelegatingRepositoryTest {

    private SecurityContext fixture(String username) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            )
        );
        return context;
    }

    @Test
    void saveToBothAndReadFromSessionOnNextRequest() {
        var requestRepo =
            new RequestAttributeSecurityContextRepository();
        var sessionRepo =
            new HttpSessionSecurityContextRepository();

        SecurityContextRepository repo =
            new DelegatingSecurityContextRepository(
                requestRepo, sessionRepo
            );

        var first = new MockHttpServletRequest();
        repo.saveContext(
            fixture("alice"), first,
            new MockHttpServletResponse()
        );

        assertTrue(requestRepo.containsContext(first));
        assertTrue(sessionRepo.containsContext(first));

        MockHttpSession session =
            (MockHttpSession) first.getSession(false);
        assertNotNull(session);

        var second = new MockHttpServletRequest();
        second.setSession(session);

        assertFalse(requestRepo.containsContext(second));
        assertTrue(sessionRepo.containsContext(second));
        assertEquals(
            "alice",
            repo.loadDeferredContext(second)
                .get().getAuthentication().getName()
        );
    }

    @Test
    void requestAttributeOverridesSessionOnlyInThatRequest() {
        var requestRepo =
            new RequestAttributeSecurityContextRepository();
        var sessionRepo =
            new HttpSessionSecurityContextRepository();
        SecurityContextRepository repo =
            new DelegatingSecurityContextRepository(
                requestRepo, sessionRepo
            );

        var first = new MockHttpServletRequest();
        repo.saveContext(
            fixture("alice"), first,
            new MockHttpServletResponse()
        );
        MockHttpSession session =
            (MockHttpSession) first.getSession(false);
        assertNotNull(session);

        var second = new MockHttpServletRequest();
        second.setSession(session);

        // BOB data is set only on the request attribute for TESTING,
        // NOT a way to switch identities in production.
        requestRepo.saveContext(
            fixture("bob"), second,
            new MockHttpServletResponse()
        );

        assertEquals(
            "bob",
            repo.loadDeferredContext(second)
                .get().getAuthentication().getName()
        );

        var third = new MockHttpServletRequest();
        third.setSession(session);

        assertEquals(
            "alice",
            repo.loadDeferredContext(third)
                .get().getAuthentication().getName()
        );
    }

    @Test
    void emptyContextDoesNotCreateNewHttpSession() {
        SecurityContextRepository repo =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );
        var request = new MockHttpServletRequest();

        repo.saveContext(
            SecurityContextHolder.createEmptyContext(),
            request,
            new MockHttpServletResponse()
        );

        assertNull(request.getSession(false));
    }
}
~~~

**Security note:** the `fixture(username)` method manually creates an authenticated token solely for repository unit tests. In a real application, an authentication provider/manager must verify credentials first; never create an authenticated token from client input.

Run:

~~~bash
./mvnw test
~~~

Windows: `.\mvnw.cmd test`. Expect **three passing tests**, with a Maven Surefire summary similar to:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
~~~

The tests only verify the repository contract: saving to both; new requests loading from session; request attribute winning within the current request; empty context not creating a session. They **do not replace** integration tests for real `DispatcherType.ERROR`, session fixation, CSRF, or distributed sessions.

## 9. Choosing a Repository by Architecture

| Design | Appropriate Repository | What to Verify |
| --- | --- | --- |
| Form login + session in Servlet | Delegating(RequestAttribute, HttpSession) | New requests, session cookies, error dispatches |
| Context needed only within the same servlet request | RequestAttributeSecurityContextRepository | No persistence across new requests |
| Only session persistence needed for specific requirements | HttpSessionSecurityContextRepository | Error dispatches, session policy |
| Stateless JWT/Bearer | NullSecurityContextRepository or matching stateless mechanism | Token verified on every request |
| Custom store | Delegating(custom, RequestAttribute, Session) if truly needed | Order, stale data, per-backend failures, performance |

### 9.1. Stateless APIs Should Not Create Sessions Arbitrarily

A resource server application can configure:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(session ->
            session.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS
            )
        )
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

This is a **fragment**, requiring the OAuth2 resource server starter, JWT decoder/issuer, and imports. Do not paste it into the form-login app above and expect sessions to keep working as before. With `STATELESS`, Spring Security does not use HTTP sessions to retrieve context and typically uses `NullSecurityContextRepository` in the corresponding mechanism.

`SessionCreationPolicy.NEVER` differs from `STATELESS`: `NEVER` can still use an existing session; other components such as request cache can still create sessions. Verify empirically rather than relying on the enum name.

### 9.2. Custom Repositories Must Have a Conflict Policy

If adding a database/Redis repository:

- A higher-priority yet stale delegate can mask newer data from the session.
- Writing to multiple backends has no atomic/rollback guarantee if one backend fails.
- On logout, all saved locations must be cleared/revoked accurately.
- Session/context may require safe serialization.
- Accessing remote backends on the request path increases latency and system failure modes.
- Never store raw passwords, bearer tokens, or excessive personal data in serialized principals.

Do not use `DelegatingSecurityContextRepository` as a distributed synchronization cache or an automatic permission-merging mechanism.

## 10. Troubleshooting

| Symptom | Possible Cause | Fix Direction |
| --- | --- | --- |
| Login returns success, yet refresh loses login | Only set holder without saving; used only request attribute | Use composite and save via the right mechanism |
| ERROR dispatch lacks principal | Holder cleared, request attr not saved, missing filter mapping | Test RequestAttribute repo and dispatcher types |
| Request sees Bob, refresh turns into Alice | Only updated request attribute while session remains Alice | Ensure proper saving across all delegates |
| Has JSESSIONID yet still anonymous | Session lacks authenticated context or expired | Inspect session contents and filters |
| No session after save | Empty/anonymous context, stateless, allowSessionCreation=false | Check policy; do not fake sessions |
| Public page created a session | CSRF, request cache, or other code | Trace which component created the session |
| Stateless API creates a session | Mixed session policies/filter chains | Configure and test STATELESS |
| `containsContext` used to grant access | API misunderstanding | Use authorization rules |
| User still visible after logout | Session/other delegate or token not revoked | Use logout support and token policies |
| Multi-node drops login | Sessions not shared across nodes | Use an appropriate shared session backend |
| Async job lacks principal | Different thread did not receive propagated context | Use security context propagation |
| Request runs two security context filters | Mixed HolderFilter with PersistenceFilter | Use only one per configuration |

### 10.1. Debugging Sequence

1. Verify whether authentication succeeded from manager/provider.
2. Verify which `SecurityFilterChain` actually handles the URL.
3. Locate where `saveContext(...)` is called after authentication and check the repository instance.
4. Inspect `requestAttributeRepo.containsContext(request)` and `sessionRepo.containsContext(request)` separately in tests.
5. Check session cookie, expiry, session ID, and backend/node.
6. For error pages, check `DispatcherType.ERROR` and filter registrations.
7. If HTTP `403`, distinguish missing authorities from missing persistence.
8. Never log raw credentials, literal session IDs, or `SecurityContext` dumps.

## 11. Security and Lifecycle

**Logout:** `SecurityContextHolder.clearContext()` only clears data from the current execution; it **does not automatically** delete sessions or other stores. Use Spring Security logout support and test that new requests are no longer authenticated; handle remember-me, refresh tokens, or JWTs per architecture.

**CSRF/session fixation:** Session-based form login must protect state-changing requests against CSRF. Session fixation protection is the job of the session authentication strategy; merely saving context to the HTTP session does not replace it. With HTTPS, configure `HttpOnly`, `Secure`, and appropriate `SameSite` cookie attributes.

**Account changes:** A `SecurityContext` saved in a session may hold stale authorities. Disabling an account or changing roles in the DB does not revoke sessions/tokens by default. If the product requires immediate blocking, a dedicated recheck/revocation policy is needed.

**Async and ThreadLocal:** Request attributes belong to the servlet request, while the holder usually relies on ThreadLocal. Switching threads does not mean the principal transfers automatically. Use supported mechanisms such as `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` or proper async integration; do not expect the request-attribute repository to solve every thread boundary.

**Consistency:** Delegating sends saves to its delegates, but has no distributed quorum/transaction. If the session store fails while the request attribute succeeds, the current request may see the context in a subsequent dispatch, while the next request loses login. Clear monitoring and failure policies are essential.

## 12. Questions and Answers

**Question 1.** Why are there two default repositories?

**Answer:** request attributes work within the same request across dispatches; sessions work across subsequent requests sharing the same session.

**Question 2.** Is `SecurityContextHolder.setContext(ctx)` enough for login to be remembered across requests?

**Answer:** no under `SecurityContextHolderFilter`'s explicit-save model. You must save through the repository or use a standard authentication filter that handles it.

**Question 3.** Request attribute has Bob, session has Alice, and attribute comes before session. Whom does load return?

**Answer:** Bob within that request, if the attribute holds an existing context. No merging or privilege comparison occurs.

**Question 4.** The next request has Alice's session but not Bob's old attribute. Whom does load return?

**Answer:** Alice from the session, if the session is valid.

**Question 5.** Is `containsContext(request) == true` enough for `/admin`?

**Answer:** no. Real authentication and authorization are required.

**Question 6.** Does saving an empty context always create a session?

**Answer:** no; the standard session repository avoids creating pointless sessions for empty/anonymous contexts.

**Question 7.** Why can an error page lose the principal?

**Answer:** the holder may be cleared before the ERROR dispatch; request attributes allow restoration if saved and the filter applies.

**Question 8.** Does a stateless JWT API need a session repo?

**Answer:** no; bearer tokens can be verified on every request using a stateless policy.

**Question 9.** Why should an authenticated token self-constructed in a unit test not be used for production login?

**Answer:** the test only creates a fixture. In production, creating that token from an unverified username is an authentication bypass.

**Question 10.** Does a composite repo synchronize sessions across two servers?

**Answer:** no. A shared session backend or appropriate routing/solution is needed.

**Question 11.** After logout, only the holder is cleared while the session still holds Alice—what is the risk?

**Answer:** new requests can reload Alice from the session; all stores/tokens must be cleared properly.

**Question 12.** Does `requireExplicitSave(true)` require saving after every read?

**Answer:** no. Saving is needed when the flow modifies the context and wants to keep it; non-mutating reads normally do not need to write.

## 13. Implementation Checklist

- [ ] Use properly on the Servlet stack, distinguishing `SecurityContextRepository` from `SecurityContextHolder`.
- [ ] Understand Delegating's load ordering and save-to-all behavior.
- [ ] Use both request attributes and HTTP sessions when both error dispatches and session persistence are needed.
- [ ] For custom authentication, obtain a manager-verified result and call `saveContext` at the right time.
- [ ] Never create authenticated tokens from unverified client usernames.
- [ ] Never use `containsContext` as an authorization check.
- [ ] Test new requests with the same session and requests without cookies.
- [ ] Test error dispatches/filter mappings if error pages need the principal.
- [ ] Never mix `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter` on the same chain.
- [ ] Never use HTTP sessions for stateless APIs outside policy; test `STATELESS` empirically.
- [ ] Test logout, session expiration, session fixation, and cookie flags.
- [ ] With multiple nodes or custom stores, define clear consistency/failure/serialization rules.
- [ ] Never store raw passwords/tokens in context or logs.
- [ ] Test against the project's actual Spring Security 6 API and dependency versions.

**Conclusion:** `DelegatingSecurityContextRepository` coordinates ways of storing `SecurityContext`. In Spring Security 6 Servlet, pairing `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository` preserves context across dispatches of the **same request** and across **other requests** within a session. Delegating **reads in order** and **saves across delegates**, yet does not authenticate, authorize, or sync sessions across servers itself. With `SecurityContextHolderFilter`'s explicit-save model, code performing custom authentication must save the context explicitly to maintain login.

## Official Documentation

- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Migration: Session Management](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security 6.5 — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html)
- [Spring Security 6.5 — RequestAttributeSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html)
- [Spring Security 6.5 — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
