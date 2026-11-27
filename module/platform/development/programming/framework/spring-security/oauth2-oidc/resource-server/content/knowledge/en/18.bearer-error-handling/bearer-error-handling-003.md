# WWW-Authenticate and Challenges Under RFC 6750

In **Spring Security OAuth 2.0/OIDC Resource Server**, an API usually receives an access token via the **Authorization: Bearer ...** request header. When a request has no token, an invalid token, or a validated token lacking permissions, the server does not just return HTTP 401/403 arbitrarily: **RFC 6750 — OAuth 2.0 Bearer Token Usage** defines how a Resource Server sends a **Bearer challenge** via the **WWW-Authenticate** response header.

Three situations must be distinguished:

- **No authentication credentials**: the protected endpoint returns **401 Unauthorized** with a Bearer challenge; per RFC 6750, the server **SHOULD NOT** add a specific error code when the client has not supplied authentication information.
- **Bearer token present but invalid**: typically returns **401 Unauthorized**, with challenge **error="invalid_token"**.
- **Token authenticated but insufficient scope**: typically returns **403 Forbidden**, with challenge **error="insufficient_scope"**, possibly indicating the required scope.

Additionally, a malformed Bearer request or one using multiple token submission methods simultaneously falls under **invalid_request**, for which RFC 6750 recommends **400 Bad Request**.

Spring Security provides components such as **BearerTokenAuthenticationEntryPoint**, **BearerTokenAccessDeniedHandler**, **BearerTokenError**, and **BearerTokenErrors** to represent these outcomes. This lesson moves from the HTTP standard, challenge parameters, and request/response examples to Servlet Resource Server configuration and practical testing.

## 1. What Is WWW-Authenticate?

HTTP authentication distinguishes two sides:

| Header | Sender | Role |
|---|---|---|
| **Authorization** | **Client → Resource Server** | Client presents authentication credentials, e.g., a Bearer access token |
| **WWW-Authenticate** | **Resource Server → Client** | Server issues an **authentication challenge**, announcing supported authentication methods and optionally error details |

Example of a client calling the Orders API without sending a token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Accept: application/json
~~~

A standard response under RFC 6750 might be:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Length: 0
~~~

The client understands that the resource is protected by the **Bearer authentication scheme**. If the client has been issued a suitable access token, the next request can use:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <access-token>
~~~

Values inside angle brackets are placeholders only, not real tokens.

**WWW-Authenticate is not an address to obtain an access token** and is not a token endpoint response. It is a **challenge from the Resource Server** when accessing a protected resource. The client must obtain a token using an appropriate OAuth2 flow with the Authorization Server and then present the token to the API.

### 1.1. A Challenge Is Not Necessarily an Error in a JSON Body

An API might have a body:

~~~json
{
  "code": "UNAUTHORIZED",
  "message": "Authentication required"
}
~~~

However, such a JSON body **does not replace** the HTTP WWW-Authenticate header when the protocol requires a Bearer challenge. OAuth clients, HTTP libraries, and automated tests may rely on status/headers rather than a custom body schema.

Conversely, a response with WWW-Authenticate **does not have to contain a JSON body**. The Resource Server can send the status, header, and an empty body depending on the API contract.

### 1.2. Do Not Confuse with HTTP Basic

HTTP supports multiple authentication schemes, for example:

~~~http
WWW-Authenticate: Basic realm="legacy-app"
~~~

or:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

**Basic** is typically tied to username/password or client credentials per its mechanism. **Bearer** is tied to possession of an access token. Never change **Bearer** to **Basic** in a Resource Server's challenge just because the introspection endpoint uses HTTP Basic for client authentication.

A server may advertise multiple challenges per HTTP rules if it genuinely supports multiple schemes; combining/splitting multiple header fields must follow HTTP syntax. This lesson focuses on the **Bearer challenge** of RFC 6750.

## 2. Structure of a Bearer Challenge

Under **RFC 6750 §3**, a Bearer challenge uses the **Bearer** authentication scheme accompanied by appropriate **auth-params**.

Complete example to explain syntax:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", error_description="Insufficient scope", scope="orders.write"
~~~

Fields:

| Auth-param | Meaning | Note |
|---|---|---|
| **realm** | Identifies the protection space under HTTP authentication | Optional; does not replace issuer/tenant policies |
| **error** | OAuth Bearer error code | RFC 6750 defines **invalid_request**, **invalid_token**, **insufficient_scope** |
| **error_description** | Short explanation for developers/clients | Must not contain secrets, tokens, or stack traces |
| **error_uri** | URI to documentation explaining the error | Not the token endpoint or jwks_uri |
| **scope** | Scopes required to access the resource | Optional; space-delimited list of scopes |

Structurally, the response can have multiple comma-separated parameters. For instance:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token expired"
~~~

Do not confuse the **comma** separating auth-params with the **space** between multiple scope values:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read orders.write"
~~~

Depending on policy, the **scope** parameter may list multiple required scopes. Scope strings must follow OAuth2 rules, where scope names are **case-sensitive**.

### 2.1. Are Auth-Params Required to Appear?

Not every response needs all of **realm**, **error**, **error_description**, **error_uri**, and **scope**. In a specific system:

- **realm** may or may not be configured.
- **error** is normally absent when the request has not sent authentication credentials, per RFC recommendations.
- **error_description** and **error_uri** are supplementary info and are not always returned.
- **scope** is typically meaningful when the server reports **insufficient_scope**; it is not mandatory to disclose.

Some Spring Security versions may return **WWW-Authenticate: Bearer** without a realm, or add extension parameters depending on the release line. Therefore, **do not write tests asserting the header equals an exact fixed literal string across all versions** when the app does not lock down the exact configuration.

### 2.2. Non-Duplication Rule for Parameters

RFC 6750 specifies that parameters among **realm**, **scope**, **error**, **error_description**, and **error_uri** must not appear more than once per its rules.

Example to avoid:

~~~http
WWW-Authenticate: Bearer realm="orders-api", realm="admin-api", error="invalid_token"
~~~

Duplicate parameters make challenges hard for clients to parse and can cause discrepancies across parsers. When constructing headers manually, use an appropriate builder/handler instead of unchecked string concatenation.

### 2.3. Values Are Not Arbitrary Text

**error** and **error_description** must satisfy RFC 6750/RFC 6749 character constraints; **error_uri** must conform to URI-reference syntax and corresponding character limits. Do not put **raw newlines**, control characters, unescaped quotes, or invalid values into auth-params.

For example, an error description carrying untrusted data is dangerous:

~~~text
error_description = exception.getMessage()
~~~

if the exception contains raw tokens, HTTP request content, newline characters, or internal details. For public messages, use **short, safe fixed strings**, avoiding header injection and system leaks.

## 3. Three Error Codes of RFC 6750 §3.1

RFC 6750 defines three primary error codes for Bearer authentication on protected resources.

| Error code | Meaning | Recommended HTTP status |
|---|---|---|
| **invalid_request** | Request carries Bearer token violating structure/transmission rules | **400 Bad Request** |
| **invalid_token** | Submitted token is invalid, expired, revoked, or fails validation conditions | **401 Unauthorized** |
| **insufficient_scope** | Token is authenticated but lacks sufficient scope for the resource | **403 Forbidden** |

In the RFC, these statuses are expressed with **SHOULD**, not as an exclusive rule for every HTTP error kind. Moreover, Spring Security may map certain specific situations through different **BearerTokenError**/exception handling paths.

### 3.1. invalid_request — Malformed Request

Some situations:

- Request uses **more than one method** to send the access token simultaneously.
- Duplicate token parameter.
- Bearer authentication request is missing or has an invalid required parameter.
- A token presentation method is unsupported by the endpoint.
- Request is malformed under Bearer rules.

Illustrative response:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request", error_description="Multiple bearer tokens"
Content-Length: 0
~~~

The RFC recommends 400 for invalid_request. **However, do not deduce that every malformed Authorization string is guaranteed to become invalid_request/400 in every Spring Security version.** For instance, some code paths in **DefaultBearerTokenResolver** may represent a malformed Bearer header as **invalid_token**; verify the exact exception and status produced by your framework version.

### 3.2. invalid_token — Token Not Accepted

Examples:

- JWT access token has a bad signature or disallowed algorithm.
- JWT has wrong **iss** or **aud**.
- Token is expired (**exp**) or not yet valid (**nbf**) per policy.
- Opaque token marked **active=false** by introspection.
- Token has been revoked.
- Token is forged, non-existent, or not confirmed by a trusted issuer source.

Typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="Invalid access token"
Content-Length: 0
~~~

The RFC also illustrates an expired access token error with the description **The access token expired**. In production, it is not necessary to reveal the exact classification of every signature/claim error; what matters is that the client knows the token was rejected.

**invalid_token does not mean the client just needs to add a scope.** The client usually must check the token in use, obtain a valid new token via the appropriate OAuth flow, or prompt the user to re-authenticate when truly needed.

### 3.3. insufficient_scope — Valid Token but Insufficient Permissions

Suppose an endpoint:

~~~text
POST /api/orders/42/approve
Required authority: SCOPE_orders.approve
~~~

The client has an authenticated access token that only carries:

~~~text
SCOPE_orders.read
~~~

The Resource Server may return:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.approve"
Content-Length: 0
~~~

**scope="orders.approve"** is a hint about the required permission scope; the RFC allows it, though the server is **not required** to provide this parameter.

The client cannot manually insert **orders.approve** into the JWT string and resend it. Granting scopes is decided by the **Authorization Server and authorization policies**, not by client JSON editing.

### 3.4. How Does 401 Differ from 403?

- **401 Unauthorized** usually means the request lacks suitable authentication credentials or the presented token could not be authenticated.
- **403 Forbidden** usually means the identity/token was authenticated, yet **lacks sufficient permissions** to perform the action.

In Spring Security, **AccessDeniedException** can occur in multiple states; whether **ExceptionTranslationFilter** invokes the authentication entry point or access denied handler also depends on the current Authentication. Hence the status is not determined solely by the exception class name.

An application may also return **404 Not Found** to conceal resource existence per domain policy. In that case, distinguish data-hiding policy from standard Bearer **insufficient_scope** handling; do not assume every AccessDeniedException should expose scopes.

## 4. Missing Token: Bearer Challenge Without an Error

A subtle detail of RFC 6750 is easily overlooked: **when the request contains no authentication information**, the server **SHOULD NOT** include an error code or specific error information.

Example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

This differs from an invalid token:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <invalid-access-token>
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

**A token does not need to be present for WWW-Authenticate to appear.** RFC 6750 requires the Resource Server to send a challenge when a protected resource request lacks credentials or lacks a token capable of accessing it. The challenge tells the client which scheme to use.

Do not force **invalid_token** as a mandatory error code for requests that sent no credentials at all; in that situation, no token exists to judge “invalid”.

## 5. Decision Diagram When Resource Server Receives a Bearer Request

~~~mermaid
flowchart TD
    R[HTTP request to protected endpoint] --> T{Valid Bearer token syntax?}
    T -->|No credential| C[401 + WWW-Authenticate Bearer, no error]
    T -->|Malformed / duplicate| B[Bearer error: invalid_request or framework mapping]
    T -->|Token present| V{JWT verification or introspection passes?}
    V -->|No| I[401 + error=invalid_token]
    V -->|Yes| Q{Claims/token policy valid?}
    Q -->|No| I
    Q -->|Yes| A{Sufficient scope/authority?}
    A -->|No| F[403 + error=insufficient_scope if OAuth2 authentication detected]
    A -->|Yes| D{Data/tenant permissions valid?}
    D -->|No| P[403/404 per domain policy]
    D -->|Yes| OK[Allow controller/service processing]
~~~

This is a **logical** diagram and does not impose the exact same HTTP response on every implementation. For example:

- **invalid_request** per RFC is usually 400; specific malformed header cases may be interpreted differently by the framework.
- An access denied handler may not be able to prove the Authentication is OAuth2; in that case it might only return a generic Bearer challenge rather than **insufficient_scope**.
- A domain policy denying a record may not want to disclose scopes or error descriptions.
- If no Spring Security chain processes the request, you cannot rely on this diagram to infer the API is protected.

## 6. Participating Spring Security Components

In a **Servlet Resource Server**:

~~~mermaid
flowchart LR
    H[Authorization: Bearer token] --> F[BearerTokenAuthenticationFilter]
    F --> M[AuthenticationManager / Provider]
    M --> J[JwtDecoder or OpaqueTokenIntrospector]
    J -->|Failure| E[BearerTokenAuthenticationEntryPoint]
    J -->|Success| A[Authentication in SecurityContext]
    A --> R[authorizeHttpRequests / method security]
    R -->|Insufficient permissions| D[BearerTokenAccessDeniedHandler]
    E --> W[HTTP status + WWW-Authenticate]
    D --> W
    R -->|Sufficient permissions| C[Controller / Service]
~~~

Main components:

| Component | Responsibility |
|---|---|
| **BearerTokenAuthenticationFilter** | Extracts token via BearerTokenResolver and requests authentication |
| **DefaultBearerTokenResolver** | By default finds Bearer token in Authorization header and applies parsing rules |
| **JwtAuthenticationProvider/JwtDecoder** | Verifies JWT signature, issuer, expiration, and configured validators |
| **OpaqueTokenAuthenticationProvider/OpaqueTokenIntrospector** | Checks token via trusted introspection |
| **BearerTokenAuthenticationEntryPoint** | Initiates response when authentication is missing/failed; builds Bearer challenge |
| **BearerTokenAccessDeniedHandler** | Handles access denied, can produce insufficient_scope challenge |
| **BearerTokenError** | Carries error code, HTTP status, description, URI, and scope |
| **BearerTokenErrors** | Factory creating common RFC 6750 errors |
| **ExceptionTranslationFilter** | Dispatches AuthenticationEntryPoint/AccessDeniedHandler when exceptions cross its filter chain |

**BearerTokenAuthenticationEntryPoint** and **BearerTokenAccessDeniedHandler** have distinct roles. They are not the components that decode JWTs or introspect opaque tokens.

### 6.1. BearerTokenAuthenticationEntryPoint

Class:

~~~text
org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint
~~~

This is an **AuthenticationEntryPoint** implementation that uses the **BearerTokenError** inside **OAuth2AuthenticationException** when present to determine the HTTP status and **WWW-Authenticate** parameters.

Examples:

- No token on a protected endpoint → typically builds a **Bearer** challenge with realm if configured, without an error code.
- A token rejected by JwtDecoder → can build a challenge with **error="invalid_token"**.
- A malformed request represented by **BearerTokenError invalid_request** → the entry point can use HTTP status **400** from the error.

The **setRealmName(String)** API configures the default realm.

### 6.2. BearerTokenAccessDeniedHandler

Class:

~~~text
org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler
~~~

This is an **AccessDeniedHandler** implementation for requests denied authorization.

According to Spring Security's Java API, if the handler **has sufficient evidence that the request carries a valid OAuth 2.0 Authentication**, it can return **insufficient_scope**. If it cannot identify such an authentication, the handler typically only emits the **Bearer** scheme and configured realm, rather than unconditionally attaching **insufficient_scope**.

This prevents a false inference:

> Seeing HTTP 403 in Spring Security does not mean the response is guaranteed to contain error="insufficient_scope".

Some 403s come from CSRF, resource/tenant permissions, custom access denied handlers, or other mechanisms. The actual header depends on the **security chain, handler, authentication type, and denial cause**.

### 6.3. BearerTokenError and BearerTokenErrors

Classes in package:

~~~text
org.springframework.security.oauth2.server.resource
~~~

**BearerTokenErrors** provides factory methods such as:

~~~java
BearerTokenErrors.invalidRequest("Malformed bearer request");
BearerTokenErrors.invalidToken("Invalid access token");
BearerTokenErrors.insufficientScope("Insufficient scope", "orders.approve");
~~~

These are error objects; they do not automatically write HTTP responses unless routed through an appropriate handler.

**BearerTokenError** holds fields for error code, HTTP status, description, error URI, and scope. **BearerTokenAuthenticationEntryPoint** knows how to read this data to construct the challenge. When customizing, ensure error descriptions adhere to RFC character sets and never contain tokens/secrets.

## 7. Configuring Resource Server to Generate Bearer Challenges Automatically

A basic Spring Boot configuration for a JWT Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Example Servlet **SecurityFilterChain**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

With suitable default configuration, Spring Security uses Bearer-specific entry points and access denied handlers for the Resource Server.

- **GET /api/orders/42** without a token: usually **401** and a Bearer challenge.
- JWT token with bad signature, issuer, audience, or expired: usually **401** with the corresponding Bearer error.
- Valid token with only **orders.write** calling GET requiring **orders.read**: usually **403** and may include **insufficient_scope**.
- Valid token with proper scope: enters handler; the service still must check permissions on order 42.
- Endpoint **/api/public/** with **permitAll**: does not require authentication to pass the rule, though security filters may still process a Bearer token if the client sends one.

**These statuses/headers are common behavior**, not something to assert byte-for-byte across all Spring Boot/Spring Security versions, because realm settings, handlers, metadata extensions, or custom security can alter them.

## 8. Customizing the Realm with Standard Handlers

Sometimes an API wants to expose a stable realm, such as **orders-api**, so clients or logs can easily distinguish the protection space.

It can be configured as:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ChallengeConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
            new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

**authenticationEntryPoint(entryPoint)** and **accessDeniedHandler(deniedHandler)** apply to the corresponding OAuth2 Resource Server configuration. If the app has multiple SecurityFilterChains, attach the handlers to the chain actually processing the request.

**realm does not mean issuer.** Even if the header has **realm="orders-api"**, it does not replace checking **iss**, **aud**, key sources, or ownership. Realm is HTTP protection-space metadata, not proof the token was issued by an Authorization Server.

### 8.1. Should You Manually Concatenate WWW-Authenticate Strings?

Usually **no**. The standard handlers already know how to extract information from Spring Security exceptions. Manual concatenation:

~~~java
response.setHeader(
    "WWW-Authenticate",
    "Bearer realm=\"" + untrustedValue + "\""
);
~~~

can introduce escaping bugs, header injection, or lose **error/description/scope** details. If a very specific response format is needed, constrain values per the RFC, use trusted configuration sources, and verify with tests.

### 8.2. Some Versions May Add resource_metadata

Newer Spring Security versions may support the extension parameter **resource_metadata** related to OAuth Protected Resource Metadata under **RFC 9728**. This parameter is not one of the five core parameters listed in RFC 6750 §3, though the RFC permits extension auth-params.

Illustrative header pattern on a version supporting the extension:

~~~http
WWW-Authenticate: Bearer realm="orders-api", resource_metadata="https://orders-api.example.com/.well-known/oauth-protected-resource"
~~~

Do not assume every Spring Security version emits **resource_metadata**, or copy the example URL verbatim for every deployment. With proxies/context paths, ensure the metadata endpoint is published accurately and never build URLs from untrusted Host/Forwarded headers.

**resource_metadata** also does not replace **error_uri**: one describes the protected resource, while the other is a documentation URI explaining a specific error.

## 9. Opaque Tokens Also Use the Same Bearer Challenge Style

Switching from JWT configuration to opaque tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: replace-through-secret-manager
~~~

And in SecurityFilterChain:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

The main difference lies in how the **token is validated**:

- JWT: JwtDecoder checks signature, issuer, audience/timestamps per validators.
- Opaque: OpaqueTokenIntrospector contacts the trusted Authorization Server, checking the introspection result and policy.

On the client side, however, the HTTP header remains:

~~~http
Authorization: Bearer <access-token>
~~~

and Resource Server errors still use **Bearer challenges** per RFC 6750 in appropriate cases.

If an opaque token is revoked and the AS returns **active=false**, the Resource Server usually returns **401** with **invalid_token**. If the token is active but lacks **SCOPE_orders.read**, it usually returns **403** with the corresponding challenge.

**Do not distinguish JWT vs. opaque tokens by error codes in WWW-Authenticate.** Those codes describe Bearer authentication/authorization status, not a mandatory disclosure of token representation.

## 10. invalid_request and Where Bearer Tokens Are Presented

RFC 6750 §2 describes three methods to pass an access token to a Resource Server:

1. **Authorization header** — the recommended method, supported by Spring Security by default.
2. **Form-encoded body parameter** under strict specification conditions.
3. **URI query parameter** — only for compatibility in certain cases; discouraged by the RFC because tokens easily leak.

**A Client MUST NOT use more than one method to transmit the token in the same request.** For example, a request with both a Bearer header and an **access_token** query parameter (when the server supports query tokens) can result in **invalid_request**.

### 10.1. Valid Request Using the Authorization Header

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <access-token>
~~~

This is the preferred method. The token must be protected by HTTPS and kept out of logs.

### 10.2. Request Using Two Methods

~~~http
GET /api/orders/42?access_token=<second-token> HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <first-token>
~~~

Per the RFC, sending a token via more than one method in the same request is invalid. When the resolver **is configured to allow reading query tokens**, it can detect the duplicate and report **invalid_request**.

**However, Spring Security's DefaultBearerTokenResolver does not accept tokens from URI query or form body by default.** Therefore, do not claim it will definitely report a duplicate-method error under default configuration if one method is disabled. When testing security, verify the actual **BearerTokenResolver** configuration.

### 10.3. DefaultBearerTokenResolver

In Servlet Resource Server:

~~~text
org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver
~~~

Options to know:

| API | Default and Meaning |
|---|---|
| **setAllowUriQueryParameter(boolean)** | Default **false**, does not read Bearer tokens from URL query |
| **setAllowFormEncodedBodyParameter(boolean)** | Default **false**, does not read tokens from form body |
| **setBearerTokenHeaderName(String)** | Default **Authorization**; can change to another header when needed |

Do not enable query-parameter token transmission just for convenient testing. URLs easily end up in browser history, proxy access logs, referers, telemetry, or bookmarks. Prefer the Authorization header over HTTPS.

### 10.4. Malformed Requests Do Not Always Have the Same Status Across All Parsers

Per the RFC, **invalid_request/400** is the typical model for malformed Bearer requests. In Spring Security, however, specific code paths may create:

- **BearerTokenErrors.invalidRequest(...)** for requests with multiple tokens.
- **BearerTokenErrors.invalidToken(...)** for certain malformed Bearer headers.

Thus, if a test expects **400** for all malformed Authorization strings, it may not match the implementation/version. Verify the **error code and HTTP status** actually produced by your BearerTokenResolver/entry point.

Never change **invalid_token** to **insufficient_scope** just to make the client ask for more permissions; the two errors have different causes and remedies.

## 11. What Appears on 403?

A 403 response can originate from multiple mechanisms:

| Cause | Characteristic |
|---|---|
| Valid OAuth2 token lacking scope/authority | May be rendered as **insufficient_scope** |
| Insufficient application role/permission | AccessDeniedException, may be handled by a custom handler |
| Ownership/tenant check failed | Domain policy denial; may return 403/404 |
| CSRF rejects request in CSRF-protected app | Does not mean missing OAuth scope |
| Access denied from a non-OAuth2 Resource Server chain | Not guaranteed to use Bearer-specific handler |

Per JavaDoc, **BearerTokenAccessDeniedHandler** only emits **insufficient_scope** when it has sufficient basis that the authentication is a valid OAuth2 one. Otherwise, it may only return the Bearer scheme/realm.

### 11.1. Example: Scope Differs from Role

Authentication has:

~~~text
SCOPE_orders.read
ROLE_SUPPORT
~~~

Endpoint requires:

~~~java
.hasRole("ADMIN")
~~~

Fails due to missing **ROLE_ADMIN**. Returning 403 is proper per policy, yet the client **cannot infer** that adding the OAuth2 scope orders.write will satisfy hasRole ADMIN.

If the API uses non-scope authorities, design error messages responsibly. Do not automatically emit **scope="ADMIN"** if ADMIN is an internal role rather than an OAuth scope issued by the Authorization Server.

### 11.2. Should scope in the Challenge Be Exposed?

**scope** is an optional auth-param. If included, ensure:

- The scope truly belongs to the API's OAuth2 contract.
- The scope name matches exact case sensitivity.
- Internal permission names/details that should not be publicized are not leaked.
- The client understands it is a scope to request from the Authorization Server, **not a value for the client to write into the token**.
- When an endpoint has complex permission conditions, avoid emitting incomplete/misleading scope hints.

Rules like **hasAuthority("SCOPE_...")** do not necessarily make Spring Security infer the required scope name to insert into WWW-Authenticate. If specific scope reporting is needed, design/customize it appropriately.

## 12. How Should Clients Handle Bearer Challenges?

On the API client side, classify at minimum:

| HTTP/challenge | Reasonable Handling |
|---|---|
| **401 Bearer, no error** | No credential sent or unauthenticated; determine how to obtain a valid access token |
| **401 + invalid_token** | Do not reuse the rejected token; try obtaining a new token per OAuth flow/refresh policy |
| **400 + invalid_request** | Fix Bearer token structure/transmission method; do not retry the exact request infinitely |
| **403 + insufficient_scope** | Identify needed permissions and check whether the user/client can be granted that scope |
| **403 without insufficient_scope** | Likely another authorization/domain policy; do not assume refreshing the token will fix it |
| **5xx from API/upstream authentication** | Handle transient errors with appropriate retry/backoff; do not broadcast credentials |

A client **must not** blindly loop refreshing tokens and resending infinitely on every 401. If issuer, audience, resource, or scope is mismatched, fetching another access token of the same kind will keep failing. Cap retries and handle configuration errors.

### 12.1. WWW-Authenticate Is Not an OAuth Token Response

The Authorization Server returns a **token response** with fields like **access_token**, **token_type**, and **expires_in** when issuing a token successfully. The Resource Server returns **WWW-Authenticate** when challenging access to a protected resource.

For example, do not interpret:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

as a mandatory redirect URL, an authorization endpoint, or an instruction to send a **client secret** to the Resource Server. It merely describes the HTTP authentication scheme of the protected resource.

### 12.2. 401 Is Not an Invitation to Switch to HTTP Basic

If the Resource Server sends a **Bearer** challenge, the client should use an OAuth2 Bearer access token. Switching to Basic username/password for the API endpoint is not the right approach unless the API explicitly advertises and permits separate Basic authentication.

## 13. Testing with curl: Inspecting Status and Headers

Suppose an Orders API in a test environment:

~~~text
https://orders-api.example.com/api/orders/42
~~~

### 13.1. Sending No Token

~~~bash
curl --include --silent --show-error \
  https://orders-api.example.com/api/orders/42
~~~

Observe:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

An actual response may differ in realm or extension auth-params. Key criterion: **a protected endpoint must not pass just because the request lacks a token** and must include a suitable Bearer challenge.

### 13.2. Sending an Invalid Token

~~~bash
curl --include --silent --show-error \
  -H "Authorization: Bearer not-a-valid-access-token" \
  https://orders-api.example.com/api/orders/42
~~~

Typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Never put real credentials into examples, logs, or tickets. Strings in examples are hypothetical for learning.

### 13.3. Sending a Valid Token Missing Scope

Requires a **test token** issued by a test issuer, with the right audience but lacking **orders.read**.

~~~bash
curl --include --silent --show-error \
  -H "Authorization: Bearer <valid-test-token-without-orders-read>" \
  https://orders-api.example.com/api/orders/42
~~~

Response may be:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

With custom configuration, **realm** and **scope** may be present. Never type raw production tokens into shells with uncontrolled history/logs. Use appropriate test environments and test tokens.

### 13.4. When curl Sees the Header, but the Browser Cannot Read It

Browser JavaScript running a **cross-origin fetch** may be restricted by CORS from reading response headers. **WWW-Authenticate is not a CORS-safelisted response header by default**.

If the app needs the frontend to read this header, the server's CORS policy may need to explicitly expose it:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

This setting **does not grant API access** and does not replace JWT verification. It only allows browser JavaScript to read the header under CORS policy. Also configure allowed origins, methods, credentials, and preflight properly; never open CORS unconditionally.

## 14. Testing Spring Security with MockMvc

For Servlet Spring Security, you can use **MockMvc with security filters enabled** to verify responses.

### 14.1. Testing Requests Without a Token

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

// Inside a test class with MockMvc injected and the real SecurityFilterChain loaded.
@Test
void protectedEndpointWithoutTokenHasBearerChallenge() throws Exception {
    mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("Bearer")
        ));
}
~~~

If the application config sets a realm, you can also assert the realm. However, do not require **error="invalid_token"** for a request containing no token, because the RFC recommends omitting error info in that case.

### 14.2. Testing a Fake Token Rejected by the Decoder

An integration test should configure **JwtDecoder** with an appropriate test issuer/key or mock the decoder to **actively throw JwtException** when receiving a fake token. Then send a real Authorization header through the security filters and assert status 401 and the Bearer challenge.

Example request assertion, assuming the test fixture guarantees the decoder rejects the token:

~~~java
@Test
void invalidJwtHasInvalidTokenChallenge() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer a-rejected-test-token"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("invalid_token")
        ));
}
~~~

**Only use the assertion above when the decoder/test fixture definitely rejects the input token**. If the test does not run a real JwtDecoder, the result does not prove production signature verification. A MockMvc test using only the **jwt() request post-processor** also typically skips the JWT signature decoding step.

### 14.3. Testing Missing Scope with a Mocked Authentication

Spring Security Test provides **jwt()** to create an Authentication in authorization tests:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void validAuthWithoutReadScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}
~~~

The test above checks the **hasAuthority("SCOPE_orders.read")** rule. It does not prove the token was signed by an issuer or that the decoder ran. If you want to assert **insufficient_scope** in WWW-Authenticate, test with an **appropriate BearerTokenAccessDeniedHandler** and an OAuth2-shaped Authentication recognized by the handler.

### 14.4. Keep Header Assertions Reasonably Flexible

Do not only assert:

~~~java
header().string(HttpHeaders.WWW_AUTHENTICATE,
    "Bearer realm=\"orders-api\"")
~~~

in every test, if the framework might add **resource_metadata** or version-dependent error details. You can:

- Assert **HTTP status** explicitly.
- Assert header presence and that it contains **Bearer**.
- Assert **error="invalid_token"** or **error="insufficient_scope"** in tests whose setup genuinely triggers those cases.
- Assert realm and scope if they are part of the **application contract**.
- When parser-level compliance is needed, use a proper parser instead of substring matching that could match inside description text.

Some tests may check exact headers to pin an API contract, provided it is intentional with stable test fixtures/versions.

### 14.5. Testing Non-Existent Handlers Does Not Have the Same Value

If calling a non-existent URL returns **404**, you cannot conclude Spring Security returned the right Bearer challenge for a protected endpoint. Tests must call an **endpoint with a real handler** or a test-only route, with security filters enabled.

**@AutoConfigureMockMvc(addFilters=false)** or **standaloneSetup** does not run the production filter chain automatically. When testing security responses, attach **springSecurityFilterChain** or use a Spring Boot test context with filters.

## 15. Risks When Middleware/Proxies Modify Responses

The challenge is generated at the Resource Server, but may pass through a gateway, ingress, or reverse proxy.

Common operational bugs:

- Gateway **strips WWW-Authenticate** and only keeps status 401.
- Gateway **turns 401 into a 302 redirect** to an HTML login page, breaking OAuth API clients.
- Proxy returns 401 from another authentication scheme like Basic, masking the backend's Bearer challenge.
- API Gateway generates its own 403 without using the same Bearer policy.
- CORS prevents browsers from reading WWW-Authenticate.
- Response cache/CDN mistakenly caches responses containing sensitive metadata or mixes responses across users.
- Application exception handler converts all authentication failures into 200 with JSON **success=false**.

**An API with a correct SecurityFilterChain does not guarantee external users receive the right headers** if a proxy alters responses. Test directly against the **backend** and through the **actual public URL**.

### 15.1. Multiple WWW-Authenticate Challenges

Per HTTP, a server may advertise multiple authentication schemes or multiple challenges. When passing through proxies, ensure header fields are forwarded/combined per HTTP semantics so parsers do not lose the Bearer challenge.

Do not mix challenges with **Proxy-Authenticate**: **WWW-Authenticate** is the challenge for the origin resource, whereas Proxy-Authenticate relates to proxy authentication.

### 15.2. Reverse Proxies and Trusted Scheme/Host

If the framework constructs extension URLs (such as resource_metadata), reverse proxy configuration can affect the external scheme/host. Never trust **Host**, **Forwarded**, or **X-Forwarded-*** from untrusted clients to construct metadata URLs pointing to an attacker. Only honor forwarded headers from authenticated/managed proxies.

## 16. Do Not Use WWW-Authenticate as an Information-Leak Channel

Response headers are observable by the client. Therefore:

- Do not include **raw access tokens**, refresh tokens, client secrets, or private signing keys in error_description.
- Do not expose stack traces, file paths, database queries, key material, or internal configuration.
- Do not directly echo unvalidated values from the request into headers.
- Do not use overly granular error descriptions distinguishing whether a token exists/expired/was revoked if doing so aids token probing.
- Limit information about sensitive scopes/roles; only advertise scopes permitted by the API contract.
- Record errors via controlled request IDs/metrics without logging the Authorization header.
- Use HTTPS to protect Bearer tokens in requests; WWW-Authenticate does not replace TLS.
- Beware of HTTP response splitting/CRLF injection when customizing headers.

A good error for a client is **actionable**, without reciting every internal security detail.

### 16.1. error_uri Should Point to Stable Documentation

If providing **error_uri**, use a public, stable, accessible documentation URL:

~~~http
WWW-Authenticate: Bearer error="invalid_token", error_uri="https://docs.example.com/api/auth/errors#invalid-token"
~~~

Do not put internal URIs or tokens in the query string. **error_uri** is not an automatic access-token refresh channel and should never cause clients to send credentials to unfamiliar URLs.

### 16.2. Do Not Treat realm as an Authorization Boundary

For example:

~~~http
WWW-Authenticate: Bearer realm="tenant-a"
~~~

does not prove tenant A is the issuer or that the client is authorized for tenant A. **Realm** is just challenge metadata. The Resource Server still must verify signature/introspection, issuer, audience, and tenant/ownership policies independently.

## 17. Several 401/403/400 Situations to Distinguish

| Request/Condition | Typical HTTP | Bearer Challenge |
|---|---|---|
| Protected endpoint, no Authorization | **401** | **Bearer** with realm if configured; usually no error |
| JWT sent, but bad signature | **401** | **error="invalid_token"** |
| JWT valid signature, wrong issuer/audience | **401** | **error="invalid_token"** |
| JWT expired | **401** | **error="invalid_token"**, description if publicized |
| Opaque token with AS returning active=false | **401** | **error="invalid_token"** |
| Multiple tokens sent via multiple methods detected by resolver | **400** per RFC recommendation | **error="invalid_request"** |
| Malformed Bearer header | Depends on resolver/version error | May be invalid_token or invalid_request |
| Valid token, missing required scope | **403** | Possibly **error="insufficient_scope"** |
| Valid token, has scope, does not own resource | **403** or **404** per domain policy | Not required to expose scope |
| Matches no SecurityFilterChain | Cannot infer | Not guaranteed to have Bearer challenge |
| CORS preflight OPTIONS | Depends on CORS/security policy | Not proof GET/POST request is authenticated |
| Introspection upstream timeout | Auth infrastructure failure | Do not fail open; status/headers per exception mapping |

**Never use a single HTTP status to conclude whether a request passed JWT validation.** Inspect the SecurityFilterChain, exception path, Authentication type, and actual headers.

## 18. Troubleshooting When WWW-Authenticate Differs from Expectations

### 18.1. API Returns 401 Without WWW-Authenticate

Possible causes:

- A controller returned 401 manually, bypassing the Bearer entry point.
- A custom AuthenticationEntryPoint set the status but omitted the header.
- Request did not match the intended SecurityFilterChain.
- API Gateway or reverse proxy stripped the header.
- Browser CORS did not expose the header to JavaScript.
- Another security chain with form login/Basic matched first.

How to check: call the backend directly in an allowed environment with **curl -i**, inspect chain/filter configuration, then compare with responses through the public gateway.

### 18.2. API Returns Login HTML or 302 Instead of a Bearer Challenge

The Resource Server chain may not have been selected while a web-login security chain was matched instead. Check **@Order**, **securityMatcher**, **ExceptionTranslationFilter**, and the Resource Server DSL.

A pure API should normally return explicit status/challenges rather than redirecting to an HTML login page, unless the architecture intentionally supports another flow.

### 18.3. API Returns 403 Without insufficient_scope

It could be:

- A domain-level AccessDeniedException, not directly caused by OAuth scopes.
- An Authentication type that BearerTokenAccessDeniedHandler cannot prove is OAuth2.
- A customized AccessDeniedHandler.
- CSRF or another policy.
- Header hidden by proxy/CORS.

Do not force every 403 to emit **insufficient_scope**, as it misleads clients into the wrong recovery action.

### 18.4. Client Receives invalid_token Even Though JWT Decodes Cleanly

A JWT can be Base64URL-decoded yet fail signature, issuer, audience, expiration, or token type checks. **Reading claims does not replace verifying the JWT**, and a token signed by the issuer for another API must still be rejected.

### 18.5. Client Receives invalid_request for Multiple Tokens

Check the Authorization header, query parameters, form body, and resolver configuration. Do not send the token in two locations simultaneously. Avoid enabling query-parameter tokens just for debugging convenience.

### 18.6. Header Unexpectedly Contains resource_metadata

This may be an extension from a newer Spring Security release related to OAuth Protected Resource Metadata. Check the framework version and Resource Server configuration. Do not treat it as invalid_request just because the original RFC 6750 did not list that parameter.

### 18.7. Error Description Contains Invalid Characters

When building headers manually, accented characters, quotes, or newlines may violate RFC 6750 character sets. Avoid putting arbitrary Unicode text into auth-params; put localized messages in the response body per API contract and keep headers standard-compliant.

## 19. Bearer Error Response Design Checklist

Before putting an API into production, verify:

1. Does a **protected endpoint without a token** return HTTP 401 and a Bearer challenge?
2. Is **missing** token distinguished from **invalid** token, avoiding detailed errors when no credential was supplied?
3. Are invalid JWT/opaque tokens processed through a trusted JwtDecoder/introspection before producing errors?
4. Does a valid token lacking scope return **403**, without being mistaken for a signature failure?
5. Are **BearerTokenAuthenticationEntryPoint** and **BearerTokenAccessDeniedHandler** wired to the right SecurityFilterChain?
6. Does any other chain or proxy alter statuses/headers?
7. If customizing the realm, do all related chains use a consistent realm?
8. Do **error_description**, **error_uri**, and **scope** avoid leaking info/credentials and conform to RFC character rules?
9. Does any custom JSON error template preserve WWW-Authenticate when required?
10. Does CORS expose WWW-Authenticate to the frontend when genuinely needed?
11. Do tests distinguish **401 missing token**, **401 invalid_token**, **400 invalid_request** where applicable, and **403 insufficient permissions**?
12. Does MockMvc enable security filters and use real handlers?
13. Do tests passing through the gateway/ingress produce the same results as direct backend tests?
14. Does the client bound retries/token refreshes and refrain from self-escalating scopes?
15. Is there a test for a malformed bearer header on the exact Spring Security version rather than assuming a fixed status?

## 20. Practice Exercises

Suppose the Orders API has this policy:

~~~text
Issuer: https://login.example.com/realms/shop
Audience: orders-api
GET /api/orders/**  -> SCOPE_orders.read
POST /api/orders/** -> SCOPE_orders.write
Realm: orders-api
~~~

Predict the responses:

**A. GET /api/orders/42 without an Authorization header**

An appropriate response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

**error** is not required.

**B. GET /api/orders/42 with a fake JWT and bad signature**

An appropriate response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Even if the JWT claims the right iss/aud/scope, the signature is not verified by the issuer and is therefore invalid.

**C. POST /api/orders/42 with only the orders.read scope**

An appropriate response:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

The **scope** parameter is optional. The client needs a token issued with the appropriate scope via an OAuth flow; never edit the JWT payload manually.

**D. GET /api/orders/42 with both Authorization Bearer and access_token query**

If the Resource Server is configured to read both locations and detects a duplicate-method token:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
~~~

However, if the default resolver **does not** read query tokens, actual behavior may differ. The exercise requires stating the **resolver configuration** before predicting.

**E. GET /api/orders/42 with a valid token, but the order belongs to another tenant**

This is a **domain authorization failure**. It may return 403 or 404 per resource-protection policy; it does not have to advertise **scope** or **insufficient_scope** when the cause is not a missing OAuth scope.

### 20.1. Exercise: Identify Spring Security Components

Fill in the roles:

| Component | Responsibility |
|---|---|
| **DefaultBearerTokenResolver** | Locates/reads Bearer token from request |
| **BearerTokenAuthenticationFilter** | Sends token through authentication flow |
| **JwtDecoder/OpaqueTokenIntrospector** | Verifies token against trusted source |
| **BearerTokenAuthenticationEntryPoint** | Returns challenge for authentication failures |
| **BearerTokenAccessDeniedHandler** | Handles access denial and appropriate challenge |
| **BearerTokenErrors** | Creates standard BearerTokenError objects like invalid_token |
| **authorizeHttpRequests** | Enforces authority/role/policy checks on requests |

Specifically, **ExceptionTranslationFilter** coordinates exceptions thrown downstream in the filter chain, whereas **BearerTokenAuthenticationFilter** may invoke the entry point directly when Bearer authentication fails. This explains why not all errors pass through the exact same handler.

## Conclusion

**WWW-Authenticate** is the response header carrying the authentication challenge. For OAuth 2.0 Resource Servers, **RFC 6750** defines the Bearer challenge and the error codes **invalid_request**, **invalid_token**, and **insufficient_scope**, typically paired with statuses **400**, **401**, and **403**.

The most critical distinctions are:

- **Missing token:** 401 + Bearer challenge, usually **no error**.
- **Invalid token:** 401 + **invalid_token**.
- **Valid token missing scope:** 403 + **insufficient_scope** when handled under OAuth2 Bearer and the handler has sufficient info.
- **Malformed token submission:** possibly **invalid_request/400**, depending on policy and implementation.

In Spring Security Servlet Resource Server, **BearerTokenAuthenticationEntryPoint** handles authentication challenges, **BearerTokenAccessDeniedHandler** handles access denial, and **BearerTokenError** supplies error metadata. Never construct headers without validation, never treat an HTTP status alone as proof a JWT was verified, and never let an API Gateway, CORS, or custom exception handler strip required Bearer challenges.

### References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Sections 3 and 3.1](https://www.rfc-editor.org/rfc/rfc6750#section-3)
- [RFC 9110 — HTTP Semantics: WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110#section-11.6.1)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [Spring Security — Servlet OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [Spring Security API — BearerTokenError](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/BearerTokenError.html)
- [Spring Security API — BearerTokenErrors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/BearerTokenErrors.html)
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html)
