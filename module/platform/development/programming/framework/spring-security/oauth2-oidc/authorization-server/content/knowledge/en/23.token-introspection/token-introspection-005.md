# OAuth2TokenIntrospectionEndpointConfigurer and Customization Points

In OAuth 2.0, a Resource Server needs to know whether an access token sent by a client is still valid or has expired, been revoked, or is not intended for that API. With a JWT, the Resource Server usually verifies the signature and claims itself. With an **opaque access token**, the token does not carry self-readable claims; the Resource Server needs to query the Authorization Server (AS) about its current state. The **OAuth 2.0 Token Introspection (RFC 7662)** protocol defines the endpoint for performing this lookup.

In Spring Authorization Server, **OAuth2TokenIntrospectionEndpointConfigurer** is the dedicated configuration point for the introspection endpoint. It allows customizing four stages of processing:

1. **Pre-processing:** convert the HTTP request into an Authentication object using an AuthenticationConverter.
2. **Main processing:** validate the introspection request and decide whether the token is active using an AuthenticationProvider.
3. **Success post-processing:** return `OAuth2TokenIntrospection` to the Resource Server using an AuthenticationSuccessHandler.
4. **Failure post-processing:** convert authentication/processing errors into an OAuth2 error response using an AuthenticationFailureHandler.

This lesson belongs to the **Introspection** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The goal of the module is to learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.

> **Key takeaway:** The introspection endpoint is not a login endpoint and does not issue new tokens. It accepts an existing token, authenticates the querying client, checks token state in the authorization store, and returns the required metadata to the proper Resource Server.

## 1. What Problem Does Token Introspection Solve?

Suppose `orders-api` receives an access token from `identity.example.com`. If the token is opaque, the API cannot read `sub`, `scope`, `exp`, or revocation status on its own. It sends the token to the AS's introspection endpoint:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

The AS authenticates the `orders-api` client, locates the corresponding authorization, evaluates the token state, and returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "client_id": "portal-web",
  "sub": "user-42",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iss": "https://identity.example.com",
  "iat": 1794850000,
  "exp": 1794850600,
  "token_type": "Bearer"
}
~~~

This is an illustrative response; actual values and claim sets depend on the AS, the token, and policies for the Resource Server. `client_id` in the example is the OAuth2 Client that requested the token, whereas the client authenticating at the introspection endpoint is the `orders-api` Resource Server.

If the token does not exist, is expired, has been revoked, or the Resource Server is not permitted to know about that token, a validly authenticated introspection request typically receives the response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

This is not an HTTP error. `active=false` is the business outcome of a valid introspection query. Returning the same response shape for non-existent tokens and tokens the caller is unauthorized to introspect reduces the ability to probe internal AS state.

### 1.1. Introspection Differs from JWT Signature Validation

| Criterion | JWT Validation at Resource Server | Token Introspection |
|---|---|---|
| Token data | JWT with claims and signature | Token can be opaque/reference |
| Primary verification location | Resource Server, using public key/validator | Authorization Server |
| Revocation status | Usually needs denylist, version, or extra check | AS can query current state |
| Network request per verification | Not required | Usually yes |
| Latency and AS dependency | Lower with offline verification | Depends on network and AS endpoint |
| State update responsiveness | Depends on auxiliary model | Can reflect new state faster, unless RS caches |
| Best suited for | Self-contained tokens, high throughput | Opaque tokens, centralized state checks |

Introspection can also be used for JWTs if the architecture requires the AS to be the authoritative source of state. However, merely because a JWT can be sent to the introspection endpoint does not mean the Resource Server must always do so.

### 1.2. Introspection Does Not Replace Business Authorization

`active=true` means the AS confirms the token is active and permitted for use in the evaluated context. That does **not automatically** allow every action on every record.

After introspection, the Resource Server still needs to check audience, scope/authority, tenant, owner, resource state, and business permissions. For example, a token with scope `orders.read` must not be allowed to call the order cancellation API even though `active` is true.

## 2. RFC 7662: HTTP Contract of the Introspection Endpoint

RFC 7662 specifies that the Resource Server sends an **HTTP POST** with an `application/x-www-form-urlencoded` body. The `token` parameter is required. `token_type_hint` is optional, helping the AS optimize lookup; if the AS does not find the token via the hint, it must still broaden its search across supported token types.

### 2.1. Request Parameters

| Parameter | Required | Meaning |
|---|---|---|
| token | Yes | The access token or refresh token value to introspect |
| token_type_hint | No | Hint of the token type, e.g., `access_token` or `refresh_token` |
| Extension parameters | No | Context sent by the Resource Server, if AS and RS share a custom contract |

Never send tokens via query strings. URLs can be written into access logs, proxy logs, browser history, or tracing systems. A POST body over TLS reduces the risk of tokens appearing in URLs; body redaction in logging middleware is still required.

### 2.2. Response and the active Claim

`active` is a required claim of type boolean. The definition of active depends on the AS, but typically means the token was issued by this AS, has not expired, has not been revoked/invalidated, is valid for the calling Resource Server, and is allowed to disclose metadata to that caller.

When `active=true`, the response can contain standard claims:

| Claim | Meaning |
|---|---|
| scope | List of granted scopes |
| client_id | Client that requested the token |
| username | Display name of the resource owner, if available |
| sub | Subject of the token |
| aud | Audience/resource receiving the token |
| iss | Issuer that issued the token |
| exp | Expiration time |
| iat | Issued-at time |
| nbf | Time before which the token is not valid |
| jti | Token identifier |
| token_type | Token type, e.g., Bearer |

Fields other than `active` are optional depending on the RFC and implementation. The AS may return additional claims under an agreed contract with the Resource Server. Do not send sensitive data simply because it is accessible from the authorization record.

### 2.3. Why Should Inactive Tokens Return Only active:false?

RFC 7662 recommends including no extra claims in responses for inactive tokens. If the response says a token expired, was revoked, does not exist, or belongs to another client, callers can use those differences to probe token state or infer internal details.

Therefore, tokens that are not found, expired, revoked/invalidated, or unauthorized for introspection can all return `active=false`. Never return `sub`, `client_id`, `exp`, or specific reasons in an inactive response.

### 2.4. Client Authentication Errors Differ from Inactive Tokens

| Situation | Appropriate Result |
|---|---|
| Resource Server authenticates properly, token inactive | HTTP 200 with `active:false` |
| Resource Server authenticates properly, token active | HTTP 200 with `active:true` and permitted claims |
| Invalid client authentication | HTTP 401 or authentication error per OAuth2 mechanism |
| Missing/malformed request | Appropriate request error |
| AS cannot reach authorization store | Server/availability error; do not pretend token is active |

Never turn database errors, timeouts, or internal errors into `active=true`. If the AS cannot determine token state, reject safely and log the incident.

## 3. Processing Flow in Spring Authorization Server

`OAuth2TokenIntrospectionEndpointConfigurer` configures `OAuth2TokenIntrospectionEndpointFilter`. The filter receives the HTTP request, converts it into an `Authentication` object, passes that object to `AuthenticationManager`, and then uses a success/failure handler to write the response.

~~~mermaid
flowchart TD
    A[POST /oauth2/introspect] --> B[Client Authentication Filter]
    B --> C{Resource Server client authenticated?}
    C -->|No| X[401 / OAuth2 client error]
    C -->|Yes| D[OAuth2TokenIntrospectionEndpointFilter]
    D --> E[AuthenticationConverter]
    E --> F[OAuth2TokenIntrospectionAuthenticationToken]
    F --> G[AuthenticationManager]
    G --> H[OAuth2TokenIntrospectionAuthenticationProvider]
    H --> I[OAuth2AuthorizationService]
    I --> J{Token active and caller allowed?}
    J -->|Yes| K[OAuth2TokenIntrospection active=true]
    J -->|No| L[OAuth2TokenIntrospection active=false]
    K --> M[AuthenticationSuccessHandler]
    L --> M
    M --> N[HTTP 200 JSON]
    H -->|AuthenticationException| O[AuthenticationFailureHandler]
    O --> P[OAuth2 error response]
~~~

There are two distinct authentication steps:

1. **Client authentication:** proves the caller is permitted to call the introspection endpoint.
2. **Token introspection:** evaluates the token the caller wants to inspect and decides whether that caller may receive metadata.

A token being inspected is not the credential used to authenticate the Resource Server at the introspection endpoint. The Resource Server needs its own dedicated credential.

### 3.1. Default Components

In Spring Authorization Server 1.5.x, the default endpoint filter uses:

| Stage | Default Component | Role |
|---|---|---|
| Parse request | OAuth2TokenIntrospectionAuthenticationConverter | Reads `token`, `token_type_hint`, and additional parameters |
| Main processing | OAuth2TokenIntrospectionAuthenticationProvider | Uses client registration and authorization service to process introspection |
| Success | Internal success handler | Returns `OAuth2TokenIntrospection` as JSON |
| Failure | OAuth2ErrorAuthenticationFailureHandler | Returns OAuth2 error response |

`OAuth2TokenIntrospectionAuthenticationProvider` is initialized with `RegisteredClientRepository` and `OAuth2AuthorizationService`. The authorization service is the data source for looking up authorizations and related tokens. Common implementations are `InMemoryOAuth2AuthorizationService` for development/testing and `JdbcOAuth2AuthorizationService` for persistence.

## 4. What Extension Points Does OAuth2TokenIntrospectionEndpointConfigurer Provide?

The configurer has six primary configuration methods:

| Method | Extension Type | When to Use? |
|---|---|---|
| introspectionRequestConverter(...) | Add AuthenticationConverter | Accept an extended request format |
| introspectionRequestConverters(...) | Access default and custom converter list | Change order, remove, or customize converters |
| authenticationProvider(...) | Add AuthenticationProvider | Handle a custom introspection authentication type |
| authenticationProviders(...) | Access provider list | Replace, wrap, or supplement the default provider |
| introspectionResponseHandler(...) | AuthenticationSuccessHandler | Customize success response, headers, auditing, or serialization |
| errorResponseHandler(...) | AuthenticationFailureHandler | Customize error responses and error auditing |

These extension points correspond to three processing layers: **pre-processing**, **main processing**, and **post-processing**. Choose the right layer for each change; for example, a converter only parses requests—it is not the place to decide whether a token is active.

## 5. Configuring the Endpoint in SecurityFilterChain

The example below uses the fluent configuration API of Spring Authorization Server 1.5.x:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenIntrospectionEndpoint(introspection -> introspection
                .introspectionRequestConverters(configureRequestConverters())
                .authenticationProviders(configureProviders())
                .introspectionResponseHandler(introspectionSuccessHandler())
                .errorResponseHandler(introspectionFailureHandler())
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is a configuration skeleton. You still need infrastructure beans such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, client authentication, and the remaining filter chains. If a stage does not need customization, keep the framework's default handler/converter/provider.

### 5.1. Configuring the Endpoint URI

By default the introspection endpoint is usually `/oauth2/introspect`. It can be changed via `AuthorizationServerSettings`:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .tokenIntrospectionEndpoint("/oauth2/v1/introspect")
        .build();
}
~~~

The public URL also depends on context path and reverse proxy configuration. Resource Servers must be configured to point to the exact HTTPS endpoint. If you change the endpoint, update Resource Server configuration and metadata/discovery accordingly.

### 5.2. Protecting the Endpoint with Client Authentication

The introspection endpoint must require authenticated/authorized callers. For a Resource Server, typically register a dedicated confidential client:

~~~java
RegisteredClient ordersApi = RegisteredClient.withId("orders-api-internal")
    .clientId("orders-api")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("token.introspect")
    .build();
~~~

This is an illustrative registration example. Having the `token.introspect` scope in the registration **does not automatically** cause Spring Authorization Server to restrict introspection permissions by that scope; appropriate policy enforcement must be added if desired. Client secrets must come from a secret manager, never hardcoded into source code or logs.

In production, you can use `private_key_jwt`, `tls_client_auth`, or `self_signed_tls_client_auth` depending on deployment capabilities. Never allow uncredentialed public clients to call the introspection endpoint as a public API.

## 6. Pre-processing: introspectionRequestConverter

The converter receives an `HttpServletRequest`, reads protocol parameters, and creates an `OAuth2TokenIntrospectionAuthenticationToken`. The default converter understands requests per RFC 7662. When adding extension parameters, preserve handling of `token` and `token_type_hint`.

### 6.1. When Is a Custom Converter Needed?

For example, suppose an organization wants the Resource Server to send an extra `resource_id` so the AS limits returned claims per API:

~~~http
POST /oauth2/introspect HTTP/1.1
Authorization: Basic RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_TOKEN&token_type_hint=access_token&resource_id=orders-api
~~~

`resource_id` is a custom extension between AS and RS, not a mandatory standard RFC 7662 parameter. The AS must verify that `resource_id` belongs to the authenticated caller; never trust an arbitrary value sent in the request body.

### 6.2. An Extension Converter Is Pre-Processing, Not Authorization

A custom converter can validate request structure, read additional parameters, normalize data, and construct an `OAuth2TokenIntrospectionAuthenticationToken` with `additionalParameters`.

A converter should not decide whether a token is active, trust `resource_id` without checking it against the client, bypass the authenticated client principal, query the token store to build a JSON response itself, or drop standard requests supported by the default converter.

### 6.3. Example Converter with an Additional Parameter (Pseudocode)

~~~java
// PSEUDOCODE: illustrates the extension point; adapt to your project's
// version and default converter before using in production.
AuthenticationConverter resourceAwareConverter = request -> {
    String token = request.getParameter("token");
    if (!StringUtils.hasText(token)) {
        return null;
    }

    Authentication clientPrincipal =
        SecurityContextHolder.getContext().getAuthentication();

    String tokenTypeHint = request.getParameter("token_type_hint");
    String resourceId = request.getParameter("resource_id");

    Map<String, Object> additionalParameters = new HashMap<>();
    if (StringUtils.hasText(resourceId)) {
        additionalParameters.put("resource_id", resourceId);
    }

    return new OAuth2TokenIntrospectionAuthenticationToken(
        token, clientPrincipal, tokenTypeHint, additionalParameters);
};
~~~

The snippet above illustrates the `OAuth2TokenIntrospectionAuthenticationToken` constructor; it is not a complete replacement for the default converter. If used directly, ensure malformed requests, duplicate parameters, body encoding, and client authentication conform to contract. A safer approach is to wrap/delegate to the default converter and enrich context after successful parsing.

### 6.4. Adding a Converter While Keeping the Default

The configurer lets you manipulate the converter list:

~~~java
private Consumer<List<AuthenticationConverter>> configureRequestConverters() {
    return converters -> {
        // Keep the default OAuth2TokenIntrospectionAuthenticationConverter.
        // Only add an extension converter when it can recognize custom requests.
        converters.add(0, resourceAwareConverter());
    };
}
~~~

If an extension converter does not handle a request, it should return `null` so the next converter can process it. Do not remove the default converter unless you have replaced its entire contract and have equivalent integration tests.

## 7. Main Processing: AuthenticationProvider

The `AuthenticationProvider` receives `OAuth2TokenIntrospectionAuthenticationToken` and performs the core processing. The default provider `OAuth2TokenIntrospectionAuthenticationProvider` is constructed from `RegisteredClientRepository` and `OAuth2AuthorizationService`.

Logically, the provider must confirm the introspection caller principal is an authenticated client, look up the token by value and token type hint, identify which authorization the token belongs to, verify the token is active/unexpired/uninvalidated, enforce policy on whether the current Resource Server may know about that token, and build `OAuth2TokenIntrospection` with `active` and permitted claims.

Do not conclude a token is active solely from finding a record. An authorization record can still exist in the database after its access token has expired or been invalidated.

### 7.1. OAuth2AuthorizationService Is the Central Data Source

`OAuth2AuthorizationService` manages OAuth2 authorizations and allows searching for tokens:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(tokenValue, OAuth2TokenType.ACCESS_TOKEN);
~~~

This is a service-layer lookup example, not code meant to replace the default provider. `findByToken` can return `null`; the token type hint can be `null` if the implementation needs to search across multiple token types. Lookup and state evaluation must follow the provider/version contract.

`OAuth2Authorization.Token` exposes states such as `isExpired()`, `isInvalidated()`, and `isActive()`. When building a custom provider, use actual token state and current policy; do not merely check `authorization != null`.

### 7.2. Token Type Hint Is Only a Hint

RFC 7662 specifies that `token_type_hint` is optional. If the AS cannot find the token under the hint, it must continue searching across supported token types. Never return `active:false` merely because a caller sent the wrong hint when the actual token belongs to another supported type.

### 7.3. Default Provider vs. Custom Provider

The configurer provides `authenticationProvider(provider)` to add a provider and `authenticationProviders(consumer)` to access the list of default and additional providers.

`OAuth2TokenIntrospectionAuthenticationProvider` in Spring Authorization Server 1.5.x is a `final` class with a constructor taking `RegisteredClientRepository` and `OAuth2AuthorizationService`; it does not have setters like `setAuthenticationValidator()` as some other grant providers do. Therefore, do not write code assuming you can subclass this provider or call a non-existent customizer method.

If a custom introspection policy is needed, you can add a provider for an extended `Authentication` type produced by a custom converter, wrap the default logic with a delegating provider, or replace the default provider with a custom implementation when you truly must alter semantics.

When a custom provider supports the same authentication type as the default provider, ordering in `AuthenticationManager` matters. Verify which provider runs first, which handles the request, and avoid creating a fallback that bypasses policy.

### 7.4. Example Configuring the Provider List

~~~java
private Consumer<List<AuthenticationProvider>> configureProviders() {
    return providers -> {
        // Example: register a provider specialized for a custom authentication type.
        // Do not remove the default provider unless the custom provider fully replaces
        // RFC 7662 token verification.
        providers.add(0, tenantAwareIntrospectionProvider());
    };
}
~~~

`tenantAwareIntrospectionProvider()` is an application-built bean. If the provider handles the same `OAuth2TokenIntrospectionAuthenticationToken` as the default provider, clearly define when it handles vs. delegates, and guarantee a request cannot fall through to another provider to bypass the tenant check.

## 8. Custom Response Claims and Restricting Returned Information

`OAuth2TokenIntrospection` is Spring Authorization Server's response model. Its builder lets you set `active`, `scope`, `clientId`, `subject`, `audience`, `issuer`, `expiresAt`, `issuedAt`, `notBefore`, `id`, `username`, and custom claims.

Example constructing the response model:

~~~java
OAuth2TokenIntrospection introspection =
    OAuth2TokenIntrospection.builder(true)
        .clientId("portal-web")
        .subject("user-42")
        .audience("orders-api")
        .scope("orders.read")
        .issuer("https://identity.example.com")
        .issuedAt(issuedAt)
        .expiresAt(expiresAt)
        .claim("tenant_id", "tenant-17")
        .build();
~~~

This example illustrates the model API, not code to replace the default provider. When adding claims, obtain values from the authorization record or a trusted data source—never directly from the caller's request.

### 8.1. When Should You Add Custom Claims?

Some valid cases: a Resource Server needs `tenant_id` to enforce isolation; an API needs assurance context if the token actually carries it; the system needs `authorization_id` or a non-sensitive internal identifier for correlation; the AS needs to return `cnf` for sender-constrained tokens per a supported contract.

Do not return email, phone number, address, or PII if the Resource Server does not need them; the full list of system-wide roles when the API only needs bounded scopes; consent contents or unrelated internal data; claims for inactive tokens; secrets, refresh tokens, client secrets, or key material details.

### 8.2. Restricting Responses per Resource Server

RFC 7662 permits the AS to return different responses to different Resource Servers. For example:

| Resource Server | Potentially Needed Claims |
|---|---|
| orders-api | `sub`, `aud`, `scope`, `tenant_id`, `exp` |
| billing-api | `sub`, `aud`, `scope`, `account_id`, `exp` |
| analytics-api | pseudonymized `sub`, `aud`, `scope`, `exp` |

To achieve this, the AS must identify the Resource Server via the authenticated client, check whether the token was issued for that resource, filter scopes/claims against an allowlist, avoid exposing tenants or subjects of other resources, and return `active:false` if the caller is not permitted to know the token's status by policy.

Do not use an `aud` self-declared in the request body as sole proof. Audience must be checked against claims/authorizations stored and verified by the AS.

### 8.3. Do Not Replace active with a Custom Status

You may add internal claims such as `risk_level` or `policy_version`, but never replace the required `active` claim. The Resource Server must have explicit rules for custom claims; otherwise, extra data only complicates the response without increasing security.

## 9. Success Post-Processing: introspectionResponseHandler

`introspectionResponseHandler` is an `AuthenticationSuccessHandler` that processes the authenticated result and writes the HTTP response. Use it when you need to customize response headers, attach a correlation ID, record safe audit metadata, apply a standardized serializer or response wrapper, or control cache headers.

### 9.1. The Handler Is Not Where Token Activity Is Decided

The success handler runs after `AuthenticationProvider` has succeeded. It should not look up tokens itself, check expiration itself, or flip an inactive token to active. That logic belongs in the provider/domain service.

### 9.2. Custom Response Handler (Pseudocode)

~~~java
AuthenticationSuccessHandler introspectionSuccessHandler() {
    return (request, response, authentication) -> {
        OAuth2TokenIntrospectionAuthenticationToken result =
            (OAuth2TokenIntrospectionAuthenticationToken) authentication;

        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");

        // The default protocol response handler is replaced here.
        // If serializing manually, return JSON claims compliant with RFC 7662,
        // preserve active, and do not disclose information outside policy.
        objectMapper.writeValue(
            response.getOutputStream(),
            result.getTokenClaims().getClaims());
    };
}
~~~

This is pseudocode illustrating custom serialization; properly inject `ObjectMapper`, set content type/status, handle exceptions, and handle response commitment. If you only need to add claims, handle that in the provider and keep the default success handler instead of rewriting HTTP serialization.

### 9.3. Cache Headers

Introspection responses contain security metadata and can change when a token is revoked. Do not allow intermediaries to cache responses by default. If you want the Resource Server to cache, design caching explicitly on the Resource Server side with an appropriate TTL—never rely on public browser/proxy caches.

## 10. Failure Post-Processing: errorResponseHandler

`errorResponseHandler` receives `OAuth2AuthenticationException` errors and produces the OAuth2 error response. It can be used to standardize logs/audits, attach request correlation IDs, map infrastructure errors to appropriate protocol errors, hide stack traces and internal details, and preserve the proper HTTP status and OAuth2 error contract.

Do not use the failure handler to turn an inactive token into HTTP 401. For an authenticated, syntactically valid introspection request, an inactive token is normally a `200` response with `active:false`.

Example failure handler:

~~~java
AuthenticationFailureHandler introspectionFailureHandler() {
    return (request, response, exception) -> {
        // Record metrics/audit using request ID and error code.
        // Never write tokens, client secrets, or stack traces to the response.
        oauth2ErrorResponseHandler().onAuthenticationFailure(
            request, response, exception);
    };
}
~~~

`oauth2ErrorResponseHandler()` is a placeholder for the application's standard OAuth2 handler. In real code, keep the default handler if no customization is needed; if writing your own, preserve status, error codes, and appropriate headers.

## 11. Client Authentication and Introspection Permissions

RFC 7662 requires the endpoint to have an authorization mechanism to prevent token scanning. Spring Authorization Server configures client authentication for the introspection endpoint. Commonly supported client authentication methods include `client_secret_basic`, `client_secret_post`, `client_secret_jwt`, `private_key_jwt`, `tls_client_auth`, and `self_signed_tls_client_auth` depending on configuration.

Resource Servers should not use uncredentialed public clients to query token status. In larger systems, register each Resource Server or API group with a dedicated identity, least-privilege introspection permissions, and independent auditing.

### 11.1. An Authenticated Client May Not Introspect Every Token

Authenticating `orders-api` only proves the caller is `orders-api`. The AS still needs to decide whether the token belongs to an issuer/realm/tenant this API may query, whether the token has a matching audience, whether the API may view sensitive claims, whether returned scopes should be restricted, and whether the caller is attempting to probe another client's or tenant's tokens.

If the token does not exist or the caller is not permitted to know its status, return `active:false` per policy to avoid leaking information.

### 11.2. Separate Introspection Credentials from API Call Credentials

The credential `orders-api` uses to call the introspection endpoint is a **Resource Server** credential. It is distinct from the user's access token being checked by the API. Never turn a user's access token into a client credential to introspect itself.

### 11.3. Never Log Tokens in Introspection Requests

The introspection body contains a token, which is a credential. Redact request bodies at reverse proxies, servlet filters, APM, and HTTP client logging; never put tokens in exception messages; never log Basic Authorization headers or client secrets; use correlation IDs without tokens; restrict retention of audits and security logs.

## 12. Resource Server Using the Introspection Endpoint

Spring Security Resource Server supports opaque tokens via `OpaqueTokenIntrospector`. With Spring Boot, you can configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-api
          client-secret: ORDERS_API_INTROSPECTION_SECRET_FROM_SECRET_MANAGER
~~~

In production, fetch the secret from a secret manager or secure configuration mechanism. Never commit secrets to `application.yml`.

### 12.1. SecurityFilterChain for the Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Spring Security uses `OpaqueTokenAuthenticationProvider` and `OpaqueTokenIntrospector` to call the AS, check `active`, and map scopes into authorities prefixed with `SCOPE_`. After authentication, the `Authentication` typically holds an `OAuth2AuthenticatedPrincipal`; controllers can read the attributes returned by introspection.

### 12.2. Using SpringOpaqueTokenIntrospector

You can declare a bean for direct configuration:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        IntrospectionClientProperties properties) {

    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(properties.introspectionUri())
        .clientId(properties.clientId())
        .clientSecret(properties.clientSecret())
        .build();
}
~~~

`IntrospectionClientProperties` is an application-defined configuration object loaded from a secret manager. If you provide an `OpaqueTokenIntrospector` bean or call `introspector(...)` in the DSL, Boot's auto-configuration for the introspector may be superseded.

### 12.3. Scopes Mapped to Authorities

If introspection returns:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

The Resource Server maps this by default to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Thus the `hasAuthority("SCOPE_orders.read")` rule matches the example. If you want to map different roles/permissions, intentionally use a custom introspector or authentication converter.

## 13. Customizing OpaqueTokenIntrospector on the Resource Server

`OpaqueTokenIntrospector` sits on the client side calling the introspection endpoint. It differs from `OAuth2TokenIntrospectionEndpointConfigurer` on the AS side:

| Component | Where does it live? | Responsibility |
|---|---|---|
| OAuth2TokenIntrospectionEndpointConfigurer | Authorization Server | Receives and processes introspection requests |
| OpaqueTokenIntrospector | Resource Server | Calls the endpoint and turns the response into an authenticated principal |
| OpaqueTokenAuthenticationProvider | Resource Server | Uses the introspector to authenticate Bearer tokens |
| OAuth2TokenIntrospectionAuthenticationProvider | Authorization Server | Looks up authorization/token and produces the introspection result |

Example of a custom introspector delegating to the Spring implementation and enriching authorities:

~~~java
final class CustomAuthoritiesIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    CustomAuthoritiesIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = this.delegate.introspect(token);

        Collection<GrantedAuthority> authorities =
            extractAuthorities(principal.getAttributes());

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(), principal.getAttributes(), authorities);
    }
}
~~~

`extractAuthorities(...)` is an application-implemented function. Never add authorities based solely on data sent by the request caller. Only map claims verified and returned by the AS in the response.

## 14. Caching Introspection: Performance and State Freshness

Introspection typically creates a network round trip to the AS for every token authentication. Caching at the Resource Server can reduce latency and load, but delays visibility of newly revoked tokens.

### 14.1. Trade-Offs

| Cache TTL | Pros | Risks |
|---|---|---|
| No cache | Latest state from AS on every request | Increases latency, load, and AS dependency |
| Very short | Balances performance and revocation freshness | Still has a brief stale window |
| Long | Greatly reduces introspection calls | Revoked tokens may remain accepted until cache expires |

### 14.2. TTL Must Be Bounded by Remaining Token Lifetime

If a token only has 20 seconds remaining while the cache TTL is 5 minutes, the Resource Server must not keep trusting the cache past `exp`. Effective TTL should be the minimum of:

~~~text
cacheTTL = min(configuredTTL, token.exp - now, revocationFreshnessBudget)
~~~

This is an illustrative design formula. If the response lacks `exp`, a short policy-defined TTL is required. Never cache active responses indefinitely.

### 14.3. Caching Inactive Responses

You can cache `active:false` briefly to curb token scanning and AS load, but bound cache size and prevent cache pollution from attackers sending random tokens. Never create cache keys by storing raw tokens in logs or metrics; use a secure hash appropriate for your system.

### 14.4. Do Not Fail-Open When the AS Errors

If the introspection endpoint times out or is unavailable, the Resource Server does not know whether the token is still active. For secure APIs, the default should reject requests or return an appropriate infrastructure error—never automatically treat tokens as active. You can use circuit breakers, bounded retries, timeouts, and stale caches under explicit policy; never use an unbounded stale cache.

## 15. Multi-Resource Server and Claim Restriction

An access token may be used across multiple resource boundaries, but not every Resource Server needs to know all token information. The AS should apply the principle of **minimum disclosure**.

~~~mermaid
flowchart LR
    T[Access token] --> AS[Authorization Server]
    AS --> O[orders-api introspection client]
    AS --> B[billing-api introspection client]
    AS --> A[analytics-api introspection client]
    O --> OR[claims: sub, aud, orders scope]
    B --> BR[claims: sub, aud, billing scope]
    A --> AR[claims: pseudonymous subject, aud, analytics scope]
~~~

To enforce this, the AS must identify the Resource Server via the authenticated client, verify the token was issued for that resource, filter scopes/claims via an allowlist, avoid disclosing tenants or subjects of other resources, and return `active:false` if the caller is not permitted to know the token's status under policy.

Do not use `aud` self-reported in the request body as sole evidence. Audience must be verified against claims/authorizations stored and validated by the AS.

## 16. Customizing the Endpoint: Choosing the Right Extension Point

| Need | Extension Point to Use | Reason |
|---|---|---|
| Read extra `resource_id` or context parameters | introspectionRequestConverter(s) | This is the step converting HTTP to an authentication request |
| Check whether client may query tokens of this tenant/resource | authenticationProvider(s) or a service policy invoked by the provider | This is the introspection authorization decision |
| Add permitted claims to the response | Custom provider building `OAuth2TokenIntrospection` | Claims must be based on token state and caller |
| Add correlation header, success audit, custom JSON serialization | introspectionResponseHandler | Handles HTTP response after successful authentication |
| Normalize errors, failure audit, hide internal errors | errorResponseHandler | Handles authentication failures |
| Change endpoint path | AuthorizationServerSettings | This is endpoint URI configuration, not converter/provider |
| Change how authorizations/tokens are stored | OAuth2AuthorizationService | This is the persistence/query model used by the provider |
| Change how Resource Server calls introspection | OpaqueTokenIntrospector | This is client-side integration on the RS |

A common anti-pattern is placing all logic inside the converter or success handler. This mixes request parsing, authorization decisions, and response serialization, making testing and auditing harder.

## 17. Testing with MockMvc

Integration tests should go through the real filter chain, authenticate a real client in the test fixture, and use the real provider or configured custom provider. Mocking only `findByToken` does not prove the endpoint enforces client authentication and response semantics properly.

### 17.1. Testing an Active Token

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenIntrospectionEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedResourceServerCanIntrospectActiveToken() throws Exception {
        String accessToken = fixtureActiveAccessToken();

        mvc.perform(post("/oauth2/introspect")
                .with(httpBasic("orders-api", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", accessToken)
                .param("token_type_hint", "access_token"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.active").value(true))
            .andExpect(jsonPath("$.sub").value("user-42"))
            .andExpect(jsonPath("$.scope").value("orders.read"));
    }
}
~~~

This test skeleton requires a confidential `orders-api` `RegisteredClient`, a client secret encoder, an authorization/token fixture saved in `OAuth2AuthorizationService`, and the endpoint filter chain. Never hardcode production secrets; `test-secret` is strictly for test profiles.

### 17.2. Testing an Inactive Token

~~~java
@Test
void unknownOrRevokedTokenReturnsInactiveResponse() throws Exception {
    mvc.perform(post("/oauth2/introspect")
            .with(httpBasic("orders-api", "test-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("token", "UNKNOWN_OR_REVOKED_TOKEN")
            .param("token_type_hint", "access_token"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.active").value(false))
        .andExpect(jsonPath("$.sub").doesNotExist())
        .andExpect(jsonPath("$.client_id").doesNotExist());
}
~~~

This test verifies no extra claims are leaked when a token is inactive. If a custom policy produces a different response, verify it against the RFC and security contract.

### 17.3. Testing Failed Client Authentication

~~~java
@Test
void introspectionRequiresAuthenticatedClient() throws Exception {
    mvc.perform(post("/oauth2/introspect")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("token", "ANY_TOKEN"))
        .andExpect(status().isUnauthorized());
}
~~~

The exact status depends on client authentication configuration and entry point, but the endpoint must never be treated as an unauthenticated public API.

### 17.4. Testing the Resource Server Calling Introspection

Have a dedicated integration test for `orders-api`:

1. Configure `OpaqueTokenIntrospector` pointing to the test AS;
2. Send a protected resource request with `Authorization: Bearer opaque-token`;
3. Verify the RS calls the introspection endpoint using client credentials;
4. With `active=true`, the request proceeds to authorization rules;
5. With `active=false`, the RS returns 401;
6. With an active token missing scopes, the RS returns 403;
7. When the token is revoked, the next introspection call must observe inactive status according to the cache policy.

### 17.5. Testing Custom Providers and Response Handlers

Verify that the provider rejects tokens of another tenant, the provider adds no custom claims when `active=false`, the response handler does not log tokens, the error handler does not leak stack traces, `resource_id` cannot be used by a caller to read another resource's claims, and the default provider still handles standard requests if a custom converter/provider declines to handle a request.

## 18. Error Scenarios and Diagnosis

| Symptom | Possible Cause | What to Check |
|---|---|---|
| RS gets 401 for all tokens | Wrong introspection URI or client credentials | Check endpoint, TLS, and client authentication |
| AS returns 401 | Client not authenticated or auth method mismatches registration | Check `RegisteredClient` and HTTP Authorization |
| AS returns 200 `active:false` | Token non-existent, expired, revoked, or caller unauthorized to inspect | Check authorization store and policy in test env; do not disclose reason to caller |
| AS returns 500 | Persistence error, custom provider/handler exception | Check internal trace; do not fail-open |
| Scopes not mapped | Response missing `scope` or custom converter replaces authorities | Check introspection response and `OpaqueTokenIntrospector` |
| RS receives scope yet endpoint still returns 403 | Missing scope or rule expects different authority | Check `SCOPE_` prefix and authorization matchers |
| Recently revoked token still works | RS caches active responses too long | Check cache TTL and revocation SLA |
| Custom parameter ignored | Default converter processes request first or custom converter does not match request | Check converter ordering |
| Custom provider not invoked | Default provider comes first or custom provider does not `supports` the `Authentication` type | Check provider order and type |
| Response handler does not run | Request did not pass authentication or wrong endpoint matcher | Check filter chain and `AuthenticationManager` |

## 19. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Exposing introspection endpoint without authentication | Token scanning and metadata leakage | Require Resource Server client authentication |
| Sending token via GET query string | Token can leak into access logs/history | Use POST form body over TLS |
| Returning claims when `active=false` | Leaks token existence and status | Return only `active:false` |
| Treating `active=true` as sufficient for all APIs | Missing audience/scope/tenant checks | Resource Server still authorizes per policy |
| Converter deciding whether token is active | Mixes parsing and authorization | Move decision into provider/domain service |
| Success handler looking up tokens itself | Duplicates business logic and hard to control | Provider creates result; handler only writes response |
| Replacing default provider without expiry/revocation checks | Old tokens may be accepted | Retain or fully re-implement validation |
| Trusting `resource_id` from request body | Resource Server could read out-of-scope claims | Bind resource to authenticated client |
| Caching active responses too long | Revoked tokens remain accepted | Short TTL, never exceeding `exp`/revocation budget |
| Failing open when AS is unavailable | Unverified tokens accepted | Fail-closed or bounded stale-cache policy |
| Logging tokens/client secrets | Credential leakage | Redact body and Authorization headers |
| Exposing all claims to every Resource Server | Leaks PII/tenant data | Minimum disclosure per client/audience |

## 20. Production Checklist

1. **Endpoint URI:** Does `AuthorizationServerSettings` publish the right introspection path and reverse proxy route?
2. **Client authentication:** May only authorized Resource Servers/clients call the endpoint?
3. **TLS:** Do requests and responses travel over HTTPS with certificate validation?
4. **Request format:** POST form-urlencoded; tokens never appear in queries/logs?
5. **Converter:** Retains default request parser or extends safely without dropping standard parameters?
6. **Provider:** Looks up tokens in `OAuth2AuthorizationService`, checking expiry/invalidated/active?
7. **Caller authorization:** Do Resource Servers only view tokens and claims within their permitted scope?
8. **Response:** Is `active` always a boolean; do inactive responses omit other claims?
9. **Custom claims:** Sourced from trusted stores and returning only minimal data?
10. **Response handler:** Preserves `Cache-Control: no-store`, never logs tokens, and preserves OAuth response compliance?
11. **Error handler:** Distinguishes client auth failures from inactive tokens, without leaking stack traces?
12. **Resource Server:** Checks `active`, audience, scope, and business permissions?
13. **Cache:** Short TTL, never exceeding `exp`, aligned with revocation SLA?
14. **Availability:** Explicit timeouts, retries, circuit breakers, and fail-closed policy?
15. **Multi-node:** Does `OAuth2AuthorizationService` have consistent persistence so all AS nodes see revocations/updates?
16. **Observability:** Metrics for latency, active/inactive ratio, errors, store failures, and cache hits—without tokens?
17. **Testing:** Positive, inactive, invalid-client, wrong-tenant, custom claims, revocation, and outage tests present?
18. **Version alignment:** Does code use the right packages/APIs for Spring Authorization Server 1.5.x or Spring Security 7.0+?

## 21. Applied Exercises

**Scenario A — Revoked token:** `orders-api` just introspected a token and received `active=true`. Moments later, the user logs out and the AS revokes the token. If the RS caches responses for 60 seconds, how long might the token still be accepted? Design a TTL based on an SLA.

**Scenario B — Resource Server spoofing audience:** Caller `orders-api` sends `resource_id=billing-api` in an introspection request to obtain billing claims. Which data should the AS use to identify the resource?

**Scenario C — Custom provider:** A custom provider is added to the list, yet the default provider still handles the request first. Analyze the impact of provider ordering and how to write a test proving the custom policy actually runs.

**Scenario D — Inactive token:** A Resource Server sends a random token with valid client authentication. Why is the right response typically HTTP 200 with `active:false` rather than HTTP 401?

**Scenario E — AS database timeout:** The introspection provider cannot determine token state. Choose a safe behavior and describe how to monitor the infrastructure failure.

**Hints:** A depends on cache TTL and the revocation freshness budget; B must bind the resource to the authenticated client principal; C must check provider ordering and `supports`; D because the introspection request itself is authenticated, an inactive token result is not a caller authentication error; E never fail-open—use fail-closed or an approved bounded stale cache.

## 22. Summary

`OAuth2TokenIntrospectionEndpointConfigurer` is the customization point for the introspection endpoint in Spring Authorization Server. It provides converters for pre-processing, providers for main processing, a success handler for successful responses, and a failure handler for OAuth2 error responses.

The default provider coordinates `RegisteredClientRepository` with `OAuth2AuthorizationService` to locate authorizations and evaluate tokens. The response must contain a boolean `active` field; if a token does not exist, is expired, is revoked, or the caller is not authorized to know its status, the AS should return `active:false` without disclosing extra claims.

Each extension point must be used in its proper role: converters parse requests, providers perform authorization/introspection, response handlers serialize results, and error handlers return errors. When custom claims or per-Resource-Server restrictions are needed, decisions must rely on the authenticated client and trusted authorization records.

On the Resource Server side, `OpaqueTokenIntrospector` calls the endpoint, reads `active`, and maps scopes to authorities. Caching must balance performance against visibility of revoked tokens; when the AS cannot determine token state, the token must never be assumed active.

Mastering these customization points makes it straightforward to build an extensible introspection endpoint that stays compliant with RFC 7662 while keeping the Authorization Server, Resource Server, authorization store, and overall security policy aligned.

## 23. References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request, response, active, client authorization, caching, and security considerations.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client authentication, access tokens, and OAuth2 error responses.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenIntrospectionEndpointConfigurer`, filter, converter, provider, and handlers.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer`, `AuthorizationServerSettings`, and endpoint configuration.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2AuthorizationService`, authorization/token lifecycle, and JDBC/in-memory implementations.
- [Spring Authorization Server API — OAuth2TokenIntrospectionEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenIntrospectionEndpointConfigurer.html): detailed API of extension points in the 1.5.x line.
- [Spring Authorization Server API — OAuth2TokenIntrospectionAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationProvider.html): default provider and dependencies.
- [Spring Authorization Server API — OAuth2TokenIntrospection.Builder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2TokenIntrospection.Builder.html): building response claims.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, `OpaqueTokenAuthenticationProvider`, authority mapping, and customization.
- [Spring Security 7 — OAuth 2.0 Authorization Server Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): APIs after Authorization Server integration into Spring Security 7.
