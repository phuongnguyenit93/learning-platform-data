# OAuth 2.0 Dynamic Client Registration and OIDC Client Registration

## 1. Objectives and Context

In the **Dynamic Client Registration** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, OAuth 2.0 clients usually have to be registered in advance at the Authorization Server (AS). The traditional approach requires an administrator or provisioning process to create the client and configure redirect URIs, grant types, scopes, and client authentication methods. When there are many applications, tenants, deployment environments, or partner-developed software, a manual process can become a bottleneck.

**Dynamic Client Registration (DCR)** allows a client or client-developing organization to send metadata to a Registration Endpoint so the AS creates a client registration and returns the identifier along with the necessary configuration. For OpenID Connect (OIDC), the registration protocol is defined in **OpenID Connect Dynamic Client Registration 1.0**. OAuth 2.0 has a compatible standard in **RFC 7591**; post-registration client configuration management is extended by **RFC 7592**.

**Spring Authorization Server (SAS)** supports the OIDC Client Registration Endpoint via `OidcClientRegistrationEndpointConfigurer`. This endpoint is disabled by default; when enabled, it provides registration and Client Read handling according to the SAS implementation. Dynamic registration must still be controlled with access tokens, metadata validation, persistence, and appropriate authorization policies.

After this lesson, you will be able to:

- Distinguish between static client registration, OAuth 2.0 DCR (RFC 7591), and OIDC Client Registration 1.0.
- Understand the roles of the Client Registration Endpoint, Initial Access Token, Registration Access Token, and Registration Client URI.
- Read and construct registration requests/responses according to the JSON metadata contract.
- Distinguish OIDC Client Read from update/delete operations in RFC 7592.
- Enable `clientRegistrationEndpoint` in `OAuth2AuthorizationServerConfigurer`.
- Configure a registrar client, `client.create`, `client.read`, and `JwtDecoder`.
- Map metadata to `RegisteredClient` and persist it using `RegisteredClientRepository`.
- Customize converters/providers/validators to support custom metadata while preserving default validation.
- Protect redirect URIs, grant types, scopes, client authentication, software statements, and registration credentials.
- Design lifecycle management, revocation, auditing, abuse limits, and DCR testing for production environments.

**Version scope:** The example code targets **Spring Authorization Server 1.5.x**, **Spring Security 6.x**, and **Spring Boot 3.x**; some APIs may differ in 1.0/1.1 or subsequent releases. Current Spring documentation describes SAS 1.5.8. Protocol rules are based on RFC 7591, RFC 7592, and OpenID Connect Dynamic Client Registration 1.0 incorporating errata set 2. Inspect responses and test the actual endpoint of your dependency version before publishing an integration contract.

## 2. Why Do We Need Dynamic Client Registration?

An OAuth2 client needs metadata so the AS knows how to process requests and issue tokens. Typical metadata includes valid redirect URIs, response types and grant types, requested scopes, the client authentication method at the Token Endpoint, application type (web/native), the client's JWK Set or JWKS URI if using private key JWT/request signing, display information, and OIDC options.

With static registration, operators create the configuration beforehand and hand `client_id` to the development team. With DCR, this process is performed over an HTTP/JSON protocol.

### 2.1. Static registration vs. dynamic registration

| Criterion | Static registration | Dynamic registration |
| --- | --- | --- |
| Client creation | Admin/provisioning creates manually or via internal API | Client/registrar sends a registration request |
| Client ID issuance | Operational workflow | AS issues upon successful registration |
| Metadata changes | Via admin/config deployment | Via registration workflow or supported client configuration endpoint |
| Control | Easy to tie to existing approval workflows | Must design initial access tokens, policies, and rate limits |
| Best suited for | Few clients, known partner identities | Many deployments/tenants, automated onboarding |
| Risks | Manual misconfiguration or drift | Registration spam, spoofed metadata, redirect URI abuse, credential leakage |

DCR does not automatically make an application a trusted client. The AS must still decide who is allowed to register, what metadata is accepted, and which grants/scopes the client is permitted to use.

### 2.2. Suitable Scenarios

- A SaaS platform issues a dedicated client per tenant after tenant onboarding completes.
- A product integrates with many partners, each having its own redirect URIs and keys.
- Software is deployed across many organizations with different callback URLs.
- An OIDC relying party needs to register metadata with an OpenID Provider using a standard protocol.
- A provisioning portal issues a scoped registration token to a developer or deployment agent.

### 2.3. When Should Public DCR Not Be Opened?

Open registration allows anyone to submit metadata without an Initial Access Token. This may suit certain ecosystems, but it creates cost and risk: attackers create large numbers of clients; clients spoof brand names/logos; metadata contains attacker-controlled redirect URIs; stale registrations are hard to classify; and the AS does not know who is responsible without a developer identity/attestation.

For enterprise platforms, **protected dynamic registration** is usually a safer starting point: only authorized registrars/developers receive an Initial Access Token to register clients.

## 3. Standards and Protocol Boundaries

Three specifications are often mentioned together, though they have different scopes.

| Standard | Role | Scope |
| --- | --- | --- |
| RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol | Defines OAuth2 client registration using JSON metadata | Registration request/response, client metadata, and Initial Access Token |
| OpenID Connect Dynamic Client Registration 1.0 | Defines how an OIDC RP registers with an OP and reads registration info | OIDC client metadata, registration response, Client Configuration Endpoint, and Client Read |
| RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol | Extends registration management after creation | Reading, updating, and deleting client registrations using a Registration Access Token |

OIDC Registration 1.0 is compatible with RFC 7591 and defines the Client Configuration Endpoint for the **GET Client Read** operation. RFC 7592 adds management operations such as PUT/DELETE. Do not assume an OIDC Client Registration Endpoint supports all of RFC 7592 simply because the response contains `registration_client_uri`.

### 3.1. DCR Is Not the Client Credentials Grant

The two concepts are related but serve different purposes:

- `client_credentials` is an OAuth2 grant for a client to obtain an access token to access a resource.
- DCR is a protocol to create a client registration at the AS.
- A registrar client can use `client_credentials` to obtain an **Initial Access Token** carrying the `client.create` scope.
- The newly created client has its own grant types and authentication methods in its registration metadata.

DCR does not itself issue a user session and does not replace the Authorization Code Flow or other grants.

### 3.2. OIDC Registration Endpoint and Discovery

An OIDC Provider Configuration may publish the `registration_endpoint` field. An RP can retrieve the URL from the discovery document instead of hard-coding the endpoint.

Do not append `/connect/register` to the issuer and assume every deployment uses the default path. Verify the metadata published by the OP, TLS, and the issuer before calling.

## 4. Registration Lifecycle

A typical protected registration flow:

```mermaid
sequenceDiagram
    autonumber
    participant D as Developer / Deployment Agent
    participant R as Registrar Client
    participant AS as Authorization Server
    participant DB as RegisteredClientRepository
    participant C as Newly Registered Client

    D->>R: Request permission to provision client
    R->>AS: Token request: client_credentials + client.create
    AS-->>R: Initial Access Token
    R->>AS: POST registration_endpoint + Bearer token + JSON metadata
    AS->>AS: Validate token, metadata and policy
    AS->>DB: Persist RegisteredClient
    AS-->>R: 201 Created + client_id + credentials + registration metadata
    AS-->>R: registration_access_token + registration_client_uri
    R->>C: Deliver client credentials securely
    C->>AS: Normal OAuth/OIDC flow using assigned client_id
    C->>AS: GET registration_client_uri + registration access token
    AS-->>C: Current client registration metadata
```

Stages:

1. The developer or deployment system is approved.
2. The registrar client obtains an Initial Access Token.
3. The registrar sends metadata to the Client Registration Endpoint.
4. The AS validates the access token, redirect URIs, grants, scopes, auth method, and policy.
5. The AS creates a `RegisteredClient` and saves it to the repository.
6. The AS returns the registration response; the client stores credentials securely.
7. The client uses the assigned `client_id` and authentication method.
8. The client can read its own registration if the AS issues a Registration Access Token and Client Configuration Endpoint.

### 4.1. Three Identifiers/Credentials Not to Confuse

| Value | Issued By | Used For | Scope |
| --- | --- | --- | --- |
| `client_id` | AS | Identifying the client in OAuth/OIDC requests | Not a secret |
| Initial Access Token | AS or provisioning workflow | Authorizing the registrar to call the registration endpoint | Grants client creation permission per policy |
| Registration Access Token | AS after registration if supported | Authenticating Client Configuration/Read requests | Bound to one registration |
| `client_secret` | AS if the client is confidential and the method requires a secret | Client authentication at the Token Endpoint | Client's secret |
| `registration_client_uri` | AS | Exact URL for the client to read its registration configuration | Not a credential; must be paired with the Registration Access Token |

Both the Initial Access Token and the Registration Access Token can be bearer tokens, but they have **different purposes and permissions**. Do not use an Initial Access Token to call business APIs; do not use a client secret in place of a Registration Access Token.

## 5. Client Metadata: What Can a Client Request to Register?

A registration request is a JSON object with top-level metadata. Example:

```json
{
  "application_type": "web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ],
  "response_types": ["code"],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "client_name": "Partner Portal",
  "client_uri": "https://portal.example.com",
  "policy_uri": "https://portal.example.com/privacy",
  "tos_uri": "https://portal.example.com/terms",
  "token_endpoint_auth_method": "private_key_jwt",
  "jwks_uri": "https://portal.example.com/.well-known/jwks.json",
  "scope": "openid profile email"
}
```

This is an illustrative request. The AS may reject metadata, substitute allowed values, apply defaults, or ignore unsupported fields. The client must read the registration response and use the **values accepted by the AS**, rather than treating every value in the request as approved configuration.

### 5.1. Important Metadata Groups

| Metadata | Meaning | Control Notes |
| --- | --- | --- |
| `redirect_uris` | Registered callbacks | Required in OIDC registration; must be strictly validated |
| `response_types` | Response types the client intends to use | Do not enable implicit flow without a clear compatibility reason |
| `grant_types` | Grant types the client intends to use | Grant only the minimum required |
| `application_type` | `web` or `native` | Affects redirect URI rules |
| `client_name` | Display name | Not proof of software identity |
| `logo_uri` | Logo URL | Can be abused for brand impersonation or tracking |
| `client_uri` | Client website | Validate scheme/host and display rights |
| `policy_uri` / `tos_uri` | Privacy policy / terms | Must be valid, verifiable URLs |
| `token_endpoint_auth_method` | How the client authenticates at the Token Endpoint | Must be in the AS-supported allowlist |
| `jwks_uri` | Client's JWK Set URL | HTTPS, validate remote key source / SSRF |
| `jwks` | JWK Set sent directly | Public keys only; never accept private/symmetric keys |
| `scope` | Scopes requested by the client | AS still enforces policies and restricts permissions |
| `subject_type` | `public` or `pairwise` | Only when supported by the OP and allowed by metadata policy |
| `sector_identifier_uri` | Source of redirect URI list for pairwise subjects | Must validate HTTPS and JSON document |
| `contacts` | Contact addresses of responsible parties | Contact PII; restrict access |
| `software_statement` | JWT metadata attestation signed by publisher | Must verify signature, issuer, audience, and expiration |

### 5.2. Grant Types and Response Types Must Be Consistent

For OIDC Authorization Code Flow:

```json
{
  "response_types": ["code"],
  "grant_types": ["authorization_code", "refresh_token"]
}
```

`response_types` describes the response type at the Authorization Endpoint; `grant_types` describes the grant at the Token Endpoint. For example, `code` corresponds to `authorization_code`.

Do not add `client_credentials` simply because the registrar client uses that grant. The registrar and the new client are two separate registrations. The new client should only receive the grants needed for its use case.

### 5.3. Web Clients and Native Clients

- Web confidential clients typically authenticate using `private_key_jwt`, mTLS, or a backend-protected client secret.
- Native apps are public clients; do not embed a shared client secret into distributed binaries.
- Public clients should use Authorization Code + PKCE with `S256`.
- Production web redirect URIs should use HTTPS.
- Native loopback redirects may use localhost/loopback according to rules for native apps.
- Do not treat `application_type` as proof of a confidential/public client; auth method and deployment model must be evaluated separately.

### 5.4. JWK Metadata

If a client uses `private_key_jwt` or signs requests, the AS needs public keys to verify them. `jwks_uri` points to the client's public JWK Set. Never accept private key fields or symmetric secrets in a JWK Set.

When using `jwks_uri`, the AS must control remote fetching: HTTPS, DNS, redirects, response size, timeouts, and private network addresses. If the client sends `jwks` directly, the server must still validate key type, algorithm, and intended use.

## 6. OIDC Registration Request and Response

### 6.1. HTTP Request

The client sends a POST with JSON content type:

```http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer <INITIAL_ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json

{
  "application_type": "web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code", "refresh_token"],
  "client_name": "Partner Portal",
  "token_endpoint_auth_method": "private_key_jwt",
  "jwks_uri": "https://portal.example.com/.well-known/jwks.json",
  "scope": "openid profile email"
}
```

The endpoint path in the example is the commonly used SAS default. Production must use the `registration_endpoint` published in OIDC discovery or an administrator-confirmed URL.

### 6.2. Registration Response

On success, the OIDC registration endpoint typically returns HTTP `201 Created` and JSON containing the registered metadata along with values issued by the AS:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "client_id": "portal-tenant-42",
  "client_id_issued_at": 1790000000,
  "client_secret": "REDACTED_IF_ISSUED",
  "client_secret_expires_at": 1792592000,
  "registration_access_token": "REDACTED_REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=portal-tenant-42",
  "application_type": "web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_method": "private_key_jwt",
  "scope": "openid profile email"
}
```

These fields are illustrative; SAS is not guaranteed to return every field. `client_secret` only appears when the client method/type requires a secret. If the server issues a client secret, `client_secret_expires_at` must be handled according to the contract; a value of `0` indicates the secret does not expire according to OIDC registration metadata.

### 6.3. The Server May Normalize Metadata

The AS may reject an invalid field, apply defaults for omitted fields, substitute certain permissible values, ignore unsupported fields, or restrict grants, scopes, response types, and authentication methods according to policy.

For `redirect_uris`, never arbitrarily replace them with URIs not registered by the client and never relax validation. The client should read the response to know the exact stored configuration.

### 6.4. Error Response

A registration error is usually HTTP `400 Bad Request` with a JSON error, for example:

```json
{
  "error": "invalid_redirect_uri",
  "error_description": "One or more redirect URI values are invalid"
}
```

Possible errors:

- `invalid_redirect_uri`: invalid redirect URI.
- `invalid_client_metadata`: an invalid metadata field.
- `invalid_token`/Bearer error: invalid or expired Initial Access Token.
- Server/storage error: AS could not complete registration.

Do not return stack traces, secrets, internal token information, or data belonging to other clients in the error description.

## 7. Initial Access Token: Protecting Client Creation Permissions

RFC 7591 allows the AS to require an Initial Access Token to restrict which parties may register. OIDC Registration 1.0 also describes this token as an optional provisioning mechanism. How the token is issued and validated is outside the specification's scope; organizations must define their own process.

### 7.1. Registrar Client

A registrar client is a pre-configured client that performs provisioning. Example:

```java
RegisteredClient registrarClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("platform-registrar")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
```

This is an SAS configuration example. In production, use a random secret and a secret manager; do not use `{noop}` or guessable secrets; let only the provisioning service hold registrar credentials; scope registrars by organization/tenant/environment; monitor every created registration; and do not grant `client.create` to regular business clients.

### 7.2. Obtaining an Initial Access Token in SAS

The SAS how-to uses `client_credentials` and requires the token request to have **only the `client.create` scope**:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <BASE64_REGISTRAR_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
```

After receiving the access token, the registrar uses it as a Bearer token at the registration endpoint.

**SAS 1.5.x specific behavior:** the SAS guide notes that this Initial Access Token is single-use; after a client is successfully registered, the token is invalidated. This is an implementation detail of the SAS guide and should not be generalized as a requirement for every DCR server.

### 7.3. Do Not Combine the Read Scope into the Initial Access Token

The SAS guide requires the registration token to have only the single `client.create` scope. Configuring the registrar client with `client.read` as well does not mean the registration token is allowed to carry both scopes.

Keep the token used to create a client (`client.create`) clearly separate from the token used to read a registration (`client.read`) per SAS's Registration Access Token/client configuration mechanism.

### 7.4. Initial Token Issuance Workflow

A provisioning workflow can:

1. Verify the developer/organization via a portal or CI workload identity.
2. Generate a short-lived Initial Access Token.
3. Bind the token to the required tenant, environment, quota, and policy.
4. Deliver the token via a secret channel to the deployment agent.
5. Audit issuance metadata without logging the raw token.
6. Allow the token to be used for the exact allowed count/duration.
7. Revoke the token if the workflow is canceled or compromise is detected.

Do not issue a single permanent Initial Access Token shared across all developers.

## 8. Registration Access Token and Client Configuration Endpoint

After registration, the response may contain `registration_access_token` and `registration_client_uri`. The Registration Access Token is a credential with access to the registration; it must be protected like a secret.

### 8.1. Client Read

OIDC Registration 1.0 defines GET Client Read:

```http
GET /connect/register?client_id=portal-tenant-42 HTTP/1.1
Host: auth.example.com
Authorization: Bearer <REGISTRATION_ACCESS_TOKEN>
Accept: application/json
```

**The client must use the exact URL in `registration_client_uri`** returned by the AS. Do not construct the URL by appending paths or modifying query parameters. The AS may use path parameters, query parameters, or a custom URL structure. If the AS returns `registration_client_uri`, that URL must use HTTPS and the response must also return `registration_access_token`; never return only one of the two values.

The response is typically HTTP `200 OK` and returns the current registration metadata. Do not cache registration responses containing secrets or registration access tokens in insecure locations.

### 8.2. Client Read Is Not Update/Delete

OIDC Registration 1.0 defines the GET operation for Client Read. RFC 7592 extends DCR management with registration update and delete operations using the Registration Access Token.

According to the SAS 1.5.8 documentation, `OidcClientRegistrationEndpointFilter` handles Client Registration and Client Read; default providers include `OidcClientRegistrationAuthenticationProvider` and `OidcClientConfigurationAuthenticationProvider`. Do not assume an SAS endpoint supports RFC 7592 PUT/DELETE if your version/application has not implemented and tested those operations.

### 8.3. Permissions of the Registration Access Token

- Use only for the corresponding registration.
- Do not use as an access token for business APIs.
- Do not send in URLs/query strings.
- Do not log in application logs, tracing, or support tickets.
- Have a revoke/rotate procedure if exposed.
- The client must store `registration_client_uri` alongside credentials in appropriate secret storage.

If the token is lost, do not allow recovering the registration using only the public `client_id`. Require admin recovery or an authenticated provisioning workflow.

## 9. Enabling the OIDC Client Registration Endpoint in SAS

OIDC must be enabled in the Authorization Server configurer, and then the Client Registration Endpoint must be enabled explicitly. The OIDC Client Registration Endpoint is **disabled by default**, since not every deployment needs DCR.

### 9.1. Configuring SecurityFilterChain

```java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(oidc ->
                            oidc.clientRegistrationEndpoint(
                                    Customizer.withDefaults())))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a configuration skeleton. The application still needs infrastructure beans such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, key sources, user authentication, and an appropriate `AuthorizationServerSettings`.

### 9.2. Registering JwtDecoder

SAS requires a `JwtDecoder` for the OIDC Client Registration Endpoint. If the application already has a `JWKSource<SecurityContext>`, you can create the decoder as follows:

```java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration
            .jwtDecoder(jwkSource);
}
```

Do not omit the decoder just because the endpoint is already in the Authorization Server filter chain. The endpoint needs to verify the Bearer access token before processing registration/read requests.

### 9.3. Endpoint Path

The default path is typically `/connect/register`. It can be configured via `AuthorizationServerSettings`:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcClientRegistrationEndpoint("/connect/register")
            .build();
}
```

If you change the endpoint path, you must synchronize discovery metadata, gateways, reverse proxies, client registrars, and integration tests. Clients should obtain the URL from `registration_endpoint` or trusted configuration rather than hard-coding the default.

### 9.4. The Endpoint Is a Protected Resource

According to the SAS 1.5.8 documentation:

- A Client Registration request requires a Bearer access token with the `client.create` scope.
- A Client Read request requires an access token with the `client.read` scope.
- A `JwtDecoder` bean is required.
- The endpoint filter uses default converters/providers to handle registration and read.

This is the behavior of the SAS implementation described in the documentation, not a description of every server supporting open DCR under RFC 7591.

## 10. Configuring the Registrar and Persistence

### 10.1. RegisteredClientRepository

SAS uses `RegisteredClientRepository` to store and retrieve client registrations. Simple test examples may use `InMemoryRegisteredClientRepository`, but production should use durable persistence, such as `JdbcRegisteredClientRepository` or a suitable implementation.

```java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcTemplate jdbcTemplate) {
    return new JdbcRegisteredClientRepository(jdbcTemplate);
}
```

This snippet assumes the SAS schema is deployed and the datasource is configured. An in-memory repository is suitable for simple demos/tests; it does not share state across replicas and loses registrations on process restart.

### 10.2. Mapping Metadata to RegisteredClient

The registration provider converts OIDC metadata into a `RegisteredClient` via a converter. Key information is stored in the client ID, client secret handled per credential storage policy (usually hashed), client authentication methods, authorization grant types, redirect URIs, scopes, client settings, token settings, and extended metadata in settings if the application uses a custom converter.

Do not store the entire JSON request in a single column and use it as the sole source of truth for authorization. The AS needs a registration model with explicit types and validation.

### 10.3. Client ID Must Be Unique

`client_id` is issued by the AS and must be unique within the AS scope. Do not use an email, tenant name, or display name as the client ID if they can change or collide. The database's internal registration ID and the public `client_id` are two separate concepts.

### 10.4. Client Secret Storage

If registration creates a confidential client with a secret, generate a high-entropy secret, store it hashed using `PasswordEncoder`, never log the secret, deliver it only to the rightful owner over a secure channel, enforce an expiry/rotation policy, and never issue a secret for public clients using `none` authentication.

Do not confuse the new client's secret with the registrar client's secret.

## 11. Customizing Validation and Providers in SAS

`OidcClientRegistrationEndpointConfigurer` provides extension points for pre-processing, main processing, and post-processing.

| Extension point | API | Responsibility |
| --- | --- | --- |
| Request conversion | `clientRegistrationRequestConverter` | Converts HTTP request into registration authentication |
| Converter collection | `clientRegistrationRequestConverters` | Adds/replaces converters in the list |
| Provider | `authenticationProvider` | Adds a provider to handle registration/read |
| Provider collection | `authenticationProviders` | Customizes the default provider list |
| Success handler | `clientRegistrationResponseHandler` | Builds the HTTP registration/read response |
| Error handler | `errorResponseHandler` | Returns registration/read errors |

Do not replace the entire pipeline if you only need to add a metadata check. Keeping the default converters/providers preserves protocol parsing and handling.

### 11.1. Customizing Provider Validators

The SAS guide illustrates configuring validators for `OidcClientRegistrationAuthenticationProvider`. The following example preserves the standard validators for redirect URI, post-logout redirect URI, JWK Set URI, and scope:

```java
private Consumer<List<AuthenticationProvider>>
        configureRegistrationValidators() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                OidcClientRegistrationAuthenticationProvider registrationProvider) {

            registrationProvider.setAuthenticationValidator(
                    OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_REDIRECT_URI_VALIDATOR
                            .andThen(
                                    OidcClientRegistrationAuthenticationValidator
                                            .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                            .andThen(
                                    OidcClientRegistrationAuthenticationValidator
                                            .DEFAULT_JWK_SET_URI_VALIDATOR)
                            .andThen(
                                    OidcClientRegistrationAuthenticationValidator
                                            .SIMPLE_SCOPE_VALIDATOR));
        }
    });
}
```

Then configure it in the DSL:

```java
authorizationServer.oidc(oidc ->
        oidc.clientRegistrationEndpoint(endpoint ->
                endpoint.authenticationProviders(
                        configureRegistrationValidators())));
```

Validator class/method names must be checked against your dependency version. The example above illustrates chaining standard validators; when replacing validators, ensure you do not accidentally drop other mandatory validations of the version in use.

### 11.2. Adding Custom Metadata

Suppose the platform wants to store `logo_uri` or `contacts`. Both directions must be extended:

1. Convert OIDC registration metadata into `RegisteredClient` or client settings.
2. Convert `RegisteredClient` back into an OIDC registration response on Client Read.

The SAS guide illustrates the converters:

- `OidcClientRegistrationRegisteredClientConverter`: OIDC registration → RegisteredClient.
- `RegisteredClientOidcClientRegistrationConverter`: RegisteredClient → OIDC registration.
- `OidcClientRegistrationAuthenticationProvider`: configures the registered-client converter and response converter.
- `OidcClientConfigurationAuthenticationProvider`: configures the converter for Client Read.

Do not save custom fields only during registration while forgetting the response/read path; otherwise, the client will not be able to read back its registered configuration.

### 11.3. Example of Configuring Provider Converters

Configuration skeleton for SAS 1.5.x API:

```java
private Consumer<List<AuthenticationProvider>>
        configureCustomMetadataConverters(
                Converter<OidcClientRegistration, RegisteredClient>
                        registeredClientConverter,
                Converter<RegisteredClient, OidcClientRegistration>
                        clientRegistrationConverter) {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setRegisteredClientConverter(
                    registeredClientConverter);
            registrationProvider.setClientRegistrationConverter(
                    clientRegistrationConverter);
        }

        if (provider instanceof
                OidcClientConfigurationAuthenticationProvider configurationProvider) {
            configurationProvider.setClientRegistrationConverter(
                    clientRegistrationConverter);
        }
    });
}
```

The passed converters are application-built implementations or delegates from the default converters. This is an integration skeleton; verify constructors and packages for your version. Only store allowlisted and validated metadata; do not copy arbitrary fields into client settings.

### 11.4. Custom Metadata Does Not Automatically Become Permissions

For example, `tenant_id` or `billing_plan` may be stored in registration settings, but client-submitted values must not be treated as authoritative. The server must verify the tenant/plan from the provisioning system. A client must not self-declare `tenant_id` to move itself to another tenant or elevate its own privileges.


## 12. Software Statements and Attestation

RFC 7591 supports `software_statement` as a JWT containing metadata signed by a software publisher or authority. It can help the AS verify software provenance and attested metadata.

A software statement can carry software identifier/version, publisher/organization, redirect URI claims, approved grant types/scopes, JWK information or policy references, issuance/expiration times, and a statement identifier.

### 12.1. Verifying a Software Statement

Do not trust a JWT just because it parses. The AS must verify:

- Signature using a key from a trusted publisher/authority.
- `iss` and `aud` per the trust contract.
- `exp`, `iat`, and allowed lifetime.
- `jti` or replay controls if required by the profile.
- Whether metadata inside the statement matches the request.
- Whether the publisher is permitted to register this client type.
- Whether the statement has been revoked or the signer compromised.

### 12.2. SAS and software_statement

SAS supports extending metadata via converters/providers, but you should not assume every software statement profile is automatically verified just because the OIDC DCR endpoint is enabled. If attestation is needed, implement an explicit validator/trust service before persisting the registration.

Do not use a signed `software_statement` as an excuse to skip redirect URI validation or registrar authorization. Attestation is an additional trust signal; the AS must still enforce its own policies.

## 13. Redirect URI: The Most Critical Security Boundary

The Redirect URI determines where the Authorization Server sends the authorization response. If an attacker registers a redirect URI they control, they can capture authorization codes or token responses in misconfigured flows.

### 13.1. Exact Matching

- Compare the request redirect URI against the registered value per protocol rules.
- Do not use arbitrary domain wildcards.
- Do not accept prefix matching like `https://trusted.example.com.attacker.test`.
- Do not strip paths/queries when comparing.
- Do not allow clients to alter redirect URIs in authorization requests.
- Revalidate when a client updates metadata.

### 13.2. Web and Native Redirect URIs

| Client type | Typical Redirect URI | Policy |
| --- | --- | --- |
| Web | Client-controlled HTTPS callback | Do not allow arbitrary HTTP in production |
| Native | Custom URI scheme or appropriate loopback redirect | Apply native app rules and PKCE |
| SPA/browser-based public client | HTTPS callback | Use Authorization Code + PKCE; do not embed secrets |

`localhost` is not a workaround to bypass validation for web confidential clients. Loopback redirects are a specific case for native applications under the corresponding profile.

### 13.3. Do Not Allow Wildcards for Deployment Convenience

Dangerous examples:

```text
https://*.example.com/callback
https://example.com/*
https://portal.example.com/callback*
```

Wildcards can open the door to subdomain takeover or redirects to applications outside your control. If the platform needs multiple tenant hosts, register each exact redirect URI after verifying domain ownership or use a dedicated domain onboarding workflow.

### 13.4. Post-Logout Redirect URI

If OIDC logout is supported, `post_logout_redirect_uris` must also be validated and bound to the registration. Do not blindly reuse the redirect URI allowlist for logout; the two endpoints can have different contracts and validators.

## 14. Restricting Grants, Scopes, and Client Authentication

DCR is where security principals are created for OAuth flows. A metadata request must not independently grant permissions beyond AS policy.

### 14.1. Grant Allowlist

Example where a platform only allows Authorization Code and Refresh Token:

```text
Allowed:
authorization_code
refresh_token

Denied unless explicitly approved:
implicit
password
client_credentials
device_code
custom_grant
```

This is an example policy, not a mandatory OIDC grant list. The registrar must verify each grant type and business use case before saving.

### 14.2. Scope Allowlist

- Clients may only request scopes within the allowed catalog.
- High-privilege scopes require separate approval.
- Do not automatically grant all scopes submitted by the client.
- Scopes in metadata do not replace user consent/authorization when granting access.
- Clients cannot add scopes by altering Token Endpoint requests after registration.

### 14.3. Token Endpoint Authentication Method

| Method | Suitable For | Notes |
| --- | --- | --- |
| `client_secret_basic` | Confidential web/backend clients | Secret must be protected |
| `client_secret_post` | Legacy compatibility when needed | Secret is in the form body; avoid if unnecessary |
| `private_key_jwt` | Workloads/backends with a private key | AS needs a verified public JWKS |
| `tls_client_auth` | Workloads with an mTLS identity | Manage certificate lifecycle |
| `none` | Public clients | No client secret; require PKCE for Authorization Code |

Do not accept an auth method just because its name appears in the request. Verify that the method is supported by the AS and permitted for the client type.

### 14.4. PKCE

For public clients, require PKCE, preferring `S256`. Do not allow a client to drop PKCE simply by registering different metadata if AS policy requires a proof key.

With SAS, you can configure `ClientSettings.requireProofKey` for created registrations. Ensure converters/policies map metadata and defaults appropriately for the client type.

## 15. Protecting Remote Metadata and Preventing SSRF

Some metadata fields contain URLs accessed by the AS or admin console, such as `jwks_uri`, `sector_identifier_uri`, `logo_uri`, `client_uri`, `policy_uri`, and `tos_uri`.

Not every URL needs to be fetched by the server. However, if a backend, validator, image proxy, or admin UI fetches client-provided URLs, SSRF and malicious content must be mitigated.

### 15.1. URL Controls

- Require HTTPS for key/sector metadata URIs per the corresponding standards.
- Block loopback, private IP, link-local, and cloud metadata addresses when the backend fetches.
- Validate DNS resolution and guard against DNS rebinding.
- Limit redirects; never follow redirects to disallowed hosts.
- Set connect/read timeouts and response size caps.
- Validate content type/schema.
- Disallow `file` schemes or unnecessary protocols.
- Do not trust logo images or client names as proof of identity.

### 15.2. JWK Set

- Accept public keys only.
- Validate `kty`, `use`, `key_ops`, `alg`, key size, and allowlisted algorithms.
- Disallow internal key URLs.
- Cache with TTL and support rotation.
- Verify keys belong to the approved client registration.
- Never use a client's JWK set to verify tokens signed by the AS.

### 15.3. Metadata Display

Client name, logo, website, and policy URI may be displayed on the consent page. Attackers can use spoofed names/icons to impersonate other applications. Display verified publisher/organization details, bind registrations to developer accounts/tenants, distinguish self-declared names from attested names, verify domain ownership, never render raw HTML from metadata, and use a safe image proxy or allowlist when loading logos.

## 16. Persistence, Updates, and Deprovisioning

### 16.1. Shared Storage Across Multiple AS Instances

In a cluster, every node must see the same registration state. If each node uses its own in-memory repository:

- A client created on node A may not exist on node B.
- The Token Endpoint may return `invalid_client` depending on the node.
- Client Read may return different metadata.
- Revocation/disable policies become inconsistent.

Production requires a shared durable store, backups, schema migrations, indexing by client ID, and proper transactions.

### 16.2. Updating a Registration

If implementing RFC 7592 update or a custom admin update:

- Authenticate the proper Registration Access Token or admin identity.
- Allow modifying only policy-approved metadata.
- Never change the client ID.
- Validate new redirect URIs before committing.
- Use optimistic locking/versioning to avoid lost updates.
- Audit before/after metadata without logging secrets.
- Consider revoking prior authorizations/tokens when security-sensitive fields change.

### 16.3. Deleting or Disabling a Client

Deprovisioning is more than deleting a row. The process should consider:

1. Marking the client disabled or stopping new grant issuance.
2. Revoking associated authorizations/refresh tokens per policy.
3. Ensuring current access tokens are rejected according to the validation model.
4. Revoking the Registration Access Token and client secret.
5. Deleting or archiving metadata per retention policy.
6. Auditing who requested it and why.
7. Ensuring all AS replicas and Resource Server caches receive the change.

If Resource Servers verify JWTs offline, disabling a client at the AS does not immediately invalidate all already-issued JWTs. Introspection, denylists, event invalidation, or appropriate access token TTLs are needed.

### 16.4. Client Secret Rotation

When a secret is compromised or expires:

- Verify the caller's authorization to request rotation.
- Issue the new secret through a secure process.
- Allow a bounded overlap period if zero-downtime is required.
- Revoke the old secret after the transition window.
- Update client secret storage.
- Never put the new secret in logs or tickets.
- Monitor client auth failures after rotation.

Do not use Client Read as a rotation operation. OIDC Client Read is a read operation; updates/rotations must follow a server-supported mechanism protected separately.

## 17. End-to-End Example with curl

### 17.1. Obtaining an Initial Access Token

Assuming the registrar is already registered:

```bash
curl -i -X POST "https://auth.example.com/oauth2/token" \
  -u "platform-registrar:REDACTED_REGISTRAR_SECRET" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=client.create"
```

Use the returned access token as the Initial Access Token. Per the SAS guide, the token has only the `client.create` scope.

### 17.2. Registering a Client

```bash
curl -i -X POST "https://auth.example.com/connect/register" \
  -H "Authorization: Bearer REDACTED_INITIAL_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{
    "application_type": "web",
    "redirect_uris": [
      "https://portal.example.com/login/oauth2/code/partner"
    ],
    "response_types": ["code"],
    "grant_types": ["authorization_code", "refresh_token"],
    "client_name": "Partner Portal",
    "token_endpoint_auth_method": "private_key_jwt",
    "jwks_uri": "https://portal.example.com/.well-known/jwks.json",
    "scope": "openid profile email"
  }'
```

Do not store raw Initial Access Tokens in shell history, CI output, or process logs. In automation, pull credentials from a secret manager and redact request headers.

### 17.3. Reading the Registration

Use the exact `registration_client_uri` from the response:

```bash
curl -i \
  -H "Authorization: Bearer REDACTED_REGISTRATION_ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://auth.example.com/connect/register?client_id=portal-tenant-42"
```

The URL above is illustrative. The client must use the actual URI returned by the AS, rather than building query parameters from the example.

## 18. Testing DCR in Spring Boot

### 18.1. Unit Tests for Metadata Policy

Test redirect URIs matching the allowlist, redirect URIs with wrong host/path/scheme, grant types outside the allowlist, over-privileged scopes, public clients declaring a secret authentication method, confidential clients missing a credential strategy, non-HTTPS JWKS URIs or private addresses, JWK Sets containing private/symmetric keys, software statements with invalid signature/issuer/audience/expiry, custom metadata outside the allowlist, and domain/tenant mismatches.

### 18.2. Registration Integration Test

MockMvc example verifying successful registration:

```java
@Test
void registerClientWithInitialAccessToken() throws Exception {
    mockMvc.perform(post("/connect/register")
            .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + initialAccessToken)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "application_type": "web",
                  "redirect_uris": [
                    "https://portal.example.com/callback"
                  ],
                  "response_types": ["code"],
                  "grant_types": ["authorization_code"],
                  "client_name": "Portal",
                  "token_endpoint_auth_method": "private_key_jwt",
                  "jwks_uri": "https://portal.example.com/jwks.json",
                  "scope": "openid profile"
                }
                """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.client_id").isNotEmpty())
        .andExpect(jsonPath("$.registration_access_token").isNotEmpty())
        .andExpect(jsonPath("$.registration_client_uri").isNotEmpty())
        .andExpect(jsonPath("$.redirect_uris[0]")
                .value("https://portal.example.com/callback"));
}
```

This is a skeleton. The test context needs the SAS security chain, `JwtDecoder`, JWK source, registrar client, token store, and persistent `RegisteredClientRepository`. Response fields depend on configuration and client type.

### 18.3. Testing the Initial Access Token

| Test | Expected |
| --- | --- |
| No Bearer token sent | Rejected via bearer authentication |
| Expired token | Rejected |
| Token missing `client.create` | Registration rejected |
| Token has extra scopes beyond `client.create` per SAS guide | Registration rejected |
| Using the Initial Access Token a second time | Rejected per SAS guide's one-time behavior |
| Registrar not authorized to create clients | Rejected per authorization policy |

### 18.4. Testing Client Read

| Test | Expected |
| --- | --- |
| Valid Registration Access Token + correct URI | HTTP 200 and registration metadata |
| Expired/invalid token | Bearer error |
| Client A's token accessing registration B | Cannot read registration B |
| Missing `client.read` scope | Rejected |
| Client Read response | Does not mutate the registration |
| Registration URI with modified query/path | Do not use a self-built URL; use the server-returned URI |

### 18.5. Security and Operational Tests

- Concurrent registration requests do not produce duplicate client IDs.
- Registrations remain readable after an AS restart.
- Client created on node A is recognized by node B.
- Database failures do not return false success responses.
- Rate limits operate per registrar/tenant.
- Raw tokens/secrets never appear in logs.
- Domain/tenant isolation is enforced.
- Deprovisioning disables clients according to policy.
- Key rotation does not break registrar token verification.
- Metadata discovery publishes the correct registration endpoint.

## 19. Observability and Lifecycle Governance

### 19.1. Metrics

Track successful/failed registration counts, errors by type, registration rate per registrar/tenant, active/disabled client counts, registration/read latency, idle client ratio, token misuse counts, client secret expiry/rotation failures, and post-provisioning client authentication failures.

Never use raw access tokens, client secrets, or registration access tokens as metric labels.

### 19.2. Auditing

Audit records can store the authenticated registrar identity, tenant/organization, issued client ID, modified metadata field names and policy decisions, approved redirect domains, timestamp/correlation ID/approval reference, and software publisher/statement identity if present.

Never log raw secrets/tokens. Restrict who can view contact metadata and developer-identifying information.

### 19.3. Cleanup and Inventory

- Owner and business purpose for each registration.
- Environment/tenant tags.
- Expiration or review date.
- Procedure to disable unused clients.
- Reports on redirect domains and auth methods.
- Checks for duplicate registrations.
- Retention/archival for audit records and client metadata.
- Recovery workflow if a client loses its registration access token.

DCR can create many short-lived clients. Without inventory and cleanup, the registry will accumulate orphaned clients whose ownership is unknown.

## 20. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `/connect/register` returns 404 | OIDC Client Registration Endpoint not enabled or wrong path | Check `clientRegistrationEndpoint` and `AuthorizationServerSettings` |
| Returns 401/invalid_token | Missing Initial Access Token, invalid/expired token, or decoder cannot verify | Check Bearer token, issuer/JWKS, and `JwtDecoder` |
| Returns 403/scope error | Token missing `client.create` or has scopes violating contract | Obtain a token with the required scope |
| `client.create` and `client.read` mixed up | Registrar token carries wrong scopes | Separate the registration token and registration access token |
| `invalid_redirect_uri` | Invalid URI or violates policy | Check scheme/host/path and application type |
| `invalid_client_metadata` | Invalid grant, auth method, JWKS, or metadata | Check validators and allowlists |
| Client created but Token Endpoint returns invalid_client | Registration not persisted or auth method/secret mapping mismatch | Check repository and converters |
| Client Read returns 401 | Wrong/expired Registration Access Token or wrong URL | Use the token and URI from the response |
| Client Read returns stale data | Converter does not round-trip custom metadata | Check bidirectional converters |
| Custom metadata is lost | Only registration converter was updated, not read converter | Update both the registration provider and configuration provider |
| SAS endpoint fails to start | Missing `JwtDecoder` | Register a decoder from `JWKSource` |
| Duplicate Client IDs across nodes | Faulty ID generation/repository uniqueness | Use UUID/random IDs and DB unique constraints |
| One node cannot see new clients | In-memory/local repository | Use a shared persistent repository |
| Secrets appear in logs | Request/response body logging | Redact and disable body logging for the endpoint |
| Registration spam | Open registration or overly broad tokens | Protected registration, quotas, and rate limits |
| Spoofed app logo metadata | Trusting self-declared `client_name`/`logo_uri` | Publisher attestation and verified organization |
| Backend fetches internal URLs | Missing SSRF controls | Egress allowlist, DNS/IP validation, redirect restrictions |
| Client disabled but JWT still works | Resource Server verifies JWTs offline | Introspection, denylist, or appropriate token TTL |

## 21. Anti-patterns to Avoid

| Anti-pattern | Risk | Recommended Practice |
| --- | --- | --- |
| Enabling open DCR without rate limits | Spam and registry pollution | Protected registration or quotas |
| Issuing shared, non-expiring Initial Access Tokens | Compromising one token allows creating many clients | Short-lived tokens, tenant-scoped, single-use where appropriate |
| Trusting client-supplied redirect URIs | Authorization code theft | Exact validation and domain ownership |
| Allowing all grants/scopes | Clients gain privileges beyond their use case | Allowlists and least privilege |
| Using client secrets for public apps | Secret extracted from binary | Public client + PKCE |
| Treating `client_name`/`logo_uri` as identity proof | Phishing/brand impersonation | Publisher verification/software statement |
| Trusting `software_statement` just because the JWT decodes | Attackers forge fake attestations | Verify signature and trust chain |
| Storing raw Registration Access Tokens in logs | Hijacking registration read access | Secret handling and redaction |
| Constructing `registration_client_uri` from `client_id` | Wrong route or contract violation | Use the exact URI from the response |
| Customizing only the registration converter | Client Read loses metadata | Customize both directions (`RegisteredClient` → response) |
| Letting clients self-declare `tenant_id` for access | Cross-tenant privilege escalation | Resolve tenant from provisioning authority |
| Treating OIDC Client Read as full RFC 7592 | Calling unsupported PUT/DELETE | Verify endpoint implementation/version |
| Deleting client records while leaving token state uncontrolled | Old tokens may remain active | Coordinate deprovisioning with authorization/revocation |
| Treating successful registration as a trusted client | Client metadata is unattested | Approval, policy, and runtime authorization |

## 22. Production Acceptance Checklist

- [ ] Identified the DCR use case and the permitted scope of registrars.
- [ ] Distinguished RFC 7591, OIDC Registration 1.0, and RFC 7592.
- [ ] OIDC Client Registration Endpoint enabled only when needed.
- [ ] Discovery publishes the correct `registration_endpoint`.
- [ ] Registrar client exists with scoped `client.create` permission.
- [ ] Initial Access Token is protected, expires, and has quota/single-use policy.
- [ ] Per SAS guide, registration tokens contain only `client.create`.
- [ ] Appropriate `JwtDecoder` bean and JWK source are configured.
- [ ] `RegisteredClientRepository` uses shared persistence in production.
- [ ] Client IDs are unique and independent of display names/emails.
- [ ] Exact redirect URI validation; no arbitrary wildcards.
- [ ] Grant types, response types, scopes, and auth methods are allowlisted.
- [ ] Public/native clients use PKCE and do not receive unnecessary secrets.
- [ ] JWKS/sector URIs are validated for HTTPS, schema, and SSRF policy.
- [ ] Software statements have signature/issuer/audience/expiry verified if used.
- [ ] Registration responses have appropriate cache control and secrets are never logged.
- [ ] Registration Access Tokens are stored as bearer secrets.
- [ ] Clients use the exact returned `registration_client_uri`.
- [ ] Tested Client Read and SAS version limitations.
- [ ] Custom metadata uses bidirectional converters and allowlists.
- [ ] Disable/delete/rotation procedures and related token revocation are in place.
- [ ] Tenant isolation, auditing, rate limiting, monitoring, and cleanup are in place.
- [ ] Integration tests cover tokens, redirects, scopes, metadata, persistence, and multi-instance setups.
- [ ] Runbook exists for compromised registrar tokens or client credentials.

## 23. Memory Map

```mermaid
flowchart TD
    DISC["OIDC Discovery"] --> ENDPOINT["registration_endpoint"]
    OWNER["Approved developer / provisioning"] --> REGISTRAR["Registrar Client"]
    REGISTRAR --> TOKEN["Initial Access Token<br/>scope client.create"]
    TOKEN --> POST["POST Client Registration + JSON metadata"]
    POST --> VALIDATE["Validate bearer token + client metadata"]
    VALIDATE --> STORE["RegisteredClientRepository"]
    STORE --> RESPONSE["201 Created<br/>client_id + client credentials"]
    RESPONSE --> ACCESS["registration_access_token"]
    RESPONSE --> URI["registration_client_uri"]
    ACCESS --> READ["GET Client Read"]
    URI --> READ
    READ --> META["Current registration metadata"]
    STORE --> AUTH["Normal OAuth/OIDC client flows"]
```

**Dynamic Client Registration is a controlled client creation workflow using metadata and standard protocols.** RFC 7591 defines OAuth2 registration; OIDC Registration 1.0 adds a contract for relying parties and the Client Read operation; RFC 7592 extends registration management operations. In Spring Authorization Server, the OIDC Client Registration Endpoint is built-in but disabled by default, requires a Bearer access token with the appropriate scope, and needs a `JwtDecoder`. Registrars, Initial Access Tokens, Registration Access Tokens, metadata validation, and persistence must be designed as a single security lifecycle. By keeping redirect URIs exact, applying least privilege, verifying metadata, and governing deprovisioning, DCR can automate onboarding while maintaining OAuth 2.0/OpenID Connect trust boundaries.

## 24. References

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592)
- [OpenID Connect Dynamic Client Registration 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-registration-1_0.html)
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
