# Evaluating CSRF Exemptions for Bearer-Token APIs Based on How Browsers Send Credentials

**Module:** Spring Security – reactive (WebFlux)  
**Parent topic:** CSRF Protection  
**Audience:** Java 17+ developers implementing APIs, SPAs, browser sessions, or BFFs with Spring Security.

**Key conclusion before configuring:** An API may be considered for **CSRF exemption** on state-changing requests when the **sole credential accepted by the API** is a Bearer access token explicitly added to the `Authorization` header by the client; the browser **does not automatically fetch that token from a trusted origin and attach it to requests triggered by another website**. Conversely, if the API accepts **session cookies, JWT/opaque tokens in cookies, cached browser HTTP Basic, BFF cookies, or any authentication fallback auto-sent by browsers**, CSRF risk **remains**. Returning JSON, calling the token JWT/Bearer, or labeling the backend "stateless" are **never enough** to justify disabling CSRF.

This lesson progresses from browser mechanics, risk matrices, and WebFlux chain design to a Java Spring Boot app featuring **two `SecurityWebFilterChain` beans** and **14 HTTP tests**. Examples use HMAC-signed test tokens on localhost for learning, **not production key-management configurations**.

## 1. Nature of CSRF: authority auto-carried by browsers into requests

CSRF (*Cross-Site Request Forgery*) happens when an attack page abuses an authenticated user's browser to ask a target site to perform an action the user did not choose. The core requirement is that the request hitting the target server **automatically carries credentials accepted by the server**, such as a `SESSION` cookie. The attacker does not need to read the cookie; it suffices for the browser to send it when processing a form/navigation/request under applicable rules.

```text
User is logged into https://bank.example.test
   |
   | Browser holds Cookie: SESSION=...
   |
   v
Visits https://evil.example.test
   |
   | Unfamiliar page builds a POST form to bank
   | Browser may auto-add SESSION per SameSite/cookie policy
   |
   v
Bank receives POST + valid SESSION
   |
   +--> If lacking CSRF protection: risk of executing forged action
   +--> If requiring non-auto-sent CSRF token: rejects forged request
```

Login proof inside a cookie may be a session ID or a self-contained JWT. **Even without server-side sessions**, CSRF risk persists if a JWT is auto-sent by browsers via cookies. That is why "stateless" does not mean "CSRF-safe".

### 1.1. Contrasting with a Bearer header explicitly attached by JavaScript

```http
POST /api/transfer HTTP/1.1
Host: api.example.test
Authorization: Bearer <valid-access-token>
Content-Type: application/json

{"destination":"demo","amount":1}
```

If the access token exists only within an authorized client context and application JavaScript explicitly sets `Authorization: Bearer ...`, an external site **cannot automatically obtain the token** to put in the header. Browsers do not automatically attach Bearer tokens from an app's private storage onto cross-site forms. This is the **conditional** basis for exempting CSRF on Bearer-only APIs.

This **does not eliminate** XSS, token theft, third-party script risks, overly permissive CORS, access tokens in logs, or resource servers failing to validate signatures/issuers/expiries. CSRF exemption and token security are two separate concerns.

### 1.2. Five questions before exempting

1. **Which credentials does the server truly accept?** Only `Authorization: Bearer` headers, or also `SESSION`/`access_token` cookies/HTTP Basic?
2. **Does the browser auto-carry that credential into requests?** Inspect cookie scope, SameSite, `credentials` mode, Basic caching, and gateways.
3. **If the Bearer header is omitted while a valid session cookie is present, does the endpoint return 401?** This is a critical negative test.
4. **Does a BFF/gateway accept cookies and attach a Bearer header to the backend?** If so, the browser-facing boundary still receives ambient cookies.
5. **Which routes are browser-session vs. Bearer-only?** Can `csrf.disable()` be strictly scoped to the right `SecurityWebFilterChain`?

If anything remains ambiguous, never disable CSRF just to turn a POST test into 200.

## 2. Decision matrix by credential transport

| Server authenticates request via | Auto-sent by browser on requests triggered by another site? | CSRF assessment for state-changing commands |
| --- | --- | --- |
| Bearer header **explicitly added by trusted JS**, API **accepts no cookie fallback** | Does not auto-attach another origin's Bearer token | **May consider exemption**, keeping authentication/authorization intact |
| JWT Bearer stored in a cookie and API reads that cookie | Possibly, per SameSite/cookie policy | **Must enforce CSRF** or proven equivalent defenses |
| `WebSession`/`SESSION` cookie for form login | Possibly | **Enable CSRF**, especially POST/PUT/PATCH/DELETE |
| BFF holds tokens server-side; browser uses `SESSION` cookie | Possibly | **Enable CSRF on BFF/browser-facing endpoints** |
| HTTP Basic cached by the browser | Can auto-send `Authorization: Basic` | **Treat as ambient credential; keep CSRF** |
| Bearer-only API where cookies appear yet are **completely ignored in auth** | Cookies may appear; **grant zero authority from them** | **May exempt** after verifying cookie-only always returns 401 |
| An endpoint accepting **both Bearer and session cookies** | Has an ambient cookie path | **Keep CSRF**, or refactor to eliminate cookie fallback |
| Resource server accepting only mTLS/service-to-service tokens with no browsers | No ambient browser credentials in this model | CSRF is usually unnecessary; authn/authz still mandatory |
| Proxy reads cookie and converts it to `Authorization: Bearer` for backend | Yes at ingress | **Enforce CSRF at ingress/BFF**; Bearer-only backend does not remove browser risk |
| `GET` with side effects or tokens in URLs | Links/navigations can trigger; URLs leak easily | **Fix HTTP semantics**; never use CSRF exemption as a "fix" |

**Do not conflate:** JWT is a **token format**; Bearer is a **credential type**; headers vs. cookies are **browser transports**; CSRF depends on **ambient credentials accepted by the server**.

### 2.1. Authorization headers are not all alike

`Authorization: Bearer <token>` explicitly set by client code differs from `Authorization: Basic <base64>` which browsers may auto-resend after a user logs in via HTTP Basic. You cannot deduce "has Authorization header, therefore no CSRF risk". Nor can you look solely at a backend's incoming HTTP header if an upstream gateway synthesized it from a cookie.

### 2.2. Cookie presence alone does not prove danger

A browser on the same domain may auto-attach `SESSION` when sending a Bearer request to an API. If the API **never uses** that session cookie to authenticate, the cookie grants no authority to the request. A negative test sending **cookie only without Bearer** must return 401. If a later refactor reads a cookie token to build Authentication, the CSRF exemption conclusion **must be re-evaluated**.

## 3. Three real-world browser scenarios

### 3.1. SPA explicitly attaching Bearer

```javascript
// accessToken must come from a proper token-issuance flow and be stored safely.
const result = await fetch("/api/transfer", {
  method: "POST",
  credentials: "omit",
  headers: {
    Authorization: "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ destination: "demo", amount: 1 })
});

if (!result.ok) {
  throw new Error("Request rejected: " + result.status);
}
```

`credentials: "omit"` stops the browser from attaching cookies/ambient credentials in this mode; `Authorization` is still explicitly set by application code. **Never treat JS-attached Bearer tokens as XSS defense**: if the origin suffers XSS or malicious scripts can run there, attackers can steal/use tokens and issue requests. Storing tokens in memory, storage, or a BFF each carries trade-offs; never assume `localStorage` is a safe default.

### 3.2. JWT in an HttpOnly cookie

```http
POST /api/transfer HTTP/1.1
Cookie: access_token=<jwt>
Content-Type: application/x-www-form-urlencoded

destination=attacker&amount=1
```

`HttpOnly` stops JavaScript from reading the cookie directly, **not** from the browser auto-sending it. If a Spring filter/gateway uses this cookie to grant Authentication, CSRF risk exists. CSRF tokens or equivalent defenses are required alongside SameSite/Secure/Origin policies. Putting a JWT in a cookie **does not retain the CSRF-exemption benefit** of a JS-set Bearer header.

### 3.3. BFF receiving session cookie and calling resource server with Bearer

```text
Browser --Cookie: SESSION=...--> BFF (WebFlux)
                                 |
                                 | Authorization: Bearer ...
                                 v
                              Resource Server
```

The Resource Server may exempt CSRF if it accepts only Bearer tokens with no direct browser access, **yet the cookie-receiving BFF must still enforce CSRF** on `POST /web/**`. Identify the exact trust boundary users interact with; never cite backend configuration to justify disabling CSRF on the frontend.

## 4. Standalone Java 17 exercise: classifying credential sources

The code below is solely a **mental model** with deterministic stdout. It cannot analyze browser policies and must never be used as production security middleware.

Save `CsrfDecisionDemo.java`:

```java
import java.util.List;

public class CsrfDecisionDemo {

    record Channel(String name, boolean acceptedByServer,
                   boolean ambientFromBrowser) {}

    static String policy(Channel c) {
        if (!c.acceptedByServer()) {
            return "NOT_AUTHENTICATION";
        }
        if (c.ambientFromBrowser()) {
            return "CSRF_REQUIRED";
        }
        return "EXEMPTION_CAN_BE_REVIEWED";
    }

    public static void main(String[] args) {
        var cases = List.of(
            new Channel("JS Bearer header", true, false),
            new Channel("JWT in cookie", true, true),
            new Channel("WebSession cookie", true, true),
            new Channel("Cached HTTP Basic", true, true),
            new Channel("Ignored cookie", false, true)
        );

        for (Channel c : cases) {
            System.out.println(c.name() + " -> " + policy(c));
        }
    }
}
```

Run:

```bash
javac CsrfDecisionDemo.java
java CsrfDecisionDemo
```

**Exact stdout:**

```text
JS Bearer header -> EXEMPTION_CAN_BE_REVIEWED
JWT in cookie -> CSRF_REQUIRED
WebSession cookie -> CSRF_REQUIRED
Cached HTTP Basic -> CSRF_REQUIRED
Ignored cookie -> NOT_AUTHENTICATION
```

`ambientFromBrowser` must be **evaluated against actual behavior**, not assigned as a gut-feel boolean. Consider cookie domain/path, SameSite, browser versions, gateways/BFFs, and how the server authenticates.

## 5. Default CSRF in Spring Security Reactive

In WebFlux, `@EnableWebFluxSecurity` and `SecurityWebFilterChain` enable CSRF protection by default. `CsrfWebFilter` guards state-changing requests per `ServerWebExchangeMatcher`, typically requiring CSRF on POST/PUT/PATCH/DELETE and skipping GET/HEAD/OPTIONS/TRACE.

This is **distinct** from authentication and authorization:

- **CSRF:** does the browser request carry extra proof that could not be auto-attached by an attack page?
- **Authentication:** are the credentials (session, Bearer, Basic) genuinely valid?
- **Authorization:** is the Authentication permitted to act on this route/record/tenant?

Therefore, in a CSRF-exempt Bearer-only API, POST **without Bearer** must still return 401; valid Bearer **lacking scope** must return 403; valid Bearer **with sufficient scope** can return 200 without a CSRF token. On the browser session chain, a POST missing a CSRF token can return 403 **before** authorization logic runs.

### 5.1. Scope the chain properly

`ServerHttpSecurity.securityMatcher(...)` selects which **`SecurityWebFilterChain`** applies to a URL. `authorizeExchange().pathMatchers(...)` only selects **authorization rules inside the chain**; it **does not restrict the scope** of `csrf.disable()` to a path if that chain matches everything.

An easy-to-audit configuration:

```text
@Order(1): /api/**
    OAuth2 Resource Server Bearer header
    API does not accept WebSession or HTTP Basic for auth
    csrf.disable() applies only to this chain
    scope/role/object-level authorization remains active

@Order(2): browser catch-all
    formLogin + WebSession cookie
    CSRF enabled by default (including POST login/logout)
    explicit authorization, default deny
```

If mixing two authentication types in one chain without eliminating cookie fallbacks, **never** write a matcher like "skip CSRF whenever an `Authorization` header is present". A client-supplied header is not proof that the route never falls back to cookies.

## 6. Java 17+ Spring Boot WebFlux project with two chains

The following project cleanly separates two surfaces:

- `POST /api/transfer`: simulates a write command, accepting only a JWT Bearer header with scope `transfer:write`. **No CSRF token required**, yet signature and scope are still checked.
- `GET /api/public`: public.
- `GET /web/private`: user form login via `WebSession`.
- `POST /web/save`: **requires a valid CSRF token** in addition to the session cookie.
- `GET /web/csrf`: same-origin demo endpoint issuing tokens to protect `POST /web/save`; requires an authenticated session.

Test JWTs are signed with HS256 using a **hardcoded secret strictly for localhost learning**. In production, never expose secrets to clients, never hardcode signing keys, and never let frontends mint JWTs. Use a verified IdP/JWKS, validate `iss`, `aud`, `exp`, `nbf`, scopes, and token types, and enforce key protection/rotation.

### 6.1. Project files and dependencies

```text
csrf-bearer-webflux/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/csrf/
    │   │   ├── CsrfBearerApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/csrf/
        └── CsrfBearerTests.java
```

Uses Java 17+ and Spring Boot `3.5.7` as the curriculum baseline. In real operations, upgrade to supported releases and patches per project policy. Never add `spring-boot-starter-web`, which forces the Servlet stack.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>csrf-bearer-webflux</artifactId>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=csrf-bearer-webflux
server.port=8080
```

`src/main/java/demo/csrf/CsrfBearerApplication.java`:

```java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfBearerApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfBearerApplication.class, args);
    }
}
```

### 6.2. SecurityConfig: only /api/** is CSRF-exempt

`src/main/java/demo/csrf/SecurityConfig.java`:

```java
package demo.csrf;

import java.nio.charset.StandardCharsets;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    static final String DEMO_ISSUER = "https://issuer.example.invalid";

    // Only for signing test JWTs; NEVER use in production.
    static SecretKey demoSecret() {
        String raw = "only-for-local-csrf-demo-secret-key-32bytes";
        return new SecretKeySpec(
            raw.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withSecretKey(demoSecret())
                .macAlgorithm(MacAlgorithm.HS256)
                .build();
        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(DEMO_ISSUER));
        return decoder;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService browserUsers(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(viewer);
    }

    // Bearer-only API: does not use session/Basic as authentication sources.
    @Bean
    @Order(1)
    SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/transfer")
                    .hasAuthority("SCOPE_transfer:write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }

    // Browser-facing WebSession: CSRF remains enabled.
    @Bean
    @Order(2)
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/web/public").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers("/web/**").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

**Explanation:**

1. `@Order(1)` and `securityMatcher` restrict the JWT chain to `/api/**`. Omitting `securityMatcher` would apply `csrf.disable()` to browser routes too.
2. `oauth2ResourceServer().jwt()` extracts the Bearer header and validates the JWT. For valid test JWTs, scope `transfer:write` becomes authority `SCOPE_transfer:write`.
3. `NoOpServerSecurityContextRepository` prevents saving/loading `Authentication` via `WebSession` on the API. Combined with disabling form login and Basic on the API chain, this avoids cookie-auth fallbacks. Still, **never treat `NoOp` alone as sufficient** if a custom filter/proxy derives identity from cookies.
4. `csrf.disable()` applies strictly to the API chain whose threat model fits; `authorizeExchange` and JWT validation remain active.
5. The browser chain uses form login/session cookies; `csrf(Customizer.withDefaults())` retains default protection. Any additional browser POSTs still undergo CSRF matching.

**Production:** replace `DEMO_ISSUER` and demo HS256 with your IdP's issuer/JWK Set URI, validate JWT signatures, `iss`, audience, `exp`, `nbf`, algorithms, scopes/tenants, and token types, and protect tokens on clients. `spring-boot-starter-oauth2-resource-server` provides standard JWT verification; never manually decode payloads and trust claims.

### 6.3. DemoController: keeping Bearer APIs and browser cookies separate

`src/main/java/demo/csrf/DemoController.java`:

```java
package demo.csrf;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record TransferRequest(String destination, int amount) {}

    @GetMapping(value = "/api/public", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> apiPublic() {
        return Mono.just("api-public");
    }

    @PostMapping(value = "/api/transfer",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> transfer(@RequestBody Mono<TransferRequest> request) {
        // Simulation only; performs no real money transfer.
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .zipWith(request)
            .map(t -> "queued:" + t.getT1() + ":"
                + t.getT2().destination() + ":"
                + t.getT2().amount());
    }

    @GetMapping(value = "/web/public", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webPublic() {
        return Mono.just("web-public");
    }

    @GetMapping(value = "/web/private", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webPrivate() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "browser:" + name);
    }

    // Same-origin UI only; do not open permissive CORS.
    @GetMapping(value = "/web/csrf", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> webCsrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());
        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CSRF is unavailable for browser chain"));
        }
        return token.map(value -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .contentType(MediaType.TEXT_PLAIN)
            .body(value.getToken()));
    }

    @PostMapping(value = "/web/save", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webSave() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "saved:" + name);
    }
}
```

`/web/csrf` is a demo endpoint to test issuing CSRF tokens for a logged-in session. The token is read from the exchange attribute keyed by `CsrfToken.class.getName()`. Spring Security Reactive 6.x uses `XorServerCsrfTokenRequestAttributeHandler` by default (BREACH protection), so tokens submitted from valid pages must flow through the proper request handler. Never put CSRF tokens into logs/queries, and never let untrusted origins read this endpoint.

`/api/transfer` never reads `SESSION` cookies; Alice's name comes from the `Authentication` produced when the resource server verifies the JWT, and it returns a simulated result. Real business logic also needs input validation, owner/tenant authorization, idempotency, and transactions.

## 7. WebTestClient testing: evidence instead of assumptions

The test suite runs a real WebFlux server with `@SpringBootTest(RANDOM_PORT)` instead of just testing services or mocking HTTP principals. It mints **real HS256 JWTs** with `NimbusJwtEncoder` in **tests** and sends them in `Authorization: Bearer`. The resource server's decoder verifies signature, issuer, and expiry. Browser tests send session cookies after CSRF-protected form login, then attempt POSTs without and with CSRF.

`src/test/java/demo/csrf/CsrfBearerTests.java`:

```java
package demo.csrf;

import java.time.Instant;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CsrfBearerTests {

    @Autowired
    WebTestClient client;

    private static String token(String scope, boolean expired) {
        JwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableSecret<>(SecurityConfig.demoSecret()));

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(SecurityConfig.DEMO_ISSUER)
            .subject("alice")
            .issuedAt(expired ? now.minusSeconds(3600) : now)
            .notBefore(expired ? now.minusSeconds(3500) : now.minusSeconds(5))
            .expiresAt(expired ? now.minusSeconds(600) : now.plusSeconds(900))
            .claim("scope", scope)
            .build();

        return encoder.encode(JwtEncoderParameters.from(
            JwsHeader.with(MacAlgorithm.HS256).build(), claims))
            .getTokenValue();
    }

    private static String session(
            EntityExchangeResult<?> result, String earlier) {
        ResponseCookie value = result.getResponseCookies()
            .getFirst("SESSION");
        return value == null ? earlier : value.getValue();
    }

    private static String csrfFromHtml(String html) {
        assertNotNull(html);
        Matcher tag = Pattern.compile(
            "(?is)<input\\b(?=[^>]*\\bname\\s*=\\s*['\\\"]_csrf['\\\"])[^>]*>")
            .matcher(html);
        assertTrue(tag.find(), "No _csrf hidden field");

        Matcher value = Pattern.compile(
            "(?i)\\bvalue\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]")
            .matcher(tag.group());
        assertTrue(value.find(), "No CSRF value");
        return value.group(1);
    }

    private String loginBrowser() {
        EntityExchangeResult<String> page =
            client.get().uri("/login")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String cookie = session(page, null);
        assertNotNull(cookie, "Missing SESSION cookie");
        String csrf = csrfFromHtml(page.getResponseBody());

        EntityExchangeResult<byte[]> login =
            client.post().uri("/login")
                .cookie("SESSION", cookie)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "viewer")
                    .with("password", "viewer123")
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = login.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertFalse(location.contains("error"));
        return session(login, cookie);
    }

    @Test
    void publicApiDoesNotRequireAuth() {
        client.get().uri("/api/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api-public");
    }

    @Test
    void apiPostWithoutBearerIs401NotCsrf403() {
        client.post().uri("/api/transfer")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void validBearerPostWithoutCsrfSucceeds() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBearerAuth(token("transfer:write", false)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("queued:alice:demo:1");
    }

    @Test
    void validJwtWithoutRequiredScopeIs403() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBearerAuth(token("profile:read", false)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void expiredJwtIs401() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBearerAuth(token("transfer:write", true)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicCannotReplaceBearer() {
        client.post().uri("/api/transfer")
            .headers(h -> h.setBasicAuth("viewer", "viewer123"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void tokenCookieIsNotAcceptedAsBearerHeader() {
        client.post().uri("/api/transfer")
            .cookie("access_token", token("transfer:write", false))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void browserSessionCookieCannotAuthorizeBearerApi() {
        String cookie = loginBrowser();
        client.post().uri("/api/transfer")
            .cookie("SESSION", cookie)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void bearerStillAuthorizesWhenUnrelatedSessionCookieExists() {
        String cookie = loginBrowser();
        client.post().uri("/api/transfer")
            .cookie("SESSION", cookie)
            .headers(h -> h.setBearerAuth(token("transfer:write", false)))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"destination\":\"demo\",\"amount\":1}")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("queued:alice:demo:1");
    }

    @Test
    void anonymousBrowserRouteRedirectsToLogin() {
        client.get().uri("/web/private")
            .exchange().expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void bearerDoesNotAutomaticallyLogIntoBrowserChain() {
        client.get().uri("/web/private")
            .headers(h -> h.setBearerAuth(token("transfer:write", false)))
            .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void browserLoginPostWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "viewer")
                .with("password", "viewer123"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void authenticatedBrowserPostWithoutCsrfIsRejected() {
        String cookie = loginBrowser();

        client.post().uri("/web/save")
            .cookie("SESSION", cookie)
            .exchange().expectStatus().isForbidden();

        client.get().uri("/web/private")
            .cookie("SESSION", cookie)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("browser:viewer");
    }

    @Test
    void browserPostWithValidCsrfIsAccepted() {
        String cookie = loginBrowser();

        EntityExchangeResult<String> csrfResponse =
            client.get().uri("/web/csrf")
                .cookie("SESSION", cookie)
                .exchange().expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String csrf = csrfResponse.getResponseBody();
        assertNotNull(csrf);
        assertFalse(csrf.isBlank());

        client.post().uri("/web/save")
            .cookie("SESSION", cookie)
            .header("X-CSRF-TOKEN", csrf)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("saved:viewer");
    }
}
```

Run:

```bash
mvn test
```

With the classes above, the target is **14 tests**. This curriculum is for readers to run in an appropriate environment; **no claim is made that tests were executed** in your project. The JWT signing helper is strictly for local testing: never put secrets in frontends or production, and never turn the demo into an Authorization Server.

### 7.1. Why are the negative tests meaningful?

- **No Bearer -> 401**, not CSRF 403: proves CSRF is exempted **while authentication still runs**.
- **Valid Bearer, no CSRF -> 200:** proves the exempted case behaves as intended.
- **Valid Bearer, missing scope -> 403:** proves `hasAuthority("SCOPE_transfer:write")` remains intact.
- **Expired JWT -> 401:** proves disabling CSRF did not skip JWT validation.
- **HTTP Basic -> 401** and **JWT in cookie -> 401:** the API has no ambient credential fallback.
- **Real browser WebSession cookie without Bearer -> 401:** proves `WebSession` never grants Authentication on the API.
- **WebSession cookie + valid Bearer -> 200:** browsers may attach unrelated cookies; the API still authenticates via Bearer.
- **Browser POST without CSRF -> 403**, yet POST with same session and valid token -> 200: CSRF remains active on the cookie-auth chain.
- **Bearer header hitting a browser route does not auto-login:** the two chains keep auth schemes isolated.

`WebTestClient` is an HTTP client that sets headers/cookies arbitrarily: it verifies **server** configuration, not whether real browsers send cookies per SameSite or issue preflights. Full verification requires cross-origin browser tests and proxy/gateway checks.

## 8. Manual testing with curl

Run `mvn spring-boot:run` and open another terminal:

```bash
curl -i http://localhost:8080/api/public

curl -i -X POST http://localhost:8080/api/transfer \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'

curl -i -X POST http://localhost:8080/api/transfer \
  -H 'Cookie: access_token=not-a-token' \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'

curl -i --user viewer:viewer123 -X POST \
  http://localhost:8080/api/transfer \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'

curl -i http://localhost:8080/web/private
curl -i -X POST http://localhost:8080/web/save
```

Expected: public API 200; the three API POST commands lacking valid Bearer return **401**; unauthenticated `GET /web/private` redirects to `/login`; `POST /web/save` without a CSRF token returns **403**. On Windows PowerShell, if `curl` is an alias, use `curl.exe`.

To send a **valid** Bearer token:

```bash
# Replace placeholder with a validly issued JWT; DO NOT paste this literal string.
curl -i -X POST http://localhost:8080/api/transfer \
  -H 'Authorization: Bearer <VALID_SIGNED_TEST_JWT>' \
  -H 'Content-Type: application/json' \
  -d '{"destination":"demo","amount":1}'
```

This command contains a **placeholder**. The test code in Section 7 mints properly signed HS256 tokens and sends real requests, so `mvn test` verifies the happy path **without an external IdP**. There is no arbitrary token-minting endpoint in the demo; real systems obtain tokens from an Authorization Server. Never put real tokens/passwords in shell history/logs; use HTTPS outside localhost.

## 9. CORS, SameSite, Origin, and Fetch Metadata are separate layers

### 9.1. CORS is not proof CSRF is solved

CORS governs whether browsers can execute certain cross-origin fetches and read responses. A JavaScript-added `Authorization` header typically triggers a preflight because it is not a safelisted header. However:

- HTML `form` POSTs or top-level navigations follow different rules from custom-header `fetch`.
- A CSRF attack may only need to **send the request**, without reading the response.
- CORS does not validate usernames, JWTs, permissions, or CSRF tokens.
- If an API uses session cookies, never disable CSRF just because CORS is restricted.
- Never enable `Access-Control-Allow-Origin: *` with credentials as a way to "fix" SPA requests; use a narrow origin allowlist per policy.

### 9.2. SameSite does not replace full CSRF protection

`SameSite=Lax`/`Strict` cookies can curb certain cross-site requests carrying cookies, yet **site differs from origin**. Another subdomain can be *same-site* yet *cross-origin*, and attackers may control another subdomain in some setups. Older browsers/clients, cookie domain/path, navigation exceptions, and SSO flows needing `SameSite=None; Secure` can all alter outcomes. When cookies authenticate requests on the server, **keep CSRF protection**.

### 9.3. Origin/Referer/Fetch Metadata

`Origin`, `Referer`, and `Sec-Fetch-Site` can help block cross-site requests as an additional layer. You must handle missing headers, trusted proxy origins, same-site subdomains, unsupported browsers, and CLI/mobile clients. Never deduce that an absent header means a request is safe, nor assume every CLI request sends `Origin`. If deployed, define explicit policies and test thoroughly.

### 9.4. GET must be genuinely safe

The default CSRF matcher does not require tokens for GET/HEAD. Therefore **never** write `GET /delete`, `GET /logout-all`, or a GET that transfers funds. Even on a Bearer-only API, state-mutating GETs create risks via links, navigations, caches, and retries. Use semantically proper methods, guard against replays where needed, and enforce authorization.

## 10. Architecture upgrade scenarios and common traps

**Trap 1 – "Our API is stateless so disable CSRF globally."** A self-contained cookie JWT needs no server session yet is still auto-sent by browsers. Calling it stateless does not change the CSRF model.

**Trap 2 – "JWT is Bearer, so CSRF isn't needed even when the JWT is in a cookie."** False. If the server reads a JWT from a cookie to create the principal, treat it as an ambient credential.

**Trap 3 – "Just add `authorizeExchange.pathMatchers("/api/**")` and call `csrf.disable()`."** Insufficient scope. Disabling affects the whole chain; use `securityMatcher`/separate chains.

**Trap 4 – "Authorization header is present so it's exempt."** HTTP Basic can be cached by browsers; gateways can synthesize Bearer from cookies. Verify the source of trust and fallbacks.

**Trap 5 – "CORS already blocks cross-site requests."** CORS does not block all HTML forms or request triggers, and does not replace CSRF validation when cookies are ambient.

**Trap 6 – "SameSite=Strict solves everything absolutely."** Same-site subdomains and evolving browser/cookie policies can break assumptions. Keep CSRF whenever authentication relies on cookies.

**Trap 7 – "No CSRF means we can skip authentication/authorization."** They are three distinct mechanisms. Bearer still needs signatures, issuer/audience/expiry, scopes, and object-level checks.

**Trap 8 – "The BFF uses Bearer downstream, so skip CSRF on the BFF."** The browser-facing BFF still accepts `SESSION` cookies and needs CSRF for mutations.

**Trap 9 – "Only test valid Bearer returning 200."** Must also include cookie-only 401, Basic-only 401, expired token 401, wrong scope 403, and browser CSRF 403.

**Trap 10 – "No CSRF risk means the app has no risks."** XSS can steal Bearer tokens, tokens can leak via logs/URLs, JWT validators can be misconfigured, and CORS/proxies can be overly open. Build a dedicated threat model.

### 10.1. If chains cannot be separated

`ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(ServerWebExchangeMatcher)` lets you choose which requests require CSRF via a matcher, yet **never** write a matcher skipping CSRF whenever an arbitrary `Authorization` header appears. An endpoint accepting both cookies and Bearer tokens still has an ambient credential path; if you cannot remove the cookie fallback, the simpler and safer choice is to **keep CSRF on state-changing requests**.

Illustrative fragment, **not a complete configuration**:

```java
// browserMutatingMatcher must reflect real ROUTE + authentication policy,
// not just client-supplied headers.
http.csrf(csrf -> csrf
    .requireCsrfProtectionMatcher(browserMutatingMatcher));
```

A chain scoped by `securityMatcher("/api/**")` is easier to audit and test than a complex header-inspecting matcher. Whenever an API changes authentication methods, update tests/policies together.

### 10.2. Proxies can overturn the entire conclusion

If browsers send cookies to an API gateway and the gateway converts them into a Bearer header for the resource server, the backend sees only Bearer **yet the ingress remains vulnerable to CSRF without protection**. Evaluate along **user-agent -> first service accepting ambient credentials**, not solely downstream service logs.

## 11. Pre-exemption review checklist

1. **Inventory auth sources:** Bearer headers, token cookies, `WebSession`, Basic, custom proxy principals, OAuth2 login; prove the route has no ambient fallbacks.
2. **Verify chains:** `@Order`, `securityMatcher`, default deny, URL rewrites, gateway paths, and route matching.
3. **Test cookie-only -> 401** on every state-changing Bearer-only API, including a real `SESSION` cookie logged in on the website.
4. **Test Basic-only -> 401**, token-cookie-only -> 401, expired/invalid JWT -> 401.
5. **Test valid Bearer without CSRF -> 2xx** and wrong scope -> 403; never grant access to invalid credentials.
6. **Keep CSRF on the browser chain**, including POST login/logout/session mutations; test missing token -> 403 and valid token + session -> 2xx.
7. **Verify JWT/opaque validation:** signature or introspection, issuer, audience, `exp`, `nbf`, type, key rotation, and scope/tenant.
8. **Verify browser credential policies:** `SameSite`, `Secure`, `HttpOnly`, fetch credentials mode, Basic cache, subdomains, and SSO/BFF.
9. **Verify CORS and Origin:** narrow allowed origins, preflights, Fetch Metadata/Origin/Referer as defense-in-depth rather than sole grounds to drop CSRF.
10. **Verify XSS/token storage:** CSP, output escaping, scripts, refresh-token lifecycles, never putting tokens in URLs/logs.
11. **Verify method safety:** GET has zero side effects; mutations enforce validation and idempotency/transactions where needed.
12. **CI regressions:** any change to auth transport, proxies, login, or cookie handling must re-run negative tests.
13. **Test beyond localhost:** real browsers on another origin, real reverse proxies/ingress, and cross-browser cookie policies.
14. **Document the decision:** exact exempted paths, why credentials are non-ambient, and conditions requiring CSRF to be re-enabled.

## 12. Self-assessment questions

**1.** An API accepts only Bearer headers explicitly set by trusted JavaScript; attack websites lack the token. Can CSRF be exempted?  
**May be considered** strictly within that API's scope, after proving no cookie/Basic/session fallback exists while still enforcing authentication/authorization.

**2.** Moving the JWT into an `HttpOnly` cookie. Does the previous conclusion still hold?  
**No.** Cookies can be auto-sent by browsers; CSRF must be re-evaluated and usually requires protection.

**3.** A BFF receives `SESSION` and calls downstream services with Bearer. Do browser POSTs to the BFF need CSRF?  
**Yes.** The browser-facing boundary relies on an ambient cookie.

**4.** A browser sends an unrelated cookie alongside Bearer; the API always ignores cookies. Does that cookie grant authority?  
**No.** Prove it with a cookie-only 401 test.

**5.** Why must a Bearer-only API POST missing a token return 401 instead of CSRF 403?  
Because CSRF is exempted on the API chain, **yet authentication is still required**.

**6.** What does a POST with a validly signed Bearer lacking the required scope receive?  
**403 Forbidden** per authorization policy.

**7.** Can CORS replace CSRF on a session-cookie endpoint?  
**No.** CORS does not stop all form/navigation requests and does not replace synchronizer CSRF tokens.

**8.** HTTP Basic uses the `Authorization` header—is it CSRF-exempt like JS-set Bearer?  
**Never assume so.** Browsers can auto-send cached Basic credentials.

**9.** Does merely calling `authorizeExchange.pathMatchers("/api/**")` scope `csrf.disable()` solely to `/api/**`?  
**No.** You need `securityMatcher` or a proper CSRF matcher.

**10.** If XSS steals a Bearer token, is CSRF exemption the sole cause?  
**No.** Token theft/XSS is a separate threat model; protect frontend/tokens and backend authorization.

### Official References

- Spring Security 6.5, *CSRF for WebFlux*: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security, *CSRF Considerations* (stateless/cookie/HTTP Basic): https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security 6.5, `ServerHttpSecurity.CsrfSpec` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security 6.5, *Reactive OAuth2 Resource Server JWT*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- OWASP, *Cross-Site Request Forgery Prevention Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- MDN, *Request.credentials*: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN, *Set-Cookie SameSite*: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie

**In summary:** Any decision to exempt CSRF must rest on **how browsers can auto-attach credentials accepted by the server**. A Bearer header actively attached by trusted clients on a Bearer-only API can be a valid exemption; JWT/session cookies, browser Basic auth, and BFF cookies are not. Separate `SecurityWebFilterChain` configurations, keep CSRF for browsers, and verify with both happy-path and negative tests before deploying.