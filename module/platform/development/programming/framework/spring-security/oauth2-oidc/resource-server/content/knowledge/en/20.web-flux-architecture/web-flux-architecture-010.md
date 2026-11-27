# Authentication Errors, Access Denied, and Corresponding Server-Side Handlers

In a **Spring Security OAuth 2.0/OIDC Resource Server running on WebFlux**, requests are processed under the **reactive** model: security components participate in a **WebFilter** chain, results can be **`Mono`**, and authentication information flows through the Reactor context.

Therefore, when an error occurs, you must know **at which step the error happened**, **whether the request has already been authenticated**, and **which handler is responsible for generating the HTTP response**. Reading a single log line showing 401 or 403 is rarely enough.

Four interfaces/classes to distinguish:

- **ServerAuthenticationEntryPoint**: initiates an authentication challenge when an endpoint requires authentication and the request lacks valid authentication; typically returns **401**.
- **ServerAccessDeniedHandler**: handles **AccessDeniedException** when access is denied; typically returns **403** if the principal is authenticated but lacks sufficient permissions.
- **BearerTokenServerAuthenticationEntryPoint**: entry point for OAuth2 Resource Server Bearer tokens, producing the **WWW-Authenticate: Bearer** header per RFC 6750.
- **BearerTokenServerAccessDeniedHandler**: access denied handler for Bearer tokens, which can emit **error="insufficient_scope"** when it knows the request carries a valid OAuth2 Authentication.

These mechanisms **are not the same as verifying JWT or opaque tokens**. JWTs are verified via **ReactiveJwtDecoder**, opaque tokens via **ReactiveOpaqueTokenIntrospector** and their respective reactive authentication managers. Error handlers only decide how failures are expressed in HTTP; they do not turn forged tokens into valid ones.

## 1. Start from the WebFlux Model, Not Servlet

Spring Security has two primary web models:

| Component | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| Web security configuration | **HttpSecurity** | **ServerHttpSecurity** |
| Security chain | **SecurityFilterChain** | **SecurityWebFilterChain** |
| Request/response object | **HttpServletRequest/Response** | **ServerWebExchange** |
| Primary security filter | Servlet **Filter** | Reactive **WebFilter** |
| Entry point | **AuthenticationEntryPoint** | **ServerAuthenticationEntryPoint** |
| Access denied handler | **AccessDeniedHandler** | **ServerAccessDeniedHandler** |
| Exception translation | **ExceptionTranslationFilter** | **ExceptionTranslationWebFilter** |
| JWT decoder | **JwtDecoder** | **ReactiveJwtDecoder** |
| Opaque token introspector | **OpaqueTokenIntrospector** | **ReactiveOpaqueTokenIntrospector** |
| Standard security context storage | Thread-local **SecurityContextHolder** on Servlet threads | **ReactiveSecurityContextHolder** and Reactor Context |

**Do not copy Servlet AuthenticationEntryPoint/AccessDeniedHandler code verbatim into WebFlux.** Method signatures, exchange objects, response writing, and the execution model differ.

This lesson covers **WebFlux server-side handling**. Do not confuse it with **WebClient**, which is the reactive HTTP client used to call other services.

### 1.1. Where Does a Typical Request Travel?

~~~mermaid
flowchart TD
    R[HTTP request] --> P[WebFilterChainProxy]
    P --> C[Selected SecurityWebFilterChain]
    C --> B[AuthenticationWebFilter / Bearer converter]
    B --> M[ReactiveAuthenticationManager]
    M --> D[ReactiveJwtDecoder or ReactiveOpaqueTokenIntrospector]
    D -->|Failure| AF[ServerAuthenticationFailureHandler]
    AF --> EP[BearerTokenServerAuthenticationEntryPoint]
    D -->|Success| SC[Authentication in Reactor SecurityContext]
    SC --> AW[AuthorizationWebFilter]
    AW -->|Insufficient permissions| ET[ExceptionTranslationWebFilter]
    ET --> AD[BearerTokenServerAccessDeniedHandler]
    AW -->|Sufficient permissions| H[Handler/Controller]
    EP --> HTTP[HTTP error + WWW-Authenticate]
    AD --> HTTP
~~~

This diagram shows the **flow of responsibilities**, not the strict execution order of every filter across all versions. **ExceptionTranslationWebFilter** can handle **AccessDeniedException** from downstream filters and decide whether to invoke the entry point or access denied handler based on the current authentication. An authentication failure detected directly inside **AuthenticationWebFilter** may go through **ServerAuthenticationFailureHandler** before the entry point writes the response.

## 2. Authentication Failure and Access Denied Are Different

These two error classes answer **two different questions**:

1. **Authentication:** Did the request supply valid credentials identifying a principal?
2. **Authorization:** Is the authenticated principal permitted to access this resource or operation?

### 2.1. Authentication Failure — Not Validly Authenticated

Examples:

- Missing Bearer token when the endpoint requires one.
- JWT with an invalid signature or disallowed algorithm.
- JWT expired, not yet valid (`nbf`), wrong issuer, or wrong audience.
- Opaque access token returning **active=false** from the Authorization Server.
- Malformed Bearer token or non-compliant credential transport.
- Authentication manager rejecting the principal/credential.

In a Bearer Resource Server, invalid-token cases are typically expressed as **401 Unauthorized**, optionally with:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

When the request **sends no credentials at all**, the server typically returns a Bearer challenge **without an error code**, as recommended by RFC 6750.

### 2.2. Authorization Failure — Authenticated, but Insufficient Permissions

For example, a JWT has been verified by ReactiveJwtDecoder and SecurityContext holds:

~~~text
principal: user-123
authorities: [SCOPE_orders.read]
~~~

Yet the endpoint requires:

~~~java
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Authentication is genuine, but **SCOPE_orders.write** is absent. The response is typically **403 Forbidden**. With a Bearer-specific denied handler and matching authentication, the server may return:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Not **every 403** is `insufficient_scope`: it can result from roles, ownership, tenant checks, CSRF, internal policies, or custom handlers.

### 2.3. HTTP Status Codes Do Not Replace Error Analysis

| Scenario | Primary Step | Typical HTTP Status |
|---|---|---|
| No token, protected endpoint | Authentication challenge | **401** |
| JWT bad signature | ReactiveJwtDecoder/authentication | **401** |
| JWT expired | ReactiveJwtDecoder/token validator | **401** |
| Inactive opaque token | Introspection/authentication | **401** |
| Bearer request violates syntax | Bearer token conversion/validation | **400** or implementation-defined code |
| Valid token, missing scope | Authorization | **403** |
| Valid token, wrong tenant/owner | Domain authorization | **403/404** per policy |
| Missing CSRF token in web session chain | CSRF web filter | **403** |
| Decoder/introspection upstream timeout | Authentication infrastructure error | Must not fail open; status depends on exception handling |
| Controller throws data error | Application error | 4xx/5xx per business exception handler |

You must **distinguish HTTP errors from SecurityWebFilterChain from controller business errors**. Seeing a 403 response is not enough to conclude ReactiveJwtDecoder failed.

## 3. ServerAuthenticationEntryPoint

Reactive interface:

~~~java
package org.springframework.security.web.server;

public interface ServerAuthenticationEntryPoint {

    Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception
    );
}
~~~

This is a simplified signature for learning, not a complete copy of the source code or API annotations.

Meaning:

- **ServerWebExchange** provides access to the request and response in WebFlux.
- **AuthenticationException** carries the authentication failure context.
- **Mono<Void>** represents an asynchronous task completing the response; the handler does not return a controller-style String body.
- The entry point typically sets the HTTP status/challenge and completes the response or returns a Mono writing the response.

Example implementations:

| Class | Typical Behavior |
|---|---|
| **BearerTokenServerAuthenticationEntryPoint** | Bearer 401/challenge per RFC 6750 |
| **HttpBasicServerAuthenticationEntryPoint** | HTTP Basic challenge |
| **RedirectServerAuthenticationEntryPoint** | Redirects to a login page, suitable for certain web login flows |
| **HttpStatusServerEntryPoint** | Returns a configured HTTP status |
| **Custom ServerAuthenticationEntryPoint** | Produces a custom-contract response while preserving security semantics |

**Resource Server APIs should generally use a Bearer entry point**, never redirecting to an HTML login page like an interactive browser form/OIDC Login web app.

### 3.1. Challenge Example When Token Is Missing

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
~~~

May receive:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Length: 0
~~~

The **WWW-Authenticate** header is a core part of the Bearer protocol. There is no requirement that every error response carry a JSON body.

### 3.2. Example invalid_token

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <invalid-test-token>
~~~

Typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Some frameworks or versions may include **error_description**, **error_uri**, or extended auth-params. Avoid overly brittle exact-header assertions in tests if the API does not guarantee those specific fields.

## 4. BearerTokenServerAuthenticationEntryPoint

This class lives in package:

~~~text
org.springframework.security.oauth2.server.resource.web.server
~~~

And implements:

~~~java
public final class BearerTokenServerAuthenticationEntryPoint
        implements ServerAuthenticationEntryPoint {
    // ...
}
~~~

It uses details from **BearerTokenError** when the exception provides one to determine the **HTTP status** and **WWW-Authenticate** header per RFC 6750.

Notable API:

~~~java
BearerTokenServerAuthenticationEntryPoint entryPoint =
    new BearerTokenServerAuthenticationEntryPoint();
entryPoint.setRealmName("orders-api");
~~~

**realm** identifies a protection space, but does not replace issuer (**iss**), audience (**aud**), or tenant authorization.

Specifically:

- No token: typically **401** with a **Bearer** challenge and no error attribute.
- Invalid token: typically **401** with **invalid_token**.
- Malformed Bearer request: may return **invalid_request/400** or another error mapping from the converter/resolver depending on version and error type.
- The entry point **does not verify signatures**. It receives an error already detected by the security flow and formats the HTTP response.

Simply replacing the entry point with **HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)** can strip **WWW-Authenticate** and the RFC 6750 parameters OAuth clients expect.

## 5. ServerAccessDeniedHandler

Interface:

~~~java
package org.springframework.security.web.server.authorization;

public interface ServerAccessDeniedHandler {

    Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied
    );
}
~~~

Meaning:

- Invoked when a request is denied access under an authorization policy.
- Can set **403 Forbidden** and appropriate HTTP headers/body.
- Returns **Mono<Void>** without performing blocking I/O.
- Does not decide access-token validity; that is authentication's responsibility.

Example implementations:

| Class | Purpose |
|---|---|
| **BearerTokenServerAccessDeniedHandler** | Bearer-specific 403/challenge |
| **HttpStatusServerAccessDeniedHandler** | Returns a configured HTTP status |
| **ServerWebExchangeDelegatingServerAccessDeniedHandler** | Selects a handler based on an exchange matcher |
| **Custom ServerAccessDeniedHandler** | Custom policy response; must preserve HTTP/Bearer contracts |

### 5.1. BearerTokenServerAccessDeniedHandler

This class lives in package:

~~~text
org.springframework.security.oauth2.server.resource.web.access.server
~~~

Example:

~~~java
BearerTokenServerAccessDeniedHandler denied =
    new BearerTokenServerAccessDeniedHandler();
denied.setRealmName("orders-api");
~~~

It translates an **AccessDeniedException** into an RFC 6750 response.

According to the API docs: **only when the handler has sufficient evidence that the request carries a valid OAuth2 Authentication** does it return **error="insufficient_scope"**. In other cases, it may only report the Bearer scheme and configured realm.

Therefore, never state:

> Whenever WebFlux throws AccessDeniedException, you always get WWW-Authenticate: Bearer error="insufficient_scope".

That conclusion is false if the request is anonymous, unauthenticated, or using a non-Bearer-specific handler.

## 6. ExceptionTranslationWebFilter: Coordinator Between 401 and 403

In WebFlux, **ExceptionTranslationWebFilter** lives in package:

~~~text
org.springframework.security.web.server.authorization
~~~

It handles **AuthenticationException/AccessDeniedException** within the observable portion of the security web filter chain and dispatches the appropriate response.

Primary extension points:

~~~java
void setAuthenticationEntryPoint(
    ServerAuthenticationEntryPoint authenticationEntryPoint);

void setAccessDeniedHandler(
    ServerAccessDeniedHandler accessDeniedHandler);
~~~

It also checks trust/anonymous authentication state depending on the version.

Decision logic:

~~~mermaid
flowchart TD
    X[AccessDeniedException in security chain] --> A{Trusted and sufficient Authentication?}
    A -->|Anonymous/unauthenticated| E[ServerAuthenticationEntryPoint]
    A -->|Authenticated, denied| D[ServerAccessDeniedHandler]
    E --> H1[401 or appropriate challenge]
    D --> H2[403 or policy-specific response]
~~~

**Important:** Not every AuthenticationException in **AuthenticationWebFilter** goes through a single branch of ExceptionTranslationWebFilter. AuthenticationWebFilter has its own **ServerAuthenticationFailureHandler**. In a Resource Server, that failure handler can delegate errors to the Bearer entry point.

Consequently, if a custom entry point has no effect on a malformed Bearer token error, inspect the **authentication failure handler** in the WebFlux flow—not solely ExceptionTranslationWebFilter.

### 6.1. Why Can Anonymous Requests Trigger the Entry Point Instead of 403?

A rule:

~~~java
.anyExchange().authenticated()
~~~

accessed without a token can raise an AccessDeniedException from authorization. Because the principal is not genuinely authenticated, exception translation **triggers an authentication challenge** via the entry point, typically returning **401** for a Bearer API.

If the principal is authenticated yet lacks an authority, the denied handler runs and typically returns **403**.

That is why the exact same authorization rule can yield two different status codes depending on Authentication.

## 7. AuthenticationWebFilter and ServerAuthenticationFailureHandler

**AuthenticationWebFilter** is part of the reactive authentication flow. It typically uses:

- **ServerAuthenticationConverter** to extract credentials/Authentication requests from ServerWebExchange.
- **ReactiveAuthenticationManager** to authenticate.
- **ServerAuthenticationSuccessHandler** on success.
- **ServerAuthenticationFailureHandler** when authentication fails.

In a Bearer Resource Server, the converter reads the Bearer token and the manager calls the decoder or introspector; on failure, the failure handler can invoke the Bearer authentication entry point.

Failure handler interface:

~~~java
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception
);
~~~

A common implementation is **ServerAuthenticationEntryPointFailureHandler**. It **adapts** a **ServerAuthenticationEntryPoint** into a **ServerAuthenticationFailureHandler**.

Model example:

~~~java
ServerAuthenticationEntryPoint entryPoint =
    new BearerTokenServerAuthenticationEntryPoint();

ServerAuthenticationFailureHandler failureHandler =
    new ServerAuthenticationEntryPointFailureHandler(entryPoint);
~~~

In the default Resource Server configuration, Spring Security wires most of this automatically. You do not need to manually instantiate AuthenticationWebFilter just to use a standard JWT Resource Server.

### 7.1. Differences Between Failure Handler and Entry Point

| Aspect | ServerAuthenticationFailureHandler | ServerAuthenticationEntryPoint |
|---|---|---|
| Context | An **authentication attempt** failed | Need to **initiate/challenge authentication** |
| Input | WebFilterExchange + AuthenticationException | ServerWebExchange + AuthenticationException |
| Output | Mono<Void> | Mono<Void> |
| Can delegate to the other? | Yes, via ServerAuthenticationEntryPointFailureHandler | Can receive delegated errors |
| When used? | Token/password/auth method failure inside AuthenticationWebFilter | Missing authentication and required challenges |

Do not confuse the two interfaces simply because both can produce a 401 response.

### 7.2. Never Fail Open When Authentication Manager Errors

If ReactiveJwtDecoder cannot fetch JWKS, the introspection endpoint times out, or the issuer service is unavailable, that is an **inability to verify credentials**, not proof that the token is valid.

Never do this:

~~~java
// Anti-pattern: assuming authentication succeeded when upstream fails.
// Never implement this kind of fallback.
return authenticationManager.authenticate(token)
    .onErrorResume(error -> Mono.just(fakeAdminAuthentication));
~~~

A sound policy denies or returns an appropriate infrastructure error with monitoring and bounded retries/circuit breakers, **never minting a successful principal from an unverified token**.

## 8. RFC 6750 and WWW-Authenticate in WebFlux

The HTTP **WWW-Authenticate** header is part of the **Bearer Token Usage** protocol.

| Scenario | Common Status | Challenge |
|---|---|---|
| Protected endpoint, no token | **401** | **Bearer**; typically no error |
| Token invalid/expired/revoked | **401** | **error="invalid_token"** |
| Malformed Bearer request | **400** per RFC recommendation | **error="invalid_request"** when handled as such |
| Valid token, missing scope | **403** | **error="insufficient_scope"** when handler recognizes valid OAuth2 Authentication |

A challenge may look like:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

RFC 6750 auth-params:

- **realm**: HTTP protection space.
- **error**: invalid_request, invalid_token, insufficient_scope.
- **error_description**: brief description without leaking secrets.
- **error_uri**: URI for error documentation.
- **scope**: required scope, if disclosed.

**Missing token** is not the same as **invalid_token**. RFC 6750 recommends omitting error details when the request included no authentication credentials.

**Not every 403 carries sufficient scope metadata.** For example, a missing ADMIN role, tenant mismatch, or business-policy denial does not necessarily translate into an OAuth2 scope.

### 8.1. Avoid Asking Clients to “Edit” JWT Scopes

If an endpoint requires **orders.write** and a client only has **orders.read**, the client cannot edit the JWT payload to add the scope. Scopes must be granted by the Authorization Server per policy. The Resource Server simply checks verified tokens and its own authorization policies.

### 8.2. Never Expose Overly Detailed Signature Errors

Information exposed to clients should stay minimal for handling. Never put raw tokens, JWK private keys, file paths, stack traces, or internal issuer config details into **error_description**.

## 9. Basic WebFlux JWT Resource Server Configuration

Example for **Spring Boot 3.x/Spring Security 6.x** with WebFlux, applying similarly on newer compatible versions.

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

**issuer-uri** establishes trust with the issuer via metadata/JWKS. **audiences** configures audience validation on supported Spring Boot versions; on other versions, configure ReactiveJwtDecoder validators explicitly.

A SecurityWebFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Differences from Servlet:

- Use **ServerHttpSecurity**, not HttpSecurity.
- Use **SecurityWebFilterChain**, not SecurityFilterChain.
- Use **authorizeExchange** and **pathMatchers**, not authorizeHttpRequests/requestMatchers.
- Do not put blocking JwtDecoder into a reactive flow; use **ReactiveJwtDecoder** via proper configuration.
- Default Bearer-specific handlers produce the corresponding challenges unless replaced by custom config.

For APIs accepting only Bearer headers with no browser-managed authentication, evaluate a dedicated CSRF policy. Never disable CSRF solely because of WebFlux or JWT; if browsers send session or JWT cookies, CSRF risks still apply.

### 9.1. When WebFlux Receives Opaque Tokens

Replace with:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

and configure the introspection endpoint and client credentials. Authentication flows through **ReactiveOpaqueTokenIntrospector** instead of ReactiveJwtDecoder, while 401/403 Bearer challenges follow the same principles.

## 10. Customizing Bearer Entry Point and Denied Handler

When you want an explicit realm for the Orders API, use the standard Bearer handlers:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class BearerChallengeConfig {

    @Bean
    SecurityWebFilterChain ordersApi(ServerHttpSecurity http) {
        BearerTokenServerAuthenticationEntryPoint entryPoint =
            new BearerTokenServerAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenServerAccessDeniedHandler deniedHandler =
            new BearerTokenServerAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

In WebFlux, **ServerHttpSecurity.OAuth2ResourceServerSpec** exposes:

~~~java
authenticationEntryPoint(ServerAuthenticationEntryPoint)
accessDeniedHandler(ServerAccessDeniedHandler)
authenticationFailureHandler(ServerAuthenticationFailureHandler)
~~~

These are the extension points of the **Bearer Resource Server**. Using dedicated handlers on this branch preserves RFC 6750 semantics.

### 10.1. Broad Customization via exceptionHandling

WebFlux also provides:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(entryPoint)
    .accessDeniedHandler(deniedHandler)
);
~~~

This affects exception handling across the security chain more broadly. In applications with multiple authentication mechanisms or multiple SecurityWebFilterChains, determine **where errors originate** and **which handler is actually selected**.

Do not configure a generic JSON/302 entry point on a Bearer API chain and accidentally lose **WWW-Authenticate**.

### 10.2. With Multiple SecurityWebFilterChains

Design example:

~~~text
@Order(1) /api/**:
   Bearer Resource Server
   401 WWW-Authenticate: Bearer
   403 insufficient_scope when appropriate

@Order(2) /web/**:
   OIDC Login + session cookie
   May redirect to login page
   CSRF protection for unsafe methods

Fallback:
   denyAll or explicit policy for other paths
~~~

**The first matching chain** governs authentication and authorization. If a broad web-login matcher is ordered ahead of the API chain, API requests may receive 302/HTML redirects instead of Bearer challenges.

Do not assume configuring a Bearer entry point in one bean automatically applies across all URLs or ports.

## 11. When to Use Generic HttpStatus Handlers?

WebFlux provides simple handlers that only set an HTTP status:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;

ServerAuthenticationEntryPoint plain401 =
    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

ServerAccessDeniedHandler plain403 =
    new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);
~~~

They are useful for certain application protocols or tests, but **do not build RFC 6750 Bearer WWW-Authenticate headers**.

For OAuth2 Resource Servers, prefer **BearerTokenServer*** handlers unless a custom response is deliberately designed to preserve scheme, error code, HTTP status, and client-safe information.

### 11.1. Redirect Entry Points Do Not Suit Every API

A web app with OIDC Login may use **RedirectServerAuthenticationEntryPoint** to send browsers to a login page. However, a machine-to-machine API client expects 401 + Bearer challenge, not a 302 to an HTML login page.

When hosting both web UI and APIs together, separate security chains or request matchers clearly rather than sharing a single entry point across all endpoints.

## 12. Custom JSON Error Bodies: Proper Reactive Responses

Some systems standardize errors into JSON or **Problem Details** (RFC 9457), such as:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required"
}
~~~

This is a **response-body contract**, distinct from **WWW-Authenticate**. For Bearer APIs, **never return JSON while dropping the challenge header**.

A custom reactive handler must:

1. Set the right **HTTP status**.
2. Preserve **WWW-Authenticate: Bearer** and matching error parameters when it is a Bearer challenge.
3. Set the right **Content-Type**, e.g., application/problem+json or application/json.
4. Build a fixed-format body without echoing exceptions or tokens.
5. Return **Mono<Void>** using non-blocking response writes.
6. Never write the response twice if another handler has already committed it.
7. Never turn authentication errors into 200 responses or improper API redirects.

### 12.1. Generic JSON ServerAccessDeniedHandler Example

Example of a **non-Bearer domain endpoint** returning JSON 403:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import reactor.core.publisher.Mono;

ServerAccessDeniedHandler jsonDenied = (exchange, denied) -> {
    var response = exchange.getResponse();

    if (response.isCommitted()) {
        return Mono.error(denied);
    }

    response.setStatusCode(HttpStatus.FORBIDDEN);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

    byte[] bytes = (
        "{\"code\":\"ACCESS_DENIED\",\"message\":\"Access denied\"}"
    ).getBytes(StandardCharsets.UTF_8);

    return response.writeWith(
        Mono.just(response.bufferFactory().wrap(bytes))
    );
};
~~~

This illustrates **how to write a reactive response**, not a recommendation to replace BearerTokenServerAccessDeniedHandler across all Resource Server chains.

If you install this global handler on a Bearer API, responses may **lose error="insufficient_scope"**. If both JSON and RFC 6750 challenges are needed, design a dedicated handler that inspects BearerTokenError/WWW-Authenticate and ensures only one component owns writing the response. Similarly, customizing 401 requires an appropriate **ServerAuthenticationEntryPoint**.

### 12.2. Never Block Inside Handlers

**Do not** write:

~~~java
// Anti-pattern on the WebFlux event loop:
String value = remoteClient.call().block();
response.getOutputStream().write(...);
~~~

In WebFlux, use **Mono/Flux**, reactive HTTP clients, and the reactive response API. Blocking I/O on the event loop stalls threads, increases latency, and impacts the entire system.

Also never subscribe manually to write the response and immediately return Mono.empty(), because lifecycle and commit timing fall outside pipeline control. **Return the Publisher describing the entire operation.**

### 12.3. The Response May Already Be Committed

Once headers/body are written, handlers cannot change the status code. A downstream reactive flow may emit an error **after body streaming has begun**.

Distinguish:

- **Error before commit**: status/headers can be changed and an error body written.
- **Error after commit**: cannot reliably turn the response into a clean 401/403; handle via streaming protocol termination, connection closure, and appropriate logs/metrics.

This is especially important for **Server-Sent Events**, **Flux response bodies**, and streaming APIs.

## 13. Reactor Context and SecurityContext

WebFlux must not assume “an HTTP request always executes on a single Thread”.

Reactive Spring Security passes authentication via **Reactor Context**, accessible through **ReactiveSecurityContextHolder** or Spring Security method/controller integrations.

Service example:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
~~~

In practice, handle empty contexts or anonymous principals according to application policy.

### 13.1. Why Not Use SecurityContextHolder.getContext() Like Servlet?

Traditional **SecurityContextHolder** uses ThreadLocal in most Servlet setups. In reactive pipelines with scheduling and thread hops, reading an arbitrary ThreadLocal can return a wrong or empty security context.

When writing a **ReactiveAuthorizationManager**, WebFilter, or reactive authentication service, use context-aware APIs and Publisher composition. Never store global static Authentications or inject another request's principal into Reactor context.

### 13.2. Never Treat a JWT Claim as an Authorization Decision Before Verification

JWT JSON payloads can be Base64URL-decoded without signature verification. Never read **scope/roles** to mint an Authentication from unverified input in a custom WebFilter.

Correct pipeline:

~~~text
Untrusted Bearer string
 -> ReactiveJwtDecoder or trusted introspector
 -> Authentication
 -> Reactive authorization
 -> Domain policy
~~~

Entry points and denied handlers only express **pipeline failures**; they do not replace verification.

## 14. Authorization WebFilter and Method Security

A WebFlux rule:

~~~java
.authorizeExchange(auth -> auth
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers("/api/admin/**")
        .hasRole("ADMIN")
    .anyExchange()
        .authenticated()
)
~~~

- **hasAuthority("SCOPE_orders.read")** matches the scope authority.
- **hasRole("ADMIN")** typically checks **ROLE_ADMIN** by convention.
- **authenticated()** requires an authenticated principal, without checking tenant/owner.
- **anyExchange()** covers only requests routed into the selected SecurityWebFilterChain.

Method security also works with reactive methods via version-appropriate **@EnableReactiveMethodSecurity**, typically using **@PreAuthorize** on Mono/Flux-returning methods.

Example:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderView> findOrder(String orderId) {
    return repository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)));
}
~~~

**OrderView**, **repository**, and **OrderNotFoundException** are hypothetical application types. When tenant/ownership checks are needed, enforce them in reactive domain policies.

### 14.1. Do Method Security Errors Flow Through the Same HTTP Handler?

If reactive method security emits **AccessDeniedException** inside a Publisher executed in the HTTP pipeline before the response is committed, **ExceptionTranslationWebFilter** or the corresponding exception handling can translate it per security policy.

However, if the method is called outside an HTTP request (background job/message consumer) or the error is caught with **onErrorResume** in the service/controller, do not assume ServerAccessDeniedHandler will run automatically.

**Never swallow AccessDeniedException** and return a normal value just to avoid 403 if that misleads callers into thinking the operation succeeded.

## 15. Controller Errors Differ from WebFilter Security Errors

Example controller:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderView> getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Error categories:

| Error | Source | Typically Involved Handler |
|---|---|---|
| Bearer JWT bad signature | Authentication pipeline | Bearer entry point/failure handler |
| Missing scope at HTTP matcher | AuthorizationWebFilter | ExceptionTranslationWebFilter + denied handler |
| @PreAuthorize denial | Reactive method security | Security exception path if propagated through pipeline |
| Invalid request input | WebFlux binding/validation | Controller advice/WebExceptionHandler |
| Order not found | Domain service | Application exception mapping |
| Database timeout | Reactive service/repository | 5xx/application error handling |
| Streaming response errors after commit | Reactive response pipeline | Status/headers cannot reliably be changed |

**@RestControllerAdvice** and **WebExceptionHandler** handle many application errors, but should not be viewed as automatic replacements for the Bearer authentication entry point. A custom global error handler catching all AuthenticationException/AccessDeniedException instances and turning them into arbitrary JSON can strip RFC 6750 headers or produce wrong statuses.

### 15.1. When to Use @RestControllerAdvice?

Use it for validation, resource not found, or business exceptions:

~~~java
@RestControllerAdvice
class DomainErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(
            OrderNotFoundException error) {
        return ResponseEntity.status(404)
            .body(Map.of("code", "ORDER_NOT_FOUND"));
    }
}
~~~

Simplified snippet; add real imports and domain exceptions.

Never add a catch-all **@ExceptionHandler(Exception.class)** returning HTTP 200 for all errors, or catch AuthenticationException and return 401 without WWW-Authenticate. For WebFilter security errors, controller advice may **never even be invoked** because the request never reached the controller.

## 16. Testing WebFlux with WebTestClient

In the reactive stack, use **WebTestClient**, not Servlet MockMvc, to test SecurityWebFilterChain flows.

Example test integrating Spring Security:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class BearerErrorWebFluxTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        this.client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void noTokenIsUnauthorized() {
        client.get().uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, ".*Bearer.*");
    }

    @Test
    void validAuthenticationButMissingScopeIsForbidden() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.write")))
            .get().uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

This test assumes a real controller handler at **/api/orders/42** and a JWT Resource Server configured with **SCOPE_orders.read**. When missing the scope, 403 is returned before the controller is invoked.

**mockJwt()** injects simulated authentication to test authorization; **it does not prove JWT signatures were verified**. Add separate integration tests with ReactiveJwtDecoder/test JWKS to confirm forged tokens are rejected.

### 16.1. Testing Invalid Tokens via a Real Authorization Header

A real authentication test sends a raw Bearer token on the request:

~~~java
client.get()
    .uri("/api/orders/42")
    .header(HttpHeaders.AUTHORIZATION, "Bearer rejected-test-token")
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Condition: the test context must have a **ReactiveJwtDecoder** or introspector configured to reject that token. If a mock decoder returns valid Authentication for all inputs, the test proves nothing about invalid tokens.

You can mock/stub the decoder to throw corresponding errors for error-handling tests, and add integration tests with test signing keys for cryptographic validation.

### 16.2. Checking the insufficient_scope Header

If the application uses BearerTokenServerAccessDeniedHandler and an Authentication recognized as valid OAuth2, you can assert:

~~~java
client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.write")))
    .get().uri("/api/orders/42")
    .exchange()
    .expectStatus().isForbidden()
    .expectHeader().valueMatches(
        HttpHeaders.WWW_AUTHENTICATE, ".*insufficient_scope.*");
~~~

With custom handlers or configurations, exact headers may differ; verify application requirements and the Authentication type created by test mutators. Never assume every 403 in WebFlux must carry `insufficient_scope`.

### 16.3. Also Test Responses Through the Real Proxy

WebTestClient bound to ApplicationContext tests web filters and authorization well, but does not fully test production TLS, gateways, CORS, ingress rewrites, or port routing.

Run smoke/integration tests in a deployed test environment for:

- 401 with no token.
- 401 `invalid_token`.
- 403 missing scope.
- `WWW-Authenticate` header preserved across reverse proxies.
- No HTML redirects when APIs require Bearer challenges.
- Wrong issuer/audience and unreachable JWKS.
- Opaque token `active=false` or upstream introspection errors.
- CORS preflights and frontend ability to read `WWW-Authenticate` when permitted by policy.

## 17. WebFlux with Multiple SecurityWebFilterChains

WebFlux allows multiple **SecurityWebFilterChain** beans, each with its own matcher and order.

Example:

~~~text
@Order(1)
  path /api/**
  OAuth2 Resource Server
  Bearer entry point
  Bearer access denied handler

@Order(2)
  path /web/**
  OAuth2/OIDC login + session
  Redirect entry point when needed

@Order(3)
  fallback
  denyAll or reviewed exceptions
~~~

Remember:

1. **WebFilterChainProxy** selects the first chain matching the request.
2. Handlers on one chain do not automatically apply to another chain.
3. If a URL matches no chain, Spring Security cannot guarantee authentication/authorization enforcement.
4. A broad `permitAll` catch-all chain ordered first can bypass the Bearer API chain.
5. A login chain ordered ahead of the API chain can make APIs return 302 instead of 401.
6. Actuator/management ports or separate contexts may need dedicated security policies.

When debugging unexpected 401/403 responses, determine **which chain was actually selected** instead of reading one config class and guessing.

## 18. CSRF Errors in WebFlux Are Not JWT Scope Errors

WebFlux can run both OAuth2 Resource Server and CSRF protection. If browsers use session cookies or a BFF, CSRF may be necessary. If the API uses only explicit Bearer headers and no ambient credentials, the CSRF threat model differs.

A POST returning 403 may stem from:

- **CsrfWebFilter** detecting a missing or invalid CSRF token.
- AuthorizationWebFilter seeing the principal lacks an authority.
- Reactive method security denying access.
- Service domain policy denying access.

**Do not “fix” every 403 by adding `SCOPE_*` or blindly disabling CSRF.**

### 18.1. Testing CSRF Separately

Spring Security reactive testing provides the **csrf()** configurer to supply CSRF tokens in WebTestClient. When a chain requires CSRF tokens, a POST test with only `mockJwt` may receive 403 before reaching scope rules.

Enable or disable CSRF based on how browsers send credentials—never by JWT/opaque naming or test convenience.

## 19. Opaque Tokens and Hard-to-Diagnose Upstream Errors

When using **ReactiveOpaqueTokenIntrospector**, not every error means the token is `active=false`.

Examples:

| Scenario | Appropriate Conclusion |
|---|---|
| AS returns token `active=false` | Token is rejected |
| AS returns `active=true`, missing scope | Token valid, authorization denies |
| AS returns 401 to introspection client | Problem with introspection credentials/permissions |
| AS timeout/DNS/TLS failure | No reliable authentication result |
| AS returns metadata violating contract | Introspector/policy may reject |
| Cached `active=true` result still valid | Acceptable within designed TTL; account for revocation latency |

Never “fix” an introspection outage by marking every token authenticated. Handlers should separate invalid credentials from configuration/infrastructure errors without exposing secrets or raw tokens to clients.

### 19.1. ReactiveJwtDecoder Also Has External Dependencies

JWT verification normally uses cached public keys, yet JWKS rotation, discovery, network outages, or bad metadata can still cause key-loading errors. Configure caching, timeouts, monitoring, and rotation procedures properly.

**Signature failure** differs from **JWKS server unavailable** in root cause, even though external responses may both reject the request to preserve security.

## 20. Designing Common JSON Errors Without Breaking the Bearer Protocol

Some systems want every 401/403 to return a JSON body:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Permission required",
  "requestId": "req-123"
}
~~~

This can help frontends, provided key rules are followed:

- HTTP **status** stays accurate.
- **WWW-Authenticate** stays present for OAuth Bearer challenges when required.
- **error_description** contains no sensitive data.
- The JSON body returns no credentials, private claims, stack traces, or internal paths.
- **requestId** comes from trusted tracing infrastructure rather than echoing unvalidated request headers.
- The response is written via **Mono<Void>** in the reactive pipeline.
- Do not reuse one static error body for all cases if clients need to distinguish 401 vs. 403.
- Do not put JSON handlers in controller advice expecting them to catch filter-level authentication failures before the controller.

To preserve full RFC 6750 auth-params alongside a JSON body, build a **Bearer-aware entry point/access denied handler** with contract tests rather than replacing default handlers with a lambda that only sets HttpStatus.

## 21. Troubleshooting Checklist for Authentication and Access Denied Errors

When a WebFlux API returns 401/403, investigate in order:

1. **Which endpoint/path/method?** Is the expected SecurityWebFilterChain matched?
2. **Is `Authorization: Bearer` present?** Is there a token, or is the header missing?
3. **Did the converter accept Bearer syntax?** Is the header malformed or carrying multiple credentials?
4. **Did ReactiveJwtDecoder verify the JWT?** Signature, issuer, audience, `exp`, `nbf`, algorithm/key source?
5. **Was the opaque token introspected?** `active`, AS endpoint, client credentials, TLS/timeout?
6. **Which authorities does Authentication hold?** `SCOPE_*`, `ROLE_*`, custom mappings?
7. **Which rule matched?** `authorizeExchange` `pathMatchers`/`anyExchange`, method security?
8. **Is the principal authenticated or anonymous?** This determines entry point vs. denied handler.
9. **Could 403 be CSRF or domain policy?** Never assume `insufficient_scope`.
10. **Which handler wrote the response?** Bearer entry point, Bearer denied handler, generic status handler, or global WebFlux handler?
11. **Did `WWW-Authenticate` survive the gateway?** Was it stripped by a proxy or hidden by browser CORS?
12. **Was the response already committed?** Streaming bodies cannot reliably change status codes.
13. **Are logs safe?** Never log raw tokens, `Authorization`, cookies, or secrets.
14. **Do tests run real security web filters?** Not just mocked controllers.
15. **Does it happen only in production?** Compare chain configs, profiles, issuer/JWKS, reverse proxies, and certificates.

### 21.1. Anti-Patterns to Avoid

- Catching all exceptions and returning **200 OK** with error JSON.
- Turning every 403 into 401 to “make the client refresh its token”.
- Redirecting 401 responses with 302 to a login page when the API is a Resource Server.
- Replacing the Bearer entry point with a generic status handler and losing `WWW-Authenticate`.
- Mapping every `AccessDeniedException` to `insufficient_scope`.
- Reading JWT claims before verification to assign roles.
- Calling **block()** inside a WebFilter, entry point, or denied handler.
- Relying on ThreadLocal security context inside a Reactor pipeline.
- Subscribing manually to write responses outside the reactive chain.
- Trying to change HTTP status after the response is committed.
- Using Servlet MockMvc to test a WebFlux SecurityWebFilterChain.
- Getting a 404 on a handlerless URL and assuming authorization worked.
- Disabling CSRF system-wide without evaluating browser cookie authentication.
- Widening CORS overly broadly to “fix” 401/403 errors.
- Failing open when upstream introspection or JWKS is unreachable.

## 22. Self-Check Exercises

**Question 1. A GET request to a protected endpoint has no Authorization header. Which handler should respond?**

The authentication entry point—typically **BearerTokenServerAuthenticationEntryPoint**—returning a **401** Bearer challenge without requiring an error code.

**Question 2. The JWT is valid, but lacks `SCOPE_orders.read`. What is the right outcome?**

Authorization denies access; typically **403**. BearerTokenServerAccessDeniedHandler may add **insufficient_scope** if it recognizes a valid OAuth2 Authentication.

**Question 3. How does ServerAuthenticationFailureHandler differ from ServerAuthenticationEntryPoint?**

The failure handler handles a **failed authentication attempt** inside AuthenticationWebFilter. The entry point initiates an **authentication challenge**; the failure handler can delegate to an entry point via an adapter.

**Question 4. Should HttpStatusServerEntryPoint be used to return 401 for every OAuth2 Resource Server?**

Not by default. It lacks RFC 6750 **WWW-Authenticate** headers. Use a Bearer-specific entry point or a custom implementation that honors the contract.

**Question 5. In WebFlux, can you safely retrieve the principal from ThreadLocal SecurityContextHolder like in Servlet?**

Do not rely on it. For reactive pipelines, use **ReactiveSecurityContextHolder** and Reactor-aware integrations.

**Question 6. Why might a POST using `mockJwt` still return 403?**

**CsrfWebFilter** may require a CSRF token, an authority may be missing, or a domain policy may reject it. Diagnose the true cause before changing anything.

**Question 7. Should an opaque token introspection timeout be treated as `active=true`?**

No. When a token cannot be verified, never mint an authenticated principal in fail-open fashion.

**Question 8. Do all controller errors pass through the Bearer access denied handler?**

No. Validation, not-found, and database errors are typically handled by application/WebFlux exception mapping. The Bearer denied handler primarily handles security access denials in that pipeline.

**Question 9. WebFlux has two SecurityWebFilterChains, and both match a URL. Do both handlers execute?**

No. Chains are evaluated in order and the first matching chain is used. Chain ordering directly affects which handlers and challenges apply.

**Question 10. Why shouldn't `error_description` return the full `exception.getMessage()`?**

Because exception messages can expose raw tokens, internal details, invalid HTTP header characters, or hints helping attackers probe token state. Keep messages minimal and RFC-compliant.

## Conclusion

In a **Spring Security WebFlux Resource Server**, authentication errors and access denials follow two distinct branches:

- **Authentication failure**: missing or invalid credentials; typically routed through **ServerAuthenticationEntryPoint**—**BearerTokenServerAuthenticationEntryPoint** in Bearer APIs—returning **401** and **WWW-Authenticate: Bearer**.
- **Authorization failure**: Authentication is established, but lacks sufficient scope, role, or permissions; routed through **ServerAccessDeniedHandler**—typically **BearerTokenServerAccessDeniedHandler** in Bearer APIs—returning **403** and optionally **insufficient_scope**.
- **AuthenticationWebFilter** has its own **ServerAuthenticationFailureHandler**; **ExceptionTranslationWebFilter** coordinates downstream security exceptions. Not every error flows through a single handler.
- **ReactiveSecurityContextHolder** and **Mono<Void>** reflect the Reactor model; never use blocking I/O or ThreadLocal assumptions when customizing handlers.

The right design is **verifying tokens from trusted sources → building reactive Authentication → checking authorities and domain policies → returning 401/403 with appropriate challenges on failure**. Never sacrifice RFC 6750, expose credentials, or fail open to make errors look friendlier.

### References

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — ServerHttpSecurity.OAuth2ResourceServerSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2ResourceServerSpec.html)
- [Spring Security API — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Spring Security API — BearerTokenServerAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenServerAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html)
- [Spring Security API — ServerAuthenticationEntryPointFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html)
- [Spring Security API — ServerAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
