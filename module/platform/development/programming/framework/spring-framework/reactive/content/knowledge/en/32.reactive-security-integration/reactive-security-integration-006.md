# CSRF, Sessions, and Choosing Based on Actual Authentication in Spring WebFlux

## 1. The Most Important Question: How Does the Browser Send Credentials?

When building security for Spring WebFlux, many people ask: "If the app uses JWT, can I disable CSRF?" or "If it uses sessions, must CSRF always be enabled?". That framing is not precise enough.

**Cross-Site Request Forgery (CSRF) risk depends primarily on whether the browser automatically attaches credentials to a request initiated by another website.** What kind of data is used as the credential (session ID, JWT, opaque token) is only part of the answer.

Three scenarios:

1. **Form login + session cookie:** the browser automatically sends cookies for the target domain. A malicious page can try to trigger a state-changing request carrying the user's cookie. CSRF protection is required.
2. **An API accepting only `Authorization: Bearer` where the client explicitly attaches the token:** an ordinary cross-site form cannot obtain the token and attach the user's `Authorization` header. If the API truly does not accept ambient credentials like cookies, CSRF can be disabled for that specific API surface while still enforcing token validation, authorization, CORS, and XSS protection.
3. **JWT or bearer token stored in a cookie:** the browser still automatically sends the cookie. Labels like "JWT" or "stateless" do not eliminate CSRF; corresponding protection is still required.

Spring Security for WebFlux enables CSRF protection by default. Disabling it must be based on **the actual authentication flow of each endpoint group**, not on a technology buzzword.

## 2. What Is CSRF? A Concrete Scenario

Suppose a user logs into `bank.example` and the browser stores a session cookie:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; HttpOnly; Secure; SameSite=Lax; Path=/
~~~

The bank page exposes:

~~~http
POST /transfer HTTP/1.1
Host: bank.example
Cookie: SESSION=<opaque-session-id>
Content-Type: application/x-www-form-urlencoded

to=attacker&amount=1000
~~~

If the endpoint only checks the session cookie without requiring proof that the request originated from a legitimate UI flow, another website can trick the browser into sending a similar request. The browser attaches cookies automatically per cookie rules; the malicious site does not even need to know the cookie value.

In the synchronizer token CSRF defense model:

1. The server generates an unpredictable secret token bound to the session/security context.
2. The legitimate UI obtains the token via a form/meta tag or a protected same-origin endpoint.
3. When issuing `POST`, `PUT`, `PATCH`, or `DELETE`, the client includes the token in a **form parameter** or **HTTP header**.
4. Browsers **do not automatically attach** CSRF headers/parameters the way they attach cookies.
5. The server compares the received token against the expected token; missing or mismatched tokens are rejected.

Example of a valid `POST`:

~~~http
POST /transfer HTTP/1.1
Host: bank.example
Cookie: SESSION=<opaque-session-id>
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token>

{"to":"friend","amount":100}
~~~

The cookie and the CSRF token serve different roles: the cookie proves the user's session; the CSRF token proves the request came from an interactive flow authorized to access that token.

CSRF is not primarily a "data-reading theft" bug. An attacker might not be able to read the HTTP response due to the same-origin policy, yet can still alter state if the server accepts forged requests. CORS is not a complete substitute for CSRF.

## 3. Same-Origin Policy, CORS, SameSite, and CSRF Differ

| Mechanism | Primary Goal | Replaces CSRF Token? |
| --- | --- | --- |
| Same-Origin Policy | Restricts JavaScript on another origin from reading target origin responses/data | No |
| CORS | Controls when browsers allow cross-origin JavaScript access and certain preflighted requests | No |
| `SameSite` cookie | Restricts sending cookies in cross-site contexts | An additional defense layer, should not be the sole defense |
| `HttpOnly` cookie | Prevents JavaScript from reading cookie values directly | No; browsers can still send cookies automatically |
| `Secure` cookie | Sends cookies only over HTTPS connections | No |
| CSRF token | Requires proof that browsers do not attach automatically to requests | Direct defense |
| XSS protection | Prevents malicious scripts from executing inside the app's origin | Needed separately; XSS can defeat multiple layers |

Important notes:

- CORS blocks reading responses or blocks certain preflighted cross-origin requests, but **HTML forms** and simple requests can still be sent in certain situations.
- `Content-Type: application/json` is not a sufficiently reliable anti-CSRF policy for every endpoint or proxy.
- `SameSite=Lax` generally allows cookies on certain top-level navigations using safe methods. Never perform side effects via `GET`.
- `SameSite=None` generally requires `Secure`; `SameSite=Strict` restricts more cross-site navigations but may affect UX.
- A same-origin XSS vulnerability can read a CSRF token exposed to JavaScript and forge valid requests. CSRF defense does not replace CSP, output encoding, and XSS prevention.

## 4. `WebSession` in Spring WebFlux

### 4.1. `WebSession` Is Not `HttpSession`

Servlet/Spring MVC applications typically use `HttpSession`. Reactive Spring WebFlux applications use the **`WebSession`** abstraction and `WebSessionManager`.

A `WebSession` can hold server-side state, such as:

- `SecurityContext` after form login.
- The expected CSRF token when using `WebSessionServerCsrfTokenRepository`.
- OAuth2 authorization requests or flow state depending on configuration.
- Intentional application data.

The browser usually holds only a **session identifier** in a cookie. The cookie does not inherently contain the entire user profile or `SecurityContext`; the server uses the ID to look up session state.

Do not confuse "having a session cookie" with "`WebSession` stores everything". Also do not confuse "API uses bearer tokens" with "definitely no `WebSession`": another component can still create a session if the configuration allows it.

### 4.2. Security Context Repository

Reactive Spring Security provides `ServerSecurityContextRepository` implementations:

- **`WebSessionServerSecurityContextRepository`:** stores/loads `SecurityContext` via `WebSession`, suited for interactive login when preserving login state across requests.
- **`NoOpServerSecurityContextRepository`:** does not persist `SecurityContext` via that repository; commonly used for independently authenticated requests like stateless bearer APIs.

`NoOpServerSecurityContextRepository` **does not** by itself guarantee the entire application never creates a `WebSession`. It only governs how that security context repository handles context. You must also inspect form login, OAuth2 flows, session managers, and application code.

### 4.3. Session Fixation, Timeouts, and Distributed Storage

For browser login:

- Generate/rotate the session identifier appropriately after authentication to mitigate session fixation risks; evaluate the session fixation protection provided by the framework.
- Protect session cookies with `Secure` and `HttpOnly`, and set `SameSite` appropriately.
- Enforce session timeouts; support logout and proper session invalidation.
- When running multiple application instances, consider Spring Session + Redis or a shared session store when shared state is truly needed.
- Never keep sessions indefinitely or store unnecessarily large/sensitive data in sessions.
- In a multi-node cluster, the cookie is an identifier; the session store must provide appropriate consistency.

A single system can simultaneously use `WebSession` for a web UI and stateless bearer auth for APIs, provided filter chains and credential policies are clearly separated.

## 5. CSRF in Spring Security WebFlux

### 5.1. Defaults

In Spring Security for WebFlux, CSRF protection is enabled by default. Spring Security uses:

- **`CsrfWebFilter`** to protect applicable requests.
- **`WebSessionServerCsrfTokenRepository`** by default to store the expected token in `WebSession`.
- **`ServerCsrfTokenRequestHandler`** to expose the token to requests and parse submitted tokens.
- Since Spring Security 6, **`XorServerCsrfTokenRequestAttributeHandler`** is used by default, adding masking to mitigate BREACH risks when tokens are rendered into responses.

There is no need to add a manual CSRF filter when using Spring Security properly.

"Safe" methods such as `GET`, `HEAD`, `TRACE`, and `OPTIONS` are treated as read-only under the default CSRF model. State-changing methods such as `POST`, `PUT`, `PATCH`, and `DELETE` must submit a token when CSRF is enabled on the chain.

**Important:** this is foundational for HTTP API design. Never update data, delete accounts, or log out via `GET` while relying on "CSRF only applies to POST".

### 5.2. `WebSession` Repository

This can be configured explicitly:

~~~java
@Bean
SecurityWebFilterChain webChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/login", "/error").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf.csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository()))
            .build();
}
~~~

This snippet illustrates a single chain; in a multi-chain app, add matchers and `@Order`. `WebSessionServerCsrfTokenRepository` fits interactive browser login where the server maintains session state.

### 5.3. Providing the Token to HTML Forms

A valid `POST` form needs a hidden field:

~~~html
<form action="/web/preferences" method="post">
  <input type="hidden" name="_csrf" value="token-from-server">
  <input type="text" name="theme" value="dark">
  <button type="submit">Save</button>
</form>
~~~

In Thymeleaf applications integrated with Spring Security, the token can be injected into forms automatically when view templates are configured properly. The HTML above only illustrates the structure; never hardcode tokens.

### 5.4. Providing the Token for JavaScript `fetch`

`CsrfWebFilter` places a **`Mono<CsrfToken>`** into a `ServerWebExchange` attribute named `CsrfToken.class.getName()`. A controller can explicitly return the token to authenticated clients:

~~~java
@GetMapping("/web/csrf")
Mono<CsrfView> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(new IllegalStateException(
                "CSRF token unavailable"));
    }

    return token.map(value -> new CsrfView(
            value.getHeaderName(), value.getToken()));
}
~~~

This is a controller snippet where `CsrfView` is an application-defined record. The controller only returns the token for requests passing through the CSRF-protected chain and satisfying authentication/authorization.

A same-origin browser client sends:

~~~javascript
async function saveTheme(theme) {
  const csrfResponse = await fetch("/web/csrf", {
    credentials: "same-origin"
  });

  if (!csrfResponse.ok) {
    throw new Error("Unable to obtain CSRF token");
  }

  const csrf = await csrfResponse.json();

  const response = await fetch("/web/preferences", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ theme })
  });

  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.json();
}
~~~

After login/logout or session changes, old tokens may no longer be valid; the client must fetch a new token as required by the flow. Never cache token responses publicly, never log tokens, and never let untrusted origins read this endpoint.

### 5.5. `CookieServerCsrfTokenRepository` for SPAs

If a JavaScript framework needs to read the CSRF token from a cookie, Spring Security provides `CookieServerCsrfTokenRepository`:

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

By default this repository uses the **`XSRF-TOKEN`** cookie, the **`X-XSRF-TOKEN`** header, or the `_csrf` parameter.

`withHttpOnlyFalse()` lets JavaScript read the cookie. Use it only if the frontend genuinely needs to read the cookie from JavaScript; otherwise keep cookies `HttpOnly`. Configure `Secure`, `SameSite`, `path`, `domain`, and CORS appropriately for your deployment.

**Spring Security 6+ note:** CSRF token masking/XOR may require configuring an appropriate `ServerCsrfTokenRequestHandler` if an SPA reads the **raw token** from a cookie and sends it back directly in a header. Do not assume changing only the repository works across every version/configuration. Do not disable BREACH protection arbitrarily; follow the official SPA CSRF guidance and test real requests.

### 5.6. Never Use a CSRF Cookie as a Credential

A CSRF token is not an access token, not a session ID, and does not authenticate users. An unauthenticated request must never be accepted merely because it carries a valid CSRF token.

A cookie holding a CSRF token is automatically sent by the browser; therefore, **checking only that the cookie exists** does not protect against CSRF. The token must be submitted via a channel an attacker cannot make the browser attach automatically—such as a header or form parameter—and verified by the server.

## 6. When Can CSRF Be Disabled?

### 6.1. Truly Bearer-Only APIs

For example, a service that accepts only:

~~~http
POST /api/commands HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{"action":"sync"}
~~~

Browsers do not automatically attach an application's Bearer token in the `Authorization` header on requests initiated by another website. Therefore, if an API:

- Accepts only explicit `Authorization: Bearer` headers.
- Does not use cookies or ambient HTTP Basic credentials to authenticate the same endpoints.
- Does not fall back to session login when a bearer token is absent.
- Verifies JWT signature/issuer/audience/expiry or introspects opaque tokens.
- Enforces authorization and XSS protection.
- Applies intentional CORS and credential policies.

then disabling CSRF **for that API group only** is generally reasonable.

There is no need to send a CSRF token on every bearer-only API call. Doing so does not make a bearer API "less secure": CSRF tokens prevent one specific class of attack and do not replace authentication.

### 6.2. JWTs in Cookies Still Suffer from CSRF

If a JWT is placed inside an `HttpOnly` cookie and the server reads that cookie to authenticate requests, the browser still sends the cookie automatically. Using JWT does not remove CSRF risk.

A BFF (Backend for Frontend) using session cookies or `HttpOnly` cookies to hold credentials for browsers also requires CSRF evaluation, even though the BFF's backend calls downstream APIs with bearer tokens. Browser → BFF and BFF → API are two separate security boundaries.

### 6.3. HTTP Basic in Browsers

HTTP Basic uses the `Authorization` header, yet browsers can cache credentials and resend them automatically under certain conditions. Therefore, do not automatically conclude browser-facing HTTP Basic is immune to CSRF.

For service-to-service Basic where code explicitly attaches credentials, the risk profile differs; still, prefer OAuth2/mTLS when strong authorization is required. Never treat "any `Authorization` header is immune to CSRF" as an absolute rule.

### 6.4. CORS Does Not Replace CSRF

CORS controls whether JavaScript from another origin can read responses and governs preflight checks, not whether every state change was intentionally initiated by the user.

Browsers can submit cross-site form `POST`s under certain conditions even when JavaScript cannot read the response. Rejecting preflights is not enough to protect endpoints accepting "simple" requests. Even if an API only returns JSON, verify authentication flows, content negotiation, and all accepted request types.

### 6.5. `SameSite` Is Defense-in-Depth

For session cookies, configure `SameSite` (`Lax`/`Strict`/`None` per use case), `Secure`, `HttpOnly`, and session expiry. `SameSite` helps curb cross-site cookie transmission, but should not be the sole reason to disable CSRF for flows with ambient credentials.

Factors like same-site subdomains, embedded iframes, OAuth login redirects, browser compatibility, and allowed HTTP methods can alter `SameSite`'s effectiveness.

## 7. Decision Matrix Based on Actual Authentication

| Architecture | How Are Credentials Sent? | CSRF for Unsafe Methods | Notes |
| --- | --- | --- | --- |
| Web app form login + `WebSession` cookie | Browser automatically sends cookie | Enabled | Default `WebSessionServerCsrfTokenRepository` |
| OAuth2 Login/OIDC browser web app | Browser typically holds login session in cookie | Enabled for post-login actions | OAuth2 `state`/`nonce` do not replace CSRF on business `POST`s |
| SPA calling BFF via session cookie | Browser automatically sends cookie | Enabled | Send token via form/header, strict CORS |
| Dedicated `Authorization: Bearer` API | JS/app explicitly sets token header | Can disable on API chain | No fallback to cookies/Basic; verify bearer |
| JWT stored in `HttpOnly` cookie | Browser automatically sends JWT cookie | Enabled | Stateless JWT does not mean CSRF-safe |
| REST API accepting both cookies and Bearer | At least one ambient credential exists | Enabled or split endpoints/chains | Avoid disabling globally just because Bearer exists |
| HTTP Basic used by browsers | Browser may auto-send cached credentials | Evaluate/prefer keeping protection | Do not infer safety from header name |
| Public webhook signed with HMAC | Service sends code-generated signature | Usually no CSRF needed | Use signature, timestamp, replay protection |
| Browser WebSocket with cookie auth | Cookie may travel on handshake | HTTP CSRF filter is insufficient post-upgrade | Check `Origin`, auth, and per-message permissions |
| SSE using cookies to stream events | Browser auto-sends cookie on `GET` | `GET` must stay read-only, check CORS/auth | State-changing operations still need protection |

Rule: **Start from the actual credentials, determine whether the browser attaches them automatically, and only then decide the CSRF policy for each endpoint group.**

## 8. Splitting Multiple `SecurityWebFilterChain`s in WebFlux

### 8.1. Why Split?

An application may contain:

- `/web/**`: browser UI authenticated via form login, storing `SecurityContext` in `WebSession`, with CSRF.
- `/api/**`: machine/API clients sending `Authorization: Bearer`, rejecting sessions, without CSRF.
- `/login`: form login for browsers.

Spring Security WebFlux allows registering multiple `SecurityWebFilterChain` beans; each request selects a chain via `securityMatcher` and `@Order`. Specialized chains must precede catch-all chains.

Never write a single chain covering both styles and call `.csrf(disable)` just to keep the bearer API from getting 403. Doing so disables protection for browser session endpoints.

### 8.2. Bearer Chain and Session Chain

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance())
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.POST, "/api/commands")
                    .hasAuthority("SCOPE_write")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain webChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/login", "/error").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(csrf -> csrf.csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository()))
            .build();
}
~~~

These are two methods inside the same `@Configuration`; imports and authentication beans are shown in the runnable project below.

Every API request must carry a verified Bearer token; web session cookies are not a fallback authentication mechanism on `/api/**`. The web chain keeps CSRF enabled for browser login.

### 8.3. Difference Between `securityMatcher` and `pathMatchers`

- `securityMatcher` selects **whether the entire `SecurityWebFilterChain`** applies to the request.
- `authorizeExchange().pathMatchers` decides **permissions** inside the already selected chain.

If you only configure `permitAll` or `authenticated` with `pathMatchers` inside one chain while disabling CSRF at the chain level, the CSRF setting still applies to that entire chain's scope. Therefore, separating `securityMatcher` cleanly is essential.

### 8.4. `NoOpSecurityContext` Is Not a CSRF Policy

`NoOpServerSecurityContextRepository` neither saves nor loads `SecurityContext`. It does not replace the CSRF filter and does not guarantee requests will never create a `WebSession`.

In a bearer-only API, the goal is avoiding session-based authentication and credential fallback. When applying a no-op repository, also verify whether other filters/handlers create sessions.

## 9. Runnable Demo: Java 17+ / Spring Boot 3.5.16

The example demonstrates two security boundaries inside **the same WebFlux application**:

1. `/web/**` uses form login + `WebSession` with mandatory CSRF on `POST`.
2. `/api/**` uses only Bearer tokens via the `Authorization` header; CSRF is disabled for this chain.
3. The demo bearer token is only valid when running under the `"demo"` profile; never use a static introspector in production.
4. Tests use `WebTestClient` + `spring-security-test` to simulate users and CSRF, while also sending real Bearer requests through the resource server chain.

The project uses the opaque token introspection interface to keep the example offline without needing an Identity Provider when running tests. In production, replace the demo token verifier with an Authorization Server introspection endpoint or standard JWT validation.

### 9.1. Directory Structure

~~~text
webflux-csrf-session-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/security/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── BrowserController.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/example/security/
        └── SecurityIntegrationTest.java
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-csrf-session-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
~~~

### 9.3. `DemoApplication.java`

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.4. `SecurityConfig.java`

~~~java
package example.security;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.POST, "/api/commands")
                        .hasAuthority("SCOPE_write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/error").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .csrf(csrf -> csrf.csrfTokenRepository(
                        new WebSessionServerCsrfTokenRepository()))
                .build();
    }

    // For demo purposes only; do not use these passwords or in-memory users in production.
    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails demo = User.withUsername("student")
                .password("{noop}demo-pass")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(demo);
    }

    // Only active when the demo profile is enabled. DO NOT deploy the demo profile.
    @Bean
    @Profile("demo")
    ReactiveOpaqueTokenIntrospector demoTokenIntrospector() {
        return token -> {
            if (!"demo-token".equals(token)) {
                return Mono.error(
                        new BadOpaqueTokenException("Invalid demo token"));
            }

            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                    "demo-service",
                    Map.of("sub", "demo-service"),
                    List.of(new SimpleGrantedAuthority("SCOPE_write"))));
        };
    }
}
~~~

**Analysis:**

- `@Order(1)` ensures the `/api/**` chain is evaluated first.
- The API chain disables form login and HTTP Basic, accepting only OAuth2 Resource Server opaque bearer tokens.
- `NoOpServerSecurityContextRepository` avoids saving/loading `SecurityContext` via a session repository for APIs.
- `.csrf(disable)` applies solely to that API chain.
- `webChain` protects all remaining paths with form login and `WebSessionServerCsrfTokenRepository`.
- The `{noop}` password encoder and `demo-token` are test fixtures, **not acceptable security mechanisms for production**.
- If running neither the `demo` profile nor a valid production OAuth2 introspection config, the application must be configured further for the resource server; never accept unverified tokens automatically.

### 9.5. `BrowserController.java`

~~~java
package example.security;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class BrowserController {

    public record PreferenceRequest(String theme) {
    }

    public record SavedPreference(boolean saved, String theme) {
    }

    public record CsrfView(String headerName, String token) {
    }

    @GetMapping("/web/ping")
    public Mono<String> ping() {
        return Mono.just("web-session-ok");
    }

    @GetMapping("/web/csrf")
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
                exchange.getAttribute(CsrfToken.class.getName());

        if (csrf == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token unavailable"));
        }

        return csrf.map(token -> new CsrfView(
                token.getHeaderName(), token.getToken()));
    }

    @PostMapping(
            path = "/web/preferences",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<SavedPreference> save(
            @RequestBody PreferenceRequest request) {
        return Mono.just(new SavedPreference(true, request.theme()));
    }
}
~~~

`/web/csrf` is a token-reading endpoint for logged-in browser apps. In a real application, ensure tokens are never cached publicly or logged, and rotate CSRF tokens when login sessions change.

### 9.6. `ApiController.java`

~~~java
package example.security;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record CommandRequest(String action) {
    }

    public record CommandResult(boolean accepted, String action) {
    }

    @PostMapping(
            path = "/api/commands",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<CommandResult> command(
            @RequestBody CommandRequest request) {
        return Mono.just(new CommandResult(true, request.action()));
    }
}
~~~

The API does not read session cookies. The `SCOPE_write` authority is checked in the resource server security chain before the controller receives the request.

### 9.7. `application.yml`

~~~yaml
spring:
  application:
    name: webflux-csrf-session-demo
  webflux:
    base-path: ""
~~~

The `demo` profile is not active by default. To run the learning environment, explicitly activate the `demo` profile. This prevents accidentally enabling the `"demo-token"` verifier in unauthorized environments.

### 9.8. `SecurityIntegrationTest.java`

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
@ActiveProfiles("demo")
class SecurityIntegrationTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void webPostWithoutCsrfIsForbiddenEvenWhenAuthenticated() {
        client.mutateWith(mockUser("student"))
                .post()
                .uri("/web/preferences")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new BrowserController.PreferenceRequest("dark"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void webPostWithCsrfIsAccepted() {
        client.mutateWith(mockUser("student"))
                .mutateWith(csrf())
                .post()
                .uri("/web/preferences")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new BrowserController.PreferenceRequest("dark"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.saved").isEqualTo(true)
                .jsonPath("$.theme").isEqualTo("dark");
    }

    @Test
    void authenticatedGetDoesNotRequireCsrf() {
        client.mutateWith(mockUser("student"))
                .get()
                .uri("/web/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("web-session-ok");
    }

    @Test
    void csrfEndpointExposesTokenForSameOriginClient() {
        client.mutateWith(mockUser("student"))
                .get()
                .uri("/web/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.headerName").isEqualTo("X-CSRF-TOKEN")
                .jsonPath("$.token").isNotEmpty();
    }

    @Test
    void bearerApiRequiresAuthentication() {
        client.post()
                .uri("/api/commands")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CommandRequest("sync"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void bearerApiPostSucceedsWithoutCsrfForValidBearer() {
        client.post()
                .uri("/api/commands")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-token")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CommandRequest("sync"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.accepted").isEqualTo(true)
                .jsonPath("$.action").isEqualTo("sync");
    }

    @Test
    void bearerApiRejectsInvalidToken() {
        client.post()
                .uri("/api/commands")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CommandRequest("sync"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

`WebTestClient` is bound to `ApplicationContext` with `apply(springSecurity())` so `mockUser()` and `csrf()` can be used. `mockUser` tests verify authorization + CSRF behavior of the chain, and are **not** full integration tests of browser session cookies after form login. Bearer requests pass through the resource-server filter with the demo introspector. Do not infer from these tests that production token verification is secure.

### 9.9. Running Tests and the Application

In the directory containing `pom.xml`:

~~~bash
mvn test
~~~

To launch the demo with the static-token profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=demo
~~~

Call the bearer API (use this token only in demo environments):

~~~bash
curl -i -X POST http://localhost:8080/api/commands \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -d '{"action":"sync"}'
~~~

Example response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"accepted":true,"action":"sync"}
~~~

If the `Bearer` header is omitted, the API returns `401 Unauthorized`. If `/web/preferences` is called without a valid login session and CSRF token, the request is rejected. Browsers navigate to `/login` to use the Spring Security-generated form login.

To interact with a real browser session via JavaScript, log in through the form first, then call `/web/csrf` and send the received token in the header for `POST /web/preferences`.

### 9.10. Replacing the Demo Token Verifier with a Real System

Production must never retain the `demo` profile, `{noop}` user passwords, or a hardcoded introspector.

Example of an opaque token resource server calling Authorization Server introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example/introspect
          client-id: my-resource-server
          client-secret: from-secure-config
~~~

In production, `client-secret` must come from a secret manager or secure environment variable; never commit secrets to the repository. Without the demo `ReactiveOpaqueTokenIntrospector` bean, Spring Boot can auto-configure an introspector from these properties.

If using JWT, replace the `opaqueToken` configuration with `jwt()` and provide an appropriate `issuer-uri` or JWK Set URI. Validators must verify signature, issuer, audience, expiry, and required claims/authorities; never accept tokens merely because JSON can be decoded.

## 10. State and Sessions Across Login Styles

### 10.1. Form Login

With form login:

1. Browser `GET /login` to retrieve the form with a CSRF token.
2. Browser `POST`s username/password along with the CSRF token.
3. Spring Security authenticates; `SecurityContext` is stored per session configuration.
4. Browser sends the session cookie on subsequent requests.
5. Read-only `GET` requests normally do not need CSRF.
6. `POST`/`PUT`/`PATCH`/`DELETE` requests carrying the cookie must include a valid CSRF token.
7. Logout should be a CSRF-protected `POST`, not a state-changing `GET`.

Preventing login CSRF is also important: a forged login request could log a victim's browser into an attacker-controlled account. Spring Security protects `POST` login with CSRF under the proper configuration.

### 10.2. OAuth2 Login / OIDC

The OAuth2 Authorization Code flow uses a `state` parameter to protect the authorization callback, alongside PKCE and `nonce` depending on the flow. These mechanisms do not replace CSRF protection for business `POST`s after the user has logged in.

WebFlux OAuth2 Login typically manages session state across requests/sessions depending on config. When browsers hold login state via cookies, unsafe actions still require protection.

### 10.3. Stateless Bearer Resource Server

A resource server authenticates each request from a bearer token explicitly sent by the client. It does not need to save `SecurityContext` in `WebSession` to remember login. However:

- Expired, revoked, or wrong-audience tokens must still be rejected.
- Authorization based on scopes/roles/claims is still required.
- CORS must restrict which origins may access the API.
- If tokens live in JavaScript storage, XSS can steal them.
- An API supporting both bearer tokens and session fallback must be evaluated as a cookie-enabled endpoint, not assumed CSRF-safe.

### 10.4. Hybrid: BFF, SPA, and Backend API

A common architecture:

~~~text
Browser
  |
  | Cookie SESSION + CSRF header
  v
BFF / WebFlux app
  |
  | Authorization: Bearer explicit header
  v
Downstream Resource API
~~~

Browser → BFF requires CSRF because cookies are sent automatically. BFF → downstream API is not a form/browser ambient request; authenticate separately with Bearer and validate tokens properly. This boundary explains why one system can enable CSRF on its frontend-facing chain and disable it on its machine-facing chain without contradiction.

## 11. Distinguishing 401, 403, and CSRF Errors

| Scenario | Typical Result | Interpretation |
| --- | --- | --- |
| Bearer API with no token | `401 Unauthorized` | Not authenticated |
| Bearer API with invalid/expired token | `401 Unauthorized` | Authentication failed |
| Valid bearer token lacking required scope | `403 Forbidden` | Not authorized to perform action |
| Authenticated web session, `POST` missing/wrong CSRF | `403 Forbidden` | Rejected by CSRF protection |
| Web page not logged in | `302` to login or configured entry point behavior | Interactive authentication required |
| Expired session with stale CSRF token | May be `403` CSRF or login redirect depending on flow | Obtain fresh session/token per flow |

Do not build clients that rely solely on status `403` to conclude an error is definitely CSRF. `403` can also mean authorization denial. Inspect server exceptions/logs and the application's standardized error contract.

Never return CSRF tokens, credentials, cookies, or stack traces in error messages. Avoid logging full HTTP headers containing `Authorization`.

## 12. Which CSRF Token Repository to Choose?

| Repository | Token Storage | When Appropriate | Caveats |
| --- | --- | --- | --- |
| `WebSessionServerCsrfTokenRepository` | Expected token in `WebSession` | Server-rendered browser apps, form login, session-backed BFF | Maintains session state; requires proper session store/cookie policy |
| `CookieServerCsrfTokenRepository` | Token in cookie | SPAs reading token cookies and echoing in headers | `HttpOnly` false only when needed; masking/XOR handler, XSS/CORS |
| Custom `ServerCsrfTokenRepository` | Application-defined mechanism | Custom storage requirements | Must preserve verification semantics and lifecycle |

Unless there is a specific reason, prefer the default `WebSessionServerCsrfTokenRepository` for browser sessions. Do not pick the Cookie repository merely to "avoid sessions" when authentication still relies on cookies/sessions and no secure token-management plan exists.

Some SPAs use a double-submit cookie pattern. Do not mistakenly assume "having the token in a cookie" is enough; the server must validate the token presented in a header/parameter rather than treating the cookie alone as proof.

## 13. Cookie Policy, CORS, and Session Stores

### 13.1. Cookies

In production, verify:

- `Secure`: transmit cookies only over HTTPS.
- `HttpOnly`: prevent JavaScript from reading session cookies directly.
- `SameSite`: choose `Lax`/`Strict`/`None` matching OAuth redirects, iframes, and cross-site needs.
- `Path` and `Domain`: do not scope broader than necessary.
- Cookie name and session expiry.
- Session ID rotation/invalidation on login/logout per policy.
- Whether the reverse proxy forwards the HTTPS scheme properly so the app sets `Secure` cookies.

### 13.2. CORS

For cross-origin SPAs calling APIs with cookies:

- Allowlist exact origins, never wildcards with `allowCredentials`.
- Permit only truly needed methods/headers.
- Enforce HTTPS and explicit credential policies.
- Keep CSRF enabled if browsers auto-send cookies on unsafe operations.
- Never open the CSRF-token endpoint to arbitrary origins or public caches.

For Bearer APIs, CORS must still reflect only allowed frontends; "CSRF disabled" does not make wildcard CORS safe.

### 13.3. Sessions in Multi-Node Deployments

With the default `WebSession` across multiple instances, sessions are not automatically shared between nodes. For horizontal scaling without sticky-session dependence, you can use Spring Session with Redis. Secure Redis and session data, configure TTL and failover, and handle logout/session invalidation properly.

If the browser holds a session cookie on the BFF domain, do not unnecessarily share that session cookie across every microservice; constrain domain/path and trust boundaries.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "We use JWT, so disable CSRF" | JWTs in cookies are still auto-sent | Check whether credentials travel via cookies or explicit headers |
| "Stateless means no CSRF needed" | Stateless cookie authentication is still vulnerable to CSRF | Evaluate ambient credentials |
| Disabling CSRF app-wide because of one REST API | Form/session endpoints lose protection | Split `SecurityWebFilterChain` via `securityMatcher` |
| Letting `/api/**` fall back to session cookies | Cookies can authenticate API calls with CSRF off | Bearer-only chain with no session/Basic fallback |
| Thinking `NoOpServerSecurityContextRepository` disables all `WebSession`s | Other components can still create sessions | Audit the entire auth/session flow |
| Using HTTP Basic in browsers and blindly disabling CSRF | Browsers may auto-send cached Basic credentials | Treat as ambient auth where applicable |
| Thinking CORS replaces CSRF | Simple forms/requests can still trigger side effects | Require CSRF tokens on cookie-backed unsafe endpoints |
| Mutating data via `GET` | Bypasses unsafe-method protection | Use `POST`/`PUT`/`PATCH`/`DELETE` |
| Checking only the `XSRF-TOKEN` cookie | Browsers auto-send cookies | Require and verify token in header/parameter |
| SPA copies raw cookie token but forgets XOR handler | Valid-looking token may still get 403 | Configure SPA CSRF per version and test |
| Exposing CSRF tokens on public/cross-origin endpoints | Enables forged valid requests | Require auth + same-origin policy + no public caching |
| Logging `Authorization`, session cookies, or CSRF tokens | Leaks credentials | Redact/sanitize logs |
| Forgetting CSRF on login/logout | Login/logout CSRF | Protect `POST` login and logout |
| Relying on `SameSite` as the sole defense | Vulnerable configurations/flows remain | Combine CSRF tokens with layered defenses |
| Catch-all chain placed before API chain | API inherits unintended formLogin/CSRF policy | Set explicit `@Order` and `securityMatcher` |
| Failing to test missing/valid token cases | Vulnerabilities or production 403s | Test with `WebTestClient` + `spring-security-test` |
| Leaving demo introspector in production | Static tokens accepted for any request | Restrict to `demo` profile; use production IdP |
| Decoding JWTs without verification | Accepts forged tokens | Verify cryptographic signature, issuer, audience, `exp` |

## 15. Security Review Checklist

Before deciding to enable/disable CSRF for an endpoint or group of endpoints:

1. Is the client a browser, mobile app, or service-to-service caller?
2. Are credentials in a session cookie, JWT cookie, `Authorization` header, Basic auth, or mTLS?
3. Does the browser automatically attach credentials to cross-site requests?
4. Does the API ever accept session or cookie fallback?
5. Are unsafe HTTP methods used properly for all state changes?
6. Are chains selected via `securityMatcher` ordered properly?
7. Do the CSRF repository and request handler match how the frontend submits tokens?
8. Is the token fetched/read only by trusted origins without public caching or logging?
9. Do session cookies have `Secure`, `HttpOnly`, `SameSite`, and proper `Path`/`Domain`?
10. Does OAuth2 login have proper `state`/`nonce`/PKCE while still protecting business `POST`s?
11. Does the bearer resource server verify tokens, scopes, and authorization?
12. Is CSRF enabled for JWT-in-cookie APIs despite stateless tokens?
13. Does the SPA handle CSRF token rotation and session expiry?
14. Does CORS specify explicit trusted origins without overly broad credentials?
15. Do security integration tests cover 401, 403, `POST` missing token, and valid `POST`?
16. Are session fixation, logout, invalidation, and Redis/session stores tested for multi-instance setups?

## 16. Key Takeaways

- **CSRF does not depend simply on "JWT vs. Session".** It depends on whether the browser automatically attaches credentials.
- Form login, OAuth2 login, or BFFs using session cookies require CSRF protection on unsafe requests.
- Client-attached JWT/opaque bearer tokens in the `Authorization` header generally allow disabling CSRF on that specific bearer-only API chain.
- JWTs in cookies are still subject to CSRF. HTTP Basic in browsers can act as an ambient credential.
- WebFlux uses `WebSession` and `WebSessionServerCsrfTokenRepository`; Spring Security enables CSRF by default.
- `CsrfWebFilter` places `Mono<CsrfToken>` into `ServerWebExchange`; tokens can be rendered in forms or returned via a same-origin endpoint.
- Spring Security 6 uses `XorServerCsrfTokenRequestAttributeHandler` by default; SPA cookie tokens may need an appropriate request handler.
- `NoOpServerSecurityContextRepository` does not make the entire application completely stateless on its own.
- Multiple `SecurityWebFilterChain`s with `@Order` and `securityMatcher` keep session+CSRF for the web UI and bearer-only for `/api/**`.
- `SameSite`, `HttpOnly`, `Secure`, CORS, CSP, and XSS prevention are complementary defenses, not replacements for CSRF tokens when needed.
- Test cookie-backed `POST` without token (403), with token (2xx), bearer API without token (401), and with valid token (2xx).
- Disable CSRF only after confirming no automatic browser authentication remains on that endpoint scope.

**Official Documentation:**
- [Spring Security 6.5 — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — WebFlux Security, Multiple `SecurityWebFilterChain`s](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — CSRF Attack and Defense Mechanisms](https://docs.spring.io/spring-security/reference/6.5/features/exploits/csrf.html)
- [Spring Security 6.5 — Opaque Token Resource Server for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — `WebTestClient` Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Framework — `WebSession` and WebFlux Session Handling](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
