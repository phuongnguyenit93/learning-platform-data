# invalid_request, invalid_token, and insufficient_scope

In **Spring Security OAuth 2.0 / OIDC Resource Server**, an HTTP request using a Bearer Access Token can fail for very different reasons: the client sent malformed credentials, the token is no longer trusted, or the token is valid but lacks permission to call the endpoint. Three standard error codes from **OAuth 2.0 Bearer Token Usage — RFC 6750** express these situations:

- **`invalid_request`**: the way the client **sent the Bearer token in the request** violates the rules.
- **`invalid_token`**: a Bearer credential was sent, but **cannot be accepted as a valid token**.
- **`insufficient_scope`**: the token was authenticated, but **lacks the required permission scope** for the resource or operation.

Distinguishing these three situations properly is crucial: the client knows whether to fix the request, obtain a new token, or request additional permissions; the API returns the right HTTP status; operations does not confuse JWT configuration errors with missing scopes; and the system does not accidentally turn a bad token into a logged-in user.

This lesson explains in detail **HTTP statuses, `WWW-Authenticate` challenges, the `error`, `error_description`, `error_uri`, `realm`, and `scope` parameters**, the processing flow in **Spring Security 6.x**, examples with **JWT and opaque Access Tokens**, protecting error responses, and key tests. Examples use **Spring Boot 3.x, Java 17+, and Servlet Resource Server**. All hostnames and tokens are illustrative only.

## 1. Context: Who Returns the Error and at Which Step?

Suppose a client calls an API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

The Resource Server must pass through several decisions:

~~~text
HTTP request
     |
     v
1. Extract Bearer token from request
     |-- header/scheme breaks rules?
     |     -> invalid_request
     v
2. Validate Bearer token
     |-- JWT: signature, iss, aud, exp, nbf...
     |-- Opaque: introspection, active, metadata...
     |-- token invalid?
     |     -> invalid_token
     v
3. Build authenticated Authentication
     |-- principal, authorities (SCOPE_...)
     v
4. HTTP/method authorization
     |-- missing authority/scope?
     |     -> insufficient_scope or access denied
     v
5. Domain authorization
     |-- wrong tenant, owner, account status?
     |     -> 403/404 per business policy
     v
Controller / Service
~~~

**A JWT with a valid signature can still be rejected for lacking permissions.** Conversely, a JWT claiming `scope: "admin.manage"` with an invalid signature must never reach the authorization step. OAuth 2.0 Bearer errors must sit squarely on the **request parsing → authentication → authorization** boundaries.

| Layer | Data Checked | Related Error |
| --- | --- | --- |
| **Bearer token resolution** | Authorization header, token transport method, number of token sources. | `invalid_request` when Bearer request format is invalid. |
| **Token authentication** | JWT signature, issuer, audience, lifetime; or introspection status. | `invalid_token`. |
| **Scope/authority authorization** | `SCOPE_orders.read`, `SCOPE_orders.write`, permitted roles. | `insufficient_scope` when permission scope is missing. |
| **Business authorization** | Owner, tenant, record-level permission, local account status. | 403 or 404 per policy; not necessarily `insufficient_scope`. |

## 2. Quick Comparison Table of the Three Standard Errors

| OAuth Bearer error | Typical Situation | HTTP Status Suggested by RFC 6750 | What Should the Client Do? |
| --- | --- | --- | --- |
| **`invalid_request`** | Malformed Bearer request, sending token via multiple methods, unaccepted parameters. | **400 Bad Request** | Fix how the HTTP request is constructed. |
| **`invalid_token`** | Token expired, revoked, unverifiable, wrong audience/issuer per policy. | **401 Unauthorized** | Obtain a new valid credential or re-run the appropriate authorization flow. |
| **`insufficient_scope`** | Valid token lacking the endpoint's required permission. | **403 Forbidden** | Request permitted scope, use the right client/account, or deny the operation. |

RFC 6750 requires using **`WWW-Authenticate`** to return challenges when needed, while describing suitable status codes. However, **not every 400, 401, or 403 in an application corresponds to one of these three codes**:

- A JSON request body failing schema validation can be a **400** from domain validation, not a Bearer protocol `invalid_request`.
- An API returning **401** when no Bearer token is present may return only a `Bearer` challenge, **without `error="invalid_token"`**.
- A locked account or a request accessing someone else's record may receive **403**, without necessarily lacking an OAuth scope.
- An unavailable Authorization Server/JWKS/introspection endpoint is an **authentication dependency issue**, not automatic proof that a real token was revoked.

## 3. WWW-Authenticate Is Where Bearer Errors Are Described

In HTTP, `WWW-Authenticate` is the response header the Resource Server uses to announce the **authentication scheme** and challenge parameters. With OAuth 2.0 Bearer Tokens, a response might contain:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Components:

| Component | Example | Function |
| --- | --- | --- |
| **Scheme** | `Bearer` | Signals a Bearer challenge. |
| **`realm`** | `"orders-api"` | Describes the protection space, useful when clients interact with multiple APIs. |
| **`error`** | `"invalid_token"` | Standardized error code. |
| **`error_description`** | `"The access token expired"` | Short, optional description; must avoid leaking sensitive data. |
| **`error_uri`** | `"https://docs.example.test/errors/invalid-token"` | Optional link to documentation explaining the error. |
| **`scope`** | `"orders.write"` | Required scopes, optionally provided when permissions are insufficient. |

Challenge parameters must obey HTTP syntax and RFC 6750 constraints. **Never concatenate client-controlled strings** into `WWW-Authenticate`: this risks malformed headers, header injection, or reflecting sensitive content.

### 3.1. Complete Examples for Each Code

**Malformed Bearer request:**

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request", error_description="Malformed bearer token request"
~~~

**Token no longer accepted:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

**Valid token with insufficient permissions:**

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

These are **illustrative responses matching RFC semantics**, not a guarantee that Spring Security automatically populates all of `realm`, `scope`, or `error_description` in every case. Actual header contents depend on the exception, handler, and configuration.

### 3.2. Why Does a Response When No Token Was Sent Usually Omit error?

Suppose a client calls an endpoint requiring a Bearer token without **sending a credential**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

Appropriate response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Per RFC 6750, when a request **contains no authentication information**, or uses an authentication method unsupported by the Resource Server, the server **should not include OAuth Bearer error info**. Since no token was evaluated, returning `invalid_token` would be misleading.

The same can happen if the request carries:

~~~http
Authorization: Basic SOME_OTHER_CREDENTIAL
~~~

while the endpoint only supports Bearer. The Resource Server may return a 401 Bearer challenge without attaching `invalid_token` to a credential from another scheme.

### 3.3. Is Returning error_description Required?

No. `error_description`, `error_uri`, and `scope` all require careful consideration. For example, returning `"JWT signature verification failed using key kid-..."` with key and configuration details helps attackers map infrastructure; a message like `"Token is invalid"` is usually enough for clients.

`error_description` is information for the client, not an internal debug log. Never return the raw Authorization header, token, secret, stack trace, user ID, administrative account-lock reasons, or system paths in responses.

## 4. invalid_request: Error in How the Bearer Token Was Sent

The **`invalid_request`** code relates to the **request using a Bearer credential**, for example:

- The request is missing a required Bearer parameter in the token transmission method used.
- The request repeats a parameter in a disallowed manner.
- The request sends the token using **multiple transmission methods simultaneously** (such as header and form body when the server supports both).
- The request contains an unacceptable token format.
- The request uses a token transmission mechanism unsupported by the endpoint, depending on implementation and enforced rules.

RFC 6750 describes syntax errors and Bearer token usage errors; it is **not** a generic error code for all invalid API data.

### 4.1. What Does a Valid Bearer Header Look Like?

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

There must be valid syntax between scheme and token. A request such as:

~~~http
Authorization: Bearer abc def
~~~

does not represent a valid Bearer credential under standard syntax because the token is split into multiple parts by whitespace. With an appropriate default `DefaultBearerTokenResolver` configuration, that kind of request can be rejected with `invalid_request` and **HTTP 400**.

Do not treat `abc def` as two tokens and pick the first one. Never call `split(" ")` and silently discard the rest if writing a custom token resolver.

### 4.2. Sending the Token in Both Header and Query

Example to avoid:

~~~http
GET /api/orders?access_token=TOKEN_FROM_QUERY HTTP/1.1
Authorization: Bearer TOKEN_FROM_HEADER
~~~

RFC 6750 forbids using **more than one method to transmit an Access Token in the same request**. If a Resource Server is configured to support multiple transport methods and finds tokens in multiple places, this is an `invalid_request` situation.

In Spring Security Resource Server, **`DefaultBearerTokenResolver` defaults to the Authorization header**; form-encoded body or URI query tokens **are not enabled by default**. Therefore, do not assume every request with `access_token` in the query is classified identically when the server **has not enabled** query token lookup.

**Recommendation:** use solely:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Do not enable URI query tokens without a mandatory requirement and dedicated risk assessment: query strings can be recorded in access logs, browser history, analytics, referrers, or infrastructure monitoring.

### 4.3. Body Tokens Are Not the Default for JSON APIs

RFC 6750 describes passing tokens in a **form-encoded body** under specific conditions, but that is not a good default for REST JSON APIs.

Example:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN_VALUE&item=sample
~~~

If the Spring Security application **does not allow form-body tokens**, that request does not become authenticated just because it contains an `access_token` parameter. If supported, you must still prevent simultaneous use of Authorization header and body tokens, and assess token exposure in body logs.

### 4.4. Duplicate Authorization Headers

When a client/proxy sends multiple `Authorization` headers, behavior can depend on the **HTTP server, reverse proxy, and token resolver**. Systems must enforce a policy **rejecting ambiguous multiple Bearer credentials** and test it across the real stack. Never write custom logic to grab "the first or last header" when other infrastructure components may interpret them differently.

### 4.5. invalid_request Is Not a JSON Request Body Error

If `POST /api/orders` receives:

~~~json
{"quantity": -100}
~~~

then the invalid business body can produce:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
~~~

This is an **API validation** error, not an OAuth Bearer `invalid_request` if the Bearer credential was sent properly. Do not attach `WWW-Authenticate: Bearer error="invalid_request"` to every 400 error of a REST API.

## 5. invalid_token: Token Cannot Be Authenticated/Accepted

The **`invalid_token`** code describes an Access Token that is expired, revoked, malformed, or otherwise invalid. The Resource Server usually returns **401** if the client supplied a Bearer credential that could not be authenticated.

### 5.1. With a JWT Resource Server

Typical scenarios:

| JWT Issue | Why Is the Token Rejected? |
| --- | --- |
| JWT bad signature | Cannot be verified with a trusted public key. |
| Token signed by another key/issuer | Does not satisfy the API's trust configuration. |
| Wrong `iss` | Not issued by an authorized issuer under the contract. |
| Wrong `aud` or missing API | Token is intended for another resource. |
| `exp` in the past | Token lifetime has expired. |
| `nbf` not reached | Token is not yet valid for use. |
| Disallowed algorithm | JWT violates signature verification policy. |
| Required claims wrong/missing | Fails the API's token profile. |
| Tampered or unparseable JWT | Credential is not a valid JWT per decoder. |
| Wrong token type/purpose | E.g., using an OIDC ID Token instead of an Access Token for a Resource Server. |

`invalid_token` does not mean Spring Security must disclose the **exact internal reason** to the caller. A concise response is usually appropriate:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Issuer/audience must be checked explicitly. **A valid signature is not enough** if the token was issued for another API or the principal is not from an allowed source.

### 5.2. With Opaque Tokens

The Resource Server sends the token to the introspection endpoint. If it receives:

~~~json
{"active": false}
~~~

then the token is rejected, typically resulting in **401** meaning invalid token.

However, an **HTTP 200 from the introspection endpoint** can contain `active:false`, so never interpret the upstream HTTP status as meaning the token is valid. Conversely, HTTP 401/503 or timeout **from the introspection endpoint** is a different problem (client authentication or upstream outage) and does not automatically prove the caller's Access Token expired.

### 5.3. Expired Token Differs from Missing Scope

For example, a token has:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "aud": ["orders-api"],
  "exp": 1700000000,
  "scope": "orders.read orders.write"
}
~~~

Once the current time passes `exp`, the token must be rejected at **authentication** even if its scope contains all permissions. It must not "pass authentication and get 403 for scope", nor be accepted just because the request formatted `Authorization: Bearer` properly.

### 5.4. What Should the Client Do on Receiving invalid_token?

Depending on the OAuth flow, the client can:

- Request a valid Access Token from the Authorization Server via an allowed workflow.
- If it is an OAuth 2.0 Client with a Refresh Token, perform a refresh per policy.
- Prompt the user to re-authenticate when necessary.
- If the token was revoked, stop replaying the same token repeatedly.
- Verify the client is calling the **right API audience**, not sending an ID Token or an Access Token meant for another API.

Not every `invalid_token` can be fixed by a "refresh": a client rejected due to wrong issuer/audience or Authorization Server misconfiguration must fix the token request/registration and scope/resource, not just keep swapping tokens of the same kind.

## 6. insufficient_scope: Valid Credential, Insufficient Permissions

Endpoint example:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
Content-Type: application/json

{"item":"book"}
~~~

The token has been authenticated and has:

~~~json
{
  "scope": "orders.read"
}
~~~

But the POST endpoint requires:

~~~text
orders.write
~~~

Then the Resource Server typically denies it:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

**401 is not appropriate for a token that is authenticated but merely lacks scope**, unless a separate policy treats that deficiency as an invalid token profile condition right at authentication. Keep token contracts and policy layers consistent.

### 6.1. Scopes Do Not Have an Implicit Hierarchy

If a token has `orders.write`, the API **should not assume** it also has `orders.read` unless specified by the contract. Spring Security:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

checks the **exact** mapped GrantedAuthority. It does not know whether `orders.write` implies `orders.read`.

### 6.2. Scope Differs from Roles and Resource Permissions

Suppose a caller has `SCOPE_orders.read` but tries to view someone else's order:

~~~text
Valid JWT
Authority: SCOPE_orders.read
Order ID: 42 belongs to another tenant
~~~

The OAuth scope requirement may be satisfied, yet **domain authorization** still must block it. The response may be **403** or **404** per resource-hiding policy. `insufficient_scope` is not necessarily used, because the caller does not lack a general scope; the caller lacks **permission on that specific record**.

Similarly, `hasRole("ADMIN")` by default checks `ROLE_ADMIN`, which differs from `hasAuthority("SCOPE_admin.manage")`. If the domain uses internal roles instead of OAuth scopes, error handling should not treat every AccessDeniedException as a missing real OAuth scope.

### 6.3. Should the Required Scope Be Disclosed?

RFC 6750 permits including the `scope` parameter:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

That helps the client understand the required permission. However, only disclose scopes permitted to be public. If an endpoint/role or resource is sensitive, listing scopes can be abused to enumerate capabilities. Nor is there any guarantee the Authorization Server will grant that scope to the client just because the Resource Server asked for it.

## 7. Distinguishing the Three Error Codes from Non-Bearer Cases

| Request or State | Typical HTTP Code | Appropriate Bearer Error? |
| --- | --- | --- |
| GET protected endpoint, no Authorization header | **401** | Bearer challenge **without error**. |
| Authorization with another scheme when API only supports Bearer | **401** | May be Bearer challenge only, without error. |
| Malformed Bearer header syntax | **400** | `invalid_request`. |
| Sending token via multiple disallowed methods | **400** | `invalid_request`. |
| Tampered/bad-signature JWT | **401** | `invalid_token`. |
| Expired JWT, invalid issuer/audience | **401** | `invalid_token`. |
| Opaque introspection returns `active:false` | **401** | `invalid_token`. |
| Valid Bearer token lacking OAuth scope | **403** | `insufficient_scope`. |
| Valid Bearer token, sufficient scope, local account locked | **403** | Domain denied; do not treat as `invalid_token`. |
| Sufficient scope, accessing another tenant's order | **403/404** | Domain denied; not necessarily `insufficient_scope`. |
| JSON body violates schema | **400** | REST API error, **not** Bearer `invalid_request`. |
| Non-existent route | **404** or security policy may reject earlier | Do not fabricate a Bearer error. |
| Introspection endpoint 503 / JWKS unreachable | **Possibly 5xx** depending on exception mapping | Upstream failure; must fail closed, do not call token revoked. |

**Core point:** HTTP status, OAuth error code, and business error code **are related, not identical**. Good design classifies errors at the exact layer where they occur rather than catching all exceptions and returning the same response.

## 8. Where Does Spring Security Handle Bearer Errors?

For Servlet Resource Server, typical components are:

~~~text
HttpServletRequest
      |
      v
BearerTokenAuthenticationFilter
      |
      +-- BearerTokenResolver
      |     +-- invalid request -> OAuth2AuthenticationException
      |           |
      |           v
      |       BearerTokenAuthenticationEntryPoint
      |       -> invalid_request / 400 (for corresponding error)
      |
      +-- Token present
             |
             v
       AuthenticationManager
             |
             +-- JWT: JwtAuthenticationProvider -> JwtDecoder
             |
             +-- Opaque: OpaqueTokenAuthenticationProvider
             |           -> OpaqueTokenIntrospector
             |
             +-- Authentication failed
             |     -> BearerTokenAuthenticationEntryPoint
             |     -> 401 / invalid_token (for corresponding error)
             |
             +-- Authentication succeeded
                     |
                     v
               AuthorizationFilter
                     |
                     +-- Missing authority/scope
                     |      -> AccessDeniedException
                     |      -> BearerTokenAccessDeniedHandler
                     |      -> 403 / insufficient_scope when appropriate
                     v
               Controller / Method Security
~~~

### 8.1. DefaultBearerTokenResolver

Spring Security's `DefaultBearerTokenResolver` reads Bearer Access Tokens from requests. By default it uses the **Authorization header** and does not enable query/form-body tokens. It also checks Bearer header formatting before passing the token to AuthenticationManager.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);

    return resolver;
}
~~~

In the example, both options are set **explicitly to false**; this is also the common default. If configuring a custom resolver bean, make sure the Resource Server actually uses it. Never enable `setAllowUriQueryParameter(true)` just to support a legacy client without assessing URL token exposure risks.

### 8.2. BearerTokenAuthenticationEntryPoint

`BearerTokenAuthenticationEntryPoint` is responsible for returning **challenges** when authentication fails or credentials are missing/invalid.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;

@Bean
BearerTokenAuthenticationEntryPoint bearerEntryPoint() {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();
    entryPoint.setRealmName("orders-api");
    return entryPoint;
}
~~~

Setting `realm` lets the response announce the protection space. The exact error in the header depends on the `AuthenticationException` and `OAuth2Error`/Bearer error received by Spring Security.

**Do not replace all exception handling with a handler that always returns 401**, as that turns missing scopes into “invalid token” and deprives clients of necessary context.

### 8.3. BearerTokenAccessDeniedHandler

`BearerTokenAccessDeniedHandler` handles `AccessDeniedException` when an authenticated caller is not permitted access.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

@Bean
BearerTokenAccessDeniedHandler bearerAccessDeniedHandler() {
    BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();
    handler.setRealmName("orders-api");
    return handler;
}
~~~

For a valid Authentication missing an authority, the handler usually returns **403** and Bearer `insufficient_scope`. Yet an `AccessDeniedException` can also come from tenant/owner policies. If the application needs domain-specific error codes, clarify the boundary and design handlers intentionally; do not assume every 403 is due to OAuth scopes.

### 8.4. Attaching the Entry Point and Access-Denied Handler

DSL example:

~~~java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerAccessDeniedHandler)
);
~~~

The snippet uses the beans created in the previous two sections inside the same Bearer API `SecurityFilterChain`. This is an illustrative snippet rather than a standalone complete Spring Boot application; the next section shows a full chain.

## 9. Configuring JWT Resource Server and Endpoint Groups

### 9.1. Dependencies

Gradle Groovy DSL example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 9.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

On Spring Boot versions supporting `audiences`, the API requires the `aud` claim to contain `orders-api`. On other versions, add an appropriate audience validator. The Resource Server also needs to verify JWT signature, issuer, time claims, and profile per policy.

### 9.3. Complete SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApiChain(HttpSecurity http)
            throws Exception {

        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
            new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin.manage")
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this example:

- No token for `GET /api/orders` → **401** Bearer challenge, typically without an error code.
- Malformed Bearer token → token resolver rejects it, possibly **400 invalid_request** depending on the generated error.
- Bearer JWT with bad signature or expired → **401 invalid_token**.
- Valid JWT with only `orders.read` calling `POST /api/orders` → **403 insufficient_scope** per handler.
- Valid JWT with `orders.read` calling GET → can proceed to controller/domain policy.
- Endpoint not declared in the chain → `denyAll`, even with an admin token.

`securityMatcher("/api/**")` only selects the **chain** for this path; if the app has URLs outside `/api/**`, you must define a **fallback SecurityFilterChain** or another policy. Never assume `anyRequest().denyAll()` protects requests outside every chain.

`csrf.disable()` and `STATELESS` here are for APIs using Bearer Authorization headers only, not session-cookie authentication. If the same backend hosts web OIDC Login, configure CSRF/session/CORS policies appropriately per chain.

## 10. A Public Request Can Still Be Rejected for a Bad Bearer Header

Suppose the API defines:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
~~~

For the request:

~~~http
GET /api/public/ping HTTP/1.1
Host: api.example.test
~~~

HTTP authorization allows anonymous access.

Yet for:

~~~http
GET /api/public/ping HTTP/1.1
Authorization: Bearer abc def
~~~

`BearerTokenAuthenticationFilter` can process the header before `AuthorizationFilter`, detect the malformed Bearer request, and return **invalid_request**. Therefore **`permitAll()` does not mean “skip all authentication filters”**.

Similarly, a Bearer token with a bad signature sent to a public endpoint can cause **401**, depending on whether the security chain has Bearer processing and how handlers are configured.

If you need a health endpoint completely independent of authentication, design a **separate chain/route** per infrastructure needs and limit exposed data, rather than assuming permitAll suppresses processing of malformed credentials.

## 11. Both JWT and Opaque Tokens Use the Same Bearer Errors

The three RFC 6750 codes belong to the **Bearer token usage protocol**, not exclusively to JWTs.

### 11.1. JWT Resource Server

~~~text
Bearer token
  -> NimbusJwtDecoder
  -> JWS signature + issuer/audience/time validation
  -> JwtAuthenticationToken
  -> SCOPE_... authorities
~~~

Expired/wrong-issuer/bad-signature JWTs typically lead to `invalid_token`. Valid tokens missing scopes lead to `insufficient_scope` where appropriate.

### 11.2. Opaque Resource Server

~~~text
Bearer token
  -> OpaqueTokenIntrospector
  -> Authorization Server introspection
  -> active false => token invalid
  -> active true + metadata matches contract
  -> BearerTokenAuthentication
  -> SCOPE_... authorities
~~~

For opaque tokens, configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: SECRET_FROM_A_SECURE_STORE
~~~

And in the chain select:

~~~java
.oauth2ResourceServer(oauth ->
    oauth.opaqueToken(Customizer.withDefaults()))
~~~

to replace the `jwt()` branch when the API only accepts opaque tokens.

An **`active:false`** result is normally returned to the client as `invalid_token`; an active token lacking scope can still return `insufficient_scope`. **Introspection endpoint timeout or HTTP 503** is a service-dependency authentication error, not automatic proof the Access Token was revoked; never fail open.

## 12. Details in Spring Security That Easily Cause Confusion

### 12.1. BearerTokenErrors and OAuth2AuthenticationException

Spring Security provides Bearer error types such as `BearerTokenError`, `BearerTokenErrors`, and error code constants in `BearerTokenErrorCodes`. Token resolvers or authentication providers can throw `OAuth2AuthenticationException` wrapping a corresponding `OAuth2Error`. The entry point uses that error type to craft the HTTP response.

Therefore, if writing a custom token resolver/introspector, **preserve error type semantics** instead of wrapping everything in `RuntimeException` and catching it in a controller advice that always returns 500 or 200.

### 12.2. BearerTokenAccessDeniedHandler Does Not Know All Domain Policies

This handler can use `insufficient_scope` for AccessDeniedExceptions when the Authentication is already verified. However:

~~~text
Role/Scope authorization: missing SCOPE_orders.write
Domain authorization: order does not belong to caller
~~~

can both end in **403**, yet **do not share the same meaning**. When the app needs to distinguish them in responses, design dedicated exception/domain error mapping, preserve secure statuses, avoid leaking sensitive owner/tenant info, and do not strip genuine Bearer challenges.

### 12.3. Not Every Authentication Is a JWT

With a JWT Resource Server the principal is typically `JwtAuthenticationToken`; with opaque tokens it is typically `BearerTokenAuthentication`; with an OAuth2 Login session it may be another Authentication type. A custom error handler must never cast every principal to `Jwt` to read `scope` or `iss`.

### 12.4. 401 Is Named Unauthorized, but Refers to Authentication

The HTTP name **401 Unauthorized** is misleading: in security architecture, it normally requires valid **authentication**. Meanwhile **403 Forbidden** applies to an authenticated principal who is **not permitted** to perform the action.

If a JWT has a bad signature, do not let the request become a successful Authentication and return 403 just for missing a role. If there is no token, never create an anonymous principal with admin authorities “to make the endpoint work”.

## 13. Designing a JSON Error Body Alongside a Bearer Challenge

Spring Security may return only `WWW-Authenticate` without a JSON body. If the API wants consistent JSON errors, you can add a body, but **must not break HTTP status and Bearer headers**.

Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json

{
  "type": "https://docs.example.test/problems/invalid-token",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Unable to authenticate request."
}
~~~

Notes:

- The body does not replace the `WWW-Authenticate` challenge.
- Do not dump raw exception details automatically into `detail`.
- Avoid bodies like `{"error":"Signature key rsa-2026-a missing from internal-jwks-host"}` because they leak configuration.
- Do not return token owner info, email, `sub`, or internal permissions when the token is invalid.
- Keep the API error contract consistent across filter exceptions and controller/domain exceptions.

**Relying solely on `@RestControllerAdvice` is not enough to handle all Resource Server errors**, because Bearer and authorization filters run **before the controller**. If writing a JSON error handler, integrate via `AuthenticationEntryPoint` and `AccessDeniedHandler` or an appropriate mechanism while preserving standard Bearer challenge behavior.

### 13.1. Do Not Reveal Too Much About insufficient_scope

A response may state:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

but internal admin APIs do not necessarily want to publish their entire list of scopes/roles. You can use neutral messages in the body and document scopes for authorized clients. Any scope appearing in the challenge must also be the exact OAuth scope name used in the contract, not guessed from internal roles prefixed with `ROLE_`.

### 13.2. CORS Expose Headers If Frontend Needs to Read WWW-Authenticate

Browser JavaScript may need to read `WWW-Authenticate` to handle errors. The CORS policy may need to **expose** that header to allowed origins:

~~~java
cors.setExposedHeaders(
    List.of("WWW-Authenticate"));
~~~

This adds to a `CorsConfiguration` that already has origin/method/header allowlists. CORS does not replace authentication/authorization, and exposing the header grants no new permissions to the client. Never use improper wildcard origins/credentials to “fix” 401 or 403 errors.

## 14. How Should HTTP Clients Handle the Three Errors?

A well-behaved OAuth 2.0 client does not handle every 401/403 with an infinite “refresh and retry” loop.

### 14.1. When Receiving invalid_request

Check:

1. Is it formatted properly as `Authorization: Bearer TOKEN`?
2. Are there whitespace or invalid characters in the header?
3. Is the token being sent in query/body simultaneously?
4. Did a proxy merge/alter/duplicate the Authorization header?
5. Is the client using a token transport mechanism supported by the server?

**Fix the request**—do not necessarily force the user to log in again. Refreshing the token does not solve a malformed header error.

### 14.2. When Receiving invalid_token

Check the credential lifecycle:

1. Is the token expired/revoked?
2. Did the client send an Access Token rather than an ID Token?
3. Are the issuer and audience/resource correct?
4. Is the client holding a token from another environment (dev/staging/prod)?
5. Can a new Access Token be obtained via an allowed flow?

If the client has a refresh token, it can refresh per policy with **retry limits** and avoid endless concurrent refreshes. Never log old or new tokens. If the server keeps rejecting fresh tokens due to wrong issuer/audience, investigate configuration instead of refreshing forever.

### 14.3. When Receiving insufficient_scope

Do not assume refreshing the same grant will add new permissions: scopes do not automatically expand on refresh. You can:

- Check whether the right endpoint was called.
- If permitted by policy, start an authorization flow to **request additional scopes**.
- Display an insufficient-permissions message or contact an administrator.
- Never allow the client to send a custom `X-Scope: admin.manage` header to override verified claims.

Never instruct clients to resend the Access Token in a query string to “bypass 403”; the issue is permissions, not how the token was transmitted.

## 15. Testing Each Error Code with MockMvc and Decoder Tests

To test properly, separate:

- **Token resolution tests**: are the Bearer header and token transport valid?
- **Token authentication tests**: are JWT/opaque tokens genuinely verified?
- **HTTP authorization tests**: does a valid principal have sufficient authority for the endpoint?

### 15.1. Requirements Matrix

| Scenario | Expected | Layer |
| --- | --- | --- |
| No Authorization header sent to protected endpoint | **401**, Bearer challenge without error. | Authentication entry point. |
| `Authorization: Basic ...` sent to Bearer-only API | **401**, possibly Bearer challenge only. | Unsupported/missing Bearer credential. |
| `Authorization: Bearer abc def` sent | **400 invalid_request** per appropriate default resolver. | Token resolution. |
| Malformed JWT string sent | **401 invalid_token** when decoder rejects. | Token authentication. |
| Expired JWT | **401 invalid_token**. | JWT validation. |
| JWT with wrong issuer/audience | **401 invalid_token**. | JWT validation. |
| Opaque `active:false` | **401 invalid_token**. | Introspection authentication. |
| Valid JWT, `SCOPE_orders.read`, calling GET | Allowed through to handler/domain service. | HTTP authorization. |
| Valid JWT, only `SCOPE_orders.read`, calling POST | **403 insufficient_scope**. | HTTP authorization. |
| Valid JWT, sufficient scope, wrong owner/tenant | **403 or 404**, not necessarily insufficient_scope. | Domain authorization. |
| Malformed JSON body with valid Bearer | **400 domain validation**, not Bearer invalid_request. | Controller/request validation. |
| JWKS or introspection endpoint timeout | Deny access; 5xx/503 mapping depending on handler. | Dependency/operation failure. |

### 15.2. Token Resolver Unit Test: invalid_request

To test Bearer header syntax directly:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BearerTokenResolverTest {

    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void malformedBearerHeaderIsInvalidRequest() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();
        request.addHeader(
            HttpHeaders.AUTHORIZATION, "Bearer abc def");

        OAuth2AuthenticationException exception =
            assertThrows(
                OAuth2AuthenticationException.class,
                () -> resolver.resolve(request));

        assertEquals(
            "invalid_request", exception.getError().getErrorCode());
    }

    @Test
    void noBearerTokenReturnsNull() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        assertEquals(null, resolver.resolve(request));
    }
}
~~~

This is a **token resolution unit test**, not an HTTP response test; it only proves the resolver raises an error with code `invalid_request`. To test HTTP 400 and `WWW-Authenticate`, run the request through the Spring Security filter chain with the entry point.

### 15.3. MockMvc Tests for Authentication and Authorization

Minimal example using a test `JwtDecoder` that rejects raw Bearer tokens, while `jwt()` creates a mock principal to test scopes:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(BearerErrorHttpTest.TestDecoderConfig.class)
class BearerErrorHttpTest {

    @Autowired
    MockMvc mockMvc;

    @TestConfiguration
    static class TestDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException("Bad test token");
            };
        }
    }

    @Test
    void missingTokenHasBearerChallengeWithoutInvalidTokenCode()
            throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void malformedBearerHeaderReturnsInvalidRequest()
            throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer abc def"))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_request")));
    }

    @Test
    void tokenRejectedByDecoderReturnsInvalidToken()
            throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer opaque-looking-value"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_token")));
    }

    @Test
    void authenticatedReaderCannotWrite()
            throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedReaderCanPassReadRule()
            throws Exception {
        // Without a matching controller, the final
        // result may be 404 even though authorization passed.
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }
}
~~~

**Conditions for using this example:** the test app must have a `SecurityFilterChain` as in section 9 and a **`GET /api/orders` controller returning 200** for the final assertion to pass. Without a handler, an authorized request may return **404**, which is not a security error. The test decoder bean is for testing only and must not coexist with a production decoder bean causing duplicate configuration. `with(jwt())` intentionally bypasses the decoder, so the last two tests **do not verify real signatures**.

### 15.4. Testing the insufficient_scope Header Separately

With an appropriate default `BearerTokenAccessDeniedHandler` and an authenticated principal:

~~~java
mockMvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("insufficient_scope")));
~~~

This tests **HTTP authorization + access-denied handler**. The header might not include `scope="orders.write"` if the handler cannot infer the missing scope list from `AccessDeniedException`; do not force every test to expect that parameter. If the app uses a custom handler, verify that handler's specific semantics.

### 15.5. Testing Real Signed JWTs

Another test suite must verify the real JWT path:

~~~text
1. Generate a test RSA key pair.
2. Configure NimbusJwtDecoder with the test public key or test JWKS server.
3. Sign JWTs with the test private key.
4. Create valid token, bad-signature token,
   wrong-issuer token, wrong-audience token, expired token.
5. Send Bearer token through the filter chain without jwt().
6. Verify valid tokens authenticate,
   and invalid tokens are rejected before reaching controllers.
~~~

`JwtDecoder` needs appropriate issuer, audience, and timestamp validators. A `jwt()` MockMvc fixture **does not** test decoder/JWKS; such tests are only suitable for testing authorities and endpoint policies.

### 15.6. Testing Real Opaque Introspection

Use an introspection test server returning:

~~~text
token=active-reader
  -> HTTP 200 {"active":true,"scope":"orders.read"}

token=inactive
  -> HTTP 200 {"active":false}

token=upstream-error
  -> HTTP 503
~~~

Send raw Bearer tokens through the Resource Server with a real introspector pointing to the test server. Verify:

- `active:false` → authentication fails, usually **401 invalid_token**.
- `active:true`, lacking write scope → **403 insufficient_scope** on POST.
- HTTP 503 → do not let the request run as authenticated; classify as upstream error, do not mistake for a revoked token.

The MockMvc `opaqueToken()` helper builds a mock Authentication and therefore **does not test real RFC 7662 `active` checks**. Testing introspection requires a client/server fixture.

## 16. Notes on Multiple SecurityFilterChains

An application might have:

~~~text
/api/**       -> Resource Server Bearer chain
/web/**       -> OIDC Login + session chain
/management/**-> Separate management policy
fallback      -> denyAll
~~~

If the same application uses OIDC Login and Bearer APIs, do not let the **Bearer entry point** control all web session requests, or let **redirects to the login page** replace HTTP 401 when an API client sends a Bearer token.

`securityMatcher` selects the chain; inside the chain, `requestMatchers` decide permissions. Place specific chains first, fallbacks last, and ensure no endpoint sits unprotected outside every chain.

For browser CORS preflights, OPTIONS requests normally do not contain a Bearer Access Token; configure **proper CORS processing before authentication**. Do not call a CORS preflight failure `invalid_token` when the browser has not sent a token. For cookie/session APIs, handle CSRF per that model; stateless Bearer-header APIs may choose a different policy.

## 17. Protecting Error Handling and Observability

### 17.1. Data Safe to Log

- Request ID, logical endpoint name, HTTP method, and status.
- Error category such as `bearer_invalid_request`, `jwt_invalid_token`, `insufficient_scope`.
- **Configured** issuer/resource when needed for diagnostics, avoiding untrusted URLs as sources of truth.
- JWT decoder/introspection latency and network error categories.
- 401/403 rates, auth failure rates, and authorization denial rates.

### 17.2. Data Never to Log

- Raw `Authorization` header or Access Token.
- Refresh Token, client secret, private keys, or introspection request bodies.
- Full JWT payloads/claims containing PII.
- Session cookies or client-submitted authentication secrets.
- Stack traces in HTTP responses, sensitive internal JWKS URLs, or key material.

### 17.3. Preventing Error Probing

If a client receives overly detailed messages per token:

~~~text
Token does not exist
Token belongs to user A and is locked
Token has kid X but bad signature
Tenant Y's token lacks scope ...
~~~

attackers can infer token or architectural details. Use standard challenges, concise descriptions, and access-controlled internal logs instead of reflecting every detail.

Never handle `invalid_request` by printing the raw Authorization header for debugging; that is one of the easiest ways to leak Bearer credentials when clients make mistakes.

## 18. Common Mistakes When Applying the Three OAuth Codes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Returning `invalid_token` for requests with no token. | Client mistakenly thinks a token existed and failed. | 401 Bearer challenge, usually **without error**. |
| Returning `invalid_request` for every HTTP 400. | Mixes Bearer protocol errors with body validation. | Classify by layer. |
| Returning `invalid_token` for valid JWT lacking write scope. | Wrong authentication/authorization semantics. | Usually 403 `insufficient_scope`. |
| Returning 403 for bad-signature token. | Assumes principal authenticated when credential is invalid. | 401 `invalid_token`. |
| Allowing access on JWT decoder/introspection timeout. | Fail-open at the authentication boundary. | Fail closed, classify upstream error. |
| Letting token pass whenever introspection returns HTTP 200. | A 200 response can carry `active:false`. | Check the active boolean. |
| Using `hasRole("ADMIN")` when token only has `SCOPE_admin.manage`. | Rule never matches or leads to unsafe workarounds. | Align authority converter and policy. |
| Creating custom handler always returning JSON 200/401. | Hides 400 invalid_request and 403 insufficient_scope. | Keep proper HTTP status and WWW-Authenticate. |
| Returning `scope` taken from client-submitted body. | Client influences security policy descriptions. | Scopes must be defined by server policy. |
| Allowing Bearer tokens in URLs for client convenience. | Token easily leaks via logs/history/referrers. | Use Authorization header. |
| Dropping security filters on public endpoints to dodge Bearer errors. | Loses other security controls. | Use explicit permitAll/chains per requirements. |
| Testing only MockMvc `jwt()` and assuming invalid_token is tested. | Test skips JWT verification. | Add signed-JWT integration tests. |
| Logging the full Bearer header on authentication failure. | Credential leak. | Log error codes and request IDs. |
| Equating domain 403 with `insufficient_scope`. | Reports wrong cause; leaks permission structure. | Separate domain error mapping when needed. |

## 19. Consistent Bearer Error Implementation Workflow

1. **Identify Access Token type**: JWT or opaque, issuer/audience, token type, and proper validation method.
2. **Set clear Bearer resolution**: accept the Authorization header; do not enable query/body or multiple sources by default.
3. **Use standard framework exception handling**: `BearerTokenAuthenticationEntryPoint` for authentication, `BearerTokenAccessDeniedHandler` for authorization.
4. **Classify the three errors**: malformed request → `invalid_request`; invalid token → `invalid_token`; valid token lacking OAuth scope → `insufficient_scope`.
5. **Keep 401/403 boundaries accurate**: missing credentials or bad tokens belong to authentication; scopes and business permissions belong to authorization.
6. **Design responses that leak no secrets**: syntactically valid `WWW-Authenticate`, concise body without tokens, secrets, owner/tenant info, or stack traces.
7. **Separate upstream outages**: JWKS/introspection errors must not grant access; do not mislabel every network error as a revoked token.
8. **Test across three layers**: resolver, real JwtDecoder/introspector, and endpoint authorization via MockMvc.
9. **Ensure chain coverage/CORS/CSRF**: Bearer APIs differ from web OIDC sessions; public endpoints may still process malformed Bearer headers.
10. **Record metrics and audit safely**: track error categories, 401/403 counts, and reliability without exposing credentials.

**Remember:** **`invalid_request` = Bearer request violates rules; `invalid_token` = credential not accepted; `insufficient_scope` = valid token lacking permission scope.** With Spring Security Resource Server, understanding **`WWW-Authenticate`**, distinguishing **400/401/403**, and testing **authentication/authorization** paths keeps the API clear for clients while maintaining strict security boundaries.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Section 3: WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc6750#section-3).
- [RFC 6750 — Section 3.1: Error Codes](https://www.rfc-editor.org/rfc/rfc6750#section-3.1).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [Spring Security — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html).
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
