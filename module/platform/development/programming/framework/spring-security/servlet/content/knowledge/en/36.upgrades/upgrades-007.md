# SecurityContextPersistenceFilter, Explicit Save, and Session Behavior Changes

> **Scope:** Upgrading a **Spring Security Servlet** application from common **Spring Security 5.x** patterns to **Spring Security 6.x / Spring Boot 3.x (Java 17+, Jakarta Servlet)**. Key topics: `SecurityContextPersistenceFilter`, `SecurityContextHolderFilter`, `SecurityContextRepository`, `requireExplicitSave`, saving `Authentication` in the right place, and why login can appear to succeed in the **current request** yet disappear on the **next request**. This lesson distinguishes session persistence, session creation, session fixation, CSRF, logout, stateful apps, and stateless apps. Java snippets using Spring must live inside an application with matching dependencies; they are not standalone Java SE files compiled directly with `javac`.

## 1. Common symptom during upgrades

An application previously signed users in inside a custom filter or controller:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

In some Spring Security 5 setups, the current request could read user details and the next request also saw the user as logged in. After upgrading to Spring Security 6, the first request may still succeed while the next request prompts for login again or returns 401/403.

Key reason: **putting `Authentication` into `SecurityContextHolder` is not the same as saving `SecurityContext` for subsequent requests**.

Previously, many apps relied on `SecurityContextPersistenceFilter` to auto-save modified contexts at the end of a request. Under Spring Security 6's new default model, `SecurityContextHolderFilter` primarily **reads/loads the context** and **does not auto-save it**; code that explicitly establishes authentication must call `SecurityContextRepository.saveContext(...)` when persistence is required.

**Very important note:** Spring Security's built-in login filters are already updated to persist the context properly. This lesson does **not** tell every post-login controller to call `saveContext`. The issue mainly affects **custom authentication** flows, custom filters, manual context mutations, or specialized repository/session setups.

### Three questions to separate

1. **Does the current request have authentication?** Check `SecurityContextHolder.getContext().getAuthentication()` in the active execution flow.
2. **Was the context saved in the right repository?** Check where it is stored, the `saveContext(...)` call, request/response objects, and timing.
3. **Does the next request carry the right session state?** Check session cookies, the session store, how filters load the repository, networking/clustering, and `SessionCreationPolicy`.

Seeing `authentication.isAuthenticated() == true` inside one request is not enough to prove the user will remain logged in on the next request.

## 2. SecurityContext, SecurityContextHolder, and Authentication

Spring Security builds on these core components:

| Component | Responsibility |
| --- | --- |
| `Authentication` | Represents the principal, authorities, credentials, and authentication status. |
| `SecurityContext` | Holds the `Authentication` bound to the execution context. |
| `SecurityContextHolder` | Exposes `SecurityContext` to current code (typically via `ThreadLocal` on the Servlet request thread). |
| `SecurityContextRepository` | Loads/saves `SecurityContext` across requests/dispatches per configuration. |

Example of **reading** the context inside a Java service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    System.out.println(authentication.getName());
}
~~~

This is a **Java snippet inside a method**, not a standalone file with `main()`. The printed value depends on the active request/principal; there is no fixed stdout.

`SecurityContextHolder` normally stores the context on the thread handling the request. When the request finishes, the filter chain clears/restores state appropriately so a principal never leaks to another request running on the same thread. Thus, if you only execute:

~~~java
SecurityContextHolder.getContext().setAuthentication(authenticated);
~~~

you have only updated state **for the current request context**. For the next request to recognize the user, a suitable repository and an explicit save are required whenever persistence is not handled automatically.

**Never share `SecurityContext` via `static` fields or singletons.** Doing so risks user A seeing user B's authentication. Nor should `SecurityContextHolder` be treated as a cross-request login store.

## 3. What did SecurityContextPersistenceFilter do previously?

In the legacy Servlet model, `SecurityContextPersistenceFilter` essentially did:

1. Start of request: load `SecurityContext` from `SecurityContextRepository` and place it into `SecurityContextHolder`.
2. Let downstream filters/handlers process the request.
3. On completion, handle **saving the modified context** automatically, including cases right before response commit depending on wrappers/implementations.
4. Clear `SecurityContextHolder` so subsequent requests never reuse stale thread data.

Conceptual diagram:

~~~text
Request N
  -> SecurityContextPersistenceFilter
     -> repository.loadContext(request)
     -> SecurityContextHolder = loaded context
     -> application/authentication filter modifies Authentication
     -> repository.saveContext(...) via automatic mechanism
     -> clear holder
  -> response

Request N+1
  -> repository.loadContext(...)  # if saved and client sends valid session
  -> application sees prior Authentication
~~~

**Not every context was saved unconditionally.** `SecurityContextRepository` has rules for anonymous users, session creation, context changes, response state, and configuration; never assume calling `setAuthentication` always creates an `HttpSession`. Auto-save only worked when filter, repository, and session policy aligned.

### Why was the automatic mechanism hard to predict?

Practical issues included:

- Apps redirecting/sending responses before the filter could save; the framework had to intercept response-commit timing.
- Repositories needing to create a new session at the end of a request; adding cookies once a response is committed becomes fragile.
- Requests spanning multiple dispatches/threads obscuring when the context changed and whether it was saved.
- Custom code mutating authentication in `ThreadLocal` without the author knowing whether it was actually persisted.

That is why the modern API expects **code performing authentication to explicitly save the context into the repository** when needed, rather than relying on end-of-request dirty detection.

## 4. SecurityContextHolderFilter: the core change in Spring Security 6

`SecurityContextHolderFilter`'s primary job is **reading/preparing `SecurityContext`** for the filter chain. By default, it does not take responsibility for “automatically saving any context mutation at the end of the request” the way some `SecurityContextPersistenceFilter` flows did.

Conceptual diagram when **requiring explicit save**:

~~~text
Request N
  -> SecurityContextHolderFilter
     -> repository.loadDeferredContext(request)
     -> SecurityContextHolder holds context on demand
     -> application/authentication code
          |
          +-- only sets SecurityContextHolder
          |      -> usable in request N
          |      -> NOT guaranteed for request N+1
          |
          +-- creates new SecurityContext
                 -> context.setAuthentication(verifiedAuthentication)
                 -> SecurityContextHolder.setContext(context)
                 -> repository.saveContext(context, request, response)
                        -> persisted per repository/session policy
     -> clear holder

Request N+1
  -> SecurityContextHolderFilter
     -> repository.loadDeferredContext(request) if client sends valid state
     -> saved Authentication can be restored
~~~

**“Explicit save” is an action required of code that performs authentication**, not turning `SecurityContextHolder` into a new storage backend. Authentication in the holder and context in the repository are two distinct layers of responsibility.

### Before-and-after comparison table

| Criterion | Common mechanism based on `SecurityContextPersistenceFilter` | Explicit save mechanism using `SecurityContextHolderFilter` |
| --- | --- | --- |
| Loading context | Repository loads and populates holder at request start. | Repository supplies deferred context, loaded when accessed. |
| Saving modified context | Filter has auto-save hooks at request end/commit points. | Filter does not auto-save arbitrary changes; auth setter saves when needed. |
| Custom code calling only `setAuthentication` | May be auto-saved if filter/repository allow. | **Insufficient** to ensure the next request stays authenticated. |
| Built-in login filters | Framework handles authentication and persistence per config. | Built-in login filters normally call save as part of login success. |
| Stateless APIs | Repository/session policy decides; does not necessarily create sessions. | Still governed by repository/session policy; explicit save does not force `HttpSession`. |
| Upgrade goal | Identify code that implicitly relied on auto-save. | Switch to explicit saving where authentication is established. |

### requireExplicitSave

In Spring Security 6 Servlet, the relevant setting is:

~~~java
http.securityContext(context -> context.requireExplicitSave(true));
~~~

This is a **configuration snippet** inside building a `SecurityFilterChain`. It opts into requiring explicit saves (typically via `SecurityContextHolderFilter`). This is the default in standard Spring Security 6 setups, so you do not have to declare it just to repeat the default.

In several Spring Security 6 releases, `requireExplicitSave(false)` can temporarily restore legacy persistence behavior during transition:

~~~java
// Transitional compatibility option, not the upgrade target:
http.securityContext(context -> context.requireExplicitSave(false));
~~~

**Do not use it as a permanent fix for broken custom authentication.** Verify the exact running version, test the request lifecycle, and update code to call `saveContext` in the right place. Never manually register both `SecurityContextPersistenceFilter` and `SecurityContextHolderFilter` just to “have both.”

## 5. SecurityContextRepository: where it is saved determines session behavior

A filter cannot create persistence if the configured repository disallows it. Key implementations on the Servlet stack:

| Repository | Scope/lifecycle | Upgrade notes |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Saves context into `HttpSession` when needed and permitted. | Used for form login/session-based auth so later requests restore from session. |
| `RequestAttributeSecurityContextRepository` | Stores in a **request attribute**, keeping context visible across dispatches of **the same request**. | Does not replace session persistence across separate HTTP requests. |
| `DelegatingSecurityContextRepository` | Loads/saves across configured delegates (commonly request-attribute + session). | Spring Security 6 commonly uses this by default, supporting both error dispatches and sessions. |
| `NullSecurityContextRepository` | Does not persist context in a repository. | Fits stateless designs or per-request re-auth flows; saving creates no login session. |
| Custom repository | Project-specific cookie/token/store. | Must enforce trust, serialization, rotation, replay protection, and compatibility. |

### HttpSessionSecurityContextRepository

This repository is most directly tied to the **“logged in, then user vanishes on the next request”** symptom. It persists context across requests via `HttpSession`. However:

- It may **not create a session** if unnecessary or blocked by `allowSessionCreation`/session policy.
- It should not persist an anonymous `Authentication` as a valid login.
- Clients must retain the session using the right cookie or configured session-tracking mechanism. No valid cookie → next request has a different session → auth is not reloaded.
- In clusters, every node handling the session needs shared session storage or sticky routing.
- Do not use it to store large non-Serializable domain objects or arbitrary raw credentials; keep the principal/session lean, stable, and compliant with policy.

### RequestAttributeSecurityContextRepository

This repository keeps the context accessible during **ERROR/FORWARD dispatches** within the same HTTP request if the servlet container clears the holder between dispatches. It does **not** keep the user logged in on the next HTTP request.

Example sequence:

~~~text
One HTTP request /api/action
   -> authentication/authorization
   -> controller throws exception
   -> ERROR dispatch to /error
   -> request attribute preserves SecurityContext within the same request

New HTTP request /api/me
   -> cannot expect the previous request's request attribute
~~~

If you configure only `RequestAttributeSecurityContextRepository` and expect form login to survive multiple requests, you chose the wrong storage scope.

### DelegatingSecurityContextRepository

This is the common Spring Security 6 pattern when combining both:

~~~java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
~~~

Imports:

~~~java
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
~~~

This is a **Java snippet**. `DelegatingSecurityContextRepository` delegates saves per each implementation; it **does not turn a stateless architecture into stateful** if another policy overrides it. Use the exact repository instance **wired into the `SecurityFilterChain`**; never instantiate a separate one in a controller assuming downstream filters read from it.

## 6. Spring Boot 3 / Spring Security 6 configuration sample with session persistence

This section presents a runnable Servlet sample in a **Spring Boot project**. Goal: standard Spring Security form login, saving context to the right repository, and verifying on the next request. Files live in package `com.example.persistence`.

### 6.1 Maven dependencies

In `pom.xml` using the Spring Boot parent/BOM, Java 17+, add:

~~~xml
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
~~~

This is a **POM snippet**, not a standalone POM. Let Boot manage compatible versions; never mix Spring Security 5 `javax.servlet` classes with Spring Boot 3/Spring Security 6 `jakarta.servlet` classes.

### 6.2 Entry point

File `src/main/java/com/example/persistence/PersistenceDemoApplication.java`:

~~~java
package com.example.persistence;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PersistenceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PersistenceDemoApplication.class, args);
    }
}
~~~

### 6.3 SecurityContextRepository and SecurityFilterChain sharing one bean

File `src/main/java/com/example/persistence/SecurityConfig.java`:

~~~java
package com.example.persistence;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(securityContextRepository))
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

**Why declare the repository as a bean?**

1. So the filter chain and any custom authentication integration **share the exact same repository configuration** rather than writing to mismatched stores.
2. `DelegatingSecurityContextRepository` persists to both request attributes and session via its delegates, making request/ERROR dispatches easy to observe.
3. `requireExplicitSave(true)` highlights Spring Security 6 behavior. Built-in authentication filters manage saving the context for their login flow; no `/login` controller needs to call save manually.
4. `/api/me` requires authentication. Any unauthenticated caller hitting this URL is handled by the entry point (form login normally redirects to `/login`).
5. `anyRequest().denyAll()` locks down remaining routes in the demo. Production apps add endpoints with explicit policies rather than opening all URLs just to make tests pass.
6. **CSRF remains enabled.** Login POST requires a valid token. If a login POST test omits the token and gets 403, that may be CSRF rather than the authentication manager rejecting the password.

This illustrative configuration **does not** store private credentials in the repository. Nor is it meant for a stateless JWT resource server that re-authenticates Bearer tokens on every request.

### 6.4 Demo user

File `src/main/java/com/example/persistence/DemoUsersConfig.java`:

~~~java
package com.example.persistence;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("local-test-password"))
                .roles("USER")
                .build()
        );
    }
}
~~~

The password `local-test-password` is for demo/test environments only, **never for production**. Real applications need a proper user store/SSO, secret management, account status checks, and login security controls.

### 6.5 Controller returning current request identity

File `src/main/java/com/example/persistence/MeController.java`:

~~~java
package com.example.persistence;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

This controller neither authenticates the user itself nor saves the session. `/api/me` is protected by the filter chain; once authenticated, it reads the `Authentication` supplied by Spring Security.

## 7. Built-in form login already saves the context: avoid redundant saves

In standard `formLogin` configs, Spring Security's authentication components handle authentication success and persistence per the current version's design:

~~~text
POST /login (valid username/password + CSRF)
  -> UsernamePasswordAuthenticationFilter
  -> AuthenticationManager / AuthenticationProvider
  -> SecurityContext is populated
  -> SecurityContextRepository.saveContext(...) via login integration
  -> redirect response

GET /api/me on a new request, same session cookie
  -> SecurityContextHolderFilter
  -> SecurityContextRepository.loadDeferredContext(...)
  -> alice's Authentication
  -> controller returns "alice"
~~~

This is a **conceptual flow**, not a fixed trace for every application. Filters, entry points, and session strategies can differ with OAuth2 Login, SAML2, remember-me, custom login, multiple chains, or other customizations.

**Common upgrade mistake:** noticing `SecurityContextHolderFilter` does not auto-save and blindly adding `saveContext` in every post-authentication controller. That is unnecessary for built-in login and risks corrupting session semantics or persisting untrusted authentications. Add explicit save only at the **exact point where your own code creates/persists `SecurityContext`**.

### Successful login does not mean the old session cookie stays unchanged

Spring Security normally enables **session fixation protection** upon login; the session ID may rotate. Browsers must store and send the **new session cookie** on subsequent requests. A changing `JSESSIONID` during login can be **correct security behavior**.

A custom filter creating sessions or cookies during a redirect can conflict unless coordinated with `SessionAuthenticationStrategy`. Never “fix” lost logins by disabling session fixation protection without understanding the root cause.

## 8. Explicit save: the right way for verified custom authentication

### 8.1 Anti-pattern: setting only the holder

The following code is **insufficient** under `requireExplicitSave(true)`:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(verifiedAuthentication);
~~~

The name `verifiedAuthentication` here implies the authentication **has already been verified by a trusted component**. If code reads username/role from a request body/header and constructs `UsernamePasswordAuthenticationToken.authenticated(...)` directly, that is **authentication forgery**, not secure login.

This snippet lets downstream components in the **same request** see the authentication. However, subsequent requests will not see a logged-in user unless something saves the context to the appropriate repository.

### 8.2 Explicit save in the right order

Inside a trusted custom authentication integration (for example, after `AuthenticationManager.authenticate(...)` succeeds), the structure should be:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);

SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Required imports:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
~~~

This is a **Java snippet inside a filter/handler/service with injected variables**, not a standalone program. Key rules:

1. **Only use** `verifiedAuthentication` verified by a valid provider/trust boundary. Never accept arbitrary authorities from clients.
2. Create a fresh context with `SecurityContextHolder.createEmptyContext()` rather than mutating a context object that may be shared or referenced elsewhere.
3. Attach the authentication to the new context.
4. Set the context in the holder so components in the current request recognize the user.
5. **Call `saveContext(context, request, response)`** on the repository wired into the right security chain.
6. Save **before the response is committed**, redirected, or finalized if `Set-Cookie`/session creation is needed.

This cleanly separates **“setting context for the current request”** from **“saving context for future requests.”**

### 8.3 A helper class for saving verified Authentication

File `src/main/java/com/example/persistence/VerifiedAuthenticationPersistence.java`:

~~~java
package com.example.persistence;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.stereotype.Component;

@Component
public class VerifiedAuthenticationPersistence {

    private final SecurityContextRepository repository;

    public VerifiedAuthenticationPersistence(
            SecurityContextRepository repository) {
        this.repository = repository;
    }

    public void saveVerified(
            Authentication verifiedAuthentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (verifiedAuthentication == null ||
                !verifiedAuthentication.isAuthenticated()) {
            throw new IllegalArgumentException(
                    "Authentication must already be verified");
        }

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verifiedAuthentication);

        SecurityContextHolder.setContext(context);
        repository.saveContext(context, request, response);
    }
}
~~~

This class **compiles inside the Spring Boot project with the repository bean from Section 6**. Its sole job is saving the context; **it is not a complete login mechanism**. `isAuthenticated()` is a basic defensive check and **does not prove the authentication came from a trusted source**, because any code could construct an authenticated token. Only call this method after genuine verification trusted by the application. Never expose it directly as an HTTP endpoint where users supply principals/roles.

### 8.4 Responsibilities missing from this helper class

A production custom login endpoint/filter typically also needs:

- Password/credential/token verification via `AuthenticationManager` or a valid provider/IdP—never self-fabricating verified tokens.
- **SessionAuthenticationStrategy**: session fixation defense, concurrent session limits, and configured behaviors.
- **CSRF lifecycle**: in session/cookie apps, old tokens may be cleared on login/logout; frontends must obtain fresh tokens.
- Authentication success/failure handlers, redirect allowlists, error policies, auditing, and avoiding credential logging.
- Alignment with the actual `SecurityContextRepository` wired into the chain and the session creation policy.
- Proper session logout/invalidation and principal revocation.
- Multi-request tests with cookies from the same client.

Therefore, **prefer built-in authentication filters** (`formLogin`, `httpBasic`, OAuth2 Login, SAML2 Login, Resource Server per model) whenever they meet requirements. Write custom login/filters only with clear justification and full understanding of security hooks.

## 9. Does explicit save always create an HttpSession?

**No.** `SecurityContextRepository.saveContext(...)` is a repository persistence API, not a “force-create session” command.

Cases:

- `HttpSessionSecurityContextRepository` can create/store a session if needed and allowed.
- `RequestAttributeSecurityContextRepository` keeps context only in request attributes; it creates no persistence across new HTTP requests.
- `NullSecurityContextRepository` persists nothing, even if you call `saveContext`.
- With `DelegatingSecurityContextRepository`, behavior depends on the configured delegates.
- `SessionCreationPolicy.STATELESS` is typically used to avoid creating/using HTTP sessions for authentication and to protect stateless resource servers/tokens.
- `SessionCreationPolicy.NEVER` prevents Spring Security from creating sessions itself, though it may use an existing session in applicable mechanisms; do not equate it with `STATELESS`.
- `SessionCreationPolicy.IF_REQUIRED` lets Spring Security create sessions when needed, though anonymous requests do not automatically create sessions in all setups.

### Guidance table

| Application model | Desired persistence | Configuration direction |
| --- | --- | --- |
| Web MVC with form login and session cookies | Authentication across multiple requests in the same session. | `HttpSessionSecurityContextRepository` or `DelegatingSecurityContextRepository`, matching session policy. |
| Stateless Bearer JWT API | Each request verifies its token; no Authentication saved from prior requests. | Stateless session policy and matching repository, typically `NullSecurityContextRepository`. |
| Error dispatch of the same HTTP request | Keep context for related dispatches. | Include `RequestAttributeSecurityContextRepository` as a delegate. |
| Custom SSO login creating a session | Keep verified Authentication on the next request. | Explicit save into the shared repository, plus full session/auth strategies. |
| Per-request machine-to-machine Basic auth | Verify header every request, not necessarily session-backed. | Policy/repository per threat model; do not silently turn into session login. |

**Note:** if you want a stateless API, having the next request lack `Authentication` when the Bearer token is omitted is **by design**, not an explicit-save bug. Never “fix” it by opening HTTP sessions for bearer requests.

## 10. Session fixation, invalidation, and session behavior shifts during upgrades

Many incidents share the symptom “lost login after a request” while having distinct root causes.

### 10.1 Session fixation protection

Spring Security can rotate the session ID after successful authentication to prevent attackers from fixing a session ID before login. On modern Servlets, `changeSessionId()` is commonly built in.

~~~text
Before login: JSESSIONID = A
POST /login succeeds
SessionAuthenticationStrategy / container session fixation protection
After login:  JSESSIONID = B (may be the same logical session with rotated ID)
GET /api/me with cookie B -> stays authenticated if context was saved
GET /api/me with cookie A -> may fail to find a valid session
~~~

This is an **illustrative timeline**, not real cookie values. Do not conclude “Spring Security changing the session ID caused a bug”; ID rotation is a proper security defense. If a custom client drops the new `Set-Cookie` or a proxy/load balancer mangles the cookie path/domain, the next request loses the session even though the repository saved properly.

**Never disable session fixation protection just to keep `JSESSIONID` static.** Fix `Set-Cookie`, cookie jars, domains, paths, `Secure`, `SameSite`, and follow-up requests instead.

### 10.2 CSRF tokens after login/logout

CSRF and `SecurityContext` persistence are **two separate mechanisms**:

- `SecurityContextRepository` stores `Authentication`/context within the chosen scope.
- `CsrfTokenRepository` stores CSRF tokens in CSRF's repository (typically HTTP session or cookie).
- `CsrfAuthenticationStrategy` and `CsrfLogoutHandler` can **clear old CSRF tokens** on authentication changes/logout, depending on configuration.
- After login, a form or SPA reusing a pre-login token can receive 403 even though `Authentication` was saved properly.

When testing migrations, distinguish:
1. Post-login GET redirects back to login → suspect authentication/session persistence/cookies.
2. GET is authenticated yet POST returns 403 → suspect a stale/invalid CSRF token or missing authority.
3. Both GET and POST reach the right user yet the action is denied → inspect authorization/owner/tenant rules.

Never use `csrf.disable()` to mask context-saving errors. For session-based browser apps, CSRF protection is normally an essential defense layer.

### 10.3 Concurrent sessions and logout

Other legitimate reasons a context “disappears”:

- Session timeout.
- Logout invalidates the session and clears `SecurityContextHolder`.
- Maximum-sessions / concurrent-session controls reject or expire another session.
- `SecurityContext`/HTTP session invalidated by password reset, explicit revocation, or session store eviction.
- User B logs in on another tab in the same browser, replacing the session/principal.

Do not “fix” every case by spinning up new sessions. An intentionally revoked session **must** lose access. Multi-tab clients should refresh UI state to match the current authentication rather than running User A's actions under User B's session.

## 11. When must saving happen before response commit?

A custom authentication flow might send a redirect or response right after setting the context:

~~~java
SecurityContextHolder.setContext(context);
response.sendRedirect("/dashboard");
// saveContext() here may be too late if the response is already committed.
~~~

The snippet above is an **anti-pattern**. If the implementation needs to create a session or emit `Set-Cookie`, a committed response may no longer allow header updates.

Conceptually proper order:

~~~java
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/dashboard");
~~~

**Only do this when `context` holds a verified `Authentication` and session strategies have run properly.** Check response wrappers or handler behavior in your framework version. Never rely on calling `saveContext` after writing the body, flushing the buffer, or calling `sendError`.

### Signs a response has committed

- `sendRedirect(...)` or `sendError(...)`.
- `flushBuffer()` or flushing the output stream/writer.
- Body bytes already flushed over the network (on some servers/containers).
- Async handling or another filter commits the response before custom authentication code reaches save.

If a user “logs in successfully” and gets redirected back to login, verify whether login saves context before commit and whether the browser retains the new session cookie.

## 12. Multiple SecurityFilterChains: save in one place, read in another?

Spring Security Servlet supports multiple `SecurityFilterChain`s using `securityMatcher` and `@Order`. Then you must ensure not only that auth was saved, but also **which filter chain handles the next request**.

Partitioning example:

~~~text
@Order(1): /api/**   -> stateless Bearer JWT (does not read session context)
@Order(2): /**        -> stateful form login (reads HttpSession context)
~~~

If login creates a session in the web chain while the next request hits `/api/**` using `NullSecurityContextRepository`, the API may return 401 without a Bearer token. That can be intentional design; `saveContext` in the web chain does not automatically apply to a stateless chain.

Even more hazardous is **a custom handler writing to repository X while the chain serving the next request reads repository Y**. Saving appears to succeed at the API level, yet the user still “loses their session.”

### How to verify

1. List every `SecurityFilterChain` configured by the app and its matched URLs/methods.
2. Check `@Order` precedence; the first matching filter chain is chosen.
3. Inspect which repository the login chain writes to and which repository follow-up request chains read from.
4. Inspect each chain's `SessionCreationPolicy`.
5. Send real requests to login, dashboard/API routes, and inspect auth/cookies.
6. Never declare one global repository bean and assume **every chain** uses it; verify how it is wired into each chain's `HttpSecurity`.

### Do not treat request matchers as session persistence

`requestMatchers("/api/**").authenticated()` only enforces **authorization** inside a chain; it does not persist the user into a session. Likewise, `requestMatchers("/login").permitAll()` does not make a custom login endpoint execute session security strategies. Each piece must be designed explicitly.

## 13. MockMvc test: proving login genuinely persists across requests

A crucial migration test rule is **do not use `@WithMockUser`** for scenarios meant to prove authentication persistence. `@WithMockUser` injects a fake `Authentication` directly, so tests can pass green even when production login filters or repositories persist nothing.

### 13.1 Real form-login test suite in the Spring context

File `src/test/java/com/example/persistence/LoginPersistenceTest.java`:

~~~java
package com.example.persistence;

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

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistenceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void formLoginPersistsAuthenticationForSecondRequest()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-test-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession savedSession =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(savedSession);

        mvc.perform(get("/api/me").session(savedSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void anonymousSecondRequestCannotUsePrivateEndpoint()
            throws Exception {

        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void invalidPasswordDoesNotCreateAnAuthenticatedSession()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

**Why is this test suite valuable?**

- `POST /login` executes a real request through the demo's `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `UserDetailsService`, and `PasswordEncoder` (not `@WithMockUser`).
- `.with(csrf())` ensures login is not blocked by CSRF before checking the password.
- After login, grabbing the **session from the completed request** (`getSession(false)`) simulates a second request carrying that session. This matters because session fixation protection can rotate the session ID.
- The second request `GET /api/me` proves cross-request persistence. Asserting only the login redirect on the first request does not prove the context was saved.
- Separate invalid-password and anonymous tests catch accidental `permitAll` rules or faked authentication.
- If the app sits behind HTTPS/cookies/proxies, MockMvc cannot verify **whether browsers retain `Set-Cookie` properly**. Add HTTP/browser integration tests for real deployments.

**Expected:** in a properly configured demo project, the first test returns `alice` on the second request; the two negative tests cannot reach `/api/me`. Do not fabricate fixed Maven stdout. To run, execute:

~~~bash
mvn test
~~~

If the first test fails, inspect status/headers, Session ID (masked in logs), repository, and filter chain. Never switch the test to `@WithMockUser` just to make it pass.

### 13.2 Testing the repository/bridge without confusing it with real login tests

`VerifiedAuthenticationPersistence` from Section 8 can be unit-tested with Mockito to verify it calls `saveContext` with the right request/response instances, yet that test **does not prove** the repository actually persists across requests.

Small test **to verify interaction with the repository**, not real login:

~~~java
@Test
void bridgeCallsRepositorySave() {
    SecurityContextRepository repository =
            Mockito.mock(SecurityContextRepository.class);
    VerifiedAuthenticationPersistence bridge =
            new VerifiedAuthenticationPersistence(repository);

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpServletResponse response = new MockHttpServletResponse();

    Authentication verified =
            UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));

    bridge.saveVerified(verified, request, response);

    Mockito.verify(repository).saveContext(
            Mockito.argThat(ctx ->
                    ctx.getAuthentication() == verified),
            Mockito.same(request), Mockito.same(response));

    SecurityContextHolder.clearContext();
}
~~~

This is a **test-method snippet** requiring the relevant JUnit, Mockito, Spring Mock Servlet, and Spring Security imports. `UsernamePasswordAuthenticationToken.authenticated(...)` is used **only to build a test fixture**, not as proof a real user authenticated. Never use this fake-auth construction pattern inside production endpoints.

To prove real persistence, add a **second GET/POST request** test against a real repository as in 13.1 or an appropriate custom-flow integration test.

## 14. Why does @WithMockUser hide explicit-save bugs?

Consider a test:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void meReturnsAlice() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

This test can pass **without any context ever being saved in `HttpSession`**. `@WithMockUser` builds a test `Authentication` so the single running request sees “alice.” Therefore, never cite it as proof for the question: **“After a user logs in, does the next GET request see the session?”**

It remains very useful for verifying:
- URL/method authorization.
- Role/authority rules.
- Controller/service behavior once a principal exists.
- CSRF on specific requests when paired appropriately with `.with(csrf())`.

However, specifically for session persistence upgrades, you must test **real login → save context → new request reloads it**. With custom filters, add tests for that custom flow. Principal-mocking tests and authentication-lifecycle tests must be reported as two distinct scopes.

## 15. Diagnosing lost login behavior after an upgrade

### Symptom A: login request succeeds, yet the next request redirects back to /login

Check in order:

1. Is the login filter **built-in** or custom? Does custom code only call `SecurityContextHolder.setContext`?
2. Is the filter chain running `SecurityContextHolderFilter`/`requireExplicitSave(true)`?
3. Which repository is actually configured? Is an `HttpSessionSecurityContextRepository` delegate present, or `NullSecurityContextRepository`?
4. Did custom code call `saveContext(context, request, response)` **before response commit**?
5. Is the same repository used to **load** the second request?
6. Did the response emit the right `Set-Cookie`/`JSESSIONID`, and did the browser send the updated cookie on the next request?
7. Was the session invalidated right after login due to logout, concurrency limits, or security policies?
8. Behind a load balancer, do all nodes share the session store or sticky routing?

### Symptom B: controller sees Authentication, yet session lacks expected data

Possible causes:
- Authentication was placed in the holder, not saved.
- Repository saves only to request attributes.
- Session policy disallows creating a session.
- Custom code saves into a different repository than the filter chain.
- Response committed before cookie/session could be saved.
- Session attribute was saved, yet you are inspecting a **different session**, node, or namespace.

**Do not draw conclusions** solely from one key in the session map if the app uses a custom repository. What must be tested is **actual behavior on the follow-up request**, not only a specific attribute name.

### Symptom C: GET works after login, POST returns 403

Distinguish:
- Authentication may have persisted fine, yet **the old CSRF token** is invalid after login/logout.
- User is authenticated yet lacks authority for POST.
- Cookie/session/authorities changed between GET and POST.
- Multiple filter chains apply differently per URL/method.

To test POST authorization when CSRF is enabled, send a valid CSRF token. Never “fix persistence” by disabling `CsrfFilter`.

### Symptom D: behavior differs between real servers and MockMvc

MockMvc normally does not start TCP/TLS or fully emulate browser/proxy cookie handling, even though Spring Security filters run in context. Causes outside MockMvc include:

- `Secure` cookies sent only over HTTPS.
- `SameSite` and cross-site redirects/posts.
- Reverse proxy rewriting scheme/host/context path.
- Session replication/sticky sessions across multiple nodes.
- Session store timeout/eviction.
- HTTP clients retaining an old cookie after login/session ID rotation.

Run appropriate browser/server integration tests rather than disabling filters in MockMvc to force desired results.

## 16. Safe logging when debugging SecurityContext

In dev/test environments, enable logging to observe the Spring Security filter chain:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.context=TRACE
~~~

Use TRACE only under strict control; never put raw session IDs, credentials, `Authorization` headers, cookies, JWT/SAML assertions, or sensitive user data into logs or public tickets. You can inspect request IDs, paths, statuses, selected chains, which authentication **type** ran, and whether `repository.saveContext` was invoked without printing secrets.

### Where to observe?

- `FilterChainProxy` and security filters in the application context.
- Loggers for `SecurityContextHolderFilter`/`SecurityContextPersistenceFilter` depending on configuration.
- `SecurityContextRepository.load...` and `saveContext` invocations via mocks/spies in tests or guarded instrumentation.
- Session creation and session ID rotation in tests (without publishing raw IDs).
- Browser DevTools: cookie path/domain/`Secure`/`SameSite` and request headers (observe locally only; never paste secrets into tickets).
- Spring Session / store logs if using Redis/JDBC, without dumping full sessions.

**Never rely on a single filter name in one log line.** Check which chain matched the request and which repository was invoked. An app with multiple chains or differing test/prod configs can behave differently.

## 17. Common errors and fixes table

| Symptom | Possible cause | Check / fix direction |
| --- | --- | --- |
| Custom login succeeds on first request; next request 302 `/login` | Only set holder; missing explicit save under `SecurityContextHolderFilter`. | Save context to the right repository before response commit; test second request. |
| Default form login loses session | Misconfigured cookies/session store/repository/chain; do not assume built-in filter omitted save. | Inspect `Set-Cookie`, session IDs, repositories, chain matching, and timeouts. |
| `SecurityContext` exists only during ERROR dispatch | Using request-attribute repository without `HttpSession` persistence. | Choose a repository suited for multi-request persistence. |
| `saveContext` is called, yet next request still 401 | `NullSecurityContextRepository`, stateless chain, missing session, or next chain reads another repo. | Inspect implementation, `SessionCreationPolicy`, request cookies, and multiple chains. |
| Saving after redirect creates no session cookie | Response already committed, preventing expected session/header updates. | Save context before redirecting/writing response. |
| Session ID changes after login | Session fixation protection active; client ignores the new cookie. | Keep fixation defense; fix cookie handling/proxy/client. |
| Reading context via static field sees wrong user | Storing `SecurityContext` outside holder/repository as shared mutable state. | Remove static/shared auth state; use security context and trusted repository properly. |
| POST after login 403 while GET is authenticated | CSRF token cleared/rotated, or missing authority. | Diagnose CSRF and authorization separately; fetch a fresh token. |
| Session keeps being created despite “stateless” | Another component creates a session (request cache, app code, container) or policy missed the chain. | Audit session creation sources; do not look solely at `securityContext().requireExplicitSave()`. |
| JWT API loses Authentication without a new token | Stateless resource server working by design. | Send Bearer token on every request; do not open `HttpSession` to “keep login.” |
| `@WithMockUser` test passes, real app loses login | Test injects fake auth, bypassing login/persistence. | Test real form/custom login and a follow-up request with the same session. |
| Same session loses auth on another node | Session store not shared/sticky routing, serialization/replication failure. | Inspect Spring Session/cluster topology and failover tests. |
| After logout user stays authenticated in test | Test reuses mock Authentication or skips logout filter. | Test real logout and session invalidation without fake contexts when proving logout. |
| `javax.servlet` / `jakarta.servlet` mismatch after upgrade | Boot 3/Security 6 moved to Jakarta APIs. | Use `jakarta.servlet.*` imports and compatible dependency versions. |

## 18. Step-by-step upgrade strategy

### Step 1 — Inventory where Authentication is written

Search **your own application codebase** for uses of:

~~~text
SecurityContextHolder.setContext(...)
SecurityContextHolder.getContext().setAuthentication(...)
new UsernamePasswordAuthenticationToken(...)
custom OncePerRequestFilter / authentication filter
custom login controller / trusted SSO bridge
SecurityContextRepository.saveContext(...)
securityContext().requireExplicitSave(...)
SessionCreationPolicy.STATELESS / NEVER / IF_REQUIRED
~~~

Not every match is a bug. The goal is distinguishing places that **set Authentication for the current request** from places that must **persist across subsequent requests**.

### Step 2 — Lock down the trust and persistence model per chain

For each request category, document:
- Who authenticates the user/token?
- Must Authentication live **for one request** or **across multiple requests**?
- Which repository loads and saves it?
- Are session cookies used? What is the session creation policy?
- Which filter chain applies? Do stateless Bearer APIs and stateful form logins coexist in the app?
- Where are session invalidation, timeouts, logout, CSRF, and fixation handled?

Only after building this table decide where to add explicit saves or swap repositories.

### Step 3 — Migrate custom auth to explicit save

For code creating verified Authentications:
1. Ensure authentication originates from a valid provider/trusted upstream and is already verified.
2. Create a **new `SecurityContext`**.
3. Place that context into `SecurityContextHolder`.
4. **Call `SecurityContextRepository.saveContext(context, request, response)`** on the right repository instance before response commit.
5. Run session strategies, CSRF lifecycle, and success/failure handlers per your authentication model.
6. Avoid redundant double-saves out of habit if a framework filter already manages persistence.

### Step 4 — Add second-request tests

Test **accurately**:
- Real login/custom authentication succeeds.
- Next request with the **same session/client** is authenticated.
- Request with another session or no credentials is rejected.
- Wrong password or authentication failure never creates an authenticated session.
- Logout/timeout revokes access per policy.
- Post-login CSRF and permissions are not conflated with persistence bugs.

### Step 5 — Test session lifecycle and realistic deployment

Verify:
- `Set-Cookie` after login and `changeSessionId` behavior.
- Browsers retain cookies cleanly across redirects/cross-site flows.
- Session store/cluster/replication under failover.
- Multiple filter chains and new endpoint routes.
- Tests running under production-like profiles/configs.
- `SecurityContextRepository` and custom integrations sharing the same load/save contract.

### Step 6 — Use compatibility mode only when genuinely needed

If your framework version supports `requireExplicitSave(false)`, use it **short-term** to isolate regressions, never as the final solution. Your upgrade plan must confirm custom code performs explicit saves and remove reliance on auto-save before finalizing.

## 19. Anti-patterns to avoid

- **Calling only `SecurityContextHolder.getContext().setAuthentication(...)`** in custom login and assuming the user persists across requests.
- **Constructing an authenticated token from client-sent username/role** and saving it to session: that is a critical privilege vulnerability, not persistence handling.
- **Manually registering both `SecurityContextPersistenceFilter` and `SecurityContextHolderFilter`** without understanding `FilterChainProxy` and default config.
- **Calling `saveContext` on a different repository** than the one the next request loads from.
- **Using `RequestAttributeSecurityContextRepository` expecting users to stay logged in on new HTTP requests**.
- **Using `NullSecurityContextRepository` while expecting stateful form login**.
- **Saving after `sendRedirect`/flush** without checking response commit or cookies.
- **Disabling session fixation or CSRF** merely to silence POST/redirect errors.
- **Using `@WithMockUser` to prove persistence**.
- **Using a global/static user session** causing cross-request principal leaks or privilege crossover.
- **Forcing one session mechanism across all chains** even when stateless Bearer APIs must re-verify every request.
- **Logging session IDs or raw `SecurityContext`s** into uncontrolled log stores.

## 20. Knowledge check

**Question 1.** With `SecurityContextHolderFilter` and `requireExplicitSave(true)`, is calling `SecurityContextHolder.setContext(ctx)` in a custom filter enough to keep the next request authenticated?

**Answer:** **No.** For persistent logins, custom code must also call `SecurityContextRepository.saveContext(ctx, request, response)` on the appropriate repository aligned with lifecycle/session policy. Setting the holder affects only the current request.

**Question 2.** Why doesn't `RequestAttributeSecurityContextRepository` solve login across multiple HTTP requests?

**Answer:** Because request attributes live only within the scope of the active request/dispatch; a new HTTP request has a different request object. Stateful form login normally requires an `HttpSession`-backed repository.

**Question 3.** Does Spring Security 6 built-in form login require a controller to call `saveContext` manually after redirect?

**Answer:** Usually **no**. Built-in authentication filters manage saving the context on success per configuration. If logins disappear, check sessions/cookies/repositories/chains/customizations first rather than adding blind double-saves.

**Question 4.** Within the same `SecurityFilterChain`, login returns 302, yet the subsequent protected GET also returns 302 to `/login`. What are the main causes?

**Answer:** Context was never saved (especially in custom auth), repository does not persist across sessions, save happened too late, client did not carry the new session cookie, session was invalidated, or the follow-up request hit a different chain/repository. Test the second request using the same session.

**Question 5.** With `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository`, is `saveContext` failing to retain `Authentication` across requests a bug?

**Answer:** Not necessarily. In a stateless API, clients send credentials/tokens **on every request** and the server re-verifies them. Not saving sessions matches the chosen architecture.

**Question 6.** After login, `GET /api/me` sees user `alice`, yet `POST /api/save` returns 403. Is persistence definitely broken?

**Answer:** No. The context may already be restored properly; POST is also subject to CSRF and authorization. Determine whether `CsrfFilter` or an authorization policy denied it, obtain a fresh CSRF token after login if needed, and verify permissions.

## 21. Summary

Upgrading from `SecurityContextPersistenceFilter` patterns to the `SecurityContextHolderFilter` / **explicit save** model shifts an important responsibility: **code that establishes `Authentication` itself and wants it preserved across requests must save `SecurityContext` to the right `SecurityContextRepository`**. Yet **not every `Authentication` should be saved** — for stateless APIs, re-authenticating every request is the intended design.

In stateful Servlet systems, inspect **holder → repository → session → cookie → next request's filter chain** together. Built-in login filters typically handle context saving already; custom authentication must be audited and tested carefully. Session fixation, CSRF, timeouts, logout, and multi-chain setups can produce similar “lost login” symptoms, and each must be diagnosed by its actual mechanism.

**Quick rule of thumb:** *`SecurityContextHolder` identifies the user for the **current request**; `SecurityContextRepository.saveContext(...)` is required when a **custom authenticated context must survive to the next request** under the explicit-save model. Call save only on the repository actually used for loading, before response commit, and never bypass authentication or session safeguards.*

## References

- Spring Security Reference — Authentication Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security Reference — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security Reference — Migrating to Spring Security 6 (Servlet session management): https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security Reference — Servlet Architecture and FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Testing Spring MVC with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
