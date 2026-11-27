# Distinguishing GET, POST, PUT, and DELETE When Assigning Access Permissions

In a **Spring Security OAuth 2.0/OIDC Resource Server**, the same API path can serve multiple different operations. A user allowed to view an order may not be allowed to create a new order, edit the delivery address, or delete the order. Therefore, protecting `/api/orders/**` with a generic "authenticated" rule is usually not enough: you must distinguish **the HTTP method**, **the permissions granted to the access token**, and **the principal's permissions on the specific resource**.

For example, the same resource:

```http
GET /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
```

```http
PUT /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json

{"deliveryAddress": "Updated address"}
```

The two requests share the same path but carry different intents. With Spring Security Servlet, you can use `requestMatchers(HttpMethod.GET, ...)` and `requestMatchers(HttpMethod.PUT, ...)` to enforce distinct policies right at the **HTTP authorization layer**.

This lesson focuses on assigning permissions for **GET, POST, PUT, and DELETE**, while also explaining related cases such as `PATCH`, `HEAD`, `OPTIONS`, CORS, CSRF, rule ordering, unsupported methods, method security, and record-level permissions.

## 1. What Does an HTTP Method Signify?

An HTTP method describes **the semantics of the requested action on a resource**, rather than being a security permission on its own. When designing REST APIs, people commonly use these conventions:

| Method | Common HTTP semantics | Orders API example | Potential API permission required |
|---|---|---|---|
| **GET** | Retrieve a resource representation; **safe** in HTTP semantics | `GET /api/orders/123` | `orders.read` |
| **POST** | Ask the target resource to process the payload per endpoint semantics; often creates or executes a task | `POST /api/orders` | `orders.create` or `orders.write` |
| **PUT** | Create/replace the state of the target resource with the submitted representation, per contract | `PUT /api/orders/123` | `orders.update` or `orders.write` |
| **DELETE** | Request removal of the association between the URI and resource functionality, typically deleting or marking deleted | `DELETE /api/orders/123` | `orders.delete` or `orders.write` |

This is an **illustrative mapping**, not an OAuth 2.0 specification rule saying GET always maps to `read` or POST always maps to `write`. OAuth scopes are strings agreed upon between the Authorization Server and Resource Server. Spring Security does not automatically infer `GET → read` or `DELETE → admin` unless the application configures it.

### 1.1. Safe and Idempotent Are Not Synonymous with "Public"

HTTP has two properties frequently confused with permissions:

- **Safe method:** the client does not request a meaningful business state change by calling the method. GET and HEAD are defined as safe. Server-side logging, statistics, or incidental side effects do not make GET unsafe if they were not the operation requested by the client.
- **Idempotent method:** multiple identical requests have the same *intended effect on server state* as a single request, even though status codes, logs, or secondary side effects may differ. GET, PUT, and DELETE are idempotent in HTTP semantics; POST is not guaranteed idempotent by method definition.

**Safe does not mean the data is public.** `GET /api/salaries` may be an endpoint only authorized HR staff can read. **Idempotent does not mean low risk.** `DELETE /api/accounts/123` remains a critical action even if repeating it causes no additional deletion in HTTP semantics.

### 1.2. PUT and DELETE Are Not the Same as POST

`PUT /api/orders/123` typically targets a resource with an identified URI and target representation. If the API allows **PUT to create when the resource does not yet exist**, a caller with only "update existing order" permission might accidentally create new orders unless the service distinguishes that case. When the contract forbids upsert, the service must reject missing resources; if allowed, it must apply the corresponding create policy.

`DELETE` can be a soft delete, hard delete, or business state transition. Required permissions depend on **impact**, not merely the method name. A token with `orders.write` is not necessarily allowed to delete data subject to retention rules.

`POST` is especially diverse: it can create orders, cancel orders, execute payments, or even run searches with complex payloads. Thus you should not assign every POST to a single write permission without inspecting the endpoint.

## 2. Three Permission Decision Layers in a Resource Server

A request with an access token must satisfy multiple conditions:

```mermaid
flowchart TD
    A["HTTP request: method + path + Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C{"Valid token?<br/>issuer, audience, signature, lifetime"}
    C -->|"No"| X["401 / invalid_token"]
    C -->|"Yes"| D["Authentication with GrantedAuthority"]
    D --> E{"HTTP method + path<br/>matches rule and has permission?"}
    E -->|"No"| Y["403 / insufficient_scope if applicable"]
    E -->|"Yes"| F["Controller / Service"]
    F --> G{"Owner, tenant, state,<br/>and data policy valid?"}
    G -->|"No"| Z["403 or 404 per policy"]
    G -->|"Yes"| H["Execute operation"]
```

| Layer | What needs to be known? | Example |
|---|---|---|
| **Authentication** | Who issued the access token, is it still valid, and is it for this API? | Valid `iss`, `aud=orders-api`, valid signature, unexpired `exp` |
| **HTTP authorization** | Does the caller have permission to perform this type of operation on this route? | GET requires `SCOPE_orders.read`, DELETE requires `SCOPE_orders.delete` |
| **Business authorization** | Does the principal have permission to act on **this specific order** in its current state? | User belongs to the right tenant and is owner, or holds approved admin privileges |

A token with `SCOPE_orders.delete` does not prove the caller may delete someone else's order `ORD-123`. Conversely, a user may own an order while the current access token only holds `orders.read`; a DELETE request must still be rejected.

## 3. OAuth Scopes and GrantedAuthority in Spring Security

An Authorization Server can issue a JWT access token containing:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create orders.update",
  "exp": 1893459600
}
```

The example depicts only a payload; it is not a validly signed token. When `JwtDecoder` verifies the token and `JwtAuthenticationConverter` uses the standard mapping, Spring Security converts scopes into `GrantedAuthority` instances:

```text
orders.read   -> SCOPE_orders.read
orders.create -> SCOPE_orders.create
orders.update -> SCOPE_orders.update
```

Rules like `hasAuthority("SCOPE_orders.read")` inspect authorities on the current request's `Authentication`. The string `SCOPE_` is Spring Security's default prefix, **not a prefix that the Authorization Server must write into the `scope` claim**.

With opaque tokens, the Resource Server uses introspection to obtain granted scopes; Spring Security can likewise convert those scopes into `SCOPE_...` authorities. When using a custom converter, prefix and claim names may differ, so HTTP rules must match the **actual** authorities produced.

### 3.1. Do Not Use `hasRole` to Check Default Scopes

```java
.hasAuthority("SCOPE_orders.read") // checks the exact authority name
.hasRole("ADMIN")                  // checks ROLE_ADMIN by default
```

`hasRole("orders.read")` typically checks `ROLE_orders.read`, not `SCOPE_orders.read`. Having a scope name that looks like a role does not make Spring Security treat them as equivalent.

### 3.2. Does "Write" Permission Imply "Read" Permission?

No. Scopes have no automatic hierarchical relationship:

```text
SCOPE_orders.write
    does not automatically imply
SCOPE_orders.read
```

If a system wants write permission to include read permission, express that explicitly in policy—for instance using `hasAnyAuthority("SCOPE_orders.read", "SCOPE_orders.write")` on GET, or issuing both scopes in the token. Never infer a hierarchy from naming alone.

## 4. Assigning Different Permissions via `requestMatchers(HttpMethod, ...)`

In Spring Security Servlet 6+, authorization configuration commonly uses:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.PUT, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
)
```

This is an **initial illustrative pattern**: GET uses read, while POST/PUT/DELETE use write. It demonstrates method differentiation yet has limitations:

- All POST/PUT/DELETE share write, failing to separate create, update, and delete.
- A broad pattern may include routes with very different business semantics.
- `anyRequest().authenticated()` allows other methods/paths through solely because the token is valid, even without scope rules for them.

For APIs with multiple sensitive operations, assign permissions **by `(HTTP method, business-meaningful path)` pairs** and end with an appropriate fallback.

### 4.1. Detailed Example for the Orders API

Endpoint and scope design:

| Request | Function | Required authority |
|---|---|---|
| `GET /api/orders` | List visible orders | `SCOPE_orders.read` |
| `GET /api/orders/{id}` | View order details | `SCOPE_orders.read` |
| `POST /api/orders` | Create order | `SCOPE_orders.create` |
| `PUT /api/orders/{id}` | Replace/update per API contract | `SCOPE_orders.update` |
| `DELETE /api/orders/{id}` | Delete/remove per DELETE contract | `SCOPE_orders.delete` |
| `POST /api/orders/{id}/cancel` | Cancel order via business command | `SCOPE_orders.cancel` |

Each authority is a string agreed upon by the Authorization Server and Resource Server; no names are invented by Spring Security merely from HTTP methods. For example, `orders.cancel` exists only if the system designs and issues that scope.

### 4.2. Complete Servlet Configuration by Method and Route

Example using Spring Boot 3.x, Spring Security 6+, and Spring MVC:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Example REST API using Bearer in the Authorization header,
            // not cookies/sessions as credentials for write operations.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()

                // HEAD has semantics similar to GET without returning a response body.
                .requestMatchers(HttpMethod.HEAD,
                    "/api/orders", "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(HttpMethod.GET,
                    "/api/orders", "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.read")

                // Cancel command is a distinct permission; do not treat every POST as create.
                .requestMatchers(HttpMethod.POST,
                    "/api/orders/{orderId}/cancel")
                    .hasAuthority("SCOPE_orders.cancel")

                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")

                .requestMatchers(HttpMethod.PUT,
                    "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.update")

                .requestMatchers(HttpMethod.DELETE,
                    "/api/orders/{orderId}")
                    .hasAuthority("SCOPE_orders.delete")

                // Methods/paths not explicitly permitted are denied.
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Here:

1. `oauth2ResourceServer(...jwt...)` enables Bearer token handling.
2. The JWT decoder verifies signature/issuer/timestamps and audience per the active configuration/validators.
3. Spring Security maps scopes to `SCOPE_...` authorities.
4. `requestMatchers(HttpMethod.X, path)` matches **both method and path**, then applies the corresponding policy.
5. `anyRequest().denyAll()` denies any unlisted route in this chain, helping prevent accidentally adding a new endpoint while forgetting its scope.
6. The service still needs to decide which principal may edit/cancel/delete a specific order.

The example uses the pattern `"/api/orders/{orderId}"` with Spring MVC/modern Spring Security path matching when MVC is present. Path pattern interpretation can depend on matcher type, Servlet path, and version. When an application has a context path or custom Servlet mapping, ensure matchers align with the actual URI observed by Spring Security.

**Note that `/api/orders` and `/api/orders/{orderId}` are two different paths.** A rule for the collection does not necessarily cover items. A pattern like `/api/orders/**` may be broader than expected; consider the scope of all child endpoints.

### 4.3. Ordering Rules to Prevent Broad Rules from Swallowing Narrow Rules

Spring Security evaluates authorization rules in declaration order and uses **the first matching rule** in the chain handling the request. Incorrect example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
        .hasAuthority("SCOPE_orders.delete")
    .anyRequest().denyAll())
```

The first rule does not restrict the method. A request:

```http
DELETE /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_READ
```

already matches `"/api/orders/**"`, so **the specific DELETE rule below it is unused**. This illustrates how a read scope can mistakenly be applied to delete operations.

Correct approach: place specific method-path exceptions/pairs first, followed by broader rules or fallback.

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
        .hasAuthority("SCOPE_orders.delete")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll())
```

Yet putting specific rules first **is not enough** if a later broad rule still allows unlisted sensitive methods. When configuring method-based authorization, minimize method-less matchers in API zones (aside from genuinely public endpoints or those with a uniform policy across all methods).

### 4.4. Path-Only `permitAll` Opens Other Methods Too

Example:

```java
.requestMatchers("/public/health").permitAll()
```

means this path is permitted for **every HTTP method matched by that matcher**, not just GET. If the controller supports only GET, POST may return 405 at the MVC layer; yet the security layer already let it through. If strict per-method protection is required:

```java
.requestMatchers(HttpMethod.GET, "/public/health").permitAll()
.requestMatchers(HttpMethod.HEAD, "/public/health").permitAll()
```

Place these rules before `anyRequest().denyAll()`. Do not use an overly broad public matcher like `"/public/**"` if that path tree might later gain a state-changing POST endpoint.

## 5. Basic Mapping: GET Reads, POST Creates, PUT Updates, DELETE Deletes

### 5.1. GET: Reads, Yet Not Public to Everyone by Default

Example:

```http
GET /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_READ
```

At the HTTP layer:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

Then in the service:

- Does the user genuinely belong to the order's tenant?
- Is the user the owner or authorized to read on someone else's behalf?
- Does the order hold sensitive data requiring an extra role?
- Which fields may be returned to this principal type?

**GET is safe in HTTP semantics, not exempt from authentication or ownership checks.** For example, `GET /api/orders/{id}/invoice` may require a more sensitive scope like `invoices.read`.

Never design a GET endpoint to trigger client-requested side effects, such as `GET /api/orders/123/delete`. Link previews, crawlers, or prefetchers can invoke GET; placing deletion behind GET violates HTTP semantics and makes a "GET = read" policy dangerous.

### 5.2. POST: Distinguish Resource Creation from Business Commands

Resource creation example:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_CREATE
Content-Type: application/json

{"items": [{"sku": "SKU-001", "quantity": 1}]}
```

Rule:

```java
.requestMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.create")
```

Yet another POST could be:

```http
POST /api/orders/ORD-123/cancel HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_CANCEL
```

This should require a separate `SCOPE_orders.cancel` if cancellation carries higher risk than creation. Do not treat every POST under `"/api/orders/**"` as creating an order.

Additionally, some APIs use:

```http
POST /api/orders/search HTTP/1.1
Content-Type: application/json

{"filters": {"status": ["PAID", "SHIPPED"]}}
```

**Even though it is POST, this operation may only read data.** Depending on design, it may require `SCOPE_orders.read` rather than `SCOPE_orders.create`. Choose scopes based on **function and business impact**, not mechanically by method name.

### 5.3. PUT: Replace, Update, and Upsert Risks

Example:

```http
PUT /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_UPDATE
Content-Type: application/json

{"deliveryAddress": "Updated address"}
```

If the API genuinely uses PUT for **full-representation replacement**, the server must document required fields and handle missing fields per contract. For partial updates, PATCH is usually a better fit, or PUT's contract must be clearly defined.

The HTTP rule:

```java
.requestMatchers(HttpMethod.PUT, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.update")
```

is not enough to decide:

- May an already-shipped order change its address?
- May a user update someone else's order?
- May the client alter server-owned fields like total amount, owner, tenant, or status?
- If the URI does not exist, is PUT allowed to create a new record or must it return 404?

In particular, if PUT can **upsert**, do not rely solely on `SCOPE_orders.update` and accidentally permit creation. Either forbid creation via PUT or require `orders.create` when the resource does not yet exist, checking after resolving state in the service.

### 5.4. DELETE: Idempotent Yet Highly Sensitive

```http
DELETE /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_DELETE
```

Rule:

```java
.requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.delete")
```

Beyond the scope, the service may require:

- The order belongs to an allowed tenant and principal.
- The order has not been paid/dispatched, or meets cancellation criteria.
- The data is not subject to a legal retention hold.
- Auditing or transition to an archived state per policy.

DELETE being **idempotent** does not mean responses are always identical: the first delete may return 204 and the next 404, yet the intended effect ("resource no longer exists") remains idempotent. Some APIs forbid clients from DELETE-ing completed resources and instead use a business POST cancel; policies must match the real endpoints.

## 6. Simple Scopes or Granular Scopes?

There are two common models, both valid if designed consistently.

### 6.1. Read/Write Model

```text
GET                  -> SCOPE_orders.read
POST, PUT, DELETE    -> SCOPE_orders.write
```

Pros:

- Easy to understand and issue scopes.
- Fits small APIs where write operations carry similar sensitivity.

Limitations:

- A caller needing only to update an order address can also DELETE if every mutating endpoint requires `orders.write`.
- Harder to apply tailored policies for refund/cancel/export.

### 6.2. Granular Model by Business Capability

```text
GET /api/orders/{id}              -> SCOPE_orders.read
POST /api/orders                  -> SCOPE_orders.create
PUT /api/orders/{id}              -> SCOPE_orders.update
DELETE /api/orders/{id}           -> SCOPE_orders.delete
POST /api/orders/{id}/cancel      -> SCOPE_orders.cancel
POST /api/orders/search           -> SCOPE_orders.read
```

Pros:

- Supports the **least privilege** principle: tokens hold only the permissions needed for the task.
- Separates sensitive actions from ordinary writes.
- Makes API permissions easier to explain to clients and administrators.

Limitations:

- Requires managing more scopes in the Authorization Server.
- Defining scopes so granular that they mirror individual records makes tokens and authorization hard to manage; per-record permissions usually belong in domain services/policy stores.

A practical approach is using **capability** scopes at the HTTP layer while enforcing ownership, tenant, admin roles, and resource state in the service layer.

### 6.3. Scopes Have No Automatic Inheritance

`SCOPE_orders.delete` does not automatically imply `SCOPE_orders.read`. If an admin has permission for all operations, express it explicitly:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAnyAuthority(
        "SCOPE_orders.read",
        "SCOPE_orders.admin")
```

This expresses an **OR** relationship: holding either authority suffices. If a rule requires **both** conditions simultaneously, use a policy/`AuthorizationManager` for AND logic. Do not mix `hasRole("ADMIN")` with `SCOPE_...` unless you are certain converters produce `ROLE_ADMIN` reliably.

## 7. GET, HEAD, OPTIONS, PATCH, and Other Methods

Although this lesson focuses on the four primary methods, a secure Resource Server must know **how other methods are handled**.

### 7.1. HEAD: Close to GET, Yet a Distinct Method in Authorization Matching

In HTTP, HEAD is like GET in selecting response headers/metadata without returning a body. Spring MVC can support HEAD for handlers annotated with `@GetMapping`.

However, `HttpMethod.GET` and `HttpMethod.HEAD` are **two distinct values**. When a rule matches only:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

do not assume that matcher always matches HEAD. Decide explicitly:

```java
.requestMatchers(HttpMethod.HEAD, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

If HEAD hits a `denyAll` fallback, a client with read permission may get 403 on HEAD even though GET succeeds. That may be intentional policy or a UX bug, depending on contract.

HEAD can also reveal sensitive metadata such as resource existence, size, or last-modified timestamp. Do not open all HEAD requests to anonymous callers merely because there is no response body.

### 7.2. OPTIONS and CORS Preflight

When a browser makes a cross-origin request with an `Authorization` header or a non-simple request, it typically sends a **CORS preflight**:

```http
OPTIONS /api/orders/ORD-123 HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization
```

Preflight usually **does not send the real request's Bearer access token**. If the authentication filter rejects preflight as a request requiring a bearer token, the browser may never send the real DELETE, even when the user's token is authorized.

The recommended solution in Spring Security Servlet is configuring **CORS before Security authorization** for allowed origins/methods/headers, for instance via `CorsConfigurationSource` and `http.cors(...)`:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://shop.example.com"));
    cors.setAllowedMethods(List.of(
        "GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false);
    cors.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
```

And in `SecurityFilterChain`:

```java
.cors(Customizer.withDefaults())
```

This is a sample configuration for an API using a Bearer header sent explicitly by JavaScript, without cookies as credentials. In systems with cookies, `allowCredentials` and allowed origins must be designed separately; never enable wildcard origins combined with unchecked credentials.

**CORS is not authorization:** permitting an origin to run preflight **does not mean** the real POST/PUT/DELETE has the scope. The subsequent request still must pass Bearer authentication and method-specific authorization.

Do not resolve preflight errors simply with a rule opening all `OPTIONS` system-wide without understanding CORS filters/matchers; non-preflight OPTIONS requests exist and API policies may differ.

### 7.3. PATCH: Partial Update, Does Not Inherit PUT Permissions

An API may expose:

```http
PATCH /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_UPDATE
Content-Type: application/merge-patch+json

{"deliveryAddress": "New address"}
```

If PATCH is supported, add a dedicated rule:

```java
.requestMatchers(HttpMethod.PATCH, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.update")
```

Or require a distinct scope if patch operations carry different permissions from PUT. `HttpMethod.PUT` does not automatically match PATCH; if `anyRequest().authenticated()` is used as fallback, PATCH could pass without the update scope.

### 7.4. TRACE and Disallowed Methods

A typical API rarely has reason to enable `TRACE`, `CONNECT`, or methods outside its contract. `anyRequest().denyAll()` helps block undeclared methods at the authorization layer. Simultaneously, web servers/proxies and controllers must configure the appropriate supported method set; authorization does not replace protocol-level controls in infrastructure.

## 8. Distinguishing 401, 403, 404, and 405

Method-based permission assignment directly affects how the application returns errors.

| HTTP status | Common meaning | Example |
|---|---|---|
| **401 Unauthorized** | Request lacks or fails valid authentication | Protected GET without Bearer, bad signature, or expired token |
| **403 Forbidden** | Authentication may be valid, but action is not permitted | DELETE with a token holding only `orders.read` |
| **404 Not Found** | Resource/route does not exist, or domain chooses to hide existence | Non-existent order ID, or API hides another user's order |
| **405 Method Not Allowed** | Resource/handler does not support that HTTP method | `POST /api/orders/123` when controller only maps GET/PUT/DELETE |

**These outcomes depend on processing order.** The Spring Security filter chain usually runs before the controller. With `anyRequest().denyAll()`, an unpermitted method may be rejected at the security layer (403 after authentication) **before** Spring MVC gets a chance to determine 405. Similarly, an unauthenticated request may receive 401 instead of 404.

Therefore, do not rely on a security assumption that "every unsupported method must always return 405." If an API requires consistent 405 responses per a public contract, design it deliberately so it neither leaks data nor bypasses auth.

### 8.1. Tracing an Insufficient Scope Flow

```http
DELETE /api/orders/ORD-123 HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
```

Suppose the token contains:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

In reality a token also needs a valid signature and lifetime; do not treat the payload above as sufficient for authentication. After authentication, `Authentication` holds `SCOPE_orders.read` but lacks `SCOPE_orders.delete`. The DELETE rule denies it → typically **403**. The Bearer access denied handler may emit `WWW-Authenticate` with `error="insufficient_scope"` per RFC 6750 depending on configuration.

If the token is expired, the request **normally never reaches scope comparison** and is rejected at authentication → typically **401** with Bearer `invalid_token`.

### 8.2. Never Turn Missing Scope into Default Permission

Never write custom code like:

```java
// Illustrative anti-pattern: DO NOT use.
if (!authenticationHas("SCOPE_orders.delete")) {
    // Missing permission => still run delete for compatibility
    deleteOrder();
}
```

A missing permission must result in denial or a deliberately designed business path, never an "allow" fallback.

## 9. Multiple SecurityFilterChains: Covering All Paths

Large applications may have multiple chains:

```text
/internal/** -> Basic/service authentication
/api/**      -> OAuth2 Resource Server JWT
Other URLs   -> fallback security policy
```

Example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().denyAll())
        .build();
}
```

Imports for the example include `org.springframework.core.annotation.Order`, `HttpMethod`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer`. In real systems, define complete chains for internal URLs and their authentication mechanisms.

**Important distinction:**

- `securityMatcher("/api/**")` determines which requests **enter the chain**.
- `requestMatchers(HttpMethod.GET, "...")` determines authorization rules **inside the selected chain**.

`FilterChainProxy` selects **the first matching `SecurityFilterChain`** in order; it does not merge rules across chains. If a URL matches no chain, it may **not go through Spring Security web filters** as expected. A fallback chain prevents "gaps" when declaring chains with restricted matchers.

### 9.1. Two Independent Ordering Levels

There are two separate questions:

1. **Chain order:** which chain handles the request? `@Order(1)` takes priority over `@Order(2)` when matchers overlap.
2. **Rule order:** inside that chain, which authorization matcher matches first? Method/path rules can be shadowed by a broad path rule placed earlier.

A misconfiguration at either level can allow GET permissions to cover POST/DELETE or leave an endpoint without Resource Server filters.

## 10. Path Mappings Must Match Real Handlers

Placing rules by method only works when **paths are matched accurately**.

Example controller:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderDto getOrder(@PathVariable String orderId) {
        return orders.getOrder(orderId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderDto create(@RequestBody CreateOrderCommand command) {
        return orders.create(command);
    }

    @PutMapping("/{orderId}")
    public OrderDto update(
            @PathVariable String orderId,
            @RequestBody UpdateOrderCommand command) {
        return orders.update(orderId, command);
    }

    @DeleteMapping("/{orderId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String orderId) {
        orders.delete(orderId);
    }
}
```

The classes `OrderService`, `OrderDto`, and command DTOs are application components not defined here; the example simply shows how controller URL/method mappings relate to authorization matchers.

With `@RequestMapping("/api/orders")`, Spring MVC binds:

- `@PostMapping` → POST `/api/orders`.
- `@GetMapping("/{orderId}")` → GET `/api/orders/{orderId}`.
- `@PutMapping("/{orderId}")` → PUT `/api/orders/{orderId}`.
- `@DeleteMapping("/{orderId}")` → DELETE `/api/orders/{orderId}`.

When changing controller mappings (for example from `/api/orders/{id}` to `/api/v2/orders/{id}`), update security matchers and policies accordingly. A rule that no longer matches the new handler can cause unexpected denials or, with an overly broad fallback, over-permissive access.

### 10.1. Broad Patterns Can Include Unintended Endpoints

`"/api/orders/**"` can cover:

```text
/api/orders
/api/orders/ORD-123
/api/orders/ORD-123/notes
/api/orders/ORD-123/export
/api/orders/ORD-123/cancel
```

Exact behavior depends on the path matcher; in practice a broad pattern can catch more routes than intended. If `GET /api/orders/ORD-123/export` contains sensitive financial data, it may need `orders.export` instead of `orders.read`.

**Principle:** apply rules from specific to general and keep a deny fallback. Never rely on a trailing `/**` alone to assume all child endpoints share the same sensitivity level.

### 10.2. A Path with a Path Variable Is Not a Per-Object Scope

IDs like `ORD-123` in the URL are caller-chosen data. A rule:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.read")
```

does not verify that `orderId` belongs to the `sub` inside the token. If the client swaps `ORD-123` for `ORD-999`, Spring Security still matches the same route and the same scope. **Object-level authorization** must rely on ownership/tenant data in the service or an equivalent policy decision point.

## 11. Object Authorization: Method Scope Is Necessary, Not Sufficient

Example JWT after verification:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.update",
  "tenant_id": "tenant-a"
}
```

A controller receiving the verified principal:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}

@GetMapping("/api/orders/{orderId}")
public OrderDto readOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );
    return orderService.readVisibleTo(actor, orderId);
}
```

The snippet illustrates a controller method and record (placed in proper files/classes in a real implementation), assuming `orderService` is injected. It should run only after properly configured JWT authentication. With opaque tokens, the controller should accept `Authentication`/`OAuth2AuthenticatedPrincipal` instead of casting every principal to `Jwt`.

In the service:

```java
public OrderDto readVisibleTo(CurrentActor actor, String orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean sameTenant =
        order.getTenantId().equals(actor.tenantId());

    boolean isOwner =
        order.getOwnerIssuer().equals(actor.issuer()) &&
        order.getOwnerSubject().equals(actor.subject());

    if (!sameTenant || !isOwner) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

The example depicts an "only the order owner within the right tenant may view" policy, excluding admin/delegation cases. When admin roles exist, explicitly define the conditions overriding ownership and never rely on unverified role claims.

### 11.1. PUT/DELETE Need Resource State Checks

Even when the client holds `SCOPE_orders.update` or `SCOPE_orders.delete`, the service may need:

```text
UPDATE:
  order belongs to the right owner and tenant
  order has not shipped yet
  server-owned fields such as price/owner/tenant are not modified

DELETE:
  order belongs to the right owner and tenant
  order is unpaid or eligible for deletion
  does not violate retention/audit policies
```

This business policy runs after method-level authentication/authorization. Operations may require appropriate transactions/locking to avoid state changing between check and write.

### 11.2. Method Security Is an Additional Layer

When enabled:

```java
@EnableMethodSecurity
```

you can add service-layer protection:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto read(String orderId) {
        return readWithBusinessPolicy(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.delete')")
    public void delete(String orderId) {
        deleteWithBusinessPolicy(orderId);
    }
}
```

The methods `readWithBusinessPolicy` and `deleteWithBusinessPolicy` are illustrative placeholders, not yet defined. **Method security checks authorities but does not replace ownership checks** unless the application adds an expression/`AuthorizationManager` with concrete data policies.

In the default proxy configuration, **self-invocation** (a method in a bean calling another annotated method on the same bean) can bypass the Spring AOP proxy. Therefore, do not rely on `@PreAuthorize` as the sole protection for internal flows if the architecture involves self-calls.

## 12. Valid Authentication Is Not Permission to Call Every Method

For JWTs, a Resource Server needs a trusted `JwtDecoder` to verify:

- JWS signature, algorithm, and key.
- Issuer `iss`.
- Audience `aud` intended for the API.
- Expiration `exp` and not-before `nbf`.
- Other mandatory claims per the token profile.

Example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences: orders-api
```

In Boot versions supporting `audiences`, this property binds the audience on the auto-configured decoder. When the application defines its own `JwtDecoder` bean, configure validators explicitly; do not assume Boot automatically attaches every property to a custom bean.

### 12.1. A Properly Signed JWT Does Not Mean DELETE Is Allowed

A token with:

```text
iss = trusted issuer
aud = orders-api
unexpired exp
scope = orders.read
```

can pass authentication, yet DELETE must still be rejected. The Authorization Server authenticated the user/client and issued **read scope**, not "every permission on the resource."

### 12.2. Client Credentials Can Represent a Service Principal

A token from client credentials may represent a service:

```text
client_id = nightly-order-job
scope = orders.read
```

Do not assume `Authentication.getName()` is an interactive human user. The API still applies method-based scopes and resource/tenant policies appropriate for a service identity. If a job needs to delete data, grant a narrowly scoped dedicated permission; never use broad admin credentials just to handle a small task.

### 12.3. An OIDC ID Token Is Not an API Access Token

An OIDC ID token is typically issued to an OIDC client to communicate login results. It does not replace a Resource Server access token, even though it contains `sub` and has a valid signature. The API must verify the proper token profile and audience; holding an `id_token` does not automatically grant `SCOPE_orders.read`.

## 13. CSRF and CORS: Mutating Methods Have Distinct Security Characteristics

### 13.1. CSRF Protects Against Browser-Auto-Sent Credentials

POST, PUT, and DELETE methods typically mutate state. If the application uses cookies/sessions or any credential automatically attached by browsers, **CSRF** is a concern to evaluate.

For example:

```java
.csrf(AbstractHttpConfigurer::disable)
```

can be reasonable for an **API purely using Bearer tokens in the `Authorization` header**, where browsers do not attach tokens automatically on cross-site requests without client code. However, if the same application uses session cookies or browser HTTP Basic for mutating actions, disabling CSRF globally can be unsafe.

Never treat "this is a REST API" or "we use JWT" as sufficient reason to disable CSRF. Evaluate **how credentials are transmitted and whether the browser can attach them automatically**.

### 13.2. CORS Does Not Grant Scopes

CORS responses tell browsers which origins may read responses under browser policy. They do not replace bearer authentication or `hasAuthority` rules. A `DELETE` request passing CORS preflight still needs a token with the proper scope on the actual request.

CORS configuration must account for both `OPTIONS` preflights and the allowed actual methods. Never use `permitAll()` on POST/PUT/DELETE just to fix a CORS error.

## 14. Idempotency, Method Override, and Reverse Proxies

### 14.1. HTTP Idempotency Differs from Business Idempotency Keys

DELETE and PUT are defined as idempotent in HTTP semantics, yet that does not prevent duplicate transaction replay or protect against unauthorized actions. For payment/order POSTs, systems may need an **idempotency key** to prevent duplicate creation on client retries:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer TOKEN_WITH_ORDERS_CREATE
Idempotency-Key: request-1234
Content-Type: application/json

{"items": [{"sku": "SKU-001", "quantity": 1}]}
```

`Idempotency-Key` is an API convention; it requires storage, concurrency control, principal/scope/request binding, and expiration logic. The header alone does not guarantee deduplication, nor does it grant `orders.create`.

### 14.2. HTTP Method Override Can Skew Authorization Results

Some older stacks support `X-HTTP-Method-Override` or a `_method` form parameter to tunnel PUT/DELETE over POST. If the proxy, servlet filter, and Spring Security observe **inconsistent** methods, mismatches can occur:

```text
Initial HTTP layer: POST /api/orders/123
Method override filter: changes to DELETE
Which method does Spring Security see?
Which method does the Spring MVC handler receive?
```

If Spring Security permits POST under a create scope, yet the final controller receives DELETE, that is an authorization boundary breach. Ensure **consistent filter ordering and method interpretation**, or disable method override when the API does not need it. Never trust client-set override headers without explicit design.

### 14.3. Proxies Should Not Arbitrarily Transform HEAD and GET

Proxies may optimize caching or perform health checks using HEAD/GET. At the application layer, policies must reflect the actual method Spring Security receives. If a proxy alters methods, understand its behavior and ensure transformations never bypass API authorization.

## 15. Testing Method-Based Authorization

When testing, separate two parts:

1. **JWT authentication/decoder:** verifies signature, issuer, audience, expiration, and converts the token into an Authentication.
2. **HTTP authorization:** given a constructed Authentication, are GET/POST/PUT/DELETE requests allowed per authorities?

Spring Security Test supports `MockMvc` and the `jwt()` request post processor to test the second layer.

### 15.1. Illustrative Method-Specific Authorization Test

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersHttpAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getRequiresReadScope() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-123")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void postRequiresCreateScope() throws Exception {
        mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"items\":[]}")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }
}
```

This snippet illustrates how to test the policy, not a complete test suite: compatible controllers/services and test data are needed so GET can return 200, along with CSRF configured as in the sample API so POST is not blocked by CSRF before reaching the authority rule. To isolate the HTTP layer, mock controllers/services instead of hitting a real database.

`jwt().authorities(...)` **pre-populates Authentication for the test**, so it does not prove that a JWT bearer string is validated by the parser/decoder or that `scope`/`scp` is mapped properly by the default converter. To test those, write integration tests with JWTs signed by test keys, a test decoder/JWKS, and a real Bearer header.

### 15.2. GET, POST, PUT, DELETE Test Matrix

| Request | Token authorities | Expected HTTP authorization outcome |
|---|---|---|
| GET `/api/orders/123` | `SCOPE_orders.read` | Allowed into controller/service |
| GET `/api/orders/123` | Only `SCOPE_orders.create` | Denied |
| POST `/api/orders` | `SCOPE_orders.create` | Allowed into controller/service |
| POST `/api/orders` | Only `SCOPE_orders.read` | Denied |
| PUT `/api/orders/123` | `SCOPE_orders.update` | Allowed into controller/service |
| PUT `/api/orders/123` | Only `SCOPE_orders.create` | Denied |
| DELETE `/api/orders/123` | `SCOPE_orders.delete` | Allowed into controller/service |
| DELETE `/api/orders/123` | Only `SCOPE_orders.update` | Denied |
| POST `/api/orders/123/cancel` | `SCOPE_orders.cancel` | Allowed into controller/service |
| POST `/api/orders/123/cancel` | Only `SCOPE_orders.create` | Denied |
| PATCH `/api/orders/123` (no rule declared) | Any scope | Fallback denies per policy |
| HEAD `/api/orders/123` | `SCOPE_orders.read` | Allowed if HEAD rule is present |

"Allowed into service" **does not guarantee HTTP 200/201/204**, because the request may still fail payload validation, resource lookup, or ownership/tenant checks.

### 15.3. Testing Missing Authentication and Missing Permissions

Distinguish:

- **No Bearer token sent** to protected GET: typically 401.
- **Expired JWT / invalid signature / wrong issuer or audience**: typically 401.
- **Valid JWT, missing scope**: typically 403.
- **Valid JWT, sufficient scope, no permission on specific order**: service denies (403/404 per policy).
- **Undeclared method with valid token**: with a `denyAll` fallback, may return 403 before the controller evaluates 405.
- **Valid CORS preflight**: must be handled per CORS configuration without requiring a bearer token like a real request.

With method-specific rules, the most important test is **same path, different HTTP method, permissions must change accordingly**. Testing only that GET succeeds does not prove DELETE is properly protected.

### 15.4. Testing Rule Ordering

A configuration with a broad rule placed first:

```java
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/{orderId}")
    .hasAuthority("SCOPE_orders.delete")
```

must be recognized as risky: DELETE may match the first rule. A test sending **DELETE with a read-only token** catches this bug; the request must **not** reach the delete service.

## 16. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Matching `"/api/orders/**"` without restricting method | Read permission can apply to DELETE | Use `requestMatchers(HttpMethod.X, ...)`, specific rules first |
| `.anyRequest().authenticated()` after a few read/write rules | Undeclared methods may need only a valid token | Consider `denyAll()` for APIs requiring an allowlist |
| Assuming GET is always public | Sensitive data exposure | GET still needs proper scopes/ownership |
| Assuming POST always writes | POST search may be read-only; POST cancel may be more sensitive than create | Choose authorities by endpoint semantics |
| Assuming PUT only updates | PUT can create new records per contract | Forbid upsert or check create permission when needed |
| Assuming idempotent DELETE needs no special permission | Unauthorized data deletion | Check delete scope and resource state |
| Having only a GET rule, forgetting HEAD | HEAD gets denied or hits a different fallback | Decide explicit HEAD policy |
| Ignoring OPTIONS preflight | Browser requests with bearer fail | Configure CORS properly; still protect real requests |
| Allowing all OPTIONS, thinking CORS is solved | CORS policy and authorization get mixed | Use trusted CORS filter/config sources |
| Having a PUT rule without a PATCH rule | PATCH is denied or hits an overly broad fallback | Declare PATCH separately if API supports it |
| Using `hasRole("orders.read")` | Does not match `SCOPE_orders.read` | Use `hasAuthority` with the right prefix |
| Assuming write scope includes read/delete | Over-grants permissions based on assumptions not in OAuth | Define permission relationships explicitly |
| Token has right scope but wrong audience | Cross-API token substitution | Verify `aud` before authorization |
| Thinking `SCOPE_orders.delete` lets you delete any order | Broken Object Level Authorization | Check owner/tenant/business state |
| Custom `JwtDecoder` drops issuer/time validators | Invalid JWTs may be accepted | Keep default validators and add requirements |
| Multiple chains protect only `/api/**`, forgetting other URLs | Paths outside matchers may lack security filters | Add a fallback chain or covering matchers |
| HTTP method override runs after security matching | Permissions enforced for a different method than final handler | Align filter/proxy ordering, or disable override |
| Disabling CSRF because "we use JWT" while keeping session cookies | CSRF risk on mutating operations | Inspect credential sources per flow |
| Using mocked test JWTs to claim signatures are verified | Misses decoder/claim validation | Separate authorization tests and authentication integration tests |

## 17. Workflow for Designing Method-Based Authorization for an API

When developing a new group of endpoints, follow this sequence:

1. **List every actual route and method** from Spring MVC mappings, not just generic URI names.
2. **Describe the business effect** of each endpoint: read, create, replace, partial update, delete, cancel, refund, export, search, and so on.
3. **Design scopes on least privilege**: `orders.read`, `orders.create`, `orders.update`, `orders.delete`, or simpler when the contract truly permits.
4. **Align with the Authorization Server** on scopes clients can request and receive, token audiences, and principal types.
5. **Map scopes to `GrantedAuthority`** in the JWT/opaque Resource Server, typically with the `SCOPE_` prefix.
6. **Declare specific method/path rules first**, especially sensitive operations or endpoints sharing a method with different permissions.
7. **Add a deny fallback** for undefined routes/methods to avoid accidentally opening new endpoints.
8. **Handle HEAD, OPTIONS/CORS, and PATCH** per contract so no method is overlooked.
9. **Configure CSRF to match credential sources** and handle method overrides/proxies consistently.
10. **Enforce per-object and state permissions** in the service; URL IDs are never proof of ownership.
11. **Test the method × authority matrix**, especially read-only tokens calling PUT/DELETE and scopeless tokens hitting new routes.
12. **Distinguish authentication, authorization, and routing errors** when observing 401/403/404/405.

### 17.1. Decision Flowchart

```mermaid
flowchart TD
    A["Request enters API"] --> B{"Passed Bearer authentication?<br/>Valid token and right audience?"}
    B -->|"No"| X["401"]
    B -->|"Yes"| C{"Which SecurityFilterChain matches request?"}
    C -->|"None"| W["Dangerous gap if no fallback exists"]
    C -->|"Matched"| D{"Which method + path rule matches first?"}
    D -->|"denyAll rule"| Y["403"]
    D -->|"Scope rule"| E{"Does Authentication hold required authority?"}
    E -->|"No"| Y
    E -->|"Yes"| F{"Owner/tenant/state policy satisfied?"}
    F -->|"No"| Z["403/404 per policy"]
    F -->|"Yes"| G["Controller/Service handles request"]
```

This diagram is a conceptual model for understanding layers; in reality **chain selection occurs before authentication**, so the true execution order is `FilterChainProxy picks chain → authentication filters → authorization rules → controller/service`. If a URL matches no chain, you cannot assume it underwent Bearer authentication.

## 18. Summary

A brief summary to remember:

```text
HTTP method indicates request intent:
  GET      -> usually read
  POST     -> usually create / execute command
  PUT      -> usually replace / update (possibly upsert)
  DELETE   -> usually delete / transition state

OAuth scope indicates granted capability:
  orders.read / orders.create / orders.update / orders.delete

Spring Security represents scopes as authorities:
  SCOPE_orders.read / SCOPE_orders.create / ...

HTTP authorization applies rules:
  requestMatchers(HttpMethod, path).hasAuthority(...)

Business authorization verifies:
  Right owner? Right tenant? Allowed state? Allowed fields?
```

**GET, POST, PUT, and DELETE must be treated as separate authorization conditions whenever they carry different impacts and risk levels.** Spring Security lets you express this via `requestMatchers(HttpMethod.X, "...")`. Yet the method is only **one part** of the decision: you must also verify the access token, match scopes/authorities per contract, check paths, rule order, and real record-level permissions.

Avoid both extremes: **do not protect all methods with a single overly broad `authenticated()` rule**, yet **do not assign permissions mechanically like "every POST is create, every GET is public."** Good policies are designed from each endpoint's business behavior and then expressed explicitly in Spring Security.

## References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): GET/HEAD/POST/PUT/DELETE, safe and idempotent methods, 405.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789): PATCH semantics.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens and scopes.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authentication, insufficient_scope, and errors.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token claims and audience.
- [Spring Security Reference — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `hasAuthority`, first-match rules.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication and scope mapping.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and authorities.
- [Spring Security Reference — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, chain order, and `HttpSecurity`.
- [Spring Security Reference — CORS (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): preflight and CORS configuration.
- [Spring Security Reference — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protecting write operations and CSRF conditions.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and service protection.
