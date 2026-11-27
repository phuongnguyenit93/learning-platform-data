# Distinguishing HTTP 400, 401, and 403 in the Bearer Flow

## 1. Goal: Understand the Error Properly Before Fixing JWTs or Permissions

In **Spring Security OAuth 2.0/OIDC Resource Server**, clients usually call an API with an access token:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer ACCESS_TOKEN
~~~

When a request fails, three HTTP status codes are easily confused: **400 Bad Request**, **401 Unauthorized**, and **403 Forbidden**. They do not describe the same problem.

- **400**: the request uses the Bearer mechanism in an improper format, or the HTTP request has an input error unrelated to authentication. In RFC 6750, the typical Bearer error is **invalid_request**.
- **401**: the Resource Server does not yet have an accepted credential to authenticate the caller. The token may be missing, expired, have a bad signature, wrong issuer/audience, or be revoked. The Bearer error is usually **invalid_token** when a token was presented but is invalid.
- **403**: the credential was accepted, but the caller is not permitted to perform the action according to OAuth scopes or business policies. The typical Bearer error when lacking a scope is **insufficient_scope**.

Mental model:

~~~text
Request sent to Resource Server
           |
           v
Is the Bearer credential format valid?
  No -> 400 invalid_request (typical case)
           |
           v
Is the credential authenticated?
  No -> 401 (possibly invalid_token)
           |
           v
Does the authenticated token have sufficient permissions?
  No -> 403 (possibly insufficient_scope)
           |
           v
Does the domain policy allow the object/tenant?
  No -> 403 or corresponding domain policy
           |
           v
Allow request
~~~

The diagram illustrates logic, not a claim that every servlet filter runs in that exact order. CSRF, CORS, gateways, multiple SecurityFilterChains, and custom handlers can also return 400/401/403.

**Principle:** distinguish **credential submission errors**, **credential acceptance errors**, and **action authorization errors**. A single status code alone does not reveal the full cause.

## 2. RFC 6750: Three Bearer Error Codes to Remember

RFC 6750 specifies OAuth 2.0 Bearer token presentation and related error codes.

| Bearer error | Meaning | Typical HTTP status |
|---|---|---|
| **invalid_request** | Invalid Bearer credential presentation, missing/malformed required parameter, invalid use of multiple credential transmission methods | **400 Bad Request** |
| **invalid_token** | Token expired, revoked, malformed, or not accepted by the Resource Server | **401 Unauthorized** |
| **insufficient_scope** | Access token lacks the scope required for the requested resource | **403 Forbidden** |

Examples:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

These pairs are **common patterns aligned with RFC 6750**, not absolute guarantees for every implementation. For example, a syntactically malformed Bearer header may be described by Spring Security's **DefaultBearerTokenResolver** with **invalid_token** and status 401 instead of invalid_request 400. To be certain, you need to know which **BearerTokenError** the resolver creates.

### HTTP Status vs. Bearer Error

The **HTTP status** describes the request outcome at the HTTP layer. The **Bearer error code** explains the specific error under the Bearer authentication scheme. A **JSON body**, if present, is an additional API contract.

For instance, a 400 caused by an invalid JSON body does not mean there is a Bearer invalid_request error. Likewise, a 403 because a user lacks tenant membership does not necessarily carry insufficient_scope.

## 3. What Does the WWW-Authenticate Header Say?

A response when the caller has not provided authentication information may only contain:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

An **error** field is not necessarily present. RFC 6750 recommends that when a request **contains no authentication information**, the Resource Server should not include an error code or error description, because no token has been submitted to judge invalid.

When a token has been presented but is not accepted:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

When a token is valid but lacks scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Parameters to know:

| Parameter | Role |
|---|---|
| **Bearer** | RFC 6750 HTTP authentication scheme |
| **realm** | Name of the protection scope; not the token's issuer |
| **error** | Bearer code such as invalid_request, invalid_token, insufficient_scope |
| **error_description** | Short, safe description, if provided by the server |
| **error_uri** | URI to documentation describing the error |
| **scope** | For insufficient_scope, may describe the additional scope needed |

**Do not log and do not return the raw access token** in error_description. Never include private signing keys, introspection secrets, stack traces, issuer key material, or other users' membership information in the response.

WWW-Authenticate is especially helpful for the client to know whether it needs a **new credential** or **new permissions**. If a custom handler returns a JSON body but accidentally drops the required Bearer challenge, the API can break standards-compliant clients.

## 4. HTTP 400: Malformed Bearer Request

A classic case of **invalid_request** is when the caller supplies the token via **multiple methods at the same time**.

Example to avoid:

~~~http
POST /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer TOKEN_A
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN_B&quantity=1
~~~

If the Resource Server is configured to accept both header and form body, it must avoid arbitrarily picking token A or B. Per RFC 6750, using more than one method to transmit a token is an **invalid_request** error, typically 400.

Some improper Bearer presentations:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer
~~~

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer TOKEN_A,TOKEN_B
~~~

~~~http
GET /api/orders?access_token=TOKEN_IN_QUERY HTTP/1.1
Authorization: Bearer TOKEN_IN_HEADER
~~~

**Implementation note:** the situations above do not automatically all return 400 in Spring Security. DefaultBearerTokenResolver uses the header by default; query/form parameters are not enabled out of the box, and a malformed header token may be represented by the parser as **invalid_token**. Verify against your actual configuration.

### Query Strings Containing Access Tokens Are a Risky Choice

Bearer tokens in URLs can leak through history, proxy logs, HTTP referrers, analytics, browser caches, or monitoring. Spring Security normally disallows URI query tokens by default. Clients should use:

~~~http
Authorization: Bearer ACCESS_TOKEN
~~~

Do not enable URI query tokens just to fix a 401 caused by the frontend forgetting to add the Authorization header.

### Do Not Confuse JSON Validation 400 with Bearer invalid_request

Example:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer VALID_TOKEN
Content-Type: application/json

{"quantity": -3}
~~~

If the API requires a positive quantity, Spring MVC/Bean Validation may return **400**, even though the Bearer token is completely valid. This is **input validation**, not Bearer invalid_request.

| Reason for 400 | Processing Layer | Is it a Bearer error? |
|---|---|---|
| Sending token via multiple methods against policy | BearerTokenResolver | Possibly invalid_request |
| Conflicting Bearer credential parameters | BearerTokenResolver | Possibly invalid_request |
| Malformed JSON body syntax | MVC JSON parser | No |
| Domain form missing required field | MVC/application validation | No |
| Business query parameter has wrong type | Request binding | No |
| Gateway rejects oversized request | Proxy/container | Not necessarily |

## 5. HTTP 401: Missing or Unaccepted Credential

HTTP 401 is the common outcome when a request requires authentication and **lacks valid authentication**.

Scenarios:

1. Endpoint is protected but request lacks a Bearer credential.
2. JWT is expired per **exp**.
3. JWT is not yet valid per **nbf**.
4. JWT signature is invalid.
5. JWS algorithm is not on the allow-list.
6. JWT **iss** differs from the issuer trusted by the API.
7. JWT **aud** is not intended for the Resource Server.
8. Token is an OIDC ID token or wrong-purpose JWT assertion, not an appropriate access token.
9. Token has been revoked or marked invalid per policy.
10. Opaque token introspection returns **active=false**.
11. Another credential is presented, but there is no valid authentication mechanism for the route.

### 5.1. Missing Bearer Token

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
~~~

If the route requires authentication, typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Do not attach **invalid_token** manually if no token was actually evaluated.

A **permitAll** endpoint may return 200 for the same request without a token. **Missing a token does not always mean 401**, because route policy determines whether authentication is required.

### 5.2. JWT Present but Token Invalid

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer EXPIRED_OR_INVALID_JWT
~~~

If JwtDecoder does not accept the credential, typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

A JWT with **scope=orders.admin** but an invalid signature must still **never be used to grant permissions**. A token payload can be Base64URL-decoded without verification; those untrusted claims must never enter the SecurityContext as an authenticated principal.

### 5.3. Valid Signature but Wrong Issuer or Audience

Example:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

Even though the JWT signature matches the issuer's key, **orders-api** must not accept a token issued for **billing-api**. If the audience validator requires aud to contain orders-api, this is a **token contract failure**, typically **401 invalid_token**.

It is **not** a 403 insufficient_scope error just because the scope in the token looks appropriate.

### 5.4. An ID Token Is Not an Access Token

An OIDC ID token is meant for the **OIDC Client/Relying Party** to confirm a login result. A Resource Server requires an access token targeted to the API's audience. Sharing the same issuer/JWKS does not turn an ID token into an access token.

If the API's token profile requires **RFC 9068** and **typ=at+jwt**, or a provider-specific classification claim, check the exact contract. The wrong token type is an **acceptance/authentication** failure, not a post-authentication missing-permission error.

## 6. HTTP 403: Authenticated but Insufficient Permissions

A token accepted by the Resource Server:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

If the endpoint **POST /api/orders** requires **orders.write**, the caller lacks sufficient scope.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

**insufficient_scope** describes the situation where an access token lacks the permission scope required by the resource. The scope parameter can help the client know which scope needs to be granted by the AS, though sensitive permissions/domain policies should not be leaked uncontrollably.

### 6.1. Not Every 403 Is insufficient_scope

Even when a token has **orders.write**, the domain may still deny access:

- Actor lacks current tenant membership.
- Order belongs to another user or organization.
- Resource is locked/approved and cannot be updated.
- Action violates workflow rules.
- Service principal is not allowed to perform a user-only action.
- Permissions were revoked after the access token was issued.

Example:

~~~text
JWT signature/issuer/audience/expiry: valid
Token scope: orders.write
User's tenant membership: REVOKED
Requested operation: PUT /api/orders/42

=> Authentication may succeed.
=> Domain authorization denies access.
=> Usually 403; not necessarily insufficient_scope.
~~~

An API may use domain-specific error codes in the JSON response while preserving proper HTTP semantics.

### 6.2. 403 Does Not Automatically Prove the Caller Was Authenticated

In Spring Security, **CsrfFilter**, CORS handling, WAF, or a reverse proxy can also return 403 when the caller has no Bearer authentication. Therefore, the saying "403 means the user is logged in" is only a rule of thumb for the **typical authorization path**, not an absolute law for every HTTP response.

To know why a 403 occurred, check **which filter/handler returned the response** and **whether an Authentication was created**.

## 7. Comparison Table of 400, 401, and 403

| Situation | Credential Accepted? | Failing Step | Typical HTTP |
|---|---|---|---|
| No Bearer token on protected endpoint | No | Authentication required | **401** |
| JWT expired | No | JwtDecoder/time validation | **401 invalid_token** |
| JWT signature invalid | No | JWS verification | **401 invalid_token** |
| JWT wrong issuer | No | Issuer validation | **401 invalid_token** |
| JWT wrong audience | No | Audience validation | **401 invalid_token** |
| ID token used as access token, blocked by profile check | No | Token purpose | **401 invalid_token** |
| Opaque introspection active=false | No | Token introspection | **401 invalid_token** |
| Token sent via multiple disallowed sources | Undetermined | BearerTokenResolver | **400 invalid_request** when enforced by resolver |
| Malformed Bearer header | Undetermined | BearerTokenResolver | **400 or 401**, depending on resolver error code |
| Active token lacking orders.write | Yes | Scope authorization | **403 insufficient_scope** |
| Active token with scope but wrong tenant | Yes | Domain authorization | **403** or another policy |
| Active token, invalid JSON body | Possibly yes | Input validation | **400** (not a Bearer error) |
| Active token, POST rejected by CSRF filter | Not necessarily | CSRF | **403**, not necessarily missing scope |
| CORS preflight rejected | Not necessarily | CORS/gateway | Possibly **403** |
| Opaque introspection AS returns 401 due to wrong RS secret | Unknown | Upstream credentials | Dependency failure; do not conclude token is invalid |
| Opaque introspection AS timeout | Unknown | Network/AS | Dependency failure; fail closed |
| permitAll route without token | Not needed | Public policy | Possibly **200** |
| Non-existent URL | Depends on chain | Routing | Possibly **404** |
| Unsupported HTTP method | Depends on chain | Routing | Possibly **405** |

**Status codes must be interpreted in their actual processing context.** Relying solely on a table without knowing the SecurityFilterChain and error handlers can lead to misdiagnosis.

## 8. Where Does DefaultBearerTokenResolver Extract Tokens From?

**DefaultBearerTokenResolver** in Spring Security typically reads the token from the **Authorization header**. Form body and query parameter mechanisms are not enabled by default.

Example configuration using header only:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);

    return resolver;
}
~~~

When wiring the resolver:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenResolver(bearerTokenResolver())
        .jwt(Customizer.withDefaults()))
~~~

**Do not assume** a URI with **?access_token=...** will be treated by Spring as a credential. If the resolver does not allow query tokens, that parameter may not be viewed as a Bearer token source.

### Does a Malformed Header Always Return 400?

No. For certain malformed syntaxes, Spring Security may produce a **BearerTokenError** with code **invalid_token** and status **401**. Using **two token submission methods** when multiple sources are allowed, on the other hand, can produce **invalid_request** and status **400**.

Therefore:

- RFC 6750 defines the semantics of error categories.
- Spring Security determines the **specific BearerTokenError** per resolver/implementation.
- Real tests must verify the status and challenge for your active configuration.

### Multiple Authorization Headers

Proxies or Servlet containers may handle duplicate headers differently: keeping multiple values, taking the first value, or merging them. Do not assume DefaultBearerTokenResolver catches every duplicate scenario. In sensitive systems, enforce a consistent policy at the edge and write integration tests for HTTP header duplication so proxies and the app never pick different credentials.

## 9. Servlet Resource Server Flow and Error Origins

~~~mermaid
sequenceDiagram
    participant Client
    participant F as BearerTokenAuthenticationFilter
    participant R as BearerTokenResolver
    participant P as AuthenticationProvider
    participant D as JwtDecoder / Introspector
    participant A as AuthorizationFilter
    participant E as EntryPoint / DeniedHandler

    Client->>F: Request with or without Bearer
    F->>R: resolve(request)
    alt Invalid Bearer request
      R-->>F: BearerTokenError / auth exception
      F->>E: Authentication failure
      E-->>Client: 400/401 depending on BearerTokenError
    else Missing token
      R-->>F: null
      F->>A: No Bearer authentication created
      A->>E: Protected endpoint requires auth
      E-->>Client: 401 challenge
    else Bearer token extracted
      R-->>F: raw token
      F->>P: BearerTokenAuthenticationToken
      P->>D: decode or introspect
      alt Token invalid
        D-->>P: Authentication failure
        P-->>F: AuthenticationException
        F->>E: Failure
        E-->>Client: Typical 401 invalid_token
      else Token accepted
        D-->>P: Trusted principal
        P-->>F: Authenticated result
        F->>A: SecurityContext populated
        A->>A: Check authority / scope
        alt Authorization denied
          A->>E: AccessDeniedException
          E-->>Client: Typical 403
        else Authorization succeeds
          A-->>Client: Continue to controller
        end
      end
    end
~~~

This is a **logical responsibility diagram**, not a guarantee that every exception flows through the exact same filter in every Spring Security version.

Key components:

| Class | Responsibility |
|---|---|
| **BearerTokenAuthenticationFilter** | Extracts Bearer and triggers authentication |
| **BearerTokenResolver** | Selects credential source/syntax from request |
| **BearerTokenAuthenticationToken** | Holds unauthenticated raw credential |
| **JwtAuthenticationProvider** | Authenticates JWT via JwtDecoder |
| **OpaqueTokenAuthenticationProvider** | Authenticates opaque token via OpaqueTokenIntrospector |
| **JwtDecoder** | Verifies signature, algorithm, JWT claims validators |
| **OpaqueTokenIntrospector** | Queries AS for token active status and metadata |
| **JwtAuthenticationConverter** | Maps verified JWT into authorities |
| **SecurityContextHolder** | Holds the request's valid Authentication |
| **AuthorizationFilter** | Enforces endpoint security policy |
| **ExceptionTranslationFilter** | Translates certain authentication/access-denied exceptions |
| **BearerTokenAuthenticationEntryPoint** | Builds Bearer challenge on authentication failure |
| **BearerTokenAccessDeniedHandler** | Handles access denial with Bearer semantics |

**Key distinction:** Authentication failures may be handled directly by **BearerTokenAuthenticationFilter** via its failure handler/entry point. Downstream AccessDeniedExceptions are usually routed by **ExceptionTranslationFilter** to the access-denied handler or authentication entry point. Never assume all errors come from controllers.

## 10. AuthenticationException and AccessDeniedException

In Spring Security:

- **AuthenticationException** represents being unauthenticated or having an unaccepted credential.
- **AccessDeniedException** represents failing an authorization requirement.

However, an AccessDeniedException on an **anonymous/unauthenticated** request may be translated by ExceptionTranslationFilter to the authentication entry point (usually **401**). If an authenticated Authentication exists and lacks permissions, it usually goes to **403**.

~~~text
Not authenticated + protected route
  -> AuthenticationEntryPoint
  -> 401

Authenticated + insufficient authority
  -> AccessDeniedHandler
  -> 403
~~~

This does not mean every 403 comes from AccessDeniedHandler, as CSRF/CORS/gateways can produce 403 at other stages.

### Be Careful with SecurityContext

A custom filter that Base64URL-decodes a JWT and sets a principal in SecurityContext **before verifying the signature** can break both 401/403 semantics and security boundaries.

Keep the standard mechanism:

~~~text
BearerTokenAuthenticationToken (unauthenticated)
   -> JwtAuthenticationProvider or OpaqueTokenAuthenticationProvider
   -> verified Authentication
   -> SecurityContext
   -> AuthorizationFilter / method security
~~~

Do not build a parallel JWT filter just to decide 401/403 yourself.

## 11. Illustrative Spring Security JWT Resource Server Configuration

With Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

SecurityFilterChain:

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
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
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

With this configuration and a JWT meeting the token contract:

| HTTP request | Typical status |
|---|---|
| GET /api/orders without token | **401** |
| GET /api/orders with expired JWT | **401 invalid_token** |
| GET /api/orders with orders.read JWT | Can proceed |
| POST /api/orders with orders.read-only JWT | **403** |
| POST /api/orders with orders.write JWT | Can proceed, still depends on domain |
| GET /api/public/help without token | No authentication required per matcher |

**CSRF caveat:** the example disables CSRF only to illustrate a **purely stateless Bearer** API that does not use session/cookie authentication for browser requests. Do not copy a disable-CSRF configuration into an application with cookie-based authentication without evaluating the security model.

**Audience caveat:** declaring issuer-uri alone does not automatically guarantee the access token's audience targets orders-api across all configurations. Appropriate token contracts/validators must be configured.

## 12. Checking Issuer/Audience Before Evaluating Scope

A JWT with:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

must not be used to call **orders-api** if the audience policy requires **orders-api**. Even though the token has the orders.read scope, a wrong audience is an **authentication/token acceptance** error, usually **401**, not 403.

Example JwtDecoder checking issuer and audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com/realms/shop";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                                "Wrong resource audience", null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, audience));

    return decoder;
}
~~~

This code snippet only illustrates issuer/audience validation. The framework also needs to verify signature/algorithm and other **access-token profile** constraints per the AS contract, especially when distinguishing ID tokens from access tokens.

**setJwtValidator(...) replaces the validators currently attached to the decoder**. When adding custom conditions, retain issuer/time and any required profile validators. Never use an audience validator in place of JWT signature or expiration checks.

## 13. Scopes in JWTs and How Spring Security Creates Authorities

A JWT:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

is typically mapped by Spring Security into:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

This explains:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

If the JWT only has orders.read, a POST requiring orders.write usually gets **403**.

### SCOPE_ vs. ROLE_

- **hasAuthority("SCOPE_orders.write")** checks an authority derived from scope.
- **hasRole("ADMIN")** by convention checks the **ROLE_ADMIN** authority.
- A **roles: ["ADMIN"]** claim does not automatically become ROLE_ADMIN under the default scope converter.

If a custom JwtGrantedAuthoritiesConverter replaces the default converter, **SCOPE_...** might not be generated as before. That is an authorization mapping issue leading to 403 even with a valid scope, not an invalid token.

## 14. BearerTokenAuthenticationEntryPoint and BearerTokenAccessDeniedHandler

Two Spring Security extension points:

- **BearerTokenAuthenticationEntryPoint**: returns the authentication challenge, typically on missing/invalid credentials, and can use BearerTokenError to determine status/error.
- **BearerTokenAccessDeniedHandler**: handles access denied in a Bearer Resource Server; can return **insufficient_scope** when authentication has appropriate OAuth2 Bearer semantics.

Example using standard handlers:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain apiErrorHandlers(HttpSecurity http)
        throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .authenticationEntryPoint(
                            new BearerTokenAuthenticationEntryPoint())
                    .accessDeniedHandler(
                            new BearerTokenAccessDeniedHandler())
                    .jwt(Customizer.withDefaults()))
            .build();
}
~~~

This is an example of **handler wiring**, not a full production configuration. In a real application, combine security matchers, CSRF, sessions, issuer, audience, and domain policies.

### Why Not Return 403 for Every Error?

A custom handler like:

~~~java
response.setStatus(403);
~~~

for every exception would make requests with missing tokens, bad signatures, or expired tokens all look like **insufficient permissions**. Similarly, a handler that always returns 401 turns domain authorization denials into **invalid_token**, causing clients to refresh endlessly.

If you want a uniform JSON body, preserve **HTTP status + WWW-Authenticate** according to error semantics; the body should only supplement non-sensitive info.

## 15. Opaque Tokens: Distinguishing Access Token Errors from Introspection Errors

An Opaque Resource Server uses introspection per RFC 7662:

~~~text
Hop A: Client -> orders-api
  Authorization: Bearer OPAQUE_TOKEN

Hop B: orders-api -> Authorization Server
  POST introspection
  Authorization: Basic RS_CLIENT_CREDENTIALS
  token=OPAQUE_TOKEN
~~~

Different outcomes:

| Outcome at Hop B | Meaning | Conclude Token Is Invalid? |
|---|---|---|
| 200 + active=true | AS confirms token is active | No; token may still lack audience/scope |
| 200 + active=false | AS rejects token | **Yes**, per introspection semantics |
| 401 invalid_client | RS credentials wrong/rejected by AS | **Not yet** |
| 403 from AS | RS lacks permission to introspect | Not yet |
| 429/5xx | AS throttled or unavailable | Not yet |
| DNS/TLS/timeout | Network/channel trust failure | Not yet |
| 200 but malformed JSON | Protocol/response failure | Not yet |

**Do not forward a hop-B HTTP 401 directly as an invalid_token error at hop A.** If the introspection client secret expires, the user's token might still be active. This is an RS-to-AS failure requiring fail-closed behavior and proper error mapping, such as **503 Service Unavailable** per application contract.

Do not claim Spring Security always returns 503 by default for AS errors; behavior depends on implementation, exception mapping, entry point, and security chain.

### Why Must It Not Fail Open?

If the AS times out and the API accepts an unverified opaque token:

~~~text
AS unavailable
    -> API skips introspection
    -> Attacker uses fake token
    -> API grants unauthorized access
~~~

Therefore, **protected operations must not proceed** without proof of a valid token. Failing closed does not require returning 401 invalid_token; you can surface a dependency error so operations sees the true cause.

## 16. CSRF and CORS: 403s That Do Not Come from Missing Scope

A POST with a valid Bearer token can still receive 403:

~~~text
CsrfFilter requires a CSRF token for POST
Request lacks CSRF token
    -> 403
~~~

This case should not be fixed by granting more OAuth scopes. In applications using cookie/session authentication, CSRF protection serves a critical purpose. For pure Bearer-header APIs with no ambient browser credentials, CSRF policy may be designed differently, but must match the actual security model.

Similarly, CORS preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization
~~~

Preflight requests usually **do not carry a Bearer token**. If CORS is not handled properly and security requires authentication on OPTIONS, the preflight may fail with 401/403. Inspect the CORS filter/matcher and gateway rather than changing JwtDecoder or the scope converter.

### Why Does GET Return 200 While POST Returns 403?

Possibilities:

1. POST requires **orders.write**, while GET only needs **orders.read**.
2. CSRF protection blocks unsafe HTTP methods.
3. Domain policy forbids modifying resource state.
4. Gateway/WAF has a specific rule for POST.
5. POST is handled by a different SecurityFilterChain.

The same JWT does not guarantee every HTTP method is permitted.

## 17. When Does the Domain Return 404 Instead of 403?

Some APIs intentionally return **404 Not Found** when the caller is not allowed to know whether a resource exists, such as an order belonging to another tenant.

~~~text
GET /api/orders/42
Order 42 belongs to another tenant.
Policy forbids revealing existence.

Response may be 404 per API contract.
~~~

This is a **domain authorization/information-hiding** decision, not a replacement for Bearer token acceptance. An expired JWT must still be rejected at authentication; an introspection outage must never be masked as a 404.

This illustrates that **403 is the typical code for authorization denial**, but not every domain denial necessarily uses 403.

## 18. How Should the Frontend React?

| Outcome | What the Client Should Do | What Not to Do |
|---|---|---|
| 400 invalid_request | Fix header/token transmission method, remove duplicate credentials | Repeatedly refresh tokens while request format remains broken |
| 401 when no token provided | Obtain an access token via the proper flow and retry | Assume a missing token means it was revoked |
| 401 invalid_token | Check expiry/issuer/audience, obtain a valid token via allowed flow | Manually edit JWT payload or retry infinitely with the same token |
| 403 insufficient_scope | Request consent/scope/role if AS and product allow; or show insufficient permissions | Refresh infinitely with the same grant |
| 403 domain policy | Display action not permitted | Try a token from another API to bypass |
| 400 input validation | Fix business JSON/body/query | Modify unrelated OAuth tokens |
| 503 due to introspection outage | Bounded backoff/retry per contract, report dependency unavailable | Log out all users assuming tokens are invalid |

**401 does not automatically mean refresh the token immediately.** If the JWT has the wrong audience/issuer, refreshing from the same source may keep failing. If backend introspection credentials are wrong, client refreshes will not help.

**403 does not automatically mean refreshing the token will grant permissions.** If the AS has not granted the scope or the user is not authorized, the client must follow a valid permission-grant flow or stop the action.

## 19. Custom JSON Errors: Preserve Status and Challenge

An API contract may add a JSON body:

~~~json
{
  "code": "ACCESS_TOKEN_INVALID",
  "message": "The access token cannot be accepted",
  "requestId": "req-1042"
}
~~~

Codes like **ACCESS_TOKEN_INVALID** are only application-defined examples, **not RFC Bearer error codes**.

An illustrative mapping:

| Error Source | HTTP | WWW-Authenticate | Internal Body Code |
|---|---|---|---|
| Invalid Bearer transport | 400 per resolver | Bearer invalid_request when appropriate | BEARER_REQUEST_INVALID |
| Route requires auth but no token | 401 | Bearer, error not required | AUTHENTICATION_REQUIRED |
| Rejected JWT/opaque token | 401 | Bearer invalid_token | ACCESS_TOKEN_INVALID |
| Active token missing scope | 403 | Bearer insufficient_scope | INSUFFICIENT_SCOPE |
| Active token violates domain policy | 403 | Not necessarily insufficient_scope | ACCESS_DENIED |
| AS introspection unavailable | 503 per contract | Do not blame invalid token | AUTH_DEPENDENCY_UNAVAILABLE |
| Invalid HTTP input body | 400 | Not a Bearer challenge | INPUT_VALIDATION_FAILED |

**Not every 400 needs WWW-Authenticate**, especially when the error is MVC input validation.

### Why Is @ControllerAdvice Not Enough?

BearerTokenAuthenticationFilter and many Spring Security filters run before Spring MVC controllers. Exceptions from them may be handled by a failure handler or AuthenticationEntryPoint rather than passing through **@ControllerAdvice**.

To customize properly:

- Separate Bearer transport, authentication, and authorization errors.
- Use handlers/entry points at the Security filter boundary when appropriate.
- Preserve HTTP status and Bearer challenges.
- Never write raw tokens/secrets to the body.
- Test end-to-end through the SecurityFilterChain.

## 20. State Machine for Classifying Errors

~~~mermaid
flowchart TD
    A["HTTP request arrives at API"] --> B{"Valid Bearer transport?"}
    B -- "No" --> BAD["invalid_request / resolver-specific error"]
    B -- "Yes" --> C{"Required credential present?"}
    C -- "No" --> NO["401 Bearer challenge if route is protected"]
    C -- "Yes" --> D{"Token accepted?"}
    D -- "No" --> INVALID["Typical 401 invalid_token"]
    D -- "Yes" --> E["Authenticated principal"]
    E --> F{"Sufficient scope/authority?"}
    F -- "No" --> SCOPE["403 insufficient_scope when appropriate"]
    F -- "Yes" --> G{"Domain policy allows?"}
    G -- "No" --> DENY["403 or policy-specific denial"]
    G -- "Yes" --> OK["Proceed"]
~~~

The diagram does not yet depict **CSRF/CORS/AS dependency errors/gateways**; those can produce errors at other layers and must be diagnosed independently.

## 21. 400/401/403 Test Scenario Suite

The test cases below are **design expectations**, not executed test results.

| Test case | Expectation |
|---|---|
| Protected GET without Authorization header | 401 Bearer challenge |
| Expired JWT | 401 invalid_token |
| Invalid JWT signature | 401 invalid_token |
| Wrong JWT issuer | 401 invalid_token |
| Wrong JWT audience | 401 invalid_token |
| ID token used as access token, rejected by profile validator | 401 |
| Opaque introspection active=false | 401 |
| Duplicated Bearer transport blocked by resolver | invalid_request/status per contract |
| Malformed Bearer header | Check actual resolver BearerTokenError |
| Valid token with orders.read only calling POST requiring orders.write | 403 insufficient_scope when appropriate |
| Valid token with write but revoked tenant membership | Domain denial, usually 403 |
| Valid token but invalid JSON body | 400 input validation |
| POST blocked by CSRF filter | 403 from CSRF, not scope |
| Misconfigured CORS OPTIONS preflight | Possibly 401/403 from CORS/security |
| Opaque introspection 401 invalid_client | Do not treat caller token as invalid |
| AS introspection timeout | Fail closed, dependency failure |
| permitAll route without token | Must not force 401 |
| Valid token, sufficient permissions, domain object allowed | Not blocked by auth/authz |

### Tests Must Target the Right Layer

**BearerTokenResolver unit tests**: header syntax, duplicate credentials, query/form policy, and exceptions.

**JwtDecoder/opaque introspector tests**: signature, issuer, audience, expiration, token purpose, active=false, upstream errors.

**SecurityFilterChain integration tests**: genuinely traverse BearerTokenAuthenticationFilter/entry point/denied handler to verify HTTP status, headers, and absence of authentication when tokens are invalid.

**Domain authorization tests**: missing ownership/membership, resource status, and per-tenant permissions.

Spring Security Test's **jwt()** request post-processor can create a fake authentication for authorization tests; it can **bypass the real JwtDecoder**. Thus a test using jwt() is not enough to prove production signature/issuer/audience verification works.

### Do Not Check Only the Status Code

When testing the error contract, assert:

- HTTP status.
- WWW-Authenticate scheme and Bearer error (when required by contract).
- No access tokens or secrets in the response.
- No successful Authentication created when the token is invalid.
- No domain service invoked when authentication has not succeeded.
- No insufficient_scope assigned to tokens with wrong issuer/audience.
- No confusion between AS introspection errors and invalid tokens.
- Custom handlers do not drop challenges or change status codes incorrectly.

## 22. Troubleshooting Unexpected Status Codes

### 22.1. No Token, Yet API Returns 403

Possible causes:

- CsrfFilter rejects before authentication.
- CORS/gateway blocks the request.
- Custom handler always returns 403.
- Wrong SecurityFilterChain matcher.
- Anonymous request translated under an unexpected configuration.
- Custom filter writes SecurityContext incorrectly.

**How to handle:** inspect filter chain, matchers, CSRF/CORS, entry point, and authentication state. Do not rush to change JWT scopes.

### 22.2. JWT Has the Right Scope, Yet API Returns 401

Possible causes:

- JWT is expired or not yet valid.
- Bad signature, JWKS rotation/cache out of sync.
- Wrong Issuer URI, including path/realm/trailing slash.
- Wrong audience.
- Token is an ID token or another token type.
- Malformed Bearer header.
- Opaque introspection active=false.
- Misconfigured AS introspection mistakenly mapped to invalid_token.

**Scope does not replace token acceptance.** Only after the Resource Server has verified the token does scope become a trusted authority for authorization.

### 22.3. Valid JWT, Yet API Returns 403

Possible causes:

- Missing scope/authority required by endpoint.
- **SCOPE_** vs. **ROLE_** mapping differs from expectations.
- Custom JwtGrantedAuthoritiesConverter dropped scopes.
- Domain policy denies tenant/owner/order status.
- Blocked by CSRF or CORS.
- Gateway or WAF returns 403.

Read the cause from the handler or policy; never conclude from the status code alone.

### 22.4. All Requests Suddenly Return 401 After Deployment

If using opaque tokens, check the **RS → AS introspection** HTTP status. Upstream 401 **invalid_client** suggests wrong client ID/secret/mTLS credentials. For JWTs, check issuer URI, JWKS, algorithm, and validators.

Do not force all users to log out and log back in when the API itself is using the wrong introspection secret.

### 22.5. GET Works, Yet POST Returns 403

Check:

- Does GET require orders.read while POST requires orders.write?
- Is CSRF enabled for POST?
- Is POST forbidden by domain policy?
- Are there multiple SecurityFilterChains?
- Is there a method-specific proxy/WAF rule?

Not every difference between GET and POST is related to scope.

## 23. Common Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Return 401 for every error | Hides request/authorization errors | Separate 400/401/403 layers |
| Return 403 for every error | Client doesn't know a token is needed | Return 401 when authentication is required/failed |
| Always force malformed headers to 400 | Doesn't match resolver implementation | Use BearerTokenError and test actual behavior |
| Missing scope → invalid_token | Confuses authorization with authentication | 403 insufficient_scope when appropriate |
| Wrong audience → insufficient_scope | Mistakenly accepts another API's token | Reject at token acceptance |
| Missing token → invalid_token | No token present to evaluate | 401 challenge without error if appropriate |
| AS introspection 401 → caller token invalid | Confuses two HTTP hops | Distinguish RS-to-AS credentials |
| AS timeout → allow opaque token | Bypasses authentication | Fail closed |
| Domain 403 always tagged insufficient_scope | Wrong semantics and may leak policy | Appropriate domain error/403 |
| Log raw Bearer tokens | Leaks credentials | Sanitized logs and request IDs |
| Enable query access_token to fix 401 | Token can leak via URL | Use Authorization header |
| Blindly disable CSRF to fix 403 | Creates risk for cookie endpoints | Choose CSRF policy based on trust model |
| Custom JWT filter manually creates Authentication | Bypasses JwtDecoder or overwrites SecurityContext | Keep standard Resource Server |
| Handle errors only in @ControllerAdvice | Misses errors from security filters | Use security entry point/denied handler |
| 403 → frontend refreshes token infinitely | Allowed grant may not exist | Respect authorization contract |
| JSON error body replaces all WWW-Authenticate | Client loses challenge semantics | Keep proper status/headers |

## 24. Decision Checklist Before Returning an Error

When seeing a Bearer error, answer these questions:

1. Did the request enter the right SecurityFilterChain?
2. Is there a Bearer credential from an accepted source?
3. Did BearerTokenResolver report a format/duplicate-credential error?
4. Was the token validated by JwtDecoder or introspector?
5. Are the JWT signature, issuer, audience, lifetime, and token purpose valid?
6. For opaque tokens, did the AS return **active=false** or was there an upstream AS/credentials error?
7. Was an Authentication created in SecurityContext?
8. Which scope/authority does the endpoint require?
9. Does domain policy allow the actor for the tenant/resource?
10. Was the status produced by Spring Security, MVC, CSRF, CORS, or a gateway?
11. Does WWW-Authenticate still reflect the proper Bearer error?
12. Do responses/logs leak Bearer tokens, secrets, or internal authorization data?

These questions help isolate the actual error instead of guessing status codes or tweaking JWTs intuitively.

## 25. Summary

~~~text
400 BAD REQUEST
  Request presents Bearer credential with invalid method/structure
  -> invalid_request in applicable RFC 6750 cases
  Or business request input error in MVC, not a Bearer error.

401 UNAUTHORIZED
  Caller lacks a credential accepted by the Resource Server.
  -> Missing token: Bearer challenge.
  -> Invalid token: typically invalid_token.

403 FORBIDDEN
  Caller is authenticated, but the action is not permitted.
  -> Missing OAuth scope: insufficient_scope when semantically accurate.
  -> Domain policy denial: 403 or domain-specific response.
~~~

**Remember three key principles:**

1. **Classify by error layer, not just status.** BearerTokenResolver, JwtDecoder, introspector, AuthorizationFilter, domain service, CSRF/CORS, and gateways can produce different responses.
2. **Preserve the authentication vs. authorization boundary.** A token with wrong issuer/audience/signature must never be treated as authenticated and handled as missing scope.
3. **Keep Bearer challenges safe.** HTTP status, WWW-Authenticate, and error descriptions must match semantics without leaking tokens or secrets.

A well-designed Resource Server does not just return the right **400/401/403**; it helps clients handle errors accurately, helps operations pinpoint root causes, and never trades away security for “nicer-looking” status codes.

## 26. References

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** token transmission, WWW-Authenticate, invalid_request, invalid_token, and insufficient_scope. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 9110 — HTTP Semantics:** meanings of HTTP 400, 401, 403, and authentication challenges. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 6749 — OAuth 2.0 Authorization Framework:** access tokens and scopes. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7519 — JSON Web Token:** iss, sub, aud, exp, and registered claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices:** issuer/audience, algorithm validation, and token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token purpose and profile. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque token active/inactive and response semantics. https://www.rfc-editor.org/rfc/rfc7662
- **Spring Security — OAuth 2.0 Resource Server (Servlet):** Bearer authentication architecture. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security — JWT Resource Server:** decoder, validators, and authorities. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security — Opaque Token Resource Server:** token introspection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security API — DefaultBearerTokenResolver:** configuring Bearer credential sources. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html
- **Spring Security API — BearerTokenAuthenticationEntryPoint:** Bearer challenge. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html
- **Spring Security API — BearerTokenAccessDeniedHandler:** handling access denied in Bearer context. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html
