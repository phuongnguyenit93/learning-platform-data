# Bearer Semantics: Usage Rights Bound to Token Possession

In an OAuth 2.0 Resource Server, a **bearer token** is a way of using an access token based on the principle that **any party possessing a valid token can present it to request the access rights that the token represents**. The Resource Server must validate the token and authorization conditions, but with pure bearer tokens, it **does not require the sender to prove possession of a separate cryptographic key bound to the token**.

This is the key point for understanding both the convenience and the risks of bearer tokens. A token works much like a **temporary access key**: having the key does not mean you can open every door; however, anyone who picks up the key can try to open the doors that the key is permitted to unlock.

According to [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), the defining property of a bearer token is that the token holder can use the token without presenting proof of possession of a cryptographic key. This holds true for **both JWT access tokens and opaque access tokens** if they are used with bearer semantics.

## 1. What does “Bearer” mean?

The term **bearer** refers to **the person or party carrying or possessing** a credential value. Suppose the Authorization Server issues an access token `T` to client A:

1. Client A sends `T` to `orders-api` using the `Authorization: Bearer T` header.
2. The Resource Server validates `T` and allows operations within the token's scope.
3. If an unauthorized party B copies the entire value of `T`, B can also send `Authorization: Bearer T`.
4. If `T` is still valid and B's request satisfies the authorization conditions, **the bearer token by itself does not help the Resource Server distinguish A from B**.

The exact takeaway to keep in mind: **possessing the token allows requesting access according to the token's permissions**, not that every request carrying a token must be accepted. The server can still reject expired tokens, tokens with the wrong audience, tokens lacking required scopes, or actions exceeding data ownership rules.

~~~text
               Authorization Server
                       |
            issues access token T
                       |
                       v
                Legitimate Client A
                       |
     GET /api/orders   | Authorization: Bearer T
                       v
                Resource Server
                validates T + permissions
                       |
                 returns result


 If T is leaked:
                Unauthorized Party B
                       |
     GET /api/orders   | Authorization: Bearer T
                       v
                Resource Server
                validates T + permissions
                       |
     T still valid? B can exercise the permissions T grants.
~~~

The Resource Server can apply additional protections such as data-level authorization, behavioral limits, or sender-constrained tokens. However, those measures **do not change the fundamental definition** of a pure bearer token.

### “Possessing” a token is not the same as “being the legitimate owner”

Three concepts are often confused:

| Concept | Question answered | Example |
|---|---|---|
| **Possession** — holding the token | Does the request carry a token value? | Header contains `Bearer T` |
| **Token validation** — token is valid | Was the token issued by a trusted source, is it still valid, and is it intended for this API? | Valid JWT signature; `exp` not expired; matching `iss` and `aud` |
| **Authorization** — permitted to act | Do the token's permissions and system policies allow this action? | `orders.read` and the order belongs to the corresponding customer |

With bearer tokens, having `T` is usually enough to **present proof of authorization at the token layer**. It does not by itself prove that the party making the request is the original logged-in user, the original application, or the original device.

## 2. Bearer is a usage semantic, not a token format

A common misconception is equating “bearer” with “JWT”. In reality, there are two independent axes:

- **Token format**: a signed JWT, an opaque string, or another representation defined by the Authorization Server's contract.
- **How usage rights are proven**: pure bearer or sender-constrained token, such as mTLS/DPoP.

| Token | How does the Resource Server validate it? | What if someone else obtains that exact token? |
|---|---|---|
| JWT access token used as bearer | Verifies signature, timestamps, issuer, audience, and claims | Can replay the still-valid token within the granted permissions |
| Opaque access token used as bearer | Typically calls an introspection endpoint to check status/permissions | Can replay the token while `active` within the granted permissions |
| Sender-constrained access token | Checks token validity **and** proof of the sender | Simply obtaining the token string is usually not enough; the appropriate proof/key is also needed |

Crucially, **a signed JWT does not mean the token is bound to the request sender**. A JWT signature typically proves that the token has not been tampered with and was signed by a trusted issuer; **it does not prove that the current client is the one to which the AS issued the token**.

### Example of a JWT bearer token

Suppose the valid claim payload issued by the AS is:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794703600
}
~~~

If the token has a valid signature, the Resource Server can determine that the token represents subject `customer-42`, is intended only for `orders-api`, and carries the `orders.read` scope. However, if copied, **the party sending the token is not necessarily customer 42 themselves**. The `sub` claim is information about the subject recorded by the AS in the token; it is not live proof that that subject is directly performing the operation.

## 3. Bearer Token Flow over HTTP

OAuth 2.0 specifies the common, recommended way to present a bearer token as an HTTP header:

~~~http
GET /api/orders/1001 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
~~~

The value after `Bearer` is the **access token** that the client is authorized to use. The request does not need to send a password, refresh token, or client secret at the same time. The Resource Server validates the token according to its configured mechanism.

~~~text
  Client                   Resource Server               Authorization Server
    |                            |                                 |
    |-- Authorization: Bearer T ->|                                 |
    |                            |                                 |
    |                            |-- [JWT] verify with trusted     |
    |                            |         public key              |
    |                            |                                 |
    |                            |-- [opaque] introspect T ------->|
    |                            |<--- active, scope, sub, ... -----|
    |                            |                                 |
    |                            |-- check scope, audience,        |
    |                            |   and endpoint policy           |
    |<--------- 200/401/403 ------|                                 |
~~~

The two branches in the diagram are **alternative verification options**, not both required on every request.

### A bearer token is not an instruction to “skip authentication”

In Spring Security, using bearer tokens still goes through a full authentication process:

1. Extract the token from the request.
2. Wrap the token into an `Authentication` mechanism.
3. Verify it using the configured JWT decoder or opaque token introspector.
4. Build the principal and authorities if the token is valid.
5. Evaluate the API's authorization rules.

“Not having to prove an additional private key” does not mean “not validating the token”.

## 4. Why does a leaked token lead to replay risk?

**Token replay** is a situation where a valid token value is captured and resent from another source. With pure bearer tokens, resending the exact same token string is not blocked by the bearer mechanism alone.

Example:

- Token `T` is issued to `shop-web` with the `orders.read` permission on `orders-api`, expiring in 10 minutes.
- Within those 10 minutes, the token accidentally appears in application logs or a debugging tool.
- An unauthorized person with log read access retrieves `T` and sends a request from another device.
- If the Resource Server only requires a bearer token, the token is still valid, matches the audience, and the request does not violate additional data permissions, that request can be accepted.

Here, **TLS cannot save a token already leaked from logs**. TLS protects data in transit; it cannot prevent someone from using a secret copied from elsewhere.

### Common bearer token leak vectors

| Leak source | How it happens | Impact |
|---|---|---|
| HTTP instead of HTTPS | Third parties can observe or tamper with traffic | Token stolen in transit |
| Logs at API gateway, reverse proxy, app | Logging full request headers, traces, exceptions | Log readers can copy `Authorization` |
| URL query | Token appears in access logs, browser history, shared links, or referrer headers | Very hard to control where the token propagates |
| Injected JavaScript (XSS) | Malicious script can access tokens in the browser environment | Reads or uses the token within the user session |
| Browser extensions, debug tools, telemetry | Capturing requests/responses, storing headers | Token spreads to unintended systems |
| Insecure client-side storage | Config files, local storage, memory, or backups accessed without authorization | Token gets reused |
| Sharing tokens via chat, tickets, screenshots | Incident responders accidentally paste real tokens | Multiple parties hold the access secret |

The examples above illustrate the **risk surface**, and do not imply that every system or storage medium carries the same level of danger. Sensitivity also depends on token lifetime, token permissions, and an attacker's access capabilities.

### What limits token replay?

A leaked bearer token is not necessarily still usable if:

- The token has expired (`exp`) or has been invalidated through the verification system in use.
- The token is not intended for the called API (different `aud`).
- The token lacks the required scope/authority.
- Resource policy denies access even when the scope matches.
- The Resource Server enforces additional requirements that the caller does not satisfy, such as sender-constrained proof.

**Damage mitigation principle:** the shorter the token lifetime, the narrower the permissions, and the more specific the audience, the smaller the impact of a leak tends to be.

## 5. What is actually proven when the RS receives Bearer T?

Suppose an API receives a token and decodes it to:

~~~json
{
  "sub": "alice",
  "client_id": "shop-web",
  "scope": "profile.read",
  "aud": ["profile-api"]
}
~~~

The Resource Server can rely on verified claims to process the request **as a request authorized by the token on behalf of subject `alice`**. However, the token itself does not prove:

- That the person holding the phone or computer is Alice.
- That the request originated from the original `shop-web` application.
- That the request came from the exact IP or device that originally received the token.
- That Alice is still interactively logged into the browser.
- That every profile or record in the system belongs to Alice.

The system still needs corresponding control layers. For example, reading `GET /api/profiles/alice` may be allowed with claim `sub=alice`, whereas reading `/api/profiles/bob` must be blocked if Alice does not have permission to access Bob.

**Do not treat email, `sub`, or `client_id` in a token as “proof that the sender is the legitimate owner”**. They are claims/attributes trusted after token verification, not proof of sender possession.

## 6. Where does Spring Security process bearer tokens?

In a Spring MVC Resource Server, the default mechanism is designed around HTTP `Authorization: Bearer ...`:

~~~text
HTTP request
    |
    v
Spring Security FilterChain
    |
    v
BearerTokenAuthenticationFilter
    |
    +-- BearerTokenResolver extracts token from request
    |
    +-- AuthenticationManager / AuthenticationProvider
    |       |
    |       +-- JWT: JwtDecoder and validators
    |       |
    |       +-- Opaque: OpaqueTokenIntrospector
    |
    +-- authentication succeeds -> SecurityContext holds Authentication
    |
    v
AuthorizationFilter / method security
    |
    +-- scope, role, data access policies
    |
    v
Controller / business logic
~~~

This is a conceptual description; component ordering may be affected by configuring multiple `SecurityFilterChain` beans and custom application filters.

Key components:

| Component | Responsibility |
|---|---|
| `BearerTokenAuthenticationFilter` | Detects the bearer token and initiates authentication |
| `BearerTokenResolver` | Decides where in the HTTP request to read the token |
| `DefaultBearerTokenResolver` | By default, reads from the `Authorization` header |
| `JwtDecoder` | Decodes and verifies JWT signatures and claims as configured |
| `OpaqueTokenIntrospector` | Validates the token via introspection and builds a principal from returned attributes |
| `Authentication` / `SecurityContext` | Represents the authenticated principal and authorities for the request |
| Authorization rules | Decides which endpoints/methods/resources can be accessed |

Spring Security **does not automatically infer that a token was sent by the same device that received it**. If sender-constrained tokens are used, the system must have support and configuration to verify that binding proof.

### Configuring a Resource Server with JWT bearer tokens

Example for a Spring MVC servlet application using modern Spring Security:

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

Configuring `issuer-uri` specifies the trusted issuer; `audiences` binds the token to `orders-api`. The `audiences` property is available in modern Spring Boot versions; if using an unsupported version, add an audience validator in Java instead of omitting this check.

`SecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Security assumption of the example:** `/api/**` is an API that only accepts access tokens in `Authorization`, and does not rely on browser cookies/sessions for authentication. If the same endpoints accept automatically attached cookies or the application serves login forms, you must redesign CSRF protection rather than copying `csrf(...disable)`.

A token with claim `scope: "orders.read"` is typically mapped by Spring Security to authority `SCOPE_orders.read`. It permits **GET** under the rule above, while still denying **POST** if `SCOPE_orders.write` is missing. This code checks permissions at the endpoint level; controllers/services must still check ownership of individual orders.

### Testing a request with curl

Example using a test token obtained from the Authorization Server:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders/1001
~~~

Do not place real access tokens in documentation, publicly shared shell histories, screenshots, or logging systems. Local environment variables must also be managed according to the runtime environment's secrets policy.

A request may:

- Return `200 OK` if the token is valid, has the required scope, and is permitted to read the order.
- Return `401 Unauthorized` if no token is present, the token is invalid, or the token is expired.
- Return `403 Forbidden` if the token is valid but lacks permissions, or data access rules deny it.

Exact status codes and error bodies depend on application configuration, exception handlers, and additional authentication/authorization mechanisms.

## 7. Choosing where to carry the bearer token

RFC 6750 describes transport methods for bearer tokens in HTTP. For modern APIs, **the `Authorization` header is the preferred approach**:

~~~http
Authorization: Bearer <access_token>
~~~

Several other transport forms exist in the specification or legacy systems, but carry higher risks.

| Token location | Assessment | Reason |
|---|---|---|
| `Authorization` header | Recommended default choice | Separates credentials from the URL, uses standard HTTP authentication mechanics |
| Form body `application/x-www-form-urlencoded` | Conditional exception in RFC 6750 | Inconvenient, subject to strict conditions, and easily captured in payload logs |
| URL query `?access_token=...` | Avoid using | Easily leaked through URL logs, browser history, referrer headers, and shared links |
| Cookie | Not the default bearer location for Resource Servers | Browsers send cookies automatically; requires evaluating CSRF, SameSite, cookie scope, and session architecture |

According to `DefaultBearerTokenResolver`, Spring Security by default **does not accept** bearer tokens from URI query parameters or form bodies. Only enable those sources if there is a special requirement, the security consequences are understood, and the token exposure surface is restricted.

Do not create “convenience” patterns like:

~~~http
GET /api/orders?access_token=<token>
~~~

because tokens in URLs can pass through many layers that record request metadata. Even if an API itself does not log URLs, proxies, APMs, browsers, or external infrastructure can still store that information.

### HTTP headers do not guarantee tokens won't be logged

Applications often have logging filters or API gateways that record request headers. Therefore, you must proactively **redact `Authorization`**, `Proxy-Authorization`, and similar secret headers before sending data to logs, tracing, crash reports, or analytics tools.

Safer log example:

~~~text
GET /api/orders/1001
Authorization: [REDACTED]
traceId: 9d5f...
status: 200
~~~

Avoid logging full token values, even in shared development environments or when returning error messages to users.

## 8. Bearer tokens, HTTPS, and the limits of transport security

**HTTPS/TLS is a foundational requirement** when transmitting bearer tokens over a network. It protects request contents from eavesdropping and tampering in transit between TLS termination points.

However, keep these distinctions clear:

- **TLS protects the token in transit** between trusted TLS endpoints.
- **JWT signatures protect token integrity and signing origin**, not preventing a leaked token from being replayed.
- **Lifetime, scope, and audience** narrow the time window and scope in which a token can be used.
- **Sender-constrained proof** adds a condition so that a stolen token string alone is not sufficient for a request.

If TLS terminates at a load balancer or API gateway and traffic is forwarded internally, the internal forwarding path must also be protected according to the trust boundary. Do not assume an “internal” hop can safely carry bearer tokens over an insecure channel.

### Bearer semantics are not bound by default to IP or User-Agent

Some systems attempt to record the IP/User-Agent at token issuance and reject the token if it appears from a new IP. This is an **additional policy** and has drawbacks: mobile devices, VPNs, proxies, NAT, and browser updates can change these values. IP or User-Agent **is not cryptographic proof of token possession**. Checking them should not be considered a complete replacement for sender-constrained tokens.

## 9. How to reduce bearer token risks

Because possession is the deciding factor, token protection must span the entire lifecycle: **issuance → transmission → usage → storage → expiration/revocation**.

### 9.1. Limiting token scope

The Authorization Server should issue access tokens following the principle of least privilege:

- **Specific audience**: a token for `orders-api` must not automatically work for `billing-api`.
- **Minimal scopes**: an application that only reads orders receives `orders.read`, not `orders.write` if unneeded.
- **Reasonable lifetime**: short-lived tokens limit the window an attacker can exploit.
- **Data-level authorization**: `orders.read` does not mean reading every order; the API must evaluate ownership/tenant/status.

For JWTs, the Resource Server must verify the signature and required claims, especially `iss`, `aud`, `exp`, and related requirements. For opaque tokens, the Resource Server must verify status through a trusted mechanism such as introspection while enforcing API access permissions.

### 9.2. Managing lifetime and revocation

Suppose an access token has 5 minutes remaining before expiration. If leaked, an attacker can exploit it during that window unless other revocation/restriction mechanisms exist.

Operational options include:

1. **Short-lived access tokens:** shrink the replay window.
2. **Introspection:** the Resource Server queries the token's current status at the Authorization Server; timeouts and caching must be controlled.
3. **Denylist/permission versioning/additional state checks:** support early revocation in a locally verified JWT model, if designed consistently.
4. **Sender-constrained tokens:** reduce the usability of a leaked token alone.

Client-side “user logout” only clears client state and may trigger a separate revocation mechanism. **It does not automatically invalidate all issued copies of an access token** at Resource Servers performing local JWT verification.

If introspection responses are cached, the cache duration can delay revocation enforcement. Cache TTL must be designed around security requirements rather than assuming introspection is always instantaneous across every architecture.

### 9.3. Keeping tokens away from leak surfaces

Depending on client type, protections differ:

| Client | Key considerations |
|---|---|
| Backend server | Store tokens/secrets in memory or a controlled secret store; avoid logs and dumps |
| Browser SPA application | JavaScript compromised via XSS can read tokens accessible from JS; prefer architectures and mechanisms that minimize exposure |
| Browser with Backend for Frontend (BFF) | Backend holds tokens; browser uses properly protected session cookies; must handle CSRF and session security |
| Mobile/native app | Use platform secure storage APIs/keystores; avoid inappropriate logs and backups |
| Service-to-service | Protect tokens in memory, communication channels, and telemetry; consider mTLS/DPoP when required |

There is no single token storage choice that is universally right for every application. `localStorage` and `sessionStorage` are convenient, but scripts running on the same origin can access them; `HttpOnly` cookies prevent JavaScript from reading the cookie directly, but browsers send cookies automatically, introducing CSRF concerns if cookies are used for authentication. Evaluate the **overall threat model** rather than drawing conclusions solely from the storage location.

## 10. Sender-constrained access tokens: when possession is not enough

OAuth 2.0 Security Best Current Practice ([RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)) recommends using **sender-constrained access token** mechanisms where appropriate to restrict reuse of stolen tokens.

Two common standard approaches exist:

### 10.1. Mutual TLS (mTLS) — RFC 8705

The Authorization Server binds the access token to the TLS client's identity/certificate. When the Resource Server receives the token, it inspects the certificate information authenticated by the mTLS connection and verifies that the certificate matches the token's binding.

~~~text
Client holds token T + client certificate's private key
           |
           | TLS handshake proves possession of private key
           | Authorization: Bearer T
           v
Resource Server
           |
           +-- verifies T
           +-- verifies client certificate bound to T
           +-- enforces permissions
~~~

If an attacker only obtains the string `T` without the ability to use the corresponding private key/certificate, they generally cannot use the token at a Resource Server that properly enforces the binding. Trust configuration across load balancers, proxies, and TLS termination must be designed carefully.

### 10.2. DPoP (Demonstrating Proof of Possession) — RFC 9449

DPoP binds a token to a public/private key pair held by the client. With each request, the client can send a **DPoP proof JWT** signed with its private key, bound to request details.

Conceptual request structure example:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP <access_token>
DPoP: <signed_proof_jwt>
~~~

The Resource Server must check all of the following:

- Whether the token is valid and bound to the client's public key.
- Whether the DPoP proof signature is valid.
- Whether the proof matches the protected HTTP method and URI.
- Whether timestamp, proof identifier, and token binding values satisfy anti-replay requirements.

Note that **Spring Security's default `Bearer` Resource Server does not automatically become a DPoP Resource Server simply by changing a header or configuring `jwt()`**. Properly supporting DPoP/mTLS requires using the appropriate components, configuration, and binding verification implementations across the Authorization Server, client, and Resource Server.

### Fundamental comparison

| Characteristic | Pure Bearer | Sender-constrained |
|---|---|---|
| Holding only a valid token string | May be enough to request access | Insufficient without a valid proof |
| Proof of sender key | Not required | Required |
| Prevents replay when token alone is copied | No, absent additional controls | Can prevent depending on threat model and binding mechanism |
| Implementation complexity | Lower | Must manage keys/certificates, proofs, verification, and integration |
| If both token **and** sender key are compromised | Token can be abused | Binding can be bypassed; not absolute |

Sender-constraining mitigates an important class of attacks, but **does not make a compromised client application completely secure**. If an attacker controls both the token and the key, or can instruct the client to sign proofs, unauthorized actions can still occur.

## 11. Distinguishing Bearer tokens from ID tokens and refresh tokens

Even though they are all “token” strings, their roles differ:

| Token type | Where is it sent? | Purpose |
|---|---|---|
| **Access token** | Resource Server / API | Authorizes access to resources based on scope, audience, and policy |
| **ID token (OIDC)** | OIDC Client / Relying Party | Provides user authentication information to the client |
| **Refresh token** | Authorization Server / token endpoint | Obtains new access tokens under permitted policies |

Do not take an ID token and send `Authorization: Bearer <id_token>` to an API. Even though an ID token may also be a signed JWT, **its audience and purpose are typically meant for the client rather than the Resource Server**.

A refresh token is also a sensitive secret. It can allow obtaining additional access tokens and requires dedicated protections, including rotation policies or sender constraints depending on client type and applicable security standards.

### Also do not confuse Bearer tokens with API keys

API keys and bearer tokens often feel similar in usage: anyone who knows the secret value can send a request. However, OAuth access tokens typically carry standardized attributes such as issuer, audience, scope, and expiration; API keys may follow system-specific mechanisms. **The similarity in secret reusability does not turn every API key into an OAuth bearer access token**.

## 12. 401, 403, and the meaning of WWW-Authenticate

When a bearer token request fails, distinguishing authentication errors from authorization errors helps clients respond properly.

| Situation | Typical HTTP result | Meaning |
|---|---|---|
| Missing token when endpoint requires authentication | `401 Unauthorized` | Client must provide valid authentication credentials |
| Malformed, rejected, or expired bearer token | `401 Unauthorized` | Token cannot be used to authenticate the request |
| Valid token lacking `orders.write` for a modifying action | `403 Forbidden` | Authenticated, but lacks permission |
| Valid token, but user does not own the order | `403` or `404` per API policy | Data permission condition not met |
| Request contains multiple token presentations/malformed header | May return `400 Bad Request` | Request does not follow bearer token specification |

RFC 6750 describes the `WWW-Authenticate` header for a Resource Server to communicate information about bearer authentication. Illustrative example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Or when the token is valid but lacks the required scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Applications may hide detailed error information to avoid leaking system internals. Never include raw tokens or Authorization Server credentials in error messages returned to clients.

## 13. A complete example: stealing a token to read orders

Suppose a shop has:

- `orders-api` validating JWT bearer tokens from issuer `https://idp.example.com/realms/shop`.
- A JWT with `sub=alice`, `aud=["orders-api"]`, `scope="orders.read"`, and 8 minutes remaining before expiration.
- Endpoint `GET /api/orders/1001` returning order 1001 details for Alice.
- Controller/service performing order ownership checks.

Consider four requests:

| Sender and request | Expected outcome | Explanation |
|---|---|---|
| Alice uses her valid token to view her order 1001 | Allowed | Valid token, right API, has scope, valid owner |
| Bob copies Alice's token and views order 1001 | **May be allowed** if relying only on the stated conditions | RS receives the same token/claim `sub=alice`; does not know Bob is the actual sender |
| Bob uses Alice's token to call `POST /api/orders` | Denied (typically 403) | Token lacks `orders.write` |
| Bob uses Alice's token on `billing-api` | Denied if billing properly checks audience | Token only has `aud=orders-api` |

The second case is the most important lesson: even order ownership checks **cannot distinguish someone who stole Alice's token** when decisions rely on the same authenticated `sub`. Therefore, beyond data permission checks, the system must reduce token leakage risks and limit replayability.

If business policy requires strong assurance for sensitive actions such as changing a bank account, appropriate additional controls must be designed (for example, step-up authentication, sender-constrained tokens, or transaction approval mechanisms). **A bearer token with the right scope does not guarantee that the real person is performing a high-risk action.**

## 14. Misconceptions to avoid

**“Bearer means a token that does not need verification.”** False. You still must verify the token, permissions, and resource policies. Bearer only means not requiring separate cryptographic key proof when presenting a pure bearer token.

**“A signed JWT means hackers cannot use a stolen token.”** False. An attacker does not need to modify the token; simply replaying the original token string remains valid if other conditions allow it.

**“Opaque tokens cannot be replayed.”** False. Opaque tokens used with bearer semantics can still be copied and reused until invalidated.

**“Having a `sub` claim means we know that exact person sent the request.”** False. `sub` is the identity recorded by the AS in the token, not live verification of who holds the token at the time of the API call.

**“HTTPS is enough; no need to worry about logs/storage.”** False. TLS protects transit, but does not solve token leaks at endpoints, traces, browsers, or storage.

**“Deleting the token on the client revokes it on the server.”** False. There must be expiration/revocation mechanisms actually enforced by the Resource Server.

**“Adding an IP check turns bearer into proof-of-possession.”** False. An IP address is not proof of key possession and can change or be shared.

**“Enabling JWT Resource Server automatically supports DPoP.”** False. Sender constraint requires both token issuance mechanics and corresponding proof verification.

## 15. Self-check questions

**Scenario A:** A JWT is unexpired, has a valid signature and valid scope, and is sent from an unfamiliar machine. The Resource Server uses standard JWT bearer authentication. Can the server automatically tell this is not the original machine?

> No. Without sender-constraining or additional controls, the token alone does not prove the original sending source.

**Scenario B:** An opaque token is introspected and the AS returns `active: true`. Does this guarantee the request can access every endpoint?

> No. The Resource Server must still check audience, scopes, and resource permission policies.

**Scenario C:** A token is copied into an access log, while the user's internet connection always uses HTTPS. Does replay risk still exist?

> Yes. The leak occurred at the logging system; HTTPS does not eliminate the ability to reuse an already exposed secret.

**Scenario D:** A token is bound to a DPoP key, and an attacker only obtains the access token string. How does the risk change?

> If the Resource Server properly enforces the binding mechanism, an attacker without the private key/valid proof generally cannot use the token merely by replaying the access token string.

## 16. References

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): defines bearer tokens, HTTP presentation methods, and token protection.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): guidance on preventing token leakage, replay, restricting audience/permissions, and sender-constrained tokens.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): binding access tokens to mTLS certificates.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): binding access tokens to key pairs and per-request proofs.
- [Spring Security — OAuth 2.0 Bearer Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): bearer token extraction locations and customizing the resolver.
- [Spring Security — JWT Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation and scope mapping.
- [Spring Security — Opaque Token Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection for access tokens.

The takeaway to keep in mind when designing a Resource Server: **a bearer token is a credential that can be reused if leaked**. Issuer, audience, scope, expiration, and data permission checks limit what a token can do; secret protection measures and sender constraints reduce the chance that someone else uses the token unintendedly.
