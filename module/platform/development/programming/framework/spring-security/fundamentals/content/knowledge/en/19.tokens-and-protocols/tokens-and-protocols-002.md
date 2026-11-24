# Access Tokens, Refresh Tokens, and Usage Lifecycle

In a system using OAuth 2.0, an application often needs to call APIs on behalf of a user or on behalf of the application itself. Instead of repeatedly sending the user's password to every API, the system can issue an **access token** to access resources and, if policy permits, a **refresh token** to obtain a new access token when the old access token expires.

These two token types have different responsibilities:

- **Access token**: a credential that the client presents to a **resource server** (API) to request access to authorized resources.
- **Refresh token**: a credential that the client presents to an **authorization server** at the **token endpoint** to obtain a new access token; a refresh token **must not be sent to resource APIs**.
- Whether a refresh token is issued is **up to the policy** of the authorization server; not every OAuth flow issues a refresh token.

This lesson explains the concepts, issuance and refresh mechanisms, lifetimes, revocation, and how Spring Security handles tokens. All token values in the examples are illustrative placeholder strings and cannot be used to log in to any real system.

## 1. Where Do Tokens Live in the System?

Common roles in OAuth 2.0:

| Role | Responsibility |
|---|---|
| **Resource owner** | Entity that owns/decides to grant access to a resource, typically a user |
| **Client** | Application that needs to access the API, e.g., web app, mobile app, backend service |
| **Authorization server** | Authenticates/authorizes via the appropriate flow, issues and manages tokens |
| **Resource server** | API that receives the access token and decides whether to accept the request |

Simple flow example:

```text
    User
        |
        | authenticates / authorizes via appropriate flow
        v
  Client (web/mobile/backend) <----> Authorization Server
        |                            issues access token
        |                            and optionally refresh token
        |
        | Authorization: Bearer <access_token>
        v
  Resource Server (API) ----> validates token + permissions ---> resource

  When access token can no longer be used:
  Client -- refresh_token --> Authorization Server
  Client <-- new access_token and optionally new refresh_token --
```

**The resource server does not need to know the client's refresh token.** The client only sends the access token to the corresponding API. In the authorization code flow, the authorization server typically issues tokens only after the client has exchanged the authorization code; for public clients such as SPAs/native apps, PKCE and appropriate safeguards are required. Logging in with a password does not automatically generate two tokens.

**OAuth 2.0 is primarily an authorization framework** and does not by itself define full user identity for application sign-in. If identity authentication under OpenID Connect (OIDC) is needed, the flow may additionally issue an **ID token**; an ID token serves a different purpose from an access token and must not be used in place of an access token to call APIs.

## 2. Comparing Access Tokens and Refresh Tokens

| Characteristic | Access Token | Refresh Token |
|---|---|---|
| Purpose | Proves permission to access an API within the granted scope | Obtains a new access token from the authorization server |
| Where used | Resource server permitted by the token | Token endpoint of the authorization server |
| Common transmission | `Authorization: Bearer ...` header | Request body with `grant_type=refresh_token` over TLS with client authentication when applicable |
| Lifetime | Usually short to limit damage if leaked | Usually longer than access token, but still requires an expiration/revocation policy |
| Content/format | May be JWT, opaque string, or another format | Typically an opaque string, though format is an implementation choice |
| Scope / audience | Must match the allowed resource and action | Bound to the grant, client, and granted scopes/resources |
| If compromised | Attackers can access the API until invalidated/expired, unless sender-constrained | Attackers can obtain new access tokens if they pass constraints; impact typically lasts longer |
| Mandatory? | Yes when the API requires an OAuth access token | No, the authorization server may decline to issue one |

A common lifetime choice is **an access token of a few minutes** and **a longer-lived refresh token**. This is a **policy example**, not a default mandated by the OAuth standard; actual lifetimes depend on risk level, client type, organizational policy, and protection/revocation mechanisms.

**An access token is not an account password**, but a **bearer token** behaves much like a temporary key: whoever holds a valid token can generally use it within the permissions the token allows. Therefore, tokens are also secrets that must be protected.

## 3. Full Lifecycle from Issuance to Expiration

The lifecycle can be divided into the following states:

1. **Unauthenticated / ungranted**: the client does not yet hold an appropriate token for the API.
2. **Authorization and issuance**: the authorization server confirms a valid grant, issues an access token, and may issue a refresh token.
3. **In use**: the client attaches the access token to API requests; the resource server checks validity, audience, scope/permissions, and applicable policies.
4. **Nearing expiration or expired**: the client decides to request a new token; if it holds a valid refresh token, it sends it to the token endpoint.
5. **Refresh**: the authorization server verifies the refresh token and client/grant constraints; if permitted, it issues a new access token and may simultaneously **rotate** the refresh token.
6. **Expired/revoked/invalid**: when refresh is not possible, the client must re-run an appropriate authorization or login flow; it must not retry a broken token indefinitely.
7. **Logout/grant revocation**: the client clears local credentials and coordinates token/grant revocation at the authorization server per system policy; the impact on existing access tokens must be considered.

Two important clocks are usually independent: **access token lifetime** and **refresh token lifetime/inactivity**. Do not treat an expired access token as meaning the user has been logged out; a refresh token can still obtain new access without forcing the user to re-enter credentials.

## 4. Receiving Tokens: Reading the Response Correctly

Example successful response from a token endpoint after a valid authorization flow:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "scope": "orders.read"
}
```

Values such as `EXAMPLE_...` are illustrative labels only, not usable tokens. `expires_in: 300` means the access token has a lifetime of **300 seconds from the time the response was issued, as defined by the server**. In a real system, the client should store an appropriate expiration timestamp and account for clock skew/network delay rather than mechanically comparing a bare number.

Field meanings:

- `access_token`: the credential value used to call APIs.
- `token_type`: how the token is used; a common value is `Bearer`.
- `expires_in`: number of seconds the token remains valid as stated by the authorization server.
- `refresh_token`: optional, present only when the authorization server issues one.
- `scope`: the granted permission scope; may be narrower than what the client requested.

**Note:** Not every response includes `refresh_token`, and access tokens do not have to be JWTs. If a system has multiple APIs, a token issued for a specific audience/resource must only be sent to that permitted resource.

## 5. Calling an API with an Access Token

Example client request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

The resource server must not trust a request merely because the header contains `Bearer`. It must verify that the token comes from the right issuer/trusted source, is still active, is intended for this API, satisfies required permissions, and has not been revoked if the system supports revocation checking.

Possible response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

When a request lacks a token or the token is invalid/expired, the API typically returns **401**. If the token is valid but lacks the permission needed for the resource, the API typically returns **403**; depending on the implementation, it may include `WWW-Authenticate: Bearer error="insufficient_scope"`. These error examples describe common cases and do not guarantee every framework returns the exact same response body.

**Do not send access tokens in URL query parameters** when headers can be used; query strings easily leak into logs, browser history, proxies, and analytics. Use HTTPS with proper certificate verification and avoid exposing the `Authorization` header in telemetry.

### Does an Active Token Mean Sufficient Permissions?

No. Two steps must be separated:

1. **Authentication/token validation**: the token is an accepted credential under system rules.
2. **Authorization**: the token and associated principal have permission to perform the specific operation.

For example, an access token with only `orders.read` can call `GET /api/orders`, but is not automatically allowed to call `DELETE /api/orders/42`. The resource server needs permission checks and resource-level access control, not just verifying that the token has a valid signature.

## 6. JWT and Opaque Tokens: Format Is Not Role

A **JWT access token** typically consists of three Base64URL-encoded parts `header.payload.signature`. When using a signed JWT (JWS), the resource server can verify the signature and claims such as:

- `iss` (issuer): the issuing party.
- `sub` (subject): the subject the token refers to; not automatically synonymous with permissions across every API.
- `aud` (audience): the resource/recipient the token is intended for.
- `exp` (expiration): expiration timestamp.
- `nbf` (not before): timestamp when validity begins, if present.
- `scope` / `scp`: granted permissions according to the authorization server's convention.

A signed JWT **is not a confidentially encrypted JWT**: the payload of a typical signed JWT can be decoded by anyone who receives the token. Therefore, do not put passwords or unnecessary sensitive data in claims, and do not merely `decode` and trust the contents. You must **verify the signature, allowed algorithm, issuer/audience, timestamps, and permissions**.

An **opaque access token** is a string carrying no useful public structure for the API. The resource server typically needs a lookup/introspection mechanism or integration with a verification service to determine whether the token is valid and what scopes it holds. Do not infer that an opaque token is more secure than a JWT just because its contents cannot be read; both are credentials that must be protected.

**A refresh token can have any format**, but the client should not read or decode it to infer permissions or lifetime. Treat it as an opaque secret string and follow the response and policy from the authorization server.

## 7. How Do Refresh Tokens Work?

When an access token is about to expire or is no longer accepted due to expiration, the client can request a new token if it was issued a refresh token. Example OAuth 2.0 request:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

`/oauth2/token` is an illustrative path; the real endpoint is published/configured by the authorization server. **Confidential clients** also typically have to authenticate at the token endpoint, for instance via an agreed client authentication mechanism; any `Authorization` header used for client authentication **is not** an HTTP Bearer access token sent to an API. Public clients cannot keep a client secret confidential like a backend can, so they must use appropriate refresh token protections.

The authorization server checks at least these essentials depending on client type and grant policy:

1. The refresh token was issued by this server, is still valid, and has not been revoked.
2. The token belongs to the right client/grant and satisfies authentication constraints or proof-of-possession when applicable.
3. Requested scopes/resources do not exceed what the owner granted.
4. There are no signs of replay/suspicious activity or other policy conditions requiring rejection.

If valid, the response may look like:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "EXAMPLE_ACCESS_TOKEN_2",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_2",
  "scope": "orders.read"
}
```

When the server issues a **new refresh token** under a rotation policy, the client must store the new token securely and **stop using the old token**. A response may also omit a new refresh token in systems with other policies; do not assume every refresh always performs rotation.

**Never send a refresh token in `Authorization: Bearer` when calling a resource server.** When an access token expires, use the refresh token with the **authorization server**—do not send both tokens to the API to "try which token works".

## 8. Timing Example: Two Different Lifecycles

Suppose an application is issued:

- Access token `A1` with a lifetime of **5 minutes**.
- Refresh token `R1` with an expiration policy of **7 days**; may be shorter due to inactivity, revocation, or risk.
- The authorization server enables **refresh token rotation**.

Hypothetical sequence:

| Time | Event | Outcome |
|---|---|---|
| 10:00 | `A1` and `R1` are issued | Client calls API using `A1` |
| 10:04 | Valid API call with sufficient permissions | `A1` is still usable within lifetime and policy |
| 10:05 | `A1` expires | API rejects `A1` if no longer valid; `R1` may still be usable |
| 10:06 | Client sends `R1` to token endpoint | If valid, server issues `A2` and `R2`, invalidating `R1` |
| 10:07 | Client calls API using `A2` | Succeeds if `A2` is valid and has sufficient permissions |
| 10:08 | Old `R1` is re-sent | Rejected; under replay detection policy, the session/grant may be further revoked |

This is an illustrative policy; TTLs are **not mandatory standards**. Under rotation, invalidating `R1` **does not automatically invalidate `A1`** if the old access token is still within its validity window and the system has no corresponding access token revocation mechanism. Receiving `A2` also does not automatically grant more permissions than the original grant.

Clients can refresh **before** the access token expires to avoid failed requests, such as when a few dozen seconds remain. Do not rely on "it is minute five" while ignoring clock skew, network delay, early token revocation, or `nbf`/custom policies.

## 9. Refresh Token Rotation and Preventing Reuse of Stolen Tokens

Refresh tokens usually live longer and therefore carry high value for attackers. An important safeguard is **rotation**:

```text
Initial grant:      Access A1  + Refresh R1
Refresh with R1:    Access A2  + Refresh R2  (R1 invalidated)
Refresh with R2:    Access A3  + Refresh R3  (R2 invalidated)
Reuse of R1/R2:     Detected or rejected per server policy
```

The authorization server tracks or derives relationships between tokens belonging to the same grant/family to detect reuse of a rotated token. If `R1` is stolen, when both the attacker and the legitimate client attempt to use it, at least one party will present an already-invalidated token. The server can detect a potential leak and revoke active refresh tokens in the family. It **does not inherently know for certain which party is the attacker**.

According to **RFC 9700 (OAuth 2.0 Security Best Current Practice)**, if issuing refresh tokens to **public clients**, the authorization server must use **refresh token rotation or sender-constrained refresh tokens** to detect replay. Sender-constrained tokens bind usage to cryptographic proof from the client, such as DPoP or mTLS in supported models.

**Do not assume rotation eliminates all risk:** If an attacker steals the latest refresh token and uses it first, they can still obtain a new access token until the system detects/revokes it. You still need HTTPS, secure secret storage, minimal scopes, expiration/inactivity policies, anomaly detection, and handling for lost devices or password changes.

### Avoiding Concurrent Refreshes Mistaken for Replay

Multiple tabs or multiple HTTP requests detecting `A1` expiration at the same time can send `R1` **twice almost simultaneously**. If the server uses one-time rotation, one request succeeds and receives `R2`, while the other reuses `R1` and may be rejected or trigger reuse detection.

In the client, use a **single-flight / synchronized refresh** mechanism per session or device: multiple requests wait for the result of one in-flight refresh, then all receive the new access token. Across multiple browser tabs, an architecture-appropriate mechanism is needed to coordinate token updates safely; do not disable server-side reuse detection just to "fix" a race condition.

If a refresh fails with an error like `invalid_grant`, do not retry the same refresh token in an infinite loop. Clear the invalid token state, distinguish transient network errors from a revoked grant, and initiate a new authorization flow when needed.

## 10. Do Expiration, Revocation, and Logout Differ?

**Expiration**: A token exceeds its validity period or policy window. JWTs may carry `exp`; opaque tokens are typically checked against server-side metadata. A token can be rejected **before its expiration time** due to revocation, policy changes, audience mismatch, or sender-binding mismatch.

**Revocation**: The authorization server actively invalidates a token/grant upon request or security event. OAuth 2.0 Token Revocation (RFC 7009) defines an endpoint for clients to request revocation; revoking a refresh token may affect related tokens depending on server policy and capabilities.

**Logout**: The application ends the client-side session and, when appropriate, performs logout/revocation at the authorization server or identity provider. Deleting a token from client memory only stops **that client** from sending the token in the future; it does not automatically invalidate a leaked access token elsewhere.

In the case of **self-contained JWT access tokens**: a resource server that only verifies signatures/claims locally can continue accepting an issued token until it expires if there is no revocation-status check, denylist, or equivalent mechanism. Thus, the claim "logout immediately invalidates all access tokens" is only true when the architecture actually supports it.

If near-instant revocation is required, consider opaque tokens + introspection/server-side state, revocation checks, short access token lifetimes, or other solutions. Each option involves trade-offs in latency, availability, and state management.

### Distinguishing from Session Cookies

A session cookie typically carries a Session ID for the server to look up session state; a refresh token is a credential used to **request a new access token**. A web application can use the Backend-for-Frontend (BFF) pattern, keeping tokens on the server and giving the browser a secure session cookie. In that case, the browser does not directly hold the refresh token even though the system still uses OAuth 2.0 underneath. Do not equate logging out a session cookie with revoking all OAuth tokens at the authorization server.

## 11. Spring Security Application: Resource Server Verifying Access Tokens

In **Spring Security Servlet**, an API configured as an **OAuth2 Resource Server** can accept a Bearer access token in the header and verify a JWT or opaque token according to the chosen mechanism.

Example **configuration in a Spring Boot project with appropriate Resource Server/JWT dependencies**, against a real issuer supporting metadata/JWKS:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/issuer
```

Java code configuring an endpoint requiring scope `orders.read` (this snippet belongs to a **Spring Boot/Spring Security project**, not a standalone Java program):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

With standard JWT configuration, Spring Security Resource Server verifies the signature and checks time claims such as `exp` and `nbf`, as well as matching `iss` when an issuer is configured. Scopes are typically converted into authorities prefixed with `SCOPE_`. **Audience (`aud`) validation must be ensured via appropriate configuration/validators** if the API requires a specific audience; do not assume every default configuration automatically checks every field required by enterprise policy.

The sample code intentionally illustrates only a **resource server consuming access tokens**. It **does not issue access tokens or refresh tokens**, does not create a token endpoint, and does not implement rotation. Those responsibilities belong to the authorization server. If a Spring Security application acts as an **OAuth2 Client**, it can manage `OAuth2AuthorizedClient` and refresh tokens via the appropriate Client/`AuthorizedClientManager` mechanism depending on configuration; you should not build a custom refresh endpoint inside a resource server unless the architecture truly requires it and roles are clearly defined.

If the resource server is configured to validate opaque tokens, the mechanism is typically introspection against the authorization server rather than local signed-JWT verification. Choose accurately according to the **access token format issued by the issuer**.

## 12. Simulating Lifetimes in Java 17

The following standalone Java example helps observe why an access token can expire while a refresh token still has remaining lifetime. It **only simulates timestamps and renames token strings**; it does not create, identify, or verify real credentials, and any hardcoded tokens in this lesson are unsafe for production applications.

Create the file `TokenLifecycleDemo.java`:

```java
import java.time.Instant;

public class TokenLifecycleDemo {
    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T10:00:00Z");
        Instant accessExpiresAt = issuedAt.plusSeconds(5 * 60);
        Instant refreshExpiresAt = issuedAt.plusSeconds(7 * 24 * 60 * 60);
        Instant now = issuedAt.plusSeconds(6 * 60);

        String oldRefresh = "refresh-v1";
        String currentRefresh = oldRefresh;

        boolean accessExpired = !now.isBefore(accessExpiresAt);
        boolean refreshWithinTime = now.isBefore(refreshExpiresAt);

        System.out.println("Access expired: " + accessExpired);
        System.out.println("Refresh within lifetime: " + refreshWithinTime);

        if (accessExpired && refreshWithinTime
                && currentRefresh.equals(oldRefresh)) {
            String newAccess = "access-v2";
            currentRefresh = "refresh-v2";
            System.out.println("New access: " + newAccess);
            System.out.println(
                    "Old refresh still current: "
                    + currentRefresh.equals(oldRefresh));
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac TokenLifecycleDemo.java
java TokenLifecycleDemo
```

Exact output:

```text
Access expired: true
Refresh within lifetime: true
New access: access-v2
Old refresh still current: false
```

At the sixth minute, the simulated access token has expired (five-minute TTL), whereas the refresh token has a seven-day TTL and is therefore still **within its time limit**. However, in a real system, **remaining time alone does not prove a refresh token is valid**: the authorization server must also check client binding, signature/ID/state, rotation, scope, revocation, and security policies. Do not use the string comparison logic in this example as a real validation algorithm.

## 13. Protecting and Storing Tokens by Client Type

Token protection requires evaluating storage, transport, and blast radius if stolen:

| Environment | Appropriate Approach to Evaluate | Notes |
|---|---|---|
| **Backend/confidential client** | Store tokens in a controlled server-side system, secret store/protected vault, with restricted access permissions | Do not log tokens, encrypt/protect stored data, protect client secrets |
| **Web app using BFF** | Browser holds a session cookie with appropriate `HttpOnly`, `Secure`, `SameSite`; BFF holds OAuth tokens server-side | Cookies still carry CSRF risk because browsers send them automatically; implement appropriate CSRF defenses |
| **Pure browser-based SPA** | Avoid exposing long-lived tokens to JavaScript when possible; consider access tokens in memory and safe session re-issuance/refresh design | XSS can steal tokens or call APIs; `localStorage` provides no barrier against XSS scripts |
| **Native/mobile app** | Use OS secret storage where appropriate, authorization code + PKCE, device management, and revocation | A compromised device can still expose credentials |
| **Resource server/API** | Accept and verify only access tokens intended for itself; avoid logging or forwarding tokens unnecessarily to other services | Do not ask for the client's refresh token to access an API |

There is no "100% secure" storage location. Choose a design matching your threat model; for tokens in cookies, the `HttpOnly` attribute only prevents JavaScript from reading the cookie via normal APIs—it does not stop scripts from triggering requests to which the browser automatically attaches the cookie, and does not replace CSRF/XSS protections.

General principles:

1. **HTTPS/TLS** for every token-exchange endpoint, including the token endpoint, APIs, introspection/revocation, and network segments needing protection.
2. **Short lifetimes, minimal scopes/audiences** for access tokens. Actual authorization is enforced by the API.
3. **Refresh token rotation or sender-constraining** as required when issuing refresh tokens to public clients; manage inactivity timeouts and revocation.
4. **Never log tokens/secrets** in URLs, request/response dumps, analytics, stack traces, or error screenshots. Fully redact sensitive values before sharing.
5. **Do not generate tokens with predictable strings** or roll your own signing algorithms. Use a proven authorization server and security library.
6. **Do not use ID tokens instead of access tokens** for APIs, and do not send refresh tokens to resource servers.
7. **Prevent refresh race conditions** and properly handle errors, logout, or remotely invalidated sessions.

## 14. Real-World Errors and How to Handle Them

| Symptom | Possible Cause | Proper Resolution |
|---|---|---|
| API returns `401 invalid_token` | Expired access token, wrong issuer, invalid signature, wrong audience, or revoked | Inspect error details, verify issuer/audience configuration; refresh only when conditions warrant |
| API returns `403` | Token is valid but lacks scope/role or object-level permission | Review authorization policy; do not try to "bypass" it by refreshing repeatedly |
| Token endpoint returns `invalid_grant` | Refresh token expired, already used/rotated, revoked, or not part of a valid grant | Stop using the broken token, clear old state, request a new grant via the standard flow |
| Multiple requests refresh simultaneously | May reuse the same old token and trigger reuse detection | Coalesce refresh requests and update tokens atomically per architecture |
| Refresh succeeds but requests still return 401 | Client still sends old access token, new token has wrong audience/scope, or server enforces another policy | Ensure the newly received token is applied, inspect the request and validators |
| Old token still calls API after logout | Client only deleted local token, old JWT is still valid, and API lacks revocation check | Evaluate revocation mechanisms, shorter lifetimes, introspection/denylist as needed |
| Token leaked via logs | Gateway, tracing, or debug logging printed `Authorization` | Mask/strip tokens from logs, revoke affected tokens, and investigate root cause |

**Note:** Refreshing is not a cure-all for every `401`; a token may have the wrong issuer, wrong audience, or already be revoked. On repeated authentication errors, the client must stop infinite automatic retry loops and transition to re-authentication handling.

## 15. Self-Check Questions

1. **Are access tokens and refresh tokens sent to the same API?** No. Access tokens go to the resource server; refresh tokens go only to the authorization server to obtain a new access token.
2. **Does access token expiration always force the user to log in again?** No; if a valid refresh token exists and policy permits, the client can obtain a new access token.
3. **Are refresh tokens mandatory in OAuth 2.0?** No; the authorization server decides whether to issue one.
4. **If a token is a JWT, can you trust the payload after Base64URL decoding?** No; you must verify the signature and applicable claims/constraints.
5. **Does every refresh response issue a new refresh token?** No. Rotation is a policy; when issuing refresh tokens to public clients, RFC 9700 requires rotation or sender-constraining to detect replay.
6. **Does client logout immediately revoke all JWT access tokens?** Not by default. It requires a revocation policy and a suitable verification mechanism on the resource server.
7. **Can an unexpired access token lacking `orders.write` modify an order?** Not if the API enforces authorization properly.
8. **How dangerous is a leaked refresh token?** It can allow obtaining new access tokens, prolonging unauthorized access if protections and reuse detection are absent.

**Remember:** **Access tokens are for calling APIs, refresh tokens are for obtaining new access tokens, and both must be bounded in lifetime, scope, and revocability.** Protecting the token lifecycle is a coordinated effort across the authorization server, client, resource server, and security operations—not just checking the `exp` field.

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): roles, refresh tokens, issuance and refreshing of access tokens.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sending access tokens as Bearer and authentication errors.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, sender-constraining, replay prevention, and modern recommendations.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation mechanism.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): validating tokens via introspection.
- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): configuring JWT access token verification in Spring Security.
