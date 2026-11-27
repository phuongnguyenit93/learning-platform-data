# Distinguishing token errors from introspection credential errors or network errors

## 1. Why doesn't a 401 response from an API always mean the opaque token is bad?

In a **Spring Security OAuth 2.0 Resource Server**, when an API receives an **opaque access token**, the Resource Server does not decode the token like a JWT to verify signatures itself. Instead, the Resource Server calls the Authorization Server's (AS) **OAuth 2.0 Token Introspection** endpoint per **RFC 7662**.

The system involves **two independent HTTP hops**:

~~~text
Hop A: OAuth Client -> Resource Server
  GET /api/orders
  Authorization: Bearer OPAQUE_ACCESS_TOKEN

Hop B: Resource Server -> Authorization Server
  POST /oauth2/introspect
  Authorization: Basic <RS introspection client credentials>
  Content-Type: application/x-www-form-urlencoded
  Body: token=OPAQUE_ACCESS_TOKEN
~~~

A common point of confusion:

- **HTTP 200 + JSON `{"active":false}`** on hop B: the AS answered a valid introspection request and stated the token is **not active**.
- **HTTP 401** on hop B: the AS may be rejecting **the Resource Server's own client ID/client secret or authentication method**. This **does not prove the caller's opaque token is bad**.
- **HTTP 503/timeout/TLS failure** on hop B: the Resource Server received no trustworthy introspection response, so **it has no verdict on whether the token is active**.

All of these cases must **block the protected request from proceeding** whenever the Resource Server cannot verify a trusted credential. Yet the error category, retry behavior, response code returned to the caller, and operational remediation must **differ**.

### Lesson objectives

This lesson focuses on:

1. Distinguishing **invalid/inactive token**, **introspection client authentication failure**, **network/AS outage**, **protocol error**, and **post-authentication insufficient permissions**.
2. Understanding the two credential types, two HTTP statuses, and how they interact across the Spring Security Servlet filter chain.
3. Designing fail-closed behavior, error mapping, retries/caching, and observability.
4. Diagnosing Spring Boot Resource Server misconfigurations without building a parallel JWT/Bearer filter.
5. Designing test scenarios covering opaque-token authentication and upstream dependency failures.

## 2. Two different sets of credentials

Distinguish the participants:

| Entity | Role | Credential |
|---|---|---|
| OAuth Client | Obtains access token and calls API | Bearer access token sent to RS |
| Resource Server | Protects API | Receives and validates access token |
| Authorization Server | Issues tokens, validates tokens via introspection | Manages tokens and introspection endpoint |
| Introspection client | RS identity used for AS permission to introspect | Client ID/secret, mTLS, or another AS-supported method |

Example request sent by client to API:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer OPAQUE_ACCESS_TOKEN
~~~

Request sent by Resource Server to AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_RS_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_ACCESS_TOKEN
~~~

On hop B, **Basic credentials belong to the Resource Server**, not the user's access token. Base64 in Basic auth **is not security encryption**; the connection requires HTTPS/TLS and credentials must be protected via a proper secret manager.

Not every Authorization Server uses Basic auth. Some systems require **`private_key_jwt`, mTLS**, or another client authentication method per contract. The Resource Server must use the exact method and have introspection permission under AS policy.

### Never confuse AS credentials with the caller's token

~~~text
Bearer token:
  Used to call orders-api.
  Can be active/inactive, expired, missing scope.

Introspection client credentials:
  Used by orders-api to call auth.example.com.
  Can have wrong secret, be disabled, lack introspection permission.
~~~

If the RS uses the wrong secret, the AS can return 401 on hop B **for every token**, even completely valid ones. Asking users to sign in again or repeatedly refreshing tokens cannot fix that configuration error.

## 3. RFC 7662: which response actually says the token is inactive?

Token introspection typically uses POST with a form body:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_RS_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

**`token_type_hint`** is an optional parameter helping the AS look up the token; it does not turn a token into a valid access token. Calling the endpoint still depends on introspection client registration and AS policy.

### 3.1. HTTP 200 and `active=true`

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "client_id": "shop-web",
  "sub": "user-42",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "iss": "https://auth.example.com",
  "exp": 1910003600
}
~~~

This is a valid response stating the token is **active** per AS. The Resource Server still must check:

- Does it match the API's **audience/resource binding**?
- Does the token belong to a profile allowed as an access token?
- Are scopes/authorities sufficient for the endpoint?
- Does the principal/client have permissions on the specific tenant and object?
- Are required metadata fields present and consistent?

**`active=true` does not mean access to every API.** A token that is active yet meant only for **`billing-api`** must never be accepted for **`orders-api`**.

### 3.2. HTTP 200 and `active=false`

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

This is the actual signal from the AS stating the token is **inactive**. Possible reasons include:

- Forged/non-existent token.
- Expired token.
- Revoked token.
- Invalidated under AS policy.
- Not recognized by the AS in this introspection caller's context.
- AS withholds the reason per security policy.

**Never equate `active=false` with "expired."** RFC 7662 intentionally does not require the AS to detail why a token is inactive; some AS implementations return `active=false` whenever the RS is not allowed to know whether a token exists.

Proper conclusion:

~~~text
HTTP 200 + active=false from trusted AS
  -> Token is not accepted for this request.
  -> Do not create an authenticated principal.
  -> Hop A typically returns 401 / Bearer invalid_token depending on config.
~~~

### 3.3. HTTP 200 with malformed JSON

Type mismatch example:

~~~json
{
  "active": "true"
}
~~~

**`active`** in RFC 7662 is a boolean, not a string. Another example:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read"
}
~~~

Missing **`active`**.

This is a **protocol/contract failure**—never default to `active=true` or coerce it into `active=false`. An HTTP 200 might carry HTML from a gateway or JSON from the wrong endpoint; responses must satisfy the exact schema the introspector expects.

## 4. HTTP 401 from the introspection endpoint: RS-to-AS authentication failure

Example AS response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
Content-Type: application/json

{
  "error": "invalid_client"
}
~~~

This is a **hop B failure**. The RS might be:

- Sending the wrong client ID or secret.
- Using an old secret after the AS rotated credentials.
- Using a disabled client or one never granted introspection rights.
- Using Basic when the AS demands mTLS/`private_key_jwt`.
- Calling the wrong Authorization Server endpoint/realm/tenant.
- Sending credentials in the wrong place.
- Having a reverse proxy strip or alter the `Authorization` header.
- Using an expired client certificate when the AS requires mTLS.

None of these errors **make any statement about the caller's access token**.

~~~text
User's opaque token: may be active.
RS introspection secret: wrong.

AS receives POST introspection:
  -> returns 401 invalid_client
  -> returns no trustworthy token status.

Accurate classification:
  INTROSPECTION_CLIENT_AUTH_FAILURE
  NOT TOKEN_INACTIVE.
~~~

### HTTP 403 from the AS

An AS or gateway may return 403 Forbidden if the introspection client is recognized yet **not permitted** to query that token/realm/resource.

Check client registration permissions, introspection policies, and tenant binding. An HTTP 403 on hop B **differs** from an HTTP 403 on hop A when an authenticated user lacks a scope.

Exact status/error details depend on the Authorization Server, deployment policy, and HTTP gateway. Never assume with certainty that a secret is wrong from a bare 401/403 status without checking the AS contract.

## 5. HTTP 400: invalid introspection request

Example:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_request"
}
~~~

Causes include:

- Missing **`token`** parameter.
- Sending JSON when the endpoint accepts only **`application/x-www-form-urlencoded`**.
- Bad encoding, malformed parameters, or request mangled by a proxy.
- Request aimed at the token-issuance endpoint instead of introspection.
- Wrong HTTP method or client authentication scheme per contract.

**Never conclude "the token expired" upon seeing HTTP 400 from the AS.** For an inactive token, an RFC 7662-compliant AS normally returns **200 + `active=false`**. HTTP 400 must be investigated as a **request/protocol error**.

A confusing case is a misconfigured endpoint: the API calls **`/oauth2/token`** or the login endpoint, and the server returns a request error rather than an introspection result.

## 6. HTTP 429/5xx, DNS, timeouts, and TLS: infrastructure errors, not token errors

Key failure modes:

| Symptom | Classification | Does it prove the token is inactive? |
|---|---|---|
| HTTP 429 Too Many Requests | AS throttling/quota | **No** |
| HTTP 500 | AS internal error | No |
| HTTP 502/503/504 | Gateway/AS unavailable | No |
| DNS resolution failure | Network | No |
| Connection refused/reset | Network | No |
| Connect timeout | Network | No |
| Read timeout | Slow network/AS | No |
| TLS certificate unknown/expired | TLS trust/configuration | No |
| Hostname mismatch | TLS trust/configuration | No |
| HTTP 200 yet schema mismatch | Protocol response error | No |

Lacking a trusted introspection response **is not equivalent** to `active=false`.

Remember:

~~~text
Upstream did not answer in time
    !=
AS answered "active=false".
~~~

Safe behavior:

1. **Fail closed:** never authenticate an opaque token without valid proof.
2. **Preserve the dependency failure cause** so AS/network/config bugs get fixed.
3. Bounded retries for transient failures, never infinite retries.
4. Explicit timeouts to avoid tying up servlet threads.
5. Circuit breakers and backoff when the AS is overloaded.
6. Bounded caching; never rely on stale allow decisions indefinitely.
7. Never disable TLS verification to "make introspection work."
8. Never pick arbitrary introspection endpoints from untrusted tokens.

## 7. Reference matrix: distinguishing outcomes on hop B

| Result from AS | Outcome category | Resource Server action | Hop A handling |
|---|---|---|---|
| **200 + `active=true`**, valid metadata | Success | Create authenticated principal, check permissions | Proceed to endpoint or 403 if lacking scope |
| **200 + `active=false`** | `TOKEN_INACTIVE` | Do not authenticate token | Usually 401, `invalid_token` |
| **200 + `active=true`**, wrong audience | `TOKEN_CONTRACT_INVALID` | Reject token for API | Usually 401 |
| **200 + `active=true`**, missing scope | `AUTHORIZATION_DENIED` | Authenticated yet lacks permission | Usually 403 |
| **401 `invalid_client`** | `RS_INTROSPECTION_AUTH_FAILURE` | No token verdict, fail closed | Server/dependency failure; never label token invalid |
| **403 forbidden at AS** | `RS_INTROSPECTION_ACCESS_DENIED` | No token verdict | Server/dependency failure |
| **400 `invalid_request`** | `INTROSPECTION_PROTOCOL_ERROR` | Fix request/config, fail closed | Appropriate server/dependency error |
| **429** | `INTROSPECTION_RATE_LIMIT` | Backoff/throttle, fail closed | Typically dependency error such as 503 |
| **5xx** | `INTROSPECTION_AS_UNAVAILABLE` | Bounded retry, fail closed | Typically 503 or matching server code |
| **DNS/TLS/timeout** | `INTROSPECTION_TRANSPORT_ERROR` | Fail closed, alert | Typically dependency error |
| **200 yet malformed JSON** | `INTROSPECTION_INVALID_RESPONSE` | Fail closed, investigate protocol | Dependency/protocol error |

**"Usually" here indicates design guidance**, not a guarantee that Spring Security returns those exact codes by default across every version. How the framework maps exceptions to HTTP depends on the introspector, provider, authentication entry point, and application configuration.

## 8. 401 on hop A and 401 on hop B are two different concepts

~~~text
Hop A:
  Client --Bearer opaque token--> Orders API
  API returns 401:
    Caller credential rejected (or error mapping unrefined).

Hop B:
  Orders API --RS client credentials--> Authorization Server
  AS returns 401:
    RS is not accepted to call introspection.
    Says nothing reliable about the caller's opaque token.
~~~

Likewise:

~~~text
403 on hop A:
  Caller is authenticated yet lacks permission for the action.

403 on hop B:
  RS client is not permitted to introspect under AS policy.
~~~

A common operational incident: the RS uses a stale secret so the AS returns 401, and the framework or handler translates that into a 401 to the caller. The frontend assumes the token expired and refreshes continuously, yet **token refresh cannot fix a backend secret**.

Observe statuses across **both hops**, never looking at a single **`http.response.status=401`** metric and concluding "lots of tokens expired."

## 9. Where does introspection sit inside Spring Security?

The Servlet processing chain typically looks like:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as AuthorizationFilter

    C->>F: Authorization: Bearer opaque-token
    F->>M: BearerTokenAuthenticationToken
    M->>P: authenticate(token)
    P->>I: introspect(raw token)
    I->>AS: POST /introspect + RS credentials
    alt 200 active=true
      AS-->>I: trusted attributes
      I-->>P: OAuth2AuthenticatedPrincipal
      P-->>M: BearerTokenAuthentication
      M-->>F: Authenticated result
      F->>A: Continue, evaluate authority
    else 200 active=false
      AS-->>I: inactive
      I-->>P: Token rejected
    else 401/403/5xx/network
      AS-->>I: Failure or no response
      I-->>P: Introspection error; no authenticated principal
    end
~~~

Key classes:

| Component | Responsibility |
|---|---|
| **`BearerTokenAuthenticationFilter`** | Extracts caller's Bearer credential |
| **`BearerTokenAuthenticationToken`** | Unauthenticated authentication request holding the raw token |
| **`OpaqueTokenAuthenticationProvider`** | Calls introspector to authenticate opaque token |
| **`OpaqueTokenIntrospector`** | Introspects token and returns `OAuth2AuthenticatedPrincipal` on success |
| **`OAuth2AuthenticatedPrincipal`** | Trusted principal/attributes from introspection |
| **`BearerTokenAuthentication`** | Resulting `Authentication` after successful introspection |
| **`SecurityContextHolder`** | Holds request security context for authorization |
| **`AuthorizationFilter`** | Enforces endpoint permissions |
| **`BearerTokenAuthenticationEntryPoint`** | Handles authentication challenges |
| **`BearerTokenAccessDeniedHandler`** | Handles insufficient permissions for Bearer authentication |

**Never write a parallel JWT filter** as a "fallback" when opaque introspection fails. A filter decoding an opaque token itself cannot verify tokens that the AS defines as opaque.

### Spring Security exceptions do not preserve every upstream status automatically

Exceptions you may encounter by version include:

- **`BadOpaqueTokenException`**: relates to a token rejected during introspection.
- **`OAuth2IntrospectionException`**: error occurring during introspection, not necessarily meaning the token is inactive.

Depending on implementation and Spring Security version, HTTP 401/403, malformed JSON, or network errors may be wrapped in exceptions with varying causes. **Never classify AS outages accurately by matching exception message strings**, as messages can change or contain sensitive details.

To distinguish upstream 401, 403, 429, 5xx, timeouts, or TLS failures, capture status/cause **in the HTTP client or a protocol-aware introspector adapter** before that context is lost.

## 10. Spring Boot configuration for opaque tokens

Example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
~~~

In deployments, replace the placeholder with a secret provided via **environment variables/secret manager**, never committing client secrets to repositories or public configs.

Example `SecurityFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Meaning:**

1. Endpoints under **`/api/**`** use Spring Security opaque-token Resource Server.
2. The RS calls the configured introspection endpoint using the supplied credentials.
3. When the AS reports **`active=true`** and the response meets the contract, the RS builds an authenticated principal.
4. Scopes returned by the AS can become **`SCOPE_...`** authorities via the default converter.
5. This configuration is illustrative; add resource binding, principal-type checks, and domain authorization per your AS contract.

**The introspection URI must belong to a trusted AS.** Never assume every issuer uses `/oauth2/introspect`, and never take the introspection URL from an incoming Bearer token request.

### Two secrets to protect

- Raw opaque access token in the HTTP `Authorization` header: **caller's Bearer credential**, never log.
- Introspection client secret: **Resource Server's credential toward the AS**, never log.

Never include either in stack traces, HTTP 500 bodies, metric labels, tracing spans, or published config files.

## 11. Classifying exceptions without hiding infrastructure errors

An application model can define internal outcomes:

~~~text
ACTIVE(principal)
INACTIVE
RS_CREDENTIALS_REJECTED
RS_NOT_ALLOWED_TO_INTROSPECT
BAD_INTROSPECTION_REQUEST
INTROSPECTION_THROTTLED
AS_UNAVAILABLE
NETWORK_TIMEOUT
TLS_FAILURE
MALFORMED_RESPONSE
~~~

This is a **suggested outcome model**, not a built-in Spring Security enum. It aids observability and API response mapping.

You can attach an **`OpaqueTokenIntrospector` decorator** to record coarse outcomes:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ObservedOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final IntrospectionMetrics metrics;

    public ObservedOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            IntrospectionMetrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        try {
            OAuth2AuthenticatedPrincipal principal =
                    delegate.introspect(token);
            metrics.record("active");
            return principal;
        }
        catch (BadOpaqueTokenException ex) {
            metrics.record("inactive");
            throw ex;
        }
        catch (OAuth2IntrospectionException ex) {
            metrics.record("introspection_failure");
            throw ex;
        }
    }
}
~~~

In this example:

- **`IntrospectionMetrics`** is an application-defined service.
- **`delegate`** is an appropriate introspector provided by Spring Security or the application; the snippet only illustrates the decorator, not full bean wiring.
- **`BadOpaqueTokenException`** is caught before the more general introspection exception.
- Exceptions are **rethrown**, never turning everything into an invalid-token error.
- Never log the **`token`** argument.
- Exact exception subtype hierarchies and wrapped causes depend on version and implementation.

**Important limitation:** This decorator separates only token-inactive from general introspection errors at the built-in exception level. To classify **401 vs. 403 vs. 5xx vs. timeout/TLS**, you need an HTTP-aware adapter or instrumentation inside the HTTP client actually calling the AS. Never infer upstream status from **`ex.getMessage()`**.

## 12. Controlling the hop A response: 401, 403, 500, or 503?

When the AS returns **`active=false`**, the API must normally reject the Bearer credential. An appropriate response might be:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

When the token is authenticated yet lacks scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

When introspection credentials are rejected by the AS or the AS has an outage, the API should signal a **server dependency failure**, for example:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "error": "authentication_dependency_unavailable"
}
~~~

**503 is an example of a deliberately designed API error contract**, not an RFC 7662 requirement or guaranteed default behavior across all Spring Security versions.

You might return 500 for severe configuration errors like a bad introspection secret, and 503 for timeouts/outages. What matters is **never claiming an access token is invalid without a trustworthy token-state verdict**.

### Why might `@ControllerAdvice` not catch the error?

**`BearerTokenAuthenticationFilter`** runs inside the Servlet filter chain, before controllers. Exceptions from the introspector/provider may be handled by Spring Security's authentication failure handler/entry point or filter-chain error path, **not necessarily reaching an MVC `@ExceptionHandler`**.

To distinguish invalid tokens from upstream outages in API responses:

1. Capture the classification from the HTTP client/introspection adapter.
2. Preserve the failure reason across Spring Security's authentication boundary.
3. Configure failure/entry-point/exception handlers aligned with your filter chain and framework version.
4. Ensure every failure produces zero authenticated principals.
5. Never leak upstream Basic challenges or client secret details from the AS to callers.
6. Test end-to-end HTTP statuses directly rather than guessing from property configuration.

**Never forward** an upstream challenge verbatim:

~~~http
WWW-Authenticate: Basic realm="introspection"
~~~

to callers of **`orders-api`**. API callers use Bearer tokens, not RS introspection credentials.

## 13. Retries: not every error is safe to retry

| Situation on hop B | Is retrying sensible? | Reason |
|---|---|---|
| **200 `active=false`** | **No** | AS already stated the token is inactive |
| **401 `invalid_client`** | **Not with the same credentials** | Must fix client ID/secret/method |
| **403 denied** | Do not retry blindly | Must fix RS client permissions |
| **400 `invalid_request`** | Do not retry a malformed request | Must fix endpoint/body/encoding |
| **429 throttled** | Possibly, with backoff/rate limit | Avoid overloading AS |
| **502/503/504** | Possibly bounded retries | Transient error |
| **Connect/read timeout** | Possibly bounded retries | Needs deadline and circuit breaker |
| **TLS validation error** | Never disable TLS to retry | Must fix certificate/truststore |
| **Malformed HTTP 200 JSON** | Retry only under strict policy | May be a persistent protocol bug |

Proper retries require:

- Small attempt limits, never infinite loops.
- Total deadline matching the API's latency budget.
- Exponential backoff with jitter.
- Honoring **`Retry-After`** when present and appropriate.
- Rate limiting/circuit breakers to prevent retry storms.
- Distinguishing AS timeouts from gateway timeouts.
- Never forcing the AS to process thousands of repeated introspection requests from a single user request.

A backend using synchronous introspection can exhaust Servlet threads if it waits long on upstream calls and retries endlessly. Protecting RS availability is part of the design.

## 14. Introspection caching: stale results vs. dependency failures

Because introspection can cost a network call, the Resource Server may cache results. Yet caching must respect token state and expiration.

### 14.1. Caching `active=true`

~~~text
T0: AS returns active=true, scope=orders.read.
T1: RS caches for 30 seconds.
T2: AS revokes token.
T3: RS keeps seeing cached active=true until cache expires,
    unless invalidated.
~~~

Thus **caching `active=true` widens the token revocation window**. Use short TTLs, never exceeding token expiration, aligned with your revocation SLA.

### 14.2. Caching `active=false`

Negative-caching inactive token results may be allowed by policy, provided attackers sending random junk tokens cannot flood the cache. Never convert transport errors into `active=false` and cache them.

### 14.3. Never cache timeouts or upstream 401s as inactive tokens

~~~text
AS response: 401 invalid_client
    != cache(token, active=false)

AS request: timeout
    != cache(token, active=false)
~~~

Once the RS fixes its secret or network, genuinely active tokens must be able to be re-introspected. Caching configuration errors as token results causes false rejections even after infrastructure recovers.

### 14.4. Fail closed vs. stale cached allow

When the AS is unavailable, an application may want to use a cached positive introspection result to soften an outage. Do so only if **trust/revocation policy permits**, the cached entry is within its age bound, the token has not expired, and resource bindings match.

Never enable anything like:

~~~text
if introspection fails:
    accept any opaque token
~~~

That is **fail open** and lets forged tokens access the API.

## 15. TLS, secret rotation, and wrong-realm errors

### TLS/hostname mismatch

Suppose the RS calls:

~~~text
https://auth-internal.example.local/introspect
~~~

yet the endpoint certificate is valid only for:

~~~text
auth.example.com
~~~

The TLS connection can fail before any HTTP response arrives. This is a **TLS/trust failure**, not an inactive token. Fix the certificate, hostname, DNS, or truststore—**never disable hostname verification**.

### Out-of-sync secret rotation

~~~text
AS rotated introspection client secret from V1 to V2.

RS instance 1: uses V2 -> AS 200
RS instance 2: uses V1 -> AS 401

Same opaque token:
  request hitting instance 1 succeeds;
  request hitting instance 2 fails.
~~~

This is **configuration drift**, not a token randomly expiring. Telemetry should include RS instance IDs and a **non-sensitive secret version alias**, never logging real secret values.

### Wrong realm or AS endpoint

An Authorization Server with multiple realms/tenants may have separate introspection credentials and endpoints. Sending a token from realm A to realm B's introspection endpoint may return **`active=false`** or 401/403 depending on the provider.

Configure trust domains, endpoints, and credentials per contract. Never let opaque tokens declare arbitrary URLs for the RS to call. Opaque strings have no mandatory JWT structure to read an issuer from.

## 16. Multi-issuer opaque tokens and endpoint selection

If an API trusts multiple Authorization Servers, route introspection based on trusted context:

~~~text
/tenant-a/api/** -> Introspection endpoint A + client credentials A
/tenant-b/api/** -> Introspection endpoint B + client credentials B
~~~

Or use an **`AuthenticationManagerResolver`** / equivalent multi-tenant pattern if supported by your Spring Security architecture.

Avoid:

~~~text
read opaque token prefix
    -> construct arbitrary URL from request
    -> send token to that URL
    -> trust response
~~~

unless prefix and endpoint binding belong to an AS-defined token protocol restricted by an allowlist and immune to SSRF.

If two endpoints could accidentally share colliding token strings, partition caches by endpoint/trust domain rather than pooling all introspection results in a single global namespace.

## 17. Authentication differs from authorization: `active=true` can still yield 403

Suppose the AS returns:

~~~json
{
  "active": true,
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

The POST endpoint requires:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Then:

~~~text
Token state:
  active=true

Authentication:
  succeeds if the full token acceptance contract passes

Authorization:
  token lacks SCOPE_orders.write
  => denied, typically 403
~~~

Similarly, an active token with write scope can still be denied if the user lost tenant membership, the order belongs to another owner, or the order is locked. Domain authorization sits **after** token introspection, rather than manifesting as **`active=false`**.

### Scope does not mean all roles and permissions

An introspection response with **`scope=orders.write`** means the AS granted the token write scope. The API still must check object-level authorization and current privileges if required by policy. Never pull **`roles`**, **`groups`**, or **`sub`** from the response to auto-grant domain admin powers without a defined mapping and trust contract.

## 18. Observability: track errors at the right hop

Metric dimensions should use cardinality-controlled values:

| Field | Example | Note |
|---|---|---|
| `introspection.endpoint_id` | `shop-as-primary` | Trusted config ID, not a token-supplied URL |
| `introspection.outcome` | `inactive` | `active`/`inactive`/`upstream_auth`/`network`/... |
| `introspection.upstream_status` | `200`, `401`, `503`, `none` | Status on hop B |
| `api.response_status` | `401`, `403`, `503` | Status on hop A |
| `introspection.latency` | histogram | Detect timeouts/saturation |
| `rs.instance` | `api-pod-3` | Spot config drift |
| `error_category` | `client_auth`, `network`, `protocol` | Contains no secrets |
| `secret.version_alias` | `auth-secret-v2` | Alias only, never the secret value |

Never put raw Bearer tokens, Basic Authorization headers, form-body tokens, client secrets, PII, or sensitive HTTP responses into logs or traces.

### Helpful alerts

- **Upstream 401 rate spikes after deployment:** check client ID/secret, mTLS, or auth method.
- **Upstream 403 rate spikes:** check introspection permissions.
- **Simultaneous spike in timeouts/503s:** check AS outage or gateway saturation.
- **TLS errors spike after certificate rotation:** inspect truststores/hostnames.
- **`active=false` rises** while upstream 200s stay steady: tokens are genuinely inactive or clients are sending bad tokens.
- **One replica fails while others succeed:** check for secret/config drift.

Tracking only total client-facing 401s is **not enough** to pinpoint root causes.

## 19. State machine diagram classifying error layers

~~~mermaid
flowchart TD
    A["Client sends Bearer opaque token"] --> B{"Valid Bearer request?"}
    B -- "No" --> R["Bearer request failure"]
    B -- "Yes" --> C["POST trusted introspection endpoint"]
    C --> D{"HTTP response received?"}
    D -- "No: network/TLS/timeout" --> INF["Dependency failure, fail closed"]
    D -- "Yes" --> E{"HTTP status?"}
    E -- "401/403" --> AUTH["RS introspection client auth/access failure"]
    E -- "429/5xx" --> INF
    E -- "400" --> PROT["Bad introspection request"]
    E -- "200" --> F{"JSON active boolean?"}
    F -- "false" --> INV["Token inactive; reject credential"]
    F -- "true" --> G["Validate audience/resource metadata"]
    F -- "Missing/invalid" --> PROT
    G --> H{"Token contract met?"}
    H -- "No" --> INV
    H -- "Yes" --> I["Authenticated principal"]
    I --> J{"Enough scope/domain authority?"}
    J -- "No" --> DENY["Authorization denied"]
    J -- "Yes" --> OK["Allow operation"]
    AUTH --> ERR["Server dependency/configuration error"]
    PROT --> ERR
~~~

This model avoids two anti-patterns:

- **Fail open:** cannot introspect yet still trusts the token.
- **Misclassification:** cannot introspect yet claims the AS rejected the caller's access token.

Both must be avoided in a Resource Server.

## 20. Test matrix for each introspection state

The scenarios below are **design expectations**, not observed test runs.

| Stub AS or network condition | Expected classification | Security behavior |
|---|---|---|
| 200 + `active=true` + matching scope/audience | `ACTIVE` | Create principal then authorize |
| 200 + `active=false` | `TOKEN_INACTIVE` | Do not create principal; usually 401 |
| 200 + `active=true` yet missing scope | `AUTHORIZATION_DENIED` | Usually 403 |
| 200 + `active=true` yet wrong audience | `TOKEN_CONTRACT_FAILURE` | Reject token |
| 401 + `invalid_client` | `UPSTREAM_AUTH_FAILURE` | Do not treat token as inactive |
| 403 + `forbidden` | `UPSTREAM_ACCESS_DENIED` | Do not treat token as inactive |
| 400 + `invalid_request` | `INTROSPECTION_REQUEST_ERROR` | Fix request, do not retry blindly |
| 429 | `THROTTLED` | Backoff/circuit breaker, fail closed |
| 500/502/503/504 | `UPSTREAM_UNAVAILABLE` | Fail closed, dependency response |
| DNS failure | `NETWORK_ERROR` | Fail closed |
| Connect timeout | `TIMEOUT` | Fail closed, deadline |
| Read timeout | `TIMEOUT` | Fail closed, bounded retry |
| TLS hostname mismatch | `TLS_ERROR` | Never bypass TLS check |
| 200 + `active="true"` | `PROTOCOL_ERROR` | Never treat string as boolean |
| 200 + missing `active` | `PROTOCOL_ERROR` | Never default to active |
| 200 + HTML login page | `WRONG_ENDPOINT/PROTOCOL_ERROR` | Do not create principal |
| Different V1/V2 RS secret across two pods | `CONFIG_DRIFT` | Report error per instance |
| Cached `active=true` stale after revocation | `CACHE_FRESHNESS` | Follow TTL/revocation policy |
| Timeout cached as `active=false` | `INVALID_ERROR_CACHING` | Never conflate dependency failure with token failure |

Separate test layers:

1. **Introspection HTTP client contract:** simulate HTTP statuses, JSON, network, and TLS.
2. **Resource Server integration:** requests pass through `BearerTokenAuthenticationFilter`, `OpaqueTokenAuthenticationProvider`, and a real/stubbed introspector.
3. **Authorization tests:** verify whether an active principal has the required scopes and resource permissions.

A test that merely mocks an authenticated principal **does not prove** upstream credentials and network error handling were tested.

## 21. When many users simultaneously see `invalid_token`

A sample incident:

~~~text
10:00 System operating normally.
10:05 AS rotates introspection client secret.
10:06 RS has not received the new secret yet.
10:07 500 users report the API returns 401.
10:08 Frontend refreshes tokens automatically, still gets 401.
~~~

Diagnose in order:

1. **Is the AS returning HTTP 200 + `active=false`?** If not, do not blame user tokens prematurely.
2. **Is upstream returning `401 invalid_client`?** Check introspection secret and auth method.
3. **Is the error global or isolated to specific RS replicas?** Check for config drift.
4. **Was the introspection client disabled or stripped of permissions?**
5. **Does the endpoint match the right realm/tenant?**
6. **Is a reverse proxy preserving HTTP `Authorization` and mTLS policy?**
7. **Are there TLS/DNS/timeout/5xx errors instead of an AS authentication rejection?**
8. **How is the framework mapping introspection failures to client-facing 401s?**
9. **After fixing the secret, do unexpired existing tokens introspect as active again?**
10. **Are there cached error entries needing invalidation?**

Never force users to sign out en masse to work around **an expired Resource Server credential**.

## 22. Checklist for implementing a safe error contract

For a protected opaque-token endpoint, verify:

1. Is the hop A Bearer token syntactically valid?
2. Does the introspection endpoint belong to a trusted AS via static config or allowlist?
3. Does the RS use credentials/methods permitted to introspect?
4. Does the AS return a valid response containing a boolean **`active`** field?
5. When **`active=false`**, do you reject the credential without leaking sensitive reasons?
6. On upstream HTTP 401/403, do you alert configuration/IAM rather than labeling tokens invalid?
7. On HTTP 429/5xx, do you apply bounded retries and appropriate failure mapping?
8. On timeout/TLS/DNS errors, do you fail closed and preserve the infrastructure error cause?
9. When **`active=true`**, do you check resource binding, scopes, and domain permissions?
10. Do metrics separate upstream status from client-facing status?
11. Does any cache policy align with token expiration and revocation SLAs?
12. When the dependency is unavailable, is the response behavior explicitly designed and tested?
13. Are raw access tokens, Basic credentials, and client secrets kept out of logs and error bodies?
14. Do secret rotation and AS availability have clear owners and alerts?
15. Is no custom Bearer filter silently overwriting a valid `Authentication`?

## 23. Common mistakes

| Mistake | Risk | Right approach |
|---|---|---|
| Catching every exception and throwing `invalid_token` | Masks AS outages and config bugs | Classify by protocol vs. transport |
| Hop B returning 401 always producing hop A 401 | Blames clients when RS secret is wrong | Keep the two HTTP hops distinct |
| Defaulting to `active=true` on AS timeout | **Authentication bypass** | Fail closed |
| Retrying `401 invalid_client` indefinitely | Never fixes credentials, overloads AS | Fix IAM/secret/method |
| Retrying `200 active=false` until `active=true` | Defeats AS semantics | Reject credential |
| Disabling TLS verification to "fix" errors | Breaks trust in AS | Fix trust/certificate/hostname |
| Using a public OAuth client as introspection client | Lacks proper confidential credentials | Provision an RS client with introspection rights |
| Treating `200 active=true` as valid for every API | Token may have wrong audience/scope | Enforce token/resource contract |
| Caching timeouts as inactive tokens | Continues falsely rejecting after AS recovers | Never cache dependency failures as token state |
| Caching `active=true` indefinitely | Revoked tokens stay usable | Use bounded TTLs and invalidation |
| Logging raw tokens and Basic headers | Leaks Bearer tokens and RS secrets | Sanitized observability |
| Using only `@ControllerAdvice` for filter errors | Exceptions can fire before MVC | Handle at the Security filter boundary |
| Parsing opaque tokens locally as JWTs | Tokens lack JWT guarantees | Use introspection |
| Letting opaque tokens pick the introspection URL | SSRF / trust confusion | Endpoint allowlist |
| Treating upstream 403 as caller missing scope | Confuses RS introspection rights with domain auth | Classify by hop |

## 24. Conclusion and references

Three distinct cases to remember:

~~~text
(A) AS returns HTTP 200 + {"active":false}
    -> Token is inactive.
    -> Caller credential is rejected.

(B) AS returns HTTP 401/403 on POST introspection
    -> RS has an issue with client credentials or introspection permission.
    -> No verdict yet on whether the token is active.

(C) AS fails to return a trusted response (network/TLS/5xx/malformed)
    -> Dependency/protocol error.
    -> No verdict yet on whether the token is active.
~~~

A secure opaque-token Resource Server must **fail closed** in all three cases when token validity has not been proven, while **preserving the error cause** so it can return accurate responses and fix the right component.

**Final principles:**

- **`active=false` from a valid introspection response is a token-state verdict.**
- **HTTP 401/403 from the AS is an RS-to-introspection credential/permission failure, not proof that the caller's token is bad.**
- **Timeouts, TLS, DNS, 429, 5xx, and malformed JSON are dependency/protocol errors, not `active=false`.**
- **The Resource Server must never fail open**, nor collapse every failure into `invalid_token`.
- **Returning 503 during an AS outage requires proper error translation at the Security filter boundary**, never assuming it happens automatically.
- **Scopes and business permissions are checked after a token is active**, never using `active=true` as an access pass.
- **Retries, caching, and secret rotation must have strict bounds and policies** that preserve trust boundaries.
- **Observe the two HTTP hops separately**, keeping tokens and credentials out of logs.

### Foundational references

- **RFC 7662 — OAuth 2.0 Token Introspection:** introspection request/response, boolean `active`, and endpoint authentication. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** presenting access tokens and Bearer error semantics. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client authentication, access tokens, and OAuth errors. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7009 — OAuth 2.0 Token Revocation:** token revocation and token lifecycle. https://www.rfc-editor.org/rfc/rfc7009
- **Spring Security Reference — Opaque Token Resource Server (Servlet):** configuring introspection and opaque-token authentication. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Resource Server:** filters/providers and Bearer authentication handling. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security API — `OpaqueTokenIntrospector`:** token introspection contract. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html
- **Spring Security API — `BadOpaqueTokenException`:** rejected token exception. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html
- **Spring Security API — `OAuth2IntrospectionException`:** general introspection exception. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OAuth2IntrospectionException.html
