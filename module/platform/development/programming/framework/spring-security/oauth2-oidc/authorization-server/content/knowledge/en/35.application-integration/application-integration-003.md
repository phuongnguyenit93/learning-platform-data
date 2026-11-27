# Integrating a Resource Server via Introspection for Reference Tokens

## 1. Context: The Resource Server Needs to Know Whether a Token Is Still Valid

An OAuth 2.0 Resource Server receives an access token from a client via HTTP Bearer Authentication. Before returning data or performing an operation, it must determine whether the token was issued by the Authorization Server, is still valid, and is authorized to access the current resource.

There are two common ways to validate an access token:

- **Local validation:** The Resource Server locally verifies the signature and claims of a self-contained token, typically a JWT.
- **Token introspection:** The Resource Server sends the token to the Authorization Server's Introspection Endpoint to receive the current status and metadata of the token.

This lesson focuses on reference tokens (opaque tokens) and RFC 7662 Token Introspection. A reference token is an opaque random identifier string; the token's contents and permissions are stored at the Authorization Server. The Resource Server does not need to know the token's structure and instead queries the Authorization Server whenever authentication is needed.

In the Spring ecosystem:

- **Spring Authorization Server (SAS)** issues reference access tokens, stores authorizations, provides the Token Introspection Endpoint, and returns token metadata.
- **Spring Security Resource Server** extracts the Bearer token from the request, calls OpaqueTokenIntrospector, and creates an Authentication upon receiving a valid result.
- **The API application** uses scopes, audience, tenant, and business policies to decide whether the request is permitted to execute.

Introspection is useful when token revocation needs to take effect quickly across multiple Resource Servers. In return, API requests depend on connectivity to the Authorization Server and require careful design around load, timeouts, caching, and fail-closed behavior.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between reference tokens and self-contained JWT access tokens.
2. Explain the RFC 7662 protocol and the active field.
3. Configure SAS to issue REFERENCE access tokens.
4. Configure and protect the Token Introspection Endpoint.
5. Register a Resource Server as an authorized introspection client.
6. Configure Spring Security Resource Server using Boot properties.
7. Understand OpaqueTokenIntrospector and BearerTokenAuthentication.
8. Map scopes to authorities and protect endpoints.
9. Validate audience, issuer, and resource-level permissions.
10. Synchronize introspection with token revocation.
11. Design caching, timeouts, resilience, and fail-closed behavior.
12. Perform end-to-end testing, operations, and production troubleshooting.

## 2. Reference Tokens vs. Self-Contained Tokens

OAuth 2.0 does not mandate a specific format for access tokens. A token can be a reference string or a protected self-contained structure.

| Criterion | Reference / Opaque Token | Self-Contained Token (typically JWT) |
|---|---|---|
| Token contents | Unpredictable reference string | Signed or protected claims |
| Where metadata is stored | Authorization Server | Can reside directly inside the token |
| Verification | Queries Introspection Endpoint | Resource Server verifies signature and claims |
| Revocation | Can take effect on the next introspection | Typically requires denylist, token version, or introspection |
| Request latency | Incurs a network call to Authorization Server | Can be verified locally |
| Runtime dependency | Depends on introspection endpoint | Depends on key distribution/rotation |
| Metadata exposure | Client cannot read claims from the token | JWT payload is readable, though signature protects integrity |
| Caching | Caching delays revocation awareness | Caches keys/JWKS and local policies |

A reference token is not an OAuth grant type. It is an access token format. Clients still use Authorization Code, Client Credentials, or other grant types to obtain tokens.

### 2.1. Opaque Token Does Not Mean No Metadata

The Authorization Server still stores the subject, client, scopes, issuance time, expiration time, revocation status, and other metadata. A reference token merely hides that structure from the client and Resource Server.

When the Resource Server calls introspection, the Authorization Server can return the attributes needed for authentication and authorization.

### 2.2. When Should Introspection Be Used?

Introspection is suitable when access tokens must be centrally invalidated, multiple APIs need a single source of truth for token state, tokens carry sensitive information that should not be readable by clients, or user-state policies must be checked online. The system must accept the network cost and operate the Authorization Server with appropriate availability.

Local JWT validation is better suited when low latency, independent operation, and high throughput are priorities, and revocation windows can be controlled using short token TTLs or supplementary mechanisms.

## 3. Integration Architecture

~~~mermaid
flowchart LR
    C[OAuth2 Client] -->|Bearer reference token| RS[Spring Resource Server]
    RS -->|POST /oauth2/introspect| AS[Spring Authorization Server]
    AS --> STORE[(OAuth2AuthorizationService)]
    AS --> CLIENTS[(RegisteredClientRepository)]
    AS -->|active + scope + claims| RS
    RS -->|Authentication + authorities| API[API authorization]
~~~

Two types of client identity must be distinguished:

- The OAuth client that requested the access token. The **client_id** field in the introspection response typically identifies this client.
- The introspection caller, which is the Resource Server authenticating to the Introspection Endpoint. It uses its own credentials to prove permission to query token status.

Both roles could exist within the same application, but they should have separate client registrations and credentials to isolate permissions, auditing, and secret lifecycles.

### 3.1. Request Processing Flow for an API Call

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant RS as Resource Server
    participant AS as Authorization Server
    participant DB as Authorization Store

    C->>RS: GET /orders + Authorization: Bearer token
    RS->>RS: BearerTokenAuthenticationFilter extracts token
    RS->>AS: POST /oauth2/introspect + client authentication
    AS->>DB: Look up authorization and token metadata
    DB-->>AS: Token state, scopes, subject, expiry
    AS-->>RS: active=true + metadata
    RS->>RS: Validate audience and build authorities
    RS->>RS: AuthorizationManager checks scope
    RS-->>C: 200 OK or 403 Forbidden
~~~

If the token does not exist, has expired, is not yet valid, has been revoked, or is not permitted for use at that Resource Server, the Authorization Server returns **active: false**. Spring Security rejects Bearer token authentication.

## 4. What Does RFC 7662 Define?

RFC 7662 defines a protocol for a Protected Resource to query an Authorization Server about the current state and metadata of an OAuth token.

An introspection request uses HTTP POST with an **application/x-www-form-urlencoded** body. The required parameter is **token**; **token_type_hint** is optional.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CLIENT
Accept: application/json
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

The endpoint must be protected with TLS and must require authentication for the Resource Server. If the endpoint is unprotected, an attacker could try many token values to probe for valid tokens.

### 4.1. The active Field

**active** is a required field in the introspection response:

- **true:** The Authorization Server confirms the token is currently active under its policy.
- **false:** The token is inactive, does not exist, is invalid, or the Resource Server is not authorized to know the token's status.

An inactive response should contain only **active: false**, avoiding leaking whether the token exists or why it is invalid.

### 4.2. Common Metadata Fields

| Field | Meaning |
|---|---|
| active | Token status |
| scope | Space-separated list of scopes |
| client_id | Client that requested the token |
| username | Human-readable identifier for the resource owner, if available |
| token_type | Type of token, e.g. Bearer |
| exp | Expiration time, Unix timestamp |
| iat | Issued-at time |
| nbf | Time before which the token is not valid |
| sub | Subject of the token |
| aud | Intended resource or audience for the token |
| iss | Issuer of the token |
| jti | Token identifier |

Fields other than **active** are largely optional under RFC 7662. The Resource Server must agree on a contract with the Authorization Server and not assume every claim is always present.

### 4.3. Example Active Response

~~~json
{
  "active": true,
  "client_id": "orders-worker",
  "scope": "orders.read",
  "sub": "service-account-42",
  "aud": ["https://api.example.com/orders"],
  "iss": "https://auth.example.com",
  "token_type": "Bearer",
  "iat": 1784282400,
  "exp": 1784282700
}
~~~

This is an illustrative response. Actual values depend on the Authorization Server and token customizers. Do not assume SAS always returns every optional field.

## 5. Spring Authorization Server Issuing Reference Tokens

In Spring Authorization Server 1.5.8, **TokenSettings** defaults to **OAuth2TokenFormat.SELF_CONTAINED**, which typically produces a JWT when a JwtGenerator is present. To issue reference tokens, configure **OAuth2TokenFormat.REFERENCE** on the corresponding RegisteredClient.

~~~java
RegisteredClient ordersWorker = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("orders-worker")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .scope("orders.write")
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

This is a machine-to-machine example. If the client uses Authorization Code, configure the grant and redirect URI accordingly; the key setting for this lesson is **accessTokenFormat(REFERENCE)**.

### 5.1. REFERENCE Is Configured per RegisteredClient

Each RegisteredClient can have its own TokenSettings. One Authorization Server can issue JWTs for one client and reference tokens for another.

This enables migrating API by API or client group by client group. A Resource Server receiving tokens must be configured for the corresponding format and verification method.

### 5.2. How Are Reference Access Tokens Generated and Stored?

**OAuth2AccessTokenGenerator** creates the reference access token. The token is a reference string pointing to metadata stored in **OAuth2Authorization**. **OAuth2AuthorizationService** is the authorization store used by token issuance, introspection, and revocation.

In production:

- Use JdbcRegisteredClientRepository or an equivalent durable storage implementation.
- Use JdbcOAuth2AuthorizationService or a shared store with appropriate consistency.
- Do not use InMemoryRegisteredClientRepository or InMemoryOAuth2AuthorizationService for multi-node production clusters.
- Ensure all Authorization Server nodes read/write the same resilient state store.

## 6. Configuring the Token Introspection Endpoint in SAS

Spring Authorization Server provides the Token Introspection Endpoint. The default endpoint is **/oauth2/introspect**, which can be changed via **AuthorizationServerSettings**.

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .tokenIntrospectionEndpoint("/oauth2/introspect")
        .build();
}
~~~

**AuthorizationServerSettings** is a required configuration component of the Authorization Server. If the endpoint is not overridden, SAS uses the default path.

### 6.1. Built-in Components in Authorization Server Configuration

When using **OAuth2AuthorizationServerConfigurer**, SAS registers **OAuth2TokenIntrospectionEndpointFilter** along with default components:

- **OAuth2TokenIntrospectionAuthenticationConverter** reads the request.
- **OAuth2TokenIntrospectionAuthenticationProvider** processes introspection.
- Success handler returns **OAuth2TokenIntrospection**.
- Error handler returns an OAuth2 error response.

The default provider uses **RegisteredClientRepository** to authenticate the client and **OAuth2AuthorizationService** to look up the authorization.

### 6.2. Minimal SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, Customizer.withDefaults());

    return http.build();
}
~~~

This example uses SAS's default endpoints. If the application already has an Authorization Server filter chain, maintain a unified configuration and verify that the introspection endpoint is not blocked or accidentally made public by another filter chain.

## 7. Authenticating the Resource Server When Calling Introspection

RFC 7662 requires the Protected Resource to authenticate when calling the Introspection Endpoint. By default, SAS requires client authentication at the Token Introspection Endpoint.

Client authentication methods supported by SAS include:

- client_secret_basic
- client_secret_post
- private_key_jwt
- client_secret_jwt
- tls_client_auth
- self_signed_tls_client_auth
- none for public clients

For a Resource Server calling introspection, use a confidential client with an authentication method capable of proving service identity. Do not use **none** for a production API authorized to query token status.

### 7.1. Separating Introspection Credentials from API-Calling Application Credentials

For example, **orders-worker** is the OAuth client requesting tokens to call the API; **orders-api-introspection** is the service identity that the API uses to call **/oauth2/introspect**.

Separating the two credentials lets you rotate the Resource Server secret without impacting external clients, revoke introspection rights for an API independently, accurately audit which service queried token status, and avoid using frontend client credentials to call internal endpoints.

Register the introspection caller in **RegisteredClientRepository** with an appropriate client authentication method. Store the encoded secret using SAS's **PasswordEncoder** and distribute the raw secret to the Resource Server via a secret manager.

### 7.2. Restricting Introspection Permissions

RFC 7662 recommends that the Authorization Server only allow authorized Protected Resources to call this endpoint. If multiple APIs share an Authorization Server, define which API may introspect tokens for which resources.

Do not treat successful client authentication as a reason to return full metadata for every token. Customize **OAuth2TokenIntrospectionAuthenticationProvider** or response handling to enforce policies by client, resource, and permitted disclosures.

## 8. Restricting Audience of Reference Tokens

**active: true** does not automatically mean a token is suitable for every API. A token may still be valid yet issued for a different Resource Server.

For APIs requiring resource isolation, use explicit audiences. RFC 7662 defines **aud** as one or more intended recipients of the token. The Authorization Server must verify that the token is intended for use at the introspecting Resource Server.

### 8.1. Adding Audience to Opaque Access Tokens

SAS supports **OAuth2TokenCustomizer<OAuth2TokenClaimsContext>** to add claims to opaque access tokens. For example, mapping a client to the Orders API:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> accessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "orders-worker".equals(
                    context.getRegisteredClient().getClientId())) {

            context.getClaims().claim(
                "aud",
                List.of("https://api.example.com/orders"));
        }
    };
}
~~~

This is an illustrative policy. In a multi-resource system, the audience must be computed from server-side policies or verified resource indicators. Do not take an arbitrary **aud** value from a client request and place it directly into the token.

Claims of an opaque token are stored with the authorization and can be used in the introspection response. Test SAS's actual response to ensure **aud** is returned with the exact type and values expected by the Resource Server. If the application declares its own **OAuth2TokenGenerator** instead of using the default generator, attach the access-token customizer to **OAuth2AccessTokenGenerator** inside **DelegatingOAuth2TokenGenerator**; merely declaring a customizer bean does not automatically wire it into a custom generator.

### 8.2. Authorization Server Must Check the Target Resource

When audiences are present, the Authorization Server must identify the introspecting Resource Server and return **active: true** only if the token is permitted at that resource. RFC 7662 requires the Authorization Server to perform applicable resource-specific checks. Adding the **aud** claim to the token only provides data for checking; it does not automatically enforce introspection policy.

SAS's default provider handles authorization and token state. If you need to restrict an introspection caller to querying only specific audiences or resources, implement a custom policy with an **AuthenticationProvider** and register it via **tokenIntrospectionEndpoint(...).authenticationProviders(...)**. Do not rely solely on client authentication or on the Resource Server checking the **aud** claim itself.

If a token lacks an audience while the system needs API separation, add an audience contract before taking the token to production. Do not treat scope as a complete substitute for audience: scope describes permissions, while audience identifies where those permissions apply.

## 9. Configuring Spring Boot Resource Server

With Spring Boot, the minimal configuration consists of the Introspection URI and the Resource Server's credentials:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: SECRET_FROM_SECRET_MANAGER
~~~

The minimal dependency for opaque Bearer tokens is **spring-boot-starter-oauth2-resource-server** in Spring Boot or **spring-security-oauth2-resource-server** when managing dependencies manually.

Spring Boot auto-configures **OpaqueTokenIntrospector** and the Resource Server filter chain from these properties. The secret in the example is a placeholder; production must obtain it from a secret manager, environment secret injection, or an appropriate credential management mechanism.

### 9.1. Do Not Confuse introspection-uri with token-uri

- **introspection-uri** is the endpoint where the Resource Server queries token status.
- **token-uri** is the endpoint where an OAuth client exchanges a grant for tokens.

The Resource Server in this lesson does not request access tokens on each API call. It receives tokens from clients and sends them to the introspection endpoint.

### 9.2. Customizing SecurityFilterChain

If the application defines its own **SecurityFilterChain**, opaque token support must be enabled:

~~~java
@Bean
SecurityFilterChain resourceServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()));

    return http.build();
}
~~~

Once a custom SecurityFilterChain is declared, do not assume Boot still applies default configuration to every endpoint. Inspect matchers, filter chain ordering, and authorization rules.

## 10. Processing Flow in Spring Security

Spring Security uses the following key components:

1. **BearerTokenAuthenticationFilter** extracts the access token from the Authorization header.
2. The filter creates a **BearerTokenAuthenticationToken**.
3. **AuthenticationManager** delegates the request to **OpaqueTokenAuthenticationProvider**.
4. The provider calls **OpaqueTokenIntrospector**.
5. The introspector sends the token to the endpoint and reads the response.
6. If the token is active, the provider creates a **BearerTokenAuthentication**.
7. The Authentication is stored in **SecurityContextHolder**.

By default, the principal is **OAuth2AuthenticatedPrincipal**. Authorities include scopes converted into authorities with the **SCOPE_** prefix and the bearer factor authority.

### 10.1. Token Sent in the Header

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer OPAQUE_ACCESS_TOKEN
Accept: application/json
~~~

Do not send access tokens in query strings, URL paths, or form parameters. Tokens in URLs are easily recorded in browser history, proxy logs, analytics, and Referer headers.

### 10.2. Accessing the Principal After Authentication

Controllers can receive **BearerTokenAuthentication** or **OAuth2AuthenticatedPrincipal**:

~~~java
@GetMapping("/whoami")
Map<String, Object> whoami(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    return Map.of(
        "subject", principal.getName(),
        "clientId", principal.getAttribute("client_id"),
        "scopes", principal.getAttribute("scope"));
}
~~~

**Authentication#getName** maps by default to the **sub** claim if present in the introspection response. With Client Credentials, the subject may represent a workload or client rather than an End-User. Do not assume every token represents a human user.

## 11. Mapping Scopes to Permissions

If the introspection response contains:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Spring Security creates authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Accordingly, the API should check specific scopes:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()));

    return http.build();
}
~~~

### 11.1. Method Security

Business methods can be protected using **@PreAuthorize**:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Order findOrder(String orderId) {
        // Load order and apply ownership/tenant checks.
        return ...;
    }
}
~~~

Scopes do not replace business authorization. The API must still check tenant, resource ownership, order state, and other domain policies.

### 11.2. Scopes Must Not Be Inferred from Client Identity

Do not grant permissions merely because **client_id** has the expected name or the token is active. Scopes in the introspection response must reflect the actual permissions granted by the Authorization Server, and the Resource Server must enforce scopes per endpoint.

If the API uses custom roles or permissions, map trusted claims to GrantedAuthority instances via a custom introspector. Do not trust arbitrary claims that the Authorization Server does not control.

## 12. Validating Audience with a Custom OpaqueTokenIntrospector

By default, Spring Security verifies **active** and maps scopes. If the API needs audience enforcement, add a validation layer after the delegate introspects successfully.

~~~java
public final class AudienceCheckingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Object audience = principal.getAttribute("aud");
        boolean accepted = false;

        if (audience instanceof String value) {
            accepted = this.expectedAudience.equals(value);
        } else if (audience instanceof Collection<?> values) {
            accepted = values.contains(this.expectedAudience);
        }

        if (!accepted) {
            throw new BadOpaqueTokenException(
                "The token is not intended for this resource server");
        }

        return principal;
    }
}
~~~

If the introspection response lacks **aud**, the wrapper rejects the token. This is an appropriate fail-closed choice when the API requires an audience. Before enabling this check, configure the Authorization Server to emit the audience claim and verify that the endpoint returns it.

### 12.1. Registering the Custom Introspector

For custom timeouts or audience checks, you can construct the delegate from application-injected URI and credentials:

~~~java
@ConfigurationProperties(
    "spring.security.oauth2.resourceserver.opaquetoken")
public record IntrospectionProperties(
    String introspectionUri,
    String clientId,
    String clientSecret
) {
}
~~~

Register this record using **@EnableConfigurationProperties(IntrospectionProperties.class)** or **@ConfigurationPropertiesScan**. The prefix and field names match the Boot properties in section 9, so you do not have to maintain two separate sets of credentials.

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        IntrospectionProperties properties) {

    OpaqueTokenIntrospector delegate =
        SpringOpaqueTokenIntrospector
            .withIntrospectionUri(properties.introspectionUri())
            .clientId(properties.clientId())
            .clientSecret(properties.clientSecret())
            .build();

    return new AudienceCheckingOpaqueTokenIntrospector(
        delegate,
        "https://api.example.com/orders");
}
~~~

Providing an **OpaqueTokenIntrospector** bean replaces Boot's auto-configured introspector. The new bean must retain the delegate to verify tokens via the Authorization Server; never construct a principal solely from the token string.

### 12.2. Validating the Issuer When Strict Binding Is Required

If the Resource Server uses multiple Authorization Servers or has distinct trust boundaries, you can also check **iss** after introspection. The introspection endpoint must be fixed in trusted configuration; never choose an endpoint based on unverified data from the token.

## 13. Custom Claim Mapping

Some APIs need to map **roles**, **permissions**, **tenant_id**, or **organization** claims. You can wrap the delegate and build a new principal with controlled authorities.

~~~java
public final class PermissionOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public PermissionOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Collection<GrantedAuthority> authorities =
            new ArrayList<>(principal.getAuthorities());

        Collection<String> permissions =
            principal.getAttribute("permissions");

        if (permissions != null) {
            permissions.stream()
                .map(permission ->
                    new SimpleGrantedAuthority("PERM_" + permission))
                .forEach(authorities::add);
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
    }
}
~~~

This example only illustrates how to map claims. In production, validate claim data types, constrain allowed values, and avoid granting administrative roles from client-controllable data.

Do not discard the authorities created by the delegate if **SCOPE_** authorities and the bearer factor are still needed. If replacing all authorities, explicitly reconstruct every authority required by application policies.

## 14. Distinguishing Scope, Audience, and Tenant

These three concepts answer different questions:

| Attribute | Question | Example |
|---|---|---|
| Scope | What actions is the token allowed to perform? | orders.read |
| Audience | Which API is the token allowed to be sent to? | https://api.example.com/orders |
| Tenant | Within which organization's scope is the request operating? | tenant-42 |

A token can have the **orders.read** scope while its audience is for the Billing API. The Orders API must reject that token.

A token can have the right audience and scope yet belong to a different tenant. The Resource Server must still verify the tenant from a trusted claim and compare it with the tenant on the resource/request according to policy.

Do not place a client-supplied tenant ID directly into the principal or treat it as proof of access rights. Token claims must be determined or verified by the Authorization Server from a trusted source.

## 15. Revocation and Token Lifecycle

A major benefit of introspection is that the Resource Server can recognize revoked tokens without waiting for a JWT to expire, provided the request is introspected again and caching is not overly long.

Spring Authorization Server includes a Token Revocation Endpoint. When a token is revoked, **OAuth2Authorization** and token metadata are updated in **OAuth2AuthorizationService**. Subsequent introspection calls can return **active: false**.

### 15.1. Revocation Flow

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant DB as Authorization Store
    participant RS as Resource Server

    C->>AS: POST /oauth2/revoke + token
    AS->>AS: Authenticate client
    AS->>DB: Mark token invalidated
    AS-->>C: 200 OK
    RS->>AS: POST /oauth2/introspect + same token
    AS->>DB: Read token state
    DB-->>AS: Token inactive
    AS-->>RS: {"active": false}
    RS-->>C: Reject next API request
~~~

### 15.2. Revocation Does Not Immediately Halt Every In-Flight Request

Introspection checks state when the Resource Server authenticates the request. Requests already authenticated before revocation may continue executing. If an API performs long-running sensitive operations, re-check authorization at transaction or domain-operation boundaries if necessary.

If the Resource Server caches positive introspection results, a revoked token may still be accepted until the cache entry expires. This trade-off must be explicitly defined in the security SLA.

### 15.3. Data Must Be Shared Across Nodes

If the Authorization Server runs across multiple nodes, all nodes must observe the same authorization state. If one node revokes a token while another introspection node reads from a separate in-memory store, it may return stale state.

Use a shared persistent authorization store and verify read-after-write consistency. When using read replicas with replication lag, factor revocation propagation delay into the security SLA.

## 16. Caching Introspection Responses

RFC 7662 allows Resource Servers to cache responses to reduce load and network latency. Caching reduces freshness of token state.

| Strategy | Advantage | Risk |
|---|---|---|
| No cache | Detects revocation on the very next request | Every request makes a network call |
| Short cache | Reduces load, small stale window | Revocation delayed up to TTL |
| Long cache | Maximizes throughput | Revoked tokens may remain accepted longer |

### 16.1. Safe Caching Rules

- Never cache responses longer than **exp**.
- If **exp** is absent, use a very short TTL with an explicit upper bound.
- Positive cache TTL must be shorter than the system's acceptable revocation window.
- Never turn network errors or timeouts into an **active: true** response.
- Never cache client authentication errors as if the token were inactive.
- Cache keys should be a hash/HMAC of the token, avoiding storing raw bearer tokens in keys or logs.
- If the Authorization Server returns different results per Resource Server, caches must isolate by resource/client context.
- Provide an invalidation mechanism upon receiving revocation events if the architecture supports it.

### 16.2. Caching Inactive Tokens

Inactive results can be cached briefly to mitigate token scanning and repeated invalid requests. Keep the TTL short so it does not mask newly issued tokens or state transitions after a legitimate workflow.

### 16.3. Do Not Assume Spring Security Caches Automatically

Spring Security's opaque token support invokes the introspector during the authentication flow. To enable caching, explicitly wrap **OpaqueTokenIntrospector** with a cache configured with an appropriate TTL and policy; do not rely implicitly on HTTP or proxy caching.

## 17. Timeouts, Retries, and Availability

Introspection sits on the API request-processing path. A slow or unreachable Authorization Server can increase API latency or prevent token validation.

Spring Security 6.5 defaults to a 30-second connection timeout and socket timeout for introspection calls. For latency-sensitive APIs, this value typically needs tuning to match the system's request budget.

### 17.1. Setting Explicit Timeouts

You can configure **RestTemplateBuilder** to set timeouts:

~~~java
@Bean
OpaqueTokenIntrospector introspector(
        IntrospectionProperties properties,
        RestTemplateBuilder builder) {

    RestOperations restOperations = builder
        .basicAuthentication(
            properties.clientId(), properties.clientSecret())
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(2))
        .build();

    return new SpringOpaqueTokenIntrospector(
        properties.introspectionUri(), restOperations);
}
~~~

Two seconds is only an example. Choose timeouts based on p95/p99 latency, network topology, retry policy, and remaining API request budget. Avoid overly long timeouts that exhaust thread pools during an Authorization Server outage.

### 17.2. Bounded Retries

Retries should apply only to transient errors and must include a deadline, backoff, and jitter. Do not retry unconditionally on every request; doing so can amplify an Authorization Server outage.

Wrong credentials or inactive tokens are not transient errors to retry. Never retry an invalid token hoping for an active response.

### 17.3. Circuit Breakers and Fail-Closed

When the introspection endpoint is unreachable:

- Do not accept a token based on a prior validation once the cache has expired.
- Do not fabricate **active: true**.
- Do not bypass the authentication filter.
- Return an appropriate service error while keeping the request unauthenticated.
- Shed load and recover via circuit breakers/backoff.

This is fail-closed behavior: the system may reject valid requests when the Authorization Server is disconnected, but never grants access based on unverifiable state.

## 18. Securing the Introspection Endpoint

The introspection endpoint receives bearer tokens in the body and returns data used to make access decisions. Protect this endpoint as a sensitive endpoint.

### 18.1. Transport Protection

- Expose only over HTTPS.
- Support TLS 1.2 or higher and verify server certificates.
- Do not disable hostname verification.
- Use a private network or service mesh where appropriate, while retaining TLS and client authentication.
- Restrict network-layer access to the endpoint to an allowlist of Resource Servers.

### 18.2. Protecting Client Credentials

- Use a separate credential for each Resource Server.
- Prefer **private_key_jwt** or mTLS when high assurance is required.
- When using client secrets, store them in a secret manager and enforce rotation schedules.
- Never log Authorization headers.
- Revoke client registrations when an API is decommissioned or credentials are compromised.

### 18.3. Protecting Token Data

- Accept only POST requests per RFC 7662.
- Never log token bodies in access logs, traces, or exception messages.
- Never send tokens in query parameters.
- Limit request body size and call rates per client.
- Do not return extra metadata for inactive tokens.
- Return only the claims needed by each Resource Server.

### 18.4. Rate Limiting and Anti-Token-Scanning

The introspection endpoint must authenticate the caller before looking up any token. Apply rate limits by client ID, trusted network IP, and resource identity. Monitor high inactive-token ratios, anomalous traffic, and client authentication failures.

Never use raw tokens as metric labels or log fields.

## 19. Introspection Responses and Privacy

The Authorization Server can return different metadata to different Protected Resources. For example, the Orders API only needs scopes and subjects relevant to Orders, not the token's permissions on the Billing API.

Define the response contract according to the principle of least privilege:

- **active** to determine validity.
- **scope** to check permissions.
- **sub** if the API needs the subject.
- **aud** to bind the resource.
- **exp** to bound caching and lifecycle.
- **client_id** for auditing or client policies.
- Tenant/organization claims only when the Resource Server genuinely needs them.

Do not return email, profile, organizational groups, or personal information merely because the token may carry those attributes. Introspection is not a UserInfo endpoint.

## 20. End-to-End Testing

Tests should exercise a real Authorization Server, authorization store, and Resource Server in an integration test environment. Mock introspectors are only suitable for testing isolated authorization rules; they do not verify the protocol contract or revocation propagation.

### 20.1. Token Issuance Tests

- RegisteredClient requiring reference tokens has **accessTokenFormat(REFERENCE)**.
- The client receives an opaque string access token.
- The authorization is persisted in **OAuth2AuthorizationService**.
- Scopes and audience are stored according to policy.
- Token TTL matches configuration.
- Other clients still receive token formats according to their own TokenSettings.

### 20.2. Introspection Tests

| Case | Expected Result |
|---|---|
| Active token with matching audience | active: true, Resource Server accepts |
| Non-existent token | active: false |
| Expired token | active: false |
| Revoked token | active: false |
| Token before nbf | active: false |
| Invalid client credentials | Endpoint rejects caller authentication |
| Caller not authorized to inspect token | active: false per policy |
| Response missing required audience | Custom introspector rejects |
| Insufficient scope | Token authenticated, API returns 403 |
| Authorization Server timeout | Request is not authenticated |

### 20.3. Revocation Propagation Tests

1. Obtain an access token.
2. Call the API and verify success.
3. Call the Token Revocation Endpoint.
4. Call the API again.
5. Verify introspection returns inactive and the API rejects the request.
6. If caching is enabled, measure the maximum window before the token is rejected.

### 20.4. Infrastructure Failure Tests

- Authorization Server unreachable.
- Expired or untrusted TLS certificate.
- Introspection secret rotated.
- Temporary authorization store outage.
- One SAS node misses a record due to replication lag.
- Malformed introspection response.
- Cache backend disconnected.
- Circuit breaker opens and then recovers.

## 21. Observability and Operations

Track total introspection requests by Resource Server client ID, active/inactive ratios, p50/p95/p99 latency, client authentication errors, timeouts, TLS errors, connection refused errors, malformed responses, API 401/403 counts, revocation propagation time, and cache hits/misses.

### 21.1. Safe Logging

Logs should include correlation ID, Resource Server client ID, accessed endpoint or resource, categorized active/inactive/error outcome, processing duration, and error category.

Never log raw bearer tokens, client secrets, Authorization headers, or entire introspection responses containing PII. If you need to correlate revocation events with tokens, use a token fingerprint generated with a protected-key HMAC.

### 21.2. Runbook When All APIs Start Returning 401

1. Check whether the client credentials used for introspection were rotated or expired.
2. Check whether the Token Introspection Endpoint is healthy and on the expected path.
3. Verify TLS certificates and hostnames.
4. Verify the Authorization Server can reach the authorization store.
5. Check whether the active response or scopes changed after a deployment.
6. Verify the Resource Server is using the right introspection URI/issuer.
7. Check whether the cache is holding old inactive results or stale responses.
8. Check clock synchronization if policies depend on exp/nbf.
9. Check audience and resource mappings if only one API is affected.

Never work around an outage by disabling introspection or accepting tokens when the endpoint is failing.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Forgetting accessTokenFormat(REFERENCE) | SAS keeps issuing default JWTs | Configure TokenSettings per RegisteredClient |
| Using a JWT decoder for reference tokens | Cannot verify tokens locally | Use opaque token introspection |
| Resource Server lacks client credentials | Introspection endpoint rejects requests | Register a confidential caller |
| Using frontend client credentials | Exposure of privileges or difficult auditing | Separate service identities |
| Checking only active | Token may have wrong audience or missing scope | Validate audience and authorization policies |
| Treating scope as audience | Token may be used against the wrong API | Enforce aud separately |
| Not persisting authorizations in production | Token state lost on restart or out of sync across nodes | Use a shared persistent OAuth2AuthorizationService |
| Caching positive results too long | Revoked tokens remain accepted | Short TTL bounded by exp and revocation SLA |
| Swallowing timeouts and treating token as active | Authentication bypass | Fail closed |
| Logging tokens | Leaks bearer credentials | Redact bodies and Authorization headers |
| Using GET for introspection | Tokens may leak into URLs/logs | Use POST form body only |
| Letting any client call introspection | Token scanning and metadata leakage | Authenticate, authorize, and rate-limit callers |
| Not testing revocation propagation | Unknown actual invalidation delay | End-to-end revocation tests |
| Using an in-memory authorization store in a cluster | Token state diverges across nodes | Use shared persistence |

## 23. Choosing Introspection vs. Local JWT Validation

| Architectural Question | Reference Token Introspection | Local JWT Validation |
|---|---|---|
| Need fast revocation? | Good fit, depending on cache | Needs extra mechanisms or short TTL |
| Acceptable network call per verification? | Yes | No |
| Want tokens not to expose claims? | Good fit | JWT payload is readable |
| Resource Server must work when AS is down? | No once cache expires | Possible |
| Centralized state management? | Yes | Must be added |
| High introspection load? | Needs AS scaling and careful caching | Less dependent on AS |
| Isolating multiple APIs? | Use audience/policy in introspection | Use aud claim and local validators |

No single choice fits every system. Some architectures use JWTs while still introspecting for online revocation checks. Spring Security's opaque-token support does not care whether a token is structured; it sends the token to the endpoint and uses the introspection result.

## 24. Production Deployment Checklist

### Authorization Server

- [ ] RegisteredClients needing reference tokens use OAuth2TokenFormat.REFERENCE.
- [ ] Access token TTL is bounded according to risk.
- [ ] OAuth2AuthorizationService uses a shared persistent store.
- [ ] RegisteredClientRepository uses a persistent store.
- [ ] Token Introspection Endpoint has a fixed path and issuer.
- [ ] Endpoint requires client authentication.
- [ ] Resource Server callers are registered with dedicated credentials.
- [ ] Callers are permitted to introspect only appropriate token scopes/resources.
- [ ] Responses return only required claims.
- [ ] Audiences are attached according to resource policy.
- [ ] Revocation updates the same authorization store.
- [ ] Endpoint enforces TLS and rate limiting.

### Resource Server

- [ ] Includes spring-security-oauth2-resource-server.
- [ ] introspection-uri points to a trusted endpoint.
- [ ] Introspection credentials are retrieved from a secret manager.
- [ ] Uses opaqueToken() in SecurityFilterChain.
- [ ] Scopes are mapped and enforced with SCOPE_ authorities.
- [ ] Audience is checked when the API requires resource isolation.
- [ ] Tenant and ownership checks are enforced at the domain layer.
- [ ] Timeouts match the latency budget.
- [ ] Introspection errors fail closed.
- [ ] Cache has explicit TTL and revocation SLA.
- [ ] Logs contain no tokens or secrets.

### Testing and Operations

- [ ] Test active, inactive, expired, and revoked tokens.
- [ ] Test invalid introspection caller credentials.
- [ ] Test audience mismatch and insufficient scopes.
- [ ] Test Authorization Server unavailability.
- [ ] Test revocation propagation across multiple nodes.
- [ ] Test stale cache and cache expiration.
- [ ] Dashboards monitor latency and active/inactive ratios.
- [ ] Alerts exist for abnormal spikes in authentication failures.
- [ ] Runbooks exist for credential, TLS, store, and cache failures.
- [ ] Process exists for rotating introspection client secrets.

### Core Knowledge

A reference token is a string referencing authorization metadata stored at the Authorization Server. With Spring Authorization Server, TokenSettings defaults to self-contained tokens; configure OAuth2TokenFormat.REFERENCE for RegisteredClients that should issue opaque tokens. SAS provides /oauth2/introspect, authenticates callers, and looks up tokens via OAuth2AuthorizationService.

Spring Security Resource Server uses OpaqueTokenIntrospector to send tokens to the endpoint. When the active response is true, the framework creates a BearerTokenAuthentication and maps scopes to SCOPE_ authorities. The API must still enforce audience, scopes, tenant, ownership, and business policies. Introspection supports detecting revocation on the next check; caching, timeouts, and network failures govern the latency and availability of this mechanism.

Production designs must separate Resource Server credentials from API-calling OAuth clients, enforce TLS, restrict introspection permissions, never log tokens, use a persistent authorization store, and fail closed whenever state cannot be verified. Test the full chain from token issuance to introspection, API authorization, and revocation.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html)
- [Spring Security 6.5 — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — SpringOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — OAuth2TokenFormat API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/OAuth2TokenFormat.html)
- [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospectionAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationProvider.html)
