# Managing the Lifecycle of Dynamically Registered Clients and Protecting Registration Secrets

## 1. Why Does Dynamic Client Registration Need Lifecycle Management?

**Dynamic Client Registration (DCR)** allows an OAuth 2.0 Client or developer to send metadata to an Authorization Server (AS) to create a client registration without an administrator manually entering every field. The AS issues a `client_id`, optionally issues a `client_secret`, and stores configurations such as redirect URIs, grant types, scopes, token endpoint authentication method, and public key locations.

Creating a registration is only the first step. A client may change redirect URIs, update names/metadata, rotate secrets, suffer credential exposure, transfer ownership, become inactive, or require revocation. Without a clear lifecycle, stale registrations linger indefinitely, secrets go unrotated, old permissions remain active, and operators do not know who manages the client.

This lesson belongs to the **Dynamic Client Registration** chapter of the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module. The goal is to design how to manage dynamically registered clients and protect related credentials in Spring Boot, Spring Security, and Spring Authorization Server (SAS) applications.

After this lesson, you should be able to:
1. Distinguish client registrations, client credentials, Initial Access Tokens, and Registration Access Tokens.
2. Understand the create, read, update, rotate, suspend, revoke, and deprovision lifecycle.
3. Apply RFC 7591 and RFC 7592 within their exact scopes.
4. Protect `client_secret` and `registration_access_token` from issuance to revocation.
5. Enable and customize the OIDC Client Registration Endpoint in SAS.
6. Recognize what SAS 1.5.8 supports by default versus what must be extended yourself.
7. Design zero-downtime secret rotation, incident response, and lifecycle testing.

## 2. Identifiers and Credentials to Distinguish

| Value | Issued By | Used Where? | Permissions / Nature |
| --- | --- | --- | --- |
| `client_id` | AS | Authorization Endpoint, Token Endpoint, and related APIs | Identifies the client; typically a public value |
| `client_secret` | AS, if the client is confidential | Client Authentication at the Token Endpoint | Authenticates the client; not a registration management key |
| **Initial Access Token (IAT)** | AS or administratively issued registrar | Client Registration Endpoint | Authorizes creating a new registration; may be single-use |
| **Registration Access Token (RAT)** | AS after registration | Client Configuration Endpoint | Bearer credential managing one specific registration |
| `registration_client_uri` | AS | Client Configuration Endpoint | Full URL to read/manage the registration; client must use the exact issued URL |
| `software_statement` | Software publisher or attesting party | Client Registration Endpoint | Signed JWT attesting software metadata; trusted only when the issuer is trusted by the AS |

**IAT and RAT are not the same token.** An IAT authorizes calling the client creation operation. A RAT is bound to an existing registration and authorizes accessing client configuration per the management protocol. Meanwhile, `client_secret` authenticates the client at the Token Endpoint. Never use a RAT in place of a client secret, and never use a client secret to call the Client Configuration Endpoint.

### 2.1. Two High-Impact Bearer Credentials

~~~text
Initial Access Token
  Permission to register a new client
  Authorization: Bearer INITIAL_ACCESS_TOKEN

Registration Access Token
  Permission to manage one specific client
  Authorization: Bearer REGISTRATION_ACCESS_TOKEN
~~~

Both are bearer credentials: whoever holds the token can perform the operations that token authorizes. A leaked IAT can lead to unauthorized client registrations; a leaked RAT can lead to reading, modifying, or deleting the corresponding registration if the AS supports those operations.

## 3. Client Registration Lifecycle

A registration should not be treated as a record created once and forgotten. Both client state and credential state must be managed separately:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Registration request received
    Pending --> Active: Policy and metadata valid
    Pending --> Rejected: Policy check failed
    Active --> Active: Metadata read or updated
    Active --> RotationPending: Due for rotation / suspected secret leak
    RotationPending --> Active: Client confirms new credential
    Active --> Suspended: Client suspended
    Suspended --> Active: Restored after review
    Active --> Revoked: Revoked due to incident or violation
    Suspended --> Revoked: Not restored
    Revoked --> Deprovisioned: Registration and credentials deleted
    Rejected --> [*]
    Deprovisioned --> [*]
~~~

| State | Meaning | Required Actions |
| --- | --- | --- |
| Pending | Registration under review | Hold in staging; do not grant broad permissions yet |
| Active | Client permitted to operate | Monitor owner, metadata, secret expiry, and usage |
| Rotation pending | Credential replacement in progress | Coordinate deploying new secret and invalidating old secret |
| Suspended | Temporarily halted | Block authorizations/tokens per policy; retain audit records |
| Revoked | Credential or client revoked | Invalidate RAT/secret and handle related tokens/grants |
| Deprovisioned | Registration removed | No longer accept `client_id` or credentials |

SAS `RegisteredClient` represents client metadata, whereas Pending/Suspended/Revoked states and approval workflows typically require application-level attributes or management stores. Do not assume that simply deleting a row in `RegisteredClientRepository` immediately makes every access token, refresh token, authorization grant, and cache in other systems disappear.

## 4. What Do RFC 7591 and RFC 7592 Address?

| Document | Status | Scope |
| --- | --- | --- |
| **RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol** | Standards Track | Creating client registrations, client metadata, software statements, and Client Information Response |
| **RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol** | Experimental | Reading, updating, and deleting existing registrations; using Registration Access Tokens |

RFC 7591 describes how a client sends an HTTP POST to the Client Registration Endpoint. The AS validates metadata, issues `client_id`, and optionally issues a secret. RFC 7592 extends the lifecycle via a Client Configuration Endpoint with GET, PUT, and DELETE methods.

**RFC 7592 is an Experimental RFC**, not Standards Track. Therefore, verify that both the AS and clients support management operations before relying on them in operational contracts. Not every AS with DCR supports update/delete or credential rotation.
## 5. Initial Client Registration under RFC 7591

### 5.1. Protecting the Client Registration Endpoint

The Client Registration Endpoint accepts HTTP POST with JSON metadata. The endpoint **MUST** be protected by transport-layer security. The AS may:
- Allow open registration without an IAT, though it should enforce rate limits, quotas, and abuse controls.
- Require an IAT issued out of band by an administrative workflow.
- Require a `software_statement` signed by a trusted software publisher or attesting party.
- Combine IAT, software statement, and metadata to decide whether to accept the registration.

Do not issue non-expiring IATs to every caller just to make DCR integration easier. IATs should have appropriate audience/endpoint bindings, short lifetimes or usage limits, and creation permissions scoped by tenant/partner/software.

### 5.2. Illustrative Metadata Request

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "Portal Web",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/portal"
  ],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile email"
}
~~~

This represents the client's desired metadata. The AS has the right to reject or replace certain values with its own policies/defaults. Never assume every field submitted by the client automatically becomes the accepted configuration.

### 5.3. Validating Metadata Before Issuing client_id

The AS must validate at a minimum:
- `redirect_uris` are absolute URIs, use HTTPS in production, and do not point to endpoints outside the client's control.
- `grant_types` and `response_types` are permitted combinations; never grant weak or unsupported flows.
- `token_endpoint_auth_method` fits the client type. Public clients cannot keep a secret simply by embedding it in an app.
- `scope` falls within the policy-permitted set for the client/tenant.
- `jwks_uri` or `jwks`, if using `private_key_jwt`, pass validation and trust policies.
- `client_uri`, `logo_uri`, `policy_uri`, `tos_uri` are self-declared metadata; validate content/hosts before displaying.
- `software_id`, `software_version`, and `software_statement`, if present, are checked against configured trust relationships.

Self-declared metadata does not prove the sender owns the corresponding domain, logo, or software. Even a signed software statement is only an assertion by its issuer; the AS must still trust that issuer and evaluate the entire registration request.

### 5.4. Software Statement

A Software Statement is a signed or MACed JWT containing claims describing the client software. When used:
1. Verify the signature using a trusted issuer's key.
2. Check `iss`, expiration, and required claims per organizational profile.
3. Validate `software_id`, `software_version`, and related metadata.
4. If JSON metadata conflicts with claims in the statement, apply RFC 7591 precedence rules and policy.
5. Never treat a valid signature as absolute proof that the running binary is the declared software.

## 6. Client Information Response and Credential Protection

An RFC 7591 success response typically uses HTTP `201 Created` and JSON. Condensed example:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "client_id": "portal-client-8f31",
  "client_id_issued_at": 1794800000,
  "client_secret": "ONE_TIME_CLIENT_SECRET",
  "client_secret_expires_at": 1797392000,
  "registration_access_token": "REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://auth.example.com/connect/register/portal-client-8f31",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/portal"
  ],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Values in the example are illustrative. `client_secret` may be omitted if the client is public or uses another authentication method. `client_secret_expires_at` is a UTC NumericDate; `0` indicates a non-expiring secret in RFC 7591. If a secret expiry is set, the AS must publish and enforce that expiration.

Responses containing credentials must be sent over TLS with `Cache-Control: no-store` and `Pragma: no-cache`. The client must store credentials immediately in an appropriate secret vault; never put the response into logs, telemetry, tickets, browser storage, or source control.

### 6.1. Distinguishing client_id and client_secret

- `client_id` is a client identifier, not a password. It may appear in authorization requests and logs per policy.
- `client_secret` is a confidential client's credential. Keep it confidential and send it only to the rightful AS/token endpoint per the registered authentication method.
- `client_secret_expires_at` is a point-in-time timestamp, not a duration from when the response is read.
- `registration_access_token` grants registration management permission, which can be more powerful than the client secret.
- `registration_client_uri` is the management endpoint; never build the URL from `client_id`.

Never log the entire registration response in application logs just to "debug." For auditing, record client ID, owner, metadata version, timestamp, and outcome; never record raw secrets or bearer tokens.

## 7. Initial Access Token and Registration Access Token

### 7.1. Initial Access Token

An IAT is used to call the Client Registration Endpoint when the AS requires protected registration. IATs may be issued via an admin portal, partner onboarding, or an out-of-band workflow.

In Spring Authorization Server 1.5.8, the DCR guide uses a pre-configured registrar client with:
- Grant type `client_credentials`.
- Scope `client.create` to create clients.
- Scope `client.read` if the registrar needs to read registrations.

The IAT used for registration requires an access token with only the `client.create` scope; the SAS guide states this token is single-use and invalidated after registration succeeds. This is a behavior of the SAS guide's implementation, not a universal requirement that every RFC 7591 IAT must be single-use.

### 7.2. Registration Access Token

A RAT is issued by the AS alongside registration details. Per RFC 7592, it is a Bearer Token used at the Client Configuration Endpoint. It is bound to a `client_id` and must be presented in every registration management request.

A RAT can allow its holder to:
- Read current metadata.
- Replace metadata via PUT if supported by the AS.
- Delete the registration via DELETE if supported by the AS.

A RAT is not used at the Token Endpoint to authenticate the client. Never share one RAT across unrelated instances/tenants: a compromised instance could modify or delete the shared registration.

### 7.3. Client Read Example

Use the exact URL returned by the AS:

~~~http
GET /connect/register/portal-client-8f31 HTTP/1.1
Host: auth.example.com
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
~~~

The client must use the issued `registration_client_uri` verbatim. RFC 7592 does not ask the client to append paths or infer the URL from the issuer and `client_id`.

If the RAT is invalid, the AS returns the corresponding Bearer Token error. If the registration has been deprovisioned, remaining RATs must be invalidated; never allow a management token to still authenticate successfully after the client has been deleted.

## 8. Reading, Updating, and Deleting Registrations under RFC 7592

### 8.1. GET — Reading Current Configuration

GET uses the RAT to fetch the metadata currently stored by the AS. The response may include new values for `client_secret` or `registration_access_token`. If the AS issues new credentials in the response, the client **MUST** immediately discard the old credentials and use the new ones for subsequent calls.

Some AS implementations do not return a new RAT on every read. Clients must not assume the token changed unless the response issues a new token.

### 8.2. PUT — Full Metadata Update

RFC 7592 uses HTTP PUT with JSON containing the client's **entire current metadata**. This is not a PATCH sending only a few changed fields.

Key rules:
- The request must include the current `client_id`.
- Submitted metadata replaces prior metadata rather than auto-merging.
- Fields omitted from the request are treated as null/empty requesting removal, depending on AS policy.
- The request must not supply `registration_access_token`, `registration_client_uri`, `client_secret_expires_at`, or `client_id_issued_at`.
- If `client_secret` is sent, it must match the current secret; the client cannot choose a new secret to overwrite the server's. The AS decides whether to issue new credentials.

`client_id` must remain constant across reads/updates. If the response returns a new `client_secret` or RAT, the client must discard the old credential and switch to the new one per the AS's contract.

The client must include all metadata it wishes to keep. Omitting a redirect URI can remove it from the registration after PUT.

### 8.3. DELETE — Deprovisioning a Client

DELETE at the Client Configuration Endpoint is authenticated with the RAT. Success returns HTTP `204 No Content`. The AS must invalidate the registration's `client_id`, `client_secret`, and RAT. RFC 7592 further recommends that the AS revoke associated authorization grants, access tokens, refresh tokens, and related tokens if possible.

Deprovisioning must mean terminating the registration. Merely deleting metadata while leaving credentials or RATs active creates inconsistent state and leaves unintended access paths open.
## 9. Protecting client_secret Throughout Its Lifecycle

### 9.1. Choosing the Right Client Type

| Client Type | Can Keep a Secret? | Appropriate Authentication |
| --- | --- | --- |
| Server-side web application | Yes, if the secret stays strictly on the backend | `client_secret_basic`, `private_key_jwt`, mTLS |
| Service-to-service workload | Yes, if managed secret/key storage exists | `private_key_jwt`, mTLS, or policy-approved secret |
| Browser SPA | Cannot durably keep a secret | Public client, Authorization Code + PKCE |
| Native mobile/desktop app | Cannot keep a shared secret inside binaries | Public client, Authorization Code + PKCE |
| User-installed device/CLI | Usually cannot keep a shared secret | Public client or appropriate proof-of-possession mechanism |

Never issue client secrets to SPAs/mobile apps assuming minification/obfuscation will protect them. Any secret embedded in binaries or JavaScript can be extracted.

### 9.2. Generating High-Entropy Secrets

For confidential clients using shared secrets, the AS should generate secrets with a CSPRNG. Java example:

~~~java
static String generateClientSecret() {
    byte[] random = new byte[32]; // 256 bit
    SecureRandom secureRandom = new SecureRandom();
    secureRandom.nextBytes(random);

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
}
~~~

This is an example of generating a random string; actual entropy depends on the CSPRNG and byte count. Never use UUID v1, timestamps, client IDs, usernames, or predictable strings as client secrets.

RFC 7591 requires issued secrets to be unique per `client_id` and recommends distinct secrets across multiple instances of the same client. Never share one secret across multiple applications/tenants just because they share a developer.

### 9.3. Storage on the Authorization Server Side

In Spring Authorization Server, `RegisteredClient.clientSecret` should be encoded with `PasswordEncoder` before persistence. Never use `{noop}` in production.

~~~java
RegisteredClient registeredClient = RegisteredClient.withId(internalId)
        .clientId(clientId)
        .clientSecret(passwordEncoder.encode(rawClientSecret))
        .clientSecretExpiresAt(secretExpiresAt)
        .build();
~~~

This snippet illustrates building the metadata; `internalId`, `clientId`, `rawClientSecret`, and `secretExpiresAt` must be generated/validated by the registration service. Do not log `RegisteredClient` objects if doing so could expose encoded credentials or sensitive metadata.

`PasswordEncoder` is one-way: the AS cannot recover the raw secret from the hash to display it again. If a management API needs to return a new secret, it must generate a new secret, store the verifier/hash, and return the new raw secret once per contract; never return the encoded hash as if it were usable at the Token Endpoint. For Client Read, return the current secret only if the implementation truly protects and provides the actual raw credential; otherwise, design a dedicated rotation operation.

### 9.4. Storage on the Client Side

Clients must store secrets in:
- The deployment environment's secret manager or vault.
- Kubernetes Secrets encrypted at rest with proper RBAC.
- Cloud/runtime secret management systems.
- OS keychain or secure enclave when supported by the application model.

Avoid storing secrets in:
- Git, Docker image layers, or committed configuration files.
- Browser `localStorage`/`sessionStorage`.
- Logs, APM traces, crash reports, or analytics.
- Chats, emails, and tickets lacking secret management.
- Environment variables if the system allows broad reading/dumping; if used, restrict process, debug, and runtime permissions.

### 9.5. Protecting the Registration Access Token

RATs typically live longer than regular access tokens because they manage registrations. RFC 7592 recommends not expiring RATs while the client remains active if doing so would lock the client out of reading/updating/deleting its registration. The AS may rotate the RAT when the client performs reads/updates.

Therefore:
- RATs need high entropy, TLS, and protection as privileged credentials.
- Never place RATs in browsers, URLs, query strings, source code, or logs.
- Store RATs separately from client secrets and allow only the management service to read them.
- Never share RATs across client instances without common ownership.
- Revoke all RATs when the client is deprovisioned.
- Have a recovery process if a RAT is lost; never automatically issue a new RAT to someone who only knows `client_id`.

## 10. Zero-Downtime Client Secret Rotation

### 10.1. When Is Rotation Needed?

- Secret is approaching `client_secret_expires_at`.
- Personnel or workloads with secret access leave the system.
- Secret appears in logs, tickets, repositories, or incidents.
- Environment/tenant/owner changes.
- Periodically per policy.
- After migrating from shared secrets to `private_key_jwt` or mTLS.

Do not wait until a secret is confirmed abused to start rotating. Establish a rotation schedule, owner, overlap window, and authentication tests before expiration.

### 10.2. Two-Phase Rotation Workflow

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant V as Secret Manager
    participant C as Client workload
    participant T as Token Endpoint
    AS->>AS: Generate new secret and update registration
    AS->>V: Write new secret as a new version
    V-->>C: Deliver new secret via workload identity
    C->>T: Authenticate with new secret
    T-->>C: Client authentication succeeds
    C->>AS: Confirm switch to new secret
    AS->>AS: Revoke old secret
    AS->>AS: Audit rotation complete
~~~

A safe rollout workflow:
1. Identify all workloads using the old secret.
2. Generate the new secret and set its effective time.
3. Write the new secret into the secret manager.
4. Deploy clients reading the new version.
5. Test client authentication at the Token Endpoint.
6. Monitor `invalid_client` errors and traffic still using the old secret.
7. Revoke the old secret once all instances have cut over, or immediately if an incident demands it.
8. Record expiry metadata, version, owner, and audit events; never log raw secrets in audits.

If the AS allows only one active secret at a time, dual-secret overlap is not available by default. For zero-downtime, you can use credential slots/dual-secret validation in a custom authentication provider or migrate to `private_key_jwt`/mTLS. Such an extension requires testing concurrency and rollback.

### 10.3. Rotation under RFC 7592

RFC 7592 allows the AS to issue a new client secret and/or new RAT in Client Read or Client Update responses. Rotation frequency is decided by the AS, not requested by the client sending a self-chosen secret.

When a response returns new credentials:
- The client must persist the new credential before discarding the old one.
- The client must stop using the old credential immediately per protocol semantics.
- The AS should invalidate the old credential if possible.
- Never send a client-chosen new secret in PUT to overwrite the active secret.

### 10.4. Client Secret Expiration

`client_secret_expires_at` is a NumericDate. In SAS, `RegisteredClient.Builder.clientSecretExpiresAt(Instant)` represents the expiration timestamp; `null` indicates no expiration.

The AS must enforce expiration during client authentication, not merely display the timestamp to clients. Before expiration, alert owners and provide a rotation workflow. Never extend expiry simply by bumping the timestamp without rotating the secret or obtaining policy approval.

## 11. Revoking, Suspending, and Deprovisioning Clients

### 11.1. Suspend — Temporarily Halting a Client

Suspension is useful when investigating or awaiting owner confirmation. The AS should:
- Prevent the client from obtaining new tokens.
- Block new authorization requests per policy.
- Retain metadata and audits for investigation.
- Optionally revoke related refresh tokens or sessions if risk warrants it.
- Avoid immediately deleting the registration if restoration may be needed.

Suspended state is usually additional application logic, not a standard HTTP method in RFC 7591.

### 11.2. Revoking Credentials

When a secret or RAT is compromised:
1. Invalidate the exposed credential immediately.
2. Issue a new credential if the client is still permitted to operate.
3. Consider revoking authorization grants and refresh tokens.
4. Evaluate active access tokens; self-contained JWTs may remain valid until expiry if Resource Servers verify only signatures and expirations.
5. Inspect logs, token usage, IPs/devices, and when the credential leaked.
6. Notify owners per incident response procedures.

Do not just swap the secret and ignore previously issued refresh tokens or access tokens. Secret rotation protects future client authentications; it does not make old tokens vanish automatically.

### 11.3. Deprovisioning

When a client is no longer used:
- Confirm with the owner and verify workloads have stopped.
- Delete or disable the registration per policy.
- Invalidate `client_id`/secret/RAT.
- Revoke authorization grants and access/refresh tokens if possible.
- Remove custom metadata mappings, redirect URIs, software statement references, and secret manager entries.
- Retain audit records per retention policy.
- Return appropriate authentication errors for requests after deletion.

If an application must be recreated later, it is usually better to create a new registration with a new `client_id` rather than reusing a deprovisioned client ID.
## 12. Enabling Dynamic Client Registration in Spring Authorization Server 1.5.8

### 12.1. Default Endpoint and Requirements

Per the SAS 1.5.8 documentation:
- The OIDC Dynamic Client Registration Endpoint is **disabled by default**.
- The default endpoint is `/connect/register`.
- `OidcClientRegistrationEndpointConfigurer` configures the request converter, `AuthenticationProvider`, response handler, and error handler.
- The endpoint uses OAuth2 Bearer access tokens.
- Client Registration requests require the `client.create` scope.
- Client Read requests require the `client.read` scope.
- A `JwtDecoder` bean is REQUIRED for this endpoint.

Illustrative configuration:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .clientRegistrationEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

The application still needs other infrastructure beans such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, issuer, JWK source, `JwtDecoder`, and login security chains. Do not treat the snippet above as a standalone runnable Authorization Server.

Example declaring `JwtDecoder` from a JWK source:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

The JWK source must be configured with the AS's signing keys. Never expose private keys in public JWKS and never skip signature/issuer validation on access tokens presented to the registration endpoint.

### 12.2. Configuring the Endpoint Path

You can set the path in `AuthorizationServerSettings`:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcClientRegistrationEndpoint("/connect/register")
            .build();
}
~~~

If changing the path, update `registration_endpoint` metadata and corresponding client integrations. Reverse proxies must advertise the external HTTPS URL; never return internal hosts to clients.

### 12.3. Configuring the Registrar Client

A registrar is a pre-provisioned client authorized to create and read registrations:

~~~java
RegisteredClient registrar = RegisteredClient.withId("registrar-internal-id")
        .clientId("registrar-service")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
~~~

`registrarSecret` must come from a secret manager; do not put raw secrets in code. In production, registrars should have minimal scopes for their job. If a registrar only creates clients and never needs to read them, do not grant `client.read`.

### 12.4. Obtaining an Initial Access Token

To register a client, the registrar requests an access token with only the `client.create` scope:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64(registrar-service:REGISTRAR_SECRET)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

The SAS guide requires the registration token to contain only `client.create`; if extra scopes are present, the registration request is rejected. In the guide's flow, the IAT is single-use and invalidated after successful registration.

To read registrations, the registrar obtains a separate access token with the `client.read` scope per the application's policy/token configuration. Avoid tokens carrying broad combined permissions unless necessary.

### 12.5. Registering and Reading a Client

Registration request:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json

{
  "client_name": "Orders Portal",
  "redirect_uris": ["https://orders.example.com/login/oauth2/code/portal"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile"
}
~~~

Store `registration_access_token` and `registration_client_uri` from the response in a secret store/management store. When reads are needed, send GET with the RAT:

~~~http
GET https://auth.example.com/connect/register/CLIENT_CONFIGURATION_PATH
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
~~~

In the SAS example, the Client Read response contains registration metadata without a new `registration_access_token`. Do not assume every GET automatically rotates the RAT; rely on the actual response and AS contract.

### 12.6. Customizing Registration Validation

SAS allows configuring the `AuthenticationProvider` to enforce appropriate validators. The example below combines default validators for redirect URIs, post-logout redirect URIs, JWKS URIs, and scopes:

~~~java
private static Consumer<List<AuthenticationProvider>> registrationValidators() {
    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setAuthenticationValidator(
                    OidcClientRegistrationAuthenticationValidator.DEFAULT_REDIRECT_URI_VALIDATOR
                            .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                            .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_JWK_SET_URI_VALIDATOR)
                            .andThen(OidcClientRegistrationAuthenticationValidator.SIMPLE_SCOPE_VALIDATOR)
            );
        }
    });
}
~~~

Then pass this consumer into `clientRegistrationEndpoint(...).authenticationProviders(...)`. This is the extension point for preserving default validators while adding organizational policies such as scope allowlists, trust tiers, redirect domain ownership, or software statements. Never replace all default validators with a trivial check verifying only `client_name`.

### 12.7. Using a Durable Repository

Registrar examples in the SAS guide may use `InMemoryRegisteredClientRepository` for demos. Production needs a durable repository such as JDBC or a custom implementation so registrations survive restarts, with backups, transactions, and auditing. Managing updates/deletes requires atomic updates by internal registration ID; never rely on caches or in-memory copies as the source of truth.

## 13. SAS Support Boundaries and What Must Be Extended

### 13.1. What Does SAS 1.5.8 Support?

SAS 1.5.8 documentation describes:
- POST to create an OIDC Client Registration.
- GET Client Read at the issued URL.
- `OidcClientRegistrationEndpointConfigurer` to customize request converters, authentication providers, response handlers, and error handlers.
- `OidcClientRegistrationAuthenticationProvider` to validate and create registrations.
- `OidcClientConfigurationAuthenticationProvider` to handle Client Read.
- Custom converters to store and return extended metadata.

### 13.2. Do Not Confuse Client Read with Full RFC 7592 Management

The SAS 1.5.8 guide documents **registering and retrieving/reading** clients. It does not document default RFC 7592 PUT Client Update and DELETE Client Deprovision operations. Therefore:
- Do not assume SAS provides a built-in PUT API to change redirect URIs or secrets.
- Do not assume a DELETE endpoint automatically deprovisions clients.
- Do not advertise update/delete capabilities in system contracts unless actually implemented.
- If full RFC 7592 is needed, build an extension/management service or choose an AS supporting the full protocol.

RFC 7592 is also Experimental; decide clearly whether interoperability with this RFC is required or whether internal lifecycle management suffices.

### 13.3. Extended Management Service Architecture

A dedicated service can perform:
1. Validate the RAT and bind the token to the exact client ID.
2. Verify owner/tenant and read/update/delete permissions.
3. Re-validate all metadata after updates.
4. Generate and encode a new secret if rotation is needed.
5. Persist the updated registration transactionally.
6. Invalidate old credentials and necessary authorizations/tokens.
7. Emit audit events and return an appropriate Client Information Response.
8. On DELETE, deprovision the registration and invalidate all remaining RATs.

Never write a controller that accepts `client_id` and lets callers edit any `RegisteredClient`. The management service must verify the bearer token, audience/resource, registration binding, tenant, and operation permissions.

### 13.4. Updating RegisteredClient in the Application Store

`RegisteredClient` has `clientSecret` and `clientSecretExpiresAt`. The builder can clone a registration with a new secret:

~~~java
RegisteredClient replacement = RegisteredClient.from(current)
        .clientSecret(passwordEncoder.encode(newRawSecret))
        .clientSecretExpiresAt(newSecretExpiry)
        .build();
~~~

This builds only the new configuration object. Database persistence must run through the application's repository/persistence implementation inside a transaction, ensuring the right record is updated by internal ID and client ID. Never change the client ID merely when rotating a secret.

When updating other metadata, mutate only policy-permitted fields such as redirect URIs, authentication methods, or scopes. Never let clients self-escalate grants/scopes/authentication methods beyond their approved trust tier.

### 13.5. Custom Metadata Converters

If you need to store metadata outside standard `RegisteredClient` fields, SAS provides extension points to customize converters between `OidcClientRegistration` and `RegisteredClient`. For instance, `logo_uri` or `contacts` can be persisted in `ClientSettings` or a separate metadata store.

Allow only an explicit field allowlist; never accept arbitrary JSON properties and persist them blindly. When Client Read returns metadata, strip internal fields, secret hashes, token store identifiers, and operational data that do not belong in a Client Information Response.
## 14. Controlling Metadata After a Client Is Active

Registration metadata directly impacts authorization security:
- Adding a redirect URI can send authorization codes to a new domain.
- Adding a grant type can open new ways to obtain tokens.
- Adding a scope can expand the privileges a client may request.
- Changing the token endpoint authentication method can remove or weaken client authentication.
- Changing `jwks_uri` can swap the public key source the AS uses to verify `private_key_jwt`.
- Changing `post_logout_redirect_uris` can affect logout redirects.
- Changing `client_name` or `logo_uri` can alter consent screen content shown to users.

Therefore, metadata updates should have per-field policies. For example:
- Newly added redirect URIs require domain/ownership verification or approval.
- Privilege-expanding grant types and scopes require approval.
- Switching authentication methods from shared secret to private key requires key onboarding.
- User-facing display metadata must undergo content checks.
- Custom claims must never be used as security entitlements unless verified by validators.

Never let a client update `redirect_uris` to arbitrary domains simply because it holds a valid RAT. A RAT proves registration management authority; the AS can still apply additional policies or reject updates.

## 15. Handling Exposed Credential Incidents

When a client secret or RAT is suspected compromised, prioritize narrowing exposure:

1. Identify the credential type, client ID, tenant, owner, and permission scope.
2. Revoke the RAT immediately if a RAT leaked; a RAT can read or alter the registration.
3. If a client secret leaked, invalidate the old secret and issue a new secret/key per authentication method.
4. If a registrar IAT leaked, revoke the IAT and review all clients created during the affected window.
5. Temporarily suspend the client if the blast radius is unclear.
6. Revoke related refresh tokens/grants and evaluate active access tokens.
7. Inspect Token Endpoint, Registration Endpoint, Client Configuration Endpoint logs, and audit trails.
8. Check whether redirect URIs, scopes, grant types, JWKS URIs, or authentication methods were altered without authorization.
9. Notify the owner and deploy new credentials.
10. Preserve evidence, timestamps, event IDs, and remediation decisions without logging raw credentials.

If a RAT leaks, an attacker could use it to alter metadata or deprovision the client if supported by the AS. Consequently, a RAT compromise incident can be more severe than routine client secret rotation.

## 16. Registration Lifecycle Test Matrix

### 16.1. Registration and Client Read

| Test | Action | Expected Result |
| --- | --- | --- |
| DCR disabled | POST to registration endpoint when OIDC DCR is off | Client creation disallowed |
| Missing IAT | POST without bearer token in protected mode | Rejected |
| Wrong IAT scope | Token lacks exact `client.create` | Rejected |
| Reuse IAT | Reuse already-consumed IAT in SAS guide flow | Rejected |
| Invalid redirect URI | Submit invalid or out-of-policy URI | Registration rejected |
| Unsupported grant | Request grant unsupported by AS | Rejected or replaced per published policy |
| Public client secret | Register `none` client | No unnecessary secret issued |
| Confidential client | Register `client_secret_basic` | Secret generated and expiry published |
| Read without RAT | GET Client Configuration without RAT | Rejected |
| Read with wrong RAT | Client A's RAT used on Client B | Rejected |
| Read wrong scope | Access token missing `client.read` | Rejected |
| Read after delete | GET deprovisioned registration | RAT invalidated; cannot read |
| Metadata consistency | Compare response with persisted `RegisteredClient` | Matches accepted metadata |

### 16.2. Update, Rotation, and Delete

| Test | Action | Expected Result |
| --- | --- | --- |
| PUT incomplete metadata | Omit a field that must be kept | System handles full-replacement semantics properly |
| PUT `client_id` mismatch | Send a different client ID | Rejected |
| PUT secret overwrite | Client sends a self-chosen secret | Rejected; only AS issues secrets |
| PUT untrusted redirect | Add an unapproved redirect URI | Rejected or awaits approval |
| Rotate client secret | AS issues new secret | Client uses new secret; old secret invalidated per policy |
| Secret expiry | Use secret after `client_secret_expires_at` | Client authentication fails |
| RAT rotation | AS returns new RAT | Client adopts new RAT and discards old RAT |
| RAT revoked | Call management with old RAT | 401 |
| DELETE valid RAT | Deprovision client | 204 and invalidates credentials/registration |
| DELETE wrong RAT | Use another client's RAT | Rejected |
| Delete outstanding tokens | Delete client with active refresh/access tokens | Revoked per policy and token behavior verified |
| Concurrent update | Two simultaneous PUT requests | Versioning/locking prevents lost updates |
| Concurrent rotation | Two simultaneous rotations | Only the valid credential version remains active |
| Retry after timeout | Client unsure if update succeeded | Idempotency/version strategy prevents losing the new secret |

If deploying SAS 1.5.8 with only the default endpoint, PUT/DELETE tests should confirm those methods are unsupported rather than assuming they work. Update/delete tests apply only once a management extension has been built.

### 16.3. Security and Operational Testing

- Raw client secrets never appear in logs, tracing, metrics, or error responses.
- RATs and IATs never appear in query strings, source code, or browser storage.
- TLS certificates are verified by registrars/clients.
- `Cache-Control: no-store` and `Pragma: no-cache` appear on responses containing credentials.
- Client secrets are stored via `PasswordEncoder`, never `{noop}`.
- Public clients never receive shared secrets embedded in apps.
- Registrar clients hold only `client.create` and/or `client.read` as needed.
- Software statements with bad issuer/signature/expiry are rejected.
- Redirect URIs, scopes, grant types, and auth methods all pass validators.
- Deprovisioning invalidates all remaining RATs.
- Token/grant lifecycles are tested separately after a client is suspended/revoked/deleted.
- Audits record client ID, actor, metadata version, and outcome without recording raw secrets.

## 17. Case Study Exercise

An enterprise has a registrar service using Spring Authorization Server 1.5.8 to register partner portal clients. Each portal is a confidential client using `client_secret_basic`. One client has metadata:

~~~json
{
  "client_id": "partner-portal-7",
  "client_name": "Partner Portal",
  "redirect_uris": ["https://partner.example.com/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "client_secret_expires_at": 1797392000,
  "registration_client_uri": "https://auth.example.com/connect/register/partner-portal-7"
}
~~~

Incident:
- Client secret appeared in CI logs.
- RAT was stored in a shared config file across multiple instances.
- Partner wants to change redirect URI and rotate the secret simultaneously.
- Ops team sent PUT to SAS `/connect/register/partner-portal-7` and received a method error.
- Client still holds an old refresh token and an unexpired JWT access token.

Analyze:

1. How do secret and RAT permissions differ? Which token must be revoked first when the RAT leaks?
2. Why should a RAT not be shared across unrelated instances?
3. How do you roll out secret rotation without portal downtime?
4. Why does default SAS 1.5.8 not handle full RFC 7592 PUT/DELETE?
5. Which services/repositories need to be extended to update metadata and credentials?
6. How do you verify the new redirect URI is under the partner's control?
7. After rotation, how are already-issued refresh tokens and access tokens handled?
8. Design a deprovisioning and auditing workflow for retired clients.
9. Propose tests for wrong RAT, expired secret, concurrent rotation, metadata update, and delete.

**Hint:** IAT creates registrations; RAT manages registrations; client secret authenticates clients at the Token Endpoint. SAS 1.5.8 provides DCR POST and Client Read GET, without default documented management PUT/DELETE. A custom management service or an AS supporting RFC 7592 is required. Rotation must replace secrets in both the AS and client secret store via a coordinated workflow; replacing a secret does not automatically revoke already-issued tokens.

## 18. Production Checklist

1. **Registration policy:** decide open vs. protected registration, registrar owners, quotas, rate limits, and approvals.
2. **IAT:** issued per registrar, minimal scope, usage limits, and revocation on suspected leak.
3. **Metadata validation:** validate redirect URIs, grants, scopes, auth methods, JWKS, and software statements.
4. **Client type:** public clients never use embedded secrets; confidential clients have proper credential storage.
5. **Credential generation:** use a CSPRNG with high entropy.
6. **Secret storage:** `PasswordEncoder` at AS; secret manager/vault at client; never log raw secrets.
7. **RAT:** stored separately, high entropy, bound to client, never used at Token Endpoint.
8. **Registration URL:** use the exact `registration_client_uri` issued by the AS.
9. **Expiry:** track `client_secret_expires_at`, alert, and rotate before expiration.
10. **Rotation:** defined owner, versioning, overlap window, rollback, and old secret revocation.
11. **RFC 7592:** clarify whether the AS supports GET/PUT/DELETE and credential rotation.
12. **SAS version:** verify DCR disabled-by-default, `JwtDecoder`, `client.create`, `client.read`, and management support for your exact version.
13. **Repository:** use durable persistence, transactions/version control, and auditing for the client lifecycle.
14. **Suspend/revoke:** block new tokens, revoke credentials, handle active grants and tokens.
15. **Deprovision:** invalidate client ID, secret, RAT, and related authorizations/tokens.
16. **Incident response:** runbooks for IAT/RAT/client secret compromise.
17. **Observability:** audit metadata versions and outcomes; redact all credentials.
18. **Testing:** test registration/read/update/delete, rotation, replay, races, expiry, and token behavior.

## 19. Authoritative Standards and Spring References

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client metadata, registration request/response, software statements, and security considerations.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): Client Read, Update, Delete, Registration Access Token, and credential rotation. This is an Experimental RFC.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client types, client authentication, and token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): protecting bearer credentials and Authorization headers.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): modern security practices for OAuth clients and token handling.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): OIDC client registration metadata and Client Read.
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling DCR, registrar scopes, initial access tokens, registration, and client retrieval.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, providers, converters, and response handlers.
- [Spring Authorization Server 1.5.8 — RegisteredClient.Builder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.Builder.html): `clientSecret`, `clientSecretExpiresAt`, and client metadata.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClientRepository` and storing client registrations.

**Key takeaway:** DCR creates a client registration; managing its lifecycle additionally requires read, update, rotation, suspend, revoke, and deprovision operations. IATs authorize creating new clients; RATs manage a specific registration; client secrets authenticate confidential clients at the Token Endpoint. RFC 7591 defines initial registration, while Experimental RFC 7592 extends GET/PUT/DELETE and credential rotation. Spring Authorization Server 1.5.8 disables DCR by default and supports registration and Client Read when the endpoint is enabled, with `client.create` and `client.read` registrar scopes; do not assume PUT/DELETE management is built in. Store secrets via `PasswordEncoder`, keep raw credentials in a secret manager, validate metadata against policy, and invalidate all related credentials/tokens when a client is revoked.
