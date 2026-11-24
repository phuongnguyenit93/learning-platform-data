# ServerCsrfTokenRequestHandler and Token Masking Against BREACH

## Learning Objectives

In **Spring Security Reactive (Spring WebFlux)**, CSRF tokens are generated/stored on the server and sent to browsers to protect state-changing HTTP requests. However, if every compressed HTML response echoes the exact same raw CSRF token, the system can expose a **BREACH** surface—a side-channel attack based on compressed payload lengths. Since version 6.0, Spring Security applies **XOR masking** by default to vary the emitted token string while still validating against the same expected value.

This lesson belongs to the **CSRF Protection** context of the **Spring Security – reactive** module. Its main subject is **`ServerCsrfTokenRequestHandler` and token masking against BREACH**.

After this lesson, you will be able to:

1. Explain the difference between CSRF and BREACH, and why HTTPS, SameSite, CORS, and CSRF tokens solve distinct problems.
2. Distinguish **raw expected token**, **masked token**, **random mask**, and **token rotation**, without mistaking differing masked tokens for session token rotation.
3. Understand the responsibilities of `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler`, `ServerCsrfTokenRequestResolver`, and `CsrfToken`.
4. Grasp Spring Security 6.x default behavior: `XorServerCsrfTokenRequestAttributeHandler`, and compare it with `ServerCsrfTokenRequestAttributeHandler`.
5. Access `Mono<CsrfToken>` on `ServerWebExchange` per the reactive contract, without blocking or manually subscribing.
6. Explain the flow of form hidden fields/headers carrying masked tokens, XOR decoding, and comparison with the raw expected token in `WebSession`.
7. Identify the bug when an SPA reads a raw CSRF token from a cookie yet submits it to a handler expecting a masked token.
8. Build a Java 17+ Spring Boot 3.5/Spring Security 6.5 app with `GET /csrf` and `POST /transfer`; test valid/invalid/cross-session tokens, 401/403, and changing masks across requests.
9. Apply XSS defenses, avoid token caching/logging, configure cookies/CORS, and handle logout/timeouts and operational risks.

The hands-on portion uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, Gradle**. API signatures and default behaviors follow the 6.5 line; check your running dependency versions before copying code.

## 1. Threat model: what is CSRF?

Browsers automatically send cookies matching domain/path/SameSite when accessing a site where a user is logged in. An attacker controlling another website can try to make the victim's browser execute a POST to a sensitive endpoint. If the server checks cookies alone, a request not intended by the account owner can still pass authentication.

Hypothetical request example:

```http
POST /transfer HTTP/1.1
Host: bank.example
Cookie: SESSION=<session-id-of-victim>
Content-Type: application/x-www-form-urlencoded

recipient=attacker&amount=100
```

This is an example to understand risk, not a real transaction. Whether a browser sends cross-site cookies also depends on SameSite, request context, and browser policy. CSRF protection solves this by requiring a token that **legitimate clients must fetch from a trusted origin/session and explicitly put into a header or form field**, rather than something the browser auto-attaches when an attack page submits a form.

Common pattern:

```text
GET /form (legitimate website):
  Server loads/generates expected CSRF token R
  Server renders token for frontend
  Browser holds session cookie

POST /transfer:
  Session cookie + token in _csrf field or X-CSRF-TOKEN header
  CsrfWebFilter loads expected R
  Request handler resolves actual token A from request
  A is valid and matches R -> proceed to authentication/authorization/business
  Missing/wrong -> reject, typically HTTP 403
```

**A CSRF token is not an access token.** It neither verifies identity nor grants permissions. Anyone holding a valid CSRF token still needs authentication and authorization if the endpoint requires them.

### 1.1. Why does CSRF still matter with HTTP Basic and cookie-based SPAs?

A browser can auto-send cookies or reuse cached HTTP Basic credentials per its rules. Therefore never deduce "my API is REST/JSON so there is no CSRF". Check whether browsers auto-attach credentials, whether cookie-based login exists, how CORS/SameSite are configured, and which endpoints accept unsafe requests.

For pure server-to-server APIs using `Authorization: Bearer` explicitly supplied by the client in ways browsers never auto-attach, the CSRF threat model differs. Decisions to enable/disable CSRF must rest on **credential and client mechanics**, not labels like REST or reactive.

### 1.2. HTTP methods and CSRF

Spring Security CSRF protects **unsafe** methods by default, typically anything outside GET/HEAD/OPTIONS/TRACE. Those "safe" methods must be designed by the application **not to mutate state**. If a GET performs a delete or transfer, an attacker can trigger it simply by loading a URL, and default CSRF will not block it since GET is considered safe.

Move state-changing actions to POST/PUT/PATCH/DELETE and protect them per contract. Never disable CSRF just because a frontend POST currently returns 403.

## 2. BREACH: leaking secrets via compressed response length

BREACH is an attack class targeting **HTTP response compression**. If an attacker can control part of the data echoed in a response alongside a secret and measure compressed payload sizes across multiple attempts, length differences can reveal information about the secret even over HTTPS.

An HTML form may echo a CSRF token:

```html
<form method="post" action="/transfer">
  <input type="hidden" name="_csrf" value="TOKEN_VALUE">
</form>
```

If `TOKEN_VALUE` is the same fixed raw secret repeated across many compressed responses, it can emit a signal in certain BREACH scenarios. Not every compressed response is automatically exploitable: chosen-plaintext reflection, length observability, and other deployment conditions are also required.

Since Spring Security 6.0, WebFlux **masks tokens exposed in responses** by default to avoid repeating a static raw token string. This **does not replace** evaluating compression risks when other secrets are also reflected.

### 2.1. CSRF and BREACH do not replace each other

| Mechanism | Goal | Does NOT solve on its own |
|---|---|---|
| CSRF synchronizer token | Block unsafe requests not intended by origin/user | XSS, all compression side channels, token leaks via logs |
| XOR masking | Randomize emitted token representation to mitigate BREACH | Does not replace CSRF validation or encrypt tokens |
| HTTPS | Protect content in transit | Does not stop CSRF; does not eliminate compressed size signals |
| SameSite | Curb certain cross-site browser cookie transmissions | Does not replace tokens in all flows |
| CORS | Govern cross-origin JS response reading/certain requests | Not a general anti-CSRF solution |
| CSP/XSS prevention | Reduce risk of same-origin malicious scripts | Does not replace request handlers or repositories |

## 3. Raw tokens, masked tokens, and token rotation

### 3.1. Raw expected token R

`ServerCsrfTokenRepository` handles **generating, saving, and loading the expected CSRF value**. With default WebFlux, `WebSessionServerCsrfTokenRepository` holds the raw token in `WebSession`. The raw token must be random/unpredictable, never derived from a username or fixed value.

Notation example:

```text
Server-side raw expected token: R
  - saved/loaded by repository
  - bound to WebSession or storage strategy
  - reference target when filter validates request
```

R need not be rendered verbatim in every response. While the session stays valid, the repository can continue reusing R across multiple requests.

### 3.2. Masked representation V

`XorServerCsrfTokenRequestAttributeHandler` uses a random mask to create a fresh representation of the token on each exposure as needed.

Intuitive model:

```text
Same session holding raw R:

1st GET /csrf:
  random M1
  masked representation V1 = Encode(M1, M1 XOR R)

2nd GET /csrf:
  random M2
  masked representation V2 = Encode(M2, M2 XOR R)

V1 and V2 usually differ
yet both decode back to R via the handler
```

This is an **explanatory model**, not a promise of specific byte/Base64 layout to reimplement yourself. The framework handles encoding/decoding, sizing, randomness, and malformed input.

### 3.3. Different masks do not mean the raw token rotated

- **Masking** changes the presentation of the same expected token.
- **Rotation** replaces the underlying token in the repository.
- **Invalidation** deletes the expected token, usually tied to logout/session timeout or custom lifecycles.
- **Expiry** can cause old cookies/sessions to no longer map to an expected token.
- Once rotated, old masked tokens no longer match the new expected token; when only re-masked, earlier masked tokens remain valid for the same raw R and session.

Never write a unit test like `assertEquals(csrf1.token(), csrf2.token())` across two independent GETs and treat a difference as a bug. Likewise, never assume a new masked token means the login session rotated.

### 3.4. XOR masking is not encryption

The XOR representation carries the data needed for the handler to recover the raw token; it is not ciphertext requiring a separate secret key to decrypt. Masking merely randomizes the representation per emission to reduce length side channels when secrets are reflected. Never send masked tokens to untrusted origins, log them, or treat masked tokens as "safe to make public".

## 4. Core components of Spring Security WebFlux CSRF

| Component | Responsibility |
|---|---|
| `CsrfWebFilter` | Enforces CSRF protection, exposes token, validates unsafe requests |
| `CsrfToken` | Provides `getToken()`, `getHeaderName()`, `getParameterName()` |
| `DefaultCsrfToken` | Concrete implementation, handy in unit tests |
| `ServerCsrfTokenRepository` | Generates/saves/loads expected raw token for the exchange |
| `WebSessionServerCsrfTokenRepository` | Default repository, binds token to `WebSession` |
| `CookieServerCsrfTokenRepository` | Uses `XSRF-TOKEN` cookie to store raw token |
| `ServerCsrfTokenRequestHandler` | Exposes token via exchange attributes and resolves request tokens |
| `ServerCsrfTokenRequestResolver` | Extracts actual client-submitted token from header/form data |
| `ServerCsrfTokenRequestAttributeHandler` | Plain request handler without XOR masking |
| `XorServerCsrfTokenRequestAttributeHandler` | Default 6+ request handler, masking + unmasking |
| `ServerHttpSecurity.CsrfSpec` | DSL selecting token repository, handler, and CSRF rules |

**Correct packages:** WebFlux uses `org.springframework.security.web.server.csrf`; Servlet uses `org.springframework.security.web.csrf`. Never import Servlet's `XorCsrfTokenRequestAttributeHandler` when configuring `ServerHttpSecurity`.

### 4.1. ServerCsrfTokenRequestHandler contract

The WebFlux interface defines key methods:

```java
// Signature model only; DO NOT redefine the interface.
void handle(ServerWebExchange exchange, Mono<CsrfToken> csrfToken);

Mono<String> resolveCsrfTokenValue(
    ServerWebExchange exchange,
    CsrfToken csrfToken
);
```

`handle` places the token on `ServerWebExchange` for views/controllers and can transform its representation. `resolveCsrfTokenValue` extracts the actual token submitted by the request. These methods belong to `ServerCsrfTokenRequestHandler` and parent `ServerCsrfTokenRequestResolver`; consult your version's Javadoc for default methods and details.

A custom handler must never create arbitrary subscriptions to push tokens into responses. If lazy token materialization is needed, compose the publisher with the response lifecycle. Normally use standard handlers instead of writing custom ones.

### 4.2. Attribute holds Mono<CsrfToken>, not CsrfToken directly

`CsrfWebFilter` exposes `Mono<CsrfToken>` in the attribute keyed by:

```java
CsrfToken.class.getName()
```

Key value is typically `org.springframework.security.web.server.csrf.CsrfToken`. Reading in a WebFlux controller:

```java
Mono<CsrfToken> csrfMono =
    exchange.getAttribute(CsrfToken.class.getName());

return csrfMono.map(csrf -> csrf.getToken());
```

This is a snippet requiring method context, imports, and null handling. Never cast the attribute directly to `CsrfToken`, never call `.block()` on the Netty event loop, and never call `.subscribe()` separately. Views/controllers should return/compose the publisher so WebFlux subscribes.

### 4.3. Repository and handler are two separate strategies

```text
ServerCsrfTokenRepository:
  expected raw R
      |
      v
CsrfWebFilter / Mono<CsrfToken>
      |
      v
ServerCsrfTokenRequestHandler.handle(exchange, tokenMono)
      |
      +-- expose: Xor...handler produces masked V
      |             view/JSON/form sends V to frontend
      |
      +-- unsafe POST:
            Browser sends session Cookie and V (header or _csrf)
            |
            v
            handler.resolveCsrfTokenValue(...)
            |
            v
            decode V into raw actual A
            |
            v
            filter compares A against expected raw R
            |
            +-- match: proceed with request
            +-- mismatch/missing: deny, typically 403
```

Changing the repository does not change masking behavior. Changing the request handler does not change where tokens are stored. This distinction is critical for JS frontends reading raw cookies.

## 5. Journey of GET and POST with masked tokens

### 5.1. Page GET or GET /csrf

An ordinary GET needs no CSRF validation if truly safe, and tokens can be **deferred/lazy** to avoid unnecessary session creation. Once a controller or view **subscribes to `Mono<CsrfToken>`** to emit the token, the repository loads or generates the raw expected token and saves it in `WebSession`/cookies per configuration.

```text
GET /csrf
  -> CsrfWebFilter prepares Mono<CsrfToken>
  -> request handler puts publisher in exchange attribute
  -> controller maps publisher to JSON/header/view model
  -> subscription actually demands token
  -> repository loads/generates R
  -> XOR handler exposes V = masked(R)
  -> response returns V
  -> session cookie sent when session has state to persist
```

A public `GET /csrf` can create a `WebSession` even when the user **is not logged in**; having a session/cookie does not mean the user is authenticated. Conversely, a public GET that does not read the token need not create CSRF state.

### 5.2. Same-session POST, masked token in header

```http
POST /transfer HTTP/1.1
Host: app.example
Cookie: SESSION=<current-session-id>
Authorization: Basic <credentials>
X-CSRF-TOKEN: <masked-token-from-same-session>
Content-Type: application/json

{}
```

This is a sample request, not real credentials/tokens. `CsrfWebFilter` loads expected raw R from the repository, the handler unmasks actual A, and the filter compares A with R. A valid token **only** lets the POST proceed past CSRF; authentication/authorization can still reject it.

### 5.3. HTML form

Sample form:

```html
<form method="post" action="/transfer">
  <input type="hidden" name="_csrf" value="MASKED_FROM_SERVER">
  <button type="submit">Confirm</button>
</form>
```

`MASKED_FROM_SERVER` is purely illustrative. Real forms must render the value from the CSRF token exposed by Spring Security for the **same session**. Thymeleaf integrated with `CsrfRequestDataValueProcessor` can automatically inject fields into unsafe-method forms when configured properly. When rendering manually, read `Mono<CsrfToken>` and HTML-escape attributes.

Never put tokens in URLs, as URLs leak into logs, browser history, analytics, and referrers.

### 5.4. Missing cookie or different session is still an invalid token

```text
GET /csrf with session A cookie -> masked V_A

POST /transfer:
  session B cookie
  token V_A
  -> unmasked to raw R_A
  -> expected in B's repository is R_B
  -> R_A != R_B -> deny
```

Never fix this by letting the server accept any syntactically valid masked token; it must match the expected raw token of the receiving request's context.

## 6. ServerCsrfTokenRequestAttributeHandler and XorServerCsrfTokenRequestAttributeHandler

Spring Security 5.8 used `ServerCsrfTokenRequestAttributeHandler` as default; since **6.0**, WebFlux switched to `XorServerCsrfTokenRequestAttributeHandler` to mitigate BREACH.

| Feature | Plain handler | XOR handler |
|---|---|---|
| Class | `ServerCsrfTokenRequestAttributeHandler` | `XorServerCsrfTokenRequestAttributeHandler` |
| Token exposure | Raw token representation | Masked representation |
| Token resolution | Plain header/form value | Unmasks header/form value |
| Prevents static raw token reflection via compression | No masking | Random masking |
| 5.8 default | Yes | No |
| 6.0+ default | No | **Yes** |
| With SPA raw cookie headers | Compatible when configured | Watch out for raw/masked mismatch |
| For server-rendered HTML forms | Works but lacks mitigation | Prefer keeping default |

The XOR handler in Spring Security 6.x **needs no extra config** if using default CSRF. To declare it explicitly:

```java
// Snippet inside @Bean SecurityWebFilterChain:
return http
    .csrf(csrf -> csrf
        .csrfTokenRequestHandler(
            new XorServerCsrfTokenRequestAttributeHandler()))
    .build();
```

If forced to switch back to plain:

```java
// Intentional opt-out of BREACH masking; NOT a default 403 fix.
.csrf(csrf -> csrf
    .csrfTokenRequestHandler(
        new ServerCsrfTokenRequestAttributeHandler()))
```

**Do not do this solely because the frontend sent the wrong token.** Disabling XOR can allow a static raw token to be reflected in compressed responses. Review integration and threat model before altering protections.

## 7. SPA raw CSRF cookies are an easy trap

### 7.1. CookieServerCsrfTokenRepository

`CookieServerCsrfTokenRepository` writes the `XSRF-TOKEN` cookie and reads client-submitted values from header `X-XSRF-TOKEN` or form parameter `_csrf` by convention. `withHttpOnlyFalse()` lets JavaScript read the raw cookie.

Sample configuration:

```java
// Snippet choosing storage only; incomplete for SPAs on its own.
.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

This is a trade-off: if the frontend **does not need** JavaScript to read the cookie, keep `HttpOnly` to minimize access surface. Cookie tokens do not replace authentication cookies, and `withHttpOnlyFalse()` does not automatically enable the right request resolver for every SPA.

### 7.2. Why can a raw header get 403 under the XOR default?

A JS client reads raw `XSRF-TOKEN` from the cookie and puts it in `X-XSRF-TOKEN`. If the request handler assumes the actual value is **masked**, it routes the header through unmasking rather than "raw token from repository". Raw and masked are two different representations; requests can be rejected even though the browser cookie holds the exact raw token expected by the repository.

To support both, design consistently:

- HTML forms: XOR-masked field to mitigate BREACH reflection.
- SPA raw cookie header: appropriate request resolver accepting raw headers and comparing with raw expected tokens.
- Alternatively, if using a `GET /csrf` endpoint returning masked tokens in JSON, the frontend can send that exact **masked value** in the matching header without reading a raw XSRF cookie.
- Refresh tokens per lifecycle after login/logout, session timeout, or reset.
- Never disable CSRF or BREACH solely to make a POST succeed.
- CORS must restrict origins and credentialed access; if an attacker can read the token, CSRF protection weakens.

**Never copy Servlet's `SpaCsrfTokenRequestHandler` verbatim**: Spring Servlet uses `HttpServletRequest`/`Supplier<CsrfToken>`, whereas WebFlux uses `ServerWebExchange`/`Mono<CsrfToken>`. In a custom reactive handler, never manually `subscribe()` to the deferred `Mono` inside `handle`.

### 7.3. A simpler option for SPAs

With a session-based WebFlux backend, a same-origin `GET /csrf` endpoint can return the **masked** token in JSON; the client keeps the session cookie and sends that value in a header on POSTs. The demo below illustrates this exact flow.

The token endpoint needs proper cache policy (usually `no-store`), TLS, and protection from cross-origin attacker reads. When tokens/sessions expire, clients fetch a new one, yet **must never infinitely auto-retry POSTs that may have caused side effects**.

## 8. Runnable Java 17+ demo: Spring Boot 3.x and Security 6.x

The app provides:

- `GET /public`: public, no CSRF required.
- `GET /csrf`: reads masked token via `Mono<CsrfToken>` from request attribute, returning JSON with header/form field metadata.
- `POST /transfer`: requires HTTP Basic authentication and a CSRF token; simulates a mutation with an in-memory counter.
- `WebSessionServerCsrfTokenRepository`: stores expected raw token.
- `XorServerCsrfTokenRequestAttributeHandler`: exposes masked token, unmasks on submission.
- Integration tests keeping the same cookie to verify masked token round-trips.

**No real financial transactions occur.** This is a security demo for learning request flows.

### 8.1. Project creation and dependencies

Generate a Gradle Groovy project via [Spring Initializr](https://start.spring.io/), selecting Java 17+, Spring Boot 3.5.x, and dependencies Spring Reactive Web, Spring Security, Spring Boot Starter Test, Spring Security Test, and Reactor Test.

`dependencies` section of `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is only the dependencies block; keep plugins, repositories, Java toolchain, and Gradle wrapper generated by Initializr. Do not add `spring-boot-starter-web`: with both MVC and WebFlux starters present, Spring Boot 3.x typically defaults to Servlet.

Layout:

```text
src/main/java/demo/csrfxor/
  CsrfXorApplication.java
  SecurityConfig.java
  CsrfController.java
  TransferController.java
src/test/java/demo/csrfxor/
  CsrfXorIntegrationTests.java
  XorHandlerTests.java
```

### 8.2. CsrfXorApplication.java

```java
package demo.csrfxor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfXorApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfXorApplication.class, args);
    }
}
```

### 8.3. SecurityConfig.java

```java
package demo.csrfxor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public", "/csrf")
                    .permitAll()
                .pathMatchers(HttpMethod.POST, "/transfer")
                    .authenticated()
                .anyExchange().denyAll())
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository())
                .csrfTokenRequestHandler(
                    new XorServerCsrfTokenRequestAttributeHandler()))
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
```

Explanation:

1. `ServerHttpSecurity`, `SecurityWebFilterChain`, and `@EnableWebFluxSecurity` belong to WebFlux.
2. `/csrf` is `permitAll` so same-origin clients can obtain tokens before login; it does not mean arbitrary third-party origins can read the response via CORS.
3. `WebSessionServerCsrfTokenRepository` holds the expected raw token in the session.
4. `XorServerCsrfTokenRequestAttributeHandler` is the Security 6 default, declared explicitly for clarity.
5. HTTP Basic supplies authentication for the demo; Base64 is not encryption, so production must run HTTPS.
6. `POST /transfer` requires both Basic credentials and a CSRF token. A `403` from CSRF differs from a `401` due to missing authentication.
7. CSRF **is not disabled**. `formLogin` is disabled so API endpoints do not redirect to an HTML page when Basic auth is missing.
8. In-memory credentials are sample data; account passwords are hashed by `PasswordEncoder` and example passwords must never be used in production.

### 8.4. CsrfController.java: returning the masked token

```java
package demo.csrfxor;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CsrfController {

    public record TokenView(
            String headerName,
            String parameterName,
            String token) {
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/csrf")
    public Mono<TokenView> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter did not expose a CSRF token"));
        }

        exchange.getResponse().getHeaders()
            .setCacheControl("no-store");

        return token.map(t -> new TokenView(
            t.getHeaderName(),
            t.getParameterName(),
            t.getToken()));
    }
}
```

**Key learning point:** `exchange.getAttribute(...)` returns the publisher placed on the exchange by the handler. `token.map(...)` is subscribed to by WebFlux and triggers generating/loading the expected raw token, persisting session state, and returning the masked representation from the XOR handler. Never `block()` or manually `subscribe()` in controllers.

A `GET /csrf` endpoint returns a security-sensitive value without requiring authentication: only legitimate same-origin clients should read it, never shared caches or unconditionally open CORS. `Cache-Control: no-store` reduces browser/proxy caching risk; production also requires XSS protection, TLS, and careful logging.

### 8.5. TransferController.java: observable side effect

```java
package demo.csrfxor;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class TransferController {

    private final AtomicInteger completed = new AtomicInteger();

    public record TransferResult(String status, int sequence) {
    }

    @PostMapping("/transfer")
    public Mono<TransferResult> transfer() {
        return Mono.fromSupplier(() ->
            new TransferResult(
                "accepted",
                completed.incrementAndGet()));
    }

    public int completedCount() {
        return completed.get();
    }

    // Internal JUnit helper, not exposed as an HTTP endpoint.
    public void resetForTests() {
        completed.set(0);
    }
}
```

The counter increments **only when** the request passes CSRF, authentication, and authorization and the controller is subscribed to. It is not a real transaction and is unsuitable for financial products. Tests verify the counter stays at 0 when the token is missing or invalid.

### 8.6. Running the app

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Verify the public route:

```bash
curl -i http://localhost:8080/public
```

Expected body:

```text
public
```

Fetch masked token and save cookie for subsequent requests:

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
```

The `GET /csrf` response returns JSON with `headerName`, `parameterName`, and `token`; the server may emit the `SESSION` cookie if the repository persisted state. Never put real tokens/cookies into public logs. To POST with curl, send **the exact masked value from JSON** in the matching header along with the cookie from the file; otherwise CSRF returns 403. Using `WebTestClient` below automates these steps without copying tokens into shell history.

## 9. Integration tests: masked tokens across two HTTP requests

Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `WebTestClient` to test the real flow through WebFlux filters. Tests **do not fabricate fake tokens**; they retrieve tokens issued by the endpoint, keep the session cookie, and resend the masked token properly.

Create `src/test/java/demo/csrfxor/CsrfXorIntegrationTests.java`:

```java
package demo.csrfxor;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfXorIntegrationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    TransferController transfer;

    @BeforeEach
    void reset() {
        transfer.resetForTests();
    }

    private EntityExchangeResult<CsrfController.TokenView> initial() {
        return client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(CsrfController.TokenView.class)
            .returnResult();
    }

    private EntityExchangeResult<CsrfController.TokenView> again(
            String cookie) {
        return client.get().uri("/csrf")
            .cookie("SESSION", cookie)
            .exchange()
            .expectStatus().isOk()
            .expectBody(CsrfController.TokenView.class)
            .returnResult();
    }

    private String cookie(
            EntityExchangeResult<CsrfController.TokenView> result) {
        ResponseCookie c =
            result.getResponseCookies().getFirst("SESSION");
        assertNotNull(c);
        return c.getValue();
    }

    private CsrfController.TokenView token(
            EntityExchangeResult<CsrfController.TokenView> result) {
        CsrfController.TokenView v = result.getResponseBody();
        assertNotNull(v);
        assertNotNull(v.token());
        assertNotNull(v.headerName());
        return v;
    }

    @Test
    void publicGetWorksWithoutCsrf() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void csrfEndpointExposesMetadataAndSession() {
        var result = initial();
        var v = token(result);

        assertNotNull(cookie(result));
        assertEquals("X-CSRF-TOKEN", v.headerName());
        assertEquals("_csrf", v.parameterName());
    }

    @Test
    void missingTokenBlocksMutationEvenWithCredentials() {
        client.post().uri("/transfer")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void maskedHeaderWithSameSessionAllowsPost() {
        var result = initial();
        var v = token(result);
        String session = cookie(result);

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v.headerName(), v.token());
            })
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted")
            .jsonPath("$.sequence").isEqualTo(1);

        assertEquals(1, transfer.completedCount());
    }

    @Test
    void maskedTokenWithoutSessionIsForbidden() {
        var v = token(initial());

        client.post().uri("/transfer")
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v.headerName(), v.token());
            })
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void tokenFromDifferentSessionIsForbidden() {
        var sessionA = initial();
        var sessionB = initial();

        var tokenA = token(sessionA);
        String cookieB = cookie(sessionB);

        client.post().uri("/transfer")
            .cookie("SESSION", cookieB)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(tokenA.headerName(), tokenA.token());
            })
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void twoMasksInSameSessionAreBothValid() {
        var first = initial();
        String session = cookie(first);
        var v1 = token(first);
        var v2 = token(again(session));

        assertNotEquals(v1.token(), v2.token());

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v1.headerName(), v1.token());
            })
            .exchange()
            .expectStatus().isOk();

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v2.headerName(), v2.token());
            })
            .exchange()
            .expectStatus().isOk();

        assertEquals(2, transfer.completedCount());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() {
        var result = initial();
        var v = token(result);
        String session = cookie(result);

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .header(v.headerName(), v.token())
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(0, transfer.completedCount());
    }
}
```

**8 test cases** cover public GET, CSRF GET, missing token, valid token, missing session, different session, two different masked values in the same session, and valid CSRF without authentication. Tests assert both HTTP responses and the counter, not just status codes.

### 9.1. Note on session cookies in tests

In default Spring WebFlux, the session cookie is typically named `SESSION`. If your project customizes `WebSessionIdResolver` or cookie names, read the actual cookie name from the response. Tests retain the cookie from `GET /csrf` so the server can locate the expected raw token.

`twoMasksInSameSessionAreBothValid` uses `assertNotEquals` on random masks: the probability of two masked strings colliding is minuscule, though theoretically non-zero. Never use a weak fixed RNG in production just to make tests deterministic.

### 9.2. Why not use mutateWith(csrf()) for everything?

`SecurityMockServerConfigurers.csrf()` is helpful for general security testing. Here, however, the goal is verifying **real masked tokens from `ServerCsrfTokenRequestHandler`**, cookie round-trips, and POST resolution. If you only inject tokens via a test helper, frontend bugs like sending raw cookie values to an XOR resolver can go unnoticed. That is why integration tests fetch tokens via the endpoint rather than mocking them.

## 10. Unit tests for the XOR handler and plain handler

Create `src/test/java/demo/csrfxor/XorHandlerTests.java`:

```java
package demo.csrfxor;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.DefaultCsrfToken;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class XorHandlerTests {

    private final CsrfToken raw =
        new DefaultCsrfToken(
            "X-CSRF-TOKEN", "_csrf", "unit-test-raw-value");

    private String render(
            XorServerCsrfTokenRequestAttributeHandler handler) {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/form").build());

        handler.handle(exchange, Mono.just(raw));

        Mono<CsrfToken> exposed =
            exchange.getAttribute(CsrfToken.class.getName());
        assertNotNull(exposed);

        // Unit test only; NEVER call block() on the Netty event loop.
        CsrfToken value = exposed.block();
        assertNotNull(value);
        return value.getToken();
    }

    @Test
    void xorRepresentationChangesEachTime() {
        var handler =
            new XorServerCsrfTokenRequestAttributeHandler();

        String first = render(handler);
        String second = render(handler);

        assertNotEquals(raw.getToken(), first);
        assertNotEquals(first, second);
    }

    @Test
    void resolverRecoversRawFromMaskedHeader() {
        var handler =
            new XorServerCsrfTokenRequestAttributeHandler();
        String masked = render(handler);

        var post = MockServerWebExchange.from(
            MockServerHttpRequest.post("/transfer")
                .header("X-CSRF-TOKEN", masked)
                .build());

        StepVerifier.create(
                handler.resolveCsrfTokenValue(post, raw))
            .expectNext(raw.getToken())
            .verifyComplete();
    }

    @Test
    void plainHandlerExposesUnmaskedToken() {
        var handler =
            new ServerCsrfTokenRequestAttributeHandler();
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/form").build());

        handler.handle(exchange, Mono.just(raw));

        Mono<CsrfToken> exposed =
            exchange.getAttribute(CsrfToken.class.getName());
        assertNotNull(exposed);
        CsrfToken value = exposed.block();
        assertNotNull(value);

        assertEquals(raw.getToken(), value.getToken());
    }
}
```

Unit tests verify public behavior: XOR produces masked values differing from raw, masking is randomized, masked headers resolve back to expected raw values, and the plain handler exposes raw values. Do not assert internal Base64 structures, as the framework may change implementations. `block()` is used only in unit tests, never inside reactive handlers.

Run:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Expected: **11 tests** defined (8 integration + 3 unit) in the project configuration above. This is an expectation from the code, **not confirmation that Gradle was executed**. If adapter versions differ, inspect actual responses/cookies, dependency tree, request handlers, and test logs, and adjust based on contract rather than blindly changing expected statuses.

## 11. Common errors after upgrading Spring Security

| Symptom | Possible cause | Resolution |
|---|---|---|
| GET form returns a longer token than before | XOR representation includes mask/encoding | Keep the string intact; never truncate tokens |
| Different token on two GETs in the same session | Random masking per exposure | Expected behavior; do not treat as rotation |
| SPA raw XSRF header POST returns 403 after upgrade | Request handler unmasks while client sends raw | Use a compatible resolver or send masked tokens |
| POST missing token returns 403 | Blocked by CSRF filter | Fetch token for the right session; send header/form field |
| Valid HTTP Basic yet POST returns 403 | CSRF mismatch/missing or insufficient authority | Separate CSRF 403 from authorization 403 debugging |
| Valid token without auth returns 401 | CSRF does not authenticate users | Send valid credentials over HTTPS |
| Token from session A with cookie B gets 403 | Expected raw tokens differ | Keep cookie and token in the same session |
| JSON `/csrf` has no token | Filter not in chain or publisher never materialized | Check chain, exchange attribute, and reactive composition |
| Cookie readable yet request fails | Header name, raw/masked, CORS, session, or token expiry | Align repository and handler |
| Disabling CSRF makes tests pass | Removed the protection layer | Never treat as a fix; fix the token flow |
| Disabling XOR makes POST succeed | Removed BREACH mitigation | Align client/server representation instead of disabling protection |
| Fetching `CsrfToken` via direct cast | Attribute holds `Mono<CsrfToken>` | Compose publisher; never cast |
| `block()` in controller | Risks blocking the event loop | Return `Mono` |
| CDN cache serves JSON CSRF tokens | Shared cache ignores user/session boundaries | `no-store`, check proxies |
| After logout/login old token gets 403 | Raw token was cleared/rotated | Fetch fresh token per lifecycle |
| Multipart request with token in body fails | Different default resolver/multipart handling | Evaluate `tokenFromMultipartDataEnabled` and prefer headers with JS |
| Copied Servlet's `XorCsrfTokenRequestAttributeHandler` | Wrong API stack | Use WebFlux's `XorServerCsrfTokenRequestAttributeHandler` |

### 11.1. Safe logs for debugging

Log request ID, sanitized HTTP path, method, token source (header/form), categorized missing/invalid reason, and status. Never log **raw tokens, masked tokens, Authorization, Cookies, session IDs**, or full request bodies. Use test environments and browser Developer Tools to inspect cookies/headers when needed, and never paste real credentials/tokens into tickets.

### 11.2. 403 has multiple causes

A `403` on POST is not always CSRF; it can be missing role/permission after CSRF passes. Conversely, `401` can appear when the CSRF token is valid yet authentication is missing. Debug along the pipeline: CSRF validation, authentication, authorization, and handler. Looking at the HTTP status alone is insufficient.

## 12. Cookie flags, CORS, XSS, and compression

### 12.1. Cookies

Session cookies should set `Secure` over HTTPS, `HttpOnly`, and appropriate `SameSite`. `SameSite` helps curb certain cross-site flows, but never replaces CSRF tokens in all scenarios. The `XSRF-TOKEN` cookie may need to be JavaScript-readable if using the raw-cookie SPA pattern; `HttpOnly=false` is an intentional trade-off—do not enable it unnecessarily.

### 12.2. CORS

CORS does not check CSRF, and CSRF does not replace CORS. If a server allows untrusted origins to read `GET /csrf` with credentials, attackers can grab tokens and weaken protection. Strictly allowlist origins, methods, headers, and credentials; never reflect arbitrary `Origin` headers and expose tokens.

### 12.3. XSS

If an attacker executes same-origin JavaScript (XSS), the script can call legitimate `GET /csrf` and use the token. CSRF protection does not stop XSS. Maintain escaping, CSP, dependency hygiene, third-party script restrictions, and review untrusted data rendering.

### 12.4. Session expiry and refresh

Raw expected tokens can be removed on session expiry/logout/login lifecycles, or rotated by custom repositories. SPAs should fetch fresh tokens after relevant state transitions. However, CSRF tokens are not idempotency keys; network-failed POSTs should not automatically retry indefinitely if the mutation may already have succeeded.

### 12.5. Response compression

Masking curbs stable CSRF secret reflection in HTML/JSON, yet does not protect every rendered secret. If your app reflects API keys, PII, or session-specific secrets alongside attacker-controlled plaintext in compressed responses, assess the broader BREACH threat model. HTTPS remains essential, yet does not eliminate all length side channels.

## 13. Exercises with answers

### Exercise 1. Do two differing masked tokens mean the token expired?

A user calls `GET /csrf` twice in the same `WebSession`: `V1 != V2`. Can `V1` still be used in a POST?

**Answer:** Yes, provided the expected raw token in the repository has not changed and the session remains valid. XOR generates a fresh mask per exposure; both representations decode to the same raw token.

### Exercise 2. Does changing masks mean the session ID changed?

**Answer:** No. Masking changes only the CSRF token representation. Session IDs and raw expected tokens follow separate lifecycles; never infer session changes from masked strings.

### Exercise 3. Why not send a raw XSRF cookie to an XOR resolver?

**Answer:** Because the handler decodes masked representations rather than comparing plain raw strings directly. Client and server must agree on resolution; either use a compatible handler for raw headers or send the server-exposed masked token.

### Exercise 4. Does having a valid token grant access to resources?

**Answer:** No. CSRF tokens replace neither authentication nor authorization. APIs can still return 401 or 403 if the user lacks credentials/roles.

### Exercise 5. Why can GET /csrf create a SESSION cookie before login?

**Answer:** The endpoint must materialize the token; the `WebSession` repository may start a session to store the raw token. An existing session does not mean the user is authenticated.

### Exercise 6. Why is CSRF protection still required even with HTTPS enabled?

**Answer:** HTTPS protects payloads in transit, yet browsers can still auto-send cookies on requests triggered by another site per policy; CSRF tokens address that threat model.

### Exercise 7. Why is XOR not encryption?

**Answer:** Masking creates randomized representations to reduce compression side channels; the masked token can be decoded back to raw by the handler without a separate cryptographic decryption secret. It does not make tokens safe to give to attackers.

### Exercise 8. Can public GET /csrf be cached by a CDN?

**Answer:** It should not be. Tokens are bound to sessions/contexts; shared caches could hand out tokens across sessions and leak data. Use `no-store` and review proxies, CORS, and logs.

### Exercise 9. What must be tested when using an SPA cookie token?

**Answer:** Reading raw tokens from cookies, header names, compatible resolver handling, masked forms continuing to work, cookie refresh after login/logout, 403 on different sessions, 403 on missing tokens, and Origin/CORS policies blocking attacker token reads.

### Exercise 10. Why not disable BREACH mitigation to fix 403?

**Answer:** Switching to the plain handler can echo static raw secrets into compressed responses. Fix how the frontend sends tokens or design a controlled custom resolver instead of silently removing mitigation.

### Exercise 11. Is a 403 error necessarily CSRF?

**Answer:** No. It could be authorization denying a missing role. Check the CSRF filter, authentication manager, and authorization rules; test with a valid CSRF token to isolate permission errors.

### Exercise 12. Should you manually subscribe to Mono<CsrfToken> inside a handler?

**Answer:** Avoid it. Creating a detached subscription disconnects from the response lifecycle/error handling/cancellation and causes session cookie issues. Compose the publisher into the WebFlux handler response.

## 14. Technical pre-production checklist

- [ ] Inbound stack is genuinely Spring WebFlux; uses `ServerHttpSecurity` and `.web.server.csrf` packages.
- [ ] Confirmed Spring Security version and aware of the 6.0+ XOR default.
- [ ] CSRF enforced on unsafe methods and browser login/logout flows per threat model.
- [ ] Repository safely stores/loads expected raw tokens per session/cookie strategy.
- [ ] Views/forms obtain masked values from the request handler rather than echoing raw tokens directly.
- [ ] SPA raw cookie headers use a compatible resolver or clients fetch from a masked token endpoint.
- [ ] Never hand-roll XOR, and never use weak/fixed-seed RNGs in production.
- [ ] Never block or manually subscribe to `Mono<CsrfToken>` inside handlers.
- [ ] Token endpoints and HTML forms are excluded from shared caches and public logs.
- [ ] HTTPS, `Secure`/`HttpOnly`/`SameSite`, and tight cookie domain/path configured.
- [ ] CORS restricts which origins may read tokens with credentials.
- [ ] XSS/CSP/HTML escaping controlled; CSRF never substitutes for XSS defense.
- [ ] Tested differing masked tokens in the same session, confirming POST succeeds with each.
- [ ] Tested missing tokens, wrong sessions, expired tokens, and login/logout refreshes.
- [ ] Tested authentication/roles separately; CSRF tokens grant zero privileges.
- [ ] For multipart, evaluated body tokens vs. early file parsing and preferred custom headers with JS.
- [ ] Never pass CSRF tokens in query strings.
- [ ] Never blindly retry non-idempotent mutations when tokens expire.
- [ ] Reviewed response compression if any other secrets besides CSRF tokens are reflected.

## 15. Quick summary

```text
Repository (WebSessionServerCsrfTokenRepository):
  stores expected RAW token R

CsrfWebFilter:
  exposes Mono<CsrfToken> via ServerWebExchange attribute

XorServerCsrfTokenRequestAttributeHandler:
  generates masked representation V1 = mask(R)
  another request can emit V2 != V1
  default since Spring Security 6+

Browser:
  retains session cookie
  sends V1 or V2 in _csrf form field or X-CSRF-TOKEN header

Request handler resolution:
  unmasks V -> raw actual A
  CsrfWebFilter compares A with expected R
  match    -> continue
  mismatch -> reject, typically 403

ServerCsrfTokenRequestAttributeHandler:
  plain representation, no XOR BREACH masking

SPA raw XSRF cookie:
  not compatible out-of-the-box with masked resolver
  requires aligned frontend/handler strategy

CSRF != authentication
XOR masking != encryption
BREACH mitigation != complete response compression safety
```

**Core message:** `ServerCsrfTokenRequestHandler` defines how tokens are **presented to clients** and **resolved from incoming requests**. `XorServerCsrfTokenRequestAttributeHandler` uses randomness so repeated token reflections differ, mitigating BREACH risk, while the server still validates against the **raw expected token** managed by the repository.

## Official References

- [Spring Security 6.5 — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security 6.5 — XorServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security 6.5 — ServerCsrfTokenRequestHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestHandler.html)
- [Spring Security — ServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security — CsrfWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html)
- [Spring Security — WebSessionServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html)
- [Spring Security — CookieServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html)
- [Spring Security — WebFlux testing CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [BREACH background](https://breachattack.com/)
