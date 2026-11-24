# WebSessionServerSecurityContextRepository and NoOpServerSecurityContextRepository

## Learning objectives

After this lesson, you will be able to:

- Explain the `ServerSecurityContextRepository` contract in Spring Security WebFlux and how `load` / `save` participate in the reactive authentication lifecycle.
- Distinguish `WebSessionServerSecurityContextRepository` (persists/restores `SecurityContext` via `WebSession`) from `NoOpServerSecurityContextRepository` (does not persist or restore).
- Understand why `SecurityContext` in **the current request's Reactor Context** differs from `SecurityContext` **persisted across multiple HTTP requests**.
- Properly configure both **where context is read for incoming requests** and **where context is saved after authentication** in `ServerHttpSecurity` / authentication filters.
- Run a Java 17+ example comparing a request with HTTP Basic, a subsequent request with only a session cookie, and a request with no credentials.
- Choose the right strategy for web applications using login sessions or APIs authenticating per request with bearer tokens; recognize implications for CSRF, cookies, logout, performance, clustering, and security.

> **Scope:** Spring Security **reactive** on Spring WebFlux, using `org.springframework.security.web.server.context.*` APIs. Do not mix with **Servlet** stack classes such as `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository`, or `HttpSecurity`.

## 1. Why is a SecurityContextRepository needed?

After authenticating credentials, Spring Security produces an `Authentication` (principal, authorities, and related details), placed inside `SecurityContext`. In WebFlux, this context is normally accessed per **subscription** via `ReactiveSecurityContextHolder`, rather than relying on a fixed request `ThreadLocal`.

However, an HTTP request eventually finishes. The next request is a **different** exchange and subscription. If the application wants to remember that the user logged in on an earlier request, it needs a mechanism to **save and reload** the context. `ServerSecurityContextRepository` provides the strategy for doing so.

Three concepts should be kept separate:

| Concept | Role | Scope |
|---|---|---|
| `SecurityContext` | Holds the current `Authentication`. | Used within the request processing pipeline. |
| Reactor `Context` / `ReactiveSecurityContextHolder` | Propagates security context along a reactive subscription, even across thread switches. | **Single subscription** and properly scoped pipeline stages. |
| `ServerSecurityContextRepository` | Decides whether to persist/restore `SecurityContext` across HTTP exchanges. | **Across requests** when an appropriate storage mechanism is used. |

Do not conflate these three. A request can still be authenticated and authorized **even if the repository saves nothing**. Conversely, an existing session does not guarantee a valid `Authentication` is inside it.

Model:

~~~text
Request #1                 Request #2
  |                           |
  v                           v
Authentication             Repository.load(exchange)
  |                           |
  v                           v
SecurityContext ----------> if saved: SecurityContext
  |                           |
  v                           v
Reactor Context #1         Reactor Context #2
  |                           |
  v                           v
Authorization + Handler    Authorization + Handler
  |
  +--> Repository.save(exchange, context) (when the authentication
        filter/processing flow is configured to save)
~~~

With a session-backed repository, the `save` arrow on the first request and `load` on the next request can link two requests via a session ID. With NoOp, they do not link two requests.

## 2. The ServerSecurityContextRepository contract

Spring Security reactive interface:

~~~java
public interface ServerSecurityContextRepository {

    Mono<Void> save(ServerWebExchange exchange,
                    SecurityContext context);

    Mono<SecurityContext> load(ServerWebExchange exchange);
}
~~~

This is an **abbreviated signature for learning** (nullability annotations omitted); it is not the full framework source. The two methods mean:

- `load(exchange)`: emits `SecurityContext` if present; returns an **empty publisher** (`Mono.empty()`) when none is found. Never returns `null` instead of a `Mono`.
- `save(exchange, context)`: returns `Mono<Void>` signaling completion/error of the save operation. Passing `null` as context means deletion in implementations that support it, per the respective API. Do not assume calling the method writes data if the publisher is never subscribed.
- `exchange` is the current HTTP request's `ServerWebExchange`, which can provide `WebSession` via `getSession()`.

Practical point: `Mono<Void> save(...)` must be **composed into the reactive flow**. If you write a custom authentication filter and ignore the `save` publisher, you cannot assume the context was persisted. Avoid `block()` or manual `subscribe()` in a WebFlux filter.

### 2.1. Who calls load, who calls save?

In the WebFlux security chain:

1. `ReactorContextWebFilter` uses the repository configured at `ServerHttpSecurity.securityContextRepository(...)` to look up the request's security context and place it into Reactor Context scope when appropriate.
2. `AuthenticationWebFilter` or the corresponding authentication mechanism, upon successful authentication, can place `Authentication` into **the current request's** context and call the save repository configured **for that authentication filter**.
3. Authorization and downstream code use `ReactiveSecurityContextHolder.getContext()`, `ServerWebExchange.getPrincipal()`, or suitable reactive APIs to access the current user.
4. For the next request, whether identity is restored from the earlier request depends on repository load **and** available cookies/sessions or new credentials.

Important: **choosing where to load and where to save are two things that may need separate configuration.** The `ServerHttpSecurity`-level API sets the repository for `ReactorContextWebFilter`, without automatically replacing every repository used to save on individual authentication filters.

## 3. WebSessionServerSecurityContextRepository: saving context in WebSession

Class: `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository`.

This implementation stores `SecurityContext` in Spring WebFlux's `WebSession` and reads it back from the session attached to subsequent requests. It fits applications that want **log in once, maintain a session** across multiple requests.

### 3.1. Mechanism

~~~text
Successful login
    Authentication succeeds
      -> create SecurityContext containing Authentication
      -> WebSessionServerSecurityContextRepository.save(exchange, context)
      -> WebSession stores security context attribute
      -> response sends session ID info to client (usually via cookie)

Subsequent request
    client sends matching session ID
      -> WebFlux resolves current WebSession
      -> WebSessionServerSecurityContextRepository.load(exchange)
      -> retrieves saved SecurityContext
      -> ReactorContextWebFilter supplies it to reactive security pipeline
      -> authorization/handler sees logged-in user
~~~

**Not every request automatically creates a session.** When saving context is needed, the implementation can access `exchange.getSession()` to obtain the corresponding `WebSession`. Cookie/session lifecycle also depends on WebFlux configuration, session management, response commit timing, and session store infrastructure.

According to Spring Security's Javadoc, `WebSessionServerSecurityContextRepository` changes the session ID when saving the security context to defend against **session fixation**. This behavior does not replace other session protection measures.

### 3.2. Stored attribute

`WebSessionServerSecurityContextRepository.DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME` is the default attribute name constant. You can change the name with `setSpringSecurityContextAttrName(...)` if compatibility with another system truly requires it.

The class also provides `setCacheSecurityContext(boolean)` in supported versions: when enabled, the value returned by `load(exchange)` can be cached with `Mono.cache()` to avoid repeated lookups **within the scope of the cached publisher**. Do not confuse this cache with a cluster-wide session store or cross-request security cache.

### 3.3. Operational implications

- The client usually holds a session cookie (e.g., `SESSION` per WebFlux configuration). The cookie is a session lookup identifier, **not JSON-serialized Authentication contents**.
- The server/session store must retain state and manage timeouts/invalidation. Multiple instances may need Spring Session with a shared backend (such as Redis); with only single-instance in-memory session storage, routing requests to another instance can lose the session.
- CSRF protection is critical for browser applications relying on automatically sent cookies. Storing context in a session **does not eliminate CSRF risk**; configure `CsrfWebFilter`, token repository, and `Secure`/`HttpOnly`/`SameSite` cookie attributes per your threat model.
- Proper logout must remove/update the saved context and handle the session appropriately. Clearing a key in the current request's Reactor Context alone is insufficient to ensure the user is not restored on the next request.
- Session IDs must be protected over HTTPS; avoid logging them or placing them in URLs or tracing.

**There is no rule that "WebSessionRepository = automatic login".** Only when a real authentication flow creates a context and **saves it successfully** does the next request have data to restore.

## 4. NoOpServerSecurityContextRepository: no save and no load

Class: `org.springframework.security.web.server.context.NoOpServerSecurityContextRepository`.

This implementation intentionally **does nothing** for persistence:

~~~java
ServerSecurityContextRepository repository =
    NoOpServerSecurityContextRepository.getInstance();
~~~

This is a short Java snippet for a configuration class; `getInstance()` returns a shared instance.

Behaviorally:

- `load(exchange)` does not look up or create a previously saved `SecurityContext`; the publisher emits no context from the repository.
- `save(exchange, context)` completes without persisting authentication.
- On the request being authenticated, `AuthenticationWebFilter` can still supply context downstream; authorization still works normally. However, the next request needs a fresh authentication mechanism, such as a valid Bearer JWT sent with each request.

This is the common choice for APIs that are **stateless with respect to security-context persistence**. For instance, each request carries `Authorization: Bearer <token>`, the resource server validates the token and creates context for the current request, without storing authentication in `WebSession`.

### 4.1. Not equivalent to disabling every WebSession

Setting `NoOpServerSecurityContextRepository` **does not mean**:

- The server will never create a `WebSession` for other purposes (CSRF token repository, application flash/session state, request cache, etc.).
- Requests cannot have an `Authentication` in the active Reactor Context.
- Spring Security stops authenticating or authorizing.
- Client-side tokens are automatically revoked on logout.
- Application cookies vanish or all other WebFilters stop running.

It specifies only that **the repository does not persist/restore SecurityContext**. A fully stateless design also requires reviewing other mechanisms that might maintain sessions or cookies and verifying the active authentication model.

### 4.2. Using with bearer tokens

In OAuth2 Resource Server JWT applications, requests are typically authenticated via signed/encrypted credentials or introspection **per request**. With NoOp, request A with a valid token is allowed; request B without a token can receive 401. That is the intended behavior.

However, choosing NoOp does not replace configuring:

- issuer/audience/JWK/signature/expiry/token validation;
- scope/authority mapping and authorization rules;
- HTTPS, logging redaction, and token lifetime/revocation policies.

Not storing Authentication in a session **does not make JWTs secure automatically**.

## 5. Technical comparison table

| Criterion | WebSessionServerSecurityContextRepository | NoOpServerSecurityContextRepository |
|---|---|---|
| Purpose | Persists SecurityContext across HTTP requests via WebSession | Does not persist SecurityContext across HTTP requests |
| `save(exchange, context)` | Stores/deletes context in WebSession per implementation contract | Completes without saving |
| `load(exchange)` | Looks up context in WebSession; `Mono.empty()` if absent | Emits no saved context: `Mono.empty()` |
| State to maintain | WebSession and client-side session ID; server-side store | No session store needed for SecurityContext itself |
| Subsequent request with only session cookie | Can restore saved Authentication | Does not restore Authentication from repo |
| Request carrying fresh valid credentials | Can still authenticate; whether saved depends on authentication filter | Can still authenticate within the current request |
| Typical model | Form login, session-based web applications | Bearer token APIs or per-request Basic auth |
| Costs/risks | Session store, cookies, timeouts, clustering, fixation, CSRF | Credential verification per request; token lifecycle managed elsewhere |
| Logout | Must remove saved context/invalidate session per configuration | No context in repository to delete; handle token/revocation separately |
| Common pitfall | Save repo configured, yet auth filter does not call it | Assuming no `WebSession` exists anywhere in the app |

Do not interpret "stateless" as "no security context". Stateless refers only to **not retaining Authentication across requests via the repository**; within a single request, full principal/authorities still exist for authorization.

## 6. Proper configuration: load place differs from save place

### 6.1. Where incoming requests read from

~~~java
http.securityContextRepository(repository);
~~~

In WebFlux, this configuration gives the repository to `ReactorContextWebFilter` to load context and integrate it into Reactor Context as requests traverse the security chain.

### 6.2. Where to save after authentication

Depending on the authentication mechanism, there is another configuration point:

~~~java
http.httpBasic(basic ->
    basic.securityContextRepository(repository));

http.formLogin(form ->
    form.securityContextRepository(repository));
~~~

The two methods above are **independent illustrative snippets**. Enable only the login type you need. They configure the repository for the **authentication filter to save Authentication upon success**.

Defaults worth remembering (per Spring Security reactive 6.3+ APIs):

- For **HTTP Basic**, `HttpBasicSpec.securityContextRepository(...)` defaults to `NoOpServerSecurityContextRepository` so Basic does not automatically create a session on every request.
- For **form login**, `FormLoginSpec.securityContextRepository(...)` defaults to `WebSessionServerSecurityContextRepository` so login can maintain a session.
- These defaults **do not have to** match the repository instance used in `ServerHttpSecurity.securityContextRepository(...)` for loading. When changing strategies, wire **both sides** consistently and test.

That is why a common mistake is writing only:

~~~java
// Insufficient to ensure every authentication mechanism saves with this repo.
http.securityContextRepository(new WebSessionServerSecurityContextRepository());
~~~

If using HTTP Basic while Basic's save repository remains NoOp, Basic authentication on one request **does not automatically produce a security context persisted in WebSession**. The next request without Basic credentials can still get 401. Conversely, if the authentication filter saves to session while `ReactorContextWebFilter` uses NoOp to load, the next request still cannot restore context from the session.

## 7. Standalone runnable Java 17+ example: one API with two strategies

The example runs with **Spring Boot 3.3.5**, **Java 17+**, Spring WebFlux, and Spring Security 6.3.x managed by Spring Boot. The experiment explicitly configures:

1. `ServerHttpSecurity.securityContextRepository(repo)` to **load** with the chosen repo.
2. `httpBasic(basic -> basic.securityContextRepository(repo))` to **save** with the chosen repo.
3. A `GET /me` endpoint requiring authentication and returning the principal name.
4. Selecting the repository via `--demo.repository=session` or `--demo.repository=noop`.

**Why intentionally use Basic?** To clearly observe the persistence effect: in session mode, the second request sends only the cookie, **without resending Basic credentials**, and can still authenticate from the saved context. This is a way to test the repository mechanism, **not a recommendation to use HTTP Basic as session-based login in production**. For real web login, design proper form login/SSO and CSRF protection.

### 7.1. Project structure

~~~text
security-context-repository-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/SecurityContextRepositoryDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-context-repository-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

`src/main/java/example/SecurityContextRepositoryDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityContextRepositoryDemo {

    public static void main(String[] args) {
        SpringApplication.run(SecurityContextRepositoryDemo.class, args);
    }

    @Bean
    ServerSecurityContextRepository securityContextRepository(Environment env) {
        String mode = env.getProperty("demo.repository", "session");

        return switch (mode) {
            case "session" -> new WebSessionServerSecurityContextRepository();
            case "noop" -> NoOpServerSecurityContextRepository.getInstance();
            default -> throw new IllegalArgumentException(
                "Unsupported demo.repository: " + mode);
        };
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ServerSecurityContextRepository repository) {

        return http
            // Use this repo to load context via ReactorContextWebFilter.
            .securityContextRepository(repository)
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            // HTTP Basic normally does not save sessions by default;
            // this demo intentionally uses the same repo for saving.
            .httpBasic(basic ->
                basic.securityContextRepository(repository))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // GET /me only; keep default CSRF configuration intact.
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // For localhost demo only, never use in production.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class MeController {
        @GetMapping("/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal ->
                    Map.of("username", principal.getName()));
        }
    }
}
~~~

**Code explanation:**

- The `securityContextRepository(...)` bean returns exactly one of the two implementations.
- `@EnableWebFluxSecurity` enables reactive web security.
- The two calls `securityContextRepository` and `httpBasic(...securityContextRepository...)` are the key point of the lesson: **load and save with the same repo**.
- `formLogin(...disable)` avoids a form login flow using a different default repository, which would confuse the experiment.
- The controller inspects only `exchange.getPrincipal()` populated by Spring Security, never reading usernames from the `Authorization` header manually.
- The code uses Java `switch` expressions (supported in Java 17) and `Map.of(...)`; no Lombok is required.

### 7.2. Running in WebSession mode

Requires JDK 17+ and compatible Gradle/Gradle Wrapper. In the project directory:

~~~bash
gradle bootRun --args="--demo.repository=session"
~~~

If the project has a wrapper, use `./gradlew bootRun --args="--demo.repository=session"` on Linux/macOS or `gradlew.bat bootRun --args="--demo.repository=session"` on Windows.

In another terminal:

~~~bash
# Request A: send valid Basic auth and save cookie if issued by server.
curl -i -c session-cookies.txt -u learner:demo-pass http://localhost:8080/me

# Request B: DO NOT send -u; send only the cookie from request A.
curl -i -b session-cookies.txt http://localhost:8080/me
~~~

With the demo app running and using the default session store, expected results:

- Request A: `200 OK`, body contains `{"username":"learner"}`; the response typically includes `Set-Cookie: SESSION=...` or the configured session cookie.
- Request B: `200 OK`, body contains the same username even without a Basic header this time. The repository reloaded `SecurityContext` via `WebSession` using the saved cookie.
- If request B gets `401`, check the cookie jar/cookie domain and port, Basic's `save`, `ReactorContextWebFilter`'s `load`, session timeout, and session store. Do not conclude the repository is wrong solely from the status code.

The JSON body above has a single field, so its value is fixed in the demo; HTTP headers (cookie ID, timestamps, security headers) vary. The `curl -i` output is an HTTP response, not fixed stdout from the Java program.

### 7.3. Running in NoOp mode

Stop the app in the first terminal, restart the same project with the changed argument:

~~~bash
gradle bootRun --args="--demo.repository=noop"
~~~

In another terminal:

~~~bash
# Request A: valid Basic credentials, authenticates within this request.
curl -i -c noop-cookies.txt -u learner:demo-pass http://localhost:8080/me

# Request B: no Basic auth, only try sending any recorded cookie.
curl -i -b noop-cookies.txt http://localhost:8080/me
~~~

Expected results:

- Request A: `200 OK` and body `{"username":"learner"}`. **NoOp does not block a request with valid Authentication.**
- Request B: `401 Unauthorized` because there are no new Basic credentials and no SecurityContext restored from the repository. The HTTP Basic entry point may add `WWW-Authenticate`.
- `NoOp` itself does not emit `Set-Cookie` for `SecurityContext`; if the app or another component issues a cookie, that cookie's existence **does not prove SecurityContext was saved**.

Try next:

~~~bash
# Each request carries valid Basic auth: in NoOp mode it still returns 200.
curl -i -u learner:demo-pass http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/me
~~~

Both requests return 200 because **each request re-authenticates**. This illustrates that NoOp only skips saving/restoring security context across requests, rather than disabling authentication.

**Safety when testing:** Passwords using `{noop}` (plain text) are solely for localhost demos; never use in real deployments. HTTP Basic sends credentials on every request, requiring TLS/HTTPS in deployed environments. Never keep hard-coded accounts or expose test apps to the public Internet.

## 8. Internal flow: why do the two setups produce different results?

### 8.1. WebSession + explicit Basic save

~~~text
GET /me + Authorization: Basic ...
  -> AuthenticationWebFilter authenticates successfully
  -> Authentication exists in request #1 Reactor Context
  -> repository.save(exchange #1, SecurityContext)
       WebSession stores SecurityContext
       session ID issued/returned to client
  -> Controller: 200 {"username":"learner"}

GET /me + Cookie: SESSION=... (no Basic)
  -> ReactorContextWebFilter uses repository.load(exchange #2)
       reads SecurityContext from saved WebSession
  -> Authorization sees Authentication
  -> Controller: 200 {"username":"learner"}
~~~

### 8.2. NoOp + non-persisting Basic save

~~~text
GET /me + Authorization: Basic ...
  -> AuthenticationWebFilter authenticates successfully
  -> Authentication exists in request #1 Reactor Context
  -> repository.save(exchange #1, context) completes without persisting
  -> Controller: 200 {"username":"learner"}

GET /me (no Basic)
  -> repository.load(exchange #2) is empty
  -> No restored Authentication
  -> anyExchange().authenticated() rejects
  -> HTTP Basic entry point: 401
~~~

The crucial verification point is that **the subsequent request carries no credentials**. If you pass `-u learner:demo-pass` on both requests, both strategies return 200 and fail to distinguish whether the repository persists context.

## 9. Choosing a repository by authentication model

### 9.1. Web applications using form login and session cookies

Most browser-interactive applications want users to log in once and send a cookie on subsequent requests. `WebSessionServerSecurityContextRepository` is usually appropriate. Configure:

- Form login/SSO (proper authentication manager and success/failure handlers) to save to `WebSession`;
- `ServerHttpSecurity`'s load repository compatible with where form login saves;
- CSRF protection for state-changing requests when browsers automatically send cookies;
- Cookies with `Secure` over HTTPS, appropriate `HttpOnly`/`SameSite`, session timeout, and invalidation;
- A session store reliable enough for scaled environments (reactive Spring Session with Redis or equivalent infrastructure);
- Real tests for logout and session expiry workflows.

Config-only example (placed in a compatible `SecurityWebFilterChain` bean; do **not** combine simultaneously with the demo's `httpBasic`):

~~~java
ServerSecurityContextRepository sessionRepo =
    new WebSessionServerSecurityContextRepository();

return http
    .securityContextRepository(sessionRepo)
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/login", "/public/**").permitAll()
        .anyExchange().authenticated())
    .formLogin(form ->
        form.securityContextRepository(sessionRepo))
    .build();
~~~

The snippet above is an **illustrative configuration fragment only**, omitting the user details bean and login UI. Spring Security can provide a default login page if the app has not created a custom one. With a custom login page, configure the URL/form fields/success handler and CSRF token properly for login to work.

### 9.2. Stateless bearer token APIs

APIs receiving a bearer access token on every request generally do not need to save `SecurityContext` into `WebSession`:

~~~java
return http
    .securityContextRepository(
        NoOpServerSecurityContextRepository.getInstance())
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/health").permitAll()
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        org.springframework.security.config.Customizer.withDefaults()))
    .build();
~~~

This is an **integration configuration snippet**, requiring `spring-boot-starter-oauth2-resource-server`, issuer/JWK validation, and appropriate OAuth2 Resource Server configuration. Every request carrying a valid bearer token is authenticated from the token; requests without a token on protected routes receive 401. Never assign Authentication for unverified tokens.

**Stateless boundary:** `NoOp` does not automatically disable form login, request cache, or other session sources. For APIs not relying on automatically sent cookies, evaluate CSRF against the actual model; never disable CSRF merely because you call the API "REST".

### 9.3. Multiple SecurityWebFilterChains

If an application has both a session-based website and a bearer-based API, you can configure **two SecurityWebFilterChain beans** with separate matchers/ordering. Within each chain:

- Web routes → session repository + appropriate form login.
- API routes → NoOp + appropriate resource server token auth.
- Have a clear fallback chain if all URLs need protection; never leave sensitive paths outside all chains.
- Do not assume a repository applies app-wide if chains are configured differently.

Never use a single repository bean with mutable global state to switch between session/NoOp per request. The choice belongs in controlled chain/matcher configuration.

## 10. Logout, session fixation, clustering, and real-world risks

### 10.1. Logout in session mode

When a user logs out, the logout mechanism must delete the saved `SecurityContext` and, depending on policy, invalidate `WebSession`; clearing only the current request's Reactor Context **is not enough** to ensure subsequent requests are not restored from the old cookie. Use Spring Security's logout handler and verify that a subsequent request with the old cookie is rejected.

`WebSessionServerSecurityContextRepository`'s Javadoc notes that it rotates the session ID when saving context to mitigate session fixation. Session fixation testing should inspect the cookie/session ID before and after authentication, and verify another user cannot hijack an exposed session ID.

### 10.2. Logout in NoOp mode

The NoOp repository has no `SecurityContext` to delete. With JWTs or bearer tokens, client-side "logout" usually removes the credential from storage; the old token **can remain valid** until expiry unless a revocation mechanism exists. If immediate revocation is required, design revocation/denylist/introspection or token rotation as needed.

### 10.3. Loading from WebSession is not authorization

`SecurityContextRepository.load` only retrieves `SecurityContext`; it does not directly decide whether the user is allowed to view a resource. Authorization still relies on Authentication/authorities and rules (`authenticated()`, `hasRole`, reactive method security...). Stale sessions, disabled users, or changed permissions may require context refresh/revocation depending on the security model; never assume a session always reflects the latest permission data.

### 10.4. Multi-instance design

A session in server A's memory does not automatically appear on server B. With a load balancer and horizontal scaling, either use bounded sticky sessions or prefer an appropriate shared session store (e.g., reactive Spring Session with Redis). Consider timeouts, failover, serialization, Redis access control, and cluster-wide session deletion/invalidation.

NoOp reduces session-store requirements for Authentication, but can increase per-request token validation/identity lookup frequency. Assess real bottlenecks, safely cache keys/JWKs/introspection, and apply rate limits.

### 10.5. Status display and logging

Never log raw `SecurityContext`, bearer tokens, `SESSION` cookies, passwords, or Basic credentials. When debugging, log a correlation ID and harmless indicators: whether an Authorization header was present (without logging its value), status, matched filter, and repository mode. Avoid returning detailed authentication failure reasons to clients beyond standard HTTP behavior.

## 11. Common mistakes and fixes

**Mistake 1 — Configuring only the load point and forgetting the save point.**

~~~java
http.securityContextRepository(sessionRepo);
// Basic authentication may still default to saving into NoOp!
~~~

Fix by configuring the repository on the authentication mechanism that needs persistence, such as `httpBasic(basic -> basic.securityContextRepository(sessionRepo))` in the demo. Similarly, configure form login with a compatible repository.

**Mistake 2 — Configuring only the save point, while subsequent requests load with another repo.**

If the repository saves to `WebSession` while `ReactorContextWebFilter` reads from NoOp, subsequent requests see no Authentication. Fix by configuring consistently at both places.

**Mistake 3 — Thinking NoOp makes every request anonymous.**

Valid credentials in a single request still create an `Authentication` in that request's Reactor Context. Test request A with valid Basic → 200, request B without Basic → 401.

**Mistake 4 — Thinking WebSessionRepo authenticates headers itself.**

The repository only saves/restores `SecurityContext`; **it does not verify username/password/JWT**. Authentication managers/filters perform verification; never build `SecurityContext` from unverified client headers.

**Mistake 5 — Calling `repository.save(...).subscribe()` and returning the response immediately.**

Operations may not complete before the response commits; errors are not coordinated properly. Fix by composing the `save` publisher into the processing chain and returning `Mono<Void>` for the framework to subscribe.

**Mistake 6 — Enabling WebSessionRepository for a JWT API thinking it is mandatory.**

Self-contained bearer tokens sent per request usually do not need security-context sessions. Avoid creating unnecessary server state and cookies unless security requirements demand it.

**Mistake 7 — Disabling CSRF unconditionally to make form login/sessions work.**

If browsers automatically send cookies on state-changing requests, take CSRF seriously. Configure CSRF tokens/routes properly; never use "WebFlux is reactive" as an excuse to drop CSRF.

**Mistake 8 — Checking only the cookie without checking whether the next request sends Authorization.**

If the next request still sends Basic/JWT, it can return 200 even with NoOp; that does not prove persistence. Test the next request **with only the session cookie**, without credentials.

**Mistake 9 — Confusing Servlet `HttpSessionSecurityContextRepository` with WebFlux `WebSessionServerSecurityContextRepository`.**

Use the classes from the right package and stack. Servlet `SecurityContextRepository`/`HttpSecurity` APIs cannot substitute for reactive `ServerSecurityContextRepository` and `ServerHttpSecurity`.

**Mistake 10 — Thinking NoOp revokes JWTs or deletes cookies automatically.**

NoOp does not save Authentication; it does not manage client token lifetimes, cookies outside security context, or still-valid signed tokens. A dedicated revocation/logout mechanism is needed.

**Mistake 11 — Equating SecurityContext persistence with Reactor Context caching.**

`setCacheSecurityContext` and Reactor `Mono.cache()` optimize publisher access, not long-lived cross-request session storage. Session stores and timeouts are managed separately.

**Mistake 12 — Sharing a mutable Authentication across multiple users/requests.**

Never store one request's Authentication or WebSession in a singleton field. Control scope via the framework, per-subscriber context, and exchange-bound repositories.

## 12. Testing checklist

Before taking a configuration to production, verify at a minimum:

1. **Current authentication:** With valid credentials, protected routes return 200 and the right principal, even when the repository is NoOp.
2. **Persistence:** With WebSession repo and proper save wiring, a subsequent request with only the session cookie (no Authorization) is restored; with NoOp, a subsequent request lacking credentials gets 401.
3. **No credentials:** The initial request to a protected route with neither credentials nor a valid session must be rejected.
4. **Invalid credentials:** Requests with wrong Basic/password or expired bearer tokens must be rejected without leaking tokens/passwords in logs.
5. **Session cookies:** Cookies are handled with proper `Secure`, `HttpOnly`, `SameSite`, Path, and HTTPS per environment.
6. **Logout:** Session-based logout causes subsequent requests with the old cookie to fail; token-based logout follows revocation/expiry policy.
7. **CSRF:** State-changing routes are tested with/without CSRF tokens when the app uses cookie auth.
8. **Multi-instance:** Context loading after switching instances still works if distributed operation is required; session-store failures never create an authorization bypass.
9. **Matchers/chains:** Every route belongs to the right `SecurityWebFilterChain`; no sensitive endpoint sits outside all chains.
10. **Observability:** Correlation IDs and logs provide enough detail to debug without recording credentials/sessions.
11. **Timeouts:** Expired sessions reject requests without credentials; expired tokens are rejected by the resource server.
12. **Permission changes:** Plan updates/invalidation of stale contexts when roles or accounts change.

## 13. Self-assessment

**Question 1.** If `NoOpServerSecurityContextRepository` is used, will a request sending a valid JWT be authenticated?

**Answer:** Yes, when the token is successfully verified by the resource server configuration. `Authentication` exists within the current request, though NoOp does not persist it to subsequent requests.

**Question 2.** Why can configuring `http.securityContextRepository(sessionRepo)` alone be insufficient for Basic authentication to persist context?

**Answer:** Because the `ServerHttpSecurity`-level setting is used for loading via `ReactorContextWebFilter`; the repository used to save after authentication is configured separately on `HttpBasicSpec.securityContextRepository`, which defaults to NoOp.

**Question 3.** An application uses form login to save sessions, yet returns 401 when the next request includes the cookie. What should you check?

**Answer:** Check whether the cookie was sent properly, `WebSession` is still valid and on the same store, the authentication filter saved to the right repo, `ReactorContextWebFilter` loads from the same repo, the request matches the security chain, and authorization rules accept that principal.

**Question 4.** Does disabling security-context persistence automatically disable CSRF?

**Answer:** No. CSRF and security-context persistence are two separate mechanisms; evaluate CSRF based on whether browsers can automatically send credentials on state-changing requests.

**Question 5.** Does seeing a `SESSION` cookie mean the user is logged in?

**Answer:** No. A session can be empty, expired, or hold only CSRF or application data; `Authentication` must be loaded and verified through Spring Security.

**Question 6.** Does using WebSessionRepository mean authorization is no longer necessary?

**Answer:** No. Restored context only provides the saved `Authentication`; authorization is still needed to decide whether the user has permission for the specific resource and action.

## Official documentation

- Spring Security — `ServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- Spring Security — `WebSessionServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security — `NoOpServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html
- Spring Security — `ServerHttpSecurity` (`ReactorContextWebFilter` repository): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — `ServerHttpSecurity.HttpBasicSpec` (default NoOp save repository): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security — `ServerHttpSecurity.FormLoginSpec` (default WebSession save repository): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — CSRF in WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework — WebSession API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
