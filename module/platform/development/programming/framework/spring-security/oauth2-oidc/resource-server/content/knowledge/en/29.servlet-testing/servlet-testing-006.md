# Testing Missing Tokens, Malformed Tokens, and WWW-Authenticate Responses

In a **Spring Security OAuth 2.0 Resource Server using Servlet**, three scenarios must be tested separately:

1. A request hits a protected endpoint **without sending an access token**.
2. A request sends `Authorization: Bearer ...`, but **the header or token is malformed/invalid**.
3. The Resource Server rejects a request and must return the **HTTP status and `WWW-Authenticate` challenge** with the right semantics.

At a glance, these scenarios may all return 401, yet their meanings differ. Clients need to know when no credentials were sent, when the token cannot be authenticated, and when the token is valid but lacks permissions.

**RFC 6750** defines three key error codes for bearer access tokens:

- `invalid_request`: the request carries the token improperly or has an invalid request structure; the Resource Server usually returns **400 Bad Request**.
- `invalid_token`: the token is expired, revoked, malformed, or otherwise invalid; the Resource Server usually returns **401 Unauthorized**.
- `insufficient_scope`: the token is valid, but lacks sufficient permissions for the resource; the Resource Server usually returns **403 Forbidden**.

When a request contains no authentication information, the RFC states the Resource Server sends `WWW-Authenticate`, but **should not include an error code or detailed error information** in that challenge.

> **Testing principle:** assert both the status and the `WWW-Authenticate` header. A test checking only `status().isUnauthorized()` does not prove the server properly distinguishes missing credentials, malformed bearer headers, and invalid tokens.

This article uses Spring Security Servlet, Spring MVC Test, and **MockMvc with the real filter chain**. Examples assume modern Spring Boot and Spring Security, Java 17+, and JUnit 5. WebFlux uses `WebTestClient` and the corresponding reactive server-side handlers.

## 1. Distinguishing the three error types before writing tests

### 1.1. No bearer credential

Request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

The endpoint requires authentication, yet the request has no `Authorization: Bearer ...`.

Typical result:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

If a realm is configured:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

There is no `error="invalid_token"` because the client did not send a token for the Resource Server to inspect. RFC 6750 states that when a request lacks authentication information, the Resource Server **SHOULD NOT** include an error code or other error information.

### 1.2. Malformed or invalid token

Request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJub25lIn0.invalid.signature
~~~

The client attempted to authenticate using a bearer token, but the token is invalid. Examples:

- Header does not follow bearer syntax.
- Token cannot be parsed.
- JWT has an invalid signature.
- JWT uses an unaccepted algorithm.
- Incorrect `iss` or `aud`.
- Token is expired or before `nbf`.
- Opaque token is determined inactive by introspection.

Typical result:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Spring may add `error_description` or `error_uri` depending on the error and configuration. The specific description string should not be treated as stable across every version.

### 1.3. Request sending the token improperly

For example, the client sends the same access token via multiple methods:

~~~http
GET /api/orders?access_token=query-token HTTP/1.1
Host: api.example.com
Authorization: Bearer header-token
~~~

RFC 6750 requires clients to use **at most one method to transmit the bearer token in each request**. When the Resource Server detects multiple token sources or duplicated/malformed token parameters, the appropriate error is `invalid_request`, usually paired with HTTP 400:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

Spring Security's `DefaultBearerTokenResolver` reads only the `Authorization` header by default. Query parameter and form body token transports are disabled by default. If the application enables those mechanisms, the resolver can detect tokens in multiple locations and reject the request.

### 1.4. Valid token with insufficient permissions

Request:

~~~http
GET /api/orders/export HTTP/1.1
Host: api.example.com
Authorization: Bearer <valid-access-token>
~~~

Suppose the token is authenticated, but only has `SCOPE_orders.read`, while the endpoint requires `SCOPE_orders.export`.

Typical result:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

This is an authorization failure. The token passed authentication; the Resource Server denies access because the caller lacks sufficient permissions.

## 2. Error classification table per RFC 6750

| Scenario | Error code | Typical HTTP status | Meaning |
|---|---|---:|---|
| No token sent | No error code | 401 | Client needs to know the endpoint requires Bearer authentication |
| Wrong authentication scheme sent, e.g., `Basic` to a Bearer-only API | Usually no error code | 401 | Resource Server received no Bearer credential |
| Malformed Bearer header | `invalid_token` in default Spring when resolver recognizes Bearer scheme with invalid syntax | 401 | Cannot extract a valid token |
| Token parse/verification failure | `invalid_token` | 401 | Credential was sent, but is invalid |
| Expired/revoked token | `invalid_token` | 401 | Token is no longer usable |
| Token sent via multiple methods | `invalid_request` | 400 | Request does not comply with bearer token transmission rules |
| Duplicate or empty token parameter when resolver supports that transport | `invalid_request` | 400 | Request parameters are invalid |
| Valid token but missing scope/privilege | `insufficient_scope` | 403 | Authentication succeeded, authorization denied |
| Missing CSRF token when CSRF is enabled | Not necessarily a Bearer error | 403 | CSRF filter rejected the request |
| Introspection/JWKS dependency failure | Depends on exception handling | May be 5xx or authentication error | Unable to verify token due to dependency failure |

**Do not collapse every error into 401.** For API clients, accurate classification helps decide whether to acquire a new token, fix the request, or request additional permissions.

## 3. `WWW-Authenticate` is a protocol header, not a JSON error body

`WWW-Authenticate` is an HTTP response header indicating which authentication scheme the server accepts and optionally providing error details.

A Bearer challenge looks like:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Or with error parameters:

~~~http
WWW-Authenticate: Bearer realm="orders-api",
                  error="invalid_token",
                  error_description="The access token expired"
~~~

Common attributes:

| Attribute | Meaning | Notes |
|---|---|---|
| `Bearer` | Authentication scheme | Required in the challenge per RFC 6750 |
| `realm` | Protection space / realm name | Optional |
| `error` | OAuth bearer error code | Optional; used on corresponding authentication/authorization errors |
| `error_description` | Developer-facing explanation | Optional, not intended to be shown directly to end users |
| `error_uri` | URI of documentation explaining the error | Optional |
| `scope` | Required scope for the resource | Optional, should only send meaningful values per contract |

### 3.1. Missing token should not include `invalid_token`

Correct:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Avoid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token",
                  error_description="Token is invalid"
~~~

In the second example, the client did not send a token. The server has no token to conclude that a token is invalid.

### 3.2. Invalid token should include `invalid_token`

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

The client can request a new access token if the grant/refresh policy allows it, then retry the request.

Do not put raw tokens, full JWT payloads, signing keys, sensitive introspection responses, or stack traces into `error_description`.

### 3.3. `insufficient_scope` belongs to 403

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

The RFC allows the server to add `scope` to indicate the required permission. However, not every authorization failure is caused solely by an OAuth scope; applications also have roles, tenant memberships, ownership, and business policies. Choose an appropriate error description and avoid leaking internal policy details.

### 3.4. Do not assume the response body must contain JSON

RFC 6750 specifies the status and `WWW-Authenticate`; it does not mandate a specific JSON error body.

Default Spring Security typically returns the status and challenge header without automatically generating an application-specific JSON body schema. If the API needs a body like:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A bearer access token is required"
}
~~~

the application can implement a custom `AuthenticationEntryPoint`/`AccessDeniedHandler`. When doing so, still preserve `WWW-Authenticate` per the RFC; do not replace the protocol header with a JSON body.

## 4. How does Spring Security process the request?

For a Servlet Resource Server, the basic path is:

~~~text
HTTP request
     |
     v
FilterChainProxy
     |
     v
SecurityFilterChain
     |
     v
BearerTokenAuthenticationFilter
     |
     +-- BearerTokenResolver
     |      |
     |      +-- No token found -> continue filter chain
     |      |
     |      +-- Malformed header -> AuthenticationException
     |      |
     |      +-- Token found -> BearerTokenAuthenticationToken
     |
     v
AuthenticationManager / AuthenticationProvider
     |
     +-- JWT -> JwtAuthenticationProvider -> JwtDecoder
     |
     +-- Opaque -> OpaqueTokenAuthenticationProvider -> Introspector
     |
     v
SecurityContextHolder
     |
     v
AuthorizationFilter
     |
     +-- Permit / sufficient authority -> controller
     |
     +-- Anonymous / unauthenticated -> ExceptionTranslationFilter
     |                                    |
     |                                    v
     |                             AuthenticationEntryPoint
     |
     +-- Authenticated but denied -> AccessDeniedHandler
~~~

Key details:

- `BearerTokenResolver` extracts the token from the request.
- `BearerTokenAuthenticationFilter` creates an authentication request and calls `AuthenticationManager`.
- The JWT provider verifies via `JwtDecoder`.
- The opaque provider calls `OpaqueTokenIntrospector`.
- `BearerTokenAuthenticationEntryPoint` translates authentication errors into HTTP status and `WWW-Authenticate`.
- `BearerTokenAccessDeniedHandler` translates authorization errors into 403 and a Bearer challenge when the request has valid OAuth authentication.

### 4.1. Where does `DefaultBearerTokenResolver` read from by default?

By default Spring Security reads:

~~~http
Authorization: Bearer <access-token>
~~~

`DefaultBearerTokenResolver` can be configured to read tokens from a custom header, form body, or query parameter. However:

- Form body token parameter is disabled by default.
- Query parameter token is disabled by default.
- RFC 6750 recommends avoiding query parameters because URLs can be recorded in logs, browser history, proxies, and monitoring.
- Clients should not send the same token through multiple methods.

If the application only accepts the `Authorization` header, a query parameter test must not be mistaken for a valid bearer token.

### 4.2. Malformed header vs invalid token content are two distinct failure points

Malformed header example:

~~~http
Authorization: Bearer bad"token
~~~

`DefaultBearerTokenResolver` recognizes the Bearer scheme, but the token fails the grammar accepted by the resolver. In the current default implementation, the resolver throws an `invalid_token` error before the decoder is invoked.

Example of a syntactically valid token string that is not a valid JWT:

~~~http
Authorization: Bearer not-a-jwt
~~~

This string can pass bearer token extraction, after which the decoder fails to parse the JWT. The result is also `invalid_token`, but the failure occurs at the decode/verification step.

Therefore, tests should separate:

1. Malformed header — tests `BearerTokenResolver`.
2. Malformed/invalid token — tests `AuthenticationProvider` and decoder/introspector.

### 4.3. Wrong scheme is not the same as malformed Bearer

Request:

~~~http
Authorization: Basic dXNlcjpwYXNz
~~~

If the API only configures OAuth2 Resource Server Bearer, the default resolver does not treat this as a Bearer token. On a private endpoint, the request is usually rejected as **missing Bearer credentials** with a `WWW-Authenticate: Bearer` challenge without `invalid_token`.

This differs from:

~~~http
Authorization: Bearer bad"token
~~~

The second header attempted to use the Bearer scheme, but the token syntax is invalid.

## 5. Configuring the Resource Server for tests

A simple JWT-only API:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/export")
                    .hasAuthority("SCOPE_orders.export")
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This example assumes:

- The API uses only the Bearer header for authentication.
- The JWT decoder is configured via `issuer-uri`, `jwk-set-uri`, or a `JwtDecoder` bean.
- `SCOPE_orders.read` and `SCOPE_orders.export` are mapped from claims per contract.
- The API does not use cookies/sessions to send credentials automatically.

If the application is a bearer-only API, disabling CSRF can be considered after confirming the credential model:

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

Do not disable CSRF solely because the application uses JWT or `SessionCreationPolicy.STATELESS`. If browsers automatically send a cookie for authentication, CSRF still needs evaluation.

### 5.1. Test dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Spring Boot BOM manages the corresponding versions. Do not mix `spring-security-test` from a different minor version than the running runtime.

## 6. Using MockMvc with the real SecurityFilterChain

### 6.1. Spring Boot test

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BearerChallengeIntegrationTests {

    @Autowired
    MockMvc mvc;
}
~~~

`@AutoConfigureMockMvc` registers servlet filters from the application context by default. To test Spring Security, do not configure:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

because this option skips filters and drops the Bearer token processing path.

### 6.2. Building MockMvc manually from WebApplicationContext

If not using Boot auto-configuration:

~~~java
@BeforeEach
void setUp() {
    mvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
}
~~~

`springSecurity()` attaches the `springSecurityFilterChain` bean to MockMvc and integrates test security context helpers. Without this step, tests may go straight to MVC without running `FilterChainProxy`.

### 6.3. Do not use `standaloneSetup` to conclude the filter chain ran

~~~java
MockMvcBuilders
    .standaloneSetup(new OrdersController(service))
    .build();
~~~

This approach is useful for controller unit tests, but does not automatically load the full application security configuration. When testing the real filter chain, prefer `@SpringBootTest` or `webAppContextSetup(...).apply(springSecurity())`.

## 7. Testing private endpoints without a token

Basic test:

~~~java
@Test
void protectedEndpointWithoutTokenReturns401AndBearerChallenge()
        throws Exception {

    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ));
}
~~~

To assert that missing credentials are not mistakenly labeled `invalid_token`:

~~~java
@Test
void missingTokenDoesNotReturnInvalidTokenError()
        throws Exception {

    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            allOf(
                startsWith("Bearer"),
                not(containsString("error="))
            )
        ));
}
~~~

Static imports:

~~~java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Common imports:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
~~~

### 7.1. Testing public endpoints do not require a token

~~~java
@Test
void publicEndpointDoesNotRequireToken() throws Exception {
    mvc.perform(get("/api/public/health"))
        .andExpect(status().isOk());
}
~~~

Public endpoints are not rejected simply for lacking a Bearer token. If a client sends a malformed Bearer token, the Bearer filter may still process the submitted credential and return an authentication error before authorization reaches the controller. `permitAll()` is not an instruction to ignore Bearer header processing.

### 7.2. Testing wrong authentication scheme

~~~java
@Test
void basicSchemeIsNotAcceptedAsBearerAuthentication()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Basic dXNlcjpwYXNz"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ))
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            not(containsString("error="))
        ));
}
~~~

This test assumes the `SecurityFilterChain` only configures OAuth2 Resource Server Bearer and does not enable HTTP Basic alongside it.

## 8. Testing malformed Bearer headers

### 8.1. Token containing characters rejected by the resolver

~~~java
@Test
void malformedBearerHeaderReturnsInvalidToken()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer bad\"token"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

In the current default implementation, `DefaultBearerTokenResolver` applies a grammar for bearer tokens. The header starts with `Bearer`, but the token contains a double quote not matching the grammar, so the resolver produces `invalid_token`.

Do not assert the exact full `error_description`; it can change across versions or implementations.

### 8.2. Bearer scheme without a token

~~~java
@Test
void bearerSchemeWithoutTokenIsRejected()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

With the current `DefaultBearerTokenResolver`, a header starting with `Bearer` that does not match `Bearer <token>` syntax is treated as a malformed Bearer credential. This is a Spring implementation detail; re-verify if replacing the resolver or upgrading versions.

### 8.3. Do not confuse valid token syntax with a security-valid token

A token can be a valid string under bearer grammar yet still not be a valid JWT:

~~~http
Authorization: Bearer not-a-jwt
~~~

The resolver can extract `not-a-jwt`, and then `JwtDecoder` fails to parse it. Both malformed headers and invalid JWTs can lead to:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

However, they are tested at different layers:

- Malformed header: decoder is not yet called.
- Valid token syntax but invalid JWT: decoder is called and throws an error.

## 9. Testing unparseable/unverifiable JWTs

If using a real decoder, send a token with valid bearer grammar that is not a compact JWT:

~~~java
@Test
void bearerValueThatIsNotJwtReturnsInvalidToken()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer not-a-jwt"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

To test other invalid reasons, use tokens signed with test keys or a decoder stub per scenario:

| Test token | Expected result |
|---|---|
| Malformed JWT payload | 401 `invalid_token` |
| Invalid JWT signature | 401 `invalid_token` |
| `alg=none` when disallowed | 401 `invalid_token` |
| Wrong `iss` | 401 `invalid_token` |
| Wrong `aud` | 401 `invalid_token` |
| Expired `exp` | 401 `invalid_token` |
| `nbf` in the future beyond clock skew | 401 `invalid_token` |
| Valid token | Authentication succeeds, continues to authorization |

You do not need a production Authorization Server to test every JWT error. You can use a test RSA key, test public key, and real decoder; if only testing exception/status mapping, use a decoder stub, while clearly noting that the test does not prove cryptographic signatures.

### 9.1. Testing whether the decoder is called

To distinguish whether the failure happens in the resolver or decoder, you can use a mock `JwtDecoder`:

~~~java
@MockitoBean
JwtDecoder jwtDecoder;
~~~

Modern Spring Framework provides `@MockitoBean`; some older Spring Boot projects use `@MockBean`.

Malformed header test:

~~~java
@Test
void malformedHeaderIsRejectedBeforeJwtDecoder()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer bad\"token"
            ))
        .andExpect(status().isUnauthorized());

    verifyNoInteractions(jwtDecoder);
}
~~~

Test with syntactically valid token where the decoder reports invalid:

~~~java
@Test
void invalidJwtValueReachesDecoder() throws Exception {
    given(jwtDecoder.decode("not-a-jwt"))
        .willThrow(new BadJwtException("Malformed JWT"));

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer not-a-jwt"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));

    verify(jwtDecoder).decode("not-a-jwt");
}
~~~

`@MockitoBean`/`@MockBean` replaces the decoder in the test context, so this test verifies filter/provider wiring and error translation. It does not verify real JWS signatures.

## 10. Testing `invalid_request` when the client sends tokens improperly

### 10.1. Query parameter and form body are disabled by default

Default `DefaultBearerTokenResolver`:

~~~java
DefaultBearerTokenResolver resolver =
    new DefaultBearerTokenResolver();

resolver.setAllowUriQueryParameter(false);
resolver.setAllowFormEncodedBodyParameter(false);
~~~

Both defaults are `false`; there is no need to call the setters in production if keeping the defaults.

Request with only a query token:

~~~http
GET /api/orders?access_token=query-token HTTP/1.1
Host: api.example.com
~~~

With the default resolver, the query token is ignored. A private endpoint will treat it as having no Bearer credentials and return a 401 challenge without `invalid_token`.

This differs from a request sending a malformed Bearer header.

### 10.2. Enabling query parameters in a dedicated test configuration

To test sending tokens via two methods, configure a test resolver:

~~~java
@Bean
BearerTokenResolver testBearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    resolver.setAllowUriQueryParameter(true);

    return resolver;
}
~~~

Attach the resolver to the Resource Server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(testBearerTokenResolver)
    .jwt(Customizer.withDefaults())
)
~~~

Test:

~~~java
@Test
void tokenInHeaderAndQueryParameterReturnsInvalidRequest()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer header-token"
            )
            .param("access_token", "query-token"))
        .andExpect(status().isBadRequest())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_request\"")
        ));
}
~~~

The resolver detects two token sources and rejects the request before the decoder runs.

**Do not enable query parameter tokens in production just to make this test pass.** Query tokens are easily exposed via URL logs, browser history, analytics, proxies, and monitoring.

### 10.3. Empty or duplicate token parameters

When query parameter support is enabled, cases like:

~~~text
?access_token=
?access_token=one&access_token=two
~~~

can be classified by the resolver as `invalid_request`.

Similarly, if form body support is enabled and a request transmits tokens in both the header and form body, the resolver can detect multiple token methods and reject the request.

### 10.4. Table distinguishing `invalid_request` and `invalid_token` in Spring

| Request | Typical resolver behavior | Status/error |
|---|---|---|
| No Authorization | No token found | 401, Bearer challenge without error |
| `Authorization: Basic ...` | Not Bearer | 401, Bearer challenge without error |
| `Authorization: Bearer bad"token` | Malformed Bearer header | 401 `invalid_token` |
| `Authorization: Bearer not-a-jwt` | Extracts token, decoder cannot parse | 401 `invalid_token` |
| Header + query token when query support enabled | Multiple token sources | 400 `invalid_request` |
| Header + form token when form support enabled | Multiple token sources | 400 `invalid_request` |
| Query token when query support disabled | Ignored | 401 if private route, challenge without error |
| Expired token | Decoder/introspector rejects | 401 `invalid_token` |

Easy-to-confuse point: **a malformed Bearer token does not automatically mean `invalid_request`**. The RFC defines `invalid_token` for malformed access tokens; Spring uses this code by default when the Bearer header is recognized but token syntax is wrong.

## 11. Testing `WWW-Authenticate` with a custom realm

Spring Security provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`.

You can set the realm:

~~~java
@Bean
BearerTokenAuthenticationEntryPoint bearerAuthenticationEntryPoint() {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    entryPoint.setRealmName("orders-api");

    return entryPoint;
}

@Bean
BearerTokenAccessDeniedHandler bearerAccessDeniedHandler() {
    BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();

    handler.setRealmName("orders-api");

    return handler;
}
~~~

Register in the Resource Server configurer:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        BearerTokenAuthenticationEntryPoint entryPoint,
        BearerTokenAccessDeniedHandler deniedHandler)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
            .authenticationEntryPoint(entryPoint)
            .accessDeniedHandler(deniedHandler))
        .build();
}
~~~

When missing a token:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

When the token is invalid:

~~~http
WWW-Authenticate: Bearer realm="orders-api",
                  error="invalid_token"
~~~

When authenticated but denied:

~~~http
WWW-Authenticate: Bearer realm="orders-api",
                  error="insufficient_scope"
~~~

`BearerTokenAuthenticationEntryPoint` extracts status/error details from `BearerTokenError` and formats the challenge per RFC 6750. `BearerTokenAccessDeniedHandler` handles access denial; when a valid OAuth `Authentication` exists, the handler uses `insufficient_scope` according to bearer-token semantics.

### 11.1. Realm is optional

Configuring a realm is not mandatory. If unset, the default challenge may simply be:

~~~http
WWW-Authenticate: Bearer
~~~

Tests should not depend on a realm unless the application commits to a realm in its API contract.

### 11.2. Do not compare the entire header with a fixed string

A response may include `realm`, `error`, `error_description`, `error_uri`, and other parameters. Spring Security versions may also include resource metadata if configured.

More stable test:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    startsWith("Bearer")
))
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    containsString("error=\"invalid_token\"")
));
~~~

Only assert the entire header if the application explicitly publishes a fixed challenge string as its contract.

## 12. Testing a valid token missing a scope

Use `jwt()` for quick authorization testing:

~~~java
@Test
void validAuthenticationWithoutExportScopeReturns403()
        throws Exception {

    mvc.perform(get("/api/orders/export")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"insufficient_scope\"")
        ));
}
~~~

This test has a specific target:

- The Spring Security filter chain still runs if MockMvc has security filters attached.
- `jwt()` supplies a mock JWT authentication.
- The test does not call the decoder or verify signatures.
- The authorization rule rejects due to missing `SCOPE_orders.export`.
- The Bearer access-denied handler returns 403 and the appropriate challenge.

This is a good way to test HTTP permissions without signing a JWT in every test.

### 12.1. Comparing `401` and `403`

| Assertion | What the test is checking |
|---|---|
| 401, `Bearer` challenge, no error | No Bearer credentials |
| 401, `error="invalid_token"` | Token was sent, but failed authentication |
| 400, `error="invalid_request"` | Malformed token transport/request structure |
| 403, `error="insufficient_scope"` | Valid OAuth Authentication, but insufficient permissions |
| 403 without Bearer error | Likely CSRF or another access-denied path |

A test returning 403 is not guaranteed to mean missing scope. If CSRF is enabled, `CsrfFilter` can reject a POST before authorization rules are evaluated. When testing insufficient scope, use a safe request method like GET or send a valid CSRF token if POST is required.

## 13. Testing Opaque Tokens similarly

For opaque tokens, `BearerTokenResolver` still extracts the token from the header. The difference is that the provider calls `OpaqueTokenIntrospector` instead of `JwtDecoder`.

Configuration:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

Scenarios:

| Request | Result |
|---|---|
| No token | 401 Bearer challenge |
| Malformed Bearer header | 401 `invalid_token` |
| Inactive opaque token | 401 `invalid_token` |
| Introspection response active but missing authority | 403 `insufficient_scope` |
| Introspection endpoint failure | No authentication granted; response depends on exception handling |
| Header + query token when query support enabled | 400 `invalid_request` |

Test opaque authorization with `opaqueToken()`:

~~~java
@Test
void opaqueAuthenticationWithoutRequiredAuthorityIsForbidden()
        throws Exception {

    mvc.perform(get("/api/orders/export")
            .with(opaqueToken()
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"insufficient_scope\"")
        ));
}
~~~

`opaqueToken()` creates a sample authentication. It does not call the introspection endpoint. To test `active=false`, credentials, or timeouts, send `Authorization: Bearer ...` through the filter chain with a real `OpaqueTokenIntrospector` pointing to a test server/stub.

## 14. Custom AuthenticationEntryPoint: preserving the protocol header

Some APIs need a JSON body for clients:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A bearer access token is required"
}
~~~

You can create a custom `AuthenticationEntryPoint`, but you must delegate to or reuse the Bearer challenge logic:

~~~java
public final class JsonBearerAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.delegate.setRealmName("orders-api");
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        delegate.commence(request, response, exception);

        response.setContentType(MediaType.APPLICATION_JSON_VALUE);

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "code", "AUTHENTICATION_REQUIRED",
                "message", "A bearer access token is required"
            )
        );
    }
}
~~~

Required imports:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
~~~

This is an illustrative skeleton. A production implementation must classify exceptions so the body code/message fits `invalid_token`, `invalid_request`, and missing credentials, while not overwriting the status already set by the delegate. To return bodies for 400/401/403, also configure `AccessDeniedHandler` where appropriate.

**Do not use `@ControllerAdvice` as the sole solution** for Bearer filter errors. Authentication failures occur inside the Servlet filter chain before any controller is invoked; MVC exception advice usually does not catch these errors like controller exceptions.

## 15. Custom error responses must not drop WWW-Authenticate

A common bug is a custom entry point that only writes JSON:

~~~java
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
~~~

Without adding the challenge header, clients do not receive Bearer authentication details per RFC 6750.

When writing a custom handler:

- Preserve the status matching `BearerTokenError`.
- Always send `WWW-Authenticate` when a protected resource lacks a valid/permitted access token.
- Do not add `invalid_token` when the request sent no token.
- Do not return `invalid_request` for every JWT signature failure.
- Do not turn 403 into 401 just to make clients refresh tokens automatically.
- Do not write raw access tokens or secrets into the body/headers.
- Do not let error descriptions expose internal hostnames, issuer discovery URLs, or stack traces.

## 16. Testing AuthenticationEntryPoint and AccessDeniedHandler separately

If the application has custom handlers, write dedicated tests.

### 16.1. Entry point for missing credentials

~~~java
@Test
void missingCredentialsUsesBearerEntryPoint() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ));
}
~~~

### 16.2. Entry point for invalid tokens

~~~java
@Test
void invalidTokenUsesInvalidTokenChallenge() throws Exception {
    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer not-a-jwt"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

### 16.3. Access denied handler for authenticated callers

~~~java
@Test
void insufficientAuthorityUsesBearerAccessDeniedHandler()
        throws Exception {

    mvc.perform(get("/api/orders/export")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"insufficient_scope\"")
        ));
}
~~~

These tests confirm the handlers are wired properly into the chain. If testing a custom JSON body, assert `Content-Type`, response code, and `WWW-Authenticate` separately.

## 17. Testing the resolver directly when isolating syntax

Not every case requires booting a Spring context. `DefaultBearerTokenResolver` can be unit tested with `MockHttpServletRequest`.

Example:

~~~java
class DefaultBearerTokenResolverTests {

    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void noAuthorizationHeaderReturnsNull() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        assertThat(resolver.resolve(request)).isNull();
    }

    @Test
    void validBearerHeaderReturnsToken() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer abc.def-123"
        );

        assertThat(resolver.resolve(request))
            .isEqualTo("abc.def-123");
    }

    @Test
    void malformedBearerHeaderThrowsInvalidToken() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer bad\"token"
        );

        assertThatThrownBy(() -> resolver.resolve(request))
            .isInstanceOf(OAuth2AuthenticationException.class)
            .extracting(ex ->
                ((OAuth2AuthenticationException) ex)
                    .getError().getErrorCode())
            .isEqualTo(BearerTokenErrorCodes.INVALID_TOKEN);
    }
}
~~~

Key imports:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrorCodes;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

This unit test verifies resolver behavior independently. It does not prove `BearerTokenAuthenticationFilter` converts the exception into the right status/header. That is why the MockMvc integration tests in earlier sections are needed.

## 18. Minimum test matrix to maintain

| Test | Request setup | Expected status | Header to assert |
|---|---|---:|---|
| Public endpoint | No token | 200 | Bearer challenge not required |
| Private endpoint missing token | No Authorization | 401 | `Bearer`, no `error` |
| Wrong scheme | `Authorization: Basic ...` | 401 | `Bearer`, no `error` |
| Malformed Bearer header | Token with invalid characters | 401 | `error="invalid_token"` |
| Non-JWT token string | Bearer value parse fails | 401 | `error="invalid_token"` |
| Invalid JWT signature | JWT signed with different key | 401 | `error="invalid_token"` |
| Wrong JWT issuer/audience | Claims validation fails | 401 | `error="invalid_token"` |
| Expired JWT | `exp` in the past | 401 | `error="invalid_token"` |
| Token sent in two places | Header + query/form when support enabled | 400 | `error="invalid_request"` |
| Query token when support disabled | Only `access_token` query | 401 | `Bearer`, no `error` |
| Valid token missing scope | Mock or signed JWT with missing authority | 403 | `error="insufficient_scope"` |
| Inactive opaque token | Introspection `active=false` | 401 | `error="invalid_token"` |
| Active opaque token missing scope | Introspection active, missing scope | 403 | `error="insufficient_scope"` |
| Missing CSRF | POST when CSRF enabled | 403 | May lack Bearer `insufficient_scope` |
| Custom entry point | Missing/invalid token | 401 | Header preserved + JSON contract |
| Custom access denied handler | Valid authentication, missing permission | 403 | Header preserved + body contract |

### 18.1. Checking side effects

Besides status/headers, verify the controller or service is not invoked when authentication fails:

~~~java
verifyNoInteractions(ordersService);
~~~

This helps catch bugs where the final response is rejected yet business code executed earlier.

### 18.2. Do not overfit `error_description`

Prefer asserting:

~~~java
containsString("error=\"invalid_token\"")
~~~

rather than:

~~~java
equalTo(
    "Bearer error=\"invalid_token\", error_description=\"An error occurred while attempting to decode the Jwt: ...\""
)
~~~

Messages depend on the decoder, version, and exception chain. Only test exact messages if the API has a clear contract and the content contains no sensitive information.

## 19. Common anti-patterns

### 19.1. Treating every 401 as an invalid token

Missing token and invalid token have different meanings. Clients should not refresh a token just because an endpoint returns 401 when the request sent no credentials.

### 19.2. Returning 400 for every Bearer error

An invalid JWT signature is `invalid_token`, usually 401. `invalid_request`/400 is for invalid request structure or token transport.

### 19.3. Missing token returning `error="invalid_token"`

Without a token, it is impossible to conclude the token is invalid. The challenge should only indicate that the Bearer scheme is supported.

### 19.4. Asserting only the status code

Two responses can both be 401 while one has `invalid_token` and the other has no error. Clients handle them differently; tests must assert the header.

### 19.5. Using `jwt()` to test malformed tokens

`jwt()` creates mock authentication. It does not invoke the Bearer resolver or decoder. Use a real Bearer header to test authentication failures.

### 19.6. Using `opaqueToken()` to test `active=false`

`opaqueToken()` creates a sample authentication. It does not call the introspection endpoint. Send `Authorization: Bearer ...` through the filter chain with a real/stub introspector.

### 19.7. Disabling filters to test 401/403

`@AutoConfigureMockMvc(addFilters = false)` skips security filters. Test results no longer demonstrate Resource Server behavior.

### 19.8. Using `@ControllerAdvice` instead of an entry point

Errors from `BearerTokenAuthenticationFilter` occur before MVC controllers. Configure `AuthenticationEntryPoint`/`AccessDeniedHandler` on the filter chain.

### 19.9. Putting raw tokens into `error_description`

Response headers can be logged by clients, proxies, or monitoring. Never echo raw tokens, full payloads, or sensitive data.

### 19.10. Enabling query token transport without reason

Tokens in URLs risk appearing in access logs, browser history, analytics, and referrers. Keep default header transport unless there is a specific legacy requirement.

### 19.11. Treating every 403 as insufficient scope

CSRF, tenant ACLs, ownership, or custom policies can also produce 403. Identify which handler/filter rejected the request before concluding scope is missing.

### 19.12. Hardcoding the entire WWW-Authenticate header in tests

Realm, `error_description`, `error_uri`, and metadata parameters may change. Assert the scheme and key error code per contract.

## 20. Debugging unexpected responses

### Case A: No token yet server returns 200

Check:

- Does the route have `permitAll()`?
- Does the request match any `SecurityFilterChain`?
- Is there a fallback chain?
- Is MockMvc using `addFilters=false`?
- Is the test calling `.with(jwt())`, `.with(user())`, or `@WithMockUser`?
- Does a security test configuration replace the production chain?

### Case B: No token and 401 response lacks WWW-Authenticate

Check:

- Does the chain use OAuth2 Resource Server?
- Was `AuthenticationEntryPoint` replaced by a custom one?
- Does the custom entry point write the header?
- Is a proxy/gateway stripping response headers?
- Is the test inspecting the filter chain's response or a response produced by another layer?

### Case C: Malformed token returns 400

Check:

- Is the resolver in use `DefaultBearerTokenResolver`?
- Did the request send the token in multiple places?
- Is query/form token support enabled?
- Is a custom `BearerTokenResolver` classifying errors differently?
- Is the exception actually `BearerTokenErrorCodes.INVALID_REQUEST`?

A syntactically invalid Bearer header in the current default implementation usually maps to `invalid_token`/401; a request using multiple token sources can map to `invalid_request`/400.

### Case D: Invalid token yet response is 403

Check:

- Was the decoder actually called?
- Did the test use `.with(jwt())` causing the decoder to be bypassed?
- Was a principal already set by a session/other authentication mechanism?
- Is token validation skipped on the active chain?
- Is the actual error authorization/CSRF rather than authentication?

### Case E: Missing scope yet response is 401

Check:

- Did authentication succeed?
- Did the converter map scopes with the right `SCOPE_` prefix?
- Was `AuthenticationEntryPoint` invoked due to a decoder/issuer/audience failure?
- Did `AuthorizationManager` throw an authentication error instead of access denied?
- Did a custom handler change the status?

## 21. Security and operational considerations for response headers

### 21.1. Do not let error messages leak internals

`error_description` is for developers. Do not include:

- Raw JWTs or opaque tokens.
- Private signing keys or client secrets.
- Full contents of sensitive claims.
- Internal hostnames or network paths.
- Stack traces.
- Database errors or table names.
- Unrelated tenant/customer details.

Detailed internal causes may be logged according to policy, but logs must redact the `Authorization` header and never record raw tokens.

### 21.2. `WWW-Authenticate` must be preserved across proxies

If the API sits behind a reverse proxy/API gateway, verify the proxy does not strip the header:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

Clients need this header to distinguish missing credentials, invalid tokens, and insufficient privileges. If a browser SPA needs to read the header over CORS, you may need to expose it:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

CORS exposure only lets JavaScript read the header; it does not replace authentication.

### 21.3. Headers may contain multiple challenges

HTTP allows servers to advertise multiple authentication schemes. Do not assume `WWW-Authenticate` always has only a single Bearer string if the application combines Basic, Negotiate, or other mechanisms.

In tests, assert that the Bearer challenge is present and contains the required error code, rather than assuming the entire header is one fixed value.

## 22. Self-check questions

**1.** What should a request to a private endpoint without a Bearer token return?

> Usually 401 with `WWW-Authenticate: Bearer`; per RFC 6750, no error code should be included when authentication information is missing.

**2.** Which error code does an expired token use?

> `invalid_token`, usually returning 401.

**3.** Does a grammatically invalid Bearer header necessarily return `invalid_request`?

> No. Spring Security's current `DefaultBearerTokenResolver` classifies malformed Bearer headers as `invalid_token`/401.

**4.** When is `invalid_request` typically used?

> Malformed request structure or sending a token via multiple methods, or duplicate/empty token parameters when the corresponding transport is enabled.

**5.** Which status does `insufficient_scope` use?

> 403 Forbidden.

**6.** How do missing token and invalid token differ?

> Missing token means no credential was provided to check; invalid token means the client sent a credential, but the token is invalid.

**7.** Is `WWW-Authenticate` a response body or a response header?

> A response header per the HTTP authentication framework.

**8.** Is `realm` required?

> No. It is an optional authentication challenge parameter.

**9.** Is `error_description` required?

> No. It is optional and developer-facing, and should not contain sensitive information.

**10.** Which Spring class generates the Bearer challenge for authentication failures?

> `BearerTokenAuthenticationEntryPoint`.

**11.** Which Spring class handles access denied for OAuth Bearer authentication?

> `BearerTokenAccessDeniedHandler`.

**12.** Does `.with(jwt())` test the Bearer header parser?

> No. It creates mock JWT authentication for authorization testing.

**13.** What must you do to test a malformed token through the filter chain?

> Send `Authorization: Bearer ...` directly through MockMvc without `.with(jwt())`.

**14.** Are query tokens read by `DefaultBearerTokenResolver` by default?

> No. Query and form body token transports are disabled by default.

**15.** Should query-string tokens be enabled for new APIs?

> No. URLs can be recorded in logs, browser history, proxies, and monitoring.

**16.** Does a 403 response always mean a missing scope?

> No. It could be due to CSRF, roles, tenant membership, ownership, or business policy.

**17.** Why must tests assert `WWW-Authenticate` alongside status?

> Because status alone is not enough to distinguish missing credentials, invalid tokens, and insufficient scope.

**18.** Why must a custom `AuthenticationEntryPoint` preserve the Bearer challenge?

> Because clients need the protocol signal to know the server requires Bearer authentication and to understand credential errors.

## 23. References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer request syntax, `WWW-Authenticate`, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer filter, authentication entry point, and access denied flow.
- [Spring Security — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): token extraction and custom `BearerTokenResolver`.
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): translating `BearerTokenError` into HTTP status and `WWW-Authenticate`.
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): RFC 6750 access-denied response.
- [Spring Security — DefaultBearerTokenResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): reading Authorization headers, form/query parameters, and syntax validation.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()` and `opaqueToken()` test helpers.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `springSecurity()` and `FilterChainProxy`.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers, authorities, and `denyAll`.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): `webAppContextSetup` and MVC test support.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` and `@AutoConfigureMockMvc`.

**Conclusion:** When testing a Spring Security Resource Server, clearly separate **missing token**, **invalid Bearer header/token**, **improper token transmission**, and **valid token with insufficient permissions**. RFC 6750 defines the `WWW-Authenticate` challenge as an essential protocol signal: missing credentials are typically 401 without an error; `invalid_token` is 401; `invalid_request` is typically 400; `insufficient_scope` is 403. Use MockMvc with the real `FilterChainProxy` to verify statuses/headers, and use real Bearer requests when testing the resolver/decoder; `.with(jwt())` is only suitable for testing authorization with mock authentication.
