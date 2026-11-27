# Service-to-Service Integration Using Client Credentials

## 1. Context and Objectives

In a microservices architecture, many requests are sent by an application or workload rather than a logged-in user. For example, the Billing service calls the Inventory API to reserve stock; a nightly job worker reads reporting data; the Notification service sends requests to the Communication API. These components need a machine identity and scoped access permissions.

The OAuth 2.0 **Client Credentials Grant** is designed for scenarios where a confidential client acts on its own behalf when accessing resources. The client authenticates to the Authorization Server using its client credentials, obtains an access token, and sends that token to the Resource Server. There is no browser redirect, no resource owner sign-in, and no interactive consent screen in this flow.

Running example throughout this lesson:

- `billing-service` is the OAuth client.
- `inventory-api` is the Resource Server.
- The Authorization Server runs at `https://auth.example.com`.
- Billing may only read inventory and reserve stock within its authorized API scopes.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as billing-service
    participant AS as Authorization Server
    participant I as inventory-api
    B->>AS: POST /oauth2/token (client authentication + grant_type)
    AS->>AS: Authenticate client and validate grant/scope
    AS-->>B: access_token + token_type + expires_in
    B->>I: GET /inventory (Authorization: Bearer token)
    I->>I: Verify token, audience and scope
    I-->>B: 200 OK + inventory data
~~~

After this lesson, you will be able to:

1. Distinguish machine identity from user identity.
2. Accurately describe the Client Credentials Grant and its limitations.
3. Register confidential clients in Spring Authorization Server.
4. Configure client authentication, grant types, scopes, and token lifetimes.
5. Issue JWT access tokens with an API-appropriate audience.
6. Configure a Resource Server to verify issuer, audience, and scopes.
7. Use Spring Security OAuth2 Client to acquire and manage access tokens.
8. Cache tokens properly and avoid calling the token endpoint for every API request.
9. Handle secret rotation, token expiry, authentication failures, and retries.
10. Test the entire service-to-service flow and operate it securely.

**Version scope:** Examples reference Spring Authorization Server 1.5.8, Spring Security 6.x, and Spring Boot 3.x. Some OAuth2 Client integration APIs vary by minor version; verify against your application's dependency versions when implementing.

## 2. How Does the Client Credentials Grant Work?

### 2.1. Roles

| Role | Component in Example | Responsibility |
| --- | --- | --- |
| OAuth client | `billing-service` | Authenticates using client credentials and requests an access token. |
| Authorization Server | `auth.example.com` | Authenticates the client, checks permissions, and issues tokens. |
| Resource Server | `inventory-api` | Verifies the token and decides whether the request is allowed. |
| Resource owner | Not directly involved | This flow does not represent a logged-in user. |

Client Credentials is strictly for confidential clients capable of keeping credentials secure. Never embed client secrets in mobile apps, SPAs, or binaries distributed to end users.

### 2.2. Request to the Token Endpoint

The client sends a request to the Token Endpoint, typically `POST /oauth2/token`, containing:

- Client authentication per the registered method.
- `grant_type=client_credentials`.
- Optional `scope`, if the client needs a specific set of permissions.

Example using HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

HTTP Basic is how credentials are encoded in the request; always use TLS. Never write the Authorization header or client secret into access logs, traces, or exception messages.

### 2.3. Token Response

A successful response looks like:

~~~json
{
  "access_token": "eyJraWQiOiJrZXktMjAyNi0wMSIs...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

`expires_in` expresses the access token's lifetime in seconds. The client must use the token before it expires and request a new token when needed.

The Client Credentials Grant does not issue refresh tokens per RFC 6749. When the access token expires, the client re-authenticates at the Token Endpoint to acquire a new token.

### 2.4. There Is No User in the Flow

The token represents the client/workload, not a user. Therefore:

- Do not use this flow as a substitute for Authorization Code + PKCE for users.
- Do not attach a user identity to the token simply because the initial trigger came from a user request.
- Do not infer the current user from the client ID.
- If business logic needs both user and service identities, design token exchange/on-behalf-of under a proper authorization model instead of pretending Client Credentials represents user delegation.

The Resource Server can identify the client via the `client_id` claim or subject depending on the token profile, but the semantics of issued tokens must be clearly defined. When applying the JWT Access Token Profile in RFC 9068 to Client Credentials, `sub` identifies the client and `client_id` is a required claim; keep those semantics consistent on both the issuer and the API.

## 3. Registering Confidential Clients in Spring Authorization Server

### 3.1. RegisteredClient

Spring Authorization Server stores client metadata via `RegisteredClientRepository`. A Client Credentials registration typically requires:

- A stable Client ID.
- An encoded client secret or a stronger authentication mechanism.
- Client authentication method.
- Authorization grant type `client_credentials`.
- Allowed scopes.
- Token settings, including access token time-to-live.

Example creating a client:

~~~java
RegisteredClient billingClient = RegisteredClient.withId(UUID.randomUUID().toString())
    .clientId("billing-service")
    .clientSecret(passwordEncoder.encode(configuredClientSecret))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("inventory.read")
    .scope("inventory.reserve")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(false)
        .build())
    .build();

registeredClientRepository.save(billingClient);
~~~

`configuredClientSecret` must come from a secret manager or a secure provisioning process. Do not hard-code secrets into source code or commit configuration files containing real values. `PasswordEncoder` must use the same algorithm/strength policy the server uses to verify client secrets.

### 3.2. Why Use client_secret_basic?

Common client authentication methods:

| Method | How It Works | When Appropriate |
| --- | --- | --- |
| `client_secret_basic` | Client ID/secret in HTTP Basic Authorization. | Confidential services with securely managed secrets. |
| `client_secret_post` | Client ID/secret in form body. | Only for compatibility reasons; credentials can easily be logged with request bodies. |
| `private_key_jwt` | Client signs a JWT assertion with its private key. | Workloads with solid key management that want to avoid shared secrets. |
| `tls_client_auth` | Client authenticated via certificate at the TLS layer. | Infrastructure supporting mutual TLS and certificate lifecycle management. |

Choose a method supported by both the Authorization Server and the client. In systems with HSM/KMS or workload identities, `private_key_jwt` or mutual TLS may be preferable to shared secrets.

### 3.3. Client ID Must Identify the Workload

Do not share one client ID across all services when those services have different permissions. For example:

| Client | Granted Scopes |
| --- | --- |
| `billing-service` | `inventory.read`, `inventory.reserve` |
| `reporting-worker` | `inventory.read`, `reports.export` |
| `notification-service` | `notifications.send` |

If all services share credentials, one compromised service gains all permissions of the others. Separating client identities limits blast radius and supports auditing.

### 3.4. Scopes Are the Maximum Permission Boundary

The scope list in RegisteredClient defines the set of permissions a client may request. A client should receive only the scopes needed for its work.

The Authorization Server must reject unregistered scopes. The Resource Server continues enforcing scopes on each endpoint; possessing a scope in a token does not mean every endpoint accepts it.

Do not grant `admin`, `*`, or overly broad scopes for deployment convenience. Create meaningful API/resource/action scopes such as `inventory.read`, `inventory.reserve`, and `invoice.issue`.

## 4. Configuring the Authorization Server

### 4.1. Endpoints and Core Services

Spring Authorization Server processes Client Credentials via the Token Endpoint and core components:

- `RegisteredClientRepository`: looks up clients and client configurations.
- `OAuth2AuthorizationService`: stores authorization/token state when persistence is configured.
- `OAuth2TokenGenerator`: generates access tokens.
- `OAuth2AuthorizationServerSettings`: configures issuer and endpoints.

In production, use persistent repositories suited to your deployment; in-memory repositories fit simple experiments or demos. Multiple instances must share durable client/token state by design.

### 4.2. SecurityFilterChain for the Authorization Server

A baseline configuration can use Spring Authorization Server's configurer:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, Customizer.withDefaults());

    return http.build();
}
~~~

This snippet illustrates the filter chain handling Authorization Server endpoints. A real application also needs to configure authentication, exception handling, a JWK source, issuer, endpoints, and filter chains for the rest of the application.

### 4.3. Configuring Issuer and Token Endpoint

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .tokenEndpoint("/oauth2/token")
        .build();
}
~~~

The issuer must be stable and match discovery metadata as well as the `iss` claim in tokens. Never derive the issuer from an untrusted Host header.

### 4.4. JWT Access Tokens and Audience

A JWT access token can be verified locally by the Resource Server using its signature and claims. A critical claim is `aud` (audience), identifying the resource server/API for which the token is intended.

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "billing-service",
  "aud": ["inventory-api"],
  "client_id": "billing-service",
  "scope": "inventory.read inventory.reserve",
  "iat": 1794850000,
  "exp": 1794850300
}
~~~

Do not assume every access token automatically carries the right API audience. Define an audience policy and ensure Resource Servers enforce it.

### 4.5. Adding Audience and client_id to JWT Access Tokens

For JWT access tokens, you can use `OAuth2TokenCustomizer<JwtEncodingContext>`:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            RegisteredClient client = context.getRegisteredClient();
            context.getClaims().claim("client_id", client.getClientId());

            if (client.getClientId().equals("billing-service")) {
                context.getClaims().audience(List.of("inventory-api"));
            }
        }
    };
}
~~~

This is a small policy example. With many clients/APIs, manage client-scope-audience mappings via configuration or a policy service. Never let a client submit an arbitrary audience and copy it straight into the token.

If a client is permitted to call multiple APIs, include only the audience of the resource actually requested/authorized in the token. Separate tokens per audience can be issued to minimize the chance of a token being misused against the wrong API.

### 4.6. Tenant Claims When a Service Operates per Tenant

If each workload is restricted to a specific tenant, tenant binding must come from client registration or a trusted policy. Never read an arbitrary `tenant_id` from the token endpoint request.

For example, a customizer can read managed metadata from the client registration or a service mapping:

~~~java
context.getClaims().claim("tenant_id", tenantPolicy.tenantFor(client.getId()));
~~~

This is pseudocode; `tenantPolicy` must come from a trusted configuration source. The Resource Server must verify that the tenant claim matches the tenant of the resource being accessed.

### 4.7. JWT or Opaque Access Token?

| Criterion | JWT | Opaque Token |
| --- | --- | --- |
| Validation | Resource Server verifies signature and claims. | Resource Server introspects with the Authorization Server. |
| Network dependency | No introspection needed per request. | Requires introspection or response caching. |
| Revocation | Issued JWTs may remain valid until `exp` if API validates locally only. | Authorization Server can reflect token status via introspection. |
| Payload | Claims are readable; must not be treated as secret. | Does not expose claims to client/API without introspection. |
| Distribution | APIs can validate independently with JWKS. | APIs depend on introspection endpoint availability/latency. |

A JWT is not encrypted merely because it is signed. Do not place secrets, private data, or unnecessary information inside claims.

## 5. Resource Server Protecting the API

### 5.1. Verifying Issuer and Signature

The Inventory API must verify that tokens were issued by a trusted Authorization Server. With Spring Boot, configure the issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

Spring Security uses issuer metadata/JWKS to configure the JWT decoder and verify issuer, signature, and appropriate default validators.

### 5.2. Opaque Tokens and Introspection

If the Authorization Server issues opaque access tokens, the Resource Server must introspect them. Example Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: inventory-api-introspector
          client-secret: ${INVENTORY_INTROSPECTION_SECRET}
~~~

The credentials in this configuration are dedicated credentials for the Inventory API to call the introspection endpoint. They do not need to be the `billing-service` client credentials used to obtain access tokens. Grant only the necessary introspection permissions and protect the secret with a secret manager.

Introspection results provide token status and attributes such as scope, client, and audience depending on the token profile. The Resource Server must still validate scope/audience/tenant policies after confirming the token is active.

### 5.3. Validating Audience

A valid issuer is not enough. A token intended for `billing-api` must not be accepted by `inventory-api` simply because both were issued by the same Authorization Server.

Example validator:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com";
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("inventory-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null);
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
    return decoder;
}
~~~

This example validates a specific audience for the Inventory API. In a system with multiple Resource Servers, each API must configure its own audience. Do not share a single global audience across all APIs if your goal is to restrict tokens per resource.

### 5.4. Validating Scope

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/inventory/**")
                .hasAuthority("SCOPE_inventory.read")
            .requestMatchers(HttpMethod.POST, "/inventory/reservations")
                .hasAuthority("SCOPE_inventory.reserve")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

Spring Security maps scopes to authorities with the `SCOPE_` prefix by default. If you change the authority converter, keep endpoint/method security checks aligned.

### 5.5. Combining Scopes with Tenant Authorization

Scopes only describe permissions at the API/action level. When resources belong to specific tenants, the API must verify the tenant claim and the resource's tenant ownership.

~~~java
@PreAuthorize("hasAuthority('SCOPE_inventory.read')")
public Inventory findInventory(String tenantId, String sku) {
    String tokenTenant = currentJwt().getClaimAsString("tenant_id");
    if (!tenantId.equals(tokenTenant)) {
        throw new AccessDeniedException("Tenant mismatch");
    }
    return inventoryRepository.findByTenantIdAndSku(tenantId, sku);
}
~~~

This is pseudocode for tenant authorization. Ensure repository queries always include a tenant predicate, even when method authorization has already checked the claim.

## 6. Integrating OAuth2 Client in the API-Calling Service

### 6.1. Declaring Client Registration

The Billing service needs the Token Endpoint, client ID, secret, grant type, authentication method, and scopes. With Spring Boot, you can configure:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: platform-auth
            client-id: billing-service
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
              - inventory.reserve
        provider:
          platform-auth:
            token-uri: https://auth.example.com/oauth2/token
~~~

In real configuration files, use an environment/secret-manager placeholder referencing `INVENTORY_CLIENT_SECRET`. Real secret values must not be stored in the repository. For production, consider a secret manager, workload identity, private_key_jwt, or mTLS.

### 6.2. OAuth2AuthorizedClientManager

`OAuth2AuthorizedClientManager` coordinates acquiring and storing authorized clients/access tokens. For service-to-service calls, you can use `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, authorizedClients);

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

The provider supports Client Credentials and the manager uses `OAuth2AuthorizedClientService` to store tokens per client registration/principal. You can use an in-memory implementation for simple services or persistence tailored to the runtime environment.

### 6.3. Acquiring Tokens and Calling the API

~~~java
@Service
public class InventoryGateway {

    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final RestClient restClient;

    public InventoryGateway(
            OAuth2AuthorizedClientManager authorizedClientManager,
            RestClient.Builder restClientBuilder) {
        this.authorizedClientManager = authorizedClientManager;
        this.restClient = restClientBuilder
            .baseUrl("https://inventory.example.com")
            .build();
    }

    public Inventory getInventory(String sku) {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest.withClientRegistrationId("inventory-service")
                .principal("billing-service")
                .build();

        OAuth2AuthorizedClient authorizedClient =
            authorizedClientManager.authorize(authorizeRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Could not obtain inventory access token");
        }

        String token = authorizedClient.getAccessToken().getTokenValue();

        return restClient.get()
            .uri("/inventory/{sku}", sku)
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(Inventory.class);
    }
}
~~~

`principal("billing-service")` is a technical principal name used to store the authorized client; it does not turn the request into a user login. Use a stable principal name per workload so tokens are reused under the exact registration/principal key.

In real applications, encapsulate token acquisition in a shared gateway/interceptor instead of repeating it in every method. Never log the token value.

### 6.4. Storing Tokens Client-Side

`OAuth2AuthorizedClientService` stores the authorized client and access token. When the token expires or a new token is needed, the Client Credentials provider re-authenticates with the Token Endpoint using client authentication. This is a fresh token issuance, not a refresh token exchange.

When using an in-memory service:

- Tokens are lost on process restart.
- Each instance maintains its own cache.
- Multiple instances may call the Token Endpoint concurrently.

This can be acceptable for simple workloads. For high-scale systems, consider a shared token cache or controlled token acquisition design; never share tokens across instances that have different credentials, tenants, or audiences.

### 6.5. Integrating a RestClient Interceptor

Spring Security provides integrations to attach OAuth2 authorized clients to HTTP clients. On versions supporting `OAuth2ClientHttpRequestInterceptor`, you can configure the interceptor to select the client registration and principal for each request.

When using an interceptor, verify that the right registration ID is selected, the principal name is stable, tokens are sent only to trusted destinations, inbound user bearer tokens are not automatically forwarded, and redirects do not send Authorization headers to other hosts.

If your Spring Security version does not yet include that interceptor, use the manager directly as in the previous example or write a small interceptor calling the manager.

## 7. Token Caching and Lifecycle Management

### 7.1. Do Not Request a Token for Every API Call

A common mistake is calling the Token Endpoint before every request to a Resource Server. That increases latency, overloads the Authorization Server, and easily triggers rate spikes under concurrent traffic.

The client should reuse the access token until shortly before expiration. `OAuth2AuthorizedClientManager` can manage authorization and token storage by registration/principal.

### 7.2. Token Cache Keys

If building a custom token cache, the key must include every factor that alters a token's permissions:

~~~text
token-cache:{issuer}:{client-registration}:{principal}:{audience}:{scope-set}:{tenant}
~~~

Never share one cache entry across different scopes, audiences, or tenants. Canonicalize the scope set before constructing the key. Never use raw client secrets or raw access tokens as cache keys.

### 7.3. Refreshing Before Expiry

A token cache should compute expiration from `expires_in`/`expiresAt` and refresh ahead by a safety margin to prevent requests from using a just-expired token due to clock skew or network latency.

Example policy: 5-minute token lifetime, start fetching a new token with 30 seconds remaining, and add small jitter so instances do not refresh simultaneously. These are illustrative values; synchronize clocks and choose skew based on latency, clock drift, and token lifetime.

### 7.4. Preventing Token Request Stampedes

When a token expires, hundreds of requests may simultaneously ask for a new token. Implement single-flight/mutex locking per cache key so only one request fetches a new token, plus timeouts, bounded retries for the Token Endpoint, jittered backoff, and a retry cap.

Do not retry `invalid_client`, `unauthorized_client`, or `invalid_scope` as network errors. Those are configuration/credential errors requiring alerts and remediation.

### 7.5. Token Caches and Multi-Instance Deployments

Sharing access tokens across instances is not always necessary. Some systems let each instance fetch tokens and hold a local cache because token lifetimes are short, reducing the blast radius of widely shared tokens. If using a shared cache, protect read permissions, encrypt at rest where appropriate, and namespace by client/tenant/audience/scope.

When a client secret rotates or a client is disabled, evict old authorized client/token caches and stop calling the token endpoint with the old credential.

## 8. Protecting Client Credentials

### 8.1. Secret Lifecycle

A client secret is a long-lived credential for obtaining access tokens. You must:

- Generate secrets using a cryptographically secure random generator.
- Store secrets in a secret manager/vault.
- Never commit them to Git, images, or logs.
- Restrict secret read access by workload identity.
- Maintain rotation and revocation procedures.
- Never send secrets over chat, email, or unprotected tickets.
- Use TLS to the Token Endpoint.

The Authorization Server only needs to store a password hash/encoded secret compatible with its PasswordEncoder; it does not need to read back plaintext secrets.

### 8.2. Zero-Downtime Rotation

A rotation workflow:

1. Create a new credential or a new client registration as supported by the system.
2. Update the secret manager for the workload.
3. Roll out the calling service and verify token acquisition with the new credential.
4. Monitor `invalid_client` and token issuance metrics.
5. Revoke the old secret after all instances have switched.
6. Evict old token/authorized-client caches.

If your framework/storage supports only one active secret at a time, use two client registrations during the transition window to avoid a simultaneous cutover.

### 8.3. Stronger Client Authentication

For sensitive production systems:

- `private_key_jwt` avoids distributing shared secrets, though it requires protecting private keys and managing public JWKs.
- Mutual TLS binds client authentication to a certificate and can support certificate-bound access tokens when both the Authorization Server and Resource Server are configured accordingly.
- Cloud/platform workload identity can issue short-lived credentials or sign assertions in place of static secrets.

Enable only methods fully supported by the client, Authorization Server, and infrastructure. Test certificate rotation, key compromise, and client disabling.

### 8.4. Do Not Use Client Credentials to Impersonate a User

If the Billing service processes an order created by Alice, the Client Credentials access token still represents the Billing service. If the Inventory API needs to know Alice is the user and enforce Alice's permissions, a delegation design is required:

- Authorization Code Flow for the client to acquire a user-scoped token.
- Token Exchange/on-behalf-of if supported by the Authorization Server and permitted by policy.
- Passing separately authenticated business actor context without spoofing `sub` in the client token.

Audit records can log both the service principal and business actor, but never conflate the two identities within the same token semantics.

## 9. Token and API Security

### 9.1. A Bearer Token Is a Credential

Anyone holding a bearer token can use it until it expires or is invalidated by the active mechanism. Therefore:

- Send only over HTTPS.
- Place it in `Authorization: Bearer`.
- Never put it in URL query parameters.
- Never log tokens in request/response bodies.
- Never send it to untrusted hosts.
- Never store it in browser storage.

### 9.2. Audience Restriction

A token should be valid only for the API that needs it. If Billing fetches a token for the Inventory API, that token must not automatically work at the Payments API. The Resource Server must verify `aud`, not merely the signature and issuer.

### 9.3. Scope Restriction

The client requests only granted scopes. The Resource Server maps scopes to authorities and enforces them on each endpoint. Never trust scopes self-reported by a caller in HTTP headers or parameters.

### 9.4. Token Lifetime and Revocation

Client Credentials access tokens should have short lifetimes aligned with risk and operational cost. Self-contained JWTs may still be accepted by Resource Servers until `exp` if APIs validate signatures locally only, even after the client is disabled at the Authorization Server.

When immediate revocation is required, use opaque tokens and introspection, denylist/revocation lookups on the Resource Server, token version/workload state checks, or short JWT lifetimes with a defined maximum exposure window.

Never claim that disabling a client automatically invalidates all already-issued JWTs.

### 9.5. Rate Limiting and Abuse Control

The Token Endpoint needs rate limits by client, IP, tenant, and authentication outcome. Monitor clients sending unusual token requests, invalid credentials, or out-of-policy scopes.

The Resource Server also needs rate limits by client/workload and business operation; scopes do not replace quotas.

## 10. Error Handling

### 10.1. Token Endpoint Errors

| Error | Common Cause | Resolution |
| --- | --- | --- |
| `invalid_client` | Wrong client ID/secret, client disabled, or authentication method mismatch. | Check secret manager, registration, and auth method; do not retry continuously. |
| `unauthorized_client` | Client is not permitted to use the Client Credentials grant. | Add the grant if policy allows. |
| `invalid_scope` | Unregistered or ungranted scope. | Fix client registration/requested scope. |
| `unsupported_grant_type` | Wrong grant type or provider not enabled on server. | Check `grant_type=client_credentials` and server configuration. |
| `invalid_request` | Missing/malformed form parameters or Content-Type. | Send standard POST form-urlencoded requests. |
| HTTP 429 | Rate limit/quota exceeded. | Back off with jitter and reduce request rate. |
| HTTP 5xx/network timeout | Temporary Authorization Server or network failure. | Bounded retry; continue using valid cached tokens if policy allows. |

### 10.2. Resource Server Errors

| HTTP Status | Common Meaning | How to Check |
| --- | --- | --- |
| 401 Unauthorized | Missing token, invalid signature, wrong issuer, expired, or malformed. | Check token, clock, issuer, and JWKS. |
| 403 Forbidden | Valid token, but lacking scope/authority or tenant permission. | Check scope, audience, tenant, and authorization policy. |
| 404 Not Found | Resource does not exist or API hides cross-tenant resources. | Check tenant-scoped lookup. |
| 429 Too Many Requests | Client exceeded quota/rate limit. | Check client identity and retry-after. |
| 5xx | API or dependency processing failure. | Correlation ID, traces, and dependency health. |

Do not automatically fetch a new token when the Resource Server returns 403 due to insufficient permissions. A new token with the same client/scope policy will not resolve an authorization failure.

### 10.3. Retry Policy

Retry only transient errors such as timeouts, connection resets, 429, or 5xx per policy. For `invalid_client`, `invalid_scope`, `unauthorized_client`, and token signature failures, stop retrying and raise an alert.

Do not retry non-idempotent API mutations without an idempotency key or duplicate-processing protection.

## 11. End-to-End Testing

### 11.1. Testing the Token Endpoint

~~~bash
curl --request POST \
  --url https://auth.example.com/oauth2/token \
  --user "$CLIENT_ID:$CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=inventory.read"
~~~

In a real shell, pull credentials from a secret manager or a secure test environment. Never enable shell tracing (`set -x`) when commands contain secrets.

### 11.2. Testing the API

~~~bash
curl --request GET \
  --url https://inventory.example.com/inventory/SKU-123 \
  --header "Authorization: Bearer $ACCESS_TOKEN"
~~~

Test valid tokens with matching issuer/audience/scope, tokens missing scope, wrong audience, wrong issuer/signature, expired tokens, Tenant A accessing Tenant B resources, and requests with no token.

### 11.3. Unit Testing RegisteredClient

Verify Client Credentials grant, client authentication method, secret encoding, approved scopes, access token TTL, and that the client has no unnecessary grants.

### 11.4. Authorization Server Integration Tests

Use an HTTP test client or Spring Boot integration test to confirm:

1. Valid client acquires a token successfully.
2. Wrong client secret receives `invalid_client`.
3. Client not registered for Client Credentials is rejected.
4. Scopes outside the allowlist are rejected.
5. JWT contains expected issuer, audience, client ID, and scopes.
6. Token is stored/retrieved properly when authorization persistence is enabled.
7. Secret rotation causes old credentials to be rejected as planned.

### 11.5. Resource Server Integration Tests

Test issuer, signature, `exp`/`nbf`, audience, scope mapping, tenant claims, and opaque token introspection if using opaque access tokens.

### 11.6. Load and Concurrency Testing

Simulate many concurrent requests from the same client as the token nears expiry. Measure Token Endpoint call count, cache hit ratio, token acquisition latency, API p95/p99 latency, 401 rate from token expiry, and behavior when the Authorization Server is unavailable.

The expected outcome is one token acquisition per cache key within the refresh window, not one token request per API call.

## 12. Observability and Operations

### 12.1. Metrics

Monitor token request counts by client/grant/result; `invalid_client`, `invalid_scope`, and `unauthorized_client` rates; token issuance latency; access token lifetimes; OAuth2 client cache hit/miss ratios; Resource Server 401/403 counts; JWKS refresh/error rates; credential rotation age; and rate-limit hits.

Do not place unbounded-cardinality raw client IDs, secrets, tokens, subjects, or sensitive claims into metric labels. Use categorized identifiers and controlled logging.

### 12.2. Audit

Audit events should record which client requested a token, grant type and granted scopes, audience if policy permits, tenant context, authentication result, timestamp, and correlation ID. Never write access tokens or client secrets to audit logs.

### 12.3. Availability and Dependencies

Client Credentials depends on the Authorization Server when acquiring new tokens. If the Authorization Server is unavailable, the client can continue using valid unexpired access tokens; never use expired tokens just to preserve availability. Use timeouts, bounded retries, and circuit breakers/bulkheads for the Token Endpoint. The Resource Server can continue verifying JWTs locally while cached JWKS remain valid; for opaque tokens, the introspection dependency must fit within the availability budget.

### 12.4. Secret and Key Rotation Operations

Maintain a schedule to rotate client secrets/private keys/certificates, track credential age, verify rollout completion, and revoke old credentials. Authorization Server signing keys follow a different lifecycle from client credentials; rotating signing keys must update JWKS and ensure Resource Servers handle key overlap correctly.

## 13. Common Mistakes

### Mistake 1: Using Client Credentials for User Login

**Symptom:** The API does not know which user performed an action, or all actions share the same client identity.

**Cause:** Confusing machine identity with resource owner identity.

**Fix:** Use Authorization Code + PKCE or appropriate delegation/token exchange.

### Mistake 2: Sharing One Client ID/Secret Across All Services

**Symptom:** Cannot distinguish which service originated a request and cannot limit blast radius.

**Cause:** Reusing one credential across multiple workloads.

**Fix:** Assign one client identity per workload or trust boundary with dedicated scopes.

### Mistake 3: Storing Secrets in Source Code

**Symptom:** Secrets appear in Git history, images, or logs.

**Cause:** Hard-coding credentials.

**Fix:** Use a secret manager, rotation, and workload-identity-scoped read permissions.

### Mistake 4: Not Checking Audience

**Symptom:** A token intended for API A is accepted by API B.

**Cause:** Verifying only issuer and signature.

**Fix:** Issue targeted audiences and enforce dedicated validators on each Resource Server.

### Mistake 5: Granting Overly Broad Scopes

**Symptom:** A service that only needs read access can write or delete.

**Cause:** Using wildcard/admin scopes.

**Fix:** Enforce least privilege and endpoint-level authority checks.

### Mistake 6: Calling the Token Endpoint on Every Request

**Symptom:** High load on the Token Endpoint and increased API latency.

**Cause:** Not caching authorized clients/access tokens.

**Fix:** Use OAuth2AuthorizedClientManager or an expiration-aware token cache.

### Mistake 7: Token Cache Key Missing Scope/Audience

**Symptom:** Service sends a token with the wrong permissions or audience for a request.

**Cause:** Caching solely by client ID.

**Fix:** Namespace caches by issuer, client registration, principal, scope, audience, and tenant.

### Mistake 8: Retrying Credential Errors

**Symptom:** Token Endpoint gets spammed with invalid client secrets.

**Cause:** Retrying every HTTP status as a network error.

**Fix:** Retry only transient errors; OAuth client errors must stop and alert.

### Mistake 9: Assuming Disabling a Client Immediately Revokes JWTs

**Symptom:** APIs continue accepting old JWTs.

**Cause:** Resource Servers verify JWTs locally and the tokens have not yet expired.

**Fix:** Use opaque/introspection, denylists, or short TTLs per requirements.

### Mistake 10: Sending Bearer Tokens to Unintended Hosts

**Symptom:** Tokens leak when an HTTP client follows a redirect or calls the wrong base URL.

**Cause:** Not restricting destinations and redirect behavior.

**Fix:** Enforce HTTPS, host allowlists, redirect controls, and never forward Authorization headers across origins.

## 14. Production Checklist

| Item | Condition to Verify |
| --- | --- |
| Client identity | Does each workload have its own client identity per permissions and trust boundary? |
| Grant | Is `client_credentials` enabled only for valid use cases? |
| Authentication | Is Basic secret, private_key_jwt, or mTLS appropriate? |
| Secret storage | Are secrets in a secret manager and absent from source/images/logs? |
| Secret encoding | Does the Authorization Server store encoded secrets? |
| Scopes | Do scopes follow least privilege and are they enforced at the API? |
| Audience | Is the token restricted to the intended Resource Server? |
| Issuer | Does the Resource Server verify issuer and signature? |
| Tenant | Is tenant binding derived from a trusted source and checked at the API? |
| Token lifetime | Is the TTL short and aligned with risk/latency? |
| Refresh | Do clients avoid assuming Client Credentials issues refresh tokens? |
| Token cache | Are tokens reused, refreshed early, and protected against stampedes? |
| Cache key | Does it include issuer/client/principal/scope/audience/tenant? |
| Retries | Are retries bounded and do they distinguish credential errors from transient errors? |
| Rotation | Is there a rollout and revocation workflow for old credentials? |
| Revocation | Is there a policy for JWTs still valid after disable/revocation? |
| TLS | Do the Token Endpoint and Resource Server enforce HTTPS only? |
| Logging | Are secrets/access tokens/Authorization headers excluded from logs? |
| Audit | Are client, scope, grant, result, and correlation ID recorded? |
| Availability | Are timeouts, circuit breakers, and dependency SLOs defined? |
| Tests | Are wrong issuer/audience/scope/tenant and secret rotation tested? |

## 15. Hands-on Exercise

An e-commerce system has three services:

- `billing-service` needs to read inventory and create reservations.
- `reporting-worker` only reads data to export reports.
- `notification-service` only sends notifications.

The Authorization Server issues JWT access tokens. Inventory API and Notification API are independent Resource Servers. The system runs across multiple instances and must tolerate brief Authorization Server outages.

Complete the following tasks:

1. Create three RegisteredClients with distinct client IDs, secrets, and scopes.
2. Choose a client authentication method and justify your choice.
3. Configure the Client Credentials Grant and access token TTLs.
4. Emit JWTs containing the appropriate issuer, audience, client ID, and scopes.
5. Configure separate audiences for Inventory API and Notification API.
6. Configure Resource Servers to verify issuer, audience, and scopes.
7. Use OAuth2AuthorizedClientManager in the Billing service.
8. Design token caching, refresh skew, and single-flight behavior.
9. Plan a zero-downtime secret rotation procedure.
10. Simulate Authorization Server timeouts, invalid_client, invalid_scope, and API 403 responses.
11. Verify that a Reporting token cannot create reservations.
12. Measure token request counts and API latency before and after caching.

**Passing criteria:** Each workload has a dedicated identity; tokens carry only required permissions and the right audience; Resource Servers verify issuer/audience/scopes; clients reuse tokens safely; credential errors are not retried infinitely; secrets/tokens never appear in logs.

## 16. Reference Documents

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): Client Credentials Grant.
- [RFC 6749 — Section 3.2.1](https://www.rfc-editor.org/rfc/rfc6749#section-3.2.1): Client Authentication.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sending and protecting bearer access tokens.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): iss, sub, aud, and exp claims.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile and client-related claims.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, token generation, and core services.
- [Spring Authorization Server 1.5.8 — OAuth2TokenCustomizer Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenCustomizer.html): customizing claims/tokens.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint and protocol processing.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized clients, and manager.
- [Spring Security — OAuth2AuthorizedClientManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): coordinating authorization and authorized client lifecycle.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder and Resource Server validation.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection for opaque access tokens.
