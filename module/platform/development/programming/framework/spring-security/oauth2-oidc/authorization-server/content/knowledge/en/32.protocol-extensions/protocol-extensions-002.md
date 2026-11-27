# Declaring AuthorizationGrantType and Registering Grants for Clients

## 1. Where Does AuthorizationGrantType Fit in OAuth 2.0?

OAuth 2.0 defines an authorization grant as a credential representing the authorization granted by the Resource Owner to the Client, or the Client's own authorization in certain flows. The Client sends the grant to the Token Endpoint to request an access token. Standard grants include Authorization Code, Client Credentials, and Refresh Token; OAuth 2.0 also allows extensions via **Extension Grants**.

In Spring Authorization Server (SAS), `AuthorizationGrantType` is the data type representing the value of the `grant_type` parameter. `RegisteredClient` stores the set of grants that a client is permitted to use. When configuring a client, you declare standard grants using built-in constants or instantiate a new `AuthorizationGrantType` for an extension grant.

`AuthorizationGrantType` holds the string value of the grant, provides `getValue()`, and compares using `equals`/`hashCode`. Therefore, you should define a shared constant and avoid scattering grant strings across multiple classes.

This lesson belongs to the **Protocol Extensions** chapter of the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module. It focuses on declaring grant types and registering grants for clients using Spring Authorization Server 1.5.8.

After this lesson, you will be able to:
1. Distinguish between authorization grant, grant type, client authentication method, and scope.
2. Read grant type values and know when to create a new `AuthorizationGrantType`.
3. Choose a stable identifier for an extension grant.
4. Register standard or custom grants on `RegisteredClient`.
5. Persist client registrations via `RegisteredClientRepository`.
6. Verify whether a client is permitted to use the requested grant.
7. Understand why registering a grant on a client alone does not enable the Token Endpoint to process the new grant.
8. Connect registration with `AuthenticationConverter` and `AuthenticationProvider` when implementing an extension grant.

## 2. Distinguishing Grant Type, Client Authentication Method, and Scope

Three concepts frequently appear together in a `RegisteredClient`, but they have distinct meanings:

| Component | Question It Answers | Examples |
| --- | --- | --- |
| **Authorization grant type** | Which flow may the client use to request a token? | `authorization_code`, `client_credentials`, custom extension URI |
| **Client authentication method** | How does the client prove its identity to the Token Endpoint? | `client_secret_basic`, `private_key_jwt`, `tls_client_auth`, `none` |
| **Scope** | Which access permissions may the client request? | `orders.read`, `orders.write`, `profile` |

For example, a confidential client might:
- Authenticate using `private_key_jwt`.
- Be permitted to use `client_credentials`.
- Only request the `orders.read` scope.

Grant type is not scope. Putting `partner_assertion` into scope does not register an authorization grant. Similarly, declaring `client_secret_basic` does not permit a client to use the `client_credentials` grant.

A valid Token Endpoint request must simultaneously satisfy:
- The client is authenticated using its registered authentication method.
- The grant type is supported by the Authorization Server.
- The grant type is in the allowed list for that specific client.
- The grant data and scopes are verified according to the flow's policy.

## 3. AuthorizationGrantType in Spring Security

`AuthorizationGrantType` belongs to the package:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
~~~

Commonly used standard constants:

| Constant | Protocol Value | Meaning |
| --- | --- | --- |
| `AUTHORIZATION_CODE` | `authorization_code` | Exchange an authorization code for tokens |
| `CLIENT_CREDENTIALS` | `client_credentials` | Client requests a token for itself |
| `REFRESH_TOKEN` | `refresh_token` | Exchange a refresh token for a new token |
| `DEVICE_CODE` | `urn:ietf:params:oauth:grant-type:device_code` | Device Authorization Grant |
| `JWT_BEARER` | `urn:ietf:params:oauth:grant-type:jwt-bearer` | JWT Bearer Grant |
| `TOKEN_EXCHANGE` | `urn:ietf:params:oauth:grant-type:token-exchange` | Token Exchange |

The exact set of constants depends on the Spring Security version used by SAS. Do not copy constants from documentation of a newer version into a project running an older version without checking the API.

For standard grants, use the built-in constants rather than constructing objects manually with the corresponding string:

The code below assumes `clientSecret` has been read from a secret manager and `PasswordEncoder` is configured:

~~~java
RegisteredClient registeredClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();
~~~

Using constants makes the code's intent clear and prevents typos. When you need an extension grant without a standard constant, construct the object using the constructor that takes the string value.

## 4. Choosing an Identifier for an Extension Grant

RFC 6749, Section 4.5, requires clients to specify an extension grant using an **absolute URI** in the Token Endpoint's `grant_type` parameter. This URI is defined by the Authorization Server. The request may include additional parameters required to convey the authorization grant.

Illustrative identifier example:

~~~text
https://auth.example.com/oauth/grants/partner-assertion
~~~

An HTTPS URI or URN may be used, provided it is an absolute URI and managed stably. When choosing an identifier:
- Use a namespace under your organization's control.
- Pick a unique value that does not collide with standard grants or partner extensions.
- Keep the identifier unchanged once client registrations and authorization records have been persisted.
- Do not use temporary URLs, dev environment hostnames, or values that change across versions.
- Do not embed secrets, tenant credentials, or sensitive data into the identifier.
- Document the grant's semantics, parameters, validation rules, and protocol errors.

The identifier is a protocol value sent verbatim by the client in `grant_type`; it is not an endpoint URL for the client to invoke directly. The server is not required to serve a web page at this URI.

If the identifier changes, the client, Authorization Server, database, integration tests, monitoring, and metadata must all be updated in lockstep. In practice, treat the identifier as a long-term protocol contract.

### 4.1. Declaring Custom Grant Constants

~~~java
package com.example.authorizationserver.grants;

import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class PartnerAssertionGrantTypes {

    public static final String PARTNER_ASSERTION_VALUE =
            "https://auth.example.com/oauth/grants/partner-assertion";

    public static final AuthorizationGrantType PARTNER_ASSERTION =
            new AuthorizationGrantType(PARTNER_ASSERTION_VALUE);

    private PartnerAssertionGrantTypes() {
    }
}
~~~

The example uses `auth.example.com` for documentation purposes. In real deployments, replace it with a stable namespace managed by your organization. Place the constant in a shared package used across registration, the Token Endpoint converter/provider, and tests to avoid defining different strings in multiple places.

### 4.2. Do Not Create a Custom Grant If a Standard Grant Fits

Before creating a new identifier, check standardized OAuth/OIDC flows and extensions. For example, if the use case is Token Exchange, evaluate RFC 8693 and the `token-exchange` grant available in the corresponding version. Creating a custom grant similar to a standard reduces interoperability and forces clients into custom integrations.

## 5. Registering Grants for Clients with RegisteredClient.Builder

`RegisteredClient` is the metadata model of a client registered with the Authorization Server. The `authorizationGrantTypes` field is the set of grants that the client may use. SAS provides `authorizationGrantType(...)` to add a grant to the builder.

Example of a partner client permitted to use `client_credentials` and the `partner_assertion` extension grant:

~~~java
import org.springframework.core.env.Environment;

@Bean
RegisteredClient partnerGateway(PasswordEncoder passwordEncoder, Environment environment) {
    String partnerSecret = environment.getRequiredProperty("app.clients.partner-gateway.secret");
    return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("partner-gateway")
            .clientSecret(passwordEncoder.encode(partnerSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
            .scope("orders.read")
            .scope("orders.status")
            .build();
}
~~~

This snippet is a configuration example; `partnerSecret` must be supplied from a secret manager or protected configuration source—never hard-code raw secrets in source code.

Key points to note:
- `withId(...)` accepts the internal registration ID, which differs from `clientId(...)` used on the protocol wire.
- `authorizationGrantType(...)` can be called multiple times to add multiple grants.
- `authorizationGrantTypes(Consumer<Set<AuthorizationGrantType>>)` allows adding, replacing, or removing elements in the grant set.
- `scope(...)` declares the scopes permitted to be requested; it does not register a grant.
- `clientAuthenticationMethod(...)` declares how the client authenticates; it also does not register a grant.
- Only grant extension grants to clients that genuinely need them.

### 5.1. Only Register Extension Grants for Approved Clients

Do not add custom grants to all clients by default. You can separate registrations by trust tier:

~~~java
RegisteredClient webClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("customer-portal")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.example.com/login/oauth2/code/customer")
        .scope("openid")
        .scope("profile")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();

RegisteredClient partnerClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("partner-gateway")
        .clientSecret(passwordEncoder.encode(partnerSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
        .scope("orders.read")
        .build();
~~~

The portal uses Authorization Code + PKCE. Only the Partner Gateway is granted the extension grant. Separating clients helps limit the blast radius if credentials or grant-specific authorizations are compromised.

These are builder fragments inside a registration service; `passwordEncoder` and `partnerSecret` are injected from the application's configuration/secret manager.

Do not grant a custom grant to a public client simply because the client requests it. Determine whether the flow can be executed safely with that client type, and whether the client can adequately protect and present the grant proof.

## 6. Registering Clients in the Repository

After constructing a `RegisteredClient`, the Authorization Server needs to persist it via `RegisteredClientRepository`. The repository is used during client authentication, authorization grant processing, token introspection, and other protocol flows.

Simple example for development/testing:

~~~java
import org.springframework.core.env.Environment;

@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder, Environment environment) {
    String clientSecret = environment.getRequiredProperty("app.clients.partner-gateway.secret");
    RegisteredClient partnerClient = RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("partner-gateway")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
            .scope("orders.read")
            .build();

    return new InMemoryRegisteredClientRepository(partnerClient);
}
~~~

`InMemoryRegisteredClientRepository` is suitable for demos, testing, or small applications with a static registration lifecycle. In-memory data is lost on process restart and is not shared across instances.

For production, `JdbcRegisteredClientRepository` or another durable storage implementation is typically used. Example of initializing the JDBC repository:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(JdbcOperations jdbcOperations) {
    return new JdbcRegisteredClientRepository(jdbcOperations);
}
~~~

The database must contain the `oauth2-registered-client-schema.sql` schema matching the SAS version in use. If using a custom repository, the implementation must faithfully preserve grant types, authentication methods, redirect URIs, scopes, and settings when writing and reading registrations.

### 6.1. Verifying Persisted Registrations

After saving a client, read it back from the repository and verify the grant is in the allowed set:

~~~java
RegisteredClient saved = registeredClientRepository.findByClientId("partner-gateway");

if (saved == null ||
        !saved.getAuthorizationGrantTypes()
                .contains(PartnerAssertionGrantTypes.PARTNER_ASSERTION)) {
    throw new IllegalStateException("Partner assertion grant is not registered");
}
~~~

This check is useful in integration tests, startup validation, or onboarding workflows. Do not leave registration verification solely in tests if clients can be dynamically created or updated after application startup.

## 7. Registering Grants in Dynamic Client Registration

If the Authorization Server supports Dynamic Client Registration (DCR), the client registration request may contain `grant_types` metadata. This is the list of grants the client declares it intends to use. The DCR endpoint must validate each value and only accept grants that the server supports and that policy allows for that client.

Example metadata:

~~~json
{
  "client_name": "Partner Gateway",
  "grant_types": [
    "client_credentials",
    "https://auth.example.com/oauth/grants/partner-assertion"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "orders.read"
}
~~~

The AS must not treat client-submitted `grant_types` values as permissions granted automatically. The registration process must:
1. Authenticate the registrar or Initial Access Token per policy.
2. Verify the client owner, software statement, or trust tier if applicable.
3. Check that each grant type is in the Authorization Server's allowlist.
4. Determine whether the extension grant is permitted for this client type and authentication method.
5. Save the approved set of grants into `RegisteredClient`.
6. Return the server-accepted metadata.

If the DCR endpoint does not support custom grants, reject them or handle them according to published policy. Do not silently ignore an unrecognized grant and respond to the client as though it were registered.

DCR and custom grants are two separate capabilities:
- DCR creates/updates client registrations.
- The extension grant implementation processes token issuance requests.
- DCR might allow registering a grant name, yet the Token Endpoint still requires the corresponding converter/provider.

## 8. Reading the Grant List from RegisteredClient

At runtime, token request processing code needs access to the authenticated `RegisteredClient` to determine which grants the client is authorized to use.

~~~java
Set<AuthorizationGrantType> allowedGrantTypes =
        registeredClient.getAuthorizationGrantTypes();

boolean allowed = allowedGrantTypes.contains(
        PartnerAssertionGrantTypes.PARTNER_ASSERTION
);

if (!allowed) {
    throw new OAuth2AuthenticationException(
            OAuth2ErrorCodes.UNAUTHORIZED_CLIENT
    );
}
~~~

This is a per-client allowlist check. `registeredClient` must be obtained from the client principal authenticated by Spring Security; do not look up by an arbitrary `client_id` from the form body and trust the result as proof of client authentication.

When a client submits a grant type:
- If the server does not support that grant, the Token Endpoint cannot process it and typically returns `unsupported_grant_type`.
- If the server has a provider but the client has not been granted that grant, the provider must reject the client with `unauthorized_client`.
- If the grant artifact is malformed, expired, has the wrong audience, or was replayed, return `invalid_grant` per the extension's semantics.
- If parameters are missing/extra or improperly duplicated, return `invalid_request`.

Do not rely on client UI or client-side configuration to enforce permissions. The Authorization Server must re-verify authorization server-side on every token request.

## 9. Token Endpoint Request with an Extension Grant

Once the client has the grant registered, it sends a token request to the Token Endpoint. For the partner assertion example, the request might look like:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64(partner-gateway:CLIENT_SECRET)
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=https%3A%2F%2Fauth.example.com%2Foauth%2Fgrants%2Fpartner-assertion&assertion=SIGNED_PARTNER_ASSERTION&scope=orders.read
~~~

In the request:
- `grant_type` must match the exact identifier declared in `PartnerAssertionGrantTypes`.
- `assertion` is the grant-specific data defined by the extension; in this example, a signed assertion.
- The client authenticates using its registered method, here `client_secret_basic`.
- `scope` contains only scopes the client is allowed to request and the grant provider permits issuing.

The client must not send an arbitrary new URI or invent a grant name. The client and Authorization Server must agree on the exact same identifier and parameter contract.

A successful response still follows the OAuth 2.0 access token response format:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read"
}
~~~

Token values are placeholders. If the extension issues refresh tokens, the server must define a clear refresh policy and also register the `refresh_token` grant for the client if the client is allowed to use that flow.

## 10. Token Endpoint Requires AuthenticationConverter and AuthenticationProvider

SAS processes the Token Endpoint through a pipeline:

~~~mermaid
flowchart LR
    A[HTTP POST /oauth2/token] --> B[Client authentication]
    B --> C[AuthenticationConverter chain]
    C --> D[Custom grant Authentication token]
    D --> E[AuthenticationProvider]
    E --> F[Validate client grant allowlist]
    F --> G[Validate grant artifact and policy]
    G --> H[OAuth2TokenGenerator]
    H --> I[Persist OAuth2Authorization]
    I --> J[OAuth2 access token response]
~~~

Two main components:

**AuthenticationConverter**
- Reads the HTTP request and determines whether it matches the custom `grant_type` this converter handles.
- If it is not its grant, returns `null` so another converter can process it.
- Validates required parameters, duplicate parameters, and format.
- Creates a dedicated `Authentication` object representing the custom grant.
- Retrieves the client principal from `SecurityContext` after client authentication has executed.

**AuthenticationProvider**
- Receives the custom grant `Authentication` token.
- Confirms the client has been authenticated.
- Reads `RegisteredClient` from the client principal.
- Verifies the grant type is in `RegisteredClient.getAuthorizationGrantTypes()`.
- Verifies the assertion/credential and extension policy.
- Generates the access token, persists the authorization, and returns the result to the Token Endpoint.

Separating the converter and provider decouples HTTP request parsing from grant verification business logic. Do not place all validation and token issuance inside a custom controller and bypass the standard Token Endpoint pipeline.

### 10.1. Converter Only Matches Its Own Grant

Converter logic pattern:

~~~java
public Authentication convert(HttpServletRequest request) {
    String grantType = request.getParameter(OAuth2ParameterNames.GRANT_TYPE);

    if (!PartnerAssertionGrantTypes.PARTNER_ASSERTION_VALUE.equals(grantType)) {
        return null;
    }

    String assertion = request.getParameter("assertion");
    if (!StringUtils.hasText(assertion) ||
            request.getParameterValues("assertion").length != 1) {
        throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
    }

    Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

    return new PartnerAssertionGrantAuthenticationToken(
            clientPrincipal, assertion, extractAdditionalParameters(request));
}
~~~

This is an illustrative skeleton; `PartnerAssertionGrantAuthenticationToken` and `extractAdditionalParameters(...)` are application-defined components. In actual implementation:
- Use `getParameterValues` to detect required parameters appearing multiple times.
- Exclude `grant_type`, `client_id`, and already-processed parameters from additional parameters.
- Do not trust `client_id` in the form body over the authenticated client principal.
- Do not log raw assertions.
- Do not swallow errors for other grants; return `null` when the converter is not responsible for the request.

### 10.2. Provider Must Check the Client's Allowlist

Before verifying the grant artifact, the provider must verify that the client is authenticated and authorized to use the grant:

~~~java
RegisteredClient registeredClient = authenticatedClient.getRegisteredClient();

if (!registeredClient.getAuthorizationGrantTypes()
        .contains(PartnerAssertionGrantTypes.PARTNER_ASSERTION)) {
    throw new OAuth2AuthenticationException(OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
}
~~~

If the grant is not in the client's grant set, stop processing immediately. Do not assume that because the converter recognized `grant_type`, the client is permitted to use it.

## 11. Configuring the Extension Grant on the OAuth2 Token Endpoint

After creating the converter and provider, register them in the Authorization Server configuration:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                .accessTokenRequestConverter(
                        new PartnerAssertionGrantAuthenticationConverter())
                .authenticationProvider(
                        new PartnerAssertionGrantAuthenticationProvider(
                                authorizationService, tokenGenerator))
            )
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

SAS provides `accessTokenRequestConverter(...)` and `authenticationProvider(...)` as Token Endpoint extension points. These two calls add custom components to the existing pipeline. If you have multiple custom grants, register multiple converters/providers accordingly or use the consumer to manage the list.

The application still needs foundational beans such as:
- `RegisteredClientRepository` to read client registrations.
- `OAuth2AuthorizationService` to save authorizations and tokens.
- `OAuth2TokenGenerator` to issue access tokens/refresh tokens.
- JWK source and token encoder if issuing JWTs.
- Security filter chain and client authentication configuration for the Token Endpoint.

Do not treat the filter chain above as a complete standalone Authorization Server configuration.

## 12. AuthenticationProvider Responsibilities When Issuing Tokens

The provider does not stop at checking the client grant allowlist. It must verify the authorization grant itself according to the designed contract.

For a JWT-based partner assertion, verification steps may include:
1. Verify the signature using a trusted issuer's key.
2. Check `iss`, `aud`, `exp`, `iat`, and required claims.
3. Check whether the subject/partner identity is permitted for the current client.
4. Check that the assertion has not been reused; if `jti` is present, use an atomic replay store.
5. Check that requested scopes lie within the scopes allowed by the client and grant policy.
6. Determine the principal and granted permissions.
7. Generate the access token with appropriate audience, claims, lifetime, and token type.
8. Save the authorization to support introspection, revocation, and refresh if the flow allows it.

Do not accept an assertion just because its payload decodes. You must verify signature, issuer, audience, timestamps, and replay according to the profile. For grants using one-time codes/assertions, consuming the grant must be atomic so two concurrent requests cannot exchange one grant for two tokens.

### 12.1. Creating OAuth2TokenContext

The provider uses `OAuth2TokenGenerator` together with `OAuth2TokenContext` to create the token. Core pattern:

~~~java
OAuth2TokenContext tokenContext = DefaultOAuth2TokenContext.builder()
        .registeredClient(registeredClient)
        .principal(clientPrincipal)
        .authorizationServerContext(AuthorizationServerContextHolder.getContext())
        .tokenType(OAuth2TokenType.ACCESS_TOKEN)
        .authorizedScopes(authorizedScopes)
        .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
        .authorizationGrant(partnerAssertionAuthentication)
        .build();

OAuth2Token generatedAccessToken = tokenGenerator.generate(tokenContext);
if (generatedAccessToken == null) {
    throw new OAuth2AuthenticationException(new OAuth2Error(OAuth2ErrorCodes.SERVER_ERROR));
}
~~~

After generating the token, the provider constructs `OAuth2AccessToken`, attaches the token to `OAuth2Authorization` along with claims metadata if the token is a JWT, and calls `OAuth2AuthorizationService.save(...)`. Persisting the authorization allows the server to manage the token lifecycle consistently with standard grants.

Condensed example of creating the authorization after the token has been generated and `authorizedScopes` validated:

~~~java
OAuth2AccessToken accessToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        generatedAccessToken.getTokenValue(),
        generatedAccessToken.getIssuedAt(),
        generatedAccessToken.getExpiresAt(),
        authorizedScopes
);

OAuth2Authorization authorization = OAuth2Authorization
        .withRegisteredClient(registeredClient)
        .principalName(clientPrincipal.getName())
        .authorizationGrantType(PartnerAssertionGrantTypes.PARTNER_ASSERTION)
        .authorizedScopes(authorizedScopes)
        .accessToken(accessToken)
        .build();

authorizationService.save(authorization);
~~~

The snippet above is illustrative; a complete implementation needs to:
- Verify the client principal has the expected type and is authenticated.
- Persist the principal name, registered client ID, and authorization grant type.
- Persist claims metadata when the token generator returns a token with claims.
- Handle refresh tokens only when permitted by grant/policy.
- Return `OAuth2AccessTokenAuthenticationToken` to the Token Endpoint.
- Avoid storing raw assertions unless required; if stored for audit, encrypt or store a fingerprint.

## 13. Distinguishing Grant Registration from Token Issuance

| Configuration Step | Result | Enough to Use Custom Grant? |
| --- | --- | --- |
| Create `AuthorizationGrantType` | Have an object representing the identifier | No |
| Add to `RegisteredClient` | Client is allowlisted for the grant | No |
| Save via `RegisteredClientRepository` | Server can read the registration | No |
| Register `AuthenticationConverter` | Token Endpoint can parse requests | Not yet sufficient |
| Register `AuthenticationProvider` | Have verification and token issuance logic | Needs to be paired with converter |
| Configure token generator and authorization service | Can issue and persist tokens | Needs complete policy/validation |

A client may have `partner_assertion` registered, yet requests will still fail if:
- The server has not installed the converter/provider.
- The client has not authenticated.
- The provider rejects that client.
- The assertion is invalid or has been replayed.
- Requested scopes exceed granted permissions.
- The token generator does not support the requested token type.

This is why registration and the Token Endpoint must be tested as two distinct layers.

## 14. Managing Grant Types Across the Client Lifecycle

A grant type is security-sensitive client metadata. When adding or removing a grant:
- Verify the owner, use case, and business justification.
- Assess whether the grant requires a confidential client or sender-constrained credentials.
- Check grant-specific scopes and resource/audience.
- Update `RegisteredClient` via a transactional repository.
- Synchronize metadata across nodes/caches.
- Audit the actor, client ID, old grant, new grant, and timestamp of the change.
- Evaluate whether authorizations/tokens already issued under the old grant need to be revoked.

Do not automatically grant custom grants to every new client. If DCR is enabled, the validator must apply the same allowlist and policy as static registration.

When removing a grant from `RegisteredClient`, the provider may still remain registered on the Token Endpoint. The provider must check the allowlist on every request so the client loses access immediately after the registration updates. Do not merely hide the grant in the client UI or discovery metadata.

If changing the identifier, treat it as a protocol migration:
1. Create a new identifier and new provider.
2. Decide on a compatibility window between the two identifiers.
3. Only register the new grant for migrated clients.
4. Monitor usage of the old identifier.
5. Revoke the old grant after the transition period.
6. Remove the old provider once no clients/authorizations use it.

## 15. Testing Matrix for Declaring and Using Grants

| Scenario | Action | Expected Result |
| --- | --- | --- |
| Built-in grant | Register `client_credentials` | Grant appears in `RegisteredClient` |
| Custom grant | Register Partner Assertion | Custom grant is stored with exact URI |
| Wrong identifier | Create `AuthorizationGrantType` with different URI | Does not match allowlist |
| Duplicate registration | Add the same grant multiple times | Grant set does not create distinct permissions |
| Client disallowed | Client without custom grant sends request | `unauthorized_client` |
| Provider missing | Client has grant but server lacks provider | `unsupported_grant_type` or corresponding endpoint error |
| Converter mismatch | Request uses another grant | Custom converter returns `null`, standard converter proceeds |
| Missing assertion | Missing required parameter | `invalid_request` |
| Duplicate assertion | Send assertion multiple times | `invalid_request` |
| Invalid signature | Assertion signed with untrusted key | `invalid_grant` |
| Wrong issuer/audience | Assertion not intended for AS/client | `invalid_grant` |
| Expired assertion | Assertion has expired | `invalid_grant` |
| Replay | Resend one-time assertion | Subsequent request is rejected |
| Scope escalation | Request scope outside allowlist | Rejected |
| Repository restart | Restart with JDBC repository | Grant is still read accurately |
| Client update | Remove custom grant from registration | Provider rejects client on next request |
| Concurrent redemption | Two requests use the same assertion | Only one request consumes successfully |

Tests must verify both the HTTP response and persisted state. For example, a rejected request must not create an active authorization or token record.

### 15.1. Checking Registration in Unit/Integration Tests

A focused test can verify that the grant type was added properly:

~~~java
@Test
void partnerClientHasPartnerAssertionGrant() {
    RegisteredClient client = registeredClientRepository
            .findByClientId("partner-gateway");

    assertThat(client).isNotNull();
    assertThat(client.getAuthorizationGrantTypes())
            .contains(PartnerAssertionGrantTypes.PARTNER_ASSERTION);
}
~~~

An integration test for the Token Endpoint should also verify:
- Client authentication actually succeeds.
- The request is recognized by the custom grant's converter.
- The provider verifies the assertion and checks the grant allowlist.
- The authorization is persisted via `OAuth2AuthorizationService`.
- The access token has the right claims/audience and only permitted scopes.
- Replays or invalid assertions do not generate new tokens.

Do not only test that the `Set` in `RegisteredClient` contains the custom grant. That test confirms registration, but does not prove the extension grant works end-to-end from HTTP request to token response.

## 16. Scenario Exercise

A B2B system has an Authorization Server and multiple partner gateways. The gateways need to send a JWT assertion signed by a partner system to obtain an access token for reading orders. The Authorization Server names the extension grant:

~~~text
https://auth.example.com/oauth/grants/partner-assertion
~~~

Only clients `partner-gateway-a` and `partner-gateway-b` are allowed to use this grant. Client `customer-portal` only uses Authorization Code + PKCE.

Analyze:
1. Why must `partner-assertion` be an absolute URI?
2. Which package should `AuthorizationGrantType` be declared in and how should it be shared?
3. How do you register the grant for the two partner gateways using `RegisteredClient.Builder`?
4. Why should the grant not be assigned to `customer-portal`?
5. How do you ensure the client has already been authenticated before the provider reads the assertion?
6. Which claims of the JWT assertion must the provider validate?
7. How do you prevent replay when a partner sends the same assertion twice?
8. If the client requests `orders.write` while only permitted `orders.read`, what must the outcome be?
9. Why is adding the grant to `RegisteredClient` alone insufficient for the Token Endpoint to issue tokens?
10. When revoking the grant from a partner gateway, how must the repository/cache/provider be synchronized?

**Hint:** Use a single `AuthorizationGrantType` constant across registration, converter, provider, and tests. `RegisteredClient` acts as the per-client allowlist; the provider must still enforce that allowlist at runtime. The assertion needs signature, issuer, audience, expiration, and replay verification. Grant only minimal scopes and never let public clients use flows requiring credentials they cannot protect.

## 17. Implementation Checklist

1. **Protocol:** check whether a standard grant exists or an extension grant is needed.
2. **Identifier:** use a stable, unique absolute URI under a managed namespace.
3. **Constant:** declare a single shared `AuthorizationGrantType` constant in code.
4. **Client allowlist:** add the grant only to approved `RegisteredClient` entries.
5. **Client authentication:** choose an authentication method matching the client type and threat model.
6. **Scopes:** separate scopes from grant types; apply least privilege.
7. **Persistence:** persist grants via `RegisteredClientRepository`; use JDBC/custom durable repositories in production.
8. **DCR:** validate `grant_types` against the server allowlist and client policy.
9. **Converter:** parse requests for the target grant, detect missing/duplicate parameters, and do not log credentials.
10. **Provider:** verify client, grant allowlist, grant artifact, issuer/audience/time/replay.
11. **Token issuance:** build token context, generate token, and persist authorization.
12. **Error handling:** distinguish `unsupported_grant_type`, `unauthorized_client`, `invalid_grant`, and `invalid_request`.
13. **Lifecycle:** audit grant changes and synchronize caches/clusters.
14. **Testing:** test registration, token endpoint, replay, scope escalation, and persistence.
15. **Documentation:** publish parameter contract, identifier, client eligibility, scopes, token claims, and errors.

## 18. Standards and Spring References

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.5 Extension Grants](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.5): absolute URI in `grant_type` and extension grant requests.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): modern OAuth security guidance when selecting grants and authenticating clients.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): standard grant for token exchange use cases.
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): converter, provider, Token Endpoint configuration, and custom grant requests.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenEndpointConfigurer` and extension points.
- [Spring Authorization Server 1.5.8 — RegisteredClient.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.Builder.html): `authorizationGrantType` and `authorizationGrantTypes`.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient` and `RegisteredClientRepository`.
- [Spring Security — AuthorizationGrantType API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/AuthorizationGrantType.html): constructor, built-in constants, and `getValue()`.

**Remember:** `AuthorizationGrantType` represents the identifier of an authorization grant. `RegisteredClient.Builder.authorizationGrantType(...)` registers the grant in a client's allowlist; it does not implement token issuance logic itself. For a custom extension grant, you need a stable absolute URI identifier, a converter to parse requests, and a provider to verify the grant, check the client allowlist, issue tokens, and persist authorizations. Always keep grant type separate from client authentication method and scope, grant it only to appropriate clients, and enforce permissions server-side on the Authorization Server for every token request.
