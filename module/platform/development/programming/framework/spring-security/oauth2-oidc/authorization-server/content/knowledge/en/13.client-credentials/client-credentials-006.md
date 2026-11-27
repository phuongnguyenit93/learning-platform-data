# Setting TTL, client-side token caching, and credential rotation policy

## 1. Context: three distinct lifecycles in the Client Credentials Grant

In an OAuth 2.0/OpenID Connect Authorization Server system built with **Spring Security**, **Spring Authorization Server**, and Spring Boot, many backend services need to call internal APIs **without an end user logged in**.

For example: `billing-service` must call `inventory-api` to read inventory. With the **Client Credentials Grant**, `billing-service` authenticates itself at the Token Endpoint, receives an access token, and sends that token when calling the Resource Server. If the service requests a new token for every single API request, load on the Authorization Server increases unnecessarily. If it uses an expired token, the API rejects it. If a client secret is rotated abruptly, the application may keep running fine with a cached token and then fail on the next token acquisition.

Three concerns must be separated:

1. **Access token TTL:** How long is the token issued by the Authorization Server valid?
2. **Client-side token cache:** When does the application hold, reuse, and replace an access token?
3. **Credential rotation:** How does the client rotate secrets, private keys, or authentication certificates without downtime or leaking secrets?

**Do not equate access token lifetime with client credential lifetime.** A secret can be used to request many tokens over a period; conversely, already-issued tokens may remain usable after the secret is changed, depending on revocation policies and Resource Server mechanisms.

### Learning objectives

After this lesson, you will be able to:

- Configure `TokenSettings.accessTokenTimeToLive` per `RegisteredClient`.
- Explain why Client Credentials normally has no refresh token, ID token, user session, or consent.
- Configure Spring Security OAuth2 Client using `AuthorizedClientServiceOAuth2AuthorizedClientManager` to obtain and cache access tokens in backend tasks.
- Design early-expiration thresholds, cache keys, concurrent request handling, and multi-instance execution.
- Build rotation policies for `client_secret_basic`, `private_key_jwt`, and mTLS.
- Test TTL, cache hit/miss, token acquisition failure, 401/403, and rotation.
- Monitor token issuance and credential lifecycles without logging tokens or secrets.

## 2. Client Credentials flow in Spring architecture

```mermaid
sequenceDiagram
    participant C as billing-service / OAuth Client
    participant AS as Spring Authorization Server
    participant RS as inventory-api / Resource Server

    C->>C: Look up access token cache
    alt No token with sufficient remaining lifetime
        C->>AS: POST /oauth2/token + client authentication
        AS->>AS: Verify client, grant, scope, credentials
        AS-->>C: access_token, token_type, expires_in
        C->>C: Store token and expiresAt
    end
    C->>RS: GET /inventory + Bearer access token
    RS->>RS: Verify token, audience, scope, policy
    RS-->>C: Return data
    C->>C: Subsequent requests reuse valid token
    Note over C,AS: When token nears expiration
    C->>AS: POST /oauth2/token using client_credentials
    AS-->>C: New access token
```

Components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `RegisteredClientRepository` at AS | Stores client ID, authentication method, grant, scope, and token settings |
| Token Endpoint at AS | Authenticates client, validates `client_credentials`, and issues tokens |
| `OAuth2AuthorizationService` at AS | Manages authorization/token state per configuration |
| `ClientRegistrationRepository` at client | Holds configuration for calling the Token Endpoint |
| `OAuth2AuthorizedClientService` at client | Stores/retrieves authorized clients containing access tokens |
| `OAuth2AuthorizedClientManager` at client | Coordinates using a valid cached token or requesting a new one |
| Resource Server | Validates access tokens and enforces API permissions |

**The Client Credentials Grant does not require Authorization Code + PKCE**, has no user login redirect, and does not issue an ID token just because a client authenticated. Per RFC 6749 §4.4, a refresh token **SHOULD NOT** be issued for this grant. Normally the client simply re-uses the `client_credentials` grant when the old token nears expiration.

### 2.1. A client secret is not an access token

A client secret is a credential used at the **Token Endpoint** to prove the identity of a confidential client. An access token is a credential sent to a **Resource Server**. Never put `client_secret` in headers when calling `inventory-api`, and never return a client secret in an API response.

In OAuth, `client_id` is an identifier and **not a secret**. When using `client_secret_basic`, the secret portion must be protected with HTTPS and secure storage. Base64 in HTTP Basic is merely an encoding representation, **not encryption**.

## 3. TTL: who decides it, and how is it measured?

**TTL (time to live)** is the duration for which an access token is intended to remain valid. The Authorization Server determines token TTL upon issuance. A client cannot extend a JWT's `exp` simply by keeping the token in its cache longer.

| Value | Source | Meaning |
|---|---|---|
| `TokenSettings.accessTokenTimeToLive` | Registered client on AS | TTL policy for newly issued tokens |
| `expires_in` | Token response | Validity duration in seconds reported by the AS |
| `iat`, `exp` | JWT access token if JWT is used | Issuance/expiration timestamps as claims |
| `OAuth2AccessToken.expiresAt` | Token model in Spring Security OAuth2 Client | Timestamp the token manager checks to evaluate validity |
| **Safety margin / clock skew** | Client/RS policy | Early refresh buffer guarding against network latency and clock drift |
| **Client credential validity** | Secret store/PKI/AS policy | Period a secret/key is allowed to authenticate the client, independent of token TTL |

For instance, if the AS issues a token with `expires_in=600`, do not hold onto the token until the final second before sending an API request. The token could expire between when the request leaves the client and when the Resource Server checks it.

### 3.1. Balancing TTL against security and system load

| Illustrative TTL | Benefits | Trade-offs |
|---|---|---|
| 2–5 minutes | Shrinks the window to abuse a leaked token | Token Endpoint receives more token requests |
| 10–15 minutes | Moderate balance between load and token validity | Needs revocation handling if immediate termination is required |
| 30 minutes or more | Reduces token acquisition frequency | Old JWTs/claims can remain valid longer |

These ranges are **purely for analysis**, not Spring Authorization Server defaults or mandatory recommendations. Measure actual performance, resource sensitivity, and revocation requirements.

With self-verifying JWTs, the Resource Server may continue accepting old tokens until `exp` unless an additional revocation-status check exists. Short TTLs help bound this window but do not replace revocation capability when needed.

## 4. Configuring TTL in Spring Authorization Server

Each `RegisteredClient` has its own `TokenSettings`. Example confidential client `billing-service` allowed only Client Credentials with the `inventory.read` scope:

```java
RegisteredClient billingClient = RegisteredClient
    .withId("billing-service-internal-id")
    .clientId("billing-service")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("inventory.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .build())
    .build();
```

This example constructs a **registered client model**. A real application still requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer, JWK/signing keys, `SecurityFilterChain`, and other Spring Authorization Server components matching your project version.

Key points:

1. `clientSecret` is loaded from a **secret manager** or secure config channel, never hardcoded in source.
2. `CLIENT_SECRET_BASIC` is the client authentication method; the Token Endpoint must verify the credential.
3. `CLIENT_CREDENTIALS` does not grant permission to use other grants like Authorization Code.
4. `inventory.read` is the scope the client may request, not permission to view every data object.
5. `accessTokenTimeToLive` applies to **newly issued tokens**; changing TTL does not retroactively alter `exp` on existing tokens.
6. `SELF_CONTAINED` specifies the token format; the Resource Server must still verify issuer, signature, audience, timestamps, and scope.

**ID note:** The internal ID of `RegisteredClient` should be generated and kept stable in the repository. Do not regenerate a random ID on every app startup if clients and authorization state must survive restarts.

### 4.1. Two clients with different TTLs

```java
TokenSettings readerPolicy = TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .build();

TokenSettings reportingPolicy = TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(15))
    .build();
```

Attach the two settings to the two corresponding `RegisteredClient` instances. The system can enforce a maximum TTL cap at the governance/policy layer so operators do not accidentally issue overly long-lived tokens.

Never rely on a caller-supplied TTL parameter to decide token lifetime. Grant and token policies are Authorization Server-controlled data.

### 4.2. Do not use refresh token TTL to handle Client Credentials

`TokenSettings.refreshTokenTimeToLive` is not a caching solution for the `client_credentials` grant. Under RFC 6749, refresh tokens should not be issued in this grant; the client uses **client authentication + grant_type=client_credentials** to obtain a new access token.

Do not write logic like "when the access token expires, send a refresh_token" for M2M simply because `OAuth2RefreshToken` exists in the library.

## 5. Token Request and sample response

A confidential client uses HTTP Basic to call the Token Endpoint over TLS:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

The Basic header above is **only a placeholder**, not a real credential. Client ID and secret must be encoded per HTTP Basic/OAuth rules. The AS checks registration, authentication method, credentials, grant, scope, and policy.

Example successful response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "inventory.read"
}
```

This is a readable data illustration, not a literal HTTP body containing raw status/header lines inside JSON. Tokens must be protected like credentials, even when short-lived.

If the client secret is wrong, the Token Endpoint normally returns an error such as `invalid_client`. If the grant or scope is disallowed, appropriate errors like `unauthorized_client` or `invalid_scope` may appear. **Never redirect an M2M client to a user login page.**

## 6. Why cache access tokens on the client?

An unexpired access token can be reused across many API requests. If an instance calls the Inventory API hundreds of times per minute and requests a new token every time, the Token Endpoint bears load proportional to API traffic rather than token lifetime.

```mermaid
flowchart TD
    REQ["billing-service needs to call Inventory API"]
    KEY["Determine token cache key"]
    HIT{"Unexpired token available?"}
    USE["Use existing token"]
    SINGLE["Single-flight per cache key if needed"]
    AS["Client Credentials Token Request"]
    SAVE["Store token, expiresAt, and metadata"]
    API["Call Inventory API"]

    REQ --> KEY --> HIT
    HIT -->|"Yes"| USE --> API
    HIT -->|"No"| SINGLE --> AS --> SAVE --> API
```

Caching serves only to **reuse valid tokens**; it does not alter permissions, expiration, or revocation status.

### 6.1. Cache key: do not use one token for every client

A cache key is typically managed by:

```text
(clientRegistrationId, principalName)
```

In Spring Security OAuth2 Client, `principalName` identifies the authorized client entry. For background Client Credentials, it can be a stable workload name like `svc:billing`, **not a logged-in user**.

| Situation | Cache partitioning |
|---|---|
| One workload, one registration | `inventory-api` + `svc:billing` |
| Calling multiple Resource Servers | Separate registration per API/audience |
| Multiple tenants using different credentials | Partition by trusted tenant/registration |
| Scope/audience changes per request | Never reuse tokens with wrong scope/audience; design separate registrations/keys |

Never keep a single static `lastAccessToken` variable for all APIs. A token carrying only `inventory.read` must never be used as a credential for `payments-api`, even if both systems accept Bearer tokens.

### 6.2. Renewing tokens before expiration

An ideal safety margin accounts for clock skew, network latency, and processing time:

```text
token_usable = (now + safety_margin) < expiresAt
```

For example, if an access token has 20 seconds left yet an API request might run for 30 seconds, acquire a new token before calling the API. A 30–60 second safety margin is a common illustrative baseline; for very short token TTLs, pick a smaller margin to avoid constant token requests.

**Cache TTL must never exceed the access token's lifetime.** Never add extra time to `expiresAt`, because the Resource Server still enforces the issued expiration.

### 6.3. Jitter and avoiding thundering herds

Hundreds of instances may request tokens simultaneously at startup and then expire around the same time, causing a *thundering herd*.

This can be mitigated with:

- **Small bounded jitter** so each instance renews **early** at a slightly different moment.
- **Single-flight** so multiple threads sharing one cache key emit only one Token Request at a time.
- Bounded retries and backoff when the Token Endpoint returns 429/5xx.
- Distributed locking/leasing if the cache is shared across instances and load warrants it.

Jitter must never push token usage past `exp`.

## 7. Spring Security OAuth2 Client: using a manager instead of rolling a custom cache

With `billing-service` acting as the OAuth client, Spring Security provides:

| Class | Role |
|---|---|
| `ClientRegistrationRepository` | Client ID, Token URI, scope, grant, and authentication method |
| `OAuth2AuthorizedClientService` | Saves/retrieves/removes authorized clients, including access tokens |
| `ClientCredentialsOAuth2AuthorizedClientProvider` | Executes the Client Credentials grant when a new token is needed |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manages access tokens for background services without user requests/sessions |

These classes belong to the **OAuth client application**, not default Authorization Server beans.

### 7.1. Declaring client registration

`application.yml` on `billing-service`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-api:
            provider: corporate-as
            client-id: billing-service
            client-secret: ${INVENTORY_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          corporate-as:
            token-uri: https://auth.example.com/oauth2/token
```

`${INVENTORY_OAUTH_CLIENT_SECRET}` indicates a secret injected from the environment/secret manager; **never** commit the real value to Git or print it in startup logs. The Token URI must use HTTPS and point to the trusted issuer/Authorization Server.

### 7.2. Manager for scheduled jobs and service-to-service calls

```java
@Configuration
class OAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {
        return new InMemoryOAuth2AuthorizedClientService(registrations);
    }

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        ClientCredentialsOAuth2AuthorizedClientProvider provider =
            new ClientCredentialsOAuth2AuthorizedClientProvider();

        provider.setClockSkew(Duration.ofSeconds(45));

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Explanation:

- `InMemoryOAuth2AuthorizedClientService` is an in-process cache, convenient for examples and single-instance services.
- `setClockSkew(...)` tells the provider to treat the token as needing renewal slightly before expiration.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` fits **background processes**, without needing an `HttpServletRequest`.
- If no token exists or it is nearing expiration, the provider can **request a new access token via client_credentials**, without using a refresh token.

Depending on your Spring Boot version, repository/service beans may already be auto-configured; avoid creating duplicate beans or unintentionally overriding active configuration. Test runtime behavior with your actual dependency versions.

### 7.3. Service calling the Inventory API with a managed token

Example using `RestClient` in a blocking application:

```java
@Service
public class InventoryGateway {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient inventoryClient;

    public InventoryGateway(
            OAuth2AuthorizedClientManager manager,
            RestClient.Builder restClientBuilder) {
        this.manager = manager;
        this.inventoryClient = restClientBuilder
            .baseUrl("https://inventory.example.com")
            .build();
    }

    public String readInventory() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
            .withClientRegistrationId("inventory-api")
            .principal("svc:billing")
            .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "No authorized client for inventory-api");
        }

        String token = client.getAccessToken().getTokenValue();

        return inventoryClient.get()
            .uri("/inventory")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
```

This code focuses on token acquisition and API invocation; imports, RestClient timeouts, exception handling, and integration tests are still needed. `RestClient` is part of modern Spring Framework. For reactive WebFlux services, use the **reactive** OAuth2 client manager rather than blocking the event loop with a blocking manager.

**Do not log the `token` variable.** `principal("svc:billing")` is a stable workload name used to partition the authorized client entry, not evidence of an end user.

### 7.4. Limitations of the default cache

The manager/service handles token lifecycle, yet does not automatically guarantee:

- A single Token Request across all threads during concurrent cache misses.
- A shared cache across multiple JVMs/pods.
- Encryption at rest if stored in a custom distributed cache.
- Cache keys automatically expanded for dynamic audiences/tenants.
- Automatic recovery from every API 401 caused by token revocation.
- Zero outages during client secret rotation.

Evaluate real requirements and add appropriate mechanisms rather than assuming "having a manager makes every topology production-ready".

## 8. In-memory vs. distributed token caching

| Approach | Advantages | Risks/trade-offs |
|---|---|---|
| Per-instance in-memory | Simple to operate; tokens never traverse a shared cache | Restarts drop tokens; multiple instances acquire tokens independently |
| Persistent `OAuth2AuthorizedClientService` | Can retain state across restarts | Must protect tokens at rest, enforce access control, and clean up stale entries |
| Custom distributed cache/locking | Reduces Token Requests cluster-wide | Adds complexity for races, consistency, lock expiry, and cache security |
| No cache | Simple, but sends far more requests | Higher Token Endpoint load/latency; outages propagate immediately |

**Per-instance in-memory caching is usually the right first choice** for M2M if instance count and Token Endpoint capacity allow. Introduce distributed caching only when the benefit is measured and token-protection controls are in place.

### 8.1. Race conditions on cache miss

Suppose 30 threads simultaneously notice an expired token. If all 30 call the AS, 30 new access tokens are minted at once even though one would suffice.

Single-flight should lock **per cache key**, not across the entire application. Threads sharing the same key wait for one token acquisition; threads calling other clients proceed independently. Across multiple nodes, a JVM mutex is not a distributed lock.

When retrying, use backoff and jitter; do not turn the Token Endpoint into a bottleneck caused by every API request refreshing simultaneously.

### 8.2. Never keep using an expired cached token just because the AS is down

If the AS experiences an outage while a cached access token is still valid, the client can keep using that cached token. Once the token expires, **never attempt to send the expired token** or ask the Resource Server to ignore `exp`. Fail cleanly with controlled error reporting, reduced retry load, and operational fallbacks matching your SLA.

## 9. Handling 401, 403, and Token Endpoint errors

| Situation | Analysis | Appropriate response |
|---|---|---|
| Resource Server returns `401 invalid_token` | Token expired/invalid/revoked | Conditionally evict cache, acquire a new token, and retry at most once if appropriate |
| Resource Server returns `403` | Token authenticated, yet lacks permissions | Check scope/audience/policy; do not retry token acquisition infinitely |
| Token Endpoint returns `invalid_client` | Client credentials rejected by AS | Check secret/key/cert, rotation state, and clock if using assertions |
| Token Endpoint returns `unauthorized_client` | Client is not permitted to use the grant | Check registration; do not "increase TTL" as a workaround |
| Token Endpoint returns `invalid_scope` | Requested scope is invalid | Check registration and policy |
| Token Endpoint returns `429` or `5xx` | Rate limiting or AS incident | Backoff, bounded retries, circuit breaker, and metrics |
| Token Endpoint timeout | Network/AS unresponsive | Bounded retries, thundering-herd protection |

Caution when retrying API requests: never automatically replay **non-idempotent** data-modifying operations without proper idempotency guarantees. With multiple threads, cache eviction must avoid accidentally deleting a fresh token just stored by another thread.

`OAuth2AuthorizedClientService.removeAuthorizedClient(registrationId, principalName)` can evict an authorized client from storage, though production requires handling concurrency and eviction reasons carefully.

### 9.1. A 401 is not always caused by an expired token

Even a brand-new token gets a 401 if the Resource Server has the wrong issuer, audience, JWKS, mTLS token binding, or points to the wrong environment. Never build an infinite `401 → acquire new token → 401 → acquire new token` loop.

Similarly, a 403 due to missing scope cannot be solved by requesting another token with the exact same grant/scope and hoping for a different outcome. Inspect policies and the claims actually issued.

## 10. Client credential rotation is a separate problem from token TTL

Suppose the AS issued access token A with `exp` 10 minutes out. After 3 minutes, an operator rotates the secret:

```mermaid
flowchart LR
    OLD["Old client secret"] --> TOKEN["AS issues access token A"]
    TOKEN --> RS["Resource Server validates token A"]
    NEW["New client secret"] --> TOKEN2["AS issues access token B"]
    TOKEN2 --> RS
```

Once the AS stops accepting the old secret:

- The old secret **can no longer be used to request new tokens**.
- Access token A **is not automatically invalidated**; a self-verifying JWT remains usable until `exp` if the RS does not check revocation.
- Clients caching token A continue calling the API normally, then fail on the next token acquisition unless they have received the new secret.
- If a secret is compromised and access must be cut immediately, handle **both the credential and live tokens** under incident response policy.

### 10.1. Distinguishing key/credential types

| Artifact | What is it used for? |
|---|---|
| Client secret | Authenticates the client to the AS at the Token Endpoint |
| `private_key_jwt` private key | Client signs an assertion for the AS to verify the client |
| mTLS client certificate/private key | Authenticates the client at TLS and may support sender-constrained tokens |
| AS JWT signing key | AS signs tokens; Resource Server verifies with the public key |
| Access token | Client calls the Resource Server |

**Rotating a client secret is not rotating the AS JWT signing key.** AS signing keys must be retained/rotated around remaining token lifetimes and JWKS caches; that is an independent lifecycle.

## 11. Phased client secret rotation policy

A controlled rotation process:

| Step | Action | Verification |
|---|---|---|
| **Prepare** | Generate a new secret via CSPRNG, store in secret manager, restrict visibility | Not leaked in Git/CI/logs/tickets |
| **Enable** | Load the new secret into the AS acceptance mechanism per design | A **new** Token Request using the new secret succeeds |
| **Roll out** | Update the secret version across all client instances | Instances actually use the new version when requesting tokens |
| **Observe** | Monitor `invalid_client`, Token Endpoint, and API 401s | No error spikes when cached tokens expire |
| **Retire** | Stop accepting the old secret | Token Requests using the old secret are rejected |
| **Audit** | Log actor, client, version, timestamps, and outcome | Never store secret values in audit events |

### 11.1. Limitations of `RegisteredClient.clientSecret`

The standard `RegisteredClient` model typically holds only **one active `clientSecret` field**. Never assume a simple `RegisteredClientRepository.save(...)` supports **two simultaneously valid secrets** for zero-downtime rotation.

If a secret overlap window is needed:

- Verify whether your framework/implementation supports multiple valid credentials.
- If not, design a custom credential store/client authentication provider, or adopt an asymmetric method with managed overlap.
- If overlap is unsupported, schedule a synchronized rollout/maintenance window, measure impact, and prepare a rollback plan **that never reverts to a compromised secret**.

**Never design zero-downtime rotation on top of a multi-secret feature that does not exist.**

### 11.2. Example updating a secret in the repository

```java
RegisteredClient existing =
    registeredClientRepository.findByClientId("billing-service");

if (existing == null) {
    throw new IllegalStateException("Client not found");
}

RegisteredClient updated = RegisteredClient.from(existing)
    .clientSecret(passwordEncoder.encode(newSecretFromSecureStore))
    .build();

registeredClientRepository.save(updated);
```

This snippet only illustrates preserving other `RegisteredClient` fields. Production requires admin authorization, validation, revision/optimistic locking, auditing, approvals where needed, and synchronizing client repository caches across AS nodes.

**Never record old/new secrets or secret hashes in audit diffs.** Record only events like `CLIENT_SECRET_ROTATED` with actor, client ID, and credential version.

## 12. Rotating `private_key_jwt` keys

With `private_key_jwt`, the client holds a private key and signs a JWT assertion to authenticate at the Token Endpoint. The Authorization Server verifies the assertion with a trusted public key. This mechanism simplifies rotation because the client's JWK Set can publish **both old and new public keys** during the transition window.

Reference procedure:

1. Generate a new key pair and new `kid`; protect the private key.
2. Publish the new public key in the JWK Set trusted by the AS, retaining the old key if policy permits.
3. Verify the AS accepts assertions signed with the new key.
4. Roll client instances over to the new key.
5. Monitor `invalid_client` errors, JWKS caching, clock skew on `iat`/`exp`, and assertion audience.
6. After the transition window, remove the old public key; revoke/delete the old private key.
7. Log a rotation audit event containing no private keys or raw assertions.

Example method registration:

```java
RegisteredClient jwtClient = RegisteredClient
    .withId("billing-internal-id")
    .clientId("billing-service")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.PRIVATE_KEY_JWT)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("inventory.read")
    .clientSettings(ClientSettings.builder()
        .jwkSetUrl("https://keys.example.com/billing/jwks.json")
        .build())
    .build();
```

This is an illustrative model, omitting the JWT assertion generator, validator, signing keys, and full deployment config. `jwkSetUrl` must point to a trusted, controlled source to prevent SSRF or trusting arbitrary URLs. Exact support depends on your Spring Authorization Server version.

## 13. Rotating mTLS certificates

mTLS requires the client to present a certificate and the server to validate the trust chain/identity over the TLS connection. It **differs from standard HTTPS**, where only the server presents a certificate.

mTLS rotation includes:

- Managing CA/PKI and certificate lifetimes.
- Issuing new certificates/keys before old ones expire.
- Allowing a controlled overlap window in trust policies when needed.
- Updating client keystores/truststores and reverse proxy configurations.
- Testing that the AS resolves the right client identity under TLS termination topologies.
- Revoking old certificates and auditing cutover timestamps.

mTLS can also participate in sender-constrained access tokens when implementing RFC 8705 properly. Tokens can then be bound to the certificate and the RS must actively verify the binding; never assume "using mTLS at the Token Endpoint automatically binds every Bearer token".

## 14. Simulating a rotation incident with token caching

Suppose there are three pods A, B, and C. Token TTL is 10 minutes, and all pods cache tokens.

| Simulated time | Event | Outcome |
|---|---|---|
| 10:00 | A/B/C acquire tokens using the old secret | All operate normally |
| 10:03 | AS switches to the new secret | Unexpired old tokens can still call the API |
| 10:04 | A updates to the new secret | A's next token acquisition will succeed |
| 10:06 | B/C not yet updated; still using cached tokens | API calls may still succeed |
| 10:09 | B's token nears expiration; B requests a new token | `invalid_client` due to old secret |
| 10:10 | C's cached token expires | C may also fail |
| 10:11 | B/C update to the new secret and request new tokens | Normal operation resumes |

**Token caching can mask rotation failures until the next token acquisition.** Therefore, rotation verification must never rely solely on calling the API with a cached access token. Force a **new Token Request** with the new credential, confirm every pod loaded the new secret version, and monitor `invalid_client`.

### 14.1. Post-rotation verification

1. Force a fresh Token Request using the new credential through the proper integration path.
2. Verify the Token Endpoint authenticates the client and issues a token with the expected scope/audience.
3. Call the Resource Server with the new token.
4. Verify all instances are running with the new credential version.
5. Retire the old secret on schedule.
6. Verify the old secret can no longer obtain tokens.
7. Decide how to handle access tokens issued before rotation, especially upon suspected compromise.

## 15. Handling Authorization Server outages with token caching

When the Token Endpoint temporarily fails:

- If the cached token **is still valid and matches scope/audience**, the client may continue using it.
- Once the token expires, never send an expired token or ask the RS to skip validation.
- Token Endpoint retries must be bounded with exponential backoff/jitter and an appropriate circuit breaker.
- When the AS recovers, prevent the entire cluster from firing a flood of simultaneous Token Requests.

A simple model to estimate steady-state token acquisition load:

```text
token_requests_per_second ≈
    number_of_instances × number_of_distinct_cache_keys
    / effective_token_ttl_seconds
```

Assuming 100 instances, each with one cache key and an effective token TTL of 500 seconds, steady-state load is roughly 0.2 requests/second. This is only an approximation; startup bursts, retries, and multiple registrations increase the request rate.

**Do not inflate token TTL excessively just to work around network/caching bugs.** Measure cache hit ratio and fix token acquisition efficiency first.

## 16. Testing TTL, caching, and credential rotation

### 16.1. Testing the Authorization Server

| Case | Setup | Expectation |
|---|---|---|
| Valid grant | Client has `CLIENT_CREDENTIALS` and valid secret | AS issues access token |
| Unregistered grant | Client only has Authorization Code | AS rejects `client_credentials` |
| Wrong scope | Requesting `inventory.write` when only `inventory.read` is allowed | AS rejects or refuses excess scope |
| Per-client TTL | Clients A/B have different `TokenSettings` | Issued tokens carry corresponding expirations |
| JWT/opaque format | Configured token format | RS verifies with matching mechanism |
| Wrong secret | Token Request with old/revoked secret | `invalid_client` or corresponding error |
| No refresh token | Client Credentials Token Response | Client does not receive a refresh token by default |

### 16.2. Testing the token cache

| Case | Outcome to prove |
|---|---|
| Cache miss | Emits Token Request to fetch token |
| Cache hit with sufficient remaining lifetime | Does not call Token Endpoint again |
| Token near `expiresAt` | Manager requests a new token per clock skew |
| Two threads miss cache | Concurrency handled per policy without uncontrolled stampede |
| Multiple registrations | Token for API A is never used for API B |
| Different tenants | Never shares tokens across mismatched identity/scope/audience |
| Cache restart | Token acquisition resumes cleanly after cache loss |
| AS outage, valid cached token | Can continue calling API per policy |
| AS outage, expired token | Never attempts to use expired token |
| RS 401 | Bounded invalidation/retry avoiding races |
| RS 403 | Does not spam new token requests |

### 16.3. Testing rotation

| Case | Outcome to prove |
|---|---|
| New secret before retire | AS accepts new Token Requests via designed transition mechanism |
| Old secret after retire | Rejected |
| Unexpired old access token | RS handles per `exp`/revocation; do not assume automatic expiration |
| Pod missing new secret | Failure detected when cache needs a new token |
| `private_key_jwt` rotating `kid` | AS trusts new key during transition window |
| mTLS certificate rotation | AS verifies new certificate |
| Concurrent admin updates | Revision/locking prevents lost updates |
| Logs/audits | No secrets, raw tokens, or private keys appear |

### 16.4. Boundary unit test with `Clock`

You can test the "token has enough lifetime to call API" condition with a small helper using a controllable `Clock`:

```java
static boolean hasEnoughLifetime(
        OAuth2AccessToken accessToken,
        Clock clock,
        Duration safetyMargin) {

    Instant expiresAt = accessToken.getExpiresAt();
    return expiresAt != null
        && Instant.now(clock)
            .plus(safetyMargin)
            .isBefore(expiresAt);
}
```

This function only illustrates the TTL condition. When using the standard `OAuth2AuthorizedClientManager`, rely on the provider's built-in clock-skew mechanism and test real behavior rather than maintaining two conflicting expiry rules. Boundary tests around expiry using a fake clock are far more deterministic than `Thread.sleep(...)`.

## 17. Observability, auditing, and incident response

### 17.1. Metrics to measure

- Token Endpoint QPS by client and grant type.
- `invalid_client`, `unauthorized_client`, and `invalid_scope` rates.
- Cache hit/miss ratio and token acquisition latency.
- Requests occurring near token expiration.
- API 401/403 counts by registration/Resource Server.
- Single-flight waits, retry/backoff counts, and circuit breaker activations.
- Credential version, `kid`/certificate identifier, and rotation progress (without secrets).
- Number of instances still using an old credential version.
- Failed token acquisition events during AS outages.

### 17.2. Never log

- `client_secret` or raw `Authorization: Basic ...`.
- `access_token`/`refresh_token` or raw `Authorization: Bearer ...`.
- Private keys, raw client assertion JWTs, or mTLS private keys.
- Unredacted Token Endpoint bodies/responses.
- Cache dumps containing tokens, secret manager responses, or secret hashes.

Use correlation IDs, client registration IDs, remaining TTL, error categories, and durations instead of raw credentials.

### 17.3. If a client credential is compromised

1. Identify affected clients and workloads; restrict further permissions/usage paths.
2. Revoke the old credential and securely issue a new credential.
3. Verify every client instance has rolled over to the new credential.
4. Investigate access tokens that may have been issued using the compromised credential.
5. If immediate access cutoff is required, enact revocation/introspection/denylist or RS policies rather than only rotating the secret.
6. Record audit logs, preserve evidence, and add controls to prevent recurrence.

## 18. Pre-production checklist

- [ ] Client is registered only with the `CLIENT_CREDENTIALS` grant and required scopes.
- [ ] Client authentication is appropriate; secrets/keys are stored in a secret manager.
- [ ] `TokenSettings.accessTokenTimeToLive` is chosen based on threat model and real load.
- [ ] Resource Server verifies issuer, signature or introspection, audience, expiry, and scope/policy.
- [ ] Client reuses unexpired access tokens using a tested manager/cache.
- [ ] Cache keys never mix registrations, workloads, tenants, or audiences.
- [ ] Cache refreshes tokens ahead of expiration using appropriate clock skew/jitter.
- [ ] Cache stampede controls exist for multi-thread/multi-instance misses.
- [ ] 401 and 403 are handled differently; no infinite retries.
- [ ] Refresh tokens are not assumed in Client Credentials.
- [ ] Credential rotation policy covers prepare/enable/rollout/verify/retire/audit.
- [ ] Verified whether dual-secret support exists before promising zero downtime.
- [ ] Tested new token acquisition after rotation rather than only calling APIs with cached tokens.
- [ ] AS signing key rotation is decoupled from client credential rotation.
- [ ] Logs, traces, metrics, and audits contain no raw secrets/tokens/keys.
- [ ] Runbooks exist for secret leakage, AS outages, and token revocation.

### Core knowledge

**Token TTL** is a policy decided by the Authorization Server at issuance; **token caching** is the OAuth client's responsibility to reuse valid tokens and acquire new ones when needed; **credential rotation** is the process of replacing client authentication material at the Token Endpoint. These three lifecycles interact, yet **do not terminate together automatically**.

Spring Authorization Server provides `TokenSettings` on each `RegisteredClient`. Spring Security OAuth2 Client provides `AuthorizedClientServiceOAuth2AuthorizedClientManager` and `ClientCredentialsOAuth2AuthorizedClientProvider` for M2M workloads. Safe production operation additionally requires proper cache keying, expiry skew, concurrency control, credential protection, verified rotation, and real-world observability.

## References

- [RFC 6749 — OAuth 2.0 Authorization Framework, Client Credentials §4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Security — OAuth 2.0 Client: Authorized Client Manager](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
