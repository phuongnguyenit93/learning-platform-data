# SecurityContext and the Identity Lifecycle in a Request

> **Parent topic:** Security Context. This lesson focuses on Spring Security 6.x on Servlet/Spring MVC, Java 17+, and Spring Boot 3.x. Goal: understand how identity is **loaded, established, used, saved, and cleared** in an HTTP request; distinguish `SecurityContext`, `SecurityContextHolder`, `Authentication`, and `SecurityContextRepository`; and compare session-based form login with stateless HTTP Basic, anonymous authentication, request dispatch, and async. Examples include Spring Boot source code and MockMvc tests.

## 1. What is SecurityContext?

In a web application, when Alice accesses `GET /me`, the controller often needs to know who the caller is. We cannot retrieve the "current user" from a global static variable: many HTTP requests from many users are processed concurrently, and thread pools may reuse threads.

Spring Security solves this with the **security context**. This is an object holding an `Authentication` that represents the current identity information.

~~~text
SecurityContextHolder
    |
    v
SecurityContext
    |
    v
Authentication
    +-- principal: who is represented
    +-- credentials: authentication proof (may have been erased)
    +-- authorities: ROLE_USER, ROLE_ADMIN, scope, permission...
    +-- authenticated: state of the authentication object
~~~

Four distinct concepts:

| Concept | Responsibility | What it is not |
| --- | --- | --- |
| `Authentication` | Object describing an authentication request or the resulting identity | A mechanism that automatically authorizes every resource |
| `SecurityContext` | Container holding the current Authentication | A user database or an HTTP session |
| `SecurityContextHolder` | API/strategy for running code to access the SecurityContext | A persistent context store across requests |
| `SecurityContextRepository` | Loads and saves the SecurityContext according to policy | A `UserDetailsService` or `AuthenticationProvider` |

Example of reading the context:

~~~java
SecurityContext context =
    SecurityContextHolder.getContext();

Authentication authentication =
    context.getAuthentication();

if (authentication != null) {
    String name = authentication.getName();
    boolean authenticatedFlag =
        authentication.isAuthenticated();
}
~~~

This is a snippet and requires imports and an enclosing method. **`getContext()` returning non-null does not mean the user is logged in**. A context may have no Authentication yet or hold an `AnonymousAuthenticationToken`.

## 2. What steps does an HTTP request go through?

Consider a browser where Alice has logged in via form login. The browser sends the session cookie:

~~~http
GET /me HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-id>
~~~

Typical Servlet flow:

~~~text
HTTP request from browser
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy (springSecurityFilterChain)
    |
    +--> Select SecurityFilterChain by URL/request
    |
    v
SecurityContextHolderFilter
    |
    +--> SecurityContextRepository
    |       +--> Look up saved context (if any)
    |       +--> Or provide an empty context
    |
    v
Authentication filters, if the request carries credentials
    |
    +--> Basic / Form / Bearer / other mechanisms
    +--> AuthenticationManager + providers
    +--> If successful: place trusted Authentication into context
    |
    v
AnonymousAuthenticationFilter
    |
    +--> If no Authentication yet, create anonymous token
    |
    v
ExceptionTranslationFilter / AuthorizationFilter
    |
    +--> `.authenticated()`, `.hasRole()`, other policies
    +--> Allow or deny the request
    |
    v
DispatcherServlet -> Controller -> Service
    |
    +--> Read the current request's context
    |
    v
HTTP response / exception
    |
    v
Filter lifecycle ends
    |
    +--> SecurityContextHolder is cleared from the thread
    |
    v
Thread is ready to serve another request
~~~

This diagram is a **conceptual model**; it does not claim that every SecurityFilterChain contains every filter or that the sequence above is an exhaustive list. The exact order depends on the authentication mechanism, version, custom filters, and servlet dispatcher type.

Key point to remember: a request can **perform no new login** and still be recognized as Alice, because the context from the **previous login's HttpSession** is restored.

### 2.1. `SecurityFilterChain` is selected first

An application may have multiple chains:

~~~text
SecurityFilterChain #1: /api/**
  - HTTP Basic
  - STATELESS
  - do not persist identity across HttpSession

SecurityFilterChain #2: remaining URLs
  - Form login
  - save context into HttpSession on login
~~~

`FilterChainProxy` selects a chain by matcher and order. The security context is handled according to the chosen chain's policy. Do not configure `/api/**` and forget the fallback chain, leaving other URLs outside Spring Security.

### 2.2. `permitAll()` does not erase SecurityContext

An endpoint `/public` may be configured with `permitAll()`, yet it still runs through the Spring Security chain. Therefore `AnonymousAuthenticationFilter` can attach an AnonymousAuthenticationToken and the Controller can observe the context.

Distinction:
- `.permitAll()`: the filter chain still runs; only authorization permits the request.
- `web.ignoring()`/request matching no chain: may bypass all security filters and related protections.

When a public endpoint still needs security headers/anonymous/CSRF behavior, `permitAll` is generally preferred over bypassing the chain.

## 3. Loading the context at the start of a request

### 3.1. Role of `SecurityContextHolderFilter`

In Spring Security 6, `SecurityContextHolderFilter` is used under an explicit-save model. It interacts with a `SecurityContextRepository` so the security context is available when the request needs it, and clears the holder after the request completes.

**It does not automatically save every Authentication change made by custom code.** This is an important difference from the Spring Security 5 model using `SecurityContextPersistenceFilter`, which could automatically save the context at the end of a request. Framework authentication filters already integrate the appropriate persistence logic; if you write a custom login filter/controller, you must pay special attention to the save step.

### 3.2. What implementations of `SecurityContextRepository` exist?

| Implementation | Meaning | How long does it live? |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Saves context in HttpSession so subsequent requests can restore it | Follows the session lifecycle and logout/invalidation policy |
| `RequestAttributeSecurityContextRepository` | Holds context via request attributes, useful for certain ERROR dispatches | Within the same logical request; does not persist to a new HTTP request |
| `DelegatingSecurityContextRepository` | Combines multiple repositories, commonly request attribute + HttpSession | Follows each delegate's behavior |
| `NullSecurityContextRepository` | Neither saves nor restores state via repository | No persistence across requests |

The common default configuration in Spring Security 6 uses `DelegatingSecurityContextRepository`, combining HttpSession and request attribute. Do not assume `getContext()` means "query the database" — it retrieves the context the framework has established or restored.

### 3.3. Why does RequestAttributeSecurityContextRepository exist?

In Servlet, `REQUEST` and `ERROR` dispatches can occur within the same logical request. A controller authenticates Alice and then throws an exception; the container may run an ERROR dispatch after the initial holder has already been cleared.

The request attribute repository helps a properly saved context reappear during certain dispatches belonging to the **same request**, depending on container and configuration. It is **not a session store**: a new HTTP request from the browser cannot use an old request's request attribute to recognize Alice.

### 3.4. Deferred loading

Spring Security supports deferred context loading to avoid unnecessary session/context reads on certain requests. You should not assume every `getContext()` triggers a database query or that a request always loads the context exactly once. Actual interaction depends on the repository and when authentication is requested.

## 4. SessionCreationPolicy and identity lifecycle

| Value | Behavior related to HttpSession |
| --- | --- |
| `ALWAYS` | Spring Security may proactively create an HttpSession |
| `IF_REQUIRED` | Creates a session when needed, e.g., saving a successful login |
| `NEVER` | Does not proactively create a session, but **can use an existing session** |
| `STATELESS` | Does not use HttpSession to obtain SecurityContext or create a session for that purpose |

**`NEVER` differs from `STATELESS`.** The two policies are not interchangeable. `STATELESS` also does not mean "no Authentication": each Bearer/Basic request can still authenticate successfully and have an Authentication within that request.

### 4.1. Stateful session example

~~~text
POST /login: Alice provides username/password
   |
   v
Provider authenticates successfully
   |
   v
Context(Alice) is saved into HttpSession S1

GET /me + Cookie S1
   |
   v
Repository restores context(Alice)
   |
   v
/me allows
   |
   v
Thread's holder is cleared at end of request

GET /me + Cookie S1 again
   |
   v
Context(Alice) is restored again
~~~

**Clearing the holder at the end of each request** does not destroy the `HttpSession` and does not automatically log Alice out.

### 4.2. Stateless Basic example

~~~text
Request #1:
  GET /api/me
  Authorization: Basic alice:...
  -> filter verifies -> Authentication(Alice)
  -> Controller returns 200
  -> clear thread's context

Request #2:
  GET /api/me
  no Authorization header
  -> do not restore Alice from HttpSession
  -> endpoint requires authenticated
  -> 401 via Basic entry point
~~~

Request #1 has a complete context/authentication, even though the application does not persist it to Request #2. When the user supplies Basic on every request, the provider re-verifies; with JWT, the decoder/validator checks the token on every request and creates a fresh Authentication according to policy.

### 4.3. Stateless is not token revocation

An already issued JWT can still hold old roles/scopes after the database changes. Not storing a session only avoids server-side identity persistence, **it does not revoke an access token**; you need TTL, revocation, introspection, or live authorization if business rules require immediate effect.

## 5. Authentication created and updated mid-request

An HTTP Basic filter can create an **unauthenticated** token:

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "example-password"
    );

boolean before = attempt.isAuthenticated(); // false
~~~

This is an illustrative snippet. `AuthenticationManager`/`AuthenticationProvider` will verify credentials, check account status, and produce the resulting Authentication.

For username/password:
- `UserDetailsService` looks up the username and hash from the account store.
- `PasswordEncoder.matches(rawPassword, storedHash)` verifies the credentials.
- `DaoAuthenticationProvider` checks disabled/locked/expired status and issues the result.
- The filter places the verified Authentication into the context through a trusted mechanism.

**Do not use `UsernamePasswordAuthenticationToken.authenticated(...)` with client-sent authorities for a "quick login".** Code that constructs a trusted Authentication without verifying credentials is a security bypass.

### 5.1. Principal, credentials, authorities

After successful authentication, Authentication typically contains:
- **Principal:** `UserDetails`, `Jwt`, `OAuth2User`, or a custom principal, depending on the mechanism.
- **Credentials:** may be erased by `ProviderManager` and `CredentialsContainer`. Do not use `null` to infer a failed login.
- **Authorities:** permissions granted by a trusted provider/converter.
- **isAuthenticated():** a flag on the object; **does not by itself prove permission for every resource**.

### 5.2. What happens if nobody logs in?

`AnonymousAuthenticationFilter` typically populates an `AnonymousAuthenticationToken` into the context if no Authentication is present yet:

~~~text
principal = "anonymousUser"
authorities = [ROLE_ANONYMOUS]
isAuthenticated() may be true
~~~

This provides a uniform representation for anonymous requests. However, Spring Security uses `AuthenticationTrustResolver` to distinguish anonymous from real users; `.authenticated()` **does not let anonymous through** just because the raw flag is true.

In Spring MVC, an `Authentication` or `Principal` parameter resolved via the Servlet principal is sometimes **null for anonymous**, even though `SecurityContextHolder` already holds an AnonymousAuthenticationToken. To inspect anonymous, use `@CurrentSecurityContext SecurityContext context`.

### 5.3. Authentication and authorization

Example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/me").authenticated()
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

- Alice with `ROLE_USER` can access `/me`, but normally receives 403 at `/admin`.
- Anonymous accessing `/me` is challenged to log in by the authentication entry point.
- `ROLE_ADMIN` does not automatically permit operating on every tenant/owner's data; domain policy must check the specific resource.
- Authorities in Authentication may be a snapshot from login time, not always the latest roles in the database.

## 6. End of request: clearing ThreadLocal, never leaking Alice to Bob

`SecurityContextHolder` in Servlet defaults to `MODE_THREADLOCAL`: code on the same thread can access the context without passing it as a parameter to every method.

~~~text
Thread 1: Alice's GET /me
    |
    +--> context=Alice
    +--> authorization, controller
    +--> clear context

Thread 1 is reused: Bob's GET /me
    |
    +--> context=Bob or anonymous
    +--> must not still hold Alice's context
    +--> clear context
~~~

If cleanup is forgotten, the server risks **identity leakage across requests** because the thread pool reuses threads. Spring Security handles clearing in the filter-chain lifecycle for requests it manages. Code running outside the chain bears the corresponding responsibility.

### 6.1. `clearContext()` is not logout

~~~java
SecurityContextHolder.clearContext();
~~~

This line clears the current execution context according to the strategy. It **does not directly invalidate HttpSession**, revoke a JWT, delete a refresh token, or alter the account database. A new request carrying the same valid session cookie can still restore the saved context.

**Real logout** in a session-based app requires an appropriate logout mechanism: clearing SecurityContext, invalidating the session, and handling the repository/cookies/response. With stateless tokens, a revocation policy is needed if logout must take effect before token expiration.

### 6.2. Do not store Authentication in a static field

Anti-pattern:

~~~java
// WRONG: can share Alice's identity with Bob's request.
static Authentication currentUser;
~~~

If you need identity in a synchronous service handling the request, read the current context via Spring Security or pass a trusted account ID. If a long-running job needs data, pass minimal business data and design reauthorization.

## 7. Spring Security 6 and `requireExplicitSave`

In Spring Security 5, `SecurityContextPersistenceFilter` could automatically save context changes when the request ended or response committed. In Spring Security 6, the default model based on `SecurityContextHolderFilter` **only loads**, while saving a new context must be done **explicitly** by the authentication mechanism or custom code.

Description:

~~~text
Initial context from repository
    |
    v
SecurityContextHolderFilter places context into holder
    |
    v
Authentication filter/provider authenticates successfully
    |
    v
Place new Authentication into SecurityContext
    |
    +--> If persisting across requests is desired:
    |       SecurityContextRepository.saveContext(...)
    |
    v
Controller/response
    |
    v
Holder is cleared
~~~

Standard framework form login already handles the required persistence. However, if you write a custom login flow and only call `SecurityContextHolder.setContext(context)` **without saving**, subsequent requests may lose identity.

### 7.1. Custom authentication snippet with proper boundaries

~~~java
// Snippet after obtaining a trusted authenticationManager and repository.
// Runs in custom authentication code with HttpServletRequest/Response.

Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        usernameFromLogin, rawPasswordFromLogin
    );

Authentication verified =
    authenticationManager.authenticate(attempt);

SecurityContext freshContext =
    SecurityContextHolder.createEmptyContext();

freshContext.setAuthentication(verified);
SecurityContextHolder.setContext(freshContext);

// Only needed if the flow is designed to persist context to subsequent requests.
securityContextRepository.saveContext(
    freshContext, request, response
);
~~~

**Do not assign ADMIN authority to a self-declared token from the request and call save.** Verification by AuthenticationManager/Provider is mandatory before turning a token into a trusted Authentication. Save the context at the right moment before the response is committed if the application needs to create a session/cookie.

### 7.2. Why is `createEmptyContext()` recommended?

~~~java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

A SecurityContext is usually mutable; mutating the Authentication directly on a context shared across multiple threads or concurrent session requests can cause race conditions or unexpected state. Creating a fresh context when setting a new Authentication avoids unintended sharing bugs.

### 7.3. Do not call save in every controller

If you use standard form login, there is no need to add `saveContext` in every controller just to stay logged in. If you use stateless HTTP Basic, you **should not** force saving into HttpSession against the architecture. Distinguish authentication flow from persistence policy.

## 8. Spring MVC: three ways to read identity

### 8.1. `Authentication` parameter

In an endpoint restricted to logged-in users:

~~~java
@GetMapping("/me")
public String me(Authentication authentication) {
    return authentication.getName();
}
~~~

This is a snippet inside a @RestController on a protected endpoint. Spring MVC may rely on the Servlet principal resolver, so anonymous can receive null; avoid dereferencing it in public endpoints.

### 8.2. `@CurrentSecurityContext`

~~~java
@GetMapping("/public/context")
public String publicContext(
        @CurrentSecurityContext SecurityContext context) {
    Authentication auth = context.getAuthentication();
    return auth == null ? "none" : auth.getName();
}
~~~

This reads Spring Security's current context and can observe the anonymous Authentication when the anonymous filter is active.

### 8.3. `@AuthenticationPrincipal`

~~~java
@GetMapping("/profile")
public String profile(
        @AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

Only use the `UserDetails` type if the provider actually supplies a principal of that type. With a JWT Resource Server it may be Jwt, and with OAuth2 Login it may be OidcUser/OAuth2User. Do not blindly cast every principal to UserDetails.

### 8.4. Safe DTO

Never return `Authentication`, `SecurityContext`, `UserDetails`, or `Jwt` directly as JSON. They may contain password hashes, tokens, claims, and metadata not meant for clients. The demo below returns a minimal DTO: name, principal type, authorities, anonymous, and authenticated flag — strictly for learning purposes.

## 9. Spring Boot 3 Demo: two filter chains to see different lifecycles

The demo includes:
- `/public` and `/public/context`: public; the second endpoint observes anonymous Authentication.
- `/me`: form login + session; subsequent requests with the cookie still see Alice.
- `/admin`: requires ROLE_ADMIN; Alice lacks sufficient authority.
- `/api/me`: HTTP Basic + stateless; the next request must carry its own credentials.
- `/api/public`: public through the API chain, without form-login session.

### 9.1. Dependencies and structure

Create a Spring Boot **3.x**, Spring Security **6.x**, Java **17+** project with Gradle Wrapper plugins and repositories configured. In the existing `build.gradle`, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is only the dependencies block, not a standalone build.gradle. Files:

~~~text
src/main/java/com/example/contextlife/
  ContextLifeApplication.java
  SecurityConfig.java
  ContextController.java

src/test/java/com/example/contextlife/
  ContextLifecycleTest.java
~~~

### 9.2. ContextLifeApplication.java

~~~java
package com.example.contextlife;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextLifeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextLifeApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfig.java

~~~java
package com.example.contextlife;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(ctx -> ctx
                .securityContextRepository(
                    new NullSecurityContextRepository()
                )
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/public", "/public/context")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/public")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );

        return http.build();
    }
}
~~~

Analysis:

1. **Two filter chains:** `/api/**` is handled first (`@Order(1)`), and all other URLs use the fallback (`@Order(2)`).
2. **API:** enables HTTP Basic, does not use HttpSession as SecurityContextRepository, and request cache does not store saved requests. One authenticated API request does not turn the next unauthenticated request into Alice.
3. **Web:** enables standard form login and permits the login page/login processing URL. Form login creates a session when required and persists Authentication through the framework's repository.
4. **Authorization:** `/me` requires authenticated; `/admin` requires ROLE_ADMIN; other paths are deny-by-default.
5. **CSRF:** CSRF is not disabled for the web chain. POST `/login`/`logout` must submit a CSRF token while protection is enabled.
6. **Demo credentials:** `alice123`/`admin123` are only for learning on localhost; in production use a database with hashed passwords, HTTPS, session-cookie security, and rate-limiting.

### 9.4. ContextController.java

~~~java
package com.example.contextlife;

import java.util.List;
import java.util.Objects;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ContextController {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/public/context")
    public ContextView publicContext(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context);
    }

    @GetMapping("/me")
    public ContextView me(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context);
    }

    @GetMapping("/api/me")
    public ContextView apiMe(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context);
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin-only";
    }

    private ContextView describe(SecurityContext context) {
        Authentication authentication = context.getAuthentication();
        if (authentication == null) {
            return new ContextView(
                "none", "none", false, true, List.of()
            );
        }

        List<String> authorities =
            authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .toList();

        String type = authentication.getPrincipal() == null
            ? "null"
            : authentication.getPrincipal()
                .getClass().getSimpleName();

        return new ContextView(
            authentication.getName(),
            type,
            authentication.isAuthenticated(),
            trustResolver.isAnonymous(authentication),
            authorities
        );
    }

    public record ContextView(
        String name,
        String principalType,
        boolean authenticatedFlag,
        boolean anonymous,
        List<String> authorities
    ) {}
}
~~~

The demo uses `@CurrentSecurityContext` because a public endpoint needs to read anonymous. `AuthenticationTrustResolver` distinguishes anonymous; `isAuthenticated()` alone is not sufficient. The DTO intentionally **excludes credentials, password hashes, and session IDs**.

### 9.5. Run and observe

From the project root with Gradle Wrapper present:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Test the Basic API and anonymous endpoints:

~~~bash
curl -i http://localhost:8080/public/context
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/public
~~~

Expected results:

| Request | HTTP | What to observe |
| --- | --- | --- |
| `/public/context` unauthenticated | **200** | `name=anonymousUser`, `anonymous=true`, authenticated flag may be true |
| `/api/me` without Basic | **401** | API chain requires authentication |
| `/api/me` with valid Alice Basic | **200** | `name=alice`, `anonymous=false`, ROLE_USER |
| `/api/me` without Basic right after valid request | **401** | No session-based identity persistence |
| `/api/public` without Basic | **200** | `api-public` |
| `/me` after form login with session | **200** | Alice is restored from HttpSession |
| `/admin` after Alice form login | **403** | Logged in, but missing ROLE_ADMIN |

Browser form login requires a CSRF token in POST `/login`; use the default login page or the MockMvc tests in the next section. Do not try removing CSRF just to "make it easy to run". These statuses are **expectations based on the source code**, not HTTP responses measured from a live server.

### 9.6. JSON examples

An anonymous request to `/public/context` can return:

~~~json
{
  "name": "anonymousUser",
  "principalType": "String",
  "authenticatedFlag": true,
  "anonymous": true,
  "authorities": ["ROLE_ANONYMOUS"]
}
~~~

A valid Basic request to `/api/me`:

~~~json
{
  "name": "alice",
  "principalType": "User",
  "authenticatedFlag": true,
  "anonymous": false,
  "authorities": ["ROLE_USER"]
}
~~~

Both objects have `authenticatedFlag=true` in the demo, yet **only Alice** is a genuinely authenticated user. That is why custom authorization must not be implemented with `auth != null && auth.isAuthenticated()`.

## 10. MockMvc tests for identity across requests

Create `src/test/java/com/example/contextlife/ContextLifecycleTest.java`:

~~~java
package com.example.contextlife;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextLifecycleTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertNotNull(session);
        assertNotNull(
            session.getAttribute("SPRING_SECURITY_CONTEXT")
        );
        return session;
    }

    @Test
    void anonymousIsPresentOnlyInsideRequest() throws Exception {
        mvc.perform(get("/public/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("anonymousUser"))
            .andExpect(jsonPath("$.anonymous").value(true));

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void formLoginPersistsIdentityIntoLaterSessionRequest()
            throws Exception {
        MockHttpSession session = login("alice", "alice123");

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));

        // After MockMvc filter execution, the test thread's holder is cleared.
        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );

        // Another request with the same session still restores Alice.
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void twoSessionsAreIsolatedFromEachOther() throws Exception {
        MockHttpSession alice = login("alice", "alice123");
        MockHttpSession admin = login("admin", "admin123");

        mvc.perform(get("/me").session(alice))
            .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/me").session(admin))
            .andExpect(jsonPath("$.name").value("admin"));

        mvc.perform(get("/public/context"))
            .andExpect(jsonPath("$.anonymous").value(true));

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void basicAuthenticationIsNotPersistedForNextRequest()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"));

        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void newWebRequestWithoutSessionMustLogInAgain()
            throws Exception {
        login("alice", "alice123");

        // Do not attach login's MockHttpSession to this request.
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void publicRoutesAreInTheirRespectiveChains() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

Test suite explanation:

1. The public handler sees the anonymous context **inside the request**, and once the filter chain ends, the test thread has no Authentication left.
2. Form login stores SecurityContext in HttpSession; a browser sending back the session receives the same identity.
3. Using two sessions for Alice and admin sequentially on the test thread does not mix identities.
4. A Basic request with valid credentials returns Alice; the next Basic request missing credentials does not inherit the context.
5. Logging in via form is not enough for a new request **without a session cookie** to be automatically recognized.
6. Alice has a valid Authentication, yet `/admin` is still denied by the authority rule.

**Do not use `@WithMockUser` to prove session persistence.** `@WithMockUser` builds a fake Authentication to test authorization; it does not pass through the login filter/DaoAuthenticationProvider and does not prove that SecurityContextRepository saved the context from POST `/login`.

These outcomes are **assertions expected from the code**, not proof that Gradle tests have already been run. If using a custom login flow, request cache, entry point, or different Spring Security version, redirects/statuses may need adjustment in tests to match the application.

## 11. Async and thread pools: an important trap

By default Servlet uses `SecurityContextHolder.MODE_THREADLOCAL`. A task in another thread pool **does not automatically have** the Authentication of the request-processing thread.

Anti-pattern:

~~~java
new Thread(() -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    // May be null: this is a different thread.
}).start();
~~~

Do not fix this by setting `MODE_GLOBAL` on a multi-user server. `MODE_INHERITABLETHREADLOCAL` also requires caution, especially with reused thread pools and stale authorities.

### 11.1. Propagation via Spring Security's executor

Example snippet with an executor already existing in the application:

~~~java
DelegatingSecurityContextExecutor secureExecutor =
    new DelegatingSecurityContextExecutor(delegateExecutor);

secureExecutor.execute(() -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    // Only perform work within valid permissions.
});
~~~

`delegateExecutor` is a lifecycle-managed `Executor`; the snippet needs imports. Spring Security's helper propagates the context into the submitted task and restores/clears the context around execution. However, **propagation is not re-authentication**, and the context snapshot can become stale when a job runs for a long time.

For long-running tasks, it is usually better to pass an immutable account ID, require valid delegation and check policy at execution time, or use a dedicated **service identity**. Do not keep raw credentials or an entire mutable Authentication in a long-lived queue.

### 11.2. WebFlux does not use this Servlet model

Reactive Spring WebFlux uses Reactor Context and `ReactiveSecurityContextHolder`; Servlet `ThreadLocal` does not apply directly across operators/threads. When migrating from MVC to WebFlux, you need to re-learn context propagation and `SecurityWebFilterChain`.

## 12. Request dispatch, errors, logout, and account changes

### 12.1. ERROR dispatch

In Servlet, a controller may throw an exception and the container routes to an ERROR dispatch. The initial dispatch's Context Holder may already have been cleared. `RequestAttributeSecurityContextRepository` can assist in restoring the context for the same logical request if properly saved. It is not guaranteed that every error handler will automatically see the user; check dispatcher configuration and repository.

### 12.2. Session timeout

Session expiration means a new request can no longer load the Authentication saved in the session. If the endpoint requires login, the framework typically redirects to `/login` with form login or returns 401 with Basic. **Session timeout** is different from `SecurityContextHolder.clearContext()` after each request.

### 12.3. Logout

Logout in web form apps usually consists of clearing SecurityContext, invalidating HttpSession, and handling repository/cookies. `GET /logout` is not the default production logout method when CSRF protection is active; the framework uses POST and a CSRF token for the state-changing logout action.

### 12.4. User locking and stale authorities

If an admin disables an account or revokes ROLE_ADMIN in the database, an existing session may still hold the previously created Authentication. `UserDetailsService` is not automatically called on every session-restoring request. You need session revocation, security-version checks, reauthentication, or resource-level live authorization if business rules require immediate permission updates.

### 12.5. JWT and non-HttpSession state

Each Bearer request can build a new Authentication from the JWT, yet an already issued JWT keeps its original claims. `clearContext()` at the end of a request **does not revoke a JWT**; revocation requires short TTLs, denylists, introspection, version checks, or another system-appropriate policy.

## 13. Common mistakes and how to avoid them

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Storing Authentication in a static field | Mixes identities across requests/threads | Read SecurityContext per proper lifecycle |
| Checking `getContext()!=null` as logged in | Context may be empty/anonymous | Use `.authenticated()` and policy |
| Only checking `isAuthenticated()==true` | Anonymous token can be true | Use trust resolver and authorization |
| Only calling `setContext` in custom login | Spring Security 6 explicit-save does not auto-persist | Call `saveContext` at the right time |
| Calling `clearContext` thinking it logs out | Only clears current holder | Use logout/session/token revocation |
| Using `NEVER` thinking it equals `STATELESS` | NEVER can still use an existing session | Choose the right policy |
| Forcing HttpSession writes in a stateless API | Breaks the stateless boundary | Authenticate per request |
| Returning raw SecurityContext JSON | Can leak principal/credentials | Return a minimal DTO |
| Copying context to `@Async` unconditionally | Context may fail to propagate or become stale | Use a supported executor strategy |
| Omitting a fallback chain | Leaves URLs unprotected | Cover all URLs, deny-by-default |
| Forgetting CSRF on POST login/logout | CSRF filter can reject requests | Keep CSRF and send a valid token |
| Assuming session roles are always up-to-date | Snapshot can be stale | Revoke/refresh/live authorization |

A test asserting only `GET /me == 200` does not prove all boundaries are right. Test **consecutive requests by different users**, **stateless requests missing credentials**, **anonymous requests**, and **context cleanup**.

## 14. Debugging along a request's lifecycle

When the wrong user appears or an endpoint unexpectedly returns 401/403, investigate in order:

1. Does the request pass through `springSecurityFilterChain`?
2. Which chain matches the URL, HTTP method, and dispatcher type? Are `@Order` and fallback configured?
3. Is the chain's repository HttpSession, RequestAttribute, Delegating, or Null?
4. Does the client send a session cookie, Basic header, Bearer token, or form credentials?
5. Which authentication filter runs? Which provider verifies? Are there exceptions?
6. Is the context loaded from an existing session or freshly created from credentials?
7. Does the anonymous filter create an AnonymousAuthenticationToken?
8. What are the principal type and `getName()`? Is it the expected user/workload?
9. Do authorities have the right role/scope prefixes?
10. Which authorization rule returns allow/deny? Is there another owner/tenant policy?
11. For custom login, was `saveContext` called before the response committed?
12. Did the session expire, was the cookie sent back, or did logout/revocation run?
13. Is there code on another thread/executor failing to propagate/clear context properly?
14. Are there ERROR/ASYNC dispatches and an appropriate context repository?
15. After the response, is the context cleared from the request thread?

You can enable logging in a dev environment:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Only log correlation ID, endpoint, filter decisions, and permitted account IDs. **Never log raw passwords, Authorization headers, session cookies, access tokens, sensitive JWT claims, credentials, or raw Authentication objects**.

### 14.1. Symptom table

| Symptom | Likely cause to check |
| --- | --- |
| `/me` still redirects after login | Cookie/session not sent; custom flow forgot saveContext |
| `/api/me` without Basic still sees Alice | Chain/stateless/repository or implicitly passed credentials |
| Public endpoint has `anonymousUser` | Normal when anonymous filter runs |
| Bob's request sees Alice | Static/shared context or broken thread cleanup/propagation |
| `@Async` does not see current user | Missing proper context propagation |
| `getCredentials()==null` after login | ProviderManager may have erased credentials |
| Valid JWT token has old roles | Stale claims; needs revocation/live authorization |
| Login succeeds but `/admin` is 403 | Missing ROLE_ADMIN; authorization is independent of authentication |
| Error controller does not see principal | ERROR dispatch/repository/request attribute config |
| SecurityContextHolder reads null in custom job | Job is outside a protected Servlet request |

## 15. Self-check exercises

**Q1.** How does `SecurityContextHolder` differ from `SecurityContext`?

**A:** Holder is the API/strategy for the current execution; SecurityContext is the object holding Authentication.

**Q2.** If `getContext()` always returns an object, does that confirm the user is logged in?

**A:** No. The context can be empty or anonymous.

**Q3.** Why must the holder be cleared at the end of a request?

**A:** Because Servlet threads are reused; failing to clear it can leak identity into someone else's request.

**Q4.** Does clearing the holder delete the login session?

**A:** No. The session context can be restored by the repository on the next request.

**Q5.** Does `SecurityContextHolderFilter` in Spring Security 6 automatically save a newly set custom context?

**A:** No, under the explicit-save model. Custom login wanting persistence must save into an appropriate SecurityContextRepository.

**Q6.** Does `RequestAttributeSecurityContextRepository` keep a login across two HTTP requests?

**A:** No. It serves the same logical request/dispatch; an HttpSession repository or another mechanism persists across requests.

**Q7.** Can a stateless API have an Authentication?

**A:** Yes. With valid Basic/Bearer credentials, an Authentication exists for that specific request.

**Q8.** Is `SessionCreationPolicy.NEVER` the same as STATELESS?

**A:** No. NEVER can still use an already existing session.

**Q9.** AnonymousAuthenticationToken has flag true. Does `.authenticated()` let it in?

**A:** No. The framework distinguishes anonymous via AuthenticationTrustResolver.

**Q10.** Why can a user log in yet get 403 at `/admin`?

**A:** Authentication succeeded, but ROLE_ADMIN or another authorization condition is missing.

**Q11.** Can `@WithMockUser` be used to prove HttpSession persistence?

**A:** No. It mocks Authentication; you must test an actual POST login and a subsequent request reusing the same session.

**Q12.** Should Authentication be stored in a static variable shared across controllers?

**A:** No, because it leaks identity across users and threads.

**Q13.** An async task does not see the user; should we switch to MODE_GLOBAL?

**A:** No. Use supported context propagation or pass minimal identity with reauthorization.

**Q14.** Does locking an account in the DB automatically invalidate all HttpSessions/JWTs?

**A:** Not by default. Revocation/live status/version checks are needed per system requirements.

**Q15.** Why does a public endpoint still have an anonymous token when using permitAll?

**A:** Because permitAll is authorization, while the anonymous filter can still run in the chain.

## 16. References

- Spring Security — **Servlet Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 — **Persisting Authentication**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html
- Spring Security 6.5 — **Session Management**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — **Explicit Save Migration**: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security — **Anonymous Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Spring MVC and Servlet API**: https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html
- Spring Security — **Concurrency Support**: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html

**Takeaway:** In every request, Spring Security **loads or creates a SecurityContext**, places a valid Authentication, uses the context to make authorization decisions, and **clears the context from the thread at the end of the request**. `SecurityContextHolder` is only the current access point; if you need to keep a login across subsequent requests, you need an appropriate `SecurityContextRepository` and persistence flow. Session-based login and stateless Basic have different identity lifecycles, yet both must prevent Authentication leakage across requests.
