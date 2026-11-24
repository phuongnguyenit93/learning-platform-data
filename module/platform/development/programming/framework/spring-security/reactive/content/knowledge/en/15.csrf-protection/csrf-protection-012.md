# Scoping CSRF Exemptions with Matchers and Verifying with Tests

## 1. Problem to solve

In Spring Security reactive (Spring WebFlux), CSRF protection is enabled by default for HTTP requests capable of mutating state. An application using session cookies or HTTP Basic in browsers may require CSRF tokens on POST, PUT, PATCH, and DELETE. At the same time, the same application sometimes must receive webhooks from a third-party provider that do not use user session cookies and instead verify an HMAC signature over the raw request body.

Suppose there are two requests:

~~~text
POST /api/notes
  Logged-in user's browser
  Browser may auto-send session cookie / Basic credentials
  -> Must keep CSRF token and authentication.

POST /integrations/webhook/receive
  Partner server sending webhook
  No user session cookie used
  Has dedicated HMAC signature and replay policy
  -> Justified to exempt CSRF if scope is tightly bounded.
~~~

A **dangerous mistake** is disabling CSRF across the entire security chain just because the webhook returned 403:

~~~java
// ANTI-PATTERN. Never copy into an app with browser sessions!
http.csrf(csrf -> csrf.disable());
~~~

That call strips CSRF protection from login/logout, forms, and APIs using ambient credentials in the same chain. The right approach is designing a conditional matcher:

~~~text
CSRF_REQUIRED = UNSAFE_HTTP_METHOD AND NOT(EXACT_WEBHOOK_POST)
~~~

That is, **exempt only exact POST to the exact webhook URL**, while every other request keeps the default CSRF policy.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the boundary among CSRF, authentication, authorization, and webhook signature verification.
2. Use `ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(...)` in WebFlux instead of disabling CSRF globally.
3. Combine `CsrfWebFilter.DEFAULT_CSRF_MATCHER`, `AndServerWebExchangeMatcher`, `NegatedServerWebExchangeMatcher`, and `ServerWebExchangeMatchers.pathMatchers(...)` accurately.
4. Scope exemptions by both HTTP method and exact path without spilling into child paths or PUT/PATCH/DELETE.
5. Verify matcher outcomes directly with `StepVerifier` and verify HTTP behavior with `WebTestClient`.
6. Keep CSRF for browser POSTs, login, and logout while authenticating webhooks separately via HMAC.
7. Spot configuration bugs across multiple security chains, overly broad matchers, misleading 403 test results, and production security requirements.

## 2. When is CSRF genuinely needed?

CSRF (Cross-Site Request Forgery) happens when an external page causes a victim's browser to send a state-changing request to an app where the victim is logged in. If the browser can auto-carry credentials (such as cookies/sessions or cached HTTP Basic), a server relying solely on credentials may mistake a forged request for the victim's intentional action.

~~~text
Victim is logged into app.example
    │
    ▼
Browser holds app.example session cookie
    │
    ▼
Victim opens attacker.example
    │
    ▼
Attacker page submits POST form to app.example/update-email
    │
    ▼
Browser may auto-send cookie per SameSite and cookie policy
    │
    ▼
Backend only checks "valid session exists" -> unintended mutation
~~~

To defend, a session-based app can require a secret CSRF token not auto-attached by browsers to simple cross-site requests, paired with SameSite, origin checks, and supporting defenses.

**The deciding factor is not labels like "REST API" or "JSON API", but how authentication is delivered.**

| Scenario | Basis for CSRF evaluation |
| --- | --- |
| HTML login page with session cookies | Usually must keep CSRF on unsafe actions |
| SPA calling APIs with session cookies | Browser may auto-attach cookies; needs CSRF or proven equivalent defense |
| HTTP Basic in browsers | Browser may auto-send Basic credentials; never disable CSRF by default |
| API using only Bearer tokens explicitly attached in headers by JS/app | Classic CSRF risk differs; still inspect tokens, XSS, and any cookie endpoints |
| Server-to-server webhook using HMAC/mTLS, zero ambient browser auth | May exempt CSRF on exact endpoint, yet requires dedicated verification and replay protection |
| Public POST with `permitAll()` | Does not auto-exempt CSRF; authorization and CSRF are separate concerns |

CSRF tokens **do not replace** authentication/authorization, nor do they stop XSS on their own. If an attacker achieves XSS in the app's origin, scripts can read tokens rendered on the page or send same-origin requests. Defend against XSS independently rather than skipping output encoding just because CSRF tokens exist.

### 2.1. Safe HTTP methods and the rule that GET must cause zero side effects

By default, `CsrfWebFilter.DEFAULT_CSRF_MATCHER` treats GET, HEAD, OPTIONS, and TRACE as methods requiring no CSRF token. Other methods, including POST, PUT, PATCH, and DELETE, are subject to verification.

That relies on the assumption that GET/HEAD do not mutate business state. If you write `GET /delete-account`, that GET can be triggered via links, images, or navigations without any token. The fix is changing the endpoint design to the proper method, **not** adding a matcher exception to dodge errors.

## 3. Do not confuse four distinct matchers and conditions

Spring Security WebFlux has several APIs taking `ServerWebExchangeMatcher`, each answering a different question:

| API | What it actually asks |
| --- | --- |
| `ServerHttpSecurity.securityMatcher(...)` | Should this `SecurityWebFilterChain` be selected for the request? |
| `ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(...)` | For a request already inside this chain, is a CSRF token required? |
| `AuthenticationWebFilter.setRequiresAuthenticationMatcher(...)` | Should this specific authentication filter attempt to authenticate the request? |
| `authorizeExchange(...).pathMatchers(...).permitAll()/authenticated()/hasAuthority(...)` | Is the request authorized for this route by authentication/authorities? |

A `permitAll()` endpoint can still be blocked on POST by the CSRF filter if a token is missing. A CSRF-exempt endpoint can still be rejected 401 by `AuthenticationWebFilter` or 403 by authorization. A webhook marked `permitAll()` to skip user login must still run a dedicated HMAC verifier before any side effect occurs.

### 3.1. WebFlux APIs differ from Servlet APIs

Reactive WebFlux uses:

~~~java
org.springframework.security.config.web.server.ServerHttpSecurity
org.springframework.security.web.server.SecurityWebFilterChain
org.springframework.security.web.server.csrf.CsrfWebFilter
org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher
~~~

Servlet Spring MVC typically uses `HttpSecurity`, `CsrfFilter`, and `RequestMatcher`. Never copy Servlet's `ignoringRequestMatchers(...)` into `ServerHttpSecurity.CsrfSpec` assuming the same helper exists in the reactive DSL. In Spring Security WebFlux 6.x, use `requireCsrfProtectionMatcher(...)` to supply the protection matcher.

## 4. Exact expression using two independent conditions

Define:

- `U(r)`: request `r` has an unsafe method per `CsrfWebFilter.DEFAULT_CSRF_MATCHER`.
- `W(r)`: request `r` is strictly `POST /integrations/webhook/receive`.
- `C(r)`: request `r` must carry a CSRF token.

We want:

~~~text
C(r) = U(r) AND NOT W(r)

If GET/HEAD/OPTIONS/TRACE:
  U(r) = false
  -> C(r) = false for every URL.

If POST/PUT/PATCH/DELETE:
  U(r) = true
  -> C(r) = false solely when W(r) = true.
~~~

In Spring Security WebFlux:

~~~java
ServerWebExchangeMatcher webhookPost =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.POST, "/integrations/webhook/receive");

ServerWebExchangeMatcher csrfRequired =
    new AndServerWebExchangeMatcher(
        CsrfWebFilter.DEFAULT_CSRF_MATCHER,
        new NegatedServerWebExchangeMatcher(webhookPost)
    );

return http
    .csrf(csrf -> csrf.requireCsrfProtectionMatcher(csrfRequired))
    .build();
~~~

This is an **extracted config fragment**, not a standalone class. The full project below provides imports and beans.

Role of each piece:

1. `ServerWebExchangeMatchers.pathMatchers(HttpMethod.POST, "...")` matches strictly **one method + one path**.
2. `NegatedServerWebExchangeMatcher(webhookPost)` evaluates to false strictly on the exempted request.
3. `AndServerWebExchangeMatcher` enforces CSRF when the request is both an unsafe method and **not** in the exemption.
4. `requireCsrfProtectionMatcher(...)` sets the **entire predicate** deciding CSRF enforcement, rather than appending an exception to the default. Thus `DEFAULT_CSRF_MATCHER` must be included in the AND expression.
5. Safe methods still evaluate to false because `U=false`.
6. All other POSTs still require tokens, even if the user is authenticated or the route is `permitAll()`.

### 4.1. Why not use OR?

~~~java
// ANTI-PATTERN: syntactically valid, logically wrong.
new OrServerWebExchangeMatcher(
    CsrfWebFilter.DEFAULT_CSRF_MATCHER,
    new NegatedServerWebExchangeMatcher(webhookPost)
);
~~~

With OR, a webhook POST **still** matches the default unsafe matcher so it is not exempted; meanwhile many non-webhook GETs match the NOT-webhook branch and mistakenly demand CSRF. This bug is hard to notice if you only test one request without handlers.

### 4.2. Why not use solely NOT webhook?

~~~java
// ANTI-PATTERN: non-webhook GET/OPTIONS requests also demand tokens.
new NegatedServerWebExchangeMatcher(webhookPost);
~~~

Without preserving the default condition, almost every non-webhook request matches. Public GETs, health checks, and OPTIONS preflights can fail with CSRF 403. Exemption matchers must be combined with method-based policy.

### 4.3. Why not exempt every method on the same path?

~~~java
// ANTI-PATTERN: path-only also exempts PUT/DELETE on this route.
ServerWebExchangeMatchers.pathMatchers(
    "/integrations/webhook/receive");
~~~

When the provider only sends POST, exempting PUT/DELETE is unnecessary. Even if no controller handles PUT today, a future endpoint added later could accidentally inherit the exemption. Always use a method-aware matcher if policy permits only one method.

### 4.4. Avoid broad wildcards

A `/integrations/**` matcher exempts all current and future callbacks, even one lacking HMAC verification. A `/api/**` matcher can disable CSRF across all session-cookie browser APIs. Prefer exact paths and an explicitly controlled exemption list.

When multiple valid callbacks exist, build an `OrServerWebExchangeMatcher` **among those specific exemptions**, wrap it in `NegatedServerWebExchangeMatcher`, and AND with the default. Here OR sits **inside the exemption group**, never directly ORed with the default CSRF matcher.

## 5. Truth table to write before coding

| Method | URL | Default unsafe? | Matches exemption? | Needs CSRF? |
| --- | --- | --- | --- | --- |
| GET | `/health` | No | No | No |
| HEAD | `/health` | No | No | No |
| OPTIONS | `/api/notes` | No | No | No |
| GET | `/api/notes/count` | No | No | No |
| POST | `/integrations/webhook/receive` | Yes | **Yes** | **No** |
| POST | `/integrations/webhook/receive/batch` | Yes | No | **Yes** |
| POST | `/integrations/other` | Yes | No | **Yes** |
| PUT | `/integrations/webhook/receive` | Yes | No | **Yes** |
| PATCH | `/integrations/webhook/receive` | Yes | No | **Yes** |
| DELETE | `/integrations/webhook/receive` | Yes | No | **Yes** |
| POST | `/api/notes` | Yes | No | **Yes** |
| POST | `/login` | Yes | No | **Yes** |
| POST | `/logout` | Yes | No | **Yes** |

This is a **matcher truth table**, not an HTTP status table. A URL lacking a controller or hitting `denyAll` can return 403/404/405 from another layer. Testing HTTP status alone does not prove the matcher is right.

**URL note:** Path matching inspects the framework-resolved path, not the query string. `POST /integrations/webhook/receive?delivery=123` still matches the same webhook path in this design. If query parameters are part of a security protocol, the verifier must check them properly; never treat query strings as authentication proof by themselves.

## 6. Why exempting CSRF must not exempt webhook authentication

Webhooks from partner servers lack browser session cookies. To accept callbacks, applications should use another mechanism: HMAC, mTLS, JWT/client credentials, or provider-defined signatures.

In the demo project we choose **HMAC-SHA-256**:
- Use a provider-dedicated secret.
- Sign the exact **raw body bytes**, never JSON parsed and re-serialized.
- Incoming header format: `X-Hook-Signature: sha256=<64 hex characters>`.
- The verifier validates format, computes expected HMAC, and compares bytes with `MessageDigest.isEqual(...)`.
- Invalid/missing HMAC: **401**; valid HMAC: demo accepts with **202**.
- Lacking a signature while exempted from CSRF is **never** treated as a valid request.

Understand clearly: HMAC **does not prevent replays on its own**. A validly signed payload can be replayed. Production systems need timestamps/delivery IDs/nonces inside the signed material, clock-skew bounds, processed-state storage, and idempotency. Otherwise payments or resource mutations can execute repeatedly. That is a business-state replay/TOCTOU issue, distinct from CSRF verification.

**Secrets in learning code are localhost-only.** Production must load secrets from a secret manager or secure environment with rotation and zero logging. Nor does HMAC replace HTTPS, validation, size limits, rate limits, internal authorization, or schema checks.

## 7. Runnable Java 17+ project with Spring Boot WebFlux

The example pins **Spring Boot 3.3.13** and Java 17+ so illustrative APIs stay consistent. Never treat the demo as a complete production config; for real deployments pick a supported Boot release and re-test.

### 7.1. Layout and Gradle

~~~text
webflux-csrf-scoped/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── CsrfScopedApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── WebhookVerifier.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── CsrfScopeTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-csrf-scoped'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

Spring Boot manages compatible Spring Security and Reactor versions. Never add Servlet MVC's `spring-boot-starter-web` to a WebFlux project. `spring-security-test` supplies `csrf()` and `springSecurity()`; `reactor-test` supplies `StepVerifier`.

`src/main/resources/application.properties`:

~~~properties
# Local demo only: NEVER use this secret in production.
demo.webhook.secret=development-only-change-me
~~~

### 7.2. Main class

`src/main/java/demo/CsrfScopedApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfScopedApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfScopedApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig with a very narrow exemption

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CsrfWebFilter;
import org.springframework.security.web.server.util.matcher.AndServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.NegatedServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(reader);
    }

    // Tests can call this method to verify each truth-table cell.
    static ServerWebExchangeMatcher csrfRequiredMatcher() {
        ServerWebExchangeMatcher exemptWebhook =
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.POST,
                "/integrations/webhook/receive"
            );

        return new AndServerWebExchangeMatcher(
            CsrfWebFilter.DEFAULT_CSRF_MATCHER,
            new NegatedServerWebExchangeMatcher(exemptWebhook)
        );
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()

                // Requires no end-user login, YET the controller
                // must verify a valid HMAC before accepting.
                .pathMatchers(HttpMethod.POST,
                    "/integrations/webhook/receive")
                    .permitAll()

                .pathMatchers(HttpMethod.GET,
                    "/api/notes/count")
                    .authenticated()
                .pathMatchers(HttpMethod.POST,
                    "/api/notes")
                    .authenticated()

                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf
                .requireCsrfProtectionMatcher(csrfRequiredMatcher()))
            .build();
    }
}
~~~

**Explanation:**

- There is **one security chain**, so every URL passes through the configured policy. `securityMatcher` is not customized in the demo; chain selection and CSRF matchers are separate concepts.
- `exemptWebhook` matches only POST on that exact path. PATCH/PUT/DELETE on the same path are not exempted.
- `AndServerWebExchangeMatcher` preserves default safe methods and excludes only webhook POST.
- `requireCsrfProtectionMatcher` sets the predicate requiring tokens—it is not `disable()`.
- `permitAll` on the webhook is a **user-level authentication decision**, not proof the request came from the partner. The HMAC verifier proves authenticity.
- `/api/notes` uses HTTP Basic for easy testing; Basic credentials can be ambient in browsers, so POST still requires a CSRF token.
- `/api/notes/count` is a GET; it needs no CSRF yet still requires authentication.
- `anyExchange().denyAll()` avoids silently permitting new routes. If adding form login, permit the relevant pages and re-test login/logout CSRF.
- Uses reactive APIs rather than Servlet's `HttpSecurity`/`CsrfFilter`.

### 7.4. HMAC verifier over raw body bytes

`src/main/java/demo/WebhookVerifier.java`:

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class WebhookVerifier {

    private static final String PREFIX = "sha256=";
    private final byte[] secret;

    WebhookVerifier(Environment environment) {
        secret = environment
            .getRequiredProperty("demo.webhook.secret")
            .getBytes(StandardCharsets.UTF_8);
    }

    boolean verify(byte[] raw, String header) {
        if (header == null || !header.startsWith(PREFIX)) {
            return false;
        }

        String hex = header.substring(PREFIX.length());
        if (hex.length() != 64) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = HexFormat.of().parseHex(hex);
        }
        catch (IllegalArgumentException badHex) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal(raw);
            return MessageDigest.isEqual(expected, supplied);
        }
        catch (GeneralSecurityException configError) {
            throw new IllegalStateException(
                "Webhook HMAC configuration failed", configError);
        }
    }
}
~~~

- `HexFormat` is a Java 17 API.
- The HMAC signature is computed over the **exact original bytes** from the request body. Parsing and re-serializing JSON can alter whitespace or key ordering and break the digest.
- Malformed headers, invalid hex, or missing signatures are rejected.
- `MessageDigest.isEqual(...)` compares digests bytewise rather than naive string equality.
- Algorithm/secret errors must never degrade into "skip verification".
- This verifier targets the lesson's sample protocol and does not match every real provider. Production needs versioned signatures, timestamps, nonces, size/format checks, key rotation, and replay protection.

### 7.5. Controller: webhook and browser API with distinct responsibilities

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    record NoteInput(String text) {}
    record NoteView(int count, String text) {}
    record CountView(int count) {}

    private final WebhookVerifier verifier;
    private final AtomicInteger count = new AtomicInteger();

    DemoController(WebhookVerifier verifier) {
        this.verifier = verifier;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/notes/count")
    Mono<CountView> count() {
        return Mono.fromSupplier(() -> new CountView(count.get()));
    }

    @PostMapping(
        path = "/api/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<NoteView>> create(
            @RequestBody Mono<NoteInput> body) {

        return body.map(note -> {
            if (note.text() == null
                || note.text().isBlank()
                || note.text().length() > 200) {

                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid note");
            }

            int next = count.incrementAndGet();
            return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteView(next, note.text()));
        });
    }

    @PostMapping(
        path = "/integrations/webhook/receive",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<Map<String, String>>> webhook(
            @RequestBody Mono<byte[]> rawBody,
            @RequestHeader(
                name = "X-Hook-Signature", required = false
            ) String signature) {

        return rawBody
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Empty webhook body")))
            .map(bytes -> {
                if (!verifier.verify(bytes, signature)) {
                    throw new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED, "Bad webhook signature");
                }
                return ResponseEntity.accepted().body(
                    Map.of("status", "accepted"));
            });
    }
}
~~~

**Notes on response DTOs and bodies:**
- `@RequestBody Mono<byte[]>` reads raw bytes for HMAC verification. Never read raw signatures from query strings.
- `X-Hook-Signature` is not a default Spring Security header; it belongs to the demo protocol.
- Valid HMAC returns HTTP **202 Accepted**; no real persistence or transaction occurs.
- Missing/invalid HMAC returns **401 Unauthorized** with zero side effects.
- `POST /api/notes` has a counter-increment side effect. If blocked by the CSRF filter, the controller is not invoked and the counter stays unchanged.
- Note payloads are validated; clients cannot spoof owner/roles.
- `GET /api/notes/count` uses `Mono.fromSupplier`, non-blocking, independent of CSRF tokens.
- No `block()` or `subscribe()` calls inside reactive controllers.
- Production must enforce body size limits and use idempotent repositories/transactions rather than an in-memory counter.

## 8. Verifying matcher logic independently of HTTP status

A common testing mistake: `POST /integrations/other` without a token returns 403, leading someone to conclude it was definitely CSRF. Yet `anyExchange().denyAll()` can also return 403, as can another controller or filter. **HTTP 403 alone is insufficient to prove the CSRF matcher is right.**

Test directly:

~~~java
SecurityConfig.csrfRequiredMatcher()
    .matches(mockExchange)
    .map(ServerWebExchangeMatcher.MatchResult::isMatch);
~~~

The result is `Mono<Boolean>`. In tests, use `StepVerifier` to confirm:
- Exact webhook POST -> false.
- Child path POST -> true.
- Webhook PUT/PATCH/DELETE -> true.
- Browser API/login/logout POST -> true.
- GET/HEAD/OPTIONS -> false.

This is a unit test of the policy predicate; it differs from HTTP integration tests exercising the security filter chain + controllers.

## 9. Complete verification with WebTestClient

`src/test/java/demo/CsrfScopeTests.java`:

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CsrfScopeTests {

    private static final String WEBHOOK =
        "/integrations/webhook/receive";
    private static final String SECRET =
        "development-only-change-me";
    private static final byte[] BODY =
        "{\"event\":\"ping\"}".getBytes(StandardCharsets.UTF_8);

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private void expectCsrfRequired(
            HttpMethod method, String path, boolean shouldMatch) {

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.method(method, path));

        StepVerifier.create(
                SecurityConfig.csrfRequiredMatcher().matches(exchange))
            .assertNext(result ->
                assertThat(result.isMatch()).isEqualTo(shouldMatch))
            .verifyComplete();
    }

    @Test
    void exactPostWebhookIsOnlyExemption() {
        expectCsrfRequired(HttpMethod.POST, WEBHOOK, false);
        expectCsrfRequired(HttpMethod.POST, WEBHOOK + "/batch", true);
        expectCsrfRequired(HttpMethod.POST, "/integrations/other", true);
    }

    @Test
    void otherMethodsAtWebhookPathStillNeedCsrf() {
        expectCsrfRequired(HttpMethod.PUT, WEBHOOK, true);
        expectCsrfRequired(HttpMethod.PATCH, WEBHOOK, true);
        expectCsrfRequired(HttpMethod.DELETE, WEBHOOK, true);
    }

    @Test
    void safeHttpMethodsRemainUnprotectedByCsrf() {
        expectCsrfRequired(HttpMethod.GET, "/health", false);
        expectCsrfRequired(HttpMethod.HEAD, "/health", false);
        expectCsrfRequired(HttpMethod.OPTIONS, "/api/notes", false);
    }

    @Test
    void browserPostLoginLogoutAndNotesStillNeedCsrf() {
        expectCsrfRequired(HttpMethod.POST, "/login", true);
        expectCsrfRequired(HttpMethod.POST, "/logout", true);
        expectCsrfRequired(HttpMethod.POST, "/api/notes", true);
    }

    private static String signature(byte[] raw) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                SECRET.getBytes(StandardCharsets.UTF_8),
                "HmacSHA256"));
            return "sha256=" +
                HexFormat.of().formatHex(mac.doFinal(raw));
        }
        catch (GeneralSecurityException error) {
            throw new AssertionError(error);
        }
    }

    @Test
    void validWebhookNeedsNoCsrfAndNoUserSession() {
        client.post().uri(WEBHOOK)
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Hook-Signature", signature(BODY))
            .bodyValue(BODY)
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted");
    }

    @Test
    void webhookWithoutSignatureFailsAtVerifier() {
        client.post().uri(WEBHOOK)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(BODY)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void webhookWithWrongSignatureFailsAtVerifier() {
        client.post().uri(WEBHOOK)
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Hook-Signature",
                "sha256=0000000000000000000000000000000000000000000000000000000000000000")
            .bodyValue(BODY)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() {
        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "No token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedPostWithValidCsrfIsCreated() {
        client.mutateWith(csrf())
            .post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "Valid note"))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.text").isEqualTo("Valid note");
    }

    @Test
    void csrfTokenDoesNotReplaceAuthentication() {
        client.mutateWith(csrf())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "Anonymous"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void getDoesNotNeedCsrfButStillNeedsAuthentication() {
        client.get().uri("/api/notes/count")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/notes/count")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.count").isNumber();
    }

    @Test
    void unrelatedPostDoesNotBecomeAnExemption() {
        client.post().uri("/integrations/other")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("event", "ping"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

### 9.1. Why are both test types needed?

The first tests inspect `ServerWebExchangeMatcher.MatchResult.isMatch()` directly via the publisher, avoiding confusion between a `denyAll` 403 and a CSRF 403. The remaining HTTP tests run the `WebFilterChain`:

- Valid signature + no CSRF + no user login on webhook -> **202**, proving the exemption works and the verifier accepts the request.
- Missing/wrong signature on webhook -> **401**, proving the exemption did not disable source verification.
- Valid Basic user + note POST missing CSRF -> **403**, proving browser APIs remain protected.
- Valid Basic + valid test `csrf()` -> **201**, proving not all POSTs are blocked.
- Valid CSRF without auth -> **401**, proving CSRF tokens do not grant identity.
- Note-count GET without CSRF yet missing auth -> **401**, and with auth -> **200**.

`WebTestClient.mutateWith(csrf())` **does not disable CSRF in the application**. It is a Spring Security Test helper supplying a valid token for mock requests. In real browsers, tokens must be issued and sent via Spring Security's `ServerCsrfTokenRepository` and request handler in the same session.

### 9.2. Commands to run

~~~bash
gradle bootRun
gradle test
~~~

These are two **separate** commands: run the server for manual testing or run tests for verification. If using Gradle Wrapper, run `./gradlew bootRun` and `./gradlew test` on Unix/macOS, or `gradlew.bat` on Windows. Requires JDK 17+ and compatible Gradle.

With compatible dependencies, **12** test methods are expected to pass. Actual build output, stdout/logs, and timings must be verified when run; never treat this description as a log of an executed run.

### 9.3. What do the tests NOT cover yet?

This demo focuses on the matcher and does not claim to cover full production webhook security. In real deployments, add tests for:
- Replayed signed payloads with the same delivery ID rejected or safely ignored.
- Expired timestamps and duplicate nonces rejected.
- Changing a single byte of the raw JSON body after signing -> invalid HMAC.
- Malformed hex or wrong prefix in header -> rejected.
- Oversized bodies, wrong content types, and invalid schemas -> 400/413/415 per HTTP contract.
- Duplicate event handling idempotency, especially for financial operations.
- Signatures using revoked secrets no longer accepted.
- Reverse proxies adding prefixes, trailing slashes, or unusual encodings never bypassing matchers.
- Multi-chain behavior verified on the actual selected chain.
- Browser access to protected routes with invalid/cross-session CSRF tokens returns 403.
- On apps with form login, login/logout POSTs missing tokens are still rejected.

## 10. HTTP outcomes: 401 and 403 don't tell the whole story

The table below applies to the demo, where the sole exemption is exact webhook POST.

| Request | Expected | Why |
| --- | --- | --- |
| Webhook POST, valid HMAC, no CSRF token | **202** | Matcher exempts CSRF; verifier accepts |
| Webhook POST, missing/wrong HMAC | **401** | Verifier rejects |
| `POST /api/notes` valid Basic, no CSRF | **403** | `CsrfWebFilter` rejects |
| `POST /api/notes` valid Basic, valid test CSRF | **201** | Passes auth + CSRF, controller runs |
| `POST /api/notes` valid CSRF, missing Basic | **401** | Missing authentication |
| `GET /api/notes/count`, no Basic | **401** | Safe GET yet requires login |
| `GET /api/notes/count`, valid Basic | **200** | Valid authentication |
| Unknown path POST, no token | **403** | Likely rejected by CSRF before `denyAll` |
| Unknown path POST, valid token | **403** | `anyExchange().denyAll()` |
| Webhook path PUT, no token | **403** | Matcher still requires CSRF; authorization also denies method |
| Path without handler that passes all security layers | **404/405** | Routing decides per URL/method |

**Never** conclude "403 proves CSRF" without checking where it originated. Spring Security authz, CSRF filter, CORS policy, gateways, or app error handlers can all return 403. With browser form login, unauthenticated requests may redirect 302 instead of 401; the demo disabled form login to keep HTTP Basic observable.

### 10.1. Distinguishing "CSRF excluded" from "endpoint permitted to run"

On the webhook, the CSRF matcher returns false. Yet a request with a bad HMAC still returns 401 and is never processed. On `/api/notes`, the CSRF matcher returns true, yet a valid token still cannot permit the request without logging in.

Visualize it as:

~~~text
Can processing continue?
  ├─ Correct security chain selected?
  ├─ Valid CSRF token IF required by matcher?
  ├─ Route authentication valid?
  ├─ Authorization permits the action?
  ├─ For webhooks: valid HMAC signature and replay policy?
  └─ Business validation and data permissions satisfied?
      -> Only when every relevant layer passes do side effects occur.
~~~

## 11. Pitfalls when changing paths or methods

### 11.1. Relaxing from exact path to wildcard

Initially only `POST /integrations/webhook/receive` exists. After a refactor, if the exemption changes to `/integrations/**`:
- `POST /integrations/webhook/refund` becomes auto-exempted even before signature policies exist.
- PUT/PATCH/DELETE under `/integrations/**` may be exempted if the matcher omits method constraints.
- Teammates may mistakenly assume "none of integrations need CSRF".

Keep exact paths/methods, or enumerate endpoints in a reviewed group. Every newly added callback needs tests for both exempted requests **and** requests that must stay protected.

### 11.2. Proxy rewrites and URL normalization

Ingress may prepend prefixes, rewrite paths, or decode URLs. Spring Security matchers inspect the path WebFlux receives when the filter runs; the app must know whether that matches controller mappings.

If webhook POSTs return 403 in production, check:
- Which exact path actually reaches the app?
- Does a reverse proxy strip prefixes or set forwarded headers?
- Does a trailing slash differ from the exact path?
- Are percent-encoded paths, casing, and dot-segments normalized consistently?
- Is a filter/rewrite running before Spring Security?

Never fix this by exempting `/**`. Test the real path through the proxy and update an approved scoped matcher.

### 11.3. Multiple `SecurityWebFilterChain` beans

If a dedicated webhook chain uses `securityMatcher("/integrations/**")` and a browser chain handles `/**`, chain order (`@Order`) decides which chain runs. `requireCsrfProtectionMatcher(...)` affects only the chain containing that configuration.

A right matcher inside an **unselected** chain has zero effect. A `permitAll` webhook chain lacking signature verification creates a vulnerability. Test chain selection and authentication protocols per URL group.

**Never** use `securityMatcher` to "skip a CSRF check" if the goal is solely exempting one POST in the same chain. That scopes every filter, not just `CsrfWebFilter`.

## 12. CORS, cookies, and CSRF are independent policies

Browser CORS preflights send OPTIONS, and the default CSRF matcher requires no token for OPTIONS. If preflight gets 401/redirect, the cause is CORS handling vs. authentication ordering, not missing CSRF tokens.

- **CORS** governs cross-origin browser policies for preflights and response reads.
- **CSRF** guards against forged actions when browsers auto-send credentials.
- **Authentication** verifies user identity or webhook origin.
- **Authorization** enforces permissions and resource boundaries.

Disabling CORS does not eliminate CSRF, because cross-site HTML forms can send requests without the attacker reading responses. Allowing an origin in CORS also does not grant CSRF tokens or write permissions.

For SPAs using session cookies, JavaScript needs a mechanism to fetch CSRF tokens matching the repository and send them with requests. Spring Security WebFlux 6.x has `ServerCsrfTokenRepository` (default `WebSession`) and request handlers; `XorServerCsrfTokenRequestAttributeHandler` applies BREACH protection so token representations must be used properly. Test `csrf()` helpers do not replace real UI testing.

## 13. Other scenario: Bearer-only stateless APIs

In an API accepting only Bearer tokens **explicitly** attached in headers by clients with zero ambient cookies, HTTP Basic, or browser auto-sent client certificates, the CSRF model differs sharply from browser session apps. A separate chain serving strictly Bearer-only traffic can have its own CSRF policy if the threat model permits.

However:
- A refresh-token cookie on another endpoint may still require CSRF.
- An endpoint accepting both Basic/sessions and Bearer may still carry CSRF risk.
- JWTs must verify issuer, signature, audience, expiration, scopes, and ownership.
- XSS can steal tokens from client storage or send requests as the user.
- HMAC webhook endpoints still need replay protection/idempotency despite having no CSRF tokens.

Never infer "API is REST -> disable all CSRF"; inspect how credentials work and the policy of each security chain.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Chain-wide `csrf.disable()` for a webhook | Browser forms/APIs lose CSRF protection | Exempt exact POST + path |
| Using `NOT webhook` without default matcher | GET/OPTIONS may demand CSRF | AND with `DEFAULT_CSRF_MATCHER` |
| Direct OR between default and NOT webhook | Webhook still demands token; GET may demand token | Write logic expression first; use AND |
| Path-only exemption without method constraint | PUT/DELETE on same path exempted | Path matcher with `HttpMethod.POST` |
| Exempting `/integrations/**` broadly | New routes silently inherit exemption | Explicit route allowlist policy |
| Believing `permitAll()` disables `CsrfWebFilter` | POST still 403; devs wrongly call `disable()` | Separate CSRF matcher and authorization |
| Treating HMAC as replay protection | Valid delivery can be replayed | Timestamp + nonce/delivery ID + idempotency |
| Naive string comparison for HMAC | Encoding/timing flaws | HMAC raw bytes + `MessageDigest.isEqual` |
| Hardcoding real secrets in repo | Leaks, hard to rotate | Secret manager and versioned keys |
| Confusing Servlet `HttpSecurity`/`RequestMatcher` | Wrong stack for WebFlux | `ServerHttpSecurity`/`ServerWebExchangeMatcher` |
| Testing only HTTP 403 | Unclear which filter returned 403 | Unit test matcher + integration tests |
| Testing only disabled CSRF on webhook | Webhook may lack authentication | Test valid signature 202, missing/wrong 401 |
| Forgetting PUT/PATCH/DELETE on webhook path | Exemption leaks across methods | Method-specific truth table |
| Disabling CSRF because browser API got 403 | Loses genuine CSRF protection | Issue session token; use `csrf()` in tests |
| Manually `subscribe()` to check signatures before saving | Detaches lifecycle and side effects | Compose in `Mono`; never block |
| Treating Origin/CORS as partner signature | Origin can be spoofed outside browsers | Independent HMAC/mTLS/OAuth2 |
| Not testing after proxy rewrites | Real URL misses matcher | Test actual route via ingress/proxy |
| Not testing after adding chains | Requests may hit another chain | Test `securityMatcher`/`@Order` |
| Treating 401/403/404 as fixed causes | Fails to pinpoint rejecting layer | Classify by security filter/entry point |

### 14.1. When the CSRF filter rejects, does the controller run?

On `POST /api/notes` missing a token, `CsrfWebFilter` rejects before the request reaches the controller, so the counter does not increment. Invalid permissions/users must likewise prevent side effects. In production, include tests that re-read resources to confirm rejected requests truly wrote nothing.

### 14.2. Do you need tests for wrong tokens besides missing tokens?

Yes. Beyond tokenless POST tests, real systems need:
- Invalid random token -> 403.
- Valid token belonging to another session -> 403.
- Expired/invalidated token -> rejected.
- Valid token with unauthenticated user -> blocked by authentication.
- Valid token lacking role/owner -> blocked by authorization.

Spring Security's test `csrf()` supplies a valid mocked token for mock requests; to verify full session/browser flows, run integration/E2E tests with server-rendered tokens and preserved cookies.

## 15. Exercises and answers

**Q1.** You only want `POST /integrations/webhook/receive` to skip CSRF. Can you call `csrf.disable()`?

**Answer:** No while browser session/cookie/Basic endpoints remain in the chain. Use `DEFAULT_CSRF_MATCHER AND NOT exact POST webhook`.

**Q2.** Why is `new NegatedServerWebExchangeMatcher(webhook)` alone wrong?

**Answer:** It matches non-webhook GET/OPTIONS requests too, causing safe methods to demand CSRF.

**Q3.** What does OR between the default matcher and NOT webhook produce?

**Answer:** Webhook POST still matches default and demands a token; many GETs match NOT webhook and may demand tokens too. Use AND.

**Q4.** Is `POST /integrations/webhook/receive/batch` exempted?

**Answer:** No, because the exact path differs. The matcher requires CSRF.

**Q5.** Is `PUT /integrations/webhook/receive` exempted?

**Answer:** No, because the method must be POST to match the exemption.

**Q6.** Does `GET /api/notes/count` require CSRF? Does it require authentication?

**Answer:** No CSRF under default safe methods; still requires authentication per `authorizeExchange`.

**Q7.** Does `permitAll()` on the webhook skip the HMAC verifier?

**Answer:** No. It only lets the route be called without user login; the verifier must check signatures before any side effect.

**Q8.** Can you conclude the matcher is right if a non-webhook POST returns 403?

**Answer:** Not yet. 403 can come from `denyAll`; test `MatchResult.isMatch()` directly.

**Q9.** When can a request with a valid HMAC still be dangerous?

**Answer:** When payloads are replayed, signing secrets leak, business validation is flawed, or handlers execute duplicate work. Enforce timestamps/nonces, idempotency, and audits.

**Q10.** When a server-to-server webhook gets 403, what is the right first step?

**Answer:** Identify the exact URL/method and which filter returned 403, then check matchers, chain routing, and signatures—never disable CSRF across the chain.

**Q11.** Can a JWT-only API using zero ambient cookies disable CSRF?

**Answer:** Potentially per its own threat model, while still inspecting cookie/refresh/Basic endpoints and maintaining XSS, authentication, and authorization controls.

**Q12.** Why test POST login/logout even though the demo uses Basic?

**Answer:** To ensure the exemption matcher never spills onto routes that will need CSRF once form login is enabled in the same chain.

**Q13.** Does Spring Security Test's `csrf()` actually disable `CsrfWebFilter`?

**Answer:** No. It supplies valid test CSRF credentials so tests pass the filter legitimately.

**Q14.** When adding a proxy prefix breaks webhook matching, should you exempt `/**` for speed?

**Answer:** No. Inspect the URL WebFlux receives, fix mappings/matchers precisely, and test through the proxy.

**Q15.** Does a valid CSRF token grant roles or allow modifying another user's documents?

**Answer:** No. Authentication, authorization, and object ownership remain independently enforced.

## 16. Pre-production review checklist

- [ ] Threat model documents why the endpoint uses no ambient browser credentials.
- [ ] Exemption covers **strictly the approved method + exact path**.
- [ ] CSRF matcher is `DEFAULT_CSRF_MATCHER AND NOT webhookMatcher`; safe methods still need no tokens.
- [ ] Never disable CSRF chain-wide just to make one webhook work.
- [ ] Dedicated webhook HMAC/mTLS/auth runs **before** any side effects.
- [ ] Secrets managed securely, rotated, never hardcoded in production.
- [ ] Replay protection, timestamps, nonces/delivery IDs, and idempotency implemented.
- [ ] Input validation, request size limits, rate limits, and auditing in place.
- [ ] Matcher unit tests verify exact POST, child paths, other methods, login/logout, and GET/OPTIONS.
- [ ] Integration tests verify valid webhook HMAC returns 2xx without CSRF; missing/wrong HMAC is rejected.
- [ ] Integration tests verify browser POST missing/wrong CSRF returns 403 and valid token succeeds.
- [ ] CSRF tokens never replace authentication/authorization; unauthorized user tests included.
- [ ] Never infer solely from HTTP 403; distinguish CSRF from `denyAll`.
- [ ] Security chain selection, proxy rewrites, and CORS preflights verified on changes.
- [ ] Never log cookies, CSRF tokens, HMAC secrets, signatures, or credentials.
- [ ] Negative test cases retained in CI to catch overly broad exemptions.

## 17. Official References

- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security API — `ServerHttpSecurity.CsrfSpec` and `requireCsrfProtectionMatcher`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security API — `CsrfWebFilter.DEFAULT_CSRF_MATCHER`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/csrf/CsrfWebFilter.html
- Spring Security API — `AndServerWebExchangeMatcher`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/util/matcher/AndServerWebExchangeMatcher.html
- Spring Security API — `NegatedServerWebExchangeMatcher`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/util/matcher/NegatedServerWebExchangeMatcher.html
- Spring Security API — `ServerWebExchangeMatchers`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html
- Spring Security — Testing WebFlux with CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Takeaway:** Safely exempting CSRF means **bounding a justified exception**, not turning off the protection layer. Spring Security WebFlux lets you express `unsafe method AND NOT exact webhook POST` using `requireCsrfProtectionMatcher(...)`. Test the **truth table directly on the matcher** and use **WebTestClient** to confirm properly signed webhooks are accepted while browser POSTs still require valid CSRF tokens and authentication.
