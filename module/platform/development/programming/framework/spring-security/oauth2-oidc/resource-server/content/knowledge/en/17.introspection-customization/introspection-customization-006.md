# Introspection Credentials and Secret Rotation

## 1. Problem Statement: One Access Token and One Credential to Verify Tokens

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an API may receive an **opaque access token** and validate it through the Authorization Server's (AS) **OAuth 2.0 Token Introspection** endpoint rather than verifying a JWT locally with a public key. What often causes confusion is that this flow involves **two credentials with different origins and purposes**.

**First credential — the API caller's Bearer access token:**

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer 8NsP2s0Y...access-token...
```

**Second credential — the Resource Server's own credentials when calling the introspection endpoint:**

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <base64-of-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=8NsP2s0Y...access-token...
```

The access token string in the body is the data being inspected. The Basic credential in the HTTP header is proof that the Resource Server is permitted to query the AS about that token. They **do not substitute for each other**:

| Component | Who Holds and Uses It? | Which Endpoint Is It Used With? | What Can It Do? |
| --- | --- | --- | --- |
| Bearer **access token** | OAuth client; Resource Server receives it to process requests | Business API `/api/**` | Proves authorization for a resource if the token is active and satisfies the contract |
| **Introspection client ID** | Resource Server / trusted backend | AS introspection endpoint | Identifies the Resource Server's client at the AS; **not a secret** |
| **Introspection client secret** | Resource Server / secret manager | AS introspection endpoint | Authenticates the Resource Server client per AS policy |
| Private key / certificate for introspection client auth | Resource Server using asymmetric auth or mTLS | AS introspection endpoint | Proves workload identity without a traditional shared secret |
| AS's JWT signing private key | Authorization Server | JWT issuance flow | Signs JWTs; **not** the secret for the Resource Server to call introspection |

An **expired introspection client secret** incident can prevent all valid access tokens from being verified. This is normally an **authentication incident between the Resource Server and the Authorization Server**, not every user token being revoked simultaneously.

> **Principle:** Separate the lifecycles of **access tokens**, **introspection credentials**, and **JWT signing keys**. Rotating one credential does not automatically rotate the other two.

## 2. RFC 7662 and the Trust Boundary of Introspection

**RFC 7662 — OAuth 2.0 Token Introspection** defines the protocol by which a Resource Server queries an AS about a token's state and metadata. Under the common model:

1. The client calls the API with an access token.
2. The Resource Server extracts the Bearer token via `BearerTokenAuthenticationFilter`.
3. `OpaqueTokenAuthenticationProvider` invokes `OpaqueTokenIntrospector.introspect(String token)`.
4. The introspector uses **its own credentials** to call the introspection endpoint over HTTPS.
5. The AS verifies the Resource Server's permission to call the endpoint, checks the token, and returns a response with `active` and metadata.
6. The Resource Server then enforces resource policy, scopes, and data-level permissions.

```mermaid
sequenceDiagram
    participant Client as OAuth Client
    participant API as Spring Resource Server
    participant Vault as Secret Manager
    participant AS as Authorization Server
    Client->>API: Authorization: Bearer access_token
    API->>Vault: Fetch active secret (from config/memory)
    Vault-->>API: Introspection client credential
    API->>AS: POST introspection (client auth + token)
    AS->>AS: Authenticate API client credential
    alt Client credential wrong/expired
        AS-->>API: HTTP 401/403 (per AS policy)
        API-->>Client: Reject safely, classify dependency/config failure
    else Client credential allowed
        AS->>AS: Determine token status
        alt Token inactive
            AS-->>API: 200 {"active": false}
            API-->>Client: Token not accepted
        else Token active
            AS-->>API: 200 {"active": true, "scope": "...", ...}
            API->>API: Check audience, scope, actor/tenant
            API-->>Client: Allow or deny per policy
        end
    end
```

The diagram above is conceptual. Depending on the architecture, the Resource Server may load secrets at startup or receive updates from the secret manager **without calling the secret manager on every HTTP request**. The diagram does not imply that each introspection performs a Vault read.

### 2.1. Do Not Confuse HTTP 200 with a Valid Token

The AS may return:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
```

This means **the introspection request was processed**, but the token is not recognized. An active token may return:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
```

`active=true` shows that the AS accepts the token under endpoint semantics, yet the API must still check resource binding, scopes, tenant, and business rules when required by contract. **Never grant administrative permissions merely because the AS confirmed the token is active.**

### 2.2. What Should the Introspection Client Be Allowed to See?

An introspection endpoint can reveal information about subjects, clients, scopes, audiences, and token status. Therefore:

- The AS must **protect the endpoint** with authentication/authorization and TLS per RFC 7662.
- The Resource Server's credentials should only be authorized to **introspect the tokens/resources it needs**.
- Never use a shared secret allowed to view every tenant's tokens when scopes/permissions can be separated.
- Never return the full introspection response to the API caller.
- The AS may restrict returned metadata based on the introspecting resource/client; the API must know the exact data contract.

In multi-Resource-Server systems, a shared secret increases the **blast radius** if credentials leak. Prefer separate client registrations/permissions per resource or trust domain when supported by the AS.

## 3. Client Authentication at the Introspection Endpoint: Not Just Basic

OAuth 2.0 supports several client authentication mechanisms depending on the AS and client registration. **Spring Boot's opaque-token properties do not automatically support every mechanism.** Choose only a mechanism registered with the AS, capable of credential provisioning, and supported by a corresponding client implementation.

| Mechanism | Principle | Lifecycle Characteristics |
| --- | --- | --- |
| **`client_secret_basic`** | HTTP Basic `Authorization` containing client ID and client secret encoded per protocol | Shared secret must be rotated; avoid header logging |
| **`client_secret_post`** | Sends client ID/secret in the form body when supported by the AS | Secret resides in HTTP body; avoid body logging and prefer Basic when available |
| **`private_key_jwt`** | Resource Server signs a client assertion JWT with a private key; AS verifies with registered public key | Rotate private key/public JWK; manage `kid`/`jti`/`exp` and replay protection |
| **mTLS client authentication** | TLS client certificate proves client identity; AS binds certificate to client registration | Rotate certificate/private key and TLS trust; requires overlap window |
| **Custom client authentication** | Vendor- or gateway/trust-domain-specific | Requires dedicated contract; do not assume RFC compatibility |

**Spring Security Resource Server's default opaque-token config typically uses introspection URI, client ID, and client secret**, fitting client-secret scenarios. For mTLS or `private_key_jwt`, configure the HTTP client/`OpaqueTokenIntrospector` and Authorization Server per contract; do not just set `client-secret` and expect it to switch mechanisms automatically.

### 3.1. HTTP Basic and Encoding Pitfalls

Under OAuth 2.0, client IDs and secrets can contain characters such as `+`, `:`, `%`, `/`. The Basic mechanism for OAuth client authentication has encoding rules before forming HTTP Basic credentials. Naively concatenating `clientId + ":" + secret` and Base64-encoding **can fail** when credentials contain special characters.

Hypothetical example:

```text
client_id     = orders:api+introspection
client_secret = p@ss/word+2026
```

**Never use these two strings as real secrets.** They merely show how double-encoding or missing encoding can cause the AS to return 401 even when the logical client ID/secret are right.

In Spring Security 6.5+ per the documented builder API:

```java
OpaqueTokenIntrospector introspector =
        SpringOpaqueTokenIntrospector
                .withIntrospectionUri(introspectionUri)
                .clientId(rawClientId)
                .clientSecret(rawClientSecret)
                .build();
```

The builder takes **unencoded (raw) values** and handles encoding appropriately. When upgrading older code that **stored secrets in percent-encoded form**, do not keep feeding the pre-encoded string into the builder and double-encoding it.

### 3.2. Basic Differs from the Caller's Bearer Token

In a request to the AS:

```http
POST /oauth2/introspect HTTP/1.1
Authorization: Basic <introspection-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<caller-access-token>
```

Basic here is not the user's `Authorization: Bearer`. The AS needs to distinguish **which token** the Resource Server is asking about, **which client** the Resource Server is, and **which scope of tokens it is allowed to introspect**.

**Never pass the caller's Bearer token as the Basic password**, and never use the introspection client secret as an access token to call APIs. If you need to call another AS endpoint with a Bearer credential, use a separate registration and flow per contract.

### 3.3. Client Assertion Tokens for `private_key_jwt`

In the `private_key_jwt` model, the Resource Server typically signs a short-lived client assertion JWT containing required claims, such as `iss`/`sub` identifying the client, `aud` targeting the AS-required endpoint, `exp`, `iat`, and `jti`. The AS must verify the signature and anti-replay policy.

Conceptual flow:

```text
Resource Server private key
  -> sign client assertion JWT
  -> send client_assertion_type + client_assertion in introspection request
Authorization Server
  -> look up registered public key for the introspection client
  -> verify signature, aud, expiration, and jti
  -> only then introspect the caller's access token
```

This is a JWT **authenticating the client calling introspection**, **not** a user's JWT access token. `kid` on the client assertion helps the AS select the client's registered public key; `kid` does not create trust on its own.

## 4. Common Spring Boot Configuration Without Exposing Secrets in Source

A Servlet Resource Server using introspection can declare:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

The environment variables in the example must be provisioned via a **secret manager / secure deployment mechanism**; never write production secrets into YAML files committed to Git.

Example `SecurityFilterChain`:

```java
@Configuration
class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

With the right Spring Boot dependencies/configuration and no custom replacement bean, Boot can auto-configure an `OpaqueTokenIntrospector` from those three properties. `OpaqueTokenAuthenticationProvider` invokes the introspector to obtain the principal/authorities, and URL/method authorization then checks scopes.

**Do not blindly call `oauth2ResourceServer().jwt()` when the AS issues opaque tokens.** Configuring JWT makes Spring use `JwtDecoder`; configuring opaque makes Spring use `OpaqueTokenIntrospector`. Even a JWT-shaped token can be sent to introspection if the chain intentionally selects the opaque-token flow.

### 4.1. Never Put Secrets in Live Example Configs

Do not do this:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: my-actual-long-lived-secret # DO NOT COMMIT
```

In production environments, use an appropriate mechanism:

- A secret manager (Vault, cloud secret manager, or internal IAM-backed solution).
- A Kubernetes Secret volume protected by RBAC/namespace/encryption, paired with safe reload mechanisms.
- Deployment injection with restricted read access, rotation, and auditing.
- Secret references in a configuration management system with least-privilege access.

**Environment variables** are convenient for configuration, yet can still leak via process inspection, crash dumps, diagnostic logs, or platform configuration-viewing permissions. Never treat "put it in an environment variable" as sufficient without IAM, access control, auditing, and rotation procedures.

### 4.2. Protect Both Client ID and Secret as Assets with Different Semantics

A client ID is usually **not a secret**, though exposing it can help an attacker identify which registration is in use. The client secret is an **authentication secret**. A secret manager can store both in a single versioned configuration to avoid deployments picking up a new client ID alongside an old secret.

When changing a **client registration** during a migration, treat the `(client-id, client-secret)` pair as **one consistent credential bundle** rather than updating the two fields at uncoordinated times.

## 5. `OpaqueTokenIntrospector` Is the Extension Point to Keep Stable

In Spring Security Servlet, the interface:

```java
package org.springframework.security.oauth2.server.resource.introspection;

public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

This contract allows:

- Letting Boot build `SpringOpaqueTokenIntrospector` from properties.
- Explicitly building `SpringOpaqueTokenIntrospector` when HTTP client customization is needed.
- Wrapping with a decorator to add issuer/audience checks, metrics, or fail-closed policies.
- Replacing the underlying implementation during framework upgrades without changing service/business code.

Example bean for **Spring Security 6.5+**:

```java
@Configuration
class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${introspection.uri}") String uri,
            @Value("${introspection.client-id}") String clientId,
            @Value("${introspection.client-secret}") String clientSecret) {

        return SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();
    }
}
```

The builder above was added in Spring Security **6.5**; older projects should use the constructor/`RestOperations` available in their running version. Newer Spring Security releases also provide `RestClientOpaqueTokenIntrospector` using `RestClient` starting in **7.1**. When implementing, check your actual `spring-security-oauth2-resource-server` dependency version; bean code must match that specific version.

**Once you define a custom `OpaqueTokenIntrospector` bean**, Boot's auto-configuration may back off, while chain-level `.opaqueToken(opaque -> opaque.introspector(...))` can override bean selection. Always verify **which introspector is actually used**.

## 6. The Essence of Secret Rotation

**Secret rotation** is the process of replacing the credential that authenticates the Resource Server to the introspection endpoint while ensuring:

1. The API **never accepts a token that has not been properly introspected**.
2. Neither the old nor the new secret is leaked.
3. Service disruption is avoided to the extent supported by the AS.
4. The new credential is proven to work **before disabling the old credential**, when an overlap window exists.
5. Exposure time for a suspected compromised secret is minimized.
6. A clear rollback runbook and incident plan are in place.

A credential lifecycle:

```mermaid
flowchart LR
    NEW["Create new secret<br/>in AS/secret manager"] --> STAGE["Distribute new version<br/>to Resource Servers"]
    STAGE --> ACT["Activate new version<br/>by version ID"]
    ACT --> CHECK["Verify introspection<br/>with new credential"]
    CHECK --> RETIRE["Revoke old secret<br/>per allowed window"]
    RETIRE --> AUDIT["Check audit logs, remove<br/>unneeded copies/backups"]
```

Never just "change the string in YAML and restart" without knowing whether the AS supports **two active secrets simultaneously**. If the AS allows only one secret per client, rotating the secret can immediately break introspection on older instances.

### 6.1. Questions to Ask the Authorization Server Before Rotating

- Can a single client registration have **two client secrets in parallel** during a transition window?
- Is there an operation to generate a new secret **without immediately revoking the old one**?
- Does the client ID stay the same during rotation, or must a **new client ID** be created?
- When does the new secret take effect; is there any propagation/cache delay?
- Can the new credential be tested against the introspection endpoint safely without touching real user tokens?
- Can the old credential be revoked independently, with logs confirming when it stops being used?
- How does the emergency procedure for suspected compromise differ from scheduled rotation?
- Are **mTLS** or `private_key_jwt` supported to reduce shared-secret risk?

These capabilities **belong to the AS/provider**, not Spring Security.

## 7. Scenario A: AS Accepts Both Old and New Secrets Simultaneously

This is the favorable condition for **zero-downtime or near-zero-downtime rotation**, if executed properly.

Suppose we have:

```text
client_id = orders-api-introspector
secret_v1 = [old secret — do not log]
secret_v2 = [new secret — do not log]
```

### Phase 1 — Preparation

1. Create `secret_v2` in the AS using randomness/strength meeting policy.
2. **Keep `secret_v1` active** in the AS.
3. Store `secret_v2` in the secret manager under a **new version**, never in Git, tickets, or Slack.
4. Verify read access to the secret is restricted to the required service accounts/deployments.
5. Prepare a rolling deployment or tested introspector update mechanism.

### Phase 2 — Cut Over Resource Servers

1. Roll out the application/secret reference so instances gradually adopt `secret_v2`.
2. Let un-updated instances continue using `secret_v1` during the overlap window.
3. From each region/cluster, run an **authenticated health probe** to the introspection endpoint safely.
4. Monitor introspection client auth errors, AS 401/403 responses, timeouts, and latency.
5. On error, roll back instances to the old bundle **while the AS still permits v1**.

### Phase 3 — Revoke the Old Secret

1. Confirm **every instance** is using v2, including background jobs, standby, disaster-recovery, and long-lived processes.
2. Check AS logs to verify no requests are still arriving with v1.
3. Disable `secret_v1` in the AS.
4. Monitor for post-revocation errors during a watch window.
5. Remove v1 from secret manager/CI/CD runtime copies per retention/audit policy.

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant SM as Secret Manager
    participant RS1 as Resource Server v1
    participant RS2 as Resource Server v2
    AS->>AS: Create secret_v2, keep v1 active
    AS->>SM: Secret v2 (via authorized workflow)
    SM-->>RS2: Distribute v2
    RS1->>AS: Introspect with v1
    AS-->>RS1: Success
    RS2->>AS: Introspect with v2
    AS-->>RS2: Success
    RS2->>AS: Probe/traffic confirms v2 stable
    AS->>AS: Revoke v1 after full rollout
    RS2->>AS: Continue using v2
    AS-->>RS2: Success
```

**Do not pick an arbitrary overlap window:** base it on instance count, rollout speed, config caches, client auth logs, failure detection time, and revocation urgency upon compromise.

## 8. Scenario B: AS Allows Only One Active Secret Per Client

Some Authorization Servers **immediately invalidate the old secret** when you "regenerate client secret." With rolling deployments, this creates risk:

```text
T0: All Resource Servers use secret_v1.
T1: AS immediately replaces v1 with v2.
T2: Instances still holding v1 call introspection → AS returns 401.
T3: Introspection resumes only after instances are updated.
```

In this case, **zero downtime** cannot be guaranteed solely by choosing "update AS first" or "update app first." Another design is needed:

### 8.1. Create Two Independent Client Registrations

If supported by the AS, create:

```text
orders-introspector-v1 → secret_v1 (active)
orders-introspector-v2 → secret_v2 (new)
```

Grant **equivalent least-privilege** introspection permissions to v2; verify scopes, audience/resource visibility, and rate limits. Once v2 works, rolling-deploy Resource Servers to the **`(client-id-v2, secret-v2)` pair**. Once v2 serves traffic stably, revoke client registration v1.

This is **blue-green introspection client registration**, not issuing new access tokens for users. Permissions of both client registrations must be reviewed so v2 does not accidentally receive broader access.

### 8.2. Coordinated Cutover with a Planned Disruption Window

If the AS supports neither multiple secrets nor equivalent client registrations, a brief outage **may be unavoidable**. In that case:

- Schedule a maintenance window or traffic draining.
- Stage the new secret/configuration on inactive instances before switching.
- Switch the AS and runtime in a coordinated procedure.
- Verify introspection per region before taking traffic.
- Communicate operational status clearly instead of **failing open** on unverified tokens.

Never promise "zero downtime" if the provider lacks overlap support or the cutover procedure is not atomic.

## 9. Scenario C: Emergency Rotation When Secret Compromise Is Suspected

Scheduled rotation optimizes continuity. **Emergency rotation** prioritizes **stopping abuse of the exposed secret**.

Typical procedure:

1. Scope the impact: which client registration, which AS, which environments, and which Resource Servers may be affected.
2. Prioritize **revoking/disabling the suspected compromised credential** quickly per incident response policy, even if it causes disruption.
3. Issue a new credential over a secure channel with minimal introspection permissions; never reuse the old secret in another environment.
4. Audit AS logs, anomalous token metadata queries, and administrative actions around the credential.
5. Deploy the new credential and confirm APIs no longer depend on the old version.
6. Scrub copies of the secret from CI/CD variables, logs, temp files, crash dumps, test environments, and docs if present.
7. Analyze the exposure root cause and update IAM, rotation intervals, and preventive controls.

**Never keep a suspected compromised secret active just for zero downtime.** You may use blue-green or emergency replacement, but the decision must be risk-driven.

### 9.1. What Damage Can an Exposed Introspection Secret Cause?

This depends on the client's permissions in the AS:

- If the credential only permits introspection, an attacker can **query status and metadata of tokens they know/guess/steal**, depending on AS policy.
- If the secret is reused for `client_credentials` grants, token endpoints, or admin APIs, impact can be **far greater**.
- If the introspection endpoint does not restrict token/resource visibility, it can create a cross-tenant information-disclosure channel.
- If the secret is hardcoded across many services, revoking it impacts multiple systems simultaneously.

Apply **least privilege**, separate client registrations by function, and avoid sharing one credential between introspection and other sensitive operations when the AS allows.

## 10. Separating Secret Rotation from Access-Token and Signing-Key Rotation

Three distinct operations:

| Operation | What Is Replaced? | Primary Impact |
| --- | --- | --- |
| **Introspection secret rotation** | Credential the Resource Server uses to authenticate to the AS introspection endpoint | The API's ability to call `introspect` |
| **Access token rotation/refresh** | Access token the OAuth client sends to the API | A client's session/permissions, token expiry/revocation |
| **JWT signing-key rotation** | Private/public keys used to sign and verify JWTs, with `kid`/JWKS | JWT signature verification; may affect client assertions if that key also serves client auth under contract |

When rotating the **introspection client secret**, users' access tokens **do not automatically need to be reissued**. The AS can still confirm existing active tokens under the new credential if AS policy hasn't changed.

When the AS rotates **JWT signing keys**, an opaque-token Resource Server using introspection might not need to manage public JWKS for access tokens themselves. However, if the Resource Server uses **`private_key_jwt` client authentication** or another JWT layer, those keys must be managed independently.

This matters during investigations:

```text
All opaque access tokens rejected simultaneously by the API
  -> check introspection client credentials, AS endpoint, TLS, network.

Only one access token returns active=false
  -> check that token's expiry/revocation and AS policy.

JWT validation fails after JWKS rotation
  -> investigate signing keys/JWKS; do not blindly rotate the introspection secret.
```

## 11. When Are Secrets Loaded? The Risk of "Rotated in Vault, API Still Uses Old Version"

A bean created when the Spring context starts:

```java
@Bean
OpaqueTokenIntrospector introspector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    return SpringOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();
}
```

Typically this bean holds an HTTP client/credentials built from **the values injected at startup**. If the secret manager publishes a new version, **never assume the bean automatically re-reads the secret on every request**.

The result can be:

```text
Vault current secret = v2
Running instance bean = still using v1
AS already revoked v1 = introspection 401
```

Ways to load the new version:

1. **Rolling restart/redeploy**: each instance initializes a fresh bean with v2; simple and easy to verify.
2. **Controlled config refresh**: the application uses a refresh mechanism that genuinely rebuilds dependencies/HTTP clients with concurrency/lifecycle testing.
3. **Dynamic delegation**: a stable wrapper points to a newly initialized introspector upon a rotation event.

**Do not blindly use `@RefreshScope`, file watchers, or polling** without understanding bean destruction/refresh mechanics, credential leaks, exception handling, and in-flight requests. Depending on your environment, a clean rolling redeploy is often the better choice.

### 11.1. Containerized Deployments

Updating a Kubernetes Secret does not mean:

- Environment variables in a running process update immediately.
- Spring `@Value` fields are re-injected automatically.
- The introspection HTTP client created at startup is rebuilt.

**Environment-variable** secrets typically require restarting the process/pod to pick up new values. File-mounted secrets may update on the volume per platform mechanics, yet the application must **actively re-read and reload the credential**. Test with your exact platform and CSI/secret manager provider.

## 12. Dynamic Reload via Delegate: Swap Implementations Only After Preparation

One way to decouple business code from rotation is keeping the `OpaqueTokenIntrospector` interface stable while holding an `AtomicReference` to the current introspector internally.

Example for **Spring Security 6.5+**:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
        .SpringOpaqueTokenIntrospector;

public final class SwappableOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final AtomicReference<OpaqueTokenIntrospector> current;

    public SwappableOpaqueTokenIntrospector(
            OpaqueTokenIntrospector initial) {
        this.current = new AtomicReference<>(initial);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        return current.get().introspect(token);
    }

    public void activate(OpaqueTokenIntrospector replacement) {
        current.set(replacement);
    }

    public static OpaqueTokenIntrospector createDelegate(
            String uri,
            String clientId,
            String rawClientSecret) {
        return SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(rawClientSecret)
                .build();
    }
}
```

An authorized coordinator can:

```java
OpaqueTokenIntrospector next =
        SwappableOpaqueTokenIntrospector.createDelegate(
                trustedUri, newClientId, newRawSecret);

// Activate only after confirming the new registration/credential is ready.
swappableIntrospector.activate(next);
```

**This is an architectural skeleton**, not a complete automated rotation system. Requirements to implement outside this snippet:

- Accept updates only from an **authenticated secret manager/control plane**, never from an HTTP client request.
- Use approved introspection URI, TLS, timeouts, and auth methods.
- Verify the new credential actually works before activating.
- Do not retain/log two secret versions longer than needed.
- Manage the lifecycle, connections, and resources of the old HTTP client if the implementation owns them.
- Log a **non-sensitive** version/ID in metrics/logs to confirm rollout.
- Account for concurrency: requests that already read `current.get()` before the swap may still use the old delegate.
- Rotate across **every instance**; `AtomicReference` only applies within **one JVM**, not across the cluster.

### 12.1. Why Is an Overlap Window Needed Even with `AtomicReference`?

Suppose a request already started `introspect` with secret v1, and another thread calls `activate(v2)`. That in-flight request may still use v1 when the AS revokes v1, causing it to fail.

Thus dynamic swapping only avoids recreating the Spring context; it **does not replace** coordinating AS active secrets, in-flight requests, and old-secret revocation ordering.

## 13. Should You Automatically Retry with the Old or New Secret?

Some teams consider configuring:

```text
Try introspection with v2.
If AS returns 401, automatically try with v1.
```

This is not a safe default for every system:

- Extends how long the old credential remains usable, defeating emergency compromise rotation.
- Can double load and leak state differences during fallback.
- If HTTP 401 stems from another issue (wrong registration, TLS proxy, or client auth failure), repeated retries can trigger a **retry storm**.
- Two client registrations may have **different introspection permissions**, yielding different active/metadata results.
- Easy to forget to remove the fallback, leaving v1 alive indefinitely.

During **scheduled rotation with overlap**, a **short-lived, bounded, feature-flagged, metric-monitored** fallback is occasionally viable, only if permitted by the AS contract and threat model. Never retry an inactive token (`active=false`) with another secret to "try to make the token active"—that can violate resource scope/visibility.

If a secret is suspected compromised, **never fall back to v1** just for availability. Controlled **rolling updates/blue-green** are generally safer and simpler to operate than complex per-request auth fallback logic.

## 14. Customizing the HTTP Client When mTLS, Proxies, or Timeouts Are Needed

Introspection depends on the network. A production client may need:

- TLS certificate validation, proper truststores, and protection against connecting to spoofed endpoints.
- mTLS client certificates if the AS registers `tls_client_auth` or `self_signed_tls_client_auth`.
- Connect/read timeouts and concurrency limits.
- Approved proxies and egress host/port restrictions.
- Sensible rate limiting / circuit breakers / backoff.
- Log redaction for `Authorization` headers and `token` bodies.

In supported versions, `SpringOpaqueTokenIntrospector` can accept a custom `RestOperations`; Spring Security 7.1+ has `RestClientOpaqueTokenIntrospector` using `RestClient`.

### 14.1. Configuring Basic Auth When Creating Your Own HTTP Client

Conceptual example with `RestTemplate`:

```java
RestTemplate restTemplate = new RestTemplate();
restTemplate.getInterceptors().add(
        new BasicAuthenticationInterceptor(clientId, clientSecret));

OpaqueTokenIntrospector introspector =
        new SpringOpaqueTokenIntrospector(
                introspectionUri, restTemplate);
```

**Important:** this illustrates **configuring authentication on the HTTP client**, not a complete guide to RFC 6749 encoding and rotation. For credentials with special characters, verify version and wire behavior. If HTTP client customization is unnecessary, using the Spring Security 6.5+ builder with **raw credentials** reduces encoding mistakes.

Never build a custom `RestOperations` and forget client authentication; the introspector will send the token without credentials and the AS will reject it.

### 14.2. Never Take the Introspection URI from the Token

The endpoint must come from **approved configuration/trust domains**:

```text
trusted_uri = https://login.example.test/oauth2/introspect
```

Do not do this:

```java
// WRONG: URL suggested by the token sender leads to SSRF/key trust confusion.
String introspectionUri = request.getHeader(
        "X-Introspection-Endpoint");
```

If an API accepts multiple issuers, each issuer must have a **pre-configured trusted** endpoint/credential/policy, and routing must never invent an issuer from unverified values.

## 15. Rotating mTLS Certificates and `private_key_jwt` Keys

If a system uses client authentication **not based on shared secrets**, there is still a credential lifecycle to manage.

### 15.1. mTLS

A Resource Server holds a certificate and private key trusted by the AS per client registration:

```text
Resource Server -> TLS handshake with client certificate C1
Authorization Server -> verify certificate/trust policy
Authorization Server -> allow calling introspection endpoint
```

Rotation requires:

1. Generate a new certificate/private key C2 in HSM/KMS/keystore as appropriate.
2. Register C2 / the trust chain or new identity binding at the AS before use.
3. Verify the TLS handshake and introspection permissions of C2.
4. Deploy the keystore/HTTP client using C2.
5. Keep C1 during the overlap window if permitted by AS policy, accounting for connection pooling / TLS session reuse.
6. Revoke C1 and remove the old key; monitor certificate expiry and revocation.

Never confuse a certificate used for **TLS client authentication** with a public JWK used to **verify JWS access tokens**.

### 15.2. `private_key_jwt`

If the introspection endpoint accepts client assertions:

```text
Client assertion:
  iss = introspection client ID
  sub = introspection client ID
  aud = AS endpoint identifier per contract
  exp = very short lifetime
  jti = anti-replay ID
  signed_by = client private key K1
```

Rotation:

- Publish/register **public key K2** or the new JWKS with the AS.
- Keep K1/K2 active in parallel for the allowed window.
- Switch client assertion signing to private key K2 and its matching `kid`.
- Verify the AS accepts the new assertion and rejects replays.
- Revoke K1 once all instances have migrated.

`kid` only helps the AS choose a registered public key for the client; **it does not create trust on its own**. Private keys must be protected, have expiry/lifecycles, and never enter source control.

**No default Spring Boot opaque-token property configuration automatically handles full mTLS/`private_key_jwt` rotation.** Real implementation and protocol testing are required.

## 16. What Happens When Introspection Client Credentials Are Wrong?

Three scenarios are very easy to confuse:

**Scenario A — Caller sends an invalid access token:**

```text
API calls AS using valid introspection credentials.
AS returns {"active": false}.
Conclusion: caller's token is not accepted.
```

**Scenario B — API uses expired/wrong introspection secret:**

```text
API calls AS using old Basic credentials.
AS returns HTTP 401 (or auth failure response per policy).
Conclusion: client authentication failure between API and AS.
```

**Scenario C — AS is temporarily unreachable:**

```text
API encounters timeout/TLS/DNS/connect error/HTTP 5xx.
No trustworthy introspection response.
Conclusion: dependency unavailable; never assume token is valid.
```

| Signal | Error Layer | What to Do |
| --- | --- | --- |
| `active: false` | Caller's token is inactive | Do not create an authenticated principal |
| AS HTTP 401/403 | Resource Server introspection credentials/permissions | Check registration, secret version, encoding, TLS, scopes |
| AS HTTP 429 | Request rate limit | Shed load / bounded backoff; never fail open |
| AS HTTP 5xx or timeout | AS/network unavailable | Fail closed; alert on dependency incident |
| AS returns malformed JSON | Invalid protocol response | Do not trust metadata; fail in a controlled way |
| AS returns `active=true` lacking required audience | Resource contract mismatch | Reject per policy or fix provider config |
| Token `active=true`, missing endpoint scope | Authorization | Usually 403; do not rotate introspection secret |

### 16.1. What HTTP Status Does the API Return to the Client?

In a Bearer Resource Server:

- Missing Bearer token on a protected endpoint → usually **401**.
- Token determined inactive → usually **401 invalid_token**.
- Token active and authenticated, lacking scope → usually **403 insufficient_scope**.
- AS client credential failure or AS unavailable → depends on Spring Security exception mapping/handlers and deployment. Some configurations return 401 for failures in the authentication chain, yet **operationally** this must not be labeled "caller token invalid" when the true cause is a wrong client secret; infrastructure errors may return 5xx/503 per policy.

Never emit `WWW-Authenticate` headers revealing secret versions, Basic header contents, internal AS URLs, or stack traces. The API can return a generic public error code while internal logs record correlation IDs and root-cause categories.

## 17. Principal Validation After Introspection

An introspection response may contain `scope`, `sub`, `client_id`, `aud`, `iss`, though **not every endpoint returns the same metadata**. Spring Security normally maps scopes to `SCOPE_...` authorities and the principal to `OAuth2AuthenticatedPrincipal`.

Controller example:

```java
@GetMapping("/api/me")
public Map<String, String> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    Object subject = principal.getAttribute("sub");
    return Map.of(
            "subject",
            subject == null ? "unknown" : subject.toString());
}
```

This example only illustrates reading an attribute; production requires a data contract and privacy policy. Never return the full introspection response or secrets to the frontend.

**Never**:

- Treat `active=true` as permission to call every resource.
- Use email or display name as a stable identifier without a contract.
- Add `ROLE_ADMIN` merely because a custom claim contains `"admin"`.
- Grant all scopes to a user because the API's introspection credentials have broad permissions.
- Use another **token's** introspection result due to a bad cache key.

### 17.1. Enforcing Audience with a Decorator

If the issuer commits to returning `aud`, a policy wrapper can require tokens to target this specific API:

```java
public final class ResourceBindingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public ResourceBindingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean accepted =
                (aud instanceof String one
                        && expectedAudience.equals(one))
                || (aud instanceof Collection<?> many
                        && many.contains(expectedAudience));

        if (!accepted) {
            throw new BadOpaqueTokenException(
                    "Access token is not for this resource");
        }
        return principal;
    }
}
```

Imports are omitted. This wrapper accepts only principals returned by **a delegate that introspected successfully**; if the API's introspection credentials are wrong, the delegate must throw an exception and the wrapper **never creates a fake user**.

If the AS does not return `aud` yet guarantees that the introspection credential can inspect only tokens belonging to the right resource, document and test that **equivalent guarantee**; never fabricate an audience from client input.

## 18. Introspection Caching During Credential Rotation

Caching reduces calls to the AS, yet introduces nuances during secret rotation.

### 18.1. Two Distinct Cache Lifecycles

1. **Credential cache:** the process/bean holding secret v1 or v2, which may require re-initialization after rotation.
2. **Introspection result cache:** the API retaining `active=true` metadata and authorities for an access token with a policy-governed TTL.

Never confuse "rotated the secret" with "refreshed all introspection results." If the result cache keeps returning authenticated principals, an outage from a wrong secret **may stay hidden until cache misses occur**, making a broken rollout look successful.

### 18.2. Verify Rotation Without Relying Only on Cache Hits

A valid probe must force a **real introspection request using the new credential**, rather than returning stale cached results. You can use an AS-issued/permitted test token with minimal privileges; avoid feeding production access tokens into general monitoring tools.

When using caching:

- Keep TTL within token expiry and revocation SLA limits.
- Never store raw tokens in logs/metrics or observable cache keys.
- Scope cached results to the right issuer/resource-policy context when multiple ASes/tenants exist.
- Have an invalidation strategy when policies change or tokens are known to be revoked.
- Never treat result-cache hits as proof "the new secret works" while real requests are still using v1.

**Never extend TTL indefinitely to mask 401s from the introspection endpoint.** That turns an outage or credential compromise into the risk of accepting revoked tokens.

## 19. Monitoring Rotation with Safe Signals

Metrics to watch:

| Metric | Operational Question |
| --- | --- |
| Introspection HTTP 2xx, 401/403, 429, 5xx | Is the AS accepting our client credentials? |
| Introspection latency/timeouts | Are AS/network meeting SLA? |
| `active=false` rate | Is there an unusual shift in caller token state? |
| Credential version **identifier** per instance | Which instances are still running v1? |
| Request counts seen by AS under v1/v2 | Is it safe to revoke v1 yet? |
| Cache hit/miss | Did the probe actually reach the AS or just hit cache? |
| API 401/403/5xx | Are errors token/authorization issues or introspection infrastructure? |
| Instances not yet rolled out | Which regions/workers still hold the old secret? |

Log only **non-sensitive version IDs** such as `credential-generation=2026-11-B`—never actual secrets, simple hashes of secrets, Basic Authorization headers, or raw access tokens.

### 19.1. Do Not Enable Uncontrolled HTTP Wire Logging

During debugging, HTTP client interceptors, reverse proxies, or APM agents can log:

- `Authorization: Basic ...` headers containing Resource Server credentials.
- Form request bodies containing `token=...`, the Bearer access token.
- JSON introspection responses containing subjects, scopes, emails, or sensitive metadata.

Enforce **redaction at every layer** (HTTP client, proxy, tracing, diagnostics, error reporting). Never surface these details on public dashboards.

### 19.2. A Critical Distinction When Analyzing Logs

```text
API returns 401 to user request
    !=
AS returns HTTP 401 to API introspection request
```

These are events on **two different HTTP hops**. Without distinguishing them, operations may tell all users to log in again when the real cause is **an expired Resource Server secret**.

## 20. Testing the Rotation Strategy

A practical test suite must cover **wire protocol**, **secret lifecycle**, and **authorization behavior**.

### 20.1. Unit Testing Fail-Closed Wrappers

Test a throwing delegate:

```java
OpaqueTokenIntrospector failingDelegate = token -> {
    throw new OAuth2IntrospectionException(
            "Introspection service unavailable");
};

OpaqueTokenIntrospector guarded =
        new ResourceBindingIntrospector(
                failingDelegate, "orders-api");

assertThrows(OAuth2IntrospectionException.class,
        () -> guarded.introspect("test-token"));
```

This test illustrates that the decorator **does not invent a principal** when the delegate fails. No HTTP server is needed for this test. Exception names/imports should match your Spring Security version.

### 20.2. HTTP Protocol Tests with a Mock AS

Use WireMock, MockWebServer, or a test HTTP endpoint to verify:

1. Introspection requests send **POST** to the trusted URL.
2. Form parameter `token` equals the exact token received from the caller.
3. Client authentication matches the format registered with the AS.
4. Client IDs/secrets with special characters are encoded **exactly once**.
5. `active=true` builds the right principal/authorities.
6. `active=false` creates no authentication.
7. HTTP 401 at the introspection endpoint is recorded as **client-auth failure**, not token revocation.
8. 5xx/timeouts/TLS errors **never cause the app to fail open**.
9. Logs/metrics contain neither secrets nor tokens.

### 20.3. Testing Rotation with Overlap

Suppose the mock AS accepts v1 and v2:

| Step | AS Accepts | Resource Server Uses | Expected Outcome |
| --- | --- | --- | --- |
| 1 | v1 | v1 | Introspection works |
| 2 | v1 and v2 | v1 | Works as before |
| 3 | v1 and v2 | v2 on a subset of instances | Both groups keep working |
| 4 | v1 and v2 | v2 on all instances | Real introspection probes pass |
| 5 | v2 only | v2 on all instances | Works after v1 revocation |
| 6 | v2 only | Intentionally use v1 in negative test | AS rejects old credential |

Tests must prove **the old credential truly stops working** after revocation; writing `v2` in a deployment manifest is not enough.

### 20.4. Testing a Single-Secret Provider

| Condition | Expected Outcome |
| --- | --- |
| AS switched v1 → v2, instance still holds v1 | Introspection client auth fails |
| AS uses v2, instance updated to v2 | Introspection passes |
| Using blue-green registrations v1 and v2 both allowed | Zero-disruption rolling migration possible |
| Blue-green v2 lacks permission to introspect `orders-api` | Do not treat v2 as "ready" merely because HTTP Basic succeeded |

For non-overlapping cutovers, tests must reveal **potential disruption points** and the health gates required before opening traffic.

### 20.5. Concurrency Tests When Swapping Delegates

If using `SwappableOpaqueTokenIntrospector`:

- A request that already read delegate v1 may still be running when v2 is activated.
- New requests after the swap must use v2.
- `current` must never be `null`.
- Rollback is allowed only if the old credential is still active and not suspected compromised.
- Multi-instance/cluster tests must run at the orchestration layer; `AtomicReference` does not synchronize across JVMs.

### 20.6. MockMvc Through the Real Filter Chain

Conceptual sketch:

```java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer active-read"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer active-no-scope"))
        .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer inactive"))
        .andExpect(status().isUnauthorized());
```

These examples assume a test introspection endpoint or fake `OpaqueTokenIntrospector` configured to distinguish the three tokens and a controller returning 200 when valid. These **are not executed test outputs**.

If using:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))));
```

then Spring Security Test's `jwt()` can **bypass introspection** by pre-populating a mock Authentication. Such tests are useful for authorization, yet **do not prove secret/Basic client authentication, rotation, or `active` validation**.

## 21. Deployment Runbook: Milestone Control Template

A scheduled rotation runbook can be standardized as follows.

### Before Rollout

1. Confirm the AS owner, credential registration, introspection permissions, and target environments.
2. Verify whether the AS supports overlap or requires two client registrations.
3. Generate the new credential, store a new secret manager version, enforce IAM/dual-approval.
4. Prepare deployment config/secret references, keeping client ID and secret in **the same bundle**.
5. Set up dashboards for AS client-auth failures, API 401/403/5xx, and cache misses.
6. Prepare a verification probe using a minimal-privilege test token over the **real introspection path**.

### During Rollout

1. Enable v2 in the AS without revoking v1 yet if overlap is supported.
2. Deploy a canary instance using v2.
3. Confirm the AS sees v2, active/inactive test requests behave correctly, and scopes/audience remain unchanged.
4. Roll out instance groups incrementally, including DR/standby regions.
5. Halt rollout on AS HTTP 401s, TLS errors, or unexpected shifts in active metadata.
6. Never fall back to fail-open or extend cache TTLs indefinitely to mask errors.

### After Rollout

1. Confirm zero valid introspection traffic remains on v1 within the observation window.
2. Revoke v1 in the AS.
3. Negative-test that v1 is rejected; positive-test that v2 continues working.
4. Remove v1 copies from runtime/secret stores per retention policy, and audit CI/CD and tooling.
5. Record audit log: timestamp, credential **version identifier**, approver/approval mechanism, test results, and incidents.
6. Schedule the next rotation and pre-expiration alerts.

### Abort / Rollback Conditions

- **Roll back to v1** only if v1 is **still active and not suspected compromised**.
- If v1 was revoked due to an incident, never re-enable it just to restore service without security approval.
- If v2 lacks permission to introspect the right resource, **do not revoke v1** during scheduled rotation until fixed and tested.
- If the AS lacks overlap support, execute the approved cutover/blue-green/maintenance plan rather than relying on an uncertain rollback.

## 22. Anti-Patterns to Avoid

### 22.1. Sharing One Production Secret Across Multiple Environments

Dev/staging/prod require separate trust boundaries. A shared secret lets a compromise in a less-protected environment impact production. Separate client registrations and introspection permissions per environment when supported by the AS.

### 22.2. Hardcoding or Committing Secrets to Source

Even if removed in a later commit, secrets can linger in Git history, build artifacts, logs, or CI caches. If exposure is discovered, **revoke and reissue**—never just delete the line from the repo.

### 22.3. Keeping the Old Secret Indefinitely Out of Fear of Downtime

Overlap is only a transition window. Without revoking the old secret, rotation is incomplete and the blast radius never shrinks.

### 22.4. Changing a Vault Secret and Assuming Spring Beans Auto-Update

Beans built from `@Value` usually hold startup credentials. Use controlled restarts/refreshes/delegate swaps—never guess that configuration reloaded.

### 22.5. Confusing AS HTTP 401 with an Invalid User Bearer Token

The AS rejecting the Resource Server's client credentials is a fault in the token-verification service. Classify it properly to fix secret/registration/encoding rather than needlessly forcing all users to refresh tokens.

### 22.6. Skipping `active` Checks to Avoid AS Dependency

An HTTP 200 with `active=false` is still a rejected token. When the AS times out, there is no basis to create a trusted principal.

### 22.7. Letting Clients Supply Arbitrary Introspection URLs

Introspection endpoints carry Resource Server credentials; choosing URLs from input causes SSRF and Basic credential leaks. Pin allowlisted URLs and trusted TLS.

### 22.8. Logging Credentials Alongside Caller Tokens in Logs or Telemetry

Both Basic headers and `token` bodies are sensitive. Mask/redact across HTTP clients, reverse proxies, and APMs.

### 22.9. Testing Only Success Without Testing Expired Secrets

If tests always mock `OAuth2AuthenticatedPrincipal`, they skip the HTTP client and miss encoding/rotation failures. Write protocol tests with a mock AS plus negative tests.

### 22.10. Treating `client_id` in the Introspection Response as the Introspection Client ID

`client_id` **in the response** usually identifies the OAuth client **issued the access token**. The client ID used in Basic auth to call introspection is a **separate** registration for the Resource Server. Do not confuse the response client ID with API credentials or permissions.

### 22.11. Accepting Active Tokens Belonging to Another Resource

If the API is `orders-api`, a token with `aud=payments-api` is not automatically valid just because the AS returned `active=true`. Enforce resource binding via the AS or API validators.

### 22.12. Using the Same Introspection Permissions Across All Tenants

One credential could inspect tokens/metadata of other tenants unless restricted by the AS. Enforce least privilege, tenant isolation, and real introspection authorization rather than merely naming secrets differently.

## 23. Practical Troubleshooting Scenarios

### Scenario A — API Errors Across the Board After Changing Secrets

Suppose all Bearer requests return 401 for several minutes after the AS rotates credentials. AS logs show `invalid_client` or Basic auth failures for `orders-introspector`. Likely the process still holds the old secret or suffers double-encoding. Check the loaded secret version, bean lifecycle, encoding method, and AS registration; **do not immediately conclude user tokens expired**.

### Scenario B — Canary Works, Older Production Pods Start Failing

The AS allows v1/v2 active, and the v2 canary passes. An operator revokes v1 too early while some pods have not redeployed yet. Those pods keep using v1 and introspection fails. Maintain overlap until confirming **all instances** have received v2. If the AS already revoked v1, finish the rollout or execute the approved rollback runbook.

### Scenario C — AS Does Not Support Multiple Secrets

An organization cannot roll out seamlessly if regenerating a secret immediately invalidates v1. Solution: register a new v2 introspection client with equivalent permissions if supported by the provider; otherwise schedule a controlled maintenance/cutover window. Never promise zero downtime solely because of Kubernetes rolling updates.

### Scenario D — Secret Contains Special Characters

The new client secret contains `+` and `%`. Legacy code pre-percent-encoded it, while the new builder encodes it again. The AS returns HTTP 401. Pass **raw credentials** to the 6.5+ builder per its contract and test wire-level Basic authentication against a mock endpoint. Never log Basic headers.

### Scenario E — AS Times Out During Peak Hours

Many concurrent requests call introspection, and the AS hits limits or a TLS proxy fails. Never catch the exception and return a default principal. Use timeouts, bounded backoff, rate limiting, caching aligned with revocation SLAs, and a fail-closed circuit breaker.

### Scenario F — v2 Has Different Permissions from v1

An AS admin created a new client registration for rotation but forgot to grant permission to introspect `orders-api` tokens. v2 Basic authentication succeeds, yet the AS omits expected metadata. Verify **resource permissions**, `active` responses, and scopes/audience in canary; declare migration successful only when semantics match.

### Scenario G — mTLS Certificate Nearing Expiration

The certificate the Resource Server uses to authenticate introspection is about to expire. Rotate the private key/cert so the AS trusts the new one before shifting traffic, and confirm the HTTP client actually reloads the new keystore. Never confuse client-auth certificates with JWT public JWKS used to verify access tokens.

### Scenario H — Caller Token Is Active Yet Lacks Scope

AS introspection returns `active=true`, `scope="orders:read"`. The client calls an endpoint requiring `SCOPE_orders:write`. **Authentication succeeds**, authorization denies (usually 403). Rotating the introspection secret does not grant additional scopes to tokens.

## 24. Self-Check Questions

**1. How many credentials exist in the Resource Server → AS introspection flow?** At a minimum, distinguish the caller's Bearer token from the separate credential authenticating the Resource Server to the introspection endpoint.

**2. Does HTTP 200 from the AS guarantee the token is active?** No. You must inspect `active` in the response.

**3. Is the introspection client secret the AS's JWT signing key?** No. They serve different authentication flows.

**4. Why shouldn't secrets be stored directly in `application.yml` in Git?** They can leak via source, history, artifacts, and tooling; use secret management, IAM, and rotation.

**5. Does the `SpringOpaqueTokenIntrospector` builder in 6.5+ take raw or percent-encoded secrets?** It takes **raw/unencoded** values; the builder handles encoding per API version.

**6. When a secret changes in the secret manager, do Spring beans created at startup automatically pick up the new version?** Not by default; you need a designed refresh/redeploy/delegate-swap mechanism.

**7. When the AS allows only one active secret, is a rolling update automatically zero-downtime?** No. You need blue-green registration or a coordinated cutover; a maintenance window may be required.

**8. Should the old secret stay active indefinitely to reduce outage risk?** No. Define an overlap duration and a revocation step.

**9. When a secret is suspected compromised, should you prioritize availability by keeping v1?** No. Incident response must stop abuse; emergency revocation of v1 may be required.

**10. Does an HTTP 401 from the introspection endpoint prove the user's Bearer token is invalid?** No; it more likely indicates incorrect Resource Server credentials/permissions, which must be distinguished by HTTP hop.

**11. Can you cache `active=true` indefinitely so you don't have to call the AS during outages?** No; that breaks revocation and expiration semantics.

**12. Does secret rotation force users to log in again?** Not by default. Rotating internal introspection credentials does not change callers' access tokens.

**13. Must `client_id` in the introspection response match the client ID the Resource Server uses for Basic auth?** No. The response typically names the OAuth client issued the token, whereas Basic auth uses the Resource Server's own identity.

**14. When using `private_key_jwt`, which keys must be rotated?** The private key signing client assertions and the public key/JWKS registered with the AS, along with `kid`/`jti`/`exp` policies.

**15. Why is a `MockMvc.jwt()` test insufficient to test rotation?** Because it can synthesize mock authentication, bypassing `OpaqueTokenIntrospector` and client authentication requests to the AS.

## 25. References and Standards for Further Reading

- **RFC 7662 — OAuth 2.0 Token Introspection:** endpoint, `active`, access control, and response metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6749 — OAuth 2.0 Authorization Framework:** client authentication, confidential clients, and `client_secret_basic` rules. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** passing Bearer access tokens and 401/403 errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** certificate-based client auth. https://www.rfc-editor.org/rfc/rfc8705
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT client assertions. https://www.rfc-editor.org/rfc/rfc7523
- **Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token:** configuring introspection, `OpaqueTokenIntrospector`, and Spring implementations. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Boot — OAuth2 Resource Server:** auto-configuration, `opaquetoken.*` properties, and custom introspector beans. https://docs.spring.io/spring-boot/reference/security/oauth2.html
- **Spring Security — Migration to 7 (Opaque Token Credentials):** changes to client ID/secret encoding during upgrades. https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html

**Conclusion:** The credential used to call introspection is **the Resource Server's machine-to-machine identity before the Authorization Server**, not the user's Bearer token. Protect credentials with **TLS, least privilege, secret managers, logging redaction**, and a verifiable rotation process. When the AS supports overlap, deploy the new secret first and only then revoke the old one; when it does not, use blue-green client registrations or a controlled cutover. In Spring Security, know which secret version your introspector bean was built from and how client authentication is encoded; on errors, distinguish **inactive tokens**, **client authentication failures**, and **AS/network unavailability**, always **failing closed** instead of accepting unverified access tokens.
