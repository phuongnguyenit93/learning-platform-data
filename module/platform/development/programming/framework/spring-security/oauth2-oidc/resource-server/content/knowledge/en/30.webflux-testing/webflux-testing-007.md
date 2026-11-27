# Testing 401, 403, Challenges, and API Error Responses

## 1. Distinguishing Authentication from Authorization

A Spring Security WebFlux Resource Server must answer two independent questions:

1. Has the caller been authenticated with a valid credential?
2. Is the authenticated principal permitted to perform this action?
**401 Unauthorized**: the request lacks valid authentication. Possible causes include a missing Bearer token, an invalid JWT signature, expiration, wrong issuer/audience, or introspection reporting inactive.

**403 Forbidden**: the principal is authenticated but is not allowed to perform the action. Examples include missing scope, not belonging to the tenant, or not owning the resource.

Example:

~~~text
GET /api/orders
No Authorization header
  -> No authentication
  -> 401 + WWW-Authenticate: Bearer

GET /api/orders
Authorization: Bearer <expired-token>
  -> Invalid credential
  -> 401 + Bearer error="invalid_token"

POST /api/orders
Authorization: Bearer <valid-token-with-orders.read>
  -> Authentication succeeded, missing orders.write
  -> 403 + Bearer error="insufficient_scope" when appropriate

POST /api/orders
Authorization: Bearer <valid-token-with-orders.write>
  -> Authentication and authorization passed
  -> API proceeds with business processing
~~~

**401 is an authentication error; 403 is an authorization error.** Do not return 403 for an expired token, and do not force the client to re-authenticate merely because a valid principal lacks permission.

Some 403 responses may come from CSRF, CORS, a gateway, or network policy. Always identify the exact component that rejected the request.

## 2. WebFlux Resource Server Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux Security Filters
    participant B as Bearer Converter
    participant M as ReactiveAuthenticationManager
    participant D as JWT Decoder / Opaque Introspector
    participant A as Authorization
    participant H as Handler

    C->>W: Request + Authorization Bearer
    W->>B: Extract credential
    B-->>W: Bearer authentication request
    W->>M: authenticate
    M->>D: verify JWT or introspect opaque token
    alt Authentication fails
      D-->>M: Authentication exception
      M-->>W: Failure
      W-->>C: AuthenticationEntryPoint -> 401
    else Authentication succeeds
      D-->>M: Valid principal
      M-->>W: Authentication
      W->>A: Check authority and access rules
      alt Authorization denied
        A-->>W: AccessDeniedException
        W-->>C: AccessDeniedHandler -> 403
      else Authorization granted
        A->>H: Invoke handler
        H-->>C: API response
      end
    end
~~~

Components:

| Component | Role |
|---|---|
| **ServerBearerTokenAuthenticationConverter** | Extracts the Bearer token from `ServerWebExchange` |
| **AuthenticationWebFilter** | Executes reactive authentication |
| **ReactiveAuthenticationManager** | Authenticates credentials per the configured strategy |
| **ReactiveJwtDecoder** | Verifies and validates JWTs |
| **ReactiveOpaqueTokenIntrospector** | Verifies opaque tokens via introspection |
| **ExceptionTranslationWebFilter** | Translates authentication/authorization exceptions into HTTP responses |
| **ServerAuthenticationEntryPoint** | Initiates the authentication challenge, typically 401 |
| **ServerAccessDeniedHandler** | Handles authorization denial, typically 403 |
| **SecurityWebFilterChain** | Chain of WebFilters protecting requests |
| **ServerHttpSecurity** | DSL for configuring WebFlux Security |

The Servlet stack uses differently named APIs: AuthenticationEntryPoint, AccessDeniedHandler, HttpSecurity, and SecurityFilterChain. This lesson focuses on **WebFlux reactive APIs**.

### Authentication Failures Occur Before the Controller

An invalid-signature JWT is typically rejected in AuthenticationWebFilter/the Resource Server flow before the controller runs. Therefore, **@RestControllerAdvice** is not the primary place to handle Bearer challenges.

Authorization can fail at `authorizeExchange` in the filter chain or at reactive method security such as `@PreAuthorize`.

## 3. 401: Missing or Invalid Authentication

| Scenario | Cause | Typical outcome |
|---|---|---|
| No Authorization sent on protected route | Missing credential | 401 challenge |
| Bearer header without a token | Malformed request | 400 invalid_request or corresponding parser error |
| Malformed token | Unable to parse credential | 401 invalid_token |
| Invalid JWT signature | Unable to verify signing source | 401 invalid_token |
| Wrong JWT issuer | Outside trust domain | 401 invalid_token |
| Wrong JWT audience | Token not intended for this API | 401 invalid_token |
| Expired JWT | `exp` passed per time policy | 401 invalid_token |
| JWT before `nbf` | Token not yet valid | 401 invalid_token |
| Opaque token `active=false` | AS does not confirm token active | 401 invalid_token |
| Wrong token type/profile | Does not match access-token contract | 401 invalid_token |

For a protected resource, a request lacking valid authentication typically receives:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When a caller sends a Bearer token that is invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

### Missing Token vs. Invalid Token

When the caller sends no authentication information, the server usually sends a challenge without an error code. When the caller presents a token that is invalid, the challenge may include `error="invalid_token"`.

This distinction helps clients understand:
- No token: obtain a credential.
- Invalid/expired token: may need to request a new token.
- Insufficient scope: needs appropriate permissions or a different grant.

Never include raw JWTs, key IDs, internal JWKS URLs, stack traces, or full claims in error responses.

## 4. 403: Authenticated Principal Is Not Permitted

Suppose the JWT has been verified:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794731400
}
~~~

GET may be allowed, whereas POST requiring `orders.write` will be denied:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

When appropriate, the challenge can specify the required scope:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

**403 does not mean the token is invalid.** It can mean the token is valid but lacks sufficient permission.

### 403 Is Not Always insufficient_scope

A request may be denied because:
- The user does not belong to the tenant owning the resource.
- The user is not the owner of the order.
- The order is in a state that forbids modification.
- Domain policy prohibits the action.
- A CSRF token is missing or invalid.
- Gateway/IP/network policy denied the request.
- Another internal role is required.

Do not attach `insufficient_scope` to every AccessDeniedException. If the token already has the required scope yet fails a tenant check, the `insufficient_scope` error code can mislead the client.

## 5. Three Bearer Error Codes per RFC 6750

| Error | Typical HTTP status | Meaning |
|---|---:|---|
| **invalid_request** | 400 | Request passes Bearer credentials improperly, omits a field, or uses conflicting token-delivery methods |
| **invalid_token** | 401 | Token is expired, revoked, malformed, or invalid |
| **insufficient_scope** | 403 | Token lacks the scope required for the resource |

Examples:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

Parameters such as `realm`, `error_description`, and `error_uri` are optional per contract. Not every response needs all of them.

### Do Not Leak Information in error_description

Do not send:
- Raw access tokens.
- Signatures, private keys, or shared secrets.
- Stack traces.
- Full JWT claims/PII.
- JWKS hosts or internal topology.
- Account-lock details if doing so discloses sensitive information.

Safe messages can be **The access token is invalid** or **The request is not permitted**. Record technical details in controlled logs tagged with a correlation ID.

## 6. WWW-Authenticate Is Part of the HTTP Response

For HTTP 401, the server must send at least one `WWW-Authenticate` challenge per HTTP semantics. For OAuth Bearer, the authentication scheme is `Bearer`.

Simple challenge:

~~~http
WWW-Authenticate: Bearer
~~~

With realm:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Invalid token:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Insufficient scope:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Clients use the challenge to determine the scheme, credential state, required scope, and whether to acquire a new token. A JSON body does not replace the challenge header.

Never concatenate raw exception messages or caller input into the challenge header. Use Spring Security's Bearer handlers to preserve grammar and semantics.

## 7. Built-in Reactive Handlers in Spring Security

| Class | Package | Responsibility |
|---|---|---|
| **BearerTokenServerAuthenticationEntryPoint** | org.springframework.security.oauth2.server.resource.web.server | Builds the Bearer challenge when authentication fails |
| **BearerTokenServerAccessDeniedHandler** | org.springframework.security.oauth2.server.resource.web.server | Handles access denied and Bearer challenges when appropriate |

Interfaces:

| Interface | Package | Method |
|---|---|---|
| **ServerAuthenticationEntryPoint** | org.springframework.security.web.server | commence(ServerWebExchange, AuthenticationException) |
| **ServerAccessDeniedHandler** | org.springframework.security.web.server.authorization | handle(ServerWebExchange, AccessDeniedException) |

Reactive signatures:

~~~java
Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception);

Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException exception);
~~~

Handlers return **Mono<Void>**. Never use `HttpServletResponse.sendError()` or Servlet `AuthenticationEntryPoint` in WebFlux.

When configuring:

~~~java
.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()))
~~~

Spring Security sets up Bearer authentication behavior and the appropriate handlers. You do not need to write a custom entry point just to get standard 401/403 behavior.

If you want a custom JSON error body, you can decorate the built-in handlers to preserve the status/challenge and then write the body.

## 8. Configuring ServerHttpSecurity for 401 and 403

WebFlux JWT Resource Server example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        BearerTokenServerAuthenticationEntryPoint entryPoint =
                new BearerTokenServerAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenServerAccessDeniedHandler deniedHandler =
                new BearerTokenServerAccessDeniedHandler();

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Meaning:
- `ServerHttpSecurity` is the WebFlux DSL.
- `BearerTokenServerAuthenticationEntryPoint` creates the 401 challenge.
- `setRealmName` sets the realm.
- `BearerTokenServerAccessDeniedHandler` handles 403.
- `exceptionHandling` configures handlers for exception translation.
- `oauth2ResourceServer` configures handlers for the Bearer authentication path.
- Authorization rules distinguish read and write scopes.

DSL methods may change across Spring Security versions. Check your actual dependency if a method is unavailable. Never substitute Servlet handlers for reactive handlers.

Opaque tokens share the same error boundary:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .authenticationEntryPoint(entryPoint)
        .accessDeniedHandler(deniedHandler)
        .opaqueToken(Customizer.withDefaults()))
~~~

An opaque token with `active=false` typically leads to authentication failure/401. An active token missing a scope leads to authorization denial/403.

## 9. Missing Token, Malformed Bearer, and Invalid Token

Missing token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
~~~

Protected routes typically return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Malformed Bearer header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer
~~~

This may return `400 invalid_request` depending on the parser and version. Test against your actual Spring Security version rather than assuming all malformed headers map identically.

Token sent but invalid:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer expired-or-invalid-token
~~~

Typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Do not use an `access_token` query parameter as a fallback when the Bearer header is invalid. RFC 6750 recommends clients use only one method to transmit a Bearer token per request.

## 10. Missing Scope vs. Domain Permission

A token with only `orders.read`:

~~~json
{
  "scope": "orders.read"
}
~~~

When POST requires `orders.write`, the authorization manager denies it. This is the right case for `insufficient_scope`.

However, a token with `orders.write` still might not be allowed to edit an order belonging to another tenant:

~~~text
Authentication:
  SCOPE_orders.write

Domain:
  order 42 belongs to tenant-blue
  caller belongs to tenant-red
~~~

This is a domain authorization failure. The API can return a generic 403:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
~~~

There is no need to add Bearer `insufficient_scope` because the token already has the scope. The client needs to know the action is forbidden by resource policy.

Some APIs return 404 instead of 403 to avoid disclosing whether a resource exists to unauthorized callers. That is a security/domain contract choice, not a mandatory rule.
## 11. Custom JSON Error Body While Preserving the Bearer Challenge

Many APIs want to return Problem Details or a unified JSON format. You can delegate to the Bearer handler first to preserve the status and challenge, then write the body.

Authentication entry point example:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.Map;

public final class JsonBearerAuthenticationEntryPoint
        implements ServerAuthenticationEntryPoint {

    private final BearerTokenServerAuthenticationEntryPoint delegate;
    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.delegate = new BearerTokenServerAuthenticationEntryPoint();
        this.delegate.setRealmName("orders-api");
    }

    @Override
    public Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException exception) {

        return delegate.commence(exchange, exception)
                .then(Mono.defer(() -> writeBody(exchange)));
    }

    private Mono<Void> writeBody(ServerWebExchange exchange) {
        var response = exchange.getResponse();
        int status = response.getStatusCode() != null
                ? response.getStatusCode().value()
                : 401;

        Map<String, Object> body = Map.of(
                "type", "about:blank",
                "title", status == 400
                        ? "Invalid authentication request"
                        : "Unauthorized",
                "status", status,
                "code", "authentication_failed",
                "detail", "A valid Bearer credential is required");

        byte[] bytes;
        try {
            bytes = objectMapper.writeValueAsBytes(body);
        }
        catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        response.getHeaders().setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl(CacheControl.noStore());

        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }
}
~~~

Key points:
- The delegate sets the status and `WWW-Authenticate` per Bearer semantics.
- The JSON body only supplements the API representation.
- The body contains no raw exception messages or raw tokens.
- `Cache-Control: no-store` prevents caching error responses with unnecessary metadata.
- Do not overwrite `WWW-Authenticate` with a generic header after the delegate has built the challenge.

### Custom Access Denied JSON Body

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.Map;

public final class JsonBearerAccessDeniedHandler
        implements ServerAccessDeniedHandler {

    private final ServerAccessDeniedHandler delegate =
            new BearerTokenServerAccessDeniedHandler();

    private final ObjectMapper objectMapper;

    public JsonBearerAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            AccessDeniedException exception) {

        return delegate.handle(exchange, exception)
                .then(Mono.defer(() -> writeBody(exchange)));
    }

    private Mono<Void> writeBody(ServerWebExchange exchange) {
        var response = exchange.getResponse();

        Map<String, Object> body = Map.of(
                "type", "about:blank",
                "title", "Forbidden",
                "status", 403,
                "code", "access_denied",
                "detail", "The authenticated principal cannot access this resource");

        byte[] bytes;
        try {
            bytes = objectMapper.writeValueAsBytes(body);
        }
        catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        response.getHeaders().setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl(CacheControl.noStore());

        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }
}
~~~

This decorates the handler rather than re-implementing the entire Bearer protocol. Test the handler with your actual Spring Security version to confirm the delegate has not already committed the response before the body is written.

Attaching custom handlers:

~~~java
@Bean
SecurityWebFilterChain api(
        ServerHttpSecurity http,
        ObjectMapper objectMapper) {

    ServerAuthenticationEntryPoint entryPoint =
            new JsonBearerAuthenticationEntryPoint(objectMapper);

    ServerAccessDeniedHandler deniedHandler =
            new JsonBearerAccessDeniedHandler(objectMapper);

    return http
            .authorizeExchange(auth ->
                    auth.anyExchange().authenticated())
            .exceptionHandling(ex -> ex
                    .authenticationEntryPoint(entryPoint)
                    .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth2 -> oauth2
                    .authenticationEntryPoint(entryPoint)
                    .accessDeniedHandler(deniedHandler)
                    .jwt(Customizer.withDefaults()))
            .build();
}
~~~

Ensure imports are the reactive interfaces. Never use Servlet `AuthenticationEntryPoint`/`AccessDeniedHandler` in WebFlux.

## 12. Why @RestControllerAdvice Does Not Replace Security Handlers

A `@RestControllerAdvice` can handle errors from controllers/application handlers:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<?> handleNotFound(OrderNotFoundException ex) {
        // Return appropriate domain error.
        return ResponseEntity.notFound().build();
    }
}
~~~

However, authentication can fail **before the controller is called** inside `AuthenticationWebFilter`. Authorization can be handled in `ExceptionTranslationWebFilter` or method security.

Therefore:
- Use **ServerAuthenticationEntryPoint** for authentication challenges.
- Use **ServerAccessDeniedHandler** for access denied.
- Use **@RestControllerAdvice** for appropriate application/domain exceptions.
- Never catch every `Throwable` and return HTTP 200.
- Never swallow `AuthenticationException`/`AccessDeniedException` to let the request continue.

If a custom `WebExceptionHandler` has high precedence, ensure it does not write a response before security handlers or lose challenge semantics.

## 13. Distinguishing Authentication, Authorization, and Dependency Failures

| Error source | Example | Possible HTTP mapping |
|---|---|---|
| Bearer parser | Malformed header | 400 |
| Authentication | Token missing/invalid/expired | 401 |
| Authorization | Missing scope/permission | 403 |
| Domain policy | Not allowed to edit order | 403 or 404 per contract |
| CSRF | Session-cookie POST missing CSRF token | 403 |
| CORS | Origin/method/header not permitted | CORS behavior per browser/server |
| Rate limit | Too many requests | 429 |
| Dependency | JWKS/introspection timeout | May be 503 per error mapping |
| Server bug | Unexpected exception | 500 |

### JWKS/Introspection Outage Does Not Prove Token Invalidity

If the Resource Server cannot reach the JWKS endpoint, it lacks the data needed to verify a token with a new key. If introspection times out, the RS does not know whether the token is active.

Both cases must **fail closed**, yet logs/metrics should classify them as dependency errors. Never pretend the AS confirmed the token is inactive.

Do not assume every Spring Security version automatically returns 503 for every network error. Status depends on exception mapping and the application error contract. What is mandatory is never creating an authenticated principal when credentials cannot be verified.

### Do Not Use 403 insufficient_scope to Mask Infrastructure Failures

An AS outage does not mean the principal is authenticated but lacks permissions. Returning 403 could prompt the client to request broader scopes when the real problem is that the RS cannot validate tokens.

## 14. CSRF and CORS Can Also Cause 403

A POST request carrying a session cookie without a CSRF token may be blocked:

~~~http
POST /api/orders HTTP/1.1
Cookie: SESSION=...
Content-Type: application/json
~~~

The response may be 403 even if the user has the `orders.write` scope. This is not evidence of a missing scope.

Browser preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

If CORS policy rejects the origin/method/header, the browser may report a CORS error and JavaScript cannot read the response. Do not diagnose that as a Bearer authentication error when preflight has not passed.

### CORS Configuration

Spring WebFlux integrates CORS with `ServerHttpSecurity` and version-appropriate reactive CORS configuration. Intentionally allow origins/methods/headers, especially the `Authorization` header.

Do not open wildcard origins with credentials unless policy permits. Do not bypass OPTIONS blindly; define preflight behavior explicitly.

### CSRF with Stateless Bearer APIs

An API that only uses an `Authorization: Bearer` header sent explicitly by the client has a different threat model from browser session cookies. If the application also accepts cookies, do not disable CSRF merely because Resource Server is enabled. Determine credential precedence and ambient browser credentials.

## 15. BearerTokenServerAccessDeniedHandler and insufficient_scope

The dedicated Resource Server handler is **BearerTokenServerAccessDeniedHandler**. When the principal is an OAuth2 token authentication and authorization denies access, the handler can add the `insufficient_scope` challenge per Bearer semantics.

Not every `AccessDeniedException` is a scope failure:

- **hasAuthority("SCOPE_orders.write")** with a Bearer token missing the scope: may be `insufficient_scope`.
- Domain service rejecting tenant ownership: a generic access denied may be appropriate.
- CSRF filter rejecting: not Bearer `insufficient_scope`.

When customizing the handler, keep information useful to the client without disclosing other actors' resources or permissions.

### Scope Parameter

The challenge can specify the needed scope:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

Do not disclose internal permission taxonomies or sensitive scope lists to unauthorized callers.

## 16. Standardizing JSON Error Responses

An API can use Problem Details or a custom schema:

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "code": "access_denied",
  "detail": "The authenticated principal cannot access this resource",
  "requestId": "req-123"
}
~~~

Fields to include:
- **type/title/status**: HTTP error description.
- **code**: stable client-facing code.
- **detail**: safe message.
- **requestId**: non-sensitive correlation ID.

Do not:
- Expose raw exception messages externally.
- Include tokens or full claims in the body.
- Return stack traces.
- Disclose internal JWKS/introspection URLs.
- Put status 401 in the body of an HTTP 403 response.
- Strip `WWW-Authenticate` when adding JSON.
- Use HTTP 200 with `success=false` to hide auth errors.

JSON body and Bearer challenge coexist:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store
~~~

The body serves the API contract; the header preserves OAuth/Bearer semantics.
## 17. WebTestClient: Testing 401 When a Token Is Missing

WebFlux tests should go through the real `SecurityWebFilterChain` when the goal is HTTP security behavior.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BearerHttpStatusTests {

    @Autowired
    WebTestClient client;

    @Test
    void missingBearerTokenReturns401Challenge() {
        client.get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                    .valueMatches("WWW-Authenticate", "Bearer.*");
    }
}
~~~

Assumptions:
- `/api/orders` is a protected route.
- The application enables Bearer Resource Server.
- No test authentication automatically grants permissions.
- The request carries no session cookie or other credential that could substitute for Bearer.

Expectations:
- HTTP 401.
- `WWW-Authenticate` starts with `Bearer`.
- Controller/business handlers are not called.
- No tokens/exception internals appear in the body.

If you bind `WebTestClient` directly to a controller without attaching security filters, the test does not prove the filter chain.

## 18. WebTestClient: Testing 403 with an Authenticated Principal

Spring Security Test provides **mockJwt()** for WebFlux. Use it to test authorization:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void validAuthenticationWithoutWriteScopeReturns403() {
    client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")))
            .post()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

This test verifies that a mock-authenticated principal with only the read scope cannot POST. It **does not prove** that the JWT signature, issuer, audience, or JWKS were checked.

Testing with write scope:

~~~java
@Test
void writeScopeCanCreateOrder() {
    client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write")))
            .post()
            .uri("/api/orders")
            .exchange()
            .expectStatus().is2xxSuccessful();
}
~~~

The example requires an appropriate endpoint and request payload in a real application.

## 19. Testing Invalid Tokens Through the Real Decoder

To test authentication failure, send a real compact JWS in the Authorization header:

~~~java
@Test
void invalidSignatureReturns401() {
    String token = signedWithUntrustedTestKey();

    client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader()
                .valueMatches("WWW-Authenticate", ".*invalid_token.*");
}
~~~

The test needs:
- Real Bearer Resource Server filter chain.
- Real `ReactiveJwtDecoder`, not a mock.
- Test JWKS publishing only the trusted public key.
- A token signed with an untrusted key.
- Issuer/audience/timestamp validators per contract.

**mockJwt()** bypasses the decoder; never use it to test signatures.

### Inactive Opaque Token

For an opaque Resource Server, use a mock HTTP introspection endpoint and send a Bearer opaque token. When the AS returns `active=false`, the request is rejected, typically with `401 invalid_token`. This differs from `mockOpaqueToken()`, because the post-processor constructs a mock Authentication and skips HTTP introspection.

## 20. Status and Challenge Test Matrix

| Case | Status | WWW-Authenticate |
|---|---:|---|
| Missing token | 401 | `Bearer`, optionally with realm |
| Expired token | 401 | `Bearer error="invalid_token"` |
| Invalid signature | 401 | `Bearer error="invalid_token"` |
| Wrong issuer/audience | 401 | `Bearer error="invalid_token"` |
| Malformed Bearer request | Typically 400 | `Bearer error="invalid_request"` per parser |
| Valid token missing scope | 403 | `Bearer error="insufficient_scope"` when appropriate |
| Domain permission denial | 403 | May not need `insufficient_scope` |
| CSRF denial | 403 | Not a Bearer scope challenge |
| Dependency outage | Fail closed | Status per error contract |

Headers may include `realm` and parameters in varying orders. Check semantics with regex/parsers rather than brittle exact string equality if the framework can add parameters.

Do not only assert status codes. Also verify:
- Challenge has the right scheme/error.
- JSON content type and schema.
- Controllers are not invoked when authentication fails.
- Side effects do not happen when authorization is denied.
- Raw tokens never appear in bodies/logs.
- Dependency errors are classified properly.

## 21. Testing JSON Handlers

With a custom entry point:

~~~java
client.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader()
            .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
        .expectHeader()
            .valueMatches("WWW-Authenticate", "Bearer.*")
        .expectBody()
            .jsonPath("$.status").isEqualTo(401)
            .jsonPath("$.code").isEqualTo("authentication_failed");
~~~

With access denied:

~~~java
client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
        .post()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden()
        .expectBody()
            .jsonPath("$.status").isEqualTo(403)
            .jsonPath("$.code").isEqualTo("access_denied");
~~~

Tests must run the security config with the custom handlers. If the delegate commits the response before the body is written, integration tests will catch committed-response/double-write errors. Therefore, custom handlers must be tested through `WebTestClient`, not only with unit tests on the class.

## 22. Testing to Distinguish CSRF, CORS, and insufficient_scope

### CSRF

If the app uses session cookies, a POST without a CSRF token may return 403 before method authorization. Tests must assert that this is a CSRF denial, not expect Bearer `insufficient_scope`.

### CORS

Send an OPTIONS preflight with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`. Verify:
- Only allowed origins receive `Access-Control-Allow-Origin`.
- Methods and the `Authorization` header are permitted per policy.
- Preflight is handled before requiring Bearer authentication if CORS config allows.
- Disallowed origins are rejected per contract.

Browsers enforce CORS; Java HTTP clients generally do not enforce it like browsers. Use browser/e2e tests if you need to prove browser-side behavior.

### Domain Denial

Create a principal with `SCOPE_orders.write` but a tenant mismatch. Expect a 403 domain policy response. Do not attach `insufficient_scope` when the token already carries the required scope.

## 23. Safe Observability

You can record:

~~~text
requestId
routeId
authenticationOutcome = missing / invalid / success
authenticationFailureCategory = invalid_token / invalid_request / dependency
authorizationOutcome = granted / denied
authorizationCategory = insufficient_scope / tenant / ownership / csrf
httpStatus
securityHandler = bearer_entry_point / access_denied_handler
latency
~~~

Do not record:
- Authorization header.
- Raw access/refresh tokens.
- Passwords, client secrets, API keys.
- Full JWT payloads containing PII.
- Stack traces or key management details in responses.
- Unverified issuer/subject as a trusted identity.

Metrics should use route ID, configured issuer ID, strategy ID, and bounded-cardinality error categories; never use raw `sub`/tokens/error messages as metric labels.

Distinguishing `invalid_token` from dependency failures is critical. A JWKS/introspection outage means the RS could not verify, not that the AS confirmed the token is inactive.

## 24. Common Anti-Patterns

| Mistake | Problem | Right approach |
|---|---|---|
| Returning 403 for expired tokens | Confuses authentication and authorization | 401 `invalid_token` |
| Returning 401 for missing scope | Forces unnecessary user re-login | 403 `insufficient_scope` |
| 401 without `WWW-Authenticate` | Missing Bearer challenge | Bearer entry point |
| Every 403 is `insufficient_scope` | Wrong for CSRF/domain/CORS | Classify denials properly |
| JSON body only, dropping challenge | Loses HTTP auth semantics | Preserve `WWW-Authenticate` |
| Custom entry point returning 200 | Masks authentication failures | Proper status code |
| Returning raw exception messages | Leaks internals/secrets | Generic detail, correlation ID |
| `@RestControllerAdvice` handling all security errors | Filter-chain errors bypass controllers | Reactive security handlers |
| Using Servlet `AuthenticationEntryPoint` in WebFlux | Wrong API stack | `ServerAuthenticationEntryPoint` |
| `block()` inside response handlers | Blocks reactive pipeline | `Mono<Void>` composition |
| Writing body after response committed | Double write/response error | Delegate lifecycle + integration tests |
| Treating CORS preflight as invalid token | Wrong policy | Configure CORS properly |
| Reporting CSRF 403 as missing scope | Wrong root cause | Classify CSRF separately |
| `mockJwt()` to test signatures | Bypasses decoder | Signed Bearer token + real decoder |
| Asserting only status codes | Skips challenge/body checks | Assert headers, body, side effects |
| Logging raw JWTs | Exposes credentials | Sanitized telemetry |

## 25. Response Decision Matrix

| Authentication | Authorization | Typical response |
|---|---|---|
| No credential | Not run | 401 + Bearer challenge |
| Malformed credential | Not authenticated | 400 `invalid_request` when appropriate |
| Invalid/expired/revoked credential | Failed | 401 `invalid_token` |
| Dependency unable to verify | Unauthenticated | Fail closed; status per error contract, possibly 503 |
| Authentication succeeded, missing scope | Denied | 403 `insufficient_scope` |
| Authentication succeeded, wrong tenant/owner | Denied | 403 or 404 per policy |
| Authentication succeeded, permitted | Allowed | 2xx or business status |
| CSRF/CORS/gateway denial | May not reach authorization | Status per filter/policy |

Not every rejected request is an OAuth error. Reverse proxies, CORS, CSRF, authentication, authorization, domain rules, and rate limiting are separate layers. Responses should reflect the exact denying layer per the API contract.

## 26. Summary

~~~text
HTTP Request
    |
    v
Bearer credential parsing
    |
    v
Authentication
  +-- missing/invalid -> ServerAuthenticationEntryPoint
  |                       -> 401 + WWW-Authenticate
  |
  +-- valid
         |
         v
Authorization
  +-- insufficient permission -> ServerAccessDeniedHandler
  |                               -> 403
  |
  +-- permitted
         |
         v
      Controller / domain
         |
         v
      API response
~~~

Principles to remember:

1. **401** when the caller lacks valid authentication, such as a missing or invalid Bearer token.
2. **403** when the principal is authenticated yet not permitted to perform the action.
3. **WWW-Authenticate: Bearer** is the key challenge for 401; a JSON body does not replace the header.
4. RFC 6750 distinguishes **invalid_request**, **invalid_token**, and **insufficient_scope**.
5. **BearerTokenServerAuthenticationEntryPoint** and **BearerTokenServerAccessDeniedHandler** are the appropriate reactive handlers.
6. Use **ServerAuthenticationEntryPoint** and **ServerAccessDeniedHandler**, never Servlet handlers in WebFlux.
7. A JSON body can supplement the response, but must preserve status and challenge semantics.
8. **@RestControllerAdvice** does not replace security filter-chain handlers.
9. CSRF/CORS/domain denials are not automatically missing OAuth scopes.
10. Dependency failures must fail closed, without pretending the AS confirmed the token is inactive.
11. Tests with **WebTestClient** must check status, `WWW-Authenticate`, body, and side effects.
12. **mockJwt()** is useful for authorization tests, but does not prove signature/JWKS verification ran.

**Conclusion:** A WebFlux Resource Server must return accurate HTTP semantics for each security layer. 401 reflects an authentication challenge, 403 reflects an authorization denial, Bearer error codes must match the root cause, and JSON bodies must be safe. Spring Security provides reactive entry points and access-denied handlers to preserve protocol behavior; WebTestClient verifies the API's response contract.

## 27. References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server:** Bearer authentication, error handling, JWT, and opaque flows. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security Reference — Reactive JWT Resource Server:** JWT authentication and validation. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive Opaque Token Resource Server:** introspection and inactive token handling. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security API — ServerAuthenticationEntryPoint:** reactive authentication challenge. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- **Spring Security API — ServerAccessDeniedHandler:** reactive authorization denial. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- **Spring Security API — BearerTokenServerAuthenticationEntryPoint:** Bearer challenge implementation. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html
- **Spring Security API — BearerTokenServerAccessDeniedHandler:** Bearer access-denied implementation. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAccessDeniedHandler.html
- **Spring Security Reference — WebFlux Security:** SecurityWebFilterChain and exception handling. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security Reference — Reactive Testing:** WebTestClient and mock JWT. https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- **Spring Security Reference — Testing OAuth 2.0:** mock JWT and Resource Server test concepts. https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** invalid_request, invalid_token, insufficient_scope, and WWW-Authenticate. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 9110 — HTTP Semantics:** 401 challenge, 403 forbidden, and WWW-Authenticate. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 7807 — Problem Details for HTTP APIs:** error representation. https://www.rfc-editor.org/rfc/rfc7807
- **RFC 9457 — Problem Details for HTTP APIs:** updated Problem Details specification. https://www.rfc-editor.org/rfc/rfc9457


