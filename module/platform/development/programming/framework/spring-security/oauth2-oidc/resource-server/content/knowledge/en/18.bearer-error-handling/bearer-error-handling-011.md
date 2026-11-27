# Testing Filter Responses Rather Than Only Controller Exceptions

In **Spring Security OAuth 2.0/OIDC Resource Server**, many access-token errors are detected **before a request ever reaches a controller**. An expired Bearer token, bad signature, token unrecognized by the Authorization Server, or missing scope can cause the **Spring Security filter chain** to emit an HTTP response with status **401/403** and a **`WWW-Authenticate`** header. Therefore, testing only exceptions thrown by controllers or handled by `@RestControllerAdvice` **does not prove** the API returns compliant OAuth 2.0 Bearer responses.

For example, when a client calls:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer invalid-access-token
~~~

The Resource Server may reject the token inside `BearerTokenAuthenticationFilter` without **ever invoking `OrdersController`**. If a unit test directly calls `controller.getOrder(123L)`, it bypasses the filter, resolver, provider, decoder, entry point, and HTTP authorization rules. That test can pass while real-world requests receive the wrong status or lack a Bearer challenge.

This lesson explains how to **test responses at the HTTP boundary** with Spring Security Servlet Resource Server: distinguishing authentication vs. authorization, `AuthenticationEntryPoint`/`AccessDeniedHandler` error handlers, `WWW-Authenticate` headers under RFC 6750, MockMvc with a **real SecurityFilterChain**, mocking `JwtDecoder` or `OpaqueTokenIntrospector`, and pitfalls when using test helpers that pre-populate Authentication.

## 1. Why Don't Bearer Errors Necessarily Pass Through Controllers?

With a typical Resource Server setup, the processing flow looks like:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["FilterChainProxy selects SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Bearer token present?"}
    D -- "Yes" --> E["AuthenticationManager"]
    E --> F["JwtAuthenticationProvider or OpaqueTokenAuthenticationProvider"]
    F --> G{"Token valid?"}
    G -- "No" --> H["AuthenticationEntryPoint"]
    H --> I["HTTP 401/error response"]
    G -- "Yes" --> J["Authentication in SecurityContext"]
    D -- "No" --> K["Continue filter chain"]
    J --> K
    K --> L["AuthorizationFilter"]
    L --> M{"Sufficient permissions?"}
    M -- "No" --> N["AccessDeniedHandler or AuthenticationEntryPoint"]
    N --> O["HTTP 403 or 401 per state"]
    M -- "Yes" --> P["DispatcherServlet -> Controller"]
    P --> Q["Business HTTP response"]
~~~

This is a **logical responsibility diagram**, not a guarantee of every filter's exact position across all versions. `ExceptionTranslationFilter` normally sits ahead of `AuthorizationFilter` and handles `AuthenticationException`/`AccessDeniedException` thrown downstream of it. Meanwhile, `BearerTokenAuthenticationFilter` can **handle authentication errors itself via `AuthenticationEntryPoint`**. Do not assert that every security exception passes through `ExceptionTranslationFilter`.

| Component | Responsibility |
| --- | --- |
| `FilterChainProxy` | Selects the first `SecurityFilterChain` matching the request |
| `BearerTokenResolver` | Parses Bearer token location/syntax |
| `BearerTokenAuthenticationFilter` | Initiates Bearer authentication if a token is detected |
| `JwtAuthenticationProvider` | Invokes `JwtDecoder` to verify signature, claims, and token profile |
| `OpaqueTokenAuthenticationProvider` | Invokes `OpaqueTokenIntrospector` to verify token status |
| `AuthenticationEntryPoint` | Commences response when authentication is needed or fails |
| `AuthorizationFilter` | Enforces `permitAll`, `authenticated`, scope/authority rules, etc. |
| `AccessDeniedHandler` | Handles post-authentication insufficient-permission requests per policy |
| `DispatcherServlet` | Receives requests only when filters allow them through; MVC controllers/advice run here |

**Testing consequence:** to prove a request with a bad Bearer token returns 401 and skips the controller, tests must start from an **HTTP request traversing the filters**, not by calling controller methods directly.

## 2. Authentication Differs from Authorization and Business Errors

An Orders API requiring `SCOPE_orders.read` can encounter these cases:

| Request | Decision Stage | Typical Response |
| --- | --- | --- |
| No Bearer token sent to protected endpoint | Authorization sees no suitable Authentication; entry point triggered | **401 Unauthorized**, Bearer challenge |
| Expired JWT, bad signature, wrong issuer or audience | Rejected by `JwtDecoder`/provider | **401 Unauthorized**, usually `invalid_token` |
| Opaque token whose introspection returns `active: false` | Rejected by introspector/provider | **401 Unauthorized**, usually `invalid_token` |
| Bearer sent with invalid syntax/method | Resolver/filter detects `invalid_request` | Possibly **400 Bad Request**, depending on config and error kind |
| Valid token lacking `SCOPE_orders.read` | HTTP authorization or method security | **403 Forbidden**, possibly `insufficient_scope` |
| Valid token with scope, does not own order | Business object authorization | **403 or 404** per policy |
| Valid token, controller cannot find order | MVC/controller/business exception handling | **404** or designed business response |

A **401** means the request lacks acceptable authentication. A **403** usually means a principal or context was identified, yet permissions are insufficient. In real applications, custom handlers and other filter errors can produce different responses, so tests must assert the API's **exact contract**.

Never fix a missing-scope 403 by disabling JwtDecoder or removing audience checks. Nor should you turn all errors into 200 just so controllers can return uniform JSON.

## 3. WWW-Authenticate Header Under RFC 6750

**RFC 6750** defines Bearer authentication mechanics and error responses so OAuth 2.0 Clients understand the problem.

A request completely lacking a token to an auth-required endpoint may receive:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Token sent, yet invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Token authenticated, yet missing scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Bearer challenges may also include `realm`, `error_description`, `error_uri`, or `scope`:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

| Bearer Error Code | Situation | Status Associated with RFC 6750 |
| --- | --- | --- |
| `invalid_request` | Request deemed malformed under Bearer rules, e.g., invalid multiple token methods | Usually **400** |
| `invalid_token` | Token expired, revoked, or failed verification | Usually **401** |
| `insufficient_scope` | Valid access token lacking sufficient scope | Usually **403** |

**Not every 401 must include `error="invalid_token"`.** When the client provides no credentials, a standard Bearer challenge may **omit an error code**. A missing-token test should verify status 401 and the Bearer scheme; only tests where a token was sent and rejected require `invalid_token` if mandated by contract.

The examples above are valid forms, **not immutable literal header strings** across all Spring Security versions. Parameter order, realm, error description, and body depend on configured entry points/denied handlers. Never assert the whole literal header string if the contract only requires scheme and error code.

### Checking Status and Bearer Challenge with MockMvc

~~~java
import static org.hamcrest.Matchers.startsWith;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.http.HttpHeaders;

// No token: usually only requires a Bearer challenge.
mockMvc.perform(get("/api/orders/123"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE, startsWith("Bearer")));

// Decoder rejects Bearer token: includes invalid_token with standard handler.
mockMvc.perform(get("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("error=\"invalid_token\"")));
~~~

The snippet assumes a MockMvc configured to **run the filter chain**, and that the mock/real decoder rejects `invalid-token`. You cannot conclude test setup is right merely by sending an arbitrary string.

**Never put access tokens, secrets, stack traces, or sensitive internal errors into `error_description`.** Friendly error descriptions must be intentionally chosen, never dumping raw library exceptions.

## 4. AuthenticationEntryPoint and AccessDeniedHandler Belong to the Filter Layer

For Servlet Resource Server, two key components are:

- **`BearerTokenAuthenticationEntryPoint`** runs when Bearer authentication needs to start/challenge; usually returns 401 and an appropriate `WWW-Authenticate`.
- **`BearerTokenAccessDeniedHandler`** handles access denied in the OAuth2 Bearer authentication branch; usually returns 403 and may add `insufficient_scope`.

`ExceptionTranslationFilter` can distinguish an `AccessDeniedException` from an unauthenticated caller vs. one with an existing Authentication. For an unauthenticated caller, the entry point is called, yielding 401. For an authenticated caller lacking permissions, the access-denied handler usually returns 403.

SecurityFilterChain example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/info").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(
                    new BearerTokenAuthenticationEntryPoint())
                .accessDeniedHandler(
                    new BearerTokenAccessDeniedHandler())
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

For Resource Servers, appropriate Bearer handlers are typically included in defaults; declaring them explicitly here **illustrates which components craft responses**.

**Example assumption:** this is a stateless API authenticated by Bearer tokens, using no browser-auto-sent session cookies. When using cookies/sessions, revisit disabling CSRF. In particular, a POST rejected with 403 by `CsrfFilter` **does not prove** `SCOPE_orders.write` was missing.

## 5. @RestControllerAdvice Does Not Automatically Catch Pre-DispatcherServlet Errors

Suppose the API uses:

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(OrderNotFoundException ex) {
        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(Map.of("error", "order_not_found"));
    }
}
~~~

A controller test throwing `OrderNotFoundException` and asserting 404 proves only **MVC exception handling**. It does not prove:

1. Expired or bad-signature tokens are blocked.
2. `WWW-Authenticate` is generated properly.
3. Missing scopes are blocked by `AuthorizationFilter`.
4. Requests without tokens reach the authentication entry point.
5. Controllers are not invoked when authentication fails.

`@ControllerAdvice` is used by Spring MVC within `DispatcherServlet`. Filters run **outside, before the MVC layer**, so exceptions handled by filters do not automatically flow to `@ControllerAdvice`. An app can wire `HandlerExceptionResolver` from a filter manually, but that is a customization, not Spring Security OAuth2 Resource Server's default flow.

### Two Complementary Test Groups

~~~text
Controller/unit test:
  controller/service throws OrderNotFoundException
  -> @RestControllerAdvice
  -> business 404

Filter integration test:
  GET + Authorization: Bearer invalid-token
  -> BearerTokenAuthenticationFilter
  -> JwtDecoder rejects
  -> AuthenticationEntryPoint
  -> 401 + WWW-Authenticate
  -> Controller is NOT called
~~~

Keep both test groups—never substitute the first for the second.

## 6. Building a Small Controller to Observe Filters

Example controller for testing:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    @GetMapping("/{id}")
    Map<String, String> read(@PathVariable String id) {
        return Map.of("orderId", id);
    }
}
~~~

A separate public controller:

~~~java
@RestController
class PublicController {

    @GetMapping("/public/info")
    Map<String, String> info() {
        return Map.of("service", "orders-api");
    }
}
~~~

With `OrdersSecurity` from section 4:

~~~text
GET /public/info           -> permitAll()
GET /api/orders/{id}      -> SCOPE_orders.read
POST /api/orders/...      -> SCOPE_orders.write
Remaining routes          -> authenticated()
~~~

Test requests must pass through the **SecurityFilterChain containing these matchers**. If MockMvc constructs the controller directly without filters, both tokenless requests and broken-token requests may reach the controller and return 200.

## 7. MockMvc with Real Security Chain and Mocked JwtDecoder

For the goal of **verifying filter responses**, you can keep the real Spring Security filter/provider/entry point/authorization intact and mock only **`JwtDecoder`**. That lets you exercise both failure and success branches without spinning up an Authorization Server/JWKS per test.

Common test setup:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BearerResponseTest {
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;
}
~~~

`@SpringBootTest` loads the application context, and `@AutoConfigureMockMvc` configures MockMvc with appropriate filters. `@MockitoBean` replaces the decoder bean with a Mockito mock in newer Spring Test lines (e.g., Spring Framework 6.2+). On older Spring Boot versions, use compatible `@MockBean`. **Never copy an annotation absent from your current dependencies.**

### Illustrative HTTP Test Suite

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BearerResponseTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void missingBearerOnProtectedEndpointReturns401() throws Exception {
        mvc.perform(get("/api/orders/123"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")));

        verifyNoInteractions(jwtDecoder);
    }

    @Test
    void invalidJwtReturns401FromSecurityFilter() throws Exception {
        when(jwtDecoder.decode("invalid-token"))
            .thenThrow(new BadJwtException("Invalid JWT"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("error=\"invalid_token\"")));
    }

    @Test
    void expiredJwtReportedByDecoderReturns401() throws Exception {
        when(jwtDecoder.decode("expired-token"))
            .thenThrow(new JwtValidationException(
                "JWT expired",
                List.of(new OAuth2Error(
                    "invalid_token", "expired", null))
            ));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer expired-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("error=\"invalid_token\"")));
    }

    @Test
    void validJwtButMissingReadScopeReturns403() throws Exception {
        when(jwtDecoder.decode("token-without-scope"))
            .thenReturn(fakeJwt("token-without-scope", "profile.read"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer token-without-scope"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validJwtWithReadScopeCanReachController() throws Exception {
        when(jwtDecoder.decode("token-with-read-scope"))
            .thenReturn(fakeJwt("token-with-read-scope", "orders.read"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer token-with-read-scope"))
            .andExpect(status().isOk());
    }

    private static Jwt fakeJwt(String token, String scope) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(issued)
            .expiresAt(issued.plusSeconds(31_536_000L * 5))
            .claim("aud", List.of("orders-api"))
            .claim("scope", scope)
            .build();
    }
}
~~~

**Test limitations:** the `fakeJwt(...)` helper creates a `Jwt` object **returned by the mock decoder**, not a validly signed JWT. The expired test branch also **mocks the exception from the decoder**, without actually running `JwtTimestampValidator`. This suite verifies the **Bearer filter/provider, 401/403 responses, Bearer challenge, and scope authorization**—it does not prove signature, issuer, audience, or expiration are verified properly by the production decoder.

To truly test signature/claim policies, add tests with a **real `NimbusJwtDecoder`**, test signing keys/JWKS, and full validators. The two test layers serve different purposes.

### Testing WWW-Authenticate with insufficient_scope

If the Resource Server uses `BearerTokenAccessDeniedHandler` per RFC 6750:

~~~java
when(jwtDecoder.decode("token-without-scope"))
    .thenReturn(fakeJwt("token-without-scope", "profile.read"));

mvc.perform(get("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer token-without-scope"))
    .andExpect(status().isForbidden())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("error=\"insufficient_scope\"")));
~~~

This applies when the handler is configured to emit the corresponding Bearer challenge. A custom `AccessDeniedHandler` may return a different body/header; in that case tests must match the **API's actual contract**.

### Proving the Controller Does Not Run

A 401 test only asserts status. To prove the filter blocks requests **before the controller**, spy/mock a service called by the controller and verify zero invocations:

~~~java
// Illustration when the fixture has a matching orderApplicationService bean.
// @MockitoSpyBean OrderApplicationService orderApplicationService;
//
// mvc.perform(get("/api/orders/123")
//         .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
//     .andExpect(status().isUnauthorized());
//
// verifyNoInteractions(orderApplicationService);
~~~

Only assert zero interactions when the fixture guarantees the service is not invoked during context startup or other tests. Alternatives include a test-only controller with a counter, or testing an observable side effect. **The key point to prove** is that the controller runs no business logic after authentication fails.

## 8. For Opaque Tokens: Mock OpaqueTokenIntrospector

The opaque token branch follows this flow:

~~~text
BearerTokenAuthenticationFilter
    -> OpaqueTokenAuthenticationProvider
    -> OpaqueTokenIntrospector
    -> OAuth2AuthenticatedPrincipal
    -> BearerTokenAuthentication
    -> AuthorizationFilter
~~~

When the introspector rejects an access token, the filter/provider produces an authentication error; when accepted but missing scope, the request can be denied by authorization.

For an app using:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

you can test:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueBearerResponseTest {

    @Autowired MockMvc mvc;
    @MockitoBean OpaqueTokenIntrospector introspector;

    @Test
    void inactiveTokenReturns401() throws Exception {
        when(introspector.introspect("inactive-token"))
            .thenThrow(new BadOpaqueTokenException("Token inactive"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer inactive-token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This test targets an **app configured as an opaque-token Resource Server**, not something to mix into a JWT-only test app expecting the provider to switch modes automatically. Mocking the introspector tests filter responses, yet **does not call a real HTTP introspection endpoint**. To test RFC 7662 `active: false` responses, TLS, client authentication, timeouts, and attribute/authority mapping, use a mock HTTP introspection server or a matching test issuer.

## 9. Why Aren't MockMvc jwt() or opaqueToken() Enough?

Spring Security Test provides request post-processors that construct test Authentications:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This test is useful for verifying **authorization rules** once a request has a `JwtAuthenticationToken`. Yet it normally **skips extracting the Bearer header and invoking the real JwtDecoder**. Likewise, `opaqueToken()` builds a mock opaque principal without calling introspection.

| Testing Approach | Tests Real Bearer Parsing/Filter and Decoder? | Primary Value |
| --- | --- | --- |
| Calling controller directly | No | Controller unit logic |
| MockMvc with `jwt()` | Not on normal Bearer decoding path | Scope and method/URL authorization |
| MockMvc with `opaqueToken()` | Not on normal introspection path | Authorization with opaque principal |
| MockMvc sending `Authorization: Bearer X` with mocked decoder | Real filter/provider, mocked decoder | HTTP error/challenge + filter orchestration |
| MockMvc sending genuinely signed JWT with real decoder/JWKS | Yes, when fixture is configured properly | Signature/claims validation and HTTP responses |
| HTTP opaque token test with introspection test server | Yes, when real client/endpoint configured | Introspection protocol + filter response |

If a “missing token” test accidentally adds `@WithMockUser` or calls `.with(jwt())`, the request already carries a mocked Authentication. The test no longer represents an anonymous caller's HTTP request.

## 10. Pitfall: MockMvc Not Running SecurityFilterChain

A test may build MockMvc like this:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new OrdersController())
    .build();
~~~

This is fine for testing MVC/controllers, yet **does not automatically include the application's Spring Security filters**. Never use results from default `standaloneSetup` to conclude Bearer authentication returns 401/403 properly.

When you need to test both the web app and filter chain, use:

~~~java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@Autowired
WebApplicationContext context;

MockMvc mvc = webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Or use `@SpringBootTest @AutoConfigureMockMvc` with Spring Security integrated. Ensure the filter chain in context matches the route under test.

### WebMvcTest and Slice Tests

`@WebMvcTest` can bring part of Spring Security into an MVC slice, yet does not guarantee loading every `SecurityFilterChain`, decoder, custom filter, or exception handler just like production. When using slice tests, import appropriate configurations and supply missing mock beans; if testing error flows close to runtime reality, `@SpringBootTest @AutoConfigureMockMvc` is usually a clearer starting point.

A sanity test should be:

~~~text
GET /api/orders/123 (no token)
   -> 401 Unauthorized, Bearer challenge

GET /public/info (no token)
   -> permitted if controller returns success
~~~

If a protected endpoint without a token returns 200, check whether the filter chain was loaded, matchers align, or a test helper accidentally attached an Authentication.

## 11. Multiple SecurityFilterChains and permitAll

An application may split chains:

~~~text
@Order(1) publicChain
  securityMatcher("/public/**")
  permitAll(), OAuth2 Resource Server disabled

@Order(2) apiChain
  securityMatcher("/api/**")
  oauth2ResourceServer().jwt()
  scope rules

@Order(3) fallbackChain
  denyAll()
~~~

Spring Security selects the **first chain matching the request**; it does not combine filters from all chains. Therefore, tests must verify representative routes for each chain.

**`permitAll()` does not automatically skip BearerTokenAuthenticationFilter.** When a public endpoint sits **inside the same chain that enables Resource Server**, a request carrying a bad token can still return 401 before the authorization step:

~~~text
Public inside same JWT chain:
  No token           -> possibly 200
  Valid Bearer       -> possibly 200
  Invalid/expired Bearer -> usually 401

Public in separate chain without Bearer Resource Server:
  No token           -> possibly 200
  Invalid Bearer     -> not processed by that chain's Bearer filter
~~~

If the product requires public routes to **ignore any sent Bearer token**, design a separate chain or a `BearerTokenResolver` with intentional matchers. Declaring `.requestMatchers("/public/**").permitAll()` alone does not achieve this.

Do not forget a **fallback chain** for unmatched routes; if no chain guards them, endpoints can accidentally sit outside Spring Security.

## 12. Other Filters Can Produce 401/403: CORS, CSRF, and Custom Filters

When testing 403 or requests failing to reach controllers, do not assume the cause is always a missing scope.

### CORS Preflight

Browsers can send:

~~~http
OPTIONS /api/orders/123 HTTP/1.1
Origin: https://frontend.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflights usually **contain no Bearer token**, even though the subsequent GET does. If CORS is misconfigured, the browser may fail to send the real request.

Example test when the app **permits** the corresponding origin/method/header:

~~~java
mockMvc.perform(options("/api/orders/123")
        .header(HttpHeaders.ORIGIN,
            "https://frontend.example.com")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
            "authorization"))
    .andExpect(status().isOk());
~~~

If CORS is not configured properly, this test can fail—and **that is not necessarily a Bearer authentication bug**. The Resource Server needs CORS configured for valid origins, methods, and headers, e.g., via `.cors(Customizer.withDefaults())` with a CORS configuration source.

### CSRF

A POST can be blocked with 403 by `CsrfFilter` **before** scope rules ever decide. For stateless Bearer-only APIs, configure CSRF to match the application style; for cookie/session apps, never disable CSRF casually.

To test missing scopes cleanly, use a GET with appropriate scope rules or ensure the test handles CSRF according to configuration.

### Custom Filters and Gateways

Rate limiting, tenant filters, security header filters, or gateways can generate responses before controllers. When debugging, identify **which filter actually produced the error**, which security chain was selected, and whether a custom entry point or access-denied handler is active.

## 13. Testing JSON Error Bodies at the Right Layer

Suppose the API wants all 401 errors to use Problem Details:

~~~json
{
  "type": "https://api.example.com/problems/invalid-token",
  "title": "Unauthorized",
  "status": 401,
  "detail": "A valid access token is required"
}
~~~

If the error originates from the Bearer filter, a standard `@RestControllerAdvice` **is not enough** to guarantee this body. You must write or configure **`AuthenticationEntryPoint`** for authentication errors and **`AccessDeniedHandler`** for permission errors; MVC advice continues handling business errors.

~~~text
Bad Bearer token
    -> AuthenticationEntryPoint
    -> 401 + WWW-Authenticate + JSON body (if configured)

Valid access token, missing scope
    -> AccessDeniedHandler
    -> 403 + matching Bearer challenge + JSON body (if configured)

Order not found in controller
    -> @RestControllerAdvice
    -> 404 + business JSON body
~~~

If the app already has a custom entry point returning `application/problem+json`, tests can assert:

~~~java
mockMvc.perform(get("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("invalid_token")))
    .andExpect(content().contentTypeCompatibleWith(
        "application/problem+json"))
    .andExpect(jsonPath("$.status").value(401));
~~~

This expectation **applies only when the app genuinely has a handler returning JSON**. Spring Security defaults may leave the body empty. When writing a custom handler, never omit RFC 6750 Bearer challenges or write the response twice after it has committed.

## 14. Choosing the Boundary to Mock

A practical rule: **keep the component you want to test real, and mock at the boundary outside the test's responsibility**.

| Goal | Keep Real | Can Mock |
| --- | --- | --- |
| 401 + WWW-Authenticate on broken JWT | Bearer filter, provider, entry point | `JwtDecoder` throwing exception |
| 403 on JWT missing scope | Bearer filter, authority converter, authorization rules, denied handler | `JwtDecoder` returning valid Jwt with fewer scopes |
| Missing token | Filter chain, authorization, entry point | Decoder should not be called |
| Verifying exp/iss/aud/signature | `NimbusJwtDecoder` and validators | JWKS/issuer test server |
| Inactive opaque token | Filter/provider and (if testing protocol) real introspector | HTTP introspection test server or mock introspector |
| Order/tenant permissions | Business policy, repository, method security | Identity fixture or matching test token |
| Business @ControllerAdvice | MVC advice, handler mapping | Service throwing business exception |

Do not mock `AuthenticationEntryPoint` itself when your goal is testing the HTTP response produced by that entry point. Do not mock the entire filter chain and treat the response as proof of a valid security configuration.

## 15. Bearer Response Test Matrix

For endpoint GET `/api/orders/123` requiring `SCOPE_orders.read`:

| Scenario | Expected Outcome |
| --- | --- |
| No Authorization header | Usually **401**, Bearer challenge |
| Authorization: Basic ... in Bearer-only app | Usually treated as no Bearer authentication |
| Bearer token with bad signature | Usually **401**, `invalid_token` |
| Expired or not-yet-valid JWT | Usually **401**, `invalid_token` |
| JWT with wrong issuer or audience | Authentication rejected per token validators |
| Opaque token active=false | Usually **401**, `invalid_token` |
| Malformed Bearer request | Possibly **400** + `invalid_request` per resolver and situation |
| Valid token lacking scope | Usually **403**, possibly `insufficient_scope` |
| Valid token with scope | Enters controller; business response |
| Valid token, sufficient scope, lacks permission on order | Usually **403/404** per business policy |
| Public route, no token | Possibly **200** |
| Public route, broken token, same resource-server chain | Possibly **401** before `permitAll` |
| Public route with separate chain without Bearer filter | Broken token is not processed by that chain's Resource Server filter |
| Permitted CORS preflight | Responds per CORS policy, does not require Bearer token |
| POST denied by CSRF | Possibly 403 due to CSRF, not missing scope |
| JWKS/introspection unreachable | Must not grant access if token cannot be verified; exact status depends on handler |

Tests should assert **status, WWW-Authenticate, body, and that the controller did not run** when those elements are part of the contract. Avoid asserting a rigid status for infrastructure failures not standardized by the app itself.

## 16. Common Test Design Mistakes

**“Testing @RestControllerAdvice gives 401, so the Bearer filter returns 401 too.”** No. MVC advice does not automatically catch exceptions occurring before DispatcherServlet.

**“MockMvc standaloneSetup(controller) is enough to test security.”** No. That setup does not automatically register the Spring Security filter chain.

**“Using jwt() with an expired token returns 200, proving the decoder is broken.”** Not necessarily. The test helper constructs a mocked Authentication without necessarily running the decoder/timestamp validators.

**“401 and 403 differ only in response body.”** No. The two codes reflect authentication vs. authorization and may carry different Bearer error codes.

**“No token sent without invalid_token in WWW-Authenticate is a bug.”** No. A Bearer challenge for missing credentials may omit an error code.

**“403 on POST proves the token lacked scope.”** Not guaranteed: rule out CSRF, method security, and business policies.

**“Mocking JwtDecoder proves signature verification.”** No. It merely controls the test outcome.

**“Testing status alone is enough.”** If the API follows RFC 6750, `WWW-Authenticate` and key parameters must also be verified.

**“Returning raw access tokens in JSON errors for debugging is fine.”** No. Bearer tokens are credentials; keep them out of responses, exception descriptions, logs, and metrics.

**“permitAll means the filter ignores any sent token.”** No. `permitAll` is an authorization rule; it does not automatically remove `BearerTokenAuthenticationFilter`.

## 17. Practical Workflow When Testing Filter Errors

1. **Identify the actual chain** for the route: Bearer JWT, opaque token, public, or fallback; check `securityMatcher` and `@Order` when multiple chains exist.
2. **Specify the response contract** for missing token, invalid token, missing scope, object permission errors, and business errors.
3. **Enable the filter chain in tests** using `@SpringBootTest @AutoConfigureMockMvc` or `webAppContextSetup(...).apply(springSecurity())`.
4. **Mock at the right boundary**: `JwtDecoder`/`OpaqueTokenIntrospector` when verifying filter responses; never mock the entry point under test.
5. **Send real HTTP Authorization headers** via `.header(HttpHeaders.AUTHORIZATION, "Bearer ...")`; do not substitute `jwt()` for malformed/expired token scenarios.
6. **Assert status and Bearer challenge**; check body/content type when the API has custom handlers.
7. **Verify the controller did not run** when errors must stop at the filter, using a spy/service fixture as needed.
8. **Separate authentication and authorization tests**: invalid token → 401, authenticated missing scope → 403, sufficient scope but wrong owner/tenant → 403/404 policy.
9. **Add real decoder/integration tests** to verify JWS signatures, issuer/audience/time, or introspection responses/TLS/client authentication.
10. **Maintain a regression suite for public/CORS/CSRF/multiple chains**, because other filters can also determine responses before the controller.

**Key takeaway:** Bearer errors in Spring Security Resource Server are very often detected and returned **before the controller**. To be sure clients actually receive the right response, test **HTTP requests passing through SecurityFilterChain** and observe **status, `WWW-Authenticate`, body, and that execution stops at the right layer**. Controller unit tests and `@RestControllerAdvice` remain necessary for business errors, yet **do not replace testing `BearerTokenAuthenticationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`**.
