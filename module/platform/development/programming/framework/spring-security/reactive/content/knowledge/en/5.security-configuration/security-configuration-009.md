# NoOpServerRequestCache and Avoiding Saved Requests in Sessionless APIs

## 1. The problem to solve

A Spring WebFlux application can serve two different types of access flows:

- **Website with interactive login:** a user visits a protected page, the app redirects to the login page, and after a successful login returns the user to the originally requested URL.
- **Sessionless HTTP API (stateless API):** a client sends credentials or a Bearer token on each request, receives the corresponding HTTP status, and decides the next step itself; the server does not need to remember the URL the client called before authentication.

Spring Security has a **saved request** mechanism for the first case. It remembers a request interrupted by authentication so that once authenticated, execution can continue or redirect to that address. However, for a stateless API, this mechanism is usually unnecessary and can unintentionally introduce dependencies on `WebSession` or cookies if an unsuitable request cache is chosen.

**`NoOpServerRequestCache`** is the `ServerRequestCache` implementation for WebFlux that intentionally **does not save, look up, or restore requests**. Spring Security describes it as a "do-nothing" request cache for stateless applications.

This lesson focuses on this class's role in Reactive Spring Security **configuration**, while also clarifying why **disabling the request cache alone does not make the entire application stateless**.

After this lesson, you will be able to:

1. Explain how saved requests work in a login flow and why stateless APIs do not need that behavior.
2. Distinguish `ServerRequestCache` from `ServerSecurityContextRepository`, HTTP response caches, Reactor Context, and token storage mechanisms.
3. Configure `NoOpServerRequestCache` via `ServerHttpSecurity` for a `SecurityWebFilterChain`.
4. Run a Java 17+ WebFlux API, observe HTTP 200/401 behavior, and confirm each request needs fresh credentials.
5. Directly unit-test the no-op contract and spot mistakes with sessions, CSRF, redirects, multiple security chains, and the "used `NoOp` yet still see cookies" pitfall.

## 2. What is a saved request?

Suppose a website uses form login:

~~~text
(1) Browser: GET /account/orders
                    |
                    v
(2) Unauthenticated --> redirect to /login
                    |
                    v
(3) User logs in
                    |
                    v
(4) Login succeeds --> return to /account/orders
~~~

To accomplish step (4), the application can save the original request address. In Spring Security WebFlux, `ServerRequestCache` is the abstraction for that mechanism. Some implementations:

- `WebSessionServerRequestCache`: saves request info in `WebSession`.
- `CookieServerRequestCache`: saves the requested URI in a cookie via its corresponding mechanism.
- `NoOpServerRequestCache`: does not save requests.

**It does not mean "saving the entire HTTP request to replay at any arbitrary time".** Its primary purpose is supporting URLs/redirects in flows interrupted by authentication. Never treat a saved request as a secure store for the body of a POST transaction, a command, or sensitive business data to be re-executed automatically.

For an SPA/mobile client or service-to-service API using Bearer tokens, the flow is typically:

~~~text
(1) Client: GET /api/orders
             Authorization: (missing / invalid token)
                    |
                    v
(2) Server: 401 Unauthorized
                    |
                    v
(3) Client obtains/refreshes token via authentication flow
                    |
                    v
(4) Client sends a new request with a valid token
                    |
                    v
(5) Server: 200 response + authorized data
~~~

The server does not need to remember `/api/orders` on the client's behalf. If it wants to re-send the request after logging in, the client manages UI state and constructs a new request per business logic.

### 2.1. Why shouldn't a sessionless API keep saved requests?

Saving URLs just to support redirects can cause unwanted side effects:

- Consumes server/cookie resources for a step not in the HTTP API contract.
- Pulls in `WebSession` reads or writes when the system expects each request to be independent.
- When clients expect JSON 401s, post-login navigation logic makes flows harder to predict.
- Harder to verify isolation across requests and instances when scaling horizontally.
- Easy to confuse: saving a pre-login URI does not mean authentication or post-login authorization has been saved.

**Limitation:** if the application never hits any branch that triggers saved requests, the runtime impact of changing it may be small. Configuring `NoOpServerRequestCache` is still useful because it explicitly declares the policy: "do not maintain saved-request state for this security flow".

## 3. Four easily confused kinds of state

| Mechanism | What does it store/answer? | Typical API/object | Disabled just by using `NoOpServerRequestCache`? |
| --- | --- | --- | --- |
| **Saved request** | Pre-login URI/request so the user can return after authenticating | `ServerRequestCache` | **Yes:** specifically saved-request functionality uses this cache |
| **Authentication persistence** | `SecurityContext` saved/loaded across requests | `ServerSecurityContextRepository` | **No** |
| **Reactor Context** | Context attached to the **current subscription**, including the request's security context | `ReactiveSecurityContextHolder` | **No** |
| **HTTP response cache** | Response data for browser/proxy/CDN or application cache | `Cache-Control`, CDN, Redis, etc. | **No** |

The most important distinction is between two interfaces:

~~~java
// Two different APIs; illustrative signatures, not a standalone program.

// Saved request:
ServerRequestCache requestCache;

// SecurityContext persistence:
ServerSecurityContextRepository securityContextRepository;
~~~

`NoOpServerRequestCache` lives in package:

~~~text
org.springframework.security.web.server.savedrequest
~~~

Whereas `NoOpServerSecurityContextRepository` lives in package:

~~~text
org.springframework.security.web.server.context
~~~

The two classes have similar names, yet **they are not substitutes for each other**. One disables saving requests for replay/redirect; the other disables saving and loading `SecurityContext` via the repository. You can configure both for a stateless API, while still inspecting session usage by other components separately.

### 3.1. Statelessness is a property of the whole design

A sessionless API typically has these characteristics:
- The client sends required authentication credentials **on every request**.
- The server does not rely on a prior login session to grant access.
- Requests can be handled across different instances without sharing authentication sessions.
- Permission decisions rely on the identity/permissions verified for the current request and relevant business data.

However, "stateless authentication" **does not mean** the application uses no database, product cache, logs, rate limiting, or state of any kind. A database can still manage orders/accounts; the system can still store a list of revoked tokens or business state as needed. What must be avoided is unintentionally depending on a **previous request's session to authenticate the current request**.

## 4. What does NoOpServerRequestCache actually do?

`NoOpServerRequestCache` implements `ServerRequestCache` and exposes a shared instance via:

~~~java
NoOpServerRequestCache.getInstance()
~~~

The three methods in the interface:

| Method | Meaningful result when using NoOp |
| --- | --- |
| `Mono<Void> saveRequest(ServerWebExchange exchange)` | Completes without saving the request |
| `Mono<URI> getRedirectUri(ServerWebExchange exchange)` | `Mono.empty()`: no saved URI to redirect to |
| `Mono<ServerHttpRequest> removeMatchingRequest(ServerWebExchange exchange)` | `Mono.empty()`: no old request to retrieve/remove |

Consequently, an unauthenticated request is **not** retained by the no-op cache to resume after client login. Spring Security can still choose HTTP 401 or redirect to login depending on the configured **authentication entry point**; `NoOpServerRequestCache` itself does not decide status codes or redirects.

A proper mental model of this behavior:

~~~text
ServerRequestCache.saveRequest(exchange)
                  |
            NoOp: completes
                  |
            No saved request created

ServerRequestCache.getRedirectUri(exchange)
                  |
            NoOp: Mono.empty()
                  |
            No old URI to restore
~~~

In Reactive Streams, `Mono.empty()` is a publisher that completes with no value—**not** `null` and not an error. All methods remain part of the reactive API so they compose cleanly with the filter chain.

### 4.1. How does NoOp differ from a "temporarily empty cache"?

A freshly created session cache might not have saved a request yet today, yet it **is capable of saving one in the future** when a flow calls `saveRequest`. NoOp intentionally holds no state even if `saveRequest` is called repeatedly.

Therefore, using `NoOpServerRequestCache` keeps the policy stable against future changes to login branches or entry points if some component later interacts with the configured request cache.

## 5. Position in the security filter chain

Reactive Spring Security normally operates via a `SecurityWebFilterChain`, configured with `ServerHttpSecurity`:

~~~text
HTTP request
     |
     v
SecurityWebFilterChain
     |
     +--> Authentication (Bearer / Basic / appropriate mechanism)
     |
     +--> When authentication is required without valid credentials:
     |         |
     |         +--> Entry point behavior (401 or redirect per configuration)
     |         |
     |         +--> If the flow involves saved requests:
     |                     ServerRequestCache
     |                     |
     |                     +--> NoOp: do not save
     |
     +--> Authorization: check authorities/business permissions
     |
     v
WebFlux Handler --> Mono/Flux --> HTTP response
~~~

This is a **conceptual diagram**, not an exhaustive depiction of every WebFilter's position or every authentication branch. The request cache may be used by parts of login flows or filters involved in replay/redirect. A simple HTTP Basic or Bearer API request may return 401 directly without invoking request-saving logic.

**Key takeaway:** `NoOpServerRequestCache` is not a "custom authentication filter" running independently before controllers. It is a **strategy** that Spring Security components can consult when handling saved requests. Configure it on the appropriate `SecurityWebFilterChain`.

## 6. Standard configuration: no-op request cache

For Spring Security WebFlux 6.x, the explicit configuration syntax is:

~~~java
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

// Inside a declared SecurityWebFilterChain:
.requestCache(cache ->
        cache.requestCache(NoOpServerRequestCache.getInstance()))
~~~

This syntax is passed directly to `ServerHttpSecurity`; using lambdas is the idiomatic configuration style for modern Spring Security releases.

An alternative when you are certain no request-cache functionality at all is needed in the chain:

~~~java
// Alternative configuration snippet:
.requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
~~~

Both serve the goal of **not using saved requests** in the chain, though their configuration semantics differ: the first assigns a no-op implementation; the second disables the request cache spec entirely. When the lesson goal is to use and observe `NoOpServerRequestCache`, choose the first form.

**Avoid mixing APIs:** `HttpSecurity` + `NullRequestCache` is the familiar Servlet/Spring MVC pairing. For WebFlux, use `ServerHttpSecurity` + `NoOpServerRequestCache`. Do not bring `HttpSessionRequestCache`, `SecurityFilterChain`, or Servlet `Filter` into WebFlux to configure a reactive application.

## 7. Runnable Java 17+ example: API without saved requests

The example below uses Spring Boot **3.3.13**, Spring Security 6.x, Java 17, and Gradle. It deliberately enables HTTP Basic for testing with `curl`; Basic makes HTTP 401 easy to observe, not a default recommendation for production APIs. Authentication uses an in-memory user strictly for the demo.

**Verification goals:**
- Users without credentials are rejected at protected endpoints.
- Users with valid credentials are processed on the current request.
- A new request **without credentials** is still rejected, even after an earlier request succeeded.
- No saved request exists to auto-redirect or replay from cache.
- Code clearly separates no-op request cache and no-op security-context repository.

Project structure:

~~~text
noop-request-cache-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/
        └── NoOpCacheContractTest.java
~~~

### 7.1. Gradle

**`settings.gradle`**

~~~groovy
rootProject.name = 'noop-request-cache-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-webflux` provides WebFlux HTTP; `spring-boot-starter-security` provides Reactive Spring Security; `reactor-test` supports testing Publishers with `StepVerifier`. Dependencies resolve compatible versions through Spring Boot's dependency management.

### 7.2. Application

**`src/main/java/demo/DemoApplication.java`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.3. Security configuration

**`src/main/java/demo/SecurityConfig.java`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public").permitAll()
                        .anyExchange().authenticated()
                )
                .requestCache(cache ->
                        cache.requestCache(NoOpServerRequestCache.getInstance())
                )
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}localpass")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
~~~

**Explanation of each choice:**

1. `authorizeExchange`: `/api/public` requires no login; remaining paths require authentication. `anyExchange()` establishes an explicit default policy.
2. `requestCache(... NoOpServerRequestCache.getInstance())`: does not retain prior requests for post-login redirect/replay.
3. `securityContextRepository(NoOpServerSecurityContextRepository.getInstance())`: does not use the repository to save/load `SecurityContext` **across requests**. `Authentication` can still exist in the Reactor Context of the **current request**.
4. `httpBasic`: clients send username/password on every request; Spring Security authenticates upon receiving credentials.
5. `formLogin(...disable)`: no HTML login page in the demo API.
6. `MapReactiveUserDetailsService`: provides the in-memory `reader` user for learning; not a production user store.

**Important:** `NoOpServerRequestCache` and `NoOpServerSecurityContextRepository` address **two different kinds of state**. Configuring both clarifies the demo model; one class cannot substitute for the other.

**Safety:** `{noop}` deliberately skips password hashing and is strictly for local experiments. Basic credentials are Base64, not encryption; never use over unencrypted HTTP in real environments. Use HTTPS and a proper password encoder when deploying. The example performs only HTTP GETs with no state-changing operations. Do not disable CSRF simply because the app has `/api` paths; browser credential handling, cookies, and write endpoints determine the right CSRF policy.

### 7.4. Controller

**`src/main/java/demo/ApiController.java`**

~~~java
package demo;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    public Mono<String> privateEndpoint() {
        return Mono.just("private");
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "user:"
                        + context.getAuthentication().getName());
    }
}
~~~

Handlers return Publishers and never call `block()` or `subscribe()`. `ReactiveSecurityContextHolder` retrieves authentication from the request pipeline's context after credentials are verified; it does not require saving context in a session.

### 7.5. Running and comparing statuses

In the project directory, run:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, you can use `./gradlew bootRun`. By default the server listens on port 8080; in another terminal run:

~~~bash
# 1. Public endpoint
curl -i http://localhost:8080/api/public

# 2. Protected endpoint, no credentials
curl -i http://localhost:8080/api/private

# 3. Protected endpoint, valid credentials supplied
curl -i -u reader:localpass http://localhost:8080/api/private

# 4. Completely new request, again without credentials
curl -i http://localhost:8080/api/private

# 5. Read the principal of the current request
curl -i -u reader:localpass http://localhost:8080/api/me

# 6. Wrong password
curl -i -u reader:wrong http://localhost:8080/api/private
~~~

| Command | Expected status | Body/meaning |
| --- | --- | --- |
| 1 | **200 OK** | `public` |
| 2 | **401 Unauthorized** | Credentials required; HTTP Basic may send `WWW-Authenticate` |
| 3 | **200 OK** | `private` |
| 4 | **401 Unauthorized** | The previous successful request **did not** log in the new request |
| 5 | **200 OK** | `user:reader` |
| 6 | **401 Unauthorized** | Invalid authentication credentials |

Error bodies and header sets can vary across Spring Security versions and configs; the primary results to verify are the **HTTP status codes and bodies of successful responses**.

**Do not over-infer from `curl`:** seeing no redirect matches the HTTP Basic entry point, yet that observation alone **does not prove** the NoOp cache is active; Basic may avoid redirects even with a different cache. Direct tests in the next section verify the no-op contract.

## 8. Unit testing the NoOpServerRequestCache contract

This test specifically verifies that `NoOpServerRequestCache` neither saves nor restores requests. It complements HTTP tests; it **is not** an integration test proving the entire security chain or all session components are off.

**`src/test/java/demo/NoOpCacheContractTest.java`**

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.savedrequest.ServerRequestCache;
import org.springframework.web.server.ServerWebExchange;

import reactor.test.StepVerifier;

class NoOpCacheContractTest {

    @Test
    void noOpCacheDoesNotSaveOrReturnRequests() {
        ServerRequestCache cache = NoOpServerRequestCache.getInstance();

        ServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/private")
        );

        StepVerifier.create(cache.saveRequest(exchange))
                .verifyComplete();

        StepVerifier.create(cache.getRedirectUri(exchange))
                .verifyComplete();

        StepVerifier.create(cache.removeMatchingRequest(exchange))
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

With the code and dependencies shown, the test is expected to **PASS**. `verifyComplete()` on publishers returning `Mono<URI>` or `Mono<ServerHttpRequest>` confirms completion **without `onNext`**: meaning no saved URI/request exists. It also confirms `saveRequest` completes without error.

This is a small test that hits the exact NoOp contract. When you want to prove **the security chain actually uses that instance**, add an integration test with initialized Spring Security configuration, or inspect bean configuration and real requests in the target runtime environment. The test above instantiates NoOp directly and does not itself verify the security chain selected it.

## 9. Configuring an API using JWT Bearer tokens

In an API using OAuth2 Resource Server, the typical configuration direction is:

~~~java
// Illustrative snippet to place inside a SecurityWebFilterChain bean.
// Requires valid issuer/JWK configuration for the system receiving tokens.
return http
        .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated()
        )
        .requestCache(cache ->
                cache.requestCache(NoOpServerRequestCache.getInstance()))
        .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
        .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
~~~

**This snippet is a configuration variant, not a standalone program.** The application needs the Resource Server dependency, real JWT verification config (e.g., matching issuer/JWK), validation of issuer/audience/signature/expiration, scope/authority mapping, and an approved error policy. Never treat an arbitrary Bearer token as valid merely because the request cache was disabled.

Client call format:

~~~bash
curl -i \
  -H "Authorization: Bearer <valid-access-token>" \
  http://localhost:8080/api/private
~~~

The command above is a **syntax template**, requiring a real token issued by a valid identity provider; it cannot succeed with the placeholder string alone. In practice, avoid logging tokens into terminal history in shared or sensitive environments. Tokens must be verified on **every request**; if missing or invalid, protected endpoints must reject the request, typically with 401.

### 9.1. Should sessions always be disabled when using JWT?

If an API is truly standalone without login forms or cookie authentication, no-op request cache and no-op security context repository are two helpful configuration steps. Still, a comprehensive statelessness assessment requires checking:
- Does any filter or controller call `exchange.getSession()` and write data?
- Does the CSRF token repository use `WebSession` or cookies?
- Do OAuth2 Login or browser authorize/redirect steps need state storage?
- Does the system use Spring Session or another persistence mechanism?
- Does any component outside Spring Security create a session for its own needs?

**A no-op request cache does not automatically prove "zero cookies, zero WebSession".** Nor does it disable CSRF tokens, logout, CORS, authentication entry points, HTTP response caching, or cookie creation by other parts.

## 10. When NOT to use NoOpServerRequestCache

A website with a login form usually wants users to return to the page they were opening before logging in. Configuring no-op can **break returning to the previous page**. For example:

~~~text
GET /checkout  --> unauthenticated --> login
Login succeeds
    |
    +--> With saved request: can return to /checkout
    |
    +--> NoOp: no saved request to retrieve the URL
                    --> uses default URL or other navigation logic
~~~

Do not apply no-op unconditionally across a whole system that has both an API and an interactive web login.

A clean design uses **multiple `SecurityWebFilterChain` beans** with `securityMatcher` and `@Order` whenever different routes need different policies:
- Chain for `/api/**`: Bearer/Basic per API contract, no-op request cache.
- Chain for website: form/OAuth2 login and saved requests if the UX requires returning to the pre-login page.

Specify matchers accurately; Spring Security selects matching chains in order. A "match-all" chain placed too early can swallow API requests and prevent the intended chain's no-op configuration from taking effect. Never assume a bean applies to all routes just because it exists.

## 11. Common mistakes

### Mistake 1: Using NoOpServerRequestCache and claiming "the API is completely stateless"

**Why it is wrong?** The request cache only manages saved requests. The authentication repository, CSRF token repository, OAuth2 login, `WebSession` from other code, or other filters can still hold state.

**Right approach:** identify every component reading/writing sessions across the entire API. For cross-request authentication, look at `NoOpServerSecurityContextRepository` and remove unused cookie login mechanisms. Verify behavior through a sequence of fresh HTTP requests.

### Mistake 2: Using NoOpServerSecurityContextRepository while letting request cache store sessions

The two repositories/strategies are independent. You could stop retaining authenticated users across requests while still saving pre-login URLs via another request cache. For a stateless API, review **both**.

### Mistake 3: Thinking request cache caches response data

`NoOpServerRequestCache` does not turn off Spring Security's `Cache-Control`, clear Redis caches, or forbid CDNs from caching responses. `Cache-Control`/security headers must be configured, tested, and designed around actual data sensitivity.

### Mistake 4: Thinking NoOp forces every tokenless request to return 401

Statuses like 401, 302, or 403 depend on the authentication entry point, authorization, routing, and active mechanisms. The no-op cache only decides **not to keep saved requests**. An app can still redirect to login if form login is enabled.

### Mistake 5: Using Servlet APIs for WebFlux

Do not use Servlet's `NullRequestCache`, `HttpSecurity`, or `HttpSessionRequestCache` to configure request caching on a `SecurityWebFilterChain`. In WebFlux, use `ServerHttpSecurity` and `ServerRequestCache`.

### Mistake 6: Disabling CSRF by reflex

"REST API" does not automatically mean "no CSRF needed". If browsers automatically send credentials such as cookies/sessions or HTTP Basic, state-changing operations may require CSRF protection. Only disable CSRF after inspecting **how credentials are sent** and the threat model, especially with browsers.

### Mistake 7: Testing only authenticated requests and inferring no-op request cache

Requests with valid credentials can return 200 under many different request cache setups. Test the no-op contract directly or inspect saved-request/redirect behavior in context; never use a single 200 status as proof.

### Mistake 8: Confusing client state with server state

An SPA may remember the pre-login route in browser storage or router state. That does not mean server-side Spring Security saved the request. In a stateless API, having the client manage its own UI flow is normal.

### Mistake 9: Writing a custom WebFilter to clear sessions on every request

There is no need to add a filter that manipulates sessions arbitrarily when proper configuration strategies exist. An arbitrary "clear session" filter can break browser flows and fails to address the source creating state. Configure the request cache, security-context repository, authentication mechanisms, and specific session consumers properly.

## 12. Checklist for auditing a real API

Follow this practical checklist in order:

1. **Identify client types:** browsers with login forms or API callers sending tokens on each request?
2. **Identify the security chain:** which `SecurityWebFilterChain` bean matches this route and what is the matcher order?
3. **Check request cache:** does the chain intentionally configure `NoOpServerRequestCache` or disable request caching?
4. **Check SecurityContext repository:** does it save/load authentication from `WebSession`?
5. **Check authentication:** HTTP Basic, Bearer JWT, or cookies? What must every request carry?
6. **Check entry point:** do unauthenticated requests return an API 401 or an HTML redirect?
7. **Check other session components:** CSRF, OAuth2 login, `exchange.getSession()`, Spring Session, business code.
8. **Test independent HTTP calls:** send a request without credentials, one with credentials, then a new request without credentials; compare statuses.
9. **Test no-op directly:** `saveRequest` completes, `getRedirectUri` and `removeMatchingRequest` emit no values.
10. **Test real authorization:** valid users lacking required authorities must be rejected per policy; check resource ownership in services if applicable.

### 12.1. Distinguishing symptoms from causes

| Observation | Valid conclusion | Invalid conclusion |
| --- | --- | --- |
| Missing token → 401 | Authentication entry point is rejecting the request | Does not yet prove no-op request cache |
| Request with token → 200 | Token/credentials were likely accepted | Does not prove no session was saved |
| Subsequent request without credentials → 401 | No authentication was reused for that request | Does not prove no cookies were created elsewhere |
| NoOp test returns empty publishers | NoOp neither saves nor returns requests per contract | Does not prove every chain uses that instance |
| Response contains `Set-Cookie` | Some component is creating a cookie | Cannot immediately blame the request cache |
| Response contains `Cache-Control` | An HTTP caching/header policy is active | Unrelated directly to saved-request cache |

### 12.2. Notes on performance and reliability

The no-op cache avoids saving requests because no saved-request flow is needed; it **does not** speed up JWT validation, reduce database queries, or replace rate limiting. The system must still bound resources for token decoding/validation, authorization, and business data.

If migrating from session login to Bearer tokens, changing the request cache is only one piece. Review client migration, logout/revocation, expiration, clock skew, key rotation, object-level access permissions, and error handling. Never claim "stateless means zero security risk".

## 13. Self-check questions

1. A user opens `/checkout` and is redirected to login. In this flow, what is a saved request used for?
2. When using `NoOpServerRequestCache`, what is the result of `getRedirectUri(exchange)` after `saveRequest(exchange)`? Why?
3. Why does `NoOpServerRequestCache` differ from `NoOpServerSecurityContextRepository`?
4. Can a JWT API still create a `WebSession` after configuring a no-op request cache? Which components need further checking?
5. Why is a `401 Unauthorized` response insufficient to prove `NoOpServerRequestCache` is active?
6. When does `NoOpServerRequestCache` degrade a website user's experience?
7. Why shouldn't you disable CSRF merely because `NoOpServerRequestCache` is configured?
8. With multiple `SecurityWebFilterChain` beans, why do matchers and `@Order` affect whether the no-op configuration applies?

**Suggested answers:**
- (1) To allow returning to the pre-login URL.
- (2) `Mono.empty()`: no saved URI exists.
- (3) One prevents saved requests, while the other prevents saving/loading `SecurityContext` across requests via the repository.
- (4) Yes; check CSRF, OAuth2 login, `WebSession` from controllers/filters, or other mechanisms.
- (5) Status is decided by the authentication entry point; no-op only controls saved requests.
- (6) When a website needs to return users to the pre-login page.
- (7) CSRF depends on how browsers send credentials and state-changing endpoints.
- (8) Only the chain that actually matches the request governs that request.

## 14. Summary

**`NoOpServerRequestCache` for Spring Security WebFlux disables saving and restoring pre-authentication requests.** In a sessionless API, the client is responsible for re-sending requests with valid credentials, so the server has no need to remember URLs for post-login redirects.

For a sound stateless architecture, clearly separate:
- Saved-request state → `ServerRequestCache` / `NoOpServerRequestCache`.
- Authentication persistence → `ServerSecurityContextRepository` / `NoOpServerSecurityContextRepository`.
- Identity within the **current request** → authentication filters and `ReactiveSecurityContextHolder`.
- State created by browsers, CSRF, OAuth2 Login, `WebSession` consumers, or other subsystems → configure and test separately.

Choose no-op based on the **API contract**, keep security chains easy to verify, and never infer "no sessions exist" from a single configuration line.

### Official references

- Spring Security Javadoc — `NoOpServerRequestCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/savedrequest/NoOpServerRequestCache.html
- Spring Security Javadoc — `ServerRequestCache`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/savedrequest/ServerRequestCache.html
- Spring Security Javadoc — `ServerHttpSecurity.RequestCacheSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.RequestCacheSpec.html
- Spring Security Javadoc — `NoOpServerSecurityContextRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html
- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html