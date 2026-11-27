# SecurityFilterChain and Where Bearer Tokens Are Processed

## 1. Where Does a Resource Server Protect Requests?

In a **Spring Boot + Spring Security OAuth 2.0 Resource Server** application running on the **Servlet stack** (Spring MVC), Bearer access token authentication takes place in the **Servlet Filter chain** before the request reaches `DispatcherServlet` and the controller.

For example:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOi...
~~~

For the request above to be processed securely, the system must perform several steps:

1. Select the right security configuration that applies to the `/api/orders` path.
2. Locate the Bearer access token string in the HTTP request.
3. Validate the access token via JWT signature/claim validation or opaque token introspection.
4. Store the successful authentication information in the `SecurityContext`.
5. Check the caller's permissions for the endpoint and resource.
6. Allow the request to proceed to the controller if it passes the applicable rules.

These steps are handled by multiple filters and components working together, **not the job of a single filter alone**.

This lesson focuses on the question: **Where does `SecurityFilterChain` sit in the Servlet request lifecycle, at which stage does `BearerTokenAuthenticationFilter` run, and how is the authentication result used before authorization?**

## 2. Distinguishing Three Layers of "Filter Chain"

### 2.1. The Container's Servlet Filter Chain

A Servlet container such as Tomcat creates a **Servlet Filter Chain** for a request. Filters are invoked before the target Servlet, and can read the request, add response headers, and decide whether to continue or stop processing.

Overview:

~~~text
HTTP client
   |
   v
Servlet container
   |
   v
Servlet Filter 1 -> Servlet Filter 2 -> ... -> DispatcherServlet
                                                |
                                                v
                                           Spring MVC Controller
~~~

In an application with Spring Security, the container does not directly manage individual Spring Security filters such as `BearerTokenAuthenticationFilter`. Instead, the container typically invokes a **`DelegatingFilterProxy`**.

### 2.2. `DelegatingFilterProxy`: The Bridge Between the Servlet Container and Spring

`DelegatingFilterProxy` is a Servlet Filter that delegates work to a Spring bean. With Spring Security, the common bean name is `springSecurityFilterChain`, which is actually provided by **`FilterChainProxy`**.

Diagram:

~~~text
Servlet container filter chain
             |
             v
DelegatingFilterProxy (springSecurityFilterChain)
             |
             v
FilterChainProxy (Spring Security)
             |
             v
Selected SecurityFilterChain
             |
             v
Spring Security filters
             |
             v
DispatcherServlet / Controller
~~~

Thus, `DelegatingFilterProxy` handles integration with the Servlet container, while `FilterChainProxy` coordinates the **security filter chains** defined by Spring Security.

### 2.3. `FilterChainProxy` and `SecurityFilterChain`

**`FilterChainProxy`** is Spring Security's coordinating filter. It can contain **multiple `SecurityFilterChain` instances**, each with a request matcher and a list of security filters.

**`SecurityFilterChain`** is not a single filter. It represents:

- **Which requests does this chain protect?** — the matcher, for example `/api/**`.
- **Which Spring Security filters will run for those requests?** — authentication, context handling, authorization, exception handling, and so on.

When there are multiple chains, `FilterChainProxy` evaluates them in order and uses **the first chain that matches the request**. It does not merge filters from all matching chains simultaneously.

> Distinction: `SecurityFilterChain` selects the **security pipeline**; `authorizeHttpRequests` defines **access rules inside the selected pipeline**. These two steps are different.

## 3. Big Picture of a Bearer Token Request in the Servlet Stack

~~~mermaid
flowchart TD
    A["HTTP request with Authorization: Bearer ..."] --> B["Servlet container"]
    B --> C["DelegatingFilterProxy"]
    C --> D["FilterChainProxy"]
    D --> E{"First matching SecurityFilterChain?"}
    E -->|"No matching chain"| Z["No protection from Spring Security chain"]
    E -->|"Matching chain"| F["SecurityContextHolderFilter and supporting filters"]
    F --> G["BearerTokenAuthenticationFilter"]
    G --> H["BearerTokenResolver extracts token"]
    H --> I{"Bearer token present?"}
    I -->|"Yes"| J["AuthenticationManager"]
    J --> K["JwtAuthenticationProvider or OpaqueTokenAuthenticationProvider"]
    K --> L{"Authentication valid?"}
    L -->|"No"| M["Handle authentication failure, usually 401"]
    L -->|"Yes"| N["Store Authentication in SecurityContext"]
    I -->|"No"| O["Continue through remaining filters"]
    N --> O
    O --> P["AnonymousAuthenticationFilter if no Authentication yet"]
    P --> Q["ExceptionTranslationFilter / AuthorizationFilter"]
    Q --> R{"Access authorized?"}
    R -->|"No"| S["401 or 403 depending on cause"]
    R -->|"Yes"| T["DispatcherServlet / Controller"]
~~~

This is a **conceptual** diagram. The exact list, position, and presence of individual filters depend on the configuration and Spring Security version. In practice, there are also filters for headers, CORS, CSRF, logout, request cache, anonymous authentication, and many other features.

Key points to keep in mind in the Resource Server flow:

- `FilterChainProxy` must select the right chain.
- A chain accepting Bearer tokens needs `BearerTokenAuthenticationFilter` (typically added by `oauth2ResourceServer`).
- Authentication is performed **before the endpoint authorization decision**.
- `AuthorizationFilter` can use the `Authentication` information after the Bearer token has been authenticated.
- A request without a Bearer token can continue through the chain, but an endpoint requiring authentication will still ultimately be rejected if there is no other authentication mechanism.

### 3.1. Example Relative Order of Filters

In a modern Spring Security Servlet configuration, part of the chain can be pictured as follows:

~~~text
SecurityContextHolderFilter
    |
    v
HeaderWriterFilter / CorsFilter / CsrfFilter / ...  (if configured)
    |
    v
LogoutFilter / other authentication filters (if any)
    |
    v
BearerTokenAuthenticationFilter
    |
    v
RequestCacheAwareFilter / SecurityContextHolderAwareRequestFilter / ...
    |
    v
AnonymousAuthenticationFilter
    |
    v
ExceptionTranslationFilter
    |
    v
AuthorizationFilter
    |
    v
Controller if permitted
~~~

The order above helps visualize key processing milestones; it is **not a fixed filter list for every application**. For example, an API that only authenticates Bearer tokens will not need to run form login; an application that also supports session login may contain additional corresponding filters.

Two ordering rules to remember:

1. `BearerTokenAuthenticationFilter` must have the opportunity to authenticate the Bearer token **before authorization decides access**.
2. `AnonymousAuthenticationFilter` may supply an anonymous principal when no authentication exists yet; it **does not turn an anonymous request into a validly logged-in request**.

## 4. Configuring a SecurityFilterChain for a JWT Resource Server

### 4.1. Dependencies and Issuer

Spring Boot example using Spring MVC and JWT access tokens:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

`issuer-uri` is a placeholder example; it must be replaced with the real issuer of your Authorization Server. With a provider that supports compatible metadata/JWKS, Spring can use the issuer configuration to determine the keys for verifying JWTs.

**Note:** verifying the JWT signature/issuer/expiration does not automatically guarantee that the token is intended for the right API. For APIs that require `aud` restriction, you must configure audience validation appropriate for your version and token contract.

### 4.2. Defining the Filter Chain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // Example API authenticating via Authorization: Bearer,
            // not using cookies/sessions to authenticate requests.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
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

Role of each configuration group:

| Component | Role |
|---|---|
| `SecurityFilterChain` bean | Set of security rules and filters managed by Spring |
| `HttpSecurity` | DSL for building the filter chain |
| `authorizeHttpRequests(...)` | Allow/deny policy for each endpoint |
| `oauth2ResourceServer(...jwt(...))` | Enables Bearer JWT access token authentication |
| `SessionCreationPolicy.STATELESS` | Does not create/use an `HttpSession` to store the SecurityContext for the API's authentication mechanism |
| `csrf(AbstractHttpConfigurer::disable)` | Appropriate only under the assumption that the API uses Bearer tokens outside cookies and does not authenticate via browser cookies |

**Do not disable CSRF by habit for every application.** If there are endpoints using cookies/sessions or any mechanism where the browser automatically sends credentials, you must analyze and keep appropriate CSRF protection. `STATELESS` also does not replace CSRF configuration or CORS decisions.

The line enabling `oauth2ResourceServer(...jwt(...))` is what causes Spring Security to build the JWT Bearer pipeline; normally you do not need to manually create or register `BearerTokenAuthenticationFilter`.

### 4.3. A Request Flowing Through This Configuration

Client call:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

If the access token is valid, has the `orders.read` scope, and passes all other constraints, the GET request is processed. By default, Spring Security typically maps compatible `scope`/`scp` claims into authorities with the `SCOPE_` prefix, so `orders.read` is checked via `SCOPE_orders.read`.

Example controller:

~~~java
package com.example.orders.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/orders")
    public Map<String, String> currentSubject(
            @AuthenticationPrincipal Jwt jwt) {

        // Illustrates the authenticated principal only.
        // A real endpoint must also verify order ownership.
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

`@AuthenticationPrincipal Jwt` fits the **JWT** Resource Server flow. If the application uses **opaque token introspection**, the principal is typically of type `OAuth2AuthenticatedPrincipal`, and should not be assumed to cast to `Jwt`.

## 5. What Does `BearerTokenAuthenticationFilter` Do?

`BearerTokenAuthenticationFilter` is the filter responsible for receiving and processing Bearer access tokens in Servlet requests.

### 5.1. Step 1 — Extract the Token Using `BearerTokenResolver`

By default, the resolver looks for:

~~~http
Authorization: Bearer <access_token>
~~~

`BearerTokenResolver` only returns the token string or indicates no token was found; it does not validate the token's contents yet.

When no Bearer token is present, the filter normally lets the request continue. This is useful because a chain may have `permitAll` endpoints or another authentication mechanism.

If the header contains a malformed Bearer value, the resolver may throw an error; the filter handles it via the authentication failure path.

### 5.2. Step 2 — Create an Authentication Request

When a token is found, the filter creates a **`BearerTokenAuthenticationToken`** object containing the token string and passes it to the configured **`AuthenticationManager`**.

Processing flow:

~~~text
HTTP Authorization header
         |
         v
BearerTokenResolver
         |
         v
String accessToken
         |
         v
BearerTokenAuthenticationToken
         |
         v
AuthenticationManager
         |
         v
Corresponding AuthenticationProvider
~~~

In advanced designs, `BearerTokenAuthenticationFilter` can work with `AuthenticationManagerResolver<HttpServletRequest>` to select a manager per request. Selecting an issuer/manager must be based on an allowlist and trust policy, never blindly trusting whatever issuer an unverified token claims.

### 5.3. Step 3 — Validate the JWT or Opaque Token

For a JWT Resource Server:

~~~text
BearerTokenAuthenticationToken
        |
        v
JwtAuthenticationProvider
        |
        v
JwtDecoder (usually NimbusJwtDecoder)
        |
        v
Signature verification + validators (issuer/time/audience/...)
        |
        v
JwtAuthenticationConverter
        |
        v
JwtAuthenticationToken (authenticated Authentication)
~~~

`JwtDecoder` is responsible for verifying the JWS signature and running configured validators. `JwtAuthenticationConverter` converts claims into a principal and authorities. By default, the principal name is typically based on `sub`, and valid scopes can become `SCOPE_<scope>` authorities.

For an opaque token:

~~~text
BearerTokenAuthenticationToken
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
OpaqueTokenIntrospector
        |
        v
Valid introspection result
        |
        v
BearerTokenAuthentication
~~~

Both use the Bearer token filter at the HTTP layer; the difference lies in **how the token is validated and converted into an `Authentication`**.

### 5.4. Step 4 — Store Authentication in `SecurityContext`

After success, the filter creates a `SecurityContext` and places the authenticated `Authentication` into `SecurityContextHolder` for processing the request.

Downstream filters and controllers can read the context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

In controllers, it is usually better to use parameter injection or `@AuthenticationPrincipal`:

~~~java
@GetMapping("/api/whoami")
public Map<String, String> whoAmI(Authentication authentication) {
    return Map.of("name", authentication.getName());
}
~~~

When the request finishes, Spring Security manages clearing the context according to the filter lifecycle. **Do not store an `Authentication` in a static field yourself**, and do not treat `SecurityContextHolder` as permanent storage for a user's login.

With a stateless Bearer token model, subsequent requests normally must continue sending the token; `SessionCreationPolicy.STATELESS` helps avoid relying on a session to remember the `SecurityContext` from an earlier request.

### 5.5. Step 5 — Continue the Filter Chain

After authentication succeeds, `BearerTokenAuthenticationFilter` invokes the remaining filters downstream. That is why a valid token **can still be denied access** at `AuthorizationFilter`.

The Bearer filter is responsible for **authentication**, while authorization is enforced through rules such as:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

and can be supplemented by business-level authorization checks when reading, modifying, or deleting records.

## 6. `AuthorizationFilter` Evaluates Access After Authentication

In modern configurations using `authorizeHttpRequests`, **`AuthorizationFilter`** typically sits near the end of the Spring Security chain. It delegates the decision to an `AuthorizationManager` based on the request and the current `Authentication`.

Example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
~~~

Meaning:

- `permitAll()`: the endpoint does not require authorization at this authorization step.
- `authenticated()`: requires an authentication that Spring Security considers authenticated, not anonymous.
- `hasAuthority("SCOPE_orders.read")`: requires a specific authority.
- `denyAll()`: rejects the request even if it has a valid token.

Rules are evaluated in matcher order, so specific rules should be placed before general rules.

A properly signed JWT token with scope `orders.write` **does not automatically satisfy** a rule requiring `orders.read`. The API must specify the exact authorities required.

**Important:** `AuthorizationFilter` checks permissions at the request/endpoint level. When an endpoint returns a specific order, the business layer still needs to check ownership, tenant, or access-control lists (ACL). Scopes are only one part of the authorization decision.

## 7. One Request: Four Typical Scenarios

### 7.1. No Bearer Token

Request:

~~~http
GET /api/orders HTTP/1.1
~~~

Typical flow:

1. `BearerTokenResolver` finds no token.
2. `BearerTokenAuthenticationFilter` lets the request continue without creating an authenticated principal.
3. `AnonymousAuthenticationFilter` may set an anonymous authentication.
4. `AuthorizationFilter` sees that the endpoint requires `SCOPE_orders.read`, while the request lacks suitable authentication.
5. Error handling runs, typically returning **401 Unauthorized** via the Bearer entry point.

If the endpoint is `permitAll` and has no other requirements, the request can still reach the controller without a token.

### 7.2. Token Present but Invalid

~~~http
Authorization: Bearer invalid.jwt.value
~~~

The filter extracts the token string and calls `AuthenticationManager`. `JwtDecoder` fails to verify the token, resulting in an authentication error. `BearerTokenAuthenticationFilter` handles the error using the appropriate failure handler/entry point; typically the client receives:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Details in the header may vary depending on the situation and configuration. Never include real tokens or sensitive claims in error messages.

### 7.3. Valid Token but Insufficient Permissions

Suppose the token is successfully authenticated, but only has `scope = profile`:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITHOUT_ORDERS_READ>
~~~

`BearerTokenAuthenticationFilter` creates the authentication successfully. Afterward, `AuthorizationFilter` denies access for `SCOPE_orders.read`; typically the client receives **403 Forbidden**.

If the appropriate Bearer access denied handler is used, the response may indicate `insufficient_scope`. Do not jump to interpreting 403 as a "broken JWT": the token can be completely valid yet lack the required permission.

### 7.4. Valid Token and Sufficient Scope

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITH_ORDERS_READ>
~~~

If the signature, issuer, audience, expiration, and validators all pass, the authentication has `SCOPE_orders.read`, and `AuthorizationFilter` allows the request to proceed. The controller can still deny access if the user accesses an order outside their tenant.

| Scenario | Bearer filter | Authorization | Typical outcome |
|---|---|---|---|
| No token | Does not create an authenticated Bearer principal | Insufficient permissions | 401 |
| Invalid or expired token | Authentication fails | Usually does not reach authorization | 401 |
| Valid token, missing scope | Authentication succeeds | Denied | 403 |
| Valid token, sufficient scope | Authentication succeeds | Allowed | Controller handles; may be 200 |
| No token, `permitAll` endpoint | Does not create a Bearer principal | Allowed | Controller handles |
| Invalid token, `permitAll` endpoint with Bearer filter | May authenticate and fail | May not reach authorization | Usually 401 |

The last row highlights an important detail: **`permitAll` does not mean `BearerTokenAuthenticationFilter` is skipped**. The filter may see the invalid token and return an error before authorization allows the public endpoint.

## 8. Multiple `SecurityFilterChain`s: Select the Chain First, Then Evaluate Permissions

An application may have APIs authenticated with Bearer JWTs alongside other endpoints that do not use Bearer tokens.

### 8.1. Example of Two Chains with `@Order`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().denyAll()
            );

        return http.build();
    }
}
~~~

**Explanation:**

- A `GET /api/orders` request matches `/api/**` → the first chain is selected → the Bearer token is processed.
- A `GET /actuator/health` request does not match the API chain → enters the second chain → the endpoint is allowed.
- A `GET /admin` request does not match the API chain → enters the second chain → `denyAll`.
- The second chain does not enable Resource Server JWT, so it **does not have the Bearer token processing from the first chain's `oauth2ResourceServer().jwt()` configuration**.
- `@Order(1)` and `@Order(2)` control **chain selection order**, not the execution order of individual filters inside a chain.

Configuring a fallback chain reduces the risk of forgetting to protect paths that do not match a specific chain. If a request **does not match any `SecurityFilterChain`**, the protections provided by Spring Security filter chains do not apply to that request.

### 8.2. How Does `securityMatcher` Differ from `requestMatchers`?

Consider this configuration:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

- `securityMatcher("/api/**")`: **For which requests does `FilterChainProxy` select this chain?**
- `requestMatchers("/api/public/**").permitAll()`: **once the chain is selected, which endpoints are permitted without authorization?**
- `requestMatchers("/api/admin/**")`: **authorization rule applied to specific endpoints within the chain.**

Because `/api/public/**` still falls under the API chain, **`BearerTokenAuthenticationFilter` can still run**. If a client sends a malformed Bearer token to the public endpoint, it may be rejected even though the endpoint's authorization policy is `permitAll`.

Conversely, if `securityMatcher` is too narrow and excludes an endpoint that needs protection, Spring Security cannot fix that by adding `requestMatchers` to the same chain: the request never selects that chain in the first place.

### 8.3. First-Match-Wins and Overlapping Matchers

Example of a misconfigured intention:

~~~java
// Higher-priority chain
http.securityMatcher("/**");

// Lower-priority chain
http.securityMatcher("/api/**");
~~~

If both exist, the higher-priority `/**` chain will catch every request, preventing the `/api/**` chain behind it from ever being selected. As a result, the API may never run the Bearer token filter if the catch-all chain does not enable Resource Server.

When using multiple chains:

1. Place specific matchers before general matchers.
2. Specify `@Order` explicitly.
3. Ensure no important endpoint falls outside protection scope.
4. Avoid two chains with unintended overlapping matchers.
5. Distinguish endpoint rules from chain selection rules when diagnosing 401/403 responses.

## 9. Which Chain Handles Bearer Tokens When the Same App Also Has OIDC Login?

A single application can simultaneously be:

- An **OAuth 2.0/OIDC Client** using `oauth2Login()` to log users in via a browser, typically with sessions.
- A **Resource Server** using `oauth2ResourceServer()` to accept access tokens from API clients.

These two roles are distinct.

| Component | Purpose |
|---|---|
| `oauth2Login()` | Redirects users to the Identity Provider, handles callbacks/authorization codes, and creates a login session on the client |
| `oauth2Client()` | Manages `OAuth2AuthorizedClient` and access tokens so the application can call other APIs |
| `oauth2ResourceServer().jwt()` | Accepts Bearer access tokens and verifies JWTs |
| `oauth2ResourceServer().opaqueToken()` | Accepts Bearer opaque access tokens and verifies them via introspection |

When combining them, design separate, appropriate filter chains for API and web traffic. If an API request accidentally enters the form/OIDC login chain, the client may receive a `302` redirect to a login page instead of the expected Bearer `401`. If a web page accidentally enters the stateless API chain, cookie-based login sessions may fail to work as intended.

**An OIDC ID Token is not a Resource Server Bearer access token.** An API must validate access tokens issued for its own audience; do not accept an ID Token just because both share a JWT header/payload/signature structure.

## 10. Customizing Where Bearer Tokens Are Extracted in the Chain

If the contract between a client/gateway and the API requires:

~~~http
X-Access-Token: Bearer <ACCESS_TOKEN>
~~~

you can configure a resolver in the Resource Server chain:

~~~java
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName("X-Access-Token");

http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults())
);
~~~

`BearerTokenAuthenticationFilter` will then use the configured resolver to look for the token in `X-Access-Token`.

**`setBearerTokenHeaderName` only changes the header name**; the value must still carry the `Bearer ` scheme. A raw JWT string in a custom header is a different contract and requires a custom resolver if truly needed.

Do not create a custom filter just to read a header and parse JWTs in a controller merely because the header name changed. Configuring `BearerTokenResolver` preserves Spring Security's authentication, error handling, and authorization pipeline.

If the backend sits behind a gateway, agree on which headers the gateway forwards; the gateway must not allow clients to spoof headers reserved for internal network use. Renaming a header does not provide security on its own.

## 11. CORS, CSRF, and Filter Order for APIs

### 11.1. CORS Preflight

For a frontend running on a different origin, the browser may send a **CORS preflight** before a request containing an `Authorization` header:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight requests usually **have no Bearer token**. Therefore, the application must configure CORS properly so preflight requests are handled before the authentication layer that requires a token. Spring Security supports CORS integration via:

~~~java
http.cors(Customizer.withDefaults());
~~~

Provide an appropriate CORS configuration (such as a `CorsConfigurationSource`) specifying allowed origins, methods, and headers. Allowing `Authorization` in CORS **does not authenticate the Bearer token**; the actual request must still go through Resource Server authentication and authorization.

Do not disable all security just to make preflight requests work. Handle CORS using the proper mechanism integrated with the Servlet filter chain.

### 11.2. CSRF and Stateless Bearer

Pure Bearer token APIs where clients explicitly set the `Authorization` header generally do not rely on browser cookies to automatically attach credentials. In such cases, disabling CSRF for **that API chain** can be appropriate.

However, if the same app also uses form login/cookie sessions, **do not disable CSRF globally** without evaluating each chain. Use `securityMatcher` to scope CSRF policies to specific endpoint groups.

### 11.3. Security Headers and Request Cache

A Resource Server can still receive security response headers from the relevant filters. `RequestCacheAwareFilter` or other supporting filters may appear in the chain depending on configuration. For stateless APIs, avoid letting the system perform form-login redirects or store requests in a session by accidentally mixing web and API configurations.

## 12. Which Filter Handles 401/403 Errors?

Two components are important to understand:

- **`BearerTokenAuthenticationFilter`** handles errors directly during Bearer token authentication. When a token is supplied but invalid, the failure handler/entry point can return **401**.
- **`ExceptionTranslationFilter`** sits in the chain to translate authentication/authorization exceptions thrown by filters **after it** (typically including decisions at `AuthorizationFilter`) into responses using the appropriate entry point or access denied handler.

Therefore, do not claim that every Bearer 401 is caught by `ExceptionTranslationFilter`. Some authentication failures are handled directly inside `BearerTokenAuthenticationFilter`.

Typically:

| Issue | Detection stage | Typical HTTP status |
|---|---|---|
| Malformed Bearer header | Resolver/Bearer filter | 401 or corresponding Bearer error response |
| Invalid JWT signature | JwtDecoder inside AuthenticationProvider | 401 |
| Expired token, wrong issuer/audience | JwtDecoder/validator | 401 |
| Missing token on required endpoint | Authorization, anonymous/entry point | 401 |
| Valid token but missing scope | AuthorizationFilter/AccessDeniedHandler | 403 |
| Valid token, policy allows | AuthorizationFilter | Handled by controller |
| Controller denies data ownership | Business layer | 403 or 404 depending on API policy |

Responses following RFC 6750 may include the header:

~~~http
WWW-Authenticate: Bearer
~~~

or for an invalid token:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

For a valid token lacking required permissions, the header may include `insufficient_scope` depending on the handler. Response details depend on Resource Server configuration.

## 13. Why Should You Not Register the Bearer Filter Manually?

When you write:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

Spring Security automatically adds the corresponding components to the security chain, including token extraction and JWT validation.

A trouble-prone configuration is manually creating `BearerTokenAuthenticationFilter` as a standalone Servlet Filter while also enabling `oauth2ResourceServer`. When that happens, you may run into:

- The filter running outside `FilterChainProxy` or running twice.
- Incorrect ordering relative to `SecurityContextHolderFilter`/`AuthorizationFilter`.
- Creating a different `AuthenticationManager`/decoder than the Resource Server chain.
- Inconsistent 401/403 error handling.
- Two overlapping token-processing mechanisms on the same request.

Only use `addFilterBefore`/`addFilterAfter` for **purpose-built custom filters** with a clearly defined anchor filter, threat model, and interaction with the authentication context. Do not add a custom filter just to change the Bearer header name or validate a claim that `JwtDecoder`/`OAuth2TokenValidator` can already handle.

Similarly, `@Order` on a `SecurityFilterChain` **does not adjust the position of `BearerTokenAuthenticationFilter` within a chain**. Individual filter ordering is handled by the security configurers and Spring Security's filter ordering mechanism.

## 14. When Using Opaque Access Tokens, Does the Bearer Filter Position Change?

At the HTTP position level, **no**: the Resource Server still needs to extract the Bearer token from the request. The difference lies in the validation step.

Configuration:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Example `application.yml` with an Authorization Server exposing an introspection endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: example-from-secret-store
~~~

These values are illustrative placeholders. Real secrets must come from environment variables or a secret manager, never committed to a repository. The introspection endpoint and client credentials depend on the provider.

Flow:

~~~text
BearerTokenAuthenticationFilter
    |
    v
BearerTokenAuthenticationToken
    |
    v
OpaqueTokenAuthenticationProvider
    |
    v
OpaqueTokenIntrospector -> Authorization Server
    |
    v
BearerTokenAuthentication
    |
    v
AuthorizationFilter
~~~

A JWT decoder can validate tokens using public keys locally at the API; introspection typically requires calling the Authorization Server according to caching and network policies. Neither approach changes the responsibility of selecting the `SecurityFilterChain` and enforcing authorization after authentication.

## 15. Diagnosing Real-World Issues

### 15.1. Token Present, Yet API Returns 401

Check causes stage by stage:

1. Did the request enter a **chain with Resource Server enabled**? Check `securityMatcher` and `@Order`.
2. Is the Bearer filter reading the expected `Authorization` header or configured custom header?
3. Does the header follow the `Bearer <token>` format?
4. Is the decoder using the right issuer, JWKS, JWT algorithm, or introspection endpoint?
5. Is the access token still valid (not expired) and matching the required audience and profile?

Never fix a 401 by adding `permitAll` to a protected endpoint: if token authentication fails, lowering endpoint access restrictions only hides the problem.

### 15.2. API Returns a 302 Redirect to Login

This commonly happens when an API request enters a filter chain intended for browser login, or when the authentication entry point differs from a Bearer Resource Server. Check the selected chain, matchers, and authentication mechanisms in the chain.

APIs using Bearer access tokens should generally return appropriate 401/403 responses for clients to handle, rather than redirecting to a web login page.

### 15.3. Valid Token Present, Yet Returns 403

The token may have authenticated successfully, but lacks the required authority. Check:

- The scopes in the token and their mapping to `SCOPE_...`.
- Which `requestMatchers` rule is matching.
- Whether other role-based policies apply.
- Whether tenant or ownership restrictions exist at the business layer.

A `403` does not mean the Bearer filter failed to run; it usually indicates authentication succeeded but permissions are insufficient.

### 15.4. `permitAll` Endpoint Still Returns 401 When Sent an Invalid Token

Because `permitAll` is only an **authorization policy**, the Resource Server filter still processes Bearer tokens if the request falls within that chain. When a client sends an invalid token, an authentication failure can occur **before** authorization.

If you truly want an endpoint to have no Bearer processing at all, design chain boundaries with clear paths and policies rather than expecting `permitAll` to bypass the filter automatically.

### 15.5. One Chain "Swallows" Requests Meant for Another Chain

If the first chain has `securityMatcher("/**")`, every request can match that chain immediately. `FilterChainProxy` will not evaluate subsequent chains once the first chain matches.

Check specific matchers, `@Order` precedence, and ensure there is a fallback chain protecting remaining routes.

### 15.6. Controller Does Not See the Expected Authentication

The request might not have gone through the right chain, the Bearer token might not have been sent, or authentication might have failed before reaching the controller. For JWTs and opaque tokens, the principal types differ; do not cast every principal to `Jwt`.

Do not store `SecurityContextHolder.getContext()` in a variable shared across multiple requests or threads. Read it within the current request or use injection.

## 16. Observing the Filter Chain During Development

### 16.1. Controlled Security Logging

In local/dev environments, you can enable:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Depending on the version, logs can display the chain protecting the request and the configured list of filters. `TRACE` provides even more detail, though at higher log volume.

**Do not leave verbose security logging enabled in production** without evaluating information disclosure risks. Avoid logging raw access tokens, `Authorization` headers, cookies, private keys, or sensitive data in logs and telemetry.

### 16.2. Distinguishing Authorization Tests from Full Bearer Flow Tests

In Spring Security Test, a MockMvc request using `jwt()`:

~~~java
mockMvc.perform(
    get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        ))
);
~~~

This is a convenient technique to **mock authentication** when testing endpoint rules. It **does not necessarily test extracting the Bearer string from the HTTP header, verifying the signature, or running `JwtDecoder` validators**.

To test the entire Bearer pipeline, write an integration test with actual security filters enabled, properly signed test access tokens, a controlled JWKS/decoder source, and negative cases for bad signatures/issuer/audience/scope. Similarly, if customizing the header name, write a dedicated test verifying the resolver extracts the token from the right header.

### 16.3. Suggested Request Matrix

| Request | Expected chain | Expected outcome |
|---|---|---|
| `GET /api/orders` no token | API chain | 401 |
| `GET /api/orders` invalid token | API chain | 401 |
| `GET /api/orders` valid token missing scope | API chain | 403 |
| `GET /api/orders` valid token sufficient scope | API chain | Handled by controller |
| `GET /actuator/health` no token | Fallback chain in the two-chain example | Allowed |
| `GET /admin` | Fallback chain | Denied |
| `GET /api/public/ping` invalid token, `permitAll` endpoint in API chain | API chain | May be 401 due to Bearer authentication failure |

The goal of the matrix is to separate **chain selection errors**, **token validation errors**, and **authorization errors**.

## 17. Reasoning Checklist for a New Endpoint

When adding `GET /api/reports` to a Resource Server application, answer these in order:

1. **Which `SecurityFilterChain` does the endpoint belong to?** For example, `/api/**`.
2. **Does the chain enable Bearer Resource Server?** For example, `oauth2ResourceServer().jwt()`.
3. **Where does the Bearer token come from?** Default `Authorization` header or a custom header per contract.
4. **How is the token validated?** `JwtDecoder` or opaque introspection, and which issuer/key/alg/audience.
5. **Which authority represents access permission?** For example, `SCOPE_reports.read`.
6. **Which records can the caller view?** Check tenant/owner and application policies.
7. **On failure, what should the client see?** Missing or invalid token: 401; authenticated but insufficient permissions: 403 (or 404 depending on object policy).

Following this order helps avoid putting JWT parsing logic in controllers, duplicating filters, misconfiguring matchers, or confusing API permissions with OIDC login.

## 18. Key Takeaways

- **`DelegatingFilterProxy`** connects the Servlet container to Spring Security; **`FilterChainProxy`** selects a **`SecurityFilterChain`** per request.
- **The first matching chain** is used; `@Order` orders priority across chains.
- **`securityMatcher`** defines the scope of a chain, whereas **`requestMatchers`** inside `authorizeHttpRequests` defines permissions within that chain.
- **`oauth2ResourceServer(...jwt(...))`** adds JWT Bearer handling; **`BearerTokenAuthenticationFilter`** extracts the token, creates an authentication request, and invokes authentication.
- After successful authentication, **`Authentication`** is available in **`SecurityContext`** for **`AuthorizationFilter`** and application code.
- **`permitAll` does not automatically bypass the Bearer filter**; an invalid token on a public endpoint in the same chain can still be rejected.
- **401** usually indicates missing or invalid authentication; **403** usually indicates valid authentication with insufficient permissions.
- Do not create a Bearer filter manually just to configure a JWT Resource Server, change the header name, or validate claims; use Spring Security's official extension points.

### References

- [Spring Security Reference — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — BearerTokenAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html)
- [Spring Security API — FilterChainProxy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
