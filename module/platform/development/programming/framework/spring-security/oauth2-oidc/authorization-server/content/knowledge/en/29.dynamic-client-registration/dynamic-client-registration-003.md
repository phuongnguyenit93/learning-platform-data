# Protecting Registration with Initial Access Tokens and Client Registration Permissions

## 1. Problem: Who Is Allowed to Create New OAuth Clients?

A platform has multiple product teams needing to integrate with the Authorization Server. If anyone could send JSON to the Client Registration Endpoint and create a client, an attacker could self-register an application, declare redirect URIs under their control, request broad grants/scopes, or create many clients to abuse the system.

**Dynamic Client Registration (DCR)** allows software or an organization to register OAuth/OIDC clients through a protocol endpoint. Yet dynamic registration does not mean public registration. Under the protected registration model, the Authorization Server only accepts requests from parties granted permission to register, via an **initial access token** or an equivalent protection mechanism.

This lesson focuses on three credentials/permissions to distinguish:

1. **Initial access token**: the initial token, used by an approved registrar to create a new client.
2. **Scope client.create**: the permission allowing a registrar to invoke the registration operation in Spring Authorization Server.
3. **Registration access token**: a separate token returned after successful registration, used to read client configuration via Client Read when granted the corresponding permission.

In Spring Authorization Server (SAS) 1.5.8, the OIDC Client Registration Endpoint is **disabled by default**. When enabled, the endpoint is protected as an OAuth Resource Server, requiring a Bearer access token; a registration request requires the `client.create` scope, while Client Read requires the `client.read` scope. The initial token used for a registration request must contain only the `client.create` scope; this token is single-use and is invalidated after the client is successfully registered.

This lesson belongs to the **Dynamic Client Registration** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The overall goal of the module is **learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application**.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish open registration from protected registration under RFC 7591.
- Explain the role and lifecycle of an initial access token.
- Configure a dedicated registrar in `RegisteredClientRepository`.
- Issue an initial access token with the exact `client.create` scope and use it solely for registration.
- Enable the OIDC Client Registration Endpoint in Spring Authorization Server 1.5.8.
- Distinguish `client.create`, `client.read`, `registration_access_token`, and the new client's tokens.
- Control grants, redirect URIs, scopes, client authentication methods, and metadata in registration requests.
- Design issuance, storage, revocation, and auditing workflows for registrar credentials.
- Write integration tests for valid registration, missing/wrong-scope tokens, replayed tokens, and Client Read.

> **Version scope:** The Spring examples use the Spring Authorization Server 1.5.8 and Spring Security 6.x APIs. RFC 7591 describes the general protocol; the `client.create`/`client.read` scopes, the single-use initial token rule, and how the endpoint is enabled below are specific behaviors guided by the SAS 1.5.8 documentation. The assigned SPECIAL_NOTE for this lesson is left blank.

## 2. DCR and Protected Registration under RFC 7591

RFC 7591 defines a Client Registration Endpoint accepting HTTP POST with client metadata in JSON format. The endpoint **must be protected by transport-layer security**. The Authorization Server may protect the endpoint as an OAuth protected resource and require an initial access token to restrict which organizations or developers may register clients.

Two common models:

| Model | Who can register? | Protection |
| --- | --- | --- |
| Open registration | Any software that can reach the endpoint, per server policy | TLS, validation, abuse protection, quotas, and metadata controls |
| Protected registration | Only approved developers/registrars | TLS + initial access token or equivalent authorization mechanism |

For enterprise systems, partner platforms, or shared authorization services, protected registration is usually more appropriate because the organization needs to know who is creating clients and why.

### 2.1. What Is an Initial Access Token?

RFC 7591 defines an initial access token as an OAuth access token issued by the Authorization Server to a developer/client to authorize calling the Client Registration Endpoint. The RFC does not prescribe a single format or issuance method for this token; issuance and verification are outside the scope of the general protocol.

A typical workflow:

1. A developer or team submits an onboarding request.
2. Operators verify the organization, owner, environment, and integration purpose.
3. The Authorization Server issues an initial access token to the approved registrar.
4. The registrar calls the Client Registration Endpoint with the Bearer token.
5. The server validates the token, scope, policy, and request metadata.
6. If valid, the server creates the registration and returns client information.

The initial access token represents **permission to register**, not necessarily the new client's credential. Nor does it prove that all metadata declared by the registrant is valid. The server must still validate the request and may require a software statement or approval.

### 2.2. Initial Access Token vs. Registration Access Token

| Property | Initial access token | Registration access token |
| --- | --- | --- |
| When issued? | Before creating the client | After client registration succeeds |
| Who uses it? | Approved registrar/developer | Subject granted permission to manage/read the corresponding registration |
| Purpose | Authorize creating a new client | Access Client Read or supported registration operations |
| Scope | Can be restricted to a single registration | Bound to a specific registration |
| In SAS 1.5.8 | Initial token must have only the `client.create` scope, single-use | Registration response includes `registration_access_token`; Client Read uses a Bearer token with `client.read` permission |

Do not save an initial access token and use it as a long-lived API key. Do not take one client's registration access token to read another client's registration.

## 3. Three Permission Layers in the Registration Flow

A secure DCR workflow can separate:

1. **Organizational onboarding permission:** who may request client creation, who approves it, and which registrar receives an initial token.
2. **Registrar protocol permission:** an access token with the `client.create` scope to call the Registration Endpoint.
3. **New client usage permissions:** grant types, scopes, redirect URIs, client authentication methods, and token policies recorded in the registration.

These three layers do not substitute for one another. A registrar having `client.create` does not mean the new client can use every grant; the registration request is still constrained by validation and policy.

```mermaid
flowchart TD
    A[Developer / Product Team] --> B[Onboarding & Approval]
    B --> C[Approved Registrar]
    C --> D[Initial Access Token: client.create]
    D --> E[POST Client Registration Endpoint]
    E --> F{Token + metadata valid?}
    F -->|No| G[Reject request]
    F -->|Yes| H[Persist RegisteredClient]
    H --> I[Return client_id + registration credentials]
    I --> J[Client uses registered grants/scopes]
    I --> K[Client Read with registration_access_token]
```

The Authorization Server must verify the registrar before processing metadata. Then the server must verify metadata independently, such as exact redirect URIs, supported grants, allowed scopes, and appropriate authentication methods.

## 4. Enabling the OIDC Client Registration Endpoint in Spring Authorization Server

In SAS 1.5.8, Dynamic Client Registration is part of OIDC Client Registration. The endpoint is **disabled by default** because many systems do not need dynamic client onboarding.

To enable the endpoint:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(oidc ->
                oidc.clientRegistrationEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
```

This is the endpoint configuration portion. The application still needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, key/token services, and related OAuth/OIDC beans.

### 4.1. JwtDecoder Is a Required Dependency

SAS 1.5.8's Client Registration Endpoint is an OAuth protected resource accepting Bearer access tokens. The SAS documentation requires a `JwtDecoder` bean for this endpoint.

Example:

```java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
```

The example above assumes the application already has an appropriate `JWKSource<SecurityContext>`. `JwtDecoder` verifies the JWT access token sent to the Registration Endpoint; it does not replace checking the `client.create` scope or registrar policy.

### 4.2. The Endpoint Handles Both Registration and Client Read

`OidcClientRegistrationEndpointFilter` handles two types of requests:

- Client Registration: creating a new registration.
- Client Read: retrieving an already registered client's configuration.

Default components include:

| Component | Role |
| --- | --- |
| OidcClientRegistrationAuthenticationConverter | Converts the HTTP request into an authentication request |
| OidcClientRegistrationAuthenticationProvider | Processes creating a client registration |
| OidcClientConfigurationAuthenticationProvider | Processes Client Read |
| Success handler | Serializes the OIDC Client Registration response |
| Failure handler | Returns the OAuth error response |

Keep the default converters/providers if you only need to protect the endpoint by scope. Customize only when you have specific metadata or validation requirements.

## 5. Configuring the Registrar in RegisteredClientRepository

A registrar is a pre-created OAuth client granted permission to register new clients. An illustrative configuration:

```java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder) {

    RegisteredClient registrar = RegisteredClient.withId(
                    UUID.randomUUID().toString())
            .clientId("platform-registrar")
            .clientSecret(passwordEncoder.encode("replace-with-managed-secret"))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("client.create")
            .scope("client.read")
            .build();

    return new InMemoryRegisteredClientRepository(registrar);
}
```

This is an educational example. Production needs to store the registrar in a durable repository, hash the secret with `PasswordEncoder`, retrieve the secret from a secret manager, and have a rotation procedure. Never use literal secrets in source code.

### 5.1. Why Does the Registrar Use Client Credentials?

The registrar is a workload or service performing onboarding; it does not need an End-User login to perform this task. Client Credentials fits machine-to-machine scenarios when the registrar is trusted and managed as a service account.

Other client authentication methods may be used if policy allows, such as `private_key_jwt` or mTLS. What matters is properly authenticating the registrar before issuing an initial access token.

### 5.2. Registrar Scopes Are Not the New Client's Scopes

`client.create` and `client.read` are the registrar's permissions on the Client Registration Endpoint. They are not business scopes of the created application.

| Subject | Scope | Purpose |
| --- | --- | --- |
| Registrar | client.create | Create a registration |
| Registrar | client.read | Read a registration when authorized |
| New client orders-web | openid, orders.read | Permissions the application requests at runtime |
| New client billing-worker | billing.write | Business permissions of the workload if approved |

Do not add `client.create` to every new client. Regular clients must not be allowed to create additional clients on their own.

## 6. Obtaining an Initial Access Token with the Exact Scope

According to the SAS 1.5.8 guide, the access token used for a Client Registration request must have **a single scope: `client.create`**. If the token contains additional scopes, the Registration Endpoint will reject the request.

Example Token Endpoint request:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
```

Illustrative response:

```json
{
  "access_token": "INITIAL_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 120,
  "scope": "client.create"
}
```

The `expires_in` value above is illustrative. Choose a short lifetime based on risk and your onboarding flow; do not copy the number without a policy.

### 6.1. Do Not Request Business Scopes Together with the Initial Token

The following request is invalid under the SAS 1.5.8 rule for initial registration tokens:

```http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create%20orders.read
```

A token with `client.create orders.read` will be rejected by the Registration Endpoint. The registrar should obtain a dedicated token for the client-creation task, carrying only the required scope.

### 6.2. Initial Tokens Must Be Protected as High-Privilege Credentials

An initial token allows creating OAuth clients. If leaked, an attacker could create registrations with redirect URIs or metadata they control, within the limits of server validation.

Therefore:

- Transmit only over HTTPS.
- Do not put it in URLs, query strings, source code, or logs.
- Do not share it over unprotected tickets/chats.
- Keep the token in memory/secret store for a short time.
- Scope the registrar by organization/environment.
- Prefer short-lived and one-time use tokens.

## 7. Registering a Client with an Initial Access Token

A Client Registration request is an HTTP POST with a JSON body. The initial access token is sent in the Authorization Bearer header.

```http
POST /connect/register HTTP/1.1
Host: login.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "orders-web",
  "application_type": "web",
  "redirect_uris": [
    "https://orders.example.com/login/oauth2/code/company"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "scope": "openid profile orders.read",
  "token_endpoint_auth_method": "client_secret_basic"
}
```

`/connect/register` is the path commonly used in SAS examples; verify the configured endpoint path in your deployment. The JSON above is only a sample request and does not mean every metadata field is accepted under every policy.

### 7.1. Request Metadata Is Untrusted Input

An authenticated registrar only proves **who sent the request**. Values such as `client_name`, `redirect_uris`, `grant_types`, `scope`, `logo_uri`, and `jwks_uri` must still be validated.

The server should check:

- Grant types are in the system's allowlist.
- Response types match the grants and OIDC flow.
- Redirect URIs are exact, HTTPS in production, and free of dangerous wildcards.
- Post-logout redirect URIs are validated separately.
- Token endpoint authentication method matches the client type.
- Scopes belong to the permitted set and are approved for the application.
- JWKS URI/sector identifier/logo URLs do not lead to SSRF or malicious content.
- Unsupported metadata or metadata with wrong data types is rejected.

### 7.2. Client Response After Registration

Illustrative response:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "client_id": "generated-client-id",
  "client_secret": "GENERATED_CLIENT_SECRET",
  "client_name": "orders-web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "redirect_uris": [
    "https://orders.example.com/login/oauth2/code/company"
  ],
  "scope": "openid profile orders.read",
  "registration_access_token": "REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://login.example.com/connect/register/generated-client-id"
}
```

This is an illustrative response. The server may return different metadata fields depending on implementation. Secrets are only shown per the response contract at issuance time; the client must store them securely immediately upon receipt.

### 7.3. The Initial Access Token Is Single-Use in SAS

Per the SAS 1.5.8 guide, the initial access token **can only be used once**. After a client is successfully registered, the token is invalidated. If the same token is sent again, the request must fail.

One-time use reduces the replay window for a stolen token. However, you should test behavior when a request times out after the server persisted the client but the client missed the response. Do not automatically retry with the same token or create duplicate registrations; first have a reconciliation/audit workflow to determine the outcome of the initial call.

## 8. Client Read and registration_access_token

After registration, the response may provide:

- `registration_access_token`: Bearer token to access the registration.
- `registration_client_uri`: URI used for Client Read.

Client Read uses a registration access token with the `client.read` scope per SAS 1.5.8 policy. Example:

```http
GET /connect/register/generated-client-id HTTP/1.1
Host: login.example.com
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
```

The Client Read response returns the corresponding client metadata; it does not return `registration_access_token` as part of the read response. Protect the registration access token like an administrative credential since it grants access to registration data.

### 8.1. Do Not Misuse Tokens

| Token | Where Used? | Permissions |
| --- | --- | --- |
| Registrar client secret/private key | Token Endpoint | Authenticates the registrar |
| Initial access token | Client Registration POST | Creates a client; SAS requires `client.create` only and one-time use |
| Registration access token | Client Read | Reads the corresponding registration with `client.read` |
| New client secret/private key | New client's Token Endpoint | Authenticates the new client per its registration |
| New client's business access token | Resource Server/API | Calls APIs per granted scopes/audience |

Do not use `registration_access_token` to call business APIs. Do not use the new client's access token to read its registration if it lacks the right permissions and bindings.

### 8.2. Client Read Does Not Mean Reading All Clients

A registration access token is bound to a specific registration. A token for `orders-web` must not be able to read `billing-worker`'s configuration. The server must verify the token, registration identifier, and access rights; never rely solely on a caller-supplied client ID.

### 8.3. SAS Management Scope Must Be Verified

The OIDC Dynamic Client Registration specification defines registration management operations broader than read-only. However, in the SAS 1.5.8 documentation, the endpoint is explicitly documented for **Client Registration and Client Read**. Do not assume PUT update or DELETE registration is supported just because the OIDC standard defines them; verify your actual API/version before designing the lifecycle.

## 9. Configuring the Registrar and Token Policy in Spring

A registrar is typically a confidential client using Client Credentials. Tokens issued for client creation should carry only the `client.create` scope.

Illustrative token settings example:

```java
RegisteredClient registrar = RegisteredClient.withId(
                UUID.randomUUID().toString())
        .clientId("platform-registrar")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(2))
                .build())
        .build();
```

The two-minute lifetime is illustrative, not mandatory. If a `client.read` token is needed, issue it separately via an appropriate workflow. When requesting an initial token to register, the request scope remains solely `client.create`.

### 9.1. Issuing the Initial Token

The flow can use Client Credentials:

```text
grant_type=client_credentials
scope=client.create
```

Do not grant `client.create` to a service that only needs Client Read. Separate registrar roles by responsibility:

- Registration service: `client.create`.
- Registration inspection service: `client.read`.
- Admin workflow: approval and operational permissions in a separate administrative layer.

### 9.2. One-Time Initial Token and State Persistence

To guarantee one-time use in a multi-instance environment, token/authorization state must be shared and updated atomically. If each node has its own authorization store, the same token could be accepted concurrently on two nodes before the invalidated state is synchronized.

SAS uses `OAuth2AuthorizationService` to store authorization state. Production requires durable storage, transactions, and a consistent state update mechanism. Test concurrency to prove one initial token cannot create two clients.

## 10. Scoping Registrars by Environment and Organization

A system may have multiple registrars:

| Registrar | Environment/Scope | Permissions |
| --- | --- | --- |
| internal-dev-registrar | Development clients | `client.create`, optionally `client.read` in dev |
| partner-onboarding | Partner sandbox | Only creates clients for approved partners |
| production-registrar | Production | Creates clients per approval ticket and strict policy |
| registration-auditor | Production read-only | `client.read` within assigned scope |

Not all registrars should share the same secret or permissions. Separating credentials allows revoking a compromised registrar without disrupting all onboarding.

### 10.1. Binding a Registrar to a Tenant/Organization

The `client.create` scope indicates the registrar has protocol-level permission to create registrations. In a multi-tenant system, add application-layer policy to determine which tenants the registrar is allowed to create clients for.

Do not trust `organization_id` or `tenant_id` sent by the caller in JSON unless verified against the registrar's identity and approval record. Use server-side policy or a signed software statement to bind metadata.

### 10.2. Environment Isolation

Initial tokens issued for sandbox must not work in production. Isolate issuers, registrar credentials, audiences/resources, and storage per environment. Never copy production registration tokens into local development or CI logs.

## 11. Metadata Validation and Constraining New Client Permissions

An initial access token only grants permission to call the endpoint. It **does not exempt the registration payload from validation**.

### 11.1. Redirect URI

The Redirect URI is a critical security boundary of the Authorization Code Flow. Validate exact URIs, scheme/host/path, and per-client policy. Avoid broad wildcards, open redirects, `localhost` URIs in production, or domains not owned by the organization.

Do not accept a redirect URI passed by a registrar simply because the registrar holds `client.create`; the registrar itself could have a bug or be compromised.

### 11.2. Grant Types and Response Types

Allow only grant types the server truly supports and the client requires. Never grant Client Credentials to browser apps; never grant Password Grant; never let public clients use a client secret as if it could be kept confidential.

Response types must match the Authorization Endpoint and grants. For instance, an Authorization Code client typically uses `response_types` of `code` and should not advertise implicit responses if not implemented and allowed.

### 11.3. Scope

Requested scopes are a proposal from the client, not self-granted permissions. The server needs an allowlist per product/API, tenant, and approval. Internal scopes like `client.create` or `admin.write` must never be automatically granted to new clients.

### 11.4. Token Endpoint Authentication Method

Confidential clients need a server-supported authentication method such as `client_secret_basic`, `private_key_jwt`, or mTLS. Public clients cannot protect a secret; use `none` paired with PKCE per appropriate policy.

### 11.5. Metadata URIs and SSRF

Fields such as `jwks_uri`, `logo_uri`, `sector_identifier_uri`, or extension URLs can cause the server/client to make network requests. If the server fetches registrant-declared URLs, apply SSRF controls: block loopback, link-local, and disallowed private IPs, out-of-policy redirects, DNS rebinding, and unsafe schemes.

Do not fetch arbitrary URLs from registration requests just to check metadata. Use egress policies, timeouts, response size limits, and domain allowlists when fetching is necessary.

## 12. Software Statements and Initial Access Tokens

RFC 7591 allows requests to include `software_statement`, a JWT signed by a trusted issuer attesting to a set of client metadata. Initial access tokens and software statements serve different roles:

- An initial access token proves the caller is authorized to use the Registration Endpoint.
- A software statement can attest metadata such as publisher, software ID, redirect URIs, or grant policy.
- Plain JSON metadata is self-asserted data from the client.

If the same metadata field appears in both the software statement and the JSON body, RFC rules require the value from the software statement to take precedence per the protocol. The Authorization Server must still evaluate the entire request and trust relationship.

SAS 1.5.8 has extension points for custom metadata converters/providers, but you should not assume that merely enabling the Client Registration Endpoint gives you a complete trust framework/software statement policy. If your organization needs attestation, you must build issuer trust, signature validation, audience/expiry/replay checks, and dedicated metadata mapping.

## 13. Customizing Client Metadata in Spring Authorization Server

SAS has default converters that translate OIDC client registration metadata into `RegisteredClient` and back. If you want to support custom metadata such as `logo_uri`, `contacts`, or `organization_id`, customize converters/providers in a controlled manner.

Main extension points:

- `clientRegistrationRequestConverter(...)` and `clientRegistrationRequestConverters(...)`.
- `authenticationProvider(...)` and `authenticationProviders(...)`.
- `clientRegistrationResponseHandler(...)`.
- `errorResponseHandler(...)`.
- `OidcClientRegistrationAuthenticationProvider.setRegisteredClientConverter(...)`.
- `OidcClientRegistrationAuthenticationProvider.setClientRegistrationConverter(...)`.
- `OidcClientConfigurationAuthenticationProvider.setClientRegistrationConverter(...)`.

Illustrative direction:

```java
Consumer<List<AuthenticationProvider>> customizeRegistrationProviders =
        providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registration) {
                registration.setAuthenticationValidator(
                        OidcClientRegistrationAuthenticationValidator
                                .DEFAULT_REDIRECT_URI_VALIDATOR
                );
            }
        });
```

This is a skeleton. In production, compose the necessary default validators such as redirect URI, post-logout redirect URI, JWK Set URI, and a scope validator; never replace default validators with a weaker validator just to let requests pass.

### 13.1. Persist Only Allowlisted Metadata

For example, if only `logo_uri` and `contacts` are supported:

1. Declare both fields as supported metadata.
2. Validate types, lengths, and URL/contact formats.
3. Store them in `ClientSettings` or a dedicated storage domain.
4. During Client Read, serialize back exactly those two fields.
5. Ignore or reject unsupported metadata per policy.

Do not dump arbitrary JSON into settings and return it to other callers. Doing so can turn registrations into uncontrolled data storage or leak internal metadata.

### 13.2. Converters Are Not the Only Place to Check Permissions

Converters are responsible for representation translation. The authentication provider/policy layer must verify the registrar token, registration scope, metadata validation, and approval. Do not bury all authorization logic inside a converter where it might be bypassed when Client Read uses a different converter.

## 14. Registration Response and Secure Credential Storage

After creating a client, the server may return `client_id`, `client_secret` (if the client uses a secret), `registration_access_token`, and `registration_client_uri`.

The client onboarding system must:

- Store `client_secret` in a secret manager; avoid re-displaying it after saving unless required.
- Store `registration_access_token` separately from the client secret.
- Restrict which people/automations can read the registration token.
- Record owner, tenant, environment, approval ID, and issuance timestamp.
- Never log response bodies containing credentials.
- Have procedures to rotate/revoke credentials based on endpoint capabilities and admin workflows.

### 14.1. Do Not Return Secrets on Client Read Without Reason

Some registration responses may include sensitive metadata per contract. The system must define which fields are returned at creation time vs. read time. Client Read is not a reason to re-log or redistribute client secrets. If an implementation returns credential fields per spec, only callers with a valid registration access token may read them.

### 14.2. Handling Lost Responses

If a registration POST times out, it is uncertain whether the server created the client. The initial access token may already have been consumed. Do not blindly retry multiple times with new tokens, as that could create duplicate registrations.

Recovery workflow:

1. Record a correlation/request ID before calling.
2. Check audit logs or the registration store using approved reconciliation data.
3. Determine whether the client was created.
4. If created, retrieve details via a secure administrative workflow; do not try to read using the already-used initial token.
5. If not created, request a new initial token per approval.

If idempotency is required, design an idempotency key and persistence in the onboarding service; do not assume RFC 7591 or SAS automatically guarantees idempotency across retries.

## 15. Rate Limiting, Auditing, and Abuse Prevention

Protected registration still needs abuse controls:

| Control | Purpose |
| --- | --- |
| Rate limit per registrar/tenant/IP | Curb bulk client creation |
| Registration count quota | Limit clients per partner/product |
| Approval workflow | Block out-of-scope metadata or permissions |
| Immutable audit log | Trace who created a client, when, and with what authority |
| Credential rotation | Limit blast radius if registrar secrets/tokens leak |
| Anomaly alerts | Detect spikes in errors, unusual redirect URIs, or abnormal grants/scopes |
| Egress restrictions | Mitigate SSRF when handling metadata URIs |
| Transactional/one-time token state | Prevent replaying initial access tokens across nodes |

Audit events should record registrar identity, registration ID, owner/tenant, approved grants/scopes, normalized redirect URIs, approval reference, and outcome. Never log raw initial access tokens, client secrets, or registration access tokens.

### 15.1. Revoking Registrar Credentials

When a registrar is compromised:

1. Disable the registrar client or revoke its credentials.
2. Revoke/invalidate unused initial access tokens.
3. Investigate registrations created during the suspected window.
4. Disable newly created clients with suspicious metadata/permissions.
5. Rotate the registrar secret/private key and review issued tokens.
6. Inspect audit logs and notify relevant resource owners per incident policy.

### 15.2. Revoking Registration Access

A registration access token can be exposed independently from a client secret. Have a way to disable the registration or revoke the token according to server capabilities and admin workflows. If the SAS endpoint does not provide update/delete operations and the system requires them, use controlled server-side administration or build a suitable extension; never call an unsupported method.

## 16. Multi-Instance Setup and One-Time Token Atomicity

In multi-instance production, a single initial access token must never be accepted concurrently on two nodes.

Risk:

1. Request A reaches node 1 and request B reaches node 2 nearly simultaneously.
2. Both nodes read the token as active before the invalidated state is written.
3. Both may create registrations if storage/updates lack atomicity.

Mitigations:

- Use `OAuth2AuthorizationService` backed by shared storage.
- Ensure transactions/locking or conditional updates for one-time use.
- Do not rely on an in-memory authorization store in a multi-node environment.
- Test two concurrent requests using the same initial token.
- Verify retries/load balancers do not unintentionally replay requests.
- Synchronize clocks and token state across instances.

One-time token enforcement is a security property that must be verified across the entire deployment, not just on a single local JVM.

## 17. End-to-End Illustrative Requests and Responses

### 17.1. Obtaining an Initial Token

```bash
curl --request POST "https://login.example.com/oauth2/token" \
  --user "$REGISTRAR_CLIENT_ID:$REGISTRAR_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=client.create"
```

Keep the access token in a secret store or in memory of the onboarding service. Never echo tokens to terminal logs in production.

### 17.2. Creating a Client

```bash
curl --request POST "https://login.example.com/connect/register" \
  --header "Authorization: Bearer $INITIAL_ACCESS_TOKEN" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json" \
  --data '{
    "client_name": "orders-web",
    "application_type": "web",
    "redirect_uris": [
      "https://orders.example.com/login/oauth2/code/company"
    ],
    "grant_types": [
      "authorization_code",
      "refresh_token"
    ],
    "response_types": ["code"],
    "scope": "openid profile orders.read",
    "token_endpoint_auth_method": "client_secret_basic"
  }'
```

### 17.3. Reading the Registration

```bash
curl --request GET "$REGISTRATION_CLIENT_URI" \
  --header "Authorization: Bearer $REGISTRATION_ACCESS_TOKEN" \
  --header "Accept: application/json"
```

The shell variables above are placeholders. The actual registration path must come from `registration_client_uri` in the response rather than concatenating a client ID manually if the server returns a different URI format.

## 18. Protected Registration Test Matrix

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| DCR disabled by default | `clientRegistrationEndpoint` not enabled | Registration endpoint does not operate as DCR |
| Endpoint enabled | OIDC Client Registration + `JwtDecoder` configured | Endpoint accepts requests per contract |
| Missing Bearer token | POST registration without Authorization header | Rejected |
| Invalid token | Bearer token with bad signature/expired | Rejected |
| Token missing `client.create` | Access token lacks this scope | Rejected |
| Token with extra scopes | `client.create orders.read` | Rejected per SAS 1.5.8 rule |
| Token with `client.create` only | Initial token with exact scope | Registration request proceeds to validation |
| Reused token | Resend consumed initial token | Rejected |
| Unauthorized registrar | Client not granted `client.create` scope | Cannot register |
| Client Read missing token | GET registration URI without Bearer | Rejected |
| Client Read missing `client.read` | Bearer token lacks sufficient scope | Rejected |
| Client Read valid token | Registration access token for matching client | Returns allowed registration metadata |
| Client A's token reading Client B | Registration B URI with Token A | Rejected |
| Invalid Redirect URI | Unapproved URI | Registration rejected |
| Unsupported grant | Request asks for unsupported grant | Rejected |
| Disallowed grant | Server supports grant, but client policy forbids it | Rejected |
| Overly broad scope | Request asks for admin/internal scopes | Rejected or narrowed per explicit policy |
| Public client sending secret method | Metadata incompatible with client type | Rejected |
| Unlisted custom metadata | JSON contains unknown fields | Ignored or rejected per policy |
| Internal Logo/JWKS URI | URL points to loopback/private network | Blocked by SSRF policy |
| Duplicate registration | Similar request sent multiple times | Reconciliation/idempotency policy prevents unintended duplicates |
| Timeout after commit | Server creates client but response is lost | Reconciliation instead of blind retry |
| Concurrent initial token replay | Two nodes use same token simultaneously | Only one request succeeds |
| Registrar credential revoked | Disable registrar before request | New tokens not issued; old credentials unusable per policy |
| Initial token expired | Expired before registration | Rejected |
| Registration token revoked | Client Read with revoked token | Rejected |
| Registration response secret | New client uses secret | Secret stored securely and never logged |
| Multi-tenant mismatch | Registrar submits out-of-scope tenant | Rejected |
| Approval missing | No approval record | Rejected at policy layer |
| Rate limit exceeded | Registrar exceeds quota | Throttled/rejected |
| Audit trail | Registration succeeds/fails | Required event logged without raw credentials |
| Reverse proxy | Public HTTPS, private backend | Tokens/URIs do not leak internal host; Authorization header forwarded safely |

### 18.1. Testing One-Time Tokens with Integration Tests

Pseudocode:

```java
MvcResult first = registerClient(initialAccessToken, validRequest);
assertThat(first.getResponse().getStatus()).isEqualTo(201);

MvcResult replay = registerClient(initialAccessToken, anotherValidRequest);
assertThat(replay.getResponse().getStatus()).isBetween(400, 499);
```

This is pseudocode; `registerClient(...)` is a test helper. Tests should verify registration state in the repository to ensure only one client was created, rather than relying solely on HTTP status.

### 18.2. Testing Exact Scopes

Verify at least three cases:

```java
// Token has the exact single scope
assertRegistrationAllowed(Set.of("client.create"));

// Token lacks creation permission
assertRegistrationRejected(Set.of("client.read"));

// Token contains additional scopes
assertRegistrationRejected(Set.of("client.create", "orders.read"));
```

SAS 1.5.8 specifies that the initial token must contain only the `client.create` scope. Keep this test separate from Client Read policies and the new client's business scopes.

## 19. Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Registration endpoint returns 404 | DCR not enabled or wrong path/proxy | Check `clientRegistrationEndpoint(...)`, endpoint matcher, and ingress |
| 401 on registration POST | Missing Bearer token, bad signature/expired | Check token issuer, audience, `JwtDecoder`, and Authorization header |
| 403/invalid_scope | Initial token lacks exact `client.create` | Inspect actual token scopes |
| Token has `client.create` yet still rejected | Token has extra scopes or was already used | Check all scopes and one-time state |
| Cannot obtain initial token | Registrar lacks Client Credentials or scope not registered | Inspect registrar's `RegisteredClient` |
| Client Read returns error | Wrong registration URI/token or missing `client.read` | Use the URI from the response and a token with proper permission |
| Custom metadata disappears | Default converter does not map custom fields | Configure both `RegisteredClient` converter and response converter |
| Registration returns redirect URI error | URI fails validator/policy | Check scheme, host, path, and validators |
| DCR endpoint enabled but app fails to start | Missing `JwtDecoder` bean | Register a decoder matching the key source |
| Client created twice after timeout | Blind retry or missing idempotency/reconciliation | Check audit/registration store before retrying |
| One-time token accepted on two nodes | Authorization store not shared / non-atomic update | Check persistence, transactions, and concurrency tests |
| Secrets appear in logs | HTTP body/response logging | Mask Authorization/body and disable credential logging |
| Metadata URL triggers SSRF | Missing URL/egress validation | Block private/link-local IPs, redirects, and DNS rebinding |

Investigation order: **registrar authentication → initial token claims/scopes → one-time token state → registration endpoint → metadata validation → persistence → registration response → Client Read authorization**.

## 20. Pre-Production Checklist

- [ ] DCR is enabled only when there is a clear dynamic onboarding requirement.
- [ ] Client Registration Endpoint is accessible only over HTTPS.
- [ ] An approval process exists before issuing an initial access token.
- [ ] The registrar is a separately managed confidential client/service account.
- [ ] Initial tokens contain only `client.create`, have short TTLs, and are single-use.
- [ ] Token state is durably persisted and updated atomically across instances.
- [ ] `JwtDecoder` is configured to verify Bearer tokens on the DCR endpoint.
- [ ] Registration requests are validated for redirect URIs, grants, response types, scopes, auth methods, and metadata URIs.
- [ ] `client.create`/`client.read` are granted only to required registrars/services.
- [ ] Initial access tokens, registration access tokens, and client secrets are stored separately.
- [ ] Registration responses are never logged or exposed to unauthorized parties.
- [ ] Client Read is scoped strictly to the matching registration.
- [ ] Custom metadata is allowlisted and serialized in a controlled manner.
- [ ] Rate limits, quotas, auditing, and anomaly alerts are in place.
- [ ] Procedures exist to revoke registrar credentials, initial tokens, and registration access.
- [ ] Recovery exists for request timeouts after the server has persisted the client.
- [ ] Tests cover replay, concurrent use, wrong scopes, wrong clients, and tenant mismatches.
- [ ] Do not assume SAS supports update/delete registration without verifying the version/API.

## 21. Composite Scenario: Approved Partner Onboarding

A platform allows partners to register OIDC applications to sign into a portal.

**Step 1 — Onboarding:** the partner submits organization name, technical owner, callback domain, and environment. Operators verify domain ownership, contract, and intended use.

**Step 2 — Issuing the registrar token:** the system issues a short-lived initial access token to the authenticated registrar. The token has only `client.create`.

**Step 3 — Registering the client:** the registrar sends JSON with client name, HTTPS redirect URI, Authorization Code + Refresh Token, response type `code`, approved scopes, and an appropriate authentication method.

**Step 4 — Validation:** the server validates the redirect URI against the verified domain, scopes against the product catalog, grants against the application type, and tenant policy.

**Step 5 — Issuing credentials:** the server creates `client_id`, secret if applicable, registration access token, and registration client URI. The onboarding service stores credentials in a secret manager.

**Step 6 — Client Read:** the service reads back metadata via the registration URI using a registration access token with `client.read`; it does not use the consumed initial token.

**Step 7 — Auditing and operations:** record owner, approval ID, approved metadata, creation timestamp, and registrar identity. When the partner leaves the platform, disable the client/credentials per admin policy and revoke related tokens.

This flow lets partners automate integration while keeping client creation within approved boundaries.

## 22. Summary

Protected Dynamic Client Registration uses tokens to control who can create new OAuth/OIDC clients. In Spring Authorization Server 1.5.8:

1. The OIDC Client Registration Endpoint is **disabled by default**; it must be explicitly enabled with `clientRegistrationEndpoint(...)`.
2. The endpoint is an OAuth protected resource, requiring a Bearer access token and `JwtDecoder`.
3. The initial access token used for registration must carry **only the `client.create` scope**.
4. The initial token is **single-use**; after successful registration, SAS invalidates the token.
5. `client.read` is the permission for Client Read; the registration access token and URI are returned in the registration response.
6. Registrar permissions do not automatically grant grants/scopes to the new client; metadata must still pass validation and approval.
7. Production requires credential protection, auditing, quotas, transactions, concurrency safety, and post-timeout recovery.

RFC 7591 defines dynamic registration and allows protected registration via initial access tokens. Spring Authorization Server provides an OIDC Client Registration implementation with specific scope and one-time token rules. Distinguish the general protocol from framework behavior, and test both happy paths and replay/unauthorized cases before exposing the endpoint in production.

### References

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server 1.5.8 — How-to: Register a Client Dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
