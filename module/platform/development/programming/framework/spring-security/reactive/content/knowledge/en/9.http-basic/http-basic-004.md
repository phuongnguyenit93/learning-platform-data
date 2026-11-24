# WWW-Authenticate, Authentication Realm, and Unauthenticated Responses

## 1. Goal and context

This lesson belongs to the **HTTP Basic** topic in **Spring Security reactive (WebFlux)**. After studying it, you can:

- Distinguish the `WWW-Authenticate` response header (server requesting authentication) from the `Authorization` request header (client sending credentials).
- Explain what a realm/protection space is, why it appears in a Basic challenge, and why a realm is **not** a role or authorization mechanism.
- Distinguish HTTP **401 Unauthorized**, **403 Forbidden**, and **407 Proxy Authentication Required**.
- Configure a realm with `HttpBasicServerAuthenticationEntryPoint` in `ServerHttpSecurity`, using the same entry point for both missing-credential and invalid-credential requests.
- Accurately test statuses/headers with `curl` and `WebTestClient`; recognize common pitfalls when returning JSON errors and when APIs are called from browsers.
- Understand the security limits of HTTP Basic: Base64 does not secure credentials, HTTPS is mandatory in real environments, and secrets must not leak into logs.

> **Use WebFlux/reactive APIs only.** `HttpBasicServerAuthenticationEntryPoint`/`ServerAuthenticationEntryPoint`/`ServerWebExchange` are not the same as Servlet MVC's `BasicAuthenticationEntryPoint`/`AuthenticationEntryPoint`/`HttpServletRequest`. A Servlet example may work in its own stack but must not be pasted verbatim into a WebFlux configuration.

## 2. Challenge–response mechanism of HTTP Basic

When a client requests a resource without valid authentication credentials, the origin server can ask the client to supply Basic credentials via an HTTP 401 response.

~~~text
Client                                            Spring Security WebFlux
  |                                                         |
  | GET /api/private                                        |
  | (no Authorization yet)                                  |
  |-------------------------------------------------------->|
  |                                                         |
  |                      authenticated() not satisfied      |
  |                                                         |
  |<--------------------------------------------------------|
  | HTTP/1.1 401 Unauthorized                               |
  | WWW-Authenticate: Basic realm="Learning API"            |
  |                                                         |
  | GET /api/private                                        |
  | Authorization: Basic <base64(username:password)>        |
  |-------------------------------------------------------->|
  |                                                         |
  |                   verify username/password              |
  |                   and authorization                     |
  |<--------------------------------------------------------|
  | HTTP/1.1 200 OK (if valid and permitted)                |
~~~

The diagram illustrates the protocol; not all clients wait for a 401. Many HTTP clients send `Authorization` on the very first request (preemptive authentication), such as `curl -u`. The server must still verify the submitted credentials.

The two headers are very different:

| Header | Direction | Responsibility | Example |
|---|---|---|---|
| `WWW-Authenticate` | Server → Client | Challenge: announces the authentication scheme and required parameters. | `WWW-Authenticate: Basic realm="Learning API"` |
| `Authorization` | Client → Server | Credentials per scheme for authentication. | `Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==` |

The Base64 string in the example is for `Aladdin:open sesame` from RFC 7617; it is not a credential in the Java demo. The `WWW-Authenticate` header itself **contains no password**, whereas `Authorization` may contain sensitive data and must not be logged verbatim.

### 2.1. What must not be inferred from the name "Unauthorized"

Although the status is named "401 Unauthorized", it primarily indicates that the resource **lacks valid authentication credentials**. If the client is validly authenticated but lacks access permission, the more accurate status is usually **403 Forbidden**. The two cases require different handling: 401 may cause the client to log in or change credentials, while 403 typically requires changing permissions or policies.

## 3. Basic challenge format per the RFC

Example showing only the relevant lines (not a complete HTTP response):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
~~~

Per **RFC 7617**:

- `Basic` is the authentication scheme name.
- `realm` is **required** in a Basic challenge; its value is enclosed in double quotes, e.g., `"Learning API"`.
- `charset` is an **optional** parameter whose defined value is `UTF-8`. Standard example: `WWW-Authenticate: Basic realm="Learning API", charset="UTF-8"`. Do not assume Spring Security emits `charset` by default without checking.
- Scheme and parameter names are matched case-insensitively; the realm value should be kept consistent.
- Basic credentials are formed from `username + ":" + password`, converted to bytes, and then Base64-encoded. The **first** `:` is the separator; usernames containing a colon are invalid in this format.
- Regarding non-ASCII username/password charsets, interoperability issues arise across clients without an encoding agreement. `charset="UTF-8"` in the challenge signals a preference to supporting clients, not "password encryption".

Example credential value defined in the RFC:

~~~http
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
~~~

That is the Base64 of `Aladdin:open sesame`. **Base64 is not encryption**; anyone reading the header can reverse it back to username/password. Do not send Basic over non-TLS HTTP in real environments. Enforce TLS/HTTPS on all hops carrying credentials, control proxies, and strictly avoid logging `Authorization`.

**RFC 9110, sections 11.6.1/15.5.2:** an origin server generating a **401 response must provide at least one `WWW-Authenticate` challenge applicable to the resource**. A custom error handler returning JSON with status 401 while omitting the challenge header can violate HTTP semantics and cause clients to misbehave.

## 4. How is a realm actually an "authentication space"?

A realm is a **server-chosen label** helping clients distinguish protection spaces. The realm name may appear in a browser when the user is prompted for a Basic username/password and helps the client decide whether credentials can be reused within the corresponding scope.

Example:

~~~text
https://api.example.test                   origin A
  /courses/**     -> Basic realm="Learning API"
  /reports/**     -> Basic realm="Reports"

https://admin.example.test                 origin B
  /**            -> Basic realm="Reports"
~~~

Even if realms on two origins share the name `Reports`, **two origins do not inherently share the same security boundary**. The RFC also defines authentication scope by URI path for Basic, though how browsers/caches apply it can depend on the client. Do not assume browsers will always prompt exactly once per path group.

### 4.1. A realm is not a role, tenant, or password store

| Misconception | Reality |
|---|---|
| `realm="admins"` forces the user to be an admin. | No. `hasRole("ADMIN")` or authorization policy determines permissions. |
| Realm represents a verified tenant. | No. Realm is challenge metadata; tenants require separate authentication/binding. |
| Changing realm renames users or resets passwords. | No. It does not touch `ReactiveUserDetailsService`/`PasswordEncoder`. |
| Each realm automatically creates a new `SecurityWebFilterChain`. | No. Security chain selection depends on `securityMatcher(...)` and bean order. |
| Realm is like JWT audience/OAuth2 scope. | No. Those are concepts from other tokens/protocols. |
| Realm protects endpoints without needing authorization. | No. Rules like `authenticated()`, `hasRole(...)`, etc. are still required. |
| Realm is verified principal information. | No. It is a label sent by the server in the response challenge. |

Choose a short, stable, non-sensitive realm, typically a clear ASCII string. Never interpolate user-supplied header/query values directly into the realm because this data is emitted in an HTTP header; if a dynamic realm is needed, validate/escape it and account for header injection risks.

### 4.2. Browser prompts and API clients

A browser may display a Basic popup when receiving `WWW-Authenticate: Basic realm="..."` with 401, then remember the username/password for a scope/duration depending on its implementation. API clients such as curl, Postman, and SDKs may behave differently; typically the developer supplies credentials explicitly.

- Do not treat the browser popup as a login page built by Spring Security.
- Do not conclude that 401 will always trigger a popup across all browsers, all AJAX/fetch calls, or proxies.
- If you want the API to return JSON so an SPA displays its own login screen, adding a JSON body **is not guaranteed** to suppress browser popups while a Basic challenge is still sent.
- Do not blindly apply Servlet Basic notes about `X-Requested-With: XMLHttpRequest` to WebFlux; verify the reactive implementation's behavior and test on real clients.
- Do not use "constantly changing the realm" as a logout mechanism; browsers may still cache Basic credentials, and the backend may not invalidate any session/token either.

## 5. Responses when unauthenticated and unauthorized

| Request/scenario | Typical status | How it is handled |
|---|---|---|
| `GET /api/private` without credentials, `authenticated()` rule | **401** | Basic challenge `WWW-Authenticate` |
| `GET /api/private` with wrong Basic credentials | **401** | Authentication failure, may re-challenge |
| Account locked/disabled/expired in username/password login | **401** | Authentication failed; details in internal audit |
| Valid user missing role/scope | **403** | Access denied; should not keep prompting for the same password |
| `POST` rejected by CSRF filter | Usually **403** | Not necessarily due to missing role |
| Public `permitAll()` resource without credentials | May be **200** | No challenge required |
| HTTP proxy requiring client authentication to the proxy | **407** | `Proxy-Authenticate`, not `WWW-Authenticate` |
| Non-existent URL allowed to reach handler | **404** | Not a login error |

You cannot infer the exact cause from status alone. An `AuthenticationException` can be turned into 401 by an authentication entry point; an `AccessDeniedException` from authorization can become 403 or trigger authentication if the user is not yet authenticated.

### 5.1. 401: missing or invalid credentials

When protecting an endpoint with `authenticated()`, a request lacking Authentication can be rejected by authorization; error handling uses `ServerAuthenticationEntryPoint` to commence authentication. With HTTP Basic, the typical response is status 401 and a Basic challenge header.

If the client sends invalid Basic credentials, the authentication filter can fail **before** authorization, and the authentication failure handler/entry point can return 401. These are two different causal paths, both requiring a consistent response.

### 5.2. 403: authenticated but missing permissions

If a user has `ROLE_READER` while the endpoint requires `ROLE_ADMIN`, valid credentials are still **insufficient**. In standard WebFlux configuration, `ServerAccessDeniedHandler` returns 403; do not return 401 just to make the browser re-show the Basic prompt, because re-entering the same credentials does not change authorities.

### 5.3. 407: proxy authentication

`407 Proxy Authentication Required` uses `Proxy-Authenticate` and `Proxy-Authorization`. Do not use this as the login response of a WebFlux origin server. A proxy may sit in front of the API, but proxy authentication and API user authentication are separate responsibilities.

### 5.4. permitAll does not mean skipping authentication

For a `permitAll()` URL, authorization does not require a logged-in principal. However, if a client **actively sends invalid Basic credentials**, the authentication filter may check them and return 401. Hence "public GET without credentials" and "public GET with wrong Basic" are two distinct tests. Likewise, `permitAll` does not disable CSRF or other security filters.

## 6. Which reactive classes handle this?

Conceptual model:

~~~text
Spring Security WebFilterChainProxy
  |
  +-- HTTP Basic authentication filter
  |      |
  |      +-- reads Authorization header for Basic
  |      +-- ReactiveAuthenticationManager verifies
  |      +-- success: Authentication into reactive security context
  |      +-- failure: failure handling / entry point
  |
  +-- AuthorizationWebFilter
         |
         +-- authenticated() when Authentication is missing
         |        -> ExceptionTranslationWebFilter
         |        -> ServerAuthenticationEntryPoint
         |        -> 401 + WWW-Authenticate
         |
         +-- authenticated but missing role
                  -> ServerAccessDeniedHandler
                  -> typically 403
~~~

The diagram only shows **roles and outcomes**, not a hardcoded filter order. Actual order is governed by `SecurityWebFiltersOrder`/chain configuration.

### 6.1. ServerAuthenticationEntryPoint

The reactive interface `org.springframework.security.web.server.ServerAuthenticationEntryPoint` has the method:

~~~java
Mono<Void> commence(
    ServerWebExchange exchange,
    AuthenticationException exception);
~~~

The signature above is condensed for learning, not a standalone class. It creates a response starting authentication for a `ServerWebExchange`. Do not use the Servlet interface `org.springframework.security.web.AuthenticationEntryPoint` with `HttpServletRequest`/`HttpServletResponse` parameters.

### 6.2. HttpBasicServerAuthenticationEntryPoint

The class `org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint` is the built-in entry point for Basic:

- `new HttpBasicServerAuthenticationEntryPoint()` creates an instance.
- `setRealm(String)` sets the realm name, defaulting to `"Realm"`.
- `commence(...)` emits a 401 response and Basic challenge.
- Can be used both when credentials are omitted and when credentials are sent but authentication fails.

### 6.3. Wire the same entry point into both branches

Illustrative configuration inside a `SecurityWebFilterChain` bean:

~~~java
HttpBasicServerAuthenticationEntryPoint entryPoint =
    new HttpBasicServerAuthenticationEntryPoint();
entryPoint.setRealm("Learning API");

http.httpBasic(basic ->
    basic.authenticationEntryPoint(entryPoint));

http.exceptionHandling(exceptions ->
    exceptions.authenticationEntryPoint(entryPoint));
~~~

This is a **configuration snippet**, not a complete application. Purpose:

- `httpBasic(...authenticationEntryPoint(...))` handles failures from HTTP Basic authentication.
- `exceptionHandling(...authenticationEntryPoint(...))` handles authentication requests when authorization sees an unauthenticated user.
- Using the same instance prevents bugs like "no Basic gives realm A; wrong Basic gives realm B".

With multiple authentication mechanisms (Basic + Bearer, form login, OAuth2), a global entry point may not fit all URLs. Configure per `SecurityWebFilterChain` and matcher, thoroughly testing every branch instead of using one Basic challenge everywhere.

## 7. Java 17 Demo: Custom Basic realm in Spring WebFlux

Self-contained runnable example using **Java 17**, **Spring Boot 3.5.16**, and Spring Security/WebFlux dependencies managed by Boot:

- `GET /api/public`: public.
- `GET /api/private`: requires authenticated.
- `GET /api/admin`: requires `ROLE_ADMIN`.
- `reader:demo-pass` has `ROLE_READER`; `admin:admin-pass` has `ROLE_ADMIN`.
- Basic challenge realm is `Learning API`.

**For localhost only.** The demo stores passwords with `{noop}` and hardcodes them in Java to observe HTTP; production must use strong encoders/hashes, secret management, HTTPS/TLS, and rate limiting.

### 7.1. Structure

~~~text
webflux-basic-challenge/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/BasicChallengeApplication.java
    └── test/java/example/BasicChallengeIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-basic-challenge'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Boot 3.5.16 requires Java 17+ and a supported Gradle version (7.6.4+ or 8.4+ in the respective Gradle lines). If a wrapper is present, prefer using the wrapper to avoid version differences across machines.

### 7.2. Complete application

`src/main/java/example/BasicChallengeApplication.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class BasicChallengeApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicChallengeApplication.class, args);
    }

    @Bean
    HttpBasicServerAuthenticationEntryPoint basicEntryPoint() {
        var entryPoint = new HttpBasicServerAuthenticationEntryPoint();
        entryPoint.setRealm("Learning API");
        return entryPoint;
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // {noop} for local demo only.
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        HttpBasicServerAuthenticationEntryPoint entryPoint) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(basic ->
                basic.authenticationEntryPoint(entryPoint))
            .exceptionHandling(exceptions ->
                exceptions.authenticationEntryPoint(entryPoint))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicRoute() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/private")
        Mono<Map<String, String>> privateRoute(
            ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "access", "private",
                    "username", principal.getName()));
        }

        @GetMapping("/api/admin")
        Mono<Map<String, String>> adminRoute(
            ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "access", "admin",
                    "username", principal.getName()));
        }
    }
}
~~~

**Explaining the connection to the lesson:**

1. The `HttpBasicServerAuthenticationEntryPoint` bean sets a fixed realm; no roles, usernames, or passwords are configured here.
2. The `MapReactiveUserDetailsService` bean holds two demo users for the reactive authentication manager to verify.
3. `httpBasic` processes Basic credentials and uses the specified entry point.
4. `exceptionHandling` uses the same entry point when an unauthenticated request is rejected by access rules.
5. `pathMatchers("/api/admin").hasRole("ADMIN")` is the actual authorization rule; realm `Learning API` does not grant admin permissions.
6. `formLogin(...disable)` prevents the demo from redirecting to a login form; we want to observe HTTP Basic responses.
7. The controller processes requests **after** security filters. It does not need to set `WWW-Authenticate` itself.

### 7.3. Testing with curl

In the `webflux-basic-challenge` directory:

~~~bash
gradle bootRun
~~~

If using Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

In another terminal, once the server is running on port 8080:

~~~bash
# No Authorization: requires Basic challenge
curl -i http://localhost:8080/api/private

# Authorization Basic with wrong password: still requires challenge
curl -i -u reader:wrong-pass http://localhost:8080/api/private

# Authenticated user can access private endpoint
curl -i -u reader:demo-pass http://localhost:8080/api/private

# Authenticated user but without ROLE_ADMIN
curl -i -u reader:demo-pass http://localhost:8080/api/admin

# Admin with matching role
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Public endpoint without credentials
curl -i http://localhost:8080/api/public

# Public endpoint with intentionally wrong Basic credentials
curl -i -u reader:wrong-pass http://localhost:8080/api/public
~~~

In PowerShell, use `curl.exe` if `curl` is aliased. The `-i` flag prints HTTP response headers; `-u` instructs curl to build a Basic header from the username/password pair. Never put real passwords on the command line of shared machines because they can leak via shell history or process listings.

| Request | Expected HTTP status | Key outcome |
|---|---|---|
| `GET /api/private` no credentials | **401** | `WWW-Authenticate: Basic realm="Learning API"` |
| `GET /api/private` wrong Basic | **401** | Same Basic challenge due to configured entry point |
| `GET /api/private` valid reader Basic | **200** | JSON with `"username":"reader"` |
| `GET /api/admin` valid reader Basic | **403** | Lacks admin permissions despite valid credentials |
| `GET /api/admin` valid admin Basic | **200** | JSON with `"username":"admin"` |
| `GET /api/public` no credentials | **200** | No Basic challenge needed |
| `GET /api/public` wrong Basic | **May be 401** | Authentication filter may reject even though URL is permitAll |

**Expected HTTP response** excerpts, not fixed Java program stdout:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
~~~

~~~http
HTTP/1.1 403 Forbidden
~~~

Success JSON may have different field ordering; headers such as `Date`, `Cache-Control`, and `Content-Length` depend on the environment. Do not write tests comparing an entire byte-for-byte HTTP response when you only need to verify status and challenge.

### 7.4. Why 403 instead of 401?

A `reader:demo-pass` request to `/api/admin` already passed authentication. Authorization knows the user lacks `ROLE_ADMIN`. Forcing the user to re-enter the same credentials defeats the purpose; the normal response is 403. This shows that realm does not replace role policy.

## 8. Integration tests with WebTestClient

File `src/test/java/example/BasicChallengeIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BasicChallengeIntegrationTest {

    @Autowired
    WebTestClient client;

    private static final String BASIC_CHALLENGE =
        "Basic realm=\"Learning API\"";

    @Test
    void missingCredentialGets401AndRealm() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE, BASIC_CHALLENGE);
    }

    @Test
    void wrongCredentialAlsoGets401AndRealm() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE, BASIC_CHALLENGE);
    }

    @Test
    void correctCredentialAllowsPrivateEndpoint() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("private")
            .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void missingAdminRoleIs403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminWithCorrectCredentialIsAllowed() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("admin")
            .jsonPath("$.username").isEqualTo("admin");
    }

    @Test
    void publicRouteDoesNotRequireCredential() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("public");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test` if a wrapper is present. Six tests are expected to pass with the demo's dependencies/configuration. The tests intentionally verify the **challenge header on both the missing-credential and wrong-credential branches**; testing 403 separately proves authorization logic isn't stuffed into the Basic entry point.

This lesson provides runnable self-contained code once you create the files and dependencies properly, though actual logs/statuses still require confirmation in your execution environment; never treat static HTTP excerpts as proof in place of tests.

## 9. When you want to return JSON errors instead of the default response

Many APIs want a response body like:

~~~json
{"error":"authentication_required"}
~~~

You can use a custom `ServerAuthenticationEntryPoint` to write a JSON body while still preserving the HTTP challenge. Example **code snippet inside a configuration class**, not a standalone program:

~~~java
ServerAuthenticationEntryPoint jsonBasicEntryPoint =
    (exchange, exception) -> {
        ServerHttpResponse response = exchange.getResponse();

        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().set(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"Learning API\"");
        response.getHeaders().setContentType(
            MediaType.APPLICATION_JSON);

        byte[] body = "{\"error\":\"authentication_required\"}"
            .getBytes(StandardCharsets.UTF_8);

        return response.writeWith(
            Mono.just(response.bufferFactory().wrap(body)));
    };
~~~

Corresponding imports: `ServerAuthenticationEntryPoint` in `org.springframework.security.web.server`, `ServerHttpResponse` in `org.springframework.http.server.reactive`, `HttpStatus`/`HttpHeaders`/`MediaType` in `org.springframework.http`, `StandardCharsets` in `java.nio.charset`, and `Mono` in Reactor.

Attach this entry point in both places when consistency is needed:

~~~java
http.httpBasic(basic ->
    basic.authenticationEntryPoint(jsonBasicEntryPoint));

http.exceptionHandling(exceptions ->
    exceptions.authenticationEntryPoint(jsonBasicEntryPoint));
~~~

**Do not combine this snippet alongside the demo entry point bean in section 7 unless you clearly intend to replace it.** It only illustrates a customization strategy.

Principles:

1. Never drop `WWW-Authenticate` when returning 401.
2. Set status/headers before the body commits the response.
3. Never expose `exception.getMessage()` or specific usernames/account statuses in public error JSON; prevent account enumeration.
4. Never return 401 for all access denials; 403 needs its own handling branch.
5. Never block or subscribe manually inside a reactive handler; return `Mono<Void>` to the framework.
6. Choose the right scheme: if the API uses Bearer JWT only, do not emit a Basic challenge arbitrarily.
7. Test browser UX: a JSON body is not guaranteed to prevent popups if a Basic challenge is still sent.

## 10. Multiple SecurityWebFilterChains and multiple authentication mechanisms

In a mixed application where `/legacy/**` uses HTTP Basic and `/api/**` uses Bearer JWT, you must select the right **security chain and entry point** per request. You cannot solve this by renaming a realm from `Legacy` to `API`:

- `securityMatcher(...)` determines which chain matches a URL.
- `@Order` determines priority across multiple chains; only the first matching chain is selected.
- `authorizeExchange(...)` decides permissions within the selected chain.
- `httpBasic(...)` / `oauth2ResourceServer(...)` determines the authentication scheme.
- `authenticationEntryPoint` and failure handlers determine the challenge/response.

A `WWW-Authenticate` header can carry multiple challenges or appear across multiple header fields; the RFC allows this, though parsers can struggle with commas inside quoted strings. When using only Basic, keep the challenge clear; never use `split(",")` as a general-purpose WWW-Authenticate parser.

In particular, avoid wiring a global Basic entry point for all URLs of a Bearer API: it can cause clients to receive the wrong challenge and send passwords where they do not belong.

## 11. Common mistakes

**Mistake 1 — Returning 401 without `WWW-Authenticate`.** RFC 9110 requires 401 to include an applicable challenge. For Basic, use `HttpBasicServerAuthenticationEntryPoint` or a custom handler that keeps the header.

**Mistake 2 — Treating realm as role or tenant.** Realm is a protection-space label and does not verify identity; only verified authorization policies grant permissions.

**Mistake 3 — Confusing header directions.** `WWW-Authenticate` is server → client; `Authorization` is client → server. Never put raw passwords in the challenge.

**Mistake 4 — Customizing `httpBasic.authenticationEntryPoint` but forgetting `exceptionHandling.authenticationEntryPoint`.** The wrong-password branch and missing-credential branch may emit different realms; test both.

**Mistake 5 — Using Servlet APIs.** WebFlux requires `ServerWebExchange` and `ServerAuthenticationEntryPoint`, not `HttpServletResponse`.

**Mistake 6 — Returning 401 for authenticated users missing a role.** The right result is usually 403; do not push clients into an unnecessary Basic prompt loop.

**Mistake 7 — Assuming Base64 secures passwords.** Basic requires HTTPS/TLS; forbid logging credentials and never pass passwords in URLs.

**Mistake 8 — Returning details like "user does not exist/locked" in public responses.** This aids user enumeration; use generic error codes and record details in controlled audits.

**Mistake 9 — Changing the realm to log out.** Realm does not reliably clear browser credential caches or invalidate tokens/sessions; design logout per the actual auth scheme.

**Mistake 10 — Assuming `permitAll` guarantees every request returns 200.** Invalid Basic headers may still be rejected by the authentication filter even on public endpoints.

**Mistake 11 — Assuming a Basic challenge always makes browsers prompt.** Behavior varies by client, request context, and browser policy; test the real app.

**Mistake 12 — Reusing a Basic challenge for a JWT resource server.** Different schemes need matching challenges/entry points and cannot be substituted with a realm.

**Mistake 13 — Comparing full raw response dumps.** Dynamic headers and JSON property order can vary; assert status, `WWW-Authenticate` value, and meaningful fields.

**Mistake 14 — Not distinguishing proxy authentication from origin authentication.** 407/`Proxy-Authenticate` differs from 401/`WWW-Authenticate`.

**Mistake 15 — Building a realm from unvalidated query/header values.** Realm is an HTTP header value; this can cause header injection or leak sensitive data in responses.

## 12. Pre-deployment review checklist

1. Does the resource truly need HTTP Basic, or would Bearer/OIDC/session login fit better?
2. Is HTTPS enforced with all hops across gateways/reverse proxies properly secured?
3. Do `securityMatcher` and `authorizeExchange` cover all protected resources accurately?
4. Missing credentials → **401** with the expected Basic realm challenge?
5. Wrong Basic password → **401** with a consistent realm/challenge?
6. Authenticated but missing role → **403**, not forced to 401?
7. Public routes → work without credentials; behavior when sending wrong Basic verified?
8. Is the realm short, stable, and free of sensitive data or untrusted input?
9. Is a consistent entry point configured for both missing-credential and authentication-failure branches?
10. Are there `WebTestClient` tests for status and `WWW-Authenticate`?
11. Are `Authorization`, Basic credentials, cookies, and passwords kept out of logs?
12. If returning JSON errors, is the challenge preserved on 401 without leaking account enumeration?
13. If multiple chains/schemes exist, is the challenge selected accurately per URL and mechanism?
14. Do primary clients (curl/browser/SPA/mobile) handle 401 with proper UX and no infinite loops?
15. Are rate limiting, TLS, password hashing, credential rotation, and incident response in place?
16. Are realms never relied upon to perform logout, verify tenants, or grant roles?

## 13. Review questions

**1.** Does `WWW-Authenticate: Basic realm="Learning API"` prove a user is logged in?

**Answer:** No. It is a challenge sent by the server to the client, not an Authentication or principal.

**2.** An endpoint protected by `authenticated()` receives a request without credentials; what status and header are appropriate for Basic?

**Answer:** 401 Unauthorized along with `WWW-Authenticate: Basic realm="..."` matching the application's realm.

**3.** A user enters the right password but lacks `ROLE_ADMIN` when accessing `/api/admin`. Should 401 or 403 be returned?

**Answer:** Typically 403, because Authentication succeeded while authorization failed.

**4.** Does setting `realm="ADMIN"` automatically turn `reader` into an admin?

**Answer:** No. Realm only names the protection space; roles are decided by policy based on Authentication/authorities.

**5.** What is the difference between 401 and 407?

**Answer:** 401 uses `WWW-Authenticate` for the origin server; 407 uses `Proxy-Authenticate` for a proxy.

**6.** Why is a 401 JSON response missing `WWW-Authenticate` problematic?

**Answer:** It can violate RFC 9110, leaving clients unsure which scheme to use. Use a valid entry point/challenge.

**7.** Will a client sending wrong Basic credentials to a `permitAll` route definitely receive 200?

**Answer:** No. The authentication filter may reject invalid credentials before authorization.

**8.** How do you ensure the exact same realm for both missing credentials and wrong credentials?

**Answer:** Configure a unified entry point for both `httpBasic` and `exceptionHandling` as needed; write two separate `WebTestClient` tests asserting 401 status and header.

## Official documentation

- RFC 7617 — The "Basic" HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 9110 — HTTP Semantics, sections 11.6.1 and 15.5.2: https://www.rfc-editor.org/rfc/rfc9110.html
- Spring Security — HttpBasicServerAuthenticationEntryPoint (reactive): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/HttpBasicServerAuthenticationEntryPoint.html
- Spring Security — ServerHttpSecurity.HttpBasicSpec: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security — ServerHttpSecurity / exceptionHandling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.5 — System Requirements (JDK/Gradle): https://docs.spring.io/spring-boot/3.5/system-requirements.html
