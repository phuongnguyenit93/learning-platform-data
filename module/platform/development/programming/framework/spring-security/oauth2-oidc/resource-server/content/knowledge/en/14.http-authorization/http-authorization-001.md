# authorizeHttpRequests and Policies for Each Endpoint Group

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, a valid Access Token **does not mean permission to call every API**. After Spring Security authenticates the Bearer token and builds the `Authentication`, the application needs to decide **which HTTP requests are allowed**, based on path, HTTP method, authentication state, scope/authority, and system-specific rules.

With **Spring Security 6.x**, the `HttpSecurity.authorizeHttpRequests(...)` API is the standard way to declare those rules. The goal of this lesson is to design clear policies for **each endpoint group** — public, authenticated, read-only, write, administrative, and undeclared endpoints — rather than writing a single blanket rule like "having a token passes everything."

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC/Servlet**, assuming the application is a **Resource Server receiving OAuth 2.0 JWT Bearer Access Tokens**. The code snippets illustrate an order management API; issuer names, audiences, domains, and scopes should be replaced with your real system contract. Configurations for opaque tokens, OIDC Login, and multiple filter chains are also distinguished where relevant to endpoint policies.

## 1. HTTP Authentication and HTTP Authorization Are Two Different Steps

The client sends:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
~~~

The Resource Server processes it according to this model:

~~~text
HTTP request
     |
     v
Spring Security Filter Chain
     |
     v
BearerTokenAuthenticationFilter
     |
     v
JwtDecoder / AuthenticationProvider
     |-- is the JWT signature valid?
     |-- is the issuer trusted?
     |-- is the audience intended for orders-api?
     |-- are the expiration/token profile valid?
     v
Authenticated Authentication
     |-- principal: Jwt
     |-- authorities: e.g. SCOPE_orders.read
     v
AuthorizationFilter
     |-- what is the request method/path?
     |-- what is the first matching rule?
     |-- does the principal have the required authority?
     v
Endpoint allowed / request blocked
     |
     v
Business authorization
     |-- does the user have permission on this orderId/tenant?
     v
Response
~~~

These decisions answer different questions:

| Question | Primary mechanism | On failure |
| --- | --- | --- |
| Does the request have a Bearer token? | Bearer authentication | Usually **401 Unauthorized**. |
| Are the token's signature, issuer, audience, and expiration valid? | JwtDecoder and validators | Usually **401 Unauthorized**. |
| Is a valid token allowed to GET or POST this endpoint? | `authorizeHttpRequests`, authorities | Usually **403 Forbidden** if authenticated but lacking permissions. |
| Does the caller have permission on this specific order? | Domain service, method/resource authorization | Usually **403** or **404** depending on the resource-hiding policy. |

**An Access Token with a valid signature that lacks a scope does not mean the token is forged.** It can authenticate successfully and then be rejected at the authorization step. Conversely, a token with an invalid signature must not "proceed to scope evaluation."

## 2. Core Concepts of authorizeHttpRequests

A simple configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/private/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Meaning:

- **`authorizeHttpRequests`**: defines HTTP authorization decisions using the `AuthorizationManager` mechanism in modern Spring Security.
- **`requestMatchers(...)`**: selects HTTP requests matching by path, method, or a custom matcher.
- **`permitAll()`**: allows matching requests without requiring an authenticated principal.
- **`authenticated()`**: requires the request to be authenticated; does not itself require a specific scope.
- **`denyAll()`**: denies matching requests regardless of what authorities the principal holds.
- **`anyRequest()`**: a catch-all rule for requests **not matched by any preceding rule**.

Important: rules are **not independent** and **do not accumulate** as "if multiple rules match, take the strictest rule." Spring Security evaluates matchers in **the order declared**; **the first rule that matches the request** is used to decide whether to allow or deny it.

### 2.1. Rule Ordering Determines the Effective Policy

An unsafe example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin.manage")
    .anyRequest().denyAll()
);
~~~

For `GET /api/admin/users`, the **`/api/**`** rule matches first and allows everyone; the admin rule after it **never gets a chance to run**.

Specific rules must be placed before general rules:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**")
        .hasAuthority("SCOPE_admin.manage")
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

The second snippet has better **ordering**, yet it still only requires `authenticated` for the rest of `/api/**`; it does not yet define separate scope policies for GET/POST orders. For business APIs, you should write granular rules by method and endpoint group, avoiding treating "can log in" as "can modify data."

### 2.2. Common Authorization Expressions

| DSL | Decision | Example usage |
| --- | --- | --- |
| `permitAll()` | Does not require authentication to pass the HTTP rule. | Public catalog, non-sensitive status endpoints. |
| `denyAll()` | Does not allow matching requests. | Paths not yet designed or exposed. |
| `authenticated()` | Requires a valid Authentication. | `GET /api/me` if every user with a token may view their own profile. |
| `hasAuthority("SCOPE_orders.read")` | Must have the exact specified authority. | Reading orders via GET. |
| `hasAnyAuthority("SCOPE_orders.read", "SCOPE_orders.audit")` | Requires at least one authority in the set. | Reading orders or audit reports when policy allows. |
| `hasRole("ADMIN")` | By default requires `ROLE_ADMIN`. | Applications that map internal roles to `ROLE_...` authorities. |
| `hasAnyRole("ADMIN", "SUPPORT")` | Has one of the corresponding mapped roles. | Role-based administrative pages. |
| `access(customAuthorizationManager)` | Invokes a custom decision based on the request and Authentication. | Shared rules needing additional context data when truly appropriate at the HTTP layer. |

**`hasRole("ADMIN")` is not the same as `hasAuthority("SCOPE_admin.manage")`**. `hasRole` uses the default `ROLE_` prefix, whereas a Resource Server typically maps OAuth scopes to `SCOPE_`. Do not write `hasRole("ROLE_ADMIN")` as a substitute for `hasRole("ADMIN")` when using the default prefix configuration.

### 2.3. `authenticated()` Does Not Mean "Logged In via OIDC"

In a pure JWT Resource Server, a request is authenticated via a **Bearer Access Token**, without requiring a browser with an active OIDC Login session. An application can have both `oauth2Login()` and `oauth2ResourceServer()`, but the two mechanisms should not be mixed without explicitly designing clients, sessions, CSRF, and the associated filter chains.

An **OIDC web login** endpoint may accept session authentication; a **Bearer API** endpoint usually requires a token on each request. The `authenticated()` DSL only checks the Authentication state; it does not automatically coerce credentials into a Bearer JWT in every architecture.

## 3. Designing Policies by Endpoint Group

Suppose an order system has these groups:

| Group | HTTP method + path | Who can access | Recommended policy |
| --- | --- | --- | --- |
| **Public catalog** | `GET /api/public/catalog`, `GET /api/public/catalog/**` | Any client | `permitAll()` if the data is genuinely public. |
| **Caller's own profile** | `GET /api/me` | Authenticated principal | `authenticated()`; the service only returns the caller's profile. |
| **Read orders** | `GET /api/orders`, `GET /api/orders/**` | Token with read permission | `hasAuthority("SCOPE_orders.read")`. |
| **Create order** | `POST /api/orders` | Token with write permission | `hasAuthority("SCOPE_orders.write")`. |
| **Update or delete order** | `PUT/PATCH/DELETE /api/orders/**` | Token with write permission | `hasAuthority("SCOPE_orders.write")` plus data policy. |
| **Administration** | `/api/admin/**`, any method | Token with admin permission | `hasAuthority("SCOPE_admin.manage")`, plus business permission checks. |
| **Undefined endpoints** | All remaining requests | Nobody | `denyAll()` as fallback. |

This is an **example matrix**: a real product must align endpoint names, scopes, tenants, and roles. In particular:

- `permitAll()` does not automatically make content harmless; use it only for data permitted for public access.
- `authenticated()` on `/api/me` does not mean anyone can pass `?userId=...` to view someone else's profile; the controller/service must bind to the principal.
- Scope `orders.read` does not itself grant access to orders belonging to another tenant.
- The `admin.manage` permission may require additional **organization conditions, account status, strong authentication, or approval** for sensitive operations.
- Operational URLs such as Actuator, Swagger, metrics, or internal admin must have **their own policies**; do not lazily lump them into the public group just for testing convenience.

### 3.1. Be Careful with Path Prefixes

Organizations that look similar can lead to different policies:

~~~text
/api/public/catalog
/api/orders
/api/orders/42
/api/orders/42/items
/api/admin/users
/internal/admin/users
/actuator/health
~~~

A matcher `/api/admin/**` **does not** protect `/internal/admin/users` or `/actuator/**`. If those endpoints exist, you must define the corresponding chain/rules. With a `denyAll()` fallback, undeclared requests are blocked rather than served by default.

### 3.2. Explicitly Specify the HTTP Method for Each Group

On the same path, GET may be read-only while POST/DELETE mutates data:

~~~text
GET    /api/orders   -> SCOPE_orders.read
POST   /api/orders   -> SCOPE_orders.write
GET    /api/orders/7 -> SCOPE_orders.read
DELETE /api/orders/7 -> SCOPE_orders.write
~~~

If you only use:

~~~java
.requestMatchers("/api/orders/**").authenticated()
~~~

then all methods may be allowed for any valid Authentication. To prevent a caller with a read-only token from modifying data, you must use **method-specific matchers** and the corresponding scopes.

Undefined HTTP methods such as `TRACE`, `OPTIONS`, or extension methods must not automatically inherit GET/POST permissions; handle them according to actual requirements, CORS, and the deny fallback, and write tests for those cases.

## 4. Complete Spring Boot JWT Resource Server Example

### 4.1. Dependencies

In a Gradle project (Groovy DSL), with Spring Boot managing versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-oauth2-resource-server` provides Bearer Token support and JWT/JOSE-related modules according to the dependency tree of common Boot versions. `spring-security-test` helps mock a JWT principal when testing HTTP authorization with MockMvc.

### 4.2. Configuring Issuer and Audience

Example `src/main/resources/application.yml`:

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

- `issuer-uri` specifies the issuer trusted by the API, used for key-source discovery and validating the `iss` claim via appropriate auto-configuration.
- `audiences` requires the Access Token to be issued for **orders-api** on Spring Boot versions supporting that property. If your version does not support it, add a `JwtDecoder` with an audience validator.
- Beyond signature/issuer/audience, validate expiration and token profile according to system requirements.

**Do not confuse issuer/audience validation with `authorizeHttpRequests`.** Signature, issuer, and audience are handled at the token authentication layer, whereas HTTP rules govern allowed scopes/authorities and endpoints.

### 4.3. SecurityFilterChain with Endpoint Groups

A `SecurityFilterChain` bean for the sample API:

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
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 1. Genuinely public catalog: GET only.
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/public/catalog",
                    "/api/public/catalog/**")
                    .permitAll()

                // 2. Administrative API: checked before broader rules.
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin.manage")

                // 3. Read orders.
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                // 4. Create orders.
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                // 5. Update and delete orders.
                .requestMatchers(
                    HttpMethod.PUT,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(
                    HttpMethod.PATCH,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(
                    HttpMethod.DELETE,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                // 6. Authenticated principal's own profile.
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                // 7. All remaining requests are not open by default.
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

The example does not declare `securityMatcher(...)` at the chain level, so this filter chain can serve as the **primary fallback** of a simple application with a single chain. Each request is evaluated in order:

1. **GET catalog** is allowed without a token, because that group is genuinely public.
2. **`/api/admin/**`** requires `SCOPE_admin.manage` for any method; order rules do not dilute admin permissions.
3. **GET orders** requires `SCOPE_orders.read`.
4. **POST/PUT/PATCH/DELETE orders** require `SCOPE_orders.write`.
5. **GET /api/me** requires Authentication without adding an extra scope in this example policy.
6. Unmatched requests hit `denyAll()`.

`SessionCreationPolicy.STATELESS` indicates that the Bearer API does not rely on an HTTP session to retain Authentication. Disabling CSRF in this example **is only appropriate for APIs authenticating via an Authorization header, not using cookies/sessions as credentials**. If the same application has a web login using cookies, a separate CSRF policy is required (section 10).

**Warning about public GETs:** even though `GET /api/public/catalog` is `permitAll`, if a request carries an invalid Bearer token, authentication components may still attempt to process that credential and reject it. `permitAll()` does not mean Bearer authentication will always ignore an invalid `Authorization` header.

### 4.4. Illustrative Controller to Visualize Behavior

Simple handlers:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoApiController {

    @GetMapping("/api/public/catalog")
    Map<String, Object> catalog() {
        return Map.of("items", List.of("standard"));
    }

    @GetMapping("/api/orders")
    Map<String, Object> orders() {
        return Map.of("orders", List.of());
    }

    @PostMapping("/api/orders")
    ResponseEntity<Map<String, String>> createOrder() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("result", "created"));
    }

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }

    @PostMapping("/api/admin/rebuild")
    Map<String, String> adminOperation() {
        return Map.of("result", "accepted");
    }
}
~~~

This controller is for **training purposes** and performs no real business logic. If implementing `GET /api/orders/{id}`, `PUT /api/orders/{id}`, or real admin functionality, the controller must have the corresponding handlers and the service must continue checking permissions on the data.

### 4.5. Matching Both Base Paths and Sub-Paths

When you want to protect both `/api/orders` and `/api/orders/42`, the example uses both:

~~~java
.requestMatchers(
    HttpMethod.GET,
    "/api/orders",
    "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Do not assume every matcher syntax handles slashes, `**`, trailing slashes, path parameters, or URL encoding identically across versions. In Spring MVC, Spring Security can use matchers aligned with the application's MVC configuration. Test the actual URLs mapped by controllers, especially with nested paths and special methods.

## 5. How Are Scopes in an Access Token Mapped to Authorities?

A JWT Access Token issued by an Authorization Server may carry:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000
}
~~~

Spring Security Resource Server typically uses `JwtGrantedAuthoritiesConverter` to convert scopes from the `scope` or `scp` claim into authorities prefixed with **`SCOPE_`**:

~~~text
JWT claim scope = "orders.read orders.write"
                  |
                  v
GrantedAuthority("SCOPE_orders.read")
GrantedAuthority("SCOPE_orders.write")
~~~

Therefore, the DSL:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders")
    .hasAuthority("SCOPE_orders.read")
~~~

checks **that exact authority**; it does not directly match the string `"orders.read"` inside the JWT at the filter. If the issuer uses a custom role claim, a different `scope` format, or places permissions in `realm_access.roles`, the application must define a converter according to the **token contract**.

### 5.1. Roles and Scopes Are Not Automatically Equivalent

Suppose a JWT contains:

~~~json
{
  "roles": ["ADMIN"],
  "scope": "orders.read"
}
~~~

With the default scope-based converter, **`ROLE_ADMIN` is not automatically created** just because the token has a `roles` claim. In that case:

~~~java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

will not necessarily allow the token above, because `hasRole("ADMIN")` looks for the **`ROLE_ADMIN`** authority under the default prefix. There are two intentional design approaches:

- **Based on OAuth scopes:** the issuer grants `admin.manage`; the API requires `SCOPE_admin.manage`.
- **Based on domain roles:** a converter or domain service determines trusted internal roles and adds `ROLE_ADMIN` per policy; the API requires `hasRole("ADMIN")`.

Do not automatically map arbitrary `"ADMIN"` strings from unverified sources into administrative privileges. When multiple issuers exist, identically named roles may carry different meanings; audience and issuer must still be verified first.

### 5.2. Example Custom Converter for a Custom Permission Claim

If the Access Token uses a `permissions` claim as a **string array**, the API can define a converter that allows only approved values. For example:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class OrdersJwtAuthorities {

    private OrdersJwtAuthorities() {}

    public static JwtAuthenticationConverter converter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter result =
            new JwtAuthenticationConverter();

        result.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(scopes.convert(jwt));

            Object raw = jwt.getClaims().get("permissions");
            if (raw instanceof List<?> values) {
                for (Object value : values) {
                    if ("orders.audit".equals(value)) {
                        authorities.add(new SimpleGrantedAuthority(
                            "PERMISSION_orders.audit"));
                    }
                }
            }

            return authorities;
        });

        return result;
    }
}
~~~

Here the custom permission `orders.audit` is mapped to **`PERMISSION_orders.audit`**, kept separate from the scope prefix. The example only allows a known value rather than accepting arbitrary role/permission strings.

If using the converter:

~~~java
.oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
    jwt.jwtAuthenticationConverter(
        OrdersJwtAuthorities.converter())))
~~~

This **replaces** the `oauth2ResourceServer(...jwt(Customizer.withDefaults()))` configuration inside the `SecurityFilterChain`, rather than creating a second filter chain. With the custom configuration, you can use:

~~~java
.requestMatchers(HttpMethod.GET, "/api/audit/orders")
    .hasAuthority("PERMISSION_orders.audit")
~~~

Place this rule before the `denyAll()` fallback and avoid placing it after a broader rule that already matched first. In practice, verifying the `permissions` data type (array of strings), issuer/audience, and schema is the responsibility of the token contract/validators; the converter should not try to turn malformed data into elevated permissions.

## 6. Matcher Ordering: Thinking Correctly with "First Match Wins"

Suppose you have these rules:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.anyRequest().denyAll()
~~~

For `GET /api/orders/42`, the first rule requires `orders.read`; for `DELETE /api/orders/42`, the first rule does not match the method, so the second rule requires `orders.write`.

But if you reverse the order:

~~~java
.requestMatchers("/api/orders/**")
    .authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

then the DELETE rule **may never be evaluated**, because the first `/api/orders/**` matcher already matches every method. This is a serious authorization bug: any authenticated token can pass through the broad rule.

### 6.1. Always Check Whether an Earlier Rule Shadows Another

| Rule placed first | Rule placed later | Potential problem |
| --- | --- | --- |
| `/api/**` + `permitAll` | `/api/admin/**` + admin authority | Admin endpoints become publicly open. |
| `/api/orders/**` + `authenticated` | POST orders + write scope | Data writes may require authentication only. |
| GET `/api/orders/**` + read scope | GET `/api/orders/summary` + admin scope | Sensitive summary is exposed to any reader if matched first. |
| `anyRequest().authenticated()` | `/api/admin/**` + admin scope | The later admin rule will not be evaluated. |
| `/api/public/**` + `permitAll` | `/api/public/admin/**` + admin scope | An "admin" path under public may be left open. |

Endpoint groups should be designed so they **do not unintentionally overlap**. If there is a special endpoint inside a broad group, put the specific rule first. Use **`anyRequest().denyAll()` at the end** to block anything unclassified.

### 6.2. HTTP-Layer Rules Do Not Replace Method Security

If a business service handles multiple entry points — HTTP controllers, batch jobs, message listeners, or a new endpoint — a check at the HTTP path layer may be insufficient. Sensitive operations may require **method authorization** and business policies.

Example enabling method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Then services can use `@PreAuthorize` for appropriate permissions, though checking permissions on **each order/tenant** usually requires domain logic or queries bound to the owner/tenant. Do not treat URL patterns as a defense against **IDOR/BOLA**.

## 7. Choosing Multiple SecurityFilterChains: securityMatcher vs. requestMatchers

When an application has multiple endpoint types or multiple authentication mechanisms, it can be split into multiple `SecurityFilterChain` beans:

- A chain for **`/api/**`** using Bearer tokens, stateless.
- A chain for **web** using OIDC Login and sessions (if one actually exists).
- A chain for **management/status** with its own mechanism per infrastructure requirements.

Important distinction:

| Mechanism | Placed where? | Effect |
| --- | --- | --- |
| **`http.securityMatcher(...)`** | `SecurityFilterChain` level | Decides **whether this chain applies to the request**. |
| **`requestMatchers(...)`** inside `authorizeHttpRequests` | Rule level inside the selected chain | Decides **whether the request is permitted** once it enters the chain. |
| **`@Order` on a chain** | When multiple filter chains exist | The chain with the appropriate priority order is selected first. |
| **`anyRequest()`** | Inside a single chain | Only acts as a fallback for requests **that already entered that chain**. |

A request is typically handled by the **first SecurityFilterChain that matches the request**, rather than automatically running through all chains to accumulate protection.

### 7.1. Example with Two Chains: API and Fallback

This is an **alternative** to the single-chain configuration in section 4; do not use both sets of beans simultaneously:

~~~java
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
public class SplitSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin.manage")
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll());

        return http.build();
    }
}
~~~

The API chain only applies to `/api/**`. The fallback chain sets no `securityMatcher`, so it catches remaining requests and denies them. In this example, `/actuator/**`, `/internal/**`, and web routes are not granted access.

If you omit the fallback chain and no other chain matches a path, **that path may not be protected by Spring Security as the author expects**. Therefore, when using multiple chains, review the application's actual URL surface, including actuator, static resources, servlet paths, and framework-provided endpoints.

**Do not place `@Order(1)` on a catch-all chain** before the API chain, because the broad chain can capture all requests before the narrow chain is considered. The principle is **specific chains first, fallback last**.

### 7.2. When OIDC Login and Bearer API Coexist on the Same Backend

A web app may use `oauth2Login()` to create browser sessions while also using `oauth2ResourceServer().jwt()` to protect APIs. This model requires two distinct strategies:

- Web paths use **session cookies**, login redirects, and browser-oriented CSRF.
- API paths use **Bearer Access Tokens**, returning 401/403 status codes instead of automatically redirecting every API request to a login form.

When splitting chains, align how **sessions**, **CSRF**, **CORS**, entry points, and cookies operate. Do not take `csrf.disable()` or `STATELESS` configured for an API and apply it to the entire website just because it is easy to write.

## 8. Endpoint Groups Commonly Managed Separately

### 8.1. Public Endpoints

A genuinely public endpoint can use:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/catalog")
    .permitAll()
~~~

However, **not every endpoint named "public" is safe to expose publicly**, nor should every endpoint that requires no token return personal data. Base the decision on the data, the operation's impact, and product requirements.

Avoid:

~~~java
.requestMatchers("/api/public/**").permitAll()
~~~

in case someone later adds an API like `POST /api/public/reset-user-role` or `/api/public/internal-report`. Matchers by specific method and URL help limit unintended exposure.

### 8.2. Health Checks and Actuator

If using Spring Boot Actuator, decide which endpoints serve load balancers/orchestrators and which carry sensitive operational information:

- **Liveness/readiness** may be exposed within a controlled internal network or protected at the infrastructure layer.
- **Metrics, env, heapdump, threaddump, loggers, mappings**, and other management endpoints must not be exposed to the Internet by default.
- With a management server running on a separate port/context, define the corresponding **chain, network policy, and exposure configuration**.
- If you want a public `/healthz` endpoint, permit only that path; do not open all of `/actuator/**` with `permitAll()`.

Do not assume `authorizeHttpRequests` alone controls whether Actuator endpoints are exposed or hidden. Actuator also has **endpoint exposure**, network accessibility, and security configurations; these layers must be operated together.

### 8.3. API Documentation, Swagger UI, and OAuth Callbacks

Swagger/OpenAPI endpoints are sometimes left open in development environments; production may require authentication or network restrictions. Do not copy a `permitAll("/swagger-ui/**", "/v3/api-docs/**")` rule into every environment without evaluating what data is exposed.

OIDC Login callbacks and the OAuth Authorization Code flow belong to the **OAuth 2.0 Client**, not a typical JWT Resource Server endpoint. Open callbacks only per Client/Relying Party configuration and verify `state`, PKCE, nonce, and the corresponding session, rather than replacing them with an overly broad `permitAll` rule on the API.

### 8.4. Administrative or Sensitive Data Endpoints

Routes such as:

~~~text
/api/admin/users
/api/admin/roles
/api/admin/tenants
/api/internal/export
/api/reports/audit
~~~

need to be grouped separately, have appropriate scopes/roles/permissions, and be checked in the domain layer. If the route `/api/internal/export` is not yet declared in the policy, a `denyAll()` fallback protects far better than an overly broad `/api/**.authenticated()` rule.

## 9. Path-Based Authorization Is Insufficient for Multi-Tenancy and Record-Level Permissions

Suppose the caller has a valid JWT:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-A"
}
~~~

The HTTP rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

only ensures the token has permission to **read orders in general**; it does not ensure permission to read `GET /api/orders/987` if order 987 belongs to **tenant-B**. A caller can change the ID in the URL; the path still matches the read rule, so the domain layer must enforce resource-level authorization.

### 9.1. Example Policy in the Service Layer

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrderAccessPolicy {

    public void requireSameTenant(Jwt jwt, Order order) {
        String tokenTenant = jwt.getClaimAsString("tenant_id");

        if (tokenTenant == null
                || !tokenTenant.equals(order.getTenantId())) {
            throw new AccessDeniedException(
                "Order access not permitted");
        }
    }
}
~~~

In this example, **Order** is an illustrative domain entity that must be defined in the application. The tenant condition above is only one of the checks: the service may also need user account status, membership, owner, delegated permissions, and other business rules. Do not rely solely on a `tenant_id` sent by the client in headers/queries.

### 9.2. Where Checks Should Live

| Check | Appropriate layer |
| --- | --- |
| JWT signature, issuer, audience, expiration | `JwtDecoder` + token validators. |
| Are GET/POST/DELETE allowed by scope? | `authorizeHttpRequests`. |
| Do `roles`/custom permissions match the contract and map properly? | JWT validators + converters/domain policy. |
| Is the internal user still `ACTIVE` and a member of the tenant? | Account/domain service. |
| Does the Order ID belong to the permitted user/tenant? | Resource authorization/service/query. |
| Access via jobs/message listeners bypassing HTTP? | Method/domain authorization with the appropriate context. |

**Defense in depth** principle: HTTP filter protection blocks early, but data policies must live where full information about **the record, tenant, and permission state** is available.

## 10. CORS Preflight, OPTIONS, and CSRF: Do Not Confuse with Authorization

### 10.1. CORS Is a Browser Policy, Not a Replacement for Bearer Authentication

When a browser frontend at `https://app.example.test` calls an API at `https://api.example.test` with `Authorization: Bearer ...`, the browser may send a **CORS preflight request**:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

A normal preflight **does not contain a Bearer Access Token**. If the Resource Server tries to require a JWT for the preflight before handling CORS, the browser will fail even though the actual GET would send a valid Bearer token.

The right approach is to configure **CORS processing before Spring Security authentication/authorization**, rather than blindly treating all `OPTIONS` requests as authenticated. Spring Security can integrate CORS with `http.cors(...)` when an appropriate `CorsConfigurationSource` is provided.

Example:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsPolicyConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.test"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

In the `SecurityFilterChain`, add:

~~~java
.cors(Customizer.withDefaults())
~~~

to the corresponding `HttpSecurity` configuration, for instance before declaring `authorizeHttpRequests`. The configured CORS policy allows only specified origins; do not open `*` when unnecessary. If the API relies on cookies and `allowCredentials=true`, there must be an explicit origin policy and proper CSRF; do not use wildcard origins with credentials in violation of CORS rules.

**CORS does not stop non-browser clients from calling the API.** It is a browser mechanism controlling cross-origin access. Actual permissions must still be verified via tokens and HTTP/domain authorization.

### 10.2. Is `OPTIONS /**.permitAll()` Needed?

You should not use **`OPTIONS /**` + `permitAll`** as a default fix for every CORS issue. With `CorsFilter` properly integrated, valid preflight requests are usually handled before the API protection rules.

If the application has an `OPTIONS` endpoint with real business semantics or custom preflight behavior, write a specific rule. An `OPTIONS /**.permitAll()` rule only grants permission at the Spring Authorization layer; it does not set the proper CORS response headers or replace CORS configuration.

### 10.3. CSRF Differs from CORS

For an API using **purely Bearer tokens in the `Authorization` header**, without session cookies as credentials, many applications choose:

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

For a website using **session cookies / OIDC Login** in the browser, requests can carry cookies automatically via the browser, so **CSRF protection** is usually still required. Do not copy a stateless Bearer API configuration to disable CSRF across the entire web app.

### 10.4. HEAD, Trailing Slashes, and Method Forwarding

Methods like `HEAD` and URLs with trailing slashes or encoded paths can interact with Spring MVC routing in non-intuitive ways. A `GET` matcher is not always sufficient to define the policy for `HEAD` in every stack/configuration. When an API exposes HEAD or path variants, define and test explicit policies.

If the application sits behind a reverse proxy or API gateway, forwarded-header and path-rewriting configurations must be consistent. Do not rely on client-spoofed paths in `X-Forwarded-Prefix` to make authorization decisions. Endpoints whose paths are rewritten by a proxy must be tested against the **actual path seen by Spring Security**.

## 11. Testing HTTP Authorization by Endpoint Group

These tests should verify the policy for **both allowed and blocked requests**, covering HTTP methods, scopes, and fallbacks.

### 11.1. Expected Behavior Matrix

| Request | JWT / authorities | Result |
| --- | --- | --- |
| `GET /api/public/catalog` | No token | **200** if the controller exists and works. |
| `GET /api/orders` | No token | **401**. |
| `GET /api/orders` | `SCOPE_orders.read` | **200**. |
| `GET /api/orders` | `SCOPE_orders.write` only | **403**. |
| `POST /api/orders` | `SCOPE_orders.read` only | **403**. |
| `POST /api/orders` | `SCOPE_orders.write` | **201** per the example controller. |
| `GET /api/me` | No token | **401**. |
| `GET /api/me` | Valid JWT without `orders.read` | **200** per the `authenticated()` rule. |
| `POST /api/admin/rebuild` | `SCOPE_orders.write`, no admin | **403**. |
| `POST /api/admin/rebuild` | `SCOPE_admin.manage` | **200** per the example controller. |
| `GET /api/unconfigured` | Valid JWT with all example scopes | **403** due to the `denyAll` fallback. |
| `POST /api/public/catalog` | Valid JWT but undeclared | **403** due to the `denyAll` fallback. |
| `GET /api/orders` | Bearer JWT with bad signature/audience | **401** if the request passes through a real decoder. |

**Note:** `denyAll()` for an anonymous request may result in a **401** response due to how the entry point handles unauthenticated requests; an authenticated principal usually receives **403**. Statuses 200/201 occur only when the corresponding controller is declared; authorization may allow the request yet still return 404/405 if no matching handler exists.

### 11.2. MockMvc and spring-security-test

`spring-security-test` provides the **`jwt()`** helper to simulate a JWT Authentication for a test request. For example:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Here an Authentication with the authority is created directly for the test; **no** Authorization Server or real signed JWT is needed. As a result, the test focuses on **`requestMatchers` ordering and authorization decisions**.

At the same time, `jwt()` **does not prove** that `JwtDecoder` verified signature, issuer, audience, or expiration. Nor does it test custom authorities converters if the test supplies authorities manually. Those parts require dedicated decoder/converter tests.

### 11.3. Full Test Example with SpringBootTest

The test below assumes the configuration in section 4 and the sample controller in section 4.4 are placed in a Spring Boot application. In a rule-testing environment, the test provides a dummy `JwtDecoder` that **rejects all string tokens**, while `with(jwt())` constructs Authentication to test authorization.

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

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(EndpointAuthorizationTest.TestJwtDecoderConfig.class)
class EndpointAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @TestConfiguration
    static class TestJwtDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException("Test decoder rejects raw tokens");
            };
        }
    }

    @Test
    void publicCatalogAllowsAnonymous() throws Exception {
        mockMvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items").isArray());
    }

    @Test
    void ordersRejectAnonymous() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBearerTokenIsRejected() throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeAllowsReading() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orders").isArray());
    }

    @Test
    void writeScopeAloneCannotRead() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readScopeCannotCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isCreated());
    }

    @Test
    void meRequiresOnlyAuthenticatedPrincipal() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(jwt()
                    .jwt(jwt -> jwt.subject("user-123"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_other"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("user-123"));
    }

    @Test
    void adminOperationRejectsNormalWriter() throws Exception {
        mockMvc.perform(post("/api/admin/rebuild")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminOperationRequiresAdminScope() throws Exception {
        mockMvc.perform(post("/api/admin/rebuild")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_admin.manage"))))
            .andExpect(status().isOk());
    }

    @Test
    void unknownEndpointIsDeniedEvenForAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/api/unconfigured")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_admin.manage"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicGetRuleDoesNotOpenPost() throws Exception {
        mockMvc.perform(post("/api/public/catalog")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }
}
~~~

**Test scope:** The dummy `JwtDecoder` bean applies only in the authorization test environment. The request with `Authorization: Bearer invalid` is simulated to verify 401 behavior when the decoder rejects; it **does not** test real JWT cryptography. If the application already defines a separate production decoder bean, adjust the test configuration to be compatible instead of declaring two beans of the same type and causing a conflict.

Requests using `with(jwt())` bypass the decoder, so those tests prove only the **HTTP rules**. End-to-end signed JWT tests and mapping `scope` claims to authorities must be built at another layer.

### 11.4. Dedicated Tests for Rule Ordering and Easily Confused Paths

Beyond happy paths, include targeted tests for:

~~~text
GET    /api/admin/users       -> admin only
POST   /api/admin/users       -> admin only
GET    /api/orders            -> read scope
GET    /api/orders/42         -> read scope + data permission
POST   /api/orders            -> write scope
DELETE /api/orders/42         -> write scope + data permission
GET    /api/public/catalog    -> public
POST   /api/public/catalog    -> not public
GET    /api/unknown           -> deny fallback
GET    /internal/admin        -> deny fallback or separate chain
~~~

Especially when adding a new endpoint, test that **a specific rule is not shadowed by a preceding broad rule**. With multiple filter chains, test which chain is selected for each URL, including paths that do not start with `/api/`.

## 12. Testing Real JWTs and Security Boundaries Outside HTTP Rules

To conclude that a Resource Server protects the API safely, do not test only `authorizeHttpRequests` with mocked JWTs. Separate tests are needed:

| Layer | Example test |
| --- | --- |
| **JWT signature validation** | A JWT signed with an unknown key or with an invalid signature must be rejected. |
| **Issuer** | A properly signed JWT with an `iss` other than the trusted issuer must be rejected. |
| **Audience** | A valid JWT whose `aud` targets a different API must be rejected. |
| **Expiration** | An expired `exp` or not-yet-valid `nbf` must be rejected per the clock skew policy. |
| **JWT authorities mapping** | Real `scope` or `scp` claims are converted into the right authorities without granting roles outside the contract. |
| **HTTP rules** | Read scope cannot write; admin paths are not exposed; undeclared endpoints are blocked. |
| **Domain authorization** | A user from another tenant or another owner cannot view/edit an order even with the scope. |
| **CORS/CSRF** | Browser preflight works for allowed origins, unlisted origins are not accepted by CORS; CSRF works properly for cookie flows if present. |
| **Multi-chain coverage** | Every endpoint is protected by the right chain, with no routes slipping outside the configuration. |

To test `JwtDecoder`, you can use a test-only RSA key pair and sign JWTs with the private key fixture; the decoder verifies with the public key fixture while running issuer/audience/time validators. If JWKS fetching needs testing, spin up a local JWKS endpoint. Then integration tests send real signed JWTs in the `Authorization: Bearer` header through the filter chain to observe 401/403 responses.

Never use production private keys or real user Access Tokens in automated tests; test tokens should have synthetic identifiers and test-only scopes.

## 13. What If the Resource Server Uses Opaque Tokens Instead of JWTs?

If the Authorization Server issues **opaque Access Tokens** instead of JWTs, the Resource Server can be configured with:

~~~java
.oauth2ResourceServer(oauth ->
    oauth.opaqueToken(Customizer.withDefaults()))
~~~

In an opaque-token configuration, Authentication/authorities are built from **introspection** results per the contract. `authorizeHttpRequests` rules such as `hasAuthority("SCOPE_orders.read")` can still be used if `OpaqueTokenIntrospector` maps scopes into the corresponding authorities.

Only the **token verification step** differs, not the principles of grouping endpoints. Authorization tests can use the `spring-security-test` `opaqueToken()` helper; testing real introspection requires a separate introspector/endpoint fixture.

Do not enable both JWT and opaque token mechanisms simultaneously and assume the framework will flawlessly distinguish every token without an explicit policy design. The verification mechanism must match the token format and the Authorization Server's configuration.

## 14. The Deny-by-Default Rule and Limits to Understand Correctly

### 14.1. Why `anyRequest().denyAll()` Should Be Present

When API groups expand over time, the final rule:

~~~java
.anyRequest().denyAll()
~~~

ensures that a new endpoint **is not granted access simply because a developer added a controller and forgot to update the security policy**. It is a conservative choice that reduces the chance of accidentally exposing data.

However, `denyAll()` **does not automatically protect requests outside the filter chain** in a multi-chain setup. An appropriate fallback chain is required. Nor does it replace:

- Record-level and tenant-level authorization.
- Infrastructure configurations such as network, gateway, and actuator exposure.
- Issuer/audience/token-type validation.
- Rules for message/batch flows that do not go through HTTP.

### 14.2. Public Does Not Mean Bypassing All Security Filters

`permitAll()` allows the request at the HTTP authorization layer. It **does not remove the filter chain** and does not automatically skip all security processing. For example, an invalid Bearer token can still be rejected at the authentication filter before reaching `permitAll`.

You should not use `web.ignoring()` or remove the security chain from endpoints that need CORS/security headers/logging just to make them "public," unless you have carefully evaluated the consequences. For most applications, using `permitAll()` inside the chain for public endpoints is preferable to excluding filters altogether.

### 14.3. 401 and 403 in Per-Group Policies

A Resource Server typically distinguishes:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

when an endpoint requires authentication and lacks valid credentials.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

when the principal is authenticated but lacks permissions. Details of `WWW-Authenticate` depend on the error type/handler; not every 403 includes the same error parameter. Never return raw JWTs, access tokens, sensitive claims, or exception stack traces to clients.

If an API uses OAuth2 Login sessions, the entry point may redirect web requests to a login page. For Bearer APIs, callers generally need **API-semantic 401/403 responses**, not unconditional redirects to a website login.

## 15. Common Mistakes in HTTP Authorization

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Placing `/api/**.permitAll()` before `/api/admin/**`. | Admin endpoints are left open because the first rule matches. | Place specific rules first and restrict public rules. |
| Using only `anyRequest().authenticated()` for business APIs. | Any valid token can access more endpoints than necessary. | Define scopes per group/method and a deny fallback. |
| Using `hasRole("ADMIN")` for a token that only has `SCOPE_admin.manage`. | Checks the wrong authority type. | Align scope vs. role and converters. |
| Allowing GET/POST on the same path with a single generic rule. | A read-only token can invoke write operations. | Use matchers per HTTP method. |
| Placing `anyRequest()` before specific rules. | Later rules are never evaluated or the DSL is invalid. | Place the fallback last. |
| Multiple chains with no fallback. | Some URLs are unprotected by Spring Security. | Control chain matchers/ordering and include a fallback chain. |
| Using `securityMatcher("/api/**")` and assuming Actuator is protected. | `/actuator/**` sits outside the API chain. | Configure separate management/exposure/fallback policies. |
| Using `permitAll()` on all OPTIONS to fix CORS. | CORS does not automatically return the right headers, and methods may open unintentionally. | Configure CORS processing and test preflight. |
| Disabling CSRF system-wide because there is a Bearer API. | Web session-cookie flows may lose CSRF protection. | Separate Bearer APIs and web sessions. |
| Trusting `scope` while forgetting issuer/audience. | Tokens from another system can be misused. | Configure `JwtDecoder` and validators. |
| Using JWT `sub` as proof of ownership for every record. | IDOR/BOLA and cross-tenant access. | Domain policy checks owner/tenant against real data. |
| Testing only allowed requests. | Fails to detect overly permissive endpoints. | Test 401/403/fallback, methods, and overlapping paths. |
| Using the `jwt()` test helper and concluding JWT signatures are safe. | Tests bypass the decoder and JWKS. | Add tests for real signed JWTs and profile validation. |
| Logging the Authorization header on failed requests. | Leaks Bearer credentials. | Log error type/request ID; redact tokens and sensitive info. |

## 16. Practical Workflow for Designing an HTTP Policy

1. **List all existing and planned endpoints** by HTTP method, URL, data type, and operation impact.
2. **Group clearly**: public, authenticated-only, read, write, admin, internal, health/management, callback/web, and undeclared.
3. **Align the OAuth Access Token contract**: issuer, API audience, scope names, token profile, authority mapping, and the boundary between user tokens and client tokens.
4. **Define the SecurityFilterChain**: specific matchers before broad matchers; use `requestMatchers(HttpMethod, path)` for distinct groups; fallback to `anyRequest().denyAll()`.
5. **If using multiple chains**, choose `securityMatcher` and `@Order` deliberately; ensure a matching chain exists for every endpoint needing protection.
6. **Protect browser integrations**: CORS preflight, origin allowlist, CSRF aligned with the credential flow, and security headers.
7. **Separate business authorization**: add checks for internal account status, tenant, owner, membership, resource state, and business policies in the service layer.
8. **Test both positive and negative paths**: anonymous, invalid token, missing scope, wrong method, new routes, admin paths, multi-chain routing, CORS, and resource access.
9. **Review before adding endpoints**: require developers to update the policy matrix and tests alongside controllers/services; never open a broad wildcard to "fix" a 403 error.

**Remember:** `authorizeHttpRequests` is where you express the **HTTP access policy** of a Spring Security Resource Server. Rules must be ordered by **matcher specificity**, separate **GET/POST/DELETE**, distinguish **public/authenticated/read/write/admin** groups, and include a **deny fallback**. JWT authentication ensures the token is trustworthy; HTTP authorization ensures the endpoint matches the permissions; domain authorization continues protecting **specific data**.

## References

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Java Configuration and Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
