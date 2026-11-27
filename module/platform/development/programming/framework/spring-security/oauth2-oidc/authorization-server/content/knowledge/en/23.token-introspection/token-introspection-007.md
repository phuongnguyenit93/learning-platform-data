# Integrating a Resource Server Using Opaque Tokens

## 1. Context: Verifying Tokens via the Authorization Server

In an OAuth 2.0/OpenID Connect system using **Spring Security**, **Spring Authorization Server**, and Spring Boot, the Resource Server (RS) receives an access token from an OAuth client and decides whether the request is permitted to access an API.

If the access token is a JWT, the RS can verify the signature and claims locally using public keys from a JWK Set. With an **opaque access token**, the token string does not self-describe claims in a format that the RS can read and verify locally. The RS needs to ask the Authorization Server (AS) about the token's status and metadata via **OAuth 2.0 Token Introspection**, standardized in RFC 7662.

Spring Security provides opaque token support to connect the RS to the Introspection Endpoint. The application configures the endpoint URI and the RS's own credentials; Spring sends the token to be inspected to the AS, reads the response, and creates an `Authentication` object for the `SecurityContext`.

For example, an ordering system has:

- **order-web**: OAuth client obtaining access tokens for users.
- **checkout-api**: Resource Server protecting the checkout API.
- **auth.example.com**: Authorization Server issuing and managing access tokens.
- **checkout-introspector**: dedicated client identity for the checkout API to authenticate when calling the Introspection Endpoint.

When `checkout-api` receives a request, it extracts the bearer token, sends the token to the AS via a protected POST form, and processes the request only when the token is active and API policies are satisfied.

This lesson focuses on integrating a **Resource Server using opaque tokens** in Spring Security, from dependencies and configuration to authorities, audience, custom introspectors, timeouts, caching, error handling, and testing.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the opaque token flow from an HTTP request to the Introspection Endpoint.
2. Configure Spring Boot with the `introspection-uri`, `client-id`, and `client-secret` properties.
3. Enable opaque token support in `SecurityFilterChain`.
4. Distinguish the introspection client credential from the access token being inspected.
5. Understand `OpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, and `BearerTokenAuthentication`.
6. Map scopes to authorities and protect endpoints.
7. Add audience checks or custom policies using a custom introspector.
8. Handle opaque tokens in controllers and method security.
9. Design caching, timeouts, retries, circuit breakers, and failure policies.
10. Test active/inactive tokens, scope, audience, requester authentication, and AS outages.

## 2. Opaque Tokens and Introspection in Architecture

Opaque tokens are typically random identifier strings containing no claims in a format the RS can decode locally. The AS stores or manages token state in an authorization store and returns needed information when the RS introspects.

For example, an access token may look like:

~~~text
a4d6f7c8e9...opaque-random-token-value
~~~

The RS must not infer subject, audience, or expiry by splitting the token string itself. This data comes from the AS via the introspection protocol.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as checkout-api
    participant AS as Authorization Server
    participant DB as Authorization Store

    C->>RS: GET /checkout + Authorization: Bearer token
    RS->>RS: Extract bearer token
    RS->>AS: POST /oauth2/introspect<br/>client authentication + token
    AS->>AS: Authenticate introspection client
    AS->>DB: Look up token and authorization state
    DB-->>AS: Status and metadata
    AS-->>RS: active + scope/aud/sub/exp...
    RS->>RS: Build Authentication and check permissions
    RS-->>C: Process API or return error
~~~

### 2.1. Spring Security Components

| Component | Responsibility |
|---|---|
| BearerTokenAuthenticationFilter | Reads the bearer token from the request and initiates authentication |
| BearerTokenAuthenticationToken | Carries the bearer credential to `AuthenticationManager` |
| OpaqueTokenAuthenticationProvider | Calls the introspector and builds `Authentication` |
| OpaqueTokenIntrospector | Sends the token to the AS, processes the response, and builds the principal |
| OAuth2AuthenticatedPrincipal | Represents the principal along with attributes/authorities |
| BearerTokenAuthentication | The `Authentication` placed in `SecurityContext` upon success |
| AuthorizationManager | Evaluates authorities/endpoint access rules |

This is Spring Security's opaque token pipeline. You do not need to write custom controllers calling introspection in every endpoint; integrating into the authentication pipeline lets existing authorization rules work consistently.

### 2.2. Opaque Tokens Are Still OAuth Access Tokens

"Opaque" only describes how the token is represented to the client/RS. It does not change OAuth semantics:

- The token is still issued by the AS to a client and may represent a subject.
- The token still has scopes, audience, expiration, and revocation state.
- The client still sends the token via `Authorization: Bearer`.
- The RS must still verify scopes and business permissions after authenticating the token.

Do not confuse opaque tokens with session cookies or custom API keys.

## 3. Required Dependencies

For a Spring Boot servlet application, the common dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

This starter provides Spring Security Resource Server components and opaque token support. Manage versions through Spring Boot dependency management/BOM matching your project version.

If the application uses WebFlux, configuration and interfaces differ: use `ReactiveOpaqueTokenIntrospector` and `SecurityWebFilterChain`. This lesson covers the servlet stack with `HttpSecurity` and `OpaqueTokenIntrospector`.

## 4. Minimal Configuration via Spring Boot Properties

Once the starter is added, configure the Introspection Endpoint and the RS's credentials:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: checkout-introspector
          client-secret: CHECKOUT_INTROSPECTION_SECRET_FROM_SECRET_MANAGER
~~~

Meaning:

| Property | Meaning |
|---|---|
| introspection-uri | URL of the AS's Token Introspection Endpoint |
| client-id | OAuth client ID that the RS uses to authenticate with the endpoint |
| client-secret | Credential of the introspection client |

The value `CHECKOUT_INTROSPECTION_SECRET_FROM_SECRET_MANAGER` is an illustrative placeholder. Never commit real secrets to Git, never write them to configuration logs, and never use an end-user access token as the client secret.

### 4.1. Distinguishing the Two Credentials

In an API request flow, there are two distinct credentials:

1. **Caller's access token:** located in `Authorization: Bearer` and is the token the RS needs to verify.
2. **Introspection client's credential:** used by the RS to authenticate with the AS when calling `/oauth2/introspect`.

| Value | Who owns it? | Where is it used? |
|---|---|---|
| User/workload access token | OAuth client calling the API | `Authorization` header to RS; `token` form param to AS |
| `checkout-introspector` client ID/secret | Resource Server | Authenticates introspection requests to AS |

Never give the introspection client secret to external callers. Never use the introspected access token as a Basic credential.

### 4.2. What Spring Boot Auto-Configures

With the properties above and the right dependency, Spring Boot can create an introspector using the provided configuration. If the application has not declared its own `OpaqueTokenIntrospector` bean, auto-configuration provides a default introspector.

The default introspector sends the token to the endpoint using the configured credentials, checks the `active` response, and maps scopes to authorities prefixed with `SCOPE_`. The default principal is an `OAuth2AuthenticatedPrincipal`; the principal name is usually taken from the `sub` claim if present.

If the application declares a custom `OpaqueTokenIntrospector` bean, that bean replaces the auto-configured introspector. Understand this back-off behavior before adding a custom bean.

## 5. Enabling Opaque Tokens in SecurityFilterChain

Servlet Resource Server configuration:

~~~java
@Configuration
@EnableWebSecurity
class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().authenticated())
            .oauth2ResourceServer(resourceServer ->
                resourceServer.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

With Boot properties present, `Customizer.withDefaults()` uses the configured introspector. Requests carrying `Authorization: Bearer` pass through the opaque token authentication pipeline.

### 5.1. Do Not Just Enable authenticated() for Every Route

`authenticated()` only requires the token to be authenticated. If an endpoint needs a specific scope, enforce an authority such as `SCOPE_orders.read` or method security. Sensitive endpoints should follow deny-by-default rules rather than allowing any active token.

### 5.2. Securing Methods

You can enable method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Then:

~~~java
@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Order findOrder(String orderId) {
        // Check ownership/tenant in the domain layer.
        return loadOrder(orderId);
    }
}
~~~

Scopes are only coarse-grained permissions. Services must still verify that the caller is permitted to read the specific order/tenant.

## 6. Authentication Flow When a Request Hits the API

Suppose a client sends:

~~~http
GET /orders/123 HTTP/1.1
Host: checkout-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Spring Security performs these general steps:

1. `BearerTokenAuthenticationFilter` locates the bearer token.
2. `BearerTokenAuthenticationToken` is passed to `AuthenticationManager`.
3. `OpaqueTokenAuthenticationProvider` calls `OpaqueTokenIntrospector.introspect(token)`.
4. The introspector sends a request to the AS and processes the response.
5. If the token is active, the introspector returns an `OAuth2AuthenticatedPrincipal`.
6. The provider creates a `BearerTokenAuthentication` with the principal and authorities.
7. The `Authentication` is placed in `SecurityContextHolder`.
8. `AuthorizationManager` checks authorities for the endpoint.
9. If valid, the request reaches the controller; if permissions are lacking, Spring returns 403.

If the token is inactive or introspection fails verification per contract, authentication fails. Never synthesize a fake principal to let the request proceed.

### 6.1. Minimal Introspection Response

The AS may return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "order-web",
  "sub": "user-42",
  "aud": [
    "https://checkout-api.example.com"
  ],
  "exp": 1794825600,
  "iss": "https://auth.example.com"
}
~~~

This is an illustrative response under RFC 7662. The metadata set depends on the token and AS policy. `active` is the key field for the introspection client to determine whether the AS considers the token active.

### 6.2. Inactive Response

For an inactive token, the AS typically returns:

~~~json
{
  "active": false
}
~~~

The default Spring introspector rejects inactive tokens. There is no need to write custom logic parsing `active` in controllers. Never treat HTTP 200 as an active token; you must evaluate the boolean `active` in the response.

## 7. OpaqueTokenIntrospector and Principal

`OpaqueTokenIntrospector` is the core abstraction of Spring Security's servlet stack:

~~~java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
~~~

The method accepts a `String` token and returns a verified principal according to the introspection contract. If the token is inactive or the endpoint cannot provide a valid result, the implementation throws an exception instead of returning a fake active principal.

`OAuth2AuthenticatedPrincipal` provides:

- `getName()`: principal name.
- `getAttributes()`: metadata from the introspection response.
- `getAuthorities()`: authorities used for authorization.
- `getAttribute(name)`: retrieves a specific claim.

### 7.1. Accessing the Principal in a Controller

~~~java
@RestController
@RequestMapping("/api")
class CurrentIdentityController {

    @GetMapping("/identity")
    Map<String, Object> identity(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("name", principal.getName());
        result.put("subject", principal.getAttribute("sub"));
        result.put("clientId", principal.getAttribute("client_id"));
        return result;
    }
}
~~~

This example returns only a few attributes for illustration. Never return all token attributes from a public API; the introspection response may contain internal information or PII that the caller is not permitted to see.

### 7.2. Accessing BearerTokenAuthentication

You can inject `Authentication`:

~~~java
@GetMapping("/token-context")
Map<String, Object> tokenContext(
        BearerTokenAuthentication authentication) {

    return Map.of(
        "name", authentication.getName(),
        "authorities", authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
~~~

`BearerTokenAuthentication` can expose token attributes via `getTokenAttributes()`. Expose only validated and permitted fields; never return the raw token.

### 7.3. Principal Name Is Not Always the Client ID

By default, the principal name usually comes from `sub`. For user flows, that may be a user ID; for client credentials, it may represent a workload depending on the AS. If you need to distinguish the requesting client, read the AS-verified `client_id` claim.

Do not infer the subject by parsing an opaque token or taking a client ID from self-reported request headers.

## 8. Scopes Mapped to Authorities

Spring Security opaque token support reads the `scope` claim in the introspection response by default. Scopes are typically a space-delimited string:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel"
}
~~~

The corresponding generated authorities are:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Therefore, the configuration:

~~~java
.requestMatchers(HttpMethod.GET, "/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

matches the `orders.read` scope.

### 8.1. Scopes Are Not Automatic Roles

`orders.read` does not equate to `ROLE_ADMIN`. Do not map every scope to an administrative role. If the application has a dedicated `roles` claim, clearly define which issuer issues it, who may receive it, and which mapping is trusted.

### 8.2. Inspecting Actual Authorities

In tests or development environments, you can inspect:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

authentication.getAuthorities().forEach(authority ->
    log.debug("Granted authority: {}", authority.getAuthority()));
~~~

This snippet illustrates inspecting authorities; do not log tokens or all principal attributes. In production, metrics/audits should bound cardinality and identifying data.

## 9. Custom OpaqueTokenIntrospector: Checking Audience

By default, the introspector verifies active status and creates the principal. **Never assume `active=true` alone means every API may accept the token.** If the AS returns `aud` and the API has a distinct audience, the RS should check the audience per contract.

For example, the checkout API only accepts:

~~~text
https://checkout-api.example.com
~~~

You can wrap the default introspector:

Register a configuration properties record to bind the same three properties Spring Boot uses:

~~~java
@ConfigurationProperties(
    prefix = "spring.security.oauth2.resourceserver.opaquetoken")
public record IntrospectionClientProperties(
    String introspectionUri,
    String clientId,
    String clientSecret) {
}
~~~

Register the properties class and create a delegate introspector. The example below adds an audience check:

~~~java
@Configuration
@EnableConfigurationProperties(IntrospectionClientProperties.class)
class AudienceIntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            IntrospectionClientProperties properties) {

        OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector
                .withIntrospectionUri(properties.introspectionUri())
                .clientId(properties.clientId())
                .clientSecret(properties.clientSecret())
                .build();

        String expectedAudience = "https://checkout-api.example.com";

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            Object audience = principal.getAttribute("aud");
            boolean matches =
                audience instanceof String value
                    && expectedAudience.equals(value);

            if (audience instanceof Collection<?> values) {
                matches = values.contains(expectedAudience);
            }

            if (!matches) {
                throw new OAuth2IntrospectionException(
                    "Token is not intended for this resource server");
            }

            return principal;
        };
    }
}
~~~

This is a servlet API sample using the `SpringOpaqueTokenIntrospector` builder. Imports are omitted. When a custom bean is declared, Spring Boot no longer creates the default introspector; this bean must configure the endpoint and client credentials itself or wrap a configured delegate. If your project uses an older Spring Security version, the builder API may differ; check the documentation for your exact version before copying.

When a custom bean is declared, Spring Boot no longer creates the default introspector. This bean must configure the endpoint and client credentials itself or wrap a configured delegate.

### 9.1. Handling Audience as String or Collection

RFC 7662 allows audience metadata to be represented as a string or an array. Code must handle the exact data type the AS actually returns. Never use substring checks like `audience.contains("checkout")`, as that can match unintended identifiers.

If the response lacks `aud`, make an explicit policy decision:

- Reject if the API requires audience binding.
- Or use an alternative contract guaranteed by the AS, such as requester/resource-based introspection authorization.
- Never silently skip the check just to let requests pass.

### 9.2. Audience Does Not Replace Scope

Audience determines which API the token is intended for; scope determines which actions/permissions are granted. A token must satisfy both:

~~~text
aud contains https://checkout-api.example.com
AND
scope contains orders.read
~~~

A token with the right audience but missing scope must be rejected at the authorization layer. A token with the right scope but wrong audience must also be rejected.

## 10. Custom Authorities and Principal Mapping

Some AS implementations return custom claims such as `roles`, `permissions`, or `tenant_id`. You can wrap the delegate to add authorities, but only when those claims come from a trusted issuer with a well-defined schema.

Example adding roles from a `roles` claim:

~~~java
final class CustomAuthoritiesIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    CustomAuthoritiesIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        Object roles = principal.getAttribute("roles");
        if (roles instanceof Collection<?> values) {
            values.stream()
                .filter(String.class::isInstance)
                .map(String.class::cast)
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .forEach(authorities::add);
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
    }
}
~~~

This is an illustrative example; verify the claim schema and the application's role allowlist. Never convert arbitrary client-supplied values into authorities. If roles can change rapidly, consider an up-to-date authorization source instead of long-cached token metadata.

### 10.1. Do Not Overwrite Default Authorities

When wrapping the delegate, preserve the authorities already created by Spring from scopes if policy requires them. Creating a brand-new list solely from `roles` can accidentally drop `SCOPE_orders.read`.

### 10.2. A Tenant Claim Does Not Automatically Grant Tenant Access

A `tenant_id` claim can help establish tenant context, yet the service must still verify that the resource belongs to that tenant. Never read a tenant from a URL/body and overwrite the tenant in the principal.

## 11. Scope-Based Authorization and Business Data

An API should enforce checks across multiple layers:

1. Token is active and requester/resource binding is valid.
2. Audience includes the current API.
3. Scope/authority permits the operation.
4. Subject/client is permitted to access the specific record.
5. Tenant, state, and domain rules are all valid.

Example:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    OrderView getOrder(@PathVariable String id,
                       @AuthenticationPrincipal
                       OAuth2AuthenticatedPrincipal principal) {

        return orderService.findVisibleOrder(
            id,
            principal.getName(),
            principal.getAttribute("tenant_id"));
    }
}
~~~

`orderService.findVisibleOrder` must perform ownership/tenant checks in the domain layer. The scope annotation does not prove the user has permission to read every order.

### 11.1. Distinguishing 401 and 403

| Situation | Typical Result |
|---|---|
| No bearer token | 401 Unauthorized |
| Token inactive/invalid | 401 Unauthorized |
| Invalid introspection response | Authentication fails |
| Token active but missing scope | 403 Forbidden |
| Token active, sufficient scope, does not own record | 403 or 404 per anti-enumeration policy |
| Introspection AS temporarily unavailable | Infrastructure error per failure policy, possibly 503 |

Do not use 401 for all business errors. Clients should know when they need a new credential versus when the caller lacks permission.

## 12. Authorization Server Integration

Spring Authorization Server provides the Token Introspection Endpoint among its protocol endpoints. The endpoint is usually `/oauth2/introspect` when using the default path; the actual path depends on `AuthorizationServerSettings`.

On the Authorization Server, the configurer is applied to the `SecurityFilterChain` handling OAuth endpoints. Configuration skeleton example:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults());

    return http.build();
}
~~~

With the default Authorization Server configuration, the Token Introspection Endpoint is registered among the protocol endpoints. There is no need to write a custom controller replacing the standard endpoint. If you need to customize authentication providers or response handling, use the hooks published by your Spring Authorization Server version.

### 12.1. Authorization State Must Be Shared

The AS needs `OAuth2AuthorizationService` to look up tokens. This service must be consistent with where tokens are issued, refreshed, and revoked.

- In-memory store is suitable for simple demos/tests.
- JDBC store is suitable for deployments needing persistence when schema/transactions/indexes are properly configured.
- Custom stores must guarantee lookup, expiry, revocation, and cross-node consistency.

If a token is issued on node A while introspection on node B cannot see the authorization state, the RS may receive `active=false` for a valid token. With multiple instances, avoid per-process in-memory authorization stores.

### 12.2. Registering the Introspection Requester

The RS must be recognized by the AS as a protected resource/client. For example:

In `RegisteredClientRepository`, the AS must locate the requester's registration and verify its registered client authentication method, such as `client_secret_basic`, `private_key_jwt`, or mTLS. Client secrets must be encoded with the corresponding `PasswordEncoder`. `RegisteredClient` also models the authorization grants the client may use; do not add Client Credentials merely to illustrate introspection if the service does not need permission to request access tokens under that grant. Check `RegisteredClient` validation and registration policies in your exact version.

The AS must still have a policy allowing this client to introspect. Not every registered client automatically has permission to inspect every token. Depending on configuration, `private_key_jwt` or mTLS can be used instead of a shared secret.

### 12.3. Introspection Response Discloses Only Necessary Metadata

The AS should return `active` and the metadata the RS needs for authorization. Do not return the full user profile or sensitive claims if the checkout API does not need them.

You can restrict metadata by requester/resource—for example, returning only subject, audience, scope, client ID, and expiration. If a custom response policy is needed, use the version-appropriate extension point and test carefully not to break RFC 7662.

## 13. Customizing the Introspector and Endpoint Errors

A custom introspector can validate audience/resource, normalize or enrich authorities, map custom claims, bind the principal name per contract, and enforce additional tenant or token-type policies.

However, it must preserve the delegate's guarantees: client authentication to the AS, checking `active`, and handling error responses.

### 13.1. Distinguishing Inactive Tokens from AS Unavailability

| Result | Meaning |
|---|---|
| `active=false` | AS confirms the token is not active |
| HTTP 401 from AS | Introspection requester credentials may be wrong/expired |
| HTTP 403 from AS | Requester is not permitted to introspect |
| HTTP 429 | Requester exceeded quota |
| HTTP 5xx | AS or dependency failure |
| Timeout/network failure | Unable to verify token |
| Response violates schema | Introspection result cannot be trusted |

Never turn a timeout into an active principal. If introspection fails, authentication must not succeed simply because the RS wants higher availability.

### 13.2. Error Mapping Depends on Configuration

Spring Security handles exceptions from the introspector inside the authentication pipeline. The final HTTP status depends on the exception type, entry point, and application configuration. Test actual behavior for inactive tokens, requester credential failures, and AS outages; never assume every error returns the same 401 or every error returns 503.

If you want to return 503 for an AS outage to distinguish dependency failures from wrong credentials, configure exception translation/entry points properly without leaking internal details.

## 14. Timeouts, Retries, and Circuit Breakers

Introspection is a network dependency on the authentication path. If the AS slows down, API requests slow down too. Design connect timeouts, response/read timeouts, total request deadlines, bounded connection pools, bounded retries, circuit breakers/bulkheads, and latency metrics.

The builder/client APIs for configuring timeouts vary by Spring Security version. Recent Spring Boot versions support customizing the introspector builder via a builder customizer; if you need full control, create a custom introspector with an explicitly configured HTTP client. Check the public API of your exact version before copying configuration.

### 14.1. Never Retry Infinitely

A single API request can trigger multiple introspection calls if the client retries the API request itself. Combining retries at the gateway, RS, and HTTP client can multiply load. Retry only appropriate transient errors, with backoff/jitter and an overall deadline.

### 14.2. Bulkhead

Limit concurrent introspection calls so a slow AS does not exhaust all servlet threads or connection pools. When the bulkhead is full, reject in a controlled manner and observe metrics; do not create an unbounded queue.

## 15. Introspection Caching in the Resource Server

Do not blindly cache introspection responses by default. Caching can reduce latency and AS load, yet it delays visibility of revocations.

### 15.1. Positive Cache

Caching `active=true` requires safe keys and TTLs:

- Keys use a hash/fingerprint of the token; never store raw tokens in visible keys.
- TTL does not exceed remaining time until `exp` if the response has an expiry.
- TTL does not exceed the product's revocation freshness SLO.
- If the response depends on requester/audience/tenant, that context must be part of the cache key.
- Never share token A's principal for token B.
- Provide an eviction/clear mechanism when needed.

For example, if revocations must be detected within at most 15 seconds, a positive cache cannot have a 5-minute TTL and still claim to meet that SLO.

### 15.2. Negative Cache

Briefly caching `active=false` can reduce load when receiving junk tokens, but caching too long can reject newly issued tokens or tokens still synchronizing into the store. Use a small TTL, fingerprint keys, and test eventual consistency.

### 15.3. Caching Does Not Replace the Introspection Contract

HTTP introspection responses include `Cache-Control: no-store` and `Pragma: no-cache`. This prevents intermediaries/browsers from caching sensitive responses. An internal cache in the RS is a separate stateful application decision requiring explicit TTL, encryption/access control, invalidation, and observability.

Never cache timeout errors as `active=true`. During AS unavailability, only use still-valid positive cache entries if policy permits.

## 16. Security and Privacy

- Call the Introspection Endpoint over HTTPS/TLS and verify the AS certificate.
- Use dedicated credentials per Resource Server or workload group.
- Never let callers choose the introspection URL.
- Never send tokens via URL query strings.
- Never log access tokens, refresh tokens, Basic headers, or request bodies.
- Limit request body size and token length.
- Rate limit introspection by authenticated requester.
- Return only the metadata needed by the resource.
- Rotate introspection credentials and maintain a revocation procedure upon compromise.
- Protect the authorization store and audit logs.

### 16.1. Token Fingerprints for Auditing

If you need to correlate introspection events without storing tokens, use a one-way hash or the `jti` identifier from verified metadata. Choose appropriate algorithms, secret salts/keys (if using a keyed hash), retention, and access controls.

Never use raw tokens as metric labels or log fields. A token is a bearer credential; anywhere a token is stored becomes an attack surface.

### 16.2. Audience and Tenant

If the AS returns `aud`, the RS must verify the token is intended for the current API. In multi-tenant systems, check tenant context from trusted metadata and match it against the resource. Never allow callers to send a tenant header to override the tenant confirmed by the AS.

## 17. Integration Testing

### 17.1. Token and Authorization Matrix

| Scenario | Expected Result |
|---|---|
| Active token, right audience, sufficient scope | Request permitted |
| Active token, right audience, missing scope | 403 |
| Active token, wrong audience | Rejected per audience policy |
| Inactive token | 401 |
| Expired/revoked token | AS returns inactive, RS rejects |
| Missing `Authorization` header | 401 for endpoints requiring authentication |
| Unsupported auth scheme | Not authenticated |
| Introspection response missing `active` | Authentication fails |
| `active` is not a boolean | Invalid response, rejected |
| Valid subject but does not own record | Domain authorization denies |
| Tenant mismatch | Rejected per policy |

### 17.2. Requester and Dependency Matrix

| Scenario | Result to Prove |
|---|---|
| Valid introspection client credentials | AS authenticates requester |
| Wrong introspection secret | Introspection request rejected |
| Unauthorized requester | AS rejects per policy |
| AS timeout | No active `Authentication` created |
| AS returns 5xx | Failure policy executed |
| AS returns 429 | Client avoids retry storm |
| Invalid TLS certificate | RS does not send token to untrusted endpoint |
| Valid positive cache entry | Usable per policy |
| Positive cache TTL expired | Re-introspects |
| Token revoked within cache window | Delay stays within revocation SLO |
| Multi-instance authorization store | Nodes observe consistent state as designed |

### 17.3. Testing with MockMvc

An endpoint test can simulate an opaque token via a custom test introspector:

~~~java
@Test
void requestWithRequiredScopeIsAllowed() throws Exception {
    mockMvc.perform(get("/orders/123")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer test-opaque-token"))
        .andExpect(status().isOk());
}
~~~

This test only verifies the filter chain/authorization once the test introspector returns a principal with the required authority. Separate integration tests must call a real test AS or a mock HTTP introspection server to verify the form request, client authentication, and response parsing.

Never use dummy test tokens to conclude that the production RFC 7662 endpoint is secured.

## 18. Observability and Operations

### 18.1. Metrics

Monitor:

- Introspection requests/second by RS requester.
- Active/inactive ratio.
- HTTP 400/401/403/429/5xx counts.
- p50/p95/p99 introspection latency.
- Timeouts and connection pool usage.
- Cache hits/misses/age.
- Audience/scope authorization failures.
- Time from revocation until RS rejects the token.
- Credential rotation and authentication failures.

Never use raw tokens, subject PII, or arbitrary token values as metric labels.

### 18.2. Audit Events

Events may include:

- `OPAQUE_TOKEN_AUTHENTICATED`
- `OPAQUE_TOKEN_REJECTED`
- `INTROSPECTION_CLIENT_AUTH_FAILED`
- `INTROSPECTION_DEPENDENCY_UNAVAILABLE`
- `OPAQUE_TOKEN_AUTHORIZATION_DENIED`

Audits should include correlation ID, authenticated requester client, outcome, error category, endpoint, timestamp, and pseudonymized token fingerprint when needed. Never record raw access tokens or Basic credentials.

### 18.3. Runbook When RS Suddenly Returns 401

1. Check whether the token is actually active at the AS.
2. Check the introspection URI and TLS.
3. Check whether the introspection requester's secret/client ID was rotated or misconfigured.
4. Check whether the AS returns a proper JSON boolean `active`.
5. Check the authorization store and consistency across nodes.
6. Check audience/scope mapping and any custom introspector.
7. Check exception translation/entry points.
8. Check whether the cache is holding stale results.

Never fix errors by letting all tokens pass when the AS is unavailable or by disabling audience/scope validation.

## 19. Production Deployment Checklist

- [ ] Appropriate Spring Boot Resource Server dependency for servlet/reactive stack is present.
- [ ] Introspection Endpoint URI is configured properly.
- [ ] Introspection client ID/secret is protected in a secret manager.
- [ ] RS authenticates AS over HTTPS/TLS.
- [ ] `SecurityFilterChain` enables `opaqueToken`.
- [ ] Introspection credentials are never confused with the caller's access token.
- [ ] Introspection response must contain boolean `active` true.
- [ ] Scopes are mapped and enforced per endpoint.
- [ ] Audience/resource is checked per API contract.
- [ ] Tenant/ownership is checked in the domain layer.
- [ ] Custom introspector wraps the delegate and preserves active validation.
- [ ] AS issuance/revocation/introspection share consistent authorization state.
- [ ] Cache TTL obeys expiry and revocation SLO.
- [ ] Timeouts, connection pools, retries, circuit breakers, and bulkheads are bounded.
- [ ] AS outages never automatically treat tokens as active.
- [ ] Tokens, secrets, Basic headers, and sensitive raw introspection responses are never logged.
- [ ] Tests cover active/inactive, audience, scope, requester auth, TLS, outage, and caching.
- [ ] Metrics/audits and an incident runbook are in place.

### Core Takeaways

**An opaque token Resource Server uses introspection to ask the Authorization Server about the status and metadata of an access token.** Spring Boot can auto-configure it using the three properties `introspection-uri`, `client-id`, and `client-secret`; Spring Security integrates via `opaqueToken()` in `SecurityFilterChain`.

Spring invokes `OpaqueTokenIntrospector`, checks `active`, creates an `OAuth2AuthenticatedPrincipal`, and maps scopes into authorities prefixed with `SCOPE_`. The application continues checking audience, scope, tenant, and business permissions. The credential used to call introspection is the Resource Server's own credential, independent of the caller's access token.

Introspection introduces a network dependency, so production requires timeouts, quotas, caching bounded by the revocation SLO, a failure policy, observability, and AS outage testing. **An active token does not mean a request is permitted**; final authorization still rests with the Resource Server.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot — OAuth2 Resource Server Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
