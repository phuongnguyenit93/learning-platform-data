# Token Revocation, Token Theft, and the Impact of Storage and Transport

## 1. Why Can a Token with a Valid Signature Still Be Dangerous?

An `access token` lets a client call APIs within its granted scope. If it is a **bearer token**, anyone who obtains the token value and presents it properly to the resource server can be treated as authorized to use the token, unless the system enforces additional sender-binding controls. A stolen token can be used **before it expires**, even if the user has closed the tab or deleted the token from the browser.

Three separate questions must be answered:

1. **Is the token cryptographically and policy-wise valid?** For example, a JWT has a valid signature, matching `iss`/`aud`, falls within `nbf`–`exp`, and carries the required `scope`.
2. **Is the token still permitted by the system?** Has it been revoked, invalidated due to permission changes or account lock, or part of a terminated session/authorization grant?
3. **Who is presenting the token?** With a pure bearer token, the server generally cannot tell the legitimate user apart from someone who stole the exact token string. Sender-constrained tokens such as DPoP/mTLS add proof that the sender holds the associated key, yet do not eliminate every attack vector.

**A validly signed JWT does not mean "unrevocable".** More accurately: when verifying JWTs **purely offline** based on signature and claims, the resource server does not automatically learn that the authorization server just revoked the token unless an additional state-lookup mechanism or policy is added.

This lesson focuses on Spring Security Resource Server, OAuth 2.0/OIDC, and token protection choices across browsers, mobile, and backends. A token can be a JWT or opaque; choosing **token format**, **storage location**, **transport method**, and **verification/revocation mechanism** are related yet distinct decisions.

## 2. Distinguishing Token Types and Sessions

| Concept | What Is It For? | Behavior If Compromised |
| --- | --- | --- |
| **Access token** | Client calls resource server APIs; carries permissions, audience, expiration | Anyone holding a bearer token can call APIs within remaining scope/lifetime |
| **Refresh token** | Client requests new access tokens at the authorization server | If leaked, can sustain access longer; requires protection and rotation or sender constraint |
| **ID token (OIDC)** | Attests a login event to an OIDC client; contains authentication claims | Must not be used directly as an access token for another API; RS must require the right token type/audience |
| **Session ID / session cookie** | Browser presents a reference key to server-side login state | Theft can lead to session hijacking; clearing cookies client-side does not replace server-side session invalidation |
| **Authorization code** | Temporary code for client to exchange for tokens in Authorization Code flow | Protected by redirect URI/PKCE, short TTL, and single use; never send access tokens in URLs |
| **JWT** | A self-describing token *format* with header, claims, signature (JWS) | Signature ensures integrity and signer origin, **does not encrypt** payload contents; may still require extra state checks |
| **Opaque / reference token** | Token string from which client/RS cannot infer claims directly from structure | Typically verified via introspection or issuer's token store; reflects active status more easily but requires connectivity/infrastructure |

A `refresh token` **must not be accepted by a resource server to call APIs** merely because it is a valid token string. An `ID token` must also not replace an access token; always check type, issuer, audience, and authentication contract.

Common claims in a JWT:

- `iss`: trusted issuer.
- `aud`: intended recipient of the token; API must verify the token is meant for that exact API.
- `sub`: subject the token represents.
- `exp`, `nbf`, `iat`: expiration, not-before validity start, and issuance time.
- `jti`: unique token identifier (if supplied by issuer), useful for revoking an individual token.
- `scope` or `scp`: permission scopes; how they map to Spring Security authorities depends on issuer/configuration.
- `cnf`: key-binding confirmation for sender-constrained tokens in applicable profiles.

Do not confuse `iat` with "the user just entered their password": a token can be refreshed without a fresh user authentication event.

## 3. How Are Tokens Stolen?

**XSS (cross-site scripting).** Malicious JavaScript running in the origin can read tokens from `localStorage`, `sessionStorage`, IndexedDB, or accessible JavaScript variables. With `HttpOnly` cookies, scripts cannot read the cookie value directly via `document.cookie`, yet can still **send same-origin requests under the victim's session**. Thus `HttpOnly` reduces cookie exfiltration, without eliminating XSS impact.

**Leaks via URL.** Tokens in query strings easily appear in browser history, proxy/CDN logs, tracking tools, bookmarks, screenshots, or `Referer` headers depending on policy. Tokens in fragments have a different exposure surface, yet are not considered a good way to store or transmit access tokens. RFC 9700 recommends avoiding issuing tokens directly in authorization responses and preferring authorization code with PKCE for appropriate clients.

**Leaks from logs/telemetry.** `Authorization` headers, `Cookie` headers, response bodies containing tokens, URLs, crash reports, or gateway traces easily end up in centralized logs. Redaction is required before writing; never store raw tokens in logs or send tokens to third-party analytics systems.

**Compromised apps or devices.** Malicious browser extensions, malware, rooted/jailbroken devices, unencrypted backups, config files containing tokens, or tokens committed to repositories can all leak credentials.

**Network channels and redirects.** Sending bearer tokens over unencrypted HTTP, redirecting to untrusted origins, or forwarding to third parties poses severe risk. Always use TLS and strictly control audience, redirects, and outbound requests.

**Refresh token replay.** An attacker who obtains a refresh token can use it to mint new access tokens. If refresh tokens lack rotation, sender constraints, or replay controls, the impact lasts far longer than losing a single access token.

**JWT validation flaws.** Accepting wrong issuer/audience, ignoring `exp`, trusting attacker-specified algorithms, confusing signing keys, or accepting tokens meant for another service can turn a "validly signed elsewhere" token into unauthorized access. Spring Security Resource Server provides standard verifiers; never handle JWTs by Base64 decoding alone.

### 3.1. Illustrating the Consequence

~~~text
08:00  User logs in, receives access token (expires at 08:15)
08:03  Token leaks via log or XSS
08:05  User clicks Logout and browser deletes token
08:07  Attacker uses copied token to call API
08:15  Token expires

If the API only verifies JWTs offline without checking revocation status:
- The copied token can still work from 08:05 until before 08:15.
- Browser-side logout cannot make that copy vanish on its own.
If the API enforces immediate revocation checks, the token can be rejected sooner.
~~~

The timestamps only illustrate the risk window. A short `exp` shrinks how long a leaked token can be reused, yet does not stop an ongoing attack by itself.

## 4. Where to Store Tokens? Differences in XSS, CSRF, and Lifecycle

| Storage Location | Who Can Read the Token? | XSS Impact | CSRF / Transmission Risk | Notes |
| --- | --- | --- | --- | --- |
| In-memory JavaScript variable | JavaScript code in app context | Malicious script can use/extract token while running | If client explicitly attaches `Authorization`, browser does not auto-attach header on cross-origin requests | Lost on reload/restart; requires token re-acquisition mechanism |
| `sessionStorage` | Same-origin JavaScript in that tab | Readable under XSS | Does not auto-send token to server | Closing tab usually clears data; **does not stop XSS** |
| `localStorage` / IndexedDB | Same-origin JavaScript | Easily exfiltrated via XSS; data may persist long-term | Does not auto-send token | Avoid storing authentication tokens, refresh tokens, or session IDs in Web Storage |
| Plain cookie (non-HttpOnly) | JavaScript with cookie access and browser | Readable via `document.cookie` | Browser auto-attaches cookie per scope/flags, requiring CSRF review | Unsuitable for protecting bearer tokens |
| `HttpOnly; Secure; SameSite` cookie | Sent conditionally by browser; JavaScript cannot read value directly | Reduces token exfiltration by JS; XSS can still perform actions in-session | Cookie is auto-attached by browser; must assess CSRF, origin, and request semantics | Well-suited for holding session IDs in server-side/BFF models |
| OS secure storage for native apps | OS APIs, scoped by app/device | Browser XSS does not apply identically; malware/root remains a risk | Native client attaches token to requests | Use Keychain/Keystore and Authorization Code + PKCE appropriately |

**Browser design conclusion:** When a trusted backend exists, the **Backend-for-Frontend (BFF)** pattern typically reduces OAuth token exposure: the backend keeps access/refresh tokens server-side; the browser only sends an **`HttpOnly`, `Secure`, `SameSite` session cookie** to the backend. JavaScript never needs to read the refresh token. You must still protect the session cookie, CSRF, and backend against XSS/session riding.

No token storage mechanism is "immune to everything":

- `HttpOnly` does not stop an attacker with XSS from sending valid POST/GET requests within the same origin.
- `SameSite` mitigates many cross-site cookie submissions, yet does not fully replace CSRF design; consider same-site subdomains, legacy browsers, and redirect flows.
- `Secure` requires transmitting cookies over HTTPS in real deployments; it does not protect if the server itself is compromised.
- `localStorage` is easy to code, yet shifts risk into JavaScript readability and long-lived token persistence.
- JavaScript memory only reduces persistence; while XSS is active in-session, an attacker can still call APIs or intercept tokens.
- `CORS` restricts browser cross-origin reading/sending of certain requests; **CORS is not authorization** and does not replace authentication, CSRF, or permission checks.

When storing session cookies, consider the `__Host-` prefix (with `Secure`, `Path=/`, no `Domain`), `HttpOnly`, appropriate `SameSite=Lax` or `Strict`, session ID rotation after login, and server timeouts. Account for OAuth redirects, valid domains, and cross-site compatibility when choosing `SameSite`.

## 5. How Should Tokens Be Sent? Headers, Cookies, Query, and Body

### 5.1. `Authorization: Bearer` — Suited for Header-Based APIs

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
Accept: application/json
~~~

The client explicitly attaches the `Authorization` header. This is the standard approach for OAuth 2.0 bearer tokens. Always use TLS; server-side, validate the token and permissions per endpoint. In browsers, JavaScript needs a way to access the token or route requests through a BFF.

Browsers do not automatically pull tokens from `localStorage` and attach them as `Authorization` headers. Therefore, APIs that **only** accept custom bearer headers explicitly attached by JS are generally less susceptible to classic CSRF relying on auto-sent cookies. However, same-origin XSS can still steal the token or call the API. If the same API also accepts cookies, Basic Auth, or another auto-sent credential mechanism, CSRF evaluation must cover all authentication paths.

### 5.2. Cookies — Auto-Sent per Scope/Flags

~~~http
GET /account HTTP/1.1
Host: app.example.org
Cookie: __Host-session=<opaque-session-id>
~~~

Cookies typically carry a server-referenced **session ID**, without needing to carry a JWT. If an access token is placed directly inside a cookie, that cookie remains a bearer credential; since it is auto-sent, CSRF becomes a concern. With BFF, the backend uses the session ID to look up state and retrieve the OAuth access token server-side, then calls downstream APIs with a bearer header.

An `HttpOnly` cookie is not a security header a resource server can blindly trust as authenticated: the session/token must be verified server-side, tied to the right account, TTL, revocation status, and permissions.

### 5.3. URL Query / Fragment — Avoid Sending Credentials in Addresses

~~~http
GET /api/orders?access_token=<token> HTTP/1.1
Host: api.example.org
~~~

Although the bearer token specification describes alternative transmission methods, putting tokens in URLs easily leaks them via logs/history/tracing; avoid doing so in modern applications. Never pass **refresh tokens** in query strings or redirect URLs.

### 5.4. Body, Redirects, and gRPC

An OAuth token endpoint can accept certain credentials or authorization codes in a POST form body over TLS per protocol; that **differs** from placing bearer access tokens inside JSON bodies of arbitrary custom APIs. With gRPC or other protocols, tokens typically travel in metadata with semantics analogous to `Authorization`; TLS, log redaction, audience, and revocation rules remain unchanged.

**Quick decision table:**

| Client / Architecture | Typical Appropriate Approach | What Must Be Protected |
| --- | --- | --- |
| SPA + BFF | Browser `HttpOnly` session cookie; BFF holds OAuth tokens on backend | CSRF, cookie scope, session store, XSS/session riding |
| SPA calling APIs directly | Authorization Code + PKCE; short-lived access token kept in memory by design | XSS, token refresh, CORS, revocation, PKCE; avoid Web Storage for credentials |
| Mobile / native | Authorization Code + PKCE, store credentials in OS secure storage, bearer header | Deep/app links, OS storage, refresh rotation, device theft |
| Server-to-server | Client Credentials + mTLS/private key or suitable secret; `Authorization` header | Client secrets/keys, scope, audience, rotation, and logging |
| Traditional browser form login | Server session ID via cookie | Session fixation, CSRF, XSS, timeouts, invalidation |

## 6. What Does Token Revocation Mean?

**Revocation** is a system decision that a credential or authorization grant **is no longer accepted**, even if previously unexpired. Actual enforcement depends on whether the token-validating component knows about and enforces that decision.

Separate four distinct actions:

1. **Client deletes token:** stops using it in that specific client. Stolen copies still exist.
2. **Authorization server revokes refresh token:** blocks that refresh token from issuing new access tokens per AS policy. Already-issued access tokens may remain valid until expiration.
3. **Resource server rejects access token:** enforced via introspection, denylist, allowlist, account/session version, or other online policies. This is what actually blocks issued access tokens before expiration.
4. **Broader session/grant revocation:** terminates browser sessions, authorization grants, all devices, or user sessions per policy; state must propagate to relevant services.

### 6.1. RFC 7009 — OAuth 2.0 Token Revocation

RFC 7009 defines an endpoint for clients to request the authorization server revoke access/refresh tokens. Protocol example:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=<url-encoded-token>&token_type_hint=refresh_token
~~~

`token_type_hint` is a hint; the endpoint path is defined by the AS and need not be `/oauth2/revoke`. The client must authenticate to the AS when required by policy/protocol, send the token in the body over TLS, and avoid logging tokens. RFC 7009 requires AS support for revoking refresh tokens; support for revoking access tokens is recommended, though actual capability must be verified per provider.

An **HTTP 200** response is typically returned for both successfully revoked tokens **and already invalid/nonexistent tokens**, limiting token probing. HTTP 200 does not mean every resource server immediately knows the revocation decision. Depending on token type and distributed architecture, state propagation incurs latency.

### 6.2. RFC 7662 — Token Introspection

The resource server sends the token to the AS's introspection endpoint (typically over an authenticated connection). The AS returns metadata with `active`:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

After revocation/expiration, the AS may return:

~~~json
{
  "active": false
}
~~~

`active=false` means the resource server must reject the token. Introspection is commonly applied to opaque/reference tokens, yet **can also verify JWTs** if supported by the AS. Its advantage is that the AS reflects revocation decisions; its cost is a network call, RS–AS authentication, availability dependency, and latency. If the RS caches `active=true` for 60 seconds, revocation may not take effect at the RS until the cache expires. Never claim "instant revocation" when caching or multi-tier state propagation exists.

Define timeouts, bounded retries, circuit breakers, and **fail-closed** behavior for sensitive endpoints when tokens cannot be verified; never switch to "trust the token" merely because introspection is slow.

## 7. Access Token Revocation Strategies

| Strategy | Strengths | Limitations | Best Fit |
| --- | --- | --- | --- |
| **Short access token TTL** | Minimal state dependency; shrinks window for leaked tokens | Cannot immediately block already-issued tokens | Offline JWTs, high-throughput APIs |
| **Opaque token + introspection** | AS decides `active` status on every check | Adds network/infrastructure dependency; caching increases revocation lag | Need fast revocation and centralized control |
| **JWT + denylist** | Retains JWT claims while able to reject before `exp` | RS must query state store; requires TTL cleanup and multi-node sync | Want per-token revocation while still using JWT |
| **JWT + allowlist** | Only tokens permitted by AS/RS work | Larger state store, depends on availability | Strict token control, sensitive resources |
| **Token/session version or issued-after** | Can bulk-block tokens per user/device | Requires state lookup; user-level changes may unintentionally invalidate multiple sessions | Password changes, lost devices, account incidents |
| **Sender-constrained access token** | Reduces replay if attacker only steals token string | Does not replace revocation; requires key management and proof verification | High-value APIs, suitable native/backend clients |
| **Signing-key rotation** | Invalidates tokens signed by retired key in severe incidents | Broad blast radius if old key retired too early | Compromised signing key response; routine rotation uses overlap |

### 7.1. Short TTL and Risk Windows

Suppose a token lives 10 minutes and is stolen at minute three; without instant revocation, the attacker may have nearly 7 minutes left to use it. Choose TTL based on risk, token issuance cost, traffic, and UX. **Short TTL works only when `exp` is validated properly**, server clocks are synchronized, and clock skew is not overly wide.

### 7.2. `jti`-Based JWT Denylist

When issuing JWTs, the issuer should ensure `jti` is sufficiently unique within the issuer's scope. When a token theft is detected, the system records "revoked" in a lookup store shared across all resource servers:

- The key can be (`iss`, `jti`) to avoid collisions across issuers, or a **cryptographic hash of the full token** if no reliable `jti` exists. There is no need to store raw bearer tokens to mark them revoked.
- The denylist TTL persists **at least until the token can no longer be valid** accounting for `exp` and configured clock skew. Expired tokens do not need to stay on the denylist forever.
- Every request must still verify signature, required claims, access permissions, **and** revocation status. Never check only the denylist and bypass the JWT verifier.
- The denylist store must be shared across instances and handle disconnects, TTLs, atomic updates, and sudden flushes. For major incidents, consider durable persistence or reliable event propagation.
- Never trust an arbitrary client-supplied `jti`; the value must come from a JWT already verified against a valid issuer.

An API checking `jti` only at login or an edge gateway while internal entry points skip it does not meet revocation goals.

### 7.3. Version/Epoch Changes to Invalidate Multiple Sessions

An issuer can include `token_version`, `session_id`, or `auth_time` under a dedicated contract. The resource server compares against current state:

~~~text
Token version (signed): 7
Current account token version (database/cache): 8
=> Reject version 7 token, even if signature and exp are valid.
~~~

This technique helps on password changes or full-session locks, with trade-offs: requires state queries, cache invalidation, and clearly defining **blocking the whole user vs. a single session/device**. Never attach security meaning to a claim the RS does not verify.

### 7.4. Rotating Signing Keys on Compromise

Routine signing-key rotation leaves an overlap window between old and new keys so existing tokens expire naturally. If a **private signing key is compromised**, emergency key retirement may be necessary—rejecting all tokens signed by that key, updating JWKS, checking caches, and triggering re-authentication. This is a broad-impact measure unsuitable for revoking a single normal account. Rotating a JWT verification key also **does not revoke refresh tokens** stored at the AS unless the AS handles them separately.

## 8. Stolen Refresh Tokens: Rotation and Replay Detection

A refresh token can mint new access tokens repeatedly. Consequently, a 5-minute access token TTL means little if an attacker holds a long-lived refresh token and keeps exchanging it for new access tokens.

Per OAuth 2.0 Security Best Current Practice (RFC 9700), when issuing refresh tokens to **public clients**, the authorization server must use **refresh token rotation** or **sender-constrained refresh tokens** to detect/mitigate replay, as specified in the standard.

**Rotation** operates as follows:

~~~text
T0: Client holds refresh token R1 (active)
T1: Client uses R1 -> AS issues access token A2 + refresh token R2
    AS invalidates R1, tracks token family relationship
T2: Someone sends R1 again -> reuse of rotated token detected
T3: AS invalidates the token family / active refresh token per policy
    and forces the user/application to re-authenticate
~~~

Reuse detection **does not identify which party is the attacker**. If both parties hold the token, the AS usually cannot tell who resent R1; revoking the token family disrupts the legitimate client too, while blocking the attacker from obtaining further tokens.

**Critical implementation details:**

- Rotation must be **atomic**. Two concurrent refresh requests must not accidentally create two valid token branches. Across multiple tabs/browser instances, coordinate refreshes to avoid self-triggering "reuse detection"; do not let every request fire refreshes indiscriminately.
- Refresh tokens should be bound to client, scope, resource servers, and device/session per policy, with appropriate idle and absolute expirations.
- Store refresh tokens server-side or in a secure store; when storing state at the AS, consider hashing random tokens before persistence rather than keeping raw tokens in databases/logs.
- Reuse detection works only if the AS tracks token family lineage and actually invalidates active tokens after replay.
- Sender-constraining via **mTLS (RFC 8705)** or **DPoP (RFC 9449)** requires additional proof of key possession on use. If only the *token string* leaks without the matching key, replay is difficult; however, malware/XSS controlling the client can still act within the compromised environment.

In OAuth 2.0, **client-side logout**, **revoking refresh tokens at the AS**, and **blocking circulating access tokens at resource servers** are three actions that must be planned separately. Never assume one `/logout` request suffices to clean up every compromised session and token.

## 9. Spring Security Resource Server: Offline JWT Verification

The example below uses **Java 17+**, **Spring Boot 3.5.0**, Spring Security 6.5.x, and **Servlet**. It is a standalone API application accepting access tokens issued by an **external authorization server**. The example **does not issue access/refresh tokens itself**, since a resource server is not an issuer by default.

Three-file structure:

~~~text
token-api/
├── pom.xml
└── src/main/
    ├── java/example/tokenapi/TokenApiApplication.java
    └── resources/application.yml
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>token-api</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/java/example/tokenapi/TokenApiApplication.java`**:

~~~java
package example.tokenapi;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TokenApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(TokenApiApplication.class, args);
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            // Only for APIs using Bearer in the Authorization header;
            // evaluate CSRF separately if adding cookies/Basic to the same API.
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class Endpoints {
        @GetMapping("/health")
        String health() {
            return "ok";
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("subject", authentication.getName());
        }
    }
}
~~~

**`src/main/resources/application.yml`**:

~~~yaml
server:
  port: 8080
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/issuer
          audiences: https://api.example.org
~~~

`idp.example.org` and `api.example.org` are examples; to run, **replace them with your real issuer and the audience that issuer puts in access tokens**. Spring Security uses issuer metadata/JWKs to check signature, `iss`, and expiration; configuring `audiences` adds verification that the token targets this API. The app needs network access to the issuer's metadata/JWKS. It cannot run completely standalone without a real AS and valid token.

Run and observe:

~~~bash
mvn spring-boot:run

# Public endpoint: HTTP 200, body: ok
curl -i http://localhost:8080/health

# Missing Bearer token: HTTP 401
curl -i http://localhost:8080/api/me

# With unexpired token issued by real issuer for right audience:
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:8080/api/me
~~~

With a valid token, the last request returns HTTP 200 and JSON like `{"subject":"user-123"}`; the subject name depends on the issuer. `YOUR_ACCESS_TOKEN` is a placeholder, **not** a real token. Tokens with invalid signatures, expired timestamps, wrong issuer/audience, or missing tokens are rejected per verifier configuration.

**Revocation limitation of this sample:** if the authorization server just revoked an access JWT while the resource server only verifies offline, that JWT **may remain usable until `exp`**. Spring Security does not automatically call introspection or provide a denylist merely because you enabled `oauth2ResourceServer(...jwt(...))`.

## 10. Spring Security Resource Server: Introspection to Check Status

If you need to detect revoked tokens quickly, configure the resource server to use introspection.

Keep `pom.xml` and the controller from Section 9; **replace only** the JWT line in the security chain with:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

At the same time, replace the `spring.security.oauth2.resourceserver.jwt` block in `application.yml` with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: token-api
          client-secret: YOUR_INTROSPECTION_CLIENT_SECRET
~~~

Store the secret via a secret manager or proper environment/config injection; **never commit real secrets to files**. The endpoint URI and credentials must come from the authorization server.

Spring Security sends the bearer token to the introspection endpoint and checks `active`. If `active=false` or introspection fails to validate the token, the request is unauthenticated. When the AS revokes a token so `active=false` and the RS does not serve a stale cached result, the next request can be rejected immediately.

**Note:** `opaqueToken()` mode is an **introspection-based verification mechanism**; it does not require the token to be a random string. If the AS supports introspecting JWTs, the RS can use this configuration with **JWTs** and still receive revocation status. Choose this approach to prioritize checking status at the AS, while evaluating latency, timeouts, availability, and caching.

### 10.1. Choosing the Right Approach for Revocation Requirements

- **Offline JWT:** suits distributed systems needing fast verification that accept a maximum risk window equal to a short TTL or add a denylist/token version.
- **Introspection:** suits cases requiring rapid reflection of revocation or permission state from the AS, accepting online dependency and ensuring verification is never bypassed when the AS fails.
- **Hybrid:** JWT remains validly signed, yet the RS queries a denylist, version, or introspection for sensitive requests. Policies must align across all services.

Placing caches in an API gateway, microservice, or Spring layer can create a **window that continues accepting revoked tokens**. Cache TTLs must match the revocation RTO; never inspect only the AS result while overlooking RS-side caching.

## 11. Standalone Java 17: Simulating a JWT Denylist

This small example illustrates the **expiry + revoke list** rule. It **does not** generate JWTs, verify signatures, act as an OAuth server, and **must not be used as-is as a production token verifier**. Its main purpose is to show two independent conditions that must both hold.

Create file **`RevocationWindowDemo.java`**:

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class RevocationWindowDemo {
    static boolean mayUse(
            String verifiedJti,
            Instant tokenExpiresAt,
            Instant requestAt,
            Map<String, Instant> revoked) {

        // Assumes signature, issuer, audience, and scope are already verified.
        return requestAt.isBefore(tokenExpiresAt)
            && !revoked.containsKey(verifiedJti);
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Instant expires = start.plusSeconds(300);
        Map<String, Instant> denylist = new HashMap<>();

        System.out.println(mayUse(
            "issuer-A:jti-42", expires, start.plusSeconds(60), denylist));

        // AS / security system receives revoke request after 90 seconds.
        denylist.put("issuer-A:jti-42", expires);

        System.out.println(mayUse(
            "issuer-A:jti-42", expires, start.plusSeconds(120), denylist));

        System.out.println(mayUse(
            "issuer-A:jti-99", expires, start.plusSeconds(301), denylist));
    }
}
~~~

Run:

~~~bash
javac RevocationWindowDemo.java
java RevocationWindowDemo
~~~

**Exact stdout:**

~~~text
true
false
false
~~~

Explanation:

1. `jti-42` is unexpired and absent from the denylist, so it is accepted **in this hypothetical model**.
2. Once the denylist records that token, it is unexpired yet rejected.
3. `jti-99` is absent from the denylist yet past `exp`, so it is also rejected.

The code uses a local `Map` for simulation; in real deployments, query a shared store (Redis/database, etc.), protect keys (combining issuer + `jti` or fingerprint), purge records based on `exp` and clock skew, handle races, fail closed, and weigh per-request cost. Crucially, **never blindly trust `verifiedJti` taken straight from a request**: it must be extracted **after Spring Security has verified the JWT**.

### 11.1. Where to Integrate into Spring Security?

With JWTs, Spring Security provides `JwtDecoder`, `NimbusJwtDecoder`, `OAuth2TokenValidator<Jwt>`, and `DelegatingOAuth2TokenValidator` to combine issuer/expiry/audience checks with revocation policies. A validator can check the revocation store by (`iss`, `jti`) **after the signature is decoded/verified**, returning `invalid_token` if revoked. It is vital to preserve **standard validators** when adding a revocation validator; replacing the entire validator without retaining issuer/expiry checks can silently weaken protection.

When using opaque tokens, Spring Security supports `OpaqueTokenIntrospector`; generally let the AS return accurate `active` status rather than maintaining a second out-of-sync blocklist yourself.

All rules must be enforced inside the **request authentication/authorization pipeline**, not only on the logout page or in JavaScript. Add extra policies for high-value actions where needed.

## 12. Logout and Responding When Token Theft Is Suspected

A reliable "logout" operation must explicitly define its scope: **current tab**, **current device**, **all devices**, **application authorization grant**, or **locked account**.

### 12.1. When a User Explicitly Logs Out

1. Client stops using the access token and clears held credentials.
2. If a server session exists, invalidate the session on the backend and clear the cookie via matching `Set-Cookie`.
3. For OAuth/OIDC clients, consider revoking the refresh token at the AS per RFC 7009, or ending the grant/session via IdP APIs when supported.
4. If policy requires access tokens to stop working before `exp`, add revocation/denylist/introspection; do not only wipe client data.
5. Synchronize state with resource servers if they cache/check state; verify how long old tokens remain accepted.

Never promise "Logout everywhere = all old JWTs stop working immediately" if the architecture only uses offline JWTs with a 15-minute TTL. Honest documentation of the remaining validity window is essential.

### 12.2. When Token Exposure Is Detected

Priority response:

- Identify the compromised credential type: access token, refresh token, session cookie, signing key, client secret, or entire data store.
- Revoke the refresh token or entire token family and related sessions/authorization grants; assess blocking circulating access tokens.
- For a leaked signing key, execute emergency key rotation/retirement and prevent verifiers from accepting newly forged tokens signed with the old key.
- Fix the root cause: XSS, log leaks, URL leaks, insecure storage, missing audience/issuer checks, non-TLS transport, or compromised devices.
- Inspect redacted logs to identify anomalous actions, token usage times, and affected users/issuers/audiences; avoid re-exposing tokens during investigation.
- Notify account owners, force re-authentication or invalidate sessions per risk level, and audit sensitive data changes.

**The number of exposed tokens and available revocation mechanisms** determine response scope. Revoking one `jti` differs vastly from retiring a shared signing key used across millions of tokens.

## 13. Common Implementation Mistakes

**Mistake 1: "JWTs are signed so they cannot be revoked."** They can be blocked via denylists, introspection, allowlists, version/epoch, or key rotation when needed. In return, the system must maintain state or accept online dependency.

**Mistake 2: "Once the refresh token is revoked, old access tokens die immediately."** Self-contained already-issued access tokens do not automatically know the refresh token was revoked. Resource-server rejection policies or waiting out expiration are required.

**Mistake 3: "Clearing `localStorage` takes the token away from the attacker."** A copy already exfiltrated from the browser remains valid until rejected by the RS or expired.

**Mistake 4: "Putting the access token in an `HttpOnly` cookie eliminates XSS and CSRF."** XSS can still trigger authenticated requests; auto-sent cookies can enable CSRF. Server-side XSS, CSRF, session security, and authorization controls remain necessary.

**Mistake 5: "`sessionStorage` is immune to XSS."** Same-origin JavaScript can read it. Only its lifecycle/persistence differs from `localStorage`.

**Mistake 6: "Enabling CORS secures the API."** CORS does not replace authentication/authorization; native clients, curl, and attackers holding tokens can still call the API. CORS also does not fix XSS in a permitted origin.

**Mistake 7: "Sending JWTs in URLs is safe over HTTPS."** HTTPS encrypts the wire, yet query parameters enter logs, browser histories, and monitoring systems.

**Mistake 8: "Introspection always revokes instantaneously."** Caches at AS/RS/gateway and distributed replication introduce lag. Measure the actual time until `active=false` is enforced by all resource servers.

**Mistake 9: "Checking signature and `exp` is enough."** You must verify issuer, audience, algorithm/key, timestamps, scope, resource permissions, and revocation status when policy requires.

**Mistake 10: "Refresh token rotation just means generating a new R2 string."** You must invalidate R1, track token family lineage, detect replay, and handle concurrent/race requests.

**Mistake 11: "An in-memory blocklist per node is enough."** Requests hitting other nodes can still succeed. Use a shared store or consistent propagation matching your architecture.

**Mistake 12: "Rotating the signing key to log out one device."** This is a heavy-handed action that can invalidate many users. Use per-token/per-session revocation where appropriate.

**Mistake 13: "Resource server accepts ID tokens as bearer access tokens."** ID tokens have a different audience/intended purpose; never use ID tokens to call APIs unless a specialized profile explicitly specifies it.

**Mistake 14: "Disable CSRF because we use JWT."** How the browser **sends credentials** determines classic CSRF risk. JWTs in auto-sent cookies still require CSRF protection; APIs accepting only client-attached bearer headers have a different threat model.

## 14. Design and Testing Checklist

**Before deployment:**

1. Identify client type: browser/BFF, native, server-side, or service account. Who holds access/refresh tokens? Do copies exist?
2. Specify **access token format**, issuer, audience, scope, `exp`, `jti`, and verifier mechanism; separate ID tokens and refresh tokens.
3. Set a **maximum revocation time target**. If "a few seconds" is required, long-TTL offline JWTs without state checks will not meet it.
4. Choose access revocation: introspection, denylist, version, or short TTL; account for caching, multi-node, and fail-closed behavior.
5. Define refresh policy: rotation/sender binding, reuse detection, idle/absolute TTL, and token families.
6. Choose transport channel: TLS, `Authorization` header / BFF cookie, no query/fragment; configure CSRF/CORS properly.
7. Apply log redaction, secret storage, alerting, rate limiting, and security auditing.

**Practical testing:**

| Test Case | Expected Result |
| --- | --- |
| Missing access token | `401 Unauthorized` on authentication-required endpoints |
| Access token with wrong signature/issuer/audience or expired | Rejected |
| Valid token lacking sufficient scope/permission | `403 Forbidden` or denied per policy |
| Revoked opaque token when RS introspects `active=false` | Rejected on next uncached request |
| Offline JWT revoked at AS but unexpired | May still be accepted: documented limitation |
| JWT + denylist with flagged `jti` | Rejected across **every** instance |
| Rotated refresh token R1 reused later | AS detects replay per policy and acts on token family |
| Client logs out yet stolen token copy is replayed | Must behave per committed policy, never assumed safe |
| Cookie missing CSRF token on state-changing request | Blocked if using cookie-based auth |
| API uses Authorization bearer while browser suffers XSS | Assess token theft / session riding impact; do not rely on CORS alone |
| AS introspection slow or unreachable | RS never accepts unverified tokens |
| Token lacking valid audience | Rejected at other resource servers |

When measuring revocation effectiveness, record `T_revoke` at the AS and `T_first_reject` at **each** RS, stating cache TTLs and clock skew. The real window is the delay until every API entry point rejects the token, not merely when the revoke API returns HTTP 200.

## 15. Self-Check Questions

**Q1.** A user logs out and clears the token in the browser. An attacker holds a copied JWT with 4 minutes of validity remaining. Is it blocked immediately?  
**A:** Not necessarily. If the RS only verifies signatures/claims offline, the JWT may keep working until `exp`. RS-side revocation enforcement is needed to block early.

**Q2.** Are JWTs always stateless?  
**A:** Verifying a JWT itself can be stateless; adding a denylist/version/introspection introduces state dependency. JWT is a format, not a guarantee that the architecture is completely stateless.

**Q3.** Why should refresh tokens not be stored in `localStorage`?  
**A:** Same-origin JavaScript can read it, allowing XSS to steal a token capable of sustaining long-term access. Prefer BFF/server-side or client-appropriate secure storage.

**Q4.** Does an `HttpOnly` cookie eliminate XSS?  
**A:** No. It prevents JavaScript from reading the cookie directly, yet XSS can still issue authenticated same-origin requests and perform actions.

**Q5.** What is the fundamental difference between revoking a refresh token and revoking an access token?  
**A:** Refresh revocation blocks minting new tokens; access revocation must cause resource servers to reject already-issued tokens. The two operations may require different mechanisms.

**Q6.** Why might introspection not reflect revocation instantaneously?  
**A:** Caches, distributed replication lag, backend policies, and networking can cause an RS to keep using a prior result.

**Q7.** Does password + browser token stored in a cookie make an API immune to CSRF?  
**A:** Not automatically. Browsers can automatically attach cookies within scope; CSRF defense is required for state-changing operations.

**Q8.** What risks do refresh token rotation and sender-constrained tokens mitigate?  
**A:** Rotation helps detect refresh token reuse; sender constraints make a stolen token string harder to replay from another sender lacking the matching private key/proof.

## 16. Official Documentation

- [OAuth 2.0 Security Best Current Practice – RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token rotation, replay prevention, sender-constrained access tokens, and modern OAuth defenses.
- [OAuth 2.0 Token Revocation – RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html): semantics of the token revocation endpoint.
- [OAuth 2.0 Token Introspection – RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html): `active` and metadata when a resource server queries an AS.
- [OAuth 2.0 Bearer Token Usage – RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html): sending bearer tokens and risks of bearer usage.
- [OAuth 2.0 Demonstrating Proof of Possession (DPoP) – RFC 9449](https://www.rfc-editor.org/rfc/rfc9449.html): sender constraint for tokens.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): configuring JWT verification, issuer, audience, and validators.
- [Spring Security – OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, custom introspectors, and revocation behavior.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session storage, cookies, and session protection.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): risks of tokens in Web Storage.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF with browser credentials.
