# Client Credentials and Appropriate Use Cases

OAuth 2.0 Client Credentials is a grant type for an application or service to authenticate using its own identity to call a protected API. For example, an invoicing service calls an inventory service to read stock levels; a background job sends reports to a partner API; or a backend synchronizes data between two systems. In these scenarios, the request represents the client/service, not a logged-in user.

With Spring Boot, an application can act as an OAuth2 Client to obtain an access token from an Authorization Server, or act as a Resource Server to verify received Bearer tokens. Springdoc-openapi describes this flow in a Security Scheme Object of type `oauth2`, helping Swagger UI and clients understand the token endpoint, scopes, and which operations require which permissions. OpenAPI metadata does not itself register clients, obtain tokens, or protect endpoints; those behaviors must be configured separately with Spring Security and the Authorization Server.

## 1. What problem does Client Credentials solve?

Consider a system composed of three services:

- `order-service` manages orders.
- `inventory-service` provides inventory information.
- `reporting-job` runs on a schedule and aggregates reports.

When `order-service` needs to read inventory or `reporting-job` needs to call a reporting API, there is no interactive user logging in. Each application needs its own machine identity and should be granted only the permissions it needs.

Client Credentials allows a client to send its own credentials to the token endpoint to receive an access token. The client then sends the token to the target API:

```text
inventory-service
       |
       | client_id + client_secret
       v
Authorization Server
       |
       | access_token (scope: inventory.read)
       v
inventory-service
       |
       | Authorization: Bearer <access_token>
       v
inventory API (Resource Server)
```

The token represents the identity and permissions granted to the client. The Resource Server verifies the token and checks permissions before returning data.

## 2. Roles of OAuth 2.0 components

| Component | Role in Client Credentials |
|---|---|
| Client | Application/service that needs to call an API and can protect its own credentials |
| Client ID | Client identifier registered at the Authorization Server |
| Client Secret or other client authentication method | Proves the client is a registered application |
| Authorization Server | Authenticates the client, checks granted permissions, and issues access tokens |
| Token Endpoint | Endpoint that receives token requests, typically `/oauth2/token` |
| Resource Server | API that receives Bearer tokens, verifies tokens, and enforces authorization |
| Access Token | Time-limited credential sent in requests to the API |
| Scope | Permission requested by or granted to the client, such as `inventory.read` |

Client Credentials is a flow between the client and the Authorization Server. The Resource Server does not need to receive the client secret; it only receives the access token and verifies it according to the configured mechanism.

## 3. Client Credentials grant flow

A typical flow consists of these steps:

1. An administrator registers the client at the Authorization Server and issues a `client_id` along with a credential or another client authentication method.
2. The client sends a request to the token endpoint with `grant_type=client_credentials` and required scopes.
3. The Authorization Server authenticates the client and determines the granted permissions.
4. The Authorization Server returns an access token along with token type, expiration, and granted scopes.
5. The client sends the access token to the Resource Server via the `Authorization: Bearer ...` header.
6. The Resource Server verifies the token, checking issuer, signature or token status, expiration, and access permissions.
7. When the token expires, the client obtains a new token by performing the Client Credentials grant again.

This flow has no browser redirect to a user login page, no authorization code, and does not need a redirect URI.

## 4. Token request at the endpoint

According to OAuth 2.0, the client sends a POST request to the token endpoint with content type `application/x-www-form-urlencoded`. Example request:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Here, `<client-credentials>` is the Base64 representation of the client ID and client secret pair via HTTP Basic. This is only an illustrative example; the client can use another authentication method if supported by the Authorization Server, such as private key JWT or mTLS.

Do not send the client secret in the URL. OAuth 2.0 recommends client authentication via HTTP Basic when appropriate; sending credentials in the body should only be used when required by the Authorization Server and the client cannot use another supported method. All token exchanges must go over HTTPS/TLS.

According to OAuth 2.0 rules, `client_id` and `client_secret` are `application/x-www-form-urlencoded` encoded before joining with a colon and passing through HTTP Basic. OAuth2 libraries typically handle this step; when constructing the header manually, do not assume direct Base64 encoding of the two raw strings is always correct if credentials contain special characters.

Curl example using environment variables to avoid writing secrets directly into the command:

```bash
curl --request POST \
  --user "$OAUTH_CLIENT_ID:$OAUTH_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data "grant_type=client_credentials&scope=inventory.read" \
  https://identity.example.com/oauth2/token
```

Do not store real secrets in shell history, source code, or committed configuration files. In deployment environments, retrieve credentials from a secret manager or the platform's secret management mechanism.

## 5. Token response

The Authorization Server typically returns JSON similar to:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "inventory.read"
}
```

Common fields:

| Field | Meaning |
|---|---|
| `access_token` | Token the client uses to call the Resource Server |
| `token_type` | Token type; usually `Bearer` |
| `expires_in` | Token lifetime in seconds |
| `scope` | Granted scopes; may differ from the set of scopes requested by the client |
| `refresh_token` | Typically not issued for the Client Credentials grant |

The client must use the actual scopes in the response or token claims, rather than assuming the Authorization Server always grants all requested scopes. With Client Credentials, the client usually obtains a new access token when the token expires instead of using a refresh token.

## 6. Client Credentials does not represent a user

This is the most important distinction when choosing a grant type. A Client Credentials token represents an application or workload. It does not indicate that a specific end user logged in or consented to an action.

Suitable examples:

- `billing-service` calling an exchange rate API on a schedule.
- `analytics-job` reading aggregated data from multiple services.
- A partner's backend sending data under a machine-to-machine integration contract.
- A service calling an internal API with a read-only scope.

Unsuitable examples:

- A web application needing to access private data of the logged-in user.
- A mobile app needing to request access to resources on behalf of a user.
- An operation that needs to record end-user consent or identity.
- A client needing permissions that vary based on the current user's permissions.

In cases involving users, Authorization Code Flow with PKCE or another appropriate flow according to the Identity Provider architecture is usually needed. Do not use Client Credentials to simulate user login.

## 7. Distinguishing OAuth 2.0 Client Credentials, Authorization Code, and OIDC

| Criterion | Client Credentials | Authorization Code + PKCE | OpenID Connect |
|---|---|---|---|
| Represented principal | Client/service | Authenticated user and client | User authenticated via the OIDC layer |
| Interactive user login | No | Yes | Usually yes via Authorization Code |
| Used for | Machine-to-machine | Web, SPA, mobile, and user-facing apps | Login, verifying user identity |
| Redirect URI | Not needed | Yes | Usually present in OIDC login flow |
| ID Token | Not issued solely from using Client Credentials | Not a required component of pure OAuth2 | Core component of OIDC |
| Access Token | Yes | Yes | May be present to call APIs |

OAuth 2.0 is an authorization framework. OpenID Connect extends OAuth 2.0 to provide an authentication layer and an ID Token describing user identity. Client Credentials is typically used to authorize workloads; it is not an OIDC login flow and does not produce an ID Token just because the client uses OAuth2.

A system can use OIDC to log in employees while simultaneously using Client Credentials for service-to-service calls. The two flows serve different purposes and can coexist.

## 8. The client must be a confidential client

Client Credentials requires a client capable of keeping credentials secret or using another strong client authentication method. An application running completely in the browser or on a user's device cannot protect a client secret from the device user.

Suitable clients are typically:

- Backend servers.
- Workers or scheduled jobs running in controlled environments.
- Daemons or services within enterprise infrastructure.
- Workloads with platform-managed machine identities.

Do not embed a client secret in frontend JavaScript, mobile apps, or widely distributed desktop apps. If a public client needs to call an API on behalf of a user, use Authorization Code with PKCE and design tokens for the intended audience.

Besides client secrets, an Authorization Server may support stronger client authentication methods such as `private_key_jwt` or mutual TLS. The exact mechanism depends on the Authorization Server's capabilities and deployment policy.

## 9. Scopes and the principle of least privilege

Scopes describe the range of permissions a client requests. Examples:

| Scope | Illustrative permission |
|---|---|
| `inventory.read` | Read inventory information |
| `inventory.write` | Update inventory |
| `orders.read` | Read orders |
| `orders.export` | Export order data |

A client that only needs to read inventory should not be granted `inventory.write`. Grant minimal scopes to limit impact if credentials are exposed.

Scopes are a convention mutually understood by the Authorization Server and Resource Server. Scope names in OpenAPI must match the scopes issued by the Authorization Server and checked by the Resource Server. If the system uses custom claims/authorities instead of standard scopes, document that rule clearly.

Do not confuse scopes with user roles. Client Credentials represents a workload; its permissions are usually tied to the client, tenant, audience, or service policy.

## 10. Audience and restricting where tokens are used

Scopes answer what the client is allowed to do; audience determines which Resource Server the token was issued for. A token intended for `inventory-api` should not be accepted by `billing-api` if the token does not have the appropriate audience.

With JWTs, a Resource Server typically needs to check claims such as:

- `iss`: issuer that issued the token.
- `aud`: audience/Resource Server the token is intended for.
- `exp`: token expiration timestamp.
- `nbf`: timestamp when the token becomes valid, if present.
- `scope` or `scp`: granted permissions according to system conventions.
- `sub` or client identifier claim: client identity, as represented by the Authorization Server.

Not all Authorization Servers use the same claim names or mapping rules. Cross-check the actual configuration and verify audience on the Resource Server. Checking only the signature while skipping issuer, audience, expiration, or permissions can allow a cryptographically valid token that is inappropriate for the target API.

## 11. Describing Client Credentials in OpenAPI

OpenAPI describes Client Credentials using a Security Scheme Object of type `oauth2`, in which `flows.clientCredentials` contains `tokenUrl` and a list of scopes.

```yaml
components:
  securitySchemes:
    serviceClientAuth:
      type: oauth2
      description: OAuth2 Client Credentials for service-to-service
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            inventory.read: Read inventory information
            inventory.write: Update inventory information
```

Important fields:

- `type: oauth2`: this is an OAuth 2.0 security scheme.
- `flows.clientCredentials`: declares the Client Credentials grant type.
- `tokenUrl`: endpoint issuing access tokens.
- `scopes`: names and descriptions of permissions the client can request.
- `description`: guidance on usage context, how to register a client, and environment requirements.

`tokenUrl` is the URL of the Authorization Server, not the URL of the Resource Server. If the API runs on one host and the Authorization Server on another, declare the exact token endpoint published by the identity provider.

Do not include `client_secret` in an OpenAPI document. API documentation is often distributed to many consumers; client credentials must be managed outside the documentation.

## 12. Attaching scopes to operations with Security Requirement

After declaring the scheme, an operation needing inventory read access can reference the scope:

```yaml
paths:
  /api/inventory:
    get:
      operationId: listInventory
      security:
        - serviceClientAuth:
            - inventory.read
      responses:
        '200':
          description: Inventory list
        '401':
          description: Access token invalid or missing
        '403':
          description: Client lacks scope inventory.read
```

An operation updating inventory uses a different scope:

```yaml
  /api/inventory/{itemId}:
    put:
      operationId: updateInventory
      security:
        - serviceClientAuth:
            - inventory.write
      responses:
        '204':
          description: Inventory updated
```

The scope in Security Requirement must be one declared in the flow. OpenAPI only describes the required scope; the Authorization Server decides the actual granted scopes and the Resource Server must enforce the corresponding permissions.

## 13. Declaring the flow using springdoc annotations

Springdoc integrates Swagger Annotations to describe OAuth2 flows. Example:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "serviceClientAuth",
    type = SecuritySchemeType.OAUTH2,
    description = "OAuth2 Client Credentials for service-to-service",
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "inventory.read",
                    description = "Read inventory information"
                ),
                @OAuthScope(
                    name = "inventory.write",
                    description = "Update inventory information"
                )
            }
        )
    )
)
class OpenApiOAuthConfiguration {
}
```

Attach the scope to an operation:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@Operation(
    summary = "List inventory",
    security = @SecurityRequirement(
        name = "serviceClientAuth",
        scopes = {"inventory.read"}
    )
)
@GetMapping("/api/inventory")
List<InventoryItemResponse> listInventory() {
    return inventoryService.list();
}
```

The scheme name `serviceClientAuth` and scope `inventory.read` must match the declaration in `@SecurityScheme`. If using different scopes per operation, declare the corresponding requirement on each method or endpoint group.

## 14. Configuring Spring Boot as an OAuth2 Client

A Spring Boot service that needs to obtain tokens to call other APIs can use Spring Security OAuth2 Client. Declare registration and provider in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: company-identity
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          company-identity:
            token-uri: https://identity.example.com/oauth2/token
```

Explanation:

- `registration.inventory-service` is the registration name the application references.
- `client-id` and `client-secret` are loaded from environment variables or a secret manager.
- `authorization-grant-type: client_credentials` selects the right grant type.
- `scope` lists permissions the client requests.
- `provider.company-identity.token-uri` points to the token endpoint.

Do not commit real secret values into `application.yml`. In production environments, use a secret manager, workload identity, or the platform's credential provisioning mechanism. If the Authorization Server supports private key JWT or mTLS, consider using that method per security requirements.

## 15. Obtaining access tokens with `OAuth2AuthorizedClientManager`

Spring Security can manage the authorization process, store authorized client information, and refresh access tokens when needed. For backend applications or background jobs not tied to a user session, you can use `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class OAuth2ClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClientService
        );

        manager.setAuthorizedClientProvider(
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build()
        );

        return manager;
    }
}
```

When calling an API, ask the manager to authorize the registration:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

class InventoryApiClient {

    private final OAuth2AuthorizedClientManager authorizedClientManager;

    InventoryApiClient(OAuth2AuthorizedClientManager authorizedClientManager) {
        this.authorizedClientManager = authorizedClientManager;
    }

    String accessToken() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-service")
                .principal("inventory-service")
                .build();

        OAuth2AuthorizedClient client = authorizedClientManager.authorize(request);
        if (client == null) {
            throw new IllegalStateException("Unable to obtain access token");
        }

        return client.getAccessToken().getTokenValue();
    }
}
```

Then the client sends the token via the `Authorization: Bearer ...` header when calling the target API. In real applications, encapsulate adding the header in a shared HTTP client/interceptor, avoid handling tokens manually in multiple places, and avoid logging tokens.

`OAuth2AuthorizedClientManager` manages access token lifecycle per registration. You do not need to call the token endpoint manually for every business request; the provider can reuse valid tokens and request new tokens when needed.

## 16. Spring Boot as a Resource Server receiving Bearer tokens

Another application can act as a Resource Server. If the Authorization Server issues JWTs, add the appropriate OAuth2 Resource Server dependency and configure the issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
```

Configure the filter chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/inventory/**")
                            .hasAuthority("SCOPE_inventory.read")
                        .requestMatchers(HttpMethod.PUT, "/api/inventory/**")
                            .hasAuthority("SCOPE_inventory.write")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Spring Security normally maps scopes to authorities prefixed with `SCOPE_`. Therefore, the scope `inventory.read` can be checked with `hasAuthority("SCOPE_inventory.read")`. Mapping behavior can be customized; check the actual token claims and converter.

`issuer-uri` configures issuer verification and key discovery via metadata. If you need to verify a specific audience, add an appropriate validator; do not assume configuring only the issuer satisfies all security requirements of the system.

If the access token is opaque, configure opaque token introspection instead of a JWT decoder. OpenAPI still describes HTTP Bearer or the OAuth2 Client Credentials flow according to how the Authorization Server issues tokens.

## 17. Distinguishing OAuth2 Client and Resource Server

These two roles often appear together in service-to-service architectures, yet perform different tasks:

| Role | Main Configuration | Responsibility |
|---|---|---|
| OAuth2 Client | `spring.security.oauth2.client.registration` | Obtains and manages access tokens to call other APIs |
| Resource Server | `spring.security.oauth2.resourceserver` | Receives Bearer tokens, verifies tokens, and checks permissions |
| Authorization Server | Token issuance system | Authenticates clients and issues tokens according to policy |
| springdoc-openapi | `@SecurityScheme`, `@SecurityRequirement` | Describes flow, token URL, scopes, and operation requirements in documentation |

A service can be both an OAuth2 Client calling other services and a Resource Server receiving requests from other services. In that case, configure the two roles independently and avoid confusing client credentials used to obtain tokens with the access tokens the service issues/receives.

## 18. Swagger UI and Client Credentials

When OpenAPI declares `flows.clientCredentials`, Swagger UI can recognize the OAuth2 Client Credentials flow and display the necessary fields in the Authorize dialog, depending on the Swagger UI version bundled by springdoc.

However, Swagger UI runs in the browser. If a `client_secret` is entered into the UI, the secret is sent from the browser and can be read by the user, extensions, devtools, or controlled browser environments. Because Client Credentials is for confidential clients, do not use production client secrets in a public Swagger UI or in users' browsers.

If you need to test the flow via the UI:

- Use a separate Authorization Server and client for development/test environments.
- Create a client with restricted scopes, lifetime, and minimal permissions.
- Use a disposable or revocable secret; never use production credentials.
- Expose Swagger UI only to authorized users.
- Revoke test credentials after completion.

For real service-to-service testing, prefer a backend test client, curl in a secure environment, or integration tests using managed secrets. Do not embed `clientSecret` in frontend configuration or OpenAPI documentation.

Client Credentials does not need a redirect URI and does not use PKCE the way Authorization Code flow does. Do not configure `oauth2RedirectUrl` as if it were user login.

## 19. Handling token expiration, caching, and revocation

Access tokens usually have shorter lifetimes than client credentials. Clients should:

- Read `expires_in` or the expiration time from the token response.
- Reuse valid tokens instead of requesting a new token for every request.
- Refresh by performing the Client Credentials grant again when the token is expired or about to expire.
- Include a small safety margin before expiration to avoid token expiry mid-request.
- Handle `invalid_client`, `invalid_scope`, and token endpoint errors in an observable manner.
- Not retry indefinitely when the client secret is wrong or the client is disabled.

When client credentials are compromised, revoke or rotate the credentials at the Authorization Server, update the secret manager, and consider revoking active tokens if supported by the system. With self-contained JWTs, immediate revocation can be harder than with opaque tokens; short token lifetimes and denylist/introspection mechanisms may be part of the design.

## 20. Common error responses

The token endpoint and Resource Server have distinct groups of errors:

| Error | Source | Meaning |
|---|---|---|
| `invalid_client` | Token endpoint | Client authentication failed or client is invalid |
| `invalid_scope` | Token endpoint | Requested scope is invalid or not granted |
| `unsupported_grant_type` | Token endpoint | Authorization Server does not support the submitted grant type |
| `invalid_request` | Token endpoint | Missing or malformed parameters per the protocol |
| `401 Unauthorized` | Resource Server | Missing token, wrong token, expired, or invalid |
| `403 Forbidden` | Resource Server | Valid token but client lacks required scope/permissions |

Do not return client secrets, signature details, or internal details in error messages. Logs should record a correlation ID and traceable error code while redacting tokens and credentials.

## 21. Verifying configuration and the OpenAPI contract

After configuring OAuth2 Client, Resource Server, and springdoc, verify each part independently:

1. Confirm registration uses `authorization-grant-type: client_credentials`.
2. Confirm `token-uri` points to the right Authorization Server.
3. Confirm client ID/secret are loaded from a secret store or environment variables.
4. Call the token endpoint in a test environment and inspect the actual scopes granted.
5. Send the token to the Resource Server using a Bearer header.
6. Verify invalid/expired tokens return `401` and tokens lacking permission return `403` per policy.
7. Open `/v3/api-docs` or `/v3/api-docs.yaml`.
8. Confirm `components.securitySchemes.serviceClientAuth.type` is `oauth2`.
9. Confirm `flows.clientCredentials.tokenUrl` and scope list are accurate.
10. Confirm operations have `security` referencing the right scheme and scopes.
11. Verify Swagger UI displays the flow properly; do not use production secrets in the browser.
12. Run an OpenAPI validator and check client generators if the API is distributed to partners.

Example documentation should have a structure similar to:

```yaml
components:
  securitySchemes:
    serviceClientAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            inventory.read: Read inventory
paths:
  /api/inventory:
    get:
      security:
        - serviceClientAuth:
            - inventory.read
```

If documentation lists scope `inventory.read` while the Authorization Server issues a different scope name or the Resource Server does not check that scope, the contract and runtime will be inconsistent.

## 22. Common pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Token endpoint returns `invalid_client` | Wrong client ID/secret, mismatched authentication method, or disabled client | Check registration and client authentication method |
| Token endpoint returns `invalid_scope` | Scope not registered or not granted to client | Synchronize scopes across client, Authorization Server, and API |
| Client sends secret in URL | Misunderstanding how credentials are passed | Use client authentication over HTTPS via a server-supported method |
| API receives token but returns 401 | Issuer, signature, audience, or expiration is invalid | Check Resource Server configuration and claims |
| Valid token returns 403 | Client lacks required scope/authority | Adjust granted permissions or API's required scope |
| Swagger UI shows Authorize button but API call fails | OAuth2 flow misconfigured or runtime rejects token | Check token URL, client registration, and Resource Server |
| Client Credentials used for user login | Confusing client identity with user identity | Use Authorization Code + PKCE/OIDC for user flows |
| Client secret appears in JavaScript | Using a confidential client in the browser | Move token acquisition to backend or use an appropriate public-client flow |
| Token requested on every call | Not reusing authorized client/valid token | Use OAuth2AuthorizedClientManager and proper caching/lifecycle |
| Documentation declares scope but server skips check | Only describing OpenAPI without runtime authorization | Configure scope authorities and test endpoints |

## 23. Design principles

- Choose Client Credentials for workloads or services that need to call APIs using their own identity.
- Do not use this flow to represent end users or replace OIDC login.
- Use only confidential clients capable of protecting credentials or an equivalently strong client authentication method.
- Send token requests over HTTPS and never place secrets in URLs or source code.
- Grant minimal scopes and restrict token audience to the target Resource Server.
- Do not confuse Bearer with JWT; tokens can be JWT or opaque.
- Describe `flows.clientCredentials.tokenUrl` and scopes in OpenAPI; attach Security Requirements to the right operations.
- Do not put client secrets into OpenAPI documentation or public Swagger UI.
- Use Spring Security OAuth2 Client to obtain/manage tokens and Resource Server to verify tokens independently.
- Reuse valid tokens, obtain new tokens upon expiration, and maintain a credential rotation process.
- Verify the token endpoint, Resource Server, scopes, audience, and `/v3/api-docs` documentation.

## Conclusion

OAuth 2.0 Client Credentials fits machine-to-machine communication when a service needs to authenticate with its own identity to call an API. The client sends credentials to the token endpoint, receives an access token with granted scopes, and then uses the Bearer token to call the Resource Server. This flow does not log in users and does not issue an OIDC ID Token. In Spring Boot, OAuth2 Client manages token acquisition; Resource Server verifies tokens and permissions; springdoc-openapi describes the flow via `type: oauth2`, `flows.clientCredentials`, `tokenUrl`, and scopes. Use confidential clients, protect credentials, grant least privilege, and keep the OpenAPI contract aligned with Authorization Server and Resource Server policies.
