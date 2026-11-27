# Registration Access Token and OIDC Client Configuration Endpoint

## 1. Context: Managing a Registration After Creating a Client

In an OAuth 2.0/OpenID Connect (OIDC) system using **Spring Security**, **Spring Authorization Server**, and Spring Boot, an application can register with an OpenID Provider (OP) via Dynamic Client Registration instead of having an administrator create it manually in advance.

After successful registration, the OP issues `client_id`, may issue `client_secret`, and may return two additional important values:

- **`registration_access_token`**: Bearer token used to access the configuration of an already-registered client.
- **`registration_client_uri`**: URL of the Client Configuration Endpoint dedicated to that registration.

These two values let the client read back the configuration stored by the OP. In OIDC Dynamic Client Registration 1.0, the operation defined for the Client Configuration Endpoint is **HTTP GET**. Extended update/delete operations are described separately in RFC 7592 (Experimental) and should not be assumed to be supported by every OP.

This lesson belongs to the **Dynamic Client Registration** chapter and focuses on the Registration Access Token and Client Configuration Endpoint, covering the OIDC protocol, secure usage, and corresponding configuration in Spring Authorization Server.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish an Initial Access Token from a Registration Access Token.
2. Explain the relationship between `registration_access_token`, `registration_client_uri`, and `client_id`.
3. Read back client configuration via the Client Configuration Endpoint.
4. Understand the fields in the Registration Response and Read Response.
5. Protect the Registration Access Token as a credential with client management privileges.
6. Handle token rotation, secret rotation, and registration state.
7. Enable Dynamic Client Registration in Spring Authorization Server.
8. Grant `client.create` and `client.read` permissions to a registrar client.
9. Call `/connect/register` and read the `registration_client_uri` URL using Spring `WebClient`.
10. Extend client metadata with appropriate converters.
11. Distinguish OIDC Registration 1.0 from the RFC 7592 Management Protocol.
12. Design testing, monitoring, and registration revocation workflows.

## 2. What Is a Registration Access Token?

A Registration Access Token (RAT) is an OAuth 2.0 Bearer Token issued by the Authorization Server for **one specific client registration**. This token authenticates the caller when accessing the Client Configuration Endpoint to read registration information.

For example, after the OP registers `inventory-web`, it may return:

~~~json
{
  "client_id": "inventory-web-7f21",
  "registration_access_token": "RAT_VALUE_FROM_AUTHORIZATION_SERVER",
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=inventory-web-7f21"
}
~~~

This is an illustrative example. The real URL must be taken verbatim from the response; never assemble it from `client_id` or guess the path.

### 2.1. A RAT Is Bound to One Registration

A Registration Access Token:

- Is issued by the OP and bound to one client registration.
- Is sent in the `Authorization: Bearer ...` header to the Client Configuration Endpoint.
- Allows reading client information per OP-granted permissions.
- May allow additional management operations if the OP implements the corresponding extension.
- Must be protected as a high-value credential.

A RAT is not `client_secret`, is not an access token for calling business APIs, and is not the Initial Access Token used to create the registration.

### 2.2. A RAT Can Be Highly Sensitive

A client secret typically authenticates the client at the Token Endpoint. A RAT authenticates access to the registration record; this record may contain the client secret, redirect URIs, grant types, JWK metadata, and other security configurations.

If an attacker obtains a RAT, they can read sensitive client metadata. If the OP supports RFC 7592 update/delete, the token could also allow modifying or deleting the registration. Therefore, a RAT must be protected at least on par with long-lived credentials.

## 3. Distinguishing Three Types of Credentials in Dynamic Client Registration

Three values are frequently confused:

| Credential | Issued To | Used Where? | Purpose |
|---|---|---|---|
| Initial Access Token | Registrar/developer or onboarding system | Client Registration Endpoint | Authorizes creating a new registration |
| Registration Access Token | A newly created client registration | Client Configuration Endpoint | Reads/manages that registration |
| Client Secret | Confidential client | Token Endpoint | Authenticates the client when requesting tokens |

### 3.1. Initial Access Token

An Initial Access Token (IAT) is a token issued by the OP under its own policy to protect the Client Registration Endpoint. RFC 7591 allows an open registration endpoint or requiring an IAT; how IATs are issued is outside the RFC's scope.

In the Spring Authorization Server 1.5.8 example, the registrar client uses Client Credentials to request an access token with only the `client.create` scope. This token is used for the registration POST request and is invalidated after registration succeeds.

### 3.2. Registration Access Token

A RAT is returned in the Registration Response if the OP supports a Client Configuration Endpoint. The client uses the RAT to call the URL in `registration_client_uri`.

A RAT has a lifecycle tied to the registration and may be a long-lived credential. Never use an IAT to call the Client Configuration Endpoint, and never use a RAT to request business access tokens.

### 3.3. Client Secret

Client Secret authenticates a confidential client at the Token Endpoint per `token_endpoint_auth_method`, such as `client_secret_basic`. It does not substitute for a RAT.

A single response may return both `client_secret` and `registration_access_token`; store them securely, keep their purposes separate, and restrict access permissions.

## 4. What Does the Client Configuration Endpoint Do?

The Client Configuration Endpoint is an OP protected resource providing stored registration details. The OP returns the endpoint URL in `registration_client_uri`.

In OIDC Dynamic Client Registration 1.0, the endpoint:

- Is optionally provisioned.
- Operates only when the registration response returns both `registration_client_uri` and `registration_access_token`.
- Requires the client to send the RAT as a Bearer Token in every request.
- Defines HTTP GET for reading configuration.
- Does not require the client to construct the endpoint URL from `client_id`.

Example request:

~~~http
GET /connect/register?client_id=inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Accept: application/json
Authorization: Bearer RAT_VALUE_FROM_AUTHORIZATION_SERVER
~~~

The path above is illustrative. The client must use the exact URI returned by the OP.

### 4.1. The Client Configuration Endpoint Is a Protected Resource

The RAT is sent as an OAuth Bearer Token. The OP validates the token, identifies the registration bound to that token, and returns only that registration's information.

Never accept `client_id` from the query string and return configuration based solely on that value. The server must verify that the specified client matches the client to which the RAT was issued.

### 4.2. Read Operations Should Be Idempotent

OIDC Registration 1.0 recommends that GET reads do not mutate registration configuration. Clients can read it back to synchronize metadata after onboarding or check configuration status.

If the OP has a credential rotation mechanism, the response may reflect updated values. The client must update its secret/token per OP rules and stop using old credentials if the response provides new ones.

## 5. Lifecycle: From Registration to Reading Configuration

A typical workflow:

~~~mermaid
sequenceDiagram
    participant R as Registrar / Onboarding Service
    participant OP as OpenID Provider
    participant DB as RegisteredClient Store
    participant C as Newly Registered Client

    R->>OP: POST /connect/register + Initial Access Token
    OP->>OP: Validate registrar, scope and client metadata
    OP->>DB: Persist RegisteredClient
    DB-->>OP: Registration created
    OP-->>R: 201 Created + client_id + RAT + registration_client_uri
    R->>C: Deliver client credentials and registration data securely
    C->>OP: GET registration_client_uri + RAT
    OP->>OP: Validate RAT and registration binding
    OP->>DB: Read registered client metadata
    DB-->>OP: Current client configuration
    OP-->>C: 200 OK + client metadata
~~~

Steps:

1. The registrar requests an Initial Access Token.
2. The registrar sends client metadata to the Client Registration Endpoint.
3. The OP validates and creates the registration.
4. The OP returns `client_id`, optionally `client_secret`, and optionally the RAT/management URI.
5. The client securely stores the credentials and management URL.
6. When synchronization is needed, the client sends GET to that URL with the RAT.
7. The OP verifies permissions and returns the current configuration.

### 5.1. Two Distinct Authentication Stages

- The Registration Endpoint checks the Initial Access Token or open registration policy.
- The Configuration Endpoint checks the Registration Access Token belonging to that exact client.

Never reuse one token for both stages just because both use the Bearer scheme.

## 6. Discovery and Registration URLs

OIDC Provider Configuration may publish `registration_endpoint`, indicating where RPs send registration requests. The Client Configuration Endpoint is a per-registration URL returned in `registration_client_uri`.

Condensed metadata example:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "registration_endpoint": "https://auth.example.com/connect/register"
}
~~~

This is illustrative metadata. An OP may use different URIs; clients should retrieve `registration_endpoint` from Discovery metadata of a trusted issuer.

### 6.1. Do Not Construct registration_client_uri Manually

After registration, the OP returns `registration_client_uri`. The client must use that exact URL. The URL may embed the client ID in the path or query string, or use a deployment-specific structure.

Do not concatenate `registration_endpoint + "?client_id=" + client_id`. Doing so can form the wrong URL or send the RAT to the wrong endpoint.

### 6.2. Trust the Issuer Before Calling the URL

The client must verify that Discovery metadata belongs to the expected OP and uses TLS. Never accept a `registration_client_uri` supplied by a user or untrusted client and send a RAT to it.

If the application supports multiple issuers, store the mapping between registration, issuer, and endpoint URLs to avoid mixing up credentials across OPs.

## 7. Registration Response and Key Fields

A successful response typically uses HTTP `201 Created` and JSON:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "client_id": "inventory-web-7f21",
  "client_secret": "CLIENT_SECRET_VALUE",
  "client_secret_expires_at": 0,
  "registration_access_token": "RAT_VALUE",
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=inventory-web-7f21",
  "token_endpoint_auth_method": "client_secret_basic",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile inventory.read"
}
~~~

### 7.1. Identifier and Credential Fields

| Field | Meaning |
|---|---|
| `client_id` | Unique client identifier issued by the OP |
| `client_secret` | Confidential client secret if issued by the OP |
| `client_secret_expires_at` | Secret expiration time as NumericDate; `0` indicates non-expiring |
| `client_id_issued_at` | Client ID issuance time if returned |
| `registration_access_token` | RAT for calling the Client Configuration Endpoint |
| `registration_client_uri` | Client-specific configuration URL |

If the OP returns `registration_access_token`, it must also return `registration_client_uri`; if it does not provision a Client Configuration Endpoint, both may be omitted.

### 7.2. Client Metadata

The response also contains the metadata accepted by the OP, which may include:

- `redirect_uris`
- `grant_types`
- `response_types`
- `token_endpoint_auth_method`
- `client_name`
- `logo_uri`
- `client_uri`
- `policy_uri`
- `tos_uri`
- `jwks_uri` or `jwks`
- `scope`
- OIDC metadata such as signing/encryption algorithms

The OP may reject or substitute certain requested values, so the client must store the **actual values in the response**, never assuming all request metadata was accepted verbatim.

### 7.3. Cache-Control

Because registration responses contain credentials, the OP should return `Cache-Control: no-store`. Clients should also keep the response out of HTTP caches, logs, tracing spans, or analytics payloads.

## 8. Client Read Request

Once `registration_client_uri` and the RAT are obtained, the client sends HTTP GET:

~~~http
GET /connect/register?client_id=inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Accept: application/json
Authorization: Bearer RAT_VALUE
~~~

The client must:

1. Use HTTPS and verify the OP's certificate.
2. Send the RAT in the Authorization header.
3. Never place the RAT in URL query strings.
4. Call the exact `registration_client_uri` received.
5. Handle Bearer token errors per RFC 6750.
6. Parse JSON and validate metadata before updating local configuration.

### 8.1. Read Response

A successful response typically uses HTTP 200:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "client_id": "inventory-web-7f21",
  "client_secret": "CURRENT_CLIENT_SECRET",
  "client_secret_expires_at": 0,
  "registration_client_uri": "https://auth.example.com/connect/register?client_id=inventory-web-7f21",
  "token_endpoint_auth_method": "client_secret_basic",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile inventory.read"
}
~~~

The Read Response does not necessarily re-return `registration_access_token` or `registration_client_uri`, unless those values are updated per OP semantics.

### 8.2. Do Not Mutate Runtime Configuration Without Verification

The client should validate the response before updating local configuration. For example, if `redirect_uris` changed outside an expected change request, detect the drift and require an appropriate approval workflow.

Do not blindly trust returned metadata if it will be used to construct redirects, call endpoints, or fetch keys.

## 9. HTTP Rules and Errors

| Scenario | Typical Status | Meaning |
|---|---:|---|
| Registration read succeeds | 200 | Returns client metadata |
| RAT missing/invalid/expired | 401 | Bearer authentication failed |
| Client lacks read permission | 403 | Authenticated but unauthorized |
| Client does not exist or token no longer valid | 401 per OIDC Registration error rules | Avoids revealing whether a registration exists |
| Invalid registration request metadata | 400 | `invalid_client_metadata` or appropriate error |
| Invalid Redirect URI | 400 | `invalid_redirect_uri` |
| Registrar lacks permission | 401/403 depending on auth mechanism and policy | Not authorized to create clients |

OIDC Registration 1.0 specifies that the Client Configuration Endpoint should not return HTTP 404 on read errors; returning 401 helps prevent probing for existing registrations.

### 9.1. 401 and 403 Are Not the Same

- `401 Unauthorized`: RAT is invalid, missing, or the client/registration no longer exists per protocol semantics.
- `403 Forbidden`: RAT is valid, but the caller lacks permission for the requested operation.

Clients should not retry endlessly with a rejected token. Inspect token storage, rotation state, and registration status.

## 10. Registration Access Token and Token Rotation

A RAT is a Bearer Token, so possession confers access to endpoint operations permitted by the OP. OIDC Registration 1.0 allows the OP to return a RAT in the registration response; if the OP does not support registration management, it may omit the RAT and configuration URL.

RFC 7592 adds the ability to rotate the Registration Access Token when a client reads or updates its registration. If a response returns a new token, the client must immediately discard the old token and persist the new one before the next call.

### 10.1. Handling Rotation Safely

A client managing a registration should:

1. Read the current RAT from the secret store.
2. Call the configuration endpoint over TLS.
3. Check whether the response contains a new `registration_access_token`.
4. If present, write the new token securely and confirm persistence succeeded.
5. Only then mark the old token as retired.
6. If the response contains no new token, keep using the current token per the OP's contract.

Never log the new token for debugging. Never resend the old token after the server has signaled rotation.

### 10.2. RATs Can Be Long-Lived

RFC 7592 recommends that a RAT not expire while the client remains active so management capability is not lost. However, an OP may rotate tokens or apply other policies to limit risk.

This is why RATs require secret storage, least-privilege access, auditing, and explicit revocation procedures.

## 11. A Registration Access Token Is Not client_secret

| Attribute | Registration Access Token | Client Secret |
|---|---|---|
| Purpose | Read/manage registration | Authenticate client at Token Endpoint |
| Endpoint | `registration_client_uri` | Token Endpoint |
| How sent | Bearer Token | Per `token_endpoint_auth_method` |
| Scope | One registration | One OAuth client |
| Can read client metadata? | Yes, per OP-granted permission | Does not inherently grant config read access |
| Can request API tokens? | No per RAT semantics | Used for client authentication in allowed grants |
| On leak | Exposes configuration; may allow update/delete if extensions enabled | Attacker can impersonate the client at the Token Endpoint |

Never use a client secret in place of a RAT to call the Client Configuration Endpoint. Never use a RAT in place of a client secret to call the Token Endpoint.

## 12. How Do OIDC Registration 1.0 and RFC 7592 Differ?

This is an important protocol boundary:

| Capability | OIDC Dynamic Client Registration 1.0 | RFC 7592 |
|---|---|---|
| Client registration | Yes, via POST Registration Endpoint | Extends RFC 7591 |
| Returns `registration_access_token` and `registration_client_uri` | Optional per response | Present in management responses |
| Read configuration | GET | GET |
| Update configuration | Not defined in OIDC Registration 1.0 | PUT |
| Delete registration | Not defined in OIDC Registration 1.0 | DELETE |
| Spec status | OpenID Foundation Final Specification | Experimental RFC |

OIDC Registration 1.0 defines GET as the sole HTTP method for the Client Configuration Endpoint. Update/delete capabilities were added by **OAuth 2.0 Dynamic Client Registration Management Protocol — RFC 7592**, which is an Experimental RFC.

### 12.1. PUT in RFC 7592

If the OP implements RFC 7592, the client can send PUT to the Client Configuration Endpoint with all registered metadata. This is a full representation update; omitted metadata may be interpreted as null/empty per the RFC.

The client must preserve its existing `client_id` and must not supply its own new client secret. The server may issue a new secret or RAT in the response.

### 12.2. DELETE in RFC 7592

If the OP implements RFC 7592, DELETE can deprovision a client registration. After deletion, the registration's `client_id`, `client_secret`, and RAT are invalidated. The server SHOULD revoke associated authorization grants and tokens if possible.

Never call PUT or DELETE simply because the OP returns `registration_client_uri`. Confirm that the OP supports RFC 7592 and the specific methods.

## 13. What Does Spring Authorization Server Support?

According to the Spring Authorization Server 1.5.8 documentation:

- Dynamic Client Registration is disabled by default.
- The OIDC Client Registration Endpoint can be enabled with `clientRegistrationEndpoint(...)`.
- The registrar client uses the `client.create` scope to register.
- The `client.read` scope can be configured to read client registrations.
- The Registration Response returns `registration_access_token` and `registration_client_uri`.
- The guide demonstrates using the RAT to GET back client configuration.

The official guide illustrates **registration and reading configuration**. Do not assume Spring Authorization Server 1.5.8 implements full RFC 7592 PUT/DELETE by default. If update/delete is required, verify your API/version or build a compatible extension and test it thoroughly.

## 14. Enabling the Client Registration Endpoint in Spring Authorization Server

In Spring Authorization Server 1.x, enable the endpoint in the Authorization Server `SecurityFilterChain`:

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(oidc ->
                    oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                )
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            );

        return http.build();
    }
}
~~~

Key points:

- `getEndpointsMatcher()` scopes the chain to Authorization Server protocol endpoints.
- `oidc(...)` enables the OIDC configurer.
- `clientRegistrationEndpoint(...)` enables the Dynamic Client Registration endpoint.
- This configuration does not automatically let anyone register; the endpoint still checks Initial Access Tokens and registrar policies.

A complete configuration also needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, signing key/JWK source, issuer, and a user authentication chain depending on the application.

## 15. Configuring the Registrar Client

A registrar is a client authorized to create other clients. Example:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder) {

    RegisteredClient registrar = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("client-registrar")
        .clientSecret(passwordEncoder.encode("SECRET_FROM_SECRET_MANAGER"))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();

    return new InMemoryRegisteredClientRepository(registrar);
}
~~~

This is an educational example. Production should use a secret manager, an appropriate encoder, and a persistent `RegisteredClientRepository` such as a JDBC repository.

### 15.1. The Two Scopes Have Different Meanings

- `client.create`: allows the registrar to request an Initial Access Token to create a registration.
- `client.read`: allows the registrar to read a registration per Spring Authorization Server guide policy.

The registrar should not hold extra API scopes or unrelated admin permissions. Scopes must be granted precisely in the access token.

### 15.2. In-Memory Repository Is Suitable for Demos Only

`InMemoryRegisteredClientRepository` loses data on process restart and is unsuitable for multi-node deployments needing durable registrations. Production needs to persist registrations and authorization state in a data store with backups, transactions, and access controls.

## 16. Requesting an Initial Access Token in Spring Authorization Server

Per the Spring Authorization Server guide, the registrar uses Client Credentials to request a token with the exact `client.create` scope:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

Illustrative response:

~~~json
{
  "access_token": "INITIAL_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "client.create"
}
~~~

In the SAS 1.5.8 guide, the Initial Access Token request must have only the `client.create` scope; if the access token contains extra scopes, the registration request is rejected. The initial token is single-use and invalidated after the client is successfully registered.

### 16.1. Do Not Include client.read in the Initial Access Token

The registrar may be configured with `client.read` to obtain tokens for read operations per the guide, yet the Initial Access Token used to create a client must contain only `client.create`.

Distinguish the scopes a registrar is allowed to request from the actual scopes included in the current token.

## 17. Sending a Registration Request and Receiving the RAT

The default Client Registration Endpoint in Spring Authorization Server examples is `/connect/register`. Ideally, retrieve `registration_endpoint` from discovery metadata.

Sample request:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "Inventory Web",
  "application_type": "web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile inventory.read",
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

After validation, the OP returns the registration response. The client must store:

- `client_id`
- `client_secret` if issued
- `registration_access_token`
- `registration_client_uri`
- Actual metadata accepted by the OP

Never write this response to application logs. Deliver credentials to a secret store over a protected channel.

## 18. Reading a Registration with WebClient

The Spring Authorization Server guide uses `WebClient` to POST registration and GET configuration. Condensed DTO example:

~~~java
public record ClientRegistrationResponse(
    @JsonProperty("client_id") String clientId,
    @JsonProperty("client_secret") String clientSecret,
    @JsonProperty("registration_access_token") String registrationAccessToken,
    @JsonProperty("registration_client_uri") String registrationClientUri,
    @JsonProperty("client_name") String clientName,
    @JsonProperty("redirect_uris") List<String> redirectUris,
    @JsonProperty("grant_types") List<String> grantTypes,
    String scope) {
}
~~~

Calling the endpoint returned by the OP:

~~~java
public ClientRegistrationResponse readRegistration(
        WebClient webClient,
        String registrationClientUri,
        String registrationAccessToken) {

    return webClient
        .get()
        .uri(registrationClientUri)
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers ->
            headers.setBearerAuth(registrationAccessToken))
        .retrieve()
        .bodyToMono(ClientRegistrationResponse.class)
        .block();
}
~~~

This snippet illustrates a servlet/blocking caller. Reactive applications should keep a reactive pipeline and avoid calling `block()` on event-loop threads.

### 18.1. Protecting URI and Token Before Calling

Before calling, the application should confirm:

- `registrationClientUri` came from a trusted OP's response.
- The scheme is HTTPS.
- The host/issuer matches the saved registration.
- The RAT is retrieved from secret storage corresponding to the registration.
- The HTTP client verifies TLS certificates.
- Automatic redirects do not leak the Authorization header to another origin.

Never let callers pass an arbitrary `registrationClientUri`.

## 19. Customizing Client Metadata in Spring Authorization Server

Spring Authorization Server converts OIDC client registration metadata to `RegisteredClient` via converters. For standard metadata, default converters handle the fields supported by the framework.

If custom metadata such as `logo_uri`, `contacts`, or organization-specific fields is needed, extend converters in both directions:

1. Registration Request → `RegisteredClient`.
2. `RegisteredClient` → Client Configuration Response.

In Spring Authorization Server 1.5.8, providers can be customized via:

- `OidcClientRegistrationAuthenticationProvider`
- `OidcClientConfigurationAuthenticationProvider`
- `OidcClientRegistrationRegisteredClientConverter`
- `RegisteredClientOidcClientRegistrationConverter`

### 19.1. Storing Metadata in ClientSettings

Example approach:

~~~java
ClientSettings.Builder settings =
    ClientSettings.withSettings(registeredClient.getClientSettings().getSettings());

settings.setting("logo_uri", clientRegistration.getClaim("logo_uri"));
settings.setting("contacts", clientRegistration.getClaim("contacts"));

RegisteredClient updated = RegisteredClient.from(registeredClient)
    .clientSettings(settings.build())
    .build();
~~~

This snippet illustrates storing custom metadata; in a real converter, allowlist fields, validate data types, limit sizes, and keep the default converter for standard fields.

### 19.2. Configuring Provider Converters

When customizing, update converters on both the provider handling registration and the provider handling configuration responses. If you only persist custom metadata on POST without converting it back on GET, clients will not see those registered fields.

Never accept arbitrary custom claims and write them straight into `ClientSettings`. Allow only well-defined, validated, meaningful metadata.

## 20. Securing Metadata and Preventing SSRF

Dynamic Client Registration accepts metadata sent by clients. Some metadata contains URLs that the OP may fetch or display, such as:

- `jwks_uri`
- `sector_identifier_uri`
- `logo_uri`
- `client_uri`
- `policy_uri`
- `tos_uri`

If the OP fetches URLs itself, malicious metadata can cause SSRF, internal network access, or unwanted content downloads.

### 20.1. URL Validation

The OP should enforce:

- HTTPS only for endpoint/key URLs per metadata requirements.
- Blocking loopback, link-local, private IPs, and cloud metadata addresses when disallowed.
- DNS rebinding controls and checks on redirects to untrusted hosts.
- Timeouts, response size caps, and content type checks.
- Egress network restrictions on the Authorization Server process.
- Never rendering raw HTML/scripts from client metadata.

### 20.2. Redirect URI Is High-Security Metadata

`redirect_uris` must be strictly validated and matched per OIDC/OAuth rules. Reject broad wildcards or browser-supplied URIs in authorization requests that are absent from the registration.

Clients may request metadata, yet the OP decides what values are persisted.

### 20.3. Logos and Display Information

A malicious client could mimic a legitimate app's name/logo for phishing. The OP should verify logo sources, correlate logo hosts with redirect URIs, and display trust/approval status for newly registered clients.

## 21. Protecting the Registration Access Token

Because a RAT is a Bearer Token, possession grants endpoint access per policy. Safeguards:

- Generate high-entropy, unpredictable tokens.
- Transmit only over TLS with server certificate verification.
- Store in a secret manager or vault, encrypted at rest.
- Never log Authorization headers, token responses, or RATs.
- Restrict which service accounts can read the RAT.
- Isolate RATs per client registration.
- Audit every registration read.
- Revoke the RAT when the client is deprovisioned.
- Consider rotation based on OP capabilities.
- Never store RATs in browser local storage if they can reside in a backend.

### 21.1. A RAT Is Not Public Metadata

`client_id` can appear in logs and protocol messages; a RAT must not. `registration_client_uri` is not an independent authentication secret either, yet combined with a RAT it leads to sensitive configuration access.

Never treat the management URL as a security mechanism; authorization comes from the RAT.

## 22. Stateless Registration and Cases Without a RAT

OIDC Registration 1.0 permits an OP to perform stateless dynamic registration. When not storing registration state on the server, the OP may have no basis to issue a RAT bound to a registration.

In that case, the OP may return only the information needed for the client to operate and omit both:

- `registration_access_token`
- `registration_client_uri`

Clients must handle this possibility. Do not treat a response lacking a RAT as an error if the OP does not provision a Client Configuration Endpoint.

If an application strictly requires reading back or managing metadata post-registration, choose an OP with stateful registration or design a separate protected provisioning API.

## 23. Update/Delete under RFC 7592: Optional Extensions

RFC 7592 adds registration management operations beyond OIDC Registration 1.0.

### 23.1. PUT — Updating Metadata

If the OP implements RFC 7592, the client can send PUT to the Client Configuration Endpoint with all registered metadata. This is a full representation update; omitted metadata may be treated as null/empty per the RFC.

The client must retain its current `client_id` and must not self-assign a new client secret. The server may issue a new secret or RAT in the response.

Illustrative example when the OP declares RFC 7592 support:

~~~http
PUT /register/inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Authorization: Bearer RAT_VALUE
Content-Type: application/json

{
  "client_id": "inventory-web-7f21",
  "client_name": "Inventory Web Production",
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "scope": "openid profile inventory.read"
}
~~~

### 23.2. DELETE — Deprovisioning a Registration

If the OP implements RFC 7592, DELETE can deprovision a client registration. After deletion, the registration's `client_id`, `client_secret`, and RAT are invalidated. The server SHOULD revoke related authorization grants and tokens if possible.

Example:

~~~http
DELETE /register/inventory-web-7f21 HTTP/1.1
Host: auth.example.com
Authorization: Bearer RAT_VALUE
~~~

A successful response under RFC 7592 is `204 No Content`.

### 23.3. Boundaries with Spring Authorization Server

OIDC Registration 1.0 defines only GET on the Client Configuration Endpoint. RFC 7592 PUT/DELETE are Experimental extensions. The Spring Authorization Server 1.5.8 guide demonstrates registration and retrieval; do not assume PUT/DELETE are implemented out of the box by the framework.

If update/delete is required, verify your exact version and endpoint implementation, or build a custom extension with appropriate authorization, validation, transactions, auditing, and tests.

## 24. Testing Registration Access Tokens and the Configuration Endpoint

### 24.1. Registrar and Registration Matrix

| Test case | Expected Result |
|---|---|
| Registrar has `client.create` | Requests Initial Access Token successfully |
| Token has extra unpermitted scopes | Registration rejected per policy |
| Missing Initial Access Token when required by OP | 401 |
| Valid redirect URI metadata | Registration created |
| Invalid Redirect URI | 400 `invalid_redirect_uri` or matching error |
| Inconsistent grant/response type | Registration rejected |
| Registration succeeds | Returns `client_id` and OP-accepted metadata |
| OP provisions management endpoint | Returns both RAT and `registration_client_uri` |
| Stateless OP | May omit both management fields |

### 24.2. Client Configuration Endpoint Matrix

| Test case | Expected Result |
|---|---|
| GET with valid RAT | 200 and client metadata |
| GET missing RAT | 401 |
| GET with wrong/expired RAT | 401 |
| RAT belonging to another registration | Cannot read target registration |
| Client already deprovisioned | 401 per protocol semantics |
| Valid token lacking read permission | 403 |
| Repeated read requests | Do not mutate registration |
| Response includes new secret | Safely update secret |
| Response includes new RAT | Save new token and discard old token |
| Response has no new RAT | Continue using current token |

### 24.3. Security Testing

- RAT does not appear in access logs or tracing.
- Never send RAT to a cross-origin host.
- Metadata URLs cannot reach private/internal addresses outside allowlists.
- Registration rejects dangerous wildcard redirect URIs.
- A client cannot read another registration by changing `client_id`.
- Deprovisioning invalidates the old RAT.
- Token rotation prevents clients from continuing to use old tokens.
- Multi-node cluster reads consistent registration state.
- Custom metadata is persisted strictly per allowlist.
- JSON responses are not cached.

## 25. Operations and Observability

### 25.1. Metrics

Track:

- Registration requests per registrar client.
- Registration successes/failures and metadata errors.
- Initial Access Token issuance/consumption.
- Client Configuration GET requests.
- RAT authentication failures and 403 authorization failures.
- Ratio of registrations with vs. without RATs.
- Credential rotations and secret expirations.
- Active vs. deprovisioned client registrations.
- `RegisteredClientRepository` and authorization store errors.
- Time from deprovisioning until related tokens/grants are invalidated.

Never put RATs, client secrets, or raw tokens in metric labels.

### 25.2. Audit Events

Appropriate events:

~~~text
DYNAMIC_CLIENT_REGISTRATION_REQUESTED
DYNAMIC_CLIENT_REGISTRATION_CREATED
DYNAMIC_CLIENT_REGISTRATION_REJECTED
CLIENT_CONFIGURATION_READ
REGISTRATION_ACCESS_TOKEN_ROTATED
CLIENT_SECRET_ROTATED
DYNAMIC_CLIENT_REGISTRATION_DEPROVISIONED
CLIENT_METADATA_VALIDATION_FAILED
~~~

Audit records should include registrar/client ID, issuer, correlation ID, outcome, changed metadata field names, and timestamp. Never log secret/token values or full metadata containing PII.

### 25.3. Runbook When a Client Cannot Read Its Configuration

1. Check whether the OP returned both `registration_access_token` and `registration_client_uri`.
2. Verify the URL came from the original response and was not manually constructed.
3. Check issuer/host/TLS certificate.
4. Check whether the RAT belongs to the right registration.
5. Check whether the token rotated while the app is still using the old value.
6. Check whether the client registration still exists.
7. Check registrar/management policies and scopes.
8. Check `RegisteredClientRepository` and the authorization store.
9. Inspect 401/403 response statuses and `WWW-Authenticate`.
10. Check cluster consistency and audit events.

Never resolve errors by disabling RAT checks or making client configuration GET public.

## 26. Production Checklist

- [ ] Dynamic Client Registration is intentionally enabled.
- [ ] Registrar has a dedicated `client.create` scope and least-privilege permissions.
- [ ] Initial Access Token is separate from Registration Access Token.
- [ ] Initial Access Token carries only the scopes required by registrar policy.
- [ ] Registration Response is stored securely.
- [ ] `registration_access_token` and `registration_client_uri` are handled as a pair.
- [ ] Client uses the exact `registration_client_uri` returned by the OP.
- [ ] RAT is transmitted only over HTTPS in the Authorization header.
- [ ] RAT is stored in a secret manager/vault, never logged.
- [ ] Client verifies issuer and origin before sending the RAT.
- [ ] Client handles RAT/secret rotation if responses return new values.
- [ ] Client tolerates stateless registration without RAT/URI.
- [ ] OIDC Client Configuration Endpoint GET is tested.
- [ ] Redirect URI, grant, scope, JWK, and endpoint metadata are validated.
- [ ] Custom metadata is allowlisted and converted bidirectionally.
- [ ] `RegisteredClientRepository` and authorization state have durable persistence.
- [ ] Do not assume OIDC Registration 1.0 defines PUT/DELETE.
- [ ] RFC 7592 is implemented only when the OP explicitly supports the extension.
- [ ] Deprovisioning invalidates the RAT and handles related tokens/grants per policy.
- [ ] Auditing, metrics, redaction, and runbooks are in place.

### Core Knowledge

**Registration Access Token** is a Bearer credential bound to a single client registration. It is used at the **Client Configuration Endpoint** via the `registration_client_uri` URL returned by the OP. The client must use the URL verbatim and send the RAT in the Authorization header over TLS.

In OIDC Dynamic Client Registration 1.0, the Client Configuration Endpoint defines GET to read metadata. The **Initial Access Token** protects registration creation; the **Registration Access Token** reads/manages a registration after creation; **`client_secret`** authenticates a confidential client at the Token Endpoint. These three credentials have distinct purposes and scopes.

Spring Authorization Server 1.5.8 enables turning on the Client Registration Endpoint, granting registrars `client.create`/`client.read` scopes, creating registrations, and reading back configuration with a RAT. Update/Delete belong to Experimental RFC 7592 and must be verified or implemented separately. RATs must be protected like high-privilege secrets with proper rotation, revocation, auditing, and testing.

## References

- [OpenID Connect Dynamic Client Registration 1.0 — Client Configuration Endpoint](https://openid.net/specs/openid-connect-registration-1_0.html#ClientConfigurationEndpoint)
- [OpenID Connect Dynamic Client Registration 1.0 — Client Registration Response](https://openid.net/specs/openid-connect-registration-1_0.html#ClientRegistrationResponse)
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol (Experimental)](https://www.rfc-editor.org/rfc/rfc7592)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — OidcClientConfigurationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientConfigurationAuthenticationProvider.html)
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html)
