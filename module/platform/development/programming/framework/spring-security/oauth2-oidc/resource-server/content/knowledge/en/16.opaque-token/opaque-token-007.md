# The `active` attribute and handling invalidated tokens

When a **Spring Security OAuth 2.0 Resource Server** receives an **opaque Bearer Access Token**, it generally cannot verify signatures, expiration, or permissions locally by reading the token string. The Resource Server sends the token to the Authorization Server's **token introspection endpoint** to query its status and metadata. Under **RFC 7662**, the introspection response includes a boolean **`active`** field.

This is a critical boundary: **`active: false` requires the Resource Server to reject the token**, while **`active: true` only allows proceeding to check API permissions and policy conditions**. If the introspection endpoint errors, times out, or returns malformed JSON, the system **must never assume the token is still active**.

This lesson explains the exact meaning of `active`, reasons a token becomes inactive, Spring Security's `OpaqueTokenIntrospector` mechanism, handling 401/403, infrastructure failures, caching and revocation, along with configuration and test examples. Examples use **Spring Boot 3.x, Spring Security 6.x, and Java 17+** with a Servlet Resource Server accepting OAuth 2.0 Access Tokens.

## 1. Why do opaque tokens require introspection?

An OAuth 2.0 Access Token is a credential a client uses to call a Resource Server. The Authorization Server may issue either JWT Access Tokens or opaque Access Tokens.

| Criterion | Locally verified JWT | Opaque token |
| --- | --- | --- |
| Format the API relies on | JOSE header, JWT claims, signature. | API does not rely on the token string's structure. |
| Where validity is checked | `JwtDecoder` and JWK public keys. | `OpaqueTokenIntrospector` and Authorization Server. |
| Permission source | Verified JWT claims. | Trusted introspection metadata. |
| Revocation before expiration | Requires extra mechanisms such as denylists or short-lived tokens. | Introspection can reflect revocation status. |
| Network dependency per verification | Usually none, once appropriate keys are obtained. | Usually present, unless cached per policy. |
| `active` | Not a mandatory standard JWT claim. | Core field in an RFC 7662 response. |

An opaque token might look like:

~~~text
v2_at_R7FkS_xxxxxx
~~~

That is purely an **illustrative string**, not a real token. The Resource Server **must not** extract usernames from prefixes, Base64-decode it to guess scopes, or treat a token as valid because it matches an expected length. "Opaque" describes how the Resource Server uses the token; it does not necessarily assert that the Authorization Server stores tokens in a particular internal structure. An Authorization Server can even support introspecting JWTs.

Request from the client:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer OPAQUE_ACCESS_TOKEN_VALUE
Accept: application/json
~~~

The token in the header is a **Bearer credential**: anyone holding it can attempt to exercise its granted permissions, unless a sender-constraint mechanism is in place. Never place tokens in URLs, logs, exceptions, or public documentation.

## 2. How does RFC 7662 define `active`?

**RFC 7662 — OAuth 2.0 Token Introspection** lets a Resource Server query the Authorization Server to learn whether a token is **currently active** and retrieve metadata permitted to be disclosed to the introspecting party.

Overall flow:

~~~text
Client
  |
  | Authorization: Bearer <opaque token>
  v
Resource Server (Spring Security)
  |
  | POST /oauth2/introspect
  | token=<opaque token>
  | Authenticate the Resource Server itself to the Authorization Server
  v
Authorization Server
  |
  +-- Identify token / grant / state
  +-- Check expiration and revocation per policy
  +-- Check Resource Server's introspection permission
  |
  +-- {"active":false} -> Do not accept credential
  |
  +-- {"active":true,...} -> Permitted metadata
  v
Resource Server
  |
  +-- Establish principal and authorities
  +-- Check audience/resource, scope, and domain policy
  v
API controller / service
~~~

### 2.1. Sending the introspection POST

Example HTTP request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_RESOURCE_SERVER_CREDENTIALS
Accept: application/json

token=OPAQUE_ACCESS_TOKEN_VALUE&token_type_hint=access_token
~~~

The two credentials serve different functions:

- **Access Token** is the token sent by the client to the API, placed in the `token` form parameter when the Resource Server introspects.
- **Resource Server client credential** proves the caller invoking the introspection endpoint is authorized to query it. The example uses HTTP Basic; the Authorization Server may require mTLS or another method.

`token_type_hint=access_token` is an optional hint helping the server locate the token efficiently, **not authentication proof**. Introspection must happen over **HTTPS** with certificate and hostname verification; never log bodies containing tokens or Basic credentials.

### 2.2. `active=true` response

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "orders-web-client",
  "token_type": "Bearer",
  "sub": "person-123",
  "iss": "https://login.example.test/realms/demo",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

`active: true` indicates the Authorization Server considers the token active in the introspection context. Other fields like `scope`, `sub`, `iss`, `aud`, `exp`, and `client_id` depend on the token and the Authorization Server's contract; never assume every server returns all of them.

Even when `active:true`, the API must still verify:

- Was the token issued for **the right API resource/audience**?
- Does it carry the required scope/authority for the endpoint?
- Does it satisfy policies on token type, issuer/client, and mandatory claims?
- If the operation involves a user, is the local account still active and permitted to act?
- Does the caller have permission on the requested record/tenant?

**`active` is a necessary condition in the introspection mechanism, not the entirety of authorization.**

### 2.3. `active=false` response

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

**An HTTP 200 from introspection does not mean the Access Token is valid.** It only means the server successfully processed the introspection request. The `active` attribute determines whether token authentication may continue.

RFC 7662 requires that inactive tokens or tokens the caller is not permitted to introspect be represented by `active:false` without returning extra metadata. Withholding the reason helps prevent probing whether a token exists, is still valid, or was revoked.

The Resource Server must stop authentication upon receiving `active:false`; **never fabricate a principal, never grant default authorities**, and never fall back to reading scopes from unverified token data.

## 3. Data type of `active`: JSON boolean only

`active` is a **mandatory boolean** in a successful RFC 7662 introspection response.

| Returned JSON | Valid `active` type? | Action |
| --- | --- | --- |
| `{"active":true}` | Yes. | May proceed to metadata and permission checks. |
| `{"active":false}` | Yes. | **Reject token**. |
| `{"active":"true"}` | No: string. | Reject; report contract/protocol error. |
| `{"active":"false"}` | No: string. | Reject. |
| `{"active":1}` | No: number. | Reject. |
| `{"active":0}` | No: number. | Reject. |
| `{"active":null}` | No. | Reject. |
| `{}` | No: missing required field. | Reject. |
| `{"active":[]}` | No. | Reject. |
| Empty body / malformed JSON | No. | Reject, record protocol error. |

If parsing JSON manually, never use ambiguous coercion:

~~~java
// DO NOT DO THIS: can mask JSON type mismatches.
boolean active = Boolean.parseBoolean(
    String.valueOf(response.get("active")));
~~~

Given a `Map<String,Object>` parsed by a trusted JSON parser, treat `active` as true only when the value is strictly `Boolean.TRUE`. If the value is null, a string, or a number, reject it as an invalid introspection response.

A standard **`OpaqueTokenIntrospector`** enforces the `active` condition during authentication. If implementing a custom introspector, preserve those semantics; never create a principal from a response lacking a proper boolean `active`.

## 4. `active=false` can have many causes

Never assume every `active:false` means the token expired.

### 4.1. Expired token

Example:

~~~text
10:00  Authorization Server issues token
10:05  introspection -> active=true
10:15  token expires per expiration policy
10:16  introspection -> active=false
~~~

If introspection returns `exp`, per RFC 7662 this value is a NumericDate (Unix epoch seconds). Never treat milliseconds as seconds or accept arbitrary strings as valid expiration if the contract requires a JSON number.

### 4.2. Revoked token

Under **RFC 7009 — Token Revocation**, an Authorization Server may support revoking tokens:

~~~text
T0: Access Token active
T1: Client or administrator requests revocation of token/grant
T2: Authorization Server records revocation
T3: New introspection -> active=false
~~~

**T3 does not necessarily take effect across every Resource Server instantaneously** if `active:true` results are cached, replicated across nodes, or have state propagation lag. Whether revoking a Refresh Token/grant also revokes Access Tokens depends on the Authorization Server's policy and implementation.

### 4.3. Token does not exist or does not belong to this server

A user-fabricated string must never be accepted just because it resembles an opaque token format. The Authorization Server can return `active:false` if it does not recognize the token. Never return detailed responses distinguishing "token X not found" from "token X was revoked," as that difference can become a token-probing oracle.

### 4.4. Token not yet valid

A token with `nbf` in the future or blocked by grant/session conditions may be considered inactive by the Authorization Server under policy. The Resource Server must never alter `nbf` to make a token appear valid.

### 4.5. Resource Server is not permitted to introspect the token

RFC 7662 permits returning `active:false` when the caller **is not authorized to learn details of a specific token**. Thus, a token may still be valid in another context yet be rejected by the current Resource Server.

This also means **you cannot deduce the exact cause solely from `active:false`**. The conclusion the API needs is "do not accept this credential here."

### 4.6. Local account status is an independent layer

Suppose the Authorization Server returns `active:true` while the internal account is suspended:

~~~text
Introspection: active=true
app_user.status: SUSPENDED
Resource permission: denied
~~~

In that case, the token may be valid at the OAuth layer yet **must be denied at domain authorization**. Never treat `active=true` as proof that the user still has rights across every tenant or every order.

## 5. HTTP 200 `active=false` differs from introspection 401/503 errors

Distinguish:

1. **Client → Resource Server:** a Bearer request can receive 401 if the token is invalid.
2. **Resource Server → Authorization Server:** an introspection request can receive 401 if the introspection credential is rejected.
3. **Authorization Server → Resource Server:** HTTP 200 + JSON `active:false` reports that the token status is unacceptable.

| Upstream response | Meaning | How Resource Server handles it |
| --- | --- | --- |
| HTTP 200, `active:true` | Token is active. | Proceed with metadata/policy checks. |
| HTTP 200, `active:false` | Token is not accepted. | **Authentication fails**; protected endpoints typically return 401. |
| HTTP 200, missing `active` | Non-RFC response. | Reject token; classify as protocol error. |
| HTTP 401 at introspection | **Resource Server** credential invalid, or rejected upstream. | Do not authenticate token; investigate client authentication. |
| HTTP 403 at introspection | Caller not permitted or upstream policy denied. | Do not authenticate token; classify integration/policy issue. |
| HTTP 429/503/5xx | Upstream overloaded or failing. | **Fail closed**, never treat token as active. |
| Timeout/DNS/TLS failure | Cannot query status. | Fail closed, handle network error; do not interpret as business `active=false`. |

**Never conflate "inactive token" with "introspection service unavailable" in logs/metrics.** If every error logs "expired token," operations teams will struggle to spot an invalid client secret or an identity system outage.

When upstream fails, the Resource Server's HTTP response depends on the framework, handler, and API contract; you might return **503 Service Unavailable** to signal an authentication dependency outage, yet must never convert an error into an authenticated request. Do not assert that all introspection errors must map uniformly to 401 or 503.

## 6. Which Spring Security components process opaque tokens?

Typical Servlet flow:

~~~text
Authorization: Bearer <opaque token>
                |
                v
BearerTokenAuthenticationFilter
                |
                v
BearerTokenAuthenticationToken
                |
                v
OpaqueTokenAuthenticationProvider
                |
                v
OpaqueTokenIntrospector.introspect(token)
                |
                +-- active=false -> authentication fails
                |
                +-- invalid response / upstream error
                |   -> no successful Authentication created
                |
                +-- active=true -> OAuth2AuthenticatedPrincipal
                                     |
                                     v
                              BearerTokenAuthentication
                                     |
                                     v
                              GrantedAuthorities (SCOPE_...)
                                     |
                                     v
                              AuthorizationFilter
                                     |
                                     v
                              Controller / Service policy
~~~

`OpaqueTokenIntrospector` is the interface that performs introspection and returns **`OAuth2AuthenticatedPrincipal`** when the token is valid. When the response is inactive, the standard introspector rejects the token rather than returning a principal.

**An opaque token's principal is not a `Jwt`.** With a JWT Resource Server, `Authentication` is usually `JwtAuthenticationToken`; with opaque tokens, it is typically `BearerTokenAuthentication` containing an `OAuth2AuthenticatedPrincipal`. Avoid casting `@AuthenticationPrincipal Jwt` in APIs that only use opaque introspection.

### 6.1. Mapping scopes to authorities

If the response returns:

~~~json
{"active":true,"scope":"orders.read orders.write","sub":"person-123"}
~~~

Spring Security typically builds:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Example:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

**`active=true` does not automatically grant any scopes.** If a token is active yet lacks the required authority, the request is authenticated yet may receive **403 Forbidden**.

## 7. Configuring a Spring Boot Opaque Token Resource Server

### 7.1. Dependencies

Gradle example (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 7.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Values:

- **`introspection-uri`**: HTTPS endpoint published by the Authorization Server.
- **`client-id`**: Resource Server identity authorized to introspect.
- **`client-secret`**: credential authenticating the Resource Server to the introspection endpoint, read from environment/secret manager.

Never hardcode real client secrets in repositories or public examples. If the Authorization Server uses mTLS or a client authentication method other than Basic, configure the introspector/HTTP client accordingly; do not assume every endpoint supports the same mechanism.

### 7.3. `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This example applies the chain only to `/api/**`. An application that also has web/management endpoints must define other chains or an appropriate fallback so no path is left unprotected. `STATELESS` and disabling CSRF suit pure Bearer-header APIs; **do not reuse this verbatim for an OIDC Login website authenticating with session cookies**.

### 7.4. Accessing `OAuth2AuthenticatedPrincipal`

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrincipalController {

    @GetMapping("/api/orders/me")
    Map<String, String> current(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("principalName", principal.getName());
    }
}
~~~

This controller only demonstrates reading the principal, not a production endpoint that should arbitrarily expose identity data. When an API uses local users or tenant memberships, perform domain mapping and authorization rather than merely returning attributes received from introspection.

## 8. From `active=false` to HTTP 401

A request with a revoked token:

~~~text
Client                       Resource Server             Authorization Server
  |                                 |                            |
  | GET /api/orders/42              |                            |
  | Bearer revoked-token            |                            |
  |-------------------------------->|                            |
  |                                 | POST introspect            |
  |                                 |--------------------------->|
  |                                 |                            |
  |                                 | 200 {"active":false}       |
  |                                 |<---------------------------|
  |                                 |                            |
  | 401 Unauthorized                |                            |
  |<--------------------------------|                            |
~~~

A Resource Server response might look like:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{"code":"invalid_token","message":"Unable to authenticate request."}
~~~

Details in `WWW-Authenticate` and the body vary by exception handler and Spring Security version; not every 401 matches the exact example above. Never disclose the token, `sub`, internal revocation reasons, or stack traces to clients.

### 8.1. Comparing 401 and 403

| Status | Authentication | Authorization | Typical HTTP code |
| --- | --- | --- | --- |
| Missing Bearer token on protected endpoint | Failed | Not evaluated | **401** |
| Introspection `active:false` | Failed | Not evaluated | **401** |
| Introspection `active:true`, missing scope | Succeeded | Failed | **403** |
| Introspection active, right scope, order belongs to another user | Succeeded | Failed | **403/404** per domain policy |
| Introspection active, all conditions met | Succeeded | Succeeded | **2xx** per controller |
| Introspection timeout/503 | Unverifiable | Not permitted | **Fail closed**, may return 5xx/503 per API contract |

With OAuth 2.0 Bearer Tokens, 401 errors relate to credentials; 403 errors usually relate to permissions of an already-authenticated caller. Never use `active:false` as a catch-all representation for authorization errors.

## 9. `active=true` can still be insufficient for the API

### 9.1. Wrong audience/resource

Introspection may return:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "billing.read",
  "sub": "person-123"
}
~~~

The token is active yet issued for **`billing-api`**. **`orders-api`** must not accept the token just because it is active. Check `aud`, resource indicators, or introspection/resource-binding policies per the Authorization Server contract.

If the issuer does not return the needed field, **do not silently drop the check**. Agree on metadata or a Resource Server binding mechanism at the Authorization Server.

### 9.2. Missing scope

~~~json
{"active":true,"sub":"person-123"}
~~~

If the API requires `orders.read`, a token lacking that scope must not automatically receive `SCOPE_orders.read`. Depending on the token contract, a token without scopes may still be valid yet **lack sufficient privileges**.

### 9.3. Token does not match the token profile

An OIDC **ID Token** is intended for the OIDC Client/Relying Party and is not by default an OAuth 2.0 Access Token for a Resource Server. A token legitimately issued in the identity system but used for the wrong type/purpose must still be rejected by token profile policy.

### 9.4. Local user is suspended

~~~text
Opaque token: active=true
Local account: SUSPENDED
User attempts to view another tenant's order
~~~

The API must apply independent **domain authorization**: account status, tenant membership, ownership, and allowed actions. An active token does not make a user the owner of every record.

## 10. Custom `OpaqueTokenIntrospector`: preserve `active` checks

When you need to validate audience or custom metadata, the safe approach is **wrapping a standard introspector**, never building principals from the token string itself.

### 10.1. Never grant privileges without introspecting

The following is a security bug:

~~~java
// DO NOT DO THIS: turns any string into a high-privilege principal.
@Bean
OpaqueTokenIntrospector insecureIntrospector() {
    return token -> new DefaultOAuth2AuthenticatedPrincipal(
        "unknown",
        Map.of("sub", token),
        List.of(new SimpleGrantedAuthority("SCOPE_admin.manage")));
}
~~~

If deployed to production, any Bearer token would be accepted as valid with administrative privileges.

### 10.2. Wrapping the introspector to check audience

The following example uses `NimbusOpaqueTokenIntrospector` available in Spring Security 6.x. APIs for constructing/configuring the HTTP client can vary across minor versions, so pick the constructor supported by your project version.

~~~java
import java.util.Collection;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.oauth.introspection-uri}") String endpoint,
            @Value("${app.oauth.introspection-client-id}") String id,
            @Value("${app.oauth.introspection-client-secret}") String secret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(endpoint, id, secret);

        return token -> {
            // Delegate already verifies active before returning principal.
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            if (!hasAudience(
                    principal.getAttribute("aud"), "orders-api")) {
                throw new BadOpaqueTokenException(
                    "Token is not intended for this API");
            }

            return principal;
        };
    }

    private static boolean hasAudience(Object raw, String expected) {
        if (raw instanceof String value) {
            return expected.equals(value);
        }
        if (raw instanceof Collection<?> values) {
            return values.stream().anyMatch(
                item -> Objects.equals(expected, item));
        }
        return false;
    }
}
~~~

Matching configuration:

~~~yaml
app:
  oauth:
    introspection-uri: https://login.example.test/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Key points to remember:

- The standard delegate checks **`active`**. If inactive, `introspect` does not return a successful principal.
- The decorator merely adds **audience policy**, rejecting when `aud` is wrong or missing.
- Never catch errors from the delegate and return a default principal. When upstream is unavailable, **fail closed**.
- A custom `OpaqueTokenIntrospector` bean typically replaces Boot's auto-configuration, so ensure **the right endpoint and credentials** are passed to the bean actually in use.
- This example targets a contract where `aud` is a string or collection. If your Authorization Server differs, enforce the matching policy rather than coercing types arbitrarily.

When customizing an introspector, avoid altering `active` metadata to application-invented values. If you need custom user status checks, enforce them in account/domain policy rather than rewriting the RFC 7662 response.

## 11. Caching and its impact on token revocation

Introspection lets the Resource Server know token status close to request time, yet **caching active results** can allow a revoked token to remain usable for a short period.

### 11.1. Example timeline

~~~text
10:00:00  Resource Server introspects token-A -> active=true
          Cache active result for 60 seconds

10:00:20  Authorization Server revokes token-A

10:00:30  Client sends token-A
          Cache still reports active=true
          -> request may be processed during cache TTL

10:01:01  Cache expires, re-introspects
          -> active=false -> rejected
~~~

This illustrates a **cache policy trade-off**, not a claim that Spring Security defaults to caching for 60 seconds. Actual introspector/cache configuration must be defined per deployment.

### 11.2. TTL rules

If the response includes a schema-valid `exp`, maximum cache duration can be bounded:

~~~text
cacheTtl = min(
    policyMaxTtl,
    tokenExpiration - currentTime
)
~~~

Never cache past token expiration. If `exp` is absent, cache only within an approved bound or **do not cache**. The longer the TTL, the slower revocation visibility becomes.

The choice depends on:

- **API sensitivity**: approving financial transactions may require closer-to-real-time status than reading general catalog data.
- **Authorization Server availability**: per-request introspection increases network dependency.
- **Load/latency**: caching can reduce authentication overhead.
- **Token lifetime**: short-lived tokens bound reuse windows, though they do not replace revocation.
- **Audience/scope isolation**: caches must preserve metadata for the **specific token**, never merging across users.

### 11.3. Never cache by `sub` or `client_id`

Two Access Tokens sharing the same `sub` can differ in scopes, audiences, lifetimes, and revocation states. Caching by `sub` could let a low-privilege token inherit high-privilege metadata from another token.

Caches must key properly on **token identity** and resource/issuer boundaries; never emit raw tokens in logs or metrics. If choosing a hash/token fingerprint as a cache key, evaluate token entropy, cache security, and memory/heap-dump exposure.

### 11.4. Cache `active=false`?

Negative caching can reduce load when clients repeatedly send invalid tokens. However, you need:

- Short TTLs and memory bounds so floods of junk tokens cannot fill the cache.
- Never retaining raw tokens indefinitely.
- Never caching an **HTTP 503/timeout error** as an inactive token conclusion.
- Accounting for `nbf` or token states that can change under policy.

Caching an inactive token conclusion is completely different from caching an upstream failure. Never merge both under the same `active=false` cache entry.

### 11.5. When near-instant revocation is required

Options include:

1. Introspecting on every request, or on sensitive operations.
2. Using very short cache TTLs, never exceeding `exp`.
3. Publishing invalidation/revocation events to the cache if supported by the architecture.
4. Using short-lived Access Tokens.
5. Checking local account status and domain permissions at execution time.

Never promise "revoking an opaque token blocks it immediately" when caches or asynchronous state replication are in play.

## 12. Introspection outages must fail closed

When the Authorization Server does not answer:

~~~text
Client -> API: Bearer token-A
API -> Introspection endpoint: POST token-A
Endpoint -> API: timeout/503/TLS failure

API has NO fresh evidence that token-A is active.
API MUST NOT fabricate a valid principal.
API MUST NOT skip authentication because upstream failed.
~~~

### 12.1. Fail-open example to avoid

~~~java
// DO NOT DO THIS.
try {
    return introspector.introspect(token);
} catch (Exception any) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "fallback-user",
        Map.of("sub", "fallback-user"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.write")));
}
~~~

Network failures would turn directly into granted access. A valid cache entry still within its policy-approved TTL is **different** from a catch-all fabricating fake Authentications: caching policy must pre-define acceptable revocation latency and be thoroughly tested.

### 12.2. Bounded retries

Transient errors during introspection timeouts/503s may be retried, provided you set:

- Connect/read timeouts and maximum total retry budget.
- Backoff and jitter where appropriate to prevent retry storms.
- Circuit breakers/bulkheads under high load.
- Never infinitely retrying **`active:false`**: that is an explicit rejection of the token.
- Never infinitely retrying HTTP 401 due to a wrong client secret.
- Never leaking tokens/secrets in logs or HTTP error bodies.

When authentication still cannot be verified, the request must **never execute as authenticated**, whether the API chooses to respond with 401 or 5xx/503 per its exception mapping.

## 13. Protecting the introspection endpoint and credentials

Because the Access Token is sent verbatim to the Authorization Server, this is a sensitive channel:

1. Use **HTTPS** only, with TLS certificate and hostname verification.
2. Load the introspection URI from **trusted configuration**, never from unverified tokens or request parameters.
3. Restrict outbound egress, redirects, and DNS/proxies per network policy.
4. Authenticate the Resource Server to the introspection endpoint using least-privilege credentials.
5. Store the client secret in a secret manager/environment supporting rotation.
6. Never log raw tokens, Basic Authorization headers, introspection POST bodies, or personal data.
7. Set appropriate timeouts and connection pool/load bounds.
8. Track errors by category without putting raw Bearer tokens into metric labels.

### 13.1. Broken Resource Server credentials

If the client secret expires or rotates improperly, the Authorization Server may return HTTP 401 for **all introspection requests**, preventing massive numbers of API requests from authenticating. That does not mean every user token expired.

Monitor **upstream client authentication errors** separately, check truststores/mTLS when used, execute planned rotations, and protect secrets.

### 13.2. Sender-constrained tokens

If the system uses mTLS-bound access tokens or DPoP, `active:true` alone does not prove the caller actually possesses the bound private key. The Resource Server must enforce **proof-of-possession** and verify confirmation claims (`cnf` where contracted) per the corresponding token-binding spec. Never treat an active introspection result as a substitute for sender constraints.

## 14. Testing `active=true/false` and each failure branch

### 14.1. Test matrix

| Scenario | Introspection | Expected result |
| --- | --- | --- |
| Valid read token | 200, `active:true`, `scope:orders.read` | GET passes if other policies pass. |
| Token lacking write scope | 200, `active:true`, only `orders.read` | POST returns **403**. |
| Revoked token | 200, `active:false` | **401**, controller not called. |
| Expired token | 200, `active:false` | **401**. |
| Non-existent token | 200, `active:false` | **401**. |
| Active token, wrong audience | 200, `active:true`, `aud:billing-api` | Rejected by audience/resource policy. |
| `active` is a string | 200, `{"active":"false"}` | No Authentication created; protocol error logged. |
| Missing `active` | 200, `{}` | No Authentication created. |
| Introspection returns HTTP 401 | Wrong Resource Server credential | Access denied, classified as integration error. |
| Introspection returns HTTP 503 | Upstream unavailable | Fail closed; do not treat as business inactive token. |
| Upstream timeout | No response | Fail closed, bounded retries. |
| Active token, suspended local account | 200, `active:true` | Denied by domain authorization. |
| Newly revoked token, cache still active | Cache hit | Verify maximum reuse window matches TTL. |

### 14.2. Testing with a fake `OpaqueTokenIntrospector`

To test **HTTP authorization** independently of the network, create a test-only fake introspector:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@TestConfiguration
class TestOpaqueIntrospectorConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector() {
        return token -> {
            if (!"active-reader-test-token".equals(token)) {
                throw new BadOpaqueTokenException(
                    "Test token is not active");
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                "person-123",
                Map.of("sub", "person-123", "scope", "orders.read"),
                List.of(new SimpleGrantedAuthority(
                    "SCOPE_orders.read")));
        };
    }
}
~~~

With this fake, you can send real Bearer strings through the filter:

~~~text
GET /api/orders/42
Authorization: Bearer active-reader-test-token
-> Authenticated with orders.read permission

POST /api/orders/42
Authorization: Bearer active-reader-test-token
-> 403 if endpoint requires orders.write

GET /api/orders/42
Authorization: Bearer some-other-token
-> 401
~~~

This is a **test double** and must never be used in production. Because the fake decides `active` using custom logic, these tests **do not prove how the HTTP introspection client parses JSON `active`**. Add integration tests with a mock server.

### 14.3. `MockMvc opaqueToken()` does not call introspection

Example `spring-security-test` helper:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

`opaqueToken()` injects a pre-authenticated mock `Authentication` without sending the token to an introspection endpoint. It is useful for testing **authorization**, yet **cannot prove `active=false` is rejected**. For revocation tests, send real Bearer tokens through a real introspector or test endpoint.

### 14.4. Integration tests with a mock introspection server

Server fixture design:

~~~text
POST /oauth2/introspect, token=active-reader
  -> HTTP 200
  {"active":true,"sub":"person-123",
   "scope":"orders.read","aud":["orders-api"]}

POST /oauth2/introspect, token=inactive
  -> HTTP 200
  {"active":false}

POST /oauth2/introspect, token=wrong-audience
  -> HTTP 200
  {"active":true,"scope":"orders.read","aud":["billing-api"]}

POST /oauth2/introspect, token=malformed
  -> HTTP 200
  {"active":"false"}

POST /oauth2/introspect, token=outage
  -> HTTP 503
~~~

Steps:

1. Start WireMock, MockWebServer, or an equivalent test HTTP server.
2. Point `introspection-uri` to the fixture server with test credentials—never production secrets.
3. Send a request to the Resource Server with `Authorization: Bearer inactive` **without using `opaqueToken()`**.
4. Verify the API returns 401, does not invoke the controller/domain service, and the mock server actually received the introspection POST.
5. Repeat for `active-reader`, missing scope, wrong audience, wrong JSON type, HTTP 503, and timeout.
6. If caching is enabled, test a token that starts active and is then revoked, confirming it is blocked once the TTL expires.

A localhost HTTP fixture may be used **only in isolated test environments**; production network/TLS tests must enforce real HTTPS and certificate verification per policy. Never put production Access Tokens or client secrets into tests.

### 14.5. Testing caching when a token is revoked

~~~text
T1: Mock server returns active=true for token-A.
T2: API calls with token-A, cache retains result per config.
T3: Mock server switches to active=false for token-A.
T4: API calls with token-A before and after TTL.
T5: After TTL expires, it must re-introspect and reject.
~~~

This test reveals what the **actual accepted revocation latency** is. Never unit test only `active:false` and conclude the system handles revocation instantaneously while a cache still holds `active:true`.

## 15. Troubleshooting when the API rejects an opaque token

| Symptom | What to verify | How to resolve |
| --- | --- | --- |
| Introspection HTTP 200 yet API 401 | Is JSON `active` boolean `false`, or is the schema wrong? | Separate inactive tokens from protocol errors. |
| Every request 401 after secret rotation | Are the introspection client credentials valid? | Check credential rotation, mTLS/Basic, and safe Authorization Server logs. |
| Unexpired token gets `active:false` | Was it revoked, wrong issuer/endpoint, or restricted introspection scope? | Verify contract; never accept the token anyway. |
| Active token yet POST returns 403 | Does returned scope include `orders.write`? | Check authorities and HTTP rules. |
| Active token yet domain returns 403 | Do user/tenant/owner/status match? | Check business policy; do not assume the token is invalid. |
| Revoked token still works briefly | Is active caching enabled? What is the TTL? | Adjust cache/invalidation per revocation SLA. |
| Introspection times out, API fails | Upstream DNS/TLS/connect timeout/capacity? | Bounded retries, protect service, and fail closed. |
| `active:"true"` rejected | Wrong JSON type. | Fix Authorization Server/adapter; avoid ambiguous coercion. |
| Code expecting `Jwt` principal gets null | API is configured for opaque tokens. | Use `OAuth2AuthenticatedPrincipal`/Bearer authentication. |
| Web sign-in ID Token fails against API | Wrong token type/resource. | Issue proper API Access Token per OAuth contract. |

### 15.1. Observing without leaking credentials

Record:

- Request ID, timestamp, error category.
- `token_inactive`, `introspection_timeout`, `introspection_http_401`, `introspection_schema_error`, `insufficient_scope`.
- Introspection latency and error rates.
- Cache hit/miss counts and invalidation counts when caching is used.
- Business audits with access-controlled identifiers.

Never record:

- Raw opaque Access Tokens, even after revocation.
- `Authorization` headers on API or introspection requests.
- Client secrets, mTLS private keys, or form bodies containing tokens.
- Full introspection responses containing personal claims.
- Token strings as metric labels or tracing attributes.

## 16. Common design mistakes

| Mistake | Why it is dangerous | Correct approach |
| --- | --- | --- |
| Allowing requests upon seeing HTTP 200 from introspection. | 200 can contain `active:false`. | Check JSON boolean `active`. |
| Treating `active:"true"` as boolean `true`. | Type/contract violation that can mask issuance bugs. | Accept only RFC-compliant responses. |
| Treating tokens as active on upstream timeout. | Fail-open authentication on infrastructure faults. | Fail closed; emit controlled operational errors. |
| Parsing scopes out of an opaque token by splitting strings. | Unverified data. | Read introspection metadata only from trusted sources. |
| Caching `active` indefinitely. | Revoked tokens stay usable long-term. | Bounded TTLs and invalidation. |
| Caching by user ID instead of token. | Mixes scopes/audiences across distinct tokens. | Key cache properly on token identity. |
| Caching HTTP 503 as `active=false`. | Confuses outages with invalid tokens, hurting recovery. | Separate errors from token state; distinct retries/metrics. |
| Granting all permissions when `active=true`. | Skips scope/tenant/owner checks. | Enforce independent authorization after authentication. |
| Accepting tokens issued for other APIs. | Audience/resource unchecked. | Enforce resource binding per contract. |
| Using OIDC ID Tokens in place of Access Tokens. | Wrong purpose/audience. | Accept only the proper Access Token type. |
| Assuming logout always revokes Access Tokens. | Session logout may not revoke issued tokens. | Design token lifecycle and test revocation explicitly. |
| Custom introspector returning a principal inside a catch block. | Bypasses `active` and network errors. | Standard delegate + extra validators, fail closed. |
| Testing solely with `MockMvc opaqueToken()`. | Does not exercise real HTTP introspection. | Add integration tests sending Bearer tokens through the introspector. |
| Logging raw tokens on errors. | Credential leak. | Use error metrics/categories without tokens. |

## 17. Project rollout workflow

1. **Define the token contract:** API accepts opaque Access Tokens; document token profile, issuer, resource/audience, scopes, and required lifetimes.
2. **Agree on the introspection contract:** HTTPS endpoint, client authentication method, boolean `active`, and permitted metadata.
3. **Configure Spring Security:** `spring.security.oauth2.resourceserver.opaque-token` and `oauth2ResourceServer().opaqueToken()`.
4. **Preserve `active` semantics:** inactive fails authentication; mistyped/missing `active` never creates a principal.
5. **Verify resource and permissions:** audience, scopes, domain account/tenant, and specific records independently of `active`.
6. **Handle upstream errors:** separate inactive tokens from introspection outages/credential failures; fail closed with bounded retries and timeouts.
7. **Define cache TTL and revocation latency:** never exceed token expiration, never cache transport failures as inactive, and plan invalidation.
8. **Protect tokens and secrets:** HTTPS/TLS, endpoint allowlists, least-privilege client credentials, no raw token logging.
9. **Test positive/negative cases:** `active=true`, `false`, mistyped JSON, timeouts, 503, missing scope, wrong audience, and suspended local users.
10. **Test state transitions:** a token initially active and then revoked; verify cache behavior under real policy.

**Remember:** In OAuth 2.0 introspection, **`active:false` means the Resource Server must not accept the token**, without necessarily revealing exactly why it is inactive. **`active:true` does not mean access to every API**; resource, scope, and business permissions must still be checked. If introspection fails, the system must **fail closed** and distinguish infrastructure errors from invalidated tokens.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — `OpaqueTokenIntrospector` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449).
