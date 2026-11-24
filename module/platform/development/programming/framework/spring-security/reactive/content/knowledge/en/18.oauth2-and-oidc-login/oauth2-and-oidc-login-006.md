# state, nonce, PKCE, and Login Flow Protection Constraints

## Learning Objectives

This lesson belongs to the **OAuth2/OIDC Login** section of **Spring Security reactive (Spring WebFlux)**. After this lesson, you will be able to:

- Draw the **Authorization Code Flow** with OpenID Connect (OIDC) accurately, distinguishing the browser, OAuth2 client/Relying Party, Authorization Server/Identity Provider (IdP), and resource server.
- Understand that **`state`** binds the authorization response to the **original login request and browser session**, **`nonce`** binds the **ID Token** to the OIDC authentication session, and **PKCE (Proof Key for Code Exchange)** binds the **authorization code** to the client holding `code_verifier`.
- State accurately the roles and limits of `code_verifier`, `code_challenge`, `S256`, `iss`, `aud`, `exp`, `redirect_uri`, and `registrationId`.
- Explain why you must defend against **login CSRF, authorization-code injection, code interception, token substitution/replay, IdP mix-up, open redirect, and redirect URI manipulation**.
- Use `ServerHttpSecurity.oauth2Login(...)`, `DefaultServerOAuth2AuthorizationRequestResolver`, and `OAuth2AuthorizationRequestCustomizers.withPkce()` for a Java 17 WebFlux application.
- Know that Spring Security stores authorization requests in `WebSessionOAuth2ServerAuthorizationRequestRepository` by default; never turn `state` or the PKCE verifier into a constant or read them from user query parameters as proof of authentication.
- Run a Java 17 program demonstrating **PKCE S256 with deterministic output**, configure a WebFlux OAuth2/OIDC client, and **test authorization request creation offline** without a real IdP.
- Design negative tests: missing/wrong/replayed state, mismatched PKCE verifier, wrong ID Token nonce, wrong issuer/audience, and callback using the wrong session.

> **Scope:** Spring Security **reactive**, OAuth2 **Authorization Code + OIDC**. Do not confuse with `OAuth2 Resource Server` which only validates API Bearer tokens, or Servlet's `HttpSecurity`/`HttpSessionOAuth2AuthorizationRequestRepository`. This lesson focuses on constraints against spoofing/code injection in **login**, not building an Authorization Server from scratch.

## 1. state, nonce, and PKCE Solve Three Different Questions

When the browser starts logging in via an IdP, the app sends the user outside its own origin and later receives a callback. Merely seeing `code` on the callback **does not prove** it is the result of the current login request.

| Mechanism | Security Question | Where Created? | Where Does It Appear? | How Is It Checked? |
|---|---|---|---|---|
| **state** | “Does this callback belong to the login request just initiated in this browser/session?” | OAuth2 client | Authorization request and callback (`state`) | Compared against the stored/browser-bound authorization request; reject if missing/wrong/reused. |
| **OIDC nonce** | “Was this ID Token issued for **this authentication attempt**?” | OIDC client | Authorization request (`nonce`), then in ID Token `nonce` claim | After verifying the ID Token signature, compare `nonce` per client/framework rules. |
| **PKCE** | “Does the party exchanging the authorization code hold the ephemeral secret bound to this code?” | OAuth2 client | `code_challenge` in authorization request; **`code_verifier` in token request** | The Authorization Server checks the challenge/verifier transformation bound to the code. |
| **redirect_uri** | “Is the code returned only to the registered callback endpoint?” | Client registered at IdP | Authorization request and callback destination | The IdP performs exact redirect URI matching; the client binds the code/token request to that URI. |
| **issuer/audience** | “Did this token come from the right IdP and is it meant for the right client?” | Authorization Server | ID Token and metadata | The client verifies signature, `iss`, `aud`, lifetime, and `azp` when applicable. |

**Do not treat the three values as one:** `state` does not make a stolen code useless at the token endpoint; an OIDC `nonce` is not an access token; PKCE does not replace all ID Token/issuer checks or user status validation.

Recent security standards (RFC 9700, Jan 2025) note that PKCE and `nonce` can also provide CSRF-mitigation benefits under very specific conditions, but when using Spring Security OAuth2 Login, **keep state/session binding intact and use PKCE + OIDC nonce for defense in depth**. Do not drop one check just because another is present.

## 2. Authorization Code + OIDC: Flow Diagram

Scenario: a WebFlux application at `https://app.example.test` wants to log in via `https://idp.example.test`:

~~~text
Browser                  WebFlux OAuth2 Client             OIDC IdP
  |                              |                             |
  | GET /oauth2/authorization/oidc                           |
  |----------------------------->|                             |
  |                              | Generate state S            |
  |                              | Generate OIDC nonce N       |
  |                              | Generate PKCE verifier V    |
  |                              | challenge C = BASE64URL(    |
  |                              |     SHA256(ASCII(V)))       |
  |                              | Save request + V + N in     |
  |                              | WebSession-bound repository |
  |<----- 302 authorize? --------|                             |
  |       response_type=code     |                             |
  |       client_id=...          |                             |
  |       redirect_uri=...       |                             |
  |       scope=openid ...       |                             |
  |       state=S                |                             |
  |       nonce=N / hash(N)      |                             |
  |       code_challenge=C       |                             |
  |       code_challenge_method=S256                           |
  |----------------------------------------------------------->|
  |                              |                      Login/consent
  |<------------------------ 302 callback?code=K&state=S -----|
  | GET /login/oauth2/code/oidc?code=K&state=S                |
  |----------------------------->|                             |
  |                              | Load saved request for S    |
  |                              | Reject if state/session bad |
  |                              | POST /token: code=K, V ...  |
  |                              |---------------------------->|
  |                              |         Validate V against C|
  |                              |<----------------------------|
  |                              | access_token + id_token     |
  |                              | Validate ID Token: sig,     |
  |                              | iss, aud, exp, nonce etc.   |
  |                              | Establish local login       |
  |<------ Login success/redirect|                             |
~~~

In Spring Security 6.x, the OIDC request resolver may store the **raw nonce value in the authorization-request attributes** while placing a **nonce-derived value** into the request sent to the IdP; upon receiving the ID Token, the OIDC authentication manager verifies the corresponding binding rule. Therefore, **do not compare a raw `nonce` string by eye** when using the framework's hashed nonce mechanism. What matters is that both the **request nonce** and **ID Token nonce** are verified by the same implemented rule.

In real flows, the redirect is usually HTTP 302; final status and login pages vary by IdP/client config. Codes, access tokens, and ID Tokens must be treated as sensitive data; never paste real callback URLs into tickets or public logs.

## 3. state: Preventing Forged Callbacks and Login CSRF

### 3.1. State Acts as a Correlation Token

On the login-initiation request, the client generates a **random, unpredictable, per-attempt** `state`. The client saves the associated `OAuth2AuthorizationRequest` in the browser's session/repository. The IdP receives `state` and must return the exact same value in the authorization response.

**Illustrative URL example (not real tokens):**

~~~text
GET /oauth2/authorization/oidc
    -> 302 https://idp.example.test/authorize?
         response_type=code&
         client_id=client-web&
         state=S_X7m...&
         redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Foidc

Valid callback:
GET /login/oauth2/code/oidc?code=K_abc&state=S_X7m...

Tampered callback:
GET /login/oauth2/code/oidc?code=K_abc&state=S_attacker
    -> rejected; code must not be used to create a local session
~~~

Think of `state` as an **opaque value**, not an object containing a trusted user ID or role. Another session must not be allowed to use this session's state to legitimize a callback.

### 3.2. What Is Login CSRF?

A dangerous scenario: an attacker logs in at the IdP using the **attacker's account**, obtains an authorization response, and forces the victim's browser to hit the callback so the victim's app establishes a session pointing to the attacker's account. The victim believes they are using their own account while actually writing data into the attacker's account.

The attacker does not need the victim's password; this is **login CSRF / session swapping**. Binding `state` to the browser's login attempt ensures the app rejects an unrelated callback.

Rules to uphold:

1. The callback must carry a `state` matching an **outstanding authorization request** saved in the session/client context.
2. A completed request must be **removed/marked used** to prevent replay.
3. Expired or missing requests (session expired, lost cookie, another flow started) must fail closed.
4. When a client supports multiple IdPs, `state` must also bind to the **intended registration/issuer**, never sending a code received from IdP A to IdP B's token endpoint.
5. Never let an attacker control `state` by sending `?state=...` and having the server accept it as truth.

### 3.3. State Is Not a Place for Arbitrary Return URLs

Some apps want to return to `/orders/123` after login. Never build `state` by concatenating an arbitrary client-supplied URL and trusting that any return target inside a valid-state callback is safe.

A cleaner design:

~~~text
Before redirect:
  server validates return path is an allowed internal path
  server saves return path in session/cache by transaction ID
  server generates random state

After callback:
  validate state + session + issuer
  retrieve the server-validated return path
  redirect to internal path, never to an arbitrary host
~~~

If `state` carries meaningful payload, it needs **integrity protection** (signing/encryption if needed), session binding, and expiration. Never reflect `return_to=https://evil.example.test` into the post-login `Location` just because it was inside `state`. Open redirects can leak authorization codes or access tokens.

## 4. nonce: Binding the ID Token to an OIDC Authentication Attempt

### 4.1. How Does nonce Differ from state?

`nonce` is a parameter of the **OpenID Connect Authentication Request**. The IdP places a corresponding `nonce` value into the issued **ID Token**. The client verifies the match per the library's algorithm/configuration, preventing **ID Token replay/substitution** across authentication transactions.

- `state` returns in the **authorization response/callback**.
- `nonce` goes into the **signed ID Token**, received after the client exchanges the code.
- `nonce` is not `code_verifier` and must not be sent to the token endpoint as a PKCE secret.
- `nonce` must be per-attempt; never use a constant like `nonce="demo"`.
- Do not check only `nonce`: the ID Token still requires verifying the **JWS signature**, issuer, audience, expiration, and required claims.

### 4.2. ID Token Claims That Must Be Verified

An **illustrative** ID Token payload, not a valid signature or JWT:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "user-123",
  "aud": "web-client-id",
  "exp": 1893456000,
  "iat": 1893452400,
  "nonce": "expected-nonce-or-its-framework-derived-value"
}
~~~

Meaning:

| Claim | What to Verify |
|---|---|
| `iss` | Matches expected issuer; never accept tokens from an arbitrary IdP. |
| `sub` | User identifier at the issuer; durable user keys should combine **issuer + sub**, not email alone. |
| `aud` | Contains the app's client_id; if multiple audiences exist, handle `azp` per OIDC. |
| `exp`/`iat` | Token is not expired, timestamps are reasonable, and clock skew policy is respected. |
| `nonce` | Matches the request nonce per implementation, preventing token replay/substitution. |
| Signature `alg`/`kid`/JWKS | JWS must be verified with **trusted configured** algorithms/keys; never trust an arbitrary `alg` from the token. |

Never use “the JWT looks like Base64” or a JSON payload containing `sub` as proof of authentication. Decoding a payload without a valid signature **is not validation**.

### 4.3. Spring Security's Default Nonce Handling

For an OIDC `ClientRegistration` with the `openid` scope, `DefaultServerOAuth2AuthorizationRequestResolver` creates the nonce binding for the authorization request. In Spring Security 6.x versions, the framework uses a hashing mechanism to pass a derived nonce in the request while retaining the verification material in the authorization request's attributes.

When OIDC login completes, `OidcAuthorizationCodeReactiveAuthenticationManager` along with OIDC decoders/user services verify the token and associated conditions. **Do not overwrite/remove `nonce` in a customizer**, and never strip `scope=openid` down to `scope=profile` expecting an OIDC ID Token to still be validated.

An OAuth2 provider **that does not support OIDC** may not issue an ID Token; in that case there is no OIDC nonce validation. Never fabricate an ID token to trick `oauth2Login` into treating it as OIDC.

## 5. PKCE: Per-Login Secret Protecting the Authorization Code

PKCE (RFC 7636) is pronounced “pixy”. It is designed to reduce risk when an **authorization code is intercepted or injected** in transit. The core idea: someone who only knows the code cannot exchange it for an access token without knowing the corresponding `code_verifier` secret.

### 5.1. The S256 Formula

The client generates:

1. `code_verifier`: a **cryptographically random** string of 43–128 characters from the RFC 7636 URI-unreserved alphabet.
2. `code_challenge`: `BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))`, **without padding**.
3. `code_challenge_method=S256`.

~~~text
V = random code_verifier (kept secret in transaction store)
C = BASE64URL_NOPAD(SHA256(ASCII(V)))

Authorization request:
  response_type=code
  code_challenge=C
  code_challenge_method=S256

Token request:
  grant_type=authorization_code
  code=K
  code_verifier=V

Authorization Server:
  C_stored_for_code == BASE64URL_NOPAD(SHA256(ASCII(V))) ?
      yes -> continue checking code/client/redirect_uri and issue tokens
      no  -> reject token request
~~~

`code_verifier` **must never be sent in the authorize URL**. `code_challenge` can appear in the authorize URL because it is a one-way derivation; the critical secret is the verifier. The Authorization Server must bind the code to the challenge sent when issuing the code and **enforce** the check at the token endpoint.

### 5.2. Why S256 Is Recommended Over plain

PKCE has a `plain` method where the challenge equals the verifier itself. If an attacker observes the authorization request, they immediately obtain the verifier and the protection is severely weakened. RFC 9700 recommends using a method that does not expose the verifier in the authorization request; **S256** is the standard, widely supported method.

Never silently fall back to `plain` when an IdP rejects S256. For security-sensitive apps, the IdP must properly support PKCE; otherwise evaluate upgrading or switching providers rather than weakening protection.

### 5.3. Public Client vs. Confidential Client

| Client Type | Can It Keep a Client Secret Safely? | Should PKCE Be Used? |
|---|---|---|
| Pure JavaScript SPA, mobile/native (public) | No, if the secret ships in the client bundle. | **Mandatory best practice**; authorization code + PKCE. |
| Backend WebFlux/BFF (confidential) | Can keep the secret on the server. | **Still recommended** to defend against code interception/injection; a secret does not replace PKCE. |
| Service-to-service client credentials | Does not use browser authorization codes. | PKCE does not apply to the `client_credentials` grant. |

Spring Security 6.5 automatically adds PKCE for public clients when `client-authentication-method=none` (no client secret) or when `ClientRegistration.clientSettings.requireProofKey=true`. For **confidential OAuth2 Login**, you can explicitly require PKCE using `OAuth2AuthorizationRequestCustomizers.withPkce()`, as shown below.

### 5.4. Pure Java 17: Computing a PKCE S256 Challenge Yourself

The following example **runs standalone with JDK 17 only**, using the public test vector from RFC 7636; this is **not** how you should replace Spring Security's PKCE implementation.

File `PkceS256.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

public final class PkceS256 {
    private PkceS256() {
    }

    public static String challenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public static void main(String[] args) {
        // RFC 7636 Appendix B: PUBLIC test vector, not a real secret.
        String verifier =
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";

        System.out.println(challenge(verifier));
    }
}
~~~

Run:

~~~bash
javac PkceS256.java
java PkceS256
~~~

**Exact stdout**:

~~~text
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

This is a **fixed test vector to verify the formula**; never use this fixed verifier in real logins. In real deployments, let Spring Security generate a cryptographically random verifier for **each login attempt** and store it alongside the authorization request.

### 5.5. What Happens If an Attacker Obtains the Code?

If authorization code `K` leaks from a callback URL or reverse proxy log:

- **Without PKCE:** the attacker may attempt to redeem the code, depending on public/confidential client authentication and other constraints.
- **With proper PKCE S256:** the attacker has `K` but lacks `V`; the IdP rejects the token request due to a mismatched `code_verifier`.
- **If XSS/server compromise leaks `V` as well:** PKCE no longer helps because the attacker has everything.
- **If the IdP does not enforce PKCE or allows downgrade:** sending a challenge from the client is not enough; you must test that the IdP actually rejects missing/invalid verifiers.

PKCE also does not replace **token recipient validation** (`iss`/`aud`), TLS, session/cookie protection, or business-level authorization.

## 6. How Does Spring Security Reactive Manage Request Correlation?

Typical components in WebFlux OAuth2 Login:

| Component | Role |
|---|---|
| `OAuth2AuthorizationRequestRedirectWebFilter` | Intercepts login-initiation requests and builds the redirect to the IdP Authorization Endpoint. |
| `ServerOAuth2AuthorizationRequestResolver` | Creates an `OAuth2AuthorizationRequest` for a client registration. |
| `DefaultServerOAuth2AuthorizationRequestResolver` | Default resolver; matches `/oauth2/authorization/{registrationId}` and creates state/nonce, plus PKCE per client settings/customizer. |
| `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Stores/retrieves the original request between redirect and callback. |
| `WebSessionOAuth2ServerAuthorizationRequestRepository` | Default repository storing requests in `WebSession`, binding callbacks to the browser session. |
| `OAuth2LoginAuthenticationWebFilter` | Processes authorization response callbacks, retrieves the original request, and starts authentication. |
| `WebClientReactiveAuthorizationCodeTokenResponseClient` | Exchanges the code for tokens at the token endpoint, including `code_verifier` when PKCE applies. |
| `OidcAuthorizationCodeReactiveAuthenticationManager` | Handles OIDC authorization code login and verifies the relevant ID Token conditions. |
| `ReactiveOidcIdTokenDecoderFactory` | Builds the decoder verifying ID Token signatures per client registration config. |
| `ServerSecurityContextRepository` | Saves verified Authentication for the login session, distinct from the pending authorization request repository. |

### 6.1. Why Store OAuth2AuthorizationRequest in WebSession?

While the browser leaves the app for the IdP, the client must remember the **original state, PKCE verifier, nonce, redirect URI, registration ID, and other attributes**. When the callback returns, the repository retrieves the matching transaction from the browser's `WebSession`, verifies `state`, and proceeds with the token exchange.

**Never** build an unbounded/TTL-less singleton `Map<String, OAuth2AuthorizationRequest>` to replace the repo, as it causes data leaks, replay, concurrency races, memory leaks, and multi-instance failures. If a custom repository distributes state via Redis/database, ensure:

- `state` has sufficient entropy, and data is protected against reads/modifications by other tenants/browsers.
- Each transaction has a short TTL and is consumed **once** at callback.
- Binding to the browser/session and client/issuer is preserved.
- Concurrent tabs (multiple login attempts) are handled explicitly; never silently overwrite another tab's transaction.
- The session store is consistent and sticky/non-sticky load balancers are handled properly.
- Never log `code_verifier`, raw nonces, session cookies, or authorization codes.

### 6.2. Do Not Disable CSRF or Log Users In via a Callback Controller

The OAuth2 authorization callback is handled by Spring Security's OAuth2 login filter. Never write a controller like:

~~~java
// ANTI-EXAMPLE: do not do this.
@GetMapping("/login/oauth2/code/oidc")
public Mono<String> dangerous(@RequestParam String code) {
    // Has not validated state/PKCE/nonce/issuer; must not create login.
    return Mono.just("logged in");
}
~~~

This is an erroneous pattern, not working login code. A controller that reads `code` directly and creates Authentication from a query string is a vulnerability; delegate callback handling to the tested framework/identity library.

### 6.3. Automatic PKCE vs. Enforced PKCE via Customizer

Spring Security 6.5 supports public clients, and provides an API to enforce PKCE on authorization requests for **confidential** clients when the IdP supports it:

~~~java
DefaultServerOAuth2AuthorizationRequestResolver resolver =
    new DefaultServerOAuth2AuthorizationRequestResolver(
        clientRegistrationRepository);

resolver.setAuthorizationRequestCustomizer(
    OAuth2AuthorizationRequestCustomizers.withPkce());
~~~

This is a **configuration fragment**; you must wire `resolver` into `http.oauth2Login(...)`. Spring Security adds `code_challenge`/`code_challenge_method` and stores `code_verifier` in `OAuth2AuthorizationRequest.attributes` for reuse on the token request.

**Never write a customizer that replaces all `additionalParameters`/`attributes` and accidentally wipes out `nonce`, PKCE metadata, or `registrationId`.** If you only need to add `prompt=login`, preserve existing security values through controlled mutation.

## 7. Spring Boot WebFlux Java 17 App Example: OAuth2 Login + PKCE S256

This is a **Java 17 / Spring Boot 3.5.16** application using Boot-managed Spring Security dependencies. Startup and authorization-request tests run locally; **end-to-end login requires a real configured OIDC IdP**. Never claim callback/token validation succeeds merely because Spring Boot booted without a provider.

### 7.1. Project Structure

~~~text
reactive-oidc-login-security/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/ReactiveOidcLoginApp.java
    │   └── resources/application.yml
    └── test/
        └── java/example/AuthorizationRequestSecurityTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'reactive-oidc-login-security'
~~~

File `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use JDK 17+ and a Gradle/Wrapper compatible with Spring Boot 3.5. `spring-boot-starter-oauth2-client` is essential: the security starter alone cannot initialize OAuth2/OIDC Login. Never mix Servlet's `spring-boot-starter-web` into this WebFlux lesson.

### 7.2. application.yml and IdP Registration Values

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          oidc:
            provider: corporate-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corporate-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

**Must be replaced with real environment variables**, for example an **HTTPS** URL of an OIDC provider owned by the organization. The YAML placeholder syntax once you create the file is `${OIDC_ISSUER_URI}` (the source presentation uses a backslash escape in the text to preserve the template; when copying into real YAML, **omit any backslash before the $**). Variables:

- `OIDC_CLIENT_ID`: Client ID issued by the IdP.
- `OIDC_CLIENT_SECRET`: Client secret of the confidential backend client; store in a secret manager/env, **never commit to the repository**.
- `OIDC_ISSUER_URI`: OIDC issuer URI; the IdP must expose valid HTTPS discovery metadata.
- `scope: openid,profile,email`: includes `openid` for OIDC ID Token and nonce; adjust other scopes as needed.
- `redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"`: callback URI matching WebFlux OAuth2 Login's default endpoint and **must be registered identically at the IdP**.

**Note on discovery:** When using `issuer-uri`, Spring Boot/Spring Security may query the IdP's OIDC discovery metadata; the app only starts if the issuer is reachable and consistent. This is not an IdP simulator. The offline test in section 8 creates a registration in memory so it **does not connect** to any issuer URL.

### 7.3. Complete Application

File `src/main/java/example/ReactiveOidcLoginApp.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.server.DefaultServerOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveOidcLoginApp {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveOidcLoginApp.class, args);
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ReactiveClientRegistrationRepository registrations) {

        var resolver =
            new DefaultServerOAuth2AuthorizationRequestResolver(
                registrations);

        // Add PKCE S256 even for the backend confidential client.
        // Do not manually generate/overwrite state or nonce.
        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error", "/login",
                    "/oauth2/authorization/**",
                    "/login/oauth2/code/**")
                .permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationRequestResolver(resolver))
            .build();
    }

    @RestController
    static class Api {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> home() {
            return Mono.just(
                "<!doctype html><html lang=\"en\"><body>" +
                "<h1>OIDC Login demo</h1>" +
                "<a href=\"/oauth2/authorization/oidc\">" +
                "OIDC Login</a></body></html>");
        }

        @GetMapping("/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "subject", principal.getName()));
        }
    }
}
~~~

**Key design decisions:**

1. Login starts at `/oauth2/authorization/oidc` — this is the **`registrationId`** from YAML, not an arbitrary issuer name.
2. Spring Security's `DefaultServerOAuth2AuthorizationRequestResolver` creates the authorization request and `state`. With `scope=openid`, Spring Security OIDC handles `nonce` on the authorization request.
3. `withPkce()` ensures code challenge/verifier for the flow. Public clients may auto-enable PKCE per framework config, while backend confidential clients require it explicitly here.
4. `oauth2Login(oauth -> oauth.authorizationRequestResolver(resolver))` **wires the resolver into the OAuth2 Login DSL**. Creating a resolver bean without wiring it can leave the customizer unused.
5. Never establish a login session manually from `code`/`state` query params; the default OAuth2 Login filter and authentication manager handle callback/token validation.
6. `/me` is accessible only after login; it reads the principal from Spring Security. Never print access tokens/refresh tokens/ID Tokens into JSON.
7. WebFlux's default CSRF protection remains enabled. GET-based OAuth2 callbacks follow the OAuth2 flow; for the app's POST forms, CSRF continues to play its own role.
8. Never allow arbitrary post-login return URLs; if extending redirects, validate targets and prevent open redirects.
9. `permitAll()` on callback/authorization URLs only governs authorization matchers; it **does not bypass `state`, `nonce`, or PKCE** in the OAuth2 Login filters.
10. This is a server-side confidential client example: the browser cannot read the secret or `code_verifier` from JavaScript.

### 7.4. Running with a Real OIDC IdP

1. Register a **confidential** client, authorization code flow, with the exact callback `http://localhost:8080/login/oauth2/code/oidc` **for local dev only**. Production must use HTTPS.
2. Enable PKCE S256 at the IdP; verify that the IdP **enforces** challenge/verifier when exchanging the code.
3. Provide the three environment variables per your shell/IDE instructions; never commit secrets to git.
4. Run:

~~~bash
gradle bootRun
~~~

Or `./gradlew bootRun` / `gradlew.bat bootRun` with the Gradle Wrapper. Open `http://localhost:8080/`, click **OIDC Login**, and after the IdP authenticates and redirects back to the callback, open `http://localhost:8080/me`.

**There is no fixed stdout for real login**: each run generates fresh state/nonce/verifier; user IDs, redirect locations, and IdP metadata depend on the environment. In network diagnostics, you should observe:

- The initial redirect from `/oauth2/authorization/oidc` contains `response_type=code`, `client_id`, `state`, `nonce`, `code_challenge`, and `code_challenge_method=S256`.
- Callback succeeds at `/login/oauth2/code/oidc?code=...&state=...` within the **same browser session** that started login.
- The backend token request includes `code_verifier` (verified via IdP test harness/safe telemetry; **never log raw verifiers/tokens**).
- ID Token passes signature/claim/nonce validation. If it fails, **do not** create a local authenticated session, and handle errors safely.
- `/me` succeeds only when login is genuinely verified.

Specific providers may have particular requirements for PKCE, claims, clock skew, or client authentication that require adjusting the demo per that IdP's docs. Never disable nonce/audience validation just to “make login succeed”.

## 8. Offline Authorization Request Testing with Reactor StepVerifier

You can test **generation of `state`, PKCE challenge/verifier, and `nonce`** without an IdP by creating an in-memory `ClientRegistration` and invoking `DefaultServerOAuth2AuthorizationRequestResolver` with a `MockServerWebExchange`.

**Stated limitation:** This test only verifies that the **client builds the authorization request correctly**. It does **not** prove the IdP enforces PKCE, or that the client rejects callbacks with bad state or bad ID Token nonce. Those require integration/security tests with an IdP test harness or test doubles at the actual token/authentication layer.

File `src/test/java/example/AuthorizationRequestSecurityTest.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.server.DefaultServerOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class AuthorizationRequestSecurityTest {

    private DefaultServerOAuth2AuthorizationRequestResolver resolver() {
        ClientRegistration reg = ClientRegistration
            .withRegistrationId("oidc")
            .clientId("offline-client")
            .clientSecret("offline-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile")
            .authorizationUri("https://idp.example.test/authorize")
            .tokenUri("https://idp.example.test/token")
            .jwkSetUri("https://idp.example.test/jwks")
            .clientName("Offline OIDC Test")
            .build();

        var repo = new InMemoryReactiveClientRegistrationRepository(reg);
        var resolver =
            new DefaultServerOAuth2AuthorizationRequestResolver(repo);

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        return resolver;
    }

    private MockServerWebExchange exchange() {
        return MockServerWebExchange.from(
            MockServerHttpRequest
                .get("/oauth2/authorization/oidc")
                .build());
    }

    private String sha256Url(String input) {
        try {
            byte[] sha256 = MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(sha256);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    @Test
    void createsStateNonceAndS256Challenge() {
        StepVerifier.create(resolver().resolve(exchange()))
            .assertNext(request -> {
                assertNotNull(request.getState());
                assertFalse(request.getState().isBlank());

                String verifier = request.getAttribute("code_verifier");
                assertNotNull(verifier);
                assertTrue(verifier.length() >= 43);
                assertTrue(verifier.length() <= 128);

                assertEquals("S256",
                    request.getAdditionalParameters().get(
                        "code_challenge_method"));

                assertEquals(sha256Url(verifier),
                    request.getAdditionalParameters().get(
                        "code_challenge"));

                assertTrue(request.getAdditionalParameters()
                    .containsKey("nonce"));
                assertNotNull(request.getAttribute("nonce"));

                String authorizationUrl =
                    request.getAuthorizationRequestUri();

                assertTrue(authorizationUrl.contains("state="));
                assertTrue(authorizationUrl.contains(
                    "code_challenge="));
                assertTrue(authorizationUrl.contains("nonce="));

                // PKCE secret must not be sent in the authorize URL.
                assertFalse(authorizationUrl.contains(
                    "code_verifier="));
                assertFalse(authorizationUrl.contains(verifier));
            })
            .verifyComplete();
    }

    @Test
    void eachAuthorizationAttemptUsesDifferentState() {
        var resolver = resolver();

        Mono<OAuth2AuthorizationRequest> first =
            resolver.resolve(exchange());
        Mono<OAuth2AuthorizationRequest> second =
            resolver.resolve(exchange());

        StepVerifier.create(Mono.zip(first, second))
            .assertNext(pair -> {
                assertNotEquals(
                    pair.getT1().getState(),
                    pair.getT2().getState());

                assertNotEquals(
                    pair.getT1().getAttribute("code_verifier"),
                    pair.getT2().getAttribute("code_verifier"));

                assertNotEquals(
                    pair.getT1().getAttribute("nonce"),
                    pair.getT2().getAttribute("nonce"));
            })
            .verifyComplete();
    }

    @Test
    void doesNotResolveUnknownLoginPath() {
        var resolver = resolver();
        var unrelated = MockServerWebExchange.from(
            MockServerHttpRequest.get("/not-an-oauth-login").build());

        StepVerifier.create(resolver.resolve(unrelated))
            .verifyComplete();
    }
}
~~~

Run the offline tests from the project directory after fetching dependencies:

~~~bash
gradle test
~~~

With the Gradle Wrapper, use `./gradlew test` or `gradlew.bat test`. All 3 tests are expected to pass with compatible Spring Security 6.5.x/Boot 3.5.x. The tests do not use `@SpringBootTest` and require no `OIDC_ISSUER_URI` environment variable: they construct `ClientRegistration` directly. You should run the actual build to confirm your local dependencies/toolchain match.

### 8.1. Why Does the Nonce Test Not Compare Against an ID Token Directly?

In an offline test, there is no validly signed ID Token from an IdP yet. We only confirm that **`nonce` is generated and attached to the authorization request**. Verifying ID Token `nonce` requires an integration test with a mock IdP providing valid signatures and JWKS, or unit-testing the authentication manager/ID token decoder with a controlled mock response.

Never build a JSON object with `nonce` and declare “OIDC nonce validation passed” — signature, issuer, audience, expiration, and Spring's hashed-nonce rules must all be verified as well.

### 8.2. How to Test a Callback with Invalid State?

An integration test can:

1. Initiate `GET /oauth2/authorization/oidc` and retain the session cookie.
2. Capture `state=S1` from the received redirect; do not print real values to logs/tickets.
3. Call the callback with `state=modified` and a dummy `code`; expect **authentication failure** and **no** call to the token endpoint.
4. Call the callback with the right `S1` but a **different session cookie**; this must also be rejected.
5. Reuse `S1` after a valid callback; replay must be rejected per repository design.
6. Assert status/redirect according to the real failure handler; never hardcode every error as HTTP 401 or 403 because `oauth2Login` may redirect to a login error page.

**Do not test bad state by writing a custom callback controller** that bypasses the default checks. Tests should flow through the filter chain and an appropriate provider/test double.

## 9. Login Flow Constraints Beyond the Three Parameters

### 9.1. Redirect URI Must Be Registered and Matched Exactly

The Authorization Server must register redirect URIs and apply **exact string matching** per RFC 9700 (with a specific exception for native app localhost dynamic ports). With WebFlux:

~~~text
Authorization start:
  /oauth2/authorization/oidc

Registered callback:
  https://app.example.test/login/oauth2/code/oidc
~~~

Never register arbitrary patterns like `https://app.example.test/*`, accept callbacks from unowned hosts, or pass an attacker-supplied `redirect_uri` query param into the token request. At the IdP, keep localhost dev URIs and HTTPS production URIs as separate exact entries.

Behind a reverse proxy, `Forwarded`/`X-Forwarded-*` settings must be trusted and validated, since Spring may expand `{baseUrl}` from request/proxy headers. A proxy that lets clients forge forwarded host/scheme headers can cause malformed redirect URIs or open vulnerabilities.

### 9.2. Bind to the Right Issuer to Prevent IdP Mix-Up

When an application supports multiple OAuth2/OIDC providers, an attacker can trick the client into **sending an authorization code from IdP A to IdP B's token endpoint**. This is a **mix-up attack**.

Per RFC 9700, clients supporting multiple Authorization Servers need mix-up countermeasures, such as:

- Binding the authorization request to the intended issuer/registration in the transaction store.
- Verifying `iss` in the authorization response per RFC 9207 if supported by the provider.
- Or validating the ID Token issuer at the proper stage per OIDC/protocol; using distinct callback URIs per issuer where needed.
- Never choosing the token endpoint from an unverified `issuer=...` callback parameter.
- Testing that a callback for registration A is rejected for B, even if `state` looks valid.

Never assume **“we have `state`”** automatically immunizes against all mix-up risks. Binding the request to the right issuer/token endpoint is an independent requirement.

### 9.3. Never Skip ID Token Verification

For OIDC login, verify:

1. JWS signature/JWKS from the registered IdP.
2. `iss` matches the trusted issuer.
3. `aud` contains the exact client ID, plus `azp` per OIDC if applicable.
4. `exp`, `iat`, and reasonable clock skew.
5. `nonce` matches the authorization request, if `nonce` was sent.
6. `sub` serves as the stable identity per issuer; never default to email as a global ID.

Never allow a `userinfo` response or arbitrary access token claims to **overwrite** the identity verified by the ID Token. Across multiple tenants/issuers, use an issuer-prefixed identity key.

### 9.4. Single-Use, Short-Lived Authorization Code

The authorization code must have a short lifetime, be bound to the client ID/redirect URI, and be used **once** at the token endpoint. If a code is redeemed twice, the IdP must reject the second attempt and may revoke associated tokens per policy. PKCE does not turn a code into a long-lived bearer token.

State, nonce, and PKCE verifiers also belong to a single login attempt. If a user opens two login tabs simultaneously, two transactions may exist; test how the repository/session stores them so one tab's state does not silently overwrite another's.

### 9.5. Session Cookies and Login Callbacks

A server-side WebFlux OAuth2 Login app usually stores pending authorization requests in `WebSession`. The browser must preserve the same **session cookie** from authorization start through the callback.

- Session cookies should be `Secure` and `HttpOnly` over HTTPS.
- `SameSite=Lax` generally suits the cross-site **top-level GET redirect** of the authorization code flow, though it should not be assumed valid for every response mode.
- OIDC `response_mode=form_post` uses a cross-site POST that may be blocked by SameSite and also requires CSRF-specific handling; redesign the flow/cookie policy rather than simply disabling all CSRF.
- Multiple instances require a shared session store or proper affinity; if the callback lands on an instance lacking the pending request, state validation will fail.
- Login success should apply session-fixation protection and protect local sessions, never reusing an attacker-fixed session ID.
- Rotating a login session does not automatically mean all refresh tokens or IdP sessions have been protected/revoked.

### 9.6. HTTPS, Referrer-Policy, and Preventing Code Leaks

The callback URL contains `code` and `state`; protect it from leakage by:

- Enforcing HTTPS/TLS in production.
- Never logging full query strings in reverse proxies, tracing, or analytics.
- Never embedding untrusted third-party scripts/assets on the callback/success page while the URL still holds `code`.
- Setting a restrictive `Referrer-Policy` and redirecting the user to a clean URL after processing.
- Never redirecting codes/tokens to dynamic URLs taken from query params.
- Never sending access tokens, ID Tokens, or client secrets in fragments/queries to untrusted locations.
- Keeping secrets/JWKS keys properly configured and rotated per policy; never skip validation for clock skew or transient JWKS errors.

### 9.7. Consent, prompt, and login_hint Are Not Security Guarantees

OIDC supports UX parameters like `prompt=login`, `prompt=consent`, `login_hint=...`, and `max_age`. They guide IdP behavior; they do not replace `state`, `nonce`, PKCE, and issuer validation. If sensitive reauthentication is required, policy must check `auth_time`/`acr` or session age after login rather than merely appending `prompt=login` and trusting every new token meets the desired assurance level.

## 10. Threat Model: What Each Measure Blocks vs. Does Not Block

| Threat | State | OIDC nonce | PKCE S256 | Other Mandatory Constraints |
|---|---|---|---|---|
| Forged callback from another site (login CSRF) | **Primary** when properly session-bound | Provides OIDC protection when validated properly | Helps when IdP enforces PKCE and session binding | Cookie/session, one-time state |
| Stolen authorization code | Does not block redeeming code at token endpoint | Not directly for pure OAuth | **Primary** | Client auth, TLS, code TTL |
| Code injection from another flow | Detects callback not belonging to request | Can detect ID Token swap in OIDC | **Binds code to verifier** | Right IdP, exact redirect URI |
| ID Token replay/substitution | Does not inspect ID Token contents | **Primary** | Does not replace signature/claims validation | JWS, `iss`, `aud`, `exp` |
| Mix-up between two IdPs | Binding necessary but **insufficient** | Can help under OIDC | Does not select the right token endpoint | `iss`/registration binding, response issuer, callback strategy |
| Post-login open redirect | Not by default | No | No | Validate post-login redirect target |
| XSS on application origin | Can be read/abused depending on design | Can leak if scripts control flow | Verifier can leak if client storage is compromised | CSP, output encoding, BFF/cookie policy |
| CSRF on business POST endpoints | Does not replace app CSRF filter | No | No | CSRF token/Origin check, SameSite |
| Stolen active session cookie | Insufficient | No | No | Secure/HttpOnly cookies, session revocation, MFA/step-up |

**Remember:** OAuth2 callback anti-CSRF (`state`/PKCE/nonce under respective conditions) is distinct from CSRF protection on state-changing APIs **after the user has logged in**. Never disable `ServerHttpSecurity.csrf` globally just because OAuth2 Login already uses `state`.

## 11. Common Mistakes

**Mistake 1 — Hardcoding `state="abc"` for every login.** Attackers can predict/replay it, breaking transaction binding. Use a per-attempt random state stored in a trusted repository and consumed once.

**Mistake 2 — Using state supplied by a client query param.** State must be generated and stored on the trusted client server/BFF and matched at callback; never treat query state as authoritative data.

**Mistake 3 — Treating `nonce` as a duplicate of `state`.** State validates the callback; nonce binds the ID Token to the OIDC authentication request. Each is checked in a different place.

**Mistake 4 — Skipping ID Token validation because “we have PKCE”.** PKCE only binds the code/verifier; signature, `iss`, `aud`, `exp`, and `nonce` validation are still required.

**Mistake 5 — Putting `code_verifier` in the authorize URL.** The verifier is an ephemeral secret; send it only to the token endpoint. The authorization endpoint receives the challenge.

**Mistake 6 — Using PKCE `plain` or a static verifier.** S256 avoids exposing the verifier in the authorization request; every attempt needs a fresh random verifier.

**Mistake 7 — Client sends PKCE but IdP doesn't check it.** PKCE is secure only when the authorization server **binds** the challenge to the code and rejects wrong verifiers; test the provider.

**Mistake 8 — Thinking a confidential client secret replaces PKCE.** Client secrets authenticate the app, while PKCE binds the code to the login attempt; use PKCE on backends too when supported.

**Mistake 9 — Writing a custom callback controller that reads `code` and issues a local session.** Bypasses state/nonce/PKCE and token validation. Use Spring's OAuth2 Login filter.

**Mistake 10 — Customizer wipes out `nonce` or PKCE attributes.** Breaks security bindings; when adding `prompt`/custom parameters, preserve framework metadata.

**Mistake 11 — Letting expired state “pass if the code is valid”.** Missing state correlation must fail closed; never add a “skip state check” fallback.

**Mistake 12 — Storing `OAuth2AuthorizationRequest` in a global Map without TTL.** Causes memory leaks, cross-user mix-ups, replay, and multi-instance failures. Use a controlled repository/session store.

**Mistake 13 — Allowing wildcard redirect URIs or arbitrary URLs.** Codes can be sent to untrusted origins. Register exact redirect URIs and prevent open redirects.

**Mistake 14 — Checking only `state` without issuer binding.** Multi-IdP clients are vulnerable to mix-up; bind the right issuer/registration and follow RFC 9700/9207.

**Mistake 15 — Confusing access tokens with ID Tokens.** Access tokens call resource servers; ID Tokens prove authentication to the OIDC client once verified. Never use an access token arbitrarily as a login ID Token.

**Mistake 16 — Using email as a global user ID regardless of issuer.** Emails can change, be unverified, or collide across IdPs. Use `issuer + sub` as the identity key.

**Mistake 17 — Logging raw authorize URLs, callback queries, or PKCE verifiers.** Can leak codes, state, nonces, and correlation data; mask URLs/queries and secrets.

**Mistake 18 — Disabling CSRF on all POSTs because `oauth2Login` is enabled.** Callback anti-CSRF does not replace CSRF for post-login business endpoints.

**Mistake 19 — Losing the session cookie due to SameSite/proxy issues.** The callback cannot load pending state. Debug cookie Domain/Path/Secure/SameSite, forwarded headers, and the session store before dropping validation.

**Mistake 20 — Treating a 302 redirect test as a complete login test.** That only proves the client starts the flow. Add negative tests for state, verifier, nonce, token claims, and replay.

**Mistake 21 — Hardcoding client secrets in committed YAML.** Confidential client secrets belong in a secret manager/env; public clients have no trustworthy client secret in user-delivered bundles.

**Mistake 22 — Turning all callback errors into 200/“logged in”.** OAuth2 authentication failure must leave the user unauthenticated; render an error page for UX without creating an Authentication.

## 12. Pre-Deployment Security Checklist

1. **Grant:** Use Authorization Code Flow; never use Implicit Grant or Password Grant for new logins.
2. **state:** Is there a per-attempt random state bound to the browser/session/authorization request?
3. **Callback:** Are missing/wrong/expired/replayed states rejected, and are used requests removed?
4. **nonce:** With OIDC scope `openid`, is `nonce` per-attempt and validated in the ID Token per framework?
5. **PKCE:** Is `code_challenge_method=S256` used with a 43–128 char random verifier, and does the IdP reject missing/invalid verifiers?
6. **Verifier secrecy:** Is `code_verifier` absent from authorization URIs, logs, client URLs, and third-party analytics?
7. **Client type:** Do public clients avoid static client secrets, while confidential backends use a secret manager and PKCE where supported?
8. **Redirect URI:** Are registered URIs exact, using HTTPS in production, with no arbitrary port/host/path wildcards?
9. **Issuer:** Are `iss`/provider registration/binding checked, with RFC 9700 mix-up defense for multi-IdP setups?
10. **ID Token:** Are JWS, JWKS, allowed algorithms, `iss`, `aud`, `exp`, `iat`, `nonce`, and `azp` checked per OIDC?
11. **Subject:** Is user identity keyed by `issuer + sub`, never trusting an unverified email?
12. **One-time:** Do codes, state, and pending requests expire and get consumed once, with replay failing to create a session?
13. **Session:** Does the WebSession store persist across callbacks and multiple instances with proper Secure/HttpOnly/SameSite cookies?
14. **Cross-site mode:** Does `response_mode=form_post` have dedicated cookie/CSRF handling without accidentally losing sessions?
15. **Proxy:** Are `{baseUrl}` and forwarded headers sourced strictly from trusted reverse proxies?
16. **Open redirect:** Are post-login success targets restricted to an internal allowlist/paths, never taken from arbitrary queries?
17. **CSRF:** Do post-login business POSTs retain CSRF/Origin/SameSite controls?
18. **Tokens:** Are access/refresh/ID Tokens kept out of bodies/logs for unauthorized clients, and stored/revoked properly?
19. **Observability:** Is there sanitized auditing for failure reasons (state mismatch, PKCE invalid, invalid_nonce, issuer mismatch) without leaking secrets?
20. **Testing:** Are offline resolver tests and end-to-end IdP tests (happy path + negative cases) actually running in CI/staging?
21. **Version:** Have you checked actual Spring Security APIs and run regression tests on OAuth2 Login filters after version upgrades?
22. **Browser:** Have you tested in Chrome/Firefox/Safari and on mobile apps when special app-links/redirects are involved?
23. **Time:** Are app/IdP clocks NTP-synchronized with a tightly bounded clock skew policy?
24. **Failure mode:** Do IdP outages or discovery failures fail closed rather than falling back to accepting unverified tokens?

## 13. Self-Check Questions

**1.** Since both `state` and `nonce` are random, can you keep just one?

**Answer:** You should not arbitrarily drop either. `state` correlates the OAuth2 authorization response with the login request/browser; `nonce` binds the OIDC ID Token. RFC 9700 recognizes security interactions between them under specific conditions, but the framework designs both by default for defense in depth.

**2.** An attacker intercepts an authorization code but lacks the PKCE verifier. Can they exchange the code themselves?

**Answer:** An Authorization Server properly enforcing PKCE S256 must reject token requests with a missing or wrong verifier. This does not replace protecting tokens after issuance.

**3.** Where is `code_challenge` sent, and where is `code_verifier` sent?

**Answer:** The challenge is sent in the **authorization request**; the verifier is sent only in the **token request** to the IdP, never in the browser redirect URL.

**4.** Why must `iss` and `aud` of the ID Token still be checked even when `nonce` matches?

**Answer:** `nonce` only binds the transaction; `issuer`/`audience` prove the token was issued by an authorized IdP for the intended client. Signature and expiration are also mandatory.

**5.** Can `redirect_uri` be registered as `https://app.example.test/*` for deployment convenience?

**Answer:** Not according to OAuth2 Security BCP. IdPs must exact-match redirect URIs (aside from the native localhost ports exception); wildcard URLs/open redirects can leak codes and tokens.

**6.** How does `WebSessionOAuth2ServerAuthorizationRequestRepository` differ from `ServerSecurityContextRepository`?

**Answer:** The first holds pending authorization requests awaiting callbacks (`state`/PKCE/`nonce`), while the second persists the verified Authentication for the login session. They represent different state and lifecycles.

**7.** Does WebFlux `oauth2Login` use Servlet's `HttpSessionOAuth2AuthorizationRequestRepository`?

**Answer:** No. WebFlux uses reactive repositories such as `WebSessionOAuth2ServerAuthorizationRequestRepository`.

**8.** If an app uses two IdPs and a callback code from A is sent to token endpoint B, is having `state` enough to guarantee safety?

**Answer:** No. You must defend against IdP mix-up via issuer/registration binding, RFC 9207 response issuer checks, or distinct per-issuer redirect URI strategies.

**9.** What do the StepVerifier tests in section 8 prove, and what do they not prove?

**Answer:** They prove the resolver generates per-attempt `state`/`nonce`/challenge/verifier and does not expose the verifier in the authorize URL. They do not prove callback/session handling, token-endpoint PKCE enforcement, or ID Token validation; those require integration tests.

**10.** An OIDC ID Token has the right `nonce` but an invalid signature. Should the login be accepted?

**Answer:** No. Signature, issuer, audience, expiration, and other claims must all be verified before creating an Authentication.

**11.** A callback loses the session cookie so `state` cannot be found. Should it be allowed through if the code is still valid?

**Answer:** No. This case must fail closed while you investigate cookie `SameSite`/Secure/Path, proxy, or session persistence issues; never bypass anti-CSRF.

**12.** Why must a public SPA not embed a client secret in its bundle?

**Answer:** Any user can inspect the bundle/code. An SPA has no trustworthy confidential channel for a client secret; use Authorization Code + PKCE or a BFF to keep secrets/tokens on the server.

## Official Documentation

- Spring Security 6.5 — Reactive OAuth2 Authorization Grant Support (PKCE, authorization request resolver, WebSession repository): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- Spring Security 6.5 — OAuth2 WebFlux & OIDC login: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 — OAuth2 Login advanced settings: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html
- Spring Security — `OAuth2AuthorizationRequestCustomizers.withPkce()`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html
- RFC 7636 — PKCE, S256, public test vector: https://www.rfc-editor.org/rfc/rfc7636.html
- RFC 9700 (January 2025) — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
- RFC 9207 — Authorization Server Issuer Identification in Authorization Response: https://www.rfc-editor.org/rfc/rfc9207.html
- OpenID Connect Core 1.0 — nonce / ID Token / code flow: https://openid.net/specs/openid-connect-core-1_0.html
- OWASP — OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
