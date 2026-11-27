# ServerBearerTokenAuthenticationConverter and Input Token Sources

## 1. The Problem: How Do Tokens Reach a Resource Server?

An API built with **Spring WebFlux + Spring Security OAuth 2.0 Resource Server** typically receives an access token via the HTTP Authorization header:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
~~~

However, real-world systems can introduce several variants:

- Standard clients send **Authorization: Bearer ACCESS_TOKEN**.
- A reverse proxy forwards credentials through another header.
- Legacy clients place tokens in a **URI query parameter**.
- Legacy clients use an **application/x-www-form-urlencoded body parameter**.
- A request carries **multiple token sources** with conflicting values.
- WebSocket handshakes, SSE, gateways, or browser applications tempt developers to choose another channel to pass tokens.

Before checking the JWT signature, issuer, audience, or scope, the Resource Server must decide **which credential to read from the HTTP request**. In the **WebFlux architecture**, a key component responsible for this is:

**ServerBearerTokenAuthenticationConverter**

This is a **ServerAuthenticationConverter** that reads the HTTP request in **ServerWebExchange** and creates an **unauthenticated** Authentication request containing the Bearer token.

Core takeaway:

> The converter extracts credentials from the request; it **does not decide whether the token is valid or authorized**. That is the job of ReactiveAuthenticationManager, ReactiveJwtDecoder or ReactiveOpaqueTokenIntrospector, and the downstream authorization policy.

Without separating these two responsibilities, developers may accidentally trust unverified JWT payloads, accept tokens from unsafe sources, or add extra authentication filters overlapping the standard OAuth Resource Server.

## 2. Position in the WebFlux Architecture

Spring WebFlux uses a **reactive** model based on **Publisher/Mono/Flux**, differing from the traditional Servlet API.

Conceptual flow diagram:

~~~text
HTTP request
  |
  v
WebFlux WebFilter chain
  |
  v
Spring Security WebFilterChainProxy
  |
  v
AuthenticationWebFilter (Resource Server Bearer)
  |
  +-- ServerBearerTokenAuthenticationConverter
  |      ServerWebExchange -> Mono<Authentication>
  |      Extracts Bearer token from allowed source
  |
  v
ReactiveAuthenticationManager
  |
  +-- JWT: ReactiveJwtDecoder, JWT validators
  |      signature, alg, iss, aud, exp, nbf, token profile
  |
  +-- Opaque: ReactiveOpaqueTokenIntrospector
         queries Authorization Server for token status
  |
  v
Authenticated principal + GrantedAuthorities
  |
  v
ReactiveSecurityContextHolder / authorization
  |
  v
Handler / domain service
~~~

Roles:

| Component | Purpose |
|---|---|
| **ServerWebExchange** | HTTP exchange request/response and context in WebFlux |
| **ServerAuthenticationConverter** | Converts a request into an Authentication request inside a Mono |
| **ServerBearerTokenAuthenticationConverter** | Extracts Bearer credentials from a header or allowed source |
| **BearerTokenAuthenticationToken** | Carries the raw token string, **unauthenticated** |
| **AuthenticationWebFilter** | Coordinates the converter, ReactiveAuthenticationManager, and authentication outcome |
| **ReactiveAuthenticationManager** | Authenticates credentials using the appropriate decoder/introspector |
| **ReactiveJwtDecoder** | Verifies JWTs and validators |
| **ReactiveOpaqueTokenIntrospector** | Checks opaque tokens via introspection |
| **SecurityWebFilterChain** | WebFilter chain protecting exchanges |
| **ServerHttpSecurity** | Spring Security configuration DSL for WebFlux |
| **ReactiveSecurityContextHolder** | Accesses SecurityContext via Reactor Context |
| **Reactive AuthorizationManager / method security** | Makes access decisions after authentication |

Do not use Servlet types as the primary mental model:

~~~text
Servlet:
  HttpServletRequest
  DefaultBearerTokenResolver
  SecurityFilterChain
  HttpSecurity
  BearerTokenAuthenticationFilter

WebFlux:
  ServerWebExchange
  ServerBearerTokenAuthenticationConverter
  SecurityWebFilterChain
  ServerHttpSecurity
  AuthenticationWebFilter
~~~

Both stacks follow Bearer semantics, but their **extension points and data types differ**. Bringing an HttpServletRequest-based resolver into WebFlux does not solve the problem on ServerWebExchange.

## 3. API of ServerBearerTokenAuthenticationConverter

In modern Spring Security, the class belongs to the package:

~~~java
org.springframework.security.oauth2.server.resource.web.server.authentication
    .ServerBearerTokenAuthenticationConverter
~~~

It implements:

~~~java
org.springframework.security.web.server.authentication
    .ServerAuthenticationConverter
~~~

Conceptual interface signature:

~~~java
public interface ServerAuthenticationConverter {

    Mono<Authentication> convert(ServerWebExchange exchange);
}
~~~

**There is no need to redefine this interface** in your application; Spring Security already provides it. The key point to remember is that it returns **Mono<Authentication>**, not a raw token string and not an already-authenticated Servlet Authentication result.

Output scenarios:

| HTTP Request | Logical Converter Result |
|---|---|
| No Bearer credential from configured source | **Mono.empty()**: converter creates no authentication request |
| Syntactically valid Bearer token present | **Mono** emitting an unauthenticated BearerTokenAuthenticationToken |
| Malformed/invalid credential per transport policy | **Mono.error(...)**, typically a corresponding OAuth2AuthenticationException |
| Token present with invalid JWT signature | Converter may still emit the credential; **the decoder rejects it** |
| Token present but missing scope | Converter may still emit the credential; **authorization rejects it** |

### Mono.empty() Does Not Mean a Public Endpoint

When the converter returns Mono.empty(), it only means **no matching credential could be extracted**. On a **permitAll** endpoint, the request may proceed. On an **authenticated()** endpoint, authorization will require authentication and typically return a **401 Bearer challenge**.

~~~text
Converter: Mono.empty()
   |
   +-- /api/public/info  -> may be permitted
   |
   +-- /api/orders       -> 401 if policy requires auth
~~~

**Never write code that treats Mono.empty() as equivalent to successful authentication.**

### BearerTokenAuthenticationToken Is Still Unauthenticated

The converter may construct:

~~~java
new BearerTokenAuthenticationToken(rawToken)
~~~

This object holds the credential presented by the caller. It **does not assert that the token has a valid signature**, and unverified JWT claims or usernames must never be used as a trusted principal.

## 4. Default Source: HTTP Authorization Header

By default, a WebFlux Resource Server looks for the Bearer token in:

~~~http
Authorization: Bearer ACCESS_TOKEN
~~~

This is the recommended transport method in RFC 6750, fitting cleanly into the HTTP authentication framework.

Example:

~~~bash
curl -i https://orders.example.com/api/orders \
  -H 'Authorization: Bearer ACCESS_TOKEN'
~~~

In a reactive Java client:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("https://orders.example.com")
        .build();

Mono<String> result = webClient.get()
        .uri("/api/orders")
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(String.class);
~~~

This code is an example of a **client sending a credential**, not the converter implementation inside the Resource Server.

### Why Prefer Headers?

- Aligns with the purpose of HTTP authentication.
- Keeps Bearer credentials separate from URLs and application request bodies.
- Lower risk of recording tokens in browser history or query logs compared to URI parameters.
- Easy to configure gateways to strip tokens before logging headers.
- Works across diverse HTTP methods, body types, and reactive streaming.
- Provides a single consistent place to manage the Bearer token source.

**The Authorization header also contains a secret credential**, so never log it verbatim. Use TLS, do not share tokens via URLs, enforce appropriate request/header size limits, and control proxy forwarding.

## 5. How the Converter Reads the Bearer Header

Distinguish:

~~~http
Authorization: Bearer eyJhbGciOi...
~~~

from:

~~~http
Authorization: Basic dXNlcjpwYXNz
~~~

and:

~~~http
Authorization: DPoP ...
~~~

**ServerBearerTokenAuthenticationConverter** extracts tokens according to the **Bearer scheme** it is configured to support; it does not accept arbitrary authentication schemes by default.

Cases:

| Header | Interpretation |
|---|---|
| Authorization: Bearer abc | Bearer credential that can be passed to the authentication manager |
| Authorization: bearer abc | Per HTTP scheme semantics, scheme names are case-insensitive; implementation handles per supported syntax |
| Authorization: Basic abc | Not a Bearer credential for this converter |
| No Authorization header | Converter typically produces no credential |
| Authorization: Bearer | Malformed/missing token; transport error depends on parser |
| Authorization: Bearer abc def | May be malformed under Bearer syntax |
| Two Authorization headers | Proxies/containers may normalize differently; verify actual policy |

**Important:** The converter decides whether it **can extract a token**; **ReactiveJwtDecoder** or **ReactiveOpaqueTokenIntrospector** decides whether that token is accepted. A string without a valid signature can pass extraction and will be rejected during authentication.

### The Converter Does Not Decode JWTs

A JWT typically has three dot-separated segments. An opaque token may be a random string without that structure. The converter only extracts the **credential string**—it does not parse it into a JWT, verify a JWT signature, or check the issuer.

~~~text
Authorization: Bearer abc.def.ghi
  -> converter extracts abc.def.ghi
  -> ReactiveJwtDecoder verifies and validates
  -> token invalid if incorrect

Authorization: Bearer opaque-random-id
  -> converter extracts opaque-random-id
  -> ReactiveOpaqueTokenIntrospector queries AS
  -> active/inactive per trusted response
~~~

Therefore, the same converter can serve both a **JWT Resource Server** and an **opaque token Resource Server**, while the backend authentication managers differ.

## 6. Configuring a WebFlux Resource Server with the Default Source

With Spring Boot, a JWT Resource Server configuration can use:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

WebFlux Security:

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
public class OrdersWebFluxSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**You do not need to create a converter manually** when only accepting tokens from the default Authorization header. The Resource Server DSL configures the appropriate Bearer token extractor.

Unlike Servlet:

~~~java
// WebFlux:
SecurityWebFilterChain api(ServerHttpSecurity http)

// NOT WebFlux configuration:
SecurityFilterChain api(HttpSecurity http)
~~~

### Limitations of the Example

- The issuer must be trusted and discovery/JWKS must be accurate.
- You must validate the **audience** for orders-api and the access-token profile; `issuer-uri` alone does not replace all validators.
- Authorities **SCOPE_...** are derived from the authenticated token's scopes using the appropriate default mapping.
- A user with write scope may still be denied an action on a specific order by domain policy.
- CSRF/CORS must be designed around how the API serves browser, cookie, and Bearer clients; do not disable CSRF arbitrarily without analysis.

## 7. Customizing the Header: setBearerTokenHeaderName

Spring Security supports changing the header name read by the converter. For example, a **trusted reverse proxy** places the Bearer token into the **Proxy-Authorization** header under an internal contract.

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.web.server.authentication
        .ServerBearerTokenAuthenticationConverter;

ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
~~~

Then wire it into the WebFlux DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenConverter(converter)
        .jwt(Customizer.withDefaults()));
~~~

**Meaning:** this changes where the converter reads the token from the request; it **does not make the converter trust the token** and does not alter JWT or opaque token validators.

### Full Example: Wiring the Converter into SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class CustomBearerSourceSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        ServerBearerTokenAuthenticationConverter converter =
                new ServerBearerTokenAuthenticationConverter();

        converter.setBearerTokenHeaderName(
                HttpHeaders.PROXY_AUTHORIZATION);

        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .bearerTokenConverter(converter)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This is an illustrative configuration. **In practice, using Proxy-Authorization requires careful consideration**:

1. That header has defined meaning in HTTP proxy authentication; it is not an arbitrary application header.
2. It should only be applied when there is a clear **proxy architecture contract**.
3. The gateway must **strip headers of the same name sent directly by external clients**, and only set trusted values per policy.
4. Proxy hops, TLS/mTLS, downstream trust, and logging must be controlled.
5. Changing the header cannot replace JWT issuer, audience, or token-purpose validation.
6. Clarify whether the standard Authorization header is still accepted; `setBearerTokenHeaderName` selects **the header used to extract the Bearer token** for that converter configuration, without adding an arbitrary fallback mechanism.

**A better default for most APIs is keeping the Authorization header.** If the gateway can forward the standard header securely, there is no need to invent a new header.

## 8. A Custom Header Does Not Create a Trusted Source by Itself

Suppose an API accepts:

~~~http
X-Access-Token: ATTACKER_VALUE
~~~

If any Internet client can set **X-Access-Token** itself, switching from Authorization to X-Access-Token **does not increase trust**. It only moves where the credential is read from.

Risks:

- A gateway might pass both Authorization and the custom header simultaneously, causing **credential confusion**.
- One route might use the custom header while another uses Authorization.
- Logging or middleware might not recognize the custom header as a secret and log its value.
- Proxy header injection could cause the backend to receive a token the frontend never intended to send.
- Independent WebFilters could read two different sources and authenticate inconsistent principals.

Solution:

~~~text
Internet client
     |
     v
Trusted gateway:
  - Strip client-supplied private credential headers
  - Validate/forward per policy
  - Only emit downstream credential header when permitted
     |
     v
Resource Server:
  - Converter reads one well-defined source
  - JWT/opaque token is still validated
~~~

If clients can reach the backend directly, gateway trust-boundary configuration offers no protection. The backend must restrict network access or enforce appropriate trusted proxy authentication.

## 9. Token Sources in URI Query Parameters

Some legacy systems send access tokens like:

~~~http
GET /api/orders?access_token=ACCESS_TOKEN HTTP/1.1
Host: orders.example.com
~~~

RFC 6750 documents the URI query mechanism but **discourages** its use. On `ServerBearerTokenAuthenticationConverter`, the flag:

~~~java
converter.setAllowUriQueryParameter(true);
~~~

allows reading the token from a URI query parameter per the converter contract. **By default, this value is false.**

Configuration example (only when accepting legacy system risks):

~~~java
ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setAllowUriQueryParameter(true);

http.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenConverter(converter)
        .jwt(Customizer.withDefaults()));
~~~

### Why Is It Dangerous?

A Bearer token is a credential: anyone holding it can call the API within the token's scope unless additional key-binding constraints exist. Putting tokens in URLs can expose them in:

- Reverse proxy, nginx, and API gateway access logs.
- Browser history, bookmarks, and caches.
- Analytics URLs and monitoring dashboards.
- Copy/pasted links shared over chat or email.
- HTTP Referer headers under certain configurations/policies.
- Tracing spans and distributed logs across intermediary systems.
- Alerting rules or error-reporting systems that record full URLs.
- Screenshots and incident-debugging tools.

**Do not use query tokens as the default solution for SSE or browser APIs.** If an environment cannot send the Authorization header, evaluate **dedicated access mechanisms** (e.g., gateways, credential exchange handshakes, or one-time scoped tokens) instead of trading away Bearer token secrecy without risk assessment.

### Explicitly Disabling by Default Matters

~~~java
converter.setAllowUriQueryParameter(false);
~~~

Even though this is the default, setting it explicitly can document policy for long-lived operations teams, though manual configuration is unnecessary in typical setups.

## 10. Form-Encoded Body Parameter: Supported, but Watch the Version

RFC 6750 describes passing tokens in a form body under method and media-type constraints. Example:

~~~http
POST /api/orders HTTP/1.1
Host: orders.example.com
Content-Type: application/x-www-form-urlencoded

access_token=ACCESS_TOKEN&quantity=1
~~~

**Spring Security 6.5 and later** added the API:

~~~java
converter.setAllowFormEncodedBodyParameter(true);
~~~

The default is **false**. When using Spring Security **earlier than 6.5**, `ServerBearerTokenAuthenticationConverter` may **not have** this setter method. Do not copy examples from newer versions into 6.2 and mistake a compilation failure for a configuration error.

Example for supported versions:

~~~java
ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setAllowFormEncodedBodyParameter(true);

http.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenConverter(converter)
        .jwt(Customizer.withDefaults()));
~~~

**This example is for APIs compatible with 6.5+**, not a recommended configuration for all services. If the request body is JSON or streaming, never assume the converter will look for `access_token` inside arbitrary JSON fields.

### Why Think Twice?

- Body parameters are easily logged by form capture, API tracing, or error reporting.
- They can conflict with application form fields and RFC 6750 constraints.
- Another WebFilter or custom code might attempt to consume the reactive body before the converter runs.
- Body parsing in WebFlux is asynchronous and requires careful handling.
- If tokens are allowed in both headers and bodies, **duplicate source conflicts** must be enforced.
- Never treat an HTTP body `access_token` as automatic authorization; the token must still be verified by the decoder/introspector.

**Recommendation:** prefer the Authorization header. Form-body tokens are a special case requiring an explicit contract, not a default workaround for frontend issues.

## 11. Summary of Bearer Token Sources

| Source | Example | Default WebFlux Converter | Assessment |
|---|---|---|---|
| **Authorization header** | Authorization: Bearer abc | **Yes** | Standard approach |
| **Custom header** | Proxy-Authorization: Bearer abc | No, unless header name is set | Use when a trusted proxy contract exists |
| **URI query** | ?access_token=abc | **No** | High risk of exposure via URLs |
| **Form-urlencoded body** | access_token=abc | **No** | Setter supported from 6.5; consider RFC/media type |
| **JSON body field** | {"access_token":"abc"} | **No** in default converter | Should not treat JSON fields as Bearer transport |
| **Cookie** | Cookie: access_token=abc | **No** | Do not mix cookies/sessions with Bearer casually |
| **WebSocket subprotocol/query** | token in handshake | Not default like HTTP Bearer header | Requires dedicated handshake design |
| **Server-side session** | Session cookie | Outside Bearer converter's scope | Different authentication mechanism |
| **Custom request attribute** | exchange attribute | Not default | Only from trusted source with a purpose-built converter |

In particular, **Bearer credentials differ from session cookies**. A stateless Resource Server based on the Authorization header must not pull browser cookies as Bearer tokens without addressing CSRF, SameSite, and the session trust model.

## 12. Handling Requests Carrying Multiple Credentials

According to RFC 6750, clients must not send an access token using **multiple methods in the same request**. For example:

~~~http
POST /api/orders?access_token=QUERY_TOKEN HTTP/1.1
Authorization: Bearer HEADER_TOKEN
Content-Type: application/x-www-form-urlencoded

access_token=BODY_TOKEN&quantity=1
~~~

There are three token candidates, and their values may differ.

**Do not write a custom converter that “prefers header, otherwise falls back to query, then body” without a duplicate/conflict policy.** If two layers pick two different credentials, **credential confusion** can occur.

A policy should specify:

1. Allow only explicitly configured sources.
2. When multiple token sources are detected in the same request, **reject the request** rather than guessing which token is right.
3. Headers with multiple Authorization values must be handled consistently by the gateway and WebFlux.
4. Never allow query/body tokens to override a header provided by the caller or proxy.
5. Never allow Internet clients to set private proxy credential headers.
6. Log **error categories**, never token values.

### Do Not Assume the Framework Detects Every Duplicate Form

Some duplicate headers are normalized by reverse proxies before reaching the application. If form or query support is disabled, they may not be considered credential sources; therefore, not every input combination triggers a duplicate error in the actual implementation.

To be certain, **evaluate the behavior of ServerBearerTokenAuthenticationConverter in your deployed version and configuration**. Avoid coupling business logic to the assumption that "every duplicate token is detected by the converter".

## 13. Transport Errors and Token Validation Errors Are Not the Same

Three typical groups:

**Group A — No matching credential present**

~~~http
GET /api/orders HTTP/1.1
~~~

The converter may return Mono.empty(). If the route requires authentication, the response is typically **401** with a Bearer challenge.

**Group B — Malformed Bearer request format**

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer
~~~

Or multiple disallowed token transport methods. The converter may raise an OAuth2AuthenticationException/BearerTokenError. Depending on the error, HTTP **400 invalid_request** or **401 invalid_token** may appear per Spring Security's implementation.

**Group C — Converter extracts credential, but token is invalid**

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer INVALID_SIGNATURE_JWT
~~~

The converter simply extracts the string; ReactiveJwtDecoder verifies the JWT and rejects it. Typical response is **401 invalid_token**.

**Group D — Token is valid, but lacks sufficient permissions**

~~~http
GET /api/admin HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
~~~

The Resource Server authenticates the token; WebFlux authorization denies access. Typical response is **403 insufficient_scope** if an OAuth scope is genuinely missing, or another domain-policy 403.

| Stage | State | Typical Error |
|---|---|---|
| Converter | No Bearer found | Mono.empty(); protected routes may return 401 |
| Converter | Malformed/ambiguous Bearer transport | Mono.error; status per BearerTokenError |
| ReactiveJwtDecoder | Invalid signature, issuer, audience, exp | 401 invalid_token |
| ReactiveOpaqueTokenIntrospector | AS returns active=false | 401 invalid_token |
| Authorization | Missing scope | 403 insufficient_scope when applicable |
| Domain policy | Missing membership/ownership | 403 or domain-specific response |
| Upstream introspection | Timeout/HTTP 5xx/wrong RS secret | Dependency error; do not conclude token is invalid |

**Never treat the converter returning a token as proof that the token is valid.**

## 14. Do Not Manually Parse JWT Claims Inside a Converter

An anti-pattern:

~~~java
// Do not do this: at this point the token has not been verified.
String raw = exchange.getRequest()
        .getHeaders()
        .getFirst(HttpHeaders.AUTHORIZATION);

// Parse JWT payload and extract sub, roles...
// Then manually construct an authenticated Authentication.
~~~

Wrong in two ways:

1. **The JWT payload has not been cryptographically verified**. An attacker can craft a JSON string claiming **roles=["ADMIN"]**, **sub="victim"**, **iss="trusted-idp"** without a valid signature.
2. The converter's job is **credential extraction**, not creating authenticated identities. Doing this can bypass JWT validators.

Correct flow:

~~~text
HTTP header
   |
   v
ServerBearerTokenAuthenticationConverter
   |
   v
BearerTokenAuthenticationToken(raw token, unauthenticated)
   |
   v
ReactiveAuthenticationManager
   |
   v
ReactiveJwtDecoder / ReactiveOpaqueTokenIntrospector
   |
   v
Authenticated principal and authorities
~~~

If you need custom claim-to-authority mapping, use extension points **after the JWT is verified**, such as a reactive JWT authentication converter—never turn ServerBearerTokenAuthenticationConverter into a privilege-granting component.

## 15. Reactive Types to Distinguish

In WebFlux:

~~~java
Mono<Authentication>
Mono<Jwt>
Mono<OAuth2AuthenticatedPrincipal>
Mono<AuthorizationDecision>
Flux<Order>
~~~

Their meanings differ:

- **Mono<Authentication> from ServerAuthenticationConverter:** authentication request built from a raw token.
- **Mono<Jwt> from ReactiveJwtDecoder:** token that passed cryptographic and claim validation per the decoder.
- **Mono<OAuth2AuthenticatedPrincipal> from introspector:** principal from trusted introspection.
- **Reactive AuthorizationManager:** decides whether access is permitted.
- **Flux/Mono from business handler:** response data produced after the security policy allows the request through.

### Why Never Call block() Inside a Converter?

Reactor/WebFlux relies on non-blocking I/O. Never write:

~~~java
// Anti-pattern in the WebFlux request path:
Authentication auth = someMono.block();
return Mono.just(auth);
~~~

Blocking on the event loop can degrade throughput or throw runtime errors. If you need to read the request body or query a data source, use reactive operators and reactive APIs. In particular, **credential extraction should never call the AS or a database just to determine a username**.

A specialized converter should only express the credential source and finish quickly, while the authentication manager handles verification using the appropriate reactive strategy.

## 16. WebFlux Has No HttpServletRequest or Default ThreadLocal Security Context

Common differences:

| Servlet | WebFlux |
|---|---|
| HttpServletRequest | ServerWebExchange |
| BearerTokenResolver | ServerAuthenticationConverter |
| DefaultBearerTokenResolver | ServerBearerTokenAuthenticationConverter |
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| Servlet Filter | WebFilter |
| SecurityContextHolder typically uses thread-local | ReactiveSecurityContextHolder via Reactor Context |
| JwtDecoder | ReactiveJwtDecoder |
| OpaqueTokenIntrospector | ReactiveOpaqueTokenIntrospector |

An easy mistake is copying config:

~~~java
// Servlet style: not for WebFlux configuration.
@Bean
SecurityFilterChain api(HttpSecurity http) { ... }
~~~

into a WebFlux-only application. Correct:

~~~java
@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) { ... }
~~~

Another mistake is calling `SecurityContextHolder.getContext()` in a reactive flow and assuming the security context is always bound to the current thread. In WebFlux, execution can hop across threads and uses **Reactor Context**; access it via **ReactiveSecurityContextHolder** or appropriate reactive argument resolution.

## 17. ReactiveSecurityContextHolder and Downstream Authorization

After the authentication manager accepts the Bearer token, Spring Security places the authentication into the reactive security context. Handlers and services can use:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication());
}
~~~

Never extract the **raw token string** to infer the user in business handlers. Use the authenticated principal and contracted identity mapping, such as verified JWT **(iss, sub)** or trusted introspection metadata.

A WebFlux controller can receive Principal:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Mono<String> me(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }
}
~~~

This example focuses on the principal provided by the framework after the security pipeline; **getName()** is not necessarily a global user key in multi-issuer setups, as it may simply be **sub**. Do not use it in place of **issuer + subject** if the application trusts multiple issuers.

## 18. Custom Converters: When Are They Truly Needed?

Some scenarios may justify customization:

1. An internal gateway is only permitted to forward Bearer credentials via a dedicated header while stripping client-supplied Internet sources.
2. A special token transport contract applies to a specific group of routes.
3. Strict restriction to one token source or enterprise-specific duplicate header handling is required.
4. A temporary migration across client transports with a clear sunset window.
5. Security teams require inspecting request metadata before credentials reach the authentication manager.

However, if the requirement is only **checking JWT issuer/audience**, you do not need a custom ServerAuthenticationConverter; use **ReactiveJwtDecoder + validators**.

If the requirement is **mapping scopes/roles to authorities**, use a JWT authentication converter or reactive authorization mapping **after token validation**.

If the requirement is **domain permissions by tenant/order**, use authorization policies or method security—never place this logic inside Bearer token extraction.

If the requirement is **reading the token from a different HTTP header**, first check whether **setBearerTokenHeaderName(...)** is sufficient instead of writing a full custom implementation.

## 19. Safe Custom ServerAuthenticationConverter Skeleton

If custom transport logic is required, still keep the output as an **unauthenticated BearerTokenAuthenticationToken** and reject conflicting scenarios.

Conceptual skeleton:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class TrustedHeaderBearerConverter
        implements ServerAuthenticationConverter {

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        // This is only an example when a trusted gateway has already protected the header.
        String value = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Trusted-Bearer");

        if (value == null || value.isBlank()) {
            return Mono.empty();
        }

        // Never treat this header as trusted if sent directly by Internet clients.
        // A real implementation must validate Bearer syntax/duplicates,
        // length limits, and enforce a clear error policy.
        if (!value.startsWith("Bearer ")) {
            return Mono.empty(); // Illustrative; may need to reject per policy.
        }

        String token = value.substring("Bearer ".length());

        if (token.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "Malformed trusted bearer header"));
        }

        Authentication request =
                new BearerTokenAuthenticationToken(token);
        return Mono.just(request);
    }
}
~~~

**This snippet is an illustrative skeleton and is not safe to copy into production as-is** because you must also handle RFC-compliant Bearer syntax, duplicate credential sources, size limits, error response semantics, proxy trust, and exception translation. The example uses `IllegalArgumentException` to highlight the error branch; a real implementation must use an appropriate **Spring Security authentication exception / BearerTokenError** rather than letting a generic exception turn into an uncontrolled HTTP 500.

**Prefer the standard class** when only changing the header:

~~~java
ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setBearerTokenHeaderName("X-Trusted-Bearer");
~~~

If multiple headers must be supported simultaneously, never invent a priority order without defining a policy that “conflicting credentials are rejected”. A custom converter is security-sensitive and requires independent security review.

## 20. Testing the Converter Directly with MockServerWebExchange

The goal of a converter unit test is to verify **that the token is extracted from the expected source**, not to verify JWT signatures.

With Spring Test and Reactor Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import reactor.test.StepVerifier;

class BearerConverterTest {

    private final ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    @Test
    void readsAuthorizationBearerHeader() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/api/orders")
                                .header(HttpHeaders.AUTHORIZATION,
                                        "Bearer example-token"));

        StepVerifier.create(converter.convert(exchange))
                .assertNext(authentication -> {
                    assertThat(authentication)
                            .isInstanceOf(BearerTokenAuthenticationToken.class);
                    BearerTokenAuthenticationToken token =
                            (BearerTokenAuthenticationToken) authentication;
                    assertThat(token.getToken())
                            .isEqualTo("example-token");
                })
                .verifyComplete();
    }

    @Test
    void noBearerProducesEmptyMono() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/api/orders"));

        StepVerifier.create(converter.convert(exchange))
                .verifyComplete();
    }
}
~~~

These tests verify:

- The Authorization header is converted into an Authentication request containing the exact raw token.
- Without a Bearer token, the converter completes empty.

**They do not prove the JWT is authenticated**, because the converter does not invoke `ReactiveJwtDecoder`. Separate tests are required for JWT signature/issuer/audience validation and the WebFlux `SecurityWebFilterChain`.

### Testing a Custom Header

~~~java
@Test
void supportsConfiguredProxyHeader() {
    ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    converter.setBearerTokenHeaderName(
            HttpHeaders.PROXY_AUTHORIZATION);

    MockServerWebExchange exchange =
            MockServerWebExchange.from(
                    MockServerHttpRequest.get("/api/orders")
                            .header(HttpHeaders.PROXY_AUTHORIZATION,
                                    "Bearer forwarded-token"));

    StepVerifier.create(converter.convert(exchange))
            .assertNext(authentication -> {
                BearerTokenAuthenticationToken request =
                        (BearerTokenAuthenticationToken) authentication;
                assertThat(request.getToken()).isEqualTo("forwarded-token");
            })
            .verifyComplete();
}
~~~

You must separately test that the gateway prevents clients from setting `Proxy-Authorization` directly, as a converter unit test does not prove the proxy boundary.

## 21. Testing When Query Tokens Are Disabled

A test case:

~~~java
@Test
void ignoresUriQueryTokenByDefault() {
    ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    MockServerWebExchange exchange =
            MockServerWebExchange.from(
                    MockServerHttpRequest.get(
                            "/api/orders?access_token=query-token"));

    StepVerifier.create(converter.convert(exchange))
            .verifyComplete();
}
~~~

To test behavior **when enabled**:

~~~java
@Test
void canReadQueryTokenWhenExplicitlyEnabled() {
    ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    converter.setAllowUriQueryParameter(true);

    MockServerWebExchange exchange =
            MockServerWebExchange.from(
                    MockServerHttpRequest.get(
                            "/api/orders?access_token=query-token"));

    StepVerifier.create(converter.convert(exchange))
            .assertNext(authentication -> {
                BearerTokenAuthenticationToken request =
                        (BearerTokenAuthenticationToken) authentication;
                assertThat(request.getToken()).isEqualTo("query-token");
            })
            .verifyComplete();
}
~~~

These two examples demonstrate an **explicitly configured risk**; enabling query tokens is not recommended for production.

### Form Body Tests Must Mind the Version

Starting in Spring Security **6.5**, you can write a test with **setAllowFormEncodedBodyParameter(true)** using a POST and form-urlencoded body. When a project uses an older version, do not write tests calling a non-existent API.

In WebFlux, supply the proper body publisher and Content-Type on `MockServerHttpRequest`; avoid testing with a JSON request while expecting the resolver to parse JSON as form data.

## 22. WebTestClient and SecurityWebFilterChain Integration Tests

Testing the converter directly is not enough. For a real Resource Server, test requests flowing through the chain:

~~~text
WebTestClient request
   |
   v
SecurityWebFilterChain
   |
   v
ServerBearerTokenAuthenticationConverter
   |
   v
ReactiveAuthenticationManager / ReactiveJwtDecoder
   |
   v
Authorization decisions
   |
   v
Response status / WWW-Authenticate
~~~

Scenario matrix:

| Input | Expectation to Verify |
|---|---|
| Protected GET without token | 401 Bearer challenge |
| Public GET without token | Not forced to 401 |
| Valid JWT via Authorization header | Authentication established |
| JWT with invalid signature | Not authenticated, typically 401 |
| JWT with wrong issuer | Not authenticated |
| JWT with wrong audience | Not authenticated if validator enforces it |
| Valid JWT missing SCOPE_orders.read | Authenticated, typically 403 |
| Token in query when query source disabled | Not accepted as Bearer token |
| Token in query after enabling option | Converter extracts token; must still be validated |
| Token from custom header after configuration | Converter extracts token from selected header |
| Both header and query token with duplicate-ban policy | Rejected per transport policy |
| Malformed Bearer header | Status/challenge matches converter error code |
| Opaque introspection active=false | Authentication rejected |
| Opaque introspection AS timeout | Fail closed; do not treat as active=false |
| Gateway adds/strips header | Only trusted source accepted |
| CORS preflight OPTIONS | Not mistaken for Bearer request missing a token |
| POST form-body token on supported version | Behavior matches transport policy |

**Spring Security Test `mockJwt()` can create test Authentications while bypassing the real ReactiveJwtDecoder.** Use it to test authorization policies; do not treat it as proof that production signature, issuer, or audience validation ran.

The scenarios above represent **test scenario design**, not executed test results within this article.

## 23. If a Request Gets 401, How Do You Know Whether the Converter Caused It?

Isolate step by step:

~~~text
[1] Does the request have an Authorization header?
       |
       v
[2] Does the header have the Bearer scheme and valid syntax?
       |
       v
[3] Is the converter wired into the right SecurityWebFilterChain?
       |
       v
[4] Is the converter reading Authorization or a different header?
       |
       v
[5] Is query/form token support enabled?
       |
       v
[6] Did the converter return Mono.empty, Mono.error, or Authentication?
       |
       v
[7] If BearerTokenAuthenticationToken was produced, did the decoder accept it?
       |
       v
[8] Are JWT issuer/audience/alg/exp/profile valid?
       |
       v
[9] If the token is valid, are scopes/authorities sufficient?
~~~

If the converter finds no token because the frontend only sent a query string, changing **JwtDecoder**, JWKS, or `issuer-uri` will not fix the root cause.

Conversely, if the converter extracted the Bearer token and the decoder rejected its signature, changing the header name will not solve it either.

### Diagnostic Table

| Symptom | Likely Cause |
|---|---|
| Valid Bearer header present, but converter always empty | Converter is reading a custom header, wrong SecurityWebFilterChain, or gateway stripped Authorization |
| Query `access_token` has a value, but returns 401 | Query tokens are disabled by default |
| Form body `access_token` is ignored | Form parsing disabled, incompatible method/media type, or Spring Security before 6.5 |
| Token present, but returns 401 invalid_token | JWT/opaque validation failed or malformed transport depending on error |
| Token present and authenticated, but returns 403 | Missing `SCOPE_` authority or denied by domain policy |
| Custom proxy header works in staging, fails in production | Gateway header policy differs |
| Same token succeeds sometimes and fails other times | Multiple gateways/instances with inconsistent converter or decoder configs |
| Bearer token appears in logs | Logging policy captures headers or query strings |
| `permitAll` endpoint returns 401 when bad token sent | Authentication filter attempts to validate a supplied Bearer token even if route doesn't require it; verify chain behavior |
| CORS preflight returns 401 | OPTIONS requires authentication or CORS is ordered incorrectly |

**Pinpoint the specific hop or component** rather than guessing that every 401 is an expired token.

## 24. Multiple SecurityWebFilterChains and Different Source Policies

An application may have multiple protection chains, such as a public API and an internal API. If each chain uses a different Bearer converter, you must understand **security matchers** to know which chain actually handles a route.

Concept:

~~~text
Chain A: /api/internal/**
  -> Proxy-Authorization Bearer
  -> Internal JWT issuer
  -> Dedicated permissions

Chain B: /api/public/**
  -> Authorization Bearer or permitAll
  -> Public JWT issuer
  -> Dedicated permissions
~~~

Common pitfalls:

- A path accidentally matches the wrong chain and the converter reads the wrong header.
- The gateway only adds custom headers on certain routes.
- A public endpoint belongs to a chain that still has a Bearer filter and rejects invalid tokens if a client sends one.
- An internal header is injected directly by clients on a public route.
- Chain A's custom converter has a broader source policy than intended.

**Never fix a filter chain by removing validation.** Design matchers, ordering, endpoint boundaries, and trust policies consistently.

In large systems, prefer a unified token source across APIs and avoid parallel credential paths unless each trust zone strictly requires one.

## 25. Reactive WebClient Propagation Is Not Token Extraction

Another similarly named component is:

**ServerBearerExchangeFilterFunction**

It helps a **WebClient** propagate a Bearer token from the current SecurityContext to a downstream service according to configured behavior.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient downstreamClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
~~~

This is **outbound propagation**, not **inbound extraction**:

~~~text
Inbound:
  HTTP request -> ServerBearerTokenAuthenticationConverter
  -> verify access token

Outbound:
  Authenticated request -> WebClient
  -> ServerBearerExchangeFilterFunction
  -> Authorization: Bearer to downstream service
~~~

Important:

- Does not automatically refresh expired access tokens.
- Only forward tokens when downstream **is authorized to receive that same token**, considering audience, token exchange, and least privilege.
- Do not turn a user token intended for service A into a token usable at service B merely by copying the Authorization header.
- Avoid forwarding access tokens to endpoints outside the trust boundary.
- Never use ServerBearerExchangeFilterFunction in place of a JWT decoder or inbound converter.

## 26. WebSocket, SSE, and Browser Clients: Why Not Use Query Tokens Arbitrarily?

Some browser APIs restrict setting the Authorization header, particularly certain handshakes or APIs like EventSource. This often tempts teams to move Bearer tokens into the URL query string.

However, URL queries are the easiest to leak among the sources discussed. Risk mitigations include:

1. If the protocol and client support it, keep the **Authorization header**.
2. Design a gateway or **credential exchange** endpoint that issues a short-lived, narrow-audience/resource, single-use access ticket when necessary.
3. For WebSockets, define a dedicated authentication handshake with appropriate credential sources, TLS, replay protection, and lifecycle.
4. Never put long-lived access tokens into URLs simply for implementation convenience.
5. Evaluate cookies/sessions and CSRF/SameSite if using browser ambient credentials; do not disguise cookies as Bearer tokens without designing the threat model.
6. Never let clients choose introspection/JWKS URLs or token validation rules.
7. For Server-Sent Events, inspect client options and network constraints rather than assuming query parameters are the only choice.

**ServerBearerTokenAuthenticationConverter is designed for HTTP request extraction.** Authentication for long-lived WebSocket messages or connections can have its own lifecycle and security handshake; do not assume every message is re-checked by the converter.

## 27. Security Perspective: The Credential Source Is a Trust Boundary

A Bearer token may have a valid signature yet enter the request through an unauthorized source or spoofed proxy header. Authentication must combine two questions:

**A. Where did I receive the credential from?**

~~~text
Authorization header?
Trusted gateway header?
Query parameter?
Form body?
Session cookie?
~~~

**B. Is that credential valid and authorized?**

~~~text
JWT: signature + issuer + audience + time + profile
Opaque: trusted introspection + active + audience
Authorization: authorities + tenant + resource policy
~~~

The converter primarily solves **A**; the decoder/introspector and authorization solve **B**.

Key principles:

- Enable only the transports genuinely required.
- Keep the **Authorization header** as the default.
- Never allow multiple credential sources to silently override each other.
- Prevent spoofing of private proxy headers.
- Never trust unverified JWT claims.
- Never log tokens from headers, queries, form bodies, or traces.
- Keep JWT/opaque authentication within standard Resource Server mechanisms.
- Evaluate CSRF/CORS and browser credential models whenever cookies/sessions exist.
- Validate issuer, audience, token purpose, and scope independently of where the token was extracted.
- Measure error categories without leaking Bearer credentials.

## 28. End-to-End Illustrative Scenarios

Suppose a WebFlux API is configured with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

And uses only the Authorization header.

### Scenario 1: Valid Access Token

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer VALID_JWT
~~~

The converter returns a Bearer authentication request. ReactiveJwtDecoder verifies the JWT; Resource Server creates the authenticated principal and checks **SCOPE_orders.read**. If authorized, the request proceeds.

### Scenario 2: Token Placed in Query

~~~http
GET /api/orders?access_token=VALID_JWT HTTP/1.1
~~~

With query tokens disabled by default, the converter **does not extract that token**. If the route requires auth and no other credential is present, the request typically gets **401**. Changing JWT signing keys will not fix this error; the client must be updated to use the Authorization header.

### Scenario 3: Valid Header Format, Invalid Token

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer BAD_SIGNATURE_JWT
~~~

The converter extracts the token, but ReactiveJwtDecoder rejects it. HTTP response is typically **401 invalid_token**.

### Scenario 4: Valid Token, Insufficient Permissions

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer JWT_WITH_ORDERS_READ
~~~

The JWT is authenticated, but lacks **SCOPE_orders.write**. Authorization typically returns **403**, not a converter error.

### Scenario 5: Custom Proxy Header

~~~http
GET /api/orders HTTP/1.1
Proxy-Authorization: Bearer FORWARDED_JWT
~~~

If the converter is configured with header name **Proxy-Authorization** and the gateway protects that header source, the converter extracts the token. The JWT must still be verified by ReactiveJwtDecoder. If the converter remains at its default configuration, Proxy-Authorization may **not be recognized as a Resource Server Bearer credential**.

### Scenario 6: Two Token Sources

~~~http
GET /api/orders?access_token=QUERY_TOKEN HTTP/1.1
Authorization: Bearer HEADER_TOKEN
~~~

If query support is enabled, you need a policy preventing credential collision. Never assume one token is “stronger” because its characters look more like a JWT.

## 29. Common Design Mistakes Checklist

| Mistake | Why Is It Dangerous? | Remediation |
|---|---|---|
| Using Servlet's DefaultBearerTokenResolver for WebFlux | Wrong integration API | Use ServerBearerTokenAuthenticationConverter |
| Using HttpSecurity/SecurityFilterChain in a WebFlux app | Wrong security stack | Use ServerHttpSecurity/SecurityWebFilterChain |
| Manually parsing JWT in converter and setting authenticated=true | Bypasses signature/claim validation | Converter only extracts credentials |
| Treating Mono.empty as access allowed | No authentication request present | Let authorization policy decide if route requires auth |
| Placing Bearer access token in query string | Leaks in logs/history/referer | Use Authorization header |
| Enabling form body source on Spring Security prior to 6.5 | Setter API may not exist yet | Check version; prefer header |
| Accepting custom proxy header directly from Internet | Header spoofing | Gateway strips/rewrites and restricts network access |
| Allowing header/query/body simultaneously without conflict control | Credential confusion | Reject duplicate sources per contract |
| Custom converter calling block() | Can block reactive event loop | Use reactive APIs and proper layering |
| Reading thread-local SecurityContextHolder in Reactor flow | Inconsistent across reactive context switches | Use ReactiveSecurityContextHolder |
| Wrong audience allowed because header was valid | Token for another API accepted | Validate issuer, aud, type, signature |
| Blaming converter when valid token lacks scope | Confusing authentication with authorization | Layer error handling accurately |
| Granting authorities from scopes in raw token | Unverified token | Run decoder/introspector before authority mapping |
| Enabling query tokens solely for SSE/WebSocket | Increases token leakage risk | Design handshake / short-lived credentials |
| Using ServerBearerExchangeFilterFunction instead of inbound converter | Confusing outbound propagation with extraction | Separate WebClient propagation and Resource Server extraction |
| Logging Authorization header | Leaks Bearer credential | Redact/sanitize credentials |
| Adding multiple JWT filters to handle headers | Overlapping or bypassed authentication | Extend Resource Server DSL |
| Running mock JWT tests and assuming decoder verifies signatures | Tests create mock authentications | Write integration tests through a real decoder |

## 30. Summary Principles

~~~text
                          HTTP request
                               |
                               v
                 ServerWebExchange (WebFlux)
                               |
                               v
         ServerBearerTokenAuthenticationConverter
           - Default Authorization header
           - Custom header per trusted contract
           - Query/form only when explicitly enabled
           - Output: Mono<Authentication request>
                               |
                               v
             ReactiveAuthenticationManager
               JWT decoder or opaque introspection
                               |
                               v
                  Verified Authentication
                               |
                               v
                 Reactive authorization
                               |
                               v
                   Domain/business handler
~~~

Remember:

1. **ServerBearerTokenAuthenticationConverter extracts Bearer credentials from ServerWebExchange; it does not validate JWTs.**
2. **Reads `Authorization: Bearer` by default**, rejecting query or form body unless explicitly configured.
3. **setBearerTokenHeaderName(...)** selects an alternative header; use only with a clear trust boundary.
4. **setAllowUriQueryParameter(true)** can enable URI query tokens, but Bearer tokens in URLs carry high leakage risks.
5. **setAllowFormEncodedBodyParameter(true)** appeared in Spring Security **6.5** and is not available on older versions.
6. **Mono.empty()** means the converter produced no authentication request; protected endpoints may still return 401.
7. **Mono.error** reflects transport/converter errors; invalid signatures are caught by the decoder/introspector.
8. **JWT/opaque token acceptance and business authorization** must always occur after credential extraction.
9. **Do not use Servlet APIs to explain WebFlux security**, never block the reactive pipeline, and never assume a ThreadLocal context.
10. **Prefer standard HTTP authentication**, control duplicate/spoofed headers, and never log raw Bearer tokens.

**Conclusion:** Selecting the token source is a small yet critical step in WebFlux Resource Server architecture. The converter determines which credential string moves forward for validation; misconfiguring the token source can cause confusing 401 errors or credential confusion vulnerabilities. Keeping the Authorization header as the default and using Spring Security's extension points ensures token extraction, authentication, and authorization remain cleanly separated.

## 31. References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Bearer Tokens:** Authorization header source, custom headers with ServerBearerTokenAuthenticationConverter, WebClient Bearer propagation. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html
- **Spring Security API — ServerBearerTokenAuthenticationConverter:** convert(ServerWebExchange), setBearerTokenHeaderName, setAllowUriQueryParameter, and setAllowFormEncodedBodyParameter in supported versions. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html
- **Spring Security 6.2.8 API — ServerBearerTokenAuthenticationConverter:** reference for older APIs before the form-body setter was added. https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html
- **Spring Security Reference — Reactive JWT Resource Server:** ServerHttpSecurity, SecurityWebFilterChain, and ReactiveJwtDecoder. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token:** ReactiveOpaqueTokenIntrospector and introspection APIs. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — WebFlux Security:** reactive filter chain and security context. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security API — ServerAuthenticationConverter:** convert(ServerWebExchange) interface and Mono<Authentication>. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- **Spring Security API — AuthenticationWebFilter:** using the converter and reactive authentication manager. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** HTTP Authorization header, form body, URI query, and Bearer errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token:** JWT claims and expiration. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** validating opaque access tokens. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 8725 — JSON Web Token Best Current Practices:** validation, token substitution, and token misuse. https://www.rfc-editor.org/rfc/rfc8725
