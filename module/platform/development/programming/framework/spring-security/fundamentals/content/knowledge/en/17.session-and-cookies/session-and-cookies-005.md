# SessionCreationPolicy in Servlet and WebSession Management in WebFlux

## 1. Objectives and Scope

After this lesson, you will be able to explain why HTTP is inherently stateless yet applications can maintain login sessions; distinguish `HttpSession` creation policies in Spring Security Servlet from `WebSession` management in Spring WebFlux; choose appropriate configurations for form login and APIs; accurately read the role of `SecurityContextRepository`; and verify whether an application genuinely uses sessions to remember users across multiple requests.

**Scope:** Spring Security on Servlet and WebFlux, Java 17+, lambda-style `SecurityFilterChain` / `SecurityWebFilterChain` configuration (Spring Security 6/7). The Servlet and WebFlux examples are **two separate Spring Boot applications**; do not combine both web starters into a single sample application.

## 2. Three Easily Confused Concepts: Session, Cookie, and SecurityContext

- **HTTP session** is state associated with a user or client across multiple HTTP requests, usually held on the server side. The browser typically stores only a **session ID** in a cookie and sends that ID on subsequent requests. A cookie holding an ID does not mean all login information resides inside the cookie.
- **`SecurityContext`** holds `Authentication` (principal, authorities, authentication status). Spring Security must decide whether to persist and restore that context across requests.
- **Application session** may also store a shopping cart, UI preferences, or workflow state. Disabling persistence of `SecurityContext` in the session does not automatically forbid application components from using sessions.

In Servlet, the standard session object is `jakarta.servlet.http.HttpSession`, and the cookie is typically named `JSESSIONID` (depending on container and configuration). In WebFlux, the equivalent contract is `org.springframework.web.server.WebSession`, and `CookieWebSessionIdResolver`'s default cookie is named `SESSION`. **These two session types are not the same API**.

Typical session flow:

1. The client accesses a page requiring login; the security chain determines it is unauthenticated.
2. The user logs in successfully; the application stores `SecurityContext` per the configured mechanism.
3. The response sends a session ID to the client (typically via `Set-Cookie`).
4. The client sends the cookie on subsequent requests; the security chain reloads `SecurityContext`.
5. Logging out or session expiration prevents the old context from being used any further.

For APIs authenticating **every request** with a bearer token in the `Authorization` header, steps 2–4 may not happen at all. In that case, token validity is rechecked on each request.

## 3. Servlet: Four Values of SessionCreationPolicy

`org.springframework.security.config.http.SessionCreationPolicy` governs how **Spring Security Servlet** creates or uses `HttpSession`.

| Value | Does Spring Security create HttpSession? | Does it use an existing session for SecurityContext? | How to understand |
| --- | --- | --- | --- |
| `ALWAYS` | Yes, proactively ensures a session exists | Yes | For cases requiring eager session creation |
| `IF_REQUIRED` | Only when needed | Yes | Suited for session-based web login flows; typically the default choice |
| `NEVER` | Does not proactively create under this policy | Yes, if one already exists | Not synonymous with stateless |
| `STATELESS` | Does not create one to store authentication | Does not read `SecurityContext` from `HttpSession` | Suited for independent per-request authentication |

These values describe **Spring Security's scope**. Controllers calling `request.getSession()`, JSPs, CSRF repositories, request caches, session-scoped beans, or other libraries can still create an `HttpSession` depending on configuration. Therefore, **seeing `Set-Cookie: JSESSIONID` is not enough to conclude `STATELESS` was ignored by Spring Security**: you must identify which component created the session and whether the session is used to restore identity.

### 3.1. ALWAYS and IF_REQUIRED

`ALWAYS` uses an eager session creation mechanism (such as `ForceEagerSessionCreationFilter`). `IF_REQUIRED` only spawns a session when an actual need arises, such as maintaining login after form login. Even with `IF_REQUIRED`, a simple public request may not create a session.

`IF_REQUIRED` fits websites with form login that need to recognize users on subsequent page loads without re-entering passwords. Do not switch to `ALWAYS` just to work around a lost-login bug: first inspect cookies, the `SecurityContext` repository, and context-saving steps.

### 3.2. How do NEVER and STATELESS differ?

Suppose a client sends an already existing `JSESSIONID=abc` and the server-side session stores a valid `SecurityContext`:

- With `NEVER`, Spring Security can use that session and restore identity.
- With `STATELESS`, Spring Security does not use `HttpSession` to obtain `SecurityContext`; the request must be authenticated by the configured mechanism (such as bearer token or HTTP Basic).

`NEVER` also **does not guarantee the entire application creates no sessions**. Spring Security documentation notes scenarios where the request cache saves a login-protected request into the session. If you want to avoid that, inspect `HttpSessionRequestCache` and consider `NullRequestCache` / disabling request cache on the appropriate security chain.

### 3.3. SecurityContextRepository is the real link between requests

Key components in Servlet:

- `SecurityContextHolder`: holds the context for the currently running request (usually thread-bound under the default strategy).
- `HttpSessionSecurityContextRepository`: saves/reads context via `HttpSession`.
- `RequestAttributeSecurityContextRepository`: holds context within the same request, useful during dispatches like ERROR.
- `DelegatingSecurityContextRepository`: delegates to multiple repositories; in Spring Security 6, the default configuration combines request attribute and HTTP session.
- `NullSecurityContextRepository`: does not save/read context across requests. Configuring `SessionCreationPolicy.STATELESS` causes Spring Security to select this type of repository and avoid saving requests to the session.

In Spring Security 6 and later, `SecurityContextHolderFilter` defaults to **reading** context; it does not auto-save every mutation. Built-in login mechanisms provided by Spring Security handle saving as part of their flow. If you **write your own** filter/controller to set `Authentication`, you must explicitly save the context via `SecurityContextRepository.saveContext(...)` if you want it persisted to the next request. Calling `SecurityContextHolder.setContext(...)` alone is not enough for custom login.

## 4. Servlet Example: One Stateful Website and One Stateless API

Create a Spring Boot application with Java 17+ and dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. The following three files share the package `example.servlet`; they use an in-memory user and `{noop}` **for learning only**—never store plaintext passwords in production.

**`ServletSessionsApplication.java`**

~~~java
package example.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletSessionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletSessionsApplication.class, args);
    }
}
~~~

**`ServletSecurityConfig.java`**

~~~java
package example.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c -> c.disable())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain pages(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password("{noop}demo123")
                .roles("USER")
                .build()
        );
    }
}
~~~

**`ServletEndpoints.java`**

~~~java
package example.servlet;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ServletEndpoints {
    @GetMapping({"/", "/public"})
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication auth) {
        return "web user=" + auth.getName();
    }

    @GetMapping("/api/me")
    String apiMe(Authentication auth) {
        return "api user=" + auth.getName();
    }
}
~~~

**Test in order:**

~~~bash
# API missing Authorization: rejected (typically HTTP 401).
curl -i http://localhost:8080/api/me

# API with HTTP Basic: authenticated on this request itself.
curl -i -u demo:demo123 http://localhost:8080/api/me

# Unauthenticated web page: redirects to the login page.
curl -i http://localhost:8080/private
~~~

In the second command, the response body is `api user=demo`. Omitting `Authorization` on the next API request means login is not remembered from the previous request. The `/private` flow uses form login (open `http://localhost:8080/login` in a browser); after successful login, the browser typically receives `JSESSIONID` and continues accessing `/private` using that cookie.

**About CSRF:** the example retains default CSRF protection. `STATELESS` **is not synonymous** with disabling CSRF. Especially if a browser automatically sends HTTP Basic or cookies, CSRF remains a consideration for data-mutating operations. Only omit/disable CSRF on an API after evaluating the specific credential mechanism, clients, and attack surface; an API using exclusively client-attached bearer tokens in headers is a common case.

### 4.1. When to choose which value?

- Website with form login using cookies: usually `IF_REQUIRED`; stores login in the session.
- API designed to authenticate every request: `STATELESS`, paired with an appropriate authentication mechanism (e.g., resource server validating bearer tokens).
- Integration needing to leverage a session created by another system without Spring Security proactively creating one: consider `NEVER` and inspect the request cache.
- Business requirement demanding a session be opened from the very first request: `ALWAYS`, though with a concrete justification.

`SessionCreationPolicy` **does not automatically configure** timeouts, concurrent login limits, cookie flags, session fixation protection, or multi-server session sharing. Those are separate configurations. On modern Servlets, Spring Security usually rotates the session ID upon successful authentication (`changeSessionId`) to reduce session fixation risk.

## 5. WebFlux: WebSession Works Differently

Spring WebFlux uses a non-blocking API: obtain the session via `ServerWebExchange.getSession()` (returning `Mono<WebSession>`), rather than interacting directly with Servlet `HttpSession`. `WebSession` offers the following capabilities:

| API | Meaning |
| --- | --- |
| `getAttributes()`, `getAttribute(name)` | Read/write session data by key |
| `start()`, `isStarted()` | Explicitly start the session and check its state |
| `getMaxIdleTime()`, `setMaxIdleTime(Duration)` | View/change maximum idle duration |
| `changeSessionId()` | Rotate the session ID (returns `Mono<Void>`) |
| `invalidate()` | Invalidate the session and clear data (returns `Mono<Void>`) |
| `save()` | Save to store; the framework usually calls this automatically before committing the response |

**Key point:** simply calling `exchange.getSession()` does not necessarily create a saved session or emit a cookie. `WebSession` is **started** when `start()` is called or when an attribute is added to the session; only a started session is persisted as a new session and emits a session ID. `WebSession.save()` is usually handled by the framework at the end of the request; typical applications do not need to call it manually.

Underlying components:

1. `WebSessionManager` coordinates finding/creating sessions; the common implementation is `DefaultWebSessionManager`.
2. `WebSessionIdResolver` reads/writes the session ID, defaulting to `CookieWebSessionIdResolver` with cookie `SESSION`.
3. `WebSessionStore` holds session data; `DefaultWebSessionManager` defaults to `InMemoryWebSessionStore`, suited to single-instance apps rather than multi-node clusters.
4. Spring Session can integrate `WebSessionManager` with `ReactiveSessionRepository` (e.g., Redis) to share sessions across instances.

Cookie timeout (`Max-Age`) and server-side expiration (`maxIdleTime`) are two distinct concepts. A surviving cookie does not guarantee the server has not deleted/expired the session.

### 5.1. WebFlux does not use SessionCreationPolicy

`SessionCreationPolicy` belongs to Servlet `HttpSecurity` configuration; **do not try to apply this enum to WebFlux's `ServerHttpSecurity`**. Instead, manage `SecurityContext` persistence via:

- `ServerSecurityContextRepository`: contract for reading/saving `SecurityContext` across requests (`Mono<SecurityContext> load(exchange)` and `Mono<Void> save(exchange, context)`).
- `WebSessionServerSecurityContextRepository`: stores `SecurityContext` in `WebSession`; when saving the context, it rotates the session ID to guard against session fixation.
- `NoOpServerSecurityContextRepository`: does not save/restore context across requests. Suited for stateless authentication.
- `ReactiveSecurityContextHolder`: provides context within the **Reactor Context** for the request's reactive chain; it is **not** a cross-request session store.
- `ReactorContextWebFilter`: loads `SecurityContext` from the repository to initialize the Reactor Context.

**A configuration subtlety:** `ServerHttpSecurity.securityContextRepository(repo)` configures the repository used by `ReactorContextWebFilter` to **read** context. Individual `AuthenticationWebFilter` instances (such as form login or HTTP Basic) have their **own** repository for **saving** authentication on success. Therefore, when converting a login flow from stateful to stateless, check both where it reads **and** where it saves:

- Form login on WebFlux defaults to `WebSessionServerSecurityContextRepository` for saving authentication.
- WebFlux HTTP Basic defaults to `NoOpServerSecurityContextRepository` for saving authentication.
- With custom authentication filters, configure that filter's repository properly. Changing only the global reader does not guarantee nothing else still writes context into the session.

For OAuth2/OIDC login, the session may also serve redirect flows, authorization requests, and callback correlation. Do not mechanically apply NoOp to an entire interactive login flow without checking related components.

## 6. WebFlux Example: HTTP Basic API Without Remembering SecurityContext

Create a **separate Spring Boot application** with Java 17+, `spring-boot-starter-webflux`, and `spring-boot-starter-security` (do not add `spring-boot-starter-web` to this sample). The following files share the package `example.reactive`.

**`ReactiveSessionsApplication.java`**

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSessionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionsApplication.class, args);
    }
}
~~~

**`ReactiveSecurityConfig.java`**

~~~java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var noSessionContext = NoOpServerSecurityContextRepository.getInstance();

        return http
            .authorizeExchange(a -> a
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .securityContextRepository(noSessionContext)
            .httpBasic(b -> b.securityContextRepository(noSessionContext))
            .formLogin(f -> f.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("demo")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

Here `securityContextRepository(noSessionContext)` controls context restoration, while `httpBasic(b -> b.securityContextRepository(noSessionContext))` controls context saving for the HTTP Basic mechanism. The second line is explicitly shown for clarity; WebFlux's HTTP Basic already defaults to NoOp. Form login is disabled to prevent a login flow from saving context into `WebSession`. Requests using Basic continue to be authenticated individually.

**`ReactiveEndpoints.java`**

~~~java
package example.reactive;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveEndpoints {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me(Authentication auth) {
        return Mono.just("reactive user=" + auth.getName());
    }

    @GetMapping("/visits")
    Mono<String> visits(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer previous = session.getAttribute("visits");
            int next = previous == null ? 1 : previous + 1;
            session.getAttributes().put("visits", next);
            return "visits=" + next;
        });
    }
}
~~~

Note: the `/visits` endpoint **intentionally creates application WebSession data** via `getAttributes().put(...)`. This demonstrates that **a NoOp SecurityContext repository only prevents persisting identity in WebSession; it does not stop controllers from using WebSession themselves**.

Testing:

~~~bash
# Missing credentials: 401.
curl -i http://localhost:8080/me

# Valid credentials: body "reactive user=demo".
curl -i -u demo:demo123 http://localhost:8080/me

# Same account, without Authorization: still 401.
curl -i http://localhost:8080/me

# Controller uses WebSession: response typically issues SESSION cookie.
curl -i -u demo:demo123 -c cookies.txt http://localhost:8080/visits
curl -i -u demo:demo123 -b cookies.txt http://localhost:8080/visits
~~~

The results of the two `/visits` requests when keeping the cookie are `visits=1` and `visits=2`, respectively (as long as the server still keeps the session). This is **application** state, not retained login state: if the second request omits `Authorization`, the security chain still rejects it because `/visits` requires authentication.

**CSRF:** the sample configuration does not disable CSRF; write operations (POST/PUT/DELETE) via cookie/HTTP Basic-capable clients require an appropriate CSRF strategy. Use only the GET endpoints for testing.

### 6.1. If you want stateful WebFlux form login

Replace the `SecurityWebFilterChain` configuration in the previous example with the variant below in a **WebFlux application using a login page**:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    var repo = new WebSessionServerSecurityContextRepository();

    return http
        .authorizeExchange(a -> a
            .pathMatchers("/public").permitAll()
            .anyExchange().authenticated())
        .securityContextRepository(repo)  // read SecurityContext on subsequent requests
        .formLogin(f -> f.securityContextRepository(repo))  // save after login
        .httpBasic(b -> b.disable())
        .build();
}
~~~

Add import `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository`. The same repository is set for both the reader and the form-login filter. When login succeeds, the repository stores `SecurityContext` in `WebSession`; the browser sends back the `SESSION` cookie to stay authenticated on subsequent requests. Standard WebFlux form login already uses this type of repository; explicit configuration makes both the save and read locations clear.

### 6.2. Customizing cookies and WebSession lifetime

Example renaming the cookie and setting WebFlux cookie flags (add to a `@Configuration` class):

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(cookie -> cookie
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax"));
    return resolver;
}
~~~

Imports: `org.springframework.web.server.session.WebSessionIdResolver` and `org.springframework.web.server.session.CookieWebSessionIdResolver`. With `secure(true)`, the cookie is only sent over HTTPS: deployment requires real TLS/HTTPS, not inferences from local HTTP requests. `SameSite=Lax` helps mitigate some cross-site scenarios, **and does not replace** evaluating CSRF. `setCookieMaxAge(...)` controls browser-side cookie lifetime; `WebSession.setMaxIdleTime(Duration)` and session store configuration control server-side session expiration.

When running multiple instances, a local `InMemoryWebSessionStore` can cause clients to "lose sessions" if requests land on another node. Consider Spring Session with a `ReactiveSessionRepository` (such as Redis), aligned with your system's operational, TTL, and serialization requirements.

## 7. Direct Comparison: Servlet vs. WebFlux

| Question | Servlet | WebFlux |
| --- | --- | --- |
| Session object | `HttpSession` | `WebSession` |
| Obtaining session from request | `request.getSession(false)` / `getSession()` | `exchange.getSession(): Mono<WebSession>` |
| Typical default cookie | `JSESSIONID` | `SESSION` |
| Spring Security session policy | `SessionCreationPolicy` | Does not use this Servlet enum |
| Repository keeping stateful login | `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` |
| Repository not keeping login | `NullSecurityContextRepository` | `NoOpServerSecurityContextRepository` |
| Where SecurityContext is read in request | `SecurityContextHolder` / filter | `ReactiveSecurityContextHolder` / `ReactorContextWebFilter` |
| Where session data can live | Servlet container or Spring Session | `WebSessionStore` or reactive Spring Session |
| Per-request API authentication model | `STATELESS` + suitable auth mechanism | NoOp reader + NoOp on each required auth filter |

Both stacks can build **stateful** or **stateless login** applications. WebFlux being "reactive" does not inherently mean sessionless.

## 8. Common Failure Scenarios and Diagnosis

**Issue 1 — "Set `NEVER` yet still seeing `JSESSIONID`."** `NEVER` still uses existing sessions, and request cache/JSP/controllers can create sessions. Check request cache, callers of `getSession()`, and login redirect flows. If the goal is an API that does not persist authentication, look at `STATELESS` instead of switching only to `NEVER`.

**Issue 2 — "`STATELESS` yet responses include `Set-Cookie`."** Do not jump to concluding `SecurityContext` is being saved in `HttpSession`. Identify what generated the cookie (application session, CSRF, reverse proxy, another component); then test a subsequent request **with only the cookie and no credentials**. If it is still recognized as a logged-in user, investigate the security chain, repository, and other authentication mechanisms.

**Issue 3 — "Custom login succeeds yet the next request loses login."** In Spring Security 6/7 Servlet, calling only `SecurityContextHolder.setContext(context)` may not save the context. Call `securityContextRepository.saveContext(context, request, response)` where authentication succeeds in your custom flow. In WebFlux, you must configure the save repository on `AuthenticationWebFilter` and the read repository on `ReactorContextWebFilter`.

**Issue 4 — "WebFlux set to NoOp yet `SESSION` still appears."** NoOp only applies to `SecurityContext`. Look for code calling `getSession()` followed by `start()`/`getAttributes().put(...)`, CSRF/form login mechanisms, and other framework parts that can create a `WebSession`.

**Issue 5 — "Random session loss when running multiple nodes."** Check whether the session store is shared, whether cookies are forwarded, `Secure`/`SameSite`/domain/path attributes, server TTL, clocks, and sticky session rules. For WebFlux, consider reactive Spring Session instead of local in-memory stores if shared sessions are needed.

**Issue 6 — "Disabled CSRF because of `STATELESS`."** Stateless refers only to server-side persistence of authentication state. Browsers can automatically attach HTTP Basic, cookies, or other credentials to requests. Decide on CSRF protection based on how clients carry credentials, not solely on the policy name.

**Issue 7 — "`WebSession` returned means a cookie was created."** `exchange.getSession()` can return an unstarted session object. Check `isStarted()`, the effect of adding attributes, and response `Set-Cookie` headers. Never call `save().block()` in WebFlux; the framework handles saving asynchronously before commit.

## 9. Checklist for Verifying Actual Behavior

1. **Identify the stack:** is the application running Servlet or WebFlux? Read the right `SecurityFilterChain` or `SecurityWebFilterChain`.
2. **Inspect the authentication mechanism:** form login, Basic, bearer token, OAuth2 login, or custom filter? Each mechanism may save/restore differently.
3. **Inspect the repository:** Servlet uses `SecurityContextRepository`; WebFlux uses `ServerSecurityContextRepository`, including each authentication filter's repository.
4. **Observe HTTP:** capture statuses, `Set-Cookie`, `Cookie`, and `Authorization` on subsequent requests; distinguish "has an application session" from "login is remembered."
5. **Retry without credentials:** send only the old session cookie; for an auth-stateless API, the request must not derive identity from a session cookie.
6. **Logout, expiration, and scaling:** verify invalidation effectiveness, server-side TTL, session fixation protection, `Secure`/`HttpOnly`/`SameSite`, and session storage across multiple instances.
7. **Keep tests independent:** verify stateful web login with appropriate browser/MockMvc/WebTestClient tests and stateless APIs with requests with/without auth headers.

## 10. Quick Self-Check Questions

**Q1.** Does `NEVER` prevent Spring Security from using a `SecurityContext` already inside an existing `HttpSession`? **No.** It can use an existing session; `STATELESS` is what avoids using sessions to obtain context.

**Q2.** Why do two requests with the same HTTP Basic credentials not need a session? **Because each request is re-authenticated from the `Authorization` header.**

**Q3.** In WebFlux, does calling `exchange.getSession()` always issue a `SESSION` cookie? **No.** A new session is only started when `start()` is called or an attribute is added.

**Q4.** Why might `.securityContextRepository(NoOp...)` be insufficient if the application still enables WebFlux form login? **Because the authentication filter's repository used to save context can be configured separately**; form login defaults to saving into `WebSession`.

**Q5.** Does enabling Spring Session Redis automatically make an application stateless? **No.** It changes where sessions are stored, and it remains a server-side session if the application uses it.

## Official References

- [Spring Security — Authentication Persistence and Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Persisting Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — SessionCreationPolicy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/http/SessionCreationPolicy.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Framework — WebSession API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — DefaultWebSessionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
