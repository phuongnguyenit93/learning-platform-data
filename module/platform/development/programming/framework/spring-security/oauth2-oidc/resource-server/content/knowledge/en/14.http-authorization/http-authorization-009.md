# permitAll Does Not Automatically Disable Processing of Submitted Tokens

When configuring a Spring Security OAuth 2.0 Resource Server, we often want certain endpoints such as `/public/info`, `/health`, or API documentation to be accessible to everyone:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated())
~~~

It is tempting to assume that **`permitAll()` makes Spring Security skip all security steps for that path**. Yet that assumption is **false**. `permitAll()` governs **authorization**: the request does not need granted permissions to proceed. It **does not remove `BearerTokenAuthenticationFilter` from `SecurityFilterChain`**, nor does it by default tell the Resource Server to ignore an access token the client chose to send.

If a public endpoint resides inside a security chain with JWT Resource Server enabled, these two requests can produce different outcomes:

~~~http
GET /public/info HTTP/1.1
Host: api.example.com
~~~

~~~http
GET /public/info HTTP/1.1
Host: api.example.com
Authorization: Bearer <expired-or-invalid-access-token>
~~~

The first request requires no token and can return **200 OK**. The second request **sent a token**, causing the Bearer authentication filter to attempt verification and return **401 Unauthorized** if the token is invalid, **before** the `permitAll()` authorization rule is ever evaluated. Understanding this behavior is essential when designing an API containing both public and protected endpoints.

## 1. Distinguishing Authentication, Authorization, and the Security Filter Chain

Three concepts are frequently confused:

| Concept | Question resolved | Example in Resource Server |
| --- | --- | --- |
| **Authentication** | Is the submitted token valid, and which principal does it belong to? | `BearerTokenAuthenticationFilter` → `JwtAuthenticationProvider` → `JwtDecoder` |
| **Authorization** | Is the request permitted to access the endpoint/resource? | `authorizeHttpRequests(...).requestMatchers(...).permitAll()`, `authenticated()`, `hasAuthority(...)` |
| **SecurityFilterChain** | Which security filters participate in processing matching requests? | A chain with `oauth2ResourceServer(...jwt(...))`, CORS, CSRF, security context, exception handling, etc. |

**`permitAll` belongs to authorization, not filter-chain selection.** Inside a security chain with Bearer authentication enabled, the filter can authenticate the token before reaching authorization, even when the destination request is declared `permitAll()`.

Visualization:

~~~mermaid
flowchart TD
    A["HTTP request /public/info"] --> B["FilterChainProxy selects SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Bearer token present?"}
    D -- "No" --> E["Continue chain"]
    D -- "Yes" --> F["AuthenticationManager + JWT/opaque provider"]
    F --> G{"Token valid?"}
    G -- "No" --> H["Authentication failure → usually 401"]
    G -- "Yes" --> I["Attach Authentication to SecurityContext"]
    I --> E
    E --> J["AuthorizationFilter checks /public/info"]
    J --> K{"permitAll()?"}
    K -- "Yes" --> L["Continue to controller"]
    K -- "No" --> M["Apply another endpoint's rule"]
~~~

The diagram depicts the standard flow in Spring Security's **Servlet SecurityFilterChain** with `oauth2ResourceServer`. Exact filter ordering, exception handlers, and HTTP responses may depend on version/configuration, yet the core principle remains constant: **authorization permitting access does not mean skipping the authentication filter**.

### Why Does Authentication Run Before `permitAll`?

Filters have distinct responsibilities and execute in a fixed order. In a standard Resource Server setup:

1. `FilterChainProxy` selects the `SecurityFilterChain` matching the request.
2. `BearerTokenAuthenticationFilter` uses `BearerTokenResolver` to look for an access token in the request.
3. If a bearer token is present, the filter calls `AuthenticationManager` to verify that token.
4. If the token is valid, the filter stores `Authentication` in `SecurityContext` and lets the request proceed.
5. If the token is invalid, the filter hands the failure to the authentication error mechanism instead of letting the request pass.
6. If no Bearer token is present, the filter usually lets the request continue; public endpoints remain reachable without an identity.
7. Upon reaching authorization, `AuthorizationFilter` applies `permitAll()` or another condition.

The key takeaway is that **the token-processing filter does not ask in advance "is this endpoint `permitAll`?"**. It operates according to the security chain and Bearer-token resolution rules you configured.

## 2. What Does `BearerTokenAuthenticationFilter` Actually Do?

When JWT Resource Server is enabled, a request carrying the header:

~~~http
Authorization: Bearer eyJ...
~~~

is typically handled by `BearerTokenAuthenticationFilter`. Related components:

| Component | Responsibility |
| --- | --- |
| `DefaultBearerTokenResolver` | Extracts the Bearer-formatted token from the request, primarily from the HTTP `Authorization` header by default |
| `BearerTokenAuthenticationToken` | Carries the raw token string as an unauthenticated `Authentication` request |
| `AuthenticationManager` | Dispatches the request to the appropriate provider |
| `JwtAuthenticationProvider` | Uses `JwtDecoder` to verify the JWT, then builds `JwtAuthenticationToken` |
| `OpaqueTokenAuthenticationProvider` | Uses `OpaqueTokenIntrospector` to verify the token via introspection, then builds `BearerTokenAuthentication` |
| `SecurityContextHolder` | Exposes the successful authentication to the remainder of the request |

In a JWT setup:

~~~text
BearerTokenAuthenticationFilter
    |
    +-- No token --> continue chain
    |
    +-- Bearer token present --> AuthenticationManager
                               |
                               v
                         JwtAuthenticationProvider
                               |
                               v
                            JwtDecoder
                               |
                +--------------+--------------+
                |                             |
           Valid JWT                     Invalid JWT
                |                             |
           JwtAuthenticationToken         AuthenticationException
                |                             |
           SecurityContext                  401 / error handler
                |
           AuthorizationFilter
                |
           permitAll / other rule
~~~

An opaque-token Resource Server differs in **how the access token is verified**, not in this principle. Whether using `JwtDecoder` or `OpaqueTokenIntrospector`, a token sent to a public endpoint can still be verified and rejected if invalid.

A Bearer token can be invalid because:

- The token expired per `exp` or is not yet valid per `nbf`.
- The signature is invalid, the algorithm is disallowed, or no trusted verification key exists.
- The issuer `iss` does not match the configured source.
- The audience `aud` is not targeted at this API.
- The token has the wrong type/profile, lacks mandatory claims, or was revoked by the issuer under the active verification mechanism.
- The Bearer header is malformed, supplies multiple disallowed token transport methods, or violates resolver rules.

**`permitAll` does not turn those tokens into valid ones.** If a submitted token is detected by the filter and requires verification, an authentication failure can block the request early on.

## 3. Behavior Matrix: Public Endpoints vs. Protected Endpoints

Suppose the API is configured as:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated())
.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
~~~

And both paths sit in **the same SecurityFilterChain**.

| Endpoint | Bearer token sent | Typical behavior |
| --- | --- | --- |
| `GET /public/info` | No token | **200 OK** if the controller succeeds |
| `GET /public/info` | Valid JWT token | **200 OK**; authentication may be present in the security context |
| `GET /public/info` | Expired JWT | **401 Unauthorized** before `permitAll` allows it |
| `GET /public/info` | JWT with bad signature/wrong issuer | **401 Unauthorized** |
| `GET /public/info` | Malformed Bearer header | May fail Bearer parsing before authorization, often **400** per Bearer/RFC 6750 rules or handler response |
| `GET /api/orders` | No token | **401 Unauthorized** since endpoint requires authentication |
| `GET /api/orders` | Valid JWT with `SCOPE_orders.read` | Request is permitted to enter the controller |
| `GET /api/orders` | Valid JWT missing `SCOPE_orders.read` | **403 Forbidden** |
| `GET /api/orders` | Expired JWT or bad signature | **401 Unauthorized** |

The status codes in the table represent **typical** behavior, not absolute guarantees across every custom `AuthenticationEntryPoint`, `AccessDeniedHandler`, or request handler. For example, a controller may return 404/500 for business reasons even when security lets the request pass.

**401 and 403 address two different issues:**

- **401:** the request lacks required authentication credentials, or the submitted token failed authentication.
- **403:** the request has valid authentication, yet lacks required permissions—such as a missing scope or missing record-level access.

### "Token Not Required" Differs from "Ignore Token If Sent"

These two statements are not equivalent:

1. Endpoint `/public/info` **does not require clients to send a token**.
2. Endpoint `/public/info` **will not process a token even if the client actively sends one**.

`permitAll()` typically satisfies **(1)**, but **does not** guarantee **(2)**. If (2) is a genuine business requirement, explicitly design **security chain selection or skip Bearer resolution for the specified paths**.

## 4. Simple Configuration Example: Public Endpoint Still Validates Sent Bearer Tokens

In a Spring Boot Servlet application, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Configure the issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` and URLs are illustrative. The Resource Server must also check audience and other conditions per the API's token contract.

Example security configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Example controller:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ExampleController {

    @GetMapping("/public/info")
    Map<String, String> publicInfo() {
        return Map.of("service", "orders-api", "status", "available");
    }

    @GetMapping("/api/orders")
    Map<String, String> orders(Authentication authentication) {
        return Map.of("requestedBy", authentication.getName());
    }
}
~~~

In this setup, requests to `/public/info` **still go through the Resource Server filter** because both paths belong to the same chain. `permitAll` only means `AuthorizationFilter` requires no permissions for that public path.

The `csrf(...disable())` call in the example fits a **stateless Bearer-token API that does not use browser-auto-sent authentication cookies**. If an application has cookies/sessions or state-changing endpoints protected by auto-sent credentials, evaluate and configure CSRF appropriately.

### With a Valid Token, a Public Endpoint Can Still Know the User

Suppose the request is:

~~~http
GET /public/info HTTP/1.1
Authorization: Bearer <valid-access-token>
~~~

Because the filter verified the token, a downstream controller or component can receive the corresponding `Authentication` (if the endpoint contract uses it), even though `permitAll` also allows anonymous users.

This enables an **optional authentication** endpoint pattern: a token is not mandatory, yet if a valid token is sent, the application can use the identity to personalize content. However, **optional authentication does not mean optional validation**: invalid tokens can still be rejected right at the filter.

If a product truly wants "treat broken tokens as anonymous guests" on an endpoint, that is **a distinct policy carrying its own risks**. You never get that behavior by default from `permitAll` alone.

## 5. Observing This Behavior with cURL

Assume the application runs at `http://localhost:8080` with `/public/info` as above.

**Without sending a token:**

~~~bash
curl -i http://localhost:8080/public/info
~~~

Typical response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"service":"orders-api","status":"available"}
~~~

**Sending an invalid token:**

~~~bash
curl -i \
  -H 'Authorization: Bearer invalid-token' \
  http://localhost:8080/public/info
~~~

Typical response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Sending a valid JWT access token:**

~~~bash
curl -i \
  -H 'Authorization: Bearer YOUR_VALID_ACCESS_TOKEN' \
  http://localhost:8080/public/info
~~~

If the JWT is valid for the API's issuer/audience/lifetime, the public endpoint can return 200. This is illustrative; do not treat the placeholder string `YOUR_VALID_ACCESS_TOKEN` as a real token.

### When the Error Happens Only for Certain Clients

A browser/frontend may have an interceptor configured to **automatically attach the access token to every request** sent to the API, including public endpoints. When the token expires, `/public/info` unexpectedly returns 401, while opening the same URL from a tool that attaches no bearer token returns 200.

This situation is usually **not a `permitAll` bug**, but occurs because:

1. The public endpoint requires no token.
2. The client still proactively sent an expired token.
3. The Resource Server is configured to validate Bearer tokens whenever a request contains one.

The fix can be as simple as **not attaching bearer tokens to endpoints designed to be public**, rather than overhauling the server's entire filter policy.

## 6. Distinguishing `requestMatchers(...).permitAll()` and `securityMatcher(...)`

The two APIs look similar yet operate at **two different layers**.

### `requestMatchers(...).permitAll()`: an Authorization Rule

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Meaning: the request has already been routed into the chain and runs through its filters; at the authorization step, `/public/**` is permitted to proceed without extra permissions.

### `securityMatcher(...)`: Restricts Which Requests Belong to a Chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Meaning: **this security chain applies only to requests matching `/api/**`**. A request to `/public/info` does not match this chain, so the Resource Server filter **in this chain** does not process its token.

That **does not guarantee public requests bypass every filter**: `FilterChainProxy` may choose another `SecurityFilterChain` for them. If no Spring Security chain matches, requests can pass through the web app without Spring Security protections.

**Recommendation:** If you want public endpoints not to undergo Bearer token processing, design **a dedicated chain with an explicit scope** instead of assuming a `permitAll` rule disables authentication.

## 7. Two `SecurityFilterChain`s: Public Zone Does Not Process Bearer Tokens

If the real requirement is that **the public zone must succeed even when clients send invalid Bearer tokens**, separate those paths into a security chain **without OAuth 2.0 Resource Server enabled**, and configure the remaining chain for protected APIs.

Servlet application example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SeparatePublicAndApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain publicChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/public/**", "/health")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            // Do not call oauth2ResourceServer() in publicChain.
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

### Expected Behavior of the Example

| Request | Chain | Is Bearer token processed by Resource Server filter? |
| --- | --- | --- |
| `GET /public/info` no token | `publicChain` | No, because this chain does not enable Resource Server |
| `GET /public/info` broken JWT | `publicChain` | No, assuming no other filter handles Bearer |
| `GET /health` expired JWT | `publicChain` | No, per the illustrative config |
| `GET /api/orders` no token | `apiChain` | Filter checks for token and finds none; authorization requires authentication and usually returns 401 |
| `GET /api/orders` invalid token | `apiChain` | Yes; authentication fails |
| `GET /api/orders` valid token, right scope | `apiChain` | Yes; authenticated then authorized |

**Important:** the example above **lacks a fallback chain** for paths outside `/public/**`, `/health`, and `/api/**`. If the application has other endpoints, they may **not be protected by Spring Security** without an extra chain. In real products, add a **fallback `SecurityFilterChain`** with a default deny or authentication policy, or design API matchers with full coverage.

A default-deny fallback chain could be:

~~~java
@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

With multiple chains, `FilterChainProxy` selects **the first chain matching the request**, rather than running all chains sequentially and combining their filters. `@Order` and `securityMatcher(...)` are therefore critical.

### Splitting Chains Does Not Make Every Requirement Disappear

A public chain without `oauth2ResourceServer` only prevents **Resource Server Bearer authentication in that chain**. If you enable `httpBasic`, `formLogin`, or a custom authentication filter on the public chain, invalid headers or cookies can still fail via another mechanism. Inspect **all filters actually present**, not just the label "public."

In optional personalization designs, splitting chains this way means public endpoints **do not receive JWT identity via Resource Server**, even with valid tokens. Therefore, choose deliberately between:

- **Public while reading identity if Bearer is valid:** keep one chain, `permitAll`, and validate submitted tokens.
- **Strictly public, ignoring Bearer tokens:** use a separate chain or an explicit token-filtering mechanism.

## 8. Why Is `web.ignoring()` Not the Default Choice?

Some older apps used:

~~~java
// Legacy/illustrative configuration, not recommended for all APIs.
// web.ignoring().requestMatchers("/public/**");
~~~

When paths are configured to **bypass Spring Security completely**, Spring Security filters do not process those requests. That can sidestep broken Bearer tokens on public endpoints, yet simultaneously **drops many other protections**, such as security headers, security context/integrated filters, and request policies inside the Spring Security chain.

Therefore:

- Use **`permitAll()`** when an endpoint is public yet must still go through Spring Security and you accept validating submitted Bearer tokens.
- Use **a separate chain without Resource Server enabled** if you want public routes not to authenticate Bearer tokens while keeping other protective filters configured for those routes.
- Consider **bypassing Spring Security completely** only when it is a fully understood decision, typically for specialized static assets or necessary scenarios.

Modern Spring Security documentation generally recommends `permitAll` over skipping the entire filter chain for resources that benefit from security headers. Skipping filters is not a harmless way to "make things more public."

## 9. Another Option: Customizing `BearerTokenResolver` by Path

In some architectures, an application prefers keeping **one `SecurityFilterChain`** yet actively **skips resolving bearer tokens** on a few public endpoints. You can configure `BearerTokenResolver` to return `null` on requests matching a public list:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

public final class PublicEndpointIgnoringBearerResolver
        implements BearerTokenResolver {

    private final BearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    private final RequestMatcher publicEndpoint =
        new AntPathRequestMatcher("/public/**");

    @Override
    public String resolve(HttpServletRequest request) {
        if (publicEndpoint.matches(request)) {
            return null; // Resource Server treats it as having no Bearer token.
        }
        return delegate.resolve(request);
    }
}
~~~

Wire it into the Resource Server configuration:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(new PublicEndpointIgnoringBearerResolver())
    .jwt(Customizer.withDefaults()))
~~~

**Conditions and limitations:**

1. This is an intentional architectural choice, **not** default behavior of `permitAll`.
2. The `AntPathRequestMatcher` code illustrates versions that still provide this class/API; in newer Spring Security versions, use a version-compatible `RequestMatcher`, such as an appropriate MVC/path-pattern matcher.
3. Returning `null` from the resolver means **valid tokens are also ignored** on public routes; controllers cannot assume a JWT identity is present there.
4. If the matcher is wrong, protected paths may be treated as having no token. In many cases that causes 401, yet if a `permitAll` rule is misplaced or another authentication mechanism is active, the outcome can be more severe.
5. If other filters exist (HTTP Basic, session authentication, custom filters), they can still run on the endpoint.
6. Skip tokens only on **a small, explicit public allowlist**; never use `resolve(...) -> null` for all of `/api/**`.

When architecture permits, **splitting `SecurityFilterChain`s** usually makes responsibilities and processing scopes clearer. Customizing the resolver helps when a shared chain must be kept, provided matchers are carefully controlled and maintained.

## 10. Distinguishing `permitAll` from `anonymous`, `authenticated`, and `hasAuthority`

The rules below express **authorization requirements**, without changing how `BearerTokenAuthenticationFilter` processes submitted tokens:

| Authorization rule | Meaning |
| --- | --- |
| `permitAll()` | Permits all requests at the authorization step, even without a user Authentication |
| `authenticated()` | Requires an authenticated principal per Spring Security rules |
| `anonymous()` | Intended for requests treated as anonymous under the current authentication mechanism |
| `hasAuthority("SCOPE_orders.read")` | Requires an authority with the exact name `SCOPE_orders.read` |
| `hasRole("ADMIN")` | In typical configuration, requires authority `ROLE_ADMIN` |
| `denyAll()` | Denies at the authorization step when the rule applies |

For instance, `anonymous()` differs from `permitAll()`: with a valid token, an authenticated request may **fail** the `anonymous()` rule; conversely, `permitAll()` does not require the caller to be anonymous. With an **invalid** token, the authentication filter may still return 401 before either rule applies.

Never view `permitAll()` as "skip security steps for this request," and never view `denyAll()` as blocking early **before all authentication filters**. Both are decisions of the authorization component inside the chain.

## 11. CORS Preflight, OPTIONS, and Public Paths

Browsers can send a **CORS preflight request** before a request carrying an `Authorization` header:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://frontend.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Normal preflight requests **carry no Bearer token**, even when the subsequent GET carries a Bearer token. If preflight is processed as needing an access token, the frontend hits a CORS error before sending the actual request.

Recommended practices:

- Configure Spring Security CORS properly and allow required origins, methods, and headers; never treat `permitAll` as a complete CORS solution.
- Ensure CORS preflight is handled properly before normal authentication requirements apply.
- Never relax protection across the entire API just to let `OPTIONS` pass.
- Remember that **preflight** and **the actual request** are two separate HTTP requests, so Bearer authentication behavior differs between them.

Example CORS configuration for one allowed origin in supporting versions:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://frontend.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
~~~

Attach CORS processing to the corresponding security chain:

~~~java
.cors(Customizer.withDefaults())
~~~

These snippets illustrate structure; real configurations must also define credentials, allowed methods, response headers, and origin policies. **CORS is not authentication**: permitting preflight does not mean accepting a bad access token on the GET request.

## 12. Testing: How to Prove `permitAll` Does Not Ignore Tokens?

Separate three test categories:

| Test type | What does it prove? | Limitation |
| --- | --- | --- |
| Unit tests of `JwtDecoder`/token validators | Whether JWT is valid per signature, issuer, lifetime, audience | Does not verify the filter chain applied to public routes |
| MVC integration test with real security chain | Whether tokens pass through the Bearer filter and yield 401 on public routes | If decoder is mocked, does not prove real signature verification |
| Authorization tests with `jwt()` in Spring Security Test | `permitAll`/`authenticated`/`hasAuthority` rules for a pre-built Authentication | Typically **bypasses the real Bearer filter and JwtDecoder**, insufficient to test broken tokens |

### 12.1. Scenarios to Include

For an app with one JWT Resource Server chain and `/public/info` set to `permitAll`:

1. **Public, no token:** request enters controller successfully.
2. **Public, valid token:** request enters controller; if controller reads Authentication, it receives the right identity.
3. **Public, expired token:** `JwtDecoder`/validator rejects token; HTTP response is typically 401.
4. **Public, bad signature token:** rejected, despite the route's `permitAll` rule.
5. **Protected, no token:** rejected due to `authenticated()` or scope rule.
6. **Protected, valid token missing scope:** authorization denies, typically 403.
7. **Dedicated public chain without Resource Server:** broken token is not processed by a Resource Server filter; endpoint can return 200.
8. **Preflight:** CORS behavior is verified explicitly without relying on a bearer token.

### 12.2. Example Test with MockMvc and a Mocked Decoder

In an **integration test traversing the security filter chain**, you can replace `JwtDecoder` with a mock to control "valid" vs. "invalid" tokens while keeping the real `BearerTokenAuthenticationFilter`. The snippet below uses `@MockitoBean` on supporting Spring Test versions (e.g., Spring Framework 6.2+); older versions have equivalents such as Spring Boot's `@MockBean`.

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.util.List;

@SpringBootTest
@AutoConfigureMockMvc
class PublicBearerTokenIntegrationTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void publicRequestWithoutTokenIsAllowed() throws Exception {
        mvc.perform(get("/public/info"))
            .andExpect(status().isOk());
    }

    @Test
    void publicRequestWithInvalidBearerTokenIsRejected() throws Exception {
        when(jwtDecoder.decode("expired-token")).thenThrow(
            new JwtValidationException(
                "JWT expired",
                List.of(new OAuth2Error("invalid_token", "expired", null))
            )
        );

        mvc.perform(get("/public/info")
                .header("Authorization", "Bearer expired-token"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicRequestWithValidBearerTokenIsAllowed() throws Exception {
        Jwt jwt = Jwt.withTokenValue("valid-token")
            .header("alg", "RS256")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-11-15T09:00:00Z"))
            .expiresAt(Instant.parse("2030-11-15T09:00:00Z"))
            .claim("scope", "orders.read")
            .build();

        when(jwtDecoder.decode("valid-token")).thenReturn(jwt);

        mvc.perform(get("/public/info")
                .header("Authorization", "Bearer valid-token"))
            .andExpect(status().isOk());
    }
}
~~~

**Conditions for this example:** the test application must have `/public/info`, a security chain with JWT Resource Server enabled, and compatible Spring Boot Test, Spring Security, and Mockito dependencies. `@MockitoBean` is not present in all versions; use the API matching your build. Code constructing the test `Jwt` **does not verify JWS signatures**, because the decoder is mocked here. The test's value lies in proving **the Bearer filter still invokes the decoder on a `permitAll` endpoint**.

To prove **real token verification**, add tests with a real decoder/JWKS or test signing keys and properly signed tokens. Tests using the `jwt()` request post-processor to pre-populate Authentication cannot verify this behavior.

### 12.3. Testing Multiple Chains

With a dedicated public chain configuration:

- Send `Authorization: Bearer nonsense` to `/public/info` → no Resource Server filter exists in the public chain to call the decoder.
- Send the same header to `/api/orders` → the API chain's Bearer filter detects and rejects it.
- Send requests to a route matching neither chain → the fallback chain must enforce your designed policy.

This tests **chain scope**, not merely authorization matcher rules.

## 13. Other Misleading Situations

### "I configured `permitAll`, why is the request still getting 401?"

The request may carry an **expired or invalid access token**, and the Bearer filter rejects it before reaching the authorization rule. Alternatively, a custom filter, HTTP Basic, OAuth2 Login, another chain, or a custom handler could produce the error. Inspect which security chain matched, whether a token was sent, and at which step the exception occurred.

### "If a valid JWT hits a public endpoint, does that endpoint become protected?"

No. `permitAll` still allows requests **without a token**. A valid JWT simply populates an appropriate Authentication on the request. If the controller uses that identity to personalize output, that is optional authentication—it does not turn the authorization rule into `authenticated()`.

### "If I want public requests to always return 200 even with bad tokens, can I swallow all authentication errors?"

Never catch all `AuthenticationException`s and return success application-wide. That can cause protected endpoints to fail open. If the real requirement is ignoring Bearer tokens on a few routes, scope that to **a dedicated chain** or a tightly controlled matcher-based resolver.

### "If a public endpoint has `@PreAuthorize`, does HTTP `permitAll` guarantee entry into the controller?"

No. HTTP authorization and **method security** are two separate check layers. `permitAll` at the request layer only lets the request pass HTTP authorization. A method annotated with `@PreAuthorize("hasAuthority('SCOPE_orders.read')")` can still reject callers lacking the permission.

### "Is using `web.ignoring` for `/public/**` just as safe as `permitAll`?"

Not equivalent. Skipping Spring Security can drop filters and security headers that still run under `permitAll`. Using a separate chain usually preserves appropriate protections without processing JWTs on selected routes.

### "If a security chain is restricted by `securityMatcher('/api/**')`, is `/public/**` definitely safe?"

No. Without a fallback chain, public or other paths may fall outside Spring Security. Inspect **the entire chain configuration**, ordering, patterns, actual routes, and the default policy when no chain matches.

### "If a public endpoint has a Bearer filter, should a refresh token be sent when the access token expires?"

No. Resource Servers **do not** accept refresh tokens to access APIs and do not refresh tokens on a client's behalf. If a public endpoint does not need identity, clients usually should not attach an access token. When calling protected endpoints, clients must obtain a valid access token from the Authorization Server via a supported grant.

## 14. Choosing a Design for Real-World APIs

| Requirement | Approach | Considerations |
| --- | --- | --- |
| Public endpoint requires no token; valid tokens personalize response | `permitAll` inside JWT Resource Server chain | **Invalid** Bearer tokens can still cause the request to fail |
| Public endpoint always ignores any sent Bearer token | Dedicated public `SecurityFilterChain` **without Resource Server** | No JWT Authentication on those routes; keep other filters as needed |
| Prefer shared chain while ignoring Bearer on very specific paths | Custom `BearerTokenResolver` | Matcher must be exact so tokens are never ignored on protected routes |
| Static assets needing no Spring Security filters at all | Consider `web.ignoring` only when genuinely needed | Loses protections/headers provided by Spring Security |
| API requiring scope-based permissions | `hasAuthority("SCOPE_...")` or suitable method security | Still enforce object-level authorization |
| Browser calling API requiring Bearer token | Configure CORS and Bearer Resource Server | Both preflight and actual requests must be handled properly |

For most APIs, a safe starting point is **keeping Spring Security across all protected paths**, explicitly defining public routes, and disabling Bearer processing only where genuinely needed. If a frontend accidentally attaches an expired token to an unauthenticated request, fixing the frontend not to send that token is often the smallest, cleanest change.

## 15. Summary

**`permitAll()` means "no permission required at the authorization step," not "skip security filters."** When a public request traverses a `SecurityFilterChain` with Resource Server enabled, `BearerTokenAuthenticationFilter` can still validate any access token the client submits:

~~~text
GET /public/info
  No Bearer token      -> no authentication needed -> permitAll -> controller
  Valid Bearer         -> authentication succeeds  -> permitAll -> controller
  Invalid Bearer       -> authentication error     -> usually 401, before permitAll
~~~

To avoid processing bearer tokens on public routes, **actively design filter-chain selection or a Bearer resolver**. To keep endpoints public while recognizing signed-in users, use `permitAll` with standard Bearer handling and accept that submitted tokens must be valid. Whichever approach you choose, **never compromise JWT, issuer, audience, or object-permission checks on protected endpoints** just to make a public route return 200.
