# SecurityContextRepository and Loading/Saving Servlet Context

Consider this scenario: Mai logs into a Spring MVC application successfully. During the login request, `SecurityContextHolder.getContext().getAuthentication()` indicates the current user is Mai. Afterward, the browser sends `GET /me` and the application still recognizes Mai **without prompting for a password again**.

How can two separate HTTP requests share an authenticated identity when a Servlet application's `SecurityContextHolder` uses `ThreadLocal` by default and must be cleared once request processing ends? The answer lies in a boundary called **`SecurityContextRepository`**.

It is the strategy that **loads** `SecurityContext` for the current request and **saves** `SecurityContext` to an appropriate store when it should be reused in future requests or across different dispatches of the same request. One implementation uses `HttpSession`, another uses request attributes, and another deliberately saves nothing.

This lesson focuses on the **Spring Security Servlet stack** (Spring MVC/Tomcat and `jakarta.servlet`), and does not apply verbatim to WebFlux. You will learn `SecurityContextRepository` end-to-end, understand modern Spring Security defaults, distinguish `SecurityContextHolderFilter` from `SecurityContextPersistenceFilter`, invoke `saveContext` at the right moment, and run a Spring Boot 4.1.2/Java 17 example with form login + MockMvc tests.

## 1. Four components to distinguish before writing code

| Component | Role | Lifetime and scope |
| --- | --- | --- |
| `Authentication` | Identity, verified proof, and authorities of the principal | An object that may be held in request, context, or session depending on mechanism |
| `SecurityContext` | Container holding the security context's `Authentication` | Can be freshly created, loaded from a repository, or stored in a session |
| `SecurityContextHolder` | Access point to the current execution thread's `SecurityContext`; defaults to `ThreadLocal` in Servlet | Normally bound only to the thread handling the request; must be cleared on time |
| `SecurityContextRepository` | Strategy for **saving/loading** `SecurityContext` across servlet request/response | Depends on implementation: request attribute, HTTP session, or no storage |

One code snippet:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

**Does not mean** Spring Security queried the database on this line. In Servlet apps, the context was normally loaded/attached to `SecurityContextHolder` by filters before the controller ran; this line simply reads the current thread's context.

Another snippet:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticatedUser);
SecurityContextHolder.setContext(context);
~~~

Only sets `Authentication` into the context bound to the current thread. **It does not guarantee** that the next request will see `authenticatedUser`. Persisting across requests requires an appropriate persistence mechanism and/or an authentication filter that handles saving.

### Timeline to remember

~~~text
Request A: POST /login
    |
    +--> Authentication succeeds
    +--> SecurityContext(Authentication=Mai)
    +--> SecurityContextRepository.saveContext(...)
    +--> HTTP response + session cookie (if using session)

                (request A completes)
          SecurityContextHolder is cleared

Request B: GET /me, sending back session cookie
    |
    +--> Repository.loadDeferredContext(request B)
    +--> SecurityContextHolder has Authentication=Mai
    +--> Controller /me returns "mai"
    +--> SecurityContextHolder is cleared when request B ends
~~~

**Clearing `SecurityContextHolder`** and **saving `SecurityContext` into the session** do not contradict each other. In fact, separating these two responsibilities is precisely what keeps a servlet thread reused for another user from accidentally retaining Mai's identity.

## 2. The SecurityContextRepository contract

The interface lives at:

~~~java
org.springframework.security.web.context.SecurityContextRepository
~~~

Key methods:

~~~java
// Excerpt of Spring Security API signatures; imports omitted to focus on mechanics.
DeferredSecurityContext loadDeferredContext(HttpServletRequest request);

void saveContext(
    SecurityContext context,
    HttpServletRequest request,
    HttpServletResponse response
);

boolean containsContext(HttpServletRequest request);
~~~

Understanding each method accurately:

1. **`loadDeferredContext(request)`** returns a `DeferredSecurityContext`. Loading can be **deferred** until `get()` is needed, avoiding unnecessary session reads on requests that never ask for identity.
2. **`saveContext(context, request, response)`** persists the context per the implementation's mechanism. A session repository needs the request/response to create or use an HTTP session and emit cookies when needed.
3. **`containsContext(request)`** checks whether the repository holds a context for the current request. It is **not** password verification or a role check.
4. The older method `loadContext(HttpRequestResponseHolder)` may still appear in legacy docs/code, yet is **deprecated**; prefer `loadDeferredContext` in new designs.

`DeferredSecurityContext` provides `get()` and `isGenerated()` to access the context and know when a context was freshly generated in the API sense. Do not use `isGenerated()` alone to decide whether a user is logged in or authorized; permissions must be evaluated from `Authentication` and trusted policies.

### Mental model: load, set, and save are three distinct actions

~~~text
load:
  repository -> context for request

set:
  SecurityContextHolder <- current thread's context

save:
  context -> repository (if persisting within repository's supported scope)
~~~

If you only do `set`, the state in the thread works for the remainder of the request, yet is not guaranteed to exist on the next request. If you only do `save` without setting the context for the current request, code calling `SecurityContextHolder` **within the same request** may not see the result you expect. Normally custom login creates a fresh context, calls `setContext`, and then calls `saveContext`.

## 3. Core implementations

| Implementation | Where data is stored | Survives to next request? | Key notes |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | `HttpSession`, by default under key `SPRING_SECURITY_CONTEXT` | **Yes**, if the session remains valid and client sends the matching session identifier | Suits session-based login |
| `RequestAttributeSecurityContextRepository` | Attribute on `ServletRequest` | **No** across a new HTTP request | Useful across dispatches of the same request, such as error dispatch |
| `DelegatingSecurityContextRepository` | Multiple child repositories | Depends on delegates | On save, delegates to children; on load, retrieves suitable context in order |
| `NullSecurityContextRepository` | Does not save | **No** | Used when no context persistence is wanted, e.g., stateless flows |

These implementations belong to package `org.springframework.security.web.context`.

Do not confuse `SecurityContextRepository` with `UserDetailsService`: the first saves/loads **identity results**; the second loads **user data for username/password authentication**. The context repository does not necessarily re-verify passwords on every request, and `UserDetailsService` is not session storage.

### 3.1. HttpSessionSecurityContextRepository

This implementation uses `HttpSession` to associate identity with **subsequent requests**. After successful login, the session holds `SecurityContext`; the client holds a session cookie (commonly named `JSESSIONID`, or `SESSION` if Spring Session is used). A new request carrying a valid cookie resolves to the corresponding session.

~~~text
Browser                         Servlet app
  | POST /login                    |
  |------------------------------->|
  |                 Authenticate -> SecurityContext
  |                 saveContext -> HttpSession
  |<-------------------------------|
  |          Set-Cookie: JSESSIONID=...
  |
  | GET /me + Cookie: JSESSIONID=...
  |------------------------------->|
  |                  HttpSession -> SecurityContext
  |                  SecurityContextHolder -> Authentication
  |<-------------------------------|
  |                             "mai"
~~~

The default session attribute key of this class is `SPRING_SECURITY_CONTEXT`. That is an **internal attribute name**, not a URL API or cookie name.

`HttpSessionSecurityContextRepository.saveContext` does not mean every call creates a session. The implementation checks conditions: whether context state changed, whether it contains anonymous authentication, session creation policy, and other constraints. Documentation notes it can create a session **when needed**, with `allowSessionCreation` defaulting to `true`.

A configuration snippet:

~~~java
HttpSessionSecurityContextRepository repository =
    new HttpSessionSecurityContextRepository();

repository.setAllowSessionCreation(false);
~~~

When session creation is disallowed, the repository cannot create a new session merely because you called `saveContext`. If a session already exists, saving behavior still depends on other conditions. **Do not treat `setAllowSessionCreation(false)` as a system-wide stateless configuration**; another component might still create a session.

### 3.2. RequestAttributeSecurityContextRepository

This class keeps context in an attribute of **ServletRequest**, which does not survive across two independent HTTP requests.

A useful example:

~~~text
REQUEST dispatch
   |
   +--> already identified user Mai
   +--> context is saved into request attribute
   +--> controller throws exception
   |
   v
ERROR dispatch (still belongs to the same servlet request)
   |
   +--> container may switch/clear thread context
   +--> repository reads request attribute
   +--> error view can know Mai's identity
~~~

Some servlet containers use a different dispatch when forwarding to an error page. `RequestAttributeSecurityContextRepository` is designed so context remains accessible across dispatches of the **same request** even if `SecurityContextHolder` was temporarily cleared. It is not a database, issues no session cookie, and creates no long-lived authentication.

**Note:** which filter chain handles error dispatches, what policy applies, and whether identity info is accessible still depend on dispatcher-type/security config. Do not assume "saving to request attribute" automatically displays identity on every error page.

### 3.3. DelegatingSecurityContextRepository

Since Spring Security 6, the common setup uses:

~~~java
new DelegatingSecurityContextRepository(
    new RequestAttributeSecurityContextRepository(),
    new HttpSessionSecurityContextRepository()
)
~~~

When `saveContext` is called, `DelegatingSecurityContextRepository` forwards saving to its delegates. When loading, it retrieves an appropriate context from the delegates in order. This pair brings **two complementary benefits**: context is available across dispatches of one request and can be persisted across requests via session.

It does **not** mean Spring Security creates two separate sessions. Request attribute and HTTP session are two storage locations with **different scopes**.

Spring Security 7 continues supporting these implementations. Actual defaults in an application may be adjusted by custom `SecurityFilterChain`, session policy, authentication mechanism, or Spring Boot auto-configuration; when debugging, inspect the chain and repository **actually configured**, not just class names in an article.

### 3.4. NullSecurityContextRepository

This is a repository that "saves nothing on write, restores nothing from prior sessions on load":

~~~java
SecurityContextRepository noPersistence =
    new NullSecurityContextRepository();
~~~

Appropriate when each request re-authenticates from a bearer token or other mechanism and **must not bind Authentication to a server-side session**.

However, `NullSecurityContextRepository` does not validate JWTs, does not build `Authentication`, and **does not automatically delete cookies** that another part of the application might issue. Stateless authentication is an end-to-end design encompassing chains, session policy, token verification filters, caching, and credential handling. Never swap only the repository and declare all components stateless.

## 4. Which filter loads the context: SecurityContextHolderFilter or SecurityContextPersistenceFilter?

This is a key difference between Spring Security 5 tutorials and modern Servlet configuration.

### 4.1. SecurityContextPersistenceFilter — legacy style, auto-saves when applicable

Conceptual flow:

~~~text
SecurityContextPersistenceFilter
      |
      +--> Repository LOAD into SecurityContextHolder
      |
      +--> Filters/controller process request
      |
      +--> When context changes, may auto-SAVE
      |    (including wrapper mechanism before response commit)
      |
      +--> CLEAR SecurityContextHolder
~~~

When this filter handled persistence, some legacy code only called `SecurityContextHolder.setContext(context)`, and the filter detected changes and saved them. However, tracking context mutations/saving at the end of a request was complex, and redirects could commit the response before post-processing code ran.

`SecurityContextPersistenceFilter` is kept mainly for understanding/migrating legacy systems, **not as a default to add manually** to modern applications.

### 4.2. SecurityContextHolderFilter — loads without auto-saving

Flow:

~~~text
SecurityContextHolderFilter
      |
      +--> Repository.loadDeferredContext(request)
      |    sets strategy for app to read SecurityContext
      |
      +--> Filters/controller process request
      |
      +--> When persistence is needed:
      |        AUTHENTICATION CODE MUST EXPLICITLY saveContext(...)
      |
      +--> CLEAR SecurityContextHolder on exit
~~~

Comparison:

| Property | `SecurityContextPersistenceFilter` | `SecurityContextHolderFilter` |
| --- | --- | --- |
| Loads context for request | Yes | Yes |
| Auto-detects and saves context on change | Legacy mechanism, yes | **No** |
| Requires explicit save for code manually setting context | Typically no in legacy config | **Yes**, if persistence across requests is wanted |
| Needs thread context cleanup | Yes | Yes |
| Usage guidance for Spring Security 6/7 | Mainly migration/backward compatibility | Modern default |

Within a single security filter chain, **never add both filters simultaneously** since both manage `SecurityContextHolder`. Modern configurations should use `SecurityContextHolderFilter` and matching explicit-save semantics.

### 4.3. What does requireExplicitSave(true) mean?

In Servlet `HttpSecurity`:

~~~java
http.securityContext(sc -> sc
    .requireExplicitSave(true)
);
~~~

It selects `SecurityContextHolderFilter` semantics: the filter loads the context without **auto-saving**. In Spring Security 6/7, this is the modern default direction; it is stated explicitly in the lesson to highlight the contract.

Legacy configurations can use `requireExplicitSave(false)` to revert to auto-save behavior for migration, yet **it should not be treated as a "fix" when custom login fails to save sessions**. Instead, locate where authentication succeeds and explicitly invoke the repository to save the context.

Spring Security documentation states clearly that in 6/7, custom code manually populating `SecurityContextHolder` must save explicitly if persistence is desired. <https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html>

## 5. Why does built-in form login save the session, while your custom login does not?

A common confusion:

> "Spring Security 6 requires explicit save, so why can I use `formLogin()` without writing `saveContext` myself and still stay logged in?"

Because **the authentication filter provided by the framework** performs context saving as part of its flow. For form login, `UsernamePasswordAuthenticationFilter` inherits `AbstractAuthenticationProcessingFilter`'s logic and uses `SecurityContextRepository` upon successful authentication. The fact that **the context-loading filter does not auto-save** does not mean **no component in the application saves**.

Distinction:

- **Default form login:** the framework handles authentication, session fixation protection, success/failure handling, and saving the context per configuration.
- **Code manually calling `AuthenticationManager.authenticate` in a controller:** the application is stepping into what the framework usually does; you must design how `SecurityContext` is set/saved, handle session strategy, CSRF, failures, logout, auditing, and prevent credential leakage.
- **HTTP Basic:** can authenticate via header on each request; do not assume it always creates a login session for a headerless next request. Behavior depends on filter/repository/session config, not on `SecurityContextHolder` existing.
- **Bearer/JWT:** requests are normally authenticated from the current token; that does not mean it becomes a server-side session login.

If you only test `Authentication` inside the active request, you have not proven session persistence. A proper test must send a **second request** with the appropriate cookie/session.

## 6. Complete Java 17+ example: saving via session and loading in next request

We will build a Spring Boot 4.1.2 application using form login. The example is designed for observing the repository clearly: instead of writing a custom login filter that risks breaking session fixation/CSRF, we use standard form login and explicitly configure `DelegatingSecurityContextRepository`.

Goals:

1. `GET /public` is accessible without logging in.
2. `GET /me` while unauthenticated redirects to the login page.
3. Form login with user `mai` and the demo password creates an authenticated context saved into the session.
4. A second request with that session calling `GET /me` returns `mai`.
5. A unit-style test with mock servlet requests proves `saveContext` is required when the application saves manually.
6. Do not disable CSRF for tests; use `spring-security-test` support for valid form login.

### 6.1. Project structure

~~~text
security-context-repository-lab/
  pom.xml
  src/main/java/com/example/contextrepo/
    ContextRepositoryApplication.java
    SecurityConfiguration.java
  src/test/java/com/example/contextrepo/
    SecurityContextRepositoryTest.java
~~~

### 6.2. pom.xml

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-context-repository-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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

Boot 4 uses the `spring-boot-starter-webmvc` starter instead of `spring-boot-starter-web` seen in many Boot 3 articles. `@AutoConfigureMockMvc` in Boot 4 lives in `org.springframework.boot.webmvc.test.autoconfigure`. The dedicated test starters provide MockMvc and Spring Security Test support. The Boot BOM manages compatible Spring Security versions; there is no need to pin versions for `spring-security-web` or `spring-security-test`.

### 6.3. Application + controller

Create `src/main/java/com/example/contextrepo/ContextRepositoryApplication.java`:

~~~java
package com.example.contextrepo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ContextRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextRepositoryApplication.class, args);
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

The controller merely reads the identity loaded by filters for the request. It does not read passwords from the session, does not save `SecurityContext`, and does not self-create authenticated tokens.

### 6.4. SecurityConfiguration

Create `src/main/java/com/example/contextrepo/SecurityConfiguration.java`:

~~~java
package com.example.contextrepo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        return http
            .securityContext(sc -> sc
                .securityContextRepository(repository)
                .requireExplicitSave(true)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .build();
    }
}
~~~

Analysis:

1. The `SecurityContextRepository` bean is `DelegatingSecurityContextRepository` combining **RequestAttribute** and **HttpSession**. This corresponds to the default pair commonly used by Spring Security.
2. `HttpSecurity.securityContext(...).securityContextRepository(repository)` ensures the chain uses the exact configured repository object. When specifying a custom repository, make sure related authentication filters use **the same strategy**.
3. `.requireExplicitSave(true)` highlights modern semantics: `SecurityContextHolderFilter` does not auto-save.
4. `.formLogin(form -> form.permitAll())` enables the standard login page/filter, allowing the login page and processing login per Spring Security's flow.
5. `InMemoryUserDetailsManager` provides a demo user; `PasswordEncoder` uses BCrypt. This is not how production user management should be done.
6. The `/public` rule allows anonymous. `/me` requires authenticated.
7. **Do not disable CSRF**. Form login POST must send a valid CSRF token; tests use the Spring Security Test helper.

When the application starts, the repository bean **does not yet contain Mai's identity**. Only when an authentication request succeeds and the flow saves the context does the session contain the corresponding result.

### 6.5. MockMvc testing: two requests sharing a session

Create `src/test/java/com/example/contextrepo/SecurityContextRepositoryTest.java`:

~~~java
package com.example.contextrepo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextRepositoryTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SecurityContextRepository repository;

    @Test
    void formLoginSavesContextForNextRequest() throws Exception {
        MvcResult login = mvc.perform(
                    formLogin().user("mai").password("demo-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        assertNotNull(session.getAttribute(
            HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY));

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));
    }

    @Test
    void explicitSaveMakesContextAvailableToLaterRequest() {
        MockHttpServletRequest first = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                    "mai", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
        );

        assertFalse(repository.containsContext(first));
        repository.saveContext(context, first, response);
        assertTrue(repository.containsContext(first));

        MockHttpSession session =
                (MockHttpSession) first.getSession(false);
        assertNotNull(session);

        MockHttpServletRequest next = new MockHttpServletRequest();
        next.setSession(session);
        SecurityContext loaded =
                repository.loadDeferredContext(next).get();

        assertEquals("mai", loaded.getAuthentication().getName());
    }

    @Test
    void anonymousMayReadPublicEndpoint() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
~~~

These tests illustrate **two different levels**:

- `formLoginSavesContextForNextRequest` uses the real filter chain + form login + session. The second request `GET /me` does not resend the password, yet still returns `mai`. This is a direct test for cross-request persistence.
- `explicitSaveMakesContextAvailableToLaterRequest` creates a mock `Authentication` **strictly inside a unit-style test**, calls the repository directly, and passes `MockHttpSession` to the next request. It tests the `saveContext`/`loadDeferredContext` API, **not** that constructing an authenticated token from client input is safe.
- `anonymousMayReadPublicEndpoint` confirms the `permitAll` policy; it does not prove context was saved.

Do not use `@WithMockUser` to prove password login was saved in the session; that annotation mainly sets a test `SecurityContext`, bypassing the real authentication flow and session saving. Using `formLogin()` pushes the test properly through the login filter, including the CSRF token supplied by the helper.

### 6.6. Running the app and verifying

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

When tests pass, Maven/Surefire displays three passing tests (alongside environment-dependent log output). There is **no fixed stdout to assert** like a standalone Java program; what matters are passing assertions and HTTP responses `public`/`mai`.

Try in a browser:

1. Open `http://localhost:8080/public`: body is `public`.
2. Open `http://localhost:8080/me` while logged out: redirected to the login page.
3. Log in with username `mai`, password `demo-password`.
4. Re-open `http://localhost:8080/me`: body is `mai`.
5. Open a separate private/incognito window without the session cookie: accessing `/me` requires logging in again.
6. Perform logout through the configured flow if needed; with Spring Security CSRF active, POST logout requires a valid CSRF token.

These demo values are for local use only. In production, always use HTTPS, `Secure`/HttpOnly/SameSite cookies as needed, session timeouts, and proper session management policies. **Never** put real passwords in scripts, logs, or terminal commands that may persist in history.

### Why not demonstrate with curl -X POST /login without CSRF?

Servlet form login has CSRF protection enabled by default. A login POST containing only `username` and `password` **missing the CSRF token** can be rejected with 403, creating the impression persistence failed when it is actually the CSRF filter. For automation, use browser tests/MockMvc with a valid token or explicitly execute the flow to fetch/send a valid token and cookie.

## 7. Custom login: explicit setContext followed by saveContext

Some applications write a custom `POST /api/login` in a controller. If code looks like:

~~~java
Authentication authentication =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            username, password
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// MISSING if you want to keep login across the next request:
return ResponseEntity.noContent().build();
~~~

This is a **fragment illustrating the bug**, not a standalone class. The current request has `Authentication`, yet `SecurityContextHolderFilter` does not automatically write the context to the repository. The next request may still be anonymous.

Fixed version in the right place after successful authentication:

~~~java
// Fragment inside a CUSTOM controller/filter, requiring existing dependencies.
// username/password have been retrieved and verified via AuthenticationManager;
// request/response are jakarta.servlet.http.HttpServletRequest/Response.

Authentication authentication =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            username, password
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context, httpServletRequest, httpServletResponse
);

return ResponseEntity.noContent().build();
~~~

**Important:** this is an **explicit-save explanatory fragment**, NOT a production login implementation you can copy verbatim safely. A custom login endpoint also needs: client-appropriate CSRF, session fixation protection (`SessionAuthenticationStrategy` where appropriate), safe username/password input handling and cleanup, auth failure handlers, events/auditing, session concurrency, rate limiting, cookies/HTTPS, logout, and error handling. Built-in form login already addresses many of these, so prefer it when applicable.

Ordering point: call `saveContext` **before the response commits** so the session/cookie can be created and sent properly. Do not place the save call after `sendRedirect`, after `getWriter()` has flushed, or once the response has committed. If custom code requires a redirect, save the context successfully first and then redirect.

### Why create a fresh SecurityContext instead of mutating the existing object?

In many official examples, Spring Security recommends:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Instead of:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Creating a new context avoids accidentally mutating a context shared or restored from session, and makes the moment of identity change explicit. Depending on the mechanism, mutating the current context can cause side effects for other requests sharing the same session reference. Not every mutation is necessarily wrong, yet **createEmptyContext → setAuthentication → setContext → save** is easier to reason about and test.

### Do not store passwords inside persisted Authentication

After login, the context saved to the session must not keep raw passwords, OTPs, or unnecessary bearer tokens. `ProviderManager` has a mechanism to erase result credentials when enabled, yet custom providers/principals might still retain secrets internally. Check `CredentialsContainer` and the session lifecycle to avoid persisting secrets into long-term storage.

## 8. How do SecurityContextRepository and SessionCreationPolicy relate?

The two settings are related, yet **they are not the same thing**:

- `SecurityContextRepository` answers **where and how the context is saved/loaded**.
- `SessionCreationPolicy` answers **how Spring Security will create/use HttpSession** per policy.

Common values:

| Policy | General meaning | What to distinguish |
| --- | --- | --- |
| `ALWAYS` | Spring Security proactively creates a session | Not every endpoint needs one; consider load |
| `IF_REQUIRED` | Creates a session when a mechanism needs one | Fits many form-login apps |
| `NEVER` | Spring Security does not proactively create a session, yet can use an existing one | **Does not** mean completely stateless |
| `STATELESS` | Spring Security neither creates nor uses HttpSession to obtain SecurityContext | Other parts of the app may still create sessions; inspect the whole architecture |

For a stateless bearer-token API, you can configure:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

Requires importing `org.springframework.security.config.http.SessionCreationPolicy`. This is a Servlet configuration fragment; to actually verify bearer tokens you must configure a resource server, decoder, and policies. Never simply add `STATELESS` to a session-based form login app and expect persistent login to keep working normally.

An illustrative setup that does not persist `SecurityContext` via session:

~~~java
http.securityContext(sc -> sc
    .securityContextRepository(new NullSecurityContextRepository())
);
~~~

However, never blindly mix `STATELESS`, `NullSecurityContextRepository`, and form login without understanding which mechanism authenticates each request. **Stateless does not mean skipping Authentication checks**; it usually means every request must carry its own verifiable proof.

### When using multiple SecurityFilterChains

You can configure `/api/**` as stateless and the remaining web routes with stateful form login:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(sm -> sm
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

**This is an illustrative fragment**, needing `@Configuration`/imports/resource-server dependencies/JWT decoder and practical login/CSRF handling. `@Order` controls which chain is evaluated first; only the first matching chain handles a request. Each chain's `SecurityContextRepository` can differ. Never allow web-chain cookies to implicitly authorize a stateless API chain unless there is an explicit architectural decision.

## 9. When does saveContext NOT create a session?

Many learners mistakenly assume `saveContext` means "guaranteed Set-Cookie". In practice, it depends on the implementation and context contents.

`HttpSessionSecurityContextRepository` may **skip saving context** in situations such as:

- The context is still empty/default and carries no accepted Authentication.
- Authentication is anonymous according to `AuthenticationTrustResolver`.
- The context has not changed according to save-decision rules.
- `allowSessionCreation=false` and no existing session is available.
- The response already committed before a new session/cookie needed to be set, depending on invocation and container.

Therefore, tests should verify **the existence of a real authenticated context in the subsequent request** instead of only asserting `saveContext` was called or relying solely on a `Set-Cookie` header. `SecurityContextRepository.containsContext(request)` is useful within the same request, yet you must still test cross-request behavior when the requirement is "the user stays logged in".

### Should the session key be changed?

`HttpSessionSecurityContextRepository` provides `SPRING_SECURITY_CONTEXT_KEY` and `setSpringSecurityContextKey`. In ordinary applications, **there is no need to change the key**; an out-of-sync change between filter and repository prevents context restoration.

If using Spring Session Redis/JDBC to share sessions across nodes, verify serialization, TTL, session migration, session fixation, cleanup, and session-store access controls. Using `SecurityContextRepository` does not automatically distribute sessions across machines when the servlet container stores sessions in a single node's memory.

## 10. Error dispatches, async dispatches, and request attributes

A Servlet request may be dispatched multiple times within the same lifecycle:

~~~text
REQUEST /profile
    |
    +--> SecurityContextHolderFilter
    |       loads context
    |
    +--> controller throws exception
    |
    +--> ERROR dispatch /error
            |
            +--> filter/security handling per dispatcher type
            +--> request attribute holds context within same request
            +--> error handler processes per policy
~~~

`RequestAttributeSecurityContextRepository` helps because `SecurityContextHolder` may already have been cleared during a dispatch transition. However, **not all containers/filters behave identically**. Practical checks to run:

- Does the error dispatch pass through the Spring Security filter chain?
- Do `/error` endpoints have appropriate policies?
- Is the request attribute preserved across dispatches of the same request?
- Does another error handler accidentally turn Security's 401/403 into a 500?
- Are identifiers, claims, stack traces, or tokens leaked in error responses?

Async processing is even trickier: work on another thread does not automatically receive `SecurityContextHolder` from the initial thread. Use appropriate propagation mechanisms (`DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, MVC async integration...) when needed. **`SecurityContextRepository` is not a tool for automatically propagating ThreadLocal across threads**. Saving to request/session and propagating context across execution threads are related but distinct problems.

## 11. Logout: where is context removed, and which cookies remain valid?

When a user logs out, calling only:

~~~java
SecurityContextHolder.clearContext();
~~~

is normally **not enough** to claim the session was invalidated on the server or that the next request will not load context back from the repository. If the session still holds `SPRING_SECURITY_CONTEXT`, a subsequent request carrying the old cookie can still load that identity.

Spring Security's standard logout flow uses `LogoutFilter` and associated `LogoutHandler`s to clear context, invalidate the HTTP session, and update `SecurityContextRepository`, depending on configuration.

A common Servlet configuration:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
);
~~~

This is a fragment to understand policy; the logout endpoint/method is affected by CSRF and URL configuration. In a browser app with CSRF enabled, logout usually requires POST with a CSRF token. Browser cookies and server sessions may have independent lifecycles; with Spring Session or SSO, revoking tokens/sessions in other systems requires additional integration.

**Do not confuse:** clearing ThreadLocal context, removing session attributes, invalidating sessions, deleting browser cookies, and revoking JWT/refresh tokens are distinct actions. A multi-device application may need to manage all sessions of an account or a specific device.

## 12. SecurityContextRepository is not the source of truth for authorization

A `SecurityContext` stored in a session typically holds the `Authentication` accepted at login time. It **does not automatically guarantee** that the account is still enabled or that its authorities have not changed.

Example:

~~~text
09:00 Mai logs in:
  repo saves Authentication(username=mai, authorities=[ROLE_ADMIN])

09:15 Admin revokes Mai's ROLE_ADMIN in database:
  DB changed, yet previous session still holds authorities snapshot.

09:20 Mai sends GET /admin with session cookie:
  repo may reload old Authentication.
  Without revocation/re-evaluation, old role may still take effect.
~~~

To protect sensitive actions, an application needs a **refresh or revocation** policy:

- Invalidate a user's sessions when the account is locked, deleted, or has roles changed.
- Store a security version/permission version in the session and validate against current state.
- Check current membership/role/owner/tenant in the service according to risk level.
- Bound session lifetime, idle timeout, and use reauthentication/step-up for critical operations.
- Evaluate cache invalidation and consistency when running multiple nodes.

**The repository only handles where context is stored/loaded, not a policy engine checking every database change.** Never treat permissions stored in a session as immutable forever.

## 13. Common design mistakes

1. **"SecurityContextHolder keeps Authentication forever."** Wrong: by default it is thread-bound, not long-term storage.
2. **"SecurityContextRepository is just another layer of UserDetailsService."** No: one saves/loads context; the other loads user records for authentication.
3. **"Setting SecurityContextHolder is enough for the next request."** No in explicit-save flows; you must call the repository to save if persistence is wanted.
4. **"SecurityContextHolderFilter auto-saves at the end of a request."** Wrong: the modern filter's job is loading, not auto-saving.
5. **"Both SecurityContextHolderFilter and SecurityContextPersistenceFilter should be added to be safe."** No; they serve the same purpose and must not coexist in one chain.
6. **"Calling saveContext always creates a new HTTP session."** No: it depends on context contents, session policy, and implementation.
7. **"RequestAttributeSecurityContextRepository keeps login across multiple requests."** No: it applies within the same servlet request.
8. **"NullSecurityContextRepository automatically authenticates JWTs."** No: you need an appropriate authentication filter/decoder.
9. **"A Spring Session store makes every user share one SecurityContext."** No: context must remain isolated per session/identity; misconfiguration would be extremely dangerous.
10. **"SessionCreationPolicy.NEVER equals STATELESS."** No: NEVER can still use an existing session.
11. **"formLogin() still fails to save because SecurityContextHolderFilter does not save."** The framework's authentication filter handles saving in its success flow.
12. **"I added a custom login controller and only called setContext, that's enough."** No: if subsequent requests must recognize the user, explicit save is required.
13. **"Controller @WithMockUser test returning 200 proves context was saved."** No: the annotation populates a mock Authentication solely for the test.
14. **"A 403 login failure proves session saving failed."** It may be a missing CSRF token, unrelated to persistence.
15. **"HTTP Basic needs no header on the next request because the previous one entered SecurityContextHolder."** Not by default: Basic typically verifies each request by header, depending on configuration.
16. **"SecurityContextRepository auto-propagates context to every async thread."** No; you need an appropriate strategy/wrapper.
17. **"clearContext() is equivalent to logging out all devices."** No; session/token lifecycles are separate.
18. **"Once ROLE_ADMIN is saved in the session, permissions never change."** Wrong: it can become stale after database updates.
19. **"Every saveContext call should happen after redirect."** Wrong: by then the response may be committed and unable to create a session/cookie.
20. **"A request attribute is a browser cookie."** No: attributes exist only on the server-side servlet request.
21. **"Having a SecurityContext means the user is always authenticated."** The context may be empty; you must examine `Authentication` and anonymous handling.
22. **"Changing the SPRING_SECURITY_CONTEXT key makes all clients switch automatically."** No; this is a server-side key that must stay synchronized.
23. **"Setting requireExplicitSave(false) is the standard fix for all custom login issues."** No; prefer performing explicit save properly in the modern flow.
24. **"Using HttpSession repository means all sessions are securely protected by default."** You must also protect cookies, TLS, session fixation, timeouts, server stores, and revocation.

## 14. Required testing matrix

| Scenario | Check | Expected |
| --- | --- | --- |
| Public GET when anonymous | `/public` | HTTP 200, body `public` |
| GET `/me` when unauthenticated | Browser or MockMvc GET | Redirect to login or matching entry point |
| Valid form login | POST /login with proper CSRF/session | Authentication succeeds, context saved to session |
| Next request reusing session | GET /me without resending password | HTTP 200, body `mai` |
| Request without cookie | GET /me in private browser | Mai is not recognized; login required again |
| Only set context in custom code | Omit saveContext | Next request **does not automatically** restore identity |
| Custom code calls saveContext | Same repository and uncommitted response | Next request restores if session remains valid |
| Session invalidated | Reuse old cookie/session | Must no longer authenticate |
| Account disabled after login | Request with old session | Revocation behaves per clear policy; do not trust snapshot indefinitely |
| Role revoked after login | Request to sensitive resource | Check session refresh/re-evaluation/revocation |
| ERROR dispatch | Request already has context, then throws exception | Context is not unexpectedly lost in matching dispatch |
| Stateless bearer API | No HTTP session persistence | Every request requires valid token, not web login cookie |
| Early response commit | Redirect/flush right after custom login | Context saved **before** commit |
| Async thread | Hand off to executor | Context propagated/cleared properly if business logic requires |
| `@WithMockUser` test | Mock user bypasses login filter | Do not treat as proof of session persistence |
| Custom repository | Per-chain configuration | Matching chain uses the right repo and filter |

You should also inspect the **actual filter chain configuration** via debug logs in dev:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

When verifying exactly which filters execute, TRACE logging in a controlled environment or a debugger can help. **Never log session cookies, Authorization headers, or passwords** in production logs. Session-related bugs often require checking client cookies, the server session store, and the chain's policies together.

## 15. Practice exercises

**Exercise 1 — replace request attribute with session-only.** In the demo project, replace `DelegatingSecurityContextRepository` with `HttpSessionSecurityContextRepository` and re-run tests. Cross-HTTP-request persistence tests may still pass. Compare how context is preserved on an ERROR dispatch to see why RequestAttribute repository is useful.

**Exercise 2 — omit session save in a custom flow.** Try an isolated custom authentication flow in a test that calls `SecurityContextHolder.setContext` without `saveContext`. Send a new request with no bearer credentials but the same cookie/mock session. Observe that the context is not automatically written by `SecurityContextHolderFilter`.

**Exercise 3 — use NullSecurityContextRepository.** In a separate test configuration, configure a Null repository; verify the next request does not restore identity via HTTP session. Do not merely add a Null bean to the context and assume every chain uses it automatically.

**Exercise 4 — session fixation.** Log in via form in a browser and check how the session ID is handled per Spring Security's fixation protection policy. Never copy a custom login controller containing only `saveContext` and skip this part.

**Exercise 5 — role revocation.** Log in with `ROLE_ADMIN`, then revoke that authority in the user repository. Test the `/admin` API while the old session remains active; add invalidation/version checks or live-data authorization.

**Exercise 6 — multiple chains.** With a web session chain and a stateless API chain, write tests distinguishing web cookies from API bearer tokens. Ensure requests outside `securityMatcher` do not fall outside all security policies.

## 16. Self-check questions

**Q1.** What is the main role of `SecurityContextRepository` in Servlet?

*Answer:* It is the strategy for loading/saving `SecurityContext` across servlet requests or dispatches per the implementation's scope; it is not a password verifier.

**Q2.** Why can `SecurityContextHolder` be cleared at the end of a request while the user stays logged in on the next request?

*Answer:* Because the context was saved to a repository such as the HTTP session; the next request reloads the context and attaches it to the current thread's holder.

**Q3.** Does `RequestAttributeSecurityContextRepository` keep a user logged in permanently in the browser?

*Answer:* No; request attributes belong to a single ServletRequest and do not persist across two independent HTTP requests.

**Q4.** Which API method should be preferred over the deprecated `loadContext(HttpRequestResponseHolder)`?

*Answer:* `loadDeferredContext(HttpServletRequest)`, then reading `DeferredSecurityContext.get()` when needed.

**Q5.** How do `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter` differ in the save step?

*Answer:* HolderFilter loads context without auto-saving; legacy PersistenceFilter had an auto-save mechanism when context changed.

**Q6.** A custom controller called `setContext(context)` after authentication; why is the next request still anonymous?

*Answer:* Under explicit save, it did not call `SecurityContextRepository.saveContext(context,request,response)` on a suitable repository, or the response/session could not be written.

**Q7.** Why does built-in form login still preserve the session in modern Spring Security?

*Answer:* The framework's authentication filter handles the success flow and saves context per configuration; HolderFilter not auto-saving does not prevent other authentication components from saving explicitly.

**Q8.** Are `SessionCreationPolicy.NEVER` and `STATELESS` equivalent?

*Answer:* No. NEVER does not proactively create a session yet can use an existing one; STATELESS does not use HTTP session to obtain SecurityContext.

**Q9.** Does a `SecurityContext` existing in the HTTP session prove the current roles in the DB are still valid?

*Answer:* No; it may be a snapshot from login time. Refresh/revocation or live permission checks must be designed.

**Q10.** Does `SecurityContextRepository.saveContext` log out a JWT token on the user's device?

*Answer:* No; it is a server-side context-saving API. JWTs have their own validation/lifetime/revocation mechanisms.

**Q11.** To test persistence across requests, why must two separate requests be executed?

*Answer:* Because inspecting `SecurityContextHolder` within a single request does not prove the context was saved and reloaded from the repository.

**Q12.** When custom login needs to create a session cookie, must save be called before or after `sendRedirect`?

*Answer:* Before the response commits/redirects, so there is still an opportunity to save the context and send a valid session identifier.

## 17. Pre-production checklist

- [ ] Correct Servlet stack and using `SecurityContextRepository` from `org.springframework.security.web.context`, not mixing WebFlux's `ServerSecurityContextRepository`.
- [ ] Clear knowledge of whether each chain uses `SecurityContextHolderFilter` (explicit save) or a legacy mechanism; never add both.
- [ ] Know whether the active repository is HttpSession, RequestAttribute, Delegating, or Null and why that choice fits.
- [ ] If using custom login, perform `createEmptyContext → setAuthentication → setContext → saveContext` after trusted authentication.
- [ ] Response is not committed before saving context that must create a session/cookie.
- [ ] Session fixation, CSRF, failure/success handlers, concurrency, logout, and timeouts are thoroughly designed.
- [ ] No raw passwords, OTPs, bearer tokens, or redundant sensitive data stored in `Authentication`/session.
- [ ] Session cookies use TLS/`Secure`/`HttpOnly`/`SameSite` appropriate for the application.
- [ ] If using a stateless API, requests authenticate from dedicated proof; no unintended reliance on web session cookies.
- [ ] Real cross-request tests with cookies/sessions exist, not just `@WithMockUser` tests.
- [ ] Tests exist for logout/invalid sessions and requests after user disabling or role revocation.
- [ ] REQUEST, ERROR, and ASYNC dispatches are distinguished; no accidental logging or exposure of SecurityContext on error pages.
- [ ] Context propagation is configured for async/thread pools, with proper holder cleanup per lifecycle.
- [ ] Across multiple nodes, session store/serialization/TTL/invalidation are designed explicitly; no hidden reliance on single-node in-memory sessions.
- [ ] Persisted authorities are never assumed always fresh; sensitive actions check authorization against current sources.
- [ ] `securityMatcher`, `@Order`, session policy, and repository are verified for every chain.
- [ ] When debugging, verify both that context was **saved** after login and **loaded** on the subsequent request.
- [ ] Session/repository error monitoring exists without leaking cookies, bearer tokens, or passwords in logs.

### Summary

**`SecurityContextHolder` holds the context for current processing; `SecurityContextRepository` decides where that context is loaded from and saved to.** In modern Servlet apps, `SecurityContextHolderFilter` handles loading without auto-saving. Framework-provided form login already includes a component that saves explicitly; **custom authentication code** must call `saveContext` in the right place if identity must persist to the next request.

Always clarify the repository's **scope**: HTTP session spans multiple requests, request attribute serves one request across dispatches, Null repository saves nothing, and Delegating combines scopes as appropriate. Finally, saving context does not replace cookie/session protection, timeout management, logout handling, or updating permissions after business data changes.

### Official documentation

- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security — SecurityContextHolderFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/SecurityContextHolderFilter.html)
- [Spring Security — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security — RequestAttributeSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html)
- [Spring Security — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html)
- [Spring Security — NullSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/NullSecurityContextRepository.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Boot 4 — Starters and Test Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
