# HTTP Basic in Browsers and Its Relationship with CSRF

## 1. The problem: stateless Basic still carries CSRF risk

HTTP Basic allows a client to send a username and password via the `Authorization` HTTP header so the server can authenticate each request. In a Spring WebFlux application, this can occur without storing login state in a server session.

However, **not storing a login session does not mean immunity to CSRF**, especially when the client is a browser. Browsers can cache HTTP Basic credentials per authentication scope (protection space) and automatically attach them to subsequent requests targeting that scope. If another website causes the browser to send a state-changing request to the protected app, the server may see valid credentials even though the user never intended that action.

Spring Security explicitly notes that **browsers using Basic authentication can still be vulnerable to CSRF**, similar to other mechanisms where the browser automatically sends credentials. This differs from a CLI or backend service that explicitly sets the `Authorization` header only in code you control.

**Important note:** do not claim that every browser version always auto-sends Basic credentials on every cross-site request. Outcomes depend on cache state, origin, realm, navigation type, `fetch` credentials mode, and browser policies. Security design must account for **ambient authentication** in realistic scenarios and test across supported browsers.

### Lesson objectives

After this lesson, you should:

1. Understand the HTTP Basic challenge/response, browser authentication caching, and why Base64 is not encryption.
2. Accurately describe how a forged request can exploit Basic credentials.
3. Distinguish CSRF from CORS, SameSite, authentication, authorization, and XSS.
4. Know `CsrfWebFilter`, `ServerCsrfTokenRepository`, token handlers, and Spring Security Reactive's HTTP method rules.
5. Write a default Spring WebFlux Basic + CSRF configuration and test POST requests with and without tokens.
6. Obtain and use a CSRF token in a standalone Java 17+ Gradle application.
7. Know when disabling CSRF can be considered and why stateless authentication configuration alone is insufficient.

This lesson belongs to the **HTTP Basic** section of the Spring Security Reactive module. The focus is browsers: do not turn it into a general survey of all authentication mechanisms.

## 2. How does HTTP Basic work in a browser?

HTTP Basic is specified in RFC 7617. Example request:

~~~http
GET /api/memo HTTP/1.1
Host: example.test
Authorization: Basic bGVhcm5lcjpsb2NhbHBhc3M=
~~~

The Base64 payload in the example represents the string `learner:localpass`, not a securely encrypted secret. Anyone able to see the header can decode it; **HTTPS/TLS is mandatory for real credentials**. Never put usernames/passwords in URLs, query strings, or logs.

When a protected endpoint has not received valid credentials, the server may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="example"
~~~

`WWW-Authenticate` is an HTTP authentication challenge. The browser may show a prompt requesting username/password and reuse them according to its caching policy. Typical interaction flow:

~~~text
Browser                                     WebFlux Security
   |                                                |
   | GET /api/memo                                  |
   |----------------------------------------------->|
   | 401 + WWW-Authenticate: Basic ...              |
   |<-----------------------------------------------|
   |                                                |
   | User enters login credentials                  |
   | GET /api/memo + Authorization: Basic ...       |
   |----------------------------------------------->|
   | 200 + data                                     |
   |<-----------------------------------------------|
~~~

Once the browser retains Basic credentials, subsequent requests can be authenticated without re-prompting the user. **That is both a convenience and a factor to account for in the CSRF threat model.**

### 2.1. Realm, origin, and login session

Distinguish:

- **Browser authentication cache:** where the browser manages HTTP authentication credentials per its own policy.
- **Reactor Context:** the context of a single WebFlux request subscription; Spring Security places `Authentication` there after authenticating.
- **`ServerSecurityContextRepository`:** strategy for saving/loading `SecurityContext` across requests; can be configured as no-op.
- **`WebSession`:** the session object in WebFlux; may serve CSRF or other purposes, not necessarily a login session.
- **`realm`:** a Basic challenge directive, not a Java object or a cookie.

Having no login cookie on the response **does not prove** the browser holds no reusable credentials. Conversely, a browser sending a valid Basic header does not prove the server stored authentication in `WebSession`.

### 2.2. Logout is harder to handle than form login

With form login/sessions, the server can invalidate the session to end the login. With HTTP Basic, the browser may still remember the username/password and auto-resend it; the server cannot guarantee logout merely by deleting a server session. Credential-forgetting behavior varies across browsers. For production browser apps needing a strong login/logout UX, evaluate a more suitable authentication method instead of plain Basic.

## 3. What is CSRF, and how does it relate to HTTP Basic?

**Cross-Site Request Forgery (CSRF)** is an attack in which an untrusted source causes a user's browser to send a request with side effects to an application where the user already has an authenticated context. The server can accurately identify the user from the credentials, yet cannot tell whether the user intentionally triggered that action.

Imagine `https://account.example.test` exposes:

~~~http
POST /api/change-email
Content-Type: application/x-www-form-urlencoded

email=another@example.test
~~~

Another site can embed a form:

~~~html
<!-- Mechanism illustration only: not code to ship in production. -->
<form action="https://account.example.test/api/change-email"
      method="post">
  <input name="email" value="other@example.test">
  <button type="submit">Continue</button>
</form>
~~~

A form on another origin can trigger a request to the target application. If the browser automatically attaches cached Basic credentials in that scenario, and the server only checks username/password, the action can execute unintendedly. The attacker **does not need to know the password and does not need to read the response body**.

Risk depends on the specific browser/context; the example explains **attack preconditions** rather than claiming every browser always sends Basic on all cross-site forms.

### 3.1. Conditions for CSRF to cause harm

A CSRF scenario typically involves:

1. **A side effect** such as changing an email, making a purchase, deleting a resource, updating settings, or transferring funds.
2. **Credentials the browser may automatically attach** to requests to the target app: cookies, cached HTTP Basic credentials, or similar ambient authentication.
3. **An external source able to make the browser issue** an eligible request.
4. **Lack of request-origin/intent validation on the server** beyond identity authentication.

If an attacker steals a password and sends requests from their own machine, that is **credential compromise**, not CSRF. In CSRF, the victim's browser sends the request carrying an authenticated context.

### 3.2. Authentication does not prove user intent

- HTTP Basic asks: "Does the request carry valid credentials?"
- Authorization asks: "Is that identity permitted to modify this resource?"
- CSRF protection asks: "Was this state-changing request initiated through a trusted application flow?"

A request can pass both Basic **and** authorization and still be CSRF. Therefore, a POST with valid Basic credentials must still be blocked if it lacks a CSRF token.

## 4. Stateless does not mean immune to CSRF

A WebFlux architecture might configure:

~~~java
http.securityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());
~~~

This instructs Spring Security **not to save/load `SecurityContext` through the repository for reuse across requests**. It does not clear the browser's Basic authentication cache, does not disable CSRF, and does not automatically disable storing CSRF tokens in `WebSession`.

Comparison table:

| Concept | Function | Disabled by NoOpServerSecurityContextRepository? |
| --- | --- | --- |
| Browser HTTP Basic credential cache | Browser remembers and may resend username/password | **No** |
| Reactive `SecurityContext` | Identity for the current subscription/request | **No** |
| Authentication persistence | Saves context from previous request | **Yes**, for the configured repository |
| CSRF token | Verifies unsafe requests | **No** |
| `WebSessionServerCsrfTokenRepository` | Stores expected CSRF token in WebSession | **No** |
| HTTP response cache | Caches responses in browser/proxy | **No** |
| CORS | Governs cross-origin JavaScript access | **No** |

Notably, WebFlux CSRF by default stores the expected token in `WebSession`. An app that **does not persist authentication** can still create a WebSession cookie to hold the CSRF token. "Having a session cookie" and "persisting login" are two separate things.

If a system must maintain **zero server-side sessions** whatsoever, both authentication persistence **and** CSRF repository/client integration must be designed accordingly; disabling one piece does not prove the overall requirement is met.

## 5. How does Spring Security Reactive protect against CSRF?

In WebFlux's `SecurityWebFilterChain`, the primary components are:

- `CsrfWebFilter`: participates in the WebFilter chain, decides which requests require protection, loads/verifies tokens, and rejects missing/invalid ones.
- `ServerCsrfTokenRepository`: contract to generate, save, and load the expected token.
- `WebSessionServerCsrfTokenRepository`: default implementation storing the token in `WebSession`.
- `CookieServerCsrfTokenRepository`: option to store the token via cookie for certain frontend apps.
- `ServerCsrfTokenRequestHandler`: provides and extracts tokens from requests/attributes.
- `XorServerCsrfTokenRequestAttributeHandler`: default request handler since Spring Security 6.x, adding masking to mitigate BREACH risks in applicable scenarios.

**CSRF protection is enabled by default** in Spring Security WebFlux. By standard rules, HTTP methods `GET`, `HEAD`, `TRACE`, and `OPTIONS` are treated as safe and do not require a CSRF token; unsafe methods such as `POST`, `PUT`, `PATCH`, and `DELETE` require a token.

This means developers **must ensure GET/HEAD have no side effects**. Spring Security does not inspect controller logic to know whether a GET deletes an order.

### 5.1. POST verification flow

~~~text
POST /api/memo
       |
       v
CsrfWebFilter: does the request require CSRF?
       |
       +--> Missing / wrong token --> reject (usually HTTP 403)
       |
       +--> Valid token
                |
                v
           Authentication/Authorization
                |
                v
           Controller handles
~~~

This is a conceptual diagram, not an absolute ordering list of all filters. A POST missing both Basic credentials and a CSRF token may receive **403 before authorization returns 401**, depending on filter order. Never rely on a single status code to guess the entire pipeline.

### 5.2. Where must the CSRF token be sent?

To distinguish legitimate requests from forged ones, the client must send the token in a part of the request **not automatically attached by the browser just for holding credentials**:
- Hidden form parameter, typically `_csrf`.
- HTTP header such as `X-CSRF-TOKEN` or a name configured by the repository/handler.
- Another appropriate method per threat model.

Example request with both Basic and CSRF:

~~~http
POST /api/memo HTTP/1.1
Host: example.test
Authorization: Basic ...
X-CSRF-TOKEN: <issued-csrf-token>
Content-Type: text/plain

new-value
~~~

The Basic header **does not replace** the CSRF token. Any origin forbidden from reading the token must also not accidentally be allowed to read the token endpoint via overly permissive CORS.

### 5.3. Spring Security 6 and token masking

`CsrfWebFilter` can place `Mono<CsrfToken>` into `ServerWebExchange` under the key `CsrfToken.class.getName()`. Since Spring Security 6, the default handler applies masking to defend against BREACH; frontend apps should use the **token exposed through the request handler**, rather than attempting to grab a raw token from the repository and transform it with a custom algorithm.

For HTML forms, Thymeleaf integrates token rendering. For SPAs/AJAX, an endpoint or cookie repository can be used as properly configured. Login/logout flows may rotate tokens; the frontend must re-fetch a valid token whenever context changes.

## 6. How CSRF differs from CORS and SameSite

**CORS** primarily controls the ability of JavaScript on another origin to make cross-origin requests or read results via Fetch/XHR. **CSRF** is the risk of tricking a user into sending a state-changing request; the attacker **does not need to read the response**.

A cross-site HTML form can submit a simple request without needing JavaScript response-reading rights. Thus, **"CORS blocks the attacker's origin" is not enough to declare CSRF impossible**.

| Question | CORS | CSRF |
| --- | --- | --- |
| Can a script on another origin read the response? | Controlled | Not the primary concern |
| Was a state-changing request sent from a trusted flow? | Not guaranteed | Has anti-forgery mechanism |
| Does it replace Basic authentication? | No | No |
| Does it stop all cross-site HTML forms from sending requests? | Not guaranteed | Tokens can stop the server from accepting them |
| Can misconfiguration leak tokens? | Yes | Tokens still need protection |

### 6.1. SameSite handles cookies only

Cookie attribute `SameSite=Lax/Strict` can restrict cross-site cookie sending under certain conditions. However, cached HTTP Basic Authorization **is not a cookie**, so you cannot cite a cookie's SameSite attribute as proof that the browser will not send Basic credentials.

If CSRF tokens are stored in WebSession/cookies, that cookie itself must also have appropriate Secure/HttpOnly/SameSite settings. Note that "same-site" is not identical to "same-origin"; subdomains on the same site can still be different origins.

### 6.2. XSS is a different threat

If an attacker can execute JavaScript within the **same legitimate origin** (XSS), that script can read any CSRF token accessible to the frontend and use it to issue requests. Hence CSRF tokens do not replace XSS prevention, output encoding, and Content Security Policy. These defenses are complementary layers.

## 7. Runnable Java 17+ example: Basic + CSRF in WebFlux

The project below uses Spring Boot **3.3.13**, Spring Security Reactive 6.x, Java 17, and Gradle. The goal is to learn the mechanics: having valid Basic credentials **is still not enough** to POST if a CSRF token is missing.

An `AtomicReference<String>` simulates in-memory data. The demo password uses `{noop}` purely for simplicity; **do not use in production**.

~~~text
webflux-basic-csrf/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── MemoController.java
    └── test/java/demo/
        └── BasicCsrfTest.java
~~~

### 7.1. Gradle build

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-basic-csrf'
~~~

`build.gradle`:

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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Application

`src/main/java/demo/DemoApplication.java`:

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

### 7.3. SecurityWebFilterChain

`src/main/java/demo/SecurityConfig.java`:

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

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
~~~

Analysis:
1. `authorizeExchange` requires authentication for every demo endpoint, including `/csrf`.
2. `httpBasic` enables reading Basic credentials.
3. `formLogin` is disabled to avoid mixing form login flow with Basic.
4. `NoOpServerSecurityContextRepository` does not persist authentication for reuse across requests. It **does not disable** CSRF.
5. `csrf(Customizer.withDefaults())` retains CSRF protection, even though that is already the default. Writing it explicitly lets learners see the difference between CSRF policy and authentication persistence.
6. `{noop}localpass` is for local demo only. Production must use HTTPS, strong password hashing, rate limiting, login monitoring, and proper account management policies.

Do not add `CsrfWebFilter` manually; Spring Security wires the filter when building the security chain.

### 7.4. Controller

`src/main/java/demo/MemoController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class MemoController {

    private final AtomicReference<String> memo =
            new AtomicReference<>("initial");

    @GetMapping(path = "/api/memo",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> readMemo() {
        return Mono.fromSupplier(memo::get);
    }

    @PostMapping(path = "/api/memo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> updateMemo(@RequestBody Mono<String> body) {
        return body.map(value -> {
            memo.set(value);
            return "saved:" + value;
        });
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is not available"));
        }

        return token.map(value -> Map.of(
                "headerName", value.getHeaderName(),
                "token", value.getToken()));
    }
}
~~~

Explanation:
- `GET /api/memo` only reads data, so it is not a request with side effects.
- `POST /api/memo` modifies data; the handler **is not executed** if the CSRF filter rejects it beforehand.
- `Mono<String>` in `@RequestBody` reads the request body within the WebFlux pipeline, without calling `block()` or `subscribe()`.
- `GET /csrf` reads the `Mono<CsrfToken>` placed by Spring Security in exchange attributes. When subscribed, the token can be generated/saved per the repository.
- The token returned by `getToken()` may be masked per Spring Security 6.x; clients use **the provided value**, without attempting to unmask it.
- The JSON returns two fields `headerName` and `token`; key order is not fixed.
- The token-issuing endpoint must be protected against untrusted origins reading the response; in the demo it requires Basic authentication.

**Demo limitation:** updating `AtomicReference` is not database persistence and lacks business-object ownership checks. Production apps need domain-specific authentication, authorization, and transactions. CSRF does not replace those steps.

## 8. HTTP live tests: 401, 403, and 200

In the project directory, run:

~~~bash
gradle bootRun
~~~

If a Gradle Wrapper is available, you can run `./gradlew bootRun`. The server listens by default at `http://localhost:8080` locally; real environments must use HTTPS. Run `curl` in another terminal:

~~~bash
# A. Protected GET without credentials
curl -i http://localhost:8080/api/memo

# B. GET with valid Basic, no CSRF token needed
curl -i -u learner:localpass http://localhost:8080/api/memo

# C. POST with valid Basic but missing CSRF token
curl -i -u learner:localpass \
  -H 'Content-Type: text/plain' \
  --data 'changed-without-token' \
  http://localhost:8080/api/memo

# D. Verify the previous POST was blocked and data is unchanged
curl -i -u learner:localpass http://localhost:8080/api/memo
~~~

Expected results right after the server starts:

| Command | HTTP status | Meaning |
| --- | --- | --- |
| A | **401 Unauthorized** | Unauthenticated; Basic entry point may return `WWW-Authenticate` |
| B | **200 OK**, body `initial` | GET authenticated; GET requires no CSRF token |
| C | **403 Forbidden** | POST rejected due to missing token even though Basic is valid |
| D | **200 OK**, body still `initial` | POST controller never executed |

Do not assume an unauthenticated POST definitely returns 401: `CsrfWebFilter` may block a tokenless request before the authorization layer. Nor should you assume every 403 is CSRF; 403 can also result from insufficient roles/permissions.

### 8.1. Fetching a token and sending a valid POST

With a shell having `curl` and `jq`:

~~~bash
# Step 1: fetch token, save WebSession cookie for CSRF
curl -sS -u learner:localpass \
  -c csrf-cookies.txt \
  http://localhost:8080/csrf > csrf.json

# Step 2: extract emitted header name and token
HEADER="$(jq -r '.headerName' csrf.json)"
TOKEN="$(jq -r '.token' csrf.json)"

# Step 3: send Basic + same cookie + CSRF header
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'updated-safely' \
  http://localhost:8080/api/memo

# Step 4: verify data was updated
curl -i -u learner:localpass http://localhost:8080/api/memo
~~~

While the token and WebSession cookie remain valid, the reliable outcome is:

~~~text
POST /api/memo --> HTTP 200; body: saved:updated-safely
GET  /api/memo --> HTTP 200; body: updated-safely
~~~

A **specific token** cannot be provided as fixed stdout: tokens are randomized and may be masked. If POST returns 403, check the cookie jar, header name, expired session, token rotation, path/proxy, and security chain. Do not fix it by disabling CSRF.

**Secret precaution:** `curl -u user:password` can save passwords in shell history or expose them in environments inspecting command lines. Use demo passwords locally; in production use proper secrets management and HTTPS.

### 8.2. Why is there a WebSession cookie if authentication is stateless?

In this example, the authentication repository is **no-op**, yet the default CSRF repository still saves the expected token in **WebSession**. When obtaining the token, the app can create a session/cookie for **CSRF** purposes. This cookie must be sent back so the server can compare against the expected token. Do not mistake it for a "Basic login session"; requests still need valid Basic credentials.

If an architecture requires strictly zero server sessions, CSRF token storage and browser integration must be designed differently—simply disabling the security context repository is not enough.

## 9. WebTestClient: testing CSRF with Basic credentials

Add `spring-security-test` as in the Gradle config above. Spring Security provides `SecurityMockServerConfigurers.csrf()` so tests can supply a valid CSRF token in WebFlux. The tests below use the application context and `WebTestClient`.

`src/test/java/demo/BasicCsrfTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BasicCsrfTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousGetIsUnauthorized() {
        client.get().uri("/api/memo")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void basicGetNeedsNoCsrfToken() {
        client.get().uri("/api/memo")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void basicPostWithoutCsrfIsForbidden() {
        client.post().uri("/api/memo")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("should-not-save")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void basicPostWithCsrfIsAccepted() {
        client.mutateWith(csrf())
                .post().uri("/api/memo")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("allowed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("saved:allowed");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected test outcome:** after creating the files and dependencies as above, the cases should show 401, 200, 403, 200. This is predicted from the configuration/API, **not a claim of having executed an actual build**. The `csrf()` helper is a Spring Security test utility, not a way to bypass CSRF in production.

To verify full browser interaction, test beyond simulated requests: when the browser auto-sends Basic credentials, whether tokens are emitted properly, whether cookies persist across requests, whether CORS restricts origins, and how logout/session expiration are handled.

## 10. How should a browser frontend send the CSRF token?

### 10.1. HTML form

In HTML-rendered apps, the token is usually placed in a hidden input:

~~~html
<form method="post" action="/some-action">
  <input type="hidden" name="_csrf" value="token-from-server">
  <input type="text" name="value">
  <button type="submit">Save</button>
</form>
~~~

This is a structural template; **it is not directly compatible** with the demo `/api/memo` controller because that endpoint consumes `text/plain`, whereas this form sends form data. In real apps, use an endpoint accepting form data and Thymeleaf/Spring Security integration or corresponding view logic to supply the token.

Never hard-code tokens in HTML source. The token value is generated by the server and tied to the expected token in the repository.

### 10.2. SPA/JavaScript

A same-origin frontend can fetch the token from an endpoint and attach it to unsafe requests:

~~~javascript
const result = await fetch("/csrf", { credentials: "same-origin" });
if (!result.ok) throw new Error("CSRF token unavailable");
const csrf = await result.json();

const response = await fetch("/api/memo", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "text/plain",
    [csrf.headerName]: csrf.token
  },
  body: "new-value"
});

if (!response.ok) throw new Error("Update rejected");
~~~

This snippet is **a frontend illustration**, not a guarantee that `fetch` automatically supplies Basic credentials in every situation. Browsers have their own credential caches, policies, and credential modes; the endpoint still needs valid Authentication. For cross-origin frontends, properly design CORS, CSRF, cookies, trusted origins, and authorization; never allow arbitrary origins to read tokens.

### 10.3. Cookie CSRF repository

`CookieServerCsrfTokenRepository` is an option when a JS app needs CSRF tokens via cookies. `withHttpOnlyFalse()` lets JavaScript read the cookie, trading off that the token becomes readable by same-origin JS. If the frontend does not need to read the cookie directly, prefer keeping `HttpOnly`. In Spring Security 6.x, check integration with the XOR/BREACH token request handler and token rotation; do not copy Servlet configuration into WebFlux while ignoring API differences.

CSRF tokens **are not passwords or access tokens**, yet must still be kept from untrusted origins. If XSS can execute JS within a legitimate origin, CSRF token protection can be bypassed.

## 11. When to consider disabling CSRF?

The common case is an API **not serving browsers with ambient credentials**; backend/mobile/CLI clients explicitly attach a protected Bearer token on each request, and browsers do not auto-send credentials to the endpoint. After a security review, a system may decide CSRF is unnecessary for that route set.

Example **snippet only** for an independently evaluated Resource Server API, not a standalone runnable program:

~~~java
return http
        .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
~~~

Running this requires Resource Server dependencies, valid issuer/JWK/JWT configuration, authorization policies, and error handling. This snippet **does not apply by default to browsers using HTTP Basic**.

Before disabling CSRF, answer:
1. Can any browser automatically attach Basic credentials/cookies/client certificates?
2. Are there POST/PUT/PATCH/DELETE routes that mutate data?
3. Does the app have browser pages, form login, OAuth2 login, logout, or cookie-using SPAs?
4. Do any GET endpoints accidentally mutate state?
5. Are CORS and security chain matchers scoped properly?
6. Was real browser behavior/CSRF tested rather than just `curl`?
7. Are Origin/Referer/Fetch Metadata policies or tokens needed for defense in depth?

If unsure, **keep CSRF protection** and design token issuance/submission rather than disabling it just to make requests pass.

### 11.1. Multiple security chains

When a system simultaneously serves:
- A browser website/login or Basic,
- Machine-to-machine APIs using Bearer tokens,

you can design separate `SecurityWebFilterChain` beans using `securityMatcher` and `@Order`, each with an appropriate CSRF policy. Be careful not to place a catch-all chain too early and hijack requests meant for the browser chain. Never assume from a bean name alone that a route is protected by the intended chain.

## 12. Common mistakes

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| "Basic has no session so there is no CSRF" | Browsers may auto-send cached credentials | Account for ambient authentication in browsers |
| Using GET for state-changing actions | CSRF skips safe methods by default | Use proper methods, keep CSRF protection |
| Disabling `csrf()` to fix POST 403 | Removes forged-request defense | Fetch/send valid tokens |
| Using CORS to replace CSRF | HTML forms/simple requests need not read responses | Keep independent CSRF defenses |
| Citing cookie SameSite as proof Basic is safe | SameSite only applies to cookies | Check browser Authorization mechanics |
| Letting unintended origins read `/csrf` | Can expose tokens | Restrict endpoint CORS/origins |
| Dropping cookies between GET token and POST | Repository cannot find expected token | Preserve cookie/session in the same context |
| Manually "unmasking" Spring Security 6 tokens | Token handler may reject it | Use the token issued by the current API |
| Using `{noop}` in production | Passwords stored in cleartext | Use a strong PasswordEncoder algorithm |
| Thinking Base64 is encryption | Leaks Basic credentials without TLS | Enforce HTTPS |
| Reading CSRF token with `block()` in WebFlux | Blocks event loop, breaks reactive subscription | Compose inside `Mono` |
| Manually calling `subscribe()` for auth tasks | Detaches request context/errors/cancellation | Return Publishers to the framework |
| Confusing 401 and 403 | Misdiagnoses filter/role/token | Distinguish authentication, CSRF, authorization |

Severe anti-pattern example:

~~~java
// WRONG: GET performs data deletion.
@GetMapping("/account/delete")
public Mono<Void> deleteAccount() {
    return accountService.deleteCurrentAccount();
}
~~~

This is an illustrative snippet, not runnable standalone because `accountService` is undefined. If a GET has side effects, CSRF tokens under default policy may not be required. Fix HTTP semantics and authorization rather than tweaking CORS.

### 12.1. Do not look at HTTP status alone

- `GET` missing Basic to a protected route usually returns **401**.
- `POST` with valid Basic but missing token usually returns **403**.
- `POST` missing both Basic and token may be blocked first by CSRF and return **403**, not necessarily 401.
- `POST` with valid token but wrong username/password is still rejected by authentication.
- `POST` with valid token and Basic but missing role is still rejected by authorization, usually **403**.

Inspect the filter chain, exception mapping, and **non-sensitive** technical logs to determine the true cause; never "fix 403" by granting extra roles to users or disabling CSRF.

## 13. Checklist when testing browser Basic + CSRF

1. Identify which `SecurityWebFilterChain` handles the route.
2. Check `httpBasic` and the 401/`WWW-Authenticate` entry point.
3. Verify whether unsafe requests require CSRF per matcher.
4. Ensure GET/HEAD are truly read-only with zero side effects.
5. Identify the CSRF token repository: WebSession, cookie, or custom.
6. Verify the app issues `CsrfToken` to the frontend via a trusted view/endpoint.
7. Confirm tokens are sent in the right header/form parameter matching the version's request handler.
8. If stored in WebSession, verify the session cookie is preserved between the token GET and the POST.
9. Check expiry/rotation after login, logout, and session timeout.
10. Test browser Basic caching, realm/protection space, and behavior across navigation/fetch types.
11. Verify CORS allows only truly trusted origins; attackers cannot read tokens.
12. Check HTTPS, password hashing, rate limiting, and gaps beyond CSRF.
13. Write tests for 200/401/403 and valid users missing permissions.
14. Test directly in supported browsers, not just `curl`.
15. Avoid logging Authorization headers, CSRF tokens, session cookies, and passwords.

If you hit 403, compare two POSTs with the same credentials—one without a token and one with a valid token. If Basic GET succeeds while tokenless POST returns 403, that signals **CSRF is intentionally blocking**, not that "Basic is broken".

## 14. Self-check questions

**1.** A browser remembers Basic credentials while the server stores no login session. Is CSRF possible?

> Yes. The browser can automatically send credentials on requests to the target application. Not persisting SecurityContext across requests does not eliminate this risk.

**2.** Why is a Basic header insufficient to prevent CSRF?

> Basic proves the identity on the request; CSRF protects the intent/origin context creating a state-changing operation.

**3.** Why does a POST with valid Basic credentials sometimes return 403?

> Missing/invalid CSRF token or insufficient permissions. Identify which layer rejected it.

**4.** Does `NoOpServerSecurityContextRepository` disable the WebSession CSRF repository?

> No. They manage two different kinds of state.

**5.** Does Spring Security WebFlux require a CSRF token for GET by default?

> No. Therefore GET must remain safe with no side effects.

**6.** Does CORS guarantee an HTML form from another origin cannot send a POST?

> No. CORS does not replace CSRF protections.

**7.** Does `SameSite=Strict` on a cookie guarantee cached HTTP Basic won't be sent?

> No. SameSite is a cookie policy, not an HTTP Basic cache policy.

**8.** Why must cookies be sent when using the WebSession CSRF token repository?

> The server needs to look up the expected token bound to the same WebSession to compare with the client's submitted token.

**9.** Should CSRF be disabled for every REST API?

> No. Evaluate whether clients are browsers or machines, whether browsers auto-send credentials, and each route's threat model.

**10.** Does Base64 protect Basic passwords from someone reading network traffic?

> No. Base64 is decodable; HTTPS must be used.

## 15. Key takeaways and references

**HTTP Basic in browsers does not prevent CSRF on its own, even when the server keeps no login session.** CSRF concerns a browser's ability to automatically attach credentials to a state-changing request, not cookies alone.

In Spring Security Reactive, keep `CsrfWebFilter` for browser Basic cases, issue tokens properly, and require tokens on unsafe requests. `NoOpServerSecurityContextRepository` only governs authentication persistence, not CSRF. CORS and SameSite are separate protective layers, not direct replacements for CSRF.

To protect properly, follow HTTP method semantics, enforce HTTPS, verify CSRF tokens and authorization independently, and test with both browsers and `WebTestClient`.

### Official documentation

- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security — CSRF and Stateless Browser Applications: https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security — Testing CSRF in WebFlux: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — WebFlux Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- RFC 7617 — The Basic HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617
- MDN — HTTP Authentication: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS