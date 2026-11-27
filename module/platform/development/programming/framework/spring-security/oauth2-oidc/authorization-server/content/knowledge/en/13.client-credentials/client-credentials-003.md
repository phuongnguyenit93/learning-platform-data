# Authenticating the client and requesting an access token

## Lesson objectives

In the **Client Credentials** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how a service performs **client authentication** with the Authorization Server and sends an **access token** request using the OAuth 2.0 Client Credentials Grant. This lesson is framed in the context of building, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**.

After this lesson, you will be able to:

- Explain the machine-to-machine (M2M) nature of `client_credentials` and how it differs from Authorization Code + PKCE.
- Register a `RegisteredClient` with the `CLIENT_CREDENTIALS` grant, authentication method, scopes, and token lifetime.
- Send an RFC 6749-compliant HTTP POST request to the Token Endpoint using `client_secret_basic` and `application/x-www-form-urlencoded`.
- Interpret `access_token`, `token_type`, `expires_in`, `scope`, and the policy of not relying on refresh tokens.
- Use Spring Security OAuth2 Client to obtain, store, and reuse tokens in a background job.
- Identify `invalid_client`, `unauthorized_client`, `invalid_scope`, and Bearer token verification errors at the Resource Server.
- Test, protect credentials, restrict scopes/audiences, and control timeouts, retries, token caching, and rotation in production.

> **Running scenario:** The `inventory-worker` service runs every five minutes, calling `https://inventory-api.example.com/inventory`. It does not log in on behalf of a user; the service authenticates itself with the Authorization Server `https://auth.example.com` and requests only the `inventory.read` scope.

## 1. What is the Client Credentials Grant?

RFC 6749 Section 4.4 defines the Client Credentials Grant: the client uses its own credentials as the basis for requesting an access token when accessing resources under the client's control or according to an authorization previously arranged with the Authorization Server.

This is a **confidential client** flow: the calling system is capable of protecting credentials (secret, private key, or corresponding certificate) in a controlled server environment. No user interacts, there is no login or consent page, and no authorization code is used.

```mermaid
sequenceDiagram
    autonumber
    participant W as Inventory Worker
    participant AS as Authorization Server
    participant RS as Inventory API / Resource Server
    W->>AS: POST /oauth2/token + client auth + grant_type=client_credentials
    AS->>AS: Verify client, credentials, grant, scope, and policy
    alt Valid
        AS-->>W: 200 access_token, token_type, expires_in, scope
        W->>RS: GET /inventory with Authorization: Bearer token
        RS->>RS: Verify issuer, audience, signature/active, expiry, scope
        RS-->>W: Data per inventory.read
    else Invalid
        AS-->>W: OAuth2 error response
    end
```

Common scenarios: scheduled workers, queue processing services, backends calling partner APIs, data sync processes, or infrastructure automation tools. **Do not use Client Credentials to impersonate a user**: if business logic requires a user's decision, choose an appropriate grant/delegation flow.

### 1.1. Comparison with Authorization Code

| Aspect | Client Credentials | Authorization Code + PKCE |
|---|---|---|
| Who initiates? | Service/backend holding credentials. | Client initiates and browser interacts with the user. |
| User logs in? | No. | Yes in the standard flow. |
| Goes through Authorization Endpoint? | Not needed. | Yes. |
| Redirect URI/state/PKCE? | Not applicable to this grant. | Yes per security requirements. |
| User consent? | None. | May be required. |
| Client authentication? | **Mandatory**, using a mechanism supported by the AS. | Confidential clients must authenticate; public clients have their own mechanisms. |
| What does the token represent? | Permissions of the client/service. | Permissions tied to an authorization involving a user. |
| Refresh token? | RFC 6749 Section 4.4.3 recommends **SHOULD NOT** be issued. | May be issued depending on policy. |

`client_credentials` is not an OIDC user authentication flow and **does not issue an ID Token under the standard OAuth2 grant**. Do not put `openid`, `nonce`, `response_type=code`, `redirect_uri`, or `code_verifier` into the request to turn it into a login.

## 2. Roles and prerequisites

| Component | Responsibility | Example |
|---|---|---|
| Confidential Client | Holds credentials, sends token requests, protects and uses the access token. | `inventory-worker` |
| Authorization Server | Authenticates clients, validates grants/scopes, issues tokens, manages keys and metadata. | `auth.example.com` |
| `RegisteredClientRepository` | Stores client ID, authentication method, grant, scope, and token policy. | `inventory-worker` with `inventory.read` |
| Token Endpoint | Processes POST requests per OAuth2 `client_credentials`. | `/oauth2/token` |
| Resource Server | Verifies tokens and enforces API authorization. | `inventory-api.example.com` |

A valid flow requires the following to align:

1. Client ID is registered; only **one** client authentication method is accepted per request.
2. Client has the `AuthorizationGrantType.CLIENT_CREDENTIALS` grant and valid credentials.
3. Token Endpoint matches host, path, HTTPS, and content type.
4. Requested scope is registered and permitted by policy. Audience is properly issued for the target API.
5. Authorization Server is able to issue access tokens, e.g., configured with signing keys/JWKS for JWTs or storage/introspection for opaque tokens.
6. Resource Server trusts the issuer, verifies the token, and enforces permissions.

**A Client ID is not by itself a secret credential.** Someone who knows `client_id` must never receive a token without providing a valid authentication method. Do not allow a public client with `ClientAuthenticationMethod.NONE` to use Client Credentials just because it has a client ID.

## 3. Configuring `RegisteredClient` in Spring Authorization Server

Spring Authorization Server represents clients with `RegisteredClient`, stored via `RegisteredClientRepository`. For M2M, declare `CLIENT_CREDENTIALS` along with the specific auth method and scopes.

### 3.1. Example registering a client with HTTP Basic

```java
package com.example.authserver.config;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

@Configuration(proxyBeanMethods = false)
class InventoryClientRegistrationConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder,
            @Value("${INVENTORY_WORKER_SECRET}") String rawSecret) {

        RegisteredClient inventoryWorker = RegisteredClient
                .withId("inventory-worker-v1")
                .clientId("inventory-worker")
                .clientName("Inventory Worker")
                .clientSecret(passwordEncoder.encode(rawSecret))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("inventory.read")
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(inventoryWorker);
    }
}
```

This snippet **only illustrates registering a single client**. A complete application needs a SecurityFilterChain for the Authorization Server, issuer, token generator/signing keys, appropriate repository and persistence, plus bean/framework dependencies. `INVENTORY_WORKER_SECRET` must come from an external secret source outside source code and be generated with sufficiently high entropy.

| Setting | Purpose |
|---|---|
| `withId("inventory-worker-v1")` | Internal registration ID; stable when backed by a DB. |
| `clientId("inventory-worker")` | Value the client sends to the Token Endpoint. |
| `clientSecret(passwordEncoder.encode(...))` | Stores the hashed secret to verify incoming credentials. |
| `CLIENT_SECRET_BASIC` | Allows client authentication via HTTP Basic. |
| `CLIENT_CREDENTIALS` | Grants permission to use the M2M grant. |
| `scope("inventory.read")` | Restricts the permissions that can be requested. |
| `accessTokenTimeToLive(5 minutes)` | Limits access token lifetime to reduce impact if leaked. |

**Do not add `redirectUri(...)`, `requireProofKey(true)`, or `requireAuthorizationConsent(true)` thinking it makes this grant "safer":** there is no browser, authorization code, or user consent in Client Credentials. Security must focus on client authentication, scope/audience, token lifecycle, TLS, and the Resource Server.

`InMemoryRegisteredClientRepository` is suitable for demos/testing, not as a production client store. Use `JdbcRegisteredClientRepository` or a durable persistence implementation with controlled migrations, client ownership, approvals, rotation, access control, and backups. With multiple replicas, all instances must see the same registrations and token policies.

### 3.2. Registering multiple scopes while requesting fewer permissions

A client registered with:

```java
.scope("inventory.read")
.scope("inventory.write")
```

Can request only `inventory.read` for a read task. The Authorization Server must reject requests exceeding the allowed scope or apply a scope-reduction policy; the Resource Server continues to enforce per-API permissions. Avoid registering broad scopes just to "save configuration effort".

Do not share one client secret across multiple services. Per-workload credentials enable auditing, rotation, revocation, and blast-radius containment if one system is compromised.

## 4. Sending the HTTP POST token request

Per RFC 6749 Section 4.4.2, a Client Credentials Token Request requires:

- HTTP **POST** to the Token Endpoint.
- Body encoded as `application/x-www-form-urlencoded` in UTF-8.
- `grant_type=client_credentials` **required**.
- `scope` **optional**; default permissions when omitted depend on server policy—never assume all scopes are granted.
- Client authentication required, e.g., `client_secret_basic`, `private_key_jwt`, or mTLS per registration.

### 4.1. Raw request with Basic

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic [BASE64_ENCODED_CREDENTIALS]
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=inventory.read
```

`[BASE64_ENCODED_CREDENTIALS]` is only a placeholder. Per RFC 6749 Section 2.3.1, the client ID and secret must be form-URL-encoded per OAuth2 rules before joining them for the Basic string; using an OAuth2 client SDK avoids mistakes with special characters. **Basic Base64 is not secret encryption**: proper HTTPS/TLS with certificate validation is required, and never log the `Authorization` header.

When using HTTP Basic, do not simultaneously send `client_secret` in the form body; using two client authentication methods in the same request is an invalid request.

### 4.2. Testing more safely with cURL

The Bash example below lets cURL **prompt interactively for the password**; never write secrets directly in the command:

```bash
export M2M_CLIENT_ID="inventory-worker"
export M2M_TOKEN_URI="https://auth.example.com/oauth2/token"

curl --request POST \
  --url "$M2M_TOKEN_URI" \
  --user "$M2M_CLIENT_ID" \
  --header "Accept: application/json" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=inventory.read"
```

On PowerShell/Windows, use `curl.exe` (PowerShell 5.1 often aliases `curl`):

```powershell
$env:M2M_CLIENT_ID = "inventory-worker"
$env:M2M_TOKEN_URI = "https://auth.example.com/oauth2/token"
curl.exe --request POST --url "$env:M2M_TOKEN_URI" --user "$env:M2M_CLIENT_ID" --header "Accept: application/json" --data-urlencode "grant_type=client_credentials" --data-urlencode "scope=inventory.read"
```

Running with `--user` containing only the username normally prompts for the password at runtime. In CI, use secret injection and a secure HTTP/OAuth2 client, avoiding exposing secrets in command lines, shell history, process lists, or output logs. Never use `--insecure` to bypass TLS certificate validation.

`--data-urlencode` ensures the body is form-urlencoded. If requesting multiple scopes, send `scope=inventory.read inventory.write` as **a single** space-delimited string, properly encoded.

### 4.3. Other authentication methods

| Method | Where is the credential? | When to use? |
|---|---|---|
| `client_secret_basic` | HTTP Basic `Authorization` header. | M2M with a shared secret, TLS, and strong secret protection. |
| `client_secret_post` | Form body `client_id` + `client_secret`. | Only when the client is registered for this method; body-logging risks must be controlled. |
| `private_key_jwt` | JWT client assertion signed by the client. | When you want key pairs and stronger rotation/identity governance than shared secrets. |
| `client_secret_jwt` | JWT assertion verified with a shared secret. | When explicitly supported and governed by a JWT assertion policy. |
| `tls_client_auth` / `self_signed_tls_client_auth` | mTLS client certificate. | Environments with PKI and TLS mutual authentication infrastructure. |
| `none` | No confidential credential. | Public clients in appropriate grants; **never use to bypass authentication for Client Credentials**. |

JWT assertions must have their signature, audience, expiration, issuer/subject, and replay protection checked where applicable. When mTLS terminates at a proxy, certificate metadata must be bound to a **trusted proxy**—never accept self-asserted certificate headers from the Internet.

There is no `redirect_uri`, `code`, `state`, `code_verifier`, `nonce`, or `/oauth2/authorize` step in the standard grant. If a `resource` parameter per RFC 8707 is included, it only takes effect when the Authorization Server **actually implements the extension** and enforces the corresponding resource indicator/audience.

## 5. Access token response and token lifecycle

When the client is valid and the grant and scope are accepted, the Token Endpoint issues an access token:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
```

| Field | Meaning | How to use |
|---|---|---|
| `access_token` | Temporary credential used to call APIs. | Keep confidential; do not log or expose to UI. |
| `token_type` | Typically `Bearer` in common designs. | Send `Authorization: Bearer token` to the Resource Server. |
| `expires_in` | Seconds until expiration; 300 seconds in the example. | Proactively request a new token with a safety buffer before expiration. |
| `scope` | Final granted scope, when present in the response. | Do not assume the server granted every requested scope. |
| `refresh_token` | RFC 6749 Section 4.4.3 states **SHOULD NOT** be issued for client_credentials. | Do not design the worker to depend on a refresh token. |

When an access token expires under Client Credentials, the client **sends a new Client Credentials request**, re-authenticating with valid credentials. This differs from the refresh token grant. Best practice is to reuse valid tokens and re-acquire as needed, avoiding calling the Token Endpoint on every single API call.

### 5.1. The token represents the client, not a user

`inventory-worker` authenticates as an application/service. If the token is a JWT with `sub`, how the principal is represented depends on the token profile and issuer configuration; in many systems it is the client ID. **Do not infer that this `sub` is a logged-in user.**

The Resource Server must distinguish machine principals from human principals when business logic requires it. A "view current user's personal profile" API must never let an M2M token claim an arbitrary user to gain access.

### 5.2. Scope differs from audience

- Scope `inventory.read` describes the permitted action.
- Audience `inventory-api` or API URI describes the **intended recipient of the token**.
- Issuer `https://auth.example.com` describes the trusted token issuer.

An access token with a valid signature and scope but **wrong `aud`** must still be rejected by the target API when applying the JWT access token profile. The Resource Server uses `issuer-uri` to discover metadata/JWKS and verify the issuer, yet you must configure **audience** validation for your API; do not assume setting `issuer-uri` alone is enough.

Spring Authorization Server can customize claims via token customizers and appropriate extensions. Passing `resource` in a token request or setting a custom property **does not guarantee** the framework automatically produces the right audience without a corresponding implementation/verification policy.

### 5.3. JWT or opaque token?

| Format | Verification at the Resource Server | Notes |
|---|---|---|
| Self-contained JWT | Signature/public JWKS, `iss`, `aud`, `exp`, scope, token type, and policy. | Revocation does not automatically take effect immediately when the API verifies offline. |
| Opaque token | Introspection/status check over a trusted channel. | Requires timeouts, caching, and Authorization Server availability. |

Never consider a token "trusted" merely because the client can Base64-decode or read the JWT payload. The Resource Server must perform cryptographic and policy validation.

## 6. Sending the access token to the Resource Server

After receiving the token, the client calls the API:

```http
GET /inventory HTTP/1.1
Host: inventory-api.example.com
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

The Resource Server must verify:

1. JWT/JWKS signature or introspection and trusted issuer origin.
2. Expiration `exp`, `nbf` if present, token type, and revocation status per policy.
3. Audience matching the API.
4. Scope `inventory.read` and business permission/tenant/object checks if required.
5. Separation of machine tokens from user tokens if the API accepts both.

With Spring Security Resource Server JWT, starter configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
```

Example rule protecting GET:

```java
@Bean
SecurityFilterChain resourceServerChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/inventory/**")
                .hasAuthority("SCOPE_inventory.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));
    return http.build();
}
```

The Java snippet is abbreviated, omitting imports and `aud` validator configuration. Scopes are mapped by Spring Security to authorities prefixed with `SCOPE_` under appropriate default configurations. Do not rely on this scope rule to skip tenant checks or object-level authorization.

## 7. Configuring OAuth2 Client in the worker application

Calling the token request with cURL is great for learning the protocol, while production should use a maintained client library, especially when token caching, retries, and expiry handling are needed. Spring Security OAuth2 Client uses `ClientRegistration` (on the API-calling app) which is distinct from `RegisteredClient` (on the Authorization Server).

### 7.1. Configuration in the worker's `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-worker:
            provider: internal-as
            client-id: ${INVENTORY_WORKER_CLIENT_ID}
            client-secret: ${INVENTORY_WORKER_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          internal-as:
            token-uri: https://auth.example.com/oauth2/token
```

This configuration **lives on the OAuth2 Client/worker**, not inside Spring Authorization Server as a replacement for RegisteredClient. For a grant needing only the token endpoint, `token-uri` can be configured directly without requiring OIDC login/discovery. The host/path must match the AS's public URL, even if the Token Endpoint has been customized.

| Authorization Server | OAuth2 Client |
|---|---|
| `RegisteredClientRepository` | `ClientRegistrationRepository` |
| Defines which auth methods/grants/scopes the client may use. | Selects how to send credentials and request tokens. |
| Stores hashed secrets or public key/certificate metadata. | Holds raw credentials in a secret manager/keystore. |
| Issues access tokens. | Requests, stores, and uses access tokens. |

Do not confuse `client-secret` on the worker side with the hashed secret stored on the AS side. The worker must hold the actual credential, and the AS verifies it against the corresponding hash/key/certificate.

### 7.2. Background worker using `AuthorizedClientServiceOAuth2AuthorizedClientManager`

In a background application that does not rely on a user HTTP session, Spring Security provides a manager designed for service applications:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration(proxyBeanMethods = false)
class MachineToMachineClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

`AuthorizedClientServiceOAuth2AuthorizedClientManager` can obtain an access token using the `client_credentials` grant and renew it upon expiration via `OAuth2AuthorizedClientProvider`. It uses `OAuth2AuthorizedClientService` to store authorized client details; evaluate the lifetime/storage of this service in multi-replica deployments.

### 7.3. Example service calling an API

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryApiClient {
    private final OAuth2AuthorizedClientManager manager;
    private final RestClient restClient = RestClient.create();

    InventoryApiClient(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String fetchInventory() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-worker")
                .principal("inventory-worker-process")
                .build();

        OAuth2AuthorizedClient authorized = manager.authorize(request);
        if (authorized == null) {
            throw new IllegalStateException("Unable to obtain access token");
        }

        return restClient.get()
                .uri("https://inventory-api.example.com/inventory")
                .headers(headers -> headers.setBearerAuth(
                        authorized.getAccessToken().getTokenValue()))
                .retrieve()
                .body(String.class);
    }
}
```

The value `principal("inventory-worker-process")` is the **authorized client management key** for the system task, not a logged-in user. The example uses `RestClient.create()` for brevity; production should configure a RestClient Bean to manage timeouts, TLS, metrics, and URL policies.

Some Spring Security versions provide `OAuth2ClientHttpRequestInterceptor` for `RestClient` to automatically acquire and attach Bearer tokens. You can use it once the app manages `ClientRegistration` and `OAuth2AuthorizedClientManager` properly, avoiding hand-written OAuth logic.

### 7.4. Token reuse policy

Clients must balance reducing Token Endpoint load against avoiding mid-request token expiration:

- Reuse unexpired tokens and request a new one when nearing expiration, with a buffer for clock skew.
- Do not attempt a `refresh_token` refresh when this grant does not issue refresh tokens.
- Stop infinite retry loops when receiving `invalid_client` (usually requires fixing credentials/config).
- Apply jittered backoff on transient AS failures; prevent multiple threads or replicas from causing a "token storm".
- Partition caches by client registration, principal, scope, and actual deployed audience.
- Never log tokens, and never use a token meant for API A to call API B if the audience does not match.

## 8. Classifying Token Endpoint and Resource Server errors

| Error | Nature | How to investigate |
|---|---|---|
| `invalid_client` | Client authentication failed: wrong secret, unknown client, wrong method. | Check registration, secret injection, client authentication method, TLS. |
| `unauthorized_client` | Client authenticated validly but is not allowed `client_credentials`. | Check `authorizationGrantType` on the RegisteredClient. |
| `invalid_scope` | Requested permissions outside allowed scope/policy. | Compare requested scope with registered scopes. |
| `invalid_request` | Missing/invalid body field, duplicate parameters, or multiple auth mechanisms. | Verify POST form-urlencoded, grant_type, auth method. |
| `unsupported_grant_type` | AS does not support the submitted grant. | Check server implementation/metadata and request. |
| HTTP 404 at Token Endpoint | Wrong path, context path, or gateway rewrite. | Verify public endpoint URL/discovery. |
| HTTP 405 | Disallowed HTTP method used. | Use POST with the proper content type. |
| HTTP 401 from Resource Server | Expired token, bad signature/issuer/audience, or missing token. | Check Bearer validation at the API; distinguish from client auth at AS. |
| HTTP 403 from Resource Server | Valid token but lacks scope/permissions. | Inspect token scopes and API policies; do not broaden privileges blindly. |

With `client_secret_basic`, when the client attempts authentication via the HTTP Authorization header and fails, RFC 6749 Section 5.2 requires **HTTP 401** and an appropriate `WWW-Authenticate` header. Example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="oauth2-client"
Content-Type: application/json

{"error":"invalid_client"}
```

Never return public messages like "client ID X exists, secret expired" as that aids registry enumeration. Detailed technical diagnostics belong in restricted-access audit logs, free of raw secrets/tokens.

### 8.1. Separating token issuance errors from token usage errors

If the AS returned HTTP 200 yet the Resource Server returns 403, it is usually an API authorization issue (scope/role/tenant), not `invalid_client`. If the Resource Server returns 401, check the token header, expiry, issuer, audience, and JWKS/introspection before concluding that the secret needs rotation.

## 9. Testing Client Credentials

### 9.1. Test matrix

| Request | Expected result |
|---|---|
| Valid client, secret, grant, scope | 200, access token, token type, and appropriate expiry. |
| Missing/wrong Basic secret | `invalid_client`; no token issued. |
| Non-existent client ID | `invalid_client`; does not leak registry state. |
| Valid client without `client_credentials` grant registered | `unauthorized_client` or standard corresponding error; no token issued. |
| Scope outside registration | `invalid_scope` or rejected per policy; no extra permissions granted. |
| Missing `grant_type` | `invalid_request`. |
| Sending GET or JSON | Token Endpoint does not process it as a valid form POST. |
| Both Basic and form `client_secret` in same request | Request rejected per specification. |
| Public client `none` attempting `client_credentials` | No token issued based solely on `client_id`. |
| Using read-only token on an endpoint requiring write | 403/authorization denied. |
| Wrong JWT signature, issuer, audience, or expiry | API rejects the token. |
| Rotate client secret | New tokens require valid secret; old tokens follow their own validity policy. |
| Restart/rolling deploy across multiple replicas | Registration/keys/token policies remain consistent. |
| Client sending token requests too frequently | Rate limiting/backoff engages without causing DoS. |

### 9.2. MockMvc example testing wrong secret

```java
@SpringBootTest
@AutoConfigureMockMvc
class ClientCredentialsTokenEndpointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidBasicSecretDoesNotReceiveToken() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("inventory-worker", "wrong-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "inventory.read"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"));
    }
}
```

This test assumes a Spring Authorization Server context, valid client fixture, JUnit/MockMvc imports, and configured dependencies. Valid-path testing must use a real test secret to obtain a token, verify claims/expiry, call the Resource Server, and inspect the response; a MockMvc test for a wrong secret alone does not prove the entire flow works.

### 9.3. Assertions needed on the happy path

- `access_token`, `token_type=Bearer`, `expires_in`, and actual scopes match expectations.
- No dependency on a refresh token; under normal policy, `refresh_token` is absent.
- JWT/opaque token carries the right issuer, audience, and machine principal.
- `SCOPE_inventory.read` permits GET and denies `inventory.write` endpoints.
- A token meant solely for the inventory API cannot be used against the billing API.
- Logs, traces, and HTTP dumps contain no Basic secrets, JWT assertions, or raw tokens.
- Unexpired tokens continue to verify cleanly across valid rolling deploys/key rotations.
- When credentials fail or the signer/KMS is unavailable, the server never issues fake tokens or falls back to weak secrets.

## 10. Security and production operations

### 10.1. Credential management

Client secrets/private keys/certificates must be provisioned per workload and environment, stored in a secret manager/KMS/keystore or controlled infrastructure. Never commit secrets, bake them into images, paste them into support tickets, or put them in request query strings. Rotation needs auditing, owners, expiration dates, and incident playbooks for compromise.

HTTP Basic uses Base64 and provides no intrinsic confidentiality; TLS with hostname/certificate verification is mandatory. For stronger requirements, evaluate `private_key_jwt` or mTLS when supported end-to-end across AS, client, gateway, and Resource Server.

### 10.2. Limiting token risk

- Short TTLs and least-privilege scopes.
- API-specific audience; Resource Server validates `aud`.
- Protect tokens in cache/memory; never expose them to browsers or unrelated services.
- Where required, evaluate sender-constrained access tokens via mTLS or DPoP.
- Offline-verified JWTs may remain valid until `exp` even after a client secret is revoked. Combine TTLs, introspection, denylists, or additional session/token controls if immediate revocation is required.
- Coordinate key rotation/JWKS with overlap windows for unexpired tokens.

### 10.3. Observability and load shedding

Monitor: `client_credentials` request rates, success/`invalid_client` ratios, Token Endpoint latency, DB/KMS errors, token counts by client category, rate limits, and token cache hit rates. Never log secrets/access tokens; use request IDs and reason categories in restricted-access audit systems.

Rate limiting must account for NAT, multiple replicas, and the risk of an attacker using another client's ID to throttle them. Never let a rate limiter return distinguishable responses that allow client enumeration.

### 10.4. Impact of policy changes

| Action | New token requests | Already-issued tokens |
|---|---|---|
| Rotate secret | Old secret becomes invalid once change takes effect. | Access tokens may remain valid until expiration. |
| Remove `client_credentials` | No new tokens issued with that grant. | Does not automatically revoke all issued JWTs. |
| Reduce scopes for client | New grants must follow the updated scope/policy. | Old tokens may still carry old permission claims until invalidated. |
| Rotate signing key | New tokens signed with new key per policy. | Retain old public key during the necessary overlap window. |
| Change issuer/audience | Clients and APIs must update trust configuration together. | Requires coordinated migration—never disable issuer/audience validators. |

## 11. Common misconceptions

| Misconception | Reality |
|---|---|
| "`client_id` is equivalent to a user ID." | Client Credentials represents the service's identity, not a human user. |
| "M2M must go through `/oauth2/authorize` and consent." | This grant authenticates directly at the Token Endpoint. |
| "Adding `openid` will return an ID Token." | It is not a standard OIDC user authentication flow. |
| "No secret is needed because the API is inside a VPN." | Confidential clients must still authenticate per grant and trust policies. |
| "Client Credentials always receives a refresh token." | RFC 6749 recommends not issuing a refresh token. |
| "Any API will accept a token with the right scope." | Audience, issuer, and other permissions must also be verified. |
| "Base64 Basic is secure encryption." | Base64 is trivially decoded; TLS and log protection are required. |
| "Rotating the secret immediately invalidates old tokens." | Issued access tokens have their own lifetime and revocation policies. |
| "Request a new token for every API call." | Reuse unexpired tokens, manage caching, and apply backoff. |
| "Setting `issuer-uri` is enough to check audience." | Resource Servers must define and enforce audience validators by design. |

## 12. Hands-on exercise

**Context:** `report-worker` runs every 10 minutes and needs to read `https://reports-api.example.com` using a token from AS `https://auth.example.com`. The service does not represent a user and only has the `reports.read` scope.

Tasks:

1. Register `report-worker` as a confidential client with `CLIENT_SECRET_BASIC`, `CLIENT_CREDENTIALS`, scope `reports.read`, and a token TTL of about five minutes.
2. Put the credential in a secret manager/test environment variable and store its hash on the AS.
3. Send a form-urlencoded POST token request via cURL and inspect the response.
4. Test missing credentials, wrong secret, wrong grant, and unregistered scope `reports.write`; record the OAuth errors.
5. Configure the worker's `ClientRegistration` and `AuthorizedClientServiceOAuth2AuthorizedClientManager` with the `clientCredentials()` provider.
6. Call the reports API with the Bearer token, verifying issuer, audience, scope, and permissions.
7. Add an endpoint requiring `reports.write` and verify the read-only token is rejected.
8. Test a token with the wrong audience or an expired token, verifying the corresponding HTTP 401.
9. Rotate the client secret in staging and test new token acquisition; observe behavior of already-issued tokens.
10. Audit logs, traces, CI output, and API docs to ensure no secrets or tokens leak.

**Completion criteria:** the worker autonomously obtains an access token with the Client Credentials grant and calls the API with the right permissions; invalid requests are rejected; no user login, consent, or refresh token is required.

## 13. Pre-deployment checklist

- [ ] Confidential client is registered with the right ID, owner, auth method, and `client_credentials` grant.
- [ ] Scopes and audience are restricted to the required service/Resource Server.
- [ ] Token Endpoint uses the right URL and HTTPS; requests use form-urlencoded POST.
- [ ] Client authentication works properly and cannot be bypassed by public clients.
- [ ] Secrets/private keys/certificates are protected and have rotation policies.
- [ ] No redirect URI, state, code, PKCE, or login/consent is introduced into this grant.
- [ ] Token responses contain access token, token type, and expiry; clients do not rely on refresh tokens.
- [ ] Resource Server checks signature/introspection, issuer, audience, expiration, scope, and business permissions.
- [ ] Client reuses unexpired tokens with buffer, backoff, and bounded retries.
- [ ] Tested success, `invalid_client`, `unauthorized_client`, `invalid_scope`, and invalid method/body requests.
- [ ] Tested wrong audience, expired tokens, wrong scope, rollback, and credential rotation.
- [ ] No Basic headers, raw tokens, client secrets, JWT assertions, or private keys appear in logs.
- [ ] Rate limits, auditing, monitoring, HA, and token-issuance incident runbooks are in place.

## Summary

The Client Credentials Grant is a **machine-to-machine** OAuth 2.0 flow: a confidential client authenticates directly at the **Token Endpoint**, sends `grant_type=client_credentials` with appropriate scopes, and receives an **access token**. There is no Authorization Code, browser, PKCE, or user consent. RFC 6749 recommends not issuing refresh tokens for this grant.

With Spring Authorization Server, `RegisteredClient` defines the credential method, grant, and scopes; with Spring Security OAuth2 Client, `OAuth2AuthorizedClientManager` helps workers acquire and reuse tokens. Safe production operation requires TLS, least privilege, explicit audience enforcement, appropriate TTLs, secret rotation, Resource Server validation, and testing both valid and invalid requests.

## References

1. [RFC 6749, Section 4.4 — Client Credentials Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): client authentication, token request, scope, and refresh tokens.
2. [RFC 6749, Section 5.2 — Token Error Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): `invalid_client`, `unauthorized_client`, and OAuth2 error codes.
3. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `RegisteredClientRepository`, `TokenSettings`.
4. [Spring Authorization Server — Dynamic Client Registration](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): Client Credentials registration/request example.
5. [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `AuthorizedClientServiceOAuth2AuthorizedClientManager` for service apps.
6. [Spring Security — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): RestClient/WebClient and token management.
7. [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWKS/token validation.
8. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`.
9. [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707): declaring the target Resource Server when supported by extensions.
10. [RFC 9068 — JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068): `iss`, `aud`, and verifying access tokens.
