# Distinguishing ID Token, Access Token, Refresh Token, and Local Login Session

## 1. Four Objects That Can Coexist After a Single Login

When a user signs into a Spring Boot application via OpenID Connect (OIDC), an **ID token**, **access token**, **refresh token**, and a **local login session** (`HttpSession` in Servlet apps) may all exist at the same time. They have different purposes, issuers, consumers, lifetimes, and trust boundaries.

For example: Alice visits `https://shop.example.test`, and the application redirects the browser to an OpenID Provider (OP) to sign in. After receiving an authorization code, the application exchanges the code at the token endpoint to receive an ID token, an access token, and sometimes a refresh token. Spring Security validates the OIDC result, creates an `Authentication`, and may store `SecurityContext` in the HTTP session. The browser receives a session cookie to continue browsing **application** pages, while the access token is used when the **client calls a resource server**.

Key points to remember:

- **The ID token answers:** “*Whom* did the OP authenticate for this OAuth/OIDC client, and in which login event?”
- **The access token answers:** “*Which resources/APIs* is the client allowed to call, with what permissions, and for how long?”
- **The refresh token answers:** “Can the client request a new access token from the authorization server under the existing grant?”
- **The local session answers:** “Which login state is the application maintaining across the browser's HTTP requests?”

**There is no mandatory one-to-one relationship among these four objects.** A session-based application can continue serving internal pages after an access token for calling an external API has expired; a stateless API can accept a valid access token without any `HttpSession` existing at all; a refresh token might not be issued.

## 2. Quick Comparison Table

| Criterion | ID Token (OIDC) | Access Token (OAuth 2.0) | Refresh Token (OAuth 2.0) | Local Login Session |
| --- | --- | --- | --- | --- |
| Primary purpose | Asserts user authentication event to the **OIDC client** | Grants access to a **resource server/API** | Requests a new access token at the **token endpoint** | Maintains login state/`SecurityContext` across app requests |
| Issuer / creator | OpenID Provider | Authorization server | Authorization server (if policy issues one) | Application and session container/repository |
| Direct consumer | OIDC client / relying party | Target resource server; client carries token to call API | Authorization server; client keeps it confidential | Application receiving browser session cookie and looking up server-side state |
| Intended recipient | `aud` usually contains the relying party's `client_id` | Target resource/API, per authorization server design | Bound to client/grant; not a credential for resource servers | The application itself or app cluster sharing a session store |
| Format | JWT with claims and OIDC-compliant signature/protections | JWT or opaque; other formats possible per system | Typically opaque, not required to be JWT | Cookie holding session ID; session data resides on server or session store |
| Lifetime | ID token's `exp` | `exp` or TTL/token policy | Lifetime, rotation/revocation depend on provider | Idle timeout, absolute timeout, logout, invalidation per app |
| What it proves | OP authenticated the subject for the client per OIDC | Permission to access the resource if token is **validly verified** | Can request a new token while valid and matching client/grant | Local state still exists and is accepted by the app |
| Where it travels | To the OIDC client via standardized flow | E.g., `Authorization: Bearer ...` to target API | Only to token endpoint over an appropriate secure channel | Cookie sent back to matching domain/path; never auto-sent to other APIs |
| Common mistake | Using ID token as a Bearer token for APIs | Using access token as client login proof without checking audience | Sending refresh token to browser/JS or resource server | Assuming OP logout or token expiration auto-clears the local session |

The table above describes the typical model for a **server-side/BFF web app**. For SPAs or native apps, token and session storage may differ; authentication, authorization, refresh, and session management boundaries must still be preserved. Never treat every JWT-looking string as the same kind of token.

## 3. OAuth 2.0 and OIDC Have Different Roles

**OAuth 2.0** is an authorization framework: the resource owner authorizes a client to access certain resources managed by a resource server. OAuth 2.0 itself does not define a standard user login protocol using access tokens.

**OpenID Connect** builds on OAuth 2.0 to define federated login and identity information. OIDC adds the **ID token**, `openid` scope, UserInfo endpoint, authentication/validation rules, and claims such as `sub`, `iss`, and `aud`. Modern web apps typically use the **Authorization Code flow**, with PKCE when appropriate, instead of putting long-lived tokens in URLs.

Roles in a system:

- **End user (Alice):** the user signing in.
- **User agent (browser):** follows redirects and sends cookies.
- **OIDC client / relying party (Spring Boot web app):** receives the authorization code, exchanges tokens, validates the ID token, and creates local login state.
- **OpenID Provider / Authorization server (IdP):** authenticates Alice and issues tokens per policy.
- **Resource server (API):** accepts and validates only access tokens intended for that API.
- **Session repository:** stores/restores local state across browser requests for the web app.

In `client_credentials`, the access token may represent an **application**, not a user. Thus, seeing `sub` or scopes inside an access token does not automatically mean a user signed in through OIDC.

## 4. Full Flow: One Login, Four Distinct Lifecycles

```text
Browser                    Spring Boot web client           OP / Authorization Server        Resource API
   |                                |                               |                         |
   | GET /orders                    |                               |                         |
   |------------------------------->| not logged in locally yet     |                         |
   |<--- 302 to /authorize ---------|                               |                         |
   |---------------------------- authorize + state + PKCE --------->|                         |
   |<------------------------- login/consent and redirect code -----|                         |
   | GET /login/oauth2/code/...     |                               |                         |
   |------------------------------->| POST /token: code + verifier  |                         |
   |                                |------------------------------>|                         |
   |                                |<--- id_token, access_token,   |                         |
   |                                |     refresh_token? -----------|                         |
   |                                | validate OIDC ID token        |                         |
   |                                | create Authentication         |                         |
   |                                | save local SecurityContext    |                         |
   |<----- Set-Cookie: JSESSIONID --|                               |                         |
   |                                |                               |                         |
   | GET /orders + JSESSIONID       |                               |                         |
   |------------------------------->| load local session            |                         |
   |<----- HTML of /orders ---------|                               |                         |
   |                                |                               |                         |
   |                                | GET /orders-api Bearer access_token ---------------------->|
   |                                |<---------------------------- API response -----------------|
   |                                |                               |                         |
   |                                | access token expired          |                         |
   |                                | POST /token with refresh token (if present, still valid)   |
   |                                |------------------------------>|                         |
   |                                |<-- new access_token ----------|                         |
   |                                | local session may still remain|                         |
```

The line `refresh_token?` has a question mark because the authorization server **is not required** to issue a refresh token. Receiving a refresh token may depend on `offline_access`, client type, consent, rotation, lifetime, and provider policy. Without a refresh token, the client may have to initiate a new authorization flow when calling an API.

**Distinguishing the two login/access directions:** browser → Spring web app usually uses a session cookie; Spring web app → resource API uses an access token; never send an ID token to an API as an access token. With the BFF pattern, the backend can keep access/refresh tokens server-side, reducing credential exposure to browser JavaScript.

## 5. ID Token: Confirming Identity for the OIDC Client

An ID token is a **JWT** defined by OpenID Connect. It is issued by the OP to the client participating in the flow. A purely illustrative payload:

```json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-42",
  "aud": "web-client",
  "exp": 1796205600,
  "iat": 1796202000,
  "nonce": "nonce-registered-by-client"
}
```

The timestamp numbers are illustrative; do not use this payload as a real token. One can **decode** a JWT payload, yet Base64URL decoding **is not validation**. The client must validate the ID token per the applicable OIDC profile/flow, including at minimum:

1. **Signature, algorithm, and trusted key:** verify against configured OP metadata/JWKS; never accept an arbitrary algorithm declared by the token itself.
2. **`iss`:** must match the trusted issuer exactly; avoid trusting tokens from another tenant/provider.
3. **`aud`:** must contain the `client_id` of the exact OIDC client receiving the ID token; when multiple audiences are present, also apply `azp` checks per spec.
4. **`exp`, `iat`:** check validity window and clock skew rules. If the flow/policy requires `auth_time`, also check authentication freshness.
5. **`nonce`:** when the authorization request sent a nonce, verify the nonce in the ID token matches the stored value bound to the login flow session; alongside `state`, this guards against request/response mix-ups, though **`state` and `nonce` are two different mechanisms**.
6. **`sub`:** subject identifier within the issuer's scope, generally more stable than email or display name; the application should use the composite key `(iss, sub)` when linking users.

**Never use `id_token` as `Authorization: Bearer` for a resource API.** Its `aud` is normally the OIDC client, not the API; a resource server mistakenly accepting it breaks audience and token-type boundaries. Conversely, an access token issued for an API does not replace OIDC client ID token verification.

**Does an expired ID token immediately log out the web app?** Not automatically. `exp` defines the validity of the **token** during authentication/validation, whereas a web app that already completed login can maintain an `HttpSession` with its own lifetime. If business logic requires re-authentication or freshness (high-value transactions), configure that policy explicitly; never assume from `exp` that the local session was destroyed.

## 6. Access Token: API Access Permission, Not a Login Cookie

An access token is the credential used to access a **resource server**. A client may send:

```http
GET /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-redacted>
```

This is a sample request, **not a real token**. The resource server must validate the token according to its format:

- **JWT access token:** validate signature/algorithm, issuer, timestamps, **target audience/resource**, token-type requirements per applicable profile, scopes/authorities, and endpoint policies. Never check only `sub`.
- **Opaque access token:** the API cannot trust it by parsing the string itself; it needs token introspection or an AS-designed verification mechanism to determine active status and metadata.
- **Bearer token:** anyone who captures a valid credential can use it within the token's bounds. Protect via TLS, short lifetimes, minimal scopes, audience restrictions, and sender-constrained tokens (DPoP/mTLS) when required.

**Access token lifetime is independent of the login session.** When an access token expires, API calls using the old token may be rejected with `401`; the web app may still be logged in locally. A client with a valid refresh token can request a new access token and retry the API; refresh failure can break API-calling features, yet does not automatically wipe every web app session.

**Scope ≠ local role:** a token with scope `orders:read` does not prove `ROLE_ADMIN` in the application. Spring Security Resource Server may map scopes to `SCOPE_orders:read` authorities, while final permissions still follow policies per API, tenant, and specific resource. Object-level ownership checks are still required beyond scopes.

**Common responses:** missing/invalid/expired token → `401 Unauthorized` (the API may send `WWW-Authenticate: Bearer ...`); valid token with insufficient permissions → `403 Forbidden`. Other policies, CSRF, or gateways can affect response codes; never guess status from a single example.

## 7. Refresh Token: Renewing Access, Not Re-Authenticating the Web Session

A refresh token is sent by the client to the **authorization server's token endpoint** using the `refresh_token` grant. The result can be a new access token and, depending on the server, a new refresh token. Refresh tokens **must never be sent to resource APIs or used as `JSESSIONID` cookies**.

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-redacted>
```

This request only illustrates the *exchange direction*; real implementations may require client authentication, sender constraints, and other HTTP fields per protocol. Never store or print real refresh tokens in logs, URL queries, exceptions, traces, or JSON responses sent to the browser.

Key characteristics:

- The authorization server decides **whether to issue a refresh token**; never assume every OIDC login includes one.
- Refresh tokens can be revoked, or expire due to inactivity, logout, or policy changes; merely still holding the token string **does not prove** refreshing will succeed.
- **Rotation:** after each refresh, the server may issue a new refresh token and invalidate the old one; the client must update its stored copy safely and prevent races when multiple requests refresh concurrently.
- **Replay detection:** if a rotated token is illegally reused, the server may detect it and revoke the token family/grant per policy. RFC 9700 requires refresh tokens for public clients to be sender-constrained or rotated.
- **Storage protection:** in confidential backend web clients, keep tokens server-side in a restricted, encrypted/access-controlled store. In SPAs/native apps, follow client-type security guidance; never treat `localStorage` as backend secret storage.
- **Refresh token != “stay logged in forever”:** a successful refresh does not extend `HttpSession` on its own, nor does it prove the user recently re-completed MFA or interactive OP login.

Sometimes a provider returns `invalid_grant` when a refresh token is expired, revoked, or no longer valid. The client should handle this by stopping API calls with the failed token, clearing/updating authorized client state appropriately, and prompting for re-authorization if needed; never retry refresh infinitely or keep using expired access tokens.

## 8. Local Login Session: Application State, Not an OP Token

In a **Spring Security Servlet** app using `oauth2Login()`, after OIDC login succeeds, Spring Security typically maintains an `Authentication` representing the `OidcUser` inside `SecurityContext`. If default configuration enables stateful login, this context is usually persisted via `SecurityContextRepository`, typically `HttpSessionSecurityContextRepository`.

The browser only needs to send the application's session cookie on subsequent requests:

```http
GET /account HTTP/1.1
Host: shop.example.test
Cookie: JSESSIONID=<opaque-session-id>
```

The cookie here is a **local session lookup key**; by default it does not contain a JWT ID/access token and does not prove an access token is still alive. `HttpSession` may hold `SPRING_SECURITY_CONTEXT` along with other application data. Actual storage may be node memory, Spring Session/Redis, or a custom repository.

### Separate Lifecycle

- **Idle timeout:** if no requests arrive within the configured window, the session can expire; this does not mean OP tokens were revoked.
- **Absolute timeout:** the application may enforce a maximum lifetime regardless of activity to force re-login; implement explicitly per policy.
- **Local logout:** clears authentication and invalidates the session; the IdP may still hold an SSO login, so returning to the app might quickly re-authenticate without entering a password.
- **OP logout:** OP session expiration or logout does not guarantee the local app finds out immediately without front-channel/back-channel logout, token/session introspection, or corresponding integration.
- **Session fixation protection:** after login, the app may rotate the session ID to prevent fixation. Do not mistake session ID rotation for ID token refresh.
- **Cookie security:** use HTTPS, `Secure`, `HttpOnly`, flow-appropriate `SameSite`, and restricted domain/path; for cookie-authenticated web apps, enforce **CSRF** protection on state-changing operations.

**Note on Spring Security 6+:** a custom filter that builds an `Authentication` and sets it on `SecurityContextHolder` may need to call `SecurityContextRepository.saveContext(...)` to persist across requests. `oauth2Login()` handles context saving during authentication; never assume every custom authentication is automatically saved just by setting the holder.

### Authentication and OAuth2AuthorizedClient Are Two Different Logical Stores

- `SecurityContext` / `Authentication`: “Who does the web app consider this request to be, and what permissions does it have?”
- `OAuth2AuthorizedClient`: association between **client registration**, principal, **access token**, and possibly **refresh token**; managed by Spring Security via `OAuth2AuthorizedClientRepository` or `OAuth2AuthorizedClientService`.
- `OidcUser.getIdToken()`: ID token/claims attached to the logged-in OIDC principal.
- `HttpSession`: where some of the above states may be stored depending on config, though their lifecycles are not identical.

`OAuth2AuthorizedClientManager` can acquire/refresh access tokens when supported by the grant/provider. Refreshing an access token inside the authorized-client repository **does not alter** `Authentication` or recreate the user's OIDC login session.

## 9. Easily Confused Timelines

| Time / Event | ID Token | Access Token | Refresh Token | Local Session and Outcome |
| --- | --- | --- | --- | --- |
| Just completed OIDC login | Client has validated ID token | May be received to call APIs/UserInfo | May or may not be present | Creates `Authentication`; browser starts sending session cookie |
| 10 minutes later, access token expires | No need to reuse on every page request | Old token should no longer be accepted by API | If still valid, can request a new token | Web session can remain logged in |
| ID token passes `exp` | No longer usable as a fresh unexpired ID token | May still be valid | May still be valid | Session can continue until app requires re-auth |
| Refresh token is revoked | Not necessarily affected | Issued token may stay valid until `exp`/API revocation | Refresh fails | Local session may remain; business logic must choose policy |
| User logs out only at the web app | No new token from local logout | May stay valid until expiry/revocation | May require separate revocation/cleanup | Session invalidated and local context cleared |
| User logs out at the OP | OP no longer holds SSO login | Access token may not be invalidated at all APIs yet | May be revoked per OP policy | App needs a sync mechanism to terminate local session |
| Browser deletes `JSESSIONID` | Not auto-revoked | Not auto-revoked | Not auto-revoked | Browser loses reference to old session; server may keep session until timeout |
| API receives `client_credentials` token | Unrelated to user login | Represents client/grant | Usually no refresh in this flow | Requires no user session |

**Do not enforce the exact same TTL** across every token and session type merely because they appear after the same login. Lifetimes should be designed based on risk, API sensitivity, re-authentication requirements, UX, and revocation capability.

## 10. Standalone Java 17 Example Testing Lifecycle Independence

The snippet below is **not a JWT verification library, does not contact an IdP, and does not create a real session**. It simulates application state to show that expired access/ID tokens do not automatically change a “local session active” flag.

Save as `TokenLifetimeExample.java`:

```java
import java.time.Instant;

public class TokenLifetimeExample {

    record Snapshot(
        boolean localSessionActive,
        Instant idTokenExpiresAt,
        Instant accessTokenExpiresAt,
        boolean refreshTokenPresent
    ) {}

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");

        Snapshot state = new Snapshot(
            true,
            now.minusSeconds(60),
            now.minusSeconds(30),
            true
        );

        System.out.println("localSessionActive="
            + state.localSessionActive());
        System.out.println("idTokenExpired="
            + !now.isBefore(state.idTokenExpiresAt()));
        System.out.println("accessTokenExpired="
            + !now.isBefore(state.accessTokenExpiresAt()));
        System.out.println("refreshTokenPresent="
            + state.refreshTokenPresent());
        System.out.println("canInferRefreshWorks=false");
    }
}
```

Run with JDK 17+:

```bash
javac TokenLifetimeExample.java
java TokenLifetimeExample
```

Exact stdout:

```text
localSessionActive=true
idTokenExpired=true
accessTokenExpired=true
refreshTokenPresent=true
canInferRefreshWorks=false
```

Having a refresh token in the snapshot **does not mean it is still valid**. Having an active local session likewise does not replace authorization checks at endpoints. The example pins `now` for reproducibility; real applications must use a reliable clock and protocol-compliant validators.

## 11. Spring Security Illustration: Separating Web Login and Resource API

The example below illustrates **Spring Boot Servlet, Java 17+, Spring Security 6+**. Two `SecurityFilterChain` beans represent two authentication modes in **the same illustrative application**: `/web/**` uses OIDC login/session, and `/api/**` uses JWT bearer tokens. When deploying, client registration and IdP issuer/JWKS must be real trusted values.

Add dependencies to a Spring Boot project configured with compatible plugin/BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Example `application.yml` for an **environment with an existing OIDC provider**; replace URLs/IDs and supply secrets via a secret manager/env (never commit real client secrets):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web:
            provider: demo-idp
            client-id: web-client-id
            client-secret: demo-secret-from-secure-config
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          demo-idp:
            issuer-uri: https://idp.example.test/realms/demo
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
```

This is a **sample configuration**; real login cannot execute against the `example.test` domain. For public/PKCE clients, client authentication config differs. For the resource server, issuer validation and timestamps alone **do not replace** validating the API audience; additionally configure an `aud` validator and token profile/permissions per your real issuer.

Place source at `src/main/java/example/IdentityBoundariesApplication.java`:

```java
package example;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class IdentityBoundariesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityBoundariesApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        // Only /api/** uses Bearer access tokens via Resource Server.
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            // Only makes sense if the API chain truly accepts only Bearer,
            // never browser cookies as credentials.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        // Other routes are handled by web OIDC login.
        return http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityBoundaryController {

    @GetMapping("/web/whoami")
    Map<String, Object> web(
            @AuthenticationPrincipal OidcUser user,
            HttpServletRequest request) {
        return Map.of(
            "subject", user.getSubject(),
            "hasLocalSession", request.getSession(false) != null
        );
    }

    @GetMapping("/api/whoami")
    Map<String, String> api(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        return Map.of("subject",
            subject == null ? "(subject missing)" : subject);
    }
}
```

The code uses Spring Security and Boot Servlet **when a real provider and required configuration are present**; the `/web/whoami` endpoint assumes the request is OIDC-authenticated. If the app permits form login, Basic Auth, or anonymous access via other chains, check the `Authentication` type before using `OidcUser`. The `HttpStatus` import in the listing is unused and can be removed when applying without affecting Java compilation.

**Why separate the chains?**

1. `/api/**` is a resource server: it must validate **access tokens intended for the API**, without automatically falling back to web sessions to bypass bearer authentication. `STATELESS` prevents the API chain from relying on an HTTP session to store context; other middleware must also respect the stateless design.
2. Web routes use `oauth2Login()`: after OIDC login, the controller reads `OidcUser` from the web session's `Authentication`. `hasLocalSession` only indicates whether an HTTP session exists, **not** that a refresh token or access token is still valid.
3. API `/api/whoami` reads `sub` from the JWT that passed the resource server filter; it **does not read an ID token from `OidcUser`**.
4. Sharing the same OP issuer between the API and the OIDC client is only a configuration example; **the ID token's `aud` for `web-client-id` must never be treated as the API's audience**. Accept only access tokens with matching audience, token type, and permissions.

### Validating JWT Audience on the Resource Server

In Spring Security, when configuring a custom `JwtDecoder`, you can combine the default issuer/timestamp validator with an audience validator:

```java
// Illustrative snippet inside @Configuration, using issuer and
// audience read from trusted configuration.
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.api-audience}") String audience) {

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> validator =
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            new JwtClaimValidator<java.util.List<String>>(
                "aud",
                actual -> actual != null && actual.contains(audience))
        );

    decoder.setJwtValidator(validator);
    return decoder;
}
```

Additional imports for this snippet:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

This is an **integration snippet**, not a standalone Java class. `app.security.issuer` and `app.security.api-audience` properties must be added in the deployment environment; calling `withIssuerLocation` requires the IdP's metadata/JWKS to be reachable when needed. Real policies may also require checking `typ`/JWT access token profile, client ID, scopes, tenant, sender constraints, and revocation.

## 12. Inspecting `OAuth2AuthorizedClient` Without Leaking Tokens

Spring Security represents **OAuth2 client**-side tokens with `OAuth2AuthorizedClient`. In an app with `oauth2Login()`, you can inspect state via `OAuth2AuthorizedClientService` or the matching repository, as in this snippet:

```java
// Snippet inside a protected @RestController; OAuth2AuthorizedClientService,
// Authentication, and HttpServletRequest dependencies are provided by Spring.
// Should only be used as an internal diagnostic endpoint.
@GetMapping("/internal/auth-summary")
Map<String, Object> summary(
        Authentication authentication,
        HttpServletRequest request) {

    if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
        throw new ResponseStatusException(
            HttpStatus.FORBIDDEN, "OIDC login required");
    }

    OAuth2AuthorizedClient client =
        authorizedClientService.loadAuthorizedClient(
            oauth.getAuthorizedClientRegistrationId(),
            oauth.getName());

    return Map.of(
        "localSessionPresent", request.getSession(false) != null,
        "accessTokenStored", client != null
            && client.getAccessToken() != null,
        "refreshTokenStored", client != null
            && client.getRefreshToken() != null
    );
}
```

Assumes the controller has a constructor-injected `private final OAuth2AuthorizedClientService authorizedClientService;` field and imports the matching classes. **Note:** with configurations using a custom `OAuth2AuthorizedClientRepository`, data might not reside in the injected service; check the configured storage mechanism. Never directly read refresh/access tokens to print in logs/responses. Having a token **stored** says nothing about current validity or refreshability; that requires separate validation/exchange.

`OAuth2AuthorizedClientManager` can acquire/refresh tokens for outbound HTTP clients (`RestClient`/`WebClient`), provided the app selects appropriate scopes, grants, and authorized-client repository. Avoid building a periodic scheduler to send refreshes just to “keep login alive” without explicit requirements and handling for rotation, logout, and failures.

## 13. Testing Independent Boundaries

When writing tests, construct **scenarios where states diverge**, rather than assuming all tokens/sessions live and die together.

| Test | Setup | Assertion |
| --- | --- | --- |
| ID token with wrong audience | ID token has `aud=another-client` | OIDC client rejects login, creates no authenticated session |
| ID token with wrong issuer/nonce | `iss` or `nonce` mismatches request | Login rejected |
| Access token for another API | Validly signed JWT whose `aud` lacks this API | Resource server rejects (typically 401) |
| Expired access token | `exp` in the past | API rejects; existing web session may remain |
| Missing scope | Valid token missing `orders:read` | Protected endpoint returns 403 per policy |
| Successful refresh/rotation | Expired access token, usable refresh token | Client stores new token, never reuses old refresh token |
| Failed refresh | Revoked/expired refresh token | No infinite retry loop, prompts for new flow when needed |
| Local logout | Browser has session, calls app logout | Session/context cleared; upstream tokens handled per policy |
| IdP logout | OP ended SSO session | Local app updated via back-channel/front-channel/policy |
| Missing cookie | Call protected web endpoint without session | Redirects to login or appropriate 401; bearer API does not rely on cookies |
| API receives only ID token | Send token with web-client audience | Rejected by audience/token-type validation |
| API receives `client_credentials` token | Token represents application | Never treated as an end-user session |

### MockMvc: Testing the OIDC Principal vs. JWT Principal Boundary

In Java tests with `spring-security-test`, the `oidcLogin()` and `jwt()` request post-processors build simulated principal objects:

```java
// Method snippet inside a @SpringBootTest + @AutoConfigureMockMvc test.
// Assumes MockMvc is @Autowired with the chains/controller above.
// jwt() / oidcLogin() simulate Authentication; they DO NOT verify
// token signatures or run a real OAuth2/OIDC flow.
@Test
void browserIdentityAndApiIdentityComeFromDifferentContexts()
        throws Exception {

    mvc.perform(get("/web/whoami")
            .with(oidcLogin().idToken(
                token -> token.claim("sub", "alice-oidc"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice-oidc"));

    mvc.perform(get("/api/whoami")
            .with(jwt().jwt(token -> token.subject("service-jwt"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("service-jwt"));
}
```

Key static imports used in the test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

**Limited meaning:** the test above proves controllers/authorization use the right principal once login is simulated; **it does not prove** that ID token or JWT validators from a real IdP work properly. To prove audience/issuer/signature/nonce/refresh behavior, write integration tests with a real token server/decoder or test specific validators, including invalid tokens and failure paths. Tests for session timeout/logout must actually preserve/change cookies and repositories across requests; `with(oidcLogin())` on a single request **does not prove** a real login created a browser session.

## 14. Common Architectural Mistakes

1. **API trusts ID tokens because “both are JWTs”:** a valid signature is insufficient; a token whose `aud` targets a web client must not be accepted at a resource server.
2. **UI treats the access token as the sole proof the user is logged in:** an access token is issued to access a specific resource; it can expire before the session or represent an application in client credentials.
3. **Sending refresh tokens in an API Bearer header:** resource servers must not accept refresh tokens as credentials; refresh tokens are strictly for the token endpoint.
4. **Unnecessarily exposing server-side secrets/tokens to JavaScript:** use a BFF or client-type-appropriate security; avoid emitting refresh tokens in HTML, logs, or exceptions.
5. **Equating `JSESSIONID` with a JWT:** a session cookie is typically an opaque ID for looking up local state, not an ID token or access token.
6. **Using `exp` from the ID token to auto-logout all sessions:** may violate policy; explicitly configure re-authentication, idle/absolute session timeouts, and step-up when business rules demand.
7. **Forgetting issuer/audience/nonce:** a validly signed token meant for another client/tenant can be accepted by mistake if validators are loose.
8. **Checking only access token expiry while skipping API permissions:** scope/audience/token type/object ownership must all be verified as appropriate.
9. **Storing refresh tokens without considering rotation/concurrency:** two outbound requests refreshing the same old token concurrently can trigger `invalid_grant` and corrupt state if unsynchronized.
10. **Assuming local logout revokes all tokens:** combine token revocation, authorized-client cleanup, and OP logout per design; issued JWTs may remain valid until expiry.
11. **Assuming OP logout invalidates application sessions automatically:** requires front-channel/back-channel logout or session sync and revocation policies.
12. **Confusing resource server and OAuth2 client:** `oauth2Login()` handles web app user login; `oauth2ResourceServer().jwt()` validates bearer tokens on APIs; `OAuth2AuthorizedClientManager` handles outbound API calls and eligible refreshes.
13. **Using ID tokens for rapidly changing data:** ID tokens reflect claims at issuance time; updated profiles/roles need a separate refresh flow. Never treat long-lived tokens as real-time databases.
14. **Exposing debug endpoints that print entire tokens:** return only minimal low-sensitivity metadata; never log `Authorization` headers, access tokens, refresh tokens, ID tokens, or session cookies.

## 15. Choosing Mechanisms for Real Systems

- **Server-rendered website or BFF:** use OIDC `oauth2Login()` for web, sensible `HttpOnly`/`Secure`/`SameSite` session cookies; backend stores authorized clients and refresh tokens securely; send access tokens only to APIs with matching audiences.
- **Backend API receiving bearer tokens:** configure Resource Server to verify issuer, signature or introspection, timestamps, audience, scopes/authorities, and supplemental policies; avoid relying on browser sessions.
- **Service-to-service:** use `client_credentials` with granted scopes/audiences; do not fabricate user sessions.
- **SPA/native app:** use Authorization Code + PKCE per client type; manage tokens per current security guidance and platform specifics without assuming backend-grade secret storage.
- **Apps requiring sensitivity-based re-login:** use `max_age`/`auth_time`/`acr` or suitable step-up mechanisms alongside absolute session timeouts; never treat a live refresh token as fresh MFA proof.
- **Fast revocation:** choose suitable token TTLs, introspection/revocation, back-channel logout, session index/version, or event-driven invalidation; define concrete guarantees (“next request”, “within N seconds”, or “immediately”) so they can be tested.

### Pre-Production Self-Check Checklist

- [ ] Identified the **exact audience and consumer** of the ID token, access token, refresh token, and session cookie.
- [ ] OIDC client validates ID tokens per spec and binds `state`/`nonce` to the login flow when used.
- [ ] Resource server enforces token type, issuer, audience, timestamps, scopes, and object authorization policies.
- [ ] Refresh tokens are stored/sent only where required; rotation, revocation, concurrency, and failures are tested.
- [ ] Browser sessions have cookie protection, CSRF, session fixation, idle/absolute timeout, and local logout.
- [ ] Distinguished “token expired”, “session expired”, “user logged out at OP”, “refresh revoked”, and “access revoked”.
- [ ] Tested 401/403, staggered expirations, stateless API without cookies, and web session without bearer tokens.
- [ ] Planned `OAuth2AuthorizedClient` cleanup upon logout/revocation for the active repository.

**Key takeaway:** ID tokens confirm login **to the client**; access tokens grant access **to APIs**; refresh tokens help the client obtain **new tokens**; local sessions help the **web application** remember users across requests. Each layer requires its own consumer, lifetime, permissions, and revocation policy.

## 16. Authoritative References

- OpenID Connect Core 1.0 — ID token and validation: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://datatracker.ietf.org/doc/html/rfc6749
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://datatracker.ietf.org/doc/html/rfc6750
- OAuth 2.0 Token Revocation (RFC 7009): https://datatracker.ietf.org/doc/html/rfc7009
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://datatracker.ietf.org/doc/html/rfc9700
- Spring Security — OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth 2.0 Client / Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Testing OAuth 2.0 with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
